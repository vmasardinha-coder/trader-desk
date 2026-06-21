# Trader Desk — Prompt de Continuação (v10.4 → Fase 2 em andamento)

## Stack
- Flask no Render: https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk
- Token brapi (gratuito, 15k req/mês): configurado via `BRAPI_HEADERS` em proxy.py
- Token GitHub de ESCRITA MANUAL (Claude usa em sessão): classic, escopo `repo`+`workflow`, expira 14/07/2026 — RENOVAR ANTES DESSA DATA
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho): fine-grained, restrito SÓ ao repo trader-desk, permissão SÓ "Contents: Read and write", configurado como variável de ambiente `GITHUB_WRITE_TOKEN` no painel do Render — criado em 21/06/2026, conferir validade/expiração periodicamente
- Deploy: GET SHA → PUT base64 via API do GitHub. HTML em templates/, JS em static/app.js, CSS em static/style.css
- Console de debug: Eruda permanece ativo no index.html para validação mobile

## SHAs no momento do fechamento desta sessão (21/06/2026)
- proxy.py: bab4eb04a584
- templates/index.html: 1a9028a08b24
- static/app.js: 7721b60435bc
- static/style.css: cacb029f00b7
- positions.json: caf6eaa7bb6a (não tocado nesta sessão)
- analises.json: fe51488c7066 (criado nesta sessão, atualmente `[]`)
- montecarlo_garch.py: 31bdb9470821 (novo, módulo reutilizável)
- FLUXO_FASE_A_FASE_B.md: a746c590465e (novo, regra de processo)

## ⚠️ Regra crítica de processo — ler antes de qualquer coisa sobre "Em Análise"
Ler o arquivo `FLUXO_FASE_A_FASE_B.md` no repo (ou a memória equivalente).
Resumo: existem 2 fases. **Fase A** (pré-análise, sempre em sessão de chat,
nunca via botão) é onde os 4 números-chave (ticker, prazo, strike/range,
prêmio) ainda estão em aberto — Claude ajuda a estimar prêmio e filtrar
candidatas. **Fase B** ("tirar a foto", grava em analises.json) só
acontece DEPOIS que os 4 números estão genuinamente fechados. Se o
usuário pedir para tirar uma foto com algum número ainda vago, Claude
DEVE questionar antes de prosseguir, não aceitar de cara — é proteção
pedida explicitamente pelo usuário contra a própria falta de disciplina
de pular etapas.

## O que mudou nesta sessão (21/06/2026) — resumo cronológico

### 1. Correção do desalinhamento de versões (início da sessão)
Os arquivos mirrorados no Claude Project estavam desatualizados (refletiam
~v9.0). Confirmado que o GitHub `main` é a fonte de verdade real (v10.0+).
**Lição**: sempre buscar direto de `raw.githubusercontent.com/.../main/{arquivo}`
via bash_tool antes de assumir que arquivos de Project/contexto são atuais.

### 2. Cards "MC GARCH" nas posições (várias iterações até o formato final)
Layout final, validado pelo usuário: nas posições simples (PETR4, VALE3,
BBAS3, ROXO34), o bloco de informações tem 3 linhas no estilo padrão
(`.sr`/`.sl`/`.sv`, igual Strike/Delta):
- "Prob. B&S exercer"
- "Prob. MC exercer (Vol.Simples)" — cor por faixa de risco
- "Prob. MC exercer (GARCH)" — cor por faixa de risco
- "Vol. Simples / GARCH" — as duas vols juntas numa linha (ex: "22.6% / 26.3%")
O bloco "🎲 Monte Carlo" abaixo ficou SÓ com texto explicativo (sem cards
visuais — usuário testou com cards e pediu para reverter para linhas).
AXIA3 (barreira) manteve os 4 cards como estavam; o comparativo
GARCH-vs-Vol.Simples aparece só no texto da legenda, por decisão explícita
do usuário (não duplicar os 3 cards de probabilidade em 6).

