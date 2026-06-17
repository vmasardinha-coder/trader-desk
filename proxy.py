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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjExLjMg4oCUIERhcmsgUHJlbWl1bSAtLT4KPGh0bWwgbGFuZz0icHQtQlIiPgo8aGVhZD4KPG1ldGEgY2hhcnNldD0iVVRGLTgiPgo8bWV0YSBuYW1lPSJ2aWV3cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MS4wIj4KPHRpdGxlPlRyYWRlciBEZXNrPC90aXRsZT4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JbnRlcjp3Z2h0QDQwMDs1MDA7NjAwOzcwMCZmYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs2MDA7NzAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Cjpyb290ewogIC0tYmc6IzBmMGYxMzstLWJnMjojMTMxMzFhOy0tYmczOiMxYTFhMjQ7CiAgLS10ZXh0OiNlOGU4ZjA7LS1tdXRlZDojNTA1MDY4Oy0tYm9yZGVyOiMxZTFlMmU7CiAgLS1hY2NlbnQ6IzdjNmFmNzstLWFjY2VudDI6IzRmYzNmNzsKICAtLWdyZWVuOiMwMGU2NzY7LS1yZWQ6I2YwNjI5MjstLXdhcm46I2ZmYjc0ZDsKICAtLWdvbGQ6I2YwYTUwMAp9CmJvZHl7CiAgYmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7CiAgZm9udC1mYW1pbHk6J0ludGVyJyxzYW5zLXNlcmlmO2ZvbnQtc2l6ZToxNHB4OwogIGxpbmUtaGVpZ2h0OjEuNTtwYWRkaW5nOjIwcHggMjRweDsKICBtYXgtd2lkdGg6MTEwMHB4O21hcmdpbjowIGF1dG87bWluLWhlaWdodDoxMDB2aAp9CkBtZWRpYShtYXgtd2lkdGg6NjAwcHgpe2JvZHl7cGFkZGluZzoxMnB4fX0KCi8qIOKUgOKUgCBIRUFERVIg4pSA4pSAICovCi5oZHJ7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjIwcHg7cGFkZGluZy1ib3R0b206MTZweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpfQoubG9nb3tmb250LXNpemU6MThweDtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtsZXR0ZXItc3BhY2luZzouNXB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5sb2dvIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50Mil9Ci5oZHItcmlnaHR7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweH0KLmJhZGdle2JhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo0cHggMTJweDtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4fQouaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQoKLyog4pSA4pSAIFRBQlMg4pSA4pSAICovCi50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MjBweDtvdmVyZmxvdy14OmF1dG87cGFkZGluZy1ib3R0b206MnB4fQoudGFie3BhZGRpbmc6OHB4IDE4cHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6MTJweDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3doaXRlLXNwYWNlOm5vd3JhcDtmb250LWZhbWlseTppbmhlcml0O3RyYW5zaXRpb246YWxsIC4xNXN9Ci50YWI6aG92ZXJ7Y29sb3I6dmFyKC0tdGV4dCk7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci50YWIuYWN0aXZle2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtjb2xvcjojZmZmO2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpfQoudGFiLWNvbnRlbnR7ZGlzcGxheTpub25lfS50YWItY29udGVudC5hY3RpdmV7ZGlzcGxheTpibG9ja30KCi8qIOKUgOKUgCBTRUNUSU9OIOKUgOKUgCAqLwouc2Vje2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHggMCA3cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjE0cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4fQouc2VjIC5kb3R7d2lkdGg6NXB4O2hlaWdodDo1cHg7YmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrO2ZsZXgtc2hyaW5rOjB9Ci5zZWMgLmFjY3tjb2xvcjp2YXIoLS1hY2NlbnQpfQoKLyog4pSA4pSAIEdSSUQgQ0FSRFMg4pSA4pSAICovCi5ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDMsMWZyKTtnYXA6MTBweDttYXJnaW4tYm90dG9tOjE4cHh9CkBtZWRpYShtYXgtd2lkdGg6NTAwcHgpey5ncmlke2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoMiwxZnIpfX0KLmNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHggMTRweDtwb3NpdGlvbjpyZWxhdGl2ZTtvdmVyZmxvdzpoaWRkZW47dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1c30KLmNhcmQ6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCl9Ci5jYXJkOjpiZWZvcmV7Y29udGVudDonJztwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MDtsZWZ0OjA7cmlnaHQ6MDtoZWlnaHQ6MnB4fQouY2FyZC5nOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tZ3JlZW4pLCMwMGJjZDQpfQouY2FyZC5iOjpiZWZvcmV7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tYWNjZW50KSx2YXIoLS1hY2NlbnQyKSl9Ci5jYXJkLnc6OmJlZm9yZXtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS13YXJuKSwjZmY5ODAwKX0KLmNhcmQucjo6YmVmb3Jle2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLHZhcigtLXJlZCksI2U5MWU2Myl9Ci5jbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjRweDtmb250LXdlaWdodDo2MDB9Ci5jbntmb250LXNpemU6MTNweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLWJvdHRvbTo4cHg7Y29sb3I6cmdiYSgyNTUsMjU1LDI1NSwuOCl9Ci5jcHtmb250LXNpemU6MjBweDtmb250LXdlaWdodDo3MDA7Y29sb3I6I2ZmZn0KLmNwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToxNXB4fQouY2N7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NTAwfQouY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0uY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjN9fQoKLyog4pSA4pSAIEFDQ09SRElPTiBTRUdNRU5UT1Mg4pSA4pSAICovCi5zaHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweCAxNnB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7Zm9udC1zaXplOjEycHg7Zm9udC13ZWlnaHQ6NjAwO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDt0cmFuc2l0aW9uOmFsbCAuMTVzfQouc2g6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zYjJ7ZGlzcGxheTpub25lO3BhZGRpbmctdG9wOjZweH0KCi8qIOKUgOKUgCBQT1NJw4fDlUVTIOKUgOKUgCAqLwoucGN7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjE4cHg7bWFyZ2luLWJvdHRvbToxMnB4fQoucGx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnB0e2ZvbnQtc2l6ZToyMnB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO21hcmdpbi1ib3R0b206NHB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5wcHtmb250LXNpemU6MjhweDtmb250LXdlaWdodDo3MDB9LnBwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToyMHB4fQoucGMye2ZvbnQtc2l6ZToxMnB4O21hcmdpbi1ib3R0b206MTBweDtmb250LXdlaWdodDo1MDB9Ci5zYntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmctdG9wOjEwcHg7bWFyZ2luLXRvcDoxMHB4fQouc3J7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjVweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEzcHh9Ci5zbHtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NTAwfS5zdnt0ZXh0LWFsaWduOnJpZ2h0O21heC13aWR0aDo1OCU7Zm9udC13ZWlnaHQ6NjAwfQouc3Yub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5zdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zdi5pdG17Y29sb3I6dmFyKC0tcmVkKX0KLnBvcy1hY2N7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTttYXJnaW4tYm90dG9tOjEwcHh9Ci5wb3MtYWNjLWhkcntkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6MTRweCAxOHB4O2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246YmFja2dyb3VuZCAuMTVzfQoucG9zLWFjYy1oZHI6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQoucG9zLWFjYy10a3tmb250LXNpemU6MjJweDtmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlfQoucG9zLWFjYy1zdWJ7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQoucG9zLWFjYy1yaWdodHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxNHB4fQoucG9zLWFjYy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nOjAgMThweCAxNnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcil9Ci5wb3MtYWNjLWJvZHkub3BlbntkaXNwbGF5OmJsb2NrfQouc2lne2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHg7bWFyZ2luLXRvcDoxMHB4O2JhY2tncm91bmQ6dmFyKC0tYmcpfQouc2d0e2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjcwMDtsZXR0ZXItc3BhY2luZzoxcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206OHB4O2NvbG9yOnZhcigtLWFjY2VudDIpfQouaWJ7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEycHg7dGV4dC1hbGlnbjpjZW50ZXJ9Ci5pbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo1cHg7Zm9udC13ZWlnaHQ6NjAwO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4fQouaXZ7Zm9udC1zaXplOjIwcHg7Zm9udC13ZWlnaHQ6ODAwfQouaXYub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5pdi53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5pdi5kb3due2NvbG9yOnZhcigtLXJlZCl9CgovKiDilIDilIAgSU5ESUNBRE9SRVMg4pSA4pSAICovCi5zY2J7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyIDFmcjtnYXA6OHB4O21hcmdpbi1ib3R0b206MTRweH0KLnNjY3tiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTRweCAxMnB4O3RleHQtYWxpZ246Y2VudGVyO3Bvc2l0aW9uOnJlbGF0aXZlO292ZXJmbG93OmhpZGRlbn0KLnNjYzo6YmVmb3Jle2NvbnRlbnQ6Jyc7cG9zaXRpb246YWJzb2x1dGU7dG9wOjA7bGVmdDowO3JpZ2h0OjA7aGVpZ2h0OjJweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS1hY2NlbnQpLHZhcigtLWFjY2VudDIpKX0KLnNjbXtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjVweDtmb250LXdlaWdodDo2MDB9Ci5zY257Zm9udC1zaXplOjMycHg7Zm9udC13ZWlnaHQ6ODAwO2xpbmUtaGVpZ2h0OjF9Ci5zY2x7Zm9udC1zaXplOjExcHg7bWFyZ2luLXRvcDo0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc2N2e2ZvbnQtc2l6ZToyMHB4O2ZvbnQtd2VpZ2h0OjcwMDttYXJnaW4tdG9wOjRweH0KLnNjc3tmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHh9Ci5pcntiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCB0cmFuc3BhcmVudDtwYWRkaW5nOjEwcHggMTRweDttYXJnaW4tYm90dG9tOjRweDt0cmFuc2l0aW9uOmJvcmRlci1sZWZ0LWNvbG9yIC4xc30KLmlyOmhvdmVye2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLWFjY2VudCl9Ci5pcnR7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmJhc2VsaW5lO21hcmdpbi1ib3R0b206M3B4fQouaXJue2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjVweDtmb250LXdlaWdodDo2MDB9Ci5pcnZ7Zm9udC1zaXplOjE1cHg7Zm9udC13ZWlnaHQ6NzAwfQouaXJ2Lm9re2NvbG9yOnZhcigtLWdyZWVuKX0uaXJ2LmRvd257Y29sb3I6dmFyKC0tcmVkKX0uaXJ2Lndhcm57Y29sb3I6dmFyKC0td2Fybil9Ci5pcmV7Zm9udC1zaXplOjEzcHg7Y29sb3I6IzVhNWE4YTtsaW5lLWhlaWdodDoxLjV9CgovKiDilIDilIAgQ0FMRU5Ew4FSSU8g4pSA4pSAICovCi5jYWwtdGJse3dpZHRoOjEwMCU7Ym9yZGVyLWNvbGxhcHNlOmNvbGxhcHNlO2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZn0KLmNhbC10YmwgdGh7dGV4dC1hbGlnbjpsZWZ0O3BhZGRpbmc6N3B4IDE0cHg7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7YmFja2dyb3VuZDp2YXIoLS1iZzMpfQouY2FsLXRibCB0aC5ye3RleHQtYWxpZ246cmlnaHR9Ci5jYWwtdGJsIHRke3BhZGRpbmc6OXB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtmb250LXNpemU6MTNweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9Ci5jYWwtdGJsIHRkLnJ7dGV4dC1hbGlnbjpyaWdodH0KLmNhbC10YmwgdHI6bGFzdC1jaGlsZCB0ZHtib3JkZXItYm90dG9tOm5vbmV9Ci5jYWwtdGJsIHRyOmhvdmVyIHRke2JhY2tncm91bmQ6dmFyKC0tYmczKX0KLmNhbC1mbGFne2ZvbnQtc2l6ZToxNnB4fQouY2FsLXRpbWV7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9Ci5jYWwtZXZ7Zm9udC13ZWlnaHQ6NTAwO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcDttYXgtd2lkdGg6MzIwcHh9Ci5jYWwtdmFse2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC13ZWlnaHQ6NzAwO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjEzcHh9Ci5jYWwtZmN7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkKX0KLmltcC1oaWdoe2NvbG9yOnZhcigtLXJlZCl9LmltcC1tZWR7Y29sb3I6dmFyKC0td2Fybil9CgouaW5kLWFjY3tiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO21hcmdpbi1ib3R0b206MTZweH0KLmluZC1hY2MtaGRye2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzoxMnB4IDE2cHg7Y3Vyc29yOnBvaW50ZXI7dHJhbnNpdGlvbjpiYWNrZ3JvdW5kIC4xNXN9Ci5pbmQtYWNjLWhkcjpob3ZlcntiYWNrZ3JvdW5kOnZhcigtLWJnMyl9Ci5pbmQtYWNjLXRpdGxle2ZvbnQtc2l6ZToxNHB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS1hY2NlbnQpfQouaW5kLWFjYy1zdWJ7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQouaW5kLWFjYy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nOjAgMTZweCAxNnB4fQouaW5kLWFjYy1ib2R5Lm9wZW57ZGlzcGxheTpibG9ja30KLnRibC1ta3R7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2U7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZX0KLnRibC1ta3QgdGhlYWQgdHJ7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKX0KLnRibC1ta3QgdGh7dGV4dC1hbGlnbjpsZWZ0O3BhZGRpbmc6N3B4IDE0cHg7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZn0KLnRibC1ta3QgdGgucnt0ZXh0LWFsaWduOnJpZ2h0fQoudGJsLW1rdCB0ZHtwYWRkaW5nOjlweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjE0cHg7dmVydGljYWwtYWxpZ246bWlkZGxlfQoudGJsLW1rdCB0ZC5ye3RleHQtYWxpZ246cmlnaHR9Ci50YmwtbWt0IHRyOmxhc3QtY2hpbGQgdGR7Ym9yZGVyLWJvdHRvbTpub25lfQoudGJsLW1rdCB0cjpob3ZlciB0ZHtiYWNrZ3JvdW5kOnZhcigtLWJnMyl9Ci50YmwtbWt0IC5zeW17Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLXRleHQpfQoudGJsLW1rdCAuZGVzY3tmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC13ZWlnaHQ6NDAwO2ZvbnQtZmFtaWx5OidJbnRlcicsc2Fucy1zZXJpZjttYXJnaW4tdG9wOjFweH0KLnRibC1ta3QgLnZhbHtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjE1cHg7Y29sb3I6dmFyKC0tdGV4dCl9Ci50YmwtbWt0IC52YWwubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOjEycHh9Ci50YmwtbWt0IC5jaGd7Zm9udC1zaXplOjEzcHg7Zm9udC13ZWlnaHQ6NjAwfQoudGJsLW1rdCAuY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0udGJsLW1rdCAuY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LnRibC1ta3QgLmNoZy1mbHtjb2xvcjp2YXIoLS1tdXRlZCl9Ci50Ymwtd3JhcHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OHB4O292ZXJmbG93OmhpZGRlbjttYXJnaW4tYm90dG9tOjE4cHh9Ci50YmwtaGRye2JhY2tncm91bmQ6dmFyKC0tYmczKTtwYWRkaW5nOjlweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcn0KLnRibC1oZHItdGl0bGV7Zm9udC1zaXplOjEwcHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MS41cHh9Ci50YmwtaGRyLXRpbWV7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQpmb290ZXJ7bWFyZ2luLXRvcDoyNHB4O3BhZGRpbmctdG9wOjEycHg7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtd2VpZ2h0OjUwMH0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KCjxkaXYgY2xhc3M9ImhkciI+CiAgPGRpdiBjbGFzcz0ibG9nbyI+VFJBREVSIDxzcGFuPkRFU0s8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0iaGRyLXJpZ2h0Ij4KICAgIDxkaXYgY2xhc3M9ImJhZGdlIj7il48gQU8gVklWTzwvZGl2PgogICAgPGRpdiBjbGFzcz0iaGRyLXRpbWUiIGlkPSJsYXN0LXVwZGF0ZSI+4oCUPC9kaXY+CiAgPC9kaXY+CjwvZGl2PgoKPGRpdiBjbGFzcz0idGFicyI+CiAgPGRpdiBjbGFzcz0idGFiIGFjdGl2ZSIgb25jbGljaz0ic3coJ2NvdGFjb2VzJyx0aGlzKSI+8J+TiiBDb3Rhw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygnaW5kaWNhZG9yZXMnLHRoaXMpIj7wn5OIIEluZGljYWRvcmVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygncG9zaWNvZXMnLHRoaXMpIj7wn5K8IFBvc2nDp8O1ZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3KCdjYWxlbmRhcmlvJyx0aGlzKSI+8J+ThSBDYWxlbmTDoXJpbzwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENPVEHDh8OVRVMg4pWQ4pWQIC0tPgo8ZGl2IGlkPSJ0YWItY290YWNvZXMiIGNsYXNzPSJ0YWItY29udGVudCBhY3RpdmUiPgogIDxkaXYgY2xhc3M9InRibC13cmFwIj4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5FVUEg4oCUIE1lcmNhZG9zPC9zcGFuPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpbWUiIGlkPSJsYXN0LXVwZGF0ZS10YmwiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDx0YWJsZSBjbGFzcz0idGJsLW1rdCI+CiAgICAgIDx0aGVhZD48dHI+PHRoPkF0aXZvPC90aD48dGggY2xhc3M9InIiPsOabHRpbW88L3RoPjx0aCBjbGFzcz0iciI+VmFyaWHDp8OjbzwvdGg+PHRoIGNsYXNzPSJyIj5WYXIuJTwvdGg+PC90cj48L3RoZWFkPgogICAgICA8dGJvZHk+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlMmYW1wO1AgRVMxKjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkZ1dHVybyBTJlAgNTAwPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImVzZi1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJlc2YtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZXNmLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPk5hc2RhcSBOUTwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkZ1dHVybyBOYXNkYXEgMTAwPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJucWYtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0ibnFmLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkRvdyBKb25lczwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPsONbmRpY2UgREpJQTwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJkamktcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZGppLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImRqaS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5WSVg8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5Wb2xhdGlsaWRhZGU8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InZpeC12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2aXgtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+RFhZPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+RMOzbGFyIEluZGV4PC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImR4eS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJkeHktdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iZHh5LWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlVTRC9CUkw8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5Dw6JtYmlvIETDs2xhcjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJ1c2QtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0idXNkLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InVzZC1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0idGJsLXdyYXAiPgogICAgPGRpdiBjbGFzcz0idGJsLWhkciI+PHNwYW4gY2xhc3M9InRibC1oZHItdGl0bGUiPkIzIOKAlCBUb3AgMTA8L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+VmFyLiU8L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5JQk9WPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+w41uZGljZSBCb3Zlc3BhPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9Imlib3YtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iaWJvdi12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJpYm92LWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPldJTjEhPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+RnV0dXJvIElCT1Y8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0id2luLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Indpbi12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ3aW4tYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+UEVUUjQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5QZXRyb2JyYXMgUE48L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0icGV0cjRxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InBldHI0cS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJwZXRyNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+SVRVQjQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5JdGHDuiBVbmliYW5jbyBQTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJpdHViNHEtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iaXR1YjRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9Iml0dWI0cS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5WQUxFMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlZhbGUgT048L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0idmFsZTNxLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InZhbGUzcS12Ij7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ2YWxlM3EtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+QkJEQzQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5CcmFkZXNjbyBQTjwvZGl2PjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0idmFsIGxvYWRpbmciIGlkPSJiYmRjNHEtcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYmJkYzRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJiZGM0cS1jIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5BQkVWMzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkFtYmV2IE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImFiZXYzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJhYmV2M3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYWJldjNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJCQVMzPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+QmFuY28gZG8gQnJhc2lsIE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJiYXMzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJiYmFzM3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iYmJhczNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPldFR0UzPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+V0VHIE9OPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9IndlZ2UzcS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJ3ZWdlM3EtdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0id2VnZTNxLWMiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPlJPWE8zNDwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPk51YmFuayBCRFI8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0icm94bzM0cS1wIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJjaGciIGlkPSJyb3hvMzRxLXYiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9InJveG8zNHEtYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgPC90Ym9keT4KICAgIDwvdGFibGU+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Imp1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuIj48c3BhbiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+QjMgcG9yIFNlZ21lbnRvPC9zcGFuPjxidXR0b24gb25jbGljaz0iZXhwYW5kQWxsKCkiIGlkPSJidG4tZXhwYW5kIiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzMpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjb2xvcjp2YXIoLS1hY2NlbnQpO3BhZGRpbmc6NHB4IDEycHg7Zm9udC1zaXplOjExcHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo2MDA7bGV0dGVyLXNwYWNpbmc6LjVweCI+KyBFeHBhbmRpciBUb2RvczwvYnV0dG9uPjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnZmluJykiPjxzcGFuPvCfj6YgRmluYW5jZWlybzwvc3Bhbj48c3BhbiBpZD0iYXItZmluIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItZmluIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1maW4iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygncGV0JykiPjxzcGFuPvCfm6IgUGV0csOzbGVvICZhbXA7IEfDoXM8L3NwYW4+PHNwYW4gaWQ9ImFyLXBldCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXBldCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctcGV0Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ21pbicpIj48c3Bhbj7im48gTWluZXJhw6fDo288L3NwYW4+PHNwYW4gaWQ9ImFyLW1pbiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW1pbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbWluIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ21hdCcpIj48c3Bhbj7wn4yyIFBhcGVsICZhbXA7IENlbHVsb3NlPC9zcGFuPjxzcGFuIGlkPSJhci1tYXQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1tYXQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW1hdCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCd1dGknKSI+PHNwYW4+4pqhIFV0aWxpZGFkZSBQw7pibGljYTwvc3Bhbj48c3BhbiBpZD0iYXItdXRpIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItdXRpIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy11dGkiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnY2MnKSI+PHNwYW4+8J+bjSBDb25zdW1vIEPDrWNsaWNvPC9zcGFuPjxzcGFuIGlkPSJhci1jYyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWNjIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1jYyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdjbicpIj48c3Bhbj7wn5uSIENvbnN1bW8gTsOjbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0iYXItY24iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1jbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctY24iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0Zygnc2F1JykiPjxzcGFuPvCfj6UgU2HDumRlPC9zcGFuPjxzcGFuIGlkPSJhci1zYXUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1zYXUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXNhdSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdpbmQnKSI+PHNwYW4+8J+PlyBCZW5zIEluZHVzdHJpYWlzPC9zcGFuPjxzcGFuIGlkPSJhci1pbmQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1pbmQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWluZCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCd0aXQnKSI+PHNwYW4+8J+SuyBUSSAmYW1wOyBDb211bmljYcOnw7Vlczwvc3Bhbj48c3BhbiBpZD0iYXItdGl0Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItdGl0Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy10aXQiPjwvZGl2PjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FVUEgcG9yIFNlZ21lbnRvPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdtNycpIj48c3Bhbj7irZAgNyBNYWduw61maWNhczwvc3Bhbj48c3BhbiBpZD0iYXItbTciPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1tNyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbTciPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnbnEnKSI+PHNwYW4+8J+SuyBOYXNkYXEgVG9wIDE1PC9zcGFuPjxzcGFuIGlkPSJhci1ucSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLW5xIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1ucSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdzcCcpIj48c3Bhbj7wn5OKIFMmYW1wO1AgNTAwIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0iYXItc3AiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1zcCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9Imctc3AiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnZGonKSI+PHNwYW4+8J+PmyBEb3cgSm9uZXMgVG9wIDIwPC9zcGFuPjxzcGFuIGlkPSJhci1kaiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWRqIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1kaiI+PC9kaXY+PC9kaXY+CgogIDxkaXYgY2xhc3M9InRibC13cmFwIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij4KICAgIDxkaXYgY2xhc3M9InRibC1oZHIiPjxzcGFuIGNsYXNzPSJ0YmwtaGRyLXRpdGxlIj5Db21tb2RpdGllczwvc3Bhbj48L2Rpdj4KICAgIDx0YWJsZSBjbGFzcz0idGJsLW1rdCI+CiAgICAgIDx0aGVhZD48dHI+PHRoPkF0aXZvPC90aD48dGggY2xhc3M9InIiPsOabHRpbW88L3RoPjwvdHI+PC90aGVhZD4KICAgICAgPHRib2R5PgogICAgICAgIDx0cj48dGQ+PGRpdiBjbGFzcz0ic3ltIj5XVEkvQ0w8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5QZXRyw7NsZW8gV1RJPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImNsLXAiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkdPTEQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5PdXJvPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImdvbGQtcCI+4oCUPC9zcGFuPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+U0lMVkVSPC9kaXY+PGRpdiBjbGFzcz0iZGVzYyI+UHJhdGE8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0ic2lsdmVyLXAiPuKAlDwvc3Bhbj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkNPUFBFUjwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPkNvYnJlPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImNvcHBlci1wIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0idGJsLXdyYXAiPgogICAgPGRpdiBjbGFzcz0idGJsLWhkciI+PHNwYW4gY2xhc3M9InRibC1oZHItdGl0bGUiPkJpdGNvaW48L3NwYW4+PC9kaXY+CiAgICA8dGFibGUgY2xhc3M9InRibC1ta3QiPgogICAgICA8dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+SW5mbzwvdGg+PC90cj48L3RoZWFkPgogICAgICA8dGJvZHk+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkJUQy9VU0Q8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj5CaXRjb2luIFNwb3Q8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iYnRjLXAiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9ImNoZyIgaWQ9ImJ0Yy1jIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+QlRDIFJTSTwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlJTSSBTZW1hbmFsPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJ0Yy1yc2kiPuKAlDwvc3Bhbj48L3RkPjx0ZCBjbGFzcz0iciI+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PC90cj4KICAgICAgICA8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+RnVuZGluZzwvZGl2PjxkaXYgY2xhc3M9ImRlc2MiPlRheGEgOGggQlRDPC9kaXY+PC90ZD48dGQgY2xhc3M9InIiPjxzcGFuIGNsYXNzPSJ2YWwgbG9hZGluZyIgaWQ9ImJ0Yy1mdW5kIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PHRkIGNsYXNzPSJyIj48L3RkPjwvdHI+CiAgICAgICAgPHRyPjx0ZD48ZGl2IGNsYXNzPSJzeW0iPkZlYXIgJmFtcDsgR3JlZWQ8L2Rpdj48ZGl2IGNsYXNzPSJkZXNjIj7DjW5kaWNlIHNlbnRpbWVudG88L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iZmctdmFsIj7igJQ8L3NwYW4+PC90ZD48dGQgY2xhc3M9InIiPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBpZD0iZmctbGJsIiBzdHlsZT0iZm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpIj7igJQ8L3NwYW4+PC90ZD48L3RyPgogICAgICA8L3Rib2R5PgogICAgPC90YWJsZT4KICA8L2Rpdj4KICA8Zm9vdGVyPjxzcGFuIGlkPSJmb290ZXItdGltZSI+4oCUPC9zcGFuPjxzcGFuPlRyYWRlciBEZXNrIHYxMS4zPC9zcGFuPjwvZm9vdGVyPgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIElORElDQURPUkVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWluZGljYWRvcmVzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImRvdCI+PC9zcGFuPkNpY2xvIEJpdGNvaW48L2Rpdj4KICA8ZGl2IGlkPSJidGMtY3ljbGUtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTRweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDE1MHB4O2dhcDoxMHB4O21hcmdpbjoxNHB4IDAiPgogICAgPGRpdiBpZD0iZmctYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweCI+Q2FycmVnYW5kbyBGZWFyICZhbXA7IEdyZWVkLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTZweDt0ZXh0LWFsaWduOmNlbnRlciI+CiAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjZweDtmb250LXdlaWdodDo2MDA7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHgiPkJUQy9VU0Q8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImJ0Yy1pbmQtcCI+4oCUPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5CVEMgU2VtYW5hbDwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgoKICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OmZsZXgtZW5kO21hcmdpbi1ib3R0b206MTBweCI+CiAgICA8YnV0dG9uIG9uY2xpY2s9InRvZ2dsZUFsbEluZCgpIiBpZD0iYnRuLWFsbC1pbmQiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2NvbG9yOnZhcigtLWFjY2VudCk7cGFkZGluZzo1cHggMTRweDtmb250LXNpemU6MTFweDtjdXJzb3I6cG9pbnRlcjtmb250LWZhbWlseTppbmhlcml0O2ZvbnQtd2VpZ2h0OjYwMDtsZXR0ZXItc3BhY2luZzouNXB4Ij7iiJIgUmVjb2xoZXIgVG9kb3M8L2J1dHRvbj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3BldHI0JykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9ImluZC1hY2MtdGl0bGUiPlBFVFI0IOKAlCBQZXRyb2JyYXMgUE48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+UGV0csOzbGVvICZhbXA7IEfDoXMgwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdwZXRyNCcpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1wZXRyNCI+4pa8PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWJvZHkgb3BlbiIgaWQ9InBldHI0LWluZC13cmFwIj48ZGl2IGlkPSJwZXRyNC1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3ZhbGUzJykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9ImluZC1hY2MtdGl0bGUiPlZBTEUzIOKAlCBWYWxlIE9OPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPk1pbmVyYcOnw6NvIMK3IGNsaXF1ZSBwYXJhIGV4cGFuZGlyL3JlY29saGVyPC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHgiPjxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxM3B4IiBvbmNsaWNrPSJldmVudC5zdG9wUHJvcGFnYXRpb24oKTtybCgndmFsZTMnKSI+4oa7PC9zcGFuPjxzcGFuIGlkPSJhci1pbmQtdmFsZTMiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJ2YWxlMy1pbmQtd3JhcCI+PGRpdiBpZD0idmFsZTMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iaW5kLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWhkciIgb25jbGljaz0idG9nSW5kKCdiYmFzMycpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5CQkFTMyDigJQgQmFuY28gZG8gQnJhc2lsIE9OPC9kaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy1zdWIiPkJhbmNvcyDCtyBjbGlxdWUgcGFyYSBleHBhbmRpci9yZWNvbGhlcjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij48c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTNweCIgb25jbGljaz0iZXZlbnQuc3RvcFByb3BhZ2F0aW9uKCk7cmwoJ2JiYXMzJykiPuKGuzwvc3Bhbj48c3BhbiBpZD0iYXItaW5kLWJiYXMzIj7ilrw8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtYm9keSBvcGVuIiBpZD0iYmJhczMtaW5kLXdyYXAiPjxkaXYgaWQ9ImJiYXMzLWluZCI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImluZC1hY2MiPgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1oZHIiIG9uY2xpY2s9InRvZ0luZCgnYXhpYTMnKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0iaW5kLWFjYy10aXRsZSI+QVhJQTMg4oCUIEF1cmVuIEVuZXJnaWEgT048L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+RW5lcmdpYSBFbMOpdHJpY2EgwrcgY2xpcXVlIHBhcmEgZXhwYW5kaXIvcmVjb2xoZXI8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEzcHgiIG9uY2xpY2s9ImV2ZW50LnN0b3BQcm9wYWdhdGlvbigpO3JsKCdheGlhMycpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1heGlhMyI+4pa8PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJpbmQtYWNjLWJvZHkgb3BlbiIgaWQ9ImF4aWEzLWluZC13cmFwIj48ZGl2IGlkPSJheGlhMy1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJpbmQtYWNjIj4KICAgIDxkaXYgY2xhc3M9ImluZC1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dJbmQoJ3JveG8zNCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXRpdGxlIj5ST1hPMzQg4oCUIE51YmFuayBCRFI8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYWNjLXN1YiI+RmludGVjaCDCtyBjbGlxdWUgcGFyYSBleHBhbmRpci9yZWNvbGhlcjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij48c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTNweCIgb25jbGljaz0iZXZlbnQuc3RvcFByb3BhZ2F0aW9uKCk7cmwoJ3JveG8zNCcpIj7ihrs8L3NwYW4+PHNwYW4gaWQ9ImFyLWluZC1yb3hvMzQiPuKWvDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0iaW5kLWFjYy1ib2R5IG9wZW4iIGlkPSJyb3hvMzQtaW5kLXdyYXAiPjxkaXYgaWQ9InJveG8zNC1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBQT1NJw4fDlUVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLXBvc2ljb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Imp1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuIj48c3BhbiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4Ij48c3BhbiBjbGFzcz0iZG90Ij48L3NwYW4+T3BlcmHDp8O1ZXMgQXRpdmFzPC9zcGFuPjxidXR0b24gb25jbGljaz0idG9nZ2xlQWxsUG9zKCkiIGlkPSJidG4tYWxsLXBvcyIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmczKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y29sb3I6dmFyKC0tYWNjZW50KTtwYWRkaW5nOjRweCAxMnB4O2ZvbnQtc2l6ZToxMXB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NjAwIj7iiJIgUmVjb2xoZXIgVG9kYXM8L2J1dHRvbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1wdCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5QRVRSNDwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5QZXRyb2JyYXMgUE4gwrcgQ2FsbCBWZW5kaWRhIMK3IFBFVFJMMzE5IMK3IFZlbmMgMTcvMTIvMjAyNjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLXJpZ2h0Ij4KICAgICAgICA8ZGl2PjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJwdC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJwdC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLXB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLXB0Ij4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChQRVRSTDMxOSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDMwLDg1PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJwdC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE3LzEyLzIwMjYgwrcgPHNwYW4gaWQ9InB0LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+NDMsNCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIEImYW1wO1MgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+OSw0JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gTUMgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siIGlkPSJwdC1tYy1ydCI+Y2FsYy4uLjwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnIj4KICAgICAgPGRpdiBjbGFzcz0ic2d0Ij7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWxsIHNlciBleGVyY2lkYTwvZGl2PgogICAgICA8ZGl2IGlkPSJwdC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJwdC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIGV4ZXJjZXI8L2Rpdj48ZGl2IGNsYXNzPSJpdiIgaWQ9InB0LW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InB0LW1jLXYiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJwdC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1hY2MiPgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1oZHIiIG9uY2xpY2s9InRvZ1BvcygncG9zLXZsJykiPgogICAgICA8ZGl2PjxkaXYgY2xhc3M9InBvcy1hY2MtdGsiPlZBTEUzPC9kaXY+PGRpdiBjbGFzcz0icG9zLWFjYy1zdWIiPlZhbGUgT04gwrcgQ2FsbCBWZW5kaWRhIMK3IFZBTEVCNTc0IMK3IFZlbmMgMTgvMDIvMjAyNzwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLXJpZ2h0Ij4KICAgICAgICA8ZGl2PjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJ2bC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJ2bC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLXZsIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLXZsIj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChWQUxFQjU3NCk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDU3LDQwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJ2bC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE4LzAyLzIwMjcgwrcgPHNwYW4gaWQ9InZsLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+NzEsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIEImYW1wO1MgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MTQsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIE1DIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIiBpZD0idmwtbWMtcnQiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FsbCBzZXIgZXhlcmNpZGE8L2Rpdj4KICAgICAgPGRpdiBpZD0idmwtbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kbyA1LjAwMCBjZW7DoXJpb3MuLi48L2Rpdj4KICAgICAgPGRpdiBpZD0idmwtbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Qcm9iLiBleGVyY2VyPC9kaXY+PGRpdiBjbGFzcz0iaXYiIGlkPSJ2bC1tYy1zIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJ2bC1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHg7bGluZS1oZWlnaHQ6MS41IiBpZD0idmwtbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1hMycpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5BWElBMzwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5BWElBMyAoQSkgwrcgQmlkaXJlY2lvbmFsIMK3IFZlbmMgMTQvMDkvMjAyNjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLXJpZ2h0Ij4KICAgICAgICA8ZGl2PjxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJhMy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJhMy1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLWEzIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj7ilrw8L3NwYW4+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWJvZHkgb3BlbiIgaWQ9ImJvZHktcG9zLWEzIj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNDMsNTE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPktVTyAoKzI2LDYlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNjgsNzY8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+YXTDqSArMzEsMiUgLyArMjAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPis0JSBmaXhvPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTQvMDkvMjAyNiDCtyA8c3BhbiBpZD0iYTMtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTMta2RvIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtVTzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1rdW8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1zdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJhMy1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMnB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9ImEzLW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6OHB4O21hcmdpbi10b3A6OHB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+U2VtIEJhcnJlaXJhIOKchTwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIiBpZD0iYTMtbWMtbmIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzLW1jLWt1Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpdiBkb3duIiBpZD0iYTMtbWMta2QiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzLW1jLXZvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJhMy1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1hY2MiPgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1oZHIiIG9uY2xpY2s9InRvZ1BvcygncG9zLWEzYicpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5BWElBMzwvZGl2PjxkaXYgY2xhc3M9InBvcy1hY2Mtc3ViIj5BWElBMyAoQikgwrcgQmlkaXJlY2lvbmFsIElPTiBJdGHDuiDCtyBWZW5jIDAyLzEwLzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0iYTNiLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9ImEzYi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBpZD0iYXItcG9zLWEzYiIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1hM2IiPgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA0MCw1Mjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S1VPICgrMjQlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNjIsODE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+YXTDqSArMzEsMiUgLyArMjAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPis0JSBmaXhvICgxMiwzMyUgYS5hLik8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4wMi8xMC8yMDI2IMK3IDxzcGFuIGlkPSJhM2ItZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLWtkbyI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InN2IiBpZD0iYTNiLWt1byI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzYi1zdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siIGlkPSJhM2ItbWMtbmIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzYi1tYy1rdSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaXYgZG93biIgaWQ9ImEzYi1tYy1rZCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTNiLW1jLXZvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiIGlkPSJhM2ItbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtYWNjIj4KICAgIDxkaXYgY2xhc3M9InBvcy1hY2MtaGRyIiBvbmNsaWNrPSJ0b2dQb3MoJ3Bvcy1yeCcpIj4KICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXRrIj5ST1hPMzQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+Uk9YTzM0IMK3IEJEUiBOdWJhbmsgwrcgTGFuw6dhbWVudG8gQ29iZXJ0byDCtyBST1hPRzEwNSDCtyBWZW5jIDE2LzA3LzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0icngtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icGMyIiBpZD0icngtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPHNwYW4gaWQ9ImFyLXBvcy1yeCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1yeCI+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlN0cmlrZSAoUk9YT0cxMDUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCAxMCw1MCDCtyBJVE0g4pqgPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJyeC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE2LzA3LzIwMjYgwrcgPHNwYW4gaWQ9InJ4LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MzMsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRlbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4wLDY0Mzwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gQiZhbXA7UyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iPjYwLDQlIOKaoDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJvYi4gTUMgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJyeC1tYy1ydCI+Y2FsYy4uLjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+T2JqZXRpdm88L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5GZWNoYXIgYWJhaXhvIGRlIFIkIDEwLDUwPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIHN1Y2Vzc288L2Rpdj4KICAgICAgPGRpdiBpZD0icngtbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJyeC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjhweDttYXJnaW4tdG9wOjhweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIFN1Y2Vzc288L2Rpdj48ZGl2IGNsYXNzPSJpdiBvayIgaWQ9InJ4LW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5DYWxsIEV4ZXJjaWRhPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InJ4LW1jLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5LRE8gQXRpbmdpZG88L2Rpdj48ZGl2IGNsYXNzPSJpdiBkb3duIiBpZD0icngtbWMtayI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icngtbWMtdiI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4IiBpZD0icngtbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjIwcHgiPjxzcGFuIGNsYXNzPSJkb3QiPjwvc3Bhbj5FbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWFjYyI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtYWNjLWhkciIgb25jbGljaz0idG9nUG9zKCdwb3MtYmInKSI+CiAgICAgIDxkaXY+PGRpdiBjbGFzcz0icG9zLWFjYy10ayI+QkJBUzM8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtYWNjLXN1YiI+QmFuY28gZG8gQnJhc2lsIE9OIMK3IExhbsOnYW1lbnRvIENvYmVydG8gwrcgQkJBU0gyMSDCtyBWZW5jIDIwLzA4LzIwMjY8L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icG9zLWFjYy1yaWdodCI+CiAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0iYmItcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icGMyIiBpZD0iYmItYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPHNwYW4gaWQ9ImFyLXBvcy1iYiIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4pa8PC9zcGFuPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLWFjYy1ib2R5IG9wZW4iIGlkPSJib2R5LXBvcy1iYiI+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlN0cmlrZSAoQkJBU0gyMSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDIxLDY1IMK3IElUTTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJlw6dvIHZzIHN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YgaXRtIiBpZD0iYmItaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4yMC8wOC8yMDI2IMK3IDxzcGFuIGlkPSJiYi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZvbC4gSW1wbC48L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjI3LDElPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EZWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjAsMjQ5PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBCJmFtcDtTIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjIxLDMlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBNQyBleGVyY2VyPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayIgaWQ9ImJiLW1jLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5PYmpldGl2bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPkZlY2hhciBhYmFpeG8gZGUgUiQgMjEsNjU8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyI+CiAgICAgIDxkaXYgY2xhc3M9InNndCI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FsbCBzZXIgZXhlcmNpZGE8L2Rpdj4KICAgICAgPGRpdiBpZD0iYmItbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTJweCI+Q2FsY3VsYW5kbyA1LjAwMCBjZW7DoXJpb3MuLi48L2Rpdj4KICAgICAgPGRpdiBpZD0iYmItbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo4cHg7bWFyZ2luLXRvcDo4cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Qcm9iLiBleGVyY2VyPC9kaXY+PGRpdiBjbGFzcz0iaXYiIGlkPSJiYi1tYy1zIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJiYi1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHg7bGluZS1oZWlnaHQ6MS41IiBpZD0iYmItbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjp2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLW11dGVkKSI+CiAgICA8ZGl2IGNsYXNzPSJwdCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTZweCI+QVhJQTMgU2hvcnQgU3RyYW5nbGU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5DYWxsIFYuIEFYSUFJNTA1PC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+UiQgNTAsNTA8L3NwYW4+PC9kaXY+PGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+4pyFIEHDp8O1ZXMgbGliZXJhZGFzPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBjIiBzdHlsZT0ib3BhY2l0eTouNTtib3JkZXItY29sb3I6dmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdC1jb2xvcjp2YXIoLS1tdXRlZCkiPgogICAgPGRpdiBjbGFzcz0icHQiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjE2cHgiPlJPWE8zNCBQcmVmaXhhZG8gNywxJTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkVuY2VycmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjA0LzA2LzIwMjY8L3NwYW4+PC9kaXY+PGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBvayI+4pyFIH41LDE3JSAoNzIlIGRvIGFsdm8pPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENBTEVORMOBUklPIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWNhbGVuZGFyaW8iIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjE0cHgiPgogICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtd2VpZ2h0OjUwMCI+8J+HuvCfh7gg8J+Hp/Cfh7cg8J+HqvCfh7og8J+HrPCfh6cg8J+HqPCfh7Mg8J+Hr/Cfh7Ug8J+HqfCfh6ogwrcgSW1wYWN0byBNw6lkaW8rPC9kaXY+CiAgICA8YnV0dG9uIG9uY2xpY2s9ImxvYWRDYWwoKSIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtib3JkZXI6bm9uZTtjb2xvcjojZmZmO3BhZGRpbmc6OHB4IDE4cHg7Zm9udC1zaXplOjEycHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo3MDA7bGV0dGVyLXNwYWNpbmc6LjVweCI+4oa7IEF0dWFsaXphcjwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgaWQ9ImNhbC1zdCIgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjhweCI+PC9kaXY+CiAgPGRpdiBpZD0iY2FsLWFyZWEiPjxkaXYgc3R5bGU9ImZvbnQtZmFtaWx5OkludGVyLHNhbnMtc2VyaWYiPjxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MjBweCI+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDojMWExYTI0O3BhZGRpbmc6OHB4IDE0cHg7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOiM3YzZhZjc7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItbGVmdDozcHggc29saWQgIzdjNmFmNzttYXJnaW4tYm90dG9tOjJweCI+TW9uZGF5IDE1LzA2PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4eq8J+Hujwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDQ6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5FQ0IgUHJlc2lkZW50IExhZ2FyZGUgU3BlYWtzPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY5ODAwO3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PC9kaXY+PGRpdiBzdHlsZT0ibWFyZ2luLWJvdHRvbToyMHB4Ij48ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOiMxYTFhMjQ7cGFkZGluZzo4cHggMTRweDtmb250LXNpemU6MTFweDtmb250LXdlaWdodDo3MDA7Y29sb3I6IzdjNmFmNzt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MXB4O2JvcmRlci1sZWZ0OjNweCBzb2xpZCAjN2M2YWY3O21hcmdpbi1ib3R0b206MnB4Ij5UdWVzZGF5IDE2LzA2PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4ev8J+HtTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDA6MTk8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5CT0ogUG9saWN5IFJhdGU8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPjwxLjAwJTwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6/wn4e1PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMDoxOTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPk1vbmV0YXJ5IFBvbGljeSBTdGF0ZW1lbnQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6bwn4e6PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMTozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPkNhc2ggUmF0ZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+NC4zNSU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4em8J+Hujwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDE6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5SQkEgUmF0ZSBTdGF0ZW1lbnQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6bwn4e6PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMjozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlJCQSBQcmVzcyBDb25mZXJlbmNlPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4ev8J+HtTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDM6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5CT0ogUHJlc3MgQ29uZmVyZW5jZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjwvZGl2PjxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MjBweCI+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDojMWExYTI0O3BhZGRpbmc6OHB4IDE0cHg7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOiM3YzZhZjc7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItbGVmdDozcHggc29saWQgIzdjNmFmNzttYXJnaW4tYm90dG9tOjJweCI+V2VkbmVzZGF5IDE3LzA2PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4es8J+Hpzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDM6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5DUEkgeS95PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4zLjAlPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HqvCfh7o8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA3OjUwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+RUNCIFByZXNpZGVudCBMYWdhcmRlIFNwZWFrczwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA5OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+Q29yZSBSZXRhaWwgU2FsZXMgbS9tPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY5ODAwO3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4wLjYlPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA5OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+UmV0YWlsIFNhbGVzIG0vbTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MC41JTwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh7rwn4e4PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4xMTo0NTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlByZXNpZGVudCBUcnVtcCBTcGVha3M8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjk4MDA7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh7rwn4e4PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4xNTowMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPkZlZGVyYWwgRnVuZHMgUmF0ZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+My43NSU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4e68J+HuDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MTU6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5GT01DIEVjb25vbWljIFByb2plY3Rpb25zPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4e68J+HuDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MTU6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5GT01DIFN0YXRlbWVudDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjE1OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+Rk9NQyBQcmVzcyBDb25mZXJlbmNlPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij7igJQ8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4ez8J+Hvzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MTk6NDU8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5HRFAgcS9xPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4wLjglPC9zcGFuPjwvZGl2PjwvZGl2PjxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MjBweCI+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDojMWExYTI0O3BhZGRpbmc6OHB4IDE0cHg7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOiM3YzZhZjc7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItbGVmdDozcHggc29saWQgIzdjNmFmNzttYXJnaW4tYm90dG9tOjJweCI+VGh1cnNkYXkgMTgvMDY8L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6zwn4enPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wMzowMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPkNsYWltYW50IENvdW50IENoYW5nZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MjUuOEs8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4es8J+Hpzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDM6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5BdmVyYWdlIEVhcm5pbmdzIEluZGV4IDNtL3k8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjk4MDA7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPjQuMCU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4eo8J+HrTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDQ6MzA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5TTkIgTW9uZXRhcnkgUG9saWN5IEFzc2Vzc21lbnQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6jwn4etPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wNDozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlNOQiBQb2xpY3kgUmF0ZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MC4wMCU8L3NwYW4+PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyOHB4IDUycHggMWZyIDM2cHggNzBweCA3MHB4O2dhcDo2cHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6OHB4IDE0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzFhMWExYSI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNXB4Ij7wn4eo8J+HrTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTtmb250LXNpemU6MTFweCI+MDU6MDA8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIj5TTkIgUHJlc3MgQ29uZmVyZW5jZTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmNDQ0NDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+4oCUPC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HrPCfh6c8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA4OjAwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+TW9uZXRhcnkgUG9saWN5IFN1bW1hcnk8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPuKAlDwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh6zwn4enPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wODowMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPk1QQyBPZmZpY2lhbCBCYW5rIFJhdGUgVm90ZXM8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNmZjQ0NDQ7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjExcHgiPuKXj+KXj+KXjzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2NjYzt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTJweCI+4oCUPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjExcHgiPjEtMC04PC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HrPCfh6c8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA4OjAwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+T2ZmaWNpYWwgQmFuayBSYXRlPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZmY0NDQ0O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij7il4/il4/il488L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiNjY2M7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4zLjc1JTwvc3Bhbj48L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjI4cHggNTJweCAxZnIgMzZweCA3MHB4IDcwcHg7Z2FwOjZweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo4cHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMWExYTFhIj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE1cHgiPvCfh7rwn4e4PC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojNTU1O2ZvbnQtc2l6ZToxMXB4Ij4wOTozMDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2RkZDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXAiPlBoaWxseSBGZWQgTWFudWZhY3R1cmluZyBJbmRleDwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+OS44PC9zcGFuPjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HuvCfh7g8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjA5OjMwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+VW5lbXBsb3ltZW50IENsYWltczwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MjI1Szwvc3Bhbj48L2Rpdj48L2Rpdj48ZGl2IHN0eWxlPSJtYXJnaW4tYm90dG9tOjIwcHgiPjxkaXYgc3R5bGU9ImJhY2tncm91bmQ6IzFhMWEyNDtwYWRkaW5nOjhweCAxNHB4O2ZvbnQtc2l6ZToxMXB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjojN2M2YWY3O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzoxcHg7Ym9yZGVyLWxlZnQ6M3B4IHNvbGlkICM3YzZhZjc7bWFyZ2luLWJvdHRvbToycHgiPkZyaWRheSAxOS8wNjwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjhweCA1MnB4IDFmciAzNnB4IDcwcHggNzBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWEiPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTVweCI+8J+HrPCfh6c8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPjAzOjAwPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojZGRkO292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcCI+UmV0YWlsIFNhbGVzIG0vbTwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6I2ZmOTgwMDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTFweCI+4peP4pePPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjojY2NjO3RleHQtYWxpZ246cmlnaHQ7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7dGV4dC1hbGlnbjpyaWdodDtmb250LXNpemU6MTFweCI+MC41JTwvc3Bhbj48L2Rpdj48L2Rpdj48L2Rpdj48L2Rpdj4KPC9kaXY+Cgo8c2NyaXB0Pgpjb25zdCBCPSdodHRwczovL3RyYWRlci1kZXNrLm9ucmVuZGVyLmNvbSc7CmNvbnN0IFNFRz17CiAgZmluOlsnSVRVQjQnLCdCQkRDNCcsJ0JCQVMzJywnU0FOQjExJywnQjNTQTMnLCdCUEFDMTEnLCdJVFNBNCcsJ0JSU1I2JywnQUJDQjQnLCdCTUdCNCddLAogIHBldDpbJ1BFVFI0JywnUEVUUjMnLCdQUklPMycsJ0JSQVYzJywnVkJCUjMnLCdDU0FOMycsJ1JFQ1YzJywnVUdQQTMnLCdTRVFMMycsJ0dHQlI0J10sCiAgbWluOlsnVkFMRTMnLCdHR0JSNCcsJ0NTTkEzJywnVVNJTTUnLCdCUkFQNCcsJ0ZFU0E0JywnQ01JTjMnLCdDQkFWMycsJ0dPQVU0JywnUEdNTjMnXSwKICBtYXQ6WydTVVpCMycsJ0tMQk4xMScsJ0RYQ08zJywnVU5JUDYnLCdSQU5JMycsJ09SVlIzJywnU01UTzMnLCdGUkFTMycsJ0xQU0IzJywnQ1NVRDMnXSwKICB1dGk6WydBWElBMycsJ0VRVEwzJywnQ1BGRTMnLCdTQlNQMycsJ0NNSUc0JywnRU5HSTExJywnVEFFRTExJywnQVVSRTMnLCdFR0lFMycsJ0NQTEUzJ10sCiAgY2M6IFsnUkVOVDMnLCdMUkVOMycsJ01HTFUzJywnQ1lSRTMnLCdNUlZFMycsJ0FaWkEzJywnVklWQTMnLCdTQkZHMycsJ1lEVVEzJywnTU9WSTMnXSwKICBjbjogWydBQkVWMycsJ0pCU1MzJywnQlJGUzMnLCdOQVRVMycsJ01ESUEzJywnQkVFRjMnLCdTTENFMycsJ01UUkUzJywnQ0FNTDMnLCdQQ0FSMyddLAogIHNhdTpbJ1JET1IzJywnSEFQVjMnLCdGTFJZMycsJ0RBU0EzJywnUVVBTDMnLCdPTkNPMycsJ1BOVkwzJywnT0RQVjMnLCdNQVREMycsJ0FBTFIzJ10sCiAgaW5kOlsnV0VHRTMnLCdFTUJSMycsJ1JBSUwzJywnVEdNQTMnLCdST01JMycsJ1ZMSUQzJywnVFVQWTMnLCdJUkJSMycsJ1BPTU80JywnTEFWVjMnXSwKICB0aXQ6WydWSVZUMycsJ1RJTVMzJywnVE9UVlMzJywnUE9TSTMnLCdNTEFTMycsJ0FOSU0zJywnSU5UQjMnLCdMV1NBMycsJ0NBU0gzJywnT0lCUjMnXSwKfTsKY29uc3QgVVNTRUc9ewogIG03OlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ0dPT0dMJywnTUVUQScsJ1RTTEEnXSwKICBucTpbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdNRVRBJywnR09PR0wnLCdUU0xBJywnQVZHTycsJ0NPU1QnLCdORkxYJywnUUNPTScsJ0FNRCcsJ0FEQkUnLCdJTlRDJywnQ1NDTyddLAogIHNwOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQlJLLkInLCdKUE0nLCdMTFknLCdWJywnVU5IJywnWE9NJywnTUEnLCdORkxYJywnUEcnLCdKTkonLCdIRCcsJ0JBQyddLAogIGRqOlsnVU5IJywnR1MnLCdIRCcsJ1NIVycsJ0NBVCcsJ0FYUCcsJ01DRCcsJ0FNR04nLCdWJywnVFJWJywnSUJNJywnSlBNJywnSE9OJywnQ1JNJywnQ1ZYJywnQUFQTCcsJ01TRlQnLCdESVMnLCdOS0UnLCdCQSddCn07CmNvbnN0IGZSPXY9PnYhPW51bGw/J1IkICcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21pbmltdW1GcmFjdGlvbkRpZ2l0czoyLG1heGltdW1GcmFjdGlvbkRpZ2l0czoyfSk6J+KAlCc7CmNvbnN0IGZVPXY9PnYhPW51bGw/J1VTJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmUD12PT52IT1udWxsP051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwpmdW5jdGlvbiBFKGlkLHQpe2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKCFlKXJldHVybjtlLnRleHRDb250ZW50PXQ7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQpmdW5jdGlvbiBDaFRibChpZFYsaWRQY3Qsbm93LHByZXYsdHApewogIGNvbnN0IGRpZmY9bm93LXByZXYscGN0PShkaWZmL01hdGguYWJzKHByZXZ8fDEpKjEwMCksc2c9ZGlmZj49MD8nKyc6Jyc7CiAgY29uc3QgY2xzPWRpZmY+MD8nY2hnIGNoZy11cCc6ZGlmZjwwPydjaGcgY2hnLWRuJzonY2hnIGNoZy1mbCc7CiAgbGV0IHZhclN0cj0nJzsKICBpZih0cD09PSdyJyl2YXJTdHI9c2crJ1IkICcrTWF0aC5hYnMoZGlmZikudG9GaXhlZCgyKTsKICBlbHNlIGlmKHRwPT09J3UnKXZhclN0cj1zZytNYXRoLmFicyhkaWZmKS50b0ZpeGVkKDIpOwogIGVsc2UgdmFyU3RyPXNnK01hdGguYWJzKGRpZmYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk7CiAgY29uc3QgcGN0U3RyPXNnK3BjdC50b0ZpeGVkKDIpKyclJzsKICBjb25zdCBldj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZFYpO2lmKGV2KXtldi50ZXh0Q29udGVudD12YXJTdHI7ZXYuY2xhc3NOYW1lPWNsczt9CiAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWRQY3QpO2lmKGVwKXtlcC50ZXh0Q29udGVudD1wY3RTdHI7ZXAuY2xhc3NOYW1lPWNsczt9Cn0KZnVuY3Rpb24gQ2goaWQsbixwLHRwKXsKICBjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47CiAgY29uc3QgZD1uLXAscGM9KGQvTWF0aC5hYnMocHx8MSkqMTAwKS50b0ZpeGVkKDIpLHNnPWQ+PTA/JysnOicnOwogIGlmKHRwPT09J3InKWUudGV4dENvbnRlbnQ9c2crJ1IkICcrTWF0aC5hYnMoZCkudG9GaXhlZCgyKSsnICgnK3NnK3BjKyclKSc7CiAgZWxzZSBpZih0cD09PSd1JyllLnRleHRDb250ZW50PXNnK2QudG9GaXhlZCgyKSsnICgnK3NnK3BjKyclKSc7CiAgZWxzZSBlLnRleHRDb250ZW50PXNnK01hdGguYWJzKGQpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJyAoJytzZytwYysnJSknOwogIGUuY2xhc3NOYW1lPSdjYyAnKyhkPjA/J2NoZy11cCc6ZDwwPydjaGctZG4nOidjaGctZmwnKTsKfQpmdW5jdGlvbiBzdyh0LGVsKXsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiJykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiLWNvbnRlbnQnKS5mb3JFYWNoKHg9PnguY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJykpOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0YWItJyt0KS5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZihlbCllbC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZih0PT09J2luZGljYWRvcmVzJyYmIXdpbmRvdy5fSUwpe3dpbmRvdy5fSUw9dHJ1ZTtsb2FkSW5kKCk7fQogIGlmKHQ9PT0nY2FsZW5kYXJpbycpbG9hZENhbCgpOwp9CmZ1bmN0aW9uIHRnKGlkKXsKICBjb25zdCBiPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYi0nK2lkKSxhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci0nK2lkKTsKICBpZighYilyZXR1cm47Y29uc3Qgb3A9Yi5zdHlsZS5kaXNwbGF5IT09J2Jsb2NrJzsKICBiLnN0eWxlLmRpc3BsYXk9b3A/J2Jsb2NrJzonbm9uZSc7CiAgaWYoYSlhLnRleHRDb250ZW50PW9wPyfilrInOifilrwnOwogIGlmKG9wJiYhYi5kYXRhc2V0Lmwpe2IuZGF0YXNldC5sPScxJztsb2FkU2VnKGlkKTt9Cn0KCmFzeW5jIGZ1bmN0aW9uIGxvYWRTZWcoaWQpewogIGNvbnN0IGc9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ctJytpZCk7aWYoIWcpcmV0dXJuOwogIGNvbnN0IHBmeD1pZCsnXyc7CiAgaWYoVVNTRUdbaWRdKXsKICAgIGNvbnN0IHRrcz1VU1NFR1tpZF07CiAgICBnLmlubmVySFRNTD10a3MubWFwKHQ9Pntjb25zdCB0aWQ9dC5yZXBsYWNlKC9bXmEtekEtWjAtOV0vZywnXycpO3JldHVybiAnPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+VVM8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+Jyt0Kyc8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nO30pLmpvaW4oJycpOwogICAgdHJ5ewogICAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy91cy9xdW90ZXM/dGlja2Vycz0nK3Rrcy5qb2luKCcsJykpOwogICAgICBpZighci5vaylyZXR1cm47CiAgICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICAgIE9iamVjdC5lbnRyaWVzKGQpLmZvckVhY2goKFt0LHZdKT0+ewogICAgICAgIGNvbnN0IHRpZD10LnJlcGxhY2UoL1teYS16QS1aMC05XS9nLCdfJyk7CiAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICBpZihlcCYmdi5wcmljZSl7ZXAudGV4dENvbnRlbnQ9JyQnK051bWJlcih2LnByaWNlKS50b0ZpeGVkKDIpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CiAgICAgICAgaWYodi5wcmljZSYmdi5wcmV2KUNoKHBmeCt0aWQrJ19jJyx2LnByaWNlLHYucHJldiwndScpOwogICAgICB9KTsKICAgIH1jYXRjaChlKXt9CiAgICByZXR1cm47CiAgfQogIGNvbnN0IHRrcz1TRUdbaWRdO2lmKCF0a3MpcmV0dXJuOwogIGcuaW5uZXJIVE1MPSc8ZGl2IGNsYXNzPSJ0Ymwtd3JhcCI+PHRhYmxlIGNsYXNzPSJ0YmwtbWt0Ij48dGhlYWQ+PHRyPjx0aD5BdGl2bzwvdGg+PHRoIGNsYXNzPSJyIj7Dmmx0aW1vPC90aD48dGggY2xhc3M9InIiPlZhcmlhw6fDo288L3RoPjx0aCBjbGFzcz0iciI+VmFyLiU8L3RoPjwvdHI+PC90aGVhZD48dGJvZHk+JysKICAgIHRrcy5tYXAodD0+e2NvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7cmV0dXJuICc8dHI+PHRkPjxkaXYgY2xhc3M9InN5bSI+Jyt0Kyc8L2Rpdj48L3RkPjx0ZCBjbGFzcz0iciI+PHNwYW4gY2xhc3M9InZhbCBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iJytwZngrdGlkKydfdiI+4oCUPC9zcGFuPjwvdGQ+PHRkIGNsYXNzPSJyIj48c3BhbiBjbGFzcz0iY2hnIiBpZD0iJytwZngrdGlkKydfYyI+4oCUPC9zcGFuPjwvdGQ+PC90cj4nO30pLmpvaW4oJycpKwogICAgJzwvdGJvZHk+PC90YWJsZT48L2Rpdj4nOwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL3R2L2JyYXppbCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2Vyczp0a3MubWFwKHQ9PidCTUZCT1ZFU1BBOicrdCl9LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7CiAgICBpZighci5vayl0aHJvdyBuZXcgRXJyb3IoJ1RWIGZhaWwnKTsKICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBjb25zdCBsb2FkZWQ9bmV3IFNldCgpOwogICAgKGQuZGF0YXx8W10pLmZvckVhY2goeD0+ewogICAgICBjb25zdCB0PXgucy5yZXBsYWNlKCdCTUZCT1ZFU1BBOicsJycpLnRvTG93ZXJDYXNlKCk7CiAgICAgIGNvbnN0W2MsY2FdPXguZHx8W107CiAgICAgIGlmKGMhPW51bGwpewogICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0KydfcCcpOwogICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mUihjKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7bG9hZGVkLmFkZCh0KTt9CiAgICAgICAgQ2hUYmwocGZ4K3QrJ192JyxwZngrdCsnX2MnLGMsYy0oY2F8fDApLCdyJyk7CiAgICAgIH0KICAgIH0pOwogICAgLy8gRmFsbGJhY2sgdmlhIGJyYXBpIHBhcmEgdGlja2VycyBxdWUgVFYgbsOjbyByZXRvcm5vdQogICAgY29uc3QgbWlzc2luZz10a3MuZmlsdGVyKHQ9PiFsb2FkZWQuaGFzKHQudG9Mb3dlckNhc2UoKSkpOwogICAgaWYobWlzc2luZy5sZW5ndGg+MCl7CiAgICAgIHRyeXsKICAgICAgICBjb25zdCByYj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICAgICAgYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2VyczptaXNzaW5nLm1hcCh0PT4nQk1GQk9WRVNQQTonK3QpfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pOwogICAgICAgIC8vIFNlZ3VuZGEgdGVudGF0aXZhIGltZWRpYXRhCiAgICAgIH1jYXRjaChlMil7fQogICAgICAvLyBGYWxsYmFjayBpbmRpdmlkdWFsIHZpYSAvaW5kaWNhdG9ycwogICAgICBmb3IoY29uc3QgdCBvZiBtaXNzaW5nKXsKICAgICAgICB0cnl7CiAgICAgICAgICBjb25zdCByMj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy8nK3QrJy5TQScpOwogICAgICAgICAgaWYoIXIyLm9rKWNvbnRpbnVlOwogICAgICAgICAgY29uc3QgZDI9YXdhaXQgcjIuanNvbigpOwogICAgICAgICAgaWYoZDIucHJlY29fYXR1YWwpewogICAgICAgICAgICBjb25zdCB0aWQ9dC50b0xvd2VyQ2FzZSgpOwogICAgICAgICAgICBjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfcCcpOwogICAgICAgICAgICBpZihlcCl7ZXAudGV4dENvbnRlbnQ9ZlIoZDIucHJlY29fYXR1YWwpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CiAgICAgICAgICAgIGlmKGQyLnByZWNvX2FudGVyaW9yKUNoVGJsKHBmeCt0aWQrJ192JyxwZngrdGlkKydfYycsZDIucHJlY29fYXR1YWwsZDIucHJlY29fYW50ZXJpb3IsJ3InKTsKICAgICAgICAgIH0KICAgICAgICB9Y2F0Y2goZTIpe30KICAgICAgfQogICAgfQogIH1jYXRjaChlKXsKICAgIC8vIFRWIGZhbGhvdSBjb21wbGV0YW1lbnRlIOKAlCBmYWxsYmFjayBwYXJhIHRvZG9zIHZpYSAvaW5kaWNhdG9ycwogICAgZm9yKGNvbnN0IHQgb2YgdGtzLnNsaWNlKDAsNikpewogICAgICB0cnl7CiAgICAgICAgY29uc3QgcjI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvJyt0KycuU0EnKTsKICAgICAgICBpZighcjIub2spY29udGludWU7CiAgICAgICAgY29uc3QgZDI9YXdhaXQgcjIuanNvbigpOwogICAgICAgIGlmKGQyLnByZWNvX2F0dWFsKXsKICAgICAgICAgIGNvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7CiAgICAgICAgICBjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfcCcpOwogICAgICAgICAgaWYoZXApe2VwLnRleHRDb250ZW50PWZSKGQyLnByZWNvX2F0dWFsKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQogICAgICAgIH0KICAgICAgfWNhdGNoKGUyKXt9CiAgICB9CiAgfQp9CgpmdW5jdGlvbiBleHBhbmRBbGwoKXsKICBjb25zdCBidG49ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0bi1leHBhbmQnKTsKICBjb25zdCBzZWdzPVsnZmluJywncGV0JywnbWluJywnbWF0JywndXRpJywnY2MnLCdjbicsJ3NhdScsJ2luZCcsJ3RpdCddOwogIGNvbnN0IGFueU9wZW49c2Vncy5zb21lKGlkPT5kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2ItJytpZCk/LnN0eWxlLmRpc3BsYXk9PT0nYmxvY2snKTsKICBzZWdzLmZvckVhY2goaWQ9PnsKICAgIGNvbnN0IGI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NiLScraWQpLGE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLScraWQpOwogICAgaWYoIWIpcmV0dXJuOwogICAgaWYoYW55T3Blbil7Yi5zdHlsZS5kaXNwbGF5PSdub25lJztpZihhKWEudGV4dENvbnRlbnQ9J+KWvCc7fQogICAgZWxzZXsKICAgICAgYi5zdHlsZS5kaXNwbGF5PSdibG9jayc7aWYoYSlhLnRleHRDb250ZW50PSfilrInOwogICAgICBpZighYi5kYXRhc2V0Lmwpe2IuZGF0YXNldC5sPScxJztsb2FkU2VnKGlkKTt9CiAgICB9CiAgfSk7CiAgaWYoYnRuKWJ0bi50ZXh0Q29udGVudD1hbnlPcGVuPycrIEV4cGFuZGlyIFRvZG9zJzon4oiSIFJlY29saGVyIFRvZG9zJzsKfQpmdW5jdGlvbiB0b2dQb3MoaWQpewogIGNvbnN0IGJvZHk9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JvZHktJytpZCk7CiAgY29uc3QgYXJyPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci0nK2lkKTsKICBpZighYm9keSlyZXR1cm47CiAgY29uc3Qgb3Blbj1ib2R5LmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpOwogIGJvZHkuY2xhc3NMaXN0LnRvZ2dsZSgnb3BlbicsIW9wZW4pOwogIGlmKGFycilhcnIudGV4dENvbnRlbnQ9b3Blbj8n4pa2Jzon4pa8JzsKfQpmdW5jdGlvbiB0b2dnbGVBbGxQb3MoKXsKICBjb25zdCBpZHM9Wydwb3MtcHQnLCdwb3MtdmwnLCdwb3MtYTMnLCdwb3MtYTNiJywncG9zLXJ4JywncG9zLWJiJ107CiAgY29uc3QgYnRuPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidG4tYWxsLXBvcycpOwogIGNvbnN0IGFueU9wZW49aWRzLnNvbWUoaWQ9PmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdib2R5LScraWQpPy5jbGFzc0xpc3QuY29udGFpbnMoJ29wZW4nKSk7CiAgaWRzLmZvckVhY2goaWQ9PnsKICAgIGNvbnN0IGJvZHk9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JvZHktJytpZCk7CiAgICBjb25zdCBhcnI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FyLScraWQpOwogICAgaWYoYm9keSl7Ym9keS5jbGFzc0xpc3QudG9nZ2xlKCdvcGVuJywhYW55T3Blbik7aWYoYXJyKWFyci50ZXh0Q29udGVudD1hbnlPcGVuPyfilrYnOifilrwnO30KICB9KTsKICBpZihidG4pYnRuLnRleHRDb250ZW50PWFueU9wZW4/J+KIkiBSZWNvbGhlciBUb2Rhcyc6JysgRXhwYW5kaXIgVG9kYXMnOwp9CmZ1bmN0aW9uIHRvZ0luZChpZCl7CiAgY29uc3QgYm9keT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZC13cmFwJyk7CiAgY29uc3QgYXJyPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci1pbmQtJytpZCk7CiAgaWYoIWJvZHkpcmV0dXJuOwogIGNvbnN0IG9wZW49Ym9keS5jbGFzc0xpc3QuY29udGFpbnMoJ29wZW4nKTsKICBib2R5LmNsYXNzTGlzdC50b2dnbGUoJ29wZW4nLCFvcGVuKTsKICBpZihhcnIpYXJyLnRleHRDb250ZW50PW9wZW4/J+KWtic6J+KWvCc7Cn0KZnVuY3Rpb24gdG9nZ2xlQWxsSW5kKCl7CiAgY29uc3QgaWRzPVsncGV0cjQnLCd2YWxlMycsJ2JiYXMzJywnYXhpYTMnLCdyb3hvMzQnXTsKICBjb25zdCBidG49ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0bi1hbGwtaW5kJyk7CiAgY29uc3QgYW55T3Blbj1pZHMuc29tZShpZD0+ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQrJy1pbmQtd3JhcCcpPy5jbGFzc0xpc3QuY29udGFpbnMoJ29wZW4nKSk7CiAgaWRzLmZvckVhY2goaWQ9PnsKICAgIGNvbnN0IGJvZHk9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQrJy1pbmQtd3JhcCcpOwogICAgY29uc3QgYXJyPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhci1pbmQtJytpZCk7CiAgICBpZihib2R5KXtib2R5LmNsYXNzTGlzdC50b2dnbGUoJ29wZW4nLCFhbnlPcGVuKTtpZihhcnIpYXJyLnRleHRDb250ZW50PWFueU9wZW4/J+KWtic6J+KWvCc7fQogIH0pOwogIGlmKGJ0bilidG4udGV4dENvbnRlbnQ9YW55T3Blbj8nKyBFeHBhbmRpciBUb2Rvcyc6J+KIkiBSZWNvbGhlciBUb2Rvcyc7Cn0KYXN5bmMgZnVuY3Rpb24gZkhMKCl7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pOwogICAgaWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBjb25zdCBicD1wYXJzZUZsb2F0KGQuQlRDfHwwKTsKICAgIGlmKGJwPjApe0UoJ2J0Yy1wJyxmVShicCkpO0NoKCdidGMtYycsYnAsYnAqMC45OSwndScpO30KICAgIHRyeXsKICAgICAgY29uc3QgcjI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnLGRleDoneHl6J30pfSk7CiAgICAgIGlmKHIyLm9rKXtjb25zdCBkMj1hd2FpdCByMi5qc29uKCk7CiAgICAgICAgaWYoZDJbJ3h5ejpDTCddKUUoJ2NsLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q0wnXSkudG9GaXhlZCgyKSk7CiAgICAgICAgaWYoZDJbJ3h5ejpHT0xEJ10pRSgnZ29sZC1wJywnJCcrTnVtYmVyKGQyWyd4eXo6R09MRCddKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTsKICAgICAgICBpZihkMlsneHl6OlNJTFZFUiddKUUoJ3NpbHZlci1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OlNJTFZFUiddKS50b0ZpeGVkKDIpKTsKICAgICAgICBpZihkMlsneHl6OkNPUFBFUiddKUUoJ2NvcHBlci1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OkNPUFBFUiddKS50b0ZpeGVkKDMpKTt9CiAgICB9Y2F0Y2goZSl7fQogIH1jYXRjaChlKXt9Cn0KYXN5bmMgZnVuY3Rpb24gZlRWKCl7CiAgY29uc3Qgb3V0PXt9OwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL3R2L2JyYXppbCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2VyczpbJ0JNRkJPVkVTUEE6UEVUUjQnLCdCTUZCT1ZFU1BBOklUVUI0JywnQk1GQk9WRVNQQTpWQUxFMycsJ0JNRkJPVkVTUEE6QkJEQzQnLCdCTUZCT1ZFU1BBOkFCRVYzJywnQk1GQk9WRVNQQTpCQkFTMycsJ0JNRkJPVkVTUEE6V0VHRTMnLCdCTUZCT1ZFU1BBOklCT1YnXX0sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTsKICAgIGlmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7KGQuZGF0YXx8W10pLmZvckVhY2goeD0+e2NvbnN0W2MsY2FdPXguZHx8W107aWYoYyE9bnVsbClvdXRbeC5zXT17cDpjLHY6Yy0oY2F8fDApfTt9KTt9CiAgfWNhdGNoKGUpe30KICB0cnl7Y29uc3QgcnI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYocnIub2spe2NvbnN0IGRkPWF3YWl0IHJyLmpzb24oKTtpZihkZC5wcmVjb19hdHVhbCl7RSgncm94bzM0cS1wJyxmUihkZC5wcmVjb19hdHVhbCkpO0NoKCdyb3hvMzRxLWMnLGRkLnByZWNvX2F0dWFsLChkZC5wcmVjb19hbnRlcmlvcnx8ZGQucHJlY29fYXR1YWwqMC45OSksJ3InKTt9fX1jYXRjaChlKXt9CiAgcmV0dXJuIG91dDsKfQphc3luYyBmdW5jdGlvbiBmRnV0KCl7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2Z1dHVyZXMnKTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZGdW5kKCl7CiAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vZmFwaS5iaW5hbmNlLmNvbS9mYXBpL3YxL3ByZW1pdW1JbmRleD9zeW1ib2w9QlRDVVNEVCcpO2lmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7RSgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlfHwwKSoxMDApLnRvRml4ZWQoNCkrJyUnKTtyZXR1cm47fX1jYXRjaChlKXt9CiAgdHJ5e2NvbnN0IHIyPWF3YWl0IGZldGNoKEIrJy9iaW5hbmNlL2Z1bmRpbmcnKTtpZighcjIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgcjIuanNvbigpO2lmKGQubGFzdEZ1bmRpbmdSYXRlKUUoJ2J0Yy1mdW5kJywocGFyc2VGbG9hdChkLmxhc3RGdW5kaW5nUmF0ZSkqMTAwKS50b0ZpeGVkKDQpKyclJyk7fWNhdGNoKGUpe30KfQpmdW5jdGlvbiBkb01hY3JvKHR2LGZ0KXsKICBbWydQRVRSNCcsJ3BldHI0cSddLFsnSVRVQjQnLCdpdHViNHEnXSxbJ1ZBTEUzJywndmFsZTNxJ10sWydCQkRDNCcsJ2JiZGM0cSddLFsnQUJFVjMnLCdhYmV2M3EnXSxbJ0JCQVMzJywnYmJhczNxJ10sWydXRUdFMycsJ3dlZ2UzcSddXS5mb3JFYWNoKChbdCxpZF0pPT57CiAgICBjb25zdCBkPXR2WydCTUZCT1ZFU1BBOicrdF07aWYoZCl7RShpZCsnLXAnLGZSKGQucCkpO0NoVGJsKGlkKyctdicsaWQrJy1jJyxkLnAsZC52LCdyJyk7fQogIH0pOwogIGNvbnN0IGliPXR2WydCTUZCT1ZFU1BBOklCT1YnXTtpZihpYil7RSgnaWJvdi1wJyxmUChpYi5wKSk7Q2hUYmwoJ2lib3YtdicsJ2lib3YtYycsaWIucCxpYi52LCdwJyk7fQogIGlmKGZ0KXsKICAgIGNvbnN0IGFmPShpZCx2KT0+e2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKGUpe2UudGV4dENvbnRlbnQ9djtlLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9fTsKICAgIGlmKGZ0LmRqaT8ucHJpY2Upe2FmKCdkamktcCcsZlAoZnQuZGppLnByaWNlKSk7Q2hUYmwoJ2RqaS12JywnZGppLWMnLGZ0LmRqaS5wcmljZSxmdC5kamkucHJldiwncCcpO30KICAgIGlmKGZ0LmVzZj8ucHJpY2Upe2FmKCdlc2YtcCcsZlAoZnQuZXNmLnByaWNlKSk7Q2hUYmwoJ2VzZi12JywnZXNmLWMnLGZ0LmVzZi5wcmljZSxmdC5lc2YucHJldiwncCcpO30KICAgIGlmKGZ0Lm5xZj8ucHJpY2Upe2FmKCducWYtcCcsZlAoZnQubnFmLnByaWNlKSk7Q2hUYmwoJ25xZi12JywnbnFmLWMnLGZ0Lm5xZi5wcmljZSxmdC5ucWYucHJldiwncCcpO30KICAgIGlmKGZ0Lndpbj8ucHJpY2Upe2FmKCd3aW4tcCcsZlAoZnQud2luLnByaWNlKSk7Q2hUYmwoJ3dpbi12Jywnd2luLWMnLGZ0Lndpbi5wcmljZSxmdC53aW4ucHJldiwncCcpO30KICAgIGlmKGZ0LnZpeD8ucHJpY2Upe2FmKCd2aXgtcCcsTnVtYmVyKGZ0LnZpeC5wcmljZSkudG9GaXhlZCgyKSk7Q2hUYmwoJ3ZpeC12Jywndml4LWMnLGZ0LnZpeC5wcmljZSxmdC52aXgucHJldiwndScpO30KICAgIGlmKGZ0LmR4eT8ucHJpY2Upe2FmKCdkeHktcCcsTnVtYmVyKGZ0LmR4eS5wcmljZSkudG9GaXhlZCgyKSk7Q2hUYmwoJ2R4eS12JywnZHh5LWMnLGZ0LmR4eS5wcmljZSxmdC5keHkucHJldiwndScpO30KICAgIGlmKGZ0LnVzZD8ucHJpY2Upe2FmKCd1c2QtcCcsZlIoZnQudXNkLnByaWNlKSk7Q2hUYmwoJ3VzZC12JywndXNkLWMnLGZ0LnVzZC5wcmljZSxmdC51c2QucHJldnx8ZnQudXNkLnByaWNlLCdyJyk7fQogIH0KfQpmdW5jdGlvbiBkb1Bvcyh0dil7CiAgY29uc3QgcHQ9dHZbJ0JNRkJPVkVTUEE6UEVUUjQnXTtjb25zdCBwcD1wdD8ucHx8NDAscHY9cHQ/LnZ8fDQwOwogIEUoJ3B0LXAnLGZSKHBwKSk7Q2goJ3B0LWMnLHBwLHB2LCdyJyk7CiAgY29uc3QgcGQ9cHAtMzAuODU7RSgncHQtaXRtJywocGQ+PTA/JysgUiQgJzonLSBSJCAnKStNYXRoLmFicyhwZCkudG9GaXhlZCgyKSsnICcrKHBkPj0wPydhY2ltYSc6J2FiYWl4bycpKycgZG8gc3RyaWtlJyk7CiAgY29uc3Qgdmw9dHZbJ0JNRkJPVkVTUEE6VkFMRTMnXTtjb25zdCB2cD12bD8ucHx8NzgsdnY9dmw/LnZ8fDc4OwogIEUoJ3ZsLXAnLGZSKHZwKSk7Q2goJ3ZsLWMnLHZwLHZ2LCdyJyk7CiAgY29uc3QgdmQ9dnAtNTcuNDA7RSgndmwtaXRtJywodmQ+PTA/JysgUiQgJzonLSBSJCAnKStNYXRoLmFicyh2ZCkudG9GaXhlZCgyKSsnICcrKHZkPj0wPydhY2ltYSc6J2FiYWl4bycpKycgZG8gc3RyaWtlJyk7CiAgY29uc3QgY2Q9KGRzLGVpZCk9Pntjb25zdCB2PW5ldyBEYXRlKGRzKSxkPU1hdGgubWF4KDAsTWF0aC5jZWlsKCh2LW5ldyBEYXRlKCkpLzg2NGU1KSksZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChlaWQpO2lmKGUpZS50ZXh0Q29udGVudD1kO307CiAgY2QoJzIwMjYtMTItMTcnLCdwdC1kaWFzJyk7Y2QoJzIwMjctMDItMTgnLCd2bC1kaWFzJyk7Y2QoJzIwMjYtMDktMTQnLCdhMy1kaWFzJyk7Y2QoJzIwMjYtMTAtMDInLCdhM2ItZGlhcycpO2NkKCcyMDI2LTA3LTE2JywncngtZGlhcycpOwogIHNldFRpbWVvdXQoYXN5bmMoKT0+ewogICAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvQVhJQTMuU0EnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZighZC5wcmVjb19hdHVhbClyZXR1cm47CiAgICAgIGNvbnN0IHA9ZC5wcmVjb19hdHVhbDtFKCdhMy1wJyxmUihwKSk7RSgnYTNiLXAnLGZSKHApKTsKICAgICAgY29uc3Qga0E9NDMuNTEsa3VBPTY4Ljc2LGtCPTQwLjUyLGt1Qj02Mi44MTsKICAgICAgY29uc3QgZEE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzLWtkbycpO2lmKGRBKWRBLnRleHRDb250ZW50PSgocC1rQSkvcCoxMDApLnRvRml4ZWQoMSkrJyUgYWNpbWEgZG8gS0RPJzsKICAgICAgY29uc3QgdUE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzLWt1bycpO2lmKHVBKXVBLnRleHRDb250ZW50PSgoa3VBLXApL3AqMTAwKS50b0ZpeGVkKDEpKyclIHBhcmEgbyBLVU8nOwogICAgICBjb25zdCBzQT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTMtc3QnKTtpZihzQSl7c0EudGV4dENvbnRlbnQ9cDw9a0E/J/CflLQgS0RPIEFUSU5HSURPJzpwPj1rdUE/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NBLmNsYXNzTmFtZT0nc3YgJysocDw9a0F8fHA+PWt1QT8nd2Fybic6J29rJyk7fQogICAgICBjb25zdCBkQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYTNiLWtkbycpO2lmKGRCKWRCLnRleHRDb250ZW50PSgocC1rQikvcCoxMDApLnRvRml4ZWQoMSkrJyUgYWNpbWEgZG8gS0RPJzsKICAgICAgY29uc3QgdUI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzYi1rdW8nKTtpZih1Qil1Qi50ZXh0Q29udGVudD0oKGt1Qi1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJzsKICAgICAgY29uc3Qgc0I9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzYi1zdCcpO2lmKHNCKXtzQi50ZXh0Q29udGVudD1wPD1rQj8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1Qj8n4pqgIEtVTyBBVElOR0lETyc6J+KchSBObyByYW5nZSc7c0IuY2xhc3NOYW1lPSdzdiAnKyhwPD1rQnx8cD49a3VCPyd3YXJuJzonb2snKTt9CiAgICB9Y2F0Y2goZSl7fQogIH0sMjAwMCk7CiAgc2V0VGltZW91dChhc3luYygpPT57CiAgICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy9ST1hPMzQuU0EnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZighZC5wcmVjb19hdHVhbClyZXR1cm47CiAgICAgIGNvbnN0IHA9ZC5wcmVjb19hdHVhbDtFKCdyeC1wJyxmUihwKSk7CiAgICAgIGNvbnN0IGl0bT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtaXRtJyk7CiAgICAgIGNvbnN0IGRpc3Q9cC0xMC41MDsKICAgICAgaWYoaXRtKWl0bS50ZXh0Q29udGVudD0oZGlzdD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKGRpc3QpLnRvRml4ZWQoMikrJyAnKyhkaXN0Pj0wPydhY2ltYSAoSVRNIOKaoCknOidhYmFpeG8gKE9UTSDinIUpJykrJyBkbyBzdHJpa2UnOwogICAgICBjb25zdCBkZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngta2RvJyk7aWYoZGUpZGUudGV4dENvbnRlbnQ9KChwLTEwLjUwKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBkbyBzdHJpa2UnOwogICAgICBjb25zdCBzZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtc3QnKTtpZihzZSl7c2UudGV4dENvbnRlbnQ9cDw9MTAuNTA/J+KchSBPVE0g4oCUIGFiYWl4byBkbyBzdHJpa2UnOifimqAgSVRNIOKAlCBhY2ltYSBkbyBzdHJpa2UnO3NlLmNsYXNzTmFtZT0nc3YgJysocDw9MTAuNTA/J29rJzonaXRtJyk7fQogICAgfWNhdGNoKGUpe30KICB9LDMwMDApOwp9CmFzeW5jIGZ1bmN0aW9uIE1DKHRrLHNrLGRpYXMsbElkLHJJZCxzSWQsdklkLGlJZCxydElkKXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeSh7dGlja2VyOnRrLGtfY2FsbDpzayxrX3B1dDpzayx0X2RheXM6ZGlhcyxuOjUwMDB9KX0pOwogICAgaWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQobElkKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChySWQpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGNvbnN0IHByb2I9TnVtYmVyKGQucHJvYl9jYWxsX2V4ZXJjaWRhfHwwKTsKICAgIGNvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChzSWQpO3NFbC50ZXh0Q29udGVudD1wcm9iLnRvRml4ZWQoMSkrJyUnOwogICAgc0VsLmNsYXNzTmFtZT0naXYgJysocHJvYjwxNT8nb2snOnByb2I8MzA/J3dhcm4nOidkb3duJyk7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCh2SWQpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaUlkKS50ZXh0Q29udGVudD0nVm9sLmhpc3QuICcrZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSDCtyAnKyhwcm9iPDE1PyfinIUgUmlzY28gYmFpeG8gZGUgZXhlcmPDrWNpbyc6J+KaoCBNb25pdG9yYXIgcG9zacOnw6NvJyk7CiAgICBpZihydElkKUUocnRJZCxwcm9iLnRvRml4ZWQoMSkrJyUnKTsKICB9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQobElkKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwndGltZW91dCcpO30KfQphc3luYyBmdW5jdGlvbiBNQ0IodGssZW4sa2Qsa3UsZGlhcyxwZngpewogIHRyeXsKICAgIGNvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9tb250ZWNhcmxvL2JhcnJpZXInLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcjp0ayxlbnRyeTplbixrZG86a2Qsa3VvOmt1LHRfZGF5czpkaWFzLG46MzAwMH0pfSk7CiAgICBpZighci5vayl0aHJvdyAwO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoZC5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZC5lcnJvcik7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1sJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtcicpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLW5iJykudGV4dENvbnRlbnQ9ZC5wcm9iX3NlbV9iYXJyZWlyYS50b0ZpeGVkKDEpKyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLWt1JykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2FsdGEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1rZCcpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9iYWl4YS50b0ZpeGVkKDEpKyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLXZvJykudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1pJykudGV4dENvbnRlbnQ9J1IkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua2RvKycgwrcgS1VPIFIkICcrZC5rdW87CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLWwnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwndGltZW91dCcpO30KfQphc3luYyBmdW5jdGlvbiBNQ1IodGssZW4sa2QsZGlhcyl7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcjp0ayxrX2NhbGw6ZW4sa19wdXQ6ZW4sdF9kYXlzOmRpYXMsa25vY2tfZG93bjprZCxuOjUwMDB9KX0pOwogICAgaWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWwnKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtcicpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGNvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtcycpO3NFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX3N1Y2Vzc28pLnRvRml4ZWQoMSkrJyUnO3NFbC5jbGFzc05hbWU9J2l2ICcrKGQucHJvYl9zdWNlc3NvPjcwPydvayc6ZC5wcm9iX3N1Y2Vzc28+NTA/J3dhcm4nOidkb3duJyk7CiAgICBjb25zdCBjRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWMnKTtpZihjRWwpY0VsLnRleHRDb250ZW50PU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYSkudG9GaXhlZCgxKSsnJSc7CiAgICBjb25zdCBrRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWsnKTtpZihrRWwpa0VsLnRleHRDb250ZW50PWQucHJvYl9rZG9fYXRpbmdpZG8hPW51bGw/TnVtYmVyKGQucHJvYl9rZG9fYXRpbmdpZG8pLnRvRml4ZWQoMSkrJyUnOifigJQnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXYnKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1pJykudGV4dENvbnRlbnQ9J1IkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua25vY2tfZG93bjsKICB9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLWwnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwndGltZW91dCcpO30KfQphc3luYyBmdW5jdGlvbiBmSW5kKHRrKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDMwMDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzLycrdGsse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkJUQ0koKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDE1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9idGMvaW5kaWNhdG9ycycse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkJUQ0MoKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDE1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEIrJy9idGMvY3ljbGUnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZGRygpewogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2ZlYXJncmVlZCcpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgY29uc3Qgdj1kLnZhbHVlfHw1MCxjbHM9djw9MjU/J3ZhcigtLXJlZCknOnY8PTQ1Pyd2YXIoLS13YXJuKSc6djw9NzU/J3ZhcigtLWFjY2VudCknOid2YXIoLS1ncmVlbiknOwogICAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ZnLWFyZWEnKTsKICAgIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE2cHgiPjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjhweDtmb250LXdlaWdodDo2MDA7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHgiPvCfmLEgRmVhciAmIEdyZWVkIEluZGV4PC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTRweCI+PGRpdiBzdHlsZT0iZm9udC1zaXplOjM4cHg7Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOicrY2xzKyciPicrdisnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOicrY2xzKyciPicrKGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKSsnPC9kaXY+PC9kaXY+PC9kaXY+JzsKICAgIEUoJ2ZnLXZhbCcsU3RyaW5nKHYpKTtFKCdmZy1sYmwnLGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKTsKICAgIHRyeXtjb25zdCByYj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pO2lmKHJiLm9rKXtjb25zdCBkYj1hd2FpdCByYi5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkYi5CVEN8fDApO2lmKGJwPjApe0UoJ2J0Yy1pbmQtcCcsJyQnK051bWJlcihicCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7RSgnYnRjLXAnLGZVKGJwKSk7fX19Y2F0Y2goZTIpe30KICB9Y2F0Y2goZSl7fQp9CmZ1bmN0aW9uIHJuZEluZChpZCxkYXRhKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZCcpO2lmKCFlbClyZXR1cm47CiAgaWYoIWRhdGEpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7cGFkZGluZzoxMnB4O2ZvbnQtc2l6ZToxM3B4Ij7ij7MgU2VtIHJlc3Bvc3RhIOKAlCBjbGlxdWUg4oa7PC9kaXY+JztyZXR1cm47fQogIGlmKGRhdGEuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tcmVkKTtwYWRkaW5nOjEycHg7Zm9udC1zaXplOjEzcHgiPuKaoCAnK2RhdGEuZXJyb3IrJzwvZGl2Pic7cmV0dXJuO30KICBjb25zdCBpbmRzPWRhdGEuaW5kaWNhZG9yZXN8fFtdLHNjPU51bWJlcihkYXRhLnNjb3JlX3RvdGFsfHwwKSxwcmVjbz1kYXRhLnByZWNvX2F0dWFsLGdyYWhhbT1kYXRhLmdyYWhhbV92YWx1ZSx1cD1kYXRhLnVwc2lkZV9ncmFoYW0sc2V0b3I9ZGF0YS5zZXRvcnx8Jyc7CiAgY29uc3Qgc2MyPXNjPj02NT8ndmFyKC0tZ3JlZW4pJzpzYz49NDA/J3ZhcigtLXdhcm4pJzondmFyKC0tcmVkKScsc2w9c2M+PTY1PydDb21wcmEg4payJzpzYz49NDA/J05ldXRybyDihpInOidWZW5kYSDilrwnOwogIGxldCBoPSc8ZGl2IGNsYXNzPSJzY2IiPicrCiAgICAnPGRpdiBjbGFzcz0ic2NjIj48ZGl2IGNsYXNzPSJzY20iPlNjb3JlPC9kaXY+PGRpdiBjbGFzcz0ic2NuIiBzdHlsZT0iY29sb3I6JytzYzIrJyI+JytzYysnPC9kaXY+PGRpdiBjbGFzcz0ic2NsIiBzdHlsZT0iY29sb3I6JytzYzIrJyI+JytzbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJzY2MiPjxkaXYgY2xhc3M9InNjbSI+Q290YcOnw6NvPC9kaXY+PGRpdiBjbGFzcz0ic2N2Ij4nKyhwcmVjbz8nUiQgJytOdW1iZXIocHJlY28pLnRvRml4ZWQoMik6J+KAlCcpKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY3MiPicrc2V0b3IrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0ic2NjIj48ZGl2IGNsYXNzPSJzY20iPkdyYWhhbSBWSjwvZGl2PjxkaXYgY2xhc3M9InNjdiIgc3R5bGU9ImNvbG9yOicrKHVwJiZ1cD4wPyd2YXIoLS1ncmVlbiknOid2YXIoLS1yZWQpJykrJyI+JysoZ3JhaGFtPydSJCAnK051bWJlcihncmFoYW0pLnRvRml4ZWQoMik6J+KAlCcpKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY3MiIHN0eWxlPSJjb2xvcjonKyh1cCYmdXA+MD8ndmFyKC0tZ3JlZW4pJzondmFyKC0tcmVkKScpKyciPicrKHVwIT1udWxsPyh1cD4wPycrJzonJykrdXArJyUgdXBzaWRlJzon4oCUJykrJzwvZGl2PjwvZGl2PicrCiAgICAnPC9kaXY+JzsKICBpbmRzLmZvckVhY2goaT0+ewogICAgY29uc3Qgcz1pLnNpbmFsfHwnJyxjbHM9cz09PSdBbHRhJ3x8cz09PSdTb2JyZXZlbmRhJz8nb2snOnM9PT0nQmFpeGEnfHxzPT09J1NvYnJlY29tcHJhJz8nZG93bic6J3dhcm4nLGFyPWNscz09PSdvayc/J+KWsic6Y2xzPT09J2Rvd24nPyfilrwnOifihpInOwogICAgaCs9JzxkaXYgY2xhc3M9ImlyIj48ZGl2IGNsYXNzPSJpcnQiPjxzcGFuIGNsYXNzPSJpcm4iPicrKGkubm9tZXx8JycpKyc8L3NwYW4+PHNwYW4gY2xhc3M9ImlydiAnK2NscysnIj4nKyhpLnZhbG9yIT1udWxsP2kudmFsb3I6J+KAlCcpKycgJythcisnPC9zcGFuPjwvZGl2PicrKGkuZXhwbGljYWNhbz8nPGRpdiBjbGFzcz0iaXJlIj4nK2kuZXhwbGljYWNhbysnPC9kaXY+JzonJykrJzwvZGl2Pic7CiAgfSk7CiAgZWwuaW5uZXJIVE1MPWh8fCc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMHB4Ij5TZW0gaW5kaWNhZG9yZXM8L2Rpdj4nOwp9CmZ1bmN0aW9uIHJuZEJUQ0koZCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1pbmQtYXJlYScpO2lmKCFlbHx8IWQpcmV0dXJuOwogIGlmKGQuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7cGFkZGluZzoxMnB4O2ZvbnQtc2l6ZToxM3B4Ij7ij7MgJytkLmVycm9yKyc8L2Rpdj4nO3JldHVybjt9CiAgbGV0IGg9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4Ij4nOwogIGlmKGQucnNpX3NlbWFuYWwhPW51bGwpe2NvbnN0IHJ2PWQucnNpX3NlbWFuYWwscmM9cnY8MzA/J29rJzpydj43MD8nZG93bic6J3dhcm4nO2grPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iaXYgJytyYysnIj4nK3J2LnRvRml4ZWQoMSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JysocnY8MzA/J1NvYnJldmVuZGEg4pqhJzpydj43MD8nU29icmVjb21wcmEg4pqgJzonTmV1dHJvJykrJzwvZGl2PjwvZGl2Pic7RSgnYnRjLXJzaScscnYudG9GaXhlZCgxKSk7fQogIGlmKGQubW01MF9zZW1hbmFsKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1NIDUwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4kJytOdW1iZXIoZC5tbTUwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZC5tbTIwMF9zZW1hbmFsKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1NIDIwMCBzZW0uPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JCcrTnVtYmVyKGQubW0yMDBfc2VtYW5hbCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PC9kaXY+JzsKICBpZihkLm1hY2RfaGlzdG9ncmFtIT1udWxsKXtjb25zdCBtaD1kLm1hY2RfaGlzdG9ncmFtO2grPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1BQ0QgSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiAnKyhtaD4wPydvayc6J2Rvd24nKSsnIj4nK051bWJlcihtaCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nKyhtaD4wPydNb21lbnR1bSDilrInOidNb21lbnR1bSDilrwnKSsnPC9kaXY+PC9kaXY+Jzt9CiAgaWYoZC5vYnZfdHJlbmQpaCs9JzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+T0JWPC9kaXY+PGRpdiBjbGFzcz0iaXYgJysoZC5vYnZfdHJlbmQ9PT0nc3ViaW5kbyc/J29rJzonZG93bicpKyciPicrZC5vYnZfdHJlbmQrJzwvZGl2PjwvZGl2Pic7CiAgaCs9JzwvZGl2Pic7ZWwuaW5uZXJIVE1MPWg7CiAgaWYoZC5wcmljZSlFKCdidGMtaW5kLXAnLCckJytOdW1iZXIoZC5wcmljZSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7Cn0KZnVuY3Rpb24gcm5kQlRDQyhkKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWN5Y2xlLWFyZWEnKTtpZighZWx8fCFkfHxkLmVycm9yKXJldHVybjsKICBjb25zdCBmVTI9dj0+dj8nJCcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CiAgZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEwcHgiPicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5NVlJWIFotU2NvcmU8L2Rpdj48ZGl2IGNsYXNzPSJpdiAnKyhkLm12cnZfenNjb3JlPy52YWx1ZTwxPydvayc6ZC5tdnJ2X3pzY29yZT8udmFsdWU8Mz8nd2Fybic6J2Rvd24nKSsnIj4nK2QubXZydl96c2NvcmU/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5tdnJ2X3pzY29yZT8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5OVVBMPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JysoKGQubnVwbD8udmFsdWV8fDApKjEwMCkudG9GaXhlZCgwKSsnJTwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JytkLm51cGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHVlbGwgTXVsdGlwbGU8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nK2QucHVlbGw/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5wdWVsbD8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj4yMDBXIE1BPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JytmVTIoZC5tYTIwMHcpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrKGQubWEyMDB3X3BjdD8nKycrZC5tYTIwMHdfcGN0KyclJzonJykrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5SYWluYm93IEJhbmQ8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nKyhkLnJhaW5ib3c/LmJhbmR8fCfigJQnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlBpIEN5Y2xlIERpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siPicrZlUyKGQucGlfY3ljbGU/LmRpc3RhbmNlKSsnPC9kaXY+PC9kaXY+JysKICAgICc8L2Rpdj48ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweDtmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjYwMCI+JysoZC5waV9jeWNsZT8uc2lnbmFsfHwnJykrJzwvZGl2Pic7Cn0KYXN5bmMgZnVuY3Rpb24gbG9hZEluZCgpewogIGNvbnN0IHd0PShwLG1zLGZiKT0+UHJvbWlzZS5yYWNlKFtwLG5ldyBQcm9taXNlKHI9PnNldFRpbWVvdXQoKCk9PnIoZmIpLG1zKSldKTsKICBjb25zdFtiaSxiY109YXdhaXQgUHJvbWlzZS5hbGwoW3d0KGZCVENJKCksMTUwMDAse2Vycm9yOidUaW1lb3V0IOKAlCBjbGlxdWUg4oa7J30pLHd0KGZCVENDKCksMTUwMDAsbnVsbCldKTsKICBybmRCVENJKGJpKTtybmRCVENDKGJjKTtmRkcoKTsKICBjb25zdCBzdG9ja3M9W1snUEVUUjQuU0EnLCdwZXRyNCddLFsnVkFMRTMuU0EnLCd2YWxlMyddLFsnQkJBUzMuU0EnLCdiYmFzMyddLFsnQVhJQTMuU0EnLCdheGlhMyddLFsnUk9YTzM0LlNBJywncm94bzM0J11dOwogIGNvbnN0IHJlcz1hd2FpdCBQcm9taXNlLmFsbChzdG9ja3MubWFwKChbdF0pPT53dChmSW5kKHQpLDMwMDAwLHtlcnJvcjonVGltZW91dCAzMHMnfSkpKTsKICBzdG9ja3MuZm9yRWFjaCgoWyxpZF0saSk9PnJuZEluZChpZCxyZXNbaV0pKTsKfQphc3luYyBmdW5jdGlvbiBybCh0ayl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodGsrJy1pbmQnKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDFzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+JzsKICBjb25zdCBtPXtwZXRyNDonUEVUUjQuU0EnLHZhbGUzOidWQUxFMy5TQScsYmJhczM6J0JCQVMzLlNBJyxheGlhMzonQVhJQTMuU0EnLHJveG8zNDonUk9YTzM0LlNBJ307CiAgcm5kSW5kKHRrLGF3YWl0IGZJbmQobVt0a10pKTsKfQpjb25zdCBGTEFHUz17J1VTRCc6J/Cfh7rwn4e4JywnVVMnOifwn4e68J+HuCcsJ0JSTCc6J/Cfh6fwn4e3JywnQlInOifwn4en8J+HtycsJ0VVUic6J/Cfh6rwn4e6JywnRVUnOifwn4eq8J+HuicsJ0dCUCc6J/Cfh6zwn4enJywnQ05ZJzon8J+HqPCfh7MnLCdKUFknOifwn4ev8J+HtScsJ0NBRCc6J/Cfh6jwn4emJywnQVVEJzon8J+HpvCfh7onLCdERSc6J/Cfh6nwn4eqJywnTlpEJzon8J+Hs/Cfh78nLCdDSEYnOifwn4eo8J+HrSd9Owphc3luYyBmdW5jdGlvbiBsb2FkQ2FsKCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbC1hcmVhJyk7CiAgY29uc3Qgc3Q9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbC1zdCcpOwogIGlmKCFlbClyZXR1cm47CiAgZWwuaW5uZXJIVE1MPSc8cCBzdHlsZT0iY29sb3I6Izg4ODtwYWRkaW5nOjIwcHg7dGV4dC1hbGlnbjpjZW50ZXIiPkNhcnJlZ2FuZG8uLi48L3A+JzsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9jYWxlbmRhcicse2NhY2hlOiduby1zdG9yZSd9KTsKICAgIGlmKCFyLm9rKXRocm93IG5ldyBFcnJvcignSFRUUCAnK3Iuc3RhdHVzKTsKICAgIGNvbnN0IGV2cz1hd2FpdCByLmpzb24oKTsKICAgIGlmKGV2cy5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZXZzLmVycm9yKTsKICAgIGlmKHN0KXN0LnRleHRDb250ZW50PWV2cy5sZW5ndGgrJyBldmVudG9zJzsKICAgIGlmKCFldnMubGVuZ3RoKXtlbC5pbm5lckhUTUw9JzxwIHN0eWxlPSJjb2xvcjojODg4O3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlciI+U2VtIGV2ZW50b3M8L3A+JztyZXR1cm47fQogICAgY29uc3QgYnlEPXt9OwogICAgZXZzLmZvckVhY2goZT0+ewogICAgICBjb25zdCBkdD0oZS5kYXRlfHwnJykuc2xpY2UoMCwxMCk7CiAgICAgIGlmKCFieURbZHRdKWJ5RFtkdF09W107CiAgICAgIGJ5RFtkdF0ucHVzaChlKTsKICAgIH0pOwogICAgbGV0IGg9JzxkaXYgc3R5bGU9ImZvbnQtZmFtaWx5Om1vbm9zcGFjZSI+JzsKICAgIE9iamVjdC5rZXlzKGJ5RCkuc29ydCgpLmZvckVhY2goZHQ9PnsKICAgICAgY29uc3QgZD1uZXcgRGF0ZShkdCsnVDEyOjAwOjAwJyk7CiAgICAgIGNvbnN0IGxibD1kLnRvTG9jYWxlRGF0ZVN0cmluZygncHQtQlInLHt3ZWVrZGF5Oidsb25nJyxkYXk6JzItZGlnaXQnLG1vbnRoOidzaG9ydCd9KTsKICAgICAgaCs9JzxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MjBweCI+JzsKICAgICAgaCs9JzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6IzFhMWEyNDtwYWRkaW5nOjhweCAxNHB4O2ZvbnQtc2l6ZToxMXB4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjojN2M2YWY3O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzoxcHg7Ym9yZGVyLWxlZnQ6M3B4IHNvbGlkICM3YzZhZjciPicrbGJsKyc8L2Rpdj4nOwogICAgICBieURbZHRdLmZvckVhY2goZT0+ewogICAgICAgIGNvbnN0IGltcF9jb2xvcj1lLmltcG9ydGFuY2U+PTM/JyNmZjQ0NDQnOicjZmY5ODAwJzsKICAgICAgICBjb25zdCBhY3RfY29sb3I9ZS5zaWduYWw9PT0nYmVhdCc/JyMwMGU2NzYnOmUuc2lnbmFsPT09J21pc3MnPycjZjA2MjkyJzonI2FhYSc7CiAgICAgICAgaCs9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MzBweCA1NXB4IDFmciA0MHB4IDgwcHggODBweDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjhweCAxNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkICMxYTFhMWE7Zm9udC1zaXplOjEzcHgiPic7CiAgICAgICAgaCs9JzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTZweCI+JysoZS5mbGFnfHwn8J+MkCcpKyc8L3NwYW4+JzsKICAgICAgICBoKz0nPHNwYW4gc3R5bGU9ImNvbG9yOiM1NTU7Zm9udC1zaXplOjExcHgiPicrKGUudGltZXx8J+KAlCcpKyc8L3NwYW4+JzsKICAgICAgICBoKz0nPHNwYW4gc3R5bGU9ImNvbG9yOiNkZGQ7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwIiB0aXRsZT0iJytlLmV2ZW50KyciPicrZS5ldmVudCsnPC9zcGFuPic7CiAgICAgICAgaCs9JzxzcGFuIHN0eWxlPSJjb2xvcjonK2ltcF9jb2xvcisnO3RleHQtYWxpZ246Y2VudGVyIj4nKyfil48nLnJlcGVhdChNYXRoLm1pbihlLmltcG9ydGFuY2UsMykpKyc8L3NwYW4+JzsKICAgICAgICBoKz0nPHNwYW4gc3R5bGU9ImNvbG9yOicrYWN0X2NvbG9yKyc7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDAiPicrKGUuYWN0dWFsfHwn4oCUJykrJzwvc3Bhbj4nOwogICAgICAgIGgrPSc8c3BhbiBzdHlsZT0iY29sb3I6IzU1NTt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtc2l6ZToxMXB4Ij4nKyhlLmZvcmVjYXN0fHwn4oCUJykrJzwvc3Bhbj4nOwogICAgICAgIGgrPSc8L2Rpdj4nOwogICAgICB9KTsKICAgICAgaCs9JzwvZGl2Pic7CiAgICB9KTsKICAgIGgrPSc8L2Rpdj4nOwogICAgZWwuaW5uZXJIVE1MPWg7CiAgfWNhdGNoKGUpewogICAgZWwuaW5uZXJIVE1MPSc8cCBzdHlsZT0iY29sb3I6I2YwNjI5MjtwYWRkaW5nOjIwcHgiPkVycm86ICcrZS5tZXNzYWdlKyc8L3A+JzsKICB9Cn0KCmFzeW5jIGZ1bmN0aW9uIG1haW4oKXsKICB0cnl7CiAgICBjb25zdFssdHYsZnRdPWF3YWl0IFByb21pc2UuYWxsKFtmSEwoKSxmVFYoKSxmRnV0KCldKTsKICAgIGNvbnN0IG5vdz1uZXcgRGF0ZSgpLnRvTG9jYWxlVGltZVN0cmluZygncHQtQlInKTsKICAgIEUoJ2xhc3QtdXBkYXRlJywn4oa7ICcrbm93KTtFKCdsYXN0LXVwZGF0ZS10YmwnLG5vdyk7RSgnZm9vdGVyLXRpbWUnLG5vdyk7CiAgICB3aW5kb3cuX2xhc3RUVj10djtkb01hY3JvKHR2LGZ0KTtkb1Bvcyh0dik7CiAgICBzZXRUaW1lb3V0KGZGdW5kLDMwMDApOwogICAgc2V0VGltZW91dChhc3luYygpPT57dHJ5e2NvbnN0W2JpLGJjXT1hd2FpdCBQcm9taXNlLmFsbChbZkJUQ0koKSxmQlRDQygpXSk7aWYoYmkpcm5kQlRDSShiaSk7aWYoYmMpcm5kQlRDQyhiYyk7ZkZHKCk7fWNhdGNoKGUpe319LDUwMDApOwogICAgY29uc3QgaG9qZT1uZXcgRGF0ZSgpOwogICAgY29uc3QgZFA9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTEyLTE3JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRWPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNy0wMi0xOCcpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkQT1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDktMTQnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZEFiPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0xMC0wMicpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkUj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDctMTYnKS1ob2plKS84NjRlNSkpOwogICAgc2V0VGltZW91dCgoKT0+TUMoJ1BFVFI0LlNBJywzMC44NSxkUCwncHQtbWMtbCcsJ3B0LW1jLXInLCdwdC1tYy1zJywncHQtbWMtdicsJ3B0LW1jLWknLCdwdC1tYy1ydCcpLDYwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUMoJ1ZBTEUzLlNBJyw1Ny40MCxkViwndmwtbWMtbCcsJ3ZsLW1jLXInLCd2bC1tYy1zJywndmwtbWMtdicsJ3ZsLW1jLWknLCd2bC1tYy1ydCcpLDEyMDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DQignQVhJQTMuU0EnLDU0LjMxLDQzLjUxLDY4Ljc2LGRBLCdhMycpLDE4MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DQignQVhJQTMuU0EnLDUwLjY1LDQwLjUyLDYyLjgxLGRBYiwnYTNiJyksMjQwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUNSKCdST1hPMzQuU0EnLDEyLjg4LDEwLjUwLGRSKSwzMDAwMCk7CiAgICBjb25zdCBkQkI9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTA4LTIwJyktaG9qZSkvODY0ZTUpKTsKICAgIHNldFRpbWVvdXQoKCk9Pk1DKCdCQkFTMy5TQScsMjEuNjUsZEJCLCdiYi1tYy1sJywnYmItbWMtcicsJ2JiLW1jLXMnLCdiYi1tYy12JywnYmItbWMtaScsJ2JiLW1jLXJ0JyksMzYwMDApOwogICAgLy8gQkJBUzMgY290YcOnw6NvIOKAlCB2aWEgVFYgb3UgZmFsbGJhY2sgL2luZGljYXRvcnMKICAgIGNvbnN0IGJiVFY9dHZbJ0JNRkJPVkVTUEE6QkJBUzMnXTsKICAgIGlmKGJiVFY/LnApewogICAgICBFKCdiYi1wJyxmUihiYlRWLnApKTtDaCgnYmItYycsYmJUVi5wLGJiVFYudnx8YmJUVi5wLCdyJyk7CiAgICAgIGNvbnN0IGQyPWJiVFYucC0yMS42NTsKICAgICAgY29uc3QgaXRtMj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmItaXRtJyk7CiAgICAgIGlmKGl0bTIpe2l0bTIudGV4dENvbnRlbnQ9KGQyPj0wPycrIFIkICc6Jy0gUiQgJykrTWF0aC5hYnMoZDIpLnRvRml4ZWQoMikrJyAnKyhkMj49MD8nYWNpbWEgKElUTSDimqApJzonYWJhaXhvIChPVE0g4pyFKScpKycgZG8gc3RyaWtlJztpdG0yLmNsYXNzTmFtZT0nc3YgJysoZDI+PTA/J2l0bSc6J29rJyk7fQogICAgfSBlbHNlIHsKICAgICAgLy8gVFYgbsOjbyByZXRvcm5vdSBCQkFTMyDigJQgZmFsbGJhY2sKICAgICAgZmV0Y2goQisnL2luZGljYXRvcnMvQkJBUzMuU0EnKS50aGVuKHIyPT5yMi5qc29uKCkpLnRoZW4oZDI9PnsKICAgICAgICBpZihkMi5wcmVjb19hdHVhbCl7CiAgICAgICAgICBFKCdiYi1wJyxmUihkMi5wcmVjb19hdHVhbCkpO0NoKCdiYi1jJyxkMi5wcmVjb19hdHVhbCxkMi5wcmVjb19hbnRlcmlvcnx8ZDIucHJlY29fYXR1YWwqMC45OSwncicpOwogICAgICAgICAgY29uc3QgZGlzdD1kMi5wcmVjb19hdHVhbC0yMS42NTsKICAgICAgICAgIGNvbnN0IGl0bTI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JiLWl0bScpOwogICAgICAgICAgaWYoaXRtMil7aXRtMi50ZXh0Q29udGVudD0oZGlzdD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKGRpc3QpLnRvRml4ZWQoMikrJyAnKyhkaXN0Pj0wPydhY2ltYSAoSVRNIOKaoCknOidhYmFpeG8gKE9UTSDinIUpJykrJyBkbyBzdHJpa2UnO2l0bTIuY2xhc3NOYW1lPSdzdiAnKyhkaXN0Pj0wPydpdG0nOidvaycpO30KICAgICAgICB9CiAgICAgIH0pLmNhdGNoKCgpPT57fSk7CiAgICB9CiAgICBjb25zdCBjZEJCPSgpPT57Y29uc3Qgdj1uZXcgRGF0ZSgnMjAyNi0wOC0yMCcpLGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKSxlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiYi1kaWFzJyk7aWYoZSllLnRleHRDb250ZW50PWQ7fTtjZEJCKCk7CiAgICB3aW5kb3cuX0lMPWZhbHNlOwogIH1jYXRjaChlKXtjb25zb2xlLmVycm9yKGUpO30KfQptYWluKCk7c2V0SW50ZXJ2YWwobWFpbiwxMjAwMDApOwo8L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+Cg==").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
