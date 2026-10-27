"""Backlog #40/#41/#43 (26/10/2026). Eventos na janela, cenario de crise e concentracao por segmento.
Tudo em % -- nenhum valor em R$ sai daqui. Informativo: nao altera score nem posicoes."""
import json, os, time, datetime, requests, concurrent.futures as cf

BASE = os.path.dirname(os.path.abspath(__file__))
H = {'User-Agent': 'Mozilla/5.0'}

# Segmento de cada papel (editavel). Desconhecido -> 'Outros'.
SEGMENTOS = {
    'TEND3': 'Construcao / juros', 'IGTI11': 'Shoppings / juros', 'HYPE3': 'Farma / consumo domestico',
    'VBBR3': 'Combustiveis', 'BBAS3': 'Bancos', 'SMAL11': 'Small caps (indice)', 'PETR4': 'Petroleo',
    'BEEF3': 'Exportadoras (proteina)', 'POMO4': 'Exportadoras (industria)', 'CMIN3': 'Exportadoras (minerio)',
    'VALE3': 'Exportadoras (minerio)', 'ROXO34': 'BDR financeiro', 'BSLV39': 'BDR dolar (prata)', 'TSLA34': 'BDR dolar',
}
# Agrupamento maior, para o limite de concentracao: o que cai junto com o Brasil domestico.
GRUPO = {
    'Construcao / juros': 'Domestico', 'Shoppings / juros': 'Domestico', 'Farma / consumo domestico': 'Domestico',
    'Combustiveis': 'Domestico', 'Bancos': 'Domestico', 'Small caps (indice)': 'Domestico', 'Petroleo': 'Exportadoras / dolar',
    'Exportadoras (proteina)': 'Exportadoras / dolar', 'Exportadoras (industria)': 'Exportadoras / dolar',
    'Exportadoras (minerio)': 'Exportadoras / dolar', 'BDR financeiro': 'BDR', 'BDR dolar (prata)': 'BDR', 'BDR dolar': 'BDR',
}
LIMITE_GRUPO_PCT = 40.0   # aviso de concentracao (a definir pelo Victor)
BETA_PADRAO = 1.5          # papel sem retorno de referencia
# Retorno de 26/10 digitado a mao para papel sem serie diaria no Yahoo (BSLV39: ~+7,5% no dia, acompanhou o dolar)
RET_REF_MANUAL = {'BSLV39.SA': 7.5}


def _ler(nome):
    with open(os.path.join(BASE, nome), encoding='utf-8') as f:
        return json.load(f)


def eventos_na_janela(dias, hoje=None):
    """Eventos do calendario entre hoje (exclusive) e hoje+dias (inclusive)."""
    try:
        hoje = hoje or datetime.date.today()
        fim = hoje + datetime.timedelta(days=int(dias or 0))
        saida = []
        for e in _ler('eventos_calendario.json').get('eventos', []):
            d = datetime.date.fromisoformat(e['data'])
            if hoje < d <= fim:
                saida.append({'data': e['data'], 'nome': e['nome'], 'impacto': e.get('impacto'),
                              'confirmar': bool(e.get('confirmar'))})
        return sorted(saida, key=lambda x: x['data'])
    except Exception:
        return []


_PRECO = {}

def _preco(tk):
    ag = time.time()
    if tk in _PRECO and ag - _PRECO[tk][0] < 60:
        return _PRECO[tk][1]
    p = None
    try:
        j = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{tk}?interval=1d&range=5d',
                         headers=H, timeout=8).json()['chart']['result'][0]
        c = [x for x in j['indicators']['quote'][0]['close'] if x]
        p = float(c[-1])
    except Exception:
        p = None
    _PRECO[tk] = (ag, p)
    return p


def _posicoes_expostas(pos):
    """Estruturas ativas com KDO+quantidade e papeis que ficaram livres (ficou_com_papel)."""
    itens = []
    for a in pos.get('ativas', []):
        if a.get('kdo') and a.get('quantidade') and a.get('ticker'):
            itens.append({'id': a['id'], 'ticker': a['ticker'], 'qtd': a['quantidade'], 'entry': a.get('entry'),
                          'kdo': float(a['kdo']), 'tipo': 'estrutura'})
    for a in pos.get('encerradas', []):
        if a.get('ficou_com_papel') and a.get('quantidade') and a.get('ticker'):
            itens.append({'id': a['id'], 'ticker': a['ticker'], 'qtd': a['quantidade'], 'entry': a.get('entry'),
                          'kdo': None, 'tipo': 'papel livre'})
    return itens