### 3. Bug real corrigido: ROXO34 nunca calculava GARCH
Causa raiz (não foi a primeira tentativa — teve 2 rodadas de debug via
Eruda até achar): quando o payload de `/montecarlo` já vem com `price`
(caso do ROXO34, bloqueado no Yahoo via Render), a busca de histórico
(`cl`) era pulada inteiramente. Sem `cl`, GARCH nunca rodava. Corrigido
adicionando fallback via brapi (`range=3mo` — plano free NÃO permite
`range=1y`, dá erro 400 silencioso se tentar) quando isso acontece, e
reduzindo o limiar mínimo de pontos do GARCH de 60 para 50 nesse caminho
específico (brapi 3mo só dá ~60-65 pontos, pouca margem).

### 4. Fan chart de BTC na aba Indicadores (2 gráficos novos)
- `/btc/historico` (novo endpoint): fan chart RETROATIVO — simula a partir
  do preço de N dias atrás com a vol. conhecida NAQUELE momento (sem olhar
  o futuro), sobrepõe a linha real observada. Botões 90/180/365 dias.
- Reaproveita `/montecarlo/trajetorias` (já existia) para o fan chart
  FUTURO de BTC. Botões 30/90/180 dias.
- Ambos na seção "Bitcoin — Ciclo & Indicadores" da aba Indicadores.

### 5. EUCA4 completo
LPA, VPA, ROE, P/L preenchidos via Fundamentus (ref. 19/06/2026); P/VP e
DY também atualizados (estavam desatualizados, de uma data anterior).
Watchlist agora tem 13 indicadores completos em todos os 16 ativos.

### 6. Cache-busting automático
`proxy.py` calcula hash MD5 (8 chars) do conteúdo real de app.js/style.css
em tempo de request (`_asset_version()`), passado ao template como
`?v={hash}`. Resolve o problema de o Safari servir versão antiga do JS ao
reabrir aba pelo histórico (causa raiz de um bug real que travou os
botões do BTC por um tempo nesta sessão — diagnosticado via Eruda mostrando
`ReferenceError: Can't find variable`).

### 7. Responsividade desktop
- `body`: `max-width: clamp(1100px, 92vw, 1800px)`, `font-size: clamp(14px, 0.95vw, 17px)`
- Grid de cards: `auto-fit, minmax(150px, 1fr)` em vez de 3 colunas fixas
- Gráficos (fan chart watchlist + BTC): altura `clamp(300px, 36vh, 480px)`
- `zoom: 1.3` aplicado só em `@media(min-width:900px)` — aumenta tudo ~30%
  em desktop sem afetar mobile. Testado/validado em Edge/Chrome (não se
  preocupar com Firefox, é minoria do uso real do usuário).

### 8. Ajuste UI watchlist
Card de destaque principal trocou de "Graham VJ" isolado para "Méd. 4
Métodos" (média de Graham + Bazin + P/L Setorial + P/VP Setorial). Graham
continua aparecendo no bloco de convergência abaixo, junto dos outros 3.

### 9. Módulo reutilizável extraído (Sprint 2 da Fase 2)
`montecarlo_garch.py` e `montecarlo_garch_GUIA.md` na raiz do repo —
núcleo de `vol_hist`, `garch_11`, e as 4 formas de simulação Monte Carlo
(simples, barreira, fan chart, condicional), sem NENHUMA dependência de
Flask/HTTP/Trader Desk. Testado isoladamente, funciona como import puro.
Usuário vai usar isso em outro projeto Python; ele não vai revisar o
conteúdo, a integração é por conta do Claude quando chegar a hora.

### 10. Estudo de modelos avançados de volatilidade — ENCERRADO
Comparado GARCH(1,1) atual contra Jump-Diffusion (Merton) e Heston (vol.
estocástica) com simulações reais (PETR4/VALE3/AXIA3). Resultado:
- Jump-Diffusion: diferença de -0.7pp a -6.8pp vs GARCH puro — calibrável
  só com histórico de preço. FICA COMO ESTUDO FUTURO, sem prioridade.
