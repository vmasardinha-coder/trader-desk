# Guia — montecarlo_garch.py (módulo reutilizável)

Extraído do Trader Desk em 20/06/2026. Núcleo de volatilidade + simulação
Monte Carlo, sem nenhuma dependência de Flask, requisições HTTP, ou
qualquer coisa específica do projeto original. Só precisa de `numpy`.

## Instalação no novo projeto

1. Copie `montecarlo_garch.py` para a raiz (ou para um pacote `lib/`) do
   novo projeto.
2. Garanta que `numpy` esteja no `requirements.txt`:
   ```
   numpy
   ```
3. Importe normalmente:
   ```python
   import montecarlo_garch as mcg
   ```

## O que o módulo NÃO faz (responsabilidade de quem importa)

- **Não busca dados.** Você precisa ter, em algum lugar do seu projeto,
  uma lista de preços de fechamento históricos (`closes`) — vinda de
  Yahoo Finance, brapi, ou qualquer outra fonte. O módulo só recebe essa
  lista já pronta.
- **Não sabe o que é um "ticker".** Tudo é genérico: preço, volatilidade,
  dias, strikes. Não há nenhuma referência a ações específicas, B3, ou
  qualquer mercado em particular — funciona igual para qualquer ativo
  (ações, criptos, índices) desde que você tenha o histórico de preços.
- **Não tem cache.** Se seu projeto chamar a mesma simulação repetidamente,
  implemente cache na camada de cima (como o Trader Desk faz com
  `_IND_CACHE`/`_BTC_CACHE`).

## As 4 perguntas que o módulo responde

### 1. "Qual a volatilidade real deste ativo agora?"
```python
sigma_simples = mcg.vol_hist(closes)              # baseline simples
garch_info = mcg.garch_11(closes, horizon_days=21) # refinado, com memória de regime
sigma_garch = garch_info['vol_garch_projetada_pct'] / 100 if garch_info else sigma_simples
```
Use sempre `garch_11` quando tiver pelo menos ~60 pontos de histórico — ele
captura "clusters de volatilidade" (dias turbulentos seguidos de dias
turbulentos) que a vol. simples não captura. Com 50-59 pontos ainda
funciona, mas com menos confiança estatística.

### 2. "Qual a chance desta opção ser exercida?" (estrutura simples)
```python
resultado = mcg.simular_gbm(
    preco_atual=42.50,
    sigma=sigma_garch,
    t_dias=21,
    k_call=45.00,   # strike de uma call vendida (opcional)
    k_put=40.00,    # strike de uma put vendida (opcional)
)
# resultado['prob_call_exercida'], resultado['prob_sucesso'], etc.
```

### 3. "Qual a chance de tocar uma barreira?" (estrutura bidirecional)
```python
resultado = mcg.simular_barreira(
    preco_atual=54.31,
    sigma=sigma_garch,
    t_dias=86,
    kdo=43.51,  # barreira inferior
    kuo=68.76,  # barreira superior
)
# resultado['prob_sem_barreira'], ['prob_barreira_alta'], ['prob_barreira_baixa']
```

### 4. "Como desenho um fan chart (cone de incerteza)?"
```python
fan = mcg.simular_fan_chart(preco_atual=42.50, sigma=sigma_garch, t_dias=60)
# fan['dias']        -> eixo X
# fan['trajetorias'] -> ~20 linhas de amostra (para desenhar translúcidas)
# fan['percentis']   -> p10/p25/p50/p75/p90, prontos para a banda sombreada
```
Plote com qualquer biblioteca de gráficos (Chart.js, matplotlib, Plotly).
O formato já vem pronto: listas simples de números, sem objetos complexos.

## A 5ª pergunta — cenários "congelados" no passado

Se seu projeto tem o conceito de "decidi um cenário há N dias, quero saber
a chance de dar certo NO TEMPO QUE RESTA":

```python
dias_passados = (data_de_hoje - data_da_decisao).days
dias_restantes = prazo_original_dias - dias_passados

if dias_restantes <= 0:
    # prazo já esgotado, não há tempo restante para simular
    ...
else:
    cond = mcg.simular_condicional(
        preco_atual_real=preco_real_de_hoje,  # NÃO é o preço de quando decidiu
        sigma=sigma_garch_recalculado_agora,  # recalcule com dados de HOJE
        dias_restantes=dias_restantes,
        k_call=45.00,  # ou kdo/kuo para barreira
    )
```

Ponto importante: a vol. (`sigma`) deve ser recalculada com os dados mais
recentes no momento da consulta — não reaproveite a vol. que valia quando
o cenário foi "congelado". Só o preço de partida muda de "hoje" para
"preço real atual", e o horizonte muda de "prazo total" para "tempo que
resta".

## Decisões já tomadas (não precisa re-investigar)

Estas conclusões vieram de testes feitos na sessão de 20/06/2026 no
projeto original — economize tempo não repetindo essas investigações:

- **Grid search vs. MLE contínuo (scipy)**: testado em 5 cenários
  sintéticos diferentes, diferença na vol. projetada final foi 0.00pp em
  todos os casos. Não vale a pena trocar o grid search por otimização
  contínua — não simplifique a função achando que vai ganhar precisão.
- **Limiar mínimo de pontos para GARCH**: 60 é o padrão seguro; 50 ainda
  funciona quando a fonte de dados só permite período curto (ex: brapi
  free tier só permite `range=3mo`, ~60-65 dias úteis — dá pouca margem
  acima do limiar de 60, por isso 50 é mais seguro nesse caso específico).
- **Jump-Diffusion (Merton)**: testado contra GARCH puro, diferença fica
  entre -0.7pp e -6.8pp dependendo dos parâmetros de salto escolhidos.
  Calibrável só com histórico de preço (sem precisar de book de opções).
  Não implementado neste módulo — fica como possível extensão futura se
  o ganho de poucos pontos percentuais valer o esforço de calibração.
- **Heston (volatilidade estocástica)**: testado, diferença fica entre
  -2.3pp e -13.0pp — faixa muito mais larga (mais sensível a parâmetros
  chutados) que o Jump-Diffusion, e exigiria dados reais de book de
  opções para calibrar `xi` (vol-da-vol) e `rho` (correlação preço-vol)
  corretamente. **Considerado não viável** sem fonte paga de opções.
  Não implementado neste módulo.

## Limites matemáticos para comunicar ao usuário final

Se seu projeto mostra esses números para um usuário não-técnico, vale
deixar claro:

- O modelo (GBM) **não tem reversão de preço** — o cone de incerteza
  sempre se abre com o tempo (cresce com a raiz do tempo), nunca
  "converge de volta" para um valor central. Isso é esperado e correto.
- A probabilidade é **teórica/estatística**, não uma previsão garantida.
  Mesmo modelos mais sofisticados (GARCH, Heston) têm desempenho fraco em
  prever o resultado real (P&L) — eles estimam bem a distribuição de
  cenários possíveis, não "o que vai acontecer".
