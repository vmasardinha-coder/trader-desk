# fontes.py — Fontes de dados gerais do Trader Desk (CDI, Yahoo, FIIs, etc)
#
# Extraido do proxy.py em 04/07/2026 (Prioridade 2 da modularizacao,
# fase 3 de 5; fase 1 foi motor.py, fase 2 foi fontes_etfs.py). Contem os
# ~15 fetches/scrapers restantes que nao dependem de Flask/estado de rota:
# CDI (Bacen), BTC onchain (Yahoo), fundamentais e cotacao via Yahoo,
# minerio de ferro (TradingView/TradingEconomics), marketcap via
# 8marketcap.com, e todo o cluster de FIIs (Fundamentus + classificacao de
# segmento/risco/score + FI-Infra + StatusInvest proventos/listagem).
#
# proxy.py importa daqui: get_cdi, get_btc_onchain, yahoo_fundamentals,
# yquote, scrape_iron_ore_investing, _8MARKETCAP_TICKER_ALT,
# _parsear_marketcap_8marketcap, _buscar_html_8marketcap_paginas,
# _FII_SEGMENTO_BASE, _FII_PALAVRAS_PAPEL, _FII_PALAVRAS_FOF,
# _classificar_segmento_fii, _classificar_risco_fii, _score_fii,
# _FII_PVP_MINIMO, _FII_TICKERS_INATIVOS, scrape_fiis_fundamentus,
# scrape_fi_infra_dados, scrape_statusinvest_ultimo_provento,
# scrape_statusinvest_historico_proventos, scrape_statusinvest_tickers_listagem,
# scrape_statusinvest_fundo_dados.
#
# O que NAO esta aqui (fica em proxy.py, e rota/estado, nao fonte pura):
# todas as @app.route, _fetch_closes_for_foto/_obter_preco_sigma_garch
# (ligadas ao ciclo de congelamento de bandas da foto, nao extraidas nesta
# fase), caches e tokens de ambiente (BRAPI_TOKEN etc).

import re
import requests
import time as _t
from motor import mm

# ── CDI ───────────────────────────────────────────────
def get_cdi():
    try:
        r = requests.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.4389/dados/ultimos/1?formato=json', timeout=5)
        if r.ok:
            # CORRIGIDO 07/08/2026 -- bug identificado pelo Victor: o app continuava
            # mostrando 14,25% um dia inteiro apos o Copom cortar para 14,00%
            # (05/08/2026). Causa raiz: a serie 4389 do Bacen ja vem ANUALIZADA
            # direto em % a.a. (confirmado testando a API ao vivo: retornou 13.90
            # e 14.15 nos dias 06/08 e 05/08, valores plausiveis de CDI anual --
            # nao taxas diarias). O codigo antigo aplicava
            # ((1+cdi_d/100)**252-1)*100 em cima disso, tratando um numero ja
            # anual como se fosse diario -- resultado virava ~10^16, sempre
            # rejeitado pelo sanity check (5<=x<=20), sempre caindo no fallback
            # hardcoded abaixo. Corrigido para usar o valor direto, sem composicao.
            cdi_anual = float(r.json()[0]['valor'])
            if 5 <= cdi_anual <= 25:
                return round(cdi_anual, 2)
    except: pass
    return 14.00  # SELIC meta COPOM 05/08/2026 (corte pra 14,00%; proxima reuniao: 16/09/2026)

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


