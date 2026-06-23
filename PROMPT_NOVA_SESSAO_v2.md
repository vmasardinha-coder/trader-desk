# Trader Desk — Prompt de Continuação (v10.16 — Sprint 4/5 entregues)

## Stack
- Flask no Render: https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk
- Token brapi (gratuito, 15k req/mês): configurado via `BRAPI_HEADERS` em proxy.py
- Token GitHub de ESCRITA MANUAL (Claude usa em sessão, colado pelo usuário): classic, escopo `repo`, expira 14/07/2026 — RENOVAR ANTES DESSA DATA
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho): fine-grained, restrito SÓ ao repo trader-desk, permissão SÓ "Contents: Read and write", configurado como variável de ambiente `GITHUB_WRITE_TOKEN` no painel do Render
- Deploy: GET SHA → PUT base64 via API do GitHub. HTML em templates/, JS em static/app.js, CSS em static/style.css
- Console de debug: Eruda permanece ativo no index.html para validação mobile
- Sandbox de teste (bash_tool) NÃO acessa brapi.dev/trader-desk.onrender.com/Yahoo direto — só raw.githubusercontent.com e domínios de pacote. Testar lógica nova com mocks locais (jsdom para JS, mock de requests para Python) antes do deploy.

## SHAs no momento do fechamento desta sessão (22/06/2026)
- proxy.py: 8230d88a32ab (v10.16)
- templates/index.html: f4eb15b97faf
- static/app.js: 668588f08a8a
- static/style.css: 2e6b7bc0f2dd (não tocado nesta sessão)
- positions.json: 584d8f955de8
- analises.json: 50884ff8214e (7 análises registradas)
- montecarlo_garch.py: 31bdb9470821 (não tocado nesta sessão)
- FLUXO_FASE_A_FASE_B.md: a746c590465e (não tocado nesta sessão)

## ⚠️ Regras críticas de processo — ler antes de qualquer coisa

### 1. Fluxo Fase A / Fase B (ler FLUXO_FASE_A_FASE_B.md no repo)
**Fase A** (pré-análise, sempre em chat, nunca via botão): os 4 números-chave (ticker, prazo, strike/range, prêmio) ainda em aberto. **Fase B** ("tirar a foto", grava em analises.json) só depois dos 4 números genuinamente fechados. Se algum número estiver vago, Claude DEVE questionar antes de prosseguir.

### 2. PDFs de propostas reais do banco — NUNCA recalcular
Quando o usuário traz PDF do Itaú ("Material Publicitário") com números já fechados (ganho prefixado, barreira, teto, alavancagem), Claude aceita esses números como PREMISSA FIXA — nunca reescala/recalcula proporcionalmente ao tempo. A ÚNICA coisa que muda é o vencimento, simulado a partir de hoje: (a) se o vencimento original ainda não passou, usa o prazo restante real com os MESMOS números; (b) se já passou, simula o MESMO prazo total a partir de hoje, ainda com os MESMOS números, sem escalar nada. Claude tentou "validar com rigor" via equilíbrio de custo-zero nesta sessão e o usuário rejeitou explicitamente — o PDF já é a Fase A do banco, pronta, só se projeta o tempo.

### 3. Régua de decisão para bidirecionais — 1%/mês proporcional ao prazo
Usuário só aceita bidirecional se o TETO de retorno for ≥ ~1%/mês × meses de prazo (ex: 30d→1%, 90d→3%, 12 meses→9-12%). Essa regra é uma LIÇÃO APRENDIDA depois de um erro real com VALE3 (teto de só 5%/9meses=0.56%/mês) — NÃO é retroativa a exemplos antigos mostrados como referência histórica.

### 4. Apresentação de grades de opções — sempre os 2 lados
Quando o usuário manda uma grade do OpLab (colunas PUT e CALL lado a lado), Claude SEMPRE analisa e apresenta AMBOS os lados (venda de call coberta E venda de put), mesmo que só um tenha sido pedido — comparação sistemática é o que o usuário quer. Perfil declarado do usuário: bom comprador, mau vendedor (tende a "querer mais" e perder o timing na hora de vender) — por isso valoriza a análise objetiva de probabilidade/prêmio para compensar essa fraqueza autodeclarada na venda de call coberta especificamente.

