# Trader Desk — Prompt de Continuação (v35 — FECHAMENTO MESTRE 10/07/2026)

## ⭐ COMECE AQUI NA PRÓXIMA SESSÃO ⭐

Sou o Claude continuando o desenvolvimento do Trader Desk com o Victor. Antes de qualquer coisa:
1. Puxar este arquivo (`PROMPT_NOVA_SESSAO_v2.md`) via `api.github.com` (nunca `raw.githubusercontent.com` — CDN cacheia).
2. Puxar também `ROTINA_GATES_LOTE.md` se o usuário trouxer um lote de opções pra analisar.
3. Verificar SHAs abaixo antes de editar qualquer arquivo (sempre buscar fresco, nunca reutilizar SHA de memória).
4. Sistema é de TOMADA DE DECISÃO (melhorar assertividade), não controle de carteira/P&L exato — isso as corretoras já dão.

## 📚 Lições conceituais do Victor (não são backlog — princípios de julgamento que devem persistir entre sessões)

**Alvo único de todas as operações de venda de opção (11/07/2026):** independente da estrutura
(lançamento simples, retorno controlado, bidirecional), o objetivo primário é SEMPRE gerar
2–2,5%/mês via prêmio. A estrutura escolhida (barreira, proteção, teto) não é a meta em si — é
só a "embalagem de risco" que blinda esse alvo dependendo de quanto o cenário pode virar contra
o Victor. Ao analisar qualquer operação nova ou existente, o corte de qualidade é sempre esse
alvo de prêmio mensal — não confundir com o preço do strike, com o retorno total (prêmio +
valorização), ou com qualquer outra métrica de retorno.

**Definição de sucesso é própria do Victor, não é o retorno numérico da opção em si.** Ele não
vende a ação — carrega no tempo. Por isso, para lançamento coberto simples (ex: BBAS3), sucesso
= NÃO ser exercido + embolsar o prêmio, mesmo que o preço da ação tenha caído e o prêmio não
cubra a queda. Se cair, a saída não é vender no prejuízo — é rolar (gerar novo prêmio) ou, se a
queda for relevante, comprar mais ações no preço menor (reduz preço médio, aumenta posição).
Isso é uma tática de recuperação, não o plano principal — e só existe porque ele critérios o
ativo de forma a aceitar carregá-lo/aumentar posição de qualquer jeito.

**Decisão de "entregar o papel" (quando exercido/no topo) é caso a caso, não regra fixa.** Se o
Victor avalia que o papel ainda tem upside relevante (leitura gráfica/momentum), ele tenta ROLAR
PARA CIMA (subir o strike) em vez de simplesmente entregar — isso captura parte da valorização
já ocorrida (diferença entre strike antigo e novo) + gera novo prêmio. Só funciona "se possível"
(depende de ter prêmio decente disponível no novo strike/prazo). Se avalia que o papel já
esgotou o upside, aí sim entrega sem rolar e busca outro ativo. **Contra-exemplo didático:
ROXO34** — a subida foi rápida e violenta demais para rolar dentro dos critérios normais de
qualidade; a rolagem feita foi defensiva/emergencial ("por fora", só para sobreviver e ganhar
tempo), não estratégica. Ou seja: rolar-capturando-alta é o plano quando cabe dentro do filtro
de qualidade normal; quando o papel corre demais rápido demais, a rolagem vira modo de
sobrevivência, não plano A.

**Por que ele estuda estruturas diferentes (retorno controlado, bidirecional) em vez de só
lançamento simples:** cada uma resolve um risco diferente do lançamento simples puro.
- Retorno controlado (proteção na queda): aumenta o range em que ele ganha, absorvendo parte da
  queda no período — troca upside acima de um teto por proteção na cauda ruim.
- Bidirecional: ganha em ambas as direções dentro de um range, mas se a barreira de alta for
  rompida, a alavancagem embutida faz perder o upside todo de uma vez — esse é o risco que ele
  chama de "se alavancar e perder tudo se subir demais".
- Lançamento simples: mais direto, mas se o papel disparar muito acima do strike, perde 100% do
  excedente sem nenhuma rede de proteção.

Essas leituras devem informar qualquer análise futura de posição ativa ou lote novo — ao montar
uma explicação de probabilidade/cenário para o Victor, sempre traduzir os números pela régua dele
(sucesso = não-exercício + prêmio embolsado, para ativos que ele quer carregar), não só pelo
número bruto de retorno ou probabilidade de exercício.


## 🔍 Achado técnico (11/07/2026) — diagnóstico de FIIs incompleto vs. tela

`/fiis/diagnostico` só reflete o scraping do Fundamentus puro (universo bruto = 560, 186
descartados — 182 por liquidez baixa, 4 por DY zerado/ausente, 374 válidos). A tela do app,
porém, carrega uma segunda onda depois via `/fiis/universo-complementar` (FI-Infra não
cobertos pelo Fundamentus), que sobe o total pra ~592 brutos e ~401 válidos — mas essa leva
**não é capturada pelo diagnóstico**, então os dois números nunca batem. Constatado, não
corrigido — não é bug urgente, só uma limitação de arquitetura a ter em mente ao usar o
diagnóstico pra decisões de corte de base.

**Decisão do Victor sobre o próximo passo de qualidade de base:** em vez de reformar o
diagnóstico (mais caro) ou implementar keyword/cotação-congelada (exigem histórico que hoje
não é guardado), o caminho mais simples e imediato é trocar o critério de liquidez de
"liquidez do dia da consulta" para **"liquidez média"** (ex: média móvel de N dias, a definir)
— resolve o problema mais citado (fundo escapar do filtro por um dia bom, ou ser descartado
por um dia ruim pontual) sem exigir arquitetura nova de série histórica complexa, desde que a
fonte (Fundamentus) exponha esse dado agregado. A verificar na próxima sessão se o Fundamentus
já traz essa média pronta ou se precisa ser calculada a partir de dados diários armazenados.

## 🧹 Backlog — Limpeza da base de FIIs ("gordura"), por nível de esforço (11/07/2026)

Contexto: universo bruto real hoje é ~560 (Fundamentus) + ~30 complementares (FI-Infra) ≈ 592;
filtro de liquidez atual (do dia, <R$50k/dia) já descarta 182 por liquidez + 4 por DY zerado,
deixando ~374-401 válidos. Critérios abaixo foram estudados mas **nenhum implementado ainda**
— ordem de ataque sugerida é a da lista (fácil → difícil).

### 🟢 FÁCIL — próximo passo já decidido, atacar primeiro
1. **Liquidez média (em vez de liquidez do dia)** — trocar o critério pontual por uma média
   (ex: móvel de 30 dias, a definir). Resolve o caso de fundo escapar do filtro por 1 dia bom
   ou ser descartado por 1 dia ruim pontual. A verificar: se o Fundamentus já expõe essa média
   pronta ou se precisa ser calculada a partir de coleta diária armazenada (ainda não existe
   histórico guardado hoje — scraping é sempre ao vivo, sem cache de série temporal).
2. **Keyword no nome do fundo** ("Em Liquidação", "Incorporação", etc.) — regex simples sobre
   o nome/razão social já disponível no scraping atual. Não exige histórico.

### 🟡 MÉDIO — exige mais dado ou mais julgamento, mas não é complexo estrutural
3. **Patrimônio líquido mínimo** — cortar fundos muito pequenos (ex: <R$30-50 milhões), sinal
   de spread maior e risco de encerramento/incorporação. Dado provavelmente já vem no
   scraping, só falta decidir o piso.
4. **Idade do fundo / tempo de listagem** — fundos com <12-18 meses não têm histórico
   suficiente pra avaliar consistência de provento/vacância. Não é "lixo", mas deveria cair
   numa camada intermediária, não direto na líquida.
5. **Concentração de cotistas** — poucos cotistas (ex: <500-1000) correlaciona com liquidez
   estruturalmente baixa, não circunstancial. Depende de o Fundamentus/fonte expor esse dado.

### 🔴 DIFÍCIL — exige histórico de série temporal (arquitetura nova, mais caro)
6. **Cotação congelada** — preço parado por N pregões seguidos = sinal de fundo sem negociação
   real, mesmo que a fonte não erre o dado pontual. Exige guardar preço diário histórico, que
   hoje não existe (tudo é scraping ao vivo, sem cache).
7. **Consistência de dividendo (regularidade, não valor)** — desvio-padrão dos pagamentos
   mensais dos últimos 12 meses vs. média. Fundo que paga 8 meses e pula 4 é sinal de
   instabilidade de caixa mesmo com DY nominal atraente. Exige histórico de proventos.
8. **Vacância física/financeira sustentada** (só FIIs de tijolo) — vacância >20-25% por vários
   meses seguidos é sinal de ativo problemático. Exige série histórica de vacância, não só
   snapshot atual.
9. **Alavancagem/dívida do fundo** (FIIs de papel/CRI) — risco de crédito que "preço parado"
   não captura. Depende de a fonte expor esse dado — não confirmado se Fundamentus tem.

