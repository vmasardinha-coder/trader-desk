# Trader Desk — Prompt de Continuação (v3 — substitui PROMPT_NOVA_SESSAO_v2.md)

## ⭐ COMECE AQUI ⭐

Sou o Claude continuando o desenvolvimento do Trader Desk com o Victor.

**Por que este documento existe (v3, 04/08/2026):** o `PROMPT_NOVA_SESSAO_v2.md` antigo virou
um histórico linear gigante (sessões de 02/07 a 04/08 empilhadas, nunca podado). Isso causou a
MESMA revisão de "o que já foi feito de verdade" acontecer 3 vezes (15/07, e de novo em 04/08).
Este documento é deliberadamente CURTO. Regra permanente daqui pra frente:

- **A "Tabela Mestre" abaixo é a ÚNICA fonte de verdade de pendências.** Ao fechar um item,
  editar a linha na hora (não empilhar texto novo em outro lugar do arquivo).
- **Antes de assumir que algo está pendente, VERIFICAR NO CÓDIGO** (`raw.githubusercontent.com`
  via bash_tool) — não confiar de olhos fechados numa lista antiga. Comentários no código costumam
  citar `backlog #N (data)` quando um item foi implementado — grep por isso ajuda.
- **Histórico narrativo detalhado de sessões anteriores (até 04/08/2026)** fica preservado em
  `PROMPT_NOVA_SESSAO_v2.md`, mas esse arquivo NÃO é mais atualizado e NÃO deve ser tratado como
  fonte de status atual — é só arquivo morto pra arqueologia, se um dia for preciso entender por
  que uma decisão antiga foi tomada.

**Protocolo de início de sessão:**
1. Ler ESTE arquivo (`PROMPT_NOVA_SESSAO_v3.md`) via `api.github.com` (nunca
   `raw.githubusercontent.com` — CDN cacheia e pode mostrar versão desatualizada).
2. Puxar `ROTINA_GATES_LOTE.md` se o usuário trouxer um lote de opções pra analisar.
3. Antes de editar qualquer arquivo: buscar SHA fresco na hora (nunca reusar SHA de memória/sessão
   anterior).
4. Sistema é de TOMADA DE DECISÃO (melhorar assertividade), não controle de carteira/P&L exato —
   isso as corretoras já dão.
5. **Checagem periódica (a cada ~15 dias — ⚠️ ATRASADA: prevista a partir de 20/08/2026, não rodada até 09/09/2026):** rodar de novo a
   checagem de indexação do BCDI11 (FI-Infra novo, estreou 04/08/2026) nas 3 fontes — testar
   `curl` direto em `fiis.com.br/lista-de-fundos-imobiliarios/` (grep "BCDI"),
   `investidor10.com.br/fiis/bcdi11/` (status 200?), e `GET /fiis/universo-complementar` em
   produção (ticker aparece na resposta?). Se QUALQUER uma tiver indexado, avisar o Victor — os
   dados já vão aparecer sozinhos no app sem precisar de novo deploy (rota `universo-complementar`
   é dinâmica; a whitelist do `scrape_fi_infra()` já foi corrigida em 06/08/2026). Aproveitar essa
   mesma sessão pra rodar de novo a auditoria geral do universo de FIIs (bruto combinado vs.
   validados, ver nota de memória sobre o que Victor quer dizer com "total") e conferir se algum
   outro fundo novo (FI-Infra ou não) apareceu sem estar na whitelist. **Nota**: essa checagem só
   roda quando o Victor abre uma sessão — não existe agendamento automático fora de sessão; se ele
   quiser isso rodando sozinho sem precisar abrir chat, a ferramenta certa é Cowork/agendamento
   externo, não esta conversa.

---

## 🎯 TABELA MESTRE DE PENDÊNCIAS (auditada em 04/08/2026 direto no código, não por memória)

### UI
| Item | Status |
|---|---|
| Botão de foto em lote pra watchlist | ✅ Feito (`tirarFotoTodas()`, app.js) |
| Bandas p10/p90 com legenda de confiança na Foto do Papel | ✅ Feito (`#{id}-foto-confianca`, app.js) |
| Auto-congelamento de bandas ao criar análise em Em Análise | ✅ Feito (`_congelar_bandas_analise`, proxy.py, chamada em `POST /analises`) |
| % de variação em R$ nas Posições Ativas | ✅ Feito (`Ch(id,n,p,'r')`, app.js — aplicado em todas as posições ativas, incl. `bb`/`bb2` juntos) |

