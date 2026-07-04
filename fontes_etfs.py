# fontes_etfs.py — Fontes de dados de ETFs do Trader Desk
#
# Extraido do proxy.py em 03/07/2026 (Prioridade 2 da modularizacao,
# fase 2 de 4-5; fase 1 foi motor.py). Contem o universo fechado de 61
# ETFs e todo o cluster de busca/scraping de dados: parsing numerico
# BR, scraping HTML do investidor10 (preco/var/cap/DY), e busca de DY
# estruturado via Yahoo Finance (que substituiu o parsing fragil de
# coluna apos o bug do DY absurdo reportado em 03/07/2026).
#
# proxy.py importa daqui: ETF_UNIVERSO, _ETF_TICKERS_TODOS,
# _parse_num_br, _extrair_linhas_tabela, _dy_plausivel,
# _scrape_investidor10_etfs_nacional, _scrape_investidor10_etfs_americano,
# _fetch_dy_yahoo, _fetch_etfs_dy_yahoo_bulk, _etf_yahoo_ticker,
# _fetch_yahoo_series.
#
# O que NAO esta aqui (fica em proxy.py, e "cola" de rota, nao fonte de
# dado pura): _cache_etfs_live, _fetch_etfs_live, _refresh_dy_yahoo_
# background, e todas as rotas @app.route -- essas dependem de estado
# compartilhado (o cache) e do ciclo de vida da requisicao Flask.

import re
import html as _html_mod
import requests
from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait
from datetime import datetime as _dt_ys


