# Trader Desk — Prompt de Continuação (v13.0 — sessão 30/06/2026)

## Stack
- Flask no Render (free tier): https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk (branch: main)
- Token GitHub de SESSÃO (Claude usa em chat, colado pelo usuário): classic, escopo `repo`, válido 90 dias a partir de 30/06/2026
- Token GitHub de ESCRITA AUTOMÁTICA (app usa sozinho): fine-grained, restrito SÓ ao repo trader-desk, permissão "Contents: Read and write", configurado como `GITHUB_TOKEN` no Render. **PENDÊNCIA: criar token fine-grained sem vencimento curto para substituir o atual (processo: GitHub → Settings → Developer Settings → Fine-grained tokens → só trader-desk → Contents R/W)**
- Deploy: GET SHA → PUT base64 via API do GitHub. HTML em templates/, JS em static/app.js
- Console de debug: Eruda ativo no index.html para validação mobile
- **REGRA CRÍTICA DE PROCESSO**: usar `api.github.com/repos/.../contents/...` para ler arquivos que foram editados NA MESMA sessão — nunca `raw.githubusercontent.com` para isso (CDN cache causa leituras desatualizadas e pode reverter mudanças ao re-editar)

## SHAs no fechamento desta sessão (30/06/2026)
- proxy.py: 01056047ecb4b0755f3a5f4d1c30e36048969d2d
- static/app.js: c6c0e554adefbb2ca1d4f1026392ded236393643
- templates/index.html: ddfdfc00ef9755f83d13e7722337581eceba527f
- positions.json: 8abde67a3dc6d59be1b9586dd23f05abf9fb95eb (7 posições ativas)
- analises.json: bfb7b70fcbeab1a95aae2844c83682bf51ec6d58 (22 registros)
- carteira_fiis.json: 7cac5d8262a2ad419783f7f03ccad198ba905243
- fotos_papel.json: criado nesta sessão (via endpoints /foto-papel)

## ⚠️ Regras críticas de processo

### 1. Fase A / Fase B (ver FLUXO_FASE_A_FASE_B.md no repo)
**Fase A** (pré-análise, sempre em chat): 4 números-chave em aberto (ticker, prazo, strike/range, prêmio). **Fase B** ("tirar a foto", grava em analises.json) só depois dos 4 números fechados. Se algum estiver vago, Claude DEVE questionar antes de prosseguir.

### 2. PDFs de propostas reais do banco — NUNCA recalcular
Números do PDF (ganho prefixado, barreira, teto, alavancagem) são PREMISSA FIXA. Só o vencimento muda: (a) se ainda não passou, usa prazo restante real com os MESMOS números; (b) se já passou, simula o MESMO prazo total a partir de hoje com os MESMOS números.

### 3. Régua de decisão para bidirecionais — 1%/mês proporcional ao prazo
Só aceita bidirecional se teto de retorno ≥ ~1%/mês × prazo (ex: 30d→1%, 90d→3%). Vale só para decisões NOVAS a partir de 22/06/2026.

### 4. Apresentação de grades de opções — sempre os 2 lados
Quando o usuário manda grade do OpLab (PUT e CALL), sempre analisa e apresenta AMBOS os lados (call coberta E put vendida), mesmo que só um tenha sido pedido.

### 5. Mecânica americana vs. europeia
Campo `exercicio` ('americana'|'europeia') obrigatório em chamadas a `/montecarlo`, `/montecarlo/condicional`, `/montecarlo/posicao_ativa` com `k_call`/`k_put` sem `kdo`/`kuo`. Das posições ativas: SÓ ROXO34/ROXOG105 é americana; PETR4, VALE3, BBAS3, AXIA3(A), AXIA3(B), BSLV39 são europeias.

### 6. NUNCA inventar dados
vol_impl=null explícito se GARCH falhar, cotação=null se scraping falhar. Nunca fallback fixo (0.35 ou qualquer outro número inventado).

### 7. Fluxo de análise de lote (Fase A automática)
Quando usuário traz planilha "Index/Fixing/Strike/KO/Delta" ou PDFs do banco: 1º filtro retorno mensal >2% (eliminatório), 2º KO (proteção), 3º DY >8% (desempate). EV = retorno × Delta para desempate entre combinações do mesmo ativo. Apresentar tabela completa com TODAS as linhas, não esconder nada.

## O que o app faz hoje (estado atual)

