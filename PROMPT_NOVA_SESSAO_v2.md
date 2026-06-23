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