### Cotações
| Item | Status |
|---|---|
| **KCRP11 e KNPL11 (fundos novos Kinea, ainda não listados)** | 🔵 AGUARDANDO LANÇAMENTO — pedido pelo Victor em 13/08/2026 pra monitorar assim que listarem. **KCRP11** (Kinea Crédito Residencial Pulverizado) — NÃO é FII de tijolo residencial, é fundo de CRÉDITO: investe em séries sênior de CRIs pulverizados ligados a financiamento residencial, LTV esperado <40%. Oferta em registro na CVM (2026), ainda não estreou na B3. **KNPL11** (Kinea Plataforma Residencial) — esse sim é residencial de tijolo/renda: parceria Kinea + Brookfield, mais de 4.000 unidades residenciais em 22 projetos (multifamily), meta de retorno IPCA+8,75% a.a., oferta de R$1,9 bi, "em emissão" (fase de captação, ainda sem estreia na B3). **Ação quando listarem**: nenhum dos dois provavelmente vai caber na whitelist de FI-Infra (`TICKERS_FI_INFRA_CONHECIDOS`) — são categorias diferentes (crédito residencial e tijolo residencial, não infraestrutura). Verificar se entram no universo padrão do Fundamentus (FIIs comuns) automaticamente assim que negociarem, ou se precisam de tratamento à parte como o FI-Infra. Ligado ao item de descoberta automática de fundos novos, mais abaixo. |
| Item | Status |
|---|---|
| Ouro/Prata/Cobre à vista (spot) | ✅ **FECHADO em 06/08/2026** — fonte Hyperliquid (`fetch_commodities_hyperliquid()`). Os 3 (GOLD/SILVER/COPPER) confirmados batendo com referência externa pelo Victor. Campo `_spot_debug` temporário removido do `/futures` (não é mais exposto no payload). |
| **SELIC (`/yields br_selic`) presa em 14,25% após o corte pro 14,00%** | ✅ **FECHADO em 07/08/2026** — dois bugs achados pelo Victor. (1) `/yields` usava série SGS 11 do Bacen achando que vinha "% a.a. direto", mas na verdade é taxa DIÁRIA (ex: 0,0517) — sanity check sempre rejeitava, caía no fallback fixo; trocado pra série 432 (Meta Selic Copom), que já vem correta em % a.a. (2) `get_cdi()` (série SGS 4389) aplicava composição diária em cima de um valor que já vinha anualizado — resultado virava ~10¹⁶, também sempre rejeitado, mesmo fallback. Corrigido: usa o valor direto. Validado em produção: `br_selic` retornando 14,0% corretamente. |
| **NTN-B (curva de juros real) sempre `null`** | ✅ **FECHADO em 07/08/2026** — pedido do Victor: fonte anterior (TradingView, um único ponto ~10y) nunca funcionava de verdade. Trocado por `scrape_anbima_ettj_ntnb()` (fontes.py), que lê o arquivo público de Estrutura a Termo (ETTJ) da própria ANBIMA — gratuito, sem login, publicado diariamente (fechamento D-1). Agora retorna a curva completa em 4 vértices exatos: **2Y, 5Y, 10Y, 30Y** (não só um ponto). Novo campo `br_ntnb_curve` no `/yields`; `br_ntnb` mantido por compatibilidade (mesmo valor do vértice 10Y). Frontend (`index.html` + `app.js`) ganhou 4 linhas na tabela de Cotações, com tooltip mostrando a data de referência ANBIMA. Validado em produção. |
| `yquote_estavel()` sem nenhuma chamada no código | 🟡 ABERTO, baixa prioridade — decidir remover ou reaproveitar. |
| **UTLL11 (ETF de Utilidade Pública) não aparecia na lista** | ✅ **FECHADO em 07/08/2026** — mesmo padrão de bug do BCDI11: `ETF_UNIVERSO` (fontes_etfs.py) também é whitelist fixa, e o UTLL11 (ETF real da Investo/BTG, replica índice Utilidade Pública B3 — Eletrobras, Sabesp, Eneva, Copel, Engie, Equatorial — lançado em 2025) simplesmente não estava nela. Adicionado. Diferente do BCDI11, a fonte (investidor10.com.br) já indexava o papel (~1 ano de listagem) — dados já aparecem completos em produção (preço R$117,73, var_24m confirmado). **Mesmo item estrutural do backlog de FI-Infra se aplica aqui**: `ETF_UNIVERSO` também não tem descoberta automática — se sair ETF novo, vai precisar de aviso manual de novo. |
| Cache no-cache em `/futures` e `/carteira-fiis` (preço de FII/futuro travado no navegador) | ✅ Fechado — código confirmado e VALIDADO pelo Victor em 04/08/2026. |
| Coluna "Preço ativ." na Carteira de FIIs parecendo desatualizada | ✅ Fechado — não é bug. É o preço CONGELADO na ativação por design (`preco_ativacao`), usado só como referência de comparação, nunca recalculado. Sistema não é pra acompanhar cotação ao vivo (Victor confirmou não precisar disso). Preço vivo já existe e é usado no card de resumo agregado (`/carteira-fiis/resumo`), não na tabela linha-a-linha. |
| **BCDI11 (FI-Infra novo) não aparecia na Carteira** | ✅ **FECHADO em 07/08/2026** — resolvido em 2 etapas. (1) 06/08: identificado que `TICKERS_FI_INFRA_CONHECIDOS` (whitelist manual) não tinha o BCDI11 (BTG Pactual Dívida Infra CDI, estreou B3 04/08/2026 após 2 anos no balcão) — adicionado. (2) 07/08: mesmo com o ticker na whitelist, `scrape_fi_infra()` só descobria fundos via `fiis.com.br` (que ainda não indexava o BCDI11) — adicionada Camada 3: se `fiis.com.br` não achar, tenta confirmar via `investidor10.com.br` individual (que já tinha o fundo indexado, cotação R$95,51). Confirmado em produção: aparece em `/fiis` (fiis_todos, 583 total) e com dados completos em `/fii-infra` (cotação, DY 1,26%, P/VP 0,93). Marcado "fora do critério" por falta de dado de liquidez (fonte ainda não publica esse número, esperado pra fundo com poucos dias de negociação). |
| **🔴 Descoberta automática de FI-Infra/ETF novos (item estrutural, prioridade normal)** | 🔴 ABERTO — pedido pelo Victor em 06/08/2026. Hoje as whitelists (`TICKERS_FI_INFRA_CONHECIDOS` em fontes.py E `ETF_UNIVERSO` em fontes_etfs.py) são 100% manuais: quando sai um fundo/ETF novo, o app NUNCA vai detectar sozinho — precisa de alguém notar visualmente e pedir pra atualizar o código, sempre. A Camada 3 adicionada em 07/08 resolve o caso de "ticker já está na whitelist mas uma fonte está mais lenta que a outra" — mas não resolve "ticker nem está na whitelist ainda". **Ação proposta**: rotina que raspa TODOS os tickers marcados como "Fi-infra:" no `fiis.com.br` (mesmo padrão regex já usado, só sem o filtro de whitelist) e compara contra a whitelist — sinaliza (não precisa auto-adicionar) quando aparece um ticker novo não catalogado. Mesmo espírito do backlog de checagem de barreiras: read-only, aditivo, avisa em vez de agir sozinho. |

