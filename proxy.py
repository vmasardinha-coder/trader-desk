"""  # v8.6
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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjMgLSAyMDI2LTA2LTE0IC0tPgo8aHRtbCBsYW5nPSJwdC1CUiI+CjxoZWFkPgo8bWV0YSBjaGFyc2V0PSJVVEYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5UcmFkZXIgRGVzazwvdGl0bGU+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDMwMDs0MDA7NjAwOzcwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQo6cm9vdHsKICAtLWJnOiMwODA4MDg7LS1iZzI6IzEwMTAxMDstLWJnMzojMTYxNjE2OwogIC0tdGV4dDojZGRkOy0tbXV0ZWQ6IzQ4NDg0ODstLWJvcmRlcjojMWMxYzFjOwogIC0tYWNjZW50OiNmMGE1MDA7LS1ncmVlbjojMDBjODUzOy0tcmVkOiNmNTE3NWY7CiAgLS13YXJuOiNmZjhjMDA7LS1ibHVlOiMyMTk2ZjM7LS1pdG06I2ZmNDQ0NDstLXB1cnBsZTojOWMyN2IwCn0KYm9keXtiYWNrZ3JvdW5kOnZhcigtLWJnKTtjb2xvcjp2YXIoLS10ZXh0KTtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZTouNzRyZW07cGFkZGluZzoxMnB4IDE0cHg7bWF4LXdpZHRoOjY0MHB4O21hcmdpbjowIGF1dG87bWluLWhlaWdodDoxMDB2aH0KCi8qIEhlYWRlciAqLwouaGRye2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxMnB4O3BhZGRpbmctYm90dG9tOjEwcHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKX0KLmhkci10aXRsZXtmb250LXNpemU6Ljg4cmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO2xldHRlci1zcGFjaW5nOi4wNmVtfQouaGRyLXRpbWV7Zm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1hbGlnbjpyaWdodH0KCi8qIFRhYnMgKi8KLnRhYnN7ZGlzcGxheTpmbGV4O2dhcDozcHg7bWFyZ2luLWJvdHRvbToxMnB4O292ZXJmbG93LXg6YXV0bztwYWRkaW5nLWJvdHRvbToxcHh9Ci50YWJ7cGFkZGluZzo1cHggMTJweDtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2N1cnNvcjpwb2ludGVyO2ZvbnQtc2l6ZTouNTZyZW07bGV0dGVyLXNwYWNpbmc6LjA3ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTt3aGl0ZS1zcGFjZTpub3dyYXA7dHJhbnNpdGlvbjphbGwgLjEyc30KLnRhYjpob3Zlcntjb2xvcjp2YXIoLS10ZXh0KTtib3JkZXItY29sb3I6IzJhMmEyYX0KLnRhYi5hY3RpdmV7YmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2NvbG9yOiMwMDA7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Zm9udC13ZWlnaHQ6NzAwfQoudGFiLWNvbnRlbnR7ZGlzcGxheTpub25lfS50YWItY29udGVudC5hY3RpdmV7ZGlzcGxheTpibG9ja30KCi8qIFNlY3Rpb24gKi8KLnNlY3tmb250LXNpemU6LjQ4cmVtO2xldHRlci1zcGFjaW5nOi4xNGVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7cGFkZGluZzo5cHggMCA0cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjdweDtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo1cHh9Ci5zZWMgLmFjY3tjb2xvcjp2YXIoLS1hY2NlbnQpfS5zcmN7Y29sb3I6IzI4MjgyODtmb250LXNpemU6LjQ1cmVtfQoKLyogR3JpZCBjYXJkcyAqLwouZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjRweDttYXJnaW4tYm90dG9tOjEwcHh9Ci5jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo4cHggN3B4fQouY2FyZC5ne2JvcmRlci10b3A6MnB4IHNvbGlkIHZhcigtLWdyZWVuKX0uY2FyZC5ie2JvcmRlci10b3A6MnB4IHNvbGlkIHZhcigtLWJsdWUpfQouY2FyZC53e2JvcmRlci10b3A6MnB4IHNvbGlkIHZhcigtLXdhcm4pfS5jYXJkLnJ7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tcmVkKX0KLmMtbGJse2ZvbnQtc2l6ZTouNDJyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouMDdlbTttYXJnaW4tYm90dG9tOjFweH0KLmMtbm17Zm9udC1zaXplOi41N3JlbTtmb250LXdlaWdodDo3MDA7bWFyZ2luLWJvdHRvbTozcHh9Ci5jLXBye2ZvbnQtc2l6ZTouODJyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLWFjY2VudCl9Ci5jLXByLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjRzIGluZmluaXRlO2ZvbnQtc2l6ZTouNjJyZW19Ci5jLWNoe2ZvbnQtc2l6ZTouNDhyZW07bWFyZ2luLXRvcDoxcHh9Ci5jaGctdXB7Y29sb3I6dmFyKC0tZ3JlZW4pfS5jaGctZG57Y29sb3I6dmFyKC0tcmVkKX0uY2hnLWZse2NvbG9yOnZhcigtLW11dGVkKX0KQGtleWZyYW1lcyBwdWxzZXswJSwxMDAle29wYWNpdHk6MX01MCV7b3BhY2l0eTouM319CgovKiBTZWN0b3JzICovCi5zLWhkcntiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6N3B4IDExcHg7Y3Vyc29yOnBvaW50ZXI7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtmb250LXNpemU6LjU2cmVtO2xldHRlci1zcGFjaW5nOi4wN2VtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo0cHg7dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjEyc30KLnMtaGRyOmhvdmVye2JvcmRlci1jb2xvcjojMmEyYTJhO2NvbG9yOnZhcigtLXRleHQpfQoucy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nLXRvcDozcHh9CgovKiBQb3NpdGlvbiBjYXJkcyAqLwoucG9zLWNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjExcHg7bWFyZ2luLWJvdHRvbTo3cHh9Ci5wb3MtbGJse2ZvbnQtc2l6ZTouNDZyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi4wNmVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjNweH0KLnBvcy10a3tmb250LXNpemU6MXJlbTtmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0tYWNjZW50KTttYXJnaW4tYm90dG9tOjJweH0KLnBvcy1wcntmb250LXNpemU6MS4ycmVtO2ZvbnQtd2VpZ2h0OjcwMH0ucG9zLXByLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjRzIGluZmluaXRlO2ZvbnQtc2l6ZTouODVyZW19Ci5wb3MtY2hne2ZvbnQtc2l6ZTouNThyZW07bWFyZ2luLWJvdHRvbTo3cHh9Ci5zYntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmctdG9wOjdweDttYXJnaW4tdG9wOjdweH0KLnNiLXJvd3tkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6MnB4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtmb250LXNpemU6LjU2cmVtfQouc2ItbGJse2NvbG9yOnZhcigtLW11dGVkKX0uc2ItdmFse3RleHQtYWxpZ246cmlnaHQ7bWF4LXdpZHRoOjYyJX0KLnNiLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LnNiLXZhbC53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zYi12YWwuaXRte2NvbG9yOnZhcigtLWl0bSl9Ci5zaWduYWx7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6OXB4O21hcmdpbi10b3A6N3B4O2JhY2tncm91bmQ6dmFyKC0tYmcpfQouc2lnLXR0bHtmb250LXNpemU6LjQ3cmVtO2xldHRlci1zcGFjaW5nOi4wOGVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjVweDtjb2xvcjp2YXIoLS1tdXRlZCl9Ci5pbmQtYm94e2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo3cHg7dGV4dC1hbGlnbjpjZW50ZXJ9Ci5pbmQtbGJse2ZvbnQtc2l6ZTouNDZyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206M3B4fQouaW5kLXZhbHtmb250LXNpemU6LjlyZW07Zm9udC13ZWlnaHQ6ODAwfQouaW5kLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LmluZC12YWwud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaW5kLXZhbC5kb3due2NvbG9yOnZhcigtLXJlZCl9CgovKiBTY29yZSBib3ggKi8KLnNjb3JlLWJveHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnIgMWZyO2dhcDo1cHg7bWFyZ2luLWJvdHRvbTo4cHh9Ci5zY29yZS1jZWxse2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo5cHggN3B4O3RleHQtYWxpZ246Y2VudGVyfQouc2NvcmUtbWV0YXtmb250LXNpemU6LjQ0cmVtO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjA3ZW07bWFyZ2luLWJvdHRvbTozcHh9Ci5zY29yZS1udW17Zm9udC1zaXplOjEuNnJlbTtmb250LXdlaWdodDo4MDA7bGluZS1oZWlnaHQ6MX0KLnNjb3JlLWxibHtmb250LXNpemU6LjQ4cmVtO21hcmdpbi10b3A6MnB4fQouc2NvcmUtdmFse2ZvbnQtc2l6ZTouODhyZW07Zm9udC13ZWlnaHQ6NzAwO21hcmdpbi10b3A6MnB4fQouc2NvcmUtc3Vie2ZvbnQtc2l6ZTouNDZyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MXB4fQoKLyogSW5kaWNhZG9yIHJvdyBjb20gZXhwbGljYcOnw6NvICovCi5pbmQtcm93e2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQ6MnB4IHNvbGlkICMxYzFjMWM7cGFkZGluZzo2cHggOXB4O21hcmdpbi1ib3R0b206MnB4O3RyYW5zaXRpb246Ym9yZGVyLWxlZnQtY29sb3IgLjFzfQouaW5kLXJvdzpob3Zlcntib3JkZXItbGVmdC1jb2xvcjp2YXIoLS1hY2NlbnQpfQouaW5kLXJvdy10b3B7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmJhc2VsaW5lO21hcmdpbi1ib3R0b206MXB4fQouaW5kLXJvdy1ub21le2ZvbnQtc2l6ZTouNDZyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouMDZlbX0KLmluZC1yb3ctdmFse2ZvbnQtc2l6ZTouNzZyZW07Zm9udC13ZWlnaHQ6NzAwfQouaW5kLXJvdy12YWwub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5pbmQtcm93LXZhbC5kb3due2NvbG9yOnZhcigtLXJlZCl9LmluZC1yb3ctdmFsLndhcm57Y29sb3I6dmFyKC0td2Fybil9Ci5pbmQtcm93LWV4cHtmb250LXNpemU6LjVyZW07Y29sb3I6IzNhM2EzYTtsaW5lLWhlaWdodDoxLjR9CgovKiBDYWxlbmTDoXJpbyAqLwouY2FsLWRheS1oZHJ7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyMnB4IDQ0cHggMWZyIDI0cHggNThweCA1MnB4O2dhcDozcHg7cGFkZGluZzozcHggOXB4O2ZvbnQtc2l6ZTouNDJyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouMDZlbTtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JhY2tncm91bmQ6dmFyKC0tYmcpfQouY2FsLXJvd3tkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjIycHggNDRweCAxZnIgMjRweCA1OHB4IDUycHg7Z2FwOjNweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo1cHggOXB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOi41NnJlbX0KLmNhbC1yb3c6bGFzdC1jaGlsZHtib3JkZXItYm90dG9tOm5vbmV9Ci5jYWwtdGltZXtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi41cmVtfQouY2FsLW5hbWV7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXM7d2hpdGUtc3BhY2U6bm93cmFwfQouY2FsLWFjdHVhbHt0ZXh0LWFsaWduOnJpZ2h0O2ZvbnQtd2VpZ2h0OjcwMH0KLmNhbC1mY3t0ZXh0LWFsaWduOnJpZ2h0O2NvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjVyZW19Cgpmb290ZXJ7bWFyZ2luLXRvcDoxNnB4O3BhZGRpbmctdG9wOjlweDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2Vlbjtmb250LXNpemU6LjQ4cmVtO2NvbG9yOnZhcigtLW11dGVkKX0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KPGRpdiBjbGFzcz0iaGRyIj4KICA8ZGl2IGNsYXNzPSJoZHItdGl0bGUiPuKWuCBUUkFERVIgREVTSzwvZGl2PgogIDxkaXYgY2xhc3M9Imhkci10aW1lIiBpZD0ibGFzdC11cGRhdGUiPuKAlDwvZGl2Pgo8L2Rpdj4KPGRpdiBjbGFzcz0idGFicyI+CiAgPGRpdiBjbGFzcz0idGFiIGFjdGl2ZSIgb25jbGljaz0ic3dpdGNoVGFiKCdjb3RhY29lcycsdGhpcykiPvCfk4ogQ290YcOnw7VlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3dpdGNoVGFiKCdpbmRpY2Fkb3JlcycsdGhpcykiPvCfk4ggSW5kaWNhZG9yZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3aXRjaFRhYigncG9zaWNvZXMnLHRoaXMpIj7wn5K8IFBvc2nDp8O1ZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3aXRjaFRhYignY2FsZW5kYXJpbycsdGhpcykiPvCfk4UgQ2FsZW5kw6FyaW88L2Rpdj4KPC9kaXY+Cgo8IS0tIENPVEHDh8OVRVMgLS0+CjxkaXYgaWQ9InRhYi1jb3RhY29lcyIgY2xhc3M9InRhYi1jb250ZW50IGFjdGl2ZSI+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYWNjIj4wMTwvc3Bhbj4gRVVBIDxzcGFuIGNsYXNzPSJzcmMiPsK3IHByb3h5PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjLWxibCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+UyZQIEVTMSo8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJlc2YtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImVzZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iYy1sYmwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPk5hc2RhcSBOUTwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoIiBpZD0ibnFmLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjLWxibCI+w41uZGljZTwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkRvdyBKb25lczwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImRqaS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoIiBpZD0iZGppLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCByIj48ZGl2IGNsYXNzPSJjLWxibCI+Vm9sYXRpbGlkYWRlPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+VklYPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJ2aXgtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImMtbGJsIj5Ew7NsYXIgSW5kZXg8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5EWFk8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJkeHktcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImR4eS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkPDom1iaW88L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5VU0QvQlJMPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0idXNkLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJ1c2QtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYWNjIj4wMjwvc3Bhbj4gQjMgVG9wIDEwIDxzcGFuIGNsYXNzPSJzcmMiPsK3IFRyYWRpbmdWaWV3PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCBnIj48ZGl2IGNsYXNzPSJjLWxibCI+w41uZGljZTwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPklCT1Y8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJpYm92LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJpYm92LWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBnIj48ZGl2IGNsYXNzPSJjLWxibCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+V0lOMSE8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJ3aW4tcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9Indpbi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+UEVUUjQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJwZXRyNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9InBldHI0cS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+SVRVQjQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJpdHViNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9Iml0dWI0cS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+VkFMRTM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJ2YWxlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9InZhbGUzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+QkJEQzQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJiYmRjNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImJiZGM0cS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+QUJFVjM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJhYmV2M3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImFiZXYzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+QkJBUzM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJiYmFzM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImJiYXMzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+V0VHRTM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJ3ZWdlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9IndlZ2UzcS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgdyI+PGRpdiBjbGFzcz0iYy1sYmwiPkJEUjwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPlJPWE8zNDwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9InJveG8zNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9InJveG8zNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYWNjIj7wn5OCPC9zcGFuPiBCMyBwb3IgU2VnbWVudG8gPHNwYW4gY2xhc3M9InNyYyI+wrcgY2xpcXVlIHBhcmEgZXhwYW5kaXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygnZmluYW5jZWlybycpIj48c3Bhbj7wn4+mIEZpbmFuY2Vpcm88L3NwYW4+PHNwYW4gaWQ9InNhcnItZmluYW5jZWlybyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LWZpbmFuY2Vpcm8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1maW5hbmNlaXJvIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdwZXRyb2xlbycpIj48c3Bhbj7wn5uiIFBldHLDs2xlbyAmYW1wOyBHw6FzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXBldHJvbGVvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktcGV0cm9sZW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1wZXRyb2xlbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWluZXJhY2FvJykiPjxzcGFuPuKbjyBNaW5lcmHDp8Ojbzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1taW5lcmFjYW8iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWJvZHkiIGlkPSJzYm9keS1taW5lcmFjYW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1taW5lcmFjYW8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ21hdGVyaWFpcycpIj48c3Bhbj7wn4yyIFBhcGVsICZhbXA7IENlbHVsb3NlPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1hdGVyaWFpcyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LW1hdGVyaWFpcyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLW1hdGVyaWFpcyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygndXRpbGlkYWRlJykiPjxzcGFuPuKaoSBVdGlsaWRhZGUgUMO6YmxpY2E8L3NwYW4+PHNwYW4gaWQ9InNhcnItdXRpbGlkYWRlIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktdXRpbGlkYWRlIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtdXRpbGlkYWRlIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdjb25zdW1vX2MnKSI+PHNwYW4+8J+bjSBDb25zdW1vIEPDrWNsaWNvPC9zcGFuPjxzcGFuIGlkPSJzYXJyLWNvbnN1bW9fYyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LWNvbnN1bW9fYyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWNvbnN1bW9fYyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygnY29uc3Vtb19uJykiPjxzcGFuPvCfm5IgQ29uc3VtbyBOw6NvIEPDrWNsaWNvPC9zcGFuPjxzcGFuIGlkPSJzYXJyLWNvbnN1bW9fbiI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LWNvbnN1bW9fbiI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWNvbnN1bW9fbiI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygnc2F1ZGUnKSI+PHNwYW4+8J+PpSBTYcO6ZGU8L3NwYW4+PHNwYW4gaWQ9InNhcnItc2F1ZGUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWJvZHkiIGlkPSJzYm9keS1zYXVkZSI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLXNhdWRlIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdpbmR1c3RyaWFpcycpIj48c3Bhbj7wn4+XIEJlbnMgSW5kdXN0cmlhaXM8L3NwYW4+PHNwYW4gaWQ9InNhcnItaW5kdXN0cmlhaXMiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWJvZHkiIGlkPSJzYm9keS1pbmR1c3RyaWFpcyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWluZHVzdHJpYWlzIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCd0aV90ZWxlY29tJykiPjxzcGFuPvCfkrsgVEkgJmFtcDsgQ29tdW5pY2HDp8O1ZXM8L3NwYW4+PHNwYW4gaWQ9InNhcnItdGlfdGVsZWNvbSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LXRpX3RlbGVjb20iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC10aV90ZWxlY29tIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPjxzcGFuIGNsYXNzPSJhY2MiPvCfh7rwn4e4PC9zcGFuPiBFVUEgcG9yIFNlZ21lbnRvPC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWFnNycpIj48c3Bhbj7irZAgNyBNYWduw61maWNhczwvc3Bhbj48c3BhbiBpZD0ic2Fyci1tYWc3Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktbWFnNyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLW1hZzciPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ25hc2RhcTE1JykiPjxzcGFuPvCfkrsgTmFzZGFxIFRvcCAxNTwvc3Bhbj48c3BhbiBpZD0ic2Fyci1uYXNkYXExNSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LW5hc2RhcTE1Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbmFzZGFxMTUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3NwMjAnKSI+PHNwYW4+8J+TiiBTJmFtcDtQIDUwMCBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9InNhcnItc3AyMCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LXNwMjAiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1zcDIwIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdkamkyMCcpIj48c3Bhbj7wn4+bIERvdyBKb25lcyBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9InNhcnItZGppMjAiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWJvZHkiIGlkPSJzYm9keS1kamkyMCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWRqaTIwIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPjxzcGFuIGNsYXNzPSJhY2MiPjAzPC9zcGFuPiBDb21tb2RpdGllczwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCB3Ij48ZGl2IGNsYXNzPSJjLWxibCI+UGV0csOzbGVvPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+V1RJL0NMPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iY2wtcCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHciPjxkaXYgY2xhc3M9ImMtbGJsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkdPTEQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJnb2xkLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3Ij48ZGl2IGNsYXNzPSJjLWxibCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5TSUxWRVI8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJzaWx2ZXItcCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHciPjxkaXYgY2xhc3M9ImMtbGJsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkNPUFBFUjwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImNvcHBlci1wIj7igJQ8L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJhY2MiPjA0PC9zcGFuPiBCaXRjb2luPC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImMtbGJsIj5TcG90PC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+QlRDL1VTRDwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImJ0Yy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoIiBpZD0iYnRjLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjLWxibCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5CVEMgUlNJPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iYnRjLXJzaSI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImMtbGJsIj5GdW5kaW5nIDhoPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+QlRDIFJhdGU8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJidGMtZnVuZCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImMtbGJsIj5GZWFyICZhbXA7IEdyZWVkPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+SW5kZXg8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJmZy12YWwiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJmZy1sYmwiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxmb290ZXI+PHNwYW4gaWQ9ImZvb3Rlci10aW1lIj7igJQ8L3NwYW4+PHNwYW4+VHJhZGVyIERlc2sgdjEwLjM8L3NwYW4+PC9mb290ZXI+CjwvZGl2PgoKPCEtLSBJTkRJQ0FET1JFUyAtLT4KPGRpdiBpZD0idGFiLWluZGljYWRvcmVzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImFjYyI+8J+Tijwvc3Bhbj4gQ2ljbG8gQml0Y29pbjwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1jeWNsZS1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi41OHJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxMjBweDtnYXA6N3B4O21hcmdpbjo5cHggMCI+CiAgICA8ZGl2IGlkPSJmZWFyLWdyZWVkLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjU4cmVtO3BhZGRpbmc6MTBweCI+Q2FycmVnYW5kbyBGZWFyICZhbXA7IEdyZWVkLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTFweDt0ZXh0LWFsaWduOmNlbnRlciI+CiAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDRyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206NHB4Ij5CVEMvVVNEPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImJ0Yy1pbmQtcHJpY2UiPuKAlDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBJbmRpY2Fkb3JlcyBCVEMgU2VtYW5hbDwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNThyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBQRVRSNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjVyZW07bWFyZ2luLWxlZnQ6NnB4IiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3BldHI0JykiPuKGuyByZWNhcnJlZ2FyPC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InBldHI0LWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi41OHJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4o8L3NwYW4+IFZBTEUzIDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZTouNXJlbTttYXJnaW4tbGVmdDo2cHgiIG9uY2xpY2s9InJlbG9hZEluZCgndmFsZTMnKSI+4oa7IHJlY2FycmVnYXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0idmFsZTMtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjU4cmVtO3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+PHNwYW4gY2xhc3M9ImFjYyI+8J+Tijwvc3Bhbj4gQkJBUzMgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOi41cmVtO21hcmdpbi1sZWZ0OjZweCIgb25jbGljaz0icmVsb2FkSW5kKCdiYmFzMycpIj7ihrsgcmVjYXJyZWdhcjwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJiYmFzMy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNThyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBBWElBMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjVyZW07bWFyZ2luLWxlZnQ6NnB4IiBvbmNsaWNrPSJyZWxvYWRJbmQoJ2F4aWEzJykiPuKGuyByZWNhcnJlZ2FyPC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9ImF4aWEzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi41OHJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4o8L3NwYW4+IFJPWE8zNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjVyZW07bWFyZ2luLWxlZnQ6NnB4IiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3JveG8zNCcpIj7ihrsgcmVjYXJyZWdhcjwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJyb3hvMzQtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjU4cmVtO3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2Pgo8L2Rpdj4KCjwhLS0gUE9TScOHw5VFUyAtLT4KPGRpdiBpZD0idGFiLXBvc2ljb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImFjYyI+MDE8L3NwYW4+IE9wZXJhw6fDtWVzIEF0aXZhczwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIj4KICAgIDxkaXYgY2xhc3M9InBvcy1sYmwiPlBldHJvYnJhcyBQTiDCtyBDYWxsIFZlbmRpZGEgwrcgUEVUUkwzMTkgwrcgVmVuYyAxNy8xMi8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGsiPlBFVFI0PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHIgbG9hZGluZyIgaWQ9InB0LXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0icHQtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZSByZWYuIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgMzAsODU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlIChQRVRSTDMxOSk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCAzMCw4NTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gYXR1YWwgdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0icHQtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNy8xMi8yMDI2IMK3IDxzcGFuIGlkPSJwdC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjQzLDQlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIEImYW1wO1MgZXhlcmNlciAodm9sLmltcGwuKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjksNCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gTUMgZXhlcmNlciAodm9sLmhpc3QuKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIiBpZD0ibWMtcHQtcnQiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10dGwiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FsbCBzZXIgZXhlcmNpZGE8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcHQtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW0iPkNhbGN1bGFuZG8gNS4wMDAgY2Vuw6FyaW9zLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXB0LXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo1cHg7bWFyZ2luLXRvcDo1cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UHJvYi4gZXhlcmNlciBjYWxsPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCIgaWQ9Im1jLXB0LXN0cmlrZSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtcHQtdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NHB4O2xpbmUtaGVpZ2h0OjEuNSIgaWQ9Im1jLXB0LWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ibWFyZ2luLXRvcDo3cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxibCI+VmFsZSBPTiDCtyBDYWxsIFZlbmRpZGEgwrcgVkFMRUI1NzQgwrcgVmVuYyAxOC8wMi8yMDI3PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGsiPlZBTEUzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHIgbG9hZGluZyIgaWQ9InZsLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0idmwtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZSByZWYuIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTcsNDA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlIChWQUxFQjU3NCk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA1Nyw0MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gYXR1YWwgdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0idmwtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xOC8wMi8yMDI3IMK3IDxzcGFuIGlkPSJ2bC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjcxLDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIEImYW1wO1MgZXhlcmNlciAodm9sLmltcGwuKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjE0LDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DIGV4ZXJjZXIgKHZvbC5oaXN0Lik8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayIgaWQ9Im1jLXZsLXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdHRsIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhbGwgc2VyIGV4ZXJjaWRhPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXZsLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42cmVtIj5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy12bC1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NXB4O21hcmdpbi10b3A6NXB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlByb2IuIGV4ZXJjZXIgY2FsbDwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwiIGlkPSJtYy12bC1zdHJpa2UiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLXZsLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjRweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJtYy12bC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6N3B4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy1sYmwiPkFYSUEzIChBKSDCtyBCaWRpcmVjaW9uYWwgwrcgVmVuYyAxNC8wOS8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGsiPkFYSUEzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHIgbG9hZGluZyIgaWQ9ImF4aWEzLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0iYXhpYTMtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyByZWYuIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTQsMzE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDQzLDUxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktVTyAoKzI2LDYlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDY4LDc2PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBjLyBiYXIuIGFsdGEgS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+KzQlIGZpeG88L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNC8wOS8yMDI2IMK3IDxzcGFuIGlkPSJheGlhM2YtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMta2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzLWt1by1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMtc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10dGwiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgQ2Vuw6FyaW9zIGRlIGJhcnJlaXJhPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42cmVtIj5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzLXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo1cHg7bWFyZ2luLXRvcDo1cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+U2VtIEJhcnJlaXJhIOKchTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy1heGlhMy1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhMy1rdW8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIGRvd24iIGlkPSJtYy1heGlhMy1rZG8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLWF4aWEzLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjRweCIgaWQ9Im1jLWF4aWEzLWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ibWFyZ2luLXRvcDo3cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxibCI+QVhJQTMgKEIpIMK3IEJpZGlyZWNpb25hbCBJT04gSXRhw7ogwrcgVmVuYyAwMi8xMC8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGsiPkFYSUEzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHIgbG9hZGluZyIgaWQ9ImF4aWEzYi1wb3MtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icG9zLWNoZyIgaWQ9ImF4aWEzYi1wb3MtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJlw6dvIHJlZi4gZW50cmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCA1MCw2NTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgNDAsNTI8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S1VPICgrMjQlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDYyLDgxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBjLyBiYXIuIGFsdGEgS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+KzQlIGZpeG8gKDEyLDMzJSBhLmEuKTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjAyLzEwLzIwMjYgwrcgPHNwYW4gaWQ9ImF4aWEzYi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gS0RPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhM2Ita2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzYi1rdW8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzYi1zdGF0dXMiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXR0bCIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBDZW7DoXJpb3MgZGUgYmFycmVpcmE8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtYXhpYTNiLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42cmVtIj5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzYi1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NXB4O21hcmdpbi10b3A6NXB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlNlbSBCYXJyZWlyYSDinIU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtYXhpYTNiLW5vYnIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBBbHRhIEtVTzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLWF4aWEzYi1rdW8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIGRvd24iIGlkPSJtYy1heGlhM2Ita2RvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhM2Itdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NHB4IiBpZD0ibWMtYXhpYTNiLWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ibWFyZ2luLXRvcDo3cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxibCI+Uk9YTzM0IMK3IEJEUiBOdWJhbmsgwrcgUHJlZml4YWRvIGMvIEJhcnJlaXJhIMK3IFZlbmMgMTYvMDcvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXRrIj5ST1hPMzQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wciBsb2FkaW5nIiBpZD0icm94bzM0LXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0icm94bzM0LXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gcmVmLiBlbnRyYWRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDEyLDg4PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkJhcnJlaXJhIFJPWE9HMTA1PC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgMTAsNTA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNi8wNy8yMDI2IMK3IDxzcGFuIGlkPSJyb3hvMzQtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJyb3hvMzQta2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJyb3hvMzQtc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10dGwiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gc3VjZXNzbzwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1yb3hvMzQtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW0iPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcm94bzM0LXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo1cHg7bWFyZ2luLXRvcDo1cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UHJvYi4gU3VjZXNzbzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy1yb3hvMzQtc3VjZXNzbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5DYWxsIEV4ZXJjaWRhPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtcm94bzM0LWNhbGwiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+S0RPIEF0aW5naWRvPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBkb3duIiBpZD0ibWMtcm94bzM0LWtkbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtcm94bzM0LXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjRweCIgaWQ9Im1jLXJveG8zNC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4E8L3NwYW4+IEVuY2VycmFkYXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im9wYWNpdHk6LjU1O2JvcmRlci1jb2xvcjojMWMxYzFjO21hcmdpbi10b3A6NHB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy10ayIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjgycmVtIj5CQkFTMzwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPjxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlIEJCQVNIMjE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgMjEsNjUgwrcgUmVmIFIkIDIwLDY3PC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSA4MCUgZG8gYWx2byBlbSA3MCUgZG8gcHJhem88L3NwYW4+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJvcGFjaXR5Oi41NTtib3JkZXItY29sb3I6IzFjMWMxYzttYXJnaW4tdG9wOjRweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGsiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi44MnJlbSI+QVhJQTMgU2hvcnQgU3RyYW5nbGU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkNhbGwgVi4gQVhJQUk1MDU8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTAsNTA8L3NwYW4+PC9kaXY+PGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+4pyFIEHDp8O1ZXMgbGliZXJhZGFzPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ib3BhY2l0eTouNTU7Ym9yZGVyLWNvbG9yOiMxYzFjMWM7bWFyZ2luLXRvcDo0cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLXRrIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouODJyZW0iPlJPWE8zNCBQcmVmaXhhZG8gNywxJTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPjxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RW5jZXJyYWRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjA0LzA2LzIwMjY8L3NwYW4+PC9kaXY+PGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+4pyFIH41LDE3JSAoNzIlIGRvIGFsdm8pPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjwhLS0gQ0FMRU5Ew4FSSU8gLS0+CjxkaXYgaWQ9InRhYi1jYWxlbmRhcmlvIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbTo5cHgiPgogICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41MnJlbTtjb2xvcjp2YXIoLS1tdXRlZCkiPvCfh7rwn4e4IPCfh6fwn4e3IPCfh6rwn4e6IPCfh6zwn4enIPCfh6jwn4ezIPCfh6/wn4e1IPCfh6nwn4eqIPCfh6jwn4emIMK3IEltcGFjdG8gTcOpZGlvKzwvZGl2PgogICAgPGJ1dHRvbiBvbmNsaWNrPSJsb2FkQ2FsZW5kYXIoKSIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tYWNjZW50KTtwYWRkaW5nOjRweCAxMHB4O2ZvbnQtc2l6ZTouNTZyZW07Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtsZXR0ZXItc3BhY2luZzouMDVlbSI+4oa7IEF0dWFsaXphcjwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgaWQ9ImNhbC1zdGF0dXMiIHN0eWxlPSJmb250LXNpemU6LjQ4cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjVweDttaW4taGVpZ2h0OjEzcHgiPjwvZGl2PgogIDxkaXYgaWQ9ImNhbGVuZGFyLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjZyZW07cGFkZGluZzoxOHB4O3RleHQtYWxpZ246Y2VudGVyIj5DbGlxdWUgZW0gQXR1YWxpemFyPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgQkFTRT0naHR0cHM6Ly90cmFkZXItZGVzay5vbnJlbmRlci5jb20nOwovLyBUaWNrZXJzIGNvcnJpZ2lkb3M6IERURVgz4oaSRFhDTzMsIEJSSVQz4oaSQlJEVDMsIGNvbnN1bW9fYy9uIHJlbm9tZWFkb3MKY29uc3QgU0VHPXsKICAnZmluYW5jZWlybyc6ICBbJ0lUVUI0JywnQkJEQzQnLCdCQkFTMycsJ1NBTkIxMScsJ0IzU0EzJywnQlBBQzExJywnSVRTQTQnLCdCUlNSNicsJ0FCQ0I0JywnQk1HQjQnXSwKICAncGV0cm9sZW8nOiAgICBbJ1BFVFI0JywnUEVUUjMnLCdQUklPMycsJ0JSQVYzJywnVkJCUjMnLCdDU0FOMycsJ1JFQ1YzJywnVUdQQTMnLCdTRVFMMycsJ0VOQVQzJ10sCiAgJ21pbmVyYWNhbyc6ICAgWydWQUxFMycsJ0dHQlI0JywnQ1NOQTMnLCdVU0lNNScsJ0JSQVA0JywnRkVTQTQnLCdDTUlOMycsJ0NCQVYzJywnR09BVTQnLCdQR01OMyddLAogICdtYXRlcmlhaXMnOiAgIFsnU1VaQjMnLCdLTEJOMTEnLCdEWENPMycsJ1VOSVA2JywnUkFOSTMnLCdPUlZSMycsJ1NNVE8zJywnRlJBUzMnLCdMUFNCMycsJ0NTVUQzJ10sCiAgJ3V0aWxpZGFkZSc6ICAgWydBWElBMycsJ0VRVEwzJywnQ1BGRTMnLCdTQlNQMycsJ0NNSUc0JywnRU5HSTExJywnVEFFRTExJywnQVVSRTMnLCdFR0lFMycsJ0NQTEUzJ10sCiAgJ2NvbnN1bW9fYyc6ICAgWydSRU5UMycsJ0xSRU4zJywnTUdMVTMnLCdDWVJFMycsJ01SVkUzJywnQVpaQTMnLCdWSVZBMycsJ1NCRkczJywnWURVUTMnLCdMV1NBMyddLAogICdjb25zdW1vX24nOiAgIFsnQUJFVjMnLCdKQlNTMycsJ0JSRlMzJywnTkFUVTMnLCdNRElBMycsJ0JFRUYzJywnU0xDRTMnLCdNVFJFMycsJ0NBTUwzJywnUENBUjMnXSwKICAnc2F1ZGUnOiAgICAgICBbJ1JET1IzJywnSEFQVjMnLCdGTFJZMycsJ0RBU0EzJywnUVVBTDMnLCdPTkNPMycsJ1BOVkwzJywnT0RQVjMnLCdNQVREMycsJ0FBTFIzJ10sCiAgJ2luZHVzdHJpYWlzJzogWydXRUdFMycsJ0VNQlIzJywnUkFJTDMnLCdUR01BMycsJ1JPTUkzJywnVkxJRDMnLCdUVVBZMycsJ0lSQlIzJywnUE9NTzQnLCdMQVZWMyddLAogICd0aV90ZWxlY29tJzogIFsnVklWVDMnLCdUSU1TMycsJ1RPVFZTMycsJ09JQlIzJywnTUxBUzMnLCdBTklNMycsJ1BPU0kzJywnSU5UQjMnLCdTUUlBMycsJ0lGQ00zJ10sCn07CmNvbnN0IFVTX1NFRz17CiAgJ21hZzcnOiAgICBbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdHT09HTCcsJ01FVEEnLCdUU0xBJ10sCiAgJ25hc2RhcTE1JzpbJ0FBUEwnLCdNU0ZUJywnTlZEQScsJ0FNWk4nLCdNRVRBJywnR09PR0wnLCdUU0xBJywnQVZHTycsJ0NPU1QnLCdORkxYJywnUUNPTScsJ0FNRCcsJ0FEQkUnLCdJTlRDJywnQ1NDTyddLAogICdzcDIwJzogICAgWydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdCUksuQicsJ0pQTScsJ0xMWScsJ1YnLCdVTkgnLCdYT00nLCdNQScsJ05GTFgnLCdQRycsJ0pOSicsJ0hEJywnQkFDJ10sCiAgJ2RqaTIwJzogICBbJ1VOSCcsJ0dTJywnSEQnLCdTSFcnLCdDQVQnLCdBWFAnLCdNQ0QnLCdBTUdOJywnVicsJ1RSVicsJ0lCTScsJ0pQTScsJ0hPTicsJ0NSTScsJ0NWWCcsJ0FBUEwnLCdNU0ZUJywnRElTJywnTktFJywnQkEnXQp9Owpjb25zdCBmQlJMPXY9PnYhPW51bGw/J1IkICcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21pbmltdW1GcmFjdGlvbkRpZ2l0czoyLG1heGltdW1GcmFjdGlvbkRpZ2l0czoyfSk6J+KAlCc7CmNvbnN0IGZVU0Q9dj0+diE9bnVsbD8nVVMkICcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21pbmltdW1GcmFjdGlvbkRpZ2l0czoyLG1heGltdW1GcmFjdGlvbkRpZ2l0czoyfSk6J+KAlCc7CmNvbnN0IGZQVFM9dj0+diE9bnVsbD9OdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KTon4oCUJzsKZnVuY3Rpb24gc2V0RWwoaWQsdHh0KXtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47ZS50ZXh0Q29udGVudD10eHQ7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQpmdW5jdGlvbiBzZXRDaGcoaWQsbm93LHByZXYsdHlwZSl7Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuO2NvbnN0IGRpZmY9bm93LXByZXY7Y29uc3QgcGN0PShkaWZmL01hdGguYWJzKHByZXZ8fDEpKjEwMCkudG9GaXhlZCgyKTtjb25zdCBzaWduPWRpZmY+PTA/JysnOicnO2lmKHR5cGU9PT0nYnJsJyllLnRleHRDb250ZW50PXNpZ24rJ1IkICcrTWF0aC5hYnMoZGlmZikudG9GaXhlZCgyKSsnICgnK3NpZ24rcGN0KyclKSc7ZWxzZSBpZih0eXBlPT09J3VzZCcpZS50ZXh0Q29udGVudD1zaWduK2RpZmYudG9GaXhlZCgyKSsnICgnK3NpZ24rcGN0KyclKSc7ZWxzZSBlLnRleHRDb250ZW50PXNpZ24rTWF0aC5hYnMoZGlmZikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnICgnK3NpZ24rcGN0KyclKSc7ZS5jbGFzc05hbWU9J2MtY2ggJysoZGlmZj4wPydjaGctdXAnOmRpZmY8MD8nY2hnLWRuJzonY2hnLWZsJyk7fQpmdW5jdGlvbiBzd2l0Y2hUYWIodGFiLGVsKXtkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiJykuZm9yRWFjaCh0PT50LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTtkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcudGFiLWNvbnRlbnQnKS5mb3JFYWNoKHQ9PnQuY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJykpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0YWItJyt0YWIpLmNsYXNzTGlzdC5hZGQoJ2FjdGl2ZScpO2lmKGVsKWVsLmNsYXNzTGlzdC5hZGQoJ2FjdGl2ZScpO2lmKHRhYj09PSdpbmRpY2Fkb3JlcycmJiF3aW5kb3cuX2luZExvYWRlZCl7d2luZG93Ll9pbmRMb2FkZWQ9dHJ1ZTtsb2FkSW5kaWNhdG9ycygpO31pZih0YWI9PT0nY2FsZW5kYXJpbycpbG9hZENhbGVuZGFyKCk7fQpmdW5jdGlvbiB0b2dnbGVTZWcoaWQpe2NvbnN0IGI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Nib2R5LScraWQpO2NvbnN0IGE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NhcnItJytpZCk7aWYoIWIpcmV0dXJuO2NvbnN0IG9wZW49Yi5zdHlsZS5kaXNwbGF5IT09J2Jsb2NrJztiLnN0eWxlLmRpc3BsYXk9b3Blbj8nYmxvY2snOidub25lJztpZihhKWEudGV4dENvbnRlbnQ9b3Blbj8n4payJzon4pa8JztpZihvcGVuJiYhYi5kYXRhc2V0LmxvYWRlZCl7Yi5kYXRhc2V0LmxvYWRlZD0nMSc7bG9hZFNlZ21lbnQoaWQpO319Cgphc3luYyBmdW5jdGlvbiBsb2FkU2VnbWVudChpZCl7CiAgY29uc3QgZ3JpZD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2dyaWQtJytpZCk7aWYoIWdyaWQpcmV0dXJuOwogIGNvbnN0IHBmeD1pZCsnX18nOwogIGlmKFVTX1NFR1tpZF0pewogICAgY29uc3QgdGtzPVVTX1NFR1tpZF07CiAgICBncmlkLmlubmVySFRNTD10a3MubWFwKHQ9Pntjb25zdCB0aWQ9dC5yZXBsYWNlKC9bXmEtekEtWjAtOV0vZywnXycpO3JldHVybiAnPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjLWxibCI+VVM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nO30pLmpvaW4oJycpOwogICAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL3VzL3F1b3Rlcz90aWNrZXJzPScrdGtzLmpvaW4oJywnKSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7T2JqZWN0LmVudHJpZXMoZCkuZm9yRWFjaCgoW3Qsdl0pPT57Y29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTtjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfcCcpO2NvbnN0IGVjPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19jJyk7aWYoZXAmJnYucHJpY2Upe2VwLnRleHRDb250ZW50PSckJytOdW1iZXIodi5wcmljZSkudG9GaXhlZCgyKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fWlmKGVjJiZ2LnByaWNlJiZ2LnByZXYpc2V0Q2hnKHBmeCt0aWQrJ19jJyx2LnByaWNlLHYucHJldiwndXNkJyk7fSk7fWNhdGNoKGUpe30KICAgIHJldHVybjsKICB9CiAgY29uc3QgdGtzPVNFR1tpZF07aWYoIXRrcylyZXR1cm47CiAgZ3JpZC5pbm5lckhUTUw9dGtzLm1hcCh0PT57Y29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKS5yZXBsYWNlKC9bXmEtejAtOV0vZywnXycpO3JldHVybiAnPGRpdiBjbGFzcz0iY2FyZCBnIj48ZGl2IGNsYXNzPSJjLWxibCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nO30pLmpvaW4oJycpOwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL3R2L2JyYXppbCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOnRrcy5tYXAodD0+J0JNRkJPVkVTUEE6Jyt0KX0sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTsKICAgIGlmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgKGQuZGF0YXx8W10pLmZvckVhY2goeD0+ewogICAgICBjb25zdCB0PXgucy5yZXBsYWNlKCdCTUZCT1ZFU1BBOicsJycpLnRvTG93ZXJDYXNlKCkucmVwbGFjZSgvW15hLXowLTldL2csJ18nKTsKICAgICAgY29uc3RbYyxjYV09eC5kfHxbXTsKICAgICAgaWYoYyE9bnVsbCl7Y29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3QrJ19wJyk7aWYoZXApe2VwLnRleHRDb250ZW50PWZCUkwoYyk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO31zZXRDaGcocGZ4K3QrJ19jJyxjLGMtKGNhfHwwKSwnYnJsJyk7fQogICAgfSk7CiAgfWNhdGNoKGUpe30KfQoKYXN5bmMgZnVuY3Rpb24gZmV0Y2hITCgpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkLkJUQ3x8MCk7aWYoYnA+MCl7c2V0RWwoJ2J0Yy1wJyxmVVNEKGJwKSk7c2V0Q2hnKCdidGMtYycsYnAsYnAqMC45OSwndXNkJyk7fXRyeXtjb25zdCByMj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcycsZGV4Oid4eXonfSl9KTtpZihyMi5vayl7Y29uc3QgZDI9YXdhaXQgcjIuanNvbigpO2lmKGQyWyd4eXo6Q0wnXSlzZXRFbCgnY2wtcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDTCddKS50b0ZpeGVkKDIpKTtpZihkMlsneHl6OkdPTEQnXSlzZXRFbCgnZ29sZC1wJywnJCcrTnVtYmVyKGQyWyd4eXo6R09MRCddKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTtpZihkMlsneHl6OlNJTFZFUiddKXNldEVsKCdzaWx2ZXItcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpTSUxWRVInXSkudG9GaXhlZCgyKSk7aWYoZDJbJ3h5ejpDT1BQRVInXSlzZXRFbCgnY29wcGVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q09QUEVSJ10pLnRvRml4ZWQoMykpO319Y2F0Y2goZSl7fX1jYXRjaChlKXt9fQphc3luYyBmdW5jdGlvbiBmZXRjaFRWKCl7Y29uc3Qgb3V0PXt9O3RyeXtjb25zdCB0a3M9WydCTUZCT1ZFU1BBOlBFVFI0JywnQk1GQk9WRVNQQTpJVFVCNCcsJ0JNRkJPVkVTUEE6VkFMRTMnLCdCTUZCT1ZFU1BBOkJCREM0JywnQk1GQk9WRVNQQTpBQkVWMycsJ0JNRkJPVkVTUEE6QkJBUzMnLCdCTUZCT1ZFU1BBOldFR0UzJywnQk1GQk9WRVNQQTpJQk9WJ107Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pO2lmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7KGQuZGF0YXx8W10pLmZvckVhY2goeD0+e2NvbnN0W2MsY2FdPXguZHx8W107aWYoYyE9bnVsbClvdXRbeC5zXT17cDpjLHY6Yy0oY2F8fDApfTt9KTt9fWNhdGNoKGUpe310cnl7Y29uc3QgcnI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYocnIub2spe2NvbnN0IGRkPWF3YWl0IHJyLmpzb24oKTtpZihkZC5wcmVjb19hdHVhbCl7c2V0RWwoJ3JveG8zNHEtcCcsZkJSTChkZC5wcmVjb19hdHVhbCkpO3NldENoZygncm94bzM0cS1jJyxkZC5wcmVjb19hdHVhbCwoZGQucHJlY29fYW50ZXJpb3J8fGRkLnByZWNvX2F0dWFsKjAuOTkpLCdicmwnKTt9fX1jYXRjaChlKXt9cmV0dXJuIG91dDt9CmFzeW5jIGZ1bmN0aW9uIGZldGNoRnV0dXJlcygpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9mdXR1cmVzJyk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEZ1bmRpbmcoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9mYXBpLmJpbmFuY2UuY29tL2ZhcGkvdjEvcHJlbWl1bUluZGV4P3N5bWJvbD1CVENVU0RUJyk7aWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtzZXRFbCgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlfHwwKSoxMDApLnRvRml4ZWQoNCkrJyUnKTtyZXR1cm47fX1jYXRjaChlKXt9dHJ5e2NvbnN0IHIyPWF3YWl0IGZldGNoKEJBU0UrJy9iaW5hbmNlL2Z1bmRpbmcnKTtpZighcjIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgcjIuanNvbigpO2lmKGQubGFzdEZ1bmRpbmdSYXRlKXNldEVsKCdidGMtZnVuZCcsKHBhcnNlRmxvYXQoZC5sYXN0RnVuZGluZ1JhdGUpKjEwMCkudG9GaXhlZCg0KSsnJScpO31jYXRjaChlKXt9fQoKZnVuY3Rpb24gZG9NYWNybyh0dixmdXR1cmVzKXsKICBjb25zdCBpYkQ9dHZbJ0JNRkJPVkVTUEE6SUJPViddO2lmKGliRCl7c2V0RWwoJ2lib3YtcCcsZlBUUyhpYkQucCkpO3NldENoZygnaWJvdi1jJyxpYkQucCxpYkQudiwncHRzJyk7fQogIFtbJ1BFVFI0JywncGV0cjRxJ10sWydJVFVCNCcsJ2l0dWI0cSddLFsnVkFMRTMnLCd2YWxlM3EnXSxbJ0JCREM0JywnYmJkYzRxJ10sWydBQkVWMycsJ2FiZXYzcSddLFsnQkJBUzMnLCdiYmFzM3EnXSxbJ1dFR0UzJywnd2VnZTNxJ11dLmZvckVhY2goKFt0LGlkXSk9Pntjb25zdCBkPXR2WydCTUZCT1ZFU1BBOicrdF07aWYoZCl7c2V0RWwoaWQrJy1wJyxmQlJMKGQucCkpO3NldENoZyhpZCsnLWMnLGQucCxkLnYsJ2JybCcpO319KTsKICBpZihmdXR1cmVzKXtjb25zdCBmPWZ1dHVyZXM7CiAgICBjb25zdCBhZj0oaWQsdmFsKT0+e2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKGUpe2UudGV4dENvbnRlbnQ9dmFsO2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO319OwogICAgaWYoZi5kamk/LnByaWNlKXthZignZGppLXAnLGZQVFMoZi5kamkucHJpY2UpKTtzZXRDaGcoJ2RqaS1jJyxmLmRqaS5wcmljZSxmLmRqaS5wcmV2LCdwdHMnKTt9CiAgICBpZihmLmVzZj8ucHJpY2Upe2FmKCdlc2YtcCcsZlBUUyhmLmVzZi5wcmljZSkpO3NldENoZygnZXNmLWMnLGYuZXNmLnByaWNlLGYuZXNmLnByZXYsJ3B0cycpO30KICAgIGlmKGYubnFmPy5wcmljZSl7YWYoJ25xZi1wJyxmUFRTKGYubnFmLnByaWNlKSk7c2V0Q2hnKCducWYtYycsZi5ucWYucHJpY2UsZi5ucWYucHJldiwncHRzJyk7fQogICAgaWYoZi53aW4/LnByaWNlKXthZignd2luLXAnLGZQVFMoZi53aW4ucHJpY2UpKTtzZXRDaGcoJ3dpbi1jJyxmLndpbi5wcmljZSxmLndpbi5wcmV2LCdwdHMnKTt9CiAgICBpZihmLnZpeD8ucHJpY2Upe2FmKCd2aXgtcCcsTnVtYmVyKGYudml4LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ3ZpeC1jJyxmLnZpeC5wcmljZSxmLnZpeC5wcmV2LCd1c2QnKTt9CiAgICBpZihmLmR4eT8ucHJpY2Upe2FmKCdkeHktcCcsTnVtYmVyKGYuZHh5LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ2R4eS1jJyxmLmR4eS5wcmljZSxmLmR4eS5wcmV2LCd1c2QnKTt9CiAgICBpZihmLnVzZD8ucHJpY2Upe2FmKCd1c2QtcCcsZkJSTChmLnVzZC5wcmljZSkpO3NldENoZygndXNkLWMnLGYudXNkLnByaWNlLGYudXNkLnByZXZ8fGYudXNkLnByaWNlLCdicmwnKTt9CiAgfQp9CgpmdW5jdGlvbiBkb1Bvc2l0aW9ucyh0dil7CiAgY29uc3QgcHREPXR2WydCTUZCT1ZFU1BBOlBFVFI0J107Y29uc3QgcHRQPXB0RD8ucHx8NDAscHRWPXB0RD8udnx8NDA7CiAgc2V0RWwoJ3B0LXBvcy1wJyxmQlJMKHB0UCkpO3NldENoZygncHQtcG9zLWMnLHB0UCxwdFYsJ2JybCcpOwogIGNvbnN0IHB0RDI9cHRQLTMwLjg1O3NldEVsKCdwdC1pdG0nLChwdEQyPj0wPycrIFIkICc6Jy0gUiQgJykrTWF0aC5hYnMocHREMikudG9GaXhlZCgyKSsnICcrKHB0RDI+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCB2bEQ9dHZbJ0JNRkJPVkVTUEE6VkFMRTMnXTtjb25zdCB2bFA9dmxEPy5wfHw3OCx2bFY9dmxEPy52fHw3ODsKICBzZXRFbCgndmwtcG9zLXAnLGZCUkwodmxQKSk7c2V0Q2hnKCd2bC1wb3MtYycsdmxQLHZsViwnYnJsJyk7CiAgY29uc3QgdmxEMj12bFAtNTcuNDA7c2V0RWwoJ3ZsLWl0bScsKHZsRDI+PTA/JysgUiQgJzonLSBSJCAnKStNYXRoLmFicyh2bEQyKS50b0ZpeGVkKDIpKycgJysodmxEMj49MD8nYWNpbWEnOidhYmFpeG8nKSsnIGRvIHN0cmlrZScpOwogIGNvbnN0IGNkPShkcyxlaWQpPT57Y29uc3Qgdj1uZXcgRGF0ZShkcyk7Y29uc3QgZD1NYXRoLm1heCgwLE1hdGguY2VpbCgodi1uZXcgRGF0ZSgpKS84NjRlNSkpO2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoZWlkKTtpZihlKWUudGV4dENvbnRlbnQ9ZDt9OwogIGNkKCcyMDI2LTEyLTE3JywncHQtZGlhcycpO2NkKCcyMDI3LTAyLTE4JywndmwtZGlhcycpO2NkKCcyMDI2LTA5LTE0JywnYXhpYTNmLWRpYXMnKTtjZCgnMjAyNi0xMC0wMicsJ2F4aWEzYi1kaWFzJyk7Y2QoJzIwMjYtMDctMTYnLCdyb3hvMzQtZGlhcycpOwogIHNldFRpbWVvdXQoYXN5bmMoKT0+e3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9pbmRpY2F0b3JzL0FYSUEzLlNBJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJlY29fYXR1YWwpcmV0dXJuO2NvbnN0IHA9ZC5wcmVjb19hdHVhbDtzZXRFbCgnYXhpYTMtcG9zLXAnLGZCUkwocCkpO3NldEVsKCdheGlhM2ItcG9zLXAnLGZCUkwocCkpO2NvbnN0IGtkb0E9NDMuNTEsa3VvQT02OC43NixrZG9CPTQwLjUyLGt1b0I9NjIuODE7Y29uc3QgZEE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzLWtkby1kaXN0Jyk7aWYoZEEpZEEudGV4dENvbnRlbnQ9KChwLWtkb0EpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7Y29uc3QgdUE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzLWt1by1kaXN0Jyk7aWYodUEpdUEudGV4dENvbnRlbnQ9KChrdW9BLXApL3AqMTAwKS50b0ZpeGVkKDEpKyclIHBhcmEgbyBLVU8nO2NvbnN0IHNBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1zdGF0dXMnKTtpZihzQSl7c0EudGV4dENvbnRlbnQ9cDw9a2RvQT8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1b0E/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NBLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PWtkb0F8fHA+PWt1b0E/J3dhcm4nOidvaycpO31jb25zdCBkQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTNiLWtkby1kaXN0Jyk7aWYoZEIpZEIudGV4dENvbnRlbnQ9KChwLWtkb0IpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7Y29uc3QgdUI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1rdW8tZGlzdCcpO2lmKHVCKXVCLnRleHRDb250ZW50PSgoa3VvQi1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJztjb25zdCBzQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTNiLXN0YXR1cycpO2lmKHNCKXtzQi50ZXh0Q29udGVudD1wPD1rZG9CPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VvQj8n4pqgIEtVTyBBVElOR0lETyc6J+KchSBObyByYW5nZSc7c0IuY2xhc3NOYW1lPSdzYi12YWwgJysocDw9a2RvQnx8cD49a3VvQj8nd2Fybic6J29rJyk7fX1jYXRjaChlKXt9fSwyMDAwKTsKICBzZXRUaW1lb3V0KGFzeW5jKCk9Pnt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy9ST1hPMzQuU0EnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZighZC5wcmVjb19hdHVhbClyZXR1cm47Y29uc3QgcD1kLnByZWNvX2F0dWFsO3NldEVsKCdyb3hvMzQtcG9zLXAnLGZCUkwocCkpO2NvbnN0IGRlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyb3hvMzQta2RvLWRpc3QnKTtpZihkZSlkZS50ZXh0Q29udGVudD0oKHAtMTAuNTApL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRhIGJhcnJlaXJhJztjb25zdCBzZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm94bzM0LXN0YXR1cycpO2lmKHNlKXtzZS50ZXh0Q29udGVudD1wPD0xMC41MD8n8J+UtCBCQVJSRUlSQSBBVElOR0lEQSc6J+KchSBBY2ltYSBkYSBiYXJyZWlyYSc7c2UuY2xhc3NOYW1lPSdzYi12YWwgJysocDw9MTAuNTA/J2l0bSc6J29rJyk7fX1jYXRjaChlKXt9fSwzMDAwKTsKfQoKLy8gTW9udGUgQ2FybG8g4oCUIENPUlJJR0lETzogcHJvYl9jYWxsX2V4ZXJjaWRhID0gcHJvYiBkZSBjYWxsIHNlciBleGVyY2lkYSAoc3ViaXIgYW8gc3RyaWtlKQphc3luYyBmdW5jdGlvbiBydW5NQ0ZvckF0aXZvKHRpY2tlcixzdHJpa2UsZGlhcyxsb2FkSWQscmVzSWQsc3RyaWtlSWQsdm9sSWQsaW5mb0lkLHJ0SWQpewogIHRyeXsKICAgIGNvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO2NvbnN0IHRvPXNldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXIsa19jYWxsOnN0cmlrZSxrX3B1dDpzdHJpa2UsdF9kYXlzOmRpYXMsbjo1MDAwfSl9KTsKICAgIGNsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQobG9hZElkKS5zdHlsZS5kaXNwbGF5PSdub25lJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHJlc0lkKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7CiAgICAvLyBwcm9iX2NhbGxfZXhlcmNpZGEgPSAlIGNoYW5jZSBkZSBzdWJpciBhY2ltYSBkbyBzdHJpa2UgPSBydWltIHBhcmEgY2FsbCB2ZW5kaWRhCiAgICBjb25zdCBwcm9iPU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYXx8MCk7CiAgICBjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoc3RyaWtlSWQpOwogICAgc0VsLnRleHRDb250ZW50PXByb2IudG9GaXhlZCgxKSsnJSc7CiAgICAvLyBWZXJkZSA9IGJhaXhhIHByb2IgZGUgc2VyIGV4ZXJjaWRhID0gYm9tIHBhcmEgdmVuZGVkb3IKICAgIHNFbC5jbGFzc05hbWU9J2luZC12YWwgJysocHJvYjwxMD8nb2snOnByb2I8MjA/J3dhcm4nOidkb3duJyk7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCh2b2xJZCkudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpbmZvSWQpLnRleHRDb250ZW50PQogICAgICAnVm9sLmhpc3QuICcrZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSAoTUMpIHZzIHZvbC5pbXBsLiAoQiZTKSDigJQgJyArCiAgICAgICdCJlMgdXNhIHZvbCBpbXBsw61jaXRhIG1haW9yLCBwb3IgaXNzbyBwcm9iLiBCJlMgPiBNQyDCtyAnICsKICAgICAgJ1Byb2IuIGJhaXhhID0gcG9zacOnw6NvIHNhdWTDoXZlbCBwYXJhIGNhbGwgdmVuZGlkYSDinIUnOwogICAgaWYocnRJZClzZXRFbChydElkLHByb2IudG9GaXhlZCgxKSsnJScpOwogIH1jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChsb2FkSWQpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCdpbmRpc3BvbsOtdmVsJyk7fQp9CmFzeW5jIGZ1bmN0aW9uIHJ1bk1DQmFycmllcih0aWNrZXIsZW50cnksa2RvLGt1byxkaWFzLHByaWNlLHByZWZpeCl7CiAgcHJlZml4PXByZWZpeHx8J2F4aWEzJzsKICB0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7Y29uc3QgdG89c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTtjb25zdCBib2R5PXt0aWNrZXIsZW50cnksa2RvLGt1byx0X2RheXM6ZGlhcyxuOjMwMDB9O2lmKHByaWNlPjApYm9keS5wcmljZT1wcmljZTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9tb250ZWNhcmxvL2JhcnJpZXInLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoYm9keSl9KTtjbGVhclRpbWVvdXQodG8pO2lmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1sb2FkaW5nJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4KyctcmVzdWx0Jykuc3R5bGUuZGlzcGxheT0nYmxvY2snO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLW5vYnInKS50ZXh0Q29udGVudD1kLnByb2Jfc2VtX2JhcnJlaXJhLnRvRml4ZWQoMSkrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWt1bycpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9hbHRhLnRvRml4ZWQoMSkrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWtkbycpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9iYWl4YS50b0ZpeGVkKDEpKyclJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy12b2wnKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1pbmZvJykudGV4dENvbnRlbnQ9J1IkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua2RvKycgwrcgS1VPIFIkICcrZC5rdW8rJyDCtyAnK2QuY2VuYXJpb3MudG9Mb2NhbGVTdHJpbmcoKSsnIGNlbi4nO31jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1sb2FkaW5nJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J2luZGlzcG9uw612ZWwnKTt9Cn0KYXN5bmMgZnVuY3Rpb24gcnVuTUNQcmVmaXhhZG8odGlja2VyLGVudHJ5LGtkbyxkaWFzLHByaWNlKXsKICB0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7Y29uc3QgdG89c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTtjb25zdCBib2R5PXt0aWNrZXIsa19jYWxsOmVudHJ5LGtfcHV0OmVudHJ5LHRfZGF5czpkaWFzLGtub2NrX2Rvd246a2RvLG46NTAwMH07aWYocHJpY2U+MClib2R5LnByaWNlPXByaWNlO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoYm9keSl9KTtjbGVhclRpbWVvdXQodG8pO2lmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWxvYWRpbmcnKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LXJlc3VsdCcpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJztjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1zdWNlc3NvJyk7c0VsLnRleHRDb250ZW50PU51bWJlcihkLnByb2Jfc3VjZXNzbykudG9GaXhlZCgxKSsnJSc7c0VsLmNsYXNzTmFtZT0naW5kLXZhbCAnKyhkLnByb2Jfc3VjZXNzbz43MD8nb2snOmQucHJvYl9zdWNlc3NvPjUwPyd3YXJuJzonZG93bicpO2NvbnN0IGNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWNhbGwnKTtpZihjRWwpY0VsLnRleHRDb250ZW50PU51bWJlcihkLnByb2JfY2FsbF9leGVyY2lkYSkudG9GaXhlZCgxKSsnJSc7Y29uc3Qga0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQta2RvJyk7aWYoa0VsKWtFbC50ZXh0Q29udGVudD1kLnByb2Jfa2RvX2F0aW5naWRvIT1udWxsP051bWJlcihkLnByb2Jfa2RvX2F0aW5naWRvKS50b0ZpeGVkKDEpKyclJzon4oCUJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LXZvbCcpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtaW5mbycpLnRleHRDb250ZW50PSdSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtub2NrX2Rvd24rJyDCtyAnK2QuY2VuYXJpb3MudG9Mb2NhbGVTdHJpbmcoKSsnIGNlbi4nO31jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWxvYWRpbmcnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwnaW5kaXNwb27DrXZlbCcpO30KfQoKYXN5bmMgZnVuY3Rpb24gZmV0Y2hJbmRpY2F0b3JzKHRpY2tlcil7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwzMDAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy8nK3RpY2tlcix7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEJUQ0luZGljYXRvcnMoKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDE1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9idGMvaW5kaWNhdG9ycycse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hCVENDeWNsZSgpe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMTUwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2J0Yy9jeWNsZScse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hGZWFyR3JlZWQoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvZmVhcmdyZWVkJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7Y29uc3Qgdj1kLnZhbHVlfHw1MDtjb25zdCBjbHM9djw9MjU/J3ZhcigtLXJlZCknOnY8PTQ1Pyd2YXIoLS13YXJuKSc6djw9NzU/J3ZhcigtLWFjY2VudCknOid2YXIoLS1ncmVlbiknO2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmZWFyLWdyZWVkLWFyZWEnKTtpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMXB4Ij48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQ0cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjVweCI+8J+YsSBGRUFSICYgR1JFRUQgSU5ERVg8L2Rpdj48ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo5cHgiPjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxLjhyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOicrY2xzKyciPicrdisnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi43OHJlbTtmb250LXdlaWdodDo3MDA7Y29sb3I6JytjbHMrJyI+JysoZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpKyc8L2Rpdj48L2Rpdj48L2Rpdj4nO3NldEVsKCdmZy12YWwnLFN0cmluZyh2KSk7c2V0RWwoJ2ZnLWxibCcsZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpO3RyeXtjb25zdCByYj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pO2lmKHJiLm9rKXtjb25zdCBkYj1hd2FpdCByYi5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkYi5CVEN8fDApO2lmKGJwPjApe3NldEVsKCdidGMtaW5kLXByaWNlJywnJCcrTnVtYmVyKGJwKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTtzZXRFbCgnYnRjLXAnLGZVU0QoYnApKTt9fX1jYXRjaChlMil7fX1jYXRjaChlKXt9fQoKZnVuY3Rpb24gcmVuZGVySW5kaWNhdG9ycyhhcmVhSWQsZGF0YSxzaG93QWxsKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChhcmVhSWQpO2lmKCFlbClyZXR1cm47CiAgaWYoIWRhdGEpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7Zm9udC1zaXplOi42cmVtO3BhZGRpbmc6OXB4Ij7ij7MgU2VtIHJlc3Bvc3RhIOKAlCBjbGlxdWUg4oa7IHJlY2FycmVnYXI8L2Rpdj4nO3JldHVybjt9CiAgaWYoZGF0YS5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1yZWQpO2ZvbnQtc2l6ZTouNnJlbTtwYWRkaW5nOjlweCI+4pqgICcrZGF0YS5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGNvbnN0IGluZHM9ZGF0YS5pbmRpY2Fkb3Jlc3x8W107CiAgY29uc3Qgc2M9TnVtYmVyKGRhdGEuc2NvcmVfdG90YWx8fDApO2NvbnN0IHByZWNvPWRhdGEucHJlY29fYXR1YWw7Y29uc3QgZ3JhaGFtPWRhdGEuZ3JhaGFtX3ZhbHVlO2NvbnN0IHVwc2lkZT1kYXRhLnVwc2lkZV9ncmFoYW07Y29uc3Qgc2V0b3I9ZGF0YS5zZXRvcnx8Jyc7CiAgY29uc3Qgc2MyPXNjPj02NT8ndmFyKC0tZ3JlZW4pJzpzYz49NDA/J3ZhcigtLXdhcm4pJzondmFyKC0tcmVkKSc7CiAgY29uc3Qgc2w9c2M+PTY1PydDb21wcmEg4payJzpzYz49NDA/J05ldXRybyDihpInOidWZW5kYSDilrwnOwogIGxldCBodG1sPSc8ZGl2IGNsYXNzPSJzY29yZS1ib3giPicrCiAgICAnPGRpdiBjbGFzcz0ic2NvcmUtY2VsbCI+PGRpdiBjbGFzcz0ic2NvcmUtbWV0YSI+U2NvcmU8L2Rpdj48ZGl2IGNsYXNzPSJzY29yZS1udW0iIHN0eWxlPSJjb2xvcjonK3NjMisnIj4nK3NjKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY29yZS1sYmwiIHN0eWxlPSJjb2xvcjonK3NjMisnIj4nK3NsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjb3JlLWNlbGwiPjxkaXYgY2xhc3M9InNjb3JlLW1ldGEiPkNvdGHDp8OjbyBBdHVhbDwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXZhbCI+JysocHJlY28/J1IkICcrTnVtYmVyKHByZWNvKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NvcmUtc3ViIj4nK3NldG9yKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjb3JlLWNlbGwiPjxkaXYgY2xhc3M9InNjb3JlLW1ldGEiPkdyYWhhbSBWSjwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXZhbCIgc3R5bGU9ImNvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyhncmFoYW0/J1IkICcrTnVtYmVyKGdyYWhhbSkudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXN1YiIgc3R5bGU9ImNvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cHNpZGUhPW51bGw/KHVwc2lkZT4wPycrJzonJykrdXBzaWRlKyclIHVwc2lkZSc6J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzwvZGl2Pic7CiAgKHNob3dBbGw/aW5kczppbmRzLnNsaWNlKDAsMTQpKS5mb3JFYWNoKGk9PnsKICAgIGNvbnN0IHM9aS5zaW5hbHx8Jyc7CiAgICBjb25zdCBjbHM9cz09PSdBbHRhJ3x8cz09PSdTb2JyZXZlbmRhJz8nb2snOnM9PT0nQmFpeGEnfHxzPT09J1NvYnJlY29tcHJhJz8nZG93bic6J3dhcm4nOwogICAgY29uc3QgYXJyb3c9Y2xzPT09J29rJz8n4payJzpjbHM9PT0nZG93bic/J+KWvCc6J+KGkic7CiAgICBodG1sKz0nPGRpdiBjbGFzcz0iaW5kLXJvdyI+PGRpdiBjbGFzcz0iaW5kLXJvdy10b3AiPjxzcGFuIGNsYXNzPSJpbmQtcm93LW5vbWUiPicrKGkubm9tZXx8JycpKyc8L3NwYW4+PHNwYW4gY2xhc3M9ImluZC1yb3ctdmFsICcrY2xzKyciPicrKGkudmFsb3IhPW51bGw/aS52YWxvcjon4oCUJykrJyAnK2Fycm93Kyc8L3NwYW4+PC9kaXY+JysoaS5leHBsaWNhY2FvPyc8ZGl2IGNsYXNzPSJpbmQtcm93LWV4cCI+JytpLmV4cGxpY2FjYW8rJzwvZGl2Pic6JycpKyc8L2Rpdj4nOwogIH0pOwogIGVsLmlubmVySFRNTD1odG1sfHwnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNnJlbTtwYWRkaW5nOjhweCI+U2VtIGluZGljYWRvcmVzPC9kaXY+JzsKfQoKZnVuY3Rpb24gcmVuZGVyQlRDSW5kaWNhdG9ycyhkYXRhKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWluZC1hcmVhJyk7aWYoIWVsfHwhZGF0YSlyZXR1cm47CiAgaWYoZGF0YS5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS13YXJuKTtmb250LXNpemU6LjU4cmVtO3BhZGRpbmc6OXB4Ij7ij7MgJytkYXRhLmVycm9yKyc8L2Rpdj4nO3JldHVybjt9CiAgbGV0IGh0bWw9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NHB4Ij4nOwogIGlmKGRhdGEucnNpX3NlbWFuYWwhPW51bGwpe2NvbnN0IHI9ZGF0YS5yc2lfc2VtYW5hbDtjb25zdCBjbHM9cjwzMD8nb2snOnI+NzA/J2Rvd24nOid3YXJuJztodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsICcrY2xzKyciPicrci50b0ZpeGVkKDEpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQzcmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JysocjwzMD8nU29icmV2ZW5kYSDimqEnOnI+NzA/J1NvYnJlY29tcHJhIOKaoCc6J05ldXRybycpKyc8L2Rpdj48L2Rpdj4nO3NldEVsKCdidGMtcnNpJyxyLnRvRml4ZWQoMSkpO30KICBpZihkYXRhLm1tNTBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gNTAgc2VtLjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JCcrTnVtYmVyKGRhdGEubW01MF9zZW1hbmFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nOwogIGlmKGRhdGEubW0yMDBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gMjAwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPiQnK051bWJlcihkYXRhLm1tMjAwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZGF0YS5tYWNkX2hpc3RvZ3JhbSE9bnVsbCl7Y29uc3QgbWg9ZGF0YS5tYWNkX2hpc3RvZ3JhbTtodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TUFDRCBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysobWg+MD8nb2snOidkb3duJykrJyI+JytOdW1iZXIobWgpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDNyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4Ij4nKyhtaD4wPydNb21lbnR1bSDilrInOidNb21lbnR1bSDilrwnKSsnPC9kaXY+PC9kaXY+Jzt9CiAgaWYoZGF0YS5vYnZfdHJlbmQpaHRtbCs9JzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk9CVjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysoZGF0YS5vYnZfdHJlbmQ9PT0nc3ViaW5kbyc/J29rJzonZG93bicpKyciPicrZGF0YS5vYnZfdHJlbmQrJzwvZGl2PjwvZGl2Pic7CiAgaHRtbCs9JzwvZGl2Pic7ZWwuaW5uZXJIVE1MPWh0bWw7CiAgaWYoZGF0YS5wcmljZSlzZXRFbCgnYnRjLWluZC1wcmljZScsJyQnK051bWJlcihkYXRhLnByaWNlKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTsKfQoKZnVuY3Rpb24gcmVuZGVyQlRDQ3ljbGUoZCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1jeWNsZS1hcmVhJyk7aWYoIWVsfHwhZHx8ZC5lcnJvcilyZXR1cm47CiAgY29uc3QgZlU9dj0+dj8nJCcrTnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CiAgZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjRweDttYXJnaW4tYm90dG9tOjdweCI+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5NVlJWIFotU2NvcmU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsICcrKGQubXZydl96c2NvcmU/LnZhbHVlPDE/J29rJzpkLm12cnZfenNjb3JlPy52YWx1ZTwzPyd3YXJuJzonZG93bicpKyciPicrZC5tdnJ2X3pzY29yZT8udmFsdWUrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDNyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4Ij4nK2QubXZydl96c2NvcmU/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk5VUEw8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrKChkLm51cGw/LnZhbHVlfHwwKSoxMDApLnRvRml4ZWQoMCkrJyU8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQzcmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JytkLm51cGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlB1ZWxsIE11bHRpcGxlPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nK2QucHVlbGw/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQzcmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JytkLnB1ZWxsPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj4yMDBXIE1BPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nK2ZVKGQubWEyMDB3KSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40M3JlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDoycHgiPicrKGQubWEyMDB3X3BjdD8nKycrZC5tYTIwMHdfcGN0KyclJzonJykrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UmFpbmJvdyBCYW5kPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nKyhkLnJhaW5ib3c/LmJhbmR8fCfigJQnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5QaSBDeWNsZSBEaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siPicrZlUoZC5waV9jeWNsZT8uZGlzdGFuY2UpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzwvZGl2PicrCiAgICAnPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjdweDtmb250LXNpemU6LjU2cmVtO2NvbG9yOnZhcigtLWFjY2VudCkiPicrKGQucGlfY3ljbGU/LnNpZ25hbHx8JycpKyc8L2Rpdj4nOwp9Cgphc3luYyBmdW5jdGlvbiBsb2FkSW5kaWNhdG9ycygpewogIGNvbnN0IHd0PShwLG1zLGZiKT0+UHJvbWlzZS5yYWNlKFtwLG5ldyBQcm9taXNlKHI9PnNldFRpbWVvdXQoKCk9PnIoZmIpLG1zKSldKTsKICBjb25zdFtidGMsY3ljbGVdPWF3YWl0IFByb21pc2UuYWxsKFt3dChmZXRjaEJUQ0luZGljYXRvcnMoKSwxNTAwMCx7ZXJyb3I6J1RpbWVvdXQg4oCUIHJlY2FycmVndWUgYSBhYmEnfSksd3QoZmV0Y2hCVENDeWNsZSgpLDE1MDAwLG51bGwpXSk7CiAgcmVuZGVyQlRDSW5kaWNhdG9ycyhidGMpO3JlbmRlckJUQ0N5Y2xlKGN5Y2xlKTtmZXRjaEZlYXJHcmVlZCgpOwogIGNvbnN0IHN0b2Nrcz1bWydQRVRSNC5TQScsJ3BldHI0LWluZC1hcmVhJ10sWydWQUxFMy5TQScsJ3ZhbGUzLWluZC1hcmVhJ10sWydCQkFTMy5TQScsJ2JiYXMzLWluZC1hcmVhJ10sWydBWElBMy5TQScsJ2F4aWEzLWluZC1hcmVhJ10sWydST1hPMzQuU0EnLCdyb3hvMzQtaW5kLWFyZWEnXV07CiAgY29uc3QgcmVzdWx0cz1hd2FpdCBQcm9taXNlLmFsbChzdG9ja3MubWFwKChbdF0pPT53dChmZXRjaEluZGljYXRvcnModCksMzAwMDAse2Vycm9yOidUaW1lb3V0IDMwcyd9KSkpOwogIHN0b2Nrcy5mb3JFYWNoKChbLGFpZF0saSk9PnJlbmRlckluZGljYXRvcnMoYWlkLHJlc3VsdHNbaV0sdHJ1ZSkpOwp9CmFzeW5jIGZ1bmN0aW9uIHJlbG9hZEluZCh0aWNrZXIpewogIGNvbnN0IGFpZD10aWNrZXIrJy1pbmQtYXJlYSc7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoYWlkKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjU4cmVtO3BhZGRpbmc6OXB4O2FuaW1hdGlvbjpwdWxzZSAxcyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2Pic7CiAgY29uc3QgbT17J3BldHI0JzonUEVUUjQuU0EnLCd2YWxlMyc6J1ZBTEUzLlNBJywnYmJhczMnOidCQkFTMy5TQScsJ2F4aWEzJzonQVhJQTMuU0EnLCdyb3hvMzQnOidST1hPMzQuU0EnfTsKICByZW5kZXJJbmRpY2F0b3JzKGFpZCxhd2FpdCBmZXRjaEluZGljYXRvcnMobVt0aWNrZXJdfHx0aWNrZXIudG9VcHBlckNhc2UoKSsnLlNBJyksdHJ1ZSk7Cn0KCi8vIENhbGVuZMOhcmlvCmNvbnN0IEZMQUdTPXsnVVNEJzon8J+HuvCfh7gnLCdCUkwnOifwn4en8J+HtycsJ0VVUic6J/Cfh6rwn4e6JywnR0JQJzon8J+HrPCfh6cnLCdDTlknOifwn4eo8J+HsycsJ0pQWSc6J/Cfh6/wn4e1JywnQ0FEJzon8J+HqPCfh6YnLCdBVUQnOifwn4em8J+HuicsJ0RFJzon8J+HqfCfh6onfTsKYXN5bmMgZnVuY3Rpb24gbG9hZENhbGVuZGFyKCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbGVuZGFyLWFyZWEnKTtjb25zdCBzdD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FsLXN0YXR1cycpOwogIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNThyZW07cGFkZGluZzoxOHB4O3RleHQtYWxpZ246Y2VudGVyO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+JzsKICBpZihzdClzdC50ZXh0Q29udGVudD0nQnVzY2FuZG8gZXZlbnRvcy4uLic7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDIwMDAwKTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2NhbGVuZGFyJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7CiAgICBpZighci5vayl0aHJvdyBuZXcgRXJyb3IoJ0hUVFAgJytyLnN0YXR1cyk7CiAgICBjb25zdCBldmVudHM9YXdhaXQgci5qc29uKCk7CiAgICBpZihzdClzdC50ZXh0Q29udGVudD1ldmVudHMubGVuZ3RoPjA/ZXZlbnRzLmxlbmd0aCsnIGV2ZW50b3MgwrcgZXN0YSBzZW1hbmEgZSBwcsOzeGltYSc6J1NlbSBldmVudG9zJzsKICAgIGlmKCFldmVudHN8fCFldmVudHMubGVuZ3RoKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9InBhZGRpbmc6MThweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOi42cmVtIj5TZW0gZXZlbnRvcyBkaXNwb27DrXZlaXM8L2Rpdj4nO3JldHVybjt9CiAgICBjb25zdCBieURhdGU9e307ZXZlbnRzLmZvckVhY2goZT0+e2NvbnN0IGR0PShlLmRhdGV8fCcnKS5zbGljZSgwLDEwKTtpZighYnlEYXRlW2R0XSlieURhdGVbZHRdPVtdO2J5RGF0ZVtkdF0ucHVzaChlKTt9KTsKICAgIGxldCBodG1sPScnOwogICAgT2JqZWN0LmtleXMoYnlEYXRlKS5zb3J0KCkuZm9yRWFjaChkdD0+ewogICAgICBjb25zdCBkPW5ldyBEYXRlKGR0KydUMTI6MDA6MDAnKTsKICAgICAgY29uc3QgbGJsPWQudG9Mb2NhbGVEYXRlU3RyaW5nKCdwdC1CUicse3dlZWtkYXk6J2xvbmcnLGRheTonMi1kaWdpdCcsbW9udGg6J3Nob3J0J30pOwogICAgICBodG1sKz0nPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYWNjIj7wn5OFPC9zcGFuPiAnK2xibCsnPC9kaXY+JysKICAgICAgICAnPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjhweCI+JysKICAgICAgICAnPGRpdiBjbGFzcz0iY2FsLWRheS1oZHIiPjxzcGFuPlBhw61zPC9zcGFuPjxzcGFuPkhvcmE8L3NwYW4+PHNwYW4+RXZlbnRvPC9zcGFuPjxzcGFuPkltcDwvc3Bhbj48c3Bhbj5SZWFsaXphZG88L3NwYW4+PHNwYW4+UHJldmlzdG88L3NwYW4+PC9kaXY+JzsKICAgICAgYnlEYXRlW2R0XS5mb3JFYWNoKGU9PnsKICAgICAgICBjb25zdCBmbGFnPWUuZmxhZ3x8RkxBR1NbZS5jb3VudHJ5XXx8J/CfjJAnOwogICAgICAgIGNvbnN0IGltcD1lLmltcG9ydGFuY2V8fDE7CiAgICAgICAgY29uc3QgaWM9aW1wPj0zPyd2YXIoLS1yZWQpJzppbXA+PTI/J3ZhcigtLXdhcm4pJzondmFyKC0tbXV0ZWQpJzsKICAgICAgICBjb25zdCBhYz1lLnNpZ25hbD09PSdiZWF0Jz8ndmFyKC0tZ3JlZW4pJzplLnNpZ25hbD09PSdtaXNzJz8ndmFyKC0tcmVkKSc6J3ZhcigtLXRleHQpJzsKICAgICAgICBodG1sKz0nPGRpdiBjbGFzcz0iY2FsLXJvdyI+JysKICAgICAgICAgICc8c3Bhbj4nK2ZsYWcrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIGNsYXNzPSJjYWwtdGltZSI+JysoZS50aW1lfHwn4oCUJykrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIGNsYXNzPSJjYWwtbmFtZSIgdGl0bGU9IicrKGUuZXZlbnR8fCcnKSsnIj4nKyhlLmV2ZW50fHwnJykrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIHN0eWxlPSJ0ZXh0LWFsaWduOmNlbnRlcjtjb2xvcjonK2ljKyciPicrJ+KXjycucmVwZWF0KE1hdGgubWluKGltcCwzKSkrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIGNsYXNzPSJjYWwtYWN0dWFsIiBzdHlsZT0iY29sb3I6JythYysnIj4nKyhlLmFjdHVhbHx8J+KAlCcpKyc8L3NwYW4+JysKICAgICAgICAgICc8c3BhbiBjbGFzcz0iY2FsLWZjIj4nKyhlLmZvcmVjYXN0fHwn4oCUJykrJzwvc3Bhbj4nKwogICAgICAgICAgJzwvZGl2Pic7CiAgICAgIH0pOwogICAgICBodG1sKz0nPC9kaXY+JzsKICAgIH0pOwogICAgZWwuaW5uZXJIVE1MPWh0bWw7CiAgfWNhdGNoKGUpewogICAgaWYoc3Qpc3QudGV4dENvbnRlbnQ9J0Vycm8nOwogICAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1yZWQpO3BhZGRpbmc6MThweDtmb250LXNpemU6LjZyZW07dGV4dC1hbGlnbjpjZW50ZXIiPicrKChlLm5hbWU9PT0nQWJvcnRFcnJvcicpPydUaW1lb3V0IOKAlCB0ZW50ZSBub3ZhbWVudGUnOidFcnJvIGFvIGNhcnJlZ2FyIGNhbGVuZMOhcmlvJykrJzwvZGl2Pic7CiAgfQp9Cgphc3luYyBmdW5jdGlvbiBmZXRjaEFsbCgpewogIHRyeXsKICAgIGNvbnN0Wyx0dixmdXR1cmVzXT1hd2FpdCBQcm9taXNlLmFsbChbZmV0Y2hITCgpLGZldGNoVFYoKSxmZXRjaEZ1dHVyZXMoKV0pOwogICAgY29uc3Qgbm93PW5ldyBEYXRlKCkudG9Mb2NhbGVUaW1lU3RyaW5nKCdwdC1CUicpOwogICAgc2V0RWwoJ2xhc3QtdXBkYXRlJywn4oa7ICcrbm93KTtzZXRFbCgnZm9vdGVyLXRpbWUnLG5vdyk7CiAgICBkb01hY3JvKHR2LGZ1dHVyZXMpO2RvUG9zaXRpb25zKHR2KTsKICAgIHNldFRpbWVvdXQoZmV0Y2hGdW5kaW5nLDMwMDApOwogICAgc2V0VGltZW91dChhc3luYygpPT57dHJ5e2NvbnN0W2IsY3ljXT1hd2FpdCBQcm9taXNlLmFsbChbZmV0Y2hCVENJbmRpY2F0b3JzKCksZmV0Y2hCVENDeWNsZSgpXSk7aWYoYilyZW5kZXJCVENJbmRpY2F0b3JzKGIpO2lmKGN5YylyZW5kZXJCVENDeWNsZShjeWMpO2ZldGNoRmVhckdyZWVkKCk7fWNhdGNoKGUpe319LDUwMDApOwogICAgY29uc3QgaG9qZT1uZXcgRGF0ZSgpOwogICAgY29uc3QgZGlhc1BUPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNi0xMi0xNycpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkaWFzVkw9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI3LTAyLTE4JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRpYXNBMz1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDktMTQnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZGlhc0EzYj1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMTAtMDInKS1ob2plKS84NjRlNSkpOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DRm9yQXRpdm8oJ1BFVFI0LlNBJywzMC44NSxkaWFzUFQsJ21jLXB0LWxvYWRpbmcnLCdtYy1wdC1yZXN1bHQnLCdtYy1wdC1zdHJpa2UnLCdtYy1wdC12b2wnLCdtYy1wdC1pbmZvJywnbWMtcHQtcnQnKTt9LDYwMDApOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DRm9yQXRpdm8oJ1ZBTEUzLlNBJyw1Ny40MCxkaWFzVkwsJ21jLXZsLWxvYWRpbmcnLCdtYy12bC1yZXN1bHQnLCdtYy12bC1zdHJpa2UnLCdtYy12bC12b2wnLCdtYy12bC1pbmZvJywnbWMtdmwtcnQnKTt9LDEyMDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0JhcnJpZXIoJ0FYSUEzLlNBJyw1NC4zMSw0My41MSw2OC43NixkaWFzQTMsMCwnYXhpYTMnKTt9LDE4MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0JhcnJpZXIoJ0FYSUEzLlNBJyw1MC42NSw0MC41Miw2Mi44MSxkaWFzQTNiLDAsJ2F4aWEzYicpO30sMjQwMDApOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DUHJlZml4YWRvKCdST1hPMzQuU0EnLDEyLjg4LDEwLjUwLDMyLDApO30sMzAwMDApOwogICAgd2luZG93Ll9pbmRMb2FkZWQ9ZmFsc2U7CiAgfWNhdGNoKGUpe2NvbnNvbGUuZXJyb3IoJ2ZldGNoQWxsOicsZSk7fQp9CmZldGNoQWxsKCk7CnNldEludGVydmFsKGZldGNoQWxsLDEyMDAwMCk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4=").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