def yquote(ticker, prefer_chart_prev=False):
    try:
        r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d',
            headers={'User-Agent':'Mozilla/5.0'},timeout=6)
        if not r.ok: return None
        d=r.json(); m=d['chart']['result'][0]['meta']
        raw_close=d['chart']['result'][0]['indicators']['quote'][0]['close']
        raw_ts=d['chart']['result'][0].get('timestamp',[])
        # pares (timestamp, close) so onde close existe -- preserva o alinhamento
        # entre os dois arrays em vez de filtrar cl sozinho (que quebrava a
        # correspondencia posicional quando havia None no meio, ex: feriado)
        pares=[(t,c) for t,c in zip(raw_ts,raw_close) if c is not None]
        cl=[c for t,c in pares]
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
        #
        # CORRIGIDO 04/08/2026 (v2 -- causa raiz de verdade): usuario
        # reportou Nikkei, KOSPI E DAX com variacao % errada em dias
        # diferentes/tentativas diferentes -- nao era 1 ticker especifico
        # nem cache (ja descartado). O bug real: `cl[-2]` assume que o
        # ULTIMO ponto do array (`cl[-1]`) e sempre "hoje". Isso so e
        # verdade se a sessao de hoje ja apareceu como candle no array.
        # Quando o usuario consulta com o mercado daquela bolsa ABERTO
        # (situacao normal dele: abre de manha e olha Europa/Asia ainda
        # em pregao), o candle de "hoje" pode nao existir ainda no range
        # de 5 dias -- nesse caso cl[-1] e na verdade ONTEM, e cl[-2] vira
        # ANTEONTEM, gerando uma variacao % de 2 dias em vez de 1. Fix:
        # comparar a DATA do ultimo timestamp da serie (no fuso GMT
        # correto via 'gmtoffset' do proprio Yahoo) com a data de hoje
        # nesse mesmo fuso -- se baterem, cl[-1] e mesmo hoje (ainda em
        # andamento) e cl[-2] e o fechamento de ontem, valido; se NAO
        # baterem, cl[-1] ja E o fechamento de ontem (nao existe candle de
        # hoje ainda) e deve ser usado como 'prev' diretamente, com 'p'
        # (regularMarketPrice, sempre ao vivo) fazendo o papel de "hoje".
        # CORRIGIDO 04/08/2026 (v3 -- fix da v2): usuario reportou ouro/prata/
        # cobre com variacao % errada de forma CONSISTENTE (nao ruido -- nem
        # moda de 3 amostras resolveu, o que descarta ruido aleatorio e aponta
        # pra um calculo sistematicamente errado). Causa provavel: a v2 abaixo
        # usa `m.get('gmtoffset', 0) or 0`, que cai silenciosamente para UTC
        # se o Yahoo nao mandar esse campo para o ticker -- possivel para
        # GC=F/SI=F/HG=F especificamente. Isso e perigoso porque esses
        # contratos tem pausa diaria de so 1h (17h-18h Chicago = ~22h-23h
        # UTC), bem perto da fronteira de meia-noite UTC -- se o calculo cai
        # em UTC errado, a comparacao de "e hoje ou nao" pode furar bem nessa
        # janela estreita e ficar ERRADA DE FORMA CONSISTENTE (nao aleatoria)
        # ate a proxima virada real de dia, explicando o "carrega certo,
        # atualiza, fica errado e estabiliza errado" relatado. Fix: só usar a
        # logica de comparacao de data quando o Yahoo realmente mandar
        # gmtoffset (não usar default 0) -- sem esse dado, nao da pra saber a
        # fronteira do dia com seguranca, entao volta ao cl[-2] simples (que
        # ja era validado para commodities antes da v2).
        v = None
        gmtoffset = m.get('gmtoffset')
        if gmtoffset is not None and len(pares) >= 1:
            ultimo_ts = pares[-1][0]
            hoje_bolsa = _t.gmtime(_t.time() + gmtoffset).tm_yday, _t.gmtime(_t.time() + gmtoffset).tm_year
            data_ultimo = _t.gmtime(ultimo_ts + gmtoffset).tm_yday, _t.gmtime(ultimo_ts + gmtoffset).tm_year
            if data_ultimo == hoje_bolsa:
                # candle mais recente E de hoje (mercado aberto, sessao em
                # andamento) -- cl[-2] e o fechamento de ontem, valido
                v = pares[-2][1] if len(pares) > 1 else m.get('chartPreviousClose', p)
            else:
                # nao ha candle de hoje ainda -- cl[-1] JA E o fechamento
                # de ontem (o mais recente disponivel)
                v = pares[-1][1]
        if v is None:
            # sem gmtoffset confiavel (ou array vazio) -- volta ao metodo
            # simples original (valido para commodities, testado e confirmado
            # correto para petroleo antes desta mudanca)
            v = cl[-2] if len(cl) > 1 else m.get('chartPreviousClose', p)
        if prefer_chart_prev and m.get('chartPreviousClose') is not None:
            v = m['chartPreviousClose']
        # Adicionado 04/08/2026 -- diagnostico de defasagem (usuario reportou
        # indices Europa/Asia parecendo desatualizados em Cotacoes). regularMarketTime
        # (epoch, timezone do Yahoo) permite comparar "quando o Yahoo diz que
        # atualizou" vs o horario real -- sem isso nao da pra distinguir "Yahoo
        # atrasado" de "nosso codigo com bug". Nao quebra nada que ja consome
        # yquote() -- e so um campo a mais no dict de retorno.
        return {'price':round(float(p),2),'prev':round(float(v),2),'time':m.get('regularMarketTime')}
    except: return None

