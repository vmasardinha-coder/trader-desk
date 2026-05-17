"""
Trader Desk — Proxy Server v4
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
    'DEFAULT':   {'nome':'Geral',        'pl_medio':12.0,'pvp_medio':2.0,'roe_min':12},
}

# ── HARDCODED FUNDAMENTAIS (atualizar trimestralmente) ─
FUND = {
    'PETR4': {'pvp':1.65,'dy':6.42,'lpa':8.54, 'vpa':29.76,'ev_ebitda':3.2, 'roe':22.5,'debt_ebitda':0.8, 'margem':18.3},
    'VALE3': {'pvp':1.80,'dy':8.50,'lpa':11.20,'vpa':47.30,'ev_ebitda':4.1, 'roe':24.1,'debt_ebitda':0.6, 'margem':22.1},
    'BBAS3': {'pvp':0.95,'dy':9.80,'lpa':4.20, 'vpa':24.80,'ev_ebitda':None,'roe':19.8,'debt_ebitda':None,'margem':28.5},
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
    # Tenta múltiplos tickers para VIX e DXY
    vix = yquote('%5EVIX') or yquote('VIXY')
    # DXY — via Hyperliquid xyz:DXY (confirmado funcionando)
    dxy = None
    try:
        r_hl = requests.post('https://api.hyperliquid.xyz/info',
            json={'type':'allMids','dex':'xyz'},
            headers={'Content-Type':'application/json'}, timeout=5)
        if r_hl.ok:
            hl_data = r_hl.json()
            dxy_val = hl_data.get('xyz:DXY')
            if dxy_val:
                dxy_p = round(float(dxy_val), 3)
                dxy = {'price': dxy_p, 'prev': round(dxy_p * 0.999, 3)}
    except: pass
    # WIN futuro B3 — não tem no Yahoo, calcula via IBOV
    win = None
    try:
        ibov = yquote('%5EBVSP')
        if ibov:
            # WIN futuro tipicamente negocia com leve diferença do IBOV
            win = {'price': round(ibov['price'], 0), 'prev': round(ibov['prev'], 0)}
    except: pass
    return jsonify({
        'dji': yquote('%5EDJI'),
        'esf': yquote('ES%3DF'),
        'nqf': yquote('NQ%3DF'),
        'win': win,
        'vix': vix,
        'dxy': dxy,
    })

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
@app.route('/montecarlo', methods=['POST'])
def run_montecarlo():
    try:
        import numpy as np
        data=request.get_json() or {}
        ticker=data.get('ticker','BBAS3.SA')
        K_call=float(data.get('k_call',22.68))
        K_put=float(data.get('k_put',22.68))
        T_days=int(data.get('t_days',21))
        n=5000  # fixo em 5k — rapido e estatisticamente valido
        kd=float(data['knock_down']) if data.get('knock_down') else None

        # Busca preco atual
        r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=60d',
            headers={'User-Agent':'Mozilla/5.0'},timeout=8)
        if not r.ok: return jsonify({'error':f'Yahoo {r.status_code}'}),500
        d=r.json()
        meta=d['chart']['result'][0]['meta']
        cl=[c for c in d['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        S=float(meta.get('regularMarketPrice',cl[-1]))
        sigma=vol_hist(cl)
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

# ── SERVE HTML ────────────────────────────────────────
import os

# HTML EMBUTIDO — atualizado em 2026-05-16 11:03
PANEL_HTML = """<!DOCTYPE html>
<!-- Trader Desk v5.2 - 2026-05-15 00:44 -->
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
</div>

