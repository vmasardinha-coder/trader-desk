"""
Trader Desk — Proxy Server v2
Calcula indicadores técnicos e fundamentalistas server-side
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

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

# ── BINANCE FUNDING ───────────────────────────────────
@app.route('/binance/funding', methods=['GET'])
def binance_funding():
    # Tenta múltiplos endpoints de funding rate
    endpoints = [
        'https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT',
        'https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1',
        'https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=1',
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # Tenta Binance primeiro
    for url in endpoints[:2]:
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if not r.ok:
                continue
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                # fundingRate endpoint retorna lista
                return jsonify({'lastFundingRate': data[0].get('fundingRate', '0'),
                               'nextFundingTime': int(data[0].get('fundingTime', 0)) + 28800000})
            if 'lastFundingRate' in data:
                return jsonify(data)
        except:
            continue
    
    # Tenta Bybit como fallback
    try:
        r = requests.get(endpoints[2], headers=headers, timeout=8)
        if r.ok:
            data = r.json()
            items = data.get('result', {}).get('list', [])
            if items:
                fr = float(items[0].get('fundingRate', 0))
                return jsonify({
                    'lastFundingRate': str(fr),
                    'nextFundingTime': int(items[0].get('fundingRateTimestamp', 0)) + 28800000
                })
    except:
        pass
    
    return jsonify({'error': 'Todos endpoints indisponíveis'}), 500

# ── DOW JONES VIA YAHOO ───────────────────────────────
@app.route('/dji', methods=['GET'])
def get_dji():
    try:
        r = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1d&range=5d',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=5
        )
        if not r.ok:
            return jsonify({'error': f'HTTP {r.status_code}'}), 500
        data = r.json()
        meta = data['chart']['result'][0]['meta']
        closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
        valid = [c for c in closes if c is not None]
        price = meta.get('regularMarketPrice', valid[-1])
        prev = meta.get('chartPreviousClose', valid[-2] if len(valid) > 1 else price)
        return jsonify({'price': price, 'prev': prev})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── CÁLCULO DE INDICADORES ────────────────────────────
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i-1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period-1) + gains[i]) / period
        avg_loss = (avg_loss * (period-1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_mm(closes, period):
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)

def calc_obv(closes, volumes):
    if len(closes) < 2:
        return None
    obv = 0
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv += volumes[i]
        elif closes[i] < closes[i-1]:
            obv -= volumes[i]
    return obv

def gerar_sinal(ind):
    score = 0
    max_score = 0
    detalhes = []
    price = ind.get('price', 0)

    # RSI
    rsi = ind.get('rsi')
    if rsi is not None:
        max_score += 2
        if rsi < 30:
            score += 2
            detalhes.append({'status': 'buy', 'texto': f'RSI {rsi} — Sobrevenda (compra)'})
        elif rsi < 45:
            score += 1
            detalhes.append({'status': 'neutral', 'texto': f'RSI {rsi} — Levemente favorável'})
        elif rsi > 70:
            score -= 1
            detalhes.append({'status': 'sell', 'texto': f'RSI {rsi} — Sobrecompra (venda)'})
        else:
            detalhes.append({'status': 'neutral', 'texto': f'RSI {rsi} — Zona neutra'})

    # MM200
    mm200 = ind.get('mm200')
    if mm200 and price:
        max_score += 2
        if price > mm200:
            score += 2
            detalhes.append({'status': 'buy', 'texto': f'Acima da MM200 (R$ {mm200:.2f}) — Tendência alta'})
        else:
            score -= 1
            detalhes.append({'status': 'sell', 'texto': f'Abaixo da MM200 (R$ {mm200:.2f}) — Tendência baixa'})

    # MM50
    mm50 = ind.get('mm50')
    if mm50 and price:
        max_score += 1
        if price > mm50:
            score += 1
            detalhes.append({'status': 'buy', 'texto': f'Acima da MM50 (R$ {mm50:.2f})'})
        else:
            detalhes.append({'status': 'sell', 'texto': f'Abaixo da MM50 (R$ {mm50:.2f})'})

    # MM20
    mm20 = ind.get('mm20')
    if mm20 and price:
        max_score += 1
        if price > mm20:
            score += 1
            detalhes.append({'status': 'buy', 'texto': f'Acima da MM20 (R$ {mm20:.2f})'})
        else:
            detalhes.append({'status': 'neutral', 'texto': f'Abaixo da MM20 (R$ {mm20:.2f}) — Correção curto prazo'})

    # OBV
    obv_trend = ind.get('obv_trend')
    if obv_trend:
        max_score += 1
        if obv_trend == 'subindo':
            score += 1
            detalhes.append({'status': 'buy', 'texto': 'OBV subindo — Volume confirma tendência'})
        else:
            detalhes.append({'status': 'sell', 'texto': 'OBV caindo — Volume diverge'})

    # P/L
    pl = ind.get('pl')
    if pl and pl > 0:
        max_score += 1
        if pl < 10:
            score += 1
            detalhes.append({'status': 'buy', 'texto': f'P/L {pl:.1f}x — Barato vs lucro'})
        elif pl > 25:
            detalhes.append({'status': 'sell', 'texto': f'P/L {pl:.1f}x — Caro vs lucro'})
        else:
            detalhes.append({'status': 'neutral', 'texto': f'P/L {pl:.1f}x — Valuation neutro'})

    # DY
    dy = ind.get('dividend_yield')
    if dy and dy > 0:
        max_score += 1
        if dy > 6:
            score += 1
            detalhes.append({'status': 'buy', 'texto': f'DY {dy:.1f}% — Dividendo atrativo'})
        elif dy > 3:
            detalhes.append({'status': 'neutral', 'texto': f'DY {dy:.1f}% — Dividendo moderado'})
        else:
            detalhes.append({'status': 'neutral', 'texto': f'DY {dy:.1f}% — Dividendo baixo'})

    if max_score == 0:
        return {'sinal': 'SEM DADOS', 'forca': 0, 'detalhes': detalhes}

    pct = score / max_score
    if pct >= 0.65:
        sinal = 'COMPRA FORTE'
        cor = 'green'
    elif pct >= 0.35:
        sinal = 'COMPRA MODERADA'
        cor = 'accent'
    elif pct >= 0.0:
        sinal = 'NEUTRO'
        cor = 'warn'
    elif pct >= -0.3:
        sinal = 'VENDA MODERADA'
        cor = 'orange'
    else:
        sinal = 'VENDA FORTE'
        cor = 'danger'

    return {
        'sinal': sinal,
        'cor': cor,
        'score': score,
        'max_score': max_score,
        'forca': round(pct * 100),
        'detalhes': detalhes
    }

# ── INDICADORES AÇÕES B3 ──────────────────────────────
@app.route('/indicators/<ticker>', methods=['GET'])
def get_indicators(ticker):
    try:
        # Histórico de preços
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=300d'
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
        volumes = [v if v is not None else 0 for v in volumes_raw]
        volumes = volumes[-len(closes):]

        if not closes:
            return jsonify({'error': 'Sem dados'}), 500

        price = meta.get('regularMarketPrice', closes[-1])

        rsi = calc_rsi(closes)
        mm20 = calc_mm(closes, 20)
        mm50 = calc_mm(closes, 50)
        mm200 = calc_mm(closes, 200)

        obv_20 = calc_obv(closes[-21:], volumes[-21:]) if len(closes) >= 21 else None
        obv_trend = ('subindo' if (obv_20 or 0) > 0 else 'caindo') if obv_20 is not None else None

        # Fundamentais
        pl = ev_ebitda = dy = market_cap = None
        try:
            url2 = f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=summaryDetail,defaultKeyStatistics'
            r2 = requests.get(url2, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if r2.ok:
                fund = r2.json().get('quoteSummary', {}).get('result', [{}])[0]
                summary = fund.get('summaryDetail', {})
                stats = fund.get('defaultKeyStatistics', {})

                pl_raw = summary.get('trailingPE', {})
                pl = pl_raw.get('raw') if isinstance(pl_raw, dict) else None
                if pl: pl = round(pl, 1)

                ev_raw = stats.get('enterpriseToEbitda', {})
                ev_ebitda = ev_raw.get('raw') if isinstance(ev_raw, dict) else None
                if ev_ebitda: ev_ebitda = round(ev_ebitda, 1)

                dy_raw = summary.get('dividendYield', {})
                dy_val = dy_raw.get('raw') if isinstance(dy_raw, dict) else None
                dy = round(dy_val * 100, 2) if dy_val else None

                mc_raw = summary.get('marketCap', {})
                market_cap = mc_raw.get('raw') if isinstance(mc_raw, dict) else None
        except:
            pass

        indicators = {
            'ticker': ticker,
            'price': round(price, 2),
            'rsi': rsi,
            'mm20': mm20,
            'mm50': mm50,
            'mm200': mm200,
            'obv_trend': obv_trend,
            'pl': pl,
            'ev_ebitda': ev_ebitda,
            'dividend_yield': dy,
            'market_cap': market_cap,
            'data_points': len(closes)
        }
        indicators['sinal'] = gerar_sinal(indicators)
        return jsonify(indicators)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── INDICADORES BTC VIA BINANCE ───────────────────────
@app.route('/btc/indicators', methods=['GET'])
def get_btc_indicators():
    try:
        r = requests.get(
            'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=210',
            timeout=10
        )
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

        obv_20 = calc_obv(closes[-21:], volumes[-21:]) if len(closes) >= 21 else None
        obv_trend = 'subindo' if (obv_20 or 0) > 0 else 'caindo'

        # Divergência bullish RSI
        divergencia = None
        if rsi and len(closes) >= 60:
            min_price_recent = min(closes[-15:])
            min_price_prev = min(closes[-30:-15])
            rsi_recent = calc_rsi(closes[-29:], 14)
            rsi_prev = calc_rsi(closes[-44:-15], 14)
            if rsi_recent and rsi_prev:
                if min_price_recent < min_price_prev and rsi_recent > rsi_prev:
                    divergencia = 'BULLISH ⚡ Preço faz mínima mais baixa mas RSI não confirma — Sinal de fundo!'
                elif min_price_recent > min_price_prev and rsi_recent < rsi_prev:
                    divergencia = 'BEARISH ⚠ Preço faz máxima mais alta mas RSI não confirma — Sinal de topo!'

        return jsonify({
            'ticker': 'BTC',
            'price': round(price, 0),
            'rsi_semanal': rsi,
            'mm20_semanal': round(mm20, 0) if mm20 else None,
            'mm50_semanal': round(mm50, 0) if mm50 else None,
            'mm200_semanal': round(mm200, 0) if mm200 else None,
            'obv_trend': obv_trend,
            'divergencia_rsi': divergencia,
            'data_points': len(closes)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

import os

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    # Serve o HTML da mesma pasta do proxy.py
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'painel-trader.html')
    if os.path.exists(html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return 'painel-trader.html não encontrado na mesma pasta', 404

if __name__ == '__main__':
    print("=" * 50)
    print("  Trader Desk — Proxy v2")
    print("  Acesse: http://localhost:8888")
    print("=" * 50)
    app.run(port=8888, use_reloader=False, threaded=True)
