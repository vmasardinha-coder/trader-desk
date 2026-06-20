# Trader Desk — Prompt de Continuação (v10.0)

## Stack
- Flask no Render: https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk
- Token brapi (gratuito, 15k req/mês): `47g4Z3SJELnK2wLwXgn1rw` — configurado via `Authorization: Bearer` em proxy.py (BRAPI_HEADERS)
- Deploy: GET SHA → PUT base64. HTML em templates/, JS em static/app.js, CSS em static/style.css
- Console de debug: Eruda fica **permanentemente ativo** no index.html (botão flutuante) para validação mobile

## Versão atual: v10.0
SHAs no momento do fechamento desta sessão:
- proxy.py: fab0be4fb984
- templates/index.html: 370c144b38dc
- static/app.js: 7a9ca2ca0bb4
- static/style.css: 66161e091e52
- positions.json: caf6eaa7bb6a

## Estrutura do repositório
```
trader-desk/
├── proxy.py                  # Backend Flask — TODAS as rotas
├── positions.json            # Posições ativas/encerradas (editável sem tocar em código)
├── POSITIONS_GUIDE.md         # Guia de como editar positions.json
├── templates/
│   └── index.html            # HTML com {{ url_for(...) }}
└── static/
    ├── style.css
    └── app.js
```

## Abas do dashboard
1. **Cotações** — B3 Top10, EUA mercados, segmentos B3/EUA (accordion incluindo m7/nq/sp/dj),
   Commodities (com variação real entre ciclos via _prevPrices), Bitcoin
2. **Indicadores** — Bitcoin (accordion único: ciclo+F&G+semanal), watchlist de 16 ativos
   organizada por segmento, cada um com 13 indicadores, 4 metodologias de preço-alvo,
   GARCH(1,1), e fan chart de Monte Carlo
3. **Posições Ativas** — renderizadas 100% via positions.json (templates simples/barreira)
4. **Encerradas** — dashboard de P&L calculado automaticamente do positions.json
5. **FF Calendar** — com filtros de semana/moeda, destaque do dia atual, cron 15min
6. **TV Calendar** — widget iframe TradingView

## Pendências conhecidas (não resolvidas, não são bugs)

### 1. ROXO34 — vence 16/07/2026
Decisão tomada: deixar exercer (não rolar). Quando isso acontecer:
- Mover bloco de `ativas` para `encerradas` no positions.json
- Preencher `pct_do_alvo`, `status`, `resultado_texto`
- Nenhuma alteração de HTML/JS necessária — tudo dinâmico

### 2. Token GitHub expira 14/07/2026
Renovar em Settings → Developer settings → Personal access tokens, scopes `repo` + `workflow`.
Avisar automaticamente quando um PUT falhar por expiração — não precisa lembrete antecipado.

### 3. Fundamentais hardcoded (FUND_OVERRIDE) — data de referência 22/05/2026
16 ativos têm P/L, P/VP, DY, ROE, LPA, VPA hardcoded em proxy.py (constante FUND_DATA_REF).
Aviso visual automático aparece após 90 dias (a partir de ~20/08/2026) na própria tela,
dizendo "Fundamentais com X dias — solicitar revisão trimestral". Quando o usuário reportar
esse aviso: pesquisar de novo via web (Fundamentus, Investfy) e atualizar FUND_OVERRIDE +
mudar FUND_DATA_REF para a nova data.

### 4. EUCA4 incompleto
Só tem DY confiável, sem P/VP/ROE/LPA/VPA (8 indicadores em vez de 13). Não foi encontrada
fonte confiável na pesquisa. Se usuário quiser completar, pesquisar de novo.

## Dados de mercado — fontes por componente
| Componente | Fonte primária | Fallback |
|-----------|---------------|----------|
| B3 cotações | TV scanner brazil | /brapi/ticker -> /indicators (brapi) |
| ROXO34 cotação | /indicators (brapi) | (Yahoo bloqueia no Render) |
| EUA cotações | Hyperliquid (M7) + TV america | Yahoo |
| VIX/DXY/WIN | Yahoo Finance | TV scanner |
| Commodities | Hyperliquid xyz | variação calculada entre ciclos (_prevPrices) |
| BTC preço | Hyperliquid | Yahoo |
| BTC indicadores | Yahoo Finance semanal | Puell/200WMA/Rainbow/PiCycle (MVRV/NUPL removidos) |
| Indicadores B3 fundamentais | brapi com token Bearer | FUND_OVERRIDE hardcoded |
| Monte Carlo | /montecarlo (numpy) + GARCH(1,1) | vol_hist() fixa 21d |
| Calendário | cache/calendar.json (GitHub raw, cron 15min) | - |

## Metodologias de preço-alvo implementadas
Para cada um dos 16 ativos, 4 métodos calculados e comparados:
1. Graham: raiz(22.5 x LPA x VPA)
2. Bazin: (DY x preço_atual) / 0.06
3. P/L Setorial: LPA x P/L_médio_do_setor
4. P/VP Setorial: VPA x P/VP_médio_do_setor

Card mostra os 4 valores + média + indicador de convergência (ok <15% desvio / atenção 15-35% / alerta >35%).
Endpoint /indicators/ticker já calcula tudo, retorna graham_value, preco_alvo_bazin,
preco_alvo_pl_setorial, preco_alvo_vpa + upsides de cada.

IMPORTANTE — limite metodológico conhecido e documentado: esses 4 métodos são "foto do
presente" (múltiplos atuais), não DCF (que projeta fluxo de caixa futuro com premissas
proprietárias — é o que casas de research tipo BTG/XP realmente fazem, e não é replicável
sem dados pagos/subjetivos).