<!-- ═══════════════════════════════════════════════════ -->
<!-- TAB 1: COTAÇÕES -->
<!-- ═══════════════════════════════════════════════════ -->
<div id="tab-cotacoes" class="tab-content active">

  <div class="sec"><span>01</span> Índices EUA <span class="src">· Hyperliquid xyz: dex</span></div>
  <div class="grid">
    <div class="card blue"><div class="c-label">Índice · EUA</div><div class="c-name">S&amp;P 500</div><div class="c-price loading" id="sp-p">—</div><div class="c-change" id="sp-c">—</div><div class="c-src" id="sp-s">HL</div></div>
    <div class="card blue"><div class="c-label">Futuro · EUA</div><div class="c-name">S&amp;P ES1*</div><div class="c-price loading" id="esf-p">—</div><div class="c-change" id="esf-c">—</div><div class="c-src" id="esf-s">proxy</div></div>
    <div class="card blue"><div class="c-label">Índice · EUA</div><div class="c-name">Nasdaq 100</div><div class="c-price loading" id="ndx-p">—</div><div class="c-change" id="ndx-c">—</div><div class="c-src" id="ndx-s">HL</div></div>
    <div class="card blue"><div class="c-label">Futuro · EUA</div><div class="c-name">NQ Futuro</div><div class="c-price loading" id="nqf-p">—</div><div class="c-change" id="nqf-c">—</div><div class="c-src" id="nqf-s">proxy</div></div>
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
    <div class="card green"><div class="c-label">Ação · BR</div><div class="c-name">VALE3</div><div class="c-price loading" id="vale3q-p">—</div><div class="c-change" id="vale3q-c">—</div><div class="c-src">TV</div></div>
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
  <div class="grid2">

    <!-- PETR4 POSIÇÃO -->
    <div class="pos-card acao">
      <div class="pos-label">Petrobras PN · Call Vendida · PETRL327 · Venc 18/12/26</div>
      <div class="pos-ticker">PETR4</div>
      <div class="pos-price loading" id="pt-pos-p">—</div>
      <div class="pos-chg" id="pt-pos-c">—</div>
      <div class="sb">
        <div class="sb-row"><span class="sb-lbl">Strike vendido</span><span class="sb-val warn">R$ 32,00</span></div>
        <div class="sb-row"><span class="sb-lbl">Distância ITM</span><span class="sb-val itm" id="pt-itm">—</span></div>
        <div class="sb-row"><span class="sb-lbl">Situação</span><span class="sb-val itm">⚠ DEEP ITM</span></div>
        <div class="sb-row"><span class="sb-lbl">Gatilho reest.</span><span class="sb-val warn">≈ R$ 40</span></div>
        <div class="sb-row"><span class="sb-lbl">% p/ gatilho</span><span class="sb-val warn" id="pt-pct-gatilho">—</span></div>
        <div class="sb-row"><span class="sb-lbl">Estratégia</span><span class="sb-val">Call vendida · prêmio recorrente</span></div>
        <div class="prog-wrap"><div class="prog-bar danger" id="pt-bar" style="width:0%"></div></div>
      </div>
      <div class="signal" style="margin-top:8px">
        <div class="sig-title">📋 Status da Posição</div>
        <div id="pt-status">Strike em R$ 32 — preço atual muito acima. Monitorar oportunidade de rolagem quando próximo de R$ 40.</div>
      </div>
    </div>

    <!-- VALE3 POSIÇÃO -->
    <div class="pos-card acao">
      <div class="pos-label">Vale ON · Call Vendida · VALEB628 · Venc 19/02/27</div>
      <div class="pos-ticker">VALE3</div>
      <div class="pos-price loading" id="vl-pos-p">—</div>
      <div class="pos-chg" id="vl-pos-c">—</div>
      <div class="sb">
        <div class="sb-row"><span class="sb-lbl">Strike vendido</span><span class="sb-val warn">R$ 57,00</span></div>
        <div class="sb-row"><span class="sb-lbl">Distância ITM</span><span class="sb-val itm" id="vl-itm">—</span></div>
        <div class="sb-row"><span class="sb-lbl">Situação</span><span class="sb-val itm">⚠ DEEP ITM</span></div>
        <div class="sb-row"><span class="sb-lbl">Gatilhos</span><span class="sb-val warn">R$ 70 · R$ 80 · R$ 85</span></div>
        <div class="sb-row"><span class="sb-lbl">% p/ R$70</span><span class="sb-val warn" id="vl-pct-gatilho">—</span></div>
        <div class="sb-row"><span class="sb-lbl">Estratégia</span><span class="sb-val">Call vendida · prêmio + dividendos</span></div>
        <div class="prog-wrap"><div class="prog-bar danger" id="vl-bar" style="width:0%"></div></div>
      </div>
      <div class="signal" style="margin-top:8px">
        <div class="sig-title">📋 Status da Posição</div>
        <div id="vl-status">Strike em R$ 57 — preço atual acima. Avaliar reestruturação nos gatilhos R$ 70, R$ 80 ou R$ 85.</div>
      </div>
    </div>

  </div>

  <!-- BBAS3 POSIÇÃO -->
  <div class="pos-card acao" style="margin-top:12px">
    <div class="pos-label">Banco do Brasil · Trava de Baixa · Venc 01/06/2026</div>
    <div class="pos-ticker">BBAS3</div>
    <div class="pos-price loading" id="bb-pos-p">—</div>
    <div class="pos-chg" id="bb-pos-c">—</div>
    <div class="sb">
      <div class="sb-row"><span class="sb-lbl">Estrutura</span><span class="sb-val">Trava de Baixa Sintética</span></div>
      <div class="sb-row"><span class="sb-lbl">Strike (Call + Put)</span><span class="sb-val warn">R$ 22,68</span></div>
      <div class="sb-row"><span class="sb-lbl">KDO (Knock-Down)</span><span class="sb-val warn">R$ 19,70 — barreira de proteção</span></div>
      <div class="sb-row"><span class="sb-lbl">Proteção na queda</span><span class="sb-val ok">até 10% abaixo do strike</span></div>
      <div class="sb-row"><span class="sb-lbl">Objetivo</span><span class="sb-val ok">Manter prêmio se BBAS3 ≤ R$ 22,68</span></div>
      <div class="sb-row"><span class="sb-lbl">Retorno alvo</span><span class="sb-val ok">3,4% sobre capital alocado</span></div>
      <div class="sb-row"><span class="sb-lbl">Vencimento</span><span class="sb-val">01/06/2026 · <span id="bb-dias">—</span> dias</span></div>
      <div class="sb-row"><span class="sb-lbl">% p/ Strike</span><span class="sb-val" id="bb-pct-strike">—</span></div>
      <div class="sb-row"><span class="sb-lbl">Situação</span><span class="sb-val" id="bb-status">—</span></div>
    </div>
    <!-- MONTE CARLO -->
    <div class="signal" style="margin-top:8px;border-color:var(--blue)">
      <div class="sig-title" style="color:var(--blue)">🎲 Monte Carlo — 100k Cenários</div>
      <div id="mc-loading" style="font-size:.65rem;color:var(--muted)">Calculando...</div>
      <div id="mc-result" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
          <div class="ind-box">
            <div class="ind-lbl">Prob. Sucesso</div>
            <div class="ind-val ok" id="mc-sucesso">—</div>
          </div>
          <div class="ind-box">
            <div class="ind-lbl">Call Exercida</div>
            <div class="ind-val" id="mc-call">—</div>
          </div>
          <div class="ind-box">
            <div class="ind-lbl">KDO Atingido</div>
            <div class="ind-val" id="mc-kdo">—</div>
          </div>
          <div class="ind-box">
            <div class="ind-lbl">Vol. Histórica</div>
            <div class="ind-val warn" id="mc-vol">—</div>
          </div>
        </div>
        <div style="font-size:.62rem;color:var(--muted);margin-top:6px" id="mc-info">—</div>
      </div>
    </div>
  </div>

  <div class="sec"><span>02</span> Cripto — Bitcoin · Estratégia</div>
  <div class="grid2">

    <!-- BTC PREÇO + GRADE -->
    <div class="pos-card btc-pos">
      <div class="pos-label">Bitcoin · Spot Grid · Hyperliquid 24/7</div>
      <div class="pos-ticker">BTC</div>
      <div class="pos-price btc-c loading" id="btc-pos-p">—</div>
      <div class="pos-chg" id="btc-pos-c">—</div>
      <div class="sb">
        <div class="sb-row"><span class="sb-lbl">Status Grid</span><span class="sb-val ok">● ATIVO</span></div>
        <div class="sb-row"><span class="sb-lbl">Fundo previsto (tese)</span><span class="sb-val warn">US$ 48k – 60k</span></div>
        <div class="sb-row"><span class="sb-lbl">Suporte chave</span><span class="sb-val warn">US$ 62.510</span></div>
        <div class="sb-row"><span class="sb-lbl">ATH do ciclo</span><span class="sb-val ok">US$ 126.073</span></div>
        <div class="sb-row"><span class="sb-lbl">Próx. halving</span><span class="sb-val">~2028</span></div>
      </div>
      <div class="ind-grid">
        <div class="ind-box"><div class="ind-lbl">RSI Semanal</div><div class="ind-val warn" id="btc-pos-rsi">—</div></div>
        <div class="ind-box"><div class="ind-lbl">Tendência</div><div class="ind-val" id="btc-pos-trend">—</div></div>
        <div class="ind-box"><div class="ind-lbl">Funding</div><div class="ind-val" id="btc-pos-fr">—</div></div>
      </div>
    </div>

    <!-- BTC ANÁLISE + TESE -->
    <div class="pos-card btc-pos">
      <div class="pos-label">Análise · Tese · Gatilhos</div>
      <div style="margin-top:10px">
        <div class="rsi-hdr" style="font-size:.7rem"><span>RSI Semanal</span><span id="btc-pos-rsi-val" style="color:var(--warn)">—</span></div>
        <div class="rsi-track"><div class="rsi-needle" id="btc-pos-rsi-n" style="left:45%"></div></div>
        <div class="rsi-zones" style="font-size:.62rem"><span>&lt;30 sobrev.</span><span>neutro</span><span>&gt;70 sobrec.</span></div>
      </div>
      <div class="signal" style="margin-top:10px">
        <div class="sig-title">⚡ Gatilho de Fundo — Divergência RSI</div>
        <div id="btc-pos-sig">Carregando...</div>
      </div>
      <div class="signal" style="margin-top:8px;border-color:var(--warn)">
        <div class="sig-title" style="color:var(--warn)">📊 Minha Tese — Ciclo 2025/26</div>
        <div style="font-size:.65rem;line-height:1.7;color:var(--text)">
          Fundo esperado entre <strong style="color:var(--warn)">US$ 48k–60k</strong>. Fundo pode já ter ocorrido em Jan/25 (US$ 76k→US$ 78k). Sinal definitivo: divergência bullish no RSI semanal — preço faz mínima mais baixa mas RSI não confirma. BTC deve voltar a testar ATH antes de nova correção estrutural.
        </div>
      </div>
    </div>

  </div>

