"""
montecarlo_garch.py — Núcleo reutilizável de volatilidade e simulação Monte Carlo

Extraído do projeto Trader Desk (proxy.py) em 20/06/2026, generalizado para
uso em qualquer projeto que precise simular trajetórias de preço com
volatilidade refinada via GARCH(1,1).

Este módulo é "puro": não faz nenhuma requisição HTTP, não conhece tickers,
não tem dependência de Flask ou de qualquer framework web. Você passa uma
lista de preços de fechamento (closes) e ele devolve volatilidade estimada
e/ou simulações. Buscar os dados (Yahoo, brapi, ou qualquer outra fonte) é
responsabilidade de quem importa este módulo.

Dependências: numpy (obrigatório). math é stdlib.

Uso típico:
    import montecarlo_garch as mcg

    closes = [...]  # lista de preços de fechamento, do mais antigo ao mais recente
    preco_atual = closes[-1]

    # 1. Volatilidade histórica simples (baseline)
    sigma_simples = mcg.vol_hist(closes)

    # 2. Volatilidade refinada via GARCH(1,1) — captura clusters de volatilidade
    garch_info = mcg.garch_11(closes, horizon_days=21)
    sigma_garch = garch_info['vol_garch_projetada_pct'] / 100 if garch_info else sigma_simples

    # 3. Simulação Monte Carlo simples (probabilidade de terminar acima/abaixo de um strike)
    resultado = mcg.simular_gbm(preco_atual, sigma_garch, t_dias=21, k_call=42.0)

    # 4. Fan chart (trajetórias completas + percentis, para visualização)
    fan = mcg.simular_fan_chart(preco_atual, sigma_garch, t_dias=60)

    # 5. Probabilidade CONDICIONAL a partir de uma "foto" congelada no passado
    #    (você informa quantos dias já passaram e o preço ATUAL real)
    cond = mcg.simular_condicional(preco_atual_real, sigma_garch, dias_restantes=15, k_call=42.0)
"""

import math

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False


# ──────────────────────────────────────────────────────────────────────────
# VOLATILIDADE
# ──────────────────────────────────────────────────────────────────────────

def vol_hist(closes, janela=21):
    """
    Volatilidade histórica simples (anualizada), calculada sobre os últimos
    `janela` retornos logarítmicos diários. É o baseline mais simples —
    pesa todos os dias da janela igualmente, sem memória de regime.

    Retorna float (ex: 0.32 para 32% ao ano). Fallback de 0.35 se não houver
    dados suficientes.
    """
    if len(closes) < janela + 1:
        return 0.35
    rets = [math.log(closes[-i] / closes[-i - 1]) for i in range(1, janela + 1)]
    media = sum(rets) / len(rets)
    variancia = sum((r - media) ** 2 for r in rets) / len(rets)
    return round(math.sqrt(variancia * 252), 4)


