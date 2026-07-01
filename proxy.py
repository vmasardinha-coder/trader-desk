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
from concurrent.futures import ThreadPoolExecutor  # adicionado 23/06/2026 -- /us/concentracao
from threading import Lock  # adicionado 23/06/2026 -- cache lazy do 8marketcap

try:
    import numpy as _np
    _NUMPY = True
except ImportError:
    _NUMPY = False

app = Flask(__name__)
_IND_CACHE = {}
_BTC_CACHE = {}   # cache BTC indicators e cycle
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

# ── SETORES ───────────────────────────────────────────
SETORES = {
    'PETR4.SA': {'nome':'Petroleo & Gas','pl_medio':6.0,'pvp_medio':1.5,'roe_min':15},
    'VALE3.SA':  {'nome':'Mineracao',    'pl_medio':7.0,'pvp_medio':1.8,'roe_min':15},
    'BBAS3.SA':  {'nome':'Bancos',       'pl_medio':8.0,'pvp_medio':1.2,'roe_min':18},
    'AXIA3.SA':  {'nome':'Energia Eletrica','pl_medio':12.0,'pvp_medio':1.2,'roe_min':10},
    'ROXO34.SA': {'nome':'Fintech/BDR',    'pl_medio':40.0,'pvp_medio':5.0,'roe_min':10},
    'DEFAULT':   {'nome':'Geral',        'pl_medio':12.0,'pvp_medio':2.0,'roe_min':12},
}

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
        r = requests.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.4389/dados/ultimos/1?formato=json', timeout=5)
        if r.ok:
            cdi_d = float(r.json()[0]['valor'])
            cdi_anual = ((1 + cdi_d/100)**252 - 1)*100
            if 5 <= cdi_anual <= 20:
                return round(cdi_anual, 2)
    except: pass
    return 14.25  # SELIC meta COPOM 17/06/2026 (proxima reuniao: 05/08/2026)

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
        ms=[]
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

# ── GARCH(1,1) ────────────────────────────────────────
def garch_11(closes, horizon_days=21):
    """
    Estima GARCH(1,1) via grid search (sem scipy) e projeta a volatilidade
    media esperada para os proximos `horizon_days`.

    GARCH(1,1): sigma2_t = omega + alpha*ret_{t-1}^2 + beta*sigma2_{t-1}

    Por que GARCH em vez de vol historica fixa (vol_hist):
    - vol_hist usa uma janela fixa de 21 dias com peso igual para cada dia
    - GARCH modela "clusters de volatilidade": dias turbulentos tendem a ser
      seguidos por dias turbulentos, e dias calmos por dias calmos (memoria)
    - O resultado e uma vol. que reflete melhor o regime atual do mercado,
      em vez de uma media simples do passado recente

    Retorna dict com vol_garch_atual (anualizada), vol_garch_projetada
    (media projetada para o horizonte) e os parametros estimados.
    """
    if not _NUMPY or len(closes) < 60:
        return None
    try:
        cl = _np.array(closes, dtype=float)
        rets = _np.diff(_np.log(cl)) * 100  # retornos em % para estabilidade numerica
        rets = rets[-252:]  # usa até 1 ano de retornos
        n = len(rets)
        if n < 50:
            return None

        var_uncond = _np.var(rets)
        if var_uncond <= 0:
            return None

        best = None
        # Grid search em alpha e beta (omega derivado da variancia incondicional)
        # alpha: peso do choque recente | beta: peso da variancia anterior (persistencia)
        for alpha in _np.arange(0.02, 0.20, 0.02):
            for beta in _np.arange(0.70, 0.97, 0.02):
                if alpha + beta >= 0.999:
                    continue
                omega = var_uncond * (1 - alpha - beta)
                if omega <= 0:
                    continue
                sigma2 = _np.empty(n)
                sigma2[0] = var_uncond
                loglik = 0.0
                valid = True
                for t in range(1, n):
                    sigma2[t] = omega + alpha * rets[t-1]**2 + beta * sigma2[t-1]
                    if sigma2[t] <= 0:
                        valid = False
                        break
                if not valid:
                    continue
                # Log-likelihood gaussiana (a menos de constante)
                ll = -0.5 * _np.sum(_np.log(sigma2[1:]) + (rets[1:]**2) / sigma2[1:])
                if best is None or ll > best[0]:
                    best = (ll, alpha, beta, omega, sigma2)

        if best is None:
            return None

        _, alpha, beta, omega, sigma2 = best
        sigma2_atual = sigma2[-1]

        # Projeta a variancia media para o horizonte (GARCH reverte a media de longo prazo)
        var_lp = omega / (1 - alpha - beta)  # variancia incondicional de longo prazo
        sigma2_h = sigma2_atual
        soma_var = 0.0
        for _h in range(horizon_days):
            soma_var += sigma2_h
            sigma2_h = omega + (alpha + beta) * sigma2_h
        var_media_horizonte = soma_var / horizon_days

        # Anualiza (retornos estavam em %, então divide por 100^2 antes de anualizar)
        vol_atual_anual = math.sqrt(sigma2_atual / 10000 * 252)
        vol_projetada_anual = math.sqrt(var_media_horizonte / 10000 * 252)
        vol_lp_anual = math.sqrt(var_lp / 10000 * 252)

        return {
            'vol_garch_atual_pct': round(vol_atual_anual * 100, 2),
            'vol_garch_projetada_pct': round(vol_projetada_anual * 100, 2),
            'vol_garch_longo_prazo_pct': round(vol_lp_anual * 100, 2),
            'alpha': round(float(alpha), 3),
            'beta': round(float(beta), 3),
            'persistencia': round(float(alpha + beta), 3),
            'horizon_days': horizon_days,
        }
    except Exception:
        return None