# ── UNIVERSO FECHADO DE ETFS ───────────────────────────
ETF_UNIVERSO = [
    {'ticker':'COIN11','mercado':'Nacional','categoria':'Pagador','desc':'Bitcoin high income','risco':1},
    {'ticker':'SPYI11','mercado':'Nacional','categoria':'Pagador','desc':'S&P 500 EUA high income','risco':8},
    {'ticker':'QQQI11','mercado':'Nacional','categoria':'Pagador','desc':'Nasdaq-100 high income','risco':8},
    {'ticker':'DIVD11','mercado':'Nacional','categoria':'Pagador','desc':'IDIV - dividendos B3','risco':6},
    {'ticker':'NDIV11','mercado':'Nacional','categoria':'Pagador','desc':'Ibovespa Smart Dividendos','risco':6},
    {'ticker':'BOVA11','mercado':'Nacional','categoria':'Índice Brasil','desc':'Ibovespa','risco':4},
    {'ticker':'BOVV11','mercado':'Nacional','categoria':'Índice Brasil','desc':'Ibovespa (IT Now)','risco':4},
    {'ticker':'SMAL11','mercado':'Nacional','categoria':'Índice Brasil','desc':'Small Caps','risco':3},
    {'ticker':'PIBB11','mercado':'Nacional','categoria':'Índice Brasil','desc':'IBrX-50','risco':4},
    {'ticker':'IVVB11','mercado':'Nacional','categoria':'Americano','desc':'S&P 500 (BDR)','risco':4},
    {'ticker':'NASD11','mercado':'Nacional','categoria':'Americano','desc':'Nasdaq-100 (BDR)','risco':4},
    {'ticker':'SPXR11','mercado':'Nacional','categoria':'Americano','desc':'S&P 500 Futures BRL','risco':4},
    {'ticker':'SPXH11','mercado':'Nacional','categoria':'Americano','desc':'S&P 500 (hedge cambial)','risco':4},
    {'ticker':'TECK11','mercado':'Nacional','categoria':'Americano','desc':'Tecnologia (Brasil/América)','risco':2},
    {'ticker':'LFTB11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro Selic','risco':10},
    {'ticker':'LFTS11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro Selic','risco':10},
    {'ticker':'LFTI11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro Selic','risco':10},
    {'ticker':'LLFT11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro Selic','risco':10},
    {'ticker':'IMAB11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro IPCA+ (IMA-B)','risco':9},
    {'ticker':'IRFM11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro Prefixado','risco':10},
    {'ticker':'B5P211','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro IPCA+ 2 anos','risco':9},
    {'ticker':'B5MB11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro/crédito','risco':10},
    {'ticker':'IB5M11','mercado':'Nacional','categoria':'Renda Fixa','desc':'Tesouro','risco':10},
    {'ticker':'HASH11','mercado':'Nacional','categoria':'Cripto','desc':'Cesta cripto (Nasdaq Crypto Index)','risco':1},
    {'ticker':'QBTC11','mercado':'Nacional','categoria':'Cripto','desc':'Bitcoin','risco':1},
    {'ticker':'BITI11','mercado':'Nacional','categoria':'Cripto','desc':'Bitcoin','risco':1},
    {'ticker':'BITH11','mercado':'Nacional','categoria':'Cripto','desc':'Bitcoin (hedge)','risco':1},
    {'ticker':'ETHE11','mercado':'Nacional','categoria':'Cripto','desc':'Ethereum','risco':1},
    {'ticker':'GOLD11','mercado':'Nacional','categoria':'Ouro/Commodities','desc':'Ouro (LBMA)','risco':7},
    {'ticker':'MARG11','mercado':'Nacional','categoria':'Ouro/Commodities','desc':'Commodities/margem','risco':7},
    {'ticker':'DOLA11','mercado':'Nacional','categoria':'Câmbio','desc':'Dólar','risco':7},
    {'ticker':'WRLD11','mercado':'Nacional','categoria':'Internacional','desc':'Global All Cap (mundo todo)','risco':4},
    {'ticker':'XINA11','mercado':'Nacional','categoria':'Internacional','desc':'China','risco':4},
    {'ticker':'USAL11','mercado':'Nacional','categoria':'Internacional','desc':'EUA amplo','risco':4},
    {'ticker':'PACG11','mercado':'Nacional','categoria':'Internacional','desc':'Ásia-Pacífico','risco':4},
    {'ticker':'VOO','mercado':'Americano','categoria':'Índice amplo','desc':'S&P 500','risco':4},
    {'ticker':'VTI','mercado':'Americano','categoria':'Índice amplo','desc':'Total Stock Market EUA','risco':4},
    {'ticker':'QQQ','mercado':'Americano','categoria':'Índice amplo','desc':'Nasdaq-100','risco':4},
    {'ticker':'JEPI','mercado':'Americano','categoria':'High income','desc':'S&P 500 high income','risco':8},
    {'ticker':'JEPQ','mercado':'Americano','categoria':'High income','desc':'Nasdaq high income','risco':8},
    {'ticker':'VT','mercado':'Americano','categoria':'Internacional','desc':'Total World (global)','risco':4},
    {'ticker':'VUG','mercado':'Americano','categoria':'Índice amplo','desc':'Growth (crescimento)','risco':4},
    {'ticker':'VTV','mercado':'Americano','categoria':'Dividendo/Value','desc':'Value (valor)','risco':6},
    {'ticker':'SCHD','mercado':'Americano','categoria':'Dividendo/Value','desc':'Dividend Equity','risco':6},
    {'ticker':'VGT','mercado':'Americano','categoria':'Setorial','desc':'Tecnologia (setor)','risco':2},
    {'ticker':'SMH','mercado':'Americano','categoria':'Setorial','desc':'Semicondutores','risco':2},
    {'ticker':'VEA','mercado':'Americano','categoria':'Internacional','desc':'Mercados desenvolvidos ex-EUA','risco':4},
    {'ticker':'VWO','mercado':'Americano','categoria':'Internacional','desc':'Mercados emergentes','risco':4},
    {'ticker':'IJR','mercado':'Americano','categoria':'Small/Mid cap','desc':'Small Cap','risco':3},
    {'ticker':'IJH','mercado':'Americano','categoria':'Small/Mid cap','desc':'Mid Cap','risco':3},
    {'ticker':'GLD','mercado':'Americano','categoria':'Ouro/Commodities','desc':'Ouro','risco':7},
    {'ticker':'SLV','mercado':'Americano','categoria':'Ouro/Commodities','desc':'Prata','risco':7},
    {'ticker':'IBIT','mercado':'Americano','categoria':'Cripto','desc':'Bitcoin','risco':1},
    {'ticker':'VNQ','mercado':'Americano','categoria':'Real Estate','desc':'REITs EUA','risco':5},
    {'ticker':'BND','mercado':'Americano','categoria':'Renda Fixa','desc':'Bond total EUA','risco':10},
    {'ticker':'SGOV','mercado':'Americano','categoria':'Renda Fixa','desc':'Treasury curtíssimo','risco':10},
    {'ticker':'TLT','mercado':'Americano','categoria':'Renda Fixa','desc':'Treasury longo (20+ anos)','risco':9},
    {'ticker':'JPST','mercado':'Americano','categoria':'Renda Fixa','desc':'Ultra-short income','risco':10},
    {'ticker':'XLE','mercado':'Americano','categoria':'Setorial','desc':'Energia','risco':2},
    {'ticker':'EWJ','mercado':'Americano','categoria':'Internacional','desc':'Japão','risco':4},
    {'ticker':'EWY','mercado':'Americano','categoria':'Internacional','desc':'Coreia do Sul','risco':4},
]
_ETF_TICKERS_TODOS = {e['ticker'] for e in ETF_UNIVERSO}


