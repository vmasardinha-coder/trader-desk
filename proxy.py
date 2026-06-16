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
                    dt_brt = dt.astimezone(timezone(timedelta(hours=-3)))
                    time_str = dt_brt.strftime('%H:%M')
                    date_str = dt_brt.strftime('%Y-%m-%d')
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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjUgLS0+CjxodG1sIGxhbmc9InB0LUJSIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5UcmFkZXIgRGVzazwvdGl0bGU+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs2MDA7NzAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Cjpyb290ewogIC0tYmc6IzBkMGQwZDstLWJnMjojMTQxNDE0Oy0tYmczOiMxYzFjMWM7CiAgLS10ZXh0OiNlMGUwZTA7LS1tdXRlZDojNTA1MDUwOy0tYm9yZGVyOiMyNDI0MjQ7CiAgLS1hY2NlbnQ6I2YwYTUwMDstLWdyZWVuOiMwMGM4NTM7LS1yZWQ6I2ZmMTc0NDstLXdhcm46I2ZmOTgwMDstLWJsdWU6IzIxOTZmMwp9CmJvZHl7YmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTNweDtsaW5lLWhlaWdodDoxLjQ7cGFkZGluZzoxNnB4O21heC13aWR0aDo2ODBweDttYXJnaW46MCBhdXRvfQouaGRye2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxNnB4O3BhZGRpbmctYm90dG9tOjEycHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKX0KLmhkci10e2ZvbnQtc2l6ZToxN3B4O2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO2xldHRlci1zcGFjaW5nOjFweH0KLmhkci1ze2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKX0KLnRhYnN7ZGlzcGxheTpmbGV4O2dhcDo0cHg7bWFyZ2luLWJvdHRvbToxNnB4O292ZXJmbG93LXg6YXV0b30KLnRhYntwYWRkaW5nOjdweCAxNnB4O2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y3Vyc29yOnBvaW50ZXI7Zm9udC1zaXplOjEycHg7bGV0dGVyLXNwYWNpbmc6LjVweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3doaXRlLXNwYWNlOm5vd3JhcDtmb250LWZhbWlseTppbmhlcml0O3RyYW5zaXRpb246YWxsIC4xNXN9Ci50YWI6aG92ZXJ7Y29sb3I6dmFyKC0tdGV4dCl9Ci50YWIuYWN0aXZle2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtjb2xvcjojMDAwO2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjcwMH0KLnRhYi1jb250ZW50e2Rpc3BsYXk6bm9uZX0udGFiLWNvbnRlbnQuYWN0aXZle2Rpc3BsYXk6YmxvY2t9Ci5zZWN7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6MnB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMnB4IDAgNnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7bWFyZ2luLWJvdHRvbToxMHB4O2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjZweH0KLnNlYyAuYXtjb2xvcjp2YXIoLS1hY2NlbnQpfQouZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjZweDttYXJnaW4tYm90dG9tOjE0cHh9Ci5jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMXB4IDEwcHh9Ci5jYXJkLmd7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tZ3JlZW4pfS5jYXJkLmJ7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tYmx1ZSl9Ci5jYXJkLnd7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0td2Fybil9LmNhcmQucntib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1yZWQpfQouY2x7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206MnB4fQouY257Zm9udC1zaXplOjEycHg7Zm9udC13ZWlnaHQ6NzAwO21hcmdpbi1ib3R0b206NXB4fQouY3B7Zm9udC1zaXplOjE2cHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLWFjY2VudCl9Ci5jcC5sb2FkaW5ne2NvbG9yOnZhcigtLW11dGVkKTthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZTtmb250LXNpemU6MTJweH0KLmNje2ZvbnQtc2l6ZToxMXB4O21hcmdpbi10b3A6M3B4fQoudXB7Y29sb3I6dmFyKC0tZ3JlZW4pfS5kbntjb2xvcjp2YXIoLS1yZWQpfS5mbHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjN9fQouc2h7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjlweCAxM3B4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7Zm9udC1zaXplOjEycHg7bGV0dGVyLXNwYWNpbmc6LjVweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NXB4O3RyYW5zaXRpb246Ym9yZGVyLWNvbG9yIC4xNXN9Ci5zaDpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tYWNjZW50KTtjb2xvcjp2YXIoLS10ZXh0KX0KLnNiMntkaXNwbGF5Om5vbmU7cGFkZGluZy10b3A6NXB4fQoucGN7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjE0cHg7bWFyZ2luLWJvdHRvbToxMHB4fQoucGx7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi41cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NHB4fQoucHR7Zm9udC1zaXplOjE5cHg7Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOnZhcigtLWFjY2VudCk7bWFyZ2luLWJvdHRvbTozcHh9Ci5wcHtmb250LXNpemU6MjJweDtmb250LXdlaWdodDo3MDB9LnBwLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZToxNnB4fQoucGMye2ZvbnQtc2l6ZToxMnB4O21hcmdpbi1ib3R0b206MTBweH0KLnNie2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZy10b3A6OXB4O21hcmdpbi10b3A6OXB4fQouc3J7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjVweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEycHh9Ci5zbHtjb2xvcjp2YXIoLS1tdXRlZCl9LnN2e3RleHQtYWxpZ246cmlnaHQ7bWF4LXdpZHRoOjU4JX0KLnN2Lm9re2NvbG9yOnZhcigtLWdyZWVuKX0uc3Yud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uc3YuaXRte2NvbG9yOnZhcigtLXJlZCl9Ci5zaWd7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTFweDttYXJnaW4tdG9wOjlweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLnNndHtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzoxcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206N3B4O2NvbG9yOnZhcigtLW11dGVkKX0KLmlie2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo5cHg7dGV4dC1hbGlnbjpjZW50ZXJ9Ci5pbHtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo0cHh9Ci5pdntmb250LXNpemU6MTdweDtmb250LXdlaWdodDo4MDB9Lml2Lm9re2NvbG9yOnZhcigtLWdyZWVuKX0uaXYud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaXYuZG93bntjb2xvcjp2YXIoLS1yZWQpfQouc2Nie2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmciAxZnI7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEwcHh9Ci5zY2N7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjExcHggOXB4O3RleHQtYWxpZ246Y2VudGVyfQouc2Nte2ZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjVweDttYXJnaW4tYm90dG9tOjRweH0KLnNjbntmb250LXNpemU6MjhweDtmb250LXdlaWdodDo4MDA7bGluZS1oZWlnaHQ6MX0KLnNjbHtmb250LXNpemU6MTFweDttYXJnaW4tdG9wOjNweH0KLnNjdntmb250LXNpemU6MTZweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLXRvcDozcHh9Ci5zY3N7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQouaXJ7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDoycHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjhweCAxMXB4O21hcmdpbi1ib3R0b206M3B4O3RyYW5zaXRpb246Ym9yZGVyLWxlZnQtY29sb3IgLjFzfQouaXI6aG92ZXJ7Ym9yZGVyLWxlZnQtY29sb3I6dmFyKC0tYWNjZW50KX0KLmlydHtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6YmFzZWxpbmU7bWFyZ2luLWJvdHRvbToycHh9Ci5pcm57Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouNXB4fQouaXJ2e2ZvbnQtc2l6ZToxNHB4O2ZvbnQtd2VpZ2h0OjcwMH0KLmlydi5va3tjb2xvcjp2YXIoLS1ncmVlbil9Lmlydi5kb3due2NvbG9yOnZhcigtLXJlZCl9Lmlydi53YXJue2NvbG9yOnZhcigtLXdhcm4pfQouaXJle2ZvbnQtc2l6ZToxMXB4O2NvbG9yOiMzYTNhM2E7bGluZS1oZWlnaHQ6MS40fQouY2h7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyMnB4IDQ2cHggMWZyIDI4cHggNjJweCA1NHB4O2dhcDo0cHg7cGFkZGluZzo0cHggMTBweDtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLmNye2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjJweCA0NnB4IDFmciAyOHB4IDYycHggNTRweDtnYXA6NHB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjdweCAxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjEycHh9Ci5jcjpsYXN0LWNoaWxke2JvcmRlci1ib3R0b206bm9uZX0KLmN0e2NvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweH0KLmNuMntvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXB9Ci5jYXt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMH0KLmNme3RleHQtYWxpZ246cmlnaHQ7Y29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4fQpmb290ZXJ7bWFyZ2luLXRvcDoyMHB4O3BhZGRpbmctdG9wOjExcHg7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQo8L3N0eWxlPgo8L2hlYWQ+Cjxib2R5Pgo8ZGl2IGNsYXNzPSJoZHIiPgogIDxkaXYgY2xhc3M9Imhkci10Ij7ilrggVFJBREVSIERFU0s8L2Rpdj4KICA8ZGl2IGNsYXNzPSJoZHItcyIgaWQ9Imxhc3QtdXBkYXRlIj7igJQ8L2Rpdj4KPC9kaXY+CjxkaXYgY2xhc3M9InRhYnMiPgogIDxkaXYgY2xhc3M9InRhYiBhY3RpdmUiIG9uY2xpY2s9InN3KCdjb3RhY29lcycsdGhpcykiPvCfk4ogQ290YcOnw7VlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3coJ2luZGljYWRvcmVzJyx0aGlzKSI+8J+TiCBJbmRpY2Fkb3JlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3coJ3Bvc2ljb2VzJyx0aGlzKSI+8J+SvCBQb3Npw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzdygnY2FsZW5kYXJpbycsdGhpcykiPvCfk4UgQ2FsZW5kw6FyaW88L2Rpdj4KPC9kaXY+Cgo8ZGl2IGlkPSJ0YWItY290YWNvZXMiIGNsYXNzPSJ0YWItY29udGVudCBhY3RpdmUiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImEiPjAxPC9zcGFuPiBFVUE8L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iY2wiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5TJlAgRVMxKjwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJlc2YtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJlc2YtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImNsIj5GdXR1cm88L2Rpdj48ZGl2IGNsYXNzPSJjbiI+TmFzZGFxIE5RPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9Im5xZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iY2wiPsONbmRpY2U8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+RG93IEpvbmVzPC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9ImRqaS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9ImRqaS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgciI+PGRpdiBjbGFzcz0iY2wiPlZvbGF0aWxpZGFkZTwvZGl2PjxkaXYgY2xhc3M9ImNuIj5WSVg8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0idml4LWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+RMOzbGFyIEluZGV4PC9kaXY+PGRpdiBjbGFzcz0iY24iPkRYWTwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJkeHktcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJkeHktYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5Dw6JtYmlvPC9kaXY+PGRpdiBjbGFzcz0iY24iPlVTRC9CUkw8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0idXNkLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0idXNkLWMiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImEiPjAyPC9zcGFuPiBCMyBUb3AgMTA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPsONbmRpY2U8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+SUJPVjwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJpYm92LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0iaWJvdi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iY2wiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5XSU4xITwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJ3aW4tcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJ3aW4tYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5QRVRSNDwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJwZXRyNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJwZXRyNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5JVFVCNDwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJpdHViNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJpdHViNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5WQUxFMzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJ2YWxlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJ2YWxlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5CQkRDNDwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJiYmRjNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJiYmRjNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5BQkVWMzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJhYmV2M3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJhYmV2M3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5CQkFTMzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJiYmFzM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJiYmFzM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj5XRUdFMzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJ3ZWdlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJ3ZWdlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHciPjxkaXYgY2xhc3M9ImNsIj5CRFI8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+Uk9YTzM0PC9kaXY+PGRpdiBjbGFzcz0iY3AgbG9hZGluZyIgaWQ9InJveG8zNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSJyb3hvMzRxLWMiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImEiPvCfk4I8L3NwYW4+IEIzIHBvciBTZWdtZW50byA8c3BhbiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpIj7CtyBjbGlxdWUgcGFyYSBleHBhbmRpcjwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2ZpbicpIj48c3Bhbj7wn4+mIEZpbmFuY2Vpcm88L3NwYW4+PHNwYW4gaWQ9ImFyLWZpbiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLWZpbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctZmluIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ3BldCcpIj48c3Bhbj7wn5uiIFBldHLDs2xlbyAmYW1wOyBHw6FzPC9zcGFuPjxzcGFuIGlkPSJhci1wZXQiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1wZXQiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXBldCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdtaW4nKSI+PHNwYW4+4puPIE1pbmVyYcOnw6NvPC9zcGFuPjxzcGFuIGlkPSJhci1taW4iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1taW4iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW1pbiI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2giIG9uY2xpY2s9InRnKCdtYXQnKSI+PHNwYW4+8J+MsiBQYXBlbCAmYW1wOyBDZWx1bG9zZTwvc3Bhbj48c3BhbiBpZD0iYXItbWF0Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItbWF0Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1tYXQiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygndXRpJykiPjxzcGFuPuKaoSBVdGlsaWRhZGUgUMO6YmxpY2E8L3NwYW4+PHNwYW4gaWQ9ImFyLXV0aSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXV0aSI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctdXRpIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2NjJykiPjxzcGFuPvCfm40gQ29uc3VtbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0iYXItY2MiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1jYyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctY2MiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnY24nKSI+PHNwYW4+8J+bkiBDb25zdW1vIE7Do28gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9ImFyLWNuIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItY24iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLWNuIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ3NhdScpIj48c3Bhbj7wn4+lIFNhw7pkZTwvc3Bhbj48c3BhbiBpZD0iYXItc2F1Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2Itc2F1Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1zYXUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnaW5kJykiPjxzcGFuPvCfj5cgQmVucyBJbmR1c3RyaWFpczwvc3Bhbj48c3BhbiBpZD0iYXItaW5kIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItaW5kIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0iZy1pbmQiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygndGl0JykiPjxzcGFuPvCfkrsgVEkgJmFtcDsgQ29tdW5pY2HDp8O1ZXM8L3NwYW4+PHNwYW4gaWQ9ImFyLXRpdCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNiMiIgaWQ9InNiLXRpdCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctdGl0Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiPjxzcGFuIGNsYXNzPSJhIj7wn4e68J+HuDwvc3Bhbj4gRVVBIHBvciBTZWdtZW50bzwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0ZygnbTcnKSI+PHNwYW4+4q2QIDcgTWFnbsOtZmljYXM8L3NwYW4+PHNwYW4gaWQ9ImFyLW03Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2ItbTciPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLW03Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ25xJykiPjxzcGFuPvCfkrsgTmFzZGFxIFRvcCAxNTwvc3Bhbj48c3BhbiBpZD0iYXItbnEiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1ucSI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctbnEiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNoIiBvbmNsaWNrPSJ0Zygnc3AnKSI+PHNwYW4+8J+TiiBTJmFtcDtQIDUwMCBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9ImFyLXNwIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2IyIiBpZD0ic2Itc3AiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJnLXNwIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzaCIgb25jbGljaz0idGcoJ2RqJykiPjxzcGFuPvCfj5sgRG93IEpvbmVzIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0iYXItZGoiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzYjIiIGlkPSJzYi1kaiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9ImctZGoiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCI+PHNwYW4gY2xhc3M9ImEiPjAzPC9zcGFuPiBDb21tb2RpdGllczwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCB3Ij48ZGl2IGNsYXNzPSJjbCI+UGV0csOzbGVvPC9kaXY+PGRpdiBjbGFzcz0iY24iPldUSS9DTDwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJjbC1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgdyI+PGRpdiBjbGFzcz0iY2wiPk1ldGFsPC9kaXY+PGRpdiBjbGFzcz0iY24iPkdPTEQ8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iZ29sZC1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgdyI+PGRpdiBjbGFzcz0iY2wiPk1ldGFsPC9kaXY+PGRpdiBjbGFzcz0iY24iPlNJTFZFUjwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJzaWx2ZXItcCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHciPjxkaXYgY2xhc3M9ImNsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImNuIj5DT1BQRVI8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iY29wcGVyLXAiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImEiPjA0PC9zcGFuPiBCaXRjb2luPC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImNsIj5TcG90PC9kaXY+PGRpdiBjbGFzcz0iY24iPkJUQy9VU0Q8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iYnRjLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0iYnRjLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+QlRDIFJTSTwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJidGMtcnNpIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iY2wiPkZ1bmRpbmcgOGg8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+QlRDIFJhdGU8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iYnRjLWZ1bmQiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+RmVhciAmYW1wOyBHcmVlZDwvZGl2PjxkaXYgY2xhc3M9ImNuIj5JbmRleDwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSJmZy12YWwiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImNjIiBpZD0iZmctbGJsIj7igJQ8L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8Zm9vdGVyPjxzcGFuIGlkPSJmb290ZXItdGltZSI+4oCUPC9zcGFuPjxzcGFuPlRyYWRlciBEZXNrIHYxMC41PC9zcGFuPjwvZm9vdGVyPgo8L2Rpdj4KCjxkaXYgaWQ9InRhYi1pbmRpY2Fkb3JlcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJhIj7wn5OKPC9zcGFuPiBDaWNsbyBCaXRjb2luPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWN5Y2xlLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEycHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxMzBweDtnYXA6OHB4O21hcmdpbjoxMnB4IDAiPgogICAgPGRpdiBpZD0iZmctYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTBweCI+Q2FycmVnYW5kbyBGZWFyICZhbXA7IEdyZWVkLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTJweDt0ZXh0LWFsaWduOmNlbnRlciI+CiAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjVweCI+QlRDL1VTRDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iYnRjLWluZC1wIj7igJQ8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImEiPvCfk4o8L3NwYW4+IEJUQyBTZW1hbmFsPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3BhbiBjbGFzcz0iYSI+8J+Tijwvc3Bhbj4gUEVUUjQgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjExcHg7bWFyZ2luLWxlZnQ6OHB4IiBvbmNsaWNrPSJybCgncGV0cjQnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InBldHI0LWluZCI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCI+PHNwYW4gY2xhc3M9ImEiPvCfk4o8L3NwYW4+IFZBTEUzIDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxMXB4O21hcmdpbi1sZWZ0OjhweCIgb25jbGljaz0icmwoJ3ZhbGUzJykiPuKGuzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJ2YWxlMy1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiPjxzcGFuIGNsYXNzPSJhIj7wn5OKPC9zcGFuPiBCQkFTMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTFweDttYXJnaW4tbGVmdDo4cHgiIG9uY2xpY2s9InJsKCdiYmFzMycpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0iYmJhczMtaW5kIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3BhbiBjbGFzcz0iYSI+8J+Tijwvc3Bhbj4gQVhJQTMgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjExcHg7bWFyZ2luLWxlZnQ6OHB4IiBvbmNsaWNrPSJybCgnYXhpYTMnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9ImF4aWEzLWluZCI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCI+PHNwYW4gY2xhc3M9ImEiPvCfk4o8L3NwYW4+IFJPWE8zNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTFweDttYXJnaW4tbGVmdDo4cHgiIG9uY2xpY2s9InJsKCdyb3hvMzQnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InJveG8zNC1pbmQiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KPC9kaXY+Cgo8ZGl2IGlkPSJ0YWItcG9zaWNvZXMiIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYSI+MDE8L3NwYW4+IE9wZXJhw6fDtWVzIEF0aXZhczwvZGl2PgogIDxkaXYgY2xhc3M9InBjIj4KICAgIDxkaXYgY2xhc3M9InBsIj5QZXRyb2JyYXMgUE4gwrcgQ2FsbCBWZW5kaWRhIMK3IFBFVFJMMzE5IMK3IFZlbmMgMTcvMTIvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icHQiPlBFVFI0PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0icHQtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icGMyIiBpZD0icHQtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlN0cmlrZSAoUEVUUkwzMTkpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCAzMCw4NTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+UHJlw6dvIHZzIHN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YgaXRtIiBpZD0icHQtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4xNy8xMi8yMDI2IMK3IDxzcGFuIGlkPSJwdC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZvbC4gSW1wbC48L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjQzLDQlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5Qcm9iLiBCJmFtcDtTIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPjksNCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIE1DIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIiBpZD0icHQtbWMtcnQiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNndCIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWxsIHNlciBleGVyY2lkYTwvZGl2PgogICAgICA8ZGl2IGlkPSJwdC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJwdC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIGV4ZXJjZXI8L2Rpdj48ZGl2IGNsYXNzPSJpdiIgaWQ9InB0LW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InB0LW1jLXYiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjVweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJwdC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+VmFsZSBPTiDCtyBDYWxsIFZlbmRpZGEgwrcgVkFMRUI1NzQgwrcgVmVuYyAxOC8wMi8yMDI3PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwdCI+VkFMRTM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJ2bC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJ2bC1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U3RyaWtlIChWQUxFQjU3NCk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDU3LDQwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5QcmXDp28gdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiBpdG0iIGlkPSJ2bC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiPjE4LzAyLzIwMjcgwrcgPHNwYW4gaWQ9InZsLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+NzEsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIEImYW1wO1MgZXhlcmNlcjwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+MTQsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlByb2IuIE1DIGV4ZXJjZXI8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIiBpZD0idmwtbWMtcnQiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNndCIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWxsIHNlciBleGVyY2lkYTwvZGl2PgogICAgICA8ZGl2IGlkPSJ2bC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJ2bC1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlByb2IuIGV4ZXJjZXI8L2Rpdj48ZGl2IGNsYXNzPSJpdiIgaWQ9InZsLW1jLXMiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9InZsLW1jLXYiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjVweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJ2bC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYyI+CiAgICA8ZGl2IGNsYXNzPSJwbCI+QVhJQTMgKEEpIMK3IEJpZGlyZWNpb25hbCDCtyBWZW5jIDE0LzA5LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5BWElBMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icHAgbG9hZGluZyIgaWQ9ImEzLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9ImEzLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA0Myw1MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S1VPICgrMjYsNiUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj5SJCA2OCw3Njwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+R2FuaG8gcy8gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkdhbmhvIGMvIGJhci4gYWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+KzQlIGZpeG88L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4xNC8wOS8yMDI2IMK3IDxzcGFuIGlkPSJhMy1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhMy1rZG8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RGlzdC4gS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzLWt1byI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzLXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZyIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNndCIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBDZW7DoXJpb3MgYmFycmVpcmE8L2Rpdj4KICAgICAgPGRpdiBpZD0iYTMtbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJhMy1tYy1yIiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlNlbSBCYXJyZWlyYSDinIU8L2Rpdj48ZGl2IGNsYXNzPSJpdiBvayIgaWQ9ImEzLW1jLW5iIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+QmFyLiBBbHRhIEtVTzwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJhMy1tYy1rdSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaXYgZG93biIgaWQ9ImEzLW1jLWtkIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJhMy1tYy12byI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NXB4IiBpZD0iYTMtbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiPgogICAgPGRpdiBjbGFzcz0icGwiPkFYSUEzIChCKSDCtyBCaWRpcmVjaW9uYWwgSU9OIEl0YcO6IMK3IFZlbmMgMDIvMTAvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icHQiPkFYSUEzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcCBsb2FkaW5nIiBpZD0iYTNiLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBjMiIgaWQ9ImEzYi1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygd2FybiI+UiQgNDAsNTI8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPktVTyAoKzI0JSk8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDYyLDgxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5HYW5obyBzLyBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+R2FuaG8gYy8gYmFyLiBhbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiB3YXJuIj4rNCUgZml4byAoMTIsMzMlIGEuYS4pPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MDIvMTAvMjAyNiDCtyA8c3BhbiBpZD0iYTNiLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RGlzdC4gS0RPPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzYi1rZG8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+RGlzdC4gS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiIgaWQ9ImEzYi1rdW8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJhM2Itc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2d0IiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtbCIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJhM2ItbWMtciIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLXRvcDo2cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaXYgb2siIGlkPSJhM2ItbWMtbmIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiIgaWQ9ImEzYi1tYy1rdSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaXYgZG93biIgaWQ9ImEzYi1tYy1rZCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0iYTNiLW1jLXZvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHgiIGlkPSJhM2ItbWMtaSI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiPgogICAgPGRpdiBjbGFzcz0icGwiPlJPWE8zNCDCtyBCRFIgTnViYW5rIMK3IFByZWZpeGFkbyBjLyBCYXJyZWlyYSDCtyBWZW5jIDE2LzA3LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InB0Ij5ST1hPMzQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBwIGxvYWRpbmciIGlkPSJyeC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwYzIiIGlkPSJyeC1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+QmFycmVpcmEgUk9YT0cxMDU8L3NwYW4+PHNwYW4gY2xhc3M9InN2IHdhcm4iPlIkIDEwLDUwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+MTYvMDcvMjAyNiDCtyA8c3BhbiBpZD0icngtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5EaXN0LiBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJyeC1rZG8iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic3IiPjxzcGFuIGNsYXNzPSJzbCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3YiIGlkPSJyeC1zdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWciIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzZ3QiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gc3VjZXNzbzwvZGl2PgogICAgICA8ZGl2IGlkPSJyeC1tYy1sIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9InJ4LW1jLXIiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UHJvYi4gU3VjZXNzbzwvZGl2PjxkaXYgY2xhc3M9Iml2IG9rIiBpZD0icngtbWMtcyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPkNhbGwgRXhlcmNpZGE8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIiBpZD0icngtbWMtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPktETyBBdGluZ2lkbzwvZGl2PjxkaXYgY2xhc3M9Iml2IGRvd24iIGlkPSJyeC1tYy1rIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iIGlkPSJyeC1tYy12Ij7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHgiIGlkPSJyeC1tYy1pIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxzcGFuIGNsYXNzPSJhIj7wn5OBPC9zcGFuPiBFbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjojMWMxYzFjIj4KICAgIDxkaXYgY2xhc3M9InB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxNHB4Ij5CQkFTMzwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlN0cmlrZSBCQkFTSDIxPC9zcGFuPjxzcGFuIGNsYXNzPSJzdiI+UiQgMjEsNjUgwrcgUmVmIFIkIDIwLDY3PC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPuKchSA4MCUgZG8gYWx2byBlbSA3MCUgZG8gcHJhem88L3NwYW4+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjojMWMxYzFjIj4KICAgIDxkaXYgY2xhc3M9InB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxNHB4Ij5BWElBMyBTaG9ydCBTdHJhbmdsZTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPkNhbGwgVi4gQVhJQUk1MDU8L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij5SJCA1MCw1MDwvc3Bhbj48L2Rpdj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InN2IG9rIj7inIUgQcOnw7VlcyBsaWJlcmFkYXM8L3NwYW4+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icGMiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjojMWMxYzFjIj4KICAgIDxkaXYgY2xhc3M9InB0IiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxNHB4Ij5ST1hPMzQgUHJlZml4YWRvIDcsMSU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzciI+PHNwYW4gY2xhc3M9InNsIj5FbmNlcnJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InN2Ij4wNC8wNi8yMDI2PC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNyIj48c3BhbiBjbGFzcz0ic2wiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic3Ygb2siPuKchSB+NSwxNyUgKDcyJSBkbyBhbHZvKTwvc3Bhbj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8ZGl2IGlkPSJ0YWItY2FsZW5kYXJpbyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO21hcmdpbi1ib3R0b206MTJweCI+CiAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCkiPvCfh7rwn4e4IPCfh6fwn4e3IPCfh6rwn4e6IPCfh6zwn4enIPCfh6jwn4ezIPCfh6/wn4e1IPCfh6nwn4eqIPCfh6jwn4emIMK3IEltcGFjdG8gTcOpZGlvKzwvZGl2PgogICAgPGJ1dHRvbiBvbmNsaWNrPSJsb2FkQ2FsKCkiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1hY2NlbnQpO2NvbG9yOnZhcigtLWFjY2VudCk7cGFkZGluZzo2cHggMTRweDtmb250LXNpemU6MTJweDtjdXJzb3I6cG9pbnRlcjtmb250LWZhbWlseTppbmhlcml0Ij7ihrsgQXR1YWxpemFyPC9idXR0b24+CiAgPC9kaXY+CiAgPGRpdiBpZD0iY2FsLXN0IiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206N3B4Ij48L2Rpdj4KICA8ZGl2IGlkPSJjYWwtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlciI+Q2xpcXVlIGVtIEF0dWFsaXphcjwvZGl2PjwvZGl2Pgo8L2Rpdj4KCjxzY3JpcHQ+CmNvbnN0IEI9J2h0dHBzOi8vdHJhZGVyLWRlc2sub25yZW5kZXIuY29tJzsKY29uc3QgU0VHPXsKICBmaW46WydJVFVCNCcsJ0JCREM0JywnQkJBUzMnLCdTQU5CMTEnLCdCM1NBMycsJ0JQQUMxMScsJ0lUU0E0JywnQlJTUjYnLCdBQkNCNCcsJ0JNR0I0J10sCiAgcGV0OlsnUEVUUjQnLCdQRVRSMycsJ1BSSU8zJywnQlJBVjMnLCdWQkJSMycsJ0NTQU4zJywnUkVDVjMnLCdVR1BBMycsJ1NFUUwzJywnRU5BVDMnXSwKICBtaW46WydWQUxFMycsJ0dHQlI0JywnQ1NOQTMnLCdVU0lNNScsJ0JSQVA0JywnRkVTQTQnLCdDTUlOMycsJ0NCQVYzJywnR09BVTQnLCdQR01OMyddLAogIG1hdDpbJ1NVWkIzJywnS0xCTjExJywnRFhDTzMnLCdVTklQNicsJ1JBTkkzJywnT1JWUjMnLCdTTVRPMycsJ0ZSQVMzJywnTFBTQjMnLCdDU1VEMyddLAogIHV0aTpbJ0FYSUEzJywnRVFUTDMnLCdDUEZFMycsJ1NCU1AzJywnQ01JRzQnLCdFTkdJMTEnLCdUQUVFMTEnLCdBVVJFMycsJ0VHSUUzJywnQ1BMRTMnXSwKICBjYzogWydSRU5UMycsJ0xSRU4zJywnTUdMVTMnLCdDWVJFMycsJ01SVkUzJywnQVpaQTMnLCdWSVZBMycsJ1NCRkczJywnWURVUTMnLCdNT1ZJMyddLAogIGNuOiBbJ0FCRVYzJywnSkJTUzMnLCdCUkZTMycsJ05BVFUzJywnTURJQTMnLCdCRUVGMycsJ1NMQ0UzJywnTVRSRTMnLCdDQU1MMycsJ1BDQVIzJ10sCiAgc2F1OlsnUkRPUjMnLCdIQVBWMycsJ0ZMUlkzJywnREFTQTMnLCdRVUFMMycsJ09OQ08zJywnUE5WTDMnLCdPRFBWMycsJ01BVEQzJywnQUFMUjMnXSwKICBpbmQ6WydXRUdFMycsJ0VNQlIzJywnUkFJTDMnLCdUR01BMycsJ1JPTUkzJywnVkxJRDMnLCdUVVBZMycsJ0lSQlIzJywnUE9NTzQnLCdMQVZWMyddLAogIHRpdDpbJ1ZJVlQzJywnVElNUzMnLCdUT1RWUzMnLCdTUUlBMycsJ01MQVMzJywnQU5JTTMnLCdQT1NJMycsJ0lOVEIzJywnTFdTQTMnLCdJRkNNMyddLAp9Owpjb25zdCBVU1NFRz17CiAgbTc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnR09PR0wnLCdNRVRBJywnVFNMQSddLAogIG5xOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQ09TVCcsJ05GTFgnLCdRQ09NJywnQU1EJywnQURCRScsJ0lOVEMnLCdDU0NPJ10sCiAgc3A6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdCUksuQicsJ0pQTScsJ0xMWScsJ1YnLCdVTkgnLCdYT00nLCdNQScsJ05GTFgnLCdQRycsJ0pOSicsJ0hEJywnQkFDJ10sCiAgZGo6WydVTkgnLCdHUycsJ0hEJywnU0hXJywnQ0FUJywnQVhQJywnTUNEJywnQU1HTicsJ1YnLCdUUlYnLCdJQk0nLCdKUE0nLCdIT04nLCdDUk0nLCdDVlgnLCdBQVBMJywnTVNGVCcsJ0RJUycsJ05LRScsJ0JBJ10KfTsKY29uc3QgZlI9dj0+diE9bnVsbD8nUiQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlU9dj0+diE9bnVsbD8nVVMkICcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21pbmltdW1GcmFjdGlvbkRpZ2l0czoyLG1heGltdW1GcmFjdGlvbkRpZ2l0czoyfSk6J+KAlCc7CmNvbnN0IGZQPXY9PnYhPW51bGw/TnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CmZ1bmN0aW9uIEUoaWQsdCl7Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuO2UudGV4dENvbnRlbnQ9dDtlLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CmZ1bmN0aW9uIENoKGlkLG4scCx0cCl7CiAgY29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuOwogIGNvbnN0IGQ9bi1wLHBjPShkL01hdGguYWJzKHB8fDEpKjEwMCkudG9GaXhlZCgyKSxzZz1kPj0wPycrJzonJzsKICBpZih0cD09PSdyJyllLnRleHRDb250ZW50PXNnKydSJCAnK01hdGguYWJzKGQpLnRvRml4ZWQoMikrJyAoJytzZytwYysnJSknOwogIGVsc2UgaWYodHA9PT0ndScpZS50ZXh0Q29udGVudD1zZytkLnRvRml4ZWQoMikrJyAoJytzZytwYysnJSknOwogIGVsc2UgZS50ZXh0Q29udGVudD1zZytNYXRoLmFicyhkKS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKycgKCcrc2crcGMrJyUpJzsKICBlLmNsYXNzTmFtZT0nY2MgJysoZD4wPyd1cCc6ZDwwPydkbic6J2ZsJyk7Cn0KZnVuY3Rpb24gc3codCxlbCl7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYicpLmZvckVhY2goeD0+eC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYi1jb250ZW50JykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndGFiLScrdCkuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7CiAgaWYoZWwpZWwuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7CiAgaWYodD09PSdpbmRpY2Fkb3JlcycmJiF3aW5kb3cuX0lMKXt3aW5kb3cuX0lMPXRydWU7bG9hZEluZCgpO30KICBpZih0PT09J2NhbGVuZGFyaW8nKWxvYWRDYWwoKTsKfQpmdW5jdGlvbiB0ZyhpZCl7CiAgY29uc3QgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2ItJytpZCksYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXItJytpZCk7CiAgaWYoIWIpcmV0dXJuOwogIGNvbnN0IG9wPWIuc3R5bGUuZGlzcGxheSE9PSdibG9jayc7CiAgYi5zdHlsZS5kaXNwbGF5PW9wPydibG9jayc6J25vbmUnOwogIGlmKGEpYS50ZXh0Q29udGVudD1vcD8n4payJzon4pa8JzsKICBpZihvcCYmIWIuZGF0YXNldC5sKXtiLmRhdGFzZXQubD0nMSc7bG9hZFNlZyhpZCk7fQp9CmFzeW5jIGZ1bmN0aW9uIGxvYWRTZWcoaWQpewogIGNvbnN0IGc9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ctJytpZCk7aWYoIWcpcmV0dXJuOwogIGNvbnN0IHBmeD1pZCsnXyc7CiAgaWYoVVNTRUdbaWRdKXsKICAgIGNvbnN0IHRrcz1VU1NFR1tpZF07CiAgICBnLmlubmVySFRNTD10a3MubWFwKHQ9Pntjb25zdCB0aWQ9dC5yZXBsYWNlKC9bXmEtekEtWjAtOV0vZywnXycpO3JldHVybiAnPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjbCI+VVM8L2Rpdj48ZGl2IGNsYXNzPSJjbiI+Jyt0Kyc8L2Rpdj48ZGl2IGNsYXNzPSJjcCBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iY2MiIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nO30pLmpvaW4oJycpOwogICAgdHJ5ewogICAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy91cy9xdW90ZXM/dGlja2Vycz0nK3Rrcy5qb2luKCcsJykpOwogICAgICBpZighci5vaylyZXR1cm47CiAgICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICAgIE9iamVjdC5lbnRyaWVzKGQpLmZvckVhY2goKFt0LHZdKT0+ewogICAgICAgIGNvbnN0IHRpZD10LnJlcGxhY2UoL1teYS16QS1aMC05XS9nLCdfJyk7CiAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICBpZihlcCYmdi5wcmljZSl7ZXAudGV4dENvbnRlbnQ9JyQnK051bWJlcih2LnByaWNlKS50b0ZpeGVkKDIpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CiAgICAgICAgaWYodi5wcmljZSYmdi5wcmV2KUNoKHBmeCt0aWQrJ19jJyx2LnByaWNlLHYucHJldiwndScpOwogICAgICB9KTsKICAgIH1jYXRjaChlKXt9CiAgICByZXR1cm47CiAgfQogIGNvbnN0IHRrcz1TRUdbaWRdO2lmKCF0a3MpcmV0dXJuOwogIGcuaW5uZXJIVE1MPXRrcy5tYXAodD0+e2NvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7cmV0dXJuICc8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImNsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImNuIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImNwIGxvYWRpbmciIGlkPSInK3BmeCt0aWQrJ19wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjYyIgaWQ9IicrcGZ4K3RpZCsnX2MiPuKAlDwvZGl2PjwvZGl2Pic7fSkuam9pbignJyk7CiAgLy8gQmF0Y2ggVFYKICBjb25zdCB0dlRrcz10a3MubWFwKHQ9PidCTUZCT1ZFU1BBOicrdCk7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dHZUa3N9LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7CiAgICBpZihyLm9rKXsKICAgICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgICAgY29uc3QgbG9hZGVkPW5ldyBTZXQoKTsKICAgICAgKGQuZGF0YXx8W10pLmZvckVhY2goeD0+ewogICAgICAgIGNvbnN0IHQ9eC5zLnJlcGxhY2UoJ0JNRkJPVkVTUEE6JywnJykudG9Mb3dlckNhc2UoKTsKICAgICAgICBjb25zdFtjLGNhXT14LmR8fFtdOwogICAgICAgIGlmKGMhPW51bGwpewogICAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3QrJ19wJyk7CiAgICAgICAgICBpZihlcCl7ZXAudGV4dENvbnRlbnQ9ZlIoYyk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO2xvYWRlZC5hZGQodCk7fQogICAgICAgICAgQ2gocGZ4K3QrJ19jJyxjLGMtKGNhfHwwKSwncicpOwogICAgICAgIH0KICAgICAgfSk7CiAgICAgIC8vIEZhbGxiYWNrIGluZGl2aWR1YWwgdmlhIC9pbmRpY2F0b3JzIHBhcmEgb3MgcXVlIGZhbHRhcmFtCiAgICAgIGNvbnN0IG1pc3Npbmc9dGtzLmZpbHRlcih0PT4hbG9hZGVkLmhhcyh0LnRvTG93ZXJDYXNlKCkpKTsKICAgICAgZm9yKGNvbnN0IHQgb2YgbWlzc2luZyl7CiAgICAgICAgdHJ5ewogICAgICAgICAgY29uc3QgcjI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvJyt0KycuU0EnKTsKICAgICAgICAgIGlmKCFyMi5vayljb250aW51ZTsKICAgICAgICAgIGNvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICAgIGlmKGQyLnByZWNvX2F0dWFsKXsKICAgICAgICAgICAgY29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTsKICAgICAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICAgICAgaWYoZXApe2VwLnRleHRDb250ZW50PWZSKGQyLnByZWNvX2F0dWFsKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQogICAgICAgICAgICBpZihkMi5wcmVjb19hbnRlcmlvcilDaChwZngrdGlkKydfYycsZDIucHJlY29fYXR1YWwsZDIucHJlY29fYW50ZXJpb3IsJ3InKTsKICAgICAgICAgIH0KICAgICAgICB9Y2F0Y2goZTIpe30KICAgICAgfQogICAgfQogIH1jYXRjaChlKXt9Cn0KYXN5bmMgZnVuY3Rpb24gZkhMKCl7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pOwogICAgaWYoIXIub2spcmV0dXJuOwogICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IGJwPXBhcnNlRmxvYXQoZC5CVEN8fDApOwogICAgaWYoYnA+MCl7RSgnYnRjLXAnLGZVKGJwKSk7Q2goJ2J0Yy1jJyxicCxicCowLjk5LCd1Jyk7fQogICAgdHJ5ewogICAgICBjb25zdCByMj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcycsZGV4Oid4eXonfSl9KTsKICAgICAgaWYocjIub2spe2NvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTtpZihkMlsneHl6OkNMJ10pRSgnY2wtcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDTCddKS50b0ZpeGVkKDIpKTtpZihkMlsneHl6OkdPTEQnXSlFKCdnb2xkLXAnLCckJytOdW1iZXIoZDJbJ3h5ejpHT0xEJ10pLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpO2lmKGQyWyd4eXo6U0lMVkVSJ10pRSgnc2lsdmVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6U0lMVkVSJ10pLnRvRml4ZWQoMikpO2lmKGQyWyd4eXo6Q09QUEVSJ10pRSgnY29wcGVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q09QUEVSJ10pLnRvRml4ZWQoMykpO30KICAgIH1jYXRjaChlKXt9CiAgfWNhdGNoKGUpe30KfQphc3luYyBmdW5jdGlvbiBmVFYoKXsKICBjb25zdCBvdXQ9e307CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6WydCTUZCT1ZFU1BBOlBFVFI0JywnQk1GQk9WRVNQQTpJVFVCNCcsJ0JNRkJPVkVTUEE6VkFMRTMnLCdCTUZCT1ZFU1BBOkJCREM0JywnQk1GQk9WRVNQQTpBQkVWMycsJ0JNRkJPVkVTUEE6QkJBUzMnLCdCTUZCT1ZFU1BBOldFR0UzJywnQk1GQk9WRVNQQTpJQk9WJ119LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7CiAgICBpZihyLm9rKXtjb25zdCBkPWF3YWl0IHIuanNvbigpOyhkLmRhdGF8fFtdKS5mb3JFYWNoKHg9Pntjb25zdFtjLGNhXT14LmR8fFtdO2lmKGMhPW51bGwpb3V0W3guc109e3A6Yyx2OmMtKGNhfHwwKX07fSk7fQogIH1jYXRjaChlKXt9CiAgdHJ5e2NvbnN0IHJyPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKHJyLm9rKXtjb25zdCBkZD1hd2FpdCByci5qc29uKCk7aWYoZGQucHJlY29fYXR1YWwpe0UoJ3JveG8zNHEtcCcsZlIoZGQucHJlY29fYXR1YWwpKTtDaCgncm94bzM0cS1jJyxkZC5wcmVjb19hdHVhbCxkZC5wcmVjb19hbnRlcmlvcnx8ZGQucHJlY29fYXR1YWwqMC45OSwncicpO319fWNhdGNoKGUpe30KICByZXR1cm4gb3V0Owp9CmFzeW5jIGZ1bmN0aW9uIGZGdXQoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvZnV0dXJlcycpO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZkZ1bmQoKXsKICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9mYXBpLmJpbmFuY2UuY29tL2ZhcGkvdjEvcHJlbWl1bUluZGV4P3N5bWJvbD1CVENVU0RUJyk7aWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtFKCdidGMtZnVuZCcsKHBhcnNlRmxvYXQoZC5sYXN0RnVuZGluZ1JhdGV8fDApKjEwMCkudG9GaXhlZCg0KSsnJScpO3JldHVybjt9fWNhdGNoKGUpe30KICB0cnl7Y29uc3QgcjI9YXdhaXQgZmV0Y2goQisnL2JpbmFuY2UvZnVuZGluZycpO2lmKCFyMi5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByMi5qc29uKCk7aWYoZC5sYXN0RnVuZGluZ1JhdGUpRSgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlKSoxMDApLnRvRml4ZWQoNCkrJyUnKTt9Y2F0Y2goZSl7fQp9CmZ1bmN0aW9uIGRvTWFjcm8odHYsZnQpewogIGNvbnN0IGliPXR2WydCTUZCT1ZFU1BBOklCT1YnXTtpZihpYil7RSgnaWJvdi1wJyxmUChpYi5wKSk7Q2goJ2lib3YtYycsaWIucCxpYi52LCdwJyk7fQogIFtbJ1BFVFI0JywncGV0cjRxJ10sWydJVFVCNCcsJ2l0dWI0cSddLFsnVkFMRTMnLCd2YWxlM3EnXSxbJ0JCREM0JywnYmJkYzRxJ10sWydBQkVWMycsJ2FiZXYzcSddLFsnQkJBUzMnLCdiYmFzM3EnXSxbJ1dFR0UzJywnd2VnZTNxJ11dLmZvckVhY2goKFt0LGlkXSk9Pntjb25zdCBkPXR2WydCTUZCT1ZFU1BBOicrdF07aWYoZCl7RShpZCsnLXAnLGZSKGQucCkpO0NoKGlkKyctYycsZC5wLGQudiwncicpO319KTsKICBpZihmdCl7CiAgICBjb25zdCBhZj0oaWQsdik9Pntjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZihlKXtlLnRleHRDb250ZW50PXY7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fX07CiAgICBpZihmdC5kamk/LnByaWNlKXthZignZGppLXAnLGZQKGZ0LmRqaS5wcmljZSkpO0NoKCdkamktYycsZnQuZGppLnByaWNlLGZ0LmRqaS5wcmV2LCdwJyk7fQogICAgaWYoZnQuZXNmPy5wcmljZSl7YWYoJ2VzZi1wJyxmUChmdC5lc2YucHJpY2UpKTtDaCgnZXNmLWMnLGZ0LmVzZi5wcmljZSxmdC5lc2YucHJldiwncCcpO30KICAgIGlmKGZ0Lm5xZj8ucHJpY2Upe2FmKCducWYtcCcsZlAoZnQubnFmLnByaWNlKSk7Q2goJ25xZi1jJyxmdC5ucWYucHJpY2UsZnQubnFmLnByZXYsJ3AnKTt9CiAgICBpZihmdC53aW4/LnByaWNlKXthZignd2luLXAnLGZQKGZ0Lndpbi5wcmljZSkpO0NoKCd3aW4tYycsZnQud2luLnByaWNlLGZ0Lndpbi5wcmV2LCdwJyk7fQogICAgaWYoZnQudml4Py5wcmljZSl7YWYoJ3ZpeC1wJyxOdW1iZXIoZnQudml4LnByaWNlKS50b0ZpeGVkKDIpKTtDaCgndml4LWMnLGZ0LnZpeC5wcmljZSxmdC52aXgucHJldiwndScpO30KICAgIGlmKGZ0LmR4eT8ucHJpY2Upe2FmKCdkeHktcCcsTnVtYmVyKGZ0LmR4eS5wcmljZSkudG9GaXhlZCgyKSk7Q2goJ2R4eS1jJyxmdC5keHkucHJpY2UsZnQuZHh5LnByZXYsJ3UnKTt9CiAgICBpZihmdC51c2Q/LnByaWNlKXthZigndXNkLXAnLGZSKGZ0LnVzZC5wcmljZSkpO0NoKCd1c2QtYycsZnQudXNkLnByaWNlLGZ0LnVzZC5wcmV2fHxmdC51c2QucHJpY2UsJ3InKTt9CiAgfQp9CmZ1bmN0aW9uIGRvUG9zKHR2KXsKICBjb25zdCBwdD10dlsnQk1GQk9WRVNQQTpQRVRSNCddO2NvbnN0IHBwPXB0Py5wfHw0MCxwdj1wdD8udnx8NDA7CiAgRSgncHQtcCcsZlIocHApKTtDaCgncHQtYycscHAscHYsJ3InKTsKICBjb25zdCBwZD1wcC0zMC44NTtFKCdwdC1pdG0nLChwZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHBkKS50b0ZpeGVkKDIpKycgJysocGQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCB2bD10dlsnQk1GQk9WRVNQQTpWQUxFMyddO2NvbnN0IHZwPXZsPy5wfHw3OCx2dj12bD8udnx8Nzg7CiAgRSgndmwtcCcsZlIodnApKTtDaCgndmwtYycsdnAsdnYsJ3InKTsKICBjb25zdCB2ZD12cC01Ny40MDtFKCd2bC1pdG0nLCh2ZD49MD8nKyBSJCAnOictIFIkICcpK01hdGguYWJzKHZkKS50b0ZpeGVkKDIpKycgJysodmQ+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCBjZD0oZHMsZWlkKT0+e2NvbnN0IHY9bmV3IERhdGUoZHMpLGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKSxlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVpZCk7aWYoZSllLnRleHRDb250ZW50PWQ7fTsKICBjZCgnMjAyNi0xMi0xNycsJ3B0LWRpYXMnKTtjZCgnMjAyNy0wMi0xOCcsJ3ZsLWRpYXMnKTtjZCgnMjAyNi0wOS0xNCcsJ2EzLWRpYXMnKTtjZCgnMjAyNi0xMC0wMicsJ2EzYi1kaWFzJyk7Y2QoJzIwMjYtMDctMTYnLCdyeC1kaWFzJyk7CiAgc2V0VGltZW91dChhc3luYygpPT57CiAgICB0cnl7CiAgICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2luZGljYXRvcnMvQVhJQTMuU0EnKTtpZighci5vaylyZXR1cm47CiAgICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJlY29fYXR1YWwpcmV0dXJuOwogICAgICBjb25zdCBwPWQucHJlY29fYXR1YWw7RSgnYTMtcCcsZlIocCkpO0UoJ2EzYi1wJyxmUihwKSk7CiAgICAgIGNvbnN0IGtBPTQzLjUxLGt1QT02OC43NixrQj00MC41MixrdUI9NjIuODE7CiAgICAgIGNvbnN0IGRBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhMy1rZG8nKTtpZihkQSlkQS50ZXh0Q29udGVudD0oKHAta0EpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7CiAgICAgIGNvbnN0IHVBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhMy1rdW8nKTtpZih1QSl1QS50ZXh0Q29udGVudD0oKGt1QS1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJzsKICAgICAgY29uc3Qgc0E9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzLXN0Jyk7aWYoc0Epe3NBLnRleHRDb250ZW50PXA8PWtBPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VBPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQS5jbGFzc05hbWU9J3N2ICcrKHA8PWtBfHxwPj1rdUE/J3dhcm4nOidvaycpO30KICAgICAgY29uc3QgZEI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2EzYi1rZG8nKTtpZihkQilkQi50ZXh0Q29udGVudD0oKHAta0IpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7CiAgICAgIGNvbnN0IHVCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhM2Ita3VvJyk7aWYodUIpdUIudGV4dENvbnRlbnQ9KChrdUItcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7CiAgICAgIGNvbnN0IHNCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhM2Itc3QnKTtpZihzQil7c0IudGV4dENvbnRlbnQ9cDw9a0I/J/CflLQgS0RPIEFUSU5HSURPJzpwPj1rdUI/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NCLmNsYXNzTmFtZT0nc3YgJysocDw9a0J8fHA+PWt1Qj8nd2Fybic6J29rJyk7fQogICAgfWNhdGNoKGUpe30KICB9LDIwMDApOwogIHNldFRpbWVvdXQoYXN5bmMoKT0+ewogICAgdHJ5ewogICAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKCFyLm9rKXJldHVybjsKICAgICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTtpZighZC5wcmVjb19hdHVhbClyZXR1cm47CiAgICAgIGNvbnN0IHA9ZC5wcmVjb19hdHVhbDtFKCdyeC1wJyxmUihwKSk7CiAgICAgIGNvbnN0IGRlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1rZG8nKTtpZihkZSlkZS50ZXh0Q29udGVudD0oKHAtMTAuNTApL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRhIGJhcnJlaXJhJzsKICAgICAgY29uc3Qgc2U9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LXN0Jyk7aWYoc2Upe3NlLnRleHRDb250ZW50PXA8PTEwLjUwPyfwn5S0IEJBUlJFSVJBIEFUSU5HSURBJzon4pyFIEFjaW1hIGRhIGJhcnJlaXJhJztzZS5jbGFzc05hbWU9J3N2ICcrKHA8PTEwLjUwPydpdG0nOidvaycpO30KICAgIH1jYXRjaChlKXt9CiAgfSwzMDAwKTsKfQphc3luYyBmdW5jdGlvbiBNQyh0ayxzayxkaWFzLGxJZCxySWQsc0lkLHZJZCxpSWQscnRJZCl7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcjp0ayxrX2NhbGw6c2ssa19wdXQ6c2ssdF9kYXlzOmRpYXMsbjo1MDAwfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxJZCkuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocklkKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBjb25zdCBwcm9iPU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYXx8MCk7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoc0lkKTtzRWwudGV4dENvbnRlbnQ9cHJvYi50b0ZpeGVkKDEpKyclJzsKICAgIHNFbC5jbGFzc05hbWU9J2l2ICcrKHByb2I8MTU/J29rJzpwcm9iPDMwPyd3YXJuJzonZG93bicpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodklkKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlJZCkudGV4dENvbnRlbnQ9J1ZvbC5oaXN0LiAnK2Qudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUgwrcgQiZTIHVzYSB2b2wuaW1wbC4gbWFpb3Ig4oaSIHByb2IgQiZTID4gTUMgwrcgJysocHJvYjwxNT8n4pyFIFJpc2NvIGJhaXhvJzon4pqgIE1vbml0b3JhcicpOwogICAgaWYocnRJZClFKHJ0SWQscHJvYi50b0ZpeGVkKDEpKyclJyk7CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxJZCk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gTUNCKHRrLGVuLGtkLGt1LGRpYXMscGZ4KXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCKycvbW9udGVjYXJsby9iYXJyaWVyJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXI6dGssZW50cnk6ZW4sa2RvOmtkLGt1bzprdSx0X2RheXM6ZGlhcyxuOjMwMDB9KX0pOwogICAgaWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtbCcpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCsnLW1jLXInKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1uYicpLnRleHRDb250ZW50PWQucHJvYl9zZW1fYmFycmVpcmEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1rdScpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9hbHRhLnRvRml4ZWQoMSkrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMta2QnKS50ZXh0Q29udGVudD1kLnByb2JfYmFycmVpcmFfYmFpeGEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy12bycpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4KyctbWMtaScpLnRleHRDb250ZW50PSdSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtkbysnIMK3IEtVTyBSJCAnK2Qua3VvOwogIH1jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrJy1tYy1sJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gTUNSKHRrLGVuLGtkLGRpYXMpewogIHRyeXsKICAgIGNvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXI6dGssa19jYWxsOmVuLGtfcHV0OmVuLHRfZGF5czpkaWFzLGtub2NrX2Rvd246a2Qsbjo1MDAwfSl9KTsKICAgIGlmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1sJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXInKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3J4LW1jLXMnKTtzRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9zdWNlc3NvKS50b0ZpeGVkKDEpKyclJztzRWwuY2xhc3NOYW1lPSdpdiAnKyhkLnByb2Jfc3VjZXNzbz43MD8nb2snOmQucHJvYl9zdWNlc3NvPjUwPyd3YXJuJzonZG93bicpOwogICAgY29uc3QgY0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1jJyk7aWYoY0VsKWNFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX2NhbGxfZXhlcmNpZGEpLnRvRml4ZWQoMSkrJyUnOwogICAgY29uc3Qga0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1rJyk7aWYoa0VsKWtFbC50ZXh0Q29udGVudD1kLnByb2Jfa2RvX2F0aW5naWRvIT1udWxsP051bWJlcihkLnByb2Jfa2RvX2F0aW5naWRvKS50b0ZpeGVkKDEpKyclJzon4oCUJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy12JykudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncngtbWMtaScpLnRleHRDb250ZW50PSdSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtub2NrX2Rvd247CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyeC1tYy1sJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J3RpbWVvdXQnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gZkluZCh0ayl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwzMDAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvaW5kaWNhdG9ycy8nK3RrLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZCVENJKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvYnRjL2luZGljYXRvcnMnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZCVENDKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCKycvYnRjL2N5Y2xlJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmRkcoKXsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEIrJy9mZWFyZ3JlZWQnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IHY9ZC52YWx1ZXx8NTAsY2xzPXY8PTI1Pyd2YXIoLS1yZWQpJzp2PD00NT8ndmFyKC0td2FybiknOnY8PTc1Pyd2YXIoLS1hY2NlbnQpJzondmFyKC0tZ3JlZW4pJzsKICAgIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmZy1hcmVhJyk7CiAgICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxM3B4Ij48ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo3cHgiPvCfmLEgRkVBUiAmIEdSRUVEPC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweCI+PGRpdiBzdHlsZT0iZm9udC1zaXplOjM0cHg7Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOicrY2xzKyciPicrdisnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjE0cHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOicrY2xzKyciPicrKGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKSsnPC9kaXY+PC9kaXY+PC9kaXY+JzsKICAgIEUoJ2ZnLXZhbCcsU3RyaW5nKHYpKTtFKCdmZy1sYmwnLGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKTsKICAgIHRyeXtjb25zdCByYj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pO2lmKHJiLm9rKXtjb25zdCBkYj1hd2FpdCByYi5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkYi5CVEN8fDApO2lmKGJwPjApe0UoJ2J0Yy1pbmQtcCcsJyQnK051bWJlcihicCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7RSgnYnRjLXAnLGZVKGJwKSk7fX19Y2F0Y2goZTIpe30KICB9Y2F0Y2goZSl7fQp9CmZ1bmN0aW9uIHJuZEluZChpZCxkYXRhKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCsnLWluZCcpO2lmKCFlbClyZXR1cm47CiAgaWYoIWRhdGEpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7cGFkZGluZzoxMHB4O2ZvbnQtc2l6ZToxMnB4Ij7ij7MgU2VtIHJlc3Bvc3RhIOKAlCBjbGlxdWUg4oa7PC9kaXY+JztyZXR1cm47fQogIGlmKGRhdGEuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tcmVkKTtwYWRkaW5nOjEwcHg7Zm9udC1zaXplOjEycHgiPuKaoCAnK2RhdGEuZXJyb3IrJzwvZGl2Pic7cmV0dXJuO30KICBjb25zdCBpbmRzPWRhdGEuaW5kaWNhZG9yZXN8fFtdLHNjPU51bWJlcihkYXRhLnNjb3JlX3RvdGFsfHwwKSxwcmVjbz1kYXRhLnByZWNvX2F0dWFsLGdyYWhhbT1kYXRhLmdyYWhhbV92YWx1ZSx1cD1kYXRhLnVwc2lkZV9ncmFoYW0sc2V0b3I9ZGF0YS5zZXRvcnx8Jyc7CiAgY29uc3Qgc2MyPXNjPj02NT8ndmFyKC0tZ3JlZW4pJzpzYz49NDA/J3ZhcigtLXdhcm4pJzondmFyKC0tcmVkKScsc2w9c2M+PTY1PydDb21wcmEg4payJzpzYz49NDA/J05ldXRybyDihpInOidWZW5kYSDilrwnOwogIGxldCBoPSc8ZGl2IGNsYXNzPSJzY2IiPjxkaXYgY2xhc3M9InNjYyI+PGRpdiBjbGFzcz0ic2NtIj5TY29yZTwvZGl2PjxkaXYgY2xhc3M9InNjbiIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2MrJzwvZGl2PjxkaXYgY2xhc3M9InNjbCIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2wrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0ic2NjIj48ZGl2IGNsYXNzPSJzY20iPkNvdGHDp8OjbzwvZGl2PjxkaXYgY2xhc3M9InNjdiI+JysocHJlY28/J1IkICcrTnVtYmVyKHByZWNvKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NzIj4nK3NldG9yKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjYyI+PGRpdiBjbGFzcz0ic2NtIj5HcmFoYW0gVko8L2Rpdj48ZGl2IGNsYXNzPSJzY3YiIHN0eWxlPSJjb2xvcjonKyh1cCYmdXA+MD8ndmFyKC0tZ3JlZW4pJzondmFyKC0tcmVkKScpKyciPicrKGdyYWhhbT8nUiQgJytOdW1iZXIoZ3JhaGFtKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NzIiBzdHlsZT0iY29sb3I6JysodXAmJnVwPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cCE9bnVsbD8odXA+MD8nKyc6JycpK3VwKyclJzon4oCUJykrJzwvZGl2PjwvZGl2PjwvZGl2Pic7CiAgaW5kcy5mb3JFYWNoKGk9PnsKICAgIGNvbnN0IHM9aS5zaW5hbHx8JycsY2xzPXM9PT0nQWx0YSd8fHM9PT0nU29icmV2ZW5kYSc/J29rJzpzPT09J0JhaXhhJ3x8cz09PSdTb2JyZWNvbXByYSc/J2Rvd24nOid3YXJuJyxhcj1jbHM9PT0nb2snPyfilrInOmNscz09PSdkb3duJz8n4pa8Jzon4oaSJzsKICAgIGgrPSc8ZGl2IGNsYXNzPSJpciI+PGRpdiBjbGFzcz0iaXJ0Ij48c3BhbiBjbGFzcz0iaXJuIj4nKyhpLm5vbWV8fCcnKSsnPC9zcGFuPjxzcGFuIGNsYXNzPSJpcnYgJytjbHMrJyI+JysoaS52YWxvciE9bnVsbD9pLnZhbG9yOifigJQnKSsnICcrYXIrJzwvc3Bhbj48L2Rpdj4nKyhpLmV4cGxpY2FjYW8/JzxkaXYgY2xhc3M9ImlyZSI+JytpLmV4cGxpY2FjYW8rJzwvZGl2Pic6JycpKyc8L2Rpdj4nOwogIH0pOwogIGVsLmlubmVySFRNTD1ofHwnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6OHB4Ij5TZW0gaW5kaWNhZG9yZXM8L2Rpdj4nOwp9CmZ1bmN0aW9uIHJuZEJUQ0koZCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1pbmQtYXJlYScpO2lmKCFlbHx8IWQpcmV0dXJuOwogIGlmKGQuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7cGFkZGluZzoxMHB4O2ZvbnQtc2l6ZToxMnB4Ij7ij7MgJytkLmVycm9yKyc8L2Rpdj4nO3JldHVybjt9CiAgbGV0IGg9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NXB4Ij4nOwogIGlmKGQucnNpX3NlbWFuYWwhPW51bGwpe2NvbnN0IHJ2PWQucnNpX3NlbWFuYWwscmM9cnY8MzA/J29rJzpydj43MD8nZG93bic6J3dhcm4nO2grPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iaXYgJytyYysnIj4nK3J2LnRvRml4ZWQoMSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JysocnY8MzA/J1NvYnJldmVuZGEg4pqhJzpydj43MD8nU29icmVjb21wcmEg4pqgJzonTmV1dHJvJykrJzwvZGl2PjwvZGl2Pic7RSgnYnRjLXJzaScscnYudG9GaXhlZCgxKSk7fQogIGlmKGQubW01MF9zZW1hbmFsKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1NIDUwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4kJytOdW1iZXIoZC5tbTUwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZC5tbTIwMF9zZW1hbmFsKWgrPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1NIDIwMCBzZW0uPC9kaXY+PGRpdiBjbGFzcz0iaXYgd2FybiI+JCcrTnVtYmVyKGQubW0yMDBfc2VtYW5hbCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PC9kaXY+JzsKICBpZihkLm1hY2RfaGlzdG9ncmFtIT1udWxsKXtjb25zdCBtaD1kLm1hY2RfaGlzdG9ncmFtO2grPSc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1BQ0QgSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiAnKyhtaD4wPydvayc6J2Rvd24nKSsnIj4nK051bWJlcihtaCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6M3B4Ij4nKyhtaD4wPydNb21lbnR1bSDilrInOidNb21lbnR1bSDilrwnKSsnPC9kaXY+PC9kaXY+Jzt9CiAgaWYoZC5vYnZfdHJlbmQpaCs9JzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+T0JWPC9kaXY+PGRpdiBjbGFzcz0iaXYgJysoZC5vYnZfdHJlbmQ9PT0nc3ViaW5kbyc/J29rJzonZG93bicpKyciPicrZC5vYnZfdHJlbmQrJzwvZGl2PjwvZGl2Pic7CiAgaCs9JzwvZGl2Pic7ZWwuaW5uZXJIVE1MPWg7CiAgaWYoZC5wcmljZSlFKCdidGMtaW5kLXAnLCckJytOdW1iZXIoZC5wcmljZSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7Cn0KZnVuY3Rpb24gcm5kQlRDQyhkKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWN5Y2xlLWFyZWEnKTtpZighZWx8fCFkfHxkLmVycm9yKXJldHVybjsKICBjb25zdCBmVTI9dj0+dj8nJCcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CiAgZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjVweDttYXJnaW4tYm90dG9tOjlweCI+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk1WUlYgWi1TY29yZTwvZGl2PjxkaXYgY2xhc3M9Iml2ICcrKGQubXZydl96c2NvcmU/LnZhbHVlPDE/J29rJzpkLm12cnZfenNjb3JlPy52YWx1ZTwzPyd3YXJuJzonZG93bicpKyciPicrZC5tdnJ2X3pzY29yZT8udmFsdWUrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JytkLm12cnZfenNjb3JlPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPk5VUEw8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nKygoZC5udXBsPy52YWx1ZXx8MCkqMTAwKS50b0ZpeGVkKDApKyclPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4Ij4nK2QubnVwbD8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaWIiPjxkaXYgY2xhc3M9ImlsIj5QdWVsbCBNdWx0aXBsZTwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrZC5wdWVsbD8udmFsdWUrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JytkLnB1ZWxsPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPjIwMFcgTUE8L2Rpdj48ZGl2IGNsYXNzPSJpdiB3YXJuIj4nK2ZVMihkLm1hMjAwdykrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JysoZC5tYTIwMHdfcGN0PycrJytkLm1hMjAwd19wY3QrJyUnOicnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpYiI+PGRpdiBjbGFzcz0iaWwiPlJhaW5ib3cgQmFuZDwvZGl2PjxkaXYgY2xhc3M9Iml2IHdhcm4iPicrKGQucmFpbmJvdz8uYmFuZHx8J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImliIj48ZGl2IGNsYXNzPSJpbCI+UGkgQ3ljbGUgRGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpdiBvayI+JytmVTIoZC5waV9jeWNsZT8uZGlzdGFuY2UpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzwvZGl2PjxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo5cHg7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tYWNjZW50KSI+JysoZC5waV9jeWNsZT8uc2lnbmFsfHwnJykrJzwvZGl2Pic7Cn0KYXN5bmMgZnVuY3Rpb24gbG9hZEluZCgpewogIGNvbnN0IHd0PShwLG1zLGZiKT0+UHJvbWlzZS5yYWNlKFtwLG5ldyBQcm9taXNlKHI9PnNldFRpbWVvdXQoKCk9PnIoZmIpLG1zKSldKTsKICBjb25zdFtiaSxiY109YXdhaXQgUHJvbWlzZS5hbGwoW3d0KGZCVENJKCksMTUwMDAse2Vycm9yOidUaW1lb3V0J30pLHd0KGZCVENDKCksMTUwMDAsbnVsbCldKTsKICBybmRCVENJKGJpKTtybmRCVENDKGJjKTtmRkcoKTsKICBjb25zdCBzdG9ja3M9W1snUEVUUjQuU0EnLCdwZXRyNCddLFsnVkFMRTMuU0EnLCd2YWxlMyddLFsnQkJBUzMuU0EnLCdiYmFzMyddLFsnQVhJQTMuU0EnLCdheGlhMyddLFsnUk9YTzM0LlNBJywncm94bzM0J11dOwogIGNvbnN0IHJlcz1hd2FpdCBQcm9taXNlLmFsbChzdG9ja3MubWFwKChbdF0pPT53dChmSW5kKHQpLDMwMDAwLHtlcnJvcjonVGltZW91dCAzMHMnfSkpKTsKICBzdG9ja3MuZm9yRWFjaCgoWyxpZF0saSk9PnJuZEluZChpZCxyZXNbaV0pKTsKfQphc3luYyBmdW5jdGlvbiBybCh0ayl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodGsrJy1pbmQnKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDFzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+JzsKICBjb25zdCBtPXtwZXRyNDonUEVUUjQuU0EnLHZhbGUzOidWQUxFMy5TQScsYmJhczM6J0JCQVMzLlNBJyxheGlhMzonQVhJQTMuU0EnLHJveG8zNDonUk9YTzM0LlNBJ307CiAgcm5kSW5kKHRrLGF3YWl0IGZJbmQobVt0a10pKTsKfQpjb25zdCBGTEFHUz17J1VTRCc6J/Cfh7rwn4e4JywnVVMnOifwn4e68J+HuCcsJ0JSTCc6J/Cfh6fwn4e3JywnQlInOifwn4en8J+HtycsJ0VVUic6J/Cfh6rwn4e6JywnRVUnOifwn4eq8J+HuicsJ0dCUCc6J/Cfh6zwn4enJywnQ05ZJzon8J+HqPCfh7MnLCdKUFknOifwn4ev8J+HtScsJ0NBRCc6J/Cfh6jwn4emJywnQVVEJzon8J+HpvCfh7onLCdERSc6J/Cfh6nwn4eqJywnTlpEJzon8J+Hs/Cfh78nLCdDSEYnOifwn4eo8J+HrSd9Owphc3luYyBmdW5jdGlvbiBsb2FkQ2FsKCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbC1hcmVhJyksc3Q9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbC1zdCcpOwogIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlcjthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2Pic7CiAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9J0J1c2NhbmRvIGV2ZW50b3MuLi4nOwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQisnL2NhbGVuZGFyJyx7Y2FjaGU6J25vLXN0b3JlJ30pOwogICAgaWYoIXIub2spdGhyb3cgbmV3IEVycm9yKCdIVFRQICcrci5zdGF0dXMpOwogICAgY29uc3QgZXZzPWF3YWl0IHIuanNvbigpOwogICAgaWYoZXZzLmVycm9yKXRocm93IG5ldyBFcnJvcihldnMuZXJyb3IpOwogICAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9ZXZzLmxlbmd0aD4wP2V2cy5sZW5ndGgrJyBldmVudG9zIGNhcnJlZ2Fkb3MnOidTZW0gZXZlbnRvcyc7CiAgICBpZighZXZzLmxlbmd0aCl7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJwYWRkaW5nOjIwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtYWxpZ246Y2VudGVyIj5TZW0gZXZlbnRvcyBkaXNwb27DrXZlaXM8L2Rpdj4nO3JldHVybjt9CiAgICBjb25zdCBieUQ9e307ZXZzLmZvckVhY2goZT0+e2NvbnN0IGR0PShlLmRhdGV8fCcnKS5zbGljZSgwLDEwKTtpZighYnlEW2R0XSlieURbZHRdPVtdO2J5RFtkdF0ucHVzaChlKTt9KTsKICAgIGxldCBoPScnOwogICAgT2JqZWN0LmtleXMoYnlEKS5zb3J0KCkuZm9yRWFjaChkdD0+ewogICAgICBjb25zdCBkPW5ldyBEYXRlKGR0KydUMTI6MDA6MDAnKSxsYmw9ZC50b0xvY2FsZURhdGVTdHJpbmcoJ3B0LUJSJyx7d2Vla2RheTonbG9uZycsZGF5OicyLWRpZ2l0Jyxtb250aDonc2hvcnQnfSk7CiAgICAgIGgrPSc8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJhIj7wn5OFPC9zcGFuPiAnK2xibCsnPC9kaXY+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjEycHgiPicrCiAgICAgICAgJzxkaXYgY2xhc3M9ImNoIj48c3Bhbj5QYcOtczwvc3Bhbj48c3Bhbj5Ib3JhPC9zcGFuPjxzcGFuPkV2ZW50bzwvc3Bhbj48c3Bhbj5JbXA8L3NwYW4+PHNwYW4+UmVhbGl6YWRvPC9zcGFuPjxzcGFuPlByZXZpc3RvPC9zcGFuPjwvZGl2Pic7CiAgICAgIGJ5RFtkdF0uZm9yRWFjaChlPT57CiAgICAgICAgY29uc3QgaWM9ZS5pbXBvcnRhbmNlPj0zPyd2YXIoLS1yZWQpJzplLmltcG9ydGFuY2U+PTI/J3ZhcigtLXdhcm4pJzondmFyKC0tbXV0ZWQpJzsKICAgICAgICBjb25zdCBhYz1lLnNpZ25hbD09PSdiZWF0Jz8ndmFyKC0tZ3JlZW4pJzplLnNpZ25hbD09PSdtaXNzJz8ndmFyKC0tcmVkKSc6J3ZhcigtLXRleHQpJzsKICAgICAgICBoKz0nPGRpdiBjbGFzcz0iY3IiPjxzcGFuPicrKGUuZmxhZ3x8RkxBR1NbZS5jb3VudHJ5XXx8J/CfjJAnKSsnPC9zcGFuPjxzcGFuIGNsYXNzPSJjdCI+JysoZS50aW1lfHwn4oCUJykrJzwvc3Bhbj48c3BhbiBjbGFzcz0iY24yIiB0aXRsZT0iJysoZS5ldmVudHx8JycpKyciPicrKGUuZXZlbnR8fCcnKSsnPC9zcGFuPjxzcGFuIHN0eWxlPSJ0ZXh0LWFsaWduOmNlbnRlcjtjb2xvcjonK2ljKyciPicrJ+KXjycucmVwZWF0KE1hdGgubWluKGUuaW1wb3J0YW5jZSwzKSkrJzwvc3Bhbj48c3BhbiBjbGFzcz0iY2EiIHN0eWxlPSJjb2xvcjonK2FjKyciPicrKGUuYWN0dWFsfHwn4oCUJykrJzwvc3Bhbj48c3BhbiBjbGFzcz0iY2YiPicrKGUuZm9yZWNhc3R8fCfigJQnKSsnPC9zcGFuPjwvZGl2Pic7CiAgICAgIH0pOwogICAgICBoKz0nPC9kaXY+JzsKICAgIH0pOwogICAgZWwuaW5uZXJIVE1MPWg7CiAgfWNhdGNoKGUpewogICAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9J0Vycm8nOwogICAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1yZWQpO3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTJweCI+RXJybzogJytlLm1lc3NhZ2UrJzwvZGl2Pic7CiAgfQp9CmFzeW5jIGZ1bmN0aW9uIG1haW4oKXsKICB0cnl7CiAgICBjb25zdFssdHYsZnRdPWF3YWl0IFByb21pc2UuYWxsKFtmSEwoKSxmVFYoKSxmRnV0KCldKTsKICAgIGNvbnN0IG5vdz1uZXcgRGF0ZSgpLnRvTG9jYWxlVGltZVN0cmluZygncHQtQlInKTsKICAgIEUoJ2xhc3QtdXBkYXRlJywn4oa7ICcrbm93KTtFKCdmb290ZXItdGltZScsbm93KTsKICAgIGRvTWFjcm8odHYsZnQpO2RvUG9zKHR2KTsKICAgIHNldFRpbWVvdXQoZkZ1bmQsMzAwMCk7CiAgICBzZXRUaW1lb3V0KGFzeW5jKCk9Pnt0cnl7Y29uc3RbYmksYmNdPWF3YWl0IFByb21pc2UuYWxsKFtmQlRDSSgpLGZCVENDKCldKTtpZihiaSlybmRCVENJKGJpKTtpZihiYylybmRCVENDKGJjKTtmRkcoKTt9Y2F0Y2goZSl7fX0sNTAwMCk7CiAgICBjb25zdCBob2plPW5ldyBEYXRlKCk7CiAgICBjb25zdCBkUD1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMTItMTcnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZFY9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI3LTAyLTE4JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRBPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0wOS0xNCcpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkQWI9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTEwLTAyJyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRSPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0wNy0xNicpLWhvamUpLzg2NGU1KSk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQygnUEVUUjQuU0EnLDMwLjg1LGRQLCdwdC1tYy1sJywncHQtbWMtcicsJ3B0LW1jLXMnLCdwdC1tYy12JywncHQtbWMtaScsJ3B0LW1jLXJ0JyksNjAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQygnVkFMRTMuU0EnLDU3LjQwLGRWLCd2bC1tYy1sJywndmwtbWMtcicsJ3ZsLW1jLXMnLCd2bC1tYy12JywndmwtbWMtaScsJ3ZsLW1jLXJ0JyksMTIwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUNCKCdBWElBMy5TQScsNTQuMzEsNDMuNTEsNjguNzYsZEEsJ2EzJyksMTgwMDApOwogICAgc2V0VGltZW91dCgoKT0+TUNCKCdBWElBMy5TQScsNTAuNjUsNDAuNTIsNjIuODEsZEFiLCdhM2InKSwyNDAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT5NQ1IoJ1JPWE8zNC5TQScsMTIuODgsMTAuNTAsZFIpLDMwMDAwKTsKICAgIHdpbmRvdy5fSUw9ZmFsc2U7CiAgfWNhdGNoKGUpe2NvbnNvbGUuZXJyb3IoZSk7fQp9Cm1haW4oKTtzZXRJbnRlcnZhbChtYWluLDEyMDAwMCk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4=").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