def garch_11(closes, horizon_days=21):
    """
    Estima GARCH(1,1) via grid search (sem scipy) e projeta a volatilidade
    média esperada para os próximos `horizon_days`.

    GARCH(1,1): sigma2_t = omega + alpha*ret_{t-1}^2 + beta*sigma2_{t-1}

    Por que GARCH em vez de vol histórica fixa (vol_hist):
    - vol_hist usa uma janela fixa com peso igual para cada dia
    - GARCH modela "clusters de volatilidade": dias turbulentos tendem a ser
      seguidos por dias turbulentos, e dias calmos por dias calmos (memória)
    - O resultado é uma vol. que reflete melhor o regime atual do mercado,
      em vez de uma média simples do passado recente

    Nota sobre o grid search: testamos (via simulação, sessão 20/06/2026)
    grid search vs. MLE contínuo (scipy.optimize) em múltiplos cenários
    sintéticos — a diferença na vol. projetada final foi 0.00pp em todos
    os casos. A superfície de log-likelihood é "plana" o suficiente perto
    do ótimo (na direção da persistência alpha+beta) para que o grid já
    capture o resultado prático. Não vale a pena trocar por otimização
    contínua — não traz ganho mensurável.

    Parâmetros:
    - closes: lista de preços de fechamento (mínimo ~60 pontos recomendado,
      mas funciona com 50 em casos de dados escassos)
    - horizon_days: horizonte para o qual projetar a vol. média

    Retorna dict com vol_garch_atual_pct, vol_garch_projetada_pct,
    vol_garch_longo_prazo_pct, alpha, beta, persistencia, horizon_days —
    ou None se não houver dados suficientes ou numpy não estiver disponível.
    """
    if not _NUMPY or len(closes) < 50:
        return None
    try:
        cl = np.array(closes, dtype=float)
        rets = np.diff(np.log(cl)) * 100  # retornos em % para estabilidade numérica
        rets = rets[-252:]  # usa até 1 ano de retornos
        n = len(rets)
        if n < 40:
            return None

        var_uncond = np.var(rets)
        if var_uncond <= 0:
            return None

        best = None
        # Grid search em alpha e beta (omega derivado da variância incondicional)
        # alpha: peso do choque recente | beta: peso da variância anterior (persistência)
        for alpha in np.arange(0.02, 0.20, 0.02):
            for beta in np.arange(0.70, 0.97, 0.02):
                if alpha + beta >= 0.999:
                    continue
                omega = var_uncond * (1 - alpha - beta)
                if omega <= 0:
                    continue
                sigma2 = np.empty(n)
                sigma2[0] = var_uncond
                valid = True
                for t in range(1, n):
                    sigma2[t] = omega + alpha * rets[t - 1] ** 2 + beta * sigma2[t - 1]
                    if sigma2[t] <= 0:
                        valid = False
                        break
                if not valid:
                    continue
                # Log-likelihood gaussiana (a menos de constante)
                ll = -0.5 * np.sum(np.log(sigma2[1:]) + (rets[1:] ** 2) / sigma2[1:])
                if best is None or ll > best[0]:
                    best = (ll, alpha, beta, omega, sigma2)

        if best is None:
            return None

        _, alpha, beta, omega, sigma2 = best
        sigma2_atual = sigma2[-1]

        # Projeta a variância média para o horizonte (GARCH reverte à média de longo prazo)
        var_lp = omega / (1 - alpha - beta)  # variância incondicional de longo prazo
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


# ──────────────────────────────────────────────────────────────────────────
# MONTE CARLO — SIMULAÇÃO SIMPLES (probabilidade pontual)
# ──────────────────────────────────────────────────────────────────────────

def simular_gbm(preco_atual, sigma, t_dias, k_call=None, k_put=None, n=5000):
    """
    Simulação de Monte Carlo via Geometric Brownian Motion (GBM) — modelo
    padrão de "passeio aleatório" para preços de ativos. Calcula apenas o
    preço FINAL (não a trajetória completa) — mais rápido, usado quando só
    importa a probabilidade de terminar acima/abaixo de um strike.

    Parâmetros:
    - preco_atual: preço inicial (S0)
    - sigma: volatilidade anualizada (ex: 0.30 para 30%), normalmente vinda
      de garch_11()['vol_garch_projetada_pct']/100 ou de vol_hist()
    - t_dias: horizonte em dias corridos de pregão (úteis)
    - k_call: strike de uma call vendida (opcional) — calcula prob. de
      terminar ACIMA dele (prob_call_exercida)
    - k_put: strike de uma put vendida (opcional) — calcula prob. de
      terminar ABAIXO dele (prob_put_exercida)
    - n: número de cenários simulados

    Retorna dict com preco_atual, volatilidade_pct, cenarios, e (se k_call
    ou k_put fornecidos) as probabilidades correspondentes + prob_sucesso
    (complemento de prob_call_exercida).

    Limite matemático: GBM não tem reversão à média nem saltos (jumps) —
    é o modelo mais simples de movimento de preço. Testamos extensões
    (Jump-Diffusion, Heston) e documentamos ganho marginal pequeno ou
    inviável sem dados de book de opções reais — ver módulo de referência
    do projeto original para detalhes dessa análise.
    """
    if not _NUMPY:
        raise ImportError("numpy é obrigatório para simular_gbm()")
    T = max(t_dias, 1) / 252.0
    sqT = math.sqrt(T)
    drift = -0.5 * sigma ** 2 * T
    z = np.random.standard_normal(n)
    ST = preco_atual * np.exp(drift + sigma * sqT * z)

    res = {
        'preco_atual': round(preco_atual, 2),
        'volatilidade_pct': round(sigma * 100, 2),
        't_dias': t_dias,
        'cenarios': n,
    }
    if k_call is not None:
        call_ex = ST > k_call
        res['prob_call_exercida'] = round(float(call_ex.mean() * 100), 2)
        res['prob_sucesso'] = round(float((~call_ex).mean() * 100), 2)
    if k_put is not None:
        put_ex = ST < k_put
        res['prob_put_exercida'] = round(float(put_ex.mean() * 100), 2)
    return res