### Arquitetura / bugs corrigidos
| Item | Status |
|---|---|
| **Ranking em lote travando com muitas análises (502/JSON vazio)** | ✅ **FECHADO em 03/09/2026** — causa raiz: **limite de timeout do gateway do Render (~30s)**, não é bug do nosso código. Backend já tinha paginação (offset/limit) pronta desde 25/06/2026 (primeiro incidente, com 17 análises), mas o frontend nunca foi atualizado pra usar. Voltou a quebrar com 58 análises simultâneas. Corrigido: `loadRankingAnalises()` no app.js agora pagina automaticamente em lotes de 10 (testado: ~14s por lote de 10, ~25s por lote de 15 -- 15 ficava perto demais do limite). **Se o volume de análises continuar crescendo e lotes de 10 pararem de ser suficientes**, as opções são: (1) reduzir o lote ainda mais, (2) upgrade do plano Render pra timeout maior, ou (3) reestruturar pra processamento assíncrono em fila. Nenhuma dessas é necessária agora. |
| Item | Status |
|---|---|
| **UI: Taxa hipotética + EV realizado no painel Encerradas** | ✅ **FECHADO em 13/08/2026** — pedido do Victor: (1) confirmado que a limpeza de 30 dias das rejeitadas é SÓ um filtro de exibição em `GET /analises` — o arquivo real nunca apaga nada, o tracking-hipotetico lê direto sem esse filtro; (2) novo card no dashboard de Encerradas: "🧪 Taxa de sucesso HIPOTÉTICA (rejeitadas já vencidas)", sempre mostrando o N junto (nunca só %, amostra pequena); (3) por item rejeitado já vencido, nova linha "EV realizado" logo abaixo do "EV na rejeição" já existente — compara o EV PROJETADO (Monte Carlo, no momento da decisão, nunca muda) com o EV REALIZADO (preço real até o vencimento). Não substituiu nada que já existia, só somou. |
| Item | Status |
|---|---|
| **Badge "FRACASSO" nas Posições Encerradas mostrava "PARCIAL"** | ✅ **FECHADO em 13/08/2026** — Victor notou ao fechar a rolagem BBAS3 (`cl-bbas3-rolagem-out26`, primeiro `status='fracasso'` explícito já registrado em `positions.json`). Causa: `tplEncerrada()` (app.js) só distinguia `status==='sucesso'` de "tudo o resto" — nunca teve badge de fracasso de verdade, qualquer coisa diferente de sucesso caía em "⚠ PARCIAL". Corrigido: agora trata os 3 estados (sucesso/fracasso/outro), nova classe CSS `.enc-fracasso` (vermelho) em `style.css`. Deploy confirmado em produção. |
| Item | Status |
|---|---|
| Migração Em Análise → Posições Ativas travava silenciosamente quando o papel-base já tinha outra posição ativa (ex: AXIA3.SA com `a3b`+`a3c`) | ✅ Corrigido em 05/08/2026 — `_migrar_para_positions` checava duplicidade por TICKER (errado, papel pode ter várias estruturas concorrentes); agora checa por ID, com sufixo automático em caso raro de colisão. Testado com o cenário real (AXIA3 "Proteção Parcial"). Causa raiz de uma análise que ficou presa "ativa" em Em Análise sem nunca aparecer em Posições Ativas — ver `an_1784576725` em Encerradas (fechada de forma neutra, não migrada a pedido do Victor, era teste). |
| Não existe (e nunca existiu) botão de "tirar foto" para uma análise JÁ CRIADA em Em Análise | ℹ️ Esclarecido em 05/08/2026 — `bandas_congeladas` só nasce no momento da criação (`POST /analises` → `_congelar_bandas_analise`). `GET /analises/<id>/foto-bandas` é só visualizador, nunca gerador. Fluxo real e único: Claude discute/filtra em chat e registra a análise diretamente via GitHub API — não existe (nem nunca existiu) uma tela de "Indicadores" separada para isso. |

### 🏗️ Cobertura de tipos de estrutura (auditoria completa, 19/08/2026)
Pedido do Victor após o bug do motor bidirecional: mapear TODOS os tipos de operação estruturada que existem no mercado (não só as que ele usa hoje), pra saber exatamente onde o sistema está pronto, onde está capenga, e onde não existe nada ainda. Fonte: catálogo oficial Itaú Corretora (itaucorretora.com.br/nossosservicos/operacoes-estruturadas.aspx) + o que já foi implementado no código. **Não urgente, mas importante** — Victor disse que ~80-90% do tempo ele usa retorno controlado, mas quer o sistema preparado pra quando precisar virar a mão.

**Tipos formalmente aceitos hoje no código**: `_TIPOS_VALIDOS = ['bidirecional', 'retorno_controlado', 'premio', 'simples', 'fii']` (analises.json) e `_TIPOS_RANKING_POSICOES = ('lancamento_coberto', 'retorno_controlado', 'bidirecional', 'put_seco')` (positions.json).