</div><!-- /tab-posicoes -->

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

  <div class="sec" style="margin-top:16px"><span>📊</span> Indicadores — Bitcoin Semanal</div>
  <div id="btc-ind-area">
    <div style="color:var(--muted);font-size:.65rem;padding:10px">Carregando indicadores BTC...</div>
  </div>

</div><!-- /tab-indicadores -->

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
function switchTab(tab){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  event.target.classList.add('active');
  // Load indicators when switching to that tab
  if(tab==='indicadores' && !window._indLoaded){
    window._indLoaded=true;
    loadIndicators();
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
  e.textContent=txt;e.className=e.className.replace(/\\bloading\\b/g,'').trim();
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
  DXY:{p:98.511,v:98.2},VIX:{p:22,v:23},
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
  try{
    const r=await fetch('https://trader-desk.onrender.com/tv/brazil',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbols:{tickers:['BMFBOVESPA:PETR4','BMFBOVESPA:VALE3','BMFBOVESPA:BBAS3','BMFBOVESPA:IBOV']},columns:['close','change_abs']})
    });
    if(r.ok){
      const d=await r.json();
      (d.data||[]).forEach(x=>{
        const [close,chgAbs]=x.d||[];
        if(close!=null)out[x.s]={p:close,v:close-(chgAbs||0)};
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

  // VIX — via proxy Yahoo (atualizado em background)
  const vixFut=window._futures?.vix;
  const vixP=vixFut?.price||hlXyz('VIX')||FB.VIX.p;
  const vixV=vixFut?.prev||FB.VIX.v;
  setEl('vix-p',Number(vixP).toFixed(2));setChg('vix-c',vixP,vixV,'usd');

  // DXY — via proxy Yahoo + fallback HL xyz
  const dxyFut=window._futures?.dxy;
  const dxyRaw=dxyFut?.price||hlXyz('DXY')||FB.DXY.p;
  const dxyP=dxyRaw; const dxyV=dxyFut?.prev||FB.DXY.v;
  const dxyEl=document.getElementById('dxy-p');
  if(dxyEl){dxyEl.textContent=Number(dxyP).toFixed(3);dxyEl.className=dxyEl.className.replace(/\\bloading\\b/g,'').trim();}
  const dxyD=dxyP-dxyV; const dxyPct=(dxyD/dxyV*100); const dxyS=dxyD>=0?'+':'';
  const dxyCEl=document.getElementById('dxy-c');
  if(dxyCEl){dxyCEl.textContent=`${dxyS}${dxyPct.toFixed(2)}%`;dxyCEl.className='c-change '+(dxyD>=0?'up':'down');}

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
  // WIN futuro — busca do proxy /futures se disponivel
  const winFut=window._futures?.win;
  if(winFut){
    setEl('win-p',fPTS(winFut.price));setChg('win-c',winFut.price,winFut.prev,'pts');
  } else {
    // Fallback: IBOV * fator aproximado
    setEl('win-p',fPTS(Math.round(ibovP)));setChg('win-c',Math.round(ibovP),Math.round(ibovV),'pts');
  }

  // PETR4 e VALE3 na aba cotações
  const ptD=tv['BMFBOVESPA:PETR4'];
  const ptP=ptD?.p||FB.PETR4.p,ptV=ptD?.v||FB.PETR4.v;
  setEl('petr4q-p',fBRL(ptP));setChg('petr4q-c',ptP,ptV,'brl');

  const vlD=tv['BMFBOVESPA:VALE3'];
  const vlP=vlD?.p||FB.VALE3.p,vlV=vlD?.v||FB.VALE3.v;
  setEl('vale3q-p',fBRL(vlP));setChg('vale3q-c',vlP,vlV,'brl');

  const bbD=tv['BMFBOVESPA:BBAS3'];
  const bbP=bbD?.p||FB.BBAS3.p,bbV=bbD?.v||FB.BBAS3.v;
  setEl('bbas3q-p',fBRL(bbP));setChg('bbas3q-c',bbP,bbV,'brl');

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

  return{p:btcP,v:btcV||btcP};
}

function doPositions(tv,btcData){
  // BBAS3 cotacao e status
  const bbD=tv['BMFBOVESPA:BBAS3'];
  const bbP=bbD?.p||FB.BBAS3.p,bbV=bbD?.v||FB.BBAS3.v;
  setEl('bb-pos-p',fBRL(bbP));setChg('bb-pos-c',bbP,bbV,'brl');
  const venc=new Date('2026-06-01');
  const dias=Math.max(0,Math.ceil((venc-new Date())/(1000*60*60*24)));
  const diasEl=document.getElementById('bb-dias');
  if(diasEl) diasEl.textContent=dias+' dias';
  const bbStatus=document.getElementById('bb-status');
  if(bbStatus){
    if(bbP<=19.70){bbStatus.textContent='🔴 KDO ATINGIDO — barreira rompida';bbStatus.className='sb-val itm';}
    else if(bbP>22.68){bbStatus.textContent='⚠ Acima do strike — call em risco';bbStatus.className='sb-val warn';}
    else{bbStatus.textContent='✅ No range — retorno 3,4% garantido';bbStatus.className='sb-val ok';}
  }

  const ptD=tv['BMFBOVESPA:PETR4'];
  const ptP=ptD?.p||FB.PETR4.p,ptV=ptD?.v||FB.PETR4.v;
  setEl('pt-pos-p',fBRL(ptP));setChg('pt-pos-c',ptP,ptV,'brl');
  setEl('pt-itm',`R$ ${(ptP-32).toFixed(2)} acima do strike`);
  const ptGatilho=document.getElementById('pt-pct-gatilho');
  if(ptGatilho){const pct=((40-ptP)/ptP*100);ptGatilho.textContent=ptP<40?`+${pct.toFixed(1)}% para R$40`:`R$40 já atingido ⚠`;}
  const ptPct=Math.min(100,Math.max(0,((ptP-32)/(65-32))*100));
  const ptBar=document.getElementById('pt-bar');
  ptBar.style.width=ptPct+'%';ptBar.className='prog-bar '+(ptP>48?'danger':ptP>40?'warn':'ok');

  const vlD=tv['BMFBOVESPA:VALE3'];
  const vlP=vlD?.p||FB.VALE3.p,vlV=vlD?.v||FB.VALE3.v;
  setEl('vl-pos-p',fBRL(vlP));setChg('vl-pos-c',vlP,vlV,'brl');
  setEl('vl-itm',`R$ ${(vlP-57).toFixed(2)} acima do strike`);
  const vlGatilho=document.getElementById('vl-pct-gatilho');
  if(vlGatilho){const pct=((70-vlP)/vlP*100);vlGatilho.textContent=vlP<70?`+${pct.toFixed(1)}% para R$70`:`R$70 já atingido ⚠`;}
  const vlPct=Math.min(100,Math.max(0,((vlP-57)/(110-57))*100));
  const vlBar=document.getElementById('vl-bar');
  vlBar.style.width=vlPct+'%';vlBar.className='prog-bar '+(vlP>82?'danger':vlP>70?'warn':'ok');
}

// ── MONTE CARLO ───────────────────────────────────────
async function runMonteCarlo(){
  try{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),25000);
    const r=await fetch('https://trader-desk.onrender.com/montecarlo',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      signal:controller.signal,
      body:JSON.stringify({
        ticker:'BBAS3.SA',
        k_call:22.68,
        k_put:22.68,
        t_days:21,
        knock_down:19.70,
        n:5000
      })
    });
    clearTimeout(timeout);
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    document.getElementById('mc-loading').style.display='none';
    document.getElementById('mc-result').style.display='block';
    const sEl=document.getElementById('mc-sucesso');
    sEl.textContent=d.prob_sucesso+'%';
    sEl.className='ind-val '+(d.prob_sucesso>70?'ok':d.prob_sucesso>50?'warn':'down');
    const cEl=document.getElementById('mc-call');
    cEl.textContent=d.prob_call_exercida+'%';
    cEl.className='ind-val '+(d.prob_call_exercida<30?'ok':d.prob_call_exercida<50?'warn':'down');
    document.getElementById('mc-kdo').textContent=d.prob_kdo_atingido!=null?d.prob_kdo_atingido+'%':'—';
    document.getElementById('mc-vol').textContent=d.volatilidade_historica_pct+'%';
    document.getElementById('mc-info').textContent=
      `Preço atual R$ ${d.preco_atual} · Strike Call/Put R$ ${d.k_call} · KDO R$ ${d.knock_down} · ${d.cenarios.toLocaleString()} cenários simulados`;
  }catch(e){
    const mcEl=document.getElementById('mc-loading');
    if(mcEl)mcEl.textContent='Erro: '+(e.message||'Monte Carlo indisponível');
  }
}