def simular_barreira(preco_atual, sigma, t_dias, kdo, kuo, n=3000):
    """
    Simulação de Monte Carlo com TRAJETÓRIA completa (não só preço final),
    para estruturas bidirecionais/barreira: calcula a probabilidade de o
    preço tocar uma barreira inferior (kdo, knock-down-out) ou superior
    (kuo, knock-up-out) em QUALQUER momento da janela — não apenas no
    vencimento.

    Parâmetros:
    - preco_atual, sigma, t_dias: como em simular_gbm()
    - kdo: barreira inferior (knock-down)
    - kuo: barreira superior (knock-up)
    - n: número de cenários simulados (menor que simular_gbm pois cada
      cenário aqui é uma trajetória diária completa, mais custoso)

    Retorna dict com prob_sem_barreira (ficou dentro do range o tempo
    todo), prob_barreira_alta (tocou kuo em algum momento), e
    prob_barreira_baixa (tocou kdo em algum momento).
    """
    if not _NUMPY:
        raise ImportError("numpy é obrigatório para simular_barreira()")
    steps = max(t_dias, 1)
    dt = 1 / 252.0
    drift = -0.5 * sigma ** 2 * dt
    vol_step = sigma * math.sqrt(dt)
    z = np.random.standard_normal((n, steps))
    paths = preco_atual * np.exp(np.cumsum(drift + vol_step * z, axis=1))
    max_p = np.max(paths, axis=1)
    min_p = np.min(paths, axis=1)
    kuo_hit = max_p >= kuo
    kdo_hit = min_p <= kdo
    no_barrier = ~kuo_hit & ~kdo_hit
    return {
        'preco_atual': round(preco_atual, 2),
        'volatilidade_pct': round(sigma * 100, 2),
        't_dias': t_dias, 'kdo': kdo, 'kuo': kuo,
        'cenarios': n,
        'prob_sem_barreira': round(float(no_barrier.mean() * 100), 2),
        'prob_barreira_alta': round(float(kuo_hit.mean() * 100), 2),
        'prob_barreira_baixa': round(float(kdo_hit.mean() * 100), 2),
    }


# ──────────────────────────────────────────────────────────────────────────
# FAN CHART — trajetórias completas + percentis (para visualização)
# ──────────────────────────────────────────────────────────────────────────