| Estrutura (nome oficial Itaú) | O que é | Status no sistema |
|---|---|---|
| **Retorno Controlado** (Forward Knock Out) | Retorno prefixado fixo se barreira de baixa não rompida; senão fica com o ativo | ✅ **Sólido** — bandas, probabilidade, tracking oficial+hipotético, tudo testado com volume real de casos |
| **Bidirecional** | Participação alavancada na alta + proteção/participação na queda, dentro de duas barreiras | ✅ **FECHADO — na verdade já estava, auditoria de 09/09/2026.** A nota de 19/08 ("não é função reutilizável, feito na mão") já nasceu desatualizada: `_retorno_bidirecional_full()` existe no `proxy.py` desde **15/07/2026**, é a função única compartilhada pelos 3 lugares que fazem esse cálculo (`/montecarlo/condicional`, `/montecarlo/posicao_ativa`, `/analises/ranking`), e no ranking ela alimenta `retorno_full_ev` → `retorno_medio_pct`, que é exatamente o EV dos 4 cenários. Cobre `downside_antes`/`downside_apos`, então pega Proteção Parcial e Proteção Total (kdo=None) também. **Ressalva que continua valendo**: mora no `proxy.py`, não no `motor.py`, e não tem caso de sanidade automatizado — se um dia for movida, mover com teste junto. |
| **Lançamento Coberto** (Covered Call) | Venda de call sobre ação em custódia | ✅ Usado em posições reais (BBAS3, ROXO34 `rx`) via `tipo_posicao='simples'`. Não tem probabilidade prevista formal (correto, por design — não é estrutura binária sucesso/fracasso) |
| **Venda Coberta de Call/Put** (tipo `premium`) | Vender call coberta ou put a seco, recebendo prêmio | ✅ **FECHADO em 25/08/2026** — motivado pelo caso real da ALPA4 (única de 27 opções que bateu a diretriz de 2%/mês, mas sem modelo de cálculo). `_calc_venda_opcao_premium()` (motor.py) + branch no ranking (`proxy.py`, tipo `premium`) — testado contra 4 casos de sanidade antes do deploy, validado em produção com dados reais (ALPA4: 68,88% prob. não-exercício, EV 5,05%/mês; ROXO34: 74,12%, 4,13%/mês). Cobre tanto Venda Coberta de Call quanto Venda de Put a Seco (campo `direcao`: 'call'/'put') — fecha os dois itens de uma vez. **Limitação conhecida**: assume fixing simples no vencimento (padrão europeu/OTC), não modela exercício antecipado americano — a maioria das opções listadas na B3 é americana na prática. Revisitar se Victor reportar exercício antecipado com frequência. |
| **Booster** (categoria "Acelerador") | Compra ação + compra call + venda 2x call em strike superior — ganho amplificado em alta moderada, capado acima do strike vendido | 🔴 **Não existe no sistema.** Estrutura de 3 pernas com alavancagem assimétrica — precisaria de payoff simulator próprio. |
| **Trava de Alta (Call Spread)** | Compra call + venda call em strike superior, mesma qtd/venc | 🔴 **Não existe.** Estrutura simples, payoff linear entre os dois strikes — relativamente fácil de modelar se aparecer. |
| **Trava de Baixa (Put Spread)** | Compra put + venda put em strike inferior | 🔴 **Não existe.** Espelho da trava de alta, para viés de baixa. |
| **Collar** | Ação + compra put + venda call — protege queda, capa alta | 🔴 **Não existe.** Conceitualmente parecido com bidirecional mas SEM alavancagem e SEM a opção de ficar "livre" dentro de um range — sempre travado nos dois lados. |
| **Collar Knock In** | Ação + put + call exótica (Up and In) — participa da alta até acionar barreira, depois capa | 🔴 **Não existe.** Variação do Collar com componente de barreira. |
| **Straddle / Strangle** | Compra call + put (mesmo strike = straddle, strikes diferentes = strangle) — aposta em volatilidade, não direção | 🔴 **Não existe.** Não tem barreira nem retorno prefixado — ganha se o papel se mexer muito pra qualquer lado. Modelagem diferente de tudo que já existe (não é sobre tocar/não tocar barreira, é sobre magnitude do movimento). |
| **Twin-Win / Autocall (COE)** | Produtos de emissor (não OTC de opções) com barreiras de observação periódica, geralmente com resgate automático se atingir certas condições | 🔴 **Não existe, e é categoria diferente** — COE tem risco de crédito do emissor, estrutura de vencimento antecipado automático ("autocall"), não é feito com opções flexíveis como o resto. Se Victor migrar pra isso, precisa de modelo de dados bem diferente (datas de observação periódica, não só vencimento único). |

**Ação proposta pra próxima sessão** (ordem de prioridade):
0. ✅ **[FECHADO 19/08/2026] "Risco de Overshoot" no retorno controlado** — implementado NO MESMO DIA a pedido do Victor (não ficou só no backlog). `_calc_risco_overshoot()` em motor.py, testada contra 3 casos de sanidade (teto alto→overshoot raro, teto baixo→overshoot quase certo) antes do deploy. Conectado no ranking ao vivo (`/analises/ranking`), reaproveitando a simulação que já existia (sem custo computacional extra) -- novos campos `prob_overshoot_pct` e `overshoot_medio_pct` em cada item retorno_controlado. Validado em produção com dados reais (ex: BBAS3 0,8% teto -> 43,68% chance de overshoot, média de 5,42pp deixados na mesa quando acontece).
0.1. ✅ **[FECHADO 09/09/2026] Validação de campos obrigatórios por `tipo_estrutura`** — origem: a bidirecional da BBAS3 foi registrada em 19/08 com `ganho_prefixado_pct` (nome usado no retorno_controlado) em vez de `teto_retorno_pct`/`alavancagem`/`kuo`, passou batido na validação e o ranking caiu em fallback silencioso (tela mostrando tudo em ~50%). Causa estrutural: `_validar_analise` só checava se `tipo_estrutura` era uma string aceita, nunca se os campos DAQUELE tipo estavam presentes — e os branches do ranking são `elif tipo == X and a.get(campo) is not None`, então campo faltando não casa com branch nenhum e o item sai sem EV, sem erro. Implementado: `_CAMPOS_POR_TIPO` (retorno_controlado → `kdo`+`ganho_prefixado_pct`; bidirecional → `kuo`+`teto_retorno_pct`+`alavancagem`; premio → `strike`+`premio`+`direcao`) e `_ENUM_POR_CAMPO` (`direcao`, `downside_antes`, `downside_apos`), com checagem de tipo numérico. Retorna 422 com mensagem explicando o efeito prático. `simples` e `fii` não exigem nada extra de propósito. `kdo` NÃO é exigido na bidirecional — "Proteção Total" é bidirecional legítima sem barreira de baixa. Validado em 2 camadas: 14/14 casos de sanidade (incluindo reprodução do bug real da BBAS3) + `app.test_client()` batendo em `POST /analises` e regressão de `GET /analises`, `/analises/stats`, `/analises/tracking-hipotetico`. **Regressão contra dado real: as 55 análises `em_analise` de produção foram passadas pela nova regra, 0 reprovações** — a lista de campos bate com o que o Victor realmente registra. Commit `b07bdac8`.
1. ✅ **[FECHADO — já estava feito, auditoria 09/09/2026]** Ver a linha "Bidirecional" na tabela de cobertura acima: `_retorno_bidirecional_full()` cobre isso desde 15/07/2026.
2. Definir o mínimo necessário pra "Venda de Put a Seco" ter tracking próprio (provavelmente similar ao retorno_controlado invertido — sucesso = não ser exercido, ou dependendo da visão de Victor, sucesso = ser exercido a um preço que ele queria comprar mesmo)
3. Deixar Trava de Alta/Baixa e Collar documentados prontos pra implementar rápido quando/se aparecerem (payoff simples, baixo risco de bug)
4. Straddle/Strangle e Autocall/COE ficam no fim da fila — mecânica bem diferente do resto, exigem desenho novo, só valem o esforço se Victor realmente for usar
5. **Regra de processo daqui pra frente**: toda vez que uma função de cálculo central for criada ou alterada, rodar contra pelo menos 1 caso manual conhecido ANTES de considerar pronta — foi a falta disso que permitiu o bug da bidirecional passar batido por 2 sessões inteiras