- Heston: diferença de -2.3pp a -13.0pp — faixa muito mais larga (mais
  sensível a parâmetros chutados), exige dados reais de book de opções
  para calibrar corretamente. CONSIDERADO NÃO VIÁVEL sem fonte paga.
- Calibração mais rigorosa do GARCH atual (MLE contínuo via scipy vs.
  grid search): testado em 5 cenários sintéticos, diferença na vol.
  projetada final foi 0.00pp em TODOS os casos. NÃO VALE A PENA refinar.
**Conclusão do usuário, registrada e fechada**: considera ter atingido
maturidade razoável de modelagem gratuita sem book de opções. Não seguir
adiante com mais refinamento de volatilidade a menos que surja fonte paga
de dados ou novo contexto.

## FASE 2 — Motor de decisão pré-trade (em andamento)

### Objetivo
Virar de "monitor de posições" (maduro) para "motor de decisão
pré-trade". Fluxo completo: Watchlist/Indicadores → "Em Análise" (foto
congelada) → Ativas → Encerradas. Ver `FLUXO_FASE_A_FASE_B.md` para a
regra de quando uma foto pode ser criada.

### Já implementado (backend funcionando e testado em produção)
- **`/montecarlo/condicional`** (POST): recebe `ticker`, `preco_foto`,
  `data_foto`, `prazo_dias`, e (`k_call`/`k_put` OU `kdo`/`kuo`). Calcula
  dias_passados, dias_restantes, busca preço ATUAL real (Yahoo→brapi
  fallback), recalcula GARCH com dados de hoje, simula com horizonte =
  tempo que resta. Testado com dados reais do Itaú via Eruda — funciona.
- **`analises.json`** criado no repo (atualmente vazio, `[]`).
- **`GET /analises`**: lê tudo, público via raw.
- **`POST /analises`**: cria nova foto. Valida campos obrigatórios
  (`id, ticker, nome, data_foto, preco_foto, prazo_dias, tipo_estrutura,
  origem, status`), força `status='em_analise'`, gera `id` automático
  (`an_{timestamp}`). Escreve via API do GitHub usando `GITHUB_WRITE_TOKEN`.
- **`PUT /analises/<id>/status`**: move entre estágios
  (`em_analise`/`ativa`/`encerrada`). Valida status, trata ID inexistente
  (404). Testado em produção via Eruda — confirmado escrevendo de fato no
  GitHub, sozinho, sem intervenção manual.
- Helpers `_github_get_file()`/`_github_put_file()`: genéricos, fazem
  GET-SHA→PUT em qualquer arquivo do repo via API autenticada.

### Schema confirmado da "foto" (analises.json, cada item)
```json
{
  "id": "an_1782076714",
  "ticker": "ITUB4.SA",
  "nome": "Itau Unibanco PN",
  "data_foto": "2026-06-21",
  "preco_foto": 39.87,
  "prazo_dias": 21,
  "tipo_estrutura": "simples",
  "k_call": 39.0,
  "origem": "customizada",
  "status": "em_analise"
}
```
Campos condicionais dependendo de `tipo_estrutura`: `k_call`/`k_put`
(simples/retorno_controlado) OU `kdo`/`kuo` (bidirecional). Valores
válidos: `tipo_estrutura` ∈ {bidirecional, retorno_controlado, premio,
simples}; `origem` ∈ {customizada, pronta}; `status` ∈ {em_analise,
ativa, encerrada}.

### Regra de negócio importante (memorizar)
Só conta nas métricas de assertividade (P&L, taxa de sucesso) o que
passou por `ativa` ou foi `encerrada` como decisão real. O que ficou só
`em_analise` e nunca evoluiu NÃO conta nas estatísticas, mas o
histórico/log permanece guardado (nunca apagar registros, só mudar status).

