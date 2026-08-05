"""  # v10.16
Trader Desk — Proxy Server v10.16
Indicadores tecnicos + fundamentalistas + Monte Carlo + Futuros
Mudancas v10.16:
- /futures: adiciona busca real de Commodities (WTI/CL=F, Ouro/GC=F,
  Prata/SI=F, Cobre/HG=F) via Yahoo Finance, reaproveitando a funcao
  yquote() ja usada para VIX/indices. Antes a tabela de Commodities no
  frontend nunca tinha sido conectada a nenhuma fonte de dados real (so
  o HTML existia, sem nenhum codigo de busca) -- por isso preco e %
  nunca apareciam.
Mudancas v10.15:
- /montecarlo/condicional: put_resultado_fixo agora padroniza valores em
  R$ para 100 acoes (mesmo padrao didatico das outras 3 estruturas:
  bidirecional, retorno_controlado, call simples) — antes usava a
  quantidade real (qtd_acoes), o que quebrava a comparabilidade visual
  entre analises diferentes. O percentual de retorno e bate_meta
  continuam EXATAMENTE iguais aos reais (so o R$ exibido muda de escala).
Mudancas v10.14:
- /montecarlo/condicional: adiciona 'put_resultado_fixo' para venda de PUT
  simples (k_put, sem k_call/kdo). Mecanica diferente da call coberta:
  quando exercida, vira posicao NOVA (compra forcada), nao retorno
  fechado -- por decisao do usuario, NAO simulado via Monte Carlo. O
  retorno "se nao exercida" e um FATO FIXO (premio/capital_comprometido),
  calculado uma unica vez a partir do payload ('premio' + 'qtd_acoes'),
  ja que o valor do premio e conhecido desde o registro da foto. So a
  PROBABILIDADE de nao ser exercida usa Monte Carlo (prob_sucesso, ja
  existia). Tambem adiciona prob_sucesso para PUT (antes so existia para
  CALL).
Mudancas v10.13:
- BUGFIX CRITICO: /montecarlo/condicional estava FALTANDO o bloco de
  prob_retorno_faixas + simulacao_100_acoes para venda de CALL simples
  (k_call sem kdo/kuo) — essa extensao tinha sido adicionada por engano
  so em /montecarlo/posicao_ativa e /montecarlo (v10.11), nunca no
  /montecarlo/condicional, que e o endpoint usado pela aba "Em Analise".
  Por isso a foto ROXO34-simples (an_1782123970) continuava sem o pacote
  completo mesmo apos ter os campos exercicio/meta_pct. Corrigido agora:
  o terceiro caso (meta_pct + k_call sem kdo) foi adicionado, com a mesma
  protecao contra sobrescrita do bloco generico de simulacao_100_acoes
  (sim_100 = res.get(...) em vez de None) ja usada no posicao_ativa.
Mudancas v10.12:
- /montecarlo/condicional: corrige prob_call_exercida/prob_put_exercida
  para tambem respeitar 'exercicio' (americana usa max/min da trajetoria
  completa; europeia so preco final) — antes sempre usava so preco final
  (correto para europeia, mas subestimava o risco real para americana,
  mesmo bug ja corrigido em /montecarlo e /montecarlo/posicao_ativa).
  Campo 'exercicio' agora obrigatorio quando k_call/k_put presente sem
  kdo/kuo, mesma regra das outras rotas (sem padrao implicito).
Mudancas v10.11:
- /montecarlo (simples) e /montecarlo/posicao_ativa: estende
  prob_retorno_faixas + simulacao_100_acoes para venda de CALL coberta
  simples (k_call, sem kdo/kuo). Mecanica: se NAO exercida, retorno = a
  variacao real da acao (livre, sem teto/defesa); se EXERCIDA, retorno
  trava em (k_call/preco_foto - 1). Respeita 'exercicio' (americana usa
  max da trajetoria; europeia so preco final). So calcula quando o
  payload trouxer 'meta_pct' (a meta do usuario em %, ex 2.25). PUT
  vendida (k_put) NAO foi estendida -- por decisao do usuario, o caso
  "exercida" de uma PUT vira posicao nova (compra), nao e um retorno
  fechado; quando isso ocorrer de verdade, o usuario avisa e a foto migra
  manualmente para Encerradas com o desfecho real (sucesso/fracasso).
Mudancas v10.10:
- /montecarlo (estrutura SIMPLES): adiciona campo OBRIGATORIO 'exercicio'
  ('americana' ou 'europeia', SEM padrao implicito -- erro 400 se ausente).
  AMERICANA agora simula a trajetoria diaria completa (max/min) para
  detectar risco de exercicio em QUALQUER momento, igual ja era feito nas
  barreiras kdo/kuo das bidirecionais. EUROPEIA mantem o calculo anterior
  (so preco final, exercicio so no vencimento). Antes, TODAS as posicoes
  simples usavam a logica europeia mesmo quando a opcao real era americana
  (ex: ROXO34/ROXOG105), subestimando a probabilidade real de exercicio.
Mudancas v10.9:
- /indicators: corrige preco_anterior para BDRs (ex ROXO34) onde a brapi
  (plano free) nao traz regularMarketPreviousClose ou traz igual ao preco
  atual (mascarando variacao real do dia como zero). Agora usa o penultimo
  close do historico Yahoo ja buscado como fallback real, evitando que o
  frontend caia no fallback de "variacao de sessao" (_prevPrices, que so
  reflete a ultima leitura do app, nao o fechamento real do dia anterior).
Mudancas v10.8:
- Novo endpoint /montecarlo/posicao_ativa: para POSICOES REAIS ja ativas
  (positions.json), monta fan chart RETROATIVO REAL (preco historico real
  desde data_entrada até hoje, via Yahoo) + PROJECAO (banda de percentis de
  hoje até o vencimento). Preco de entrada extraido do proprio historico no
  dia de data_entrada (campo novo em positions.json), nao informado pelo
  payload. Reaproveita a mesma logica de faixas de retorno/simulacao_100_acoes
  do /montecarlo/condicional, mas usando o prazo TOTAL desde a entrada real.
Mudancas v10.7:
- /montecarlo/condicional agora retorna 'simulacao_100_acoes': traduz os
  percentuais abstratos da estrutura em R$ concretos sobre um lote fixo de
  100 acoes no preco_foto, nos cenarios possiveis (defesa/dentro/teto para
  bidirecional; prefixado/exposto para retorno controlado). Reaproveita os
  arrays de retorno ja simulados nos blocos de faixas (sem rodar Monte
  Carlo de novo); funciona para qualquer foto que tenha kdo+kuo+alavancagem
  +teto_retorno_pct OU kdo+ganho_prefixado_pct.
Mudancas v10.6:
- /montecarlo/condicional: prob_retorno_faixas agora tambem funciona para
  estruturas RETORNO CONTROLADO (barreira unica + ganho prefixado, ex
  TSLA34/ROXO34) -- antes so funcionava para bidirecional (kdo+kuo+
  alavancagem+teto_retorno_pct). Aceita 'ganho_prefixado_pct' no payload;
  payoff = ganho fixo se nao tocar a barreira (kdo), ou a variacao REAL da
  acao (sem garantia) se tocar. Retorna tambem 'prob_ganho_prefixado'.
Mudancas v10.5:
- /montecarlo/condicional agora retorna 'fan_chart' (banda de percentis
  p10-p90 do dia 0/preco_foto ao prazo_dias TOTAL, projetada com a vol
  atual, + serie de precos reais observados desde a data_foto via Yahoo,
  alinhados por timestamp) -- usado na aba Em Analise para visualizacao
  tipo fan chart com linha real navegando sobre a banda projetada, mesmo
  padrao ja usado em /btc/historico.
- Mesmo endpoint tambem aceita 'alavancagem' e 'teto_retorno_pct' opcionais
  no payload (estrutura bidirecional com payoff conhecido) e retorna
  'prob_retorno_faixas': probabilidade do retorno FINAL da estrutura cair
  em faixas fixas (<0%, 0-1%, 1-2%, 2-2.5%, >=meta), considerando o payoff
  real (alavancagem dentro do range, teto travado nas barreiras).
Mudancas v10.4:
- /montecarlo: corrige bug onde ROXO34 (e qualquer ticker que envie 'price' no
  payload por estar bloqueado no Yahoo via Render) nunca calculava GARCH nem
  comparativo_vol_historica, pois a busca de histórico (cl) era pulada quando
  o preco ja vinha do cliente. Agora busca historico via brapi como fallback
  nesse caso, igual ja era feito em /indicators.
Mudancas v10.3:
- EUCA4 (Eucatex PN) completo: LPA, VPA, ROE e P/L preenchidos via Fundamentus
  (ref. 19/06/2026); P/VP e DY tambem atualizados nessa mesma data (estavam
  desatualizados). Watchlist passa a ter 13 indicadores completos para todos
  os 16 ativos (antes EUCA4 tinha so 8, por falta desses 4 campos).
Mudancas v10.2:
- Novo endpoint /btc/historico: fan chart RETROATIVO de BTC — simula Monte
  Carlo (GARCH quando disponivel) a partir do preco de N dias atras (90/180/365)
  e compara com o preco real observado desde entao. Usado na aba Indicadores,
  junto com o fan chart futuro (/montecarlo/trajetorias) ja existente para BTC.
Mudancas v10.1:
- /montecarlo/barrier agora retorna comparativo_vol_historica (GARCH vs Vol.Simples),
  no mesmo padrao que ja existia em /montecarlo
- Frontend (app.js): card "MC GARCH" separado do "MC Vol.Simples" nas posicoes
  simples (PETR4/VALE3/BBAS3/ROXO34); AXIA3 (barreira) mostra o comparativo no
  texto da legenda, mantendo os 4 cards existentes
Mudancas v8.5:
- Cache BTC indicators/cycle (10-15 min)
- Range Yahoo BTC reduzido de 4y para 1y/2y (mais rapido no Render)
- Indicadores B3 com campo 'explicacao' textual
- Calendario com multiplos User-Agents + fallback TradingView
- HTML v10.1 embutido
"""
from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
import requests
import math
import time
import json
import re  # adicionado 23/06/2026 -- scraping de fallback do 8marketcap.com
from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait  # adicionado 23/06/2026 -- /us/concentracao; wait adicionado 03/07/2026 p/ orcamento de tempo no bulk DY de ETFs
from threading import Lock  # adicionado 23/06/2026 -- cache lazy do 8marketcap

try:
    import numpy as _np
    _NUMPY = True
except ImportError:
    _NUMPY = False

app = Flask(__name__)

def _retorno_bidirecional_full(variacao_full, tocou_alta_full, tocou_baixa_full,
                                teto_retorno, alavancagem,
                                downside_antes='positiva', downside_apos='protegida'):
    """
    ADICIONADO 15/07/2026 -- funcao UNICA e compartilhada pro payoff de
    estruturas bidirecionais/protecao Itau, usada nos 3 lugares do codigo
    que fazem esse calculo (/montecarlo/condicional, /montecarlo/
    posicao_ativa, /posicoes/ranking/<tipo>). Antes desta funcao, a mesma
    logica estava duplicada em 3 lugares -- e isso ja causou um bug real
    nesta sessao (corrigi 2 dos 3 lugares e esqueci o 3o, so achado
    quando o Victor reportou "tipo nao suportado" no ranking). Daqui pra
    frente, qualquer correcao de mecanica bidirecional muda so aqui.

    Modelo (confirmado contra 5 PDFs oficiais Itau -- AXIA3 Bidirecional
    x2, Protecao Total, Protecao Parcial):
    - Alta: sempre alavancada (variacao*alavancagem) ate tocar a barreira
      de alta (kuo), depois trava no teto_retorno fixo.
    - Baixa ANTES de tocar a barreira de baixa (kdo), controlado por
      downside_antes:
        'positiva'  -> retorno = -variacao (GANHA com a queda, 1:1) --
                       mecanica das AXIA3(A)/(B) bidirecionais existentes
                       e da nova "Bidirecional" 20/07/2026.
        'protegida' -> retorno = 0 (nem ganha nem perde) -- mecanica da
                       "Protecao Parcial" 20/07/2026.
    - Baixa DEPOIS de tocar kdo (barreira estourada), controlado por
      downside_apos:
        'protegida'     -> retorno = 0 (zera, nao perde mais nada) --
                            mecanica das AXIA3(A)/(B) e "Bidirecional".
        'perda_integral' -> retorno = variacao (perda real, igual acao
                            pura, SEM protecao nenhuma) -- mecanica da
                            "Protecao Parcial".
    - Se tocou_baixa_full for None (estrutura sem barreira de baixa
      nenhuma, ex "Protecao Total" -- kdo=None), a baixa NUNCA toca
      barreira; usa sempre downside_antes pra qualquer variacao negativa.
      Para "Protecao Total" o correto e' downside_antes='protegida'
      (capital 100% protegido em qualquer queda, conforme o PDF).
    """
    import numpy as np
    alta = np.where(tocou_alta_full, teto_retorno, variacao_full * alavancagem)
    if downside_antes == 'protegida':
        baixa_antes = np.zeros_like(variacao_full)
    else:
        baixa_antes = -variacao_full
    lado_alta_ou_baixa_antes = np.where(variacao_full >= 0, alta, baixa_antes)
    if tocou_baixa_full is None:
        return lado_alta_ou_baixa_antes
    if downside_apos == 'perda_integral':
        baixa_apos = variacao_full
    else:
        baixa_apos = np.zeros_like(variacao_full)
    return np.where(tocou_baixa_full, baixa_apos, lado_alta_ou_baixa_antes)

_IND_CACHE = {}
_BTC_CACHE = {}   # cache BTC indicators e cycle
# Adicionado 04/08/2026 -- usuario reportou ouro/prata/cobre "piscando" entre
# valores diferentes a cada atualizacao automatica (2min), preco E variacao %
# mudando sozinhos sem refresh manual. Causa raiz confirmada por pesquisa:
# COMEX tem deadline de rolagem do contrato de agosto/2026 em 29/07 -- estamos
# bem no meio dessa janela agora. O ticker "continuo" do Yahoo (GC=F/SI=F/HG=F)
# pode alternar entre o contrato antigo e o novo de forma inconsistente entre
# chamadas durante rolagem, sem ser um movimento real de mercado. Ja aconteceu
# antes (23/06, prata citada especificamente).
#
# CORRIGIDO 04/08/2026 (v2): a v1 usava cache em memoria por processo (90s).
# Usuario confirmou que continuou piscando MESMO com o cache -- causa provavel:
# Render pode rodar mais de 1 processo/worker, e cache em dict Python normal
# NAO e compartilhado entre processos, entao cada request podia cair num
# worker com um valor cacheado diferente. Trocado para uma abordagem que
# funciona independente de quantos processos existem: dentro da MESMA
# requisicao, consulta o Yahoo 3 vezes seguidas e usa o valor de 'prev' que
# aparecer mais (moda) -- se o Yahoo estiver alternando entre contrato
# antigo/novo de forma inconsistente, a maioria das 3 amostras tende a
# convergir no valor real, neutralizando o ruido na propria fonte em vez de
# tentar mascarar depois.
def yquote_estavel(ticker, n=3):
    """Wrapper de yquote() que consulta N vezes EM PARALELO e usa o 'prev'
    mais frequente (moda) -- usar para tickers sujeitos a ruido de rolagem de
    contrato (ouro/prata/cobre). Funciona mesmo com multiplos workers no
    servidor, diferente de um cache em memoria simples.
    CORRIGIDO 04/08/2026: v1 fazia as N chamadas em SEQUENCIA (uma depois da
    outra), o que somado as novas chamadas de spot fez o /futures inteiro
    estourar o timeout de 14s do frontend -- quando isso acontece a rota
    inteira falha e NADA carrega (nao so os tickers novos). Paralelizado com
    ThreadPoolExecutor: as N chamadas disparam ao mesmo tempo, tempo total
    fica proximo ao de 1 chamada (limitado pela mais lenta), nao a soma das N."""
    amostras = []
    with ThreadPoolExecutor(max_workers=n) as ex:
        futuros = [ex.submit(yquote, ticker) for _ in range(n)]
        for f in futuros:
            try:
                val = f.result(timeout=8)
                if val is not None:
                    amostras.append(val)
            except Exception:
                pass
    if not amostras:
        return None
    # moda do 'prev' (arredondado a 2 casas para agrupar valores praticamente
    # iguais que só diferem por ruido de ponto flutuante)
    from collections import Counter
    contagem = Counter(round(a['prev'], 2) for a in amostras)
    prev_mais_comum = contagem.most_common(1)[0][0]
    # usa o preco da amostra mais recente (ultima), mas o prev vencedor da moda
    return {'price': amostras[-1]['price'], 'prev': prev_mais_comum, 'time': amostras[-1].get('time')}

CORS(app)
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── BRAPI TOKEN ────────────────────────────────────────
# Token gratuito (15k req/mes) — necessario para fundamentais completos
# em qualquer ticker alem das 4 liberadas (PETR4/VALE3/ITUB4/MGLU3).
# Configurado via variavel de ambiente BRAPI_TOKEN no Render.
import os as _os
BRAPI_TOKEN = _os.environ.get('BRAPI_TOKEN', '47g4Z3SJELnK2wLwXgn1rw')
BRAPI_HEADERS = {'User-Agent':'Mozilla/5.0', 'Authorization': f'Bearer {BRAPI_TOKEN}'}

# ── AUTENTICACAO DAS ROTAS DE ESCRITA ──────────────────
# Adicionado 25/06/2026 -- item de backlog levantado pelo usuario: hoje
# qualquer pessoa que descobrisse a URL do app conseguia clicar em
# Rejeitar/Aprovar em qualquer analise (POST /analises e PUT /analises/
# <id>/status sao as DUAS UNICAS rotas que de fato escrevem em
# analises.json -- confirmado via grep em todas as rotas POST/PUT/DELETE
# do arquivo; /montecarlo/*, /btc/historico, /bs e /tv/* usam POST so para
# receber parametros no corpo, nao escrevem nada).
#
# PRIMEIRA CAMADA DE PROTECAO (token unico, nao multi-usuario ainda):
# token configurado via variavel de ambiente API_WRITE_TOKEN no Render
# (mesmo padrao ja usado para BRAPI_TOKEN). Rotas de ESCRITA exigem header
# 'Authorization: Bearer <token>' -- sem ele, 401. Rotas de LEITURA
# continuam abertas por decisao explicita do usuario (proteger leitura
# tambem fica para depois, se necessario).
#
# EVOLUCAO FUTURA (registrada, NAO implementada agora): se o app virar
# produto multi-usuario de verdade, cada usuario precisaria de token/login
# proprio, e os dados (analises.json/positions.json) precisariam ser POR
# USUARIO, nao um arquivo unico compartilhado no repo -- mudanca maior de
# arquitetura, fora do escopo desta correcao pontual.
API_WRITE_TOKEN = _os.environ.get('API_WRITE_TOKEN')