### Modelagem
| Item | Status |
|---|---|
| **Jump-Diffusion (Merton) — sinal de que vale a pena, teste preliminar 01/09/2026** | 🟡 **Elevado de "estudo futuro sem prioridade" para "vale investigar mais a serio"** — motivado pela faixa 70-80% do tracking de calibração dando persistentemente ~50% de acerto (vs. os 70-80% prometidos). Rodei um rascunho de Jump-Diffusion (deteccao de saltos via MAD robusto sobre retornos historicos do Yahoo -- dado gratuito, ja disponivel, SEM precisar de MT5 ou fonte paga) nos 6 casos dessa faixa. Resultado: os 2 casos que davam fracasso (TSLA34, DIRR3 curto) foram corretamente rebaixados pra faixa 60-70% pelo Jump-Diffusion, deixando a faixa 70-80% remanescente com 75% de acerto (3 sucessos de 4) -- MUITO mais proxima do prometido. Amostra pequena (6 casos), nao prova nada estatisticamente ainda, mas a DIRECAO do efeito bate exatamente com a hipotese (GBM puro subestima risco em papeis de vol alta/prazo curto, que sao justamente os que mais aparecem nessa faixa intermediaria). **LEITURA DE 09/09/2026** (`GET /analises/tracking-hipotetico` em producao): 21 avaliadas, 76,2% de acerto binario. Calibracao por faixa: 50-60% n=1 (0%), 60-70% n=5 (80%), **70-80% n=6 (50%)**, 80-90% n=7 (100%), 90-100% n=2 (100%). A faixa 70-80% continua com **exatamente os mesmos 6 casos** de 01/09 (DIRR3 x2, VIVA3, TSLA34, ITLC34, CMIN3) -- nenhuma nova venceu em 8 dias. Extremas bem calibradas, o buraco segue sendo o meio, que e justamente a hipotese. **Nao reprocessar ainda.** **Proximo passo, quando o tracking tiver mais volume na faixa 70-80% (sugestao: esperar chegar a uns 15-20 casos antes de decidir)**: se o padrao se confirmar, promover de rascunho pra implementacao real no motor.py (funcao `_calc_prob_sucesso_prevista` ganharia um parametro opcional usando Jump-Diffusion em vez de GBM puro quando houver dado historico suficiente do ativo). Codigo do rascunho ficou só no chat dessa sessao, nao commitado -- se for prosseguir, reescrever como funcao testada de verdade, seguindo o mesmo padrao de auditoria (testar contra casos conhecidos antes de considerar pronta).
| Item | Status |
|---|---|
| **Auto-rejeição quando o prazo vence sem decisão** | 🔵 Ideia registrada 25/08/2026, baixa prioridade — Victor notou que análises em `em_analise` que passam do vencimento sem serem aceitas ficam "penduradas" indefinidamente (ex: BBAS3/PRIO3 perto de 100% de prob., faltando poucos dias). Hoje ele fecha manualmente essas na mão (rejeita, entra no tracking hipotético normalmente, já validado). Ideia pra depois: rotina que auto-rejeita (ou pelo menos sinaliza) análises com vencimento já passado sem decisão — mas Victor disse explicitamente que não é urgente, o fluxo manual atual funciona bem. Não implementar sem pedido explícito. |
| Item | Status |
|---|---|
| **Papel do EV na decisão do Victor (esclarecido 13/08/2026)** | ℹ️ **Importante pra não reavaliar errado no futuro.** O Victor NÃO usa `ev_mensal_na_rejeicao` como preditor isolado de sucesso/fracasso — ele usa a **probabilidade prevista** como filtro principal, e o EV como **desempate** entre candidatas com probabilidade PRÓXIMA (duas opções com prob. parecida → pega a de EV positivo). Teste feito em 13/08 comparando "EV>0 previu sucesso?" (60% de acerto em 5 casos, vs. 75% da probabilidade sozinha em 8 casos) estava testando a pergunta ERRADA — EV nunca teve o papel de prever resultado sozinho. **A pergunta certa pra medir no futuro**: dado um PAR de candidatas com probabilidade próxima na mesma decisão, escolher a de EV positivo levou a resultado real melhor que a alternativa? Isso exige pares de candidatas concorrentes na mesma decisão (não só uma lista solta de rejeitadas) — precisa de mais volume/tempo pra ter amostra significativa. Ainda não há infraestrutura pra isso (não sabemos hoje quais análises "competiram" entre si na mesma decisão) — considerar campo `lote_concorrentes` ou similar se o padrão se repetir. |
| Item | Status |
|---|---|
| Mecânica americana vs. europeia no motor de Monte Carlo | ✅ **JÁ IMPLEMENTADO** (v10.10–v10.13 do proxy.py) — campo `exercicio` obrigatório em `/montecarlo`, `/montecarlo/condicional`, `/montecarlo/posicao_ativa`; americana simula max/min da trajetória completa, europeia só preço final. Backlog antigo dizia "não incorporado" — estava desatualizado. |
| Fan chart / Monte Carlo condicional em Posições Ativas | ✅ **JÁ IMPLEMENTADO** — `/montecarlo/posicao_ativa` retorna `trajetorias_fan`, frontend renderiza via `renderFanChartAnalise()` (botão "Ver evolução desde a entrada" em cada posição). |
| Tracking previsão-vs-realizado (assertividade real do motor MC/GARCH) | 🟡 **BACKEND ENTREGUE em 06/08/2026, aguardando validação com caso real (mesmo status do item de checagem de barreiras — Victor quer ver funcionar antes de fechar).** Implementado: (1) `_calc_prob_sucesso_prevista()` em motor.py — congela na Fase B a probabilidade de não tocar KDO/KUO até o vencimento, via Monte Carlo ancorado no `preco_foto`/prazo original; (2) `_congelar_bandas_analise` grava esse número dentro de `bandas_congeladas.prob_sucesso_prevista_pct` em toda análise nova de retorno_controlado/bidirecional; (3) `_migrar_para_positions` propaga o campo para `positions.json` na migração (senão se perderia, já que a análise original é apagada depois de migrar); (4) `GET /analises/tracking-acuracia` (somente leitura) agrega análises+posições fechadas com o campo presente, compara previsão vs. resultado real, e mostra calibração por faixa de 10pp. Validado localmente (simulação PETR4 retornou 74,96%, número plausível) e em produção (rota responde 200, regressão das rotas antigas ok). **Só vale daqui pra frente** — registros antigos (MUTC34, ROXO34, BBAS3 etc.) não têm o campo e nunca vão aparecer no tracking; só passa a alimentar estatística quando a PRIMEIRA análise criada com essa versão do código for fechada (sucesso ou fracasso) de verdade. |
| **Tracking HIPOTÉTICO (calibração em análises rejeitadas/nunca executadas)** | ✅ **BACKEND ENTREGUE em 12/08/2026, JÁ COM DADO REAL.** Complementa o tracking oficial acima — pedido do Victor: mede se o modelo acerta mesmo nas análises que ele rejeita ou nunca executa por falta de capital (o tracking oficial só conta o que virou dinheiro real). `GET /analises/tracking-hipotetico` (somente leitura): inclui análises `retorno_controlado`/`bidirecional` com `prob_sucesso_prevista_pct` congelada, SEM `resultado` real setado, e já vencidas (`data_foto + prazo_dias` em dias corridos ≤ hoje). Busca o histórico real de preço até o vencimento (reaproveita `_fetch_closes_for_foto`, já testada) e verifica se a barreira foi tocada. Resultado expresso em **%** (ganho prefixado hipotético ou variação real do papel se rompeu) — **nunca em R$**, já que não existe aporte real numa análise nunca executada; inventar um valor em reais seria dado fabricado. Mesma calibração por faixa de 10pp do tracking oficial. **SEM UI dedicada por decisão do Victor** — consultado sob demanda aqui no chat, não em tela nova. **Bug encontrado e corrigido na mesma sessão**: as 3 análises criadas em 12/08 (SPCX34 ×2, ROXO34) tinham `prazo_dias` calculado em dias ÚTEIS por engano — convenção errada, todo o resto do sistema usa dias CORRIDOS (confirmado comparando `prazo_dias` armazenado contra o texto "Xd" no nome de dezenas de análises existentes). Corrigido: `prazo_dias`, KDO, bandas e `prob_sucesso_prevista_pct` recalculados com a convenção certa (14/30/62 dias corridos, não 10/22/44 dias úteis). **Backfill retroativo (12/08/2026)**: 27 análises antigas já tinham `preco_foto`/`sigma_pct`/`kdo`/`kuo` congelados mas nunca tiveram `prob_sucesso_prevista_pct` derivada — calculado retroativamente em cima dos MESMOS números já congelados (nenhuma premissa nova, só o cálculo que faltava), marcado com `prob_sucesso_prevista_pct_origem: backfill_12082026` pra rastreabilidade. Resultado imediato: **7 dessas 27 já tinham vencido, taxa de acerto binário 71,4%**, com sinal de melhor calibração nas faixas de alta confiança (80%+ acertou 3/3) vs. faixas médias (70-80% acertou só 1/3) — ainda amostra pequena. Outras 23 (incl. AMZO34 venc. 13/08, ROXO34 venc. 30/08) vão entrar no tracking conforme forem vencendo, sem precisar de nova ação. |
| Mistura de volatilidade implícita (OpLab) + GARCH histórico | 🔴 ABERTO, confirmado — zero implementação no código. Depende do item de tracking acima pra medir se a mistura realmente melhora algo antes de valer o esforço. |
| **Bandas de Monte Carlo da SPCX34 nova (`an_1785945909`)** | ✅ Preenchidas em 05/08/2026 — `preco_foto` fixo R$39,20 como base, sigma 70,16% (vol. histórica, GARCH não convergiu), períodos 21/29d. |
| **Checagem retroativa de rompimento de barreira (KDO/KUO) em `em_analise`** | ✅ **FECHADO em 05/08/2026.** Backend: `GET /analises/checar-barreiras` (rota somente leitura, nunca escreve em analises.json) reaproveita `_fetch_closes_for_foto` já testada em produção, compara histórico real desde `data_foto` contra kdo/kuo de cada análise `em_analise` com barreira. Frontend: `checarBarreirasRompidas()` roda depois de `renderAnalises()` e injeta selo visual "⚠ BARREIRA ROMPIDA" (vermelho) no card afetado via DOM — puramente aditivo, não alterou `tplAnalise` nem nenhum fluxo de render existente; falha silenciosamente se a chamada der erro, sem quebrar a aba. Validado localmente (test client Flask, bateu com a auditoria manual das 8 análises) e em produção (Render) antes e depois do deploy. Caso real que motivou: MUTC34 (`an_1784737588`).|

