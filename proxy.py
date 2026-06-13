"""
PATCH para proxy.py v8.3 → v8.4
Aplique estas mudanças no seu proxy.py existente:

1. Adicionar cache para BTC indicators/cycle
2. Reduzir range Yahoo de 4y para 1y nos endpoints BTC
3. Adicionar campo 'explicacao' nos indicadores B3
4. Melhorar endpoint /calendar com múltiplas fontes

Cole cada bloco no local indicado.
"""

# ══════════════════════════════════════════════════════
# MUDANÇA 1: Adicionar cache BTC no topo (após _IND_CACHE)
# ══════════════════════════════════════════════════════
_IND_CACHE = {}
_BTC_CACHE = {}   # ← ADICIONAR ESTA LINHA


# ══════════════════════════════════════════════════════
# MUDANÇA 2: Substituir /btc/indicators completo
# ══════════════════════════════════════════════════════

@app.route('/btc/indicators', methods=['GET'])
def get_btc_indicators():
    import time as _t
    # Cache de 10 minutos
    if 'indicators' in _BTC_CACHE:
        cd, ct = _BTC_CACHE['indicators']
        if _t.time() - ct < 600:
            return jsonify(cd)
    try:
        # 1 ano ao invés de 4 anos — muito mais rápido no Render
        for host in ['query1', 'query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=1y',
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                    timeout=10)
                if r.ok:
                    break
            except:
                continue
        if not r.ok:
            return jsonify({'error': f'Yahoo BTC HTTP {r.status_code}'}), 500
        d = r.json()
        result_data = d['chart']['result'][0]
        q = result_data['indicators']['quote'][0]
        cl = [c for c in q.get('close', []) if c is not None]
        vl = [v if v else 0 for v in q.get('volume', [])][-len(cl):]
        price = cl[-1]
        rsi_v = rsi(cl, 14)
        mm20_v = mm(cl, 20)
        mm50_v = mm(cl, 50)
        mm200_v = mm(cl, 200)
        ml, ms, mh = macd(cl)
        bu, bm, bl = bollinger(cl)
        _, ot = obv(cl, vl)

        result = {
            'ticker': 'BTC', 'price': round(price, 0),
            'rsi_semanal': rsi_v,
            'mm20_semanal': round(mm20_v, 0) if mm20_v else None,
            'mm50_semanal': round(mm50_v, 0) if mm50_v else None,
            'mm200_semanal': round(mm200_v, 0) if mm200_v else None,
            'macd': round(ml, 0) if ml else None,
            'macd_signal': round(ms, 0) if ms else None,
            'macd_histogram': round(mh, 0) if mh else None,
            'bb_upper': round(bu, 0) if bu else None,
            'bb_mid': round(bm, 0) if bm else None,
            'bb_lower': round(bl, 0) if bl else None,
            'obv_trend': ot,
            'data_points': len(cl)
        }
        _BTC_CACHE['indicators'] = (result, _t.time())
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════
# MUDANÇA 3: Substituir /btc/cycle completo
# ══════════════════════════════════════════════════════

