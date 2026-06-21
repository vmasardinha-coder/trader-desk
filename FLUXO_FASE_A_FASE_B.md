# FLUXO_FASE_A_FASE_B.md — Regra de processo para "Em Análise"

> Definido em sessão de 21/06/2026. Esta regra é vinculante para qualquer
> assistente (Claude ou outro) que trabalhe neste projeto: antes de gerar
> uma "foto" em Em Análise, sempre verificar se este checklist foi cumprido.

## O problema que esta regra resolve

O usuário reconheceu, na sessão em que esta regra foi criada, que pode não
ter disciplina suficiente para seguir o fluxo correto sozinho — ou seja,
pode tentar pular direto para "tirar a foto" mesmo quando a análise ainda
não está fechada. Este documento existe para que o assistente sirva de
guarda-corpo nesse momento, questionando antes de prosseguir.

## Fase A — Pré-análise (sempre em sessão de chat, nunca via botão do app)

Acontece **antes** de qualquer foto ser registrada. Características:

- O usuário traz um lote de opções reais: de prateleira do banco,
  customizada (ticket ~R$50k), ou que ele mesmo monta no OpLab dentro dos
  prazos que usa (21, 30, 60 ou 90 dias).
- Os **4 números-chave ainda NÃO estão fechados**:
  1. **Ticker** — qual ativo
  2. **Prazo exato** — quantos dias
  3. **Strike/range** — `k_call`/`k_put` (estrutura simples) ou
     `kdo`/`kuo` (bidirecional/barreira)
  4. **Prêmio** — pago pelo banco explicitamente, OU estimado pelo
     assistente quando o banco não informa (baseado em liquidez, delta,
     volatilidade implícita das opções que o usuário colar)
- O assistente ajuda a: estimar prêmio quando não vem explícito, comparar
  candidatas, filtrar um lote grande (ex: 200 linhas de opções) para
  poucas opções viáveis, rodar Monte Carlo/GARCH para diferentes cenários
  hipotéticos antes de decidir.
- **Isso é trabalho aberto e exploratório.** Não tenta forçar pra um
  formulário fixo. Idas e voltas são esperadas e saudáveis aqui.

## Checkpoint de decisão (antes de avançar)

Antes de gerar uma foto, confirme com o usuário, explicitamente, que os
4 números estão fechados:

1. Ticker — definido?
2. Prazo — definido (não "entre 30 e 60", um número específico)?
3. Strike/range — definido com valores reais (não "algo perto de X")?
4. Prêmio — definido (valor real do banco, ou estimativa que o usuário
   já aceitou como referência)?

**Se qualquer um desses ainda estiver vago, incerto, ou não verbalizado
com clareza** — não gere a foto. Pergunte primeiro. Frases como "ainda
não decidi o prazo" ou "vou ver o que o banco oferece" são sinal de que
a Fase A não terminou.

## Fase B — Tirar a foto (vira registro monitorado)

Só começa depois do checkpoint acima ser cumprido. Nesse ponto:

- A foto é registrada (hoje: via sessão/Eruda; no futuro: via botão real
  no app, escrevendo em `analises.json` através de um token GitHub
  fine-grained restrito apenas a este repositório, com permissão apenas
  de "Contents" — configurado como variável de ambiente no Render, nunca
  exposto no código nem no frontend).
- A partir daí, o monitoramento é automático: o endpoint
  `/montecarlo/condicional` recalcula a probabilidade a partir do tempo
  que resta e do preço real, sem precisar de nova sessão com o assistente.
- O usuário só volta a precisar de uma sessão quando quiser fazer uma
  **nova** análise (nova Fase A) — não para acompanhar uma foto já tirada.

## Resumo de uma frase

**Sessão decide os números. App registra e monitora depois.** Se os
números ainda não foram decididos com clareza, ainda é Fase A — não gere
a foto.
