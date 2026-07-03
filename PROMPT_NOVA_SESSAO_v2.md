# Trader Desk — Prompt de Continuação (v18.0 — sessão 02/07/2026)

## Stack
- Flask no Render (free tier): https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk (branch: main)
- Token GitHub de SESSÃO (Claude usa em chat, colado pelo usuário): classic, escopo `repo`, válido 90 dias a partir de 02/07/2026
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho): fine-grained, restrito SÓ ao repo trader-desk, permissão "Contents: Read and write", configurado como `GITHUB_TOKEN` no Render. **PENDÊNCIA AINDA ABERTA (item #1 do backlog): criar token fine-grained sem vencimento curto para substituir o atual (processo: GitHub → Settings → Developer Settings → Fine-grained tokens → só trader-desk → Contents R/W)**
- Deploy: GET SHA → PUT base64 via API do GitHub. HTML em templates/, JS em static/app.js
- Console de debug: Eruda ativo no index.html para validação mobile — usuário confirmou fluxo de POST manual via `fetch()` + `localStorage.getItem('api_write_token')` como `Authorization: Bearer <token>`, funciona bem para registrar análises de teste/lote sem passar pelo formulário do app
- **REGRA CRÍTICA DE PROCESSO**: usar `api.github.com/repos/.../contents/...` para ler arquivos que foram editados NA MESMA sessão — nunca `raw.githubusercontent.com` para isso (CDN cache causa leituras desatualizadas e pode reverter mudanças ao re-editar)
- **LIMITAÇÃO DE AMBIENTE CONFIRMADA (02/07/2026)**: o sandbox de execução do Claude (bash_tool) só acessa domínios de pacotes (github.com, api.github.com, pypi.org, npmjs.com etc) — NÃO acessa `trader-desk.onrender.com` nem `finance.yahoo.com`. Isso significa que Claude NÃO consegue chamar `POST /analises` (ou qualquer rota Flask) diretamente, nem buscar preço/histórico via Yahoo no sandbox. Duas consequências práticas: (1) quando Claude precisa registrar uma análise nova a partir de um lote decidido em chat, o caminho é ESCREVER DIRETO no `analises.json`/`positions.json` via GitHub Contents API (contorna o Flask) — mas isso PULA o congelamento automático de bandas (backlog #4), que só roda dentro da rota Flask; (2) para testar de verdade o congelamento de bandas, o USUÁRIO precisa rodar o `fetch()` manual pelo Eruda, não Claude. Se no futuro o domínio do Render for liberado no sandbox, isso deixa de ser necessário.

## SHAs no fechamento desta sessão (02/07/2026, apos aba ETFs completa e validada)
- proxy.py: a0187da9623df1ae29380c71a8125662b530fb99
- static/app.js: fb7387f7691621903c51846d6847887964244aac
- templates/index.html: 3950b10eb59d1a9c07432426afeb063914206a7a
- static/style.css: 61ef8928448b18e1582aff710da2cbc4a5992d01
- requirements.txt: 149f508144c7f8dfb852f83af4b8325711e29ff3 (SEM beautifulsoup4 -- nao adicionar de novo, ver licao critica no item 4)
- positions.json: c462e0a7b4d666e0c3f6b6e165f7df767d4a23ed (7 posições ativas, 4 encerradas)
- analises.json: 5e638624371ec107611b90d63ca052452e1e66e6 (54 registros — 8 duplicadas antigas já rejeitadas)
- etfs_estado.json: novo arquivo criado nesta sessão via /etfs/mover (em_analise e carteira de ETFs)

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
4. ~~Nova aba "ETFs"~~ **IMPLEMENTADO E VALIDADO 02/07/2026** (posicionada ANTES da aba FIIs). Arquitetura de fluxo Watchlist -> Em Analise -> Carteira, exatamente como desenhado. Detalhes finais:
   - **Universo fechado real: 61 ETFs** (35 Nacionais + 26 Americanos) -- CORRECAO IMPORTANTE: em algum momento da sessao o Claude somou errado e disse "27 Nacionais / 53 total" ao usuario; a lista de tickers aprovada item-a-item pelo usuario sempre foi maior, a soma que deu 27 estava incorreta. O numero certo, que reflete o codigo em producao, e 35 Nacionais + 26 Americanos = 61. Lista completa esta em `ETF_UNIVERSO` no proxy.py.
   - **Watchlist**: tabela com todos os 61, campos ticker/mercado/categoria/desc/DY/var12m/var24m/cap/risco. Filtros por mercado, por risco (10 niveis), checkbox "so pagadores". Ordenacao por clique em qualquer coluna. Botao "Atualizar" com estilo padronizado (igual botao Atualizar de FIIs).
   - **Em Analise**: usuario manda manualmente da watchlist (sem calculo ao entrar). Mesma tabela + coluna Score (destacada), calculado dentro de cada faixa de risco (nao mistura risco 1 com risco 10). Formula do score hoje e simples (combina DY + var12m normalizados) -- volatilidade real via GARCH fica como refinamento futuro, nao implementado ainda.
   - **Carteira**: card estatico simples (ticker, preco entrada, data entrada, preco atual, variacao %). CONFIRMADO COM O USUARIO QUE E ESCOPO REDUZIDO DE PROPOSITO nesta entrega -- NAO tem clique/interacao (nao abre grafico, nao tem "tirar foto" de verdade tipo Posicoes Ativas), e NAO tem card de resumo/total agregado (tipo o que existe em Carteira FIIs). Ambos ficam como proximo passo, nao fazer sem alinhar com usuario antes.
   - **Fonte de dados**: Investidor10, dois endpoints validados via scraping regex puro (SEM bs4/BeautifulSoup -- NUNCA adicionar essa dependencia no requirements.txt, foi tentado nesta sessao e derrubou o app inteiro em producao, ver "licao critica" abaixo). Colunas Nacionais (`/etfs?page=N`, 3 paginas) e Americanas (`/etfs-global/?order=vol&dir=desc&page=N`, 2 paginas) tem ORDEM DIFERENTE -- ver funcoes `_scrape_investidor10_etfs_nacional` e `_scrape_investidor10_etfs_americano` no proxy.py, cada uma com sua propria docstring mapeando os indices de coluna. Americana NAO tem coluna de preco na listagem (preco fica sempre None pros 26 Americanos -- limitacao aceita, nao vale puxar pagina individual so por isso).
   - **Rotas finais em producao**: `GET /etfs` (watchlist com dado ao vivo, cache 15min), `GET /etfs/live-status` (diagnostico rapido: quantos dos 61 vieram com dado), `GET /etfs/estado` (le em_analise/carteira), `POST /etfs/mover` (move ticker entre estados, salva em `etfs_estado.json` via GitHub). Endpoints de debug (`/etfs/debug`, `/etfs/debug-us`) foram REMOVIDOS depois de validados -- se precisar recriar pra investigar parser no futuro, o padrao esta documentado nas funcoes de scrape.
   - **6 ETFs Nacionais historicamente mencionados como "nao classificados"** (IDKA11, FIND11, UTEC11, DEBB11, IMBB11, PHIP11) -- NAO entraram no universo fechado de 35, ficaram de fora. Se usuario quiser incluir, e adicao nova ao `ETF_UNIVERSO`, nao um resgate de algo pendente.
   - **Classificacao de risco (10 niveis, Alto->Baixo)**: 1-Cripto, 2-Setorial/tematico concentrado, 3-Small/Mid cap, 4-Indice amplo/large cap, 5-Real Estate, 6-Dividendo/Value defensivo, 7-Commodities/protecao/cambio, 8-High income (covered call, DY alto via opcoes), 9-Renda fixa longa/duration, 10-Renda fixa curta/cash equivalent. Tag SEPARADA "paga dividendo" (sim/nao) cruza os 2 eixos, nao e categoria de risco propria.
   - **Metodologia Bazin — nota lateral registrada durante a pesquisa**: nosso calculo usa DY ultimos 12 meses (`preco_bazin = DY*preco/0.06`, proxy.py), Investidor10 usa media de dividendos dos ULTIMOS 5 ANOS. Para ciclicos (ex PETR4, anos excepcionais 2022-2023) isso gera divergencia grande (R$131,90 vs nosso R$40, confirmado). Decisao: manter nossa abordagem de 12 meses -- nao mudar.
   - **LICAO CRITICA desta sessao, vale pra qualquer trabalho futuro no proxy.py**: (1) NUNCA adicionar dependencia nova ao requirements.txt sem testar isoladamente primeiro -- `beautifulsoup4` foi adicionado, o app inteiro caiu (502 em TODAS as rotas, nao so a nova), precisou de revert emergencial completo (proxy.py+app.js+index.html+style.css+requirements.txt) pra recuperar. (2) Depois de qualquer edicao no proxy.py via str_replace, alem de `ast.parse` (checa so sintaxe), validar TAMBEM que as funcoes/rotas esperadas continuam existindo (`ast.walk` procurando `FunctionDef` pelos nomes esperados) e que nao ha `@app.route` duplicado (path+methods repetidos quebra o boot do Flask) -- um `str_replace` mal calibrado apagou a rota `/etfs` inteira nesta sessao sem quebrar a sintaxe (o corpo da funcao virou codigo morto dentro de outra funcao), e isso so foi pego rodando o app de verdade, nao no syntax check. (3) Deploy em fases quando a mudanca for arriscada: primeiro so backend (sem tocar frontend), validar via endpoint de debug/diagnostico, DEPOIS religar frontend -- isso limitou o dano nesta sessao a rodadas menores em vez de derrubar tudo de novo.
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
