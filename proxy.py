"""  # v8.7
Trader Desk — Proxy Server v8.7
Indicadores tecnicos + fundamentalistas + Monte Carlo + Futuros
Mudancas v8.5:
- Cache BTC indicators/cycle (10-15 min)
- Range Yahoo BTC reduzido de 4y para 1y/2y (mais rapido no Render)
- Indicadores B3 com campo 'explicacao' textual
- Calendario com multiplos User-Agents + fallback TradingView
- HTML v10.1 embutido
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import math
import time

try:
    import numpy as _np
    _NUMPY = True
except ImportError:
    _NUMPY = False

app = Flask(__name__)
_IND_CACHE = {}
_BTC_CACHE = {}   # cache BTC indicators e cycle
CORS(app)
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── SETORES ───────────────────────────────────────────
SETORES = {
    'PETR4.SA': {'nome':'Petroleo & Gas','pl_medio':6.0,'pvp_medio':1.5,'roe_min':15},
    'VALE3.SA':  {'nome':'Mineracao',    'pl_medio':7.0,'pvp_medio':1.8,'roe_min':15},
    'BBAS3.SA':  {'nome':'Bancos',       'pl_medio':8.0,'pvp_medio':1.2,'roe_min':18},
    'AXIA3.SA':  {'nome':'Energia Eletrica','pl_medio':12.0,'pvp_medio':1.2,'roe_min':10},
    'ROXO34.SA': {'nome':'Fintech/BDR',    'pl_medio':40.0,'pvp_medio':5.0,'roe_min':10},
    'DEFAULT':   {'nome':'Geral',        'pl_medio':12.0,'pvp_medio':2.0,'roe_min':12},
}

FUND = {
    'PETR4': {'pvp':1.65,'dy':6.42,'lpa':8.54, 'vpa':29.76,'ev_ebitda':3.2, 'roe':22.5,'debt_ebitda':0.8, 'margem':18.3},
    'VALE3': {'pvp':1.80,'dy':8.50,'lpa':11.20,'vpa':47.30,'ev_ebitda':4.1, 'roe':24.1,'debt_ebitda':0.6, 'margem':22.1},
    'BBAS3': {'pvp':0.95,'dy':9.80,'lpa':4.20, 'vpa':24.80,'ev_ebitda':None,'roe':19.8,'debt_ebitda':None,'margem':28.5},
    'AXIA3': {'pvp':0.85,'dy':4.20,'lpa':1.90, 'vpa':12.50,'ev_ebitda':7.5, 'roe':10.0,'debt_ebitda':3.2, 'margem':15.0},
    'ROXO34':{'pvp':3.50,'dy':0.00,'lpa':0.45, 'vpa':3.60, 'ev_ebitda':None,'roe':8.5, 'debt_ebitda':None,'margem':18.0},
}

# ── CDI ───────────────────────────────────────────────
def get_cdi():
    try:
        r = requests.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.4389/dados/ultimos/1?formato=json', timeout=5)
        if r.ok:
            cdi_d = float(r.json()[0]['valor'])
            cdi_anual = ((1 + cdi_d/100)**252 - 1)*100
            if 5 <= cdi_anual <= 20:
                return round(cdi_anual, 2)
    except: pass
    return 14.40

# ── CALC TECNICO ──────────────────────────────────────
def rsi(closes, p=14):
    if len(closes) < p+1: return None
    g,l=[],[]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]; g.append(max(d,0)); l.append(max(-d,0))
    ag=sum(g[:p])/p; al=sum(l[:p])/p
    for i in range(p,len(g)):
        ag=(ag*(p-1)+g[i])/p; al=(al*(p-1)+l[i])/p
    return round(100-(100/(1+ag/al)),2) if al else 100.0

def mm(closes, p):
    return round(sum(closes[-p:])/p,2) if len(closes)>=p else None

def ema(closes, p):
    if len(closes)<p: return None
    k=2/(p+1); e=sum(closes[:p])/p
    for c in closes[p:]: e=c*k+e*(1-k)
    return round(e,2)

def macd(closes):
    e12=ema(closes,12); e26=ema(closes,26)
    if not e12 or not e26: return None,None,None
    ml=round(e12-e26,4)
    if len(closes)>=35:
        ms=[]
        for i in range(26,len(closes)):
            a=ema(closes[:i+1],12); b=ema(closes[:i+1],26)
            if a and b: ms.append(a-b)
        sig=ema(ms,9) if len(ms)>=9 else None
        hist=round(ml-sig,4) if sig else None
    else: sig=hist=None
    return ml,sig,hist

def bollinger(closes, p=20, s=2):
    if len(closes)<p: return None,None,None
    r=closes[-p:]; m=sum(r)/p
    std=math.sqrt(sum((x-m)**2 for x in r)/p)
    return round(m+s*std,2),round(m,2),round(m-s*std,2)

def obv(closes, vols):
    if len(closes)<2: return None,'flat'
    o=0; os=[0]
    for i in range(1,len(closes)):
        if closes[i]>closes[i-1]: o+=vols[i]
        elif closes[i]<closes[i-1]: o-=vols[i]
        os.append(o)
    trend='subindo' if len(os)>=20 and os[-1]>os[-20] else 'caindo'
    return o,trend

def graham(lpa, vpa):
    if lpa and vpa and lpa>0 and vpa>0:
        return round(math.sqrt(22.5*lpa*vpa),2)
    return None

def vol_hist(closes):
    if len(closes)<22: return 0.35
    rets=[math.log(closes[-i]/closes[-i-1]) for i in range(1,22)]
    m=sum(rets)/len(rets)
    return round(math.sqrt(sum((r-m)**2 for r in rets)/len(rets)*252),4)

# ── ONCHAIN (estimativas) ────────────────────────────
def get_btc_onchain():
    try:
        r = requests.get('https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1d&range=1y',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
        if r.ok:
            cl = [c for c in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
            if cl:
                price = cl[-1]
                ma200 = mm(cl, min(200, len(cl)))
                realized = ma200 * 0.82 if ma200 else price * 0.75
                mvrv = round((price - realized) / realized, 2) if realized else 1.2
                nupl = round(max(0, min(1, (price - realized) / price)), 2) if realized else 0.5
                puell = round(price / (ma200 * 1.1), 2) if ma200 else 1.5
                sopr = round(1 + mvrv * 0.1, 3)
                return {'mvrv_zscore': mvrv, 'nupl': nupl, 'puell_multiple': puell,
                        'sopr': sopr, 'realized_price': round(realized, 0), 'updated': 'estimado'}
    except: pass
    return {'mvrv_zscore': 1.2, 'nupl': 0.55, 'puell_multiple': 1.5,
            'sopr': 1.02, 'realized_price': 75000, 'updated': 'fallback'}

# ── TRADINGVIEW ───────────────────────────────────────
@app.route('/tv/brazil', methods=['POST'])
def tv_brazil():
    try:
        r=requests.post('https://scanner.tradingview.com/brazil/scan',json=request.get_json(),timeout=5)
        return jsonify(r.json())
    except Exception as e: return jsonify({'error':str(e)}),500

@app.route('/tv/forex', methods=['POST'])
def tv_forex():
    try:
        r=requests.post('https://scanner.tradingview.com/forex/scan',json=request.get_json(),timeout=5)
        return jsonify(r.json())
    except Exception as e: return jsonify({'error':str(e)}),500

# ── YAHOO HELPER ──────────────────────────────────────
def yquote(ticker):
    try:
        r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d',
            headers={'User-Agent':'Mozilla/5.0'},timeout=6)
        if not r.ok: return None
        d=r.json(); m=d['chart']['result'][0]['meta']
        cl=[c for c in d['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        p=m.get('regularMarketPrice',cl[-1] if cl else None)
        v=m.get('chartPreviousClose',cl[-2] if len(cl)>1 else p)
        return {'price':round(float(p),2),'prev':round(float(v),2)} if p else None
    except: return None

# ── FUTUROS ───────────────────────────────────────────
@app.route('/futures', methods=['GET'])
def get_futures():
    dji = yquote('%5EDJI')
    esf = yquote('ES%3DF')
    nqf = yquote('NQ%3DF')
    vix = yquote('%5EVIX')
    dxy = None
    win = None

    try:
        r_dxy = requests.post('https://scanner.tradingview.com/forex/scan',
            json={"symbols":{"tickers":["TVC:DXY"]},"columns":["close","change_abs"]}, timeout=6)
        if r_dxy.ok:
            items = r_dxy.json().get('data',[])
            if items:
                d = items[0].get('d',[])
                if d and d[0]:
                    close = round(float(d[0]),2)
                    chg = float(d[1]) if len(d)>1 and d[1] else 0
                    dxy = {'price':close,'prev':round(close-chg,2)}
    except: pass

    if not dxy:
        try:
            r_dxy2 = requests.post('https://scanner.tradingview.com/america/scan',
                json={"symbols":{"tickers":["TVC:DXY"]},"columns":["close","change_abs"]}, timeout=6)
            if r_dxy2.ok:
                items = r_dxy2.json().get('data',[])
                if items:
                    d = items[0].get('d',[])
                    if d and d[0]:
                        close = round(float(d[0]),2)
                        chg = float(d[1]) if len(d)>1 and d[1] else 0
                        dxy = {'price':close,'prev':round(close-chg,2)}
        except: pass

    try:
        r_win = requests.post('https://scanner.tradingview.com/futures/scan',
            json={"symbols":{"tickers":["BMFBOVESPA:WIN1!"]},"columns":["close","change_abs"]}, timeout=6)
        if r_win.ok:
            items = r_win.json().get('data',[])
            if items and items[0].get('d') and items[0]['d'][0]:
                d2 = items[0]['d']
                close = round(float(d2[0]),0)
                chg = float(d2[1]) if len(d2)>1 and d2[1] else 0
                win = {'price':close,'prev':round(close-chg,0),'source':'TV futures'}
    except: pass

    if not win:
        try:
            r_win2 = requests.post('https://scanner.tradingview.com/brazil/scan',
                json={"symbols":{"tickers":["BMFBOVESPA:WIN1!"]},"columns":["close","change_abs"]}, timeout=6)
            if r_win2.ok:
                items2 = r_win2.json().get('data',[])
                if items2 and items2[0].get('d') and items2[0]['d'][0]:
                    d3 = items2[0]['d']
                    close = round(float(d3[0]),0)
                    chg = float(d3[1]) if len(d3)>1 and d3[1] else 0
                    win = {'price':close,'prev':round(close-chg,0),'source':'TV brazil'}
        except: pass

    if not win:
        try:
            ibov = yquote('%5EBVSP')
            if ibov: win = {'price':round(ibov['price'],0),'prev':round(ibov['prev'],0),'source':'IBOV'}
        except: pass

    usd = yquote('USDBRL=X')
    return jsonify({'dji':dji,'esf':esf,'nqf':nqf,'win':win,'vix':vix,'dxy':dxy,'usd':usd})

@app.route('/dji', methods=['GET'])
def get_dji():
    d=yquote('%5EDJI')
    return jsonify(d) if d else (jsonify({'error':'indisponivel'}),500)

# ── FUNDING RATE ──────────────────────────────────────
@app.route('/binance/funding', methods=['GET'])
def binance_funding():
    try:
        r=requests.post('https://api.hyperliquid.xyz/info',
            json={'type':'metaAndAssetCtxs'},
            headers={'Content-Type':'application/json'},timeout=8)
        if r.ok:
            d=r.json(); univ=d[0].get('universe',[]); ctxs=d[1] if len(d)>1 else []
            idx=next((i for i,u in enumerate(univ) if u.get('name')=='BTC'),None)
            if idx is not None and idx<len(ctxs):
                fr=float(ctxs[idx].get('funding',0))*8
                return jsonify({'lastFundingRate':str(fr),'nextFundingTime':int(time.time()*1000)+3600000,'source':'Hyperliquid'})
    except: pass
    return jsonify({'error':'indisponivel'}),500

# ── MONTE CARLO ───────────────────────────────────────
@app.route('/montecarlo/barrier', methods=['POST'])
def run_montecarlo_barrier():
    try:
        import numpy as _np
        data = request.get_json() or {}
        ticker   = data.get('ticker', 'AXIA3.SA')
        entry    = float(data.get('entry', 54.31))
        kdo      = float(data.get('kdo', 43.39))
        kuo      = float(data.get('kuo', 68.48))
        T_days   = int(data.get('t_days', 113))
        n        = 3000
        steps    = max(T_days // 5, 10)
        S = float(data.get('price',0)) or None
        sigma = float(data.get('sigma', 0.35))
        if not S:
            for host in ['query1','query2']:
                try:
                    r2=requests.get(
                        f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=60d',
                        headers={'User-Agent':'Mozilla/5.0'},timeout=6)
                    if r2.ok:
                        d2=r2.json()
                        meta=d2['chart']['result'][0]['meta']
                        raw_cl=d2['chart']['result'][0]['indicators']['quote'][0]['close']
                        cl=[c for c in raw_cl if c is not None]
                        S=float(meta.get('regularMarketPrice',cl[-1] if cl else 0))
                        if cl: sigma=vol_hist(cl)
                        break
                except: continue
        if not S or S<=0:
            return jsonify({'error':f'Nao foi possivel obter preco de {ticker}'}),500
        dt = 1/252.0
        drift = (0 - 0.5 * sigma**2) * dt
        vol_step = sigma * (dt**0.5)
        z = _np.random.standard_normal((n, steps))
        log_returns = drift + vol_step * z
        paths = S * _np.exp(_np.cumsum(log_returns, axis=1))
        max_prices = _np.max(paths, axis=1)
        min_prices = _np.min(paths, axis=1)
        kuo_hit = max_prices >= kuo
        kdo_hit = min_prices <= kdo
        no_barrier = ~kuo_hit & ~kdo_hit
        return jsonify({
            'ticker': ticker, 'preco_atual': round(S, 2),
            'entry': entry, 'kdo': kdo, 'kuo': kuo, 't_days': T_days,
            'volatilidade_historica_pct': round(sigma * 100, 2),
            'prob_sem_barreira': round(float(no_barrier.mean() * 100), 2),
            'prob_barreira_alta': round(float(kuo_hit.mean() * 100), 2),
            'prob_barreira_baixa': round(float(kdo_hit.mean() * 100), 2),
            'cenarios': n, 'engine': 'numpy-paths'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/montecarlo', methods=['POST'])
def run_montecarlo():
    try:
        import numpy as np
        data=request.get_json() or {}
        ticker=data.get('ticker','BBAS3.SA')
        K_call=float(data.get('k_call',22.68))
        K_put=float(data.get('k_put',22.68))
        T_days=int(data.get('t_days',21))
        n=5000
        kd=float(data['knock_down']) if data.get('knock_down') else None
        S = float(data['price']) if data.get('price') else None
        sigma = float(data['sigma']) if data.get('sigma') else 0.35
        cl = []
        if not S:
            for host in ['query1','query2']:
                try:
                    r=requests.get(
                        f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=60d',
                        headers={'User-Agent':'Mozilla/5.0'},timeout=6)
                    if r.ok:
                        d=r.json()
                        meta=d['chart']['result'][0]['meta']
                        raw_cl=d['chart']['result'][0]['indicators']['quote'][0]['close']
                        cl=[c for c in raw_cl if c is not None]
                        S=float(meta.get('regularMarketPrice',cl[-1] if cl else 0))
                        if cl: sigma=vol_hist(cl)
                        break
                except: continue
        if not S or S<=0:
            return jsonify({'error':f'Nao foi possivel obter preco de {ticker}'}),500
        if not sigma or sigma==0.35:
            vol_defaults={'AXIA3':0.35,'ROXO34':0.45,'PETR4':0.30,'VALE3':0.32}
            sigma=vol_defaults.get(ticker.replace('.SA','').upper(),0.35)
        if cl and not data.get('sigma'):
            sigma=vol_hist(cl)
        T=max(T_days,1)/252.0
        sqT=math.sqrt(T)
        drift=-0.5*sigma**2*T
        z=np.random.standard_normal(n)
        ST=S*np.exp(drift+sigma*sqT*z)
        call_ex=ST>K_call
        kdo_hit=(ST<=kd) if kd else np.zeros(n,dtype=bool)
        res={
            'prob_sucesso':round(float((~call_ex).mean()*100),2),
            'prob_call_exercida':round(float(call_ex.mean()*100),2),
            'prob_put_exercida':round(float(call_ex.mean()*100),2),
            'prob_kdo_atingido':round(float(kdo_hit.mean()*100),2) if kd else None,
            'cenarios':n,'engine':'numpy',
            'preco_atual':round(S,2),
            'volatilidade_historica_pct':round(sigma*100,2),
            'k_call':K_call,'k_put':K_put,
            'knock_down':kd,'t_days':T_days,'ticker':ticker
        }
        return jsonify(res)
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── INDICADORES B3 — v8.5 com explicacao ─────────────
@app.route('/indicators/<path:ticker>', methods=['GET'])
def get_indicators(ticker):
    import time as _t
    global _IND_CACHE
    try:
        if ticker in _IND_CACHE:
            cd, ct = _IND_CACHE[ticker]
            if _t.time() - ct < 300:
                return jsonify(cd)
    except: pass
    try:
        symbol = ticker.replace('.SA','').upper()
        cdi = get_cdi()
        hist_closes = []
        fund = {}
        preco_atual = None
        preco_prev = None

        try:
            rb = requests.get(
                f'https://brapi.dev/api/quote/{symbol}?range=3mo&interval=1d&fundamental=true',
                headers={'User-Agent':'Mozilla/5.0'}, timeout=12)
            if rb.ok:
                rd = rb.json().get('results',[{}])[0]
                preco_atual = rd.get('regularMarketPrice')
                preco_prev  = rd.get('regularMarketPreviousClose', preco_atual)
                hist = rd.get('historicalDataPrice',[])
                hist_closes = [x['close'] for x in hist if x.get('close')]
                fund = {
                    'pl':   rd.get('priceEarnings'),
                    'pvp':  rd.get('priceToBook'),
                    'dy':   rd.get('dividendYield'),
                    'roe':  rd.get('returnOnEquity'),
                    'lpa':  rd.get('earningsPerShare'),
                    'vpa':  rd.get('bookValuePerShare'),
                }
        except: pass

        if not hist_closes:
            try:
                ry = requests.get(
                    f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=3mo',
                    headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
                if ry.ok:
                    dy = ry.json()
                    meta = dy['chart']['result'][0]['meta']
                    preco_atual = preco_atual or meta.get('regularMarketPrice')
                    raw = dy['chart']['result'][0]['indicators']['quote'][0]['close']
                    hist_closes = [c for c in raw if c]
            except: pass

        if not hist_closes or not preco_atual:
            return jsonify({'error': f'Sem dados para {symbol}'}), 404

        # Hardcoded fundamentais
        FUND_OVERRIDE = {
            'PETR4': {'pvp':1.65,'dy':6.42,'lpa':8.54,'vpa':29.76,'roe':22.5,'pl':5.8},
            'VALE3': {'pvp':1.80,'dy':8.50,'lpa':11.20,'vpa':47.30,'roe':24.1,'pl':7.2},
            'BBAS3': {'pvp':0.95,'dy':9.80,'lpa':4.20,'vpa':24.80,'roe':19.8,'pl':5.2},
            'AXIA3': {'pvp':0.85,'dy':4.20,'lpa':1.90,'vpa':12.50,'roe':10.0,'pl':12.0},
            'ROXO34':{'pvp':3.50,'dy':0.00,'lpa':0.45,'vpa':3.60,'roe':8.5,'pl':40.0},
        }
        if symbol in FUND_OVERRIDE:
            for k,v in FUND_OVERRIDE[symbol].items():
                if v is not None: fund[k] = fund.get(k) or v

        SETOR_MAP = {
            'PETR4': {'nome':'Petroleo & Gas','pl_medio':6.0,'pvp_medio':1.5,'roe_min':15},
            'VALE3': {'nome':'Mineracao','pl_medio':7.0,'pvp_medio':1.8,'roe_min':15},
            'BBAS3': {'nome':'Bancos','pl_medio':8.0,'pvp_medio':1.2,'roe_min':18},
            'AXIA3': {'nome':'Energia Eletrica','pl_medio':12.0,'pvp_medio':1.2,'roe_min':10},
            'ROXO34':{'nome':'Fintech/BDR','pl_medio':40.0,'pvp_medio':5.0,'roe_min':10},
        }
        setor = SETOR_MAP.get(symbol, {'nome':'Geral','pl_medio':12.0,'pvp_medio':2.0,'roe_min':12})

        closes = hist_closes
        p = float(preco_atual)

        def _mm(lst, n):
            return round(sum(lst[-n:])/n, 2) if len(lst) >= n else None
        def _rsi(cls, n=14):
            if len(cls) < n+1: return None
            gains = [max(cls[i]-cls[i-1],0) for i in range(1,len(cls))]
            losses = [max(cls[i-1]-cls[i],0) for i in range(1,len(cls))]
            ag=sum(gains[:n])/n; al=sum(losses[:n])/n
            for i in range(n,len(gains)):
                ag=(ag*(n-1)+gains[i])/n; al=(al*(n-1)+losses[i])/n
            return round(100-100/(1+ag/al),1) if al else 100.0

        rsi14 = _rsi(closes)
        ma20  = _mm(closes,20)
        ma50  = _mm(closes,50)
        ma200 = _mm(closes,200)

        pl   = fund.get('pl')
        pvp  = fund.get('pvp')
        dy   = fund.get('dy')
        roe  = fund.get('roe')
        lpa  = fund.get('lpa')
        vpa  = fund.get('vpa')

        if dy and float(dy) > 1: dy = round(float(dy)/100, 4)

        gval = None
        if lpa and vpa and float(lpa) > 0 and float(vpa) > 0:
            gval = round(math.sqrt(22.5 * float(lpa) * float(vpa)), 2)

        pl_s  = setor.get('pl_medio', 12)
        pvp_s = setor.get('pvp_medio', 2)
        roe_s = setor.get('roe_min', 12)
        cdi_ref = cdi or 14.4

        indicadores = []

        # RSI com explicacao
        if rsi14:
            if rsi14 < 30:   sinal,exp='Alta',f'RSI {rsi14} — Sobrevenda ⚡ potencial reversao de alta'
            elif rsi14 < 45: sinal,exp='Alta',f'RSI {rsi14} — Zona favoravel, momentum positivo'
            elif rsi14 > 70: sinal,exp='Baixa',f'RSI {rsi14} — Sobrecompra ⚠ risco de correcao'
            else:            sinal,exp='Neutro',f'RSI {rsi14} — Zona neutra, sem sinal claro'
            indicadores.append({'nome':'RSI(14)','valor':rsi14,'sinal':sinal,'explicacao':exp})

        if ma20:
            s='Alta' if p>ma20 else 'Baixa'
            exp=f'Preco {"acima" if p>ma20 else "abaixo"} da MM20 ({ma20:.2f}) — tendencia CP {"positiva ✅" if p>ma20 else "negativa"}'
            indicadores.append({'nome':'MM20','valor':ma20,'sinal':s,'explicacao':exp})

        if ma50:
            s='Alta' if p>ma50 else 'Baixa'
            exp=f'Preco {"acima" if p>ma50 else "abaixo"} da MM50 ({ma50:.2f}) — tendencia MP {"positiva ✅" if p>ma50 else "negativa"}'
            indicadores.append({'nome':'MM50','valor':ma50,'sinal':s,'explicacao':exp})

        if ma200:
            s='Alta' if p>ma200 else 'Baixa'
            exp=f'Preco {"acima" if p>ma200 else "abaixo"} da MM200 ({ma200:.2f}) — tendencia LP {"positiva ✅" if p>ma200 else "negativa ⚠"}'
            indicadores.append({'nome':'MM200','valor':ma200,'sinal':s,'explicacao':exp})

        if pl:
            pl_f=float(pl)
            if pl_f<pl_s*0.7:   s,exp='Alta',f'P/L {pl_f:.1f}x muito barato vs setor ({pl_s}x) ✅✅'
            elif pl_f<pl_s:     s,exp='Alta',f'P/L {pl_f:.1f}x abaixo da media setorial ({pl_s}x) — desconto ✅'
            elif pl_f>pl_s*1.5: s,exp='Baixa',f'P/L {pl_f:.1f}x caro vs setor ({pl_s}x) — premio elevado ⚠'
            else:                s,exp='Neutro',f'P/L {pl_f:.1f}x proximo da media setorial ({pl_s}x)'
            indicadores.append({'nome':'P/L','valor':round(pl_f,1),'sinal':s,'explicacao':exp})

        if pvp:
            pvp_f=float(pvp)
            if pvp_f<1.0:    s,exp='Alta',f'P/VP {pvp_f:.2f}x abaixo do patrimonio — barata pelo criterio Graham ✅'
            elif pvp_f<pvp_s:s,exp='Alta',f'P/VP {pvp_f:.2f}x abaixo da media setorial ({pvp_s}x) — desconto ✅'
            else:             s,exp='Neutro',f'P/VP {pvp_f:.2f}x acima da media setorial ({pvp_s}x)'
            indicadores.append({'nome':'P/VP','valor':round(pvp_f,2),'sinal':s,'explicacao':exp})

        if dy:
            dy_pct=round(float(dy)*100,2)
            if dy_pct>cdi_ref:         s,exp='Alta',f'DY {dy_pct:.1f}% supera CDI ({cdi_ref:.1f}%) — dividendo bate renda fixa ⭐⭐'
            elif dy_pct>cdi_ref*0.7:   s,exp='Neutro',f'DY {dy_pct:.1f}% proximo do CDI ({cdi_ref:.1f}%) — retorno competitivo'
            else:                       s,exp='Baixa',f'DY {dy_pct:.1f}% abaixo do CDI ({cdi_ref:.1f}%) — dividendo pouco atrativo'
            indicadores.append({'nome':'Div.Yield','valor':f'{dy_pct:.1f}%','sinal':s,'explicacao':exp})

        if roe:
            roe_f=float(roe)*100 if float(roe)<1 else float(roe)
            if roe_f>roe_s:   s,exp='Alta',f'ROE {roe_f:.1f}% acima do minimo setorial ({roe_s}%) — empresa rentavel ✅'
            elif roe_f>10:    s,exp='Neutro',f'ROE {roe_f:.1f}% — retorno moderado, abaixo do benchmark'
            else:              s,exp='Baixa',f'ROE {roe_f:.1f}% — retorno fraco sobre patrimonio ⚠'
            indicadores.append({'nome':'ROE','valor':f'{roe_f:.1f}%','sinal':s,'explicacao':exp})

        if gval:
            upside_g=round((gval/p-1)*100,1)
            if upside_g>20:    s,exp='Alta',f'Graham R${gval:.2f} — upside {upside_g:.0f}% ✅✅ subavaliada'
            elif upside_g>0:   s,exp='Alta',f'Graham R${gval:.2f} — desconto {upside_g:.0f}%, margem de seguranca ✅'
            elif upside_g>-20: s,exp='Neutro',f'Graham R${gval:.2f} — cotacao {abs(upside_g):.0f}% acima do valor justo'
            else:               s,exp='Baixa',f'Graham R${gval:.2f} — sobrevalorizada {abs(upside_g):.0f}% acima ⚠'
            indicadores.append({'nome':'Graham','valor':gval,'sinal':s,'explicacao':exp})

        if lpa:
            lpa_f=float(lpa)
            indicadores.append({'nome':'LPA','valor':round(lpa_f,2),'sinal':'Alta' if lpa_f>0 else 'Baixa',
                'explicacao':f'Lucro por acao R${lpa_f:.2f} — {"empresa lucrativa ✅" if lpa_f>0 else "prejuizo por acao ⚠"}'})

        if vpa:
            indicadores.append({'nome':'VPA','valor':round(float(vpa),2),'sinal':'Neutro',
                'explicacao':f'Valor patrimonial por acao R${float(vpa):.2f} — base para P/VP e Graham'})

        # TECNICOS ADICIONAIS: MACD, Bollinger, OBV
        try:
            if len(closes) >= 35:
                def _ema(cls, n):
                    if len(cls)<n: return None
                    k=2/(n+1); e=sum(cls[:n])/n
                    for c in cls[n:]: e=c*k+e*(1-k)
                    return round(e,4)
                e12=_ema(closes,12); e26=_ema(closes,26)
                if e12 and e26:
                    macd_line=e12-e26
                    ms_list=[]
                    for ix in range(26,len(closes)):
                        a2=_ema(closes[:ix+1],12); b2=_ema(closes[:ix+1],26)
                        if a2 and b2: ms_list.append(a2-b2)
                    sig_line=_ema(ms_list,9) if len(ms_list)>=9 else None
                    hist=round(macd_line-sig_line,4) if sig_line else None
                    if hist is not None:
                        s_m='Alta' if hist>0 else 'Baixa'
                        exp_m=f'MACD hist {hist:.3f} — {"momentum alta ▲ compradores no controle ✅" if hist>0 else "momentum baixa ▼ vendedores no controle"}'
                        indicadores.append({'nome':'MACD Hist.','valor':round(hist,3),'sinal':s_m,'explicacao':exp_m})
        except: pass

        try:
            if len(closes)>=20:
                bb_r=closes[-20:]; bb_m=sum(bb_r)/20
                bb_std=math.sqrt(sum((x-bb_m)**2 for x in bb_r)/20)
                bb_up=round(bb_m+2*bb_std,2); bb_dn=round(bb_m-2*bb_std,2)
                pct_b=round((p-bb_dn)/(bb_up-bb_dn)*100,1) if bb_up!=bb_dn else 50
                if p<=bb_dn:    s_b,exp_b='Alta',f'Abaixo Banda Inf Bollinger ({bb_dn:.2f}) — sobrevenda tecnica ⚡'
                elif p>=bb_up:  s_b,exp_b='Baixa',f'Acima Banda Sup Bollinger ({bb_up:.2f}) — sobrecompra tecnica ⚠'
                else:            s_b,exp_b='Neutro',f'%B {pct_b:.0f}% dentro das bandas (inf:{bb_dn:.2f} sup:{bb_up:.2f})'
                indicadores.append({'nome':'Bollinger %B','valor':f'{pct_b:.0f}%','sinal':s_b,'explicacao':exp_b})
        except: pass

        # FUNDAMENTAIS EXTRAS hardcoded (atualizar trimestralmente)
        FUND_EXTRA = {
            'PETR4': {'ev_ebitda':3.2,'debt_ebitda':0.8,'margem':18.3},
            'VALE3': {'ev_ebitda':4.1,'debt_ebitda':0.6,'margem':22.1},
            'BBAS3': {'ev_ebitda':None,'debt_ebitda':None,'margem':28.5},
            'AXIA3': {'ev_ebitda':7.5,'debt_ebitda':3.2,'margem':15.0},
            'ROXO34':{'ev_ebitda':None,'debt_ebitda':None,'margem':18.0},
        }
        extra = FUND_EXTRA.get(symbol, {})

        ev_eb = extra.get('ev_ebitda')
        if ev_eb:
            if ev_eb<4:    s_e,exp_e='Alta',f'EV/EBITDA {ev_eb:.1f}x — muito barato vs geracao de caixa ✅✅'
            elif ev_eb<8:  s_e,exp_e='Alta',f'EV/EBITDA {ev_eb:.1f}x — valuation justo ✅'
            elif ev_eb<15: s_e,exp_e='Neutro',f'EV/EBITDA {ev_eb:.1f}x — premio sobre o setor'
            else:           s_e,exp_e='Baixa',f'EV/EBITDA {ev_eb:.1f}x — caro vs geracao de caixa ⚠'
            indicadores.append({'nome':'EV/EBITDA','valor':f'{ev_eb:.1f}x','sinal':s_e,'explicacao':exp_e})

        deb_eb = extra.get('debt_ebitda')
        if deb_eb is not None:
            if deb_eb<1.5:  s_d,exp_d='Alta',f'Div/EBITDA {deb_eb:.1f}x — endividamento saudavel, baixo risco ✅'
            elif deb_eb<3:  s_d,exp_d='Neutro',f'Div/EBITDA {deb_eb:.1f}x — endividamento moderado'
            else:            s_d,exp_d='Baixa',f'Div/EBITDA {deb_eb:.1f}x — endividamento elevado ⚠'
            indicadores.append({'nome':'Div/EBITDA','valor':f'{deb_eb:.1f}x','sinal':s_d,'explicacao':exp_d})

        margem_v = extra.get('margem')
        if margem_v:
            if margem_v>20:   s_mg,exp_mg='Alta',f'Margem liquida {margem_v:.1f}% — alta eficiencia, empresa muito rentavel ✅✅'
            elif margem_v>10: s_mg,exp_mg='Alta',f'Margem liquida {margem_v:.1f}% — boa eficiencia operacional ✅'
            elif margem_v>5:  s_mg,exp_mg='Neutro',f'Margem liquida {margem_v:.1f}% — eficiencia moderada'
            else:              s_mg,exp_mg='Baixa',f'Margem liquida {margem_v:.1f}% — margens comprimidas ⚠'
            indicadores.append({'nome':'Margem Liq.','valor':f'{margem_v:.1f}%','sinal':s_mg,'explicacao':exp_mg})

        altas  = sum(1 for i in indicadores if i['sinal']=='Alta')
        total  = len(indicadores) or 1
        score  = round((altas/total)*100)

        result = {
            'ticker': ticker,
            'preco_atual': round(p,2),
            'preco_anterior': round(float(preco_prev),2) if preco_prev else None,
            'setor': setor['nome'],
            'score_total': score,
            'indicadores': indicadores,
            'graham_value': gval,
            'upside_graham': round((gval/p-1)*100,1) if gval else None,
        }
        try:
            _IND_CACHE[ticker] = (result, _t.time())
        except: pass
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── BTC INDICATORS — v8.5 com cache ──────────────────
@app.route('/btc/indicators', methods=['GET'])
def get_btc_indicators():
    import time as _t
    if 'indicators' in _BTC_CACHE:
        cd, ct = _BTC_CACHE['indicators']
        if _t.time() - ct < 600:
            return jsonify(cd)
    try:
        r = None
        for host in ['query1','query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=1y',
                    headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                    timeout=10)
                if r.ok: break
            except: continue
        if not r or not r.ok:
            return jsonify({'error':'Yahoo BTC indisponivel'}), 500
        d = r.json()
        result_d = d['chart']['result'][0]
        q = result_d['indicators']['quote'][0]
        cl = [c for c in q.get('close',[]) if c is not None]
        vl = [v if v else 0 for v in q.get('volume',[])][-len(cl):]
        price = cl[-1]
        rsi_v = rsi(cl,14)
        mm20_v = mm(cl,20); mm50_v = mm(cl,50); mm200_v = mm(cl,200)
        ml_v,ms_v,mh_v = macd(cl)
        _,ot = obv(cl,vl)
        result = {
            'ticker':'BTC','price':round(price,0),
            'rsi_semanal':rsi_v,
            'mm20_semanal':round(mm20_v,0) if mm20_v else None,
            'mm50_semanal':round(mm50_v,0) if mm50_v else None,
            'mm200_semanal':round(mm200_v,0) if mm200_v else None,
            'macd':round(ml_v,0) if ml_v else None,
            'macd_signal':round(ms_v,0) if ms_v else None,
            'macd_histogram':round(mh_v,0) if mh_v else None,
            'obv_trend':ot,'data_points':len(cl)
        }
        _BTC_CACHE['indicators'] = (result, _t.time())
        return jsonify(result)
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── BTC CYCLE — v8.5 com cache e range menor ─────────
@app.route('/btc/cycle', methods=['GET'])
def get_btc_cycle():
    import time as _t, math as _m
    if 'cycle' in _BTC_CACHE:
        cd, ct = _BTC_CACHE['cycle']
        if _t.time() - ct < 900:
            return jsonify(cd)
    try:
        r = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1d&range=2y',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=12)
        if not r.ok: return jsonify({'error':f'Yahoo {r.status_code}'}),500
        cl = [c for c in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        price = cl[-1]
        dma111 = mm(cl,111); dma350 = mm(cl,350)
        dma350x2 = round(dma350*2,0) if dma350 else None
        pi_dist = round(dma350x2-dma111,0) if (dma111 and dma350x2) else None
        if dma111 and dma350x2:
            if dma111>=dma350x2: pi_sig="TOPO DETECTADO Pi Cycle cruzou!"
            elif pi_dist and pi_dist<10000: pi_sig="Proximidade de topo critica"
            elif pi_dist and pi_dist<30000: pi_sig="Monitorar distancia diminuindo"
            else: pi_sig=f"Seguro — distancia US$ {pi_dist:,.0f}" if pi_dist else "Calculando..."
        else: pi_sig="Dados insuficientes (precisa 350 dias)"
        days = (_t.time()-1231006505)/86400
        fair = 10**(5.84*_m.log10(days)-17.01)
        mults=[0.10,0.20,0.35,0.55,0.80,1.20,1.70,2.50,4.00]
        names=["Fire Sale","Buy","Accumulate","Still Cheap","HODL!","Bubble?","FOMO","Sell","Max Bubble"]
        colors=["green","green","green","accent","warn","warn","danger","danger","danger"]
        rb=names[-1]; rc=colors[-1]
        for i,mv in enumerate(mults):
            if price<fair*mv: rb=names[i]; rc=colors[i]; break
        rw = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=1y',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
        ma200w = None
        if rw.ok:
            clw=[c for c in rw.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
            ma200w = mm(clw,52)
        oc = get_btc_onchain()
        def ml_l(v): return "Capitulacao" if v<-1 else "Valor Justo" if v<1 else "Valorizado" if v<2 else "Aquecendo" if v<3 else "Sobrevalorizado" if v<5 else "Euforia TOPO"
        def nl_l(v): return "Capitulacao" if v<0 else "Esperanca/Medo" if v<0.25 else "Otimismo" if v<0.50 else "Crenca/Negacao" if v<0.75 else "Euforia TOPO"
        def pl_l(v): return "Estresse mineradores" if v<0.5 else "Pos-halving" if v<1.0 else "Normal" if v<2.0 else "Aquecendo" if v<3.4 else "Topo de ciclo"
        result = {
            'price':round(price,0),
            'pi_cycle':{'dma111':dma111,'dma350x2':dma350x2,'distance':pi_dist,'signal':pi_sig},
            'rainbow':{'band':rb,'color':rc},
            'ma200w':round(ma200w,0) if ma200w else None,
            'ma200w_pct':round((price-ma200w)/ma200w*100,1) if ma200w else None,
            'mvrv_zscore':{'value':oc['mvrv_zscore'],'label':ml_l(oc['mvrv_zscore'])},
            'nupl':{'value':oc['nupl'],'label':nl_l(oc['nupl'])},
            'puell':{'value':oc['puell_multiple'],'label':pl_l(oc['puell_multiple'])},
            'sopr':oc['sopr'],'realized_price':oc['realized_price'],
            'onchain_updated':oc['updated']
        }
        _BTC_CACHE['cycle'] = (result, _t.time())
        return jsonify(result)
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── FEAR & GREED ──────────────────────────────────────
@app.route('/feargreed', methods=['GET'])
def get_fear_greed():
    try:
        r=requests.get('https://api.alternative.me/fng/?limit=1',headers={'User-Agent':'Mozilla/5.0'},timeout=8)
        if r.ok:
            item=r.json().get('data',[{}])[0]
            return jsonify({'value':int(item.get('value',50)),'value_classification':item.get('value_classification','Neutro'),'timestamp':item.get('timestamp','')})
    except: pass
    return jsonify({'value':50,'value_classification':'Neutro','timestamp':''}),200

# ── CALENDAR — v8.5 multi-source ─────────────────────
@app.route('/calendar', methods=['GET'])
def get_calendar():
    """Lê do cache GitHub (raw.githubusercontent.com está na allowlist do Render)"""
    flag_map = {
        'USD':'🇺🇸','US':'🇺🇸','BRL':'🇧🇷','BR':'🇧🇷',
        'EUR':'🇪🇺','EU':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳',
        'JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺','DE':'🇩🇪',
        'NZD':'🇳🇿','CHF':'🇨🇭',
    }
    currencies_ok = set(flag_map.keys()) | {'USD','BRL','EUR','GBP','CNY','JPY','CAD','AUD','DE'}
    imp_map = {'Low':1,'Medium':2,'High':3,'Holiday':0}
    
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/cache/calendar.json',
            headers={'Cache-Control':'no-cache','User-Agent':'Trader-Desk/1.0'},
            timeout=10)
        if not r.ok or len(r.text) < 10:
            return jsonify([])
        raw = r.json()
        all_events = []
        for e in raw:
            cur = e.get('country', e.get('currency',''))
            if not cur or cur not in currencies_ok: continue
            imp = imp_map.get(e.get('impact',''), 0)
            if imp < 2: continue
            raw_date = e.get('date','')
            date_str = raw_date[:10] if raw_date else ''
            time_str = ''
            if 'T' in raw_date:
                try:
                    from datetime import datetime as _dt, timedelta, timezone
                    dt = _dt.fromisoformat(raw_date)
                    # Converter para BRT mas preservar data UTC para não perder eventos
                    dt_brt = dt.astimezone(timezone(timedelta(hours=-3)))
                    time_str = dt_brt.strftime('%H:%M')
                    # Usar data UTC para não descartar eventos da madrugada BRT
                    date_str = dt.strftime('%Y-%m-%d')
                except: time_str = raw_date[11:16]
            actual = e.get('actual') or None
            forecast = e.get('forecast') or None
            signal = None
            if actual and forecast:
                try:
                    a = float(str(actual).replace('%','').replace('K','000').replace('M','000000'))
                    f2 = float(str(forecast).replace('%','').replace('K','000').replace('M','000000'))
                    signal = 'beat' if a >= f2 else 'miss'
                except: pass
            all_events.append({
                'date': date_str, 'time': time_str,
                'country': cur, 'flag': flag_map.get(cur,'🌐'),
                'event': e.get('title',''),
                'importance': imp,
                'actual': actual, 'forecast': forecast,
                'previous': e.get('previous') or None,
                'signal': signal,
            })
        all_events.sort(key=lambda x: (x.get('date',''), x.get('time','')))
        return jsonify(all_events)
    except Exception as ex:
        return jsonify({'error': str(ex)}), 500


@app.route('/calendar/test', methods=['GET'])
def get_calendar_test():
    try:
        r = requests.get('https://nfs.faireconomy.media/ff_calendar_thisweek.json',
            headers={'User-Agent':'Mozilla/5.0 Chrome/124.0.0.0'}, timeout=10)
        return jsonify({'status':r.status_code,'size':len(r.text),'sample':r.json()[:2] if r.ok else r.text[:200]})
    except Exception as e:
        return jsonify({'error':str(e)})

# ── MACRO BCB ─────────────────────────────────────────
@app.route('/macro/brazil', methods=['GET'])
def get_macro_brazil():
    result = {}
    series = {'ipca_mensal':'433','selic':'432','pib_trimestral':'22099','cambio_usd':'1','igpm':'189'}
    for name, serie_id in series.items():
        try:
            r = requests.get(f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie_id}/dados/ultimos/3?formato=json',timeout=5)
            if r.ok:
                data = r.json()
                if data: result[name] = [{'data':d['data'],'valor':d['valor']} for d in data[-3:]]
        except: pass
    return jsonify(result)

# ── US STOCKS ─────────────────────────────────────────
_US_EXCHANGE = {
    'AAPL':'NASDAQ','MSFT':'NASDAQ','NVDA':'NASDAQ','AMZN':'NASDAQ',
    'GOOGL':'NASDAQ','GOOG':'NASDAQ','META':'NASDAQ','TSLA':'NASDAQ',
    'AVGO':'NASDAQ','COST':'NASDAQ','NFLX':'NASDAQ','QCOM':'NASDAQ',
    'AMD':'NASDAQ','ADBE':'NASDAQ','INTC':'NASDAQ','CSCO':'NASDAQ',
    'AMGN':'NASDAQ','HON':'NASDAQ','MELI':'NASDAQ','KLAC':'NASDAQ',
    'JPM':'NYSE','UNH':'NYSE','V':'NYSE','MA':'NYSE','XOM':'NYSE',
    'PG':'NYSE','JNJ':'NYSE','HD':'NYSE','BAC':'NYSE','GS':'NYSE',
    'SHW':'NYSE','CAT':'NYSE','AXP':'NYSE','MCD':'NYSE','TRV':'NYSE',
    'IBM':'NYSE','CRM':'NYSE','CVX':'NYSE','DIS':'NYSE','NKE':'NYSE',
    'BA':'NYSE','LLY':'NYSE','BRK-B':'NYSE','BRK.B':'NYSE',
    'WMT':'NYSE','KO':'NYSE','PEP':'NYSE','T':'NYSE','VZ':'NYSE',
}

@app.route('/us/quotes', methods=['GET'])
def get_us_quotes():
    tickers = request.args.get('tickers','').split(',')
    tickers = [t.strip().upper() for t in tickers if t.strip()][:25]
    if not tickers: return jsonify({})
    result = {}
    HL_STOCKS = {'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','NFLX','AMD','COIN','MSTR','PLTR','UBER','ABNB'}
    hl_needed = [t for t in tickers if t in HL_STOCKS]
    if hl_needed:
        try:
            rhl = requests.post('https://api.hyperliquid.xyz/info',json={'type':'allMids'},headers={'Content-Type':'application/json'},timeout=5)
            if rhl.ok:
                hl_data = rhl.json()
                for t in hl_needed:
                    tk = 'GOOGL' if t in ('GOOG','GOOGL') else t
                    if tk in hl_data:
                        price = round(float(hl_data[tk]),2)
                        result[t] = {'price':price,'prev':round(price*0.999,2),'src':'HL'}
        except: pass
    remaining = [t for t in tickers if t not in result]
    if remaining:
        exc_map = {**{k:v for k,v in _US_EXCHANGE.items()}}
        tv_tks = [f"{exc_map.get(t,'NASDAQ')}:{t}" for t in remaining]
        try:
            rtv = requests.post('https://scanner.tradingview.com/america/scan',
                json={'symbols':{'tickers':tv_tks},'columns':['close','change_abs']},
                headers={'User-Agent':'Mozilla/5.0'},timeout=8)
            if rtv.ok:
                for item in rtv.json().get('data',[]):
                    sym = item.get('s','').split(':')[-1]
                    d2 = item.get('d',[])
                    if d2 and d2[0]:
                        close = round(float(d2[0]),2)
                        chg = float(d2[1]) if len(d2)>1 and d2[1] else 0
                        result[sym] = {'price':close,'prev':round(close-chg,2),'src':'TV'}
        except: pass
    still_missing = [t for t in tickers if t not in result]
    for t in still_missing[:8]:
        q = yquote(t)
        if q: result[t] = q
    return jsonify(result)

# ── SERVE HTML v10.1 ──────────────────────────────────
import base64 as _b64
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjcg4oCUIERhcmsgUHJlbWl1bSAtLT4KPGh0bWwgbGFuZz0icHQtQlIiPgo8aGVhZD4KPG1ldGEgY2hhcnNldD0iVVRGLTgiPgo8bWV0YSBuYW1lPSJ2aWV3cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MS4wIj4KPHRpdGxlPlRyYWRlciBEZXNrPC90aXRsZT4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JbnRlcjp3Z2h0QDQwMDs1MDA7NjAwOzcwMCZmYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs2MDA7NzAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Cjpyb290ewogIC0tYmc6IzBmMGYxMzstLWJnMjojMTMxMzFhOy0tYmczOiMxYTFhMjQ7CiAgLS10ZXh0OiNlOGU4ZjA7LS1tdXRlZDojNTA1MDY4Oy0tYm9yZGVyOiMxZTFlMmU7CiAgLS1hY2NlbnQ6IzdjNmFmNzstLWFjY2VudDI6IzRmYzNmNzsKICAtLWdyZWVuOiMwMGU2NzY7LS1yZWQ6I2YwNjI5MjstLXdhcm46I2ZmYjc0ZDsKICAtLWdvbGQ6I2YwYTUwMAp9CmJvZHl7CiAgYmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7CiAgZm9udC1mYW1pbHk6J0ludGVyJyxzYW5zLXNlcmlmO2ZvbnQtc2l6ZToxNHB4OwogIGxpbmUtaGVpZ2h0OjEuNTtwYWRkaW5nOjIwcHggMjRweDsKICBtYXgtd2lkdGg6MTEwMHB4O21hcmdpbjowIGF1dG87bWluLWhlaWdodDoxMDB2aAp9CkBtZWRpYShtYXgtd2lkdGg6NjAwcHgpe2JvZHl7cGFkZGluZzoxMnB4fX0KCi8qIOKUgOKUgCBIRUFERVIg4pSA4pSAICovCi5oZHJ7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjIwcHg7cGFkZGluZy1ib3R0b206MTZweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpfQoubG9nb3tmb250LXNpemU6MThweDtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtsZXR0ZXItc3BhY2luZzouNXB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5sb2dvIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50Mil9Ci5oZHItcmlnaHR7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweH0KLmJhZGdle2JhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo0cHggMTJweDtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4fQouaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQoKLyog4pSA4pSAIFRBQlMg4pSA4pSAICovCi50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MjBweDtvdmVyZmxvdy14OmF1dG87cGFkZGluZy1ib3R0b206MnB4fQoudGFie3BhZGRpbmc6OHB4IDE4cHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6MTJweDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3doaXRlLXNwYWNlOm5vd3JhcDtmb250LWZhbWlseTppbmhlcml0O3RyYW5zaXRpb246YWxsIC4xNXN9Ci50YWI6aG92ZXJ7Y29sb3I6dmFyKC0tdGV4dCk7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci50YWIuYWN0aXZle2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtjb2xvcjojZmZmO2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpfQoudGFiLWNvbnRlbnR7ZGlzcGxheTpub25lfS50YWItY29udGVudC5hY3RpdmV7ZGlzcGxheTpibG9ja30KCi8qIOKUgOKUgCBTRUNUSU9OIOKUgOKUgCAqLwouc2Vje2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHggMCA3cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjE0cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4fQouc2VjIC5kb3R7d2lkdGg6NXB4O2hlaWdodDo1cHg7YmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrO2ZsZXgtc2hyaW5rOjB9Ci5zZWMgLmFjY3tjb2xvcjp2YXIoLS1hY2NlbnQpfQoKLyog4pSA4pSAIEdSSUQgQ0FSRFMg4pSA4pSAICovCi5ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDMsMWZyKTtnYXA6MTBweDttYXJnaW4tYm90dG9tOjE4cHh9CkBtZWRpYShtYXgtd2lkdGg6NTAwcHgpey5ncmlke2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoMiwxZnIpfX0KLmNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHggMTRweDtwb3NpdGlvbjpyZWxhdGl2ZTtvdmVyZmxvdzpoaWRkZW47dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1c30KLmNhcmQ6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci5jYXJkOjpiZWZvcmV7Y29udGVudDonJztwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MDtsZWZ0OjA7cmlnaHQ6MDtoZWlnaHQ6MnB4fQouY2FyZC5nOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tZ3JlZW4pLCMwMGJjZDQpfQouY2FyZC5iOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tYWNjZW50KSx2YXIoLS1hY2NlbnQyKSl9Ci5jYXJkLnc6OmJlZm9yZXtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS13YXJuKSwjZmY5ODAwKX0KLmNhcmQucjo6YmVmb3Jle2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLHZhcigtLXJlZCksI2U5MWU2Myl9Ci5jbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjRweDtmb250LXdlaWdodDo2MDB9Ci5jbntmb250LXNpemU6MTNweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLWJvdHRvbTo4cHg7Y29sb3I6cmdiYSgyNTUsMjU1LDI1NSwuOCl9Ci5jcHtmb250LXNpemU6MjBweDtmb250LXdlaWdodDo3MDA7Y29sb3I6I2ZmZn0KLmNwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToxNXB4fQouY2N7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NTAwfQouY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0uY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjN9fQoKLyog4pSA4pSAIEFDQ09SRElPTiBTRUdNRU5UT1Mg4pSA4pSAICovCi5zaHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweCAxNnB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7Zm9udC1zaXplOjEycHg7Zm9udC13ZWlnaHQ6NjAwO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDt0cmFuc2l0aW9uOmFsbCAuMTVzfQouc2g6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zYjJ7ZGlzcGxheTpub25lO3BhZGRpbmctdG9wOjZweH0KCi8qIOKUgOKUgCBQT1NJw4fDlUVTIOKUgOKUgCAqLwoucGN7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjE4cHg7bWFyZ2luLWJvdHRvbToxMnB4fQoucGx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnB0e2ZvbnQtc2l6ZToyMnB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO21hcmdpbi1ib3R0b206NHB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5wcHtmb250LXNpemU6MjhweDtmb250LXdlaWdodDo3MDB9LnBwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToyMHB4fQoucGMye2ZvbnQtc2l6ZToxMnB4O21hcmdpbi1ib3R0b206MTBweDtmb250LXdlaWdodDo1MDB9Ci5zYntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmctdG9wOjEwcHg7bWFyZ2luLXRvcDoxMHB4fQouc3J7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjVweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEzcHh9Ci5zbHtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NTAwfS5zdnt0ZXh0LWFsaWduOnJpZ2h0O21heC13aWR0aDo1OCU7Zm9udC13ZWlnaHQ6NjAwfQouc3Yub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5zdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zdi5pdG17Y29sb3I6dmFyKC0tcmVkKX0KLnNpZ3tib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxNHB4O21hcmdpbi10b3A6MTBweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLnNndHtmb250LXNpemU6MTBweDtmb250LXdlaWdodDo3MDA7bGV0dGVyLXNwYWNpbmc6MXB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjhweDtjb2xvcjp2YXIoLS1hY2NlbnQyKX0KLmlie2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMnB4O3RleHQtYWxpZ246Y2VudGVyfQouaWx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206NXB4O2ZvbnQtd2VpZ2h0OjYwMDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjVweH0KLml2e2ZvbnQtc2l6ZToyMHB4O2ZvbnQtd2VpZ2h0OjgwMH0KLml2Lm9re2NvbG9yOnZhcigtLWdyZWVuKX0uaXYud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaXYuZG93bntjb2xvcjp2YXIoLS1yZWQpfQoKLyog4pSA4pSAIElORElDQURPUkVTIOKUgOKUgCAqLwouc2Nie2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmciAxZnI7Z2FwOjhweDttYXJnaW4tYm90dG9tOjE0cHh9Ci5zY2N7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHggMTJweDt0ZXh0LWFsaWduOmNlbnRlcjtwb3NpdGlvbjpyZWxhdGl2ZTtvdmVyZmxvdzpoaWRkZW59Ci5zY2M6OmJlZm9yZXtjb250ZW50OicnO3Bvc2l0aW9uOmFic29sdXRlO3RvcDowO2xlZnQ6MDtyaWdodDowO2hlaWdodDoycHg7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tYWNjZW50KSx2YXIoLS1hY2NlbnQyKSl9Ci5zY217Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzoxcHg7bWFyZ2luLWJvdHRvbTo1cHg7Zm9udC13ZWlnaHQ6NjAwfQouc2Nue2ZvbnQtc2l6ZTozMnB4O2ZvbnQtd2VpZ2h0OjgwMDtsaW5lLWhlaWdodDoxfQouc2Nse2ZvbnQtc2l6ZToxMXB4O21hcmdpbi10b3A6NHB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnNjdntmb250LXNpemU6MThweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLXRvcDo0cHh9Ci5zY3N7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4fQouaXJ7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDoycHggc29saWQgdHJhbnNwYXJlbnQ7cGFkZGluZzoxMHB4IDE0cHg7bWFyZ2luLWJvdHRvbTo0cHg7dHJhbnNpdGlvbjpib3JkZXItbGVmdC1jb2xvciAuMXN9Ci5pcjpob3Zlcntib3JkZXItbGVmdC1jb2xvcjp2YXIoLS1hY2NlbnQpfQouaXJ0e2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpiYXNlbGluZTttYXJnaW4tYm90dG9tOjNweH0KLmlybntmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHg7Zm9udC13ZWlnaHQ6NjAwfQouaXJ2e2ZvbnQtc2l6ZToxNXB4O2ZvbnQtd2VpZ2h0OjcwMH0KLmlydi5va3tjb2xvcjp2YXIoLS1ncmVlbil9Lmlydi5kb3due2NvbG9yOnZhcigtLXJlZCl9Lmlydi53YXJue2NvbG9yOnZhcigtLXdhcm4pfQouaXJle2ZvbnQtc2l6ZToxMXB4O2NvbG9yOiMzYTNhNWE7bGluZS1oZWlnaHQ6MS40fQoKLyog4pSA4pSAIENBTEVORMOBUklPIOKUgOKUgCAqLwouY2h7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyNnB4IDUycHggMWZyIDMwcHggNjhweCA2MHB4O2dhcDo0cHg7cGFkZGluZzo1cHggMTJweDtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JhY2tncm91bmQ6dmFyKC0tYmcpO2ZvbnQtd2VpZ2h0OjYwMH0KLmNye2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjZweCA1MnB4IDFmciAzMHB4IDY4cHggNjBweDtnYXA6NHB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxMnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEzcHg7dHJhbnNpdGlvbjpiYWNrZ3JvdW5kIC4xc30KLmNyOmhvdmVye2JhY2tncm91bmQ6dmFyKC0tYmczKX0KLmNyOmxhc3QtY2hpbGR7Ym9yZGVyLWJvdHRvbTpub25lfQouY3R7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5jbjJ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwO2ZvbnQtd2VpZ2h0OjUwMH0KLmNhe3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5jZnt0ZXh0LWFsaWduOnJpZ2h0O2NvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweDtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlfQoKZm9vdGVye21hcmdpbi10b3A6MjRweDtwYWRkaW5nLXRvcDoxMnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTtmb250LXdlaWdodDo1MDB9Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+Cgo8ZGl2IGNsYXNzPSJoZHIiPgogIDxkaXYgY2xhc3M9ImxvZ28iPlRSQURFUiA8c3Bhbj5ERVNLPC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9Imhkci1yaWdodCI+CiAgICA8ZGl2IGNsYXNzPSJiYWRnZSI+4pePIEFPIFZJVk88L2Rpdj4KICAgIDxkaXYgY2xhc3M9Imhkci10aW1lIiBpZD0ibGFzdC11cGRhdGUiPuKAlDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9InRhYnMiPgogIDxkaXYgY2xhc3M9InRhYiBhY3RpdmUiIG9uY2xpY2s9InN3KCdjb3RhY29lcycsdGhpcykiPvCfk4ogQ290YcOnw7VlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3coJ2luZGljYWRvcmVzJyx0aGlzKSI+8J+TiCBJbmRpY2Fkb3JlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3coJ3Bvc2ljb2VzJyx0aGlzKSI+8J+SvCBQb3Npw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygnY2FsZW5kYXJpbycsdGhpcykiPvCfk4UgQ2FsZW5kw6FyaW88L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBDT1RBw4fDlUVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWNvdGFjb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQgYWN0aXZlIj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FVUEg4oCUIE1FUkNBRE9TPC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImNsIj5GdXR1cm88L2Rpdj48ZGl2IGNsYXNzPSJjbiI+UyZQIEVTMSo8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iZXNmLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0iZXNmLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iY24iPk5hc2RhcSBOUTwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJucWYtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJucWYtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImNsIj7DjW5kaWNlPC9kaXY+PGRpdiBjbGFzcz0iY24iPkRvdyBKb25lczwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJkamktcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJkamktYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHIiPjxkaXYgY2xhc3M9ImNsIj5Wb2xhdGlsaWRhZGU8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+VklYPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9InZpeC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9InZpeC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iY2wiPkTDs2xhciBJbmRleDwvZGl2PjxkaXYgY2xhc3M9ImNuIj5EWFk8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iZHh5LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0iZHh5LWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBnIj48ZGl2IGNsYXNzPSJjbCI+Q8OibWJpbzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5VU0QvQlJMPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9InVzZC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9InVzZC1jIj7igJQ8L2Rpdj48L2Rpdj4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+QjMg4oCUIFRPUCAxMDwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCBnIj48ZGl2IGNsYXNzPSJjbCI+w41uZGljZTwvZGl2PjxkaXYgY2xhc3M9ImNuIj5JQk9WPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9Imlib3YtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJpYm92LWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBnIj48ZGl2IGNsYXNzPSJjbCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iY24iPldJTjEhPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9Indpbi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9Indpbi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPlBFVFI0PC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9InBldHI0cS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9InBldHI0cS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPklUVUI0PC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9Iml0dWI0cS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9Iml0dWI0cS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPlZBTEUzPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9InZhbGUzcS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9InZhbGUzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPkJCREM0PC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImJiZGM0cS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9ImJiZGM0cS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPkFCRVYzPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImFiZXYzcS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9ImFiZXYzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPkJCQVMzPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImJiYXMzcS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9ImJiYXMzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPldFR0UzPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9IndlZ2UzcS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9IndlZ2UzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgdyI+PGRpdiBjbGFzcz0iY2wiPkJEUjwvZGl2PjxkaXYgY2xhc3M9ImNuIj5ST1hPMzQ8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0icm94bzM0cS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9InJveG8zNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImRvdCI+PC9zcGFuPkIzIHBvciBTZWdtZW50byA8c3BhbiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtd2VpZ2h0OjQwMCI+wrcgY2xpcXVlIHBhcmEgZXhwYW5kaXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdmaW4nKSI+PHNwYW4+8J+PpiBGaW5hbmNlaXJvPC9zcGFuPjxzcGFuIGlkPSJhci1maW4iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1maW4iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWZpbiI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdwZXQnKSI+PHNwYW4+8J+boiBQZXRyw7NsZW8gJmFtcDsgR8Ohczwvc3Bhbj48c3BhbiBpZD0iYXItcGV0Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItcGV0Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1wZXQiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnbWluJykiPjxzcGFuPuKbjyBNaW5lcmHDp8Ojbzwvc3Bhbj48c3BhbiBpZD0iYXItbWluIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItbWluIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1taW4iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnbWF0JykiPjxzcGFuPvCfjLIgUGFwZWwgJmFtcDsgQ2VsdWxvc2U8L3NwYW4+PHNwYW4gaWQ9ImFyLW1hdCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW1hdCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbWF0Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ3V0aScpIj48c3Bhbj7imqEgVXRpbGlkYWRlIFDDumJsaWNhPC9zcGFuPjxzcGFuIGlkPSJhci11dGkiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi11dGkiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXV0aSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdjYycpIj48c3Bhbj7wn5uNIENvbnN1bW8gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9ImFyLWNjIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItY2MiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWNjIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2NuJykiPjxzcGFuPvCfm5IgQ29uc3VtbyBOw6NvIEPDrWNsaWNvPC9zcGFuPjxzcGFuIGlkPSJhci1jbiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWNuIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1jbiI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdzYXUnKSI+PHNwYW4+8J+PpSBTYcO6ZGU8L3NwYW4+PHNwYW4gaWQ9ImFyLXNhdSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXNhdSI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9Imctc2F1Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2luZCcpIj48c3Bhbj7wn4+XIEJlbnMgSW5kdXN0cmlhaXM8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWluZCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctaW5kIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ3RpdCcpIj48c3Bhbj7wn5K7IFRJICZhbXA7IENvbXVuaWNhw6fDtWVzPC9zcGFuPjxzcGFuIGlkPSJhci10aXQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi10aXQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXRpdCI+PC9kaXY+PC9kaXY+CgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTZweCI+PHNwYW4gY2xhc3M9ImRvdCI+PC9zcGFuPkVVQSBwb3IgU2VnbWVudG88L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ203JykiPjxzcGFuPuKtkCA3IE1hZ27DrWZpY2FzPC9zcGFuPjxzcGFuIGlkPSJhci1tNyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW03Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1tNyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCducScpIj48c3Bhbj7wn5K7IE5hc2RhcSBUb3AgMTU8L3NwYW4+PHNwYW4gaWQ9ImFyLW5xIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItbnEiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW5xIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ3NwJykiPjxzcGFuPvCfk4ogUyZhbXA7UCA1MDAgVG9wIDIwPC9zcGFuPjxzcGFuIGlkPSJhci1zcCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXNwIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1zcCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdkaicpIj48c3Bhbj7wn4+bIERvdyBKb25lcyBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9ImFyLWRqIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItZGoiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWRqIj48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+Q29tbW9kaXRpZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgdyI+PGRpdiBjbGFzcz0iY2wiPlBldHLDs2xlbzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5XVEkvQ0w8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iY2wtcCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHciPjxkaXYgY2xhc3M9ImNsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImNuIj5HT0xEPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImdvbGQtcCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHciPjxkaXYgY2xhc3M9ImNsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImNuIj5TSUxWRVI8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0ic2lsdmVyLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3Ij48ZGl2IGNsYXNzPSJjbCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+Q09QUEVSPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImNvcHBlci1wIj7igJQ8L2Rpdj48L2Rpdj4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+Qml0Y29pbjwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+U3BvdDwvZGl2PjxkaXYgY2xhc3M9ImNuIj5CVEMvVVNEPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImJ0Yy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9ImJ0Yy1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iY2wiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iY24iPkJUQyBSU0k8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iYnRjLXJzaSI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImNsIj5GdW5kaW5nIDhoPC9kaXY+PGRpdiBjbGFzcz0iY24iPkJUQyBSYXRlPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImJ0Yy1mdW5kIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iY2wiPkZlYXIgJmFtcDsgR3JlZWQ8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+SW5kZXg8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iZmctdmFsIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9ImZnLWxibCI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGZvb3Rlcj48c3BhbiBpZD0iZm9vdGVyLXRpbWUiPuKAlDwvc3Bhbj48c3Bhbj5UcmFkZXIgRGVzayB2MTAuNzwvc3Bhbj48L2Zvb3Rlcj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBJTkRJQ0FET1JFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1pbmRpY2Fkb3JlcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5DaWNsbyBCaXRjb2luPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWN5Y2xlLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjE0cHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxNTBweDtnYXA6MTBweDttYXJnaW46MTRweCAwIj4KICAgIDxkaXYgaWQ9ImZnLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHgiPkNhcnJlZ2FuZG8gRmVhciAmYW1wOyBHcmVlZC4uLjwvZGl2PjwvZGl2PgogICAgPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHg7dGV4dC1hbGlnbjpjZW50ZXIiPgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo2cHg7Zm9udC13ZWlnaHQ6NjAwO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4Ij5CVEMvVVNEPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJidGMtaW5kLXAiPuKAlDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+QlRDIFNlbWFuYWw8L2Rpdj4KICA8ZGl2IGlkPSJidGMtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBQRVRSNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTJweDttYXJnaW4tbGVmdDo4cHgiIG9uY2xpY2s9InJsKCdwZXRyNCcpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0icGV0cjQtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBWQUxFMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTJweDttYXJnaW4tbGVmdDo4cHgiIG9uY2xpY2s9InJsKCd2YWxlMycpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0idmFsZTMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBCQkFTMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTJweDttYXJnaW4tbGVmdDo4cHgiIG9uY2xpY2s9InJsKCdiYmFzMycpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0iYmJhczMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBBWElBMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTJweDttYXJnaW4tbGVmdDo4cHgiIG9uY2xpY2s9InJsKCdheGlhMycpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0iYXhpYTMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBST1hPMzQgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEycHg7bWFyZ2luLWxlZnQ6OHB4IiBvbmNsaWNrPSJybCgncm94bzM0JykiPuKGuzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJyb3hvMzQtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CjwvZGl2PgoKPCEtLSDilZDilZAgUE9TScOHw5VFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1wb3NpY29lcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5PcGVyYcOnw7VlcyBBdGl2YXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+UGV0cm9icmFzIFBOIMK3IENhbGwgVmVuZGlkYSDCtyBQRVRSTDMxOSDCtyBWZW5jIDE3LzEyLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5QRVRSNDwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9InB0LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9InB0LWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TdHJpa2UgKFBFVFJMMzE5KTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgMzAsODU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByZcOnbyB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InB0LWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTcvMTIvMjAyNiDCtyA8c3BhbiBpZD0icHQtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj40Myw0JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj45LDQlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBNQyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayIgaWQ9InB0LW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhbGwgc2VyIGV4ZXJjaWRhPC9kaXY+CiAgICAgIDxkaXYgaWQ9InB0LW1jLWwiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEycHgiPkNhbGN1bGFuZG8gNS4wMDAgY2Vuw6FyaW9zLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9InB0LW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gZXhlcmNlcjwvZGl2PjxkaXYgY2xhc3M9Iml2IiBpZD0icHQtbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icHQtbWMtdiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4O2xpbmUtaGVpZ2h0OjEuNSIgaWQ9InB0LW1jLWkiPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIj4KICAgIDxkaXYgY2xhc3M9InBsIj5WYWxlIE9OIMK3IENhbGwgVmVuZGlkYSDCtyBWQUxFQjU3NCDCtyBWZW5jIDE4LzAyLzIwMjc8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5WQUxFMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9InZsLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9InZsLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TdHJpa2UgKFZBTEVCNTc0KTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNTcsNDA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByZcOnbyB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InZsLWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTgvMDIvMjAyNyDCtyA8c3BhbiBpZD0idmwtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj43MSwyJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4xNCwyJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gTUMgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siIGlkPSJ2bC1tYy1ydCI+Y2FsYy4uLjwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnIj4KICAgICAgPGRpdiBjbGFzcz0ic2d0Ij7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWxsIHNlciBleGVyY2lkYTwvZGl2PgogICAgICA8ZGl2IGlkPSJ2bC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJ2bC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIGV4ZXJjZXI8L2Rpdj48ZGl2IGNsYXNzPSJpdiIgaWQ9InZsLW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InZsLW1jLXYiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJ2bC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+QVhJQTMgKEEpIMK3IEJpZGlyZWNpb25hbCDCtyBWZW5jIDE0LzA5LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5BWElBMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9ImEzLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9ImEzLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA0Myw1MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S1VPICgrMjYsNiUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA2OCw3Njwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+R2FuaG8gcy8gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIGMvIGJhci4gYWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+KzQlIGZpeG88L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4xNC8wOS8yMDI2IMK3IDxzcGFuIGlkPSJhMy1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1rZG8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RGlzdC4gS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzLWt1byI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzLXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgQ2Vuw6FyaW9zIGJhcnJlaXJhPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzLW1jLWwiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEycHgiPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0iYTMtbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siIGlkPSJhMy1tYy1uYiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTMtbWMta3UiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEJhaXhhIEtETzwvZGl2PjxkaXYgY2xhc3M9Iml2IGRvd24iIGlkPSJhMy1tYy1rZCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTMtbWMtdm8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweCIgaWQ9ImEzLW1jLWkiPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIj4KICAgIDxkaXYgY2xhc3M9InBsIj5BWElBMyAoQikgwrcgQmlkaXJlY2lvbmFsIElPTiBJdGHDuiDCtyBWZW5jIDAyLzEwLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5BWElBMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9ImEzYi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJhM2ItYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPktETyAoLTIwJSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDQwLDUyPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LVU8gKCsyNCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA2Miw4MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+R2FuaG8gcy8gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIGMvIGJhci4gYWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+KzQlIGZpeG8gKDEyLDMzJSBhLmEuKTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjAyLzEwLzIwMjYgwrcgPHNwYW4gaWQ9ImEzYi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhM2Ita2RvIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtVTzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhM2Ita3VvIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgQ2Vuw6FyaW9zIGJhcnJlaXJhPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzYi1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzYi1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlNlbSBCYXJyZWlyYSDinIU8L2Rpdj48ZGl2IGNsYXNzPSJpdiBvayIgaWQ9ImEzYi1tYy1uYiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTNiLW1jLWt1Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpdiBkb3duIiBpZD0iYTNiLW1jLWtkIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJhM2ItbWMtdm8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweCIgaWQ9ImEzYi1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+Uk9YTzM0IMK3IEJEUiBOdWJhbmsgwrcgUHJlZml4YWRvIGMvIEJhcnJlaXJhIMK3IFZlbmMgMTYvMDcvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icHQiPlJPWE8zNDwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9InJ4LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9InJ4LWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5CYXJyZWlyYSBST1hPRzEwNTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgMTAsNTA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4xNi8wNy8yMDI2IMK3IDxzcGFuIGlkPSJyeC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9InJ4LWtkbyI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9InJ4LXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gc3VjZXNzbzwvZGl2PgogICAgICA8ZGl2IGlkPSJyeC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9InJ4LW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gU3VjZXNzbzwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIiBpZD0icngtbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkNhbGwgRXhlcmNpZGE8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icngtbWMtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPktETyBBdGluZ2lkbzwvZGl2PjxkaXYgY2xhc3M9Iml2IGRvd24iIGlkPSJyeC1tYy1rIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJyeC1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJyeC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjIwcHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjp2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLW11dGVkKSI+CiAgICA8ZGl2IGNsYXNzPSJwdCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTZweCI+QkJBUzM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TdHJpa2UgQkJBU0gyMTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPlIkIDIxLDY1IMK3IFJlZiBSJCAyMCw2Nzwvc3Bhbj48L2Rpdj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj7inIUgODAlIGRvIGFsdm8gZW0gNzAlIGRvIHByYXpvPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIiBzdHlsZT0ib3BhY2l0eTouNTtib3JkZXItY29sb3I6dmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdC1jb2xvcjp2YXIoLS1tdXRlZCkiPgogICAgPGRpdiBjbGFzcz0icHQiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjE2cHgiPkFYSUEzIFNob3J0IFN0cmFuZ2xlPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+PGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Q2FsbCBWLiBBWElBSTUwNTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPlIkIDUwLDUwPC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPuKchSBBw6fDtWVzIGxpYmVyYWRhczwvc3Bhbj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyIgc3R5bGU9Im9wYWNpdHk6LjU7Ym9yZGVyLWNvbG9yOnZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQtY29sb3I6dmFyKC0tbXV0ZWQpIj4KICAgIDxkaXYgY2xhc3M9InB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxNnB4Ij5ST1hPMzQgUHJlZml4YWRvIDcsMSU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5FbmNlcnJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4wNC8wNi8yMDI2PC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPuKchSB+NSwxNyUgKDcyJSBkbyBhbHZvKTwvc3Bhbj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBDQUxFTkTDgVJJTyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1jYWxlbmRhcmlvIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxNHB4Ij4KICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKTtmb250LXdlaWdodDo1MDAiPvCfh7rwn4e4IPCfh6fwn4e3IPCfh6rwn4e6IPCfh6zwn4enIPCfh6jwn4ezIPCfh6/wn4e1IPCfh6nwn4eqIMK3IEltcGFjdG8gTcOpZGlvKzwvZGl2PgogICAgPGJ1dHRvbiBvbmNsaWNrPSJsb2FkQ2FsKCkiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWFjY2VudCk7Ym9yZGVyOm5vbmU7Y29sb3I6I2ZmZjtwYWRkaW5nOjhweCAxOHB4O2ZvbnQtc2l6ZToxMnB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NzAwO2xldHRlci1zcGFjaW5nOi41cHgiPuKGuyBBdHVhbGl6YXI8L2J1dHRvbj4KICA8L2Rpdj4KICA8ZGl2IGlkPSJjYWwtc3QiIHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo4cHgiPjwvZGl2PgogIDxkaXYgaWQ9ImNhbC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoyNHB4O3RleHQtYWxpZ246Y2VudGVyIj5DbGlxdWUgZW0gQXR1YWxpemFyPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgQj0naHR0cHM6Ly90cmFkZXItZGVzay5vbnJlbmRlci5jb20nOwpjb25zdCBTRUc9ewogIGZpbjpbJ0lUVUI0JywnQkJEQzQnLCdCQkFTMycsJ1NBTkIxMScsJ0IzU0EzJywnQlBBQzExJywnSVRTQTQnLCdCUlNSNicsJ0FCQ0I0JywnQk1HQjQnXSwKICBwZXQ6WydQRVRSNCcsJ1BFVFIzJywnUFJJTzMnLCdCUkFWMycsJ1ZCQlIzJywnQ1NBTjMnLCdSRUNWMycsJ1VHUEEzJywnU0VRTDMnLCdHR0JSNCddLAogIG1pbjpbJ1ZBTEUzJywnR0dCUjQnLCdDU05BMycsJ1VTSU01JywnQlJBUDQnLCdGRVNBNCcsJ0NNSU4zJywnQ0JBVjMnLCdHT0FVNCcsJ1BHTU4zJ10sCiAgbWF0OlsnU1VaQjMnLCdLTEJOMTEnLCdEWENPMycsJ1VOSVA2JywnUkFOSTMnLCdPUlZSMycsJ1NNVE8zJywnRlJBUzMnLCdMUFNCMycsJ0NTVUQzJ10sCiAgdXRpOlsnQVhJQTMnLCdFUVRMMycsJ0NQRkUzJywnU0JTUDMnLCdDTUlHNCcsJ0VOR0kxMScsJ1RBRUUxMScsJ0FVUkUzJywnRUdJRTMnLCdDUExFMyddLAogIGNjOiBbJ1JFTlQzJywnTFJFTjMnLCdNR0xVMycsJ0NZUkUzJywnTVJWRTMnLCdBWlpBMycsJ1ZJVkEzJywnU0JGRzMnLCdZRFVRMycsJ01PVkkzJ10sCiAgY246IFsnQUJFVjMnLCdKQlNTMycsJ0JSRlMzJywnTkFUVTMnLCdNRElBMycsJ0JFRUYzJywnU0xDRTMnLCdNVFJFMycsJ0NBTUwzJywnUENBUjMnXSwKICBzYXU6WydSRE9SMycsJ0hBUFYzJywnRkxSWTMnLCdEQVNBMycsJ1FVQUwzJywnT05DTzMnLCdQTlZMMycsJ09EUFYzJywnTUFURDMnLCdBQUxSMyddLAogIGluZDpbJ1dFR0UzJywnRU1CUjMnLCdSQUlMMycsJ1RHTUEzJywnUk9NSTMnLCdWTElEMycsJ1RVUFkzJywnSVJCUjMnLCdQT01PNCcsJ0xBVlYzJ10sCiAgdGl0OlsnVklWVDMnLCdUSU1TMycsJ1RPVFZTMycsJ1BPU0kzJywnTUxBUzMnLCdBTklNMycsJ0lOVEIzJywnTFdTQTMnLCdDQVNIMycsJ09JQlIzJ10sCn07CmNvbnN0IFVTU0VHPXsKICBtNzpbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdHT09HTCcsJ01FVEEnLCdUU0xBJ10sCiAgbnE6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdDT1NUJywnTkZMWCcsJ1FDT00nLCdBTUQnLCdBREJFJywnSU5UQycsJ0NTQ08nXSwKICBzcDpbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdNRVRBJywnR09PR0wnLCdUU0xBJywnQVZHTycsJ0JSSy5CJywnSlBNJywnTExZJywnVicsJ1VOSCcsJ1hPTScsJ01BJywnTkZMWCcsJ1BHJywnSk5KJywnSEQnLCdCQUMnXSwKICBkajpbJ1VOSCcsJ0dTJywnSEQnLCdTSFcnLCdDQVQnLCdBWFAnLCdNQ0QnLCdBTUdOJywnVicsJ1RSVicsJ0lCTScsJ0pQTScsJ0hPTicsJ0NSTScsJ0NWWCcsJ0FBUEwnLCdNU0ZUJywnRElTJywnTktFJywnQkEnXQp9Owpjb25zdCBmUj12PT52IT1udWxsPydSJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmVT12PT52IT1udWxsPydVUyQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlA9dj0+diE9bnVsbD9OdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KTon4oCUJzsKZnVuY3Rpb24gRShpZCx0KXtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47ZS50ZXh0Q29udGVudD10O2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KZnVuY3Rpb24gQ2goaWQsbixwLHRwKXsKICBjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47CiAgY29uc3QgZD1uLXAscGM9KGQvTWF0aC5hYnMocHx8MSkqMTAwKS50b0ZpeGVkKDIpLHNnPWQ+PTA/JysnOicnOwogIGlmKHRwPT09J3InKWUudGV4dENvbnRlbnQ9c2crJ1IkICcrTWF0aC5hYnMoZCkudG9GaXhlZCgyKSsnICgnK3NnK3BjKyclKSc7CiAgZWxzZSBpZih0cD09PSd1JyllLnRleHRDb250ZW50PXNnK2QudG9GaXhlZCgyKSsnICgnK3NnK3BjKyclKSc7CiAgZWxzZSBlLnRleHRDb250ZW50PXNnK01hdGguYWJzKGQpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJyAoJytzZytwYysnJSknOwogIGUuY2xhc3NOYW1lPSdjYyAnKyhkPjA/J2NoZy11cCc6ZDwwPydjaGctZG4nOidjaGctZmwnKTsKfQpmdW5jdGlvbiBzdyh0LGVsKXsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiJykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiLWNvbnRlbnQnKS5mb3JFYWNoKHg9PnguY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJykpOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0YWItJyt0KS5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZihlbCllbC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZih0PT09J2luZGljYWRvcmVzJyYmIXdpbmRvdy5fSUwpe3dpbmRvdy5fSUw9dHJ1ZTtsb2FkSW5kKCk7fQogIGlmKHQ9PT0nY2FsZW5kYXJpbycpbG9hZENhbCgpOwp9CmZ1bmN0aW9uIHRnKGlkKXsKICBjb25zdCBiPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYi0nK2lkKSxhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci0nK2lkKTsKICBpZighYilyZXR1cm47Y29uc3Qgb3A9Yi5zdHlsZS5kaXNwbGF5IT09J2Jsb2NrJzsKICBiLnN0eWxlLmRpc3BsYXk9b3A/J2Jsb2NrJzonbm9uZSc7CiAgaWYoYSlhLnRleHRDb250ZW50PW9wPyfilrInOifilrwnOwogIGlmKG9wJiYhYi5kYXRhc2V0Lmwpe2IuZGF0YXNldC5sPScxJztsb2FkU2VnKGlkKTt9Cn0KCmFzeW5jIGZ1bmN0aW9uIGxvYWRTZWcoaWQpewogIGNvbnN0IGc9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ctJytpZCk7aWYoIWcpcmV0dXJuOwogIGNvbnN0IHBmeD1pZCsnXyc7CiAgaWYoVVNTRUdbaWRdKXsKICAgIGNvbnN0IHRrcz1VU1NFR1tpZF07CiAgICBnLmlubmVySFRNTD10a3MubWFwKHQ9Pntjb25zdCB0aWQ9dC5yZXBsYWNlKC9bXmEtekEtWjAtOV0vZywnXycpO3JldHVybiAnPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+VVM8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+Jyt0Kyc8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nO30pLmpvaW4oJycpOwogICAgdHJ5ewogICAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy91cy9xdW90ZXM/dGlja2Vycz0nK3Rrcy5qb2luKCcsJykpOwogICAgICBpZighci5vaylyZXR1cm47CiAgICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICAgIE9iamVjdC5lbnRyaWVzKGQpLmZvckVhY2goKFt0LHZdKT0+ewogICAgICAgIGNvbnN0IHRpZD10LnJlcGxhY2UoL1teYS16QS1aMC05XS9nLCdfJyk7CiAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICBpZihlcCYmdi5wcmljZSl7ZXAudGV4dENvbnRlbnQ9JyQnK051bWJlcih2LnByaWNlKS50b0ZpeGVkKDIpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CiAgICAgICAgaWYodi5wcmljZSYmdi5wcmV2KUNoKHBmeCt0aWQrJ19jJyx2LnByaWNlLHYucHJldiwndScpOwogICAgICB9KTsKICAgIH1jYXRjaChlKXt9CiAgICByZXR1cm47CiAgfQogIGNvbnN0IHRrcz1TRUdbaWRdO2lmKCF0a3MpcmV0dXJuOwogIGcuaW5uZXJIVE1MPXRrcy5tYXAodD0+e2NvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7cmV0dXJuICc8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSInK3BmeCt0aWQrJ19wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9IicrcGZ4K3RpZCsnX2MiPuKAlDwvZGl2PjwvZGl2Pic7fSkuam9pbignJyk7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOnRrcy5tYXAodD0+J0JNRkJPVkVTUEE6Jyt0KX0sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IG5ldyBFcnJvcignVFYgZmFpbCcpOwogICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IGxvYWRlZD1uZXcgU2V0KCk7CiAgICAoZC5kYXRhfHxbXSkuZm9yRWFjaCh4PT57CiAgICAgIGNvbnN0IHQ9eC5zLnJlcGxhY2UoJ0JNRkJPVkVTUEE6JywnJykudG9Mb3dlckNhc2UoKTsKICAgICAgY29uc3RbYyxjYV09eC5kfHxbXTsKICAgICAgaWYoYyE9bnVsbCl7CiAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3QrJ19wJyk7CiAgICAgICAgaWYoZXApe2VwLnRleHRDb250ZW50PWZSKGMpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTtsb2FkZWQuYWRkKHQpO30KICAgICAgICBDaChwZngrdCsnX2MnLGMsYy0oY2F8fDApLCdyJyk7CiAgICAgIH0KICAgIH0pOwogICAgLy8gRmFsbGJhY2sgdmlhIGJyYXBpIHBhcmEgdGlja2VycyBxdWUgVFYgbsOjbyByZXRvcm5vdQogICAgY29uc3QgbWlzc2luZz10a3MuZmlsdGVyKHQ9PiFsb2FkZWQuaGFzKHQudG9Mb3dlckNhc2UoKSkpOwogICAgaWYobWlzc2luZy5sZW5ndGg+MCl7CiAgICAgIHRyeXsKICAgICAgICBjb25zdCByYj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICAgICAgYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2VyczptaXNzaW5nLm1hcCh0PT4nQk1GQk9WRVNQQTonK3QpfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pOwogICAgICAgIC8vIFNlZ3VuZGEgdGVudGF0aXZhIGltZWRpYXRhCiAgICAgIH1jYXRjaChlMil7fQogICAgICAvLyBGYWxsYmFjayBpbmRpdmlkdWFsIHZpYSAvaW5kaWNhdG9ycwogICAgICBmb3IoY29uc3QgdCBvZiBtaXNzaW5nLnNsaWNlKDAsNSkpewogICAgICAgIHRyeXsKICAgICAgICAgIGNvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdCsnLlNBJyk7CiAgICAgICAgICBpZighcjIub2spY29udGludWU7CiAgICAgICAgICBjb25zdCBkMj1hd2FpdCByMi5qc29uKCk7CiAgICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICAgIGNvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7CiAgICAgICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19wJyk7CiAgICAgICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mUihkMi5wcmVjb19hdHVhbCk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICAgICAgaWYoZDIucHJlY29fYW50ZXJpb3IpQ2gocGZ4K3RpZCsnX2MnLGQyLnByZWNvX2F0dWFsLGQyLnByZWNvX2FudGVyaW9yLCdyJyk7CiAgICAgICAgICB9CiAgICAgICAgfWNhdGNoKGUyKXt9CiAgICAgIH0KICAgIH0KICB9Y2F0Y2goZSl7CiAgICAvLyBUViBmYWxob3UgY29tcGxldGFtZW50ZSDigJQgZmFsbGJhY2sgcGFyYSB0b2RvcyB2aWEgL2luZGljYXRvcnMKICAgIGZvcihjb25zdCB0IG9mIHRrcy5zbGljZSgwLDYpKXsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdCsnLlNBJyk7CiAgICAgICAgaWYoIXIyLm9rKWNvbnRpbnVlOwogICAgICAgIGNvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICBjb25zdCB0aWQ9dC50b0xvd2VyQ2FzZSgpOwogICAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mUihkMi5wcmVjb19hdHVhbCk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICB9CiAgICAgIH1jYXRjaChlMil7fQogICAgfQogIH0KfQoKYXN5bmMgZnVuY3Rpb24gZkhMKCl7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pOwogICAgaWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBjb25zdCBicD1wYXJzZUZsb2F0KGQuQlRDfHwwKTsKICAgIGlmKGJwPjApe0UoJ2J0Yy1wJyxmVShicCkpO0NoKCdidGMtYycsYnAsYnAqMC45OSwndScpO30KICAgIHRyeXsKICAgICAgY29uc3QgcjI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnLGRleDoneHl6J30pfSk7CiAgICAgIGlmKHIyLm9rKXtjb25zdCBkMj1hd2FpdCByMi5qc29uKCk7CiAgICAgICAgaWYoZDJbJ3h5ejpDTCddKUUoJ2NsLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q0wnXSkudG9GaXhlZCgyKSk7CiAgICAgICAgaWYoZDJbJ3h5ejpHT0xEJ10pRSgnZ29sZC1wJywnJCcrTnVtYmVyKGQyWyd4eXo6R09MRCddKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTsKICAgICAgICBpZihkMlsneHl6OlNJTFZFUiddKUUoJ3NpbHZlci1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OlNJTFZFUiddKS50b0ZpeGVkKDIpKTsKICAgICAgICBpZihkMlsneHl6OkNPUFBFUiddKUUoJ2NvcHBlci1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OkNPUFBFUiddKS50b0ZpeGVkKDMpKTt9CiAgICB9Y2F0Y2goZSl7fQogIH1jYXRjaChlKXt9Cn0KYXN5bmMgZnVuY3Rpb24gZlRWKCl7CiAgY29uc3Qgb3V0PXt9OwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL3R2L2JyYXppbCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2VyczpbJ0JNRkJPVkVTUEE6UEVUUjQnLCdCTUZCT1ZFU1BBOklUVUI0JywnQk1GQk9WRVNQQTpWQUxFMycsJ0JNRkJPVkVTUEE6QkJEQzQnLCdCTUZCT1ZFU1BBOkFCRVYzJywnQk1GQk9WRVNQQTpCQkFTMycsJ0JNRkJPVkVTUEE6V0VHRTMnLCdCTUZCT1ZFU1BBOklCT1YnXX0sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTsKICAgIGlmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7KGQuZGF0YXx8W10pLmZvckVhY2goeD0+e2NvbnN0W2MsY2FdPXguZHx8W107aWYoYyE9bnVsbClvdXRbeC5zXT17cDpjLHY6Yy0oY2F8fDApfTt9KTt9CiAgfWNhdGNoKGUpe30KICB0cnl7Y29uc3QgcnI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYocnIub2spe2NvbnN0IGRkPWF3YWl0IHJyLmpzb24oKTtpZihkZC5wcmVjb19hdHVhbCl7RSgncm94bzM0cS1wJyxmUihkZC5wcmVjb19hdHVhbCkpO0NoKCdyb3hvMzRxLWMnLGRkLnByZWNvX2F0dWFsLChkZC5wcmVjb19hbnRlcmlvcnx8ZGQucHJlY29fYXR1YWwqMC45OSksJ3InKTt9fX1jYXRjaChlKXt9CiAgcmV0dXJuIG91dDsKfQphc3luYyBmdW5jdGlvbiBmRnV0KCl7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2Z1dHVyZXMnKTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZGdW5kKCl7CiAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vZmFwaS5iaW5hbmNlLmNvbS9mYXBpL3YxL3ByZW1pdW1JbmRleD9zeW1ib2w9QlRDVVNEVCcpO2lmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7RSgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlfHwwKSoxMDApLnRvRml4ZWQoNCkrJyUnKTtyZXR1cm47fX1jYXRjaChlKXt9CiAgdHJ5e2NvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9iaW5hbmNlL2Z1bmRpbmcnKTtpZighcjIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgcjIuanNvbigpO2lmKGQubGFzdEZ1bmRpbmdSYXRlKUUoJ2J0Yy1mdW5kJywocGFyc2VGbG9hdChkLmxhc3RGdW5kaW5nUmF0ZSkqMTAwKS50b0ZpeGVkKDQpKyclJyk7fWNhdGNoKGUpe30KfQpmdW5jdGlvbiBkb01hY3JvKHR2LGZ0KXsKICBjb25zdCBpYj10dlsnQk1GQk9WRVNQQTpJQk9WJ107aWYoaWIpe0UoJ2lib3YtcCcsZlAoaWIucCkpO0NoKCdpYm92LWMnLGliLnAsaWIudiwncCcpO30KICBbWydQRVRSNCcsJ3BldHI0cSddLFsnSVRVQjQnLCdpdHViNHEnXSxbJ1ZBTEUzJywndmFsZTNxJ10sWydCQkRDNCcsJ2JiZGM0cSddLFsnQUJFVjMnLCdhYmV2M3EnXSxbJ0JCQVMzJywnYmJhczNxJ10sWydXRUdFMycsJ3dlZ2UzcSddXS5mb3JFYWNoKChbdCxpZF0pPT57CiAgICBjb25zdCBkPXR2WydCTUZCT1ZFU1BBOicrdF07aWYoZCl7RShpZCsnLXAnLGZSKGQucCkpO0NoKGlkKyctYycsZC5wLGQudiwncicpO30KICB9KTsKICBpZihmdCl7CiAgICBjb25zdCBhZj0oaWQsdik9Pntjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZihlKXtlLnRleHRDb250ZW50PXY7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fX07CiAgICBpZihmdC5kamk/LnByaWNlKXthZignZGppLXAnLGZQKGZ0LmRqaS5wcmljZSkpO0NoKCdkamktYycsZnQuZGppLnByaWNlLGZ0LmRqaS5wcmV2LCdwJyk7fQogICAgaWYoZnQuZXNmPy5wcmljZSl7YWYoJ2VzZi1wJyxmUChmdC5lc2YucHJpY2UpKTtDaCgnZXNmLWMnLGZ0LmVzZi5wcmljZSxmdC5lc2YucHJldiwncCcpO30KICAgIGlmKGZ0Lm5xZj8ucHJpY2Upe2FmKCducWYtcCcsZlAoZnQubnFmLnByaWNlKSk7Q2goJ25xZi1jJyxmdC5ucWYucHJpY2UsZnQubnFmLnByZXYsJ3AnKTt9CiAgICBpZihmdC53aW4/LnByaWNlKXthZignd2luLXAnLGZQKGZ0Lndpbi5wcmljZSkpO0NoKCd3aW4tYycsZnQud2luLnByaWNlLGZ0Lndpbi5wcmV2LCdwJyk7fQogICAgaWYoZnQudml4Py5wcmljZSl7YWYoJ3ZpeC1wJyxOdW1iZXIoZnQudml4LnByaWNlKS50b0ZpeGVkKDIpKTtDaCgndml4LWMnLGZ0LnZpeC5wcmljZSxmdC52aXgucHJldiwndScpO30KICAgIGlmKGZ0LmR4eT8ucHJpY2Upe2FmKCdkeHktcCcsTnVtYmVyKGZ0LmR4eS5wcmljZSkudG9GaXhlZCgyKSk7Q2goJ2R4eS1jJyxmdC5keHkucHJpY2UsZnQuZHh5LnByZXYsJ3UnKTt9CiAgICBpZihmdC51c2Q/LnByaWNlKXthZigndXNkLXAnLGZSKGZ0LnVzZC5wcmljZSkpO0NoKCd1c2QtYycsZnQudXNkLnByaWNlLGZ0LnVzZC5wcmV2fHxmdC51c2QucHJpY2UsJ3InKTt9CiAgfQp9CmZ1bmN0aW9uIGRvUG9zKHR2KXsKICBjb25zdCBwdD10dlsnQk1GQk9WRVNQQTpQRVRSNCddO2NvbnN0IHBwPXB0Py5wfHw0MCxwdj1wdD8udnx8NDA7CiAgRSgncHQtcCcsZlIocHApKTtDaCgncHQtYycscHAscHYsJ3InKTsKICBjb25zdCBwZD1wcC0zMC44NTtFKCdwdC1pdG0nLChwZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHBkKS50b0ZpeGVkKDIpKycgJysocGQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCB2bD10dlsnQk1GQk9WRVNQQTpWQUxFMyddO2NvbnN0IHZwPXZsPy5wfHw3OCx2dj12bD8udnx8Nzg7CiAgRSgndmwtcCcsZlIodnApKTtDaCgndmwtYycsdnAsdnYsJ3InKTsKICBjb25zdCB2ZD12cC01Ny40MDtFKCd2bC1pdG0nLCh2ZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHZkKS50b0ZpeGVkKDIpKycgJysodmQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCBjZD0oZHMsZWlkKT0+e2NvbnN0IHY9bmV3IERhdGUoZHMpLGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKSxlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVpZCk7aWYoZSllLnRleHRDb250ZW50PWQ7fTsKICBjZCgnMjAyNi0xMi0xNycsJ3B0LWRpYXMnKTtjZCgnMjAyNy0wMi0xOCcsJ3ZsLWRpYXMnKTtjZCgnMjAyNi0wOS0xNCcsJ2EzLWRpYXMnKTtjZCgnMjAyNi0xMC0wMicsJ2EzYi1kaWFzJyk7Y2QoJzIwMjYtMDctMTYnLCdyeC1kaWFzJyk7CiAgc2V0VGltZW91dChhc3luYygpPT57CiAgICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy9BWElBMy5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjsKICAgICAgY29uc3QgcD1kLnByZWNvX2F0dWFsO0UoJ2EzLXAnLGZSKHApKTtFKCdhM2ItcCcsZlIocCkpOwogICAgICBjb25zdCBrQT00My41MSxrdUE9NjguNzYsa0I9NDAuNTIsa3VCPTYyLjgxOwogICAgICBjb25zdCBkQT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTMta2RvJyk7aWYoZEEpZEEudGV4dENvbnRlbnQ9KChwLWtBKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1QT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTMta3VvJyk7aWYodUEpdUEudGV4dENvbnRlbnQ9KChrdUEtcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7CiAgICAgIGNvbnN0IHNBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhMy1zdCcpO2lmKHNBKXtzQS50ZXh0Q29udGVudD1wPD1rQT8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1QT8n4pqgIEtVTyBBVElOR0lETyc6J+KchSBObyByYW5nZSc7c0EuY2xhc3NOYW1lPSdzdiAnKyhwPD1rQXx8cD49a3VBPyd3YXJuJzonb2snKTt9CiAgICAgIGNvbnN0IGRCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhM2Ita2RvJyk7aWYoZEIpZEIudGV4dENvbnRlbnQ9KChwLWtCKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1Qj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTNiLWt1bycpO2lmKHVCKXVCLnRleHRDb250ZW50PSgoa3VCLXApL3AqMTAwKS50b0ZpeGVkKDEpKyclIHBhcmEgbyBLVU8nOwogICAgICBjb25zdCBzQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTNiLXN0Jyk7aWYoc0Ipe3NCLnRleHRDb250ZW50PXA8PWtCPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VCPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQi5jbGFzc05hbWU9J3N2ICcrKHA8PWtCfHxwPj1rdUI/J3dhcm4nOidvaycpO30KICAgIH1jYXRjaChlKXt9CiAgfSwyMDAwKTsKICBzZXRUaW1lb3V0KGFzeW5jKCk9PnsKICAgIHRyeXtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjsKICAgICAgY29uc3QgcD1kLnByZWNvX2F0dWFsO0UoJ3J4LXAnLGZSKHApKTsKICAgICAgY29uc3QgZGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LWtkbycpO2lmKGRlKWRlLnRleHRDb250ZW50PSgocC0xMC41MCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgYWNpbWEgZGEgYmFycmVpcmEnOwogICAgICBjb25zdCBzZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtc3QnKTtpZihzZSl7c2UudGV4dENvbnRlbnQ9cDw9MTAuNTA/J/CflLQgQkFSUkVJUkEgQVRJTkdJREEnOifinIUgQWNpbWEgZGEgYmFycmVpcmEnO3NlLmNsYXNzTmFtZT0nc3YgJysocDw9MTAuNTA/J2l0bSc6J29rJyk7fQogICAgfWNhdGNoKGUpe30KICB9LDMwMDApOwp9CmFzeW5jIGZ1bmN0aW9uIE1DKHRrLHNrLGRpYXMsbElkLHJJZCxzSWQsdklkLGlJZCxydElkKXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeSh7dGlja2VyOnRrLGtfY2FsbDpzayxrX3B1dDpzayx0X2RheXM6ZGlhcyxuOjUwMDB9KX0pOwogICAgaWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQobElkKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChySWQpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGNvbnN0IHByb2I9TnVtYmVyKGQucHJvYl9jYWxsX2V4ZXJjaWRhfHwwKTsKICAgIGNvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChzSWQpO3NFbC50ZXh0Q29udGVudD1wcm9iLnRvRml4ZWQoMSkrJyUnOwogICAgc0VsLmNsYXNzTmFtZT0naXYgJysocHJvYjwxNT8nb2snOnByb2I8MzA/J3dhcm4nOidkb3duJyk7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCh2SWQpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaUlkKS50ZXh0Q29udGVudD0nVm9sLmhpc3QuICcrZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSDCtyAnKyhwcm9iPDE1PyfinIUgUmlzY28gYmFpeG8gZGUgZXhlcmPDrWNpbyc6J+KaoCBNb25pdG9yYXIgcG9zacOnw6NvJyk7CiAgICBpZihydElkKUUocnRJZCxwcm9iLnRvRml4ZWQoMSkrJyUnKTsKICB9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQobElkKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwndGltZW91dCcpO30KfQphc3luYyBmdW5jdGlvbiBNQ0IodGssZW4sa2Qsa3UsZGlhcyxwZngpewogIHRyeXsKICAgIGNvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9tb250ZWNhcmxvL2JhcnJpZXInLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcjp0ayxlbnRyeTplbixrZG86a2Qsa3VvOmt1LHRfZGF5czpkaWFzLG46MzAwMH0pfSk7CiAgICBpZighci5vayl0aHJvdyAwO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoZC5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZC5lcnJvcik7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1sJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtcicpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLW5iJykudGV4dENvbnRlbnQ9ZC5wcm9iX3NlbV9iYXJyZWlyYS50b0ZpeGVkKDEpKyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLWt1JykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2FsdGEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1rZCcpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9iYWl4YS50b0ZpeGVkKDEpKyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLXZvJykudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1pJykudGV4dENvbnRlbnQ9J1IkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua2RvKycgwrcgS1VPIFIkICcrZC5rdW87CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLWwnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwndGltZW91dCcpO30KfQphc3luYyBmdW5jdGlvbiBNQ1IodGssZW4sa2QsZGlhcyl7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcjp0ayxrX2NhbGw6ZW4sa19wdXQ6ZW4sdF9kYXlzOmRpYXMsa25vY2tfZG93bjprZCxuOjUwMDB9KX0pOwogICAgaWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWwnKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtcicpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGNvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtcycpO3NFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX3N1Y2Vzc28pLnRvRml4ZWQoMSkrJyUnO3NFbC5jbGFzc05hbWU9J2l2ICcrKGQucHJvYl9zdWNlc3NvPjcwPydvayc6ZC5wcm9iX3N1Y2Vzc28+NTA/J3dhcm4nOidkb3duJyk7CiAgICBjb25zdCBjRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWMnKTtpZihjRWwpY0VsLnRleHRDb250ZW50PU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYSkudG9GaXhlZCgxKSsnJSc7CiAgICBjb25zdCBrRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWsnKTtpZihrRWwpa0VsLnRleHRDb250ZW50PWQucHJvYl9rZG9fYXRpbmdpZG8hPW51bGw/TnVtYmVyKGQucHJvYl9rZG9fYXRpbmdpZG8pLnRvRml4ZWQoMSkrJyUnOifigJQnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXYnKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1pJykudGV4dENvbnRlbnQ9J1IkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua25vY2tfZG93bjsKICB9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWwnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwndGltZW91dCcpO30KfQphc3luYyBmdW5jdGlvbiBmSW5kKHRrKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDMwMDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdGsse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkJUQ0koKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDE1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9idGMvaW5kaWNhdG9ycycse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkJUQ0MoKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDE1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9idGMvY3ljbGUnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZGRygpewogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2ZlYXJncmVlZCcpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgY29uc3Qgdj1kLnZhbHVlfHw1MCxjbHM9djw9MjU/J3ZhcigtLXJlZCknOnY8PTQ1Pyd2YXIoLS13YXJuKSc6djw9NzU/J3ZhcigtLWFjY2VudCknOid2YXIoLS1ncmVlbiknOwogICAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ZnLWFyZWEnKTsKICAgIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHgiPjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjhweDtmb250LXdlaWdodDo2MDA7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHgiPvCfmLEgRmVhciAmIEdyZWVkIEluZGV4PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTRweCI+PGRpdiBzdHlsZT0iZm9udC1zaXplOjM4cHg7Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOicrY2xzKyciPicrdisnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOicrY2xzKyciPicrKGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKSsnPC9kaXY+PC9kaXY+PC9kaXY+JzsKICAgIEUoJ2ZnLXZhbCcsU3RyaW5nKHYpKTtFKCdmZy1sYmwnLGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKTsKICAgIHRyeXtjb25zdCByYj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pO2lmKHJiLm9rKXtjb25zdCBkYj1hd2FpdCByYi5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkYi5CVEN8fDApO2lmKGJwPjApe0UoJ2J0Yy1pbmQtcCcsJyQnK051bWJlcihicCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7RSgnYnRjLXAnLGZVKGJwKSk7fX19Y2F0Y2goZTIpe30KICB9Y2F0Y2goZSl7fQp9CmZ1bmN0aW9uIHJuZEluZChpZCxkYXRhKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZCcpO2lmKCFlbClyZXR1cm47CiAgaWYoIWRhdGEpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7cGFkZGluZzoxMnB4O2ZvbnQtc2l6ZToxM3B4Ij7ij7MgU2VtIHJlc3Bvc3RhIOKAlCBjbGlxdWUg4oa7PC9kaXY+JztyZXR1cm47fQogIGlmKGRhdGEuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tcmVkKTtwYWRkaW5nOjEycHg7Zm9udC1zaXplOjEzcHgiPuKaoCAnK2RhdGEuZXJyb3IrJzwvZGl2Pic7cmV0dXJuO30KICBjb25zdCBpbmRzPWRhdGEuaW5kaWNhZG9yZXN8fFtdLHNjPU51bWJlcihkYXRhLnNjb3JlX3RvdGFsfHwwKSxwcmVjbz1kYXRhLnByZWNvX2F0dWFsLGdyYWhhbT1kYXRhLmdyYWhhbV92YWx1ZSx1cD1kYXRhLnVwc2lkZV9ncmFoYW0sc2V0b3I9ZGF0YS5zZXRvcnx8Jyc7CiAgY29uc3Qgc2MyPXNjPj02NT8ndmFyKC0tZ3JlZW4pJzpzYz49NDA/J3ZhcigtLXdhcm4pJzondmFyKC0tcmVkKScsc2w9c2M+PTY1PydDb21wcmEg4payJzpzYz49NDA/J05ldXRybyDihpInOidWZW5kYSDilrwnOwogIGxldCBoPSc8ZGl2IGNsYXNzPSJzY2IiPicrCiAgICAnPGRpdiBjbGFzcz0ic2NjIj48ZGl2IGNsYXNzPSJzY20iPlNjb3JlPC9kaXY+PGRpdiBjbGFzcz0ic2NuIiBzdHlsZT0iY29sb3I6JytzYzIrJyI+JytzYysnPC9kaXY+PGRpdiBjbGFzcz0ic2NsIiBzdHlsZT0iY29sb3I6JytzYzIrJyI+JytzbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJzY2MiPjxkaXYgY2xhc3M9InNjbSI+Q290YcOnw6NvPC9kaXY+PGRpdiBjbGFzcz0ic2N2Ij4nKyhwcmVjbz8nUiQgJytOdW1iZXIocHJlY28pLnRvRml4ZWQoMik6J+KAlCcpKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY3MiPicrc2V0b3IrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0ic2NjIj48ZGl2IGNsYXNzPSJzY20iPkdyYWhhbSBWSjwvZGl2PjxkaXYgY2xhc3M9InNjdiIgc3R5bGU9ImNvbG9yOicrKHVwJiZ1cD4wPyd2YXIoLS1ncmVlbiknOid2YXIoLS1yZWQpJykrJyI+JysoZ3JhaGFtPydSJCAnK051bWJlcihncmFoYW0pLnRvRml4ZWQoMik6J+KAlCcpKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY3MiIHN0eWxlPSJjb2xvcjonKyh1cCYmdXA+MD8ndmFyKC0tZ3JlZW4pJzondmFyKC0tcmVkKScpKyciPicrKHVwIT1udWxsPyh1cD4wPycrJzonJykrdXArJyUgdXBzaWRlJzon4oCUJykrJzwvZGl2PjwvZGl2PicrCiAgICAnPC9kaXY+JzsKICBpbmRzLmZvckVhY2goaT0+ewogICAgY29uc3Qgcz1pLnNpbmFsfHwnJyxjbHM9cz09PSdBbHRhJ3x8cz09PSdTb2JyZXZlbmRhJz8nb2snOnM9PT0nQmFpeGEnfHxzPT09J1NvYnJlY29tcHJhJz8nZG93bic6J3dhcm4nLGFyPWNscz09PSdvayc/J+KWsic6Y2xzPT09J2Rvd24nPyfilrwnOifihpInOwogICAgaCs9JzxkaXYgY2xhc3M9ImlyIj48ZGl2IGNsYXNzPSJpcnQiPjxzcGFuIGNsYXNzPSJpcm4iPicrKGkubm9tZXx8JycpKyc8L3NwYW4+PHNwYW4gY2xhc3M9ImlydiAnK2NscysnIj4nKyhpLnZhbG9yIT1udWxsP2kudmFsb3I6J+KAlCcpKycgJythcisnPC9zcGFuPjwvZGl2PicrKGkuZXhwbGljYWNhbz8nPGRpdiBjbGFzcz0iaXJlIj4nK2kuZXhwbGljYWNhbysnPC9kaXY+JzonJykrJzwvZGl2Pic7CiAgfSk7CiAgZWwuaW5uZXJIVE1MPWh8fCc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMHB4Ij5TZW0gaW5kaWNhZG9yZXM8L2Rpdj4nOwp9CmZ1bmN0aW9uIHJuZEJUQ0koZCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1pbmQtYXJlYScpO2lmKCFlbHx8IWQpcmV0dXJuOwogIGlmKGQuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7cGFkZGluZzoxMnB4O2ZvbnQtc2l6ZToxM3B4Ij7ij7MgJytkLmVycm9yKyc8L2Rpdj4nO3JldHVybjt9CiAgbGV0IGg9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4Ij4nOwogIGlmKGQucnNpX3NlbWFuYWwhPW51bGwpe2NvbnN0IHJ2PWQucnNpX3NlbWFuYWwscmM9cnY8MzA/J29rJzpydj43MD8nZG93bic6J3dhcm4nO2grPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iaXYgJytyYysnIj4nK3J2LnRvRml4ZWQoMSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JysocnY8MzA/J1NvYnJldmVuZGEg4pqhJzpydj43MD8nU29icmVjb21wcmEg4pqgJzonTmV1dHJvJykrJzwvZGl2PjwvZGl2Pic7RSgnYnRjLXJzaScscnYudG9GaXhlZCgxKSk7fQogIGlmKGQubW01MF9zZW1hbmFsKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1NIDUwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4kJytOdW1iZXIoZC5tbTUwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZC5tbTIwMF9zZW1hbmFsKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1NIDIwMCBzZW0uPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JCcrTnVtYmVyKGQubW0yMDBfc2VtYW5hbCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PC9kaXY+JzsKICBpZihkLm1hY2RfaGlzdG9ncmFtIT1udWxsKXtjb25zdCBtaD1kLm1hY2RfaGlzdG9ncmFtO2grPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1BQ0QgSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiAnKyhtaD4wPydvayc6J2Rvd24nKSsnIj4nK051bWJlcihtaCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nKyhtaD4wPydNb21lbnR1bSDilrInOidNb21lbnR1bSDilrwnKSsnPC9kaXY+PC9kaXY+Jzt9CiAgaWYoZC5vYnZfdHJlbmQpaCs9JzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+T0JWPC9kaXY+PGRpdiBjbGFzcz0iaXYgJysoZC5vYnZfdHJlbmQ9PT0nc3ViaW5kbyc/J29rJzonZG93bicpKyciPicrZC5vYnZfdHJlbmQrJzwvZGl2PjwvZGl2Pic7CiAgaCs9JzwvZGl2Pic7ZWwuaW5uZXJIVE1MPWg7CiAgaWYoZC5wcmljZSlFKCdidGMtaW5kLXAnLCckJytOdW1iZXIoZC5wcmljZSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7Cn0KZnVuY3Rpb24gcm5kQlRDQyhkKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWN5Y2xlLWFyZWEnKTtpZighZWx8fCFkfHxkLmVycm9yKXJldHVybjsKICBjb25zdCBmVTI9dj0+dj8nJCcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CiAgZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEwcHgiPicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NVlJWIFotU2NvcmU8L2Rpdj48ZGl2IGNsYXNzPSJpdiAnKyhkLm12cnZfenNjb3JlPy52YWx1ZTwxPydvayc6ZC5tdnJ2X3pzY29yZT8udmFsdWU8Mz8nd2Fybic6J2Rvd24nKSsnIj4nK2QubXZydl96c2NvcmU/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5tdnJ2X3pzY29yZT8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5OVVBMPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JysoKGQubnVwbD8udmFsdWV8fDApKjEwMCkudG9GaXhlZCgwKSsnJTwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JytkLm51cGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHVlbGwgTXVsdGlwbGU8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nK2QucHVlbGw/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5wdWVsbD8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj4yMDBXIE1BPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JytmVTIoZC5tYTIwMHcpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrKGQubWEyMDB3X3BjdD8nKycrZC5tYTIwMHdfcGN0KyclJzonJykrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5SYWluYm93IEJhbmQ8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nKyhkLnJhaW5ib3c/LmJhbmR8fCfigJQnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlBpIEN5Y2xlIERpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siPicrZlUyKGQucGlfY3ljbGU/LmRpc3RhbmNlKSsnPC9kaXY+PC9kaXY+JysKICAgICc8L2Rpdj48ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweDtmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjYwMCI+JysoZC5waV9jeWNsZT8uc2lnbmFsfHwnJykrJzwvZGl2Pic7Cn0KYXN5bmMgZnVuY3Rpb24gbG9hZEluZCgpewogIGNvbnN0IHd0PShwLG1zLGZiKT0+UHJvbWlzZS5yYWNlKFtwLG5ldyBQcm9taXNlKHI9PnNldFRpbWVvdXQoKCk9PnIoZmIpLG1zKSldKTsKICBjb25zdFtiaSxiY109YXdhaXQgUHJvbWlzZS5hbGwoW3d0KGZCVENJKCksMTUwMDAse2Vycm9yOidUaW1lb3V0IOKAlCBjbGlxdWUg4oa7J30pLHd0KGZCVENDKCksMTUwMDAsbnVsbCldKTsKICBybmRCVENJKGJpKTtybmRCVENDKGJjKTtmRkcoKTsKICBjb25zdCBzdG9ja3M9W1snUEVUUjQuU0EnLCdwZXRyNCddLFsnVkFMRTMuU0EnLCd2YWxlMyddLFsnQkJBUzMuU0EnLCdiYmFzMyddLFsnQVhJQTMuU0EnLCdheGlhMyddLFsnUk9YTzM0LlNBJywncm94bzM0J11dOwogIGNvbnN0IHJlcz1hd2FpdCBQcm9taXNlLmFsbChzdG9ja3MubWFwKChbdF0pPT53dChmSW5kKHQpLDMwMDAwLHtlcnJvcjonVGltZW91dCAzMHMnfSkpKTsKICBzdG9ja3MuZm9yRWFjaCgoWyxpZF0saSk9PnJuZEluZChpZCxyZXNbaV0pKTsKfQphc3luYyBmdW5jdGlvbiBybCh0ayl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodGsrJy1pbmQnKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDFzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+JzsKICBjb25zdCBtPXtwZXRyNDonUEVUUjQuU0EnLHZhbGUzOidWQUxFMy5TQScsYmJhczM6J0JCQVMzLlNBJyxheGlhMzonQVhJQTMuU0EnLHJveG8zNDonUk9YTzM0LlNBJ307CiAgcm5kSW5kKHRrLGF3YWl0IGZJbmQobVt0a10pKTsKfQpjb25zdCBGTEFHUz17J1VTRCc6J/Cfh7rwn4e4JywnVVMnOifwn4e68J+HuCcsJ0JSTCc6J/Cfh6fwn4e3JywnQlInOifwn4en8J+HtycsJ0VVUic6J/Cfh6rwn4e6JywnRVUnOifwn4eq8J+HuicsJ0dCUCc6J/Cfh6zwn4enJywnQ05ZJzon8J+HqPCfh7MnLCdKUFknOifwn4ev8J+HtScsJ0NBRCc6J/Cfh6jwn4emJywnQVVEJzon8J+HpvCfh7onLCdERSc6J/Cfh6nwn4eqJywnTlpEJzon8J+Hs/Cfh78nLCdDSEYnOifwn4eo8J+HrSd9Owphc3luYyBmdW5jdGlvbiBsb2FkQ2FsKCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbC1hcmVhJyksc3Q9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbC1zdCcpOwogIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MjRweDt0ZXh0LWFsaWduOmNlbnRlcjthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2Pic7CiAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9J0J1c2NhbmRvIGV2ZW50b3MuLi4nOwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2NhbGVuZGFyJyx7Y2FjaGU6J25vLXN0b3JlJ30pOwogICAgaWYoIXIub2spdGhyb3cgbmV3IEVycm9yKCdIVFRQICcrci5zdGF0dXMpOwogICAgY29uc3QgZXZzPWF3YWl0IHIuanNvbigpOwogICAgaWYoZXZzLmVycm9yKXRocm93IG5ldyBFcnJvcihldnMuZXJyb3IpOwogICAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9ZXZzLmxlbmd0aD4wP2V2cy5sZW5ndGgrJyBldmVudG9zJzonU2VtIGV2ZW50b3MnOwogICAgaWYoIWV2cy5sZW5ndGgpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0icGFkZGluZzoyNHB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LWFsaWduOmNlbnRlciI+U2VtIGV2ZW50b3MgZGlzcG9uw612ZWlzPC9kaXY+JztyZXR1cm47fQogICAgY29uc3QgYnlEPXt9O2V2cy5mb3JFYWNoKGU9Pntjb25zdCBkdD0oZS5kYXRlfHwnJykuc2xpY2UoMCwxMCk7aWYoIWJ5RFtkdF0pYnlEW2R0XT1bXTtieURbZHRdLnB1c2goZSk7fSk7CiAgICBsZXQgaD0nJzsKICAgIE9iamVjdC5rZXlzKGJ5RCkuc29ydCgpLmZvckVhY2goZHQ9PnsKICAgICAgY29uc3QgZD1uZXcgRGF0ZShkdCsnVDEyOjAwOjAwJyksbGJsPWQudG9Mb2NhbGVEYXRlU3RyaW5nKCdwdC1CUicse3dlZWtkYXk6J2xvbmcnLGRheTonMi1kaWdpdCcsbW9udGg6J3Nob3J0J30pOwogICAgICBoKz0nPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+JytsYmwrJzwvZGl2PicrCiAgICAgICAgJzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7bWFyZ2luLWJvdHRvbToxNHB4Ij4nKwogICAgICAgICc8ZGl2IGNsYXNzPSJjaCI+PHNwYW4+UGHDrXM8L3NwYW4+PHNwYW4+SG9yYTwvc3Bhbj48c3Bhbj5FdmVudG88L3NwYW4+PHNwYW4+SW1wPC9zcGFuPjxzcGFuPlJlYWxpemFkbzwvc3Bhbj48c3Bhbj5QcmV2aXN0bzwvc3Bhbj48L2Rpdj4nOwogICAgICBieURbZHRdLmZvckVhY2goZT0+ewogICAgICAgIGNvbnN0IGljPWUuaW1wb3J0YW5jZT49Mz8ndmFyKC0tcmVkKSc6ZS5pbXBvcnRhbmNlPj0yPyd2YXIoLS13YXJuKSc6J3ZhcigtLW11dGVkKSc7CiAgICAgICAgY29uc3QgYWM9ZS5zaWduYWw9PT0nYmVhdCc/J3ZhcigtLWdyZWVuKSc6ZS5zaWduYWw9PT0nbWlzcyc/J3ZhcigtLXJlZCknOid2YXIoLS10ZXh0KSc7CiAgICAgICAgaCs9JzxkaXYgY2xhc3M9ImNyIj48c3Bhbj4nKyhlLmZsYWd8fEZMQUdTW2UuY291bnRyeV18fCfwn4yQJykrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIGNsYXNzPSJjdCI+JysoZS50aW1lfHwn4oCUJykrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIGNsYXNzPSJjbjIiIHRpdGxlPSInK2UuZXZlbnQrJyI+JytlLmV2ZW50Kyc8L3NwYW4+JysKICAgICAgICAgICc8c3BhbiBzdHlsZT0idGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6JytpYysnIj4nKyfil48nLnJlcGVhdChNYXRoLm1pbihlLmltcG9ydGFuY2UsMykpKyc8L3NwYW4+JysKICAgICAgICAgICc8c3BhbiBjbGFzcz0iY2EiIHN0eWxlPSJjb2xvcjonK2FjKyciPicrKGUuYWN0dWFsfHwn4oCUJykrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIGNsYXNzPSJjZiI+JysoZS5mb3JlY2FzdHx8J+KAlCcpKyc8L3NwYW4+JysKICAgICAgICAgICc8L2Rpdj4nOwogICAgICB9KTsKICAgICAgaCs9JzwvZGl2Pic7CiAgICB9KTsKICAgIGVsLmlubmVySFRNTD1oOwogIH1jYXRjaChlKXsKICAgIGlmKHN0KXN0LnRleHRDb250ZW50PSdFcnJvJzsKICAgIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tcmVkKTtwYWRkaW5nOjI0cHg7dGV4dC1hbGlnbjpjZW50ZXIiPkVycm86ICcrZS5tZXNzYWdlKyc8L2Rpdj4nOwogIH0KfQphc3luYyBmdW5jdGlvbiBtYWluKCl7CiAgdHJ5ewogICAgY29uc3RbLHR2LGZ0XT1hd2FpdCBQcm9taXNlLmFsbChbZkhMKCksZlRWKCksZkZ1dCgpXSk7CiAgICBjb25zdCBub3c9bmV3IERhdGUoKS50b0xvY2FsZVRpbWVTdHJpbmcoJ3B0LUJSJyk7CiAgICBFKCdsYXN0LXVwZGF0ZScsJ+KGuyAnK25vdyk7RSgnZm9vdGVyLXRpbWUnLG5vdyk7CiAgICBkb01hY3JvKHR2LGZ0KTtkb1Bvcyh0dik7CiAgICBzZXRUaW1lb3V0KGZGdW5kLDMwMDApOwogICAgc2V0VGltZW91dChhc3luYygpPT57dHJ5e2NvbnN0W2JpLGJjXT1hd2FpdCBQcm9taXNlLmFsbChbZkJUQ0koKSxmQlRDQygpXSk7aWYoYmkpcm5kQlRDSShiaSk7aWYoYmMpcm5kQlRDQyhiYyk7ZkZHKCk7fWNhdGNoKGUpe319LDUwMDApOwogICAgY29uc3QgaG9qZT1uZXcgRGF0ZSgpOwogICAgY29uc3QgZFA9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTEyLTE3JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRWPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNy0wMi0xOCcpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkQT1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDktMTQnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZEFiPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0xMC0wMicpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkUj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDctMTYnKS1ob2plKS84NjRlNSkpOwogICAgc2V0VGltZW91dCgoKT0+TUMoJ1BFVFI0LlNBJywzMC44NSxkUCwncHQtbWMtbCcsJ3B0LW1jLXInLCdwdC1tYy1zJywncHQtbWMtdicsJ3B0LW1jLWknLCdwdC1tYy1ydCcpLDYwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUMoJ1ZBTEUzLlNBJyw1Ny40MCxkViwndmwtbWMtbCcsJ3ZsLW1jLXInLCd2bC1tYy1zJywndmwtbWMtdicsJ3ZsLW1jLWknLCd2bC1tYy1ydCcpLDEyMDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DQignQVhJQTMuU0EnLDU0LjMxLDQzLjUxLDY4Ljc2LGRBLCdhMycpLDE4MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DQignQVhJQTMuU0EnLDUwLjY1LDQwLjUyLDYyLjgxLGRBYiwnYTNiJyksMjQwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUNSKCdST1hPMzQuU0EnLDEyLjg4LDEwLjUwLGRSKSwzMDAwMCk7CiAgICB3aW5kb3cuX0lMPWZhbHNlOwogIH1jYXRjaChlKXtjb25zb2xlLmVycm9yKGUpO30KfQptYWluKCk7c2V0SW50ZXJ2YWwobWFpbiwxMjAwMDApOwo8L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+Cg==").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
