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
5. **Checagem periódica (a cada ~15 dias — próxima a partir de 20/08/2026):** rodar de novo a
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
| Ouro/Prata/Cobre à vista (spot) | 🟡 QUASE FECHADO — fonte trocada de Yahoo para Hyperliquid (`fetch_commodities_hyperliquid()` em fontes.py). Bug do prefixo (`xyz:GOLD` vs `GOLD` puro) corrigido em 05/08. GOLD confirmado batendo com referência externa (validado pelo Victor em 05/08/2026). Em 05/08 (sessão seguinte) confirmado via `/futures` que `silver_spot` e `copper_spot` também já vêm populados com valores plausíveis (não mais `None`) — falta só o Victor confirmar visualmente no app que os 2 batem com a referência externa dele antes de fechar de vez. Campo `_spot_debug` ainda exposto no `/futures` (temporário, remover quando os 3 estiverem confirmados). |
| `yquote_estavel()` sem nenhuma chamada no código | 🟡 ABERTO, baixa prioridade — decidir remover ou reaproveitar. |
| Cache no-cache em `/futures` e `/carteira-fiis` (preço de FII/futuro travado no navegador) | ✅ Fechado — código confirmado e VALIDADO pelo Victor em 04/08/2026. |
| Coluna "Preço ativ." na Carteira de FIIs parecendo desatualizada | ✅ Fechado — não é bug. É o preço CONGELADO na ativação por design (`preco_ativacao`), usado só como referência de comparação, nunca recalculado. Sistema não é pra acompanhar cotação ao vivo (Victor confirmou não precisar disso). Preço vivo já existe e é usado no card de resumo agregado (`/carteira-fiis/resumo`), não na tabela linha-a-linha. |
| **BCDI11 (FI-Infra novo) não aparecia na Carteira** | ✅ Causa identificada e corrigida em 06/08/2026 — NÃO era liquidez nem filtro. `scrape_fi_infra()` (fontes.py) usa uma whitelist fechada e manual (`TICKERS_FI_INFRA_CONHECIDOS`, 22 tickers) — o BCDI11 (BTG Pactual Dívida Infra CDI, estreou na B3 em 04/08/2026 após 2 anos no balcão) simplesmente não estava nela ainda. Adicionado à whitelist. Dados (cotação/DY/liquidez) ainda NÃO aparecem — confirmado via checagem direta que nem `fiis.com.br` nem `investidor10.com.br` indexavam a página do fundo em 06/08 (404/410) — vão aparecer sozinhos assim que essas fontes externas publicarem, sem precisar de novo deploy. **Auditoria feita na mesma data**: comparei a whitelist completa contra o que `fiis.com.br` lista hoje como "Fi-infra:" — bate 100%, nenhum outro FI-Infra novo passou batido. Universo geral de FIIs também auditado: 560–561 linhas brutas do Fundamentus (Victor lembrava de ~592 — variação normal e esperada da base, fundos entram/saem de negociação; não é sinal de problema), 343 passam nos filtros de qualidade. |
| **🔴 Descoberta automática de FI-Infra novos (item estrutural, prioridade normal)** | 🔴 ABERTO — pedido pelo Victor em 06/08/2026. Hoje a whitelist de FI-Infra é 100% manual: quando sai um fundo novo (como o BCDI11), o app NUNCA vai detectar sozinho, mesmo que a fonte externa já liste ele — precisa de alguém notar visualmente e pedir pra atualizar o código, sempre. **Ação proposta**: construir uma rotina (pode ser leve, ex: dentro do próprio `scrape_fi_infra()` ou endpoint separado) que raspa TODOS os tickers marcados como "Fi-infra:" no `fiis.com.br` (mesmo padrão regex já usado, só sem o filtro de whitelist) e compara contra `TICKERS_FI_INFRA_CONHECIDOS` — sinaliza (não precisa auto-adicionar) quando aparece um ticker novo não catalogado. Mesmo espírito do backlog de checagem de barreiras: read-only, aditivo, avisa em vez de agir sozinho. |