# ── PARSING NUMERICO BR / HTML ────────────────────────
def _parse_num_br(txt):
    if not txt: return None
    txt = txt.strip()
    if txt in ('-', '', '—', 'N/A'): return None
    mult = 1.0
    if 'T' in txt.upper(): mult = 1000000.0
    elif 'B' in txt.upper(): mult = 1000.0
    txt = re.sub(r'[^0-9,.\-]', '', txt)
    txt = txt.replace('.', '').replace(',', '.')
    try:
        return round(float(txt) * mult, 2)
    except Exception:
        return None

def _deduplicar_celulas(textos):
    """
    04/07/2026: Victor rodou o diagnostico /etfs/live-status em producao
    e revelou a causa raiz REAL do "DY absurdo" desde o inicio -- nao era
    mapeamento de coluna nem header duplo, era CELULA duplicada: o
    investidor10 esta renderizando cada <td> duas vezes seguidas na
    mesma linha (['R$ 437,18','R$ 437,18', '15,27%','15,27%', ...]),
    provavelmente uma versao responsiva/mobile duplicada no mesmo HTML.
    Isso desalinhava QUALQUER indice fixo: a coluna 5 (onde eu esperava
    DY) na verdade pegava a segunda copia da Variacao 24m, que pode ser
    um numero grande de verdade para fundos alavancados -- exatamente o
    "BOVA11 com 10000%" que Victor reportou. Colapsa pares consecutivos
    idênticos (preserva o texto do ticker/nome na posicao 0 sempre).
    """
    if len(textos) < 2:
        return textos
    out = [textos[0]]
    i = 1
    while i < len(textos):
        if i + 1 < len(textos) and textos[i] == textos[i + 1]:
            out.append(textos[i])
            i += 2
        else:
            out.append(textos[i])
            i += 1
    return out

def _extrair_linhas_tabela(html_txt):
    linhas_out = []
    linhas_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', html_txt, re.S)
    for linha in linhas_raw:
        celulas = re.findall(r'<td[^>]*>(.*?)</td>', linha, re.S)
        if not celulas:
            continue
        textos = []
        for c in celulas:
            limpo = re.sub(r'<[^>]+>', ' ', c)
            limpo = _html_mod.unescape(limpo)
            limpo = re.sub(r'\s+', ' ', limpo).strip()
            textos.append(limpo)
        linhas_out.append(_deduplicar_celulas(textos))
    return linhas_out

def _dy_plausivel(v):
    """
    Trava de sanidade (03/07/2026) apos Victor reportar DY absurdo nos
    ETFs (ex: BOVA11 mostrando 10000%/3300%, sendo que BOVA11 nao paga
    dividendo). Nenhum ETF do nosso universo real (ETF_UNIVERSO) chega
    perto de 100% de DY anual -- os "high income" mais agressivos
    (COIN11/SPYI11/QQQI11/JEPI/JEPQ) ficam na faixa de 7-50%. Qualquer
    valor fora de [0, 100] e quase certamente coluna errada (ex: pegou
    Capitalizacao em vez de Dividend Yield) -- melhor mostrar "-"
    (None) do que um numero fisicamente implausivel.
    """
    return v is not None and 0 <= v <= 100


