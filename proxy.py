"""  # v8.6
Trader Desk — Proxy Server v8.6
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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjQgLS0+CjxodG1sIGxhbmc9InB0LUJSIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5UcmFkZXIgRGVzazwvdGl0bGU+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDMwMDs0MDA7NjAwOzcwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KLyog4pSA4pSAIFJFU0VUICYgUk9PVCDilIDilIAgKi8KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQo6cm9vdHsKICAtLWJnOiMwZDBkMGQ7LS1iZzI6IzE0MTQxNDstLWJnMzojMWExYTFhOwogIC0tdGV4dDojZTJlMmUyOy0tbXV0ZWQ6IzU1NTstLWJvcmRlcjojMjIyOwogIC0tYWNjZW50OiNmMGE1MDA7LS1ncmVlbjojMDBjODUzOy0tcmVkOiNmZjE3NDQ7CiAgLS13YXJuOiNmZjk4MDA7LS1ibHVlOiMyMTk2ZjM7LS1pdG06I2ZmNDQ0NAp9CmJvZHl7CiAgYmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdGV4dCk7CiAgZm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTsKICBmb250LXNpemU6MTNweDtsaW5lLWhlaWdodDoxLjU7CiAgcGFkZGluZzoxNHB4O21heC13aWR0aDo2NjBweDttYXJnaW46MCBhdXRvCn0KCi8qIOKUgOKUgCBIRUFERVIg4pSA4pSAICovCi5oZHJ7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjE0cHg7cGFkZGluZy1ib3R0b206MTBweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpfQouaGRyLXRpdGxle2ZvbnQtc2l6ZToxNnB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO2xldHRlci1zcGFjaW5nOjFweH0KLmhkci10aW1le2ZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKX0KCi8qIOKUgOKUgCBUQUJTIOKUgOKUgCAqLwoudGFic3tkaXNwbGF5OmZsZXg7Z2FwOjRweDttYXJnaW4tYm90dG9tOjE0cHg7b3ZlcmZsb3cteDphdXRvO3BhZGRpbmctYm90dG9tOjJweH0KLnRhYntwYWRkaW5nOjZweCAxNHB4O2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y3Vyc29yOnBvaW50ZXI7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MXB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7d2hpdGUtc3BhY2U6bm93cmFwO3RyYW5zaXRpb246YWxsIC4xNXM7Zm9udC1mYW1pbHk6aW5oZXJpdH0KLnRhYjpob3Zlcntjb2xvcjp2YXIoLS10ZXh0KTtib3JkZXItY29sb3I6IzMzM30KLnRhYi5hY3RpdmV7YmFja2dyb3VuZDp2YXIoLS1hY2NlbnQpO2NvbG9yOiMwMDA7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Zm9udC13ZWlnaHQ6NzAwfQoudGFiLWNvbnRlbnR7ZGlzcGxheTpub25lfS50YWItY29udGVudC5hY3RpdmV7ZGlzcGxheTpibG9ja30KCi8qIOKUgOKUgCBTRUNUSU9OIEhFQURFUiDilIDilIAgKi8KLnNlY3tmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEwcHggMCA1cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjhweDtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHh9Ci5zZWMgLmFjY3tjb2xvcjp2YXIoLS1hY2NlbnQpfQouc3Jje2NvbG9yOiMyODI4Mjg7Zm9udC1zaXplOjlweH0KCi8qIOKUgOKUgCBHUklEIENBUkRTIOKUgOKUgCAqLwouZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEycHh9Ci5jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4IDlweH0KLmNhcmQuZ3tib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1ncmVlbil9Ci5jYXJkLmJ7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tYmx1ZSl9Ci5jYXJkLnd7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0td2Fybil9Ci5jYXJkLnJ7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tcmVkKX0KLmMtbGJse2ZvbnQtc2l6ZTo5cHg7Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzoxcHg7bWFyZ2luLWJvdHRvbToycHh9Ci5jLW5te2ZvbnQtc2l6ZToxMXB4O2ZvbnQtd2VpZ2h0OjcwMDttYXJnaW4tYm90dG9tOjRweH0KLmMtcHJ7Zm9udC1zaXplOjE1cHg7Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLWFjY2VudCl9Ci5jLXByLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjRzIGluZmluaXRlO2ZvbnQtc2l6ZToxMXB4fQouYy1jaHtmb250LXNpemU6MTBweDttYXJnaW4tdG9wOjJweH0KLmNoZy11cHtjb2xvcjp2YXIoLS1ncmVlbil9LmNoZy1kbntjb2xvcjp2YXIoLS1yZWQpfS5jaGctZmx7Y29sb3I6dmFyKC0tbXV0ZWQpfQpAa2V5ZnJhbWVzIHB1bHNlezAlLDEwMCV7b3BhY2l0eToxfTUwJXtvcGFjaXR5Oi4zfX0KCi8qIOKUgOKUgCBTRUNUT1IgQUNDT1JESU9OIOKUgOKUgCAqLwoucy1oZHJ7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjhweCAxMnB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MXB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHg7dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1c30KLnMtaGRyOmhvdmVye2JvcmRlci1jb2xvcjojMzMzO2NvbG9yOnZhcigtLXRleHQpfQoucy1ib2R5e2Rpc3BsYXk6bm9uZTtwYWRkaW5nLXRvcDo0cHh9CgovKiDilIDilIAgUE9TSVRJT04gQ0FSRFMg4pSA4pSAICovCi5wb3MtY2FyZHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JvcmRlci1sZWZ0OjNweCBzb2xpZCB2YXIoLS1hY2NlbnQpO3BhZGRpbmc6MTNweDttYXJnaW4tYm90dG9tOjhweH0KLnBvcy1sYmx7Zm9udC1zaXplOjlweDtjb2xvcjp2YXIoLS1tdXRlZCk7bGV0dGVyLXNwYWNpbmc6MXB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjRweH0KLnBvcy10a3tmb250LXNpemU6MThweDtmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0tYWNjZW50KTttYXJnaW4tYm90dG9tOjNweH0KLnBvcy1wcntmb250LXNpemU6MjJweDtmb250LXdlaWdodDo3MDB9Ci5wb3MtcHIubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNHMgaW5maW5pdGU7Zm9udC1zaXplOjE2cHh9Ci5wb3MtY2hne2ZvbnQtc2l6ZToxMXB4O21hcmdpbi1ib3R0b206OXB4fQouc2J7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nLXRvcDo4cHg7bWFyZ2luLXRvcDo4cHh9Ci5zYi1yb3d7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtwYWRkaW5nOjRweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOjExcHh9Ci5zYi1sYmx7Y29sb3I6dmFyKC0tbXV0ZWQpfS5zYi12YWx7dGV4dC1hbGlnbjpyaWdodDttYXgtd2lkdGg6NjAlfQouc2ItdmFsLm9re2NvbG9yOnZhcigtLWdyZWVuKX0uc2ItdmFsLndhcm57Y29sb3I6dmFyKC0td2Fybil9LnNiLXZhbC5pdG17Y29sb3I6dmFyKC0taXRtKX0KLnNpZ25hbHtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4O21hcmdpbi10b3A6OHB4O2JhY2tncm91bmQ6dmFyKC0tYmcpfQouc2lnLXR0bHtmb250LXNpemU6OXB4O2xldHRlci1zcGFjaW5nOjFweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bWFyZ2luLWJvdHRvbTo2cHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQouaW5kLWJveHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6OHB4O3RleHQtYWxpZ246Y2VudGVyfQouaW5kLWxibHtmb250LXNpemU6OXB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjRweH0KLmluZC12YWx7Zm9udC1zaXplOjE2cHg7Zm9udC13ZWlnaHQ6ODAwfQouaW5kLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LmluZC12YWwud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaW5kLXZhbC5kb3due2NvbG9yOnZhcigtLXJlZCl9CgovKiDilIDilIAgU0NPUkUgQk9YIOKUgOKUgCAqLwouc2NvcmUtYm94e2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmciAxZnI7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEwcHh9Ci5zY29yZS1jZWxse2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4IDhweDt0ZXh0LWFsaWduOmNlbnRlcn0KLnNjb3JlLW1ldGF7Zm9udC1zaXplOjlweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjRweH0KLnNjb3JlLW51bXtmb250LXNpemU6MjhweDtmb250LXdlaWdodDo4MDA7bGluZS1oZWlnaHQ6MX0KLnNjb3JlLWxibHtmb250LXNpemU6MTBweDttYXJnaW4tdG9wOjNweH0KLnNjb3JlLXZhbHtmb250LXNpemU6MTVweDtmb250LXdlaWdodDo3MDA7bWFyZ2luLXRvcDozcHh9Ci5zY29yZS1zdWJ7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6MnB4fQoKLyog4pSA4pSAIElORElDQVRPUiBST1cg4pSA4pSAICovCi5pbmQtcm93e2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQ6MnB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo3cHggMTBweDttYXJnaW4tYm90dG9tOjNweDt0cmFuc2l0aW9uOmJvcmRlci1sZWZ0LWNvbG9yIC4xc30KLmluZC1yb3c6aG92ZXJ7Ym9yZGVyLWxlZnQtY29sb3I6dmFyKC0tYWNjZW50KX0KLmluZC1yb3ctdG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpiYXNlbGluZTttYXJnaW4tYm90dG9tOjJweH0KLmluZC1yb3ctbm9tZXtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweH0KLmluZC1yb3ctdmFse2ZvbnQtc2l6ZToxM3B4O2ZvbnQtd2VpZ2h0OjcwMH0KLmluZC1yb3ctdmFsLm9re2NvbG9yOnZhcigtLWdyZWVuKX0uaW5kLXJvdy12YWwuZG93bntjb2xvcjp2YXIoLS1yZWQpfS5pbmQtcm93LXZhbC53YXJue2NvbG9yOnZhcigtLXdhcm4pfQouaW5kLXJvdy1leHB7Zm9udC1zaXplOjEwcHg7Y29sb3I6IzQ0NDtsaW5lLWhlaWdodDoxLjR9CgovKiDilIDilIAgQ0FMRU5EQVIg4pSA4pSAICovCi5jYWwtaGRye2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MjJweCA0NHB4IDFmciAyOHB4IDYwcHggNTRweDtnYXA6NHB4O3BhZGRpbmc6NHB4IDEwcHg7Zm9udC1zaXplOjlweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOjFweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2JhY2tncm91bmQ6dmFyKC0tYmcpfQouY2FsLXJvd3tkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjIycHggNDRweCAxZnIgMjhweCA2MHB4IDU0cHg7Z2FwOjRweDthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzo2cHggMTBweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2ZvbnQtc2l6ZToxMXB4fQouY2FsLXJvdzpsYXN0LWNoaWxke2JvcmRlci1ib3R0b206bm9uZX0KLmNhbC10aW1le2NvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTBweH0KLmNhbC1uYW1le292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcH0KLmNhbC1hY3R1YWx7dGV4dC1hbGlnbjpyaWdodDtmb250LXdlaWdodDo3MDB9Ci5jYWwtZmN7dGV4dC1hbGlnbjpyaWdodDtjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjEwcHh9Cgpmb290ZXJ7bWFyZ2luLXRvcDoxOHB4O3BhZGRpbmctdG9wOjEwcHg7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQo8L3N0eWxlPgo8L2hlYWQ+Cjxib2R5PgoKPGRpdiBjbGFzcz0iaGRyIj4KICA8ZGl2IGNsYXNzPSJoZHItdGl0bGUiPuKWuCBUUkFERVIgREVTSzwvZGl2PgogIDxkaXYgY2xhc3M9Imhkci10aW1lIiBpZD0ibGFzdC11cGRhdGUiPuKAlDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9InRhYnMiPgogIDxkaXYgY2xhc3M9InRhYiBhY3RpdmUiIG9uY2xpY2s9InN3aXRjaFRhYignY290YWNvZXMnLHRoaXMpIj7wn5OKIENvdGHDp8O1ZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3aXRjaFRhYignaW5kaWNhZG9yZXMnLHRoaXMpIj7wn5OIIEluZGljYWRvcmVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ3Bvc2ljb2VzJyx0aGlzKSI+8J+SvCBQb3Npw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ2NhbGVuZGFyaW8nLHRoaXMpIj7wn5OFIENhbGVuZMOhcmlvPC9kaXY+CjwvZGl2PgoKPCEtLSDilZDilZAgQ09UQcOHw5VFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1jb3RhY29lcyIgY2xhc3M9InRhYi1jb250ZW50IGFjdGl2ZSI+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYWNjIj4wMTwvc3Bhbj4gRVVBIDxzcGFuIGNsYXNzPSJzcmMiPsK3IHByb3h5PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjLWxibCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+UyZQIEVTMSo8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJlc2YtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImVzZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iYy1sYmwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPk5hc2RhcSBOUTwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoIiBpZD0ibnFmLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBiIj48ZGl2IGNsYXNzPSJjLWxibCI+w41uZGljZTwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkRvdyBKb25lczwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImRqaS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoIiBpZD0iZGppLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCByIj48ZGl2IGNsYXNzPSJjLWxibCI+Vm9sYXRpbGlkYWRlPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+VklYPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJ2aXgtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImMtbGJsIj5Ew7NsYXIgSW5kZXg8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5EWFk8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJkeHktcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImR4eS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkPDom1iaW88L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5VU0QvQlJMPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0idXNkLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJ1c2QtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImFjYyI+MDI8L3NwYW4+IEIzIFRvcCAxMCA8c3BhbiBjbGFzcz0ic3JjIj7CtyBUcmFkaW5nVmlldzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPsONbmRpY2U8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5JQk9WPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iaWJvdi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoIiBpZD0iaWJvdi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPldJTjEhPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0id2luLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJ3aW4tYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImMtbGJsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPlBFVFI0PC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0icGV0cjRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJwZXRyNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImMtbGJsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPklUVUI0PC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iaXR1YjRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJpdHViNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImMtbGJsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPlZBTEUzPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0idmFsZTNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJ2YWxlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImMtbGJsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkJCREM0PC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iYmJkYzRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJiYmRjNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImMtbGJsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkFCRVYzPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iYWJldjNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJhYmV2M3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImMtbGJsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkJCQVMzPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iYmJhczNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJiYmFzM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGciPjxkaXYgY2xhc3M9ImMtbGJsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPldFR0UzPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0id2VnZTNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJ3ZWdlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHciPjxkaXYgY2xhc3M9ImMtbGJsIj5CRFI8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5ST1hPMzQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJyb3hvMzRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJyb3hvMzRxLWMiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgoKICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4I8L3NwYW4+IEIzIHBvciBTZWdtZW50byA8c3BhbiBjbGFzcz0ic3JjIj7CtyBjbGlxdWUgcGFyYSBleHBhbmRpcjwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdmaW5hbmNlaXJvJykiPjxzcGFuPvCfj6YgRmluYW5jZWlybzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1maW5hbmNlaXJvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktZmluYW5jZWlybyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWZpbmFuY2Vpcm8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3BldHJvbGVvJykiPjxzcGFuPvCfm6IgUGV0csOzbGVvICZhbXA7IEfDoXM8L3NwYW4+PHNwYW4gaWQ9InNhcnItcGV0cm9sZW8iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWJvZHkiIGlkPSJzYm9keS1wZXRyb2xlbyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLXBldHJvbGVvIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdtaW5lcmFjYW8nKSI+PHNwYW4+4puPIE1pbmVyYcOnw6NvPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1pbmVyYWNhbyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LW1pbmVyYWNhbyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLW1pbmVyYWNhbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWF0ZXJpYWlzJykiPjxzcGFuPvCfjLIgUGFwZWwgJmFtcDsgQ2VsdWxvc2U8L3NwYW4+PHNwYW4gaWQ9InNhcnItbWF0ZXJpYWlzIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktbWF0ZXJpYWlzIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbWF0ZXJpYWlzIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCd1dGlsaWRhZGUnKSI+PHNwYW4+4pqhIFV0aWxpZGFkZSBQw7pibGljYTwvc3Bhbj48c3BhbiBpZD0ic2Fyci11dGlsaWRhZGUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWJvZHkiIGlkPSJzYm9keS11dGlsaWRhZGUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC11dGlsaWRhZGUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ2NvbnN1bW9fYycpIj48c3Bhbj7wn5uNIENvbnN1bW8gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9InNhcnItY29uc3Vtb19jIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktY29uc3Vtb19jIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtY29uc3Vtb19jIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdjb25zdW1vX24nKSI+PHNwYW4+8J+bkiBDb25zdW1vIE7Do28gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9InNhcnItY29uc3Vtb19uIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktY29uc3Vtb19uIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtY29uc3Vtb19uIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdzYXVkZScpIj48c3Bhbj7wn4+lIFNhw7pkZTwvc3Bhbj48c3BhbiBpZD0ic2Fyci1zYXVkZSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LXNhdWRlIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtc2F1ZGUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ2luZHVzdHJpYWlzJykiPjxzcGFuPvCfj5cgQmVucyBJbmR1c3RyaWFpczwvc3Bhbj48c3BhbiBpZD0ic2Fyci1pbmR1c3RyaWFpcyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LWluZHVzdHJpYWlzIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtaW5kdXN0cmlhaXMiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3RpX3RlbGVjb20nKSI+PHNwYW4+8J+SuyBUSSAmYW1wOyBDb211bmljYcOnw7Vlczwvc3Bhbj48c3BhbiBpZD0ic2Fyci10aV90ZWxlY29tIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktdGlfdGVsZWNvbSI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLXRpX3RlbGVjb20iPjwvZGl2PjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuIGNsYXNzPSJhY2MiPvCfh7rwn4e4PC9zcGFuPiBFVUEgcG9yIFNlZ21lbnRvPC9kaXY+CiAgPGRpdiBjbGFzcz0icy1oZHIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWFnNycpIj48c3Bhbj7irZAgNyBNYWduw61maWNhczwvc3Bhbj48c3BhbiBpZD0ic2Fyci1tYWc3Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0icy1ib2R5IiBpZD0ic2JvZHktbWFnNyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLW1hZzciPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ25hc2RhcTE1JykiPjxzcGFuPvCfkrsgTmFzZGFxIFRvcCAxNTwvc3Bhbj48c3BhbiBpZD0ic2Fyci1uYXNkYXExNSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LW5hc2RhcTE1Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbmFzZGFxMTUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InMtaGRyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3NwMjAnKSI+PHNwYW4+8J+TiiBTJmFtcDtQIDUwMCBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9InNhcnItc3AyMCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InMtYm9keSIgaWQ9InNib2R5LXNwMjAiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1zcDIwIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWhkciIgb25jbGljaz0idG9nZ2xlU2VnKCdkamkyMCcpIj48c3Bhbj7wn4+bIERvdyBKb25lcyBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9InNhcnItZGppMjAiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzLWJvZHkiIGlkPSJzYm9keS1kamkyMCI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWRqaTIwIj48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3BhbiBjbGFzcz0iYWNjIj4wMzwvc3Bhbj4gQ29tbW9kaXRpZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgdyI+PGRpdiBjbGFzcz0iYy1sYmwiPlBldHLDs2xlbzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPldUSS9DTDwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImNsLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3Ij48ZGl2IGNsYXNzPSJjLWxibCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5HT0xEPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iZ29sZC1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgdyI+PGRpdiBjbGFzcz0iYy1sYmwiPk1ldGFsPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+U0lMVkVSPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0ic2lsdmVyLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3Ij48ZGl2IGNsYXNzPSJjLWxibCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5DT1BQRVI8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJjb3BwZXItcCI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4gY2xhc3M9ImFjYyI+MDQ8L3NwYW4+IEJpdGNvaW48L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iYy1sYmwiPlNwb3Q8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5CVEMvVVNEPC9kaXY+PGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iYnRjLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2giIGlkPSJidGMtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImMtbGJsIj5SU0kgU2VtYW5hbDwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPkJUQyBSU0k8L2Rpdj48ZGl2IGNsYXNzPSJjLXByIGxvYWRpbmciIGlkPSJidGMtcnNpIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iYy1sYmwiPkZ1bmRpbmcgOGg8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5CVEMgUmF0ZTwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImJ0Yy1mdW5kIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYiI+PGRpdiBjbGFzcz0iYy1sYmwiPkZlYXIgJmFtcDsgR3JlZWQ8L2Rpdj48ZGl2IGNsYXNzPSJjLW5tIj5JbmRleDwvZGl2PjxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImZnLXZhbCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaCIgaWQ9ImZnLWxibCI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGZvb3Rlcj48c3BhbiBpZD0iZm9vdGVyLXRpbWUiPuKAlDwvc3Bhbj48c3Bhbj5UcmFkZXIgRGVzayB2MTAuNDwvc3Bhbj48L2Zvb3Rlcj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBJTkRJQ0FET1JFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1pbmRpY2Fkb3JlcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4o8L3NwYW4+IENpY2xvIEJpdGNvaW48L2Rpdj4KICA8ZGl2IGlkPSJidGMtY3ljbGUtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MTJweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kbyBjaWNsbyBCVEMuLi48L2Rpdj48L2Rpdj4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxMzBweDtnYXA6OHB4O21hcmdpbjoxMHB4IDAiPgogICAgPGRpdiBpZD0iZmVhci1ncmVlZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjExcHg7cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvIEZlYXIgJmFtcDsgR3JlZWQuLi48L2Rpdj48L2Rpdj4KICAgIDxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMnB4O3RleHQtYWxpZ246Y2VudGVyIj4KICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206NXB4Ij5CVEMvVVNEPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImMtcHIgbG9hZGluZyIgaWQ9ImJ0Yy1pbmQtcHJpY2UiPuKAlDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBJbmRpY2Fkb3JlcyBCVEMgU2VtYW5hbDwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4o8L3NwYW4+IFBFVFI0IDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxMHB4O21hcmdpbi1sZWZ0OjhweCIgb25jbGljaz0icmVsb2FkSW5kKCdwZXRyNCcpIj7ihrsgcmVjYXJyZWdhcjwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJwZXRyNC1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCI+PHNwYW4gY2xhc3M9ImFjYyI+8J+Tijwvc3Bhbj4gVkFMRTMgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOjEwcHg7bWFyZ2luLWxlZnQ6OHB4IiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3ZhbGUzJykiPuKGuyByZWNhcnJlZ2FyPC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InZhbGUzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjExcHg7cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OKPC9zcGFuPiBCQkFTMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6MTBweDttYXJnaW4tbGVmdDo4cHgiIG9uY2xpY2s9InJlbG9hZEluZCgnYmJhczMnKSI+4oa7IHJlY2FycmVnYXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0iYmJhczMtaW5kLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweDtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4o8L3NwYW4+IEFYSUEzIDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxMHB4O21hcmdpbi1sZWZ0OjhweCIgb25jbGljaz0icmVsb2FkSW5kKCdheGlhMycpIj7ihrsgcmVjYXJyZWdhcjwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJheGlhMy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCI+PHNwYW4gY2xhc3M9ImFjYyI+8J+Tijwvc3Bhbj4gUk9YTzM0IDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZToxMHB4O21hcmdpbi1sZWZ0OjhweCIgb25jbGljaz0icmVsb2FkSW5kKCdyb3hvMzQnKSI+4oa7IHJlY2FycmVnYXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0icm94bzM0LWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjExcHg7cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CjwvZGl2PgoKPCEtLSDilZDilZAgUE9TScOHw5VFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1wb3NpY29lcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJhY2MiPjAxPC9zcGFuPiBPcGVyYcOnw7VlcyBBdGl2YXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGJsIj5QZXRyb2JyYXMgUE4gwrcgQ2FsbCBWZW5kaWRhIMK3IFBFVFJMMzE5IMK3IFZlbmMgMTcvMTIvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXRrIj5QRVRSNDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXByIGxvYWRpbmciIGlkPSJwdC1wb3MtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icG9zLWNoZyIgaWQ9InB0LXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TdHJpa2UgZW50cmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCAzMCw4NTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TdHJpa2UgKFBFVFJMMzE5KTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDMwLDg1PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBhdHVhbCB2cyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBpdG0iIGlkPSJwdC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjE3LzEyLzIwMjYgwrcgPHNwYW4gaWQ9InB0LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+NDMsNCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gQiZhbXA7UyAodm9sLmltcGwuIOKAlCBleGVyY2VyKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjksNCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gTUMgKHZvbC5oaXN0LiDigJQgZXhlcmNlcik8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayIgaWQ9Im1jLXB0LXJ0Ij5jYWxjLi4uPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdHRsIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhbGwgc2VyIGV4ZXJjaWRhIG5vIHZlbmNpbWVudG88L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcHQtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweCI+Q2FsY3VsYW5kbyA1LjAwMCBjZW7DoXJpb3MuLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcHQtcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Qcm9iLiBleGVyY2VyIGNhbGw8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIiBpZD0ibWMtcHQtc3RyaWtlIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1wdC12b2wiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjVweDtsaW5lLWhlaWdodDoxLjUiIGlkPSJtYy1wdC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjhweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGJsIj5WYWxlIE9OIMK3IENhbGwgVmVuZGlkYSDCtyBWQUxFQjU3NCDCtyBWZW5jIDE4LzAyLzIwMjc8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10ayI+VkFMRTM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wciBsb2FkaW5nIiBpZD0idmwtcG9zLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBvcy1jaGciIGlkPSJ2bC1wb3MtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTcsNDA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlIChWQUxFQjU3NCk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA1Nyw0MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gYXR1YWwgdnMgc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0idmwtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xOC8wMi8yMDI3IMK3IDxzcGFuIGlkPSJ2bC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjcxLDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIEImYW1wO1MgKHZvbC5pbXBsLiDigJQgZXhlcmNlcik8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4xNCwyJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Qcm9iLiBNQyAodm9sLmhpc3QuIOKAlCBleGVyY2VyKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIiBpZD0ibWMtdmwtcnQiPmNhbGMuLi48L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10dGwiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FsbCBzZXIgZXhlcmNpZGEgbm8gdmVuY2ltZW50bzwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy12bC1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4Ij5DYWxjdWxhbmRvIDUuMDAwIGNlbsOhcmlvcy4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy12bC1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlByb2IuIGV4ZXJjZXIgY2FsbDwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwiIGlkPSJtYy12bC1zdHJpa2UiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLXZsLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NXB4O2xpbmUtaGVpZ2h0OjEuNSIgaWQ9Im1jLXZsLWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgoKICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6OHB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy1sYmwiPkFYSUEzIChBKSDCtyBCaWRpcmVjaW9uYWwgwrcgVmVuYyAxNC8wOS8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGsiPkFYSUEzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHIgbG9hZGluZyIgaWQ9ImF4aWEzLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0iYXhpYTMtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyByZWYuIGVudHJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTQsMzE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDQzLDUxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktVTyAoKzI2LDYlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDY4LDc2PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBjLyBiYXIuIGFsdGEgS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+KzQlIGZpeG88L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNC8wOS8yMDI2IMK3IDxzcGFuIGlkPSJheGlhM2YtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMta2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzLWt1by1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMtc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10dGwiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgQ2Vuw6FyaW9zIGRlIGJhcnJlaXJhPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjExcHgiPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtYXhpYTMtcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLWF4aWEzLW5vYnIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBBbHRhIEtVTzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLWF4aWEzLWt1byI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5CYXIuIEJhaXhhIEtETzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgZG93biIgaWQ9Im1jLWF4aWEzLWtkbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTMtdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo1cHgiIGlkPSJtYy1heGlhMy1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjhweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGJsIj5BWElBMyAoQikgwrcgQmlkaXJlY2lvbmFsIElPTiBJdGHDuiDCtyBWZW5jIDAyLzEwLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10ayI+QVhJQTM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wciBsb2FkaW5nIiBpZD0iYXhpYTNiLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0iYXhpYTNiLXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gcmVmLiBlbnRyYWRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDUwLDY1PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktETyAoLTIwJSk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA0MCw1Mjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5LVU8gKCsyNCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgNjIsODE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+R2FuaG8gcy8gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+YXTDqSArMzEsMiUgLyArMjAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIGMvIGJhci4gYWx0YSBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4rNCUgZml4byAoMTIsMzMlIGEuYS4pPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MDIvMTAvMjAyNiDCtyA8c3BhbiBpZD0iYXhpYTNiLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzYi1rZG8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtVTzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTNiLWt1by1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTNiLXN0YXR1cyI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdHRsIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvcyBkZSBiYXJyZWlyYTwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhM2ItbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweCI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhM2ItcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLWF4aWEzYi1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhM2Ita3VvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBkb3duIiBpZD0ibWMtYXhpYTNiLWtkbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTNiLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NXB4IiBpZD0ibWMtYXhpYTNiLWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgoKICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6OHB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy1sYmwiPlJPWE8zNCDCtyBCRFIgTnViYW5rIMK3IFByZWZpeGFkbyBjLyBCYXJyZWlyYSDCtyBWZW5jIDE2LzA3LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10ayI+Uk9YTzM0PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHIgbG9hZGluZyIgaWQ9InJveG8zNC1wb3MtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icG9zLWNoZyIgaWQ9InJveG8zNC1wb3MtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJlw6dvIHJlZi4gZW50cmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCAxMiw4ODwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5CYXJyZWlyYSBST1hPRzEwNTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDEwLDUwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MTYvMDcvMjAyNiDCtyA8c3BhbiBpZD0icm94bzM0LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0icm94bzM0LWtkby1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0icm94bzM0LXN0YXR1cyI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdHRsIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIHN1Y2Vzc28gKG7Do28gdG9jYXIgYmFycmVpcmEpPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXJveG8zNC1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4Ij5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXJveG8zNC1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlByb2IuIFN1Y2Vzc288L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtcm94bzM0LXN1Y2Vzc28iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Q2FsbCBFeGVyY2lkYTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLXJveG8zNC1jYWxsIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPktETyBBdGluZ2lkbzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgZG93biIgaWQ9Im1jLXJveG8zNC1rZG8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLXJveG8zNC12b2wiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjVweCIgaWQ9Im1jLXJveG8zNC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3BhbiBjbGFzcz0iYWNjIj7wn5OBPC9zcGFuPiBFbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJvcGFjaXR5Oi41O2JvcmRlci1jb2xvcjojMWMxYzFjO21hcmdpbi10b3A6NXB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy10ayIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTRweCI+QkJBUzM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZSBCQkFTSDIxPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDIxLDY1IMK3IFJlZiBSJCAyMCw2Nzwvc3Bhbj48L2Rpdj48ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj7inIUgODAlIGRvIGFsdm8gZW0gNzAlIGRvIHByYXpvPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ib3BhY2l0eTouNTtib3JkZXItY29sb3I6IzFjMWMxYzttYXJnaW4tdG9wOjVweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGsiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjE0cHgiPkFYSUEzIFNob3J0IFN0cmFuZ2xlPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+PGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5DYWxsIFYuIEFYSUFJNTA1PC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDUwLDUwPC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSBBw6fDtWVzIGxpYmVyYWRhczwvc3Bhbj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im9wYWNpdHk6LjU7Ym9yZGVyLWNvbG9yOiMxYzFjMWM7bWFyZ2luLXRvcDo1cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLXRrIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxNHB4Ij5ST1hPMzQgUHJlZml4YWRvIDcsMSU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj48ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkVuY2VycmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4wNC8wNi8yMDI2PC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSB+NSwxNyUgKDcyJSBkbyBhbHZvKTwvc3Bhbj48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBDQUxFTkTDgVJJTyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1jYWxlbmRhcmlvIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxMHB4Ij4KICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKSI+8J+HuvCfh7gg8J+Hp/Cfh7cg8J+HqvCfh7og8J+HrPCfh6cg8J+HqPCfh7Mg8J+Hr/Cfh7Ug8J+HqfCfh6og8J+HqPCfh6YgwrcgSW1wYWN0byBNw6lkaW8rPC9kaXY+CiAgICA8YnV0dG9uIG9uY2xpY2s9ImxvYWRDYWxlbmRhcigpIiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYWNjZW50KTtjb2xvcjp2YXIoLS1hY2NlbnQpO3BhZGRpbmc6NXB4IDEycHg7Zm9udC1zaXplOjExcHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtsZXR0ZXItc3BhY2luZzoxcHgiPuKGuyBBdHVhbGl6YXI8L2J1dHRvbj4KICA8L2Rpdj4KICA8ZGl2IGlkPSJjYWwtc3RhdHVzIiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206NnB4O21pbi1oZWlnaHQ6MTRweCI+PC9kaXY+CiAgPGRpdiBpZD0iY2FsZW5kYXItYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlciI+Q2xpcXVlIGVtIEF0dWFsaXphciBwYXJhIGNhcnJlZ2FyIGV2ZW50b3M8L2Rpdj48L2Rpdj4KPC9kaXY+Cgo8c2NyaXB0Pgpjb25zdCBCQVNFPSdodHRwczovL3RyYWRlci1kZXNrLm9ucmVuZGVyLmNvbSc7CgovLyBUSUNLRVJTIEIzIOKAlCBjb3JyaWdpZG9zIChzZW0gdGlja2VycyBzZW0gbGlxdWlkZXogbm8gVFYpCmNvbnN0IFNFRz17CiAgJ2ZpbmFuY2Vpcm8nOiAgWydJVFVCNCcsJ0JCREM0JywnQkJBUzMnLCdTQU5CMTEnLCdCM1NBMycsJ0JQQUMxMScsJ0lUU0E0JywnQlJTUjYnLCdBQkNCNCcsJ0JNR0I0J10sCiAgJ3BldHJvbGVvJzogICAgWydQRVRSNCcsJ1BFVFIzJywnUFJJTzMnLCdCUkFWMycsJ1ZCQlIzJywnQ1NBTjMnLCdSRUNWMycsJ1VHUEEzJywnU0VRTDMnLCdFTkFUMyddLAogICdtaW5lcmFjYW8nOiAgIFsnVkFMRTMnLCdHR0JSNCcsJ0NTTkEzJywnVVNJTTUnLCdCUkFQNCcsJ0ZFU0E0JywnQ01JTjMnLCdDQkFWMycsJ0dPQVU0JywnUEdNTjMnXSwKICAnbWF0ZXJpYWlzJzogICBbJ1NVWkIzJywnS0xCTjExJywnRFhDTzMnLCdVTklQNicsJ1JBTkkzJywnT1JWUjMnLCdTTVRPMycsJ0ZSQVMzJywnTFBTQjMnLCdDU1VEMyddLAogICd1dGlsaWRhZGUnOiAgIFsnQVhJQTMnLCdFUVRMMycsJ0NQRkUzJywnU0JTUDMnLCdDTUlHNCcsJ0VOR0kxMScsJ1RBRUUxMScsJ0FVUkUzJywnRUdJRTMnLCdDUExFMyddLAogICdjb25zdW1vX2MnOiAgIFsnUkVOVDMnLCdMUkVOMycsJ01HTFUzJywnQ1lSRTMnLCdNUlZFMycsJ0FaWkEzJywnVklWQTMnLCdTQkZHMycsJ1lEVVEzJywnTU9WSTMnXSwKICAnY29uc3Vtb19uJzogICBbJ0FCRVYzJywnSkJTUzMnLCdCUkZTMycsJ05BVFUzJywnTURJQTMnLCdCRUVGMycsJ1NMQ0UzJywnTVRSRTMnLCdDQU1MMycsJ1BDQVIzJ10sCiAgJ3NhdWRlJzogICAgICAgWydSRE9SMycsJ0hBUFYzJywnRkxSWTMnLCdEQVNBMycsJ1FVQUwzJywnT05DTzMnLCdQTlZMMycsJ09EUFYzJywnTUFURDMnLCdBQUxSMyddLAogICdpbmR1c3RyaWFpcyc6IFsnV0VHRTMnLCdFTUJSMycsJ1JBSUwzJywnVEdNQTMnLCdST01JMycsJ1ZMSUQzJywnVFVQWTMnLCdJUkJSMycsJ1BPTU80JywnTEFWVjMnXSwKICAndGlfdGVsZWNvbSc6ICBbJ1ZJVlQzJywnVElNUzMnLCdUT1RWUzMnLCdTUUlBMycsJ01MQVMzJywnQU5JTTMnLCdQT1NJMycsJ0lOVEIzJywnTFdTQTMnLCdJRkNNMyddLAp9Owpjb25zdCBVU19TRUc9ewogICdtYWc3JzogICAgWydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnR09PR0wnLCdNRVRBJywnVFNMQSddLAogICduYXNkYXExNSc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdDT1NUJywnTkZMWCcsJ1FDT00nLCdBTUQnLCdBREJFJywnSU5UQycsJ0NTQ08nXSwKICAnc3AyMCc6ICAgIFsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQlJLLkInLCdKUE0nLCdMTFknLCdWJywnVU5IJywnWE9NJywnTUEnLCdORkxYJywnUEcnLCdKTkonLCdIRCcsJ0JBQyddLAogICdkamkyMCc6ICAgWydVTkgnLCdHUycsJ0hEJywnU0hXJywnQ0FUJywnQVhQJywnTUNEJywnQU1HTicsJ1YnLCdUUlYnLCdJQk0nLCdKUE0nLCdIT04nLCdDUk0nLCdDVlgnLCdBQVBMJywnTVNGVCcsJ0RJUycsJ05LRScsJ0JBJ10KfTsKCmNvbnN0IGZCUkw9dj0+diE9bnVsbD8nUiQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlVTRD12PT52IT1udWxsPydVUyQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlBUUz12PT52IT1udWxsP051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwoKZnVuY3Rpb24gc2V0RWwoaWQsdHh0KXtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47ZS50ZXh0Q29udGVudD10eHQ7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fQpmdW5jdGlvbiBzZXRDaGcoaWQsbm93LHByZXYsdHlwZSl7CiAgY29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuOwogIGNvbnN0IGRpZmY9bm93LXByZXY7Y29uc3QgcGN0PShkaWZmL01hdGguYWJzKHByZXZ8fDEpKjEwMCkudG9GaXhlZCgyKTtjb25zdCBzaWduPWRpZmY+PTA/JysnOicnOwogIGlmKHR5cGU9PT0nYnJsJyllLnRleHRDb250ZW50PXNpZ24rJ1IkICcrTWF0aC5hYnMoZGlmZikudG9GaXhlZCgyKSsnICgnK3NpZ24rcGN0KyclKSc7CiAgZWxzZSBpZih0eXBlPT09J3VzZCcpZS50ZXh0Q29udGVudD1zaWduK2RpZmYudG9GaXhlZCgyKSsnICgnK3NpZ24rcGN0KyclKSc7CiAgZWxzZSBlLnRleHRDb250ZW50PXNpZ24rTWF0aC5hYnMoZGlmZikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnICgnK3NpZ24rcGN0KyclKSc7CiAgZS5jbGFzc05hbWU9J2MtY2ggJysoZGlmZj4wPydjaGctdXAnOmRpZmY8MD8nY2hnLWRuJzonY2hnLWZsJyk7Cn0KZnVuY3Rpb24gc3dpdGNoVGFiKHRhYixlbCl7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYicpLmZvckVhY2godD0+dC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYi1jb250ZW50JykuZm9yRWFjaCh0PT50LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndGFiLScrdGFiKS5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZihlbCllbC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICBpZih0YWI9PT0naW5kaWNhZG9yZXMnJiYhd2luZG93Ll9pbmRMb2FkZWQpe3dpbmRvdy5faW5kTG9hZGVkPXRydWU7bG9hZEluZGljYXRvcnMoKTt9CiAgaWYodGFiPT09J2NhbGVuZGFyaW8nKWxvYWRDYWxlbmRhcigpOwp9CmZ1bmN0aW9uIHRvZ2dsZVNlZyhpZCl7CiAgY29uc3QgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2JvZHktJytpZCk7Y29uc3QgYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2Fyci0nK2lkKTsKICBpZighYilyZXR1cm47Y29uc3Qgb3Blbj1iLnN0eWxlLmRpc3BsYXkhPT0nYmxvY2snOwogIGIuc3R5bGUuZGlzcGxheT1vcGVuPydibG9jayc6J25vbmUnOwogIGlmKGEpYS50ZXh0Q29udGVudD1vcGVuPyfilrInOifilrwnOwogIGlmKG9wZW4mJiFiLmRhdGFzZXQubG9hZGVkKXtiLmRhdGFzZXQubG9hZGVkPScxJztsb2FkU2VnbWVudChpZCk7fQp9Cgphc3luYyBmdW5jdGlvbiBsb2FkU2VnbWVudChpZCl7CiAgY29uc3QgZ3JpZD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2dyaWQtJytpZCk7aWYoIWdyaWQpcmV0dXJuOwogIGNvbnN0IHBmeD1pZCsnX18nOwogIGlmKFVTX1NFR1tpZF0pewogICAgY29uc3QgdGtzPVVTX1NFR1tpZF07CiAgICBncmlkLmlubmVySFRNTD10a3MubWFwKHQ9PnsKICAgICAgY29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTsKICAgICAgcmV0dXJuICc8ZGl2IGNsYXNzPSJjYXJkIGIiPjxkaXYgY2xhc3M9ImMtbGJsIj5VUzwvZGl2PjxkaXYgY2xhc3M9ImMtbm0iPicrdCsnPC9kaXY+JysKICAgICAgICAnPGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9kaXY+JysKICAgICAgICAnPGRpdiBjbGFzcz0iYy1jaCIgaWQ9IicrcGZ4K3RpZCsnX2MiPuKAlDwvZGl2PjwvZGl2Pic7CiAgICB9KS5qb2luKCcnKTsKICAgIHRyeXsKICAgICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvdXMvcXVvdGVzP3RpY2tlcnM9Jyt0a3Muam9pbignLCcpKTsKICAgICAgaWYoIXIub2spcmV0dXJuOwogICAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgICBPYmplY3QuZW50cmllcyhkKS5mb3JFYWNoKChbdCx2XSk9PnsKICAgICAgICBjb25zdCB0aWQ9dC5yZXBsYWNlKC9bXmEtekEtWjAtOV0vZywnXycpOwogICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19wJyk7CiAgICAgICAgY29uc3QgZWM9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX2MnKTsKICAgICAgICBpZihlcCYmdi5wcmljZSl7ZXAudGV4dENvbnRlbnQ9JyQnK051bWJlcih2LnByaWNlKS50b0ZpeGVkKDIpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CiAgICAgICAgaWYoZWMmJnYucHJpY2UmJnYucHJldilzZXRDaGcocGZ4K3RpZCsnX2MnLHYucHJpY2Usdi5wcmV2LCd1c2QnKTsKICAgICAgfSk7CiAgICB9Y2F0Y2goZSl7fQogICAgcmV0dXJuOwogIH0KICBjb25zdCB0a3M9U0VHW2lkXTtpZighdGtzKXJldHVybjsKICBncmlkLmlubmVySFRNTD10a3MubWFwKHQ9PnsKICAgIGNvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCk7CiAgICByZXR1cm4gJzxkaXYgY2xhc3M9ImNhcmQgZyI+PGRpdiBjbGFzcz0iYy1sYmwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1ubSI+Jyt0Kyc8L2Rpdj4nKwogICAgICAnPGRpdiBjbGFzcz0iYy1wciBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9kaXY+JysKICAgICAgJzxkaXYgY2xhc3M9ImMtY2giIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nOwogIH0pLmpvaW4oJycpOwogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL3R2L2JyYXppbCcsewogICAgICBtZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzLm1hcCh0PT4nQk1GQk9WRVNQQTonK3QpfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KQogICAgfSk7CiAgICBpZighci5vaylyZXR1cm47CiAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgKGQuZGF0YXx8W10pLmZvckVhY2goeD0+ewogICAgICBjb25zdCB0PXgucy5yZXBsYWNlKCdCTUZCT1ZFU1BBOicsJycpLnRvTG93ZXJDYXNlKCk7CiAgICAgIGNvbnN0W2MsY2FdPXguZHx8W107CiAgICAgIGlmKGMhPW51bGwpewogICAgICAgIGNvbnN0IGVwPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0KydfcCcpOwogICAgICAgIGlmKGVwKXtlcC50ZXh0Q29udGVudD1mQlJMKGMpO2VwLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CiAgICAgICAgc2V0Q2hnKHBmeCt0KydfYycsYyxjLShjYXx8MCksJ2JybCcpOwogICAgICB9CiAgICB9KTsKICB9Y2F0Y2goZSl7fQp9Cgphc3luYyBmdW5jdGlvbiBmZXRjaEhMKCl7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pOwogICAgaWYoIXIub2spcmV0dXJuOwogICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IGJwPXBhcnNlRmxvYXQoZC5CVEN8fDApOwogICAgaWYoYnA+MCl7c2V0RWwoJ2J0Yy1wJyxmVVNEKGJwKSk7c2V0Q2hnKCdidGMtYycsYnAsYnAqMC45OSwndXNkJyk7fQogICAgdHJ5ewogICAgICBjb25zdCByMj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcycsZGV4Oid4eXonfSl9KTsKICAgICAgaWYocjIub2spewogICAgICAgIGNvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTsKICAgICAgICBpZihkMlsneHl6OkNMJ10pc2V0RWwoJ2NsLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q0wnXSkudG9GaXhlZCgyKSk7CiAgICAgICAgaWYoZDJbJ3h5ejpHT0xEJ10pc2V0RWwoJ2dvbGQtcCcsJyQnK051bWJlcihkMlsneHl6OkdPTEQnXSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7CiAgICAgICAgaWYoZDJbJ3h5ejpTSUxWRVInXSlzZXRFbCgnc2lsdmVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6U0lMVkVSJ10pLnRvRml4ZWQoMikpOwogICAgICAgIGlmKGQyWyd4eXo6Q09QUEVSJ10pc2V0RWwoJ2NvcHBlci1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OkNPUFBFUiddKS50b0ZpeGVkKDMpKTsKICAgICAgfQogICAgfWNhdGNoKGUpe30KICB9Y2F0Y2goZSl7fQp9Cgphc3luYyBmdW5jdGlvbiBmZXRjaFRWKCl7CiAgY29uc3Qgb3V0PXt9OwogIHRyeXsKICAgIGNvbnN0IHRrcz1bJ0JNRkJPVkVTUEE6UEVUUjQnLCdCTUZCT1ZFU1BBOklUVUI0JywnQk1GQk9WRVNQQTpWQUxFMycsJ0JNRkJPVkVTUEE6QkJEQzQnLCdCTUZCT1ZFU1BBOkFCRVYzJywnQk1GQk9WRVNQQTpCQkFTMycsJ0JNRkJPVkVTUEE6V0VHRTMnLCdCTUZCT1ZFU1BBOklCT1YnXTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL3R2L2JyYXppbCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOnRrc30sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTsKICAgIGlmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7KGQuZGF0YXx8W10pLmZvckVhY2goeD0+e2NvbnN0W2MsY2FdPXguZHx8W107aWYoYyE9bnVsbClvdXRbeC5zXT17cDpjLHY6Yy0oY2F8fDApfTt9KTt9CiAgfWNhdGNoKGUpe30KICB0cnl7CiAgICBjb25zdCBycj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy9ST1hPMzQuU0EnKTsKICAgIGlmKHJyLm9rKXtjb25zdCBkZD1hd2FpdCByci5qc29uKCk7aWYoZGQucHJlY29fYXR1YWwpe3NldEVsKCdyb3hvMzRxLXAnLGZCUkwoZGQucHJlY29fYXR1YWwpKTtzZXRDaGcoJ3JveG8zNHEtYycsZGQucHJlY29fYXR1YWwsKGRkLnByZWNvX2FudGVyaW9yfHxkZC5wcmVjb19hdHVhbCowLjk5KSwnYnJsJyk7fX0KICB9Y2F0Y2goZSl7fQogIHJldHVybiBvdXQ7Cn0KCmFzeW5jIGZ1bmN0aW9uIGZldGNoRnV0dXJlcygpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9mdXR1cmVzJyk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQoKYXN5bmMgZnVuY3Rpb24gZmV0Y2hGdW5kaW5nKCl7CiAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vZmFwaS5iaW5hbmNlLmNvbS9mYXBpL3YxL3ByZW1pdW1JbmRleD9zeW1ib2w9QlRDVVNEVCcpO2lmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7c2V0RWwoJ2J0Yy1mdW5kJywocGFyc2VGbG9hdChkLmxhc3RGdW5kaW5nUmF0ZXx8MCkqMTAwKS50b0ZpeGVkKDQpKyclJyk7cmV0dXJuO319Y2F0Y2goZSl7fQogIHRyeXtjb25zdCByMj1hd2FpdCBmZXRjaChCQVNFKycvYmluYW5jZS9mdW5kaW5nJyk7aWYoIXIyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIyLmpzb24oKTtpZihkLmxhc3RGdW5kaW5nUmF0ZSlzZXRFbCgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlKSoxMDApLnRvRml4ZWQoNCkrJyUnKTt9Y2F0Y2goZSl7fQp9CgpmdW5jdGlvbiBkb01hY3JvKHR2LGZ1dHVyZXMpewogIGNvbnN0IGliRD10dlsnQk1GQk9WRVNQQTpJQk9WJ107aWYoaWJEKXtzZXRFbCgnaWJvdi1wJyxmUFRTKGliRC5wKSk7c2V0Q2hnKCdpYm92LWMnLGliRC5wLGliRC52LCdwdHMnKTt9CiAgW1snUEVUUjQnLCdwZXRyNHEnXSxbJ0lUVUI0JywnaXR1YjRxJ10sWydWQUxFMycsJ3ZhbGUzcSddLFsnQkJEQzQnLCdiYmRjNHEnXSxbJ0FCRVYzJywnYWJldjNxJ10sWydCQkFTMycsJ2JiYXMzcSddLFsnV0VHRTMnLCd3ZWdlM3EnXV0uZm9yRWFjaCgoW3QsaWRdKT0+ewogICAgY29uc3QgZD10dlsnQk1GQk9WRVNQQTonK3RdO2lmKGQpe3NldEVsKGlkKyctcCcsZkJSTChkLnApKTtzZXRDaGcoaWQrJy1jJyxkLnAsZC52LCdicmwnKTt9CiAgfSk7CiAgaWYoZnV0dXJlcyl7CiAgICBjb25zdCBmPWZ1dHVyZXM7CiAgICBjb25zdCBhZj0oaWQsdmFsKT0+e2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKGUpe2UudGV4dENvbnRlbnQ9dmFsO2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO319OwogICAgaWYoZi5kamk/LnByaWNlKXthZignZGppLXAnLGZQVFMoZi5kamkucHJpY2UpKTtzZXRDaGcoJ2RqaS1jJyxmLmRqaS5wcmljZSxmLmRqaS5wcmV2LCdwdHMnKTt9CiAgICBpZihmLmVzZj8ucHJpY2Upe2FmKCdlc2YtcCcsZlBUUyhmLmVzZi5wcmljZSkpO3NldENoZygnZXNmLWMnLGYuZXNmLnByaWNlLGYuZXNmLnByZXYsJ3B0cycpO30KICAgIGlmKGYubnFmPy5wcmljZSl7YWYoJ25xZi1wJyxmUFRTKGYubnFmLnByaWNlKSk7c2V0Q2hnKCducWYtYycsZi5ucWYucHJpY2UsZi5ucWYucHJldiwncHRzJyk7fQogICAgaWYoZi53aW4/LnByaWNlKXthZignd2luLXAnLGZQVFMoZi53aW4ucHJpY2UpKTtzZXRDaGcoJ3dpbi1jJyxmLndpbi5wcmljZSxmLndpbi5wcmV2LCdwdHMnKTt9CiAgICBpZihmLnZpeD8ucHJpY2Upe2FmKCd2aXgtcCcsTnVtYmVyKGYudml4LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ3ZpeC1jJyxmLnZpeC5wcmljZSxmLnZpeC5wcmV2LCd1c2QnKTt9CiAgICBpZihmLmR4eT8ucHJpY2Upe2FmKCdkeHktcCcsTnVtYmVyKGYuZHh5LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ2R4eS1jJyxmLmR4eS5wcmljZSxmLmR4eS5wcmV2LCd1c2QnKTt9CiAgICBpZihmLnVzZD8ucHJpY2Upe2FmKCd1c2QtcCcsZkJSTChmLnVzZC5wcmljZSkpO3NldENoZygndXNkLWMnLGYudXNkLnByaWNlLGYudXNkLnByZXZ8fGYudXNkLnByaWNlLCdicmwnKTt9CiAgfQp9CgpmdW5jdGlvbiBkb1Bvc2l0aW9ucyh0dil7CiAgY29uc3QgcHREPXR2WydCTUZCT1ZFU1BBOlBFVFI0J107Y29uc3QgcHRQPXB0RD8ucHx8NDAscHRWPXB0RD8udnx8NDA7CiAgc2V0RWwoJ3B0LXBvcy1wJyxmQlJMKHB0UCkpO3NldENoZygncHQtcG9zLWMnLHB0UCxwdFYsJ2JybCcpOwogIGNvbnN0IHB0RDI9cHRQLTMwLjg1O3NldEVsKCdwdC1pdG0nLChwdEQyPj0wPycrIFIkICc6Jy0gUiQgJykrTWF0aC5hYnMocHREMikudG9GaXhlZCgyKSsnICcrKHB0RDI+PTA/J2FjaW1hJzonYWJhaXhvJykrJyBkbyBzdHJpa2UnKTsKICBjb25zdCB2bEQ9dHZbJ0JNRkJPVkVTUEE6VkFMRTMnXTtjb25zdCB2bFA9dmxEPy5wfHw3OCx2bFY9dmxEPy52fHw3ODsKICBzZXRFbCgndmwtcG9zLXAnLGZCUkwodmxQKSk7c2V0Q2hnKCd2bC1wb3MtYycsdmxQLHZsViwnYnJsJyk7CiAgY29uc3QgdmxEMj12bFAtNTcuNDA7c2V0RWwoJ3ZsLWl0bScsKHZsRDI+PTA/JysgUiQgJzonLSBSJCAnKStNYXRoLmFicyh2bEQyKS50b0ZpeGVkKDIpKycgJysodmxEMj49MD8nYWNpbWEnOidhYmFpeG8nKSsnIGRvIHN0cmlrZScpOwogIGNvbnN0IGNkPShkcyxlaWQpPT57Y29uc3Qgdj1uZXcgRGF0ZShkcyk7Y29uc3QgZD1NYXRoLm1heCgwLE1hdGguY2VpbCgodi1uZXcgRGF0ZSgpKS84NjRlNSkpO2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoZWlkKTtpZihlKWUudGV4dENvbnRlbnQ9ZDt9OwogIGNkKCcyMDI2LTEyLTE3JywncHQtZGlhcycpO2NkKCcyMDI3LTAyLTE4JywndmwtZGlhcycpO2NkKCcyMDI2LTA5LTE0JywnYXhpYTNmLWRpYXMnKTtjZCgnMjAyNi0xMC0wMicsJ2F4aWEzYi1kaWFzJyk7Y2QoJzIwMjYtMDctMTYnLCdyb3hvMzQtZGlhcycpOwogIHNldFRpbWVvdXQoYXN5bmMoKT0+ewogICAgdHJ5ewogICAgICBjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9pbmRpY2F0b3JzL0FYSUEzLlNBJyk7aWYoIXIub2spcmV0dXJuOwogICAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjsKICAgICAgY29uc3QgcD1kLnByZWNvX2F0dWFsO3NldEVsKCdheGlhMy1wb3MtcCcsZkJSTChwKSk7c2V0RWwoJ2F4aWEzYi1wb3MtcCcsZkJSTChwKSk7CiAgICAgIGNvbnN0IGtkb0E9NDMuNTEsa3VvQT02OC43NixrZG9CPTQwLjUyLGt1b0I9NjIuODE7CiAgICAgIGNvbnN0IGRBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1rZG8tZGlzdCcpO2lmKGRBKWRBLnRleHRDb250ZW50PSgocC1rZG9BKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1QT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTMta3VvLWRpc3QnKTtpZih1QSl1QS50ZXh0Q29udGVudD0oKGt1b0EtcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7CiAgICAgIGNvbnN0IHNBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1zdGF0dXMnKTtpZihzQSl7c0EudGV4dENvbnRlbnQ9cDw9a2RvQT8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1b0E/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NBLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PWtkb0F8fHA+PWt1b0E/J3dhcm4nOidvaycpO30KICAgICAgY29uc3QgZEI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1rZG8tZGlzdCcpO2lmKGRCKWRCLnRleHRDb250ZW50PSgocC1rZG9CKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nOwogICAgICBjb25zdCB1Qj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTNiLWt1by1kaXN0Jyk7aWYodUIpdUIudGV4dENvbnRlbnQ9KChrdW9CLXApL3AqMTAwKS50b0ZpeGVkKDEpKyclIHBhcmEgbyBLVU8nOwogICAgICBjb25zdCBzQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTNiLXN0YXR1cycpO2lmKHNCKXtzQi50ZXh0Q29udGVudD1wPD1rZG9CPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VvQj8n4pqgIEtVTyBBVElOR0lETyc6J+KchSBObyByYW5nZSc7c0IuY2xhc3NOYW1lPSdzYi12YWwgJysocDw9a2RvQnx8cD49a3VvQj8nd2Fybic6J29rJyk7fQogICAgfWNhdGNoKGUpe30KICB9LDIwMDApOwogIHNldFRpbWVvdXQoYXN5bmMoKT0+ewogICAgdHJ5ewogICAgICBjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKCFyLm9rKXJldHVybjsKICAgICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTtpZighZC5wcmVjb19hdHVhbClyZXR1cm47CiAgICAgIGNvbnN0IHA9ZC5wcmVjb19hdHVhbDtzZXRFbCgncm94bzM0LXBvcy1wJyxmQlJMKHApKTsKICAgICAgY29uc3QgZGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JveG8zNC1rZG8tZGlzdCcpO2lmKGRlKWRlLnRleHRDb250ZW50PSgocC0xMC41MCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgYWNpbWEgZGEgYmFycmVpcmEnOwogICAgICBjb25zdCBzZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm94bzM0LXN0YXR1cycpO2lmKHNlKXtzZS50ZXh0Q29udGVudD1wPD0xMC41MD8n8J+UtCBCQVJSRUlSQSBBVElOR0lEQSc6J+KchSBBY2ltYSBkYSBiYXJyZWlyYSc7c2UuY2xhc3NOYW1lPSdzYi12YWwgJysocDw9MTAuNTA/J2l0bSc6J29rJyk7fQogICAgfWNhdGNoKGUpe30KICB9LDMwMDApOwp9CgovLyDilIDilIAgTW9udGUgQ2FybG8gQ09SUklHSURPIOKUgOKUgAovLyBwcm9iX2NhbGxfZXhlcmNpZGEgPSBwcm9iIGRlIG8gcHJlw6dvIHN1YmlyIEFDSU1BIGRvIHN0cmlrZSBubyB2ZW5jaW1lbnRvCi8vIFBhcmEgY2FsbCB2ZW5kaWRhIElUTSAocHJlw6dvID4gc3RyaWtlKSwgaXNzbyBqw6Egw6kgYWx0byBwb3IgZGVmaW5pw6fDo28KLy8gTyB1c3XDoXJpbyBxdWVyIHZlciBlc3NlIG7Dum1lcm8gY29tbyAicmlzY28gZGUgZXhlcmPDrWNpbyIKYXN5bmMgZnVuY3Rpb24gcnVuTUNGb3JBdGl2byh0aWNrZXIsc3RyaWtlLGRpYXMsbG9hZElkLHJlc0lkLHN0cmlrZUlkLHZvbElkLGluZm9JZCxydElkKXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcixrX2NhbGw6c3RyaWtlLGtfcHV0OnN0cmlrZSx0X2RheXM6ZGlhcyxuOjUwMDB9KX0pOwogICAgY2xlYXJUaW1lb3V0KHRvKTtpZighci5vayl0aHJvdyAwOwogICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxvYWRJZCkuc3R5bGUuZGlzcGxheT0nbm9uZSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChyZXNJZCkuc3R5bGUuZGlzcGxheT0nYmxvY2snOwogICAgLy8gcHJvYl9jYWxsX2V4ZXJjaWRhID0gcHJvYiBkZSBmZWNoYXIgQUNJTUEgZG8gc3RyaWtlID0gcmlzY28gcGFyYSBjYWxsIHZlbmRpZGEKICAgIGNvbnN0IHByb2I9TnVtYmVyKGQucHJvYl9jYWxsX2V4ZXJjaWRhfHwwKTsKICAgIGNvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChzdHJpa2VJZCk7CiAgICBzRWwudGV4dENvbnRlbnQ9cHJvYi50b0ZpeGVkKDEpKyclJzsKICAgIC8vIFZlcmRlIHNlIGJhaXhhIHByb2IgZGUgZXhlcmNlciAocG9zacOnw6NvIHNlZ3VyYSksIHZlcm1lbGhvIHNlIGFsdGEKICAgIHNFbC5jbGFzc05hbWU9J2luZC12YWwgJysocHJvYjwxNT8nb2snOnByb2I8MzA/J3dhcm4nOidkb3duJyk7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCh2b2xJZCkudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpbmZvSWQpLnRleHRDb250ZW50PQogICAgICAnVm9sLmhpc3QuICcrZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSAoTUMpIMK3ICcrCiAgICAgICdCJlMgdXNhIHZvbC5pbXBsLiBtYWlvciDihpIgcHJvYiBCJlMgPiBNQyDCtyAnKwogICAgICAocHJvYjwxNT8n4pyFIFJpc2NvIGJhaXhvIGRlIGV4ZXJjw61jaW8nOifimqAgTW9uaXRvcmFyIHBvc2nDp8OjbycpOwogICAgaWYocnRJZClzZXRFbChydElkLHByb2IudG9GaXhlZCgxKSsnJScpOwogIH1jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChsb2FkSWQpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCdpbmRpc3BvbsOtdmVsJyk7fQp9Cgphc3luYyBmdW5jdGlvbiBydW5NQ0JhcnJpZXIodGlja2VyLGVudHJ5LGtkbyxrdW8sZGlhcyxwcmljZSxwcmVmaXgpewogIHByZWZpeD1wcmVmaXh8fCdheGlhMyc7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7Y29uc3QgdG89c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTsKICAgIGNvbnN0IGJvZHk9e3RpY2tlcixlbnRyeSxrZG8sa3VvLHRfZGF5czpkaWFzLG46MzAwMH07aWYocHJpY2U+MClib2R5LnByaWNlPXByaWNlOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvbW9udGVjYXJsby9iYXJyaWVyJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KGJvZHkpfSk7CiAgICBjbGVhclRpbWVvdXQodG8pO2lmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKS5zdHlsZS5kaXNwbGF5PSdub25lJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLXJlc3VsdCcpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLW5vYnInKS50ZXh0Q29udGVudD1kLnByb2Jfc2VtX2JhcnJlaXJhLnRvRml4ZWQoMSkrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kycta3VvJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2FsdGEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1rZG8nKS50ZXh0Q29udGVudD1kLnByb2JfYmFycmVpcmFfYmFpeGEudG9GaXhlZCgxKSsnJSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy12b2wnKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWluZm8nKS50ZXh0Q29udGVudD0nUiQgJytkLnByZWNvX2F0dWFsKycgwrcgS0RPIFIkICcrZC5rZG8rJyDCtyBLVU8gUiQgJytkLmt1bysnIMK3ICcrZC5jZW5hcmlvcy50b0xvY2FsZVN0cmluZygpKycgY2VuLic7CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwnaW5kaXNwb27DrXZlbCcpO30KfQoKYXN5bmMgZnVuY3Rpb24gcnVuTUNQcmVmaXhhZG8odGlja2VyLGVudHJ5LGtkbyxkaWFzLHByaWNlKXsKICB0cnl7CiAgICBjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApOwogICAgY29uc3QgYm9keT17dGlja2VyLGtfY2FsbDplbnRyeSxrX3B1dDplbnRyeSx0X2RheXM6ZGlhcyxrbm9ja19kb3duOmtkbyxuOjUwMDB9O2lmKHByaWNlPjApYm9keS5wcmljZT1wcmljZTsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoYm9keSl9KTsKICAgIGNsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1sb2FkaW5nJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LXJlc3VsdCcpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJzsKICAgIGNvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LXN1Y2Vzc28nKTsKICAgIHNFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX3N1Y2Vzc28pLnRvRml4ZWQoMSkrJyUnOwogICAgc0VsLmNsYXNzTmFtZT0naW5kLXZhbCAnKyhkLnByb2Jfc3VjZXNzbz43MD8nb2snOmQucHJvYl9zdWNlc3NvPjUwPyd3YXJuJzonZG93bicpOwogICAgY29uc3QgY0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtY2FsbCcpO2lmKGNFbCljRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9jYWxsX2V4ZXJjaWRhKS50b0ZpeGVkKDEpKyclJzsKICAgIGNvbnN0IGtFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWtkbycpO2lmKGtFbClrRWwudGV4dENvbnRlbnQ9ZC5wcm9iX2tkb19hdGluZ2lkbyE9bnVsbD9OdW1iZXIoZC5wcm9iX2tkb19hdGluZ2lkbykudG9GaXhlZCgxKSsnJSc6J+KAlCc7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LXZvbCcpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1pbmZvJykudGV4dENvbnRlbnQ9J1IkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua25vY2tfZG93bisnIMK3ICcrZC5jZW5hcmlvcy50b0xvY2FsZVN0cmluZygpKycgY2VuLic7CiAgfWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtbG9hZGluZycpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCdpbmRpc3BvbsOtdmVsJyk7fQp9CgovLyDilIDilIAgSW5kaWNhZG9yZXMg4pSA4pSACmFzeW5jIGZ1bmN0aW9uIGZldGNoSW5kaWNhdG9ycyh0aWNrZXIpe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMzAwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvJyt0aWNrZXIse3NpZ25hbDpjdHJsLnNpZ25hbH0pO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hCVENJbmRpY2F0b3JzKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvYnRjL2luZGljYXRvcnMnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZldGNoQlRDQ3ljbGUoKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDE1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9idGMvY3ljbGUnLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZldGNoRmVhckdyZWVkKCl7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvZmVhcmdyZWVkJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBjb25zdCB2PWQudmFsdWV8fDUwO2NvbnN0IGNscz12PD0yNT8ndmFyKC0tcmVkKSc6djw9NDU/J3ZhcigtLXdhcm4pJzp2PD03NT8ndmFyKC0tYWNjZW50KSc6J3ZhcigtLWdyZWVuKSc7CiAgICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmVhci1ncmVlZC1hcmVhJyk7CiAgICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMnB4Ij4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206NnB4Ij7wn5ixIEZFQVIgJiBHUkVFRCBJTkRFWDwvZGl2PicrCiAgICAgICc8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4Ij4nKwogICAgICAgICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MzJweDtmb250LXdlaWdodDo4MDA7Y29sb3I6JytjbHMrJyI+Jyt2Kyc8L2Rpdj4nKwogICAgICAgICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MTNweDtmb250LXdlaWdodDo3MDA7Y29sb3I6JytjbHMrJyI+JysoZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpKyc8L2Rpdj4nKwogICAgICAnPC9kaXY+PC9kaXY+JzsKICAgIHNldEVsKCdmZy12YWwnLFN0cmluZyh2KSk7c2V0RWwoJ2ZnLWxibCcsZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpOwogICAgdHJ5e2NvbnN0IHJiPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7aWYocmIub2spe2NvbnN0IGRiPWF3YWl0IHJiLmpzb24oKTtjb25zdCBicD1wYXJzZUZsb2F0KGRiLkJUQ3x8MCk7aWYoYnA+MCl7c2V0RWwoJ2J0Yy1pbmQtcHJpY2UnLCckJytOdW1iZXIoYnApLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpO3NldEVsKCdidGMtcCcsZlVTRChicCkpO319fWNhdGNoKGUyKXt9CiAgfWNhdGNoKGUpe30KfQoKZnVuY3Rpb24gcmVuZGVySW5kaWNhdG9ycyhhcmVhSWQsZGF0YSxzaG93QWxsKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChhcmVhSWQpO2lmKCFlbClyZXR1cm47CiAgaWYoIWRhdGEpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7Zm9udC1zaXplOjExcHg7cGFkZGluZzoxMHB4Ij7ij7MgU2VtIHJlc3Bvc3RhIOKAlCBjbGlxdWUg4oa7IHJlY2FycmVnYXI8L2Rpdj4nO3JldHVybjt9CiAgaWYoZGF0YS5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1yZWQpO2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MTBweCI+4pqgICcrZGF0YS5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGNvbnN0IGluZHM9ZGF0YS5pbmRpY2Fkb3Jlc3x8W107CiAgY29uc3Qgc2M9TnVtYmVyKGRhdGEuc2NvcmVfdG90YWx8fDApO2NvbnN0IHByZWNvPWRhdGEucHJlY29fYXR1YWw7Y29uc3QgZ3JhaGFtPWRhdGEuZ3JhaGFtX3ZhbHVlO2NvbnN0IHVwc2lkZT1kYXRhLnVwc2lkZV9ncmFoYW07Y29uc3Qgc2V0b3I9ZGF0YS5zZXRvcnx8Jyc7CiAgY29uc3Qgc2MyPXNjPj02NT8ndmFyKC0tZ3JlZW4pJzpzYz49NDA/J3ZhcigtLXdhcm4pJzondmFyKC0tcmVkKSc7CiAgY29uc3Qgc2w9c2M+PTY1PydDb21wcmEg4payJzpzYz49NDA/J05ldXRybyDihpInOidWZW5kYSDilrwnOwogIGxldCBodG1sPSc8ZGl2IGNsYXNzPSJzY29yZS1ib3giPicrCiAgICAnPGRpdiBjbGFzcz0ic2NvcmUtY2VsbCI+PGRpdiBjbGFzcz0ic2NvcmUtbWV0YSI+U2NvcmU8L2Rpdj48ZGl2IGNsYXNzPSJzY29yZS1udW0iIHN0eWxlPSJjb2xvcjonK3NjMisnIj4nK3NjKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY29yZS1sYmwiIHN0eWxlPSJjb2xvcjonK3NjMisnIj4nK3NsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjb3JlLWNlbGwiPjxkaXYgY2xhc3M9InNjb3JlLW1ldGEiPkNvdGHDp8OjbyBBdHVhbDwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXZhbCI+JysocHJlY28/J1IkICcrTnVtYmVyKHByZWNvKS50b0ZpeGVkKDIpOifigJQnKSsnPC9kaXY+PGRpdiBjbGFzcz0ic2NvcmUtc3ViIj4nK3NldG9yKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9InNjb3JlLWNlbGwiPjxkaXYgY2xhc3M9InNjb3JlLW1ldGEiPkdyYWhhbSBWSjwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXZhbCIgc3R5bGU9ImNvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyhncmFoYW0/J1IkICcrTnVtYmVyKGdyYWhhbSkudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXN1YiIgc3R5bGU9ImNvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cHNpZGUhPW51bGw/KHVwc2lkZT4wPycrJzonJykrdXBzaWRlKyclIHVwc2lkZSc6J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzwvZGl2Pic7CiAgKHNob3dBbGw/aW5kczppbmRzLnNsaWNlKDAsMTQpKS5mb3JFYWNoKGk9PnsKICAgIGNvbnN0IHM9aS5zaW5hbHx8Jyc7CiAgICBjb25zdCBjbHM9cz09PSdBbHRhJ3x8cz09PSdTb2JyZXZlbmRhJz8nb2snOnM9PT0nQmFpeGEnfHxzPT09J1NvYnJlY29tcHJhJz8nZG93bic6J3dhcm4nOwogICAgY29uc3QgYXJyb3c9Y2xzPT09J29rJz8n4payJzpjbHM9PT0nZG93bic/J+KWvCc6J+KGkic7CiAgICBodG1sKz0nPGRpdiBjbGFzcz0iaW5kLXJvdyI+JysKICAgICAgJzxkaXYgY2xhc3M9ImluZC1yb3ctdG9wIj4nKwogICAgICAgICc8c3BhbiBjbGFzcz0iaW5kLXJvdy1ub21lIj4nKyhpLm5vbWV8fCcnKSsnPC9zcGFuPicrCiAgICAgICAgJzxzcGFuIGNsYXNzPSJpbmQtcm93LXZhbCAnK2NscysnIj4nKyhpLnZhbG9yIT1udWxsP2kudmFsb3I6J+KAlCcpKycgJythcnJvdysnPC9zcGFuPicrCiAgICAgICc8L2Rpdj4nKwogICAgICAoaS5leHBsaWNhY2FvPyc8ZGl2IGNsYXNzPSJpbmQtcm93LWV4cCI+JytpLmV4cGxpY2FjYW8rJzwvZGl2Pic6JycpKwogICAgICAnPC9kaXY+JzsKICB9KTsKICBlbC5pbm5lckhUTUw9aHRtbHx8JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6MTFweDtwYWRkaW5nOjhweCI+U2VtIGluZGljYWRvcmVzPC9kaXY+JzsKfQoKZnVuY3Rpb24gcmVuZGVyQlRDSW5kaWNhdG9ycyhkYXRhKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWluZC1hcmVhJyk7aWYoIWVsfHwhZGF0YSlyZXR1cm47CiAgaWYoZGF0YS5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS13YXJuKTtmb250LXNpemU6MTFweDtwYWRkaW5nOjEwcHgiPuKPsyAnK2RhdGEuZXJyb3IrJzwvZGl2Pic7cmV0dXJuO30KICBsZXQgaHRtbD0nPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo1cHgiPic7CiAgaWYoZGF0YS5yc2lfc2VtYW5hbCE9bnVsbCl7CiAgICBjb25zdCByPWRhdGEucnNpX3NlbWFuYWw7Y29uc3QgY2xzPXI8MzA/J29rJzpyPjcwPydkb3duJzond2Fybic7CiAgICBodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsICcrY2xzKyciPicrci50b0ZpeGVkKDEpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDoycHgiPicrKHI8MzA/J1NvYnJldmVuZGEg4pqhJzpyPjcwPydTb2JyZWNvbXByYSDimqAnOidOZXV0cm8nKSsnPC9kaXY+PC9kaXY+JzsKICAgIHNldEVsKCdidGMtcnNpJyxyLnRvRml4ZWQoMSkpOwogIH0KICBpZihkYXRhLm1tNTBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gNTAgc2VtLjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JCcrTnVtYmVyKGRhdGEubW01MF9zZW1hbmFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nOwogIGlmKGRhdGEubW0yMDBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gMjAwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPiQnK051bWJlcihkYXRhLm1tMjAwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgaWYoZGF0YS5tYWNkX2hpc3RvZ3JhbSE9bnVsbCl7Y29uc3QgbWg9ZGF0YS5tYWNkX2hpc3RvZ3JhbTtodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TUFDRCBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysobWg+MD8nb2snOidkb3duJykrJyI+JytOdW1iZXIobWgpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JysobWg+MD8nTW9tZW50dW0g4payJzonTW9tZW50dW0g4pa8JykrJzwvZGl2PjwvZGl2Pic7fQogIGlmKGRhdGEub2J2X3RyZW5kKWh0bWwrPSc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5PQlY8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsICcrKGRhdGEub2J2X3RyZW5kPT09J3N1YmluZG8nPydvayc6J2Rvd24nKSsnIj4nK2RhdGEub2J2X3RyZW5kKyc8L2Rpdj48L2Rpdj4nOwogIGh0bWwrPSc8L2Rpdj4nO2VsLmlubmVySFRNTD1odG1sOwogIGlmKGRhdGEucHJpY2Upc2V0RWwoJ2J0Yy1pbmQtcHJpY2UnLCckJytOdW1iZXIoZGF0YS5wcmljZSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7Cn0KCmZ1bmN0aW9uIHJlbmRlckJUQ0N5Y2xlKGQpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidGMtY3ljbGUtYXJlYScpO2lmKCFlbHx8IWR8fGQuZXJyb3IpcmV0dXJuOwogIGNvbnN0IGZVPXY9PnY/JyQnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwogIGVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo1cHg7bWFyZ2luLWJvdHRvbTo4cHgiPicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TVZSViBaLVNjb3JlPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCAnKyhkLm12cnZfenNjb3JlPy52YWx1ZTwxPydvayc6ZC5tdnJ2X3pzY29yZT8udmFsdWU8Mz8nd2Fybic6J2Rvd24nKSsnIj4nK2QubXZydl96c2NvcmU/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDoycHgiPicrZC5tdnJ2X3pzY29yZT8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TlVQTDwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JysoKGQubnVwbD8udmFsdWV8fDApKjEwMCkudG9GaXhlZCgwKSsnJTwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JytkLm51cGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlB1ZWxsIE11bHRpcGxlPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nK2QucHVlbGw/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDoycHgiPicrZC5wdWVsbD8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+MjAwVyBNQTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JytmVShkLm1hMjAwdykrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjJweCI+JysoZC5tYTIwMHdfcGN0PycrJytkLm1hMjAwd19wY3QrJyUnOicnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5SYWluYm93IEJhbmQ8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrKGQucmFpbmJvdz8uYmFuZHx8J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlBpIEN5Y2xlIERpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayI+JytmVShkLnBpX2N5Y2xlPy5kaXN0YW5jZSkrJzwvZGl2PjwvZGl2PicrCiAgICAnPC9kaXY+JysKICAgICc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6OHB4O2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWFjY2VudCkiPicrKGQucGlfY3ljbGU/LnNpZ25hbHx8JycpKyc8L2Rpdj4nOwp9Cgphc3luYyBmdW5jdGlvbiBsb2FkSW5kaWNhdG9ycygpewogIGNvbnN0IHd0PShwLG1zLGZiKT0+UHJvbWlzZS5yYWNlKFtwLG5ldyBQcm9taXNlKHI9PnNldFRpbWVvdXQoKCk9PnIoZmIpLG1zKSldKTsKICBjb25zdFtidGMsY3ljbGVdPWF3YWl0IFByb21pc2UuYWxsKFsKICAgIHd0KGZldGNoQlRDSW5kaWNhdG9ycygpLDE1MDAwLHtlcnJvcjonVGltZW91dCDigJQgcmVjYXJyZWd1ZSBhIGFiYSd9KSwKICAgIHd0KGZldGNoQlRDQ3ljbGUoKSwxNTAwMCxudWxsKQogIF0pOwogIHJlbmRlckJUQ0luZGljYXRvcnMoYnRjKTtyZW5kZXJCVENDeWNsZShjeWNsZSk7ZmV0Y2hGZWFyR3JlZWQoKTsKICBjb25zdCBzdG9ja3M9W1snUEVUUjQuU0EnLCdwZXRyNC1pbmQtYXJlYSddLFsnVkFMRTMuU0EnLCd2YWxlMy1pbmQtYXJlYSddLFsnQkJBUzMuU0EnLCdiYmFzMy1pbmQtYXJlYSddLFsnQVhJQTMuU0EnLCdheGlhMy1pbmQtYXJlYSddLFsnUk9YTzM0LlNBJywncm94bzM0LWluZC1hcmVhJ11dOwogIGNvbnN0IHJlc3VsdHM9YXdhaXQgUHJvbWlzZS5hbGwoc3RvY2tzLm1hcCgoW3RdKT0+d3QoZmV0Y2hJbmRpY2F0b3JzKHQpLDMwMDAwLHtlcnJvcjonVGltZW91dCAzMHMnfSkpKTsKICBzdG9ja3MuZm9yRWFjaCgoWyxhaWRdLGkpPT5yZW5kZXJJbmRpY2F0b3JzKGFpZCxyZXN1bHRzW2ldLHRydWUpKTsKfQoKYXN5bmMgZnVuY3Rpb24gcmVsb2FkSW5kKHRpY2tlcil7CiAgY29uc3QgYWlkPXRpY2tlcisnLWluZC1hcmVhJztjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChhaWQpOwogIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj4nOwogIGNvbnN0IG09eydwZXRyNCc6J1BFVFI0LlNBJywndmFsZTMnOidWQUxFMy5TQScsJ2JiYXMzJzonQkJBUzMuU0EnLCdheGlhMyc6J0FYSUEzLlNBJywncm94bzM0JzonUk9YTzM0LlNBJ307CiAgcmVuZGVySW5kaWNhdG9ycyhhaWQsYXdhaXQgZmV0Y2hJbmRpY2F0b3JzKG1bdGlja2VyXXx8dGlja2VyLnRvVXBwZXJDYXNlKCkrJy5TQScpLHRydWUpOwp9CgovLyDilIDilIAgQ2FsZW5kw6FyaW8g4oCUIGJ1c2NhIERJUkVUTyBkbyBicm93c2VyIChldml0YSBibG9xdWVpbyBkbyBSZW5kZXIpIOKUgOKUgApjb25zdCBGTEFHUz17J1VTRCc6J/Cfh7rwn4e4JywnVVMnOifwn4e68J+HuCcsJ0JSTCc6J/Cfh6fwn4e3JywnQlInOifwn4en8J+HtycsJ0VVUic6J/Cfh6rwn4e6JywnR0JQJzon8J+HrPCfh6cnLCdDTlknOifwn4eo8J+HsycsJ0pQWSc6J/Cfh6/wn4e1JywnQ0FEJzon8J+HqPCfh6YnLCdBVUQnOifwn4em8J+HuicsJ0RFJzon8J+HqfCfh6onLCdFVSc6J/Cfh6rwn4e6J307CmNvbnN0IFBBSVNFU19PSz1uZXcgU2V0KFsnVVNEJywnVVMnLCdCUkwnLCdCUicsJ0VVUicsJ0VVJywnR0JQJywnQ05ZJywnSlBZJywnQ0FEJywnQVVEJywnREUnXSk7Cgphc3luYyBmdW5jdGlvbiBsb2FkQ2FsZW5kYXIoKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FsZW5kYXItYXJlYScpO2NvbnN0IHN0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYWwtc3RhdHVzJyk7CiAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOjExcHg7cGFkZGluZzoyMHB4O3RleHQtYWxpZ246Y2VudGVyO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvIGNhbGVuZMOhcmlvLi4uPC9kaXY+JzsKICBpZihzdClzdC50ZXh0Q29udGVudD0nQnVzY2FuZG8gZXZlbnRvcyBkaXJldGFtZW50ZSBkbyBGb3JleCBGYWN0b3J5Li4uJzsKCiAgY29uc3QgYWxsRXZlbnRzPVtdOwogIGNvbnN0IGltcE1hcD17J0xvdyc6MSwnTWVkaXVtJzoyLCdIaWdoJzozLCdIb2xpZGF5JzowfTsKCiAgLy8gQnVzY2EgRElSRVRPIGRvIGJyb3dzZXIg4oCUIHNlbSBwYXNzYXIgcGVsbyBwcm94eQogIGNvbnN0IHVybHM9WwogICAgJ2h0dHBzOi8vbmZzLmZhaXJlY29ub215Lm1lZGlhL2ZmX2NhbGVuZGFyX3RoaXN3ZWVrLmpzb24nLAogICAgJ2h0dHBzOi8vbmZzLmZhaXJlY29ub215Lm1lZGlhL2ZmX2NhbGVuZGFyX25leHR3ZWVrLmpzb24nLAogIF07CgogIGZvcihjb25zdCB1cmwgb2YgdXJscyl7CiAgICB0cnl7CiAgICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2godXJsLHsKICAgICAgICBoZWFkZXJzOnsKICAgICAgICAgICdBY2NlcHQnOidhcHBsaWNhdGlvbi9qc29uJywKICAgICAgICAgICdDYWNoZS1Db250cm9sJzonbm8tY2FjaGUnCiAgICAgICAgfQogICAgICB9KTsKICAgICAgaWYoIXIub2spY29udGludWU7CiAgICAgIGNvbnN0IGRhdGE9YXdhaXQgci5qc29uKCk7CiAgICAgIGZvcihjb25zdCBlIG9mIGRhdGEpewogICAgICAgIGNvbnN0IGN1cj1lLmNvdW50cnl8fGUuY3VycmVuY3l8fCcnOwogICAgICAgIGlmKCFQQUlTRVNfT0suaGFzKGN1cikpY29udGludWU7CiAgICAgICAgY29uc3QgaW1wPWltcE1hcFtlLmltcGFjdF18fDA7CiAgICAgICAgaWYoaW1wPDIpY29udGludWU7CiAgICAgICAgbGV0IGRhdGVfc3RyPScnLHRpbWVfc3RyPScnOwogICAgICAgIGNvbnN0IHJhdz1lLmRhdGV8fCcnOwogICAgICAgIGlmKHJhdyl7CiAgICAgICAgICBkYXRlX3N0cj1yYXcuc2xpY2UoMCwxMCk7CiAgICAgICAgICBpZihyYXcuaW5jbHVkZXMoJ1QnKSl7CiAgICAgICAgICAgIHRyeXsKICAgICAgICAgICAgICBjb25zdCBkdD1uZXcgRGF0ZShyYXcpOwogICAgICAgICAgICAgIC8vIENvbnZlcnRlciBwYXJhIEJSVCAoVVRDLTMpCiAgICAgICAgICAgICAgY29uc3QgYnJ0PW5ldyBEYXRlKGR0LmdldFRpbWUoKS0zKjM2MDAwMDApOwogICAgICAgICAgICAgIGRhdGVfc3RyPWJydC50b0lTT1N0cmluZygpLnNsaWNlKDAsMTApOwogICAgICAgICAgICAgIHRpbWVfc3RyPWJydC50b0lTT1N0cmluZygpLnNsaWNlKDExLDE2KTsKICAgICAgICAgICAgfWNhdGNoKGV4KXt0aW1lX3N0cj1yYXcuc2xpY2UoMTEsMTYpO30KICAgICAgICAgIH0KICAgICAgICB9CiAgICAgICAgY29uc3QgYWN0dWFsPWUuYWN0dWFsfHxudWxsOwogICAgICAgIGNvbnN0IGZvcmVjYXN0PWUuZm9yZWNhc3R8fG51bGw7CiAgICAgICAgbGV0IHNpZ25hbD1udWxsOwogICAgICAgIGlmKGFjdHVhbCYmZm9yZWNhc3QpewogICAgICAgICAgdHJ5ewogICAgICAgICAgICBjb25zdCBhPXBhcnNlRmxvYXQoU3RyaW5nKGFjdHVhbCkucmVwbGFjZSgnJScsJycpLnJlcGxhY2UoJ0snLCcwMDAnKS5yZXBsYWNlKCdNJywnMDAwMDAwJykpOwogICAgICAgICAgICBjb25zdCBmPXBhcnNlRmxvYXQoU3RyaW5nKGZvcmVjYXN0KS5yZXBsYWNlKCclJywnJykucmVwbGFjZSgnSycsJzAwMCcpLnJlcGxhY2UoJ00nLCcwMDAwMDAnKSk7CiAgICAgICAgICAgIHNpZ25hbD1hPj1mPydiZWF0JzonbWlzcyc7CiAgICAgICAgICB9Y2F0Y2goZXgpe30KICAgICAgICB9CiAgICAgICAgYWxsRXZlbnRzLnB1c2goewogICAgICAgICAgZGF0ZTpkYXRlX3N0cix0aW1lOnRpbWVfc3RyLAogICAgICAgICAgY291bnRyeTpjdXIsZmxhZzpGTEFHU1tjdXJdfHwn8J+MkCcsCiAgICAgICAgICBldmVudDplLnRpdGxlfHwnJyxpbXBvcnRhbmNlOmltcCwKICAgICAgICAgIGFjdHVhbCxmb3JlY2FzdCxwcmV2aW91czplLnByZXZpb3VzfHxudWxsLHNpZ25hbAogICAgICAgIH0pOwogICAgICB9CiAgICB9Y2F0Y2goZXgpe2NvbnNvbGUud2FybignQ2FsIGVycm86Jyx1cmwsZXgpO30KICB9CgogIGFsbEV2ZW50cy5zb3J0KChhLGIpPT4oYS5kYXRlK2EudGltZSkubG9jYWxlQ29tcGFyZShiLmRhdGUrYi50aW1lKSk7CgogIGlmKHN0KXN0LnRleHRDb250ZW50PWFsbEV2ZW50cy5sZW5ndGg+MD9hbGxFdmVudHMubGVuZ3RoKycgZXZlbnRvcyDCtyBlc3RhIHNlbWFuYSBlIHByw7N4aW1hJzonU2VtIGV2ZW50b3MgZGlzcG9uw612ZWlzJzsKCiAgaWYoIWFsbEV2ZW50cy5sZW5ndGgpewogICAgZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJwYWRkaW5nOjIwcHg7Y29sb3I6dmFyKC0tbXV0ZWQpO3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4Ij5TZW0gZXZlbnRvcyBkaXNwb27DrXZlaXMuPGJyPjxzbWFsbCBzdHlsZT0iZm9udC1zaXplOjEwcHgiPlRlbnRlIG5vdmFtZW50ZSBlbSBhbGd1bnMgaW5zdGFudGVzLjwvc21hbGw+PC9kaXY+JzsKICAgIHJldHVybjsKICB9CgogIGNvbnN0IGJ5RGF0ZT17fTsKICBhbGxFdmVudHMuZm9yRWFjaChlPT57CiAgICBjb25zdCBkdD1lLmRhdGUuc2xpY2UoMCwxMCk7CiAgICBpZighYnlEYXRlW2R0XSlieURhdGVbZHRdPVtdOwogICAgYnlEYXRlW2R0XS5wdXNoKGUpOwogIH0pOwoKICBsZXQgaHRtbD0nJzsKICBPYmplY3Qua2V5cyhieURhdGUpLnNvcnQoKS5mb3JFYWNoKGR0PT57CiAgICBjb25zdCBkPW5ldyBEYXRlKGR0KydUMTI6MDA6MDAnKTsKICAgIGNvbnN0IGxibD1kLnRvTG9jYWxlRGF0ZVN0cmluZygncHQtQlInLHt3ZWVrZGF5Oidsb25nJyxkYXk6JzItZGlnaXQnLG1vbnRoOidzaG9ydCd9KTsKICAgIGh0bWwrPSc8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuIGNsYXNzPSJhY2MiPvCfk4U8L3NwYW4+ICcrbGJsKyc8L2Rpdj4nKwogICAgICAnPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjEwcHgiPicrCiAgICAgICc8ZGl2IGNsYXNzPSJjYWwtaGRyIj48c3Bhbj5QYcOtczwvc3Bhbj48c3Bhbj5Ib3JhPC9zcGFuPjxzcGFuPkV2ZW50bzwvc3Bhbj48c3Bhbj5JbXA8L3NwYW4+PHNwYW4+UmVhbGl6YWRvPC9zcGFuPjxzcGFuPlByZXZpc3RvPC9zcGFuPjwvZGl2Pic7CiAgICBieURhdGVbZHRdLmZvckVhY2goZT0+ewogICAgICBjb25zdCBpYz1lLmltcG9ydGFuY2U+PTM/J3ZhcigtLXJlZCknOmUuaW1wb3J0YW5jZT49Mj8ndmFyKC0td2FybiknOid2YXIoLS1tdXRlZCknOwogICAgICBjb25zdCBhYz1lLnNpZ25hbD09PSdiZWF0Jz8ndmFyKC0tZ3JlZW4pJzplLnNpZ25hbD09PSdtaXNzJz8ndmFyKC0tcmVkKSc6J3ZhcigtLXRleHQpJzsKICAgICAgaHRtbCs9JzxkaXYgY2xhc3M9ImNhbC1yb3ciPicrCiAgICAgICAgJzxzcGFuPicrZS5mbGFnKyc8L3NwYW4+JysKICAgICAgICAnPHNwYW4gY2xhc3M9ImNhbC10aW1lIj4nKyhlLnRpbWV8fCfigJQnKSsnPC9zcGFuPicrCiAgICAgICAgJzxzcGFuIGNsYXNzPSJjYWwtbmFtZSIgdGl0bGU9IicrZS5ldmVudCsnIj4nK2UuZXZlbnQrJzwvc3Bhbj4nKwogICAgICAgICc8c3BhbiBzdHlsZT0idGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6JytpYysnIj4nKyfil48nLnJlcGVhdChNYXRoLm1pbihlLmltcG9ydGFuY2UsMykpKyc8L3NwYW4+JysKICAgICAgICAnPHNwYW4gY2xhc3M9ImNhbC1hY3R1YWwiIHN0eWxlPSJjb2xvcjonK2FjKyciPicrKGUuYWN0dWFsfHwn4oCUJykrJzwvc3Bhbj4nKwogICAgICAgICc8c3BhbiBjbGFzcz0iY2FsLWZjIj4nKyhlLmZvcmVjYXN0fHwn4oCUJykrJzwvc3Bhbj4nKwogICAgICAgICc8L2Rpdj4nOwogICAgfSk7CiAgICBodG1sKz0nPC9kaXY+JzsKICB9KTsKICBlbC5pbm5lckhUTUw9aHRtbDsKfQoKLy8g4pSA4pSAIE1haW4gbG9vcCDilIDilIAKYXN5bmMgZnVuY3Rpb24gZmV0Y2hBbGwoKXsKICB0cnl7CiAgICBjb25zdFssdHYsZnV0dXJlc109YXdhaXQgUHJvbWlzZS5hbGwoW2ZldGNoSEwoKSxmZXRjaFRWKCksZmV0Y2hGdXR1cmVzKCldKTsKICAgIGNvbnN0IG5vdz1uZXcgRGF0ZSgpLnRvTG9jYWxlVGltZVN0cmluZygncHQtQlInKTsKICAgIHNldEVsKCdsYXN0LXVwZGF0ZScsJ+KGuyAnK25vdyk7c2V0RWwoJ2Zvb3Rlci10aW1lJyxub3cpOwogICAgZG9NYWNybyh0dixmdXR1cmVzKTtkb1Bvc2l0aW9ucyh0dik7CiAgICBzZXRUaW1lb3V0KGZldGNoRnVuZGluZywzMDAwKTsKICAgIHNldFRpbWVvdXQoYXN5bmMoKT0+ewogICAgICB0cnl7Y29uc3RbYixjeWNdPWF3YWl0IFByb21pc2UuYWxsKFtmZXRjaEJUQ0luZGljYXRvcnMoKSxmZXRjaEJUQ0N5Y2xlKCldKTtpZihiKXJlbmRlckJUQ0luZGljYXRvcnMoYik7aWYoY3ljKXJlbmRlckJUQ0N5Y2xlKGN5Yyk7ZmV0Y2hGZWFyR3JlZWQoKTt9Y2F0Y2goZSl7fQogICAgfSw1MDAwKTsKICAgIGNvbnN0IGhvamU9bmV3IERhdGUoKTsKICAgIGNvbnN0IGRQVD1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMTItMTcnKS1ob2plKS84NjRlNSkpOwogICAgY29uc3QgZFZMPU1hdGgubWF4KDEsTWF0aC5jZWlsKChuZXcgRGF0ZSgnMjAyNy0wMi0xOCcpLWhvamUpLzg2NGU1KSk7CiAgICBjb25zdCBkQTM9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTA5LTE0JyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRBM2I9TWF0aC5tYXgoMSxNYXRoLmNlaWwoKG5ldyBEYXRlKCcyMDI2LTEwLTAyJyktaG9qZSkvODY0ZTUpKTsKICAgIGNvbnN0IGRSWD1NYXRoLm1heCgxLE1hdGguY2VpbCgobmV3IERhdGUoJzIwMjYtMDctMTYnKS1ob2plKS84NjRlNSkpOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DRm9yQXRpdm8oJ1BFVFI0LlNBJywzMC44NSxkUFQsJ21jLXB0LWxvYWRpbmcnLCdtYy1wdC1yZXN1bHQnLCdtYy1wdC1zdHJpa2UnLCdtYy1wdC12b2wnLCdtYy1wdC1pbmZvJywnbWMtcHQtcnQnKTt9LDYwMDApOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DRm9yQXRpdm8oJ1ZBTEUzLlNBJyw1Ny40MCxkVkwsJ21jLXZsLWxvYWRpbmcnLCdtYy12bC1yZXN1bHQnLCdtYy12bC1zdHJpa2UnLCdtYy12bC12b2wnLCdtYy12bC1pbmZvJywnbWMtdmwtcnQnKTt9LDEyMDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0JhcnJpZXIoJ0FYSUEzLlNBJyw1NC4zMSw0My41MSw2OC43NixkQTMsMCwnYXhpYTMnKTt9LDE4MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0JhcnJpZXIoJ0FYSUEzLlNBJyw1MC42NSw0MC41Miw2Mi44MSxkQTNiLDAsJ2F4aWEzYicpO30sMjQwMDApOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DUHJlZml4YWRvKCdST1hPMzQuU0EnLDEyLjg4LDEwLjUwLGRSWCwwKTt9LDMwMDAwKTsKICAgIHdpbmRvdy5faW5kTG9hZGVkPWZhbHNlOwogIH1jYXRjaChlKXtjb25zb2xlLmVycm9yKCdmZXRjaEFsbDonLGUpO30KfQpmZXRjaEFsbCgpOwpzZXRJbnRlcnZhbChmZXRjaEFsbCwxMjAwMDApOwo8L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
