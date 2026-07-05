# rotas_fiis.py — Rotas Flask de FIIs do Trader Desk
#
# Extraido do proxy.py em 04/07/2026 (Prioridade 2 da modularizacao,
# fase 4 de 5; fase 1 motor.py, fase 2 fontes_etfs.py, fase 3 fontes.py).
# Contem as rotas de FIIs (busca/listagem/ranking/carteira/FI-Infra/
# debug), que chamam os scrapers/classificadores puros ja extraidos para
# fontes.py na fase 3.
#
# PADRAO USADO (diferente de fontes.py/fontes_etfs.py/motor.py, que sao
# import direto): rotas precisam do objeto `app` do Flask para registrar
# @app.route, e proxy.py e quem cria `app` -- importar `app` de volta de
# dentro deste arquivo causaria import circular (rotas_fiis precisaria de
# proxy, que precisa de rotas_fiis). Solucao padrao para dividir rotas
# Flask sem Blueprints: uma funcao `registrar_rotas(app, ...)` que recebe
# `app` e as poucas dependencias de proxy.py que as rotas usam
# (_github_get_file/_github_put_file para carteira, _hoje_str,
# _requer_auth_escrita para as rotas de escrita), e registra as rotas
# dentro dela via closure. proxy.py chama isso 1 vez, depois de definir
# essas dependencias e o `app`.
#
# O que NAO esta aqui: os scrapers/classificadores puros (estao em
# fontes.py), e qualquer rota nao-FII.

from flask import request, jsonify
import re
import json
import math
import requests
from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait
from fontes import (
    scrape_fiis_fundamentus, _classificar_risco_fii, _score_fii,
    scrape_fi_infra, scrape_fi_infra_dados,
    scrape_statusinvest_ultimo_provento, scrape_statusinvest_historico_proventos,
    scrape_statusinvest_tickers_listagem, scrape_statusinvest_fundo_dados,
)
from fontes_etfs import _fetch_yahoo_series
from motor import vol_hist

try:
    import numpy as _np
    _NUMPY = True
except ImportError:
    _NUMPY = False

_CARTEIRA_FII_STATUS_VALIDOS = ['ativa', 'encerrada']


def registrar_rotas(app, _github_get_file, _github_put_file, _hoje_str, _requer_auth_escrita):
    """Registra todas as rotas de FIIs no app Flask recebido de proxy.py."""

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

    @app.route('/carteira-fiis/resumo', methods=['GET'])
    def get_carteira_fiis_resumo():
        """
        Card de resumo agregado da Carteira de FIIs (05/07/2026), espelhando
        /etfs/carteira/resumo: volatilidade real da carteira via matriz de
        covariancia dos retornos historicos (correlacao real entre os FIIs),
        nao soma simples das vols individuais.

        MESMA LIMITACAO ASSUMIDA que em ETFs (nao ha campo de quantidade em
        carteira_fiis.json, so preco_ativacao por posicao): pondera cada FII
        pelo VALOR da posicao (preco_atual, com fallback pro preco de
        ativacao), nao por numero de cotas.

        MESMO CUIDADO DE PERFORMANCE que em /etfs/carteira/resumo: busca os
        historicos de TODOS os FIIs em PARALELO (ThreadPoolExecutor) com
        orcamento de tempo fixo (15s), nunca sequencial -- com 12 FIIs ativos
        (mais que o caso de ETFs), buscar 1 de cada vez estouraria o tempo do
        Render e cortaria a resposta no meio.
        """
        try:
            conteudo_str, _ = _github_get_file('carteira_fiis.json')
            carteira = json.loads(conteudo_str) if conteudo_str.strip() else []
            itens = [f for f in carteira if f.get('status') == 'ativa']
            if not itens:
                return jsonify({
                    'itens': [], 'total_investido': 0, 'valor_atual': 0,
                    'retorno_pct': None, 'vol_carteira_pct': None,
                    'vol_soma_simples_pct': None, 'correlacoes': None,
                    'nota': 'Carteira vazia.',
                })

            tickers = [f['ticker'] for f in itens]
            series = {}
            ex = ThreadPoolExecutor(max_workers=min(12, len(tickers)))
            try:
                futuros = {
                    ex.submit(_fetch_yahoo_series, t + '.SA', '1y'): t
                    for t in tickers
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

            resultado_itens = []
            total_investido = 0.0
            valor_atual_total = 0.0
            pesos_valor = {}

            for f in itens:
                ticker = f['ticker']
                preco_ativacao = f.get('preco_ativacao')
                s = series.get(ticker)
                preco_atual = None
                if s:
                    ultima_data = max(s.keys())
                    preco_atual = s[ultima_data]
                valor_pos = preco_atual if preco_atual is not None else preco_ativacao
                if preco_ativacao:
                    total_investido += preco_ativacao
                if valor_pos:
                    valor_atual_total += valor_pos
                    pesos_valor[ticker] = valor_pos
                variacao = None
                if preco_ativacao and preco_atual:
                    variacao = round((preco_atual / preco_ativacao - 1) * 100, 2)
                resultado_itens.append({
                    'ticker': ticker, 'nome_fundo': f.get('nome_fundo'),
                    'segmento': f.get('segmento'),
                    'preco_ativacao': preco_ativacao, 'data_ativacao': f.get('data_ativacao'),
                    'preco_atual': preco_atual, 'variacao_pct': variacao,
                })

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

            return jsonify({
                'itens': resultado_itens,
                'total_investido': round(total_investido, 2),
                'valor_atual': round(valor_atual_total, 2),
                'retorno_pct': retorno_pct,
                'vol_carteira_pct': vol_carteira_pct,
                'vol_soma_simples_pct': vol_soma_simples_pct,
                'correlacoes': correlacoes,
                'nota': 'Peso de cada FII assume valor da posicao (nao ha campo de quantidade registrada).',
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

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
