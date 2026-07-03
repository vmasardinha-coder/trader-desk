# Trader Desk — Prompt de Continuação (v17.0 — sessão 02/07/2026)

## Stack
- Flask no Render (free tier): https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk (branch: main)
- Token GitHub de SESSÃO (Claude usa em chat, colado pelo usuário): classic, escopo `repo`, válido 90 dias a partir de 02/07/2026
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho): fine-grained, restrito SÓ ao repo trader-desk, permissão "Contents: Read and write", configurado como `GITHUB_TOKEN` no Render. **PENDÊNCIA AINDA ABERTA (item #1 do backlog): criar token fine-grained sem vencimento curto para substituir o atual (processo: GitHub → Settings → Developer Settings → Fine-grained tokens → só trader-desk → Contents R/W)**
- Deploy: GET SHA → PUT base64 via API do GitHub. HTML em templates/, JS em static/app.js
- Console de debug: Eruda ativo no index.html para validação mobile — usuário confirmou fluxo de POST manual via `fetch()` + `localStorage.getItem('api_write_token')` como `Authorization: Bearer <token>`, funciona bem para registrar análises de teste/lote sem passar pelo formulário do app
- **REGRA CRÍTICA DE PROCESSO**: usar `api.github.com/repos/.../contents/...` para ler arquivos que foram editados NA MESMA sessão — nunca `raw.githubusercontent.com` para isso (CDN cache causa leituras desatualizadas e pode reverter mudanças ao re-editar)
- **LIMITAÇÃO DE AMBIENTE CONFIRMADA (02/07/2026)**: o sandbox de execução do Claude (bash_tool) só acessa domínios de pacotes (github.com, api.github.com, pypi.org, npmjs.com etc) — NÃO acessa `trader-desk.onrender.com` nem `finance.yahoo.com`. Isso significa que Claude NÃO consegue chamar `POST /analises` (ou qualquer rota Flask) diretamente, nem buscar preço/histórico via Yahoo no sandbox. Duas consequências práticas: (1) quando Claude precisa registrar uma análise nova a partir de um lote decidido em chat, o caminho é ESCREVER DIRETO no `analises.json`/`positions.json` via GitHub Contents API (contorna o Flask) — mas isso PULA o congelamento automático de bandas (backlog #4), que só roda dentro da rota Flask; (2) para testar de verdade o congelamento de bandas, o USUÁRIO precisa rodar o `fetch()` manual pelo Eruda, não Claude. Se no futuro o domínio do Render for liberado no sandbox, isso deixa de ser necessário.

## SHAs no fechamento desta sessão (02/07/2026, apos item 2 do backlog — Cotações)
- proxy.py: 9b6d29ebd8f36ada0529e988546717ac51d9f38a
- static/app.js: d857a6883c7c148da67f0867a52a289d4011e2dd
- templates/index.html: e3331e563433989e312d00b975cddde83c5173c1
- positions.json: c462e0a7b4d666e0c3f6b6e165f7df767d4a23ed (7 posições ativas, 4 encerradas)
- analises.json: 5e638624371ec107611b90d63ca052452e1e66e6 (54 registros — 8 duplicadas antigas já rejeitadas)

## Itens CONCLUIDOS e VALIDADOS nesta sessao (02/07/2026)

### 1. Backlog #2 — Legenda de confianca na Foto do Papel
Adicionada caixa "Com 80% de confianca, o preco deve estar entre R$X e R$Y" (e faixa de 50%) no grafico da Foto do Papel, mesmo padrao do fan chart de Monte Carlo. Implementado em `renderFotoChart` (app.js).

### 2. Backlog #3 — Bulk foto na watchlist
Botao "Tirar Foto de Todos" no topo da aba Papeis. Roda sequencialmente (400ms entre chamadas) por todos os ativos da watchlist, mostra progresso e resumo final.

### 3. Backlog #4 — Foto automatica congelada em Em Analise
`POST /analises` agora congela sozinho as bandas GARCH (usando `preco_foto` como ponto de partida) sempre que uma analise e criada, para `tipo_estrutura != 'fii'`. Nova rota `GET /analises/<id>/foto-bandas` retorna as bandas congeladas + historico real desde a foto + score de assertividade. Botao de foto em cada linha do ranking de Em Analise abre um painel acima da tabela (nao dentro do card expandido — sao componentes visuais separados) com o grafico. CONFIRMADO FUNCIONANDO DE VERDADE via teste manual do usuario pelo Eruda (POST direto, resposta trouxe `bandas_congeladas` preenchido).

### 4. BUGFIX CRITICO — historico real nunca aparecia nas fotos
`_fetch_closes_for_foto` (proxy.py) tinha um typo: lia `result['timestamps']` (plural, chave errada) em vez de `result['timestamp']` (singular, chave real da API do Yahoo). Isso causava excecao silenciosa (capturada por `except: continue`), fazendo a funcao SEMPRE retornar lista vazia — ou seja, a linha de preco real NUNCA aparecia em nenhuma foto (nem Foto do Papel, nem foto de Em Analise), desde que essas features foram implementadas em 30/06. Corrigido para `result['timestamp']`. **CONFIRMADO VISUALMENTE PELO USUARIO — ponto/linha do preco real aparecendo corretamente nas fotos.**

### 5. Filtro de FIIs fantasma (fundos incorporados/deslistados)
Usuario reportou CBCV11 aparecendo no topo do ranking mesmo ja nao sendo mais negociado (virou outro fundo). Duas camadas de protecao adicionadas em `scrape_fiis_fundamentus`:
- Automatica: exclui qualquer FII com `liquidez` zerada/nula (sem nenhum negocio registrado) — nao confundir com liquidez BAIXA (fundo pequeno mas vivo, que continua no universo normalmente, so pontua pior).
- Manual: `_FII_TICKERS_INATIVOS` (set no proxy.py) para casos onde o Fundamentus mantem liquidez cacheada != 0 mesmo com o fundo morto (caso do CBCV11). Reportar novos casos ao Claude para adicionar.

### 6. Ciclo de vida real: ROXO34 encerrada (fracasso) + rolagem registrada como nova ativa
- ROXO34 original (codigo ROXOG105, strike R$10,50, opcao AMERICANA) estourou a barreira (probabilidade de rompimento chegou a 100%). Movida de `ativas` para `encerradas` com `status: "fracasso"` (id `cl-roxo-jul26`).
- Usuario fez rolagem defensiva POR FORA do app (so para ganhar tempo/sobrevivencia, nao passaria pelos criterios normais de entrada dele — "e uma seca", sem colchao real). Nova posicao registrada em `ativas` (id `rx2`): codigo ROXOI107, strike R$10,75, vencimento 17/09/2026, meta 2,44%, EUROPEIA (nao americana — ver correcao abaixo).
- LICAO IMPORTANTE: a mecanica americana/europeia NAO e fixa por ticker do ativo-objeto (ROXO34), e por codigo de opcao especifico. A ROXOG105 antiga era americana, a ROXOI107 nova e europeia. Sempre confirmar com o usuario a cada opcao/rolagem nova, nunca presumir pelo historico do ticker.
- LICAO CRITICA (adicionada apos fechamento, mesma sessao): `app.js` tem logica de frontend HARDCODED POR ID para ROXO34 especificamente -- busca de preco via `/indicators` (Yahoo bloqueia direto), calculo de ITM/OTM, e Monte Carlo Condicional, todas amarradas ao id EXATO `rx` (`byId.rx`, elementos DOM `rx-p`/`rx-itm`/`rx-mc-*`). Ao mover a ROXO34 antiga para encerradas e criar a rolagem como nova ativa, Claude criou com id `rx2` -- isso quebrou SILENCIOSAMENTE a cotacao/ITM/MC (sem erro visivel, o `if(byId.rx)` so nao rodava). Corrigido renomeando de volta para `rx`. REGRA: ao recriar/rolar a posicao ROXO34 no futuro, SEMPRE reaproveitar o id `rx` exatamente, nunca criar um novo id. Esse tipo de logica hardcoded-por-id pode existir para outras posicoes tambem -- ao mover qualquer posicao ativa entre ids, checar `app.js` por referencias tipo `byId.<id_antigo>` antes de assumir que so trocar o id no positions.json basta.

### 7. Lote de retorno controlado 01/07/2026 (Fase A -> Fase B parcial)
Usuario trouxe planilha "Index/Fixing/Strike/KO/Delta" (159 linhas, ativos ALOS3/BBSE3/CMIN3/CXSE3/DIRR3/PETR4/PRIO3/VALE3) + 7 PDFs de proposta pronta do Itau (AMZO34/BEEF3/CYRE3/INBR32/NVDC34/ROXO34/TSLA34). Processo de filtragem em varias rodadas dentro da sessao (criterio de retorno mensal >2% + refinamentos de protecao minima por prazo, pedidos pelo usuario ao vivo — nao documentar os cortes intermediarios, so o resultado):
- Claude registrou 13 analises via GitHub direto (SEM bandas congeladas, limitacao de ambiente). Usuario filtrou no ranking do app e manteve 8: ROXO34 58d, NVDC34 58d, AMZO34 43d, TSLA34 58d, PETR4 15d, DIRR3 15d, CMIN3 41d, CMIN3 15d.
- Essas 8 foram RE-REGISTRADAS pelo usuario via Eruda (fetch manual, script fornecido por Claude) — nascem com sufixo "[Lote 01/07/2026 - refeita c/ foto]" no nome e JA TEM bandas congeladas.
- **LIMPEZA CONCLUIDA: as 8 antigas (sem foto, sem sufixo) foram rejeitadas pelo usuario no ranking (status alterado, mantidas em historico).**
- BBSE3: nenhuma linha do lote bateu o corte de 2%/mes (melhor delas: 1,31%/mes), mas usuario pediu como EXCECAO por interesse em dividendo — mostradas separadamente, usuario aplicou os mesmos filtros de protecao minima por conta propria depois.

## Backlog atualizado (ordem sugerida para proxima sessao)

1. ~~Token GitHub fine-grained no Render~~ **VARIAVEIS CONFIGURADAS 02/07/2026** (token `trader-desk-render-write`, gerado no GitHub, validade ate 02/07/2027, escopo so trader-desk, Contents R/W). Usuario colou o MESMO token novo em `GITHUB_TOKEN` e `GITHUB_WRITE_TOKEN` no Render (sao 2 variaveis distintas no codigo -- `GITHUB_TOKEN`+`GITHUB_REPO` usados em `_read_fotos`/`_write_fotos` para `fotos_papel.json`; `GITHUB_WRITE_TOKEN` usado em `_github_get_file`/`_github_put_file`/`_github_criar_arquivo` para `analises.json`/`positions.json`/`carteira_fiis.json`). `API_WRITE_TOKEN` nao foi mexido (proposito diferente -- autentica o usuario, nao o GitHub). **PENDENTE DE VALIDACAO REAL**: usuario prefere confirmar organicamente na proxima vez que usar o app (tirar uma foto em Papeis ou registrar/editar algo em Em Analise) em vez de forcar um teste agora. Se aparecer erro tipo "GITHUB_TOKEN nao configurado" ou falha ao salvar, meio caminho andado ja sabemos onde olhar.
2. ~~Cotacoes: segmentos encolhidos por padrao + nome da empresa ao lado do codigo~~ **CONCLUIDO E CONFIRMADO 02/07/2026.** Escopo real (diferente do que constava antes — NAO tem nada a ver com opcoes/Posicoes Ativas): (a) todas as tabelas fixas de Cotacoes (EUA — Mercados, Juros Soberanos, Europa & Asia, B3 — Top 10, Commodities) agora carregam colapsadas por padrao via `togCot()` — Bitcoin ja estava assim, os blocos setoriais (Financeiro/Petroleo/etc, `tg()`) ja eram colapsados por padrao (CSS `.sb2{display:none}`), nao precisou mexer; (b) mapa `US_NOMES` adicionado em app.js com nome da empresa por extenso (ex: UNH → UnitedHealth) exibido como subtitulo do ticker nos segmentos EUA (7 Magnificas, Nasdaq Top 15, S&P 500 Top 20, Dow Jones Top 20, Semicondutores, Software).
3. ~~Estender tabela de meta (probabilidade de bater retorno) + simulacao 100 acoes para Posicoes Ativas~~ **JA EXISTIA, CONFIRMADO 02/07/2026.** Ao abrir a posicao em Em Analise, a foto ja replica as probabilidades de retorno e a simulacao a cada 100 acoes. Nao ha nada a implementar aqui — item removido do backlog ativo.
4. **NOVO (02/07/2026) — Nova aba "ETFs" (posicionada ANTES da aba FIIs).** Pesquisa de universo feita 100% em chat (Fase A), pronta pra virar Fase B (codigo). Arquitetura de fluxo FECHADA nesta sessao:
   - **Watchlist ETFs**: tabela unica com os 53 ETFs (27 Nacionais + 26 Americanos), todos os campos (ticker, mercado, categoria, descricao curta, DY, var 12m/24m, capitalizacao, nivel de risco 1-10). Filtros: por mercado (Nacional/Americano/Todos), por nivel de risco (10 niveis), checkbox "so pagadores de dividendo". Ordenacao por clique em qualquer coluna do cabecalho (sem ordem fixa pre-definida, diferente do ranking de FII que ja vem direcionado). Protótipo interativo ja validado e aprovado pelo usuario via Visualizer nesta sessao -- usar como especificacao exata do layout/comportamento, nao mudar nada da UX.
   - **Em Analise**: usuario manda um ETF da watchlist pra ca manualmente (sem calculo automatico ao entrar -- e so uma lista de candidatos que o usuario esta de olho, ex viu em video/indicacao mas ainda nao tem capital disponivel). Mesma estrutura de colunas da watchlist + **coluna nova de Score, visualmente destacada/separada por ser campo calculado novo**. Score usa o motor GARCH ja existente (Monte Carlo simples de projecao de preco, sem barreira -- mesma logica ja aplicada a PETR4/VALE3/BBAS3) como componente de volatilidade real, RANQUEANDO DENTRO DE CADA FAIXA DE RISCO (nao mistura risco 1/cripto com risco 10/RF num score unico -- risco e filtro, score e o desempate dentro do grupo ja filtrado). Componentes do score a definir tecnicamente na hora de codar: retorno/DY + variacao 12m/24m + volatilidade GARCH.
   - **Carteira (apos OK em Em Analise)**: ETF ganha o MESMO tratamento que ativos simples ja tem hoje (PETR4/VALE3/BBAS3/ROXO34-simples) -- SEM Monte Carlo condicional de barreira (isso e exclusivo de estruturas). So acompanhamento de cotacao + "tirar foto" pra registrar entrada e monitorar valorizacao ao longo do tempo, pagando dividendo ou nao.
   - **Principio orientador explicito do usuario** (vale pra todo o sistema, nao so ETFs): o objetivo e ser motor de criterio/filtro/decisao fria e assertiva, NAO ferramenta de trade.
   - **Fonte de dados validada**: Investidor10, dois endpoints que fazem scraping simples SEM trava de login (diferente do StatusInvest): `investidor10.com.br/etfs?page=N` (Nacionais, 3 paginas, ~191 ETFs total) e `investidor10.com.br/etfs-global/?order=vol&dir=desc&page=N` (Americanos, 2 paginas). Campos disponiveis: ticker, nome, preco, DY atual, variacao 12m/24m/30d/5anos, capitalizacao, numero de cotistas. Descricao longa (o que o ETF replica) so na pagina individual `/etfs/{ticker}/` ou `/etfs-global/{ticker}/` -- nao vale puxar em massa, so sob demanda pros que sobreviverem ao filtro.
   - **Criterio de capitalizacao fechado (Nacionais)**: >= R$100M. Aplicado aos 191, sobraram 68 (5 pagadores de dividendo: COIN11, SPYI11, QQQI11, DIVD11, NDIV11 -- + 63 nao-pagadores).
   - **Filtro final de escopo (Nacionais) feito manualmente pelo usuario em cima dos 68**: reduziu pra **27 ETFs** eliminando redundancia (so o maior de cada categoria/indice replicado). Lista fechada: BOVA11, BOVV11, SMAL11, PIBB11 (indice Brasil); IVVB11, NASD11, SPXR11, SPXH11, TECK11 (indice/setor americano); LFTB11, LFTS11, LFTI11, LLFT11, IMAB11, IRFM11, B5P211, B5MB11, IB5M11 (renda fixa/Tesouro); HASH11, QBTC11, BITI11, BITH11, ETHE11 (cripto); GOLD11, MARG11 (ouro/commodities); DOLA11 (cambio); WRLD11, XINA11, USAL11, PACG11 (internacional); + os 5 pagadores acima = 27 total.
   - **Universo Americano (Investidor10 `/etfs-global/`)**: sem filtro de capitalizacao aplicavel (escala em bilhoes torna R$100M irrelevante) -- usuario decidiu manter so o maior de cada categoria/estrategia direto. **26 fechados**: VOO, VTI, QQQ, JEPI, JEPQ, VT, VUG, VTV, SCHD, VGT, SMH, VEA, VWO, IJR, IJH, GLD, SLV, IBIT, VNQ, BND, SGOV, TLT, JPST, XLE, EWJ, EWY.
   - **6 ETFs Nacionais NAO classificados** (ficaram de fora dos 27, usuario nao decidiu still): IDKA11, FIND11, UTEC11, DEBB11, IMBB11, PHIP11 -- confirmar o que replicam antes de decidir incluir/descartar.
   - **Classificacao de risco definida (10 niveis, Alto->Baixo)**: 1-Cripto, 2-Setorial/tematico concentrado, 3-Small/Mid cap, 4-Indice amplo/large cap, 5-Real Estate, 6-Dividendo/Value defensivo, 7-Commodities/protecao, 8-High income (covered call, DY alto via opcoes), 9-Renda fixa longa/duration, 10-Renda fixa curta/cash equivalent. Tag SEPARADA de "paga dividendo" (sim/nao) cruza os 2 eixos -- NAO e uma categoria de risco propria (decisao explicita: pagador de dividendo atravessa todas as categorias, ex COIN11 paga 45% mas e risco 1/cripto).
   - **Volatilidade calculada (GARCH) como refinamento futuro**: aventado como alternativa mais objetiva a classificacao manual por categoria, reaproveitando o motor GARCH ja existente no app. NAO implementado, fica pra quando a aba for codada de verdade -- calcular por script, nao um a um em chat.
   - **Pendencia**: completar campos de variacao 12m/24m que ficaram incompletos nos ETFs nao-pagadores dos 27 fechados antes de codar o ranking (so peguei detalhado nos primeiros 20 por volume).
   - **Metodologia Bazin — nota lateral registrada durante o trabalho**: nosso calculo usa DY ultimos 12 meses (`preco_bazin = DY*preco/0.06`, proxy.py linha ~2343), enquanto Investidor10 usa media de dividendos dos ULTIMOS 5 ANOS. Para ativos ciclicos (ex PETR4, anos excepcionais 2022-2023 puxando a media pra cima -- confirmado R$131,90 vs nosso R$40), isso gera divergencia grande. Decisao: manter nossa abordagem de 12 meses, mais conservadora e adequada a ciclicos -- nao mudar.
5. **Fora de escopo por enquanto — ETFs via Binance (RWA/tokenizado)**: dois produtos distintos identificados: (a) **bStocks** (sintetico, emitido por BTech Holdings/afiliada Binance, NAO confere propriedade nem voto, lancado jun/2026, catalogo pequeno ainda, so 1 ETF listado ate agora -- MUB); (b) **acesso direto 7.000+ acoes/ETFs** (produto separado, mais solido -- custodia real via **Alpaca Securities LLC**, broker americano regulado, Binance so roteia via Nest Trading Limited como introducing broker). Nao existe lista publica raspavel do catalogo completo (pagina `binance.com/en/stocks-landing` e so marketing, ~15 tickers de exemplo). Se usuario quiser explorar no futuro, precisa puxar os tickers manualmente de dentro do app pra eu pesquisar individualmente -- sem automatizacao possivel de fora.

## Itens confirmados apos fechamento inicial desta sessao (02/07/2026)
- Bugfix do timestamp: confirmado visualmente pelo usuario, linha de preco real aparecendo nas fotos.
- Duplicatas do lote 01/07: as 8 analises antigas sem foto foram rejeitadas no ranking.
- Item 4 completo (revisao de telas 22/06): TODOS os subitens resolvidos — expandir/ocultar em "Abertura Mercado EUA"/"Top Bovespa"/Commodities; % variacao Nubank; divergencia VIX/DXY vs fonte do usuario; lazy load em Papeis; confirmacao 3 vs 4 metodos de valuation em BDRs; regressao de performance vol. simples ROXO34.
- Item 5: logica do % de variacao em R$ nas Posicoes Ativas — explicada/confirmada, resolvido.
- Cotacoes tab publica (item de longo prazo, fora da lista numerada) — usuario mencionou como resolvido em 02/07/2026, mas sem detalhe do que foi feito; confirmar escopo exato se relevante numa proxima sessao.
- **Teto de analises por lote — CONFIRMADO/FECHADO**: nao ha limitacao tecnica real no Render pra VISUALIZAR o ranking (GET /analises so le JSON, nao recalcula Monte Carlo -- bandas ja vem congeladas da criacao). O teto de 15 e so pra RODADAS DE REGISTRO (POST /analises em loop no Eruda), por seguranca de timeout/rate-limit, nao por limite real. Usuario pode acumular quantos itens quiser em Em Analise sem problema.

## Backlog de medio prazo (sem prioridade fechada, decidir a cada sessao)
- Historico mensal completo de dividendos na Carteira FIIs — **DESCARTADO 02/07/2026**: StatusInvest so tem totais semestrais via scraping simples (regex), o breakdown mes-a-mes fica atras de chamada assincrona/JS que nao consigo capturar de fora. Usuario decidiu que nao vale o esforco pra uma informacao complementar (ja acessa via detalhe do fundo quando precisa).
- Varredura/limpeza de fundos "lixo" (FIIs mortos/incorporados) na Carteira FIIs — usuario vai estudar criterios e trazer numa proxima sessao; Claude tambem deve propor criterios quando o assunto voltar.
- Ranking de ETFs — ver item 4 do backlog imediato acima (pesquisa pronta, falta codar).
- ETFs via Binance/RWA — ver item 5 do backlog imediato acima.
- Encerradas para FIIs (comportamento ainda nao definido)
- Visao multi-usuario (so se virar produto)
- Renda fixa (so registro, sem acao por enquanto)
- Analisar a empresa ORVR3 (pedido do usuario 02/07/2026, sem contexto/motivo especificado ainda -- perguntar o que despertou o interesse quando for pauta)



## Posicoes ativas atuais (positions.json, 7 no total)
| ID | Ticker | Tipo | Exercicio | Vencimento | Obs |
|---|---|---|---|---|---|
| pt | PETR4 | simples (call vendida) | europeia | 17/12/2026 | sem meta de ganho, objetivo e rollover |
| vl | VALE3 | bidirecional | europeia | 18/02/2027 | sem meta de ganho, objetivo e rollover |
| a3 | AXIA3(A) | bidirecional | europeia | 14/09/2026 | entry ~54,31 |
| a3b | AXIA3(B) | bidirecional | europeia | 02/10/2026 | entry ~50,65 |
| bb | BBAS3 | retorno_controlado | europeia | 20/08/2026 | meta 2,25% |
| bslv39 | BSLV39 | retorno_controlado | europeia | — | vol_impl=null, historico insuficiente no Yahoo |
| rx2 | ROXO34 (ROXOI107) | simples (call vendida, rolagem) | EUROPEIA | 17/09/2026 | meta 2,44%, rolagem defensiva pos-fracasso, "seca" |

## Encerradas relevantes recentes
- ROXO34 (ROXOG105, strike R$10,50): status "fracasso" — estourou a barreira, opcao era AMERICANA.

## Principios tecnicos ja estabelecidos (nao re-abrir sem novo contexto)
- GARCH(1,1) grid search = MLE continuo em todos os testes — nao vale refinar.
- Heston inviavel sem book de opcoes pago. Jump-Diffusion: estudo futuro, baixa prioridade.
- Fundamentais hardcoded (`FUND_DATA_REF`): ref. 22/05/2026, aviso automatico apos 90 dias.
- Fase A (chat, numeros ainda abertos) vs Fase B ("tirar a foto", 4 numeros fechados: ticker/prazo/strike-range/premio) — sempre questionar se algum numero parecer em aberto antes de registrar.
- PDFs de propostas reais do banco: numeros sao premissa fixa, nunca recalcular/escalar — so o vencimento e reprojetado a partir de hoje.
- Regua de bidirecionais novas (a partir de 22/06/2026): teto >= ~1%/mes proporcional ao prazo.
- Grades de opcoes do OpLab: sempre apresentar os 2 lados (call coberta E put vendida).
- Perfil do usuario: ~70% posicoes ativas sao estruturas arrojadas (bidirecional/retorno controlado), ~30% sao simples derivadas (quando a estrutura arrojada rompe e vira venda de opcao pra ganhar tempo).
- Ao registrar analises, sempre incluir a data do lote de origem no nome/observacao (ex: "Lote 01/07/2026").
