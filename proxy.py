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
    import datetime as dt_mod
    all_events = []
    currencies_ok = {'USD','BRL','EUR','GBP','CNY','JPY','CAD','AUD'}
    flag_map = {'USD':'🇺🇸','BRL':'🇧🇷','EUR':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳','JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺'}
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
                # FF usa campo 'country' com codigo da moeda (USD, EUR, GBP, etc.)
                cur = e.get('country', e.get('currency',''))
                if not cur or cur == 'All': continue
                if cur not in currencies_ok: continue
                imp = imp_map.get(e.get('impact',''), 0)
                if imp < 2: continue
                # Parse date from ISO format: "2026-06-07T05:15:00-04:00"
                raw_date = e.get('date','')
                date_str = raw_date[:10] if raw_date else ''
                # Parse time from date field
                time_str = ''
                if 'T' in raw_date:
                    time_part = raw_date[11:16]  # HH:MM
                    try:
                        from datetime import datetime as _dt, timedelta, timezone
                        # Convert to local time (BRT = UTC-3)
                        dt = _dt.fromisoformat(raw_date)
                        dt_brt = dt.astimezone(timezone(timedelta(hours=-3)))
                        time_str = dt_brt.strftime('%H:%M')
                        date_str = dt_brt.strftime('%Y-%m-%d')
                    except:
                        time_str = time_part
                all_events.append({
                    'date':       date_str,
                    'time':       time_str,
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

# HTML EMBUTIDO — 2026-06-09 13:07
import base64 as _b64
PANEL_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjwhLS0gVHJhZGVyIERlc2sgdjEwLjAgLSAyMDI2LTA2LTA3IDEwOjQ0IC0tPgo8aHRtbCBsYW5nPSJwdC1CUiI+CjxoZWFkPgo8bWV0YSBjaGFyc2V0PSJVVEYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5UcmFkZXIgRGVzazwvdGl0bGU+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDMwMDs0MDA7NjAwOzcwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQo6cm9vdHstLWJnOiMwZDBkMGQ7LS1iZzI6IzE0MTQxNDstLWJnMzojMWExYTFhOy0tdGV4dDojZThlOGU4Oy0tbXV0ZWQ6IzY2NjstLWJvcmRlcjojMjIyOy0tYWNjZW50OiNmMGE1MDA7LS1ncmVlbjojMDBjODUzOy0tcmVkOiNmZjE3NDQ7LS13YXJuOiNmZjk4MDA7LS1kYW5nZXI6I2ZmMTc0NDstLWJsdWU6IzIxOTZmMzstLWl0bTojZmY0NDQ0fQpib2R5e2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXRleHQpO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOi43NXJlbTtwYWRkaW5nOjEycHg7bWF4LXdpZHRoOjYwMHB4O21hcmdpbjowIGF1dG99Ci50YWJze2Rpc3BsYXk6ZmxleDtnYXA6NHB4O21hcmdpbi1ib3R0b206MTJweDtvdmVyZmxvdy14OmF1dG87d2hpdGUtc3BhY2U6bm93cmFwfQoudGFie3BhZGRpbmc6NnB4IDEycHg7YmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtjdXJzb3I6cG9pbnRlcjtmb250LXNpemU6LjZyZW07bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkKTtmbGV4LXNocmluazowfQoudGFiLmFjdGl2ZXtiYWNrZ3JvdW5kOnZhcigtLWFjY2VudCk7Y29sb3I6IzAwMDtib3JkZXItY29sb3I6dmFyKC0tYWNjZW50KX0KLnRhYi1jb250ZW50e2Rpc3BsYXk6bm9uZX0udGFiLWNvbnRlbnQuYWN0aXZle2Rpc3BsYXk6YmxvY2t9Ci5zZWN7Zm9udC1zaXplOi41NXJlbTtsZXR0ZXItc3BhY2luZzouMTJlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQpO3BhZGRpbmc6OHB4IDAgNHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7bWFyZ2luLWJvdHRvbTo4cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6NnB4fQouc2VjIHNwYW57Y29sb3I6dmFyKC0tYWNjZW50KX0uc3Jje2NvbG9yOnZhcigtLWJvcmRlcik7Zm9udC1zaXplOi41cmVtfQouZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjZweDttYXJnaW4tYm90dG9tOjEycHh9Ci5jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzoxMHB4IDhweH0KLmNhcmQuZ3JlZW57Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tZ3JlZW4pfS5jYXJkLmJsdWV7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tYmx1ZSl9LmNhcmQud2Fybntib3JkZXItdG9wOjJweCBzb2xpZCB2YXIoLS13YXJuKX0uY2FyZC5yZWR7Ym9yZGVyLXRvcDoycHggc29saWQgdmFyKC0tcmVkKX0KLmMtbGFiZWx7Zm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206MnB4fQouYy1uYW1le2ZvbnQtc2l6ZTouNnJlbTtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tdGV4dCk7bWFyZ2luLWJvdHRvbTo0cHh9Ci5jLXByaWNle2ZvbnQtc2l6ZTouODVyZW07Zm9udC13ZWlnaHQ6NzAwO2NvbG9yOnZhcigtLWFjY2VudCl9Ci5jLXByaWNlLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZTouN3JlbX0KLmMtY2hhbmdle2ZvbnQtc2l6ZTouNTVyZW07bWFyZ2luLXRvcDoycHh9Ci5jaGctdXB7Y29sb3I6dmFyKC0tZ3JlZW4pfS5jaGctZG57Y29sb3I6dmFyKC0tcmVkKX0uY2hnLWZsYXR7Y29sb3I6dmFyKC0tbXV0ZWQpfQpAa2V5ZnJhbWVzIHB1bHNlezAlLDEwMCV7b3BhY2l0eToxfTUwJXtvcGFjaXR5Oi40fX0KLnBvcy1jYXJke2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Ym9yZGVyLWxlZnQ6M3B4IHNvbGlkIHZhcigtLWFjY2VudCk7cGFkZGluZzoxMnB4O21hcmdpbi1ib3R0b206OHB4fQoucG9zLWxhYmVse2ZvbnQtc2l6ZTouNTJyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO2xldHRlci1zcGFjaW5nOi4wNmVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjRweH0KLnBvcy10aWNrZXJ7Zm9udC1zaXplOjEuMXJlbTtmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0tYWNjZW50KTttYXJnaW4tYm90dG9tOjJweH0KLnBvcy1wcmljZXtmb250LXNpemU6MS4zcmVtO2ZvbnQtd2VpZ2h0OjcwMDtjb2xvcjp2YXIoLS10ZXh0KX0ucG9zLXByaWNlLmxvYWRpbmd7Y29sb3I6dmFyKC0tbXV0ZWQpO2FuaW1hdGlvbjpwdWxzZSAxLjVzIGluZmluaXRlO2ZvbnQtc2l6ZTouOXJlbX0KLnBvcy1jaGd7Zm9udC1zaXplOi42NXJlbTttYXJnaW4tYm90dG9tOjhweH0KLnNie2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZy10b3A6OHB4O21hcmdpbi10b3A6OHB4fQouc2Itcm93e2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjtwYWRkaW5nOjNweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOi42cmVtfQouc2ItbGJse2NvbG9yOnZhcigtLW11dGVkKX0uc2ItdmFse2NvbG9yOnZhcigtLXRleHQpO3RleHQtYWxpZ246cmlnaHQ7bWF4LXdpZHRoOjYwJX0KLnNiLXZhbC5va3tjb2xvcjp2YXIoLS1ncmVlbil9LnNiLXZhbC53YXJue2NvbG9yOnZhcigtLXdhcm4pfS5zYi12YWwuaXRte2NvbG9yOnZhcigtLWl0bSl9Ci5zaWduYWx7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweDttYXJnaW4tdG9wOjhweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLnNpZy10aXRsZXtmb250LXNpemU6LjU1cmVtO2xldHRlci1zcGFjaW5nOi4wOGVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjZweDtjb2xvcjp2YXIoLS1tdXRlZCl9Ci5pbmQtYm94e2JhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo4cHg7dGV4dC1hbGlnbjpjZW50ZXJ9Ci5pbmQtbGJse2ZvbnQtc2l6ZTouNXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo0cHh9Ci5pbmQtdmFse2ZvbnQtc2l6ZToxcmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjp2YXIoLS10ZXh0KX0KLmluZC12YWwub2t7Y29sb3I6dmFyKC0tZ3JlZW4pfS5pbmQtdmFsLndhcm57Y29sb3I6dmFyKC0td2Fybil9LmluZC12YWwuZG93bntjb2xvcjp2YXIoLS1yZWQpfQouc2VjdG9yLWhlYWRlcntiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6OHB4IDE0cHg7Y3Vyc29yOnBvaW50ZXI7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjtmb250LXNpemU6LjY1cmVtO2xldHRlci1zcGFjaW5nOi4wOGVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo2cHh9Ci5zZWN0b3ItaGVhZGVyOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS1hY2NlbnQpO2NvbG9yOnZhcigtLXRleHQpfQouc2VjdG9yLWJvZHl7ZGlzcGxheTpub25lO3BhZGRpbmctdG9wOjRweH0KZm9vdGVye21hcmdpbi10b3A6MTZweDtwYWRkaW5nLXRvcDoxMnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2ZvbnQtc2l6ZTouNTJyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO2ZsZXgtd3JhcDp3cmFwO2dhcDo2cHh9Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+CjxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxMnB4Ij4KICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjlyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOnZhcigtLWFjY2VudCkiPlRSQURFUiBERVNLPC9kaXY+CiAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCkiIGlkPSJsYXN0LXVwZGF0ZSI+4oCUPC9kaXY+CjwvZGl2Pgo8ZGl2IGNsYXNzPSJ0YWJzIj4KICA8ZGl2IGNsYXNzPSJ0YWIgYWN0aXZlIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ2NvdGFjb2VzJyx0aGlzKSI+8J+TiiBDb3Rhw6fDtWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0idGFiIiBvbmNsaWNrPSJzd2l0Y2hUYWIoJ2luZGljYWRvcmVzJyx0aGlzKSI+8J+TiCBJbmRpY2Fkb3JlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3dpdGNoVGFiKCdwb3NpY29lcycsdGhpcykiPvCfkrwgUG9zacOnw7VlczwvZGl2PgogIDxkaXYgY2xhc3M9InRhYiIgb25jbGljaz0ic3dpdGNoVGFiKCdjYWxlbmRhcmlvJyx0aGlzKSI+8J+ThSBDYWxlbmTDoXJpbzwvZGl2Pgo8L2Rpdj4KCjxkaXYgaWQ9InRhYi1jb3RhY29lcyIgY2xhc3M9InRhYi1jb250ZW50IGFjdGl2ZSI+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj4wMTwvc3Bhbj4gRVVBIDxzcGFuIGNsYXNzPSJzcmMiPsK3IHByb3h5PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgPGRpdiBjbGFzcz0iY2FyZCBibHVlIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5GdXR1cm88L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkVTMSo8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJlc2YtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJlc2YtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZ1dHVybzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+TlE8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJucWYtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJucWYtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPsONbmRpY2U8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkRKSTwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImRqaS1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9ImRqaS1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgcmVkIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5Wb2xhdGlsaWRhZGU8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlZJWDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InZpeC1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9InZpeC1jIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgYmx1ZSI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+RMOzbGFyPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5EWFk8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJkeHktcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJkeHktYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5Dw6JtYmlvPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5VU0QvQlJMPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0idXNkLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0idXNkLWMiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+MDI8L3NwYW4+IEIzIOKAlCBUb3AgMTAgPHNwYW4gY2xhc3M9InNyYyI+wrcgVHJhZGluZ1ZpZXc8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj7DjW5kaWNlPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5JQk9WPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iaWJvdi1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJjLWNoYW5nZSIgaWQ9Imlib3YtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGdyZWVuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5GdXR1cm88L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPldJTjEhPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0id2luLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0id2luLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlBFVFI0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0icGV0cjRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0icGV0cjRxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPklUVUI0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iaXR1YjRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iaXR1YjRxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlZBTEUzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0idmFsZTNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0idmFsZTNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJCREM0PC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYmJkYzRxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iYmJkYzRxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkFCRVYzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYWJldjNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iYWJldjNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJCQVMzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYmJhczNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iYmJhczNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBncmVlbiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+QjM8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPldFR0UzPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0id2VnZTNxLXAiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0id2VnZTNxLWMiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCB3YXJuIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5CRFI8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlJPWE8zNDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InJveG8zNHEtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJyb3hvMzRxLWMiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+8J+Tgjwvc3Bhbj4gQjMgcG9yIFNlZ21lbnRvIDxzcGFuIGNsYXNzPSJzcmMiPsK3IGNsaXF1ZSBwYXJhIGV4cGFuZGlyPC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnZmluYW5jZWlybycpIj48c3Bhbj7wn4+mIEZpbmFuY2Vpcm88L3NwYW4+PHNwYW4gaWQ9InNhcnItZmluYW5jZWlybyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktZmluYW5jZWlybyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWZpbmFuY2Vpcm8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygncGV0cm9sZW8nKSI+PHNwYW4+8J+boiBQZXRyw7NsZW8gJmFtcDsgR8Ohczwvc3Bhbj48c3BhbiBpZD0ic2Fyci1wZXRyb2xlbyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktcGV0cm9sZW8iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1wZXRyb2xlbyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdtaW5lcmFjYW8nKSI+PHNwYW4+4puPIE1pbmVyYcOnw6NvPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1pbmVyYWNhbyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktbWluZXJhY2FvIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbWluZXJhY2FvIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ21hdGVyaWFpcycpIj48c3Bhbj7wn4yyIFBhcGVsICZhbXA7IENlbHVsb3NlPC9zcGFuPjxzcGFuIGlkPSJzYXJyLW1hdGVyaWFpcyI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktbWF0ZXJpYWlzIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbWF0ZXJpYWlzIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3V0aWxpZGFkZScpIj48c3Bhbj7imqEgVXRpbGlkYWRlIFDDumJsaWNhPC9zcGFuPjxzcGFuIGlkPSJzYXJyLXV0aWxpZGFkZSI+4pa8PC9zcGFuPjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1ib2R5IiBpZD0ic2JvZHktdXRpbGlkYWRlIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtdXRpbGlkYWRlIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ2NvbnN1bW9fY2ljbGljbycpIj48c3Bhbj7wn5uNIENvbnN1bW8gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9InNhcnItY29uc3Vtb19jaWNsaWNvIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1jb25zdW1vX2NpY2xpY28iPjxkaXYgY2xhc3M9ImdyaWQiIGlkPSJzZ3JpZC1jb25zdW1vX2NpY2xpY28iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnY29uc3Vtb19uYW8nKSI+PHNwYW4+8J+bkiBDb25zdW1vIE7Do28gQ8OtY2xpY288L3NwYW4+PHNwYW4gaWQ9InNhcnItY29uc3Vtb19uYW8iPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWNvbnN1bW9fbmFvIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtY29uc3Vtb19uYW8iPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnc2F1ZGUnKSI+PHNwYW4+8J+PpSBTYcO6ZGU8L3NwYW4+PHNwYW4gaWQ9InNhcnItc2F1ZGUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LXNhdWRlIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtc2F1ZGUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnaW5kdXN0cmlhaXMnKSI+PHNwYW4+8J+PlyBCZW5zIEluZHVzdHJpYWlzPC9zcGFuPjxzcGFuIGlkPSJzYXJyLWluZHVzdHJpYWlzIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1pbmR1c3RyaWFpcyI+PGRpdiBjbGFzcz0iZ3JpZCIgaWQ9InNncmlkLWluZHVzdHJpYWlzIj48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItaGVhZGVyIiBvbmNsaWNrPSJ0b2dnbGVTZWcoJ3RpX3RlbGVjb20nKSI+PHNwYW4+8J+SuyBUSSAmYW1wOyBDb211bmljYcOnw7Vlczwvc3Bhbj48c3BhbiBpZD0ic2Fyci10aV90ZWxlY29tIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS10aV90ZWxlY29tIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtdGlfdGVsZWNvbSI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn4e68J+HuDwvc3Bhbj4gRVVBIHBvciBTZWdtZW50bzwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnbWFnNycpIj48c3Bhbj7irZAgNyBNYWduw61maWNhczwvc3Bhbj48c3BhbiBpZD0ic2Fyci1tYWc3Ij7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1tYWc3Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbWFnNyI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCduYXNkYXExNScpIj48c3Bhbj7wn5K7IE5hc2RhcSBUb3AgMTU8L3NwYW4+PHNwYW4gaWQ9InNhcnItbmFzZGFxMTUiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LW5hc2RhcTE1Ij48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtbmFzZGFxMTUiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlY3Rvci1oZWFkZXIiIG9uY2xpY2s9InRvZ2dsZVNlZygnc3AyMCcpIj48c3Bhbj7wn5OKIFMmYW1wO1AgNTAwIFRvcCAyMDwvc3Bhbj48c3BhbiBpZD0ic2Fyci1zcDIwIj7ilrw8L3NwYW4+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWJvZHkiIGlkPSJzYm9keS1zcDIwIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtc3AyMCI+PC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjdG9yLWhlYWRlciIgb25jbGljaz0idG9nZ2xlU2VnKCdkamkyMCcpIj48c3Bhbj7wn4+bIERvdyBKb25lcyBUb3AgMjA8L3NwYW4+PHNwYW4gaWQ9InNhcnItZGppMjAiPuKWvDwvc3Bhbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWN0b3ItYm9keSIgaWQ9InNib2R5LWRqaTIwIj48ZGl2IGNsYXNzPSJncmlkIiBpZD0ic2dyaWQtZGppMjAiPjwvZGl2PjwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+PHNwYW4+MDM8L3NwYW4+IENvbW1vZGl0aWVzPC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHdhcm4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlBldHLDs2xlbzwvZGl2PjxkaXYgY2xhc3M9ImMtbmFtZSI+V1RJL0NMPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iY2wtcCI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIHdhcm4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPk1ldGFsPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5HT0xEPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iZ29sZC1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPlNJTFZFUjwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InNpbHZlci1wIj7igJQ8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQgd2FybiI+PGRpdiBjbGFzcz0iYy1sYWJlbCI+TWV0YWw8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkNPUFBFUjwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImNvcHBlci1wIj7igJQ8L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJzZWMiPjxzcGFuPjA0PC9zcGFuPiBCaXRjb2luPC9kaXY+CiAgPGRpdiBjbGFzcz0iZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlNwb3Q8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJUQy9VU0Q8L2Rpdj48ZGl2IGNsYXNzPSJjLXByaWNlIGxvYWRpbmciIGlkPSJidGMtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJidGMtYyI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5CVEMgUlNJPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYnRjLXJzaSI+4oCUPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkZ1bmRpbmc8L2Rpdj48ZGl2IGNsYXNzPSJjLW5hbWUiPkJUQyBSYXRlPC9kaXY+PGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYnRjLWZ1bmQiPuKAlDwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iY2FyZCBibHVlIj48ZGl2IGNsYXNzPSJjLWxhYmVsIj5GZWFyICZhbXA7IEdyZWVkPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj5JbmRleDwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9ImZnLXZhbCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJmZy1sYmwiPuKAlDwvZGl2PjwvZGl2PgogIDwvZGl2PgogIDxmb290ZXI+PHNwYW4gaWQ9ImZvb3Rlci10aW1lIj7igJQ8L3NwYW4+PHNwYW4+VHJhZGVyIERlc2sgdjEwLjA8L3NwYW4+PC9mb290ZXI+CjwvZGl2PgoKPGRpdiBpZD0idGFiLWluZGljYWRvcmVzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+8J+Tijwvc3Bhbj4gQ2ljbG8gQml0Y29pbjwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1jeWNsZS1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8uLi48L2Rpdj48L2Rpdj4KICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciBhdXRvO2dhcDoxMHB4O21hcmdpbjoxMnB4IDA7YWxpZ24taXRlbXM6c3RhcnQiPgogICAgPGRpdiBpZD0iZmVhci1ncmVlZC1hcmVhIj48ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbTtwYWRkaW5nOjEwcHgiPkNhcnJlZ2FuZG8gRmVhciAmYW1wOyBHcmVlZC4uLjwvZGl2PjwvZGl2PgogICAgPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHg7bWluLXdpZHRoOjEyMHB4O3RleHQtYWxpZ246Y2VudGVyIj4KICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbTo2cHgiPkJUQy9VU0Q8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iYy1wcmljZSBsb2FkaW5nIiBpZD0iYnRjLWluZC1wcmljZSI+4oCUPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImMtY2hhbmdlIiBpZD0iYnRjLWluZC1jaGciPuKAlDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIj48c3Bhbj7wn5OKPC9zcGFuPiBJbmRpY2Fkb3JlcyBCVEMgU2VtYW5hbDwvZGl2PgogIDxkaXYgaWQ9ImJ0Yy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBQRVRSNCA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3BldHI0JykiPuKGuzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJwZXRyNC1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBWQUxFMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ3ZhbGUzJykiPuKGuzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJ2YWxlMy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBCQkFTMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ2JiYXMzJykiPuKGuzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJiYmFzMy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBBWElBMyA8c3BhbiBzdHlsZT0iY3Vyc29yOnBvaW50ZXI7Y29sb3I6dmFyKC0tYWNjZW50KTtmb250LXNpemU6LjU1cmVtIiBvbmNsaWNrPSJyZWxvYWRJbmQoJ2F4aWEzJykiPuKGuzwvc3Bhbj48L2Rpdj4KICA8ZGl2IGlkPSJheGlhMy1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CiAgPGRpdiBjbGFzcz0ic2VjIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48c3Bhbj7wn5OKPC9zcGFuPiBST1hPMzQgPHNwYW4gc3R5bGU9ImN1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLWFjY2VudCk7Zm9udC1zaXplOi41NXJlbSIgb25jbGljaz0icmVsb2FkSW5kKCdyb3hvMzQnKSI+4oa7PC9zcGFuPjwvZGl2PgogIDxkaXYgaWQ9InJveG8zNC1pbmQtYXJlYSI+PGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5DYXJyZWdhbmRvLi4uPC9kaXY+PC9kaXY+CjwvZGl2PgoKPGRpdiBpZD0idGFiLXBvc2ljb2VzIiBjbGFzcz0idGFiLWNvbnRlbnQiPgogIDxkaXYgY2xhc3M9InNlYyI+PHNwYW4+MDE8L3NwYW4+IE9wZXJhw6fDtWVzIEF0aXZhczwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIj4KICAgIDxkaXYgY2xhc3M9InBvcy1sYWJlbCI+UGV0cm9icmFzIFBOIMK3IENhbGwgVmVuZGlkYSDCtyBQRVRSTDMxOSDCtyBWZW5jIDE3LzEyLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPlBFVFI0PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHJpY2UgbG9hZGluZyIgaWQ9InB0LXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0icHQtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDMwLDg1PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDMwLDg1IChQRVRSTDMxOSk8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gYW8gc3RyaWtlPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgaXRtIiBpZD0icHQtaXRtIj7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNy8xMi8yMDI2IMK3IDxzcGFuIGlkPSJwdC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjQzLDQlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DICh2b2wuaGlzdC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiIgaWQ9Im1jLXB0LXJlYWx0aW1lIj44LDMlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIEImUyAodm9sLmltcGwuKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjksNCU8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWlyIGFvIHN0cmlrZTwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1wdC1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW0iPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcHQtcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Qcm9iLiBjYWlyPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLXB0LXN0cmlrZSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtcHQtdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjRweCIgaWQ9Im1jLXB0LWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ibWFyZ2luLXRvcDoxMHB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy1sYWJlbCI+VmFsZSBPTiDCtyBDYWxsIFZlbmRpZGEgwrcgVkFMRUI1NzQgwrcgVmVuYyAxOC8wMi8yMDI3PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIj5WQUxFMzwvZGl2PgogICAgPGRpdiBjbGFzcz0icG9zLXByaWNlIGxvYWRpbmciIGlkPSJ2bC1wb3MtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icG9zLWNoZyIgaWQ9InZsLXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gUmVmLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCA1Nyw0MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TdHJpa2U8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA1Nyw0MCAoVkFMRUI1NzQpPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIGFvIHN0cmlrZTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIGl0bSIgaWQ9InZsLWl0bSI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZlbmNpbWVudG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MTgvMDIvMjAyNyDCtyA8c3BhbiBpZD0idmwtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZvbC4gSW1wbC48L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj43MSwyJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Qcm9iLiBNQyAodm9sLmhpc3QuKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iIGlkPSJtYy12bC1yZWFsdGltZSI+MTEsNSU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJvYi4gQiZTICh2b2wuaW1wbC4pPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+MTQsMiU8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBQcm9iLiBjYWlyIGFvIHN0cmlrZTwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy12bC1sb2FkaW5nIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO2ZvbnQtc2l6ZTouNjVyZW0iPkNhbGN1bGFuZG8uLi48L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtdmwtcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Qcm9iLiBjYWlyPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLXZsLXN0cmlrZSI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtdmwtdm9sIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjRweCIgaWQ9Im1jLXZsLWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ibWFyZ2luLXRvcDoxMHB4Ij4KICAgIDxkaXYgY2xhc3M9InBvcy1sYWJlbCI+QVhJQTMgKEEpIMK3IEJpZGlyZWNpb25hbCDCtyBWZW5jIDE0LzA5LzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPkFYSUEzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHJpY2UgbG9hZGluZyIgaWQ9ImF4aWEzLXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0iYXhpYTMtcG9zLWMiPuKAlDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByZcOnbyBSZWYuPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDU0LDMxPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktETyAoLTIwJSk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA0Myw1MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5LVU8gKCsyNiw2JSk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA2OCw3Njwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBzLyBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+R2FuaG8gYy8gYmFyLiBhbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+KzQlIGZpeG88L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+VmVuY2ltZW50bzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj4xNC8wOS8yMDI2IMK3IDxzcGFuIGlkPSJheGlhM2YtZGlhcyI+4oCUPC9zcGFuPiBkaWFzPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlZvbC4gSW1wbC48L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj4zNSwwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5Qcm9iLiBNQy9CJlM8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+NjgsNSUgLyA3MywwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5EaXN0LiBLRE88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzLWtkby1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhMy1rdW8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9ImF4aWEzLXN0YXR1cyI+4oCUPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaWduYWwiIHN0eWxlPSJib3JkZXItY29sb3I6dmFyKC0tYmx1ZSkiPgogICAgICA8ZGl2IGNsYXNzPSJzaWctdGl0bGUiIHN0eWxlPSJjb2xvcjp2YXIoLS1ibHVlKSI+8J+OsiBNb250ZSBDYXJsbyDigJQgQ2Vuw6FyaW9zPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im1jLWF4aWEzLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbSI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhMy1yZXN1bHQiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi10b3A6NnB4Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlNlbSBCYXJyZWlyYSDinIU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIG9rIiBpZD0ibWMtYXhpYTMtbm9iciI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5CYXIuIEFsdGEgS1VPPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTMta3VvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBkb3duIiBpZD0ibWMtYXhpYTMta2RvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlZvbC4gSGlzdC48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhMy12b2wiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NHB4IiBpZD0ibWMtYXhpYTMtaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxhYmVsIj5BWElBMyAoQikgwrcgQmlkaXJlY2lvbmFsIElPTiBJdGHDuiDCtyBWZW5jIDAyLzEwLzIwMjY8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy10aWNrZXIiPkFYSUEzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtcHJpY2UgbG9hZGluZyIgaWQ9ImF4aWEzYi1wb3MtcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0icG9zLWNoZyIgaWQ9ImF4aWEzYi1wb3MtYyI+4oCUPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzYiI+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UHJlw6dvIFJlZi48L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTAsNjU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+S0RPICgtMjAlKTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPlIkIDQwLDUyPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPktVTyAoKzI0JSk8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCA2Miw4MTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5HYW5obyBzLyBiYXJyZWlyYTwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj5hdMOpICszMSwyJSAvICsyMCU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+R2FuaG8gYy8gYmFyLiBhbHRhPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgd2FybiI+KzQlIGZpeG8gKDEyLDMzJSBhLmEuKTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjAyLzEwLzIwMjYgwrcgPHNwYW4gaWQ9ImF4aWEzYi1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjM1LDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DL0ImUzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIG9rIj42OCw1JSAvIDczLDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkRpc3QuIEtETzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIiBpZD0iYXhpYTNiLWtkby1kaXN0Ij7igJQ8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gS1VPPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhM2Ita3VvLWRpc3QiPuKAlDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TaXR1YcOnw6NvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiIGlkPSJheGlhM2Itc3RhdHVzIj7igJQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpZ25hbCIgc3R5bGU9ImJvcmRlci1jb2xvcjp2YXIoLS1ibHVlKSI+CiAgICAgIDxkaXYgY2xhc3M9InNpZy10aXRsZSIgc3R5bGU9ImNvbG9yOnZhcigtLWJsdWUpIj7wn46yIE1vbnRlIENhcmxvIOKAlCBDZW7DoXJpb3M8L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtYXhpYTNiLWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbSI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1heGlhM2ItcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5TZW0gQmFycmVpcmEg4pyFPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLWF4aWEzYi1ub2JyIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQWx0YSBLVU88L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iIGlkPSJtYy1heGlhM2Ita3VvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkJhci4gQmFpeGEgS0RPPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBkb3duIiBpZD0ibWMtYXhpYTNiLWtkbyI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Wb2wuIEhpc3QuPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIiBpZD0ibWMtYXhpYTNiLXZvbCI+4oCUPC9kaXY+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLXRvcDo0cHgiIGlkPSJtYy1heGlhM2ItaW5mbyI+4oCUPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0icG9zLWNhcmQiIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPgogICAgPGRpdiBjbGFzcz0icG9zLWxhYmVsIj5ST1hPMzQgwrcgQkRSIE51YmFuayDCtyBQcmVmaXhhZG8gYy8gQmFycmVpcmEgwrcgVmVuYyAxNi8wNy8yMDI2PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIj5ST1hPMzQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBvcy1wcmljZSBsb2FkaW5nIiBpZD0icm94bzM0LXBvcy1wIj7igJQ8L2Rpdj48ZGl2IGNsYXNzPSJwb3MtY2hnIiBpZD0icm94bzM0LXBvcy1jIj7igJQ8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5QcmXDp28gUmVmLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIj5SJCAxMiw4ODwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5TdHJpa2UgUk9YT0cxMDU8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCB3YXJuIj5SJCAxMCw1MDwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5WZW5jaW1lbnRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPjE2LzA3LzIwMjYgwrcgPHNwYW4gaWQ9InJveG8zNC1kaWFzIj7igJQ8L3NwYW4+IGRpYXM8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+Vm9sLiBJbXBsLjwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjM5LDAlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlByb2IuIE1DL0ImUzwvc3Bhbj48c3BhbiBjbGFzcz0ic2ItdmFsIHdhcm4iPjQzLDIlIC8gNDcsMSU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+RGlzdC4gYmFycmVpcmE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9InJveG8zNC1rZG8tZGlzdCI+4oCUPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlNpdHVhw6fDo288L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCIgaWQ9InJveG8zNC1zdGF0dXMiPuKAlDwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2lnbmFsIiBzdHlsZT0iYm9yZGVyLWNvbG9yOnZhcigtLWJsdWUpIj4KICAgICAgPGRpdiBjbGFzcz0ic2lnLXRpdGxlIiBzdHlsZT0iY29sb3I6dmFyKC0tYmx1ZSkiPvCfjrIgTW9udGUgQ2FybG8g4oCUIFByb2IuIHN1Y2Vzc288L2Rpdj4KICAgICAgPGRpdiBpZD0ibWMtcm94bzM0LWxvYWRpbmciIHN0eWxlPSJjb2xvcjp2YXIoLS1tdXRlZCk7Zm9udC1zaXplOi42NXJlbSI+Q2FsY3VsYW5kby4uLjwvZGl2PgogICAgICA8ZGl2IGlkPSJtYy1yb3hvMzQtcmVzdWx0IiBzdHlsZT0iZGlzcGxheTpub25lIj4KICAgICAgICA8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5Qcm9iLiBTdWNlc3NvPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayIgaWQ9Im1jLXJveG8zNC1zdWNlc3NvIj7igJQ8L2Rpdj48L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPkNhbGwgRXhlcmNpZGE8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIiBpZD0ibWMtcm94bzM0LWNhbGwiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+S0RPIEF0aW5naWRvPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCIgaWQ9Im1jLXJveG8zNC1rZG8iPuKAlDwvZGl2PjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+Vm9sLiBIaXN0LjwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiIgaWQ9Im1jLXJveG8zNC12b2wiPuKAlDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNTVyZW07Y29sb3I6dmFyKC0tbXV0ZWQpO21hcmdpbi10b3A6NHB4IiBpZD0ibWMtcm94bzM0LWluZm8iPuKAlDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InNlYyIgc3R5bGU9Im1hcmdpbi10b3A6MTZweCI+PHNwYW4+8J+TgTwvc3Bhbj4gRW5jZXJyYWRhczwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ib3BhY2l0eTouNjU7Ym9yZGVyLWNvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj5CQkFTMzwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPlN0cmlrZSBCQkFTSDIxPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwiPlIkIDIxLDY1IMK3IFJlZiBSJCAyMCw2Nzwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+4pyFIDgwJSBkbyBhbHZvIGVtIDcwJSBkbyBwcmF6bzwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ib3BhY2l0eTouNjU7Ym9yZGVyLWNvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj5BWElBMyBTaG9ydCBTdHJhbmdsZTwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2IiPgogICAgICA8ZGl2IGNsYXNzPSJzYi1yb3ciPjxzcGFuIGNsYXNzPSJzYi1sYmwiPkNhbGwgVi4gQVhJQUk1MDU8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+UiQgNTAsNTA8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InNiLXJvdyI+PHNwYW4gY2xhc3M9InNiLWxibCI+UmVzdWx0YWRvPC9zcGFuPjxzcGFuIGNsYXNzPSJzYi12YWwgb2siPuKchSBBw6fDtWVzIGxpYmVyYWRhczwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InBvcy1jYXJkIiBzdHlsZT0ib3BhY2l0eTouNjU7Ym9yZGVyLWNvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tdG9wOjZweCI+CiAgICA8ZGl2IGNsYXNzPSJwb3MtdGlja2VyIiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpIj5ST1hPMzQgUHJlZml4YWRvIDcsMSU8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNiIj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5FbmNlcnJhZGE8L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCI+MDQvMDYvMjAyNjwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ic2Itcm93Ij48c3BhbiBjbGFzcz0ic2ItbGJsIj5SZXN1bHRhZG88L3NwYW4+PHNwYW4gY2xhc3M9InNiLXZhbCBvayI+4pyFIH41LDE3JSAoNzIlIGRvIGFsdm8pPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CjwvZGl2PgoKPGRpdiBpZD0idGFiLWNhbGVuZGFyaW8iIGNsYXNzPSJ0YWItY29udGVudCI+CiAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjEycHgiPgogICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOi42cmVtO2NvbG9yOnZhcigtLW11dGVkKSI+8J+HuvCfh7gg8J+Hp/Cfh7cg8J+HqvCfh7og8J+HrPCfh6cg8J+HqPCfh7Mg8J+Hr/Cfh7Ug8J+HqfCfh6ogwrcgSW1wYWN0IE1lZGl1bSs8L2Rpdj4KICAgIDxidXR0b24gb25jbGljaz0ibG9hZENhbGVuZGFyKCkiIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLWJnMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1hY2NlbnQpO2NvbG9yOnZhcigtLWFjY2VudCk7cGFkZGluZzo0cHggMTBweDtmb250LXNpemU6LjZyZW07Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdCI+4oa7IEF0dWFsaXphcjwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgaWQ9ImNhbGVuZGFyLWFyZWEiPjxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlciI+Q2xpcXVlIGVtIEF0dWFsaXphcjwvZGl2PjwvZGl2Pgo8L2Rpdj4KCjxzY3JpcHQ+CmNvbnN0IEJBU0U9J2h0dHBzOi8vdHJhZGVyLWRlc2sub25yZW5kZXIuY29tJzsKY29uc3QgU0VHPXsnZmluYW5jZWlybyc6WydJVFVCNCcsJ0JCREM0JywnQkJBUzMnLCdTQU5CMTEnLCdCM1NBMycsJ0JQQUMxMScsJ0lUU0E0JywnQlJTUjYnLCdBQkNCNCcsJ0JNR0I0J10sJ3BldHJvbGVvJzpbJ1BFVFI0JywnUEVUUjMnLCdQUklPMycsJ0JSQVYzJywnVkJCUjMnLCdDU0FOMycsJ1JFQ1YzJywnVUdQQTMnLCdDR0FTMycsJ1NFUUwzJ10sJ21pbmVyYWNhbyc6WydWQUxFMycsJ0dHQlI0JywnQ1NOQTMnLCdVU0lNNScsJ0JSQVA0JywnRkVTQTQnLCdDTUlOMycsJ0NCQVYzJywnR09BVTQnLCdQR01OMyddLCdtYXRlcmlhaXMnOlsnU1VaQjMnLCdLTEJOMTEnLCdTVVpCMycsJ1VOSVA2JywnUkFOSTMnLCdPUlZSMycsJ1NNVE8zJywnRlJBUzMnLCdMUFNCMycsJ1NVWkIzJ10sJ3V0aWxpZGFkZSc6WydBWElBMycsJ0VRVEwzJywnQ1BGRTMnLCdTQlNQMycsJ0NNSUc0JywnRU5HSTExJywnVEFFRTExJywnQVVSRTMnLCdFR0lFMycsJ0NQTEUzJ10sJ2NvbnN1bW9fY2ljbGljbyc6WydSRU5UMycsJ0xSRU4zJywnTUdMVTMnLCdDWVJFMycsJ01SVkUzJywnQ0FTSDMnLCdBWlpBMycsJ1ZJVkEzJywnU0JGRzMnLCdDVkNCMyddLCdjb25zdW1vX25hbyc6WydBQkVWMycsJ0pCU1MzJywnQlJGUzMnLCdOQVRVMycsJ01ESUEzJywnQkVFRjMnLCdTTENFMycsJ01UUkUzJywnQ0FNTDMnLCdQQ0FSMyddLCdzYXVkZSc6WydSRE9SMycsJ0hBUFYzJywnRkxSWTMnLCdEQVNBMycsJ1FVQUwzJywnT05DTzMnLCdQTlZMMycsJ09EUFYzJywnTUFURDMnLCdBQUxSMyddLCdpbmR1c3RyaWFpcyc6WydXRUdFMycsJ0VNQlIzJywnUkFJTDMnLCdUR01BMycsJ1JPTUkzJywnVkxJRDMnLCdUVVBZMycsJ0lSQlIzJywnUE9NTzQnLCdSU0lEMyddLCd0aV90ZWxlY29tJzpbJ1ZJVlQzJywnVElNUzMnLCdUT1RWUzMnLCdPSUJSMycsJ0xXU0EzJywnTUxBUzMnLCdBTklNMycsJ1BPU0kzJywnSU5UQjMnLCdQT1NJMyddfTsKY29uc3QgVVNfU0VHPXsnbWFnNyc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnR09PR0wnLCdNRVRBJywnVFNMQSddLCduYXNkYXExNSc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdDT1NUJywnTkZMWCcsJ1FDT00nLCdBTUQnLCdBREJFJywnSU5UQycsJ0NTQ08nXSwnc3AyMCc6WydBQVBMJywnTVNGVCcsJ05WREEnLCdBTVpOJywnTUVUQScsJ0dPT0dMJywnVFNMQScsJ0FWR08nLCdCUksuQicsJ0pQTScsJ0xMWScsJ1YnLCdVTkgnLCdYT00nLCdNQScsJ05GTFgnLCdQRycsJ0pOSicsJ0hEJywnQkFDJ10sJ2RqaTIwJzpbJ1VOSCcsJ0dTJywnSEQnLCdTSFcnLCdDQVQnLCdBWFAnLCdNQ0QnLCdBTUdOJywnVicsJ1RSVicsJ0lCTScsJ0pQTScsJ0hPTicsJ0NSTScsJ0NWWCcsJ0FBUEwnLCdNU0ZUJywnRElTJywnTktFJywnQkEnXX07CmNvbnN0IGZCUkw9dj0+diE9bnVsbD8nUiQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ3B0LUJSJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlVTRD12PT52IT1udWxsPydVUyQgJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTon4oCUJzsKY29uc3QgZlBUUz12PT52IT1udWxsP051bWJlcih2KS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pOifigJQnOwpmdW5jdGlvbiBzZXRFbChpZCx0eHQpe2NvbnN0IGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpO2lmKCFlKXJldHVybjtlLnRleHRDb250ZW50PXR4dDtlLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9CmZ1bmN0aW9uIHNldENoZyhpZCxub3cscHJldix0eXBlKXtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZighZSlyZXR1cm47Y29uc3QgZGlmZj1ub3ctcHJldjtjb25zdCBwY3Q9KGRpZmYvTWF0aC5hYnMocHJldnx8MSkqMTAwKS50b0ZpeGVkKDIpO2NvbnN0IHNpZ249ZGlmZj49MD8nKyc6Jyc7aWYodHlwZT09PSdicmwnKWUudGV4dENvbnRlbnQ9c2lnbisnUiQgJytNYXRoLmFicyhkaWZmKS50b0ZpeGVkKDIpKycgKCcrc2lnbitwY3QrJyUpJztlbHNlIGlmKHR5cGU9PT0ndXNkJyllLnRleHRDb250ZW50PXNpZ24rZGlmZi50b0ZpeGVkKDIpKycgKCcrc2lnbitwY3QrJyUpJztlbHNlIGUudGV4dENvbnRlbnQ9c2lnbitNYXRoLmFicyhkaWZmKS50b0xvY2FsZVN0cmluZygncHQtQlInLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKycgKCcrc2lnbitwY3QrJyUpJztlLmNsYXNzTmFtZT0nYy1jaGFuZ2UgJysoZGlmZj4wPydjaGctdXAnOmRpZmY8MD8nY2hnLWRuJzonY2hnLWZsYXQnKTt9CmZ1bmN0aW9uIHN3aXRjaFRhYih0YWIsZWwpe2RvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy50YWInKS5mb3JFYWNoKHQ9PnQuY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJykpO2RvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy50YWItY29udGVudCcpLmZvckVhY2godD0+dC5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKSk7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RhYi0nK3RhYikuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7aWYoZWwpZWwuY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7aWYodGFiPT09J2luZGljYWRvcmVzJyYmIXdpbmRvdy5faW5kTG9hZGVkKXt3aW5kb3cuX2luZExvYWRlZD10cnVlO2xvYWRJbmRpY2F0b3JzKCk7fWlmKHRhYj09PSdjYWxlbmRhcmlvJylsb2FkQ2FsZW5kYXIoKTt9CmZ1bmN0aW9uIHRvZ2dsZVNlZyhpZCl7Y29uc3QgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2JvZHktJytpZCk7Y29uc3QgYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2Fyci0nK2lkKTtpZighYilyZXR1cm47Y29uc3Qgb3Blbj1iLnN0eWxlLmRpc3BsYXkhPT0nYmxvY2snO2Iuc3R5bGUuZGlzcGxheT1vcGVuPydibG9jayc6J25vbmUnO2lmKGEpYS50ZXh0Q29udGVudD1vcGVuPyfilrInOifilrwnO2lmKG9wZW4mJiFiLmRhdGFzZXQubG9hZGVkKXtiLmRhdGFzZXQubG9hZGVkPScxJztsb2FkU2VnbWVudChpZCk7fX0KYXN5bmMgZnVuY3Rpb24gbG9hZFNlZ21lbnQoaWQpe2NvbnN0IGdyaWQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NncmlkLScraWQpO2lmKCFncmlkKXJldHVybjtpZihVU19TRUdbaWRdKXtjb25zdCB0a3M9VVNfU0VHW2lkXTtncmlkLmlubmVySFRNTD10a3MubWFwKHQ9Pic8ZGl2IGNsYXNzPSJjYXJkIGJsdWUiPjxkaXYgY2xhc3M9ImMtbGFiZWwiPlVTPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InVzZy0nK3QudG9Mb3dlckNhc2UoKS5yZXBsYWNlKCctJywnXycpKyctcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJ1c2ctJyt0LnRvTG93ZXJDYXNlKCkucmVwbGFjZSgnLScsJ18nKSsnLWMiPuKAlDwvZGl2PjwvZGl2PicpLmpvaW4oJycpO3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy91cy9xdW90ZXM/dGlja2Vycz0nK3Rrcy5qb2luKCcsJykpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO09iamVjdC5lbnRyaWVzKGQpLmZvckVhY2goKFt0LHZdKT0+e2NvbnN0IHRpZD10LnRvTG93ZXJDYXNlKCkucmVwbGFjZSgnLScsJ18nKTtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndXNnLScrdGlkKyctcCcpO2lmKGVsJiZ2LnByaWNlKXtlbC50ZXh0Q29udGVudD0nJCcrTnVtYmVyKHYucHJpY2UpLnRvRml4ZWQoMik7ZWwuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO31pZih2LnByaWNlJiZ2LnByZXYpc2V0Q2hnKCd1c2ctJyt0aWQrJy1jJyx2LnByaWNlLHYucHJldiwndXNkJyk7fSk7fWNhdGNoKGUpe31yZXR1cm47fWNvbnN0IHRrcz1TRUdbaWRdO2lmKCF0a3MpcmV0dXJuO2dyaWQuaW5uZXJIVE1MPXRrcy5tYXAodD0+JzxkaXYgY2xhc3M9ImNhcmQgZ3JlZW4iPjxkaXYgY2xhc3M9ImMtbGFiZWwiPkIzPC9kaXY+PGRpdiBjbGFzcz0iYy1uYW1lIj4nK3QrJzwvZGl2PjxkaXYgY2xhc3M9ImMtcHJpY2UgbG9hZGluZyIgaWQ9InNnLScrdC50b0xvd2VyQ2FzZSgpKyctcCI+4oCUPC9kaXY+PGRpdiBjbGFzcz0iYy1jaGFuZ2UiIGlkPSJzZy0nK3QudG9Mb3dlckNhc2UoKSsnLWMiPuKAlDwvZGl2PjwvZGl2PicpLmpvaW4oJycpO3RyeXtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy90di9icmF6aWwnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2Vyczp0a3MubWFwKHQ9PidCTUZCT1ZFU1BBOicrdCl9LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7KGQuZGF0YXx8W10pLmZvckVhY2goeD0+e2NvbnN0IHQ9eC5zLnJlcGxhY2UoJ0JNRkJPVkVTUEE6JywnJykudG9Mb3dlckNhc2UoKTtjb25zdFtjLGNhXT14LmR8fFtdO2lmKGMhPW51bGwpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZy0nK3QrJy1wJyk7aWYoZWwpe2VsLnRleHRDb250ZW50PWZCUkwoYyk7ZWwuY2xhc3NMaXN0LnJlbW92ZSgnbG9hZGluZycpO31zZXRDaGcoJ3NnLScrdCsnLWMnLGMsYy0oY2F8fDApLCdicmwnKTt9fSk7fWNhdGNoKGUpe319CmFzeW5jIGZ1bmN0aW9uIGZldGNoSEwoKXt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2NvbnN0IGJwPXBhcnNlRmxvYXQoZC5CVEN8fDApO2lmKGJwPjApe3NldEVsKCdidGMtcCcsZlVTRChicCkpO3NldENoZygnYnRjLWMnLGJwLGJwKjAuOTksJ3VzZCcpO3NldEVsKCdidGMtcG9zLXAnLGZVU0QoYnApKTt9dHJ5e2NvbnN0IHIyPWF3YWl0IGZldGNoKCdodHRwczovL2FwaS5oeXBlcmxpcXVpZC54eXovaW5mbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHt0eXBlOidhbGxNaWRzJyxkZXg6J3h5eid9KX0pO2lmKHIyLm9rKXtjb25zdCBkMj1hd2FpdCByMi5qc29uKCk7aWYoZDJbJ3h5ejpDTCddKXNldEVsKCdjbC1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OkNMJ10pLnRvRml4ZWQoMikpO2lmKGQyWyd4eXo6R09MRCddKXNldEVsKCdnb2xkLXAnLCckJytOdW1iZXIoZDJbJ3h5ejpHT0xEJ10pLnRvTG9jYWxlU3RyaW5nKCdlbi1VUycse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSkpO2lmKGQyWyd4eXo6U0lMVkVSJ10pc2V0RWwoJ3NpbHZlci1wJywnJCcrcGFyc2VGbG9hdChkMlsneHl6OlNJTFZFUiddKS50b0ZpeGVkKDIpKTtpZihkMlsneHl6OkNPUFBFUiddKXNldEVsKCdjb3BwZXItcCcsJyQnK3BhcnNlRmxvYXQoZDJbJ3h5ejpDT1BQRVInXSkudG9GaXhlZCgzKSk7fX1jYXRjaChlKXt9fWNhdGNoKGUpe319CmFzeW5jIGZ1bmN0aW9uIGZldGNoVFYoKXtjb25zdCBvdXQ9e307dHJ5e2NvbnN0IHRrcz1bJ0JNRkJPVkVTUEE6UEVUUjQnLCdCTUZCT1ZFU1BBOklUVUI0JywnQk1GQk9WRVNQQTpWQUxFMycsJ0JNRkJPVkVTUEE6QkJEQzQnLCdCTUZCT1ZFU1BBOkFCRVYzJywnQk1GQk9WRVNQQTpCQkFTMycsJ0JNRkJPVkVTUEE6V0VHRTMnLCdCTUZCT1ZFU1BBOklCT1YnXTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy90di9icmF6aWwnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7c3ltYm9sczp7dGlja2Vyczp0a3N9LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSk7aWYoci5vayl7Y29uc3QgZD1hd2FpdCByLmpzb24oKTsoZC5kYXRhfHxbXSkuZm9yRWFjaCh4PT57Y29uc3RbYyxjYV09eC5kfHxbXTtpZihjIT1udWxsKW91dFt4LnNdPXtwOmMsdjpjLShjYXx8MCl9O30pO319Y2F0Y2goZSl7fXRyeXtjb25zdCBycj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy9ST1hPMzQuU0EnKTtpZihyci5vayl7Y29uc3QgZGQ9YXdhaXQgcnIuanNvbigpO2lmKGRkLnByaWNlKXtzZXRFbCgncm94bzM0cS1wJyxmQlJMKGRkLnByaWNlKSk7c2V0Q2hnKCdyb3hvMzRxLWMnLGRkLnByaWNlLGRkLnByaWNlKjAuOTksJ2JybCcpO319fWNhdGNoKGUpe31yZXR1cm4gb3V0O30KYXN5bmMgZnVuY3Rpb24gZmV0Y2hGdXR1cmVzKCl7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2Z1dHVyZXMnKTtpZighci5vaylyZXR1cm4gbnVsbDtyZXR1cm4gYXdhaXQgci5qc29uKCk7fWNhdGNoKGUpe3JldHVybiBudWxsO319CmFzeW5jIGZ1bmN0aW9uIGZldGNoRnVuZGluZygpewogIHRyeXsKICAgIC8vIFRlbnRhIEJpbmFuY2UgZGlyZXRvIHByaW1laXJvCiAgICBjb25zdCByPWF3YWl0IGZldGNoKCdodHRwczovL2ZhcGkuYmluYW5jZS5jb20vZmFwaS92MS9wcmVtaXVtSW5kZXg/c3ltYm9sPUJUQ1VTRFQnKTsKICAgIGlmKHIub2spewogICAgICBjb25zdCBkPWF3YWl0IHIuanNvbigpOwogICAgICBjb25zdCByYXRlPXBhcnNlRmxvYXQoZC5sYXN0RnVuZGluZ1JhdGV8fDApKjEwMDsKICAgICAgc2V0RWwoJ2J0Yy1mdW5kJyxyYXRlLnRvRml4ZWQoNCkrJyUnKTsKICAgICAgcmV0dXJuOwogICAgfQogIH1jYXRjaChlKXt9CiAgdHJ5ewogICAgY29uc3QgcjI9YXdhaXQgZmV0Y2goQkFTRSsnL2JpbmFuY2UvZnVuZGluZycpOwogICAgaWYoIXIyLm9rKXJldHVybjsKICAgIGNvbnN0IGQ9YXdhaXQgcjIuanNvbigpOwogICAgY29uc3QgZj1BcnJheS5pc0FycmF5KGQpP2QuZmluZCh4PT54LnN5bWJvbD09PSdCVENVU0RUJyk6bnVsbDsKICAgIGlmKGYpe3NldEVsKCdidGMtZnVuZCcsKHBhcnNlRmxvYXQoZi5mdW5kaW5nUmF0ZXx8MCkqMTAwKS50b0ZpeGVkKDQpKyclJyk7fQogIH1jYXRjaChlKXt9Cn0KZnVuY3Rpb24gZG9NYWNybyh0dixmdXR1cmVzKXtjb25zdCBpYkQ9dHZbJ0JNRkJPVkVTUEE6SUJPViddO2lmKGliRCl7c2V0RWwoJ2lib3YtcCcsZlBUUyhpYkQucCkpO3NldENoZygnaWJvdi1jJyxpYkQucCxpYkQudiwncHRzJyk7fVtbJ1BFVFI0JywncGV0cjRxJ10sWydJVFVCNCcsJ2l0dWI0cSddLFsnVkFMRTMnLCd2YWxlM3EnXSxbJ0JCREM0JywnYmJkYzRxJ10sWydBQkVWMycsJ2FiZXYzcSddLFsnQkJBUzMnLCdiYmFzM3EnXSxbJ1dFR0UzJywnd2VnZTNxJ11dLmZvckVhY2goKFt0LGlkXSk9Pntjb25zdCBkPXR2WydCTUZCT1ZFU1BBOicrdF07aWYoZCl7c2V0RWwoaWQrJy1wJyxmQlJMKGQucCkpO3NldENoZyhpZCsnLWMnLGQucCxkLnYsJ2JybCcpO319KTtmZXRjaChCQVNFKycvZnV0dXJlcycpLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZD0+e2lmKGQudXNkJiZkLnVzZC5wcmljZSl7c2V0RWwoJ3VzZC1wJyxmQlJMKGQudXNkLnByaWNlKSk7c2V0Q2hnKCd1c2QtYycsZC51c2QucHJpY2UsZC51c2QucHJldnx8ZC51c2QucHJpY2UsJ2JybCcpO31lbHNle2ZldGNoKEJBU0UrJy90di9mb3JleCcse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OkpTT04uc3RyaW5naWZ5KHtzeW1ib2xzOnt0aWNrZXJzOlsnRlg6VVNEQlJMJ119LGNvbHVtbnM6WydjbG9zZScsJ2NoYW5nZV9hYnMnXX0pfSkudGhlbihyPT5yLmpzb24oKSkudGhlbihkPT57Y29uc3QgeD1kLmRhdGE/LlswXTtpZigheClyZXR1cm47Y29uc3RbYyxjYV09eC5kfHxbXTtpZihjKXtzZXRFbCgndXNkLXAnLGZCUkwoYykpO3NldENoZygndXNkLWMnLGMsYy0oY2F8fDApLCdicmwnKTt9fSkuY2F0Y2goKCk9Pnt9KTt9fSkuY2F0Y2goKCk9Pnt9KTtpZihmdXR1cmVzKXtjb25zdCBmPWZ1dHVyZXM7Y29uc3QgYWY9KGlkLHZhbCk9Pntjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTtpZihlKXtlLnRleHRDb250ZW50PXZhbDtlLmNsYXNzTGlzdC5yZW1vdmUoJ2xvYWRpbmcnKTt9fTtpZihmLmRqaT8ucHJpY2Upe2FmKCdkamktcCcsZlBUUyhmLmRqaS5wcmljZSkpO3NldENoZygnZGppLWMnLGYuZGppLnByaWNlLGYuZGppLnByZXYsJ3B0cycpO31pZihmLmVzZj8ucHJpY2Upe2FmKCdlc2YtcCcsZlBUUyhmLmVzZi5wcmljZSkpO3NldENoZygnZXNmLWMnLGYuZXNmLnByaWNlLGYuZXNmLnByZXYsJ3B0cycpO31pZihmLm5xZj8ucHJpY2Upe2FmKCducWYtcCcsZlBUUyhmLm5xZi5wcmljZSkpO3NldENoZygnbnFmLWMnLGYubnFmLnByaWNlLGYubnFmLnByZXYsJ3B0cycpO31pZihmLndpbj8ucHJpY2Upe2FmKCd3aW4tcCcsZlBUUyhmLndpbi5wcmljZSkpO3NldENoZygnd2luLWMnLGYud2luLnByaWNlLGYud2luLnByZXYsJ3B0cycpO31pZihmLnZpeD8ucHJpY2Upe2FmKCd2aXgtcCcsTnVtYmVyKGYudml4LnByaWNlKS50b0ZpeGVkKDIpKTtzZXRDaGcoJ3ZpeC1jJyxmLnZpeC5wcmljZSxmLnZpeC5wcmV2LCd1c2QnKTt9aWYoZi5keHk/LnByaWNlKXthZignZHh5LXAnLE51bWJlcihmLmR4eS5wcmljZSkudG9GaXhlZCgyKSk7c2V0Q2hnKCdkeHktYycsZi5keHkucHJpY2UsZi5keHkucHJldiwndXNkJyk7fX19CmZ1bmN0aW9uIGRvUG9zaXRpb25zKHR2KXtjb25zdCBwdEQ9dHZbJ0JNRkJPVkVTUEE6UEVUUjQnXTtjb25zdCBwdFA9cHREPy5wfHw0MCxwdFY9cHREPy52fHw0MDtzZXRFbCgncHQtcG9zLXAnLGZCUkwocHRQKSk7c2V0Q2hnKCdwdC1wb3MtYycscHRQLHB0ViwnYnJsJyk7c2V0RWwoJ3B0LWl0bScsJytSJCAnKyhwdFAtMzAuODUpLnRvRml4ZWQoMikrJyBhY2ltYSBkbyBzdHJpa2UnKTtjb25zdCB2bEQ9dHZbJ0JNRkJPVkVTUEE6VkFMRTMnXTtjb25zdCB2bFA9dmxEPy5wfHw3OCx2bFY9dmxEPy52fHw3ODtzZXRFbCgndmwtcG9zLXAnLGZCUkwodmxQKSk7c2V0Q2hnKCd2bC1wb3MtYycsdmxQLHZsViwnYnJsJyk7c2V0RWwoJ3ZsLWl0bScsJytSJCAnKyh2bFAtNTcuNDApLnRvRml4ZWQoMikrJyBhY2ltYSBkbyBzdHJpa2UnKTtjb25zdCBjZD0oZHMsZWlkKT0+e2NvbnN0IHY9bmV3IERhdGUoZHMpO2NvbnN0IGQ9TWF0aC5tYXgoMCxNYXRoLmNlaWwoKHYtbmV3IERhdGUoKSkvODY0ZTUpKTtjb25zdCBlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVpZCk7aWYoZSllLnRleHRDb250ZW50PWQ7fTtjZCgnMjAyNi0xMi0xNycsJ3B0LWRpYXMnKTtjZCgnMjAyNy0wMi0xOCcsJ3ZsLWRpYXMnKTtjZCgnMjAyNi0wOS0xNCcsJ2F4aWEzZi1kaWFzJyk7Y2QoJzIwMjYtMTAtMDInLCdheGlhM2ItZGlhcycpO2NkKCcyMDI2LTA3LTE2Jywncm94bzM0LWRpYXMnKTtzZXRUaW1lb3V0KGFzeW5jKCk9Pnt0cnl7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvaW5kaWNhdG9ycy9BWElBMy5TQScpO2lmKCFyLm9rKXJldHVybjtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKCFkLnByaWNlKXJldHVybjtjb25zdCBwPWQucHJpY2U7c2V0RWwoJ2F4aWEzLXBvcy1wJyxmQlJMKHApKTtzZXRFbCgnYXhpYTNiLXBvcy1wJyxmQlJMKHApKTtjb25zdCBrZG9BPTQzLjUxLGt1b0E9NjguNzYsa2RvQj00MC41MixrdW9CPTYyLjgxO2NvbnN0IGRBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1rZG8tZGlzdCcpO2lmKGRBKWRBLnRleHRDb250ZW50PSgocC1rZG9BKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nO2NvbnN0IHVBPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhMy1rdW8tZGlzdCcpO2lmKHVBKXVBLnRleHRDb250ZW50PSgoa3VvQS1wKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBwYXJhIG8gS1VPJztjb25zdCBzQT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXhpYTMtc3RhdHVzJyk7aWYoc0Epe3NBLnRleHRDb250ZW50PXA8PWtkb0E/J/CflLQgS0RPIEFUSU5HSURPJzpwPj1rdW9BPyfimqAgS1VPIEFUSU5HSURPJzon4pyFIE5vIHJhbmdlJztzQS5jbGFzc05hbWU9J3NiLXZhbCAnKyhwPD1rZG9BfHxwPj1rdW9BPyd3YXJuJzonb2snKTt9Y29uc3QgZEI9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1rZG8tZGlzdCcpO2lmKGRCKWRCLnRleHRDb250ZW50PSgocC1rZG9CKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkbyBLRE8nO2NvbnN0IHVCPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdheGlhM2Ita3VvLWRpc3QnKTtpZih1Qil1Qi50ZXh0Q29udGVudD0oKGt1b0ItcCkvcCoxMDApLnRvRml4ZWQoMSkrJyUgcGFyYSBvIEtVTyc7Y29uc3Qgc0I9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2F4aWEzYi1zdGF0dXMnKTtpZihzQil7c0IudGV4dENvbnRlbnQ9cDw9a2RvQj8n8J+UtCBLRE8gQVRJTkdJRE8nOnA+PWt1b0I/J+KaoCBLVU8gQVRJTkdJRE8nOifinIUgTm8gcmFuZ2UnO3NCLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PWtkb0J8fHA+PWt1b0I/J3dhcm4nOidvaycpO319Y2F0Y2goZSl7fX0sMjAwMCk7c2V0VGltZW91dChhc3luYygpPT57dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvUk9YTzM0LlNBJyk7aWYoIXIub2spcmV0dXJuO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIWQucHJpY2UpcmV0dXJuO2NvbnN0IHA9ZC5wcmljZTtzZXRFbCgncm94bzM0LXBvcy1wJyxmQlJMKHApKTtjb25zdCBkZT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm94bzM0LWtkby1kaXN0Jyk7aWYoZGUpZGUudGV4dENvbnRlbnQ9KChwLTEwLjUwKS9wKjEwMCkudG9GaXhlZCgxKSsnJSBhY2ltYSBkYSBiYXJyZWlyYSc7Y29uc3Qgc2U9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JveG8zNC1zdGF0dXMnKTtpZihzZSl7c2UudGV4dENvbnRlbnQ9cDw9MTAuNTA/J/CflLQgQkFSUkVJUkEgQVRJTkdJREEnOifinIUgQWNpbWEgZGEgYmFycmVpcmEnO3NlLmNsYXNzTmFtZT0nc2ItdmFsICcrKHA8PTEwLjUwPydpdG0nOidvaycpO319Y2F0Y2goZSl7fX0sMzAwMCk7fQphc3luYyBmdW5jdGlvbiBydW5NQ0ZvckF0aXZvKHRpY2tlcixzdHJpa2UsZGlhcyxsb2FkSWQscmVzSWQsc3RyaWtlSWQsdm9sSWQsaW5mb0lkKXt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7Y29uc3QgdG89c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9tb250ZWNhcmxvJyx7bWV0aG9kOidQT1NUJyxoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LHNpZ25hbDpjdHJsLnNpZ25hbCxib2R5OkpTT04uc3RyaW5naWZ5KHt0aWNrZXIsa19jYWxsOnN0cmlrZSxrX3B1dDpzdHJpa2UsdF9kYXlzOmRpYXMsbjo1MDAwfSl9KTtjbGVhclRpbWVvdXQodG8pO2lmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZChsb2FkSWQpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKHJlc0lkKS5zdHlsZS5kaXNwbGF5PSdibG9jayc7Y29uc3QgcHJvYj1OdW1iZXIoZC5wcm9iX3B1dF9leGVyY2lkYXx8MCk7Y29uc3Qgc0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHN0cmlrZUlkKTtzRWwudGV4dENvbnRlbnQ9cHJvYi50b0ZpeGVkKDIpKyclJztzRWwuY2xhc3NOYW1lPSdpbmQtdmFsICcrKHByb2I+MzA/J29rJzpwcm9iPjE1Pyd3YXJuJzonZG93bicpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKHZvbElkKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpbmZvSWQpLnRleHRDb250ZW50PSdWb2wuaGlzdC4gJytkLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclIMK3IFByb2IuIGNvbSB2b2wuaGlzdC4gKE1DKSB2cyB2b2wuaW1wbC4gKEImUykgc8OjbyBkaWZlcmVudGVzIOKAlCB2ZXIgcG9zacOnw6NvJzt9Y2F0Y2goZSl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQobG9hZElkKTtpZihlbCllbC50ZXh0Q29udGVudD0nRXJybzogJysoZS5tZXNzYWdlfHwnaW5kaXNwb27DrXZlbCcpO319CmFzeW5jIGZ1bmN0aW9uIHJ1bk1DQmFycmllcih0aWNrZXIsZW50cnksa2RvLGt1byxkaWFzLHByaWNlLHByZWZpeCl7cHJlZml4PXByZWZpeHx8J2F4aWEzJzt0cnl7Y29uc3QgY3RybD1uZXcgQWJvcnRDb250cm9sbGVyKCk7Y29uc3QgdG89c2V0VGltZW91dCgoKT0+Y3RybC5hYm9ydCgpLDI1MDAwKTtjb25zdCBib2R5PXt0aWNrZXIsZW50cnksa2RvLGt1byx0X2RheXM6ZGlhcyxuOjMwMDB9O2lmKHByaWNlPjApYm9keS5wcmljZT1wcmljZTtjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9tb250ZWNhcmxvL2JhcnJpZXInLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sc2lnbmFsOmN0cmwuc2lnbmFsLGJvZHk6SlNPTi5zdHJpbmdpZnkoYm9keSl9KTtjbGVhclRpbWVvdXQodG8pO2lmKCFyLm9rKXRocm93IDA7Y29uc3QgZD1hd2FpdCByLmpzb24oKTtpZihkLmVycm9yKXRocm93IG5ldyBFcnJvcihkLmVycm9yKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1sb2FkaW5nJykuc3R5bGUuZGlzcGxheT0nbm9uZSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLScrcHJlZml4KyctcmVzdWx0Jykuc3R5bGUuZGlzcGxheT0nYmxvY2snO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLW5vYnInKS50ZXh0Q29udGVudD1kLnByb2Jfc2VtX2JhcnJlaXJhLnRvRml4ZWQoMikrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWt1bycpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9hbHRhLnRvRml4ZWQoMikrJyUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy0nK3ByZWZpeCsnLWtkbycpLnRleHRDb250ZW50PWQucHJvYl9iYXJyZWlyYV9iYWl4YS50b0ZpeGVkKDIpKyclJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy12b2wnKS50ZXh0Q29udGVudD1kLnZvbGF0aWxpZGFkZV9oaXN0b3JpY2FfcGN0KyclJztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1pbmZvJykudGV4dENvbnRlbnQ9J1ByZcOnbyBSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtkbysnIMK3IEtVTyBSJCAnK2Qua3VvKycgwrcgJytkLmNlbmFyaW9zLnRvTG9jYWxlU3RyaW5nKCkrJyBjZW7DoXJpb3MnO31jYXRjaChlKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtJytwcmVmaXgrJy1sb2FkaW5nJyk7aWYoZWwpZWwudGV4dENvbnRlbnQ9J0Vycm86ICcrKGUubWVzc2FnZXx8J2luZGlzcG9uw612ZWwnKTt9fQphc3luYyBmdW5jdGlvbiBydW5NQ1ByZWZpeGFkbyh0aWNrZXIsZW50cnksa2RvLGRpYXMscHJpY2Upe3RyeXtjb25zdCBjdHJsPW5ldyBBYm9ydENvbnRyb2xsZXIoKTtjb25zdCB0bz1zZXRUaW1lb3V0KCgpPT5jdHJsLmFib3J0KCksMjUwMDApO2NvbnN0IGJvZHk9e3RpY2tlcixrX2NhbGw6ZW50cnksa19wdXQ6ZW50cnksdF9kYXlzOmRpYXMsa25vY2tfZG93bjprZG8sbjo1MDAwfTtpZihwcmljZT4wKWJvZHkucHJpY2U9cHJpY2U7Y29uc3Qgcj1hd2FpdCBmZXRjaChCQVNFKycvbW9udGVjYXJsbycse21ldGhvZDonUE9TVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxzaWduYWw6Y3RybC5zaWduYWwsYm9keTpKU09OLnN0cmluZ2lmeShib2R5KX0pO2NsZWFyVGltZW91dCh0byk7aWYoIXIub2spdGhyb3cgMDtjb25zdCBkPWF3YWl0IHIuanNvbigpO2lmKGQuZXJyb3IpdGhyb3cgbmV3IEVycm9yKGQuZXJyb3IpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtbG9hZGluZycpLnN0eWxlLmRpc3BsYXk9J25vbmUnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtcmVzdWx0Jykuc3R5bGUuZGlzcGxheT0nYmxvY2snO2NvbnN0IHNFbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWMtcm94bzM0LXN1Y2Vzc28nKTtzRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9zdWNlc3NvKS50b0ZpeGVkKDIpKyclJztzRWwuY2xhc3NOYW1lPSdpbmQtdmFsICcrKGQucHJvYl9zdWNlc3NvPjcwPydvayc6ZC5wcm9iX3N1Y2Vzc28+NTA/J3dhcm4nOidkb3duJyk7Y29uc3QgY0VsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtY2FsbCcpO2lmKGNFbCljRWwudGV4dENvbnRlbnQ9TnVtYmVyKGQucHJvYl9jYWxsX2V4ZXJjaWRhKS50b0ZpeGVkKDIpKyclJztjb25zdCBrRWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1rZG8nKTtpZihrRWwpa0VsLnRleHRDb250ZW50PWQucHJvYl9rZG9fYXRpbmdpZG8hPW51bGw/TnVtYmVyKGQucHJvYl9rZG9fYXRpbmdpZG8pLnRvRml4ZWQoMikrJyUnOifigJQnO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtdm9sJykudGV4dENvbnRlbnQ9ZC52b2xhdGlsaWRhZGVfaGlzdG9yaWNhX3BjdCsnJSc7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21jLXJveG8zNC1pbmZvJykudGV4dENvbnRlbnQ9J1ByZcOnbyBSJCAnK2QucHJlY29fYXR1YWwrJyDCtyBLRE8gUiQgJytkLmtub2NrX2Rvd24rJyDCtyAnK2QuY2VuYXJpb3MudG9Mb2NhbGVTdHJpbmcoKSsnIGNlbsOhcmlvcyc7fWNhdGNoKGUpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtYy1yb3hvMzQtbG9hZGluZycpO2lmKGVsKWVsLnRleHRDb250ZW50PSdFcnJvOiAnKyhlLm1lc3NhZ2V8fCdpbmRpc3BvbsOtdmVsJyk7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hJbmRpY2F0b3JzKHRpY2tlcil7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2luZGljYXRvcnMvJyt0aWNrZXIpO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hCVENJbmRpY2F0b3JzKCl7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2J0Yy9pbmRpY2F0b3JzJyk7aWYoIXIub2spcmV0dXJuIG51bGw7cmV0dXJuIGF3YWl0IHIuanNvbigpO31jYXRjaChlKXtyZXR1cm4gbnVsbDt9fQphc3luYyBmdW5jdGlvbiBmZXRjaEJUQ0N5Y2xlKCl7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2J0Yy9jeWNsZScpO2lmKCFyLm9rKXJldHVybiBudWxsO3JldHVybiBhd2FpdCByLmpzb24oKTt9Y2F0Y2goZSl7cmV0dXJuIG51bGw7fX0KYXN5bmMgZnVuY3Rpb24gZmV0Y2hGZWFyR3JlZWQoKXsKICB0cnl7CiAgICBjb25zdCByPWF3YWl0IGZldGNoKEJBU0UrJy9mZWFyZ3JlZWQnKTsKICAgIGlmKCFyLm9rKXJldHVybjsKICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBjb25zdCB2PWQudmFsdWV8fDUwOwogICAgY29uc3QgY2xzPXY8PTI1Pyd2YXIoLS1yZWQpJzp2PD00NT8ndmFyKC0td2FybiknOnY8PTc1Pyd2YXIoLS1hY2NlbnQpJzondmFyKC0tZ3JlZW4pJzsKICAgIGNvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmZWFyLWdyZWVkLWFyZWEnKTsKICAgIGlmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjE0cHgiPicrCiAgICAgICc8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKTttYXJnaW4tYm90dG9tOjhweCI+8J+YsSBGZWFyICYgR3JlZWQgSW5kZXg8L2Rpdj4nKwogICAgICAnPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweCI+JysKICAgICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjJyZW07Zm9udC13ZWlnaHQ6ODAwO2NvbG9yOicrY2xzKyciPicrdisnPC9kaXY+JysKICAgICAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi44NXJlbTtmb250LXdlaWdodDo3MDA7Y29sb3I6JytjbHMrJyI+JysoZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpKyc8L2Rpdj4nKwogICAgICAnPC9kaXY+PC9kaXY+JzsKICAgIHNldEVsKCdmZy12YWwnLFN0cmluZyh2KSk7c2V0RWwoJ2ZnLWxibCcsZC52YWx1ZV9jbGFzc2lmaWNhdGlvbnx8J05ldXRybycpOwogICAgLy8gQnVzY2EgQlRDIHByaWNlIHBhcmEgbyBjYXJkIEYmRwogICAgdHJ5ewogICAgICBjb25zdCByYj1hd2FpdCBmZXRjaCgnaHR0cHM6Ly9hcGkuaHlwZXJsaXF1aWQueHl6L2luZm8nLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7dHlwZTonYWxsTWlkcyd9KX0pOwogICAgICBpZihyYi5vayl7Y29uc3QgZGI9YXdhaXQgcmIuanNvbigpO2NvbnN0IGJwPXBhcnNlRmxvYXQoZGIuQlRDfHwwKTtpZihicD4wKXtzZXRFbCgnYnRjLWluZC1wcmljZScsZlVTRChicCkpO3NldEVsKCdidGMtcCcsZlVTRChicCkpO319CiAgICB9Y2F0Y2goZTIpe30KICB9Y2F0Y2goZSl7fQp9CmZ1bmN0aW9uIHJlbmRlckluZGljYXRvcnMoYXJlYUlkLGRhdGEsc2hvd0FsbCl7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoYXJlYUlkKTsKICBpZighZWwpcmV0dXJuOwogIGlmKCFkYXRhKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXdhcm4pO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5TZW0gZGFkb3Mg4oCUIGNsaXF1ZSDihrsgcGFyYSB0ZW50YXIgbm92YW1lbnRlPC9kaXY+JztyZXR1cm47fQogIGlmKGRhdGEuZXJyb3Ipe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tZGFuZ2VyKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTBweCI+4pqgICcrZGF0YS5lcnJvcisnPC9kaXY+JztyZXR1cm47fQogIGNvbnN0IGluZHM9ZGF0YS5pbmRpY2Fkb3Jlc3x8ZGF0YS5pbmRpY2F0b3JzfHxbXTsKICBjb25zdCBzY29yZT1kYXRhLnNjb3JlX3RvdGFsfHxkYXRhLnNjb3JlOwogIGNvbnN0IHByZWNvPWRhdGEucHJlY29fYXR1YWx8fGRhdGEucHJpY2U7CiAgLy8gc2NvcmU9MCDDqSB2w6FsaWRvIChuw6NvIHVzYXIgIXNjb3JlKQogIGlmKCFpbmRzfHwhaW5kcy5sZW5ndGgpe2lmKHNjb3JlPT1udWxsKXtlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXdhcm4pO2ZvbnQtc2l6ZTouNjVyZW07cGFkZGluZzoxMHB4Ij5DYWxjdWxhbmRvIGluZGljYWRvcmVzLi4uPC9kaXY+JztyZXR1cm47fX0KICBsZXQgaHRtbD0nJzsKICBpZihzY29yZSE9bnVsbClodG1sKz0nPGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEwcHg7bWFyZ2luLWJvdHRvbTo4cHg7dGV4dC1hbGlnbjpjZW50ZXIiPicrCiAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOi41NXJlbTtjb2xvcjp2YXIoLS1tdXRlZCkiPlNDT1JFIFRPVEFMPC9kaXY+JysKICAgICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MS41cmVtO2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjonKyhzY29yZT49NjA/J3ZhcigtLWdyZWVuKSc6c2NvcmU+PTQwPyd2YXIoLS13YXJuKSc6J3ZhcigtLXJlZCknKSsnIj4nK3Njb3JlKycvMTAwPC9kaXY+JysKICAgICc8ZGl2IHN0eWxlPSJmb250LXNpemU6LjU1cmVtO2NvbG9yOnZhcigtLW11dGVkKSI+Q290YcOnw6NvOiAnKyhwcmVjbz8nUiQgJytOdW1iZXIocHJlY28pLnRvRml4ZWQoMik6J+KAlCcpKyc8L2Rpdj48L2Rpdj4nOwogIGh0bWwrPSc8ZGl2IHN0eWxlPSJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjZweCI+JzsKICBjb25zdCBsaXN0PXNob3dBbGw/aW5kczppbmRzLnNsaWNlKDAsMTApOwogIGxpc3QuZm9yRWFjaChmdW5jdGlvbihpKXsKICAgIGNvbnN0IGNscz1pLnNpbmFsPT09J0FsdGEnPydvayc6aS5zaW5hbD09PSdCYWl4YSc/J2Rvd24nOid3YXJuJzsKICAgIGh0bWwrPSc8ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj4nKyhpLm5vbWV8fGkubmFtZXx8JycpKyc8L2Rpdj4nKwogICAgICAnPGRpdiBjbGFzcz0iaW5kLXZhbCAnK2NscysnIj4nKyhpLnZhbG9yIT1udWxsP2kudmFsb3I6aS52YWx1ZSE9bnVsbD9pLnZhbHVlOifigJQnKSsnPC9kaXY+JysKICAgICAgJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDhyZW07Y29sb3I6dmFyKC0tbXV0ZWQpIj4nKyhpLnNpbmFsfHxpLnNpZ25hbHx8JycpKyc8L2Rpdj48L2Rpdj4nOwogIH0pOwogIGh0bWwrPSc8L2Rpdj4nOwogIGVsLmlubmVySFRNTD1odG1sOwp9CgpmdW5jdGlvbiByZW5kZXJCVENJbmRpY2F0b3JzKGRhdGEpe2NvbnN0IGVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdidGMtaW5kLWFyZWEnKTtpZighZWx8fCFkYXRhKXJldHVybjtsZXQgaHRtbD0nPGRpdiBzdHlsZT0iZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDo2cHgiPic7aWYoZGF0YS5yc2lfc2VtYW5hbCE9bnVsbCl7aHRtbCs9JzxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlJTSSBTZW1hbmFsPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCAnKyhkYXRhLnJzaV9zZW1hbmFsPDMwPydvayc6ZGF0YS5yc2lfc2VtYW5hbD43MD8nZG93bic6J3dhcm4nKSsnIj4nK2RhdGEucnNpX3NlbWFuYWwudG9GaXhlZCgxKSsnPC9kaXY+PC9kaXY+JztzZXRFbCgnYnRjLXJzaScsZGF0YS5yc2lfc2VtYW5hbC50b0ZpeGVkKDEpKTt9aWYoZGF0YS5tbTIwMClodG1sKz0nPGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+TU0gMjAwZDwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JytOdW1iZXIoZGF0YS5tbTIwMCkudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KSsnPC9kaXY+PC9kaXY+JztodG1sKz0nPC9kaXY+JztlbC5pbm5lckhUTUw9aHRtbDtpZihkYXRhLnByZWNvX2F0dWFsKXtzZXRFbCgnYnRjLWluZC1wcmljZScsJyQnK051bWJlcihkYXRhLnByZWNvX2F0dWFsKS50b0xvY2FsZVN0cmluZygnZW4tVVMnLHttYXhpbXVtRnJhY3Rpb25EaWdpdHM6MH0pKTt9fQpmdW5jdGlvbiByZW5kZXJCVENDeWNsZShkKXtjb25zdCBlbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYnRjLWN5Y2xlLWFyZWEnKTtpZighZWx8fCFkfHxkLmVycm9yKXJldHVybjtjb25zdCBmVT12PT52PyckJytOdW1iZXIodikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWF4aW11bUZyYWN0aW9uRGlnaXRzOjB9KTon4oCUJztlbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImRpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6NnB4O21hcmdpbi1ib3R0b206OHB4Ij48ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5NVlJWIFotU2NvcmU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsICcrKGQubXZydl96c2NvcmU/LnZhbHVlPDE/J29rJzpkLm12cnZfenNjb3JlPy52YWx1ZTwzPyd3YXJuJzonZG93bicpKyciPicrZC5tdnJ2X3pzY29yZT8udmFsdWUrJzwvZGl2PjxkaXYgc3R5bGU9ImZvbnQtc2l6ZTouNDhyZW07Y29sb3I6dmFyKC0tbXV0ZWQpIj4nK2QubXZydl96c2NvcmU/LmxhYmVsKyc8L2Rpdj48L2Rpdj48ZGl2IGNsYXNzPSJpbmQtYm94Ij48ZGl2IGNsYXNzPSJpbmQtbGJsIj5OVVBMPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCB3YXJuIj4nKygoZC5udXBsPy52YWx1ZXx8MCkqMTAwKS50b0ZpeGVkKDApKyclPC9kaXY+PGRpdiBzdHlsZT0iZm9udC1zaXplOi40OHJlbTtjb2xvcjp2YXIoLS1tdXRlZCkiPicrZC5udXBsPy5sYWJlbCsnPC9kaXY+PC9kaXY+PGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UHVlbGwgTXVsdGlwbGU8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrZC5wdWVsbD8udmFsdWUrJzwvZGl2PjwvZGl2PjxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPjIwMFcgTUE8L2Rpdj48ZGl2IGNsYXNzPSJpbmQtdmFsIHdhcm4iPicrZlUoZC5tYTIwMHcpKyc8L2Rpdj48ZGl2IHN0eWxlPSJmb250LXNpemU6LjQ4cmVtO2NvbG9yOnZhcigtLW11dGVkKSI+JysoZC5tYTIwMHdfcGN0PycrJytkLm1hMjAwd19wY3QrJyUnOicnKSsnPC9kaXY+PC9kaXY+PGRpdiBjbGFzcz0iaW5kLWJveCI+PGRpdiBjbGFzcz0iaW5kLWxibCI+UmFpbmJvdzwvZGl2PjxkaXYgY2xhc3M9ImluZC12YWwgd2FybiI+JysoZC5yYWluYm93Py5iYW5kfHwn4oCUJykrJzwvZGl2PjwvZGl2PjxkaXYgY2xhc3M9ImluZC1ib3giPjxkaXYgY2xhc3M9ImluZC1sYmwiPlBpIEN5Y2xlPC9kaXY+PGRpdiBjbGFzcz0iaW5kLXZhbCBvayI+JytmVShkLnBpX2N5Y2xlPy5kaXN0YW5jZSkrJyBkaXN0LjwvZGl2PjwvZGl2PjwvZGl2PjxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7cGFkZGluZzo4cHg7Zm9udC1zaXplOi42cmVtO2NvbG9yOnZhcigtLWFjY2VudCkiPicrKGQucGlfY3ljbGU/LnNpZ25hbHx8JycpKyc8L2Rpdj4nO30KYXN5bmMgZnVuY3Rpb24gbG9hZEluZGljYXRvcnMoKXsKICAvLyBCVEMgcHJpbWVpcm8KICBjb25zdFtidGMsY3ljbGVdPWF3YWl0IFByb21pc2UuYWxsKFtmZXRjaEJUQ0luZGljYXRvcnMoKSxmZXRjaEJUQ0N5Y2xlKCldKTsKICByZW5kZXJCVENJbmRpY2F0b3JzKGJ0Yyk7cmVuZGVyQlRDQ3ljbGUoY3ljbGUpO2ZldGNoRmVhckdyZWVkKCk7CiAgLy8gU3RvY2tzIGVtIHBhcmFsZWxvIGNvbSB0aW1lb3V0IGluZGl2aWR1YWwgZGUgMjBzCiAgY29uc3Qgc3RvY2tzPVsKICAgIFsnUEVUUjQuU0EnLCdwZXRyNC1pbmQtYXJlYSddLFsnVkFMRTMuU0EnLCd2YWxlMy1pbmQtYXJlYSddLAogICAgWydCQkFTMy5TQScsJ2JiYXMzLWluZC1hcmVhJ10sWydBWElBMy5TQScsJ2F4aWEzLWluZC1hcmVhJ10sCiAgICBbJ1JPWE8zNC5TQScsJ3JveG8zNC1pbmQtYXJlYSddCiAgXTsKICBjb25zdCB3aXRoVGltZW91dD0ocHJvbWlzZSxtcyxmYWxsYmFjayk9PnsKICAgIHJldHVybiBQcm9taXNlLnJhY2UoW3Byb21pc2UsIG5ldyBQcm9taXNlKHI9PnNldFRpbWVvdXQoKCk9PnIoZmFsbGJhY2spLG1zKSldKTsKICB9OwogIGNvbnN0IHJlc3VsdHM9YXdhaXQgUHJvbWlzZS5hbGwoCiAgICBzdG9ja3MubWFwKChbdGlja2VyXSk9PndpdGhUaW1lb3V0KGZldGNoSW5kaWNhdG9ycyh0aWNrZXIpLDIwMDAwLHtlcnJvcjonVGltZW91dCd9KSkKICApOwogIHN0b2Nrcy5mb3JFYWNoKChbLGFyZWFJZF0saSk9PnJlbmRlckluZGljYXRvcnMoYXJlYUlkLHJlc3VsdHNbaV0sdHJ1ZSkpOwp9CmNvbnN0IENBTF9GTEFHUz17J1VTRCc6J/Cfh7rwn4e4JywnQlJMJzon8J+Hp/Cfh7cnLCdFVVInOifwn4eq8J+HuicsJ0dCUCc6J/Cfh6zwn4enJywnQ05ZJzon8J+HqPCfh7MnLCdKUFknOifwn4ev8J+HtScsJ0NBRCc6J/Cfh6jwn4emJywnQVVEJzon8J+HpvCfh7onfTsKYXN5bmMgZnVuY3Rpb24gbG9hZENhbGVuZGFyKCl7Y29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhbGVuZGFyLWFyZWEnKTtpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlcjthbmltYXRpb246cHVsc2UgMS41cyBpbmZpbml0ZSI+Q2FycmVnYW5kby4uLjwvZGl2Pic7dHJ5e2NvbnN0IHI9YXdhaXQgZmV0Y2goQkFTRSsnL2NhbGVuZGFyJyk7aWYoIXIub2spdGhyb3cgbmV3IEVycm9yKCdIVFRQICcrci5zdGF0dXMpO2NvbnN0IGV2ZW50cz1hd2FpdCByLmpzb24oKTtjb25zb2xlLmxvZygnQ2FsZW5kYXIgZXZlbnRzOicsZXZlbnRzLmxlbmd0aCk7aWYoIWV2ZW50c3x8IWV2ZW50cy5sZW5ndGgpe2VsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0icGFkZGluZzoyMHB4O2NvbG9yOnZhcigtLW11dGVkKSI+U2VtIGV2ZW50b3MgZGlzcG9uw612ZWlzIGVzdGEgc2VtYW5hPC9kaXY+JztyZXR1cm47fWNvbnN0IGJ5RGF0ZT17fTtldmVudHMuZm9yRWFjaChlPT57Y29uc3QgZHQ9KGUuZGF0ZXx8JycpLnNsaWNlKDAsMTApO2lmKCFieURhdGVbZHRdKWJ5RGF0ZVtkdF09W107YnlEYXRlW2R0XS5wdXNoKGUpO30pO2xldCBodG1sPScnO09iamVjdC5rZXlzKGJ5RGF0ZSkuc29ydCgpLmZvckVhY2goZHQ9Pntjb25zdCBkPW5ldyBEYXRlKGR0KydUMTI6MDA6MDAnKTtjb25zdCBsYWJlbD1kLnRvTG9jYWxlRGF0ZVN0cmluZygncHQtQlInLHt3ZWVrZGF5OidzaG9ydCcsZGF5OicyLWRpZ2l0Jyxtb250aDonc2hvcnQnfSk7aHRtbCs9JzxkaXYgY2xhc3M9InNlYyI+PHNwYW4+8J+ThTwvc3Bhbj4gJytsYWJlbCsnPC9kaXY+PGRpdiBzdHlsZT0iYmFja2dyb3VuZDp2YXIoLS1iZzIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTttYXJnaW4tYm90dG9tOjhweCI+JztieURhdGVbZHRdLmZvckVhY2goZT0+e2NvbnN0IGZsYWc9ZS5mbGFnfHxDQUxfRkxBR1NbZS5jb3VudHJ5XXx8J/CfjJAnO2NvbnN0IGltcD1lLmltcG9ydGFuY2V8fDE7Y29uc3QgaW1wQ29sb3I9aW1wPj0zPyd2YXIoLS1yZWQpJzppbXA+PTI/J3ZhcigtLXdhcm4pJzondmFyKC0tbXV0ZWQpJztjb25zdCBhY3R1YWw9ZS5hY3R1YWw/JzxiIHN0eWxlPSJjb2xvcjp2YXIoLS1hY2NlbnQpIj4nK2UuYWN0dWFsKyc8L2I+JzonPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKSI+4oCUPC9zcGFuPic7aHRtbCs9JzxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjZweDtwYWRkaW5nOjZweCAxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Zm9udC1zaXplOi42cmVtIj48c3Bhbj4nK2ZsYWcrJzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO21pbi13aWR0aDo0MHB4Ij4nKyhlLnRpbWV8fCcnKSsnPC9zcGFuPjxzcGFuIHN0eWxlPSJmbGV4OjEiPicrKGUuZXZlbnR8fCcnKSsnPC9zcGFuPjxzcGFuIHN0eWxlPSJjb2xvcjonK2ltcENvbG9yKyc7bWluLXdpZHRoOjE2cHgiPicrJ+KXjycucmVwZWF0KGltcCkrJzwvc3Bhbj48c3BhbiBzdHlsZT0ibWluLXdpZHRoOjUwcHg7dGV4dC1hbGlnbjpyaWdodCI+JythY3R1YWwrJzwvc3Bhbj48c3BhbiBzdHlsZT0iY29sb3I6dmFyKC0tbXV0ZWQpO21pbi13aWR0aDo0NXB4O3RleHQtYWxpZ246cmlnaHQiPicrKGUuZm9yZWNhc3R8fCcnKSsnPC9zcGFuPjwvZGl2Pic7fSk7aHRtbCs9JzwvZGl2Pic7fSk7ZWwuaW5uZXJIVE1MPWh0bWw7fWNhdGNoKGUpe2lmKGVsKWVsLmlubmVySFRNTD0nPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tZGFuZ2VyKTtwYWRkaW5nOjIwcHgiPkVycm8gYW8gY2FycmVnYXI8L2Rpdj4nO319CmFzeW5jIGZ1bmN0aW9uIHJlbG9hZEluZCh0aWNrZXIpewogIGNvbnN0IGFyZWFJZD10aWNrZXIrJy1pbmQtYXJlYSc7CiAgY29uc3QgZWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoYXJlYUlkKTsKICBpZihlbCllbC5pbm5lckhUTUw9JzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLW11dGVkKTtmb250LXNpemU6LjY1cmVtO3BhZGRpbmc6MTBweDthbmltYXRpb246cHVsc2UgMXMgaW5maW5pdGUiPkNhcnJlZ2FuZG8gJyt0aWNrZXIudG9VcHBlckNhc2UoKSsnLi4uPC9kaXY+JzsKICBjb25zdCB0aWNrZXJNYXA9eydwZXRyNCc6J1BFVFI0LlNBJywndmFsZTMnOidWQUxFMy5TQScsJ2JiYXMzJzonQkJBUzMuU0EnLCdheGlhMyc6J0FYSUEzLlNBJywncm94bzM0JzonUk9YTzM0LlNBJ307CiAgY29uc3QgZD1hd2FpdCBmZXRjaEluZGljYXRvcnModGlja2VyTWFwW3RpY2tlcl18fHRpY2tlci50b1VwcGVyQ2FzZSgpKycuU0EnKTsKICByZW5kZXJJbmRpY2F0b3JzKGFyZWFJZCxkLHRydWUpOwp9Cgphc3luYyBmdW5jdGlvbiBmZXRjaEFsbCgpe3RyeXtjb25zdFssdHYsZnV0dXJlc109YXdhaXQgUHJvbWlzZS5hbGwoW2ZldGNoSEwoKSxmZXRjaFRWKCksZmV0Y2hGdXR1cmVzKCldKTtjb25zdCBub3c9bmV3IERhdGUoKS50b0xvY2FsZVRpbWVTdHJpbmcoJ3B0LUJSJyk7c2V0RWwoJ2xhc3QtdXBkYXRlJywnQXR1YWxpemFkbyAnK25vdyk7c2V0RWwoJ2Zvb3Rlci10aW1lJyxub3cpO2RvTWFjcm8odHYsZnV0dXJlcyk7ZG9Qb3NpdGlvbnModHYpO3NldFRpbWVvdXQoZmV0Y2hGdW5kaW5nLDMwMDApO3NldFRpbWVvdXQoKCk9PntydW5NQ0ZvckF0aXZvKCdQRVRSNC5TQScsMzAuODUsMTk1LCdtYy1wdC1sb2FkaW5nJywnbWMtcHQtcmVzdWx0JywnbWMtcHQtc3RyaWtlJywnbWMtcHQtdm9sJywnbWMtcHQtaW5mbycpO30sNjAwMCk7c2V0VGltZW91dCgoKT0+e3J1bk1DRm9yQXRpdm8oJ1ZBTEUzLlNBJyw1Ny40MCwyNTgsJ21jLXZsLWxvYWRpbmcnLCdtYy12bC1yZXN1bHQnLCdtYy12bC1zdHJpa2UnLCdtYy12bC12b2wnLCdtYy12bC1pbmZvJyk7fSwxMjAwMCk7c2V0VGltZW91dCgoKT0+e3J1bk1DQmFycmllcignQVhJQTMuU0EnLDU0LjMxLDQzLjUxLDY4Ljc2LDEwMSw1NC4zMSwnYXhpYTMnKTt9LDE4MDAwKTtzZXRUaW1lb3V0KCgpPT57cnVuTUNCYXJyaWVyKCdBWElBMy5TQScsNTAuNjUsNDAuNTIsNjIuODEsMTE5LDUwLjY1LCdheGlhM2InKTt9LDI0MDAwKTtzZXRUaW1lb3V0KCgpPT57cnVuTUNQcmVmaXhhZG8oJ1JPWE8zNC5TQScsMTIuODgsMTAuNTAsNDEsMTIuODgpO30sMzAwMDApO3dpbmRvdy5faW5kTG9hZGVkPWZhbHNlO31jYXRjaChlKXtjb25zb2xlLmVycm9yKCdmZXRjaEFsbDonLGUpO319CmZldGNoQWxsKCk7CnNldEludGVydmFsKGZldGNoQWxsLDEyMDAwMCk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4=").decode('utf-8')

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp=app.response_class(response=PANEL_HTML,status=200,mimetype='text/html')
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    return resp

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
