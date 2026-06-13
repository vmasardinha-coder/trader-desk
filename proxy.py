"""  # v8.4
Trader Desk — Proxy Server v8.4
Indicadores tecnicos + fundamentalistas + Monte Carlo + Futuros
Mudancas v8.4:
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

# ── INDICADORES B3 — v8.4 com explicacao ─────────────
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

# ── BTC INDICATORS — v8.4 com cache ──────────────────
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

# ── BTC CYCLE — v8.4 com cache e range menor ─────────
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

# ── CALENDAR — v8.4 multi-source ─────────────────────
@app.route('/calendar', methods=['GET'])
def get_calendar():
    all_events = []
    currencies_ok = {'USD','BRL','EUR','GBP','CNY','JPY','CAD','AUD'}
    flag_map = {'USD':'🇺🇸','BRL':'🇧🇷','EUR':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳','JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺'}
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
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjEgLSAyMDI2LTA2LTEzIC0tPgo8aHRtbCBsYW5nPSJwdC1CUiI+CjxoZWFkPgo8bWV0YSBjaGFyc2V0PSJVVEYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5UcmFkZXIgRGVzazwvdGl0bGU+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDMwMDs0MDA7NjAwOzcwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQo6cm9vdHstLWJnOiMwZDBkMGQ7LS1iZzI6IzE0MTQxNDstLWJnMzojMWExYTFhOy0tdGV4dDojZThlOGU4Oy0tbXV0ZWQ6IzY2NjstLWJvcmRlcjojMjIyOy0tYWNjZW50OiNmMGE1MDA7LS1ncmVlbjojMDBjODUzOy0tcmVkOiNmZjE3NDQ7LS13YXJuOiNmZjk4MDA7LS1kYW5nZXI6I2ZmMTc0NDstLWJsdWU6IzIxOTZmMzstLWl0bTojZmY0NDQ0fQpib2R5e2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXRleHQpO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOi43NXJlbTtwYWRkaW5nOjEycHg7bWF4LXdpZHRoOjYyMHB4O21hcmdpbjowIGF1dG99Ci50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MTJweDtvdmVyZmxvdy14OmF1dG87d2hpdGUtc3BhY2U6bm93cmFwfQoudGFie3BhZGRpbmc6NnB4IDEycHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6LjZyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtmbGV4LXNocmluazowfQoudGFiLmFjdGl2ZXtiYWNrZ3JvdW5kOnZhcigtLWFjY2VudCk7Y29sb3I6IzAwMDtib3JkZXItY29sb3I6dmFyKC0tYWNjZW50KX0KLnRhYi1jb250ZW50e2Rpc3BsYXk6bm9uZX0udGFiLWNvbnRlbnQuYWN0aXZle2Rpc3BsYXk6YmxvY2t9Ci5zZWN7Zm9udC1zaXplOi41NXJlbTtsZXR0ZXItc3BhY2luZzouMTJlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6OHB4IDAgNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7bWFyZ2luLWJvdHRvbTo4cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6NnB4fQouc2VjIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50KX0uc3Jje2NvbG9yOnZhcigtLWJvcmRlcik7Zm9udC1zaXplOi41cmVtfQouZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEycHh9Ci5jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4IDhweDt0cmFuc2l0aW9uOmJvcmRlci1jb2xvciAuMTVzfS5jYXJkOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpfQouY2FyZC5ncmVlbntib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1ncmVlbil9LmNhcmQuYmx1ZXtib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1ibHVlKX0uY2FyZC53YXJue2JvcmRlci10b3A6MnB4IHNvbGlkIHZhcigtLXdhcm4pfS5jYXJkLnJlZHtib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1yZWQpfQouYy1sYWJlbHtmb250LXNpemU6LjQ4cmVtO2NvbG9yOnZhcigtLW11dGVkKTtsZXR0ZXItc3BhY2luZzouMDhlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bWFyZ2luLWJvdHRvbToycHh9Ci5jLW5hbWV7Zm9udC1zaXplOi42cmVtO2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS10ZXh0KTttYXJnaW4tYm90dG9tOjRweH0KLmMtcHJpY2V7Zm9udC1zaXplOi44NXJlbTtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KX0KLmMtcHJpY2UubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOi43cmVtfQouYy1jaGFuZ2V7Zm9udC1zaXplOi41NXJlbTttYXJnaW4tdG9wOjJweH0KLmNoZy11cHtjb2xvcjp2YXIoLS1ncmVlbil9LmNoZy1kbntjb2xvcjp2YXIoLS1yZWQpfS5jaGctZmxhdHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjR9fQoucG9zLWNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjEycHg7bWFyZ2luLWJvdHRvbTo4cHh9Ci5wb3MtbGFiZWx7Zm9udC1zaXplOi41MnJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bGV0dGVyLXNwYWNpbmc6LjA2ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NHB4fQoucG9zLXRpY2tlcntmb250LXNpemU6MS4xcmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO21hcmdpbi1ib3R0b206MnB4fQoucG9zLXByaWNle2ZvbnQtc2l6ZToxLjNyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLXRleHQpfS5wb3MtcHJpY2UubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOi45cmVtfQoucG9zLWNoZ3tmb250LXNpemU6LjY1cmVtO21hcmdpbi1ib3R0b206OHB4fQouc2J7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nLXRvcDo4cHg7bWFyZ2luLXRvcDo4cHh9Ci5zYi1yb3d7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO3BhZGRpbmc6M3B4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtmb250LXNpemU6LjZyZW19Ci5zYi1sYmx7Y29sb3I6dmFyKC0tbXV0ZWQpfS5zYi12YWx7Y29sb3I6dmFyKC0tdGV4dCk7dGV4dC1hbGlnbjpyaWdodDttYXgtd2lkdGg6NjAlfQouc2ItdmFsLm9re2NvbG9yOnZhcigtLWdyZWVuKX0uc2ItdmFsLndhcm57Y29sb3I6dmFyKC0td2Fybil9LnNiLXZhbC5pdG17Y29sb3I6dmFyKC0taXRtKX0KLnNpZ25hbHtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4O21hcmdpbi10b3A6OHB4O2JhY2tncm91bmQ6dmFyKC0tYmcpfQouc2lnLXRpdGxle2ZvbnQtc2l6ZTouNTVyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2NvbG9yOnZhcigtLW11dGVkKX0KLmluZC1ib3h7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjhweDt0ZXh0LWFsaWduOmNlbnRlcn0KLmluZC1sYmx7Zm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjRweH0KLmluZC12YWx7Zm9udC1zaXplOjFyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOnZhcigtLXRleHQpfQouaW5kLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LmluZC12YWwud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaW5kLXZhbC5kb3due2NvbG9yOnZhcigtLXJlZCl9Ci5zZWN0b3ItaGVhZGVye2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo4cHggMTRweDtjdXJzb3I6cG9pbnRlcjtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO2ZvbnQtc2l6ZTouNjVyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweH0KLnNlY3Rvci1oZWFkZXI6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zZWN0b3ItYm9keXtkaXNwbGF5Om5vbmU7cGFkZGluZy10b3A6NHB4fQoKLyogSW5kaWNhZG9yIHJvdyBjb20gZXhwbGljYcOnw6NvICovCi5pbmQtcm93e2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo4cHggMTBweDttYXJnaW4tYm90dG9tOjRweH0KLmluZC1yb3ctdG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbTozcHh9Ci5pbmQtcm93LW5vbWV7Zm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjA2ZW19Ci5pbmQtcm93LXZhbHtmb250LXNpemU6LjhyZW07Zm9udC13ZWlnaHQ6NzAwfQouaW5kLXJvdy12YWwub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5pbmQtcm93LXZhbC5kb3due2NvbG9yOnZhcigtLXJlZCl9LmluZC1yb3ctdmFsLndhcm57Y29sb3I6dmFyKC0td2Fybil9Ci5pbmQtcm93LWV4cHtmb250LXNpemU6LjUycmVtO2NvbG9yOnZhcigtLW11dGVkKTtsaW5lLWhlaWdodDoxLjR9CgovKiBTY29yZSBoZWFkZXIgKi8KLnNjb3JlLWJveHtiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTJweDttYXJnaW4tYm90dG9tOjEwcHg7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyIDFmcjtnYXA6OHB4O3RleHQtYWxpZ246Y2VudGVyfQouc2NvcmUtbnVte2ZvbnQtc2l6ZToxLjhyZW07Zm9udC13ZWlnaHQ6ODAwfQouc2NvcmUtbGJse2ZvbnQtc2l6ZTouNTVyZW07bWFyZ2luLXRvcDoycHh9Ci5zY29yZS1tZXRhe2ZvbnQtc2l6ZTouNXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbToycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi4wNmVtfQouc2NvcmUtc3Vie2ZvbnQtc2l6ZTouNXJlbTttYXJnaW4tdG9wOjJweH0KCmZvb3RlcnttYXJnaW4tdG9wOjE2cHg7cGFkZGluZy10b3A6MTJweDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2Vlbjtmb250LXNpemU6LjUycmVtO2NvbG9yOnZhcigtLW11dGVkKTtmbGV4LXdyYXA6d3JhcDtnYXA6NnB4fQo8L3N0eWxlPgo8L2hlYWQ+Cjxib2R5Pgo8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO21hcmdpbi1ib3R0b206MTJweCI+CiAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi45cmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpIj5UUkFERVIgREVTSzwvZGl2PgogIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpIiBpZD0ibGFzdC11cGRhdGUiPuKAlDwvZGl2Pgo8L2Rpdj4KPGRpdiBjbGFzcz0idGFicyI+CiAgPGRpdiBjbGFzcz0idGFiIGFjdGl2ZSIgb25jbGljaz0ic3dpdGNoVGFiKCdjb3RhY29lcycsdGhpcykiPvCfk4ogQ290YcOnw7VlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3dpdGNoVGFiKCdpbmRpY2Fkb3JlcycsdGhpcykiPvCfk4ggSW5kaWNhZG9yZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3aXRjaFRhYigncG9zaWNvZXMnLHRoaXMpIj7wn5K8IFBvc2nDp8O1ZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3aXRjaFRhYignY2FsZW5kYXJpbycsdGhpcykiPvCfk4UgQ2FsZW5kw6FyaW88L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBDT1RBw4fDlUVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWNvdGFjb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQgYWN0aXZlIj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPjAxPC9zcGFuPiBFVUEgPHNwYW4gY2xhc3M9InNyYyI+wrcgcHJveHk8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+RVMxKjwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImVzZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImVzZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5OUTwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9Im5xZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+w41uZGljZTwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+REpJPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iZGppLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iZGppLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCByZWQiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlZvbGF0aWxpZGFkZTwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+VklYPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0idml4LWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBibHVlIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5Ew7NsYXI8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkRYWTwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImR4eS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImR4eS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkPDom1iaW88L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlVTRC9CUkw8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ1c2QtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ1c2QtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj4wMjwvc3Bhbj4gQjMg4oCUIFRvcCAxMCA8c3BhbiBjbGFzcz0ic3JjIj7CtyBUcmFkaW5nVmlldzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPsONbmRpY2U8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPklCT1Y8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJpYm92LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iaWJvdi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+V0lOMSE8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ3aW4tcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ3aW4tYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+UEVUUjQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJwZXRyNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJwZXRyNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+SVRVQjQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJpdHViNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJpdHViNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+VkFMRTM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ2YWxlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ2YWxlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QkJEQzQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJiYmRjNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJiYmRjNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QUJFVjM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJhYmV2M3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJhYmV2M3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QkJBUzM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJiYmFzM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJiYmFzM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+V0VHRTM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ3ZWdlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ3ZWdlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHdhcm4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkJEUjwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+Uk9YTzM0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0icm94bzM0cS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9InJveG8zNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj7wn5OCPC9zcGFuPiBCMyBwb3IgU2VnbWVudG8gPHNwYW4gY2xhc3M9InNyYyI+wrcgY2xpcXVlIHBhcmEgZXhwYW5kaXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdmaW5hbmNlaXJvJykiPjxzcGFuPvCfj6YgRmluYW5jZWlybzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1maW5hbmNlaXJvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1maW5hbmNlaXJvIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtZmluYW5jZWlybyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdwZXRyb2xlbycpIj48c3Bhbj7wn5uiIFBldHLDs2xlbyAmYW1wOyBHw6FzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXBldHJvbGVvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1wZXRyb2xlbyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLXBldHJvbGVvIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ21pbmVyYWNhbycpIj48c3Bhbj7im48gTWluZXJhw6fDo288L3NwYW4+PHNwYW4gaWQ9InNhcnItbWluZXJhY2FvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1taW5lcmFjYW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1taW5lcmFjYW8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWF0ZXJpYWlzJykiPjxzcGFuPvCfjLIgUGFwZWwgJmFtcDsgQ2VsdWxvc2U8L3NwYW4+PHNwYW4gaWQ9InNhcnItbWF0ZXJpYWlzIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1tYXRlcmlhaXMiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1tYXRlcmlhaXMiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygndXRpbGlkYWRlJykiPjxzcGFuPuKaoSBVdGlsaWRhZGUgUMO6YmxpY2E8L3NwYW4+PHNwYW4gaWQ9InNhcnItdXRpbGlkYWRlIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS11dGlsaWRhZGUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC11dGlsaWRhZGUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnY29uc3Vtb19jaWNsaWNvJykiPjxzcGFuPvCfm40gQ29uc3VtbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1jb25zdW1vX2NpY2xpY28iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWNvbnN1bW9fY2ljbGljbyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWNvbnN1bW9fY2ljbGljbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdjb25zdW1vX25hbycpIj48c3Bhbj7wn5uSIENvbnN1bW8gTsOjbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1jb25zdW1vX25hbyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktY29uc3Vtb19uYW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1jb25zdW1vX25hbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdzYXVkZScpIj48c3Bhbj7wn4+lIFNhw7pkZTwvc3Bhbj48c3BhbiBpZD0ic2Fyci1zYXVkZSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktc2F1ZGUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1zYXVkZSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdpbmR1c3RyaWFpcycpIj48c3Bhbj7wn4+XIEJlbnMgSW5kdXN0cmlhaXM8L3NwYW4+PHNwYW4gaWQ9InNhcnItaW5kdXN0cmlhaXMiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWluZHVzdHJpYWlzIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtaW5kdXN0cmlhaXMiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygndGlfdGVsZWNvbScpIj48c3Bhbj7wn5K7IFRJICZhbXA7IENvbXVuaWNhw6fDtWVzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXRpX3RlbGVjb20iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LXRpX3RlbGVjb20iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC10aV90ZWxlY29tIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuPvCfh7rwn4e4PC9zcGFuPiBFVUEgcG9yIFNlZ21lbnRvPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdtYWc3JykiPjxzcGFuPuKtkCA3IE1hZ27DrWZpY2FzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1hZzciPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LW1hZzciPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1tYWc3Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ25hc2RhcTE1JykiPjxzcGFuPvCfkrsgTmFzZGFxIFRvcCAxNTwvc3Bhbj48c3BhbiBpZD0ic2Fyci1uYXNkYXExNSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktbmFzZGFxMTUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1uYXNkYXExNSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdzcDIwJykiPjxzcGFuPvCfk4ogUyZhbXA7UCA1MDAgVG9wIDIwPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXNwMjAiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LXNwMjAiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1zcDIwIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ2RqaTIwJykiPjxzcGFuPvCfj5sgRG93IEpvbmVzIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0ic2Fyci1kamkyMCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktZGppMjAiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1kamkyMCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj4wMzwvc3Bhbj4gQ29tbW9kaXRpZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+UGV0csOzbGVvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5XVEkvQ0w8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJjbC1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkdPTEQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJnb2xkLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3YXJuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+U0lMVkVSPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0ic2lsdmVyLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3YXJuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+Q09QUEVSPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iY29wcGVyLXAiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+MDQ8L3NwYW4+IEJpdGNvaW48L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+U3BvdDwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QlRDL1VTRDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImJ0Yy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImJ0Yy1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJUQyBSU0k8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtcnNpIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RnVuZGluZzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QlRDIFJhdGU8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtZnVuZCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZlYXIgJmFtcDsgR3JlZWQ8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkluZGV4PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iZmctdmFsIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImZnLWxibCI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGZvb3Rlcj48c3BhbiBpZD0iZm9vdGVyLXRpbWUiPuKAlDwvc3Bhbj48c3Bhbj5UcmFkZXIgRGVzayB2MTAuMTwvc3Bhbj48L2Zvb3Rlcj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBJTkRJQ0FET1JFUyDilZDilZAgLS0+CjxkaXYgaWQ9InRhYi1pbmRpY2Fkb3JlcyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPvCfk4o8L3NwYW4+IENpY2xvIEJpdGNvaW48L2Rpdj4KICA8ZGl2IGlkPSJidGMtY3ljbGUtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4O2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvIGNpY2xvIEJUQy4uLjwvZGl2PjwvZGl2PgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIGF1dG87Z2FwOjEwcHg7bWFyZ2luOjEycHggMDthbGlnbi1pdGVtczpzdGFydCI+CiAgICA8ZGl2IGlkPSJmZWFyLWdyZWVkLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTBweCI+Q2FycmVnYW5kbyBGZWFyICZhbXA7IEdyZWVkLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTRweDttaW4td2lkdGg6MTIwcHg7dGV4dC1hbGlnbjpjZW50ZXIiPgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjZweCI+QlRDL1VTRDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtaW5kLXByaWNlIj7igJQ8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJidGMtaW5kLWNoZyI+4oCUPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPvCfk4o8L3NwYW4+IEluZGljYWRvcmVzIEJUQyBTZW1hbmFsPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBQRVRSNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3BldHI0JykiPuKGuyByZWNhcnJlZ2FyPC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InBldHI0LWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBWQUxFMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3ZhbGUzJykiPuKGuyByZWNhcnJlZ2FyPC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InZhbGUzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBCQkFTMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ2JiYXMzJykiPuKGuyByZWNhcnJlZ2FyPC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9ImJiYXMzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBBWElBMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ2F4aWEzJykiPuKGuyByZWNhcnJlZ2FyPC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9ImF4aWEzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KCiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBST1hPMzQgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOi41NXJlbSIgb25jbGljaz0icmVsb2FkSW5kKCdyb3hvMzQnKSI+4oa7IHJlY2FycmVnYXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0icm94bzM0LWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KPC9kaXY+Cgo8IS0tIOKVkOKVkCBQT1NJw4fDlUVTIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLXBvc2ljb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+MDE8L3NwYW4+IE9wZXJhw6fDtWVzIEF0aXZhczwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIj4KICAgIDxkaXYgY2xhc3M9InBvcy1sYWJlbCI+UGV0cm9icmFzIFBOIMK3IENhbGwgVmVuZGlkYSDCtyBQRVRSTDMxOSDCtyBWZW5jIDE3LzEyLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPlBFVFI0PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHJpY2UgbG9hZGluZyIgaWQ9InB0LXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0icHQtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDMwLDg1PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDMwLDg1IChQRVRSTDMxOSk8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gYW8gc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0icHQtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNy8xMi8yMDI2IMK3IDxzcGFuIGlkPSJwdC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjQzLDQlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DICh2b2wuaGlzdC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiIgaWQ9Im1jLXB0LXJlYWx0aW1lIj44LDMlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIEImYW1wO1MgKHZvbC5pbXBsLik8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj45LDQlPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdGl0bGUiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gY2FpciBhbyBzdHJpa2U8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcHQtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtIj5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXB0LXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLXRvcDo2cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UHJvYi4gY2FpciBhbyBzdHJpa2U8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtcHQtc3RyaWtlIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1wdC12b2wiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NHB4IiBpZD0ibWMtcHQtaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxhYmVsIj5WYWxlIE9OIMK3IENhbGwgVmVuZGlkYSDCtyBWQUxFQjU3NCDCtyBWZW5jIDE4LzAyLzIwMjc8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPlZBTEUzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHJpY2UgbG9hZGluZyIgaWQ9InZsLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0idmwtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDU3LDQwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDU3LDQwIChWQUxFQjU3NCk8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gYW8gc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0idmwtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xOC8wMi8yMDI3IMK3IDxzcGFuIGlkPSJ2bC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjcxLDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DICh2b2wuaGlzdC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiIgaWQ9Im1jLXZsLXJlYWx0aW1lIj4xMSw1JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Qcm9iLiBCJmFtcDtTICh2b2wuaW1wbC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+MTQsMiU8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWlyIGFvIHN0cmlrZTwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy12bC1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW0iPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtdmwtcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Qcm9iLiBjYWlyIGFvIHN0cmlrZTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy12bC1zdHJpa2UiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLXZsLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo0cHgiIGlkPSJtYy12bC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6MTBweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGFiZWwiPkFYSUEzIChBKSDCtyBCaWRpcmVjaW9uYWwgwrcgVmVuYyAxNC8wOS8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIj5BWElBMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXByaWNlIGxvYWRpbmciIGlkPSJheGlhMy1wb3MtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icG9zLWNoZyIgaWQ9ImF4aWEzLXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gUmVmLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCA1NCwzMTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgNDMsNTE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S1VPICgrMjYsNiUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgNjgsNzY8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+R2FuaG8gcy8gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+YXTDqSArMzEsMiUgLyArMjAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIGMvIGJhci4gYWx0YTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPis0JSBmaXhvPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MTQvMDkvMjAyNiDCtyA8c3BhbiBpZD0iYXhpYTNmLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+MzUsMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gTUMvQiZhbXA7Uzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj42OCw1JSAvIDczLDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMta2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzLWt1by1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMtc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBDZW7DoXJpb3M8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtYXhpYTMtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtIj5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzLXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLXRvcDo2cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+U2VtIEJhcnJlaXJhIOKchTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy1heGlhMy1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhMy1rdW8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIGRvd24iIGlkPSJtYy1heGlhMy1rZG8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLWF4aWEzLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo0cHgiIGlkPSJtYy1heGlhMy1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6MTBweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGFiZWwiPkFYSUEzIChCKSDCtyBCaWRpcmVjaW9uYWwgSU9OIEl0YcO6IMK3IFZlbmMgMDIvMTAvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciI+QVhJQTM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wcmljZSBsb2FkaW5nIiBpZD0iYXhpYTNiLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0iYXhpYTNiLXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gUmVmLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCA1MCw2NTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgNDAsNTI8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S1VPICgrMjQlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDYyLDgxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4rNCUgZml4byAoMTIsMzMlIGEuYS4pPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MDIvMTAvMjAyNiDCtyA8c3BhbiBpZD0iYXhpYTNiLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+MzUsMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gTUMvQiZhbXA7Uzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj42OCw1JSAvIDczLDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTNiLWtkby1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhM2Ita3VvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhM2Itc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBDZW7DoXJpb3M8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtYXhpYTNiLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbSI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhM2ItcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLWF4aWEzYi1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhM2Ita3VvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBkb3duIiBpZD0ibWMtYXhpYTNiLWtkbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTNiLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo0cHgiIGlkPSJtYy1heGlhM2ItaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxhYmVsIj5ST1hPMzQgwrcgQkRSIE51YmFuayDCtyBQcmVmaXhhZG8gYy8gQmFycmVpcmEgwrcgVmVuYyAxNi8wNy8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIj5ST1hPMzQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wcmljZSBsb2FkaW5nIiBpZD0icm94bzM0LXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0icm94bzM0LXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gUmVmLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCAxMiw4ODwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TdHJpa2UgUk9YT0cxMDU8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCAxMCw1MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjE2LzA3LzIwMjYgwrcgPHNwYW4gaWQ9InJveG8zNC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjM5LDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DL0ImYW1wO1M8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj40MywyJSAvIDQ3LDElPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJyb3hvMzQta2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJyb3hvMzQtc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBzdWNlc3NvPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXJveG8zNC1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW0iPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcm94bzM0LXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLXRvcDo2cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UHJvYi4gU3VjZXNzbzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy1yb3hvMzQtc3VjZXNzbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5DYWxsIEV4ZXJjaWRhPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCIgaWQ9Im1jLXJveG8zNC1jYWxsIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPktETyBBdGluZ2lkbzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwiIGlkPSJtYy1yb3hvMzQta2RvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1yb3hvMzQtdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjRweCIgaWQ9Im1jLXJveG8zNC1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxzcGFuPvCfk4E8L3NwYW4+IEVuY2VycmFkYXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im9wYWNpdHk6LjY1O2JvcmRlci1jb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+QkJBUzM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TdHJpa2UgQkJBU0gyMTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCAyMSw2NSDCtyBSZWYgUiQgMjAsNjc8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSA4MCUgZG8gYWx2byBlbSA3MCUgZG8gcHJhem88L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im9wYWNpdHk6LjY1O2JvcmRlci1jb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+QVhJQTMgU2hvcnQgU3RyYW5nbGU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5DYWxsIFYuIEFYSUFJNTA1PC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDUwLDUwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj7inIUgQcOnw7VlcyBsaWJlcmFkYXM8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im9wYWNpdHk6LjY1O2JvcmRlci1jb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiPgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+Uk9YTzM0IFByZWZpeGFkbyA3LDElPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RW5jZXJyYWRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjA0LzA2LzIwMjY8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSB+NSwxNyUgKDcyJSBkbyBhbHZvKTwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjwhLS0g4pWQ4pWQIENBTEVORMOBUklPIOKVkOKVkCAtLT4KPGRpdiBpZD0idGFiLWNhbGVuZGFyaW8iIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjEycHgiPgogICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi42cmVtO2NvbG9yOnZhcigtLW11dGVkKSI+8J+HuvCfh7gg8J+Hp/Cfh7cg8J+HqvCfh7og8J+HrPCfh6cg8J+HqPCfh7Mg8J+Hr/Cfh7Ug8J+HqPCfh6Yg8J+HpvCfh7ogwrcgSW1wYWN0IE1lZGl1bSs8L2Rpdj4KICAgIDxidXR0b24gb25jbGljaz0ibG9hZENhbGVuZGFyKCkiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1hY2NlbnQpO2NvbG9yOnZhcigtLWFjY2VudCk7cGFkZGluZzo0cHggMTBweDtmb250LXNpemU6LjZyZW07Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdCI+4oa7IEF0dWFsaXphcjwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgaWQ9ImNhbGVuZGFyLXN0YXR1cyIgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206OHB4O21pbi1oZWlnaHQ6MTZweCI+PC9kaXY+CiAgPGRpdiBpZD0iY2FsZW5kYXItYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoyMHB4O3RleHQtYWxpZ246Y2VudGVyIj5DbGlxdWUgZW0gQXR1YWxpemFyPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgQkFTRT0naHR0cHM6Ly90cmFkZXItZGVzay5vbnJlbmRlci5jb20nOwpjb25zdCBTRUc9ewogICdmaW5hbmNlaXJvJzpbJ0lUVUI0JywnQkJEQzQnLCdCQkFTMycsJ1NBTkIxMScsJ0IzU0EzJywnQlBBQzExJywnSVRTQTQnLCdCUlNSNicsJ0FCQ0I0JywnQk1HQjQnXSwKICAncGV0cm9sZW8nOlsnUEVUUjQnLCdQRVRSMycsJ1BSSU8zJywnQlJBVjMnLCdWQkJSMycsJ0NTQU4zJywnUkVDVjMnLCdVR1BBMycsJ1NFUUwzJywnRU5BVDMnXSwKICAnbWluZXJhY2FvJzpbJ1ZBTEUzJywnR0dCUjQnLCdDU05BMycsJ1VTSU01JywnQlJBUDQnLCdGRVNBNCcsJ0NNSU4zJywnQ0JBVjMnLCdHT0FVNCcsJ1BHTU4zJ10sCiAgJ21hdGVyaWFpcyc6WydTVVpCMycsJ0tMQk4xMScsJ0RYQ08zJywnVU5JUDYnLCdSQU5JMycsJ09SVlIzJywnU01UTzMnLCdGUkFTMycsJ0xQU0IzJywnRFRFWDMnXSwKICAndXRpbGlkYWRlJzpbJ0FYSUEzJywnRVFUTDMnLCdDUEZFMycsJ1NCU1AzJywnQ01JRzQnLCdFTkdJMTEnLCdUQUVFMTEnLCdBVVJFMycsJ0VHSUUzJywnQ1BMRTMnXSwKICAnY29uc3Vtb19jaWNsaWNvJzpbJ1JFTlQzJywnTFJFTjMnLCdNR0xVMycsJ0NZUkUzJywnTVJWRTMnLCdBWlpBMycsJ1ZJVkEzJywnU0JGRzMnLCdDVkNCMycsJ0xXU0EzJ10sCiAgJ2NvbnN1bW9fbmFvJzpbJ0FCRVYzJywnSkJTUzMnLCdCUkZTMycsJ05BVFUzJywnTURJQTMnLCdCRUVGMycsJ1NMQ0UzJywnTVRSRTMnLCdDQU1MMycsJ1BDQVIzJ10sCiAgJ3NhdWRlJzpbJ1JET1IzJywnSEFQVjMnLCdGTFJZMycsJ0RBU0EzJywnUVVBTDMnLCdPTkNPMycsJ1BOVkwzJywnT0RQVjMnLCdNQVREMycsJ0FBTFIzJ10sCiAgJ2luZHVzdHJpYWlzJzpbJ1dFR0UzJywnRU1CUjMnLCdSQUlMMycsJ1RHTUEzJywnUk9NSTMnLCdWTElEMycsJ1RVUFkzJywnSVJCUjMnLCdQT01PNCcsJ0ZSQVMzJ10sCiAgJ3RpX3RlbGVjb20nOlsnVklWVDMnLCdUSU1TMycsJ1RPVFZTMycsJ09JQlIzJywnTFdTQTMnLCdNTEFTMycsJ0FOSU0zJywnUE9TSTMnLCdJTlRCMycsJ0JSSVQzJ10sCn07CmNvbnN0IFVTX1NFRz17CiAgJ21hZzcnOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ0dPT0dMJywnTUVUQScsJ1RTTEEnXSwKICAnbmFzZGFxMTUnOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQ09TVCcsJ05GTFgnLCdRQ09NJywnQU1EJywnQURCRScsJ0lOVEMnLCdDU0NPJ10sCiAgJ3NwMjAnOlsnQUFQTCcsJ01TRlQnLCdOVkRBJywnQU1aTicsJ01FVEEnLCdHT09HTCcsJ1RTTEEnLCdBVkdPJywnQlJLLkInLCdKUE0nLCdMTFknLCdWJywnVU5IJywnWE9NJywnTUEnLCdORkxYJywnUEcnLCdKTkonLCdIRCcsJ0JBQyddLAogICdkamkyMCc6WydVTkgnLCdHUycsJ0hEJywnU0hXJywnQ0FUJywnQVhQJywnTUNEJywnQU1HTicsJ1YnLCdUUlYnLCdJQk0nLCdKUE0nLCdIT04nLCdDUk0nLCdDVlgnLCdBQVBMJywnTVNGVCcsJ0RJUycsJ05LRScsJ0JBJ10KfTsKY29uc3QgZkJSTD12PT52IT1udWxsPydSJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmVVNEPXY9PnYhPW51bGw/J1VTJCAnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttaW5pbXVtRnJhY3Rpb25EaWdpdHM6MixtYXhpbXVtRnJhY3Rpb25EaWdpdHM6Mn0pOifigJQnOwpjb25zdCBmUFRTPXY9PnYhPW51bGw/TnVtYmVyKHYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSk6J+KAlCc7CmZ1bmN0aW9uIHNldEVsKGlkLHR4dCl7Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoIWUpcmV0dXJuO2UudGV4dENvbnRlbnQ9dHh0O2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KZnVuY3Rpb24gc2V0Q2hnKGlkLG5vdyxwcmV2LHR5cGUpe2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKCFlKXJldHVybjtjb25zdCBkaWZmPW5vdy1wcmV2O2NvbnN0IHBjdD0oZGlmZi9NYXRoLmFicyhwcmV2fHwxKSoxMDApLnRvRml4ZWQoMik7Y29uc3Qgc2lnbj1kaWZmPj0wPycrJzonJztpZih0eXBlPT09J2JybCcpZS50ZXh0Q29udGVudD1zaWduKydSJCAnK01hdGguYWJzKGRpZmYpLnRvRml4ZWQoMikrJyAoJytzaWduK3BjdCsnJSknO2Vsc2UgaWYodHlwZT09PSd1c2QnKWUudGV4dENvbnRlbnQ9c2lnbitkaWZmLnRvRml4ZWQoMikrJyAoJytzaWduK3BjdCsnJSknO2Vsc2UgZS50ZXh0Q29udGVudD1zaWduK01hdGguYWJzKGRpZmYpLnRvTG9jYWxlU3RyaW5nKCdwdC1CUicse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJyAoJytzaWduK3BjdCsnJSknO2UuY2xhc3NOYW1lPSdjLWNoYW5nZSAnKyhkaWZmPjA/J2NoZy11cCc6ZGlmZjwwPydjaGctZG4nOidjaGctZmxhdCcpO30KZnVuY3Rpb24gc3dpdGNoVGFiKHRhYixlbCl7ZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYicpLmZvckVhY2godD0+dC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7ZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnRhYi1jb250ZW50JykuZm9yRWFjaCh0PT50LmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndGFiLScrdGFiKS5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTtpZihlbCllbC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTtpZih0YWI9PT0naW5kaWNhZG9yZXMnJiYhd2luZG93Ll9pbmRMb2FkZWQpe3dpbmRvdy5faW5kTG9hZGVkPXRydWU7bG9hZEluZGljYXRvcnMoKTt9aWYodGFiPT09J2NhbGVuZGFyaW8nKWxvYWRDYWxlbmRhcigpO30KZnVuY3Rpb24gdG9nZ2xlU2VnKGlkKXtjb25zdCBiPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYm9keS0nK2lkKTtjb25zdCBhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYXJyLScraWQpO2lmKCFiKXJldHVybjtjb25zdCBvcGVuPWIuc3R5bGUuZGlzcGxheSE9PSdibG9jayc7Yi5zdHlsZS5kaXNwbGF5PW9wZW4/J2Jsb2NrJzonbm9uZSc7aWYoYSlhLnRleHRDb250ZW50PW9wZW4/J+KWsic6J+KWvCc7aWYob3BlbiYmIWIuZGF0YXNldC5sb2FkZWQpe2IuZGF0YXNldC5sb2FkZWQ9JzEnO2xvYWRTZWdtZW50KGlkKTt9fQoKYXN5bmMgZnVuY3Rpb24gbG9hZFNlZ21lbnQoaWQpewogIGNvbnN0IGdyaWQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NncmlkLScraWQpO2lmKCFncmlkKXJldHVybjsKICBjb25zdCBwZng9aWQrJ19fJzsKICBpZihVU19TRUdbaWRdKXsKICAgIGNvbnN0IHRrcz1VU19TRUdbaWRdOwogICAgZ3JpZC5pbm5lckhUTUw9dGtzLm1hcCh0PT57Y29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTtyZXR1cm4gJzxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+VVM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPicrdCsnPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iJytwZngrdGlkKydfcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSInK3BmeCt0aWQrJ19jIj7igJQ8L2Rpdj48L2Rpdj4nO30pLmpvaW4oJycpOwogICAgdHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL3VzL3F1b3Rlcz90aWNrZXJzPScrdGtzLmpvaW4oJywnKSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7T2JqZWN0LmVudHJpZXMoZCkuZm9yRWFjaCgoW3Qsdl0pPT57Y29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTtjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfcCcpO2NvbnN0IGVjPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHBmeCt0aWQrJ19jJyk7aWYoZXAmJnYucHJpY2Upe2VwLnRleHRDb250ZW50PSckJytOdW1iZXIodi5wcmljZSkudG9GaXhlZCgyKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fWlmKGVjJiZ2LnByaWNlJiZ2LnByZXYpc2V0Q2hnKHBmeCt0aWQrJ19jJyx2LnByaWNlLHYucHJldiwndXNkJyk7fSk7fWNhdGNoKGUpe30KICAgIHJldHVybjsKICB9CiAgY29uc3QgdGtzPVNFR1tpZF07aWYoIXRrcylyZXR1cm47CiAgZ3JpZC5pbm5lckhUTUw9dGtzLm1hcCh0PT57Y29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTtyZXR1cm4gJzxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iJytwZngrdGlkKydfYyI+4oCUPC9kaXY+PC9kaXY+Jzt9KS5qb2luKCcnKTsKICB0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzLm1hcCh0PT4nQk1GQk9WRVNQQTonK3QpfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpOyhkLmRhdGF8fFtdKS5mb3JFYWNoKHg9Pntjb25zdCB0PXgucy5yZXBsYWNlKCdCTUZCT1ZFU1BBOicsJycpLnRvTG93ZXJDYXNlKCk7Y29uc3RbYyxjYV09eC5kfHxbXTtpZihjIT1udWxsKXtjb25zdCBlcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdCsnX3AnKTtpZihlcCl7ZXAudGV4dENvbnRlbnQ9ZkJSTChjKTtlcC5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fXNldENoZyhwZngrdCsnX2MnLGMsYy0oY2F8fDApLCdicmwnKTt9fSk7fWNhdGNoKGUpe30KfQoKYXN5bmMgZnVuY3Rpb24gZmV0Y2hITCgpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkLkJUQ3x8MCk7aWYoYnA+MCl7c2V0RWwoJ2J0Yy1wJyxmVVNEKGJwKSk7c2V0Q2hnKCdidGMtYycsYnAsYnAqMC45OSwndXNkJyk7fXRyeXtjb25zdCByMj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcycsZGV4Oid4eXonfSl9KTtpZihyMi5vayl7Y29uc3QgZDI9YXdhaXQgcjIuanNvbigpO2lmKGQyWyd4eXo6Q0wnXSlzZXRFbCgnY2wtcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDTCddKS50b0ZpeGVkKDIpKTtpZihkMlsneHl6OkdPTEQnXSlzZXRFbCgnZ29sZC1wJywnJCcrTnVtYmVyKGQyWyd4eXo6R09MRCddKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTtpZihkMlsneHl6OlNJTFZFUiddKXNldEVsKCdzaWx2ZXItcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpTSUxWRVInXSkudG9GaXhlZCgyKSk7aWYoZDJbJ3h5ejpDT1BQRVInXSlzZXRFbCgnY29wcGVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q09QUEVSJ10pLnRvRml4ZWQoMykpO319Y2F0Y2goZSl7fX1jYXRjaChlKXt9fQphc3luYyBmdW5jdGlvbiBmZXRjaFRWKCl7Y29uc3Qgb3V0PXt9O3RyeXtjb25zdCB0a3M9WydCTUZCT1ZFU1BBOlBFVFI0JywnQk1GQk9WRVNQQTpJVFVCNCcsJ0JNRkJPVkVTUEE6VkFMRTMnLCdCTUZCT1ZFU1BBOkJCREM0JywnQk1GQk9WRVNQQTpBQkVWMycsJ0JNRkJPVkVTUEE6QkJBUzMnLCdCTUZCT1ZFU1BBOldFR0UzJywnQk1GQk9WRVNQQTpJQk9WJ107Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvdHYvYnJhemlsJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6dGtzfSxjb2x1bW5zOlsnY2xvc2UnLCdjaGFuZ2VfYWJzJ119KX0pO2lmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7KGQuZGF0YXx8W10pLmZvckVhY2goeD0+e2NvbnN0W2MsY2FdPXguZHx8W107aWYoYyE9bnVsbClvdXRbeC5zXT17cDpjLHY6Yy0oY2F8fDApfTt9KTt9fWNhdGNoKGUpe310cnl7Y29uc3QgcnI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYocnIub2spe2NvbnN0IGRkPWF3YWl0IHJyLmpzb24oKTtpZihkZC5wcmVjb19hdHVhbCl7c2V0RWwoJ3JveG8zNHEtcCcsZkJSTChkZC5wcmVjb19hdHVhbCkpO3NldENoZygncm94bzM0cS1jJyxkZC5wcmVjb19hdHVhbCxkZC5wcmVjb19hbnRlcmlvcnx8ZGQucHJlY29fYXR1YWwqMC45OSwnYnJsJyk7fX19Y2F0Y2goZSl7fXJldHVybiBvdXQ7fQphc3luYyBmdW5jdGlvbiBmZXRjaEZ1dHVyZXMoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvZnV0dXJlcycpO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hGdW5kaW5nKCl7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vZmFwaS5iaW5hbmNlLmNvbS9mYXBpL3YxL3ByZW1pdW1JbmRleD9zeW1ib2w9QlRDVVNEVCcpO2lmKHIub2spe2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7c2V0RWwoJ2J0Yy1mdW5kJywocGFyc2VGbG9hdChkLmxhc3RGdW5kaW5nUmF0ZXx8MCkqMTAwKS50b0ZpeGVkKDQpKyclJyk7cmV0dXJuO319Y2F0Y2goZSl7fXRyeXtjb25zdCByMj1hd2FpdCBmZXRjaChCQVNFKycvYmluYW5jZS9mdW5kaW5nJyk7aWYoIXIyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIyLmpzb24oKTtpZihkLmxhc3RGdW5kaW5nUmF0ZSlzZXRFbCgnYnRjLWZ1bmQnLChwYXJzZUZsb2F0KGQubGFzdEZ1bmRpbmdSYXRlKSoxMDApLnRvRml4ZWQoNCkrJyUnKTt9Y2F0Y2goZSl7fX0KCmZ1bmN0aW9uIGRvTWFjcm8odHYsZnV0dXJlcyl7CiAgY29uc3QgaWJEPXR2WydCTUZCT1ZFU1BBOklCT1YnXTtpZihpYkQpe3NldEVsKCdpYm92LXAnLGZQVFMoaWJELnApKTtzZXRDaGcoJ2lib3YtYycsaWJELnAsaWJELnYsJ3B0cycpO30KICBbWydQRVRSNCcsJ3BldHI0cSddLFsnSVRVQjQnLCdpdHViNHEnXSxbJ1ZBTEUzJywndmFsZTNxJ10sWydCQkRDNCcsJ2JiZGM0cSddLFsnQUJFVjMnLCdhYmV2M3EnXSxbJ0JCQVMzJywnYmJhczNxJ10sWydXRUdFMycsJ3dlZ2UzcSddXS5mb3JFYWNoKChbdCxpZF0pPT57Y29uc3QgZD10dlsnQk1GQk9WRVNQQTonK3RdO2lmKGQpe3NldEVsKGlkKyctcCcsZkJSTChkLnApKTtzZXRDaGcoaWQrJy1jJyxkLnAsZC52LCdicmwnKTt9fSk7CiAgaWYoZnV0dXJlcyl7Y29uc3QgZj1mdXR1cmVzO2NvbnN0IGFmPShpZCx2YWwpPT57Y29uc3QgZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7aWYoZSl7ZS50ZXh0Q29udGVudD12YWw7ZS5jbGFzc0xpc3QucmVtb3ZlKCdsb2FkaW5nJyk7fX07CiAgICBpZihmLmRqaT8ucHJpY2Upe2FmKCdkamktcCcsZlBUUyhmLmRqaS5wcmljZSkpO3NldENoZygnZGppLWMnLGYuZGppLnByaWNlLGYuZGppLnByZXYsJ3B0cycpO30KICAgIGlmKGYuZXNmPy5wcmljZSl7YWYoJ2VzZi1wJyxmUFRTKGYuZXNmLnByaWNlKSk7c2V0Q2hnKCdlc2YtYycsZi5lc2YucHJpY2UsZi5lc2YucHJldiwncHRzJyk7fQogICAgaWYoZi5ucWY/LnByaWNlKXthZignbnFmLXAnLGZQVFMoZi5ucWYucHJpY2UpKTtzZXRDaGcoJ25xZi1jJyxmLm5xZi5wcmljZSxmLm5xZi5wcmV2LCdwdHMnKTt9CiAgICBpZihmLndpbj8ucHJpY2Upe2FmKCd3aW4tcCcsZlBUUyhmLndpbi5wcmljZSkpO3NldENoZygnd2luLWMnLGYud2luLnByaWNlLGYud2luLnByZXYsJ3B0cycpO30KICAgIGlmKGYudml4Py5wcmljZSl7YWYoJ3ZpeC1wJyxOdW1iZXIoZi52aXgucHJpY2UpLnRvRml4ZWQoMikpO3NldENoZygndml4LWMnLGYudml4LnByaWNlLGYudml4LnByZXYsJ3VzZCcpO30KICAgIGlmKGYuZHh5Py5wcmljZSl7YWYoJ2R4eS1wJyxOdW1iZXIoZi5keHkucHJpY2UpLnRvRml4ZWQoMikpO3NldENoZygnZHh5LWMnLGYuZHh5LnByaWNlLGYuZHh5LnByZXYsJ3VzZCcpO30KICAgIGlmKGYudXNkPy5wcmljZSl7YWYoJ3VzZC1wJyxmQlJMKGYudXNkLnByaWNlKSk7c2V0Q2hnKCd1c2QtYycsZi51c2QucHJpY2UsZi51c2QucHJldnx8Zi51c2QucHJpY2UsJ2JybCcpO30KICB9Cn0KCmZ1bmN0aW9uIGRvUG9zaXRpb25zKHR2KXsKICBjb25zdCBwdEQ9dHZbJ0JNRkJPVkVTUEE6UEVUUjQnXTtjb25zdCBwdFA9cHREPy5wfHw0MCxwdFY9cHREPy52fHw0MDsKICBzZXRFbCgncHQtcG9zLXAnLGZCUkwocHRQKSk7c2V0Q2hnKCdwdC1wb3MtYycscHRQLHB0ViwnYnJsJyk7CiAgc2V0RWwoJ3B0LWl0bScsJytSJCAnKyhwdFAtMzAuODUpLnRvRml4ZWQoMikrJyBhY2ltYSBkbyBzdHJpa2UnKTsKICBjb25zdCB2bEQ9dHZbJ0JNRkJPVkVTUEE6VkFMRTMnXTtjb25zdCB2bFA9dmxEPy5wfHw3OCx2bFY9dmxEPy52fHw3ODsKICBzZXRFbCgndmwtcG9zLXAnLGZCUkwodmxQKSk7c2V0Q2hnKCd2bC1wb3MtYycsdmxQLHZsViwnYnJsJyk7CiAgc2V0RWwoJ3ZsLWl0bScsJytSJCAnKyh2bFAtNTcuNDApLnRvRml4ZWQoMikrJyBhY2ltYSBkbyBzdHJpa2UnKTsKICBjb25zdCBjZD0oZHMsZWlkKT0+e2NvbnN0IHY9bmV3IERhdGUoZHMpO2NvbnN0IGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKTtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVpZCk7aWYoZSllLnRleHRDb250ZW50PWQ7fTsKICBjZCgnMjAyNi0xMi0xNycsJ3B0LWRpYXMnKTtjZCgnMjAyNy0wMi0xOCcsJ3ZsLWRpYXMnKTtjZCgnMjAyNi0wOS0xNCcsJ2F4aWEzZi1kaWFzJyk7Y2QoJzIwMjYtMTAtMDInLCdheGlhM2ItZGlhcycpO2NkKCcyMDI2LTA3LTE2Jywncm94bzM0LWRpYXMnKTsKICBzZXRUaW1lb3V0KGFzeW5jKCk9Pnt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy9BWElBMy5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByZWNvX2F0dWFsKXJldHVybjtjb25zdCBwPWQucHJlY29fYXR1YWw7c2V0RWwoJ2F4aWEzLXBvcy1wJyxmQlJMKHApKTtzZXRFbCgnYXhpYTNiLXBvcy1wJyxmQlJMKHApKTtjb25zdCBrZG9BPTQzLjUxLGt1b0E9NjguNzYsa2RvQj00MC41MixrdW9CPTYyLjgxO2NvbnN0IGRBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1rZG8tZGlzdCcpO2lmKGRBKWRBLnRleHRDb250ZW50PSgocC1rZG9BKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nO2NvbnN0IHVBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1rdW8tZGlzdCcpO2lmKHVBKXVBLnRleHRDb250ZW50PSgoa3VvQS1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJztjb25zdCBzQT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTMtc3RhdHVzJyk7aWYoc0Epe3NBLnRleHRDb250ZW50PXA8PWtkb0E/J/CflLQgS0RPIEFUSU5HSURPJzpwPj1rdW9BPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQS5jbGFzc05hbWU9J3NiLXZhbCAnKyhwPD1rZG9BfHxwPj1rdW9BPyd3YXJuJzonb2snKTt9Y29uc3QgZEI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1rZG8tZGlzdCcpO2lmKGRCKWRCLnRleHRDb250ZW50PSgocC1rZG9CKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nO2NvbnN0IHVCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhM2Ita3VvLWRpc3QnKTtpZih1Qil1Qi50ZXh0Q29udGVudD0oKGt1b0ItcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7Y29uc3Qgc0I9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1zdGF0dXMnKTtpZihzQil7c0IudGV4dENvbnRlbnQ9cDw9a2RvQj8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1b0I/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NCLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PWtkb0J8fHA+PWt1b0I/J3dhcm4nOidvaycpO319Y2F0Y2goZSl7fX0sMjAwMCk7CiAgc2V0VGltZW91dChhc3luYygpPT57dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJlY29fYXR1YWwpcmV0dXJuO2NvbnN0IHA9ZC5wcmVjb19hdHVhbDtzZXRFbCgncm94bzM0LXBvcy1wJyxmQlJMKHApKTtjb25zdCBkZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm94bzM0LWtkby1kaXN0Jyk7aWYoZGUpZGUudGV4dENvbnRlbnQ9KChwLTEwLjUwKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkYSBiYXJyZWlyYSc7Y29uc3Qgc2U9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JveG8zNC1zdGF0dXMnKTtpZihzZSl7c2UudGV4dENvbnRlbnQ9cDw9MTAuNTA/J/CflLQgQkFSUkVJUkEgQVRJTkdJREEnOifinIUgQWNpbWEgZGEgYmFycmVpcmEnO3NlLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PTEwLjUwPydpdG0nOidvaycpO319Y2F0Y2goZSl7fX0sMzAwMCk7Cn0KCi8vIOKUgOKUgCBNb250ZSBDYXJsbyDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKYXN5bmMgZnVuY3Rpb24gcnVuTUNGb3JBdGl2byh0aWNrZXIsc3RyaWtlLGRpYXMsbG9hZElkLHJlc0lkLHN0cmlrZUlkLHZvbElkLGluZm9JZCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO2NvbnN0IHRvPXNldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeSh7dGlja2VyLGtfY2FsbDpzdHJpa2Usa19wdXQ6c3RyaWtlLHRfZGF5czpkaWFzLG46NTAwMH0pfSk7Y2xlYXJUaW1lb3V0KHRvKTtpZighci5vayl0aHJvdyAwO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoZC5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZC5lcnJvcik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQobG9hZElkKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChyZXNJZCkuc3R5bGUuZGlzcGxheT0nYmxvY2snO2NvbnN0IHByb2I9TnVtYmVyKGQucHJvYl9wdXRfZXhlcmNpZGF8fDApO2NvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChzdHJpa2VJZCk7c0VsLnRleHRDb250ZW50PXByb2IudG9GaXhlZCgyKSsnJSc7c0VsLmNsYXNzTmFtZT0naW5kLXZhbCAnKyhwcm9iPjMwPydvayc6cHJvYj4xNT8nd2Fybic6J2Rvd24nKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCh2b2xJZCkudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaW5mb0lkKS50ZXh0Q29udGVudD0nVm9sLmhpc3QuICcrZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSDCtyBNQyB2cyBCJlMgdXNhbSB2b2xhdGlsaWRhZGVzIGRpZmVyZW50ZXMg4oCUIHZlciBwb3Npw6fDo28nO31jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChsb2FkSWQpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCdpbmRpc3BvbsOtdmVsJyk7fX0KYXN5bmMgZnVuY3Rpb24gcnVuTUNCYXJyaWVyKHRpY2tlcixlbnRyeSxrZG8sa3VvLGRpYXMscHJpY2UscHJlZml4KXtwcmVmaXg9cHJlZml4fHwnYXhpYTMnO3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApO2NvbnN0IGJvZHk9e3RpY2tlcixlbnRyeSxrZG8sa3VvLHRfZGF5czpkaWFzLG46MzAwMH07aWYocHJpY2U+MClib2R5LnByaWNlPXByaWNlO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL21vbnRlY2FybG8vYmFycmllcicse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeShib2R5KX0pO2NsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1yZXN1bHQnKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kyctbm9icicpLnRleHRDb250ZW50PWQucHJvYl9zZW1fYmFycmVpcmEudG9GaXhlZCgyKSsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kycta3VvJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2FsdGEudG9GaXhlZCgyKSsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kycta2RvJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2JhaXhhLnRvRml4ZWQoMikrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLXZvbCcpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWluZm8nKS50ZXh0Q29udGVudD0nUHJlw6dvIFIkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua2RvKycgwrcgS1VPIFIkICcrZC5rdW8rJyDCtyAnK2QuY2VuYXJpb3MudG9Mb2NhbGVTdHJpbmcoKSsnIGNlbsOhcmlvcyc7fWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwnaW5kaXNwb27DrXZlbCcpO319CmFzeW5jIGZ1bmN0aW9uIHJ1bk1DUHJlZml4YWRvKHRpY2tlcixlbnRyeSxrZG8sZGlhcyxwcmljZSl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO2NvbnN0IHRvPXNldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7Y29uc3QgYm9keT17dGlja2VyLGtfY2FsbDplbnRyeSxrX3B1dDplbnRyeSx0X2RheXM6ZGlhcyxrbm9ja19kb3duOmtkbyxuOjUwMDB9O2lmKHByaWNlPjApYm9keS5wcmljZT1wcmljZTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KGJvZHkpfSk7Y2xlYXJUaW1lb3V0KHRvKTtpZighci5vayl0aHJvdyAwO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoZC5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZC5lcnJvcik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1sb2FkaW5nJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1yZXN1bHQnKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7Y29uc3Qgc0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtc3VjZXNzbycpO3NFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX3N1Y2Vzc28pLnRvRml4ZWQoMikrJyUnO3NFbC5jbGFzc05hbWU9J2luZC12YWwgJysoZC5wcm9iX3N1Y2Vzc28+NzA/J29rJzpkLnByb2Jfc3VjZXNzbz41MD8nd2Fybic6J2Rvd24nKTtjb25zdCBjRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1jYWxsJyk7aWYoY0VsKWNFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX2NhbGxfZXhlcmNpZGEpLnRvRml4ZWQoMikrJyUnO2NvbnN0IGtFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWtkbycpO2lmKGtFbClrRWwudGV4dENvbnRlbnQ9ZC5wcm9iX2tkb19hdGluZ2lkbyE9bnVsbD9OdW1iZXIoZC5wcm9iX2tkb19hdGluZ2lkbykudG9GaXhlZCgyKSsnJSc6J+KAlCc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC12b2wnKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWluZm8nKS50ZXh0Q29udGVudD0nUHJlw6dvIFIkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua25vY2tfZG93bisnIMK3ICcrZC5jZW5hcmlvcy50b0xvY2FsZVN0cmluZygpKycgY2Vuw6FyaW9zJzt9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1sb2FkaW5nJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J2luZGlzcG9uw612ZWwnKTt9fQoKLy8g4pSA4pSAIEluZGljYWRvcmVzIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAphc3luYyBmdW5jdGlvbiBmZXRjaEluZGljYXRvcnModGlja2VyKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDMwMDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9pbmRpY2F0b3JzLycrdGlja2VyLHtzaWduYWw6Y3RybC5zaWduYWx9KTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZldGNoQlRDSW5kaWNhdG9ycygpe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMTUwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2J0Yy9pbmRpY2F0b3JzJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEJUQ0N5Y2xlKCl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO3NldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwxNTAwMCk7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvYnRjL2N5Y2xlJyx7c2lnbmFsOmN0cmwuc2lnbmFsfSk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEZlYXJHcmVlZCgpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9mZWFyZ3JlZWQnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTtjb25zdCB2PWQudmFsdWV8fDUwO2NvbnN0IGNscz12PD0yNT8ndmFyKC0tcmVkKSc6djw9NDU/J3ZhcigtLXdhcm4pJzp2PD03NT8ndmFyKC0tYWNjZW50KSc6J3ZhcigtLWdyZWVuKSc7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ZlYXItZ3JlZWQtYXJlYScpO2lmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHgiPjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206OHB4Ij7wn5ixIEZlYXIgJiBHcmVlZCBJbmRleDwvZGl2PjxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEycHgiPjxkaXYgc3R5bGU9ImZvbnQtc2l6ZToycmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjonK2NscysnIj4nK3YrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouODVyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOicrY2xzKyciPicrKGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKSsnPC9kaXY+PC9kaXY+PC9kaXY+JztzZXRFbCgnZmctdmFsJyxTdHJpbmcodikpO3NldEVsKCdmZy1sYmwnLGQudmFsdWVfY2xhc3NpZmljYXRpb258fCdOZXV0cm8nKTt0cnl7Y29uc3QgcmI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnfSl9KTtpZihyYi5vayl7Y29uc3QgZGI9YXdhaXQgcmIuanNvbigpO2NvbnN0IGJwPXBhcnNlRmxvYXQoZGIuQlRDfHwwKTtpZihicD4wKXtzZXRFbCgnYnRjLWluZC1wcmljZScsZlVTRChicCkpO3NldEVsKCdidGMtcCcsZlVTRChicCkpO319fWNhdGNoKGUyKXt9fWNhdGNoKGUpe319CgovLyDilIDilIAgcmVuZGVySW5kaWNhdG9ycyBjb20gZXhwbGljYcOnw6NvIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgApmdW5jdGlvbiByZW5kZXJJbmRpY2F0b3JzKGFyZWFJZCxkYXRhLHNob3dBbGwpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGFyZWFJZCk7aWYoIWVsKXJldHVybjsKICBpZighZGF0YSl7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS13YXJuKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTJweCI+4o+zIFNlbSByZXNwb3N0YSDigJQgY2xpcXVlIOKGuyByZWNhcnJlZ2FyPC9kaXY+JztyZXR1cm47fQogIGlmKGRhdGEuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tZGFuZ2VyKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTJweCI+4pqgICcrZGF0YS5lcnJvcisnPGJyPjxzbWFsbCBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj5DbGlxdWUg4oa7IHBhcmEgdGVudGFyIG5vdmFtZW50ZTwvc21hbGw+PC9kaXY+JztyZXR1cm47fQogIGNvbnN0IGluZHM9ZGF0YS5pbmRpY2Fkb3Jlc3x8W107CiAgY29uc3Qgc2NvcmU9ZGF0YS5zY29yZV90b3RhbDsKICBjb25zdCBwcmVjbz1kYXRhLnByZWNvX2F0dWFsOwogIGNvbnN0IGdyYWhhbT1kYXRhLmdyYWhhbV92YWx1ZTsKICBjb25zdCB1cHNpZGU9ZGF0YS51cHNpZGVfZ3JhaGFtOwogIGNvbnN0IHNldG9yPWRhdGEuc2V0b3J8fCcnOwogIGxldCBodG1sPScnOwoKICAvLyBTY29yZSBoZWFkZXIKICBpZihzY29yZSE9bnVsbCl7CiAgICBjb25zdCBzYz1OdW1iZXIoc2NvcmUpOwogICAgY29uc3Qgc2NvcmVDb2xvcj1zYz49NjU/J3ZhcigtLWdyZWVuKSc6c2M+PTQwPyd2YXIoLS13YXJuKSc6J3ZhcigtLXJlZCknOwogICAgY29uc3Qgc2NvcmVMYWJlbD1zYz49NjU/J0NvbXByYSDilrInOnNjPj00MD8nTmV1dHJvIOKGkic6J1ZlbmRhIOKWvCc7CiAgICBodG1sKz0nPGRpdiBjbGFzcz0ic2NvcmUtYm94Ij4nKwogICAgICAnPGRpdj48ZGl2IGNsYXNzPSJzY29yZS1tZXRhIj5TY29yZTwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLW51bSIgc3R5bGU9ImNvbG9yOicrc2NvcmVDb2xvcisnIj4nK3NjKyc8L2Rpdj48ZGl2IGNsYXNzPSJzY29yZS1sYmwiIHN0eWxlPSJjb2xvcjonK3Njb3JlQ29sb3IrJyI+JytzY29yZUxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgICAnPGRpdj48ZGl2IGNsYXNzPSJzY29yZS1tZXRhIj5Db3Rhw6fDo288L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6MXJlbTtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tdGV4dCk7bWFyZ2luLXRvcDo0cHgiPicrKHByZWNvPydSJCAnK051bWJlcihwcmVjbykudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXN1YiI+JytzZXRvcisnPC9kaXY+PC9kaXY+JysKICAgICAgJzxkaXY+PGRpdiBjbGFzcz0ic2NvcmUtbWV0YSI+R3JhaGFtPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOjFyZW07Zm9udC13ZWlnaHQ6NzAwO21hcmdpbi10b3A6NHB4O2NvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyhncmFoYW0/J1IkICcrTnVtYmVyKGdyYWhhbSkudG9GaXhlZCgyKTon4oCUJykrJzwvZGl2PjxkaXYgY2xhc3M9InNjb3JlLXN1YiIgc3R5bGU9ImNvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cHNpZGUhPW51bGw/KHVwc2lkZT4wPycrJzonJykrdXBzaWRlKyclJzon4oCUJykrJzwvZGl2PjwvZGl2PicrCiAgICAgICc8L2Rpdj4nOwogIH0KCiAgLy8gSW5kaWNhZG9yZXMgY29tIGV4cGxpY2HDp8OjbwogIGNvbnN0IGxpc3RhPXNob3dBbGw/aW5kczppbmRzLnNsaWNlKDAsMTApOwogIGxpc3RhLmZvckVhY2goZnVuY3Rpb24oaSl7CiAgICBjb25zdCBzPWkuc2luYWx8fGkuc2lnbmFsfHwnJzsKICAgIGNvbnN0IGNscz1zPT09J0FsdGEnfHxzPT09J1NvYnJldmVuZGEnPydvayc6cz09PSdCYWl4YSd8fHM9PT0nU29icmVjb21wcmEnPydkb3duJzond2Fybic7CiAgICBjb25zdCBhcnJvdz1zPT09J0FsdGEnfHxzPT09J1NvYnJldmVuZGEnPyfilrInOnM9PT0nQmFpeGEnfHxzPT09J1NvYnJlY29tcHJhJz8n4pa8Jzon4oaSJzsKICAgIGNvbnN0IHZhbENvbG9yPSd2YXIoLS0nKyhjbHM9PT0nb2snPydncmVlbic6Y2xzPT09J2Rvd24nPydyZWQnOid3YXJuJykrJyknOwogICAgaHRtbCs9JzxkaXYgY2xhc3M9ImluZC1yb3ciPicrCiAgICAgICc8ZGl2IGNsYXNzPSJpbmQtcm93LXRvcCI+JysKICAgICAgICAnPHNwYW4gY2xhc3M9ImluZC1yb3ctbm9tZSI+JysoaS5ub21lfHxpLm5hbWV8fCcnKSsnPC9zcGFuPicrCiAgICAgICAgJzxzcGFuIGNsYXNzPSJpbmQtcm93LXZhbCAnK2NscysnIj4nKyhpLnZhbG9yIT1udWxsP2kudmFsb3I6J+KAlCcpKycgJythcnJvdysnPC9zcGFuPicrCiAgICAgICc8L2Rpdj4nOwogICAgaWYoaS5leHBsaWNhY2FvKXsKICAgICAgaHRtbCs9JzxkaXYgY2xhc3M9ImluZC1yb3ctZXhwIj4nK2kuZXhwbGljYWNhbysnPC9kaXY+JzsKICAgIH0KICAgIGh0bWwrPSc8L2Rpdj4nOwogIH0pOwoKICBlbC5pbm5lckhUTUw9aHRtbDsKfQoKZnVuY3Rpb24gcmVuZGVyQlRDSW5kaWNhdG9ycyhkYXRhKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWluZC1hcmVhJyk7aWYoIWVsfHwhZGF0YSlyZXR1cm47CiAgaWYoZGF0YS5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS13YXJuKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTBweCI+4o+zICcrZGF0YS5lcnJvcisnIOKAlCBhZ3VhcmRlIG91IHJlY2FycmVndWUgYSBhYmE8L2Rpdj4nO3JldHVybjt9CiAgbGV0IGh0bWw9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4Ij4nOwogIGlmKGRhdGEucnNpX3NlbWFuYWwhPW51bGwpewogICAgY29uc3Qgcj1kYXRhLnJzaV9zZW1hbmFsOwogICAgY29uc3QgY2xzPXI8MzA/J29rJzpyPjcwPydkb3duJzond2Fybic7CiAgICBjb25zdCBleHA9cjwzMD8nU29icmV2ZW5kYSDimqEg4oCUIHBvdGVuY2lhbCByZXZlcnPDo28gZGUgYWx0YSc6cj43MD8nU29icmVjb21wcmEg4pqgIOKAlCByaXNjbyBkZSBjb3JyZcOnw6NvJzonWm9uYSBuZXV0cmEnOwogICAgaHRtbCs9JzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCAnK2NscysnIj4nK3IudG9GaXhlZCgxKSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZXhwKyc8L2Rpdj48L2Rpdj4nOwogICAgc2V0RWwoJ2J0Yy1yc2knLHIudG9GaXhlZCgxKSk7CiAgfQogIGlmKGRhdGEubW0yMDBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gMjAwIHNlbS48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPiQnK051bWJlcihkYXRhLm1tMjAwX3NlbWFuYWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkrJzwvZGl2PjwvZGl2Pic7CiAgZWxzZSBpZihkYXRhLm1tNTBfc2VtYW5hbClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gNTAgc2VtLjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JCcrTnVtYmVyKGRhdGEubW01MF9zZW1hbmFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nOwogIGlmKGRhdGEubWFjZF9oaXN0b2dyYW0hPW51bGwpe2NvbnN0IG1oPWRhdGEubWFjZF9oaXN0b2dyYW07aHRtbCs9JzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk1BQ0QgSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsICcrKG1oPjA/J29rJzonZG93bicpKyciPicrTnVtYmVyKG1oKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQ1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JysobWg+MD8nTW9tZW50dW0gYWx0YSDilrInOidNb21lbnR1bSBiYWl4YSDilrwnKSsnPC9kaXY+PC9kaXY+Jzt9CiAgaWYoZGF0YS5vYnZfdHJlbmQpaHRtbCs9JzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk9CViBUcmVuZDwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysoZGF0YS5vYnZfdHJlbmQ9PT0nc3ViaW5kbyc/J29rJzonZG93bicpKyciPicrZGF0YS5vYnZfdHJlbmQrJzwvZGl2PjwvZGl2Pic7CiAgaHRtbCs9JzwvZGl2Pic7CiAgZWwuaW5uZXJIVE1MPWh0bWw7CiAgaWYoZGF0YS5wcmljZSl7c2V0RWwoJ2J0Yy1pbmQtcHJpY2UnLCckJytOdW1iZXIoZGF0YS5wcmljZSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7fQp9CgpmdW5jdGlvbiByZW5kZXJCVENDeWNsZShkKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWN5Y2xlLWFyZWEnKTtpZighZWx8fCFkfHxkLmVycm9yKXJldHVybjsKICBjb25zdCBmVT12PT52PyckJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KTon4oCUJzsKICBlbC5pbm5lckhUTUw9CiAgICAnPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLWJvdHRvbTo4cHgiPicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TVZSViBaLVNjb3JlPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCAnKyhkLm12cnZfenNjb3JlPy52YWx1ZTwxPydvayc6ZC5tdnJ2X3pzY29yZT8udmFsdWU8Mz8nd2Fybic6J2Rvd24nKSsnIj4nK2QubXZydl96c2NvcmU/LnZhbHVlKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQ1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjNweCI+JytkLm12cnZfenNjb3JlPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5OVVBMPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nKygoZC5udXBsPy52YWx1ZXx8MCkqMTAwKS50b0ZpeGVkKDApKyclPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5udXBsPy5sYWJlbCsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5QdWVsbCBNdWx0aXBsZTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JytkLnB1ZWxsPy52YWx1ZSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrZC5wdWVsbD8ubGFiZWwrJzwvZGl2PjwvZGl2PicrCiAgICAnPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+MjAwVyBNQSAocHJveHkpPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nK2ZVKGQubWEyMDB3KSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDozcHgiPicrKGQubWEyMDB3X3BjdD8nKycrKGQubWEyMDB3X3BjdCkrJyUgYWNpbWEnOicnKSsnPC9kaXY+PC9kaXY+JysKICAgICc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5SYWluYm93IEJhbmQ8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrKGQucmFpbmJvdz8uYmFuZHx8J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgJzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlBpIEN5Y2xlIERpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayI+JytmVShkLnBpX2N5Y2xlPy5kaXN0YW5jZSkrJzwvZGl2PjwvZGl2PicrCiAgICAnPC9kaXY+JysKICAgICc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6OHB4O2ZvbnQtc2l6ZTouNnJlbTtjb2xvcjp2YXIoLS1hY2NlbnQpIj4nKyhkLnBpX2N5Y2xlPy5zaWduYWx8fCcnKSsnPC9kaXY+JzsKfQoKYXN5bmMgZnVuY3Rpb24gbG9hZEluZGljYXRvcnMoKXsKICAvLyBCVEMgY29tIHRpbWVvdXQgZGUgMTVzCiAgY29uc3Qgd2l0aFRpbWVvdXQ9KHAsbXMsZmIpPT5Qcm9taXNlLnJhY2UoW3AsbmV3IFByb21pc2Uocj0+c2V0VGltZW91dCgoKT0+cihmYiksbXMpKV0pOwogIGNvbnN0W2J0YyxjeWNsZV09YXdhaXQgUHJvbWlzZS5hbGwoWwogICAgd2l0aFRpbWVvdXQoZmV0Y2hCVENJbmRpY2F0b3JzKCksMTUwMDAse2Vycm9yOidUaW1lb3V0IDE1cyDigJQgdGVudGUgcmVjYXJyZWdhciBhIGFiYSd9KSwKICAgIHdpdGhUaW1lb3V0KGZldGNoQlRDQ3ljbGUoKSwxNTAwMCx7ZXJyb3I6J1RpbWVvdXQgMTVzJ30pCiAgXSk7CiAgcmVuZGVyQlRDSW5kaWNhdG9ycyhidGMpO3JlbmRlckJUQ0N5Y2xlKGN5Y2xlKTtmZXRjaEZlYXJHcmVlZCgpOwogIC8vIFN0b2NrcyBCMyBlbSBwYXJhbGVsbwogIGNvbnN0IHN0b2Nrcz1bWydQRVRSNC5TQScsJ3BldHI0LWluZC1hcmVhJ10sWydWQUxFMy5TQScsJ3ZhbGUzLWluZC1hcmVhJ10sWydCQkFTMy5TQScsJ2JiYXMzLWluZC1hcmVhJ10sWydBWElBMy5TQScsJ2F4aWEzLWluZC1hcmVhJ10sWydST1hPMzQuU0EnLCdyb3hvMzQtaW5kLWFyZWEnXV07CiAgY29uc3QgcmVzdWx0cz1hd2FpdCBQcm9taXNlLmFsbChzdG9ja3MubWFwKChbdF0pPT53aXRoVGltZW91dChmZXRjaEluZGljYXRvcnModCksMzAwMDAse2Vycm9yOidUaW1lb3V0IDMwcyd9KSkpOwogIHN0b2Nrcy5mb3JFYWNoKChbLGFyZWFJZF0saSk9PnJlbmRlckluZGljYXRvcnMoYXJlYUlkLHJlc3VsdHNbaV0sdHJ1ZSkpOwp9Cgphc3luYyBmdW5jdGlvbiByZWxvYWRJbmQodGlja2VyKXsKICBjb25zdCBhcmVhSWQ9dGlja2VyKyctaW5kLWFyZWEnOwogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGFyZWFJZCk7CiAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDFzIGluZmluaXRlIj5DYXJyZWdhbmRvICcrdGlja2VyLnRvVXBwZXJDYXNlKCkrJy4uLjwvZGl2Pic7CiAgY29uc3QgdGlja2VyTWFwPXsncGV0cjQnOidQRVRSNC5TQScsJ3ZhbGUzJzonVkFMRTMuU0EnLCdiYmFzMyc6J0JCQVMzLlNBJywnYXhpYTMnOidBWElBMy5TQScsJ3JveG8zNCc6J1JPWE8zNC5TQSd9OwogIGNvbnN0IGQ9YXdhaXQgZmV0Y2hJbmRpY2F0b3JzKHRpY2tlck1hcFt0aWNrZXJdfHx0aWNrZXIudG9VcHBlckNhc2UoKSsnLlNBJyk7CiAgcmVuZGVySW5kaWNhdG9ycyhhcmVhSWQsZCx0cnVlKTsKfQoKLy8g4pSA4pSAIENhbGVuZMOhcmlvIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgApjb25zdCBDQUxfRkxBR1M9eydVU0QnOifwn4e68J+HuCcsJ0JSTCc6J/Cfh6fwn4e3JywnRVVSJzon8J+HqvCfh7onLCdHQlAnOifwn4es8J+HpycsJ0NOWSc6J/Cfh6jwn4ezJywnSlBZJzon8J+Hr/Cfh7UnLCdDQUQnOifwn4eo8J+HpicsJ0FVRCc6J/Cfh6bwn4e6J307CmFzeW5jIGZ1bmN0aW9uIGxvYWRDYWxlbmRhcigpewogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYWxlbmRhci1hcmVhJyk7CiAgY29uc3Qgc3Q9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbGVuZGFyLXN0YXR1cycpOwogIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoyMHB4O3RleHQtYWxpZ246Y2VudGVyO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlIj5DYXJyZWdhbmRvIGNhbGVuZMOhcmlvLi4uPC9kaXY+JzsKICBpZihzdClzdC50ZXh0Q29udGVudD0nQnVzY2FuZG8gZXZlbnRvcyBlY29uw7RtaWNvcy4uLic7CiAgdHJ5ewogICAgY29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7CiAgICBzZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjAwMDApOwogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvY2FsZW5kYXInLHtzaWduYWw6Y3RybC5zaWduYWx9KTsKICAgIGlmKCFyLm9rKXRocm93IG5ldyBFcnJvcignSFRUUCAnK3Iuc3RhdHVzKTsKICAgIGNvbnN0IGV2ZW50cz1hd2FpdCByLmpzb24oKTsKICAgIGlmKHN0KXN0LnRleHRDb250ZW50PWV2ZW50cy5sZW5ndGg+MD9ldmVudHMubGVuZ3RoKycgZXZlbnRvcyBlbmNvbnRyYWRvcyc6J+KAlCc7CiAgICBpZighZXZlbnRzfHwhZXZlbnRzLmxlbmd0aCl7CiAgICAgIGVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0icGFkZGluZzoyMHB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LWFsaWduOmNlbnRlciI+JysKICAgICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi45cmVtO21hcmdpbi1ib3R0b206OHB4Ij7wn5OFPC9kaXY+JysKICAgICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi42NXJlbSI+U2VtIGV2ZW50b3MgZGlzcG9uw612ZWlzIGVzdGEgc2VtYW5hPC9kaXY+JysKICAgICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTttYXJnaW4tdG9wOjZweDtjb2xvcjp2YXIoLS1ib3JkZXIpIj5Gb250ZTogRm9yZXggRmFjdG9yeSDCtyBUcmFkaW5nVmlldzwvZGl2PicrCiAgICAgICc8L2Rpdj4nOwogICAgICByZXR1cm47CiAgICB9CiAgICBjb25zdCBieURhdGU9e307CiAgICBldmVudHMuZm9yRWFjaChlPT57Y29uc3QgZHQ9KGUuZGF0ZXx8JycpLnNsaWNlKDAsMTApO2lmKCFieURhdGVbZHRdKWJ5RGF0ZVtkdF09W107YnlEYXRlW2R0XS5wdXNoKGUpO30pOwogICAgbGV0IGh0bWw9Jyc7CiAgICBPYmplY3Qua2V5cyhieURhdGUpLnNvcnQoKS5mb3JFYWNoKGR0PT57CiAgICAgIGNvbnN0IGQ9bmV3IERhdGUoZHQrJ1QxMjowMDowMCcpOwogICAgICBjb25zdCBsYWJlbD1kLnRvTG9jYWxlRGF0ZVN0cmluZygncHQtQlInLHt3ZWVrZGF5OidzaG9ydCcsZGF5OicyLWRpZ2l0Jyxtb250aDonc2hvcnQnfSk7CiAgICAgIGh0bWwrPSc8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPvCfk4U8L3NwYW4+ICcrbGFiZWwrJzwvZGl2PicrCiAgICAgICAgJzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7bWFyZ2luLWJvdHRvbTo4cHgiPic7CiAgICAgIGJ5RGF0ZVtkdF0uZm9yRWFjaChlPT57CiAgICAgICAgY29uc3QgZmxhZz1lLmZsYWd8fENBTF9GTEFHU1tlLmNvdW50cnldfHwn8J+MkCc7CiAgICAgICAgY29uc3QgaW1wPWUuaW1wb3J0YW5jZXx8MTsKICAgICAgICBjb25zdCBpbXBDb2xvcj1pbXA+PTM/J3ZhcigtLXJlZCknOmltcD49Mj8ndmFyKC0td2FybiknOid2YXIoLS1tdXRlZCknOwogICAgICAgIGNvbnN0IGFjdHVhbENvbG9yPWUuc2lnbmFsPT09J2JlYXQnPyd2YXIoLS1ncmVlbiknOmUuc2lnbmFsPT09J21pc3MnPyd2YXIoLS1yZWQpJzondmFyKC0tYWNjZW50KSc7CiAgICAgICAgY29uc3QgYWN0dWFsPWUuYWN0dWFsPyc8YiBzdHlsZT0iY29sb3I6JythY3R1YWxDb2xvcisnIj4nK2UuYWN0dWFsKyc8L2I+JzonPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4oCUPC9zcGFuPic7CiAgICAgICAgaHRtbCs9JzxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjZweDtwYWRkaW5nOjZweCAxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOi42cmVtIj4nKwogICAgICAgICAgJzxzcGFuPicrZmxhZysnPC9zcGFuPicrCiAgICAgICAgICAnPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTttaW4td2lkdGg6NDBweCI+JysoZS50aW1lfHwnRGlhIHRvZG8nKSsnPC9zcGFuPicrCiAgICAgICAgICAnPHNwYW4gc3R5bGU9ImZsZXg6MTtjb2xvcjp2YXIoLS10ZXh0KSI+JysoZS5ldmVudHx8JycpKyc8L3NwYW4+JysKICAgICAgICAgICc8c3BhbiBzdHlsZT0iY29sb3I6JytpbXBDb2xvcisnO21pbi13aWR0aDoxNnB4Ij4nKyfil48nLnJlcGVhdChNYXRoLm1pbihpbXAsMykpKyc8L3NwYW4+JysKICAgICAgICAgICc8c3BhbiBzdHlsZT0ibWluLXdpZHRoOjUwcHg7dGV4dC1hbGlnbjpyaWdodCI+JythY3R1YWwrJzwvc3Bhbj4nKwogICAgICAgICAgJzxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7bWluLXdpZHRoOjQ1cHg7dGV4dC1hbGlnbjpyaWdodCI+JysoZS5mb3JlY2FzdHx8J+KAlCcpKyc8L3NwYW4+JysKICAgICAgICAnPC9kaXY+JzsKICAgICAgfSk7CiAgICAgIGh0bWwrPSc8L2Rpdj4nOwogICAgfSk7CiAgICBlbC5pbm5lckhUTUw9aHRtbDsKICB9Y2F0Y2goZSl7CiAgICBpZihzdClzdC50ZXh0Q29udGVudD0nRXJybyBhbyBjYXJyZWdhcic7CiAgICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLWRhbmdlcik7cGFkZGluZzoyMHB4O3RleHQtYWxpZ246Y2VudGVyIj4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi42NXJlbSI+JysoKGUubmFtZT09PSdBYm9ydEVycm9yJyk/J1RpbWVvdXQg4oCUIHNlcnZpZG9yIGRlbW9yYW5kbywgdGVudGUgbm92YW1lbnRlJzonRXJybyBhbyBjYXJyZWdhciBjYWxlbmTDoXJpbycpKyc8L2Rpdj4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHgiPkNsaXF1ZSBlbSBBdHVhbGl6YXIgcGFyYSB0ZW50YXIgbm92YW1lbnRlPC9kaXY+JysKICAgICc8L2Rpdj4nOwogIH0KfQoKLy8g4pSA4pSAIE1haW4gbG9vcCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKYXN5bmMgZnVuY3Rpb24gZmV0Y2hBbGwoKXsKICB0cnl7CiAgICBjb25zdFssdHYsZnV0dXJlc109YXdhaXQgUHJvbWlzZS5hbGwoW2ZldGNoSEwoKSxmZXRjaFRWKCksZmV0Y2hGdXR1cmVzKCldKTsKICAgIGNvbnN0IG5vdz1uZXcgRGF0ZSgpLnRvTG9jYWxlVGltZVN0cmluZygncHQtQlInKTsKICAgIHNldEVsKCdsYXN0LXVwZGF0ZScsJ0F0dWFsaXphZG8gJytub3cpO3NldEVsKCdmb290ZXItdGltZScsbm93KTsKICAgIGRvTWFjcm8odHYsZnV0dXJlcyk7ZG9Qb3NpdGlvbnModHYpOwogICAgc2V0VGltZW91dChmZXRjaEZ1bmRpbmcsMzAwMCk7CiAgICBzZXRUaW1lb3V0KGFzeW5jKCk9PnsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0W2IsY3ljXT1hd2FpdCBQcm9taXNlLmFsbChbZmV0Y2hCVENJbmRpY2F0b3JzKCksZmV0Y2hCVENDeWNsZSgpXSk7CiAgICAgICAgaWYoYilyZW5kZXJCVENJbmRpY2F0b3JzKGIpO2lmKGN5YylyZW5kZXJCVENDeWNsZShjeWMpO2ZldGNoRmVhckdyZWVkKCk7CiAgICAgIH1jYXRjaChlKXt9CiAgICB9LDUwMDApOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DRm9yQXRpdm8oJ1BFVFI0LlNBJywzMC44NSwxOTUsJ21jLXB0LWxvYWRpbmcnLCdtYy1wdC1yZXN1bHQnLCdtYy1wdC1zdHJpa2UnLCdtYy1wdC12b2wnLCdtYy1wdC1pbmZvJyk7fSw2MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0ZvckF0aXZvKCdWQUxFMy5TQScsNTcuNDAsMjU4LCdtYy12bC1sb2FkaW5nJywnbWMtdmwtcmVzdWx0JywnbWMtdmwtc3RyaWtlJywnbWMtdmwtdm9sJywnbWMtdmwtaW5mbycpO30sMTIwMDApOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DQmFycmllcignQVhJQTMuU0EnLDU0LjMxLDQzLjUxLDY4Ljc2LDEwMSw1NC4zMSwnYXhpYTMnKTt9LDE4MDAwKTsKICAgIHNldFRpbWVvdXQoKCk9PntydW5NQ0JhcnJpZXIoJ0FYSUEzLlNBJyw1MC42NSw0MC41Miw2Mi44MSwxMTksNTAuNjUsJ2F4aWEzYicpO30sMjQwMDApOwogICAgc2V0VGltZW91dCgoKT0+e3J1bk1DUHJlZml4YWRvKCdST1hPMzQuU0EnLDEyLjg4LDEwLjUwLDQxLDEyLjg4KTt9LDMwMDAwKTsKICAgIHdpbmRvdy5faW5kTG9hZGVkPWZhbHNlOwogIH1jYXRjaChlKXtjb25zb2xlLmVycm9yKCdmZXRjaEFsbDonLGUpO30KfQpmZXRjaEFsbCgpOwpzZXRJbnRlcnZhbChmZXRjaEFsbCwxMjAwMDApOwo8L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+Cg==").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
