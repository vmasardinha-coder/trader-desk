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
    """Lê do cache GitHub. Parse manual de timezone para compatibilidade Python 3.9+"""
    import re as _re
    flag_map = {
        'USD':'🇺🇸','US':'🇺🇸','BRL':'🇧🇷','BR':'🇧🇷',
        'EUR':'🇪🇺','EU':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳',
        'JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺','DE':'🇩🇪',
        'NZD':'🇳🇿','CHF':'🇨🇭',
    }
    currencies_ok = set(flag_map.keys())
    imp_map = {'Low':1,'Medium':2,'High':3,'Holiday':0}

    def parse_ff_date(raw):
        """Parse '2026-06-15T03:30:00-04:00' compatível com Python 3.9+"""
        if not raw or 'T' not in raw:
            return (raw[:10] if raw else ''), ''
        try:
            from datetime import datetime as _dt, timedelta
            # Extrair componentes manualmente
            match = _re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):\d{2}([+-])(\d{2}):(\d{2})', raw)
            if not match:
                return raw[:10], raw[11:16]
            date_p, hh, mm, sign, tz_h, tz_m = match.groups()
            naive = _dt.strptime(f"{date_p} {hh}:{mm}", "%Y-%m-%d %H:%M")
            tz_offset = int(tz_h) * 60 + int(tz_m)
            if sign == '-': tz_offset = -tz_offset
            # Converter para UTC depois para BRT (UTC-3)
            utc = naive - timedelta(minutes=tz_offset)
            brt = utc - timedelta(hours=3)
            return brt.strftime('%Y-%m-%d'), brt.strftime('%H:%M')
        except:
            return raw[:10], raw[11:16]

    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/cache/calendar.json',
            headers={'Cache-Control':'no-cache','User-Agent':'Trader-Desk/1.0'},
            timeout=10)
        if not r.ok or len(r.text) < 10:
            return jsonify({'error': f'cache indisponivel: {r.status_code}'}), 500
        raw = r.json()
        all_events = []
        for e in raw:
            cur = e.get('country', e.get('currency',''))
            if not cur or cur not in currencies_ok: continue
            imp = imp_map.get(e.get('impact',''), 0)
            if imp < 2: continue
            date_str, time_str = parse_ff_date(e.get('date',''))
            if not date_str: continue
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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjExLjgg4oCUIERhcmsgUHJlbWl1bSDigJQgYnVpbGQ6MTc4MTcxMjQwNiAtLT4KPGh0bWwgbGFuZz0icHQtQlIiPgo8aGVhZD4KPG1ldGEgY2hhcnNldD0iVVRGLTgiPgo8bWV0YSBuYW1lPSJ2aWV3cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MS4wIj4KPHRpdGxlPlRyYWRlciBEZXNrPC90aXRsZT4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JbnRlcjp3Z2h0QDQwMDs1MDA7NjAwOzcwMCZmYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs2MDA7NzAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Cjpyb290ewogIC0tYmc6IzBmMGYxMzstLWJnMjojMTMxMzFhOy0tYmczOiMxYTFhMjQ7CiAgLS10ZXh0OiNlOGU4ZjA7LS1tdXRlZDojNTA1MDY4Oy0tYm9yZGVyOiMxZTFlMmU7CiAgLS1hY2NlbnQ6IzdjNmFmNzstLWFjY2VudDI6IzRmYzNmNzsKICAtLWdyZWVuOiMwMGU2NzY7LS1yZWQ6I2YwNjI5MjstLXdhcm46I2ZmYjc0ZDsKICAtLWdvbGQ6I2YwYTUwMAp9CmJvZHl7CiAgYmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7CiAgZm9udC1mYW1pbHk6J0ludGVyJyxzYW5zLXNlcmlmO2ZvbnQtc2l6ZToxNHB4OwogIGxpbmUtaGVpZ2h0OjEuNTtwYWRkaW5nOjIwcHggMjRweDsKICBtYXgtd2lkdGg6MTEwMHB4O21hcmdpbjowIGF1dG87bWluLWhlaWdodDoxMDB2aAp9CkBtZWRpYShtYXgtd2lkdGg6NjAwcHgpe2JvZHl7cGFkZGluZzoxMnB4fX0KCi8qIOKUgOKUgCBIRUFERVIg4pSA4pSAICovCi5oZHJ7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjIwcHg7cGFkZGluZy1ib3R0b206MTZweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpfQoubG9nb3tmb250LXNpemU6MThweDtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtsZXR0ZXItc3BhY2luZzouNXB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5sb2dvIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50Mil9Ci5oZHItcmlnaHR7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweH0KLmJhZGdle2JhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo0cHggMTJweDtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4fQouaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQoKLyog4pSA4pSAIFRBQlMg4pSA4pSAICovCi50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MjBweDtvdmVyZmxvdy14OmF1dG87cGFkZGluZy1ib3R0b206MnB4fQoudGFie3BhZGRpbmc6OHB4IDE4cHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6MTJweDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3doaXRlLXNwYWNlOm5vd3JhcDtmb250LWZhbWlseTppbmhlcml0O3RyYW5zaXRpb246YWxsIC4xNXN9Ci50YWI6aG92ZXJ7Y29sb3I6dmFyKC0tdGV4dCk7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci50YWIuYWN0aXZle2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtjb2xvcjojZmZmO2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpfQoudGFiLWNvbnRlbnR7ZGlzcGxheTpub25lfS50YWItY29udGVudC5hY3RpdmV7ZGlzcGxheTpibG9ja30KCi8qIOKUgOKUgCBTRUNUSU9OIOKUgOKUgCAqLwouc2Vje2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHggMCA3cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjE0cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4fQouc2VjIC5kb3R7d2lkdGg6NXB4O2hlaWdodDo1cHg7YmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrO2ZsZXgtc2hyaW5rOjB9Ci5zZWMgLmFjY3tjb2xvcjp2YXIoLS1hY2NlbnQpfQoKLyog4pSA4pSAIEdSSUQgQ0FSRFMg4pSA4pSAICovCi5ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDMsMWZyKTtnYXA6MTBweDttYXJnaW4tYm90dG9tOjE4cHh9CkBtZWRpYShtYXgtd2lkdGg6NTAwcHgpey5ncmlke2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoMiwxZnIpfX0KLmNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHggMTRweDtwb3NpdGlvbjpyZWxhdGl2ZTtvdmVyZmxvdzpoaWRkZW47dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1c30KLmNhcmQ6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci5jYXJkOjpiZWZvcmV7Y29udGVudDonJztwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MDtsZWZ0OjA7cmlnaHQ6MDtoZWlnaHQ6MnB4fQouY2FyZC5nOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tZ3JlZW4pLCMwMGJjZDQpfQouY2FyZC5iOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tYWNjZW50KSx2YXIoLS1hY2NlbnQyKSl9Ci5jYXJkLnc6OmJlZm9yZXtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS13YXJuKSwjZmY5ODAwKX0KLmNhcmQucjo6YmVmb3Jle2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLHZhcigtLXJlZCksI2U5MWU2Myl9Ci5jbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjRweDtmb250LXdlaWdodDo2MDB9Ci5jbntmb250LXNpemU6MTNweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLWJvdHRvbTo4cHg7Y29sb3I6cmdiYSgyNTUsMjU1LDI1NSwuOCl9Ci5jcHtmb250LXNpemU6MjBweDtmb250LXdlaWdodDo3MDA7Y29sb3I6I2ZmZn0KLmNwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToxNXB4fQouY2N7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NTAwfQouY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0uY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjN9fQoKLyog4pSA4pSAIEFDQ09SRElPTiBTRUdNRU5UT1Mg4pSA4pSAICovCi5zaHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweCAxNnB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7Zm9udC1zaXplOjEycHg7Zm9udC13ZWlnaHQ6NjAwO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDt0cmFuc2l0aW9uOmFsbCAuMTVzfQouc2g6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zYjJ7ZGlzcGxheTpub25lO3BhZGRpbmctdG9wOjZweH0KCi8qIOKUgOKUgCBQT1NJw4fDlUVTIOKUgOKUgCAqLwoucGN7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjE4cHg7bWFyZ2luLWJvdHRvbToxMnB4fQoucGx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnB0e2ZvbnQtc2l6ZToyMnB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO21hcmdpbi1ib3R0b206NHB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5wcHtmb250LXNpemU6MjhweDtmb250LXdlaWdodDo3MDB9LnBwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToyMHB4fQoucGMye2ZvbnQtc2l6ZToxMnB4O21hcmdpbi1ib3R0b206MTBweDtmb250LXdlaWdodDo1MDB9Ci5zYntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmctdG9wOjEwcHg7bWFyZ2luLXRvcDoxMHB4fQouc3J7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjVweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEzcHh9Ci5zbHtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NTAwfS5zdnt0ZXh0LWFsaWduOnJpZ2h0O21heC13aWR0aDo1OCU7Zm9udC13ZWlnaHQ6NjAwfQouc3Yub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5zdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zdi5pdG17Y29sb3I6dmFyKC0tcmVkKX0KLnBvcy1hY2N7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTttYXJnaW4tYm90dG9tOjEwcHh9Ci5wb3MtYWNjLWhkcntkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6MTRweCAxOHB4O2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246YmFja2dyb3VuZCAuMTVzfQoucG9zLWFjYy1oZHI6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQoucG9zLWFjYy10a3tmb250LXNpemU6MjJweDtmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlfQoucG9zLWFjYy1zdWJ7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQoucG9zLWFjYy1yaWdodHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxNHB4fQoucG9zLWFjYy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nOjAgMThweCAxNnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcil9Ci5wb3MtYWNjLWJvZHkub3BlbntkaXNwbGF5OmJsb2NrfQouc2lne2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHg7bWFyZ2luLXRvcDoxMHB4O2JhY2tncm91bmQ6dmFyKC0tYmcpfQouc2d0e2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjcwMDtsZXR0ZXItc3BhY2luZzoxcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206OHB4O2NvbG9yOnZhcigtLWFjY2VudDIpfQouaWJ7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEycHg7dGV4dC1hbGlnbjpjZW50ZXJ9Ci5pbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo1cHg7Zm9udC13ZWlnaHQ6NjAwO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4fQouaXZ7Zm9udC1zaXplOjIwcHg7Zm9udC13ZWlnaHQ6ODAwfQouaXYub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5pdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5pdi5kb3due2NvbG9yOnZhcigtLXJlZCl9CgovKiDilIDilIAgSU5ESUNBRE9SRVMg4pSA4pSAICovCi5zY2J7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyIDFmcjtnYXA6OHB4O21hcmdpbi1ib3R0b206MTRweH0KLnNjY3tiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTRweCAxMnB4O3RleHQtYWxpZ246Y2VudGVyO3Bvc2l0aW9uOnJlbGF0aXZlO292ZXJmbG93OmhpZGRlbn0KLnNjYzo6YmVmb3Jle2NvbnRlbnQ6Jyc7cG9zaXRpb246YWJzb2x1dGU7dG9wOjA7bGVmdDowO3JpZ2h0OjA7aGVpZ2h0OjJweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS1hY2NlbnQpLHZhcigtLWFjY2VudDIpKX0KLnNjbXtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjVweDtmb250LXdlaWdodDo2MDB9Ci5zY257Zm9udC1zaXplOjMycHg7Zm9udC13ZWlnaHQ6ODAwO2xpbmUtaGVpZ2h0OjF9Ci5zY2x7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc2N2e2ZvbnQtc2l6ZToyMHB4O2ZvbnQtd2VpZ2h0OjcwMDttYXJnaW4tdG9wOjRweH0KLnNjc3tmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHh9Ci5pcntiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCB0cmFuc3BhcmVudDtwYWRkaW5nOjEwcHggMTRweDttYXJnaW4tYm90dG9tOjRweDt0cmFuc2l0aW9uOmJvcmRlci1sZWZ0LWNvbG9yIC4xc30KLmlyOmhvdmVye2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLWFjY2VudCl9Ci5pcnR7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmJhc2VsaW5lO21hcmdpbi1ib3R0b206M3B4fQouaXJue2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjVweDtmb250LXdlaWdodDo2MDB9Ci5pcnZ7Zm9udC1zaXplOjE1cHg7Zm9udC13ZWlnaHQ6NzAwfQouaXJ2Lm9re2NvbG9yOnZhcigtLWdyZWVuKX0uaXJ2LmRvd257Y29sb3I6dmFyKC0tcmVkKX0uaXJ2Lndhcm57Y29sb3I6dmFyKC0td2Fybil9Ci5pcmV7Zm9udC1zaXplOjEzcHg7Y29sb3I6IzVhNWE4YTtsaW5lLWhlaWdodDoxLjV9CgovKiDilIDilIAgQ0FMRU5Ew4FSSU8g4pSA4pSAICovCi5jYWwtdGJse3dpZHRoOjEwMCU7Ym9yZGVyLWNvbGxhcHNlOmNvbGxhcHNlO2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZn0KLmNhbC10YmwgdGh7dGV4dC1hbGlnbjpsZWZ0O3BhZGRpbmc6N3B4IDE0cHg7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQouY2FsLXRibCB0aC5ye3RleHQtYWxpZ246cmlnaHR9Ci5jYWwtdGJsIHRke3BhZGRpbmc6OXB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtmb250LXNpemU6MTNweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9Ci5jYWwtdGJsIHRkLnJ7dGV4dC1hbGlnbjpyaWdodH0KLmNhbC10YmwgdHI6bGFzdC1jaGlsZCB0ZHtib3JkZXItYm90dG9tOm5vbmV9Ci5jYWwtdGJsIHRyOmhvdmVyIHRke2JhY2tncm91bmQ6dmFyKC0tYmczKX0KLmNhbC1mbGFne2ZvbnQtc2l6ZToxNnB4fQouY2FsLXRpbWV7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5jYWwtZXZ7Zm9udC13ZWlnaHQ6NTAwO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcDttYXgtd2lkdGg6MzIwcHh9Ci5jYWwtdmFse2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC13ZWlnaHQ6NzAwO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjEzcHh9Ci5jYWwtZmN7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKX0KLmltcC1oaWdoe2NvbG9yOnZhcigtLXJlZCl9LmltcC1tZWR7Y29sb3I6dmFyKC0td2Fybil9CgouaW5kLWFjY3tiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO21hcmdpbi1ib3R0b206MTZweH0KLmluZC1hY2MtaGRye2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzoxMnB4IDE2cHg7Y3Vyc29yOnBvaW50ZXI7dHJhbnNpdGlvbjpiYWNrZ3JvdW5kIC4xNXN9Ci5pbmQtYWNjLWhkcjpob3ZlcntiYWNrZ3JvdW5kOnZhcigtLWJnMyl9Ci5pbmQtYWNjLXRpdGxle2ZvbnQtc2l6ZToxNHB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS1hY2NlbnQpfQouaW5kLWFjYy1zdWJ7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQouaW5kLWFjYy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nOjAgMTZweCAxNnB4fQouaW5kLWFjYy1ib2R5Lm9wZW57ZGlzcGxheTpibG9ja30KLnRibC1ta3R7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2U7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZX0KLnRibC1ta3QgdGhlYWQgdHJ7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKX0KLnRibC1ta3QgdGh7dGV4dC1hbGlnbjpsZWZ0O3BhZGRpbmc6N3B4IDE0cHg7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZn0KLnRibC1ta3QgdGgucnt0ZXh0LWFsaWduOnJpZ2h0fQoudGJsLW1rdCB0ZHtwYWRkaW5nOjlweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjE0cHg7dmVydGljYWwtYWxpZ246bWlkZGxlfQoudGJsLW1rdCB0ZC5ye3RleHQtYWxpZ246cmlnaHR9Ci50YmwtbWt0IHRyOmxhc3QtY2hpbGQgdGR7Ym9yZGVyLWJvdHRvbTpub25lfQoudGJsLW1rdCB0cjpob3ZlciB0ZHtiYWNrZ3JvdW5kOnZhcigtLWJnMyl9Ci50YmwtbWt0IC5zeW17Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLXRleHQpfQoudGJsLW1rdCAuZGVzY3tmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NDAwO2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZjttYXJnaW4tdG9wOjFweH0KLnRibC1ta3QgLnZhbHtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjE1cHg7Y29sb3I6dmFyKC0tdGV4dCl9Ci50YmwtbWt0IC52YWwubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOjEycHh9Ci50YmwtbWt0IC5jaGd7Zm9udC1zaXplOjEzcHg7Zm9udC13ZWlnaHQ6NjAwfQoudGJsLW1rdCAuY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0udGJsLW1rdCAuY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LnRibC1ta3QgLmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9Ci50Ymwtd3JhcHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OHB4O292ZXJmbG93OmhpZGRlbjttYXJnaW4tYm90dG9tOjE4cHh9Ci50YmwtaGRye2JhY2tncm91bmQ6dmFyKC0tYmczKTtwYWRkaW5nOjlweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcn0KLnRibC1oZHItdGl0bGV7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MS41cHh9Ci50YmwtaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQpmb290ZXJ7bWFyZ2luLXRvcDoyNHB4O3BhZGRpbmctdG9wOjEycHg7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtd2VpZ2h0OjUwMH0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KCjxkaXYgY2xhc3M9ImhkciI+CiAgPGRpdiBjbGFzcz0ibG9nbyI+VFJBREVSIDxzcGFuPkRFU0s8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0iaGRyLXJpZ2h0Ij4KICAgIDxkaXYgY2xhc3M9ImJhZGdlIj7il48gQU8gVklWTzwvZGl2PgogICAgPGRpdiBjbGFzcz0iaGRyLXRpbWUiIGlkPSJsYXN0LXVwZGF0ZSI+4oCUPC9kaXY+CiAgPC9kaXY+CjwvZGl2PgoKPGRpdiBjbGFzcz0idGFicyI+CiAgPGRpdiBjbGFzcz0idGFiIGFjdGl2ZSIgb25jbGljaz0ic3coJ2NvdGFjb2VzJyx0aGlzKSI+8J+TiiBDb3Rhw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygnaW5kaWNhZG9yZXMnLHRoaXMpIj7wn5OIIEluZGljYWRvcmVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygncG9zaWNvZXMnLHRoaXMpIj7wn5K8IFBvc2nDp8O1ZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3KCdjYWxlbmRhcmlvJyx0aGlzKSI+8J+ThSBDYWxlbmTDoXJpbzwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENPVEHDh8OVRVMg4pWQ4pWQIC0tPgo8ZGl2IGlkPSJ0YWItY290YWNvZXMiIGNsYXNzPSJ0YWItY29udGVudCBhY3RpdmUiPgogIDxkaXYgY2xhc3M9InRibC13cmFwIj4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5FVUEg4oCUIE1lcmNhZG9zPC9zcGFuPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpbWUiIGlkPSJsYXN0LXVwZGF0ZS10YmwiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDx0YWJsZSBjbGFzcz0idGJsLW1rdCI+CiAgICAgIDx0aGVhZD48dHI+PHRoPkF0aXZvPC90aD48dGggY2xhc3M9InIiPsOabHRpbW88L3RoPjx0aCBjbGFzcz0iciI+VmFyaWHDp8OjbzwvdGg+PHRoIGNsYXNzPSJyIj5WYXIuJTwvdGg+PC90cj48L3RoZWFkPgogICAgICA8dGJvZHk+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlMmYW1wO1AgRVMxKjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkZ1dHVybyBTJlAgNTAwPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImVzZi1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJlc2YtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZXNmLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPk5hc2RhcSBOUTwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkZ1dHVybyBOYXNkYXEgMTAwPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJucWYtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0ibnFmLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkRvdyBKb25lczwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPsONbmRpY2UgREpJQTwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJkamktcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZGppLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImRqaS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5WSVg8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5Wb2xhdGlsaWRhZGU8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InZpeC12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2aXgtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+RFhZPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+RMOzbGFyIEluZGV4PC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImR4eS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJkeHktdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZHh5LWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlVTRC9CUkw8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5Dw6JtYmlvIETDs2xhcjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJ1c2QtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0idXNkLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InVzZC1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0idGJsLXdyYXAiPgogICAgPGRpdiBjbGFzcz0idGJsLWhkciI+PHNwYW4gY2xhc3M9InRibC1oZHItdGl0bGUiPkIzIOKAlCBUb3AgMTA8L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+VmFyLiU8L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5JQk9WPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+w41uZGljZSBCb3Zlc3BhPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9Imlib3YtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iaWJvdi12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJpYm92LWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPldJTjEhPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+RnV0dXJvIElCT1Y8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0id2luLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Indpbi12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ3aW4tYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+UEVUUjQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5QZXRyb2JyYXMgUE48L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0icGV0cjRxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InBldHI0cS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJwZXRyNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+SVRVQjQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5JdGHDuiBVbmliYW5jbyBQTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJpdHViNHEtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iaXR1YjRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Iml0dWI0cS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5WQUxFMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlZhbGUgT048L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0idmFsZTNxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InZhbGUzcS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2YWxlM3EtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+QkJEQzQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5CcmFkZXNjbyBQTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJiYmRjNHEtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYmJkYzRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJiZGM0cS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5BQkVWMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkFtYmV2IE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImFiZXYzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJhYmV2M3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYWJldjNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJCQVMzPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+QmFuY28gZG8gQnJhc2lsIE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJiYXMzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJiYmFzM3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYmJhczNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPldFR0UzPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+V0VHIE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9IndlZ2UzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ3ZWdlM3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0id2VnZTNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlJPWE8zNDwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPk51YmFuayBCRFI8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0icm94bzM0cS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJyb3hvMzRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InJveG8zNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgPC90Ym9keT4KICAgIDwvdGFibGU+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Imp1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuIj48c3BhbiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+QjMgcG9yIFNlZ21lbnRvPC9zcGFuPjxidXR0b24gb25jbGljaz0iZXhwYW5kQWxsKCkiIGlkPSJidG4tZXhwYW5kIiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzMpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjb2xvcjp2YXIoLS1hY2NlbnQpO3BhZGRpbmc6NHB4IDEycHg7Zm9udC1zaXplOjExcHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweCI+KyBFeHBhbmRpciBUb2RvczwvYnV0dG9uPjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnZmluJykiPjxzcGFuPvCfj6YgRmluYW5jZWlybzwvc3Bhbj48c3BhbiBpZD0iYXItZmluIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItZmluIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1maW4iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygncGV0JykiPjxzcGFuPvCfm6IgUGV0csOzbGVvICZhbXA7IEfDoXM8L3NwYW4+PHNwYW4gaWQ9ImFyLXBldCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXBldCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctcGV0Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ21pbicpIj48c3Bhbj7im48gTWluZXJhw6fDo288L3NwYW4+PHNwYW4gaWQ9ImFyLW1pbiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW1pbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbWluIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ21hdCcpIj48c3Bhbj7wn4yyIFBhcGVsICZhbXA7IENlbHVsb3NlPC9zcGFuPjxzcGFuIGlkPSJhci1tYXQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1tYXQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW1hdCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCd1dGknKSI+PHNwYW4+4pqhIFV0aWxpZGFkZSBQw7pibGljYTwvc3Bhbj48c3BhbiBpZD0iYXItdXRpIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItdXRpIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy11dGkiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnY2MnKSI+PHNwYW4+8J+bjSBDb25zdW1vIEPDrWNsaWNvPC9zcGFuPjxzcGFuIGlkPSJhci1jYyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWNjIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1jYyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdjbicpIj48c3Bhbj7wn5uSIENvbnN1bW8gTsOjbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0iYXItY24iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1jbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctY24iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0Zygnc2F1JykiPjxzcGFuPvCfj6UgU2HDumRlPC9zcGFuPjxzcGFuIGlkPSJhci1zYXUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1zYXUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXNhdSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdpbmQnKSI+PHNwYW4+8J+PlyBCZW5zIEluZHVzdHJpYWlzPC9zcGFuPjxzcGFuIGlkPSJhci1pbmQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1pbmQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWluZCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCd0aXQnKSI+PHNwYW4+8J+SuyBUSSAmYW1wOyBDb211bmljYcOnw7Vlczwvc3Bhbj48c3BhbiBpZD0iYXItdGl0Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItdGl0Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy10aXQiPjwvZGl2PjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FVUEgcG9yIFNlZ21lbnRvPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdtNycpIj48c3Bhbj7irZAgNyBNYWduw61maWNhczwvc3Bhbj48c3BhbiBpZD0iYXItbTciPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1tNyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbTciPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnbnEnKSI+PHNwYW4+8J+SuyBOYXNkYXEgVG9wIDE1PC9zcGFuPjxzcGFuIGlkPSJhci1ucSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW5xIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1ucSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdzcCcpIj48c3Bhbj7wn5OKIFMmYW1wO1AgNTAwIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0iYXItc3AiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1zcCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9Imctc3AiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnZGonKSI+PHNwYW4+8J+PmyBEb3cgSm9uZXMgVG9wIDIwPC9zcGFuPjxzcGFuIGlkPSJhci1kaiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWRqIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1kaiI+PC9kaXY+PC9kaXY+CgogIDxkaXYgY2xhc3M9InRibC13cmFwIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5Db21tb2RpdGllczwvc3Bhbj48L2Rpdj4KICAgIDx0YWJsZSBjbGFzcz0idGJsLW1rdCI+CiAgICAgIDx0aGVhZD48dHI+PHRoPkF0aXZvPC90aD48dGggY2xhc3M9InIiPsOabHRpbW88L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5XVEkvQ0w8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5QZXRyw7NsZW8gV1RJPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImNsLXAiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkdPTEQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5PdXJvPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImdvbGQtcCI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+U0lMVkVSPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+UHJhdGE8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0ic2lsdmVyLXAiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkNPUFBFUjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkNvYnJlPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImNvcHBlci1wIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0idGJsLXdyYXAiPgogICAgPGRpdiBjbGFzcz0idGJsLWhkciI+PHNwYW4gY2xhc3M9InRibC1oZHItdGl0bGUiPkJpdGNvaW48L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+SW5mbzwvdGg+PC90cj48L3RoZWFkPgogICAgICA8dGJvZHk+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJUQy9VU0Q8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5CaXRjb2luIFNwb3Q8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iYnRjLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJ0Yy1jIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+QlRDIFJTSTwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlJTSSBTZW1hbmFsPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJ0Yy1yc2kiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+RnVuZGluZzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlRheGEgOGggQlRDPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJ0Yy1mdW5kIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PHRkIGNsYXNzPSJyIj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkZlYXIgJmFtcDsgR3JlZWQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj7DjW5kaWNlIHNlbnRpbWVudG88L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iZmctdmFsIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBpZD0iZmctbGJsIiBzdHlsZT0iZm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KICA8Zm9vdGVyPjxzcGFuIGlkPSJmb290ZXItdGltZSI+4oCUPC9zcGFuPjxzcGFuPlRyYWRlciBEZXNrIHYxMS44PC9zcGFuPjwvZm9vdGVyPgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIElORElDQURPUkVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWluZGljYWRvcmVzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImRvdCI+PC9zcGFuPkNpY2xvIEJpdGNvaW48L2Rpdj4KICA8ZGl2IGlkPSJidGMtY3ljbGUtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTRweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDE1MHB4O2dhcDoxMHB4O21hcmdpbjoxNHB4IDAiPgogICAgPGRpdiBpZD0iZmctYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweCI+Q2FycmVnYW5kbyBGZWFyICZhbXA7IEdyZWVkLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTZweDt0ZXh0LWFsaWduOmNlbnRlciI+CiAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjZweDtmb250LXdlaWdodDo2MDA7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHgiPkJUQy9VU0Q8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImJ0Yy1pbmQtcCI+4oCUPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5CVEMgU2VtYW5hbDwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgoKICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OmZsZXgtZW5kO21hcmdpbi1ib3R0b206MTBweCI+CiAgICA8YnV0dG9uIG9uY2xpY2s9InRvZ2dsZUFsbEluZCgpIiBpZD0iYnRuLWFsbC1pbmQiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2NvbG9yOnZhcigtLWFjY2VudCk7cGFkZGluZzo1cHggMTRweDtmb250LXNpemU6MTFweDtjdXJzb3I6cG9pbnRlcjtmb250LWZhbWlseTppbmhlcml0O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4Ij7iiJIgUmVjb2xoZXIgVG9kb3M8L2J1dHRvbj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3BldHI0JykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9ImluZC1hY2MtdGl0bGUiPlBFVFI0IOKAlCBQZXRyb2JyYXMgUE48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+UGV0csOzbGVvICZhbXA7IEfDoXMgwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdwZXRyNCcpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1wZXRyNCI+4pa8PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWJvZHkgb3BlbiIgaWQ9InBldHI0LWluZC13cmFwIj48ZGl2IGlkPSJwZXRyNC1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3ZhbGUzJykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9ImluZC1hY2MtdGl0bGUiPlZBTEUzIOKAlCBWYWxlIE9OPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPk1pbmVyYcOnw6NvIMK3IGNsaXF1ZSBwYXJhIGV4cGFuZGlyL3JlY29saGVyPC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHgiPjxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxM3B4IiBvbmNsaWNrPSJldmVudC5zdG9wUHJvcGFnYXRpb24oKTtybCgndmFsZTMnKSI+4oa7PC9zcGFuPjxzcGFuIGlkPSJhci1pbmQtdmFsZTMiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJ2YWxlMy1pbmQtd3JhcCI+PGRpdiBpZD0idmFsZTMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iaW5kLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWhkciIgb25jbGljaz0idG9nSW5kKCdiYmFzMycpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5CQkFTMyDigJQgQmFuY28gZG8gQnJhc2lsIE9OPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPkJhbmNvcyDCtyBjbGlxdWUgcGFyYSBleHBhbmRpci9yZWNvbGhlcjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij48c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTNweCIgb25jbGljaz0iZXZlbnQuc3RvcFByb3BhZ2F0aW9uKCk7cmwoJ2JiYXMzJykiPuKGuzwvc3Bhbj48c3BhbiBpZD0iYXItaW5kLWJiYXMzIj7ilrw8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtYm9keSBvcGVuIiBpZD0iYmJhczMtaW5kLXdyYXAiPjxkaXYgaWQ9ImJiYXMzLWluZCI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImluZC1hY2MiPgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1oZHIiIG9uY2xpY2s9InRvZ0luZCgnYXhpYTMnKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy10aXRsZSI+QVhJQTMg4oCUIEF1cmVuIEVuZXJnaWEgT048L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+RW5lcmdpYSBFbMOpdHJpY2EgwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdheGlhMycpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1heGlhMyI+4pa8PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWJvZHkgb3BlbiIgaWQ9ImF4aWEzLWluZC13cmFwIj48ZGl2IGlkPSJheGlhMy1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3JveG8zNCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5ST1hPMzQg4oCUIE51YmFuayBCRFI8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+RmludGVjaCDCtyBjbGlxdWUgcGFyYSBleHBhbmRpci9yZWNvbGhlcjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij48c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTNweCIgb25jbGljaz0iZXZlbnQuc3RvcFByb3BhZ2F0aW9uKCk7cmwoJ3JveG8zNCcpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1yb3hvMzQiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJyb3hvMzQtaW5kLXdyYXAiPjxkaXYgaWQ9InJveG8zNC1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBQT1NJw4fDlUVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLXBvc2ljb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Imp1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuIj48c3BhbiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+T3BlcmHDp8O1ZXMgQXRpdmFzPC9zcGFuPjxidXR0b24gb25jbGljaz0idG9nZ2xlQWxsUG9zKCkiIGlkPSJidG4tYWxsLXBvcyIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y29sb3I6dmFyKC0tYWNjZW50KTtwYWRkaW5nOjRweCAxMnB4O2ZvbnQtc2l6ZToxMXB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NjAwIj7iiJIgUmVjb2xoZXIgVG9kYXM8L2J1dHRvbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1wdCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5QRVRSNDwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5DYWxsIFZlbmRpZGEgUEVUUkwzMTkgwrcgU3RyaWtlIFIkMzAsODUgwrcgQiZTIDksNCUgwrcgTUMgPHNwYW4gaWQ9InB0LW1jLXJ0LWgiPmNhbGM8L3NwYW4+PC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtcmlnaHQiPgogICAgICAgIDxkaXY+PGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9InB0LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9InB0LWMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDxzcGFuIGlkPSJhci1wb3MtcHQiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCkiPuKWvDwvc3Bhbj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtYm9keSBvcGVuIiBpZD0iYm9keS1wb3MtcHQiPgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TdHJpa2UgKFBFVFJMMzE5KTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgMzAsODU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByZcOnbyB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InB0LWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTcvMTIvMjAyNiDCtyA8c3BhbiBpZD0icHQtZGlhcyI+MTgzPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj40Myw0JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj45LDQlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBNQyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayIgaWQ9InB0LW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhbGwgc2VyIGV4ZXJjaWRhPC9kaXY+CiAgICAgIDxkaXYgaWQ9InB0LW1jLWwiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEycHgiPkNhbGN1bGFuZG8gNS4wMDAgY2Vuw6FyaW9zLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9InB0LW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gZXhlcmNlcjwvZGl2PjxkaXYgY2xhc3M9Iml2IiBpZD0icHQtbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icHQtbWMtdiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4O2xpbmUtaGVpZ2h0OjEuNSIgaWQ9InB0LW1jLWkiPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWhkciIgb25jbGljaz0idG9nUG9zKCdwb3MtdmwnKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0icG9zLWFjYy10ayI+VkFMRTM8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+Q2FsbCBWZW5kaWRhIFZBTEVCNTc0IMK3IFN0cmlrZSBSJDU3LDQwIMK3IEImUyAxNCwyJSDCtyBNQyA8c3BhbiBpZD0idmwtbWMtcnQtaCI+Y2FsYzwvc3Bhbj48L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0idmwtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icGMyIiBpZD0idmwtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPHNwYW4gaWQ9ImFyLXBvcy12bCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy12bCI+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlN0cmlrZSAoVkFMRUI1NzQpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA1Nyw0MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJlw6dvIHZzIHN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YgaXRtIiBpZD0idmwtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4xOC8wMi8yMDI3IMK3IDxzcGFuIGlkPSJ2bC1kaWFzIj4yNDY8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZvbC4gSW1wbC48L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjcxLDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBCJmFtcDtTIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjE0LDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBNQyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayIgaWQ9InZsLW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhbGwgc2VyIGV4ZXJjaWRhPC9kaXY+CiAgICAgIDxkaXYgaWQ9InZsLW1jLWwiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEycHgiPkNhbGN1bGFuZG8gNS4wMDAgY2Vuw6FyaW9zLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9InZsLW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gZXhlcmNlcjwvZGl2PjxkaXYgY2xhc3M9Iml2IiBpZD0idmwtbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0idmwtbWMtdiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4O2xpbmUtaGVpZ2h0OjEuNSIgaWQ9InZsLW1jLWkiPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWhkciIgb25jbGljaz0idG9nUG9zKCdwb3MtYTMnKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0icG9zLWFjYy10ayI+QVhJQTM8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+QVhJQTMgKEEpIMK3IEJpZGlyZWNpb25hbCDCtyBWZW5jIDE0LzA5LzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0iYTMtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icGMyIiBpZD0iYTMtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPHNwYW4gaWQ9ImFyLXBvcy1hMyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1hMyI+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPktETyAoLTIwJSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDQzLDUxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LVU8gKCsyNiw2JSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDY4LDc2PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5HYW5obyBzLyBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+R2FuaG8gYy8gYmFyLiBhbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4rNCUgZml4bzwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE0LzA5LzIwMjYgwrcgPHNwYW4gaWQ9ImEzLWRpYXMiPjg5PC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTMta2RvIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtVTzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1rdW8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1zdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJhMy1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzLW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+U2VtIEJhcnJlaXJhIOKchTwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIiBpZD0iYTMtbWMtbmIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzLW1jLWt1Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpdiBkb3duIiBpZD0iYTMtbWMta2QiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzLW1jLXZvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJhMy1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1hY2MiPgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1oZHIiIG9uY2xpY2s9InRvZ1BvcygncG9zLWEzYicpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5BWElBMzwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5BWElBMyAoQikgwrcgQmlkaXJlY2lvbmFsIElPTiBJdGHDuiDCtyBWZW5jIDAyLzEwLzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0iYTNiLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9ImEzYi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLWEzYiIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1hM2IiPgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA0MCw1Mjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S1VPICgrMjQlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNjIsODE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+YXTDqSArMzEsMiUgLyArMjAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPis0JSBmaXhvICgxMiwzMyUgYS5hLik8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4wMi8xMC8yMDI2IMK3IDxzcGFuIGlkPSJhM2ItZGlhcyI+MTA3PC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLWtkbyI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLWt1byI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzYi1zdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siIGlkPSJhM2ItbWMtbmIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzYi1tYy1rdSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaXYgZG93biIgaWQ9ImEzYi1tYy1rZCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTNiLW1jLXZvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJhM2ItbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1yeCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5ST1hPMzQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+Q2FsbCBWZW5kaWRhIFJPWE9HMTA1IMK3IFN0cmlrZSBSJDEwLDUwIMK3IEImUyA2MCw0JSDimqAgwrcgTUMgPHNwYW4gaWQ9InJ4LW1jLXJ0LWgiPmNhbGM8L3NwYW4+PC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtcmlnaHQiPgogICAgICAgIDxkaXYgc3R5bGU9InRleHQtYWxpZ246cmlnaHQiPjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJyeC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJyeC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLXJ4IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLXJ4Ij4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChST1hPRzEwNSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDEwLDUwIMK3IElUTSDimqA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByZcOnbyB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InJ4LWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTYvMDcvMjAyNiDCtyA8c3BhbiBpZD0icngtZGlhcyI+Mjk8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZvbC4gSW1wbC48L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjMzLDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EZWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MCw2NDM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIEImYW1wO1MgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3YgaXRtIj42MCw0JSDimqA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIE1DIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IGl0bSIgaWQ9InJ4LW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5PYmpldGl2bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPkZlY2hhciBhYmFpeG8gZGUgUiQgMTAsNTA8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FsbCBzZXIgZXhlcmNpZGE8L2Rpdj4KICAgICAgPGRpdiBpZD0icngtbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kbyA1LjAwMCBjZW7DoXJpb3MuLi48L2Rpdj4KICAgICAgPGRpdiBpZD0icngtbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Qcm9iLiBleGVyY2VyPC9kaXY+PGRpdiBjbGFzcz0iaXYiIGlkPSJyeC1tYy1zIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJyeC1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHg7bGluZS1oZWlnaHQ6MS41IiBpZD0icngtbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjIwcHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWhkciIgb25jbGljaz0idG9nUG9zKCdwb3MtYmInKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0icG9zLWFjYy10ayI+QkJBUzM8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+Q2FsbCBWZW5kaWRhIEJCQVNIMjEgwrcgU3RyaWtlIFIkMjEsNjUgwrcgQiZTIDIxLDMlIMK3IE1DIDxzcGFuIGlkPSJiYi1tYy1ydC1oIj5jYWxjPC9zcGFuPjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLXJpZ2h0Ij4KICAgICAgICA8ZGl2PjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJiYi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJiYi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLWJiIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLWJiIj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChCQkFTSDIxKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgMjEsNjUgwrcgSVRNPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJiYi1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjIwLzA4LzIwMjYgwrcgPHNwYW4gaWQ9ImJiLWRpYXMiPjY0PC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4yNywxJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RGVsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4wLDI0OTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4yMSwzJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gTUMgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siIGlkPSJiYi1tYy1ydCI+Y2FsYy4uLjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+T2JqZXRpdm88L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5GZWNoYXIgYWJhaXhvIGRlIFIkIDIxLDY1PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhbGwgc2VyIGV4ZXJjaWRhPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImJiLW1jLWwiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEycHgiPkNhbGN1bGFuZG8gNS4wMDAgY2Vuw6FyaW9zLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImJiLW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gZXhlcmNlcjwvZGl2PjxkaXYgY2xhc3M9Iml2IiBpZD0iYmItbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYmItbWMtdiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4O2xpbmUtaGVpZ2h0OjEuNSIgaWQ9ImJiLW1jLWkiPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIiBzdHlsZT0ib3BhY2l0eTouNTtib3JkZXItY29sb3I6dmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdC1jb2xvcjp2YXIoLS1tdXRlZCkiPgogICAgPGRpdiBjbGFzcz0icHQiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjE2cHgiPkFYSUEzIFNob3J0IFN0cmFuZ2xlPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+PGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Q2FsbCBWLiBBWElBSTUwNTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPlIkIDUwLDUwPC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPuKchSBBw6fDtWVzIGxpYmVyYWRhczwvc3Bhbj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyIgc3R5bGU9Im9wYWNpdHk6LjU7Ym9yZGVyLWNvbG9yOnZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQtY29sb3I6dmFyKC0tbXV0ZWQpIj4KICAgIDxkaXYgY2xhc3M9InB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxNnB4Ij5ST1hPMzQgUHJlZml4YWRvIDcsMSU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5FbmNlcnJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4wNC8wNi8yMDI2PC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPuKchSB+NSwxNyUgKDcyJSBkbyBhbHZvKTwvc3Bhbj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBDQUxFTkTDgVJJTyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1jYWxlbmRhcmlvIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxNHB4Ij4KICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKTtmb250LXdlaWdodDo1MDAiPvCfh7rwn4e4IPCfh6fwn4e3IPCfh6rwn4e6IPCfh6zwn4enIPCfh6jwn4ezIPCfh6/wn4e1IPCfh6nwn4eqIMK3IEltcGFjdG8gTcOpZGlvKzwvZGl2PgogICAgPGJ1dHRvbiBvbmNsaWNrPSJsb2FkQ2FsKCkiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWFjY2VudCk7Ym9yZGVyOm5vbmU7Y29sb3I6I2ZmZjtwYWRkaW5nOjhweCAxOHB4O2ZvbnQtc2l6ZToxMnB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NzAwO2xldHRlci1zcGFjaW5nOi41cHgiPuKGuyBBdHVhbGl6YXI8L2J1dHRvbj4KICA8L2Rpdj4KICA8ZGl2IGlkPSJjYWwtc3QiIHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo4cHgiPjwvZGl2PgogIDxkaXYgaWQ9ImNhbC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoyNHB4O3RleHQtYWxpZ246Y2VudGVyIj5DbGlxdWUgZW0gQXR1YWxpemFyPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgQj0naHR0cHM6Ly90cmFkZXItZGVzay5vbnJlbmRlci5jb20nOwpjb25zdCBTRUc9ewogIGZpbjpbJ0lUVUI0JywnQkJEQzQnLCdCQkFTMycsJ1NBTkIxMScsJ0IzU0EzJywnQlBBQzExJywnSVRTQTQnLCdCUlNSNicsJ0FCQ0I0JywnQk1HQjQnXSwKICBwZXQ6WydQRVRSNCcsJ1BFVFIzJywnUFJJTzMnLCdCUkFWMycsJ1ZCQlIzJywnQ1NBTjMnLCdSRUNWMycsJ1VHUEEzJywnU0VRTDMnLCdHR0JSNCddLAogIG1pbjpbJ1ZBTEUzJywnR0dCUjQnLCdDU05BMycsJ1VTSU01JywnQlJBUDQnLCdGRVNBNCcsJ0NNSU4zJywnQ0JBVjMnLCdHT0FVNCcsJ1BHTU4zJ10sCiAgbWF0OlsnU1VaQjMnLCdLTEJOMTEnLCdEWENPMycsJ1VOSVA2JywnUkFOSTMnLCdPUlZSMycsJ1NNVE8zJywnRlJBUzMnLCdMUFNCMycsJ0NTVUQzJ10sCiAgdXRpOlsnQVhJQTMnLCdFUVRMMycsJ0NQRkUzJywnU0JTUDMnLCdDTUlHNCcsJ0VOR0kxMScsJ1RBRUUxMScsJ0FVUkUzJywnRUdJRTMnLCdDUExFMyddLAogIGNjOiBbJ1JFTlQzJywnTFJFTjMnLCdNR0xVMycsJ0NZUkUzJywnTVJWRTMnLCdBWlpBMycsJ1ZJVkEzJywnU0JGRzMnLCdZRFVRMycsJ01PVkkzJ10sCiAgY246IFsnQUJFVjMnLCdKQlNTMycsJ0JSRlMzJywnTkFUVTMnLCdNRElBMycsJ0JFRUYzJywnU0xDRTMnLCdNVFJFMycsJ0NBTUwzJywnUENBUjMnXSwKICBzYXU6WydSRE9SMycsJ0hBUFYzJywnRkxSWTMnLCdEQVNBMycsJ1FVQUwzJywnT05DTzMnLCdQTlZMMycsJ09EUFYzJywnTUFURDMnLCdBQUxSMyddLAogIGluZDpbJ1dFR0UzJywnRU1CUjMnLCdSQUlMMycsJ1RHTUEzJywnUk9NSTMnLCdWTElEMycsJ1RVUFkzJywnSVJCUjMnLCdQT01PNCcsJ0xBVlYzJ10sCiAgdGl0OlsnVklWVDMnLCdUSU1TMycsJ1RPVFZTMycsJ1BPU0kzJywnTUxBUzMnLCdBTklNMycsJ0lOVEIzJywnTFdTQTMnLCdDQVNIMycsJ09JQlIzJ10sCn07CmNvbnN0IFVTU0VHPXsKICBtNzpbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdHT09HTCcsJ01FVEEnLCdUU0xBJ10sCiAgbnE6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdDT1NUJywnTkZMWCcsJ1FDT00nLCdBTUQnLCdBREJFJywnSU5UQycsJ0NTQ08nXSwKICBzcDpbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdNRVRBJywnR09PR0wnLCdUU0xBJywnQVZHTycsJ0JSSy5CJywnSlBNJywnTExZJywnVicsJ1VOSCcsJ1hPTScsJ01BJywnTkZMWCcsJ1BHJywnSk5KJywnSEQnLCdCQUMnXSwKICBkajpbJ1VOSCcsJ0dTJywnSEQnLCdTSFcnLCdDQVQnLCdBWFAnLCdNQ0QnLCdBTUdOJywnVicsJ1RSVicsJ0lCTScsJ0pQTScsJ0hPTicsJ0NSTScsJ0NWWCcsJ0FBUEwnLCdNU0ZUJywnRElTJywnTktFJywnQkEnXQp9Owpjb25zdCBmUj12PT52IT1udWxsPydSJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmVT12PT52IT1udWxsPydVUyQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlA9dj0+diE9bnVsbD9OdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KTon4oCUJzsKZnVuY3Rpb24gRShpZCx0KXtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47ZS50ZXh0Q29udGVudD10O2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KZnVuY3Rpb24gQ2hUYmwoaWRWLGlkUGN0LG5vdyxwcmV2LHRwKXsKICBjb25zdCBkaWZmPW5vdy1wcmV2LHBjdD0oZGlmZi9NYXRoLmFicyhwcmV2fHwxKSoxMDApLHNnPWRpZmY+PTA/JysnOicnOwogIGNvbnN0IGNscz1kaWZmPjA/J2NoZyBjaGctdXAnOmRpZmY8MD8nY2hnIGNoZy1kbic6J2NoZyBjaGctZmwnOwogIGxldCB2YXJTdHI9Jyc7CiAgaWYodHA9PT0ncicpdmFyU3RyPXNnKydSJCAnK01hdGguYWJzKGRpZmYpLnRvRml4ZWQoMik7CiAgZWxzZSBpZih0cD09PSd1Jyl2YXJTdHI9c2crTWF0aC5hYnMoZGlmZikudG9GaXhlZCgyKTsKICBlbHNlIHZhclN0cj1zZytNYXRoLmFicyhkaWZmKS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOwogIGNvbnN0IHBjdFN0cj1zZytwY3QudG9GaXhlZCgyKSsnJSc7CiAgY29uc3QgZXY9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWRWKTtpZihldil7ZXYudGV4dENvbnRlbnQ9dmFyU3RyO2V2LmNsYXNzTmFtZT1jbHM7fQogIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkUGN0KTtpZihlcCl7ZXAudGV4dENvbnRlbnQ9cGN0U3RyO2VwLmNsYXNzTmFtZT1jbHM7fQp9CmZ1bmN0aW9uIENoKGlkLG4scCx0cCl7CiAgY29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuOwogIGNvbnN0IGQ9bi1wLHBjPShkL01hdGguYWJzKHB8fDEpKjEwMCkudG9GaXhlZCgyKSxzZz1kPj0wPycrJzonJzsKICBpZih0cD09PSdyJyllLnRleHRDb250ZW50PXNnKydSJCAnK01hdGguYWJzKGQpLnRvRml4ZWQoMikrJyAoJytzZytwYysnJSknOwogIGVsc2UgaWYodHA9PT0ndScpZS50ZXh0Q29udGVudD1zZytkLnRvRml4ZWQoMikrJyAoJytzZytwYysnJSknOwogIGVsc2UgZS50ZXh0Q29udGVudD1zZytNYXRoLmFicyhkKS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKycgKCcrc2crcGMrJyUpJzsKICBlLmNsYXNzTmFtZT0nY2MgJysoZD4wPydjaGctdXAnOmQ8MD8nY2hnLWRuJzonY2hnLWZsJyk7Cn0KZnVuY3Rpb24gc3codCxlbCl7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYicpLmZvckVhY2goeD0+eC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYi1jb250ZW50JykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndGFiLScrdCkuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7CiAgaWYoZWwpZWwuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7CiAgaWYodD09PSdpbmRpY2Fkb3JlcycmJiF3aW5kb3cuX0lMKXt3aW5kb3cuX0lMPXRydWU7bG9hZEluZCgpO30KICBpZih0PT09J2NhbGVuZGFyaW8nKXtzZXRUaW1lb3V0KCgpPT5sb2FkQ2FsKCksMTAwKTt9Cn0KZnVuY3Rpb24gdGcoaWQpewogIGNvbnN0IGI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NiLScraWQpLGE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLScraWQpOwogIGlmKCFiKXJldHVybjtjb25zdCBvcD1iLnN0eWxlLmRpc3BsYXkhPT0nYmxvY2snOwogIGIuc3R5bGUuZGlzcGxheT1vcD8nYmxvY2snOidub25lJzsKICBpZihhKWEudGV4dENvbnRlbnQ9b3A/J+KWsic6J+KWvCc7CiAgaWYob3AmJiFiLmRhdGFzZXQubCl7Yi5kYXRhc2V0Lmw9JzEnO2xvYWRTZWcoaWQpO30KfQoKYXN5bmMgZnVuY3Rpb24gbG9hZFNlZyhpZCl7CiAgY29uc3QgZz1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZy0nK2lkKTtpZighZylyZXR1cm47CiAgY29uc3QgcGZ4PWlkKydfJzsKICBpZihVU1NFR1tpZF0pewogICAgY29uc3QgdGtzPVVTU0VHW2lkXTsKICAgIGcuaW5uZXJIVE1MPXRrcy5tYXAodD0+e2NvbnN0IHRpZD10LnJlcGxhY2UoL1teYS16QS1aMC05XS9nLCdfJyk7cmV0dXJuICc8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImNsIj5VUzwvZGl2PjxkaXYgY2xhc3M9ImNuIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSInK3BmeCt0aWQrJ19wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9IicrcGZ4K3RpZCsnX2MiPuKAlDwvZGl2PjwvZGl2Pic7fSkuam9pbignJyk7CiAgICB0cnl7CiAgICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL3VzL3F1b3Rlcz90aWNrZXJzPScrdGtzLmpvaW4oJywnKSk7CiAgICAgIGlmKCFyLm9rKXJldHVybjsKICAgICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgICAgT2JqZWN0LmVudHJpZXMoZCkuZm9yRWFjaCgoW3Qsdl0pPT57CiAgICAgICAgY29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTsKICAgICAgICBjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfcCcpOwogICAgICAgIGlmKGVwJiZ2LnByaWNlKXtlcC50ZXh0Q29udGVudD0nJCcrTnVtYmVyKHYucHJpY2UpLnRvRml4ZWQoMik7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICBpZih2LnByaWNlJiZ2LnByZXYpQ2gocGZ4K3RpZCsnX2MnLHYucHJpY2Usdi5wcmV2LCd1Jyk7CiAgICAgIH0pOwogICAgfWNhdGNoKGUpe30KICAgIHJldHVybjsKICB9CiAgY29uc3QgdGtzPVNFR1tpZF07aWYoIXRrcylyZXR1cm47CiAgZy5pbm5lckhUTUw9JzxkaXYgY2xhc3M9InRibC13cmFwIj48dGFibGUgY2xhc3M9InRibC1ta3QiPjx0aGVhZD48dHI+PHRoPkF0aXZvPC90aD48dGggY2xhc3M9InIiPsOabHRpbW88L3RoPjx0aCBjbGFzcz0iciI+VmFyaWHDp8OjbzwvdGg+PHRoIGNsYXNzPSJyIj5WYXIuJTwvdGg+PC90cj48L3RoZWFkPjx0Ym9keT4nKwogICAgdGtzLm1hcCh0PT57Y29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTtyZXR1cm4gJzx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj4nK3QrJzwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSInK3BmeCt0aWQrJ19wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSInK3BmeCt0aWQrJ192Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L3NwYW4+PC90ZD48L3RyPic7fSkuam9pbignJykrCiAgICAnPC90Ym9keT48L3RhYmxlPjwvZGl2Pic7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOnRrcy5tYXAodD0+J0JNRkJPVkVTUEE6Jyt0KX0sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IG5ldyBFcnJvcignVFYgZmFpbCcpOwogICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IGxvYWRlZD1uZXcgU2V0KCk7CiAgICAoZC5kYXRhfHxbXSkuZm9yRWFjaCh4PT57CiAgICAgIGNvbnN0IHQ9eC5zLnJlcGxhY2UoJ0JNRkJPVkVTUEE6JywnJykudG9Mb3dlckNhc2UoKTsKICAgICAgY29uc3RbYyxjYV09eC5kfHxbXTsKICAgICAgaWYoYyE9bnVsbCl7CiAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3QrJ19wJyk7CiAgICAgICAgaWYoZXApe2VwLnRleHRDb250ZW50PWZSKGMpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTtsb2FkZWQuYWRkKHQpO30KICAgICAgICBDaFRibChwZngrdCsnX3YnLHBmeCt0KydfYycsYyxjLShjYXx8MCksJ3InKTsKICAgICAgfQogICAgfSk7CiAgICAvLyBGYWxsYmFjayB2aWEgYnJhcGkgcGFyYSB0aWNrZXJzIHF1ZSBUViBuw6NvIHJldG9ybm91CiAgICBjb25zdCBtaXNzaW5nPXRrcy5maWx0ZXIodD0+IWxvYWRlZC5oYXModC50b0xvd2VyQ2FzZSgpKSk7CiAgICBpZihtaXNzaW5nLmxlbmd0aD4wKXsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0IHJiPWF3YWl0IGZldGNoKEIrJy90di9icmF6aWwnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgICBib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOm1pc3NpbmcubWFwKHQ9PidCTUZCT1ZFU1BBOicrdCl9LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7CiAgICAgICAgLy8gU2VndW5kYSB0ZW50YXRpdmEgaW1lZGlhdGEKICAgICAgfWNhdGNoKGUyKXt9CiAgICAgIC8vIEZhbGxiYWNrIGluZGl2aWR1YWwgdmlhIC9pbmRpY2F0b3JzCiAgICAgIGZvcihjb25zdCB0IG9mIG1pc3NpbmcpewogICAgICAgIHRyeXsKICAgICAgICAgIGNvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdCsnLlNBJyk7CiAgICAgICAgICBpZighcjIub2spY29udGludWU7CiAgICAgICAgICBjb25zdCBkMj1hd2FpdCByMi5qc29uKCk7CiAgICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICAgIGNvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7CiAgICAgICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19wJyk7CiAgICAgICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mUihkMi5wcmVjb19hdHVhbCk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICAgICAgaWYoZDIucHJlY29fYW50ZXJpb3IpQ2hUYmwocGZ4K3RpZCsnX3YnLHBmeCt0aWQrJ19jJyxkMi5wcmVjb19hdHVhbCxkMi5wcmVjb19hbnRlcmlvciwncicpOwogICAgICAgICAgfQogICAgICAgIH1jYXRjaChlMil7fQogICAgICB9CiAgICB9CiAgfWNhdGNoKGUpewogICAgLy8gVFYgZmFsaG91IGNvbXBsZXRhbWVudGUg4oCUIGZhbGxiYWNrIHBhcmEgdG9kb3MgdmlhIC9pbmRpY2F0b3JzCiAgICBmb3IoY29uc3QgdCBvZiB0a3Muc2xpY2UoMCw2KSl7CiAgICAgIHRyeXsKICAgICAgICBjb25zdCByMj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy8nK3QrJy5TQScpOwogICAgICAgIGlmKCFyMi5vayljb250aW51ZTsKICAgICAgICBjb25zdCBkMj1hd2FpdCByMi5qc29uKCk7CiAgICAgICAgaWYoZDIucHJlY29fYXR1YWwpewogICAgICAgICAgY29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTsKICAgICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19wJyk7CiAgICAgICAgICBpZihlcCl7ZXAudGV4dENvbnRlbnQ9ZlIoZDIucHJlY29fYXR1YWwpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CiAgICAgICAgfQogICAgICB9Y2F0Y2goZTIpe30KICAgIH0KICB9Cn0KCmZ1bmN0aW9uIGV4cGFuZEFsbCgpewogIGNvbnN0IGJ0bj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRuLWV4cGFuZCcpOwogIGNvbnN0IHNlZ3M9WydmaW4nLCdwZXQnLCdtaW4nLCdtYXQnLCd1dGknLCdjYycsJ2NuJywnc2F1JywnaW5kJywndGl0J107CiAgY29uc3QgYW55T3Blbj1zZWdzLnNvbWUoaWQ9PmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYi0nK2lkKT8uc3R5bGUuZGlzcGxheT09PSdibG9jaycpOwogIHNlZ3MuZm9yRWFjaChpZD0+ewogICAgY29uc3QgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2ItJytpZCksYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXItJytpZCk7CiAgICBpZighYilyZXR1cm47CiAgICBpZihhbnlPcGVuKXtiLnN0eWxlLmRpc3BsYXk9J25vbmUnO2lmKGEpYS50ZXh0Q29udGVudD0n4pa8Jzt9CiAgICBlbHNlewogICAgICBiLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJztpZihhKWEudGV4dENvbnRlbnQ9J+KWsic7CiAgICAgIGlmKCFiLmRhdGFzZXQubCl7Yi5kYXRhc2V0Lmw9JzEnO2xvYWRTZWcoaWQpO30KICAgIH0KICB9KTsKICBpZihidG4pYnRuLnRleHRDb250ZW50PWFueU9wZW4/JysgRXhwYW5kaXIgVG9kb3MnOifiiJIgUmVjb2xoZXIgVG9kb3MnOwp9CmZ1bmN0aW9uIHRvZ1BvcyhpZCl7CiAgY29uc3QgYm9keT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYm9keS0nK2lkKTsKICBjb25zdCBhcnI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLScraWQpOwogIGlmKCFib2R5KXJldHVybjsKICBjb25zdCBvcGVuPWJvZHkuY2xhc3NMaXN0LmNvbnRhaW5zKCdvcGVuJyk7CiAgYm9keS5jbGFzc0xpc3QudG9nZ2xlKCdvcGVuJywhb3Blbik7CiAgaWYoYXJyKWFyci50ZXh0Q29udGVudD1vcGVuPyfilrYnOifilrwnOwp9CmZ1bmN0aW9uIHRvZ2dsZUFsbFBvcygpewogIGNvbnN0IGlkcz1bJ3Bvcy1wdCcsJ3Bvcy12bCcsJ3Bvcy1hMycsJ3Bvcy1hM2InLCdwb3MtcngnLCdwb3MtYmInXTsKICBjb25zdCBidG49ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0bi1hbGwtcG9zJyk7CiAgY29uc3QgYW55T3Blbj1pZHMuc29tZShpZD0+ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JvZHktJytpZCk/LmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpKTsKICBpZHMuZm9yRWFjaChpZD0+ewogICAgY29uc3QgYm9keT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYm9keS0nK2lkKTsKICAgIGNvbnN0IGFycj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXItJytpZCk7CiAgICBpZihib2R5KXtib2R5LmNsYXNzTGlzdC50b2dnbGUoJ29wZW4nLCFhbnlPcGVuKTtpZihhcnIpYXJyLnRleHRDb250ZW50PWFueU9wZW4/J+KWtic6J+KWvCc7fQogIH0pOwogIGlmKGJ0bilidG4udGV4dENvbnRlbnQ9YW55T3Blbj8n4oiSIFJlY29saGVyIFRvZGFzJzonKyBFeHBhbmRpciBUb2Rhcyc7Cn0KZnVuY3Rpb24gdG9nSW5kKGlkKXsKICBjb25zdCBib2R5PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKyctaW5kLXdyYXAnKTsKICBjb25zdCBhcnI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLWluZC0nK2lkKTsKICBpZighYm9keSlyZXR1cm47CiAgY29uc3Qgb3Blbj1ib2R5LmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpOwogIGJvZHkuY2xhc3NMaXN0LnRvZ2dsZSgnb3BlbicsIW9wZW4pOwogIGlmKGFycilhcnIudGV4dENvbnRlbnQ9b3Blbj8n4pa2Jzon4pa8JzsKfQpmdW5jdGlvbiB0b2dnbGVBbGxJbmQoKXsKICBjb25zdCBpZHM9WydwZXRyNCcsJ3ZhbGUzJywnYmJhczMnLCdheGlhMycsJ3JveG8zNCddOwogIGNvbnN0IGJ0bj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRuLWFsbC1pbmQnKTsKICBjb25zdCBhbnlPcGVuPWlkcy5zb21lKGlkPT5kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZC13cmFwJyk/LmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpKTsKICBpZHMuZm9yRWFjaChpZD0+ewogICAgY29uc3QgYm9keT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZC13cmFwJyk7CiAgICBjb25zdCBhcnI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLWluZC0nK2lkKTsKICAgIGlmKGJvZHkpe2JvZHkuY2xhc3NMaXN0LnRvZ2dsZSgnb3BlbicsIWFueU9wZW4pO2lmKGFycilhcnIudGV4dENvbnRlbnQ9YW55T3Blbj8n4pa2Jzon4pa8Jzt9CiAgfSk7CiAgaWYoYnRuKWJ0bi50ZXh0Q29udGVudD1hbnlPcGVuPycrIEV4cGFuZGlyIFRvZG9zJzon4oiSIFJlY29saGVyIFRvZG9zJzsKfQphc3luYyBmdW5jdGlvbiBmSEwoKXsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7CiAgICBpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IGJwPXBhcnNlRmxvYXQoZC5CVEN8fDApOwogICAgaWYoYnA+MCl7RSgnYnRjLXAnLGZVKGJwKSk7Q2goJ2J0Yy1jJyxicCxicCowLjk5LCd1Jyk7fQogICAgdHJ5ewogICAgICBjb25zdCByMj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcycsZGV4Oid4eXonfSl9KTsKICAgICAgaWYocjIub2spe2NvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICBpZihkMlsneHl6OkNMJ10pRSgnY2wtcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDTCddKS50b0ZpeGVkKDIpKTsKICAgICAgICBpZihkMlsneHl6OkdPTEQnXSlFKCdnb2xkLXAnLCckJytOdW1iZXIoZDJbJ3h5ejpHT0xEJ10pLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpOwogICAgICAgIGlmKGQyWyd4eXo6U0lMVkVSJ10pRSgnc2lsdmVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6U0lMVkVSJ10pLnRvRml4ZWQoMikpOwogICAgICAgIGlmKGQyWyd4eXo6Q09QUEVSJ10pRSgnY29wcGVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q09QUEVSJ10pLnRvRml4ZWQoMykpO30KICAgIH1jYXRjaChlKXt9CiAgfWNhdGNoKGUpe30KfQphc3luYyBmdW5jdGlvbiBmVFYoKXsKICBjb25zdCBvdXQ9e307CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOlsnQk1GQk9WRVNQQTpQRVRSNCcsJ0JNRkJPVkVTUEE6SVRVQjQnLCdCTUZCT1ZFU1BBOlZBTEUzJywnQk1GQk9WRVNQQTpCQkRDNCcsJ0JNRkJPVkVTUEE6QUJFVjMnLCdCTUZCT1ZFU1BBOkJCQVMzJywnQk1GQk9WRVNQQTpXRUdFMycsJ0JNRkJPVkVTUEE6SUJPViddfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pOwogICAgaWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTsoZC5kYXRhfHxbXSkuZm9yRWFjaCh4PT57Y29uc3RbYyxjYV09eC5kfHxbXTtpZihjIT1udWxsKW91dFt4LnNdPXtwOmMsdjpjLShjYXx8MCl9O30pO30KICB9Y2F0Y2goZSl7fQogIHRyeXtjb25zdCBycj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy9ST1hPMzQuU0EnKTtpZihyci5vayl7Y29uc3QgZGQ9YXdhaXQgcnIuanNvbigpO2lmKGRkLnByZWNvX2F0dWFsKXtFKCdyb3hvMzRxLXAnLGZSKGRkLnByZWNvX2F0dWFsKSk7Q2goJ3JveG8zNHEtYycsZGQucHJlY29fYXR1YWwsKGRkLnByZWNvX2FudGVyaW9yfHxkZC5wcmVjb19hdHVhbCowLjk5KSwncicpO319fWNhdGNoKGUpe30KICByZXR1cm4gb3V0Owp9CmFzeW5jIGZ1bmN0aW9uIGZGdXQoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvZnV0dXJlcycpO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkZ1bmQoKXsKICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9mYXBpLmJpbmFuY2UuY29tL2ZhcGkvdjEvcHJlbWl1bUluZGV4P3N5bWJvbD1CVENVU0RUJyk7aWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtFKCdidGMtZnVuZCcsKHBhcnNlRmxvYXQoZC5sYXN0RnVuZGluZ1JhdGV8fDApKjEwMCkudG9GaXhlZCg0KSsnJScpO3JldHVybjt9fWNhdGNoKGUpe30KICB0cnl7Y29uc3QgcjI9YXdhaXQgZmV0Y2goQisnL2JpbmFuY2UvZnVuZGluZycpO2lmKCFyMi5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByMi5qc29uKCk7aWYoZC5sYXN0RnVuZGluZ1JhdGUpRSgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlKSoxMDApLnRvRml4ZWQoNCkrJyUnKTt9Y2F0Y2goZSl7fQp9CmZ1bmN0aW9uIGRvTWFjcm8odHYsZnQpewogIFtbJ1BFVFI0JywncGV0cjRxJ10sWydJVFVCNCcsJ2l0dWI0cSddLFsnVkFMRTMnLCd2YWxlM3EnXSxbJ0JCREM0JywnYmJkYzRxJ10sWydBQkVWMycsJ2FiZXYzcSddLFsnQkJBUzMnLCdiYmFzM3EnXSxbJ1dFR0UzJywnd2VnZTNxJ11dLmZvckVhY2goKFt0LGlkXSk9PnsKICAgIGNvbnN0IGQ9dHZbJ0JNRkJPVkVTUEE6Jyt0XTtpZihkKXtFKGlkKyctcCcsZlIoZC5wKSk7Q2hUYmwoaWQrJy12JyxpZCsnLWMnLGQucCxkLnYsJ3InKTt9CiAgfSk7CiAgY29uc3QgaWI9dHZbJ0JNRkJPVkVTUEE6SUJPViddO2lmKGliKXtFKCdpYm92LXAnLGZQKGliLnApKTtDaFRibCgnaWJvdi12JywnaWJvdi1jJyxpYi5wLGliLnYsJ3AnKTt9CiAgaWYoZnQpewogICAgY29uc3QgYWY9KGlkLHYpPT57Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoZSl7ZS50ZXh0Q29udGVudD12O2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO319OwogICAgaWYoZnQuZGppPy5wcmljZSl7YWYoJ2RqaS1wJyxmUChmdC5kamkucHJpY2UpKTtDaFRibCgnZGppLXYnLCdkamktYycsZnQuZGppLnByaWNlLGZ0LmRqaS5wcmV2LCdwJyk7fQogICAgaWYoZnQuZXNmPy5wcmljZSl7YWYoJ2VzZi1wJyxmUChmdC5lc2YucHJpY2UpKTtDaFRibCgnZXNmLXYnLCdlc2YtYycsZnQuZXNmLnByaWNlLGZ0LmVzZi5wcmV2LCdwJyk7fQogICAgaWYoZnQubnFmPy5wcmljZSl7YWYoJ25xZi1wJyxmUChmdC5ucWYucHJpY2UpKTtDaFRibCgnbnFmLXYnLCducWYtYycsZnQubnFmLnByaWNlLGZ0Lm5xZi5wcmV2LCdwJyk7fQogICAgaWYoZnQud2luPy5wcmljZSl7YWYoJ3dpbi1wJyxmUChmdC53aW4ucHJpY2UpKTtDaFRibCgnd2luLXYnLCd3aW4tYycsZnQud2luLnByaWNlLGZ0Lndpbi5wcmV2LCdwJyk7fQogICAgaWYoZnQudml4Py5wcmljZSl7YWYoJ3ZpeC1wJyxOdW1iZXIoZnQudml4LnByaWNlKS50b0ZpeGVkKDIpKTtDaFRibCgndml4LXYnLCd2aXgtYycsZnQudml4LnByaWNlLGZ0LnZpeC5wcmV2LCd1Jyk7fQogICAgaWYoZnQuZHh5Py5wcmljZSl7YWYoJ2R4eS1wJyxOdW1iZXIoZnQuZHh5LnByaWNlKS50b0ZpeGVkKDIpKTtDaFRibCgnZHh5LXYnLCdkeHktYycsZnQuZHh5LnByaWNlLGZ0LmR4eS5wcmV2LCd1Jyk7fQogICAgaWYoZnQudXNkPy5wcmljZSl7YWYoJ3VzZC1wJyxmUihmdC51c2QucHJpY2UpKTtDaFRibCgndXNkLXYnLCd1c2QtYycsZnQudXNkLnByaWNlLGZ0LnVzZC5wcmV2fHxmdC51c2QucHJpY2UsJ3InKTt9CiAgfQp9CmZ1bmN0aW9uIGRvUG9zKHR2KXsKICBjb25zdCBwdD10dlsnQk1GQk9WRVNQQTpQRVRSNCddO2NvbnN0IHBwPXB0Py5wfHw0MCxwdj1wdD8udnx8NDA7CiAgRSgncHQtcCcsZlIocHApKTtDaCgncHQtYycscHAscHYsJ3InKTsKICBjb25zdCBwZD1wcC0zMC44NTtFKCdwdC1pdG0nLChwZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHBkKS50b0ZpeGVkKDIpKycgJysocGQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCB2bD10dlsnQk1GQk9WRVNQQTpWQUxFMyddO2NvbnN0IHZwPXZsPy5wfHw3OCx2dj12bD8udnx8Nzg7CiAgRSgndmwtcCcsZlIodnApKTtDaCgndmwtYycsdnAsdnYsJ3InKTsKICBjb25zdCB2ZD12cC01Ny40MDtFKCd2bC1pdG0nLCh2ZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHZkKS50b0ZpeGVkKDIpKycgJysodmQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCBjZD0oZHMsZWlkKT0+e2NvbnN0IHY9bmV3IERhdGUoZHMpLGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKSxlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVpZCk7aWYoZSllLnRleHRDb250ZW50PWQ7fTsKICBjZCgnMjAyNi0xMi0xNycsJ3B0LWRpYXMnKTtjZCgnMjAyNy0wMi0xOCcsJ3ZsLWRpYXMnKTtjZCgnMjAyNi0wOS0xNCcsJ2EzLWRpYXMnKTtjZCgnMjAyNi0xMC0wMicsJ2EzYi1kaWFzJyk7Y2QoJzIwMjYtMDctMTYnLCdyeC1kaWFzJyk7CiAgc2V0VGltZW91dChhc3luYygpPT57CiAgICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy9BWElBMy5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjsKICAgICAgY29uc3QgcD1kLnByZWNvX2F0dWFsO0UoJ2EzLXAnLGZSKHApKTtFKCdhM2ItcCcsZlIocCkpOwogICAgICBjb25zdCBrQT00My41MSxrdUE9NjguNzYsa0I9NDAuNTIsa3VCPTYyLjgxOwogICAgICBjb25zdCBkQT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTMta2RvJyk7aWYoZEEpZEEudGV4dENvbnRlbnQ9KChwLWtBKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1QT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTMta3VvJyk7aWYodUEpdUEudGV4dENvbnRlbnQ9KChrdUEtcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7CiAgICAgIGNvbnN0IHNBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhMy1zdCcpO2lmKHNBKXtzQS50ZXh0Q29udGVudD1wPD1rQT8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1QT8n4pqgIEtVTyBBVElOR0lETyc6J+KchSBObyByYW5nZSc7c0EuY2xhc3NOYW1lPSdzdiAnKyhwPD1rQXx8cD49a3VBPyd3YXJuJzonb2snKTt9CiAgICAgIGNvbnN0IGRCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhM2Ita2RvJyk7aWYoZEIpZEIudGV4dENvbnRlbnQ9KChwLWtCKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1Qj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTNiLWt1bycpO2lmKHVCKXVCLnRleHRDb250ZW50PSgoa3VCLXApL3AqMTAwKS50b0ZpeGVkKDEpKyclIHBhcmEgbyBLVU8nOwogICAgICBjb25zdCBzQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTNiLXN0Jyk7aWYoc0Ipe3NCLnRleHRDb250ZW50PXA8PWtCPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VCPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQi5jbGFzc05hbWU9J3N2ICcrKHA8PWtCfHxwPj1rdUI/J3dhcm4nOidvaycpO30KICAgIH1jYXRjaChlKXt9CiAgfSwyMDAwKTsKICBzZXRUaW1lb3V0KGFzeW5jKCk9PnsKICAgIHRyeXtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjsKICAgICAgY29uc3QgcD1kLnByZWNvX2F0dWFsO0UoJ3J4LXAnLGZSKHApKTtDaCgncngtYycscCxkLnByZWNvX2FudGVyaW9yfHxwKjAuOTksJ3InKTsKICAgICAgY29uc3QgZGlzdD1wLTEwLjUwOwogICAgICBjb25zdCBpdG09ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LWl0bScpOwogICAgICBpZihpdG0pe2l0bS50ZXh0Q29udGVudD0oZGlzdD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKGRpc3QpLnRvRml4ZWQoMikrJyAnKyhkaXN0Pj0wPydhY2ltYSBkbyBzdHJpa2UgKElUTSDimqApJzonYWJhaXhvIGRvIHN0cmlrZSAoT1RNIOKchSknKTtpdG0uY2xhc3NOYW1lPSdzdiAnKyhkaXN0Pj0wPydpdG0nOidvaycpO30KICAgIH1jYXRjaChlKXt9CiAgfSwzMDAwKTsKfQphc3luYyBmdW5jdGlvbiBNQyh0ayxzayxkaWFzLGxJZCxySWQsc0lkLHZJZCxpSWQscnRJZCl7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcjp0ayxrX2NhbGw6c2ssa19wdXQ6c2ssdF9kYXlzOmRpYXMsbjo1MDAwfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxJZCkuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocklkKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBjb25zdCBwcm9iPU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYXx8MCk7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoc0lkKTtzRWwudGV4dENvbnRlbnQ9cHJvYi50b0ZpeGVkKDEpKyclJzsKICAgIHNFbC5jbGFzc05hbWU9J2l2ICcrKHByb2I8MTU/J29rJzpwcm9iPDMwPyd3YXJuJzonZG93bicpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodklkKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlJZCkudGV4dENvbnRlbnQ9J1ZvbC5oaXN0LiAnK2Qudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUgwrcgJysocHJvYjwxNT8n4pyFIFJpc2NvIGJhaXhvIGRlIGV4ZXJjw61jaW8nOifimqAgTW9uaXRvcmFyIHBvc2nDp8OjbycpOwogICAgaWYocnRJZClFKHJ0SWQscHJvYi50b0ZpeGVkKDEpKyclJyk7CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxJZCk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gTUNCKHRrLGVuLGtkLGt1LGRpYXMscGZ4KXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvbW9udGVjYXJsby9iYXJyaWVyJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXI6dGssZW50cnk6ZW4sa2RvOmtkLGt1bzprdSx0X2RheXM6ZGlhcyxuOjMwMDB9KX0pOwogICAgaWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtbCcpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLXInKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1uYicpLnRleHRDb250ZW50PWQucHJvYl9zZW1fYmFycmVpcmEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1rdScpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9hbHRhLnRvRml4ZWQoMSkrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMta2QnKS50ZXh0Q29udGVudD1kLnByb2JfYmFycmVpcmFfYmFpeGEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy12bycpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtaScpLnRleHRDb250ZW50PSdSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtkbysnIMK3IEtVTyBSJCAnK2Qua3VvOwogIH1jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1sJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gTUNSKHRrLGVuLGtkLGRpYXMpewogIHRyeXsKICAgIGNvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXI6dGssa19jYWxsOmVuLGtfcHV0OmVuLHRfZGF5czpkaWFzLGtub2NrX2Rvd246a2Qsbjo1MDAwfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1sJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXInKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXMnKTtzRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9zdWNlc3NvKS50b0ZpeGVkKDEpKyclJztzRWwuY2xhc3NOYW1lPSdpdiAnKyhkLnByb2Jfc3VjZXNzbz43MD8nb2snOmQucHJvYl9zdWNlc3NvPjUwPyd3YXJuJzonZG93bicpOwogICAgY29uc3QgY0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1jJyk7aWYoY0VsKWNFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX2NhbGxfZXhlcmNpZGEpLnRvRml4ZWQoMSkrJyUnOwogICAgY29uc3Qga0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1rJyk7aWYoa0VsKWtFbC50ZXh0Q29udGVudD1kLnByb2Jfa2RvX2F0aW5naWRvIT1udWxsP051bWJlcihkLnByb2Jfa2RvX2F0aW5naWRvKS50b0ZpeGVkKDEpKyclJzon4oCUJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy12JykudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtaScpLnRleHRDb250ZW50PSdSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtub2NrX2Rvd247CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1sJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gZkluZCh0ayl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwzMDAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy8nK3RrLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZCVENJKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvYnRjL2luZGljYXRvcnMnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZCVENDKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvYnRjL2N5Y2xlJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmRkcoKXsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9mZWFyZ3JlZWQnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IHY9ZC52YWx1ZXx8NTAsY2xzPXY8PTI1Pyd2YXIoLS1yZWQpJzp2PD00NT8ndmFyKC0td2FybiknOnY8PTc1Pyd2YXIoLS1hY2NlbnQpJzondmFyKC0tZ3JlZW4pJzsKICAgIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmZy1hcmVhJyk7CiAgICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxNnB4Ij48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo4cHg7Zm9udC13ZWlnaHQ6NjAwO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4Ij7wn5ixIEZlYXIgJiBHcmVlZCBJbmRleDwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjE0cHgiPjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTozOHB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjonK2NscysnIj4nK3YrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjonK2NscysnIj4nKyhkLnZhbHVlX2NsYXNzaWZpY2F0aW9ufHwnTmV1dHJvJykrJzwvZGl2PjwvZGl2PjwvZGl2Pic7CiAgICBFKCdmZy12YWwnLFN0cmluZyh2KSk7RSgnZmctbGJsJyxkLnZhbHVlX2NsYXNzaWZpY2F0aW9ufHwnTmV1dHJvJyk7CiAgICB0cnl7Y29uc3QgcmI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnfSl9KTtpZihyYi5vayl7Y29uc3QgZGI9YXdhaXQgcmIuanNvbigpO2NvbnN0IGJwPXBhcnNlRmxvYXQoZGIuQlRDfHwwKTtpZihicD4wKXtFKCdidGMtaW5kLXAnLCckJytOdW1iZXIoYnApLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpO0UoJ2J0Yy1wJyxmVShicCkpO319fWNhdGNoKGUyKXt9CiAgfWNhdGNoKGUpe30KfQpmdW5jdGlvbiBybmRJbmQoaWQsZGF0YSl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQrJy1pbmQnKTtpZighZWwpcmV0dXJuOwogIGlmKCFkYXRhKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXdhcm4pO3BhZGRpbmc6MTJweDtmb250LXNpemU6MTNweCI+4o+zIFNlbSByZXNwb3N0YSDigJQgY2xpcXVlIOKGuzwvZGl2Pic7cmV0dXJuO30KICBpZihkYXRhLmVycm9yKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXJlZCk7cGFkZGluZzoxMnB4O2ZvbnQtc2l6ZToxM3B4Ij7imqAgJytkYXRhLmVycm9yKyc8L2Rpdj4nO3JldHVybjt9CiAgY29uc3QgaW5kcz1kYXRhLmluZGljYWRvcmVzfHxbXSxzYz1OdW1iZXIoZGF0YS5zY29yZV90b3RhbHx8MCkscHJlY289ZGF0YS5wcmVjb19hdHVhbCxncmFoYW09ZGF0YS5ncmFoYW1fdmFsdWUsdXA9ZGF0YS51cHNpZGVfZ3JhaGFtLHNldG9yPWRhdGEuc2V0b3J8fCcnOwogIGNvbnN0IHNjMj1zYz49NjU/J3ZhcigtLWdyZWVuKSc6c2M+PTQwPyd2YXIoLS13YXJuKSc6J3ZhcigtLXJlZCknLHNsPXNjPj02NT8nQ29tcHJhIOKWsic6c2M+PTQwPydOZXV0cm8g4oaSJzonVmVuZGEg4pa8JzsKICBsZXQgaD0nPGRpdiBjbGFzcz0ic2NiIj4nKwogICAgJzxkaXYgY2xhc3M9InNjYyI+PGRpdiBjbGFzcz0ic2NtIj5TY29yZTwvZGl2PjxkaXYgY2xhc3M9InNjbiIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2MrJzwvZGl2PjxkaXYgY2xhc3M9InNjbCIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2wrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0ic2NjIj48ZGl2IGNsYXNzPSJzY20iPkNvdGHDp8OjbzwvZGl2PjxkaXYgY2xhc3M9InNjdiI+JysocHJlY28/J1IkICcrTnVtYmVyKHByZWNvKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NzIj4nK3NldG9yKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjYyI+PGRpdiBjbGFzcz0ic2NtIj5HcmFoYW0gVko8L2Rpdj48ZGl2IGNsYXNzPSJzY3YiIHN0eWxlPSJjb2xvcjonKyh1cCYmdXA+MD8ndmFyKC0tZ3JlZW4pJzondmFyKC0tcmVkKScpKyciPicrKGdyYWhhbT8nUiQgJytOdW1iZXIoZ3JhaGFtKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NzIiBzdHlsZT0iY29sb3I6JysodXAmJnVwPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cCE9bnVsbD8odXA+MD8nKyc6JycpK3VwKyclIHVwc2lkZSc6J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzwvZGl2Pic7CiAgaW5kcy5mb3JFYWNoKGk9PnsKICAgIGNvbnN0IHM9aS5zaW5hbHx8JycsY2xzPXM9PT0nQWx0YSd8fHM9PT0nU29icmV2ZW5kYSc/J29rJzpzPT09J0JhaXhhJ3x8cz09PSdTb2JyZWNvbXByYSc/J2Rvd24nOid3YXJuJyxhcj1jbHM9PT0nb2snPyfilrInOmNscz09PSdkb3duJz8n4pa8Jzon4oaSJzsKICAgIGgrPSc8ZGl2IGNsYXNzPSJpciI+PGRpdiBjbGFzcz0iaXJ0Ij48c3BhbiBjbGFzcz0iaXJuIj4nKyhpLm5vbWV8fCcnKSsnPC9zcGFuPjxzcGFuIGNsYXNzPSJpcnYgJytjbHMrJyI+JysoaS52YWxvciE9bnVsbD9pLnZhbG9yOifigJQnKSsnICcrYXIrJzwvc3Bhbj48L2Rpdj4nKyhpLmV4cGxpY2FjYW8/JzxkaXYgY2xhc3M9ImlyZSI+JytpLmV4cGxpY2FjYW8rJzwvZGl2Pic6JycpKyc8L2Rpdj4nOwogIH0pOwogIGVsLmlubmVySFRNTD1ofHwnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTBweCI+U2VtIGluZGljYWRvcmVzPC9kaXY+JzsKfQpmdW5jdGlvbiBybmRCVENJKGQpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidGMtaW5kLWFyZWEnKTtpZighZWx8fCFkKXJldHVybjsKICBpZihkLmVycm9yKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXdhcm4pO3BhZGRpbmc6MTJweDtmb250LXNpemU6MTNweCI+4o+zICcrZC5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGxldCBoPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweCI+JzsKICBpZihkLnJzaV9zZW1hbmFsIT1udWxsKXtjb25zdCBydj1kLnJzaV9zZW1hbmFsLHJjPXJ2PDMwPydvayc6cnY+NzA/J2Rvd24nOid3YXJuJztoKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5SU0kgU2VtYW5hbDwvZGl2PjxkaXYgY2xhc3M9Iml2ICcrcmMrJyI+Jytydi50b0ZpeGVkKDEpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrKHJ2PDMwPydTb2JyZXZlbmRhIOKaoSc6cnY+NzA/J1NvYnJlY29tcHJhIOKaoCc6J05ldXRybycpKyc8L2Rpdj48L2Rpdj4nO0UoJ2J0Yy1yc2knLHJ2LnRvRml4ZWQoMSkpO30KICBpZihkLm1tNTBfc2VtYW5hbCloKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NTSA1MCBzZW0uPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JCcrTnVtYmVyKGQubW01MF9zZW1hbmFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nOwogIGlmKGQubW0yMDBfc2VtYW5hbCloKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NTSAyMDAgc2VtLjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPiQnK051bWJlcihkLm1tMjAwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZC5tYWNkX2hpc3RvZ3JhbSE9bnVsbCl7Y29uc3QgbWg9ZC5tYWNkX2hpc3RvZ3JhbTtoKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NQUNEIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgJysobWg+MD8nb2snOidkb3duJykrJyI+JytOdW1iZXIobWgpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JysobWg+MD8nTW9tZW50dW0g4payJzonTW9tZW50dW0g4pa8JykrJzwvZGl2PjwvZGl2Pic7fQogIGlmKGQub2J2X3RyZW5kKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk9CVjwvZGl2PjxkaXYgY2xhc3M9Iml2ICcrKGQub2J2X3RyZW5kPT09J3N1YmluZG8nPydvayc6J2Rvd24nKSsnIj4nK2Qub2J2X3RyZW5kKyc8L2Rpdj48L2Rpdj4nOwogIGgrPSc8L2Rpdj4nO2VsLmlubmVySFRNTD1oOwogIGlmKGQucHJpY2UpRSgnYnRjLWluZC1wJywnJCcrTnVtYmVyKGQucHJpY2UpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpOwp9CmZ1bmN0aW9uIHJuZEJUQ0MoZCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1jeWNsZS1hcmVhJyk7aWYoIWVsfHwhZHx8ZC5lcnJvcilyZXR1cm47CiAgY29uc3QgZlUyPXY9PnY/JyQnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwogIGVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLWJvdHRvbToxMHB4Ij4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+TVZSViBaLVNjb3JlPC9kaXY+PGRpdiBjbGFzcz0iaXYgJysoZC5tdnJ2X3pzY29yZT8udmFsdWU8MT8nb2snOmQubXZydl96c2NvcmU/LnZhbHVlPDM/J3dhcm4nOidkb3duJykrJyI+JytkLm12cnZfenNjb3JlPy52YWx1ZSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nK2QubXZydl96c2NvcmU/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+TlVQTDwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrKChkLm51cGw/LnZhbHVlfHwwKSoxMDApLnRvRml4ZWQoMCkrJyU8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5udXBsPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlB1ZWxsIE11bHRpcGxlPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JytkLnB1ZWxsPy52YWx1ZSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nK2QucHVlbGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+MjAwVyBNQTwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrZlUyKGQubWEyMDB3KSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nKyhkLm1hMjAwd19wY3Q/JysnK2QubWEyMDB3X3BjdCsnJSc6JycpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UmFpbmJvdyBCYW5kPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JysoZC5yYWluYm93Py5iYW5kfHwn4oCUJykrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5QaSBDeWNsZSBEaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIj4nK2ZVMihkLnBpX2N5Y2xlPy5kaXN0YW5jZSkrJzwvZGl2PjwvZGl2PicrCiAgICAnPC9kaXY+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEwcHg7Zm9udC1zaXplOjEzcHg7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXdlaWdodDo2MDAiPicrKGQucGlfY3ljbGU/LnNpZ25hbHx8JycpKyc8L2Rpdj4nOwp9CmFzeW5jIGZ1bmN0aW9uIGxvYWRJbmQoKXsKICBjb25zdCB3dD0ocCxtcyxmYik9PlByb21pc2UucmFjZShbcCxuZXcgUHJvbWlzZShyPT5zZXRUaW1lb3V0KCgpPT5yKGZiKSxtcykpXSk7CiAgY29uc3RbYmksYmNdPWF3YWl0IFByb21pc2UuYWxsKFt3dChmQlRDSSgpLDE1MDAwLHtlcnJvcjonVGltZW91dCDigJQgY2xpcXVlIOKGuyd9KSx3dChmQlRDQygpLDE1MDAwLG51bGwpXSk7CiAgcm5kQlRDSShiaSk7cm5kQlRDQyhiYyk7ZkZHKCk7CiAgY29uc3Qgc3RvY2tzPVtbJ1BFVFI0LlNBJywncGV0cjQnXSxbJ1ZBTEUzLlNBJywndmFsZTMnXSxbJ0JCQVMzLlNBJywnYmJhczMnXSxbJ0FYSUEzLlNBJywnYXhpYTMnXSxbJ1JPWE8zNC5TQScsJ3JveG8zNCddXTsKICBjb25zdCByZXM9YXdhaXQgUHJvbWlzZS5hbGwoc3RvY2tzLm1hcCgoW3RdKT0+d3QoZkluZCh0KSwzMDAwMCx7ZXJyb3I6J1RpbWVvdXQgMzBzJ30pKSk7CiAgc3RvY2tzLmZvckVhY2goKFssaWRdLGkpPT5ybmRJbmQoaWQscmVzW2ldKSk7Cn0KYXN5bmMgZnVuY3Rpb24gcmwodGspewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHRrKyctaW5kJyk7CiAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxcyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2Pic7CiAgY29uc3QgbT17cGV0cjQ6J1BFVFI0LlNBJyx2YWxlMzonVkFMRTMuU0EnLGJiYXMzOidCQkFTMy5TQScsYXhpYTM6J0FYSUEzLlNBJyxyb3hvMzQ6J1JPWE8zNC5TQSd9OwogIHJuZEluZCh0ayxhd2FpdCBmSW5kKG1bdGtdKSk7Cn0KY29uc3QgRkxBR1M9eydVU0QnOifwn4e68J+HuCcsJ1VTJzon8J+HuvCfh7gnLCdCUkwnOifwn4en8J+HtycsJ0JSJzon8J+Hp/Cfh7cnLCdFVVInOifwn4eq8J+HuicsJ0VVJzon8J+HqvCfh7onLCdHQlAnOifwn4es8J+HpycsJ0NOWSc6J/Cfh6jwn4ezJywnSlBZJzon8J+Hr/Cfh7UnLCdDQUQnOifwn4eo8J+HpicsJ0FVRCc6J/Cfh6bwn4e6JywnREUnOifwn4ep8J+HqicsJ05aRCc6J/Cfh7Pwn4e/JywnQ0hGJzon8J+HqPCfh60nfTsKYXN5bmMgZnVuY3Rpb24gbG9hZENhbCgpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYWwtYXJlYScpLHN0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYWwtc3QnKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjI0cHg7dGV4dC1hbGlnbjpjZW50ZXI7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj4nOwogIGlmKHN0KXN0LnRleHRDb250ZW50PSdCdXNjYW5kbyBldmVudG9zLi4uJzsKICB0cnl7CiAgICBjb25zb2xlLmxvZygnW0NBTF0gSW5pY2lhbmRvIGZldGNoLi4uJyk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9jYWxlbmRhcicse2NhY2hlOiduby1zdG9yZSd9KTsKICAgIGNvbnNvbGUubG9nKCdbQ0FMXSBSZXNwb25zZTonLCByLnN0YXR1cyk7CiAgICBpZighci5vayl0aHJvdyBuZXcgRXJyb3IoJ0hUVFAgJytyLnN0YXR1cysnIOKAlCAnK2F3YWl0IHIudGV4dCgpKTsKICAgIGNvbnN0IGV2cz1hd2FpdCByLmpzb24oKTsKICAgIGNvbnNvbGUubG9nKCdbQ0FMXSBFdmVudG9zIHJlY2ViaWRvczonLCBldnMubGVuZ3RoKTsKICAgIGlmKGV2cy5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZXZzLmVycm9yKTsKICAgIGlmKHN0KXN0LnRleHRDb250ZW50PWV2cy5sZW5ndGg+MD9ldnMubGVuZ3RoKycgZXZlbnRvcyAoVVNEL0VVUi9KUFkvR0JQL0NOWS9DQUQpJzonQ2FjaGUgdmF6aW8g4oCUIGFndWFyZGUgcHLDs3hpbWEgYXR1YWxpemHDp8Ojbyc7CiAgICBpZighZXZzLmxlbmd0aCl7CiAgICAgIGVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0icGFkZGluZzoyNHB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTNweCI+JysKICAgICAgICAnQ2FjaGUgc2VuZG8gYXR1YWxpemFkby4uLiB0ZW50ZSBub3ZhbWVudGUgZW0gMSBtaW51dG8uPGJyPicrCiAgICAgICAgJzxidXR0b24gb25jbGljaz0ibG9hZENhbCgpIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4O2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtib3JkZXI6bm9uZTtjb2xvcjojZmZmO3BhZGRpbmc6OHB4IDE4cHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo3MDAiPuKGuyBUZW50YXIgbm92YW1lbnRlPC9idXR0b24+JysKICAgICAgICAnPC9kaXY+JzsKICAgICAgcmV0dXJuOwogICAgfQogICAgY29uc3QgYnlEPXt9O2V2cy5mb3JFYWNoKGU9Pntjb25zdCBkdD0oZS5kYXRlfHwnJykuc2xpY2UoMCwxMCk7aWYoIWJ5RFtkdF0pYnlEW2R0XT1bXTtieURbZHRdLnB1c2goZSk7fSk7CiAgICBjb25zb2xlLmxvZygnW0NBTF0gRGF0YXM6JywgT2JqZWN0LmtleXMoYnlEKSk7CiAgICBsZXQgaD0nJzsKICAgIE9iamVjdC5rZXlzKGJ5RCkuc29ydCgpLmZvckVhY2goZHQ9PnsKICAgICAgY29uc3QgZD1uZXcgRGF0ZShkdCsnVDEyOjAwOjAwJyksbGJsPWQudG9Mb2NhbGVEYXRlU3RyaW5nKCdwdC1CUicse3dlZWtkYXk6J2xvbmcnLGRheTonMi1kaWdpdCcsbW9udGg6J3Nob3J0J30pOwogICAgICBoKz0nPGRpdiBjbGFzcz0idGJsLXdyYXAiIHN0eWxlPSJtYXJnaW4tYm90dG9tOjE0cHgiPjxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj4nK2xibCsnPC9zcGFuPjwvZGl2PicrCiAgICAgICAgJzx0YWJsZSBjbGFzcz0iY2FsLXRibCI+PHRoZWFkPjx0cj48dGg+UGHDrXM8L3RoPjx0aD5Ib3JhPC90aD48dGg+RXZlbnRvPC90aD48dGg+SW1wPC90aD48dGggY2xhc3M9InIiPlJlYWxpemFkbzwvdGg+PHRoIGNsYXNzPSJyIj5QcmV2aXN0bzwvdGg+PC90cj48L3RoZWFkPjx0Ym9keT4nOwogICAgICBieURbZHRdLmZvckVhY2goZT0+ewogICAgICAgIGNvbnN0IGljPWUuaW1wb3J0YW5jZT49Mz8naW1wLWhpZ2gnOidpbXAtbWVkJzsKICAgICAgICBjb25zdCBhYz1lLnNpZ25hbD09PSdiZWF0Jz8ndmFyKC0tZ3JlZW4pJzplLnNpZ25hbD09PSdtaXNzJz8ndmFyKC0tcmVkKSc6J3ZhcigtLXRleHQpJzsKICAgICAgICBjb25zdCBpbXA9J+KXjycucmVwZWF0KE1hdGgubWluKGUuaW1wb3J0YW5jZSwzKSk7CiAgICAgICAgaCs9Jzx0cj4nKwogICAgICAgICAgJzx0ZD48c3BhbiBjbGFzcz0iY2FsLWZsYWciPicrKGUuZmxhZ3x8RkxBR1NbZS5jb3VudHJ5XXx8J/CfjJAnKSsnPC9zcGFuPjwvdGQ+JysKICAgICAgICAgICc8dGQ+PHNwYW4gY2xhc3M9ImNhbC10aW1lIj4nKyhlLnRpbWV8fCfigJQnKSsnPC9zcGFuPjwvdGQ+JysKICAgICAgICAgICc8dGQ+PHNwYW4gY2xhc3M9ImNhbC1ldiIgdGl0bGU9IicrZS5ldmVudCsnIj4nK2UuZXZlbnQrJzwvc3Bhbj48L3RkPicrCiAgICAgICAgICAnPHRkPjxzcGFuIGNsYXNzPSInK2ljKyciPicraW1wKyc8L3NwYW4+PC90ZD4nKwogICAgICAgICAgJzx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNhbC12YWwiIHN0eWxlPSJjb2xvcjonK2FjKyciPicrKGUuYWN0dWFsfHwn4oCUJykrJzwvc3Bhbj48L3RkPicrCiAgICAgICAgICAnPHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2FsLWZjIj4nKyhlLmZvcmVjYXN0fHwn4oCUJykrJzwvc3Bhbj48L3RkPicrCiAgICAgICAgICAnPC90cj4nOwogICAgICB9KTsKICAgICAgaCs9JzwvdGJvZHk+PC90YWJsZT48L2Rpdj4nOwogICAgfSk7CiAgICBjb25zb2xlLmxvZygnW0NBTF0gSFRNTCBnZXJhZG86JywgaC5sZW5ndGgsICdjaGFycycpOwogICAgZWwuaW5uZXJIVE1MPWg7CiAgICBjb25zb2xlLmxvZygnW0NBTF0gUmVuZGVyaXphZG8gT0snKTsKICB9Y2F0Y2goZSl7CiAgICBjb25zb2xlLmVycm9yKCdbQ0FMXSBFUlJPOicsIGUpOwogICAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9J0Vycm86ICcrZS5tZXNzYWdlOwogICAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1yZWQpO3BhZGRpbmc6MjBweDtmb250LXNpemU6MTNweCI+JysKICAgICAgJzxiPkVycm8gbm8gY2FsZW5kw6FyaW86PC9iPjxicj4nK2UubWVzc2FnZSsnPGJyPjxicj4nKwogICAgICAnPHNtYWxsPkFicmEgbyBjb25zb2xlIChGMTIpIHBhcmEgZGV0YWxoZXM8L3NtYWxsPjwvZGl2Pic7CiAgfQp9CmFzeW5jIGZ1bmN0aW9uIG1haW4oKXsKICB0cnl7CiAgICBjb25zdFssdHYsZnRdPWF3YWl0IFByb21pc2UuYWxsKFtmSEwoKSxmVFYoKSxmRnV0KCldKTsKICAgIGNvbnN0IG5vdz1uZXcgRGF0ZSgpLnRvTG9jYWxlVGltZVN0cmluZygncHQtQlInKTsKICAgIEUoJ2xhc3QtdXBkYXRlJywn4oa7ICcrbm93KTtFKCdsYXN0LXVwZGF0ZS10YmwnLG5vdyk7RSgnZm9vdGVyLXRpbWUnLG5vdyk7CiAgICB3aW5kb3cuX2xhc3RUVj10djtkb01hY3JvKHR2LGZ0KTtkb1Bvcyh0dik7CiAgICBzZXRUaW1lb3V0KGZGdW5kLDMwMDApOwogICAgc2V0VGltZW91dChhc3luYygpPT57dHJ5e2NvbnN0W2JpLGJjXT1hd2FpdCBQcm9taXNlLmFsbChbZkJUQ0koKSxmQlRDQygpXSk7aWYoYmkpcm5kQlRDSShiaSk7aWYoYmMpcm5kQlRDQyhiYyk7ZkZHKCk7fWNhdGNoKGUpe319LDUwMDApOwogICAgY29uc3QgaG9qZT1uZXcgRGF0ZSgpOwogICAgY29uc3QgZFA9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTEyLTE3JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRWPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNy0wMi0xOCcpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkQT1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDktMTQnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZEFiPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0xMC0wMicpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkUj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDctMTYnKS1ob2plKS84NjRlNSkpOwogICAgc2V0VGltZW91dCgoKT0+TUMoJ1BFVFI0LlNBJywzMC44NSxkUCwncHQtbWMtbCcsJ3B0LW1jLXInLCdwdC1tYy1zJywncHQtbWMtdicsJ3B0LW1jLWknLCdwdC1tYy1ydCcpLDYwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUMoJ1ZBTEUzLlNBJyw1Ny40MCxkViwndmwtbWMtbCcsJ3ZsLW1jLXInLCd2bC1tYy1zJywndmwtbWMtdicsJ3ZsLW1jLWknLCd2bC1tYy1ydCcpLDEyMDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DQignQVhJQTMuU0EnLDU0LjMxLDQzLjUxLDY4Ljc2LGRBLCdhMycpLDE4MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DQignQVhJQTMuU0EnLDUwLjY1LDQwLjUyLDYyLjgxLGRBYiwnYTNiJyksMjQwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUMoJ1JPWE8zNC5TQScsMTAuNTAsMjksJ3J4LW1jLWwnLCdyeC1tYy1yJywncngtbWMtcycsJ3J4LW1jLXYnLCdyeC1tYy1pJywncngtbWMtcnQnKSwzMDAwMCk7CiAgICBjb25zdCBkQkI9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTA4LTIwJyktaG9qZSkvODY0ZTUpKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DKCdCQkFTMy5TQScsMjEuNjUsZEJCLCdiYi1tYy1sJywnYmItbWMtcicsJ2JiLW1jLXMnLCdiYi1tYy12JywnYmItbWMtaScsJ2JiLW1jLXJ0JyksMzYwMDApOwogICAgLy8gQkJBUzMgY290YcOnw6NvIOKAlCB2aWEgVFYgb3UgZmFsbGJhY2sgL2luZGljYXRvcnMKICAgIGNvbnN0IGJiVFY9dHZbJ0JNRkJPVkVTUEE6QkJBUzMnXTsKICAgIGlmKGJiVFY/LnApewogICAgICBFKCdiYi1wJyxmUihiYlRWLnApKTtDaCgnYmItYycsYmJUVi5wLGJiVFYudnx8YmJUVi5wLCdyJyk7CiAgICAgIGNvbnN0IGQyPWJiVFYucC0yMS42NTsKICAgICAgY29uc3QgaXRtMj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmItaXRtJyk7CiAgICAgIGlmKGl0bTIpe2l0bTIudGV4dENvbnRlbnQ9KGQyPj0wPycrIFIkICc6Jy0gUiQgJykrTWF0aC5hYnMoZDIpLnRvRml4ZWQoMikrJyAnKyhkMj49MD8nYWNpbWEgKElUTSDimqApJzonYWJhaXhvIChPVE0g4pyFKScpKycgZG8gc3RyaWtlJztpdG0yLmNsYXNzTmFtZT0nc3YgJysoZDI+PTA/J2l0bSc6J29rJyk7fQogICAgfSBlbHNlIHsKICAgICAgLy8gVFYgbsOjbyByZXRvcm5vdSBCQkFTMyDigJQgZmFsbGJhY2sKICAgICAgZmV0Y2goQisnL2luZGljYXRvcnMvQkJBUzMuU0EnKS50aGVuKHIyPT5yMi5qc29uKCkpLnRoZW4oZDI9PnsKICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICBFKCdiYi1wJyxmUihkMi5wcmVjb19hdHVhbCkpO0NoKCdiYi1jJyxkMi5wcmVjb19hdHVhbCxkMi5wcmVjb19hbnRlcmlvcnx8ZDIucHJlY29fYXR1YWwqMC45OSwncicpOwogICAgICAgICAgY29uc3QgZGlzdD1kMi5wcmVjb19hdHVhbC0yMS42NTsKICAgICAgICAgIGNvbnN0IGl0bTI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JiLWl0bScpOwogICAgICAgICAgaWYoaXRtMil7aXRtMi50ZXh0Q29udGVudD0oZGlzdD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKGRpc3QpLnRvRml4ZWQoMikrJyAnKyhkaXN0Pj0wPydhY2ltYSAoSVRNIOKaoCknOidhYmFpeG8gKE9UTSDinIUpJykrJyBkbyBzdHJpa2UnO2l0bTIuY2xhc3NOYW1lPSdzdiAnKyhkaXN0Pj0wPydpdG0nOidvaycpO30KICAgICAgICB9CiAgICAgIH0pLmNhdGNoKCgpPT57fSk7CiAgICB9CiAgICBjb25zdCBjZEJCPSgpPT57Y29uc3Qgdj1uZXcgRGF0ZSgnMjAyNi0wOC0yMCcpLGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKSxlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiYi1kaWFzJyk7aWYoZSllLnRleHRDb250ZW50PWQ7fTtjZEJCKCk7CiAgICB3aW5kb3cuX0lMPWZhbHNlOwogIH1jYXRjaChlKXtjb25zb2xlLmVycm9yKGUpO30KfQptYWluKCk7c2V0SW50ZXJ2YWwobWFpbiwxMjAwMDApOwo8L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+Cg==").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