# ── ONCHAIN (estimativas) ────────────────────────────
def get_btc_onchain():
    try:
        r = requests.get('https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?interval=1d&range=1y',
            headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
        if r.ok:
            cl = [c for c in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
            if cl:
                price = cl[-1]
                ma200 = mm(cl, min(200, len(cl)))
                realized = ma200 * 0.82 if ma200 else price * 0.75
                mvrv = round((price - realized) / realized, 2) if realized else 1.2
                nupl = round(max(0, min(1, (price - realized) / price)), 2) if realized else 0.5
                puell = round(price / (ma200 * 1.1), 2) if ma200 else 1.5
                sopr = round(1 + mvrv * 0.1, 3)
                return {'mvrv_zscore': mvrv, 'nupl': nupl, 'puell_multiple': puell,
                        'sopr': sopr, 'realized_price': round(realized, 0), 'updated': 'estimado'}
    except: pass
    return {'mvrv_zscore': 1.2, 'nupl': 0.55, 'puell_multiple': 1.5,
            'sopr': 1.02, 'realized_price': 75000, 'updated': 'fallback'}

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
def yahoo_fundamentals(ticker, _debug=None):
    """
    Busca VPA, P/VP, DY, ROE via Yahoo quoteSummary — gratuito, sem token.
    Usado como fallback quando a brapi (plano free) nao traz esses campos
    (ela so libera priceEarnings/earningsPerShare no plano gratuito).
    """
    modules = 'defaultKeyStatistics,financialData,summaryDetail'
    erros = []
    for host in ['query1', 'query2']:
        try:
            r = requests.get(
                f'https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules={modules}',
                headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
            if not r.ok:
                erros.append(f'{host}: HTTP {r.status_code}')
                continue
            res = r.json().get('quoteSummary', {}).get('result')
            if not res:
                erros.append(f'{host}: sem result no JSON — {str(r.json())[:200]}')
                continue
            d = res[0]
            dks = d.get('defaultKeyStatistics', {})
            fd  = d.get('financialData', {})
            sd  = d.get('summaryDetail', {})
            def _raw(field_dict, key):
                v = field_dict.get(key)
                if isinstance(v, dict):
                    return v.get('raw')
                return v
            vpa = _raw(dks, 'bookValue')
            pvp = _raw(dks, 'priceToBook')
            roe = _raw(fd, 'returnOnEquity')
            dy  = _raw(sd, 'dividendYield')
            out = {}
            if vpa: out['vpa'] = vpa
            if pvp: out['pvp'] = pvp
            if roe: out['roe'] = roe
            if dy:  out['dy']  = dy
            if _debug is not None: _debug['erros'] = erros
            return out if out else None
        except Exception as _e:
            erros.append(f'{host}: exception {str(_e)}')
            continue
    if _debug is not None: _debug['erros'] = erros
    return None


def yquote(ticker):
    try:
        r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d',
            headers={'User-Agent':'Mozilla/5.0'},timeout=6)
        if not r.ok: return None
        d=r.json(); m=d['chart']['result'][0]['meta']
        cl=[c for c in d['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
        p=m.get('regularMarketPrice',cl[-1] if cl else None)
        if p is None: return None
        # CORRIGIDO 23/06/2026: usuario reportou variacoes implausiveis em
        # TODAS as commodities simultaneamente (~-11% num caso, prata real
        # naquele dia caiu ~4,5%) -- sinal de problema sistemico no campo
        # chartPreviousClose do Yahoo, nao de 1 ticker especifico. Esse
        # campo e calculado pelo proprio Yahoo e pode ficar desatualizado
        # para futuros com horario de pregao estendido (CME/COMEX/NYMEX,
        # usado por TODAS as commodities, diferente do horario fechado da
        # B3). Trocado para usar cl[-2] (penultimo fechamento da propria
        # serie diaria) como fonte PRIMARIA -- mesma serie ja usada para
        # cl[-1]/p e para vol_hist/GARCH em outras partes do app, mais
        # verificavel que um campo de metadado calculado pelo Yahoo.
        # chartPreviousClose fica so como fallback quando o historico nao
        # tem pontos suficientes (ticker muito novo ou erro de fonte).
        # NAO foi usada nenhuma heuristica de "escolher o valor mais
        # proximo do preco atual" -- isso mascararia movimentos REAIS de
        # mercado (como a queda real de ~4,5% da prata no caso relatado),
        # nao so os artificiais.
        v = cl[-2] if len(cl) > 1 else m.get('chartPreviousClose', p)
        return {'price':round(float(p),2),'prev':round(float(v),2)}
    except: return None

# Adicionado 25/06/2026 -- item 6 do backlog (Minerio de Ferro parecia
# "fixo" em Cotacoes). Causa raiz confirmada: TIO=F no Yahoo e um contrato
# de baixa liquidez sujeito a rollover de vencimento -- o sanity check
# (variacao >15% oculta o %) estava disparando quase todo dia, fazendo a
# variacao parecer congelada mesmo com o preco em si atualizando.
#
# HISTORICO DE TENTATIVAS (mais detalhe no PROMPT_NOVA_SESSAO_v2.md):
# 1. Investing.com -- DESCARTADA: pagina confirmada com "Delayed Data·11/05",
#    fonte parada ha >1 mes para esse contrato especifico.
# 2. Trading Economics (indice generico) -- funcional mas ~13 dias de
#    defasagem e NAO e o mesmo instrumento que o usuario acompanha de fato.
# 3. TradingView FEF1! (SGX IODEX Iron Ore Futures) -- usuario confirmou que
#    e EXATAMENTE o ticker que ele usa no proprio TradingView para decisao
#    (FEF1!/TIO1!, nao existe indice a vista acessivel para essa commodity).
#    Pagina publica tem FAQ estruturado: "The current price of SGX IODEX
#    Iron Ore Futures is X USD / TNE". Usado como fonte PRIMARIA agora.
#
# Trading Economics mantido como FALLBACK SECUNDARIO (mais estavel que
# Yahoo, mesmo que nao seja o ticker exato), e yquote('TIO=F') como ultimo
# fallback -- nunca quebra o endpoint /futures por completo.
def scrape_iron_ore_investing():
    """Fonte para Minerio de Ferro: TradingView FEF1! (SGX IODEX Iron Ore
    Futures) como primaria -- mesmo ticker que o usuario acompanha no
    proprio TradingView. Fallback: Trading Economics. Nome da funcao
    mantido por compatibilidade historica com o restante do codigo."""
    # PRIMARIA: TradingView FEF1!
    try:
        r = requests.get(
            'https://www.tradingview.com/symbols/SGX-FEF1!/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            timeout=8)
        if r.ok:
            html_limpo = re.sub(r'<[^>]+>', ' ', r.text)
            m = re.search(
                r'current\s+price\s+of\s+SGX\s+IODEX\s+Iron\s+Ore\s+Futures\s+is\s+([\d,]+\.?\d*)\s*USD\s*/\s*TNE',
                html_limpo, re.IGNORECASE)
            if m:
                price = float(m.group(1).replace(',', ''))
                if 20 <= price <= 500:
                    return {'price': round(price, 2), 'prev': round(price, 2), 'source': 'tradingview.com (FEF1!)'}
    except Exception:
        pass
    # FALLBACK SECUNDARIO: Trading Economics
    try:
        r2 = requests.get(
            'https://pt.tradingeconomics.com/commodity/iron-ore',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            timeout=8)
        if r2.ok:
            html_limpo2 = re.sub(r'<[^>]+>', ' ', r2.text)
            m_narrativo = re.search(r'minério\s+de\s+ferro\s+(?:subiu|caiu|manteve-se)\s+para\s+([\d.,]+)\s*USD\s*/\s*T', html_limpo2, re.IGNORECASE)
            m_tabela = re.search(r'Minério\s+De\s+Ferro\s*\|?\s*([\d.,]+)\s*\|', html_limpo2, re.IGNORECASE)
            m2 = m_narrativo or m_tabela
            if m2:
                raw = m2.group(1)
                if ',' in raw and '.' in raw:
                    raw = raw.replace('.', '').replace(',', '.')
                elif ',' in raw:
                    raw = raw.replace(',', '.')
                price2 = float(raw)
                if 20 <= price2 <= 500:
                    return {'price': round(price2, 2), 'prev': round(price2, 2), 'source': 'tradingeconomics.com'}
    except Exception:
        pass
    return None

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
    gold = yquote('GC%3DF')    # Ouro
    silver = yquote('SI%3DF')  # Prata
    copper = yquote('HG%3DF')  # Cobre
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
    dax = yquote('%5EGDAXI')      # Alemanha
    cac40 = yquote('%5EFCHI')     # Franca
    stoxx50 = yquote('%5ESTOXX50E')  # Zona do Euro
    ftse100 = yquote('%5EFTSE')   # Reino Unido
    nikkei = yquote('%5EN225')    # Japao
    hangseng = yquote('%5EHSI')   # Hong Kong
    sse = yquote('000001.SS')     # China (Shanghai)
    asx200 = yquote('%5EAXJO')    # Australia
    kospi = yquote('%5EKS11')     # Coreia do Sul

    return jsonify({'dji':dji,'esf':esf,'nqf':nqf,'win':win,'vix':vix,'dxy':dxy,'usd':usd,
                     'cl':cl,'gold':gold,'silver':silver,'copper':copper,
                     'dax':dax,'cac40':cac40,'stoxx50':stoxx50,'ftse100':ftse100,
                     'nikkei':nikkei,'hangseng':hangseng,'sse':sse,'asx200':asx200,'kospi':kospi,
                     'iron_ore':iron_ore,'brent':brent,'natgas':natgas})

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
        }

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
        if kdo is not None and kuo is not None:
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
            kdo_hit = min_p <= kdo
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
        if alavancagem is not None and teto_retorno_pct is not None and kdo is not None and kuo is not None:
            try:
                alavancagem = float(alavancagem)
                teto_retorno = float(teto_retorno_pct) / 100
                n_faixas = 20000
                z_full = np.random.standard_normal((n_faixas, prazo_dias))
                paths_full = preco_foto * np.exp(np.cumsum(drift_fan + vol_step_fan * z_full, axis=1))
                max_full = np.max(paths_full, axis=1)
                min_full = np.min(paths_full, axis=1)
                ST_full = paths_full[:, -1]
                tocou_baixa_full = min_full <= kdo
                tocou_alta_full = max_full >= kuo
                variacao_full = (ST_full / preco_foto - 1)
                retorno_full = np.where(tocou_baixa_full, 0.0,
                                  np.where(tocou_alta_full, teto_retorno,
                                  variacao_full * alavancagem))
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
        if kdo is not None and kuo is not None and dias_restantes > 0:
            n = 5000
            dt2 = 1/252.0
            drift2 = -0.5*sigma**2*dt2
            vol_step2 = sigma*math.sqrt(dt2)
            z2 = np.random.standard_normal((n, dias_restantes))
            paths = S*np.exp(np.cumsum(drift2+vol_step2*z2, axis=1))
            max_p = np.max(paths, axis=1); min_p = np.min(paths, axis=1)
            kuo_hit = max_p >= kuo; kdo_hit = min_p <= kdo
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

        if alavancagem is not None and teto_retorno_pct is not None and kdo is not None and kuo is not None:
            try:
                alavancagem = float(alavancagem)
                teto_retorno = float(teto_retorno_pct)/100
                n_faixas = 20000
                z_full = np.random.standard_normal((n_faixas, prazo_dias))
                paths_full = preco_entrada*np.exp(np.cumsum(drift_fan+vol_step_fan*z_full, axis=1))
                max_full = np.max(paths_full, axis=1); min_full = np.min(paths_full, axis=1)
                ST_full = paths_full[:,-1]
                tocou_baixa_full = min_full <= kdo; tocou_alta_full = max_full >= kuo
                variacao_full = (ST_full/preco_entrada - 1)
                retorno_full = np.where(tocou_baixa_full, 0.0,
                                  np.where(tocou_alta_full, teto_retorno, variacao_full*alavancagem))
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
            vol_defaults={'AXIA3':0.35,'ROXO34':0.45,'PETR4':0.30,'VALE3':0.32}
            sigma=vol_defaults.get(ticker.replace('.SA','').upper(),0.35)
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

        # Hardcoded fundamentais
        # Data de referencia dos fundamentais hardcoded (FUND_OVERRIDE).
        # Atualizar manualmente a cada revisao trimestral.
        FUND_DATA_REF = '2026-05-22'

        FUND_OVERRIDE = {
            # Originais (mantidos)
            'PETR4': {'pvp':1.65,'dy':6.42,'lpa':8.54,'vpa':29.76,'roe':22.5,'pl':5.8},
            'VALE3': {'pvp':1.93,'dy':6.70,'lpa':3.51,'vpa':43.07,'roe':8.2,'pl':23.64},
            'BBAS3': {'pvp':0.95,'dy':9.80,'lpa':4.20,'vpa':24.80,'roe':19.8,'pl':5.2},
            'AXIA3': {'pvp':1.30,'dy':5.30,'lpa':3.27,'vpa':41.55,'roe':7.9,'pl':16.50},
            'ROXO34':{'pvp':3.50,'dy':0.00,'lpa':0.45,'vpa':3.60,'roe':8.5,'pl':40.0},
            # Novos — dados Fundamentus, ref. 22/05/2026 (atualizar periodicamente)
            'ITUB4': {'pvp':2.18,'dy':8.70,'lpa':4.21,'vpa':18.12,'roe':23.2,'pl':9.36},
            'BBSE3': {'pvp':5.29,'dy':13.60,'lpa':4.73,'vpa':6.51,'roe':72.7,'pl':7.28},
            'CXSE3': {'pvp':3.81,'dy':7.50,'lpa':1.46,'vpa':4.59,'roe':31.9,'pl':11.94},
            'MULT3': {'pvp':2.35,'dy':3.70,'lpa':2.38,'vpa':12.62,'roe':18.9,'pl':12.42},
            'CYRE3': {'pvp':0.91,'dy':10.80,'lpa':4.33,'vpa':23.25,'roe':18.6,'pl':4.91},
            'DIRR3': {'pvp':3.13,'dy':17.30,'lpa':1.61,'vpa':4.09,'roe':39.41,'pl':7.96},
            'CMIN3': {'pvp':3.44,'dy':24.30,'lpa':0.41,'vpa':1.30,'roe':31.5,'pl':10.92},
            'GGBR4': {'pvp':0.90,'dy':2.90,'lpa':0.83,'vpa':26.58,'roe':3.1,'pl':29.07},
            'PSSA3': {'pvp':2.05,'dy':6.10,'lpa':5.70,'vpa':24.03,'roe':23.7,'pl':8.63},
            'SAPR11':{'pvp':1.45,'dy':5.20,'lpa':3.30,'vpa':26.16,'roe':12.6,'pl':11.49},
            'EUCA4': {'pvp':0.77,'dy':4.60,'lpa':4.42,'vpa':31.80,'roe':13.9,'pl':5.54},
            # Adicionado 23/06/2026 -- Fundamentus, dado coletado em 13/05/2026
            # (9 dias antes da FUND_DATA_REF global de 22/05/2026 -- diferenca
            # pequena, mantida sem ajustar a referencia global por 1 ativo)
            'PRIO3': {'pvp':2.14,'dy':0.00,'lpa':2.97,'vpa':30.52,'roe':9.7,'pl':22.05},
        }
        fundamentais_de_override = False
        if symbol in FUND_OVERRIDE:
            for k,v in FUND_OVERRIDE[symbol].items():
                if v is not None and not fund.get(k):
                    fund[k] = v
                    fundamentais_de_override = True

        SETOR_MAP = {
            'PETR4': {'nome':'Petroleo & Gas','pl_medio':6.0,'pvp_medio':1.5,'roe_min':15},
            'VALE3': {'nome':'Mineracao','pl_medio':7.0,'pvp_medio':1.8,'roe_min':15},
            'BBAS3': {'nome':'Bancos','pl_medio':8.0,'pvp_medio':1.2,'roe_min':18},
            'AXIA3': {'nome':'Energia Eletrica','pl_medio':12.0,'pvp_medio':1.2,'roe_min':10},
            'ROXO34':{'nome':'Fintech/BDR','pl_medio':40.0,'pvp_medio':5.0,'roe_min':10},
            'ITUB4': {'nome':'Bancos','pl_medio':8.0,'pvp_medio':1.5,'roe_min':18},
            'CYRE3': {'nome':'Construcao & Incorporacao','pl_medio':10.0,'pvp_medio':1.3,'roe_min':12},
            'DIRR3': {'nome':'Construcao & Incorporacao','pl_medio':10.0,'pvp_medio':1.5,'roe_min':15},
            'MULT3': {'nome':'Shoppings & Locacao','pl_medio':14.0,'pvp_medio':1.5,'roe_min':10},
            'PSSA3': {'nome':'Seguros','pl_medio':9.0,'pvp_medio':2.0,'roe_min':18},
            'BBSE3': {'nome':'Seguros','pl_medio':9.0,'pvp_medio':4.0,'roe_min':40},
            'CXSE3': {'nome':'Seguros','pl_medio':9.0,'pvp_medio':3.0,'roe_min':30},
            'CMIN3': {'nome':'Mineracao','pl_medio':7.0,'pvp_medio':1.8,'roe_min':15},
            'EUCA4': {'nome':'Papel & Celulose','pl_medio':10.0,'pvp_medio':1.0,'roe_min':10},
            'SAPR11':{'nome':'Saneamento','pl_medio':9.0,'pvp_medio':1.3,'roe_min':12},
            'GGBR4': {'nome':'Siderurgia','pl_medio':8.0,'pvp_medio':1.0,'roe_min':10},
            'PRIO3': {'nome':'Petroleo & Gas','pl_medio':6.0,'pvp_medio':1.5,'roe_min':15},
        }
        setor = SETOR_MAP.get(symbol, {'nome':'Geral','pl_medio':12.0,'pvp_medio':2.0,'roe_min':12})

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

        # FUNDAMENTAIS EXTRAS hardcoded (atualizar trimestralmente)
        FUND_EXTRA = {
            'PETR4': {'ev_ebitda':3.2,'debt_ebitda':0.8,'margem':18.3},
            'VALE3': {'ev_ebitda':4.1,'debt_ebitda':0.6,'margem':22.1},
            'BBAS3': {'ev_ebitda':None,'debt_ebitda':None,'margem':28.5},
            'AXIA3': {'ev_ebitda':7.5,'debt_ebitda':3.2,'margem':15.0},
            'ROXO34':{'ev_ebitda':None,'debt_ebitda':None,'margem':18.0},
        }
        extra = FUND_EXTRA.get(symbol, {})

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
# IMPORTANTE: Claude nao tem acesso de rede a 8marketcap.com no sandbox de
# desenvolvimento (dominio bloqueado) -- esta funcao foi escrita com base
# em inspecao do conteudo via ferramenta de busca/fetch (que retorna
# Markdown pre-processado, nao o HTML bruto), NAO testada diretamente
# contra o HTML real. Parsing usa regex tolerante (busca o padrao
# "SYMBOL ... $valorT/B" perto um do outro no texto) em vez de depender de
# estrutura exata de tags/classes, para ser mais resiliente a pequenas
# mudancas de layout -- mas pode precisar de ajuste se a estrutura real
# divergir do esperado. Cobertura conhecida: bom para large-caps
# (Semicondutores/m7/Software, todos no top ~100 por market cap).
# (Energia IA -- CEG/VST/TLN/D/OKLO -- foi tentado e depois REMOVIDO em
# 23/06/2026: utilities pequenas demais, fora do top 100, usuario decidiu
# nao vale o esforco.)
# Tickers cujo simbolo no 8marketcap.com difere do simbolo padrao do
# Yahoo/USSEG. Confirmado pelo usuario: GOOGL (classe A, com voto) so
# falhava porque o 8marketcap lista a Alphabet so como GOOG (classe C,
# sem voto) -- mesma empresa, simbolo diferente. BRK.B/BRK-B adicionado
# por precaucao (mesmo tipo de variacao de simbolo ja visto em
# _US_EXCHANGE para Berkshire).
_8MARKETCAP_TICKER_ALT = {
    'GOOGL': ['GOOG'],
    'BRK.B': ['BRK-B', 'BRK.A'],
    'BRK-B': ['BRK.B', 'BRK.A'],
}

def _parsear_marketcap_8marketcap(ticker, html_paginas):
    """Procura o marketCap de 1 ticker no HTML ja buscado (lista de
    strings, uma por pagina). Retorna valor em USD (float) ou None.
    Tenta o ticker original e, se nao achar, os simbolos alternativos
    conhecidos (ver _8MARKETCAP_TICKER_ALT) -- ex: GOOGL -> GOOG.

    CORRIGIDO 23/06/2026 (10a correcao): antes cada ticker fazia sua
    PROPRIA chamada de rede ao 8marketcap (e ate 4, com paginacao) --
    com N tickers em paralelo, isso multiplicava o numero de requisicoes
    (N x 4), reintroduzindo risco de timeout (mesmo problema da 4a
    correcao). Agora o HTML de todas as paginas e buscado UMA VEZ antes
    do loop paralelo (ver _buscar_html_8marketcap_paginas), e essa
    funcao so faz parsing em memoria, sem rede."""
    for candidato in [ticker] + _8MARKETCAP_TICKER_ALT.get(ticker, []):
        for html in html_paginas:
            padrao = re.compile(
                r'>' + re.escape(candidato) + r'<.{0,500}?\$([\d,]+\.?\d*)\s*([TB])',
                re.DOTALL)
            m = padrao.search(html)
            if m:
                valor = float(m.group(1).replace(',', ''))
                multiplicador = 1e12 if m.group(2) == 'T' else 1e9
                return valor * multiplicador
    return None


def _buscar_html_8marketcap_paginas(max_paginas=4):
    """Busca o HTML de N paginas de https://8marketcap.com/companies/ UMA
    VEZ (nao por ticker), para ser reaproveitado por todos os tickers do
    grupo. Retorna lista de strings HTML (uma por pagina que respondeu
    OK; paginas que falharem sao simplesmente omitidas da lista).

    AVISO: o padrao de URL de paginacao (?page=N apos /companies/) foi
    inferido a partir do padrao confirmado para o dominio raiz
    (8marketcap.com/?page=2, visto via busca), NAO testado diretamente
    contra /companies/?page=2 especificamente -- pode precisar de ajuste
    se o formato real divergir."""
    paginas = []
    for pagina in range(1, max_paginas + 1):
        try:
            url = 'https://8marketcap.com/companies/' if pagina == 1 else f'https://8marketcap.com/companies/?page={pagina}'
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if r.ok:
                paginas.append(r.text)
        except Exception:
            continue
    return paginas

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

    with ThreadPoolExecutor(max_workers=8) as executor:
        resultados = executor.map(_buscar_marketcap, tickers)
        for t, valor, erro in resultados:
            if valor is not None:
                detalhe[t] = valor
                soma_marketcap += valor
            else:
                erros_por_ticker[t] = erro

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
        # Evita duplicar se o ticker ja estiver ativo (protecao similar a
        # ja implementada para carteira_fiis.json)
        ja_existe = any(p.get('ticker') == ticker for p in dados_pos['ativas'])
        if ja_existe:
            return False, f"{ticker} ja existe em positions.json (ativas)"
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
                if resultado:
                    item['resultado'] = resultado
                    item['data_encerramento'] = _hoje_str()
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
#   com dividendo real cadastrado em FUND_OVERRIDE_GLOBAL):
#       colchao_vs_cdi = (dy_anual/12) - (cdi_anual/12)
#       score = (prob_meta/100) * retorno_mensal * peso_prazo
#               + (0.1 if colchao_vs_cdi > 0 else 0)
#   SE NAO (BDR/ADR/commodity sem dividendo -- ex. ROXO34/TSLA34/BSLV39/
#   AMZO34): score = (prob_meta/100) * retorno_mensal * peso_prazo, puro,
#   sem bonus de colchao (nao tem rede de seguranca de dividendo).
FUND_OVERRIDE_GLOBAL = {
    # Mesmos dados do FUND_OVERRIDE usado em /indicators (ref. Fundamentus,
    # ver FUND_DATA_REF la dentro -- duplicado aqui de proposito para nao
    # acoplar este endpoint a estrutura interna de outro endpoint.
    'PETR4': 6.42, 'VALE3': 6.70, 'BBAS3': 9.80, 'AXIA3': 5.30, 'ROXO34': 0.00,
    'ITUB4': 8.70, 'BBSE3': 13.60, 'CXSE3': 7.50, 'MULT3': 3.70, 'CYRE3': 10.80,
    'DIRR3': 17.30, 'CMIN3': 24.30, 'GGBR4': 2.90, 'PSSA3': 6.10,
    'SAPR11': 5.20, 'EUCA4': 4.60, 'PRIO3': 0.00,
    # Adicionado 25/06/2026 para o lote -- ALOS3 nao estava cadastrado em
    # nenhum lugar do app ainda. DY coletado via busca web (StatusInvest,
    # 25/06/2026): 10,27%.
    'ALOS3': 10.27,
}
# Tickers sem dividendo relevante (BDRs de empresas/ETFs sem distribuicao,
# ou commodities) -- mesmo se aparecessem com dy=0.0 cadastrado, marcar
# explicitamente como "sem DY" para nao confundir com dado ausente.
_SEM_DY_RELEVANTE = {'ROXO34', 'TSLA34', 'BSLV39', 'AMZO34', 'PRIO3'}

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
                elif tipo == 'bidirecional' and a.get('kdo') is not None and a.get('kuo') is not None and a.get('teto_retorno_pct') is not None:
                    ganho_pct = float(a['teto_retorno_pct'])
                    kdo = float(a['kdo']); kuo = float(a['kuo'])
                    tocou_alta = max_sim >= kuo
                    prob_meta = round(float(tocou_alta.mean()*100), 2)
                    # EV: 0 se tocou defesa, teto se tocou alta, variacao*alavancagem
                    # dentro do range (alavancagem default 1.0 se nao informada)
                    alav = float(a.get('alavancagem', 1.0))
                    tocou_baixa_full = min_full <= kdo
                    tocou_alta_full = max_full >= kuo
                    retorno_full_ev = np.where(tocou_baixa_full, 0.0,
                                       np.where(tocou_alta_full, ganho_pct/100,
                                       variacao_full*alav))
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

# ── FIIs (item 1 do backlog) ──────────────────────────
# Adicionado 25/06/2026. Fonte: Fundamentus (fii_resultado.php), tabela
# HTML publica, gratuita, sem token, ~390 FIIs de uma vez. Mesma logica
# de scraping de tabela ja usada com sucesso para fundamentais de acoes
# (FUND_OVERRIDE usa Fundamentus tambem, fonte ja confiavel no projeto).
#
# Criterio fechado com o usuario em 25/06/2026: P/VP (1o filtro) -> DY
# (2o filtro) -> Liquidez (3o filtro, risco operacional). Tipos em ordem
# de relevancia: papel > tijolo > FoF (usuario opera os tres).
#
# Mapeamento real de "Segmento" do Fundamentus (NAO e exatamente papel/
# tijolo/fof -- e o SETOR DE ATUACAO). Lista COMPLETA confirmada via teste
# real em produção (25/06/2026, 560 FIIs brutos retornados): "Títulos e
# Val. Mob." (~=papel/CRI), "Híbrido", "Multicategoria", "Lajes
# Corporativas", "Escritórios", "Shoppings", "Logística", "Residencial",
# "Varejo", "Hospital", "Hotel", "Outros". Mapeado para papel/tijolo/
# hibrido/outros (Fundamentus nao usa papel/tijolo/fof diretamente).
# CORRIGIDO 25/06/2026: mapeamento original (especificado antes do teste
# real) estava incompleto -- "Multicategoria" e outros caiam em "outros"
# por padrão sem terem sido analisados. Ajustado apos ver os segmentos
# reais retornados pelo endpoint.
# CORRIGIDO 25/06/2026 (segunda vez): usuario apontou que "outros"/
# "Multicategoria" tinham FIIs que claramente pertenciam a outras
# categorias. Investigacao via amostra real (segmento=1, todos os FIIs)
# confirmou: "Multicategoria" do Fundamentus e GENUINAMENTE misto -- alguns
# tem imoveis fisicos reais (tijolo/hibrido de verdade, ex: BTLG11/BLOG11/
# BPML11 com 30+ imoveis logisticos/shoppings), outros sao CRI/recebiveis/
# fundo-de-fundos puros (ex: AFHI11/ARRI11/CACR11/BBFO11/BCIA11, todos com
# qtd_imoveis=0) que o Fundamentus rotula como "Multicategoria" mesmo sem
# nenhum imovel fisico. O texto do segmento SOZINHO nao basta -- usa
# qtd_imoveis (sinal mais confiavel: zero imoveis = nao e tijolo de
# verdade) + palavras-chave do nome do fundo como segundo sinal.
_FII_SEGMENTO_BASE = {
    'Títulos e Val. Mob.': 'papel',
    'Híbrido': 'hibrido',
    'Multicategoria': 'hibrido',  # default, sera corrigido por qtd_imoveis/nome abaixo
    'Lajes Corporativas': 'tijolo',
    'Escritórios': 'tijolo',
    'Shoppings': 'tijolo',
    'Logística': 'tijolo',
    'Residencial': 'tijolo',
    'Varejo': 'tijolo',
    'Hospital': 'tijolo',
    'Hotel': 'tijolo',
    # ADICIONADO 25/06/2026: usuario notou VGIA11 e KNCA11 (ambos Fiagro
    # confirmado, CRA/agronegocio) ausentes do ranking. Nome exato do
    # segmento no Fundamentus para esses fundos nao confirmado com certeza
    # (pode ser "Fiagro" sem S -- nomenclatura "Fiagros" com S vista em
    # outras fontes pode ser proprietaria de cada agregador, nao do
    # Fundamentus). Adicionado ambas as grafias por seguranca, mapeadas
    # para 'papel' (Fiagro = essencialmente CRA, equivalente a CRI mas do
    # agro -- mesma natureza de fundo de papel).
    'Fiagro': 'papel',
    'Fiagros': 'papel',
    'Outros': 'outros',
}

# Palavras-chave que, no NOME do fundo, indicam fundo de papel (CRI/
# recebiveis/credito) mesmo quando o Fundamentus rotula como
# "Multicategoria" ou "Outros" -- confirmado via amostra real (ex: "AF
# INVEST CRI", "ALIANZA CREDITO IMOBILIARIO", "CARTESIA RECEBIVEIS").
_FII_PALAVRAS_PAPEL = ['CRI', 'RECEBÍVEIS', 'RECEBIVEIS', 'CRÉDITO', 'CREDITO',
                       'SECURITIES', 'CDI', 'CRA', 'FIAGRO']
# Palavras-chave que indicam fundo de fundos (compra cotas de outros FIIs,
# nao imoveis diretos) -- confirmado via amostra real (ex: "BB FUNDO DE
# FUNDOS", "BRADESCO CARTEIRA IMOBILIARIA ATIVA - FUNDO DE FUNDOS").
_FII_PALAVRAS_FOF = ['FUNDO DE FUNDOS', 'CARTEIRA IMOBILIARIA', 'CARTEIRA IMOBILIÁRIA']

def _classificar_segmento_fii(segmento_fundamentus, qtd_imoveis, nome_completo=''):
    """Reclassifica o segmento usando qtd_imoveis e nome do fundo como
    sinais adicionais, nao so o texto de Segmento do Fundamentus (que pode
    estar generico demais para Multicategoria/Outros). nome_completo vem
    do atributo title do link <a> na pagina (nome oficial do fundo) -- se
    nao disponivel no scraping atual, fallback para o mapeamento base."""
    base = _FII_SEGMENTO_MAP_BASE = _FII_SEGMENTO_BASE.get(segmento_fundamentus, 'outros')
    nome_upper = (nome_completo or '').upper()

    # So tenta reclassificar os segmentos ambiguos (Multicategoria/Outros/
    # Hibrido) -- segmentos especificos como Shoppings/Logistica/Escritorios
    # ja sao confiaveis o suficiente no texto original.
    if segmento_fundamentus in ('Multicategoria', 'Outros', 'Híbrido'):
        if any(p in nome_upper for p in _FII_PALAVRAS_FOF):
            return 'fof'
        if any(p in nome_upper for p in _FII_PALAVRAS_PAPEL):
            return 'papel'
        # CORRIGIDO 25/06/2026 (2a vez): tratar qtd_imoveis AUSENTE (None)
        # da mesma forma que ZERO -- ambos significam "sem imovel fisico
        # contabilizado", sinal forte de fundo de papel/CRI. Usuario
        # encontrou caso real (CPTS11, fundo de CRI puro, confirmado via
        # multiplas fontes externas) caindo em 'outros' -- provavel causa:
        # qtd_imoveis vinha como None (nao 0) para esse fundo na pagina do
        # Fundamentus, e a condicao anterior so tratava o caso ==0
        # explicitamente, deixando None cair no fallback errado.
        if qtd_imoveis is None or qtd_imoveis == 0:
            return 'papel'
        if qtd_imoveis > 0:
            # Tem imovel fisico de verdade -- mantem como hibrido (mistura
            # de tipos de imovel, que e o sentido original de "Multicategoria"
            # quando aplicado a um fundo de tijolo de verdade).
            return 'hibrido'
    return base

# ── Classificacao de NIVEL DE RISCO (camada 2, cruza com segmento) ──
# Adicionado 25/06/2026. Usuario pediu categorizacao por nivel de risco
# (nao so tipo de negocio) para balizar julgamento por notorio saber.
# Baseado em pesquisa de pratica de mercado real (classificacao High
# Grade / Middle Risk / High Yield, importada do mercado americano, usada
# por gestoras como Kinea/Empiricus/XP para FIIs e Fiagros).
#
# LIMITACAO HONESTA E DOCUMENTADA (usuario perguntou explicitamente sobre
# isso, confirmado via pesquisa em 25/06/2026): ALAVANCAGEM (divida/
# patrimonio) e CONCENTRACAO DE DEVEDORES/CRIs individuais NAO estao
# disponiveis gratuitamente em nenhuma fonte de screening em massa --
# so aparecem em relatorios gerenciais PDF de cada fundo individualmente,
# ou em plataformas pagas (Suno Analitica, Clube FII Research, Status
# Invest premium). Por isso esses dois fatores NAO entram na classificacao
# automatica abaixo -- ela e deliberadamente mais simples que uma analise
# completa, e serve como PONTO DE PARTIDA para o julgamento do usuario,
# nao veredito final. Se o usuario quiser refinar com alavancagem/
# concentracao no futuro, precisaria ser manual (relatorio por relatorio)
# ou um scraping mais pesado fundo-a-fundo, nao implementado agora.
#
# Regra (ajustada apos correcao do usuario sobre Fiagro -- NAO classificar
# automaticamente como High Yield so por ser agro, ja que depende da
# composicao da carteira, que nao temos dado para avaliar -- Fiagro cai
# em Middle Risk por padrao, sinalizando incerteza sem condenar):
_FII_PALAVRAS_DESENVOLVIMENTO = ['DESENVOLVIMENTO', 'INCORPORAÇÃO', 'INCORPORACAO',
                                  'URBANISMO', 'LOTEAMENTO']

def _classificar_risco_fii(nome_completo, segmento_fundamentus, dy_pct, vacancia_pct,
                             dy_mediana_segmento):
    """Classifica em high_grade / middle_risk / high_yield usando apenas
    dados gratuitos disponiveis (nome do fundo, segmento, DY relativo ao
    segmento, vacancia). NAO avalia alavancagem nem concentracao de
    devedores -- ver nota acima sobre limitacao de dados gratuitos."""
    nome_upper = (nome_completo or '').upper()

    # Sinal mais forte: fundo de DESENVOLVIMENTO (constroi e vende, nao
    # aluga -- risco de execucao real, ex: TGAR11) -- sempre High Yield.
    if any(p in nome_upper for p in _FII_PALAVRAS_DESENVOLVIMENTO):
        return 'high_yield'

    # Fiagro: DECISAO FINAL do usuario (25/06/2026, revertendo posicao
    # anterior) -- vai para High Yield por padrao. Raciocinio do usuario:
    # "a maioria e ruim, a minoria e boa, e como nao tenho como detectar
    # isso de forma gratuita, e mais facil deixar no High Yield e organizar
    # dentro dele o que esta menos ruim" -- nao e mais filtro de exclusao,
    # e ORGANIZACAO em listas para o usuario julgar com notorio saber.
    if 'FIAGRO' in nome_upper:
        return 'high_yield'

    # DY muito acima da mediana do PROPRIO segmento e sinal de premio de
    # risco alto sendo cobrado pelo mercado (mercado nao da DY alto de
    # graca -- ou ha risco real, ou e yield trap que o filtro de P/VP ja
    # deveria ter pego antes desta funcao rodar).
    if dy_mediana_segmento and dy_pct and dy_mediana_segmento > 0:
        razao = dy_pct / dy_mediana_segmento
        if razao > 1.5:
            return 'high_yield'

    # Vacancia alta (tijolo) e risco real de fluxo de caixa futuro.
    if vacancia_pct is not None and vacancia_pct > 20:
        return 'high_yield'

    # High Grade: DY proximo/abaixo da mediana do segmento (sem premio de
    # risco visivel) E vacancia baixa quando aplicavel.
    if dy_mediana_segmento and dy_pct and dy_mediana_segmento > 0:
        razao = dy_pct / dy_mediana_segmento
        if razao <= 1.1 and (vacancia_pct is None or vacancia_pct < 10):
            return 'high_grade'

    return 'middle_risk'

def _score_fii(p_vp, dy_pct, liquidez, ffo_yield_pct=None):
    """Sub-score para ORDENAR dentro de cada categoria de risco -- NAO e
    mais filtro de exclusao (decisao do usuario em 25/06/2026: 'nao e mais
    criterio de exclusao, e organizacao -- o que esta menos ruim primeiro').
    Logica do usuario: 'se o P/VP esta muito baixo, tem bode na historia
    normalmente, mas se tem liquidez boa, vale a pena considerar entrar' --
    ou seja, dentro do High Yield, o que importa e DY alto + liquidez boa
    apesar do P/VP baixo (sinal de risco aceito conscientemente), nao o
    P/VP baixo sozinho (que seria so 'desconto', sem indicar oportunidade
    real sem a liquidez para sustentar a tese).
    Formula simples e auditavel: score = DY * fator_liquidez, onde
    fator_liquidez penaliza liquidez muito baixa (dificil de operar).

    ADICIONADO 25/06/2026 -- fator de SUSTENTABILIDADE via FFO Yield vs DY.
    Usuario investigou o caso real VEGA11 (FFO Yield 11,12% vs DY 4,5%) e
    identificou que essa razao e um sinal de qualidade real: FFO > DY
    significa que o fundo gera mais caixa operacional do que distribui
    (sobra/margem de seguranca, sinal de qualidade); FFO < DY significa
    que o fundo "esta consumindo o proprio patrimonio para manter o
    dividendo, situacao insustentavel que eventualmente leva a corte"
    (fonte: pratica de mercado, confirmado via pesquisa). Usuario decidiu
    EXPLICITAMENTE que isso deve ser FATOR DE RANKING real, nao so coluna
    informativa.
    fator_ffo: BONUS se FFO Yield > DY (ate +30%), PENALIDADE se FFO Yield
    < DY (ate -30%), NEUTRO (1.0, sem efeito) se o dado nao existir --
    FFO Yield e um campo frequentemente vazio no Fundamentus, especialmente
    para fundos de papel/CRI puro (FFO e mais relevante para fundos de
    tijolo, com depreciacao de imoveis fisicos). Nao penalizar a AUSENCIA
    do dado, so usar quando disponivel."""
    if p_vp is None or dy_pct is None or liquidez is None:
        return 0.0
    fator_liquidez = min(liquidez / 500000, 1.5)  # normaliza ~mediana do mercado, cap em 1.5x

    fator_ffo = 1.0  # neutro por padrao -- sem dado, sem efeito no score
    if ffo_yield_pct is not None and dy_pct > 0:
        razao_ffo_dy = ffo_yield_pct / dy_pct
        # Limita o efeito a +-30% para nao deixar esse fator sozinho
        # dominar o score sobre DY/liquidez -- e um AJUSTE, nao o criterio
        # principal.
        fator_ffo = max(0.7, min(1.3, razao_ffo_dy))
    return round(dy_pct * fator_liquidez * fator_ffo, 3)

# Filtro de P/VP minimo contra "yield trap" -- fechado com o usuario em
# 25/06/2026 apos o primeiro teste real mostrar FIIs com P/VP muito baixo
# (0.15-0.19) e DY muito alto (19-23%) no topo do ranking (HCTR11, DEVA11,
# VSLH11 -- FIIs de papel/CRI com historico real de problemas de credito
# documentados no mercado). P/VP tao descontado normalmente reflete
# desconfianca do mercado sobre o valor patrimonial declarado, nao uma
# pechincha genuina -- usuario confirmou que quer esse filtro adicional.
_FII_PVP_MINIMO = 0.5

def scrape_fiis_fundamentus():
    """Scraping da tabela completa de FIIs do Fundamentus. Retorna lista de
    dicts (um por FII) ou None se o sanity check falhar (layout mudou,
    pagina vazia, etc -- NUNCA retorna dado parcial/suspeito sem avisar).

    NOTA TECNICA (25/06/2026): pagina do Fundamentus usa encoding
    ISO-8859-1 (Latin-1), confirmado via inspecao manual da pagina real
    (charset=iso-8859-1 no content-type). requests pode nao detectar isso
    corretamente sozinho -- forcamos r.encoding explicitamente antes de
    ler r.text, e usamos headers mais completos (simulando navegador real)
    para reduzir chance de bloqueio anti-bot, que e mais comum contra IPs
    de datacenter (Render) do que conexoes residenciais."""
    try:
        r = requests.get(
            'https://www.fundamentus.com.br/fii_resultado.php',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.fundamentus.com.br/index.php',
            },
            timeout=15)
        if not r.ok:
            return None, f'http_error_{r.status_code}'
        # Forca o encoding correto (pagina e ISO-8859-1, requests pode
        # detectar errado e corromper acentos, o que nao afeta o parsing
        # de numeros mas pode afetar match de texto como nome de Segmento)
        r.encoding = 'iso-8859-1'
        html = r.text

        # Extrai linhas da tabela via regex (sem BeautifulSoup, mesmo
        # padrao leve ja usado no resto do projeto). Cada linha <tr> tem
        # 13 <td>, primeiro com o ticker dentro de um <a>.
        linhas_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        fiis = []
        for linha in linhas_raw:
            celulas = re.findall(r'<td[^>]*>(.*?)</td>', linha, re.DOTALL)
            # CORRIGIDO 25/06/2026: pagina real tem 14 colunas (a 14a e
            # "Endereco", que nao existia na referencia de scraping de 2023
            # usada para montar a especificacao original -- causa raiz real
            # do "0 FIIs encontrados" no primeiro teste em produção). Aceita
            # 13 OU 14 para tolerar se o site remover/adicionar essa coluna
            # de novo no futuro sem quebrar o parsing.
            if len(celulas) not in (13, 14):
                continue
            # Limpa tags HTML internas (ex: <a href=...>MXRF11</a>) e espacos
            valores = [re.sub(r'<[^>]+>', '', c).strip() for c in celulas]
            ticker = valores[0]
            if not ticker or not re.match(r'^[A-Z0-9]+$', ticker):
                continue  # pula cabecalho ou linha invalida
            # Nome completo do fundo vem no atributo title do link <a> da
            # primeira celula (ex: title="AF INVEST CRI FUNDO DE..."),
            # usado como sinal adicional para reclassificar segmentos
            # ambiguos (ver _classificar_segmento_fii acima).
            m_title = re.search(r'title=["\']([^"\']+)["\']', celulas[0])
            nome_fundo = m_title.group(1) if m_title else ''
            try:
                def _pct(s):
                    s = s.replace('%', '').replace('.', '').replace(',', '.').strip()
                    return float(s) if s and s != '-' else None
                def _num(s):
                    s = s.replace('.', '').replace(',', '.').strip()
                    return float(s) if s and s != '-' else None
                qtd_imoveis_val = _num(valores[8])
                fiis.append({
                    'ticker': ticker,
                    'nome_fundo': nome_fundo,
                    'segmento_fundamentus': valores[1],
                    'segmento': _classificar_segmento_fii(valores[1], qtd_imoveis_val, nome_fundo),
                    'cotacao': _num(valores[2]),
                    'ffo_yield_pct': _pct(valores[3]),
                    'dy_pct': _pct(valores[4]),
                    'p_vp': _num(valores[5]),
                    'valor_mercado': _num(valores[6]),
                    'liquidez': _num(valores[7]),
                    'qtd_imoveis': qtd_imoveis_val,
                    'preco_m2': _num(valores[9]),
                    'aluguel_m2': _num(valores[10]),
                    'cap_rate_pct': _pct(valores[11]),
                    'vacancia_pct': _pct(valores[12]),
                    'endereco': valores[13] if len(valores) > 13 else None,
                })
            except (ValueError, IndexError):
                continue

        # ── Sanity checks (NUNCA aceitar dado suspeito sem avisar) ──
        if len(fiis) < 300:
            return None, f'poucos_fiis_encontrados ({len(fiis)}, esperado 300+)'
        p_vps_validos = [f['p_vp'] for f in fiis if f['p_vp'] is not None]
        if p_vps_validos:
            frac_fora_faixa = sum(1 for v in p_vps_validos if v < 0 or v > 5) / len(p_vps_validos)
            if frac_fora_faixa > 0.1:  # mais de 10% fora da faixa plausivel = layout suspeito
                return None, f'p_vp_fora_da_faixa ({frac_fora_faixa*100:.1f}% das linhas)'

        return fiis, None
    except Exception as e:
        return None, str(e)

@app.route('/fiis/buscar', methods=['GET'])
def buscar_fii():
    """
    Adicionado 25/06/2026 -- usuario nao conseguia achar visualmente
    alguns tickers seus (VGIA11, KNCA11) na lista filtrada de FIIs e
    pediu uma forma de CONSULTAR diretamente um ticker especifico, para
    julgar onde ele esta (universo bruto, descartado com motivo, ou
    classificado com nivel de risco). Roda o MESMO scraping (cache nao
    implementado ainda -- cada chamada busca de novo, aceitavel para uso
    individual esporadico de consulta).

    Query param obrigatorio: ticker (ex: ?ticker=VGIA11)
    Resposta sempre diz qual dos 3 estagios o ticker atingiu:
    - nao_encontrado: nao apareceu nem no scraping bruto (pode ser erro de
      parsing, ticker baixa liquidez extrema sem listagem, ou nome errado)
    - descartado: apareceu no bruto mas caiu no descarte inicial
      (liquidez/DY) -- mostra o motivo exato
    - classificado: passou o descarte, mostra segmento/risco/score
    """
    try:
        ticker_busca = (request.args.get('ticker') or '').strip().upper()
        if not ticker_busca:
            return jsonify({'error': 'parametro ticker obrigatorio (ex: ?ticker=VGIA11)'}), 422

        fiis, erro = scrape_fiis_fundamentus()
        if fiis is None:
            return jsonify({'error': f'Scraping falhou: {erro}'}), 502

        encontrado_bruto = next((f for f in fiis if f['ticker'] == ticker_busca), None)
        if not encontrado_bruto:
            return jsonify({
                'ticker': ticker_busca,
                'estagio': 'nao_encontrado',
                'mensagem': f'{ticker_busca} nao apareceu no scraping bruto do Fundamentus ({len(fiis)} FIIs totais). Verifique se o ticker esta correto, ou se o fundo pode ter sido deslistado/renomeado.',
            })

        liquidez_min = float(request.args.get('liquidez_min', 50000))
        motivo_descarte = None
        if encontrado_bruto['liquidez'] is None or encontrado_bruto['liquidez'] < liquidez_min:
            motivo_descarte = f"liquidez baixa (R${encontrado_bruto['liquidez']:,.0f}/dia)" if encontrado_bruto['liquidez'] is not None else 'liquidez ausente'
        elif encontrado_bruto['dy_pct'] is None or encontrado_bruto['dy_pct'] <= 0:
            motivo_descarte = 'DY zerado ou ausente'

        if motivo_descarte:
            return jsonify({
                'ticker': ticker_busca,
                'estagio': 'descartado',
                'motivo': motivo_descarte,
                'dados_brutos': encontrado_bruto,
            })

        nivel_risco = _classificar_risco_fii(
            encontrado_bruto.get('nome_fundo', ''), encontrado_bruto['segmento_fundamentus'],
            encontrado_bruto['dy_pct'], encontrado_bruto['vacancia_pct'], None)
        score = _score_fii(encontrado_bruto['p_vp'], encontrado_bruto['dy_pct'],
                            encontrado_bruto['liquidez'], encontrado_bruto.get('ffo_yield_pct'))
        return jsonify({
            'ticker': ticker_busca,
            'estagio': 'classificado',
            'nivel_risco': nivel_risco,
            'score': score,
            'dados': {**encontrado_bruto, 'nivel_risco': nivel_risco, 'score': score},
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/fiis', methods=['GET'])
def get_fiis():
    """
    Screening de FIIs via Fundamentus. Query params opcionais:
    - segmento: papel|tijolo|hibrido|outros (filtra por tipo)
    - liquidez_min: minimo de liquidez diaria em R$ (default 50000 --
      descarte inicial fechado com o usuario)

    Aplica DESCARTE INICIAL (liquidez minima, DY zerado, P/VP anomalo)
    antes de devolver a lista -- usuario confirmou que esses 3 criterios
    sao seguros para eliminar o que e operacionalmente inviavel ou
    claramente quebrado, sem aplicar julgamento de qualidade ainda (isso
    fica para o criterio fino P/VP->DY->Liquidez, feito no frontend/
    proxima iteracao).

    NUNCA filtra silenciosamente por causa de erro de scraping -- se o
    sanity check falhar, retorna erro explicito em vez de lista vazia.
    """
    try:
        liquidez_min = float(request.args.get('liquidez_min', 50000))
        segmento_filtro = request.args.get('segmento')
        risco_filtro = request.args.get('risco')

        fiis, erro = scrape_fiis_fundamentus()
        if fiis is None:
            return jsonify({
                'error': f'Scraping do Fundamentus falhou ou layout pode ter mudado: {erro}',
                'fiis': [],
            }), 502

        # Descarte inicial -- AJUSTADO 25/06/2026 (decisao final do
        # usuario): so descarta o que e OPERACIONALMENTE inviavel
        # (liquidez muito baixa) ou SEM RENDA (DY zerado/ausente -- fora
        # do objetivo declarado do usuario). P/VP NAO descarta mais --
        # virou criterio de CATEGORIZACAO de risco (ver abaixo), nao de
        # exclusao. Usuario quer ver TUDO, organizado por nivel de risco,
        # para julgar com proprio notorio saber.
        #
        # ADICIONADO 26/06/2026 -- estrutura "Todos" vs "Criterio": usuario
        # quer ver o universo BRUTO completo (560 FIIs) tambem, nao so os
        # que passam no descarte. Em vez de excluir os descartados da
        # resposta, agora eles SAO INCLUIDOS, mas marcados com
        # `fora_criterio=true` e SEM segmento/risco/score classificados
        # (usuario pediu explicitamente: "ele vai ficar vazio, nao recebe
        # classificacao nenhuma, so o nome"). O frontend decide mostrar
        # Todos (560, incluindo fora_criterio) ou Criterio (so os validos)
        # filtrando localmente -- evita 2 chamadas separadas ao backend
        # (scraping e pesado, ~560 linhas, nao vale duplicar o trabalho).
        descartados_motivos = []
        candidatos = []
        fora_criterio = []
        for f in fiis:
            motivo = None
            if f['liquidez'] is None or f['liquidez'] < liquidez_min:
                motivo = f'liquidez baixa (R${f["liquidez"]:,.0f}/dia)' if f['liquidez'] is not None else 'liquidez ausente'
            elif f['dy_pct'] is None or f['dy_pct'] <= 0:
                motivo = 'DY zerado ou ausente'

            if motivo:
                descartados_motivos.append({'ticker': f['ticker'], 'motivo': motivo})
                fora_criterio.append({
                    **f,
                    'fora_criterio': True,
                    'motivo_fora_criterio': motivo,
                    'segmento': None, 'nivel_risco': None, 'score': None,
                })
            else:
                f['fora_criterio'] = False
                candidatos.append(f)

        # Mediana de DY por SEGMENTO (necessaria para _classificar_risco_fii
        # detectar premio de risco relativo -- DY alto so e suspeito quando
        # muito acima da media do PROPRIO segmento, nao em termos absolutos)
        from statistics import median
        dy_por_segmento = {}
        for f in candidatos:
            dy_por_segmento.setdefault(f['segmento'], []).append(f['dy_pct'])
        mediana_dy_segmento = {seg: median(vals) for seg, vals in dy_por_segmento.items()}

        for f in candidatos:
            f['nivel_risco'] = _classificar_risco_fii(
                f.get('nome_fundo', ''), f['segmento_fundamentus'],
                f['dy_pct'], f['vacancia_pct'],
                mediana_dy_segmento.get(f['segmento']))
            f['score'] = _score_fii(f['p_vp'], f['dy_pct'], f['liquidez'], f.get('ffo_yield_pct'))

        if segmento_filtro:
            candidatos = [f for f in candidatos if f['segmento'] == segmento_filtro]
        if risco_filtro:
            candidatos = [f for f in candidatos if f['nivel_risco'] == risco_filtro]

        # Ordenacao: dentro de cada nivel de risco, por score (maior
        # primeiro) -- score pondera DY x liquidez, nao mais so P/VP cru.
        # Niveis de risco aparecem agrupados: high_grade -> middle_risk ->
        # high_yield, e dentro de cada um, por score.
        ordem_risco = {'high_grade': 0, 'middle_risk': 1, 'high_yield': 2}
        candidatos.sort(key=lambda f: (ordem_risco.get(f['nivel_risco'], 1), -f['score']))

        # Resposta final: 'fiis' = so os classificados (visao "Criterio",
        # comportamento ORIGINAL preservado para nao quebrar nada que ja
        # consome esse campo); 'fiis_todos' = classificados + fora_criterio
        # juntos (visao "Todos", 560 brutos) -- ordenado com os validos
        # primeiro, fora_criterio depois, ordenado por ticker dentro de
        # cada grupo para facilitar leitura/busca.
        fora_criterio.sort(key=lambda f: f['ticker'])
        fiis_todos = candidatos + fora_criterio

        # ADICIONADO 26/06/2026 -- integra FI-Infra (categoria
        # regulatoriamente separada de FII tradicional, NAO coberta pelo
        # Fundamentus, ver scrape_fi_infra) na MESMA resposta, como
        # segmento proprio 'fi-infra', para aparecer na busca/Todos da
        # aba FIIs sem precisar de tela separada (usuario confirmou
        # preferencia por integracao na mesma tela).
        #
        # DELIBERADAMENTE leve aqui: so confirma EXISTENCIA do ticker
        # (sem cotacao/DY/liquidez) -- buscar dados financeiros de cada
        # FI-Infra individualmente (22 requisicoes HTTP extras, ver
        # scrape_fi_infra_dados) tornaria ESTA chamada (que ja busca 560+
        # FIIs do Fundamentus) muito mais lenta. Dados financeiros
        # completos ficam EXCLUSIVOS do endpoint dedicado GET /fii-infra
        # (mais lento, mas isolado -- nao afeta a velocidade da tela
        # principal de FIIs).
        fii_infra_tickers, erro_fii_infra = scrape_fi_infra()
        if fii_infra_tickers:
            tickers_ja_presentes = {f['ticker'] for f in fiis_todos}
            for fi in fii_infra_tickers:
                if fi['ticker'] in tickers_ja_presentes:
                    continue  # evita duplicar se por acaso ja vier do Fundamentus
                fiis_todos.append({
                    'ticker': fi['ticker'],
                    'nome_fundo': fi['ticker'],
                    'segmento_fundamentus': 'Fundo de Infraestrutura (FI-Infra)',
                    'segmento': 'fi-infra',
                    'cotacao': None, 'ffo_yield_pct': None, 'dy_pct': None,
                    'p_vp': None, 'valor_mercado': None, 'liquidez': None,
                    'qtd_imoveis': None, 'preco_m2': None, 'aluguel_m2': None,
                    'cap_rate_pct': None, 'vacancia_pct': None, 'endereco': None,
                    'fora_criterio': False, 'sem_dados_financeiros': True,
                    'nivel_risco': None, 'score': None,
                })
        # erro_fii_infra (se houver) e silenciosamente ignorado aqui --
        # FI-Infra e um EXTRA na lista, nao o foco principal do endpoint;
        # se a fonte falhar, a lista de FII tradicional continua intacta
        # e completa, so sem os FI-Infra adicionados desta vez.

        return jsonify({
            'total_brutos': len(fiis),
            'total_descartados': len(descartados_motivos),
            'total_validos': len(candidatos),
            'descartados': descartados_motivos,
            'fiis': candidatos,
            'fiis_todos': fiis_todos,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
_CARTEIRA_FII_STATUS_VALIDOS = ['ativa', 'encerrada']

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
@app.route('/analises/ranking-fiis', methods=['GET'])
def ranking_fiis_em_analise():
    """
    Roda o MESMO criterio de classificacao/score da aba FIIs (/fiis), mas
    so para os tickers que estao em analises.json com tipo_estrutura='fii'
    e status='em_analise'. Resolve o pedido do usuario de ter um ranking
    proprio para FIIs em analise, separado do ranking de estruturadas
    (que usa Monte Carlo, nao se aplica a FII).
    """
    try:
        conteudo_str, _ = _github_get_file('analises.json')
        lista = json.loads(conteudo_str) if conteudo_str.strip() else []
        fiis_em_analise = [a for a in lista if a.get('status') == 'em_analise'
                           and a.get('tipo_estrutura') == 'fii']

        if not fiis_em_analise:
            return jsonify({'total_em_analise': 0, 'ranking': []})

        tickers_em_analise = {a['ticker'].replace('.SA', '').upper() for a in fiis_em_analise}

        fiis_brutos, erro = scrape_fiis_fundamentus()
        if fiis_brutos is None:
            return jsonify({'error': f'Scraping do Fundamentus falhou: {erro}', 'ranking': []}), 502

        # Filtra so os tickers que estao em analise (cruzamento)
        candidatos = [f for f in fiis_brutos if f['ticker'].upper() in tickers_em_analise]

        # Mapa de analise_id por ticker, para o frontend poder
        # aprovar/rejeitar direto da linha do ranking.
        analise_id_por_ticker = {a['ticker'].replace('.SA', '').upper(): a['id'] for a in fiis_em_analise}

        # Mesma logica de classificacao da aba FIIs (mediana de DY POR
        # SEGMENTO calculada so dentro deste subconjunto -- pode diferir
        # levemente da mediana do universo completo, mas e o subconjunto
        # relevante para o usuario decidir agora).
        from statistics import median
        dy_por_segmento = {}
        for f in candidatos:
            dy_por_segmento.setdefault(f['segmento'], []).append(f['dy_pct'])
        mediana_dy_segmento = {seg: median(vals) for seg, vals in dy_por_segmento.items() if vals}

        for f in candidatos:
            f['nivel_risco'] = _classificar_risco_fii(
                f.get('nome_fundo', ''), f['segmento_fundamentus'],
                f['dy_pct'], f['vacancia_pct'],
                mediana_dy_segmento.get(f['segmento']))
            f['score'] = _score_fii(f['p_vp'], f['dy_pct'], f['liquidez'], f.get('ffo_yield_pct'))
            f['analise_id'] = analise_id_por_ticker.get(f['ticker'].upper())

        ordem_risco = {'high_grade': 0, 'middle_risk': 1, 'high_yield': 2}
        candidatos.sort(key=lambda f: (ordem_risco.get(f.get('nivel_risco'), 1), -(f.get('score') or 0)))

        # Tickers em analise que NAO apareceram no scraping bruto (caso
        # raro, mas possivel -- ex: fundo deslistado entre a selecao e
        # agora) -- nunca esconder, mostrar com erro explicito.
        tickers_encontrados = {f['ticker'].upper() for f in candidatos}
        nao_encontrados = [t for t in tickers_em_analise if t not in tickers_encontrados]

        # ADICIONADO 30/06/2026 -- FI-Infra (BDIF11, etc.) NUNCA aparece no
        # Fundamentus (categoria regulatoria separada, ver /fii-infra),
        # entao sempre caia em nao_encontrados ate aqui. Para os tickers
        # que sobraram, tenta a fonte de FI-Infra (investidor10.com.br)
        # antes de desistir -- mesma classificacao de risco/score, com
        # mediana de DY AUTO-REFERENCIADA so entre os FI-Infra encontrados
        # nesta chamada (mesmo principio do endpoint /fii-infra).
        candidatos_fi_infra = []
        ainda_nao_encontrados = []
        for t in nao_encontrados:
            dados = scrape_fi_infra_dados(t)
            if dados and (dados.get('cotacao') is not None or dados.get('dy_pct') is not None):
                candidatos_fi_infra.append({
                    'ticker': t,
                    'nome_fundo': t,
                    'segmento_fundamentus': 'Fundo de Infraestrutura (FI-Infra)',
                    'segmento': 'fi-infra',
                    'cotacao': dados.get('cotacao'),
                    'p_vp': dados.get('p_vp'),
                    'dy_pct': dados.get('dy_pct'),
                    'liquidez': dados.get('liquidez'),
                    'vacancia_pct': None,
                    'ffo_yield_pct': None,
                    'analise_id': analise_id_por_ticker.get(t),
                })
            else:
                ainda_nao_encontrados.append(t)

        if candidatos_fi_infra:
            dy_validos_fi = [f['dy_pct'] for f in candidatos_fi_infra if f['dy_pct'] is not None]
            mediana_dy_fi = median(dy_validos_fi) if dy_validos_fi else None
            for f in candidatos_fi_infra:
                if f['liquidez'] is None or f['dy_pct'] is None or f['dy_pct'] <= 0:
                    f['nivel_risco'] = None
                    f['score'] = None
                else:
                    f['nivel_risco'] = _classificar_risco_fii(
                        f['nome_fundo'], f['segmento_fundamentus'], f['dy_pct'], None, mediana_dy_fi)
                    f['score'] = _score_fii(f.get('p_vp'), f['dy_pct'], f['liquidez'])
            candidatos.extend(candidatos_fi_infra)
            candidatos.sort(key=lambda f: (ordem_risco.get(f.get('nivel_risco'), 1), -(f.get('score') or 0)))

        return jsonify({
            'total_em_analise': len(fiis_em_analise),
            'total_encontrados': len(candidatos),
            'nao_encontrados': ainda_nao_encontrados,
            'ranking': candidatos,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carteira-fiis', methods=['GET'])
def get_carteira_fiis():
    """Le carteira_fiis.json do repo. Sempre retorna lista (vazia se nao
    houver nenhum FII ativado ainda)."""
    try:
        conteudo_str, _ = _github_get_file('carteira_fiis.json')
        carteira = json.loads(conteudo_str) if conteudo_str.strip() else []
        return jsonify({'carteira': carteira, 'total': len(carteira)})
    except RuntimeError as e:
        return jsonify({'error': str(e), 'carteira': []}), 500
    except Exception as e:
        return jsonify({'error': str(e), 'carteira': []}), 500

@app.route('/carteira-fiis', methods=['POST'])
@_requer_auth_escrita
def ativar_fii_carteira():
    """
    Ativa um FII na carteira (migra de Em Analise para Ativa de fato).
    Espera no body: ticker, nome_fundo, segmento, nivel_risco, preco_foto
    (preco no momento da ativacao), dy_anual_pct, analise_id (opcional --
    id da analise em analises.json que esta sendo migrada, para remove-la
    de la apos a ativacao bem sucedida aqui).
    """
    try:
        body = request.get_json() or {}
        campos_obrig = ['ticker', 'nome_fundo', 'segmento', 'preco_foto']
        faltando = [c for c in campos_obrig if not body.get(c)]
        if faltando:
            return jsonify({'error': f'campos obrigatorios faltando: {faltando}'}), 422

        conteudo_str, sha = _github_get_file('carteira_fiis.json')
        carteira = json.loads(conteudo_str) if conteudo_str.strip() else []

        # CORRIGIDO 26/06/2026 -- usuario clicou no mesmo FII (CLIN11) duas
        # vezes (provavelmente clique duplo rapido, sem feedback visual
        # suficiente de que a 1a chamada ja estava em andamento -- corrigido
        # tambem no frontend com desabilitar o botao). Esta checagem e a
        # ULTIMA LINHA DE DEFESA no backend: se o ticker ja estiver ATIVO na
        # carteira, recusa em vez de duplicar silenciosamente.
        ja_ativo = next((f for f in carteira if f['ticker'] == body['ticker'] and f.get('status') == 'ativa'), None)
        if ja_ativo:
            return jsonify({'error': f"{body['ticker']} já está ativo na carteira (id={ja_ativo['id']}, desde {ja_ativo['data_ativacao']})"}), 409

        import time as _time
        novo = {
            'id': f"fii_{int(_time.time())}",
            'ticker': body['ticker'],
            'nome_fundo': body['nome_fundo'],
            'segmento': body['segmento'],
            'nivel_risco': body.get('nivel_risco'),
            'data_ativacao': _hoje_str(),
            'preco_ativacao': float(body['preco_foto']),
            'dy_anual_pct_ativacao': body.get('dy_anual_pct'),
            'status': 'ativa',
        }
        carteira.append(novo)
        novo_conteudo = json.dumps(carteira, indent=2, ensure_ascii=False)
        _github_put_file('carteira_fiis.json', novo_conteudo, sha,
            f"feat: ativa {novo['ticker']} na carteira de FIIs via app")

        # Remove de analises.json se vier o id de origem (migracao completa,
        # sem duplicar -- mesmo principio ja especificado para a migracao
        # de estruturadas Em Analise -> Ativa).
        analise_id_origem = body.get('analise_id')
        if analise_id_origem:
            try:
                conteudo_an, sha_an = _github_get_file('analises.json')
                lista_an = json.loads(conteudo_an) if conteudo_an.strip() else []
                lista_an_filtrada = [a for a in lista_an if a.get('id') != analise_id_origem]
                if len(lista_an_filtrada) != len(lista_an):
                    novo_conteudo_an = json.dumps(lista_an_filtrada, indent=2, ensure_ascii=False)
                    _github_put_file('analises.json', novo_conteudo_an, sha_an,
                        f"feat: remove {analise_id_origem} de analises.json (migrado para carteira_fiis.json)")
            except Exception:
                pass  # nao falha a ativacao principal se a limpeza falhar

        return jsonify(novo), 201
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carteira-fiis/<fii_id>/status', methods=['PUT'])
@_requer_auth_escrita
def mudar_status_carteira_fii(fii_id):
    """Move um FII da carteira para 'encerrada' (vendido). Espera
    {'status': 'encerrada'} no body."""
    try:
        body = request.get_json() or {}
        novo_status = body.get('status')
        if novo_status not in _CARTEIRA_FII_STATUS_VALIDOS:
            return jsonify({'error': f'status invalido: {novo_status!r}'}), 422

        conteudo_str, sha = _github_get_file('carteira_fiis.json')
        carteira = json.loads(conteudo_str) if conteudo_str.strip() else []
        encontrado = False
        for item in carteira:
            if item.get('id') == fii_id:
                item['status'] = novo_status
                if novo_status == 'encerrada':
                    item['data_encerramento'] = _hoje_str()
                encontrado = True
                break
        if not encontrado:
            return jsonify({'error': f'FII {fii_id} nao encontrado na carteira'}), 404

        novo_conteudo = json.dumps(carteira, indent=2, ensure_ascii=False)
        _github_put_file('carteira_fiis.json', novo_conteudo, sha,
            f"feat: FII {fii_id} -> status={novo_status} via app")
        return jsonify({'id': fii_id, 'status': novo_status})
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── FI-Infra (Fundos de Investimento em Infraestrutura) ────
# Adicionado 26/06/2026. Usuario percebeu que CDII11 (e outros FI-Infra)
# nunca apareciam na busca/listagem de FIIs -- investigacao confirmou:
# FI-Infra e categoria REGULATORIAMENTE SEPARADA de FII tradicional
# (mesma raiz legal -- condominio fechado, isencao de IR -- mas registro
# proprio na B3/CVM). O Fundamentus (fonte usada para FIIs tradicionais)
# NAO lista FI-Infra. Fonte alternativa encontrada: Investidor10
# (investidor10.com.br/fiis/segmento/fi-infra/), que lista os FI-Infra
# DENTRO da mesma estrutura de navegacao de FIIs do site (~22 fundos
# confirmados via inspecao manual em 26/06/2026, incluindo CDII11).
#
# RISCO DOCUMENTADO: pagina pode renderizar via JS (React), e um simples
# requests.get() pode nao capturar o HTML completo -- mesma ressalva ja
# dada para outras fontes nesta sessao. Sanity check rigoroso abaixo;
# se falhar, retorna erro explicito (nunca dado parcial/inventado).
_FII_INFRA_TIPO_MAP = {
    'Outro': 'outro',
    'Fundo de Papel': 'papel',
    'Fundo Misto': 'misto',
    'Fundo de Desenvolvimento': 'desenvolvimento',
}

def scrape_fi_infra():
    """
    Scraping de FI-Infra via fiis.com.br/lista-de-fundos-imobiliarios/.

    HISTORICO (26/06/2026): 1a tentativa (Investidor10) deu erro 500
    (catastrophic backtracking de regex). 2a tentativa (fiis.com.br, regex
    dependente do texto "Fi-infra:" estar proximo do link) deu 0 matches
    em producao -- a estrutura HTML real (tags/atributos) e diferente do
    que o web_fetch mostra (que ja vem processado/markdown), e adivinhar
    a estrutura exata sem poder testar contra o HTML bruto real (site
    bloqueado no sandbox de desenvolvimento) se mostrou fragil demais.

    3a TENTATIVA (atual): abordagem mais ROBUSTA, em duas camadas:
    1. Tenta o padrao mais simples possivel -- so o link href="/<ticker>/"
       seguido do texto do ticker, SEM depender de "Fi-infra:" estar logo
       antes (que pode ter mais tags/espacos entre eles do que esperado).
    2. Fallback: BUSCA DE STRING SIMPLES (nao regex) pelos tickers de
       FI-Infra JA CONHECIDOS (confirmados via multiplas fontes externas
       nesta sessao: Investidor10, fiis.com.br via web_fetch, Toro, Nord).
       Se o ticker aparecer em QUALQUER lugar do HTML da pagina (com ou
       sem tag ao redor), confirma a existencia dele -- muito mais robusto
       contra mudanca de estrutura HTML do que tentar parsear o padrao
       exato de marcacao da categoria.
    """
    # Lista de FI-Infra confirmados via pesquisa externa em 26/06/2026
    # (Investidor10 + fiis.com.br via web_fetch + Toro + Nord Research).
    # Usada como FALLBACK de busca simples se o parsing por regex falhar --
    # nao e dado "inventado", e dado real confirmado por multiplas fontes
    # independentes, so usado de forma mais robusta (busca de substring)
    # em vez de parsing fragil de estrutura HTML.
    TICKERS_FI_INFRA_CONHECIDOS = [
        'BDIF11', 'BIDB11', 'BINC11', 'BODB11', 'BRZD11', 'CDII11', 'CPTI11',
        'IFRA11', 'IFRI11', 'INFA11', 'INFB11', 'IRIF11', 'JMBI11', 'JURO11',
        'KDIF11', 'NUIF11', 'OGIN11', 'RBIF11', 'RIFF11', 'SNID11', 'VANG11', 'XPID11',
    ]
    try:
        r = requests.get(
            'https://fiis.com.br/lista-de-fundos-imobiliarios/',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'pt-BR,pt;q=0.9',
            },
            timeout=15)
        if not r.ok:
            return None, f'http_error_{r.status_code}'
        html = r.text
        html_upper = html.upper()

        # Camada 1: regex simples, so o link (sem depender de "Fi-infra:")
        fundos = []
        tickers_vistos = set()
        for m in re.finditer(r'href="/([a-z0-9]{4,7})/"[^>]{0,150}>\s*([A-Z0-9]{4,7})\s*<', html, re.IGNORECASE):
            ticker = (m.group(2) or m.group(1)).upper()
            if ticker in tickers_vistos or ticker not in TICKERS_FI_INFRA_CONHECIDOS:
                continue
            tickers_vistos.add(ticker)
            fundos.append({'ticker': ticker, 'nome_fundo': ticker, 'fonte_match': 'regex'})

        # Camada 2 (fallback): busca de substring simples para os tickers
        # conhecidos que a Camada 1 NAO encontrou -- protege contra
        # mudanca de estrutura HTML que o regex nao previu.
        for ticker in TICKERS_FI_INFRA_CONHECIDOS:
            if ticker in tickers_vistos:
                continue
            if ticker in html_upper:
                tickers_vistos.add(ticker)
                fundos.append({'ticker': ticker, 'nome_fundo': ticker, 'fonte_match': 'substring'})

        if len(fundos) < 10:
            return None, f'poucos_fundos_encontrados ({len(fundos)} de {len(TICKERS_FI_INFRA_CONHECIDOS)} conhecidos, esperado 10+)'

        return fundos, None
    except Exception as e:
        return None, str(e)

# Adicionado 26/06/2026 -- busca dados financeiros (cotacao, DY, liquidez)
# da pagina INDIVIDUAL de cada FI-Infra (ex: fiis.com.br/cdii11/), ja que
# a listagem em massa nao traz esses dados. Confirmado via inspecao manual
# que a pagina individual TEM dados reais (CDII11: DY=16.77%,
# cotacao=R$104.36, liquidez=R$5.1M/dia), mas com RESSALVA IMPORTANTE:
# alguns campos vem com "0,00" ou "-" que sao NA disfarcado, nao zero real
# (ex: P/VP="0,00", Patrimonio Liquido="-" no mesmo CDII11) -- esses campos
# sao tratados como ausentes (None), nunca usados como zero literal.
def scrape_fi_infra_dados(ticker, debug=False):
    """Busca dados financeiros da pagina individual de um FI-Infra.
    FONTE TROCADA 29/06/2026: fiis.com.br abandonado -- confirmado via
    modo debug que os numeros visiveis (DY/cotacao/liquidez) NAO existem
    como texto no HTML bruto recebido por requests.get() (provavelmente
    renderizados via JS/componente apos hidratacao) -- a primeira
    ocorrencia de "Dividend Yield" no HTML bruto era inclusive um texto
    de ajuda/tooltip serializado (PHP serialize, 's:165:...'), que ja
    tinha causado o bug antigo do "165%".

    Nova fonte: investidor10.com.br/fiis/<ticker>/ -- usa a secao
    "Duvidas comuns" (FAQ), que e texto SEO server-side renderizado, com
    padrao estavel tipo:
      "A cotação hoje de BDIF11 é de R$ 76,10, com uma variação..."
      "...distribuiu um total de R$ 9,70 por cota... O Dividend Yield
       no período foi de 12,75%."
    Mais robusto que widgets de dashboard (que podem ser JS-only).

    Retorna dict ou None se falhar/dado insuficiente. NUNCA inventa
    numero. Se debug=True, em caso de falha retorna {'_debug': {...}}
    com status_code/contexto do HTML, em vez de None puro -- usado pelo
    endpoint /fii-infra?debug=1 para diagnostico."""
    try:
        r = requests.get(
            f'https://investidor10.com.br/fiis/{ticker.lower()}/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
            timeout=10)
        if not r.ok:
            if debug:
                return {'_debug': {'status_code': r.status_code, 'snippet': r.text[:500]}}
            return None
        html = r.text

        # CORRIGIDO: o HTML real usa tags (<strong>/<b>/etc), nao markdown
        # (**texto**) -- a primeira tentativa desta funcao foi escrita
        # contra a versao markdown que a ferramenta de leitura mostra,
        # nao contra o HTML bruto real. Solucao robusta: remover TODAS
        # as tags HTML antes de rodar os regex, trabalhando so com texto
        # puro -- assim funciona independente de qual tag for usada.
        texto = re.sub(r'<[^>]+>', ' ', html)
        texto = re.sub(r'\s+', ' ', texto)  # colapsa espacos/quebras de linha

        # Cotacao: "A cotação hoje de TICKER é de R$ NUMERO"
        m_cot = re.search(
            r'cota[çc][ãa]o hoje de\s*' + re.escape(ticker) + r'\s*[ée]\s*de\s*R\$\s*([\d.]+,\d+)',
            texto, re.IGNORECASE)
        cotacao = None
        if m_cot:
            try:
                val = float(m_cot.group(1).replace('.', '').replace(',', '.'))
                cotacao = val if val > 0 else None
            except ValueError:
                pass

        # DY: "O Dividend Yield no período foi de NUMERO%"
        m_dy = re.search(
            r'Dividend Yield no per[íi]odo foi de\s*([\d.]+,\d+)\s*%',
            texto, re.IGNORECASE)
        dy_pct = None
        if m_dy:
            try:
                val = float(m_dy.group(1).replace('.', '').replace(',', '.'))
                dy_pct = val if val > 0 else None
            except ValueError:
                pass

        # Liquidez: widget do topo "Liquidez Diária R$ NUMERO M"
        liquidez = None
        m_liq = re.search(
            r'Liquidez Di[áa]ria\s*R\$\s*([\d.,]+)\s*(M|K|B|Mil|Milh[õo]es|Bilh[õo]es)?',
            texto, re.IGNORECASE)
        if m_liq:
            raw_liq, unidade = m_liq.group(1), (m_liq.group(2) or '')
            raw_liq = raw_liq.replace('.', '').replace(',', '.')
            try:
                liquidez = float(raw_liq)
                unidade = unidade.upper()
                if unidade in ('M', 'MILH', 'MILHÕES', 'MILHOES'):
                    liquidez *= 1_000_000
                elif unidade in ('B', 'BILH', 'BILHÕES', 'BILHOES'):
                    liquidez *= 1_000_000_000
                elif unidade in ('K', 'MIL'):
                    liquidez *= 1_000
            except ValueError:
                liquidez = None

        # P/VP: ADICIONADO 29/06/2026 -- padrao estavel da FAQ
        # "Hoje, o fundo tem um patrimônio de R$ X e P/VP de NUMERO,"
        p_vp = None
        m_pvp = re.search(r'e P/VP de\s*([\d]+,\d+)', texto, re.IGNORECASE)
        if m_pvp:
            try:
                val = float(m_pvp.group(1).replace(',', '.'))
                p_vp = val if val > 0 else None
            except ValueError:
                pass

        if dy_pct is None and cotacao is None:
            if debug:
                idx_dy_raw = texto.lower().find('dividend yield')
                idx_cot_raw = texto.lower().find('cotação hoje')
                ctx_dy = texto[max(0,idx_dy_raw-100):idx_dy_raw+150] if idx_dy_raw != -1 else 'TEXTO "dividend yield" NAO ENCONTRADO'
                ctx_cot = texto[max(0,idx_cot_raw-50):idx_cot_raw+200] if idx_cot_raw != -1 else 'TEXTO "cotação hoje" NAO ENCONTRADO'
                return {'_debug': {
                    'status_code': r.status_code,
                    'html_len': len(html),
                    'texto_len': len(texto),
                    'contexto_dy': ctx_dy,
                    'contexto_cotacao': ctx_cot,
                }}
            return None  # nada de util encontrado -- nao retorna dado parcial sem sentido

        return {'ticker': ticker, 'dy_pct': dy_pct, 'cotacao': cotacao, 'liquidez': liquidez, 'p_vp': p_vp}
    except Exception as e:
        if debug:
            return {'_debug': {'exception': str(e)}}
        return None

def scrape_statusinvest_ultimo_provento(ticker, segmento=None):
    """
    Busca o ULTIMO provento/rendimento pago de um FII ou FI-Infra via
    statusinvest.com.br -- adicionado 30/06/2026, fonte confirmada
    server-side renderizada (texto puro, sem JS, sem bloqueio).

    URL difere por categoria: FI-Infra usa /fiinfras/, FII tradicional
    usa /fundos-imobiliarios/ -- se 'segmento' nao for passado, tenta
    fundos-imobiliarios primeiro (mais comum) e cai para fiinfras se
    404.

    CORRIGIDO 30/06/2026 (2a tentativa): o HTML real tem DUAS ocorrencias
    do texto "ultimo provento" -- a PRIMEIRA e so o label de um widget
    Vue/JS nao renderizado (literal "{ultimoProvento_F}" no HTML bruto,
    placeholder nunca substituido por requests.get()); a SEGUNDA, mais
    adiante, e a frase SEO completa de verdade ("O ultimo provento pago
    do BDIF11 foi um rendimento de R$0,8500..."), mas com o acento "u"
    codificado como entidade HTML (&#xFA;) em vez de "u" literal --
    re.sub de tags nao decodifica entidades, entao precisa de
    html.unescape() ANTES do regex, ou o "u" da entidade nunca bate com
    o "[uu]" do padrao. Por isso a 1a versao desta funcao retornava
    sempre None em producao mesmo com o padrao certo.

    NAO e historico completo mes a mes (isso exigiria investigar a
    secao separada "Proventos (semestral, ult. 5 anos)", que pode ser
    grafico/JS -- nao confirmado ainda). Retorna so o ULTIMO pagamento
    (data + valor), util para mostrar na Carteira de FIIs enquanto o
    historico completo nao e implementado.

    Retorna dict {'data_pagamento': 'DD/MM/AA', 'valor': float} ou None.
    """
    import html as _html_mod
    # CORRIGIDO 30/06/2026: KNCA11 (Kinea Credito Agro) retornava "nao
    # encontrado" porque StatusInvest classifica Fiagros numa URL
    # SEPARADA (/fiagros/), nao em /fundos-imobiliarios/ nem /fiinfras/ --
    # mesmo com nosso campo interno 'segmento' dizendo 'papel' (categorias
    # internas nossas nao mapeiam 1:1 com as do StatusInvest). Tenta as 4
    # bases sempre, no lugar de confiar no 'segmento' para decidir.
    # /fip/ adicionado 30/06/2026 para cobrir FIP-IE (KNDI11, BDIV11, etc)
    bases = ['fundos-imobiliarios', 'fiinfras', 'fiagros', 'fip']
    if segmento == 'fi-infra':
        bases = ['fiinfras', 'fip', 'fundos-imobiliarios', 'fiagros']
    for base in bases:
        try:
            r = requests.get(
                f'https://statusinvest.com.br/{base}/{ticker.lower()}',
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
                timeout=10)
            if not r.ok:
                continue
            texto = re.sub(r'<[^>]+>', ' ', r.text)
            texto = _html_mod.unescape(texto)  # decodifica &#xFA; -> u, &nbsp; -> espaco, etc.
            texto = re.sub(r'\s+', ' ', texto)
            # Procura TODAS as ocorrencias e usa a PRIMEIRA que tem o
            # padrao completo (numero + data) -- ignora a do widget JS
            # (que nao tem numero/data reais, so o nome do placeholder)
            for m in re.finditer(
                r'[uú]ltimo (?:provento pago do|rendimento do)\s*\w*\s*foi (?:um rendimento de|de)\s*R\$\s*([\d.,]+)\s*por (?:papel|cota)\s*no dia\s*(\d{2}/\d{2}/\d{2,4})',
                texto, re.IGNORECASE):
                valor = float(m.group(1).replace('.', '').replace(',', '.'))
                return {'data_pagamento': m.group(2), 'valor': valor if valor > 0 else None}
        except Exception:
            continue
    return None

@app.route('/fii-ultimo-provento', methods=['GET'])
def get_fii_ultimo_provento():
    """
    GET /fii-ultimo-provento?ticker=BDIF11&segmento=fi-infra
    Retorna o ultimo provento pago (data + valor por cota) via
    StatusInvest. Usado na Carteira de FIIs para mostrar o ultimo
    pagamento recebido sem precisar de historico completo ainda.
    """
    ticker = request.args.get('ticker', '').strip()
    if not ticker:
        return jsonify({'error': "parametro 'ticker' obrigatorio"}), 400
    segmento = request.args.get('segmento')
    dados = scrape_statusinvest_ultimo_provento(ticker, segmento)
    if dados is None:
        return jsonify({'ticker': ticker, 'encontrado': False, 'data_pagamento': None, 'valor': None})
    return jsonify({'ticker': ticker, 'encontrado': True, **dados})


# ── HISTÓRICO DE PROVENTOS (CARTEIRA DE FIIs) ─────────────────────────────────
# Adicionado 30/06/2026 -- backlog item 2.
# Busca totais semestrais de proventos do StatusInvest (server-side renderizado,
# mesmo padrão já validado em scrape_statusinvest_ultimo_provento).
# O HTML já expõe totais como:
#   "dividendos recebidos entre 01/01/2026 e 30/06/2026 R$ 5,5500"
# Soma os semestres para compor os últimos 12 meses, e filtra por data de
# ativação para o acumulado desde que o usuário entrou no FII.
def scrape_statusinvest_historico_proventos(ticker, segmento=None):
    """
    Retorna lista de pagamentos mensais e totais agregados via StatusInvest.
    Estrutura retornada:
    {
      'ultimo_provento': {'data': 'DD/MM/AA', 'valor': float},
      'semestres': [{'periodo': '01/01/2026 - 30/06/2026', 'total': float}, ...],
      'total_12m': float,   # soma dos ultimos 2 semestres completos
    }
    Retorna None se nao conseguir extrair nada.
    """
    import html as _html_mod
    from datetime import datetime, timedelta

    bases = ['fundos-imobiliarios', 'fiinfras', 'fiagros', 'fip']
    if segmento == 'fi-infra':
        bases = ['fiinfras', 'fip', 'fundos-imobiliarios', 'fiagros']

    for base in bases:
        try:
            r = requests.get(
                f'https://statusinvest.com.br/{base}/{ticker.lower()}',
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
                timeout=12)
            if not r.ok:
                continue
            texto = re.sub(r'<[^>]+>', ' ', r.text)
            texto = _html_mod.unescape(texto)
            texto = re.sub(r'\s+', ' ', texto)

            # Extrai totais semestrais: "dividendos recebidos entre DD/MM/AAAA e DD/MM/AAAA R$ X,XX"
            semestres = []
            for m in re.finditer(
                r'dividendos recebidos entre (\d{2}/\d{2}/\d{4}) e (\d{2}/\d{2}/\d{4})\s+R\$\s+([\d.,]+)',
                texto, re.IGNORECASE):
                try:
                    total = float(m.group(3).replace('.', '').replace(',', '.'))
                    semestres.append({
                        'inicio': m.group(1),
                        'fim': m.group(2),
                        'periodo': f"{m.group(1)} - {m.group(2)}",
                        'total': total
                    })
                except: pass

            if not semestres:
                continue

            # Ordena por data de fim (mais recente primeiro)
            def _parse_dt(s):
                try: return datetime.strptime(s, '%d/%m/%Y')
                except: return datetime.min
            semestres.sort(key=lambda x: _parse_dt(x['fim']), reverse=True)

            # Total 12 meses = soma dos 2 semestres mais recentes completos
            # (exclui semestres futuros com total=0 que o StatusInvest as vezes inclui)
            sems_validos = [s for s in semestres if s['total'] > 0]
            total_12m = sum(s['total'] for s in sems_validos[:2])

            # Ultimo provento (reusar funcao ja existente)
            ultimo = scrape_statusinvest_ultimo_provento(ticker, segmento)

            return {
                'ticker': ticker,
                'semestres': sems_validos,
                'total_12m': round(total_12m, 4),
                'ultimo_provento': ultimo,
            }
        except Exception:
            continue
    return None

@app.route('/carteira-fiis/proventos', methods=['GET'])
def get_carteira_fiis_proventos():
    """
    GET /carteira-fiis/proventos?ticker=KNCR11&data_ativacao=2026-06-26&preco_ativacao=107.70&segmento=papel
    Retorna historico de proventos para 1 FII da carteira ativa:
    - total_12m: soma dos ultimos 2 semestres (R$/cota)
    - dy_12m_pct: total_12m / preco_ativacao * 100
    - acumulado_ativacao: soma dos proventos pagos APOS a data de ativacao (best-effort)
    - dy_ativacao_pct: acumulado_ativacao / preco_ativacao * 100
    - semestres: lista de periodos com totais
    - ultimo_provento: data + valor do ultimo pagamento
    Apenas para FIIs com status='ativa' na carteira -- logica de filtro e feita no frontend.
    """
    ticker = request.args.get('ticker','').strip().upper()
    if not ticker:
        return jsonify({'error': "parametro 'ticker' obrigatorio"}), 400
    segmento = request.args.get('segmento')
    preco_raw = request.args.get('preco_ativacao','0')
    data_ativ_raw = request.args.get('data_ativacao','')

    try:
        preco_ativacao = float(preco_raw)
    except:
        preco_ativacao = 0.0

    try:
        from datetime import datetime
        data_ativ = datetime.strptime(data_ativ_raw, '%Y-%m-%d').date()
    except:
        data_ativ = None

    hist = scrape_statusinvest_historico_proventos(ticker, segmento)
    if not hist:
        return jsonify({'ticker': ticker, 'encontrado': False,
                        'total_12m': None, 'dy_12m_pct': None,
                        'acumulado_ativacao': None, 'dy_ativacao_pct': None,
                        'semestres': [], 'ultimo_provento': None})

    total_12m = hist['total_12m']
    dy_12m_pct = round(total_12m / preco_ativacao * 100, 2) if preco_ativacao > 0 else None

    # Acumulado desde ativacao: soma dos semestres cujo FIM e apos data_ativacao
    # Best-effort: se data_ativacao esta no meio de um semestre, conta o semestre
    # inteiro (conservador -- pode superestimar levemente)
    acumulado_ativacao = None
    dy_ativacao_pct = None
    if data_ativ and hist['semestres']:
        from datetime import datetime
        total_ativ = 0.0
        for s in hist['semestres']:
            try:
                fim_sem = datetime.strptime(s['fim'], '%d/%m/%Y').date()
                if fim_sem >= data_ativ:
                    total_ativ += s['total']
            except: pass
        # Adiciona ultimo provento se for mais recente que o ultimo semestre
        if hist['ultimo_provento'] and hist['ultimo_provento'].get('valor'):
            try:
                data_ult = hist['ultimo_provento']['data_pagamento']
                # tenta DD/MM/AA e DD/MM/AAAA
                for fmt in ('%d/%m/%y', '%d/%m/%Y'):
                    try:
                        dt_ult = datetime.strptime(data_ult, fmt).date()
                        break
                    except: dt_ult = None
                # So adiciona se nao ja estiver contido num semestre computado
                if dt_ult and dt_ult >= data_ativ:
                    # Verifica se a data cai apos o fim do semestre mais recente
                    fim_mais_recente = None
                    for s in hist['semestres']:
                        try:
                            f = datetime.strptime(s['fim'], '%d/%m/%Y').date()
                            if fim_mais_recente is None or f > fim_mais_recente:
                                fim_mais_recente = f
                        except: pass
                    if fim_mais_recente and dt_ult > fim_mais_recente:
                        total_ativ += hist['ultimo_provento']['valor']
            except: pass
        acumulado_ativacao = round(total_ativ, 4)
        dy_ativacao_pct = round(total_ativ / preco_ativacao * 100, 2) if preco_ativacao > 0 else None

    return jsonify({
        'ticker': ticker,
        'encontrado': True,
        'total_12m': total_12m,
        'dy_12m_pct': dy_12m_pct,
        'acumulado_ativacao': acumulado_ativacao,
        'dy_ativacao_pct': dy_ativacao_pct,
        'preco_ativacao': preco_ativacao,
        'data_ativacao': data_ativ_raw,
        'semestres': hist['semestres'],
        'ultimo_provento': hist['ultimo_provento'],
    })


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
    TOKEN = os.environ.get('GITHUB_TOKEN', '')
    REPO  = os.environ.get('GITHUB_REPO', 'vmasardinha-coder/trader-desk')
    if not TOKEN:
        return {}, None
    try:
        req = _ur.Request(
            f'https://api.github.com/repos/{REPO}/contents/{FOTOS_PATH}',
            headers={'Authorization': f'token {TOKEN}', 'Accept': 'application/vnd.github.v3+json'})
        with _ur.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read())
            sha = d['sha']
            data = json.loads(base64.b64decode(d['content']).decode())
            GITHUB_FOTOS_SHA['sha'] = sha
            return data, sha
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}, None
        raise
    except Exception:
        return {}, None

def _write_fotos(data, sha=None):
    """Salva fotos_papel.json no repo. Cria se nao existir (sha=None)."""
    import urllib.request as _ur
    TOKEN = os.environ.get('GITHUB_TOKEN', '')
    REPO  = os.environ.get('GITHUB_REPO', 'vmasardinha-coder/trader-desk')
    if not TOKEN:
        return False
    payload = {'message': 'update: fotos_papel.json (auto)',
               'content': base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()}
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

def _calc_bandas_foto(S, sigma, periodos=(21, 60, 90)):
    """
    Calcula bandas (p10/p25/p50/p75/p90) para cada periodo usando GBM.
    Retorna dict: {"21": {"p10":..., "p25":..., "p50":..., "p75":..., "p90":...}, ...}
    Cada valor e uma lista de floats (um por dia), tamanho = periodo+1 (dia 0 = S).
    """
    try:
        import numpy as np
        n_sim = 3000
        dt = 1 / 252.0
        drift = -0.5 * sigma**2 * dt
        vol_step = sigma * math.sqrt(dt)
        bandas = {}
        for T in periodos:
            z = np.random.standard_normal((n_sim, T))
            log_ret = drift + vol_step * z
            paths = S * np.exp(np.cumsum(log_ret, axis=1))
            paths = np.hstack([np.full((n_sim, 1), S), paths])
            bd = {}
            for p in [10, 25, 50, 75, 90]:
                bd[f'p{p}'] = np.percentile(paths, p, axis=0).round(4).tolist()
            bandas[str(T)] = bd
        return bandas
    except Exception as e:
        return {}

def _fetch_closes_for_foto(ticker, from_date_str):
    """
    Busca closes diarios desde from_date_str (YYYY-MM-DD) ate hoje via Yahoo.
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
                timestamps = result['timestamps']
                closes = result['indicators']['quote'][0]['close']
                pairs = []
                for ts, cl in zip(timestamps, closes):
                    if cl is None:
                        continue
                    dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                    if dt >= from_date_str:
                        pairs.append({'data': dt, 'close': round(float(cl), 4)})
                return pairs
            except:
                continue
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

        # Busca preco atual e historico para GARCH
        S = None
        closes = []
        for host in ['query1', 'query2']:
            try:
                r = requests.get(
                    f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y',
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
            return jsonify({'error': f'Nao foi possivel obter preco de {ticker}'}), 500

        # GARCH com historico atual (vol recalculada)
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
            sigma = vol_hist(closes) if closes else 0.35

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
    score = None
    if historico_real and foto.get('bandas', {}).get('90'):
        bd90 = foto['bandas']['90']
        dentro_p50 = 0; dentro_p75 = 0; dentro_p90 = 0; total = 0
        for i, ponto in enumerate(historico_real):
            if i == 0:
                continue  # dia 0 = preco da foto, nao conta
            idx = min(i, len(bd90['p10']) - 1)
            cl = ponto['close']
            total += 1
            if bd90['p25'][idx] <= cl <= bd90['p75'][idx]:
                dentro_p50 += 1
            if bd90['p10'][idx] <= cl <= bd90['p90'][idx]:
                dentro_p90 += 1
        if total > 0:
            score = {
                'dias_observados': total,
                'pct_dentro_p25_p75': round(dentro_p50 / total * 100, 1),
                'pct_dentro_p10_p90': round(dentro_p90 / total * 100, 1),
            }

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

@app.route('/debug-statusinvest', methods=['GET'])
def debug_statusinvest():
    """
    DIAGNOSTICO TEMPORARIO (30/06/2026) -- investigando se
    statusinvest.com.br e viavel como fonte alternativa de cotacao para
    BDRs de baixa liquidez (BSLV39 nao tem historico suficiente no Yahoo).
    Busca a pagina real e expoe status_code, tamanho, e se existe um
    bloco __NEXT_DATA__ (JSON embutido server-side, comum em apps
    Next.js -- se existir, e uma fonte MUITO mais confiavel que regex em
    texto visivel, igual usado para FI-Infra). Remover depois de decidir
    a abordagem definitiva.
    """
    ticker = request.args.get('ticker', 'BSLV39').lower()
    base = request.args.get('base', 'bdrs')
    try:
        r = requests.get(
            f'https://statusinvest.com.br/{base}/{ticker}',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
            timeout=10)
        html = r.text
        tem_next_data = '__NEXT_DATA__' in html
        idx_next = html.find('__NEXT_DATA__')
        snippet_next = html[idx_next:idx_next+800] if idx_next != -1 else None

        # Procura tambem por padrao de preco visivel simples, tipo fallback
        texto = re.sub(r'<[^>]+>', ' ', html)
        texto = re.sub(r'\s+', ' ', texto)
        idx_preco = texto.find('R$')
        idx_provento = texto.lower().find('ltimo provento')
        if idx_provento == -1:
            idx_provento = texto.lower().find('ltimo rendimento')

        # ADICIONADO -- lista TODAS as ocorrencias (a primeira pode ser
        # so o label do widget JS, sem o valor real; a frase completa
        # tipo SEO costuma vir mais adiante no HTML)
        todas_ocorrencias = []
        for padrao_busca in ['ltimo provento', 'ltimo rendimento']:
            start = 0
            while True:
                idx = texto.lower().find(padrao_busca, start)
                if idx == -1:
                    break
                todas_ocorrencias.append(texto[max(0,idx-20):idx+200])
                start = idx + 1

        return jsonify({
            'status_code': r.status_code,
            'html_len': len(html),
            'tem_next_data_json': tem_next_data,
            'snippet_next_data': snippet_next,
            'snippet_texto_inicio_RS': texto[max(0,idx_preco-50):idx_preco+200] if idx_preco != -1 else 'R$ NAO ENCONTRADO NO TEXTO',
            'snippet_provento': texto[max(0,idx_provento-30):idx_provento+250] if idx_provento != -1 else 'TEXTO "ultimo provento/rendimento" NAO ENCONTRADO',
            'todas_ocorrencias_provento': todas_ocorrencias,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

_SI_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Referer': 'https://statusinvest.com.br/',
}

def scrape_statusinvest_tickers_listagem(path):
    """
    Extrai lista de tickers de uma pagina de listagem do StatusInvest.
    Paths conhecidos: 'fundos-imobiliarios', 'fiinfras', 'fip'.
    Retorna lista de dicts {'ticker', 'nome_fundo', 'cotacao', 'categoria_si'}
    ou (None, erro).

    O HTML dessas paginas e server-side renderizado e contem blocos como:
      TICKER  NOME COMPLETO  arrow_upward X,XX %  R$ YYY,YY  arrow_right
    Estrategia: regex no HTML bruto para capturar ticker + nome + cotacao
    que aparecem juntos em cada item da lista.
    """
    try:
        r = requests.get(
            f'https://statusinvest.com.br/{path}',
            headers=_SI_HEADERS, timeout=20)
        if not r.ok:
            return None, f'http_{r.status_code}'
        html = r.text
        # Extrai tickers via padrao: href="/fundos-imobiliarios/TICKER" ou
        # href="/fiinfras/TICKER" -- o ticker aparece no href da pagina individual
        tickers = list(dict.fromkeys(
            re.findall(
                r'href="/' + re.escape(path) + r'/([a-z0-9]{4,7})/"',
                html, re.IGNORECASE)
        ))
        tickers = [t.upper() for t in tickers if re.match(r'^[A-Z]{4,6}[0-9]{2}$', t.upper())]
        # Fallback: regex no texto (padrao que vimos no debug: TICKER no HTML como texto)
        if not tickers:
            texto = re.sub(r'<[^>]+>', ' ', html)
            tickers = list(dict.fromkeys(
                re.findall(r'\b([A-Z]{4,6}[0-9]{2})\b', texto)
            ))
        return tickers, None
    except Exception as e:
        return None, str(e)


def scrape_statusinvest_fundo_dados(ticker, path_categoria):
    """
    Busca dados financeiros de um fundo individual via StatusInvest.
    path_categoria: 'fundos-imobiliarios' | 'fiinfras' | 'fip'

    Retorna dict com ticker/cotacao/dy_pct/p_vp/liquidez ou None se falhar.
    NUNCA inventa numero -- campos ausentes ficam None.

    Reutiliza o mesmo padrao ja validado em scrape_statusinvest_ultimo_provento:
    StatusInvest e server-side renderizado, texto puro acessivel via requests.get().
    """
    try:
        r = requests.get(
            f'https://statusinvest.com.br/{path_categoria}/{ticker.lower()}',
            headers=_SI_HEADERS, timeout=10)
        if not r.ok:
            return None
        html = r.text
        import html as html_lib
        texto = html_lib.unescape(re.sub(r'<[^>]+>', ' ', html))
        texto = re.sub(r'\s+', ' ', texto)

        def _parse_num(s):
            try:
                return float(s.replace('.', '').replace(',', '.'))
            except Exception:
                return None

        # Cotacao atual -- padrao: "Valor atual R$ X,XX" ou "R$ X,XX" proximo de "Valor atual"
        cotacao = None
        m = re.search(r'Valor atual\s*R\$\s*([\d.]+,\d+)', texto, re.IGNORECASE)
        if not m:
            m = re.search(r'R\$\s*([\d.]+,\d+)', texto)
        if m:
            cotacao = _parse_num(m.group(1))
            if cotacao and cotacao <= 0:
                cotacao = None

        # DY -- padrao: "X,XX%" proximo de "Dividend Yield" ou "DY"
        dy_pct = None
        m = re.search(r'Dividend Yield[^%]{0,60}?([\d]+,\d+)\s*%', texto, re.IGNORECASE)
        if not m:
            m = re.search(r'([\d]+,\d+)\s*%[^%]{0,30}?Dividend Yield', texto, re.IGNORECASE)
        if m:
            dy_pct = _parse_num(m.group(1))
            if dy_pct and (dy_pct <= 0 or dy_pct > 100):
                dy_pct = None

        # P/VP
        p_vp = None
        m = re.search(r'P[/\\.]VP[^0-9]{0,20}?([\d]+,\d+)', texto, re.IGNORECASE)
        if m:
            p_vp = _parse_num(m.group(1))
            if p_vp and (p_vp <= 0 or p_vp > 20):
                p_vp = None

        # Liquidez diaria
        liquidez = None
        m = re.search(
            r'Liquidez[^R]{0,20}?R\$\s*([\d.,]+)\s*(M|K|B|Mil|Milh[õo]es|Bilh[õo]es)?',
            texto, re.IGNORECASE)
        if m:
            raw, un = m.group(1), (m.group(2) or '').upper()
            liquidez = _parse_num(raw)
            if liquidez is not None:
                if un in ('M', 'MILH', 'MILHÕES', 'MILHOES'):
                    liquidez *= 1_000_000
                elif un in ('B', 'BILH', 'BILHÕES', 'BILHOES'):
                    liquidez *= 1_000_000_000
                elif un in ('K', 'MIL'):
                    liquidez *= 1_000
                if liquidez <= 0:
                    liquidez = None

        if dy_pct is None and cotacao is None:
            return None  # sem nenhum dado util, nao retorna entrada vazia
        return {
            'ticker': ticker.upper(),
            'cotacao': cotacao,
            'dy_pct': dy_pct,
            'p_vp': p_vp,
            'liquidez': liquidez,
        }
    except Exception:
        return None


@app.route('/fiis/universo-complementar', methods=['GET'])
def fiis_universo_complementar():
    """
    Busca os tickers NAO cobertos pelo Fundamentus (FII tradicionais
    menos conhecidos + FI-Infra + FIP-Infra) via StatusInvest, e retorna
    dados financeiros de cada um.

    Fluxo:
    1. Busca tickers das 3 paginas de listagem do StatusInvest
       (fundos-imobiliarios, fiinfras, fip)
    2. Recebe lista de tickers_ja_cobertos via query param (enviados
       pelo frontend apos a Chamada A do Fundamentus), filtra os que
       ja tem dado completo
    3. Busca dados individuais dos tickers restantes em paralelo via
       ThreadPoolExecutor, em lotes para nao estourar memoria do Render
    4. Aplica mesmo criterio de descarte (liquidez >= 50k, DY > 0)
    5. Retorna lista pronta para merge no frontend

    Query params:
    - tickers_cobertos: string separada por virgula dos tickers que o
      Fundamentus ja cobriu (para nao duplicar)
    - incluir_fip: 1|0 (default 1) -- se inclui FIP-IE de infra
    - liquidez_min: default 50000
    """
    try:
        liquidez_min = float(request.args.get('liquidez_min', 50000))
        incluir_fip = request.args.get('incluir_fip', '1') == '1'
        tickers_cobertos_str = request.args.get('tickers_cobertos', '')
        tickers_cobertos = set(t.strip().upper() for t in tickers_cobertos_str.split(',') if t.strip())

        # Passo 1: coletar tickers das listagens do StatusInvest
        categorias = [
            ('fiinfras', 'fi-infra'),
        ]
        if incluir_fip:
            categorias.append(('fip', 'fi-infra'))  # FIP-IE vai para categoria 'fi-infra'

        # Para FII tradicional, tambem buscamos listagem do StatusInvest
        # para pegar os ~140 nao cobertos pelo Fundamentus
        categorias.insert(0, ('fundos-imobiliarios', 'fii'))

        todos_tickers = []  # lista de (ticker, path_si, segmento_app)
        tickers_vistos = set(tickers_cobertos)

        for path_si, segmento_app in categorias:
            tickers_lista, erro = scrape_statusinvest_tickers_listagem(path_si)
            if not tickers_lista:
                continue
            for t in tickers_lista:
                if t in tickers_vistos:
                    continue
                tickers_vistos.add(t)
                todos_tickers.append((t, path_si, segmento_app))

        if not todos_tickers:
            return jsonify({'fundos': [], 'total': 0, 'aviso': 'nenhum ticker novo encontrado'})

        # Passo 2: buscar dados individuais em paralelo, lotes de 10
        # para nao estourar memoria do Render free tier
        resultados = []
        LOTE = 10

        def _buscar(args):
            ticker, path_si, segmento_app = args
            dados = scrape_statusinvest_fundo_dados(ticker, path_si)
            if dados is None:
                return None
            dados['segmento'] = segmento_app
            dados['segmento_fundamentus'] = (
                'Fundo de Infraestrutura (FI-Infra)' if segmento_app == 'fi-infra'
                else 'Fundo de Participações (FIP)' if segmento_app == 'fip'
                else 'FII Tradicional'
            )
            dados['fonte'] = 'statusinvest'
            return dados

        for i in range(0, len(todos_tickers), LOTE):
            lote = todos_tickers[i:i+LOTE]
            with ThreadPoolExecutor(max_workers=LOTE) as ex:
                parcial = list(ex.map(_buscar, lote))
            resultados.extend([d for d in parcial if d is not None])

        # Passo 3: aplicar criterio e classificar risco
        from statistics import median
        fundos_validos = []
        fundos_fora = []

        dy_vals = [f['dy_pct'] for f in resultados if f.get('dy_pct')]
        mediana_dy_global = median(dy_vals) if dy_vals else 10.0

        for f in resultados:
            motivo = None
            liq = f.get('liquidez')
            dy = f.get('dy_pct')
            if liq is None or liq < liquidez_min:
                motivo = f'liquidez baixa' if liq is not None else 'liquidez ausente'
            elif dy is None or dy <= 0:
                motivo = 'DY zerado ou ausente'

            if motivo:
                f['fora_criterio'] = True
                f['motivo_fora_criterio'] = motivo
                f['nivel_risco'] = None
                f['score'] = None
                fundos_fora.append(f)
            else:
                f['fora_criterio'] = False
                f['nivel_risco'] = _classificar_risco_fii(
                    f.get('nome_fundo', f['ticker']),
                    f.get('segmento_fundamentus', ''),
                    dy, None, mediana_dy_global)
                f['score'] = _score_fii(f.get('p_vp'), dy, liq, None)
                fundos_validos.append(f)

        ordem_risco = {'high_grade': 0, 'middle_risk': 1, 'high_yield': 2}
        fundos_validos.sort(key=lambda f: (ordem_risco.get(f['nivel_risco'], 1), -(f['score'] or 0)))
        fundos_fora.sort(key=lambda f: f['ticker'])

        todos = fundos_validos + fundos_fora
        return jsonify({
            'total': len(todos),
            'total_validos': len(fundos_validos),
            'total_fora_criterio': len(fundos_fora),
            'fundos': todos,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/debug-statusinvest-listagem', methods=['GET'])
def debug_statusinvest_listagem():
    """
    DIAGNOSTICO (30/06/2026) -- valida se as 3 paginas de listagem em lote
    do StatusInvest sao server-side renderizadas e qual o padrao de texto
    real retornado por requests.get() para cada categoria:
      - /fundos-imobiliarios  (FII tradicional)
      - /fiinfras             (FI-Infra)
      - /fip                  (FIP -- inclui FIP-IE tematico de infra)
    Retorna: status_code, tamanho do HTML, primeiros 3000 chars do texto
    limpo (sem tags HTML), e exemplos de tickers encontrados via regex simples.
    """
    _HEADERS_SI = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9',
        'Referer': 'https://statusinvest.com.br/',
    }
    categoria = request.args.get('categoria', 'fi_infra')
    _PATH_MAP = {'fii': 'fundos-imobiliarios', 'fi_infra': 'fiinfras', 'fip': 'fip'}
    path = _PATH_MAP.get(categoria, 'fiinfras')
    try:
        r = requests.get(
            f'https://statusinvest.com.br/{path}',
            headers=_HEADERS_SI, timeout=20)
        html = r.text
        texto = re.sub(r'<[^>]+>', ' ', html)
        texto = re.sub(r'\s+', ' ', texto).strip()
        # Acha tickers no HTML bruto
        tickers_achados = list(dict.fromkeys(
            re.findall(r'\b([A-Z]{4,6}[0-9]{2}F?\b)', html)
        ))[:50]
        # Pega trecho em volta do primeiro ticker encontrado (dados reais)
        snippet_ticker = ''
        if tickers_achados:
            idx = texto.find(tickers_achados[0])
            if idx != -1:
                snippet_ticker = texto[max(0,idx-100):idx+500]
        # Pega trecho onde aparece primeiro numero financeiro tipo "R$" ou "%"
        idx_rs = texto.find('R$')
        snippet_rs = texto[max(0,idx_rs-50):idx_rs+800] if idx_rs != -1 else ''
        # Pega trecho do meio do texto (onde geralmente ficam os cards de fundos)
        meio = len(texto)//2
        snippet_meio = texto[meio:meio+2000]
        return jsonify({
            'status_code': r.status_code,
            'html_len': len(html),
            'texto_len': len(texto),
            'tem_next_data': '__NEXT_DATA__' in html,
            'tickers_achados': tickers_achados,
            'snippet_em_volta_ticker1': snippet_ticker,
            'snippet_primeiro_rs': snippet_rs,
            'snippet_meio_texto': snippet_meio,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/fii-infra', methods=['GET'])
def get_fii_infra():
    """
    Lista FI-Infra + FIP-IE (Fundo de Investimentos em Participacoes de
    Infraestrutura tematico) com dados financeiros completos via Investidor10.

    ATUALIZADO 30/06/2026: FIP-IE (ex: KNDI11, BDIV11, XPIE11) adicionados
    como categoria 'fi-infra' por decisao do usuario -- agrupamento TEMATICO
    (infraestrutura), nao regulatorio. Usa o mesmo scrape_fi_infra_dados()
    (Investidor10/FAQ) que ja funciona para FI-Infra puro.

    ?debug=1 -- modo diagnostico: roda so o primeiro ticker com debug=True.
    """
    # FIP-IE conhecidos (Fundo de Investimentos em Participacoes de
    # Infraestrutura) -- agrupados com FI-Infra por decisao do usuario
    # (30/06/2026). Lista baseada nos tickers encontrados via StatusInvest
    # /fip confirmados como tematica de infraestrutura (energia/portos/etc),
    # nao FIP de outros setores (imobiliario, etc).
    TICKERS_FIP_IE = [
        'KNDI11',  # Kinea Estrategia Infra
        'BDIV11',  # BTG Pactual Infraestrutura Dividendos
        'XPIE11',  # XP Infra Energia
        'DIVS11',  # Sparta Infra Inflacao Longa -- confirmado FI-Infra pelo Investidor10
        'VIGT11',  # Vinci Energia
        'BRZP11',  # BRZ Infra Portos
        'ENDD11',  # Endurance Debt Infra
        'GTIS11',  # GTIS Energia
        'PICE11',  # Primoris Capital Infra
        'PPEI11',  # PP Energia Infra
    ]

    try:
        fundos, erro = scrape_fi_infra()
        if fundos is None:
            return jsonify({
                'error': f'Scraping do fiis.com.br falhou ou layout pode ter mudado: {erro}',
                'fundos': [],
            }), 502

        # Adiciona FIP-IE a lista, marcando categoria separada para display
        tickers_ja_presentes = {f['ticker'] for f in fundos}
        for ticker in TICKERS_FIP_IE:
            if ticker not in tickers_ja_presentes:
                fundos.append({
                    'ticker': ticker,
                    'nome_fundo': ticker,
                    'fonte_match': 'fip_ie_lista_conhecida',
                    'categoria_display': 'FIP-IE',  # badge diferente no frontend
                })

        if request.args.get('debug') == '1' and fundos:
            primeiro = fundos[0]
            dados_debug = scrape_fi_infra_dados(primeiro['ticker'], debug=True)
            return jsonify({'debug_ticker': primeiro['ticker'], 'resultado': dados_debug})

        # Busca dados individuais em PARALELO (antes era serial -- com ~30
        # tickers cada um fazendo 1 request HTTP, serial = 30x timeout em serie,
        # facil de estourar o worker do Render free tier).
        # max_workers=8: equilibrio entre velocidade e uso de memoria/conexoes.
        def _buscar_dados_fi(f):
            dados = scrape_fi_infra_dados(f['ticker'])
            if dados:
                f.update(dados)
                f['dados_disponiveis'] = True
            else:
                f['dy_pct'] = None
                f['cotacao'] = None
                f['liquidez'] = None
                f['p_vp'] = None
                f['dados_disponiveis'] = False
            return f

        with ThreadPoolExecutor(max_workers=8) as executor:
            fundos = list(executor.map(_buscar_dados_fi, fundos))

        # ADICIONADO 29/06/2026 -- classificacao por criterio e nivel de
        # risco, reaproveitando EXATAMENTE a mesma logica ja usada para
        # FII tradicional (_classificar_risco_fii/_score_fii), agora que
        # cotacao/DY/liquidez/P/VP existem de verdade para FI-Infra.
        #
        # Diferenca em relacao ao FII tradicional: nao ha "segmento" do
        # Fundamentus para comparar DY relativo (FI-Infra nao e coberto
        # por ele) -- a mediana de DY usada para detectar premio de risco
        # e calculada AUTO-REFERENCIADA, so entre os proprios FI-Infra
        # validos (mesma categoria regulatoria, comparacao justa).
        liquidez_min = float(request.args.get('liquidez_min', 50000))
        from statistics import median
        validos_dy = [f['dy_pct'] for f in fundos
                      if f.get('dados_disponiveis') and f.get('dy_pct') is not None]
        mediana_dy_fi_infra = median(validos_dy) if validos_dy else None

        for f in fundos:
            if not f.get('dados_disponiveis'):
                f['fora_criterio'] = True
                f['motivo_fora_criterio'] = 'sem dados financeiros disponiveis'
                f['nivel_risco'] = None
                f['score'] = None
                continue

            motivo = None
            if f['liquidez'] is None or f['liquidez'] < liquidez_min:
                motivo = (f'liquidez baixa (R${f["liquidez"]:,.0f}/dia)'
                          if f['liquidez'] is not None else 'liquidez ausente')
            elif f['dy_pct'] is None or f['dy_pct'] <= 0:
                motivo = 'DY zerado ou ausente'

            if motivo:
                f['fora_criterio'] = True
                f['motivo_fora_criterio'] = motivo
                f['nivel_risco'] = None
                f['score'] = None
            else:
                f['fora_criterio'] = False
                f['nivel_risco'] = _classificar_risco_fii(
                    f.get('nome_fundo', ''), 'Fundo de Infraestrutura (FI-Infra)',
                    f['dy_pct'], None, mediana_dy_fi_infra)
                f['score'] = _score_fii(f.get('p_vp'), f['dy_pct'], f['liquidez'])

        ordem_risco = {'high_grade': 0, 'middle_risk': 1, 'high_yield': 2}
        fundos.sort(key=lambda f: (
            f.get('fora_criterio', True),
            ordem_risco.get(f.get('nivel_risco'), 1),
            -(f.get('score') or 0)
        ))

        return jsonify({'total': len(fundos), 'fundos': fundos, 'mediana_dy_categoria': mediana_dy_fi_infra})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

if __name__=='__main__':
    app.run(debug=False,host='0.0.0.0',port=int(__import__('os').environ.get('PORT',5000)))
