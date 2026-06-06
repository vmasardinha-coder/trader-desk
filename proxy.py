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

    return jsonify({'dji':dji,'esf':esf,'nqf':nqf,'win':win,'vix':vix,'dxy':dxy})

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
    try:
        cdi=get_cdi()
        setor=SETORES.get(ticker,SETORES['DEFAULT'])
        ticker_base=ticker.replace('.SA','').replace('.sa','').upper()
        hc=FUND.get(ticker_base,{})

        # Historico de precos
        r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=400d',
            headers={'User-Agent':'Mozilla/5.0'},timeout=10)
        if not r.ok: return jsonify({'error':f'Yahoo {r.status_code}'}),500
        d=r.json()
        result=d.get('chart',{}).get('result',[{}])[0]
        meta=result.get('meta',{})
        q=result.get('indicators',{}).get('quote',[{}])[0]
        cl=[c for c in q.get('close',[]) if c is not None]
        vl=[v if v else 0 for v in q.get('volume',[])][-len(cl):]
        if not cl: return jsonify({'error':'Sem dados'}),500
        price=float(meta.get('regularMarketPrice',cl[-1]))

        # Calculos tecnicos
        rsi_v=rsi(cl)
        mm20=mm(cl,20); mm50=mm(cl,50); mm200=mm(cl,200)
        ml,ms,mh=macd(cl)
        bu,bm,bl=bollinger(cl)
        _,ot=obv(cl,vl)
        vm=round(sum(vl[-20:])/min(20,len(vl)),0) if vl else None

        # Fundamentais — tenta brapi primeiro, depois hardcoded
        pl=pvp=dy=roe_v=ev=de=lpa_v=vpa_v=mg=None
        try:
            rb=requests.get(f'https://brapi.dev/api/quote/{ticker_base}?fundamental=true',
                headers={'User-Agent':'Mozilla/5.0'},timeout=8)
            if rb.ok:
                res2=rb.json().get('results',[{}])[0]
                pl=res2.get('priceEarnings') or res2.get('trailingPE')
                fd=res2.get('financialData') or {}
                roe_val=fd.get('returnOnEquity')
                if roe_val: roe_v=round(float(roe_val)*100,2)
                ml2=fd.get('profitMargins')
                if ml2: mg=round(float(ml2)*100,2)
        except: pass

        # Completa com hardcoded
        if pl is None:   pl=hc.get('pvp')  # fallback
        pl=hc.get('pl', pl)  # prefer hardcoded PL
        if pvp is None:  pvp=hc.get('pvp')
        if dy is None:   dy=hc.get('dy')
        if roe_v is None:roe_v=hc.get('roe')
        if ev is None:   ev=hc.get('ev_ebitda')
        if de is None:   de=hc.get('debt_ebitda')
        if lpa_v is None:lpa_v=hc.get('lpa')
        if vpa_v is None:vpa_v=hc.get('vpa')
        if mg is None:   mg=hc.get('margem')

        # Graham
        vj=graham(lpa_v,vpa_v)
        up=round((vj-price)/price*100,1) if vj else None

        f=lambda v: round(v,2) if v is not None else None

        ind={
            'ticker':ticker,'setor':setor,'price':round(price,2),
            'rsi':rsi_v,'mm20':mm20,'mm50':mm50,'mm200':mm200,
            'macd':f(ml),'macd_signal':f(ms),'macd_histogram':f(mh),
            'bb_upper':bu,'bb_mid':bm,'bb_lower':bl,
            'bollinger_upper':bu,'bollinger_mid':bm,'bollinger_lower':bl,
            'obv_trend':ot,'volume_medio_20d':vm,
            'pl':f(pl),'pl_setor':setor.get('pl_medio'),
            'pvp':f(pvp),'price_to_book':f(pvp),'pvp_setor':setor.get('pvp_medio'),
            'ev_ebitda':f(ev),
            'dividend_yield':dy,'dy':dy,
            'roe':roe_v,'roe_min_setor':setor.get('roe_min'),
            'debt_to_ebitda':f(de),'debt_ebitda':f(de),
            'profit_margin':round(mg/100,4) if mg else None,'margem_liquida':mg,
            'lpa':f(lpa_v),'vpa':f(vpa_v),
            'valor_justo_graham':vj,'upside_graham':up,
            'cdi':cdi,'data_points':len(cl)
        }
        ind['sinal']=sinal(ind,cdi)
        return jsonify(ind)
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── INDICADORES BTC ───────────────────────────────────

# BTC CYCLE INDICATORS
# Cache para dados on-chain calculados
_BTC_ONCHAIN_CACHE = {'data': None, 'ts': 0}

