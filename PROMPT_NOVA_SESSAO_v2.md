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

## Métodos estatísticos / modelos de volatilidade — mapa completo do que já foi avaliado

### Em produção hoje (motor atual do Trader Desk)
- **Black-Scholes (BS)**: usado como referência/comparação pontual, não é o motor principal de probabilidade.
- **GARCH(1,1)**: motor PRINCIPAL de volatilidade em produção (`montecarlo_garch.py`). Calibrado com histórico de preço real (Yahoo/brapi), captura "clusters" de volatilidade (períodos calmos/turbulentos).
- **Monte Carlo (com GARCH)**: simula milhares de trajetórias diárias completas a partir da vol. GARCH, usado em TODOS os endpoints (`/montecarlo`, `/montecarlo/condicional`, `/montecarlo/posicao_ativa`, `/montecarlo/trajetorias`, `/montecarlo/barrier`). Para opções AMERICANAS ou estruturas com barreira (kdo/kuo), usa o caminho completo (max/min); para EUROPEIAS simples, usa só o preço final.
- **Vol. implícita extraída via Black-Scholes invertido**: quando o usuário cola um book real do OpLab, Claude já extrai a vol. implícita real por strike (via `brentq`/busca de raiz) para calibrar simulações teóricas — usado nas sessões de Fase A para montar estruturas do zero.

### Avaliados e FECHADOS (não vale a pena seguir, decisão do usuário)
- **MLE contínuo (scipy) vs. grid search para calibrar GARCH**: testado em 5 cenários sintéticos, diferença de 0.00pp em todos os casos. Não vale o esforço de implementar.
- **Jump-Diffusion (Merton)**: modela "saltos"/gaps no preço além da variação contínua normal. Calibrável só com histórico de preço (sem precisar de book de opções). Testado contra GARCH puro: diferença de -0.7pp a -6.8pp. Fica como estudo futuro, SEM prioridade atual — diferença pequena não justificou implementar.
- **Heston (volatilidade estocástica)**: precisa de book de opções reais para calibrar 2 parâmetros (xi, rho). Testado com parâmetros estimados: diferença de -2.3pp a -13.0pp vs. GARCH — faixa MUITO mais larga e instável (alta sensibilidade a parâmetro mal calibrado sem dado real). CONSIDERADO NÃO VIÁVEL sem fonte paga de book de opções.
- **SABR**: "primo" do Heston, mesma limitação (precisa de book de opções real para calibrar a superfície de vol.). Não exploraria nada que o Heston já não tivesse mostrado ser inviável sem dado pago — descartado pelo mesmo motivo.
- **Modelos de Lévy mais gerais (Variance Gamma, CGMY)**: generalizações do Jump-Diffusion com saltos mais ricos estatisticamente. Mesma família já testada (Merton); ganho marginal incerto, exigiria ainda mais dados históricos para calibrar bem. Não avaliado numericamente, descartado por inferência da família.
- **Machine Learning / redes neurais para previsão de preço**: categoria diferente (ajuste estatístico de padrão, não modelo de difusão com fundamento probabilístico). Avaliação qualitativa: evidência acadêmica de que ML supera de forma consistente um random walk + vol. estocástica é fraca para ações individuais de curto prazo. NÃO RECOMENDADO — mais hype do que ferramenta confiável neste contexto.

### ⭐ PRÓXIMO A EXPLORAR (usuário vai iniciar a próxima sessão por aqui)
- **Volatilidade realizada de alta frequência (intraday)**: em vez de usar só o preço de FECHAMENTO diário (como o GARCH atual faz), usar dados intraday (a cada minuto, ou pelo menos a cada hora) para calcular a volatilidade realizada de forma mais precisa e responsiva a eventos recentes do próprio dia. Esse é o ÚNICO método, dentre os avaliados, identificado como genuinamente diferente e potencialmente valioso — mas também depende de dado mais granular que o close diário gratuito que o Yahoo/brapi already fornecem hoje. Pontos a investigar na próxima sessão:
  1. Se existe fonte GRATUITA de dados intraday para ações brasileiras/BDRs com granularidade suficiente (Yahoo Finance tem endpoint intraday para alguns mercados, checar se cobre B3; brapi free provavelmente não tem)
  2. Se a fonte achada tem profundidade histórica suficiente para calibrar (não só o dia de hoje, mas uma janela de dias/semanas de dados intraday)
  3. Comparar a vol. realizada intraday contra a vol. GARCH atual em alguns ativos da watchlist, com metodologia parecida com os testes já feitos para Merton/Heston (rodar em paralelo, medir divergência em pontos percentuais)
  4. Decidir se a melhoria de precisão justifica a complexidade extra de implementação e o custo/limite de requisições da fonte de dados

### Fora de escopo / mencionado mas não avaliado tecnicamente
- **Mercados de previsão/apostas (estilo Polymarket) para criptoativos**: usuário mencionou que sites de apostas sobre preço futuro do Bitcoin poderiam compor um método adicional de probabilidade implícita do mercado (similar a usar vol. implícita de opções, mas via odds de apostas). Isso seria explorado num projeto separado de Bitcoin que o usuário está construindo, depois trazido/mesclado para o Trader Desk. NÃO avaliado tecnicamente ainda — fica registrado como ideia futura, fora do escopo desta sessão e do backlog imediato.

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

---

# Sessão 23/06/2026 — correções de bugs + expansão de Commodities + backlog novo

## SHAs no momento do fechamento desta sessão (23/06/2026)
- proxy.py: 3021bcc635a8e327eab30e464d2fafca91b6f91c
- templates/index.html: b8971eb8642c6aa8708da83901fa9e0e01c919eb
- static/app.js: 84ce049b389979f5719cf448bd648db394cf7960
- positions.json: 584d8f955de8 (não tocado nesta sessão)
- analises.json: 50884ff8214e (não tocado nesta sessão — divergência conhecida: PROMPT diz an_1782147275 backtest=false, mas o arquivo real tem backtest=true; usuário ainda não confirmou qual está certo)
- montecarlo_garch.py: 31bdb9470821 (não tocado nesta sessão)

## Tag de backup criada
`v10.16-pre-novas-features` → aponta para o commit 3ed923e05d47312456ad9e66a80e4dd2a56eed96
(estado do repo ANTES de qualquer mudança de código desta sessão — ponto de
restauração caso algo dê errado nas novas features futuras)

## Arquivos novos genéricos no repo (preparação para projeto de cripto)
- `METODOS_ESTATISTICOS.md`: mapa de avaliação de modelos de volatilidade,
  generalizado para qualquer ativo financeiro (não só ações B3). Contém
  ressalva explícita de que os descartes de Heston/SABR/Jump-Diffusion foram
  por FALTA DE DADO (book de opções, intraday) no contexto de ações B3 —
  não necessariamente válidos para cripto, onde Deribit/Binance oferecem
  esse dado de forma gratuita.
- `POSITIONS_GUIDE.md`: guia simplificado do schema de positions.json (não
  documenta todos os campos reais como data_entrada/meta_pct — ver o JSON
  real para o schema completo).
- Nota: `montecarlo_garch.py` (módulo extraído) NÃO é importado por
  `proxy.py` — proxy.py tem sua própria cópia inline de garch_11/vol_hist.
  O módulo extraído é só uma cópia paralela para reuso em outros projetos,
  não é dependência ativa do app em produção.

## Bugs corrigidos e deployados nesta sessão

### 1. Desalinhamento da linha de preço real (fan chart) em fins de semana/feriados
**Sintoma:** usuário notou que a linha verde de preço real em Em Análise e
Posições Ativas parecia "andar adiantado" do tempo real.

**Causa raiz confirmada com teste sintético isolado:** em
`/montecarlo/condicional` e `/montecarlo/posicao_ativa`, o slice de
`precos_reais` usava `dias_passados` (dias CORRIDOS, calculado como
`(hoje - data_foto).days`) para cortar o array `cl[]`, que só tem 1 ponto
por PREGÃO ÚTIL (sem fins de semana/feriados, vem do Yahoo). Toda vez que
o período cruzava um fim de semana, o slice pegava pontos demais.

**Correção:** trocado para `cl[idx_inicio:]` (todo o resto do histórico a
partir do índice da foto/entrada) — já que o Yahoo nunca retorna pregão
futuro, isso sempre dá exatamente os pregões reais decorridos, sem precisar
tratar feriados manualmente (mesma causa raiz, mesma correção resolve
ambos). Validado com teste sintético antes do deploy. Confirmado
visualmente pelo usuário após o deploy: "a curva se ajustou, ficou mais
precisa".

**Por que não existiria em cripto:** mercado 24/7, "dias corridos" e "dias
com preço" são a mesma coisa — não há a noção de "pregão útil" que causa
esse desalinhamento em ações B3.

### 2. ROXO34 — Vol. Simples demorava muito mais que as outras posições
**Sintoma:** usuário notou que o card de Monte Carlo da ROXO34 ficava
"em branco"/travado por muito mais tempo que PETR4/VALE3/BBAS3/AXIA3, que
abrem quase instantâneo.

**Causa raiz confirmada lendo o código:** ROXO34 usa uma função separada
(`MCR`) que fazia 2 chamadas de rede em SÉRIE antes de mostrar qualquer
resultado: primeiro `fetch('/indicators/ROXO34.SA')` para pegar o preço
atual, e só DEPOIS `fetch('/montecarlo')`. As outras posições usam `MC`/
`MCB`, que fazem apenas 1 chamada direta. Além disso, o timeout de MCR já
tinha sido aumentado para 40s (vs 25s das outras) — sinal de que alguém já
sabia da demora e só aumentou a paciência, sem resolver a causa.

**Por que o fetch prévio era redundante:** `/montecarlo` já busca o preço
via Yahoo internamente quando `price` não é enviado no payload (mesmo
comportamento que `MC` já usa para PETR4/VALE3/BBAS3, que nunca mandam
`price`).