def _requer_auth_escrita(f):
    """Decorator que exige 'Authorization: Bearer <API_WRITE_TOKEN>' no
    header. Se API_WRITE_TOKEN nao estiver configurado no ambiente (Render),
    a rota fica ABERTA (fail-open) -- isso e intencional para nao quebrar
    o app caso a variavel de ambiente nao tenha sido configurada ainda,
    mas significa que o token PRECISA ser configurado no Render para a
    protecao funcionar de fato. Logar/avisar isso seria ideal numa
    iteracao futura."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not API_WRITE_TOKEN:
            return f(*args, **kwargs)  # fail-open se token nao configurado
        auth_header = request.headers.get('Authorization', '')
        token_recebido = auth_header.replace('Bearer ', '').strip()
        if token_recebido != API_WRITE_TOKEN:
            return jsonify({'error': 'Nao autorizado. Forneca o header Authorization: Bearer <token>.'}), 401
        return f(*args, **kwargs)
    return wrapper

# ── FUNDAMENTOS (fonte unica: fundamentos.json) ───────
# Prioridade 1 da modularizacao (03/07/2026): antes existiam 6 copias
# desses dados espalhadas pelo proxy.py (FUND, SETORES, vol_defaults,
# FUND_OVERRIDE, SETOR_MAP, FUND_EXTRA, FUND_OVERRIDE_GLOBAL) -- os dois
# primeiros eram inclusive codigo morto (nunca lidos). Agora tudo vem de
# fundamentos.json, lido uma vez no startup. Atualizacao trimestral dos
# fundamentos = 1 commit no JSON, sem tocar em codigo. Fallback embutido
# minimo garante que o app sobe mesmo se o arquivo faltar/corromper
# (principio: nenhuma rota depende de fonte externa para devolver 200).
_FUNDAMENTOS_FALLBACK = {
    'fund_data_ref': '2026-05-22',
    'fundamentos': {
        'PETR4': {'pvp': 1.65, 'dy': 6.42, 'lpa': 8.54, 'vpa': 29.76, 'roe': 22.5, 'pl': 5.8, 'ev_ebitda': 3.2, 'debt_ebitda': 0.8, 'margem': 18.3},
        'VALE3': {'pvp': 1.93, 'dy': 6.7, 'lpa': 3.51, 'vpa': 43.07, 'roe': 8.2, 'pl': 23.64, 'ev_ebitda': 4.1, 'debt_ebitda': 0.6, 'margem': 22.1},
    },
    'dy_extra': {},
    'setores': {'DEFAULT': {'nome': 'Geral', 'pl_medio': 12.0, 'pvp_medio': 2.0, 'roe_min': 12}},
    'sem_dy_relevante': ['ROXO34', 'TSLA34', 'BSLV39', 'AMZO34', 'PRIO3', 'ORVR3'],
    'vol_defaults': {'DEFAULT': 0.35},
}

def _carregar_fundamentos():
    try:
        import os as _os_f
        caminho = _os_f.path.join(_os_f.path.dirname(_os_f.path.abspath(__file__)), 'fundamentos.json')
        with open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        # validacao minima de estrutura antes de aceitar
        if 'fundamentos' in dados and 'setores' in dados:
            return dados
    except Exception:
        pass
    return _FUNDAMENTOS_FALLBACK

_FUNDX = _carregar_fundamentos()
FUND_DATA_REF_GLOBAL = _FUNDX.get('fund_data_ref', '2026-05-22')
FUNDAMENTOS = _FUNDX.get('fundamentos', {})
SETORES_MAP = _FUNDX.get('setores', {})
SEM_DY_RELEVANTE = set(_FUNDX.get('sem_dy_relevante', []))
VOL_DEFAULTS = _FUNDX.get('vol_defaults', {'DEFAULT': 0.35})
DY_GLOBAL = {t: f.get('dy') for t, f in FUNDAMENTOS.items() if f.get('dy') is not None}
DY_GLOBAL.update({k: v for k, v in _FUNDX.get('dy_extra', {}).items() if not k.startswith('_')})


# ── CALC TECNICO / GARCH ──────────────────────────────
# Extraido para motor.py em 03/07/2026 (Prioridade 2 da modularizacao,
# fase 1: nucleo estatistico puro, sem dependencia de Flask/rede/disco).
from motor import rsi, mm, ema, macd, bollinger, obv, graham, vol_hist, garch_11

# ── FONTES (Prioridade 2, fase 3, 04/07/2026) ──────────
# CDI, BTC onchain, Yahoo fundamentals/quotes, minerio de ferro,
# 8marketcap, e todo o cluster de FIIs (Fundamentus/classificacao/
# FI-Infra/StatusInvest). Ver docstring de fontes.py para a lista
# completa e o que ficou de proposito fora dela.
from fontes import (
    get_cdi, get_btc_onchain, yahoo_fundamentals, yquote, scrape_iron_ore_investing,
    fetch_commodities_hyperliquid,
    _8MARKETCAP_TICKER_ALT, _parsear_marketcap_8marketcap, _buscar_html_8marketcap_paginas,
    _FII_SEGMENTO_BASE, _FII_PALAVRAS_PAPEL, _FII_PALAVRAS_FOF,
    _classificar_segmento_fii, _classificar_risco_fii, _score_fii,
    _FII_PVP_MINIMO, _FII_TICKERS_INATIVOS, scrape_fiis_fundamentus,
    scrape_fi_infra_dados, scrape_statusinvest_ultimo_provento,
    scrape_statusinvest_historico_proventos, scrape_statusinvest_tickers_listagem,
    scrape_statusinvest_fundo_dados,
)


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

# ── YAHOO FUNDAMENTAIS (fallback gratuito p/ VPA/PVP/DY/ROE) ─


# ── FUTUROS ───────────────────────────────────────────
@app.route('/futures', methods=['GET'])
def get_futures():
    dji = yquote('%5EDJI')
    esf = yquote('ES%3DF')
    nqf = yquote('NQ%3DF')
    vix = yquote('%5EVIX')
    dxy = None
    win = None

    try:
        r_dxy = requests.post('https://scanner.tradingview.com/forex/scan',
            json={"symbols":{"tickers":["TVC:DXY"]},"columns":["close","change_abs"]}, timeout=6)
        if r_dxy.ok:
            items = r_dxy.json().get('data',[])
            if items:
                d = items[0].get('d',[])
                if d and d[0]:
                    close = round(float(d[0]),2)
                    chg = float(d[1]) if len(d)>1 and d[1] else 0
                    dxy = {'price':close,'prev':round(close-chg,2)}
    except: pass

    if not dxy:
        try:
            r_dxy2 = requests.post('https://scanner.tradingview.com/america/scan',
                json={"symbols":{"tickers":["TVC:DXY"]},"columns":["close","change_abs"]}, timeout=6)
            if r_dxy2.ok:
                items = r_dxy2.json().get('data',[])
                if items:
                    d = items[0].get('d',[])
                    if d and d[0]:
                        close = round(float(d[0]),2)
                        chg = float(d[1]) if len(d)>1 and d[1] else 0
                        dxy = {'price':close,'prev':round(close-chg,2)}
        except: pass

    try:
        r_win = requests.post('https://scanner.tradingview.com/futures/scan',
            json={"symbols":{"tickers":["BMFBOVESPA:WIN1!"]},"columns":["close","change_abs"]}, timeout=6)
        if r_win.ok:
            items = r_win.json().get('data',[])
            if items and items[0].get('d') and items[0]['d'][0]:
                d2 = items[0]['d']
                close = round(float(d2[0]),0)
                chg = float(d2[1]) if len(d2)>1 and d2[1] else 0
                win = {'price':close,'prev':round(close-chg,0),'source':'TV futures'}
    except: pass

    if not win:
        try:
            r_win2 = requests.post('https://scanner.tradingview.com/brazil/scan',
                json={"symbols":{"tickers":["BMFBOVESPA:WIN1!"]},"columns":["close","change_abs"]}, timeout=6)
            if r_win2.ok:
                items2 = r_win2.json().get('data',[])
                if items2 and items2[0].get('d') and items2[0]['d'][0]:
                    d3 = items2[0]['d']
                    close = round(float(d3[0]),0)
                    chg = float(d3[1]) if len(d3)>1 and d3[1] else 0
                    win = {'price':close,'prev':round(close-chg,0),'source':'TV brazil'}
        except: pass

    if not win:
        try:
            ibov = yquote('%5EBVSP')
            if ibov: win = {'price':round(ibov['price'],0),'prev':round(ibov['prev'],0),'source':'IBOV'}
        except: pass

    usd = yquote('USDBRL=X')

    # Commodities — futuros CME/COMEX, mesmo padrao yquote ja usado para
    # indices/vix (busca via Yahoo Finance, retorna price + prev close)
    cl = yquote('CL%3DF')      # Petroleo WTI
    # REVERTIDO 04/08/2026 (1a tentativa): usuario reportou que o app ficou
    # MAIS LENTO no geral (nao so gold/silver/copper) depois do sampling
    # paralelo + spot. Prioridade era estabilidade -- 1 chamada simples por
    # ticker, sem ThreadPoolExecutor extra a cada request.
    gold = yquote('GC%3DF')    # Ouro (futuro)
    silver = yquote('SI%3DF')  # Prata (futuro)
    copper = yquote('HG%3DF')  # Cobre (futuro)
    # RETENTADO 04/08/2026 (2a tentativa, mesma sessao): spot agora via
    # Hyperliquid em vez de Yahoo (ver docstring de fetch_commodities_hyperliquid
    # em fontes.py) -- 1 UNICA chamada sequencial pros 3 ativos de uma vez,
    # sem ThreadPoolExecutor, mesma licao do incidente acima. Fail-safe: em
    # qualquer erro a funcao retorna {}, entao gold_spot/silver_spot/
    # copper_spot caem em None automaticamente (mesmo comportamento de antes,
    # sem risco de regressao).
    #
    # DIAGNOSTICO TEMPORARIO (04/08/2026, 3a rodada): usuario testou no app
    # publicado e SPOT veio vazio ("--") apesar do FUT funcionar normal --
    # sinal de que a funcao esta caindo em algum caminho de erro. '_spot_debug'
    # exposto no payload so pra descobrir a causa real (falta de User-Agent?
    # IP do Render bloqueado? nomes de ativo diferentes do esperado?) em vez
    # de ficar chutando -- REMOVER assim que a causa for confirmada e corrigida.
    _hl_spot = fetch_commodities_hyperliquid()
    gold_spot = _hl_spot.get('gold_spot')
    silver_spot = _hl_spot.get('silver_spot')
    copper_spot = _hl_spot.get('copper_spot')
    _spot_debug = _hl_spot.get('_debug')
    # Adicionados 23/06/2026 -- selecionados por impacto direto/indireto nos
    # papeis da carteira (nao por liquidez generica): minerio de ferro e o
    # principal driver de VALE3; Brent e o benchmark internacional distinto
    # do WTI que tambem influencia a precificacao da Petrobras (PETR4); gas
    # natural fica como contexto energetico geral, sem ligacao direta a uma
    # posicao especifica. TIO=F (minerio, contrato de swap TSI 62% Fe CFR
    # China) tem liquidez/disponibilidade no Yahoo menos estavel que os
    # contratos CME tradicionais acima -- yquote ja retorna None com
    # seguranca se a busca falhar, sem quebrar o resto do payload.
    # Adicionado 25/06/2026 -- Minerio de Ferro: Investing.com como fonte
    # PRIMARIA (mais estavel, ver scrape_iron_ore_investing acima), Yahoo
    # (yquote) como FALLBACK se o scraping falhar (HTML mudou, exige JS,
    # rede indisponivel, etc). Nunca quebra o endpoint /futures inteiro.
    iron_ore = scrape_iron_ore_investing()
    if not iron_ore:
        iron_ore = yquote('TIO%3DF')  # Minerio de Ferro 62% Fe (TSI, CFR China) -- fallback
    brent = yquote('BZ%3DF')      # Petroleo Brent
    natgas = yquote('NG%3DF')     # Gas Natural

    # Adicionado 23/06/2026 -- Cotacoes: mercado Europeu e Asiatico
    # (futuros + indices apenas, sem acoes individuais -- mercado
    # americano ja cobertos acima/em outros endpoints). Tickers Yahoo
    # confirmados via busca (todos ^INDICE, mesmo padrao ja usado para
    # ^DJI/^VIX acima). Indices a vista escolhidos em vez de futuros
    # especificos de cada bolsa (ex: DAX futures via Q2JF.DE) porque
    # estes ultimos parecem ser instrumentos de nicho com liquidez/
    # disponibilidade incerta no Yahoo -- os indices a vista sao
    # extremamente liquidos e ja servem como termometro intraday.
    # REVERTIDO 04/08/2026: prefer_chart_prev=True (tentativa anterior) pioroU
    # o problema -- usuario confirmou Nikkei/KOSPI com % amplificada (5,57%
    # exibido vs 1,62% real) depois da mudanca, nao corrigida. Causa real
    # provavel: chartPreviousClose do Yahoo usa fronteira de dia baseada no
    # proprio fuso do Yahoo (nao o fuso local de cada bolsa), entao pode
    # referenciar um fechamento mais antigo que o cl[-2] da serie diaria.
    # Voltando ao comportamento padrao (cl[-2]), que usuario confirma que
    # "sempre funcionou" -- a defasagem real reportada era causada pelo
    # cache HTTP do /futures (corrigido separadamente com Cache-Control).
    dax = yquote('%5EGDAXI')      # Alemanha
    cac40 = yquote('%5EFCHI')     # Franca
    stoxx50 = yquote('%5ESTOXX50E')  # Zona do Euro
    ftse100 = yquote('%5EFTSE')   # Reino Unido
    nikkei = yquote('%5EN225')    # Japao
    hangseng = yquote('%5EHSI')   # Hong Kong
    sse = yquote('000001.SS')     # China (Shanghai)
    asx200 = yquote('%5EAXJO')    # Australia
    kospi = yquote('%5EKS11')     # Coreia do Sul

    resp = jsonify({'dji':dji,'esf':esf,'nqf':nqf,'win':win,'vix':vix,'dxy':dxy,'usd':usd,
                     'cl':cl,'gold':gold,'silver':silver,'copper':copper,
                     'gold_spot':gold_spot,'silver_spot':silver_spot,'copper_spot':copper_spot,
                     '_spot_debug':_spot_debug,  # TEMPORARIO 04/08/2026 -- remover apos diagnosticar
                     'dax':dax,'cac40':cac40,'stoxx50':stoxx50,'ftse100':ftse100,
                     'nikkei':nikkei,'hangseng':hangseng,'sse':sse,'asx200':asx200,'kospi':kospi,
                     'iron_ore':iron_ore,'brent':brent,'natgas':natgas,
                     # Adicionado 04/08/2026 -- usuario reportou TUDO defasado (indices,
                     # petroleo, ouro, futuros americanos), nao so Europa/Asia -- sintoma
                     # amplo demais pra ser 1 ticker com problema de fonte, mais coerente
                     # com HTTP caching (browser/proxy/CDN) servindo uma resposta antiga
                     # do /futures em vez de rodar a rota de novo. '_diag_time' cobre TODOS
                     # os tickers (nao so Europa/Asia) pra confirmar isso: se o timestamp
                     # bater com agora mas o preco na tela continuar velho, e cache de
                     # verdade (nao busca de dado); se o timestamp tambem for antigo, o
                     # problema esta na fonte (Yahoo) ou na propria rota nao estar rodando.
                     '_diag_time': {
                         'dji':dji.get('time') if dji else None,
                         'esf':esf.get('time') if esf else None,
                         'nqf':nqf.get('time') if nqf else None,
                         'vix':vix.get('time') if vix else None,
                         'cl':cl.get('time') if cl else None,
                         'gold':gold.get('time') if gold else None,
                         'silver':silver.get('time') if silver else None,
                         'copper':copper.get('time') if copper else None,
                         'brent':brent.get('time') if brent else None,
                         'natgas':natgas.get('time') if natgas else None,
                         'dax':dax.get('time') if dax else None,
                         'cac40':cac40.get('time') if cac40 else None,
                         'stoxx50':stoxx50.get('time') if stoxx50 else None,
                         'ftse100':ftse100.get('time') if ftse100 else None,
                         'nikkei':nikkei.get('time') if nikkei else None,
                         'hangseng':hangseng.get('time') if hangseng else None,
                         'sse':sse.get('time') if sse else None,
                         'asx200':asx200.get('time') if asx200 else None,
                         'kospi':kospi.get('time') if kospi else None,
                     },
                     '_diag_server_time': int(time.time())})
    # Forca no-cache -- rota antes nao setava nenhum header de cache, entao
    # navegador/proxy/CDN intermediario poderia legalmente reter e servir uma
    # resposta antiga do /futures sem essa instrucao explicita.
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp

# ── YIELDS DE TÍTULOS SOBERANOS ───────────────────────────────────────────────
# Adicionado 30/06/2026 -- backlog item 1.
# Curva de juros global: EUA (2y/10y/30y), Japão (10y), USD/JPY, Brasil (SELIC efetiva).
# EUA + USD/JPY: yquote() Yahoo -- mesmo padrão já usado para todos os outros tickers
# do app, provado estável (v8/finance/chart). Yields do Yahoo vêm em % anual diretamente
# (ex: ^TNX retorna 4.28 = 4.28% a.a.).
# Japão 10y: ^JGBS via Yahoo -- fallback TradingView scanner (FRED:JGBS10) se Yahoo falhar.
# Brasil SELIC: get_cdi() já existente (Bacen SGS 4389 anualizado) -- sem fonte adicional.
# Brasil NTN-B (IPCA+): TradingView scanner tentativa -- null explícito se falhar
#   (não há API pública gratuita confiável para precificação de NTN-B em tempo real;
#   ANBIMA publica dados mas via site não adequado para scraping confiável).
@app.route('/yields', methods=['GET'])
def get_yields():
    # ── EUA ──────────────────────────────────────────────
    # ^IRX = T-Bill 13 semanas (proxy do juro curto, ~3 meses)
    # ^FVX = T-Note 5 anos
    # ^TNX = T-Note 10 anos (benchmark global principal)
    # ^TYX = T-Bond 30 anos
    us_3m  = yquote('%5EIRX')   # ^IRX
    us_10y = yquote('%5ETNX')   # ^TNX
    us_30y = yquote('%5ETYX')   # ^TYX

    # ── USD/JPY ───────────────────────────────────────────
    usdjpy = yquote('USDJPY%3DX')  # USDJPY=X

    # ── JAPÃO 10y ─────────────────────────────────────────
    # ^JGBS não existe no Yahoo Finance -- vai sempre direto para o fallback TradingView.
    # TVC:JP10Y é o ticker padrão do TradingView para JGB 10 anos (yield soberano japonês).
    # Tentativa anterior usava FRED:JGBS10 -- não retornava dado (fonte FRED via TV
    # provavelmente sem cobertura nesse endpoint). TVC:JP10Y é o ticker usado nos charts
    # públicos do TradingView para esse papel, mais provável de funcionar no scanner.
    jp_10y = None
    for tv_ticker in ['TVC:JP10Y', 'FRED:JGBS10']:
        if jp_10y: break
        try:
            r_jgb = requests.post(
                'https://scanner.tradingview.com/global/scan',
                json={"symbols":{"tickers":[tv_ticker]},"columns":["close","change_abs"]},
                timeout=6)
            if r_jgb.ok:
                items = r_jgb.json().get('data',[])
                if items and items[0].get('d') and items[0]['d'][0]:
                    d2 = items[0]['d']
                    close = round(float(d2[0]),3)
                    chg = float(d2[1]) if len(d2)>1 and d2[1] else 0
                    jp_10y = {'price':close,'prev':round(close-chg,3),'source':tv_ticker}
        except: pass

    # ── BRASIL ───────────────────────────────────────────
    # SELIC meta: SGS 11 retorna % a.a. diretamente (decisão COPOM), sem conversão.
    # Fonte primária preferida porque retorna o número exato do COPOM (ex: 13.75).
    # get_cdi() (SGS 4389, CDI diário anualizado) fica como fallback -- valor quase
    # idêntico à SELIC meta mas calculado a partir da taxa overnight, pode divergir
    # levemente e tem o fallback hardcoded de 14.40 embutido.
    selic = None
    try:
        r_selic = requests.get(
            'https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados/ultimos/1?formato=json',
            timeout=5)
        if r_selic.ok:
            val = float(r_selic.json()[0]['valor'])
            if 5 <= val <= 25:  # sanity check: fora dessa faixa é dado suspeito
                selic = round(val, 2)
    except: pass
    if selic is None:
        selic = get_cdi()  # fallback: CDI anualizado (≈ SELIC efetiva) ou 14.40

    # NTN-B 2035 (IPCA+ longo) -- TradingView scanner tentativa
    # Retorna null se falhar -- não há fonte pública gratuita confiável para NTN-B em tempo real
    ntnb_10y = None
    try:
        r_ntnb = requests.post(
            'https://scanner.tradingview.com/brazil/scan',
            json={"symbols":{"tickers":["BMFBOVESPA:NTNB350101"]},"columns":["close","change_abs"]},
            timeout=6)
        if r_ntnb.ok:
            items = r_ntnb.json().get('data',[])
            if items and items[0].get('d') and items[0]['d'][0] and float(items[0]['d'][0]) > 0:
                d3 = items[0]['d']
                close = round(float(d3[0]),3)
                chg = float(d3[1]) if len(d3)>1 and d3[1] else 0
                ntnb_10y = {'price':close,'prev':round(close-chg,3),'source':'tradingview'}
    except: pass

    return jsonify({
        'us_3m':  us_3m,   # T-Bill 3 meses (^IRX)
        'us_10y': us_10y,  # T-Note 10 anos (^TNX)
        'us_30y': us_30y,  # T-Bond 30 anos (^TYX)
        'usdjpy': usdjpy,  # USD/JPY
        'jp_10y': jp_10y,  # JGB 10 anos (^JGBS)
        'br_selic': {'price': selic, 'prev': None, 'label': 'SELIC efetiva a.a.'},
        'br_ntnb':  ntnb_10y,  # NTN-B ~10y (IPCA+) -- null se fonte indisponível
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
@app.route('/montecarlo/barrier', methods=['POST'])
def run_montecarlo_barrier():
    try:
        import numpy as _np
        data = request.get_json() or {}
        ticker   = data.get('ticker', 'AXIA3.SA')
        entry    = float(data.get('entry', 54.31))
        kdo      = float(data.get('kdo', 43.39))
        kuo      = float(data.get('kuo', 68.48))
        T_days   = int(data.get('t_days', 113))
        n        = 3000
        steps    = max(T_days // 5, 10)
        S = float(data.get('price',0)) or None
        sigma = float(data.get('sigma', 0.35))
        usar_garch = data.get('usar_garch', True)
        garch_info = None
        cl = []
        if not S:
            for host in ['query1','query2']:
                try:
                    r2=requests.get(
                        f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y',
                        headers={'User-Agent':'Mozilla/5.0'},timeout=8)
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
        sigma_hist = sigma  # guarda vol. historica simples antes de qualquer ajuste GARCH
        if usar_garch and cl and len(cl) >= 60:
            try:
                garch_info = garch_11(cl, horizon_days=min(T_days, 60))
                if garch_info:
                    sigma = garch_info['vol_garch_projetada_pct'] / 100
            except: pass

        def _simula_barrier(sig):
            dt2 = 1/252.0
            drift2 = (0 - 0.5 * sig**2) * dt2
            vol_step2 = sig * (dt2**0.5)
            z2 = _np.random.standard_normal((n, steps))
            log_returns2 = drift2 + vol_step2 * z2
            paths2 = S * _np.exp(_np.cumsum(log_returns2, axis=1))
            max_p2 = _np.max(paths2, axis=1)
            min_p2 = _np.min(paths2, axis=1)
            kuo_hit2 = max_p2 >= kuo
            kdo_hit2 = min_p2 <= kdo
            no_barrier2 = ~kuo_hit2 & ~kdo_hit2
            return {
                'prob_sem_barreira': round(float(no_barrier2.mean() * 100), 2),
                'prob_barreira_alta': round(float(kuo_hit2.mean() * 100), 2),
                'prob_barreira_baixa': round(float(kdo_hit2.mean() * 100), 2),
            }

        # Simulacao principal (usa sigma final, que e GARCH se disponivel)
        res_principal = _simula_barrier(sigma)
        max_prices = None  # mantidos por compatibilidade, nao usados fora daqui
        min_prices = None

        # Simulacao comparativa com vol. historica simples (sempre calculada se GARCH foi usado)
        comparativo_hist = _simula_barrier(sigma_hist) if (garch_info and sigma_hist != sigma) else None

        return jsonify({
            'ticker': ticker, 'preco_atual': round(S, 2),
            'entry': entry, 'kdo': kdo, 'kuo': kuo, 't_days': T_days,
            'volatilidade_historica_pct': round(sigma * 100, 2),
            'volatilidade_historica_simples_pct': round(sigma_hist * 100, 2),
            'garch': garch_info,
            'comparativo_vol_historica': comparativo_hist,
            'prob_sem_barreira': res_principal['prob_sem_barreira'],
            'prob_barreira_alta': res_principal['prob_barreira_alta'],
            'prob_barreira_baixa': res_principal['prob_barreira_baixa'],
            'cenarios': n, 'engine': 'numpy-paths'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/montecarlo/trajetorias', methods=['POST'])
def run_montecarlo_trajetorias():
    """
    Gera trajetorias completas de Monte Carlo (nao so o resultado final) para
    visualizacao em fan chart na watchlist. Usa vol. GARCH(1,1) quando disponivel.

    Retorna:
    - trajetorias: lista de ~20 series de preco, uma por dia, para exibir como
      linhas individuais no grafico (efeito visual do "leque" de cenarios)
    - percentis: p10/p25/p50/p75/p90 por dia, para desenhar a banda de
      confianca central (mais robusto que olhar so as linhas individuais)
    - dias: array de indices de dia (eixo X)

    Nota tecnica: o modelo geometrico (GBM) usado aqui NAO tem reversao de
    preco — a incerteza cresce com sqrt(tempo), entao o "cone" sempre se abre,
    nunca converge de volta. Isso e esperado e correto matematicamente; nao
    confundir com convergencia de preco-alvo (que e outro calculo, estatico).
    """
    try:
        import numpy as np
        data = request.get_json() or {}
        ticker = data.get('ticker', 'PETR4.SA')
        T_days = int(data.get('t_days', 21))
        n_linhas = 20  # trajetorias individuais exibidas (nao confundir com n_sim)
        n_sim = 2000    # simulacoes usadas para os percentis (mais preciso)

        S = float(data.get('price', 0)) or None
        sigma = float(data.get('sigma', 0)) or None
        cl = []

        if not S or not sigma:
            for host in ['query1', 'query2']:
                try:
                    r = requests.get(
                        f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y',
                        headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                    if r.ok:
                        d = r.json()
                        meta = d['chart']['result'][0]['meta']
                        raw_cl = d['chart']['result'][0]['indicators']['quote'][0]['close']
                        cl = [c for c in raw_cl if c is not None]
                        if not S:
                            S = float(meta.get('regularMarketPrice', cl[-1] if cl else 0))
                        break
                except: continue

        if not S or S <= 0:
            return jsonify({'error': f'Nao foi possivel obter preco de {ticker}'}), 500

        garch_info = None
        if not sigma:
            if cl and len(cl) >= 60:
                try:
                    garch_info = garch_11(cl, horizon_days=min(T_days, 60))
                    if garch_info:
                        sigma = garch_info['vol_garch_projetada_pct'] / 100
                except: pass
            if not sigma:
                sigma = vol_hist(cl) if cl else 0.35

        dt = 1 / 252.0
        drift = -0.5 * sigma**2 * dt
        vol_step = sigma * math.sqrt(dt)

        # Simulacao para percentis (mais cenarios, mais precisao estatistica)
        z_full = np.random.standard_normal((n_sim, T_days))
        log_ret_full = drift + vol_step * z_full
        paths_full = S * np.exp(np.cumsum(log_ret_full, axis=1))
        paths_full = np.hstack([np.full((n_sim, 1), S), paths_full])  # dia 0 = preco atual

        percentis = {}
        for p in [10, 25, 50, 75, 90]:
            percentis[f'p{p}'] = np.percentile(paths_full, p, axis=0).round(2).tolist()

        # Subconjunto de trajetorias individuais para exibir como linhas (efeito visual)
        idx_amostra = np.random.choice(n_sim, size=min(n_linhas, n_sim), replace=False)
        trajetorias = paths_full[idx_amostra].round(2).tolist()

        return jsonify({
            'ticker': ticker,
            'preco_atual': round(S, 2),
            'sigma_usado_pct': round(sigma * 100, 2),
            'garch': garch_info,
            't_days': T_days,
            'dias': list(range(T_days + 1)),
            'trajetorias': trajetorias,
            'percentis': percentis,
            'cenarios_percentis': n_sim,
            'cenarios_exibidos': len(trajetorias),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/btc/historico', methods=['POST'])
def run_btc_historico():
    """
    Fan chart RETROATIVO para BTC: simula Monte Carlo a partir do preco de
    N dias atras (usando a vol. GARCH/historica conhecida naquele ponto) e
    compara com o preco REAL observado desde entao.

    Diferente de /montecarlo/trajetorias (que projeta o FUTURO a partir de
    hoje), aqui o ponto de partida e no passado e o "resultado real" ja
    aconteceu — serve para visualizar como o leque de cenarios passados se
    comparou com o caminho que o preco de fato seguiu.

    Retorna:
    - precos_reais: serie de preco de fechamento real, dia a dia, da janela
    - trajetorias: ~20 simulacoes Monte Carlo partindo do preco no dia 0
      da janela, com a vol. conhecida naquele momento
    - percentis: p10/p25/p50/p75/p90 das simulacoes (mais robusto)
    - dias: indices de dia (eixo X)
    """
    try:
        import numpy as np
        data = request.get_json() or {}
        T_days = int(data.get('t_days', 365))
        T_days = min(T_days, 365)  # limite de seguranca (janela maxima disponivel)
        n_linhas = 20
        n_sim = 2000

        cl_full = []
        for host in ['query1', 'query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1d&range=2y',
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if r.ok:
                    d = r.json()
                    raw_cl = d['chart']['result'][0]['indicators']['quote'][0]['close']
                    cl_full = [c for c in raw_cl if c is not None]
                    break
            except: continue

        if not cl_full or len(cl_full) < T_days + 60:
            return jsonify({'error': 'Historico insuficiente de BTC-USD para essa janela'}), 500

        # Janela de interesse: os ultimos T_days+1 precos (dia 0 = inicio da janela)
        janela = cl_full[-(T_days + 1):]
        S0 = float(janela[0])
        precos_reais = [round(float(p), 2) for p in janela]

        # Vol. conhecida NO PONTO DE PARTIDA (usa apenas dados disponiveis até ali,
        # sem "olhar para o futuro" — senao a simulacao retroativa seria injusta)
        cl_ate_inicio = cl_full[:-(T_days)] if T_days < len(cl_full) else cl_full[:1]
        garch_info = None
        sigma = None
        if len(cl_ate_inicio) >= 60:
            try:
                garch_info = garch_11(cl_ate_inicio, horizon_days=min(T_days, 60))
                if garch_info:
                    sigma = garch_info['vol_garch_projetada_pct'] / 100
            except: pass
        if not sigma:
            sigma = vol_hist(cl_ate_inicio) if len(cl_ate_inicio) >= 22 else 0.45

        dt = 1 / 252.0
        drift = -0.5 * sigma**2 * dt
        vol_step = sigma * math.sqrt(dt)

        z_full = np.random.standard_normal((n_sim, T_days))
        log_ret_full = drift + vol_step * z_full
        paths_full = S0 * np.exp(np.cumsum(log_ret_full, axis=1))
        paths_full = np.hstack([np.full((n_sim, 1), S0), paths_full])

        percentis = {}
        for p in [10, 25, 50, 75, 90]:
            percentis[f'p{p}'] = np.percentile(paths_full, p, axis=0).round(2).tolist()

        idx_amostra = np.random.choice(n_sim, size=min(n_linhas, n_sim), replace=False)
        trajetorias = paths_full[idx_amostra].round(2).tolist()

        return jsonify({
            'ticker': 'BTC-USD',
            'preco_inicial': round(S0, 2),
            'preco_atual': round(float(janela[-1]), 2),
            'sigma_usado_pct': round(sigma * 100, 2),
            'garch': garch_info,
            't_days': T_days,
            'dias': list(range(T_days + 1)),
            'precos_reais': precos_reais,
            'trajetorias': trajetorias,
            'percentis': percentis,
            'cenarios_percentis': n_sim,
            'cenarios_exibidos': len(trajetorias),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/montecarlo/condicional', methods=['POST'])
def run_montecarlo_condicional():
    """
    Probabilidade CONDICIONAL para uma "foto" congelada de cenario (Fase 2 —
    motor de decisao pre-trade). Diferente de /montecarlo (que sempre projeta
    a partir de HOJE com o prazo TOTAL), esta rota recebe um cenario que foi
    fixado no passado e calcula a continuacao a partir de onde a trajetoria
    real ESTA AGORA, usando apenas o tempo que RESTA do prazo original.

    Parametros esperados (JSON):
    - ticker: ex. 'ITUB4.SA'
    - preco_foto: preco do ativo no momento em que a foto foi tirada
    - data_foto: data ISO (YYYY-MM-DD) em que a foto foi tirada
    - prazo_dias: prazo ORIGINAL total escolhido na foto (ex. 21/30/60/90)
    - k_call / k_put / kdo / kuo: limites do cenario (opcionais, dependendo
      do tipo de estrutura — call simples, bidirecional/barreira, etc.)

    Retorna:
    - preco_foto, preco_atual, dias_passados, dias_restantes
    - prob_* : probabilidades calculadas com o tempo que RESTA, partindo do
      preco ATUAL (nao do preco da foto) — isso e o que torna "condicional"
    - garch: info do GARCH usado (vol. atual, nao a vol. da epoca da foto)
    - fora_do_prazo: true se dias_passados >= prazo_dias (foto vencida)
    - fan_chart: banda de percentis (p10-p90) em PRECO do ativo, do dia 0 ao
      prazo_dias total (projetada a partir do preco_foto com a vol. atual),
      junto com a serie de precos REAIS observados desde a data_foto até
      hoje — para visualizacao tipo "fan chart" com linha real navegando
      sobre a banda projetada (mesmo padrao usado em /btc/historico)
    - prob_retorno_faixas: probabilidade do RETORNO FINAL DA ESTRUTURA cair
      em cada faixa fixa (<0%, 0-1%, 1-2%, 2-2.5% [meta], >2.5%). Calculado
      em dois modos, dependendo do payload:
      (a) BIDIRECIONAL: payload com 'alavancagem' + 'teto_retorno_pct' +
          kdo/kuo — payoff = variacao*alavancagem dentro do range, 0 na
          defesa, teto_retorno_pct travado na barreira de alta.
      (b) RETORNO CONTROLADO (barreira unica): payload com
          'ganho_prefixado_pct' + kdo (sem alavancagem/teto) — payoff =
          ganho_prefixado_pct fixo SE nao tocar kdo, ou a variacao REAL da
          acao (sem garantia) SE tocar. Tambem retorna 'prob_ganho_prefixado'
          (chance de nao tocar a barreira e garantir o prefixado).
    """
    try:
        import numpy as np
        from datetime import datetime as _dt
        data = request.get_json() or {}
        ticker = data.get('ticker', 'BBAS3.SA')
        preco_foto = float(data.get('preco_foto', 0))
        data_foto_str = data.get('data_foto')
        prazo_dias = int(data.get('prazo_dias', 21))
        K_call = float(data['k_call']) if data.get('k_call') else None
        K_put = float(data['k_put']) if data.get('k_put') else None
        kdo = float(data['kdo']) if data.get('kdo') else None
        kuo = float(data['kuo']) if data.get('kuo') else None
        n = 5000

        if not data_foto_str:
            return jsonify({'error': 'data_foto e obrigatoria (formato YYYY-MM-DD)'}), 400
        try:
            data_foto = _dt.strptime(data_foto_str[:10], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'data_foto invalida, use YYYY-MM-DD'}), 400

        hoje_str = data.get('data_referencia')
        # Adicionado 05/07/2026 (pedido do usuario, painel "quanto ficou na
        # mesa" em Encerradas) -- permite ancorar o calculo em uma data
        # PASSADA (ex: data_encerramento) em vez de sempre "agora". Quando
        # nao enviado, comportamento IDENTICO ao original (usa hoje real).
        if hoje_str:
            try:
                hoje = _dt.strptime(hoje_str[:10], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'data_referencia invalida, use YYYY-MM-DD'}), 400
        else:
            hoje = _dt.now().date()
        dias_passados = (hoje - data_foto).days
        dias_restantes = max(prazo_dias - dias_passados, 0)
        fora_do_prazo = dias_passados >= prazo_dias

        # Busca preco ATUAL + historico (mesmo padrao de fallback ja usado em /montecarlo:
        # Yahoo primeiro, brapi com range=3mo se Yahoo falhar/bloquear o ticker)
        S = None
        cl = []
        ts = []  # timestamps paralelos a cl, usados para montar a janela real desde a foto
        sigma = 0.35
        for host in ['query1', 'query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y',
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                if r.ok:
                    d = r.json()
                    meta = d['chart']['result'][0]['meta']
                    raw_cl = d['chart']['result'][0]['indicators']['quote'][0]['close']
                    raw_ts = d['chart']['result'][0].get('timestamp', [])
                    cl = [c for c in raw_cl if c is not None]
                    # mantem ts alinhado: só os indices onde close nao e None
                    ts = [t for t, c in zip(raw_ts, raw_cl) if c is not None]
                    S = float(meta.get('regularMarketPrice', cl[-1] if cl else 0))
                    if cl: sigma = vol_hist(cl)
                    break
            except: continue
        if not S:
            try:
                symbol_bp = ticker.replace('.SA', '').upper()
                rb = requests.get(
                    f'https://brapi.dev/api/quote/{symbol_bp}?range=3mo&interval=1d&fundamental=true',
                    headers=BRAPI_HEADERS, timeout=10)
                if rb.ok:
                    rd = rb.json().get('results', [{}])[0]
                    S = rd.get('regularMarketPrice')
                    hist = rd.get('historicalDataPrice', [])
                    cl_bp = [x['close'] for x in hist if x.get('close')]
                    if cl_bp:
                        cl = cl_bp
                        sigma = vol_hist(cl)
            except: pass

        # Adicionado 05/07/2026 -- se preco_referencia foi enviado, usa ele
        # como ancora da projecao em vez do preco AO VIVO buscado acima
        # (que so serve para estimar volatilidade/sigma nesse caso -- ver
        # LIMITACAO ASSUMIDA no docstring da rota). Precisa ter chegado ate
        # aqui com algum preco valido primeiro (senao nao ha sigma pra usar).
        preco_referencia = data.get('preco_referencia')
        if preco_referencia:
            try:
                preco_referencia = float(preco_referencia)
                if preco_referencia > 0:
                    S = preco_referencia
            except (TypeError, ValueError):
                pass

        if not S or S <= 0:
            return jsonify({'error': f'Nao foi possivel obter preco atual de {ticker}'}), 500

        sigma_hist = sigma
        garch_info = None
        min_pontos = 50 if (len(cl) < 60) else 60
        if cl and len(cl) >= min_pontos:
            try:
                garch_info = garch_11(cl, horizon_days=min(max(dias_restantes, 1), 60))
                if garch_info:
                    sigma = garch_info['vol_garch_projetada_pct'] / 100
            except: pass

        if fora_do_prazo or dias_restantes == 0:
            # Prazo original ja esgotado — nao ha "tempo restante" para simular.
            # Retorna so o estado factual (preco atual vs faixas), sem nova simulacao.
            return jsonify({
                'ticker': ticker, 'preco_foto': preco_foto, 'preco_atual': round(S, 2),
                'data_foto': data_foto_str, 'dias_passados': dias_passados,
                'dias_restantes': 0, 'prazo_dias': prazo_dias, 'fora_do_prazo': True,
                'volatilidade_historica_pct': round(sigma * 100, 2),
                'garch': garch_info,
                'mensagem': 'Prazo original ja esgotado — sem tempo restante para nova simulacao condicional.'
            })

        T = dias_restantes / 252.0
        sqT = math.sqrt(T)
        drift = -0.5 * sigma**2 * T
        z = np.random.standard_normal(n)
        ST = S * np.exp(drift + sigma * sqT * z)

        res = {
            'ticker': ticker, 'preco_foto': preco_foto, 'preco_atual': round(S, 2),
            'data_foto': data_foto_str, 'dias_passados': dias_passados,
            'dias_restantes': dias_restantes, 'prazo_dias': prazo_dias, 'fora_do_prazo': False,
            'volatilidade_historica_pct': round(sigma * 100, 2),
            'volatilidade_historica_simples_pct': round(sigma_hist * 100, 2),
            'garch': garch_info,
            'cenarios': n, 'engine': 'numpy',
            'calculo_retroativo': bool(hoje_str),
            'data_referencia_usada': hoje.isoformat(),
        }
        if hoje_str:
            res['nota_limitacao'] = ('Calculo ancorado em data passada (data_referencia), mas a '
                'volatilidade usada e a ATUAL (nao a de entao) -- Yahoo nao da forma simples de '
                'reconstruir volatilidade historica "como era vista" numa data passada sem dados '
                'pagos. Limitacao assumida, documentada.')

        if K_call is not None or K_put is not None or (kdo is not None and kuo is not None):
            # Precisa da trajetoria completa quando a opcao for AMERICANA
            # (exercicio possivel em qualquer momento) ou quando houver
            # barreira (kdo/kuo, sempre monitorada continuamente). Campo
            # 'exercicio' e OBRIGATORIO quando k_call/k_put estiver presente
            # SEM kdo/kuo (mesma regra do /montecarlo principal).
            exercicio = data.get('exercicio')
            precisa_exercicio = (K_call is not None or K_put is not None) and kdo is None
            if precisa_exercicio and exercicio not in ('americana', 'europeia'):
                return jsonify({'error': "campo 'exercicio' obrigatorio quando k_call/k_put presente (sem kdo/kuo): 'americana' ou 'europeia'"}), 400

            steps = max(dias_restantes, 1)
            dt2 = 1 / 252.0
            drift2 = -0.5 * sigma**2 * dt2
            vol_step2 = sigma * math.sqrt(dt2)
            z2 = np.random.standard_normal((n, steps))
            paths = S * np.exp(np.cumsum(drift2 + vol_step2 * z2, axis=1))
            max_p = np.max(paths, axis=1)
            min_p = np.min(paths, axis=1)
            ST_path = paths[:, -1]

            if K_call is not None:
                call_ex = (max_p > K_call) if exercicio == 'americana' else (ST_path > K_call)
                res['prob_call_exercida'] = round(float(call_ex.mean() * 100), 2)
                res['prob_sucesso'] = round(float((~call_ex).mean() * 100), 2)
                res['exercicio'] = exercicio
            if K_put is not None:
                put_ex = (min_p < K_put) if exercicio == 'americana' else (ST_path < K_put)
                res['prob_put_exercida'] = round(float(put_ex.mean() * 100), 2)
                res['prob_sucesso'] = round(float((~put_ex).mean() * 100), 2)
                res['exercicio'] = exercicio
        if kuo is not None:
            # Para barreira, precisamos do caminho completo, nao so do ponto final —
            # roda uma simulacao de trajetoria (steps diarios) so para esse caso
            steps = max(dias_restantes, 1)
            dt2 = 1 / 252.0
            drift2 = -0.5 * sigma**2 * dt2
            vol_step2 = sigma * math.sqrt(dt2)
            z2 = np.random.standard_normal((n, steps))
            paths = S * np.exp(np.cumsum(drift2 + vol_step2 * z2, axis=1))
            max_p = np.max(paths, axis=1)
            min_p = np.min(paths, axis=1)
            kuo_hit = max_p >= kuo
            # CORRIGIDO 15/07/2026 -- suporte a kdo=None (estrutura
            # "Protecao Total", sem barreira de baixa nenhuma): antes,
            # esse bloco inteiro exigia kdo != None, entao a secao 1
            # inteira (probabilidades) sumia da tela pra essa estrutura --
            # so achado porque o Victor reportou que faltavam as secoes 2
            # e 3 tambem (mesma causa raiz, blocos diferentes). Com kdo
            # None, a barreira de baixa nunca toca (prob=0%).
            kdo_hit = (min_p <= kdo) if kdo is not None else np.zeros_like(min_p, dtype=bool)
            no_barrier = ~kuo_hit & ~kdo_hit
            res['prob_sem_barreira'] = round(float(no_barrier.mean() * 100), 2)
            res['prob_barreira_alta'] = round(float(kuo_hit.mean() * 100), 2)
            res['prob_barreira_baixa'] = round(float(kdo_hit.mean() * 100), 2)
            res['kdo'] = kdo
            res['kuo'] = kuo

        # ── FAN CHART: banda de percentis do DIA 0 (preco_foto) ao prazo_dias
        # TOTAL, projetada com a vol. ATUAL — junto com a serie de precos REAIS
        # observados desde a data_foto até hoje. Permite visualizar a linha real
        # "navegando" sobre a banda projetada, no mesmo padrao de /btc/historico.
        try:
            n_fan = 2000
            n_linhas_fan = 20
            dt_fan = 1 / 252.0
            drift_fan = -0.5 * sigma**2 * dt_fan
            vol_step_fan = sigma * math.sqrt(dt_fan)
            z_fan = np.random.standard_normal((n_fan, prazo_dias))
            paths_fan = preco_foto * np.exp(np.cumsum(drift_fan + vol_step_fan * z_fan, axis=1))
            paths_fan = np.hstack([np.full((n_fan, 1), preco_foto), paths_fan])

            percentis_fan = {}
            for p in [10, 25, 50, 75, 90]:
                percentis_fan[f'p{p}'] = np.percentile(paths_fan, p, axis=0).round(2).tolist()

            idx_amostra_fan = np.random.choice(n_fan, size=min(n_linhas_fan, n_fan), replace=False)
            trajetorias_fan = paths_fan[idx_amostra_fan].round(2).tolist()

            # Serie de precos REAIS desde a data_foto até hoje (usa o historico
            # já buscado acima, alinhado por timestamp; ts esta em segundos epoch)
            precos_reais_fan = None
            if ts and cl:
                from datetime import datetime as _dt2, timezone as _tz2
                foto_epoch = _dt2.combine(data_foto, _dt2.min.time(), tzinfo=_tz2.utc).timestamp()
                idx_inicio = None
                for i, t in enumerate(ts):
                    if t >= foto_epoch:
                        idx_inicio = i
                        break
                if idx_inicio is not None:
                    # CORRIGIDO (23/06/2026): antes usava dias_passados+1 (dias
                    # CORRIDOS) para fatiar cl[], que so tem 1 ponto por PREGAO
                    # UTIL -- isso desalinhava sempre que o periodo cruzava fim
                    # de semana/feriado (slice pegava pontos demais). Agora pega
                    # TODO o resto do historico a partir da foto: o Yahoo nunca
                    # retorna pregao futuro, entao isso sempre da exatamente os
                    # pregoes reais decorridos, sem contar dias sem pregao.
                    janela_real = cl[idx_inicio:]
                    precos_reais_fan = [round(float(p), 2) for p in janela_real]
                    # ADICIONADO 30/06/2026 -- BDRs/ativos de baixissima
                    # liquidez (ex: BSLV39) podem ter so 1 ponto no historico
                    # diario desde a foto, mesmo com varios dias passados e
                    # negociacao real (confirmado pelo usuario via TradingView/
                    # StatusInvest) -- o Yahoo so atualiza o array de
                    # fechamentos diarios quando ha pregao "fechado"
                    # registrado, mas 'S' (preco atual, ja buscado acima via
                    # meta.regularMarketPrice) costuma estar mais atualizado.
                    # Garante pelo menos 2 pontos (foto + hoje) sempre que S
                    # for diferente do ultimo ponto historico, para a linha
                    # real conseguir aparecer no grafico em vez de ficar
                    # "presa" com 1 ponto so.
                    if precos_reais_fan and round(float(S), 2) != precos_reais_fan[-1]:
                        precos_reais_fan.append(round(float(S), 2))

            res['fan_chart'] = {
                'dias': list(range(prazo_dias + 1)),
                'percentis': percentis_fan,
                'trajetorias': trajetorias_fan,
                'precos_reais': precos_reais_fan,
                'preco_foto': round(preco_foto, 2),
            }
        except Exception:
            res['fan_chart'] = None

        # ── FAIXAS DE PROBABILIDADE DE RETORNO DA ESTRUTURA (faixas fixas:
        # <0%, 0-1%, 1-2%, 2-2.5% [meta], >2.5%) — só calculado quando o
        # payload trouxer 'alavancagem' e 'teto_retorno_pct' (estrutura
        # bidirecional com payoff conhecido). Usa o tempo TOTAL original
        # (prazo_dias, projetado do preco_foto), nao o tempo restante —
        # representa "qual seria o resultado FINAL da estrutura completa".
        alavancagem = data.get('alavancagem')
        teto_retorno_pct = data.get('teto_retorno_pct')
        retorno_full = None
        tocou_baixa_full = None
        tocou_alta_full = None
        teto_retorno = None
        if alavancagem is not None and teto_retorno_pct is not None and kuo is not None:
            try:
                alavancagem = float(alavancagem)
                teto_retorno = float(teto_retorno_pct) / 100
                n_faixas = 20000
                z_full = np.random.standard_normal((n_faixas, prazo_dias))
                paths_full = preco_foto * np.exp(np.cumsum(drift_fan + vol_step_fan * z_full, axis=1))
                max_full = np.max(paths_full, axis=1)
                min_full = np.min(paths_full, axis=1)
                ST_full = paths_full[:, -1]
                tocou_baixa_full = min_full <= kdo if kdo is not None else None
                tocou_alta_full = max_full >= kuo
                variacao_full = (ST_full / preco_foto - 1)
                # CORRIGIDO 15/07/2026 -- delega pra funcao unica
                # _retorno_bidirecional_full (ver docstring dela, topo do
                # arquivo). Substitui a logica que estava duplicada aqui
                # (2 correcoes de sinal ja feitas nesta sessao, mais uma
                # variante nova -- 'downside_antes'/'downside_apos' -- pra
                # suportar Protecao Total e Protecao Parcial). Campos
                # opcionais no payload da posicao/analise, com default que
                # preserva o comportamento das AXIA3(A)/(B) ja existentes:
                # downside_antes='positiva', downside_apos='protegida'.
                downside_antes = data.get('downside_antes', 'positiva')
                downside_apos = data.get('downside_apos', 'protegida')
                retorno_full = _retorno_bidirecional_full(
                    variacao_full, tocou_alta_full, tocou_baixa_full,
                    teto_retorno, alavancagem, downside_antes, downside_apos)
                faixas = {
                    'menor_que_0': round(float((retorno_full < 0).mean() * 100), 2),
                    'entre_0_e_1': round(float(((retorno_full >= 0) & (retorno_full < 0.01)).mean() * 100), 2),
                    'entre_1_e_2': round(float(((retorno_full >= 0.01) & (retorno_full < 0.02)).mean() * 100), 2),
                    'entre_2_e_meta': round(float(((retorno_full >= 0.02) & (retorno_full < teto_retorno)).mean() * 100), 2),
                    'maior_ou_igual_meta': round(float((retorno_full >= teto_retorno).mean() * 100), 2),
                }
                res['prob_retorno_faixas'] = faixas
                res['retorno_medio_pct'] = round(float(retorno_full.mean() * 100), 2)
                res['teto_retorno_usado_pct'] = round(teto_retorno * 100, 2)

                # ADICIONADO 10/07/2026 (fix de bug real encontrado pelo
                # usuario): o calculo ACIMA e "desde o inicio" (preco_foto,
                # prazo_dias total) -- usado pelo painel de aproveitamento em
                # Encerradas (precisa ficar assim, nao mexer). Mas o rotulo no
                # front dizia "daqui pra frente", o que era FALSO -- nao
                # descontava os dias ja passados nem usava o preco atual.
                # Aqui vai a versao CONDICIONAL DE VERDADE (dias_restantes,
                # preco atual S), como campo NOVO e SEPARADO, para o painel de
                # detalhe da foto passar a mostrar o numero certo sem quebrar
                # o que ja dependia do calculo antigo.
                if dias_restantes > 0:
                    z_cond = np.random.standard_normal((n_faixas, dias_restantes))
                    paths_cond = S * np.exp(np.cumsum(drift_fan + vol_step_fan * z_cond, axis=1))
                    max_cond = np.max(paths_cond, axis=1)
                    min_cond = np.min(paths_cond, axis=1)
                    tocou_baixa_cond = (min_cond <= kdo) if kdo is not None else np.zeros_like(min_cond, dtype=bool)
                    tocou_alta_cond = max_cond >= kuo
                    res['prob_sem_barreira_condicional'] = round(float((~tocou_baixa_cond & ~tocou_alta_cond).mean() * 100), 2)
                    res['prob_barreira_baixa_condicional'] = round(float(tocou_baixa_cond.mean() * 100), 2)
                    res['prob_barreira_alta_condicional'] = round(float(tocou_alta_cond.mean() * 100), 2)
                else:
                    res['prob_sem_barreira_condicional'] = None
            except Exception:
                res['prob_retorno_faixas'] = None

        # ── RETORNO CONTROLADO (barreira UNICA + ganho prefixado, ex:
        # TSLA34/ROXO34): se NAO tocar a barreira (kdo) em nenhum momento,
        # ganho fixo prefixado; se tocar, fica exposto a variacao REAL da
        # acao no vencimento (sem garantia, sem teto). So roda quando o
        # payload trouxer 'ganho_prefixado_pct' E NAO tiver 'alavancagem'/
        # 'teto_retorno_pct' (que seria o caso bidirecional, tratado acima).
        ganho_prefixado_pct = data.get('ganho_prefixado_pct')
        retorno_full2 = None
        tocou_barreira2 = None
        variacao_full2 = None
        ganho_prefixado = None
        if (ganho_prefixado_pct is not None and alavancagem is None
                and teto_retorno_pct is None and kdo is not None):
            try:
                ganho_prefixado = float(ganho_prefixado_pct) / 100
                n_faixas2 = 20000
                z_full2 = np.random.standard_normal((n_faixas2, prazo_dias))
                paths_full2 = preco_foto * np.exp(np.cumsum(drift_fan + vol_step_fan * z_full2, axis=1))
                min_full2 = np.min(paths_full2, axis=1)
                ST_full2 = paths_full2[:, -1]
                tocou_barreira2 = min_full2 <= kdo
                variacao_full2 = (ST_full2 / preco_foto - 1)
                # se nao tocou: ganho fixo prefixado; se tocou: fica com a
                # variacao real da acao (pode ser negativa, positiva, qualquer valor)
                retorno_full2 = np.where(~tocou_barreira2, ganho_prefixado, variacao_full2)
                faixas2 = {
                    'menor_que_0': round(float((retorno_full2 < 0).mean() * 100), 2),
                    'entre_0_e_1': round(float(((retorno_full2 >= 0) & (retorno_full2 < 0.01)).mean() * 100), 2),
                    'entre_1_e_2': round(float(((retorno_full2 >= 0.01) & (retorno_full2 < 0.02)).mean() * 100), 2),
                    'entre_2_e_meta': round(float(((retorno_full2 >= 0.02) & (retorno_full2 < ganho_prefixado)).mean() * 100), 2),
                    'maior_ou_igual_meta': round(float((retorno_full2 >= ganho_prefixado).mean() * 100), 2),
                }
                res['prob_retorno_faixas'] = faixas2
                res['retorno_medio_pct'] = round(float(retorno_full2.mean() * 100), 2)
                res['teto_retorno_usado_pct'] = round(ganho_prefixado * 100, 2)
                res['prob_ganho_prefixado'] = round(float((~tocou_barreira2).mean() * 100), 2)

                # ADICIONADO 10/07/2026 (mesmo fix do bloco bidirecional acima):
                # versao CONDICIONAL DE VERDADE (dias_restantes, preco atual S)
                # -- o campo 'prob_ganho_prefixado' acima e "desde o inicio"
                # (usado no painel de aproveitamento em Encerradas, NAO mexer).
                # Este novo campo e o que devia aparecer com o rotulo "daqui
                # pra frente" no painel de detalhe da foto.
                if dias_restantes > 0:
                    z_cond2 = np.random.standard_normal((n_faixas2, dias_restantes))
                    paths_cond2 = S * np.exp(np.cumsum(drift_fan + vol_step_fan * z_cond2, axis=1))
                    min_cond2 = np.min(paths_cond2, axis=1)
                    tocou_cond2 = min_cond2 <= kdo
                    res['prob_ganho_prefixado_condicional'] = round(float((~tocou_cond2).mean() * 100), 2)
                else:
                    res['prob_ganho_prefixado_condicional'] = None
            except Exception:
                res['prob_retorno_faixas'] = None

        # ── VENDA DE CALL SIMPLES COBERTA (k_call, sem kdo/kuo): mecanica
        # binaria, sem teto/defesa fixos. Se NAO exercida, retorno = a
        # variacao REAL da acao (livre); se EXERCIDA, retorno trava em
        # (k_call/preco_foto - 1). Respeita 'exercicio' (americana usa
        # max da trajetoria completa; europeia so preco final). So roda
        # quando o payload trouxer 'meta_pct' (a meta do usuario em %).
        meta_pct = data.get('meta_pct')
        if K_call is not None and kdo is None and meta_pct is not None:
            try:
                meta_call = float(meta_pct) / 100
                n_faixas3 = 20000
                z_full3 = np.random.standard_normal((n_faixas3, prazo_dias))
                paths_full3 = preco_foto * np.exp(np.cumsum(drift_fan + vol_step_fan * z_full3, axis=1))
                ST_full3 = paths_full3[:, -1]
                if exercicio == 'americana':
                    call_ex_full3 = np.max(paths_full3, axis=1) > K_call
                else:
                    call_ex_full3 = ST_full3 > K_call
                variacao_full3 = (ST_full3 / preco_foto - 1)
                retorno_full3 = np.where(call_ex_full3, (K_call / preco_foto - 1), variacao_full3)
                faixas3 = {
                    'menor_que_0': round(float((retorno_full3 < 0).mean() * 100), 2),
                    'entre_0_e_1': round(float(((retorno_full3 >= 0) & (retorno_full3 < 0.01)).mean() * 100), 2),
                    'entre_1_e_2': round(float(((retorno_full3 >= 0.01) & (retorno_full3 < 0.02)).mean() * 100), 2),
                    'entre_2_e_meta': round(float(((retorno_full3 >= 0.02) & (retorno_full3 < meta_call)).mean() * 100), 2),
                    'maior_ou_igual_meta': round(float((retorno_full3 >= meta_call).mean() * 100), 2),
                }
                res['prob_retorno_faixas'] = faixas3
                res['retorno_medio_pct'] = round(float(retorno_full3.mean() * 100), 2)
                res['teto_retorno_usado_pct'] = round(meta_call * 100, 2)
                capital_100_call3 = preco_foto * 100
                ret_nao_ex3 = retorno_full3[~call_ex_full3]
                res['simulacao_100_acoes'] = {
                    'acoes': 100, 'preco_foto': round(preco_foto, 2), 'capital': round(capital_100_call3, 2),
                    'nao_exercida': {
                        'probabilidade_pct': round(float((~call_ex_full3).mean() * 100), 2),
                        'retorno_medio_pct': round(float(ret_nao_ex3.mean() * 100), 2) if len(ret_nao_ex3) else 0.0,
                        'retorno_medio_reais': round(float(ret_nao_ex3.mean() * capital_100_call3), 2) if len(ret_nao_ex3) else 0.0,
                        'descricao': 'Não exercida: mantém ações, variação livre',
                    },
                    'exercida': {
                        'probabilidade_pct': round(float(call_ex_full3.mean() * 100), 2),
                        'retorno_pct': round((K_call / preco_foto - 1) * 100, 2),
                        'retorno_reais': round((K_call / preco_foto - 1) * capital_100_call3, 2),
                        'descricao': 'Exercida: entrega ações no strike R$' + str(round(K_call, 2)),
                    },
                }
            except Exception:
                res['prob_retorno_faixas'] = None

        # ── VENDA DE PUT (k_put, sem k_call/kdo): mecanica diferente da
        # call coberta -- quando EXERCIDA, vira uma posicao NOVA (compra
        # forcada de acoes), nao um retorno fechado. Por decisao do usuario
        # (sessao 22/06/2026): NAO simular o pos-exercicio. O "retorno se
        # nao exercida" e um FATO FIXO (premio/capital), calculado uma
        # unica vez a partir do payload, NAO via Monte Carlo -- so a
        # PROBABILIDADE de nao ser exercida usa Monte Carlo (ja calculada
        # acima em prob_sucesso/prob_put_exercida). Requer 'premio' (R$
        # total recebido) e 'qtd_acoes' (tamanho do compromisso) no
        # payload para calcular o capital comprometido.
        premio_valor = data.get('premio')
        qtd_acoes_put = data.get('qtd_acoes')
        if K_put is not None and K_call is None and kdo is None and premio_valor is not None and qtd_acoes_put is not None:
            try:
                premio_valor = float(premio_valor)
                qtd_acoes_put = float(qtd_acoes_put)
                capital_comprometido = K_put * qtd_acoes_put
                retorno_fixo_pct = round((premio_valor / capital_comprometido) * 100, 2)
                meses_prazo = prazo_dias / 30.0
                retorno_fixo_mes_pct = round(retorno_fixo_pct / meses_prazo, 2) if meses_prazo > 0 else None
                # Padroniza exibicao em 100 acoes (mesmo padrao das outras
                # estruturas) -- premio e capital escalados proporcionalmente
                # a partir do valor REAL (premio_valor/qtd_acoes_put), o
                # percentual/meta continuam exatamente iguais aos reais.
                premio_por_acao = premio_valor / qtd_acoes_put
                premio_100 = round(premio_por_acao * 100, 2)
                capital_100_put = round(K_put * 100, 2)
                res['put_resultado_fixo'] = {
                    'premio_reais': premio_100,
                    'capital_comprometido': capital_100_put,
                    'acoes': 100,
                    'retorno_pct': retorno_fixo_pct,
                    'retorno_mes_pct': retorno_fixo_mes_pct,
                    'bate_meta': (retorno_fixo_mes_pct >= 2.0) if retorno_fixo_mes_pct is not None else None,
                    'descricao_nao_exercida': 'Não exercida: fica só com o prêmio de R$' + str(premio_100),
                    'descricao_exercida': 'Exercida: compra 100 ações a R$' + str(round(K_put, 2)) + ' (capital R$' + str(capital_100_put) + ')',
                }
            except Exception:
                res['put_resultado_fixo'] = None
        # estrutura) — traduz os percentuais abstratos em R$ concretos sobre
        # um lote de 100 ações no preco_foto, nos 3 cenários possíveis:
        # defesa/barreira tocada, dentro do range (média/mediana), e teto/
        # ganho prefixado. Reaproveita o array de retorno já simulado acima
        # (retorno_full para bidirecional, retorno_full2 para retorno
        # controlado) quando disponível; senão, não calcula (sem dado
        # suficiente, ex. estrutura simples sem kdo/kuo/ganho_prefixado).
        try:
            capital_100 = preco_foto * 100
            sim_100 = res.get('simulacao_100_acoes')  # preserva o que o bloco de call simples já setou
            if sim_100 is None and retorno_full is not None and kdo is not None and kuo is not None:
                # caso bidirecional
                r_full = retorno_full
                cenario_defesa = {
                    'probabilidade_pct': round(float(tocou_baixa_full.mean() * 100), 2),
                    'retorno_pct': 0.0,
                    'retorno_reais': 0.0,
                    'descricao': 'Protegido: nem ganha nem perde (defesa em ' + str(round(kdo,2)) + ')',
                }
                dentro_mask = (~tocou_baixa_full) & (~tocou_alta_full)
                ret_dentro = r_full[dentro_mask]
                cenario_dentro = {
                    'probabilidade_pct': round(float(dentro_mask.mean() * 100), 2),
                    'retorno_medio_pct': round(float(ret_dentro.mean() * 100), 2) if len(ret_dentro) else 0.0,
                    'retorno_medio_reais': round(float(ret_dentro.mean() * capital_100), 2) if len(ret_dentro) else 0.0,
                    'descricao': 'Fica dentro do range (ganha a variação × alavancagem)',
                }
                cenario_teto = {
                    'probabilidade_pct': round(float(tocou_alta_full.mean() * 100), 2),
                    'retorno_pct': round(teto_retorno * 100, 2),
                    'retorno_reais': round(teto_retorno * capital_100, 2),
                    'descricao': 'Trava no teto (barreira em ' + str(round(kuo,2)) + ')',
                }
                sim_100 = {
                    'acoes': 100, 'preco_foto': round(preco_foto, 2),
                    'capital': round(capital_100, 2),
                    'defesa': cenario_defesa, 'dentro': cenario_dentro, 'teto': cenario_teto,
                }
            elif sim_100 is None and retorno_full2 is not None and kdo is not None:
                # caso retorno controlado (barreira única + ganho prefixado)
                cenario_prefixado = {
                    'probabilidade_pct': round(float((~tocou_barreira2).mean() * 100), 2),
                    'retorno_pct': round(ganho_prefixado * 100, 2),
                    'retorno_reais': round(ganho_prefixado * capital_100, 2),
                    'descricao': 'Ganha o prefixado (não tocou a barreira)',
                }
                exposto_mask = tocou_barreira2
                ret_exposto = variacao_full2[exposto_mask]
                cenario_exposto = {
                    'probabilidade_pct': round(float(exposto_mask.mean() * 100), 2),
                    'retorno_medio_pct': round(float(ret_exposto.mean() * 100), 2) if len(ret_exposto) else 0.0,
                    'retorno_medio_reais': round(float(ret_exposto.mean() * capital_100), 2) if len(ret_exposto) else 0.0,
                    'descricao': 'Tocou a barreira: fica exposto à variação real (sem garantia)',
                }
                sim_100 = {
                    'acoes': 100, 'preco_foto': round(preco_foto, 2),
                    'capital': round(capital_100, 2),
                    'prefixado': cenario_prefixado, 'exposto': cenario_exposto,
                }
            res['simulacao_100_acoes'] = sim_100
        except Exception:
            res['simulacao_100_acoes'] = None

        return jsonify(res)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/montecarlo/posicao_ativa', methods=['POST'])
def run_montecarlo_posicao_ativa():
    """
    Para POSICOES REAIS ja ativas (positions.json), nao fotos de Em Analise.
    Monta o fan chart completo: RETROATIVO REAL (preco historico real desde
    data_entrada até hoje, via Yahoo) + PROJECAO (banda de percentis de hoje
    até o vencimento real). Preco de entrada (preco_foto equivalente) e
    extraido do proprio historico no dia de data_entrada (ou o pregao mais
    proximo disponivel), nao informado pelo payload -- diferente do
    /montecarlo/condicional, que recebe preco_foto fixo de uma foto ja
    registrada.

    Payload esperado:
    - ticker (obrigatorio)
    - data_entrada (obrigatorio, YYYY-MM-DD)
    - vencimento (obrigatorio, YYYY-MM-DD)
    - k_call/k_put (estrutura simples) OU kdo/kuo (bidirecional)
    - alavancagem/teto_retorno_pct (opcionais, para faixas de retorno em
      bidirecional) OU ganho_prefixado_pct (para retorno controlado)

    Retorna: preco_entrada (extraido do historico), preco_atual,
    dias_passados, dias_restantes, fan_chart (com precos_reais cobrindo
    TODO o periodo desde a entrada, nao so uma janela curta), e as mesmas
    probabilidades/faixas/simulacao_100_acoes do /montecarlo/condicional
    quando aplicavel.
    """
    try:
        import numpy as np
        from datetime import datetime as _dt
        data = request.get_json() or {}
        ticker = data.get('ticker', 'BBAS3.SA')
        data_entrada_str = data.get('data_entrada')
        vencimento_str = data.get('vencimento')
        K_call = float(data['k_call']) if data.get('k_call') else None
        K_put = float(data['k_put']) if data.get('k_put') else None
        kdo = float(data['kdo']) if data.get('kdo') else None
        kuo = float(data['kuo']) if data.get('kuo') else None

        if not data_entrada_str or not vencimento_str:
            return jsonify({'error': 'data_entrada e vencimento sao obrigatorios (YYYY-MM-DD)'}), 400
        try:
            data_entrada = _dt.strptime(data_entrada_str[:10], '%Y-%m-%d').date()
            vencimento = _dt.strptime(vencimento_str[:10], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'data_entrada/vencimento invalidas, use YYYY-MM-DD'}), 400

        hoje = _dt.now().date()
        prazo_dias = (vencimento - data_entrada).days
        dias_passados = (hoje - data_entrada).days
        dias_restantes = max((vencimento - hoje).days, 0)
        fora_do_prazo = hoje >= vencimento

        # Busca historico (mesmo padrao de fallback do /montecarlo/condicional)
        S = None
        cl = []
        ts = []
        sigma = 0.35
        for host in ['query1', 'query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y',
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                if r.ok:
                    d = r.json()
                    meta = d['chart']['result'][0]['meta']
                    raw_cl = d['chart']['result'][0]['indicators']['quote'][0]['close']
                    raw_ts = d['chart']['result'][0].get('timestamp', [])
                    cl = [c for c in raw_cl if c is not None]
                    ts = [t for t, c in zip(raw_ts, raw_cl) if c is not None]
                    S = float(meta.get('regularMarketPrice', cl[-1] if cl else 0))
                    if cl: sigma = vol_hist(cl)
                    break
            except Exception:
                continue

        if S is None or not cl:
            return jsonify({'error': f'nao foi possivel obter historico de {ticker}'}), 502

        # ADICIONADO 06/07/2026 -- fallback via brapi.dev quando o Yahoo
        # devolve historico ESPARSO DEMAIS para cobrir o periodo desde
        # data_entrada (ex: BSLV39 -- BDR de ETF estrangeiro com liquidez
        # real boa na B3, mas cobertura de dados ruim no Yahoo Finance
        # especificamente. Nao e sobre iliquidez do ativo, e sobre o Yahoo
        # nao ter os pregoes). Sem isso, precos_reais_fan ficava com so 1-2
        # pontos, aparecendo como linha reta/plana no grafico mesmo apos
        # 13 dias de posicao aberta. Mesmo padrao de fallback ja usado em
        # /montecarlo/condicional e /indicadores (brapi com range=1y).
        pontos_minimos_esperados = max(2, min(dias_passados, 5))
        if len(cl) < pontos_minimos_esperados:
            try:
                symbol_bp = ticker.replace('.SA', '').upper()
                rb = requests.get(
                    f'https://brapi.dev/api/quote/{symbol_bp}?range=1y&interval=1d&fundamental=false',
                    headers=BRAPI_HEADERS, timeout=12)
                if rb.ok:
                    rd = rb.json().get('results', [{}])[0]
                    hist_bp = rd.get('historicalDataPrice', [])
                    cl_bp = [x['close'] for x in hist_bp if x.get('close')]
                    ts_bp = [x['date'] for x in hist_bp if x.get('close') and x.get('date')]
                    if len(cl_bp) > len(cl):
                        cl = cl_bp
                        ts = ts_bp
                        sigma = vol_hist(cl) if cl else sigma
                        preco_atual_bp = rd.get('regularMarketPrice')
                        if preco_atual_bp:
                            S = float(preco_atual_bp)
            except Exception:
                pass  # falha no fallback nao impede seguir com o que o Yahoo deu

        # Extrai preco_entrada do historico real no dia de data_entrada
        # (ou o pregao mais proximo disponivel apos essa data)
        import math
        from datetime import timezone as _tz
        preco_entrada = None
        idx_entrada = None
        entrada_epoch = _dt.combine(data_entrada, _dt.min.time(), tzinfo=_tz.utc).timestamp()
        for i, t in enumerate(ts):
            if t >= entrada_epoch:
                idx_entrada = i
                preco_entrada = cl[i]
                break
        if preco_entrada is None:
            # data_entrada fora do historico disponivel (>1 ano atras) -- usa o primeiro ponto
            idx_entrada = 0
            preco_entrada = cl[0] if cl else S

        # ADICIONADO 30/06/2026 -- ativos de baixissima liquidez (ex: BSLV39)
        # tem historico do Yahoo tao esparso que a extracao acima pode
        # devolver um preco_entrada ERRADO (ex: usa o proprio preco ATUAL
        # como "entrada" porque nao existe nenhum ponto historico real no
        # meio). Quando o payload traz um 'entry' explicito (preco REAL
        # confirmado pelo usuario via boleto/nota de corretagem -- fonte
        # mais confiavel que extracao do Yahoo para esses casos), ele tem
        # PRIORIDADE sobre o valor extraido do historico. Mantem o indice
        # idx_entrada (usado so para fatiar a janela de precos_reais), mas
        # o preco usado como base da simulacao e do calculo de retorno e o
        # informado, nao o do Yahoo.
        entry_explicito = data.get('entry')
        if entry_explicito is not None:
            try:
                preco_entrada = float(entry_explicito)
            except (TypeError, ValueError):
                pass

        # ADICIONADO 06/07/2026 -- fallback NIVEL 3, so para BDRs de ETFs
        # estrangeiros mapeados em _BDR_PROXY_ORIGINAL (pedido explicito do
        # usuario): quando NEM Yahoo NEM brapi tem historico diario granular
        # (caso comprovado do BSLV39 -- confirmado que o proprio brapi.dev
        # mostra R$0,00 pra esse ticker na pagina publica dele), reconstroi
        # a trajetoria estimada usando o ATIVO ORIGINAL (ex: SLV na NYSE,
        # que tem historico perfeito) + cambio USD/BRL (Yahoo tem historico
        # perfeito de USDBRL=X tambem):
        #   preco_estimado(dia) = preco_entrada * (SLV[dia]/SLV[entrada]) *
        #                         (USDBRL[dia]/USDBRL[entrada])
        # Isso e uma ESTIMATIVA (nao e o preco real negociado do BDR na B3,
        # que pode ter pequeno premio/desconto vs o NAV teorico) -- marcado
        # explicitamente na resposta como 'precos_reais_estimados': true,
        # para o usuario saber que se o preco ficar muito longe do que ele
        # observa no home broker, o dado e aproximado, nao exato.
        _BDR_PROXY_ORIGINAL = {
            'BSLV39.SA': 'SLV',  # iShares Silver Trust BDR -> SLV (NYSE)
        }
        precos_reais_estimados = False
        # CORRIGIDO 15/07/2026 (2a correcao, mesmo dia -- achado pelo
        # Victor): a condicao antiga (`len(cl) < pontos_minimos_esperados`)
        # fazia o proxy SO entrar em acao quando o HISTORICO vinha esparso
        # demais. Só que o Yahoo pode devolver um `regularMarketPrice`
        # (usado em S/preco_atual) ERRADO ou desatualizado MESMO quando o
        # historico (`cl`) tem pontos suficientes para passar dessa
        # checagem -- foi exatamente o caso: o card no topo (via
        # MCBSimples) mostrou R$98,55 e depois R$98,42 (raw do Yahoo,
        # errado), enquanto "Ver evolucao desde a entrada" (mesmo
        # endpoint, mas caindo no branch do proxy) mostrou ~R$89 (certo).
        # Os dois deveriam SEMPRE bater, ja que e a mesma rota. Fix: pra
        # tickers em _BDR_PROXY_ORIGINAL, SEMPRE calcula o preco via proxy
        # (SLV+cambio) e usa ele pro preco ATUAL (S) incondicionalmente --
        # o historico (`cl`) continua so sendo SUBSTITUIDO quando esparso
        # (nao precisa trocar o grafico se o Yahoo já tiver pontos
        # suficientes ali), mas o preco atual em si nunca mais confia no
        # raw do Yahoo pra esses tickers conhecidos como problematicos.
        if ticker in _BDR_PROXY_ORIGINAL:
            try:
                original = _BDR_PROXY_ORIGINAL[ticker]
                def _fetch_serie_yahoo(simbolo):
                    for host in ['query1', 'query2']:
                        try:
                            rr = requests.get(
                                f'https://{host}.finance.yahoo.com/v8/finance/chart/{simbolo}?interval=1d&range=1y',
                                headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                            if rr.ok:
                                dd = rr.json()['chart']['result'][0]
                                raw_c = dd['indicators']['quote'][0]['close']
                                raw_t = dd.get('timestamp', [])
                                pares = [(t, c) for t, c in zip(raw_t, raw_c) if c is not None]
                                return pares
                        except Exception:
                            continue
                    return []

                serie_original = _fetch_serie_yahoo(original)
                serie_cambio = _fetch_serie_yahoo('USDBRL=X')

                if serie_original and serie_cambio:
                    # Converte para dict data(YYYY-MM-DD) -> preco, para alinhar
                    # os dois calendarios (NYSE vs mercado de cambio) por data
                    def _para_dict_data(pares):
                        out = {}
                        for t, c in pares:
                            dia = _dt.utcfromtimestamp(t).date()
                            out[dia] = c
                        return out
                    dict_original = _para_dict_data(serie_original)
                    dict_cambio = _para_dict_data(serie_cambio)
                    datas_original = sorted(dict_original.keys())
                    datas_cambio = sorted(dict_cambio.keys())

                    def _valor_mais_recente(dict_serie, datas_ordenadas, alvo):
                        # forward-fill: pega o ultimo valor disponivel em ou antes de 'alvo'
                        melhor = None
                        for dd2 in datas_ordenadas:
                            if dd2 <= alvo:
                                melhor = dict_serie[dd2]
                            else:
                                break
                        return melhor

                    original_entrada = _valor_mais_recente(dict_original, datas_original, data_entrada)
                    cambio_entrada = _valor_mais_recente(dict_cambio, datas_cambio, data_entrada)

                    if original_entrada and cambio_entrada:
                        datas_alvo = [dd2 for dd2 in datas_cambio if dd2 >= data_entrada]
                        cl_estimado = []
                        ts_estimado = []
                        for dd2 in datas_alvo:
                            orig_v = _valor_mais_recente(dict_original, datas_original, dd2)
                            camb_v = _valor_mais_recente(dict_cambio, datas_cambio, dd2)
                            if orig_v and camb_v:
                                preco_est = preco_entrada * (orig_v/original_entrada) * (camb_v/cambio_entrada)
                                cl_estimado.append(round(preco_est, 2))
                                ts_estimado.append(int(_dt.combine(dd2, _dt.min.time()).timestamp()))
                        # CORRIGIDO 15/07/2026 (3a tentativa, mesmo dia --
                        # as 2 anteriores pioraram em vez de resolver).
                        # Confirmado pelo Victor com print do home broker:
                        # preco real da BSLV39 = R$89,99. O calculo via
                        # proxy (SLV+cambio) anconrado no 'entry' explicito
                        # (R$99,42) deu R$98,41 -- ERRADO. Causa provavel:
                        # 'entry' e o PRECO DE EXERCICIO da estrutura
                        # (strike), nao necessariamente o preco real
                        # negociado do BDR no dia da entrada -- ancorar a
                        # razao SLV/cambio num preco de exercicio (nao no
                        # preco de mercado real daquele dia) quebra a
                        # matematica da reconstrucao, mesmo que a razao em
                        # si esteja certa. NAO sobrescreve mais 'S' com o
                        # proxy -- volta a usar o preco bruto do Yahoo (ou
                        # brapi, ja tratado acima) pro preco ATUAL. O
                        # proxy continua servindo SO pra reconstruir o
                        # HISTORICO do grafico quando esparso (abaixo),
                        # que e um uso diferente (tendencia relativa, nao
                        # preco pontual).
                        if len(cl_estimado) >= pontos_minimos_esperados and len(cl) < pontos_minimos_esperados:
                            cl = cl_estimado
                            ts = ts_estimado
                            precos_reais_estimados = True
                            # sigma: usa a vol do ATIVO ORIGINAL como proxy
                            # (mais real que a vol de 1-2 pontos esparsos do BDR)
                            vals_original_recentes = [v for _, v in serie_original[-252:]]
                            if vals_original_recentes:
                                sigma = vol_hist(vals_original_recentes)
            except Exception:
                pass  # se o proxy tambem falhar, segue com o que ja tinha (Yahoo/brapi esparso)


        res = {
            'ticker': ticker, 'preco_entrada': round(preco_entrada, 2),
            'preco_atual': round(S, 2), 'dias_passados': dias_passados,
            'dias_restantes': dias_restantes, 'prazo_dias': prazo_dias,
            'fora_do_prazo': fora_do_prazo, 'volatilidade_historica_pct': round(sigma*100, 2),
        }

        if fora_do_prazo:
            res['mensagem'] = 'Vencimento ja passou.'
            return jsonify(res)

        # Probabilidades de barreira (mesma logica do /montecarlo/condicional,
        # mas com tempo RESTANTE a partir do preco ATUAL, nao do preco_entrada)
        # CORRIGIDO 15/07/2026 -- suporte a kdo=None (Protecao Total).
        if kuo is not None and dias_restantes > 0:
            n = 5000
            dt2 = 1/252.0
            drift2 = -0.5*sigma**2*dt2
            vol_step2 = sigma*math.sqrt(dt2)
            z2 = np.random.standard_normal((n, dias_restantes))
            paths = S*np.exp(np.cumsum(drift2+vol_step2*z2, axis=1))
            max_p = np.max(paths, axis=1); min_p = np.min(paths, axis=1)
            kuo_hit = max_p >= kuo
            kdo_hit = (min_p <= kdo) if kdo is not None else np.zeros_like(min_p, dtype=bool)
            no_barrier = ~kuo_hit & ~kdo_hit
            res['prob_sem_barreira'] = round(float(no_barrier.mean()*100), 2)
            res['prob_barreira_alta'] = round(float(kuo_hit.mean()*100), 2)
            res['prob_barreira_baixa'] = round(float(kdo_hit.mean()*100), 2)
            res['kdo'] = kdo; res['kuo'] = kuo

        # Probabilidade de exercicio para venda de CALL simples (k_call,
        # sem kdo/kuo) — usa o tempo RESTANTE e respeita 'exercicio'
        # (americana = max da trajetoria; europeia = so preco final).
        # Campo obrigatorio quando K_call esta presente, mesma regra do
        # /montecarlo principal (sem padrao implicito).
        exercicio = data.get('exercicio')
        if K_call is not None and kdo is None and dias_restantes > 0:
            if exercicio not in ('americana', 'europeia'):
                return jsonify({'error': "campo 'exercicio' obrigatorio quando k_call presente: 'americana' ou 'europeia'"}), 400
            n3 = 5000
            dt3 = 1/252.0
            drift3 = -0.5*sigma**2*dt3
            vol_step3 = sigma*math.sqrt(dt3)
            z3 = np.random.standard_normal((n3, dias_restantes))
            paths3 = S*np.exp(np.cumsum(drift3+vol_step3*z3, axis=1))
            if exercicio == 'americana':
                call_ex3 = np.max(paths3, axis=1) > K_call
            else:
                call_ex3 = paths3[:, -1] > K_call
            res['prob_call_exercida'] = round(float(call_ex3.mean()*100), 2)
            res['prob_sem_exercicio'] = round(float((~call_ex3).mean()*100), 2)
            res['k_call'] = K_call
            res['exercicio'] = exercicio

        # FAN CHART: percentis projetados do dia 0 (preco_entrada) ao
        # prazo_dias TOTAL + serie de precos REAIS desde data_entrada até hoje
        try:
            n_fan = 2000
            dt_fan = 1/252.0
            drift_fan = -0.5*sigma**2*dt_fan
            vol_step_fan = sigma*math.sqrt(dt_fan)
            z_fan = np.random.standard_normal((n_fan, prazo_dias))
            paths_fan = preco_entrada*np.exp(np.cumsum(drift_fan+vol_step_fan*z_fan, axis=1))
            paths_fan = np.hstack([np.full((n_fan,1), preco_entrada), paths_fan])
            percentis_fan = {}
            for p in [10,25,50,75,90]:
                percentis_fan[f'p{p}'] = np.percentile(paths_fan, p, axis=0).round(2).tolist()
            idx_amostra = np.random.choice(n_fan, size=min(20, n_fan), replace=False)
            trajetorias_fan = paths_fan[idx_amostra].round(2).tolist()
            # CORRIGIDO (23/06/2026): antes usava dias_passados+1 (dias CORRIDOS)
            # para fatiar cl[], que so tem 1 ponto por PREGAO UTIL -- isso
            # desalinhava sempre que o periodo desde data_entrada cruzava fim
            # de semana/feriado (slice pegava pontos demais). Agora pega TODO o
            # resto do historico a partir da entrada: o Yahoo nunca retorna
            # pregao futuro, entao isso sempre da exatamente os pregoes reais
            # decorridos, sem contar dias sem pregao. Mesma correcao aplicada
            # em /montecarlo/condicional (ver linha ~1040).
            precos_reais_fan = [round(float(p), 2) for p in cl[idx_entrada:]]
            # ADICIONADO 30/06/2026 -- mesma correcao do /montecarlo/condicional:
            # garante pelo menos 2 pontos (entrada + hoje) quando o array de
            # fechamentos diarios do Yahoo nao capturou pregao novo desde a
            # entrada (comum em BDRs ilíquidas como BSLV39), mas 'S' (preco
            # atual) ja reflete negociacao real mais recente.
            if precos_reais_fan and round(float(S), 2) != precos_reais_fan[-1]:
                precos_reais_fan.append(round(float(S), 2))
            # ADICIONADO 30/06/2026 -- quando 'entry' explicito foi usado (ver
            # acima), o dia 0 do fan chart (banda de percentis) comeca em
            # preco_entrada, mas a linha real (precos_reais_fan) ainda
            # comecava do que o Yahoo tinha (que pode ser bem diferente,
            # criando um salto visual estranho no grafico). Ancora a linha
            # real no preco de entrada REAL como primeiro ponto, para bater
            # com o dia 0 da banda de projecao.
            if entry_explicito is not None:
                preco_entrada_arredondado = round(preco_entrada, 2)
                if not precos_reais_fan or precos_reais_fan[0] != preco_entrada_arredondado:
                    precos_reais_fan = [preco_entrada_arredondado] + precos_reais_fan
            res['fan_chart'] = {
                'dias': list(range(prazo_dias+1)), 'percentis': percentis_fan,
                'trajetorias': trajetorias_fan, 'precos_reais': precos_reais_fan,
                'preco_foto': round(preco_entrada, 2),
                'precos_reais_estimados': precos_reais_estimados,
            }
        except Exception:
            res['fan_chart'] = None

        # Faixas de retorno + simulacao 100 acoes (reaproveita a mesma logica
        # do /montecarlo/condicional, usando preco_entrada como base e o
        # PRAZO TOTAL, ja que representa o resultado da posicao do inicio ao fim)
        alavancagem = data.get('alavancagem')
        teto_retorno_pct = data.get('teto_retorno_pct')
        ganho_prefixado_pct = data.get('ganho_prefixado_pct')
        meta_pct = data.get('meta_pct')
        retorno_full = None; tocou_baixa_full = None; tocou_alta_full = None; teto_retorno = None
        retorno_full2 = None; tocou_barreira2 = None; variacao_full2 = None; ganho_prefixado = None

        if alavancagem is not None and teto_retorno_pct is not None and kuo is not None:
            try:
                alavancagem = float(alavancagem)
                teto_retorno = float(teto_retorno_pct)/100
                n_faixas = 20000
                z_full = np.random.standard_normal((n_faixas, prazo_dias))
                paths_full = preco_entrada*np.exp(np.cumsum(drift_fan+vol_step_fan*z_full, axis=1))
                max_full = np.max(paths_full, axis=1); min_full = np.min(paths_full, axis=1)
                ST_full = paths_full[:,-1]
                # CORRIGIDO 15/07/2026 -- suporte a kdo=None (Protecao
                # Total), mesmo motivo do bloco identico em
                # /montecarlo/condicional.
                tocou_baixa_full = (min_full <= kdo) if kdo is not None else None
                tocou_alta_full = max_full >= kuo
                variacao_full = (ST_full/preco_entrada - 1)
                # CORRIGIDO 15/07/2026 -- delega pra funcao unica
                # _retorno_bidirecional_full (ver docstring dela, topo do
                # arquivo). Mesmo motivo do bloco identico em
                # /montecarlo/condicional: elimina duplicacao que ja
                # causou 1 bug real nesta sessao (2 de 3 copias corrigidas,
                # a 3a esquecida). Suporta 'downside_antes'/'downside_apos'
                # opcionais no payload (default preserva comportamento das
                # AXIA3(A)/(B) existentes).
                downside_antes = data.get('downside_antes', 'positiva')
                downside_apos = data.get('downside_apos', 'protegida')
                retorno_full = _retorno_bidirecional_full(
                    variacao_full, tocou_alta_full, tocou_baixa_full,
                    teto_retorno, alavancagem, downside_antes, downside_apos)
                faixas = {
                    'menor_que_0': round(float((retorno_full<0).mean()*100), 2),
                    'entre_0_e_1': round(float(((retorno_full>=0)&(retorno_full<0.01)).mean()*100), 2),
                    'entre_1_e_2': round(float(((retorno_full>=0.01)&(retorno_full<0.02)).mean()*100), 2),
                    'entre_2_e_meta': round(float(((retorno_full>=0.02)&(retorno_full<teto_retorno)).mean()*100), 2),
                    'maior_ou_igual_meta': round(float((retorno_full>=teto_retorno).mean()*100), 2),
                }
                res['prob_retorno_faixas'] = faixas
                res['retorno_medio_pct'] = round(float(retorno_full.mean()*100), 2)
                res['teto_retorno_usado_pct'] = round(teto_retorno*100, 2)
            except Exception:
                res['prob_retorno_faixas'] = None
        elif ganho_prefixado_pct is not None and kdo is not None:
            try:
                ganho_prefixado = float(ganho_prefixado_pct)/100
                n_faixas2 = 20000
                z_full2 = np.random.standard_normal((n_faixas2, prazo_dias))
                paths_full2 = preco_entrada*np.exp(np.cumsum(drift_fan+vol_step_fan*z_full2, axis=1))
                min_full2 = np.min(paths_full2, axis=1)
                ST_full2 = paths_full2[:,-1]
                tocou_barreira2 = min_full2 <= kdo
                variacao_full2 = (ST_full2/preco_entrada - 1)
                retorno_full2 = np.where(~tocou_barreira2, ganho_prefixado, variacao_full2)
                faixas2 = {
                    'menor_que_0': round(float((retorno_full2<0).mean()*100), 2),
                    'entre_0_e_1': round(float(((retorno_full2>=0)&(retorno_full2<0.01)).mean()*100), 2),
                    'entre_1_e_2': round(float(((retorno_full2>=0.01)&(retorno_full2<0.02)).mean()*100), 2),
                    'entre_2_e_meta': round(float(((retorno_full2>=0.02)&(retorno_full2<ganho_prefixado)).mean()*100), 2),
                    'maior_ou_igual_meta': round(float((retorno_full2>=ganho_prefixado).mean()*100), 2),
                }
                res['prob_retorno_faixas'] = faixas2
                res['retorno_medio_pct'] = round(float(retorno_full2.mean()*100), 2)
                res['teto_retorno_usado_pct'] = round(ganho_prefixado*100, 2)
                res['prob_ganho_prefixado'] = round(float((~tocou_barreira2).mean()*100), 2)
            except Exception:
                res['prob_retorno_faixas'] = None
        elif K_call is not None and kdo is None and meta_pct is not None:
            try:
                meta_full = float(meta_pct)/100
                n_faixas3 = 20000
                z_full3 = np.random.standard_normal((n_faixas3, prazo_dias))
                paths_full3 = preco_entrada*np.exp(np.cumsum(drift_fan+vol_step_fan*z_full3, axis=1))
                ST_full3 = paths_full3[:,-1]
                if exercicio == 'americana':
                    call_ex_full3 = np.max(paths_full3, axis=1) > K_call
                else:
                    call_ex_full3 = ST_full3 > K_call
                variacao_full3 = (ST_full3/preco_entrada - 1)
                retorno_full3 = np.where(call_ex_full3, (K_call/preco_entrada - 1), variacao_full3)
                faixas3 = {
                    'menor_que_0': round(float((retorno_full3<0).mean()*100), 2),
                    'entre_0_e_1': round(float(((retorno_full3>=0)&(retorno_full3<0.01)).mean()*100), 2),
                    'entre_1_e_2': round(float(((retorno_full3>=0.01)&(retorno_full3<0.02)).mean()*100), 2),
                    'entre_2_e_meta': round(float(((retorno_full3>=0.02)&(retorno_full3<meta_full)).mean()*100), 2),
                    'maior_ou_igual_meta': round(float((retorno_full3>=meta_full).mean()*100), 2),
                }
                res['prob_retorno_faixas'] = faixas3
                res['retorno_medio_pct'] = round(float(retorno_full3.mean()*100), 2)
                res['teto_retorno_usado_pct'] = round(meta_full*100, 2)
                capital_100_call = preco_entrada*100
                ret_nao_ex_full3 = retorno_full3[~call_ex_full3]
                res['simulacao_100_acoes'] = {
                    'acoes': 100, 'preco_foto': round(preco_entrada, 2), 'capital': round(capital_100_call, 2),
                    'nao_exercida': {
                        'probabilidade_pct': round(float((~call_ex_full3).mean()*100), 2),
                        'retorno_medio_pct': round(float(ret_nao_ex_full3.mean()*100), 2) if len(ret_nao_ex_full3) else 0.0,
                        'retorno_medio_reais': round(float(ret_nao_ex_full3.mean()*capital_100_call), 2) if len(ret_nao_ex_full3) else 0.0,
                        'descricao': 'Não exercida: mantém ações, variação livre',
                    },
                    'exercida': {
                        'probabilidade_pct': round(float(call_ex_full3.mean()*100), 2),
                        'retorno_pct': round((K_call/preco_entrada - 1)*100, 2),
                        'retorno_reais': round((K_call/preco_entrada - 1)*capital_100_call, 2),
                        'descricao': 'Exercida: entrega ações no strike R$'+str(round(K_call,2)),
                    },
                }
            except Exception:
                res['prob_retorno_faixas'] = None

        try:
            capital_100 = preco_entrada*100
            sim_100 = res.get('simulacao_100_acoes')  # preserva o que o bloco de call simples já setou
            if sim_100 is None and retorno_full is not None and kdo is not None and kuo is not None:
                dentro_mask = (~tocou_baixa_full)&(~tocou_alta_full)
                ret_dentro = retorno_full[dentro_mask]
                sim_100 = {
                    'acoes': 100, 'preco_foto': round(preco_entrada, 2), 'capital': round(capital_100, 2),
                    'defesa': {'probabilidade_pct': round(float(tocou_baixa_full.mean()*100), 2),
                               'retorno_pct': 0.0, 'retorno_reais': 0.0,
                               'descricao': 'Protegido: nem ganha nem perde (defesa em '+str(round(kdo,2))+')'},
                    'dentro': {'probabilidade_pct': round(float(dentro_mask.mean()*100), 2),
                               'retorno_medio_pct': round(float(ret_dentro.mean()*100), 2) if len(ret_dentro) else 0.0,
                               'retorno_medio_reais': round(float(ret_dentro.mean()*capital_100), 2) if len(ret_dentro) else 0.0,
                               'descricao': 'Fica dentro do range (ganha a variação × alavancagem)'},
                    'teto': {'probabilidade_pct': round(float(tocou_alta_full.mean()*100), 2),
                             'retorno_pct': round(teto_retorno*100, 2), 'retorno_reais': round(teto_retorno*capital_100, 2),
                             'descricao': 'Trava no teto (barreira em '+str(round(kuo,2))+')'},
                }
            elif retorno_full2 is not None and kdo is not None:
                exposto_mask = tocou_barreira2
                ret_exposto = variacao_full2[exposto_mask]
                sim_100 = {
                    'acoes': 100, 'preco_foto': round(preco_entrada, 2), 'capital': round(capital_100, 2),
                    'prefixado': {'probabilidade_pct': round(float((~tocou_barreira2).mean()*100), 2),
                                  'retorno_pct': round(ganho_prefixado*100, 2), 'retorno_reais': round(ganho_prefixado*capital_100, 2),
                                  'descricao': 'Ganha o prefixado (não tocou a barreira)'},
                    'exposto': {'probabilidade_pct': round(float(exposto_mask.mean()*100), 2),
                                'retorno_medio_pct': round(float(ret_exposto.mean()*100), 2) if len(ret_exposto) else 0.0,
                                'retorno_medio_reais': round(float(ret_exposto.mean()*capital_100), 2) if len(ret_exposto) else 0.0,
                                'descricao': 'Tocou a barreira: fica exposto à variação real (sem garantia)'},
                }
            res['simulacao_100_acoes'] = sim_100
        except Exception:
            res['simulacao_100_acoes'] = None

        return jsonify(res)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── RANKING DE POSICOES ATIVAS POR TIPO DE ESTRUTURA (11/07/2026) ────
# ADICIONADO 11/07/2026 -- item 15 do backlog. Taxonomia fechada com o
# usuario: 4 categorias mutuamente exclusivas, cada uma com seu proprio
# "lado seguro" que define sucesso (ver PROMPT_NOVA_SESSAO_v2.md secao
# "Taxonomia FECHADA"). Reaproveita 100% a mesma engine de
# /montecarlo/posicao_ativa (via app.test_client(), self-dispatch interno,
# sem round-trip de rede real) -- garante que o numero mostrado no
# ranking e SEMPRE identico ao numero mostrado no card individual da
# posicao, nunca uma formula paralela que possa divergir.
_TIPOS_RANKING_POSICOES = ('lancamento_coberto', 'retorno_controlado', 'bidirecional', 'put_seco')

def _categoria_posicao(p):
    tp = p.get('tipo_posicao')
    if tp == 'simples':
        return 'lancamento_coberto'
    if tp == 'barreira_simples':
        return 'retorno_controlado'
    if tp == 'barreira':
        return 'bidirecional'
    # 'put_seco' nao tem tipo_posicao proprio ainda -- nenhuma posicao real
    # hoje se encaixa aqui (nenhuma venda de put a seco ativa). Fica pronto
    # esperando: se um dia existir campo/estrategia identificando isso,
    # tratar aqui.
    return None

@app.route('/posicoes/ranking/<tipo>', methods=['GET'])
def get_ranking_posicoes(tipo):
    """
    Ranking das Posicoes Ativas por probabilidade de sucesso, DENTRO da
    mesma categoria de estrutura (nunca mistura lancamento coberto com
    bidirecional -- decisao explicita do usuario, comparar coisa com
    coisa). Ordenado ASCENDENTE por probabilidade de sucesso -- a posicao
    mais em risco (menor chance de bater a propria regua) aparece primeiro,
    para o usuario saber onde focar atencao.
    """
    if tipo not in _TIPOS_RANKING_POSICOES:
        return jsonify({'error': f"tipo invalido, use um de {_TIPOS_RANKING_POSICOES}"}), 400
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/positions.json',
            headers={'Cache-Control': 'no-cache'}, timeout=10)
        if not r.ok:
            return jsonify({'error': 'positions.json indisponivel'}), 500
        data = r.json()
        candidatas = [p for p in data.get('ativas', []) if _categoria_posicao(p) == tipo]

        if not candidatas:
            return jsonify({'tipo': tipo, 'total': 0, 'itens': []})

        client = app.test_client()
        itens = []
        for p in candidatas:
            payload = {
                'ticker': p['ticker'],
                'data_entrada': p['data_entrada'],
                'vencimento': p['vencimento'],
            }
            campo_sucesso = None
            if tipo == 'lancamento_coberto':
                payload['k_call'] = p['strike']
                payload['exercicio'] = p.get('exercicio', 'europeia')
                campo_sucesso = 'prob_sem_exercicio'
            elif tipo == 'retorno_controlado':
                payload['kdo'] = p['kdo']
                if p.get('ganho_prefixado_pct') is not None:
                    payload['ganho_prefixado_pct'] = p['ganho_prefixado_pct']
                campo_sucesso = 'prob_ganho_prefixado'
            elif tipo == 'bidirecional':
                payload['kdo'] = p['kdo']
                payload['kuo'] = p['kuo']
                if p.get('alavancagem') is not None:
                    payload['alavancagem'] = p['alavancagem']
                if p.get('teto_retorno_pct') is not None:
                    payload['teto_retorno_pct'] = p['teto_retorno_pct']
                campo_sucesso = 'prob_sem_barreira'

            try:
                resp = client.post('/montecarlo/posicao_ativa', json=payload)
                rd = resp.get_json()
            except Exception as e:
                rd = {'error': str(e)}

            if not rd or rd.get('error'):
                itens.append({
                    'id': p['id'], 'ticker': p['ticker'], 'nome': p.get('nome'),
                    'erro': (rd or {}).get('error', 'falha ao calcular'),
                    'probabilidade_sucesso_pct': None,
                })
                continue

            prob_sucesso = rd.get(campo_sucesso)
            itens.append({
                'id': p['id'],
                'ticker': p['ticker'],
                'nome': p.get('nome'),
                'estrategia': p.get('estrategia'),
                'vencimento': p.get('vencimento'),
                'dias_restantes': rd.get('dias_restantes'),
                'preco_atual': rd.get('preco_atual'),
                'probabilidade_sucesso_pct': prob_sucesso,
                'campo_origem': campo_sucesso,
            })

        # Ordena: itens com probabilidade calculada primeiro (ascendente --
        # menor prob de sucesso = mais risco = aparece no topo), erros por
        # ultimo (sem numero pra ordenar).
        com_prob = [i for i in itens if i['probabilidade_sucesso_pct'] is not None]
        sem_prob = [i for i in itens if i['probabilidade_sucesso_pct'] is None]
        com_prob.sort(key=lambda i: i['probabilidade_sucesso_pct'])

        return jsonify({'tipo': tipo, 'total': len(itens), 'itens': com_prob + sem_prob})
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
        S = float(data['price']) if data.get('price') else None
        sigma = float(data['sigma']) if data.get('sigma') else 0.35
        usar_garch = data.get('usar_garch', True)  # GARCH ligado por padrao, pode desligar

        # Tipo de exercicio: AMERICANA (risco de exercicio em QUALQUER momento
        # ate o vencimento, nao so no fim) vs EUROPEIA (so no vencimento).
        # OBRIGATORIO e explicito (sem default silencioso) — usuario decidiu
        # que isso nao deve ser assumido, precisa vir junto do payload em toda
        # foto nova. Erro 400 se ausente, em vez de assumir um dos dois.
        exercicio = data.get('exercicio')
        if exercicio not in ('americana', 'europeia'):
            return jsonify({'error': "campo 'exercicio' obrigatorio: 'americana' ou 'europeia' (sem padrao implicito)"}), 400
        is_americana = (exercicio == 'americana')

        garch_info = None
        cl = []
        if not S:
            for host in ['query1','query2']:
                try:
                    r=requests.get(
                        f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y',
                        headers={'User-Agent':'Mozilla/5.0'},timeout=8)
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
        debug_brapi = None
        if not cl:
            # Preco ja veio do cliente (ex: ROXO34, bloqueado no Yahoo via Render),
            # mas ainda precisamos do HISTORICO para GARCH/vol — tenta brapi como
            # fonte alternativa (mesma usada em /indicators, que ja funciona p/ esses casos)
            try:
                symbol_bp = ticker.replace('.SA','').upper()
                rb = requests.get(
                    f'https://brapi.dev/api/quote/{symbol_bp}?range=3mo&interval=1d&fundamental=true',
                    headers=BRAPI_HEADERS, timeout=10)
                debug_brapi = {'status': rb.status_code, 'symbol': symbol_bp}
                if rb.ok:
                    rb_json = rb.json()
                    debug_brapi['has_results'] = bool(rb_json.get('results'))
                    rd = rb_json.get('results',[{}])[0]
                    hist = rd.get('historicalDataPrice',[])
                    debug_brapi['hist_len'] = len(hist)
                    cl_bp = [x['close'] for x in hist if x.get('close')]
                    debug_brapi['cl_bp_len'] = len(cl_bp)
                    if cl_bp:
                        cl = cl_bp
                        sigma = vol_hist(cl)
                else:
                    debug_brapi['body'] = rb.text[:200]
            except Exception as e_brapi:
                debug_brapi = {'exception': str(e_brapi)}
        if not sigma or sigma==0.35:
            sigma=VOL_DEFAULTS.get(ticker.replace('.SA','').upper(), VOL_DEFAULTS.get('DEFAULT', 0.35))
        if cl and not data.get('sigma'):
            sigma=vol_hist(cl)
        sigma_hist = sigma  # guarda vol. historica simples antes de qualquer ajuste GARCH

        # GARCH(1,1) — refina a vol usada na simulacao com base no regime atual
        # (clusters de volatilidade) em vez da media fixa de 21 dias do vol_hist
        # Limiar reduzido (50) quando o historico veio do brapi com poucos dados
        # disponiveis (plano gratuito so permite range=3mo, ~60-65 pontos) — nos
        # demais casos (Yahoo, 1y completo) mantem o limiar padrao de 60.
        min_pontos_garch = 50 if debug_brapi else 60
        if usar_garch and cl and len(cl) >= min_pontos_garch:
            try:
                garch_info = garch_11(cl, horizon_days=min(T_days, 60))
                if garch_info:
                    sigma = garch_info['vol_garch_projetada_pct'] / 100
            except: pass

        def _simula(sig):
            T2=max(T_days,1)/252.0
            if is_americana:
                # AMERICANA: risco de exercicio em QUALQUER momento ate o
                # vencimento — simula a trajetoria diaria completa e usa
                # max/min para detectar se o strike foi tocado em algum dia,
                # nao so no preco final (mesma logica ja usada nas barreiras
                # kdo/kuo das estruturas bidirecionais).
                dias2=max(T_days,1)
                dt2=1/252.0
                drift_d2=-0.5*sig**2*dt2
                vol_step_d2=sig*math.sqrt(dt2)
                z_path2=np.random.standard_normal((n,dias2))
                paths2=S*np.exp(np.cumsum(drift_d2+vol_step_d2*z_path2,axis=1))
                max_p2=np.max(paths2,axis=1)
                min_p2=np.min(paths2,axis=1)
                call_ex2=max_p2>K_call
                kdo_hit2=(min_p2<=kd) if kd else np.zeros(n,dtype=bool)
            else:
                # EUROPEIA: exercicio so e possivel no vencimento — so o
                # preco final importa.
                sqT2=math.sqrt(T2)
                drift2=-0.5*sig**2*T2
                z2=np.random.standard_normal(n)
                ST2=S*np.exp(drift2+sig*sqT2*z2)
                call_ex2=ST2>K_call
                kdo_hit2=(ST2<=kd) if kd else np.zeros(n,dtype=bool)
            return {
                'prob_sucesso':round(float((~call_ex2).mean()*100),2),
                'prob_call_exercida':round(float(call_ex2.mean()*100),2),
                'prob_kdo_atingido':round(float(kdo_hit2.mean()*100),2) if kd else None,
            }

        # Simulacao principal (usa sigma final, que e GARCH se disponivel)
        if is_americana:
            dias=max(T_days,1)
            dt=1/252.0
            drift_d=-0.5*sigma**2*dt
            vol_step_d=sigma*math.sqrt(dt)
            z_path=np.random.standard_normal((n,dias))
            paths=S*np.exp(np.cumsum(drift_d+vol_step_d*z_path,axis=1))
            max_p=np.max(paths,axis=1)
            min_p=np.min(paths,axis=1)
            ST=paths[:,-1]  # preco final tambem guardado, para referencia/exibicao
            call_ex=max_p>K_call
            kdo_hit=(min_p<=kd) if kd else np.zeros(n,dtype=bool)
        else:
            T=max(T_days,1)/252.0
            sqT=math.sqrt(T)
            drift=-0.5*sigma**2*T
            z=np.random.standard_normal(n)
            ST=S*np.exp(drift+sigma*sqT*z)
            call_ex=ST>K_call
            kdo_hit=(ST<=kd) if kd else np.zeros(n,dtype=bool)

        # Simulacao comparativa com vol. historica simples (sempre calculada se GARCH foi usado)
        comparativo_hist = _simula(sigma_hist) if (garch_info and sigma_hist != sigma) else None

        # ── FAIXAS DE RETORNO + SIMULACAO 100 ACOES — venda de CALL coberta
        # simples (k_call). Mecanica binaria: se NAO exercida, retorno = a
        # variacao REAL da acao (continua livre, sem teto, sem defesa); se
        # EXERCIDA, retorno trava em (K_call/preco_foto - 1) -- o premio em
        # si (recebido na largada) NAO entra aqui pois e contabilizado em
        # separado pelo usuario (entra na conta independente do desfecho).
        # So calculado quando o payload trouxer 'meta_pct' (a meta do
        # usuario, ex 2.25 para 2,25%/mes) — usa o preco_foto, que pode ser
        # diferente do preco atual quando chamado para uma posicao ATIVA
        # ja em andamento (nesse caso preco_foto = preco na entrada).
        meta_pct = data.get('meta_pct')
        preco_foto_param = data.get('preco_foto')
        prob_retorno_faixas = None
        simulacao_100_acoes = None
        if meta_pct is not None and not kd:
            try:
                preco_base = float(preco_foto_param) if preco_foto_param else S
                meta = float(meta_pct) / 100
                variacao_final = (ST - preco_base) / preco_base
                retorno_call = np.where(call_ex, (K_call/preco_base - 1), variacao_final)
                prob_retorno_faixas = {
                    'menor_que_0': round(float((retorno_call < 0).mean() * 100), 2),
                    'entre_0_e_1': round(float(((retorno_call >= 0) & (retorno_call < 0.01)).mean() * 100), 2),
                    'entre_1_e_2': round(float(((retorno_call >= 0.01) & (retorno_call < 0.02)).mean() * 100), 2),
                    'entre_2_e_meta': round(float(((retorno_call >= 0.02) & (retorno_call < meta)).mean() * 100), 2),
                    'maior_ou_igual_meta': round(float((retorno_call >= meta).mean() * 100), 2),
                }
                capital_100 = preco_base * 100
                ret_nao_exercida = retorno_call[~call_ex]
                simulacao_100_acoes = {
                    'acoes': 100, 'preco_foto': round(preco_base, 2), 'capital': round(capital_100, 2),
                    'nao_exercida': {
                        'probabilidade_pct': round(float((~call_ex).mean() * 100), 2),
                        'retorno_medio_pct': round(float(ret_nao_exercida.mean() * 100), 2) if len(ret_nao_exercida) else 0.0,
                        'retorno_medio_reais': round(float(ret_nao_exercida.mean() * capital_100), 2) if len(ret_nao_exercida) else 0.0,
                        'descricao': 'Não exercida: mantém ações, variação livre',
                    },
                    'exercida': {
                        'probabilidade_pct': round(float(call_ex.mean() * 100), 2),
                        'retorno_pct': round((K_call/preco_base - 1) * 100, 2),
                        'retorno_reais': round((K_call/preco_base - 1) * capital_100, 2),
                        'descricao': 'Exercida: entrega ações no strike R$' + str(round(K_call, 2)),
                    },
                }
            except Exception:
                pass

        res={
            'prob_sucesso':round(float((~call_ex).mean()*100),2),
            'prob_call_exercida':round(float(call_ex.mean()*100),2),
            'prob_put_exercida':round(float(call_ex.mean()*100),2),
            'prob_kdo_atingido':round(float(kdo_hit.mean()*100),2) if kd else None,
            'cenarios':n,'engine':'numpy',
            'comparativo_vol_historica':comparativo_hist,
            'volatilidade_historica_simples_pct':round(sigma_hist*100,2),

            'preco_atual':round(S,2),
            'volatilidade_historica_pct':round(sigma*100,2),
            'garch':garch_info,
            'k_call':K_call,'k_put':K_put,
            'knock_down':kd,'t_days':T_days,'ticker':ticker,'exercicio':exercicio,
            'prob_retorno_faixas': prob_retorno_faixas,
            'simulacao_100_acoes': simulacao_100_acoes,
        }
        return jsonify(res)
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── INDICADORES B3 — v8.5 com explicacao ─────────────
@app.route('/indicators/<path:ticker>', methods=['GET'])
def get_indicators(ticker):
    import time as _t
    global _IND_CACHE
    try:
        if ticker in _IND_CACHE:
            cd, ct = _IND_CACHE[ticker]
            if _t.time() - ct < 900:  # 15 min — brapi com range=1y demora mais
                return jsonify(cd)
    except: pass
    try:
        symbol = ticker.replace('.SA','').upper()
        cdi = get_cdi()
        hist_closes = []
        fund = {}
        preco_atual = None
        preco_prev = None

        try:
            rb = requests.get(
                f'https://brapi.dev/api/quote/{symbol}?range=1y&interval=1d&fundamental=true',
                headers=BRAPI_HEADERS, timeout=12)
            if rb.ok:
                rd = rb.json().get('results',[{}])[0]
                preco_atual = rd.get('regularMarketPrice')
                preco_prev  = rd.get('regularMarketPreviousClose')
                hist = rd.get('historicalDataPrice',[])
                hist_closes = [x['close'] for x in hist if x.get('close')]
                fund = {
                    'pl':   rd.get('priceEarnings'),
                    'pvp':  rd.get('priceToBook'),
                    'dy':   rd.get('dividendYield'),
                    'roe':  rd.get('returnOnEquity'),
                    'lpa':  rd.get('earningsPerShare'),
                    'vpa':  rd.get('bookValuePerShare'),
                }
        except: pass

        # Fallback Yahoo — completa vpa/pvp/dy/roe quando brapi (plano free) nao traz
        _debug_yahoo = {'tentou': False, 'erro': None, 'resultado': None}
        if not fund.get('vpa') or not fund.get('pvp'):
            _debug_yahoo['tentou'] = True
            try:
                yf = yahoo_fundamentals(ticker, _debug_yahoo)
                _debug_yahoo['resultado'] = yf
                if yf:
                    for k, v in yf.items():
                        if not fund.get(k) and v:
                            fund[k] = v
            except Exception as _e_dbg:
                _debug_yahoo['erro'] = str(_e_dbg)

        if not hist_closes or len(hist_closes) < 200:
            for yrange in ['2y','1y']:
                try:
                    ry = requests.get(
                        f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={yrange}',
                        headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
                    if ry.ok:
                        dy = ry.json()
                        meta = dy['chart']['result'][0]['meta']
                        preco_atual = preco_atual or meta.get('regularMarketPrice')
                        raw = dy['chart']['result'][0]['indicators']['quote'][0]['close']
                        cl2 = [c for c in raw if c]
                        if cl2:
                            if len(cl2) > len(hist_closes):
                                hist_closes = cl2
                            if len(hist_closes) >= 200:
                                break
                except: pass

        if not hist_closes or not preco_atual:
            return jsonify({'error': f'Sem dados para {symbol}'}), 404

        # Fallback de preco_prev (fechamento anterior real) via historico Yahoo,
        # quando a brapi nao trouxe regularMarketPreviousClose (comum em BDRs no
        # plano free) — usa o PENULTIMO close do historico como referencia, desde
        # que seja diferente do preco_atual (evita variacao zero artificial)
        if (preco_prev is None or preco_prev == preco_atual) and len(hist_closes) >= 2:
            candidato = hist_closes[-2]
            if candidato != preco_atual:
                preco_prev = candidato

        # Fundamentais hardcoded -- fonte unica: fundamentos.json (03/07/2026,
        # Prioridade 1 da modularizacao). Atualizacao trimestral = commit no
        # JSON, sem tocar em codigo. Notas por ativo (ex: ORVR3 pos-Vital)
        # vivem no proprio JSON no campo _nota.
        FUND_DATA_REF = FUND_DATA_REF_GLOBAL
        fundamentais_de_override = False
        if symbol in FUNDAMENTOS:
            for k, v in FUNDAMENTOS[symbol].items():
                if k.startswith('_'):
                    continue
                if v is not None and not fund.get(k):
                    fund[k] = v
                    fundamentais_de_override = True

        setor = SETORES_MAP.get(symbol, SETORES_MAP.get('DEFAULT', {'nome':'Geral','pl_medio':12.0,'pvp_medio':2.0,'roe_min':12}))

        closes = hist_closes
        p = float(preco_atual)

        def _mm(lst, n):
            return round(sum(lst[-n:])/n, 2) if len(lst) >= n else None
        def _rsi(cls, n=14):
            if len(cls) < n+1: return None
            gains = [max(cls[i]-cls[i-1],0) for i in range(1,len(cls))]
            losses = [max(cls[i-1]-cls[i],0) for i in range(1,len(cls))]
            ag=sum(gains[:n])/n; al=sum(losses[:n])/n
            for i in range(n,len(gains)):
                ag=(ag*(n-1)+gains[i])/n; al=(al*(n-1)+losses[i])/n
            return round(100-100/(1+ag/al),1) if al else 100.0

        rsi14 = _rsi(closes)
        ma20  = _mm(closes,20)
        ma50  = _mm(closes,50)
        ma200 = _mm(closes,200)

        pl   = fund.get('pl')
        pvp  = fund.get('pvp')
        dy   = fund.get('dy')
        roe  = fund.get('roe')
        lpa  = fund.get('lpa')
        vpa  = fund.get('vpa')

        if dy and float(dy) > 1: dy = round(float(dy)/100, 4)

        gval = None
        if lpa and vpa and float(lpa) > 0 and float(vpa) > 0:
            gval = round(math.sqrt(22.5 * float(lpa) * float(vpa)), 2)

        pl_s  = setor.get('pl_medio', 12)
        pvp_s = setor.get('pvp_medio', 2)
        roe_s = setor.get('roe_min', 12)
        cdi_ref = cdi or 14.4

        # ── METODOLOGIAS ALTERNATIVAS DE PRECO-ALVO ──────────
        # Calculadas com as mesmas variaveis ja disponiveis (lpa, vpa, dy, pl_s, pvp_s)
        # Servem como referencia comparativa ao Graham — convergencia entre metodos
        # aumenta a confianca; divergencia grande sinaliza ativo atipico (ciclico, em
        # transicao, etc). Nao sao preditores validados, sao heuristicas classicas.
        preco_bazin = None
        preco_pl_setorial = None
        preco_vpa = None
        try:
            if dy and dy > 0 and p:
                dividendo_acao = float(dy) * float(p)
                preco_bazin = round(dividendo_acao / 0.06, 2)  # DY minimo desejado 6%
        except: pass
        try:
            if lpa and float(lpa) > 0:
                preco_pl_setorial = round(float(lpa) * pl_s, 2)
        except: pass
        try:
            if vpa and float(vpa) > 0:
                preco_vpa = round(float(vpa) * pvp_s, 2)
        except: pass

        indicadores = []

        # RSI com explicacao
        if rsi14:
            if rsi14 < 30:   sinal,exp='Alta',f'RSI {rsi14} — Sobrevenda ⚡ potencial reversao de alta'
            elif rsi14 < 45: sinal,exp='Alta',f'RSI {rsi14} — Zona favoravel, momentum positivo'
            elif rsi14 > 70: sinal,exp='Baixa',f'RSI {rsi14} — Sobrecompra ⚠ risco de correcao'
            else:            sinal,exp='Neutro',f'RSI {rsi14} — Zona neutra, sem sinal claro'
            indicadores.append({'nome':'RSI(14)','valor':rsi14,'sinal':sinal,'explicacao':exp})

        if ma20:
            s='Alta' if p>ma20 else 'Baixa'
            exp=f'Preco {"acima" if p>ma20 else "abaixo"} da MM20 ({ma20:.2f}) — tendencia CP {"positiva ✅" if p>ma20 else "negativa"}'
            indicadores.append({'nome':'MM20','valor':ma20,'sinal':s,'explicacao':exp})

        if ma50:
            s='Alta' if p>ma50 else 'Baixa'
            exp=f'Preco {"acima" if p>ma50 else "abaixo"} da MM50 ({ma50:.2f}) — tendencia MP {"positiva ✅" if p>ma50 else "negativa"}'
            indicadores.append({'nome':'MM50','valor':ma50,'sinal':s,'explicacao':exp})

        if ma200:
            s='Alta' if p>ma200 else 'Baixa'
            exp=f'Preco {"acima" if p>ma200 else "abaixo"} da MM200 ({ma200:.2f}) — tendencia LP {"positiva ✅" if p>ma200 else "negativa ⚠"}'
            indicadores.append({'nome':'MM200','valor':ma200,'sinal':s,'explicacao':exp})

        if pl:
            pl_f=float(pl)
            if pl_f<pl_s*0.7:   s,exp='Alta',f'P/L {pl_f:.1f}x muito barato vs setor ({pl_s}x) ✅✅'
            elif pl_f<pl_s:     s,exp='Alta',f'P/L {pl_f:.1f}x abaixo da media setorial ({pl_s}x) — desconto ✅'
            elif pl_f>pl_s*1.5: s,exp='Baixa',f'P/L {pl_f:.1f}x caro vs setor ({pl_s}x) — premio elevado ⚠'
            else:                s,exp='Neutro',f'P/L {pl_f:.1f}x proximo da media setorial ({pl_s}x)'
            indicadores.append({'nome':'P/L','valor':round(pl_f,1),'sinal':s,'explicacao':exp})

        if pvp:
            pvp_f=float(pvp)
            if pvp_f<1.0:    s,exp='Alta',f'P/VP {pvp_f:.2f}x abaixo do patrimonio — barata pelo criterio Graham ✅'
            elif pvp_f<pvp_s:s,exp='Alta',f'P/VP {pvp_f:.2f}x abaixo da media setorial ({pvp_s}x) — desconto ✅'
            else:             s,exp='Neutro',f'P/VP {pvp_f:.2f}x acima da media setorial ({pvp_s}x)'
            indicadores.append({'nome':'P/VP','valor':round(pvp_f,2),'sinal':s,'explicacao':exp})

        if dy:
            dy_pct=round(float(dy)*100,2)
            if dy_pct>cdi_ref:         s,exp='Alta',f'DY {dy_pct:.1f}% supera CDI ({cdi_ref:.1f}%) — dividendo bate renda fixa ⭐⭐'
            elif dy_pct>cdi_ref*0.7:   s,exp='Neutro',f'DY {dy_pct:.1f}% proximo do CDI ({cdi_ref:.1f}%) — retorno competitivo'
            else:                       s,exp='Baixa',f'DY {dy_pct:.1f}% abaixo do CDI ({cdi_ref:.1f}%) — dividendo pouco atrativo'
            indicadores.append({'nome':'Div.Yield','valor':f'{dy_pct:.1f}%','sinal':s,'explicacao':exp})

        if roe:
            roe_f=float(roe)*100 if float(roe)<1 else float(roe)
            if roe_f>roe_s:   s,exp='Alta',f'ROE {roe_f:.1f}% acima do minimo setorial ({roe_s}%) — empresa rentavel ✅'
            elif roe_f>10:    s,exp='Neutro',f'ROE {roe_f:.1f}% — retorno moderado, abaixo do benchmark'
            else:              s,exp='Baixa',f'ROE {roe_f:.1f}% — retorno fraco sobre patrimonio ⚠'
            indicadores.append({'nome':'ROE','valor':f'{roe_f:.1f}%','sinal':s,'explicacao':exp})

        if gval:
            upside_g=round((gval/p-1)*100,1)
            if upside_g>20:    s,exp='Alta',f'Graham R${gval:.2f} — upside {upside_g:.0f}% ✅✅ subavaliada'
            elif upside_g>0:   s,exp='Alta',f'Graham R${gval:.2f} — desconto {upside_g:.0f}%, margem de seguranca ✅'
            elif upside_g>-20: s,exp='Neutro',f'Graham R${gval:.2f} — cotacao {abs(upside_g):.0f}% acima do valor justo'
            else:               s,exp='Baixa',f'Graham R${gval:.2f} — sobrevalorizada {abs(upside_g):.0f}% acima ⚠'
            indicadores.append({'nome':'Graham','valor':gval,'sinal':s,'explicacao':exp})

        if lpa:
            lpa_f=float(lpa)
            indicadores.append({'nome':'LPA','valor':round(lpa_f,2),'sinal':'Alta' if lpa_f>0 else 'Baixa',
                'explicacao':f'Lucro por acao R${lpa_f:.2f} — {"empresa lucrativa ✅" if lpa_f>0 else "prejuizo por acao ⚠"}'})

        if vpa:
            indicadores.append({'nome':'VPA','valor':round(float(vpa),2),'sinal':'Neutro',
                'explicacao':f'Valor patrimonial por acao R${float(vpa):.2f} — base para P/VP e Graham'})

        # TECNICOS ADICIONAIS: MACD, Bollinger, OBV
        try:
            if len(closes) >= 35:
                def _ema(cls, n):
                    if len(cls)<n: return None
                    k=2/(n+1); e=sum(cls[:n])/n
                    for c in cls[n:]: e=c*k+e*(1-k)
                    return round(e,4)
                e12=_ema(closes,12); e26=_ema(closes,26)
                if e12 and e26:
                    macd_line=e12-e26
                    ms_list=[]
                    for ix in range(26,len(closes)):
                        a2=_ema(closes[:ix+1],12); b2=_ema(closes[:ix+1],26)
                        if a2 and b2: ms_list.append(a2-b2)
                    sig_line=_ema(ms_list,9) if len(ms_list)>=9 else None
                    hist=round(macd_line-sig_line,4) if sig_line else None
                    if hist is not None:
                        s_m='Alta' if hist>0 else 'Baixa'
                        exp_m=f'MACD hist {hist:.3f} — {"momentum alta ▲ compradores no controle ✅" if hist>0 else "momentum baixa ▼ vendedores no controle"}'
                        indicadores.append({'nome':'MACD Hist.','valor':round(hist,3),'sinal':s_m,'explicacao':exp_m})
        except: pass

        try:
            if len(closes)>=20:
                bb_r=closes[-20:]; bb_m=sum(bb_r)/20
                bb_std=math.sqrt(sum((x-bb_m)**2 for x in bb_r)/20)
                bb_up=round(bb_m+2*bb_std,2); bb_dn=round(bb_m-2*bb_std,2)
                pct_b=round((p-bb_dn)/(bb_up-bb_dn)*100,1) if bb_up!=bb_dn else 50
                if p<=bb_dn:    s_b,exp_b='Alta',f'Abaixo Banda Inf Bollinger ({bb_dn:.2f}) — sobrevenda tecnica ⚡'
                elif p>=bb_up:  s_b,exp_b='Baixa',f'Acima Banda Sup Bollinger ({bb_up:.2f}) — sobrecompra tecnica ⚠'
                else:            s_b,exp_b='Neutro',f'%B {pct_b:.0f}% dentro das bandas (inf:{bb_dn:.2f} sup:{bb_up:.2f})'
                indicadores.append({'nome':'Bollinger %B','valor':f'{pct_b:.0f}%','sinal':s_b,'explicacao':exp_b})
        except: pass

        # FUNDAMENTAIS EXTRAS (ev_ebitda/debt_ebitda/margem) -- tambem da
        # fonte unica fundamentos.json (so os 5 ativos originais tem esses
        # campos cadastrados; os demais retornam {} e os indicadores extras
        # simplesmente nao aparecem, comportamento identico ao anterior)
        extra = FUNDAMENTOS.get(symbol, {})

        ev_eb = extra.get('ev_ebitda')
        if ev_eb:
            if ev_eb<4:    s_e,exp_e='Alta',f'EV/EBITDA {ev_eb:.1f}x — muito barato vs geracao de caixa ✅✅'
            elif ev_eb<8:  s_e,exp_e='Alta',f'EV/EBITDA {ev_eb:.1f}x — valuation justo ✅'
            elif ev_eb<15: s_e,exp_e='Neutro',f'EV/EBITDA {ev_eb:.1f}x — premio sobre o setor'
            else:           s_e,exp_e='Baixa',f'EV/EBITDA {ev_eb:.1f}x — caro vs geracao de caixa ⚠'
            indicadores.append({'nome':'EV/EBITDA','valor':f'{ev_eb:.1f}x','sinal':s_e,'explicacao':exp_e})

        deb_eb = extra.get('debt_ebitda')
        if deb_eb is not None:
            if deb_eb<1.5:  s_d,exp_d='Alta',f'Div/EBITDA {deb_eb:.1f}x — endividamento saudavel, baixo risco ✅'
            elif deb_eb<3:  s_d,exp_d='Neutro',f'Div/EBITDA {deb_eb:.1f}x — endividamento moderado'
            else:            s_d,exp_d='Baixa',f'Div/EBITDA {deb_eb:.1f}x — endividamento elevado ⚠'
            indicadores.append({'nome':'Div/EBITDA','valor':f'{deb_eb:.1f}x','sinal':s_d,'explicacao':exp_d})

        margem_v = extra.get('margem')
        if margem_v:
            if margem_v>20:   s_mg,exp_mg='Alta',f'Margem liquida {margem_v:.1f}% — alta eficiencia, empresa muito rentavel ✅✅'
            elif margem_v>10: s_mg,exp_mg='Alta',f'Margem liquida {margem_v:.1f}% — boa eficiencia operacional ✅'
            elif margem_v>5:  s_mg,exp_mg='Neutro',f'Margem liquida {margem_v:.1f}% — eficiencia moderada'
            else:              s_mg,exp_mg='Baixa',f'Margem liquida {margem_v:.1f}% — margens comprimidas ⚠'
            indicadores.append({'nome':'Margem Liq.','valor':f'{margem_v:.1f}%','sinal':s_mg,'explicacao':exp_mg})

        altas  = sum(1 for i in indicadores if i['sinal']=='Alta')
        total  = len(indicadores) or 1
        score  = round((altas/total)*100)

        # Calcula idade dos fundamentais hardcoded (FUND_OVERRIDE) — aviso visual apos 90 dias
        fund_idade_dias = None
        fund_desatualizado = False
        if fundamentais_de_override:
            try:
                from datetime import datetime as _dt2
                ref = _dt2.strptime(FUND_DATA_REF, '%Y-%m-%d')
                fund_idade_dias = (_dt2.now() - ref).days
                fund_desatualizado = fund_idade_dias > 90
            except: pass

        # GARCH(1,1) — complementa os 4 metodos de preco-alvo (foto do presente)
        # com uma leitura de volatilidade projetada (clusters), util para avaliar
        # se o regime atual de risco esta subindo ou descendo
        garch_watch = None
        try:
            garch_watch = garch_11(closes, horizon_days=21)
        except: pass

        result = {
            'ticker': ticker,
            'preco_atual': round(p,2),
            'preco_anterior': round(float(preco_prev),2) if preco_prev else None,
            'setor': setor['nome'],
            'score_total': score,
            'indicadores': indicadores,
            'graham_value': gval,
            'upside_graham': round((gval/p-1)*100,1) if gval else None,
            'preco_alvo_bazin': preco_bazin,
            'upside_bazin': round((preco_bazin/p-1)*100,1) if preco_bazin else None,
            'preco_alvo_pl_setorial': preco_pl_setorial,
            'upside_pl_setorial': round((preco_pl_setorial/p-1)*100,1) if preco_pl_setorial else None,
            'preco_alvo_vpa': preco_vpa,
            'upside_vpa': round((preco_vpa/p-1)*100,1) if preco_vpa else None,
            'fund_idade_dias': fund_idade_dias,
            'fund_desatualizado': fund_desatualizado,
            'garch': garch_watch,
        }
        try:
            _IND_CACHE[ticker] = (result, _t.time())
        except: pass
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── BTC INDICATORS — v8.5 com cache ──────────────────
@app.route('/btc/indicators', methods=['GET'])
def get_btc_indicators():
    import time as _t
    if 'indicators' in _BTC_CACHE:
        cd, ct = _BTC_CACHE['indicators']
        if _t.time() - ct < 600:
            return jsonify(cd)
    try:
        r = None
        for host in ['query1','query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=1y',
                    headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                    timeout=10)
                if r.ok: break
            except: continue
        if not r or not r.ok:
            return jsonify({'error':'Yahoo BTC indisponivel'}), 500
        d = r.json()
        result_d = d['chart']['result'][0]
        q = result_d['indicators']['quote'][0]
        cl = [c for c in q.get('close',[]) if c is not None]
        vl = [v if v else 0 for v in q.get('volume',[])][-len(cl):]
        price = cl[-1]
        rsi_v = rsi(cl,14)
        mm20_v = mm(cl,20); mm50_v = mm(cl,50); mm200_v = mm(cl,200)
        ml_v,ms_v,mh_v = macd(cl)
        _,ot = obv(cl,vl)
        result = {
            'ticker':'BTC','price':round(price,0),
            'rsi_semanal':rsi_v,
            'mm20_semanal':round(mm20_v,0) if mm20_v else None,
            'mm50_semanal':round(mm50_v,0) if mm50_v else None,
            'mm200_semanal':round(mm200_v,0) if mm200_v else None,
            'macd':round(ml_v,0) if ml_v else None,
            'macd_signal':round(ms_v,0) if ms_v else None,
            'macd_histogram':round(mh_v,0) if mh_v else None,
            'obv_trend':ot,'data_points':len(cl)
        }
        _BTC_CACHE['indicators'] = (result, _t.time())
        return jsonify(result)
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── BTC CYCLE — v8.5 com cache e range menor ─────────
@app.route('/btc/cycle', methods=['GET'])
def get_btc_cycle():
    import time as _t, math as _m
    if 'cycle' in _BTC_CACHE:
        cd, ct = _BTC_CACHE['cycle']
        if _t.time() - ct < 900:
            return jsonify(cd)
    try:
        r = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1d&range=2y',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=12)
        if not r.ok: return jsonify({'error':f'Yahoo {r.status_code}'}),500
        cl = [c for c in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        price = cl[-1]
        dma111 = mm(cl,111); dma350 = mm(cl,350)
        dma350x2 = round(dma350*2,0) if dma350 else None
        pi_dist = round(dma350x2-dma111,0) if (dma111 and dma350x2) else None
        if dma111 and dma350x2:
            if dma111>=dma350x2: pi_sig="TOPO DETECTADO Pi Cycle cruzou!"
            elif pi_dist and pi_dist<10000: pi_sig="Proximidade de topo critica"
            elif pi_dist and pi_dist<30000: pi_sig="Monitorar distancia diminuindo"
            else: pi_sig=f"Seguro — distancia US$ {pi_dist:,.0f}" if pi_dist else "Calculando..."
        else: pi_sig="Dados insuficientes (precisa 350 dias)"
        days = (_t.time()-1231006505)/86400
        fair = 10**(5.84*_m.log10(days)-17.01)
        mults=[0.10,0.20,0.35,0.55,0.80,1.20,1.70,2.50,4.00]
        names=["Fire Sale","Buy","Accumulate","Still Cheap","HODL!","Bubble?","FOMO","Sell","Max Bubble"]
        colors=["green","green","green","accent","warn","warn","danger","danger","danger"]
        rb=names[-1]; rc=colors[-1]
        for i,mv in enumerate(mults):
            if price<fair*mv: rb=names[i]; rc=colors[i]; break
        rw = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1wk&range=1y',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
        ma200w = None
        if rw.ok:
            clw=[c for c in rw.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
            ma200w = mm(clw,52)
        oc = get_btc_onchain()
        def ml_l(v): return "Capitulacao" if v<-1 else "Valor Justo" if v<1 else "Valorizado" if v<2 else "Aquecendo" if v<3 else "Sobrevalorizado" if v<5 else "Euforia TOPO"
        def nl_l(v): return "Capitulacao" if v<0 else "Esperanca/Medo" if v<0.25 else "Otimismo" if v<0.50 else "Crenca/Negacao" if v<0.75 else "Euforia TOPO"
        def pl_l(v): return "Estresse mineradores" if v<0.5 else "Pos-halving" if v<1.0 else "Normal" if v<2.0 else "Aquecendo" if v<3.4 else "Topo de ciclo"
        result = {
            'price':round(price,0),
            'pi_cycle':{'dma111':dma111,'dma350x2':dma350x2,'distance':pi_dist,'signal':pi_sig},
            'rainbow':{'band':rb,'color':rc},
            'ma200w':round(ma200w,0) if ma200w else None,
            'ma200w_pct':round((price-ma200w)/ma200w*100,1) if ma200w else None,
            'mvrv_zscore':{'value':oc['mvrv_zscore'],'label':ml_l(oc['mvrv_zscore'])},
            'nupl':{'value':oc['nupl'],'label':nl_l(oc['nupl'])},
            'puell':{'value':oc['puell_multiple'],'label':pl_l(oc['puell_multiple'])},
            'sopr':oc['sopr'],'realized_price':oc['realized_price'],
            'onchain_updated':oc['updated']
        }
        _BTC_CACHE['cycle'] = (result, _t.time())
        return jsonify(result)
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ── FEAR & GREED ──────────────────────────────────────
@app.route('/feargreed', methods=['GET'])
def get_fear_greed():
    try:
        r=requests.get('https://api.alternative.me/fng/?limit=1',headers={'User-Agent':'Mozilla/5.0'},timeout=8)
        if r.ok:
            item=r.json().get('data',[{}])[0]
            return jsonify({'value':int(item.get('value',50)),'value_classification':item.get('value_classification','Neutro'),'timestamp':item.get('timestamp','')})
    except: pass
    return jsonify({'value':50,'value_classification':'Neutro','timestamp':''}),200

# ── CALENDAR — v8.5 multi-source ─────────────────────
@app.route('/calendar', methods=['GET'])
def get_calendar():
    import re as _re
    flag_map = {
        'USD':'US','EUR':'EU','GBP':'GB','CNY':'CN',
        'JPY':'JP','CAD':'CA','AUD':'AU','NZD':'NZ','CHF':'CH',
    }
    emoji_map = {
        'USD':'🇺🇸','EUR':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳',
        'JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺','NZD':'🇳🇿','CHF':'🇨🇭',
    }
    imp_map = {'Low':1,'Medium':2,'High':3,'Holiday':0}
    currencies_ok = set(emoji_map.keys())

    def parse_date(raw):
        if not raw: return '',''
        try:
            match = _re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):\d{2}([+-])(\d{2}):(\d{2})', raw)
            if not match:
                return raw[:10], raw[11:16] if len(raw)>15 else ''
            date_p,hh,mm,sign,tzh,tzm = match.groups()
            from datetime import datetime as _dt, timedelta
            naive = _dt.strptime(date_p+' '+hh+':'+mm, '%Y-%m-%d %H:%M')
            offset = int(tzh)*60+int(tzm)
            if sign=='-': offset=-offset
            utc = naive - timedelta(minutes=offset)
            brt = utc - timedelta(hours=3)
            return brt.strftime('%Y-%m-%d'), brt.strftime('%H:%M')
        except:
            return raw[:10], raw[11:16] if len(raw)>15 else ''

    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/cache/calendar.json',
            headers={'Cache-Control':'no-cache'},
            timeout=10)
        if not r.ok:
            return jsonify({'error':'cache indisponivel'}), 500
        raw = r.json()
        events = []
        for e in raw:
            cur = e.get('country','')
            if cur not in currencies_ok: continue
            imp = imp_map.get(e.get('impact',''),0)
            if imp < 2: continue
            date_str, time_str = parse_date(e.get('date',''))
            if not date_str: continue
            actual = e.get('actual') or None
            forecast = e.get('forecast') or None
            signal = None
            if actual and forecast:
                try:
                    a = float(str(actual).replace('%','').replace('K','000').replace('M','000000'))
                    f2 = float(str(forecast).replace('%','').replace('K','000').replace('M','000000'))
                    signal = 'beat' if a>=f2 else 'miss'
                except: pass
            events.append({
                'date':date_str,'time':time_str,
                'country':cur,'flag':emoji_map.get(cur,'🌐'),
                'event':e.get('title',''),
                'importance':imp,
                'actual':actual,'forecast':forecast,
                'previous':e.get('previous') or None,
                'signal':signal,
            })
        events.sort(key=lambda x:(x['date'],x['time']))
        return jsonify(events)
    except Exception as ex:
        return jsonify({'error':str(ex)}), 500


@app.route('/calendar/test', methods=['GET'])
def get_calendar_test():
    try:
        r = requests.get('https://nfs.faireconomy.media/ff_calendar_thisweek.json',
            headers={'User-Agent':'Mozilla/5.0 Chrome/124.0.0.0'}, timeout=10)
        return jsonify({'status':r.status_code,'size':len(r.text),'sample':r.json()[:2] if r.ok else r.text[:200]})
    except Exception as e:
        return jsonify({'error':str(e)})

# ── MACRO BCB ─────────────────────────────────────────
@app.route('/macro/brazil', methods=['GET'])
def get_macro_brazil():
    result = {}
    series = {'ipca_mensal':'433','selic':'432','pib_trimestral':'22099','cambio_usd':'1','igpm':'189'}
    for name, serie_id in series.items():
        try:
            r = requests.get(f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie_id}/dados/ultimos/3?formato=json',timeout=5)
            if r.ok:
                data = r.json()
                if data: result[name] = [{'data':d['data'],'valor':d['valor']} for d in data[-3:]]
        except: pass
    return jsonify(result)

# ── US STOCKS ─────────────────────────────────────────
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
    # Adicionado 23/06/2026 -- TSM (Taiwan Semiconductor ADR) e NYSE, nao
    # NASDAQ (sem mapeamento, cairia no fallback errado). ASML e MU ja
    # ficam corretos no fallback padrao NASDAQ, nao precisam de entrada.
    'TSM':'NYSE',
    # Adicionado 23/06/2026 -- grupo Software expandido para o top 10 do
    # IGV (iShares Expanded Tech-Software ETF). CRM e NOW sao NYSE; APP,
    # CDNS, FTNT ficam corretos no fallback padrao NASDAQ.
    'PLTR':'NYSE','CRM':'NYSE','NOW':'NYSE',
}

@app.route('/us/quotes', methods=['GET'])
def get_us_quotes():
    tickers = request.args.get('tickers','').split(',')
    tickers = [t.strip().upper() for t in tickers if t.strip()][:25]
    if not tickers: return jsonify({})
    result = {}
    HL_STOCKS = {'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','NFLX','AMD','COIN','MSTR','PLTR','UBER','ABNB'}
    hl_needed = [t for t in tickers if t in HL_STOCKS]
    if hl_needed:
        try:
            rhl = requests.post('https://api.hyperliquid.xyz/info',json={'type':'allMids'},headers={'Content-Type':'application/json'},timeout=5)
            if rhl.ok:
                hl_data = rhl.json()
                for t in hl_needed:
                    tk = 'GOOGL' if t in ('GOOG','GOOGL') else t
                    if tk in hl_data:
                        price = round(float(hl_data[tk]),2)
                        result[t] = {'price':price,'prev':round(price*0.999,2),'src':'HL'}
        except: pass
    remaining = [t for t in tickers if t not in result]
    if remaining:
        exc_map = {**{k:v for k,v in _US_EXCHANGE.items()}}
        tv_tks = [f"{exc_map.get(t,'NASDAQ')}:{t}" for t in remaining]
        try:
            rtv = requests.post('https://scanner.tradingview.com/america/scan',
                json={'symbols':{'tickers':tv_tks},'columns':['close','change_abs']},
                headers={'User-Agent':'Mozilla/5.0'},timeout=8)
            if rtv.ok:
                for item in rtv.json().get('data',[]):
                    sym = item.get('s','').split(':')[-1]
                    d2 = item.get('d',[])
                    if d2 and d2[0]:
                        close = round(float(d2[0]),2)
                        chg = float(d2[1]) if len(d2)>1 and d2[1] else 0
                        result[sym] = {'price':close,'prev':round(close-chg,2),'src':'TV'}
        except: pass
    still_missing = [t for t in tickers if t not in result]
    for t in still_missing[:8]:
        q = yquote(t)
        if q: result[t] = q
    return jsonify(result)

# Total de market cap do S&P 500 -- numero MUDA TODO DIA (diferente de
# fundamentais trimestrais como P/L/ROE), entao e tratado explicitamente
# como aproximacao com data de referencia, mesmo padrao do FUND_DATA_REF.
# Atualizar manualmente de vez em quando (sem necessidade de precisao
# diaria -- o objetivo e mostrar ORDEM DE GRANDEZA da concentracao, nao um
# numero exato). Fonte: Slickcharts (soma do market cap de todos os
# constituintes do indice).
SP500_TOTAL_MARKETCAP_USD = 68.06e12  # ref. 23/06/2026 (Slickcharts)
SP500_TOTAL_MARKETCAP_REF = '2026-06-23'

# Adicionado 23/06/2026 -- usado para EXTRAPOLAR o tamanho total do setor
# de software (todos os 115 holdings do IGV), sem precisar buscar
# market cap de cada um individualmente. Logica (confirmada com o
# usuario, ele concordou que faz sentido dado que o IGV e ponderado por
# market cap -- ou seja, peso_% = market_cap_empresa / market_cap_total
# do indice, por definicao, nao aproximacao):
#   market_cap_total_IGV = soma_marketcap_top10 / SOFTWARE_TOP10_PESO_PCT
# Fonte do peso conhecido: StockAnalysis/Finnhub, dado de 18/06/2026 (IGV
# tinha 115 holdings, top 10 = 60.84% do fundo). Atualizar esse numero de
# vez em quando (igual FUND_DATA_REF) -- nao precisa ser diario.
SOFTWARE_TOP10_PESO_PCT = 0.6084
SOFTWARE_TOP10_PESO_REF = '2026-06-18'  # data do dado original (IGV holdings)

# CORRIGIDO 23/06/2026 (7a correcao): apos 3 tentativas diferentes via
# Yahoo (v7/finance/quote, v8/finance/chart marketCap direto, v8/chart
# calculado via price x sharesOutstanding) todas falharem de forma
# consistente em producao -- usuario confirmou que NENHUM campo de
# valuation (marketCap nem sharesOutstanding) vem no meta do Yahoo nesse
# ambiente, mesmo com preco/historico funcionando normalmente -- fica
# claro que e uma limitacao real e consistente do Yahoo para esse tipo de
# dado nesse IP/ambiente, nao um erro de implementacao. Adicionado
# scraping do 8marketcap.com como fallback final.
#

@app.route('/us/concentracao', methods=['GET'])
def get_us_concentracao():
    """
    Calcula o peso agregado de um grupo de tickers (ex: Magnificent 7,
    Semicondutores, Software, Energia IA) sobre o market cap TOTAL do
    S&P 500 -- usado como sinal de concentracao/risco de bolha. Busca o
    market cap individual de cada ticker via Yahoo v8/finance/chart (UMA
    chamada por ticker) -- mesmo endpoint que yquote() ja usa com sucesso
    comprovado durante toda a sessao.

    CORRIGIDO 23/06/2026 (2a correcao): usuario reportou que TODOS os 4
    grupos passaram a falhar com "Não foi possível calcular" (nao so m7
    como na 1a correcao). Causa raiz real identificada: a implementacao
    original usava v7/finance/quote, um endpoint NAO-OFICIAL e
    historicamente instavel/sujeito a bloqueio do Yahoo (relatos publicos
    de quebra frequente). O v8/finance/chart, em contraste, e estavel ha
    anos e e o mesmo que ja funciona em yquote() para todas as commodities/
    indices desta sessao. meta.marketCap esta disponivel nesse endpoint
    tambem -- nao precisava do v7 desde o inicio.

    Query param: grupo (qualquer chave valida do tickers_map abaixo).

    Retorna: peso_pct (agregado vs S&P 500), market_cap_grupo_usd,
    detalhe por ticker, e a data de referencia do total do indice (para
    deixar explicito que e uma aproximacao, nao um numero exato em tempo
    real).
    """
    grupo = request.args.get('grupo', 'semi')
    tickers_map = {
        'semi': ['NVDA','AMD','AVGO','TSM','ASML','INTC','MU','QCOM'],
        'm7': ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA'],
        # Expandido 23/06/2026 -- top 10 do IGV (iShares Expanded
        # Tech-Software ETF), que juntos somam 60.84% do fundo (fonte:
        # StockAnalysis/Finnhub, dado de 18/06/2026). Usado tambem como
        # base para a extrapolacao do setor de software completo -- ver
        # SOFTWARE_TOP10_PESO_PCT abaixo.
        'software': ['PANW','PLTR','MSFT','ORCL','CRWD','CRM','APP','CDNS','NOW','FTNT'],
        # energia_ia REMOVIDO 23/06/2026 -- usuario decidiu nao vale o
        # esforco: CEG/VST/TLN/D/OKLO sao utilities pequenas demais,
        # sem dado disponivel em nenhuma das 4 fontes tentadas (Yahoo
        # v7/v8 + 8marketcap, que so cobre top ~100 por market cap).
    }
    tickers = tickers_map.get(grupo)
    if not tickers:
        return jsonify({'error': f"grupo invalido: {grupo!r} (validos: {list(tickers_map.keys())})"}), 422

    detalhe = {}
    soma_marketcap = 0.0
    erros_por_ticker = {}

    def _buscar_marketcap(t):
        """Busca marketCap de 1 ticker. Retorna (ticker, valor_ou_None,
        erro_ou_None).

        CORRIGIDO 23/06/2026 (5a correcao): usuario reportou erro real
        'sem marketCap no meta' para TODOS os tickers apos a 4a correcao
        (paralelizacao). Causa raiz: meta.marketCap NAO e um campo
        garantido em v8/finance/chart -- relatos publicos confirmam que
        campos do meta desse endpoint mudam/desaparecem sem aviso do
        Yahoo. v7/finance/quote e a fonte correta historicamente para
        marketCap (campo nativo desse endpoint), mas a tentativa anterior
        com ele falhava por usar busca em LOTE (multiplos simbolos numa
        chamada). Agora: v7 INDIVIDUAL por ticker (nao lote) como fonte
        primaria, com fallback para v8/chart se o v7 falhar para aquele
        ticker especifico.
        """
        # Tenta v7/finance/quote primeiro (fonte nativa do campo marketCap)
        try:
            r = requests.get(
                f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={t}',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if r.ok:
                resultados = r.json().get('quoteResponse', {}).get('result', [])
                if resultados:
                    mc = resultados[0].get('marketCap')
                    if mc:
                        return (t, round(float(mc), 2), None)
        except Exception:
            pass  # cai no fallback v8 abaixo

        # Fallback: v8/finance/chart (caso v7 falhe ou nao traga marketCap
        # para esse ticker especifico)
        try:
            r = requests.get(
                f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&range=5d',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if r.ok:
                m = r.json()['chart']['result'][0]['meta']
                mc = m.get('marketCap')
                if mc:
                    return (t, round(float(mc), 2), None)
                # CORRIGIDO 23/06/2026 (6a correcao): testando isoladamente
                # se sharesOutstanding e mais estavel que marketCap direto
                # no mesmo meta -- ambos vem do v8/chart, sem chamada de
                # rede extra. Se funcionar, calculamos marketCap = preco x
                # sharesOutstanding em vez de depender do Yahoo ja
                # entregar o campo pronto.
                preco = m.get('regularMarketPrice')
                shares = m.get('sharesOutstanding')
                if preco and shares:
                    mc_calculado = float(preco) * float(shares)
                    return (t, round(mc_calculado, 2), None)
        except Exception:
            pass  # cai no fallback 8marketcap abaixo

        # Ultimo fallback: parsing do HTML do 8marketcap.com ja buscado
        # ANTES do loop paralelo (ver html_8marketcap_paginas abaixo) --
        # evita N x 4 requisicoes de rede redundantes (uma busca por
        # pagina, compartilhada por todos os tickers do grupo).
        mc_8mc = _parsear_marketcap_8marketcap(t, _get_html_8marketcap())
        if mc_8mc:
            return (t, round(mc_8mc, 2), None)
        return (t, None, 'sem marketCap em v7, v8 (direto/calculado) nem 8marketcap')

    # Busca o HTML do 8marketcap UMA VEZ (nao por ticker) antes do loop
    # paralelo -- ver _parsear_marketcap_8marketcap acima para o motivo.
    # Cache lazy: paginas do 8marketcap so sao buscadas se ALGUM ticker
    # realmente precisar (Yahoo v7/v8 falhando) -- evita 4 requisicoes de
    # rede desnecessarias quando todos os tickers resolvem via Yahoo.
    _cache_8marketcap = {'paginas': None}
    _lock_8marketcap = Lock()
    def _get_html_8marketcap():
        with _lock_8marketcap:
            if _cache_8marketcap['paginas'] is None:
                _cache_8marketcap['paginas'] = _buscar_html_8marketcap_paginas()
            return _cache_8marketcap['paginas']

    # CORRIGIDO 15/07/2026 (item 5.1, C1 do plano em PROMPT_NOVA_SESSAO_v2.md):
    # era "with ThreadPoolExecutor(max_workers=8) as executor:
    # executor.map(...)" -- esse padrao ESPERA TODAS as threads terminarem
    # antes de responder, sem limite de tempo proprio. Na pratica quase
    # sempre e rapido (grupo tem so 7-10 tickers, max_workers=8 cobre quase
    # todos em paralelo de verdade), mas no PIOR CASO (Yahoo v7 lento +
    # fallback v8 lento + fallback 8marketcap lento pra um ticker so) a
    # resposta inteira fica presa esperando, sem limite. Convertido pro
    # MESMO padrao ja validado em _fetch_etfs_dy_yahoo_bulk/
    # _fetch_etfs_preco_yahoo_bulk (fontes_etfs.py): orcamento de tempo
    # fixo via concurrent.futures.wait + shutdown(wait=False). Diferenca
    # pratica pro caso de B2/B3: aqui sao so 7-10 tickers (nao ~68), entao
    # o numero de threads eventualmente abandonadas no pior caso e bem
    # menor -- risco proporcionalmente baixo, ganho real (nunca mais fica
    # esperando indefinidamente).
    ex_mc = ThreadPoolExecutor(max_workers=8)
    try:
        futuros_mc = {ex_mc.submit(_buscar_marketcap, t): t for t in tickers}
        prontos_mc, pendentes_mc = _cf_wait(list(futuros_mc.keys()), timeout=20)
        for fut in prontos_mc:
            t = futuros_mc[fut]
            try:
                _, valor, erro = fut.result()
            except Exception as e:
                valor, erro = None, str(e)
            if valor is not None:
                detalhe[t] = valor
                soma_marketcap += valor
            else:
                erros_por_ticker[t] = erro or 'sem marketCap'
        for fut in pendentes_mc:
            t = futuros_mc[fut]
            erros_por_ticker[t] = 'timeout (>20s) buscando marketCap'
    finally:
        ex_mc.shutdown(wait=False)

    if not detalhe:
        return jsonify({'error': f'nenhum market cap obtido do Yahoo (detalhes: {erros_por_ticker})'}), 502

    peso_pct = round(soma_marketcap / SP500_TOTAL_MARKETCAP_USD * 100, 2)

    # CORRIGIDO 23/06/2026 (9a correcao) -- EXTRAPOLACAO para o grupo
    # 'software': usuario notou que mesmo com o top 10 do IGV, o numero
    # ainda subestima o setor de software completo (115 holdings no
    # indice). Como o IGV e ponderado por market cap (peso_% = mcap /
    # mcap_total_indice, por DEFINICAO), usa-se regra de 3 para estimar o
    # mcap total do indice a partir do mcap do top 10 conhecido + peso %
    # conhecido. Usuario concordou explicitamente com esse metodo --
    # exposto com TOTAL transparencia na resposta (nao apenas o numero
    # final) para que o calculo seja auditavel, nao uma caixa-preta.
    extrapolacao_software = None
    if grupo == 'software':
        # CORRIGIDO 23/06/2026 (10a correcao): a extrapolacao rodava
        # incondicionalmente, mesmo com a base do top 10 incompleta (caso
        # real: so 4 de 10 tickers conseguiram dado, 6 falharam por
        # estarem fora do top 100 do 8marketcap). Isso distorcia o
        # resultado, porque a regra de 3 pressupoe que soma_marketcap
        # representa os 10 tickers (60.84% do indice) -- com so 4,
        # soma_marketcap esta artificialmente baixa e a extrapolacao
        # fica sem sentido. Agora so calcula se pelo menos 70% dos
        # tickers do grupo tiverem dado (ex: 7 de 10); caso contrario,
        # avisa explicitamente que a base esta incompleta demais.
        cobertura = len(detalhe) / len(tickers) if tickers else 0
        if cobertura >= 0.7:
            mcap_total_estimado = soma_marketcap / SOFTWARE_TOP10_PESO_PCT
            peso_pct_extrapolado = round(mcap_total_estimado / SP500_TOTAL_MARKETCAP_USD * 100, 2)
            extrapolacao_software = {
                'metodo': 'Top 10 do IGV conhecido (soma_marketcap_top10) dividido pelo peso % conhecido desses 10 dentro do indice = mcap total ESTIMADO do setor de software inteiro (115 empresas). Depois comparado contra o S&P 500 total.',
                'top10_marketcap_usd': round(soma_marketcap, 2),
                'top10_peso_pct_no_indice': round(SOFTWARE_TOP10_PESO_PCT * 100, 2),
                'top10_peso_pct_ref_data': SOFTWARE_TOP10_PESO_REF,
                'setor_completo_marketcap_estimado_tri_usd': round(mcap_total_estimado / 1e12, 2),
                'setor_completo_peso_pct_sp500_estimado': peso_pct_extrapolado,
                'aviso': 'ESTIMATIVA -- nao e soma direta de market caps, e extrapolacao via regra de 3 assumindo que a proporcao do top 10 (60.84% em 18/06) ainda e representativa hoje.',
            }
        else:
            extrapolacao_software = {
                'erro': f'Base incompleta demais para extrapolar com confianca: so {len(detalhe)} de {len(tickers)} tickers do top 10 do IGV tem dado (minimo 70% = 7 de 10). Numero ficaria distorcido.',
            }

    # CORRIGIDO 23/06/2026 (8a correcao): usuario notou que o peso_pct
    # calculado (25.62% para m7) estava bem abaixo do valor real conhecido
    # (33-35% segundo multiplas fontes de mercado em junho/2026). Causa
    # raiz: ate aqui, tickers que falhavam em TODAS as fontes (Yahoo v7/v8
    # + 8marketcap) eram simplesmente OMITIDOS da soma, sem nenhum aviso na
    # resposta -- erros_por_ticker so aparecia na mensagem de erro do caso
    # de FALHA TOTAL, nunca em sucesso parcial. Agora sempre incluido na
    # resposta, com contagem explicita de quantos tickers faltaram, para
    # que o usuario (e qualquer sessao futura) saiba quando o numero esta
    # incompleto em vez de confiar nele como se fosse a soma completa.
    return jsonify({
        'grupo': grupo,
        'tickers': tickers,
        'tickers_com_dado': list(detalhe.keys()),
        'tickers_sem_dado': erros_por_ticker,
        'market_cap_grupo_usd': round(soma_marketcap, 2),
        'market_cap_grupo_tri_usd': round(soma_marketcap / 1e12, 2),
        'detalhe_por_ticker_usd': detalhe,
        'peso_pct_sp500': peso_pct,
        'extrapolacao_setor_completo': extrapolacao_software,
        'sp500_total_tri_usd': round(SP500_TOTAL_MARKETCAP_USD / 1e12, 2),
        'sp500_total_ref_data': SP500_TOTAL_MARKETCAP_REF,
        'aviso': (
            f'INCOMPLETO: {len(erros_por_ticker)} de {len(tickers)} tickers sem dado ({list(erros_por_ticker.keys())}) -- peso_pct esta SUBESTIMADO'
            if erros_por_ticker else
            'Aproximacao -- market cap total do indice muda diariamente, numero de referencia pode estar desatualizado'
        ),
    })

# ── POSIÇÕES (JSON modular) ───────────────────────────
def _validar_positions(data):
    """Valida estrutura do positions.json. Retorna lista de erros (vazia se OK)."""
    erros = []
    if not isinstance(data, dict):
        return ['positions.json deve ser um objeto JSON']

    campos_base_simples = ['id','ticker','nome','tipo_posicao','estrategia','strike','vol_impl','tipo','vencimento']
    campos_base_barreira = ['id','ticker','nome','tipo_posicao','estrategia','vencimento','entry','kdo','kuo']
    # ADICIONADO 26/06/2026: 'barreira_simples' para estruturas
    # retorno_controlado -- tem SO barreira de baixa (KDO), SEM KUO/teto de
    # alta (diferente de 'barreira', que e bidirecional completo com duas
    # barreiras). Sem este tipo, BSLV39 (retorno_controlado real, vindo de
    # migracao automatica) nao tinha como ser validado sem INVENTAR um KUO
    # que a estrutura real do banco nao tem -- usuario rejeitou
    # explicitamente qualquer dado inventado.
    campos_base_barreira_simples = ['id','ticker','nome','tipo_posicao','estrategia','vencimento','entry','kdo']
    campos_encerrada = ['id','ticker','estrategia','status']

    for i, p in enumerate(data.get('ativas', [])):
        pid = p.get('id', f'#{i}')
        if 'tipo_posicao' not in p:
            erros.append(f"ativas[{pid}]: falta campo 'tipo_posicao'")
            continue
        if p['tipo_posicao'] == 'simples':
            campos = campos_base_simples
        elif p['tipo_posicao'] == 'barreira':
            campos = campos_base_barreira
        elif p['tipo_posicao'] == 'barreira_simples':
            campos = campos_base_barreira_simples
        else:
            campos = None
        if campos is None:
            erros.append(f"ativas[{pid}]: tipo_posicao '{p['tipo_posicao']}' invalido (use 'simples', 'barreira' ou 'barreira_simples')")
            continue
        for campo in campos:
            if campo not in p or p[campo] is None:
                erros.append(f"ativas[{pid}]: falta campo obrigatorio '{campo}'")
        try:
            from datetime import datetime as _dt
            _dt.strptime(p.get('vencimento',''), '%Y-%m-%d')
        except (ValueError, TypeError):
            erros.append(f"ativas[{pid}]: 'vencimento' deve ser formato YYYY-MM-DD")

    ids_vistos = set()
    for i, p in enumerate(data.get('ativas', [])):
        pid = p.get('id')
        if pid in ids_vistos:
            erros.append(f"ativas: id '{pid}' duplicado")
        if pid: ids_vistos.add(pid)

    for i, p in enumerate(data.get('encerradas', [])):
        pid = p.get('id', f'#{i}')
        for campo in campos_encerrada:
            if campo not in p or p[campo] is None:
                erros.append(f"encerradas[{pid}]: falta campo obrigatorio '{campo}'")

    return erros

# ── ESCRITA NO GITHUB (analises.json) — Fase 2, motor pre-trade ─────
import os as _os_module

def _github_write_token():
    return _os_module.environ.get('GITHUB_WRITE_TOKEN')

def _github_get_file(path):
    """Le um arquivo do repo via API do GitHub (com auth), retornando (conteudo_decodificado, sha)."""
    import base64 as _b64
    token = _github_write_token()
    if not token:
        raise RuntimeError('GITHUB_WRITE_TOKEN nao configurado')
    r = requests.get(
        f'https://api.github.com/repos/vmasardinha-coder/trader-desk/contents/{path}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'},
        timeout=10)
    if not r.ok:
        raise RuntimeError(f'Falha ao ler {path} via API ({r.status_code}): {r.text[:200]}')
    d = r.json()
    conteudo = _b64.b64decode(d['content']).decode('utf-8')
    return conteudo, d['sha']

def _github_put_file(path, conteudo_str, sha, mensagem):
    """Escreve um arquivo no repo via API do GitHub (com auth), usando o SHA atual."""
    import base64 as _b64
    token = _github_write_token()
    if not token:
        raise RuntimeError('GITHUB_WRITE_TOKEN nao configurado')
    b64 = _b64.b64encode(conteudo_str.encode('utf-8')).decode('utf-8')
    payload = {'message': mensagem, 'content': b64, 'sha': sha, 'branch': 'main'}
    r = requests.put(
        f'https://api.github.com/repos/vmasardinha-coder/trader-desk/contents/{path}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'},
        json=payload, timeout=15)
    if not r.ok:
        raise RuntimeError(f'Falha ao escrever {path} via API ({r.status_code}): {r.text[:300]}')
    return r.json()

def _github_criar_arquivo(path, conteudo_str, mensagem):
    """Cria um arquivo NOVO no repo (sem SHA previo -- payload sem 'sha').
    Usado como fallback caso stats_analises.json ainda nao exista."""
    import base64 as _b64
    token = _github_write_token()
    if not token:
        raise RuntimeError('GITHUB_WRITE_TOKEN nao configurado')
    b64 = _b64.b64encode(conteudo_str.encode('utf-8')).decode('utf-8')
    payload = {'message': mensagem, 'content': b64, 'branch': 'main'}
    r = requests.put(
        f'https://api.github.com/repos/vmasardinha-coder/trader-desk/contents/{path}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'},
        json=payload, timeout=15)
    if not r.ok:
        raise RuntimeError(f'Falha ao criar {path} via API ({r.status_code}): {r.text[:300]}')
    return r.json()

_CAMPOS_OBRIGATORIOS_ANALISE = ['id', 'ticker', 'nome', 'data_foto', 'preco_foto', 'prazo_dias', 'tipo_estrutura', 'origem', 'status']
# NOTA (25/06/2026): para tipo_estrutura='fii', prazo_dias NAO representa
# um vencimento real (FIIs sao perpetuos, sem data de expiracao como as
# estruturadas). Convencao adotada: prazo_dias=9999 para FIIs, sinalizando
# "sem vencimento" -- mantem o campo obrigatorio (evita duplicar logica de
# validacao so para FII) sem dar a falsa impressao de um prazo real.
_STATUS_VALIDOS = ['em_analise', 'ativa', 'encerrada']

def _hoje_str():
    """Data de hoje no formato YYYY-MM-DD, mesmo padrao ja usado em data_foto."""
    from datetime import date as _date
    return _date.today().isoformat()

# ── ROTAS DE FIIs (Prioridade 2, fase 4, 04/07/2026) ───
# Extraidas para rotas_fiis.py. Registradas aqui via funcao (nao import
# direto) para evitar import circular -- ver docstring de rotas_fiis.py.
import rotas_fiis
rotas_fiis.registrar_rotas(app, _github_get_file, _github_put_file, _hoje_str, _requer_auth_escrita)

def _incrementar_contador_rejeitadas():
    """
    Incrementa o contador PERMANENTE de analises rejeitadas, em
    stats_analises.json (arquivo separado de analises.json -- analises.json
    e uma lista pura sem wrapper de metadados, mudar isso quebraria
    _validar_analise e o frontend que itera direto sobre o array).

    Este contador NUNCA diminui, mesmo apos a limpeza de 30 dias remover
    o registro detalhado da analise rejeitada da listagem visivel (ver
    rotina de limpeza chamada em GET /analises) -- e o numero que sustenta
    a estatistica de longo prazo ('total de rejeitadas: 47') pedida pelo
    usuario, independente de quantos registros detalhados ainda existem.
    """
    try:
        conteudo_str, sha = _github_get_file('stats_analises.json')
        stats = json.loads(conteudo_str) if conteudo_str.strip() else {'total_rejeitadas': 0}
    except RuntimeError:
        # Arquivo ainda nao existe -- comeca do zero (sera criado abaixo)
        stats, sha = {'total_rejeitadas': 0}, None

    stats['total_rejeitadas'] = stats.get('total_rejeitadas', 0) + 1
    stats['ultima_atualizacao'] = _hoje_str()
    novo_conteudo = json.dumps(stats, indent=2, ensure_ascii=False)

    if sha:
        _github_put_file('stats_analises.json', novo_conteudo, sha,
            f"feat: incrementa contador de rejeitadas para {stats['total_rejeitadas']}")
    else:
        _github_criar_arquivo('stats_analises.json', novo_conteudo,
            "feat: cria stats_analises.json com contador inicial de rejeitadas")
_TIPOS_VALIDOS = ['bidirecional', 'retorno_controlado', 'premio', 'simples', 'fii']
_ORIGENS_VALIDAS = ['customizada', 'pronta', 'screening_fiis']

def _validar_analise(item):
    erros = []
    for campo in _CAMPOS_OBRIGATORIOS_ANALISE:
        if campo not in item or item[campo] is None:
            erros.append(f"falta campo obrigatorio '{campo}'")
    if item.get('status') not in _STATUS_VALIDOS:
        erros.append(f"status invalido: {item.get('status')!r} (validos: {_STATUS_VALIDOS})")
    if item.get('tipo_estrutura') not in _TIPOS_VALIDOS:
        erros.append(f"tipo_estrutura invalido: {item.get('tipo_estrutura')!r} (validos: {_TIPOS_VALIDOS})")
    if item.get('origem') not in _ORIGENS_VALIDAS:
        erros.append(f"origem invalida: {item.get('origem')!r} (validas: {_ORIGENS_VALIDAS})")
    return erros

@app.route('/analises', methods=['GET'])
def get_analises():
    """Le analises.json do repo (publico, via raw — leitura nao precisa de token).

    ADICIONADO 23/06/2026: filtra da resposta (nao do arquivo real --
    evitar escrita a cada GET) analises com status='encerrada' e
    motivo_encerramento='rejeitada' com mais de 30 dias desde
    data_rejeicao. O CONTADOR PERMANENTE em stats_analises.json (ver
    _incrementar_contador_rejeitadas) ja foi incrementado no momento da
    rejeicao e nao depende desses registros continuarem visiveis aqui --
    por isso e seguro escondê-los da listagem sem perder a estatistica
    de longo prazo. O arquivo real (analises.json) so e fisicamente
    limpo numa rotina de manutencao futura (nao implementada ainda --
    por ora so filtra a resposta, registro real permanece no historico
    do GitHub indefinidamente, sem custo de leitura).
    """
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/analises.json',
            headers={'Cache-Control': 'no-cache'}, timeout=10)
        if not r.ok:
            return jsonify({'error': 'analises.json indisponivel'}), 500
        data = r.json()

        from datetime import date as _date, timedelta as _timedelta
        limite = _date.today() - _timedelta(days=30)
        data_filtrada = []
        for item in data:
            if item.get('motivo_encerramento') == 'rejeitada' and item.get('data_rejeicao'):
                try:
                    data_rej = _date.fromisoformat(item['data_rejeicao'])
                    if data_rej < limite:
                        continue  # mais de 30 dias -- esconde da listagem
                except ValueError:
                    pass  # data malformada, mantem visivel por seguranca
            data_filtrada.append(item)

        return jsonify(data_filtrada)
    except ValueError as e:
        return jsonify({'error': f'analises.json com JSON malformado: {str(e)}'}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analises/stats', methods=['GET'])
def get_analises_stats():
    """
    Expoe o contador PERMANENTE de analises rejeitadas (stats_analises.json),
    para o dashboard de Encerradas mostrar a estatistica de longo prazo
    mesmo apos os registros detalhados individuais terem sumido da
    listagem (ver filtro de 30 dias em GET /analises).
    """
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/stats_analises.json',
            headers={'Cache-Control': 'no-cache'}, timeout=10)
        if not r.ok:
            return jsonify({'total_rejeitadas': 0, 'ultima_atualizacao': None})
        return jsonify(r.json())
    except Exception:
        return jsonify({'total_rejeitadas': 0, 'ultima_atualizacao': None})

@app.route('/analises', methods=['POST'])
@_requer_auth_escrita
def criar_analise():
    """
    Cria uma nova foto em Em Análise. Espera no body o objeto da análise
    (sem 'id', que é gerado automaticamente; sem 'status', que é forçado
    para 'em_analise' nesta rota — só pode mudar via /analises/<id>/status).
    """
    try:
        novo = request.get_json() or {}
        novo['status'] = 'em_analise'
        if 'id' not in novo or not novo['id']:
            import time as _time
            novo['id'] = f"an_{int(_time.time())}"

        erros = _validar_analise(novo)
        if erros:
            return jsonify({'error': 'dados invalidos', 'detalhes': erros}), 422

        # BACKLOG #4 (30/06/2026): congela bandas GARCH no momento da
        # criacao (mesmo conceito da Foto do Papel), pra depois comparar
        # o preco real contra o que o modelo projetava nesse dia. Nunca
        # bloqueia a criacao se a busca de historico falhar.
        bandas_congeladas = _congelar_bandas_analise(novo)
        if bandas_congeladas:
            novo['bandas_congeladas'] = bandas_congeladas

        conteudo_str, sha = _github_get_file('analises.json')
        lista = json.loads(conteudo_str) if conteudo_str.strip() else []
        lista.append(novo)
        novo_conteudo = json.dumps(lista, indent=2, ensure_ascii=False)
        _github_put_file('analises.json', novo_conteudo, sha,
            f"feat: nova analise {novo['id']} ({novo.get('ticker','?')}) via app")
        return jsonify(novo), 201
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analises/<id>/foto-bandas', methods=['GET'])
def get_analise_foto_bandas(id):
    """
    BACKLOG #4 (30/06/2026): retorna as bandas congeladas no momento da
    criacao da analise (id) + o caminho real do preco desde data_foto +
    score de assertividade (mesmo conceito de GET /foto-papel, mas
    referenciado por id de analise em vez de ticker solto -- assim o
    congelamento fica atrelado ao prazo/estrutura real da negociacao,
    nao a um "papel" generico da watchlist).
    """
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/analises.json',
            headers={'Cache-Control': 'no-cache'}, timeout=10)
        if not r.ok:
            return jsonify({'error': 'analises.json indisponivel'}), 500
        lista = r.json()
        item = next((a for a in lista if a.get('id') == id), None)
        if not item:
            return jsonify({'error': f'analise {id} nao encontrada'}), 404

        bandas_congeladas = item.get('bandas_congeladas')
        if not bandas_congeladas:
            return jsonify({'encontrado': False, 'motivo': 'sem_bandas_congeladas', 'id': id})

        historico_real = _fetch_closes_for_foto(item['ticker'], item['data_foto'])
        periodo_ref = str(max(bandas_congeladas['periodos']))
        score = _score_assertividade_bandas(historico_real, bandas_congeladas['bandas'].get(periodo_ref))

        return jsonify({
            'encontrado': True,
            'id': id,
            'ticker': item['ticker'],
            'data_foto': item['data_foto'],
            'preco_foto': item['preco_foto'],
            'bandas_congeladas': bandas_congeladas,
            'historico_real': historico_real,
            'score': score,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _migrar_para_positions(item_analise):
    """
    Adicionado 26/06/2026. Quando uma analise de ESTRUTURADA (retorno_
    controlado ou bidirecional) muda para status='ativa', migra de fato
    para positions.json -- ate aqui, so o status mudava dentro de
    analises.json, sem nunca aparecer em "Posicoes Ativas" (bug real
    reportado pelo usuario com BSLV39, ficou "ativa" mas nunca migrou).

    Volatilidade implicita (vol_impl) e CALCULADA via GARCH(1,1) (mesma
    funcao garch_11 ja usada em /montecarlo) a partir do historico real
    de 1 ano do ticker -- usuario confirmou explicitamente que NAO precisa
    de input manual, o sistema ja calcula isso em outros lugares do app
    e deve fazer o mesmo aqui ("eu so preciso do calculo... ele ja calcula
    tudo").

    Campos do registro de positions.json, todos derivados do que JA EXISTE
    em analises.json + GARCH (nada inventado):
    - entry = preco_foto
    - kdo = kdo (ja existe)
    - kdo_pct = calculado (kdo/preco_foto - 1)
    - vencimento = data_foto + prazo_dias
    - data_entrada = data_foto
    - exercicio = 'europeia' por padrao (estruturas de banco -- Itau/
      bidirecional/retorno_controlado -- sao tipicamente europeias,
      conforme ja documentado; usuario pode corrigir manualmente se for
      excecao americana, igual ja aconteceu com ROXO34/ROXOG105)
    - vol_impl = GARCH(1,1) sobre 1 ano de historico real

    APENAS para tipo_estrutura in ('retorno_controlado', 'bidirecional').
    Para 'simples' (covered call) e 'fii', NAO migra automaticamente ainda
    -- 'simples' tem schema mais antigo com codigo_opcao/strike que merece
    decisao separada; 'fii' ja tem fluxo proprio (/carteira-fiis).

    Retorna (sucesso: bool, mensagem: str).
    """
    tipo = item_analise.get('tipo_estrutura')
    if tipo not in ('retorno_controlado', 'bidirecional'):
        return False, f"migracao automatica nao implementada para tipo_estrutura={tipo!r} ainda"

    from datetime import datetime as _dt_migra, timedelta as _td_migra

    ticker = item_analise['ticker']
    symbol = ticker.replace('.SA', '').upper()
    preco_foto = float(item_analise['preco_foto'])
    kdo = item_analise.get('kdo')
    if kdo is None:
        return False, "campo 'kdo' ausente na analise -- nao e possivel migrar sem barreira definida"

    try:
        data_foto = _dt_migra.strptime(item_analise['data_foto'][:10], '%Y-%m-%d').date()
        prazo_dias = int(item_analise['prazo_dias'])
        vencimento = (data_foto + _td_migra(days=prazo_dias)).isoformat()
    except Exception as e:
        return False, f"erro ao calcular vencimento: {e}"

    # Busca historico real de 1 ano e calcula GARCH -- mesmo padrao ja
    # usado em multiplos lugares do proxy.py (ex: /montecarlo/barrier).
    #
    # CORRIGIDO 26/06/2026: usuario descobriu que o fallback anterior
    # (0.35 fixo) NAO e aceitavel -- "nao invente dados para eu decidir
    # na analise... eu decidi hoje com base em X% de chance de ganho".
    # PRINCIPIO: NUNCA usar numero fixo arbitrario quando existe QUALQUER
    # calculo real possivel a partir do preco do ativo, mesmo que mais
    # simples (vol historica com poucos pontos ainda e dado real; um
    # fallback de 0.35 nao e). Cascata: GARCH (>=60 pontos, mais robusto)
    # -> vol historica calculada manualmente com QUALQUER quantidade >=5
    # pontos (sem o limite de 22 que vol_hist() teria, que tambem cai em
    # 0.35 fixo) -- so se houver MENOS de 5 pontos validos no historico
    # inteiro de 1 ano (caso extremo, praticamente sem negociacao) e que
    # fica sem calculo real possivel, e o campo e marcado explicitamente
    # como nao calculado (None), nunca com numero inventado escondido.
    vol_impl = None
    vol_impl_fonte = 'nao_calculado'  # sinaliza a ORIGEM do numero, para o usuario auditar
    try:
        for host in ['query1', 'query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}.SA?interval=1d&range=1y',
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                if r.ok:
                    d = r.json()
                    raw_cl = d['chart']['result'][0]['indicators']['quote'][0]['close']
                    cl = [c for c in raw_cl if c is not None]
                    if len(cl) >= 60:
                        garch_info = garch_11(cl, horizon_days=min(prazo_dias, 60))
                        if garch_info:
                            vol_impl = round(garch_info['vol_garch_projetada_pct'] / 100, 4)
                            vol_impl_fonte = 'garch'
                        else:
                            vol_impl = round(vol_hist(cl), 4)
                            vol_impl_fonte = 'vol_historica_22d'
                    elif len(cl) >= 5:
                        # Menos pontos do que o GARCH exige (60) -- calcula
                        # vol historica manualmente com o que tiver
                        # disponivel (real, nao inventado), em vez de cair
                        # no limite de 22 dias do vol_hist() (que tambem
                        # teria fallback fixo se nao alcancasse).
                        n_pontos = len(cl)
                        rets = [math.log(cl[i]/cl[i-1]) for i in range(1, n_pontos)]
                        if rets:
                            media = sum(rets) / len(rets)
                            var = sum((r - media)**2 for r in rets) / len(rets)
                            vol_impl = round(math.sqrt(var * 252), 4)
                            vol_impl_fonte = f'vol_historica_{n_pontos}d_baixa_amostra'
                    break
            except Exception:
                continue
    except Exception:
        pass  # vol_impl permanece None se a busca de rede falhar completamente

    kdo_pct = round((float(kdo) / preco_foto - 1) * 100, 2)
    ganho_pct = item_analise.get('ganho_prefixado_pct')

    novo_id = re.sub(r'[^a-z0-9]', '', symbol.lower())[:8] or f"pos{int(time.time())}"

    novo_registro = {
        'id': novo_id,
        'ticker': ticker,
        'nome': item_analise.get('nome', symbol),
        'tipo_posicao': 'barreira_simples' if tipo == 'retorno_controlado' else 'barreira',
        'estrategia': 'Retorno Controlado' if tipo == 'retorno_controlado' else 'Bidirecional',
        'vencimento': vencimento,
        'entry': preco_foto,
        'kdo': float(kdo),
        'kdo_pct': f"{kdo_pct:.1f}%",
        'vol_impl': vol_impl,  # pode ser None se nao houve dado suficiente -- NUNCA numero inventado
        'vol_impl_fonte': vol_impl_fonte,  # 'garch' | 'vol_historica_22d' | 'vol_historica_Nd_baixa_amostra' | 'nao_calculado' -- para auditoria do usuario
        'data_entrada': item_analise['data_foto'][:10],
        'exercicio': 'europeia',  # default -- usuario corrige manualmente se for excecao
    }
    if ganho_pct is not None:
        novo_registro['ganho_sem_barreira'] = f"{ganho_pct}% fixo"
        novo_registro['ganho_prefixado_pct'] = ganho_pct  # campo numerico, usado por /montecarlo/posicao_ativa para calcular EV completo
    if tipo == 'bidirecional':
        kuo = item_analise.get('kuo')
        if kuo is not None:
            novo_registro['kuo'] = float(kuo)
            novo_registro['kuo_pct'] = f"{round((float(kuo)/preco_foto - 1) * 100, 1)}%"
        if item_analise.get('teto_retorno_pct') is not None:
            novo_registro['teto_retorno_pct'] = item_analise['teto_retorno_pct']
        if item_analise.get('alavancagem') is not None:
            novo_registro['alavancagem'] = item_analise['alavancagem']

    try:
        conteudo_pos_str, sha_pos = _github_get_file('positions.json')
        dados_pos = json.loads(conteudo_pos_str) if conteudo_pos_str.strip() else {'ativas': [], 'encerradas': []}
        dados_pos.setdefault('ativas', [])
        # CORRIGIDO 05/08/2026: a checagem original bloqueava por TICKER
        # repetido ("qualquer posicao ja ativa com esse papel-base bloqueia
        # a migracao"), copiada do padrao usado em carteira_fiis.json -- so
        # que la faz sentido (1 FII = 1 posicao), aqui NAO faz: o usuario ja
        # roda LEGITIMAMENTE varias estruturas concorrentes no mesmo
        # papel-base (ex: AXIA3.SA tem a3b E a3c ativas ao mesmo tempo).
        # Bug real descoberto 05/08/2026: uma analise bidirecional de AXIA3
        # ("Protecao Parcial", lote 20/07/2026) foi ativada pelo usuario e
        # ficou PRA SEMPRE presa em analises.json com status='ativa' --
        # nunca apareceu em Posicoes Ativas -- porque a migracao automatica
        # falhava silenciosamente nesse bloqueio (AXIA3.SA "ja existia").
        # Fix: protege contra duplicar a MESMA migracao (checa por ID, que
        # e realmente unico por posicao) em vez de por ticker. Em caso raro
        # de colisao de ID (2 migracoes do mesmo papel no mesmo minuto),
        # gera sufixo numerico automatico em vez de bloquear.
        ids_existentes = {p.get('id') for p in dados_pos['ativas']}
        if novo_id in ids_existentes:
            sufixo = 2
            id_base = novo_id
            while novo_id in ids_existentes:
                novo_id = f"{id_base}{sufixo}"[:8]
                sufixo += 1
            novo_registro['id'] = novo_id
        dados_pos['ativas'].append(novo_registro)
        novo_conteudo_pos = json.dumps(dados_pos, indent=2, ensure_ascii=False)
        _github_put_file('positions.json', novo_conteudo_pos, sha_pos,
            f"feat: migra {ticker} de Em Analise para Posicoes Ativas (vol_impl fonte={vol_impl_fonte})")
        if vol_impl is None:
            return True, f"{ticker} migrado, mas vol_impl NAO PUDE ser calculado (histórico insuficiente, <5 pontos válidos em 1 ano) -- complete manualmente em positions.json"
        return True, f"{ticker} migrado para positions.json com vol_impl={vol_impl} (fonte: {vol_impl_fonte})"
    except Exception as e:
        return False, f"erro ao gravar positions.json: {e}"

@app.route('/analises/<analise_id>/status', methods=['PUT'])
@_requer_auth_escrita
def mudar_status_analise(analise_id):
    """
    Move uma analise entre estagios (em_analise -> ativa -> encerrada, ou
    em_analise -> encerrada direto). Espera {'status': 'ativa'} no body.

    ADICIONADO 23/06/2026: aceita tambem 'motivo_encerramento' opcional no
    body (ex: 'rejeitada' -- analise descartada na Fase A por
    probabilidade real baixa via Monte Carlo, NUNCA chegou a ser ativa).
    Quando motivo_encerramento='rejeitada', incrementa o contador
    PERMANENTE em stats_analises.json -- esse contador nunca diminui,
    mesmo apos a limpeza de 30 dias remover o registro detalhado da
    listagem (ver rotina de limpeza em /analises GET).

    ADICIONADO 26/06/2026: quando novo_status='ativa' E tipo_estrutura in
    (retorno_controlado, bidirecional), migra AUTOMATICAMENTE para
    positions.json de fato (ver _migrar_para_positions) -- antes disso, o
    status mudava mas o registro nunca aparecia em "Posicoes Ativas"
    (bug real reportado pelo usuario com BSLV39).
    """
    try:
        body = request.get_json() or {}
        novo_status = body.get('status')
        motivo = body.get('motivo_encerramento')
        resultado = body.get('resultado')
        if resultado and resultado not in ('sucesso', 'fracasso'):
            return jsonify({'error': f"resultado invalido: {resultado!r} (validos: sucesso, fracasso)"}), 422
        if novo_status not in _STATUS_VALIDOS:
            return jsonify({'error': f'status invalido: {novo_status!r}'}), 422

        conteudo_str, sha = _github_get_file('analises.json')
        lista = json.loads(conteudo_str) if conteudo_str.strip() else []
        encontrado = False
        item_encontrado = None
        for item in lista:
            if item.get('id') == analise_id:
                item['status'] = novo_status
                if motivo:
                    item['motivo_encerramento'] = motivo
                    item['data_rejeicao'] = _hoje_str()
                    # ADICIONADO 10/07/2026 (pedido do usuario) -- captura o
                    # EV/score/probabilidade que o RANKING JA CALCULOU no
                    # momento em que o usuario clicou em rejeitar (o front
                    # envia esses campos, que ja estavam na tela -- nao
                    # recalcula nada aqui, evita duplicar logica e evita o
                    # erro que ja aconteceu de eu -- Claude -- calcular
                    # manualmente com dado desatualizado/formula diferente
                    # do motor real). Permite o painel de Encerradas mostrar
                    # "deixou X na mesa" (EV positivo) ou "economizou X"
                    # (EV negativo) SEM precisar de calculo manual toda vez.
                    ev_rejeicao = body.get('ev_mensal_pct')
                    score_rejeicao = body.get('score')
                    prob_rejeicao = body.get('prob_meta_pct')
                    preco_atual_rejeicao = body.get('preco_atual')
                    if ev_rejeicao is not None:
                        item['ev_mensal_na_rejeicao'] = ev_rejeicao
                    if score_rejeicao is not None:
                        item['score_na_rejeicao'] = score_rejeicao
                    if prob_rejeicao is not None:
                        item['prob_meta_na_rejeicao'] = prob_rejeicao
                    if preco_atual_rejeicao is not None:
                        item['preco_encerramento'] = preco_atual_rejeicao
                if resultado:
                    item['resultado'] = resultado
                    item['data_encerramento'] = _hoje_str()
                    # Adicionado 05/07/2026 (pedido do usuario) -- captura o
                    # preco do ativo NO MOMENTO do encerramento, nao so a
                    # data. Sem isso, nao da pra calcular depois "quanto
                    # dinheiro ficou na mesa" (precisa comparar o preco real
                    # de fechamento com a distribuicao teorica projetada a
                    # partir daquele ponto). Best-effort: se o fetch falhar,
                    # segue sem travar o encerramento -- so fica sem o dado
                    # para o painel de Encerradas.
                    try:
                        yahoo_ticker = item.get('ticker', '')
                        preco_fechamento = _fetch_preco_yahoo(yahoo_ticker)
                        if preco_fechamento:
                            item['preco_encerramento'] = preco_fechamento
                    except Exception:
                        pass
                encontrado = True
                item_encontrado = dict(item)  # copia para usar na migracao apos salvar
                break
        if not encontrado:
            return jsonify({'error': f'analise {analise_id} nao encontrada'}), 404

        novo_conteudo = json.dumps(lista, indent=2, ensure_ascii=False)
        _github_put_file('analises.json', novo_conteudo, sha,
            f"feat: analise {analise_id} -> status={novo_status} via app")

        if motivo == 'rejeitada':
            _incrementar_contador_rejeitadas()

        migracao_info = None
        if novo_status == 'ativa' and item_encontrado:
            sucesso_migracao, msg_migracao = _migrar_para_positions(item_encontrado)
            migracao_info = {'migrado_para_positions': sucesso_migracao, 'detalhe': msg_migracao}

            # ADICIONADO 30/06/2026 (REAPLICADO -- versao anterior se
            # perdeu por cache do raw.githubusercontent.com num deploy
            # anterior desta mesma sessao). Uma vez migrada de verdade
            # para positions.json (posicao ativa real), o registro NAO
            # deve continuar em analises.json para sempre -- mesmo
            # principio ja usado na migracao de FIIs -> carteira_fiis.json.
            # So remove se a migracao realmente deu certo -- se falhou, o
            # registro fica em analises.json status=ativa mesmo, para o
            # usuario poder tentar de novo depois (nao perde silenciosamente).
            if sucesso_migracao:
                try:
                    conteudo_an2, sha_an2 = _github_get_file('analises.json')
                    lista_an2 = json.loads(conteudo_an2) if conteudo_an2.strip() else []
                    lista_an2_filtrada = [a for a in lista_an2 if a.get('id') != analise_id]
                    if len(lista_an2_filtrada) != len(lista_an2):
                        novo_conteudo_an2 = json.dumps(lista_an2_filtrada, indent=2, ensure_ascii=False)
                        _github_put_file('analises.json', novo_conteudo_an2, sha_an2,
                            f"feat: remove {analise_id} de analises.json (migrado para positions.json)")
                        migracao_info['removido_de_analises'] = True
                except Exception as e_remove:
                    migracao_info['removido_de_analises'] = False
                    migracao_info['erro_remocao'] = str(e_remove)

        resposta = {'id': analise_id, 'status': novo_status}
        if migracao_info:
            resposta['migracao'] = migracao_info
        return jsonify(resposta)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Adicionado 26/06/2026 -- endpoint para forcar migracao RETROATIVA de
# analises que ja estavam status='ativa' ANTES da correcao em
# mudar_status_analise (ex: BSLV39, ficou ativa mas nunca migrou para
# positions.json porque a logica de migracao automatica nao existia
# ainda quando o usuario aprovou). Tambem serve como ferramenta geral
# para qualquer caso futuro parecido.
@app.route('/analises/<analise_id>/forcar-migracao', methods=['POST'])
@_requer_auth_escrita
def forcar_migracao_retroativa(analise_id):
    try:
        conteudo_str, _ = _github_get_file('analises.json')
        lista = json.loads(conteudo_str) if conteudo_str.strip() else []
        item = next((a for a in lista if a.get('id') == analise_id), None)
        if not item:
            return jsonify({'error': f'analise {analise_id} nao encontrada'}), 404
        if item.get('status') != 'ativa':
            return jsonify({'error': f"analise {analise_id} nao esta com status='ativa' (status atual: {item.get('status')})"}), 422
        sucesso, msg = _migrar_para_positions(item)
        return jsonify({'id': analise_id, 'migrado_para_positions': sucesso, 'detalhe': msg})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── RANKING EM LOTE (Fase A→decisao) ─────────────────────
# Adicionado 25/06/2026. Resolve o problema de Victor ter que abrir analise
# por analise em "Em Analise" e copiar numeros manualmente quando o lote
# cresce (visto na pratica com o lote de 14 do dia 24/06). Roda a MESMA
# logica de probabilidade do /montecarlo/condicional para TODAS as analises
# em_analise de uma vez, monta uma tabela com todas as colunas (sem filtro
# automatico -- Victor decide manualmente olhando tudo) e calcula um SCORE
# so para ORDENACAO, nunca para esconder linhas.
#
# Formula do score (fechada com Victor em 25/06/2026):
#   retorno_mensal = ganho_pct / meses_restantes
#   peso_prazo = 1 + (30/dias_restantes) * 0.1   (vantagem leve, giro de capital)
#   SE dy do papel-base existir e for > 0 (bidirecional/retorno_controlado
#   com dividendo real cadastrado em fundamentos.json):
#       colchao_vs_cdi = (dy_anual/12) - (cdi_anual/12)
#       score = (prob_meta/100) * retorno_mensal * peso_prazo
#               + (0.1 if colchao_vs_cdi > 0 else 0)
#   SE NAO (BDR/ADR/commodity sem dividendo -- ex. ROXO34/TSLA34/BSLV39/
#   AMZO34): score = (prob_meta/100) * retorno_mensal * peso_prazo, puro,
#   sem bonus de colchao (nao tem rede de seguranca de dividendo).
# DY agora vem da fonte unica fundamentos.json (DY_GLOBAL derivado no
# startup, inclui dy_extra tipo ALOS3). Aliases mantidos para nao mexer
# no corpo de ranking_analises (03/07/2026, Prioridade 1 modularizacao).
FUND_OVERRIDE_GLOBAL = DY_GLOBAL
_SEM_DY_RELEVANTE = SEM_DY_RELEVANTE

@app.route('/analises/ranking', methods=['GET'])
def ranking_analises():
    """
    Roda a probabilidade (Monte Carlo) de TODAS as analises em_analise de
    uma vez e devolve uma tabela ja pronta para ranquear, com score de
    ORDENACAO (nunca filtro). Ver comentario acima desta funcao para a
    formula completa do score, fechada com o usuario em 25/06/2026.

    PROCESSAMENTO EM FASES (adicionado 25/06/2026, pedido do usuario apos
    timeout/crash em produção com 17 analises de uma vez): aceita query
    params opcionais 'offset' e 'limit' para processar so um pedaco do
    total por chamada (ex: 5 por vez). Sem esses params, processa TODAS
    de uma vez (comportamento original, mantido por compatibilidade).
    Resposta inclui 'total_geral' (quantas existem no total) para o
    frontend saber quando parar de pedir mais paginas.
    """
    try:
        import numpy as np
        from datetime import datetime as _dt3

        offset = int(request.args.get('offset', 0))
        limit_str = request.args.get('limit')
        limit = int(limit_str) if limit_str else None

        conteudo_str, _ = _github_get_file('analises.json')
        lista = json.loads(conteudo_str) if conteudo_str.strip() else []
        # CORRIGIDO 25/06/2026: FII (tipo_estrutura='fii') NUNCA deve entrar
        # no ranking de probabilidades -- usa Monte Carlo, que nao se
        # aplica a FII (sem barreira/meta real). Causa raiz de um crash
        # real em produção: FII tem prazo_dias=9999 (convencao "sem
        # vencimento"), e o ranking tentou simular 9999 dias de Monte
        # Carlo com n_sim=20000 -- custo computacional ~100x maior que uma
        # analise normal (14-89 dias), travando o servidor (502/503,
        # resposta JSON cortada). FII tem fluxo PROPRIO (ver /carteira-
        # fiis), nao passa por aqui.
        em_analise_total = [a for a in lista if a.get('status') == 'em_analise'
                      and a.get('tipo_estrutura') != 'fii']
        total_geral = len(em_analise_total)
        em_analise = em_analise_total[offset:offset+limit] if limit else em_analise_total

        cdi_anual = get_cdi()
        cdi_mensal = cdi_anual / 12

        resultado = []
        for a in em_analise:
            try:
                ticker = a['ticker']
                symbol = ticker.replace('.SA', '').upper()
                preco_foto = float(a['preco_foto'])
                data_foto = _dt3.strptime(a['data_foto'][:10], '%Y-%m-%d').date()
                prazo_dias = int(a['prazo_dias'])
                hoje = _dt3.now().date()
                dias_passados = (hoje - data_foto).days
                dias_restantes = max(prazo_dias - dias_passados, 1)
                meses_restantes = max(dias_restantes / 30.4, 0.1)

                # Busca preco atual + historico (mesmo padrao Yahoo->brapi
                # ja usado em /montecarlo/condicional)
                S = None
                cl = []
                sigma = 0.35
                for host in ['query1', 'query2']:
                    try:
                        r = requests.get(
                            f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y',
                            headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                        if r.ok:
                            d = r.json()
                            meta_y = d['chart']['result'][0]['meta']
                            raw_cl = d['chart']['result'][0]['indicators']['quote'][0]['close']
                            cl = [c for c in raw_cl if c is not None]
                            S = float(meta_y.get('regularMarketPrice', cl[-1] if cl else 0))
                            if cl: sigma = vol_hist(cl)
                            break
                    except: continue
                if not S:
                    try:
                        rb = requests.get(
                            f'https://brapi.dev/api/quote/{symbol}?range=3mo&interval=1d',
                            headers=BRAPI_HEADERS, timeout=10)
                        if rb.ok:
                            rd = rb.json().get('results', [{}])[0]
                            S = rd.get('regularMarketPrice')
                            hist = rd.get('historicalDataPrice', [])
                            cl_bp = [x['close'] for x in hist if x.get('close')]
                            if cl_bp:
                                cl = cl_bp
                                sigma = vol_hist(cl)
                    except: pass
                if not S or S <= 0:
                    resultado.append({**_linha_ranking_base(a), 'erro': 'preco atual indisponivel'})
                    continue

                # ADICIONADO 15/07/2026 -- achado pelo Victor: quando o
                # historico (cl) vem vazio (Yahoo/brapi sem cobertura pro
                # ticker, comum em BDRs exoticos/pouco liquidos tipo
                # SPCX34/ITLC34/MUTC34), sigma ficava silenciosamente em
                # 35% (generico), sem avisar em lugar nenhum -- podendo
                # SUBESTIMAR o risco real de tocar a barreira pra ativos
                # de fato mais volateis que isso. Agora expoe esse aviso
                # explicitamente no resultado, em vez de esconder.
                vol_generica_usada = (len(cl) == 0)

                if len(cl) >= 50:
                    try:
                        garch_info = garch_11(cl, horizon_days=min(max(dias_restantes, 1), 60))
                        if garch_info:
                            sigma = garch_info['vol_garch_projetada_pct'] / 100
                    except: pass

                tipo = a.get('tipo_estrutura')
                ganho_pct = None
                prob_meta = None

                n_sim = 20000
                dt_sim = 1/252.0
                drift_sim = -0.5*sigma**2*dt_sim
                vol_step_sim = sigma*math.sqrt(dt_sim)
                z_sim = np.random.standard_normal((n_sim, dias_restantes))
                paths_sim = S*np.exp(np.cumsum(drift_sim+vol_step_sim*z_sim, axis=1))
                min_sim = np.min(paths_sim, axis=1)
                max_sim = np.max(paths_sim, axis=1)

                # ── EV completo (adicionado 25/06/2026, item 7 do backlog) ──
                # Simulacao SEPARADA, com o PRAZO TOTAL original (prazo_dias)
                # a partir do preco_foto -- mesmo padrao ja usado em
                # /montecarlo/condicional para prob_retorno_faixas/
                # retorno_medio_pct. Pondera TODOS os cenarios (perda total
                # se romper a barreira, ganho parcial, ganho prefixado/teto)
                # pela propria media da simulacao -- nao so prob binaria de
                # "bateu ou nao bateu a meta". retorno_medio_pct = EV real.
                z_full = np.random.standard_normal((n_sim, prazo_dias))
                drift_full = -0.5*sigma**2*dt_sim
                paths_full = preco_foto*np.exp(np.cumsum(drift_full+vol_step_sim*z_full, axis=1))
                min_full = np.min(paths_full, axis=1)
                max_full = np.max(paths_full, axis=1)
                ST_full = paths_full[:, -1]
                variacao_full = (ST_full/preco_foto - 1)
                retorno_medio_pct = None

                if tipo == 'retorno_controlado' and a.get('kdo') is not None and a.get('ganho_prefixado_pct') is not None:
                    ganho_pct = float(a['ganho_prefixado_pct'])
                    kdo = float(a['kdo'])
                    tocou = min_sim <= kdo
                    prob_meta = round(float((~tocou).mean()*100), 2)
                    # EV: se nao tocou a barreira no prazo TOTAL, ganho prefixado;
                    # se tocou, fica exposto a variacao real (pode ser negativa)
                    tocou_full = min_full <= kdo
                    retorno_full_ev = np.where(~tocou_full, ganho_pct/100, variacao_full)
                    retorno_medio_pct = round(float(retorno_full_ev.mean()*100), 3)
                elif tipo == 'bidirecional' and a.get('kuo') is not None and a.get('teto_retorno_pct') is not None:
                    ganho_pct = float(a['teto_retorno_pct'])
                    kuo = float(a['kuo'])
                    tocou_alta = max_sim >= kuo
                    prob_meta = round(float(tocou_alta.mean()*100), 2)
                    alav = float(a.get('alavancagem', 1.0))
                    tocou_alta_full = max_full >= kuo
                    # CORRIGIDO 15/07/2026 -- delega pra funcao unica
                    # _retorno_bidirecional_full (topo do arquivo). Mesma
                    # correcao ja aplicada em /montecarlo/condicional e
                    # /montecarlo/posicao_ativa. Suporta 'downside_antes'/
                    # 'downside_apos' opcionais no registro da posicao/
                    # analise (analises.json), pra cobrir tambem
                    # "Protecao Parcial" (protegida antes + perda integral
                    # apos) e "Protecao Total" (kdo=None, sempre protegida).
                    # NOTA: ganho_pct fica em pontos percentuais (4.0, nao
                    # 0.04) porque 'retorno_mensal' mais abaixo depende
                    # dessa escala -- so a chamada da funcao usa /100.
                    kdo_val = a.get('kdo')
                    tocou_baixa_full = (min_full <= float(kdo_val)) if kdo_val is not None else None
                    downside_antes = a.get('downside_antes', 'positiva')
                    downside_apos = a.get('downside_apos', 'protegida')
                    retorno_full_ev = _retorno_bidirecional_full(
                        variacao_full, tocou_alta_full, tocou_baixa_full,
                        ganho_pct/100, alav, downside_antes, downside_apos)
                    retorno_medio_pct = round(float(retorno_full_ev.mean()*100), 3)
                else:
                    resultado.append({**_linha_ranking_base(a), 'erro': f'tipo_estrutura {tipo!r} nao suportado no ranking ainda'})
                    continue

                retorno_mensal = round(ganho_pct / meses_restantes, 3)  # mantido para referencia/coluna antiga
                meses_totais = max(prazo_dias / 30.4, 0.1)
                ev_mensal_pct = round(retorno_medio_pct / meses_totais, 3)
                peso_prazo = 1 + (30/dias_restantes)*0.1

                dy_anual = FUND_OVERRIDE_GLOBAL.get(symbol)
                tem_dy_relevante = (symbol not in _SEM_DY_RELEVANTE and dy_anual is not None and dy_anual > 0)
                colchao_vs_cdi = None
                if tem_dy_relevante:
                    colchao_vs_cdi = round((dy_anual/12) - cdi_mensal, 3)

                # Score agora usa EV mensal (pondera TODOS os cenarios via
                # media da simulacao), em vez de prob_meta x ganho fixo.
                # prob_meta continua exposta como coluna separada -- usuario
                # pediu para MANTER, nao substituir, so trocar o que entra
                # na formula do score.
                score = ev_mensal_pct * peso_prazo
                if tem_dy_relevante and colchao_vs_cdi is not None and colchao_vs_cdi > 0:
                    score += 0.1

                resultado.append({
                    'id': a['id'], 'ticker': ticker, 'nome': a.get('nome'),
                    'tipo_estrutura': tipo, 'lote': a.get('lote'),
                    'backtest': a.get('backtest'),
                    'preco_foto': preco_foto, 'preco_atual': round(S, 2),
                    'dias_restantes': dias_restantes,
                    'meses_restantes': round(meses_restantes, 2),
                    'ganho_pct': ganho_pct,
                    'retorno_mensal_pct': retorno_mensal,
                    'prob_meta_pct': prob_meta,
                    'retorno_medio_pct': retorno_medio_pct,
                    'ev_mensal_pct': ev_mensal_pct,
                    'dy_anual_pct': dy_anual if tem_dy_relevante else None,
                    'cdi_mensal_pct': round(cdi_mensal, 3),
                    'colchao_dy_vs_cdi_pct': colchao_vs_cdi,
                    'vol_generica_usada': vol_generica_usada,
                    'peso_prazo': round(peso_prazo, 3),
                    'score': round(score, 4),
                })
            except Exception as e_item:
                resultado.append({**_linha_ranking_base(a), 'erro': str(e_item)})

        resultado.sort(key=lambda r: r.get('score', -1) if r.get('score') is not None else -1, reverse=True)
        return jsonify({
            'cdi_anual_pct': cdi_anual,
            'total_analises': len(em_analise),
            'total_geral': total_geral,
            'offset': offset,
            'proxima_pagina_existe': bool(limit) and (offset + limit) < total_geral,
            'ranking': resultado,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _linha_ranking_base(a):
    """Linha minima quando o calculo completo falha -- nunca esconde o
    registro, so marca que deu erro (Victor ve TODOS, sempre)."""
    return {
        'id': a.get('id'), 'ticker': a.get('ticker'), 'nome': a.get('nome'),
        'tipo_estrutura': a.get('tipo_estrutura'), 'lote': a.get('lote'),
        'backtest': a.get('backtest'), 'score': None,
    }



# ── CARTEIRA DE FIIs ───────────────────────────────────
# Adicionado 25/06/2026. Decisao do usuario: FIIs ficam em arquivo PROPRIO
# (carteira_fiis.json), separado de analises.json/positions.json -- FIIs
# sao perpetuos (sem vencimento) e a metrica de sucesso e diferente das
# estruturadas (dividendo acumulado desde a ativacao, nao ganho prefixado/
# probabilidade de meta). Fluxo: screening (/fiis) -> Em Analise (POST
# /analises, tipo_estrutura='fii', JA IMPLEMENTADO) -> Carteira (este
# endpoint, ativa de fato). "Foto" tirada no MOMENTO da ativacao (nao
# retroativa ao historico de compra real, se ja possuido antes -- usuario
# aceitou essa simplificacao explicitamente).
# _CARTEIRA_FII_STATUS_VALIDOS movido para rotas_fiis.py em 04/07/2026
# (Fase 4) -- so a rota mudar_status_carteira_fii usava essa constante,
# e ela foi para la junto.

# ── RANKING DE FIIs EM ANALISE ─────────────────────────
# Adicionado 26/06/2026. Usuario pediu secao SEPARADA dentro de "Em
# Analise": "FIIs em Analise" com RANKING PROPRIO, usando os MESMOS
# criterios da aba FIIs (P/VP->DY->Liquidez->FFO->risco), mas rodando so
# sobre os FIIs que JA ESTAO em em_analise (nao o universo completo de
# 560). Estrategia: reaproveita scrape_fiis_fundamentus() (dados frescos
# do Fundamentus) e CRUZA com os tickers presentes em analises.json
# (tipo_estrutura='fii', status='em_analise') -- evita duplicar logica de
# classificacao de risco/score, sempre usa dado atualizado do mercado
# (nao o preco_foto congelado do momento da selecao).







# ── HISTÓRICO DE PROVENTOS (CARTEIRA DE FIIs) ─────────────────────────────────



# ── FOTO DE PAPEL (ANÁLISE DE ASSERTIVIDADE MONTE CARLO) ─────────────────────
# Adicionado 30/06/2026 -- backlog item 3.
# "Tirar uma foto" = congelar o preco atual e as bandas GARCH Monte Carlo para
# os 3 horizontes (21/60/90d) num dado dia, e acompanhar se o preco real
# ficou dentro ou fora das bandas ao longo do tempo.
#
# A GARCH e recalculada cada vez que a foto e consultada (usando historico
# atualizado), mas o PONTO DE PARTIDA (preco no dia da foto) fica congelado.
# Ao completar 90 dias uteis, a foto expira automaticamente.
#
# Storage: fotos_papel.json no repo GitHub (mesmo padrao de analises.json).
# Estrutura: { "PETR4.SA": { "ticker": ..., "data_foto": "2026-06-30",
#   "preco_foto": 36.50, "periodos": [21,60,90],
#   "bandas": { "21": {"p10":...,"p25":...,"p50":...,"p75":...,"p90":...},
#               "60": {...}, "90": {...} } } }

FOTOS_PATH = 'fotos_papel.json'
GITHUB_FOTOS_SHA = {}  # cache de SHA para commits

def _read_fotos():
    """Le fotos_papel.json do repo. Retorna (dict, sha)."""
    import urllib.request as _ur
    import base64 as _b64, urllib.error as _ue
    TOKEN = _os.environ.get('GITHUB_TOKEN', '')
    REPO  = _os.environ.get('GITHUB_REPO', 'vmasardinha-coder/trader-desk')
    if not TOKEN:
        return {}, None
    try:
        req = _ur.Request(
            f'https://api.github.com/repos/{REPO}/contents/{FOTOS_PATH}',
            headers={'Authorization': f'token {TOKEN}', 'Accept': 'application/vnd.github.v3+json'})
        with _ur.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read())
            sha = d['sha']
            data = json.loads(_b64.b64decode(d['content']).decode())
            GITHUB_FOTOS_SHA['sha'] = sha
            return data, sha
    except _ue.HTTPError as e:
        if e.code == 404:
            return {}, None
        raise
    except Exception:
        return {}, None

def _write_fotos(data, sha=None):
    """Salva fotos_papel.json no repo. Cria se nao existir (sha=None)."""
    import urllib.request as _ur, base64 as _b64
    TOKEN = _os.environ.get('GITHUB_TOKEN', '')
    REPO  = _os.environ.get('GITHUB_REPO', 'vmasardinha-coder/trader-desk')
    if not TOKEN:
        return False
    payload = {'message': 'update: fotos_papel.json (auto)',
               'content': _b64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()}
    if sha:
        payload['sha'] = sha
    try:
        req = _ur.Request(
            f'https://api.github.com/repos/{REPO}/contents/{FOTOS_PATH}',
            data=json.dumps(payload).encode(),
            headers={'Authorization': f'token {TOKEN}', 'Content-Type': 'application/json'},
            method='PUT')
        with _ur.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read())
            GITHUB_FOTOS_SHA['sha'] = r['content']['sha']
            return True
    except Exception:
        return False

# _calc_bandas_foto e _score_assertividade_bandas extraidas para
# motor.py em 03/07/2026 (Prioridade 2, fase 1)
from motor import _calc_bandas_foto, _score_assertividade_bandas


def _fetch_closes_for_foto(ticker, from_date_str):
    """
    Busca closes diarios desde from_date_str (YYYY-MM-DD) ate hoje.
    Tenta Yahoo primeiro; se falhar (ex: ROXO34, bloqueado no Yahoo via
    Render -- mesmo motivo documentado em /indicators e /bs), cai para
    brapi.dev como fallback. Adicionado 02/07/2026 apos usuario reportar
    que a foto da ROXO34 nunca mostrava a linha de preco real.
    Retorna list de (date_str, close).
    """
    from datetime import datetime, timedelta
    try:
        dt_from = datetime.strptime(from_date_str, '%Y-%m-%d')
        # Yahoo: periodo em Unix timestamps
        t1 = int(dt_from.timestamp()) - 86400  # 1 dia antes para pegar o proprio dia
        t2 = int(datetime.now().timestamp()) + 86400
        for host in ['query1', 'query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}'
                    f'?interval=1d&period1={t1}&period2={t2}',
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                if not r.ok:
                    continue
                d = r.json()
                result = d['chart']['result'][0]
                timestamps = result['timestamp']
                closes = result['indicators']['quote'][0]['close']
                pairs = []
                for ts, cl in zip(timestamps, closes):
                    if cl is None:
                        continue
                    dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                    if dt >= from_date_str:
                        pairs.append({'data': dt, 'close': round(float(cl), 4)})
                if pairs:
                    return pairs
            except:
                continue

        # Fallback brapi.dev (mesmo padrao usado em /bs e /indicators para
        # tickers bloqueados no Yahoo, ex ROXO34)
        try:
            symbol = ticker.replace('.SA', '').upper()
            rb = requests.get(
                f'https://brapi.dev/api/quote/{symbol}?range=3mo&interval=1d',
                headers=BRAPI_HEADERS, timeout=8)
            if rb.ok:
                rd = rb.json().get('results', [{}])[0]
                hist = rd.get('historicalDataPrice', [])
                pairs = []
                for pt in hist:
                    ts = pt.get('date')
                    cl = pt.get('close')
                    if ts is None or cl is None:
                        continue
                    try:
                        # brapi normalmente retorna 'date' como unix timestamp (segundos)
                        dt = datetime.utcfromtimestamp(int(ts)).strftime('%Y-%m-%d')
                    except (ValueError, TypeError, OSError):
                        # defensivo: caso venha como string ISO ('2026-07-01' ou
                        # '2026-07-01T00:00:00.000Z') em vez de timestamp
                        dt = str(ts)[:10]
                    if dt >= from_date_str:
                        pairs.append({'data': dt, 'close': round(float(cl), 4)})
                if pairs:
                    return sorted(pairs, key=lambda p: p['data'])
        except:
            pass
    except:
        pass
    return []

def _dias_uteis_desde(data_str):
    """Conta dias uteis (aprox) desde data_str ate hoje."""
    from datetime import datetime, timedelta
    try:
        dt = datetime.strptime(data_str, '%Y-%m-%d').date()
        hoje = datetime.now().date()
        du = 0
        cur = dt
        while cur < hoje:
            if cur.weekday() < 5:
                du += 1
            cur += timedelta(days=1)
        return du
    except:
        return 0

def _obter_preco_sigma_garch(ticker, range_hist='1y'):
    """
    Busca preco atual (ou ultimo close) + historico via Yahoo, e calcula
    sigma via GARCH(1,1) (fallback vol historica se GARCH nao rodar).
    Fatorado de post_foto_papel em 30/06/2026 para reuso em
    _congelar_bandas_analise (foto automatica em Em Analise -- backlog #4).
    Retorna (S, sigma, garch_info, closes) -- S e sigma podem ser None se
    a busca falhar (NUNCA inventa fallback fixo, principio #6).
    """
    S = None
    closes = []
    for host in ['query1', 'query2']:
        try:
            r = requests.get(
                f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_hist}',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if r.ok:
                d = r.json()
                result = d['chart']['result'][0]
                meta = result['meta']
                raw_cl = result['indicators']['quote'][0]['close']
                closes = [c for c in raw_cl if c is not None]
                S = float(meta.get('regularMarketPrice', closes[-1] if closes else 0))
                break
        except:
            continue

    if not S or S <= 0:
        return None, None, None, closes

    sigma = None
    garch_info = None
    if len(closes) >= 60:
        try:
            garch_info = garch_11(closes, horizon_days=60)
            if garch_info:
                sigma = garch_info['vol_garch_projetada_pct'] / 100
        except:
            pass
    if not sigma:
        sigma = vol_hist(closes) if closes else None

    return S, sigma, garch_info, closes

# _score_assertividade_bandas ja importada do motor.py mais acima
# (Prioridade 2, fase 1, 03/07/2026)


def _congelar_bandas_analise(novo):
    """
    Backlog #4 (30/06/2026): ao criar uma analise em Em Analise, congela
    as bandas GARCH (mesmo conceito da Foto do Papel) usando o preco_foto
    JA FECHADO da analise como ponto de partida (nao o preco ao vivo --
    o preco_foto e a premissa fixa da negociacao). Isso permite depois
    comparar o caminho real do preco contra o que o modelo projetava
    naquele dia, pra ver se "deixou dinheiro na mesa".

    Nunca bloqueia a criacao da analise se a busca de historico/GARCH
    falhar -- retorna None nesse caso (principio #6: nunca inventar
    dado). Pulado para tipo_estrutura='fii' (perpetuo, prazo_dias=9999).
    """
    if novo.get('tipo_estrutura') == 'fii':
        return None
    ticker = novo.get('ticker')
    preco_foto = novo.get('preco_foto')
    prazo_dias = novo.get('prazo_dias')
    if not ticker or not preco_foto or not prazo_dias or prazo_dias >= 9999:
        return None
    try:
        _, sigma, garch_info, _ = _obter_preco_sigma_garch(ticker)
        if not sigma:
            return None
        periodos = sorted({p for p in (21, 60, 90) if p <= prazo_dias})
        if not periodos:
            periodos = [min(prazo_dias, 21)]
        if prazo_dias not in periodos and prazo_dias <= 180:
            periodos = sorted(set(periodos + [prazo_dias]))
        bandas = _calc_bandas_foto(preco_foto, sigma, periodos=periodos)
        if not bandas:
            return None
        return {
            'sigma_pct': round(sigma * 100, 2),
            'garch': garch_info,
            'periodos': periodos,
            'bandas': bandas,
        }
    except Exception:
        return None


@app.route('/foto-papel', methods=['POST'])
def post_foto_papel():
    """
    POST /foto-papel
    Body JSON: { "ticker": "PETR4.SA" }
    Tira a foto: busca preco atual + GARCH, calcula bandas para 21/60/90d,
    salva em fotos_papel.json no repo.
    Substitui foto anterior do mesmo ticker se existir.
    """
    try:
        data = request.get_json() or {}
        ticker = data.get('ticker', '').strip()
        if not ticker:
            return jsonify({'error': "parametro 'ticker' obrigatorio"}), 400

        S, sigma, garch_info, closes = _obter_preco_sigma_garch(ticker)
        if not S:
            return jsonify({'error': f'Nao foi possivel obter preco de {ticker}'}), 500
        if not sigma:
            sigma = 0.35  # fallback final so aqui, mantido igual ao comportamento anterior

        # Calcula bandas para os 3 periodos
        bandas = _calc_bandas_foto(S, sigma, periodos=[21, 60, 90])

        from datetime import datetime
        foto = {
            'ticker': ticker,
            'data_foto': datetime.now().strftime('%Y-%m-%d'),
            'preco_foto': round(S, 4),
            'sigma_pct': round(sigma * 100, 2),
            'garch': garch_info,
            'periodos': [21, 60, 90],
            'bandas': bandas,
        }

        # Lê, atualiza, salva
        fotos, sha = _read_fotos()
        fotos[ticker] = foto
        ok = _write_fotos(fotos, sha)

        return jsonify({'ok': ok, 'foto': foto})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/foto-papel', methods=['GET'])
def get_foto_papel():
    """
    GET /foto-papel?ticker=PETR4.SA
    Retorna a foto salva + preco real historico desde a data da foto
    + score de assertividade (% do tempo dentro de cada banda).
    Se a foto tiver >= 90 dias uteis, retorna campo 'expirada': true.
    """
    ticker = request.args.get('ticker', '').strip()
    if not ticker:
        return jsonify({'error': "parametro 'ticker' obrigatorio"}), 400

    fotos, _ = _read_fotos()
    if ticker not in fotos:
        return jsonify({'encontrado': False, 'ticker': ticker})

    foto = fotos[ticker]
    dias_uteis = _dias_uteis_desde(foto['data_foto'])
    expirada = dias_uteis >= 90

    # Busca preco real historico desde a data da foto
    historico_real = _fetch_closes_for_foto(ticker, foto['data_foto'])

    # Score de assertividade: para cada dia real, verifica em qual banda caiu
    # Usa o periodo 90d como referencia (maior horizonte)
    score = _score_assertividade_bandas(historico_real, foto.get('bandas', {}).get('90'))

    return jsonify({
        'encontrado': True,
        'foto': foto,
        'dias_uteis_decorridos': dias_uteis,
        'expirada': expirada,
        'historico_real': historico_real,
        'score': score,
    })

@app.route('/foto-papel', methods=['DELETE'])
def delete_foto_papel():
    """
    DELETE /foto-papel?ticker=PETR4.SA
    Remove (reseta) a foto do ticker.
    """
    ticker = request.args.get('ticker', '').strip()
    if not ticker:
        return jsonify({'error': "parametro 'ticker' obrigatorio"}), 400
    fotos, sha = _read_fotos()
    if ticker not in fotos:
        return jsonify({'ok': True, 'msg': 'nao encontrado, nada a remover'})
    del fotos[ticker]
    ok = _write_fotos(fotos, sha)
    return jsonify({'ok': ok, 'ticker': ticker, 'msg': 'foto removida'})








@app.route('/positions', methods=['GET'])
def get_positions():
    """
    Le positions.json do repo (GitHub raw) e devolve pronto, com validacao de schema.
    Para editar/abrir/encerrar posicoes: editar positions.json direto, sem tocar em codigo.
    """
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/positions.json',
            headers={'Cache-Control':'no-cache'}, timeout=10)
        if not r.ok:
            return jsonify({'error': 'positions.json indisponivel'}), 500
        data = r.json()
        erros = _validar_positions(data)
        if erros:
            return jsonify({'error': 'positions.json invalido', 'detalhes': erros}), 422
        return jsonify(data)
    except ValueError as e:
        return jsonify({'error': f'positions.json com JSON malformado: {str(e)}'}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── BRAPI COTAÇÃO RÁPIDA ──────────────────────────────
@app.route('/brapi/<ticker>', methods=['GET'])
def get_brapi_quote(ticker):
    """
    Cotacao rapida via brapi.dev — sem indicadores, sem historico.
    Usado como fallback rapido quando TV scanner nao retorna o ticker.
    Retorna: price, prev, change_abs, change_pct
    """
    try:
        symbol = ticker.replace('.SA','').upper()
        r = requests.get(
            f'https://brapi.dev/api/quote/{symbol}?range=5d&interval=1d',
            headers=BRAPI_HEADERS, timeout=8)
        if not r.ok:
            return jsonify({'error': f'brapi {r.status_code}'}), 502
        rd = r.json().get('results', [{}])[0]
        price = rd.get('regularMarketPrice')
        prev  = rd.get('regularMarketPreviousClose')
        if not price:
            return jsonify({'error': 'sem preco'}), 404
        price = round(float(price), 2)
        prev  = round(float(prev), 2) if prev else price
        chg   = round(price - prev, 2)
        pct   = round((chg / prev * 100), 2) if prev else 0.0
        return jsonify({'ticker': symbol, 'price': price, 'prev': prev,
                        'change_abs': chg, 'change_pct': pct})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── BLACK-SCHOLES ─────────────────────────────────────
@app.route('/bs', methods=['POST'])
def black_scholes():
    """
    Calcula Black-Scholes para uma opcao call.
    Body JSON: { ticker, strike, t_days, vol_impl, tipo }
    tipo: 'call' (default) ou 'put'
    Busca preco atual via brapi -> TV scanner -> Yahoo.
    Retorna: preco_atual, prob_exercicio_bs, delta, theta_dia, vega, gamma, d1, d2
    """
    try:
        from math import exp, log, sqrt, pi as _pi, erf
        data = request.get_json() or {}
        ticker   = data.get('ticker', 'PETR4.SA')
        K        = float(data.get('strike', 30.85))
        T_days   = int(data.get('t_days', 180))
        vol_impl = float(data.get('vol_impl', 0.35))   # ja em decimal (0.35 = 35%)
        tipo     = data.get('tipo', 'call')
        r_rate   = 0.0   # taxa risk-free simplificada

        # — Busca preco atual —
        symbol = ticker.replace('.SA','').upper()
        S = None

        # 1) brapi (melhor para B3, especialmente ROXO34)
        try:
            rb = requests.get(
                f'https://brapi.dev/api/quote/{symbol}?range=5d&interval=1d',
                headers=BRAPI_HEADERS, timeout=8)
            if rb.ok:
                rd = rb.json().get('results',[{}])[0]
                p_brapi = rd.get('regularMarketPrice')
                if p_brapi: S = float(p_brapi)
        except: pass

        # 2) TV scanner (B3)
        if not S:
            try:
                rtv = requests.post('https://scanner.tradingview.com/brazil/scan',
                    json={'symbols':{'tickers':[f'BMFBOVESPA:{symbol}']},'columns':['close']},
                    timeout=5)
                if rtv.ok:
                    items = rtv.json().get('data',[])
                    if items and items[0].get('d') and items[0]['d'][0]:
                        S = float(items[0]['d'][0])
            except: pass

        # 3) Yahoo fallback
        if not S:
            q = yquote(ticker)
            if q: S = q['price']

        if not S or S <= 0:
            return jsonify({'error': f'Preco indisponivel para {ticker}'}), 500

        # — Black-Scholes —
        sigma = vol_impl
        T = max(T_days, 1) / 252.0

        # CDF normal aproximada (sem scipy)
        def _norm_cdf(x):
            return 0.5 * (1.0 + erf(x / sqrt(2.0)))

        # PDF normal
        def _norm_pdf(x):
            return exp(-0.5 * x * x) / sqrt(2.0 * _pi)

        d1 = (log(S / K) + (r_rate + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
        d2 = d1 - sigma * sqrt(T)

        if tipo == 'put':
            delta   = _norm_cdf(d1) - 1.0
            prob_ex = round(_norm_cdf(-d2) * 100, 2)   # prob put ITM no venc
        else:
            delta   = _norm_cdf(d1)
            prob_ex = round(_norm_cdf(d2) * 100, 2)    # prob call ITM no venc

        gamma = _norm_pdf(d1) / (S * sigma * sqrt(T))
        vega  = S * _norm_pdf(d1) * sqrt(T) / 100      # por 1% de vol
        theta = (-(S * _norm_pdf(d1) * sigma) / (2 * sqrt(T))) / 252  # por dia

        # Status ITM/OTM
        if tipo == 'call':
            itm = S > K
            status = f'ITM (+{round((S-K)/K*100,1)}%)' if itm else f'OTM ({round((S-K)/K*100,1)}%)'
        else:
            itm = S < K
            status = f'ITM ({round((K-S)/K*100,1)}%)' if itm else f'OTM (-{round((S-K)/K*100,1)}%)'

        return jsonify({
            'ticker': ticker,
            'preco_atual': round(S, 2),
            'strike': K,
            'tipo': tipo,
            't_days': T_days,
            'vol_impl_pct': round(sigma * 100, 2),
            'prob_exercicio_bs': prob_ex,
            'delta': round(delta, 4),
            'gamma': round(gamma, 6),
            'theta_dia': round(theta, 4),
            'vega': round(vega, 4),
            'd1': round(d1, 4),
            'd2': round(d2, 4),
            'itm': itm,
            'status': status,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── SERVE HTML ────────────────────────────────────
from flask import render_template
import hashlib

def _asset_version(filename):
    """
    Calcula um hash curto (8 chars) do conteudo do arquivo estatico, usado
    como query string de cache-busting (?v=hash). Diferente de timestamp,
    o hash so muda quando o CONTEUDO de fato muda — um restart do Render
    sem alteracao real no arquivo nao forca um novo download a toa.
    """
    import os as _os
    try:
        caminho = _os.path.join(app.static_folder, filename)
        with open(caminho, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except Exception:
        return str(int(time.time()))  # fallback: sempre busca de novo se der erro

@app.route('/')
@app.route('/painel-trader.html')
def serve_panel():
    resp = make_response(render_template(
        'index.html',
        v_js=_asset_version('app.js'),
        v_css=_asset_version('style.css'),
    ))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp



# ============================================================
# ETFs -- aba nova (backlog item 4, fechado sessao 02/07/2026)
# Universo Nacional (35) + Americano (26) = 61 fechado pelo usuario.
# Parsers calibrados com dado real via /etfs/debug e /etfs/debug-us
# (regex puro, sem bs4). Nacional e Americano tem ORDENS DE COLUNA
# DIFERENTES na tabela do Investidor10 -- ver docstrings.
# ============================================================
# ETF_UNIVERSO, _ETF_TICKERS_TODOS e todo o cluster de scraping/fetch
# de dados de ETF extraidos para fontes_etfs.py em 03/07/2026
# (Prioridade 2 da modularizacao, fase 2)
from fontes_etfs import (
    ETF_UNIVERSO, _ETF_TICKERS_TODOS, _parse_num_br, _extrair_linhas_tabela,
    _dy_plausivel, _scrape_investidor10_etfs_nacional,
    _scrape_investidor10_etfs_americano, _fetch_dy_yahoo,
    _fetch_etfs_dy_yahoo_bulk, _etf_yahoo_ticker, _fetch_yahoo_series,
    _fetch_preco_yahoo, _fetch_etfs_preco_yahoo_bulk,
)

# BUG CRITICO CORRIGIDO 04/07/2026: estas duas linhas foram apagadas sem
# querer durante o corte da Prioridade 2 fase 2 (extracao de fontes_etfs.py).
# Consequencia: _fetch_etfs_live() lancava NameError em TODA chamada, mas o
# erro ficava escondido pelo "except Exception: live = {}" da rota /etfs --
# por isso a watchlist inteira aparecia com "-", e nao era o investidor10
# nem o Yahoo estarem fora do ar como eu suspeitei antes. Reproduzi o 500
# de /etfs/live-status com o Flask test client de verdade e vi o
# NameError explicito -- so assim descobri.
# LICAO: boot test (importar o modulo + contar rotas) NAO basta; preciso
# tambem CHAMAR as rotas via app.test_client() antes de considerar uma
# extracao validada, nao so confirmar que o app sobe.
_cache_etfs_live = {'dados': None, 'ts': 0}
_ETF_CACHE_TTL = 900

_dy_refresh_em_andamento = {'flag': False}

# _refresh_dy_yahoo_background (so DY+preco) substituida por
# _refresh_completo_background (investidor10 paralelo + DY + preco) em
# 04/07/2026, ver docstring dela abaixo.

def _refresh_completo_background():
    """
    Atualiza TUDO em background (investidor10 nacional+americano em
    paralelo + Yahoo DY/preco) -- usado tanto pelo refresh periodico
    quanto pelo botao "Atualizar" (forcar=1). NUNCA roda no caminho da
    requisicao: correcao 04/07/2026 apos o botao Atualizar causar 502 de
    novo -- forcar=True ainda rodava o scrape do investidor10 de forma
    SINCRONA (5 paginas x 6s = ate 30s bloqueando o unico worker do
    Render). Agora forcar so dispara esta thread e devolve o cache atual
    na hora, nunca espera nada.
    """
    try:
        # CORRIGIDO 15/07/2026 (item 5.1, B1 -- parte 1 do plano registrado
        # em PROMPT_NOVA_SESSAO_v2.md): era ThreadPoolExecutor(max_workers=2)
        # + ex.shutdown(wait=False), mesmo padrao ja corrigido no A1
        # (_fetch_etfs_live). Como esta funcao INTEIRA ja roda numa thread
        # de background (disparada por _disparar_refresh_background, nunca
        # no caminho da requisicao), nao ha nenhuma razao pra manter o
        # paralelismo aqui -- sequencial nao atrasa resposta nenhuma pro
        # usuario, so faz o proprio ciclo de background demorar um pouco
        # mais (pior caso ~30s em vez de ~20s). Elimina de vez o risco de
        # threads orfas dessa parte especifica. B2/B3 (busca de DY/preco
        # via Yahoo, ~68 tickers, 25 threads cada) NAO seguem essa mesma
        # correcao -- avaliado e descartado nesta sessao a pedido do
        # Victor: sequencial ali tomaria minutos (68 tickers x ate 2 hosts),
        # atraso desproporcional ao ganho, e o disparo duplicado por
        # cliques repetidos ja e evitado pela trava
        # _dy_refresh_em_andamento['flag'] logo abaixo em
        # _disparar_refresh_background. Mantido como estava, de proposito.
        live_novo = {}
        try:
            live_novo.update(_scrape_investidor10_etfs_nacional(3))
        except Exception:
            pass
        try:
            live_novo.update(_scrape_investidor10_etfs_americano(2))
        except Exception:
            pass

        anterior = _cache_etfs_live.get('dados') or {}
        for ticker, d_ant in anterior.items():
            if ticker not in live_novo:
                live_novo[ticker] = d_ant
            else:
                if live_novo[ticker].get('preco') is None and d_ant.get('preco') is not None:
                    live_novo[ticker]['preco'] = d_ant['preco']
                if live_novo[ticker].get('dy') is None and d_ant.get('dy') is not None:
                    live_novo[ticker]['dy'] = d_ant['dy']
        if live_novo:
            _cache_etfs_live['dados'] = live_novo
            _cache_etfs_live['ts'] = time.time()

        dy_yahoo = _fetch_etfs_dy_yahoo_bulk(ETF_UNIVERSO)
        preco_yahoo = _fetch_etfs_preco_yahoo_bulk(ETF_UNIVERSO)
        dados = _cache_etfs_live.get('dados')
        if dados is not None:
            for ticker, dy in dy_yahoo.items():
                if ticker in dados:
                    if dados[ticker].get('dy') is None:
                        dados[ticker]['dy'] = dy
                else:
                    dados[ticker] = {'dy': dy}
            for ticker, preco in preco_yahoo.items():
                if ticker in dados:
                    if dados[ticker].get('preco') is None:
                        dados[ticker]['preco'] = preco
                else:
                    dados[ticker] = {'preco': preco}
    except Exception:
        pass
    finally:
        _dy_refresh_em_andamento['flag'] = False

def _disparar_refresh_background():
    if _dy_refresh_em_andamento['flag']:
        return
    _dy_refresh_em_andamento['flag'] = True
    try:
        import threading as _th
        _th.Thread(target=_refresh_completo_background, daemon=True).start()
    except Exception:
        _dy_refresh_em_andamento['flag'] = False

def _fetch_etfs_live(forcar=False):
    agora = time.time()
    tem_cache = _cache_etfs_live['dados'] is not None

    if not forcar and tem_cache and (agora - _cache_etfs_live['ts']) < _ETF_CACHE_TTL:
        return _cache_etfs_live['dados']

    if forcar and tem_cache:
        # NUNCA bloqueia: so dispara o refresh completo em background e
        # devolve o cache atual (levemente desatualizado, mas instantaneo)
        _disparar_refresh_background()
        return _cache_etfs_live['dados']

    # Cache frio (primeiro load desde o deploy, ou apos o processo dormir
    # no free tier do Render): faz o scrape SEQUENCIAL, nao paralelo.
    #
    # CORRIGIDO 15/07/2026 (item 5.1, Etapa 1 do plano registrado em
    # PROMPT_NOVA_SESSAO_v2.md): ate 15/07 este bloco usava
    # ThreadPoolExecutor(max_workers=2) + ex.shutdown(wait=False) -- o
    # MESMO padrao que ja causou o travamento total do site em 07/07/2026
    # (incidente do enriquecimento de KNCA11). O risco aqui: threads que
    # nao terminam a tempo continuam rodando OFF do caminho de resposta,
    # mas ainda consumindo o UNICO processo/worker do Render, competindo
    # com as proximas requisicoes. Como este bloco roda toda vez que o
    # cache expira OU o processo acorda depois de dormir por inatividade
    # (comum no free tier), a frequencia real e maior do que parece.
    #
    # Fix: chamadas sequenciais. Cada scraper ja tem timeout NATIVO por
    # pagina (requests.get(timeout=6) dentro de
    # _scrape_investidor10_etfs_nacional/americano, fontes_etfs.py) --
    # ou seja, nao precisa de ThreadPoolExecutor pra ter um limite de
    # tempo, o timeout de verdade ja existe por chamada HTTP individual.
    # Pior caso agora: 3 paginas nacional x 6s + 2 paginas americano x 6s
    # = ate 30s (era ~20s em paralelo). Mais lento no pior caso, mas SEM
    # thread orfa nenhuma -- o request termina, ponto final, nada fica
    # rodando depois. Frontend (loadETFs em app.js) nao tem timeout
    # proprio nessa chamada, entao nao ha risco de corte prematuro.
    live = {}
    try:
        live.update(_scrape_investidor10_etfs_nacional(3))
    except Exception:
        pass
    try:
        live.update(_scrape_investidor10_etfs_americano(2))
    except Exception:
        pass

    _cache_etfs_live['dados'] = live
    _cache_etfs_live['ts'] = agora
    _disparar_refresh_background()
    return live


# ── ROTAS DE ETFs (Prioridade 2, fase 5, 04/07/2026) ───
# Extraidas para rotas_etfs.py, ULTIMA fase da modularizacao. Registradas
# via funcao (mesmo padrao de rotas_fiis.py, fase 4) para evitar import
# circular -- ver docstring de rotas_etfs.py.
import rotas_etfs
rotas_etfs.registrar_rotas(
    app, _fetch_etfs_live, _cache_etfs_live, _dy_refresh_em_andamento,
    _github_get_file, _github_put_file, _github_criar_arquivo,
    _requer_auth_escrita, _fetch_closes_for_foto, _obter_preco_sigma_garch,
)




# _etf_yahoo_ticker e _fetch_yahoo_series ja importadas de fontes_etfs.py
# mais acima (Prioridade 2, fase 2, 03/07/2026)



if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