### 📌 Achado técnico relacionado (ver seção acima)
`/fiis/diagnostico` não reflete a leva complementar de FI-Infra (~30 fundos) que a tela carrega
depois — números de diagnóstico (560/186/374) ficam sempre um pouco defasados dos números reais
da tela (~592/~401 válidos). Não corrigido, só constatado.

### 📌 Item de estudo separado (não é limpeza de base, é ranking)
**Score não reflete risco relativo dentro da mesma categoria de risco** — Victor observou que
um FII "middle risk" específico pode ser, na leitura dele, menos arriscado que outro da mesma
faixa mesmo com score menor. Precisa de exemplos concretos de tickers pra estudar o que hoje
diferencia o score deles e propor um critério de sub-ranking de risco intra-categoria.

## SHAs no fechamento desta sessão (10/07/2026)
- proxy.py: 59e516692fdfd10f3e8bda74e5d10eb9621984a1
- fontes.py: 9f84505c2640c57001e97c1a913c5b408d00e93c
- fontes_etfs.py: 256cf7da182e82aea6b982e544b12960a20614fe
- rotas_fiis.py: 42d1a29256743f61a8981eb4c76b36919b0f3a56
- rotas_etfs.py: ab401ebbf1b12f73e6d454ded2349b3011939136
- motor.py: 035fa085a6916080a0122d46a7c1c343a3390e35
- static/app.js: f22fe1cfab18374df9db01628e18d7039c3c5e76
- templates/index.html: 82b6d88df26e2464f974609435aa6e15e4ba74f8
- static/style.css: aedb6fcbe339ede195c6e6182fec5f5da4157fe7
- analises.json: 2f6bc7ec8163fb57ec70c657c751a89d045b7aa7
- positions.json: 3319dd4b563058c50d4893f9b7b724b3d9d53af9
- carteira_fiis.json: 7ae13a8040f95b99901a2564825abe0533353f99
- etfs_estado.json: 60a538afb0d90b5a2b34c9a363230b0d1cd32c1d
- fundamentos.json: e0dc2a4d0c3cb2bf04ebf258536e36ef2a319805
- ROTINA_GATES_LOTE.md: 52e40aadf69df474fcc28864d58eca1041bd1970

## Tokens/credenciais (NUNCA colocar valores reais neste arquivo nem em nenhum arquivo do repo)
- `GITHUB_TOKEN` / `GITHUB_WRITE_TOKEN` / `GITHUB_REPO`: configurados no Render, usados pelo app em
  produção para ler/escrever no próprio repositório. Não confundir com o token de sessão que o
  usuário cola no chat para o Claude usar via `api.github.com` (esse é temporário, só da sessão).
- `API_WRITE_TOKEN`: configurado no Render, protege rotas de escrita da API do app.
- `BRAPI_TOKEN`: **RESOLVIDO nesta sessão** — havia um token antigo hardcoded em `proxy.py` (linha
  ~168, como valor DEFAULT do `_os.environ.get`) que ninguém lembra de ter criado conscientemente,
  provavelmente inserido por uma sessão anterior do Claude sem aviso claro. Confirmado que bateu o
  limite mensal de 15.000 requisições (teste real retornou 429). Usuário criou um token PRÓPRIO no
  brapi.dev e configurou `BRAPI_TOKEN` como variável de ambiente no Render — o código já lê essa
  variável automaticamente antes de cair no valor antigo hardcoded, então não precisou mexer em
  nada no código, só configurar no Render. **Usuário tem 2 contas/tokens brapi** (2 perfis Google)
  — rotação entre eles fica em backlog (ver seção de ToS abaixo).
- **brapi.dev `/api/v2/funds/*` (FIAGRO/FI-Infra/FIDC/FIP)**: testado com token novo, retornou
  `403 FEATURE_NOT_AVAILABLE` — confirmado que exige plano PAGO, não resolve com token gratuito
  novo. Não usar esse endpoint sem o usuário decidir assinar um plano.
- **Consideração de ToS pendente**: usar múltiplos tokens/contas para multiplicar cota gratuita é
  possivelmente contra os termos de uso do brapi.dev (comum em APIs free-tier proibirem isso) —
  Claude avisou o usuário disso antes de qualquer implementação; ele optou por registrar em
  backlog e pensar com calma, não implementar rotação ainda.

## Resumo do que foi feito nesta sessão (visão executiva, ver seções detalhadas abaixo para o histórico completo)
1. Modernização de layout completa: sidebar com accordion, header fixo, cards unificados.
2. Volatilidade real (correlação) + cache diário para Carteira ETFs e Carteira FIIs.
3. Reorganização de ETFs (Mercado vs Minha Operação, espelhando padrão de FIIs).
4. Painel de aproveitamento em Encerradas ("quanto ficou na mesa"), com lote de 100 como base,
   cobrindo TRÊS fluxos: (a) posições realmente encerradas (sucesso/fracasso, preço capturado
   automaticamente), (b) rejeições do ranking (EV/score capturados no clique, sem precisar de
   cálculo manual), (c) processo manual em chat para o caso raro sem esses dados.
5. Fix crítico: filtro "fantasma" de liquidez em FIIs se desativa sozinho quando a fonte
   (Fundamentus) está com dado implausível (>15% de liquidez zerada) — protege contra remover
   fundos reais como o KNCA11 em massa por falha momentânea da fonte.
6. Fallback em cascata para BSLV39 (BDR sem cobertura boa em nenhuma API gratuita): Yahoo → brapi
   → proxy via ativo original (SLV) + câmbio USD/BRL, marcado como estimativa na UI.
7. Fix de bug real em `/montecarlo/condicional`: campos rotulados "daqui pra frente" na verdade
   simulavam desde a foto original, ignorando dias passados. Corrigido de forma ADITIVA (campos
   novos `_condicional`, sem alterar os antigos que o painel de aproveitamento já depende).
8. Rotina documentada de gates para análise de lote (`ROTINA_GATES_LOTE.md`) — liquidez e retorno
   mínimo (2-2,5%/mês) cortam automaticamente; probabilidade e assimetria sempre lado a lado,
   nunca viram filtro automático (julgamento do usuário).
9. `GET /fiis/diagnostico` — nova rota de diagnóstico, mostra o que foi descartado no último
   scrape de FIIs e por quê. Ferramenta permanente, não descartar.
10. Resolução do problema de fonte de dados do brapi.dev (ver seção de tokens acima).

## Lições de arquitetura registradas (não repetir)
- `ThreadPoolExecutor` com `shutdown(wait=False)` é PERIGOSO no Render (1 worker) — pode acumular
  threads órfãs e travar o processo INTEIRO, não só a rota que criou. Preferir sempre sequencial
  com timeout nativo do `requests`. Incidente real nesta sessão: site travou completamente após
  uma implementação com esse padrão; revertido e refeito sequencialmente.
- Nunca afirmar "confirmei X" sem ter executado a verificação de verdade — já aconteceu 2x nesta
  sessão (uma vez com dado fabricado ao inves de admitir busca vazia; outra com cálculo manual
  desatualizado quando o motor de produção já tinha o número certo). Sempre preferir o número que
  o app já calculou (ranking, condicional) a um cálculo manual improvisado.
- Investigação que parece "1 caso isolado" pode ser bug estrutural maior (caso KNCA11 revelou
  ~31% do universo de FIIs afetado, não só 1 ticker) — sempre checar a ESCALA antes de aceitar
  causa pontual.
- Boot real (test_client + mocks) pega bugs que `ast.parse` sozinho não pega — usado em TODOS os
  fixes desta sessão antes de commitar.

## Princípio do usuário sobre rejeitar casos de alta probabilidade tardia (10/07/2026, versão
## corrigida/precisa -- substitui a formulação inicial, registrar como heurística de julgamento,
## NÃO como regra de código/gate)

