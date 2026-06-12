"""  # v8.3
Trader Desk — Proxy Server v8.3
Indicadores tecnicos + fundamentalistas + Monte Carlo + Futuros
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import math
import time

# Pre-import numpy at startup to avoid timeout on first call
try:
    import numpy as _np
    _NUMPY = True
except ImportError:
    _NUMPY = False

app = Flask(__name__)
_IND_CACHE = {}  # cache indicadores
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

# ── HARDCODED FUNDAMENTAIS (atualizar trimestralmente) ─
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
        # Serie 4389 = CDI diario em % ao dia
        r = requests.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.4389/dados/ultimos/1?formato=json', timeout=5)
        if r.ok:
            cdi_d = float(r.json()[0]['valor'])  # ex: 0.0416 (% ao dia)
            cdi_anual = ((1 + cdi_d/100)**252 - 1)*100
            # Sanity check: CDI anual deve estar entre 5% e 20%
            if 5 <= cdi_anual <= 20:
                return round(cdi_anual, 2)
    except: pass
    # Fallback: CDI atual aproximado maio/2026
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
        ms=[]; 
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

# ── SINAL ────────────────────────────────────────────
def sinal(ind, cdi):
    sc=mx=0; det=[]
    p=ind.get('price',0)
    setor=ind.get('setor',SETORES['DEFAULT'])

    def add(pts, max_pts, status, txt):
        nonlocal sc,mx
        sc+=pts; mx+=max_pts
        det.append({'status':status,'texto':txt})

    r=ind.get('rsi')
    if r is not None:
        if r<30:   add(2,2,'buy',f'RSI {r} — Sobrevenda ⚡')
        elif r<45: add(1,2,'neutral',f'RSI {r} — Levemente favoravel')
        elif r>70: add(-1,2,'sell',f'RSI {r} — Sobrecompra ⚠')
        else:      add(0,2,'neutral',f'RSI {r} — Zona neutra')

    m200=ind.get('mm200')
    if m200 and p:
        if p>m200: add(2,2,'buy',f'Acima MM200 ({m200:.2f}) — Tendencia alta ✅')
        else:      add(-1,2,'sell',f'Abaixo MM200 ({m200:.2f}) — Tendencia baixa')

    m50=ind.get('mm50')
    if m50 and p:
        if p>m50: add(1,1,'buy',f'Acima MM50 ({m50:.2f}) ✅')
        else:     add(0,1,'sell',f'Abaixo MM50 ({m50:.2f})')

    m20=ind.get('mm20')
    if m20 and p:
        if p>m20: add(1,1,'buy',f'Acima MM20 ({m20:.2f}) ✅')
        else:     add(0,1,'neutral',f'Abaixo MM20 ({m20:.2f}) — Correcao CP')

    mh=ind.get('macd_histogram')
    if mh is not None:
        if mh>0: add(1,1,'buy',f'MACD histograma positivo ({mh:.3f}) — Momentum alta')
        else:    add(0,1,'sell',f'MACD histograma negativo ({mh:.3f}) — Momentum baixa')

    bu=ind.get('bb_upper'); bl=ind.get('bb_lower')
    if bu and bl and p:
        if p<=bl:  add(1,1,'buy',f'Abaixo Banda Inf Bollinger ({bl:.2f}) — Sobrevenda')
        elif p>=bu:add(0,1,'sell',f'Acima Banda Sup Bollinger ({bu:.2f}) — Sobrecompra')
        else:      add(0,1,'neutral',f'Dentro das Bandas Bollinger')

    ot=ind.get('obv_trend')
    if ot:
        if ot=='subindo': add(1,1,'buy','OBV subindo — Volume confirma tendencia ✅')
        else:             add(0,1,'sell','OBV caindo — Volume diverge')

    pl=ind.get('pl'); pl_s=setor.get('pl_medio',12)
    if pl and pl>0:
        if pl<pl_s*0.7:   add(2,2,'buy',f'P/L {pl:.1f}x — Muito barato vs setor ({pl_s}x) ✅✅')
        elif pl<pl_s:     add(1,2,'buy',f'P/L {pl:.1f}x — Abaixo do setor ({pl_s}x) ✅')
        elif pl>pl_s*1.5: add(-1,2,'sell',f'P/L {pl:.1f}x — Caro vs setor ({pl_s}x)')
        else:             add(0,2,'neutral',f'P/L {pl:.1f}x — Proximo da media ({pl_s}x)')

    pvp=ind.get('pvp'); pvp_s=setor.get('pvp_medio',2)
    if pvp and pvp>0:
        if pvp<1.0:    add(1,1,'buy',f'P/VP {pvp:.2f}x — Abaixo do patrimonio ✅')
        elif pvp<pvp_s:add(1,1,'buy',f'P/VP {pvp:.2f}x — Abaixo do setor ({pvp_s}x) ✅')
        else:          add(0,1,'neutral',f'P/VP {pvp:.2f}x — Acima do setor ({pvp_s}x)')

    dy=ind.get('dy')
    if dy and dy>0:
        if dy>cdi:      add(2,2,'buy',f'DY {dy:.1f}% > CDI {cdi:.1f}% — Supera renda fixa ⭐⭐')
        elif dy>cdi*0.7:add(1,2,'neutral',f'DY {dy:.1f}% vs CDI {cdi:.1f}% — Proximo da RF')
        else:           add(0,2,'sell',f'DY {dy:.1f}% < CDI {cdi:.1f}% — Abaixo da RF')

    roe_v=ind.get('roe'); roe_s=setor.get('roe_min',15)
    if roe_v and roe_v>0:
        if roe_v>roe_s:  add(1,1,'buy',f'ROE {roe_v:.1f}% — Acima do setor ({roe_s}%) ✅')
        elif roe_v>10:   add(0,1,'neutral',f'ROE {roe_v:.1f}% — Retorno moderado')
        else:            add(0,1,'sell',f'ROE {roe_v:.1f}% — Retorno fraco')

    de=ind.get('debt_ebitda')
    if de is not None:
        if de<1.5:  add(1,1,'buy',f'Div/EBITDA {de:.1f}x — Endividamento saudavel ✅')
        elif de<3:  add(0,1,'neutral',f'Div/EBITDA {de:.1f}x — Moderado')
        else:       add(0,1,'sell',f'Div/EBITDA {de:.1f}x — Alto endividamento')

    vj=ind.get('valor_justo_graham'); up=ind.get('upside_graham')
    if vj and p:
        if up and up>20:      add(2,2,'buy',f'Graham: upside {up:.0f}% — Subavaliada (VJ: R${vj:.2f}) ✅✅')
        elif up and up>0:     add(1,2,'buy',f'Graham: upside {up:.0f}% — Leve desconto (VJ: R${vj:.2f}) ✅')
        elif up and up>-20:   add(0,2,'neutral',f'Graham: {up:.0f}% do valor justo (VJ: R${vj:.2f})')
        else:                 add(-1,2,'sell',f'Graham: sobrevalorizada {abs(up or 0):.0f}% acima (VJ: R${vj:.2f})')

    pct=sc/mx if mx else 0
    if pct>=0.65:   sig,cor='COMPRA FORTE','green'
    elif pct>=0.40: sig,cor='COMPRA MODERADA','accent'
    elif pct>=0.10: sig,cor='NEUTRO','warn'
    elif pct>=-0.20:sig,cor='VENDA MODERADA','orange'
    else:           sig,cor='VENDA FORTE','danger'

    return {'sinal':sig,'cor':cor,'score':sc,'max_score':mx,'forca':round(pct*100),'detalhes':det,'cdi_usado':cdi}

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
    # DJI, ES, NQ via Yahoo (confirmado funcionando)
    dji = yquote('%5EDJI')
    esf = yquote('ES%3DF')
    nqf = yquote('NQ%3DF')
    
    vix = None
    dxy = None
    win = None

    # VIX via Yahoo Finance (confirmado funcionando antes)
    vix = yquote('%5EVIX')

    # DXY via TradingView forex scanner
    try:
        r_dxy = requests.post('https://scanner.tradingview.com/forex/scan',
            json={"symbols":{"tickers":["TVC:DXY"]},"columns":["close","change_abs"]},
            timeout=6)
        if r_dxy.ok:
            items = r_dxy.json().get('data',[])
            if items:
                d = items[0].get('d',[])
                if d and d[0]:
                    close = round(float(d[0]),2)
                    chg = float(d[1]) if len(d)>1 and d[1] else 0
                    dxy = {'price':close,'prev':round(close-chg,2)}
    except: pass

    # DXY fallback via America scanner
    if not dxy:
        try:
            r_dxy2 = requests.post('https://scanner.tradingview.com/america/scan',
                json={"symbols":{"tickers":["TVC:DXY"]},"columns":["close","change_abs"]},
                timeout=6)
            if r_dxy2.ok:
                items = r_dxy2.json().get('data',[])
                if items:
                    d = items[0].get('d',[])
                    if d and d[0]:
                        close = round(float(d[0]),2)
                        chg = float(d[1]) if len(d)>1 and d[1] else 0
                        dxy = {'price':close,'prev':round(close-chg,2)}
        except: pass

    # WIN1! via TradingView futures scanner
    try:
        r_win = requests.post('https://scanner.tradingview.com/futures/scan',
            json={"symbols":{"tickers":["BMFBOVESPA:WIN1!"]},"columns":["close","change_abs"]},
            timeout=6)
        if r_win.ok:
            items = r_win.json().get('data',[])
            if items and items[0].get('d') and items[0]['d'][0]:
                d2 = items[0]['d']
                close = round(float(d2[0]),0)
                chg = float(d2[1]) if len(d2)>1 and d2[1] else 0
                win = {'price':close,'prev':round(close-chg,0),'source':'TV futures'}
    except: pass
    # Fallback: brazil scanner
    if not win:
        try:
            r_win2 = requests.post('https://scanner.tradingview.com/brazil/scan',
                json={"symbols":{"tickers":["BMFBOVESPA:WIN1!"]},"columns":["close","change_abs"]},
                timeout=6)
            if r_win2.ok:
                items2 = r_win2.json().get('data',[])
                if items2 and items2[0].get('d') and items2[0]['d'][0]:
                    d3 = items2[0]['d']
                    close = round(float(d3[0]),0)
                    chg = float(d3[1]) if len(d3)>1 and d3[1] else 0
                    win = {'price':close,'prev':round(close-chg,0),'source':'TV brazil'}
        except: pass
    # Fallback via Yahoo IBOV
    if not win:
        try:
            ibov = yquote('%5EBVSP')
            if ibov: win = {'price':round(ibov['price'],0),'prev':round(ibov['prev'],0),'source':'IBOV'}
        except: pass

    # USD/BRL via Yahoo
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
    """Monte Carlo com simulacao de caminhos para opcoes com barreiras"""
    try:
        import numpy as _np
        data = request.get_json() or {}
        ticker   = data.get('ticker', 'AXIA3.SA')
        entry    = float(data.get('entry', 54.31))
        kdo      = float(data.get('kdo', 43.39))   # knock-down barrier
        kuo      = float(data.get('kuo', 68.48))   # knock-up barrier
        T_days   = int(data.get('t_days', 113))
        n        = 3000
        steps    = max(T_days // 5, 10)  # passos semanais para velocidade

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

        # Simula N caminhos completos
        z = _np.random.standard_normal((n, steps))
        log_returns = drift + vol_step * z
        paths = S * _np.exp(_np.cumsum(log_returns, axis=1))

        # Verifica barreiras em cada caminho
        max_prices = _np.max(paths, axis=1)
        min_prices = _np.min(paths, axis=1)
        final_prices = paths[:, -1]

        kuo_hit = max_prices >= kuo
        kdo_hit = min_prices <= kdo
        no_barrier = ~kuo_hit & ~kdo_hit

        prob_no_barrier = round(float(no_barrier.mean() * 100), 2)
        prob_kuo_hit    = round(float(kuo_hit.mean() * 100), 2)
        prob_kdo_hit    = round(float(kdo_hit.mean() * 100), 2)

        return jsonify({
            'ticker': ticker, 'preco_atual': round(S, 2),
            'entry': entry, 'kdo': kdo, 'kuo': kuo, 't_days': T_days,
            'volatilidade_historica_pct': round(sigma * 100, 2),
            'prob_sem_barreira': prob_no_barrier,
            'prob_barreira_alta': prob_kuo_hit,
            'prob_barreira_baixa': prob_kdo_hit,
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

        # Preco: usa valor passado diretamente se disponivel (evita Yahoo lento)
        S = float(data['price']) if data.get('price') else None
        sigma = float(data['sigma']) if data.get('sigma') else 0.35
        cl = []

        if not S:
            # Busca Yahoo com fallback
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
        
        # Vol historica - usa dados do Yahoo se disponivel, senao padrao por ativo
        if cl and not data.get('sigma'):
            sigma=vol_hist(cl)
        elif not cl:
            # Vol padrao por tipo de ativo quando Yahoo nao tem dados
            vol_defaults = {
                'AXIA3': 0.35, 'ROXO34': 0.45,
                'PETR4': 0.30, 'VALE3': 0.32, 'BBAS3': 0.28,
            }
            ticker_base = ticker.replace('.SA','').upper()
            sigma = vol_defaults.get(ticker_base, 0.35)
        T=max(T_days,1)/252.0
        sqT=math.sqrt(T)
        drift=-0.5*sigma**2*T

        # Numpy Monte Carlo
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

# ── INDICADORES B3 ────────────────────────────────────
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

        # Primary: brapi.dev (API brasileira, confiavel do Render)
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
                # Fundamentais do brapi
                fund = {
                    'pl':   rd.get('priceEarnings'),
                    'pvp':  rd.get('priceToBook'),
                    'dy':   rd.get('dividendYield'),
                    'roe':  rd.get('returnOnEquity'),
                    'lpa':  rd.get('earningsPerShare'),
                    'vpa':  rd.get('bookValuePerShare'),
                    'ev_ebitda': rd.get('enterpriseValue'),
                    'margem': rd.get('profitMargin'),
                }
        except: pass

        # Fallback: Yahoo Finance
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

        # DADOS HARDCODED FUNDAMENTAIS (atualizar trimestralmente)
        FUND_OVERRIDE = {
            'PETR4': {'pvp':1.65,'dy':6.42,'lpa':8.54,'vpa':29.76,'ev_ebitda':3.2,'roe':22.5,'debt_ebitda':0.8,'margem':18.3,'pl':5.8},
            'VALE3': {'pvp':1.80,'dy':8.50,'lpa':11.20,'vpa':47.30,'ev_ebitda':4.1,'roe':24.1,'debt_ebitda':0.6,'margem':22.1,'pl':7.2},
            'BBAS3': {'pvp':0.95,'dy':9.80,'lpa':4.20,'vpa':24.80,'ev_ebitda':None,'roe':19.8,'debt_ebitda':None,'margem':28.5,'pl':5.2},
            'AXIA3': {'pvp':0.85,'dy':4.20,'lpa':1.90,'vpa':12.50,'ev_ebitda':7.5,'roe':10.0,'debt_ebitda':3.2,'margem':15.0,'pl':12.0},
            'ROXO34':{'pvp':3.50,'dy':0.00,'lpa':0.45,'vpa':3.60,'ev_ebitda':None,'roe':8.5,'debt_ebitda':None,'margem':18.0,'pl':40.0},
        }
        if symbol in FUND_OVERRIDE:
            for k,v in FUND_OVERRIDE[symbol].items():
                if v is not None: fund[k] = fund.get(k) or v

        SETORES = {
            'PETR4': {'nome':'Petróleo & Gás','pl_medio':6.0,'pvp_medio':1.5,'roe_min':15},
            'VALE3': {'nome':'Mineração','pl_medio':7.0,'pvp_medio':1.8,'roe_min':15},
            'BBAS3': {'nome':'Bancos','pl_medio':8.0,'pvp_medio':1.2,'roe_min':18},
            'AXIA3': {'nome':'Energia Elétrica','pl_medio':12.0,'pvp_medio':1.2,'roe_min':10},
            'ROXO34':{'nome':'Fintech/BDR','pl_medio':40.0,'pvp_medio':5.0,'roe_min':10},
        }
        setor = SETORES.get(symbol, {'nome':'Geral','pl_medio':12.0,'pvp_medio':2.0,'roe_min':12})

        def mm(lst, n):
            return round(sum(lst[-n:])/n, 2) if len(lst) >= n else None
        def rsi(closes, n=14):
            if len(closes) < n+1: return None
            gains = [max(closes[i]-closes[i-1],0) for i in range(1,len(closes))]
            losses = [max(closes[i-1]-closes[i],0) for i in range(1,len(closes))]
            ag = sum(gains[:n])/n; al = sum(losses[:n])/n
            for i in range(n, len(gains)):
                ag = (ag*(n-1)+gains[i])/n
                al = (al*(n-1)+losses[i])/n
            return round(100 - 100/(1+ag/al),1) if al else 100.0

        closes = hist_closes
        rsi14 = rsi(closes)
        ma20  = mm(closes,20)
        ma50  = mm(closes,50)
        ma200 = mm(closes,200)

        def sig(val, good, bad, reverse=False):
            if val is None: return 'Neutro'
            if reverse: return 'Alta' if val < good else ('Baixa' if val > bad else 'Neutro')
            return 'Alta' if val > good else ('Baixa' if val < bad else 'Neutro')

        # Graham: Valor Justo = sqrt(22.5 * LPA * VPA)
        lpa = fund.get('lpa') or fund.get('earningsPerShare')
        vpa = fund.get('vpa') or fund.get('bookValuePerShare')
        graham = None
        if lpa and vpa and lpa > 0 and vpa > 0:
            import math
            graham = round(math.sqrt(22.5 * float(lpa) * float(vpa)), 2)

        pl   = fund.get('pl') or fund.get('priceEarnings')
        pvp  = fund.get('pvp') or fund.get('priceToBook')
        dy   = fund.get('dy') or fund.get('dividendYield')
        roe  = fund.get('roe') or fund.get('returnOnEquity')
        if dy and float(dy) > 1: dy = round(float(dy)/100, 4)  # normaliza %

        indicadores = []
        # Técnicos
        if rsi14: indicadores.append({'nome':'RSI(14)','valor':rsi14,'sinal':'Sobrevenda' if rsi14<30 else ('Sobrecompra' if rsi14>70 else 'Neutro')})
        if ma20:  indicadores.append({'nome':'MM20','valor':ma20,'sinal':'Alta' if preco_atual>ma20 else 'Baixa'})
        if ma50:  indicadores.append({'nome':'MM50','valor':ma50,'sinal':'Alta' if preco_atual>ma50 else 'Baixa'})
        if ma200: indicadores.append({'nome':'MM200','valor':ma200,'sinal':'Alta' if preco_atual>ma200 else 'Baixa'})
        # Fundamentais
        if pl:   indicadores.append({'nome':'P/L','valor':round(float(pl),1),'sinal':sig(float(pl),setor['pl_medio']*0.8,setor['pl_medio']*1.5,reverse=True)})
        if pvp:  indicadores.append({'nome':'P/VP','valor':round(float(pvp),2),'sinal':sig(float(pvp),setor['pvp_medio']*0.8,setor['pvp_medio']*1.5,reverse=True)})
        if dy:
            dy_pct = round(float(dy)*100,2)
            cdi_pct = cdi or 10.5
            indicadores.append({'nome':'Div.Yield','valor':f'{dy_pct}%','sinal':'Alta' if dy_pct > cdi_pct*0.8 else ('Neutro' if dy_pct > 3 else 'Baixa')})
        if roe:  indicadores.append({'nome':'ROE','valor':f'{round(float(roe)*100 if float(roe)<1 else float(roe),1)}%','sinal':'Alta' if float(roe)*100>setor['roe_min'] or float(roe)>setor['roe_min'] else 'Neutro'})
        if graham: indicadores.append({'nome':'Graham','valor':graham,'sinal':'Alta' if preco_atual<graham else ('Neutro' if preco_atual<graham*1.3 else 'Baixa')})
        if lpa:  indicadores.append({'nome':'LPA','valor':round(float(lpa),2),'sinal':'Alta' if float(lpa)>0 else 'Baixa'})
        if vpa:  indicadores.append({'nome':'VPA','valor':round(float(vpa),2),'sinal':'Neutro'})

        # Score
        altas  = sum(1 for i in indicadores if i['sinal']=='Alta')
        baixas = sum(1 for i in indicadores if i['sinal']=='Baixa')
        total  = len(indicadores) or 1
        score_raw = round((altas/total)*100)

        result = {
            'ticker': ticker,
            'preco_atual': round(preco_atual,2),
            'preco_anterior': round(preco_prev,2) if preco_prev else None,
            'setor': setor['nome'],
            'score_total': score_raw,
            'indicadores': indicadores,
            'graham_value': graham,
            'upside_graham': round((graham/preco_atual-1)*100,1) if graham else None,
        }
        try:
            _IND_CACHE[ticker] = (result, _t.time())
        except: pass
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/btc/cycle', methods=['GET'])
def get_btc_cycle():
    try:
        import time as _t, math as _m
        r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1d&range=4y',
            headers={'User-Agent':'Mozilla/5.0'},timeout=15)
        if not r.ok: return jsonify({'error':f'Yahoo {r.status_code}'}),500
        cl=[c for c in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        price=cl[-1]
        dma111=mm(cl,111); dma350=mm(cl,350)
        dma350x2=round(dma350*2,0) if dma350 else None
        pi_dist=round(dma350x2-dma111,0) if (dma111 and dma350x2) else None
        if dma111 and dma350x2:
            if dma111>=dma350x2: pi_sig="TOPO DETECTADO Pi Cycle cruzou!"
            elif pi_dist<10000: pi_sig="Proximidade de topo critica"
            elif pi_dist<30000: pi_sig="Monitorar distancia diminuindo"
            else: pi_sig=f"Seguro distancia US$ {pi_dist:,.0f}"
        else: pi_sig="Dados insuficientes"
        days=(_t.time()-1231006505)/86400
        fair=10**(5.84*_m.log10(days)-17.01)
        mults=[0.10,0.20,0.35,0.55,0.80,1.20,1.70,2.50,4.00]
        names=["Fire Sale","Buy","Accumulate","Still Cheap","HODL!","Bubble?","FOMO","Sell","Max Bubble"]
        colors=["green","green","green","accent","warn","warn","danger","danger","danger"]
        rb=names[-1]; rc=colors[-1]
        for i,mv in enumerate(mults):
            if price<fair*mv: rb=names[i]; rc=colors[i]; break
        rw=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=4y',
            headers={'User-Agent':'Mozilla/5.0'},timeout=10)
        ma200w=None
        if rw.ok:
            clw=[c for c in rw.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
            ma200w=mm(clw,200)
        oc=get_btc_onchain()
        def ml(v): return "Capitulacao" if v<-1 else "Valor Justo" if v<1 else "Valorizado" if v<2 else "Aquecendo" if v<3 else "Sobrevalorizado" if v<5 else "Euforia TOPO"
        def nl(v): return "Capitulacao" if v<0 else "Esperanca/Medo" if v<0.25 else "Otimismo" if v<0.50 else "Crenca/Negacao" if v<0.75 else "Euforia TOPO"
        def pl(v): return "Estresse mineradores" if v<0.5 else "Pos-halving" if v<1.0 else "Normal" if v<2.0 else "Aquecendo" if v<3.4 else "Topo de ciclo"
        return jsonify({'price':round(price,0),
            'pi_cycle':{'dma111':dma111,'dma350x2':dma350x2,'distance':pi_dist,'signal':pi_sig},
            'rainbow':{'band':rb,'color':rc},
            'ma200w':round(ma200w,0) if ma200w else None,
            'ma200w_pct':round((price-ma200w)/ma200w*100,1) if ma200w else None,
            'mvrv_zscore':{'value':oc['mvrv_zscore'],'label':ml(oc['mvrv_zscore'])},
            'nupl':{'value':oc['nupl'],'label':nl(oc['nupl'])},
            'puell':{'value':oc['puell_multiple'],'label':pl(oc['puell_multiple'])},
            'sopr':oc['sopr'],'realized_price':oc['realized_price'],
            'onchain_updated':oc['updated']})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/btc/indicators', methods=['GET'])
def get_btc_indicators():
    try:
        # Yahoo Finance — historico semanal BTC-USD
        r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=4y',
            headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},timeout=15)
        if not r.ok:
            # Fallback: tenta query2
            r=requests.get('https://query2.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=4y',
                headers={'User-Agent':'Mozilla/5.0'},timeout=15)
        if not r.ok: return jsonify({'error':f'Yahoo BTC HTTP {r.status_code}'}),500
        d=r.json()
        result=d['chart']['result'][0]
        q=result['indicators']['quote'][0]
        cl=[c for c in q.get('close',[]) if c is not None]
        vl=[v if v else 0 for v in q.get('volume',[])][-len(cl):]
        price=cl[-1]
        rsi_v=rsi(cl,14); mm20_v=mm(cl,20); mm50_v=mm(cl,50); mm200_v=mm(cl,200)
        ml,ms,mh=macd(cl); bu,bm,bl=bollinger(cl); _,ot=obv(cl,vl)
        div=None
        if rsi_v and len(cl)>=60:
            mp_r=min(cl[-15:]); mp_p=min(cl[-30:-15])
            rr=rsi(cl[-29:],14); rp=rsi(cl[-44:-15],14)
            if rr and rp:
                if mp_r<mp_p and rr>rp: div='BULLISH ⚡ Preco faz minima mais baixa mas RSI nao confirma — Sinal de fundo potencial!'
                elif mp_r>mp_p and rr<rp: div='BEARISH ⚠ Preco faz maxima mais alta mas RSI nao confirma — Sinal de topo!'
        return jsonify({
            'ticker':'BTC','price':round(price,0),
            'rsi_semanal':rsi_v,
            'mm20_semanal':round(mm20_v,0) if mm20_v else None,
            'mm50_semanal':round(mm50_v,0) if mm50_v else None,
            'mm200_semanal':round(mm200_v,0) if mm200_v else None,
            'macd':round(ml,0) if ml else None,'macd_signal':round(ms,0) if ms else None,'macd_histogram':round(mh,0) if mh else None,
            'bb_upper':round(bu,0) if bu else None,'bb_mid':round(bm,0) if bm else None,'bb_lower':round(bl,0) if bl else None,
            'obv_trend':ot,'divergencia_rsi':div,'data_points':len(cl)
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── VIX e DXY via TradingView ────────────────────────
@app.route('/tv/macro', methods=['GET'])
def tv_macro():
    try:
        payload = {
            "symbols": {"tickers": ["TVC:VIX","TVC:DXY","BMFBOVESPA:WIN1!"]},
            "columns": ["close","change_abs","change"]
        }
        r = requests.post('https://scanner.tradingview.com/global/scan',
            json=payload, timeout=5)
        if not r.ok:
            return jsonify({'error': f'TV {r.status_code}'}), 500
        data = r.json()
        result = {}
        for item in data.get('data', []):
            s = item.get('s','')
            d = item.get('d', [])
            if len(d) >= 1 and d[0]:
                close = d[0]
                chg = d[1] if len(d) > 1 else 0
                prev = close - chg if chg else close
                result[s] = {'price': round(float(close),2), 'prev': round(float(prev),2)}
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── FEAR & GREED INDEX ───────────────────────────────
@app.route('/feargreed', methods=['GET'])
def get_fear_greed():
    try:
        r=requests.get('https://api.alternative.me/fng/?limit=1',
            headers={'User-Agent':'Mozilla/5.0'},timeout=8)
        if r.ok:
            d=r.json()
            item=d.get('data',[{}])[0]
            return jsonify({
                'value': int(item.get('value',50)),
                'value_classification': item.get('value_classification','Neutro'),
                'timestamp': item.get('timestamp','')
            })
    except: pass
    return jsonify({'value':50,'value_classification':'Neutro','timestamp':''}),200

# Add AXIA3 to SETORES
# ── US STOCKS VIA YAHOO ──────────────────────────────
# Exchange map for TradingView
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

    # Step 1: Hyperliquid allMids para stocks (AAPL, MSFT, NVDA, etc.)
    HL_STOCKS = {'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO',
                 'NFLX','AMD','COIN','MSTR','PLTR','UBER','ABNB'}
    hl_needed = [t for t in tickers if t in HL_STOCKS or t.replace('.','').replace('-','') in HL_STOCKS]
    if hl_needed:
        try:
            rhl = requests.post('https://api.hyperliquid.xyz/info',
                json={'type':'allMids'},
                headers={'Content-Type':'application/json'}, timeout=5)
            if rhl.ok:
                hl_data = rhl.json()
                for t in hl_needed:
                    tk = 'GOOGL' if t in ('GOOG','GOOGL') else t
                    if tk in hl_data:
                        price = round(float(hl_data[tk]), 2)
                        result[t] = {'price': price, 'prev': round(price * 0.999, 2), 'src': 'HL'}
        except: pass

    # Step 2: TradingView america scanner para restantes
    remaining = [t for t in tickers if t not in result]
    if remaining:
        exc_map = {
            'JPM':'NYSE','UNH':'NYSE','V':'NYSE','MA':'NYSE','XOM':'NYSE',
            'PG':'NYSE','JNJ':'NYSE','HD':'NYSE','BAC':'NYSE','GS':'NYSE',
            'SHW':'NYSE','CAT':'NYSE','AXP':'NYSE','MCD':'NYSE','TRV':'NYSE',
            'IBM':'NYSE','CRM':'NYSE','CVX':'NYSE','DIS':'NYSE','NKE':'NYSE',
            'BA':'NYSE','LLY':'NYSE','WMT':'NYSE','KO':'NYSE','BRK.B':'NYSE',
        }
        tv_tks = [f"{exc_map.get(t,'NASDAQ')}:{t}" for t in remaining]
        try:
            rtv = requests.post('https://scanner.tradingview.com/america/scan',
                json={'symbols':{'tickers':tv_tks},'columns':['close','change_abs']},
                headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
            if rtv.ok:
                for item in rtv.json().get('data',[]):
                    sym = item.get('s','').split(':')[-1]
                    d2 = item.get('d',[])
                    if d2 and d2[0]:
                        close = round(float(d2[0]),2)
                        chg = float(d2[1]) if len(d2)>1 and d2[1] else 0
                        result[sym] = {'price':close,'prev':round(close-chg,2),'src':'TV'}
        except: pass

    # Step 3: Yahoo individual yquote para restantes
    still_missing = [t for t in tickers if t not in result]
    for t in still_missing[:8]:
        q = yquote(t)
        if q: result[t] = q

    return jsonify(result)
@app.route('/calendar/test', methods=['GET'])
def get_calendar_test():
    """Test calendar endpoint to debug"""
    try:
        r = requests.get('https://nfs.faireconomy.media/ff_calendar_thisweek.json',
            headers={'User-Agent':'Mozilla/5.0 Trader-Desk/1.0'}, timeout=10)
        return jsonify({'status':r.status_code,'size':len(r.text),'sample':r.json()[:3] if r.ok else r.text[:200]})
    except Exception as e:
        return jsonify({'error':str(e)})

@app.route('/calendar', methods=['GET'])
def get_calendar():
    all_events = []
    currencies_ok = {'USD','BRL','EUR','GBP','CNY','JPY','CAD','AUD'}
    flag_map = {'USD':'🇺🇸','BRL':'🇧🇷','EUR':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳','JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺'}
    imp_map = {'Low':1,'Medium':2,'High':3,'Holiday':0}

    urls = [
        'https://nfs.faireconomy.media/ff_calendar_thisweek.json',
        'https://nfs.faireconomy.media/ff_calendar_nextweek.json',
    ]
    for url in urls:
        try:
            r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
            if not r.ok: continue
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
                actual   = e.get('actual')   or None
                forecast = e.get('forecast') or None
                previous = e.get('previous') or None
                # Sinal: se actual veio, comparar com forecast
                signal = None
                if actual and forecast:
                    try:
                        a = float(str(actual).replace('%','').replace('K','000').replace('M','000000'))
                        f = float(str(forecast).replace('%','').replace('K','000').replace('M','000000'))
                        signal = 'beat' if a >= f else 'miss'
                    except: pass
                all_events.append({
                    'date': date_str, 'time': time_str,
                    'country': cur, 'flag': flag_map.get(cur,'🌐'),
                    'event': e.get('title',''),
                    'importance': imp,
                    'actual': actual, 'forecast': forecast, 'previous': previous,
                    'signal': signal,
                })
        except: pass
    all_events.sort(key=lambda x: (x.get('date',''), x.get('time','')))
    return jsonify(all_events)


@app.route('/macro/brazil', methods=['GET'])
def get_macro_brazil():
    """Indicadores macro Brasil via BCB"""
    result = {}
    series = {
        'ipca_mensal': '433',
        'selic': '432', 
        'pib_trimestral': '22099',
        'cambio_usd': '1',
        'igpm': '189',
    }
    for name, serie_id in series.items():
        try:
            r = requests.get(
                f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie_id}/dados/ultimos/3?formato=json',
                timeout=5)
            if r.ok:
                data = r.json()
                if data:
                    result[name] = [{'data': d['data'], 'valor': d['valor']} for d in data[-3:]]
        except: pass
    return jsonify(result)

# ── SERVE HTML ────────────────────────────────────────
import os

# HTML EMBUTIDO — 2026-06-12 17:15
import base64 as _b64
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjAgLSAyMDI2LTA2LTA3IDEwOjQ0IC0tPgo8aHRtbCBsYW5nPSJwdC1CUiI+CjxoZWFkPgo8bWV0YSBjaGFyc2V0PSJVVEYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5UcmFkZXIgRGVzazwvdGl0bGU+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDMwMDs0MDA7NjAwOzcwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQo6cm9vdHstLWJnOiMwZDBkMGQ7LS1iZzI6IzE0MTQxNDstLWJnMzojMWExYTFhOy0tdGV4dDojZThlOGU4Oy0tbXV0ZWQ6IzY2NjstLWJvcmRlcjojMjIyOy0tYWNjZW50OiNmMGE1MDA7LS1ncmVlbjojMDBjODUzOy0tcmVkOiNmZjE3NDQ7LS13YXJuOiNmZjk4MDA7LS1kYW5nZXI6I2ZmMTc0NDstLWJsdWU6IzIxOTZmMzstLWl0bTojZmY0NDQ0fQpib2R5e2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXRleHQpO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOi43NXJlbTtwYWRkaW5nOjEycHg7bWF4LXdpZHRoOjYyMHB4O21hcmdpbjowIGF1dG99Ci50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MTJweDtvdmVyZmxvdy14OmF1dG87d2hpdGUtc3BhY2U6bm93cmFwfQoudGFie3BhZGRpbmc6NnB4IDEycHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6LjZyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtmbGV4LXNocmluazowfQoudGFiLmFjdGl2ZXtiYWNrZ3JvdW5kOnZhcigtLWFjY2VudCk7Y29sb3I6IzAwMDtib3JkZXItY29sb3I6dmFyKC0tYWNjZW50KX0KLnRhYi1jb250ZW50e2Rpc3BsYXk6bm9uZX0udGFiLWNvbnRlbnQuYWN0aXZle2Rpc3BsYXk6YmxvY2t9Ci5zZWN7Zm9udC1zaXplOi41NXJlbTtsZXR0ZXItc3BhY2luZzouMTJlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6OHB4IDAgNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7bWFyZ2luLWJvdHRvbTo4cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6NnB4fQouc2VjIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50KX0uc3Jje2NvbG9yOnZhcigtLWJvcmRlcik7Zm9udC1zaXplOi41cmVtfQouZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEycHh9Ci5jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4IDhweDt0cmFuc2l0aW9uOmJvcmRlci1jb2xvciAuMTVzfS5jYXJkOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpfQouY2FyZC5ncmVlbntib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1ncmVlbil9LmNhcmQuYmx1ZXtib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1ibHVlKX0uY2FyZC53YXJue2JvcmRlci10b3A6MnB4IHNvbGlkIHZhcigtLXdhcm4pfS5jYXJkLnJlZHtib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS1yZWQpfQouYy1sYWJlbHtmb250LXNpemU6LjQ4cmVtO2NvbG9yOnZhcigtLW11dGVkKTtsZXR0ZXItc3BhY2luZzouMDhlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bWFyZ2luLWJvdHRvbToycHh9Ci5jLW5hbWV7Zm9udC1zaXplOi42cmVtO2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS10ZXh0KTttYXJnaW4tYm90dG9tOjRweH0KLmMtcHJpY2V7Zm9udC1zaXplOi44NXJlbTtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjZW50KX0KLmMtcHJpY2UubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOi43cmVtfQouYy1jaGFuZ2V7Zm9udC1zaXplOi41NXJlbTttYXJnaW4tdG9wOjJweH0KLmNoZy11cHtjb2xvcjp2YXIoLS1ncmVlbil9LmNoZy1kbntjb2xvcjp2YXIoLS1yZWQpfS5jaGctZmxhdHtjb2xvcjp2YXIoLS1tdXRlZCl9CkBrZXlmcmFtZXMgcHVsc2V7MCUsMTAwJXtvcGFjaXR5OjF9NTAle29wYWNpdHk6LjR9fQoucG9zLWNhcmR7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tYWNjZW50KTtwYWRkaW5nOjEycHg7bWFyZ2luLWJvdHRvbTo4cHh9Ci5wb3MtbGFiZWx7Zm9udC1zaXplOi41MnJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bGV0dGVyLXNwYWNpbmc6LjA2ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NHB4fQoucG9zLXRpY2tlcntmb250LXNpemU6MS4xcmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS1hY2NlbnQpO21hcmdpbi1ib3R0b206MnB4fQoucG9zLXByaWNle2ZvbnQtc2l6ZToxLjNyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLXRleHQpfS5wb3MtcHJpY2UubG9hZGluZ3tjb2xvcjp2YXIoLS1tdXRlZCk7YW5pbWF0aW9uOnB1bHNlIDEuNXMgaW5maW5pdGU7Zm9udC1zaXplOi45cmVtfQoucG9zLWNoZ3tmb250LXNpemU6LjY1cmVtO21hcmdpbi1ib3R0b206OHB4fQouc2J7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nLXRvcDo4cHg7bWFyZ2luLXRvcDo4cHh9Ci5zYi1yb3d7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO3BhZGRpbmc6M3B4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKTtmb250LXNpemU6LjZyZW19Ci5zYi1sYmx7Y29sb3I6dmFyKC0tbXV0ZWQpfS5zYi12YWx7Y29sb3I6dmFyKC0tdGV4dCk7dGV4dC1hbGlnbjpyaWdodDttYXgtd2lkdGg6NjAlfQouc2ItdmFsLm9re2NvbG9yOnZhcigtLWdyZWVuKX0uc2ItdmFsLndhcm57Y29sb3I6dmFyKC0td2Fybil9LnNiLXZhbC5pdG17Y29sb3I6dmFyKC0taXRtKX0KLnNpZ25hbHtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4O21hcmdpbi10b3A6OHB4O2JhY2tncm91bmQ6dmFyKC0tYmcpfQouc2lnLXRpdGxle2ZvbnQtc2l6ZTouNTVyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206NnB4O2NvbG9yOnZhcigtLW11dGVkKX0KLmluZC1ib3h7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjhweDt0ZXh0LWFsaWduOmNlbnRlcn0KLmluZC1sYmx7Zm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjRweH0KLmluZC12YWx7Zm9udC1zaXplOjFyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOnZhcigtLXRleHQpfQouaW5kLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LmluZC12YWwud2Fybntjb2xvcjp2YXIoLS13YXJuKX0uaW5kLXZhbC5kb3due2NvbG9yOnZhcigtLXJlZCl9Ci5zZWN0b3ItaGVhZGVye2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo4cHggMTRweDtjdXJzb3I6cG9pbnRlcjtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO2ZvbnQtc2l6ZTouNjVyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweH0KLnNlY3Rvci1oZWFkZXI6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tdGV4dCl9Ci5zZWN0b3ItYm9keXtkaXNwbGF5Om5vbmU7cGFkZGluZy10b3A6NHB4fQpmb290ZXJ7bWFyZ2luLXRvcDoxNnB4O3BhZGRpbmctdG9wOjEycHg7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Zm9udC1zaXplOi41MnJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7ZmxleC13cmFwOndyYXA7Z2FwOjZweH0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjEycHgiPgogIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouOXJlbTtmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0tYWNjZW50KSI+VFJBREVSIERFU0s8L2Rpdj4KICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKSIgaWQ9Imxhc3QtdXBkYXRlIj7igJQ8L2Rpdj4KPC9kaXY+CjxkaXYgY2xhc3M9InRhYnMiPgogIDxkaXYgY2xhc3M9InRhYiBhY3RpdmUiIG9uY2xpY2s9InN3aXRjaFRhYignY290YWNvZXMnLHRoaXMpIj7wn5OKIENvdGHDp8O1ZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJ0YWIiIG9uY2xpY2s9InN3aXRjaFRhYignaW5kaWNhZG9yZXMnLHRoaXMpIj7wn5OIIEluZGljYWRvcmVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ3Bvc2ljb2VzJyx0aGlzKSI+8J+SvCBQb3Npw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ2NhbGVuZGFyaW8nLHRoaXMpIj7wn5OFIENhbGVuZMOhcmlvPC9kaXY+CjwvZGl2PgoKPGRpdiBpZD0idGFiLWNvdGFjb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQgYWN0aXZlIj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPjAxPC9zcGFuPiBFVUEgPHNwYW4gY2xhc3M9InNyYyI+wrcgcHJveHk8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+RVMxKjwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImVzZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImVzZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RnV0dXJvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5OUTwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9Im5xZi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9Im5xZi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+w41uZGljZTwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+REpJPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iZGppLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iZGppLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCByZWQiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlZvbGF0aWxpZGFkZTwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+VklYPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0idml4LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0idml4LWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBibHVlIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5Ew7NsYXI8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkRYWTwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImR4eS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImR4eS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkPDom1iaW88L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlVTRC9CUkw8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ1c2QtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ1c2QtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj4wMjwvc3Bhbj4gQjMg4oCUIFRvcCAxMCA8c3BhbiBjbGFzcz0ic3JjIj7CtyBUcmFkaW5nVmlldzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPsONbmRpY2U8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPklCT1Y8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJpYm92LXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iaWJvdi1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+V0lOMSE8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ3aW4tcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ3aW4tYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+UEVUUjQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJwZXRyNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJwZXRyNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+SVRVQjQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJpdHViNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJpdHViNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+VkFMRTM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ2YWxlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ2YWxlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QkJEQzQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJiYmRjNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJiYmRjNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QUJFVjM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJhYmV2M3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJhYmV2M3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QkJBUzM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJiYmFzM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJiYmFzM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CMzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+V0VHRTM8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJ3ZWdlM3EtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ3ZWdlM3EtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHdhcm4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkJEUjwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+Uk9YTzM0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0icm94bzM0cS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9InJveG8zNHEtYyI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj7wn5OCPC9zcGFuPiBCMyBwb3IgU2VnbWVudG8gPHNwYW4gY2xhc3M9InNyYyI+wrcgY2xpcXVlIHBhcmEgZXhwYW5kaXI8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdmaW5hbmNlaXJvJykiPjxzcGFuPvCfj6YgRmluYW5jZWlybzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1maW5hbmNlaXJvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1maW5hbmNlaXJvIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtZmluYW5jZWlybyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdwZXRyb2xlbycpIj48c3Bhbj7wn5uiIFBldHLDs2xlbyAmYW1wOyBHw6FzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXBldHJvbGVvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1wZXRyb2xlbyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLXBldHJvbGVvIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ21pbmVyYWNhbycpIj48c3Bhbj7im48gTWluZXJhw6fDo288L3NwYW4+PHNwYW4gaWQ9InNhcnItbWluZXJhY2FvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1taW5lcmFjYW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1taW5lcmFjYW8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWF0ZXJpYWlzJykiPjxzcGFuPvCfjLIgUGFwZWwgJmFtcDsgQ2VsdWxvc2U8L3NwYW4+PHNwYW4gaWQ9InNhcnItbWF0ZXJpYWlzIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1tYXRlcmlhaXMiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1tYXRlcmlhaXMiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygndXRpbGlkYWRlJykiPjxzcGFuPuKaoSBVdGlsaWRhZGUgUMO6YmxpY2E8L3NwYW4+PHNwYW4gaWQ9InNhcnItdXRpbGlkYWRlIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS11dGlsaWRhZGUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC11dGlsaWRhZGUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnY29uc3Vtb19jaWNsaWNvJykiPjxzcGFuPvCfm40gQ29uc3VtbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1jb25zdW1vX2NpY2xpY28iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWNvbnN1bW9fY2ljbGljbyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWNvbnN1bW9fY2ljbGljbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdjb25zdW1vX25hbycpIj48c3Bhbj7wn5uSIENvbnN1bW8gTsOjbyBDw61jbGljbzwvc3Bhbj48c3BhbiBpZD0ic2Fyci1jb25zdW1vX25hbyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktY29uc3Vtb19uYW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1jb25zdW1vX25hbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdzYXVkZScpIj48c3Bhbj7wn4+lIFNhw7pkZTwvc3Bhbj48c3BhbiBpZD0ic2Fyci1zYXVkZSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktc2F1ZGUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1zYXVkZSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdpbmR1c3RyaWFpcycpIj48c3Bhbj7wn4+XIEJlbnMgSW5kdXN0cmlhaXM8L3NwYW4+PHNwYW4gaWQ9InNhcnItaW5kdXN0cmlhaXMiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWluZHVzdHJpYWlzIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtaW5kdXN0cmlhaXMiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygndGlfdGVsZWNvbScpIj48c3Bhbj7wn5K7IFRJICZhbXA7IENvbXVuaWNhw6fDtWVzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXRpX3RlbGVjb20iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LXRpX3RlbGVjb20iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC10aV90ZWxlY29tIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuPvCfh7rwn4e4PC9zcGFuPiBFVUEgcG9yIFNlZ21lbnRvPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdtYWc3JykiPjxzcGFuPuKtkCA3IE1hZ27DrWZpY2FzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1hZzciPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LW1hZzciPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1tYWc3Ij48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ25hc2RhcTE1JykiPjxzcGFuPvCfkrsgTmFzZGFxIFRvcCAxNTwvc3Bhbj48c3BhbiBpZD0ic2Fyci1uYXNkYXExNSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktbmFzZGFxMTUiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1uYXNkYXExNSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdzcDIwJykiPjxzcGFuPvCfk4ogUyZhbXA7UCA1MDAgVG9wIDIwPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXNwMjAiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LXNwMjAiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1zcDIwIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ2RqaTIwJykiPjxzcGFuPvCfj5sgRG93IEpvbmVzIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0ic2Fyci1kamkyMCI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktZGppMjAiPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1kamkyMCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj4wMzwvc3Bhbj4gQ29tbW9kaXRpZXM8L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+UGV0csOzbGVvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5XVEkvQ0w8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJjbC1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkdPTEQ8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJnb2xkLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3YXJuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+U0lMVkVSPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0ic2lsdmVyLXAiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3YXJuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5NZXRhbDwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+Q09QUEVSPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iY29wcGVyLXAiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+MDQ8L3NwYW4+IEJpdGNvaW48L2Rpdj4KICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+U3BvdDwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QlRDL1VTRDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImJ0Yy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImJ0Yy1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJUQyBSU0k8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtcnNpIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RnVuZGluZzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+QlRDIFJhdGU8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtZnVuZCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZlYXIgJmFtcDsgR3JlZWQ8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkluZGV4PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iZmctdmFsIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImZnLWxibCI+4oCUPC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGZvb3Rlcj48c3BhbiBpZD0iZm9vdGVyLXRpbWUiPuKAlDwvc3Bhbj48c3Bhbj5UcmFkZXIgRGVzayB2MTAuMDwvc3Bhbj48L2Zvb3Rlcj4KPC9kaXY+Cgo8ZGl2IGlkPSJ0YWItaW5kaWNhZG9yZXMiIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj7wn5OKPC9zcGFuPiBDaWNsbyBCaXRjb2luPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWN5Y2xlLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTBweCI+Q2FycmVnYW5kby4uLjwvZGl2PjwvZGl2PgogIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIGF1dG87Z2FwOjEwcHg7bWFyZ2luOjEycHggMDthbGlnbi1pdGVtczpzdGFydCI+CiAgICA8ZGl2IGlkPSJmZWFyLWdyZWVkLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTBweCI+Q2FycmVnYW5kbyBGZWFyICZhbXA7IEdyZWVkLi4uPC9kaXY+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTRweDttaW4td2lkdGg6MTIwcHg7dGV4dC1hbGlnbjpjZW50ZXIiPgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjZweCI+QlRDL1VTRDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtaW5kLXByaWNlIj7igJQ8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJidGMtaW5kLWNoZyI+4oCUPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPvCfk4o8L3NwYW4+IEluZGljYWRvcmVzIEJUQyBTZW1hbmFsPC9kaXY+CiAgPGRpdiBpZD0iYnRjLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuPvCfk4o8L3NwYW4+IFBFVFI0IDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZTouNTVyZW0iIG9uY2xpY2s9InJlbG9hZEluZCgncGV0cjQnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InBldHI0LWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuPvCfk4o8L3NwYW4+IFZBTEUzIDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZTouNTVyZW0iIG9uY2xpY2s9InJlbG9hZEluZCgndmFsZTMnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InZhbGUzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuPvCfk4o8L3NwYW4+IEJCQVMzIDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZTouNTVyZW0iIG9uY2xpY2s9InJlbG9hZEluZCgnYmJhczMnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9ImJiYXMzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuPvCfk4o8L3NwYW4+IEFYSUEzIDxzcGFuIHN0eWxlPSJjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1hY2NlbnQpO2ZvbnQtc2l6ZTouNTVyZW0iIG9uY2xpY2s9InJlbG9hZEluZCgnYXhpYTMnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9ImF4aWEzLWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiIHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxzcGFuPvCfk4o8L3NwYW4+IFJPWE8zNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3JveG8zNCcpIj7ihrs8L3NwYW4+PC9kaXY+CiAgPGRpdiBpZD0icm94bzM0LWluZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KPC9kaXY+Cgo8ZGl2IGlkPSJ0YWItcG9zaWNvZXMiIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj4wMTwvc3Bhbj4gT3BlcmHDp8O1ZXMgQXRpdmFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiPgogICAgPGRpdiBjbGFzcz0icG9zLWxhYmVsIj5QZXRyb2JyYXMgUE4gwrcgQ2FsbCBWZW5kaWRhIMK3IFBFVFJMMzE5IMK3IFZlbmMgMTcvMTIvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciI+UEVUUjQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wcmljZSBsb2FkaW5nIiBpZD0icHQtcG9zLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBvcy1jaGciIGlkPSJwdC1wb3MtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJlw6dvIFJlZi48L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgMzAsODU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgMzAsODUgKFBFVFJMMzE5KTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBhbyBzdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBpdG0iIGlkPSJwdC1pdG0iPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjE3LzEyLzIwMjYgwrcgPHNwYW4gaWQ9InB0LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+NDMsNCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gTUMgKHZvbC5oaXN0Lik8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIiBpZD0ibWMtcHQtcmVhbHRpbWUiPjgsMyU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gQiZTICh2b2wuaW1wbC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+OSw0JTwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXRpdGxlIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhaXIgYW8gc3RyaWtlPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXB0LWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbSI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1wdC1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlByb2IuIGNhaXI8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtcHQtc3RyaWtlIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1wdC12b2wiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NHB4IiBpZD0ibWMtcHQtaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxhYmVsIj5WYWxlIE9OIMK3IENhbGwgVmVuZGlkYSDCtyBWQUxFQjU3NCDCtyBWZW5jIDE4LzAyLzIwMjc8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPlZBTEUzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHJpY2UgbG9hZGluZyIgaWQ9InZsLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0idmwtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDU3LDQwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDU3LDQwIChWQUxFQjU3NCk8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gYW8gc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0idmwtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xOC8wMi8yMDI3IMK3IDxzcGFuIGlkPSJ2bC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjcxLDIlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DICh2b2wuaGlzdC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiIgaWQ9Im1jLXZsLXJlYWx0aW1lIj4xMSw1JTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Qcm9iLiBCJlMgKHZvbC5pbXBsLik8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4xNCwyJTwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXRpdGxlIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIGNhaXIgYW8gc3RyaWtlPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXZsLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbSI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy12bC1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlByb2IuIGNhaXI8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtdmwtc3RyaWtlIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy12bC12b2wiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NHB4IiBpZD0ibWMtdmwtaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxhYmVsIj5BWElBMyAoQSkgwrcgQmlkaXJlY2lvbmFsIMK3IFZlbmMgMTQvMDkvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciI+QVhJQTM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wcmljZSBsb2FkaW5nIiBpZD0iYXhpYTMtcG9zLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBvcy1jaGciIGlkPSJheGlhMy1wb3MtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJlw6dvIFJlZi48L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTQsMzE8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDQzLDUxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktVTyAoKzI2LDYlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDY4LDc2PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4rNCUgZml4bzwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjE0LzA5LzIwMjYgwrcgPHNwYW4gaWQ9ImF4aWEzZi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjM1LDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DL0ImUzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj42OCw1JSAvIDczLDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMta2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzLWt1by1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTMtc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBDZW7DoXJpb3M8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtYXhpYTMtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtIj5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzLXJlc3VsdCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLXRvcDo2cHgiPgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+U2VtIEJhcnJlaXJhIOKchTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgb2siIGlkPSJtYy1heGlhMy1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhMy1rdW8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIGRvd24iIGlkPSJtYy1heGlhMy1rZG8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLWF4aWEzLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo0cHgiIGlkPSJtYy1heGlhMy1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6MTBweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGFiZWwiPkFYSUEzIChCKSDCtyBCaWRpcmVjaW9uYWwgSU9OIEl0YcO6IMK3IFZlbmMgMDIvMTAvMjAyNjwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXRpY2tlciI+QVhJQTM8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wcmljZSBsb2FkaW5nIiBpZD0iYXhpYTNiLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0iYXhpYTNiLXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gUmVmLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCA1MCw2NTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5LRE8gKC0yMCUpPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+UiQgNDAsNTI8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S1VPICgrMjQlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDYyLDgxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkdhbmhvIHMvIGJhcnJlaXJhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPmF0w6kgKzMxLDIlIC8gKzIwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBjLyBiYXIuIGFsdGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4rNCUgZml4byAoMTIsMzMlIGEuYS4pPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MDIvMTAvMjAyNiDCtyA8c3BhbiBpZD0iYXhpYTNiLWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+MzUsMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gTUMvQiZTPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPjY4LDUlIC8gNzMsMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gS0RPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhM2Ita2RvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLVU88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzYi1rdW8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzYi1zdGF0dXMiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXRpdGxlIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIENlbsOhcmlvczwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhM2ItbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtIj5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzYi1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlNlbSBCYXJyZWlyYSDinIU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtYXhpYTNiLW5vYnIiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBBbHRhIEtVTzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLWF4aWEzYi1rdW8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+QmFyLiBCYWl4YSBLRE88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIGRvd24iIGlkPSJtYy1heGlhM2Ita2RvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhM2Itdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjRweCIgaWQ9Im1jLWF4aWEzYi1pbmZvIj7igJQ8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwb3MtY2FyZCIgc3R5bGU9Im1hcmdpbi10b3A6MTBweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtbGFiZWwiPlJPWE8zNCDCtyBCRFIgTnViYW5rIMK3IFByZWZpeGFkbyBjLyBCYXJyZWlyYSDCtyBWZW5jIDE2LzA3LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPlJPWE8zNDwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXByaWNlIGxvYWRpbmciIGlkPSJyb3hvMzQtcG9zLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9InBvcy1jaGciIGlkPSJyb3hvMzQtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDEyLDg4PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZSBST1hPRzEwNTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDEwLDUwPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MTYvMDcvMjAyNiDCtyA8c3BhbiBpZD0icm94bzM0LWRpYXMiPuKAlDwvc3Bhbj4gZGlhczwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Wb2wuIEltcGwuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+MzksMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gTUMvQiZTPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+NDMsMiUgLyA0NywxJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0icm94bzM0LWtkby1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U2l0dWHDp8Ojbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0icm94bzM0LXN0YXR1cyI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdGl0bGUiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgUHJvYi4gc3VjZXNzbzwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1yb3hvMzQtbG9hZGluZyIgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtIj5DYWxjdWxhbmRvLi4uPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLXJveG8zNC1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlByb2IuIFN1Y2Vzc288L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtcm94bzM0LXN1Y2Vzc28iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Q2FsbCBFeGVyY2lkYTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwiIGlkPSJtYy1yb3hvMzQtY2FsbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5LRE8gQXRpbmdpZG88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIiBpZD0ibWMtcm94bzM0LWtkbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtcm94bzM0LXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo0cHgiIGlkPSJtYy1yb3hvMzQtaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48c3Bhbj7wn5OBPC9zcGFuPiBFbmNlcnJhZGFzPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJvcGFjaXR5Oi42NTtib3JkZXItY29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCkiPkJCQVMzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+U3RyaWtlIEJCQVNIMjE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgMjEsNjUgwrcgUmVmIFIkIDIwLDY3PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj7inIUgODAlIGRvIGFsdm8gZW0gNzAlIGRvIHByYXpvPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJvcGFjaXR5Oi42NTtib3JkZXItY29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCkiPkFYSUEzIFNob3J0IFN0cmFuZ2xlPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Q2FsbCBWLiBBWElBSTUwNTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCA1MCw1MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+4pyFIEHDp8O1ZXMgbGliZXJhZGFzPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJvcGFjaXR5Oi42NTtib3JkZXItY29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NnB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCkiPlJPWE8zNCBQcmVmaXhhZG8gNywxJTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkVuY2VycmFkYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4wNC8wNi8yMDI2PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlJlc3VsdGFkbzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj7inIUgfjUsMTclICg3MiUgZG8gYWx2byk8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8ZGl2IGlkPSJ0YWItY2FsZW5kYXJpbyIgY2xhc3M9InRhYi1jb250ZW50Ij4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyO21hcmdpbi1ib3R0b206MTJweCI+CiAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjZyZW07Y29sb3I6dmFyKC0tbXV0ZWQpIj7wn4e68J+HuCDwn4en8J+HtyDwn4eq8J+HuiDwn4es8J+HpyDwn4eo8J+HsyDwn4ev8J+HtSDwn4ep8J+HqiDCtyBJbXBhY3QgTWVkaXVtKzwvZGl2PgogICAgPGJ1dHRvbiBvbmNsaWNrPSJsb2FkQ2FsZW5kYXIoKSIgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWFjY2VudCk7Y29sb3I6dmFyKC0tYWNjZW50KTtwYWRkaW5nOjRweCAxMHB4O2ZvbnQtc2l6ZTouNnJlbTtjdXJzb3I6cG9pbnRlcjtmb250LWZhbWlseTppbmhlcml0Ij7ihrsgQXR1YWxpemFyPC9idXR0b24+CiAgPC9kaXY+CiAgPGRpdiBpZD0iY2FsZW5kYXItYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoyMHB4O3RleHQtYWxpZ246Y2VudGVyIj5DbGlxdWUgZW0gQXR1YWxpemFyPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgQkFTRT0naHR0cHM6Ly90cmFkZXItZGVzay5vbnJlbmRlci5jb20nOwpjb25zdCBTRUc9ewogICdmaW5hbmNlaXJvJzogICBbJ0lUVUI0JywnQkJEQzQnLCdCQkFTMycsJ1NBTkIxMScsJ0IzU0EzJywnQlBBQzExJywnSVRTQTQnLCdCUlNSNicsJ0FCQ0I0JywnQk1HQjQnXSwKICAncGV0cm9sZW8nOiAgICAgWydQRVRSNCcsJ1BFVFIzJywnUFJJTzMnLCdCUkFWMycsJ1ZCQlIzJywnQ1NBTjMnLCdSRUNWMycsJ1VHUEEzJywnU0VRTDMnLCdFTkFUMyddLAogICdtaW5lcmFjYW8nOiAgICBbJ1ZBTEUzJywnR0dCUjQnLCdDU05BMycsJ1VTSU01JywnQlJBUDQnLCdGRVNBNCcsJ0NNSU4zJywnQ0JBVjMnLCdHT0FVNCcsJ1BHTU4zJ10sCiAgJ21hdGVyaWFpcyc6ICAgIFsnU1VaQjMnLCdLTEJOMTEnLCdEWENPMycsJ1VOSVA2JywnUkFOSTMnLCdPUlZSMycsJ1NNVE8zJywnRlJBUzMnLCdMUFNCMycsJ0RURVgzJ10sCiAgJ3V0aWxpZGFkZSc6ICAgIFsnQVhJQTMnLCdFUVRMMycsJ0NQRkUzJywnU0JTUDMnLCdDTUlHNCcsJ0VOR0kxMScsJ1RBRUUxMScsJ0FVUkUzJywnRUdJRTMnLCdDUExFMyddLAogICdjb25zdW1vX2NpY2xpY28nOlsnUkVOVDMnLCdMUkVOMycsJ01HTFUzJywnQ1lSRTMnLCdNUlZFMycsJ0FaWkEzJywnVklWQTMnLCdTQkZHMycsJ0NWQ0IzJywnTFdTQTMnXSwKICAnY29uc3Vtb19uYW8nOiAgWydBQkVWMycsJ0pCU1MzJywnQlJGUzMnLCdOQVRVMycsJ01ESUEzJywnQkVFRjMnLCdTTENFMycsJ01UUkUzJywnQ0FNTDMnLCdQQ0FSMyddLAogICdzYXVkZSc6ICAgICAgICBbJ1JET1IzJywnSEFQVjMnLCdGTFJZMycsJ0RBU0EzJywnUVVBTDMnLCdPTkNPMycsJ1BOVkwzJywnT0RQVjMnLCdNQVREMycsJ0FBTFIzJ10sCiAgJ2luZHVzdHJpYWlzJzogIFsnV0VHRTMnLCdFTUJSMycsJ1JBSUwzJywnVEdNQTMnLCdST01JMycsJ1ZMSUQzJywnVFVQWTMnLCdJUkJSMycsJ1BPTU80JywnRlJBUzMnXSwKICAndGlfdGVsZWNvbSc6ICAgWydWSVZUMycsJ1RJTVMzJywnVE9UVlMzJywnT0lCUjMnLCdMV1NBMycsJ01MQVMzJywnQU5JTTMnLCdQT1NJMycsJ0lOVEIzJywnQlJJVDMnXSwKfTsKY29uc3QgVVNfU0VHPXsnbWFnNyc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnR09PR0wnLCdNRVRBJywnVFNMQSddLCduYXNkYXExNSc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdDT1NUJywnTkZMWCcsJ1FDT00nLCdBTUQnLCdBREJFJywnSU5UQycsJ0NTQ08nXSwnc3AyMCc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdCUksuQicsJ0pQTScsJ0xMWScsJ1YnLCdVTkgnLCdYT00nLCdNQScsJ05GTFgnLCdQRycsJ0pOSicsJ0hEJywnQkFDJ10sJ2RqaTIwJzpbJ1VOSCcsJ0dTJywnSEQnLCdTSFcnLCdDQVQnLCdBWFAnLCdNQ0QnLCdBTUdOJywnVicsJ1RSVicsJ0lCTScsJ0pQTScsJ0hPTicsJ0NSTScsJ0NWWCcsJ0FBUEwnLCdNU0ZUJywnRElTJywnTktFJywnQkEnXX07CmNvbnN0IGZCUkw9dj0+diE9bnVsbD8nUiQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlVTRD12PT52IT1udWxsPydVUyQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlBUUz12PT52IT1udWxsP051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwpmdW5jdGlvbiBzZXRFbChpZCx0eHQpe2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKCFlKXJldHVybjtlLnRleHRDb250ZW50PXR4dDtlLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CmZ1bmN0aW9uIHNldENoZyhpZCxub3cscHJldix0eXBlKXtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47Y29uc3QgZGlmZj1ub3ctcHJldjtjb25zdCBwY3Q9KGRpZmYvTWF0aC5hYnMocHJldnx8MSkqMTAwKS50b0ZpeGVkKDIpO2NvbnN0IHNpZ249ZGlmZj49MD8nKyc6Jyc7aWYodHlwZT09PSdicmwnKWUudGV4dENvbnRlbnQ9c2lnbisnUiQgJytNYXRoLmFicyhkaWZmKS50b0ZpeGVkKDIpKycgKCcrc2lnbitwY3QrJyUpJztlbHNlIGlmKHR5cGU9PT0ndXNkJyllLnRleHRDb250ZW50PXNpZ24rZGlmZi50b0ZpeGVkKDIpKycgKCcrc2lnbitwY3QrJyUpJztlbHNlIGUudGV4dENvbnRlbnQ9c2lnbitNYXRoLmFicyhkaWZmKS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKycgKCcrc2lnbitwY3QrJyUpJztlLmNsYXNzTmFtZT0nYy1jaGFuZ2UgJysoZGlmZj4wPydjaGctdXAnOmRpZmY8MD8nY2hnLWRuJzonY2hnLWZsYXQnKTt9CmZ1bmN0aW9uIHN3aXRjaFRhYih0YWIsZWwpe2RvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy50YWInKS5mb3JFYWNoKHQ9PnQuY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJykpO2RvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy50YWItY29udGVudCcpLmZvckVhY2godD0+dC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RhYi0nK3RhYikuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7aWYoZWwpZWwuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7aWYodGFiPT09J2luZGljYWRvcmVzJyYmIXdpbmRvdy5faW5kTG9hZGVkKXt3aW5kb3cuX2luZExvYWRlZD10cnVlO2xvYWRJbmRpY2F0b3JzKCk7fWlmKHRhYj09PSdjYWxlbmRhcmlvJylsb2FkQ2FsZW5kYXIoKTt9CmZ1bmN0aW9uIHRvZ2dsZVNlZyhpZCl7Y29uc3QgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2JvZHktJytpZCk7Y29uc3QgYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2Fyci0nK2lkKTtpZighYilyZXR1cm47Y29uc3Qgb3Blbj1iLnN0eWxlLmRpc3BsYXkhPT0nYmxvY2snO2Iuc3R5bGUuZGlzcGxheT1vcGVuPydibG9jayc6J25vbmUnO2lmKGEpYS50ZXh0Q29udGVudD1vcGVuPyfilrInOifilrwnO2lmKG9wZW4mJiFiLmRhdGFzZXQubG9hZGVkKXtiLmRhdGFzZXQubG9hZGVkPScxJztsb2FkU2VnbWVudChpZCk7fX0KYXN5bmMgZnVuY3Rpb24gbG9hZFNlZ21lbnQoaWQpewogIGNvbnN0IGdyaWQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NncmlkLScraWQpOwogIGlmKCFncmlkKXJldHVybjsKICBjb25zdCBwZng9aWQrJ19fJzsgIC8vIHVuaXF1ZSBwcmVmaXggcGVyIHNlY3RvcgogIAogIGlmKFVTX1NFR1tpZF0pewogICAgY29uc3QgdGtzPVVTX1NFR1tpZF07CiAgICBncmlkLmlubmVySFRNTD10a3MubWFwKHQ9PnsKICAgICAgY29uc3QgdGlkPXQucmVwbGFjZSgvW15hLXpBLVowLTldL2csJ18nKTsKICAgICAgcmV0dXJuICc8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlVTPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj4nK3QrJzwvZGl2PicrCiAgICAgICAgJzxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PicrCiAgICAgICAgJzxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iJytwZngrdGlkKydfYyI+4oCUPC9kaXY+PC9kaXY+JzsKICAgIH0pLmpvaW4oJycpOwogICAgdHJ5ewogICAgICBjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy91cy9xdW90ZXM/dGlja2Vycz0nK3Rrcy5qb2luKCcsJykpOwogICAgICBpZighci5vaylyZXR1cm47CiAgICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICAgIE9iamVjdC5lbnRyaWVzKGQpLmZvckVhY2goKFt0LHZdKT0+ewogICAgICAgIGNvbnN0IHRpZD10LnJlcGxhY2UoL1teYS16QS1aMC05XS9nLCdfJyk7CiAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3RpZCsnX3AnKTsKICAgICAgICBjb25zdCBlYz1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChwZngrdGlkKydfYycpOwogICAgICAgIGlmKGVwJiZ2LnByaWNlKXtlcC50ZXh0Q29udGVudD0nJCcrTnVtYmVyKHYucHJpY2UpLnRvRml4ZWQoMik7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICBpZihlYyYmdi5wcmljZSYmdi5wcmV2KXNldENoZyhwZngrdGlkKydfYycsdi5wcmljZSx2LnByZXYsJ3VzZCcpOwogICAgICB9KTsKICAgIH1jYXRjaChlKXt9CiAgICByZXR1cm47CiAgfQogIAogIGNvbnN0IHRrcz1TRUdbaWRdOwogIGlmKCF0a3MpcmV0dXJuOwogIGdyaWQuaW5uZXJIVE1MPXRrcy5tYXAodD0+ewogICAgY29uc3QgdGlkPXQudG9Mb3dlckNhc2UoKTsKICAgIHJldHVybiAnPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPicrdCsnPC9kaXY+JysKICAgICAgJzxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9IicrcGZ4K3RpZCsnX3AiPuKAlDwvZGl2PicrCiAgICAgICc8ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9IicrcGZ4K3RpZCsnX2MiPuKAlDwvZGl2PjwvZGl2Pic7CiAgfSkuam9pbignJyk7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvdHYvYnJhemlsJyx7CiAgICAgIG1ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2Vyczp0a3MubWFwKHQ9PidCTUZCT1ZFU1BBOicrdCl9LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pCiAgICB9KTsKICAgIGlmKCFyLm9rKXJldHVybjsKICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICAoZC5kYXRhfHxbXSkuZm9yRWFjaCh4PT57CiAgICAgIGNvbnN0IHQ9eC5zLnJlcGxhY2UoJ0JNRkJPVkVTUEE6JywnJykudG9Mb3dlckNhc2UoKTsKICAgICAgY29uc3RbYyxjYV09eC5kfHxbXTsKICAgICAgaWYoYyE9bnVsbCl7CiAgICAgICAgY29uc3QgZXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocGZ4K3QrJ19wJyk7CiAgICAgICAgaWYoZXApe2VwLnRleHRDb250ZW50PWZCUkwoYyk7ZXAuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO30KICAgICAgICBzZXRDaGcocGZ4K3QrJ19jJyxjLGMtKGNhfHwwKSwnYnJsJyk7CiAgICAgIH0KICAgIH0pOwogIH1jYXRjaChlKXt9Cn0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hITCgpe3RyeXtjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkLkJUQ3x8MCk7aWYoYnA+MCl7c2V0RWwoJ2J0Yy1wJyxmVVNEKGJwKSk7c2V0Q2hnKCdidGMtYycsYnAsYnAqMC45OSwndXNkJyk7c2V0RWwoJ2J0Yy1wb3MtcCcsZlVTRChicCkpO310cnl7Y29uc3QgcjI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vYXBpLmh5cGVybGlxdWlkLnh5ei9pbmZvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3R5cGU6J2FsbE1pZHMnLGRleDoneHl6J30pfSk7aWYocjIub2spe2NvbnN0IGQyPWF3YWl0IHIyLmpzb24oKTtpZihkMlsneHl6OkNMJ10pc2V0RWwoJ2NsLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6Q0wnXSkudG9GaXhlZCgyKSk7aWYoZDJbJ3h5ejpHT0xEJ10pc2V0RWwoJ2dvbGQtcCcsJyQnK051bWJlcihkMlsneHl6OkdPTEQnXSkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSk7aWYoZDJbJ3h5ejpTSUxWRVInXSlzZXRFbCgnc2lsdmVyLXAnLCckJytwYXJzZUZsb2F0KGQyWyd4eXo6U0lMVkVSJ10pLnRvRml4ZWQoMikpO2lmKGQyWyd4eXo6Q09QUEVSJ10pc2V0RWwoJ2NvcHBlci1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OkNPUFBFUiddKS50b0ZpeGVkKDMpKTt9fWNhdGNoKGUpe319Y2F0Y2goZSl7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hUVigpe2NvbnN0IG91dD17fTt0cnl7Y29uc3QgdGtzPVsnQk1GQk9WRVNQQTpQRVRSNCcsJ0JNRkJPVkVTUEE6SVRVQjQnLCdCTUZCT1ZFU1BBOlZBTEUzJywnQk1GQk9WRVNQQTpCQkRDNCcsJ0JNRkJPVkVTUEE6QUJFVjMnLCdCTUZCT1ZFU1BBOkJCQVMzJywnQk1GQk9WRVNQQTpXRUdFMycsJ0JNRkJPVkVTUEE6SUJPViddO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL3R2L2JyYXppbCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOnRrc30sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KTtpZihyLm9rKXtjb25zdCBkPWF3YWl0IHIuanNvbigpOyhkLmRhdGF8fFtdKS5mb3JFYWNoKHg9Pntjb25zdFtjLGNhXT14LmR8fFtdO2lmKGMhPW51bGwpb3V0W3guc109e3A6Yyx2OmMtKGNhfHwwKX07fSk7fX1jYXRjaChlKXt9dHJ5e2NvbnN0IHJyPWF3YWl0IGZldGNoKEJBU0UrJy9pbmRpY2F0b3JzL1JPWE8zNC5TQScpO2lmKHJyLm9rKXtjb25zdCBkZD1hd2FpdCByci5qc29uKCk7aWYoZGQucHJpY2Upe3NldEVsKCdyb3hvMzRxLXAnLGZCUkwoZGQucHJpY2UpKTtzZXRDaGcoJ3JveG8zNHEtYycsZGQucHJpY2UsZGQucHJpY2UqMC45OSwnYnJsJyk7fX19Y2F0Y2goZSl7fXJldHVybiBvdXQ7fQphc3luYyBmdW5jdGlvbiBmZXRjaEZ1dHVyZXMoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvZnV0dXJlcycpO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hGdW5kaW5nKCl7CiAgdHJ5ewogICAgLy8gVGVudGEgQmluYW5jZSBkaXJldG8gcHJpbWVpcm8KICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goJ2h0dHBzOi8vZmFwaS5iaW5hbmNlLmNvbS9mYXBpL3YxL3ByZW1pdW1JbmRleD9zeW1ib2w9QlRDVVNEVCcpOwogICAgaWYoci5vayl7CiAgICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICAgIGNvbnN0IHJhdGU9cGFyc2VGbG9hdChkLmxhc3RGdW5kaW5nUmF0ZXx8MCkqMTAwOwogICAgICBzZXRFbCgnYnRjLWZ1bmQnLHJhdGUudG9GaXhlZCg0KSsnJScpOwogICAgICByZXR1cm47CiAgICB9CiAgfWNhdGNoKGUpe30KICB0cnl7CiAgICBjb25zdCByMj1hd2FpdCBmZXRjaChCQVNFKycvYmluYW5jZS9mdW5kaW5nJyk7CiAgICBpZighcjIub2spcmV0dXJuOwogICAgY29uc3QgZD1hd2FpdCByMi5qc29uKCk7CiAgICBjb25zdCBmPUFycmF5LmlzQXJyYXkoZCk/ZC5maW5kKHg9Pnguc3ltYm9sPT09J0JUQ1VTRFQnKTpudWxsOwogICAgaWYoZil7c2V0RWwoJ2J0Yy1mdW5kJywocGFyc2VGbG9hdChmLmZ1bmRpbmdSYXRlfHwwKSoxMDApLnRvRml4ZWQoNCkrJyUnKTt9CiAgfWNhdGNoKGUpe30KfQpmdW5jdGlvbiBkb01hY3JvKHR2LGZ1dHVyZXMpe2NvbnN0IGliRD10dlsnQk1GQk9WRVNQQTpJQk9WJ107aWYoaWJEKXtzZXRFbCgnaWJvdi1wJyxmUFRTKGliRC5wKSk7c2V0Q2hnKCdpYm92LWMnLGliRC5wLGliRC52LCdwdHMnKTt9W1snUEVUUjQnLCdwZXRyNHEnXSxbJ0lUVUI0JywnaXR1YjRxJ10sWydWQUxFMycsJ3ZhbGUzcSddLFsnQkJEQzQnLCdiYmRjNHEnXSxbJ0FCRVYzJywnYWJldjNxJ10sWydCQkFTMycsJ2JiYXMzcSddLFsnV0VHRTMnLCd3ZWdlM3EnXV0uZm9yRWFjaCgoW3QsaWRdKT0+e2NvbnN0IGQ9dHZbJ0JNRkJPVkVTUEE6Jyt0XTtpZihkKXtzZXRFbChpZCsnLXAnLGZCUkwoZC5wKSk7c2V0Q2hnKGlkKyctYycsZC5wLGQudiwnYnJsJyk7fX0pO2ZldGNoKEJBU0UrJy9mdXR1cmVzJykudGhlbihyPT5yLmpzb24oKSkudGhlbihkPT57aWYoZC51c2QmJmQudXNkLnByaWNlKXtzZXRFbCgndXNkLXAnLGZCUkwoZC51c2QucHJpY2UpKTtzZXRDaGcoJ3VzZC1jJyxkLnVzZC5wcmljZSxkLnVzZC5wcmV2fHxkLnVzZC5wcmljZSwnYnJsJyk7fWVsc2V7ZmV0Y2goQkFTRSsnL3R2L2ZvcmV4Jyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LGJvZHk6SlNPTi5zdHJpbmdpZnkoe3N5bWJvbHM6e3RpY2tlcnM6WydGWDpVU0RCUkwnXX0sY29sdW1uczpbJ2Nsb3NlJywnY2hhbmdlX2FicyddfSl9KS50aGVuKHI9PnIuanNvbigpKS50aGVuKGQ9Pntjb25zdCB4PWQuZGF0YT8uWzBdO2lmKCF4KXJldHVybjtjb25zdFtjLGNhXT14LmR8fFtdO2lmKGMpe3NldEVsKCd1c2QtcCcsZkJSTChjKSk7c2V0Q2hnKCd1c2QtYycsYyxjLShjYXx8MCksJ2JybCcpO319KS5jYXRjaCgoKT0+e30pO319KS5jYXRjaCgoKT0+e30pO2lmKGZ1dHVyZXMpe2NvbnN0IGY9ZnV0dXJlcztjb25zdCBhZj0oaWQsdmFsKT0+e2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKGUpe2UudGV4dENvbnRlbnQ9dmFsO2UuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO319O2lmKGYuZGppPy5wcmljZSl7YWYoJ2RqaS1wJyxmUFRTKGYuZGppLnByaWNlKSk7c2V0Q2hnKCdkamktYycsZi5kamkucHJpY2UsZi5kamkucHJldiwncHRzJyk7fWlmKGYuZXNmPy5wcmljZSl7YWYoJ2VzZi1wJyxmUFRTKGYuZXNmLnByaWNlKSk7c2V0Q2hnKCdlc2YtYycsZi5lc2YucHJpY2UsZi5lc2YucHJldiwncHRzJyk7fWlmKGYubnFmPy5wcmljZSl7YWYoJ25xZi1wJyxmUFRTKGYubnFmLnByaWNlKSk7c2V0Q2hnKCducWYtYycsZi5ucWYucHJpY2UsZi5ucWYucHJldiwncHRzJyk7fWlmKGYud2luPy5wcmljZSl7YWYoJ3dpbi1wJyxmUFRTKGYud2luLnByaWNlKSk7c2V0Q2hnKCd3aW4tYycsZi53aW4ucHJpY2UsZi53aW4ucHJldiwncHRzJyk7fWlmKGYudml4Py5wcmljZSl7YWYoJ3ZpeC1wJyxOdW1iZXIoZi52aXgucHJpY2UpLnRvRml4ZWQoMikpO3NldENoZygndml4LWMnLGYudml4LnByaWNlLGYudml4LnByZXYsJ3VzZCcpO31pZihmLmR4eT8ucHJpY2Upe2FmKCdkeHktcCcsTnVtYmVyKGYuZHh5LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ2R4eS1jJyxmLmR4eS5wcmljZSxmLmR4eS5wcmV2LCd1c2QnKTt9fX0KZnVuY3Rpb24gZG9Qb3NpdGlvbnModHYpe2NvbnN0IHB0RD10dlsnQk1GQk9WRVNQQTpQRVRSNCddO2NvbnN0IHB0UD1wdEQ/LnB8fDQwLHB0Vj1wdEQ/LnZ8fDQwO3NldEVsKCdwdC1wb3MtcCcsZkJSTChwdFApKTtzZXRDaGcoJ3B0LXBvcy1jJyxwdFAscHRWLCdicmwnKTtzZXRFbCgncHQtaXRtJywnK1IkICcrKHB0UC0zMC44NSkudG9GaXhlZCgyKSsnIGFjaW1hIGRvIHN0cmlrZScpO2NvbnN0IHZsRD10dlsnQk1GQk9WRVNQQTpWQUxFMyddO2NvbnN0IHZsUD12bEQ/LnB8fDc4LHZsVj12bEQ/LnZ8fDc4O3NldEVsKCd2bC1wb3MtcCcsZkJSTCh2bFApKTtzZXRDaGcoJ3ZsLXBvcy1jJyx2bFAsdmxWLCdicmwnKTtzZXRFbCgndmwtaXRtJywnK1IkICcrKHZsUC01Ny40MCkudG9GaXhlZCgyKSsnIGFjaW1hIGRvIHN0cmlrZScpO2NvbnN0IGNkPShkcyxlaWQpPT57Y29uc3Qgdj1uZXcgRGF0ZShkcyk7Y29uc3QgZD1NYXRoLm1heCgwLE1hdGguY2VpbCgodi1uZXcgRGF0ZSgpKS84NjRlNSkpO2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoZWlkKTtpZihlKWUudGV4dENvbnRlbnQ9ZDt9O2NkKCcyMDI2LTEyLTE3JywncHQtZGlhcycpO2NkKCcyMDI3LTAyLTE4JywndmwtZGlhcycpO2NkKCcyMDI2LTA5LTE0JywnYXhpYTNmLWRpYXMnKTtjZCgnMjAyNi0xMC0wMicsJ2F4aWEzYi1kaWFzJyk7Y2QoJzIwMjYtMDctMTYnLCdyb3hvMzQtZGlhcycpO3NldFRpbWVvdXQoYXN5bmMoKT0+e3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9pbmRpY2F0b3JzL0FYSUEzLlNBJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJpY2UpcmV0dXJuO2NvbnN0IHA9ZC5wcmljZTtzZXRFbCgnYXhpYTMtcG9zLXAnLGZCUkwocCkpO3NldEVsKCdheGlhM2ItcG9zLXAnLGZCUkwocCkpO2NvbnN0IGtkb0E9NDMuNTEsa3VvQT02OC43NixrZG9CPTQwLjUyLGt1b0I9NjIuODE7Y29uc3QgZEE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzLWtkby1kaXN0Jyk7aWYoZEEpZEEudGV4dENvbnRlbnQ9KChwLWtkb0EpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7Y29uc3QgdUE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzLWt1by1kaXN0Jyk7aWYodUEpdUEudGV4dENvbnRlbnQ9KChrdW9BLXApL3AqMTAwKS50b0ZpeGVkKDEpKyclIHBhcmEgbyBLVU8nO2NvbnN0IHNBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1zdGF0dXMnKTtpZihzQSl7c0EudGV4dENvbnRlbnQ9cDw9a2RvQT8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1b0E/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NBLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PWtkb0F8fHA+PWt1b0E/J3dhcm4nOidvaycpO31jb25zdCBkQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTNiLWtkby1kaXN0Jyk7aWYoZEIpZEIudGV4dENvbnRlbnQ9KChwLWtkb0IpL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRvIEtETyc7Y29uc3QgdUI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1rdW8tZGlzdCcpO2lmKHVCKXVCLnRleHRDb250ZW50PSgoa3VvQi1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJztjb25zdCBzQj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTNiLXN0YXR1cycpO2lmKHNCKXtzQi50ZXh0Q29udGVudD1wPD1rZG9CPyfwn5S0IEtETyBBVElOR0lETyc6cD49a3VvQj8n4pqgIEtVTyBBVElOR0lETyc6J+KchSBObyByYW5nZSc7c0IuY2xhc3NOYW1lPSdzYi12YWwgJysocDw9a2RvQnx8cD49a3VvQj8nd2Fybic6J29rJyk7fX1jYXRjaChlKXt9fSwyMDAwKTtzZXRUaW1lb3V0KGFzeW5jKCk9Pnt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy9ST1hPMzQuU0EnKTtpZighci5vaylyZXR1cm47Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZighZC5wcmljZSlyZXR1cm47Y29uc3QgcD1kLnByaWNlO3NldEVsKCdyb3hvMzQtcG9zLXAnLGZCUkwocCkpO2NvbnN0IGRlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyb3hvMzQta2RvLWRpc3QnKTtpZihkZSlkZS50ZXh0Q29udGVudD0oKHAtMTAuNTApL3AqMTAwKS50b0ZpeGVkKDEpKyclIGFjaW1hIGRhIGJhcnJlaXJhJztjb25zdCBzZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm94bzM0LXN0YXR1cycpO2lmKHNlKXtzZS50ZXh0Q29udGVudD1wPD0xMC41MD8n8J+UtCBCQVJSRUlSQSBBVElOR0lEQSc6J+KchSBBY2ltYSBkYSBiYXJyZWlyYSc7c2UuY2xhc3NOYW1lPSdzYi12YWwgJysocDw9MTAuNTA/J2l0bSc6J29rJyk7fX1jYXRjaChlKXt9fSwzMDAwKTt9CmFzeW5jIGZ1bmN0aW9uIHJ1bk1DRm9yQXRpdm8odGlja2VyLHN0cmlrZSxkaWFzLGxvYWRJZCxyZXNJZCxzdHJpa2VJZCx2b2xJZCxpbmZvSWQpe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL21vbnRlY2FybG8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoe3RpY2tlcixrX2NhbGw6c3RyaWtlLGtfcHV0OnN0cmlrZSx0X2RheXM6ZGlhcyxuOjUwMDB9KX0pO2NsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKGxvYWRJZCkuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQocmVzSWQpLnN0eWxlLmRpc3BsYXk9J2Jsb2NrJztjb25zdCBwcm9iPU51bWJlcihkLnByb2JfcHV0X2V4ZXJjaWRhfHwwKTtjb25zdCBzRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoc3RyaWtlSWQpO3NFbC50ZXh0Q29udGVudD1wcm9iLnRvRml4ZWQoMikrJyUnO3NFbC5jbGFzc05hbWU9J2luZC12YWwgJysocHJvYj4zMD8nb2snOnByb2I+MTU/J3dhcm4nOidkb3duJyk7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQodm9sSWQpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKGluZm9JZCkudGV4dENvbnRlbnQ9J1ZvbC5oaXN0LiAnK2Qudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUgwrcgUHJvYi4gY29tIHZvbC5oaXN0LiAoTUMpIHZzIHZvbC5pbXBsLiAoQiZTKSBzw6NvIGRpZmVyZW50ZXMg4oCUIHZlciBwb3Npw6fDo28nO31jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChsb2FkSWQpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCdpbmRpc3BvbsOtdmVsJyk7fX0KYXN5bmMgZnVuY3Rpb24gcnVuTUNCYXJyaWVyKHRpY2tlcixlbnRyeSxrZG8sa3VvLGRpYXMscHJpY2UscHJlZml4KXtwcmVmaXg9cHJlZml4fHwnYXhpYTMnO3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApO2NvbnN0IGJvZHk9e3RpY2tlcixlbnRyeSxrZG8sa3VvLHRfZGF5czpkaWFzLG46MzAwMH07aWYocHJpY2U+MClib2R5LnByaWNlPXByaWNlO2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL21vbnRlY2FybG8vYmFycmllcicse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeShib2R5KX0pO2NsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKS5zdHlsZS5kaXNwbGF5PSdub25lJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1yZXN1bHQnKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kyctbm9icicpLnRleHRDb250ZW50PWQucHJvYl9zZW1fYmFycmVpcmEudG9GaXhlZCgyKSsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kycta3VvJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2FsdGEudG9GaXhlZCgyKSsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4Kycta2RvJykudGV4dENvbnRlbnQ9ZC5wcm9iX2JhcnJlaXJhX2JhaXhhLnRvRml4ZWQoMikrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLXZvbCcpLnRleHRDb250ZW50PWQudm9sYXRpbGlkYWRlX2hpc3RvcmljYV9wY3QrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWluZm8nKS50ZXh0Q29udGVudD0nUHJlw6dvIFIkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua2RvKycgwrcgS1VPIFIkICcrZC5rdW8rJyDCtyAnK2QuY2VuYXJpb3MudG9Mb2NhbGVTdHJpbmcoKSsnIGNlbsOhcmlvcyc7fWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWxvYWRpbmcnKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwnaW5kaXNwb27DrXZlbCcpO319CmFzeW5jIGZ1bmN0aW9uIHJ1bk1DUHJlZml4YWRvKHRpY2tlcixlbnRyeSxrZG8sZGlhcyxwcmljZSl7dHJ5e2NvbnN0IGN0cmw9bmV3IEFib3J0Q29udHJvbGxlcigpO2NvbnN0IHRvPXNldFRpbWVvdXQoKCk9PmN0cmwuYWJvcnQoKSwyNTAwMCk7Y29uc3QgYm9keT17dGlja2VyLGtfY2FsbDplbnRyeSxrX3B1dDplbnRyeSx0X2RheXM6ZGlhcyxrbm9ja19kb3duOmtkbyxuOjUwMDB9O2lmKHByaWNlPjApYm9keS5wcmljZT1wcmljZTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KGJvZHkpfSk7Y2xlYXJUaW1lb3V0KHRvKTtpZighci5vayl0aHJvdyAwO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoZC5lcnJvcil0aHJvdyBuZXcgRXJyb3IoZC5lcnJvcik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1sb2FkaW5nJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1yZXN1bHQnKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7Y29uc3Qgc0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtc3VjZXNzbycpO3NFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX3N1Y2Vzc28pLnRvRml4ZWQoMikrJyUnO3NFbC5jbGFzc05hbWU9J2luZC12YWwgJysoZC5wcm9iX3N1Y2Vzc28+NzA/J29rJzpkLnByb2Jfc3VjZXNzbz41MD8nd2Fybic6J2Rvd24nKTtjb25zdCBjRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1jYWxsJyk7aWYoY0VsKWNFbC50ZXh0Q29udGVudD1OdW1iZXIoZC5wcm9iX2NhbGxfZXhlcmNpZGEpLnRvRml4ZWQoMikrJyUnO2NvbnN0IGtFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWtkbycpO2lmKGtFbClrRWwudGV4dENvbnRlbnQ9ZC5wcm9iX2tkb19hdGluZ2lkbyE9bnVsbD9OdW1iZXIoZC5wcm9iX2tkb19hdGluZ2lkbykudG9GaXhlZCgyKSsnJSc6J+KAlCc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC12b2wnKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LWluZm8nKS50ZXh0Q29udGVudD0nUHJlw6dvIFIkICcrZC5wcmVjb19hdHVhbCsnIMK3IEtETyBSJCAnK2Qua25vY2tfZG93bisnIMK3ICcrZC5jZW5hcmlvcy50b0xvY2FsZVN0cmluZygpKycgY2Vuw6FyaW9zJzt9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1sb2FkaW5nJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J2luZGlzcG9uw612ZWwnKTt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEluZGljYXRvcnModGlja2VyKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy8nK3RpY2tlcik7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEJUQ0luZGljYXRvcnMoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvYnRjL2luZGljYXRvcnMnKTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZldGNoQlRDQ3ljbGUoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvYnRjL2N5Y2xlJyk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEZlYXJHcmVlZCgpewogIHRyeXsKICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2ZlYXJncmVlZCcpOwogICAgaWYoIXIub2spcmV0dXJuOwogICAgY29uc3QgZD1hd2FpdCByLmpzb24oKTsKICAgIGNvbnN0IHY9ZC52YWx1ZXx8NTA7CiAgICBjb25zdCBjbHM9djw9MjU/J3ZhcigtLXJlZCknOnY8PTQ1Pyd2YXIoLS13YXJuKSc6djw9NzU/J3ZhcigtLWFjY2VudCknOid2YXIoLS1ncmVlbiknOwogICAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ZlYXItZ3JlZWQtYXJlYScpOwogICAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTRweCI+JysKICAgICAgJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206OHB4Ij7wn5ixIEZlYXIgJiBHcmVlZCBJbmRleDwvZGl2PicrCiAgICAgICc8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMnB4Ij4nKwogICAgICAgICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MnJlbTtmb250LXdlaWdodDo4MDA7Y29sb3I6JytjbHMrJyI+Jyt2Kyc8L2Rpdj4nKwogICAgICAgICc8ZGl2IHN0eWxlPSJmb250LXNpemU6Ljg1cmVtO2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjonK2NscysnIj4nKyhkLnZhbHVlX2NsYXNzaWZpY2F0aW9ufHwnTmV1dHJvJykrJzwvZGl2PicrCiAgICAgICc8L2Rpdj48L2Rpdj4nOwogICAgc2V0RWwoJ2ZnLXZhbCcsU3RyaW5nKHYpKTtzZXRFbCgnZmctbGJsJyxkLnZhbHVlX2NsYXNzaWZpY2F0aW9ufHwnTmV1dHJvJyk7CiAgICAvLyBCdXNjYSBCVEMgcHJpY2UgcGFyYSBvIGNhcmQgRiZHCiAgICB0cnl7CiAgICAgIGNvbnN0IHJiPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJ30pfSk7CiAgICAgIGlmKHJiLm9rKXtjb25zdCBkYj1hd2FpdCByYi5qc29uKCk7Y29uc3QgYnA9cGFyc2VGbG9hdChkYi5CVEN8fDApO2lmKGJwPjApe3NldEVsKCdidGMtaW5kLXByaWNlJyxmVVNEKGJwKSk7c2V0RWwoJ2J0Yy1wJyxmVVNEKGJwKSk7fX0KICAgIH1jYXRjaChlMil7fQogIH1jYXRjaChlKXt9Cn0KZnVuY3Rpb24gcmVuZGVySW5kaWNhdG9ycyhhcmVhSWQsZGF0YSxzaG93QWxsKXsKICBjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZChhcmVhSWQpOwogIGlmKCFlbClyZXR1cm47CiAgaWYoIWRhdGEpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0td2Fybik7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEycHgiPuKPsyBTZW0gcmVzcG9zdGEg4oCUIGNsaXF1ZSDihrs8L2Rpdj4nO3JldHVybjt9CiAgaWYoZGF0YS5lcnJvcil7ZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1kYW5nZXIpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMnB4Ij7imqAgJytkYXRhLmVycm9yKyc8YnI+PHNtYWxsIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCkiPkNsaXF1ZSDihrsgcGFyYSB0ZW50YXIgbm92YW1lbnRlPC9zbWFsbD48L2Rpdj4nO3JldHVybjt9CiAgY29uc3QgaW5kcz1kYXRhLmluZGljYWRvcmVzfHxbXTsKICBjb25zdCBzY29yZT1kYXRhLnNjb3JlX3RvdGFsOwogIGNvbnN0IHByZWNvPWRhdGEucHJlY29fYXR1YWw7CiAgY29uc3QgZ3JhaGFtPWRhdGEuZ3JhaGFtX3ZhbHVlOwogIGNvbnN0IHVwc2lkZT1kYXRhLnVwc2lkZV9ncmFoYW07CiAgY29uc3Qgc2V0b3I9ZGF0YS5zZXRvcnx8Jyc7CgogIGxldCBodG1sPScnOwogIC8vIFNjb3JlIGhlYWRlcgogIGlmKHNjb3JlIT1udWxsKXsKICAgIGNvbnN0IHNjPU51bWJlcihzY29yZSk7CiAgICBjb25zdCBzY29yZUNvbG9yPXNjPj02NT8ndmFyKC0tZ3JlZW4pJzpzYz49NDA/J3ZhcigtLXdhcm4pJzondmFyKC0tcmVkKSc7CiAgICBjb25zdCBzY29yZUxhYmVsPXNjPj02NT8nQ29tcHJhIOKWsic6c2M+PTQwPydOZXV0cm8g4oaSJzonVmVuZGEg4pa8JzsKICAgIGh0bWwrPSc8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTJweDttYXJnaW4tYm90dG9tOjhweDtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnIgMWZyO2dhcDo4cHg7dGV4dC1hbGlnbjpjZW50ZXIiPicrCiAgICAgICc8ZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbToycHgiPlNDT1JFPC9kaXY+JysKICAgICAgJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxLjZyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOicrc2NvcmVDb2xvcisnIj4nK3NjKyc8L2Rpdj4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjonK3Njb3JlQ29sb3IrJyI+JytzY29yZUxhYmVsKyc8L2Rpdj48L2Rpdj4nKwogICAgICAnPGRpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi1ib3R0b206MnB4Ij5DT1RBw4fDg088L2Rpdj4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjFyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLXRleHQpIj4nKyhwcmVjbz8nUiQgJytOdW1iZXIocHJlY28pLnRvRml4ZWQoMik6J+KAlCcpKyc8L2Rpdj4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKSI+JytzZXRvcisnPC9kaXY+PC9kaXY+JysKICAgICAgJzxkaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjJweCI+R1JBSEFNPC9kaXY+JysKICAgICAgJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxcmVtO2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjonKyh1cHNpZGUmJnVwc2lkZT4wPyd2YXIoLS1ncmVlbiknOid2YXIoLS1yZWQpJykrJyI+JysoZ3JhaGFtPydSJCAnK051bWJlcihncmFoYW0pLnRvRml4ZWQoMik6J+KAlCcpKyc8L2Rpdj4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi41cmVtO2NvbG9yOicrKHVwc2lkZSYmdXBzaWRlPjA/J3ZhcigtLWdyZWVuKSc6J3ZhcigtLXJlZCknKSsnIj4nKyh1cHNpZGU/dXBzaWRlKyclIHVwc2lkZSc6J+KAlCcpKyc8L2Rpdj48L2Rpdj4nKwogICAgICAnPC9kaXY+JzsKICB9CiAgLy8gSW5kaWNhdG9ycyBncmlkCiAgaHRtbCs9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NXB4Ij4nOwogIChzaG93QWxsP2luZHM6aW5kcy5zbGljZSgwLDEwKSkuZm9yRWFjaChmdW5jdGlvbihpKXsKICAgIGNvbnN0IHM9aS5zaW5hbHx8aS5zaWduYWx8fCcnOwogICAgY29uc3QgY2xzPXM9PT0nQWx0YSd8fHM9PT0nU29icmV2ZW5kYSc/J29rJzpzPT09J0JhaXhhJ3x8cz09PSdTb2JyZWNvbXByYSc/J2Rvd24nOid3YXJuJzsKICAgIGNvbnN0IGFycm93PXM9PT0nQWx0YSc/J+KWsic6cz09PSdCYWl4YSc/J+KWvCc6J+KGkic7CiAgICBodG1sKz0nPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjdweDtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6Y2VudGVyIj4nKwogICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi41cmVtO2NvbG9yOnZhcigtLW11dGVkKSI+JysoaS5ub21lfHxpLm5hbWV8fCcnKSsnPC9kaXY+JysKICAgICAgJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNzVyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLScrKGNscz09PSdvayc/J2dyZWVuJzpjbHM9PT0nZG93bic/J3JlZCc6J3dhcm4nKSsnKSI+JysoaS52YWxvciE9bnVsbD9pLnZhbG9yOifigJQnKSsnICcrYXJyb3crJzwvZGl2PjwvZGl2Pic7CiAgfSk7CiAgaHRtbCs9JzwvZGl2Pic7CiAgZWwuaW5uZXJIVE1MPWh0bWw7Cn0KCmZ1bmN0aW9uIHJlbmRlckJUQ0luZGljYXRvcnMoZGF0YSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2J0Yy1pbmQtYXJlYScpO2lmKCFlbHx8IWRhdGEpcmV0dXJuO2xldCBodG1sPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweCI+JztpZihkYXRhLnJzaV9zZW1hbmFsIT1udWxsKXtodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UlNJIFNlbWFuYWw8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsICcrKGRhdGEucnNpX3NlbWFuYWw8MzA/J29rJzpkYXRhLnJzaV9zZW1hbmFsPjcwPydkb3duJzond2FybicpKyciPicrZGF0YS5yc2lfc2VtYW5hbC50b0ZpeGVkKDEpKyc8L2Rpdj48L2Rpdj4nO3NldEVsKCdidGMtcnNpJyxkYXRhLnJzaV9zZW1hbmFsLnRvRml4ZWQoMSkpO31pZihkYXRhLm1tMjAwKWh0bWwrPSc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5NTSAyMDBkPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nK051bWJlcihkYXRhLm1tMjAwKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKyc8L2Rpdj48L2Rpdj4nO2h0bWwrPSc8L2Rpdj4nO2VsLmlubmVySFRNTD1odG1sO2lmKGRhdGEucHJlY29fYXR1YWwpe3NldEVsKCdidGMtaW5kLXByaWNlJywnJCcrTnVtYmVyKGRhdGEucHJlY29fYXR1YWwpLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpO319CmZ1bmN0aW9uIHJlbmRlckJUQ0N5Y2xlKGQpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidGMtY3ljbGUtYXJlYScpO2lmKCFlbHx8IWR8fGQuZXJyb3IpcmV0dXJuO2NvbnN0IGZVPXY9PnY/JyQnK051bWJlcih2KS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnO2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHg7bWFyZ2luLWJvdHRvbTo4cHgiPjxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk1WUlYgWi1TY29yZTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgJysoZC5tdnJ2X3pzY29yZT8udmFsdWU8MT8nb2snOmQubXZydl96c2NvcmU/LnZhbHVlPDM/J3dhcm4nOidkb3duJykrJyI+JytkLm12cnZfenNjb3JlPy52YWx1ZSsnPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCkiPicrZC5tdnJ2X3pzY29yZT8ubGFiZWwrJzwvZGl2PjwvZGl2PjxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPk5VUEw8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrKChkLm51cGw/LnZhbHVlfHwwKSoxMDApLnRvRml4ZWQoMCkrJyU8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQ4cmVtO2NvbG9yOnZhcigtLW11dGVkKSI+JytkLm51cGw/LmxhYmVsKyc8L2Rpdj48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5QdWVsbCBNdWx0aXBsZTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JytkLnB1ZWxsPy52YWx1ZSsnPC9kaXY+PC9kaXY+PGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+MjAwVyBNQTwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JytmVShkLm1hMjAwdykrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDhyZW07Y29sb3I6dmFyKC0tbXV0ZWQpIj4nKyhkLm1hMjAwd19wY3Q/JysnK2QubWEyMDB3X3BjdCsnJSc6JycpKyc8L2Rpdj48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5SYWluYm93PC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nKyhkLnJhaW5ib3c/LmJhbmR8fCfigJQnKSsnPC9kaXY+PC9kaXY+PGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UGkgQ3ljbGU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIj4nK2ZVKGQucGlfY3ljbGU/LmRpc3RhbmNlKSsnIGRpc3QuPC9kaXY+PC9kaXY+PC9kaXY+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjhweDtmb250LXNpemU6LjZyZW07Y29sb3I6dmFyKC0tYWNjZW50KSI+JysoZC5waV9jeWNsZT8uc2lnbmFsfHwnJykrJzwvZGl2Pic7fQphc3luYyBmdW5jdGlvbiBsb2FkSW5kaWNhdG9ycygpewogIC8vIEJUQyBwcmltZWlybwogIGNvbnN0W2J0YyxjeWNsZV09YXdhaXQgUHJvbWlzZS5hbGwoW2ZldGNoQlRDSW5kaWNhdG9ycygpLGZldGNoQlRDQ3ljbGUoKV0pOwogIHJlbmRlckJUQ0luZGljYXRvcnMoYnRjKTtyZW5kZXJCVENDeWNsZShjeWNsZSk7ZmV0Y2hGZWFyR3JlZWQoKTsKICAvLyBTdG9ja3MgZW0gcGFyYWxlbG8gY29tIHRpbWVvdXQgaW5kaXZpZHVhbCBkZSAyMHMKICBjb25zdCBzdG9ja3M9WwogICAgWydQRVRSNC5TQScsJ3BldHI0LWluZC1hcmVhJ10sWydWQUxFMy5TQScsJ3ZhbGUzLWluZC1hcmVhJ10sCiAgICBbJ0JCQVMzLlNBJywnYmJhczMtaW5kLWFyZWEnXSxbJ0FYSUEzLlNBJywnYXhpYTMtaW5kLWFyZWEnXSwKICAgIFsnUk9YTzM0LlNBJywncm94bzM0LWluZC1hcmVhJ10KICBdOwogIGNvbnN0IHdpdGhUaW1lb3V0PShwcm9taXNlLG1zLGZhbGxiYWNrKT0+ewogICAgcmV0dXJuIFByb21pc2UucmFjZShbcHJvbWlzZSwgbmV3IFByb21pc2Uocj0+c2V0VGltZW91dCgoKT0+cihmYWxsYmFjayksbXMpKV0pOwogIH07CiAgY29uc3QgcmVzdWx0cz1hd2FpdCBQcm9taXNlLmFsbCgKICAgIHN0b2Nrcy5tYXAoKFt0aWNrZXJdKT0+d2l0aFRpbWVvdXQoZmV0Y2hJbmRpY2F0b3JzKHRpY2tlciksMzAwMDAse2Vycm9yOidUaW1lb3V0IDMwcyd9KSkKICApOwogIHN0b2Nrcy5mb3JFYWNoKChbLGFyZWFJZF0saSk9PnJlbmRlckluZGljYXRvcnMoYXJlYUlkLHJlc3VsdHNbaV0sdHJ1ZSkpOwp9CmNvbnN0IENBTF9GTEFHUz17J1VTRCc6J/Cfh7rwn4e4JywnQlJMJzon8J+Hp/Cfh7cnLCdFVVInOifwn4eq8J+HuicsJ0dCUCc6J/Cfh6zwn4enJywnQ05ZJzon8J+HqPCfh7MnLCdKUFknOifwn4ev8J+HtScsJ0NBRCc6J/Cfh6jwn4emJywnQVVEJzon8J+HpvCfh7onfTsKYXN5bmMgZnVuY3Rpb24gbG9hZENhbGVuZGFyKCl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbGVuZGFyLWFyZWEnKTtpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlcjthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2Pic7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2NhbGVuZGFyJyk7aWYoIXIub2spdGhyb3cgbmV3IEVycm9yKCdIVFRQICcrci5zdGF0dXMpO2NvbnN0IGV2ZW50cz1hd2FpdCByLmpzb24oKTtjb25zb2xlLmxvZygnQ2FsZW5kYXIgZXZlbnRzOicsZXZlbnRzLmxlbmd0aCk7aWYoIWV2ZW50c3x8IWV2ZW50cy5sZW5ndGgpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0icGFkZGluZzoyMHB4O2NvbG9yOnZhcigtLW11dGVkKSI+U2VtIGV2ZW50b3MgZGlzcG9uw612ZWlzIGVzdGEgc2VtYW5hPC9kaXY+JztyZXR1cm47fWNvbnN0IGJ5RGF0ZT17fTtldmVudHMuZm9yRWFjaChlPT57Y29uc3QgZHQ9KGUuZGF0ZXx8JycpLnNsaWNlKDAsMTApO2lmKCFieURhdGVbZHRdKWJ5RGF0ZVtkdF09W107YnlEYXRlW2R0XS5wdXNoKGUpO30pO2xldCBodG1sPScnO09iamVjdC5rZXlzKGJ5RGF0ZSkuc29ydCgpLmZvckVhY2goZHQ9Pntjb25zdCBkPW5ldyBEYXRlKGR0KydUMTI6MDA6MDAnKTtjb25zdCBsYWJlbD1kLnRvTG9jYWxlRGF0ZVN0cmluZygncHQtQlInLHt3ZWVrZGF5OidzaG9ydCcsZGF5OicyLWRpZ2l0Jyxtb250aDonc2hvcnQnfSk7aHRtbCs9JzxkaXYgY2xhc3M9InNlYyI+PHNwYW4+8J+ThTwvc3Bhbj4gJytsYWJlbCsnPC9kaXY+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjhweCI+JztieURhdGVbZHRdLmZvckVhY2goZT0+e2NvbnN0IGZsYWc9ZS5mbGFnfHxDQUxfRkxBR1NbZS5jb3VudHJ5XXx8J/CfjJAnO2NvbnN0IGltcD1lLmltcG9ydGFuY2V8fDE7Y29uc3QgaW1wQ29sb3I9aW1wPj0zPyd2YXIoLS1yZWQpJzppbXA+PTI/J3ZhcigtLXdhcm4pJzondmFyKC0tbXV0ZWQpJztjb25zdCBhY3R1YWxDb2xvcj1lLnNpZ25hbD09PSdiZWF0Jz8ndmFyKC0tZ3JlZW4pJzplLnNpZ25hbD09PSdtaXNzJz8ndmFyKC0tcmVkKSc6J3ZhcigtLWFjY2VudCknOwogICAgICAgIGNvbnN0IGFjdHVhbD1lLmFjdHVhbD8nPGIgc3R5bGU9ImNvbG9yOicrYWN0dWFsQ29sb3IrJyI+JytlLmFjdHVhbCsnPC9iPic6JzxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCkiPuKAlDwvc3Bhbj4nO2h0bWwrPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHg7cGFkZGluZzo2cHggMTBweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2ZvbnQtc2l6ZTouNnJlbSI+PHNwYW4+JytmbGFnKyc8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTttaW4td2lkdGg6NDBweCI+JysoZS50aW1lfHwnJykrJzwvc3Bhbj48c3BhbiBzdHlsZT0iZmxleDoxIj4nKyhlLmV2ZW50fHwnJykrJzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6JytpbXBDb2xvcisnO21pbi13aWR0aDoxNnB4Ij4nKyfil48nLnJlcGVhdChpbXApKyc8L3NwYW4+PHNwYW4gc3R5bGU9Im1pbi13aWR0aDo1MHB4O3RleHQtYWxpZ246cmlnaHQiPicrYWN0dWFsKyc8L3NwYW4+PHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTttaW4td2lkdGg6NDVweDt0ZXh0LWFsaWduOnJpZ2h0Ij4nKyhlLmZvcmVjYXN0fHwnJykrJzwvc3Bhbj48L2Rpdj4nO30pO2h0bWwrPSc8L2Rpdj4nO30pO2VsLmlubmVySFRNTD1odG1sO31jYXRjaChlKXtpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLWRhbmdlcik7cGFkZGluZzoyMHB4Ij5FcnJvIGFvIGNhcnJlZ2FyPC9kaXY+Jzt9fQphc3luYyBmdW5jdGlvbiByZWxvYWRJbmQodGlja2VyKXsKICBjb25zdCBhcmVhSWQ9dGlja2VyKyctaW5kLWFyZWEnOwogIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGFyZWFJZCk7CiAgaWYoZWwpZWwuaW5uZXJIVE1MPSc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHg7YW5pbWF0aW9uOnB1bHNlIDFzIGluZmluaXRlIj5DYXJyZWdhbmRvICcrdGlja2VyLnRvVXBwZXJDYXNlKCkrJy4uLjwvZGl2Pic7CiAgY29uc3QgdGlja2VyTWFwPXsncGV0cjQnOidQRVRSNC5TQScsJ3ZhbGUzJzonVkFMRTMuU0EnLCdiYmFzMyc6J0JCQVMzLlNBJywnYXhpYTMnOidBWElBMy5TQScsJ3JveG8zNCc6J1JPWE8zNC5TQSd9OwogIGNvbnN0IGQ9YXdhaXQgZmV0Y2hJbmRpY2F0b3JzKHRpY2tlck1hcFt0aWNrZXJdfHx0aWNrZXIudG9VcHBlckNhc2UoKSsnLlNBJyk7CiAgcmVuZGVySW5kaWNhdG9ycyhhcmVhSWQsZCx0cnVlKTsKfQoKYXN5bmMgZnVuY3Rpb24gZmV0Y2hBbGwoKXt0cnl7Y29uc3RbLHR2LGZ1dHVyZXNdPWF3YWl0IFByb21pc2UuYWxsKFtmZXRjaEhMKCksZmV0Y2hUVigpLGZldGNoRnV0dXJlcygpXSk7Y29uc3Qgbm93PW5ldyBEYXRlKCkudG9Mb2NhbGVUaW1lU3RyaW5nKCdwdC1CUicpO3NldEVsKCdsYXN0LXVwZGF0ZScsJ0F0dWFsaXphZG8gJytub3cpO3NldEVsKCdmb290ZXItdGltZScsbm93KTtkb01hY3JvKHR2LGZ1dHVyZXMpO2RvUG9zaXRpb25zKHR2KTtzZXRUaW1lb3V0KGZldGNoRnVuZGluZywzMDAwKTsKICAvLyBCVEMgUlNJIGUgRmVhciZHcmVlZCBuYXMgY290YcOnw7VlcwogIHNldFRpbWVvdXQoYXN5bmMoKT0+ewogICAgdHJ5ewogICAgICBjb25zdFtiLGN5Y109YXdhaXQgUHJvbWlzZS5hbGwoW2ZldGNoQlRDSW5kaWNhdG9ycygpLGZldGNoQlRDQ3ljbGUoKV0pOwogICAgICBpZihiKXJlbmRlckJUQ0luZGljYXRvcnMoYik7CiAgICAgIGlmKGN5YylyZW5kZXJCVENDeWNsZShjeWMpOwogICAgICBmZXRjaEZlYXJHcmVlZCgpOwogICAgfWNhdGNoKGUpe30KICB9LDQwMDApO3NldFRpbWVvdXQoKCk9PntydW5NQ0ZvckF0aXZvKCdQRVRSNC5TQScsMzAuODUsMTk1LCdtYy1wdC1sb2FkaW5nJywnbWMtcHQtcmVzdWx0JywnbWMtcHQtc3RyaWtlJywnbWMtcHQtdm9sJywnbWMtcHQtaW5mbycpO30sNjAwMCk7c2V0VGltZW91dCgoKT0+e3J1bk1DRm9yQXRpdm8oJ1ZBTEUzLlNBJyw1Ny40MCwyNTgsJ21jLXZsLWxvYWRpbmcnLCdtYy12bC1yZXN1bHQnLCdtYy12bC1zdHJpa2UnLCdtYy12bC12b2wnLCdtYy12bC1pbmZvJyk7fSwxMjAwMCk7c2V0VGltZW91dCgoKT0+e3J1bk1DQmFycmllcignQVhJQTMuU0EnLDU0LjMxLDQzLjUxLDY4Ljc2LDEwMSw1NC4zMSwnYXhpYTMnKTt9LDE4MDAwKTtzZXRUaW1lb3V0KCgpPT57cnVuTUNCYXJyaWVyKCdBWElBMy5TQScsNTAuNjUsNDAuNTIsNjIuODEsMTE5LDUwLjY1LCdheGlhM2InKTt9LDI0MDAwKTtzZXRUaW1lb3V0KCgpPT57cnVuTUNQcmVmaXhhZG8oJ1JPWE8zNC5TQScsMTIuODgsMTAuNTAsNDEsMTIuODgpO30sMzAwMDApO3dpbmRvdy5faW5kTG9hZGVkPWZhbHNlO31jYXRjaChlKXtjb25zb2xlLmVycm9yKCdmZXRjaEFsbDonLGUpO319CmZldGNoQWxsKCk7CnNldEludGVydmFsKGZldGNoQWxsLDEyMDAwMCk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4=").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