@app.route('/btc/cycle', methods=['GET'])
def get_btc_cycle():
    import time as _t, math as _m
    # Cache de 15 minutos
    if 'cycle' in _BTC_CACHE:
        cd, ct = _BTC_CACHE['cycle']
        if _t.time() - ct < 900:
            return jsonify(cd)
    try:
        # Usar 2 anos ao invés de 4 — suficiente para MM111/350
        r = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1d&range=2y',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if not r.ok:
            return jsonify({'error': f'Yahoo {r.status_code}'}), 500
        cl = [c for c in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        price = cl[-1]
        dma111 = mm(cl, 111)
        dma350 = mm(cl, 350)
        dma350x2 = round(dma350 * 2, 0) if dma350 else None
        pi_dist = round(dma350x2 - dma111, 0) if (dma111 and dma350x2) else None
        if dma111 and dma350x2:
            if dma111 >= dma350x2:
                pi_sig = "TOPO DETECTADO Pi Cycle cruzou!"
            elif pi_dist and pi_dist < 10000:
                pi_sig = "Proximidade de topo crítica"
            elif pi_dist and pi_dist < 30000:
                pi_sig = "Monitorar distância diminuindo"
            else:
                pi_sig = f"Seguro — distância US$ {pi_dist:,.0f}" if pi_dist else "Calculando..."
        else:
            pi_sig = "Dados insuficientes (precisa 350 dias)"

        days = (_t.time() - 1231006505) / 86400
        fair = 10 ** (5.84 * _m.log10(days) - 17.01)
        mults = [0.10, 0.20, 0.35, 0.55, 0.80, 1.20, 1.70, 2.50, 4.00]
        names = ["Fire Sale", "Buy", "Accumulate", "Still Cheap", "HODL!", "Bubble?", "FOMO", "Sell", "Max Bubble"]
        colors = ["green", "green", "green", "accent", "warn", "warn", "danger", "danger", "danger"]
        rb = names[-1]; rc = colors[-1]
        for i, mv in enumerate(mults):
            if price < fair * mv:
                rb = names[i]; rc = colors[i]; break

        # MA 200w — usar dados semanais 1 ano (aproximado)
        rw = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=1y',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        ma200w = None
        if rw.ok:
            clw = [c for c in rw.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
            ma200w = mm(clw, 52)  # 52 semanas ≈ MA anual como proxy

        oc = get_btc_onchain()

        def ml_label(v):
            return "Capitulação" if v < -1 else "Valor Justo" if v < 1 else "Valorizado" if v < 2 else "Aquecendo" if v < 3 else "Sobrevalorizado" if v < 5 else "Euforia TOPO"
        def nl_label(v):
            return "Capitulação" if v < 0 else "Esperança/Medo" if v < 0.25 else "Otimismo" if v < 0.50 else "Crença/Negação" if v < 0.75 else "Euforia TOPO"
        def pl_label(v):
            return "Estresse mineradores" if v < 0.5 else "Pós-halving" if v < 1.0 else "Normal" if v < 2.0 else "Aquecendo" if v < 3.4 else "Topo de ciclo"

        result = {
            'price': round(price, 0),
            'pi_cycle': {'dma111': dma111, 'dma350x2': dma350x2, 'distance': pi_dist, 'signal': pi_sig},
            'rainbow': {'band': rb, 'color': rc},
            'ma200w': round(ma200w, 0) if ma200w else None,
            'ma200w_pct': round((price - ma200w) / ma200w * 100, 1) if ma200w else None,
            'mvrv_zscore': {'value': oc['mvrv_zscore'], 'label': ml_label(oc['mvrv_zscore'])},
            'nupl': {'value': oc['nupl'], 'label': nl_label(oc['nupl'])},
            'puell': {'value': oc['puell_multiple'], 'label': pl_label(oc['puell_multiple'])},
            'sopr': oc['sopr'],
            'realized_price': oc['realized_price'],
            'onchain_updated': oc['updated']
        }
        _BTC_CACHE['cycle'] = (result, _t.time())
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════
# MUDANÇA 4: Substituir /indicators/<ticker> — adicionar campo 'explicacao'
# Apenas a parte que monta 'indicadores', substituir o bloco:
# ══════════════════════════════════════════════════════

# No final da função get_indicators(), onde monta a lista indicadores=[],
# substitua por esta versão que adiciona 'explicacao':

def _build_indicadores(preco_atual, fund, setor, hist_closes, cdi):
    """Monta lista de indicadores com explicação textual"""
    closes = hist_closes

    def _mm(lst, n):
        return round(sum(lst[-n:]) / n, 2) if len(lst) >= n else None

    def _rsi(closes, n=14):
        if len(closes) < n + 1: return None
        gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
        losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
        ag = sum(gains[:n]) / n; al = sum(losses[:n]) / n
        for i in range(n, len(gains)):
            ag = (ag * (n-1) + gains[i]) / n
            al = (al * (n-1) + losses[i]) / n
        return round(100 - 100 / (1 + ag / al), 1) if al else 100.0

    rsi14 = _rsi(closes)
    ma20 = _mm(closes, 20)
    ma50 = _mm(closes, 50)
    ma200 = _mm(closes, 200)

    p = preco_atual
    pl = fund.get('pl') or fund.get('priceEarnings')
    pvp = fund.get('pvp') or fund.get('priceToBook')
    dy = fund.get('dy') or fund.get('dividendYield')
    roe = fund.get('roe') or fund.get('returnOnEquity')
    lpa = fund.get('lpa') or fund.get('earningsPerShare')
    vpa = fund.get('vpa') or fund.get('bookValuePerShare')

    if dy and float(dy) > 1:
        dy = round(float(dy) / 100, 4)

    import math as _m
    graham = None
    if lpa and vpa and float(lpa) > 0 and float(vpa) > 0:
        graham = round(_m.sqrt(22.5 * float(lpa) * float(vpa)), 2)

    pl_s = setor.get('pl_medio', 12)
    pvp_s = setor.get('pvp_medio', 2)
    roe_s = setor.get('roe_min', 12)

    indicadores = []

    # RSI
    if rsi14:
        if rsi14 < 30:
            sinal, exp = 'Alta', f'RSI {rsi14} — Sobrevenda ⚡ potencial reversão de alta'
        elif rsi14 < 45:
            sinal, exp = 'Alta', f'RSI {rsi14} — Zona favorável, momentum positivo'
        elif rsi14 > 70:
            sinal, exp = 'Baixa', f'RSI {rsi14} — Sobrecompra ⚠ risco de correção'
        else:
            sinal, exp = 'Neutro', f'RSI {rsi14} — Zona neutra, sem sinal claro'
        indicadores.append({'nome': 'RSI(14)', 'valor': rsi14, 'sinal': sinal, 'explicacao': exp})

    # MMs
    if ma20:
        sinal = 'Alta' if p > ma20 else 'Baixa'
        exp = f'Preço {"acima" if p > ma20 else "abaixo"} da MM20 ({ma20:.2f}) — tendência de curto prazo {"positiva ✅" if p > ma20 else "negativa"}'
        indicadores.append({'nome': 'MM20', 'valor': ma20, 'sinal': sinal, 'explicacao': exp})

    if ma50:
        sinal = 'Alta' if p > ma50 else 'Baixa'
        exp = f'Preço {"acima" if p > ma50 else "abaixo"} da MM50 ({ma50:.2f}) — tendência de médio prazo {"positiva ✅" if p > ma50 else "negativa"}'
        indicadores.append({'nome': 'MM50', 'valor': ma50, 'sinal': sinal, 'explicacao': exp})

    if ma200:
        sinal = 'Alta' if p > ma200 else 'Baixa'
        exp = f'Preço {"acima" if p > ma200 else "abaixo"} da MM200 ({ma200:.2f}) — tendência de longo prazo {"positiva ✅" if p > ma200 else "negativa ⚠"}'
        indicadores.append({'nome': 'MM200', 'valor': ma200, 'sinal': sinal, 'explicacao': exp})

    # P/L
    if pl:
        pl_f = float(pl)
        if pl_f < pl_s * 0.7:
            sinal, exp = 'Alta', f'P/L {pl_f:.1f}x muito barato vs setor ({pl_s}x) — potencial de valorização ✅✅'
        elif pl_f < pl_s:
            sinal, exp = 'Alta', f'P/L {pl_f:.1f}x abaixo da média do setor ({pl_s}x) — desconto relativo ✅'
        elif pl_f > pl_s * 1.5:
            sinal, exp = 'Baixa', f'P/L {pl_f:.1f}x caro vs setor ({pl_s}x) — prêmio elevado ⚠'
        else:
            sinal, exp = 'Neutro', f'P/L {pl_f:.1f}x próximo da média setorial ({pl_s}x)'
        indicadores.append({'nome': 'P/L', 'valor': round(pl_f, 1), 'sinal': sinal, 'explicacao': exp})

    # P/VP
    if pvp:
        pvp_f = float(pvp)
        if pvp_f < 1.0:
            sinal, exp = 'Alta', f'P/VP {pvp_f:.2f}x abaixo do patrimônio líquido — ação "barata" pelo Graham ✅'
        elif pvp_f < pvp_s:
            sinal, exp = 'Alta', f'P/VP {pvp_f:.2f}x abaixo da média setorial ({pvp_s}x) — desconto relativo ✅'
        else:
            sinal, exp = 'Neutro', f'P/VP {pvp_f:.2f}x acima da média setorial ({pvp_s}x)'
        indicadores.append({'nome': 'P/VP', 'valor': round(pvp_f, 2), 'sinal': sinal, 'explicacao': exp})

    # DY
    if dy:
        dy_pct = round(float(dy) * 100, 2)
        cdi_ref = cdi or 14.4
        if dy_pct > cdi_ref:
            sinal, exp = 'Alta', f'DY {dy_pct:.1f}% supera CDI ({cdi_ref:.1f}%) — dividendo bate renda fixa ⭐⭐'
        elif dy_pct > cdi_ref * 0.7:
            sinal, exp = 'Neutro', f'DY {dy_pct:.1f}% — próximo do CDI ({cdi_ref:.1f}%), retorno competitivo'
        else:
            sinal, exp = 'Baixa', f'DY {dy_pct:.1f}% abaixo do CDI ({cdi_ref:.1f}%) — dividendo pouco atrativo'
        indicadores.append({'nome': 'Div.Yield', 'valor': f'{dy_pct:.1f}%', 'sinal': sinal, 'explicacao': exp})

    # ROE
    if roe:
        roe_f = float(roe) * 100 if float(roe) < 1 else float(roe)
        if roe_f > roe_s:
            sinal, exp = 'Alta', f'ROE {roe_f:.1f}% acima do mínimo setorial ({roe_s}%) — empresa rentável ✅'
        elif roe_f > 10:
            sinal, exp = 'Neutro', f'ROE {roe_f:.1f}% — retorno moderado, abaixo do benchmark setorial'
        else:
            sinal, exp = 'Baixa', f'ROE {roe_f:.1f}% — retorno fraco sobre patrimônio ⚠'
        indicadores.append({'nome': 'ROE', 'valor': f'{roe_f:.1f}%', 'sinal': sinal, 'explicacao': exp})

    # Graham
    if graham:
        upside = round((graham / p - 1) * 100, 1)
        if upside > 20:
            sinal, exp = 'Alta', f'Graham R${graham:.2f} — upside de {upside:.0f}% ✅✅ subavaliada pelo critério conservador'
        elif upside > 0:
            sinal, exp = 'Alta', f'Graham R${graham:.2f} — leve desconto de {upside:.0f}%, dentro da margem de segurança ✅'
        elif upside > -20:
            sinal, exp = 'Neutro', f'Graham R${graham:.2f} — cotação {abs(upside):.0f}% acima do valor justo, monitorar'
        else:
            sinal, exp = 'Baixa', f'Graham R${graham:.2f} — sobrevalorizada {abs(upside):.0f}% acima, prêmio elevado ⚠'
        indicadores.append({'nome': 'Graham', 'valor': graham, 'sinal': sinal, 'explicacao': exp})

    if lpa:
        indicadores.append({'nome': 'LPA', 'valor': round(float(lpa), 2), 'sinal': 'Alta' if float(lpa) > 0 else 'Baixa',
                            'explicacao': f'Lucro por ação R${float(lpa):.2f} — {"positivo, empresa lucrativa ✅" if float(lpa) > 0 else "prejuízo por ação ⚠"}'})
    if vpa:
        indicadores.append({'nome': 'VPA', 'valor': round(float(vpa), 2), 'sinal': 'Neutro',
                            'explicacao': f'Valor patrimonial por ação R${float(vpa):.2f} — referência para cálculo P/VP e Graham'})

    altas = sum(1 for i in indicadores if i['sinal'] == 'Alta')
    total = len(indicadores) or 1
    score = round((altas / total) * 100)

    return indicadores, score, graham, round((graham / p - 1) * 100, 1) if graham else None


# ══════════════════════════════════════════════════════
# MUDANÇA 5: Substituir /calendar completo
# ══════════════════════════════════════════════════════

@app.route('/calendar', methods=['GET'])
def get_calendar():
    all_events = []
    currencies_ok = {'USD', 'BRL', 'EUR', 'GBP', 'CNY', 'JPY', 'CAD', 'AUD'}
    flag_map = {'USD': '🇺🇸', 'BRL': '🇧🇷', 'EUR': '🇪🇺', 'GBP': '🇬🇧', 'CNY': '🇨🇳', 'JPY': '🇯🇵', 'CAD': '🇨🇦', 'AUD': '🇦🇺'}
    imp_map = {'Low': 1, 'Medium': 2, 'High': 3, 'Holiday': 0}

    # FONTE 1: Forex Factory (múltiplos User-Agents para evitar bloqueio)
    ua_list = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Trader-Desk/1.0 (financial dashboard; contact@traderdesk.app)',
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
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.forexfactory.com/',
                    'Cache-Control': 'no-cache',
                }, timeout=12)
                if r.ok and len(r.text) > 100:
                    for e in r.json():
                        cur = e.get('country', e.get('currency', ''))
                        if not cur or cur not in currencies_ok: continue
                        imp = imp_map.get(e.get('impact', ''), 0)
                        if imp < 2: continue
                        raw_date = e.get('date', '')
                        date_str = raw_date[:10] if raw_date else ''
                        time_str = ''
                        if 'T' in raw_date:
                            try:
                                from datetime import datetime as _dt, timedelta, timezone
                                dt = _dt.fromisoformat(raw_date)
                                dt_brt = dt.astimezone(timezone(timedelta(hours=-3)))
                                time_str = dt_brt.strftime('%H:%M')
                                date_str = dt_brt.strftime('%Y-%m-%d')
                            except:
                                time_str = raw_date[11:16]
                        actual = e.get('actual') or None
                        forecast = e.get('forecast') or None
                        previous = e.get('previous') or None
                        signal = None
                        if actual and forecast:
                            try:
                                a = float(str(actual).replace('%', '').replace('K', '000').replace('M', '000000'))
                                f = float(str(forecast).replace('%', '').replace('K', '000').replace('M', '000000'))
                                signal = 'beat' if a >= f else 'miss'
                            except:
                                pass
                        all_events.append({
                            'date': date_str, 'time': time_str,
                            'country': cur, 'flag': flag_map.get(cur, '🌐'),
                            'event': e.get('title', ''),
                            'importance': imp,
                            'actual': actual, 'forecast': forecast, 'previous': previous,
                            'signal': signal,
                        })
                    break  # sucesso, não precisa tentar outro UA
            except Exception as ex:
                continue

    # FONTE 2: TradingView Economic Calendar como fallback
    if not all_events:
        try:
            from datetime import datetime as _dt, timedelta
            today = _dt.utcnow()
            end = today + timedelta(days=14)
            r_tv = requests.post(
                'https://economic-calendar.tradingview.com/events',
                json={
                    "from": today.strftime('%Y-%m-%dT00:00:00Z'),
                    "to": end.strftime('%Y-%m-%dT23:59:59Z'),
                    "countries": ["US", "BR", "EU", "GB", "CN", "JP", "CA", "AU"],
                    "importance": [1, 2],  # 1=medium, 2=high no TV
                },
                headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
                timeout=10
            )
            if r_tv.ok:
                tv_data = r_tv.json()
                for e in tv_data.get('result', []):
                    cur = e.get('country', '')
                    if cur not in currencies_ok: continue
                    imp_tv = e.get('importance', 0)
                    if imp_tv < 1: continue
                    raw_date = e.get('date', '')
                    try:
                        from datetime import datetime as _dt2, timedelta as _td, timezone as _tz
                        dt = _dt2.fromisoformat(raw_date.replace('Z', '+00:00'))
                        dt_brt = dt.astimezone(_tz(timedelta(hours=-3)))
                        date_str = dt_brt.strftime('%Y-%m-%d')
                        time_str = dt_brt.strftime('%H:%M')
                    except:
                        date_str = raw_date[:10]
                        time_str = raw_date[11:16] if 'T' in raw_date else ''
                    all_events.append({
                        'date': date_str, 'time': time_str,
                        'country': cur, 'flag': flag_map.get(cur, '🌐'),
                        'event': e.get('title', e.get('description', '')),
                        'importance': imp_tv + 1,  # normaliza para 2-3
                        'actual': e.get('actual'), 'forecast': e.get('consensus'),
                        'previous': e.get('previous'), 'signal': None,
                    })
        except Exception as ex:
            pass

    all_events.sort(key=lambda x: (x.get('date', ''), x.get('time', '')))
    return jsonify(all_events)
