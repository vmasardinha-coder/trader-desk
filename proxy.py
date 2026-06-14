"""  # v8.5
Trader Desk — Proxy Server v8.5
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
    all_events = []
    currencies_ok = {'USD','BRL','EUR','GBP','CNY','JPY','CAD','AUD','DE'}
    flag_map = {'USD':'🇺🇸','BRL':'🇧🇷','EUR':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳','JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺','DE':'🇩🇪'}
    imp_map = {'Low':1,'Medium':2,'High':3,'Holiday':0}

    ua_list = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Trader-Desk/1.0',
    ]
    urls = [
        'https://nfs.faireconomy.media/ff_calendar_thisweek.json',
        'https://nfs.faireconomy.media/ff_calendar_nextweek.json',
    ]
    for url in urls:
        for ua in ua_list:
            try:
                r = requests.get(url, headers={
                    'User-Agent': ua,
                    'Accept': 'application/json, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.forexfactory.com/',
                }, timeout=12)
                if r.ok and len(r.text) > 100:
                    for e in r.json():
                        cur = e.get('country', e.get('currency',''))
                        if not cur or cur not in currencies_ok: continue
                        imp = imp_map.get(e.get('impact',''),0)
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
                        actual   = e.get('actual') or None
                        forecast = e.get('forecast') or None
                        previous = e.get('previous') or None
                        signal = None
                        if actual and forecast:
                            try:
                                a=float(str(actual).replace('%','').replace('K','000').replace('M','000000'))
                                f=float(str(forecast).replace('%','').replace('K','000').replace('M','000000'))
                                signal='beat' if a>=f else 'miss'
                            except: pass
                        all_events.append({
                            'date':date_str,'time':time_str,
                            'country':cur,'flag':flag_map.get(cur,'🌐'),
                            'event':e.get('title',''),
                            'importance':imp,
                            'actual':actual,'forecast':forecast,'previous':previous,'signal':signal,
                        })
                    break
            except: continue

    # Fallback TradingView Economic Calendar
    if not all_events:
        try:
            from datetime import datetime as _dt2, timedelta as _td
            today = _dt2.utcnow()
            end = today + _td(days=14)
            r_tv = requests.post(
                'https://economic-calendar.tradingview.com/events',
                json={
                    "from": today.strftime('%Y-%m-%dT00:00:00Z'),
                    "to": end.strftime('%Y-%m-%dT23:59:59Z'),
                    "countries": ["US","BR","EU","GB","CN","JP","CA","AU"],
                    "importance": [1,2],
                },
                headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'},
                timeout=10)
            if r_tv.ok:
                for e in r_tv.json().get('result',[]):
                    cur = e.get('country','')
                    if cur not in currencies_ok: continue
                    imp_tv = e.get('importance',0)
                    if imp_tv < 1: continue
                    raw_date = e.get('date','')
                    try:
                        from datetime import datetime as _dt3, timedelta as _td3, timezone as _tz3
                        dt = _dt3.fromisoformat(raw_date.replace('Z','+00:00'))
                        dt_brt = dt.astimezone(_tz3(_td3(hours=-3)))
                        date_str = dt_brt.strftime('%Y-%m-%d')
                        time_str = dt_brt.strftime('%H:%M')
                    except:
                        date_str = raw_date[:10]
                        time_str = raw_date[11:16] if 'T' in raw_date else ''
                    all_events.append({
                        'date':date_str,'time':time_str,
                        'country':cur,'flag':flag_map.get(cur,'🌐'),
                        'event':e.get('title',e.get('description','')),
                        'importance':imp_tv+1,
                        'actual':e.get('actual'),'forecast':e.get('consensus'),
                        'previous':e.get('previous'),'signal':None,
                    })
        except: pass

    all_events.sort(key=lambda x:(x.get('date',''),x.get('time','')))
    return jsonify(all_events)

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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjIgLSAyMDI2LTA2LTEzIC0tPgo8aHRtbCBsYW5nPSJwdC1CUiI+CjxoZWFkPgo8bWV0YSBjaGFyc2V0PSJVVEYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5UcmFkZXIgRGVzazwvdGl0bGU+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDMwMDs0MDA7NjAwOzcwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQo6cm9vdHstLWJnOiMwYTBhMGE7LS1iZzI6IzExMTstLWJnMzojMTgxODE4Oy0tdGV4dDojZThlOGU4Oy0tbXV0ZWQ6IzU1NTstLWJvcmRlcjojMWUxZTFlOy0tYWNjZW50OiNmMGE1MDA7LS1ncmVlbjojMDBjODUzOy0tcmVkOiNmZjE3NDQ7LS13YXJuOiNmZjk4MDA7LS1kYW5nZXI6I2ZmMTc0NDstLWJsdWU6IzIxOTZmMzstLWl0bTojZmY0NDQ0Oy0tcHVycGxlOiM5YzI3YjB9CmJvZHl7YmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6Ljc1cmVtO3BhZGRpbmc6MTRweDttYXgtd2lkdGg6NjQwcHg7bWFyZ2luOjAgYXV0b30KCi8qIEhlYWRlciAqLwouaGRye2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxNHB4O3BhZGRpbmctYm90dG9tOjEwcHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKX0KLmhkci10aXRsZXtmb250LXNpemU6Ljk1cmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO2xldHRlci1zcGFjaW5nOi4wNWVtfQouaGRyLXRpbWV7Zm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKX0KCi8qIFRhYnMgKi8KLnRhYnN7ZGlzcGxheTpmbGV4O2dhcDozcHg7bWFyZ2luLWJvdHRvbToxNHB4O292ZXJmbG93LXg6YXV0bzt3aGl0ZS1zcGFjZTpub3dyYXA7cGFkZGluZy1ib3R0b206MnB4fQoudGFie3BhZGRpbmc6NXB4IDExcHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6LjU4cmVtO2xldHRlci1zcGFjaW5nOi4wN2VtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7ZmxleC1zaHJpbms6MDt0cmFuc2l0aW9uOmFsbCAuMTVzfQoudGFiOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS1tdXRlZCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci50YWIuYWN0aXZle2JhY2tncm91bmQ6dmFyKC0tYWNjZW50KTtjb2xvcjojMDAwO2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtd2VpZ2h0OjcwMH0KLnRhYi1jb250ZW50e2Rpc3BsYXk6bm9uZX0udGFiLWNvbnRlbnQuYWN0aXZle2Rpc3BsYXk6YmxvY2t9CgovKiBTZWN0aW9uIGhlYWRlcnMgKi8KLnNlY3tmb250LXNpemU6LjVyZW07bGV0dGVyLXNwYWNpbmc6LjE0ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEwcHggMCA1cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjhweDtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHh9Ci5zZWMgc3Bhbntjb2xvcjp2YXIoLS1hY2NlbnQpfS5zcmN7Y29sb3I6dmFyKC0tYm9yZGVyKTtmb250LXNpemU6LjQ4cmVtfQoKLyogQ2FyZHMgZ3JpZCAqLwouZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjVweDttYXJnaW4tYm90dG9tOjEycHh9Ci5jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo5cHggOHB4O3RyYW5zaXRpb246Ym9yZGVyLWNvbG9yIC4xNXM7cG9zaXRpb246cmVsYXRpdmV9Ci5jYXJkOmhvdmVye2JvcmRlci1jb2xvcjojMzMzfQouY2FyZC5ncmVlbntib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1ncmVlbil9LmNhcmQuYmx1ZXtib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1ibHVlKX0KLmNhcmQud2Fybntib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS13YXJuKX0uY2FyZC5yZWR7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tcmVkKX0KLmMtbGFiZWx7Zm9udC1zaXplOi40NHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206MnB4fQouYy1uYW1le2ZvbnQtc2l6ZTouNThyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLXRleHQpO21hcmdpbi1ib3R0b206M3B4fQouYy1wcmljZXtmb250LXNpemU6LjgycmVtO2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS1hY2NlbnQpfQouYy1wcmljZS5sb2FkaW5ne2NvbG9yOnZhcigtLW11dGVkKTthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZTtmb250LXNpemU6LjY1cmVtfQouYy1jaGFuZ2V7Zm9udC1zaXplOi41cmVtO21hcmdpbi10b3A6MnB4fQouY2hnLXVwe2NvbG9yOnZhcigtLWdyZWVuKX0uY2hnLWRue2NvbG9yOnZhcigtLXJlZCl9LmNoZy1mbGF0e2NvbG9yOnZhcigtLW11dGVkKX0KQGtleWZyYW1lcyBwdWxzZXswJSwxMDAle29wYWNpdHk6MX01MCV7b3BhY2l0eTouMzV9fQoKLyogU2VjdG9yIGFjY29yZGlvbiAqLwouc2VjdG9yLWhlYWRlcntiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6N3B4IDEycHg7Y3Vyc29yOnBvaW50ZXI7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtmb250LXNpemU6LjU4cmVtO2xldHRlci1zcGFjaW5nOi4wN2VtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHg7dHJhbnNpdGlvbjphbGwgLjE1c30KLnNlY3Rvci1oZWFkZXI6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zZWN0b3ItYm9keXtkaXNwbGF5Om5vbmU7cGFkZGluZy10b3A6NHB4fQoKLyogUG9zaXRpb24gY2FyZHMgKi8KLnBvcy1jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQ6M3B4IHNvbGlkIHZhcigtLWFjY2VudCk7cGFkZGluZzoxMnB4O21hcmdpbi1ib3R0b206OHB4fQoucG9zLWxhYmVse2ZvbnQtc2l6ZTouNDhyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi4wNmVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjNweH0KLnBvcy10aWNrZXJ7Zm9udC1zaXplOjEuMDVyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOnZhcigtLWFjY2VudCk7bWFyZ2luLWJvdHRvbToycHh9Ci5wb3MtcHJpY2V7Zm9udC1zaXplOjEuMjVyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLXRleHQpfS5wb3MtcHJpY2UubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOi45cmVtfQoucG9zLWNoZ3tmb250LXNpemU6LjZyZW07bWFyZ2luLWJvdHRvbTo4cHh9Ci5zYntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmctdG9wOjhweDttYXJnaW4tdG9wOjhweH0KLnNiLXJvd3tkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6M3B4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtmb250LXNpemU6LjU4cmVtfQouc2ItbGJse2NvbG9yOnZhcigtLW11dGVkKX0uc2ItdmFse2NvbG9yOnZhcigtLXRleHQpO3RleHQtYWxpZ246cmlnaHQ7bWF4LXdpZHRoOjYyJX0KLnNiLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LnNiLXZhbC53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zYi12YWwuaXRte2NvbG9yOnZhcigtLWl0bSl9Ci5zaWduYWx7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweDttYXJnaW4tdG9wOjhweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLnNpZy10aXRsZXtmb250LXNpemU6LjVyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2NvbG9yOnZhcigtLW11dGVkKX0KLmluZC1ib3h7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjhweDt0ZXh0LWFsaWduOmNlbnRlcn0KLmluZC1sYmx7Zm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo0cHh9Ci5pbmQtdmFse2ZvbnQtc2l6ZTouOTVyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOnZhcigtLXRleHQpfQouaW5kLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LmluZC12YWwud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaW5kLXZhbC5kb3due2NvbG9yOnZhcigtLXJlZCl9CgovKiBJbmRpY2Fkb3JlcyBjb20gZXhwbGljYcOnw6NvICovCi5pbmQtcm93e2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQ6MnB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo3cHggMTBweDttYXJnaW4tYm90dG9tOjNweDt0cmFuc2l0aW9uOmJvcmRlci1jb2xvciAuMXN9Ci5pbmQtcm93OmhvdmVye2JvcmRlci1sZWZ0LWNvbG9yOnZhcigtLWFjY2VudCl9Ci5pbmQtcm93LXRvcHtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6YmFzZWxpbmU7bWFyZ2luLWJvdHRvbToycHh9Ci5pbmQtcm93LW5vbWV7Zm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi4wN2VtfQouaW5kLXJvdy12YWx7Zm9udC1zaXplOi43OHJlbTtmb250LXdlaWdodDo3MDB9Ci5pbmQtcm93LXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LmluZC1yb3ctdmFsLmRvd257Y29sb3I6dmFyKC0tcmVkKX0uaW5kLXJvdy12YWwud2Fybntjb2xvcjp2YXIoLS13YXJuKX0KLmluZC1yb3ctZXhwe2ZvbnQtc2l6ZTouNTFyZW07Y29sb3I6IzQ0NDtsaW5lLWhlaWdodDoxLjQ1fQoKLyogU2NvcmUgYm94ICovCi5zY29yZS1ib3h7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyIDFmcjtnYXA6NnB4O21hcmdpbi1ib3R0b206MTBweH0KLnNjb3JlLWNlbGx7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEwcHggOHB4O3RleHQtYWxpZ246Y2VudGVyfQouc2NvcmUtbWV0YXtmb250LXNpemU6LjQ1cmVtO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjA4ZW07bWFyZ2luLWJvdHRvbTo0cHh9Ci5zY29yZS1udW17Zm9udC1zaXplOjEuN3JlbTtmb250LXdlaWdodDo4MDA7bGluZS1oZWlnaHQ6MX0KLnNjb3JlLWxibHtmb250LXNpemU6LjVyZW07bWFyZ2luLXRvcDozcHh9Ci5zY29yZS12YWx7Zm9udC1zaXplOi45NXJlbTtmb250LXdlaWdodDo3MDA7bWFyZ2luLXRvcDoycHh9Ci5zY29yZS1zdWJ7Zm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDoycHh9CgovKiBDYWxlbmTDoXJpbyAqLwouY2FsLWV2ZW50e2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjBweCA0MnB4IDFmciAyMnB4IDU0cHggNTBweDtnYXA6NHB4O2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjVweCAxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOi41OHJlbX0KLmNhbC1ldmVudDpsYXN0LWNoaWxke2JvcmRlci1ib3R0b206bm9uZX0KLmNhbC10aW1le2NvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjUycmVtfQouY2FsLWV2ZW50LW5hbWV7Y29sb3I6dmFyKC0tdGV4dCk7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwfQouY2FsLWltcHt0ZXh0LWFsaWduOmNlbnRlcn0KLmNhbC1hY3R1YWx7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDB9Ci5jYWwtZm9yZWNhc3R7dGV4dC1hbGlnbjpyaWdodDtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi41MnJlbX0KLmNhbC1oZWFkZXJ7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyMHB4IDQycHggMWZyIDIycHggNTRweCA1MHB4O2dhcDo0cHg7cGFkZGluZzozcHggMTBweDtmb250LXNpemU6LjQ0cmVtO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjA3ZW07Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KCmZvb3RlcnttYXJnaW4tdG9wOjE4cHg7cGFkZGluZy10b3A6MTBweDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2Vlbjtmb250LXNpemU6LjVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpfQo8L3N0eWxlPgo8L2hlYWQ+Cjxib2R5Pgo8ZGl2IGNsYXNzPSJoZHIiPgogIDxkaXYgY2xhc3M9Imhkci10aXRsZSI+4pa4IFRSQURFUiBERVNLPC9kaXY+CiAgPGRpdiBjbGFzcz0iaGRyLXRpbWUiIGlkPSJsYXN0LXVwZGF0ZSI+4oCUPC9kaXY+CjwvZGl2Pgo8ZGl2IGNsYXNzPSJ0YWJzIj4KICA8ZGl2IGNsYXNzPSJ0YWIgYWN0aXZlIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ2NvdGFjb2VzJyx0aGlzKSI+8J+TiiBDb3Rhw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ2luZGljYWRvcmVzJyx0aGlzKSI+8J+TiCBJbmRpY2Fkb3JlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3dpdGNoVGFiKCdwb3NpY29lcycsdGhpcykiPvCfkrwgUG9zacOnw7VlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3dpdGNoVGFiKCdjYWxlbmRhcmlvJyx0aGlzKSI+8J+ThSBDYWxlbmTDoXJpbzwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENPVEHDh8OVRVMg4pWQ4pWQIC0tPgo8ZGl2IGlkPSJ0YWItY290YWNvZXMiIGNsYXNzPSJ0YWItY29udGVudCBhY3RpdmUiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+MDE8L3NwYW4+IEVVQSA8c3BhbiBjbGFzcz0ic3JjIj7CtyBwcm94eTwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5TJlAgRVMxKjwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImVzZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImVzZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5OYXNkYXEgTlE8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJucWYtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJucWYtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPsONbmRpY2U8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkRvdyBKb25lczwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImRqaS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImRqaS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgcmVkIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5Wb2xhdGlsaWRhZGU8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlZJWDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InZpeC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9InZpeC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RMOzbGFyIEluZGV4PC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5EWFk8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJkeHktcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJkeHktYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5Dw6JtYmlvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5VU0QvQlJMPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0idXNkLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0idXNkLWMiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+MDI8L3NwYW4+IEIzIOKAlCBUb3AgMTAgPHNwYW4gY2xhc3M9InNyYyI+wrcgVHJhZGluZ1ZpZXc8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj7DjW5kaWNlPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5JQk9WPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iaWJvdi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9Imlib3YtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5GdXR1cm88L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPldJTjEhPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0id2luLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0id2luLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlBFVFI0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0icGV0cjRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0icGV0cjRxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPklUVUI0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iaXR1YjRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iaXR1YjRxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlZBTEUzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0idmFsZTNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0idmFsZTNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJCREM0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYmJkYzRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iYmJkYzRxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkFCRVYzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYWJldjNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iYWJldjNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJCQVMzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYmJhczNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iYmJhczNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPldFR0UzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0id2VnZTNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0id2VnZTNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3YXJuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CRFI8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlJPWE8zNDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InJveG8zNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJyb3hvMzRxLWMiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+8J+Tgjwvc3Bhbj4gQjMgcG9yIFNlZ21lbnRvIDxzcGFuIGNsYXNzPSJzcmMiPsK3IGNsaXF1ZSBwYXJhIGV4cGFuZGlyPC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnZmluYW5jZWlybycpIj48c3Bhbj7wn4+mIEZpbmFuY2Vpcm88L3NwYW4+PHNwYW4gaWQ9InNhcnItZmluYW5jZWlybyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktZmluYW5jZWlybyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWZpbmFuY2Vpcm8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygncGV0cm9sZW8nKSI+PHNwYW4+8J+boiBQZXRyw7NsZW8gJmFtcDsgR8Ohczwvc3Bhbj48c3BhbiBpZD0ic2Fyci1wZXRyb2xlbyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktcGV0cm9sZW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1wZXRyb2xlbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdtaW5lcmFjYW8nKSI+PHNwYW4+4puPIE1pbmVyYcOnw6NvPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1pbmVyYWNhbyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktbWluZXJhY2FvIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbWluZXJhY2FvIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ21hdGVyaWFpcycpIj48c3Bhbj7wn4yyIFBhcGVsICZhbXA7IENlbHVsb3NlPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1hdGVyaWFpcyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktbWF0ZXJpYWlzIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbWF0ZXJpYWlzIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3V0aWxpZGFkZScpIj48c3Bhbj7imqEgVXRpbGlkYWRlIFDDumJsaWNhPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXV0aWxpZGFkZSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktdXRpbGlkYWRlIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtdXRpbGlkYWRlIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ2NvbnN1bW9fY2ljbGljbycpIj48c3Bhbj7wn5uNIENvbnN1bW8gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9InNhcnItY29uc3Vtb19jaWNsaWNvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1jb25zdW1vX2NpY2xpY28iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1jb25zdW1vX2NpY2xpY28iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnY29uc3Vtb19uYW8nKSI+PHNwYW4+8J+bkiBDb25zdW1vIE7Do28gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9InNhcnItY29uc3Vtb19uYW8iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWNvbnN1bW9fbmFvIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtY29uc3Vtb19uYW8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnc2F1ZGUnKSI+PHNwYW4+8J+PpSBTYcO6ZGU8L3NwYW4+PHNwYW4gaWQ9InNhcnItc2F1ZGUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LXNhdWRlIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtc2F1ZGUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnaW5kdXN0cmlhaXMnKSI+PHNwYW4+8J+PlyBCZW5zIEluZHVzdHJpYWlzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLWluZHVzdHJpYWlzIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1pbmR1c3RyaWFpcyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWluZHVzdHJpYWlzIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3RpX3RlbGVjb20nKSI+PHNwYW4+8J+SuyBUSSAmYW1wOyBDb211bmljYcOnw7Vlczwvc3Bhbj48c3BhbiBpZD0ic2Fyci10aV90ZWxlY29tIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS10aV90ZWxlY29tIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtdGlfdGVsZWNvbSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn4e68J+HuDwvc3Bhbj4gRVVBIHBvciBTZWdtZW50bzwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWFnNycpIj48c3Bhbj7irZAgNyBNYWduw61maWNhczwvc3Bhbj48c3BhbiBpZD0ic2Fyci1tYWc3Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1tYWc3Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbWFnNyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCduYXNkYXExNScpIj48c3Bhbj7wn5K7IE5hc2RhcSBUb3AgMTU8L3NwYW4+PHNwYW4gaWQ9InNhcnItbmFzZGFxMTUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LW5hc2RhcTE1Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbmFzZGFxMTUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnc3AyMCcpIj48c3Bhbj7wn5OKIFMmYW1wO1AgNTAwIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0ic2Fyci1zcDIwIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1zcDIwIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtc3AyMCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdkamkyMCcpIj48c3Bhbj7wn4+bIERvdyBKb25lcyBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9InNhcnItZGppMjAiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWRqaTIwIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtZGppMjAiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+PHNwYW4+MDM8L3NwYW4+IENvbW1vZGl0aWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHdhcm4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlBldHLDs2xlbzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+V1RJL0NMPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iY2wtcCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHdhcm4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPk1ldGFsPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5HT0xEPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iZ29sZC1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlNJTFZFUjwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InNpbHZlci1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkNPUFBFUjwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImNvcHBlci1wIj7igJQ8L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPjA0PC9zcGFuPiBCaXRjb2luPC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlNwb3Q8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJUQy9VU0Q8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJidGMtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5CVEMgUlNJPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYnRjLXJzaSI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZ1bmRpbmcgOGg8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJUQyBSYXRlPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYnRjLWZ1bmQiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBibHVlIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5GZWFyICZhbXA7IEdyZWVkPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5JbmRleDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImZnLXZhbCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJmZy1sYmwiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxmb290ZXI+PHNwYW4gaWQ9ImZvb3Rlci10aW1lIj7igJQ8L3NwYW4+PHNwYW4+VHJhZGVyIERlc2sgdjEwLjI8L3NwYW4+PC9mb290ZXI+CjwvZGl2PgoKPCEtLSDilZDilZAgSU5ESUNBRE9SRVMg4pWQ4pWQIC0tPgo8ZGl2IGlkPSJ0YWItaW5kaWNhZG9yZXMiIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj7wn5OKPC9zcGFuPiBDaWNsbyBCaXRjb2luPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWN5Y2xlLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMnB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvIGNpY2xvIEJUQy4uLjwvZGl2PjwvZGl2PgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDEzMHB4O2dhcDo4cHg7bWFyZ2luOjEwcHggMCI+CiAgICA8ZGl2IGlkPSJmZWFyLWdyZWVkLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTJweDt0ZXh0LWFsaWduOmNlbnRlciI+CiAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDhyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206NXB4Ij5CVEMvVVNEPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImJ0Yy1pbmQtcHJpY2UiPuKAlDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj7wn5OKPC9zcGFuPiBJbmRpY2Fkb3JlcyBCVEMgU2VtYW5hbDwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNnJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBQRVRSNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjUycmVtO21hcmdpbi1sZWZ0OjRweCIgb25jbGljaz0icmVsb2FkSW5kKCdwZXRyNCcpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0icGV0cjQtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBWQUxFMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjUycmVtO21hcmdpbi1sZWZ0OjRweCIgb25jbGljaz0icmVsb2FkSW5kKCd2YWxlMycpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0idmFsZTMtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBCQkFTMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjUycmVtO21hcmdpbi1sZWZ0OjRweCIgb25jbGljaz0icmVsb2FkSW5kKCdiYmFzMycpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0iYmJhczMtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBBWElBMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjUycmVtO21hcmdpbi1sZWZ0OjRweCIgb25jbGljaz0icmVsb2FkSW5kKCdheGlhMycpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0iYXhpYTMtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBST1hPMzQgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOi41MnJlbTttYXJnaW4tbGVmdDo0cHgiIG9uY2xpY2s9InJlbG9hZEluZCgncm94bzM0JykiPuKGuzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJyb3hvMzQtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CjwvZGl2PgoKPCEtLSDilZDilZAgUE9TScOHw5VFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1wb3NpY29lcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPjAxPC9zcGFuPiBPcGVyYcOnw7VlcyBBdGl2YXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGFiZWwiPlBldHJvYnJhcyBQTiDCtyBDYWxsIFZlbmRpZGEgwrcgUEVUUkwzMTkgwrcgVmVuYyAxNy8xMi8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIj5QRVRSNDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXByaWNlIGxvYWRpbmciIGlkPSJwdC1wb3MtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icG9zLWNoZyIgaWQ9InB0LXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gUmVmLiBlbnRyYWRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDMwLDg1PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDMwLDg1IChQRVRSTDMxOSk8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gYW8gc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0icHQtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNy8xMi8yMDI2IMK3IDxzcGFuIGlkPSJwdC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLiAoQiZhbXA7Uyk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj40Myw0JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Qcm9iLiBCJmFtcDtTICh2b2wuaW1wbC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+OSw0JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Qcm9iLiBNQyAodm9sLmhpc3QuKSDihpM8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayIgaWQ9Im1jLXB0LXJlYWx0aW1lIj5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdGl0bGUiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gc3ViaXIgYW8gc3RyaWtlPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXB0LWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42MnJlbSI+Q2FsY3VsYW5kbyA1LjAwMCBjZW7DoXJpb3MuLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcHQtcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Qcm9iLiBhdGluZ2lyIHN0cmlrZTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwiIGlkPSJtYy1wdC1zdHJpa2UiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LiB1c2FkYTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLXB0LXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41MnJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHg7bGluZS1oZWlnaHQ6MS41IiBpZD0ibWMtcHQtaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjhweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGFiZWwiPlZhbGUgT04gwrcgQ2FsbCBWZW5kaWRhIMK3IFZBTEVCNTc0IMK3IFZlbmMgMTgvMDIvMjAyNzwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciI+VkFMRTM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wcmljZSBsb2FkaW5nIiBpZD0idmwtcG9zLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBvcy1jaGciIGlkPSJ2bC1wb3MtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJlw6dvIFJlZi4gZW50cmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCA1Nyw0MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA1Nyw0MCAoVkFMRUI1NzQpPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIGFvIHN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIGl0bSIgaWQ9InZsLWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MTgvMDIvMjAyNyDCtyA8c3BhbiBpZD0idmwtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZvbC4gSW1wbC4gKEImYW1wO1MpPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+NzEsMiU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gQiZhbXA7UyAodm9sLmltcGwuKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjE0LDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DICh2b2wuaGlzdC4pIOKGkzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIiBpZD0ibWMtdmwtcmVhbHRpbWUiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBzdWJpciBhbyBzdHJpa2U8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtdmwtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjYycmVtIj5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy12bC1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlByb2IuIGF0aW5naXIgc3RyaWtlPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCIgaWQ9Im1jLXZsLXN0cmlrZSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuIHVzYWRhPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtdmwtdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjUycmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjVweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJtYy12bC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6OHB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy1sYWJlbCI+QVhJQTMgKEEpIMK3IEJpZGlyZWNpb25hbCDCtyBWZW5jIDE0LzA5LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPkFYSUEzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHJpY2UgbG9hZGluZyIgaWQ9ImF4aWEzLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0iYXhpYTMtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTQsMzE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDQzLDUxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktVTyAoKzI2LDYlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDY4LDc2PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4rNCUgZml4bzwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjE0LzA5LzIwMjYgwrcgPHNwYW4gaWQ9ImF4aWEzZi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gS0RPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhMy1rZG8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtVTzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMta3VvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhMy1zdGF0dXMiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXRpdGxlIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBkZSBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhMy1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjJyZW0iPkNhbGN1bGFuZG8gMy4wMDAgY2Vuw6FyaW9zLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzLXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo1cHg7bWFyZ2luLXRvcDo2cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+U2VtIEJhcnJlaXJhIOKchTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy1heGlhMy1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU8g4pqgPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTMta3VvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQmFpeGEgS0RPIPCflLQ8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIGRvd24iIGlkPSJtYy1heGlhMy1rZG8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLWF4aWEzLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41MnJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHgiIGlkPSJtYy1heGlhMy1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6OHB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy1sYWJlbCI+QVhJQTMgKEIpIMK3IEJpZGlyZWNpb25hbCBJT04gSXRhw7ogwrcgVmVuYyAwMi8xMC8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIj5BWElBMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXByaWNlIGxvYWRpbmciIGlkPSJheGlhM2ItcG9zLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBvcy1jaGciIGlkPSJheGlhM2ItcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTAsNjU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDQwLDUyPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktVTyAoKzI0JSk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA2Miw4MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBzLyBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+R2FuaG8gYy8gYmFyLiBhbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+KzQlIGZpeG8gKDEyLDMzJSBhLmEuKTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjAyLzEwLzIwMjYgwrcgPHNwYW4gaWQ9ImF4aWEzYi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gS0RPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhM2Ita2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzYi1rdW8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzYi1zdGF0dXMiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXRpdGxlIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBkZSBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhM2ItbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjYycmVtIj5DYWxjdWxhbmRvIDMuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhM2ItcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjVweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLWF4aWEzYi1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU8g4pqgPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTNiLWt1byI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5CYXIuIEJhaXhhIEtETyDwn5S0PC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBkb3duIiBpZD0ibWMtYXhpYTNiLWtkbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTNiLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41MnJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHgiIGlkPSJtYy1heGlhM2ItaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjhweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGFiZWwiPlJPWE8zNCDCtyBCRFIgTnViYW5rIMK3IFByZWZpeGFkbyBjLyBCYXJyZWlyYSDCtyBWZW5jIDE2LzA3LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPlJPWE8zNDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXByaWNlIGxvYWRpbmciIGlkPSJyb3hvMzQtcG9zLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBvcy1jaGciIGlkPSJyb3hvMzQtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgMTIsODg8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+QmFycmVpcmEgUk9YT0cxMDU8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCAxMCw1MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjE2LzA3LzIwMjYgwrcgPHNwYW4gaWQ9InJveG8zNC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9InJveG8zNC1rZG8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9InJveG8zNC1zdGF0dXMiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXRpdGxlIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIHN1Y2Vzc28gKG7Do28gdG9jYXIgYmFycmVpcmEpPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXJveG8zNC1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjJyZW0iPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcm94bzM0LXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo1cHg7bWFyZ2luLXRvcDo2cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UHJvYi4gU3VjZXNzbzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy1yb3hvMzQtc3VjZXNzbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5DYWxsIEV4ZXJjaWRhPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCIgaWQ9Im1jLXJveG8zNC1jYWxsIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPktETyBBdGluZ2lkbzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwiIGlkPSJtYy1yb3hvMzQta2RvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1yb3hvMzQtdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjUycmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjVweCIgaWQ9Im1jLXJveG8zNC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxzcGFuPvCfk4E8L3NwYW4+IEVuY2VycmFkYXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im9wYWNpdHk6LjY7Ym9yZGVyLWNvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjVweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouODVyZW0iPkJCQVMzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlIEJCQVNIMjE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgMjEsNjUgwrcgUmVmIFIkIDIwLDY3PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj7inIUgODAlIGRvIGFsdm8gZW0gNzAlIGRvIHByYXpvPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJvcGFjaXR5Oi42O2JvcmRlci1jb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6Ljg1cmVtIj5BWElBMyBTaG9ydCBTdHJhbmdsZTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkNhbGwgVi4gQVhJQUk1MDU8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTAsNTA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSBBw6fDtWVzIGxpYmVyYWRhczwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ib3BhY2l0eTouNjtib3JkZXItY29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NXB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi44NXJlbSI+Uk9YTzM0IFByZWZpeGFkbyA3LDElPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RW5jZXJyYWRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjA0LzA2LzIwMjY8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSB+NSwxNyUgKDcyJSBkbyBhbHZvKTwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENBTEVORMOBUklPIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWNhbGVuZGFyaW8iIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjEwcHgiPgogICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCkiPvCfh7rwn4e4IPCfh6fwn4e3IPCfh6rwn4e6IPCfh6zwn4enIPCfh6jwn4ezIPCfh6/wn4e1IPCfh6nwn4eqIPCfh6jwn4emIMK3IEltcGFjdG8gTcOpZGlvKzwvZGl2PgogICAgPGJ1dHRvbiBvbmNsaWNrPSJsb2FkQ2FsZW5kYXIoKSIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tYWNjZW50KTtwYWRkaW5nOjRweCAxMHB4O2ZvbnQtc2l6ZTouNThyZW07Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtsZXR0ZXItc3BhY2luZzouMDVlbSI+4oa7IEF0dWFsaXphcjwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgaWQ9ImNhbGVuZGFyLXN0YXR1cyIgc3R5bGU9ImZvbnQtc2l6ZTouNXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo2cHg7bWluLWhlaWdodDoxNHB4Ij48L2Rpdj4KICA8ZGl2IGlkPSJjYWxlbmRhci1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42MnJlbTtwYWRkaW5nOjIwcHg7dGV4dC1hbGlnbjpjZW50ZXIiPkNsaXF1ZSBlbSBBdHVhbGl6YXIgcGFyYSBjYXJyZWdhciBldmVudG9zPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgQkFTRT0naHR0cHM6Ly90cmFkZXItZGVzay5vbnJlbmRlci5jb20nOwpjb25zdCBTRUc9ewogICdmaW5hbmNlaXJvJzpbJ0lUVUI0JywnQkJEQzQnLCdCQkFTMycsJ1NBTkIxMScsJ0IzU0EzJywnQlBBQzExJywnSVRTQTQnLCdCUlNSNicsJ0FCQ0I0JywnQk1HQjQnXSwKICAncGV0cm9sZW8nOlsnUEVUUjQnLCdQRVRSMycsJ1BSSU8zJywnQlJBVjMnLCdWQkJSMycsJ0NTQU4zJywnUkVDVjMnLCdVR1BBMycsJ1NFUUwzJywnRU5BVDMnXSwKICAnbWluZXJhY2FvJzpbJ1ZBTEUzJywnR0dCUjQnLCdDU05BMycsJ1VTSU01JywnQlJBUDQnLCdGRVNBNCcsJ0NNSU4zJywnQ0JBVjMnLCdHT0FVNCcsJ1BHTU4zJ10sCiAgJ21hdGVyaWFpcyc6WydTVVpCMycsJ0tMQk4xMScsJ0RYQ08zJywnVU5JUDYnLCdSQU5JMycsJ09SVlIzJywnU01UTzMnLCdGUkFTMycsJ0xQU0IzJywnRFRFWDMnXSwKICAndXRpbGlkYWRlJzpbJ0FYSUEzJywnRVFUTDMnLCdDUEZFMycsJ1NCU1AzJywnQ01JRzQnLCdFTkdJMTEnLCdUQUVFMTEnLCdBVVJFMycsJ0VHSUUzJywnQ1BMRTMnXSwKICAnY29uc3Vtb19jaWNsaWNvJzpbJ1JFTlQzJywnTFJFTjMnLCdNR0xVMycsJ0NZUkUzJywnTVJWRTMnLCdBWlpBMycsJ1ZJVkEzJywnU0JGRzMnLCdDVkNCMycsJ0xXU0EzJ10sCiAgJ2NvbnN1bW9fbmFvJzpbJ0FCRVYzJywnSkJTUzMnLCdCUkZTMycsJ05BVFUzJywnTURJQTMnLCdCRUVGMycsJ1NMQ0UzJywnTVRSRTMnLCdDQU1MMycsJ1BDQVIzJ10sCiAgJ3NhdWRlJzpbJ1JET1IzJywnSEFQVjMnLCdGTFJZMycsJ0RBU0EzJywnUVVBTDMnLCdPTkNPMycsJ1BOVkwzJywnT0RQVjMnLCdNQVREMycsJ0FBTFIzJ10sCiAgJ2luZHVzdHJpYWlzJzpbJ1dFR0UzJywnRU1CUjMnLCdSQUlMMycsJ1RHTUEzJywnUk9NSTMnLCdWTElEMycsJ1RVUFkzJywnSVJCUjMnLCdQT01PNCcsJ0ZSQVMzJ10sCiAgJ3RpX3RlbGVjb20nOlsnVklWVDMnLCdUSU1TMycsJ1RPVFZTMycsJ09JQlIzJywnTFdTQTMnLCdNTEFTMycsJ0FOSU0zJywnUE9TSTMnLCdJTlRCMycsJ0JSSVQzJ10sCn07CmNvbnN0IFVTX1NFRz17CiAgJ21hZzcnOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ0dPT0dMJywnTUVUQScsJ1RTTEEnXSwKICAnbmFzZGFxMTUnOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQ09TVCcsJ05GTFgnLCdRQ09NJywnQU1EJywnQURCRScsJ0lOVEMnLCdDU0NPJ10sCiAgJ3NwMjAnOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQlJLLkInLCdKUE0nLCdMTFknLCdWJywnVU5IJywnWE9NJywnTUEnLCdORkxYJywnUEcnLCdKTkonLCdIRCcsJ0JBQyddLAogICdkamkyMCc6WydVTkgnLCdHUycsJ0hEJywnU0hXJywnQ0FUJywnQVhQJywnTUNEJywnQU1HTicsJ1YnLCdUUlYnLCdJQk0nLCdKUE0nLCdIT04nLCdDUk0nLCdDVlgnLCdBQVBMJywnTVNGVCcsJ0RJUycsJ05LRScsJ0JBJ10KfTsKY29uc3QgZkJSTD12PT52IT1udWxsPydSJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmVVNEPXY9PnYhPW51bGw/J1VTJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmUFRTPXY9PnYhPW51bGw/TnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CmZ1bmN0aW9uIHNldEVsKGlkLHR4dCl7Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuO2UudGV4dENvbnRlbnQ9dHh0O2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KZnVuY3Rpb24gc2V0Q2hnKGlkLG5vdyxwcmV2LHR5cGUpe2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKCFlKXJldHVybjtjb25zdCBkaWZmPW5vdy1wcmV2O2NvbnN0IHBjdD0oZGlmZi9NYXRoLmFicyhwcmV2fHwxKSoxMDApLnRvRml4ZWQoMik7Y29uc3Qgc2lnbj1kaWZmPj0wPycrJzonJztpZih0eXBlPT09J2JybCcpZS50ZXh0Q29udGVudD1zaWduKydSJCAnK01hdGguYWJzKGRpZmYpLnRvRml4ZWQoMikrJyAoJytzaWduK3BjdCsnJSknO2Vsc2UgaWYodHlwZT09PSd1c2QnKWUudGV4dENvbnRlbnQ9c2lnbitkaWZmLnRvRml4ZWQoMikrJyAoJytzaWduK3BjdCsnJSknO2Vsc2UgZS50ZXh0Q29udGVudD1zaWduK01hdGguYWJzKGRpZmYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJyAoJytzaWduK3BjdCsnJSknO2UuY2xhc3NOYW1lPSdjLWNoYW5nZSAnKyhkaWZmPjA/J2NoZy11cCc6ZGlmZjwwPydjaGctZG4nOidjaGctZmxhdCcpO30KZnVuY3Rpb24gc3dpdGNoVGFiKHRhYixlbCl7ZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYicpLmZvckVhY2godD0+dC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7ZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYi1jb250ZW50JykuZm9yRWFjaCh0PT50LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndGFiLScrdGFiKS5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTtpZihlbCllbC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTtpZih0YWI9PT0naW5kaWNhZG9yZXMnJiYhd2luZG93Ll9pbmRMb2FkZWQpe3dpbmRvdy5faW5kTG9hZGVkPXRydWU7bG9hZEluZGljYXRvcnMoKTt9aWYodGFiPT09J2NhbGVuZGFyaW8nKWxvYWRDYWxlbmRhcigpO30KZnVuY3Rpb24gdG9nZ2xlU2VnKGlkKXtjb25zdCBiPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYm9keS0nK2lkKTtjb25zdCBhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYXJyLScraWQpO2lmKCFiKXJldHVybjtjb25zdCBvcGVuPWIuc3R5bGUuZGlzcGxheSE9PSdibG9jayc7Yi5zdHlsZS5kaXNwbGF5PW9wZW4/J2Jsb2NrJzonbm9uZSc7aWYoYSlhLnRleHRDb250ZW50PW9wZW4/J+KWsic6J+KWvCc7aWYob3BlbiYmIWIuZGF0YXNldC5sb2FkZWQpe2IuZGF0YXNldC5sb2FkZWQ9JzEnO2xvYWRTZWdtZW50KGlkKTt9fQoKYXN5bmMgZnVuY3Rpb24gbG9hZFNlZ21lbnQoaWQpewogIGNvbnN0IGdyaWQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NncmlkLScraWQpO2lmKCFncmlkKXJldHVybjsKICBjb25zdCBwZng9aWQrJ19fJzsKICBpZihVU19TRUdbaWRdKXsKICAgIGNvbnN0IHRrcz1VU19TRUdbaWRdOwogICAgZ3JpZC5pbm5lckhUTUw9dGtzLm1hcCh0PT57Y29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTtyZXR1cm4gJzxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+VVM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPicrdCsnPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nO30pLmpvaW4oJycpOwogICAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL3VzL3F1b3Rlcz90aWNrZXJzPScrdGtzLmpvaW4oJywnKSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7T2JqZWN0LmVudHJpZXMoZCkuZm9yRWFjaCgoW3Qsdl0pPT57Y29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTtjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfcCcpO2NvbnN0IGVjPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19jJyk7aWYoZXAmJnYucHJpY2Upe2VwLnRleHRDb250ZW50PSckJytOdW1iZXIodi5wcmljZSkudG9GaXhlZCgyKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fWlmKGVjJiZ2LnByaWNlJiZ2LnByZXYpc2V0Q2hnKHBmeCt0aWQrJ19jJyx2LnByaWNlLHYucHJldiwndXNkJyk7fSk7fWNhdGNoKGUpe30KICAgIHJldHVybjsKICB9CiAgY29uc3QgdGtzPVNFR1tpZF07aWYoIXRrcylyZXR1cm47CiAgZ3JpZC5pbm5lckhUTUw9dGtzLm1hcCh0PT57Y29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTtyZXR1cm4gJzxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iJytwZngrdGlkKydfYyI+4oCUPC9kaXY+PC9kaXY+Jzt9KS5qb2luKCcnKTsKICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzLm1hcCh0PT4nQk1GQk9WRVNQQTonK3QpfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpOyhkLmRhdGF8fFtdKS5mb3JFYWNoKHg9Pntjb25zdCB0PXgucy5yZXBsYWNlKCdCTUZCT1ZFU1BBOicsJycpLnRvTG93ZXJDYXNlKCk7Y29uc3RbYyxjYV09eC5kfHxbXTtpZihjIT1udWxsKXtjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdCsnX3AnKTtpZihlcCl7ZXAudGV4dENvbnRlbnQ9ZkJSTChjKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fXNldENoZyhwZngrdCsnX2MnLGMsYy0oY2F8fDApLCdicmwnKTt9fSk7fWNhdGNoKGUpe30KfQoKYXN5bmMgZnVuY3Rpb24gZmV0Y2hITCgpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkLkJUQ3x8MCk7aWYoYnA+MCl7c2V0RWwoJ2J0Yy1wJyxmVVNEKGJwKSk7c2V0Q2hnKCdidGMtYycsYnAsYnAqMC45OSwndXNkJyk7fXRyeXtjb25zdCByMj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcycsZGV4Oid4eXonfSl9KTtpZihyMi5vayl7Y29uc3QgZDI9YXdhaXQgcjIuanNvbigpO2lmKGQyWyd4eXo6Q0wnXSlzZXRFbCgnY2wtcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDTCddKS50b0ZpeGVkKDIpKTtpZihkMlsneHl6OkdPTEQnXSlzZXRFbCgnZ29sZC1wJywnJCcrTnVtYmVyKGQyWyd4eXo6R09MRCddKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTtpZihkMlsneHl6OlNJTFZFUiddKXNldEVsKCdzaWx2ZXItcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpTSUxWRVInXSkudG9GaXhlZCgyKSk7aWYoZDJbJ3h5ejpDT1BQRVInXSlzZXRFbCgnY29wcGVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q09QUEVSJ10pLnRvRml4ZWQoMykpO319Y2F0Y2goZSl7fX1jYXRjaChlKXt9fQphc3luYyBmdW5jdGlvbiBmZXRjaFRWKCl7Y29uc3Qgb3V0PXt9O3RyeXtjb25zdCB0a3M9WydCTUZCT1ZFU1BBOlBFVFI0JywnQk1GQk9WRVNQQTpJVFVCNCcsJ0JNRkJPVkVTUEE6VkFMRTMnLCdCTUZCT1ZFU1BBOkJCREM0JywnQk1GQk9WRVNQQTpBQkVWMycsJ0JNRkJPVkVTUEE6QkJBUzMnLCdCTUZCT1ZFU1BBOldFR0UzJywnQk1GQk9WRVNQQTpJQk9WJ107Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pO2lmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7KGQuZGF0YXx8W10pLmZvckVhY2goeD0+e2NvbnN0W2MsY2FdPXguZHx8W107aWYoYyE9bnVsbClvdXRbeC5zXT17cDpjLHY6Yy0oY2F8fDApfTt9KTt9fWNhdGNoKGUpe310cnl7Y29uc3QgcnI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYocnIub2spe2NvbnN0IGRkPWF3YWl0IHJyLmpzb24oKTtpZihkZC5wcmVjb19hdHVhbCl7c2V0RWwoJ3JveG8zNHEtcCcsZkJSTChkZC5wcmVjb19hdHVhbCkpO3NldENoZygncm94bzM0cS1jJyxkZC5wcmVjb19hdHVhbCwoZGQucHJlY29fYW50ZXJpb3J8fGRkLnByZWNvX2F0dWFsKjAuOTkpLCdicmwnKTt9fX1jYXRjaChlKXt9cmV0dXJuIG91dDt9CmFzeW5jIGZ1bmN0aW9uIGZldGNoRnV0dXJlcygpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9mdXR1cmVzJyk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEZ1bmRpbmcoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9mYXBpLmJpbmFuY2UuY29tL2ZhcGkvdjEvcHJlbWl1bUluZGV4P3N5bWJvbD1CVENVU0RUJyk7aWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtzZXRFbCgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlfHwwKSoxMDApLnRvRml4ZWQoNCkrJyUnKTtyZXR1cm47fX1jYXRjaChlKXt9dHJ5e2NvbnN0IHIyPWF3YWl0IGZldGNoKEJBU0UrJy9iaW5hbmNlL2Z1bmRpbmcnKTtpZighcjIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgcjIuanNvbigpO2lmKGQubGFzdEZ1bmRpbmdSYXRlKXNldEVsKCdidGMtZnVuZCcsKHBhcnNlRmxvYXQoZC5sYXN0RnVuZGluZ1JhdGUpKjEwMCkudG9GaXhlZCg0KSsnJScpO31jYXRjaChlKXt9fQoKZnVuY3Rpb24gZG9NYWNybyh0dixmdXR1cmVzKXsKICBjb25zdCBpYkQ9dHZbJ0JNRkJPVkVTUEE6SUJPViddO2lmKGliRCl7c2V0RWwoJ2lib3YtcCcsZlBUUyhpYkQucCkpO3NldENoZygnaWJvdi1jJyxpYkQucCxpYkQudiwncHRzJyk7fQogIFtbJ1BFVFI0JywncGV0cjRxJ10sWydJVFVCNCcsJ2l0dWI0cSddLFsnVkFMRTMnLCd2YWxlM3EnXSxbJ0JCREM0JywnYmJkYzRxJ10sWydBQkVWMycsJ2FiZXYzcSddLFsnQkJBUzMnLCdiYmFzM3EnXSxbJ1dFR0UzJywnd2VnZTNxJ11dLmZvckVhY2goKFt0LGlkXSk9Pntjb25zdCBkPXR2WydCTUZCT1ZFU1BBOicrdF07aWYoZCl7c2V0RWwoaWQrJy1wJyxmQlJMKGQucCkpO3NldENoZyhpZCsnLWMnLGQucCxkLnYsJ2JybCcpO319KTsKICBpZihmdXR1cmVzKXtjb25zdCBmPWZ1dHVyZXM7CiAgICBjb25zdCBhZj0oaWQsdmFsKT0+e2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKGUpe2UudGV4dENvbnRlbnQ9dmFsO2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO319OwogICAgaWYoZi5kamk/LnByaWNlKXthZignZGppLXAnLGZQVFMoZi5kamkucHJpY2UpKTtzZXRDaGcoJ2RqaS1jJyxmLmRqaS5wcmljZSxmLmRqaS5wcmV2LCdwdHMnKTt9CiAgICBpZihmLmVzZj8ucHJpY2Upe2FmKCdlc2YtcCcsZlBUUyhmLmVzZi5wcmljZSkpO3NldENoZygnZXNmLWMnLGYuZXNmLnByaWNlLGYuZXNmLnByZXYsJ3B0cycpO30KICAgIGlmKGYubnFmPy5wcmljZSl7YWYoJ25xZi1wJyxmUFRTKGYubnFmLnByaWNlKSk7c2V0Q2hnKCducWYtYycsZi5ucWYucHJpY2UsZi5ucWYucHJldiwncHRzJyk7fQogICAgaWYoZi53aW4/LnByaWNlKXthZignd2luLXAnLGZQVFMoZi53aW4ucHJpY2UpKTtzZXRDaGcoJ3dpbi1jJyxmLndpbi5wcmljZSxmLndpbi5wcmV2LCdwdHMnKTt9CiAgICBpZihmLnZpeD8ucHJpY2Upe2FmKCd2aXgtcCcsTnVtYmVyKGYudml4LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ3ZpeC1jJyxmLnZpeC5wcmljZSxmLnZpeC5wcmV2LCd1c2QnKTt9CiAgICBpZihmLmR4eT8ucHJpY2Upe2FmKCdkeHktcCcsTnVtYmVyKGYuZHh5LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ2R4eS1jJyxmLmR4eS5wcmljZSxmLmR4eS5wcmV2LCd1c2QnKTt9CiAgICBpZihmLnVzZD8ucHJpY2Upe2FmKCd1c2QtcCcsZkJSTChmLnVzZC5wcmljZSkpO3NldENoZygndXNkLWMnLGYudXNkLnByaWNlLGYudXNkLnByZXZ8fGYudXNkLnByaWNlLCdicmwnKTt9CiAgfQp9CgpmdW5jdGlvbiBkb1Bvc2l0aW9ucyh0dil7CiAgY29uc3QgcHREPXR2WydCTUZCT1ZFU1BBOlBFVFI0J107Y29uc3QgcHRQPXB0RD8ucHx8NDAscHRWPXB0RD8udnx8NDA7CiAgc2V0RWwoJ3B0LXBvcy1wJyxmQlJMKHB0UCkpO3NldENoZygncHQtcG9zLWMnLHB0UCxwdFYsJ2JybCcpOwogIGNvbnN0IHB0RGlzdD1wdFAtMzAuODU7CiAgc2V0RWwoJ3B0LWl0bScsKHB0RGlzdD49MD8nKyc6JycpKycgUiQgJytwdERpc3QudG9GaXhlZCgyKSsnICcrKHB0RGlzdD49MD8nYWNpbWEnOidhYmFpeG8nKSsnIGRvIHN0cmlrZScpOwogIGNvbnN0IHZsRD10dlsnQk1GQk9WRVNQQTpWQUxFMyddO2NvbnN0IHZsUD12bEQ/LnB8fDc4LHZsVj12bEQ/LnZ8fDc4OwogIHNldEVsKCd2bC1wb3MtcCcsZkJSTCh2bFApKTtzZXRDaGcoJ3ZsLXBvcy1jJyx2bFAsdmxWLCdicmwnKTsKICBjb25zdCB2bERpc3Q9dmxQLTU3LjQwOwogIHNldEVsKCd2bC1pdG0nLCh2bERpc3Q+PTA/JysnOicnKSsnIFIkICcrdmxEaXN0LnRvRml4ZWQoMikrJyAnKyh2bERpc3Q+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCBjZD0oZHMsZWlkKT0+e2NvbnN0IHY9bmV3IERhdGUoZHMpO2NvbnN0IGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKTtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVpZCk7aWYoZSllLnRleHRDb250ZW50PWQ7fTsKICBjZCgnMjAyNi0xMi0xNycsJ3B0LWRpYXMnKTtjZCgnMjAyNy0wMi0xOCcsJ3ZsLWRpYXMnKTtjZCgnMjAyNi0wOS0xNCcsJ2F4aWEzZi1kaWFzJyk7Y2QoJzIwMjYtMTAtMDInLCdheGlhM2ItZGlhcycpO2NkKCcyMDI2LTA3LTE2Jywncm94bzM0LWRpYXMnKTsKICBzZXRUaW1lb3V0KGFzeW5jKCk9Pnt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy9BWElBMy5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjtjb25zdCBwPWQucHJlY29fYXR1YWw7c2V0RWwoJ2F4aWEzLXBvcy1wJyxmQlJMKHApKTtzZXRFbCgnYXhpYTNiLXBvcy1wJyxmQlJMKHApKTtjb25zdCBrZG9BPTQzLjUxLGt1b0E9NjguNzYsa2RvQj00MC41MixrdW9CPTYyLjgxO2NvbnN0IGRBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1rZG8tZGlzdCcpO2lmKGRBKWRBLnRleHRDb250ZW50PSgocC1rZG9BKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nO2NvbnN0IHVBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1rdW8tZGlzdCcpO2lmKHVBKXVBLnRleHRDb250ZW50PSgoa3VvQS1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJztjb25zdCBzQT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTMtc3RhdHVzJyk7aWYoc0Epe3NBLnRleHRDb250ZW50PXA8PWtkb0E/J/CflLQgS0RPIEFUSU5HSURPJzpwPj1rdW9BPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQS5jbGFzc05hbWU9J3NiLXZhbCAnKyhwPD1rZG9BfHxwPj1rdW9BPyd3YXJuJzonb2snKTt9Y29uc3QgZEI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1rZG8tZGlzdCcpO2lmKGRCKWRCLnRleHRDb250ZW50PSgocC1rZG9CKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nO2NvbnN0IHVCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhM2Ita3VvLWRpc3QnKTtpZih1Qil1Qi50ZXh0Q29udGVudD0oKGt1b0ItcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7Y29uc3Qgc0I9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1zdGF0dXMnKTtpZihzQil7c0IudGV4dENvbnRlbnQ9cDw9a2RvQj8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1b0I/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NCLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PWtkb0J8fHA+PWt1b0I/J3dhcm4nOidvaycpO319Y2F0Y2goZSl7fX0sMjAwMCk7CiAgc2V0VGltZW91dChhc3luYygpPT57dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJlY29fYXR1YWwpcmV0dXJuO2NvbnN0IHA9ZC5wcmVjb19hdHVhbDtzZXRFbCgncm94bzM0LXBvcy1wJyxmQlJMKHApKTtjb25zdCBkZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm94bzM0LWtkby1kaXN0Jyk7aWYoZGUpZGUudGV4dENvbnRlbnQ9KChwLTEwLjUwKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkYSBiYXJyZWlyYSc7Y29uc3Qgc2U9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JveG8zNC1zdGF0dXMnKTtpZihzZSl7c2UudGV4dENvbnRlbnQ9cDw9MTAuNTA/J/CflLQgQkFSUkVJUkEgQVRJTkdJREEnOifinIUgQWNpbWEgZGEgYmFycmVpcmEnO3NlLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PTEwLjUwPydpdG0nOidvaycpO319Y2F0Y2goZSl7fX0sMzAwMCk7Cn0KCi8vIOKUgOKUgCBNb250ZSBDYXJsbyDilIDilIAKYXN5bmMgZnVuY3Rpb24gcnVuTUNGb3JBdGl2byh0aWNrZXIsc3RyaWtlLGRpYXMsbG9hZElkLHJlc0lkLHN0cmlrZUlkLHZvbElkLGluZm9JZCxyZWFsdGltZUlkKXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeSh7dGlja2VyLGtfY2FsbDpzdHJpa2Usa19wdXQ6c3RyaWtlLHRfZGF5czpkaWFzLG46NTAwMH0pfSk7CiAgICBjbGVhclRpbWVvdXQodG8pO2lmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxvYWRJZCkuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocmVzSWQpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIC8vIHByb2JfY2FsbF9leGVyY2lkYSA9IHByb2IgZG8gcHJlw6dvIHN1YmlyIGFvIHN0cmlrZSAoY2FsbCB2ZW5kaWRhIElUTSA9IHJ1aW0pCiAgICBjb25zdCBwcm9iPU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYXx8MCk7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoc3RyaWtlSWQpOwogICAgc0VsLnRleHRDb250ZW50PXByb2IudG9GaXhlZCgyKSsnJSc7CiAgICBzRWwuY2xhc3NOYW1lPSdpbmQtdmFsICcrKHByb2I8MTA/J29rJzpwcm9iPDI1Pyd3YXJuJzonZG93bicpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodm9sSWQpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaW5mb0lkKS50ZXh0Q29udGVudD0nVm9sLmhpc3QuICcrZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSDCtyBCJlMgdXNhIHZvbC5pbXBsLiAobWFpb3IpIOKGkiBwcm9iLiBCJlMgc2VtcHJlID4gTUMgwrcgQW1iYXMgaW5kaWNhbSByaXNjbyBiYWl4byc7CiAgICBpZihyZWFsdGltZUlkKXNldEVsKHJlYWx0aW1lSWQscHJvYi50b0ZpeGVkKDEpKyclJyk7CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxvYWRJZCk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J2luZGlzcG9uw612ZWwnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gcnVuTUNCYXJyaWVyKHRpY2tlcixlbnRyeSxrZG8sa3VvLGRpYXMscHJpY2UscHJlZml4KXsKICBwcmVmaXg9cHJlZml4fHwnYXhpYTMnOwogIHRyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApO2NvbnN0IGJvZHk9e3RpY2tlcixlbnRyeSxrZG8sa3VvLHRfZGF5czpkaWFzLG46MzAwMH07aWYocHJpY2U+MClib2R5LnByaWNlPXByaWNlO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL21vbnRlY2FybG8vYmFycmllcicse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeShib2R5KX0pO2NsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1yZXN1bHQnKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kyctbm9icicpLnRleHRDb250ZW50PWQucHJvYl9zZW1fYmFycmVpcmEudG9GaXhlZCgyKSsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kycta3VvJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2FsdGEudG9GaXhlZCgyKSsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kycta2RvJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2JhaXhhLnRvRml4ZWQoMikrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLXZvbCcpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWluZm8nKS50ZXh0Q29udGVudD0nUHJlw6dvIFIkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua2RvKycgwrcgS1VPIFIkICcrZC5rdW8rJyDCtyAnK2QuY2VuYXJpb3MudG9Mb2NhbGVTdHJpbmcoKSsnIGNlbsOhcmlvcyc7fWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwnaW5kaXNwb27DrXZlbCcpO30KfQphc3luYyBmdW5jdGlvbiBydW5NQ1ByZWZpeGFkbyh0aWNrZXIsZW50cnksa2RvLGRpYXMscHJpY2UpewogIHRyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApO2NvbnN0IGJvZHk9e3RpY2tlcixrX2NhbGw6ZW50cnksa19wdXQ6ZW50cnksdF9kYXlzOmRpYXMsa25vY2tfZG93bjprZG8sbjo1MDAwfTtpZihwcmljZT4wKWJvZHkucHJpY2U9cHJpY2U7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeShib2R5KX0pO2NsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtbG9hZGluZycpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtcmVzdWx0Jykuc3R5bGUuZGlzcGxheT0nYmxvY2snO2NvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LXN1Y2Vzc28nKTtzRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9zdWNlc3NvKS50b0ZpeGVkKDIpKyclJztzRWwuY2xhc3NOYW1lPSdpbmQtdmFsICcrKGQucHJvYl9zdWNlc3NvPjcwPydvayc6ZC5wcm9iX3N1Y2Vzc28+NTA/J3dhcm4nOidkb3duJyk7Y29uc3QgY0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtY2FsbCcpO2lmKGNFbCljRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9jYWxsX2V4ZXJjaWRhKS50b0ZpeGVkKDIpKyclJztjb25zdCBrRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1rZG8nKTtpZihrRWwpa0VsLnRleHRDb250ZW50PWQucHJvYl9rZG9fYXRpbmdpZG8hPW51bGw/TnVtYmVyKGQucHJvYl9rZG9fYXRpbmdpZG8pLnRvRml4ZWQoMikrJyUnOifigJQnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtdm9sJykudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1pbmZvJykudGV4dENvbnRlbnQ9J1ByZcOnbyBSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtub2NrX2Rvd24rJyDCtyAnK2QuY2VuYXJpb3MudG9Mb2NhbGVTdHJpbmcoKSsnIGNlbsOhcmlvcyc7fWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtbG9hZGluZycpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCdpbmRpc3BvbsOtdmVsJyk7fQp9CgovLyDilIDilIAgSW5kaWNhZG9yZXMg4pSA4pSACmFzeW5jIGZ1bmN0aW9uIGZldGNoSW5kaWNhdG9ycyh0aWNrZXIpe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMzAwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvJyt0aWNrZXIse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hCVENJbmRpY2F0b3JzKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvYnRjL2luZGljYXRvcnMnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZldGNoQlRDQ3ljbGUoKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDE1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9idGMvY3ljbGUnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZldGNoRmVhckdyZWVkKCl7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2ZlYXJncmVlZCcpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2NvbnN0IHY9ZC52YWx1ZXx8NTA7Y29uc3QgY2xzPXY8PTI1Pyd2YXIoLS1yZWQpJzp2PD00NT8ndmFyKC0td2FybiknOnY8PTc1Pyd2YXIoLS1hY2NlbnQpJzondmFyKC0tZ3JlZW4pJztjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmVhci1ncmVlZC1hcmVhJyk7aWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTJweCI+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo2cHgiPvCfmLEgRkVBUiAmIEdSRUVEIElOREVYPC9kaXY+PGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweCI+PGRpdiBzdHlsZT0iZm9udC1zaXplOjEuOXJlbTtmb250LXdlaWdodDo4MDA7Y29sb3I6JytjbHMrJyI+Jyt2Kyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjhyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOicrY2xzKyciPicrKGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKSsnPC9kaXY+PC9kaXY+PC9kaXY+JztzZXRFbCgnZmctdmFsJyxTdHJpbmcodikpO3NldEVsKCdmZy1sYmwnLGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKTt0cnl7Y29uc3QgcmI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnfSl9KTtpZihyYi5vayl7Y29uc3QgZGI9YXdhaXQgcmIuanNvbigpO2NvbnN0IGJwPXBhcnNlRmxvYXQoZGIuQlRDfHwwKTtpZihicD4wKXtzZXRFbCgnYnRjLWluZC1wcmljZScsJyQnK051bWJlcihicCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7c2V0RWwoJ2J0Yy1wJyxmVVNEKGJwKSk7fX19Y2F0Y2goZTIpe319Y2F0Y2goZSl7fX0KCmZ1bmN0aW9uIHJlbmRlckluZGljYXRvcnMoYXJlYUlkLGRhdGEsc2hvd0FsbCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoYXJlYUlkKTtpZighZWwpcmV0dXJuOwogIGlmKCFkYXRhKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXdhcm4pO2ZvbnQtc2l6ZTouNjJyZW07cGFkZGluZzoxMHB4Ij7ij7MgU2VtIHJlc3Bvc3RhIOKAlCBjbGlxdWUg4oa7PC9kaXY+JztyZXR1cm47fQogIGlmKGRhdGEuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tZGFuZ2VyKTtmb250LXNpemU6LjYycmVtO3BhZGRpbmc6MTBweCI+4pqgICcrZGF0YS5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGNvbnN0IGluZHM9ZGF0YS5pbmRpY2Fkb3Jlc3x8W107CiAgY29uc3Qgc2NvcmU9ZGF0YS5zY29yZV90b3RhbDtjb25zdCBwcmVjbz1kYXRhLnByZWNvX2F0dWFsO2NvbnN0IGdyYWhhbT1kYXRhLmdyYWhhbV92YWx1ZTtjb25zdCB1cHNpZGU9ZGF0YS51cHNpZGVfZ3JhaGFtO2NvbnN0IHNldG9yPWRhdGEuc2V0b3J8fCcnOwogIGxldCBodG1sPScnOwogIGlmKHNjb3JlIT1udWxsKXsKICAgIGNvbnN0IHNjPU51bWJlcihzY29yZSk7CiAgICBjb25zdCBzYzI9c2M+PTY1Pyd2YXIoLS1ncmVlbiknOnNjPj00MD8ndmFyKC0td2FybiknOid2YXIoLS1yZWQpJzsKICAgIGNvbnN0IHNsPXNjPj02NT8nQ29tcHJhIOKWsic6c2M+PTQwPydOZXV0cm8g4oaSJzonVmVuZGEg4pa8JzsKICAgIGh0bWwrPSc8ZGl2IGNsYXNzPSJzY29yZS1ib3giPicrCiAgICAgICc8ZGl2IGNsYXNzPSJzY29yZS1jZWxsIj48ZGl2IGNsYXNzPSJzY29yZS1tZXRhIj5TY29yZTwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLW51bSIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2MrJzwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLWxibCIgc3R5bGU9ImNvbG9yOicrc2MyKyciPicrc2wrJzwvZGl2PjwvZGl2PicrCiAgICAgICc8ZGl2IGNsYXNzPSJzY29yZS1jZWxsIj48ZGl2IGNsYXNzPSJzY29yZS1tZXRhIj5Db3Rhw6fDo288L2Rpdj48ZGl2IGNsYXNzPSJzY29yZS12YWwiPicrKHByZWNvPydSJCAnK051bWJlcihwcmVjbykudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXN1YiI+JytzZXRvcisnPC9kaXY+PC9kaXY+JysKICAgICAgJzxkaXYgY2xhc3M9InNjb3JlLWNlbGwiPjxkaXYgY2xhc3M9InNjb3JlLW1ldGEiPkdyYWhhbSBWSjwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXZhbCIgc3R5bGU9ImNvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyhncmFoYW0/J1IkICcrTnVtYmVyKGdyYWhhbSkudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXN1YiIgc3R5bGU9ImNvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cHNpZGUhPW51bGw/KHVwc2lkZT4wPycrJzonJykrdXBzaWRlKyclIHVwc2lkZSc6J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgICAnPC9kaXY+JzsKICB9CiAgKHNob3dBbGw/aW5kczppbmRzLnNsaWNlKDAsMTIpKS5mb3JFYWNoKGk9PnsKICAgIGNvbnN0IHM9aS5zaW5hbHx8Jyc7CiAgICBjb25zdCBjbHM9cz09PSdBbHRhJ3x8cz09PSdTb2JyZXZlbmRhJz8nb2snOnM9PT0nQmFpeGEnfHxzPT09J1NvYnJlY29tcHJhJz8nZG93bic6J3dhcm4nOwogICAgY29uc3QgYXJyb3c9Y2xzPT09J29rJz8n4payJzpjbHM9PT0nZG93bic/J+KWvCc6J+KGkic7CiAgICBodG1sKz0nPGRpdiBjbGFzcz0iaW5kLXJvdyI+JysKICAgICAgJzxkaXYgY2xhc3M9ImluZC1yb3ctdG9wIj48c3BhbiBjbGFzcz0iaW5kLXJvdy1ub21lIj4nKyhpLm5vbWV8fCcnKSsnPC9zcGFuPjxzcGFuIGNsYXNzPSJpbmQtcm93LXZhbCAnK2NscysnIj4nKyhpLnZhbG9yIT1udWxsP2kudmFsb3I6J+KAlCcpKycgJythcnJvdysnPC9zcGFuPjwvZGl2PicrCiAgICAgIChpLmV4cGxpY2FjYW8/JzxkaXYgY2xhc3M9ImluZC1yb3ctZXhwIj4nK2kuZXhwbGljYWNhbysnPC9kaXY+JzonJykrCiAgICAgICc8L2Rpdj4nOwogIH0pOwogIGVsLmlubmVySFRNTD1odG1sfHwnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNnJlbTtwYWRkaW5nOjhweCI+U2VtIGluZGljYWRvcmVzIGRpc3BvbsOtdmVpczwvZGl2Pic7Cn0KCmZ1bmN0aW9uIHJlbmRlckJUQ0luZGljYXRvcnMoZGF0YSl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1pbmQtYXJlYScpO2lmKCFlbHx8IWRhdGEpcmV0dXJuOwogIGlmKGRhdGEuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7Zm9udC1zaXplOi42cmVtO3BhZGRpbmc6MTBweCI+4o+zICcrZGF0YS5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGxldCBodG1sPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjVweCI+JzsKICBpZihkYXRhLnJzaV9zZW1hbmFsIT1udWxsKXtjb25zdCByPWRhdGEucnNpX3NlbWFuYWw7Y29uc3QgY2xzPXI8MzA/J29rJzpyPjcwPydkb3duJzond2Fybic7aHRtbCs9JzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCAnK2NscysnIj4nK3IudG9GaXhlZCgxKSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40NHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDoycHgiPicrKHI8MzA/J1NvYnJldmVuZGEg4pqhJzpyPjcwPydTb2JyZWNvbXByYSDimqAnOidab25hIG5ldXRyYScpKyc8L2Rpdj48L2Rpdj4nO3NldEVsKCdidGMtcnNpJyxyLnRvRml4ZWQoMSkpO30KICBpZihkYXRhLm1tNTBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gNTAgc2VtLjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JCcrTnVtYmVyKGRhdGEubW01MF9zZW1hbmFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nOwogIGlmKGRhdGEubW0yMDBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gMjAwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPiQnK051bWJlcihkYXRhLm1tMjAwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZGF0YS5tYWNkX2hpc3RvZ3JhbSE9bnVsbCl7Y29uc3QgbWg9ZGF0YS5tYWNkX2hpc3RvZ3JhbTtodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TUFDRCBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysobWg+MD8nb2snOidkb3duJykrJyI+JytOdW1iZXIobWgpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDRyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4Ij4nKyhtaD4wPydNb21lbnR1bSDilrInOidNb21lbnR1bSDilrwnKSsnPC9kaXY+PC9kaXY+Jzt9CiAgaWYoZGF0YS5vYnZfdHJlbmQpaHRtbCs9JzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk9CViBUcmVuZDwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysoZGF0YS5vYnZfdHJlbmQ9PT0nc3ViaW5kbyc/J29rJzonZG93bicpKyciPicrZGF0YS5vYnZfdHJlbmQrJzwvZGl2PjwvZGl2Pic7CiAgaHRtbCs9JzwvZGl2Pic7ZWwuaW5uZXJIVE1MPWh0bWw7CiAgaWYoZGF0YS5wcmljZSlzZXRFbCgnYnRjLWluZC1wcmljZScsJyQnK051bWJlcihkYXRhLnByaWNlKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTsKfQoKZnVuY3Rpb24gcmVuZGVyQlRDQ3ljbGUoZCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1jeWNsZS1hcmVhJyk7aWYoIWVsfHwhZHx8ZC5lcnJvcilyZXR1cm47CiAgY29uc3QgZlU9dj0+dj8nJCcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CiAgZWwuaW5uZXJIVE1MPQogICAgJzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NXB4O21hcmdpbi1ib3R0b206OHB4Ij4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk1WUlYgWi1TY29yZTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysoZC5tdnJ2X3pzY29yZT8udmFsdWU8MT8nb2snOmQubXZydl96c2NvcmU/LnZhbHVlPDM/J3dhcm4nOidkb3duJykrJyI+JytkLm12cnZfenNjb3JlPy52YWx1ZSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40NHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDoycHgiPicrZC5tdnJ2X3pzY29yZT8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TlVQTDwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JysoKGQubnVwbD8udmFsdWV8fDApKjEwMCkudG9GaXhlZCgwKSsnJTwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDRyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4Ij4nK2QubnVwbD8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UHVlbGwgTXVsdGlwbGU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrZC5wdWVsbD8udmFsdWUrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDRyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4Ij4nK2QucHVlbGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPjIwMFcgTUE8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrZlUoZC5tYTIwMHcpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQ0cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JysoZC5tYTIwMHdfcGN0PycrJytkLm1hMjAwd19wY3QrJyUgYWNpbWEnOicnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5SYWluYm93IEJhbmQ8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrKGQucmFpbmJvdz8uYmFuZHx8J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlBpIEN5Y2xlIERpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayI+JytmVShkLnBpX2N5Y2xlPy5kaXN0YW5jZSkrJzwvZGl2PjwvZGl2PicrCiAgICAnPC9kaXY+JysKICAgICc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6OHB4O2ZvbnQtc2l6ZTouNThyZW07Y29sb3I6dmFyKC0tYWNjZW50KSI+JysoZC5waV9jeWNsZT8uc2lnbmFsfHwnJykrJzwvZGl2Pic7Cn0KCmFzeW5jIGZ1bmN0aW9uIGxvYWRJbmRpY2F0b3JzKCl7CiAgY29uc3Qgd2l0aFRpbWVvdXQ9KHAsbXMsZmIpPT5Qcm9taXNlLnJhY2UoW3AsbmV3IFByb21pc2Uocj0+c2V0VGltZW91dCgoKT0+cihmYiksbXMpKV0pOwogIGNvbnN0W2J0YyxjeWNsZV09YXdhaXQgUHJvbWlzZS5hbGwoW3dpdGhUaW1lb3V0KGZldGNoQlRDSW5kaWNhdG9ycygpLDE1MDAwLHtlcnJvcjonVGltZW91dCDigJQgY2xpcXVlIOKGuyBuYSBhYmEnfSksd2l0aFRpbWVvdXQoZmV0Y2hCVENDeWNsZSgpLDE1MDAwLG51bGwpXSk7CiAgcmVuZGVyQlRDSW5kaWNhdG9ycyhidGMpO3JlbmRlckJUQ0N5Y2xlKGN5Y2xlKTtmZXRjaEZlYXJHcmVlZCgpOwogIGNvbnN0IHN0b2Nrcz1bWydQRVRSNC5TQScsJ3BldHI0LWluZC1hcmVhJ10sWydWQUxFMy5TQScsJ3ZhbGUzLWluZC1hcmVhJ10sWydCQkFTMy5TQScsJ2JiYXMzLWluZC1hcmVhJ10sWydBWElBMy5TQScsJ2F4aWEzLWluZC1hcmVhJ10sWydST1hPMzQuU0EnLCdyb3hvMzQtaW5kLWFyZWEnXV07CiAgY29uc3QgcmVzdWx0cz1hd2FpdCBQcm9taXNlLmFsbChzdG9ja3MubWFwKChbdF0pPT53aXRoVGltZW91dChmZXRjaEluZGljYXRvcnModCksMzAwMDAse2Vycm9yOidUaW1lb3V0IDMwcyd9KSkpOwogIHN0b2Nrcy5mb3JFYWNoKChbLGFyZWFJZF0saSk9PnJlbmRlckluZGljYXRvcnMoYXJlYUlkLHJlc3VsdHNbaV0sdHJ1ZSkpOwp9CmFzeW5jIGZ1bmN0aW9uIHJlbG9hZEluZCh0aWNrZXIpewogIGNvbnN0IGFyZWFJZD10aWNrZXIrJy1pbmQtYXJlYSc7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoYXJlYUlkKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxcyBpbmZpbml0ZSI+Q2FycmVnYW5kbyAnK3RpY2tlci50b1VwcGVyQ2FzZSgpKycuLi48L2Rpdj4nOwogIGNvbnN0IHRpY2tlck1hcD17J3BldHI0JzonUEVUUjQuU0EnLCd2YWxlMyc6J1ZBTEUzLlNBJywnYmJhczMnOidCQkFTMy5TQScsJ2F4aWEzJzonQVhJQTMuU0EnLCdyb3hvMzQnOidST1hPMzQuU0EnfTsKICBjb25zdCBkPWF3YWl0IGZldGNoSW5kaWNhdG9ycyh0aWNrZXJNYXBbdGlja2VyXXx8dGlja2VyLnRvVXBwZXJDYXNlKCkrJy5TQScpOwogIHJlbmRlckluZGljYXRvcnMoYXJlYUlkLGQsdHJ1ZSk7Cn0KCi8vIOKUgOKUgCBDYWxlbmTDoXJpbyDilIDilIAKY29uc3QgQ0FMX0ZMQUdTPXsnVVNEJzon8J+HuvCfh7gnLCdCUkwnOifwn4en8J+HtycsJ0VVUic6J/Cfh6rwn4e6JywnR0JQJzon8J+HrPCfh6cnLCdDTlknOifwn4eo8J+HsycsJ0pQWSc6J/Cfh6/wn4e1JywnQ0FEJzon8J+HqPCfh6YnLCdBVUQnOifwn4em8J+HuicsJ0RFJzon8J+HqfCfh6onLCdFVVInOifwn4eq8J+Huid9Owphc3luYyBmdW5jdGlvbiBsb2FkQ2FsZW5kYXIoKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FsZW5kYXItYXJlYScpO2NvbnN0IHN0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYWxlbmRhci1zdGF0dXMnKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoyMHB4O3RleHQtYWxpZ246Y2VudGVyO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+JzsKICBpZihzdClzdC50ZXh0Q29udGVudD0nQnVzY2FuZG8gZXZlbnRvcy4uLic7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDIwMDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2NhbGVuZGFyJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7CiAgICBpZighci5vayl0aHJvdyBuZXcgRXJyb3IoJ0hUVFAgJytyLnN0YXR1cyk7CiAgICBjb25zdCBldmVudHM9YXdhaXQgci5qc29uKCk7CiAgICBpZihzdClzdC50ZXh0Q29udGVudD1ldmVudHMubGVuZ3RoPjA/ZXZlbnRzLmxlbmd0aCsnIGV2ZW50b3MgwrcgZXN0YSBlIHByw7N4aW1hIHNlbWFuYSc6J1NlbSBldmVudG9zJzsKICAgIGlmKCFldmVudHN8fCFldmVudHMubGVuZ3RoKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9InBhZGRpbmc6MjBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOi42MnJlbSI+U2VtIGV2ZW50b3MgZGlzcG9uw612ZWlzPC9kaXY+JztyZXR1cm47fQogICAgY29uc3QgYnlEYXRlPXt9O2V2ZW50cy5mb3JFYWNoKGU9Pntjb25zdCBkdD0oZS5kYXRlfHwnJykuc2xpY2UoMCwxMCk7aWYoIWJ5RGF0ZVtkdF0pYnlEYXRlW2R0XT1bXTtieURhdGVbZHRdLnB1c2goZSk7fSk7CiAgICBsZXQgaHRtbD0nJzsKICAgIE9iamVjdC5rZXlzKGJ5RGF0ZSkuc29ydCgpLmZvckVhY2goZHQ9PnsKICAgICAgY29uc3QgZD1uZXcgRGF0ZShkdCsnVDEyOjAwOjAwJyk7CiAgICAgIGNvbnN0IGxhYmVsPWQudG9Mb2NhbGVEYXRlU3RyaW5nKCdwdC1CUicse3dlZWtkYXk6J2xvbmcnLGRheTonMi1kaWdpdCcsbW9udGg6J3Nob3J0J30pOwogICAgICBodG1sKz0nPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj7wn5OFPC9zcGFuPiAnK2xhYmVsKyc8L2Rpdj4nKwogICAgICAgICc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO21hcmdpbi1ib3R0b206MTBweCI+JysKICAgICAgICAnPGRpdiBjbGFzcz0iY2FsLWhlYWRlciI+PHNwYW4+UGHDrXM8L3NwYW4+PHNwYW4+SG9yYTwvc3Bhbj48c3Bhbj5FdmVudG88L3NwYW4+PHNwYW4+SW1wPC9zcGFuPjxzcGFuPlJlYWxpemFkbzwvc3Bhbj48c3Bhbj5QcmV2aXN0bzwvc3Bhbj48L2Rpdj4nOwogICAgICBieURhdGVbZHRdLmZvckVhY2goZT0+ewogICAgICAgIGNvbnN0IGZsYWc9ZS5mbGFnfHxDQUxfRkxBR1NbZS5jb3VudHJ5XXx8J/CfjJAnOwogICAgICAgIGNvbnN0IGltcD1lLmltcG9ydGFuY2V8fDE7CiAgICAgICAgY29uc3QgaW1wQ29sb3I9aW1wPj0zPyd2YXIoLS1yZWQpJzppbXA+PTI/J3ZhcigtLXdhcm4pJzondmFyKC0tbXV0ZWQpJzsKICAgICAgICBjb25zdCBhY3RDb2xvcj1lLnNpZ25hbD09PSdiZWF0Jz8ndmFyKC0tZ3JlZW4pJzplLnNpZ25hbD09PSdtaXNzJz8ndmFyKC0tcmVkKSc6J3ZhcigtLXRleHQpJzsKICAgICAgICBodG1sKz0nPGRpdiBjbGFzcz0iY2FsLWV2ZW50Ij4nKwogICAgICAgICAgJzxzcGFuPicrZmxhZysnPC9zcGFuPicrCiAgICAgICAgICAnPHNwYW4gY2xhc3M9ImNhbC10aW1lIj4nKyhlLnRpbWV8fCfigJQnKSsnPC9zcGFuPicrCiAgICAgICAgICAnPHNwYW4gY2xhc3M9ImNhbC1ldmVudC1uYW1lIiB0aXRsZT0iJysoZS5ldmVudHx8JycpKyciPicrKGUuZXZlbnR8fCcnKSsnPC9zcGFuPicrCiAgICAgICAgICAnPHNwYW4gY2xhc3M9ImNhbC1pbXAiIHN0eWxlPSJjb2xvcjonK2ltcENvbG9yKyciPicrJ+KXjycucmVwZWF0KE1hdGgubWluKGltcCwzKSkrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIGNsYXNzPSJjYWwtYWN0dWFsIiBzdHlsZT0iY29sb3I6JythY3RDb2xvcisnIj4nKyhlLmFjdHVhbHx8J+KAlCcpKyc8L3NwYW4+JysKICAgICAgICAgICc8c3BhbiBjbGFzcz0iY2FsLWZvcmVjYXN0Ij4nKyhlLmZvcmVjYXN0fHwn4oCUJykrJzwvc3Bhbj4nKwogICAgICAgICAgJzwvZGl2Pic7CiAgICAgIH0pOwogICAgICBodG1sKz0nPC9kaXY+JzsKICAgIH0pOwogICAgZWwuaW5uZXJIVE1MPWh0bWw7CiAgfWNhdGNoKGUpewogICAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9J0Vycm8nOwogICAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1kYW5nZXIpO3BhZGRpbmc6MjBweDtmb250LXNpemU6LjYycmVtO3RleHQtYWxpZ246Y2VudGVyIj4nKygoZS5uYW1lPT09J0Fib3J0RXJyb3InKT8nVGltZW91dCDigJQgdGVudGUgbm92YW1lbnRlJzonRXJybyBhbyBjYXJyZWdhcicpKyc8L2Rpdj4nOwogIH0KfQoKLy8g4pSA4pSAIE1haW4g4pSA4pSACmFzeW5jIGZ1bmN0aW9uIGZldGNoQWxsKCl7CiAgdHJ5ewogICAgY29uc3RbLHR2LGZ1dHVyZXNdPWF3YWl0IFByb21pc2UuYWxsKFtmZXRjaEhMKCksZmV0Y2hUVigpLGZldGNoRnV0dXJlcygpXSk7CiAgICBjb25zdCBub3c9bmV3IERhdGUoKS50b0xvY2FsZVRpbWVTdHJpbmcoJ3B0LUJSJyk7CiAgICBzZXRFbCgnbGFzdC11cGRhdGUnLCfihrsgJytub3cpO3NldEVsKCdmb290ZXItdGltZScsbm93KTsKICAgIGRvTWFjcm8odHYsZnV0dXJlcyk7ZG9Qb3NpdGlvbnModHYpOwogICAgc2V0VGltZW91dChmZXRjaEZ1bmRpbmcsMzAwMCk7CiAgICBzZXRUaW1lb3V0KGFzeW5jKCk9Pnt0cnl7Y29uc3RbYixjeWNdPWF3YWl0IFByb21pc2UuYWxsKFtmZXRjaEJUQ0luZGljYXRvcnMoKSxmZXRjaEJUQ0N5Y2xlKCldKTtpZihiKXJlbmRlckJUQ0luZGljYXRvcnMoYik7aWYoY3ljKXJlbmRlckJUQ0N5Y2xlKGN5Yyk7ZmV0Y2hGZWFyR3JlZWQoKTt9Y2F0Y2goZSl7fX0sNTAwMCk7CiAgICAvLyBNQyBjb20gNMK6IGFyZ3VtZW50byBwYXJhIGF0dWFsaXphciByZWFsdGltZSBubyBzYi1yb3cKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0ZvckF0aXZvKCdQRVRSNC5TQScsMzAuODUsMTg3LCdtYy1wdC1sb2FkaW5nJywnbWMtcHQtcmVzdWx0JywnbWMtcHQtc3RyaWtlJywnbWMtcHQtdm9sJywnbWMtcHQtaW5mbycsJ21jLXB0LXJlYWx0aW1lJyk7fSw2MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0ZvckF0aXZvKCdWQUxFMy5TQScsNTcuNDAsMjUwLCdtYy12bC1sb2FkaW5nJywnbWMtdmwtcmVzdWx0JywnbWMtdmwtc3RyaWtlJywnbWMtdmwtdm9sJywnbWMtdmwtaW5mbycsJ21jLXZsLXJlYWx0aW1lJyk7fSwxMjAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT57cnVuTUNCYXJyaWVyKCdBWElBMy5TQScsNTQuMzEsNDMuNTEsNjguNzYsOTMsNTQuMzEsJ2F4aWEzJyk7fSwxODAwMCk7CiAgICBzZXRUaW1lb3V0KCgpPT57cnVuTUNCYXJyaWVyKCdBWElBMy5TQScsNTAuNjUsNDAuNTIsNjIuODEsMTExLDUwLjY1LCdheGlhM2InKTt9LDI0MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ1ByZWZpeGFkbygnUk9YTzM0LlNBJywxMi44OCwxMC41MCwzMywxMi44OCk7fSwzMDAwMCk7CiAgICB3aW5kb3cuX2luZExvYWRlZD1mYWxzZTsKICB9Y2F0Y2goZSl7Y29uc29sZS5lcnJvcignZmV0Y2hBbGw6JyxlKTt9Cn0KZmV0Y2hBbGwoKTsKc2V0SW50ZXJ2YWwoZmV0Y2hBbGwsMTIwMDAwKTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPgo=").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