def risco_carteira(pos, ibov_pct=-16.0):
    ref = _ler('pior_dia_10a.json').get('choque_ref', {})
    ib_ref = ref.get('ibov_pct')
    rets = dict(ref.get('retornos', {}))
    for k, v in RET_REF_MANUAL.items():
        rets.setdefault(k, v)
    itens = _posicoes_expostas(pos)
    tks = sorted({i['ticker'] if i['ticker'].endswith('.SA') else i['ticker'] + '.SA' for i in itens})
    with cf.ThreadPoolExecutor(8) as ex:
        precos = dict(zip(tks, ex.map(_preco, tks)))
    linhas = []
    for i in itens:
        tk = i['ticker'] if i['ticker'].endswith('.SA') else i['ticker'] + '.SA'
        curto = tk.replace('.SA', '')
        S = precos.get(tk)
        if not S:
            continue
        beta = (rets[tk] / ib_ref) if (ib_ref and tk in rets and ib_ref != 0) else BETA_PADRAO
        shock = ibov_pct * beta
        exp = S * i['qtd']
        seg = SEGMENTOS.get(curto, 'Outros')
        queda_kdo = round((1 - i['kdo'] / S) * 100, 1) if i['kdo'] else None
        toca = (queda_kdo is not None and -shock >= queda_kdo)
        linhas.append({'id': i['id'], 'ticker': curto, 'tipo': i['tipo'], 'segmento': seg, 'grupo': GRUPO.get(seg, 'Outros'),
                       'beta_crise': round(beta, 2), 'choque_pct': round(shock, 1), 'queda_ate_kdo_pct': queda_kdo,
                       'toca_kdo_no_cenario': toca, '_exp': exp})
    tot = sum(l['_exp'] for l in linhas) or 1.0
    for l in linhas:
        l['peso_pct'] = round(l['_exp'] / tot * 100, 1)
    perda = sum(l['_exp'] * l['choque_pct'] / 100 for l in linhas) / tot * 100 if linhas else 0.0
    grupos = {}
    segs = {}
    for l in linhas:
        grupos[l['grupo']] = grupos.get(l['grupo'], 0) + l['_exp'] / tot * 100
        segs[l['segmento']] = segs.get(l['segmento'], 0) + l['_exp'] / tot * 100
    for l in linhas:
        l.pop('_exp')
    return {
        'cenario': {'ibov_pct': ibov_pct, 'referencia': f"retorno de cada papel em {ref.get('data')} (IBOV {ib_ref}%) escalado ao cenario",
                    'beta_padrao': BETA_PADRAO},
        'perda_carteira_pct': round(perda, 1),
        'estruturas_que_tocam': sum(1 for l in linhas if l['toca_kdo_no_cenario']),
        'estruturas_total': sum(1 for l in linhas if l['tipo'] == 'estrutura'),
        'por_grupo_pct': {k: round(v, 1) for k, v in sorted(grupos.items(), key=lambda x: -x[1])},
        'por_segmento_pct': {k: round(v, 1) for k, v in sorted(segs.items(), key=lambda x: -x[1])},
        'limite_grupo_pct': LIMITE_GRUPO_PCT,
        'grupos_acima_do_limite': [k for k, v in grupos.items() if v > LIMITE_GRUPO_PCT],
        'posicoes': sorted(linhas, key=lambda x: -x['peso_pct']),
        'proximos_eventos': eventos_na_janela(60),
        'nota': 'Calls (PETR4, VALE3, BBAS3, ROXO34) ficam fora: o app nao tem quantidade/KDO delas. Informativo.',
    }


# ---------------------------------------------------------------- #44 recuperacao e calls cobertas
import math

def _serie(tk):
    """(fechamento de 26/10, ultimo preco, vol 30d sem o dia do choque, vol 30d com ele) via Yahoo diario."""
    try:
        j = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{tk}?interval=1d&range=3mo',
                         headers=H, timeout=10).json()['chart']['result'][0]
        ts = j['timestamp']; c = j['indicators']['quote'][0]['close']
        s = [(datetime.datetime.fromtimestamp(a, datetime.timezone(datetime.timedelta(hours=-3))).strftime('%Y-%m-%d'), b)
             for a, b in zip(ts, c) if b]
        ref = next((b for d, b in s if d == '2026-10-26'), None)
        r = [(s[i][0], math.log(s[i][1] / s[i - 1][1])) for i in range(1, len(s))]
        def vol(lst):
            if len(lst) < 5: return None
            m = sum(lst) / len(lst)
            return (sum((x - m) ** 2 for x in lst) / (len(lst) - 1)) ** 0.5 * 252 ** 0.5
        ult30 = r[-30:]
        return ref, s[-1][1], vol([x for d, x in ult30 if d != '2026-10-26']), vol([x for d, x in ult30])
    except Exception:
        return None, None, None, None


