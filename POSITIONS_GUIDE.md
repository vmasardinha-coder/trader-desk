# Trader Desk — Guia do `positions.json`

Este arquivo controla **todas** as posições ativas e encerradas do dashboard.
Editar aqui não exige tocar em HTML ou JavaScript — o app lê este arquivo
direto do GitHub e renderiza tudo automaticamente.

---

## Onde editar

`positions.json` na raiz do repositório:
https://github.com/vmasardinha-coder/trader-desk/blob/main/positions.json

No GitHub, clique no ícone de lápis (✏️) pra editar direto no navegador.

---

## Estrutura geral

```json
{
  "ativas": [ ... ],
  "encerradas": [ ... ]
}
```

---

## Posição ativa — tipo `simples`

Usado para: Call Vendida, Lançamento Coberto (PETR4, VALE3, ROXO34, BBAS3).

```json
{
  "id": "pt",
  "ticker": "PETR4.SA",
  "nome": "Petrobras PN",
  "tipo_posicao": "simples",
  "estrategia": "Call Vendida",
  "codigo_opcao": "PETRL319",
  "strike": 30.85,
  "vol_impl": 0.434,
  "tipo": "call",
  "vencimento": "2026-12-17",
  "objetivo": "Fechar abaixo de R$ 30,85"
}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id` | sim | Identificador único, curto, sem espaços (ex: `pt`, `vl`, `bb2`). Usado internamente para gerar todos os elementos da tela. |
| `ticker` | sim | Ticker com `.SA` (ex: `PETR4.SA`). Usado para buscar cotação e calcular B&S/Monte Carlo. |
| `nome` | sim | Nome de exibição (ex: `Petrobras PN`). |
| `tipo_posicao` | sim | Sempre `"simples"` para este formato. |
| `estrategia` | sim | Texto livre (ex: `Call Vendida`, `Lançamento Coberto`). |
| `codigo_opcao` | não | Código da opção (ex: `PETRL319`). Se omitido, a linha "Strike" não mostra o código. |
| `strike` | sim | Preço de exercício, número decimal. |
| `vol_impl` | sim | Volatilidade implícita em **decimal** (43.4% → `0.434`). Esse é o único parâmetro que você define manualmente — não existe fonte gratuita de vol. implícita real para opções B3. |
| `tipo` | sim | `"call"` ou `"put"`. |
| `vencimento` | sim | Data no formato `YYYY-MM-DD`. |
| `objetivo` | não | Texto livre exibido como meta da posição. |

---

## Posição ativa — tipo `barreira`

Usado para: estruturas Bidirecionais com KDO/KUO (AXIA3).