# ── SCRAPING INVESTIDOR10 (preco/var/cap/DY, fallback) ─
def _scrape_investidor10_etfs_nacional(paginas):
    """Colunas Nacionais: col0='#N TICKER Nome...', 1=preco, 2=var12m,
    3=var24m, 4=cap, 5=dy. Indices fixos (tentativa de mapeamento dinamico
    por header foi revertida em 03/07/2026 -- pagina tem mais de uma
    tabela/thead, header lido nao correspondia as linhas de dados,
    causando desalinhamento pior que o indice fixo). DY passa por
    _dy_plausivel como trava de sanidade final."""
    resultado = {}
    for pagina in range(1, paginas + 1):
        try:
            url = f'https://investidor10.com.br/etfs?page={pagina}'
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)  # era 15s; 5 paginas x 15s = ate 75s segurando o unico worker do Render (03/07/2026)
            if not r.ok:
                continue
            linhas = _extrair_linhas_tabela(r.text)
            for textos in linhas:
                if len(textos) < 6:
                    continue
                m = re.match(r'#?\d*\s*([A-Z0-9]{2,7})\s+(.*)', textos[0])
                if not m:
                    continue
                ticker = m.group(1).upper()
                if ticker not in _ETF_TICKERS_TODOS:
                    continue
                dy = _parse_num_br(textos[5])
                resultado[ticker] = {
                    'preco': _parse_num_br(textos[1]),
                    'var_12m': _parse_num_br(textos[2]),
                    'var_24m': _parse_num_br(textos[3]),
                    'cap': _parse_num_br(textos[4]),
                    'dy': dy if _dy_plausivel(dy) else None,
                }
        except Exception:
            continue
    return resultado

def _scrape_investidor10_etfs_americano(paginas):
    """Colunas Americanas (ordem DIFERENTE da Nacional, sem preco):
    col0='#N TICKER Nome...', 1=dy, 2=dy_medio5a, 3=cap, 4=var12m,
    5=var24m, 6=var5a, 7=var30d, 8=cotistas(sempre 0). Indices fixos
    (ver nota no scraper nacional sobre reversao do mapeamento por
    header em 03/07/2026). DY passa por _dy_plausivel."""
    resultado = {}
    for pagina in range(1, paginas + 1):
        try:
            url = f'https://investidor10.com.br/etfs-global/?order=vol&dir=desc&page={pagina}'
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)  # era 15s, ver nota no scraper nacional (03/07/2026)
            if not r.ok:
                continue
            linhas = _extrair_linhas_tabela(r.text)
            for textos in linhas:
                if len(textos) < 6:
                    continue
                m = re.match(r'#?\d*\s*([A-Z0-9]{2,7})\s+(.*)', textos[0])
                if not m:
                    continue
                ticker = m.group(1).upper()
                if ticker not in _ETF_TICKERS_TODOS:
                    continue
                dy = _parse_num_br(textos[1])
                resultado[ticker] = {
                    'preco': None,
                    'dy': dy if _dy_plausivel(dy) else None,
                    'cap': _parse_num_br(textos[3]),
                    'var_12m': _parse_num_br(textos[4]),
                    'var_24m': _parse_num_br(textos[5]),
                }
        except Exception:
            continue
    return resultado