**Correção:** removido o fetch prévio a `/indicators`; MCR agora chama
`/montecarlo` direto, sem esperar nada antes. Timeout reduzido de 40s para
25s. NÃO afeta as outras 2 chamadas a `/indicators/ROXO34.SA` que existem
no app.js (cotação simples e status ITM/OTM) — contextos diferentes, com
motivo próprio documentado no código ("Yahoo bloqueia chamada direta
nesses casos").

## Feature nova: Commodities expandidas
Adicionadas ao endpoint `/futures` (mesmo padrão `yquote()` já usado para
WTI/Ouro/Prata/Cobre da v10.16), selecionadas por CRITÉRIO DE IMPACTO
DIRETO NOS PAPÉIS DA CARTEIRA (não liquidez genérica — usuário foi
explícito sobre isso):
- **Minério de Ferro** (`TIO=F`, contrato TSI 62% Fe CFR China): driver
  principal de VALE3. Atenção: é contrato de swap, liquidez/disponibilidade
  no Yahoo menos estável que os contratos CME tradicionais abaixo — pode
  vir `None` ocasionalmente, `yquote()` já trata isso com segurança.
- **Brent** (`BZ=F`): benchmark internacional distinto do WTI, também
  influencia a precificação da Petrobras (PETR4).
- **Gás Natural** (`NG=F`): contexto energético geral, sem ligação direta
  a uma posição específica (usuário pediu mesmo assim, "só para ter uma
  noção").
- **Gasolina foi EXPLICITAMENTE REJEITADA pelo usuário** — não adicionar
  de volta sem ele pedir.

AXIA3 é a antiga Eletrobras (energia elétrica, hidro em maioria) — não tem
driver de commodity Yahoo direto e confiável (PLD/CCEE não é cotado lá).
Não foi adicionado nada para ela.

## ⚠️ Pendência importante levantada pelo usuário — "Marcar como Ativa" não migra dados
Usuário identificou (e código confirma) que o botão "Marcar como Ativa" em
Em Análise hoje só troca o campo `status` dentro do MESMO registro em
`analises.json` (`PUT /analises/<id>/status`). NÃO cria nada em
`positions.json`, NÃO reseta a data/preço de entrada. Resultado: mesmo
"ativada", a análise continuaria sendo lida com a `data_foto` original, e
a linha verde do fan chart NÃO reseta como deveria.

**Especificação confirmada pelo usuário para a implementação futura:**
1. Migração é COMPLETA: o registro é REMOVIDO de `analises.json` e um
   registro NOVO é criado em `positions.json` — não fica duplicado nos
   dois lugares.
2. O preço de entrada da nova posição ativa é o PREÇO REAL DO DIA DA
   MIGRAÇÃO (capturado via Yahoo nesse momento), NÃO o `preco_foto`
   antigo que já estava na análise — é um novo "dia zero" genuíno.
3. Precisa mapear os campos de `analises.json` (tipo_estrutura, kdo/kuo,
   k_call/k_put, alavancagem, teto_retorno_pct, ganho_prefixado_pct, etc.)
   para o schema de `positions.json` (tipo_posicao simples/barreira) —
   ainda não especificado em detalhe, fica para quando for implementar.
4. "Encerrar sem executar" já funciona corretamente como está (não precisa
   de migração, é só uma foto histórica de "olhei e não fechei negócio").

**Prioridade:** usuário pediu explicitamente para deixar este item por
ÚLTIMO no backlog desta fase — é o item mais complexo e ele quer estudar
os outros temas primeiro. Hoje ele tem 7 análises todas em `em_analise`
(todas backtest), vai carregar uma amostra real maior antes de pensar em
ativar qualquer uma de verdade.

## Backlog novo desta sessão (ordem não é prioridade — usuário define a cada sessão)

1. **Fundos Imobiliários (FIIs):** pesquisar fontes gratuitas de dados,
   criar critério de avaliação (segurança + preço atrativo) parecido com o
   já usado para estruturadas, aplicado ao universo líquido de FIIs.
   Ainda não iniciado.

2. **Nova aba em Cotações — mercado Europeu e Asiático:** só futuros +
   índices (sem detalhe de ações individuais). Mercado americano já está
   coberto (US quotes/futures existentes); o foco da expansão é
   especificamente Europa + Ásia.

3. **PRIO3 nos Indicadores:** usuário vai pedir formalmente em sessão
   futura — ação de petróleo (PetroRio), ligada à mesma lógica de
   exposição a WTI/Brent.

4. **Watchlist de Semicondutores + "Magnificent 7" + métrica de
   concentração no S&P 500/Nasdaq-100:** usuário está preocupado com risco
   de bolha de IA — dados de mercado confirmam concentração recorde
   (top 10 empresas = ~36% do S&P 500 em 2026, vs 23% em 2000; Magnificent
   7 = ~33,8% do índice; Nasdaq-100 top 5 = ~55,4%). Lista proposta e
   CONFIRMADA pelo usuário como ponto de partida:
   - Núcleo semicondutores: NVDA, AMD, AVGO, TSM, ASML, INTC, MU, QCOM
   - Núcleo Magnificent 7: MSFT, AAPL, GOOGL/GOOG, AMZN, META, TSLA (+NVDA
     do grupo de cima)
   - Métrica de concentração: peso agregado desses nomes vs. SPY/S&P 500
     total — fonte de dado ainda não definida (StockAnalysis/State Street
     publicam holdings do SPY diariamente, mas não é um "preço" simples de
     puxar via Yahoo como as commodities; precisa de investigação técnica
     própria antes de implementar).
   Ainda não iniciado — só lista e conceito confirmados.

5. **ETFs:** estudo futuro, mencionado como naturalmente ligado ao item 4
   (ETFs temáticos de semicondutores/IA, ex. SOXX, agrupam exatamente esses
   nomes). Backlog de longo prazo, sem ação ainda.

6. **Renda fixa:** registrar a ideia no backlog, sem ação por enquanto
   (usuário confirmou explicitamente "só registrar, sem ação agora").

## Aprendizados desta sessão (não repetir)
- Sempre re-baixar o arquivo do GitHub (`raw.githubusercontent.com`) antes
  de editar quando há qualquer chance de ter mudado desde a última leitura
  na mesma sessão — feito antes de cada edição desta sessão, evitou
  trabalhar em cima de versão desatualizada.
- Ao investigar uma demora/bug de performance, ler o código real (não
  assumir) — o caso da ROXO34 parecia "só lentidão de rede" mas a causa
  raiz era arquitetural (chamada redundante em série), só visível lendo o
  fluxo completo de chamadas no app.js.
- Antes de marcar um item como "resolvido" em UI, verificar se outras
  ocorrências do mesmo padrão (ex: outras chamadas a `/indicators/
  ROXO34.SA`) são o MESMO bug ou contextos legítimos e separados — neste
  caso eram separados, com motivo próprio documentado no código.

---

# Continuação sessão 23/06/2026 (parte 2) — correções de Commodities, PRIO3, e nova feature conceitual "Análise de Papel"

## SHAs no momento deste registro
- proxy.py: 3c7f69ff3c442a463293fd5ea59cf9d7da9ff872
- static/app.js: 619d36a5523f572c4c33f23a18727b3a9ac7e281
- templates/index.html: b8971eb8642c6aa8708da83901fa9e0e01c919eb (não tocado nesta parte)

## Correções adicionais em Commodities (após a expansão inicial desta sessão)
1. **Moeda corrigida:** as 7 commodities (WTI, Brent, Gás Natural, Ouro,
   Prata, Cobre, Minério de Ferro) são cotadas em USD no Yahoo, mas a
   função `afChg()` usava `fR()` (prefixo R$) — exibia ex. "R$ 73,88"
   quando o valor real era US$ 73,88, SEM nenhuma conversão de câmbio
   (apenas rótulo errado). Corrigido para usar `fU()` (US$, já existia e
   era usado para Bitcoin), trocando o parâmetro `tp` de `'r'` para `'u'`
   nas 7 chamadas.
2. **Sanity check no Minério de Ferro:** usuário reportou variação de
   ~60% em 1 dia, impossível para essa commodity. Causa provável:
   `TIO=F` é contrato de baixa liquidez (swap TSI 62% Fe CFR China),
   sujeito a rollover de vencimento que pode fazer `prev` vir de um
   contrato diferente. Implementado: se `|variação%| > 15`, o preço é
   exibido normalmente mas a variação fica oculta (mantém "—") em vez de
   mostrar um número implausível. Threshold de 15% confirmado pelo
   usuário.

**Lição de processo desta correção:** `raw.githubusercontent.com` ficou
desatualizado por alguns minutos após o commit (CDN/cache), apesar do SHA
via API Contents já estar correto. A verificação pós-deploy deve SEMPRE
usar a API Contents (decodificando base64) como fonte de verdade, nunca
confiar isoladamente em `raw.githubusercontent.com` para validação
imediata pós-commit — exatamente como já estava documentado, mas vale
reforçar pois aconteceu na prática nesta sessão.

## PRIO3 adicionada à aba de Indicadores
Adicionada ao segmento "🛢️ Petróleo & Gás" da `WATCHLIST` (app.js), junto
da PETR4. Fundamentais reais coletados do Fundamentus em 13/05/2026 (9
dias antes da `FUND_DATA_REF` global de 22/05/2026 — diferença pequena,
mantida sem ajustar a referência global por causa de 1 ativo só):
P/L 22.05, P/VP 2.14, LPA 2.97, VPA 30.52, DY 0%, ROE 9.7%.

**Descoberta importante de arquitetura:** adicionar um novo ativo à
watchlist de Indicadores exige tocar em 3 lugares (não documentado antes
com essa clareza):
1. `WATCHLIST` em `app.js` (frontend, define quais ativos aparecem)
2. `FUND_OVERRIDE` em `proxy.py` (backend, fundamentais hardcoded:
   pvp/dy/lpa/vpa/roe/pl)
3. `SETOR_MAP` em `proxy.py` (backend, médias do setor para comparação:
   nome/pl_medio/pvp_medio/roe_min)

Existem TAMBÉM `SETORES` e `FUND` (linhas ~171-185 de proxy.py) — esses
dois são dicionários DIFERENTES, menores, que servem só para as 5
Posições Ativas reais (PETR4/VALE3/BBAS3/AXIA3/ROXO34), não para o
universo completo de 16+ ativos da watchlist de Indicadores. Não confundir
os dois pares de dicionários ao adicionar/editar fundamentais no futuro.

## ⭐ Nova feature conceitual — "Análise de Papel" (aba nova, separada)

Usuário trouxe um conceito novo, ainda não implementado, que precisa de
uma aba própria distinta de "Em Análise" (que é exclusiva para estruturas
de opções — call vendida, bidirecional, etc.).

**O problema que motiva a feature:** hoje só existe fan chart (linha
verde de preço real + cone Monte Carlo) quando existe uma ESTRUTURA DE
OPÇÃO registrada (Em Análise ou Posições Ativas). Mas o usuário às vezes
quer simplesmente avaliar se vale comprar uma AÇÃO PURA (sem opção
nenhuma envolvida) — não existe hoje um jeito de tirar uma "foto" só do
papel para acompanhar evolução de preço com banda de probabilidade.

**Especificação dada pelo usuário:**
1. Nova aba separada, nome de trabalho "Análise de Papel" (distinta de
   "Em Análise", que continua exclusiva para estruturas de opções).
2. Ao criar uma análise de papel, em vez de 1 fan chart com prazo
   variável (como hoje), o sistema tira **3 fotos simultâneas, com
   horizontes FIXOS: 21, 60 e 90 dias**.
3. **Motivo explícito da escolha de 3 prazos curtos, não 1 prazo longo:**
   o cone de incerteza do GBM cresce com a raiz do tempo — em horizontes
   muito longos a banda fica tão larga que perde valor preditivo ("fica
   igual jogar moeda"). Limitar a 21/60/90 dias mantém o cone útil/estreito
   o suficiente para servir de sinal real.
4. **Uso pretendido como sinal de entrada:** se o preço real, dentro
   desses prazos curtos, estiver "na vermelha"/abaixo da projeção, isso é
   um sinal de possível bom ponto de compra do papel (montagem de
   carteira simples, sem opção envolvida) — não é uma estrutura para
   gerar prêmio, é puramente para timing de entrada na ação.
5. Cada uma das 3 fotos (21d/60d/90d) teria sua própria linha verde +
   cone, igual ao padrão já usado em Em Análise/Posições Ativas, só que
   com prazo fixo em vez de variável.

**O que NÃO foi especificado ainda (decidir antes de implementar):**
- Schema de dados exato (provavelmente um novo arquivo JSON ou nova
  estrutura dentro de um arquivo existente — analogia a `analises.json`,
  mas para papel puro, sem campos de estrutura de opção como kdo/kuo/
  k_call/premio).
- Se as 3 fotos (21/60/90d) ficam como 3 registros separados ou 1
  registro com 3 sub-resultados.
- Layout exato da UI: como mostrar 3 fan charts ao mesmo tempo de forma
  legível (provavelmente lado a lado ou em abas internas).
- Se existe transição "Análise de Papel" → "Ativa" (ex: usuário decide
  comprar o papel após ver o sinal) — análogo à migração Em Análise →
  Ativa que já está especificada e pendente (item de maior prioridade,
  ainda por último no backlog atual).
- Endpoint backend novo provavelmente necessário (reaproveitando
  `simular_fan_chart`/GARCH já existentes, só mudando os parâmetros de
  entrada — não deve precisar de lógica estatística nova, só uma nova
  forma de orquestrar prazos fixos).

**Prioridade:** registrado para estudo futuro, SEM ação ainda. Usuário
ainda está testando as entregas desta sessão (Commodities, PRIO3) antes de
seguir para o próximo item do backlog. Não é o próximo item garantido —
fica junto dos demais itens do backlog para priorização em sessão futura.

## Lembrete de processo confirmado pelo usuário nesta sessão
Usuário pediu explicitamente para SEMPRE ser avisado quando uma entrega
estiver pronta para teste — não assumir que ele vai notar sozinho que
algo foi deployado. Reforçar esse aviso explícito ao final de cada
entrega de código daqui em diante.

---

# Continuação sessão 23/06/2026 (parte 3) — correção sistêmica de yquote, grupo Semicondutores, métrica de concentração

## SHAs no momento deste registro
- proxy.py: 7a44a373d21c9a5e5a0c9e32faab5dd007cec0c6
- static/app.js: e288c5f406cbeecc088f39ef95732d125369641d
- templates/index.html: b4f683ff165201833ffe06a30d324e5108c4ddd4

## Correção: variação implausível em TODAS as commodities (causa sistêmica)
Usuário relatou que variações pareciam excessivas em todas as commodities,
não só na Prata isolada. Investigação:
- Movimento real do dia (FXStreet, 23/06): Prata caiu -4,47% (US$ 65,09 →
  US$ 62,18) — bem menor que o ~-11% visto no app.
- Causa raiz: `yquote()` usava `meta.chartPreviousClose` (campo calculado
  pelo próprio Yahoo) como referência de "ontem". Esse campo pode ficar
  desatualizado para futuros com horário de pregão ESTENDIDO (CME/COMEX/
  NYMEX) — diferente do horário fechado da B3/NYSE. Afeta TODAS as
  commodities + outros consumidores de `yquote()` (DJI, ES=F, NQ=F, VIX,
  IBOV, USD/BRL).
- Correção: `yquote()` agora usa `cl[-2]` (penúltimo fechamento da própria
  série histórica diária, mesma série já usada para `cl[-1]`/price e para
  `vol_hist`/GARCH) como fonte PRIMÁRIA. `chartPreviousClose` fica só como
  fallback quando o histórico não tem pontos suficientes.
- **Decisão deliberada**: NÃO foi usada nenhuma heurística de "escolher o
  valor mais próximo do preço atual" entre os dois candidatos — isso
  mascararia movimentos REAIS de mercado (como a queda real de -4,47% da
  prata), não só os artificiais. A correção troca a FONTE do dado, não
  filtra o resultado por plausibilidade.
- **Limitação assumida**: não foi possível validar empiricamente contra a
  API real do Yahoo (sandbox sem acesso de rede a `query1.finance.yahoo.com`)
  — a correção é baseada em raciocínio sobre a causa mais provável, não em
  teste direto. Usuário confirmou visualmente que "ficou bom" após o
  deploy.

## Feature nova: grupo "Semicondutores" em Cotações
Descoberta importante: a infraestrutura para "EUA por Segmento" (botões
expansíveis tipo "7 Magníficas", "Nasdaq Top 15", etc.) JÁ EXISTIA
completa (`USSEG` em app.js + `loadSeg()` + endpoint `/us/quotes`) —
adicionar um grupo novo foi só adicionar a entrada no dicionário + a
seção HTML correspondente, sem precisar de lógica nova.

Lista confirmada pelo usuário: `semi: ['NVDA','AMD','AVGO','TSM','ASML',
'INTC','MU','QCOM']`. Adicionado `'TSM':'NYSE'` ao `_US_EXCHANGE` (TSM é
NYSE, não NASDAQ — sem isso o fallback do TradingView erraria a bolsa).
ASML e MU já ficam corretos no fallback padrão NASDAQ.

## Feature nova: métrica de concentração no S&P 500 (`/us/concentracao`)
Calcula o peso agregado de um grupo (`semi` ou `m7`) sobre o market cap
TOTAL do S&P 500 — sinal de risco de concentração/bolha de IA que o
usuário queria acompanhar.

**Decisões de arquitetura tomadas nesta sessão:**
1. Calcular nós mesmos (market cap individual via Yahoo ÷ total do
   índice), não fazer scraping de página de terceiro (mais fragante a
   mudança de layout).
2. Market cap individual vem de `v7/finance/quote?symbols=...` — endpoint
   DIFERENTE do `v8/finance/chart` já usado em `yquote()`; só o v7 retorna
   o campo `marketCap`. Suporta múltiplos tickers numa só chamada.
3. `SP500_TOTAL_MARKETCAP_USD` é hardcoded com data de referência
   explícita (`SP500_TOTAL_MARKETCAP_REF`), mesmo padrão do
   `FUND_DATA_REF` — mas com uma ressalva importante: esse número muda
   TODO DIA (diferente de P/L/ROE que mudam por trimestre), então é
   tratado como aproximação para ORDEM DE GRANDEZA, não precisão em tempo
   real. A resposta da API inclui um campo `aviso` explícito sobre isso.
   Usuário confirmou estar OK com essa limitação antes de implementar.
4. **Nasdaq-100 NÃO foi implementado** — pesquisa não encontrou um número
   confiável e específico do market cap TOTAL do índice (só do "Nasdaq
   exchange" inteiro, que é uma coisa MAIOR e DIFERENTE — confundir os
   dois seria erro de precisão real). Mesmo o Slickcharts teve divergência
   de >US$1tri entre páginas do mesmo site (US$38,59T vs US$39,69T,
   provavelmente datas de captura diferentes). Fica como pendência —
   antes de implementar Nasdaq-100, pesquisar mais ou aceitar uma fonte
   específica com ressalva clara.
5. Valor de referência atual: `SP500_TOTAL_MARKETCAP_USD = 68.06e12` (ref.
   23/06/2026, fonte Slickcharts).

**UI**: card de resumo acima da tabela, nos grupos `semi` e `m7` apenas
(Nasdaq/S&P/Dow Jones não mostram essa métrica, só os dois grupos
relevantes ao tema de concentração de IA).

## Lição de processo desta sessão — usar ask_user_input_v0 sempre que a pergunta exigir decisão
Usuário pediu explicitamente: quando uma pergunta no meio do texto exigir
uma decisão real (não só contexto), usar a ferramenta de perguntas com
botões em vez de deixar a pergunta solta em prosa — fica mais claro
visualmente que aquilo precisa de resposta, especialmente para alguém
testando/distraído voltando à conversa depois de um tempo.

## Estado do backlog ao final desta sessão (23/06/2026)
**Concluído hoje:**
- ✅ Desalinhamento fim de semana/feriado na linha de preço real
- ✅ ROXO34 (lentidão do Vol. Simples)
- ✅ Commodities expandidas (Minério de Ferro, Brent, Gás Natural)
- ✅ Moeda das Commodities (US$ em vez de R$)
- ✅ Sanity check no Minério de Ferro (variação >15% oculta)
- ✅ Correção sistêmica de `yquote()` (todas as commodities + DJI/ES/NQ/
  VIX/IBOV/USD-BRL)
- ✅ PRIO3 nos Indicadores (fundamentais reais do Fundamentus)
- ✅ Grupo Semicondutores em Cotações
- ✅ Métrica de concentração S&P 500 (semi/m7)

**Backlog pendente, por ordem de simplicidade (definida pelo usuário):**
1. Nasdaq-100 na métrica de concentração (precisa de fonte confiável de
   market cap total do índice)
2. Cotações Europa/Ásia (futuros + índices, sem ações individuais)
3. FIIs (pesquisa de fontes gratuitas + critério de avaliação)
4. "Análise de Papel" (feature conceitual nova — 3 fotos fixas 21/60/90d
   para ações puras, sinal de entrada, aba separada de "Em Análise")
5. ETFs (estudo futuro)
6. Renda fixa (backlog de longo prazo, sem ação)
7. **Migração Em Análise → Ativa** — especificada em detalhe em sessão
   anterior, usuário confirmou que fica POR ÚLTIMO deliberadamente

---

# Continuação sessão 23/06/2026 (parte 3) — Grupos de concentração EUA + correção crítica do endpoint /us/concentracao

## SHAs no momento deste registro
- proxy.py: e0367b2d5cb6648b717ae5d4c8a1f52aff5bf47d
- static/app.js: 8ab1da65aeb3166973857a56d0896854be1cf9b3
- templates/index.html: a44ea0308e1f25c0717e1962b1d1ccbd8fbbc9d7

## Feature: 4 grupos de concentração EUA (item 2 do backlog, concluído)
Adicionados à seção "EUA por Segmento" das Cotações, todos com a mesma
métrica de peso vs. S&P 500:
- **Semicondutores**: NVDA, AMD, AVGO, TSM, ASML, INTC, MU, QCOM
- **7 Magníficas** (m7, já existia): AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA
- **Software**: ORCL, PANW, PLTR, CRWD, ADBE (baseado em holdings reais
  do ETF IGV — iShares Expanded Tech-Software Sector)
- **Energia IA** (infraestrutura/data centers, NÃO petróleo/gás
  tradicional): CEG, VST, TLN, D, OKLO — utilities/nuclear com contratos
  de energia para data centers de AWS/Meta/Microsoft/Google

`_US_EXCHANGE` atualizado com os tickers NYSE que não seguiam o fallback
padrão NASDAQ: TSM, PLTR, VST, D, OKLO.

`SP500_TOTAL_MARKETCAP_USD = 68.06e12` (ref. 23/06/2026, fonte
Slickcharts) — hardcoded com data de referência explícita, mesmo padrão
do `FUND_DATA_REF`, porque esse número muda diariamente (decisão
confirmada pelo usuário após discussão sobre trade-off de precisão).
Nasdaq-100 NÃO foi incluído como denominador alternativo — fontes
encontradas (Slickcharts) divergiam em mais de US$ 1 trilhão entre duas
páginas do mesmo site, sem confiança suficiente para hardcodar. Fica
pendente para pesquisa futura se o usuário quiser essa métrica também.

## Bug crítico corrigido — /us/concentracao usava endpoint errado do Yahoo
Historico do bug (2 correcoes até resolver de verdade):

1a tentativa (insuficiente): usuario reportou erro so no grupo m7. Causa
suposta: intermitencia do Yahoo. Correcao aplicada: retry de 2 tentativas
no endpoint v7/finance/quote. NAO resolveu a causa raiz.

2a situacao: usuario reportou que TODOS os 4 grupos (semi, m7, software,
energia_ia) passaram a falhar com "Não foi possível calcular".

**Causa raiz REAL identificada:** a implementacao original usava
v7/finance/quote (busca em lote, multiplos simbolos numa unica chamada)
-- esse e um endpoint NAO-OFICIAL do Yahoo, sem documentacao, e com
historico publico de instabilidade/bloqueio (confirmado via busca:
desenvolvedores relatam quebras frequentes nesse endpoint especificamente,
diferente do v8/finance/chart, que e estavel ha anos apesar de tambem nao
ser oficialmente documentado).

**Correcao definitiva:** trocado para v8/finance/chart (uma chamada por
ticker, nao em lote) -- mesmo endpoint que yquote() ja usa com sucesso
comprovado durante TODA a sessao para commodities/indices. O campo
meta.marketCap esta disponivel nesse endpoint tambem; nunca havia
necessidade real de usar o v7.

**Licao de processo para nao repetir:** ao montar uma chamada nova a uma
API externa, preferir reaproveitar um endpoint que ja esta provadamente
funcionando no projeto (yquote()/v8/finance/chart, usado dezenas de vezes
nesta sessao) em vez de introduzir um endpoint novo e nao testado
(v7/finance/quote), mesmo que pareca mais conveniente (1 chamada batch vs
N chamadas individuais). A conveniencia de uma chamada em lote nao
compensou o risco de usar um endpoint nao comprovado.

**Risco residual conhecido, nao resolvido:** Claude nao tem acesso de rede
direto a API do Yahoo neste ambiente (bash_tool e web_fetch bloqueiam o
dominio) -- nenhuma das correcoes desta sessao envolvendo comportamento
da API do Yahoo pode ser validada empiricamente antes do deploy. Todas as
correcoes foram baseadas em busca de documentacao/relatos publicos +
raciocinio sobre o codigo, nao em teste direto. Se o usuario reportar
falha recorrente em qualquer endpoint que dependa do Yahoo, considerar
essa limitacao ao diagnosticar.

## Item de acompanhamento periodico novo -- Fusao Dominion/NextEra
Usuario pediu para isso ser registrado como item a cobrar de tempos em
tempos (mesmo padrao do aviso de 90 dias do FUND_DATA_REF): Dominion
Energy (D, parte do grupo Energia IA) esta em processo de fusao anunciada
com a NextEra Energy (negocio all-stock, criando a maior utility regulada
do mundo, fechamento previsto em 12-18 meses a partir de ~maio/2026 quando
anunciado). Se a fusao se concretizar, o ticker "D" pode deixar de existir
ou ser convertido -- isso vai exigir atualizar o grupo energia_ia em
USSEG (app.js) e tickers_map (proxy.py), removendo "D" e possivelmente
adicionando "NEE" no lugar. Quando o usuario mencionar essa fusao ou
perguntar sobre o status dela em sessao futura, verificar via web search
se ja fechou antes de responder.

## Lembrete de processo reforcado nesta sessao
Usuario pediu explicitamente que toda pergunta que exige uma decisao dele
(nao uma reflexao propria do Claude) deve usar a ferramenta de pergunta
com botoes (ask_user_input_v0), nunca so texto solto na resposta -- ele
pode estar distraido/ler rapido e perguntas em texto corrido se perdem.
Isso reforca e formaliza o padrao que ja vinha sendo seguido informalmente
ao longo da sessao.

---

# Continuação sessão 23/06/2026 (parte 4) — Fechamento da feature de concentração EUA

## SHAs no momento deste registro
- proxy.py: f5d5d88fe4b5ce6e8b5795e4772783c17ee6a185
- static/app.js: c11c1af186815952b2144b2f1305a1819758f186
- templates/index.html: 13e3d6fce8b14505f795cd6468ede5fcdf64c4c9

## Item 2 do backlog (Watchlist Semicondutores/m7 + concentração) — FECHADO E VALIDADO

Histórico completo de correções até funcionar (8 iterações no total, todas
documentadas nas partes 2-3 anteriores deste arquivo):
1. Endpoint usava v7/finance/quote em lote → trocado para v8/finance/chart
2. v8/chart não tinha marketCap confiável → tentativa de paralelização
3. Faltavam parâmetros de query → adicionados (sem efeito real)
4. Paralelização via ThreadPoolExecutor (correta, mas não era a causa raiz)
5. v7 individual por ticker (ainda sem marketCap em produção)
6. Tentativa de calcular via price × sharesOutstanding (também ausente)
7. **Scraping de 8marketcap.com/companies/ como fallback final — isso
   resolveu para a maioria dos tickers**
8. Exposição de tickers_sem_dado/aviso na resposta (para nunca mostrar
   número incompleto sem avisar) + correção GOOGL→GOOG (Alphabet só
   listada como classe C nesse site)

**Causa raiz definitiva confirmada pelo usuário com testes reais**: o
Yahoo (v7 e v8) não retorna NENHUM campo de valuation (marketCap nem
sharesOutstanding) no ambiente de produção (Render), de forma consistente
-- mesmo com preço/histórico funcionando normalmente em todo o resto do
app. Causa exata desconhecida (possível throttling/filtro específico do
Yahoo para esses campos nesse IP), mas o padrão é claro e replicável.

**Resultado final validado pelo usuário (23/06/2026, mercado em queda no
dia):**
- Semicondutores: ~18% do S&P 500 — usuário considerou plausível
- 7 Magníficas: ~31,8% do S&P 500 (todos os 7 tickers, incluindo GOOGL
  via fallback GOOG) — bate com a faixa real confirmada via busca (33-35%
  em maio/início de junho/2026); diferença pequena para baixo é coerente
  com mercado em queda no dia da consulta
- Software: funciona para ORCL/PANW/PLTR (3 de 5) — ADBE (posição 313 no
  ranking) e CRWD (posição 119) estão fora do top 100 que a função busca
  (só primeira página, sem paginação)
- Energia IA: REMOVIDO permanentemente (CEG/VST/TLN/D/OKLO são utilities
  pequenas, sem dado em nenhuma fonte tentada)

## Decisão sobre ADBE/CRWD faltando em Software
Usuário decidiu NÃO implementar paginação para cobrir esses 2 tickers
agora -- consideração explícita: "não dá nem 2%, não é isso que vai ser
indicador de bolha". Decisão consciente de custo/benefício, não uma
limitação técnica não resolvida.

**Condicional para revisitar**: usuário quer primeiro investigar a lista
completa de holdings do ETF de software que ele mencionou (citado como
"usado para comparar com Bitcoin" -- possivelmente um ETF tipo IGV
iShares Expanded Tech-Software, ou outro popular nesse nicho, ainda não
identificado com certeza). Se essa lista for extensa e revelar que há
muito mais nomes relevantes fora do ranking atual de 5 tickers do grupo
`software`, ele quer reavaliar nessa ocasião -- não antes.

## Pendência de pesquisa para próxima sessão (sem ação ainda)
Identificar e estudar o ETF de software mencionado pelo usuário como
"usado para comparar com Bitcoin" em discussões de mercado. Pode revelar
uma lista de holdings mais ampla/diferente da atual (ORCL/PANW/PLTR/CRWD/
ADBE) que valeria incorporar ao grupo `software`, dependendo do que for
encontrado. Usuário não deu o nome exato do ETF -- precisa de pesquisa
para identificá-lo (candidatos prováveis: IGV, ou algo do universo
"AI/cloud/SaaS" popularmente comparado a Bitcoin em conteúdo de mercado).

## Lição de processo importante desta sessão (correções do mesmo bug)
Esta foi a sequência de correção mais longa da sessão (8 iterações para
um único bug). Padrão a reconhecer mais rápido em sessões futuras: quando
uma fonte de dado externa (aqui, campos de valuation do Yahoo) falha de
forma CONSISTENTE e IDÊNTICA através de múltiplas variações de
implementação (endpoint diferente, parâmetros diferentes, campo
calculado em vez de direto), é sinal de limitação real da fonte nesse
ambiente -- não vale continuar variando a MESMA fonte indefinidamente.
O sinal para trocar de fonte (scraping de terceiro, nesse caso) deveria
ter vindo mais cedo, não somente após confirmação explícita do usuário em
3 testes seguidos com o mesmo padrão de erro.

Também vale notar: alternativas como APIs pagas (Financial Modeling Prep,
EOD Historical Data) e exchanges de cripto/RWA (Binance/Hyperliquid para
ações tokenizadas) foram avaliadas e descartadas com justificativa clara
-- RWA tokenizado tem market cap muitas ordens de grandeza menor que o
real (ex: Nvidia tokenizada ~US$42M contra ~US$5T real), não serve para
essa métrica especificamente. Documentado para não reconsiderar essa
opção no futuro sem motivo novo.

---

# Resumo consolidado — sessão 23/06/2026 (estado final, validado pelo usuário)

## SHAs finais
- proxy.py: 3119679099b3ead49775b1ed5c92fcfc4c84f64a
- static/app.js: cc11954ad2b8e6165093feeede81a14a3980e8bf
- templates/index.html: 13e3d6fce8b14505f795cd6468ede5fcdf64c4c9

## Nova regra de processo (válida a partir desta sessão)
Atualizar este arquivo ao final de cada item de backlog CONCLUÍDO e
VALIDADO pelo usuário -- não a cada tentativa/iteração intermediária de
um bug, nem automaticamente a cada commit. Evita reconstituir estado lendo
vários arquivos em sessões futuras, economiza tokens. Usuário quer
replicar esse padrão em outros projetos também.

## Itens concluídos e validados nesta sessão

**1. Bug do fan chart (linha de preço real) desalinhado em fins de
semana/feriados** -- corrigido em /montecarlo/condicional e
/montecarlo/posicao_ativa (slice usava dias corridos para cortar array de
pregões úteis). Confirmado visualmente pelo usuário.

**2. ROXO34 -- Vol. Simples lenta** -- causa real era uma chamada
redundante a /indicators antes de /montecarlo (2 chamadas em série em vez
de 1). Removida. Confirmado.

**3. PRIO3 adicionada aos Indicadores** -- segmento Petróleo & Gás,
fundamentais reais do Fundamentus (ref. 13/05/2026).

**4. Commodities expandidas e corrigidas**:
- Minério de Ferro (TIO=F), Brent (BZ=F), Gás Natural (NG=F) adicionados
- Moeda corrigida: todas as 7 commodities agora mostram US$ (estavam
  rotuladas como R$ por engano -- valor sempre esteve certo, só o rótulo)
- Sanity check no Minério de Ferro: variação >15% em módulo oculta o %
  (contrato de baixa liquidez, sujeito a dado de rollover inconsistente)
- yquote() corrigido: usa cl[-2] (penúltimo fechamento da série real) em
  vez de chartPreviousClose (campo do Yahoo que ficava desatualizado para
  futuros com horário estendido) -- variações absurdas em TODAS as
  commodities (ex: -11% relatado quando o real era -4,5%) resolvidas.

**5. Grupos de concentração no S&P 500 (Cotações → EUA por Segmento)**:
- Semicondutores (NVDA/AMD/AVGO/TSM/ASML/INTC/MU/QCOM): ~18% do S&P 500,
  validado pelo usuário como plausível.
- 7 Magníficas (AAPL/MSFT/NVDA/AMZN/GOOGL/META/TSLA): ~31,8% do S&P 500
  (após corrigir GOOGL→GOOG, que faltava por diferença de classe de ação
  no 8marketcap), validado contra fontes externas (faixa real 33-35% em
  maio-início de junho/2026; diferença pequena coerente com queda do dia).
- Software: expandido para o top 10 real do IGV (PANW/PLTR/MSFT/ORCL/
  CRWD/CRM/APP/CDNS/NOW/FTNT, 60,84% do ETF) + extrapolação opcional do
  setor completo (115 holdings) via regra de 3 (só calcula se ≥70% dos
  10 tickers tiverem dado, evitando número distorcido). PENDENTE DE TESTE
  FINAL pelo usuário (paginação no 8marketcap acabou de subir).
- Energia IA (CEG/VST/TLN/D/OKLO): implementada e depois REMOVIDA --
  usuário decidiu não valer o esforço (empresas pequenas, <2% de impacto,
  sem dado disponível em nenhuma fonte tentada).

**Causa raiz definitiva do bug de concentração (8 correções até
resolver)**: Yahoo (v7 e v8) não retorna nenhum campo de valuation
(marketCap nem sharesOutstanding) no ambiente de produção (Render), de
forma consistente. Resolvido com scraping de 8marketcap.com/companies/
como fallback (com paginação e cache compartilhado para não multiplicar
requisições). Ver código para detalhes técnicos completos (comentários
inline em proxy.py documentam cada correção numerada).

## Backlog restante, por ordem de simplicidade (usuário define prioridade a cada sessão)

9. **Cotações Europa/Ásia** -- nova seção com futuros + índices apenas
   (sem ações individuais). Mercado americano já está coberto. PRÓXIMO
   ITEM A FAZER (usuário confirmou em 23/06/2026).
10. **FIIs** -- pesquisar fontes gratuitas de dados, criar critério de
    avaliação (segurança + preço atrativo). Não iniciado.
11. **ETFs** -- estudo futuro, ligado ao grupo Software/IGV. Não
    iniciado.
12. **Renda fixa** -- backlog de longo prazo, sem ação (registrar só).
13. **"Análise de Papel"** -- feature nova: aba separada de "Em Análise"
    (que é exclusiva para estruturas de opções). Permite tirar 3 fotos
    simultâneas com horizontes FIXOS (21/60/90 dias) de um ativo PURO
    (sem opção), para servir de sinal de timing de entrada na ação (se
    preço real ficar abaixo da projeção no curto prazo = sinal de
    possível bom ponto de compra). Motivo de horizontes fixos curtos: cone
    de incerteza do GBM cresce com raiz do tempo, em prazos longos perde
    valor preditivo. Especificação completa registrada na parte 2 deste
    arquivo (sessão 23/06, mais acima). Não iniciado.
14. **Migração Em Análise → Ativa** (a mais complexa, fica por último por
    decisão do usuário): hoje o botão só troca status dentro do mesmo
    registro em analises.json -- NÃO migra para positions.json, NÃO
    reseta data/preço de entrada. Especificação confirmada: migração
    COMPLETA (remove de analises.json, cria em positions.json, sem
    duplicado); preço de entrada = preço REAL do dia da migração (novo
    dia zero genuíno, não o preco_foto antigo). Mapeamento de campos
    entre os 2 schemas ainda não detalhado. Usuário quer carregar uma
    base maior de análises reais primeiro, antes de pensar em ativar
    qualquer uma de verdade.

## Pendências/observações menores
- ADBE e CRWD (e outros do top 10 do IGV) podem continuar fora de
  cobertura mesmo com a paginação nova -- usuário disse que abaixo de ~2%
  de impacto não vale insistir mais.
- Lista de Software pode ser revisada se o usuário decidir que vale
  cobrir holdings menores do IGV (ele mencionou completar para ver o
  tamanho real do setor -- isso já foi parcialmente resolvido pela
  extrapolação via regra de 3).

---

# FLUXO DE ANÁLISE DE LOTE (Fase A) — Critérios consolidados em 23-24/06/2026

Esta seção formaliza o processo que se repete sempre que o usuário traz um lote de
propostas (PDFs do banco e/ou planilha "Index/Fixing/Strike/KO/Delta") para escolher
candidatos antes de "tirar a foto". Aplicar AUTOMATICAMENTE sempre que esse padrão de
input aparecer numa sessão nova, sem precisar que o usuário reexplique os critérios.

## Como decodificar a planilha "Index/Fixing/Strike/KO/Delta"
Vem de propostas FECHADAS do banco (não é menu de escolha livre, já são estruturas de
Retorno Controlado prontas). Colunas:
- **Index**: número de linha/identificador, sem uso analítico
- **Ativo**: ticker B3
- **Fixing**: data de VENCIMENTO da estrutura (não data de criação)
- **Strike**: na verdade é o GANHO/RETORNO da estrutura, expresso como % do valor
  inicial. Ex: "101,02%" significa retorno de **1,02%** no período (subtrair 100)
- **KO (Knock-Out)**: nível de PROTEÇÃO/barreira de baixa, % do valor inicial. Ex:
  "82,00%" = proteção até a ação cair 18% (100% - 82%) sem perder a estrutura
- **Delta**: probabilidade (no momento em que a tabela foi gerada) de o cenário BOM se
  realizar (não tocar a barreira, ganhar o retorno) — quanto MAIOR, melhor, mas é
  informação SECUNDÁRIA na decisão do usuário (ver ordem de critérios abaixo)

## Ordem de critérios do usuário (aplicar nesta ordem, sem pular etapas)

**1º filtro (ALVO/retorno) — eliminatório, sempre primeiro:**
Calcular retorno mensal equivalente = (Strike% - 100) / meses_até_o_fixing.
Usar meses = dias_corridos_até_fixing / 30.4 (a partir de HOJE, não da data de
emissão da planilha).
- Corte: **retorno mensal > 2%** (não "2 a 2,5%" — para este fluxo de filtro
  preliminar de lote, o corte simples é >2%, mais permissivo que a meta de
  2-2,5%/mês usada como referência geral do app)
- Se uma linha NÃO passa neste filtro, ela é DESCARTADA imediatamente — não importa
  o quão boa seja a proteção (KO) ou o Delta. Comprar a ação à vista já seria melhor
  que estruturar por um prêmio menor que isso.
- Ex. confirmado pelo usuário: BBSE3 e CXSE3 NUNCA passam neste filtro em nenhuma
  combinação da planilha de 24/06/2026 (Strike sempre próximo de 100%) — não vale a
  estrutura para esses dois, independente de KO/Delta.

**2º filtro (PROTEÇÃO/KO) — só considerado DEPOIS de passar no 1º:**
Quanto mais funda a proteção (KO mais baixo = % de queda tolerada maior), melhor —
mas só entra na decisão depois do retorno já ter passado no corte de 2%.

**3º critério (DIVIDENDO do papel-base) — desempate / mitigação de pior caso:**
Se a barreira for rompida, o usuário fica com o papel em carteira, sem garantia,
exposto à variação real. Usuário aceita esse risco com mais conforto se o papel
PAGA BEM DIVIDENDO (carrega recebendo renda enquanto espera recuperar/decidir
repetir a operação). Corte usado nesta sessão: **dividend yield > 8%**.
- Resultado possível: papel passa nos 2 (retorno bom + dividendo bom — ideal),
  só no retorno (dividendo zero/baixo — ok mas sem chão se der errado), só no
  dividendo (retorno da estrutura não compensa, mas o usuário pode comprar o
  papel À VISTA mesmo, sem estruturar — esse foi o caso explícito de BBSE3, DY
  18,7% mas retorno de estrutura sempre <2%/mês: "é só pra comprar mesmo"), ou
  nenhum dos 2 (sem interesse).
- ADRs/BDRs de ações americanas que não pagam dividendo (AMZO34, NVDC34, ROXO34,
  TSLA34) e BDR de ETF de prata (BSLV39, nunca paga, metal físico não gera caixa)
  são SEMPRE dividend yield 0% — isso é esperado e não é falha de análise, é
  característica do ativo. Usuário aceita isso conscientemente: tende a concentrar
  o retorno mais alto justamente nessas ADRs (confirmado nesta sessão: ROXO34,
  TSLA34, BSLV39, AMZO34, NVDC34 dominam o topo do ranking de retorno mensal).

## Caso especial: estrutura Bidirecional (ex: WEGE3)
Tratar SEPARADO do ranking de Retorno Controlado — risco assimétrico diferente:
- Ganho fixo (ex: 15%) só é GARANTIDO no lado de ALTA (se romper a barreira de
  alta) ou dentro do range. NÃO há piso garantido no lado de BAIXA — se romper a
  barreira de baixa, o resultado acompanha a queda real da ação integralmente,
  igual às estruturas de Retorno Controlado (sem garantia).
- Por isso WEGE3 (PDF de 24/06/2026, ganho fixo 15% em 12 meses = 1,25%/mês) NÃO
  passou no filtro de retorno >2%/mês desta rodada — mas isso é avaliado como
  ESTUDO SEPARADO do ranking principal, não descartado pelo mesmo critério direto.

## Próximo passo depois do filtro de retorno (>2%) — rodar probabilidade real
Para os candidatos que passam no 1º filtro, USUÁRIO ESCOLHE MANUALMENTE quais
aprofundar (ele "bate o olho" na tabela completa e decide) — Claude NÃO deve rodar
Monte Carlo para todas as 66+ linhas automaticamente, só para as que o usuário
apontar especificamente. Motivo do usuário: quando o retorno é muito alto, pode
valer o risco mesmo com probabilidade menor (ele pode repetir a operação se der
errado) — então a decisão de quais vale a pena rodar com mais rigor é dele, não
um corte automático adicional.

## Entregável esperado pelo usuário neste fluxo
Tabela ÚNICA e completa (CSV/planilha), com TODAS as linhas (inclusive as que NÃO
passam nos critérios, sem esconder) das duas fontes juntas (PDFs + planilha de
opções), ordenada por retorno mensal decrescente, com colunas: origem, ativo,
fixing/vencimento, dias restantes, meses, retorno %, retorno mensal %, flag
passa_retorno_2pct, KO%, proteção%, Delta%, DY%, flag passa_dy_8pct. Usuário prefere
abrir isso no Excel/Sheets dele e filtrar/decidir por conta própria, em vez de receber
só um resumo verbal. Disponibilizar como arquivo para download.

## Lembrete de processo já validado nesta sessão (reforçar)
NÃO subir nada em analises.json neste fluxo até o usuário escolher explicitamente
quais ativos avançar ("eu vou escolher: quero esse e esse, para análise"). O
quadro/tabela é só para ele decidir — a Fase B (registro real) só acontece depois
dessa escolha manual, e mesmo aí seguindo a regra já estabelecida de confirmar os
4 números-chave antes de "tirar a foto".

---

# Fechamento sessão 23-24/06/2026 — Lote de análises + categoria "rejeitada"

## SHAs finais
- proxy.py: eb0381b171afadcb1ef975c2afbb2982c1e0f6b9
- static/app.js: acbe3237e3c38d0e9cc5a250e35bc82140eabf39
- static/style.css: e3305846812e60e8d4ed33f89181fb157d432b49
- templates/index.html: 9ee178b2350ab85295e29732be22a9376a21918e
- analises.json: 4d6bebc1cf01b263340d5231ff3d14a7c9f273de
- stats_analises.json: 558869f0d357da3954f9f5f9f0df5dfb7cb3c074 (arquivo NOVO)

## Feature nova: categoria "rejeitada" para análises (concluída e corrigida)

**Mecânica final correta** (após 2 correções de UX nesta sessão):
- Botão "Encerrar sem executar" (em `em_analise`) foi **renomeado para "🚫
  Rejeitar"** — é ELE que marca `motivo_encerramento='rejeitada'`
  automaticamente (não precisa de lógica nova por fora, o botão já
  existia, só faltava essa semântica).
- Botão "Encerrar operação" (em `ativa`) agora pergunta **sucesso ou
  fracasso** (2 confirmações sequenciais, para não confundir "cancelar a
  ação" com "foi fracasso") — grava em `resultado` ('sucesso'/'fracasso').
- `PUT /analises/<id>/status` aceita `motivo_encerramento` e `resultado`
  opcionais no body.
- Contador **permanente** em `stats_analises.json` (arquivo separado,
  já que `analises.json` é lista pura sem wrapper de metadados) —
  incrementado a cada rejeição, nunca diminui.
- `GET /analises` filtra da **resposta** (não do arquivo real) itens
  rejeitados com mais de 30 dias desde `data_rejeicao` — o contador
  permanente já garante a estatística de longo prazo independente disso.
- Novo endpoint `GET /analises/stats` expõe o contador.

**Localização correta da UI** (usuário corrigiu o posicionamento errado
que eu tinha feito inicialmente):
- Aba **"Em Análise"** mostra SÓ `em_analise`/`ativa` — limpa, sem
  dashboard misturado.
- Aba **"Encerradas"** tem 2 seções agora: "Histórico de Operações"
  (posições reais, `positions.json`, já existia) + nova seção "Histórico
  de Análises (Fase A)" (`analises.json`, rejeitadas + encerradas reais
  com sucesso/fracasso), cada uma com seu próprio mini-dashboard no
  mesmo estilo visual (`calcDashboardEncerradas`/`pos-enc`/`enc-badge`).
- Uma vez rejeitada/encerrada, a análise MIGRA por completo da aba Em
  Análise para Encerradas — não fica visível nos dois lugares.

## Resultado do exercício "qual das 7 em análise é melhor" (concluído)
Comparando retorno nominal × probabilidade REAL (Monte Carlo, já
calculada pela engine na observação de cada análise):

| Ativo | Tipo | Retorno/mês | Probabilidade | Decisão |
|---|---|---|---|---|
| ROXO34 (an_1782100906) | Retorno Controlado | 9,00% | 88,89% | Mantida em_analise |
| TSLA34 (an_1782100907) | Retorno Controlado | 5,45% | 87,59% | Mantida em_analise |
| AXIA3 (an_1782124389) | Bidirecional | 4,00% (teto) | 40,85% | Mantida em_analise |
| PETR4 (an_1782098774) | Bidirecional | 2,25% (teto) | 17,90% | **Rejeitada** |
| VALE3 (an_1782124685) | Bidirecional | 2,46% (teto) | 31,86% | **Rejeitada** |
| ROXO34-PUT (an_1782147275) | Venda de PUT | 2,26% | — (baixa liquidez) | **Rejeitada** |
| ROXO34-Call (an_1782123970) | Venda de Call | 1,00% | — (abaixo da meta) | **Rejeitada** |

Lição confirmada pelo usuário nesta sessão: "não adianta o número estar
bonito se a chance é ruim" — retorno nominal alto não compensa
probabilidade real baixa de bater a meta.

## ⭐ NOVO: Lote de análise de propostas reais (24/06/2026) — AINDA EM ABERTO

Usuário trouxe um lote grande: 8 PDFs reais do Itaú (WEGE3-bidirecional,
AMZO34/BEEF3/BSLV39/CYRE3/NVDC34/ROXO34/TSLA34-retorno controlado) + uma
planilha de 144 linhas (ALOS3/BBSE3/CMIN3/CXSE3/DIRR3/PETR4/PRIO3/VALE3,
campos Index/Fixing/Strike/KO/Delta).

**Processo aplicado, já formalizado na seção "FLUXO DE ANÁLISE DE LOTE"
mais acima neste arquivo** (critérios: retorno mensal >2%, depois KO,
depois DY >8% como desempate/mitigação, EV=retorno×Delta para desempate
entre combinações do mesmo ativo).

**Resultado final, ainda PENDENTE de decisão do usuário sobre subir ou
não para análise** (ele disse explicitamente "não é pra subir nada
ainda sem falar comigo" — aguardando ele escolher quais):

Candidatos que sobraram depois das exclusões do usuário (BBSE3, CXSE3,
WEGE3, PRIO3, BEEF3 excluídos por comparação direta com alternativas
melhores):

| Ativo | Fixing (melhor por EV) | Dias | Ret. mensal | Delta |
|---|---|---|---|---|
| DIRR3 | 08/07/2026 | 14 | 5,69% | 46,4% |
| CMIN3 | 08/07/2026 | 14 | 4,34% | 53,1% |
| ROXO34 (PDF) | 21/08/2026 | 58 | 4,66% | — |
| TSLA34 (PDF) | 21/08/2026 | 58 | 4,61% | — |
| BSLV39 (PDF) | 21/08/2026 | 58 | 4,35% | — |
| AMZO34 (PDF) | 10/08/2026 | 47 | 3,88% | — |
| CYRE3 (PDF) | 21/08/2026 | 58 | 2,94% | — |
| PETR4 | 08/07/2026 | 14 | 2,65% | 66,0% |
| ALOS3 | 21/09/2026 | 89 | 2,13% | 47,1% |
| VALE3 | 08/07/2026 | 14 | 2,11% | 71,5% |

**Próximo passo quando a sessão continuar**: usuário vai "bater o olho"
e escolher manualmente quais desses 10 candidatos avançar para
"tirar a foto" (Fase B) — alguns são PDFs do banco (4 números já
fechados), outros são da planilha (também já fechados, formato similar).
Nenhum foi registrado em analises.json ainda.

## Lembretes de processo reforçados nesta sessão
- Sempre avisar explicitamente quando algo estiver pronto para o usuário
  testar.
- Sempre usar ask_user_input_v0 (popup com botões) para perguntas que
  exigem decisão do usuário, nunca só texto corrido.
- Para análise de lote: tabelas SEMPRE em formato de tabela visual
  (markdown), nunca em texto corrido — usuário tem dificuldade de
  analisar informação densa em prosa.
- Antes de implementar uma feature nova que parece exigir lógica do
  zero, verificar se já existe um mecanismo parecido no código (ex: o
  botão "Encerrar sem executar" já era o "Rejeitar", só faltava a
  semântica certa — não precisava reinventar por fora).

---

# Anexo — Tabelas completas do lote de 24/06/2026 (exclusivas deste lote)

Estas são as DUAS tabelas completas construídas e usadas para a filtragem
e decisão do lote de 24/06/2026 (8 PDFs + planilha de 144 linhas). O
resumo de 10 candidatos já registrado na seção anterior é o RESULTADO
final dessas tabelas — aqui fica o caminho completo, caso precise
revisitar/refazer o raciocínio numa sessão futura.

## Tabela 1 — Critério completo (retorno + dividendo), pós-exclusões do usuário

Critério: retorno mensal equivalente > 2% (eliminatório) + dividend
yield do papel-base > 8% (desempate/mitigação de pior caso). Exclusões
já aplicadas pelo usuário: BBSE3, CXSE3 (nunca passam retorno), PRIO3
(PETR4 quase igual em retorno e paga dividendo), BEEF3 (comentado antes
como fora), WEGE3 (bidirecional, estudo separado — sem piso de queda).

| Ativo | Origem | Fixing | Dias | Ret. total | Ret. mensal | DY | Passa os 2? |
|---|---|---|---|---|---|---|---|
| CMIN3 | Tabela | 21/09/2026 | 89 | 13,61% | 4,65% | 11,7% | ✅✅ |
| ROXO34 | PDF | 21/08/2026 | 58 | 8,90% | 4,66% | 0% | Só retorno |
| TSLA34 | PDF | 21/08/2026 | 58 | 8,80% | 4,61% | 0% | Só retorno |
| BSLV39 | PDF | 21/08/2026 | 58 | 8,30% | 4,35% | 0% | Só retorno |
| DIRR3 | Tabela | 21/09/2026 | 89 | 12,26% | 4,19% | 9,0% | ✅✅ |
| AMZO34 | PDF | 10/08/2026 | 47 | 6,00% | 3,88% | 0% | Só retorno |
| PETR4 | Tabela | 21/09/2026 | 89 | 9,38% | 3,20% | 12,0% | ✅✅ |
| CYRE3 | PDF | 21/08/2026 | 58 | 5,60% | 2,94% | 12,8% | ✅✅ |
| VALE3 | Tabela | 21/09/2026 | 89 | 6,23% | 2,13% | 9,0% | ✅✅ |
| ALOS3 | Tabela | 21/09/2026 | 89 | 6,25% | 2,13% | 12,0% | ✅✅ |

## Tabela 2 — Melhor combinação por ativo via EV (retorno × Delta), pós-desempate

Para ativos com múltiplas combinações na planilha (DIRR3, CMIN3, PETR4,
VALE3, ALOS3), o usuário pediu desempate por EV simplificado = retorno
mensal × (Delta/100), em vez de só o maior retorno isolado — porque
retorno mais alto às vezes "compra" probabilidade (Delta) muito mais
baixa. Resultado: todos os 4 com opção de vencimento curto (08/07/2026,
14 dias) convergiram para essa data como melhor EV (só ALOS3 não tinha
opção curta na planilha filtrada).

| Ativo | Fixing | Dias | Ret. total | Ret. mensal | Delta | EV |
|---|---|---|---|---|---|---|
| DIRR3 | 08/07/2026 | 14 | 2,62% | 5,69% | 46,4% | 2,64 |
| CMIN3 | 08/07/2026 | 14 | 2,00% | 4,34% | 53,1% | 2,31 |
| ROXO34 (PDF) | 21/08/2026 | 58 | 8,90% | 4,66% | — | — |
| TSLA34 (PDF) | 21/08/2026 | 58 | 8,80% | 4,61% | — | — |
| BSLV39 (PDF) | 21/08/2026 | 58 | 8,30% | 4,35% | — | — |
| AMZO34 (PDF) | 10/08/2026 | 47 | 6,00% | 3,88% | — | — |
| CYRE3 (PDF) | 21/08/2026 | 58 | 5,60% | 2,94% | — | — |
| PETR4 | 08/07/2026 | 14 | 1,22% | 2,65% | 66,0% | 1,75 |
| ALOS3 | 21/09/2026 | 89 | 2,13% | 2,13% | 47,1% | 1,00 |
| VALE3 | 08/07/2026 | 14 | 0,97% | 2,11% | 71,5% | 1,51 |

## Observação importante sobre DIRR3/CMIN3/PETR4/VALE3
As duas tabelas têm fixing DIFERENTE para esses 4 ativos (Tabela 1 usa
21/09/2026 — maior retorno total nominal — Tabela 2 usa 08/07/2026 —
melhor EV). O usuário AINDA NÃO decidiu qual das duas filosofias seguir
para esses 4 quando for escolher os candidatos finais — isso precisa ser
resolvido antes de "tirar a foto" de qualquer um desses 4 (CMIN3, DIRR3,
PETR4, VALE3). Os outros 6 (ROXO34, TSLA34, BSLV39, AMZO34, CYRE3, ALOS3)
não têm esse conflito — são os mesmos números nas duas tabelas.

---

# Correção final 24/06/2026 — Dashboard de análises simplificado para funil único

## SHA final
- static/app.js: 3625c11c541c6e489d7b5107dba0f03be4e753ce

Usuário simplificou o dashboard de análises (na aba Encerradas, seção
"Histórico de Análises"): NÃO precisa separar por "fase" — é UM
histórico único. Removida a divisão anterior em 2 dashboards.

**Funil final (4 cards, nesta ordem):**
1. **Total Analisado** — todas as análises que já existiram, incluindo
   rejeitadas que já saíram da listagem visível após 30 dias (usa o
   contador permanente de `stats_analises.json` para compensar isso:
   `total = visiveis.length + max(0, total_rejeitadas_permanente -
   rejeitadas_ainda_visiveis)`).
2. **Aprovadas/Ativadas (%)** — do total, quantas chegaram a ser ativas
   de fato (inclui as que ainda estão `ativa` agora + as já `encerrada`
   com campo `resultado` preenchido).
3. **Rejeitadas (%)** — do total, usa o contador PERMANENTE (não as
   visíveis), já que nunca chegaram a ser ativas.
4. **Taxa de Sucesso (%)** — calculada SÓ entre as que têm
   `status==='encerrada' && resultado` (ou seja, só entre as que
   realmente foram ativas e fecharam) — NÃO inclui rejeitadas no
   denominador, porque elas nunca foram testadas de verdade.

Estado real hoje (24/06/2026, 7 análises totais): Total=7,
Aprovadas/Ativadas=0% (nenhuma virou Ativa ainda — as 3 atuais, ROXO34/
TSLA34/AXIA3, são comparações teóricas em `em_analise`), Rejeitadas=57%
(4 de 7), Taxa de Sucesso=— (ainda não há nenhuma encerrada com
resultado, pois nenhuma análise chegou a ser ativada e depois encerrada
de fato ainda).

## Estado da sessão ao encerrar (24/06/2026)
Usuário confirmou que vai abrir uma NOVA sessão a partir daqui. Pontos
em aberto para quando ela começar:

1. **Lote de 24/06 ainda não decidido** — usuário precisa "bater o olho"
   nas duas tabelas completas (ver seção "Anexo — Tabelas completas do
   lote") e escolher manualmente quais dos 10 candidatos avançar para
   Fase B. Conflito de fixing em 4 ativos (CMIN3/DIRR3/PETR4/VALE3) entre
   Tabela 1 (retorno total maior, prazo longo) e Tabela 2 (EV maior,
   prazo curto) ainda não resolvido.
2. **Dashboard de análises (Encerradas) implementado e validado** pelo
   usuário nesta sessão — não precisa de mais ajuste, a menos que ele
   peça.
3. Todo o resto do backlog (FIIs, ETFs, Renda fixa, "Análise de Papel",
   Migração Em Análise→Ativa) continua igual, sem mudança nesta sessão.

---

# Sessão 25/06/2026 — Lote de 24/06 resolvido e subido (14 análises)

## SHA final
- analises.json: 21f23087b89d1efe66ab185356d667ee5124451c

## Ambiguidade dos 4 ativos (DIRR3/CMIN3/PETR4/VALE3) — RESOLVIDA
Usuário decidiu: subir AMBAS as versões (curto 08/07 e longo 21/09) em vez de
escolher uma filosofia só. Justificativa: ambas estão dentro do limite de
~120 dias considerado aceitável para uma análise (o limite mais estrito é
para posição REALIZADA, não para o registro em análise). Decisão vale como
padrão para casos futuros parecidos — não reabrir essa discussão sem motivo
novo.

## Campo novo: `lote` em analises.json
Adicionado a cada registro de análise, formato `"lote": "AAAA-MM-DD"` (data
do lote de origem, não necessariamente igual a `data_foto`). Objetivo:
diferenciar lotes diferentes quando o usuário trouxer novos no futuro, mesmo
padrão de utilidade do campo `backtest`. Usar esse campo (não criar um novo)
sempre que houver outro lote de candidatos.

## KOs dos PDFs do banco extraídos corretamente (lição: sempre ler o PDF antes de assumir)
Os 5 PDFs do lote de 24/06 (AMZO34/BSLV39/CYRE3/ROXO34/TSLA34) tinham a
barreira (KO) só no documento, não nas tabelas-resumo já registradas em
sessão anterior. Usuário enviou os 5 PDFs reais; KOs extraídos da seção
"Composição da Estratégia" de cada (campo "Valor da Barreira"):
- AMZO34: barreira -10,00% (89,90% do valor inicial), vencimento 10/08/2026
- BSLV39: barreira -20,00% (79,90%), vencimento 21/08/2026
- CYRE3: barreira -20,00% (79,90%), vencimento 21/08/2026
- ROXO34 (retorno_controlado, NOVA estrutura): barreira -18,40% (81,50%),
  vencimento 21/08/2026 — independente da posição ativa real ROXOG105
  (strike R$10,50, vencimento 16/07/2026), mesmo padrão da an_1782123970
  antiga (call simples), mas esta é retorno_controlado.
- TSLA34: barreira -20,00% (79,90%), vencimento 21/08/2026

## KOs dos 4 ativos com conflito de fixing (planilha) confirmados via dados reais
Usuário colou a planilha completa de 144 linhas. Confirmado por cálculo
reverso (retorno mensal e EV batendo com os números já registrados na
Tabela 2 da sessão anterior):
- PETR4/VALE3 prazo curto (08/07): KO = 91,80% (não 87,80%, que é uma
  combinação de KO mais raso disponível na mesma planilha mas não a que
  gerou os números já registrados)
- DIRR3/CMIN3 prazo curto (08/07): mesma lógica, KO = 91,80% confirmado
  (vs. alternativa 87,80% que dava números diferentes)
- Todos os 4 ativos no prazo curto usam a MESMA combinação de barreira
  (91,80%), sinal de que vêm do mesmo lote/dia de emissão da planilha.

## Preços de foto (preco_foto) coletados via web search, não via Yahoo direto
Yahoo confirmado bloqueado no sandbox (bash_tool/web_fetch, mesmo padrão já
documentado em sessões anteriores). Preços usados (fonte StatusInvest/ADVFN,
25/06/2026, mais recentes disponíveis no momento da busca):
PETR4=39.33, VALE3=79.38, ALOS3=27.13, DIRR3=12.81, CMIN3=4.31, ROXO34=14.01,
TSLA34=65.12, BSLV39=96.68, AMZO34=61.01, CYRE3=20.86.
**Limitação assumida**: alguns desses preços têm 1-2 semanas de defasagem
(fonte não tinha cotação de hoje exata para todos os ativos) — usuário pode
querer confirmar/corrigir manualmente os preços de foto mais sensíveis antes
de tomar decisão final, especialmente para os de prazo curto (14 dias), onde
a defasagem do preço de entrada tem mais impacto proporcional no resultado.

## 14 análises subidas, todas em_analise, backtest=false, lote=2026-06-24
IDs an_1782394704 a an_1782394717. Ver analises.json no repo para o detalhe
completo de cada uma. Usuário vai analisar os resultados de probabilidade
(Monte Carlo, calculados pela engine ao abrir cada card no app) para decidir
o que rejeitar ou manter — não decidir por conta própria nem pré-filtrar.

## Próximo passo
Usuário vai abrir o app (aba Em Análise) e olhar os botões/probabilidades já
calculadas pela engine para cada uma das 14. Verificar se os botões de
status (Rejeitar / Marcar como Ativa) estão funcionando corretamente — não
testado nesta sessão ainda. Backlog de "Análise de Papel" mencionado como
possivelmente já implementado ou não — PRECISA CONFIRMAR no código real
antes de assumir, usuário não tem certeza do estado atual desse item.

---

# Sessão 25/06/2026 (parte 2) — Endpoint de ranking em lote + correção de dados + lições de cache

## SHAs finais desta parte
- proxy.py: 470dd940e0a23a80c47ff4a53549136946fe52e5
- static/app.js: b6b82ff3dc67991bd64a656ef4b0f4e25d49fb71
- templates/index.html: b7ab4663c28b680138c5b7f9e66e22bd03a51087
- analises.json: 253232d5d5f2fd217c69b86976947cdc25439536 (após rejeição real de AXIA3
  feita pelo usuário em teste)

## ⭐ Feature nova: GET /analises/ranking (resolve o problema de escala do lote)
Usuário identificou que copiar manualmente probabilidade de cada análise (abrindo
card por card) não escala para lotes de 14+ — formalizado um endpoint que roda
Monte Carlo de TODAS as `em_analise` de uma vez e devolve tabela ordenada por
score. Especificação fechada com o usuário antes de implementar (ver árvore de
decisão desenhada na sessão — diagrama SVG mostrado em chat, não persiste no
repo, mas a lógica está documentada abaixo).

**Fórmula do score (fechada com usuário em 25/06/2026):**
```
retorno_mensal = ganho_pct / meses_restantes
peso_prazo = 1 + (30/dias_restantes) * 0.1   (vantagem leve, giro de capital --
                                                usuário confirmou "peso levinho")
SE papel-base tem DY relevante (cadastrado em FUND_OVERRIDE_GLOBAL, > 0, e
NAO está em _SEM_DY_RELEVANTE -- ROXO34/TSLA34/BSLV39/AMZO34/PRIO3):
    colchao_vs_cdi = (dy_anual/12) - (cdi_anual/12)
    score = (prob_meta/100) * retorno_mensal * peso_prazo + (0.1 se colchao>0)
SE NAO (BDR/ADR/commodity sem dividendo): score = puro, sem bonus de colchao
```
CDI buscado via `get_cdi()` já existente (API Bacen, SGS 4389), nao hardcoded.

**Tabela NUNCA filtra/esconde linha** -- score e so para ORDENACAO. Linhas com
erro de calculo aparecem com motivo explicito, nunca somem silenciosamente.

**Lógica de decisão sobre DY/CDI, fechada com o usuário (importante para
qualquer extensão futura do critério):**
- Bidirecional/retorno_controlado: se romper a barreira, fica com o papel --
  nesse cenário o DY funciona como "colchão" comparado ao CDI (custo de
  oportunidade). Quanto mais o DY mensal supera o CDI mensal, melhor o
  consolo do pior caso.
- BDR/ADR/commodity sem dividendo relevante: nao tem esse colchao -- decisao
  cai 100% em prob_meta x retorno_mensal puro (usuario: "eu vou sempre olhar
  mais a probabilidade e a meta... se está muito acima com boa probabilidade
  é pra onde eu vou").

**Dado novo cadastrado:** ALOS3 nao tinha DY em lugar nenhum do codigo --
adicionado a FUND_OVERRIDE_GLOBAL com 10,27% (StatusInvest, 25/06/2026).
Mesma lacuna deveria ser checada para qualquer ticker novo que entrar em
lotes futuros (nem todo ativo da B3 tem DY cadastrado ainda).

## Painel de ranking na aba Em Análise (UI)
Botão "Rodar ranking" no topo da aba (acima da lista de cards), abre tabela
com: Ativo+nome completo, Tipo (rotulo curto BI/RC/SI/PR com title no
hover), Prazo, Ret. mensal, Prob., DY, Colchão (com tooltip explicando a
fórmula), Score, e coluna de Ação com botões ✓ (Aprovar/Marcar como Ativa)
e 🚫 (Rejeitar) DIRETO NA LINHA.

**Decisão de UX importante:** os botões "Marcar como Ativa"/"Rejeitar" foram
REMOVIDOS dos cards soltos de Em Análise (tplAnaliseAcoes) -- usuário decidiu
que não faz sentido duplicar a ação em dois lugares agora que o ranking é o
ponto de decisão real. Cards mantêm só "Encerrar operação" para quem já
está `status=ativa` (isso não faz parte do fluxo de ranking, que é só para
`em_analise`).

**Erro cometido e corrigido nesta sessão:** ao implementar a primeira versão
da tabela, removi a coluna "Tipo" por engano (usuário tinha pedido só para
ENCURTAR colunas, não remover nenhuma). Corrigido restaurando com rótulo
curto + title. Lição: ao receber pedido de "encurtar"/"compactar", nunca
remover uma coluna/campo sem confirmação explícita -- só reduzir largura/
formato.

## Bug real encontrado e corrigido: preço desatualizado quebrava o cálculo
Ao montar o lote de 14 análises (sessão anterior, mesma data), o `preco_foto`
da ROXO34 (retorno_controlado, lote 24/06) foi coletado errado via busca web
(R$14,01, fonte sem timestamp confiável) -- o preço real na época já estava
em ~R$10,90-10,96 (ROXO34 caiu bastante: rebaixamento BofA + saída do CFO
Guilherme Lago). Isso fez o `kdo` calculado (R$11,43) ficar ACIMA do preço
real, ou seja, a barreira já estaria tecnicamente "rompida" pelo próprio
preço de partida da simulação -- resultado: `prob_meta=0,1%` no ranking,
descoberto justamente porque o ranking expôs o outlier (usuário suspeitou
"essa deve estar distorcida" ao ver o score quase zero).

**Corrigido:** `preco_foto`→10.96, `kdo` recalculado→8.94 (mesma barreira
-18,40% do PDF, premissa fixa mantida). Após a correção, ROXO34 do lote
voltou a uma posição de ranking coerente (score ~3.9, prob ~80%).

**Lição de processo reforçada:** sempre que um preço coletado por busca web
(não Yahoo/brapi direto, que estão bloqueados no sandbox) alimentar um
cálculo de barreira/KDO, é prudente desconfiar de scores/probabilidades
extremas (muito perto de 0% ou 100%) como sinal de possível erro de dado de
entrada -- o endpoint de ranking, ao rodar TODAS de uma vez, serviu como uma
boa ferramenta de detecção de outliers para esse tipo de erro.

## Lição de infraestrutura: cache de raw.githubusercontent.com após rejeição
Usuário testou o botão Rejeitar (AXIA3) -- backend gravou corretamente e na
HORA no GitHub (confirmado via API Contents: status='encerrada',
motivo_encerramento='rejeitada'), mas o app continuou mostrando a AXIA3 no
card de Em Análise por alguns minutos, sem aparecer ainda em Encerradas.

**Causa confirmada:** `GET /analises` lê via `raw.githubusercontent.com`
(não API Contents) -- mesmo com header `Cache-Control: no-cache` na
requisição do backend, a CDN do GitHub para raw.githubusercontent.com NÃO
respeita esse header do lado do servidor/CDN e serve uma cópia em cache por
alguns minutos após qualquer commit. Isso é uma limitação conhecida da
infraestrutura do GitHub (mesma causa raiz já documentada antes nesta sessão
para outro contexto: "raw.githubusercontent.com ficou desatualizado por
alguns minutos após o commit (CDN/cache), apesar do SHA via API Contents já
estar correto").

**Não há correção de código possível para isso** (não dá para forçar a CDN
do GitHub a invalidar cache do lado de fora). Comportamento esperado:
esperar alguns minutos (variável, não documentado por tempo fixo) após
qualquer ação que grave no analises.json antes de esperar refletir na
listagem. Usuário confirmou entendimento e que o teste funcionou após
esperar.

## Resultado do teste real do usuário (validado)
1. ✅ AXIA3 rejeitada via botão na tabela de ranking -- confirmou popup,
   linha saiu do ranking imediatamente, e após esperar alguns minutos
   (propagação do cache do GitHub), também saiu do card de Em Análise e
   foi confirmada como migrada (status real no GitHub: encerrada/rejeitada).
2. Rejeição em lote (clicar em várias seguidas) -- confirmado que funciona
   da mesma forma, cada clique é independente.

## ⭐ Reflexão sobre o score -- registrado para evolução futura
Usuário perguntou se o score atual é "como os grandes bancos decidem" --
resposta honesta dada: NÃO é um modelo rigoroso de mercado, é uma heurística
pragmática para o fluxo específico do usuário. Diferenças reais de um modelo
mais rigoroso:
- Bancos usariam Sharpe/Sortino (retorno ajustado a volatilidade real), não
  só probabilidade de bater uma meta binária.
- O "colchão vs CDI" (bônus fixo de +0.1) é uma boa intuição prática, mas um
  modelo rigoroso ponderaria TODOS os cenários (sucesso/parcial/pior caso)
  por probabilidade e valor presente, não um bônus binário.
- O peso_prazo (vantagem de 10% para prazo curto) é preferência pessoal do
  usuário (giro de capital), sem fundamento de mercado -- está correto para
  o objetivo dele, mas não é "como o mercado precifica".

**Usuário confirmou explicitamente: quer evoluir para EV completo (Valor
Esperado ponderado por TODOS os cenários do `prob_retorno_faixas`, que a
engine já calcula mas não está sendo usado no score hoje) em sessão futura.**
Não implementado ainda -- só registrado como próximo passo prioritário do
ranking.

## Backlog novo desta sessão (ordem sugerida)
1. ⭐ **PRÓXIMO PASSO PRIORITÁRIO:** evoluir score do ranking para EV
   completo, usando `prob_retorno_faixas` (já calculado pela engine) em vez
   de só `prob_meta` binária -- pondera TODOS os cenários (perda, parcial,
   meta, acima da meta) por probabilidade, não só "bateu ou não bateu".
2. **Minério de Ferro (TIO=F) parece fixo/sem oscilar em Cotações** --
   usuário notou e pediu para investigar em sessão futura (sem ação ainda).
   Possível causa a investigar: mesmo padrão de liquidez baixa/rollover já
   documentado para essa commodity especificamente, ou bug separado no
   fetch/cache do valor.
3. Lote de 24/06 -- usuário começou a decidir via ranking (AXIA3 rejeitada
   em teste real, não só teste de UI). Resto do lote (13 análises restantes
   + as 2 antigas que sobraram em_analise: ROXO34 posição real e
   ROXO34/TSLA34 do lote antigo) ainda aguardando decisão -- usuário vai
   usar o ranking para decidir o resto.
4. Resto do backlog de sessões anteriores continua igual (FIIs, ETFs, Renda
   fixa, "Análise de Papel", Migração Em Análise→Ativa) -- sem mudança.

## Lembrete de processo reforçado nesta sessão
- Ao receber pedido de "encurtar"/"compactar" algo visual, nunca remover um
  campo/coluna sem confirmação explícita -- só reduzir formato/largura.
- Scores ou probabilidades extremas (perto de 0% ou 100%) em qualquer
  cálculo em lote são sinal de possível erro de dado de entrada (preço
  desatualizado, barreira mal calculada) -- vale conferir antes de assumir
  que é um resultado real.
- Após qualquer escrita no analises.json via app (não via sessão de chat),
  esperar alguns minutos antes de assumir que a listagem (`GET /analises`,
  que lê via raw.githubusercontent.com) já reflete a mudança -- é
  limitação de cache de CDN do GitHub, não bug de lógica.
