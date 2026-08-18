# motor.py — Nucleo estatistico do Trader Desk
#
# Extraido do proxy.py em 03/07/2026 (Prioridade 2 da modularizacao,
# fase 1 de 4-5). Contem SOMENTE funcoes puras: recebem numeros/listas,
# devolvem numeros/listas/dicts, sem tocar Flask (app/request), sem
# fazer I/O de arquivo, sem chamar rede. E o nucleo "fechado" que Victor
# ja validou estar maduro (GARCH vs grid search vs MLE: zero diferenca
# pratica, topico encerrado) -- por isso e o primeiro modulo extraido,
# menor risco de todos pra modularizar.
#
# proxy.py importa daqui: rsi, mm, ema, macd, bollinger, obv, graham,
# vol_hist, garch_11, _calc_bandas_foto, _score_assertividade_bandas.
#
# Nao mexer na logica aqui dentro sem reler o GUIA de GARCH no projeto
# (montecarlo_garch_GUIA.md) -- ha decisoes de modelagem documentadas
# la (por que GARCH e nao so vol historica, por que grid search e nao
# MLE continuo, etc.).

import math

try:
    import numpy as _np
    _NUMPY = True
except ImportError:
    _NUMPY = False


# ── INDICADORES TECNICOS ──────────────────────────────
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


# ── PRECO JUSTO / VOLATILIDADE HISTORICA ──────────────
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


# ── BANDAS DE PROJECAO (GBM) / SCORE DE ASSERTIVIDADE ─
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
    except Exception:
        return {}

def _score_assertividade_bandas(historico_real, bandas_periodo):
    """
    Calcula % do tempo que o preco real ficou dentro da banda central
    (p25-p75) e da banda ampla (p10-p90), comparando dia a dia.
    Fatorado de get_foto_papel em 30/06/2026 para reuso em
    GET /analises/<id>/foto-bandas (backlog #4).
    """
    if not historico_real or not bandas_periodo:
        return None
    dentro_p50 = 0; dentro_p90 = 0; total = 0
    for i, ponto in enumerate(historico_real):
        if i == 0:
            continue  # dia 0 = preco da foto, nao conta
        idx = min(i, len(bandas_periodo['p10']) - 1)
        cl = ponto['close']
        total += 1
        if bandas_periodo['p25'][idx] <= cl <= bandas_periodo['p75'][idx]:
            dentro_p50 += 1
        if bandas_periodo['p10'][idx] <= cl <= bandas_periodo['p90'][idx]:
            dentro_p90 += 1
    if total == 0:
        return None
    return {
        'dias_observados': total,
        'pct_dentro_p25_p75': round(dentro_p50 / total * 100, 1),
        'pct_dentro_p10_p90': round(dentro_p90 / total * 100, 1),
    }