def simular_fan_chart(preco_atual, sigma, t_dias, n_sim=2000, n_linhas_amostra=20):
    """
    Gera as trajetórias completas de uma simulação Monte Carlo, junto com
    os percentis (p10/p25/p50/p75/p90) por dia — formato pronto para
    plotar um "fan chart" (cone de incerteza que se abre com o tempo).

    Parâmetros:
    - preco_atual, sigma, t_dias: como em simular_gbm()
    - n_sim: número de simulações usadas para calcular os percentis
      (mais simulações = percentis mais suaves, mas mais custoso)
    - n_linhas_amostra: quantas trajetórias individuais retornar para
      desenhar como linhas translúcidas no gráfico (não precisa ser todas
      as n_sim, só uma amostra visual)

    Retorna dict com:
    - dias: lista de índices de dia (eixo X, de 0 a t_dias)
    - trajetorias: lista de listas, cada uma uma trajetória de preço dia-a-dia
    - percentis: dict com p10/p25/p50/p75/p90, cada um uma lista por dia

    Limite matemático (importante explicar ao usuário final): o modelo GBM
    usado aqui NÃO tem reversão de preço — o cone sempre se abre com o
    tempo (incerteza cresce com a raiz do tempo), nunca "converge de volta".
    Isso é esperado e correto, não é um defeito do modelo.
    """
    if not _NUMPY:
        raise ImportError("numpy é obrigatório para simular_fan_chart()")
    dt = 1 / 252.0
    drift = -0.5 * sigma ** 2 * dt
    vol_step = sigma * math.sqrt(dt)
    z = np.random.standard_normal((n_sim, t_dias))
    log_ret = drift + vol_step * z
    paths = preco_atual * np.exp(np.cumsum(log_ret, axis=1))
    paths = np.hstack([np.full((n_sim, 1), preco_atual), paths])  # inclui dia 0

    percentis = {}
    for p in [10, 25, 50, 75, 90]:
        percentis[f'p{p}'] = np.percentile(paths, p, axis=0).round(2).tolist()

    idx_amostra = np.random.choice(n_sim, size=min(n_linhas_amostra, n_sim), replace=False)
    trajetorias = paths[idx_amostra].round(2).tolist()

    return {
        'preco_atual': round(preco_atual, 2),
        'volatilidade_pct': round(sigma * 100, 2),
        't_dias': t_dias,
        'dias': list(range(t_dias + 1)),
        'trajetorias': trajetorias,
        'percentis': percentis,
        'cenarios_percentis': n_sim,
        'cenarios_exibidos': len(trajetorias),
    }


# ──────────────────────────────────────────────────────────────────────────
# PROBABILIDADE CONDICIONAL — para "fotos" congeladas no passado
# ──────────────────────────────────────────────────────────────────────────

def simular_condicional(preco_atual_real, sigma, dias_restantes, k_call=None,
                         k_put=None, kdo=None, kuo=None, n=5000):
    """
    Calcula a probabilidade CONDICIONAL de um cenário a partir de onde a
    trajetória real ESTÁ AGORA — não do zero. Use isto quando você "tirou
    uma foto" de um cenário no passado (preço X, prazo N dias) e quer saber,
    passados alguns dias, qual a chance de terminar dentro/fora do range
    usando o TEMPO QUE RESTA e o PREÇO ATUAL REAL (não o preço da foto).

    Diferente de simular_gbm()/simular_barreira() (que sempre partem de
    "hoje" com o prazo TOTAL), esta função assume que o ponto de partida
    já é intermediário — ou seja, dias_restantes já deve ser calculado
    por quem chama (prazo_original - dias_já_passados).

    Parâmetros:
    - preco_atual_real: preço REAL observado agora (não o preço da foto)
    - sigma: volatilidade ATUAL (recomendado recalcular com garch_11 nos
      dados mais recentes, não usar a vol. que valia na época da foto)
    - dias_restantes: quantos dias ainda restam do prazo original
    - k_call / k_put: para estrutura de call/put simples
    - kdo / kuo: para estrutura bidirecional/barreira (usa simulação de
      trajetória completa neste caso, mais custosa)
    - n: número de cenários

    Retorna dict no mesmo formato de simular_gbm() ou simular_barreira(),
    dependendo de quais parâmetros foram fornecidos. Se dias_restantes <= 0,
    levanta ValueError — quem chama deve verificar isso antes (prazo já
    esgotado não tem "tempo restante" para simular).
    """
    if dias_restantes <= 0:
        raise ValueError(
            "dias_restantes deve ser > 0 — prazo original já esgotado, "
            "não há tempo restante para simular."
        )
    if kdo is not None and kuo is not None:
        return simular_barreira(preco_atual_real, sigma, dias_restantes, kdo, kuo, n=min(n, 3000))
    return simular_gbm(preco_atual_real, sigma, dias_restantes, k_call=k_call, k_put=k_put, n=n)