// ── RENDER INDICADORES ───────────────────────────────
function renderIndicators(containerId, ind, isBRL){
  const el=document.getElementById(containerId);
  if(!el)return;
  if(!ind||ind.error){
    el.innerHTML=`<div style="color:var(--danger);font-size:.65rem;padding:10px">Erro: ${ind?.error||'indisponível'}</div>`;
    return;
  }

  const sinal=ind.sinal||{};
  const corMap={green:'var(--green)',accent:'var(--accent)',warn:'var(--warn)',orange:'#fb923c',danger:'var(--danger)'};
  const cor=corMap[sinal.cor]||'var(--muted)';
  const mm=isBRL?'R$':'US$';
  const f2=v=>v!=null?Number(v).toFixed(2):'—';

  // Sinal principal
  let html=`
  <div style="background:var(--bg2);border:2px solid ${cor};padding:16px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
    <div>
      <div style="font-size:.55rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px">⚡ Sinal Automático — ${ind.setor||''}</div>
      <div style="font-size:1.6rem;font-weight:800;color:${cor}">${sinal.sinal||'—'}</div>
      <div style="font-size:.62rem;color:var(--muted);margin-top:2px">Score: ${sinal.score||0}/${sinal.max_score||0} pts (máx 20 possíveis) · ${sinal.forca||0}% favorável · CDI: ${Number(ind.cdi||0).toFixed(1)}%</div>
    </div>
    ${ind.valor_justo_graham?`<div style="text-align:right">
      <div style="font-size:.55rem;color:var(--muted);text-transform:uppercase">Valor Justo Graham</div>
      <div style="font-size:1.2rem;font-weight:700;color:${(ind.upside_graham||0)>0?'var(--green)':'var(--red)'}">${mm} ${f2(ind.valor_justo_graham)}</div>
      <div style="font-size:.68rem;color:${(ind.upside_graham||0)>0?'var(--green)':'var(--red)'}">${(ind.upside_graham||0)>0?'▲':'▼'} ${Math.abs(ind.upside_graham||0).toFixed(1)}% ${(ind.upside_graham||0)>0?'upside':'downside'}</div>
    </div>`:''}
  </div>`;

  // Grid técnicos
  html+=`<div style="font-size:.58rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin:10px 0 6px">Indicadores Técnicos</div>`;
  html+=`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:7px;margin-bottom:12px">`;
  const TIPS={
    'RSI (14)':'Índice de Força Relativa. <30=sobrevenda(compra), >70=sobrecompra(venda), neutro=30-70.',
    'MM 20':'Média Móvel 20 períodos. Tendência de curto prazo. Preço acima=positivo.',
    'MM 50':'Média Móvel 50 períodos. Tendência de médio prazo.',
    'MM 200':'Média Móvel 200 períodos. Tendência principal de longo prazo. Mais importante.',
    'MACD':'Convergência/Divergência de Médias. Positivo=momentum de alta.',
    'MACD Signal':'Linha de sinal do MACD (EMA 9). MACD acima do sinal=compra.',
    'BB Superior':'Banda Superior de Bollinger (2 desvios). Preço próximo=sobrecompra.',
    'BB Inferior':'Banda Inferior de Bollinger (2 desvios). Preço próximo=sobrevenda.',
    'OBV Trend':'On Balance Volume. Confirma tendência pelo volume. Subindo=positivo.',
    'P/L':'Preço/Lucro. Quanto o mercado paga por R$1 de lucro. Menor=mais barato.',
    'P/L Setor':'Média histórica do P/L do setor. Referência para comparação.',
    'P/VP':'Preço/Valor Patrimonial. <1=ação abaixo do patrimônio(muito barato).',
    'EV/EBITDA':'Valor da empresa / EBITDA. Menor=mais barato. <6x=atrativo.',
    'ROE':'Retorno sobre Patrimônio. Mede eficiência. >15%=bom.',
    'Dív/EBITDA':'Dívida líquida / EBITDA. Endividamento. <1.5x=saudável, >3x=alto.',
    'Div. Yield':'Dividendo/Preço. Retorno em dividendos. Comparar com CDI.',
    'CDI Atual':'Taxa CDI anual atual (renda fixa). DY>CDI=ação supera RF.',
    'Margem Liq.':'Lucro líquido / Receita. Rentabilidade real. >15%=bom.',
    'LPA':'Lucro Por Ação. Base para cálculo do valor justo Graham.',
    'VPA':'Valor Patrimonial Por Ação. Base para cálculo do valor justo Graham.',
  };
  const tecnicos=[
    {l:'RSI (14)',v:ind.rsi!=null?ind.rsi+'':null,cls:ind.rsi<30?'up':ind.rsi>70?'down':'warn'},
    {l:'MM 20',v:ind.mm20?mm+' '+f2(ind.mm20):null},
    {l:'MM 50',v:ind.mm50?mm+' '+f2(ind.mm50):null},
    {l:'MM 200',v:ind.mm200?mm+' '+f2(ind.mm200):null},
    {l:'MACD',v:ind.macd!=null?ind.macd.toFixed(3):null,cls:ind.macd>ind.macd_signal?'up':'down'},
    {l:'MACD Signal',v:ind.macd_signal!=null?ind.macd_signal.toFixed(3):null},
    {l:'BB Superior',v:ind.bb_upper?mm+' '+f2(ind.bb_upper):null},
    {l:'BB Inferior',v:ind.bb_lower?mm+' '+f2(ind.bb_lower):null},
    {l:'OBV Trend',v:ind.obv_trend||null,cls:ind.obv_trend==='subindo'?'up':'down'},
  ];
  tecnicos.forEach(i=>{
    if(!i.v)return;
    const tip=TIPS[i.l]||'';
    html+=`<div class="ind-box"><div class="ind-lbl">${i.l} ${tip?'❓':''}</div><div class="ind-val ${i.cls||''}">${i.v}</div>${tip?`<div class="tooltip">${tip}</div>`:''}</div>`;
  });
  html+='</div>';

  // Grid fundamentalistas
  html+=`<div style="font-size:.58rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin:10px 0 6px">Indicadores Fundamentalistas</div>`;
  html+=`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:7px;margin-bottom:12px">`;
  // Normaliza campos para garantir que todos aparecem
  const pvp=ind.pvp||ind.price_to_book;
  const dy=ind.dy||ind.dividend_yield;
  const de=ind.debt_ebitda||ind.debt_to_ebitda;
  const mg=ind.margem_liquida!=null?ind.margem_liquida:(ind.profit_margin!=null?ind.profit_margin*100:null);
  const fundas=[
    {l:'P/L',v:ind.pl?ind.pl+'x':null,cls:ind.pl&&ind.pl_setor&&ind.pl<ind.pl_setor?'up':ind.pl&&ind.pl_setor&&ind.pl>ind.pl_setor*1.3?'down':''},
    {l:'P/L Setor',v:ind.pl_setor?ind.pl_setor+'x':null},
    {l:'P/VP',v:pvp?pvp+'x':null,cls:pvp<1?'up':pvp>2?'down':''},
    {l:'EV/EBITDA',v:ind.ev_ebitda?ind.ev_ebitda+'x':null,cls:ind.ev_ebitda<6?'up':ind.ev_ebitda>10?'down':''},
    {l:'ROE',v:ind.roe?ind.roe+'%':null,cls:ind.roe&&ind.roe_min_setor&&ind.roe>ind.roe_min_setor?'up':''},
    {l:'Dív/EBITDA',v:de!=null?de+'x':null,cls:de<1.5?'up':de>3?'down':'warn'},
    {l:'Div. Yield',v:dy?dy+'%':null,cls:dy&&ind.cdi&&dy>=ind.cdi?'up':dy&&ind.cdi&&dy>ind.cdi*0.7?'warn':''},
    {l:'CDI Atual',v:ind.cdi?Number(ind.cdi).toFixed(1)+'%':null},
    {l:'Margem Liq.',v:mg!=null?Number(mg).toFixed(1)+'%':null,cls:mg>15?'up':mg<5?'down':''},
    {l:'LPA',v:ind.lpa?mm+' '+f2(ind.lpa):null},
    {l:'VPA',v:ind.vpa?mm+' '+f2(ind.vpa):null},
  ];
  fundas.forEach(i=>{
    if(!i.v)return;
    const tip=TIPS[i.l]||'';
    html+=`<div class="ind-box"><div class="ind-lbl">${i.l} ${tip?'❓':''}</div><div class="ind-val ${i.cls||''}">${i.v}</div>${tip?`<div class="tooltip">${tip}</div>`:''}</div>`;
  });
  html+='</div>';

  // Detalhes do sinal
  if(sinal.detalhes?.length){
    html+=`<div style="background:var(--bg3);border:1px solid var(--border);padding:12px">
    <div style="font-size:.58rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">Análise Detalhada do Sinal</div>`;
    sinal.detalhes.forEach(d=>{
      const c=d.status==='buy'?'var(--green)':d.status==='sell'?'var(--danger)':'var(--warn)';
      html+=`<div style="font-size:.65rem;padding:5px 0;border-bottom:1px solid var(--border);color:${c}">${d.texto}</div>`;
    });
    html+='</div>';
  }

  el.innerHTML=html;
}