def _tk(t):
    return t if t.endswith('.SA') else t + '.SA'


def recuperacao(pos):
    """Progresso da recuperacao dos papeis acompanhados pelo app, em %: quanto da perda
    (preco medio -> fechamento de 26/10) ja foi devolvido. Sem R$."""
    itens = _posicoes_expostas(pos)
    with cf.ThreadPoolExecutor(8) as ex:
        ser = list(ex.map(lambda i: _serie(_tk(i['ticker'])), itens))
    linhas, ref_tot, agora_tot, custo_tot = [], 0.0, 0.0, 0.0
    for i, (ref, ult, _, _) in zip(itens, ser):
        if not (ref and ult and i.get('entry')):
            continue
        q, e = i['qtd'], i['entry']
        perda_ref = (ref - e) * q
        perda_agora = (ult - e) * q
        custo_tot += e * q; ref_tot += perda_ref; agora_tot += perda_agora
        rec = ((ult - ref) / (e - ref) * 100) if e > ref else None
        linhas.append({'ticker': i['ticker'].replace('.SA', ''), 'tipo': i['tipo'], 'preco_medio_vs_hoje_pct': round((ult / e - 1) * 100, 1),
                       'queda_26_10_vs_medio_pct': round((ref / e - 1) * 100, 1),
                       'recuperado_pct': round(rec, 1) if rec is not None else None,
                       'faltam_ate_medio_pct': round((e / ult - 1) * 100, 1) if ult < e else 0.0})
    rec_tot = ((agora_tot - ref_tot) / (-ref_tot) * 100) if ref_tot < 0 else None
    return {
        'carteira_acompanhada': {
            'perda_26_10_pct_do_custo': round(ref_tot / custo_tot * 100, 1) if custo_tot else None,
            'perda_agora_pct_do_custo': round(agora_tot / custo_tot * 100, 1) if custo_tot else None,
            'recuperado_pct_da_perda': round(rec_tot, 1) if rec_tot is not None else None},
        'posicoes': sorted(linhas, key=lambda x: (x['recuperado_pct'] is None, x['recuperado_pct'] or 0)),
        'nota': 'Só os papéis acompanhados pelo app (estruturas e papéis livres). Referência: fechamento de 26/10 contra o preço médio pago. Calls e dólares ficam fora. Sem valores em R$.'}


def _bs_call(S, K, T, r, s):
    d1 = (math.log(S / K) + (r + s * s / 2) * T) / (s * math.sqrt(T)); d2 = d1 - s * math.sqrt(T)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    return S * N(d1) - K * math.exp(-r * T) * N(d2), N(d1)


def calls_cobertas(pos, dias=15, juros=0.14):
    """Estudo de call coberta nos papeis livres (ficou_com_papel): para strikes acima do preco de hoje,
    premio TEORICO (Black-Scholes, vol 30d sem o dia do choque) em % do preco e resultado se exercida
    contra o preco medio. Nao e cotacao de mercado."""
    itens = [i for i in _posicoes_expostas(pos) if i['tipo'] == 'papel livre' and i.get('entry')]
    with cf.ThreadPoolExecutor(8) as ex:
        ser = list(ex.map(lambda i: _serie(_tk(i['ticker'])), itens))
    T = dias / 365.0
    out = []
    for i, (ref, ult, v_ex, v_com) in zip(itens, ser):
        if not (ult and v_ex):
            continue
        e = i['entry']
        linhas = []
        for dist in (0.0, 3.0, 6.0, 10.0):
            K = ult * (1 + dist / 100)
            prem, delta = _bs_call(ult, K, T, juros, v_ex)
            premio_pct = prem / ult * 100
            resultado_exercida = (K / e - 1) * 100 + premio_pct   # vs preco medio, se entregar o papel
            linhas.append({'strike_acima_do_preco_pct': dist, 'strike': round(K, 2),
                           'premio_teorico_pct': round(premio_pct, 2), 'chance_exercicio_pct': round(delta * 100, 0),
                           'se_exercida_vs_medio_pct': round(resultado_exercida, 1)})
        out.append({'ticker': i['ticker'].replace('.SA', ''), 'preco': round(ult, 2), 'preco_medio': e,
                    'vol_usada_pct': round(v_ex * 100, 0), 'vol_com_choque_pct': round(v_com * 100, 0) if v_com else None,
                    'strikes': linhas})
    return {'dias': dias, 'juros_pct': juros * 100, 'papeis': out,
            'nota': 'Prêmio teórico (Black-Scholes), vol realizada de 30d sem o dia 26/10; NÃO é cotação. Confirme se existe série de opção líquida no papel e o preço real na mesa.'}
