# Trader Desk — Prompt de Continuação

## Stack
- Flask no Render: https://trader-desk.onrender.com
- GitHub: vmasardinha-coder/trader-desk
- Token "Update Claude": ghp_SEU_TOKEN_AQUI (expira 14/07/2026 — URGENTE renovar)
- Deploy: GET SHA → PUT base64. HTML SEMPRE em templates/, JS em static/app.js, CSS em static/style.css

## Versão atual: v9.0 modular (commit d77ef332bf)

## Estrutura do repositório
```
trader-desk/
├── proxy.py                  # Backend Flask puro
├── templates/
│   └── index.html            # HTML com {{ url_for(...) }}
└── static/
    ├── style.css             # CSS separado
    └── app.js                # JS separado
```
Flask usa render_template() + url_for('static', filename=...)

## Abas do dashboard
1. **Cotações** — B3 Top10, EUA mercados, segmentos B3/EUA (accordion), Commodities, Bitcoin
2. **Indicadores** — BTC ciclo, BTC semanal, Fear&Greed, acordeons por ativo (PETR4/VALE3/BBAS3/AXIA3/ROXO34)
3. **Posições Ativas** — PETR4, VALE3, AXIA3(A), AXIA3(B), ROXO34, BBAS3
4. **Encerradas** — AXIA3 Short Strangle, ROXO34 Prefixado 7,1%, BBAS3 anterior
5. **FF Calendar** — Forex Factory via GitHub Action (cache/calendar.json, atualiza a cada hora)
6. **TV Calendar** — Widget iframe TradingView

## Posições ativas
| Ativo   | Estratégia            | Parâmetros                        | Venc       | Dias |
|---------|-----------------------|-----------------------------------|------------|------|
| PETR4   | Call Vendida PETRL319 | Strike R$30,85                    | 17/12/2026 | 183  |
| VALE3   | Call Vendida VALEB574 | Strike R$57,40                    | 18/02/2027 | 246  |
| AXIA3 A | Bidirecional          | KDO R$43,51 / KUO R$68,76         | 14/09/2026 | 89   |
| AXIA3 B | Bidirecional ION      | KDO R$40,52 / KUO R$62,81         | 02/10/2026 | 107  |
| ROXO34  | Call Vendida ROXOG105 | Strike R$10,50 · ITM · B&S 71,8% · Delta 0,748 | 16/07/2026 | 29 |
| BBAS3   | Call Vendida BBASH21  | Strike R$21,65 · OTM · B&S 20,97% · Delta 0,244 | 20/08/2026 | 64 |

Dias são calculados dinamicamente (Math.ceil). MC também usa dias calculados — não hardcoded.
NUNCA mostrar quantidades ou valores financeiros.

## Encerradas (não reabrir como ativas)
- AXIA3 Short Strangle AXIAI505 R$50,50 — ações liberadas
- ROXO34 Prefixado 7,1% — encerrada 04/06/2026, ~5,17% (72% do alvo)
- BBAS3 anterior — 80% do alvo em 70% do prazo

## Calendário FF
- GitHub Action roda toda hora → cache/calendar.json (104 eventos, semana atual + próxima)
- Proxy lê de raw.githubusercontent.com
- JS chama loadCal() ao abrir a aba pela primeira vez (window._CL flag)
- Botão Atualizar faz window.location.reload()
- actual dos eventos chega com delay de até 1h da FF — comportamento normal

## Dados de mercado
- **B3 tickers**: TV scanner (BMFBOVESPA:TICKER) + fallback /indicators (brapi)
- **ROXO34**: sempre via /indicators/ROXO34.SA (brapi) — Yahoo bloqueia no Render
- **VIX/DXY**: Yahoo Finance via /futures
- **WIN**: TradingView futures scanner
- **EUA**: Hyperliquid allMids (M7+) + TradingView america scanner
- **Commodities**: Hyperliquid xyz:CL/GOLD/SILVER/COPPER
- **BTC**: Hyperliquid allMids + Yahoo semanal para indicadores

## Tickers removidos (404 no TV scanner)
Removidos dos segmentos: JBSS3, BRFS3 (cn), EMBR3 (ind), TOTVS3 (tit), MRFG3 (cn)
Substitutos: SMTO3, MRVE3, FRAS3, IFCM3

## Indicadores B3 (/indicators/<ticker>)
- Fonte: brapi.dev com range=1y (252 pregões — necessário para MM200)
- Fallback: Yahoo Finance range=2y, depois 1y
- Cache: 5min por ticker
- Indicadores: RSI(14), MM20, MM50, MM200, P/L, P/VP, DY, ROE, Graham, LPA, VPA, MACD, Bollinger, EV/EBITDA, Div/EBITDA, Margem Liq.
- MM200 aparece apenas quando há 200+ dias de dados

## Monte Carlo
- **MC()** — call simples: PETR4, VALE3, BBAS3. Usa /montecarlo endpoint.
- **MCB()** — barreira: AXIA3 A e B. Usa /montecarlo/barrier endpoint.
- **MCR()** — ROXO34: busca preço via /indicators antes de chamar /montecarlo (Yahoo bloqueia ROXO34.SA)
- Todos os prazos calculados dinamicamente de new Date()
- Timeouts: MC/MCR=40s, MCB=25s

## Problema raiz do layout (RESOLVIDO)
O container `<div class="grid" id="g-xxx">` tinha `display:grid;grid-template-columns:repeat(3,1fr)`
comprimindo as tabelas para ~213px. Fix: loadSeg() agora remove a classe 'grid' e define
display:block antes de injetar a tabela. Colgroup com larguras 40/20/20/20% + table-layout:fixed.

## Regras críticas de desenvolvimento
- **NUNCA triple-quotes para HTML** — usar render_template()
- **Sempre ast.parse() antes de deploy**
- **Sempre buscar SHA antes de PUT no GitHub**
- **Verificar balance de divs** antes de qualquer deploy do index.html:
  ```python
  import re
  tabs = [('tab-cotacoes','tab-indicadores'),('tab-indicadores','tab-posicoes'),
          ('tab-posicoes','tab-encerradas'),('tab-encerradas','tab-tvcal'),
          ('tab-tvcal','tab-calendario'),('tab-calendario','</body>')]
  for t1,t2 in tabs:
      s=html.find(f'id="{t1}"'); e=html.find(f'id="{t2}"') if t2!='</body>' else html.rfind('</body>')
      d=sum(1 if m.group(1)=='' else -1 for m in re.finditer(r'<(/?)(div)',html[s:e]))
      print(f"{t1}: {'✅' if d==0 else f'❌ {d}'}")
  ```
- **Cada sessão termina com upload para GitHub**

## Próximos passos sugeridos
1. **ROXO34 vence 16/07** — 22 dias, ITM. Decisão de rolar ou deixar exercer urgente.
2. **Token GitHub expira 14/07** — renovar antes.
3. **Vol.Impl./Delta/B&S hardcoded nas posições** — criar rota /bs/<ticker> para calcular em tempo real.
4. **Rota /brapi/<ticker>** — endpoint dedicado para tickers problemáticos no TV scanner.
5. **Cron do calendário FF para 15min** — reduzir delay dos "actual".
6. **Alerta de barreira AXIA3** — destacar em vermelho quando < 5% do KDO/KUO.
7. **Cache /indicators aumentar para 15min** — brapi com range=1y demora mais.
8. **BBAS3 B&S desatualizado** — Vol.Impl. 26.2% hardcoded pode estar errado.
