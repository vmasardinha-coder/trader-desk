"""
Trader Desk — Proxy Server v3
Indicadores técnicos + fundamentalistas + sinal combinado
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import math
import time

app = Flask(__name__)
CORS(app)

import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── SETORES E P/L MÉDIO HISTÓRICO ─────────────────────
SETORES = {
    'PETR4.SA': {'nome': 'Petróleo & Gás', 'pl_medio': 6.5,  'pvp_medio': 1.8, 'roe_medio': 18},
    'VALE3.SA': {'nome': 'Mineração',       'pl_medio': 7.0,  'pvp_medio': 2.0, 'roe_medio': 20},
}
SETOR_DEFAULT = {'nome': 'Geral', 'pl_medio': 12.0, 'pvp_medio': 2.0, 'roe_medio': 15}

# ── TRADINGVIEW ───────────────────────────────────────
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

# ── DOW JONES ─────────────────────────────────────────
@app.route('/dji', methods=['GET'])
def get_dji():
    try:
        r = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1d&range=5d',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if not r.ok:
            return jsonify({'error': f'HTTP {r.status_code}'}), 500
        data = r.json()
        meta = data['chart']['result'][0]['meta']
        closes = [c for c in data['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        price = meta.get('regularMarketPrice', closes[-1])
        prev = meta.get('chartPreviousClose', closes[-2] if len(closes) > 1 else price)
        return jsonify({'price': price, 'prev': prev})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── FUNDING RATE via Hyperliquid ──────────────────────
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
            btc_idx = next((i for i, u in enumerate(universe) if u.get('name') == 'BTC'), None)
            if btc_idx is not None and btc_idx < len(ctxs):
                fr = float(ctxs[btc_idx].get('funding', 0)) * 8
                return jsonify({
                    'lastFundingRate': str(fr),
                    'nextFundingTime': int(time.time() * 1000) + 3600000,
                    'source': 'Hyperliquid'
                })
    except Exception as e:
        pass
    return jsonify({'error': 'Funding indisponível'}), 500

# ── CDI ATUAL VIA BANCO CENTRAL ───────────────────────
def get_cdi():
    try:
        r = requests.get(
            'https://api.bcb.gov.br/dados/serie/bcdata.sgs.4389/dados/ultimos/1?formato=json',
            timeout=5)
        if r.ok:
            data = r.json()
            if data:
                # CDI diário — converte para anual: (1 + cdi_diario/100)^252 - 1
                cdi_diario = float(data[0]['valor'])
                cdi_anual = ((1 + cdi_diario/100) ** 252 - 1) * 100
                return round(cdi_anual, 2)
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
    if al == 0:
        return 100.0
    return round(100 - (100 / (1 + ag/al)), 2)

def calc_mm(closes, period):
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)

def calc_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return round(ema, 2)

def calc_macd(closes):
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    if ema12 is None or ema26 is None:
        return None, None, None
    macd_line = round(ema12 - ema26, 2)
    # Signal line (EMA9 do MACD) — simplificado
    if len(closes) >= 35:
        macd_series = []
        for i in range(26, len(closes)):
            e12 = calc_ema(closes[:i+1], 12)
            e26 = calc_ema(closes[:i+1], 26)
            if e12 and e26:
                macd_series.append(e12 - e26)
        signal = calc_ema(macd_series, 9) if len(macd_series) >= 9 else None
        histogram = round(macd_line - signal, 2) if signal else None
    else:
        signal = None
        histogram = None
    return macd_line, signal, histogram

def calc_bollinger(closes, period=20, std_dev=2):
    if len(closes) < period:
        return None, None, None
    recent = closes[-period:]
    mm = sum(recent) / period
    variance = sum((x - mm) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    upper = round(mm + std_dev * std, 2)
    lower = round(mm - std_dev * std, 2)
    middle = round(mm, 2)
    return upper, middle, lower

def calc_obv(closes, volumes):
    if len(closes) < 2:
        return None, None
    obv = 0
    obv_series = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv += volumes[i]
        elif closes[i] < closes[i-1]:
            obv -= volumes[i]
        obv_series.append(obv)
    # Tendência OBV (últimos 20 dias)
    if len(obv_series) >= 20:
        trend = 'subindo' if obv_series[-1] > obv_series[-20] else 'caindo'
    else:
        trend = 'subindo' if obv > 0 else 'caindo'
    return obv, trend

def calc_graham(lpa, vpa):
    if lpa and vpa and lpa > 0 and vpa > 0:
        return round(math.sqrt(22.5 * lpa * vpa), 2)
    return None

# ── GERADOR DE SINAL ──────────────────────────────────
def gerar_sinal(ind, cdi):
    score_tec = 0
    max_tec = 0
    score_fund = 0
    max_fund = 0
    detalhes_tec = []
    detalhes_fund = []

    price = ind.get('price', 0)
    setor = ind.get('setor', SETOR_DEFAULT)

    # ── TÉCNICOS ──
    rsi = ind.get('rsi')
    if rsi is not None:
        max_tec += 2
        if rsi < 30:
            score_tec += 2
            detalhes_tec.append({'status':'buy','texto':f'RSI {rsi} — Sobrevenda ⚡'})
        elif rsi < 45:
            score_tec += 1
            detalhes_tec.append({'status':'neutral','texto':f'RSI {rsi} — Levemente favorável'})
        elif rsi > 70:
            score_tec -= 1
            detalhes_tec.append({'status':'sell','texto':f'RSI {rsi} — Sobrecompra ⚠'})
        else:
            detalhes_tec.append({'status':'neutral','texto':f'RSI {rsi} — Zona neutra'})

    mm200 = ind.get('mm200')
    if mm200 and price:
        max_tec += 2
        if price > mm200:
            score_tec += 2
            detalhes_tec.append({'status':'buy','texto':f'Acima MM200 (R$ {mm200:.2f}) — Tendência alta'})
        else:
            score_tec -= 1
            detalhes_tec.append({'status':'sell','texto':f'Abaixo MM200 (R$ {mm200:.2f}) — Tendência baixa'})

    mm50 = ind.get('mm50')
    if mm50 and price:
        max_tec += 1
        if price > mm50:
            score_tec += 1
            detalhes_tec.append({'status':'buy','texto':f'Acima MM50 (R$ {mm50:.2f})'})
        else:
            detalhes_tec.append({'status':'sell','texto':f'Abaixo MM50 (R$ {mm50:.2f})'})

    mm20 = ind.get('mm20')
    if mm20 and price:
        max_tec += 1
        if price > mm20:
            score_tec += 1
            detalhes_tec.append({'status':'buy','texto':f'Acima MM20 (R$ {mm20:.2f})'})
        else:
            detalhes_tec.append({'status':'neutral','texto':f'Abaixo MM20 (R$ {mm20:.2f}) — Correção curto prazo'})

    macd = ind.get('macd')
    macd_hist = ind.get('macd_histogram')
    if macd is not None and macd_hist is not None:
        max_tec += 1
        if macd_hist > 0:
            score_tec += 1
            detalhes_tec.append({'status':'buy','texto':f'MACD histograma positivo ({macd_hist:.2f}) — Momentum de alta'})
        else:
            detalhes_tec.append({'status':'sell','texto':f'MACD histograma negativo ({macd_hist:.2f}) — Momentum de baixa'})

    boll_upper = ind.get('bollinger_upper')
    boll_lower = ind.get('bollinger_lower')
    boll_mid = ind.get('bollinger_mid')
    if boll_upper and boll_lower and price:
        max_tec += 1
        boll_pct = (price - boll_lower) / (boll_upper - boll_lower) * 100 if boll_upper != boll_lower else 50
        if price <= boll_lower:
            score_tec += 1
            detalhes_tec.append({'status':'buy','texto':f'Abaixo Banda Inferior Bollinger (R$ {boll_lower:.2f}) — Sobrevenda'})
        elif price >= boll_upper:
            detalhes_tec.append({'status':'sell','texto':f'Acima Banda Superior Bollinger (R$ {boll_upper:.2f}) — Sobrecompra'})
        else:
            detalhes_tec.append({'status':'neutral','texto':f'Dentro das Bandas Bollinger ({boll_pct:.0f}% da faixa)'})

    obv_trend = ind.get('obv_trend')
    if obv_trend:
        max_tec += 1
        if obv_trend == 'subindo':
            score_tec += 1
            detalhes_tec.append({'status':'buy','texto':'OBV subindo — Volume confirma tendência'})
        else:
            detalhes_tec.append({'status':'sell','texto':'OBV caindo — Volume diverge'})

    # ── FUNDAMENTALISTAS ──
    pl = ind.get('pl')
    pl_setor = setor.get('pl_medio', 12)
    if pl and pl > 0:
        max_fund += 2
        if pl < pl_setor * 0.7:
            score_fund += 2
            detalhes_fund.append({'status':'buy','texto':f'P/L {pl:.1f}x — Barato vs setor ({pl_setor}x)'})
        elif pl < pl_setor:
            score_fund += 1
            detalhes_fund.append({'status':'buy','texto':f'P/L {pl:.1f}x — Abaixo da média do setor ({pl_setor}x)'})
        elif pl > pl_setor * 1.5:
            score_fund -= 1
            detalhes_fund.append({'status':'sell','texto':f'P/L {pl:.1f}x — Caro vs setor ({pl_setor}x)'})
        else:
            detalhes_fund.append({'status':'neutral','texto':f'P/L {pl:.1f}x — Próximo da média do setor ({pl_setor}x)'})

    pvp = ind.get('pvp')
    pvp_setor = setor.get('pvp_medio', 2.0)
    if pvp and pvp > 0:
        max_fund += 1
        if pvp < 1.0:
            score_fund += 1
            detalhes_fund.append({'status':'buy','texto':f'P/VP {pvp:.2f}x — Abaixo do patrimônio (muito barato)'})
        elif pvp < pvp_setor:
            score_fund += 1
            detalhes_fund.append({'status':'buy','texto':f'P/VP {pvp:.2f}x — Abaixo da média do setor ({pvp_setor}x)'})
        else:
            detalhes_fund.append({'status':'neutral','texto':f'P/VP {pvp:.2f}x — Acima da média do setor ({pvp_setor}x)'})

    dy = ind.get('dividend_yield')
    if dy and dy > 0:
        max_fund += 2
        if dy > cdi:
            score_fund += 2
            detalhes_fund.append({'status':'buy','texto':f'DY {dy:.1f}% > CDI {cdi:.1f}% — Dividendo supera renda fixa ⭐'})
        elif dy > cdi * 0.7:
            score_fund += 1
            detalhes_fund.append({'status':'neutral','texto':f'DY {dy:.1f}% vs CDI {cdi:.1f}% — Próximo da renda fixa'})
        else:
            detalhes_fund.append({'status':'sell','texto':f'DY {dy:.1f}% < CDI {cdi:.1f}% — Dividendo abaixo da renda fixa'})

    roe = ind.get('roe')
    roe_setor = setor.get('roe_medio', 15)
    if roe and roe > 0:
        max_fund += 1
        if roe > roe_setor:
            score_fund += 1
            detalhes_fund.append({'status':'buy','texto':f'ROE {roe:.1f}% — Acima da média do setor ({roe_setor}%)'})
        elif roe > 10:
            detalhes_fund.append({'status':'neutral','texto':f'ROE {roe:.1f}% — Retorno moderado'})
        else:
            detalhes_fund.append({'status':'sell','texto':f'ROE {roe:.1f}% — Retorno fraco'})

    div_ebitda = ind.get('divida_ebitda')
    if div_ebitda is not None:
        max_fund += 1
        if div_ebitda < 1.5:
            score_fund += 1
            detalhes_fund.append({'status':'buy','texto':f'Dívida/EBITDA {div_ebitda:.1f}x — Endividamento saudável'})
        elif div_ebitda < 3.0:
            detalhes_fund.append({'status':'neutral','texto':f'Dívida/EBITDA {div_ebitda:.1f}x — Endividamento moderado'})
        else:
            detalhes_fund.append({'status':'sell','texto':f'Dívida/EBITDA {div_ebitda:.1f}x — Endividamento alto'})

    # Valor justo Graham vs preço atual
    vj_graham = ind.get('valor_justo_graham')
    if vj_graham and price:
        max_fund += 2
        upside = (vj_graham - price) / price * 100
        if upside > 20:
            score_fund += 2
            detalhes_fund.append({'status':'buy','texto':f'Upside Graham {upside:.0f}% — Ação subavaliada (VJ: R$ {vj_graham:.2f})'})
        elif upside > 0:
            score_fund += 1
            detalhes_fund.append({'status':'buy','texto':f'Upside Graham {upside:.0f}% — Leve desconto (VJ: R$ {vj_graham:.2f})'})
        elif upside > -20:
            detalhes_fund.append({'status':'neutral','texto':f'Desconto Graham {upside:.0f}% — Próximo do valor justo (VJ: R$ {vj_graham:.2f})'})
        else:
            score_fund -= 1
            detalhes_fund.append({'status':'sell','texto':f'Sobrevalorizado {abs(upside):.0f}% acima do Graham (VJ: R$ {vj_graham:.2f})'})

    # ── SINAL COMBINADO ──
    pct_tec = score_tec / max_tec if max_tec > 0 else 0
    pct_fund = score_fund / max_fund if max_fund > 0 else 0
    pct_total = (pct_tec * 0.5 + pct_fund * 0.5)  # peso igual técnico e fundamentalista

    def classify(pct):
        if pct >= 0.65: return 'COMPRA FORTE', 'green'
        elif pct >= 0.40: return 'COMPRA MODERADA', 'accent'
        elif pct >= 0.10: return 'NEUTRO', 'warn'
        elif pct >= -0.20: return 'VENDA MODERADA', 'orange'
        else: return 'VENDA FORTE', 'danger'

    sinal_tec, cor_tec = classify(pct_tec)
    sinal_fund, cor_fund = classify(pct_fund)
    sinal_total, cor_total = classify(pct_total)

    return {
        'sinal': sinal_total,
        'cor': cor_total,
        'forca': round(pct_total * 100),
        'sinal_tecnico': sinal_tec,
        'cor_tecnico': cor_tec,
        'forca_tecnica': round(pct_tec * 100),
        'sinal_fundamentalista': sinal_fund,
        'cor_fundamentalista': cor_fund,
        'forca_fundamentalista': round(pct_fund * 100),
        'detalhes_tecnicos': detalhes_tec,
        'detalhes_fundamentalistas': detalhes_fund,
        'cdi_usado': cdi
    }

# ── INDICADORES B3 ────────────────────────────────────
@app.route('/indicators/<path:ticker>', methods=['GET'])
def get_indicators(ticker):
    try:
        cdi = get_cdi()
        setor = SETORES.get(ticker, SETOR_DEFAULT)

        # Histórico de preços
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=400d'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if not r.ok:
            return jsonify({'error': f'Yahoo HTTP {r.status_code}'}), 500

        data = r.json()
        result = data.get('chart', {}).get('result', [{}])[0]
        meta = result.get('meta', {})
        quotes = result.get('indicators', {}).get('quote', [{}])[0]

        closes_raw = quotes.get('close', [])
        volumes_raw = quotes.get('volume', [])
        closes = [c for c in closes_raw if c is not None]
        volumes = [v if v is not None else 0 for v in volumes_raw][-len(closes):]

        if not closes:
            return jsonify({'error': 'Sem dados de preço'}), 500

        price = meta.get('regularMarketPrice', closes[-1])

        # Indicadores técnicos
        rsi = calc_rsi(closes)
        mm20 = calc_mm(closes, 20)
        mm50 = calc_mm(closes, 50)
        mm200 = calc_mm(closes, 200)
        macd_line, macd_signal, macd_hist = calc_macd(closes)
        boll_upper, boll_mid, boll_lower = calc_bollinger(closes)
        obv_val, obv_trend = calc_obv(closes, volumes)

        # Vol médio 20 dias
        vol_medio = round(sum(volumes[-20:]) / min(20, len(volumes)), 0) if volumes else None

        # Fundamentais via Yahoo
        pl = pvp = dy = roe = ev_ebitda = divida_ebitda = market_cap = None
        margem_liquida = crescimento_lucro = lpa = vpa = None

        try:
            url2 = f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=summaryDetail,defaultKeyStatistics,financialData,incomeStatementHistory'
            r2 = requests.get(url2, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if r2.ok:
                fund = r2.json().get('quoteSummary', {}).get('result', [{}])[0]
                summary = fund.get('summaryDetail', {})
                stats = fund.get('defaultKeyStatistics', {})
                financial = fund.get('financialData', {})

                def raw(d, key):
                    v = d.get(key, {})
                    return v.get('raw') if isinstance(v, dict) else v

                pl = raw(summary, 'trailingPE')
                pvp = raw(stats, 'priceToBook')
                dy_val = raw(summary, 'dividendYield')
                dy = round(dy_val * 100, 2) if dy_val else None
                roe_val = raw(financial, 'returnOnEquity')
                roe = round(roe_val * 100, 2) if roe_val else None
                ev_ebitda = raw(stats, 'enterpriseToEbitda')
                market_cap = raw(summary, 'marketCap')

                # Dívida/EBITDA
                total_debt = raw(financial, 'totalDebt')
                ebitda = raw(financial, 'ebitda')
                if total_debt and ebitda and ebitda > 0:
                    divida_ebitda = round(total_debt / ebitda, 2)

                # LPA e VPA para Graham
                lpa = raw(stats, 'trailingEps')
                bvps = raw(stats, 'bookValue')
                vpa = bvps

                # Margem líquida
                ml = raw(financial, 'profitMargins')
                margem_liquida = round(ml * 100, 2) if ml else None

        except Exception as e:
            pass

        # Valor justo Graham
        valor_justo_graham = calc_graham(lpa, vpa)

        # Upside Graham
        upside_graham = None
        if valor_justo_graham and price:
            upside_graham = round((valor_justo_graham - price) / price * 100, 1)

        # Formata valores
        def fmt(v): return round(v, 2) if v is not None else None

        indicators = {
            'ticker': ticker,
            'setor': setor,
            'price': round(price, 2),
            # Técnicos
            'rsi': rsi,
            'mm20': mm20,
            'mm50': mm50,
            'mm200': mm200,
            'macd': fmt(macd_line),
            'macd_signal': fmt(macd_signal),
            'macd_histogram': fmt(macd_hist),
            'bollinger_upper': boll_upper,
            'bollinger_mid': boll_mid,
            'bollinger_lower': boll_lower,
            'obv_trend': obv_trend,
            'volume_medio_20d': vol_medio,
            # Fundamentalistas
            'pl': fmt(pl),
            'pvp': fmt(pvp),
            'ev_ebitda': fmt(ev_ebitda),
            'dividend_yield': dy,
            'roe': roe,
            'divida_ebitda': fmt(divida_ebitda),
            'margem_liquida': margem_liquida,
            'lpa': fmt(lpa),
            'vpa': fmt(vpa),
            'valor_justo_graham': valor_justo_graham,
            'upside_graham': upside_graham,
            'market_cap': market_cap,
            'cdi': cdi,
            'data_points': len(closes)
        }

        indicators['sinal'] = gerar_sinal(indicators, cdi)
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
        if not r.ok:
            return jsonify({'error': 'Binance indisponível'}), 500

        candles = r.json()
        closes = [float(c[4]) for c in candles]
        volumes = [float(c[5]) for c in candles]
        price = closes[-1]

        rsi = calc_rsi(closes, 14)
        mm20 = calc_mm(closes, 20)
        mm50 = calc_mm(closes, 50)
        mm200 = calc_mm(closes, 200)
        macd_line, macd_signal, macd_hist = calc_macd(closes)
        boll_upper, boll_mid, boll_lower = calc_bollinger(closes)
        obv_val, obv_trend = calc_obv(closes, volumes)

        # Divergência bullish RSI
        divergencia = None
        if rsi and len(closes) >= 60:
            min_p_rec = min(closes[-15:])
            min_p_prev = min(closes[-30:-15])
            rsi_rec = calc_rsi(closes[-29:], 14)
            rsi_prev = calc_rsi(closes[-44:-15], 14)
            if rsi_rec and rsi_prev:
                if min_p_rec < min_p_prev and rsi_rec > rsi_prev:
                    divergencia = 'BULLISH ⚡ Preço faz mínima mais baixa mas RSI não confirma — Sinal de fundo potencial!'
                elif min_p_rec > min_p_prev and rsi_rec < rsi_prev:
                    divergencia = 'BEARISH ⚠ Preço faz máxima mais alta mas RSI não confirma — Sinal de topo!'

        return jsonify({
            'ticker': 'BTC',
            'price': round(price, 0),
            'rsi_semanal': rsi,
            'mm20_semanal': round(mm20, 0) if mm20 else None,
            'mm50_semanal': round(mm50, 0) if mm50 else None,
            'mm200_semanal': round(mm200, 0) if mm200 else None,
            'macd': round(macd_line, 0) if macd_line else None,
            'macd_histogram': round(macd_hist, 0) if macd_hist else None,
            'bollinger_upper': round(boll_upper, 0) if boll_upper else None,
            'bollinger_mid': round(boll_mid, 0) if boll_mid else None,
            'bollinger_lower': round(boll_lower, 0) if boll_lower else None,
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
    print("  Acesse: http://localhost:8888")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8888, use_reloader=False, threaded=True)