# Adicionado 04/08/2026 (v2) -- fonte ALTERNATIVA para spot de ouro/prata/
# cobre, sugerida pelo usuario apos a 1a tentativa (gold_spot/silver_spot/
# copper_spot via Yahoo) ter voltado sempre vazia e a tentativa de paralelizar
# com ThreadPoolExecutor ter deixado o /futures mais lento (revertido no
# mesmo dia). Fonte nova: Hyperliquid (exchange descentralizada), mercados
# perpetuos HIP-3 do dex 'xyz' (operado pela TradeXYZ), com preco lastreado
# a oraculo benchmarked ao COMEX front-month -- ou seja, mesma referencia de
# mercado que o usuario ja acompanha externamente, so que via uma API
# publica sem autenticacao/rate-limit agressivo, em vez do Yahoo (que so
# tem futuro, sujeito a ruido de rolagem de contrato).
#
# UMA UNICA chamada POST (metaAndAssetCtxs) traz os 3 ativos de uma vez —
# sem ThreadPoolExecutor, licao aprendida do incidente do mesmo dia.
# Endpoint documentado: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals
# dex='xyz' confirmado por 3 fontes independentes (SDK oficial, quantpylib,
# Hyperliquid-Data-Layer-API) -- nao e chute.
#
# TESTADO 04/08/2026 (2a rodada) NO APP PUBLICADO: usuario reportou GOLD/
# SILVER/COPPER (SPOT) aparecendo vazios ("--") na tela, mesmo com FUT
# funcionando normal -- ou seja, a funcao esta caindo no except silenciosamente.
# Causas mais provaveis: (1) falta de User-Agent (Hyperliquid/Cloudflare pode
# bloquear requests sem cara de navegador, mesmo problema que o yquote() ja
# tinha pro Yahoo), (2) IP do Render bloqueado/rate-limited por ser
# datacenter. Adicionado User-Agent igual ao ja usado em yquote() (tentativa
# de correcao) + campo '_debug' no retorno (excecao/status real, nunca
# None/generico) para diagnosticar sem ficar chutando -- exposto
# TEMPORARIAMENTE em /futures como '_spot_debug', remover depois que
# resolver.
def fetch_commodities_hyperliquid():
    """Busca preco a vista (spot) de ouro/prata/cobre via mercados perpetuos
    HIP-3 da Hyperliquid (dex 'xyz'). Retorna dict com chaves
    'gold_spot'/'silver_spot'/'copper_spot' ({'price':float,'prev':float|None})
    e '_debug' (str ou None) com o motivo do erro se algo falhou -- NUNCA
    lanca excecao pro chamador, so degrada pra dict vazio + _debug preenchido."""
    try:
        r = requests.post(
            'https://api.hyperliquid.xyz/info',
            json={'type': 'metaAndAssetCtxs', 'dex': 'xyz'},
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
            timeout=6,
        )
        if not r.ok:
            return {'_debug': f'HTTP {r.status_code}: {r.text[:200]}'}
        payload = r.json()
        if not isinstance(payload, list) or len(payload) != 2:
            return {'_debug': f'formato inesperado (nao e [meta, ctxs]): {str(payload)[:200]}'}
        meta, ctxs = payload
        universe = meta.get('universe', [])
        # CORRIGIDO 04/08/2026 (3a rodada): diagnostico real mostrou que o
        # campo 'name' do universe JA VEM com o prefixo do dex embutido
        # ('xyz:GOLD', nao 'GOLD' puro) mesmo filtrando por dex='xyz' na
        # request -- diferente do que a documentacao/SDKs de terceiros
        # sugeriam (prefixo so apareceria ao misturar dexes). Normaliza
        # removendo qualquer prefixo 'algo:' antes de comparar.
        alvo_para_chave = {'GOLD': 'gold_spot', 'SILVER': 'silver_spot', 'COPPER': 'copper_spot'}
        nomes_encontrados = [a.get('name') for a in universe]
        out = {}
        for idx, ativo in enumerate(universe):
            nome_raw = ativo.get('name') or ''
            nome = nome_raw.split(':')[-1].upper()
            chave = alvo_para_chave.get(nome)
            if not chave or idx >= len(ctxs):
                continue
            ctx = ctxs[idx]
            preco_raw = ctx.get('markPx') or ctx.get('midPx')
            if preco_raw is None:
                continue
            try:
                preco = round(float(preco_raw), 2)
            except (TypeError, ValueError):
                continue
            prev_raw = ctx.get('prevDayPx')
            prev = None
            if prev_raw is not None:
                try:
                    prev = round(float(prev_raw), 2)
                except (TypeError, ValueError):
                    prev = None
            out[chave] = {'price': preco, 'prev': prev}
        faltando = [k for k in ('gold_spot', 'silver_spot', 'copper_spot') if k not in out]
        if faltando:
            # Busca por substring nos nomes completos, pra pegar variantes
            # tipo 'XAG'/'SI'/'CU' caso SILVER/COPPER nao existam com esse
            # nome exato no dex 'xyz' (ex: podem estar em outro dex HIP-3,
            # ou nao terem sido lancados ainda).
            pistas = [n for n in nomes_encontrados if n and any(
                s in n.upper() for s in ('SILV', 'COPP', 'XAG', 'XCU', ':CU', ':SI', ':HG')
            )]
            out['_debug'] = (
                f'faltando: {faltando} | total de ativos no universe: {len(universe)} | '
                f'possiveis variantes encontradas: {pistas} | primeiros 25 nomes: {nomes_encontrados[:25]}'
            )
        else:
            out['_debug'] = None
        return out
    except Exception as e:
        return {'_debug': f'{type(e).__name__}: {e}'}

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