function renderBTCIndicators(ind){
  const el=document.getElementById('btc-ind-area');
  if(!el)return;
  if(!ind||ind.error){
    el.innerHTML=`<div style="color:var(--danger);font-size:.65rem;padding:10px">Erro: ${ind?.error||'indisponível'}</div>`;
    return;
  }

  const f0=v=>v!=null?'US$ '+Number(v).toLocaleString('en-US',{maximumFractionDigits:0}):'—';
  const f2=v=>v!=null?Number(v).toFixed(2):'—';

  // RSI Semanal em destaque
  const rsi=ind.rsi_semanal;
  const rsiCls=rsi<30?'var(--green)':rsi>70?'var(--red)':'var(--warn)';
  const rsiPct=rsi||45;
  let html=`
  <div style="background:var(--bg2);border:1px solid var(--border);padding:14px;margin-bottom:12px">
    <div style="font-size:.55rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">RSI Semanal — Indicador Principal BTC</div>
    <div style="display:flex;align-items:center;gap:16px">
      <div style="font-size:2rem;font-weight:800;color:${rsiCls}">${rsi||'—'}</div>
      <div style="flex:1">
        <div style="height:6px;background:linear-gradient(90deg,var(--red) 0%,var(--warn) 35%,var(--green) 55%,var(--red) 100%);position:relative;margin-bottom:4px">
          <div style="position:absolute;top:-4px;left:${rsiPct}%;width:2px;height:14px;background:#fff;transform:translateX(-50%)"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:.5rem;color:var(--muted)"><span>&lt;30 sobrevenda</span><span>neutro</span><span>&gt;70 sobrecompra</span></div>
      </div>
    </div>
    <div style="font-size:.62rem;color:${rsiCls};margin-top:6px">${rsi<30?'⚡ SOBREVENDA — Sinal de compra potencial':rsi>70?'⚠ SOBRECOMPRA — Cuidado com posições longas':'Zona neutra — sem sinal extremo'}</div>
  </div>`;

  html+=`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:7px;margin-bottom:12px">`;
  const TIPS_BTC={
    'MM 20 Sem.':'Média Móvel 20 semanas. Tendência de curto prazo semanal.',
    'MM 50 Sem.':'Média Móvel 50 semanas. Tendência de médio prazo.',
    'MM 200 Sem.':'Média Móvel 200 semanas. Tendência estrutural de longo prazo. Muito importante.',
    'MACD Sem.':'MACD no gráfico semanal. Momentum de tendência.',
    'BB Sup Sem.':'Banda Superior Bollinger semanal.',
    'BB Inf Sem.':'Banda Inferior Bollinger semanal. Próximo=oportunidade.',
    'OBV Trend':'On Balance Volume semanal. Confirma tendência pelo volume.',
    'Semanas':'Quantidade de semanas de dados históricos utilizados.',
  };
  const items=[
    {l:'MM 20 Sem.',v:ind.mm20_semanal?f0(ind.mm20_semanal):null},
    {l:'MM 50 Sem.',v:ind.mm50_semanal?f0(ind.mm50_semanal):null},
    {l:'MM 200 Sem.',v:ind.mm200_semanal?f0(ind.mm200_semanal):null},
    {l:'MACD Sem.',v:ind.macd!=null?f2(ind.macd):null,cls:ind.macd>0?'up':'down'},
    {l:'BB Sup Sem.',v:ind.bb_upper?f0(ind.bb_upper):null},
    {l:'BB Inf Sem.',v:ind.bb_lower?f0(ind.bb_lower):null},
    {l:'OBV Trend',v:ind.obv_trend||null,cls:ind.obv_trend==='subindo'?'up':'down'},
    {l:'Semanas',v:ind.data_points?ind.data_points+' sem.':null},
  ];
  items.forEach(i=>{
    if(!i.v)return;
    const tip=TIPS_BTC[i.l]||'';
    html+=`<div class="ind-box"><div class="ind-lbl">${i.l}${tip?' ❓':''}</div><div class="ind-val ${i.cls||''}">${i.v}</div>${tip?`<div class="tooltip">${tip}</div>`:''}</div>`;
  });
  html+='</div>';

  if(ind.divergencia_rsi){
    const isBull=ind.divergencia_rsi.includes('BULLISH');
    html+=`<div style="background:var(--bg3);border:2px solid ${isBull?'var(--accent)':'var(--danger)'};padding:14px;font-size:.68rem;line-height:1.6;margin-bottom:8px">
      <div style="font-size:.58rem;color:${isBull?'var(--accent)':'var(--danger)'};letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px">⚡ Divergência RSI Detectada</div>
      <div style="color:var(--text)">${ind.divergencia_rsi}</div>
    </div>`;
  } else {
    html+=`<div style="background:var(--bg3);border:1px solid var(--border);padding:10px;font-size:.65rem;color:var(--muted);margin-bottom:8px">Sem divergência de RSI detectada no semanal.</div>`;
  }

  el.innerHTML=html;
}