### 5. Mecânica de exercício — americana vs. europeia
Campo `exercicio` ('americana'|'europeia') é OBRIGATÓRIO em qualquer chamada a `/montecarlo`, `/montecarlo/condicional` ou `/montecarlo/posicao_ativa` que envolva `k_call`/`k_put` SEM `kdo`/`kuo` — sem padrão implícito, erro 400 se ausente. Americana = risco de exercício em qualquer momento (usa max/min da trajetória completa); europeia = só no vencimento (usa só preço final). Das posições ativas reais: SÓ ROXO34/ROXOG105 é americana; PETR4, VALE3, BBAS3, AXIA3(A), AXIA3(B) são europeias. Usuário prioriza europeias; a americana foi sem querer/desconhecimento prévio.

## O que mudou nesta sessão (22/06/2026) — resumo cronológico

### Investigação inicial
- Workflow `update_calendar.yml`: causa raiz real das 4 falhas antigas identificada via histórico de commits (erro de indentação YAML + heredoc frágil), já corrigidas antes desta sessão. Limpeza de resíduo `node-version` inválido em `actions/checkout@v4`.

### Sprint 4 — Aba "Em Análise" (entregue e testada)
- Nova aba na navegação, entre Indicadores e Posições Ativas
- Listagem com accordion, badge de status, mudança de status via `PUT /analises/<id>/status`
- Botão "Ver probabilidade atualizada" → `/montecarlo/condicional`
- **NÃO cria foto pelo app** — decisão deliberada, criação continua via chat (Fase A/B)