### Abas e funcionalidades
- **Cotações**: mercados EUA/B3/Europa/Ásia, commodities (WTI/Brent/Gás/Ouro/Prata/Cobre/Minério de Ferro via TradingView FEF1!), índices (VIX/DXY), câmbio (USD/BRL/EUR/BRL/BTC), grupos EUA por segmento (Semi/M7/Software com métrica de concentração no S&P 500), calendário econômico. **NOVO 30/06**: seção "📈 Juros Soberanos" (T-Bill 3M/T-Note 10Y/T-Bond 30Y/JGB 10Y/USD-JPY/SELIC).
- **Papéis** (antes "Indicadores"): watchlist com ~17 ativos, 4 métodos de valuation (Graham/Bazin/P/L/P/VP), fan chart Monte Carlo, **NOVO 30/06: "📸 Foto do Papel"** — congela bandas GARCH 21/60/90d, acompanha preço real vs bandas, score de assertividade, auto-expira em 90 dias úteis, reseta manualmente ou automaticamente. Storage: fotos_papel.json no repo.
- **FIIs**: screening de 591 fundos (560 Fundamentus + 31 FI-Infra/FIP-IE via Investidor10), critério P/VP→DY→liquidez, classificação High Grade/Middle Risk/High Yield, busca por texto, visão Todos vs Critério.
- **Carteira FIIs**: FIIs ativos com preço/DY de ativação, último provento (via StatusInvest), **NOVO 30/06: colunas "Últ. Prov." e "12M (R$)"** carregadas assincronamente via /carteira-fiis/proventos.
- **Em Análise**: estruturadas (ranking Monte Carlo com EV completo, botões Rejeitar/Ativar) + FIIs em análise (seção separada, ranking próprio com critério P/VP/DY/FFO). Migração automática Em Análise→Ativas (retorno_controlado/bidirecional) via /analises/<id>/status.
- **Posições Ativas**: 7 posições (PETR4/VALE3/AXIA3-A/AXIA3-B/ROXO34/BBAS3/BSLV39), fan chart retroativo + projeção, simulação 100 ações, faixas de retorno.
- **Encerradas**: histórico estático de análises (rejeitadas/encerradas) e posições.

### Motor estatístico
- GARCH(1,1) via grid search (sem scipy) — em produção em /montecarlo, /montecarlo/barrier, /indicators, /foto-papel
- Monte Carlo com n_sim=20000, horizonte até 90d (cuidado com memória no free tier: máx ~15-20 análises por chamada do ranking)
- EV completo no score do ranking: pondera todos os cenários via prob_retorno_faixas
- Fan chart: percentis p10/p25/p50/p75/p90, retroativo real (Yahoo) + projeção

### Segurança
- Token de API (`API_WRITE_TOKEN` no Render) protege rotas de escrita (POST/PUT/DELETE)
- Frontend pede token via prompt() uma vez por dispositivo, salva em localStorage
- Disclaimer CVM implementado (modal na primeira visita + botão no rodapé)

## Posições ativas atuais (positions.json)
| ID | Ticker | Tipo | Exercício | Data entrada est. | Obs |
|---|---|---|---|---|---|
| pt | PETR4 | bidirecional | europeia | ~15/03/2026 | objetivo: rollover/recompra, SEM meta de ganho |
| vl | VALE3 | bidirecional | europeia | ~04/02/2026 | objetivo: rollover/recompra, SEM meta de ganho |
| rx | ROXO34 | simples (call vendida) | americana | ~03/06/2026 | meta_pct: 2.25, venc 16/07/2026 |
| bb | BBAS3 | retorno_controlado | europeia | ~03/06/2026 | meta_pct: 2.25 |
| a3 | AXIA3(A) | bidirecional | europeia | ~16/05/2026 | entry ~54.31 |
| a3b | AXIA3(B) | bidirecional | europeia | ~08/06/2026 | entry ~50.65 |
| bs | BSLV39 | retorno_controlado | europeia | ~26/06/2026 | vol_impl=null (histórico insuficiente no Yahoo para BDR de prata) |

## Carteira FIIs (carteira_fiis.json) — ativos confirmados
KNCR11, ITRI11, KNCA11, BDIF11, CDII11, e outros (verificar arquivo real).

## Universo FII coberto
- FII tradicional: ~560 via Fundamentus (Papel/Tijolo/Híbrido/FoF/Fiagro)
- FI-Infra + FIP-IE temático: ~31 via Investidor10 individual (CDII11, KNDI11, BDIV11, XPIE11, DIVS11, VIGT11, BRZP11, ENDD11, GTIS11, PICE11, PPEI11 + outros FI-Infra)
- FIP genérico / FIDC: FORA DO ESCOPO por decisão deliberada do usuário

## Pendências ativas (próximas sessões)
1. **Token GitHub fine-grained no Render** — substituir token atual (válido 90 dias) por PAT fine-grained sem vencimento curto (só trader-desk, Contents R/W). Processo: GitHub → Settings → Developer Settings → Fine-grained tokens.
2. **Layout da Foto do Papel** — adicionar bandas p10/p90 visíveis com legenda de confiança no gráfico (como o fan chart do Monte Carlo que mostra "80% de confiança"), não só a mediana.
3. **Bulk foto** — botão para tirar foto de todos os papéis da watchlist de uma vez.
4. **Foto automática na Em Análise** — quando uma análise é criada, congelar as bandas naquele dia; gráfico acompanha preço real por cima sem recalcular (mesmo conceito da Foto do Papel, aplicado à Em Análise).

