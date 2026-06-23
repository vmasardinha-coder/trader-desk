# Métodos Estatísticos e Modelos de Volatilidade — Mapa de Avaliação

> Extraído do projeto Trader Desk (ações/B3) em 22/06/2026, mas o conteúdo
> é GENÉRICO o suficiente para servir de ponto de partida em qualquer
> projeto que precise modelar volatilidade/probabilidade de preço de um
> ativo financeiro — incluindo criptoativos. Os números de diferença
> percentual (pp) citados abaixo foram medidos especificamente em ações
> brasileiras (PETR4/VALE3/AXIA3); a ORDEM DE GRANDEZA relativa entre os
> métodos tende a se manter, mas vale re-testar no novo contexto.

## ⚠️ LEIA PRIMEIRO — por que isto NÃO é um veredito definitivo para cripto

Os métodos marcados como "descartados" abaixo (Heston, SABR, e em menor
grau Jump-Diffusion/Lévy) foram descartados especificamente no contexto
de **ações na B3**, onde a limitação real era **falta de acesso gratuito
a book de opções e dados intraday**. Essa restrição de dado é o motivo
do descarte — **não é uma limitação do método em si**.

**Em criptoativos, essa restrição de dado tende a não existir, ou ser
muito mais branda**, porque:
- Exchanges como Binance/Coinbase oferecem candles intraday (1min, 5min)
  históricos via API gratuita, com profundidade de semanas/meses
- Exchanges de derivativos como Deribit publicam book de opções de BTC/ETH
  de forma aberta, incluindo dados históricos em alguns casos
- O mercado roda 24/7, gerando muito mais pontos de dado por dia do que
  um pregão de ações de poucas horas

**Conclusão prática**: ao iniciar o projeto de cripto, NÃO assumir que
Heston/SABR/Jump-Diffusion estão descartados — a primeira tarefa é
reavaliar se a fonte de dado que os tornava inviáveis aqui (book de
opções, dados intraday) está disponível de forma gratuita/acessível lá.
Se estiver, vale rodar os mesmos testes comparativos feitos no Trader
Desk (rodar cada método, medir divergência em pp contra o GARCH/baseline)
para decidir com dado real, não por analogia ao que foi decidido para
ações.

## Em produção / validados como suficientes

- **Black-Scholes (BS)**: fórmula fechada clássica de precificação de
  opções europeias. Útil como referência rápida e para extrair
  volatilidade implícita de preços de opção reais (via inversão
  numérica, ex. `scipy.optimize.brentq`), mas não é um motor de
  simulação de cenários por si só.

- **GARCH(1,1)**: modelo de volatilidade condicional que captura
  "clusters" de volatilidade (períodos calmos seguidos de turbulência,
  e vice-versa). Calibrado com histórico de preço REAL do ativo (não
  precisa de book de opções). Foi o motor principal escolhido no Trader
  Desk depois de comparação. Implementação livre de dependências pesadas
  feita à mão (grid search de alpha/beta, sem scipy) — funciona bem com
  janelas de ~50-60+ pontos de preço histórico.

- **Monte Carlo (alimentado pela vol. do GARCH)**: simula milhares de
  trajetórias de preço (GBM — Geometric Brownian Motion — com a
  volatilidade do GARCH). Para detectar eventos de barreira/exercício
  que podem ocorrer em QUALQUER momento até o vencimento (ex: opção
  americana, ou estrutura com barreira knock-in/knock-out), simula o
  CAMINHO DIÁRIO completo e usa max/min da trajetória. Para eventos que
  só importam no vencimento (opção europeia simples), basta simular o
  preço FINAL, sem precisar do caminho completo (mais rápido).

- **Vol. implícita via Black-Scholes invertido**: quando se tem acesso a
  preços reais de opções (book de mercado), extrair a vol. implícita por
  strike permite calibrar a simulação com a expectativa real do mercado
  para aquele vencimento específico — mais informativo que vol. histórica
  pura quando o dado está disponível.

## Avaliados e descartados NO CONTEXTO DE AÇÕES B3 (não valeu o esforço/custo ali — ver ressalva no topo antes de assumir o mesmo para cripto)

- **Calibração GARCH via MLE contínuo (scipy/Nelder-Mead) vs. grid
  search simples**: testado em 5 cenários sintéticos — diferença de
  0.00pp em TODOS os casos na vol. final projetada. Conclusão: grid
  search simples (sem dependência de scipy) já é suficiente; refinar a
  calibração não move a agulha.

- **Jump-Diffusion (Merton)**: adiciona "saltos"/gaps discretos ao GBM
  contínuo do GARCH, modelando eventos abruptos de preço. Calibrável só
  com histórico de preço (sem precisar de book de opções) — vantagem
  real de acessibilidade de dado. MAS testado contra GARCH puro em
  ações reais: diferença de apenas **-0.7pp a -6.8pp**. Ganho pequeno
  para a complexidade extra de calibrar 3 parâmetros adicionais (taxa de
  salto, média e desvio do tamanho do salto). Fica como ESTUDO FUTURO
  sem prioridade — pode valer mais a pena em ativos com histórico de
  saltos mais extremos/frequentes que ações (ex: criptoativos durante
  eventos de notícia, hacks, ou decisões regulatórias — vale re-testar
  aqui, pode ter resultado diferente).

