"""Jump-Diffusion (Merton) em modo SOMBRA -- backlog #3 (08/10/2026).

Nao substitui o motor GBM: calcula uma segunda probabilidade, com saltos,
para comparar lado a lado. A variancia TOTAL e mantida igual a do motor
(sigma do app); o que muda e a forma: parte dela vira saltos raros e
grandes (gaps de resultado, noticia), o resto fica difusao. Assim a
diferenca entre as duas probabilidades mede so o efeito dos saltos.
"""
import math
import numpy as np


def estimar_saltos(closes, k=4.0):
    """Detecta saltos por MAD robusto nos retornos log diarios.
    Retorna dict lam (saltos/ano), mu_j, sig_j, n_saltos, sigma_hist (anual)."""
    c = np.asarray([x for x in closes if x and x > 0], dtype=float)
    if len(c) < 120:
        return None
    r = np.diff(np.log(c))
    med = np.median(r)
    mad = np.median(np.abs(r - med)) * 1.4826
    if mad <= 0:
        return None
    m = np.abs(r - med) > k * mad
    n = int(m.sum())
    anos = len(r) / 252.0
    out = {'n_saltos': n, 'lam': n / anos, 'sigma_hist': float(r.std() * math.sqrt(252)),
           'mu_j': float(r[m].mean()) if n else 0.0,
           'sig_j': float(r[m].std()) if n > 1 else (abs(float(r[m][0])) if n == 1 else 0.0)}
    return out


def prob_nao_tocar_jd(S, sigma, dias, barreira, saltos, n_sim=40000, tipo='baixo', seed=None):
    """Prob. de NAO tocar a barreira em `dias` corridos (dt=1/365, ajuste BGK).
    tipo 'baixo' = KDO, 'alto' = KUO. Sem saltos detectados -> GBM puro."""
    rng = np.random.default_rng(seed)
    dt = 1 / 365.0
    n = int(dias)
    lam = saltos['lam'] if saltos else 0.0
    if saltos and saltos['sigma_hist'] > 0:
        esc = sigma / saltos['sigma_hist']
        mu_j, sig_j = saltos['mu_j'] * esc, saltos['sig_j'] * esc
    else:
        mu_j = sig_j = 0.0
    var_salto = lam * (mu_j ** 2 + sig_j ** 2)
    sig_d2 = max(sigma ** 2 - var_salto, 0.3 * sigma ** 2)
    sig_d = math.sqrt(sig_d2)
    kappa = math.exp(mu_j + 0.5 * sig_j ** 2) - 1
    drift = (-0.5 * sig_d2 - lam * kappa) * dt
    inc = drift + sig_d * math.sqrt(dt) * rng.standard_normal((n_sim, n))
    if lam > 0:
        N = rng.poisson(lam * dt, (n_sim, n))
        inc += N * mu_j + np.sqrt(N) * sig_j * rng.standard_normal((n_sim, n))
    paths = S * np.exp(np.cumsum(inc, axis=1))
    aj = math.exp(0.5826 * sig_d * math.sqrt(dt))
    if tipo == 'baixo':
        return float((paths.min(axis=1) > barreira * aj).mean() * 100)
    return float((paths.max(axis=1) < barreira / aj).mean() * 100)


def caminhos_jd(S, sigma, dias, saltos, n_sim=20000, seed=None):
    """Caminhos diarios (dt=1/365) com saltos de Merton, variancia total = sigma^2.
    Retorna (paths, sigma_difusao) -- sigma_difusao serve ao ajuste de barreira."""
    rng = np.random.default_rng(seed)
    dt = 1 / 365.0
    n = int(dias)
    lam = saltos['lam'] if saltos else 0.0
    if saltos and saltos['sigma_hist'] > 0:
        esc = sigma / saltos['sigma_hist']
        mu_j, sig_j = saltos['mu_j'] * esc, saltos['sig_j'] * esc
    else:
        mu_j = sig_j = 0.0
    sig_d2 = max(sigma ** 2 - lam * (mu_j ** 2 + sig_j ** 2), 0.3 * sigma ** 2)
    kappa = math.exp(mu_j + 0.5 * sig_j ** 2) - 1
    inc = (-0.5 * sig_d2 - lam * kappa) * dt + math.sqrt(sig_d2 * dt) * rng.standard_normal((n_sim, n))
    if lam > 0:
        N = rng.poisson(lam * dt, (n_sim, n))
        inc += N * mu_j + np.sqrt(N) * sig_j * rng.standard_normal((n_sim, n))
    return S * np.exp(np.cumsum(inc, axis=1)), math.sqrt(sig_d2)
