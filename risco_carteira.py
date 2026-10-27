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