**Nota:** os 2 itens de Modelagem marcados ✅ acima estavam listados como pendentes no backlog
antigo (04/08) — auditoria mostrou que já foram feitos em sessões anteriores e a lista nunca foi
limpa. Os outros 2 itens de Modelagem seguem genuinamente abertos.

---

## 📚 Princípios de decisão (permanentes — não reabrir sem novo contexto real)

**Critério de sucesso por tipo de estrutura (definido 19/08/2026):**
- **Bidirecional**: sucesso = bater o CDI no mínimo, sem tocar nenhuma das duas barreiras.
- **Venda de Put a Seco**: sucesso = prêmio recebido compensar o comprometimento de capital no strike. Rolar fica caro/difícil se o preço foge muito do strike original — nesses casos pode nem bater 1%/mês, mesmo "dando sucesso" tecnicamente.
- **Retorno Controlado**: sucesso = pagar o retorno prometido sem tocar a barreira de baixo. Objetivo é 100% financeiro — nunca é "acumular/manter ações" (isso é consequência automática da mecânica, não uma meta). Mesmo que o preço fique parado (nem suba nem desça o suficiente pra qualquer coisa interessante), ainda é sucesso se pagou o prometido — não dá pra "acertar o preço parado", isso seria sorte, não o objetivo.
- **Camada extra que atravessa todos os tipos**: sucesso também depende do resultado financeiro permitir montar **outra operação no ticket mínimo do banco** (normalmente R$30-50 mil por lote, e as PDFs de retorno controlado sempre citam R$30.000,00 de aplicação mínima). Não é só bater o % prometido isolado — é manter capacidade de giro pro próximo lote sem precisar completar capital do bolso. Por isso Victor se importa com quantidade de ações e valor final, não só a taxa percentual.