### Extensões do backend (v10.5 → v10.16), todas em `/montecarlo/condicional` e replicadas em `/montecarlo/posicao_ativa`:
- **v10.5**: `fan_chart` (banda de percentis do dia 0 ao vencimento + série de preços reais desde a foto, alinhados por timestamp Yahoo)
- **v10.6**: `prob_retorno_faixas` para `retorno_controlado` (barreira única + ganho prefixado)
- **v10.7**: `simulacao_100_acoes` (padrão didático fixo, 100 ações, em todos os tipos de estrutura)
- **v10.8**: novo endpoint `/montecarlo/posicao_ativa` (retroativo real desde `data_entrada` + projeção até vencimento, para Posições Ativas)
- **v10.9**: fix `preco_anterior` para BDRs (fallback de histórico Yahoo quando brapi não traz ou traz igual ao atual)
- **v10.10**: campo `exercicio` obrigatório (ver regra crítica #5)
- **v10.11-13**: extensão de meta/100-ações para venda de CALL simples (`k_call` sem `kdo`) — **bug real**: a extensão foi adicionada só em `posicao_ativa`/`montecarlo` na v10.11, faltando em `condicional` até a v10.13 (usuário pegou isso testando)
- **v10.14-15**: bloco `put_resultado_fixo` para venda de PUT (mecânica diferente: "exercida" vira posição NOVA de compra, não retorno fechado — por decisão do usuário, NÃO simulado via Monte Carlo, só a probabilidade de não-exercício usa MC; valor do prêmio é fato fixo, calculado uma vez). Padronizado para 100 ações na v10.15.
- **v10.16**: Commodities (WTI/Ouro/Prata/Cobre via Yahoo `CL=F`/`GC=F`/`SI=F`/`HG=F`) implementada do zero — **nunca tinha tido dados reais**, só o HTML existia.

### Frontend — 4 blocos padronizados, numerados e com divisor visual
Em TODA análise (Em Análise e Posições Ativas), na mesma ordem:
1. Probabilidades — preço da foto/entrada vs. atual, dias
2. Simulação Didática — 100 ações (formatos: defesa/dentro/teto | prefixado/exposto | não-exercida/exercida)
3. Probabilidade de Retorno Final — faixas (<0%, 0-1%, 1-2%, 2-meta%, ≥meta%)
4. Evolução — gráfico fan chart (retroativo real + projeção)
PUT vendida (tipo_estrutura='premio') tem um bloco "2-3" combinado em vez de blocos 2 e 3 separados (mecânica fixa, não simulada).

### Outras correções de UI nesta sessão
- Cotações: expandir/ocultar em EUA/B3 Top 10/Commodities (`togCot()`)
- Indicadores: lazy load — cards abrem recolhidos, indicador real só carrega ao expandir (antes carregava todos ~16+ de uma vez)
- Badge "🧪 BACKTEST" nas análises de validação do modelo (vs. decisões reais)

## 7 análises registradas em analises.json (todas com backtest correto)
| ID | Ticker | Tipo | backtest | Observação |
|---|---|---|---|---|
| an_1782098774 | PETR4 | bidirecional | true | Teórica, construída do zero via OpLab |
| an_1782100906 | ROXO34 | retorno_controlado | true | Real do banco, vencimento original vigente |
| an_1782100907 | TSLA34 | retorno_controlado | true | Real do banco, reprojetada (vencimento original já passou) |
| an_1782123970 | ROXO34 | simples | true | Call nova, independente da posição ativa ROXOG105 |
| an_1782124389 | AXIA3 | bidirecional | true | Comparativo "contratar hoje" vs. posição ativa AXIA3(B) |
| an_1782124685 | VALE3 | bidirecional | true | Estudo/referência, possivelmente indisponível hoje |
| an_1782147275 | ROXO34 | premio | false | Venda de PUT real (ROXOS105), decisão real sendo avaliada |

## positions.json — campos por posição (6 ativas)
| ID | Ticker | exercicio | data_entrada (estimada) | Campos extras |
|---|---|---|---|---|
| pt | PETR4 | europeia | ~15/03/2026 | nenhum (objetivo: só recompra/rolagem, SEM meta) |
| vl | VALE3 | europeia | ~04/02/2026 | nenhum (objetivo: só recompra/rolagem, SEM meta) |
| rx | ROXO34 | **americana** | ~03/06/2026 | meta_pct: 2.25 |
| bb | BBAS3 | europeia | ~03/06/2026 | meta_pct: 2.25 |
| a3 | AXIA3(A) | europeia | ~16/05/2026 | alavancagem: 1.3, teto_retorno_pct: 4.0 |
| a3b | AXIA3(B) | europeia | ~08/06/2026 | alavancagem: 1.3, teto_retorno_pct: 4.0 |
Datas de entrada são ESTIMADAS por aproximação do usuário, não documento oficial — ajustar se ele achar nota de corretagem real.

## Backlog pendente — sem ação ainda, mas mapeado
1. **VIX/DXY**: % de variação diverge da fonte que o usuário acompanha externamente — investigado e CONCLUÍDO que é divergência normal entre fontes públicas (não é bug do app); sem ação.
2. **Estender `simples`/`premio` com `k_put` isolado** (sem `meta_pct`/`qtd_acoes`) — só a foto an_1782147275 tem o suporte completo hoje; outras fotos futuras de venda de PUT vão precisar dos mesmos campos (`premio`, `qtd_acoes`, `exercicio`) para mostrar o bloco fixo.
3. **Encerradas**: quando uma análise migra Ativa→Encerrada, o histórico/fan_chart completo deve continuar aparecendo lá (ainda não implementado — análises atuais ainda estão todas em `em_analise`).
4. **Crescimento de analises.json**: vigilância contínua, sem ação até crescer muito.
5. **Long-term, pausado sem ação**: tornar Cotações/Indicadores públicos; monetização de Encerradas; bot de futuros automatizado.

## Aprendizados-chave desta sessão (não repetir os mesmos erros)
- **Sempre confirmar em QUAL função/endpoint uma edição está, antes de assumir que está em todos os lugares esperados.** O bug da v10.11-13 (extensão de call simples faltando no `/montecarlo/condicional`) aconteceu porque uma contagem de ocorrências de variável (`grep -c`) foi mal interpretada como "está nos 2 lugares" quando só estava em 1.
- **`str_replace` pode apagar código adjacente por engano se o texto-alvo não for único o suficiente** — sempre incluir uma linha-âncora exclusiva (ex: nome de função vizinha) no `old_str`/`new_str`, e validar com `grep` que a função afetada ainda existe depois de cada edição.
- **Memória de longo prazo (`userMemories`) pode ficar defasada em poucas trocas de assunto dentro da mesma sessão longa** — sempre reconferir contra o GitHub real antes de agir, especialmente para SHAs e schemas.
- **PDFs de propostas reais do banco não devem ser "validados" ou recalculados com rigor financeiro extra** — isso foi tentado nesta sessão e o usuário rejeitou; os números do banco são premissa, não objeto de verificação.
- **Erros 400 retroativos**: ao tornar um campo obrigatório num endpoint, sempre auditar TODOS os registros existentes que usam aquele endpoint antes de considerar a mudança "pronta" — a foto an_1782147275 quebrou silenciosamente até o usuário testar.