def _calc_prob_sucesso_prevista(preco_foto, sigma, prazo_dias, tipo_estrutura, kdo=None, kuo=None, n_sim=5000):
    """
    ADICIONADO 06/08/2026 -- tracking previsao-vs-realizado (item de
    backlog pedido pelo Victor). Calcula, no momento da FOTO (Fase B),
    a probabilidade de a estrutura NAO tocar a barreira ate o vencimento
    original -- mesma logica de simulacao GBM ja usada em /analises/ranking
    (prob_meta), so que ANCORADA no preco_foto/prazo_dias/sigma congelados
    na criacao, em vez de recalculada com o preco AO VIVO toda vez que o
    ranking roda. Isso congela UMA previsao unica e imutavel por analise,
    pra depois comparar contra o resultado real (sucesso/fracasso) e medir
    se o modelo era bem calibrado -- ex: entre as analises que o modelo deu
    80% de chance de sucesso, quantas realmente deram certo?

    So aplicavel a retorno_controlado (kdo) e bidirecional (kdo e/ou kuo).
    Para outros tipos (simples, fii), retorna None -- nao inventa numero
    sem logica clara de "sucesso" definida para esses casos.

    CORRIGIDO 19/08/2026 -- bug achado pelo Victor (caso BBAS3 bidirecional
    9 meses): a versao anterior, para bidirecional, so checava a barreira
    de CIMA (kuo) e ainda com a logica invertida (retornava prob de TOCAR,
    nao de nao tocar -- inconsistente com o retorno_controlado, que sempre
    retornou prob de sucesso). Isso e conceitualmente errado pra bidirecional:
    tocar o KUO normalmente so CAPA o ganho (ainda positivo, ex: 9% fixo no
    caso BBAS3), enquanto tocar o KDO costuma ser a barreira que da PERDA
    integral sem protecao -- essa e a barreira que realmente importa pra
    medir "sucesso" de forma economicamente coerente com o retorno_controlado.
    Corrigido para: bidirecional agora calcula prob de NAO tocar o KDO
    (barreira de baixo, a que da prejuizo), com a mesma semantica de sucesso
    do retorno_controlado. Se so kuo for fornecido (sem kdo), cai num
    fallback que calcula prob de nao tocar o KUO, mas isso e raro -- a
    grande maioria das bidirecionais tem KDO definido.
    """
    try:
        if tipo_estrutura not in ('retorno_controlado', 'bidirecional'):
            return None
        if not preco_foto or not sigma or not prazo_dias or prazo_dias <= 0:
            return None
        import numpy as np
        dt = 1 / 252.0
        drift = -0.5 * sigma**2 * dt
        vol_step = sigma * math.sqrt(dt)
        z = np.random.standard_normal((n_sim, int(prazo_dias)))
        paths = preco_foto * np.exp(np.cumsum(drift + vol_step * z, axis=1))

        if tipo_estrutura == 'retorno_controlado':
            if kdo is None:
                return None
            min_path = np.min(paths, axis=1)
            tocou = min_path <= float(kdo)
            return round(float((~tocou).mean() * 100), 2)
        else:  # bidirecional
            if kdo is not None:
                # Metrica principal: prob de NAO tocar a barreira de baixo
                # (a que da prejuizo integral sem protecao) -- mesma
                # semantica de "sucesso" do retorno_controlado.
                min_path = np.min(paths, axis=1)
                tocou = min_path <= float(kdo)
                return round(float((~tocou).mean() * 100), 2)
            elif kuo is not None:
                # Fallback raro: so tem kuo cadastrado, sem kdo. Ainda
                # assim retorna prob de NAO tocar (semantica de sucesso
                # consistente), mesmo sabendo que kuo normalmente nao
                # representa perda, so limitacao de ganho.
                max_path = np.max(paths, axis=1)
                tocou = max_path >= float(kuo)
                return round(float((~tocou).mean() * 100), 2)
            return None
    except Exception:
        return None

def _calc_risco_overshoot(preco_foto, sigma, prazo_dias, teto_retorno_pct, n_sim=5000):
    """
    ADICIONADO 19/08/2026 -- pedido explicito do Victor: "Risco de
    Overshoot" (nome dele, para nao esquecer). Para retorno_controlado,
    o retorno fica travado no teto combinado (ex: 2,5%) mesmo que o papel
    suba muito mais -- o risco simetrico ao de tocar a barreira (que ja
    calculamos) e o de "deixar dinheiro na mesa": o papel fecha tao acima
    do esperado que o retorno fixo vira uma fracao pequena do que teria
    dado sem nenhuma estrutura.

    Calcula, via Monte Carlo (mesma simulacao GBM ja usada em toda parte
    do sistema):
    - prob_overshoot_pct: probabilidade de a variacao FINAL do papel (no
      vencimento, preco final vs preco_foto) superar o teto_retorno_pct
      combinado. Nao depende de ter tocado ou nao a barreira de baixa --
      e simplesmente "quanto o papel efetivamente valorizou vs o teto".
    - overshoot_medio_pct: MEDIA de quanto ficou acima do teto, CONDICIONAL
      a ter overshoot (ou seja, so conta os casos em que aconteceu) --
      ex: se overshoot_medio_pct=4.2, significa que quando acontece, em
      media o papel teria rendido 4,2 pontos percentuais A MAIS do que o
      retorno travado.

    Retorna dict {'prob_overshoot_pct':.., 'overshoot_medio_pct':..} ou
    None se parametros invalidos/erro -- nunca quebra o chamador.
    """
    try:
        if not preco_foto or not sigma or not prazo_dias or prazo_dias <= 0:
            return None
        if teto_retorno_pct is None:
            return None
        import numpy as np
        dt = 1 / 252.0
        drift = -0.5 * sigma**2 * dt
        vol_step = sigma * math.sqrt(dt)
        z = np.random.standard_normal((n_sim, int(prazo_dias)))
        paths = preco_foto * np.exp(np.cumsum(drift + vol_step * z, axis=1))
        preco_final = paths[:, -1]
        variacao_final_pct = (preco_final / preco_foto - 1) * 100

        overshoot_mask = variacao_final_pct > float(teto_retorno_pct)
        prob_overshoot = round(float(overshoot_mask.mean() * 100), 2)
        if overshoot_mask.any():
            overshoot_medio = round(
                float((variacao_final_pct[overshoot_mask] - float(teto_retorno_pct)).mean()), 2)
        else:
            overshoot_medio = 0.0

        return {'prob_overshoot_pct': prob_overshoot, 'overshoot_medio_pct': overshoot_medio}
    except Exception:
        return None
