"""  # v10.11
Trader Desk — Proxy Server v10.11
Indicadores tecnicos + fundamentalistas + Monte Carlo + Futuros
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
        v=m.get('chartPreviousClose',cl[-2] if len(cl)>1 else p)
        return {'price':round(float(p),2),'prev':round(float(v),2)} if p else None
    except: return None

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

        if K_call is not None:
            call_ex = ST > K_call
            res['prob_call_exercida'] = round(float(call_ex.mean() * 100), 2)
            res['prob_sucesso'] = round(float((~call_ex).mean() * 100), 2)
        if K_put is not None:
            put_ex = ST < K_put
            res['prob_put_exercida'] = round(float(put_ex.mean() * 100), 2)
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
                    janela_real = cl[idx_inicio:idx_inicio + dias_passados + 1]
                    precos_reais_fan = [round(float(p), 2) for p in janela_real]

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

        # ── SIMULAÇÃO DIDÁTICA EM 100 AÇÕES (padrão fixo, qualquer tipo de
        # estrutura) — traduz os percentuais abstratos em R$ concretos sobre
        # um lote de 100 ações no preco_foto, nos 3 cenários possíveis:
        # defesa/barreira tocada, dentro do range (média/mediana), e teto/
        # ganho prefixado. Reaproveita o array de retorno já simulado acima
        # (retorno_full para bidirecional, retorno_full2 para retorno
        # controlado) quando disponível; senão, não calcula (sem dado
        # suficiente, ex. estrutura simples sem kdo/kuo/ganho_prefixado).
        try:
            capital_100 = preco_foto * 100
            sim_100 = None
            if retorno_full is not None and kdo is not None and kuo is not None:
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
            elif retorno_full2 is not None and kdo is not None:
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
            precos_reais_fan = [round(float(p), 2) for p in cl[idx_entrada:idx_entrada+dias_passados+1]]
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

# ── POSIÇÕES (JSON modular) ───────────────────────────
def _validar_positions(data):
    """Valida estrutura do positions.json. Retorna lista de erros (vazia se OK)."""
    erros = []
    if not isinstance(data, dict):
        return ['positions.json deve ser um objeto JSON']

    campos_base_simples = ['id','ticker','nome','tipo_posicao','estrategia','strike','vol_impl','tipo','vencimento']
    campos_base_barreira = ['id','ticker','nome','tipo_posicao','estrategia','vencimento','entry','kdo','kuo']
    campos_encerrada = ['id','ticker','estrategia','status']

    for i, p in enumerate(data.get('ativas', [])):
        pid = p.get('id', f'#{i}')
        if 'tipo_posicao' not in p:
            erros.append(f"ativas[{pid}]: falta campo 'tipo_posicao'")
            continue
        campos = campos_base_simples if p['tipo_posicao']=='simples' else campos_base_barreira if p['tipo_posicao']=='barreira' else None
        if campos is None:
            erros.append(f"ativas[{pid}]: tipo_posicao '{p['tipo_posicao']}' invalido (use 'simples' ou 'barreira')")
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

_CAMPOS_OBRIGATORIOS_ANALISE = ['id', 'ticker', 'nome', 'data_foto', 'preco_foto', 'prazo_dias', 'tipo_estrutura', 'origem', 'status']
_STATUS_VALIDOS = ['em_analise', 'ativa', 'encerrada']
_TIPOS_VALIDOS = ['bidirecional', 'retorno_controlado', 'premio', 'simples']
_ORIGENS_VALIDAS = ['customizada', 'pronta']

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
    """Le analises.json do repo (publico, via raw — leitura nao precisa de token)."""
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/analises.json',
            headers={'Cache-Control': 'no-cache'}, timeout=10)
        if not r.ok:
            return jsonify({'error': 'analises.json indisponivel'}), 500
        data = r.json()
        return jsonify(data)
    except ValueError as e:
        return jsonify({'error': f'analises.json com JSON malformado: {str(e)}'}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analises', methods=['POST'])
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

@app.route('/analises/<analise_id>/status', methods=['PUT'])
def mudar_status_analise(analise_id):
    """
    Move uma analise entre estagios (em_analise -> ativa -> encerrada, ou
    em_analise -> encerrada direto). Espera {'status': 'ativa'} no body.
    """
    try:
        body = request.get_json() or {}
        novo_status = body.get('status')
        if novo_status not in _STATUS_VALIDOS:
            return jsonify({'error': f'status invalido: {novo_status!r}'}), 422

        conteudo_str, sha = _github_get_file('analises.json')
        lista = json.loads(conteudo_str) if conteudo_str.strip() else []
        encontrado = False
        for item in lista:
            if item.get('id') == analise_id:
                item['status'] = novo_status
                encontrado = True
                break
        if not encontrado:
            return jsonify({'error': f'analise {analise_id} nao encontrada'}), 404

        novo_conteudo = json.dumps(lista, indent=2, ensure_ascii=False)
        _github_put_file('analises.json', novo_conteudo, sha,
            f"feat: analise {analise_id} -> status={novo_status} via app")
        return jsonify({'id': analise_id, 'status': novo_status})
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500
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