_FII_TICKERS_INATIVOS = {
    'CBCV11',  # incorporado/renomeado -- reportado pelo usuario 01/07/2026,
               # aparecia no topo do ranking com dado cacheado do Fundamentus
               # mesmo ja nao sendo mais negociado sob esse ticker
}

# Adicionado 07/07/2026 -- guarda o ultimo diagnostico de descarte do
# scrape_fiis_fundamentus (quais tickers foram removidos e por qual
# motivo), consultavel via /fiis/diagnostico sem precisar re-rodar o scrape.
_FII_ULTIMO_DIAGNOSTICO = {}

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
        # ADICIONADO 07/07/2026 -- diagnostico real (nao so contagem): usuario
        # reportou KNCA11 (maior Fiagro do mercado, liquidez real excelente,
        # confirmado por pesquisa externa) sumindo do universo entre a
        # primeira chamada e a "atualizadinha". Sem rastrear POR TICKER qual
        # filtro descartou o que, e impossivel diagnosticar sem acesso ao
        # scrape ao vivo (que o Claude nao tem, sandbox nao acessa
        # fundamentus.com.br). Agora qualquer descarte fica registrado com
        # motivo, consultavel via /fiis/diagnostico.
        descartados_diagnostico = []
        for linha in linhas_raw:
            celulas = re.findall(r'<td[^>]*>(.*?)</td>', linha, re.DOTALL)
            # CORRIGIDO 25/06/2026: pagina real tem 14 colunas (a 14a e
            # "Endereco", que nao existia na referencia de scraping de 2023
            # usada para montar a especificacao original -- causa raiz real
            # do "0 FIIs encontrados" no primeiro teste em produção). Aceita
            # 13 OU 14 para tolerar se o site remover/adicionar essa coluna
            # de novo no futuro sem quebrar o parsing.
            if len(celulas) not in (13, 14):
                if celulas:
                    tk_aprox = re.sub(r'<[^>]+>', '', celulas[0]).strip()
                    if tk_aprox and re.match(r'^[A-Z0-9]+$', tk_aprox):
                        descartados_diagnostico.append({'ticker': tk_aprox, 'motivo': f'celulas_count_{len(celulas)}'})
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
            except (ValueError, IndexError) as e:
                descartados_diagnostico.append({'ticker': ticker, 'motivo': f'erro_parsing_{type(e).__name__}'})
                continue

        # ── Filtro automatico de "fantasma": liquidez zerada/nula = fundo
        # sem NENHUM negocio recente, sinal forte de ticker morto (fusao,
        # incorporacao, deslistagem) mesmo que o Fundamentus ainda exiba
        # cadastro/cotacao antiga em cache. Diferente de liquidez BAIXA
        # (fundo pequeno mas ativo, que continua no universo normalmente --
        # so entra como score baixo via _score_fii, nao e excluido aqui).
        # Adicionado 01/07/2026 junto com _FII_TICKERS_INATIVOS (que cobre
        # o caso raro de liquidez cacheada != 0 mesmo estando morto).
        #
        # CORRIGIDO 07/07/2026 -- usuario reportou KNCA11 (Fiagro gigante,
        # liquidez real excelente, confirmado por pesquisa externa) sumindo
        # do universo. Investigacao (busca direta na pagina real do
        # Fundamentus) confirmou: ~30% de TODOS os FIIs estavam com
        # liquidez=0 na fonte no momento -- incluindo fundos enormes e
        # conhecidos (BBPO11, BCFF11, AEFI11, etc.), nao so KNCA11. Isso e
        # uma falha da FONTE DE DADOS (Fundamentus), nao fundos mortos de
        # verdade -- fundos mortos de verdade sao <2% do universo, nao 30%.
        # Sanity check: so aplica o filtro de fantasma se a fracao de
        # liquidez=0 for PLAUSIVEL (<15%). Se vier mais alto que isso, o
        # dado de liquidez desse run inteiro e considerado NAO CONFIAVEL --
        # o filtro se desliga sozinho (mantem todos os FIIs) em vez de
        # arriscar descartar em massa fundos reais e liquidos.
        antes_liq = len(fiis)
        candidatos_liq0 = [f['ticker'] for f in fiis if not (f['liquidez'] and f['liquidez'] > 0)]
        frac_liq0 = len(candidatos_liq0) / antes_liq if antes_liq else 0
        if frac_liq0 > 0.15:
            for tk in candidatos_liq0:
                descartados_diagnostico.append({'ticker': tk, 'motivo': 'liquidez_zerada_MAS_filtro_desativado_fonte_suspeita'})
            removidos_liq0 = 0
            # NAO filtra -- fiis permanece como esta, com todos os tickers
        else:
            for tk in candidatos_liq0:
                descartados_diagnostico.append({'ticker': tk, 'motivo': 'liquidez_zerada_ou_nula'})
            fiis = [f for f in fiis if f['liquidez'] and f['liquidez'] > 0]
            removidos_liq0 = antes_liq - len(fiis)

        # ── Exclusao manual: fundos que saíram de negociacao (fusao,
        # incorporacao, troca de ticker) mas o Fundamentus ainda mantem na
        # tabela com dado cacheado/desatualizado (liquidez sozinha nao e
        # confiavel pra detectar isso, pode ficar com valor antigo).
        # Adicionado 01/07/2026 apos usuario reportar CBCV11 no topo do
        # ranking mesmo ja nao sendo mais negociado (virou outro fundo).
        # Reportar novos casos aqui conforme aparecerem.
        for f in fiis:
            if f['ticker'] in _FII_TICKERS_INATIVOS:
                descartados_diagnostico.append({'ticker': f['ticker'], 'motivo': 'exclusao_manual_inativo'})
        fiis = [f for f in fiis if f['ticker'] not in _FII_TICKERS_INATIVOS]

        # ── Sanity checks (NUNCA aceitar dado suspeito sem avisar) ──
        if len(fiis) < 300:
            return None, f'poucos_fiis_encontrados ({len(fiis)}, esperado 300+)'
        p_vps_validos = [f['p_vp'] for f in fiis if f['p_vp'] is not None]
        if p_vps_validos:
            frac_fora_faixa = sum(1 for v in p_vps_validos if v < 0 or v > 5) / len(p_vps_validos)
            if frac_fora_faixa > 0.1:  # mais de 10% fora da faixa plausivel = layout suspeito
                return None, f'p_vp_fora_da_faixa ({frac_fora_faixa*100:.1f}% das linhas)'

        # ADICIONADO 07/07/2026 -- guarda o diagnostico completo em cache
        # module-level, consultavel via /fiis/diagnostico sem precisar
        # rodar o scrape de novo (que so roda 1x por ciclo de cache normal).
        global _FII_ULTIMO_DIAGNOSTICO
        _FII_ULTIMO_DIAGNOSTICO = {
            'total_linhas_html': len(linhas_raw),
            'total_aceitos': len(fiis),
            'total_descartados': len(descartados_diagnostico),
            'fracao_liquidez_zerada_pct': round(frac_liq0 * 100, 1),
            'filtro_fantasma_desativado_fonte_suspeita': frac_liq0 > 0.15,
            'descartados': descartados_diagnostico,
        }

        return fiis, None
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
        'BCDI11',  # BTG Pactual Divida Infra CDI -- estreou na B3 em 04/08/2026
                   # apos 2 anos no balcao (fonte: Seu Dinheiro). Adicionado
                   # 06/08/2026 apos Victor notar ausencia -- NAO era bug de
                   # liquidez/filtro, so faltava na whitelist manual. Fontes
                   # externas (fiis.com.br e investidor10.com.br) ainda NAO
                   # indexavam o papel em 06/08 (404/410 confirmados) -- os
                   # dados (cotacao/DY/liquidez) so aparecem quando essas
                   # fontes publicarem a pagina do fundo, sem precisar de
                   # novo deploy.
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