### Arquitetura / bugs corrigidos
| Item | Status |
|---|---|
| Migração Em Análise → Posições Ativas travava silenciosamente quando o papel-base já tinha outra posição ativa (ex: AXIA3.SA com `a3b`+`a3c`) | ✅ Corrigido em 05/08/2026 — `_migrar_para_positions` checava duplicidade por TICKER (errado, papel pode ter várias estruturas concorrentes); agora checa por ID, com sufixo automático em caso raro de colisão. Testado com o cenário real (AXIA3 "Proteção Parcial"). Causa raiz de uma análise que ficou presa "ativa" em Em Análise sem nunca aparecer em Posições Ativas — ver `an_1784576725` em Encerradas (fechada de forma neutra, não migrada a pedido do Victor, era teste). |
| Não existe (e nunca existiu) botão de "tirar foto" para uma análise JÁ CRIADA em Em Análise | ℹ️ Esclarecido em 05/08/2026 — `bandas_congeladas` só nasce no momento da criação (`POST /analises` → `_congelar_bandas_analise`). `GET /analises/<id>/foto-bandas` é só visualizador, nunca gerador. Fluxo real e único: Claude discute/filtra em chat e registra a análise diretamente via GitHub API — não existe (nem nunca existiu) uma tela de "Indicadores" separada para isso. |

### Modelagem
| Item | Status |
|---|---|
| Mecânica americana vs. europeia no motor de Monte Carlo | ✅ **JÁ IMPLEMENTADO** (v10.10–v10.13 do proxy.py) — campo `exercicio` obrigatório em `/montecarlo`, `/montecarlo/condicional`, `/montecarlo/posicao_ativa`; americana simula max/min da trajetória completa, europeia só preço final. Backlog antigo dizia "não incorporado" — estava desatualizado. |
| Fan chart / Monte Carlo condicional em Posições Ativas | ✅ **JÁ IMPLEMENTADO** — `/montecarlo/posicao_ativa` retorna `trajetorias_fan`, frontend renderiza via `renderFanChartAnalise()` (botão "Ver evolução desde a entrada" em cada posição). |
| Tracking previsão-vs-realizado (assertividade real do motor MC/GARCH) | 🟡 **BACKEND ENTREGUE em 06/08/2026, aguardando validação com caso real (mesmo status do item de checagem de barreiras — Victor quer ver funcionar antes de fechar).** Implementado: (1) `_calc_prob_sucesso_prevista()` em motor.py — congela na Fase B a probabilidade de não tocar KDO/KUO até o vencimento, via Monte Carlo ancorado no `preco_foto`/prazo original; (2) `_congelar_bandas_analise` grava esse número dentro de `bandas_congeladas.prob_sucesso_prevista_pct` em toda análise nova de retorno_controlado/bidirecional; (3) `_migrar_para_positions` propaga o campo para `positions.json` na migração (senão se perderia, já que a análise original é apagada depois de migrar); (4) `GET /analises/tracking-acuracia` (somente leitura) agrega análises+posições fechadas com o campo presente, compara previsão vs. resultado real, e mostra calibração por faixa de 10pp. Validado localmente (simulação PETR4 retornou 74,96%, número plausível) e em produção (rota responde 200, regressão das rotas antigas ok). **Só vale daqui pra frente** — registros antigos (MUTC34, ROXO34, BBAS3 etc.) não têm o campo e nunca vão aparecer no tracking; só passa a alimentar estatística quando a PRIMEIRA análise criada com essa versão do código for fechada (sucesso ou fracasso) de verdade. |
| Mistura de volatilidade implícita (OpLab) + GARCH histórico | 🔴 ABERTO, confirmado — zero implementação no código. Depende do item de tracking acima pra medir se a mistura realmente melhora algo antes de valer o esforço. |
| **Bandas de Monte Carlo da SPCX34 nova (`an_1785945909`)** | ✅ Preenchidas em 05/08/2026 — `preco_foto` fixo R$39,20 como base, sigma 70,16% (vol. histórica, GARCH não convergiu), períodos 21/29d. |
| **Checagem retroativa de rompimento de barreira (KDO/KUO) em `em_analise`** | ✅ **FECHADO em 05/08/2026.** Backend: `GET /analises/checar-barreiras` (rota somente leitura, nunca escreve em analises.json) reaproveita `_fetch_closes_for_foto` já testada em produção, compara histórico real desde `data_foto` contra kdo/kuo de cada análise `em_analise` com barreira. Frontend: `checarBarreirasRompidas()` roda depois de `renderAnalises()` e injeta selo visual "⚠ BARREIRA ROMPIDA" (vermelho) no card afetado via DOM — puramente aditivo, não alterou `tplAnalise` nem nenhum fluxo de render existente; falha silenciosamente se a chamada der erro, sem quebrar a aba. Validado localmente (test client Flask, bateu com a auditoria manual das 8 análises) e em produção (Render) antes e depois do deploy. Caso real que motivou: MUTC34 (`an_1784737588`).|