## Backlog de médio prazo (sem prioridade definida, decidir a cada sessão)
- Histórico mensal completo de dividendos na Carteira FIIs (hoje só último provento + total semestral via 2 semestres; histórico mensal real exigiria scraping de proventos individuais não disponível server-side no StatusInvest)
- Teto de análises por chamada do ranking (15-20, não fechado) + faseamento no frontend
- ETFs (mapear universo com cuidado, lição do FI-Infra)
- Encerradas para FIIs (comportamento não definido)
- Visão multi-usuário (só se virar produto)
- Renda fixa (só registro, sem ação)

## Princípios técnicos estabelecidos
- **Modelagem de volatilidade**: GARCH(1,1) grid search = MLE contínuo (scipy) em todos os testes. Heston inviável sem book de opções. Jump-Diffusion (Merton): estudo futuro, baixa prioridade. Vol realizada intraday: potencialmente útil mas fonte gratuita para B3 não confirmada.
- **Scraping**: sempre validar estrutura real via endpoint de debug antes de implementar. Nunca assumir que HTML visto em web_fetch = HTML bruto que requests.get() recebe (JS pode renderizar campos dinamicamente). Investidor10/FAQ e StatusInvest/server-side são as fontes confiáveis validadas.
- **Preço de foto impreciso**: usuário compara visualmente e rejeita/re-pede ao banco se diferença for grande — não auditoria automática.
- **Tipos de estrutura**: retorno_controlado e bidirecional migram automaticamente (Em Análise → Ativas); 'simples' nunca passa por esse fluxo (decidido em chat, nasce já analisado).
- **Próxima reunião COPOM**: 05/08/2026. SELIC meta atual: 14,25% (COPOM 17/06/2026). Atualizar fallback hardcoded em get_cdi() após cada decisão.
- **Fundamentais hardcoded** (`FUND_DATA_REF` em proxy.py): ref. 22/05/2026. App mostra aviso visual automático após 90 dias. Quando usuário reportar esse aviso, atualizar via web search.


## Fluxo de análise de lote com PDFs do banco (Fase A)

### Como decodificar a planilha "Index/Fixing/Strike/KO/Delta"
Propostas fechadas do banco (Retorno Controlado prontas). Colunas:
- **Fixing**: data de VENCIMENTO
- **Strike**: RETORNO da estrutura em % do valor inicial (ex: "101,02%" = retorno de 1,02%, subtrair 100)
- **KO**: nível de PROTEÇÃO/barreira de baixa em % do valor inicial (ex: "82,00%" = proteção até cair 18%)
- **Delta**: probabilidade de o cenário bom se realizar (informação secundária na decisão)

### Ordem de critérios (aplicar nesta ordem)
1. **Retorno mensal > 2%** (eliminatório): retorno_mensal = (Strike% - 100) / (dias_corridos_até_fixing / 30.4). Se não passa, descartado — não importa KO nem Delta.
2. **KO** (proteção): quanto mais funda, melhor — só entra na decisão após passar no 1º filtro.
3. **DY > 8%** (desempate): se barreira romper, usuário fica com o papel. DY alto = colchão enquanto espera recuperar. ADRs/BDRs sem dividendo (ROXO34/TSLA34/BSLV39/AMZO34/NVDC34) sempre DY=0%, é esperado.
- **EV = retorno × Delta**: desempate entre combinações do mesmo ativo com fixing diferente.

### PDFs do banco (Material Publicitário do Itaú) — REGRA ABSOLUTA
- Aceitar todos os números como PREMISSA FIXA: ganho prefixado, barreira, teto, alavancagem. **NUNCA recalcular, NUNCA reescalar proporcionalmente ao tempo.**
- A ÚNICA coisa que muda é o vencimento: (a) se ainda não passou → usa prazo restante real com os MESMOS números; (b) se já passou → simula o MESMO prazo total a partir de hoje com os MESMOS números.
- Estrutura típica de bidirecional Itaú (3 pernas): 1 put com KDO (proporção 2x) + 1 call com KUI + 1 call com KUO. SEM desembolso de prêmio na largada — ganho embutido no payoff, realizado só no encerramento.

### Entregável esperado
Tabela completa com TODAS as linhas (inclusive as que não passam nos critérios), ordenada por retorno mensal decrescente. Colunas: origem, ativo, fixing, dias, meses, retorno%, retorno_mensal%, passa_retorno_2pct, KO%, proteção%, Delta%, DY%, passa_dy_8pct. Usuário filtra/decide por conta própria — Claude NÃO decide quais avançar para Fase B sem o usuário escolher explicitamente.

### Bidirecionais — tratamento separado do ranking de Retorno Controlado
Risco assimétrico diferente: sem piso garantido na queda se romper barreira baixa. Avaliar como ESTUDO SEPARADO do ranking principal.
