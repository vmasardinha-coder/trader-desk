# rotas_etfs.py — Rotas Flask de ETFs do Trader Desk
#
# Extraido do proxy.py em 04/07/2026 (Prioridade 2 da modularizacao,
# fase 5 de 5, ULTIMA fase -- fase 1 motor.py, fase 2 fontes_etfs.py,
# fase 3 fontes.py, fase 4 rotas_fiis.py). Contem as 6 rotas de ETFs
# (watchlist, live-status, estado, mover, carteira/projecao,
# carteira/resumo), que chamam o universo/scrapers puros de
# fontes_etfs.py (fase 2).
#
# MESMO PADRAO de rotas_fiis.py (fase 4): funcao registrar_rotas(app, ...)
# em vez de import direto, pra evitar circular import (rotas precisam do
# `app` que proxy.py cria).
#
# O que NAO esta aqui (fica em proxy.py, de proposito): _cache_etfs_live,
# _ETF_CACHE_TTL, _dy_refresh_em_andamento, _fetch_etfs_live,
# _refresh_completo_background, _disparar_refresh_background -- essas
# dependem de ESTADO COMPARTILHADO entre requisicoes (cache em memoria +
# thread de background) e do ciclo de vida do processo, nao sao rota nem
# fonte pura. Passadas para ca como parametro de registrar_rotas().
#
# _ler_etfs_estado ficou AQUI (nao em proxy.py) porque e self-contained
# (so requests, sem estado compartilhado) e especifica de ETFs.

from flask import request, jsonify
import re
import json
import math
import time
import datetime as _dt_cache
import requests
from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait
from motor import vol_hist, _calc_bandas_foto
from fontes_etfs import (
    ETF_UNIVERSO, _ETF_TICKERS_TODOS, _etf_yahoo_ticker, _fetch_yahoo_series,
    _fetch_dy_yahoo, _fetch_preco_yahoo, _extrair_linhas_tabela,
)

try:
    import numpy as _np
    _NUMPY = True
except ImportError:
    _NUMPY = False


def _ler_etfs_estado():
    try:
        r = requests.get(
            'https://raw.githubusercontent.com/vmasardinha-coder/trader-desk/main/etfs_estado.json',
            headers={'Cache-Control': 'no-cache'}, timeout=10)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {'em_analise': [], 'carteira': []}


# Cache diario do resumo de volatilidade da Carteira ETFs (05/07/2026,
# pedido do usuario -- mesmo raciocinio aplicado em /carteira-fiis/resumo:
# o calculo de correlacao/GARCH nao precisa rodar a cada clique, so 1x por
# dia). Chave inclui os tickers da carteira, entao se o usuario mover um
# ETF pra dentro/fora da carteira no meio do dia, o cache invalida sozinho.
_cache_etf_carteira_resumo = {'chave': None, 'resposta': None}