## GARCH(1,1) — implementado em 2 lugares
Função garch_11(closes, horizon_days) em proxy.py — estimação via grid search (sem scipy,
só numpy), captura clusters de volatilidade (memória) em vez de vol. histórica fixa.

Lugar 1 — Posições (Monte Carlo):
- /montecarlo e /montecarlo/barrier usam GARCH para refinar sigma
- Endpoint retorna comparativo_vol_historica mostrando a probabilidade alternativa
  calculada com vol. histórica simples, para comparação lado a lado
- Frontend (MC() em app.js) exibe as duas probabilidades com a diferença em pp

Lugar 2 — Watchlist (Indicadores):
- /indicators/ticker retorna campo garch com vol atual/projetada/longo-prazo
- Exibido como linha extra no card de Convergência de Preços-Alvo

## Fan Chart — Monte Carlo visual (watchlist apenas, por agora)
Endpoint: POST /montecarlo/trajetorias — recebe {ticker, t_days}, retorna:
- trajetorias: ~20 séries de preço dia-a-dia (amostra visual)
- percentis: p10/p25/p50/p75/p90 por dia (de 2000 simulações)
- garch: info do GARCH usado

Frontend: botão "Ver cenários futuros" em cada card da watchlist -> abre seletor
21/60/90 dias -> renderiza gráfico Chart.js (CDN incluído no index.html) com:
- Linhas individuais translúcidas (leque)
- Banda sombreada P25-P75
- Mediana em destaque
- P10/P90 pontilhados
- Frase-resumo didática automática: "Com 80% de confiança, o preço em Nd deve estar
  entre R$X e R$Y. O cenário mais provável é R$Z."

Limite matemático documentado e explicado ao usuário: o modelo GBM usado NÃO tem
reversão de preço — o cone sempre se abre com o tempo (incerteza cresce com raiz do tempo),
nunca "converge de volta". Isso é esperado e correto, não confundir com a convergência dos
4 métodos de preço-alvo (que é um cálculo estático diferente).

NÃO implementado ainda: fan chart nas Posições Ativas (só existe na watchlist por agora —
usuário pediu especificamente para lá).

## Fontes de dados testadas e definitivamente bloqueadas (não retestar sem novidade)
- brapi free: fundamental=true só dá priceEarnings/earningsPerShare. modules= (P/VP,ROE,VPA)
  retorna 403 MODULES_NOT_AVAILABLE. Endpoint de opções retorna 403 FEATURE_NOT_AVAILABLE.
- Yahoo quoteSummary (v10/finance) retorna 401, exige auth agora (mudança recente da política
  Yahoo). Yahoo v8/finance/chart (preço/histórico) continua livre, sem problema.
- OpLab: tem API mas é paga (parte da assinatura).
- Opções.net.br: site público mas exige login para ver números de vol. implícita.
- MVRV/NUPL on-chain: removidos do app — sem fonte gratuita viável encontrada.

Conclusão: vol. implícita real via book de opções NÃO está disponível de graça por nenhuma
via testada. GARCH(1,1) é o substituto estatístico viável sem custo.

## Regras críticas de desenvolvimento
- Sempre fazer backup (ler SHAs + salvar conteúdo local) antes de mudanças estruturais
- Sempre validar antes de deploy: ast.parse() para Python, new Function(code) via node para
  JS, balance de divs via regex para HTML
- Sempre buscar SHA antes de PUT no GitHub (422 sem isso)
- Forçar restart após deploy relevante: trocar comentário de versão no topo do proxy.py e
  fazer outro commit — Render reinicia o processo e limpa _IND_CACHE/_BTC_CACHE em memória
  (cache de 15min não atualiza sozinho, restart resolve na hora)
- NUNCA usar AbortSignal.timeout() — causou tela branca total já 2x nesta sessão (quebra o
  script inteiro se o browser não suportar bem). Usar sempre
  new AbortController(); setTimeout(()=>ctrl.abort(), Xms)
- Verificar balance de divs antes de deploy do index.html (script Python de checagem nas
  sessões anteriores)

## Próximos passos sugeridos (ordem de relevância)
1. Fan chart nas Posições Ativas — estender o que já existe na watchlist para PETR4, VALE3,
   AXIA3, ROXO34, BBAS3, marcando visualmente o strike/KDO/KUO no gráfico
2. Completar EUCA4 — pesquisar P/VP, ROE, LPA, VPA (não encontrados ainda)
3. Revisão trimestral dos fundamentais — só quando o aviso de 90 dias aparecer (a partir de
   ~20/08/2026)
4. Avaliar contexto da "próxima fase mais robusta" — usuário mencionou que vai trazer
   contexto novo para evoluir o projeto além do protótipo atual; aguardar esse briefing
5. Considerar ampliar mais ativos na watchlist

## Aprendizados-chave desta sessão (não repetir os mesmos erros)
- Cache _IND_CACHE/_BTC_CACHE em memória do Python NÃO atualiza sozinho ao fazer deploy —
  sempre forçar restart (bump de versão no comentário do topo + commit) após mudanças que
  afetem o que essas rotas retornam
- brapi free é muito mais limitada do que parece pela doc — testar sempre com fetch direto
  antes de assumir que um campo vai vir
- Yahoo quoteSummary parou de funcionar sem auth — não tentar de novo sem token
- Toda vez que pedir para o usuário rodar fetch() no Eruda para debug, isso testa o endpoint
  EXTERNO direto do browser dele — pode dar erro de CORS que NÃO significa que o backend
  (que chama server-to-server) vai falhar igual. Diferenciar os dois tipos de teste.
