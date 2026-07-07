# Rotina de Análise de Lote — Gates (v1, criada 06/07/2026)

**O que é isto:** não é uma feature do site. É uma rotina que o Claude segue
sempre que o usuário cola um lote de opções aqui no chat (do banco, do OpLab,
ou qualquer fonte) para análise pré-trade (Fase A). Documentada aqui para
persistir entre sessões, do mesmo jeito que o motor de Monte Carlo é uma
função documentada no backend — só que esta "função" roda em conversa, não
no servidor.

**Quando aplicar:** toda vez que o usuário colar um lote de candidatos
(múltiplas linhas de opções/estruturas) pedindo para filtrar, comparar, ou
"aplicar os gates".

---

## Passo 1 — Gates automáticos (cortam o candidato, ele não aparece na tabela final)

Estes dois são objetivos e não dependem de perfil/julgamento — se não passam,
o candidato é inoperável de qualquer forma:

1. **Liquidez**: descartar linhas sem liquidez operável (volume/OI muito
   baixo, spread bid/ask muito largo a ponto de inviabilizar entrada/saída
   a preço razoável).
2. **Retorno mínimo 2–2,5%/mês, proporcional ao prazo**: 30d → 2–2,5%;
   60d → 4–5%; 90d → 6–7,5%; 12m → 24–30%. Abaixo disso, descartar — usuário
   não opera fora dessa diretriz.

Candidatos cortados podem ser mencionados en passant ("N linhas descartadas
por liquidez/retorno"), mas NÃO entram na tabela comparativa final.

## Passo 2 — Para os sobreviventes: tabela comparativa, sem cortar nada

Estes dois são **julgamento do usuário**, ligados ao perfil da estrutura e do
momento — o Claude NUNCA os usa como filtro automático, só apresenta o dado
bruto lado a lado para o usuário decidir:

3. **Probabilidade de sucesso** (Monte Carlo/GARCH) — sempre mostrar o número,
   nunca pré-filtrar por um piso arbitrário.
4. **Assimetria** (ganho se der certo vs. perda se der errado, em % ou R$) —
   sempre mostrar os dois lados lado a lado. Estruturas mais curtas tendem a
   ter assimetria pior (lição já registrada do caso VALE3) — mencionar isso
   como contexto, não como corte.

Colunas mínimas da tabela final: ticker/estrutura, prazo, retorno
teto/prefixado, probabilidade de sucesso, ganho se certo, perda se errado.

## Passo 3 — Regras já existentes que continuam valendo (não duplicar, só lembrar)

- Apresentar candidatos de covered call writing E put selling lado a lado,
  didaticamente, mesmo que só um lado tenha sido pedido (regra já
  estabelecida no "Options batch template").
- Sempre incluir a data de origem do lote no registro (`nome`/`observacao`)
  quando a análise virar "foto" (regra de rastreabilidade já existente).
- NUNCA avançar para "tirar a foto" (Fase B) sem os 4 números finalizados
  (ticker, prazo, strike/faixa, prêmio) — regra crítica já existente, esta
  rotina de gates não a substitui, é um passo ANTES dela.

## O que esta rotina NÃO faz

- Não decide por decisão. Passos 1–2 cortam o obviamente inviável; passos
  3–4 mostram dado bruto — a escolha final entre os sobreviventes continua
  sendo do usuário.
- Não vira filtro automático de probabilidade/assimetria, mesmo que pareça
  conveniente — o usuário foi explícito que isso tiraria autonomia da parte
  que é realmente julgamento dele.

## Limitações práticas por gate (corrigido 06/07/2026, conversa real com o usuário)

**Retorno mínimo (gate 2)**: cálculo puro/aritmético a partir dos números que o usuário
já traz (strike, prêmio, prazo). Claude calcula na hora, sempre, sem depender de nada
externo. Nenhuma limitação aqui.

**Liquidez (gate 1)**: na prática do usuário, quase sempre já vem resolvida -- o banco só
oferece o que tem liquidez, e o usuário já filtra antes de trazer o lote. Este gate existe
mais como salvaguarda (caso um dia apareça algo fora desse padrão, ex: ideia própria do
usuário não vinda do banco) do que como filtro que realisticamente vai reprovar algo no
fluxo usual.

**Probabilidade de sucesso (gate 3)**: **aqui SIM há uma limitação real**. O Claude NÃO
acessa o site/Render nem o Yahoo Finance diretamente no seu ambiente de sandbox (limitação
de rede já documentada em outras partes do projeto). Para calcular probabilidade com a
MESMA precisão do motor GARCH real (histórico de 1 ano, calibração completa), o caminho é:
- **Preferencial**: usuário roda o ranking/condicional no próprio app e cola o resultado
  aqui -- Claude incorpora esse número na tabela comparativa.
- **Alternativa quando o usuário não tiver isso em mãos**: Claude busca o preço atual via
  busca na web e roda uma simulação Monte Carlo própria (tem numpy disponível), mas com uma
  volatilidade ESTIMADA (vol implícita se o usuário tiver, ou uma aproximação própria) --
  **menos precisa** que o motor real do site. Sempre avisar quando o número é estimativa,
  não fingir precisão de motor quando não há.

**Assimetria (gate 4)**: mesma lógica de retorno mínimo -- cálculo direto a partir dos
números do lote (payoff se der certo vs se der errado), sem dependência externa.

## Evolução futura (backlog, não fazer sem pedido explícito)

Depois de acumular um histórico real de análises encerradas com o painel de
aproveitamento (esperado vs. realizado, ver seção de continuação 05/07/2026
parte 2 do prompt de sessão), revisitar se os limiares de liquidez/retorno
teriam evitado os piores casos reais -- e recalibrar os gates com base em
dado real, não em estimativa. Só fazer isso quando houver massa de dados
suficiente (usuário estimou ~15-20 análises encerradas).
