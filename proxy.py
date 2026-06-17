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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjExLjIg4oCUIERhcmsgUHJlbWl1bSAtLT4KPGh0bWwgbGFuZz0icHQtQlIiPgo8aGVhZD4KPG1ldGEgY2hhcnNldD0iVVRGLTgiPgo8bWV0YSBuYW1lPSJ2aWV3cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MS4wIj4KPHRpdGxlPlRyYWRlciBEZXNrPC90aXRsZT4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JbnRlcjp3Z2h0QDQwMDs1MDA7NjAwOzcwMCZmYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs2MDA7NzAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Cjpyb290ewogIC0tYmc6IzBmMGYxMzstLWJnMjojMTMxMzFhOy0tYmczOiMxYTFhMjQ7CiAgLS10ZXh0OiNlOGU4ZjA7LS1tdXRlZDojNTA1MDY4Oy0tYm9yZGVyOiMxZTFlMmU7CiAgLS1hY2NlbnQ6IzdjNmFmNzstLWFjY2VudDI6IzRmYzNmNzsKICAtLWdyZWVuOiMwMGU2NzY7LS1yZWQ6I2YwNjI5MjstLXdhcm46I2ZmYjc0ZDsKICAtLWdvbGQ6I2YwYTUwMAp9CmJvZHl7CiAgYmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7CiAgZm9udC1mYW1pbHk6J0ludGVyJyxzYW5zLXNlcmlmO2ZvbnQtc2l6ZToxNHB4OwogIGxpbmUtaGVpZ2h0OjEuNTtwYWRkaW5nOjIwcHggMjRweDsKICBtYXgtd2lkdGg6MTEwMHB4O21hcmdpbjowIGF1dG87bWluLWhlaWdodDoxMDB2aAp9CkBtZWRpYShtYXgtd2lkdGg6NjAwcHgpe2JvZHl7cGFkZGluZzoxMnB4fX0KCi8qIOKUgOKUgCBIRUFERVIg4pSA4pSAICovCi5oZHJ7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjIwcHg7cGFkZGluZy1ib3R0b206MTZweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpfQoubG9nb3tmb250LXNpemU6MThweDtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtsZXR0ZXItc3BhY2luZzouNXB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5sb2dvIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50Mil9Ci5oZHItcmlnaHR7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweH0KLmJhZGdle2JhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo0cHggMTJweDtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4fQouaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQoKLyog4pSA4pSAIFRBQlMg4pSA4pSAICovCi50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MjBweDtvdmVyZmxvdy14OmF1dG87cGFkZGluZy1ib3R0b206MnB4fQoudGFie3BhZGRpbmc6OHB4IDE4cHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6MTJweDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3doaXRlLXNwYWNlOm5vd3JhcDtmb250LWZhbWlseTppbmhlcml0O3RyYW5zaXRpb246YWxsIC4xNXN9Ci50YWI6aG92ZXJ7Y29sb3I6dmFyKC0tdGV4dCk7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci50YWIuYWN0aXZle2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtjb2xvcjojZmZmO2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpfQoudGFiLWNvbnRlbnR7ZGlzcGxheTpub25lfS50YWItY29udGVudC5hY3RpdmV7ZGlzcGxheTpibG9ja30KCi8qIOKUgOKUgCBTRUNUSU9OIOKUgOKUgCAqLwouc2Vje2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHggMCA3cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjE0cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4fQouc2VjIC5kb3R7d2lkdGg6NXB4O2hlaWdodDo1cHg7YmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrO2ZsZXgtc2hyaW5rOjB9Ci5zZWMgLmFjY3tjb2xvcjp2YXIoLS1hY2NlbnQpfQoKLyog4pSA4pSAIEdSSUQgQ0FSRFMg4pSA4pSAICovCi5ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDMsMWZyKTtnYXA6MTBweDttYXJnaW4tYm90dG9tOjE4cHh9CkBtZWRpYShtYXgtd2lkdGg6NTAwcHgpey5ncmlke2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoMiwxZnIpfX0KLmNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHggMTRweDtwb3NpdGlvbjpyZWxhdGl2ZTtvdmVyZmxvdzpoaWRkZW47dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1c30KLmNhcmQ6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci5jYXJkOjpiZWZvcmV7Y29udGVudDonJztwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MDtsZWZ0OjA7cmlnaHQ6MDtoZWlnaHQ6MnB4fQouY2FyZC5nOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tZ3JlZW4pLCMwMGJjZDQpfQouY2FyZC5iOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tYWNjZW50KSx2YXIoLS1hY2NlbnQyKSl9Ci5jYXJkLnc6OmJlZm9yZXtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS13YXJuKSwjZmY5ODAwKX0KLmNhcmQucjo6YmVmb3Jle2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLHZhcigtLXJlZCksI2U5MWU2Myl9Ci5jbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjRweDtmb250LXdlaWdodDo2MDB9Ci5jbntmb250LXNpemU6MTNweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLWJvdHRvbTo4cHg7Y29sb3I6cmdiYSgyNTUsMjU1LDI1NSwuOCl9Ci5jcHtmb250LXNpemU6MjBweDtmb250LXdlaWdodDo3MDA7Y29sb3I6I2ZmZn0KLmNwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToxNXB4fQouY2N7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NTAwfQouY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0uY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjN9fQoKLyog4pSA4pSAIEFDQ09SRElPTiBTRUdNRU5UT1Mg4pSA4pSAICovCi5zaHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweCAxNnB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7Zm9udC1zaXplOjEycHg7Zm9udC13ZWlnaHQ6NjAwO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDt0cmFuc2l0aW9uOmFsbCAuMTVzfQouc2g6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zYjJ7ZGlzcGxheTpub25lO3BhZGRpbmctdG9wOjZweH0KCi8qIOKUgOKUgCBQT1NJw4fDlUVTIOKUgOKUgCAqLwoucGN7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjE4cHg7bWFyZ2luLWJvdHRvbToxMnB4fQoucGx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnB0e2ZvbnQtc2l6ZToyMnB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO21hcmdpbi1ib3R0b206NHB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5wcHtmb250LXNpemU6MjhweDtmb250LXdlaWdodDo3MDB9LnBwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToyMHB4fQoucGMye2ZvbnQtc2l6ZToxMnB4O21hcmdpbi1ib3R0b206MTBweDtmb250LXdlaWdodDo1MDB9Ci5zYntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmctdG9wOjEwcHg7bWFyZ2luLXRvcDoxMHB4fQouc3J7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjVweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEzcHh9Ci5zbHtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NTAwfS5zdnt0ZXh0LWFsaWduOnJpZ2h0O21heC13aWR0aDo1OCU7Zm9udC13ZWlnaHQ6NjAwfQouc3Yub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5zdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zdi5pdG17Y29sb3I6dmFyKC0tcmVkKX0KLnNpZ3tib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxNHB4O21hcmdpbi10b3A6MTBweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLnNndHtmb250LXNpemU6MTBweDtmb250LXdlaWdodDo3MDA7bGV0dGVyLXNwYWNpbmc6MXB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjhweDtjb2xvcjp2YXIoLS1hY2NlbnQyKX0KLmlie2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMnB4O3RleHQtYWxpZ246Y2VudGVyfQouaWx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206NXB4O2ZvbnQtd2VpZ2h0OjYwMDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjVweH0KLml2e2ZvbnQtc2l6ZToyMHB4O2ZvbnQtd2VpZ2h0OjgwMH0KLml2Lm9re2NvbG9yOnZhcigtLWdyZWVuKX0uaXYud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaXYuZG93bntjb2xvcjp2YXIoLS1yZWQpfQoKLyog4pSA4pSAIElORElDQURPUkVTIOKUgOKUgCAqLwouc2Nie2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmciAxZnI7Z2FwOjhweDttYXJnaW4tYm90dG9tOjE0cHh9Ci5zY2N7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHggMTJweDt0ZXh0LWFsaWduOmNlbnRlcjtwb3NpdGlvbjpyZWxhdGl2ZTtvdmVyZmxvdzpoaWRkZW59Ci5zY2M6OmJlZm9yZXtjb250ZW50OicnO3Bvc2l0aW9uOmFic29sdXRlO3RvcDowO2xlZnQ6MDtyaWdodDowO2hlaWdodDoycHg7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tYWNjZW50KSx2YXIoLS1hY2NlbnQyKSl9Ci5zY217Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzoxcHg7bWFyZ2luLWJvdHRvbTo1cHg7Zm9udC13ZWlnaHQ6NjAwfQouc2Nue2ZvbnQtc2l6ZTozMnB4O2ZvbnQtd2VpZ2h0OjgwMDtsaW5lLWhlaWdodDoxfQouc2Nse2ZvbnQtc2l6ZToxMXB4O21hcmdpbi10b3A6NHB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnNjdntmb250LXNpemU6MjBweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLXRvcDo0cHh9Ci5zY3N7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4fQouaXJ7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDoycHggc29saWQgdHJhbnNwYXJlbnQ7cGFkZGluZzoxMHB4IDE0cHg7bWFyZ2luLWJvdHRvbTo0cHg7dHJhbnNpdGlvbjpib3JkZXItbGVmdC1jb2xvciAuMXN9Ci5pcjpob3Zlcntib3JkZXItbGVmdC1jb2xvcjp2YXIoLS1hY2NlbnQpfQouaXJ0e2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpiYXNlbGluZTttYXJnaW4tYm90dG9tOjNweH0KLmlybntmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHg7Zm9udC13ZWlnaHQ6NjAwfQouaXJ2e2ZvbnQtc2l6ZToxNXB4O2ZvbnQtd2VpZ2h0OjcwMH0KLmlydi5va3tjb2xvcjp2YXIoLS1ncmVlbil9Lmlydi5kb3due2NvbG9yOnZhcigtLXJlZCl9Lmlydi53YXJue2NvbG9yOnZhcigtLXdhcm4pfQouaXJle2ZvbnQtc2l6ZToxM3B4O2NvbG9yOiM1YTVhOGE7bGluZS1oZWlnaHQ6MS41fQoKLyog4pSA4pSAIENBTEVORMOBUklPIOKUgOKUgCAqLwouY2FsLXRibHt3aWR0aDoxMDAlO2JvcmRlci1jb2xsYXBzZTpjb2xsYXBzZTtmb250LWZhbWlseTonSW50ZXInLHNhbnMtc2VyaWZ9Ci5jYWwtdGJsIHRoe3RleHQtYWxpZ246bGVmdDtwYWRkaW5nOjdweCAxNHB4O2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JhY2tncm91bmQ6dmFyKC0tYmczKX0KLmNhbC10YmwgdGgucnt0ZXh0LWFsaWduOnJpZ2h0fQouY2FsLXRibCB0ZHtwYWRkaW5nOjlweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEzcHg7dmVydGljYWwtYWxpZ246bWlkZGxlfQouY2FsLXRibCB0ZC5ye3RleHQtYWxpZ246cmlnaHR9Ci5jYWwtdGJsIHRyOmxhc3QtY2hpbGQgdGR7Ym9yZGVyLWJvdHRvbTpub25lfQouY2FsLXRibCB0cjpob3ZlciB0ZHtiYWNrZ3JvdW5kOnZhcigtLWJnMyl9Ci5jYWwtZmxhZ3tmb250LXNpemU6MTZweH0KLmNhbC10aW1le2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKTtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlfQouY2FsLWV2e2ZvbnQtd2VpZ2h0OjUwMDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXA7bWF4LXdpZHRoOjMyMHB4fQouY2FsLXZhbHtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtd2VpZ2h0OjcwMDt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxM3B4fQouY2FsLWZje2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1tdXRlZCl9Ci5pbXAtaGlnaHtjb2xvcjp2YXIoLS1yZWQpfS5pbXAtbWVke2NvbG9yOnZhcigtLXdhcm4pfQoKLmluZC1hY2N7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjE2cHh9Ci5pbmQtYWNjLWhkcntkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6MTJweCAxNnB4O2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246YmFja2dyb3VuZCAuMTVzfQouaW5kLWFjYy1oZHI6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQouaW5kLWFjYy10aXRsZXtmb250LXNpemU6MTRweDtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KX0KLmluZC1hY2Mtc3Vie2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweH0KLmluZC1hY2MtYm9keXtkaXNwbGF5Om5vbmU7cGFkZGluZzowIDE2cHggMTZweH0KLmluZC1hY2MtYm9keS5vcGVue2Rpc3BsYXk6YmxvY2t9Ci50YmwtbWt0e3dpZHRoOjEwMCU7Ym9yZGVyLWNvbGxhcHNlOmNvbGxhcHNlO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci50YmwtbWt0IHRoZWFkIHRye2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcil9Ci50YmwtbWt0IHRoe3RleHQtYWxpZ246bGVmdDtwYWRkaW5nOjdweCAxNHB4O2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtmb250LWZhbWlseTonSW50ZXInLHNhbnMtc2VyaWZ9Ci50YmwtbWt0IHRoLnJ7dGV4dC1hbGlnbjpyaWdodH0KLnRibC1ta3QgdGR7cGFkZGluZzo5cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2ZvbnQtc2l6ZToxNHB4O3ZlcnRpY2FsLWFsaWduOm1pZGRsZX0KLnRibC1ta3QgdGQucnt0ZXh0LWFsaWduOnJpZ2h0fQoudGJsLW1rdCB0cjpsYXN0LWNoaWxkIHRke2JvcmRlci1ib3R0b206bm9uZX0KLnRibC1ta3QgdHI6aG92ZXIgdGR7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQoudGJsLW1rdCAuc3lte2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS10ZXh0KX0KLnRibC1ta3QgLmRlc2N7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtd2VpZ2h0OjQwMDtmb250LWZhbWlseTonSW50ZXInLHNhbnMtc2VyaWY7bWFyZ2luLXRvcDoxcHh9Ci50YmwtbWt0IC52YWx7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxNXB4O2NvbG9yOnZhcigtLXRleHQpfQoudGJsLW1rdCAudmFsLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToxMnB4fQoudGJsLW1rdCAuY2hne2ZvbnQtc2l6ZToxM3B4O2ZvbnQtd2VpZ2h0OjYwMH0KLnRibC1ta3QgLmNoZy11cHtjb2xvcjp2YXIoLS1ncmVlbil9LnRibC1ta3QgLmNoZy1kbntjb2xvcjp2YXIoLS1yZWQpfS50YmwtbWt0IC5jaGctZmx7Y29sb3I6dmFyKC0tbXV0ZWQpfQoudGJsLXdyYXB7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItcmFkaXVzOjhweDtvdmVyZmxvdzpoaWRkZW47bWFyZ2luLWJvdHRvbToxOHB4fQoudGJsLWhkcntiYWNrZ3JvdW5kOnZhcigtLWJnMyk7cGFkZGluZzo5cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXJ9Ci50YmwtaGRyLXRpdGxle2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjEuNXB4fQoudGJsLWhkci10aW1le2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKX0KZm9vdGVye21hcmdpbi10b3A6MjRweDtwYWRkaW5nLXRvcDoxMnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTtmb250LXdlaWdodDo1MDB9Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+Cgo8ZGl2IGNsYXNzPSJoZHIiPgogIDxkaXYgY2xhc3M9ImxvZ28iPlRSQURFUiA8c3Bhbj5ERVNLPC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9Imhkci1yaWdodCI+CiAgICA8ZGl2IGNsYXNzPSJiYWRnZSI+4pePIEFPIFZJVk88L2Rpdj4KICAgIDxkaXYgY2xhc3M9Imhkci10aW1lIiBpZD0ibGFzdC11cGRhdGUiPuKAlDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9InRhYnMiPgogIDxkaXYgY2xhc3M9InRhYiBhY3RpdmUiIG9uY2xpY2s9InN3KCdjb3RhY29lcycsdGhpcykiPvCfk4ogQ290YcOnw7VlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3coJ2luZGljYWRvcmVzJyx0aGlzKSI+8J+TiCBJbmRpY2Fkb3JlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3coJ3Bvc2ljb2VzJyx0aGlzKSI+8J+SvCBQb3Npw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygnY2FsZW5kYXJpbycsdGhpcykiPvCfk4UgQ2FsZW5kw6FyaW88L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBDT1RBw4fDlUVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWNvdGFjb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQgYWN0aXZlIj4KICA8ZGl2IGNsYXNzPSJ0Ymwtd3JhcCI+CiAgICA8ZGl2IGNsYXNzPSJ0YmwtaGRyIj48c3BhbiBjbGFzcz0idGJsLWhkci10aXRsZSI+RVVBIOKAlCBNZXJjYWRvczwvc3Bhbj48c3BhbiBjbGFzcz0idGJsLWhkci10aW1lIiBpZD0ibGFzdC11cGRhdGUtdGJsIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+VmFyLiU8L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5TJmFtcDtQIEVTMSo8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5GdXR1cm8gUyZQIDUwMDwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJlc2YtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZXNmLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImVzZi1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5OYXNkYXEgTlE8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5GdXR1cm8gTmFzZGFxIDEwMDwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJucWYtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0ibnFmLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Im5xZi1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5Eb3cgSm9uZXM8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj7DjW5kaWNlIERKSUE8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iZGppLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImRqaS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJkamktYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+VklYPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+Vm9sYXRpbGlkYWRlPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9InZpeC1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2aXgtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0idml4LWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkRYWTwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkTDs2xhciBJbmRleDwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJkeHktcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZHh5LXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImR4eS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5VU0QvQlJMPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+Q8OibWJpbyBEw7NsYXI8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0idXNkLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InVzZC12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ1c2QtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgPC90Ym9keT4KICAgIDwvdGFibGU+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InRibC13cmFwIj4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5CMyDigJQgVG9wIDEwPC9zcGFuPjwvZGl2PgogICAgPHRhYmxlIGNsYXNzPSJ0YmwtbWt0Ij4KICAgICAgPHRoZWFkPjx0cj48dGg+QXRpdm88L3RoPjx0aCBjbGFzcz0iciI+w5psdGltbzwvdGg+PHRoIGNsYXNzPSJyIj5WYXJpYcOnw6NvPC90aD48dGggY2xhc3M9InIiPlZhci4lPC90aD48L3RyPjwvdGhlYWQ+CiAgICAgIDx0Ym9keT4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+SUJPVjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPsONbmRpY2UgQm92ZXNwYTwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJpYm92LXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Imlib3YtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iaWJvdi1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5XSU4xITwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkZ1dHVybyBJQk9WPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9Indpbi1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ3aW4tdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0id2luLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlBFVFI0PC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+UGV0cm9icmFzIFBOPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9InBldHI0cS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJwZXRyNHEtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0icGV0cjRxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPklUVUI0PC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+SXRhw7ogVW5pYmFuY28gUE48L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iaXR1YjRxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Iml0dWI0cS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJpdHViNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+VkFMRTM8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5WYWxlIE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9InZhbGUzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2YWxlM3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0idmFsZTNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJCREM0PC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+QnJhZGVzY28gUE48L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iYmJkYzRxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJiZGM0cS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJiYmRjNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+QUJFVjM8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5BbWJldiBPTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJhYmV2M3EtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYWJldjNxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImFiZXYzcS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5CQkFTMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkJhbmNvIGRvIEJyYXNpbCBPTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJiYmFzM3EtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYmJhczNxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJiYXMzcS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5XRUdFMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPldFRyBPTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJ3ZWdlM3EtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0id2VnZTNxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9IndlZ2UzcS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5ST1hPMzQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5OdWJhbmsgQkRSPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9InJveG8zNHEtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0icm94bzM0cS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJyb3hvMzRxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgIDwvdGJvZHk+CiAgICA8L3RhYmxlPgogIDwvZGl2PgoKICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbiI+PHNwYW4gc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweCI+PHNwYW4gY2xhc3M9ImRvdCI+PC9zcGFuPkIzIHBvciBTZWdtZW50bzwvc3Bhbj48YnV0dG9uIG9uY2xpY2s9ImV4cGFuZEFsbCgpIiBpZD0iYnRuLWV4cGFuZCIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y29sb3I6dmFyKC0tYWNjZW50KTtwYWRkaW5nOjRweCAxMnB4O2ZvbnQtc2l6ZToxMXB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NjAwO2xldHRlci1zcGFjaW5nOi41cHgiPisgRXhwYW5kaXIgVG9kb3M8L2J1dHRvbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2ZpbicpIj48c3Bhbj7wn4+mIEZpbmFuY2Vpcm88L3NwYW4+PHNwYW4gaWQ9ImFyLWZpbiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWZpbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctZmluIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ3BldCcpIj48c3Bhbj7wn5uiIFBldHLDs2xlbyAmYW1wOyBHw6FzPC9zcGFuPjxzcGFuIGlkPSJhci1wZXQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1wZXQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXBldCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdtaW4nKSI+PHNwYW4+4puPIE1pbmVyYcOnw6NvPC9zcGFuPjxzcGFuIGlkPSJhci1taW4iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1taW4iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW1pbiI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdtYXQnKSI+PHNwYW4+8J+MsiBQYXBlbCAmYW1wOyBDZWx1bG9zZTwvc3Bhbj48c3BhbiBpZD0iYXItbWF0Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItbWF0Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1tYXQiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygndXRpJykiPjxzcGFuPuKaoSBVdGlsaWRhZGUgUMO6YmxpY2E8L3NwYW4+PHNwYW4gaWQ9ImFyLXV0aSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXV0aSI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctdXRpIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2NjJykiPjxzcGFuPvCfm40gQ29uc3VtbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0iYXItY2MiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1jYyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctY2MiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnY24nKSI+PHNwYW4+8J+bkiBDb25zdW1vIE7Do28gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9ImFyLWNuIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItY24iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWNuIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ3NhdScpIj48c3Bhbj7wn4+lIFNhw7pkZTwvc3Bhbj48c3BhbiBpZD0iYXItc2F1Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2Itc2F1Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1zYXUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnaW5kJykiPjxzcGFuPvCfj5cgQmVucyBJbmR1c3RyaWFpczwvc3Bhbj48c3BhbiBpZD0iYXItaW5kIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItaW5kIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1pbmQiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygndGl0JykiPjxzcGFuPvCfkrsgVEkgJmFtcDsgQ29tdW5pY2HDp8O1ZXM8L3NwYW4+PHNwYW4gaWQ9ImFyLXRpdCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXRpdCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctdGl0Ij48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+RVVBIHBvciBTZWdtZW50bzwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnbTcnKSI+PHNwYW4+4q2QIDcgTWFnbsOtZmljYXM8L3NwYW4+PHNwYW4gaWQ9ImFyLW03Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItbTciPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW03Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ25xJykiPjxzcGFuPvCfkrsgTmFzZGFxIFRvcCAxNTwvc3Bhbj48c3BhbiBpZD0iYXItbnEiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1ucSI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbnEiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0Zygnc3AnKSI+PHNwYW4+8J+TiiBTJmFtcDtQIDUwMCBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9ImFyLXNwIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2Itc3AiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXNwIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2RqJykiPjxzcGFuPvCfj5sgRG93IEpvbmVzIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0iYXItZGoiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1kaiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctZGoiPjwvZGl2PjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJ0Ymwtd3JhcCIgc3R5bGU9Im1hcmdpbi10b3A6MTZweCI+CiAgICA8ZGl2IGNsYXNzPSJ0YmwtaGRyIj48c3BhbiBjbGFzcz0idGJsLWhkci10aXRsZSI+Q29tbW9kaXRpZXM8L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48L3RyPjwvdGhlYWQ+CiAgICAgIDx0Ym9keT4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+V1RJL0NMPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+UGV0csOzbGVvIFdUSTwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJjbC1wIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5HT0xEPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+T3VybzwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJnb2xkLXAiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlNJTFZFUjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlByYXRhPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9InNpbHZlci1wIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5DT1BQRVI8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5Db2JyZTwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJjb3BwZXItcCI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgPC90Ym9keT4KICAgIDwvdGFibGU+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InRibC13cmFwIj4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5CaXRjb2luPC9zcGFuPjwvZGl2PgogICAgPHRhYmxlIGNsYXNzPSJ0YmwtbWt0Ij4KICAgICAgPHRoZWFkPjx0cj48dGg+QXRpdm88L3RoPjx0aCBjbGFzcz0iciI+w5psdGltbzwvdGg+PHRoIGNsYXNzPSJyIj5WYXJpYcOnw6NvPC90aD48dGggY2xhc3M9InIiPkluZm88L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5CVEMvVVNEPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+Qml0Y29pbiBTcG90PC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJ0Yy1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJidGMtYyI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJUQyBSU0k8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5SU0kgU2VtYW5hbDwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJidGMtcnNpIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PHRkIGNsYXNzPSJyIj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkZ1bmRpbmc8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5UYXhhIDhoIEJUQzwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJidGMtZnVuZCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48L3RkPjx0ZCBjbGFzcz0iciI+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5GZWFyICZhbXA7IEdyZWVkPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+w41uZGljZSBzZW50aW1lbnRvPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImZnLXZhbCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gaWQ9ImZnLWxibCIgc3R5bGU9ImZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKSI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgPC90Ym9keT4KICAgIDwvdGFibGU+CiAgPC9kaXY+CiAgPGZvb3Rlcj48c3BhbiBpZD0iZm9vdGVyLXRpbWUiPuKAlDwvc3Bhbj48c3Bhbj5UcmFkZXIgRGVzayB2MTEuMjwvc3Bhbj48L2Zvb3Rlcj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBJTkRJQ0FET1JFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1pbmRpY2Fkb3JlcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5DaWNsbyBCaXRjb2luPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWN5Y2xlLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjE0cHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxNTBweDtnYXA6MTBweDttYXJnaW46MTRweCAwIj4KICAgIDxkaXYgaWQ9ImZnLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHgiPkNhcnJlZ2FuZG8gRmVhciAmYW1wOyBHcmVlZC4uLjwvZGl2PjwvZGl2PgogICAgPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHg7dGV4dC1hbGlnbjpjZW50ZXIiPgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo2cHg7Zm9udC13ZWlnaHQ6NjAwO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4Ij5CVEMvVVNEPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJidGMtaW5kLXAiPuKAlDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+QlRDIFNlbWFuYWw8L2Rpdj4KICA8ZGl2IGlkPSJidGMtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpmbGV4LWVuZDttYXJnaW4tYm90dG9tOjEwcHgiPgogICAgPGJ1dHRvbiBvbmNsaWNrPSJ0b2dnbGVBbGxJbmQoKSIgaWQ9ImJ0bi1hbGwtaW5kIiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzMpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjb2xvcjp2YXIoLS1hY2NlbnQpO3BhZGRpbmc6NXB4IDE0cHg7Zm9udC1zaXplOjExcHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweCI+4oiSIFJlY29saGVyIFRvZG9zPC9idXR0b24+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iaW5kLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWhkciIgb25jbGljaz0idG9nSW5kKCdwZXRyNCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5QRVRSNCDigJQgUGV0cm9icmFzIFBOPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPlBldHLDs2xlbyAmYW1wOyBHw6FzIMK3IGNsaXF1ZSBwYXJhIGV4cGFuZGlyL3JlY29saGVyPC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHgiPjxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxM3B4IiBvbmNsaWNrPSJldmVudC5zdG9wUHJvcGFnYXRpb24oKTtybCgncGV0cjQnKSI+4oa7PC9zcGFuPjxzcGFuIGlkPSJhci1pbmQtcGV0cjQiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJwZXRyNC1pbmQtd3JhcCI+PGRpdiBpZD0icGV0cjQtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iaW5kLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWhkciIgb25jbGljaz0idG9nSW5kKCd2YWxlMycpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5WQUxFMyDigJQgVmFsZSBPTjwvZGl2PjxkaXYgY2xhc3M9ImluZC1hY2Mtc3ViIj5NaW5lcmHDp8OjbyDCtyBjbGlxdWUgcGFyYSBleHBhbmRpci9yZWNvbGhlcjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij48c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTNweCIgb25jbGljaz0iZXZlbnQuc3RvcFByb3BhZ2F0aW9uKCk7cmwoJ3ZhbGUzJykiPuKGuzwvc3Bhbj48c3BhbiBpZD0iYXItaW5kLXZhbGUzIj7ilrw8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtYm9keSBvcGVuIiBpZD0idmFsZTMtaW5kLXdyYXAiPjxkaXYgaWQ9InZhbGUzLWluZCI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImluZC1hY2MiPgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1oZHIiIG9uY2xpY2s9InRvZ0luZCgnYmJhczMnKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy10aXRsZSI+QkJBUzMg4oCUIEJhbmNvIGRvIEJyYXNpbCBPTjwvZGl2PjxkaXYgY2xhc3M9ImluZC1hY2Mtc3ViIj5CYW5jb3MgwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdiYmFzMycpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1iYmFzMyI+4pa8PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWJvZHkgb3BlbiIgaWQ9ImJiYXMzLWluZC13cmFwIj48ZGl2IGlkPSJiYmFzMy1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ2F4aWEzJykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9ImluZC1hY2MtdGl0bGUiPkFYSUEzIOKAlCBBdXJlbiBFbmVyZ2lhIE9OPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPkVuZXJnaWEgRWzDqXRyaWNhIMK3IGNsaXF1ZSBwYXJhIGV4cGFuZGlyL3JlY29saGVyPC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHgiPjxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxM3B4IiBvbmNsaWNrPSJldmVudC5zdG9wUHJvcGFnYXRpb24oKTtybCgnYXhpYTMnKSI+4oa7PC9zcGFuPjxzcGFuIGlkPSJhci1pbmQtYXhpYTMiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJheGlhMy1pbmQtd3JhcCI+PGRpdiBpZD0iYXhpYTMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iaW5kLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWhkciIgb25jbGljaz0idG9nSW5kKCdyb3hvMzQnKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy10aXRsZSI+Uk9YTzM0IOKAlCBOdWJhbmsgQkRSPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPkZpbnRlY2ggwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdyb3hvMzQnKSI+4oa7PC9zcGFuPjxzcGFuIGlkPSJhci1pbmQtcm94bzM0Ij7ilrw8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtYm9keSBvcGVuIiBpZD0icm94bzM0LWluZC13cmFwIj48ZGl2IGlkPSJyb3hvMzQtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CjwvZGl2PgoKPCEtLSDilZDilZAgUE9TScOHw5VFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1wb3NpY29lcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5PcGVyYcOnw7VlcyBBdGl2YXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+UGV0cm9icmFzIFBOIMK3IENhbGwgVmVuZGlkYSDCtyBQRVRSTDMxOSDCtyBWZW5jIDE3LzEyLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5QRVRSNDwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9InB0LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9InB0LWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TdHJpa2UgKFBFVFJMMzE5KTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgMzAsODU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByZcOnbyB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InB0LWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTcvMTIvMjAyNiDCtyA8c3BhbiBpZD0icHQtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj40Myw0JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj45LDQlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBNQyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayIgaWQ9InB0LW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhbGwgc2VyIGV4ZXJjaWRhPC9kaXY+CiAgICAgIDxkaXYgaWQ9InB0LW1jLWwiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEycHgiPkNhbGN1bGFuZG8gNS4wMDAgY2Vuw6FyaW9zLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9InB0LW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gZXhlcmNlcjwvZGl2PjxkaXYgY2xhc3M9Iml2IiBpZD0icHQtbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icHQtbWMtdiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4O2xpbmUtaGVpZ2h0OjEuNSIgaWQ9InB0LW1jLWkiPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIj4KICAgIDxkaXYgY2xhc3M9InBsIj5WYWxlIE9OIMK3IENhbGwgVmVuZGlkYSDCtyBWQUxFQjU3NCDCtyBWZW5jIDE4LzAyLzIwMjc8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5WQUxFMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9InZsLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9InZsLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TdHJpa2UgKFZBTEVCNTc0KTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNTcsNDA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByZcOnbyB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InZsLWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTgvMDIvMjAyNyDCtyA8c3BhbiBpZD0idmwtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj43MSwyJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4xNCwyJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gTUMgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siIGlkPSJ2bC1tYy1ydCI+Y2FsYy4uLjwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnIj4KICAgICAgPGRpdiBjbGFzcz0ic2d0Ij7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWxsIHNlciBleGVyY2lkYTwvZGl2PgogICAgICA8ZGl2IGlkPSJ2bC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJ2bC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIGV4ZXJjZXI8L2Rpdj48ZGl2IGNsYXNzPSJpdiIgaWQ9InZsLW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InZsLW1jLXYiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJ2bC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+QVhJQTMgKEEpIMK3IEJpZGlyZWNpb25hbCDCtyBWZW5jIDE0LzA5LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5BWElBMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9ImEzLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9ImEzLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA0Myw1MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S1VPICgrMjYsNiUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA2OCw3Njwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+R2FuaG8gcy8gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIGMvIGJhci4gYWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+KzQlIGZpeG88L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4xNC8wOS8yMDI2IMK3IDxzcGFuIGlkPSJhMy1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1rZG8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RGlzdC4gS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzLWt1byI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzLXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgQ2Vuw6FyaW9zIGJhcnJlaXJhPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzLW1jLWwiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEycHgiPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0iYTMtbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siIGlkPSJhMy1tYy1uYiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTMtbWMta3UiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEJhaXhhIEtETzwvZGl2PjxkaXYgY2xhc3M9Iml2IGRvd24iIGlkPSJhMy1tYy1rZCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTMtbWMtdm8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweCIgaWQ9ImEzLW1jLWkiPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIj4KICAgIDxkaXYgY2xhc3M9InBsIj5BWElBMyAoQikgwrcgQmlkaXJlY2lvbmFsIElPTiBJdGHDuiDCtyBWZW5jIDAyLzEwLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5BWElBMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9ImEzYi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJhM2ItYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPktETyAoLTIwJSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDQwLDUyPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LVU8gKCsyNCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA2Miw4MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+R2FuaG8gcy8gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIGMvIGJhci4gYWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+KzQlIGZpeG8gKDEyLDMzJSBhLmEuKTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjAyLzEwLzIwMjYgwrcgPHNwYW4gaWQ9ImEzYi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhM2Ita2RvIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtVTzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhM2Ita3VvIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgQ2Vuw6FyaW9zIGJhcnJlaXJhPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzYi1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzYi1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlNlbSBCYXJyZWlyYSDinIU8L2Rpdj48ZGl2IGNsYXNzPSJpdiBvayIgaWQ9ImEzYi1tYy1uYiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTNiLW1jLWt1Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpdiBkb3duIiBpZD0iYTNiLW1jLWtkIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJhM2ItbWMtdm8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweCIgaWQ9ImEzYi1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+Uk9YTzM0IMK3IEJEUiBOdWJhbmsgwrcgTGFuw6dhbWVudG8gQ29iZXJ0byDCtyBST1hPRzEwNSDCtyBWZW5jIDE2LzA3LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5ST1hPMzQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJyeC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJyeC1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChST1hPRzEwNSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDEwLDUwIMK3IElUTSDimqA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByZcOnbyB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InJ4LWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTYvMDcvMjAyNiDCtyA8c3BhbiBpZD0icngtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4zMywyJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RGVsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjAsNjQzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBCJmFtcDtTIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSI+NjAsNCUg4pqgPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBNQyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9InJ4LW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5PYmpldGl2bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPkZlY2hhciBhYmFpeG8gZGUgUiQgMTAsNTA8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gc3VjZXNzbzwvZGl2PgogICAgICA8ZGl2IGlkPSJyeC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9InJ4LW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gU3VjZXNzbzwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIiBpZD0icngtbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkNhbGwgRXhlcmNpZGE8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icngtbWMtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPktETyBBdGluZ2lkbzwvZGl2PjxkaXYgY2xhc3M9Iml2IGRvd24iIGlkPSJyeC1tYy1rIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJyeC1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJyeC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjIwcHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiPgogICAgPGRpdiBjbGFzcz0icGwiPkJhbmNvIGRvIEJyYXNpbCBPTiDCtyBMYW7Dp2FtZW50byBDb2JlcnRvIMK3IEJCQVNIMjEgwrcgVmVuYyAyMC8wOC8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwdCI+QkJBUzM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJiYi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJiYi1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChCQkFTSDIxKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgMjEsNjUgwrcgSVRNPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJiYi1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjIwLzA4LzIwMjYgwrcgPHNwYW4gaWQ9ImJiLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MjcsMSU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRlbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MCwyNDk8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIEImYW1wO1MgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MjEsMyU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIE1DIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIiBpZD0iYmItbWMtcnQiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPk9iamV0aXZvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+RmVjaGFyIGFiYWl4byBkZSBSJCAyMSw2NTwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnIj4KICAgICAgPGRpdiBjbGFzcz0ic2d0Ij7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWxsIHNlciBleGVyY2lkYTwvZGl2PgogICAgICA8ZGl2IGlkPSJiYi1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJiYi1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIGV4ZXJjZXI8L2Rpdj48ZGl2IGNsYXNzPSJpdiIgaWQ9ImJiLW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImJiLW1jLXYiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJiYi1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyIgc3R5bGU9Im9wYWNpdHk6LjU7Ym9yZGVyLWNvbG9yOnZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQtY29sb3I6dmFyKC0tbXV0ZWQpIj4KICAgIDxkaXYgY2xhc3M9InB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxNnB4Ij5BWElBMyBTaG9ydCBTdHJhbmdsZTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkNhbGwgVi4gQVhJQUk1MDU8L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij5SJCA1MCw1MDwvc3Bhbj48L2Rpdj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj7inIUgQcOnw7VlcyBsaWJlcmFkYXM8L3NwYW4+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjp2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLW11dGVkKSI+CiAgICA8ZGl2IGNsYXNzPSJwdCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTZweCI+Uk9YTzM0IFByZWZpeGFkbyA3LDElPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+PGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RW5jZXJyYWRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MDQvMDYvMjAyNjwvc3Bhbj48L2Rpdj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj7inIUgfjUsMTclICg3MiUgZG8gYWx2byk8L3NwYW4+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CjwvZGl2PgoKPCEtLSDilZDilZAgQ0FMRU5Ew4FSSU8g4pWQ4pWQIC0tPgo8ZGl2IGlkPSJ0YWItY2FsZW5kYXJpbyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO21hcmdpbi1ib3R0b206MTRweCI+CiAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NTAwIj7wn4e68J+HuCDwn4en8J+HtyDwn4eq8J+HuiDwn4es8J+HpyDwn4eo8J+HsyDwn4ev8J+HtSDwn4ep8J+HqiDCtyBJbXBhY3RvIE3DqWRpbys8L2Rpdj4KICAgIDxidXR0b24gb25jbGljaz0ibG9hZENhbCgpIiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2JvcmRlcjpub25lO2NvbG9yOiNmZmY7cGFkZGluZzo4cHggMThweDtmb250LXNpemU6MTJweDtjdXJzb3I6cG9pbnRlcjtmb250LWZhbWlseTppbmhlcml0O2ZvbnQtd2VpZ2h0OjcwMDtsZXR0ZXItc3BhY2luZzouNXB4Ij7ihrsgQXR1YWxpemFyPC9idXR0b24+CiAgPC9kaXY+CiAgPGRpdiBpZD0iY2FsLXN0IiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206OHB4Ij48L2Rpdj4KICA8ZGl2IGlkPSJjYWwtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MjRweDt0ZXh0LWFsaWduOmNlbnRlciI+Q2xpcXVlIGVtIEF0dWFsaXphcjwvZGl2PjwvZGl2Pgo8L2Rpdj4KCjxzY3JpcHQ+CmNvbnN0IEI9J2h0dHBzOi8vdHJhZGVyLWRlc2sub25yZW5kZXIuY29tJzsKY29uc3QgU0VHPXsKICBmaW46WydJVFVCNCcsJ0JCREM0JywnQkJBUzMnLCdTQU5CMTEnLCdCM1NBMycsJ0JQQUMxMScsJ0lUU0E0JywnQlJTUjYnLCdBQkNCNCcsJ0JNR0I0J10sCiAgcGV0OlsnUEVUUjQnLCdQRVRSMycsJ1BSSU8zJywnQlJBVjMnLCdWQkJSMycsJ0NTQU4zJywnUkVDVjMnLCdVR1BBMycsJ1NFUUwzJywnR0dCUjQnXSwKICBtaW46WydWQUxFMycsJ0dHQlI0JywnQ1NOQTMnLCdVU0lNNScsJ0JSQVA0JywnRkVTQTQnLCdDTUlOMycsJ0NCQVYzJywnR09BVTQnLCdQR01OMyddLAogIG1hdDpbJ1NVWkIzJywnS0xCTjExJywnRFhDTzMnLCdVTklQNicsJ1JBTkkzJywnT1JWUjMnLCdTTVRPMycsJ0ZSQVMzJywnTFBTQjMnLCdDU1VEMyddLAogIHV0aTpbJ0FYSUEzJywnRVFUTDMnLCdDUEZFMycsJ1NCU1AzJywnQ01JRzQnLCdFTkdJMTEnLCdUQUVFMTEnLCdBVVJFMycsJ0VHSUUzJywnQ1BMRTMnXSwKICBjYzogWydSRU5UMycsJ0xSRU4zJywnTUdMVTMnLCdDWVJFMycsJ01SVkUzJywnQVpaQTMnLCdWSVZBMycsJ1NCRkczJywnWURVUTMnLCdNT1ZJMyddLAogIGNuOiBbJ0FCRVYzJywnSkJTUzMnLCdCUkZTMycsJ05BVFUzJywnTURJQTMnLCdCRUVGMycsJ1NMQ0UzJywnTVRSRTMnLCdDQU1MMycsJ1BDQVIzJ10sCiAgc2F1OlsnUkRPUjMnLCdIQVBWMycsJ0ZMUlkzJywnREFTQTMnLCdRVUFMMycsJ09OQ08zJywnUE5WTDMnLCdPRFBWMycsJ01BVEQzJywnQUFMUjMnXSwKICBpbmQ6WydXRUdFMycsJ0VNQlIzJywnUkFJTDMnLCdUR01BMycsJ1JPTUkzJywnVkxJRDMnLCdUVVBZMycsJ0lSQlIzJywnUE9NTzQnLCdMQVZWMyddLAogIHRpdDpbJ1ZJVlQzJywnVElNUzMnLCdUT1RWUzMnLCdQT1NJMycsJ01MQVMzJywnQU5JTTMnLCdJTlRCMycsJ0xXU0EzJywnQ0FTSDMnLCdPSUJSMyddLAp9Owpjb25zdCBVU1NFRz17CiAgbTc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnR09PR0wnLCdNRVRBJywnVFNMQSddLAogIG5xOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQ09TVCcsJ05GTFgnLCdRQ09NJywnQU1EJywnQURCRScsJ0lOVEMnLCdDU0NPJ10sCiAgc3A6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdCUksuQicsJ0pQTScsJ0xMWScsJ1YnLCdVTkgnLCdYT00nLCdNQScsJ05GTFgnLCdQRycsJ0pOSicsJ0hEJywnQkFDJ10sCiAgZGo6WydVTkgnLCdHUycsJ0hEJywnU0hXJywnQ0FUJywnQVhQJywnTUNEJywnQU1HTicsJ1YnLCdUUlYnLCdJQk0nLCdKUE0nLCdIT04nLCdDUk0nLCdDVlgnLCdBQVBMJywnTVNGVCcsJ0RJUycsJ05LRScsJ0JBJ10KfTsKY29uc3QgZlI9dj0+diE9bnVsbD8nUiQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlU9dj0+diE9bnVsbD8nVVMkICcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21pbmltdW1GcmFjdGlvbkRpZ2l0czoyLG1heGltdW1GcmFjdGlvbkRpZ2l0czoyfSk6J+KAlCc7CmNvbnN0IGZQPXY9PnYhPW51bGw/TnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CmZ1bmN0aW9uIEUoaWQsdCl7Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuO2UudGV4dENvbnRlbnQ9dDtlLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CmZ1bmN0aW9uIENoVGJsKGlkVixpZFBjdCxub3cscHJldix0cCl7CiAgY29uc3QgZGlmZj1ub3ctcHJldixwY3Q9KGRpZmYvTWF0aC5hYnMocHJldnx8MSkqMTAwKSxzZz1kaWZmPj0wPycrJzonJzsKICBjb25zdCBjbHM9ZGlmZj4wPydjaGcgY2hnLXVwJzpkaWZmPDA/J2NoZyBjaGctZG4nOidjaGcgY2hnLWZsJzsKICBsZXQgdmFyU3RyPScnOwogIGlmKHRwPT09J3InKXZhclN0cj1zZysnUiQgJytNYXRoLmFicyhkaWZmKS50b0ZpeGVkKDIpOwogIGVsc2UgaWYodHA9PT0ndScpdmFyU3RyPXNnK01hdGguYWJzKGRpZmYpLnRvRml4ZWQoMik7CiAgZWxzZSB2YXJTdHI9c2crTWF0aC5hYnMoZGlmZikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KTsKICBjb25zdCBwY3RTdHI9c2crcGN0LnRvRml4ZWQoMikrJyUnOwogIGNvbnN0IGV2PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkVik7aWYoZXYpe2V2LnRleHRDb250ZW50PXZhclN0cjtldi5jbGFzc05hbWU9Y2xzO30KICBjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZFBjdCk7aWYoZXApe2VwLnRleHRDb250ZW50PXBjdFN0cjtlcC5jbGFzc05hbWU9Y2xzO30KfQpmdW5jdGlvbiBDaChpZCxuLHAsdHApewogIGNvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKCFlKXJldHVybjsKICBjb25zdCBkPW4tcCxwYz0oZC9NYXRoLmFicyhwfHwxKSoxMDApLnRvRml4ZWQoMiksc2c9ZD49MD8nKyc6Jyc7CiAgaWYodHA9PT0ncicpZS50ZXh0Q29udGVudD1zZysnUiQgJytNYXRoLmFicyhkKS50b0ZpeGVkKDIpKycgKCcrc2crcGMrJyUpJzsKICBlbHNlIGlmKHRwPT09J3UnKWUudGV4dENvbnRlbnQ9c2crZC50b0ZpeGVkKDIpKycgKCcrc2crcGMrJyUpJzsKICBlbHNlIGUudGV4dENvbnRlbnQ9c2crTWF0aC5hYnMoZCkudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnICgnK3NnK3BjKyclKSc7CiAgZS5jbGFzc05hbWU9J2NjICcrKGQ+MD8nY2hnLXVwJzpkPDA/J2NoZy1kbic6J2NoZy1mbCcpOwp9CmZ1bmN0aW9uIHN3KHQsZWwpewogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy50YWInKS5mb3JFYWNoKHg9PnguY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJykpOwogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy50YWItY29udGVudCcpLmZvckVhY2goeD0+eC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RhYi0nK3QpLmNsYXNzTGlzdC5hZGQoJ2FjdGl2ZScpOwogIGlmKGVsKWVsLmNsYXNzTGlzdC5hZGQoJ2FjdGl2ZScpOwogIGlmKHQ9PT0naW5kaWNhZG9yZXMnJiYhd2luZG93Ll9JTCl7d2luZG93Ll9JTD10cnVlO2xvYWRJbmQoKTt9CiAgaWYodD09PSdjYWxlbmRhcmlvJylsb2FkQ2FsKCk7Cn0KZnVuY3Rpb24gdGcoaWQpewogIGNvbnN0IGI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NiLScraWQpLGE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLScraWQpOwogIGlmKCFiKXJldHVybjtjb25zdCBvcD1iLnN0eWxlLmRpc3BsYXkhPT0nYmxvY2snOwogIGIuc3R5bGUuZGlzcGxheT1vcD8nYmxvY2snOidub25lJzsKICBpZihhKWEudGV4dENvbnRlbnQ9b3A/J+KWsic6J+KWvCc7CiAgaWYob3AmJiFiLmRhdGFzZXQubCl7Yi5kYXRhc2V0Lmw9JzEnO2xvYWRTZWcoaWQpO30KfQoKYXN5bmMgZnVuY3Rpb24gbG9hZFNlZyhpZCl7CiAgY29uc3QgZz1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZy0nK2lkKTtpZighZylyZXR1cm47CiAgY29uc3QgcGZ4PWlkKydfJzsKICBpZihVU1NFR1tpZF0pewogICAgY29uc3QgdGtzPVVTU0VHW2lkXTsKICAgIGcuaW5uZXJIVE1MPXRrcy5tYXAodD0+e2NvbnN0IHRpZD10LnJlcGxhY2UoL1teYS16QS1aMC05XS9nLCdfJyk7cmV0dXJuICc8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImNsIj5VUzwvZGl2PjxkaXYgY2xhc3M9ImNuIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSInK3BmeCt0aWQrJ19wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9IicrcGZ4K3RpZCsnX2MiPuKAlDwvZGl2PjwvZGl2Pic7fSkuam9pbignJyk7CiAgICB0cnl7CiAgICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL3VzL3F1b3Rlcz90aWNrZXJzPScrdGtzLmpvaW4oJywnKSk7CiAgICAgIGlmKCFyLm9rKXJldHVybjsKICAgICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgICAgT2JqZWN0LmVudHJpZXMoZCkuZm9yRWFjaCgoW3Qsdl0pPT57CiAgICAgICAgY29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTsKICAgICAgICBjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfcCcpOwogICAgICAgIGlmKGVwJiZ2LnByaWNlKXtlcC50ZXh0Q29udGVudD0nJCcrTnVtYmVyKHYucHJpY2UpLnRvRml4ZWQoMik7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICBpZih2LnByaWNlJiZ2LnByZXYpQ2gocGZ4K3RpZCsnX2MnLHYucHJpY2Usdi5wcmV2LCd1Jyk7CiAgICAgIH0pOwogICAgfWNhdGNoKGUpe30KICAgIHJldHVybjsKICB9CiAgY29uc3QgdGtzPVNFR1tpZF07aWYoIXRrcylyZXR1cm47CiAgZy5pbm5lckhUTUw9dGtzLm1hcCh0PT57Y29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTtyZXR1cm4gJzxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkIzPC9kaXY+PGRpdiBjbGFzcz0iY24iPicrdCsnPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0iJytwZngrdGlkKydfYyI+4oCUPC9kaXY+PC9kaXY+Jzt9KS5qb2luKCcnKTsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy90di9icmF6aWwnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzLm1hcCh0PT4nQk1GQk9WRVNQQTonK3QpfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pOwogICAgaWYoIXIub2spdGhyb3cgbmV3IEVycm9yKCdUViBmYWlsJyk7CiAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgY29uc3QgbG9hZGVkPW5ldyBTZXQoKTsKICAgIChkLmRhdGF8fFtdKS5mb3JFYWNoKHg9PnsKICAgICAgY29uc3QgdD14LnMucmVwbGFjZSgnQk1GQk9WRVNQQTonLCcnKS50b0xvd2VyQ2FzZSgpOwogICAgICBjb25zdFtjLGNhXT14LmR8fFtdOwogICAgICBpZihjIT1udWxsKXsKICAgICAgICBjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdCsnX3AnKTsKICAgICAgICBpZihlcCl7ZXAudGV4dENvbnRlbnQ9ZlIoYyk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO2xvYWRlZC5hZGQodCk7fQogICAgICAgIENoKHBmeCt0KydfYycsYyxjLShjYXx8MCksJ3InKTsKICAgICAgfQogICAgfSk7CiAgICAvLyBGYWxsYmFjayB2aWEgYnJhcGkgcGFyYSB0aWNrZXJzIHF1ZSBUViBuw6NvIHJldG9ybm91CiAgICBjb25zdCBtaXNzaW5nPXRrcy5maWx0ZXIodD0+IWxvYWRlZC5oYXModC50b0xvd2VyQ2FzZSgpKSk7CiAgICBpZihtaXNzaW5nLmxlbmd0aD4wKXsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0IHJiPWF3YWl0IGZldGNoKEIrJy90di9icmF6aWwnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgICBib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOm1pc3NpbmcubWFwKHQ9PidCTUZCT1ZFU1BBOicrdCl9LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7CiAgICAgICAgLy8gU2VndW5kYSB0ZW50YXRpdmEgaW1lZGlhdGEKICAgICAgfWNhdGNoKGUyKXt9CiAgICAgIC8vIEZhbGxiYWNrIGluZGl2aWR1YWwgdmlhIC9pbmRpY2F0b3JzCiAgICAgIGZvcihjb25zdCB0IG9mIG1pc3NpbmcpewogICAgICAgIHRyeXsKICAgICAgICAgIGNvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdCsnLlNBJyk7CiAgICAgICAgICBpZighcjIub2spY29udGludWU7CiAgICAgICAgICBjb25zdCBkMj1hd2FpdCByMi5qc29uKCk7CiAgICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICAgIGNvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7CiAgICAgICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19wJyk7CiAgICAgICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mUihkMi5wcmVjb19hdHVhbCk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICAgICAgaWYoZDIucHJlY29fYW50ZXJpb3IpQ2gocGZ4K3RpZCsnX2MnLGQyLnByZWNvX2F0dWFsLGQyLnByZWNvX2FudGVyaW9yLCdyJyk7CiAgICAgICAgICB9CiAgICAgICAgfWNhdGNoKGUyKXt9CiAgICAgIH0KICAgIH0KICB9Y2F0Y2goZSl7CiAgICAvLyBUViBmYWxob3UgY29tcGxldGFtZW50ZSDigJQgZmFsbGJhY2sgcGFyYSB0b2RvcyB2aWEgL2luZGljYXRvcnMKICAgIGZvcihjb25zdCB0IG9mIHRrcy5zbGljZSgwLDYpKXsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdCsnLlNBJyk7CiAgICAgICAgaWYoIXIyLm9rKWNvbnRpbnVlOwogICAgICAgIGNvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICBjb25zdCB0aWQ9dC50b0xvd2VyQ2FzZSgpOwogICAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mUihkMi5wcmVjb19hdHVhbCk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICB9CiAgICAgIH1jYXRjaChlMil7fQogICAgfQogIH0KfQoKZnVuY3Rpb24gZXhwYW5kQWxsKCl7CiAgY29uc3QgYnRuPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidG4tZXhwYW5kJyk7CiAgY29uc3Qgc2Vncz1bJ2ZpbicsJ3BldCcsJ21pbicsJ21hdCcsJ3V0aScsJ2NjJywnY24nLCdzYXUnLCdpbmQnLCd0aXQnXTsKICBjb25zdCBhbnlPcGVuPXNlZ3Muc29tZShpZD0+ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NiLScraWQpPy5zdHlsZS5kaXNwbGF5PT09J2Jsb2NrJyk7CiAgc2Vncy5mb3JFYWNoKGlkPT57CiAgICBjb25zdCBiPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYi0nK2lkKSxhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci0nK2lkKTsKICAgIGlmKCFiKXJldHVybjsKICAgIGlmKGFueU9wZW4pe2Iuc3R5bGUuZGlzcGxheT0nbm9uZSc7aWYoYSlhLnRleHRDb250ZW50PSfilrwnO30KICAgIGVsc2V7CiAgICAgIGIuc3R5bGUuZGlzcGxheT0nYmxvY2snO2lmKGEpYS50ZXh0Q29udGVudD0n4payJzsKICAgICAgaWYoIWIuZGF0YXNldC5sKXtiLmRhdGFzZXQubD0nMSc7bG9hZFNlZyhpZCk7fQogICAgfQogIH0pOwogIGlmKGJ0bilidG4udGV4dENvbnRlbnQ9YW55T3Blbj8nKyBFeHBhbmRpciBUb2Rvcyc6J+KIkiBSZWNvbGhlciBUb2Rvcyc7Cn0KZnVuY3Rpb24gdG9nSW5kKGlkKXsKICBjb25zdCBib2R5PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKyctaW5kLXdyYXAnKTsKICBjb25zdCBhcnI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLWluZC0nK2lkKTsKICBpZighYm9keSlyZXR1cm47CiAgY29uc3Qgb3Blbj1ib2R5LmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpOwogIGJvZHkuY2xhc3NMaXN0LnRvZ2dsZSgnb3BlbicsIW9wZW4pOwogIGlmKGFycilhcnIudGV4dENvbnRlbnQ9b3Blbj8n4pa2Jzon4pa8JzsKfQpmdW5jdGlvbiB0b2dnbGVBbGxJbmQoKXsKICBjb25zdCBpZHM9WydwZXRyNCcsJ3ZhbGUzJywnYmJhczMnLCdheGlhMycsJ3JveG8zNCddOwogIGNvbnN0IGJ0bj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRuLWFsbC1pbmQnKTsKICBjb25zdCBhbnlPcGVuPWlkcy5zb21lKGlkPT5kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZC13cmFwJyk/LmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpKTsKICBpZHMuZm9yRWFjaChpZD0+ewogICAgY29uc3QgYm9keT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZC13cmFwJyk7CiAgICBjb25zdCBhcnI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLWluZC0nK2lkKTsKICAgIGlmKGJvZHkpe2JvZHkuY2xhc3NMaXN0LnRvZ2dsZSgnb3BlbicsIWFueU9wZW4pO2lmKGFycilhcnIudGV4dENvbnRlbnQ9YW55T3Blbj8n4pa2Jzon4pa8Jzt9CiAgfSk7CiAgaWYoYnRuKWJ0bi50ZXh0Q29udGVudD1hbnlPcGVuPycrIEV4cGFuZGlyIFRvZG9zJzon4oiSIFJlY29saGVyIFRvZG9zJzsKfQphc3luYyBmdW5jdGlvbiBmSEwoKXsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7CiAgICBpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IGJwPXBhcnNlRmxvYXQoZC5CVEN8fDApOwogICAgaWYoYnA+MCl7RSgnYnRjLXAnLGZVKGJwKSk7Q2goJ2J0Yy1jJyxicCxicCowLjk5LCd1Jyk7fQogICAgdHJ5ewogICAgICBjb25zdCByMj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcycsZGV4Oid4eXonfSl9KTsKICAgICAgaWYocjIub2spe2NvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICBpZihkMlsneHl6OkNMJ10pRSgnY2wtcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDTCddKS50b0ZpeGVkKDIpKTsKICAgICAgICBpZihkMlsneHl6OkdPTEQnXSlFKCdnb2xkLXAnLCckJytOdW1iZXIoZDJbJ3h5ejpHT0xEJ10pLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpOwogICAgICAgIGlmKGQyWyd4eXo6U0lMVkVSJ10pRSgnc2lsdmVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6U0lMVkVSJ10pLnRvRml4ZWQoMikpOwogICAgICAgIGlmKGQyWyd4eXo6Q09QUEVSJ10pRSgnY29wcGVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q09QUEVSJ10pLnRvRml4ZWQoMykpO30KICAgIH1jYXRjaChlKXt9CiAgfWNhdGNoKGUpe30KfQphc3luYyBmdW5jdGlvbiBmVFYoKXsKICBjb25zdCBvdXQ9e307CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOlsnQk1GQk9WRVNQQTpQRVRSNCcsJ0JNRkJPVkVTUEE6SVRVQjQnLCdCTUZCT1ZFU1BBOlZBTEUzJywnQk1GQk9WRVNQQTpCQkRDNCcsJ0JNRkJPVkVTUEE6QUJFVjMnLCdCTUZCT1ZFU1BBOkJCQVMzJywnQk1GQk9WRVNQQTpXRUdFMycsJ0JNRkJPVkVTUEE6SUJPViddfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pOwogICAgaWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTsoZC5kYXRhfHxbXSkuZm9yRWFjaCh4PT57Y29uc3RbYyxjYV09eC5kfHxbXTtpZihjIT1udWxsKW91dFt4LnNdPXtwOmMsdjpjLShjYXx8MCl9O30pO30KICB9Y2F0Y2goZSl7fQogIHRyeXtjb25zdCBycj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy9ST1hPMzQuU0EnKTtpZihyci5vayl7Y29uc3QgZGQ9YXdhaXQgcnIuanNvbigpO2lmKGRkLnByZWNvX2F0dWFsKXtFKCdyb3hvMzRxLXAnLGZSKGRkLnByZWNvX2F0dWFsKSk7Q2goJ3JveG8zNHEtYycsZGQucHJlY29fYXR1YWwsKGRkLnByZWNvX2FudGVyaW9yfHxkZC5wcmVjb19hdHVhbCowLjk5KSwncicpO319fWNhdGNoKGUpe30KICByZXR1cm4gb3V0Owp9CmFzeW5jIGZ1bmN0aW9uIGZGdXQoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvZnV0dXJlcycpO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkZ1bmQoKXsKICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9mYXBpLmJpbmFuY2UuY29tL2ZhcGkvdjEvcHJlbWl1bUluZGV4P3N5bWJvbD1CVENVU0RUJyk7aWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtFKCdidGMtZnVuZCcsKHBhcnNlRmxvYXQoZC5sYXN0RnVuZGluZ1JhdGV8fDApKjEwMCkudG9GaXhlZCg0KSsnJScpO3JldHVybjt9fWNhdGNoKGUpe30KICB0cnl7Y29uc3QgcjI9YXdhaXQgZmV0Y2goQisnL2JpbmFuY2UvZnVuZGluZycpO2lmKCFyMi5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByMi5qc29uKCk7aWYoZC5sYXN0RnVuZGluZ1JhdGUpRSgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlKSoxMDApLnRvRml4ZWQoNCkrJyUnKTt9Y2F0Y2goZSl7fQp9CmZ1bmN0aW9uIGRvTWFjcm8odHYsZnQpewogIFtbJ1BFVFI0JywncGV0cjRxJ10sWydJVFVCNCcsJ2l0dWI0cSddLFsnVkFMRTMnLCd2YWxlM3EnXSxbJ0JCREM0JywnYmJkYzRxJ10sWydBQkVWMycsJ2FiZXYzcSddLFsnQkJBUzMnLCdiYmFzM3EnXSxbJ1dFR0UzJywnd2VnZTNxJ11dLmZvckVhY2goKFt0LGlkXSk9PnsKICAgIGNvbnN0IGQ9dHZbJ0JNRkJPVkVTUEE6Jyt0XTtpZihkKXtFKGlkKyctcCcsZlIoZC5wKSk7Q2hUYmwoaWQrJy12JyxpZCsnLWMnLGQucCxkLnYsJ3InKTt9CiAgfSk7CiAgY29uc3QgaWI9dHZbJ0JNRkJPVkVTUEE6SUJPViddO2lmKGliKXtFKCdpYm92LXAnLGZQKGliLnApKTtDaFRibCgnaWJvdi12JywnaWJvdi1jJyxpYi5wLGliLnYsJ3AnKTt9CiAgaWYoZnQpewogICAgY29uc3QgYWY9KGlkLHYpPT57Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoZSl7ZS50ZXh0Q29udGVudD12O2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO319OwogICAgaWYoZnQuZGppPy5wcmljZSl7YWYoJ2RqaS1wJyxmUChmdC5kamkucHJpY2UpKTtDaFRibCgnZGppLXYnLCdkamktYycsZnQuZGppLnByaWNlLGZ0LmRqaS5wcmV2LCdwJyk7fQogICAgaWYoZnQuZXNmPy5wcmljZSl7YWYoJ2VzZi1wJyxmUChmdC5lc2YucHJpY2UpKTtDaFRibCgnZXNmLXYnLCdlc2YtYycsZnQuZXNmLnByaWNlLGZ0LmVzZi5wcmV2LCdwJyk7fQogICAgaWYoZnQubnFmPy5wcmljZSl7YWYoJ25xZi1wJyxmUChmdC5ucWYucHJpY2UpKTtDaFRibCgnbnFmLXYnLCducWYtYycsZnQubnFmLnByaWNlLGZ0Lm5xZi5wcmV2LCdwJyk7fQogICAgaWYoZnQud2luPy5wcmljZSl7YWYoJ3dpbi1wJyxmUChmdC53aW4ucHJpY2UpKTtDaFRibCgnd2luLXYnLCd3aW4tYycsZnQud2luLnByaWNlLGZ0Lndpbi5wcmV2LCdwJyk7fQogICAgaWYoZnQudml4Py5wcmljZSl7YWYoJ3ZpeC1wJyxOdW1iZXIoZnQudml4LnByaWNlKS50b0ZpeGVkKDIpKTtDaFRibCgndml4LXYnLCd2aXgtYycsZnQudml4LnByaWNlLGZ0LnZpeC5wcmV2LCd1Jyk7fQogICAgaWYoZnQuZHh5Py5wcmljZSl7YWYoJ2R4eS1wJyxOdW1iZXIoZnQuZHh5LnByaWNlKS50b0ZpeGVkKDIpKTtDaFRibCgnZHh5LXYnLCdkeHktYycsZnQuZHh5LnByaWNlLGZ0LmR4eS5wcmV2LCd1Jyk7fQogICAgaWYoZnQudXNkPy5wcmljZSl7YWYoJ3VzZC1wJyxmUihmdC51c2QucHJpY2UpKTtDaFRibCgndXNkLXYnLCd1c2QtYycsZnQudXNkLnByaWNlLGZ0LnVzZC5wcmV2fHxmdC51c2QucHJpY2UsJ3InKTt9CiAgfQp9CmZ1bmN0aW9uIGRvUG9zKHR2KXsKICBjb25zdCBwdD10dlsnQk1GQk9WRVNQQTpQRVRSNCddO2NvbnN0IHBwPXB0Py5wfHw0MCxwdj1wdD8udnx8NDA7CiAgRSgncHQtcCcsZlIocHApKTtDaCgncHQtYycscHAscHYsJ3InKTsKICBjb25zdCBwZD1wcC0zMC44NTtFKCdwdC1pdG0nLChwZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHBkKS50b0ZpeGVkKDIpKycgJysocGQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCB2bD10dlsnQk1GQk9WRVNQQTpWQUxFMyddO2NvbnN0IHZwPXZsPy5wfHw3OCx2dj12bD8udnx8Nzg7CiAgRSgndmwtcCcsZlIodnApKTtDaCgndmwtYycsdnAsdnYsJ3InKTsKICBjb25zdCB2ZD12cC01Ny40MDtFKCd2bC1pdG0nLCh2ZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHZkKS50b0ZpeGVkKDIpKycgJysodmQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCBjZD0oZHMsZWlkKT0+e2NvbnN0IHY9bmV3IERhdGUoZHMpLGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKSxlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVpZCk7aWYoZSllLnRleHRDb250ZW50PWQ7fTsKICBjZCgnMjAyNi0xMi0xNycsJ3B0LWRpYXMnKTtjZCgnMjAyNy0wMi0xOCcsJ3ZsLWRpYXMnKTtjZCgnMjAyNi0wOS0xNCcsJ2EzLWRpYXMnKTtjZCgnMjAyNi0xMC0wMicsJ2EzYi1kaWFzJyk7Y2QoJzIwMjYtMDctMTYnLCdyeC1kaWFzJyk7CiAgc2V0VGltZW91dChhc3luYygpPT57CiAgICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy9BWElBMy5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjsKICAgICAgY29uc3QgcD1kLnByZWNvX2F0dWFsO0UoJ2EzLXAnLGZSKHApKTtFKCdhM2ItcCcsZlIocCkpOwogICAgICBjb25zdCBrQT00My41MSxrdUE9NjguNzYsa0I9NDAuNTIsa3VCPTYyLjgxOwogICAgICBjb25zdCBkQT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTMta2RvJyk7aWYoZEEpZEEudGV4dENvbnRlbnQ9KChwLWtBKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1QT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTMta3VvJyk7aWYodUEpdUEudGV4dENvbnRlbnQ9KChrdUEtcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7CiAgICAgIGNvbnN0IHNBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhMy1zdCcpO2lmKHNBKXtzQS50ZXh0Q29udGVudD1wPD1rQT8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1QT8n4pqgIEtVTyBBVElOR0lETyc6J+KchSBObyByYW5nZSc7c0EuY2xhc3NOYW1lPSdzdiAnKyhwPD1rQXx8cD49a3VBPyd3YXJuJzonb2snKTt9CiAgICAgIGNvbnN0IGRCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhM2Ita2RvJyk7aWYoZEIpZEIudGV4dENvbnRlbnQ9KChwLWtCKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1Qj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTNiLWt1bycpO2lmKHVCKXVCLnRleHRDb250ZW50PSgoa3VCLXApL3AqMTAwKS50b0ZpeGVkKDEpKyclIHBhcmEgbyBLVU8nOwogICAgICBjb25zdCBzQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTNiLXN0Jyk7aWYoc0Ipe3NCLnRleHRDb250ZW50PXA8PWtCPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VCPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQi5jbGFzc05hbWU9J3N2ICcrKHA8PWtCfHxwPj1rdUI/J3dhcm4nOidvaycpO30KICAgIH1jYXRjaChlKXt9CiAgfSwyMDAwKTsKICBzZXRUaW1lb3V0KGFzeW5jKCk9PnsKICAgIHRyeXtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjsKICAgICAgY29uc3QgcD1kLnByZWNvX2F0dWFsO0UoJ3J4LXAnLGZSKHApKTsKICAgICAgY29uc3QgaXRtPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1pdG0nKTsKICAgICAgY29uc3QgZGlzdD1wLTEwLjUwOwogICAgICBpZihpdG0paXRtLnRleHRDb250ZW50PShkaXN0Pj0wPycrIFIkICc6Jy0gUiQgJykrTWF0aC5hYnMoZGlzdCkudG9GaXhlZCgyKSsnICcrKGRpc3Q+PTA/J2FjaW1hIChJVE0g4pqgKSc6J2FiYWl4byAoT1RNIOKchSknKSsnIGRvIHN0cmlrZSc7CiAgICAgIGNvbnN0IGRlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1rZG8nKTtpZihkZSlkZS50ZXh0Q29udGVudD0oKHAtMTAuNTApL3AqMTAwKS50b0ZpeGVkKDEpKyclIGRvIHN0cmlrZSc7CiAgICAgIGNvbnN0IHNlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1zdCcpO2lmKHNlKXtzZS50ZXh0Q29udGVudD1wPD0xMC41MD8n4pyFIE9UTSDigJQgYWJhaXhvIGRvIHN0cmlrZSc6J+KaoCBJVE0g4oCUIGFjaW1hIGRvIHN0cmlrZSc7c2UuY2xhc3NOYW1lPSdzdiAnKyhwPD0xMC41MD8nb2snOidpdG0nKTt9CiAgICB9Y2F0Y2goZSl7fQogIH0sMzAwMCk7Cn0KYXN5bmMgZnVuY3Rpb24gTUModGssc2ssZGlhcyxsSWQscklkLHNJZCx2SWQsaUlkLHJ0SWQpewogIHRyeXsKICAgIGNvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXI6dGssa19jYWxsOnNrLGtfcHV0OnNrLHRfZGF5czpkaWFzLG46NTAwMH0pfSk7CiAgICBpZighci5vayl0aHJvdyAwO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoZC5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZC5lcnJvcik7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChsSWQpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKHJJZCkuc3R5bGUuZGlzcGxheT0nYmxvY2snOwogICAgY29uc3QgcHJvYj1OdW1iZXIoZC5wcm9iX2NhbGxfZXhlcmNpZGF8fDApOwogICAgY29uc3Qgc0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHNJZCk7c0VsLnRleHRDb250ZW50PXByb2IudG9GaXhlZCgxKSsnJSc7CiAgICBzRWwuY2xhc3NOYW1lPSdpdiAnKyhwcm9iPDE1Pydvayc6cHJvYjwzMD8nd2Fybic6J2Rvd24nKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHZJZCkudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpSWQpLnRleHRDb250ZW50PSdWb2wuaGlzdC4gJytkLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclIMK3ICcrKHByb2I8MTU/J+KchSBSaXNjbyBiYWl4byBkZSBleGVyY8OtY2lvJzon4pqgIE1vbml0b3JhciBwb3Npw6fDo28nKTsKICAgIGlmKHJ0SWQpRShydElkLHByb2IudG9GaXhlZCgxKSsnJScpOwogIH1jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChsSWQpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCd0aW1lb3V0Jyk7fQp9CmFzeW5jIGZ1bmN0aW9uIE1DQih0ayxlbixrZCxrdSxkaWFzLHBmeCl7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL21vbnRlY2FybG8vYmFycmllcicse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeSh7dGlja2VyOnRrLGVudHJ5OmVuLGtkbzprZCxrdW86a3UsdF9kYXlzOmRpYXMsbjozMDAwfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLWwnKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1yJykuc3R5bGUuZGlzcGxheT0nYmxvY2snOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtbmInKS50ZXh0Q29udGVudD1kLnByb2Jfc2VtX2JhcnJlaXJhLnRvRml4ZWQoMSkrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMta3UnKS50ZXh0Q29udGVudD1kLnByb2JfYmFycmVpcmFfYWx0YS50b0ZpeGVkKDEpKyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLWtkJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2JhaXhhLnRvRml4ZWQoMSkrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtdm8nKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLWknKS50ZXh0Q29udGVudD0nUiQgJytkLnByZWNvX2F0dWFsKycgwrcgS0RPIFIkICcrZC5rZG8rJyDCtyBLVU8gUiQgJytkLmt1bzsKICB9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtbCcpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCd0aW1lb3V0Jyk7fQp9CmFzeW5jIGZ1bmN0aW9uIE1DUih0ayxlbixrZCxkaWFzKXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeSh7dGlja2VyOnRrLGtfY2FsbDplbixrX3B1dDplbix0X2RheXM6ZGlhcyxrbm9ja19kb3duOmtkLG46NTAwMH0pfSk7CiAgICBpZighci5vayl0aHJvdyAwO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoZC5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZC5lcnJvcik7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtbCcpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1yJykuc3R5bGUuZGlzcGxheT0nYmxvY2snOwogICAgY29uc3Qgc0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1zJyk7c0VsLnRleHRDb250ZW50PU51bWJlcihkLnByb2Jfc3VjZXNzbykudG9GaXhlZCgxKSsnJSc7c0VsLmNsYXNzTmFtZT0naXYgJysoZC5wcm9iX3N1Y2Vzc28+NzA/J29rJzpkLnByb2Jfc3VjZXNzbz41MD8nd2Fybic6J2Rvd24nKTsKICAgIGNvbnN0IGNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtYycpO2lmKGNFbCljRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9jYWxsX2V4ZXJjaWRhKS50b0ZpeGVkKDEpKyclJzsKICAgIGNvbnN0IGtFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtaycpO2lmKGtFbClrRWwudGV4dENvbnRlbnQ9ZC5wcm9iX2tkb19hdGluZ2lkbyE9bnVsbD9OdW1iZXIoZC5wcm9iX2tkb19hdGluZ2lkbykudG9GaXhlZCgxKSsnJSc6J+KAlCc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtdicpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWknKS50ZXh0Q29udGVudD0nUiQgJytkLnByZWNvX2F0dWFsKycgwrcgS0RPIFIkICcrZC5rbm9ja19kb3duOwogIH1jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtbCcpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCd0aW1lb3V0Jyk7fQp9CmFzeW5jIGZ1bmN0aW9uIGZJbmQodGspe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMzAwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvJyt0ayx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmQlRDSSgpe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMTUwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2J0Yy9pbmRpY2F0b3JzJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmQlRDQygpe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMTUwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2J0Yy9jeWNsZScse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkZHKCl7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvZmVhcmdyZWVkJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBjb25zdCB2PWQudmFsdWV8fDUwLGNscz12PD0yNT8ndmFyKC0tcmVkKSc6djw9NDU/J3ZhcigtLXdhcm4pJzp2PD03NT8ndmFyKC0tYWNjZW50KSc6J3ZhcigtLWdyZWVuKSc7CiAgICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmctYXJlYScpOwogICAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTZweCI+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206OHB4O2ZvbnQtd2VpZ2h0OjYwMDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjVweCI+8J+YsSBGZWFyICYgR3JlZWQgSW5kZXg8L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxNHB4Ij48ZGl2IHN0eWxlPSJmb250LXNpemU6MzhweDtmb250LXdlaWdodDo4MDA7Y29sb3I6JytjbHMrJyI+Jyt2Kyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTZweDtmb250LXdlaWdodDo3MDA7Y29sb3I6JytjbHMrJyI+JysoZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpKyc8L2Rpdj48L2Rpdj48L2Rpdj4nOwogICAgRSgnZmctdmFsJyxTdHJpbmcodikpO0UoJ2ZnLWxibCcsZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpOwogICAgdHJ5e2NvbnN0IHJiPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7aWYocmIub2spe2NvbnN0IGRiPWF3YWl0IHJiLmpzb24oKTtjb25zdCBicD1wYXJzZUZsb2F0KGRiLkJUQ3x8MCk7aWYoYnA+MCl7RSgnYnRjLWluZC1wJywnJCcrTnVtYmVyKGJwKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTtFKCdidGMtcCcsZlUoYnApKTt9fX1jYXRjaChlMil7fQogIH1jYXRjaChlKXt9Cn0KZnVuY3Rpb24gcm5kSW5kKGlkLGRhdGEpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKyctaW5kJyk7aWYoIWVsKXJldHVybjsKICBpZighZGF0YSl7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS13YXJuKTtwYWRkaW5nOjEycHg7Zm9udC1zaXplOjEzcHgiPuKPsyBTZW0gcmVzcG9zdGEg4oCUIGNsaXF1ZSDihrs8L2Rpdj4nO3JldHVybjt9CiAgaWYoZGF0YS5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1yZWQpO3BhZGRpbmc6MTJweDtmb250LXNpemU6MTNweCI+4pqgICcrZGF0YS5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGNvbnN0IGluZHM9ZGF0YS5pbmRpY2Fkb3Jlc3x8W10sc2M9TnVtYmVyKGRhdGEuc2NvcmVfdG90YWx8fDApLHByZWNvPWRhdGEucHJlY29fYXR1YWwsZ3JhaGFtPWRhdGEuZ3JhaGFtX3ZhbHVlLHVwPWRhdGEudXBzaWRlX2dyYWhhbSxzZXRvcj1kYXRhLnNldG9yfHwnJzsKICBjb25zdCBzYzI9c2M+PTY1Pyd2YXIoLS1ncmVlbiknOnNjPj00MD8ndmFyKC0td2FybiknOid2YXIoLS1yZWQpJyxzbD1zYz49NjU/J0NvbXByYSDilrInOnNjPj00MD8nTmV1dHJvIOKGkic6J1ZlbmRhIOKWvCc7CiAgbGV0IGg9JzxkaXYgY2xhc3M9InNjYiI+JysKICAgICc8ZGl2IGNsYXNzPSJzY2MiPjxkaXYgY2xhc3M9InNjbSI+U2NvcmU8L2Rpdj48ZGl2IGNsYXNzPSJzY24iIHN0eWxlPSJjb2xvcjonK3NjMisnIj4nK3NjKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY2wiIHN0eWxlPSJjb2xvcjonK3NjMisnIj4nK3NsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjYyI+PGRpdiBjbGFzcz0ic2NtIj5Db3Rhw6fDo288L2Rpdj48ZGl2IGNsYXNzPSJzY3YiPicrKHByZWNvPydSJCAnK051bWJlcihwcmVjbykudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjcyI+JytzZXRvcisnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJzY2MiPjxkaXYgY2xhc3M9InNjbSI+R3JhaGFtIFZKPC9kaXY+PGRpdiBjbGFzcz0ic2N2IiBzdHlsZT0iY29sb3I6JysodXAmJnVwPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyhncmFoYW0/J1IkICcrTnVtYmVyKGdyYWhhbSkudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjcyIgc3R5bGU9ImNvbG9yOicrKHVwJiZ1cD4wPyd2YXIoLS1ncmVlbiknOid2YXIoLS1yZWQpJykrJyI+JysodXAhPW51bGw/KHVwPjA/JysnOicnKSt1cCsnJSB1cHNpZGUnOifigJQnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8L2Rpdj4nOwogIGluZHMuZm9yRWFjaChpPT57CiAgICBjb25zdCBzPWkuc2luYWx8fCcnLGNscz1zPT09J0FsdGEnfHxzPT09J1NvYnJldmVuZGEnPydvayc6cz09PSdCYWl4YSd8fHM9PT0nU29icmVjb21wcmEnPydkb3duJzond2FybicsYXI9Y2xzPT09J29rJz8n4payJzpjbHM9PT0nZG93bic/J+KWvCc6J+KGkic7CiAgICBoKz0nPGRpdiBjbGFzcz0iaXIiPjxkaXYgY2xhc3M9ImlydCI+PHNwYW4gY2xhc3M9ImlybiI+JysoaS5ub21lfHwnJykrJzwvc3Bhbj48c3BhbiBjbGFzcz0iaXJ2ICcrY2xzKyciPicrKGkudmFsb3IhPW51bGw/aS52YWxvcjon4oCUJykrJyAnK2FyKyc8L3NwYW4+PC9kaXY+JysoaS5leHBsaWNhY2FvPyc8ZGl2IGNsYXNzPSJpcmUiPicraS5leHBsaWNhY2FvKyc8L2Rpdj4nOicnKSsnPC9kaXY+JzsKICB9KTsKICBlbC5pbm5lckhUTUw9aHx8JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEwcHgiPlNlbSBpbmRpY2Fkb3JlczwvZGl2Pic7Cn0KZnVuY3Rpb24gcm5kQlRDSShkKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWluZC1hcmVhJyk7aWYoIWVsfHwhZClyZXR1cm47CiAgaWYoZC5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS13YXJuKTtwYWRkaW5nOjEycHg7Zm9udC1zaXplOjEzcHgiPuKPsyAnK2QuZXJyb3IrJzwvZGl2Pic7cmV0dXJuO30KICBsZXQgaD0nPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHgiPic7CiAgaWYoZC5yc2lfc2VtYW5hbCE9bnVsbCl7Y29uc3QgcnY9ZC5yc2lfc2VtYW5hbCxyYz1ydjwzMD8nb2snOnJ2PjcwPydkb3duJzond2Fybic7aCs9JzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJpdiAnK3JjKyciPicrcnYudG9GaXhlZCgxKSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nKyhydjwzMD8nU29icmV2ZW5kYSDimqEnOnJ2PjcwPydTb2JyZWNvbXByYSDimqAnOidOZXV0cm8nKSsnPC9kaXY+PC9kaXY+JztFKCdidGMtcnNpJyxydi50b0ZpeGVkKDEpKTt9CiAgaWYoZC5tbTUwX3NlbWFuYWwpaCs9JzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+TU0gNTAgc2VtLjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPiQnK051bWJlcihkLm1tNTBfc2VtYW5hbCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PC9kaXY+JzsKICBpZihkLm1tMjAwX3NlbWFuYWwpaCs9JzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+TU0gMjAwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4kJytOdW1iZXIoZC5tbTIwMF9zZW1hbmFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nOwogIGlmKGQubWFjZF9oaXN0b2dyYW0hPW51bGwpe2NvbnN0IG1oPWQubWFjZF9oaXN0b2dyYW07aCs9JzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+TUFDRCBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2ICcrKG1oPjA/J29rJzonZG93bicpKyciPicrTnVtYmVyKG1oKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrKG1oPjA/J01vbWVudHVtIOKWsic6J01vbWVudHVtIOKWvCcpKyc8L2Rpdj48L2Rpdj4nO30KICBpZihkLm9idl90cmVuZCloKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5PQlY8L2Rpdj48ZGl2IGNsYXNzPSJpdiAnKyhkLm9idl90cmVuZD09PSdzdWJpbmRvJz8nb2snOidkb3duJykrJyI+JytkLm9idl90cmVuZCsnPC9kaXY+PC9kaXY+JzsKICBoKz0nPC9kaXY+JztlbC5pbm5lckhUTUw9aDsKICBpZihkLnByaWNlKUUoJ2J0Yy1pbmQtcCcsJyQnK051bWJlcihkLnByaWNlKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTsKfQpmdW5jdGlvbiBybmRCVENDKGQpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidGMtY3ljbGUtYXJlYScpO2lmKCFlbHx8IWR8fGQuZXJyb3IpcmV0dXJuOwogIGNvbnN0IGZVMj12PT52PyckJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KTon4oCUJzsKICBlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi1ib3R0b206MTBweCI+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1WUlYgWi1TY29yZTwvZGl2PjxkaXYgY2xhc3M9Iml2ICcrKGQubXZydl96c2NvcmU/LnZhbHVlPDE/J29rJzpkLm12cnZfenNjb3JlPy52YWx1ZTwzPyd3YXJuJzonZG93bicpKyciPicrZC5tdnJ2X3pzY29yZT8udmFsdWUrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JytkLm12cnZfenNjb3JlPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk5VUEw8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nKygoZC5udXBsPy52YWx1ZXx8MCkqMTAwKS50b0ZpeGVkKDApKyclPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nK2QubnVwbD8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5QdWVsbCBNdWx0aXBsZTwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrZC5wdWVsbD8udmFsdWUrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JytkLnB1ZWxsPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPjIwMFcgTUE8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nK2ZVMihkLm1hMjAwdykrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JysoZC5tYTIwMHdfcGN0PycrJytkLm1hMjAwd19wY3QrJyUnOicnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlJhaW5ib3cgQmFuZDwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrKGQucmFpbmJvdz8uYmFuZHx8J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UGkgQ3ljbGUgRGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiBvayI+JytmVTIoZC5waV9jeWNsZT8uZGlzdGFuY2UpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzwvZGl2PjxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4O2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC13ZWlnaHQ6NjAwIj4nKyhkLnBpX2N5Y2xlPy5zaWduYWx8fCcnKSsnPC9kaXY+JzsKfQphc3luYyBmdW5jdGlvbiBsb2FkSW5kKCl7CiAgY29uc3Qgd3Q9KHAsbXMsZmIpPT5Qcm9taXNlLnJhY2UoW3AsbmV3IFByb21pc2Uocj0+c2V0VGltZW91dCgoKT0+cihmYiksbXMpKV0pOwogIGNvbnN0W2JpLGJjXT1hd2FpdCBQcm9taXNlLmFsbChbd3QoZkJUQ0koKSwxNTAwMCx7ZXJyb3I6J1RpbWVvdXQg4oCUIGNsaXF1ZSDihrsnfSksd3QoZkJUQ0MoKSwxNTAwMCxudWxsKV0pOwogIHJuZEJUQ0koYmkpO3JuZEJUQ0MoYmMpO2ZGRygpOwogIGNvbnN0IHN0b2Nrcz1bWydQRVRSNC5TQScsJ3BldHI0J10sWydWQUxFMy5TQScsJ3ZhbGUzJ10sWydCQkFTMy5TQScsJ2JiYXMzJ10sWydBWElBMy5TQScsJ2F4aWEzJ10sWydST1hPMzQuU0EnLCdyb3hvMzQnXV07CiAgY29uc3QgcmVzPWF3YWl0IFByb21pc2UuYWxsKHN0b2Nrcy5tYXAoKFt0XSk9Pnd0KGZJbmQodCksMzAwMDAse2Vycm9yOidUaW1lb3V0IDMwcyd9KSkpOwogIHN0b2Nrcy5mb3JFYWNoKChbLGlkXSxpKT0+cm5kSW5kKGlkLHJlc1tpXSkpOwp9CmFzeW5jIGZ1bmN0aW9uIHJsKHRrKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCh0aysnLWluZCcpOwogIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj4nOwogIGNvbnN0IG09e3BldHI0OidQRVRSNC5TQScsdmFsZTM6J1ZBTEUzLlNBJyxiYmFzMzonQkJBUzMuU0EnLGF4aWEzOidBWElBMy5TQScscm94bzM0OidST1hPMzQuU0EnfTsKICBybmRJbmQodGssYXdhaXQgZkluZChtW3RrXSkpOwp9CmNvbnN0IEZMQUdTPXsnVVNEJzon8J+HuvCfh7gnLCdVUyc6J/Cfh7rwn4e4JywnQlJMJzon8J+Hp/Cfh7cnLCdCUic6J/Cfh6fwn4e3JywnRVVSJzon8J+HqvCfh7onLCdFVSc6J/Cfh6rwn4e6JywnR0JQJzon8J+HrPCfh6cnLCdDTlknOifwn4eo8J+HsycsJ0pQWSc6J/Cfh6/wn4e1JywnQ0FEJzon8J+HqPCfh6YnLCdBVUQnOifwn4em8J+HuicsJ0RFJzon8J+HqfCfh6onLCdOWkQnOifwn4ez8J+HvycsJ0NIRic6J/Cfh6jwn4etJ307CmFzeW5jIGZ1bmN0aW9uIGxvYWRDYWwoKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FsLWFyZWEnKSxzdD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FsLXN0Jyk7CiAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoyNHB4O3RleHQtYWxpZ246Y2VudGVyO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+JzsKICBpZihzdClzdC50ZXh0Q29udGVudD0nQnVzY2FuZG8gZXZlbnRvcy4uLic7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvY2FsZW5kYXInLHtjYWNoZTonbm8tc3RvcmUnfSk7CiAgICBpZighci5vayl0aHJvdyBuZXcgRXJyb3IoJ0hUVFAgJytyLnN0YXR1cyk7CiAgICBjb25zdCBldnM9YXdhaXQgci5qc29uKCk7CiAgICBpZihldnMuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGV2cy5lcnJvcik7CiAgICBpZihzdClzdC50ZXh0Q29udGVudD1ldnMubGVuZ3RoPjA/ZXZzLmxlbmd0aCsnIGV2ZW50b3MnOidTZW0gZXZlbnRvcyc7CiAgICBpZighZXZzLmxlbmd0aCl7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJwYWRkaW5nOjI0cHg7Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtYWxpZ246Y2VudGVyIj5TZW0gZXZlbnRvcyBkaXNwb27DrXZlaXM8L2Rpdj4nO3JldHVybjt9CiAgICBjb25zdCBieUQ9e307ZXZzLmZvckVhY2goZT0+e2NvbnN0IGR0PShlLmRhdGV8fCcnKS5zbGljZSgwLDEwKTtpZighYnlEW2R0XSlieURbZHRdPVtdO2J5RFtkdF0ucHVzaChlKTt9KTsKICAgIGxldCBoPScnOwogICAgT2JqZWN0LmtleXMoYnlEKS5zb3J0KCkuZm9yRWFjaChkdD0+ewogICAgICBjb25zdCBkPW5ldyBEYXRlKGR0KydUMTI6MDA6MDAnKSxsYmw9ZC50b0xvY2FsZURhdGVTdHJpbmcoJ3B0LUJSJyx7d2Vla2RheTonbG9uZycsZGF5OicyLWRpZ2l0Jyxtb250aDonc2hvcnQnfSk7CiAgICAgIGgrPSc8ZGl2IGNsYXNzPSJ0Ymwtd3JhcCIgc3R5bGU9Im1hcmdpbi1ib3R0b206MTRweCI+PGRpdiBjbGFzcz0idGJsLWhkciI+PHNwYW4gY2xhc3M9InRibC1oZHItdGl0bGUiPicrbGJsKyc8L3NwYW4+PC9kaXY+JysKICAgICAgICAnPHRhYmxlIGNsYXNzPSJjYWwtdGJsIj48dGhlYWQ+PHRyPjx0aD5QYcOtczwvdGg+PHRoPkhvcmE8L3RoPjx0aD5FdmVudG88L3RoPjx0aD5JbXA8L3RoPjx0aCBjbGFzcz0iciI+UmVhbGl6YWRvPC90aD48dGggY2xhc3M9InIiPlByZXZpc3RvPC90aD48L3RyPjwvdGhlYWQ+PHRib2R5Pic7CiAgICAgIGJ5RFtkdF0uZm9yRWFjaChlPT57CiAgICAgICAgY29uc3QgaWM9ZS5pbXBvcnRhbmNlPj0zPydpbXAtaGlnaCc6J2ltcC1tZWQnOwogICAgICAgIGNvbnN0IGFjPWUuc2lnbmFsPT09J2JlYXQnPyd2YXIoLS1ncmVlbiknOmUuc2lnbmFsPT09J21pc3MnPyd2YXIoLS1yZWQpJzondmFyKC0tdGV4dCknOwogICAgICAgIGNvbnN0IGltcD0n4pePJy5yZXBlYXQoTWF0aC5taW4oZS5pbXBvcnRhbmNlLDMpKTsKICAgICAgICBoKz0nPHRyPicrCiAgICAgICAgICAnPHRkPjxzcGFuIGNsYXNzPSJjYWwtZmxhZyI+JysoZS5mbGFnfHxGTEFHU1tlLmNvdW50cnldfHwn8J+MkCcpKyc8L3NwYW4+PC90ZD4nKwogICAgICAgICAgJzx0ZD48c3BhbiBjbGFzcz0iY2FsLXRpbWUiPicrKGUudGltZXx8J+KAlCcpKyc8L3NwYW4+PC90ZD4nKwogICAgICAgICAgJzx0ZD48c3BhbiBjbGFzcz0iY2FsLWV2IiB0aXRsZT0iJytlLmV2ZW50KyciPicrZS5ldmVudCsnPC9zcGFuPjwvdGQ+JysKICAgICAgICAgICc8dGQ+PHNwYW4gY2xhc3M9IicraWMrJyI+JytpbXArJzwvc3Bhbj48L3RkPicrCiAgICAgICAgICAnPHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2FsLXZhbCIgc3R5bGU9ImNvbG9yOicrYWMrJyI+JysoZS5hY3R1YWx8fCfigJQnKSsnPC9zcGFuPjwvdGQ+JysKICAgICAgICAgICc8dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjYWwtZmMiPicrKGUuZm9yZWNhc3R8fCfigJQnKSsnPC9zcGFuPjwvdGQ+JysKICAgICAgICAgICc8L3RyPic7CiAgICAgIH0pOwogICAgICBoKz0nPC90Ym9keT48L3RhYmxlPjwvZGl2Pic7CiAgICB9KTsKICAgIGVsLmlubmVySFRNTD1oOwogIH1jYXRjaChlKXsKICAgIGlmKHN0KXN0LnRleHRDb250ZW50PSdFcnJvJzsKICAgIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tcmVkKTtwYWRkaW5nOjI0cHg7dGV4dC1hbGlnbjpjZW50ZXIiPkVycm86ICcrZS5tZXNzYWdlKyc8L2Rpdj4nOwogIH0KfQphc3luYyBmdW5jdGlvbiBtYWluKCl7CiAgdHJ5ewogICAgY29uc3RbLHR2LGZ0XT1hd2FpdCBQcm9taXNlLmFsbChbZkhMKCksZlRWKCksZkZ1dCgpXSk7CiAgICBjb25zdCBub3c9bmV3IERhdGUoKS50b0xvY2FsZVRpbWVTdHJpbmcoJ3B0LUJSJyk7CiAgICBFKCdsYXN0LXVwZGF0ZScsJ+KGuyAnK25vdyk7RSgnbGFzdC11cGRhdGUtdGJsJyxub3cpO0UoJ2Zvb3Rlci10aW1lJyxub3cpOwogICAgd2luZG93Ll9sYXN0VFY9dHY7ZG9NYWNybyh0dixmdCk7ZG9Qb3ModHYpOwogICAgc2V0VGltZW91dChmRnVuZCwzMDAwKTsKICAgIHNldFRpbWVvdXQoYXN5bmMoKT0+e3RyeXtjb25zdFtiaSxiY109YXdhaXQgUHJvbWlzZS5hbGwoW2ZCVENJKCksZkJUQ0MoKV0pO2lmKGJpKXJuZEJUQ0koYmkpO2lmKGJjKXJuZEJUQ0MoYmMpO2ZGRygpO31jYXRjaChlKXt9fSw1MDAwKTsKICAgIGNvbnN0IGhvamU9bmV3IERhdGUoKTsKICAgIGNvbnN0IGRQPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0xMi0xNycpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkVj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjctMDItMTgnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZEE9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTA5LTE0JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRBYj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMTAtMDInKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZFI9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTA3LTE2JyktaG9qZSkvODY0ZTUpKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DKCdQRVRSNC5TQScsMzAuODUsZFAsJ3B0LW1jLWwnLCdwdC1tYy1yJywncHQtbWMtcycsJ3B0LW1jLXYnLCdwdC1tYy1pJywncHQtbWMtcnQnKSw2MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DKCdWQUxFMy5TQScsNTcuNDAsZFYsJ3ZsLW1jLWwnLCd2bC1tYy1yJywndmwtbWMtcycsJ3ZsLW1jLXYnLCd2bC1tYy1pJywndmwtbWMtcnQnKSwxMjAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQ0IoJ0FYSUEzLlNBJyw1NC4zMSw0My41MSw2OC43NixkQSwnYTMnKSwxODAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQ0IoJ0FYSUEzLlNBJyw1MC42NSw0MC41Miw2Mi44MSxkQWIsJ2EzYicpLDI0MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DUignUk9YTzM0LlNBJywxMi44OCwxMC41MCxkUiksMzAwMDApOwogICAgY29uc3QgZEJCPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0wOC0yMCcpLWhvamUpLzg2NGU1KSk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQygnQkJBUzMuU0EnLDIxLjY1LGRCQiwnYmItbWMtbCcsJ2JiLW1jLXInLCdiYi1tYy1zJywnYmItbWMtdicsJ2JiLW1jLWknLCdiYi1tYy1ydCcpLDM2MDAwKTsKICAgIC8vIEJCQVMzIGNvdGHDp8OjbyDigJQgdmlhIFRWIG91IGZhbGxiYWNrIC9pbmRpY2F0b3JzCiAgICBjb25zdCBiYlRWPXR2WydCTUZCT1ZFU1BBOkJCQVMzJ107CiAgICBpZihiYlRWPy5wKXsKICAgICAgRSgnYmItcCcsZlIoYmJUVi5wKSk7Q2goJ2JiLWMnLGJiVFYucCxiYlRWLnZ8fGJiVFYucCwncicpOwogICAgICBjb25zdCBkMj1iYlRWLnAtMjEuNjU7CiAgICAgIGNvbnN0IGl0bTI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JiLWl0bScpOwogICAgICBpZihpdG0yKXtpdG0yLnRleHRDb250ZW50PShkMj49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKGQyKS50b0ZpeGVkKDIpKycgJysoZDI+PTA/J2FjaW1hIChJVE0g4pqgKSc6J2FiYWl4byAoT1RNIOKchSknKSsnIGRvIHN0cmlrZSc7aXRtMi5jbGFzc05hbWU9J3N2ICcrKGQyPj0wPydpdG0nOidvaycpO30KICAgIH0gZWxzZSB7CiAgICAgIC8vIFRWIG7Do28gcmV0b3Jub3UgQkJBUzMg4oCUIGZhbGxiYWNrCiAgICAgIGZldGNoKEIrJy9pbmRpY2F0b3JzL0JCQVMzLlNBJykudGhlbihyMj0+cjIuanNvbigpKS50aGVuKGQyPT57CiAgICAgICAgaWYoZDIucHJlY29fYXR1YWwpewogICAgICAgICAgRSgnYmItcCcsZlIoZDIucHJlY29fYXR1YWwpKTtDaCgnYmItYycsZDIucHJlY29fYXR1YWwsZDIucHJlY29fYW50ZXJpb3J8fGQyLnByZWNvX2F0dWFsKjAuOTksJ3InKTsKICAgICAgICAgIGNvbnN0IGRpc3Q9ZDIucHJlY29fYXR1YWwtMjEuNjU7CiAgICAgICAgICBjb25zdCBpdG0yPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiYi1pdG0nKTsKICAgICAgICAgIGlmKGl0bTIpe2l0bTIudGV4dENvbnRlbnQ9KGRpc3Q+PTA/JysgUiQgJzonLSBSJCAnKStNYXRoLmFicyhkaXN0KS50b0ZpeGVkKDIpKycgJysoZGlzdD49MD8nYWNpbWEgKElUTSDimqApJzonYWJhaXhvIChPVE0g4pyFKScpKycgZG8gc3RyaWtlJztpdG0yLmNsYXNzTmFtZT0nc3YgJysoZGlzdD49MD8naXRtJzonb2snKTt9CiAgICAgICAgfQogICAgICB9KS5jYXRjaCgoKT0+e30pOwogICAgfQogICAgY29uc3QgY2RCQj0oKT0+e2NvbnN0IHY9bmV3IERhdGUoJzIwMjYtMDgtMjAnKSxkPU1hdGgubWF4KDAsTWF0aC5jZWlsKCh2LW5ldyBEYXRlKCkpLzg2NGU1KSksZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmItZGlhcycpO2lmKGUpZS50ZXh0Q29udGVudD1kO307Y2RCQigpOwogICAgd2luZG93Ll9JTD1mYWxzZTsKICB9Y2F0Y2goZSl7Y29uc29sZS5lcnJvcihlKTt9Cn0KbWFpbigpO3NldEludGVydmFsKG1haW4sMTIwMDAwKTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPgo=").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
