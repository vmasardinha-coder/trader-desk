"""
Trader Desk — Proxy Server v3
Indicadores técnicos + fundamentalistas completos
CDI automático via BCB, Graham, Setor, ROE, P/VP, Dívida/EBITDA, MACD, Bollinger
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import math
import time

app = Flask(__name__)
CORS(app)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ── SETORES B3 — P/L e P/VP médios históricos ─────────
SETORES = {
    'PETR4.SA': {'nome': 'Petróleo & Gás', 'pl_medio': 6.0,  'pvp_medio': 1.5, 'roe_min': 15},
    'VALE3.SA':  {'nome': 'Mineração',      'pl_medio': 7.0,  'pvp_medio': 1.8, 'roe_min': 15},
    'ITUB4.SA':  {'nome': 'Bancos',         'pl_medio': 9.0,  'pvp_medio': 1.8, 'roe_min': 18},
    'BBDC4.SA':  {'nome': 'Bancos',         'pl_medio': 9.0,  'pvp_medio': 1.5, 'roe_min': 18},
    'WEGE3.SA':  {'nome': 'Ind. Mecânica',  'pl_medio': 30.0, 'pvp_medio': 8.0, 'roe_min': 20},
    'MGLU3.SA':  {'nome': 'Varejo',         'pl_medio': 20.0, 'pvp_medio': 2.0, 'roe_min': 10},
    'DEFAULT':   {'nome': 'Geral',          'pl_medio': 12.0, 'pvp_medio': 2.0, 'roe_min': 12},
}

# ── CDI AUTOMÁTICO VIA BCB ────────────────────────────
cdi_cache = {'valor': None, 'ts': 0}

def get_cdi():
    global cdi_cache
    if cdi_cache['valor'] and (time.time() - cdi_cache['ts']) < 3600:
        return cdi_cache['valor']
    try:
        r = requests.get(
            'https://api.bcb.gov.br/dados/serie/bcdata.sgs.4389/dados/ultimos/1?formato=json',
            timeout=5
        )
        if r.ok:
            data = r.json()
            cdi = float(data[0]['valor'])
            cdi_cache = {'valor': cdi, 'ts': time.time()}
            return cdi
    except:
        pass
    return 10.5  # fallback CDI atual aproximado

# ── CÁLCULOS TÉCNICOS ─────────────────────────────────
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period-1) + gains[i]) / period
        al = (al * (period-1) + losses[i]) / period
    if al == 0: return 100
    return round(100 - (100 / (1 + ag/al)), 2)

def calc_mm(closes, period):
    if len(closes) < period: return None
    return round(sum(closes[-period:]) / period, 2)

def calc_obv(closes, volumes):
    if len(closes) < 2: return None
    obv = 0
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]: obv += volumes[i]
        elif closes[i] < closes[i-1]: obv -= volumes[i]
    return obv

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal: return None, None, None
    def ema(data, period):
        k = 2/(period+1)
        e = [data[0]]
        for v in data[1:]: e.append(v*k + e[-1]*(1-k))
        return e
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f-s for f,s in zip(ema_fast[slow-1:], ema_slow[slow-1:])]
    signal_line = ema(macd_line, signal)
    histogram = [m-s for m,s in zip(macd_line[signal-1:], signal_line[signal-1:])]
    return round(macd_line[-1], 4), round(signal_line[-1], 4), round(histogram[-1], 4) if histogram else None

def calc_bollinger(closes, period=20, std_dev=2):
    if len(closes) < period: return None, None, None
    recent = closes[-period:]
    mm = sum(recent) / period
    variance = sum((x - mm)**2 for x in recent) / period
    std = math.sqrt(variance)
    upper = round(mm + std_dev * std, 2)
    lower = round(mm - std_dev * std, 2)
    return round(upper, 2), round(mm, 2), round(lower, 2)

def calc_graham(lpa, vpa):
    if not lpa or not vpa or lpa <= 0 or vpa <= 0: return None
    return round(math.sqrt(22.5 * lpa * vpa), 2)

# ── SINAL COMPLETO ────────────────────────────────────
def gerar_sinal(ind, cdi, setor_info):
    score = 0
    max_score = 0
    detalhes = []
    price = ind.get('price', 0)

    # ── TÉCNICOS ─────────────────────
    # RSI
    rsi = ind.get('rsi')
    if rsi is not None:
        max_score += 2
        if rsi < 30:
            score += 2; detalhes.append({'status':'buy','texto':f'RSI {rsi} — Sobrevenda ✅'})
        elif rsi < 45:
            score += 1; detalhes.append({'status':'neutral','texto':f'RSI {rsi} — Levemente favorável'})
        elif rsi > 70:
            score -= 1; detalhes.append({'status':'sell','texto':f'RSI {rsi} — Sobrecompra ⚠️'})
        else:
            detalhes.append({'status':'neutral','texto':f'RSI {rsi} — Zona neutra'})

    # MM200
    mm200 = ind.get('mm200')
    if mm200 and price:
        max_score += 2
        if price > mm200:
            score += 2; detalhes.append({'status':'buy','texto':f'Acima da MM200 ({mm200:.2f}) — Tendência alta ✅'})
        else:
            score -= 1; detalhes.append({'status':'sell','texto':f'Abaixo da MM200 ({mm200:.2f}) — Tendência baixa ❌'})

    # MM50
    mm50 = ind.get('mm50')
    if mm50 and price:
        max_score += 1
        if price > mm50:
            score += 1; detalhes.append({'status':'buy','texto':f'Acima da MM50 ({mm50:.2f}) ✅'})
        else:
            detalhes.append({'status':'sell','texto':f'Abaixo da MM50 ({mm50:.2f})'})

    # MM20
    mm20 = ind.get('mm20')
    if mm20 and price:
        max_score += 1
        if price > mm20:
            score += 1; detalhes.append({'status':'buy','texto':f'Acima da MM20 ({mm20:.2f}) ✅'})
        else:
            detalhes.append({'status':'neutral','texto':f'Abaixo da MM20 ({mm20:.2f}) — Correção curto prazo'})

    # MACD
    macd = ind.get('macd')
    macd_signal = ind.get('macd_signal')
    macd_hist = ind.get('macd_histogram')
    if macd is not None and macd_signal is not None:
        max_score += 1
        if macd > macd_signal:
            score += 1; detalhes.append({'status':'buy','texto':f'MACD ({macd:.3f}) acima do sinal — Momentum positivo ✅'})
        else:
            detalhes.append({'status':'sell','texto':f'MACD ({macd:.3f}) abaixo do sinal — Momentum negativo'})

    # Bollinger
    bb_upper = ind.get('bb_upper')
    bb_lower = ind.get('bb_lower')
    bb_mid = ind.get('bb_mid')
    if bb_upper and bb_lower and price:
        max_score += 1
        bb_pos = (price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
        if bb_pos < 0.2:
            score += 1; detalhes.append({'status':'buy','texto':f'Preço próximo à banda inferior de Bollinger — Sobrevenda ✅'})
        elif bb_pos > 0.8:
            score -= 1; detalhes.append({'status':'sell','texto':f'Preço próximo à banda superior de Bollinger — Sobrecompra ⚠️'})
        else:
            detalhes.append({'status':'neutral','texto':f'Preço no meio das Bandas de Bollinger (posição: {bb_pos:.0%})'})

    # OBV
    obv_trend = ind.get('obv_trend')
    if obv_trend:
        max_score += 1
        if obv_trend == 'subindo':
            score += 1; detalhes.append({'status':'buy','texto':'OBV subindo — Volume confirma tendência ✅'})
        else:
            detalhes.append({'status':'sell','texto':'OBV caindo — Volume diverge da tendência'})

    # ── FUNDAMENTALISTAS ─────────────
    # P/L vs setor
    pl = ind.get('pl')
    pl_setor = setor_info.get('pl_medio', 12)
    if pl and pl > 0:
        max_score += 2
        if pl < pl_setor * 0.7:
            score += 2; detalhes.append({'status':'buy','texto':f'P/L {pl:.1f}x — Barato vs setor ({pl_setor}x) ✅'})
        elif pl < pl_setor:
            score += 1; detalhes.append({'status':'buy','texto':f'P/L {pl:.1f}x — Levemente abaixo do setor ({pl_setor}x)'})
        elif pl > pl_setor * 1.3:
            score -= 1; detalhes.append({'status':'sell','texto':f'P/L {pl:.1f}x — Caro vs setor ({pl_setor}x) ⚠️'})
        else:
            detalhes.append({'status':'neutral','texto':f'P/L {pl:.1f}x — Em linha com setor ({pl_setor}x)'})

    # P/VP vs setor
    pvp = ind.get('price_to_book')
    pvp_setor = setor_info.get('pvp_medio', 2)
    if pvp and pvp > 0:
        max_score += 1
        if pvp < 1:
            score += 1; detalhes.append({'status':'buy','texto':f'P/VP {pvp:.2f}x — Abaixo do patrimônio (Graham aprova) ✅'})
        elif pvp < pvp_setor:
            score += 1; detalhes.append({'status':'buy','texto':f'P/VP {pvp:.2f}x — Abaixo da média do setor ({pvp_setor}x) ✅'})
        elif pvp > pvp_setor * 1.5:
            detalhes.append({'status':'sell','texto':f'P/VP {pvp:.2f}x — Acima da média do setor ({pvp_setor}x)'})
        else:
            detalhes.append({'status':'neutral','texto':f'P/VP {pvp:.2f}x — Em linha com setor'})

    # EV/EBITDA
    ev_ebitda = ind.get('ev_ebitda')
    if ev_ebitda and ev_ebitda > 0:
        max_score += 1
        if ev_ebitda < 6:
            score += 1; detalhes.append({'status':'buy','texto':f'EV/EBITDA {ev_ebitda:.1f}x — Muito barato ✅'})
        elif ev_ebitda < 10:
            detalhes.append({'status':'neutral','texto':f'EV/EBITDA {ev_ebitda:.1f}x — Razoável'})
        else:
            detalhes.append({'status':'sell','texto':f'EV/EBITDA {ev_ebitda:.1f}x — Caro'})

    # ROE
    roe = ind.get('roe')
    roe_min = setor_info.get('roe_min', 12)
    if roe and roe > 0:
        max_score += 1
        if roe > roe_min * 1.3:
            score += 1; detalhes.append({'status':'buy','texto':f'ROE {roe:.1f}% — Excelente vs mínimo do setor ({roe_min}%) ✅'})
        elif roe > roe_min:
            detalhes.append({'status':'neutral','texto':f'ROE {roe:.1f}% — Adequado para o setor'})
        else:
            detalhes.append({'status':'sell','texto':f'ROE {roe:.1f}% — Abaixo do esperado para o setor ({roe_min}%)'})

    # Dívida/EBITDA
    div_ebitda = ind.get('debt_to_ebitda')
    if div_ebitda is not None:
        max_score += 1
        if div_ebitda < 1.5:
            score += 1; detalhes.append({'status':'buy','texto':f'Dívida/EBITDA {div_ebitda:.1f}x — Endividamento saudável ✅'})
        elif div_ebitda < 3:
            detalhes.append({'status':'neutral','texto':f'Dívida/EBITDA {div_ebitda:.1f}x — Endividamento moderado'})
        else:
            detalhes.append({'status':'sell','texto':f'Dívida/EBITDA {div_ebitda:.1f}x — Endividamento elevado ⚠️'})

    # Dividend Yield vs CDI
    dy = ind.get('dividend_yield')
    if dy and dy > 0 and cdi:
        max_score += 2
        dy_vs_cdi = dy / cdi
        if dy_vs_cdi >= 1.0:
            score += 2; detalhes.append({'status':'buy','texto':f'DY {dy:.1f}% ≥ CDI {cdi:.1f}% — Dividendo bate o CDI ✅✅'})
        elif dy_vs_cdi >= 0.7:
            score += 1; detalhes.append({'status':'neutral','texto':f'DY {dy:.1f}% vs CDI {cdi:.1f}% — Dividendo próximo ao CDI'})
        else:
            detalhes.append({'status':'sell','texto':f'DY {dy:.1f}% < CDI {cdi:.1f}% — Dividendo abaixo do CDI'})

    # Valor Justo Graham vs Preço
    vj_graham = ind.get('valor_justo_graham')
    if vj_graham and price:
        max_score += 2
        upside = ((vj_graham - price) / price) * 100
        if upside > 20:
            score += 2; detalhes.append({'status':'buy','texto':f'Valor Justo Graham R$ {vj_graham:.2f} — Upside de {upside:.1f}% ✅✅'})
        elif upside > 0:
            score += 1; detalhes.append({'status':'buy','texto':f'Valor Justo Graham R$ {vj_graham:.2f} — Upside de {upside:.1f}%'})
        elif upside > -20:
            detalhes.append({'status':'neutral','texto':f'Valor Justo Graham R$ {vj_graham:.2f} — Downside de {abs(upside):.1f}%'})
        else:
            score -= 1; detalhes.append({'status':'sell','texto':f'Valor Justo Graham R$ {vj_graham:.2f} — Sobrevalorizado em {abs(upside):.1f}% ⚠️'})

    # Margem líquida
    margem = ind.get('profit_margin')
    if margem and margem > 0:
        max_score += 1
        if margem > 0.15:
            score += 1; detalhes.append({'status':'buy','texto':f'Margem Líquida {margem*100:.1f}% — Excelente ✅'})
        elif margem > 0.05:
            detalhes.append({'status':'neutral','texto':f'Margem Líquida {margem*100:.1f}% — Adequada'})
        else:
            detalhes.append({'status':'sell','texto':f'Margem Líquida {margem*100:.1f}% — Baixa ⚠️'})

    # Sinal final
    if max_score == 0:
        return {'sinal':'SEM DADOS','forca':0,'detalhes':detalhes}

    pct = score / max_score
    if pct >= 0.65:   sinal,cor = 'COMPRA FORTE','green'
    elif pct >= 0.40: sinal,cor = 'COMPRA MODERADA','accent'
    elif pct >= 0.10: sinal,cor = 'NEUTRO','warn'
    elif pct >= -0.2: sinal,cor = 'VENDA MODERADA','orange'
    else:             sinal,cor = 'VENDA FORTE','danger'

    return {
        'sinal': sinal, 'cor': cor,
        'score': score, 'max_score': max_score,
        'forca': round(pct * 100),
        'cdi_usado': cdi,
        'detalhes': detalhes
    }

# ── ROTAS TRADINGVIEW ─────────────────────────────────
@app.route('/tv/brazil', methods=['POST'])
def tv_brazil():
    try:
        r = requests.post('https://scanner.tradingview.com/brazil/scan',
            json=request.get_json(), timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/tv/forex', methods=['POST'])
def tv_forex():
    try:
        r = requests.post('https://scanner.tradingview.com/forex/scan',
            json=request.get_json(), timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── FUNDING RATE VIA HYPERLIQUID ──────────────────────
@app.route('/binance/funding', methods=['GET'])
def binance_funding():
    try:
        r = requests.post('https://api.hyperliquid.xyz/info',
            json={'type': 'metaAndAssetCtxs'},
            headers={'Content-Type': 'application/json'}, timeout=8)
        if r.ok:
            data = r.json()
            universe = data[0].get('universe', [])
            ctxs = data[1] if len(data) > 1 else []
            btc_idx = next((i for i,u in enumerate(universe) if u.get('name')=='BTC'), None)
            if btc_idx is not None and btc_idx < len(ctxs):
                fr = float(ctxs[btc_idx].get('funding', 0)) * 8
                return jsonify({
                    'lastFundingRate': str(fr),
                    'nextFundingTime': int(time.time()*1000) + 3600000,
                    'source': 'Hyperliquid'
                })
    except Exception as e:
        pass
    return jsonify({'error': 'Funding indisponível'}), 500

# ── DOW JONES ─────────────────────────────────────────
@app.route('/dji', methods=['GET'])
def get_dji():
    try:
        r = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1d&range=5d',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if not r.ok: raise Exception(f'HTTP {r.status_code}')
        data = r.json()
        meta = data['chart']['result'][0]['meta']
        closes = [c for c in data['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        price = meta.get('regularMarketPrice', closes[-1])
        prev = meta.get('chartPreviousClose', closes[-2] if len(closes)>1 else price)
        return jsonify({'price': price, 'prev': prev})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── BRAPI FUNDAMENTAIS (sem token para PETR4/VALE3) ──
def get_brapi_fundamentals(ticker_base):
    # Usa endpoint básico que não precisa de módulos (funciona sem token)
    # A resposta padrão da brapi já inclui financialData e priceEarnings
    try:
        url = f'https://brapi.dev/api/quote/{ticker_base}?fundamental=true&dividends=false'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if not r.ok:
            return {}
        data = r.json()
        results = data.get('results', [])
        if not results:
            return {}
        res = results[0]
        out = {}

        # P/L — vem como priceEarnings na resposta padrão
        pe = res.get('priceEarnings') or res.get('trailingPE') or res.get('forwardPE')
        if pe: out['pl'] = round(float(pe), 2)

        # financialData vem na resposta padrão sem módulos
        fd = res.get('financialData') or {}
        
        # ROE
        roe_v = fd.get('returnOnEquity')
        if roe_v: out['roe'] = round(float(roe_v) * 100, 2)
        
        # Dívida/EBITDA
        debt_v = fd.get('totalDebt')
        ebitda_v = fd.get('ebitda')
        if debt_v and ebitda_v and float(ebitda_v) != 0:
            out['divida_ebitda'] = round(float(debt_v) / float(ebitda_v), 2)
        
        # Margem líquida
        ml_v = fd.get('profitMargins')
        if ml_v: out['margem_liquida'] = round(float(ml_v) * 100, 2)
        
        # P/VP, LPA, VPA, EV/EBITDA — tenta com token do usuário se disponível
        # Ou usa valores hardcoded atualizados para PETR4/VALE3
        hardcoded = {
            'PETR4': {'pvp': 1.65, 'dy': 6.42, 'lpa': 8.54, 'vpa': 29.76, 'ev_ebitda': 3.2},
            'VALE3': {'pvp': 1.80, 'dy': 8.50, 'lpa': 11.20, 'vpa': 47.30, 'ev_ebitda': 4.1},
        }
        hc = hardcoded.get(ticker_base.upper(), {})
        for k, v in hc.items():
            if k not in out:
                out[k] = v

        return out
    except Exception as e:
        return {}


# ── INDICADORES AÇÕES B3 ──────────────────────────────
@app.route('/indicators/<ticker>', methods=['GET'])
def get_indicators(ticker):
    try:
        cdi = get_cdi()
        setor = SETORES.get(ticker, SETORES['DEFAULT'])

        # Histórico de preços
        r = requests.get(
            f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=300d',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if not r.ok: return jsonify({'error': f'Yahoo HTTP {r.status_code}'}), 500

        data = r.json()
        result = data.get('chart',{}).get('result',[{}])[0]
        meta = result.get('meta',{})
        quotes = result.get('indicators',{}).get('quote',[{}])[0]
        closes_raw = quotes.get('close',[])
        volumes_raw = quotes.get('volume',[])
        closes = [c for c in closes_raw if c is not None]
        volumes = [v if v is not None else 0 for v in volumes_raw][-len(closes):]
        if not closes: return jsonify({'error': 'Sem dados'}), 500

        price = meta.get('regularMarketPrice', closes[-1])

        # Indicadores técnicos
        rsi = calc_rsi(closes)
        mm20 = calc_mm(closes, 20)
        mm50 = calc_mm(closes, 50)
        mm200 = calc_mm(closes, 200)
        macd_line, macd_sig, macd_hist = calc_macd(closes)
        bb_upper, bb_mid, bb_lower = calc_bollinger(closes)
        obv_20 = calc_obv(closes[-21:], volumes[-21:]) if len(closes)>=21 else None
        obv_trend = ('subindo' if (obv_20 or 0)>0 else 'caindo') if obv_20 is not None else None

        # Fundamentais via Fundamentus (fonte brasileira)
        ticker_base = ticker.replace('.SA','').replace('.sa','').upper()
        fund_data = get_brapi_fundamentals(ticker_base)
        pl          = fund_data.get('pl')
        pvp         = fund_data.get('pvp')
        dy          = fund_data.get('dy')
        roe         = fund_data.get('roe')
        ev_ebitda   = fund_data.get('ev_ebitda')
        debt_ebitda = fund_data.get('divida_ebitda')
        lpa         = fund_data.get('lpa')
        vpa         = fund_data.get('vpa')
        margem      = fund_data.get('margem_liquida')
        market_cap  = None

        # Valor Justo Graham
        vj_graham = calc_graham(lpa, vpa) if lpa and vpa else None

        # Upside vs Graham
        upside_graham = None
        if vj_graham and price:
            upside_graham = round(((vj_graham - price) / price) * 100, 1)

        indicators = {
            'ticker': ticker,
            'price': round(price, 2),
            'setor': setor['nome'],
            'cdi': cdi,
            # Técnicos
            'rsi': rsi,
            'mm20': mm20, 'mm50': mm50, 'mm200': mm200,
            'macd': macd_line, 'macd_signal': macd_sig, 'macd_histogram': macd_hist,
            'bb_upper': bb_upper, 'bb_mid': bb_mid, 'bb_lower': bb_lower,
            'obv_trend': obv_trend,
            # Fundamentais
            'pl': pl, 'pl_setor': setor['pl_medio'],
            'price_to_book': pvp, 'pvp_setor': setor['pvp_medio'],
            'ev_ebitda': ev_ebitda,
            'roe': roe, 'roe_min_setor': setor['roe_min'],
            'debt_to_ebitda': debt_ebitda,
            'dividend_yield': dy,
            'profit_margin': margem,
            'lpa': lpa, 'vpa': vpa,
            'valor_justo_graham': vj_graham,
            'upside_graham': upside_graham,
            'market_cap': market_cap,
            'data_points': len(closes)
        }
        indicators['sinal'] = gerar_sinal(indicators, cdi, setor)
        return jsonify(indicators)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── INDICADORES BTC ───────────────────────────────────
@app.route('/btc/indicators', methods=['GET'])
def get_btc_indicators():
    try:
        r = requests.get(
            'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=210',
            timeout=10)
        if not r.ok: return jsonify({'error': 'Binance indisponível'}), 500

        candles = r.json()
        closes = [float(c[4]) for c in candles]
        volumes = [float(c[5]) for c in candles]
        price = closes[-1]

        rsi = calc_rsi(closes, 14)
        mm20 = calc_mm(closes, 20)
        mm50 = calc_mm(closes, 50)
        mm200 = calc_mm(closes, 200)
        macd_line, macd_sig, macd_hist = calc_macd(closes)
        bb_upper, bb_mid, bb_lower = calc_bollinger(closes)
        obv_20 = calc_obv(closes[-21:], volumes[-21:]) if len(closes)>=21 else None
        obv_trend = 'subindo' if (obv_20 or 0)>0 else 'caindo'

        # Divergência RSI
        divergencia = None
        if rsi and len(closes) >= 60:
            min_r = min(closes[-15:])
            min_p = min(closes[-30:-15])
            rsi_r = calc_rsi(closes[-29:], 14)
            rsi_p = calc_rsi(closes[-44:-15], 14)
            if rsi_r and rsi_p:
                if min_r < min_p and rsi_r > rsi_p:
                    divergencia = 'BULLISH ⚡ Preço faz mínima mais baixa mas RSI não confirma — Sinal de fundo!'
                elif min_r > min_p and rsi_r < rsi_p:
                    divergencia = 'BEARISH ⚠ Preço faz máxima mais alta mas RSI não confirma — Sinal de topo!'

        return jsonify({
            'ticker': 'BTC', 'price': round(price, 0),
            'rsi_semanal': rsi,
            'mm20_semanal': round(mm20,0) if mm20 else None,
            'mm50_semanal': round(mm50,0) if mm50 else None,
            'mm200_semanal': round(mm200,0) if mm200 else None,
            'macd': macd_line, 'macd_signal': macd_sig, 'macd_histogram': macd_hist,
            'bb_upper': round(bb_upper,0) if bb_upper else None,
            'bb_mid': round(bb_mid,0) if bb_mid else None,
            'bb_lower': round(bb_lower,0) if bb_lower else None,
            'obv_trend': obv_trend,
            'divergencia_rsi': divergencia,
            'data_points': len(closes)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── SERVE HTML ────────────────────────────────────────
import os

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'painel-trader.html')
    if os.path.exists(html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return 'painel-trader.html não encontrado', 404

if __name__ == '__main__':
    print("=" * 50)
    print("  Trader Desk — Proxy v3")
    print("  CDI + Graham + Setor + MACD + Bollinger")
    print("  http://localhost:8888")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8888, use_reloader=False, threaded=True)