- **Alvo único de venda de opção**: sempre 2–2,5%/mês via prêmio, independente da estrutura
  (lançamento simples, retorno controlado, bidirecional). A estrutura é a "embalagem de risco",
  não a meta em si.
- **Sucesso é definido pelo Victor, não pelo número bruto**: ele carrega o papel no tempo. Pra
  lançamento coberto simples, sucesso = não ser exercido + embolsar prêmio, mesmo que o papel
  tenha caído. Rolar/aumentar posição é tática de recuperação, não o plano principal.
- **Rolar pra cima vs. entregar**: caso a caso, depende de leitura de upside restante. Se o papel
  correu rápido/violento demais (ex: ROXO34), a rolagem vira defensiva/sobrevivência, não
  estratégica — não tentar encaixar isso nos critérios normais de qualidade.
- **Bidirecional novo (a partir de 22/06/2026)**: só aceitar se teto de alta ≥ ~1%/mês
  proporcional ao prazo (30d→≥1%, 90d→≥3%, 12m→≥9-12%). Não aplicar retroativamente.
- **PDF do banco é premissa fixa**: nunca recalcular/reescalar números de um PDF oficial — só
  reprojetar o vencimento (dias restantes se ainda não venceu; prazo total do zero se já venceu).
- **Fase A (chat, números abertos) → Fase B ("tirar a foto", 4 números fechados: ticker/prazo/
  strike-range/prêmio)**: sempre perguntar antes de registrar se algum número parecer em aberto.
- **Grades de opções do OpLab**: sempre apresentar os 2 lados (call coberta E put vendida).
- **Mecânica americana/europeia**: confirmar SEMPRE por código de opção específico com o Victor,
  nunca presumir pelo ticker do papel-objeto (ex: ROXO34 já teve as duas mecânicas em rolagens
  diferentes).
- **Taxonomia de sucesso por tipo de estrutura** (usada no ranking de Posições Ativas):
  1. Lançamento coberto: sucesso = fechar ABAIXO do strike.
  2. Retorno controlado: sucesso = não romper a barreira inferior (KDO).
  3. Bidirecional: sucesso = fechar DENTRO do range (não rompe KDO nem KUO).
  4. Venda de put a seco: sucesso = fechar ACIMA do strike.

## 🏗️ Princípios de processo/arquitetura (permanentes)

- **`ThreadPoolExecutor` com `shutdown(wait=False)` é PERIGOSO no Render (1 worker)** — pode
  travar o processo inteiro, não só a rota. Preferir sequencial com timeout nativo do `requests`,
  ou orçamento de tempo fixo (`concurrent.futures.wait(timeout=X)`).
- **Um item por vez, validar antes de empilhar o próximo** — regra reforçada depois do incidente
  de 04/08/2026 no `/futures` (várias tentativas seguidas de spot causaram lentidão geral).
- **Validação em 2 camadas obrigatória**: `ast.parse`/`node -c` (só sintaxe) NÃO é suficiente —
  sempre também `app.test_client()` batendo nas rotas de verdade, com mocks de rede/GitHub. Vários
  bugs reais (NameError, campo faltando) só apareceram rodando de verdade, não no syntax check.
- **SHA fresco imediatamente antes de qualquer PUT no GitHub** — nunca reusar SHA de memória.
- **NUNCA usar `raw.githubusercontent.com` para reler um arquivo de dados (analises.json, positions.json, stats_analises.json etc.) dentro da MESMA sessão logo após escrever nele** — incidente real em 05/08/2026: escrevi corretamente o fechamento de uma análise, na sequência precisei reler o arquivo pra adicionar outro registro, usei `raw.githubusercontent.com` (CDN com cache de alguns minutos), peguei a versão desatualizada de ANTES do meu próprio fechamento, colei o novo registro nela e sobrescrevi — desfazendo silenciosamente a edição anterior sem erro nenhum aparecer. Regra: para qualquer ciclo de ler→editar→escrever dentro da sessão, usar SEMPRE `api.github.com` (nunca cacheia) tanto pra leitura quanto pra escrita. `raw.githubusercontent.com` só é seguro pra uma leitura isolada de diagnóstico, nunca como base pra uma escrita subsequente na mesma sessão.
- **Acesso de rede do sandbox do Claude**: ✅ **LIBERADO — confirmado por teste direto em
  09/09/2026**, primeira sessão nova depois da mudança de allowlist que o Victor fez em 05/08.
  Resultados: `query1.finance.yahoo.com` (PETR4.SA) → 200, `trader-desk.onrender.com/analises` →
  200 (298 KB), `api.hyperliquid.xyz/info` → 200. **Isso obsoleta toda menção neste documento a
  "não dá pra calcular GARCH / pegar preço ao vivo daqui"** — o Claude agora busca preço e
  histórico direto, roda GARCH no sandbox, consulta produção e recalcula bandas na hora de
  registrar uma análise, sem depender do Victor colar número. Era esse o gargalo do caso SPCX34
  (registrada em 05/08 sem `bandas_congeladas`). Se voltar a dar 403 "Host not in allowlist",
  a config foi revertida — testar de novo antes de assumir.
- **Estruturas bidirecionais/retorno controlado sempre com PDF oficial do banco presente** —
  nunca cadastrar de memória/estimativa.
- **ROXO34 = id `rx` sempre** (lógica hardcoded no app.js pra cotação/ITM-OTM/Monte Carlo
  Condicional). Nunca criar `rx2` ou variantes em rolagens futuras.