**Nota:** os 2 itens de Modelagem marcados ✅ acima estavam listados como pendentes no backlog
antigo (04/08) — auditoria mostrou que já foram feitos em sessões anteriores e a lista nunca foi
limpa. Os outros 2 itens de Modelagem seguem genuinamente abertos.

---

## 📚 Princípios de decisão (permanentes — não reabrir sem novo contexto real)

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
- **Acesso de rede do sandbox do Claude**: histórico era travado em `api.github.com`,
  `raw.githubusercontent.com` e domínios de pacotes (confirmado via teste direto em 05/08/2026 —
  `curl` pra `trader-desk.onrender.com` e `query1.finance.yahoo.com` retornou 403 "Host not in
  allowlist"). **Victor mudou a configuração de rede (Settings → Capabilities → Code execution →
  Domain allowlist) em 05/08/2026 pra liberar mais domínios — vale ATÉ SER TESTADO EM UMA NOVA
  CONVERSA** (mudança de config não se aplica à conversa em andamento no momento da troca, só a
  partir da próxima). Primeira ação de qualquer sessão nova: testar `curl
  https://query1.finance.yahoo.com/v8/finance/chart/PETR4.SA` e `curl
  https://trader-desk.onrender.com/analises` pra confirmar se já libera — se sim, muita coisa
  neste documento sobre "não dá pra calcular GARCH/pegar preço ao vivo daqui" fica obsoleta e o
  Claude pode buscar preço/histórico direto em vez de sempre pedir pro Victor.
- **Estruturas bidirecionais/retorno controlado sempre com PDF oficial do banco presente** —
  nunca cadastrar de memória/estimativa.
- **ROXO34 = id `rx` sempre** (lógica hardcoded no app.js pra cotação/ITM-OTM/Monte Carlo
  Condicional). Nunca criar `rx2` ou variantes em rolagens futuras.
- **`positions.json`**: `tipo_posicao: "barreira"` exige `kdo` E `kuo` numéricos (validador
  rejeita se faltar um dos dois).

---

## 📌 Operações em andamento (checar status ao retomar)

- **BSLV39 (rolagem, 05/08/2026)**: posição antiga encerrada com sucesso (retorno proporcional
  5,7% = 8,3% × 41/60 dias decorridos, confirmado pelo Victor e pelo corretor). Nova posição aberta
  (mesmo id `bslv39`), venc. 05/10/2026, retorno prefixado 8,20%, barreira -20% (KDO R$76,94).
  **`entry` está PROVISÓRIO em R$96,30** (valor assumido a pedido do Victor) — NÃO corrigir por
  conta própria, só quando ele mandar o valor real do boleto de liquidação. Ver `positions.json`
  ativas (`bslv39`) e encerradas (`cl-bslv39-ago26`).
