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
    import re as _re
    flag_map = {
        'USD':'US','EUR':'EU','GBP':'GB','CNY':'CN',
        'JPY':'JP','CAD':'CA','AUD':'AU','NZD':'NZ','CHF':'CH',
    }
    emoji_map = {
        'USD':'🇺🇸','EUR':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳',
        'JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺','NZD':'🇳🇿','CHF':'🇨🇭',
    }
    imp_map = {'Low':1,'Medium':2,'High':3,'Holiday':0}
    currencies_ok = set(emoji_map.keys())

    def parse_date(raw):
        if not raw: return '',''
        try:
            match = _re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):\d{2}([+-])(\d{2}):(\d{2})', raw)
            if not match:
                return raw[:10], raw[11:16] if len(raw)>15 else ''
            date_p,hh,mm,sign,tzh,tzm = match.groups()
            from datetime import datetime as _dt, timedelta
            naive = _dt.strptime(date_p+' '+hh+':'+mm, '%Y-%m-%d %H:%M')
            offset = int(tzh)*60+int(tzm)
            if sign=='-': offset=-offset
            utc = naive - timedelta(minutes=offset)
            brt = utc - timedelta(hours=3)
            return brt.strftime('%Y-%m-%d'), brt.strftime('%H:%M')
        except:
            return raw[:10], raw[11:16] if len(raw)>15 else ''

    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/cache/calendar.json',
            headers={'Cache-Control':'no-cache'},
            timeout=10)
        if not r.ok:
            return jsonify({'error':'cache indisponivel'}), 500
        raw = r.json()
        events = []
        for e in raw:
            cur = e.get('country','')
            if cur not in currencies_ok: continue
            imp = imp_map.get(e.get('impact',''),0)
            if imp < 2: continue
            date_str, time_str = parse_date(e.get('date',''))
            if not date_str: continue
            actual = e.get('actual') or None
            forecast = e.get('forecast') or None
            signal = None
            if actual and forecast:
                try:
                    a = float(str(actual).replace('%','').replace('K','000').replace('M','000000'))
                    f2 = float(str(forecast).replace('%','').replace('K','000').replace('M','000000'))
                    signal = 'beat' if a>=f2 else 'miss'
                except: pass
            events.append({
                'date':date_str,'time':time_str,
                'country':cur,'flag':emoji_map.get(cur,'🌐'),
                'event':e.get('title',''),
                'importance':imp,
                'actual':actual,'forecast':forecast,
                'previous':e.get('previous') or None,
                'signal':signal,
            })
        events.sort(key=lambda x:(x['date'],x['time']))
        return jsonify(events)
    except Exception as ex:
        return jsonify({'error':str(ex)}), 500


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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjExLjMg4oCUIERhcmsgUHJlbWl1bSAtLT4KPGh0bWwgbGFuZz0icHQtQlIiPgo8aGVhZD4KPG1ldGEgY2hhcnNldD0iVVRGLTgiPgo8bWV0YSBuYW1lPSJ2aWV3cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MS4wIj4KPHRpdGxlPlRyYWRlciBEZXNrPC90aXRsZT4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JbnRlcjp3Z2h0QDQwMDs1MDA7NjAwOzcwMCZmYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs2MDA7NzAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Cjpyb290ewogIC0tYmc6IzBmMGYxMzstLWJnMjojMTMxMzFhOy0tYmczOiMxYTFhMjQ7CiAgLS10ZXh0OiNlOGU4ZjA7LS1tdXRlZDojNTA1MDY4Oy0tYm9yZGVyOiMxZTFlMmU7CiAgLS1hY2NlbnQ6IzdjNmFmNzstLWFjY2VudDI6IzRmYzNmNzsKICAtLWdyZWVuOiMwMGU2NzY7LS1yZWQ6I2YwNjI5MjstLXdhcm46I2ZmYjc0ZDsKICAtLWdvbGQ6I2YwYTUwMAp9CmJvZHl7CiAgYmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7CiAgZm9udC1mYW1pbHk6J0ludGVyJyxzYW5zLXNlcmlmO2ZvbnQtc2l6ZToxNHB4OwogIGxpbmUtaGVpZ2h0OjEuNTtwYWRkaW5nOjIwcHggMjRweDsKICBtYXgtd2lkdGg6MTEwMHB4O21hcmdpbjowIGF1dG87bWluLWhlaWdodDoxMDB2aAp9CkBtZWRpYShtYXgtd2lkdGg6NjAwcHgpe2JvZHl7cGFkZGluZzoxMnB4fX0KCi8qIOKUgOKUgCBIRUFERVIg4pSA4pSAICovCi5oZHJ7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjIwcHg7cGFkZGluZy1ib3R0b206MTZweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpfQoubG9nb3tmb250LXNpemU6MThweDtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtsZXR0ZXItc3BhY2luZzouNXB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5sb2dvIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50Mil9Ci5oZHItcmlnaHR7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweH0KLmJhZGdle2JhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo0cHggMTJweDtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4fQouaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQoKLyog4pSA4pSAIFRBQlMg4pSA4pSAICovCi50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MjBweDtvdmVyZmxvdy14OmF1dG87cGFkZGluZy1ib3R0b206MnB4fQoudGFie3BhZGRpbmc6OHB4IDE4cHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6MTJweDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3doaXRlLXNwYWNlOm5vd3JhcDtmb250LWZhbWlseTppbmhlcml0O3RyYW5zaXRpb246YWxsIC4xNXN9Ci50YWI6aG92ZXJ7Y29sb3I6dmFyKC0tdGV4dCk7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci50YWIuYWN0aXZle2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtjb2xvcjojZmZmO2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpfQoudGFiLWNvbnRlbnR7ZGlzcGxheTpub25lfS50YWItY29udGVudC5hY3RpdmV7ZGlzcGxheTpibG9ja30KCi8qIOKUgOKUgCBTRUNUSU9OIOKUgOKUgCAqLwouc2Vje2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHggMCA3cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjE0cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4fQouc2VjIC5kb3R7d2lkdGg6NXB4O2hlaWdodDo1cHg7YmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrO2ZsZXgtc2hyaW5rOjB9Ci5zZWMgLmFjY3tjb2xvcjp2YXIoLS1hY2NlbnQpfQoKLyog4pSA4pSAIEdSSUQgQ0FSRFMg4pSA4pSAICovCi5ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDMsMWZyKTtnYXA6MTBweDttYXJnaW4tYm90dG9tOjE4cHh9CkBtZWRpYShtYXgtd2lkdGg6NTAwcHgpey5ncmlke2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoMiwxZnIpfX0KLmNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHggMTRweDtwb3NpdGlvbjpyZWxhdGl2ZTtvdmVyZmxvdzpoaWRkZW47dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1c30KLmNhcmQ6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci5jYXJkOjpiZWZvcmV7Y29udGVudDonJztwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MDtsZWZ0OjA7cmlnaHQ6MDtoZWlnaHQ6MnB4fQouY2FyZC5nOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tZ3JlZW4pLCMwMGJjZDQpfQouY2FyZC5iOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tYWNjZW50KSx2YXIoLS1hY2NlbnQyKSl9Ci5jYXJkLnc6OmJlZm9yZXtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS13YXJuKSwjZmY5ODAwKX0KLmNhcmQucjo6YmVmb3Jle2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLHZhcigtLXJlZCksI2U5MWU2Myl9Ci5jbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjRweDtmb250LXdlaWdodDo2MDB9Ci5jbntmb250LXNpemU6MTNweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLWJvdHRvbTo4cHg7Y29sb3I6cmdiYSgyNTUsMjU1LDI1NSwuOCl9Ci5jcHtmb250LXNpemU6MjBweDtmb250LXdlaWdodDo3MDA7Y29sb3I6I2ZmZn0KLmNwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToxNXB4fQouY2N7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NTAwfQouY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0uY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjN9fQoKLyog4pSA4pSAIEFDQ09SRElPTiBTRUdNRU5UT1Mg4pSA4pSAICovCi5zaHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweCAxNnB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7Zm9udC1zaXplOjEycHg7Zm9udC13ZWlnaHQ6NjAwO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDt0cmFuc2l0aW9uOmFsbCAuMTVzfQouc2g6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zYjJ7ZGlzcGxheTpub25lO3BhZGRpbmctdG9wOjZweH0KCi8qIOKUgOKUgCBQT1NJw4fDlUVTIOKUgOKUgCAqLwoucGN7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjE4cHg7bWFyZ2luLWJvdHRvbToxMnB4fQoucGx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnB0e2ZvbnQtc2l6ZToyMnB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO21hcmdpbi1ib3R0b206NHB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5wcHtmb250LXNpemU6MjhweDtmb250LXdlaWdodDo3MDB9LnBwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToyMHB4fQoucGMye2ZvbnQtc2l6ZToxMnB4O21hcmdpbi1ib3R0b206MTBweDtmb250LXdlaWdodDo1MDB9Ci5zYntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmctdG9wOjEwcHg7bWFyZ2luLXRvcDoxMHB4fQouc3J7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjVweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEzcHh9Ci5zbHtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NTAwfS5zdnt0ZXh0LWFsaWduOnJpZ2h0O21heC13aWR0aDo1OCU7Zm9udC13ZWlnaHQ6NjAwfQouc3Yub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5zdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zdi5pdG17Y29sb3I6dmFyKC0tcmVkKX0KLnBvcy1hY2N7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTttYXJnaW4tYm90dG9tOjEwcHh9Ci5wb3MtYWNjLWhkcntkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6MTRweCAxOHB4O2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246YmFja2dyb3VuZCAuMTVzfQoucG9zLWFjYy1oZHI6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQoucG9zLWFjYy10a3tmb250LXNpemU6MjJweDtmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlfQoucG9zLWFjYy1zdWJ7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQoucG9zLWFjYy1yaWdodHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxNHB4fQoucG9zLWFjYy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nOjAgMThweCAxNnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcil9Ci5wb3MtYWNjLWJvZHkub3BlbntkaXNwbGF5OmJsb2NrfQouc2lne2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHg7bWFyZ2luLXRvcDoxMHB4O2JhY2tncm91bmQ6dmFyKC0tYmcpfQouc2d0e2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjcwMDtsZXR0ZXItc3BhY2luZzoxcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206OHB4O2NvbG9yOnZhcigtLWFjY2VudDIpfQouaWJ7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEycHg7dGV4dC1hbGlnbjpjZW50ZXJ9Ci5pbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo1cHg7Zm9udC13ZWlnaHQ6NjAwO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4fQouaXZ7Zm9udC1zaXplOjIwcHg7Zm9udC13ZWlnaHQ6ODAwfQouaXYub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5pdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5pdi5kb3due2NvbG9yOnZhcigtLXJlZCl9CgovKiDilIDilIAgSU5ESUNBRE9SRVMg4pSA4pSAICovCi5zY2J7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyIDFmcjtnYXA6OHB4O21hcmdpbi1ib3R0b206MTRweH0KLnNjY3tiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTRweCAxMnB4O3RleHQtYWxpZ246Y2VudGVyO3Bvc2l0aW9uOnJlbGF0aXZlO292ZXJmbG93OmhpZGRlbn0KLnNjYzo6YmVmb3Jle2NvbnRlbnQ6Jyc7cG9zaXRpb246YWJzb2x1dGU7dG9wOjA7bGVmdDowO3JpZ2h0OjA7aGVpZ2h0OjJweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS1hY2NlbnQpLHZhcigtLWFjY2VudDIpKX0KLnNjbXtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjVweDtmb250LXdlaWdodDo2MDB9Ci5zY257Zm9udC1zaXplOjMycHg7Zm9udC13ZWlnaHQ6ODAwO2xpbmUtaGVpZ2h0OjF9Ci5zY2x7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc2N2e2ZvbnQtc2l6ZToyMHB4O2ZvbnQtd2VpZ2h0OjcwMDttYXJnaW4tdG9wOjRweH0KLnNjc3tmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHh9Ci5pcntiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCB0cmFuc3BhcmVudDtwYWRkaW5nOjEwcHggMTRweDttYXJnaW4tYm90dG9tOjRweDt0cmFuc2l0aW9uOmJvcmRlci1sZWZ0LWNvbG9yIC4xc30KLmlyOmhvdmVye2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLWFjY2VudCl9Ci5pcnR7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmJhc2VsaW5lO21hcmdpbi1ib3R0b206M3B4fQouaXJue2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjVweDtmb250LXdlaWdodDo2MDB9Ci5pcnZ7Zm9udC1zaXplOjE1cHg7Zm9udC13ZWlnaHQ6NzAwfQouaXJ2Lm9re2NvbG9yOnZhcigtLWdyZWVuKX0uaXJ2LmRvd257Y29sb3I6dmFyKC0tcmVkKX0uaXJ2Lndhcm57Y29sb3I6dmFyKC0td2Fybil9Ci5pcmV7Zm9udC1zaXplOjEzcHg7Y29sb3I6IzVhNWE4YTtsaW5lLWhlaWdodDoxLjV9CgovKiDilIDilIAgQ0FMRU5Ew4FSSU8g4pSA4pSAICovCi5jYWwtdGJse3dpZHRoOjEwMCU7Ym9yZGVyLWNvbGxhcHNlOmNvbGxhcHNlO2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZn0KLmNhbC10YmwgdGh7dGV4dC1hbGlnbjpsZWZ0O3BhZGRpbmc6N3B4IDE0cHg7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQouY2FsLXRibCB0aC5ye3RleHQtYWxpZ246cmlnaHR9Ci5jYWwtdGJsIHRke3BhZGRpbmc6OXB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtmb250LXNpemU6MTNweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9Ci5jYWwtdGJsIHRkLnJ7dGV4dC1hbGlnbjpyaWdodH0KLmNhbC10YmwgdHI6bGFzdC1jaGlsZCB0ZHtib3JkZXItYm90dG9tOm5vbmV9Ci5jYWwtdGJsIHRyOmhvdmVyIHRke2JhY2tncm91bmQ6dmFyKC0tYmczKX0KLmNhbC1mbGFne2ZvbnQtc2l6ZToxNnB4fQouY2FsLXRpbWV7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5jYWwtZXZ7Zm9udC13ZWlnaHQ6NTAwO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcDttYXgtd2lkdGg6MzIwcHh9Ci5jYWwtdmFse2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC13ZWlnaHQ6NzAwO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjEzcHh9Ci5jYWwtZmN7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKX0KLmltcC1oaWdoe2NvbG9yOnZhcigtLXJlZCl9LmltcC1tZWR7Y29sb3I6dmFyKC0td2Fybil9CgouaW5kLWFjY3tiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO21hcmdpbi1ib3R0b206MTZweH0KLmluZC1hY2MtaGRye2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzoxMnB4IDE2cHg7Y3Vyc29yOnBvaW50ZXI7dHJhbnNpdGlvbjpiYWNrZ3JvdW5kIC4xNXN9Ci5pbmQtYWNjLWhkcjpob3ZlcntiYWNrZ3JvdW5kOnZhcigtLWJnMyl9Ci5pbmQtYWNjLXRpdGxle2ZvbnQtc2l6ZToxNHB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS1hY2NlbnQpfQouaW5kLWFjYy1zdWJ7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQouaW5kLWFjYy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nOjAgMTZweCAxNnB4fQouaW5kLWFjYy1ib2R5Lm9wZW57ZGlzcGxheTpibG9ja30KLnRibC1ta3R7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2U7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZX0KLnRibC1ta3QgdGhlYWQgdHJ7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKX0KLnRibC1ta3QgdGh7dGV4dC1hbGlnbjpsZWZ0O3BhZGRpbmc6N3B4IDE0cHg7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZn0KLnRibC1ta3QgdGgucnt0ZXh0LWFsaWduOnJpZ2h0fQoudGJsLW1rdCB0ZHtwYWRkaW5nOjlweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjE0cHg7dmVydGljYWwtYWxpZ246bWlkZGxlfQoudGJsLW1rdCB0ZC5ye3RleHQtYWxpZ246cmlnaHR9Ci50YmwtbWt0IHRyOmxhc3QtY2hpbGQgdGR7Ym9yZGVyLWJvdHRvbTpub25lfQoudGJsLW1rdCB0cjpob3ZlciB0ZHtiYWNrZ3JvdW5kOnZhcigtLWJnMyl9Ci50YmwtbWt0IC5zeW17Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLXRleHQpfQoudGJsLW1rdCAuZGVzY3tmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NDAwO2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZjttYXJnaW4tdG9wOjFweH0KLnRibC1ta3QgLnZhbHtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjE1cHg7Y29sb3I6dmFyKC0tdGV4dCl9Ci50YmwtbWt0IC52YWwubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOjEycHh9Ci50YmwtbWt0IC5jaGd7Zm9udC1zaXplOjEzcHg7Zm9udC13ZWlnaHQ6NjAwfQoudGJsLW1rdCAuY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0udGJsLW1rdCAuY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LnRibC1ta3QgLmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9Ci50Ymwtd3JhcHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OHB4O292ZXJmbG93OmhpZGRlbjttYXJnaW4tYm90dG9tOjE4cHh9Ci50YmwtaGRye2JhY2tncm91bmQ6dmFyKC0tYmczKTtwYWRkaW5nOjlweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcn0KLnRibC1oZHItdGl0bGV7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MS41cHh9Ci50YmwtaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQpmb290ZXJ7bWFyZ2luLXRvcDoyNHB4O3BhZGRpbmctdG9wOjEycHg7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtd2VpZ2h0OjUwMH0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KCjxkaXYgY2xhc3M9ImhkciI+CiAgPGRpdiBjbGFzcz0ibG9nbyI+VFJBREVSIDxzcGFuPkRFU0s8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0iaGRyLXJpZ2h0Ij4KICAgIDxkaXYgY2xhc3M9ImJhZGdlIj7il48gQU8gVklWTzwvZGl2PgogICAgPGRpdiBjbGFzcz0iaGRyLXRpbWUiIGlkPSJsYXN0LXVwZGF0ZSI+4oCUPC9kaXY+CiAgPC9kaXY+CjwvZGl2PgoKPGRpdiBjbGFzcz0idGFicyI+CiAgPGRpdiBjbGFzcz0idGFiIGFjdGl2ZSIgb25jbGljaz0ic3coJ2NvdGFjb2VzJyx0aGlzKSI+8J+TiiBDb3Rhw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygnaW5kaWNhZG9yZXMnLHRoaXMpIj7wn5OIIEluZGljYWRvcmVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygncG9zaWNvZXMnLHRoaXMpIj7wn5K8IFBvc2nDp8O1ZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3KCdjYWxlbmRhcmlvJyx0aGlzKSI+8J+ThSBDYWxlbmTDoXJpbzwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENPVEHDh8OVRVMg4pWQ4pWQIC0tPgo8ZGl2IGlkPSJ0YWItY290YWNvZXMiIGNsYXNzPSJ0YWItY29udGVudCBhY3RpdmUiPgogIDxkaXYgY2xhc3M9InRibC13cmFwIj4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5FVUEg4oCUIE1lcmNhZG9zPC9zcGFuPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpbWUiIGlkPSJsYXN0LXVwZGF0ZS10YmwiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDx0YWJsZSBjbGFzcz0idGJsLW1rdCI+CiAgICAgIDx0aGVhZD48dHI+PHRoPkF0aXZvPC90aD48dGggY2xhc3M9InIiPsOabHRpbW88L3RoPjx0aCBjbGFzcz0iciI+VmFyaWHDp8OjbzwvdGg+PHRoIGNsYXNzPSJyIj5WYXIuJTwvdGg+PC90cj48L3RoZWFkPgogICAgICA8dGJvZHk+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlMmYW1wO1AgRVMxKjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkZ1dHVybyBTJlAgNTAwPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImVzZi1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJlc2YtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZXNmLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPk5hc2RhcSBOUTwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkZ1dHVybyBOYXNkYXEgMTAwPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJucWYtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0ibnFmLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkRvdyBKb25lczwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPsONbmRpY2UgREpJQTwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJkamktcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZGppLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImRqaS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5WSVg8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5Wb2xhdGlsaWRhZGU8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InZpeC12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2aXgtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+RFhZPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+RMOzbGFyIEluZGV4PC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImR4eS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJkeHktdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZHh5LWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlVTRC9CUkw8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5Dw6JtYmlvIETDs2xhcjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJ1c2QtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0idXNkLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InVzZC1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0idGJsLXdyYXAiPgogICAgPGRpdiBjbGFzcz0idGJsLWhkciI+PHNwYW4gY2xhc3M9InRibC1oZHItdGl0bGUiPkIzIOKAlCBUb3AgMTA8L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+VmFyLiU8L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5JQk9WPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+w41uZGljZSBCb3Zlc3BhPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9Imlib3YtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iaWJvdi12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJpYm92LWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPldJTjEhPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+RnV0dXJvIElCT1Y8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0id2luLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Indpbi12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ3aW4tYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+UEVUUjQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5QZXRyb2JyYXMgUE48L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0icGV0cjRxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InBldHI0cS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJwZXRyNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+SVRVQjQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5JdGHDuiBVbmliYW5jbyBQTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJpdHViNHEtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iaXR1YjRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Iml0dWI0cS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5WQUxFMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlZhbGUgT048L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0idmFsZTNxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InZhbGUzcS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2YWxlM3EtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+QkJEQzQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5CcmFkZXNjbyBQTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJiYmRjNHEtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYmJkYzRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJiZGM0cS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5BQkVWMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkFtYmV2IE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImFiZXYzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJhYmV2M3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYWJldjNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJCQVMzPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+QmFuY28gZG8gQnJhc2lsIE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJiYXMzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJiYmFzM3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYmJhczNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPldFR0UzPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+V0VHIE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9IndlZ2UzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ3ZWdlM3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0id2VnZTNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlJPWE8zNDwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPk51YmFuayBCRFI8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0icm94bzM0cS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJyb3hvMzRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InJveG8zNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgPC90Ym9keT4KICAgIDwvdGFibGU+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Imp1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuIj48c3BhbiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+QjMgcG9yIFNlZ21lbnRvPC9zcGFuPjxidXR0b24gb25jbGljaz0iZXhwYW5kQWxsKCkiIGlkPSJidG4tZXhwYW5kIiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzMpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjb2xvcjp2YXIoLS1hY2NlbnQpO3BhZGRpbmc6NHB4IDEycHg7Zm9udC1zaXplOjExcHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweCI+KyBFeHBhbmRpciBUb2RvczwvYnV0dG9uPjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnZmluJykiPjxzcGFuPvCfj6YgRmluYW5jZWlybzwvc3Bhbj48c3BhbiBpZD0iYXItZmluIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItZmluIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1maW4iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygncGV0JykiPjxzcGFuPvCfm6IgUGV0csOzbGVvICZhbXA7IEfDoXM8L3NwYW4+PHNwYW4gaWQ9ImFyLXBldCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXBldCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctcGV0Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ21pbicpIj48c3Bhbj7im48gTWluZXJhw6fDo288L3NwYW4+PHNwYW4gaWQ9ImFyLW1pbiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW1pbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbWluIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ21hdCcpIj48c3Bhbj7wn4yyIFBhcGVsICZhbXA7IENlbHVsb3NlPC9zcGFuPjxzcGFuIGlkPSJhci1tYXQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1tYXQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW1hdCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCd1dGknKSI+PHNwYW4+4pqhIFV0aWxpZGFkZSBQw7pibGljYTwvc3Bhbj48c3BhbiBpZD0iYXItdXRpIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItdXRpIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy11dGkiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnY2MnKSI+PHNwYW4+8J+bjSBDb25zdW1vIEPDrWNsaWNvPC9zcGFuPjxzcGFuIGlkPSJhci1jYyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWNjIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1jYyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdjbicpIj48c3Bhbj7wn5uSIENvbnN1bW8gTsOjbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0iYXItY24iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1jbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctY24iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0Zygnc2F1JykiPjxzcGFuPvCfj6UgU2HDumRlPC9zcGFuPjxzcGFuIGlkPSJhci1zYXUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1zYXUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXNhdSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdpbmQnKSI+PHNwYW4+8J+PlyBCZW5zIEluZHVzdHJpYWlzPC9zcGFuPjxzcGFuIGlkPSJhci1pbmQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1pbmQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWluZCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCd0aXQnKSI+PHNwYW4+8J+SuyBUSSAmYW1wOyBDb211bmljYcOnw7Vlczwvc3Bhbj48c3BhbiBpZD0iYXItdGl0Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItdGl0Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy10aXQiPjwvZGl2PjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FVUEgcG9yIFNlZ21lbnRvPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdtNycpIj48c3Bhbj7irZAgNyBNYWduw61maWNhczwvc3Bhbj48c3BhbiBpZD0iYXItbTciPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1tNyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbTciPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnbnEnKSI+PHNwYW4+8J+SuyBOYXNkYXEgVG9wIDE1PC9zcGFuPjxzcGFuIGlkPSJhci1ucSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW5xIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1ucSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdzcCcpIj48c3Bhbj7wn5OKIFMmYW1wO1AgNTAwIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0iYXItc3AiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1zcCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9Imctc3AiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnZGonKSI+PHNwYW4+8J+PmyBEb3cgSm9uZXMgVG9wIDIwPC9zcGFuPjxzcGFuIGlkPSJhci1kaiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWRqIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1kaiI+PC9kaXY+PC9kaXY+CgogIDxkaXYgY2xhc3M9InRibC13cmFwIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5Db21tb2RpdGllczwvc3Bhbj48L2Rpdj4KICAgIDx0YWJsZSBjbGFzcz0idGJsLW1rdCI+CiAgICAgIDx0aGVhZD48dHI+PHRoPkF0aXZvPC90aD48dGggY2xhc3M9InIiPsOabHRpbW88L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5XVEkvQ0w8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5QZXRyw7NsZW8gV1RJPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImNsLXAiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkdPTEQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5PdXJvPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImdvbGQtcCI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+U0lMVkVSPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+UHJhdGE8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0ic2lsdmVyLXAiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkNPUFBFUjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkNvYnJlPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImNvcHBlci1wIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0idGJsLXdyYXAiPgogICAgPGRpdiBjbGFzcz0idGJsLWhkciI+PHNwYW4gY2xhc3M9InRibC1oZHItdGl0bGUiPkJpdGNvaW48L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+SW5mbzwvdGg+PC90cj48L3RoZWFkPgogICAgICA8dGJvZHk+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJUQy9VU0Q8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5CaXRjb2luIFNwb3Q8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iYnRjLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJ0Yy1jIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+QlRDIFJTSTwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlJTSSBTZW1hbmFsPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJ0Yy1yc2kiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+RnVuZGluZzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlRheGEgOGggQlRDPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJ0Yy1mdW5kIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PHRkIGNsYXNzPSJyIj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkZlYXIgJmFtcDsgR3JlZWQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj7DjW5kaWNlIHNlbnRpbWVudG88L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iZmctdmFsIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBpZD0iZmctbGJsIiBzdHlsZT0iZm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KICA8Zm9vdGVyPjxzcGFuIGlkPSJmb290ZXItdGltZSI+4oCUPC9zcGFuPjxzcGFuPlRyYWRlciBEZXNrIHYxMS4zPC9zcGFuPjwvZm9vdGVyPgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIElORElDQURPUkVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWluZGljYWRvcmVzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImRvdCI+PC9zcGFuPkNpY2xvIEJpdGNvaW48L2Rpdj4KICA8ZGl2IGlkPSJidGMtY3ljbGUtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTRweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDE1MHB4O2dhcDoxMHB4O21hcmdpbjoxNHB4IDAiPgogICAgPGRpdiBpZD0iZmctYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweCI+Q2FycmVnYW5kbyBGZWFyICZhbXA7IEdyZWVkLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTZweDt0ZXh0LWFsaWduOmNlbnRlciI+CiAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjZweDtmb250LXdlaWdodDo2MDA7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHgiPkJUQy9VU0Q8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImJ0Yy1pbmQtcCI+4oCUPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5CVEMgU2VtYW5hbDwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgoKICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OmZsZXgtZW5kO21hcmdpbi1ib3R0b206MTBweCI+CiAgICA8YnV0dG9uIG9uY2xpY2s9InRvZ2dsZUFsbEluZCgpIiBpZD0iYnRuLWFsbC1pbmQiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2NvbG9yOnZhcigtLWFjY2VudCk7cGFkZGluZzo1cHggMTRweDtmb250LXNpemU6MTFweDtjdXJzb3I6cG9pbnRlcjtmb250LWZhbWlseTppbmhlcml0O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4Ij7iiJIgUmVjb2xoZXIgVG9kb3M8L2J1dHRvbj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3BldHI0JykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9ImluZC1hY2MtdGl0bGUiPlBFVFI0IOKAlCBQZXRyb2JyYXMgUE48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+UGV0csOzbGVvICZhbXA7IEfDoXMgwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdwZXRyNCcpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1wZXRyNCI+4pa8PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWJvZHkgb3BlbiIgaWQ9InBldHI0LWluZC13cmFwIj48ZGl2IGlkPSJwZXRyNC1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3ZhbGUzJykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9ImluZC1hY2MtdGl0bGUiPlZBTEUzIOKAlCBWYWxlIE9OPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPk1pbmVyYcOnw6NvIMK3IGNsaXF1ZSBwYXJhIGV4cGFuZGlyL3JlY29saGVyPC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHgiPjxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxM3B4IiBvbmNsaWNrPSJldmVudC5zdG9wUHJvcGFnYXRpb24oKTtybCgndmFsZTMnKSI+4oa7PC9zcGFuPjxzcGFuIGlkPSJhci1pbmQtdmFsZTMiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJ2YWxlMy1pbmQtd3JhcCI+PGRpdiBpZD0idmFsZTMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iaW5kLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWhkciIgb25jbGljaz0idG9nSW5kKCdiYmFzMycpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5CQkFTMyDigJQgQmFuY28gZG8gQnJhc2lsIE9OPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPkJhbmNvcyDCtyBjbGlxdWUgcGFyYSBleHBhbmRpci9yZWNvbGhlcjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij48c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTNweCIgb25jbGljaz0iZXZlbnQuc3RvcFByb3BhZ2F0aW9uKCk7cmwoJ2JiYXMzJykiPuKGuzwvc3Bhbj48c3BhbiBpZD0iYXItaW5kLWJiYXMzIj7ilrw8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtYm9keSBvcGVuIiBpZD0iYmJhczMtaW5kLXdyYXAiPjxkaXYgaWQ9ImJiYXMzLWluZCI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImluZC1hY2MiPgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1oZHIiIG9uY2xpY2s9InRvZ0luZCgnYXhpYTMnKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy10aXRsZSI+QVhJQTMg4oCUIEF1cmVuIEVuZXJnaWEgT048L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+RW5lcmdpYSBFbMOpdHJpY2EgwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdheGlhMycpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1heGlhMyI+4pa8PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWJvZHkgb3BlbiIgaWQ9ImF4aWEzLWluZC13cmFwIj48ZGl2IGlkPSJheGlhMy1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3JveG8zNCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5ST1hPMzQg4oCUIE51YmFuayBCRFI8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+RmludGVjaCDCtyBjbGlxdWUgcGFyYSBleHBhbmRpci9yZWNvbGhlcjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij48c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTNweCIgb25jbGljaz0iZXZlbnQuc3RvcFByb3BhZ2F0aW9uKCk7cmwoJ3JveG8zNCcpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1yb3hvMzQiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJyb3hvMzQtaW5kLXdyYXAiPjxkaXYgaWQ9InJveG8zNC1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBQT1NJw4fDlUVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLXBvc2ljb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Imp1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuIj48c3BhbiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+T3BlcmHDp8O1ZXMgQXRpdmFzPC9zcGFuPjxidXR0b24gb25jbGljaz0idG9nZ2xlQWxsUG9zKCkiIGlkPSJidG4tYWxsLXBvcyIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y29sb3I6dmFyKC0tYWNjZW50KTtwYWRkaW5nOjRweCAxMnB4O2ZvbnQtc2l6ZToxMXB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NjAwIj7iiJIgUmVjb2xoZXIgVG9kYXM8L2J1dHRvbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1wdCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5QRVRSNDwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5QZXRyb2JyYXMgUE4gwrcgQ2FsbCBWZW5kaWRhIMK3IFBFVFJMMzE5IMK3IFZlbmMgMTcvMTIvMjAyNjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLXJpZ2h0Ij4KICAgICAgICA8ZGl2PjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJwdC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJwdC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLXB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLXB0Ij4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChQRVRSTDMxOSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDMwLDg1PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJwdC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE3LzEyLzIwMjYgwrcgPHNwYW4gaWQ9InB0LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+NDMsNCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIEImYW1wO1MgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+OSw0JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gTUMgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siIGlkPSJwdC1tYy1ydCI+Y2FsYy4uLjwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnIj4KICAgICAgPGRpdiBjbGFzcz0ic2d0Ij7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWxsIHNlciBleGVyY2lkYTwvZGl2PgogICAgICA8ZGl2IGlkPSJwdC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJwdC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIGV4ZXJjZXI8L2Rpdj48ZGl2IGNsYXNzPSJpdiIgaWQ9InB0LW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InB0LW1jLXYiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJwdC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1hY2MiPgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1oZHIiIG9uY2xpY2s9InRvZ1BvcygncG9zLXZsJykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9InBvcy1hY2MtdGsiPlZBTEUzPC9kaXY+PGRpdiBjbGFzcz0icG9zLWFjYy1zdWIiPlZhbGUgT04gwrcgQ2FsbCBWZW5kaWRhIMK3IFZBTEVCNTc0IMK3IFZlbmMgMTgvMDIvMjAyNzwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLXJpZ2h0Ij4KICAgICAgICA8ZGl2PjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJ2bC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJ2bC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLXZsIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLXZsIj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChWQUxFQjU3NCk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDU3LDQwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJ2bC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE4LzAyLzIwMjcgwrcgPHNwYW4gaWQ9InZsLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+NzEsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIEImYW1wO1MgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MTQsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIE1DIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIiBpZD0idmwtbWMtcnQiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FsbCBzZXIgZXhlcmNpZGE8L2Rpdj4KICAgICAgPGRpdiBpZD0idmwtbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kbyA1LjAwMCBjZW7DoXJpb3MuLi48L2Rpdj4KICAgICAgPGRpdiBpZD0idmwtbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Qcm9iLiBleGVyY2VyPC9kaXY+PGRpdiBjbGFzcz0iaXYiIGlkPSJ2bC1tYy1zIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJ2bC1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHg7bGluZS1oZWlnaHQ6MS41IiBpZD0idmwtbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1hMycpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5BWElBMzwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5BWElBMyAoQSkgwrcgQmlkaXJlY2lvbmFsIMK3IFZlbmMgMTQvMDkvMjAyNjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLXJpZ2h0Ij4KICAgICAgICA8ZGl2PjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJhMy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJhMy1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLWEzIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLWEzIj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNDMsNTE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPktVTyAoKzI2LDYlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNjgsNzY8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+YXTDqSArMzEsMiUgLyArMjAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPis0JSBmaXhvPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTQvMDkvMjAyNiDCtyA8c3BhbiBpZD0iYTMtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTMta2RvIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtVTzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1rdW8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1zdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJhMy1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzLW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+U2VtIEJhcnJlaXJhIOKchTwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIiBpZD0iYTMtbWMtbmIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzLW1jLWt1Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpdiBkb3duIiBpZD0iYTMtbWMta2QiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzLW1jLXZvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJhMy1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1hY2MiPgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1oZHIiIG9uY2xpY2s9InRvZ1BvcygncG9zLWEzYicpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5BWElBMzwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5BWElBMyAoQikgwrcgQmlkaXJlY2lvbmFsIElPTiBJdGHDuiDCtyBWZW5jIDAyLzEwLzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0iYTNiLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9ImEzYi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLWEzYiIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1hM2IiPgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA0MCw1Mjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S1VPICgrMjQlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNjIsODE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+YXTDqSArMzEsMiUgLyArMjAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPis0JSBmaXhvICgxMiwzMyUgYS5hLik8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4wMi8xMC8yMDI2IMK3IDxzcGFuIGlkPSJhM2ItZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLWtkbyI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLWt1byI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzYi1zdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siIGlkPSJhM2ItbWMtbmIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzYi1tYy1rdSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaXYgZG93biIgaWQ9ImEzYi1tYy1rZCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTNiLW1jLXZvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJhM2ItbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1yeCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5ST1hPMzQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+Uk9YTzM0IMK3IEJEUiBOdWJhbmsgwrcgTGFuw6dhbWVudG8gQ29iZXJ0byDCtyBST1hPRzEwNSDCtyBWZW5jIDE2LzA3LzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0icngtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icGMyIiBpZD0icngtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPHNwYW4gaWQ9ImFyLXBvcy1yeCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1yeCI+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlN0cmlrZSAoUk9YT0cxMDUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCAxMCw1MCDCtyBJVE0g4pqgPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJyeC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE2LzA3LzIwMjYgwrcgPHNwYW4gaWQ9InJ4LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MzMsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRlbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4wLDY0Mzwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iPjYwLDQlIOKaoDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gTUMgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJyeC1tYy1ydCI+Y2FsYy4uLjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+T2JqZXRpdm88L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5GZWNoYXIgYWJhaXhvIGRlIFIkIDEwLDUwPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIHN1Y2Vzc288L2Rpdj4KICAgICAgPGRpdiBpZD0icngtbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJyeC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIFN1Y2Vzc288L2Rpdj48ZGl2IGNsYXNzPSJpdiBvayIgaWQ9InJ4LW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5DYWxsIEV4ZXJjaWRhPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InJ4LW1jLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5LRE8gQXRpbmdpZG88L2Rpdj48ZGl2IGNsYXNzPSJpdiBkb3duIiBpZD0icngtbWMtayI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icngtbWMtdiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4IiBpZD0icngtbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjIwcHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWhkciIgb25jbGljaz0idG9nUG9zKCdwb3MtYmInKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0icG9zLWFjYy10ayI+QkJBUzM8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+QmFuY28gZG8gQnJhc2lsIE9OIMK3IExhbsOnYW1lbnRvIENvYmVydG8gwrcgQkJBU0gyMSDCtyBWZW5jIDIwLzA4LzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0iYmItcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icGMyIiBpZD0iYmItYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPHNwYW4gaWQ9ImFyLXBvcy1iYiIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1iYiI+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlN0cmlrZSAoQkJBU0gyMSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDIxLDY1IMK3IElUTTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJlw6dvIHZzIHN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YgaXRtIiBpZD0iYmItaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4yMC8wOC8yMDI2IMK3IDxzcGFuIGlkPSJiYi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZvbC4gSW1wbC48L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjI3LDElPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EZWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjAsMjQ5PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBCJmFtcDtTIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjIxLDMlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBNQyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayIgaWQ9ImJiLW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5PYmpldGl2bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPkZlY2hhciBhYmFpeG8gZGUgUiQgMjEsNjU8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FsbCBzZXIgZXhlcmNpZGE8L2Rpdj4KICAgICAgPGRpdiBpZD0iYmItbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kbyA1LjAwMCBjZW7DoXJpb3MuLi48L2Rpdj4KICAgICAgPGRpdiBpZD0iYmItbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Qcm9iLiBleGVyY2VyPC9kaXY+PGRpdiBjbGFzcz0iaXYiIGlkPSJiYi1tYy1zIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJiYi1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHg7bGluZS1oZWlnaHQ6MS41IiBpZD0iYmItbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjp2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLW11dGVkKSI+CiAgICA8ZGl2IGNsYXNzPSJwdCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTZweCI+QVhJQTMgU2hvcnQgU3RyYW5nbGU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5DYWxsIFYuIEFYSUFJNTA1PC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+UiQgNTAsNTA8L3NwYW4+PC9kaXY+PGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+4pyFIEHDp8O1ZXMgbGliZXJhZGFzPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIiBzdHlsZT0ib3BhY2l0eTouNTtib3JkZXItY29sb3I6dmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdC1jb2xvcjp2YXIoLS1tdXRlZCkiPgogICAgPGRpdiBjbGFzcz0icHQiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjE2cHgiPlJPWE8zNCBQcmVmaXhhZG8gNywxJTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkVuY2VycmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjA0LzA2LzIwMjY8L3NwYW4+PC9kaXY+PGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+4pyFIH41LDE3JSAoNzIlIGRvIGFsdm8pPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENBTEVORMOBUklPIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWNhbGVuZGFyaW8iIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjE0cHgiPgogICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtd2VpZ2h0OjUwMCI+8J+HuvCfh7gg8J+Hp/Cfh7cg8J+HqvCfh7og8J+HrPCfh6cg8J+HqPCfh7Mg8J+Hr/Cfh7Ug8J+HqfCfh6ogwrcgSW1wYWN0byBNw6lkaW8rPC9kaXY+CiAgICA8YnV0dG9uIG9uY2xpY2s9IndpbmRvdy5sb2NhdGlvbi5yZWxvYWQoKSIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtib3JkZXI6bm9uZTtjb2xvcjojZmZmO3BhZGRpbmc6OHB4IDE4cHg7Zm9udC1zaXplOjEycHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo3MDA7bGV0dGVyLXNwYWNpbmc6LjVweCI+4oa7IEF0dWFsaXphcjwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgaWQ9ImNhbC1zdCIgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjhweCI+PC9kaXY+CiAgPGRpdiBpZD0iY2FsLWFyZWEiPjxkaXYgc3R5bGU9ImZvbnQtZmFtaWx5OkludGVyLHNhbnMtc2VyaWYiPjxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MjBweCI+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDojMWExYTI0O3BhZGRpbmc6OHB4IDE0cHg7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOiM3YzZhZjc7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItbGVmdDozcHggc29saWQgIzdjNmFmNzttYXJnaW4tYm90dG9tOjJweCI+TW9uZGF5IDE1LzA2PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4eq8J+Hujwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDQ6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5FQ0IgUHJlc2lkZW50IExhZ2FyZGUgU3BlYWtzPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY5ODAwO3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PC9kaXY+PGRpdiBzdHlsZT0ibWFyZ2luLWJvdHRvbToyMHB4Ij48ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOiMxYTFhMjQ7cGFkZGluZzo4cHggMTRweDtmb250LXNpemU6MTFweDtmb250LXdlaWdodDo3MDA7Y29sb3I6IzdjNmFmNzt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2JvcmRlci1sZWZ0OjNweCBzb2xpZCAjN2M2YWY3O21hcmdpbi1ib3R0b206MnB4Ij5UdWVzZGF5IDE2LzA2PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4ev8J+HtTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDA6MTk8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5CT0ogUG9saWN5IFJhdGU8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPjwxLjAwJTwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6/wn4e1PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMDoxOTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPk1vbmV0YXJ5IFBvbGljeSBTdGF0ZW1lbnQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6bwn4e6PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMTozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPkNhc2ggUmF0ZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+NC4zNSU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4em8J+Hujwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDE6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5SQkEgUmF0ZSBTdGF0ZW1lbnQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6bwn4e6PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMjozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlJCQSBQcmVzcyBDb25mZXJlbmNlPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4ev8J+HtTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDM6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5CT0ogUHJlc3MgQ29uZmVyZW5jZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjwvZGl2PjxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MjBweCI+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDojMWExYTI0O3BhZGRpbmc6OHB4IDE0cHg7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOiM3YzZhZjc7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItbGVmdDozcHggc29saWQgIzdjNmFmNzttYXJnaW4tYm90dG9tOjJweCI+V2VkbmVzZGF5IDE3LzA2PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4es8J+Hpzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDM6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5DUEkgeS95PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4zLjAlPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HqvCfh7o8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA3OjUwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+RUNCIFByZXNpZGVudCBMYWdhcmRlIFNwZWFrczwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA5OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+Q29yZSBSZXRhaWwgU2FsZXMgbS9tPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY5ODAwO3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4wLjYlPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA5OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+UmV0YWlsIFNhbGVzIG0vbTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MC41JTwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh7rwn4e4PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4xMTo0NTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlByZXNpZGVudCBUcnVtcCBTcGVha3M8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjk4MDA7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh7rwn4e4PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4xNTowMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPkZlZGVyYWwgRnVuZHMgUmF0ZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+My43NSU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4e68J+HuDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MTU6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5GT01DIEVjb25vbWljIFByb2plY3Rpb25zPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4e68J+HuDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MTU6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5GT01DIFN0YXRlbWVudDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjE1OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+Rk9NQyBQcmVzcyBDb25mZXJlbmNlPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4ez8J+Hvzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MTk6NDU8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5HRFAgcS9xPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4wLjglPC9zcGFuPjwvZGl2PjwvZGl2PjxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MjBweCI+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDojMWExYTI0O3BhZGRpbmc6OHB4IDE0cHg7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOiM3YzZhZjc7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItbGVmdDozcHggc29saWQgIzdjNmFmNzttYXJnaW4tYm90dG9tOjJweCI+VGh1cnNkYXkgMTgvMDY8L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6zwn4enPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMzowMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPkNsYWltYW50IENvdW50IENoYW5nZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MjUuOEs8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4es8J+Hpzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDM6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5BdmVyYWdlIEVhcm5pbmdzIEluZGV4IDNtL3k8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjk4MDA7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPjQuMCU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4eo8J+HrTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDQ6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5TTkIgTW9uZXRhcnkgUG9saWN5IEFzc2Vzc21lbnQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6jwn4etPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wNDozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlNOQiBQb2xpY3kgUmF0ZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MC4wMCU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4eo8J+HrTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDU6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5TTkIgUHJlc3MgQ29uZmVyZW5jZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HrPCfh6c8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA4OjAwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+TW9uZXRhcnkgUG9saWN5IFN1bW1hcnk8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6zwn4enPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wODowMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPk1QQyBPZmZpY2lhbCBCYW5rIFJhdGUgVm90ZXM8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPjEtMC04PC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HrPCfh6c8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA4OjAwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+T2ZmaWNpYWwgQmFuayBSYXRlPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4zLjc1JTwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh7rwn4e4PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wOTozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlBoaWxseSBGZWQgTWFudWZhY3R1cmluZyBJbmRleDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+OS44PC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA5OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+VW5lbXBsb3ltZW50IENsYWltczwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MjI1Szwvc3Bhbj48L2Rpdj48L2Rpdj48ZGl2IHN0eWxlPSJtYXJnaW4tYm90dG9tOjIwcHgiPjxkaXYgc3R5bGU9ImJhY2tncm91bmQ6IzFhMWEyNDtwYWRkaW5nOjhweCAxNHB4O2ZvbnQtc2l6ZToxMXB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjojN2M2YWY3O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzoxcHg7Ym9yZGVyLWxlZnQ6M3B4IHNvbGlkICM3YzZhZjc7bWFyZ2luLWJvdHRvbToycHgiPkZyaWRheSAxOS8wNjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HrPCfh6c8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjAzOjAwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+UmV0YWlsIFNhbGVzIG0vbTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MC41JTwvc3Bhbj48L2Rpdj48L2Rpdj48L2Rpdj48L2Rpdj4KPC9kaXY+Cgo8c2NyaXB0Pgpjb25zdCBCPSdodHRwczovL3RyYWRlci1kZXNrLm9ucmVuZGVyLmNvbSc7CmNvbnN0IFNFRz17CiAgZmluOlsnSVRVQjQnLCdCQkRDNCcsJ0JCQVMzJywnU0FOQjExJywnQjNTQTMnLCdCUEFDMTEnLCdJVFNBNCcsJ0JSU1I2JywnQUJDQjQnLCdCTUdCNCddLAogIHBldDpbJ1BFVFI0JywnUEVUUjMnLCdQUklPMycsJ0JSQVYzJywnVkJCUjMnLCdDU0FOMycsJ1JFQ1YzJywnVUdQQTMnLCdTRVFMMycsJ0dHQlI0J10sCiAgbWluOlsnVkFMRTMnLCdHR0JSNCcsJ0NTTkEzJywnVVNJTTUnLCdCUkFQNCcsJ0ZFU0E0JywnQ01JTjMnLCdDQkFWMycsJ0dPQVU0JywnUEdNTjMnXSwKICBtYXQ6WydTVVpCMycsJ0tMQk4xMScsJ0RYQ08zJywnVU5JUDYnLCdSQU5JMycsJ09SVlIzJywnU01UTzMnLCdGUkFTMycsJ0xQU0IzJywnQ1NVRDMnXSwKICB1dGk6WydBWElBMycsJ0VRVEwzJywnQ1BGRTMnLCdTQlNQMycsJ0NNSUc0JywnRU5HSTExJywnVEFFRTExJywnQVVSRTMnLCdFR0lFMycsJ0NQTEUzJ10sCiAgY2M6IFsnUkVOVDMnLCdMUkVOMycsJ01HTFUzJywnQ1lSRTMnLCdNUlZFMycsJ0FaWkEzJywnVklWQTMnLCdTQkZHMycsJ1lEVVEzJywnTU9WSTMnXSwKICBjbjogWydBQkVWMycsJ0pCU1MzJywnQlJGUzMnLCdOQVRVMycsJ01ESUEzJywnQkVFRjMnLCdTTENFMycsJ01UUkUzJywnQ0FNTDMnLCdQQ0FSMyddLAogIHNhdTpbJ1JET1IzJywnSEFQVjMnLCdGTFJZMycsJ0RBU0EzJywnUVVBTDMnLCdPTkNPMycsJ1BOVkwzJywnT0RQVjMnLCdNQVREMycsJ0FBTFIzJ10sCiAgaW5kOlsnV0VHRTMnLCdFTUJSMycsJ1JBSUwzJywnVEdNQTMnLCdST01JMycsJ1ZMSUQzJywnVFVQWTMnLCdJUkJSMycsJ1BPTU80JywnTEFWVjMnXSwKICB0aXQ6WydWSVZUMycsJ1RJTVMzJywnVE9UVlMzJywnUE9TSTMnLCdNTEFTMycsJ0FOSU0zJywnSU5UQjMnLCdMV1NBMycsJ0NBU0gzJywnT0lCUjMnXSwKfTsKY29uc3QgVVNTRUc9ewogIG03OlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ0dPT0dMJywnTUVUQScsJ1RTTEEnXSwKICBucTpbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdNRVRBJywnR09PR0wnLCdUU0xBJywnQVZHTycsJ0NPU1QnLCdORkxYJywnUUNPTScsJ0FNRCcsJ0FEQkUnLCdJTlRDJywnQ1NDTyddLAogIHNwOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQlJLLkInLCdKUE0nLCdMTFknLCdWJywnVU5IJywnWE9NJywnTUEnLCdORkxYJywnUEcnLCdKTkonLCdIRCcsJ0JBQyddLAogIGRqOlsnVU5IJywnR1MnLCdIRCcsJ1NIVycsJ0NBVCcsJ0FYUCcsJ01DRCcsJ0FNR04nLCdWJywnVFJWJywnSUJNJywnSlBNJywnSE9OJywnQ1JNJywnQ1ZYJywnQUFQTCcsJ01TRlQnLCdESVMnLCdOS0UnLCdCQSddCn07CmNvbnN0IGZSPXY9PnYhPW51bGw/J1IkICcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21pbmltdW1GcmFjdGlvbkRpZ2l0czoyLG1heGltdW1GcmFjdGlvbkRpZ2l0czoyfSk6J+KAlCc7CmNvbnN0IGZVPXY9PnYhPW51bGw/J1VTJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmUD12PT52IT1udWxsP051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwpmdW5jdGlvbiBFKGlkLHQpe2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKCFlKXJldHVybjtlLnRleHRDb250ZW50PXQ7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQpmdW5jdGlvbiBDaFRibChpZFYsaWRQY3Qsbm93LHByZXYsdHApewogIGNvbnN0IGRpZmY9bm93LXByZXYscGN0PShkaWZmL01hdGguYWJzKHByZXZ8fDEpKjEwMCksc2c9ZGlmZj49MD8nKyc6Jyc7CiAgY29uc3QgY2xzPWRpZmY+MD8nY2hnIGNoZy11cCc6ZGlmZjwwPydjaGcgY2hnLWRuJzonY2hnIGNoZy1mbCc7CiAgbGV0IHZhclN0cj0nJzsKICBpZih0cD09PSdyJyl2YXJTdHI9c2crJ1IkICcrTWF0aC5hYnMoZGlmZikudG9GaXhlZCgyKTsKICBlbHNlIGlmKHRwPT09J3UnKXZhclN0cj1zZytNYXRoLmFicyhkaWZmKS50b0ZpeGVkKDIpOwogIGVsc2UgdmFyU3RyPXNnK01hdGguYWJzKGRpZmYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk7CiAgY29uc3QgcGN0U3RyPXNnK3BjdC50b0ZpeGVkKDIpKyclJzsKICBjb25zdCBldj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZFYpO2lmKGV2KXtldi50ZXh0Q29udGVudD12YXJTdHI7ZXYuY2xhc3NOYW1lPWNsczt9CiAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWRQY3QpO2lmKGVwKXtlcC50ZXh0Q29udGVudD1wY3RTdHI7ZXAuY2xhc3NOYW1lPWNsczt9Cn0KZnVuY3Rpb24gQ2goaWQsbixwLHRwKXsKICBjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47CiAgY29uc3QgZD1uLXAscGM9KGQvTWF0aC5hYnMocHx8MSkqMTAwKS50b0ZpeGVkKDIpLHNnPWQ+PTA/JysnOicnOwogIGlmKHRwPT09J3InKWUudGV4dENvbnRlbnQ9c2crJ1IkICcrTWF0aC5hYnMoZCkudG9GaXhlZCgyKSsnICgnK3NnK3BjKyclKSc7CiAgZWxzZSBpZih0cD09PSd1JyllLnRleHRDb250ZW50PXNnK2QudG9GaXhlZCgyKSsnICgnK3NnK3BjKyclKSc7CiAgZWxzZSBlLnRleHRDb250ZW50PXNnK01hdGguYWJzKGQpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJyAoJytzZytwYysnJSknOwogIGUuY2xhc3NOYW1lPSdjYyAnKyhkPjA/J2NoZy11cCc6ZDwwPydjaGctZG4nOidjaGctZmwnKTsKfQpmdW5jdGlvbiBzdyh0LGVsKXsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiJykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiLWNvbnRlbnQnKS5mb3JFYWNoKHg9PnguY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJykpOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0YWItJyt0KS5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZihlbCllbC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZih0PT09J2luZGljYWRvcmVzJyYmIXdpbmRvdy5fSUwpe3dpbmRvdy5fSUw9dHJ1ZTtsb2FkSW5kKCk7fQoKfQpmdW5jdGlvbiB0ZyhpZCl7CiAgY29uc3QgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2ItJytpZCksYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXItJytpZCk7CiAgaWYoIWIpcmV0dXJuO2NvbnN0IG9wPWIuc3R5bGUuZGlzcGxheSE9PSdibG9jayc7CiAgYi5zdHlsZS5kaXNwbGF5PW9wPydibG9jayc6J25vbmUnOwogIGlmKGEpYS50ZXh0Q29udGVudD1vcD8n4payJzon4pa8JzsKICBpZihvcCYmIWIuZGF0YXNldC5sKXtiLmRhdGFzZXQubD0nMSc7bG9hZFNlZyhpZCk7fQp9Cgphc3luYyBmdW5jdGlvbiBsb2FkU2VnKGlkKXsKICBjb25zdCBnPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdnLScraWQpO2lmKCFnKXJldHVybjsKICBjb25zdCBwZng9aWQrJ18nOwogIGlmKFVTU0VHW2lkXSl7CiAgICBjb25zdCB0a3M9VVNTRUdbaWRdOwogICAgZy5pbm5lckhUTUw9dGtzLm1hcCh0PT57Y29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTtyZXR1cm4gJzxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iY2wiPlVTPC9kaXY+PGRpdiBjbGFzcz0iY24iPicrdCsnPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0iJytwZngrdGlkKydfYyI+4oCUPC9kaXY+PC9kaXY+Jzt9KS5qb2luKCcnKTsKICAgIHRyeXsKICAgICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvdXMvcXVvdGVzP3RpY2tlcnM9Jyt0a3Muam9pbignLCcpKTsKICAgICAgaWYoIXIub2spcmV0dXJuOwogICAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgICBPYmplY3QuZW50cmllcyhkKS5mb3JFYWNoKChbdCx2XSk9PnsKICAgICAgICBjb25zdCB0aWQ9dC5yZXBsYWNlKC9bXmEtekEtWjAtOV0vZywnXycpOwogICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19wJyk7CiAgICAgICAgaWYoZXAmJnYucHJpY2Upe2VwLnRleHRDb250ZW50PSckJytOdW1iZXIodi5wcmljZSkudG9GaXhlZCgyKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQogICAgICAgIGlmKHYucHJpY2UmJnYucHJldilDaChwZngrdGlkKydfYycsdi5wcmljZSx2LnByZXYsJ3UnKTsKICAgICAgfSk7CiAgICB9Y2F0Y2goZSl7fQogICAgcmV0dXJuOwogIH0KICBjb25zdCB0a3M9U0VHW2lkXTtpZighdGtzKXJldHVybjsKICBnLmlubmVySFRNTD0nPGRpdiBjbGFzcz0idGJsLXdyYXAiPjx0YWJsZSBjbGFzcz0idGJsLW1rdCI+PHRoZWFkPjx0cj48dGg+QXRpdm88L3RoPjx0aCBjbGFzcz0iciI+w5psdGltbzwvdGg+PHRoIGNsYXNzPSJyIj5WYXJpYcOnw6NvPC90aD48dGggY2xhc3M9InIiPlZhci4lPC90aD48L3RyPjwvdGhlYWQ+PHRib2R5PicrCiAgICB0a3MubWFwKHQ9Pntjb25zdCB0aWQ9dC50b0xvd2VyQ2FzZSgpO3JldHVybiAnPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPicrdCsnPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9IicrcGZ4K3RpZCsnX3YiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9IicrcGZ4K3RpZCsnX2MiPuKAlDwvc3Bhbj48L3RkPjwvdHI+Jzt9KS5qb2luKCcnKSsKICAgICc8L3Rib2R5PjwvdGFibGU+PC9kaXY+JzsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy90di9icmF6aWwnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzLm1hcCh0PT4nQk1GQk9WRVNQQTonK3QpfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pOwogICAgaWYoIXIub2spdGhyb3cgbmV3IEVycm9yKCdUViBmYWlsJyk7CiAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgY29uc3QgbG9hZGVkPW5ldyBTZXQoKTsKICAgIChkLmRhdGF8fFtdKS5mb3JFYWNoKHg9PnsKICAgICAgY29uc3QgdD14LnMucmVwbGFjZSgnQk1GQk9WRVNQQTonLCcnKS50b0xvd2VyQ2FzZSgpOwogICAgICBjb25zdFtjLGNhXT14LmR8fFtdOwogICAgICBpZihjIT1udWxsKXsKICAgICAgICBjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdCsnX3AnKTsKICAgICAgICBpZihlcCl7ZXAudGV4dENvbnRlbnQ9ZlIoYyk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO2xvYWRlZC5hZGQodCk7fQogICAgICAgIENoVGJsKHBmeCt0KydfdicscGZ4K3QrJ19jJyxjLGMtKGNhfHwwKSwncicpOwogICAgICB9CiAgICB9KTsKICAgIC8vIEZhbGxiYWNrIHZpYSBicmFwaSBwYXJhIHRpY2tlcnMgcXVlIFRWIG7Do28gcmV0b3Jub3UKICAgIGNvbnN0IG1pc3Npbmc9dGtzLmZpbHRlcih0PT4hbG9hZGVkLmhhcyh0LnRvTG93ZXJDYXNlKCkpKTsKICAgIGlmKG1pc3NpbmcubGVuZ3RoPjApewogICAgICB0cnl7CiAgICAgICAgY29uc3QgcmI9YXdhaXQgZmV0Y2goQisnL3R2L2JyYXppbCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6bWlzc2luZy5tYXAodD0+J0JNRkJPVkVTUEE6Jyt0KX0sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTsKICAgICAgICAvLyBTZWd1bmRhIHRlbnRhdGl2YSBpbWVkaWF0YQogICAgICB9Y2F0Y2goZTIpe30KICAgICAgLy8gRmFsbGJhY2sgaW5kaXZpZHVhbCB2aWEgL2luZGljYXRvcnMKICAgICAgZm9yKGNvbnN0IHQgb2YgbWlzc2luZyl7CiAgICAgICAgdHJ5ewogICAgICAgICAgY29uc3QgcjI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvJyt0KycuU0EnKTsKICAgICAgICAgIGlmKCFyMi5vayljb250aW51ZTsKICAgICAgICAgIGNvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICAgIGlmKGQyLnByZWNvX2F0dWFsKXsKICAgICAgICAgICAgY29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTsKICAgICAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICAgICAgaWYoZXApe2VwLnRleHRDb250ZW50PWZSKGQyLnByZWNvX2F0dWFsKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQogICAgICAgICAgICBpZihkMi5wcmVjb19hbnRlcmlvcilDaFRibChwZngrdGlkKydfdicscGZ4K3RpZCsnX2MnLGQyLnByZWNvX2F0dWFsLGQyLnByZWNvX2FudGVyaW9yLCdyJyk7CiAgICAgICAgICB9CiAgICAgICAgfWNhdGNoKGUyKXt9CiAgICAgIH0KICAgIH0KICB9Y2F0Y2goZSl7CiAgICAvLyBUViBmYWxob3UgY29tcGxldGFtZW50ZSDigJQgZmFsbGJhY2sgcGFyYSB0b2RvcyB2aWEgL2luZGljYXRvcnMKICAgIGZvcihjb25zdCB0IG9mIHRrcy5zbGljZSgwLDYpKXsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdCsnLlNBJyk7CiAgICAgICAgaWYoIXIyLm9rKWNvbnRpbnVlOwogICAgICAgIGNvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICBjb25zdCB0aWQ9dC50b0xvd2VyQ2FzZSgpOwogICAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mUihkMi5wcmVjb19hdHVhbCk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICB9CiAgICAgIH1jYXRjaChlMil7fQogICAgfQogIH0KfQoKZnVuY3Rpb24gZXhwYW5kQWxsKCl7CiAgY29uc3QgYnRuPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidG4tZXhwYW5kJyk7CiAgY29uc3Qgc2Vncz1bJ2ZpbicsJ3BldCcsJ21pbicsJ21hdCcsJ3V0aScsJ2NjJywnY24nLCdzYXUnLCdpbmQnLCd0aXQnXTsKICBjb25zdCBhbnlPcGVuPXNlZ3Muc29tZShpZD0+ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NiLScraWQpPy5zdHlsZS5kaXNwbGF5PT09J2Jsb2NrJyk7CiAgc2Vncy5mb3JFYWNoKGlkPT57CiAgICBjb25zdCBiPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYi0nK2lkKSxhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci0nK2lkKTsKICAgIGlmKCFiKXJldHVybjsKICAgIGlmKGFueU9wZW4pe2Iuc3R5bGUuZGlzcGxheT0nbm9uZSc7aWYoYSlhLnRleHRDb250ZW50PSfilrwnO30KICAgIGVsc2V7CiAgICAgIGIuc3R5bGUuZGlzcGxheT0nYmxvY2snO2lmKGEpYS50ZXh0Q29udGVudD0n4payJzsKICAgICAgaWYoIWIuZGF0YXNldC5sKXtiLmRhdGFzZXQubD0nMSc7bG9hZFNlZyhpZCk7fQogICAgfQogIH0pOwogIGlmKGJ0bilidG4udGV4dENvbnRlbnQ9YW55T3Blbj8nKyBFeHBhbmRpciBUb2Rvcyc6J+KIkiBSZWNvbGhlciBUb2Rvcyc7Cn0KZnVuY3Rpb24gdG9nUG9zKGlkKXsKICBjb25zdCBib2R5PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdib2R5LScraWQpOwogIGNvbnN0IGFycj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXItJytpZCk7CiAgaWYoIWJvZHkpcmV0dXJuOwogIGNvbnN0IG9wZW49Ym9keS5jbGFzc0xpc3QuY29udGFpbnMoJ29wZW4nKTsKICBib2R5LmNsYXNzTGlzdC50b2dnbGUoJ29wZW4nLCFvcGVuKTsKICBpZihhcnIpYXJyLnRleHRDb250ZW50PW9wZW4/J+KWtic6J+KWvCc7Cn0KZnVuY3Rpb24gdG9nZ2xlQWxsUG9zKCl7CiAgY29uc3QgaWRzPVsncG9zLXB0JywncG9zLXZsJywncG9zLWEzJywncG9zLWEzYicsJ3Bvcy1yeCcsJ3Bvcy1iYiddOwogIGNvbnN0IGJ0bj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRuLWFsbC1wb3MnKTsKICBjb25zdCBhbnlPcGVuPWlkcy5zb21lKGlkPT5kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYm9keS0nK2lkKT8uY2xhc3NMaXN0LmNvbnRhaW5zKCdvcGVuJykpOwogIGlkcy5mb3JFYWNoKGlkPT57CiAgICBjb25zdCBib2R5PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdib2R5LScraWQpOwogICAgY29uc3QgYXJyPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci0nK2lkKTsKICAgIGlmKGJvZHkpe2JvZHkuY2xhc3NMaXN0LnRvZ2dsZSgnb3BlbicsIWFueU9wZW4pO2lmKGFycilhcnIudGV4dENvbnRlbnQ9YW55T3Blbj8n4pa2Jzon4pa8Jzt9CiAgfSk7CiAgaWYoYnRuKWJ0bi50ZXh0Q29udGVudD1hbnlPcGVuPyfiiJIgUmVjb2xoZXIgVG9kYXMnOicrIEV4cGFuZGlyIFRvZGFzJzsKfQpmdW5jdGlvbiB0b2dJbmQoaWQpewogIGNvbnN0IGJvZHk9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQrJy1pbmQtd3JhcCcpOwogIGNvbnN0IGFycj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXItaW5kLScraWQpOwogIGlmKCFib2R5KXJldHVybjsKICBjb25zdCBvcGVuPWJvZHkuY2xhc3NMaXN0LmNvbnRhaW5zKCdvcGVuJyk7CiAgYm9keS5jbGFzc0xpc3QudG9nZ2xlKCdvcGVuJywhb3Blbik7CiAgaWYoYXJyKWFyci50ZXh0Q29udGVudD1vcGVuPyfilrYnOifilrwnOwp9CmZ1bmN0aW9uIHRvZ2dsZUFsbEluZCgpewogIGNvbnN0IGlkcz1bJ3BldHI0JywndmFsZTMnLCdiYmFzMycsJ2F4aWEzJywncm94bzM0J107CiAgY29uc3QgYnRuPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidG4tYWxsLWluZCcpOwogIGNvbnN0IGFueU9wZW49aWRzLnNvbWUoaWQ9PmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKyctaW5kLXdyYXAnKT8uY2xhc3NMaXN0LmNvbnRhaW5zKCdvcGVuJykpOwogIGlkcy5mb3JFYWNoKGlkPT57CiAgICBjb25zdCBib2R5PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKyctaW5kLXdyYXAnKTsKICAgIGNvbnN0IGFycj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXItaW5kLScraWQpOwogICAgaWYoYm9keSl7Ym9keS5jbGFzc0xpc3QudG9nZ2xlKCdvcGVuJywhYW55T3Blbik7aWYoYXJyKWFyci50ZXh0Q29udGVudD1hbnlPcGVuPyfilrYnOifilrwnO30KICB9KTsKICBpZihidG4pYnRuLnRleHRDb250ZW50PWFueU9wZW4/JysgRXhwYW5kaXIgVG9kb3MnOifiiJIgUmVjb2xoZXIgVG9kb3MnOwp9CmFzeW5jIGZ1bmN0aW9uIGZITCgpewogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnfSl9KTsKICAgIGlmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgY29uc3QgYnA9cGFyc2VGbG9hdChkLkJUQ3x8MCk7CiAgICBpZihicD4wKXtFKCdidGMtcCcsZlUoYnApKTtDaCgnYnRjLWMnLGJwLGJwKjAuOTksJ3UnKTt9CiAgICB0cnl7CiAgICAgIGNvbnN0IHIyPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJyxkZXg6J3h5eid9KX0pOwogICAgICBpZihyMi5vayl7Y29uc3QgZDI9YXdhaXQgcjIuanNvbigpOwogICAgICAgIGlmKGQyWyd4eXo6Q0wnXSlFKCdjbC1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OkNMJ10pLnRvRml4ZWQoMikpOwogICAgICAgIGlmKGQyWyd4eXo6R09MRCddKUUoJ2dvbGQtcCcsJyQnK051bWJlcihkMlsneHl6OkdPTEQnXSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7CiAgICAgICAgaWYoZDJbJ3h5ejpTSUxWRVInXSlFKCdzaWx2ZXItcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpTSUxWRVInXSkudG9GaXhlZCgyKSk7CiAgICAgICAgaWYoZDJbJ3h5ejpDT1BQRVInXSlFKCdjb3BwZXItcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDT1BQRVInXSkudG9GaXhlZCgzKSk7fQogICAgfWNhdGNoKGUpe30KICB9Y2F0Y2goZSl7fQp9CmFzeW5jIGZ1bmN0aW9uIGZUVigpewogIGNvbnN0IG91dD17fTsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy90di9icmF6aWwnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6WydCTUZCT1ZFU1BBOlBFVFI0JywnQk1GQk9WRVNQQTpJVFVCNCcsJ0JNRkJPVkVTUEE6VkFMRTMnLCdCTUZCT1ZFU1BBOkJCREM0JywnQk1GQk9WRVNQQTpBQkVWMycsJ0JNRkJPVkVTUEE6QkJBUzMnLCdCTUZCT1ZFU1BBOldFR0UzJywnQk1GQk9WRVNQQTpJQk9WJ119LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7CiAgICBpZihyLm9rKXtjb25zdCBkPWF3YWl0IHIuanNvbigpOyhkLmRhdGF8fFtdKS5mb3JFYWNoKHg9Pntjb25zdFtjLGNhXT14LmR8fFtdO2lmKGMhPW51bGwpb3V0W3guc109e3A6Yyx2OmMtKGNhfHwwKX07fSk7fQogIH1jYXRjaChlKXt9CiAgdHJ5e2NvbnN0IHJyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKHJyLm9rKXtjb25zdCBkZD1hd2FpdCByci5qc29uKCk7aWYoZGQucHJlY29fYXR1YWwpe0UoJ3JveG8zNHEtcCcsZlIoZGQucHJlY29fYXR1YWwpKTtDaCgncm94bzM0cS1jJyxkZC5wcmVjb19hdHVhbCwoZGQucHJlY29fYW50ZXJpb3J8fGRkLnByZWNvX2F0dWFsKjAuOTkpLCdyJyk7fX19Y2F0Y2goZSl7fQogIHJldHVybiBvdXQ7Cn0KYXN5bmMgZnVuY3Rpb24gZkZ1dCgpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9mdXR1cmVzJyk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmRnVuZCgpewogIHRyeXtjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2ZhcGkuYmluYW5jZS5jb20vZmFwaS92MS9wcmVtaXVtSW5kZXg/c3ltYm9sPUJUQ1VTRFQnKTtpZihyLm9rKXtjb25zdCBkPWF3YWl0IHIuanNvbigpO0UoJ2J0Yy1mdW5kJywocGFyc2VGbG9hdChkLmxhc3RGdW5kaW5nUmF0ZXx8MCkqMTAwKS50b0ZpeGVkKDQpKyclJyk7cmV0dXJuO319Y2F0Y2goZSl7fQogIHRyeXtjb25zdCByMj1hd2FpdCBmZXRjaChCKycvYmluYW5jZS9mdW5kaW5nJyk7aWYoIXIyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIyLmpzb24oKTtpZihkLmxhc3RGdW5kaW5nUmF0ZSlFKCdidGMtZnVuZCcsKHBhcnNlRmxvYXQoZC5sYXN0RnVuZGluZ1JhdGUpKjEwMCkudG9GaXhlZCg0KSsnJScpO31jYXRjaChlKXt9Cn0KZnVuY3Rpb24gZG9NYWNybyh0dixmdCl7CiAgW1snUEVUUjQnLCdwZXRyNHEnXSxbJ0lUVUI0JywnaXR1YjRxJ10sWydWQUxFMycsJ3ZhbGUzcSddLFsnQkJEQzQnLCdiYmRjNHEnXSxbJ0FCRVYzJywnYWJldjNxJ10sWydCQkFTMycsJ2JiYXMzcSddLFsnV0VHRTMnLCd3ZWdlM3EnXV0uZm9yRWFjaCgoW3QsaWRdKT0+ewogICAgY29uc3QgZD10dlsnQk1GQk9WRVNQQTonK3RdO2lmKGQpe0UoaWQrJy1wJyxmUihkLnApKTtDaFRibChpZCsnLXYnLGlkKyctYycsZC5wLGQudiwncicpO30KICB9KTsKICBjb25zdCBpYj10dlsnQk1GQk9WRVNQQTpJQk9WJ107aWYoaWIpe0UoJ2lib3YtcCcsZlAoaWIucCkpO0NoVGJsKCdpYm92LXYnLCdpYm92LWMnLGliLnAsaWIudiwncCcpO30KICBpZihmdCl7CiAgICBjb25zdCBhZj0oaWQsdik9Pntjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZihlKXtlLnRleHRDb250ZW50PXY7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fX07CiAgICBpZihmdC5kamk/LnByaWNlKXthZignZGppLXAnLGZQKGZ0LmRqaS5wcmljZSkpO0NoVGJsKCdkamktdicsJ2RqaS1jJyxmdC5kamkucHJpY2UsZnQuZGppLnByZXYsJ3AnKTt9CiAgICBpZihmdC5lc2Y/LnByaWNlKXthZignZXNmLXAnLGZQKGZ0LmVzZi5wcmljZSkpO0NoVGJsKCdlc2YtdicsJ2VzZi1jJyxmdC5lc2YucHJpY2UsZnQuZXNmLnByZXYsJ3AnKTt9CiAgICBpZihmdC5ucWY/LnByaWNlKXthZignbnFmLXAnLGZQKGZ0Lm5xZi5wcmljZSkpO0NoVGJsKCducWYtdicsJ25xZi1jJyxmdC5ucWYucHJpY2UsZnQubnFmLnByZXYsJ3AnKTt9CiAgICBpZihmdC53aW4/LnByaWNlKXthZignd2luLXAnLGZQKGZ0Lndpbi5wcmljZSkpO0NoVGJsKCd3aW4tdicsJ3dpbi1jJyxmdC53aW4ucHJpY2UsZnQud2luLnByZXYsJ3AnKTt9CiAgICBpZihmdC52aXg/LnByaWNlKXthZigndml4LXAnLE51bWJlcihmdC52aXgucHJpY2UpLnRvRml4ZWQoMikpO0NoVGJsKCd2aXgtdicsJ3ZpeC1jJyxmdC52aXgucHJpY2UsZnQudml4LnByZXYsJ3UnKTt9CiAgICBpZihmdC5keHk/LnByaWNlKXthZignZHh5LXAnLE51bWJlcihmdC5keHkucHJpY2UpLnRvRml4ZWQoMikpO0NoVGJsKCdkeHktdicsJ2R4eS1jJyxmdC5keHkucHJpY2UsZnQuZHh5LnByZXYsJ3UnKTt9CiAgICBpZihmdC51c2Q/LnByaWNlKXthZigndXNkLXAnLGZSKGZ0LnVzZC5wcmljZSkpO0NoVGJsKCd1c2QtdicsJ3VzZC1jJyxmdC51c2QucHJpY2UsZnQudXNkLnByZXZ8fGZ0LnVzZC5wcmljZSwncicpO30KICB9Cn0KZnVuY3Rpb24gZG9Qb3ModHYpewogIGNvbnN0IHB0PXR2WydCTUZCT1ZFU1BBOlBFVFI0J107Y29uc3QgcHA9cHQ/LnB8fDQwLHB2PXB0Py52fHw0MDsKICBFKCdwdC1wJyxmUihwcCkpO0NoKCdwdC1jJyxwcCxwdiwncicpOwogIGNvbnN0IHBkPXBwLTMwLjg1O0UoJ3B0LWl0bScsKHBkPj0wPycrIFIkICc6Jy0gUiQgJykrTWF0aC5hYnMocGQpLnRvRml4ZWQoMikrJyAnKyhwZD49MD8nYWNpbWEnOidhYmFpeG8nKSsnIGRvIHN0cmlrZScpOwogIGNvbnN0IHZsPXR2WydCTUZCT1ZFU1BBOlZBTEUzJ107Y29uc3QgdnA9dmw/LnB8fDc4LHZ2PXZsPy52fHw3ODsKICBFKCd2bC1wJyxmUih2cCkpO0NoKCd2bC1jJyx2cCx2diwncicpOwogIGNvbnN0IHZkPXZwLTU3LjQwO0UoJ3ZsLWl0bScsKHZkPj0wPycrIFIkICc6Jy0gUiQgJykrTWF0aC5hYnModmQpLnRvRml4ZWQoMikrJyAnKyh2ZD49MD8nYWNpbWEnOidhYmFpeG8nKSsnIGRvIHN0cmlrZScpOwogIGNvbnN0IGNkPShkcyxlaWQpPT57Y29uc3Qgdj1uZXcgRGF0ZShkcyksZD1NYXRoLm1heCgwLE1hdGguY2VpbCgodi1uZXcgRGF0ZSgpKS84NjRlNSkpLGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoZWlkKTtpZihlKWUudGV4dENvbnRlbnQ9ZDt9OwogIGNkKCcyMDI2LTEyLTE3JywncHQtZGlhcycpO2NkKCcyMDI3LTAyLTE4JywndmwtZGlhcycpO2NkKCcyMDI2LTA5LTE0JywnYTMtZGlhcycpO2NkKCcyMDI2LTEwLTAyJywnYTNiLWRpYXMnKTtjZCgnMjAyNi0wNy0xNicsJ3J4LWRpYXMnKTsKICBzZXRUaW1lb3V0KGFzeW5jKCk9PnsKICAgIHRyeXtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzL0FYSUEzLlNBJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJlY29fYXR1YWwpcmV0dXJuOwogICAgICBjb25zdCBwPWQucHJlY29fYXR1YWw7RSgnYTMtcCcsZlIocCkpO0UoJ2EzYi1wJyxmUihwKSk7CiAgICAgIGNvbnN0IGtBPTQzLjUxLGt1QT02OC43NixrQj00MC41MixrdUI9NjIuODE7CiAgICAgIGNvbnN0IGRBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhMy1rZG8nKTtpZihkQSlkQS50ZXh0Q29udGVudD0oKHAta0EpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7CiAgICAgIGNvbnN0IHVBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhMy1rdW8nKTtpZih1QSl1QS50ZXh0Q29udGVudD0oKGt1QS1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJzsKICAgICAgY29uc3Qgc0E9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzLXN0Jyk7aWYoc0Epe3NBLnRleHRDb250ZW50PXA8PWtBPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VBPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQS5jbGFzc05hbWU9J3N2ICcrKHA8PWtBfHxwPj1rdUE/J3dhcm4nOidvaycpO30KICAgICAgY29uc3QgZEI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzYi1rZG8nKTtpZihkQilkQi50ZXh0Q29udGVudD0oKHAta0IpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7CiAgICAgIGNvbnN0IHVCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhM2Ita3VvJyk7aWYodUIpdUIudGV4dENvbnRlbnQ9KChrdUItcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7CiAgICAgIGNvbnN0IHNCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhM2Itc3QnKTtpZihzQil7c0IudGV4dENvbnRlbnQ9cDw9a0I/J/CflLQgS0RPIEFUSU5HSURPJzpwPj1rdUI/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NCLmNsYXNzTmFtZT0nc3YgJysocDw9a0J8fHA+PWt1Qj8nd2Fybic6J29rJyk7fQogICAgfWNhdGNoKGUpe30KICB9LDIwMDApOwogIHNldFRpbWVvdXQoYXN5bmMoKT0+ewogICAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJlY29fYXR1YWwpcmV0dXJuOwogICAgICBjb25zdCBwPWQucHJlY29fYXR1YWw7RSgncngtcCcsZlIocCkpOwogICAgICBjb25zdCBpdG09ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LWl0bScpOwogICAgICBjb25zdCBkaXN0PXAtMTAuNTA7CiAgICAgIGlmKGl0bSlpdG0udGV4dENvbnRlbnQ9KGRpc3Q+PTA/JysgUiQgJzonLSBSJCAnKStNYXRoLmFicyhkaXN0KS50b0ZpeGVkKDIpKycgJysoZGlzdD49MD8nYWNpbWEgKElUTSDimqApJzonYWJhaXhvIChPVE0g4pyFKScpKycgZG8gc3RyaWtlJzsKICAgICAgY29uc3QgZGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LWtkbycpO2lmKGRlKWRlLnRleHRDb250ZW50PSgocC0xMC41MCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgZG8gc3RyaWtlJzsKICAgICAgY29uc3Qgc2U9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LXN0Jyk7aWYoc2Upe3NlLnRleHRDb250ZW50PXA8PTEwLjUwPyfinIUgT1RNIOKAlCBhYmFpeG8gZG8gc3RyaWtlJzon4pqgIElUTSDigJQgYWNpbWEgZG8gc3RyaWtlJztzZS5jbGFzc05hbWU9J3N2ICcrKHA8PTEwLjUwPydvayc6J2l0bScpO30KICAgIH1jYXRjaChlKXt9CiAgfSwzMDAwKTsKfQphc3luYyBmdW5jdGlvbiBNQyh0ayxzayxkaWFzLGxJZCxySWQsc0lkLHZJZCxpSWQscnRJZCl7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcjp0ayxrX2NhbGw6c2ssa19wdXQ6c2ssdF9kYXlzOmRpYXMsbjo1MDAwfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxJZCkuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocklkKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBjb25zdCBwcm9iPU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYXx8MCk7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoc0lkKTtzRWwudGV4dENvbnRlbnQ9cHJvYi50b0ZpeGVkKDEpKyclJzsKICAgIHNFbC5jbGFzc05hbWU9J2l2ICcrKHByb2I8MTU/J29rJzpwcm9iPDMwPyd3YXJuJzonZG93bicpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodklkKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlJZCkudGV4dENvbnRlbnQ9J1ZvbC5oaXN0LiAnK2Qudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUgwrcgJysocHJvYjwxNT8n4pyFIFJpc2NvIGJhaXhvIGRlIGV4ZXJjw61jaW8nOifimqAgTW9uaXRvcmFyIHBvc2nDp8OjbycpOwogICAgaWYocnRJZClFKHJ0SWQscHJvYi50b0ZpeGVkKDEpKyclJyk7CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxJZCk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gTUNCKHRrLGVuLGtkLGt1LGRpYXMscGZ4KXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvbW9udGVjYXJsby9iYXJyaWVyJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXI6dGssZW50cnk6ZW4sa2RvOmtkLGt1bzprdSx0X2RheXM6ZGlhcyxuOjMwMDB9KX0pOwogICAgaWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtbCcpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLXInKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1uYicpLnRleHRDb250ZW50PWQucHJvYl9zZW1fYmFycmVpcmEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1rdScpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9hbHRhLnRvRml4ZWQoMSkrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMta2QnKS50ZXh0Q29udGVudD1kLnByb2JfYmFycmVpcmFfYmFpeGEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy12bycpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtaScpLnRleHRDb250ZW50PSdSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtkbysnIMK3IEtVTyBSJCAnK2Qua3VvOwogIH1jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1sJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gTUNSKHRrLGVuLGtkLGRpYXMpewogIHRyeXsKICAgIGNvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXI6dGssa19jYWxsOmVuLGtfcHV0OmVuLHRfZGF5czpkaWFzLGtub2NrX2Rvd246a2Qsbjo1MDAwfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1sJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXInKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXMnKTtzRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9zdWNlc3NvKS50b0ZpeGVkKDEpKyclJztzRWwuY2xhc3NOYW1lPSdpdiAnKyhkLnByb2Jfc3VjZXNzbz43MD8nb2snOmQucHJvYl9zdWNlc3NvPjUwPyd3YXJuJzonZG93bicpOwogICAgY29uc3QgY0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1jJyk7aWYoY0VsKWNFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX2NhbGxfZXhlcmNpZGEpLnRvRml4ZWQoMSkrJyUnOwogICAgY29uc3Qga0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1rJyk7aWYoa0VsKWtFbC50ZXh0Q29udGVudD1kLnByb2Jfa2RvX2F0aW5naWRvIT1udWxsP051bWJlcihkLnByb2Jfa2RvX2F0aW5naWRvKS50b0ZpeGVkKDEpKyclJzon4oCUJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy12JykudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtaScpLnRleHRDb250ZW50PSdSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtub2NrX2Rvd247CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1sJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gZkluZCh0ayl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwzMDAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy8nK3RrLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZCVENJKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvYnRjL2luZGljYXRvcnMnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZCVENDKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvYnRjL2N5Y2xlJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmRkcoKXsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9mZWFyZ3JlZWQnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IHY9ZC52YWx1ZXx8NTAsY2xzPXY8PTI1Pyd2YXIoLS1yZWQpJzp2PD00NT8ndmFyKC0td2FybiknOnY8PTc1Pyd2YXIoLS1hY2NlbnQpJzondmFyKC0tZ3JlZW4pJzsKICAgIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmZy1hcmVhJyk7CiAgICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxNnB4Ij48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo4cHg7Zm9udC13ZWlnaHQ6NjAwO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4Ij7wn5ixIEZlYXIgJiBHcmVlZCBJbmRleDwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjE0cHgiPjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTozOHB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjonK2NscysnIj4nK3YrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjonK2NscysnIj4nKyhkLnZhbHVlX2NsYXNzaWZpY2F0aW9ufHwnTmV1dHJvJykrJzwvZGl2PjwvZGl2PjwvZGl2Pic7CiAgICBFKCdmZy12YWwnLFN0cmluZyh2KSk7RSgnZmctbGJsJyxkLnZhbHVlX2NsYXNzaWZpY2F0aW9ufHwnTmV1dHJvJyk7CiAgICB0cnl7Y29uc3QgcmI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnfSl9KTtpZihyYi5vayl7Y29uc3QgZGI9YXdhaXQgcmIuanNvbigpO2NvbnN0IGJwPXBhcnNlRmxvYXQoZGIuQlRDfHwwKTtpZihicD4wKXtFKCdidGMtaW5kLXAnLCckJytOdW1iZXIoYnApLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpO0UoJ2J0Yy1wJyxmVShicCkpO319fWNhdGNoKGUyKXt9CiAgfWNhdGNoKGUpe30KfQpmdW5jdGlvbiBybmRJbmQoaWQsZGF0YSl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQrJy1pbmQnKTtpZighZWwpcmV0dXJuOwogIGlmKCFkYXRhKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXdhcm4pO3BhZGRpbmc6MTJweDtmb250LXNpemU6MTNweCI+4o+zIFNlbSByZXNwb3N0YSDigJQgY2xpcXVlIOKGuzwvZGl2Pic7cmV0dXJuO30KICBpZihkYXRhLmVycm9yKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXJlZCk7cGFkZGluZzoxMnB4O2ZvbnQtc2l6ZToxM3B4Ij7imqAgJytkYXRhLmVycm9yKyc8L2Rpdj4nO3JldHVybjt9CiAgY29uc3QgaW5kcz1kYXRhLmluZGljYWRvcmVzfHxbXSxzYz1OdW1iZXIoZGF0YS5zY29yZV90b3RhbHx8MCkscHJlY289ZGF0YS5wcmVjb19hdHVhbCxncmFoYW09ZGF0YS5ncmFoYW1fdmFsdWUsdXA9ZGF0YS51cHNpZGVfZ3JhaGFtLHNldG9yPWRhdGEuc2V0b3J8fCcnOwogIGNvbnN0IHNjMj1zYz49NjU/J3ZhcigtLWdyZWVuKSc6c2M+PTQwPyd2YXIoLS13YXJuKSc6J3ZhcigtLXJlZCknLHNsPXNjPj02NT8nQ29tcHJhIOKWsic6c2M+PTQwPydOZXV0cm8g4oaSJzonVmVuZGEg4pa8JzsKICBsZXQgaD0nPGRpdiBjbGFzcz0ic2NiIj4nKwogICAgJzxkaXYgY2xhc3M9InNjYyI+PGRpdiBjbGFzcz0ic2NtIj5TY29yZTwvZGl2PjxkaXYgY2xhc3M9InNjbiIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2MrJzwvZGl2PjxkaXYgY2xhc3M9InNjbCIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2wrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0ic2NjIj48ZGl2IGNsYXNzPSJzY20iPkNvdGHDp8OjbzwvZGl2PjxkaXYgY2xhc3M9InNjdiI+JysocHJlY28/J1IkICcrTnVtYmVyKHByZWNvKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NzIj4nK3NldG9yKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjYyI+PGRpdiBjbGFzcz0ic2NtIj5HcmFoYW0gVko8L2Rpdj48ZGl2IGNsYXNzPSJzY3YiIHN0eWxlPSJjb2xvcjonKyh1cCYmdXA+MD8ndmFyKC0tZ3JlZW4pJzondmFyKC0tcmVkKScpKyciPicrKGdyYWhhbT8nUiQgJytOdW1iZXIoZ3JhaGFtKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NzIiBzdHlsZT0iY29sb3I6JysodXAmJnVwPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cCE9bnVsbD8odXA+MD8nKyc6JycpK3VwKyclIHVwc2lkZSc6J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzwvZGl2Pic7CiAgaW5kcy5mb3JFYWNoKGk9PnsKICAgIGNvbnN0IHM9aS5zaW5hbHx8JycsY2xzPXM9PT0nQWx0YSd8fHM9PT0nU29icmV2ZW5kYSc/J29rJzpzPT09J0JhaXhhJ3x8cz09PSdTb2JyZWNvbXByYSc/J2Rvd24nOid3YXJuJyxhcj1jbHM9PT0nb2snPyfilrInOmNscz09PSdkb3duJz8n4pa8Jzon4oaSJzsKICAgIGgrPSc8ZGl2IGNsYXNzPSJpciI+PGRpdiBjbGFzcz0iaXJ0Ij48c3BhbiBjbGFzcz0iaXJuIj4nKyhpLm5vbWV8fCcnKSsnPC9zcGFuPjxzcGFuIGNsYXNzPSJpcnYgJytjbHMrJyI+JysoaS52YWxvciE9bnVsbD9pLnZhbG9yOifigJQnKSsnICcrYXIrJzwvc3Bhbj48L2Rpdj4nKyhpLmV4cGxpY2FjYW8/JzxkaXYgY2xhc3M9ImlyZSI+JytpLmV4cGxpY2FjYW8rJzwvZGl2Pic6JycpKyc8L2Rpdj4nOwogIH0pOwogIGVsLmlubmVySFRNTD1ofHwnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTBweCI+U2VtIGluZGljYWRvcmVzPC9kaXY+JzsKfQpmdW5jdGlvbiBybmRCVENJKGQpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidGMtaW5kLWFyZWEnKTtpZighZWx8fCFkKXJldHVybjsKICBpZihkLmVycm9yKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXdhcm4pO3BhZGRpbmc6MTJweDtmb250LXNpemU6MTNweCI+4o+zICcrZC5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGxldCBoPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweCI+JzsKICBpZihkLnJzaV9zZW1hbmFsIT1udWxsKXtjb25zdCBydj1kLnJzaV9zZW1hbmFsLHJjPXJ2PDMwPydvayc6cnY+NzA/J2Rvd24nOid3YXJuJztoKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5SU0kgU2VtYW5hbDwvZGl2PjxkaXYgY2xhc3M9Iml2ICcrcmMrJyI+Jytydi50b0ZpeGVkKDEpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrKHJ2PDMwPydTb2JyZXZlbmRhIOKaoSc6cnY+NzA/J1NvYnJlY29tcHJhIOKaoCc6J05ldXRybycpKyc8L2Rpdj48L2Rpdj4nO0UoJ2J0Yy1yc2knLHJ2LnRvRml4ZWQoMSkpO30KICBpZihkLm1tNTBfc2VtYW5hbCloKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NTSA1MCBzZW0uPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JCcrTnVtYmVyKGQubW01MF9zZW1hbmFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nOwogIGlmKGQubW0yMDBfc2VtYW5hbCloKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NTSAyMDAgc2VtLjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPiQnK051bWJlcihkLm1tMjAwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZC5tYWNkX2hpc3RvZ3JhbSE9bnVsbCl7Y29uc3QgbWg9ZC5tYWNkX2hpc3RvZ3JhbTtoKz0nPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NQUNEIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgJysobWg+MD8nb2snOidkb3duJykrJyI+JytOdW1iZXIobWgpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JysobWg+MD8nTW9tZW50dW0g4payJzonTW9tZW50dW0g4pa8JykrJzwvZGl2PjwvZGl2Pic7fQogIGlmKGQub2J2X3RyZW5kKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk9CVjwvZGl2PjxkaXYgY2xhc3M9Iml2ICcrKGQub2J2X3RyZW5kPT09J3N1YmluZG8nPydvayc6J2Rvd24nKSsnIj4nK2Qub2J2X3RyZW5kKyc8L2Rpdj48L2Rpdj4nOwogIGgrPSc8L2Rpdj4nO2VsLmlubmVySFRNTD1oOwogIGlmKGQucHJpY2UpRSgnYnRjLWluZC1wJywnJCcrTnVtYmVyKGQucHJpY2UpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpOwp9CmZ1bmN0aW9uIHJuZEJUQ0MoZCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1jeWNsZS1hcmVhJyk7aWYoIWVsfHwhZHx8ZC5lcnJvcilyZXR1cm47CiAgY29uc3QgZlUyPXY9PnY/JyQnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwogIGVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLWJvdHRvbToxMHB4Ij4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+TVZSViBaLVNjb3JlPC9kaXY+PGRpdiBjbGFzcz0iaXYgJysoZC5tdnJ2X3pzY29yZT8udmFsdWU8MT8nb2snOmQubXZydl96c2NvcmU/LnZhbHVlPDM/J3dhcm4nOidkb3duJykrJyI+JytkLm12cnZfenNjb3JlPy52YWx1ZSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nK2QubXZydl96c2NvcmU/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+TlVQTDwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrKChkLm51cGw/LnZhbHVlfHwwKSoxMDApLnRvRml4ZWQoMCkrJyU8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5udXBsPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlB1ZWxsIE11bHRpcGxlPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JytkLnB1ZWxsPy52YWx1ZSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nK2QucHVlbGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+MjAwVyBNQTwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrZlUyKGQubWEyMDB3KSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nKyhkLm1hMjAwd19wY3Q/JysnK2QubWEyMDB3X3BjdCsnJSc6JycpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UmFpbmJvdyBCYW5kPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JysoZC5yYWluYm93Py5iYW5kfHwn4oCUJykrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5QaSBDeWNsZSBEaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIj4nK2ZVMihkLnBpX2N5Y2xlPy5kaXN0YW5jZSkrJzwvZGl2PjwvZGl2PicrCiAgICAnPC9kaXY+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEwcHg7Zm9udC1zaXplOjEzcHg7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXdlaWdodDo2MDAiPicrKGQucGlfY3ljbGU/LnNpZ25hbHx8JycpKyc8L2Rpdj4nOwp9CmFzeW5jIGZ1bmN0aW9uIGxvYWRJbmQoKXsKICBjb25zdCB3dD0ocCxtcyxmYik9PlByb21pc2UucmFjZShbcCxuZXcgUHJvbWlzZShyPT5zZXRUaW1lb3V0KCgpPT5yKGZiKSxtcykpXSk7CiAgY29uc3RbYmksYmNdPWF3YWl0IFByb21pc2UuYWxsKFt3dChmQlRDSSgpLDE1MDAwLHtlcnJvcjonVGltZW91dCDigJQgY2xpcXVlIOKGuyd9KSx3dChmQlRDQygpLDE1MDAwLG51bGwpXSk7CiAgcm5kQlRDSShiaSk7cm5kQlRDQyhiYyk7ZkZHKCk7CiAgY29uc3Qgc3RvY2tzPVtbJ1BFVFI0LlNBJywncGV0cjQnXSxbJ1ZBTEUzLlNBJywndmFsZTMnXSxbJ0JCQVMzLlNBJywnYmJhczMnXSxbJ0FYSUEzLlNBJywnYXhpYTMnXSxbJ1JPWE8zNC5TQScsJ3JveG8zNCddXTsKICBjb25zdCByZXM9YXdhaXQgUHJvbWlzZS5hbGwoc3RvY2tzLm1hcCgoW3RdKT0+d3QoZkluZCh0KSwzMDAwMCx7ZXJyb3I6J1RpbWVvdXQgMzBzJ30pKSk7CiAgc3RvY2tzLmZvckVhY2goKFssaWRdLGkpPT5ybmRJbmQoaWQscmVzW2ldKSk7Cn0KYXN5bmMgZnVuY3Rpb24gcmwodGspewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHRrKyctaW5kJyk7CiAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxcyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2Pic7CiAgY29uc3QgbT17cGV0cjQ6J1BFVFI0LlNBJyx2YWxlMzonVkFMRTMuU0EnLGJiYXMzOidCQkFTMy5TQScsYXhpYTM6J0FYSUEzLlNBJyxyb3hvMzQ6J1JPWE8zNC5TQSd9OwogIHJuZEluZCh0ayxhd2FpdCBmSW5kKG1bdGtdKSk7Cn0KY29uc3QgRkxBR1M9eydVU0QnOifwn4e68J+HuCcsJ1VTJzon8J+HuvCfh7gnLCdCUkwnOifwn4en8J+HtycsJ0JSJzon8J+Hp/Cfh7cnLCdFVVInOifwn4eq8J+HuicsJ0VVJzon8J+HqvCfh7onLCdHQlAnOifwn4es8J+HpycsJ0NOWSc6J/Cfh6jwn4ezJywnSlBZJzon8J+Hr/Cfh7UnLCdDQUQnOifwn4eo8J+HpicsJ0FVRCc6J/Cfh6bwn4e6JywnREUnOifwn4ep8J+HqicsJ05aRCc6J/Cfh7Pwn4e/JywnQ0hGJzon8J+HqPCfh60nfTsKYXN5bmMgZnVuY3Rpb24gbG9hZENhbCgpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYWwtYXJlYScpOwogIGNvbnN0IHN0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYWwtc3QnKTsKICBpZighZWwpcmV0dXJuOwogIGVsLmlubmVySFRNTD0nPHAgc3R5bGU9ImNvbG9yOiM4ODg7cGFkZGluZzoyMHB4O3RleHQtYWxpZ246Y2VudGVyIj5DYXJyZWdhbmRvLi4uPC9wPic7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvY2FsZW5kYXInLHtjYWNoZTonbm8tc3RvcmUnfSk7CiAgICBpZighci5vayl0aHJvdyBuZXcgRXJyb3IoJ0hUVFAgJytyLnN0YXR1cyk7CiAgICBjb25zdCBldnM9YXdhaXQgci5qc29uKCk7CiAgICBpZihldnMuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGV2cy5lcnJvcik7CiAgICBpZihzdClzdC50ZXh0Q29udGVudD1ldnMubGVuZ3RoKycgZXZlbnRvcyc7CiAgICBpZighZXZzLmxlbmd0aCl7ZWwuaW5uZXJIVE1MPSc8cCBzdHlsZT0iY29sb3I6Izg4ODtwYWRkaW5nOjIwcHg7dGV4dC1hbGlnbjpjZW50ZXIiPlNlbSBldmVudG9zPC9wPic7cmV0dXJuO30KICAgIGNvbnN0IGJ5RD17fTsKICAgIGV2cy5mb3JFYWNoKGU9PnsKICAgICAgY29uc3QgZHQ9KGUuZGF0ZXx8JycpLnNsaWNlKDAsMTApOwogICAgICBpZighYnlEW2R0XSlieURbZHRdPVtdOwogICAgICBieURbZHRdLnB1c2goZSk7CiAgICB9KTsKICAgIGxldCBoPSc8ZGl2IHN0eWxlPSJmb250LWZhbWlseTptb25vc3BhY2UiPic7CiAgICBPYmplY3Qua2V5cyhieUQpLnNvcnQoKS5mb3JFYWNoKGR0PT57CiAgICAgIGNvbnN0IGQ9bmV3IERhdGUoZHQrJ1QxMjowMDowMCcpOwogICAgICBjb25zdCBsYmw9ZC50b0xvY2FsZURhdGVTdHJpbmcoJ3B0LUJSJyx7d2Vla2RheTonbG9uZycsZGF5OicyLWRpZ2l0Jyxtb250aDonc2hvcnQnfSk7CiAgICAgIGgrPSc8ZGl2IHN0eWxlPSJtYXJnaW4tYm90dG9tOjIwcHgiPic7CiAgICAgIGgrPSc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOiMxYTFhMjQ7cGFkZGluZzo4cHggMTRweDtmb250LXNpemU6MTFweDtmb250LXdlaWdodDo3MDA7Y29sb3I6IzdjNmFmNzt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2JvcmRlci1sZWZ0OjNweCBzb2xpZCAjN2M2YWY3Ij4nK2xibCsnPC9kaXY+JzsKICAgICAgYnlEW2R0XS5mb3JFYWNoKGU9PnsKICAgICAgICBjb25zdCBpbXBfY29sb3I9ZS5pbXBvcnRhbmNlPj0zPycjZmY0NDQ0JzonI2ZmOTgwMCc7CiAgICAgICAgY29uc3QgYWN0X2NvbG9yPWUuc2lnbmFsPT09J2JlYXQnPycjMDBlNjc2JzplLnNpZ25hbD09PSdtaXNzJz8nI2YwNjI5Mic6JyNhYWEnOwogICAgICAgIGgrPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjMwcHggNTVweCAxZnIgNDBweCA4MHB4IDgwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhO2ZvbnQtc2l6ZToxM3B4Ij4nOwogICAgICAgIGgrPSc8c3BhbiBzdHlsZT0iZm9udC1zaXplOjE2cHgiPicrKGUuZmxhZ3x8J/CfjJAnKSsnPC9zcGFuPic7CiAgICAgICAgaCs9JzxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4nKyhlLnRpbWV8fCfigJQnKSsnPC9zcGFuPic7CiAgICAgICAgaCs9JzxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCIgdGl0bGU9IicrZS5ldmVudCsnIj4nK2UuZXZlbnQrJzwvc3Bhbj4nOwogICAgICAgIGgrPSc8c3BhbiBzdHlsZT0iY29sb3I6JytpbXBfY29sb3IrJzt0ZXh0LWFsaWduOmNlbnRlciI+Jysn4pePJy5yZXBlYXQoTWF0aC5taW4oZS5pbXBvcnRhbmNlLDMpKSsnPC9zcGFuPic7CiAgICAgICAgaCs9JzxzcGFuIHN0eWxlPSJjb2xvcjonK2FjdF9jb2xvcisnO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwIj4nKyhlLmFjdHVhbHx8J+KAlCcpKyc8L3NwYW4+JzsKICAgICAgICBoKz0nPHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+JysoZS5mb3JlY2FzdHx8J+KAlCcpKyc8L3NwYW4+JzsKICAgICAgICBoKz0nPC9kaXY+JzsKICAgICAgfSk7CiAgICAgIGgrPSc8L2Rpdj4nOwogICAgfSk7CiAgICBoKz0nPC9kaXY+JzsKICAgIGVsLmlubmVySFRNTD1oOwogIH1jYXRjaChlKXsKICAgIGVsLmlubmVySFRNTD0nPHAgc3R5bGU9ImNvbG9yOiNmMDYyOTI7cGFkZGluZzoyMHB4Ij5FcnJvOiAnK2UubWVzc2FnZSsnPC9wPic7CiAgfQp9Cgphc3luYyBmdW5jdGlvbiBtYWluKCl7CiAgdHJ5ewogICAgY29uc3RbLHR2LGZ0XT1hd2FpdCBQcm9taXNlLmFsbChbZkhMKCksZlRWKCksZkZ1dCgpXSk7CiAgICBjb25zdCBub3c9bmV3IERhdGUoKS50b0xvY2FsZVRpbWVTdHJpbmcoJ3B0LUJSJyk7CiAgICBFKCdsYXN0LXVwZGF0ZScsJ+KGuyAnK25vdyk7RSgnbGFzdC11cGRhdGUtdGJsJyxub3cpO0UoJ2Zvb3Rlci10aW1lJyxub3cpOwogICAgd2luZG93Ll9sYXN0VFY9dHY7ZG9NYWNybyh0dixmdCk7ZG9Qb3ModHYpOwogICAgc2V0VGltZW91dChmRnVuZCwzMDAwKTsKICAgIHNldFRpbWVvdXQoYXN5bmMoKT0+e3RyeXtjb25zdFtiaSxiY109YXdhaXQgUHJvbWlzZS5hbGwoW2ZCVENJKCksZkJUQ0MoKV0pO2lmKGJpKXJuZEJUQ0koYmkpO2lmKGJjKXJuZEJUQ0MoYmMpO2ZGRygpO31jYXRjaChlKXt9fSw1MDAwKTsKICAgIGNvbnN0IGhvamU9bmV3IERhdGUoKTsKICAgIGNvbnN0IGRQPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0xMi0xNycpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkVj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjctMDItMTgnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZEE9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTA5LTE0JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRBYj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMTAtMDInKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZFI9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTA3LTE2JyktaG9qZSkvODY0ZTUpKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DKCdQRVRSNC5TQScsMzAuODUsZFAsJ3B0LW1jLWwnLCdwdC1tYy1yJywncHQtbWMtcycsJ3B0LW1jLXYnLCdwdC1tYy1pJywncHQtbWMtcnQnKSw2MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DKCdWQUxFMy5TQScsNTcuNDAsZFYsJ3ZsLW1jLWwnLCd2bC1tYy1yJywndmwtbWMtcycsJ3ZsLW1jLXYnLCd2bC1tYy1pJywndmwtbWMtcnQnKSwxMjAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQ0IoJ0FYSUEzLlNBJyw1NC4zMSw0My41MSw2OC43NixkQSwnYTMnKSwxODAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQ0IoJ0FYSUEzLlNBJyw1MC42NSw0MC41Miw2Mi44MSxkQWIsJ2EzYicpLDI0MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DUignUk9YTzM0LlNBJywxMi44OCwxMC41MCxkUiksMzAwMDApOwogICAgY29uc3QgZEJCPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0wOC0yMCcpLWhvamUpLzg2NGU1KSk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQygnQkJBUzMuU0EnLDIxLjY1LGRCQiwnYmItbWMtbCcsJ2JiLW1jLXInLCdiYi1tYy1zJywnYmItbWMtdicsJ2JiLW1jLWknLCdiYi1tYy1ydCcpLDM2MDAwKTsKICAgIC8vIEJCQVMzIGNvdGHDp8OjbyDigJQgdmlhIFRWIG91IGZhbGxiYWNrIC9pbmRpY2F0b3JzCiAgICBjb25zdCBiYlRWPXR2WydCTUZCT1ZFU1BBOkJCQVMzJ107CiAgICBpZihiYlRWPy5wKXsKICAgICAgRSgnYmItcCcsZlIoYmJUVi5wKSk7Q2goJ2JiLWMnLGJiVFYucCxiYlRWLnZ8fGJiVFYucCwncicpOwogICAgICBjb25zdCBkMj1iYlRWLnAtMjEuNjU7CiAgICAgIGNvbnN0IGl0bTI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JiLWl0bScpOwogICAgICBpZihpdG0yKXtpdG0yLnRleHRDb250ZW50PShkMj49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKGQyKS50b0ZpeGVkKDIpKycgJysoZDI+PTA/J2FjaW1hIChJVE0g4pqgKSc6J2FiYWl4byAoT1RNIOKchSknKSsnIGRvIHN0cmlrZSc7aXRtMi5jbGFzc05hbWU9J3N2ICcrKGQyPj0wPydpdG0nOidvaycpO30KICAgIH0gZWxzZSB7CiAgICAgIC8vIFRWIG7Do28gcmV0b3Jub3UgQkJBUzMg4oCUIGZhbGxiYWNrCiAgICAgIGZldGNoKEIrJy9pbmRpY2F0b3JzL0JCQVMzLlNBJykudGhlbihyMj0+cjIuanNvbigpKS50aGVuKGQyPT57CiAgICAgICAgaWYoZDIucHJlY29fYXR1YWwpewogICAgICAgICAgRSgnYmItcCcsZlIoZDIucHJlY29fYXR1YWwpKTtDaCgnYmItYycsZDIucHJlY29fYXR1YWwsZDIucHJlY29fYW50ZXJpb3J8fGQyLnByZWNvX2F0dWFsKjAuOTksJ3InKTsKICAgICAgICAgIGNvbnN0IGRpc3Q9ZDIucHJlY29fYXR1YWwtMjEuNjU7CiAgICAgICAgICBjb25zdCBpdG0yPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiYi1pdG0nKTsKICAgICAgICAgIGlmKGl0bTIpe2l0bTIudGV4dENvbnRlbnQ9KGRpc3Q+PTA/JysgUiQgJzonLSBSJCAnKStNYXRoLmFicyhkaXN0KS50b0ZpeGVkKDIpKycgJysoZGlzdD49MD8nYWNpbWEgKElUTSDimqApJzonYWJhaXhvIChPVE0g4pyFKScpKycgZG8gc3RyaWtlJztpdG0yLmNsYXNzTmFtZT0nc3YgJysoZGlzdD49MD8naXRtJzonb2snKTt9CiAgICAgICAgfQogICAgICB9KS5jYXRjaCgoKT0+e30pOwogICAgfQogICAgY29uc3QgY2RCQj0oKT0+e2NvbnN0IHY9bmV3IERhdGUoJzIwMjYtMDgtMjAnKSxkPU1hdGgubWF4KDAsTWF0aC5jZWlsKCh2LW5ldyBEYXRlKCkpLzg2NGU1KSksZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmItZGlhcycpO2lmKGUpZS50ZXh0Q29udGVudD1kO307Y2RCQigpOwogICAgd2luZG93Ll9JTD1mYWxzZTsKICB9Y2F0Y2goZSl7Y29uc29sZS5lcnJvcihlKTt9Cn0KbWFpbigpO3NldEludGVydmFsKG1haW4sMTIwMDAwKTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPgo=").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