- **`positions.json`**: `tipo_posicao: "barreira"` exige `kdo` E `kuo` numéricos (validador
  rejeita se faltar um dos dois).

---

## 📌 Operações em andamento (RECONSTRUÍDA 09/09/2026 direto do `positions.json`)

**A versão anterior desta seção estava travada em 05/08/2026 e não batia mais com a realidade** —
listava `a3b`/`a3c` (já encerradas), `bslv39` venc. 05/10, `rx` venc. 17/09, `bb2` venc. 15/10.
Nenhum desses estava certo. Tabela abaixo lida do arquivo real (9 ativas, 18 encerradas).

| ID | Ticker | Tipo | Exercício | Vencimento | Números |
|---|---|---|---|---|---|
| `pt` | PETR4 | simples (call vendida) | europeia | 17/12/2026 | PETRL319, strike 30,85 — objetivo é rollover |
| `vl` | VALE3 | simples (call vendida) | europeia | 18/02/2027 | VALEB574, strike 57,40 — objetivo é rollover |
| `rx` | ROXO34 | simples (call vendida) | europeia | 17/12/2026 | ROXOL112, strike 11,25, 2.500 ações, delta 0,677 — **id SEMPRE `rx`** |
| `bb2` | BBAS3 | simples (call vendida) | europeia | 17/12/2026 | BBASL212, strike 20,81, 2.200 ações — risco elevado de exercício, papel com força |
| `tsmc34` | TSMC34 | retorno_controlado | europeia | 15/10/2026 | entry 280,95, KDO 224,52, prefixado 8,20% — boleto confirmado 19/08 |
| `sbsp3` | SBSP3 | retorno_controlado | europeia | 03/11/2026 | entry 25,10, KDO 21,21, prefixado 7,80% — boleto confirmado 04/09 |
| `inbr32` | INBR32 | retorno_controlado | europeia | 05/11/2026 | entry 29,97, KDO 23,58, prefixado 10,50% — boleto confirmado 04/09 |
| `tsla342` | TSLA34 | retorno_controlado | europeia | 10/11/2026 | entry 59,05, KDO 47,24, prefixado 5,30% — lote 09/09/2026 |
| `bslv392` | BSLV39 | retorno_controlado | europeia | 10/11/2026 | entry 103,22, KDO 82,58, prefixado 8,20% — lote 09/09/2026 |

**Ponto de atenção (09/09/2026):** `tsla342` e `bslv392` entraram como "candidata rolagem" no lote
de 09/09 e, diferente de `tsmc34`/`sbsp3`/`inbr32`, **não têm nota de "CONFIRMADO com o boleto
real"** na observação. Se os `entry` ainda forem provisórios, marcar como tal e corrigir só quando
o documento oficial de liquidação chegar — regra permanente de nunca fixar número financeiro por
estimativa. Confirmar com o Victor.

**Nota histórica:** `bslv39` (venc. 05/10) e `a3b`/`a3c` (AXIA3) saíram de ativas entre 05/08 e
09/09 — ver `encerradas` no `positions.json` para o desfecho de cada uma.

## Encerradas relevantes recentes
- ROXO34 (ROXOG105, strike R$10,50): fracasso — estourou barreira, opção era AMERICANA.
- BBAS3 antiga (BBASH21): sucesso — R$800/1,82% em ~38 dias.
- AXIA3(A): sucesso — R$1.580/65 dias (2,72%/mês), encerrada 20/07/2026.
- BSLV39 antiga: sucesso — 5,7% proporcional em 41/60 dias, encerrada 05/08/2026, rolada pra nova estrutura.
- **MUTC34 (`an_1784737588`, Em Análise, nunca virou posição real)**: barreira rompida no histórico real (KDO R$657,60, fechou R$632,92 em 29/07/2026) — passou batido pelo app por 1 semana até o Victor notar visualmente no gráfico em 05/08/2026. Encerrada manualmente na mesma data. NÃO conta em stats (nunca foi ativada). Ver item de PRIORIDADE em Modelagem acima pra evitar recorrência.

---

## 🔧 Stack & credenciais

- Flask no Render (free tier): `https://trader-desk.onrender.com`
- GitHub: `vmasardinha-coder/trader-desk` (branch: `main`)
- Token GitHub de SESSÃO: colado pelo Victor a cada sessão, nunca armazenado, usado via
  `api.github.com`.
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho, fine-grained, só este repo, Contents R/W):
  configurado em `GITHUB_TOKEN`/`GITHUB_WRITE_TOKEN` no Render — confirmado funcionando (validado
  em produção em 15/07/2026).
- `API_WRITE_TOKEN`: protege rotas de escrita da API do app (autentica o usuário, não o GitHub).
- Arquivos-fonte de dados: `positions.json`, `analises.json`, `stats_analises.json`,
  `carteira_fiis.json`, `etfs_estado.json`, `fundamentos.json`.
- Módulos: `proxy.py` (core + Monte Carlo de Papéis), `motor.py` (estatística pura), `fontes.py`
  (scrapers/fetches gerais), `fontes_etfs.py`, `rotas_fiis.py`, `rotas_etfs.py`.

## 🔑 SHAs de referência (09/09/2026 — SEMPRE rebuscar antes de editar, nunca reusar de memória)
- Último commit desta sessão: `b07bdac8` (proxy.py — validação por `tipo_estrutura`)
- Os SHAs antigos listados aqui (06/08/2026) foram removidos: estavam com um mês de idade e o
  próprio cabeçalho já dizia pra nunca reusá-los. Manter uma lista que não deve ser usada só
  convida a ser usada. Buscar fresco via `api.github.com/repos/vmasardinha-coder/trader-desk/contents/{arquivo}?ref=main`.

---

## 📜 Arquivo histórico

Todo o histórico narrativo detalhado de sessões de 02/07/2026 até 04/08/2026 (incluindo saga do DY
de ETFs, incidentes de ThreadPoolExecutor, correções de BSLV39, modularização do proxy.py, etc.)
está preservado em `PROMPT_NOVA_SESSAO_v2.md`, mantido como arquivo morto — não é mais tocado nem
deve ser lido como status atual. Consultar só se precisar entender o raciocínio por trás de uma
decisão antiga específica.