# ── DY VIA YAHOO (fonte estruturada, primaria) ────────
def _fetch_dy_yahoo(yahoo_ticker):
    """
    DY via Yahoo Finance (modulo summaryDetail.dividendYield) -- JSON
    estruturado, mesmo dominio ja usado com sucesso no resto do app para
    preco/historico (query1/query2.finance.yahoo.com). Solucao adotada
    em 03/07/2026 para substituir o parsing por regex da tabela HTML do
    investidor10, que estava desalinhando o DY silenciosamente (Victor
    reportou BOVA11 com 10000%/3300%, sendo que BOVA11 nao paga
    dividendo). Fonte estruturada elimina essa classe de bug por
    completo -- nao depende de indice de coluna nenhum.
    """
    for host in ['query1', 'query2']:
        try:
            r = requests.get(
                f'https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{yahoo_ticker}?modules=summaryDetail',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            if not r.ok:
                continue
            d = r.json()
            res = (d.get('quoteSummary') or {}).get('result')
            if not res:
                continue
            sd = res[0].get('summaryDetail', {}) or {}
            dy_raw = (sd.get('dividendYield') or {}).get('raw')
            if dy_raw is not None:
                return round(float(dy_raw) * 100, 2)
        except Exception:
            continue
    return None

def _etf_yahoo_ticker(etf):
    """Nacional (B3) precisa do sufixo .SA no Yahoo; Americano vai puro."""
    return etf['ticker'] + '.SA' if etf.get('mercado') == 'Nacional' else etf['ticker']

def _fetch_etfs_dy_yahoo_bulk(etfs, timeout_total=9):
    """
    Busca DY de todos os ETFs via Yahoo em paralelo (ThreadPoolExecutor).
    CORRECAO CRITICA 03/07/2026: a primeira versao usava
    "with ThreadPoolExecutor(...) as ex: ex.map(...)" -- o `with` so
    libera a requisicao quando TODAS as ~61 threads terminam (mesmo com
    timeout de 8s por chamada individual, o pior caso e sequencial por
    causa de retries/hosts alternativos dentro de _fetch_dy_yahoo), o
    que estourou o timeout do Render e derrubou /etfs com 502. Agora usa
    ORCAMENTO DE TEMPO FIXO (~9s) via concurrent.futures.wait: o que
    responder a tempo entra no resultado, o resto e descartado sem
    bloquear a resposta -- e ex.shutdown(wait=False) para nao esperar as
    threads pendentes. O DY que faltar fica None nesse ciclo (cache de
    15min tenta de novo depois; investidor10 serve de fallback nesse
    meio tempo, ja filtrado por _dy_plausivel).
    """
    resultado = {}
    ex = ThreadPoolExecutor(max_workers=25)
    try:
        futuros = {ex.submit(_fetch_dy_yahoo, _etf_yahoo_ticker(etf)): etf['ticker'] for etf in etfs}
        prontos, pendentes = _cf_wait(list(futuros.keys()), timeout=timeout_total)
        for fut in prontos:
            ticker = futuros[fut]
            try:
                dy = fut.result()
                if _dy_plausivel(dy):
                    resultado[ticker] = dy
            except Exception:
                continue
    except Exception:
        pass
    finally:
        ex.shutdown(wait=False)
    return resultado

def _fetch_preco_yahoo(yahoo_ticker):
    """
    Preco mais recente via Yahoo (v8/finance/chart, range curto, ultimo
    close). Adicionado 04/07/2026 apos Victor reportar Carteira de ETFs
    com R$0,00 -- causa raiz: investidor10 vinha falhando para COIN11/
    SPYI11 desde 03/07/2026 (preco_entrada ja tinha sido salvo como null
    na epoca da compra), nao era so um problema de timeout de hoje.
    Mesmo padrao de robustez ja aplicado ao DY: Yahoo como fonte
    estruturada, investidor10 vira fallback tambem para preco.
    """
    for host in ['query1', 'query2']:
        try:
            r = requests.get(
                f'https://{host}.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1d&range=5d',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            if not r.ok:
                continue
            d = r.json()
            result = d['chart']['result'][0]
            closes = result['indicators']['quote'][0]['close']
            validos = [c for c in closes if c is not None]
            if validos:
                return round(float(validos[-1]), 2)
        except Exception:
            continue
    return None

def _fetch_etfs_preco_yahoo_bulk(etfs, timeout_total=9):
    """
    Preco de todos os ETFs via Yahoo em paralelo, mesmo padrao de
    orcamento de tempo fixo do _fetch_etfs_dy_yahoo_bulk (04/07/2026) --
    nao bloqueia a resposta, o que nao responder a tempo fica para o
    proximo ciclo de cache/refresh em background.
    """
    resultado = {}
    ex = ThreadPoolExecutor(max_workers=25)
    try:
        futuros = {ex.submit(_fetch_preco_yahoo, _etf_yahoo_ticker(etf)): etf['ticker'] for etf in etfs}
        prontos, pendentes = _cf_wait(list(futuros.keys()), timeout=timeout_total)
        for fut in prontos:
            ticker = futuros[fut]
            try:
                preco = fut.result()
                if preco is not None and preco > 0:
                    resultado[ticker] = preco
            except Exception:
                continue
    except Exception:
        pass
    finally:
        ex.shutdown(wait=False)
    return resultado

def _fetch_yahoo_series(ticker, range_hist='1y'):
    """
    Serie (data_str -> close) via Yahoo, para alinhar por data entre varios
    tickers (correlacao real da carteira de ETFs, item 2 do backlog
    03/07/2026). Fatorado de _obter_preco_sigma_garch pois aquela funcao
    so retorna a lista de closes sem as datas correspondentes.
    """
    for host in ['query1', 'query2']:
        try:
            r = requests.get(
                f'https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_hist}',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if not r.ok:
                continue
            d = r.json()
            result = d['chart']['result'][0]
            ts = result['timestamp']
            cl = result['indicators']['quote'][0]['close']
            out = {}
            for t, c in zip(ts, cl):
                if c is None:
                    continue
                dt = _dt_ys.utcfromtimestamp(t).strftime('%Y-%m-%d')
                out[dt] = float(c)
            if out:
                return out
        except Exception:
            continue
    return {}