- **SPCX34 (nova, 05/08/2026)**: registrada em Em Análise (`an_1785945909`), status `em_analise`
  (ainda NÃO decidida), preço de referência R$39,20 (papel caiu -8,24% no dia do registro — vale
  reconferir se isso muda a leitura). Retorno prefixado 19,00%/29 dias (MUITO acima do normal,
  vol. implícita alta, BDR de empresa de capital fechado). **Faltam as bandas de Monte Carlo**
  (`bandas_congeladas`) — não deu pra calcular por falta de acesso de rede no momento do registro.
  Se a mudança de rede (ver Princípios de processo acima) já valer na sessão nova, recalcular e
  preencher isso primeiro, antes de mais nada, antes do Victor rodar o ranking de novo.
- **AXIA3 "Proteção Parcial" (`an_1784576725`)**: encerrada de forma neutra em 05/08/2026 (era
  teste, nunca foi decisão real, não conta em stats). Não precisa de ação — só contexto caso o
  Victor pergunte por ela de novo.

| ID | Ticker | Tipo | Exercício | Vencimento | Obs |
|---|---|---|---|---|---|
| pt | PETR4 | simples (call vendida) | europeia | 17/12/2026 | sem meta, objetivo é rollover |
| vl | VALE3 | bidirecional | europeia | 18/02/2027 | sem meta, objetivo é rollover |
| a3b | AXIA3(B) | bidirecional | europeia | 02/10/2026 | entry 50,75 (boleto oficial) |
| a3c | AXIA3(C) | retorno_controlado | europeia | 22/11/2026 | entry 51,68, teto 27,75%, alav. 1,5x |
| bb2 | BBASJ222 (BBAS3) | simples (call vendida, rolagem) | — | 15/10/2026 | strike 21,90, prêmio 1,20 |
| bslv39 | BSLV39 | retorno_controlado | europeia | 05/10/2026 | entry R$96,30 PROVISÓRIO (rolagem 05/08, ver seção Operações em andamento) |
| rx | ROXO34 (ROXOI107) | simples (call vendida, rolagem) | EUROPEIA | 17/09/2026 | meta 2,44%, rolagem defensiva — id SEMPRE `rx` |

**Nota:** AXIA3(A) original (id `a3`) já não está mais em ativas — foi encerrada com sucesso em
20/07/2026 (ver Encerradas abaixo). A tabela antiga desta seção listava ela por engano até
05/08/2026; corrigido nesta atualização.

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

## 🔑 SHAs de referência (buscados frescos em 06/08/2026, fim de sessão — SEMPRE rebuscar antes de editar, nunca reusar estes de memória)
- proxy.py: 4556df91b4d8db6f3750406b841679608eec0f39 (commit, não blob sha — rebuscar sempre)
- fontes.py: 572cb85da788e0fc16edf2cfc39c05f565e97d39 (commit, não blob sha — rebuscar sempre)
- static/app.js: 711b3fc50ada4468b68b840d4b7ce5825c6245d2 (commit, não blob sha — rebuscar sempre)
- analises.json: última escrita foi o encerramento da MUTC34 (13a8314e4462dd477562cc2272611771da8be788, commit)

---

## 📜 Arquivo histórico

Todo o histórico narrativo detalhado de sessões de 02/07/2026 até 04/08/2026 (incluindo saga do DY
de ETFs, incidentes de ThreadPoolExecutor, correções de BSLV39, modularização do proxy.py, etc.)
está preservado em `PROMPT_NOVA_SESSAO_v2.md`, mantido como arquivo morto — não é mais tocado nem
deve ser lido como status atual. Consultar só se precisar entender o raciocínio por trás de uma
decisão antiga específica.