```json
{
  "id": "a3",
  "ticker": "AXIA3.SA",
  "nome": "AXIA3 (A)",
  "tipo_posicao": "barreira",
  "estrategia": "Bidirecional",
  "vencimento": "2026-09-14",
  "entry": 54.31,
  "kdo": 43.51,
  "kuo": 68.76,
  "kdo_pct": "-20%",
  "kuo_pct": "+26,6%",
  "ganho_sem_barreira": "até +31,2% / +20%",
  "ganho_barreira_alta": "+4% fixo"
}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `entry` | sim | Preço de entrada da estrutura. |
| `kdo` | sim | Barreira de baixa (Knock-Down-Out), número decimal. |
| `kuo` | sim | Barreira de alta (Knock-Up-Out), número decimal. |
| `kdo_pct` / `kuo_pct` | não | Texto de exibição da distância percentual (ex: `"-20%"`). |
| `ganho_sem_barreira` / `ganho_barreira_alta` | não | Texto livre descrevendo o payoff. |

Demais campos (`id`, `ticker`, `nome`, `estrategia`, `vencimento`) seguem o mesmo padrão do tipo simples.

---

## Como abrir uma posição nova

1. Copie um bloco existente do tipo certo (`simples` ou `barreira`).
2. Mude o `id` para algo único que não exista ainda na lista.
3. Ajuste todos os campos.
4. Adicione o bloco dentro do array `"ativas": [ ... ]`, separado por vírgula.
5. Salve / suba o arquivo.

A aba **Posições Ativas** vai mostrar o card automaticamente, com B&S e Monte
Carlo calculados em tempo real a partir do `strike`, `vol_impl` e `vencimento`
que você definiu.

---

## Como encerrar uma posição

1. **Remova** o bloco correspondente do array `"ativas"`.
2. **Adicione** um bloco no array `"encerradas"`, no formato abaixo.

```json
{
  "id": "cl-roxo34-2026",
  "ticker": "ROXO34",
  "estrategia": "Lançamento Coberto",
  "codigo_opcao": "ROXOG105",
  "strike": 10.50,
  "data_encerramento": "2026-07-16",
  "status": "sucesso",
  "pct_do_alvo": 100,
  "resultado_texto": "Exercida no vencimento",
  "observacao": "Ação debitada na carteira ao preço do strike"
}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id` | sim | Identificador único. |
| `ticker` | sim | Nome do ativo (sem `.SA` aqui, é só exibição). |
| `estrategia` | sim | Texto livre. |
| `status` | sim | `"sucesso"` ou `"parcial"`. Controla o badge (verde ou amarelo) e entra na Taxa de Sucesso do dashboard. |
| `codigo_opcao` + `strike` | não | Se presentes, mostra a linha "Opção". |
| `alvo_pct` / `realizado_pct` | não | Para operações de renda fixa/prefixado (ex: ROXO34 Prefixado). |
| `pct_do_alvo` | não | Se presente, desenha a barra de progresso visual e entra no cálculo de "Resultado Médio" do dashboard. |
| `pct_do_prazo` | não | Entra no cálculo de "Tempo Médio" do dashboard. |
| `data_encerramento` | não | Formato `YYYY-MM-DD`. Se omitido, mostra "Encerrada" sem data. |
| `resultado_texto` | não | Frase livre de resultado. |
| `observacao` | não | Nota adicional em cinza. |

O dashboard no topo da aba Encerradas (Operações, Taxa de Sucesso, Resultado
Médio, Tempo Médio) **recalcula automaticamente** com base em todos os itens
do array — não precisa editar nada manualmente ali.

---

## Erros comuns e validação automática

O backend valida o arquivo a cada carregamento. Se algo estiver errado, a
aba mostra a mensagem de erro exata, apontando qual posição e qual campo:

- Vírgula faltando ou sobrando entre blocos -> erro de JSON, a mensagem vai
  indicar "JSON malformado".
- Campo obrigatório faltando -> `ativas[pt]: falta campo obrigatorio 'strike'`.
- `id` duplicado -> `ativas: id 'pt' duplicado`.
- Data em formato errado -> `ativas[pt]: 'vencimento' deve ser formato YYYY-MM-DD`.
- `tipo_posicao` diferente de `simples`/`barreira` -> erro explícito.

Se a validação falhar, as outras abas continuam funcionando normalmente —
só Posições e Encerradas mostram a mensagem de erro até o arquivo ser
corrigido.

---

## Dica — validar antes de subir

Antes de salvar mudanças manuais, você pode colar o conteúdo em
https://jsonlint.com para garantir que a sintaxe JSON está correta (vírgulas,
chaves, aspas). Isso evita o erro mais comum: vírgula sobrando no último
item de uma lista.

---

## O que NÃO fica neste arquivo

- Cálculos de B&S, Monte Carlo, preços atuais — tudo isso é calculado em
  tempo real pelo backend (`proxy.py`), a partir dos parâmetros que você
  define aqui.
- Cotações ao vivo — vêm de TradingView/brapi/Yahoo, não deste arquivo.
- Layout visual — controlado por `style.css` e `app.js`. Esses sim exigem
  edição de código.