def registrar_rotas(app, _fetch_etfs_live, _cache_etfs_live, _dy_refresh_em_andamento,
                     _github_get_file, _github_put_file, _github_criar_arquivo,
                     _requer_auth_escrita, _fetch_closes_for_foto, _obter_preco_sigma_garch):
    """Registra todas as rotas de ETFs no app Flask recebido de proxy.py."""

    @app.route('/etfs', methods=['GET'])
    def get_etfs_watchlist():
        try:
            forcar = request.args.get('forcar', '').lower() in ('1', 'true', 'sim')
            live = _fetch_etfs_live(forcar=forcar)
        except Exception:
            live = {}
        resultado = []
        for etf in ETF_UNIVERSO:
            d = live.get(etf['ticker'], {})
            resultado.append({
                **etf,
                'preco': d.get('preco'),
                'dy': d.get('dy'),
                'var_12m': d.get('var_12m'),
                'var_24m': d.get('var_24m'),
                'cap': d.get('cap'),
                'pagador': etf['categoria'] == 'Pagador' or (d.get('dy') is not None),
            })
        return jsonify(resultado)

    @app.route('/etfs/live-status', methods=['GET'])
    def etfs_live_status():
        """
        04/07/2026: Victor reportou watchlist inteira com "—" mesmo apos
        forcar refresh. Nao consigo testar rede real (investidor10/Yahoo)
        do sandbox de desenvolvimento -- essa rota faz um diagnostico AO
        VIVO, direto do Render, pra saber exatamente onde a cadeia esta
        falhando: investidor10 bloqueando (status != 200)? Retornando 200
        mas com HTML que nao bate o regex (0 linhas)? Yahoo bloqueando?
        Timeout? So chamar essa rota no navegador/curl e mandar o retorno.
        """
        diagnostico = {}

        # 1. investidor10 nacional, pagina 1, cru -- sem cache, sem paralelismo
        try:
            t0 = time.time()
            r = requests.get('https://investidor10.com.br/etfs?page=1',
                              headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            dt = round(time.time() - t0, 2)
            linhas = _extrair_linhas_tabela(r.text) if r.ok else []
            diagnostico['investidor10_nacional_pagina1'] = {
                'status_http': r.status_code, 'tempo_s': dt,
                'tamanho_resposta': len(r.text), 'linhas_extraidas': len(linhas),
                'primeira_linha_bruta': linhas[0] if linhas else None,
            }
        except Exception as e:
            diagnostico['investidor10_nacional_pagina1'] = {'excecao': str(e)}

        # 2. Yahoo DY direto para 1 ticker conhecido (COIN11.SA)
        try:
            t0 = time.time()
            dy = _fetch_dy_yahoo('COIN11.SA')
            diagnostico['yahoo_dy_COIN11'] = {'valor': dy, 'tempo_s': round(time.time()-t0, 2)}
        except Exception as e:
            diagnostico['yahoo_dy_COIN11'] = {'excecao': str(e)}

        # 3. Yahoo preco direto para 1 ticker conhecido
        try:
            t0 = time.time()
            preco = _fetch_preco_yahoo('COIN11.SA')
            diagnostico['yahoo_preco_COIN11'] = {'valor': preco, 'tempo_s': round(time.time()-t0, 2)}
        except Exception as e:
            diagnostico['yahoo_preco_COIN11'] = {'excecao': str(e)}

        # 4. Estado do cache em memoria agora
        diagnostico['cache_atual'] = {
            'tem_dados': _cache_etfs_live['dados'] is not None,
            'idade_s': round(time.time() - _cache_etfs_live['ts'], 1) if _cache_etfs_live['dados'] else None,
            'qtd_tickers_com_dado': len(_cache_etfs_live['dados']) if _cache_etfs_live['dados'] else 0,
            'refresh_em_andamento': _dy_refresh_em_andamento['flag'],
        }

        try:
            live = _fetch_etfs_live()
        except Exception as e:
            return jsonify({'erro_geral': str(e), 'diagnostico': diagnostico})
        faltando = [t for t in sorted(_ETF_TICKERS_TODOS) if t not in live]
        return jsonify({
            'total_universo': len(_ETF_TICKERS_TODOS),
            'total_com_dado': len(live),
            'faltando': faltando,
            'diagnostico': diagnostico,
        })

    @app.route('/etfs/estado', methods=['GET'])
    def get_etfs_estado():
        return jsonify(_ler_etfs_estado())

    @app.route('/etfs/mover', methods=['POST'])
    @_requer_auth_escrita
    def mover_etf():
        try:
            body = request.get_json(force=True)
            ticker = (body.get('ticker') or '').upper().strip()
            destino = body.get('destino')
            if not ticker or ticker not in _ETF_TICKERS_TODOS:
                return jsonify({'error': 'ticker invalido ou fora do universo fechado de ETFs'}), 400
            if destino not in ('em_analise', 'carteira'):
                return jsonify({'error': "destino deve ser 'em_analise' ou 'carteira'"}), 400
            try:
                conteudo, sha = _github_get_file('etfs_estado.json')
                estado = json.loads(conteudo)
            except Exception:
                estado = {'em_analise': [], 'carteira': []}
                sha = None
            estado.setdefault('em_analise', [])
            estado.setdefault('carteira', [])
            estado['em_analise'] = [t for t in estado['em_analise'] if t != ticker]
            if destino == 'em_analise':
                if ticker not in estado['em_analise']:
                    estado['em_analise'].append(ticker)
            else:
                from datetime import datetime as _dt_etf
                preco_entrada = body.get('preco_entrada')
                data_entrada = body.get('data_entrada') or _dt_etf.now().strftime('%Y-%m-%d')
                estado['carteira'] = [c for c in estado['carteira'] if c.get('ticker') != ticker]
                estado['carteira'].append({'ticker': ticker, 'preco_entrada': preco_entrada, 'data_entrada': data_entrada})
            conteudo_novo = json.dumps(estado, ensure_ascii=False, indent=2)
            if sha:
                _github_put_file('etfs_estado.json', conteudo_novo, sha, f'Move ETF {ticker} -> {destino}')
            else:
                _github_criar_arquivo('etfs_estado.json', conteudo_novo, f'Cria etfs_estado.json, move {ticker} -> {destino}')
            return jsonify({'ok': True, 'estado': estado})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/etfs/carteira/<ticker>/status', methods=['PUT'])
    @_requer_auth_escrita
    def mudar_status_carteira_etf(ticker):
        """
        Encerra (vende) um ETF da Carteira. Espera {'status': 'encerrada'}
        no body.

        ADICIONADO 15/07/2026 -- mesmo padrao ja validado em
        mudar_status_carteira_fii (rotas_fiis.py, 11/07/2026): como nao ha
        como calcular automaticamente o resultado (venda pode ser parcial,
        e o app nao guarda quantidade de cotas real), o encerramento aceita
        3 campos OPCIONAIS extras no body, preenchidos via prompt() no
        frontend, no mesmo espirito de FIIs:
        - resultado: 'sucesso' | 'fracasso' | 'parcial'
        - valor_financeiro_resultado: numero (R$), digitado manualmente --
          nunca calculado aqui, so o usuario sabe o que de fato vendeu.
        - observacao_encerramento: texto livre opcional.
        Itens da carteira sem 'status' sao tratados como 'ativa'
        (compatibilidade retroativa -- etfs_estado.json nunca teve esse
        campo antes desta mudanca).
        """
        try:
            ticker = ticker.upper().strip()
            body = request.get_json() or {}
            novo_status = body.get('status')
            if novo_status != 'encerrada':
                return jsonify({'error': f"status invalido: {novo_status!r} (use 'encerrada')"}), 422

            resultado = body.get('resultado')
            if resultado is not None and resultado not in ('sucesso', 'fracasso', 'parcial'):
                return jsonify({'error': f"resultado invalido: {resultado!r} (use sucesso/fracasso/parcial)"}), 422

            conteudo_str, sha = _github_get_file('etfs_estado.json')
            estado = json.loads(conteudo_str) if conteudo_str.strip() else {'em_analise': [], 'carteira': []}
            estado.setdefault('carteira', [])
            encontrado = False
            from datetime import datetime as _dt_etf2
            for item in estado['carteira']:
                if item.get('ticker') == ticker and item.get('status', 'ativa') == 'ativa':
                    item['status'] = 'encerrada'
                    item['data_encerramento'] = _dt_etf2.now().strftime('%Y-%m-%d')
                    if resultado is not None:
                        item['resultado'] = resultado
                    if body.get('valor_financeiro_resultado') is not None:
                        item['valor_financeiro_resultado'] = float(body['valor_financeiro_resultado'])
                    if body.get('observacao_encerramento'):
                        item['observacao_encerramento'] = body['observacao_encerramento']
                    encontrado = True
                    break
            if not encontrado:
                return jsonify({'error': f'ETF {ticker} nao encontrado (ativo) na carteira'}), 404

            novo_conteudo = json.dumps(estado, ensure_ascii=False, indent=2)
            _github_put_file('etfs_estado.json', novo_conteudo, sha,
                f"feat: ETF {ticker} -> status=encerrada via app")
            return jsonify({'ticker': ticker, 'status': 'encerrada'})
        except RuntimeError as e:
            return jsonify({'error': str(e)}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/etfs/carteira/resumo-encerradas', methods=['GET'])
    def get_etf_carteira_resumo_encerradas():
        """
        ADICIONADO 15/07/2026 -- soma os resultados financeiros informados
        manualmente no encerramento de ETFs (ver mudar_status_carteira_etf),
        espelhando /carteira-fiis/resumo-encerradas. So conta itens com
        valor_financeiro_resultado preenchido.
        """
        try:
            estado = _ler_etfs_estado()
            carteira = estado.get('carteira', [])
            encerrados_com_valor = [
                c for c in carteira
                if c.get('status') == 'encerrada' and c.get('valor_financeiro_resultado') is not None
            ]
            total_liquido = sum(c['valor_financeiro_resultado'] for c in encerrados_com_valor)
            por_resultado = {'sucesso': 0, 'fracasso': 0, 'parcial': 0}
            for c in encerrados_com_valor:
                r = c.get('resultado')
                if r in por_resultado:
                    por_resultado[r] += 1
            return jsonify({
                'total_liquido': round(total_liquido, 2),
                'qtd_com_valor_registrado': len(encerrados_com_valor),
                'qtd_total_encerradas': len([c for c in carteira if c.get('status') == 'encerrada']),
                'por_resultado': por_resultado,
                'itens': [
                    {'ticker': c['ticker'], 'resultado': c.get('resultado'),
                     'valor_financeiro_resultado': c['valor_financeiro_resultado'],
                     'observacao_encerramento': c.get('observacao_encerramento'),
                     'data_encerramento': c.get('data_encerramento')}
                    for c in encerrados_com_valor
                ],
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/etfs/carteira/<ticker>/projecao', methods=['GET'])
    def get_etf_carteira_projecao(ticker):
        """
        Fan chart de projecao (GARCH) para um ETF individual da Carteira,
        a partir do preco atual -- sem meta/barreira (ETF nao tem estrutura
        com vencimento, e buy-and-hold puro). Mesmo padrao visual da Foto
        do Papel: bandas p10/p25/p50/p75/p90 + linha de preco real desde a
        data de entrada registrada em etfs_estado.json.
        """
        try:
            ticker = ticker.upper().strip()
            if ticker not in _ETF_TICKERS_TODOS:
                return jsonify({'error': 'ticker fora do universo fechado de ETFs'}), 400
            etf = next((e for e in ETF_UNIVERSO if e['ticker'] == ticker), None)
            estado = _ler_etfs_estado()
            pos = next((c for c in estado.get('carteira', [])
                        if c.get('ticker') == ticker and c.get('status', 'ativa') == 'ativa'), None)
            if not pos:
                return jsonify({'error': 'ETF nao esta ativo na Carteira'}), 404

            yt = _etf_yahoo_ticker(etf)
            S, sigma, garch_info, closes = _obter_preco_sigma_garch(yt)
            if not S:
                return jsonify({'error': f'Nao foi possivel obter preco/historico de {ticker}'}), 500
            if not sigma:
                sigma = 0.35  # fallback final, mesmo padrao do resto do app

            periodos = [21, 60, 90, 180]
            bandas = _calc_bandas_foto(S, sigma, periodos=periodos)

            historico_real = []
            data_entrada = pos.get('data_entrada')
            if data_entrada:
                try:
                    historico_real = _fetch_closes_for_foto(yt, data_entrada)
                except Exception:
                    historico_real = []

            return jsonify({
                'ticker': ticker,
                'desc': etf.get('desc'),
                'mercado': etf.get('mercado'),
                'preco_atual': round(S, 2),
                'sigma_pct': round(sigma * 100, 2),
                'garch': garch_info,
                'preco_entrada': pos.get('preco_entrada'),
                'data_entrada': data_entrada,
                'periodos': periodos,
                'bandas': bandas,
                'historico_real': historico_real,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/etfs/carteira/resumo', methods=['GET'])
    def get_etf_carteira_resumo():
        """
        Card de resumo agregado da Carteira de ETFs (item 2 do backlog,
        03/07/2026). Volatilidade da carteira calculada com CORRELACAO REAL
        entre os ativos (matriz de covariancia dos retornos historicos
        alinhados por data), nao soma simples das vols individuais --
        decisao explicita do usuario ("realista", nao simplificado).

        LIMITACAO ASSUMIDA (nao ha campo de quantidade em etfs_estado.json,
        so preco_entrada por posicao): pondera cada ETF como 1 cota. Se no
        futuro quiser peso por quantidade real comprada, precisa adicionar
        campo 'quantidade' em /etfs/mover e aqui.

        CACHE DIARIO (05/07/2026): calculo pesado, roda de verdade so 1x
        por dia (chave = data + tickers da carteira). Resposta cacheada
        volta com 'cache': True.
        """
        try:
            estado = _ler_etfs_estado()
            # ADICIONADO 15/07/2026: so conta posicoes ATIVAS -- encerradas
            # (ver mudar_status_carteira_etf) nao entram no total investido/
            # valor atual/volatilidade da carteira em operacao.
            itens = [c for c in estado.get('carteira', []) if c.get('status', 'ativa') == 'ativa']
            if not itens:
                return jsonify({
                    'itens': [], 'total_investido': 0, 'valor_atual': 0,
                    'retorno_pct': None, 'vol_carteira_pct': None,
                    'vol_soma_simples_pct': None, 'correlacoes': None,
                    'nota': 'Carteira vazia.',
                })

            itens_check = sorted(c.get('ticker', '') for c in itens)
            chave_cache = _dt_cache.date.today().isoformat() + '|' + ','.join(itens_check)
            if _cache_etf_carteira_resumo['chave'] == chave_cache:
                resp_cache = dict(_cache_etf_carteira_resumo['resposta'])
                resp_cache['cache'] = True
                return jsonify(resp_cache)

            try:
                live = _fetch_etfs_live()
            except Exception:
                live = {}
            etf_map = {e['ticker']: e for e in ETF_UNIVERSO}

            resultado_itens = []
            total_investido = 0.0
            valor_atual_total = 0.0
            pesos_valor = {}
            series = {}

            for c in itens:
                ticker = c.get('ticker')
                etf = etf_map.get(ticker)
                if not etf:
                    continue
                preco_entrada = c.get('preco_entrada')
                preco_atual = (live.get(ticker) or {}).get('preco')
                valor_pos = preco_atual if preco_atual is not None else preco_entrada
                if preco_entrada:
                    total_investido += preco_entrada
                if valor_pos:
                    valor_atual_total += valor_pos
                    pesos_valor[ticker] = valor_pos
                variacao = None
                if preco_entrada and preco_atual:
                    variacao = round((preco_atual / preco_entrada - 1) * 100, 2)
                resultado_itens.append({
                    'ticker': ticker, 'mercado': etf.get('mercado'), 'desc': etf.get('desc'),
                    'preco_entrada': preco_entrada, 'data_entrada': c.get('data_entrada'),
                    'preco_atual': preco_atual, 'variacao_pct': variacao,
                })

            # CORRIGIDO 04/07/2026 -- o loop acima buscava _fetch_yahoo_series
            # SEQUENCIALMENTE (1 ticker de cada vez, ate 2 hosts x 8s cada),
            # podendo passar de 30s com so 2-3 posicoes e derrubar a resposta
            # no meio (Render mata a conexao, browser recebe corpo vazio ->
            # "Unexpected end of JSON input"). Mesmo principio ja usado em
            # _fetch_etfs_live/_refresh_completo_background: busca em PARALELO
            # com orcamento de tempo fixo, nunca deixa uma rota depender de N
            # chamadas de rede sequenciais para responder.
            tickers_com_etf = [c.get('ticker') for c in itens if etf_map.get(c.get('ticker'))]
            if tickers_com_etf:
                ex = ThreadPoolExecutor(max_workers=min(8, len(tickers_com_etf)))
                try:
                    futuros = {
                        ex.submit(_fetch_yahoo_series, _etf_yahoo_ticker(etf_map[t]), '1y'): t
                        for t in tickers_com_etf
                    }
                    prontos, pendentes = _cf_wait(list(futuros.keys()), timeout=15)
                    for fut in prontos:
                        t = futuros[fut]
                        try:
                            s = fut.result()
                        except Exception:
                            s = None
                        if s:
                            series[t] = s
                finally:
                    ex.shutdown(wait=False)

            retorno_pct = None
            if total_investido > 0:
                retorno_pct = round((valor_atual_total / total_investido - 1) * 100, 2)


            vol_carteira_pct = None
            vol_soma_simples_pct = None
            correlacoes = None

            if _NUMPY:
                tickers_com_serie = [t for t in pesos_valor if t in series and len(series[t]) >= 30]
                if len(tickers_com_serie) >= 2:
                    datas_comuns = None
                    for t in tickers_com_serie:
                        ds = set(series[t].keys())
                        datas_comuns = ds if datas_comuns is None else (datas_comuns & ds)
                    datas_ordenadas = sorted(datas_comuns) if datas_comuns else []
                    if len(datas_ordenadas) >= 30:
                        precos_np = _np.array([[series[t][d] for d in datas_ordenadas] for t in tickers_com_serie])
                        log_rets = _np.diff(_np.log(precos_np), axis=1)
                        cov_diaria = _np.cov(log_rets)
                        cov_anual = cov_diaria * 252
                        pesos_vec = _np.array([pesos_valor[t] for t in tickers_com_serie])
                        soma_pesos = pesos_vec.sum()
                        if soma_pesos > 0:
                            w = pesos_vec / soma_pesos
                            var_port = float(w @ cov_anual @ w)
                            vol_carteira_pct = round(math.sqrt(max(var_port, 0)) * 100, 2)
                            vols_individuais = _np.sqrt(_np.diag(cov_anual))
                            vol_soma_simples_pct = round(float((w * vols_individuais).sum()) * 100, 2)
                            std = _np.sqrt(_np.diag(cov_anual))
                            std_safe = _np.where(std == 0, 1e-9, std)
                            corr = cov_anual / _np.outer(std_safe, std_safe)
                            correlacoes = {
                                tickers_com_serie[i]: {
                                    tickers_com_serie[j]: round(float(corr[i, j]), 3)
                                    for j in range(len(tickers_com_serie))
                                } for i in range(len(tickers_com_serie))
                            }
                elif len(tickers_com_serie) == 1:
                    t = tickers_com_serie[0]
                    cl = list(series[t].values())
                    vh = vol_hist(cl) if len(cl) >= 22 else None
                    if vh:
                        vol_carteira_pct = round(vh * 100, 2)
                        vol_soma_simples_pct = vol_carteira_pct

            resposta = {
                'itens': resultado_itens,
                'total_investido': round(total_investido, 2),
                'valor_atual': round(valor_atual_total, 2),
                'retorno_pct': retorno_pct,
                'vol_carteira_pct': vol_carteira_pct,
                'vol_soma_simples_pct': vol_soma_simples_pct,
                'correlacoes': correlacoes,
                'nota': 'Peso de cada ETF assume 1 cota (nao ha campo de quantidade registrada).',
            }
            _cache_etf_carteira_resumo['chave'] = chave_cache
            _cache_etf_carteira_resumo['resposta'] = resposta
            resp_out = dict(resposta)
            resp_out['cache'] = False
            return jsonify(resp_out)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