def get_btc_onchain():
    import time as _t
    global _BTC_ONCHAIN_CACHE
    # Cache de 4 horas
    if _BTC_ONCHAIN_CACHE['data'] and _t.time() - _BTC_ONCHAIN_CACHE['ts'] < 14400:
        return _BTC_ONCHAIN_CACHE['data']
    try:
        # Market Cap via CoinGecko
        rg = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_market_cap=true',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
        market_cap = None
        price_usd = None
        if rg.ok:
            d = rg.json().get('bitcoin',{})
            market_cap = d.get('usd_market_cap')
            price_usd = d.get('usd')

        # Realized Cap via Blockchain.com (total output volume proxy)
        # Usa realized price = 61k como base e ajusta pelo preco atual
        # MVRV = market_cap / realized_cap
        realized_price = 61120  # Realized price atual (atualizar mensalmente)
        supply = 19700000  # BTC em circulacao
        realized_cap = realized_price * supply

        # Se CoinGecko falhou, calcula market_cap pelo preco atual da HL
        if not market_cap and price_usd:
            market_cap = price_usd * supply
        elif not market_cap:
            # Busca preco BTC da HL como fallback
            try:
                rh = requests.post('https://api.hyperliquid.xyz/info',
                    json={'type':'allMids'}, headers={'Content-Type':'application/json'}, timeout=5)
                if rh.ok:
                    btc_price = float(rh.json().get('BTC', 77000))
                    market_cap = btc_price * supply
            except:
                market_cap = 77000 * supply  # fallback absoluto

        mvrv = round(market_cap / realized_cap, 2) if market_cap else 1.28
        nupl = round((market_cap - realized_cap) / market_cap, 2) if market_cap else 0.22

        # MVRV Z-Score = (MVRV - media_historica) / std_historico
        # Media ~1.5, std ~1.2 baseado em dados historicos
        mvrv_zscore = round((mvrv - 1.5) / 1.2, 2)

        # Puell Multiple via blockchain hashrate proxy
        # Aproxima usando preco BTC vs media 365d
        puell = 0.85  # Atualizar mensalmente - requer dados de mineracao

        result = {
            'mvrv_zscore': mvrv_zscore,
            'nupl': nupl if nupl else 0.30,
            'puell_multiple': puell,
            'sopr': 0.98,
            'realized_price': realized_price,
            'market_cap': market_cap,
            'realized_cap': realized_cap,
            'mvrv_raw': mvrv,
            'updated': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        _BTC_ONCHAIN_CACHE = {'data': result, 'ts': _t.time()}
        return result
    except Exception as e:
        return {
            'mvrv_zscore': -0.18, 'nupl': 0.22, 'puell_multiple': 0.85,
            'sopr': 0.98, 'realized_price': 61120, 'updated': 'cache (fallback)'
        }

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
@app.route('/us/quotes', methods=['GET'])
def get_us_quotes():
    tickers = request.args.get('tickers','').split(',')
    tickers = [t.strip() for t in tickers if t.strip()][:25]
    result = {}
    for t in tickers:
        q = yquote(t)
        if q: result[t] = q
    return jsonify(result)

# ── ECONOMIC CALENDAR ─────────────────────────────────
@app.route('/calendar', methods=['GET'])
def get_calendar():
    import datetime as dt_mod
    all_events = []
    currencies_ok = {'USD','BRL','EUR','GBP','CNY','JPY','DEM'}
    flag_map = {'USD':'🇺🇸','BRL':'🇧🇷','EUR':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳','JPY':'🇯🇵','DEM':'🇩🇪'}
    imp_map = {'Low':1,'Medium':2,'High':3,'Holiday':0}

    # Forex Factory — fonte principal gratuita
    for url in [
        'https://nfs.faireconomy.media/ff_calendar_thisweek.json',
        'https://nfs.faireconomy.media/ff_calendar_nextweek.json',
    ]:
        try:
            r = requests.get(url, headers={'User-Agent':'Mozilla/5.0 Trader-Desk/1.0'}, timeout=10)
            if not r.ok: continue
            for e in r.json():
                cur = e.get('currency','')
                if cur not in currencies_ok: continue
                imp = imp_map.get(e.get('impact',''), 0)
                if imp < 2: continue
                all_events.append({
                    'date':       e.get('date','')[:10],
                    'time':       e.get('time',''),
                    'country':    cur,
                    'flag':       flag_map.get(cur,'🌐'),
                    'event':      e.get('title',''),
                    'importance': imp,
                    'actual':     e.get('actual','') or None,
                    'forecast':   e.get('forecast','') or None,
                    'previous':   e.get('previous','') or None,
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

# HTML EMBUTIDO — 2026-06-06 18:05
PANEL_HTML = """<!DOCTYPE html>
<!-- Trader Desk v9.6 - 2026-06-06 18:05 -->
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trader Desk</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#06080a;--bg2:#0b0f12;--bg3:#101518;--border:#1a2530;--accent:#00ffa3;--blue:#38bdf8;--warn:#f59e0b;--danger:#f43f5e;--muted:#3d5464;--text:#b8cdd8;--green:#00ffa3;--red:#f43f5e;--gold:#fbbf24;--silver:#94a3b8}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'IBM Plex Mono',monospace;min-height:100vh}
body::after{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 20% 0%,rgba(0,255,163,.04) 0%,transparent 60%),radial-gradient(ellipse at 80% 100%,rgba(56,189,248,.04) 0%,transparent 60%);pointer-events:none;z-index:0}

/* TICKER TAPE */
.ticker-wrap{background:var(--bg2);border-bottom:1px solid var(--border);overflow:hidden;height:44px;position:relative;z-index:10}
.ticker-track{display:flex;align-items:center;height:100%;white-space:nowrap;animation:scroll-left 80s linear infinite}
.ticker-track:hover{animation-play-state:paused}
.ticker-item{display:inline-flex;align-items:center;gap:8px;padding:0 22px;font-size:.78rem;border-right:1px solid var(--border);height:100%}
.ticker-name{color:var(--muted);letter-spacing:.06em}
.ticker-price{font-weight:700;color:var(--text)}
.ticker-chg.up{color:var(--green);font-size:.68rem}.ticker-chg.down{color:var(--red);font-size:.68rem}.ticker-chg.flat{color:var(--muted);font-size:.68rem}
@keyframes scroll-left{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}

/* LAYOUT */
.wrap{position:relative;z-index:1;max-width:1300px;margin:0 auto;padding:16px 14px}

header{display:flex;align-items:center;justify-content:space-between;padding-bottom:12px;border-bottom:1px solid var(--border);margin-bottom:14px}
.brand{font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;letter-spacing:.12em;color:var(--accent)}
.brand em{color:var(--muted);font-style:normal}
.hdr-right{text-align:right;font-size:.62rem;line-height:1.8}
.hdr-right .t{font-size:.9rem;color:var(--blue);font-weight:600}

/* TABS */
.tabs{display:flex;gap:0;margin-bottom:18px;border-bottom:1px solid var(--border)}
.tab{font-family:'Syne',sans-serif;font-size:.75rem;font-weight:700;letter-spacing:.1em;padding:10px 28px;cursor:pointer;border:1px solid transparent;border-bottom:none;color:var(--muted);text-transform:uppercase;transition:all .2s;margin-bottom:-1px}
.tab:hover{color:var(--text)}
.tab.active{color:var(--accent);border-color:var(--border);border-bottom-color:var(--bg);background:var(--bg)}
.tab-content{display:none}
.tab-content.active{display:block}

/* STATUS BAR */
.sbar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;align-items:center}
.pill{font-size:.58rem;padding:3px 9px;border:1px solid var(--border);color:var(--muted);letter-spacing:.08em;text-transform:uppercase;transition:all .3s}
.pill.live{border-color:var(--accent);color:var(--accent);animation:blink 2s infinite}
.pill.closed{border-color:var(--muted);color:var(--muted)}
.pill.ok{border-color:var(--blue);color:var(--blue)}
.pill.warn{border-color:var(--warn);color:var(--warn)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
.refresh-btn{margin-left:auto;background:transparent;border:1px solid var(--accent);color:var(--accent);font-family:'IBM Plex Mono',monospace;font-size:.62rem;padding:6px 14px;cursor:pointer;letter-spacing:.1em;text-transform:uppercase;transition:all .2s}
.refresh-btn:hover{background:var(--accent);color:var(--bg)}
.refresh-btn:disabled{opacity:.4;cursor:default}

/* SECTION TITLE */
.sec{font-family:'Syne',sans-serif;font-size:.6rem;letter-spacing:.2em;color:var(--muted);text-transform:uppercase;margin:16px 0 8px;display:flex;align-items:center;gap:10px}
.sec::after{content:'';flex:1;height:1px;background:var(--border)}
.sec span{color:var(--blue)}
.sec .src{font-size:.5rem;color:var(--muted);letter-spacing:.05em;text-transform:none}

/* CARDS */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
@media(max-width:700px){.grid{grid-template-columns:1fr 1fr}.grid2,.grid3{grid-template-columns:1fr}}

.card{background:var(--bg2);border:1px solid var(--border);padding:12px;position:relative;overflow:hidden;animation:fadeUp .3s ease both}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px}
.card.blue::before{background:linear-gradient(90deg,var(--blue),transparent)}
.card.green::before{background:linear-gradient(90deg,var(--accent),transparent)}
.card.warn::before{background:linear-gradient(90deg,var(--warn),transparent)}
.card.danger::before{background:linear-gradient(90deg,var(--danger),transparent)}
.card.gold::before{background:linear-gradient(90deg,var(--gold),transparent)}
.card.silver::before{background:linear-gradient(90deg,var(--silver),transparent)}
.card.orange::before{background:linear-gradient(90deg,#fb923c,transparent)}
.card.btc::before{background:linear-gradient(90deg,var(--warn),transparent);height:2px}
@keyframes fadeUp{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}

.c-label{font-size:.58rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:3px}
.c-name{font-family:'Syne',sans-serif;font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:4px}
.c-price{font-size:1.15rem;font-weight:600;color:var(--accent);margin-bottom:2px;min-height:1.3em}
.c-price.loading{color:var(--muted);font-size:.7rem;animation:pulse 1.5s infinite}
.c-price.gold-c{color:var(--gold)}.c-price.silver-c{color:var(--silver)}.c-price.copper-c{color:#fb923c}.c-price.btc-c{color:var(--warn)}
.c-change{font-size:.68rem;min-height:.9em}
.c-change.up{color:var(--green)}.c-change.down{color:var(--red)}.c-change.flat{color:var(--muted)}
.c-src{font-size:.52rem;color:var(--muted);margin-top:3px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* POSITION CARDS */
.pos-card{background:var(--bg2);border:1px solid var(--border);padding:16px;position:relative;overflow:hidden}
.pos-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.pos-card.acao::before{background:linear-gradient(90deg,var(--danger),transparent)}
.pos-card.btc-pos::before{background:linear-gradient(90deg,var(--warn),var(--danger),transparent)}
.pos-label{font-size:.55rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px}
.pos-ticker{font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;color:var(--text)}
.pos-price{font-size:1.5rem;font-weight:700;color:var(--accent);margin:4px 0 2px}
.pos-price.btc-c{color:var(--warn)}
.pos-price.loading{color:var(--muted);font-size:.8rem;animation:pulse 1.5s infinite}
.pos-chg{font-size:.7rem;margin-bottom:10px}
.pos-chg.up{color:var(--green)}.pos-chg.down{color:var(--red)}

.sb{background:var(--bg3);border:1px solid var(--border);padding:10px;margin-top:8px;font-size:.68rem}
.sb-row{display:flex;justify-content:space-between;margin-bottom:5px;align-items:center}
.sb-row:last-child{margin-bottom:0}
.sb-lbl{color:var(--muted)}.sb-val{font-weight:600}
.sb-val.itm{color:var(--danger)}.sb-val.ok{color:var(--green)}.sb-val.warn{color:var(--warn)}
.prog-wrap{margin-top:8px;background:var(--bg);height:3px}
.prog-bar{height:100%;transition:width 1s ease;max-width:100%}
.prog-bar.danger{background:var(--danger)}.prog-bar.warn{background:var(--warn)}.prog-bar.ok{background:var(--green)}

/* RSI */
.rsi-wrap{margin-top:10px}
.rsi-hdr{display:flex;justify-content:space-between;font-size:.7rem;color:var(--muted);margin-bottom:5px}
.rsi-track{height:6px;background:linear-gradient(90deg,var(--red) 0%,var(--warn) 35%,var(--green) 55%,var(--red) 100%);position:relative}
.rsi-needle{position:absolute;top:-5px;width:2px;height:16px;background:#fff;transform:translateX(-50%);transition:left 1s ease;box-shadow:0 0 4px rgba(255,255,255,.5)}
.rsi-zones{display:flex;justify-content:space-between;font-size:.62rem;color:var(--muted);margin-top:4px}

/* SIGNAL */
.signal{margin-top:10px;padding:10px;background:var(--bg3);border:1px solid var(--border);font-size:.65rem;line-height:1.6}
.sig-title{font-size:.55rem;color:var(--blue);letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px}

/* FUNDING */
.fr-box{margin-top:10px;padding:10px;background:var(--bg3);border:1px solid var(--warn)}
.fr-title{font-size:.55rem;color:var(--warn);letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}
.fr-vals{display:flex;gap:20px;margin-bottom:8px;align-items:baseline}
.fr-lbl{font-size:.52rem;color:var(--muted);text-transform:uppercase}
.fr-val{font-size:1.1rem;font-weight:700}
.fr-next{font-size:.78rem;color:var(--text)}
.fr-sig{font-size:.65rem;line-height:1.6}
.fr-ref{font-size:.52rem;color:var(--muted);margin-top:4px}

/* IND GRID */
.ind-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:8px}
.ind-box{background:var(--bg3);border:1px solid var(--border);padding:9px}
.ind-lbl{font-size:.62rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:3px}
.ind-val{font-size:.95rem;font-weight:600;color:var(--text)}
.ind-val.up{color:var(--green)}.ind-val.down{color:var(--red)}.ind-val.warn{color:var(--warn)}

/* DEBUG */
#debug-bar{background:var(--bg3);border-top:1px solid var(--border);padding:6px 14px;font-size:.52rem;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap}
#debug-bar .ok{color:var(--accent)}
#debug-bar .err{color:var(--danger)}

footer{margin-top:16px;padding-top:12px;border-top:1px solid var(--border);display:flex;justify-content:space-between;font-size:.52rem;color:var(--muted);flex-wrap:wrap;gap:6px}
.sector-header{background:var(--bg2);border:1px solid var(--border);padding:8px 14px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;font-size:.65rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-top:6px;transition:border-color .2s}
.sector-header:hover{border-color:var(--accent);color:var(--text)}
.sector-body{display:none;padding-top:4px}
/* TOOLTIPS */
.ind-box{position:relative;cursor:help}
.ind-box .tooltip{display:none;font-size:.6rem;position:absolute;bottom:110%;left:50%;transform:translateX(-50%);background:#1a2530;border:1px solid var(--border);color:var(--text);font-size:.55rem;padding:6px 10px;white-space:nowrap;z-index:100;line-height:1.5;min-width:180px;max-width:260px;white-space:normal}
.ind-box:hover .tooltip{display:block}
</style>
</head>
<body>

<!-- TICKER TAPE -->
<div class="ticker-wrap"><div class="ticker-track" id="tape"></div></div>

<div class="wrap">
<header>
  <div class="brand">TRADER<em>//</em>DESK</div>
  <div class="hdr-right">
    <div class="t" id="clk">--:--:--</div>
    <div id="clk-date">—</div>
    <div id="mkt-st" style="color:var(--muted);font-size:.58rem">verificando...</div>
  </div>
</header>

<!-- STATUS BAR -->
<div class="sbar">
  <div class="pill closed" id="pill-b3">B3 ○</div>
  <div class="pill live"   id="pill-hl">HYPERLIQUID ●</div>
  <div class="pill closed" id="pill-us">EUA ○</div>
  <div class="pill warn"   id="pill-upd">Aguardando...</div>
  <button class="refresh-btn" id="btn-ref" onclick="fetchAll()">↻ Atualizar</button>
</div>

<!-- TABS -->
<div class="tabs">
  <div class="tab active" onclick="switchTab('cotacoes')">📊 Cotações</div>
  <div class="tab" onclick="switchTab('indicadores')">📈 Indicadores & Sinais</div>
  <div class="tab" onclick="switchTab('posicoes')">💼 Minhas Posições</div>
  <div class="tab" onclick="switchTab('calendario')">📅 Calendário</div>
</div>

<!-- ═══════════════════════════════════════════════════ -->
<!-- TAB 1: COTAÇÕES -->
<!-- ═══════════════════════════════════════════════════ -->
<div id="tab-cotacoes" class="tab-content active">

  <div class="sec"><span>01</span> Índices EUA <span class="src">· Hyperliquid xyz: dex</span></div>
  <div class="grid">
    <div class="card blue"><div class="c-label">Índice · EUA</div><div class="c-name">S&amp;P 500</div><div class="c-price loading" id="sp-p">—</div><div class="c-change" id="sp-c">—</div><div class="c-src" id="sp-s">HL</div></div>
    <div class="card blue"><div class="c-label">Futuro · EUA</div><div class="c-name">S&amp;P ES1*</div><div class="c-price loading" id="esf-p" style="color:var(--accent)">—</div><div class="c-change" id="esf-c">—</div><div class="c-src" id="esf-s">proxy</div></div>
    <div class="card blue"><div class="c-label">Índice · EUA</div><div class="c-name">Nasdaq 100</div><div class="c-price loading" id="ndx-p">—</div><div class="c-change" id="ndx-c">—</div><div class="c-src" id="ndx-s">HL</div></div>
    <div class="card blue"><div class="c-label">Futuro · EUA</div><div class="c-name">NQ Futuro</div><div class="c-price loading" id="nqf-p" style="color:var(--accent)">—</div><div class="c-change" id="nqf-c">—</div><div class="c-src" id="nqf-s">proxy</div></div>
    <div class="card blue"><div class="c-label">Índice · EUA</div><div class="c-name">Dow Jones</div><div class="c-price loading" id="dji-p">—</div><div class="c-change" id="dji-c">—</div><div class="c-src" id="dji-s">proxy</div></div>
    <div class="card blue"><div class="c-label">Volatilidade</div><div class="c-name">VIX</div><div class="c-price loading" id="vix-p">—</div><div class="c-change" id="vix-c">—</div><div class="c-src">HL</div></div>
    <div class="card warn"><div class="c-label">Índice Dólar</div><div class="c-name">DXY</div><div class="c-price loading" id="dxy-p">—</div><div class="c-change" id="dxy-c">—</div><div class="c-src">HL</div></div>
    <div class="card warn"><div class="c-label">Câmbio · Spot</div><div class="c-name">USD / BRL</div><div class="c-price loading" id="usd-p">—</div><div class="c-change" id="usd-c">—</div><div class="c-src" id="usd-s">TV</div></div>
  </div>

  <div class="sec"><span>02</span> B3 — Brasil <span class="src">· TradingView via proxy</span></div>
  <div class="grid">
    <div class="card green"><div class="c-label">BR · Índice</div><div class="c-name">Ibovespa</div><div class="c-price loading" id="ibov-p">—</div><div class="c-change" id="ibov-c">—</div><div class="c-src" id="ibov-s">TV</div></div>
    <div class="card green"><div class="c-label">BR · Futuro</div><div class="c-name">WIN Futuro</div><div class="c-price loading" id="win-p">—</div><div class="c-change" id="win-c">—</div><div class="c-src">ref</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">PETR4</div><div class="c-price loading" id="petr4q-p">—</div><div class="c-change" id="petr4q-c">—</div><div class="c-src">TV</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">ITUB4</div><div class="c-price loading" id="itub4q-p">—</div><div class="c-change" id="itub4q-c">—</div><div class="c-src">TV</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">VALE3</div><div class="c-price loading" id="vale3q-p">—</div><div class="c-change" id="vale3q-c">—</div><div class="c-src">TV</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">BBDC4</div><div class="c-price loading" id="bbdc4q-p">—</div><div class="c-change" id="bbdc4q-c">—</div><div class="c-src">TV</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">ABEV3</div><div class="c-price loading" id="abev3q-p">—</div><div class="c-change" id="abev3q-c">—</div><div class="c-src">TV</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">BBAS3</div><div class="c-price loading" id="bbas3q-p">—</div><div class="c-change" id="bbas3q-c">—</div><div class="c-src">TV</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">WEGE3</div><div class="c-price loading" id="wege3q-p">—</div><div class="c-change" id="wege3q-c">—</div><div class="c-src">TV</div></div>
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">RDOR3</div><div class="c-price loading" id="rdor3q-p">—</div><div class="c-change" id="rdor3q-c">—</div><div class="c-src">TV</div></div>
    <div class="card warn"><div class="c-label">BDR · Nubank</div><div class="c-name">ROXO34</div><div class="c-price loading" id="roxo34q-p">—</div><div class="c-change" id="roxo34q-c">—</div><div class="c-src">Yahoo</div></div>
  </div>


  <div class="sec" style="margin-top:16px"><span>📂</span> B3 por Segmento <span class="src">· clique para expandir</span></div>

  <div class="sector-header" onclick="toggleSeg('financeiro')"><span>🏦 Financeiro</span><span id="sarr-financeiro">▼</span></div>
  <div class="sector-body" id="sbody-financeiro" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">ITUB4</div><div class="c-price loading" id="sg-itub4-p">—</div><div class="c-change" id="sg-itub4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BBDC4</div><div class="c-price loading" id="sg-bbdc4-p">—</div><div class="c-change" id="sg-bbdc4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BBAS3</div><div class="c-price loading" id="sg-bbas3-p">—</div><div class="c-change" id="sg-bbas3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">SANB11</div><div class="c-price loading" id="sg-sanb11-p">—</div><div class="c-change" id="sg-sanb11-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">B3SA3</div><div class="c-price loading" id="sg-b3sa3-p">—</div><div class="c-change" id="sg-b3sa3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BPAC11</div><div class="c-price loading" id="sg-bpac11-p">—</div><div class="c-change" id="sg-bpac11-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ITSA4</div><div class="c-price loading" id="sg-itsa4-p">—</div><div class="c-change" id="sg-itsa4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BRSR6</div><div class="c-price loading" id="sg-brsr6-p">—</div><div class="c-change" id="sg-brsr6-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ABCB4</div><div class="c-price loading" id="sg-abcb4-p">—</div><div class="c-change" id="sg-abcb4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BMGB4</div><div class="c-price loading" id="sg-bmgb4-p">—</div><div class="c-change" id="sg-bmgb4-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('petroleo')"><span>🛢 Petróleo & Gás</span><span id="sarr-petroleo">▼</span></div>
  <div class="sector-body" id="sbody-petroleo" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">PETR4</div><div class="c-price loading" id="sg-petr4-p">—</div><div class="c-change" id="sg-petr4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">PETR3</div><div class="c-price loading" id="sg-petr3-p">—</div><div class="c-change" id="sg-petr3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">PRIO3</div><div class="c-price loading" id="sg-prio3-p">—</div><div class="c-change" id="sg-prio3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BRAV3</div><div class="c-price loading" id="sg-brav3-p">—</div><div class="c-change" id="sg-brav3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">VBBR3</div><div class="c-price loading" id="sg-vbbr3-p">—</div><div class="c-change" id="sg-vbbr3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CSAN3</div><div class="c-price loading" id="sg-csan3-p">—</div><div class="c-change" id="sg-csan3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">RECV3</div><div class="c-price loading" id="sg-recv3-p">—</div><div class="c-change" id="sg-recv3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">UGPA3</div><div class="c-price loading" id="sg-ugpa3-p">—</div><div class="c-change" id="sg-ugpa3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CGAS3</div><div class="c-price loading" id="sg-cgas3-p">—</div><div class="c-change" id="sg-cgas3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">SEQL3</div><div class="c-price loading" id="sg-seql3-p">—</div><div class="c-change" id="sg-seql3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('mineracao')"><span>⛏ Mineração</span><span id="sarr-mineracao">▼</span></div>
  <div class="sector-body" id="sbody-mineracao" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">VALE3</div><div class="c-price loading" id="sg-vale3-p">—</div><div class="c-change" id="sg-vale3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">GGBR4</div><div class="c-price loading" id="sg-ggbr4-p">—</div><div class="c-change" id="sg-ggbr4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CSNA3</div><div class="c-price loading" id="sg-csna3-p">—</div><div class="c-change" id="sg-csna3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">USIM5</div><div class="c-price loading" id="sg-usim5-p">—</div><div class="c-change" id="sg-usim5-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BRAP4</div><div class="c-price loading" id="sg-brap4-p">—</div><div class="c-change" id="sg-brap4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">FESA4</div><div class="c-price loading" id="sg-fesa4-p">—</div><div class="c-change" id="sg-fesa4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CMIN3</div><div class="c-price loading" id="sg-cmin3-p">—</div><div class="c-change" id="sg-cmin3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CBAV3</div><div class="c-price loading" id="sg-cbav3-p">—</div><div class="c-change" id="sg-cbav3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">GOAU4</div><div class="c-price loading" id="sg-goau4-p">—</div><div class="c-change" id="sg-goau4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">PGMN3</div><div class="c-price loading" id="sg-pgmn3-p">—</div><div class="c-change" id="sg-pgmn3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('materiais')"><span>🌲 Papel & Celulose</span><span id="sarr-materiais">▼</span></div>
  <div class="sector-body" id="sbody-materiais" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">SUZB3</div><div class="c-price loading" id="sg-suzb3-p">—</div><div class="c-change" id="sg-suzb3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">KLBN11</div><div class="c-price loading" id="sg-klbn11-p">—</div><div class="c-change" id="sg-klbn11-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">DXCO3</div><div class="c-price loading" id="sg-dxco3-p">—</div><div class="c-change" id="sg-dxco3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">UNIP6</div><div class="c-price loading" id="sg-unip6-p">—</div><div class="c-change" id="sg-unip6-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">RANI3</div><div class="c-price loading" id="sg-rani3-p">—</div><div class="c-change" id="sg-rani3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ORVR3</div><div class="c-price loading" id="sg-orvr3-p">—</div><div class="c-change" id="sg-orvr3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">SMTO3</div><div class="c-price loading" id="sg-smto3-p">—</div><div class="c-change" id="sg-smto3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">DTEX3</div><div class="c-price loading" id="sg-dtex3-p">—</div><div class="c-change" id="sg-dtex3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">FRAS3</div><div class="c-price loading" id="sg-fras3-p">—</div><div class="c-change" id="sg-fras3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">KEPL3</div><div class="c-price loading" id="sg-kepl3-p">—</div><div class="c-change" id="sg-kepl3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('utilidade')"><span>⚡ Utilidade Pública</span><span id="sarr-utilidade">▼</span></div>
  <div class="sector-body" id="sbody-utilidade" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">ELET3</div><div class="c-price loading" id="sg-elet3-p">—</div><div class="c-change" id="sg-elet3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">EQTL3</div><div class="c-price loading" id="sg-eqtl3-p">—</div><div class="c-change" id="sg-eqtl3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CPFE3</div><div class="c-price loading" id="sg-cpfe3-p">—</div><div class="c-change" id="sg-cpfe3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">SBSP3</div><div class="c-price loading" id="sg-sbsp3-p">—</div><div class="c-change" id="sg-sbsp3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CMIG4</div><div class="c-price loading" id="sg-cmig4-p">—</div><div class="c-change" id="sg-cmig4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ENGI11</div><div class="c-price loading" id="sg-engi11-p">—</div><div class="c-change" id="sg-engi11-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">TAEE11</div><div class="c-price loading" id="sg-taee11-p">—</div><div class="c-change" id="sg-taee11-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">TRPL4</div><div class="c-price loading" id="sg-trpl4-p">—</div><div class="c-change" id="sg-trpl4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">AURE3</div><div class="c-price loading" id="sg-aure3-p">—</div><div class="c-change" id="sg-aure3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">EGIE3</div><div class="c-price loading" id="sg-egie3-p">—</div><div class="c-change" id="sg-egie3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('consumo_ciclico')"><span>🛍 Consumo Cíclico</span><span id="sarr-consumo_ciclico">▼</span></div>
  <div class="sector-body" id="sbody-consumo_ciclico" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">RENT3</div><div class="c-price loading" id="sg-rent3-p">—</div><div class="c-change" id="sg-rent3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">LREN3</div><div class="c-price loading" id="sg-lren3-p">—</div><div class="c-change" id="sg-lren3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">MGLU3</div><div class="c-price loading" id="sg-mglu3-p">—</div><div class="c-change" id="sg-mglu3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CYRE3</div><div class="c-price loading" id="sg-cyre3-p">—</div><div class="c-change" id="sg-cyre3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">MRVE3</div><div class="c-price loading" id="sg-mrve3-p">—</div><div class="c-change" id="sg-mrve3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">AZUL4</div><div class="c-price loading" id="sg-azul4-p">—</div><div class="c-change" id="sg-azul4-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">AZZA3</div><div class="c-price loading" id="sg-azza3-p">—</div><div class="c-change" id="sg-azza3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">VIVA3</div><div class="c-price loading" id="sg-viva3-p">—</div><div class="c-change" id="sg-viva3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">SBFG3</div><div class="c-price loading" id="sg-sbfg3-p">—</div><div class="c-change" id="sg-sbfg3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CVCB3</div><div class="c-price loading" id="sg-cvcb3-p">—</div><div class="c-change" id="sg-cvcb3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('consumo_nao')"><span>🛒 Consumo Não Cíclico</span><span id="sarr-consumo_nao">▼</span></div>
  <div class="sector-body" id="sbody-consumo_nao" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">ABEV3</div><div class="c-price loading" id="sg-abev3-p">—</div><div class="c-change" id="sg-abev3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">JBSS3</div><div class="c-price loading" id="sg-jbss3-p">—</div><div class="c-change" id="sg-jbss3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BRFS3</div><div class="c-price loading" id="sg-brfs3-p">—</div><div class="c-change" id="sg-brfs3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">NATU3</div><div class="c-price loading" id="sg-natu3-p">—</div><div class="c-change" id="sg-natu3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">MDIA3</div><div class="c-price loading" id="sg-mdia3-p">—</div><div class="c-change" id="sg-mdia3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">BEEF3</div><div class="c-price loading" id="sg-beef3-p">—</div><div class="c-change" id="sg-beef3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">SLCE3</div><div class="c-price loading" id="sg-slce3-p">—</div><div class="c-change" id="sg-slce3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">MTRE3</div><div class="c-price loading" id="sg-mtre3-p">—</div><div class="c-change" id="sg-mtre3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CAML3</div><div class="c-price loading" id="sg-caml3-p">—</div><div class="c-change" id="sg-caml3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">PCAR3</div><div class="c-price loading" id="sg-pcar3-p">—</div><div class="c-change" id="sg-pcar3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('saude')"><span>🏥 Saúde</span><span id="sarr-saude">▼</span></div>
  <div class="sector-body" id="sbody-saude" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">RDOR3</div><div class="c-price loading" id="sg-rdor3-p">—</div><div class="c-change" id="sg-rdor3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">HAPV3</div><div class="c-price loading" id="sg-hapv3-p">—</div><div class="c-change" id="sg-hapv3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">FLRY3</div><div class="c-price loading" id="sg-flry3-p">—</div><div class="c-change" id="sg-flry3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">DASA3</div><div class="c-price loading" id="sg-dasa3-p">—</div><div class="c-change" id="sg-dasa3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">QUAL3</div><div class="c-price loading" id="sg-qual3-p">—</div><div class="c-change" id="sg-qual3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ONCO3</div><div class="c-price loading" id="sg-onco3-p">—</div><div class="c-change" id="sg-onco3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">PNVL3</div><div class="c-price loading" id="sg-pnvl3-p">—</div><div class="c-change" id="sg-pnvl3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ODPV3</div><div class="c-price loading" id="sg-odpv3-p">—</div><div class="c-change" id="sg-odpv3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">MATD3</div><div class="c-price loading" id="sg-matd3-p">—</div><div class="c-change" id="sg-matd3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">AALR3</div><div class="c-price loading" id="sg-aalr3-p">—</div><div class="c-change" id="sg-aalr3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('industriais')"><span>🏗 Bens Industriais</span><span id="sarr-industriais">▼</span></div>
  <div class="sector-body" id="sbody-industriais" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">WEGE3</div><div class="c-price loading" id="sg-wege3-p">—</div><div class="c-change" id="sg-wege3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">EMBR3</div><div class="c-price loading" id="sg-embr3-p">—</div><div class="c-change" id="sg-embr3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">RAIL3</div><div class="c-price loading" id="sg-rail3-p">—</div><div class="c-change" id="sg-rail3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">TGMA3</div><div class="c-price loading" id="sg-tgma3-p">—</div><div class="c-change" id="sg-tgma3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ROMI3</div><div class="c-price loading" id="sg-romi3-p">—</div><div class="c-change" id="sg-romi3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">VLID3</div><div class="c-price loading" id="sg-vlid3-p">—</div><div class="c-change" id="sg-vlid3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">TUPY3</div><div class="c-price loading" id="sg-tupy3-p">—</div><div class="c-change" id="sg-tupy3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">IRBR3</div><div class="c-price loading" id="sg-irbr3-p">—</div><div class="c-change" id="sg-irbr3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">LPSB3</div><div class="c-price loading" id="sg-lpsb3-p">—</div><div class="c-change" id="sg-lpsb3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">KEPL3</div><div class="c-price loading" id="sg-kepl3-p">—</div><div class="c-change" id="sg-kepl3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('ti_telecom')"><span>💻 TI & Comunicações</span><span id="sarr-ti_telecom">▼</span></div>
  <div class="sector-body" id="sbody-ti_telecom" style="display:none">
    <div class="grid"><div class="card green"><div class="c-label">B3</div><div class="c-name">VIVT3</div><div class="c-price loading" id="sg-vivt3-p">—</div><div class="c-change" id="sg-vivt3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">TIMS3</div><div class="c-price loading" id="sg-tims3-p">—</div><div class="c-change" id="sg-tims3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">TOTVS3</div><div class="c-price loading" id="sg-totvs3-p">—</div><div class="c-change" id="sg-totvs3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">OIBR3</div><div class="c-price loading" id="sg-oibr3-p">—</div><div class="c-change" id="sg-oibr3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">LWSA3</div><div class="c-price loading" id="sg-lwsa3-p">—</div><div class="c-change" id="sg-lwsa3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">INTB3</div><div class="c-price loading" id="sg-intb3-p">—</div><div class="c-change" id="sg-intb3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">MLAS3</div><div class="c-price loading" id="sg-mlas3-p">—</div><div class="c-change" id="sg-mlas3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">ANIM3</div><div class="c-price loading" id="sg-anim3-p">—</div><div class="c-change" id="sg-anim3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">CASH3</div><div class="c-price loading" id="sg-cash3-p">—</div><div class="c-change" id="sg-cash3-c">—</div><div class="c-src">TV</div></div>
      <div class="card green"><div class="c-label">B3</div><div class="c-name">POSI3</div><div class="c-price loading" id="sg-posi3-p">—</div><div class="c-change" id="sg-posi3-c">—</div><div class="c-src">TV</div></div>
      </div>
  </div>



  <div class="sec" style="margin-top:20px"><span>🇺🇸</span> Estados Unidos <span class="src">· Yahoo Finance via proxy</span></div>

  <div class="sector-header" onclick="toggleSeg('mag7')"><span>⭐ As 7 Magníficas</span><span id="sarr-mag7">▼</span></div>
  <div class="sector-body" id="sbody-mag7" style="display:none">
    <div class="grid"><div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AAPL</div><div class="c-price loading" id="us-aapl-p">—</div><div class="c-change" id="us-aapl-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">MSFT</div><div class="c-price loading" id="us-msft-p">—</div><div class="c-change" id="us-msft-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">NVDA</div><div class="c-price loading" id="us-nvda-p">—</div><div class="c-change" id="us-nvda-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AMZN</div><div class="c-price loading" id="us-amzn-p">—</div><div class="c-change" id="us-amzn-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">GOOGL</div><div class="c-price loading" id="us-googl-p">—</div><div class="c-change" id="us-googl-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">META</div><div class="c-price loading" id="us-meta-p">—</div><div class="c-change" id="us-meta-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">TSLA</div><div class="c-price loading" id="us-tsla-p">—</div><div class="c-change" id="us-tsla-c">—</div><div class="c-src">Yahoo</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('nasdaq15')"><span>💻 Nasdaq Top 15</span><span id="sarr-nasdaq15">▼</span></div>
  <div class="sector-body" id="sbody-nasdaq15" style="display:none">
    <div class="grid"><div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AAPL</div><div class="c-price loading" id="nq-aapl-p">—</div><div class="c-change" id="nq-aapl-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">MSFT</div><div class="c-price loading" id="nq-msft-p">—</div><div class="c-change" id="nq-msft-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">NVDA</div><div class="c-price loading" id="nq-nvda-p">—</div><div class="c-change" id="nq-nvda-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AMZN</div><div class="c-price loading" id="nq-amzn-p">—</div><div class="c-change" id="nq-amzn-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">META</div><div class="c-price loading" id="nq-meta-p">—</div><div class="c-change" id="nq-meta-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">GOOGL</div><div class="c-price loading" id="nq-googl-p">—</div><div class="c-change" id="nq-googl-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">TSLA</div><div class="c-price loading" id="nq-tsla-p">—</div><div class="c-change" id="nq-tsla-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AVGO</div><div class="c-price loading" id="nq-avgo-p">—</div><div class="c-change" id="nq-avgo-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">COST</div><div class="c-price loading" id="nq-cost-p">—</div><div class="c-change" id="nq-cost-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">NFLX</div><div class="c-price loading" id="nq-nflx-p">—</div><div class="c-change" id="nq-nflx-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">QCOM</div><div class="c-price loading" id="nq-qcom-p">—</div><div class="c-change" id="nq-qcom-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AMD</div><div class="c-price loading" id="nq-amd-p">—</div><div class="c-change" id="nq-amd-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">ADBE</div><div class="c-price loading" id="nq-adbe-p">—</div><div class="c-change" id="nq-adbe-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">INTC</div><div class="c-price loading" id="nq-intc-p">—</div><div class="c-change" id="nq-intc-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">CSCO</div><div class="c-price loading" id="nq-csco-p">—</div><div class="c-change" id="nq-csco-c">—</div><div class="c-src">Yahoo</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('sp20')"><span>📊 S&P 500 Top 20</span><span id="sarr-sp20">▼</span></div>
  <div class="sector-body" id="sbody-sp20" style="display:none">
    <div class="grid"><div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AAPL</div><div class="c-price loading" id="sp-aapl-p">—</div><div class="c-change" id="sp-aapl-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">MSFT</div><div class="c-price loading" id="sp-msft-p">—</div><div class="c-change" id="sp-msft-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">NVDA</div><div class="c-price loading" id="sp-nvda-p">—</div><div class="c-change" id="sp-nvda-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AMZN</div><div class="c-price loading" id="sp-amzn-p">—</div><div class="c-change" id="sp-amzn-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">META</div><div class="c-price loading" id="sp-meta-p">—</div><div class="c-change" id="sp-meta-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">GOOGL</div><div class="c-price loading" id="sp-googl-p">—</div><div class="c-change" id="sp-googl-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">TSLA</div><div class="c-price loading" id="sp-tsla-p">—</div><div class="c-change" id="sp-tsla-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AVGO</div><div class="c-price loading" id="sp-avgo-p">—</div><div class="c-change" id="sp-avgo-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">BRK-B</div><div class="c-price loading" id="sp-brk_b-p">—</div><div class="c-change" id="sp-brk_b-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">JPM</div><div class="c-price loading" id="sp-jpm-p">—</div><div class="c-change" id="sp-jpm-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">LLY</div><div class="c-price loading" id="sp-lly-p">—</div><div class="c-change" id="sp-lly-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">V</div><div class="c-price loading" id="sp-v-p">—</div><div class="c-change" id="sp-v-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">UNH</div><div class="c-price loading" id="sp-unh-p">—</div><div class="c-change" id="sp-unh-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">XOM</div><div class="c-price loading" id="sp-xom-p">—</div><div class="c-change" id="sp-xom-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">MA</div><div class="c-price loading" id="sp-ma-p">—</div><div class="c-change" id="sp-ma-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">NFLX</div><div class="c-price loading" id="sp-nflx-p">—</div><div class="c-change" id="sp-nflx-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">PG</div><div class="c-price loading" id="sp-pg-p">—</div><div class="c-change" id="sp-pg-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">JNJ</div><div class="c-price loading" id="sp-jnj-p">—</div><div class="c-change" id="sp-jnj-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">HD</div><div class="c-price loading" id="sp-hd-p">—</div><div class="c-change" id="sp-hd-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">BAC</div><div class="c-price loading" id="sp-bac-p">—</div><div class="c-change" id="sp-bac-c">—</div><div class="c-src">Yahoo</div></div>
      </div>
  </div>

  <div class="sector-header" onclick="toggleSeg('dji20')"><span>🏛 Dow Jones Top 20</span><span id="sarr-dji20">▼</span></div>
  <div class="sector-body" id="sbody-dji20" style="display:none">
    <div class="grid"><div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">UNH</div><div class="c-price loading" id="dj-unh-p">—</div><div class="c-change" id="dj-unh-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">GS</div><div class="c-price loading" id="dj-gs-p">—</div><div class="c-change" id="dj-gs-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">HD</div><div class="c-price loading" id="dj-hd-p">—</div><div class="c-change" id="dj-hd-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">SHW</div><div class="c-price loading" id="dj-shw-p">—</div><div class="c-change" id="dj-shw-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">CAT</div><div class="c-price loading" id="dj-cat-p">—</div><div class="c-change" id="dj-cat-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AXP</div><div class="c-price loading" id="dj-axp-p">—</div><div class="c-change" id="dj-axp-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">MCD</div><div class="c-price loading" id="dj-mcd-p">—</div><div class="c-change" id="dj-mcd-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AMGN</div><div class="c-price loading" id="dj-amgn-p">—</div><div class="c-change" id="dj-amgn-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">V</div><div class="c-price loading" id="dj-v-p">—</div><div class="c-change" id="dj-v-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">TRV</div><div class="c-price loading" id="dj-trv-p">—</div><div class="c-change" id="dj-trv-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">IBM</div><div class="c-price loading" id="dj-ibm-p">—</div><div class="c-change" id="dj-ibm-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">JPM</div><div class="c-price loading" id="dj-jpm-p">—</div><div class="c-change" id="dj-jpm-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">HON</div><div class="c-price loading" id="dj-hon-p">—</div><div class="c-change" id="dj-hon-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">CRM</div><div class="c-price loading" id="dj-crm-p">—</div><div class="c-change" id="dj-crm-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">CVX</div><div class="c-price loading" id="dj-cvx-p">—</div><div class="c-change" id="dj-cvx-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">AAPL</div><div class="c-price loading" id="dj-aapl-p">—</div><div class="c-change" id="dj-aapl-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">MSFT</div><div class="c-price loading" id="dj-msft-p">—</div><div class="c-change" id="dj-msft-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">DIS</div><div class="c-price loading" id="dj-dis-p">—</div><div class="c-change" id="dj-dis-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">NKE</div><div class="c-price loading" id="dj-nke-p">—</div><div class="c-change" id="dj-nke-c">—</div><div class="c-src">Yahoo</div></div>
      <div class="card blue"><div class="c-label">NYSE/NASDAQ</div><div class="c-name">BA</div><div class="c-price loading" id="dj-ba-p">—</div><div class="c-change" id="dj-ba-c">—</div><div class="c-src">Yahoo</div></div>
      </div>
  </div>

  <div class="sec"><span>03</span> Commodities <span class="src">· Hyperliquid 24/7</span></div>
  <div class="grid">
    <div class="card danger"><div class="c-label">Energia · WTI</div><div class="c-name">Petróleo CL</div><div class="c-price loading" id="cl-p">—</div><div class="c-change" id="cl-c">—</div><div class="c-src">HL</div></div>
    <div class="card gold"><div class="c-label">Metal · XAU</div><div class="c-name">Ouro</div><div class="c-price gold-c loading" id="gold-p">—</div><div class="c-change" id="gold-c2">—</div><div class="c-src">HL</div></div>
    <div class="card silver"><div class="c-label">Metal · XAG</div><div class="c-name">Prata</div><div class="c-price silver-c loading" id="silver-p">—</div><div class="c-change" id="silver-c">—</div><div class="c-src">HL</div></div>
    <div class="card orange"><div class="c-label">Metal · HG</div><div class="c-name">Cobre</div><div class="c-price copper-c loading" id="copper-p">—</div><div class="c-change" id="copper-c">—</div><div class="c-src">HL</div></div>
  </div>

  <div class="sec"><span>04</span> Bitcoin — Indicadores de Mercado <span class="src">· Hyperliquid + Binance</span></div>
  <div class="grid2">
    <div class="card btc">
      <div class="c-label">Cripto · BTC/USD</div>
      <div class="c-name">Bitcoin</div>
      <div class="c-price btc-c loading" id="btc-p">—</div>
      <div class="c-change" id="btc-c">—</div>
      <div class="ind-grid">
        <div class="ind-box"><div class="ind-lbl">RSI Semanal</div><div class="ind-val warn" id="btc-rsi">—</div></div>
        <div class="ind-box"><div class="ind-lbl">Tendência</div><div class="ind-val" id="btc-trend">—</div></div>
        <div class="ind-box"><div class="ind-lbl">VIX Cripto</div><div class="ind-val" id="btc-vix">—</div></div>
      </div>
    </div>
    <div class="card btc">
      <div class="c-label">Análise Técnica</div>
      <div class="c-name" style="margin-bottom:8px">RSI Semanal</div>
      <div class="rsi-wrap">
        <div class="rsi-hdr"><span>RSI Semanal (aprox)</span><span id="rsi-val" style="color:var(--warn)">—</span></div>
        <div class="rsi-track"><div class="rsi-needle" id="rsi-n" style="left:45%"></div></div>
        <div class="rsi-zones"><span>&lt;30 sobrev.</span><span>neutro</span><span>&gt;70 sobrec.</span></div>
      </div>
      <div class="signal">
        <div class="sig-title">⚡ Divergência Bullish RSI</div>
        <div id="btc-sig">Carregando...</div>
      </div>
      <div class="fr-box">
        <div class="fr-title">💰 Funding Rate — Binance Perpétuos</div>
        <div class="fr-vals">
          <div><div class="fr-lbl">Taxa 8h</div><div class="fr-val" id="fr-bin">—</div></div>
          <div><div class="fr-lbl">Próx. funding</div><div class="fr-next" id="fr-next">—</div></div>
        </div>
        <div class="fr-sig" id="fr-sig">Carregando...</div>
        <div class="fr-ref">Ref: topo ≈ +0.08% · neutro ≈ 0.01% · fundo ≈ -0.010%</div>
      </div>
    </div>
  </div>

</div><!-- /tab-cotacoes -->

<!-- ═══════════════════════════════════════════════════ -->
<!-- TAB 2: MINHAS POSIÇÕES -->
<!-- ═══════════════════════════════════════════════════ -->
<div id="tab-posicoes" class="tab-content">

  <div class="sec"><span>01</span> Ações B3 — Operações Estruturadas</div>

  <!-- PETR4 -->
  <div class="pos-card acao">
    <div class="pos-label">Petrobras PN · Call Vendida · PETRL319 · Venc 17/12/2026</div>
    <div class="pos-ticker">PETR4</div>
    <div class="pos-price loading" id="pt-pos-p">—</div>
    <div class="pos-chg" id="pt-pos-c">—</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Preço Ref.</span><span class="sb-val">R$ 30,85</span></div>
      <div class="sb-row"><span class="sb-lbl">Strike vendido</span><span class="sb-val warn">R$ 30,85 (PETRL319)</span></div>
      <div class="sb-row"><span class="sb-lbl">Dist. ao strike</span><span class="sb-val itm" id="pt-itm">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Vencimento</span><span class="sb-val">17/12/2026 · <span id="pt-dias">—</span> dias</span></div>
      <div class="sb-row"><span class="sb-lbl">Vol. Implícita</span><span class="sb-val warn">43,4%</span></div>
      <div class="sb-row"><span class="sb-lbl">Prob. MC / B&S</span><span class="sb-val">8,3% / 9,4%</span></div>
      <div class="sb-row"><span class="sb-lbl">% p/ gatilho R$40</span><span class="sb-val warn" id="pt-pct-gatilho">—</span></div>
      <div class="prog-wrap"><div class="prog-bar danger" id="pt-bar" style="width:0%"></div></div>
    </div>
    <div class="signal" style="margin-top:8px;border-color:var(--blue)">
      <div class="sig-title" style="color:var(--blue)">🎲 Monte Carlo — Prob. cair ao strike R$30,85</div>
      <div id="mc-pt-loading" style="font-size:.65rem;color:var(--muted)">Calculando...</div>
      <div id="mc-pt-result" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
          <div class="ind-box"><div class="ind-lbl">Prob. cair ao strike</div><div class="ind-val ok" id="mc-pt-strike">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Vol. Histórica</div><div class="ind-val warn" id="mc-pt-vol">—</div></div>
        </div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:6px" id="mc-pt-info">—</div>
      </div>
    </div>
  </div>

  <!-- VALE3 -->
  <div class="pos-card acao" style="margin-top:12px">
    <div class="pos-label">Vale ON · Call Vendida · VALEB574 · Venc 18/02/2027</div>
    <div class="pos-ticker">VALE3</div>
    <div class="pos-price loading" id="vl-pos-p">—</div>
    <div class="pos-chg" id="vl-pos-c">—</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Preço Ref.</span><span class="sb-val">R$ 57,40</span></div>
      <div class="sb-row"><span class="sb-lbl">Strike vendido</span><span class="sb-val warn">R$ 57,40 (VALEB574)</span></div>
      <div class="sb-row"><span class="sb-lbl">Dist. ao strike</span><span class="sb-val itm" id="vl-itm">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Vencimento</span><span class="sb-val">18/02/2027 · <span id="vl-dias">—</span> dias</span></div>
      <div class="sb-row"><span class="sb-lbl">Vol. Implícita</span><span class="sb-val warn">71,2%</span></div>
      <div class="sb-row"><span class="sb-lbl">Prob. MC / B&S</span><span class="sb-val">11,5% / 14,2%</span></div>
      <div class="sb-row"><span class="sb-lbl">Gatilhos</span><span class="sb-val warn">R$ 70 · R$ 80 · R$ 85</span></div>
      <div class="sb-row"><span class="sb-lbl">% p/ R$70</span><span class="sb-val warn" id="vl-pct-gatilho">—</span></div>
      <div class="prog-wrap"><div class="prog-bar danger" id="vl-bar" style="width:0%"></div></div>
    </div>
    <div class="signal" style="margin-top:8px;border-color:var(--blue)">
      <div class="sig-title" style="color:var(--blue)">🎲 Monte Carlo — Prob. cair ao strike R$57,40</div>
      <div id="mc-vl-loading" style="font-size:.65rem;color:var(--muted)">Calculando...</div>
      <div id="mc-vl-result" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
          <div class="ind-box"><div class="ind-lbl">Prob. cair ao strike</div><div class="ind-val ok" id="mc-vl-strike">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Vol. Histórica</div><div class="ind-val warn" id="mc-vl-vol">—</div></div>
        </div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:6px" id="mc-vl-info">—</div>
      </div>
    </div>
  </div>

  <!-- AXIA3 (A) FENCE -->
  <div class="pos-card acao" style="margin-top:12px">
    <div class="pos-label">AXIA3 (A) · Bidirecional · Venc 14/09/2026</div>
    <div class="pos-ticker">AXIA3</div>
    <div class="pos-price loading" id="axia3-pos-p">—</div>
    <div class="pos-chg" id="axia3-pos-c">—</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Preço Ref.</span><span class="sb-val">R$ 54,31</span></div>
      <div class="sb-row"><span class="sb-lbl">KDO (Barreira Baixa)</span><span class="sb-val warn">R$ 43,51 (-20%)</span></div>
      <div class="sb-row"><span class="sb-lbl">KUO (Barreira Alta)</span><span class="sb-val warn">R$ 68,76 (+26,6%)</span></div>
      <div class="sb-row"><span class="sb-lbl">Ganho s/ barreira</span><span class="sb-val ok">até +31,20% alta / +20% baixa</span></div>
      <div class="sb-row"><span class="sb-lbl">Ganho c/ barreira alta</span><span class="sb-val warn">+4% fixo</span></div>
      <div class="sb-row"><span class="sb-lbl">Vencimento</span><span class="sb-val">14/09/2026 · <span id="axia3f-dias">—</span> dias</span></div>
      <div class="sb-row"><span class="sb-lbl">Vol. Implícita</span><span class="sb-val warn">35,0%</span></div>
      <div class="sb-row"><span class="sb-lbl">Prob. MC / B&S</span><span class="sb-val ok">68,5% / 73,0%</span></div>
      <div class="sb-row"><span class="sb-lbl">Dist. ao KDO</span><span class="sb-val" id="axia3-kdo-dist">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Dist. ao KUO</span><span class="sb-val" id="axia3-kuo-dist">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Situação</span><span class="sb-val" id="axia3-status">—</span></div>
    </div>
    <div class="signal" style="margin-top:8px;border-color:var(--blue)">
      <div class="sig-title" style="color:var(--blue)">🎲 Monte Carlo — Prob. de cada cenário</div>
      <div id="mc-axia3-loading" style="font-size:.65rem;color:var(--muted)">Calculando...</div>
      <div id="mc-axia3-result" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px">
          <div class="ind-box"><div class="ind-lbl">Sem Barreira ✅</div><div class="ind-val ok" id="mc-axia3-nobr">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Bar. Alta KUO</div><div class="ind-val warn" id="mc-axia3-kuo">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Bar. Baixa KDO</div><div class="ind-val down" id="mc-axia3-kdo">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Vol. Histórica</div><div class="ind-val warn" id="mc-axia3-vol">—</div></div>
        </div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:6px" id="mc-axia3-info">—</div>
      </div>
    </div>
  </div>

  <!-- AXIA3 (B) BIDIRECIONAL - NOVA -->
  <div class="pos-card acao" style="margin-top:12px">
    <div class="pos-label">AXIA3 (B) · Bidirecional ION Itaú · Venc 02/10/2026</div>
    <div class="pos-ticker">AXIA3</div>
    <div class="pos-price loading" id="axia3b-pos-p">—</div>
    <div class="pos-chg" id="axia3b-pos-c">—</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Preço Ref.</span><span class="sb-val">R$ 50,65</span></div>
      <div class="sb-row"><span class="sb-lbl">KDO (Barreira Baixa)</span><span class="sb-val warn">R$ 40,52 (-20%)</span></div>
      <div class="sb-row"><span class="sb-lbl">KUO (Barreira Alta)</span><span class="sb-val warn">R$ 62,81 (+24%)</span></div>
      <div class="sb-row"><span class="sb-lbl">Ganho s/ barreira</span><span class="sb-val ok">até +31,20% alta / +20% baixa</span></div>
      <div class="sb-row"><span class="sb-lbl">Ganho c/ barreira alta</span><span class="sb-val warn">+4% fixo (12,33% a.a.)</span></div>
      <div class="sb-row"><span class="sb-lbl">Ganho c/ barreira baixa</span><span class="sb-val itm">proporcional à queda</span></div>
      <div class="sb-row"><span class="sb-lbl">Vencimento</span><span class="sb-val">02/10/2026 · <span id="axia3b-dias">—</span> dias</span></div>
      <div class="sb-row"><span class="sb-lbl">Vol. Implícita</span><span class="sb-val warn">35,0%</span></div>
      <div class="sb-row"><span class="sb-lbl">Prob. MC / B&S</span><span class="sb-val ok">68,5% / 73,0%</span></div>
      <div class="sb-row"><span class="sb-lbl">Dist. ao KDO</span><span class="sb-val" id="axia3b-kdo-dist">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Dist. ao KUO</span><span class="sb-val" id="axia3b-kuo-dist">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Situação</span><span class="sb-val" id="axia3b-status">—</span></div>
    </div>
    <div class="signal" style="margin-top:8px;border-color:var(--blue)">
      <div class="sig-title" style="color:var(--blue)">🎲 Monte Carlo — Prob. de cada cenário</div>
      <div id="mc-axia3b-loading" style="font-size:.65rem;color:var(--muted)">Calculando...</div>
      <div id="mc-axia3b-result" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px">
          <div class="ind-box"><div class="ind-lbl">Sem Barreira ✅</div><div class="ind-val ok" id="mc-axia3b-nobr">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Bar. Alta KUO</div><div class="ind-val warn" id="mc-axia3b-kuo">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Bar. Baixa KDO</div><div class="ind-val down" id="mc-axia3b-kdo">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Vol. Histórica</div><div class="ind-val warn" id="mc-axia3b-vol">—</div></div>
        </div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:6px" id="mc-axia3b-info">—</div>
      </div>
    </div>
  </div>

  <!-- ROXO34 ATIVO -->
  <div class="pos-card acao" style="margin-top:12px">
    <div class="pos-label">ROXO34 · BDR Nubank · Prefixado c/ Barreira · Venc 16/07/2026</div>
    <div class="pos-ticker">ROXO34</div>
    <div class="pos-price loading" id="roxo34-pos-p">—</div>
    <div class="pos-chg" id="roxo34-pos-c">—</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Preço Ref.</span><span class="sb-val">R$ 12,88</span></div>
      <div class="sb-row"><span class="sb-lbl">Strike (ROXOG105)</span><span class="sb-val warn">R$ 10,50</span></div>
      <div class="sb-row"><span class="sb-lbl">KDO (Barreira)</span><span class="sb-val warn">R$ 10,50 (-18,70%)</span></div>
      <div class="sb-row"><span class="sb-lbl">Vol. Implícita</span><span class="sb-val warn">39,0%</span></div>
      <div class="sb-row"><span class="sb-lbl">Prob. MC / B&S</span><span class="sb-val warn">43,2% / 47,07%</span></div>
      <div class="sb-row"><span class="sb-lbl">Vencimento</span><span class="sb-val">16/07/2026 · <span id="roxo34-dias">—</span> dias</span></div>
      <div class="sb-row"><span class="sb-lbl">Dist. à barreira</span><span class="sb-val" id="roxo34-kdo-dist">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Situação</span><span class="sb-val" id="roxo34-status">—</span></div>
    </div>
    <div class="signal" style="margin-top:8px;border-color:var(--blue)">
      <div class="sig-title" style="color:var(--blue)">🎲 Monte Carlo — Prob. de sucesso</div>
      <div id="mc-roxo34-loading" style="font-size:.65rem;color:var(--muted)">Calculando...</div>
      <div id="mc-roxo34-result" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
          <div class="ind-box"><div class="ind-lbl">Prob. Sucesso</div><div class="ind-val ok" id="mc-roxo34-sucesso">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Call Exercida</div><div class="ind-val" id="mc-roxo34-call">—</div></div>
          <div class="ind-box"><div class="ind-lbl">KDO Atingido</div><div class="ind-val" id="mc-roxo34-kdo">—</div></div>
          <div class="ind-box"><div class="ind-lbl">Vol. Histórica</div><div class="ind-val warn" id="mc-roxo34-vol">—</div></div>
        </div>
        <div style="font-size:.6rem;color:var(--muted);margin-top:6px" id="mc-roxo34-info">—</div>
      </div>
    </div>
  </div>

  <!-- POSIÇÕES ENCERRADAS -->
  <div class="sec" style="margin-top:20px"><span>📁</span> Posições Encerradas</div>

  <!-- BBAS3 ENCERRADA -->
  <div class="pos-card acao" style="margin-top:8px;opacity:0.7;border-color:var(--muted)">
    <div class="pos-label" style="color:var(--muted)">BBAS3 · Call Vendida · Encerrada — 80% do alvo em 70% do prazo</div>
    <div class="pos-ticker" style="color:var(--muted)">BBAS3</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Strike</span><span class="sb-val">BBASH21 (R$ 21,65)</span></div>
      <div class="sb-row"><span class="sb-lbl">Preço Ref.</span><span class="sb-val">R$ 20,67</span></div>
      <div class="sb-row"><span class="sb-lbl">Vencimento original</span><span class="sb-val">20/08/2026</span></div>
      <div class="sb-row"><span class="sb-lbl">Vol. Implícita</span><span class="sb-val">27,62%</span></div>
      <div class="sb-row"><span class="sb-lbl">Resultado</span><span class="sb-val ok">✅ 80% do lucro alvo em 70% do prazo</span></div>
    </div>
  </div>

  <!-- AXIA3 SHORT STRANGLE ENCERRADA -->
  <div class="pos-card acao" style="margin-top:8px;opacity:0.7;border-color:var(--muted)">
    <div class="pos-label" style="color:var(--muted)">AXIA3 · Short Strangle · Encerrada — ações liberadas</div>
    <div class="pos-ticker" style="color:var(--muted)">AXIA3</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Call Vendida</span><span class="sb-val">AXIAI505 (R$ 50,50)</span></div>
      <div class="sb-row"><span class="sb-lbl">Put Vendida</span><span class="sb-val">AXIAU600 (R$ 60,00)</span></div>
      <div class="sb-row"><span class="sb-lbl">Resultado</span><span class="sb-val ok">✅ Ações liberadas</span></div>
    </div>
  </div>

  <!-- ROXO34 ENCERRADA ANTERIOR -->
  <div class="pos-card acao" style="margin-top:8px;opacity:0.7;border-color:var(--muted)">
    <div class="pos-label" style="color:var(--muted)">ROXO34 · Prefixado 7,1% · Encerrada em 04/06/2026</div>
    <div class="pos-ticker" style="color:var(--muted)">ROXO34</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Preço entrada</span><span class="sb-val">R$ 12,67</span></div>
      <div class="sb-row"><span class="sb-lbl">KDO</span><span class="sb-val">R$ 9,60</span></div>
      <div class="sb-row"><span class="sb-lbl">Retorno alvo</span><span class="sb-val">7,10%</span></div>
      <div class="sb-row"><span class="sb-lbl">Retorno obtido</span><span class="sb-val ok">~5,17% (72% do alvo) ✅</span></div>
      <div class="sb-row"><span class="sb-lbl">Tempo no trade</span><span class="sb-val ok">~50% do prazo</span></div>
    </div>
  </div>

  <!-- BITCOIN -->
  <div class="sec" style="margin-top:20px"><span>02</span> Cripto — Bitcoin · Estratégia</div></div><!-- /tab-posicoes -->

<!-- ═══════════════════════════════════════════════════ -->
<!-- TAB: INDICADORES & SINAIS -->
<!-- ═══════════════════════════════════════════════════ -->
<div id="tab-indicadores" class="tab-content">

  <div class="sec"><span>📊</span> Indicadores & Sinal — PETR4 <span class="src">· Yahoo Finance + Fundamentus</span></div>
  <div id="petr4-ind-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores...</div>
  </div>

  <div class="sec" style="margin-top:16px"><span>📊</span> Indicadores & Sinal — VALE3</div>
  <div id="vale3-ind-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores...</div>
  </div>

  <div class="sec" style="margin-top:16px"><span>📊</span> Indicadores & Sinal — BBAS3</div>
  <div id="bbas3-ind-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores...</div>
  </div>

  <div class="sec" style="margin-top:16px"><span>📊</span> Indicadores & Sinal — AXIA3</div>
  <div id="axia3-ind-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores...</div>
  </div>

  <div class="sec" style="margin-top:16px"><span>📊</span> Indicadores & Sinal — ROXO34</div>
  <div id="roxo34-ind-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores...</div>
  </div>

  <div class="sec" style="margin-top:16px"><span>🔄</span> Dashboard de Ciclo — Bitcoin</div>
  <div id="btc-cycle-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores de ciclo...</div>
  </div>

  <div class="sec" style="margin-top:16px"><span>📊</span> Indicadores Técnicos — Bitcoin Semanal</div>
  <div style="display:grid;grid-template-columns:1fr auto;gap:10px;margin-bottom:10px;align-items:start">
    <div id="fear-greed-area">
      <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando Fear & Greed...</div>
    </div>
    <div style="background:var(--bg2);border:1px solid var(--border);padding:14px;min-width:130px;text-align:center">
      <div style="font-size:.55rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">BTC / USD</div>
      <div class="c-price btc-c loading" id="btc-ind-price">—</div>
      <div class="c-change" id="btc-ind-chg">—</div>
    </div>
  </div>
  <div id="btc-ind-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores BTC...</div>
  </div>

</div><!-- /tab-indicadores -->

</div><!-- /tab-posicoes -->

<!-- ═══════════════════════════════════════════════════ -->
<!-- TAB: CALENDÁRIO ECONÔMICO -->
<!-- ═══════════════════════════════════════════════════ -->
<div id="tab-calendario" class="tab-content">
  <div class="sbar" style="margin-bottom:12px">
    <div class="pill ok">🇺🇸 EUA</div>
    <div class="pill ok">🇧🇷 Brasil</div>
    <div class="pill ok">🇪🇺 Zona Euro</div>
    <div class="pill ok">🇬🇧 UK</div>
    <div class="pill ok">🇨🇳 China</div>
    <div class="pill ok">🇯🇵 Japão</div>
    <div class="pill ok">🇩🇪 Alemanha</div>
    <button class="refresh-btn" onclick="loadCalendar()">↻ Atualizar</button>
  </div>
  <div id="calendar-area">
    <div style="color:var(--muted);font-size:.65rem;padding:20px;text-align:center">Clique em Atualizar para carregar eventos econômicos</div>
  </div>
</div><!-- /tab-calendario -->

<footer>
  <span>Hyperliquid xyz: (índices + commodities + cripto) · TradingView proxy (B3) · Binance Futures (funding)</span>
  <span id="ftr">—</span>
</footer>
</div><!-- /wrap -->

<!-- DEBUG BAR -->
<div id="debug-bar">
  <span>HL cripto: <b id="db-hlc">—</b></span>
  <span>HL xyz: <b id="db-hlx">—</b></span>
  <span>TV B3: <b id="db-tv">—</b></span>
  <span>Funding: <b id="db-fr">—</b></span>
</div>

<script>
// ── TABS ──────────────────────────────────────────────
function toggleSector(id){
  const el=document.getElementById('sec-'+id);
  const arr=document.getElementById('arr-'+id);
  if(!el)return;
  const open=el.style.display==='none';
  el.style.display=open?'block':'none';
  if(arr)arr.textContent=open?'▲':'▼';
  // Fetch sector data on first open
  if(open&&!el.dataset.loaded){
    el.dataset.loaded='1';
    fetchSector(id);
  }
}

// Sector tickers map
const SECTOR_TICKERS={
  'financeiro':['ITUB4','BBDC4','BBAS3','SANB11','B3SA3','BPAC11','IRBR3','SULA11','PSSA3','CIEL3'],
  'petroleo_e_gas':['PETR4','PETR3','PRIO3','UGPA3','VBBR3','CSAN3','RECV3','RRRP3','DMMO3','ENAT3'],
  'materiais_basicos':['VALE3','GGBR4','CSNA3','SUZB3','KLBN11','USIM5','BRAP4','UNIP6','FESA4','CBAV3'],
  'utilidade_publica':['ELET3','EQTL3','CPFE3','SBSP3','CMIG4','ENGI11','TAEE11','TRPL4','AURE3','EGIE3'],
  'consumo_ciclico':['RENT3','LREN3','MGLU3','CYRE3','MRVE3','AZUL4','CVCB3','COGN3','LWSA3','VIVA3'],
  'consumo_nao_ciclico':['ABEV3','JBSS3','BRFS3','NATU3','MDIA3','BEEF3','SLCE3','MTRE3','PCAR3','CAML3'],
  'saude':['RDOR3','HAPV3','FLRY3','DASA3','QUAL3','ONCO3','PNVL3','ODPV3','MATD3','AALR3'],
  'bens_industriais':['WEGE3','EMBR3','RAIL3','TGMA3','ROMI3','FRAS3','TUPY3','PMAM3','VLID3','LPSB3'],
  'ti_e_comunicacoes':['VIVT3','TIMS3','TOTVS3','OIBR3','LWSA3','INTB3','MLAS3','ANIM3','DESK3','LWSA3'],
};

async function fetchSector(id){
  const tickers=SECTOR_TICKERS[id];
  if(!tickers)return;
  try{
    const tvTickers=tickers.map(t=>'BMFBOVESPA:'+t);
    const r=await fetch('https://trader-desk.onrender.com/tv/brazil',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbols:{tickers:tvTickers},columns:['close','change_abs']})
    });
    if(!r.ok)return;
    const d=await r.json();
    (d.data||[]).forEach(x=>{
      const t=x.s.replace('BMFBOVESPA:','').toLowerCase();
      const [close,chg]=x.d||[];
      if(close!=null){
        const prev=close-(chg||0);
        const pEl=document.getElementById(`s-${t}-p`);
        const cEl=document.getElementById(`s-${t}-c`);
        if(pEl){pEl.textContent=fBRL(close);pEl.className=pEl.classList.remove('loading');}
        if(cEl)setChg(`s-${t}-c`,close,prev,'brl');
      }
    });
  }catch(e){}
}

function switchTab(tab){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  event.target.classList.add('active');
  if(tab==='indicadores'&&!window._indLoaded){
    window._indLoaded=true;
    loadIndicators();
  }
  if(tab==='calendario'){
    loadCalendar();
  }
}

// ── CLOCK ─────────────────────────────────────────────
function tick(){
  const n=new Date();
  document.getElementById('clk').textContent=n.toLocaleTimeString('pt-BR');
  document.getElementById('clk-date').textContent=n.toLocaleDateString('pt-BR',{weekday:'short',day:'2-digit',month:'short',year:'numeric'});
}
setInterval(tick,1000);tick();

function checkMarkets(){
  const br=new Date(new Date().toLocaleString('en-US',{timeZone:'America/Sao_Paulo'}));
  const ny=new Date(new Date().toLocaleString('en-US',{timeZone:'America/New_York'}));
  const b3=br.getDay()>=1&&br.getDay()<=5&&br.getHours()>=10&&br.getHours()<18;
  const us=ny.getDay()>=1&&ny.getDay()<=5&&ny.getHours()>=9&&ny.getHours()<16;
  const pb3=document.getElementById('pill-b3'),pus=document.getElementById('pill-us');
  pb3.textContent=b3?'B3 ● ABERTO':'B3 ○ FECHADO';pb3.className='pill '+(b3?'live':'closed');
  pus.textContent=us?'EUA ● ABERTO':'EUA ○ FECHADO';pus.className='pill '+(us?'live':'closed');
  document.getElementById('mkt-st').textContent=b3?'B3 aberta':us?'EUA aberto':'Mercados fechados';
}

// ── HELPERS ───────────────────────────────────────────
const fBRL=v=>'R$ '+Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const fUSD=v=>'US$ '+Number(v).toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:0});
const fUSD2=v=>'US$ '+Number(v).toFixed(2);
const fPTS=v=>Number(v).toLocaleString('pt-BR',{maximumFractionDigits:0});

function setEl(id,txt){
  const e=document.getElementById(id);if(!e)return;
  e.textContent=txt;e.classList.remove('loading');
}
function setChg(id,p,prev,fmt){
  const e=document.getElementById(id);if(!e||!prev||isNaN(prev)||isNaN(p))return;
  const d=p-prev,pct=(d/prev*100),s=d>=0?'+':'';
  let ds=fmt==='brl'?`${s}R$ ${Math.abs(d).toFixed(2)}`:fmt==='usd'?`${s}US$ ${Math.abs(d).toFixed(2)}`:`${s}${Math.abs(d).toFixed(0)} pts`;
  e.textContent=`${ds} (${s}${pct.toFixed(2)}%)`;
  const base=e.className.includes('pos-chg')?'pos-chg':'c-change';
  e.className=base+' '+(d>=0?'up':'down');
}

// ── FALLBACKS (valores de hoje corrigidos) ────────────
const FB={
  SP500:{p:7165,v:7080},ESFUT:{p:7194,v:7110},NDX:{p:27301,v:27000},NQFUT:{p:27435,v:27150},DJI:{p:49230,v:48800},
  DXY:{p:99.024,v:98.8},VIX:{p:18.26,v:18.5},
  IBOV:{p:130740,v:129500},USDBRL:{p:4.95,v:5.01},
  CL:{p:63.02,v:63.02},GOLD:{p:3320,v:3320},
  SILVER:{p:32.50,v:32.50},COPPER:{p:4.85,v:4.85},
  PETR4:{p:47.44,v:47.01},VALE3:{p:85.38,v:85.82},BBAS3:{p:23.44,v:23.20},
  BTC:{p:75940,v:75940}
};

// ── HYPERLIQUID — guarda preços anteriores para variação correta
let HLC={},HLX={},HLC_PREV={},HLX_PREV={};
async function fetchHL(){
  // Guarda versão anterior antes de atualizar
  HLC_PREV={...HLC};
  HLX_PREV={...HLX};

  try{
    const r=await fetch('https://api.hyperliquid.xyz/info',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type:'allMids'})
    });
    if(r.ok){
      HLC=await r.json();
      document.getElementById('db-hlc').textContent=`OK BTC=${Number(HLC['BTC']||0).toFixed(0)}`;
      document.getElementById('db-hlc').className='ok';
    }
  }catch(e){
    document.getElementById('db-hlc').textContent='ERRO: '+e.message;
    document.getElementById('db-hlc').className='err';
    HLC={};
  }
  try{
    const r=await fetch('https://api.hyperliquid.xyz/info',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type:'allMids',dex:'xyz'})
    });
    if(r.ok){
      HLX=await r.json();
      document.getElementById('db-hlx').textContent=`OK ${Object.keys(HLX).length} ativos`;
      document.getElementById('db-hlx').className='ok';
    }
  }catch(e){
    document.getElementById('db-hlx').textContent='ERRO: '+e.message;
    document.getElementById('db-hlx').className='err';
    HLX={};
  }
}

// Tickers confirmados com prefixo xyz:
function hlXyz(k){
  if(HLX['xyz:'+k]!=null)return parseFloat(HLX['xyz:'+k]);
  if(HLX[k]!=null)return parseFloat(HLX[k]);
  return null;
}
function hlXyzPrev(k){
  if(HLX_PREV['xyz:'+k]!=null)return parseFloat(HLX_PREV['xyz:'+k]);
  return null;
}
function hlCrypto(k){return HLC[k]!=null?parseFloat(HLC[k]):null;}
function hlCryptoPrev(k){return HLC_PREV[k]!=null?parseFloat(HLC_PREV[k]):null;}

// ── DOW JONES VIA PROXY ──────────────────────────────
async function fetchFutures(){
  const results={dji:null,esf:null,nqf:null};
  try{
    const r=await fetch('https://trader-desk.onrender.com/futures');
    if(r.ok){
      const d=await r.json();
      results.dji=d.dji||null;
      results.esf=d.esf||null;
      results.nqf=d.nqf||null;
    }
  }catch{}
  return results;
}

// ── TRADINGVIEW via proxy ─────────────────────────────
async function fetchTV(){
  const out={};
  // Busca todos os ativos B3 de uma vez
  const allTickers=['BMFBOVESPA:PETR4','BMFBOVESPA:ITUB4','BMFBOVESPA:VALE3','BMFBOVESPA:BBDC4',
    'BMFBOVESPA:ABEV3','BMFBOVESPA:BBAS3','BMFBOVESPA:WEGE3','BMFBOVESPA:RDOR3','BMFBOVESPA:IBOV'];
  try{
    const r=await fetch('https://trader-desk.onrender.com/tv/brazil',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbols:{tickers:allTickers},columns:['close','change_abs']})
    });
    if(r.ok){
      const d=await r.json();
      (d.data||[]).forEach(x=>{
        const[c,ca]=x.d||[];
        if(c!=null)out[x.s]={p:c,v:c-(ca||0)};
      });
    }
  }catch{}
  try{
    const r=await fetch('https://trader-desk.onrender.com/tv/forex',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbols:{tickers:['FX_IDC:USDBRL']},columns:['close','change_abs']})
    });
    if(r.ok){
      const d=await r.json();
      (d.data||[]).forEach(x=>{
        const [close,chgAbs]=x.d||[];
        if(close!=null)out[x.s]={p:close,v:close-(chgAbs||0)};
      });
    }
  }catch{}
  const n=Object.keys(out).length;
  document.getElementById('db-tv').textContent=n>0?`OK ${n} ativos`:'proxy offline';
  document.getElementById('db-tv').className=n>0?'ok':'err';
  return out;
}

// ── INDICADORES B3 + BTC ─────────────────────────────
async function fetchIndicators(ticker){
  try{
    const r=await fetch(`https://trader-desk.onrender.com/indicators/${ticker}`);
    if(!r.ok)throw 0;
    return await r.json();
  }catch{return null;}
}

async function fetchBTCCycle(){
  try{
    const r=await fetch('https://trader-desk.onrender.com/btc/cycle');
    if(!r.ok)throw 0;
    return await r.json();
  }catch{return null;}
}

async function fetchBTCIndicators(){
  try{
    const r=await fetch('https://trader-desk.onrender.com/btc/indicators');
    if(!r.ok)throw 0;
    return await r.json();
  }catch{return null;}
}

// ── BINANCE FUNDING ───────────────────────────────────
async function fetchFunding(){
  try{
    const r=await fetch('https://trader-desk.onrender.com/binance/funding');
    if(!r.ok)throw 0;
    const d=await r.json();
    const fr=parseFloat(d.lastFundingRate||d.fundingRate||'0')*100;
    if(isNaN(fr)||fr===0&&!d.lastFundingRate){throw 0;}
    const diffMin=Math.round((d.nextFundingTime-Date.now())/60000);
    const frEl=document.getElementById('fr-bin');
    frEl.textContent=fr.toFixed(4)+'%';
    frEl.style.color=fr<-0.005?'var(--red)':fr>0.05?'var(--danger)':'var(--warn)';
    document.getElementById('fr-next').textContent=diffMin>60?`${Math.floor(diffMin/60)}h ${diffMin%60}min`:`${diffMin} min`;
    document.getElementById('btc-pos-fr').textContent=fr.toFixed(4)+'%';
    document.getElementById('btc-pos-fr').style.color=fr<-0.005?'var(--red)':fr>0.05?'var(--danger)':'var(--warn)';
    const sig=document.getElementById('fr-sig');
    if(fr<-0.01)sig.innerHTML=`<span style="color:var(--accent)">⚡ NEGATIVO — Sinal de fundo potencial.</span> Maioria short. Historicamente marca fundos.`;
    else if(fr<0)sig.innerHTML=`<span style="color:var(--accent)">Levemente negativo.</span> Mais shorts que longs.`;
    else if(fr<0.01)sig.innerHTML=`<span style="color:var(--warn)">⚠ NEUTRO</span> — Mercado equilibrado.`;
    else if(fr<0.05)sig.innerHTML=`<span style="color:var(--blue)">Positivo moderado.</span> Leve viés de alta.`;
    else sig.innerHTML=`<span style="color:var(--danger)">🔴 ALTO.</span> Muitos longs alavancados. Risco de cascata.`;
    document.getElementById('db-fr').textContent=`OK ${fr.toFixed(4)}%`;
    document.getElementById('db-fr').className='ok';
  }catch{
    document.getElementById('fr-bin').textContent='—';
    document.getElementById('fr-sig').textContent='Proxy offline';
    document.getElementById('db-fr').textContent='ERRO';
    document.getElementById('db-fr').className='err';
  }
}

// ── TICKER TAPE ───────────────────────────────────────
function buildTape(data){
  const items=[
    {n:'PETR4',v:data.PETR4,f:'brl'},{n:'VALE3',v:data.VALE3,f:'brl'},
    {n:'IBOV',v:data.IBOV,f:'pts'},{n:'USD/BRL',v:data.USDBRL,f:'brl4'},
    {n:'BTC',v:data.BTC,f:'usd'},{n:'S&P500',v:data.SP500,f:'pts'},
    {n:'Nasdaq',v:data.NDX,f:'pts'},{n:'DXY',v:data.DXY,f:'usd2'},
    {n:'WTI',v:data.CL,f:'usd2'},{n:'Ouro',v:data.GOLD,f:'usd'},
    {n:'Prata',v:data.SILVER,f:'usd2'},{n:'Cobre',v:data.COPPER,f:'usd2'},
    {n:'VIX',v:data.VIX,f:'usd2'},
  ];
  const fp=(v,f)=>{
    if(!v||isNaN(v.p))return'—';
    if(f==='brl')return fBRL(v.p);
    if(f==='brl4')return'R$ '+Number(v.p).toFixed(4);
    if(f==='usd')return fUSD(v.p);
    if(f==='usd2')return Number(v.p).toFixed(2);
    return fPTS(v.p);
  };
  const fc=v=>{
    if(!v||!v.p||!v.v||v.p===v.v)return{t:'—',c:'flat'};
    const d=v.p-v.v,p=(d/v.v*100),s=d>=0?'+':'';
    return{t:`${s}${p.toFixed(2)}%`,c:d>=0?'up':'down'};
  };
  const html=items.map(i=>`<div class="ticker-item"><span class="ticker-name">${i.n}</span><span class="ticker-price">${fp(i.v,i.f)}</span><span class="ticker-chg ${fc(i.v).c}">${fc(i.v).t}</span></div>`).join('');
  document.getElementById('tape').innerHTML=html+html;
}

// ── UPDATE COTAÇÕES ───────────────────────────────────
function doMacro(tv){
  // S&P500
  const spP=hlXyz('SP500')||FB.SP500.p;
  const spV=hlXyzPrev('SP500')||FB.SP500.v;
  setEl('sp-p',fPTS(spP));setChg('sp-c',spP,spV,'pts');
  document.getElementById('sp-s').textContent=hlXyz('SP500')?'HL ✓':'fallback';

  // Nasdaq
  const ndxP=hlXyz('XYZ100')||FB.NDX.p;
  const ndxV=hlXyzPrev('XYZ100')||FB.NDX.v;
  setEl('ndx-p',fPTS(ndxP));setChg('ndx-c',ndxP,ndxV,'pts');
  document.getElementById('ndx-s').textContent=hlXyz('XYZ100')?'HL ✓':'fallback';

  // Dow Jones + futuros — atualizados em background via fetchFutures
  // Mostra fallback inicialmente
  if(!window._futures?.dji){setEl('dji-p',fPTS(FB.DJI.p));setChg('dji-c',FB.DJI.p,FB.DJI.v,'pts');}
  if(!window._futures?.esf){setEl('esf-p',fPTS(FB.ESFUT.p));setChg('esf-c',FB.ESFUT.p,FB.ESFUT.v,'pts');}
  if(!window._futures?.nqf){setEl('nqf-p',fPTS(FB.NQFUT.p));setChg('nqf-c',FB.NQFUT.p,FB.NQFUT.v,'pts');}

  // VIX handled by futures block

  // DXY — via proxy /futures (atualizado em background)
  // Mostra fallback até futures carregar
  const dxyEl=document.getElementById('dxy-p');
  if(dxyEl&&dxyEl.className.includes('loading')){dxyEl.textContent=FB.DXY.p.toFixed(2);}

  // USD/BRL via USAR
  const usarP=hlXyz('USAR');
  const usdD=tv['FX_IDC:USDBRL'];
  const usdP=usdD?.p||(usarP&&usarP>4&&usarP<8?usarP:null)||FB.USDBRL.p;
  const usdV=usdD?.v||FB.USDBRL.v;
  setEl('usd-p','R$ '+Number(usdP).toFixed(4));setChg('usd-c',usdP,usdV,'brl');
  document.getElementById('usd-s').textContent=usdD?'TV ✓':usarP?'HL USAR':'fallback';

  // IBOV
  const ibovD=tv['BMFBOVESPA:IBOV'];
  const ibovP=ibovD?.p||FB.IBOV.p,ibovV=ibovD?.v||FB.IBOV.v;
  setEl('ibov-p',fPTS(ibovP));setChg('ibov-c',ibovP,ibovV,'pts');
  document.getElementById('ibov-s').textContent=ibovD?'TV ✓':'fallback';
  // WIN handled by futures block

  // PETR4 e VALE3 na aba cotações
  // Calcula dias restantes para todos os vencimentos
  const calcDias=(dateStr,elId)=>{
    const v=new Date(dateStr);
    const d=Math.max(0,Math.ceil((v-new Date())/(1000*60*60*24)));
    const el=document.getElementById(elId);
    if(el)el.textContent=d;
  };
  calcDias('2026-12-18','pt-dias');
  calcDias('2027-02-19','vl-dias');
  calcDias('2026-09-14','axia3s-dias');
  calcDias('2026-09-14','axia3f-dias');

  // AXIA3 Call Spread status
  setTimeout(async()=>{
    try{
      const r=await fetch('https://trader-desk.onrender.com/indicators/AXIA3.SA');
      if(r.ok){
        const d=await r.json();
        if(d.price){
          const p=d.price, cs=50.50, ps=60.00;
          setEl('axia3s-pos-p',fBRL(p));
          const cdEl=document.getElementById('axia3s-call-dist');
          const pdEl=document.getElementById('axia3s-put-dist');
          const stEl=document.getElementById('axia3s-status');
          if(cdEl)cdEl.textContent=p>cs?`+${((p-cs)/cs*100).toFixed(1)}% acima da call`:`${((cs-p)/p*100).toFixed(1)}% para a call`;
          if(pdEl)pdEl.textContent=p<ps?`${((ps-p)/p*100).toFixed(1)}% para a put`:`+${((p-ps)/ps*100).toFixed(1)}% acima da put ⚠`;
          if(stEl){
            if(p>=ps){stEl.textContent='⚠ Acima de R$60 — put exercida (vende a R$60)';stEl.className='sb-val warn';}
            else if(p>=cs&&p<ps){stEl.textContent='✅ No range — prêmio garantido dos dois lados';stEl.className='sb-val ok';}
            else{stEl.textContent='⚠ Abaixo de R$50,50 — call exercida (entrega ações)';stEl.className='sb-val warn';}
          }
        }
      }
    }catch(e){}
  },2000);

  // AXIA3 Fence posição
  setTimeout(async()=>{
    try{
      const r=await fetch('https://trader-desk.onrender.com/indicators/AXIA3.SA');
      if(r.ok){
        const d=await r.json();
        if(d.price){
          setEl('axia3-pos-p',fBRL(d.price));
          const entry=54.31,kdo=43.39,kuo=68.48,p=d.price;
          const kdoDist=document.getElementById('axia3-kdo-dist');
          const kuoDist=document.getElementById('axia3-kuo-dist');
          const axSt=document.getElementById('axia3-status');
          if(kdoDist)kdoDist.textContent=`${((p-kdo)/p*100).toFixed(1)}% acima do KDO`;
          if(kuoDist)kuoDist.textContent=`${((kuo-p)/p*100).toFixed(1)}% para o KUO`;
          if(axSt){
            if(p<=kdo){axSt.textContent='🔴 KDO ATINGIDO';axSt.className='sb-val itm';}
            else if(p>=kuo){axSt.textContent='⚠ KUO ATINGIDO — retorno 4%';axSt.className='sb-val warn';}
            else{axSt.textContent='✅ Dentro do range — até +26%';axSt.className='sb-val ok';}
          }
        }
      }
    }catch(e){}
  },2000);

  // ROXO34 posição
  setTimeout(async()=>{
    try{
      const r=await fetch('https://trader-desk.onrender.com/indicators/ROXO34.SA');
      if(r.ok){
        const d=await r.json();
        if(d.price){
          setEl('roxo34-pos-p',fBRL(d.price));
          const kdo=9.60,p=d.price;
          const venc=new Date('2026-07-01');
          const dias=Math.max(0,Math.ceil((venc-new Date())/(1000*60*60*24)));
          const diasEl=document.getElementById('roxo34-dias');
          if(diasEl)diasEl.textContent=dias+' dias';
          const distEl=document.getElementById('roxo34-kdo-dist');
          if(distEl)distEl.textContent=`${((p-kdo)/p*100).toFixed(1)}% acima da barreira`;
          const stEl=document.getElementById('roxo34-status');
          if(stEl){
            if(p<=kdo){stEl.textContent='🔴 BARREIRA ATINGIDA';stEl.className='sb-val itm';}
            else{stEl.textContent='✅ No range — retorno 7,1% projetado';stEl.className='sb-val ok';}
          }
        }
      }
    }catch(e){}
  },2500);

  const ptD=tv['BMFBOVESPA:PETR4'];
  const ptP=ptD?.p||FB.PETR4.p,ptV=ptD?.v||FB.PETR4.v;
  setEl('petr4q-p',fBRL(ptP));setChg('petr4q-c',ptP,ptV,'brl');

  const vlD=tv['BMFBOVESPA:VALE3'];
  const vlP=vlD?.p||FB.VALE3.p,vlV=vlD?.v||FB.VALE3.v;
  setEl('vale3q-p',fBRL(vlP));setChg('vale3q-c',vlP,vlV,'brl');

  const bbD=tv['BMFBOVESPA:BBAS3'];
  const bbP=bbD?.p||FB.BBAS3.p,bbV=bbD?.v||FB.BBAS3.v;
  setEl('bbas3q-p',fBRL(bbP));setChg('bbas3q-c',bbP,bbV,'brl');

  // Top 10 — atualiza todos
  ['ITUB4','BBDC4','ABEV3','WEGE3','RDOR3'].forEach(t=>{
    const d=tv['BMFBOVESPA:'+t];
    if(d&&d.p){
      const pid=t.toLowerCase()+'q-p';
      const cid=t.toLowerCase()+'q-c';
      const el=document.getElementById(pid);
      if(el){el.textContent=fBRL(d.p);el.classList.remove('loading');}
      setChg(cid,d.p,d.v,'brl');
    }
  });

  return{usdP,usdV,ibovP,ibovV,ptP,ptV,vlP,vlV};
}

function doCommodities(){
  // Usa preço anterior da HL para variação correta
  const clP=hlXyz('CL')||hlXyz('BRENTOIL')||FB.CL.p;
  const clV=hlXyzPrev('CL')||hlXyzPrev('BRENTOIL')||FB.CL.v;
  setEl('cl-p',fUSD2(clP));setChg('cl-c',clP,clV==='0'?clP:clV,'usd');

  const goldP=hlXyz('GOLD')||FB.GOLD.p;
  const goldV=hlXyzPrev('GOLD')||FB.GOLD.v;
  setEl('gold-p',fUSD(goldP));setChg('gold-c2',goldP,goldV||goldP,'usd');

  const silverP=hlXyz('SILVER')||FB.SILVER.p;
  const silverV=hlXyzPrev('SILVER')||FB.SILVER.v;
  setEl('silver-p',fUSD2(silverP));setChg('silver-c',silverP,silverV||silverP,'usd');

  const copperP=hlXyz('COPPER')||FB.COPPER.p;
  const copperV=hlXyzPrev('COPPER')||FB.COPPER.v;
  setEl('copper-p',fUSD2(copperP));setChg('copper-c',copperP,copperV||copperP,'usd');

  return{clP,clV,goldP,goldV,silverP,silverV,copperP,copperV};
}

function doBTC(){
  const btcP=hlCrypto('BTC')||FB.BTC.p;
  const btcV=hlCryptoPrev('BTC')||FB.BTC.v;

  // Aba cotações
  setEl('btc-p',fUSD(btcP));setChg('btc-c',btcP,btcV||btcP,'usd');

  // Aba posições
  setEl('btc-pos-p',fUSD(btcP));setChg('btc-pos-c',btcP,btcV||btcP,'usd');

  // RSI aproximado
  const rsi=Math.min(78,Math.max(22,22+((btcP-48000)/(105000-48000))*56));
  const rsiStr='~'+Math.round(rsi);

  // Cotações
  document.getElementById('rsi-n').style.left=rsi+'%';
  document.getElementById('rsi-val').textContent=rsiStr;
  document.getElementById('btc-rsi').textContent=rsiStr;

  // Posições
  document.getElementById('btc-pos-rsi-n').style.left=rsi+'%';
  document.getElementById('btc-pos-rsi-val').textContent=rsiStr;
  document.getElementById('btc-pos-rsi').textContent=rsiStr;

  // Tendência
  const trend=btcP>84000?'ALTA':btcP>70000?'NEUTRO':'BAIXA';
  const tClass='ind-val '+(btcP>84000?'up':btcP>70000?'warn':'down');
  document.getElementById('btc-trend').textContent=trend;
  document.getElementById('btc-trend').className=tClass;
  document.getElementById('btc-pos-trend').textContent=trend;
  document.getElementById('btc-pos-trend').className=tClass;

  // VIX cripto (aproximado pelo VIX normal)
  const vixP=hlXyz('VIX')||FB.VIX.p;
  document.getElementById('btc-vix').textContent=Number(vixP).toFixed(1);

  // Signal RSI
  const sigTxt=btcP<62510?
    `⚠ <strong style="color:var(--warn)">Abaixo de US$ 62.510!</strong> Checar RSI semanal — divergência = <strong style="color:var(--accent)">SINAL DE FUNDO</strong>.`:
    btcP<70000?`Zona de atenção. Aguardar RSI &lt; 30 + divergência no semanal.`:
    `Acima dos suportes. Monitorar recuo para <strong style="color:var(--warn)">US$ 62k–58k</strong>.`;
  document.getElementById('btc-sig').innerHTML=sigTxt;
  document.getElementById('btc-pos-sig').innerHTML=sigTxt;

  // Update BTC price in indicators tab too
  setEl('btc-ind-price',fUSD(btcP));setChg('btc-ind-chg',btcP,btcV||btcP,'usd');
  return{p:btcP,v:btcV||btcP};
}

function doPositions(tv,btcData){
  const ptD=tv['BMFBOVESPA:PETR4'];
  const ptP=ptD?.p||43.0,ptV=ptD?.v||43.0;
  setEl('pt-pos-p',fBRL(ptP));setChg('pt-pos-c',ptP,ptV,'brl');
  setEl('pt-itm',`+R$ ${(ptP-30.85).toFixed(2)} acima do strike`);
  const ptPct=Math.min(100,Math.max(0,((ptP-30.85)/(65-30.85))*100));
  const ptBar=document.getElementById('pt-bar');
  if(ptBar){ptBar.style.width=ptPct+'%';ptBar.className='prog-bar '+(ptP>50?'danger':ptP>40?'warn':'ok');}
  const ptGatilho=document.getElementById('pt-pct-gatilho');
  if(ptGatilho){const pct=((ptP-30.85)/30.85*100);ptGatilho.textContent=`+${pct.toFixed(1)}% acima do strike`;}

  const vlD=tv['BMFBOVESPA:VALE3'];
  const vlP=vlD?.p||78.0,vlV=vlD?.v||78.0;
  setEl('vl-pos-p',fBRL(vlP));setChg('vl-pos-c',vlP,vlV,'brl');
  setEl('vl-itm',`+R$ ${(vlP-57.40).toFixed(2)} acima do strike`);
  const vlPct=Math.min(100,Math.max(0,((vlP-57.40)/(110-57.40))*100));
  const vlBar=document.getElementById('vl-bar');
  if(vlBar){vlBar.style.width=vlPct+'%';vlBar.className='prog-bar '+(vlP>82?'danger':vlP>70?'warn':'ok');}
  const vlGatilho=document.getElementById('vl-pct-gatilho');
  if(vlGatilho){const pct=((vlP-57.40)/57.40*100);vlGatilho.textContent=`+${pct.toFixed(1)}% acima do strike`;}

  // Countdown para todos os vencimentos
  const calcDias=(dateStr,elId)=>{
    const v=new Date(dateStr);
    const d=Math.max(0,Math.ceil((v-new Date())/(1000*60*60*24)));
    const el=document.getElementById(elId);
    if(el)el.textContent=d;
  };
  calcDias('2026-12-17','pt-dias');
  calcDias('2027-02-18','vl-dias');
  calcDias('2026-09-14','axia3f-dias');
  calcDias('2026-10-02','axia3b-dias');
  calcDias('2026-07-16','roxo34-dias');

  // AXIA3 (A) status
  setTimeout(async()=>{
    try{
      const r=await fetch('https://trader-desk.onrender.com/indicators/AXIA3.SA');
      if(!r.ok)return;
      const d=await r.json();
      if(!d.price)return;
      const p=d.price;
      setEl('axia3-pos-p',fBRL(p));
      // AXIA3 A
      const kdoA=43.51,kuoA=68.76;
      const dkA=document.getElementById('axia3-kdo-dist');
      const dkuA=document.getElementById('axia3-kuo-dist');
      const stA=document.getElementById('axia3-status');
      if(dkA)dkA.textContent=`${((p-kdoA)/p*100).toFixed(1)}% acima do KDO`;
      if(dkuA)dkuA.textContent=`${((kuoA-p)/p*100).toFixed(1)}% para o KUO`;
      if(stA){
        if(p<=kdoA){stA.textContent='🔴 KDO ATINGIDO';stA.className='sb-val itm';}
        else if(p>=kuoA){stA.textContent='⚠ KUO ATINGIDO — retorno 4%';stA.className='sb-val warn';}
        else{stA.textContent='✅ No range — participação plena';stA.className='sb-val ok';}
      }
      // AXIA3 B
      setEl('axia3b-pos-p',fBRL(p));
      const kdoB=40.52,kuoB=62.81;
      const dkB=document.getElementById('axia3b-kdo-dist');
      const dkuB=document.getElementById('axia3b-kuo-dist');
      const stB=document.getElementById('axia3b-status');
      if(dkB)dkB.textContent=`${((p-kdoB)/p*100).toFixed(1)}% acima do KDO`;
      if(dkuB)dkuB.textContent=`${((kuoB-p)/p*100).toFixed(1)}% para o KUO`;
      if(stB){
        if(p<=kdoB){stB.textContent='🔴 KDO ATINGIDO';stB.className='sb-val itm';}
        else if(p>=kuoB){stB.textContent='⚠ KUO ATINGIDO — retorno 4%';stB.className='sb-val warn';}
        else{stB.textContent='✅ No range — participação plena';stB.className='sb-val ok';}
      }
    }catch(e){}
  },2000);

  // ROXO34 status
  setTimeout(async()=>{
    try{
      const r=await fetch('https://trader-desk.onrender.com/indicators/ROXO34.SA');
      if(!r.ok)return;
      const d=await r.json();
      if(!d.price)return;
      const p=d.price,kdo=10.50;
      setEl('roxo34-pos-p',fBRL(p));
      const distEl=document.getElementById('roxo34-kdo-dist');
      if(distEl)distEl.textContent=`${((p-kdo)/p*100).toFixed(1)}% acima da barreira`;
      const stEl=document.getElementById('roxo34-status');
      if(stEl){
        if(p<=kdo){stEl.textContent='🔴 BARREIRA ATINGIDA';stEl.className='sb-val itm';}
        else{stEl.textContent='✅ Acima da barreira';stEl.className='sb-val ok';}
      }
    }catch(e){}
  },2500);

  // BTC
  const btcD=btcData||{p:79000,v:79000};
  setEl('btc-pos-p',fUSD(btcD.p));setChg('btc-pos-c',btcD.p,btcD.v,'usd');
}



// ── MONTE CARLO BARREIRA (AXIA3) ─────────────────────
async function runMCSpread(ticker, callStrike, putStrike, dias, loadId, resId, rangeId, belowId, aboveId, infoId, price=null){
  try{
    const controller=new AbortController();
    const to=setTimeout(()=>controller.abort(),25000);
    const body={ticker,k_call:putStrike,k_put:callStrike,t_days:dias,n:5000};
    if(price&&price>0) body.price=price;
    const r=await fetch('https://trader-desk.onrender.com/montecarlo',{
      method:'POST',headers:{'Content-Type':'application/json'},
      signal:controller.signal,
      body:JSON.stringify(body)
    });
    clearTimeout(to);
    if(!r.ok)throw 0;
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    // prob abaixo do callStrike = prob_put_exercida
    // prob acima do putStrike = prob_call_exercida  
    // prob no range = 100 - ambos
    const below=Number(d.prob_put_exercida||0);
    const above=Number(d.prob_call_exercida||0);
    const inRange=Math.max(0,100-below-above);
    document.getElementById(loadId).style.display='none';
    document.getElementById(resId).style.display='block';
    const rEl=document.getElementById(rangeId);
    rEl.textContent=inRange.toFixed(2)+'%';
    rEl.className='ind-val '+(inRange>50?'ok':inRange>30?'warn':'down');
    document.getElementById(belowId).textContent=below.toFixed(2)+'%';
    document.getElementById(aboveId).textContent=above.toFixed(2)+'%';
    document.getElementById(infoId).textContent=
      `Preço R$ ${d.preco_atual} · Call R$ ${callStrike} · Put R$ ${putStrike} · ${d.cenarios.toLocaleString()} cenários`;
    const volEl=document.getElementById('mc-axia3s-vol');
    if(volEl)volEl.textContent=d.volatilidade_historica_pct+'%';
  }catch(e){
    const el=document.getElementById(loadId);
    if(el)el.textContent='Erro: '+(e.message||'indisponível');
  }
}

async function runMCBarrier(ticker, entry, kdo, kuo, dias, price=null, prefix='axia3'){
  try{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),25000);
    const r=await fetch('https://trader-desk.onrender.com/montecarlo/barrier',{
      method:'POST',headers:{'Content-Type':'application/json'},
      signal:controller.signal,
      body:JSON.stringify({ticker,entry,kdo,kuo,t_days:dias,n:5000,...(price&&price>0?{price}:{})})
    });
    clearTimeout(timeout);
    if(!r.ok)throw 0;
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    document.getElementById('mc-'+prefix+'-loading').style.display='none';
    document.getElementById('mc-'+prefix+'-result').style.display='block';
    document.getElementById('mc-'+prefix+'-nobr').textContent=d.prob_sem_barreira.toFixed(2)+'%';
    document.getElementById('mc-'+prefix+'-kuo').textContent=d.prob_barreira_alta.toFixed(2)+'%';
    document.getElementById('mc-'+prefix+'-kdo').textContent=d.prob_barreira_baixa.toFixed(2)+'%';
    document.getElementById('mc-'+prefix+'-info').textContent=
      `Preço R$ ${d.preco_atual} · KDO R$ ${d.kdo} · KUO R$ ${d.kuo} · ${d.cenarios.toLocaleString()} cenários`;
    const axVolEl=document.getElementById('mc-'+prefix+'-vol');
    if(axVolEl)axVolEl.textContent=d.volatilidade_historica_pct+'%';
  }catch(e){
    const el=document.getElementById('mc-axia3-loading');
    if(el)el.textContent='Erro: '+(e.message||'indisponível');
  }
}

async function runMCPrefixado(ticker, entry, kdo, dias, price=null){
  try{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),25000);
    const r=await fetch('https://trader-desk.onrender.com/montecarlo',{
      method:'POST',headers:{'Content-Type':'application/json'},
      signal:controller.signal,
      body:JSON.stringify({ticker,k_call:entry,k_put:entry,t_days:dias,knock_down:kdo,n:5000,...(price&&price>0?{price}:{})})
    });
    clearTimeout(timeout);
    if(!r.ok)throw 0;
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    document.getElementById('mc-roxo34-loading').style.display='none';
    document.getElementById('mc-roxo34-result').style.display='block';
    const sEl=document.getElementById('mc-roxo34-sucesso');
    sEl.textContent=Number(d.prob_sucesso).toFixed(2)+'%';
    sEl.className='ind-val '+(d.prob_sucesso>70?'ok':d.prob_sucesso>50?'warn':'down');
    const cEl=document.getElementById('mc-roxo34-call');
    if(cEl){cEl.textContent=Number(d.prob_call_exercida).toFixed(2)+'%';cEl.className='ind-val '+(d.prob_call_exercida<30?'ok':d.prob_call_exercida<50?'warn':'down');}
    const kEl=document.getElementById('mc-roxo34-kdo');
    if(kEl)kEl.textContent=d.prob_kdo_atingido!=null?Number(d.prob_kdo_atingido).toFixed(2)+'%':'—';
    document.getElementById('mc-roxo34-vol').textContent=d.volatilidade_historica_pct+'%';
    document.getElementById('mc-roxo34-info').textContent=
      `Preço R$ ${d.preco_atual} · Strike R$ ${d.k_call} · KDO R$ ${d.knock_down} · ${d.cenarios.toLocaleString()} cenários`;
  }catch(e){
    const el=document.getElementById('mc-roxo34-loading');
    if(el)el.textContent='Erro: '+(e.message||'indisponível');
  }
}

// ── MONTE CARLO ───────────────────────────────────────
async function runMCForAtivo(ticker, strike, dias, loadingId, resultId, strikeId, volId, infoId){
  try{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),25000);
    const r=await fetch('https://trader-desk.onrender.com/montecarlo',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      signal:controller.signal,
      body:JSON.stringify({ticker,k_call:strike,k_put:strike,t_days:dias,n:5000})
    });
    clearTimeout(timeout);
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    document.getElementById(loadingId).style.display='none';
    document.getElementById(resultId).style.display='block';
    // Call vendida ITM: prob de CAIR ao strike = prob_put_exercida
    const probCair=d.prob_put_exercida||0;
    const sEl=document.getElementById(strikeId);
    sEl.textContent=Number(probCair).toFixed(2)+'%';
    // Para call vendida: baixa prob de cair = RUIM (não recompra barato)
    // alta prob de cair = BOM (recompra no strike)
    sEl.className='ind-val '+(probCair>30?'ok':probCair>15?'warn':'down');
    document.getElementById(volId).textContent=d.volatilidade_historica_pct+'%';
    const precoAtual=d.preco_atual;
    const distancia=((precoAtual-strike)/precoAtual*100).toFixed(1);
    document.getElementById(infoId).textContent=
      `Preço R$ ${precoAtual} · Strike R$ ${strike} · Distância: -${distancia}% · ${d.cenarios.toLocaleString()} cenários · ${d.t_days} dias`;
  }catch(e){
    const el=document.getElementById(loadingId);
    if(el)el.textContent='Erro: '+(e.message||'indisponível');
  }
}
</script>
</body>
</html>
"""

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    print("="*50)
    print("  Trader Desk — Proxy v4")
    print("  http://localhost:8888")
    print("="*50)
    app.run(host='0.0.0.0',port=8888,use_reloader=False,threaded=True)