Usuário observou, ao ver a CMIN3 teste subir de 63,85% (desde o início) para 99,45% (hoje) em só 9
dias, que faz sentido rejeitar e buscar outras oportunidades. A formulação inicial dele ("99% na
largada nunca existe, seria fácil demais ganhar dinheiro") foi REFINADA para o motivo real:

**Em estruturas de retorno controlado, o ganho é sempre travado (prefixado fixo), não importa a
distância da barreira.** Quando a probabilidade sobe de 63% para 99% ao longo de dias passados sem
ativar, o que mudou foi só o RISCO (menor), não o GANHO (continua o mesmo teto fixo) -- e o PRAZO
RESTANTE encolheu. Isso significa que o retorno esperado por unidade de tempo restante (ex:
2,21%/32 dias) fica pior do que o de uma estrutura NOVA com prazo cheio (ex: ROXO34 no ranking
rendendo 5,90%/mês -- quase o triplo do ritmo). Não é sobre "99% ser suspeito" -- é sobre EFICIÊNCIA
DE CAPITAL/TEMPO: com capital limitado, ativar tarde uma estrutura que já "queimou" a maior parte do
prazo é pior uso de capital do que uma alternativa fresca com ritmo mensal melhor, mesmo que a
tardia tenha probabilidade de sucesso mais alta e EV positivo no momento. Baixo risco sem prêmio
proporcionalmente maior não compensa abrir mão de uma alternativa com ritmo melhor.



---



## Validação em produção do fix de /montecarlo/condicional (10/07/2026)
Usuário testou criando uma análise clone (mesma estrutura CMIN3, data/preço de hoje) e confirmou: o
campo novo `prob_ganho_prefixado_condicional` (painel de detalhe) e o `Prob.` do ranking agora
BATEM (~98-99% nos dois, diferença de décimos por ruído normal de Monte Carlo) -- antes divergiam
muito (64% vs 99%). Fluxo de rejeição com captura de EV também validado: rejeitou a análise teste,
apareceu em Encerradas com "EV mensal na rejeição: +2,21% · deixou ~R$11,32 na mesa" e entrou no
somatório automático corretamente.

**Esclarecimento conceitual confirmado com o usuário**: os dois números (ranking vs "desde o
início") usam a MESMA metodologia (barreira tocada em QUALQUER momento do caminho = knock-out
permanente, sem recuperação -- `min(caminho) <= kdo`). NÃO é "nunca tocar" vs "preço final
permite recuar" -- a única diferença é o PONTO DE REFERÊNCIA no tempo (foto original vs hoje).
Usuário tinha uma hipótese diferente (achava que eram duas metodologias distintas), corrigida.

## Investigação: ranking de probabilidade para Posições Ativas (positions.json)
Usuário perguntou se dá pra fazer o mesmo ranking (Prob./EV/Score) para as 7 posições ativas reais,
não só para "em análise". Investigação (SEM implementar, conforme pedido):
- **AXIA3-A, AXIA3-B (bidirecional) e BSLV39 (retorno_controlado)**: JÁ TÊM os campos que o motor
  do ranking usa (`kdo`, `kuo`/`teto_retorno_pct`/`alavancagem` ou `ganho_prefixado_pct`, `entry`,
  `data_entrada`, `vencimento`) -- reaproveitamento direto seria rápido (só adaptar "prazo restante"
  via `vencimento` real em vez de `prazo_dias` fixo).
- **PETR4, VALE3, BBAS3, ROXO34 (tipo_posicao=simples, venda coberta de call)**: o motor do ranking
  HOJE NÃO TEM fórmula de EV para covered call -- só cobre bidirecional e retorno_controlado.
  Precisaria de lógica NOVA (baseada em prêmio recebido + prob. de exercício via `/montecarlo/
  condicional` que já sabe calcular isso, mas o ranking em si nunca usa) -- não é reaproveitamento
  simples.
- BSLV39 também herda a limitação de dado já resolvida no gráfico (proxy SLV+câmbio) -- precisaria
  reaproveitar aquela lógica pro preço atual usado no ranking também.

**Decisão do usuário**: registrar no backlog, NÃO implementar agora.



## SHAs relevantes: proxy.py 59e516692fdfd10f3e8bda74e5d10eb9621984a1 | static/app.js f22fe1cfab18374df9db01628e18d7039c3c5e76

## Continuação 10/07/2026 — Duas features novas

**1. Rejeições agora capturam EV/score/prob no momento do clique** (não é o painel automático de sucesso/fracasso, é NOVO): o botão "🚫 Rejeitar" no ranking envia `ev_mensal_pct`/`score`/`prob_meta_pct`/`preco_atual` (cache das linhas do ranking, `window._rankingCache`) junto com a rejeição. Backend (`proxy.py`, rota `PUT /analises/<id>/status`) grava em `ev_mensal_na_rejeicao`/`score_na_rejeicao`/`prob_meta_na_rejeicao`/`preco_encerramento`. Painel de Encerradas (`calcularSomatorioEncerradas`) processa isso SEM chamada de rede (já tem o dado): EV positivo → "deixou na mesa"; EV negativo → "economizou, evitou EV negativo". Só vale para rejeições a partir de agora (as antigas, feitas manualmente por mim antes disso existir, não têm os campos).

**2. Bug real encontrado e corrigido em `/montecarlo/condicional`**: campos rotulados "(daqui pra frente)" -- `prob_ganho_prefixado` (retorno_controlado) e `prob_retorno_faixas`/`retorno_medio_pct` (bidirecional) -- na verdade simulavam desde a FOTO ORIGINAL (`preco_foto`, `prazo_dias` total), ignorando completamente os dias já passados e o preço atual. Usuário notou a discrepância entre o Ranking (que já calculava certo, usando `dias_restantes`/preço atual) e o painel de detalhe da foto (que dava um número bem diferente e mais conservador). Investigação confirmou: bug real de implementação, não duas métricas com propósitos diferentes.

**Fix ADITIVO (sem quebrar nada existente)**: os campos antigos (`prob_ganho_prefixado`, `prob_retorno_faixas`, `retorno_medio_pct`) foram MANTIDOS EXATAMENTE COMO ESTAVAM -- são a base do painel de aproveitamento em Encerradas (que compara "esperado desde a foto" vs "realizado desde a foto", ambos ancorados no mesmo preço/data de referência -- mudar isso quebraria aquele painel). Foram ADICIONADOS campos NOVOS e CORRETOS: `prob_ganho_prefixado_condicional`, `prob_sem_barreira_condicional`, `prob_barreira_baixa_condicional`, `prob_barreira_alta_condicional` -- estes sim usam `dias_restantes`/preço atual (`S`) de verdade. Frontend atualizado para mostrar o campo condicional em destaque (era o que devia ter aparecido desde o início) e o antigo como referência secundária, cinza, rotulado "desde o início".

**Nota técnica**: para estruturas BIDIRECIONAIS (kdo+kuo), já existia um bloco SEPARADO e CORRETO (`prob_sem_barreira`, sem o bug) que já usava dias_restantes/S -- o bug afetava só a quebra por faixas de retorno (`prob_retorno_faixas`) e o EV (`retorno_medio_pct`) desse tipo, não a probabilidade simples de não tocar a barreira. Para RETORNO CONTROLADO (kdo sozinho, ex: CMIN3), não existia nenhum bloco correto -- o único número exibido (`prob_ganho_prefixado`) era o buggy, por isso a confusão do usuário foi mais visível nesse caso.

**Testado com boot real (proxy.py completo, mocks de rede)** para os dois tipos de estrutura antes de commitar -- campos antigos inalterados, campos novos condizentes com o que o ranking já mostrava.



## Novos itens de backlog (09/07/2026, registrados apenas como estudo/direção, NAO implementar sem confirmação explícita)

**Resumo do painel de aproveitamento por período**: hoje o "Somatório de aproveitamento" em
Encerradas é só um total corrido, sem quebra por período (semana/mês). Usuário quer poder ver
isso agrupado por período. Considerar também: rejeições (`motivo_encerramento='rejeitada'`) hoje
NÃO entram nesse somatório automático (só ficam como texto manual na observação) -- e itens
rejeitados somem da lista visível após ~30 dias (embora continuem contados num contador
permanente separado). Se decidir incluir rejeições no somatório, pensar em como isso se comporta
quando o item some da lista visível (persistir o valor calculado em algum lugar antes de sumir?).

**Estudo de detecção de "lixo" no universo de FIIs (confirmado 09/07/2026: KNCA11 100% resolvido,
passa nos dois gates, campos populados corretamente)**: usuário perguntou se há risco de fundo
morto/lixo migrar do "bruto" (592 hoje) para o grupo que passa no Critério (403 hoje). Avaliação:
migração é IMPROVÁVEL pelo desenho atual (exigiria fingir liquidez E DY reais ao mesmo tempo) --
caso já conhecido e tratado manualmente é o CBCV11 (`_FII_TICKERS_INATIVOS` em `fontes.py`), fundo
com dado cacheado antigo que passava nos dois filtros por coincidência. Mais provável é lixo
aparecer só no bruto (Todos), corretamente cortado do Critério -- comportamento esperado, não bug.

Sugestões de detecção mais robusta levantadas para avaliação futura (nenhuma implementada):
1. Consistência temporal -- comparar liquidez de hoje com scrapes anteriores (já há cache diário);
   fundo com liquidez zerada há semanas que "pisca" positivo um dia só é suspeito mesmo passando
   no filtro pontual.
2. Palavra-chave no `nome_fundo` ("em liquidação", "encerramento").
3. Cruzar com lista oficial da B3 de fundos ativos (fonte de verdade externa, mais robusto porém
   mais trabalho de manter).
4. Detectar `valor_mercado` congelado (sem mudança) em múltiplos scrapes consecutivos como sinal
   de dado cacheado parado no Fundamentus.

Usuário foi explícito: "é só uma análise inicial, um estudo, pra ver se tem algo que dá pra
melhorar" -- avaliar com calma antes de implementar, sistema já está funcionando bem como está.



## Continuação 09/07/2026 — Processo manual para "quanto ficou na mesa" em REJEIÇÕES (não encerradas)

**Contexto**: o painel automático de aproveitamento (Encerradas) só cobre itens com `status=encerrada`
+ `resultado` preenchido (fluxo de Posições Ativas de verdade). Quando o usuário REJEITA um
candidato do ranking (`motivo_encerramento='rejeitada'`, sem `resultado`) porque já bateu ~100% de
probabilidade e ele decidiu não entrar, **não existe botão nem cálculo automático** -- mesmo
padrão de limitação já documentado para Posições Ativas.

**Processo estabelecido (mesmo espírito do combinado para Posições Ativas)**: usuário avisa quais
foram rejeitadas recentemente (ou Claude consulta `analises.json` filtrando por
`motivo_encerramento='rejeitada'` + `data_rejeicao` do dia). Para cada uma:
1. Busca preço atual via web_search (Claude não acessa Yahoo/Render direto do sandbox).
2. Roda simulação Monte Carlo PRÓPRIA (numpy disponível no sandbox) usando o `sigma_pct` REAL já
   gravado em `bandas_congeladas` daquela análise específica (não uma estimativa nova) -- GBM,
   passos diários, probabilidade de NÃO tocar a barreira (kdo/kuo) entre a data de referência
   (hoje) e o vencimento original.
3. Valor esperado = probabilidade × ganho_prefixado_pct (ou payoff equivalente do tipo de
   estrutura) × preco_foto × **lote de 100** (mesma base padrão já usada no painel automático).
4. Grava a observação calculada diretamente na análise via GitHub API (campo `observacao`,
   concatenado ao que já existia, nunca sobrescrevendo).
5. **Limitação sempre exposta**: o cálculo usa o preço do MOMENTO DA REJEIÇÃO como referência, não
   o caminho diário completo desde a foto -- não há garantia de que a barreira não foi tocada em
   algum ponto intermediário entre a foto e a rejeição.

**Exemplo real desta sessão**: PETR4 (retorno controlado, kdo=33.865, rejeitada com preço ~R$38.44,
13.5% de folga da barreira) e CMIN3 (kdo=3.8372, rejeitada a ~R$4.55, 18.6% de folga) -- ambas
com probabilidade simulada de ~100% de não tocar a barreira nos 7 dias restantes de 15, dado a
distância grande e a volatilidade real (25.42% e 33.22% respectivamente). Valor esperado
calculado: R$43.53 (PETR4) + R$7.94 (CMIN3) = R$51.47 total, lote de 100 cada. Gravado em
`analises.json` (SHA 3a2e703dd7b5275a28f1cdfb76e2f801a8c4be68).



## SHA relevante: rotas_fiis.py 412c5cd9a19189bf53e332f1375a7c7ed3511f28

## INCIDENTE 07/07/2026 -- site travou completamente (registrar como aprendizado de arquitetura)

Apos o primeiro fix do KNCA11 (enriquecimento via StatusInvest), o usuario reportou o SITE INTEIRO
travado (nao so /fiis lento -- nada carregava). Causa suspeita: a implementacao usava
`ThreadPoolExecutor` com `ex.shutdown(wait=False)` -- as threads de rede que nao terminavam
dentro do orcamento continuavam rodando em SEGUNDO PLANO mesmo apos o shutdown, e como o Render
roda com 1 worker so, threads acumulando a cada clique em "Atualizar" podem ter degradado o
processo inteiro (contencao de GIL/recursos), nao so a rota que as criou.

**Acao tomada**: revert IMEDIATO e completo do bloco de threads assim que o usuario reportou o
travamento -- prioridade foi estabilizar antes de qualquer outra coisa, mesmo que isso significasse
perder o enriquecimento (KNCA11 voltou a ficar "sem dado" por um tempo). So depois de confirmar
estabilidade, reimplementado de forma SEQUENCIAL (sem nenhuma thread nova): cada chamada de rede
usa o timeout NATIVO do `requests.get()` (aborta de verdade, nao deixa nada rodando depois), loop
para sozinho se o orcamento total (8s) estourar. Testado simulando rede sempre lenta (3s/chamada)
-- total ficou em 9.3s, bem dentro do timeout do front (30s).

**Licao de arquitetura para o projeto (Render free tier, 1 worker)**: `ThreadPoolExecutor` com
`shutdown(wait=False)` e um padrao PERIGOSO nesse ambiente -- ja era usado em outros lugares do
codigo (Carteira ETFs, Carteira FIIs) SEM ter causado esse problema ainda, mas o risco existe
sempre que threads podem ficar rodando alem do timeout monitorado. Se aparecer mais algum
travamento parecido no futuro, suspeitar PRIMEIRO desse padrao antes de investigar outra coisa.
Nao foi possivel confirmar 100% que foi essa a causa exata (nao ha acesso a logs do Render), mas
a correlacao temporal (travou logo apos esse deploy especifico) e o padrao de risco conhecido
tornam essa a hipotese mais provavel.

## Continuação 07/07/2026 (parte 3) — bug de frontend descoberto na mesma cadeia

Apos o fix do backend (fallback + bypass de gates), o frontend quebrou com "Cannot read properties
of null (reading 'toFixed')" -- a tabela de Criterio nunca esperava receber `dy_pct`/`liquidez`/
`p_vp`/`score` como `null` (antes do fallback, esses campos SEMPRE vinham preenchidos para
qualquer item que chegasse no Criterio). Fix: `app.js` (SHA 64d0f3199b5538b250e7ac6844dfa9287a306d34)
adiciona guardas `!=null?...:'—'` nessas 4 celulas da linha da tabela (as unicas que ainda usavam
`.toFixed()` direto sem protecao -- as outras ocorrencias no arquivo ja tinham essa protecao).



## SHA relevante: rotas_fiis.py 6743f818d35bafbb3fba54d61c5d6407d8053386

## Continuação 07/07/2026 (parte 2) — Cadeia completa de fixes do caso KNCA11

**IMPORTANTE -- correcao de um erro proprio nesta sessao**: em um momento da investigacao, Claude
afirmou ter "confirmado 30% de liquidez zerada buscando a pagina real do Fundamentus" quando na
verdade a busca daquele momento nao trouxe conteudo -- os numeros foram fabricados para ilustrar
o raciocinio sem deixar claro que nao eram reais. Usuario pegou o erro. Depois disso, o numero real
(31,4%) veio do proprio diagnostico em producao (`/fiis/diagnostico`), reportado pelo usuario via
console -- esse sim e real e foi a base de todos os fixes desta secao. **Licao**: nunca afirmar
"confirmei X" sem ter de fato executado a verificacao -- se a ferramenta nao trouxe resultado,
dizer isso explicitamente em vez de preencher com exemplo plausivel.

**Cadeia de causas (cada uma so apareceu depois de corrigir a anterior)**:
1. Filtro fantasma (liquidez=0 -> remove) derrubava ~31% do universo por falha real da fonte
   (Fundamentus) -- FIX: sanity check desliga o filtro sozinho se fracao > 15% (`fontes.py`,
   SHA 9f84505c2640c57001e97c1a913c5b408d00e93c, sessao anterior).
2. Depois desse fix, universo bruto voltou a ~582-592 (numero que o usuario confirma ser o
   "correto" de antes), mas o KNCA11 ainda ficava FORA DO CRITERIO (rota `/fiis`, filtro
   separado de liquidez_min=50000 -- diferente do filtro fantasma do scrape) -- FIX: mesmo
   sinal de fonte suspeita agora tambem libera esse segundo filtro via fallback de VALOR DE
   MERCADO (fundo grande = confia mesmo sem liquidez confiavel).
3. Depois desse fix, KNCA11 aparecia no Criterio mas com dy_pct=0 (dado tambem contaminado,
   nao so liquidez) -- FIX: gate de DY tambem bypassed quando aceito via fallback, e dy_pct=0
   suspeito e corrigido para None (nao fica um zero falso enganando o score/exibicao).
4. Esse fix causou 2 bugs novos pegos ANTES de subir (nao depois): calculo de mediana de DY por
   segmento quebrava com None misturado; sort da lista de candidatos vulneravel a score=None
   (mesmo que na pratica _score_fii ja retornasse 0.0 nesse caso, nao None -- corrigido por
   seguranca mesmo assim).
5. **Fix final**: usuario notou que a Carteira FIIs (fonte StatusInvest individual, usada em
   outro lugar do app) MOSTRA o KNCA11 com todos os campos corretos -- ou seja, a fonte
   individual funciona bem, so a fonte EM MASSA (Fundamentus) que esta com problema hoje.
   Em vez de so aceitar "sem dado" via fallback, `/fiis` agora ENRIQUECE com dado real: para
   os tickers aceitos via fallback de valor de mercado, busca em paralelo (ThreadPoolExecutor,
   orcamento 10s) via `scrape_statusinvest_fundo_dados` (mesma funcao ja usada e validada em
   Carteira FIIs), tentando `fundos-imobiliarios` depois `fiagros`. Se tambem falhar, degrada
   graciosamente para "sem dado" (nao quebra).

**Todos os fixes testados com boot real (nao so ast.parse) antes de cada commit**, incluindo
cenarios de sucesso, falha parcial, e ausencia total de dado -- ver commits de rotas_fiis.py
desta sessao para os testes especificos usados.

**Ferramenta criada nesta investigacao**: `GET /fiis/diagnostico` -- lista todo ticker
descartado no ultimo scrape com o motivo exato, mais `fracao_liquidez_zerada_pct` e
`filtro_fantasma_desativado_fonte_suspeita`. Consultavel via console do navegador. Deve
continuar existindo -- foi essencial para diagnosticar esta cadeia inteira remotamente.



## SHA relevante: fontes.py 9f84505c2640c57001e97c1a913c5b408d00e93c

## Continuação 07/07/2026 — Fix crítico: filtro "fantasma" de liquidez derrubando ~30% do universo de FIIs

**Sintoma**: usuário reportou KNCA11 (maior Fiagro do mercado, liquidez real excelente) sumindo
do universo de FIIs em Mercado. A princípio pareceu ser um caso isolado do KNCA11.

**Diagnóstico real (via `/fiis/diagnostico`, rota nova, + pesquisa direta na página real do
Fundamentus)**: NÃO era o KNCA11 isoladamente -- confirmado contando manualmente que **~30% de
TODOS os FIIs** (incluindo fundos gigantes conhecidos: BBPO11 com R$1,5bi/61 imóveis, BCFF11,
AEFI11, etc.) estavam com liquidez="0" LITERAL na própria página do Fundamentus naquele momento.
Isso é uma falha da FONTE DE DADOS (Fundamentus, causa exata desconhecida -- possível problema no
feed deles), não fundos mortos de verdade (que normalmente são <2% do universo).

**Causa raiz do bug (existia desde 01/07/2026, antes desta sessão)**: o filtro "fantasma"
(`liquidez==0 -> remove como fundo morto`) não tinha proteção contra esse cenário -- confiava
cegamente na fonte e removia em massa fundos reais e líquidos sempre que a fonte tivesse esse
tipo de falha.

**Fix**: sanity check antes de aplicar o filtro -- calcula `frac_liq0` (fração do universo com
liquidez zerada). Se > 15% (implausível para fundos mortos de verdade), o filtro se DESATIVA
sozinho para aquele run inteiro (mantém todos os FIIs), em vez de arriscar remover fundos reais
em massa. Exposto no diagnóstico: `fracao_liquidez_zerada_pct` e
`filtro_fantasma_desativado_fonte_suspeita`. Testado com 2 cenários (fração baixa = filtra
normal; fração alta = desliga sozinho) -- ambos passaram.

**Ferramenta nova que ajudou a achar isso**: `GET /fiis/diagnostico` (rota criada na mesma
investigação) -- lista todo ticker descartado no último scrape e o motivo exato. Consultável via
console do navegador: `fetch('/fiis/diagnostico').then(r=>r.json()).then(d=>console.log(JSON.stringify(d,null,2)))`.
Só mostra dado de um scrape que já rodou nesta instância (reseta a cada restart/deploy do Render).

**Lição de processo**: uma investigação que começou parecendo "1 ticker com problema" (KNCA11)
era na verdade um bug estrutural afetando ~1/3 do universo -- vale sempre checar a ESCALA do
problema (quantos tickers, não só o que o usuário citou) antes de assumir causa pontual.



## SHAs relevantes desta sessão (06/07/2026)
- proxy.py: 754b9a78e601e2c4fb1049602ff41332914ab8b9 (fallback nivel 3 BSLV39: proxy SLV+cambio)
- static/app.js: adaedf1f4598093bc91e2bdc069f97185ec60d99 (aviso visivel de dado estimado no grafico)
- ROTINA_GATES_LOTE.md: 52e40aadf69df474fcc28864d58eca1041bd1970

## Continuação 06/07/2026 — Fix BSLV39 (histórico "achatado" no gráfico de evolução)

**Sintoma**: usuário reportou que "Ver evolução desde a entrada" pro BSLV39 mostrava uma linha
praticamente reta/plana, como se fosse 1 dia único, apesar de já estarem 13 dias desde a entrada.

**Diagnóstico real (não era bug de lógica de datas)**: `/montecarlo/posicao_ativa` dependia só do
Yahoo Finance. Confirmado via pesquisa que nem Yahoo nem brapi.dev têm cobertura de histórico
diário boa para o BSLV39 especificamente (BDR de ETF estrangeiro de metal -- prata) -- o próprio
brapi.dev mostra "R$0,00" publicamente pra esse ticker. Não é sobre liquidez real do ativo (que é
boa, negocia diariamente na B3) -- é sobre cobertura de dado das APIs gratuitas para esse tipo
específico de BDR.

**Fix em 3 camadas** (cada uma só dispara se a anterior não resolveu):
1. Yahoo (já existia).
2. brapi.dev como fallback quando Yahoo é esparso (mesmo padrão já usado em `/montecarlo/condicional`).
3. **NOVO**: quando NEM Yahoo NEM brapi resolvem, para tickers mapeados em `_BDR_PROXY_ORIGINAL`
   (hoje só `'BSLV39.SA': 'SLV'`), reconstrói a trajetória via o ativo ORIGINAL (SLV na NYSE, que
   tem histórico perfeito) + câmbio USD/BRL (Yahoo tem histórico perfeito de `USDBRL=X` também):
   `preco_estimado(dia) = preco_entrada * (SLV[dia]/SLV[entrada]) * (cambio[dia]/cambio[entrada])`.
   Marcado explicitamente como `precos_reais_estimados: true` na resposta -- front mostra aviso
   visível no card. Usuário confirmou no ar: "deu certo, buscou histórico, está certinho".
   **Extensível**: se aparecer outro BDR de ETF estrangeiro com o mesmo problema (ex: BIAU39/ouro),
   só adicionar ao dict `_BDR_PROXY_ORIGINAL` em `proxy.py` (dentro de `run_montecarlo_posicao_ativa`).

**Ordem de execução importante (bug corrigido durante o desenvolvimento, não repetir)**: o cálculo
de `preco_entrada`/`idx_entrada` (extraído do histórico real no dia da entrada) precisa acontecer
**ANTES** do fallback nível 3 (proxy SLV+câmbio) usar `preco_entrada` como âncora -- na primeira
tentativa de implementação isso ficou na ordem errada (`UnboundLocalError`), só descoberto porque
o teste automatizado rodou de verdade (boot real + mock) em vez de só `ast.parse()`.

## Rotina de gates (validada em conversa 06/07/2026, ver `ROTINA_GATES_LOTE.md` para o texto completo)
Usuário confirmou o desenho: liquidez e retorno mínimo (2-2,5%/mês) são gates automáticos (cortam
o candidato); probabilidade e assimetria são sempre mostradas lado a lado, nunca viram filtro
automático (é julgamento do usuário). **Limitação prática exposta e aceita pelo usuário**:
probabilidade com precisão de motor real só é possível se o usuário rodar no site e colar o
resultado aqui -- Claude não acessa o Render/Yahoo direto do sandbox. Quando o usuário não tiver
isso em mãos, Claude pode estimar com busca na web + Monte Carlo próprio (numpy disponível), mas
avisando que é aproximação.



## Stack
- Flask no Render (free tier): https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk (branch: main)
- Token GitHub de SESSÃO (Claude usa em chat, colado pelo usuário): classic, escopo `repo`, válido 90 dias a partir de 02/07/2026
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho): fine-grained, restrito SÓ ao repo trader-desk, permissão "Contents: Read and write", configurado como `GITHUB_TOKEN` no Render. **PENDÊNCIA AINDA ABERTA (item #1 do backlog): criar token fine-grained sem vencimento curto para substituir o atual (processo: GitHub → Settings → Developer Settings → Fine-grained tokens → só trader-desk → Contents R/W)**
- Deploy: GET SHA → PUT base64 via API do GitHub. HTML em templates/, JS em static/app.js
- Console de debug: Eruda ativo no index.html para validação mobile — usuário confirmou fluxo de POST manual via `fetch()` + `localStorage.getItem('api_write_token')` como `Authorization: Bearer <token>`, funciona bem para registrar análises de teste/lote sem passar pelo formulário do app
- **REGRA CRÍTICA DE PROCESSO**: usar `api.github.com/repos/.../contents/...` para ler arquivos que foram editados NA MESMA sessão — nunca `raw.githubusercontent.com` para isso (CDN cache causa leituras desatualizadas e pode reverter mudanças ao re-editar)
- **LIMITAÇÃO DE AMBIENTE CONFIRMADA (02/07/2026)**: o sandbox de execução do Claude (bash_tool) só acessa domínios de pacotes (github.com, api.github.com, pypi.org, npmjs.com etc) — NÃO acessa `trader-desk.onrender.com` nem `finance.yahoo.com`. Isso significa que Claude NÃO consegue chamar `POST /analises` (ou qualquer rota Flask) diretamente, nem buscar preço/histórico via Yahoo no sandbox. Duas consequências práticas: (1) quando Claude precisa registrar uma análise nova a partir de um lote decidido em chat, o caminho é ESCREVER DIRETO no `analises.json`/`positions.json` via GitHub Contents API (contorna o Flask) — mas isso PULA o congelamento automático de bandas (backlog #4), que só roda dentro da rota Flask; (2) para testar de verdade o congelamento de bandas, o USUÁRIO precisa rodar o `fetch()` manual pelo Eruda, não Claude. Se no futuro o domínio do Render for liberado no sandbox, isso deixa de ser necessário.

## SHAs no fechamento REAL desta sessão (05/07/2026, todos validados no ar pelo usuario)
- proxy.py: 4f37b90ee37e8385e234c80d41ccfa37b8c39f2c (captura preco_encerramento + /montecarlo/condicional aceita override retroativo)
- static/app.js: bb84611393a21285933af603ccec82e496968aa9 (painel de aproveitamento em Encerradas, lote de 100)
- rotas_fiis.py: aba19f80ed2f52e0a37203742ad4c79a3f47ae79 (novo endpoint /carteira-fiis/resumo + cache diario)
- rotas_etfs.py: ab401ebbf1b12f73e6d454ded2349b3011939136 (cache diario em /etfs/carteira/resumo)
- templates/index.html: 82b6d88df26e2464f974609435aa6e15e4ba74f8 (sidebar com accordion + reorg de ETFs)
- static/style.css: aedb6fcbe339ede195c6e6182fec5f5da4157fe7 (sidebar/app-shell + unificacao de radius)
- fontes.py: ca3a07053ccdc794dff5fed9a5eeb455597dd4c3 (inalterado desde 04/07)
- fontes_etfs.py: 256cf7da182e82aea6b982e544b12960a20614fe (inalterado desde 04/07)
- motor.py: 035fa085a6916080a0122d46a7c1c343a3390e35 (inalterado)
- fundamentos.json: e0dc2a4d0c3cb2bf04ebf258536e36ef2a319805 (inalterado)
- etfs_estado.json: 3972f87b0de75a9b35f4821a206595246b4012f0 (inalterado)
- positions.json: 3319dd4b563058c50d4893f9b7b724b3d9d53af9 (inalterado -- 7 ativas, 4 encerradas SEM preco_encerramento/data_encerramento, ver processo novo abaixo)
- analises.json: 5e638624371ec107611b90d63ca052452e1e66e6 (inalterado)
- carteira_fiis.json: 7ae13a8040f95b99901a2564825abe0533353f99 (inalterado, so lido)

## Continuação 05/07/2026 (parte 2) — Painel "quanto ficou na mesa" em Encerradas + processo de fechamento de Posições Ativas

**Contexto/motivação**: usuário quer, ao encerrar uma análise/posição, saber retrospectivamente
qual era a probabilidade de sucesso NO MOMENTO do fechamento (não só hoje), e "quanto dinheiro
ficou na mesa" comparado ao que a simulação esperava -- útil para avaliar se o motor de decisão
está sendo assertivo, não para controle financeiro exato (isso as corretoras já dão).

**Backend (`proxy.py`):**
- `PUT /analises/<id>/status`: quando `resultado` é enviado (sucesso/fracasso), agora captura
  `preco_encerramento` via `_fetch_preco_yahoo` (best-effort, não trava o encerramento se falhar)
  além do `data_encerramento` que já existia.
- `/montecarlo/condicional`: ganhou parâmetros OPCIONAIS `data_referencia` e `preco_referencia`.
  Quando enviados, ancora o cálculo NAQUELE ponto no tempo (não em "agora") -- permite calcular
  "qual era a probabilidade quando encerrei" em vez de sempre "qual é a probabilidade hoje".
  Comportamento ORIGINAL (sem esses parâmetros) preservado 100% -- testado com boot real do
  proxy.py (test_client, mocks de rede/GitHub), não só ast.parse.
  **LIMITAÇÃO ASSUMIDA E EXPOSTA na resposta** (`nota_limitacao`): a volatilidade usada continua
  sendo a ATUAL (buscada ao vivo), não a de época -- Yahoo não dá uma forma simples de reconstruir
  vol histórica "como era vista" numa data passada sem dados pagos. `retorno_medio_pct` (usado no
  painel) vem do bloco de simulação que já existia (projeta do `preco_foto` original pelo
  `prazo_dias` TOTAL, não depende de fato do override -- é o valor esperado teórico da estrutura
  completa, ponto de comparação, não uma projeção "condicional" de verdade).

**Frontend (`app.js`):** painel novo na aba Encerradas (`calcularSomatorioEncerradas`), roda
automaticamente ao carregar a aba, para toda análise com `status=='encerrada' && resultado &&
preco_encerramento`:
- Por item: "Esperado (teórico) X% · Realizado (preço) Y% · diferença em R$ (lote de 100)".
- Agregado no topo: soma de todas as diferenças, em R$ (lote de 100 ativos, seja ETF/ação/FII --
  padronizado para comparabilidade) + em pp.
- Chamadas SEQUENCIAIS com atraso de 400ms entre elas (não paralelas) -- mesmo cuidado de
  concorrência do Render (1 worker) já documentado no backlog.
- **"Realizado" é retorno BRUTO de preço** (`preco_encerramento/preco_foto - 1`), NÃO o payoff
  exato da estrutura (kdo/kuo/alavancagem/teto) -- replicar o payoff exato no front duplicaria
  lógica do backend. Indicador direcional ("ficou dinheiro na mesa ou não"), não valor exato.
  Documentado na própria UI, não escondido.
- **Só funciona para encerramentos A PARTIR DE 05/07/2026** -- análises já encerradas antes não
  têm `preco_encerramento` salvo (painel avisa quando não há dado suficiente).

**PROCESSO NOVO ESTABELECIDO (Posições Ativas, `positions.json`) -- decisão explícita do usuário
05/07/2026:** `positions.json` **NÃO TEM e NÃO VAI GANHAR** endpoint/botão de fechamento automático
por enquanto -- usuário prefere fechar SEMPRE em conversa com o Claude, dando contexto (se bateu
a meta, se saiu antes mas dentro da proporção esperada, e sua PRÓPRIA interpretação de
sucesso/fracasso, que pode divergir do número puro -- ex: "só rolei, não perdi dinheiro, mas
considero fracasso"). Rotina esperada quando o usuário pedir para encerrar uma posição real:
1. Claude busca o preço atual do ativo (web_search/web_fetch, já que o sandbox NÃO acessa Yahoo
   nem o Render diretamente -- ver limitação de ambiente já documentada).
2. Claude calcula esperado-vs-realizado usando a MESMA lógica do painel (lote de 100 ativos).
3. Usuário informa o resultado final (sucesso/fracasso, na sua própria leitura -- não
   necessariamente a leitura pelo numero puro).
4. Claude grava tudo direto no `positions.json` (moving pra lista `encerradas`, com
   `preco_encerramento`, `data_encerramento`, `resultado`, `observacao`) via GitHub Contents API.
NÃO construir endpoint/UI para isso sem o usuário pedir explicitamente essa mudança de rotina.

**Backlog ETFs/FIIs (adiado, prioridade baixa) -- critério explícito do usuário:** este é um
sistema de TOMADA DE DECISÃO, não de controle de carteira -- o valor financeiro exato corretoras/
bancos já fornecem. Para ETFs/FIIs, o interesse é só se o motor está sendo ASSERTIVO na decisão
(a análise recomendou certo?), não o dinheiro ganho/perdido. Quando for revisitar, manter esse
escopo mais simples -- não replicar o painel de R$/lote de 100 para ETFs/FIIs sem necessidade
clara, considerar algo mais leve (ex: só confirmar se a decisão bateu com o esperado, sem
valor monetário).



## Continuação 05/07/2026 — Modernização de layout (4 fases) + volatilidade Carteira FIIs + cache diário + reorg ETFs

**Modernização de layout (aprovada por mockups no Visualizer antes de cada fase, nenhuma feita "no escuro"):**
- **Fase 1** (nav 2 níveis, depois SUBSTITUÍDA pela fase 4): agrupou as 10 abas em 3 famílias (Mercado/Minha Operação/Agenda) via `swFam()`.
- **Fase 2** (header fixo): sticky, com ticker IBOV/USD/SELIC espelhando (via `syncHeaderTicker()`, poll a cada 1.5s) os valores já calculados na aba Cotações — zero duplicação de fetch.
- **Fase 3** (unificação visual): border-radius consistente (10px) em todos os cards principais (`.card`,`.pc`,`.pos-acc`,`.ind-acc`,`.tbl-wrap`,`.sig`,`.ib`,`.scc`,`.pos-enc`) + nav centralizado (mobile e depois desktop também).
- **Fase 4** (sidebar com accordion — SUBSTITUIU as fases 1-3 de nav horizontal): usuário pediu referências visuais reais (buscou imagens, aprovou por mockup), apontou 2 fotos de dashboards ("Metric Flow" e "Hector") como referência de estilo. Sidebar fixa à esquerda, só a família ativa expandida (accordion), item ativo = retângulo sólido colorido (não mais borda lateral fina). `swFam()` reescrito para controlar `.sidebar-fam-body` (display block/none) em vez de nav horizontal. No mobile, sidebar empilha em cima do conteúdo (`.app-shell{flex-direction:column}`).
- **Pendência de estética explicitamente aceita pelo usuário**: layout "ainda feio mas funcional" — usuário quer ver mais exemplos antes de pedir refinamento visual adicional (cores/textura/tipografia). Não é bug, é gosto pessoal ainda não resolvido — não tratar como bug se voltar ao assunto.

**Volatilidade real da Carteira FIIs (novo endpoint, espelhando o de ETFs):**
- `GET /carteira-fiis/resumo` em `rotas_fiis.py`: mesma lógica de `/etfs/carteira/resumo` (matriz de covariância dos retornos históricos, correlação REAL entre os FIIs, não soma simples das vols individuais). Peso de cada FII = valor da posição (preço atual via última cota do histórico Yahoo, fallback pro preço de ativação) — mesma limitação assumida de ETFs (sem campo de quantidade real).
- Busca os históricos de TODOS os FIIs ativos em PARALELO (`ThreadPoolExecutor`, orçamento 15s) — 12 FIIs ativos (mais que o caso de ETFs), sequencial estouraria o tempo do Render.
- Testado com harness real (mock de rede + GitHub): dados normais, falha parcial de rede (1 ticker falha, rota não quebra), carteira vazia — todos passaram.
- Frontend: card `#carteirafiis-resumo` em `loadCarteiraFiisResumo()` (app.js), acima da tabela da Carteira FIIs, mesmo visual do card de ETFs.

**Cache diário (pedido do usuário 05/07/2026 — cálculo de correlação é pesado, não precisa rodar a cada clique):**
- Ambos `/etfs/carteira/resumo` e `/carteira-fiis/resumo` agora cacheiam em memória (module-level dict), chave = `data_de_hoje + tickers_ativos_ordenados`. Se o usuário ativar/encerrar um ativo no meio do dia, a chave muda e o cache invalida sozinho. Resposta cacheada volta com `'cache': true` pro front (não usado visualmente ainda, disponível se quiser indicar na UI).
- Testado: 1ª chamada busca de rede de verdade, 2ª chamada (mesmo dia, mesma composição) não rebusca nada, mesmo resultado.

**Reorganização de ETFs (Mercado vs Minha Operação, mesmo padrão que FIIs):**
- Watchlist de ETFs ficou sozinha em Mercado > ETFs (removida a barra de sub-abas, já que só sobrou 1 seção).
- "Em Análise" e "Carteira" de ETFs viraram aba própria — **"📦 Carteira ETFs"** — dentro de Minha Operação, com sub-abas internas (`etfSubTab()`, inalterado). Nova aba precisa aguardar `loadETFs()` terminar antes de renderizar (flag `window._etfDataPronto`, usada porque `_etfData` começa como array vazio `[]`, que é truthy em JS — checar só `!_etfData` não detectava "ainda não carregado").
- **BACKLOG NOVO, registrado pelo próprio usuário nesta sessão**: o "Em Análise" de ETFs deveria estar dentro da aba única e já existente `#tab-emanalise` (a mesma que tem "Estruturas em Análise" + ranking de FIIs logo abaixo), não dentro de "Carteira ETFs". Ou seja, `#tab-emanalise` deveria virar o lugar único para TODO "em análise" (estruturas, FIIs, ETFs), e "Carteira ETFs" deveria conter só a carteira de fato (como Carteira FIIs). Usuário classificou como "mais estético do que prático", não urgente — mas fica registrado pra próxima rodada de ajuste de layout.
- Confirmado com o usuário: o fluxo de ativação (`moverEtf()`, botões "+ Em Análise"/"OK → Carteira") não foi afetado pela reorganização — só mudou em qual aba os containers (`etf-analise-tbody`, `etf-carteira-lista`) aparecem, os IDs continuam os mesmos.

**Itens do backlog antigo confirmados como já entregues nesta sessão (não precisam de ação):**
- Item "convergência Graham → Média dos 4 métodos": já estava implementado (card de resumo já mostra "Méd. 4 Métodos" como destaque principal). Confirmado.
- Item "fan chart para Posições Ativas" (retroativo + projeção): já implementado (`data_entrada` real, botão "Ver evolução desde a entrada" em todos os templates de posição). Confirmado.
- Item "Monte Carlo Condicional em Em Análise": já implementado (`/montecarlo/condicional`, botão "Ver probabilidade atualizada"). Confirmado.
- Item "código da opção junto ao ticker em Posições Ativas": **CANCELADO** pelo usuário — não se aplica a operações estruturadas (bidirecional/retorno controlado), que não têm um único código de opção (são combinações de pernas com quantidades). Só faz sentido pra operações simples, que já mostravam certo.



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

## Continuação 04/07/2026 (tarde) — Modularização completa (Fases 3, 4 e 5)

`proxy.py` caiu de **6.606 → 4.323 linhas (-35%)** nesta sessão. As 5 fases do
plano de modularização (aprovado em 03/07) estão TODAS concluídas e validadas
no ar pelo usuário:
- **Fase 1** (`motor.py`) e **Fase 2** (`fontes_etfs.py`): já fechadas em sessão anterior.
- **Fase 3** (`fontes.py`, novo): CDI (Bacen), BTC onchain, Yahoo fundamentals/quotes,
  minério de ferro, 8marketcap (helpers), e todo o cluster de FIIs — constantes de
  segmento/classificação, `scrape_fiis_fundamentus` (Fundamentus), `scrape_fi_infra`,
  `scrape_fi_infra_dados`, os 4 scrapers do StatusInvest. Tudo puro (sem Flask/estado).
- **Fase 4** (`rotas_fiis.py`, novo): as 10 rotas de FIIs (`/fiis`, `/fiis/buscar`,
  `/fii-infra`, `/carteira-fiis` GET/POST/PUT, `/fii-ultimo-provento`,
  `/carteira-fiis/proventos`, `/fiis/universo-complementar`, `/analises/ranking-fiis`,
  `/debug-statusinvest*`). Padrão novo: `registrar_rotas(app, ...)` — rotas não podem
  fazer import direto de `proxy.py` (circular), então `proxy.py` cria o `app` e as
  dependências (`_github_get_file`, `_github_put_file`, `_hoje_str`,
  `_requer_auth_escrita`) e CHAMA a função de registro depois de defini-las.
- **Fase 5** (`rotas_etfs.py`, novo): as 6 rotas de ETFs (`/etfs`, `/etfs/live-status`,
  `/etfs/estado`, `/etfs/mover`, `/etfs/carteira/<ticker>/projecao`,
  `/etfs/carteira/resumo`). Mesmo padrão `registrar_rotas(app, ...)`, incluindo
  `_cache_etfs_live`, `_dy_refresh_em_andamento`, `_fetch_closes_for_foto` e
  `_obter_preco_sigma_garch` como dependências passadas (essas ficam em `proxy.py`
  de propósito — dependem de estado compartilhado/ciclo de background, não são
  rota nem fonte pura).

`proxy.py` agora é essencialmente: app Flask + rotas core (posições/análises/
Monte Carlo de Papéis) + as chamadas `registrar_rotas(...)` dos módulos.

### Bugs reais pegos DEPOIS do commit (rede real, não sandbox) — corrigidos
1. **`rotas_fiis.py` (Fase 4)**: faltava `import json` (NameError real em
   `/carteira-fiis`), e faltavam `ThreadPoolExecutor`/`_CARTEIRA_FII_STATUS_VALIDOS`
   (NameError real em `/fii-infra` e `/fiis/universo-complementar` — só aparecia
   DEPOIS que o scraping de rede tinha sucesso, por isso o boot test no sandbox,
   que não acessa Fundamentus/Investidor10, nunca chegava nessas linhas e não
   pegou o bug antes do commit). Ambos corrigidos e revalidados.
2. **`rotas_etfs.py` (Fase 5) — fix de performance, não crash**: `/etfs/carteira/resumo`
   buscava o histórico de cada ETF da carteira SEQUENCIALMENTE via Yahoo (até 2 hosts
   × 8s por ticker). Com Render free tier (timeout de request), isso podia estourar
   e devolver resposta vazia pro navegador (`Unexpected end of JSON input`).
   Corrigido: agora usa `ThreadPoolExecutor` (orçamento de 15s), mesmo padrão já usado
   em `_fetch_etfs_live`/`_refresh_completo_background`. Confirmado com teste de
   latência simulada (2s por ticker): antes ~4s+ para 2 posições, depois ~2,5s.

### LIÇÃO NOVA para próximas extrações/refatorações
Quando uma rota só executa um trecho de código DEPOIS de uma chamada de rede bem
sucedida (ex: processamento paralelo pós-scraping), o boot test de 2 camadas
(`ast.parse` + `app.test_client()`) não é suficiente sozinho se o sandbox não tem
acesso à rede real usada pela rota — o código nunca chega a rodar esse trecho, e
um `NameError` escondido ali passa despercebido. Precisa **mockar a função de rede**
(ex: `fontes_etfs._fetch_yahoo_series = lambda ...: {...}`) para forçar a execução
real do trecho pós-rede antes de considerar validado. Usado com sucesso para pegar
e confirmar os 2 bugs acima.

### Incidente durante validação (revertido)
Um teste de `POST /etfs/mover` rodou sem querer com o token de escrita real contra
o `etfs_estado.json` de produção, adicionando IVVB11 em `em_analise` sem ter sido
pedido. Revertido na hora (estado exato de antes restaurado, novo SHA
`3972f87b0de75a9b35f4821a206595246b4012f0`). **Regra nova**: testes de rota de
escrita (POST/PUT/DELETE) SEMPRE com `_github_get_file`/`_github_put_file`
mockados — nunca mais token real em teste, mesmo que o teste pareça inofensivo.

### Nota conhecida (não é bug, não vale corrigir sem sair do free tier)
Erros esporádicos de "Unexpected end of JSON input" ao clicar rápido em Atualizar
(FIIs) ou trocar de aba rapidamente (Em Análise) — Render free tier só tem 1
worker, então duas requisições pesadas simultâneas competem pelo único processo e
uma pode estourar timeout. Usuário confirmou: não clicar em cascata resolve na
prática. Não é regressão da modularização.

## Itens CONCLUIDOS e VALIDADOS em sessao anterior (02/07/2026)

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

## SAGA DO DY DE ETFS -- RESOLVIDA DE VERDADE (04/07/2026)
Historico completo (a v20 registrou o meio do caminho; isto e o desfecho real):

**Descoberta 1 (03/07):** mapeamento por header do investidor10 piorou (pagina tem varias tabelas/thead) -- revertido para indice fixo + trava `_dy_plausivel`.

**Descoberta 2 (03/07):** trava de sanidade escondeu o sintoma mas nao a causa -- ETFs pagadores tambem ficaram sem DY. Solucao adotada: Yahoo (`quoteSummary.summaryDetail.dividendYield`) como fonte primaria de DY, investidor10 como fallback.

**Descoberta 3 (04/07, INICIO DESTA SESSAO):** apos a Prioridade 2 fase 2 (extracao de fontes_etfs.py), a watchlist inteira apareceu com "-" em tudo, mesmo forcando refresh. Causa: `_cache_etfs_live` e `_ETF_CACHE_TTL` foram APAGADOS POR ENGANO no corte -- `_fetch_etfs_live()` lancava `NameError` em toda chamada, escondido pelo `except Exception: live={}` da rota. Corrigido restaurando as 2 linhas. **LICAO CRITICA: boot test (importar modulo + contar rotas) NAO basta -- e preciso CHAMAR as rotas via `app.test_client()` de verdade antes de considerar uma extracao validada.** Isso virou pratica obrigatoria a partir de agora.

**Descoberta 4 (04/07, A CAUSA RAIZ VERDADEIRA):** criei rota de diagnostico `/etfs/live-status` (expõe status HTTP, tempo, linhas parseadas, chamadas Yahoo cruas) porque nao consigo testar rede real do sandbox de dev. Victor rodou em producao e o `primeira_linha_bruta` revelou: o investidor10 duplica CADA CELULA da tabela (`["R$ 437,18","R$ 437,18", "15,27%","15,27%", ...]`) -- provavelmente uma variante responsiva/mobile embutida no mesmo HTML. Isso desalinhava QUALQUER indice fixo desde o primeiro dia: a coluna 5 (esperada = DY) na verdade pegava a segunda copia da Variacao 24m -- exatamente o "BOVA11 com 10000%" original. NAO era header, nao era mapeamento -- era duplicacao de celula.

**FIX FINAL:** `_deduplicar_celulas()` em fontes_etfs.py colapsa pares consecutivos identicos antes de indexar. Validado com o HTML real (via diagnostico) e com mock: IVVB11 (indice, sem dividendo) -> dy=None correto; NDIV11 (pagador) -> dy=9.8% plausivel. Confirmado em producao via segunda rodada do diagnostico: `total_com_dado: 61/61`, linha limpa com 10 elementos.

**Ajuste final de prioridade de fontes:** com investidor10 corrigido e confiavel de novo, Yahoo virou FALLBACK (so preenche lacuna quando investidor10 nao tem o dado), nao mais primario -- descobriu-se que o Yahoo da preco ERRADO para COIN11 (R$39,50 vs R$47,98 real, ~20% de diferenca, provavel ticker `.SA` resolvendo para instrumento errado). Sobrescrever um investidor10 ja correto com um Yahoo as vezes errado seria regressao.

**Dado corrigido:** `etfs_estado.json` tinha `preco_entrada: null` para COIN11 e SPYI11 (comprados em 03/07 quando investidor10 ja estava com o bug). Corrigido com cotacao real confirmada via investidor10 ao vivo (COIN11: R$47,98, SPYI11: R$108,53), autorizado por Victor ("pegue o ultimo preco sem problemas"), mantendo data_entrada original.

**PENDENTE:** investigar por que Yahoo da preco errado para COIN11/SPYI11 especificamente (BDR/wrapper de ETF americano, "high income" com opcoes) -- pode ser resolucao de ticker `.SA` incorreta no Yahoo para esse tipo de fundo. Nao e urgente agora que Yahoo virou so fallback, mas vale entender se aparecer de novo.

## FECHAMENTO DA SESSAO 04/07/2026 -- recapitulacao final

**Tudo abaixo foi validado pelo usuario no ar (nao so no sandbox):**

1. Watchlist de ETFs: DY/preco/var/cap corretos depois do fix de deduplicacao de celula.
2. Escala de risco invertida (1=minimo, 10=maximo -- era o contrario, Cripto aparecia como 1). Rotulos dos filtros (`ETF_RISCO_LABEL`) corrigidos junto.
3. Botao "Atualizar" nao trava mais em 502 -- `forcar=1` agora so dispara refresh em background e devolve o cache na hora, nunca bloqueia a resposta.
4. Loading states adicionados na tabela de ETFs (ficava em branco enquanto carregava a primeira vez) e nos botoes "+ Em Analise"/"OK -> Carteira" (ficam desabilitados com "⏳ ..." durante o POST). FIIs ja tinha isso desde antes, nao precisou mexer.
5. Carteira de ETFs: preco_entrada de COIN11/SPYI11 corrigido (estava null por causa do bug do investidor10 no dia da compra) -- usado preco real confirmado via investidor10 ao vivo.
6. Prioridade 2 da modularizacao: fases 1 (`motor.py`) e 2 (`fontes_etfs.py`) concluidas e validadas. proxy.py caiu de 6.940 para ~6.500 linhas.

**Bug mais serio da sessao (referencia rapida caso precise depurar algo parecido no futuro):** a extracao do fontes_etfs.py apagou sem querer `_cache_etfs_live`/`_ETF_CACHE_TTL`, causando `NameError` silencioso em toda chamada de `_fetch_etfs_live()` (escondido pelo `except Exception: live={}`). So foi descoberto rodando `app.test_client()` de verdade contra a rota -- boot test (importar + contar rotas) NAO pega esse tipo de erro. **Regra permanente a partir de agora: toda extracao/refatoracao de rota precisa ser testada com `app.test_client()` batendo nas rotas afetadas, alem do boot test.**

**Praticas consolidadas nesta sessao (usar sempre daqui pra frente):**
- SHA antes E depois de cada edicao, anotado no raciocinio (backup implicito via git history).
- Validacao em 2 camadas: boot test (importa modulo) + `app.test_client()` batendo nas rotas de verdade.
- Rede real (investidor10/Yahoo/Render) so pode ser testada em producao -- quando precisar diagnosticar algo que depende de rede, criar uma rota de diagnostico temporaria (como `/etfs/live-status`) em vez de tentar adivinhar do sandbox.
- Ao achar um bug de dado (ex: DY errado), sempre considerar a hipotese "duplicacao/estrutura do HTML mudou" antes de "mapeamento de coluna errado" -- a segunda parece mais obvia mas nem sempre e a causa real.

**Proxima sessao, ordem sugerida:**
1. Validar mais uma vez a Watchlist/Em Analise/Carteira de ETFs com uso normal (sem forcar nada), confirmar que loading states aparecem bem.
2. Se tudo OK, seguir a Prioridade 2 -- Fase 3 (`fontes.py` geral: Yahoo fundamentals, Bacen/CDI, scrapers de FIIs) ou pular direto pra Fase 4/5 (rotas_fiis.py/rotas_etfs.py) se preferir ver o proxy.py enxugar mais rapido.
3. Backlog de medio prazo (sem urgencia): investigar por que Yahoo erra preco do COIN11/SPYI11; considerar adicionar confirmacao antes do "Tirar Foto de Todos" (reseta historico sem avisar); revisar se algum outro FII/papel tem tese pendente tipo ORVR3.

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
- **NOVO 05/07/2026** — "Em Análise" de ETFs deveria morar dentro da aba única `#tab-emanalise` (junto com Estruturas em Análise + ranking de FIIs), em vez de dentro de "Carteira ETFs". "Carteira ETFs" ficaria só com a carteira de fato. Classificado pelo usuário como estético, não urgente.
- Historico mensal completo de dividendos na Carteira FIIs — **DESCARTADO 02/07/2026**: StatusInvest so tem totais semestrais via scraping simples (regex), o breakdown mes-a-mes fica atras de chamada assincrona/JS que nao consigo capturar de fora. Usuario decidiu que nao vale o esforco pra uma informacao complementar (ja acessa via detalhe do fundo quando precisa).
- Varredura/limpeza de fundos "lixo" (FIIs mortos/incorporados) na Carteira FIIs — usuario vai estudar criterios e trazer numa proxima sessao; Claude tambem deve propor criterios quando o assunto voltar.
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