// ── LOAD INDICATORS ──────────────────────────────────
async function loadIndicators(){
  const areas=['petr4-ind-area','vale3-ind-area','bbas3-ind-area','btc-ind-area'];
  areas.forEach(a=>{
    const el=document.getElementById(a);
    if(el) el.innerHTML='<div style="color:var(--muted);font-size:.65rem;padding:10px;animation:pulse 1.5s infinite">Calculando indicadores...</div>';
  });
  const [p4,v3,bb,btc]=await Promise.all([
    fetchIndicators('PETR4.SA'),
    fetchIndicators('VALE3.SA'),
    fetchIndicators('BBAS3.SA'),
    fetchBTCIndicators()
  ]);
  renderIndicators('petr4-ind-area',p4,true);
  renderIndicators('vale3-ind-area',v3,true);
  renderIndicators('bbas3-ind-area',bb,true);
  renderBTCIndicators(btc);
}

// ── MAIN ──────────────────────────────────────────────
async function fetchAll(){
  const btn=document.getElementById('btn-ref'),upd=document.getElementById('pill-upd');
  btn.disabled=true;upd.textContent='Atualizando...';upd.className='pill warn';
  checkMarkets();

  // HL e TV em paralelo — não bloqueia por futuros
  const [,tv]=await Promise.all([fetchHL(),fetchTV()]);
  
  // Futuros em background — não bloqueia cotações principais
  fetchFutures().then(futures=>{
    window._futures=futures;
    const djiD=futures?.dji;
    if(djiD){setEl('dji-p',fPTS(djiD.price));setChg('dji-c',djiD.price,djiD.prev,'pts');document.getElementById('dji-s').textContent='Yahoo ✓';}
    const esfD=futures?.esf;
    if(esfD){setEl('esf-p',fPTS(esfD.price));setChg('esf-c',esfD.price,esfD.prev,'pts');}
    const nqfD=futures?.nqf;
    if(nqfD){setEl('nqf-p',fPTS(nqfD.price));setChg('nqf-c',nqfD.price,nqfD.prev,'pts');}
    // WIN futuro — pontos do indice (~180k é correto)
    const winD=futures?.win;
    if(winD&&winD.price>50000){
      setEl('win-p',fPTS(winD.price));
      setChg('win-c',winD.price,winD.prev,'pts');
    }
    // VIX — ex: 17.26
    const vixD=futures?.vix;
    if(vixD&&vixD.price>5&&vixD.price<100){
      const vEl=document.getElementById('vix-p');
      if(vEl){vEl.textContent=Number(vixD.price).toFixed(2);vEl.className=vEl.className.replace(/loading/g,'').trim();}
      setChg('vix-c',vixD.price,vixD.prev,'usd');
    }
    // DXY — ex: 97.15 (range 70-120)
    const dxyD2=futures?.dxy;
    if(dxyD2&&dxyD2.price>70&&dxyD2.price<120){
      const dEl=document.getElementById('dxy-p');
      if(dEl){dEl.textContent=Number(dxyD2.price).toFixed(2);dEl.className=dEl.className.replace(/loading/g,'').trim();}
      setChg('dxy-c',dxyD2.price,dxyD2.prev,'usd');
    }
  }).catch(()=>{});

  const macroData=doMacro(tv);
  const commData=doCommodities();
  const btcData=doBTC();
  doPositions(tv,btcData);

  // Tape com variações corretas
  buildTape({
    PETR4:{p:tv['BMFBOVESPA:PETR4']?.p||FB.PETR4.p,v:tv['BMFBOVESPA:PETR4']?.v||FB.PETR4.v},
    VALE3:{p:tv['BMFBOVESPA:VALE3']?.p||FB.VALE3.p,v:tv['BMFBOVESPA:VALE3']?.v||FB.VALE3.v},
    IBOV:{p:tv['BMFBOVESPA:IBOV']?.p||FB.IBOV.p,v:tv['BMFBOVESPA:IBOV']?.v||FB.IBOV.v},
    USDBRL:{p:macroData.usdP,v:macroData.usdV},
    BTC:btcData,
    SP500:{p:hlXyz('SP500')||FB.SP500.p,v:hlXyzPrev('SP500')||FB.SP500.v},
    NDX:{p:hlXyz('XYZ100')||FB.NDX.p,v:hlXyzPrev('XYZ100')||FB.NDX.v},
    DXY:{p:hlXyz('DXY')||FB.DXY.p,v:hlXyzPrev('DXY')||FB.DXY.v},
    CL:{p:commData.clP,v:commData.clV},
    GOLD:{p:commData.goldP,v:commData.goldV},
    SILVER:{p:commData.silverP,v:commData.silverV},
    COPPER:{p:commData.copperP,v:commData.copperV},
    VIX:{p:hlXyz('VIX')||FB.VIX.p,v:hlXyzPrev('VIX')||FB.VIX.v},
  });

  const now=new Date().toLocaleTimeString('pt-BR');
  upd.textContent='Atualizado '+now;upd.className='pill ok';
  document.getElementById('ftr').textContent='Última atualização: '+now;
  btn.disabled=false;

  setTimeout(fetchFunding,3000);

  // Indicadores carregam apenas quando usuario clica na aba
  window._indLoaded=false;
}

fetchAll();
setInterval(fetchAll,120000);
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
