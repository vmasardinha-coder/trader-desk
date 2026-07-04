# Trader Desk — Prompt de Continuação (v20.0 — sessão 03/07/2026)

## Stack
- Flask no Render (free tier): https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk (branch: main)
- Token GitHub de SESSÃO (Claude usa em chat, colado pelo usuário): classic, escopo `repo`, válido 90 dias a partir de 02/07/2026
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho): fine-grained, restrito SÓ ao repo trader-desk, permissão "Contents: Read and write", configurado como `GITHUB_TOKEN` no Render. **PENDÊNCIA AINDA ABERTA (item #1 do backlog): criar token fine-grained sem vencimento curto para substituir o atual (processo: GitHub → Settings → Developer Settings → Fine-grained tokens → só trader-desk → Contents R/W)**
- Deploy: GET SHA → PUT base64 via API do GitHub. HTML em templates/, JS em static/app.js
- Console de debug: Eruda ativo no index.html para validação mobile — usuário confirmou fluxo de POST manual via `fetch()` + `localStorage.getItem('api_write_token')` como `Authorization: Bearer <token>`, funciona bem para registrar análises de teste/lote sem passar pelo formulário do app
- **REGRA CRÍTICA DE PROCESSO**: usar `api.github.com/repos/.../contents/...` para ler arquivos que foram editados NA MESMA sessão — nunca `raw.githubusercontent.com` para isso (CDN cache causa leituras desatualizadas e pode reverter mudanças ao re-editar)
- **LIMITAÇÃO DE AMBIENTE CONFIRMADA (02/07/2026)**: o sandbox de execução do Claude (bash_tool) só acessa domínios de pacotes (github.com, api.github.com, pypi.org, npmjs.com etc) — NÃO acessa `trader-desk.onrender.com` nem `finance.yahoo.com`. Isso significa que Claude NÃO consegue chamar `POST /analises` (ou qualquer rota Flask) diretamente, nem buscar preço/histórico via Yahoo no sandbox. Duas consequências práticas: (1) quando Claude precisa registrar uma análise nova a partir de um lote decidido em chat, o caminho é ESCREVER DIRETO no `analises.json`/`positions.json` via GitHub Contents API (contorna o Flask) — mas isso PULA o congelamento automático de bandas (backlog #4), que só roda dentro da rota Flask; (2) para testar de verdade o congelamento de bandas, o USUÁRIO precisa rodar o `fetch()` manual pelo Eruda, não Claude. Se no futuro o domínio do Render for liberado no sandbox, isso deixa de ser necessário.

## SHAs no fechamento desta sessão (03/07/2026, apos Prioridade 2 fase 1+2 da modularizacao)
- proxy.py: e2d484afc1d0f76443992a7ac2103d8b0f1e6581
- static/app.js: dd5b4b2fc1eded93c8439f7e44cca67ab3a309d2
- templates/index.html: 3950b10eb59d1a9c07432426afeb063914206a7a (inalterado nesta sessao)
- fundamentos.json: e0dc2a4d0c3cb2bf04ebf258536e36ef2a319805
- motor.py: 035fa085a6916080a0122d46a7c1c343a3390e35 (NOVO -- nucleo estatistico)
- fontes_etfs.py: c21f836de7d50f986309d604f1d46d4e6922c9fc (NOVO -- universo ETFs + scraping/fetch)

**PRATICA DE BACKUP (pedido explicito do usuario 03/07/2026):** cada arquivo
tocado tem seu SHA anotado aqui ANTES e DEPOIS de cada edicao. Isso ja
funciona como backup completo -- reverter e so fazer PUT com o conteudo
do SHA anterior. Sempre guardar o SHA de "antes" no raciocinio da sessao,
nao so o de "depois", para rollback ser trivial se algo quebrar.
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

## Itens CONCLUIDOS nesta sessao (03/07/2026)

### 1. Carteira de ETFs interativa (era pendencia tecnica da v18)
- **Card de resumo agregado** no topo: total investido, valor atual, retorno %, e volatilidade da carteira com CORRELACAO REAL (matriz de covariancia dos retornos historicos alinhados por data entre os ETFs, ponderada por valor) -- decisao explicita do usuario: "realista", nao soma simples. Mostra tambem quanto a diversificacao esta descontando vs cenario 100% correlacionado.
- **Cards individuais clicaveis** -> painel com fan chart de projecao GARCH (bandas p10-p90, periodos 21/60/90/180d), mesmo padrao visual da Foto do Papel, SEM meta/barreira (ETF e buy-and-hold).
- Rotas novas: `GET /etfs/carteira/resumo` e `GET /etfs/carteira/<ticker>/projecao`.
- **LIMITACAO ACEITA PELO USUARIO**: nao ha campo de quantidade de cotas em etfs_estado.json -- peso assume 1 cota por posicao. Usuario confirmou que esta ok por enquanto ("como referencia"); se um dia quiser peso real, adicionar campo `quantidade` em /etfs/mover + resumo.
- Botoes "+ Em Analise" e "OK -> Carteira" estilizados (estavam brancos, sem CSS).

### 2. Saga do DY dos ETFs (bug reportado: BOVA11 com 10000%/3300%)
Historico completo da investigacao (importante pra nao repetir caminhos que falharam):
- (a) Primeira tentativa: mapear colunas da tabela do investidor10 pelo NOME do header (<th>) em vez de indice fixo -- **PIOROU** (pagina tem mais de um thead/tabela, header lido nao correspondia as linhas). Revertido.
- (b) Segunda camada: `_dy_plausivel` (trava de sanidade, DY fora de [0,100] vira None) -- parou de mostrar lixo, mas ETFs pagadores tambem ficaram sem DY, confirmando que o indice fixo tambem estava errado.
- (c) **SOLUCAO FINAL**: DY via Yahoo Finance (`quoteSummary/summaryDetail.dividendYield`, JSON estruturado, mesmo dominio ja usado pra preco/historico) em `_fetch_dy_yahoo` + `_fetch_etfs_dy_yahoo_bulk`. Elimina a classe de bug por completo (nao depende de coluna). Investidor10 vira fallback.
- **BUG CRITICO NO MEIO DO CAMINHO**: primeira versao do bulk usou `with ThreadPoolExecutor` + `ex.map` -- o `with` espera TODAS as ~61 threads terminarem, estourou o timeout do Render e derrubou `/etfs` com 502. Corrigido com ORCAMENTO DE TEMPO FIXO (~9s) via `concurrent.futures.wait` + `shutdown(wait=False)`: o que responder a tempo entra, o resto e descartado sem travar (cache de 15min tenta de novo depois). **PRINCIPIO FORMALIZADO: nenhuma rota pode depender de fonte externa responder pra devolver 200 -- sempre orcamento de tempo + fallback degradado.**
- **PENDENTE DE VALIDACAO pelo usuario**: conferir DY de BOVA11/WRLD/NDIV11 apos deploy.

### 3. ORVR3 incorporada ao sistema
- Watchlist de Papeis: novo segmento "Residuos & Economia Circular" com ORVR3 (app.js, array WATCHLIST).
- Padronizada nos metodos de precificacao: fundamentos completos + setor cadastrados (agora em fundamentos.json). LPA negativo -> Graham None (esperado). Detalhes da triagem/regua de reentrada: ver backlog de medio prazo.

### 4. PRIORIDADE 1 DA MODULARIZACAO EXECUTADA: fundamentos.json como fonte unica
- Analise de arquitetura feita nesta sessao (metricas reais): proxy.py 6.964 linhas/54 rotas, app.js 4.127 linhas/130 funcoes, fundamentos duplicados em 6 lugares, maiores funcoes com 400-500 linhas.
- Extraidos TODOS os fundamentos hardcoded para `fundamentos.json` (raiz do repo): fundamentos por ativo (18 ativos, incl. ev_ebitda/debt_ebitda/margem dos 5 originais), setores (18+DEFAULT), dy_extra (ALOS3), sem_dy_relevante, vol_defaults, fund_data_ref.
- proxy.py le o JSON no startup (`_carregar_fundamentos`, com fallback embutido minimo se arquivo faltar -- app nunca deixa de subir por causa disso). Removidos: FUND e SETORES do topo (eram CODIGO MORTO, nunca lidos), vol_defaults inline, FUND_OVERRIDE, SETOR_MAP, FUND_EXTRA (dentro de get_indicators), FUND_OVERRIDE_GLOBAL/_SEM_DY_RELEVANTE (viraram aliases de DY_GLOBAL/SEM_DY_RELEVANTE derivados do JSON).
- Validacao: espot-check completo dos 18 ativos campo a campo contra os valores antigos (zero divergencia) + execucao real do loader + checagem de rotas duplicadas.
- **ATUALIZACAO TRIMESTRAL DE FUNDAMENTOS AGORA = 1 COMMIT NO fundamentos.json** (Claude pode fazer via Contents API sem tocar em codigo).

## Plano de modularizacao aprovado (03/07/2026) -- executar em fases, uma por sessao
Analise completa de engenharia feita e aprovada pelo usuario. Ordem de retorno sobre esforco:
1. ~~**Prioridade 1** -- dados fora do codigo (fundamentos.json)~~ **EXECUTADA 03/07/2026** (ver acima). **PENDENTE VALIDACAO NO AR** (usuario testar aba Papeis/indicadores apos deploy).
2. **Prioridade 2** -- modularizar proxy.py em 4-5 arquivos: `motor.py` (GARCH/Monte Carlo/Graham-Bazin, nucleo fechado), `fontes.py` (24 fetches Yahoo + Bacen + scrapers), `rotas_etfs.py`, `rotas_fiis.py`, proxy.py so app+rotas core. UM MODULO POR SESSAO, validando no ar antes do proximo (licao beautifulsoup4). Pre-requisito para multi-usuario futuro.
3. **Prioridade 3** -- layout profissional sem framework: (a) agrupar 10 abas em 3 familias (Mercado / Minha Operacao / Agenda) com navegacao de 2 niveis (padrao dos subtabs de ETFs ja existente); (b) unificar linguagem visual dos cards (30-40 linhas de classes CSS reutilizaveis: .card, .card-titulo, .badge-pct); (c) header fixo com resumo do dia (IBOV, dolar, SELIC, P&L das posicoes).
4. **NAO fazer** (decisao registrada): React/Vue (reescrita, ganho marginal p/ 1 usuario), banco de dados (GitHub-as-storage e auditavel por design), TypeScript, testes formais. Multi-usuario depende da Prioridade 2 primeiro.

## Prioridade 2 da modularizacao -- progresso (03/07/2026)
Plano original (ver secao anterior "Plano de modularizacao aprovado"): 4-5 modulos, um por sessao, validando no ar antes do proximo.

- **Fase 1 CONCLUIDA**: `motor.py` -- nucleo estatistico puro (RSI/MM/EMA/MACD/Bollinger/OBV, Graham, vol_hist, GARCH(1,1), bandas de projecao GBM, score de assertividade). Zero dependencia de Flask/rede/disco. proxy.py: -194 linhas.
- **Fase 2 CONCLUIDA**: `fontes_etfs.py` -- universo fechado dos 61 ETFs (ETF_UNIVERSO) + todo o cluster de parsing/scraping (parse numerico BR, scraping investidor10 nacional/americano, DY via Yahoo estruturado, fetch de serie historica por data). proxy.py: -270 linhas.
- proxy.py total: 6.940 -> 6.476 linhas (-464, -6.7%) so nessas duas fases.

**METODO DE VALIDACAO usado em cada fase (repetir sempre)**:
1. Baixar proxy.py + modulos direto do GitHub via api.github.com (nunca confiar em cache local)
2. Importar o modulo de verdade (`importlib.util.spec_from_file_location` + `exec_module`) -- NAO basta `ast.parse`, isso so pega erro de sintaxe, nao de import faltando (foi assim que passou batido o `ModuleNotFoundError: flask_cors` na primeira tentativa desta sessao)
3. Contar rotas registradas no `app.url_map` de verdade e conferir que as criticas estao la
4. Checar ausencia de rotas duplicadas
5. Chamar as funcoes migradas com valores de teste conhecidos pra confirmar que o comportamento nao mudou
6. Commitar
7. **Baixar de novo do GitHub (nao do cache local) e repetir o boot test** -- garante que o que esta commitado e exatamente o que foi validado, nao uma versao local que "parecia certa"

**Proximas fases (ordem sugerida, nao obrigatoria)**:
- Fase 3: `fontes.py` geral -- os ~15 fetches restantes (Yahoo fundamentals/quotes, Bacen/CDI, scrapers de FIIs -- fundamentus/statusinvest/8marketcap, BTC onchain). Mais delicada que as duas primeiras: mais acoplamento com cache e headers repetidos.
- Fase 4: `rotas_fiis.py` -- rotas de FIIs (get_fiis, buscar_fii, ranking_fiis_em_analise, carteira_fiis*, get_fii_infra, etc.)
- Fase 5: `rotas_etfs.py` -- rotas de ETFs (get_etfs_watchlist, mover_etf, get_etf_carteira_*) -- pode aproveitar e ficar fino agora que fontes_etfs.py ja existe.
- Depois disso, proxy.py vira essencialmente so: app Flask + rotas core de posicoes/analises/montecarlo + imports dos modulos.

**BUG CORRIGIDO NO MEIO DO CAMINHO desta sessao (antes das fases acima)**: apos a Prioridade 1 (fundamentos.json), o usuario reportou varias abas nao carregando. Causa raiz: NAO era a migracao do JSON (essa validou limpa) -- era o worker unico do Render free tier ficando bloqueado pelo bulk de DY do Yahoo (~9s) SOMADO ao scraping do investidor10 (ate 75s no pior caso, 5 paginas x 15s). Corrigido: bulk de DY movido para thread de fundo (`_refresh_dy_yahoo_background`, nao bloqueia a resposta) + timeout dos scrapers reduzido de 15s para 6s por pagina. **PRINCIPIO REFORCADO: o Render free tier so aceita 1 requisicao por vez -- qualquer rota lenta trava TODAS as outras, nao so a propria.**

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
- ~~Analisar ORVR3~~ **TRIADO EM 03/07/2026 pelo proprio usuario** (dados puxados por ele): tese de crescimento/assimetria (residuos, biometano, creditos de carbono, incorporacao Vital), NAO e papel de renda (DY 0). Decisao: RADAR, nao comprar agora. Zona de reentrada definida por ele: correcao pra R$70-72 OU proximo resultado confirmando aceleracao do EBITDA proforma pos-Vital. Acima de R$79 nao corre atras. Posicao satelite se entrar. ORVR3 ja esta na watchlist de Papeis (segmento Residuos & Economia Circular) e padronizada nos metodos de precificacao (fundamentos.json) -- ATENCAO: LPA negativo (-0,87) faz Graham retornar None, esperado e nao bug (fundamentos incertos pos-incorporacao Vital, fontes divergem).



## Posicoes ativas atuais (positions.json, 7 no total)
| ID | Ticker | Tipo | Exercicio | Vencimento | Obs |
|---|---|---|---|---|---|
| pt | PETR4 | simples (call vendida) | europeia | 17/12/2026 | sem meta de ganho, objetivo e rollover |
| vl | VALE3 | bidirecional | europeia | 18/02/2027 | sem meta de ganho, objetivo e rollover |
| a3 | AXIA3(A) | bidirecional | europeia | 14/09/2026 | entry ~54,31 |
| a3b | AXIA3(B) | bidirecional | europeia | 02/10/2026 | entry ~50,65 |
| bb | BBAS3 | retorno_controlado | europeia | 20/08/2026 | meta 2,25% |
| bslv39 | BSLV39 | retorno_controlado | europeia | — | vol_impl=null, historico insuficiente no Yahoo |
| rx | ROXO34 (ROXOI107) | simples (call vendida, rolagem) | EUROPEIA | 17/09/2026 | meta 2,44%, rolagem defensiva pos-fracasso, "seca" -- id SEMPRE `rx` (logica hardcoded no app.js) |

## Encerradas relevantes recentes
- ROXO34 (ROXOG105, strike R$10,50): status "fracasso" — estourou a barreira, opcao era AMERICANA.

## Principios tecnicos ja estabelecidos (nao re-abrir sem novo contexto)
- GARCH(1,1) grid search = MLE continuo em todos os testes — nao vale refinar.
- Heston inviavel sem book de opcoes pago. Jump-Diffusion: estudo futuro, baixa prioridade.
- Fundamentais em `fundamentos.json` (fonte UNICA desde 03/07/2026, antes eram 6 copias no proxy.py): ref. 22/05/2026 (`fund_data_ref` no JSON), aviso automatico apos 90 dias. Atualizacao trimestral = 1 commit no JSON, sem tocar em codigo.
- Fase A (chat, numeros ainda abertos) vs Fase B ("tirar a foto", 4 numeros fechados: ticker/prazo/strike-range/premio) — sempre questionar se algum numero parecer em aberto antes de registrar.
- PDFs de propostas reais do banco: numeros sao premissa fixa, nunca recalcular/escalar — so o vencimento e reprojetado a partir de hoje.
- Regua de bidirecionais novas (a partir de 22/06/2026): teto >= ~1%/mes proporcional ao prazo.
- Grades de opcoes do OpLab: sempre apresentar os 2 lados (call coberta E put vendida).
- Perfil do usuario: ~70% posicoes ativas sao estruturas arrojadas (bidirecional/retorno controlado), ~30% sao simples derivadas (quando a estrutura arrojada rompe e vira venda de opcao pra ganhar tempo).
- Ao registrar analises, sempre incluir a data do lote de origem no nome/observacao (ex: "Lote 01/07/2026").