### Pendente — próximos passos (Sprint 4 e 5)
1. **Sprint 4 — Aba "Em Análise" no frontend**: nova aba na navegação,
   listando os itens com `status=em_analise`, formulário para criar nova
   foto (chamando `POST /analises`), botão para mover para `ativa` ou
   `encerrada` (chamando `PUT /analises/<id>/status`), e visualização
   gráfica chamando `/montecarlo/condicional` para mostrar a probabilidade
   atualizada — no mesmo estilo visual do fan chart histórico de BTC
   (linha real sobreposta à banda original projetada).
2. **Sprint 5 — Integração com Ativas**: quando uma análise migra para
   `ativa`, o card da posição correspondente (se ela "nascer" desse fluxo)
   ganha uma 4ª linha/gráfico mostrando a evolução desde a foto. Só vale
   para posições NOVAS nascidas desse fluxo — as 5 atuais (PETR4/VALE3/
   AXIA3/ROXO34/BBAS3) não precisam disso retroativamente.

## Backlog — sem ação agora, mas anotado
- Tornar Cotações/Indicadores públicos (sempre grátis); Posições em
  Análise/Ativas privadas; Encerradas pode futuramente abrir para
  visitantes "copiarem" via doação/apoio, sem recomendação formal —
  discutir modelo de monetização/disclaimer legal no futuro.
- Bot operando mini-contratos futuros (dólar/índice) automaticamente —
  fora de escopo, mencionado como fase muito mais distante.
- Investigar e corrigir as 4 falhas recentes do workflow
  `.github/workflows/update_calendar.yml` (notificações do GitHub
  mostraram falhas nos últimos 4-5 dias). Usuário colou um trecho de YAML
  com lógica duplicada (2 blocos de curl, 2 métodos de filtro) que pode
  ser causa raiz — não investigado a fundo ainda nesta sessão.
- EUCA4 está completo agora; não há mais "ativo incompleto" pendente na
  watchlist de 16.
- Revisão trimestral dos fundamentais (FUND_DATA_REF ainda em 22/05/2026
  para 15 dos 16 ativos — só EUCA4 foi atualizado para 19/06/2026 nesta
  sessão). Aviso automático de 90 dias dispara a partir de ~20/08/2026.

## Aprendizados-chave desta sessão (não repetir os mesmos erros)
- **Sempre validar sintaxe (ast.parse / new Function / Acorn) ANTES do
  deploy**, mesmo em edições que parecem triviais — nesta sessão, pelo
  menos 2 erros de sintaxe reais (declaração de função duplicada, divs
  desbalanceadas aparentes) só foram pegos porque a validação rodou antes
  do PUT, não depois.
- **Cache do navegador (não cache do servidor) pode simular um bug que
  não existe no código.** Quando "os botões não funcionam" mas o código
  está correto e validado, suspeitar de cache do Safari/navegador antes
  de caçar bug em lugar errado — usar Eruda Console para ver o erro real
  (`ReferenceError`, etc.) é o jeito mais rápido de diferenciar os dois.
- **Testar com mock de rede antes de assumir que uma chamada de API
  externa vai funcionar como esperado.** O bug do ROXO34 (Yahoo bloqueado
  → fallback brapi) só foi resolvido depois de usar o Eruda para ver a
  resposta REAL do servidor (`debug_brapi` temporário) — a brapi rejeitou
  `range=1y` com erro 400 que estava sendo engolido silenciosamente por
  um `except: pass` genérico demais.
- **Sandbox de teste (bash_tool) não tem acesso a `brapi.dev` nem
  `api.github.com` sem token/allowlist** — só `raw.githubusercontent.com`
  e domínios da allowlist. Para testar lógica que depende dessas APIs,
  usar mocks (`requests.get` monkeypatched) localmente, e confirmar o
  comportamento real em produção via Eruda quando precisar de certeza.
- **Token de escrita automática (GITHUB_WRITE_TOKEN) é fine-grained,
  restrito a 1 repo, só permissão Contents** — não confundir com o token
  classic que Claude usa manualmente em sessão (esse tem escopo `repo`
  completo, mais amplo, mas só existe durante a sessão, nunca fica
  armazenado em lugar nenhum persistente).