- **Heston (volatilidade estocástica)**: a própria volatilidade segue um
  processo estocástico (mean-reverting), não é fixa como no GARCH/BS.
  Precisa de DADOS REAIS DE BOOK DE OPÇÕES para calibrar 2 parâmetros-
  chave (xi = vol. da vol., rho = correlação preço-vol.) com confiança.
  Testado com parâmetros estimados (sem book real): diferença de
  **-2.3pp a -13.0pp** vs. GARCH — faixa MUITO mais larga e instável,
  sintoma de alta sensibilidade a parâmetro chutado sem dado real.
  CONCLUSÃO: não vale a pena sem acesso a fonte paga de book de opções
  (no caso de cripto, equivalente seria o book de opções de uma exchange
  como Deribit, que tem dados gratuitos via API pública em alguns casos —
  vale checar antes de descartar automaticamente neste novo contexto).

- **SABR (Stochastic Alpha Beta Rho)**: "primo" do Heston, popular para
  modelar a superfície de "sorriso" de volatilidade em mercados de juros/
  câmbio. Mesma limitação fundamental do Heston — precisa de book de
  opções real para calibrar a superfície. Não foi testado numericamente
  (descartado por inferência direta da mesma limitação do Heston), mas
  poderia ser revisitado SE uma fonte de book de opções gratuita for
  encontrada (ver nota sobre Deribit acima).

- **Modelos de Lévy mais gerais (Variance Gamma, CGMY)**: generalizações
  do Jump-Diffusion com processos de salto mais ricos estatisticamente
  (não apenas saltos gaussianos simples como no Merton). Mesma família
  já testada; ganho marginal incerto, e exigiria MAIS dados históricos
  (idealmente intraday, não só fechamento diário) para calibrar os
  parâmetros extras com confiança. Não testado numericamente — descartado
  por inferência, não por medição direta.

- **Machine Learning / redes neurais para previsão de preço**: categoria
  fundamentalmente diferente dos modelos acima — é um ajuste estatístico
  de padrão (pattern-matching), não um modelo de difusão com fundamento
  probabilístico explícito. Avaliação qualitativa (sem teste numérico
  específico): a evidência acadêmica de que ML supera de forma
  CONSISTENTE um bom modelo de random walk + volatilidade estocástica é
  fraca, especialmente para horizontes curtos em ativos individuais.
  Risco real de overfitting e de criar falsa confiança nos resultados.
  NÃO RECOMENDADO como prioridade — mais hype do que ferramenta confiável
  nesse tipo de aplicação (probabilidade de cenário/risco, não
  classificação de padrão).

## ⭐ PRÓXIMO PASSO — o mais promissor ainda não explorado

### Volatilidade Realizada de Alta Frequência (dados intraday)

**A ideia central**: todos os modelos acima (GARCH, Merton, Heston) são
calibrados com preços de FECHAMENTO DIÁRIO. Mas a volatilidade real de
um ativo se manifesta a cada minuto/segundo de negociação — usar dados
intraday (preço a cada 1min, 5min, ou pelo menos a cada hora) permite
calcular a "volatilidade realizada" de forma muito mais precisa e
responsiva a eventos recentes do que esperar o fechamento do dia.

**Por que isso é diferente dos outros métodos testados**: Merton/Heston/
SABR são alternativas de FORMA do modelo (mudam a equação que descreve
o preço), mas continuam alimentados pelo mesmo dado pobre (close diário).
Vol. realizada intraday muda a GRANULARIDADE DO DADO DE ENTRADA — é uma
melhoria ortogonal, que pode ser combinada com qualquer um dos modelos
acima (inclusive o GARCH já em produção).

**Por que pode ser mais viável em cripto do que foi em ações B3**: o
mercado de criptoativos é 24/7, com volume e profundidade de dados
intraday GRATUITOS muito mais acessíveis via APIs públicas (Binance,
Coinbase, etc. oferecem candles de 1min/5min históricos de forma
gratuita e generosa) — isso pode resolver de cara a limitação que
inviabilizou explorar isso no contexto de ações B3 (onde dado intraday
gratuito de qualidade é mais escasso).

**Plano de investigação sugerido para a próxima sessão (no projeto de
cripto)**:
1. Mapear quais exchanges/APIs oferecem candles intraday históricos
   gratuitos com profundidade suficiente (semanas/meses) para o
   ativo de interesse
2. Calcular a volatilidade realizada (soma dos retornos intraday ao
   quadrado, anualizada) numa janela recente, e comparar contra a
   vol. GARCH calculada com close diário no mesmo período
3. Medir a diferença de forma sistemática (mesma metodologia usada
   para comparar Merton/Heston vs. GARCH: testar em múltiplos
   períodos/ativos, registrar a faixa de divergência em pontos
   percentuais)
4. Avaliar se a melhoria de precisão (se houver) justifica a
   complexidade extra de buscar/processar/armazenar dados intraday
   (mais volume de dados, mais chamadas de API, possível necessidade
   de cache/agregação)
5. Se valer a pena, considerar combinar com book de opções/derivativos
   da exchange (ex: Deribit tem book de opções de BTC/ETH com dados
   abertos), o que poderia reabrir a porta para Heston/SABR também,
   já que a limitação de dado pago que os descartou no contexto de
   ações pode não se aplicar da mesma forma em cripto

## Fora de escopo — mencionado mas não avaliado tecnicamente ainda

- **Mercados de previsão/apostas (estilo Polymarket) como fonte de
  probabilidade implícita**: a ideia é usar as "odds" de mercados de
  apostas sobre o preço futuro de um ativo (ex: "Bitcoin vai passar de
  $150k até dezembro?") como uma fonte adicional e pública de
  probabilidade implícita do mercado — similar ao que vol. implícita de
  opções já fornece, mas vindo de uma fonte diferente. Pode servir como
  dado complementar ou de validação cruzada contra os modelos acima.
  NÃO avaliado tecnicamente ainda (sem teste de viabilidade, sem
  mapeamento de quais plataformas têm dados acessíveis via API). Fica
  registrado como ideia a explorar depois do item de vol. intraday.
