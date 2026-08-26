const B='https://trader-desk.onrender.com';

// ── AUTENTICACAO DAS ROTAS DE ESCRITA ──────────────────
// Adicionado 25/06/2026. Backend agora exige header Authorization: Bearer
// <token> nas rotas que gravam dados reais (POST /analises, PUT /analises/
// <id>/status). Token salvo no localStorage DESTE DISPOSITIVO -- pedido
// uma vez (prompt simples), nao precisa digitar de novo depois. NAO e
// multi-usuario (token unico compartilhado entre quem tiver acesso ao
// dispositivo) -- e a PRIMEIRA CAMADA de protecao contra acesso externo
// pela URL publica, nao um sistema de contas por usuario.
function _getApiToken(){
  let t=localStorage.getItem('api_write_token');
  if(!t){
    t=prompt('Configure o token de acesso para gravar dados (Rejeitar/Aprovar análises). Cole aqui:');
    if(t)localStorage.setItem('api_write_token',t.trim());
  }
  return t;
}
function _authHeaders(){
  const t=_getApiToken();
  return t?{'Authorization':'Bearer '+t}:{};
}

const SEG={
  fin:['ITUB4','BBDC4','BBAS3','SANB11','B3SA3','BPAC11','ITSA4','BRSR6','ABCB4','BMGB4'],
  pet:['PETR4','PETR3','PRIO3','BRAV3','VBBR3','CSAN3','RECV3','UGPA3','SEQL3','GGBR4'],
  min:['VALE3','GGBR4','CSNA3','USIM5','BRAP4','FESA4','CMIN3','CBAV3','GOAU4','PGMN3'],
  mat:['SUZB3','KLBN11','DXCO3','UNIP6','RANI3','ORVR3','SMTO3','FRAS3','LPSB3','CSUD3'],
  uti:['AXIA3','EQTL3','CPFE3','SBSP3','CMIG4','ENGI11','TAEE11','AURE3','EGIE3','CPLE3'],
  cc: ['RENT3','LREN3','MGLU3','CYRE3','MRVE3','AZZA3','VIVA3','SBFG3','YDUQ3','MOVI3'],
  cn: ['ABEV3','SMTO3','NATU3','MDIA3','BEEF3','SLCE3','MTRE3','CAML3','PCAR3','MRVE3'],
  sau:['RDOR3','HAPV3','FLRY3','DASA3','QUAL3','ONCO3','PNVL3','ODPV3','MATD3','AALR3'],
  ind:['WEGE3','RAIL3','TGMA3','ROMI3','VLID3','TUPY3','IRBR3','POMO4','LAVV3','FRAS3'],
  tit:['VIVT3','TIMS3','POSI3','MLAS3','ANIM3','INTB3','LWSA3','CASH3','OIBR3','IFCM3'],
};
const USSEG={
  m7:['AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA'],
  nq:['AAPL','MSFT','NVDA','AMZN','META','GOOGL','TSLA','AVGO','COST','NFLX','QCOM','AMD','ADBE','INTC','CSCO'],
  sp:['AAPL','MSFT','NVDA','AMZN','META','GOOGL','TSLA','AVGO','BRK.B','JPM','LLY','V','UNH','XOM','MA','NFLX','PG','JNJ','HD','BAC'],
  dj:['UNH','GS','HD','SHW','CAT','AXP','MCD','AMGN','V','TRV','IBM','JPM','HON','CRM','CVX','AAPL','MSFT','DIS','NKE','BA'],
  // Adicionado 23/06/2026 -- usuario preocupado com risco de concentracao/
  // bolha de IA no mercado americano. Lista confirmada pelo usuario:
  // nucleo de semicondutores (infraestrutura fisica da IA), separado dos
  // grupos acima para nao misturar com Amazon/Meta/etc. do Nasdaq Top 15.
  semi:['NVDA','AMD','AVGO','TSM','ASML','INTC','MU','QCOM'],
  // Adicionados 23/06/2026 -- mesma logica de concentracao/bolha de IA,
  // usuario identificou que Software e Energia (ligada a infraestrutura
  // de IA/data centers, NAO petroleo/gas tradicional) sao outras 2 areas
  // de alta concentracao na narrativa de IA. Listas baseadas em holdings
  // reais do ETF IGV (software) e do indice NUKZX/cobertura de imprensa
  // sobre acordos de energia nuclear para data centers (CEG/VST/TLN
  // fornecem energia para AWS/Meta/Microsoft/Google).
  // CORRIGIDO 23/06/2026: estava com a lista antiga de 5 tickers
  // (ORCL/PANW/PLTR/CRWD/ADBE) -- nao batia com o top 10 real do IGV ja
  // usado no backend (tickers_map de /us/concentracao). ADBE NEM esta no
  // top 10 real (e a 12a posicao, 3.02%) -- foi um erro de selecao
  // anterior, nao do IGV. Corrigido para os 10 reais.
  software:['PANW','PLTR','MSFT','ORCL','CRWD','CRM','APP','CDNS','NOW','FTNT'],
  // energia_ia REMOVIDO 23/06/2026 -- usuario decidiu nao vale o esforco
  // (CEG/VST/TLN/D/OKLO sao utilities pequenas demais, sem dado
  // disponivel em nenhuma das fontes tentadas)
};
const fR=v=>v!=null?'R$ '+Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
// Nomes de empresas para exibir junto ao ticker nos segmentos EUA
// (m7/nq/sp/dj/semi/software) -- pedido do usuario 02/07/2026: so o
// codigo (ex "UNH") nao deixa obvio qual e o papel.
const US_NOMES={
  AAPL:'Apple',MSFT:'Microsoft',NVDA:'NVIDIA',AMZN:'Amazon',GOOGL:'Alphabet (Google)',
  META:'Meta Platforms',TSLA:'Tesla',AVGO:'Broadcom',COST:'Costco',NFLX:'Netflix',
  QCOM:'Qualcomm',AMD:'AMD',ADBE:'Adobe',INTC:'Intel',CSCO:'Cisco',
  'BRK.B':'Berkshire Hathaway',JPM:'JPMorgan Chase',LLY:'Eli Lilly',V:'Visa',
  UNH:'UnitedHealth',XOM:'Exxon Mobil',MA:'Mastercard',PG:'Procter & Gamble',
  JNJ:'Johnson & Johnson',HD:'Home Depot',BAC:'Bank of America',GS:'Goldman Sachs',
  SHW:'Sherwin-Williams',CAT:'Caterpillar',AXP:'American Express',MCD:"McDonald's",
  AMGN:'Amgen',TRV:'Travelers',IBM:'IBM',HON:'Honeywell',CRM:'Salesforce',
  CVX:'Chevron',DIS:'Disney',NKE:'Nike',BA:'Boeing',
  TSM:'Taiwan Semiconductor',ASML:'ASML',MU:'Micron',
  PANW:'Palo Alto Networks',PLTR:'Palantir',ORCL:'Oracle',CRWD:'CrowdStrike',
  APP:'AppLovin',CDNS:'Cadence',NOW:'ServiceNow',FTNT:'Fortinet',
};
const fU=v=>v!=null?'US$ '+Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
const fP=v=>v!=null?Number(v).toLocaleString('pt-BR',{maximumFractionDigits:0}):'—';
function E(id,t){const e=document.getElementById(id);if(!e)return;e.textContent=t;e.classList.remove('loading');}
function ChTbl(idV,idPct,now,prev,tp){
  const diff=now-prev,pct=(diff/Math.abs(prev||1)*100),sg=diff>=0?'+':'';
  const cls=diff>0?'chg chg-up':diff<0?'chg chg-dn':'chg chg-fl';
  let varStr='';
  if(tp==='r')varStr=sg+'R$ '+Math.abs(diff).toFixed(2);
  else if(tp==='u')varStr=sg+Math.abs(diff).toFixed(2);
  else varStr=sg+Math.abs(diff).toLocaleString('pt-BR',{maximumFractionDigits:0});
  const pctStr=sg+pct.toFixed(2)+'%';
  const ev=document.getElementById(idV);if(ev){ev.textContent=varStr;ev.className=cls;}
  const ep=document.getElementById(idPct);if(ep){ep.textContent=pctStr;ep.className=cls;}
}
function Ch(id,n,p,tp){
  const e=document.getElementById(id);if(!e)return;
  const d=n-p,pc=(d/Math.abs(p||1)*100).toFixed(2),sg=d>=0?'+':'';
  if(tp==='r')e.textContent=sg+'R$ '+Math.abs(d).toFixed(2)+' ('+sg+pc+'%)';
  else if(tp==='u')e.textContent=sg+d.toFixed(2)+' ('+sg+pc+'%)';
  else e.textContent=sg+Math.abs(d).toLocaleString('pt-BR',{maximumFractionDigits:0})+' ('+sg+pc+'%)';
  e.className='cc '+(d>0?'chg-up':d<0?'chg-dn':'chg-fl');
}
function sw(t,el){
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(x=>{x.classList.remove('active');x.style.display='none';});
  const tabEl=document.getElementById('tab-'+t);
  if(tabEl){tabEl.classList.add('active');tabEl.style.display='block';}
  if(el)el.classList.add('active');
  if(t==='indicadores'&&!window._IL){window._IL=true;loadInd();}
  if(t==='calendario'&&!window._CL){window._CL=true;loadCal();}
  if(t==='emanalise'&&!window._AL){window._AL=true;loadAnalises();}
  if(t==='encerradas'&&!window._ENCL){window._ENCL=true;loadAnalisesEncerradas();}
  if(t==='etfs'&&!window._ETL){window._ETL=true;loadETFs();}
  if(t==='emanalise'){
    // ADICIONADO 15/07/2026 -- "ETFs em Análise" agora mora aqui (ver
    // _renderEtfAnaliseTabQuandoPronto abaixo). Precisa de _etfData
    // carregado (mesma dependencia que ja existia para Carteira ETFs).
    if(!window._ETL){window._ETL=true;loadETFs();}
    _renderEtfAnaliseTabQuandoPronto();
  }
  if(t==='etfscarteira'){
    if(!window._ETL){window._ETL=true;loadETFs();}
    _renderEtfCarteiraTabQuandoPronto();
  }

}

// Adicionado 05/07/2026 -- Em Analise/Carteira de ETFs viraram aba propria
// em Minha Operacao (#tab-etfscarteira), separada da Watchlist (que ficou
// em Mercado). Como essa aba pode ser aberta ANTES da Watchlist (e antes
// de loadETFs() terminar), espera _etfData estar populado antes de
// renderizar -- evita mostrar tabela vazia se o usuario clicar direto em
// "Carteira ETFs" sem nunca ter aberto "ETFs" (Mercado).
// ATUALIZADO 15/07/2026: nao ha mais subtabs aqui (Em Analise saiu pra
// #tab-emanalise) -- essa aba agora e so a Carteira de fato.
function _renderEtfCarteiraTabQuandoPronto(){
  if(!window._etfDataPronto){
    setTimeout(_renderEtfCarteiraTabQuandoPronto,200);
    return;
  }
  renderEtfCarteira();
}

// ADICIONADO 15/07/2026 -- mesmo raciocinio do helper acima, mas para a
// secao "ETFs em Análise" que passou a morar dentro de #tab-emanalise.
function _renderEtfAnaliseTabQuandoPronto(){
  if(!window._etfDataPronto){
    setTimeout(_renderEtfAnaliseTabQuandoPronto,200);
    return;
  }
  renderEtfAnaliseTable();
}

// Adicionado 05/07/2026 -- fase 4 da modernizacao de layout (sidebar com
// accordion, substitui a nav horizontal das fases 1-3). NAO substitui
// sw(): so controla qual .sidebar-fam-body fica expandido (accordion) e
// ativa a primeira aba daquela familia clicando nela de verdade
// (reaproveita o onclick original, sem duplicar logica de troca de
// conteudo). Cada familia e seu container: '#sfam-'+fam.
function swFam(fam,el){
  document.querySelectorAll('.sidebar-fam').forEach(sf=>{
    const hdr=sf.querySelector('.sidebar-fam-hdr');
    const body=sf.querySelector('.sidebar-fam-body');
    const arrow=sf.querySelector('.sidebar-fam-arrow');
    const isAlvo=sf.id==='sfam-'+fam;
    if(hdr)hdr.classList.toggle('active',isAlvo);
    if(body)body.style.display=isAlvo?'block':'none';
    if(arrow)arrow.textContent=isAlvo?'⌄':'›';
  });
  const first=document.querySelector('#sfam-'+fam+' .tab');
  if(first)first.click();
}

// Adicionado 04/07/2026 -- fase 2 da modernizacao de layout (header fixo).
// NAO duplica fetch: so espelha o que ja esta calculado nos elementos da
// aba Cotacoes (ibov-p/ibov-c, usd-p/usd-c, brselic-p) para os elementos
// espelho no header sticky. Roda em intervalo simples, zero acoplamento
// com a logica de busca/atualizacao existente.
function _mirror(srcId,dstId){
  const s=document.getElementById(srcId),d=document.getElementById(dstId);
  if(!s||!d)return;
  d.textContent=s.textContent;
  d.className=s.className;
}
function syncHeaderTicker(){
  _mirror('ibov-p','hdr-ibov-p');
  _mirror('ibov-c','hdr-ibov-c');
  _mirror('usd-p','hdr-usd-p');
  _mirror('usd-c','hdr-usd-c');
  _mirror('brselic-p','hdr-selic-p');
}
setInterval(syncHeaderTicker,1500);
syncHeaderTicker();

// Adicionado 25/06/2026 -- item 1 do backlog (FIIs). Screening via
// Fundamentus, descarte automatico no backend (liquidez/DY/P-VP), filtro
// de segmento aplicado no FRONTEND (dado completo ja vem do backend numa
// chamada so -- nao recarrega ao trocar de segmento, so refiltra a lista
// em memoria). Carregamento MANUAL via botao "Atualizar" (nao automatico
// ao trocar de aba) -- scraping de 560 FIIs e mais pesado que as outras
// abas, usuario decide quando vale rodar de novo.
let _fiisData=[];
let _fiisTodosData=[];
let _fiisEscopoAtivo='criterio';  // 'todos' ou 'criterio'
let _fiisSegmentoAtivo='todos';
let _fiisRiscoAtivo='todos';
let _fiisBuscaTexto='';
// ADICIONADO 30/06/2026 -- set com tickers ja ATIVOS na carteira de FIIs,
// usado para o botao "+ Em Analise" virar "✓ Em Carteira" (desabilitado)
// no screening, em vez de continuar oferecendo a acao para algo que ja
// foi decidido. Populado em loadFiis() (fetch paralelo e silencioso).
let _carteiraFiisTickers=new Set();

// Decide o estado do botao de acao na linha do FII/FI-Infra do
// screening, considerando 3 estados possiveis: ja na carteira (ativa),
// ja em analise (em_analise/ativa em analises.json), ou disponivel.
function botaoStatusFii(ticker, tituloDisponivel, estiloDisponivel){
  const tickerCompleto=ticker+'.SA';
  if(_carteiraFiisTickers.has(tickerCompleto)||_carteiraFiisTickers.has(ticker)){
    return `<button disabled title="Já está ativo na sua Carteira de FIIs" style="background:rgba(76,217,100,.12);border:1px solid rgba(76,217,100,.3);color:var(--green);padding:5px 9px;font-size:10px;font-family:inherit;font-weight:700;cursor:default">✓ Em Carteira</button>`;
  }
  const jaEmAnalise=_analiseData&&_analiseData.find(a=>(a.ticker===tickerCompleto||a.ticker===ticker)&&(a.status==='em_analise'||a.status==='ativa'));
  if(jaEmAnalise){
    return `<button disabled title="Já está em Em Análise (id: ${jaEmAnalise.id})" style="background:rgba(255,204,0,.12);border:1px solid rgba(255,204,0,.3);color:#ffcc00;padding:5px 9px;font-size:10px;font-family:inherit;font-weight:700;cursor:default">Em Análise</button>`;
  }
  return `<button onclick="aprovarFiiParaAnalise('${ticker}')" title="${tituloDisponivel}" style="${estiloDisponivel}">+ Em Análise</button>`;
}

const _FII_ESCOPO_LABEL={
  todos:'Todos (universo bruto)', criterio:'Critério (liquidez + DY + vacância)'
};
const _FII_ESCOPO_TITLE={
  todos:'Todos os FIIs tradicionais encontrados no Fundamentus, SEM nenhum filtro -- inclui os que ficariam fora do critério padrão (liquidez baixa, DY zerado). Esses aparecem com marcador vermelho e sem classificação de segmento/risco.',
  criterio:'Apenas FIIs que passam no critério padrão (liquidez ≥ R$50k/dia, DY > 0%, vacância média ≤ 25% quando disponível) -- classificados por segmento e nível de risco.',
};
const _FII_SEGMENTO_LABEL={
  todos:'Todos', papel:'Papel', hibrido:'Híbrido', tijolo:'Tijolo', fof:'Fundo de Fundos', 'fi-infra':'FI-Infra', outros:'Outros'
};
const _FII_RISCO_LABEL={
  todos:'Todos', high_grade:'🟢 High Grade', middle_risk:'🟡 Middle Risk', high_yield:'🔴 High Yield'
};
const _FII_RISCO_TITLE={
  high_grade:'DY próximo/abaixo da média do segmento, vacância baixa -- menor risco relativo',
  middle_risk:'Risco intermediário, sem sinal claro de alerta nem de qualidade alta',
  high_yield:'DY muito acima da média do segmento, fundo de desenvolvimento, Fiagro, ou vacância alta -- maior risco relativo. NÃO é exclusão automática -- listas organizadas para você julgar com seu próprio critério (alavancagem e concentração de devedores não são capturáveis de forma gratuita).'
};

async function loadFiis(){
  const cont=document.getElementById('fiis-container');
  const btn=document.getElementById('btn-fiis-reload');
  if(!cont)return;
  cont.innerHTML='<p style="color:var(--muted);padding:20px;text-align:center">Buscando dados do Fundamentus (560+ FIIs, pode levar alguns segundos)...</p>';
  if(btn){btn.disabled=true;btn.style.opacity='.6';}
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),30000);
    const r=await fetch(B+'/fiis',{signal:ctrl.signal,cache:'no-store'});
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    _fiisData=d.fiis||[];          // so os classificados (visao Criterio)
    _fiisTodosData=d.fiis_todos||d.fiis||[];  // classificados + fora_criterio (visao Todos)
    renderFiisFiltro();
    renderFiis();

    // ADICIONADO 30/06/2026 -- busca silenciosa (paralela, nao bloqueia o
    // render acima) da carteira de FIIs, so para saber QUAIS tickers ja
    // estao ativos -- usado por botaoStatusFii() para trocar "+ Em
    // Analise" por "✓ Em Carteira". Falha silenciosa (nao impede uso do
    // screening se a carteira nao carregar por algum motivo).
    fetch(B+'/carteira-fiis',{cache:'no-store'}).then(r2=>r2.json()).then(d2=>{
      _carteiraFiisTickers=new Set((d2.carteira||[]).filter(f=>f.status==='ativa').map(f=>f.ticker));
      renderFiis();  // re-renderiza so os botoes com o estado correto, sem re-buscar nada
    }).catch(()=>{});

    // Mesma logica para _analiseData (usado no estado "Em Analise" do
    // botao) -- se ainda nao foi carregado nesta sessao (usuario foi
    // direto para a aba FIIs sem passar por Em Analise antes), busca
    // agora tambem, silenciosamente.
    if(!_analiseData){
      fetch(B+'/analises',{cache:'no-store'}).then(r3=>r3.json()).then(d3=>{
        _analiseData=Array.isArray(d3)?d3:[];
        renderFiis();
      }).catch(()=>{});
    }
  }catch(e){
    cont.innerHTML='<p style="color:var(--red);padding:20px">⚠ Erro ao buscar FIIs: '+e.message+'</p>';
    if(btn){btn.disabled=false;btn.style.opacity='1';}
    return;
  }
  if(btn){btn.disabled=false;btn.style.opacity='1';}

  // Adicionado 26/06/2026 -- busca dados financeiros do FI-Infra EM
  // PARALELO, sem bloquear a tela principal (que ja carregou rapido com
  // os 560 FIIs tradicionais). FI-Infra exige 22 requisicoes HTTP extras
  // (pagina individual de cada ticker), por isso e mais lento -- a tela
  // atualiza sozinha quando os dados chegarem, sem o usuario precisar
  // esperar ou clicar de novo.
  try{
    const ctrl2=new AbortController();setTimeout(()=>ctrl2.abort(),45000);
    const r2=await fetch(B+'/fii-infra',{signal:ctrl2.signal,cache:'no-store'});
    const d2=await r2.json();
    if(r2.ok&&!d2.error&&d2.fundos){
      const dadosPorTicker={};
      d2.fundos.forEach(f=>{dadosPorTicker[f.ticker]=f;});
      // Passo 1: atualiza FI-Infra que ja existem em _fiisTodosData
      _fiisTodosData=_fiisTodosData.map(f=>{
        if(f.segmento==='fi-infra'&&dadosPorTicker[f.ticker]){
          const dados=dadosPorTicker[f.ticker];
          return {...f, cotacao:dados.cotacao, dy_pct:dados.dy_pct, liquidez:dados.liquidez,
                   p_vp:dados.p_vp, nivel_risco:dados.nivel_risco, score:dados.score,
                   fora_criterio:dados.fora_criterio, motivo_fora_criterio:dados.motivo_fora_criterio,
                   sem_dados_financeiros:!dados.dados_disponiveis};
        }
        return f;
      });
      // Passo 2: insere fundos novos que vieram do /fii-infra mas NAO
      // existem ainda em _fiisTodosData (ex: FIP-IE como KNDI11/BDIV11/
      // XPIE11 que nao sao cobertos pelo Fundamentus)
      const tickersJaPresentes=new Set(_fiisTodosData.map(f=>f.ticker));
      const novosInfra=d2.fundos.filter(f=>!tickersJaPresentes.has(f.ticker)).map(f=>({
        ...f,
        segmento: 'fi-infra',
        segmento_fundamentus: f.categoria_display==='FIP-IE'
          ? 'Fundo de Investimentos em Participacoes (FIP-IE)' : 'Fundo de Infraestrutura (FI-Infra)',
        sem_dados_financeiros: !f.dados_disponiveis,
      }));
      if(novosInfra.length>0){
        // Insere antes dos fora_criterio, depois dos validos ja existentes
        const validos=_fiisTodosData.filter(f=>!f.fora_criterio);
        const fora=_fiisTodosData.filter(f=>f.fora_criterio);
        const novosValidos=novosInfra.filter(f=>!f.fora_criterio);
        const novosFora=novosInfra.filter(f=>f.fora_criterio);
        _fiisTodosData=[...validos,...novosValidos,...fora,...novosFora];
      }
      _fiisData=_fiisTodosData.filter(f=>!f.fora_criterio);
      renderFiisFiltro();
      renderFiis();
    }
  }catch(e){
    // Falha silenciosa -- FI-Infra continua mostrando "sem dados ainda",
    // nao quebra a tela principal que ja carregou com sucesso.
  }

  // NOTA (30/06/2026): Chamada B (universo complementar via StatusInvest)
  // foi cancelada -- StatusInvest nao renderiza DY nem liquidez server-side,
  // entao nao acrescenta nada util alem do que o Fundamentus ja cobre.
  // Os ~140 FIIs extras nao cobertos pelo Fundamentus tem liquidez tao baixa
  // que morreriam no criterio de qualquer forma. FI-Infra e FIP-IE sao
  // cobertos pelo /fii-infra (Investidor10 individual, ja implementado).
}

// Adicionado 26/06/2026 -- estrutura em ARVORE pedida pelo usuario:
// 1. Busca por texto (sempre visivel, no topo)
// 2. Escopo: Todos (560 brutos) vs Criterio (so validos) -- nivel 1
// 3. Segmento -- SEMPRE visivel (FI-Infra so existe na visao Todos, e
//    precisa do filtro de segmento la tambem -- bug real reportado pelo
//    usuario: filtro so existia/funcionava dentro de Criterio, FI-Infra
//    aparecia 0 mesmo estando na lista). Risco -- SO em Criterio (FIIs
//    fora do criterio/FI-Infra nao tem nivel_risco classificado).
function renderFiisFiltro(){
  const area=document.getElementById('fiis-segmento-filtro');
  if(!area)return;
  const dadosBase=_fiisEscopoAtivo==='todos'?_fiisTodosData:_fiisData;

  const escopos=['criterio','todos'];
  const linhaEscopo=escopos.map(e=>{
    const ativo=e===_fiisEscopoAtivo;
    const n=e==='todos'?_fiisTodosData.length:_fiisData.length;
    return `<button onclick="setFiisEscopo('${e}')" title="${_FII_ESCOPO_TITLE[e]}" style="background:${ativo?'var(--accent)':'var(--bg3)'};border:1px solid ${ativo?'var(--accent)':'var(--border)'};color:${ativo?'#fff':'var(--muted)'};padding:7px 16px;font-size:12px;cursor:pointer;font-family:inherit;font-weight:700;border-radius:4px">${_FII_ESCOPO_LABEL[e]} (${n})</button>`;
  }).join('');

  // Segmento -- conta a partir de dadosBase (reflete o escopo atual: 560+22
  // em Todos, ~249 em Criterio), SEMPRE renderizado independente do escopo.
  const contagensSeg={todos:dadosBase.length};
  dadosBase.forEach(f=>{contagensSeg[f.segmento]=(contagensSeg[f.segmento]||0)+1;});
  const segs=['todos','papel','tijolo','hibrido','fof','fi-infra','outros'];
  const linhaSeg=segs.map(s=>{
    const ativo=s===_fiisSegmentoAtivo;
    const n=contagensSeg[s]||0;
    return `<button onclick="setFiisSegmento('${s}')" style="background:${ativo?'var(--accent)':'var(--bg3)'};border:1px solid ${ativo?'var(--accent)':'var(--border)'};color:${ativo?'#fff':'var(--muted)'};padding:6px 14px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:${ativo?'700':'600'};border-radius:4px">${_FII_SEGMENTO_LABEL[s]} (${n})</button>`;
  }).join('');

  // Risco -- so faz sentido em Criterio (FI-Infra/fora_criterio nunca tem
  // nivel_risco classificado, filtrar por risco neles nao daria nada).
  let linhaRiscoHtml='';
  if(_fiisEscopoAtivo==='criterio'){
    const contagensRisco={todos:_fiisData.length};
    _fiisData.forEach(f=>{contagensRisco[f.nivel_risco]=(contagensRisco[f.nivel_risco]||0)+1;});
    const riscos=['todos','high_grade','middle_risk','high_yield'];
    const linhaRisco=riscos.map(r=>{
      const ativo=r===_fiisRiscoAtivo;
      const n=contagensRisco[r]||0;
      const title=_FII_RISCO_TITLE[r]?` title="${_FII_RISCO_TITLE[r]}"`:'';
      return `<button onclick="setFiisRisco('${r}')"${title} style="background:${ativo?'var(--accent)':'var(--bg3)'};border:1px solid ${ativo?'var(--accent)':'var(--border)'};color:${ativo?'#fff':'var(--muted)'};padding:6px 14px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:${ativo?'700':'600'};border-radius:4px">${_FII_RISCO_LABEL[r]} (${n})</button>`;
    }).join('');
    linhaRiscoHtml=`
      <div style="font-size:9px;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px;margin-top:8px">Nível de risco</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${linhaRisco}</div>`;
  }

  const filtrosSegRisco=`
    <div style="margin-left:16px;margin-top:8px;padding-left:10px;border-left:2px solid var(--border)">
      <div style="font-size:9px;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px">Segmento</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${linhaSeg}</div>
      ${linhaRiscoHtml}
    </div>`;

  const buscaHtml=`<div style="margin-bottom:10px"><input type="text" id="fiis-busca-input" placeholder="Buscar ticker ou nome do fundo..." value="${_fiisBuscaTexto||''}" oninput="setFiisBusca(this.value)" style="width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:7px 10px;font-size:12px;font-family:inherit;border-radius:4px"></div>`;
  const escopoHtml=`<div style="font-size:9px;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px">Escopo</div><div style="display:flex;gap:6px;flex-wrap:wrap">${linhaEscopo}</div>`;

  area.innerHTML=buscaHtml+escopoHtml+filtrosSegRisco;
}

function setFiisBusca(texto){
  _fiisBuscaTexto=texto;
  renderFiis();  // NAO chama renderFiisFiltro aqui -- evitaria perder o foco do input a cada tecla digitada
}
function setFiisEscopo(escopo){
  _fiisEscopoAtivo=escopo;
  _fiisSegmentoAtivo='todos';  // reseta os filtros de nivel 2 ao trocar de escopo
  _fiisRiscoAtivo='todos';
  renderFiisFiltro();
  renderFiis();
}
function setFiisSegmento(seg){
  _fiisSegmentoAtivo=seg;
  renderFiisFiltro();
  renderFiis();
}
function setFiisRisco(risco){
  _fiisRiscoAtivo=risco;
  renderFiisFiltro();
  renderFiis();
}

function renderFiis(){
  const cont=document.getElementById('fiis-container');
  if(!cont)return;
  let lista=_fiisEscopoAtivo==='todos'?_fiisTodosData:_fiisData;
  // CORRIGIDO 26/06/2026: filtro de segmento agora funciona em AMBOS os
  // escopos (Todos e Criterio), nao so em Criterio como antes -- bug real
  // reportado pelo usuario: clicar no filtro "FI-Infra" nao mostrava nada,
  // porque FI-Infra so existe na visao "Todos" (sem_dados_financeiros=true,
  // nunca passa pelo criterio de liquidez/DY), mas o filtro de segmento
  // so era aplicado quando _fiisEscopoAtivo==='criterio'. Filtro de RISCO
  // continua so em Criterio (FI-Infra/fora_criterio nao tem nivel_risco
  // classificado, filtrar por risco neles nao faz sentido).
  if(_fiisSegmentoAtivo!=='todos')lista=lista.filter(f=>f.segmento===_fiisSegmentoAtivo);
  if(_fiisEscopoAtivo==='criterio'&&_fiisRiscoAtivo!=='todos')lista=lista.filter(f=>f.nivel_risco===_fiisRiscoAtivo);
  if(_fiisBuscaTexto&&_fiisBuscaTexto.trim()){
    const termo=_fiisBuscaTexto.trim().toUpperCase();
    lista=lista.filter(f=>f.ticker.toUpperCase().includes(termo)||(f.nome_fundo||'').toUpperCase().includes(termo));
  }
  if(!lista.length){
    cont.innerHTML='<p style="color:var(--muted);padding:20px;text-align:center">Nenhum FII nesse filtro.</p>';
    return;
  }
  const RISCO_BADGE={
    high_grade:'<span style="background:rgba(76,217,100,.15);color:var(--green);border:1px solid rgba(76,217,100,.3);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">🟢 HG</span>',
    middle_risk:'<span style="background:rgba(255,204,0,.15);color:#ffcc00;border:1px solid rgba(255,204,0,.3);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">🟡 MR</span>',
    high_yield:'<span style="background:rgba(255,107,107,.15);color:var(--red);border:1px solid rgba(255,107,107,.3);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">🔴 HY</span>',
  };
  const FORA_CRITERIO_BADGE='<span style="background:rgba(255,59,48,.15);color:#ff3b30;border:1px solid rgba(255,59,48,.4);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">⚠ FORA</span>';
  const FI_INFRA_BADGE='<span style="background:rgba(0,180,216,.15);color:#00b4d8;border:1px solid rgba(0,180,216,.4);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">FI-INFRA</span>';
  const rows=lista.map(f=>{
    // FI-Infra (adicionado 26/06/2026): categoria separada de FII
    // tradicional, scraping ainda nao traz cotacao/DY/liquidez -- so
    // confirma EXISTENCIA do ticker (resolve usuario nao achar CDII11).
    // Linha simplificada, sem nenhum dado financeiro, so o ticker e o
    // link para adicionar em analise (usuario decide manualmente, sem
    // criterio automatico ainda).
    // FI-Infra COM dados financeiros ja carregados (busca paralela em
    // loadFiis ja completou) -- mostra normalmente, so com badge
    // FI-INFRA em vez do badge de risco (FI-Infra nao tem classificacao
    // de risco automatica ainda).
    if(f.segmento==='fi-infra'&&!f.sem_dados_financeiros&&f.cotacao!=null){
      const dyColor=f.dy_pct>=8?'var(--green)':'var(--muted)';
      // CORRIGIDO 29/06/2026: agora que FI-Infra tem P/VP, nivel_risco e
      // score reais (classificacao adicionada no backend), mostra o
      // badge de risco de verdade (igual ao FII tradicional) em vez do
      // badge fixo "FI-INFRA", preenche a celula de P/VP que antes era
      // sempre "—", e adiciona a celula de Score que faltava (a linha
      // tinha so 7 <td> de dado contra 9 colunas no cabecalho,
      // desalinhando a tabela -- Vacancia continua "—" pois nao se
      // aplica a FI-Infra, que nao tem imoveis fisicos).
      const badgeRisco = f.fora_criterio
        ? FORA_CRITERIO_BADGE
        : (RISCO_BADGE[f.nivel_risco] || FI_INFRA_BADGE);
      return `<tr id="fii-row-${f.ticker}">
        <td style="padding:6px 8px;font-weight:700">${f.ticker} ${FI_INFRA_BADGE} ${badgeRisco}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${f.fora_criterio?f.motivo_fora_criterio:(f.segmento_fundamentus||'')}</span></td>
        <td style="padding:6px 8px;text-align:right">R$${f.cotacao.toFixed(2)}</td>
        <td style="padding:6px 8px;text-align:right">${f.p_vp!=null?f.p_vp.toFixed(2):'—'}</td>
        <td style="padding:6px 8px;text-align:right;font-weight:700;color:${dyColor}">${f.dy_pct!=null?f.dy_pct.toFixed(2)+'%':'—'}</td>
        <td style="padding:6px 8px;text-align:right">—</td>
        <td style="padding:6px 8px;text-align:right">${f.liquidez!=null?'R$'+(f.liquidez/1000).toFixed(0)+'k/dia':'—'}</td>
        <td style="padding:6px 8px;text-align:right">—</td>
        <td style="padding:6px 8px;text-align:right">${f.score!=null?f.score.toFixed(1):'—'}</td>
        <td id="prov-${f.ticker}" style="padding:6px 8px;text-align:right;color:var(--muted)">—</td>
        <td style="padding:6px 8px;text-align:right;white-space:nowrap">
          ${botaoStatusFii(f.ticker,'Adicionar a Em Análise','background:var(--accent);border:none;color:#fff;padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:700')}
        </td>
      </tr>`;
    }
    // FI-Infra SEM dados financeiros ainda (busca paralela nao completou,
    // ou falhou para esse ticker especifico) -- linha simplificada com
    // mensagem generica, igual antes.
    if(f.sem_dados_financeiros){
      return `<tr id="fii-row-${f.ticker}" style="opacity:.7">
        <td style="padding:6px 8px;font-weight:700">${f.ticker} ${FI_INFRA_BADGE}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${f.segmento_fundamentus||''}</span></td>
        <td colspan="7" style="padding:6px 8px;color:var(--muted);font-size:10px">Buscando dados financeiros... (FI-Infra exige consulta individual, pode levar mais alguns segundos)</td>
        <td style="padding:6px 8px;text-align:right;white-space:nowrap">
          ${botaoStatusFii(f.ticker,'Adicionar a Em Análise (sem dados financeiros automáticos -- você decide manualmente)','background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:600')}
        </td>
      </tr>`;
    }
    // FII fora do criterio: linha simplificada, sem classificacao --
    // usuario pediu explicitamente "fica vazio, nao recebe classificacao
    // nenhuma, so o nome" + marcador vermelho.
    if(f.fora_criterio){
      return `<tr id="fii-row-${f.ticker}" style="opacity:.7">
        <td style="padding:6px 8px;font-weight:700">${f.ticker} ${FORA_CRITERIO_BADGE}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${f.segmento_fundamentus||''}</span></td>
        <td style="padding:6px 8px;text-align:right">R$${(f.cotacao||0).toFixed(2)}</td>
        <td style="padding:6px 8px;text-align:right">${f.p_vp!=null?f.p_vp.toFixed(2):'—'}</td>
        <td style="padding:6px 8px;text-align:right">${f.dy_pct!=null?f.dy_pct.toFixed(2)+'%':'—'}</td>
        <td colspan="5" style="padding:6px 8px;color:var(--muted);font-size:10px" title="${f.motivo_fora_criterio||''}">${f.motivo_fora_criterio||'fora do critério'}</td>
        <td style="padding:6px 8px;text-align:right;white-space:nowrap">
          ${botaoStatusFii(f.ticker,'Adicionar a Em Análise mesmo assim (você assume o risco de estar fora do critério padrão)','background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:600')}
        </td>
      </tr>`;
    }
    const dyCor=f.dy_pct>=8?'var(--green)':'var(--muted)';
    const pvpCor=f.p_vp<1?'var(--green)':'var(--muted)';
    const vac=f.vacancia_pct!=null&&f.vacancia_pct>0?f.vacancia_pct.toFixed(1)+'%':'—';
    const badge=RISCO_BADGE[f.nivel_risco]||'';
    let ffoHtml='—';
    if(f.ffo_yield_pct!=null){
      const sustentavel=f.ffo_yield_pct>=f.dy_pct;
      const cor=sustentavel?'var(--green)':'var(--red)';
      const seta=sustentavel?'▲':'▼';
      ffoHtml=`<span style="color:${cor}" title="${sustentavel?'FFO cobre o dividendo pago -- sinal de sustentabilidade':'Fundo pode estar pagando mais que gera de caixa real -- risco de corte futuro'}">${f.ffo_yield_pct.toFixed(2)}% ${seta}</span>`;
    }
    return `<tr id="fii-row-${f.ticker}">
      <td style="padding:6px 8px;font-weight:700">${f.ticker} ${badge}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${f.segmento_fundamentus}</span></td>
      <td style="padding:6px 8px;text-align:right">R$${f.cotacao!=null?f.cotacao.toFixed(2):'—'}</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:${pvpCor}">${f.p_vp!=null?f.p_vp.toFixed(2):'—'}</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:${dyCor}">${f.dy_pct!=null?f.dy_pct.toFixed(2)+'%':'—'}</td>
      <td style="padding:6px 8px;text-align:right">${ffoHtml}</td>
      <td style="padding:6px 8px;text-align:right">${f.liquidez!=null?'R$'+(f.liquidez/1000).toFixed(0)+'k/dia':'—'}</td>
      <td style="padding:6px 8px;text-align:right">${vac}</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:var(--accent)" title="Score = DY × fator de liquidez × fator de sustentabilidade (FFO vs DY) -- ordena dentro de cada nível de risco, não substitui seu julgamento">${f.score!=null?f.score.toFixed(1):'—'}</td>
      <td id="prov-${f.ticker}" style="padding:6px 8px;text-align:right;color:var(--muted)">—</td>
      <td style="padding:6px 8px;text-align:right;white-space:nowrap">
        ${botaoStatusFii(f.ticker,'Adicionar a Em Análise','background:var(--accent);border:none;color:#fff;padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:700')}
      </td>
    </tr>`;
  }).join('');
  // ADICIONADO 30/06/2026 -- limite de auto-carregamento do ultimo
  // provento: a lista Criterio pode ter ate ~249 FIIs, e cada provento
  // exige 1 chamada ao StatusInvest -- buscar tudo de uma vez seria
  // pesado/lento (risco de timeout no Render free tier, mesmo padrao ja
  // visto com FI-Infra). So carrega automaticamente quando o filtro
  // atual tem ate 30 itens (normal depois de filtrar por segmento/risco/
  // busca); acima disso, mostra aviso pedindo para filtrar mais.
  const LIMITE_AUTO_PROVENTO=30;
  const avisoProvento = lista.length>LIMITE_AUTO_PROVENTO
    ? `<div style="font-size:10px;color:var(--muted);margin-bottom:8px;padding:6px 8px;background:var(--bg3);border-radius:4px">ℹ Coluna "Últ. Prov." carrega automaticamente só com até ${LIMITE_AUTO_PROVENTO} itens no filtro (hoje: ${lista.length}). Filtre por segmento, risco ou busca para ver os proventos.</div>`
    : '';
  cont.innerHTML=`
  <div style="font-size:10px;color:var(--muted);margin-bottom:8px">${lista.length} FIIs neste filtro · agrupado por nível de risco, ordenado por score (DY×liquidez×sustentabilidade) dentro de cada grupo</div>
  ${avisoProvento}
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="border-bottom:1px solid var(--border);color:var(--muted);text-align:left">
      <th style="padding:6px 8px">Ticker</th>
      <th style="padding:6px 8px;text-align:right">Cotação</th>
      <th style="padding:6px 8px;text-align:right" title="Preço sobre Valor Patrimonial -- abaixo de 1,0 indica desconto">P/VP</th>
      <th style="padding:6px 8px;text-align:right" title="Dividend Yield anual">DY</th>
      <th style="padding:6px 8px;text-align:right" title="FFO Yield -- caixa operacional real gerado pelo fundo, sem ganhos extraordinários. ▲ acima do DY = sustentável (sobra de caixa). ▼ abaixo do DY = fundo pode estar consumindo patrimônio para manter o dividendo">FFO ⓘ</th>
      <th style="padding:6px 8px;text-align:right" title="Volume financeiro médio negociado por dia">Liquidez</th>
      <th style="padding:6px 8px;text-align:right" title="Vacância média dos imóveis (relevante para FIIs de tijolo)">Vacância</th>
      <th style="padding:6px 8px;text-align:right">Score</th>
      <th style="padding:6px 8px;text-align:right" title="Último rendimento pago, via StatusInvest (carregado automaticamente só quando o filtro tem até 30 itens)">Últ. Prov.</th>
      <th style="padding:6px 8px;text-align:right">Ação</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>
  </div>`;

  // Carrega o ultimo provento so se a lista estiver dentro do limite (ver
  // LIMITE_AUTO_PROVENTO acima) -- escalonado para nao disparar tudo no
  // mesmo instante. Pula linhas que nao tem celula de provento (FI-Infra
  // ainda sem dados financeiros, por exemplo).
  if(lista.length<=LIMITE_AUTO_PROVENTO){
    let delayProv2=0;
    lista.forEach(f=>{
      if(document.getElementById('prov-'+f.ticker)){
        setTimeout(()=>_buscarEPreencherProvento('prov-'+f.ticker, f.ticker, f.segmento, f.cotacao), delayProv2);
        delayProv2+=300;
      }
    });
  }
}

// Adicionado 25/06/2026 -- migracao de FII selecionado para Em Analise.
// Reaproveita o MESMO endpoint POST /analises ja usado para estruturadas
// (Fase A/B) -- usuario decidiu que a "foto" do FII e tirada no MOMENTO da
// selecao (nao retroativa, mesmo se o usuario ja possui o FII ha tempo --
// simplificacao aceita explicitamente pelo usuario: "pega foto de como se
// eu tivesse comprando no momento da selecao").
async function aprovarFiiParaAnalise(ticker){
  // CORRIGIDO 26/06/2026 -- busca em AMBAS as listas (Criterio + Todos),
  // ja que o botao "+ Em Analise" agora tambem aparece para FIIs
  // fora_criterio (visao Todos) -- antes so buscava em _fiisData
  // (so Criterio), e o clique nao fazia nada para FIIs fora do criterio.
  const f=_fiisData.find(x=>x.ticker===ticker)||_fiisTodosData.find(x=>x.ticker===ticker);
  if(!f)return;

  // FI-Infra (adicionado 26/06/2026): sem dados financeiros automaticos
  // ainda -- f.cotacao/f.dy_pct/f.p_vp sao todos null, .toFixed() quebraria.
  // Pede o preco MANUALMENTE em vez de tentar usar dado que nao existe.
  let precoFoto = f.cotacao;
  if(f.sem_dados_financeiros){
    const precoStr=prompt(`${ticker} é FI-Infra -- ainda não temos cotação automática.\n\nDigite o preço atual (consulte investidor10.com.br/fiis/${ticker.toLowerCase()}/ ou seu home broker):`);
    if(!precoStr)return;
    precoFoto=parseFloat(precoStr.replace(',','.'));
    if(isNaN(precoFoto)||precoFoto<=0){alert('Preço inválido.');return;}
  }

  const avisoFora=f.fora_criterio?`\n\n⚠ Este FII está FORA do critério padrão (${f.motivo_fora_criterio}). Você está assumindo esse risco conscientemente.`:'';

  // ADICIONADO 30/06/2026 -- controle de duplicidade: antes nao havia
  // nenhuma checagem, entao clicar 2x no mesmo ticker (ou clicar de
  // novo dias depois sem perceber que ja estava em analise) criava
  // registros duplicados em analises.json. Verifica se ja existe uma
  // analise ATIVA (em_analise ou ativa) para este ticker antes de
  // permitir adicionar de novo.
  if(_analiseData){
    const tickerCompleto = ticker+'.SA';
    const jaExiste = _analiseData.find(a =>
      (a.ticker===tickerCompleto || a.ticker===ticker) &&
      (a.status==='em_analise' || a.status==='ativa')
    );
    if(jaExiste){
      alert(`${ticker} já está em "${jaExiste.status==='ativa'?'Ativa (posição real)':'Em Análise'}" (id: ${jaExiste.id}).\n\nNão é possível adicionar de novo enquanto a análise anterior estiver em aberto. Rejeite ou encerre a análise existente primeiro, se quiser registrar uma nova.`);
      return;
    }
  }

  const ok=confirm(`Adicionar ${ticker} a "Em Análise"? Isso grava no repositório com preço de referência R$${precoFoto.toFixed(2)}.${avisoFora}`);
  if(!ok)return;
  const linha=document.getElementById('fii-row-'+ticker);
  try{
    const hoje=new Date().toISOString().slice(0,10);
    const body={
      ticker: ticker+'.SA',
      nome: `${ticker} - FII ${f.segmento_fundamentus||'(sem classificação)'}`,
      data_foto: hoje,
      preco_foto: precoFoto,
      tipo_estrutura: 'fii',
      prazo_dias: 9999,  // FIIs sao perpetuos, sem vencimento -- convencao documentada no backend
      dy_anual_pct: f.dy_pct,
      p_vp: f.p_vp,
      liquidez: f.liquidez,
      segmento: f.segmento,
      nivel_risco: f.nivel_risco,
      origem: 'screening_fiis',
      status: 'em_analise',
      backtest: false,
      // CORRIGIDO 29/06/2026: f.p_vp pode ser null mesmo com
      // sem_dados_financeiros=false (FI-Infra tem P/VP, mas FII
      // tradicional do Fundamentus tambem pode vir sem ele em casos
      // raros) -- f.p_vp.toFixed(2) direto quebrava com
      // "Cannot read properties of null". Usa fallback textual.
      observacao: f.sem_dados_financeiros
        ? `FI-Infra adicionado via screening em ${hoje}. Preço informado MANUALMENTE pelo usuário (R$${precoFoto.toFixed(2)}) -- dados financeiros automáticos (DY, P/VP, liquidez) ainda não disponíveis para esta categoria.`
        : `FII adicionado via screening em ${hoje}. P/VP=${f.p_vp!=null?f.p_vp.toFixed(2):'N/D'}, DY=${f.dy_pct!=null?f.dy_pct.toFixed(2)+'%':'N/D'}, segmento=${f.segmento_fundamentus||f.segmento}, nível de risco=${f.nivel_risco||'N/A'}. Foto tirada no momento da seleção (não retroativa ao histórico de compra real, se já possuído antes).`
    };
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const r=await fetch(B+'/analises',{
      method:'POST',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    if(linha){linha.style.opacity='.4';linha.querySelector('button').textContent='✓ Adicionado';linha.querySelector('button').disabled=true;}
  }catch(e){
    alert('Erro ao adicionar à análise: '+e.message);
  }
}

// Adicionado 25/06/2026 -- aba Carteira FIIs, le carteira_fiis.json
// (arquivo proprio, separado de analises.json/positions.json por decisao
// do usuario). Mostra FIIs ativos com dias desde ativacao.
async function loadCarteiraFiis(){
  const cont=document.getElementById('carteirafiis-container');
  const btn=document.getElementById('btn-carteirafiis-reload');
  if(!cont)return;
  cont.innerHTML='<p style="color:var(--muted);padding:20px;text-align:center">Carregando carteira...</p>';
  if(btn){btn.disabled=true;btn.style.opacity='.6';}
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const r=await fetch(B+'/carteira-fiis',{signal:ctrl.signal,cache:'no-store'});
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    renderCarteiraFiis(d.carteira||[]);
    loadCarteiraFiisResumo();
  }catch(e){
    cont.innerHTML='<p style="color:var(--red);padding:20px">⚠ Erro ao carregar carteira: '+e.message+'</p>';
  }finally{
    if(btn){btn.disabled=false;btn.style.opacity='1';}
  }
}

function renderCarteiraFiis(carteira){
  const cont=document.getElementById('carteirafiis-container');
  if(!cont)return;
  const ativos=carteira.filter(f=>f.status==='ativa');
  const encerrados=carteira.filter(f=>f.status==='encerrada');
  if(!ativos.length&&!encerrados.length){
    cont.innerHTML='<p style="color:var(--muted);padding:20px;text-align:center">Nenhum FII na carteira ainda. Ative algum em "Em Análise".</p>';
    return;
  }
  const hoje=new Date();
  const linhaAtivo=f=>{
    const dataAtiv=new Date(f.data_ativacao);
    const dias=Math.floor((hoje-dataAtiv)/86400000);
    return `<tr id="cfii-row-${f.id}">
      <td style="padding:6px 8px;font-weight:700">${f.ticker}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${f.nome_fundo||''}</span></td>
      <td style="padding:6px 8px;text-align:right">R$${f.preco_ativacao.toFixed(2)}</td>
      <td style="padding:6px 8px;text-align:right">${f.dy_anual_pct_ativacao!=null?f.dy_anual_pct_ativacao.toFixed(2)+'%':'—'}</td>
      <td style="padding:6px 8px;text-align:right">${f.data_ativacao}</td>
      <td style="padding:6px 8px;text-align:right">${dias}d</td>
      <td id="cfii-prov-${f.id}" style="padding:6px 8px;text-align:right;color:var(--muted)" class="loading">...</td>
      <td id="cfii-12m-${f.id}" style="padding:6px 8px;text-align:right;color:var(--muted)" class="loading">...</td>
      <td style="padding:6px 8px;text-align:right">
        <button onclick="encerrarFiiCarteira('${f.id}')" style="background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:600">Encerrar</button>
      </td>
    </tr>`;
  };
  const linhaEncerrado=f=>{
    const cor = f.resultado==='sucesso' ? 'var(--green,#2ecc71)' : f.resultado==='fracasso' ? 'var(--red,#e74c3c)' : 'var(--muted)';
    const valorTxt = f.valor_financeiro_resultado!=null
      ? (f.valor_financeiro_resultado>=0?'+':'')+'R$'+f.valor_financeiro_resultado.toFixed(2)
      : '—';
    return `<tr>
      <td style="padding:6px 8px;font-weight:700">${f.ticker}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${f.nome_fundo||''}</span></td>
      <td style="padding:6px 8px;text-align:right">R$${f.preco_ativacao.toFixed(2)}</td>
      <td style="padding:6px 8px;text-align:right">${f.data_encerramento||'—'}</td>
      <td style="padding:6px 8px;text-align:right;color:${cor};font-weight:600">${f.resultado||'—'}</td>
      <td style="padding:6px 8px;text-align:right;color:${cor};font-weight:600">${valorTxt}</td>
      <td style="padding:6px 8px;font-size:9px;color:var(--muted)" title="${f.observacao_encerramento||''}">${f.observacao_encerramento||''}</td>
    </tr>`;
  };
  cont.innerHTML=`
  <div style="font-size:10px;color:var(--muted);margin-bottom:8px">${ativos.length} ativos${encerrados.length?' · '+encerrados.length+' encerrados':''}</div>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="border-bottom:1px solid var(--border);color:var(--muted);text-align:left">
      <th style="padding:6px 8px">Ticker</th>
      <th style="padding:6px 8px;text-align:right">Preço ativ.</th>
      <th style="padding:6px 8px;text-align:right">DY na ativ.</th>
      <th style="padding:6px 8px;text-align:right">Data</th>
      <th style="padding:6px 8px;text-align:right">Dias</th>
      <th style="padding:6px 8px;text-align:right" title="Último rendimento pago (R$/cota) · StatusInvest">Últ. Prov.</th>
      <th style="padding:6px 8px;text-align:right" title="Total de rendimentos pagos nos últimos 12 meses (R$/cota) · 2 semestres StatusInvest">12M (R$)</th>
      <th style="padding:6px 8px;text-align:right">Ação</th>
    </tr></thead>
    <tbody>${ativos.map(linhaAtivo).join('')}</tbody>
  </table>
  </div>
  ${encerrados.length?`
  <div style="font-size:10px;color:var(--muted);margin:16px 0 8px">📂 Encerrados (${encerrados.length})</div>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="border-bottom:1px solid var(--border);color:var(--muted);text-align:left">
      <th style="padding:6px 8px">Ticker</th>
      <th style="padding:6px 8px;text-align:right">Preço ativ.</th>
      <th style="padding:6px 8px;text-align:right">Encerrado em</th>
      <th style="padding:6px 8px;text-align:right">Resultado</th>
      <th style="padding:6px 8px;text-align:right">Valor (R$)</th>
      <th style="padding:6px 8px">Obs.</th>
    </tr></thead>
    <tbody>${encerrados.map(linhaEncerrado).join('')}</tbody>
  </table>
  </div>`:''}`;

  // Busca histórico completo de proventos para cada FII ativo, escalonado
  // para não disparar todas as chamadas ao StatusInvest simultaneamente.
  // Endpoint novo: /carteira-fiis/proventos (retorna 12M + acumulado desde ativação).
  let delay=0;
  ativos.forEach(f=>{
    setTimeout(()=>carregarProventosCarteira(f), delay);
    delay+=500;
  });
}

// Adicionado 05/07/2026 -- card de resumo agregado da Carteira FIIs
// (volatilidade real via correlacao, espelhando o mesmo card ja existente
// em Carteira de ETFs / renderEtfCarteira). Fica em div separada
// (#carteirafiis-resumo), nao mexe na tabela nem na logica de proventos
// existente em renderCarteiraFiis.
async function loadCarteiraFiisResumo(){
  const div=document.getElementById('carteirafiis-resumo');
  if(!div)return;
  div.style.display='block';
  div.innerHTML='<div style="border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:14px;background:var(--bg2)">'+
    '<div style="font-size:11px;color:var(--muted)">Calculando resumo da carteira (vol. real com correlação entre ativos)...</div></div>';
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),18000);
    const r=await fetch(B+'/carteira-fiis/resumo',{signal:ctrl.signal,cache:'no-store'});
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    if(!d.itens||!d.itens.length){div.style.display='none';return;}
    const retornoColor=d.retorno_pct==null?'var(--muted)':(d.retorno_pct>=0?'var(--green)':'var(--red)');
    let volLinha='<span style="color:var(--muted)">Volatilidade da carteira indisponível (histórico insuficiente para 2+ ativos).</span>';
    if(d.vol_carteira_pct!=null){
      const diff=d.vol_soma_simples_pct!=null?(d.vol_soma_simples_pct-d.vol_carteira_pct):null;
      volLinha='Vol. anualizada da carteira (correlação real): <b style="color:var(--accent)">'+d.vol_carteira_pct.toFixed(1)+'%</b>'+
        (diff!=null&&diff>0.05?' <span style="color:var(--muted);font-size:10px">(vs '+d.vol_soma_simples_pct.toFixed(1)+'% se os FIIs fossem 100% correlacionados — diversificação está descontando ~'+diff.toFixed(1)+'pp)</span>':'');
    }
    div.innerHTML='<div style="border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:14px;background:var(--bg2)">'+
      '<div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:8px">'+
        '<div><div style="font-size:10px;color:var(--muted)">TOTAL INVESTIDO</div><div style="font-size:16px;font-weight:700">R$ '+d.total_investido.toFixed(2)+'</div></div>'+
        '<div><div style="font-size:10px;color:var(--muted)">VALOR ATUAL</div><div style="font-size:16px;font-weight:700">R$ '+d.valor_atual.toFixed(2)+'</div></div>'+
        '<div><div style="font-size:10px;color:var(--muted)">RETORNO</div><div style="font-size:16px;font-weight:700;color:'+retornoColor+'">'+(d.retorno_pct!=null?(d.retorno_pct>=0?'+':'')+d.retorno_pct.toFixed(2)+'%':'—')+'</div></div>'+
      '</div>'+
      '<div style="font-size:11px;color:var(--text)">'+volLinha+'</div>'+
      '<div style="font-size:9px;color:var(--muted);margin-top:6px">'+(d.nota||'')+'</div>'+
    '</div>';
  }catch(e){
    div.innerHTML='<div style="border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:14px;background:var(--bg2)">'+
      '<span style="color:var(--red);font-size:11px">Erro ao calcular resumo: '+e.message+'</span></div>';
  }
}

// GENERALIZADO 30/06/2026 -- antes so existia para a Carteira de FIIs,
// agora tambem usado pelo screening (renderFiis). Recebe o id do
// elemento <td> alvo diretamente, em vez de assumir o padrao
// 'cfii-prov-'+id (que so fazia sentido para a Carteira).
async function _buscarEPreencherProvento(idCelula,tickerLimpo,segmento,cotacao){
  const cel=document.getElementById(idCelula);
  if(!cel)return;
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),10000);
    const r=await fetch(B+'/fii-ultimo-provento?ticker='+encodeURIComponent(tickerLimpo)+'&segmento='+encodeURIComponent(segmento||''),{signal:ctrl.signal});
    const d=await r.json();
    if(d.encontrado&&d.valor!=null){
      let sufixoPct='';
      if(cotacao!=null&&cotacao>0){
        const pctMes=(d.valor/cotacao)*100;
        sufixoPct=` <span style="color:var(--green);font-weight:700">(${pctMes.toFixed(2)}%/mês)</span>`;
      }
      cel.innerHTML='R$'+d.valor.toFixed(2)+' ('+d.data_pagamento+')'+sufixoPct;
      cel.title='Fonte: StatusInvest. %/mês = último provento ÷ cotação atual';
      cel.classList.remove('loading');
      cel.style.color='var(--text)';
    }else{
      cel.textContent='—';
      cel.classList.remove('loading');
    }
  }catch(e){
    if(cel){cel.textContent='—';cel.classList.remove('loading');}
  }
}

// Adicionado 30/06/2026 -- carrega histórico completo (12M + acumulado desde ativação)
// para um FII ativo na carteira. Usa o novo endpoint /carteira-fiis/proventos.
async function carregarProventosCarteira(f){
  const celProv=document.getElementById('cfii-prov-'+f.id);
  const cel12m=document.getElementById('cfii-12m-'+f.id);
  const limpar=(cel,txt)=>{if(cel){cel.textContent=txt||'—';cel.classList.remove('loading');cel.style.color='var(--muted)';}};
  try{
    const ticker=f.ticker.replace('.SA','');
    const params=new URLSearchParams({
      ticker,
      segmento:f.segmento||'',
      preco_ativacao:f.preco_ativacao||0,
      data_ativacao:f.data_ativacao||''
    });
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const r=await fetch(B+'/carteira-fiis/proventos?'+params,{signal:ctrl.signal});
    const d=await r.json();
    if(!d.encontrado){
      limpar(celProv);limpar(cel12m);
      return;
    }
    // Último provento
    if(celProv&&d.ultimo_provento?.valor!=null){
      const pct=f.preco_ativacao>0?` <span style="color:var(--green);font-size:10px">(${(d.ultimo_provento.valor/f.preco_ativacao*100).toFixed(2)}%/mês)</span>`:'';
      celProv.innerHTML=`R$${d.ultimo_provento.valor.toFixed(2)}<br><span style="font-size:9px;color:var(--muted)">${d.ultimo_provento.data_pagamento||''}</span>${pct}`;
      celProv.classList.remove('loading');celProv.style.color='var(--text)';
    } else limpar(celProv);
    // Total 12M
    if(cel12m&&d.total_12m!=null){
      const dy=d.dy_12m_pct!=null?` <span style="color:var(--green);font-size:10px">(${d.dy_12m_pct.toFixed(1)}% a.a.)</span>`:'';
      cel12m.innerHTML=`R$${d.total_12m.toFixed(2)}${dy}`;
      cel12m.title='Soma dos 2 semestres mais recentes · StatusInvest';
      cel12m.classList.remove('loading');cel12m.style.color='var(--text)';
    } else limpar(cel12m);

  }catch(e){
    limpar(celProv);limpar(cel12m);
  }
}
async function carregarUltimoProventoCarteira(f){
  // Mantido para compatibilidade -- novo fluxo usa carregarProventosCarteira
  await carregarProventosCarteira(f);
}

async function loadRankingPosicoes(tipo){
  const cont=document.getElementById('ranking-posicoes-container');
  if(!cont)return;
  const nomes={
    lancamento_coberto:'Lançamento Coberto', retorno_controlado:'Retorno Controlado',
    bidirecional:'Bidirecional', put_seco:'Venda de Put a Seco'
  };
  cont.innerHTML='<p style="padding:10px;text-align:center">Calculando ranking...</p>';
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const r=await fetch(B+'/posicoes/ranking/'+tipo,{signal:ctrl.signal});
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    if(d.total===0){
      cont.innerHTML=`<p style="padding:10px;text-align:center">Nenhuma posição ativa na categoria "${nomes[tipo]}" no momento.</p>`;
      return;
    }
    const linhas=d.itens.map(i=>{
      if(i.erro){
        return `<tr><td style="padding:6px 8px;font-weight:700">${i.ticker}</td><td colspan="4" style="padding:6px 8px;color:var(--red)">Erro: ${i.erro}</td></tr>`;
      }
      const p=i.probabilidade_sucesso_pct;
      const cor = p>=70?'var(--green,#2ecc71)':p>=40?'var(--warn,#e6a817)':'var(--red,#e74c3c)';
      return `<tr>
        <td style="padding:6px 8px;font-weight:700">${i.ticker.replace('.SA','')}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${i.estrategia||''}</span></td>
        <td style="padding:6px 8px;text-align:right">${i.vencimento||'—'}</td>
        <td style="padding:6px 8px;text-align:right">${i.dias_restantes!=null?i.dias_restantes+'d':'—'}</td>
        <td style="padding:6px 8px;text-align:right;font-weight:700;color:${cor}">${p!=null?p.toFixed(1)+'%':'—'}</td>
      </tr>`;
    }).join('');
    cont.innerHTML=`
    <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Ranking — ${nomes[tipo]} (${d.total}) · ordenado por menor probabilidade de sucesso primeiro (mais atenção necessária no topo)</div>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:11px">
      <thead><tr style="border-bottom:1px solid var(--border);color:var(--muted);text-align:left">
        <th style="padding:6px 8px">Ticker</th>
        <th style="padding:6px 8px;text-align:right">Vencimento</th>
        <th style="padding:6px 8px;text-align:right">Dias rest.</th>
        <th style="padding:6px 8px;text-align:right">Prob. sucesso</th>
      </tr></thead>
      <tbody>${linhas}</tbody>
    </table>
    </div>`;
  }catch(e){
    cont.innerHTML=`<p style="padding:10px;color:var(--red)">Erro ao calcular ranking: ${e.message}</p>`;
  }
}

async function encerrarFiiCarteira(id){
  const ok=confirm('Confirma ENCERRAR (vendeu) este FII da carteira?');
  if(!ok)return;

  // ADICIONADO 11/07/2026 -- captura manual do resultado no encerramento
  // (nao da pra calcular automatico: venda quase sempre parcial + proventos
  // recebidos no meio nao sao armazenados). Segue o mesmo padrao de prompt()
  // ja usado no app (ex: preco manual de FI-Infra). Todos os 3 campos sao
  // OPCIONAIS -- se o usuario cancelar/deixar em branco, encerra do mesmo
  // jeito, so sem entrar no somatorio de aproveitamento.
  let resultado=null, valorStr=null, observacao=null;
  const resp=prompt('Resultado desta operação? Digite: sucesso, fracasso ou parcial\n(deixe em branco para pular e encerrar sem registrar resultado)');
  if(resp&&['sucesso','fracasso','parcial'].includes(resp.trim().toLowerCase())){
    resultado=resp.trim().toLowerCase();
    valorStr=prompt('Valor financeiro do resultado (R$)? Considere venda + proventos recebidos no período.\nEx: 1000 para ganho de R$1.000, -500 para perda de R$500');
    observacao=prompt('Observação (opcional, ex: "vendeu 60% da posição"):');
  }

  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const bodyObj={status:'encerrada'};
    if(resultado)bodyObj.resultado=resultado;
    if(valorStr&&!isNaN(parseFloat(valorStr)))bodyObj.valor_financeiro_resultado=parseFloat(valorStr);
    if(observacao)bodyObj.observacao_encerramento=observacao;
    const r=await fetch(B+'/carteira-fiis/'+encodeURIComponent(id)+'/status',{
      method:'PUT',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
      body:JSON.stringify(bodyObj)
    });
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    await loadCarteiraFiis();
  }catch(e){
    alert('Erro ao encerrar: '+e.message);
  }
}

// ADICIONADO 15/07/2026 -- mesmo padrao de encerrarFiiCarteira (rotas_fiis.py
// 11/07/2026): 3 campos opcionais via prompt(), nenhum calculado sozinho.
async function encerrarEtfCarteira(ticker){
  const ok=confirm('Confirma ENCERRAR (vendeu) '+ticker+' da carteira?');
  if(!ok)return;

  let resultado=null, valorStr=null, observacao=null;
  const resp=prompt('Resultado desta operação? Digite: sucesso, fracasso ou parcial\n(deixe em branco para pular e encerrar sem registrar resultado)');
  if(resp&&['sucesso','fracasso','parcial'].includes(resp.trim().toLowerCase())){
    resultado=resp.trim().toLowerCase();
    valorStr=prompt('Valor financeiro do resultado (R$)? Considere venda no preço de hoje.\nEx: 1000 para ganho de R$1.000, -500 para perda de R$500');
    observacao=prompt('Observação (opcional, ex: "vendeu metade da posição"):');
  }

  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const bodyObj={status:'encerrada'};
    if(resultado)bodyObj.resultado=resultado;
    if(valorStr&&!isNaN(parseFloat(valorStr)))bodyObj.valor_financeiro_resultado=parseFloat(valorStr);
    if(observacao)bodyObj.observacao_encerramento=observacao;
    const r=await fetch(B+'/etfs/carteira/'+encodeURIComponent(ticker)+'/status',{
      method:'PUT',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
      body:JSON.stringify(bodyObj)
    });
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    await loadETFs();
  }catch(e){
    alert('Erro ao encerrar: '+e.message);
  }
}

function tg(id){
  const b=document.getElementById('sb-'+id),a=document.getElementById('ar-'+id);
  if(!b)return;const op=b.style.display!=='block';
  b.style.display=op?'block':'none';
  if(a)a.textContent=op?'▲':'▼';
  if(op&&!b.dataset.l){b.dataset.l='1';loadSeg(id);}
}

// Toggle simples para as tabelas de Cotações (EUA/B3/Commodities) — os
// dados dessas tabelas já são carregados por main()/fMacro() independente
// do estado expandido, então aqui é só esconder/mostrar visualmente, sem
// disparar nenhum fetch (diferente de tg(), que carrega dados por setor).
function togCot(id){
  const w=document.getElementById('cot-'+id+'-wrap'),a=document.getElementById('ar-cot-'+id);
  if(!w)return;
  const op=w.style.display==='none';
  w.style.display=op?'block':'none';
  if(a)a.textContent=op?'▼':'▶';
}

async function loadSeg(id){
  const g=document.getElementById('g-'+id);if(!g)return;
  g.classList.remove('grid');g.style.display='block';
  const pfx=id+'_';
  // Grupos onde a metrica de concentracao vs S&P 500 faz sentido (areas de
  // alta concentracao na narrativa de bolha de IA). Constante unica usada
  // nas 2 checagens abaixo para nao precisar atualizar 2 lugares ao
  // adicionar um grupo novo (lição da v10.11-13: extensao parcial gerou
  // bug por falta de cobertura em 1 dos lugares).
  const GRUPOS_COM_CONCENTRACAO=['semi','m7','software'];
  if(USSEG[id]){
    const tks=USSEG[id];
    // Bloco de concentracao vs S&P 500. Adicionado 23/06/2026, expandido
    // para software na mesma data.
    let concHtml='';
    if(GRUPOS_COM_CONCENTRACAO.includes(id)){
      concHtml='<div id="conc-'+id+'" style="margin-bottom:10px;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:12px;color:var(--muted)">Calculando peso no S&amp;P 500...</div>';
    }
    g.innerHTML=concHtml+'<table class="tbl-mkt tbl-seg"><colgroup><col style="width:40%"><col style="width:20%"><col style="width:20%"><col style="width:20%"></colgroup><thead><tr><th>Ativo</th><th class="r">Último</th><th class="r">Variação</th><th class="r">Var.%</th></tr></thead><tbody>'+
      tks.map(t=>{const tid=t.replace(/[^a-zA-Z0-9]/g,'_');const nome=US_NOMES[t];return '<tr><td><div class="sym">'+t+'</div>'+(nome?'<div class="desc">'+nome+'</div>':'')+'</td><td class="r"><span class="val loading" id="'+pfx+tid+'_p">—</span></td><td class="r"><span class="chg" id="'+pfx+tid+'_v">—</span></td><td class="r"><span class="chg" id="'+pfx+tid+'_c">—</span></td></tr>';}).join('')+'</tbody></table>';
    if(GRUPOS_COM_CONCENTRACAO.includes(id)){
      // CORRIGIDO 23/06/2026 (5a correcao real): o bug NAO era timeout nem
      // paralelizacao -- era que r.ok e false para o 502 que o backend
      // retorna deliberadamente em caso de erro, e o '.then(r=>r.ok?
      // r.json():null)' descartava o corpo JSON (com a mensagem de erro
      // detalhada) sempre que o status nao era 2xx, mostrando so 'sem
      // resposta do servidor' mesmo quando o backend tinha mandado um erro
      // claro. Causa raiz REAL do erro em si (confirmada testando local
      // com Flask test_client): Yahoo retorna status 403 (bloqueio ativo)
      // para as chamadas de marketCap em v8/finance/chart nesses tickers.
      fetch(B+'/us/concentracao?grupo='+id).then(r=>r.json().catch(()=>null)).then(d=>{
        const el=document.getElementById('conc-'+id);
        if(!el)return;
        if(!d||d.error){el.textContent='Não foi possível calcular: '+(d&&d.error?d.error:'sem resposta do servidor');return;}
        // CORRIGIDO 23/06/2026 (8a correcao): usuario notou peso_pct
        // subestimado (25.62% para m7, vs 33-35% real conhecido) porque
        // tickers que falhavam em todas as fontes eram omitidos da soma
        // SEM nenhum aviso visivel. Agora mostra quantos tickers faltam,
        // se for o caso.
        const incompleto = d.tickers_sem_dado && Object.keys(d.tickers_sem_dado).length > 0;
        const avisoIncompleto = incompleto
          ? '<br><span style="color:var(--warn,#e8a33d)">⚠ incompleto: faltam '+Object.keys(d.tickers_sem_dado).join(', ')+'</span>'
          : '';
        // Adicionado 23/06/2026 -- extrapolacao do setor de software
        // completo (115 holdings do IGV) via regra de 3, usando o top 10
        // conhecido. Usuario pediu explicitamente para deixar o METODO
        // visivel, nao so o numero final ("mais importante deixar claro
        // do que um numero sem explicacao").
        const ext = d.extrapolacao_setor_completo;
        const extHtml = ext && ext.setor_completo_peso_pct_sp500_estimado != null
          ? '<br><span style="color:var(--muted)">≈ setor de software completo (115 cias do IGV, estimado): <b style="color:var(--text)">'+ext.setor_completo_peso_pct_sp500_estimado+'%</b> do S&P 500 — top 10 conhecido (US$ '+(ext.top10_marketcap_usd/1e12).toFixed(2)+'T) representa '+ext.top10_peso_pct_no_indice+'% do ETF (ref. '+ext.top10_peso_pct_ref_data+'); resto extrapolado por regra de 3, não somado diretamente</span>'
          : (ext && ext.erro ? '<br><span style="color:var(--warn,#e8a33d)">⚠ '+ext.erro+'</span>' : '');
        el.innerHTML='<b style="color:var(--text)">'+d.peso_pct_sp500+'%</b> do S&P 500 · grupo vale <b>US$ '+d.market_cap_grupo_tri_usd+'T</b> de um total de US$ '+d.sp500_total_tri_usd+'T (ref. '+d.sp500_total_ref_data+', aproximado)'+avisoIncompleto+extHtml;
      }).catch(()=>{const el=document.getElementById('conc-'+id);if(el)el.textContent='Não foi possível calcular a concentração agora.';});
    }
    try{
      const r=await fetch(B+'/us/quotes?tickers='+tks.join(','));
      if(!r.ok)return;
      const d=await r.json();
      Object.entries(d).forEach(([t,v])=>{
        const tid=t.replace(/[^a-zA-Z0-9]/g,'_');
        const ep=document.getElementById(pfx+tid+'_p');
        if(ep&&v.price){ep.textContent='$'+Number(v.price).toFixed(2);ep.classList.remove('loading');}
        if(v.price&&v.prev)ChTbl(pfx+tid+'_v',pfx+tid+'_c',v.price,v.prev,'u');
      });
    }catch(e){}
    return;
  }
  const tks=SEG[id];if(!tks)return;
  g.innerHTML='<table class="tbl-mkt tbl-seg"><colgroup><col style="width:40%"><col style="width:20%"><col style="width:20%"><col style="width:20%"></colgroup><thead><tr><th>Ativo</th><th class="r">Último</th><th class="r">Variação</th><th class="r">Var.%</th></tr></thead><tbody>'+
    tks.map(t=>{const tid=t.toLowerCase();return '<tr><td><div class="sym">'+t+'</div></td><td class="r"><span class="val loading" id="'+pfx+tid+'_p">—</span></td><td class="r"><span class="chg" id="'+pfx+tid+'_v">—</span></td><td class="r"><span class="chg" id="'+pfx+tid+'_c">—</span></td></tr>';}).join('')+
    '</tbody></table>';
  try{
    const r=await fetch(B+'/tv/brazil',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbols:{tickers:tks.map(t=>'BMFBOVESPA:'+t)},columns:['close','change_abs']})});
    if(!r.ok)throw new Error('TV fail');
    const d=await r.json();
    const loaded=new Set();
    (d.data||[]).forEach(x=>{
      const t=x.s.replace('BMFBOVESPA:','').toLowerCase();
      const[c,ca]=x.d||[];
      if(c!=null){
        const ep=document.getElementById(pfx+t+'_p');
        if(ep){ep.textContent=fR(c);ep.classList.remove('loading');loaded.add(t);}
        ChTbl(pfx+t+'_v',pfx+t+'_c',c,c-(ca||0),'r');
      }
    });
    // Fallback para tickers que TV não retornou: /brapi → /indicators
    const missing=tks.filter(t=>!loaded.has(t.toLowerCase()));
    if(missing.length>0){
      await Promise.all(missing.map(async t=>{
        const tid=t.toLowerCase();
        const ep=document.getElementById(pfx+tid+'_p');
        if(!ep)return;
        // 1) tenta /brapi (rápido, só cotação)
        try{
          const ctrlB=new AbortController();setTimeout(()=>ctrlB.abort(),8000);
          const rb=await fetch(B+'/brapi/'+t+'.SA',{signal:ctrlB.signal});
          if(rb.ok){
            const db=await rb.json();
            if(db.price){
              ep.textContent=fR(db.price);ep.classList.remove('loading');
              ChTbl(pfx+tid+'_v',pfx+tid+'_c',db.price,db.prev||db.price,'r');
              return;
            }
          }
        }catch(e2){}
        // 2) fallback /indicators (mais pesado mas completo)
        try{
          const ctrlI=new AbortController();setTimeout(()=>ctrlI.abort(),15000);
          const r2=await fetch(B+'/indicators/'+t+'.SA',{signal:ctrlI.signal});
          if(!r2.ok)return;
          const d2=await r2.json();
          if(d2.preco_atual){
            ep.textContent=fR(d2.preco_atual);ep.classList.remove('loading');
            if(d2.preco_anterior)ChTbl(pfx+tid+'_v',pfx+tid+'_c',d2.preco_atual,d2.preco_anterior,'r');
          }
        }catch(e2){}
      }));
    }
  }catch(e){
    // TV falhou completamente — fallback paralelo via /brapi → /indicators
    await Promise.all(tks.map(async t=>{
      const tid=t.toLowerCase();
      const ep=document.getElementById(pfx+tid+'_p');
      if(!ep)return;
      try{
        const ctrlB=new AbortController();setTimeout(()=>ctrlB.abort(),8000);
        const rb=await fetch(B+'/brapi/'+t+'.SA',{signal:ctrlB.signal});
        if(rb.ok){
          const db=await rb.json();
          if(db.price){
            ep.textContent=fR(db.price);ep.classList.remove('loading');
            ChTbl(pfx+tid+'_v',pfx+tid+'_c',db.price,db.prev||db.price,'r');
            return;
          }
        }
      }catch(e2){}
      try{
        const ctrlI=new AbortController();setTimeout(()=>ctrlI.abort(),15000);
        const r2=await fetch(B+'/indicators/'+t+'.SA',{signal:ctrlI.signal});
        if(!r2.ok)return;
        const d2=await r2.json();
        if(d2.preco_atual){
          ep.textContent=fR(d2.preco_atual);ep.classList.remove('loading');
          if(d2.preco_anterior)ChTbl(pfx+tid+'_v',pfx+tid+'_c',d2.preco_atual,d2.preco_anterior,'r');
        }
      }catch(e2){}
    }));
  }
}

function expandAll(){
  const btn=document.getElementById('btn-expand');
  const segs=['fin','pet','min','mat','uti','cc','cn','sau','ind','tit','m7','nq','sp','dj'];
  const anyOpen=segs.some(id=>document.getElementById('sb-'+id)?.style.display==='block');
  segs.forEach(id=>{
    const b=document.getElementById('sb-'+id),a=document.getElementById('ar-'+id);
    if(!b)return;
    if(anyOpen){b.style.display='none';if(a)a.textContent='▼';}
    else{
      b.style.display='block';if(a)a.textContent='▲';
      if(!b.dataset.l){b.dataset.l='1';loadSeg(id);}
    }
  });
  if(btn)btn.textContent=anyOpen?'+ Expandir Todos':'− Recolher Todos';
}
// ── RENDERIZAÇÃO DINÂMICA DE POSIÇÕES (Sprint 6 — modular) ──
let _posData = null;

function fmtData(iso){
  if(!iso)return '—';
  const [y,m,d]=iso.split('-');
  return `${d}/${m}/${y}`;
}

function tplSimples(p){
  const id=p.id;
  const stLabel = p.codigo_opcao ? `Strike (${p.codigo_opcao})` : 'Strike';
  return `
  <div class="pos-acc" id="card-${id}">
    <div class="pos-acc-hdr" onclick="togPos('pos-${id}')">
      <div><div class="pos-acc-tk">${p.ticker.replace('.SA','')}</div><div class="pos-acc-sub">${p.nome} · ${p.estrategia}${p.codigo_opcao?' · '+p.codigo_opcao:''} · Venc ${fmtData(p.vencimento)}</div></div>
      <div class="pos-acc-right">
        <div><div class="pp loading" id="${id}-p">—</div><div class="pc2" id="${id}-c">—</div></div>
        <span id="ar-pos-${id}" style="color:var(--muted)">▼</span>
      </div>
    </div>
    <div class="pos-acc-body open" id="body-pos-${id}">
    <div class="sb">
      <div class="sr"><span class="sl">${stLabel}</span><span class="sv warn">R$ ${p.strike.toFixed(2).replace('.',',')}</span></div>
      <div class="sr"><span class="sl">Preço vs strike</span><span class="sv itm" id="${id}-itm">—</span></div>
      <div class="sr"><span class="sl">Vencimento</span><span class="sv">${fmtData(p.vencimento)} · <span id="${id}-dias">—</span></span></div>
      <div class="sr"><span class="sl">Vol. Impl.</span><span class="sv warn" id="${id}-bs-vol">${(p.vol_impl*100).toFixed(1)}%</span></div>
      <div class="sr"><span class="sl">Delta</span><span class="sv warn" id="${id}-bs-delta">—</span></div>
      <div class="sr"><span class="sl">Prob. B&amp;S exercer</span><span class="sv warn" id="${id}-bs-prob">—</span></div>
      <div class="sr"><span class="sl">Prob. MC exercer (Vol.Simples)</span><span class="sv" id="${id}-mc-vs">calc...</span></div>
      <div class="sr"><span class="sl">Prob. MC exercer (GARCH)</span><span class="sv ok" id="${id}-mc-rt">calc...</span></div>
      <div class="sr"><span class="sl">Vol. Simples / GARCH</span><span class="sv" id="${id}-mc-vols">—</span></div>
      ${p.objetivo?`<div class="sr"><span class="sl">Objetivo</span><span class="sv ok">${p.objetivo}</span></div>`:''}
    </div>
    <div class="sig">
      <div class="sgt">🎲 Monte Carlo — Prob. call ser exercida</div>
      <div id="${id}-mc-l" style="color:var(--muted);font-size:12px">Calculando 5.000 cenários...</div>
      <div id="${id}-mc-r" style="display:none">
        <div style="font-size:12px;color:var(--muted);line-height:1.6" id="${id}-mc-i">—</div>
      </div>
    </div>
    ${p.data_entrada?`
    <div style="margin-top:14px">
      <button onclick="loadEvolucaoPosicao('${id}')" id="${id}-evo-btn" style="background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:6px 14px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600;letter-spacing:.3px;width:100%">📈 Ver evolução desde a entrada</button>
      <div id="${id}-evo-area" style="display:none;margin-top:10px"></div>
    </div>`:''}
    </div>
  </div>`;
}

function tplBarreira(p){
  const id=p.id;
  return `
  <div class="pos-acc" id="card-${id}">
    <div class="pos-acc-hdr" onclick="togPos('pos-${id}')">
      <div><div class="pos-acc-tk">${p.ticker.replace('.SA','')}</div><div class="pos-acc-sub">${p.nome} · ${p.estrategia} · Venc ${fmtData(p.vencimento)}</div></div>
      <div class="pos-acc-right">
        <div><div class="pp loading" id="${id}-p">—</div><div class="pc2" id="${id}-c">—</div></div>
        <span id="ar-pos-${id}" style="color:var(--muted)">▼</span>
      </div>
    </div>
    <div class="pos-acc-body open" id="body-pos-${id}">
    <div class="sb">
      <div class="sr"><span class="sl">KDO (${p.kdo_pct})</span><span class="sv warn">R$ ${p.kdo.toFixed(2).replace('.',',')}</span></div>
      <div class="sr"><span class="sl">KUO (${p.kuo_pct})</span><span class="sv warn">R$ ${p.kuo.toFixed(2).replace('.',',')}</span></div>
      <div class="sr"><span class="sl">Ganho s/ barreira</span><span class="sv ok">${p.ganho_sem_barreira}</span></div>
      <div class="sr"><span class="sl">Ganho c/ bar. alta</span><span class="sv warn">${p.ganho_barreira_alta}</span></div>
      <div class="sr"><span class="sl">Vencimento</span><span class="sv">${fmtData(p.vencimento)} · <span id="${id}-dias">—</span></span></div>
      <div class="sr"><span class="sl">Dist. KDO</span><span class="sv" id="${id}-kdo">—</span></div>
      <div class="sr"><span class="sl">Dist. KUO</span><span class="sv" id="${id}-kuo">—</span></div>
      <div class="sr"><span class="sl">Situação</span><span class="sv" id="${id}-st">—</span></div>
    </div>
    <div class="sig">
      <div class="sgt">🎲 Monte Carlo — Cenários barreira</div>
      <div id="${id}-mc-l" style="color:var(--muted);font-size:12px">Calculando...</div>
      <div id="${id}-mc-r" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
          <div class="ib"><div class="il">Sem Barreira ✅</div><div class="iv ok" id="${id}-mc-nb">—</div></div>
          <div class="ib"><div class="il">Bar. Alta KUO</div><div class="iv warn" id="${id}-mc-ku">—</div></div>
          <div class="ib"><div class="il">Bar. Baixa KDO</div><div class="iv down" id="${id}-mc-kd">—</div></div>
          <div class="ib"><div class="il">Vol. Hist.</div><div class="iv warn" id="${id}-mc-vo">—</div></div>
        </div>
        <div style="font-size:12px;color:var(--muted);margin-top:6px;line-height:1.6" id="${id}-mc-i">—</div>
      </div>
    </div>
    ${p.data_entrada?`
    <div style="margin-top:14px">
      <button onclick="loadEvolucaoPosicao('${id}')" id="${id}-evo-btn" style="background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:6px 14px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600;letter-spacing:.3px;width:100%">📈 Ver evolução desde a entrada</button>
      <div id="${id}-evo-area" style="display:none;margin-top:10px"></div>
    </div>`:''}
    </div>
  </div>`;
}

// Adicionado 26/06/2026 -- tipo_posicao='barreira_simples' (estruturas
// retorno_controlado: SO barreira de baixa KDO, SEM KUO/teto de alta --
// diferente de 'barreira', que e bidirecional completo). Criado apos bug
// real: BSLV39 (migrado automaticamente de Em Analise) caia no template
// tplSimples por engano (so existiam 2 opcoes: barreira ou else), que
// esperava campos de covered call (strike, tipo) que essa estrutura nao
// tem -- causava "Cannot read properties of undefined (reading
// 'toFixed')". vol_impl pode ser null (historico insuficiente para
// calcular, ver _migrar_para_positions no backend) -- tratado como
// opcional aqui, nunca quebra a renderizacao.
function tplBarreiraSimples(p){
  const id=p.id;
  const volTxt=p.vol_impl!=null?(p.vol_impl*100).toFixed(1)+'%':'⚠ não calculado (complete manualmente)';
  return `
  <div class="pos-acc" id="card-${id}">
    <div class="pos-acc-hdr" onclick="togPos('pos-${id}')">
      <div><div class="pos-acc-tk">${p.ticker.replace('.SA','')}</div><div class="pos-acc-sub">${p.nome} · ${p.estrategia} · Venc ${fmtData(p.vencimento)}</div></div>
      <div class="pos-acc-right">
        <div><div class="pp loading" id="${id}-p">—</div><div class="pc2" id="${id}-c">—</div></div>
        <span id="ar-pos-${id}" style="color:var(--muted)">▼</span>
      </div>
    </div>
    <div class="pos-acc-body open" id="body-pos-${id}">
    <div class="sb">
      <div class="sr"><span class="sl">KDO (${p.kdo_pct})</span><span class="sv warn">R$ ${p.kdo.toFixed(2).replace('.',',')}</span></div>
      ${p.ganho_sem_barreira?`<div class="sr"><span class="sl">Ganho s/ barreira</span><span class="sv ok">${p.ganho_sem_barreira}</span></div>`:''}
      <div class="sr"><span class="sl">Vencimento</span><span class="sv">${fmtData(p.vencimento)} · <span id="${id}-dias">—</span></span></div>
      <div class="sr"><span class="sl">Dist. KDO</span><span class="sv" id="${id}-kdo">—</span></div>
      <div class="sr"><span class="sl">Situação</span><span class="sv" id="${id}-st">—</span></div>
      <div class="sr" title="Volatilidade calculada via GARCH a partir do histórico real -- se não calculada, o histórico do ativo era insuficiente (baixa liquidez)"><span class="sl">Vol. implícita</span><span class="sv${p.vol_impl==null?' warn':''}">${volTxt}</span></div>
    </div>
    <div class="sig">
      <div class="sgt">🎲 Monte Carlo — Cenário barreira simples (só KDO)</div>
      <div style="color:var(--muted);font-size:12px">📈 Clique em "Ver evolução desde a entrada" abaixo para calcular o fan chart e as probabilidades (vol. histórica simples, calculada a partir do histórico real do ativo).</div>
    </div>
    ${p.data_entrada?`
    <div style="margin-top:14px">
      <button onclick="loadEvolucaoPosicao('${id}')" id="${id}-evo-btn" style="background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:6px 14px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600;letter-spacing:.3px;width:100%">📈 Ver evolução desde a entrada</button>
      <div id="${id}-evo-area" style="display:none;margin-top:10px"></div>
    </div>`:''}
    </div>
  </div>`;
}

// ── EVOLUÇÃO DE POSIÇÃO ATIVA (retroativo real + projeção) ──
async function loadEvolucaoPosicao(id){
  const area=document.getElementById(id+'-evo-area');
  if(!area||!_posData)return;
  const abrir=area.style.display==='none';
  area.style.display=abrir?'block':'none';
  if(!abrir)return;
  if(area.dataset.loaded){return;}

  const p=(_posData.ativas||[]).find(x=>x.id===id);
  if(!p){area.innerHTML='<p style="color:var(--red);font-size:11px;padding:10px">Posição não encontrada.</p>';return;}

  area.innerHTML='<p style="color:var(--muted);font-size:11px;padding:10px;text-align:center">Calculando evolução desde '+fmtData(p.data_entrada)+'...</p>';
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const body={ticker:p.ticker,data_entrada:p.data_entrada,vencimento:p.vencimento};
    if(p.strike!=null)body.k_call=p.strike;
    // ADICIONADO 15/07/2026 -- faltava esse campo aqui (MCBSimples ja
    // mandava). Sem isso, o backend tentava extrair o preco de entrada
    // sozinho do historico esparso do Yahoo pra ativos iliquidos tipo
    // BSLV39, podendo dar um valor errado pro "% desde a entrada" -- o
    // preco real confirmado (boleto/nota) tem prioridade.
    if(p.entry!=null)body.entry=p.entry;
    if(p.kdo!=null)body.kdo=p.kdo;
    if(p.kuo!=null)body.kuo=p.kuo;
    if(p.exercicio!=null)body.exercicio=p.exercicio;
    if(p.meta_pct!=null)body.meta_pct=p.meta_pct;
    if(p.alavancagem!=null)body.alavancagem=p.alavancagem;
    if(p.teto_retorno_pct!=null)body.teto_retorno_pct=p.teto_retorno_pct;
    // ADICIONADO 15/07/2026 -- mesma correcao do fetch de /montecarlo/
    // condicional (Em Analise): repassa a mecanica de queda customizada,
    // pra caso uma posicao ATIVA no futuro use Protecao Total/Parcial em
    // vez da Bidirecional padrao (nenhuma posicao atual usa, mas evita o
    // mesmo bug se/quando isso acontecer).
    if(p.downside_antes!=null)body.downside_antes=p.downside_antes;
    if(p.downside_apos!=null)body.downside_apos=p.downside_apos;
    if(p.ganho_prefixado_pct!=null)body.ganho_prefixado_pct=p.ganho_prefixado_pct;
    // ADICIONADO 30/06/2026 -- envia o preco de entrada REAL (positions.json,
    // confirmado pelo usuario via nota de corretagem) como prioritario sobre
    // a extracao automatica do historico do Yahoo, que pode estar errada
    // para ativos de baixissima liquidez (ex: BSLV39, onde o Yahoo so tem
    // 1 ponto no periodo e a extracao acabava usando o preco ATUAL como se
    // fosse o de entrada).
    if(p.entry!=null)body.entry=p.entry;
    const r=await fetch(B+'/montecarlo/posicao_ativa',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    area.dataset.loaded='1';
    renderEvolucaoPosicao(id,d);
  }catch(e){
    area.innerHTML='<p style="color:var(--red);font-size:11px;padding:10px">Erro: '+e.message+'</p>';
  }
}

function renderEvolucaoPosicao(id,d){
  const area=document.getElementById(id+'-evo-area');
  if(!area)return;

  if(d.fora_do_prazo){
    area.innerHTML='<div style="padding:10px;background:rgba(240,98,146,.08);border-left:2px solid var(--red);font-size:11px;color:var(--text);line-height:1.5">⚠ '+(d.mensagem||'Vencimento já passou.')+'</div>';
    return;
  }

  let html='';
  if(d.fan_chart&&d.fan_chart.precos_reais_estimados){
    html+='<div style="padding:8px 10px;background:rgba(139,124,246,.08);border-left:2px solid var(--accent);font-size:10px;color:var(--muted);line-height:1.5;margin-bottom:10px">⚠ Histórico real estimado (via ativo original + câmbio) — Yahoo/brapi não têm cobertura diária boa pra esse ticker. Se o preço parecer muito longe do seu home broker, avise.</div>';
  }
  html+='<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">1. PROBABILIDADES — PREÇO DA ENTRADA vs. ATUAL</div>';
  html+='<div class="sb" style="margin-top:0">';
  html+='<div class="sr"><span class="sl">Preço na entrada</span><span class="sv">'+fR(d.preco_entrada)+'</span></div>';
  html+='<div class="sr"><span class="sl">Preço atual</span><span class="sv">'+fR(d.preco_atual)+'</span></div>';
  html+='<div class="sr"><span class="sl">Dias decorridos / restantes</span><span class="sv">'+d.dias_passados+' / '+d.dias_restantes+'</span></div>';
  if(d.prob_sem_barreira!=null){
    html+='<div class="sr"><span class="sl">Prob. sem tocar barreira (restante)</span><span class="sv ok">'+d.prob_sem_barreira.toFixed(2)+'%</span></div>';
    html+='<div class="sr"><span class="sl">Prob. barreira alta (restante)</span><span class="sv warn">'+d.prob_barreira_alta.toFixed(2)+'%</span></div>';
    html+='<div class="sr"><span class="sl">Prob. barreira baixa (restante)</span><span class="sv warn">'+d.prob_barreira_baixa.toFixed(2)+'%</span></div>';
  }
  html+='</div>';

  if(d.simulacao_100_acoes){
    const s=d.simulacao_100_acoes;
    html+='<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)"><div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">2. SIMULAÇÃO — 100 AÇÕES A '+fR(s.preco_foto)+'</div><div class="sb" style="margin-top:0">';
    if(s.defesa){
      html+='<div class="sr"><span class="sl">'+s.defesa.descricao+'</span><span class="sv">'+fR(s.defesa.retorno_reais)+'</span></div>';
      html+='<div class="sr"><span class="sl">'+s.dentro.descricao+'</span><span class="sv '+(s.dentro.retorno_medio_reais>=0?'ok':'itm')+'">'+(s.dentro.retorno_medio_reais>=0?'+':'')+fR(s.dentro.retorno_medio_reais)+'</span></div>';
      html+='<div class="sr"><span class="sl">'+s.teto.descricao+'</span><span class="sv ok">+'+fR(s.teto.retorno_reais)+'</span></div>';
    } else if(s.prefixado){
      html+='<div class="sr"><span class="sl">'+s.prefixado.descricao+'</span><span class="sv ok">+'+fR(s.prefixado.retorno_reais)+'</span></div>';
      html+='<div class="sr"><span class="sl">'+s.exposto.descricao+'</span><span class="sv '+(s.exposto.retorno_medio_reais>=0?'ok':'itm')+'">'+(s.exposto.retorno_medio_reais>=0?'+':'')+fR(s.exposto.retorno_medio_reais)+'</span></div>';
    } else if(s.nao_exercida){
      html+='<div class="sr"><span class="sl">'+s.nao_exercida.descricao+'</span><span class="sv '+(s.nao_exercida.retorno_medio_reais>=0?'ok':'itm')+'">'+(s.nao_exercida.retorno_medio_reais>=0?'+':'')+fR(s.nao_exercida.retorno_medio_reais)+'</span></div>';
      html+='<div class="sr"><span class="sl">'+s.exercida.descricao+'</span><span class="sv '+(s.exercida.retorno_reais>=0?'ok':'itm')+'">'+(s.exercida.retorno_reais>=0?'+':'')+fR(s.exercida.retorno_reais)+'</span></div>';
    }
    html+='</div></div>';
  }

  if(d.prob_retorno_faixas){
    const f=d.prob_retorno_faixas;
    html+='<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)"><div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">3. PROBABILIDADE DE RETORNO FINAL (DESDE A ENTRADA)</div>'+
      '<div class="sb" style="margin-top:0">'+
      '<div class="sr"><span class="sl">Abaixo de 0%</span><span class="sv itm">'+f.menor_que_0.toFixed(1)+'%</span></div>'+
      '<div class="sr"><span class="sl">Entre 0% e 1%</span><span class="sv">'+f.entre_0_e_1.toFixed(1)+'%</span></div>'+
      '<div class="sr"><span class="sl">Entre 1% e 2%</span><span class="sv">'+f.entre_1_e_2.toFixed(1)+'%</span></div>'+
      '<div class="sr"><span class="sl">Entre 2% e a meta</span><span class="sv warn">'+f.entre_2_e_meta.toFixed(1)+'%</span></div>'+
      '<div class="sr"><span class="sl">Bate a meta (\u2265'+(d.teto_retorno_usado_pct!=null?d.teto_retorno_usado_pct:'?')+'%)</span><span class="sv ok">'+f.maior_ou_igual_meta.toFixed(1)+'%</span></div>'+
      '</div></div>';
  }

  if(d.fan_chart){
    html+='<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)"><div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">4. EVOLUÇÃO REAL DESDE A ENTRADA + PROJEÇÃO</div>'+
      '<div style="position:relative;height:clamp(240px,30vh,380px);background:var(--bg2);border:1px solid var(--border);padding:8px">'+
      '<canvas id="analise-fan-canvas-'+id+'-pos"></canvas></div></div>';
  }

  area.innerHTML=html;
  if(d.fan_chart){
    renderFanChartAnalise(id+'-pos', d.fan_chart);
  }
}

async function loadPositions(){
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),10000);
    const r=await fetch(B+'/positions',{signal:ctrl.signal,cache:'no-store'});
    const data=await r.json();
    if(data.error){
      const detalhes=data.detalhes?('<ul style="margin-top:8px;padding-left:18px">'+data.detalhes.map(d=>'<li>'+d+'</li>').join('')+'</ul>'):'';
      throw new Error(data.error+detalhes);
    }
    if(!r.ok)throw new Error('HTTP '+r.status);
    _posData=data;
    renderPositions(data);
    renderEncerradas(data);
  }catch(e){
    console.error('Erro ao carregar positions.json:',e);
    const msg='<p style="color:var(--red);padding:20px">⚠ Erro em positions.json: '+e.message+'<br><span style="color:var(--muted);font-size:11px">Verifique a sintaxe do arquivo no GitHub. As outras abas continuam funcionando normalmente.</span></p>';
    const cont=document.getElementById('pos-container');
    if(cont)cont.innerHTML=msg;
    const cont2=document.getElementById('enc-container');
    if(cont2)cont2.innerHTML=msg;
  }
}

function renderPositions(data){
  const cont=document.getElementById('pos-container');
  if(!cont)return;
  const ativas=data.ativas||[];
  let html='';
  ativas.forEach(p=>{
    if(p.tipo_posicao==='barreira') html+=tplBarreira(p);
    else if(p.tipo_posicao==='barreira_simples') html+=tplBarreiraSimples(p);
    else html+=tplSimples(p);
  });
  cont.innerHTML=html;
}

function getAtivaIds(){
  if(!_posData||!_posData.ativas)return [];
  return _posData.ativas.map(p=>'pos-'+p.id);
}

// ── ENCERRADAS — renderização dinâmica ───────────────
function fmtDataOrNull(iso){
  if(!iso)return null;
  const [y,m,d]=iso.split('-');
  return `${d}/${m}/${y}`;
}

function tplEncerrada(p){
  const id=p.id;
  const dataEnc=fmtDataOrNull(p.data_encerramento);
  const subParts=[p.estrategia];
  if(p.codigo_opcao)subParts.push(p.codigo_opcao);
  subParts.push(dataEnc?`Encerrada ${dataEnc}`:'Encerrada');
  const sub=subParts.join(' · ');
  // CORRIGIDO 13/08/2026 -- Victor notou que 'fracasso' aparecia como
  // "PARCIAL" -- a logica so distinguia sucesso de "tudo o resto", nunca
  // teve badge de fracasso de verdade. Achado no fechamento da rolagem
  // BBAS3 (cl-bbas3-rolagem-out26, primeiro status='fracasso' explicito
  // registrado em positions.json). Agora trata os 3 estados: sucesso,
  // fracasso, e qualquer outra coisa (ex: sem status, ou status custom
  // futuro) continua caindo em "parcial" como fallback neutro.
  const badgeCls=p.status==='sucesso'?'enc-ok':(p.status==='fracasso'?'enc-fracasso':'enc-warn');
  const badgeTxt=p.status==='sucesso'?'✅ SUCESSO':(p.status==='fracasso'?'❌ FRACASSO':'⚠ PARCIAL');

  let rows='';
  rows+=`<div class="sr"><span class="sl">Estratégia</span><span class="sv">${p.estrategia}</span></div>`;
  if(p.codigo_opcao&&p.strike)rows+=`<div class="sr"><span class="sl">Opção</span><span class="sv">${p.codigo_opcao} · R$ ${p.strike.toFixed(2).replace('.',',')}</span></div>`;
  if(p.alvo_pct!=null)rows+=`<div class="sr"><span class="sl">Alvo</span><span class="sv warn">${p.alvo_pct}%</span></div>`;
  if(p.realizado_pct!=null)rows+=`<div class="sr"><span class="sl">Realizado</span><span class="sv ok">~${p.realizado_pct}%</span></div>`;
  if(dataEnc)rows+=`<div class="sr"><span class="sl">Encerrada em</span><span class="sv">${dataEnc}</span></div>`;
  if(p.pct_do_alvo!=null)rows+=`<div class="sr"><span class="sl">% do alvo atingido</span><span class="sv ok">${p.pct_do_alvo}%</span></div>`;
  if(p.pct_do_prazo!=null)rows+=`<div class="sr"><span class="sl">% do prazo utilizado</span><span class="sv ok">${p.pct_do_prazo}%</span></div>`;
  if(p.resultado_texto)rows+=`<div class="sr"><span class="sl">Resultado</span><span class="sv ok">✅ ${p.resultado_texto}</span></div>`;
  if(p.observacao)rows+=`<div class="sr"><span class="sl">Observação</span><span class="sv" style="color:var(--muted)">${p.observacao}</span></div>`;

  let barra='';
  if(p.pct_do_alvo!=null){
    barra=`
      <div style="margin-top:12px">
        <div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:6px">PROGRESSO DO ALVO</div>
        <div style="background:var(--bg3);border:1px solid var(--border);height:8px;border-radius:2px;overflow:hidden">
          <div style="width:${p.pct_do_alvo}%;height:100%;background:linear-gradient(90deg,var(--accent),var(--green))"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:4px">
          <span>0%</span><span style="color:var(--green);font-weight:700">${p.pct_do_alvo}% atingido</span><span>100%</span>
        </div>
      </div>`;
  }

  return `
  <div class="pos-enc" style="margin-top:10px">
    <div class="pos-enc-hdr" onclick="togPos('pos-${id}')">
      <div style="display:flex;align-items:center;gap:12px">
        <div>
          <div class="pos-acc-tk" style="color:var(--muted);font-size:18px">${p.ticker}</div>
          <div class="pos-acc-sub">${sub}</div>
        </div>
        <span class="enc-badge ${badgeCls}">${badgeTxt}</span>
      </div>
      <span id="ar-pos-${id}" style="color:var(--muted)">▼</span>
    </div>
    <div class="pos-acc-body" id="body-pos-${id}">
      <div class="sb">${rows}</div>
      ${barra}
    </div>
  </div>`;
}

function calcDashboardEncerradas(encerradas){
  const total=encerradas.length;
  const sucessos=encerradas.filter(p=>p.status==='sucesso').length;
  const taxaSucesso=total?Math.round(sucessos/total*100):0;
  const comAlvo=encerradas.filter(p=>p.pct_do_alvo!=null);
  const mediaAlvo=comAlvo.length?Math.round(comAlvo.reduce((s,p)=>s+p.pct_do_alvo,0)/comAlvo.length):null;
  const comPrazo=encerradas.filter(p=>p.pct_do_prazo!=null);
  const mediaPrazo=comPrazo.length?Math.round(comPrazo.reduce((s,p)=>s+p.pct_do_prazo,0)/comPrazo.length):null;
  return {total,sucessos,taxaSucesso,mediaAlvo,mediaPrazo};
}

function renderEncerradas(data){
  const cont=document.getElementById('enc-container');
  if(!cont)return;
  const encerradas=data.encerradas||[];
  const stats=calcDashboardEncerradas(encerradas);

  let dashboard=`
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px">
    <div class="card g">
      <div class="cl">Operações</div>
      <div class="cp">${stats.total}</div>
      <div class="cc" style="color:var(--muted)">encerradas</div>
    </div>
    <div class="card g">
      <div class="cl">Taxa de Sucesso</div>
      <div class="cp">${stats.taxaSucesso}%</div>
      <div class="cc" style="color:var(--green)">${stats.sucessos} de ${stats.total} ✅</div>
    </div>
    <div class="card b">
      <div class="cl">Resultado Médio</div>
      <div class="cp" style="font-size:18px">${stats.mediaAlvo!=null?'~'+stats.mediaAlvo+'%':'—'}</div>
      <div class="cc" style="color:var(--accent)">do alvo atingido</div>
    </div>
    <div class="card b">
      <div class="cl">Tempo Médio</div>
      <div class="cp" style="font-size:18px">${stats.mediaPrazo!=null?'~'+stats.mediaPrazo+'%':'—'}</div>
      <div class="cc" style="color:var(--accent)">do prazo utilizado</div>
    </div>
  </div>`;

  let cards='';
  encerradas.forEach(p=>cards+=tplEncerrada(p));

  cont.innerHTML=dashboard+cards;
}

function togPos(id){
  const body=document.getElementById('body-'+id);
  const arr=document.getElementById('ar-'+id);
  if(!body)return;
  const open=body.classList.contains('open');
  body.classList.toggle('open',!open);
  if(arr)arr.textContent=open?'▶':'▼';
}
function toggleAllPos(){
  const ids=getAtivaIds();
  const btn=document.getElementById('btn-all-pos');
  const anyOpen=ids.some(id=>document.getElementById('body-'+id)?.classList.contains('open'));
  ids.forEach(id=>{
    const body=document.getElementById('body-'+id);
    const arr=document.getElementById('ar-'+id);
    if(body){body.classList.toggle('open',!anyOpen);if(arr)arr.textContent=anyOpen?'▶':'▼';}
  });
  if(btn)btn.textContent=anyOpen?'− Recolher Todas':'+ Expandir Todas';
}
function togInd(id){
  const body=document.getElementById(id+'-ind-wrap');
  const arr=document.getElementById('ar-ind-'+id);
  if(!body)return;
  const open=body.classList.contains('open');
  body.classList.toggle('open',!open);
  if(arr)arr.textContent=open?'▶':'▼';
  if(!open&&!body.dataset.loaded){
    body.dataset.loaded='1';
    rl(id);
  }
}
// ── WATCHLIST — ativos de análise fundamentalista por segmento ──
const WATCHLIST = [
  {segmento:'🏦 Bancos', ativos:[
    {id:'itub4', ticker:'ITUB4.SA', nome:'ITUB4 — Itaú Unibanco PN'},
    {id:'bbas3', ticker:'BBAS3.SA', nome:'BBAS3 — Banco do Brasil ON'},
  ]},
  {segmento:'🏗️ Construção & Incorporação', ativos:[
    {id:'cyre3', ticker:'CYRE3.SA', nome:'CYRE3 — Cyrela ON'},
    {id:'dirr3', ticker:'DIRR3.SA', nome:'DIRR3 — Direcional ON'},
    {id:'mult3', ticker:'MULT3.SA', nome:'MULT3 — Multiplan ON'},
    {id:'alos3', ticker:'ALOS3.SA', nome:'ALOS3 — Allos ON'},
  ]},
  {segmento:'🛡️ Seguros', ativos:[
    {id:'pssa3', ticker:'PSSA3.SA', nome:'PSSA3 — Porto Seguro ON'},
    {id:'bbse3', ticker:'BBSE3.SA', nome:'BBSE3 — BB Seguridade ON'},
    {id:'cxse3', ticker:'CXSE3.SA', nome:'CXSE3 — Caixa Seguridade ON'},
  ]},
  {segmento:'⚡ Energia Elétrica', ativos:[
    {id:'axia3', ticker:'AXIA3.SA', nome:'AXIA3 — Axia Energia ON'},
    {id:'cmig4', ticker:'CMIG4.SA', nome:'CMIG4 — Cemig PN'},
    {id:'cpfe3', ticker:'CPFE3.SA', nome:'CPFE3 — CPFL Energia ON'},
    {id:'cple3', ticker:'CPLE3.SA', nome:'CPLE3 — Copel ON'},
    {id:'taee11', ticker:'TAEE11.SA', nome:'TAEE11 — Taesa UNT'},
  ]},
  {segmento:'🛢️ Petróleo & Gás', ativos:[
    {id:'petr4', ticker:'PETR4.SA', nome:'PETR4 — Petrobras PN'},
    {id:'prio3', ticker:'PRIO3.SA', nome:'PRIO3 — PetroRio ON'},
  ]},
  {segmento:'⛏️ Mineração', ativos:[
    {id:'vale3', ticker:'VALE3.SA', nome:'VALE3 — Vale ON'},
    {id:'cmin3', ticker:'CMIN3.SA', nome:'CMIN3 — CSN Mineração ON'},
  ]},
  {segmento:'🌲 Papel & Celulose', ativos:[
    {id:'euca4', ticker:'EUCA4.SA', nome:'EUCA4 — Eucatex PN'},
  ]},
  {segmento:'💧 Saneamento', ativos:[
    {id:'sapr11', ticker:'SAPR11.SA', nome:'SAPR11 — Sanepar UNT'},
    {id:'sbsp3', ticker:'SBSP3.SA', nome:'SBSP3 — Sabesp ON'},
  ]},
  {segmento:'🏭 Siderurgia', ativos:[
    {id:'ggbr4', ticker:'GGBR4.SA', nome:'GGBR4 — Gerdau PN'},
  ]},
  {segmento:'⚙️ Bens de Capital & Industrial', ativos:[
    {id:'wege3', ticker:'WEGE3.SA', nome:'WEGE3 — WEG ON'},
  ]},
  {segmento:'💳 Fintech / BDR', ativos:[
    {id:'roxo34', ticker:'ROXO34.SA', nome:'ROXO34 — Nubank BDR'},
  ]},
  {segmento:'♻️ Resíduos & Economia Circular', ativos:[
    {id:'orvr3', ticker:'ORVR3.SA', nome:'ORVR3 — Orizon ON'},
  ]},
];

function getWatchlistFlat(){
  return WATCHLIST.flatMap(seg=>seg.ativos);
}

function tplWatchAtivo(a, segNome){
  return `
  <div class="ind-acc">
    <div class="ind-acc-hdr" onclick="togInd('${a.id}')">
      <div><div class="ind-acc-title">${a.nome}</div><div class="ind-acc-sub">${segNome} · clique para expandir/recolher</div></div>
      <div style="display:flex;align-items:center;gap:10px"><span style="cursor:pointer;color:var(--accent);font-size:13px" onclick="event.stopPropagation();rl('${a.id}')">↻</span><span id="ar-ind-${a.id}">▶</span></div>
    </div>
    <div class="ind-acc-body" id="${a.id}-ind-wrap">
      <div id="${a.id}-ind"><div style="color:var(--muted);padding:12px;font-size:12px">Clique para carregar indicadores</div></div>
      <div style="margin-top:10px">
        <button onclick="toggleFanChart('${a.id}')" id="${a.id}-fc-btn" style="background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:6px 14px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600;letter-spacing:.3px;width:100%">📊 Ver cenários futuros (Monte Carlo)</button>
        <div id="${a.id}-fc-wrap" style="display:none;margin-top:10px">
          <div style="display:flex;gap:6px;margin-bottom:10px">
            <button onclick="loadFanChart('${a.id}',21)" class="cal-fb fc-period-btn" id="${a.id}-fc-21">21 dias</button>
            <button onclick="loadFanChart('${a.id}',60)" class="cal-fb fc-period-btn" id="${a.id}-fc-60">60 dias</button>
            <button onclick="loadFanChart('${a.id}',90)" class="cal-fb fc-period-btn" id="${a.id}-fc-90">90 dias</button>
          </div>
          <div style="position:relative;height:clamp(300px,36vh,480px);background:var(--bg2);border:1px solid var(--border);padding:8px">
            <canvas id="${a.id}-fc-canvas"></canvas>
          </div>
          <div id="${a.id}-fc-info" style="font-size:10px;color:var(--muted);margin-top:6px;text-align:center">Selecione um período para simular</div>
        </div>
        <!-- FOTO DO PAPEL -- adicionado 30/06/2026 -->
        <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px">
          <div id="${a.id}-foto-status" style="font-size:10px;color:var(--muted);margin-bottom:6px">📸 <em>Sem foto registrada</em></div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button onclick="tirarFoto('${a.ticker}','${a.id}')" id="${a.id}-foto-btn"
              style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:5px 12px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600">
              📸 Tirar Foto
            </button>
            <button onclick="verFoto('${a.ticker}','${a.id}')" id="${a.id}-foto-ver-btn" style="display:none;background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:5px 12px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600">
              📊 Ver Foto
            </button>
            <button onclick="resetarFoto('${a.ticker}','${a.id}')" id="${a.id}-foto-reset-btn" style="display:none;background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 10px;font-size:10px;cursor:pointer;font-family:inherit">
              ✕ Resetar
            </button>
          </div>
          <div id="${a.id}-foto-chart-wrap" style="display:none;margin-top:10px">
            <div style="display:flex;gap:6px;margin-bottom:8px" id="${a.id}-foto-period-btns">
              <button onclick="renderFotoChart('${a.id}',21)" class="cal-fb" id="${a.id}-fp-21">21 dias</button>
              <button onclick="renderFotoChart('${a.id}',60)" class="cal-fb" id="${a.id}-fp-60">60 dias</button>
              <button onclick="renderFotoChart('${a.id}',90)" class="cal-fb" id="${a.id}-fp-90">90 dias</button>
            </div>
            <div id="${a.id}-foto-confianca" style="font-size:11px;color:var(--text);line-height:1.5;margin-bottom:8px;padding:8px 10px;background:rgba(124,106,247,.08);border-left:2px solid var(--accent);text-align:left"></div>
            <div style="position:relative;height:clamp(280px,34vh,440px);background:var(--bg2);border:1px solid var(--border);padding:8px">
              <canvas id="${a.id}-foto-canvas"></canvas>
            </div>
            <div id="${a.id}-foto-score" style="font-size:11px;color:var(--muted);margin-top:8px;padding:8px;background:var(--bg2);border:1px solid var(--border)"></div>
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

function renderWatchlist(){
  const cont=document.getElementById('watchlist-container');
  if(!cont)return;
  let html='';
  WATCHLIST.forEach(seg=>{
    html+=`<div class="sec" style="margin-top:18px"><span class="dot"></span>${seg.segmento}</div>`;
    seg.ativos.forEach(a=>{ html+=tplWatchAtivo(a, seg.segmento); });
  });
  cont.innerHTML=html;
}

// ── FOTO DO PAPEL — assertividade Monte Carlo (30/06/2026) ──────────────────
// "Tirar uma foto" = congelar preco atual + bandas GARCH nos 3 horizontes.
// Acompanha se o preco real ficou dentro das bandas ao longo do tempo.
// Storage: fotos_papel.json no repo (via /foto-papel endpoints).
const _fotoData = {};   // cache: { [id]: { foto, historico_real, score, ... } }
const _fotoCharts = {}; // instancias Chart.js por ativo

async function tirarFoto(ticker, id){
  const btn = document.getElementById(id+'-foto-btn');
  if(!id) id=ticker;  // compatibilidade quando chamado sem id
  if(btn){ btn.textContent='⏳ Calculando...'; btn.disabled=true; }
  try{
    const r = await fetch(B+'/foto-papel', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ticker: ticker})
    });
    const d = await r.json();
    if(d.foto){
      _fotoData[id] = { foto: d.foto, historico_real: [], score: null };
      _atualizarStatusFoto(id, d.foto, 0, false, null);
      if(!d.ok){
        // Foto calculada mas nao persistida (GITHUB_TOKEN ausente no servidor)
        const st = document.getElementById(id+'-foto-status');
        if(st) st.innerHTML += ' <span style="color:var(--yellow);font-size:9px">[⚠ não salva — configure GITHUB_TOKEN no Render]</span>';
      }
    } else {
      alert('Erro ao tirar foto: '+(d.error||'resposta inesperada'));
    }
  } catch(e){
    alert('Erro de rede ao tirar foto');
  } finally {
    if(btn){ btn.textContent='📸 Tirar Foto'; btn.disabled=false; }
  }
}

async function verFoto(ticker, id){
  if(!id) id=ticker;
  const wrap = document.getElementById(id+'-foto-chart-wrap');
  if(!wrap) return;
  const aberto = wrap.style.display !== 'none';
  if(aberto){ wrap.style.display='none'; return; }

  // Busca dados (com historico real e score) se ainda nao tiver
  if(!_fotoData[id] || !_fotoData[id].historico_real?.length){
    const statusEl = document.getElementById(id+'-foto-status');
    if(statusEl) statusEl.innerHTML = '⏳ Carregando foto...';
    try{
      const r = await fetch(B+'/foto-papel?ticker='+encodeURIComponent(ticker));
      const d = await r.json();
      if(!d.encontrado){ return; }
      _fotoData[id] = d;
      _atualizarStatusFoto(id, d.foto, d.dias_uteis_decorridos, d.expirada, d.score);
    } catch(e){ return; }
  }

  wrap.style.display = 'block';
  // Renderiza o periodo mais longo disponivel por padrão
  const hist = _fotoData[id]?.historico_real || [];
  const periodo = hist.length > 60 ? 90 : hist.length > 21 ? 60 : 21;
  renderFotoChart(id, periodo);
}

function _atualizarStatusFoto(id, foto, diasUteis, expirada, score){
  const statusEl = document.getElementById(id+'-foto-status');
  const verBtn   = document.getElementById(id+'-foto-ver-btn');
  const resetBtn = document.getElementById(id+'-foto-reset-btn');
  if(!foto){ 
    if(statusEl) statusEl.innerHTML = '📸 <em>Sem foto registrada</em>';
    if(verBtn)   verBtn.style.display = 'none';
    if(resetBtn) resetBtn.style.display = 'none';
    return;
  }
  const expTag = expirada ? ' <span style="color:var(--red);font-weight:700">[EXPIRADA — 90d]</span>' : '';
  let scoreStr = '';
  if(score){
    scoreStr = ` · <span title="% do tempo dentro das bandas p25-p75 e p10-p90">
      Assertividade: <b style="color:var(--green)">${score.pct_dentro_p25_p75}%</b> (banda central) /
      <b style="color:var(--accent)">${score.pct_dentro_p10_p90}%</b> (banda ampla)
      em ${score.dias_observados}d observados</span>`;
  }
  if(statusEl) statusEl.innerHTML =
    `📸 Foto: <b>${foto.data_foto}</b> · Preço: R$${foto.preco_foto.toFixed(2)} · Vol: ${foto.sigma_pct.toFixed(1)}% a.a. · ${diasUteis}d úteis${expTag}${scoreStr}`;
  if(verBtn)   verBtn.style.display = 'inline-block';
  if(resetBtn) resetBtn.style.display = 'inline-block';
}

function renderFotoChart(id, periodo){
  const data = _fotoData[id];
  if(!data || !data.foto) return;

  // Destaca botão do periodo selecionado
  [21,60,90].forEach(p => {
    const b = document.getElementById(id+'-fp-'+p);
    if(b) b.style.background = p===periodo ? 'var(--accent)' : 'var(--bg3)';
  });

  const foto = data.foto;
  const bandas = foto.bandas?.[String(periodo)];
  if(!bandas){ console.warn('Bandas nao encontradas para periodo', periodo); return; }

  const T = periodo;
  const labels = Array.from({length: T+1}, (_,i) => `D+${i}`);

  // Linha real: mapeia closes reais para os indices de dia
  const histReal = (data.historico_real || []).slice(0, T+1);
  const realData = labels.map((_, i) => i < histReal.length ? histReal[i].close : null);

  // Datasets: bandas (preenchimento entre percentis) + linha mediana + linha real
  const dsConfig = [
    // Sombra externa: p10-p90
    { label:'P90 (banda ampla)', data: bandas.p90, borderColor:'transparent', backgroundColor:'rgba(100,120,180,0.10)', fill:'+1', pointRadius:0, borderWidth:0 },
    { label:'P10 (banda ampla)', data: bandas.p10, borderColor:'transparent', backgroundColor:'rgba(100,120,180,0.10)', fill:false, pointRadius:0, borderWidth:0 },
    // Sombra central: p25-p75
    { label:'P75 (banda central)', data: bandas.p75, borderColor:'transparent', backgroundColor:'rgba(100,180,130,0.18)', fill:'+1', pointRadius:0, borderWidth:0 },
    { label:'P25 (banda central)', data: bandas.p25, borderColor:'transparent', backgroundColor:'rgba(100,180,130,0.18)', fill:false, pointRadius:0, borderWidth:0 },
    // Mediana
    { label:'Mediana (p50)', data: bandas.p50, borderColor:'rgba(180,200,255,0.6)', borderWidth:1.5, borderDash:[4,3], pointRadius:0, fill:false },
    // Preço real
    { label:'Preço real', data: realData, borderColor:'#f0c040', borderWidth:2.5, pointRadius:0, fill:false, spanGaps:false },
  ];

  const canvas = document.getElementById(id+'-foto-canvas');
  if(!canvas) return;

  if(_fotoCharts[id]) { _fotoCharts[id].destroy(); }

  _fotoCharts[id] = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets: dsConfig },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode:'index', intersect:false },
      plugins: {
        legend: { display:true, labels:{ color:'#aaa', font:{size:10},
          filter: item => !['P90 (banda ampla)','P10 (banda ampla)','P75 (banda central)','P25 (banda central)'].includes(item.text) } },
        // CORRIGIDO 17/08/2026 -- pedido do Victor: antes as bandas p90/p10/p75/p25
        // ficavam escondidas do tooltip (so mostrava Mediana e Preco real). Agora
        // mostra tudo ao passar o mouse, igual o grafico de Monte Carlo condicional
        // ja fazia -- mantido escondido so da LEGENDA (senao fica poluida), nao do tooltip.
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: R$${ctx.raw?.toFixed(2)??'—'}` } }
      },
      scales: {
        x: { ticks:{ color:'#666', maxTicksLimit:10, font:{size:9} }, grid:{color:'rgba(255,255,255,0.04)'} },
        y: { ticks:{ color:'#aaa', font:{size:10},
               callback: v => 'R$'+v.toFixed(2) }, grid:{color:'rgba(255,255,255,0.06)'} }
      }
    }
  });

  // Score de assertividade na caixa abaixo do gráfico
  const scoreEl = document.getElementById(id+'-foto-score');
  if(scoreEl && data.score){
    const s = data.score;
    scoreEl.innerHTML = `<b>Assertividade</b> (${s.dias_observados} dias observados) — 
      Dentro banda central (p25–p75): <b style="color:var(--green)">${s.pct_dentro_p25_p75}%</b> do tempo · 
      Dentro banda ampla (p10–p90): <b style="color:var(--accent)">${s.pct_dentro_p10_p90}%</b> do tempo`;
  } else if(scoreEl){
    scoreEl.innerHTML = data.historico_real?.length <= 1
      ? '<em style="color:var(--muted)">Foto recém tirada — aguarde o próximo pregão para ver assertividade.</em>'
      : '<em style="color:var(--muted)">Score disponível após o primeiro pregão.</em>';
  }

  // Legenda de confiança -- backlog #2 (30/06/2026): mesmo padrão de
  // texto usado no fan chart de Monte Carlo ("com 80% de confiança..."),
  // agora também na Foto do Papel, não só a mediana solta.
  const confEl = document.getElementById(id+'-foto-confianca');
  if(confEl){
    const last = v => Array.isArray(v) ? v[v.length-1] : null;
    const p10f = last(bandas.p10), p90f = last(bandas.p90);
    const p25f = last(bandas.p25), p75f = last(bandas.p75), p50f = last(bandas.p50);
    if(p10f!=null && p90f!=null){
      confEl.innerHTML =
        `📍 Com <b>80% de confiança</b>, o preço em <b>D+${T}</b> deve estar entre `+
        `<b style="color:var(--red)">R$${p10f.toFixed(2)}</b> e <b style="color:var(--green)">R$${p90f.toFixed(2)}</b>. `+
        (p25f!=null && p75f!=null ? `Com <b>50% de confiança</b>, entre <b style="color:var(--red)">R$${p25f.toFixed(2)}</b> e <b style="color:var(--green)">R$${p75f.toFixed(2)}</b>. ` : '')+
        `Cenário mais provável (mediana): <b style="color:var(--accent)">R$${p50f?.toFixed(2)??'—'}</b>.`;
    } else {
      confEl.innerHTML = '';
    }
  }
}

async function resetarFoto(ticker, id){
  if(!id) id=ticker;
  if(!confirm(`Resetar foto de ${ticker}? A foto atual será apagada.`)) return;
  try{
    await fetch(B+'/foto-papel?ticker='+encodeURIComponent(ticker), {method:'DELETE'});
    delete _fotoData[id];
    if(_fotoCharts[id]){ _fotoCharts[id].destroy(); delete _fotoCharts[id]; }
    const wrap = document.getElementById(id+'-foto-chart-wrap');
    if(wrap) wrap.style.display='none';
    _atualizarStatusFoto(id, null, 0, false, null);
  } catch(e){ alert('Erro ao resetar foto'); }
}

// BULK FOTO -- backlog #3 (30/06/2026): tira a foto de todos os papéis da
// watchlist de uma vez, um de cada vez (mesmo espaçamento de 200ms usado em
// _carregarStatusFotos, pra não sobrecarregar o Render free tier). Sobrescreve
// fotos já existentes (mesmo comportamento do botão individual).
async function tirarFotoTodas(){
  const btn = document.getElementById('btn-bulk-foto');
  const status = document.getElementById('bulk-foto-status');
  const pares = getWatchlistFlat();
  if(!pares.length) return;
  if(!confirm(`Tirar foto de todos os ${pares.length} papéis da watchlist? Isso substitui fotos já existentes e grava no repositório.`)) return;

  if(btn){ btn.disabled = true; btn.textContent = '⏳ Processando...'; }
  if(status){ status.style.display = 'block'; }

  let ok = 0, falhas = [];
  for(let i = 0; i < pares.length; i++){
    const {ticker, id} = pares[i];
    if(status) status.innerHTML = `📸 Tirando foto ${i+1}/${pares.length}: <b>${ticker}</b>... (${ok} ok, ${falhas.length} falhas)`;
    try{
      const r = await fetch(B+'/foto-papel', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ticker})
      });
      const d = await r.json();
      if(d.foto && d.ok){
        ok++;
        _fotoData[id] = { foto: d.foto, historico_real: [], score: null };
        _atualizarStatusFoto(id, d.foto, 0, false, null);
      } else {
        falhas.push(ticker);
      }
    } catch(e){
      falhas.push(ticker);
    }
    await new Promise(res=>setTimeout(res,400)); // escalonado, GARCH+GitHub PUT por papel
  }

  if(status){
    status.innerHTML = `📸 Concluído: <b style="color:var(--green)">${ok}</b> fotos tiradas` +
      (falhas.length ? ` · <b style="color:var(--red)">${falhas.length} falharam</b>: ${falhas.join(', ')}` : '');
  }
  if(btn){ btn.disabled = false; btn.textContent = '📸 Tirar Foto de Todos'; }
}

// Carrega status de foto ao abrir a aba Indicadores (sem forçar render do gráfico)
async function _carregarStatusFotosPares(pares){
  for(const {ticker,id} of pares){
    try{
      const r = await fetch(B+'/foto-papel?ticker='+encodeURIComponent(ticker));
      const d = await r.json();
      if(d.encontrado){
        _fotoData[id] = d;
        _atualizarStatusFoto(id, d.foto, d.dias_uteis_decorridos, d.expirada, d.score);
      }
    } catch(e){}
    await new Promise(res=>setTimeout(res,200));
  }
}
async function _carregarStatusFotos(ids){
  for(const id of ids){
    try{
      const r = await fetch(B+'/foto-papel?ticker='+encodeURIComponent(id));
      const d = await r.json();
      if(d.encontrado){
        _fotoData[id] = d;
        _atualizarStatusFoto(id, d.foto, d.dias_uteis_decorridos, d.expirada, d.score);
      }
    } catch(e){}
    await new Promise(res=>setTimeout(res,200)); // escalonado para nao sobrecarregar
  }
}

// ── FAN CHART — cenários futuros Monte Carlo (watchlist) ──────────────────
const _fanCharts={}; // guarda instancias Chart.js por ativo, para destruir/recriar

function toggleFanChart(id){
  const wrap=document.getElementById(id+'-fc-wrap');
  const btn=document.getElementById(id+'-fc-btn');
  if(!wrap)return;
  const abrir=wrap.style.display==='none';
  wrap.style.display=abrir?'block':'none';
  if(btn)btn.textContent=abrir?'📊 Ocultar cenários futuros':'📊 Ver cenários futuros (Monte Carlo)';
  if(abrir&&!wrap.dataset.loaded){
    wrap.dataset.loaded='1';
    loadFanChart(id,21);
  }
}

async function loadFanChart(id,dias){
  // Marca botão de período ativo
  [21,60,90].forEach(d=>{
    const b=document.getElementById(id+'-fc-'+d);
    if(b)b.className='cal-fb fc-period-btn'+(d===dias?' cal-fb-on':'');
  });
  const info=document.getElementById(id+'-fc-info');
  if(info)info.textContent='Calculando '+dias+' dias de simulação...';
  const ativo=getWatchlistFlat().find(a=>a.id===id);
  if(!ativo)return;
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const r=await fetch(B+'/montecarlo/trajetorias',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify({ticker:ativo.ticker,t_days:dias})
    });
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    renderFanChart(id,d);
  }catch(e){
    if(info)info.textContent='Erro ao simular: '+e.message;
  }
}

function renderFanChart(id,d){
  const canvas=document.getElementById(id+'-fc-canvas');
  const info=document.getElementById(id+'-fc-info');
  if(!canvas||typeof Chart==='undefined'){
    if(info)info.textContent='Gráfico indisponível (Chart.js não carregado)';
    return;
  }
  // Destroi grafico anterior do mesmo ativo, se existir
  if(_fanCharts[id]){ _fanCharts[id].destroy(); }

  const dias=d.dias;
  const datasets=[];

  // Trajetorias individuais — linhas finas, cinza translúcido (efeito "leque")
  d.trajetorias.forEach(traj=>{
    datasets.push({
      data:traj, borderColor:'rgba(124,106,247,.18)', borderWidth:1,
      pointRadius:0, fill:false, tension:0.15, order:2,
    });
  });

  // Banda p25-p75 (preenchida) — faixa central mais provável
  datasets.push({
    label:'P75', data:d.percentis.p75, borderColor:'transparent',
    backgroundColor:'rgba(124,106,247,.12)', pointRadius:0, fill:'+1', order:1, tension:0.15,
  });
  datasets.push({
    label:'P25', data:d.percentis.p25, borderColor:'transparent',
    pointRadius:0, fill:false, order:1, tension:0.15,
  });

  // Mediana (P50) — linha de destaque
  datasets.push({
    label:'Mediana', data:d.percentis.p50, borderColor:'#7c6af7', borderWidth:2.5,
    pointRadius:0, fill:false, order:0, tension:0.15,
  });
  // P10 e P90 — linhas pontilhadas de extremos
  datasets.push({
    label:'P90', data:d.percentis.p90, borderColor:'rgba(0,230,118,.6)', borderWidth:1.5,
    borderDash:[4,3], pointRadius:0, fill:false, order:0, tension:0.15,
  });
  datasets.push({
    label:'P10', data:d.percentis.p10, borderColor:'rgba(240,98,146,.6)', borderWidth:1.5,
    borderDash:[4,3], pointRadius:0, fill:false, order:0, tension:0.15,
  });

  _fanCharts[id]=new Chart(canvas,{
    type:'line',
    data:{ labels:dias, datasets },
    options:{
      responsive:true, maintainAspectRatio:false,
      animation:{duration:300},
      interaction:{intersect:false,mode:'index'},
      plugins:{
        legend:{display:false},
        tooltip:{
          filter:(item)=>['Mediana','P90','P10'].includes(item.dataset.label),
          callbacks:{label:(ctx)=>ctx.dataset.label+': R$ '+ctx.parsed.y.toFixed(2)}
        }
      },
      scales:{
        x:{ title:{display:true,text:'Dias',color:'#505068',font:{size:10}}, ticks:{color:'#505068',font:{size:9}}, grid:{color:'#1e1e2e'} },
        y:{ title:{display:true,text:'Preço (R$)',color:'#505068',font:{size:10}}, ticks:{color:'#505068',font:{size:9}}, grid:{color:'#1e1e2e'} },
      }
    }
  });

  if(info){
    const g=d.garch;
    const garchTxt=g?(' · GARCH '+g.vol_garch_projetada_pct+'%'):(' · Vol.hist '+d.sigma_usado_pct+'%');
    const p10f=d.percentis.p10[d.percentis.p10.length-1];
    const p90f=d.percentis.p90[d.percentis.p90.length-1];
    const p50f=d.percentis.p50[d.percentis.p50.length-1];
    info.innerHTML='Preço atual: <b style="color:var(--text)">R$ '+d.preco_atual.toFixed(2)+'</b>'+garchTxt+
      ' · Faixa P10-P90 em '+d.t_days+'d: <span style="color:var(--red)">R$ '+p10f.toFixed(2)+'</span> a <span style="color:var(--green)">R$ '+p90f.toFixed(2)+'</span>'+
      ' · Mediana: <b style="color:var(--accent)">R$ '+p50f.toFixed(2)+'</b>'+
      '<div style="margin-top:8px;padding:8px 10px;background:rgba(124,106,247,.08);border-left:2px solid var(--accent);font-size:11px;color:var(--text);line-height:1.5;text-align:left">'+
      '📍 Com <b>80% de confiança</b>, o preço em <b>'+d.t_days+' dias</b> deve estar entre <b style="color:var(--red)">R$ '+p10f.toFixed(2)+'</b> e <b style="color:var(--green)">R$ '+p90f.toFixed(2)+'</b>. '+
      'O cenário mais provável (mediana) é <b style="color:var(--accent)">R$ '+p50f.toFixed(2)+'</b>.'+
      '</div>';
  }
}

// ── FAN CHART BTC — Futuro (projeção) e Histórico (retroativo) ──
const _btcCharts={futuro:null,historico:null};

function toggleBtcFanFuturo(){
  const wrap=document.getElementById('btc-fc-fut-wrap');
  const btn=document.getElementById('btc-fc-fut-btn');
  if(!wrap)return;
  const abrir=wrap.style.display==='none';
  wrap.style.display=abrir?'block':'none';
  if(btn)btn.textContent=abrir?'📊 Ocultar projeção futura':'📊 Ver projeção futura (Monte Carlo)';
  if(abrir&&!wrap.dataset.loaded){wrap.dataset.loaded='1';loadBtcFuturo(30);}
}
function toggleBtcFanHistorico(){
  const wrap=document.getElementById('btc-fc-hist-wrap');
  const btn=document.getElementById('btc-fc-hist-btn');
  if(!wrap)return;
  const abrir=wrap.style.display==='none';
  wrap.style.display=abrir?'block':'none';
  if(btn)btn.textContent=abrir?'📈 Ocultar histórico':'📈 Ver histórico vs cenários passados';
  if(abrir&&!wrap.dataset.loaded){wrap.dataset.loaded='1';loadBtcHistorico(90);}
}

async function loadBtcFuturo(dias){
  [30,90,180].forEach(d=>{
    const b=document.getElementById('btc-fc-fut-'+d);
    if(b)b.className='cal-fb fc-period-btn'+(d===dias?' cal-fb-on':'');
  });
  const info=document.getElementById('btc-fc-fut-info');
  if(info)info.textContent='Calculando '+dias+' dias de simulação...';
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const r=await fetch(B+'/montecarlo/trajetorias',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify({ticker:'BTC-USD',t_days:dias})
    });
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    renderBtcFanFuturo(d);
  }catch(e){
    if(info)info.textContent='Erro ao simular: '+e.message;
  }
}

async function loadBtcHistorico(dias){
  [90,180,365].forEach(d=>{
    const b=document.getElementById('btc-fc-hist-'+d);
    if(b)b.className='cal-fb fc-period-btn'+(d===dias?' cal-fb-on':'');
  });
  const info=document.getElementById('btc-fc-hist-info');
  if(info)info.textContent='Calculando '+dias+' dias de histórico...';
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const r=await fetch(B+'/btc/historico',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify({t_days:dias})
    });
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    renderBtcFanHistorico(d);
  }catch(e){
    if(info)info.textContent='Erro ao simular: '+e.message;
  }
}

function renderBtcFanFuturo(d){
  const canvas=document.getElementById('btc-fc-fut-canvas');
  const info=document.getElementById('btc-fc-fut-info');
  if(!canvas||typeof Chart==='undefined'){
    if(info)info.textContent='Gráfico indisponível (Chart.js não carregado)';
    return;
  }
  if(_btcCharts.futuro){ _btcCharts.futuro.destroy(); }
  const dias=d.dias;
  const datasets=[];
  d.trajetorias.forEach(traj=>{
    datasets.push({data:traj,borderColor:'rgba(124,106,247,.18)',borderWidth:1,pointRadius:0,fill:false,tension:0.15,order:2});
  });
  datasets.push({label:'P75',data:d.percentis.p75,borderColor:'transparent',backgroundColor:'rgba(124,106,247,.12)',pointRadius:0,fill:'+1',order:1,tension:0.15});
  datasets.push({label:'P25',data:d.percentis.p25,borderColor:'transparent',pointRadius:0,fill:false,order:1,tension:0.15});
  datasets.push({label:'Mediana',data:d.percentis.p50,borderColor:'#7c6af7',borderWidth:2.5,pointRadius:0,fill:false,order:0,tension:0.15});
  datasets.push({label:'P90',data:d.percentis.p90,borderColor:'rgba(0,230,118,.6)',borderWidth:1.5,borderDash:[4,3],pointRadius:0,fill:false,order:0,tension:0.15});
  datasets.push({label:'P10',data:d.percentis.p10,borderColor:'rgba(240,98,146,.6)',borderWidth:1.5,borderDash:[4,3],pointRadius:0,fill:false,order:0,tension:0.15});

  _btcCharts.futuro=new Chart(canvas,{
    type:'line',
    data:{labels:dias,datasets},
    options:{
      responsive:true,maintainAspectRatio:false,animation:{duration:300},
      interaction:{intersect:false,mode:'index'},
      plugins:{
        legend:{display:false},
        tooltip:{filter:(item)=>['Mediana','P90','P10'].includes(item.dataset.label),
          callbacks:{label:(ctx)=>ctx.dataset.label+': US$ '+ctx.parsed.y.toLocaleString('en-US',{maximumFractionDigits:0})}}
      },
      scales:{
        x:{title:{display:true,text:'Dias',color:'#505068',font:{size:10}},ticks:{color:'#505068',font:{size:9}},grid:{color:'#1e1e2e'}},
        y:{title:{display:true,text:'Preço (US$)',color:'#505068',font:{size:10}},ticks:{color:'#505068',font:{size:9}},grid:{color:'#1e1e2e'}},
      }
    }
  });

  if(info){
    const g=d.garch;
    const garchTxt=g?(' · GARCH '+g.vol_garch_projetada_pct+'%'):(' · Vol.hist '+d.sigma_usado_pct+'%');
    const p10f=d.percentis.p10[d.percentis.p10.length-1];
    const p90f=d.percentis.p90[d.percentis.p90.length-1];
    const p50f=d.percentis.p50[d.percentis.p50.length-1];
    info.innerHTML='Preço atual: <b style="color:var(--text)">'+fU(d.preco_atual)+'</b>'+garchTxt+
      ' · Faixa P10-P90 em '+d.t_days+'d: <span style="color:var(--red)">'+fU(p10f)+'</span> a <span style="color:var(--green)">'+fU(p90f)+'</span>'+
      ' · Mediana: <b style="color:var(--accent)">'+fU(p50f)+'</b>'+
      '<div style="margin-top:8px;padding:8px 10px;background:rgba(124,106,247,.08);border-left:2px solid var(--accent);font-size:11px;color:var(--text);line-height:1.5;text-align:left">'+
      '📍 Com <b>80% de confiança</b>, o preço do BTC em <b>'+d.t_days+' dias</b> deve estar entre <b style="color:var(--red)">'+fU(p10f)+'</b> e <b style="color:var(--green)">'+fU(p90f)+'</b>. '+
      'O cenário mais provável (mediana) é <b style="color:var(--accent)">'+fU(p50f)+'</b>.'+
      '</div>';
  }
}

function renderBtcFanHistorico(d){
  const canvas=document.getElementById('btc-fc-hist-canvas');
  const info=document.getElementById('btc-fc-hist-info');
  if(!canvas||typeof Chart==='undefined'){
    if(info)info.textContent='Gráfico indisponível (Chart.js não carregado)';
    return;
  }
  if(_btcCharts.historico){ _btcCharts.historico.destroy(); }
  const dias=d.dias;
  const datasets=[];
  // Leque retroativo — cenários simulados a partir do preço de N dias atrás
  d.trajetorias.forEach(traj=>{
    datasets.push({data:traj,borderColor:'rgba(124,106,247,.15)',borderWidth:1,pointRadius:0,fill:false,tension:0.1,order:3});
  });
  datasets.push({label:'P75',data:d.percentis.p75,borderColor:'transparent',backgroundColor:'rgba(124,106,247,.10)',pointRadius:0,fill:'+1',order:2,tension:0.1});
  datasets.push({label:'P25',data:d.percentis.p25,borderColor:'transparent',pointRadius:0,fill:false,order:2,tension:0.1});
  datasets.push({label:'Mediana simulada',data:d.percentis.p50,borderColor:'rgba(124,106,247,.7)',borderWidth:1.5,borderDash:[3,3],pointRadius:0,fill:false,order:1,tension:0.1});
  // Preço REAL — linha de destaque por cima de tudo
  datasets.push({label:'Preço real',data:d.precos_reais,borderColor:'#00e676',borderWidth:2.5,pointRadius:0,fill:false,order:0,tension:0.1});

  _btcCharts.historico=new Chart(canvas,{
    type:'line',
    data:{labels:dias,datasets},
    options:{
      responsive:true,maintainAspectRatio:false,animation:{duration:300},
      interaction:{intersect:false,mode:'index'},
      plugins:{
        legend:{display:false},
        tooltip:{filter:(item)=>['Preço real','Mediana simulada'].includes(item.dataset.label),
          callbacks:{label:(ctx)=>ctx.dataset.label+': US$ '+ctx.parsed.y.toLocaleString('en-US',{maximumFractionDigits:0})}}
      },
      scales:{
        x:{title:{display:true,text:'Dias atrás → hoje',color:'#505068',font:{size:10}},ticks:{color:'#505068',font:{size:9}},grid:{color:'#1e1e2e'}},
        y:{title:{display:true,text:'Preço (US$)',color:'#505068',font:{size:10}},ticks:{color:'#505068',font:{size:9}},grid:{color:'#1e1e2e'}},
      }
    }
  });

  if(info){
    const g=d.garch;
    const garchTxt=g?(' · GARCH (na época) '+g.vol_garch_projetada_pct+'%'):(' · Vol.hist (na época) '+d.sigma_usado_pct+'%');
    const real=d.precos_reais[d.precos_reais.length-1];
    const p50f=d.percentis.p50[d.percentis.p50.length-1];
    const dentroFaixa=real>=d.percentis.p10[d.percentis.p10.length-1]&&real<=d.percentis.p90[d.percentis.p90.length-1];
    info.innerHTML='Preço há '+d.t_days+'d: <b style="color:var(--text)">'+fU(d.preco_inicial)+'</b>'+garchTxt+
      ' · Preço real hoje: <b style="color:var(--green)">'+fU(real)+'</b>'+
      ' · Mediana que o modelo previa: <b style="color:var(--accent)">'+fU(p50f)+'</b>'+
      '<div style="margin-top:8px;padding:8px 10px;background:rgba(0,230,118,.08);border-left:2px solid var(--green);font-size:11px;color:var(--text);line-height:1.5;text-align:left">'+
      '📍 Há <b>'+d.t_days+' dias</b> o modelo projetava uma mediana de <b style="color:var(--accent)">'+fU(p50f)+'</b>. '+
      'O preço real percorreu o caminho até <b style="color:var(--green)">'+fU(real)+'</b>, '+
      (dentroFaixa?'dentro da faixa P10-P90 esperada na época ✅':'fora da faixa P10-P90 esperada na época ⚠ (movimento atípico)')+'.'+
      '</div>';
  }
}

function toggleAllInd(){
  const ids=getWatchlistFlat().map(a=>a.id);
  const btn=document.getElementById('btn-all-ind');
  const anyOpen=ids.some(id=>document.getElementById(id+'-ind-wrap')?.classList.contains('open'));
  ids.forEach(id=>{
    const body=document.getElementById(id+'-ind-wrap');
    const arr=document.getElementById('ar-ind-'+id);
    if(body){body.classList.toggle('open',!anyOpen);if(arr)arr.textContent=anyOpen?'▶':'▼';}
  });
  if(btn)btn.textContent=anyOpen?'+ Expandir Todos':'− Recolher Todos';
}
// Guarda preços do ciclo anterior para calcular variação real entre atualizações
const _prevPrices = {};

async function fHL(){
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),10000);
    const r=await fetch('https://api.hyperliquid.xyz/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'allMids'}),signal:ctrl.signal});
    if(!r.ok)return;const d=await r.json();
    const bp=parseFloat(d.BTC||0);
    if(bp>0){
      E('btc-p',fU(bp));
      if(_prevPrices.BTC)Ch('btc-c',bp,_prevPrices.BTC,'u');
      _prevPrices.BTC=bp;
    }
    try{
      const ctrl2=new AbortController();setTimeout(()=>ctrl2.abort(),8000);
      const r2=await fetch('https://api.hyperliquid.xyz/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'allMids',dex:'xyz'}),signal:ctrl2.signal});
      if(r2.ok){const d2=await r2.json();
        const commods=[['CL','cl',2],['GOLD','gold',0],['SILVER','silver',2],['COPPER','copper',3]];
        commods.forEach(([key,id,dec])=>{
          const v=d2['xyz:'+key];
          if(v){
            const p=parseFloat(v);
            E(id+'-p','$'+(dec===0?Number(p).toLocaleString('en-US',{maximumFractionDigits:0}):p.toFixed(dec)));
            if(_prevPrices[key])Ch(id+'-c',p,_prevPrices[key],'u');
            _prevPrices[key]=p;
          }
        });
      }
    }catch(e){}
  }catch(e){}
}
async function fTV(){
  const out={};
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),12000);
    const r=await fetch(B+'/tv/brazil',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify({symbols:{tickers:['BMFBOVESPA:PETR4','BMFBOVESPA:ITUB4','BMFBOVESPA:VALE3','BMFBOVESPA:BBDC4','BMFBOVESPA:ABEV3','BMFBOVESPA:BBAS3','BMFBOVESPA:WEGE3','BMFBOVESPA:IBOV']},columns:['close','change_abs']})});
    if(r.ok){const d=await r.json();(d.data||[]).forEach(x=>{const[c,ca]=x.d||[];if(c!=null)out[x.s]={p:c,v:c-(ca||0)};});}
  }catch(e){}
  try{
    const ctrl2=new AbortController();setTimeout(()=>ctrl2.abort(),10000);
    const rr=await fetch(B+'/indicators/ROXO34.SA',{signal:ctrl2.signal});
    if(rr.ok){const dd=await rr.json();if(dd.preco_atual){
      E('roxo34q-p',fR(dd.preco_atual));
      // Usa preco_anterior da brapi se vier consistente; senão usa ciclo anterior do app
      const prevApi=dd.preco_anterior;
      const prevCiclo=_prevPrices.ROXO34;
      const prev = (prevApi!=null && prevApi!==dd.preco_atual) ? prevApi : prevCiclo;
      if(prev!=null){
        ChTbl('roxo34q-v','roxo34q-c',dd.preco_atual,prev,'r');
      }else{
        const ep=document.getElementById('roxo34q-v');const ec=document.getElementById('roxo34q-c');
        if(ep)ep.textContent='—';if(ec)ec.textContent='—';
      }
      _prevPrices.ROXO34=dd.preco_atual;
    }}
  }catch(e){}
  return out;
}
async function fFut(){try{const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),12000);const r=await fetch(B+'/futures',{signal:ctrl.signal});if(!r.ok)return null;return await r.json();}catch(e){return null;}}
// Adicionado 30/06/2026 -- yields soberanos (EUA 3M/10Y/30Y, Japão 10Y, USD/JPY, SELIC, NTN-B)
async function fYields(){try{const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),10000);const r=await fetch(B+'/yields',{signal:ctrl.signal});if(!r.ok)return null;return await r.json();}catch(e){return null;}}
function doYields(y){
  if(!y)return;
  // Yields são em % a.a. -- exibidos com 2-3 casas decimais, sem prefixo de moeda
  const afY=(idP,idC,data)=>{
    if(!data||data.price==null)return;
    const ep=document.getElementById(idP),ec=document.getElementById(idC);
    if(ep){ep.textContent=Number(data.price).toFixed(2)+'%';ep.classList.remove('loading');}
    if(ec&&data.prev!=null){
      const d=data.price-data.prev,sg=d>=0?'+':'';
      ec.textContent=sg+d.toFixed(3)+'pp'; // variação em pontos percentuais (basis points ÷ 100)
      ec.classList.remove('chg-up','chg-dn','chg-fl');
      ec.classList.add(d>0?'chg-up':d<0?'chg-dn':'chg-fl');
    }
  };
  afY('us3m-p','us3m-c',y.us_3m);
  afY('us10y-p','us10y-c',y.us_10y);
  afY('us30y-p','us30y-c',y.us_30y);
  afY('moveidx-p','moveidx-c',y.move_index);
  // ADICIONADO 26/08/2026 -- pedido do Victor: selo de nivel de estresse
  // ao lado do MOVE Index (calmo/normal/estresse/crise, ver proxy.py).
  if(y.move_index?.nivel_estresse){
    const elp = document.getElementById('moveidx-p');
    if(elp){
      const cores = {calmo:'var(--green)', normal:'var(--muted)', estresse:'var(--warn)', crise:'#ff5252'};
      const labels = {calmo:'calmo', normal:'normal', estresse:'⚠ estresse', crise:'🔴 crise'};
      const nivel = y.move_index.nivel_estresse;
      elp.title = 'Nivel: '+labels[nivel]+' (níveis: <80 calmo, 80-120 normal, 120-150 estresse, ≥150 crise)';
      elp.style.color = cores[nivel] || '';
    }
  }
  afY('jp10y-p','jp10y-c',y.jp_10y);
  // USD/JPY: não é yield, é câmbio -- exibe como número puro sem %
  if(y.usdjpy?.price){
    const ep=document.getElementById('usdjpy-p'),ec=document.getElementById('usdjpy-c');
    if(ep){ep.textContent=Number(y.usdjpy.price).toFixed(2);ep.classList.remove('loading');}
    if(ec&&y.usdjpy.prev!=null){
      const d=y.usdjpy.price-y.usdjpy.prev,pc=(d/Math.abs(y.usdjpy.prev||1)*100).toFixed(2),sg=d>=0?'+':'';
      ec.textContent=sg+pc+'%';
      ec.classList.remove('chg-up','chg-dn','chg-fl');
      ec.classList.add(d>0?'chg-up':d<0?'chg-dn':'chg-fl');
    }
  }
  // SELIC: valor fixo de política monetária (Bacen) -- sem variação diária real
  if(y.br_selic?.price!=null){
    const ep=document.getElementById('brselic-p');
    if(ep){ep.textContent=Number(y.br_selic.price).toFixed(2)+'%';ep.classList.remove('loading');}
  }
  // NTN-B: curva 2/5/10/30Y via ANBIMA ETTJ (dado de fechamento D-1, nao
  // intraday -- mesma natureza do br_selic acima, so mostra valor + label
  // "ANBIMA D-1" ja fixo no HTML, sem tentar simular variacao diaria).
  // ADICIONADO/AMPLIADO 07/08/2026 -- pedido do Victor. Fonte anterior
  // (TradingView, um unico ponto) sempre vinha null.
  const curva = y.br_ntnb_curve;
  ['2','5','','30'].forEach(suf=>{
    const chave = suf ? suf+'y' : '10y';
    const ep = document.getElementById('brntnb'+suf+'-p');
    if(!ep) return;
    const val = curva?.[chave];
    if(val!=null){
      ep.textContent = Number(val).toFixed(2)+'%';
      ep.classList.remove('loading');
      ep.title = 'ANBIMA ETTJ -- referência '+(curva.data_referencia||'');
    }else{
      ep.textContent='—';
      ep.classList.remove('loading');
      ep.title='Fonte pública (ANBIMA) indisponível no momento';
    }
  });
  renderNtnbCurveChart(curva);
}
let _ntnbChart=null;
// ADICIONADO 07/08/2026 -- grafico da curva NTN-B completa (67 pontos, 0.5
// a 33+ anos) + breakeven de inflacao sobreposto (so existe ate ~10y --
// alem disso o mercado prefixado longo nao tem liquidez suficiente pra
// ANBIMA calcular, fica null por design, nao e erro). So renderiza se
// Chart.js e o canvas existirem -- nunca quebra a aba se algo faltar.
function renderNtnbCurveChart(curva){
  try{
    const canvas=document.getElementById('ntnbCurveChart');
    if(!canvas||typeof Chart==='undefined')return;
    const pontos=curva?.curva_completa;
    if(!pontos||!pontos.length)return;
    const labels=pontos.map(p=>p.anos+'a');
    const real=pontos.map(p=>p.ntnb_real);
    const breakeven=pontos.map(p=>p.breakeven);
    if(_ntnbChart){_ntnbChart.destroy();}
    _ntnbChart=new Chart(canvas,{
      type:'line',
      data:{labels,datasets:[
        {label:'NTN-B real',data:real,borderColor:'#2a78d6',backgroundColor:'rgba(42,120,214,0.1)',borderWidth:2,pointRadius:0,fill:true,tension:0.2},
        {label:'Breakeven',data:breakeven,borderColor:'#eb6834',borderWidth:2,pointRadius:0,borderDash:[5,3],tension:0.2,spanGaps:false},
      ]},
      options:{
        responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false}},
        scales:{
          x:{grid:{display:false},ticks:{maxTicksLimit:10,color:'#898781',font:{size:10}}},
          y:{grid:{color:'#e1e0d9'},ticks:{callback:v=>v+'%',color:'#898781',font:{size:10}}},
        },
      },
    });
  }catch(e){/* nao quebra a aba se o Chart.js falhar por qualquer motivo */}
}
async function fFund(){
  try{const r=await fetch('https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT');if(r.ok){const d=await r.json();E('btc-fund',(parseFloat(d.lastFundingRate||0)*100).toFixed(4)+'%');return;}}catch(e){}
  try{const r2=await fetch(B+'/binance/funding');if(!r2.ok)return;const d=await r2.json();if(d.lastFundingRate)E('btc-fund',(parseFloat(d.lastFundingRate)*100).toFixed(4)+'%');}catch(e){}
}
function doMacro(tv,ft){
  [['PETR4','petr4q'],['ITUB4','itub4q'],['VALE3','vale3q'],['BBDC4','bbdc4q'],['ABEV3','abev3q'],['BBAS3','bbas3q'],['WEGE3','wege3q']].forEach(([t,id])=>{
    const d=tv['BMFBOVESPA:'+t];if(d){E(id+'-p',fR(d.p));ChTbl(id+'-v',id+'-c',d.p,d.v,'r');}
  });
  const ib=tv['BMFBOVESPA:IBOV'];if(ib){E('ibov-p',fP(ib.p));ChTbl('ibov-v','ibov-c',ib.p,ib.v,'p');}
  if(ft){
    const af=(id,v)=>{const e=document.getElementById(id);if(e){e.textContent=v;e.classList.remove('loading');}};
    if(ft.dji?.price){af('dji-p',fP(ft.dji.price));ChTbl('dji-v','dji-c',ft.dji.price,ft.dji.prev,'p');}
    if(ft.esf?.price){af('esf-p',fP(ft.esf.price));ChTbl('esf-v','esf-c',ft.esf.price,ft.esf.prev,'p');}
    if(ft.nqf?.price){af('nqf-p',fP(ft.nqf.price));ChTbl('nqf-v','nqf-c',ft.nqf.price,ft.nqf.prev,'p');}
    if(ft.win?.price){af('win-p',fP(ft.win.price));ChTbl('win-v','win-c',ft.win.price,ft.win.prev,'p');}
    if(ft.vix?.price){af('vix-p',Number(ft.vix.price).toFixed(2));ChTbl('vix-v','vix-c',ft.vix.price,ft.vix.prev,'u');}
    if(ft.dxy?.price){af('dxy-p',Number(ft.dxy.price).toFixed(2));ChTbl('dxy-v','dxy-c',ft.dxy.price,ft.dxy.prev,'u');}
    if(ft.usd?.price){af('usd-p',fR(ft.usd.price));ChTbl('usd-v','usd-c',ft.usd.price,ft.usd.prev||ft.usd.price,'r');}
    // Commodities — tabela só tem 1 coluna de variação (preço+%), sem
    // coluna de valor absoluto separada; popula direto sem usar Ch()
    // (que sobrescreveria a classe 'chg' já estilizada para essa tabela)
    const afChg=(idP,idC,now,prev,tp)=>{
      const ep=document.getElementById(idP),ec=document.getElementById(idC);
      if(!ep||now==null)return;
      // CORRIGIDO 23/06/2026: commodities sao cotadas em USD no Yahoo, mas
      // estavam usando fR() (prefixo R$) -- exibia "R$ 73,88" quando o valor
      // real era US$ 73,88, sem nenhuma conversao de cambio. Agora usa fU()
      // (US$) quando tp==='u', mantendo fR() para os casos que sao mesmo R$.
      ep.textContent=tp==='r'?fR(now):tp==='u'?fU(now):Number(now).toFixed(2);
      ep.classList.remove('loading');
      if(ec&&prev!=null){
        const d=now-prev,pc=(d/Math.abs(prev||1)*100).toFixed(2),sg=d>=0?'+':'';
        ec.textContent=sg+pc+'%';
        ec.classList.remove('chg-up','chg-dn','chg-fl');
        ec.classList.add(d>0?'chg-up':d<0?'chg-dn':'chg-fl');
      }
    };
    // CORRIGIDO 23/06/2026: 'u' em vez de 'r' -- todas as commodities sao
    // cotadas em USD no Yahoo, nao em R$ (ver comentario em afChg acima).
    // Minerio de Ferro (TIO=F) tem um sanity check extra: contrato de baixa
    // liquidez sujeito a rollover de vencimento, que pode fazer 'prev' vir
    // de um contrato diferente e gerar variacao % implausivel (caso real
    // observado: ~60% em 1 dia, impossivel para essa commodity). Se a
    // variacao calculada for >15% em modulo, mostra preco mas oculta a
    // variacao (sinal de dado de prev/rollover inconsistente) em vez de
    // exibir um numero errado.
    if(ft.iron_ore?.price){
      const p=ft.iron_ore.price,pv=ft.iron_ore.prev;
      const varPct=pv?Math.abs((p-pv)/pv*100):0;
      afChg('iron_ore-p','iron_ore-c',p,varPct>15?null:pv,'u');
    }
    if(ft.cl?.price)afChg('cl-p','cl-c',ft.cl.price,ft.cl.prev,'u');
    if(ft.brent?.price)afChg('brent-p','brent-c',ft.brent.price,ft.brent.prev,'u');
    if(ft.natgas?.price)afChg('natgas-p','natgas-c',ft.natgas.price,ft.natgas.prev,'u');
    if(ft.gold?.price)afChg('gold-p','gold-c',ft.gold.price,ft.gold.prev,'u');
    if(ft.silver?.price)afChg('silver-p','silver-c',ft.silver.price,ft.silver.prev,'u');
    if(ft.copper?.price)afChg('copper-p','copper-c',ft.copper.price,ft.copper.prev,'u');
    // Adicionado 04/08/2026 -- usuario acompanha o preco A VISTA (spot), nao
    // o futuro -- os dois sao instrumentos diferentes com gap normal entre
    // si (custo de carregamento), nao um bug. Linhas novas lado a lado com
    // o futuro para comparacao direta. copper_spot pode nao existir no
    // Yahoo (ticker XCU=X menos padronizado que XAU=X/XAG=X) -- por isso o
    // optional chaining, a linha so preenche se o dado vier.
    if(ft.gold_spot?.price)afChg('gold_spot-p','gold_spot-c',ft.gold_spot.price,ft.gold_spot.prev,'u');
    if(ft.silver_spot?.price)afChg('silver_spot-p','silver_spot-c',ft.silver_spot.price,ft.silver_spot.prev,'u');
    if(ft.copper_spot?.price)afChg('copper_spot-p','copper_spot-c',ft.copper_spot.price,ft.copper_spot.prev,'u');
    // Adicionado 23/06/2026 -- Europa & Asia (indices, sem moeda --
    // pontos de indice, nao um valor monetario direto, por isso tipo 'n'
    // numero puro em vez de 'r'/'u').
    if(ft.dax?.price)afChg('dax-p','dax-c',ft.dax.price,ft.dax.prev);
    if(ft.cac40?.price)afChg('cac40-p','cac40-c',ft.cac40.price,ft.cac40.prev);
    if(ft.stoxx50?.price)afChg('stoxx50-p','stoxx50-c',ft.stoxx50.price,ft.stoxx50.prev);
    if(ft.ftse100?.price)afChg('ftse100-p','ftse100-c',ft.ftse100.price,ft.ftse100.prev);
    if(ft.nikkei?.price)afChg('nikkei-p','nikkei-c',ft.nikkei.price,ft.nikkei.prev);
    if(ft.hangseng?.price)afChg('hangseng-p','hangseng-c',ft.hangseng.price,ft.hangseng.prev);
    if(ft.sse?.price)afChg('sse-p','sse-c',ft.sse.price,ft.sse.prev);
    if(ft.asx200?.price)afChg('asx200-p','asx200-c',ft.asx200.price,ft.asx200.prev);
    if(ft.kospi?.price)afChg('kospi-p','kospi-c',ft.kospi.price,ft.kospi.prev);
  }
}
function doPos(tv){
  if(!_posData||!_posData.ativas)return; // aguarda positions.json carregar
  const byId={}; _posData.ativas.forEach(p=>byId[p.id]=p);

  // PETR4 e VALE3 — cotação via TV scanner
  if(byId.pt){
    const pt=tv['BMFBOVESPA:PETR4'];const pp=pt?.p||40,pv=pt?.v||40;
    E('pt-p',fR(pp));Ch('pt-c',pp,pv,'r');
    const pd=pp-byId.pt.strike;E('pt-itm',(pd>=0?'+ R$ ':'- R$ ')+Math.abs(pd).toFixed(2)+' '+(pd>=0?'acima':'abaixo')+' do strike');
  }
  if(byId.vl){
    const vl=tv['BMFBOVESPA:VALE3'];const vp=vl?.p||78,vv=vl?.v||78;
    E('vl-p',fR(vp));Ch('vl-c',vp,vv,'r');
    const vd=vp-byId.vl.strike;E('vl-itm',(vd>=0?'+ R$ ':'- R$ ')+Math.abs(vd).toFixed(2)+' '+(vd>=0?'acima':'abaixo')+' do strike');
  }

  // Contador de dias/horas dinâmico — itera todas as posições do JSON
  const cdHoras=(ds,eid)=>{
    const v=new Date(ds),agora=new Date();
    const diffMs=v-agora;
    const diffDias=Math.ceil(diffMs/864e5);
    const el=document.getElementById(eid);
    if(!el)return;
    if(diffDias<=0){el.innerHTML='<span class="pos-venc-urgente">Vencido</span>';_risco.vencUrgente=true;return;}
    if(diffDias<=7){
      const diffH=Math.ceil(diffMs/3600000);
      el.innerHTML=`<span class="pos-venc-urgente">⚠ ${diffDias}d ${diffH%24}h restantes</span>`;
      _risco.vencUrgente=true;
    }else if(diffDias<=30){
      el.innerHTML=`<span class="pos-venc-atencao">${diffDias} dias</span>`;
    }else{
      el.textContent=diffDias+' dias';
    }
  };
  _posData.ativas.forEach(p=>cdHoras(p.vencimento, p.id+'-dias'));
  checkBadgeRisco();

  // AXIA3 A, B e C — preço via /indicators, distância KDO/KUO
  const a3=byId.a3, a3b=byId.a3b, a3c=byId.a3c;
  if(a3||a3b||a3c){
    setTimeout(async()=>{
      try{const r=await fetch(B+'/indicators/AXIA3.SA');if(!r.ok)return;const d=await r.json();if(!d.preco_atual)return;
        const p=d.preco_atual,pant=d.preco_anterior||p;
        if(a3){E('a3-p',fR(p));Ch('a3-c',p,pant,'r');}
        if(a3b){E('a3b-p',fR(p));Ch('a3b-c',p,pant,'r');}
        if(a3c){E('a3c-p',fR(p));Ch('a3c-c',p,pant,'r');}
        if(a3){
          const kA=a3.kdo,kuA=a3.kuo;
          const dA=document.getElementById('a3-kdo');if(dA)dA.textContent=((p-kA)/p*100).toFixed(1)+'% acima do KDO';
          const uA=document.getElementById('a3-kuo');if(uA)uA.textContent=((kuA-p)/p*100).toFixed(1)+'% para o KUO';
          const sA=document.getElementById('a3-st');if(sA){sA.textContent=p<=kA?'🔴 KDO ATINGIDO':p>=kuA?'⚠ KUO ATINGIDO':'✅ No range';sA.className='sv '+(p<=kA||p>=kuA?'warn':'ok');}
          checkAlertaBarreira('card-a3', p, kA, kuA);
        }
        if(a3b){
          const kB=a3b.kdo,kuB=a3b.kuo;
          const dB=document.getElementById('a3b-kdo');if(dB)dB.textContent=((p-kB)/p*100).toFixed(1)+'% acima do KDO';
          const uB=document.getElementById('a3b-kuo');if(uB)uB.textContent=((kuB-p)/p*100).toFixed(1)+'% para o KUO';
          const sB=document.getElementById('a3b-st');if(sB){sB.textContent=p<=kB?'🔴 KDO ATINGIDO':p>=kuB?'⚠ KUO ATINGIDO':'✅ No range';sB.className='sv '+(p<=kB||p>=kuB?'warn':'ok');}
          checkAlertaBarreira('card-a3b', p, kB, kuB);
        }
        if(a3c){
          const kC=a3c.kdo,kuC=a3c.kuo;
          const dC=document.getElementById('a3c-kdo');if(dC)dC.textContent=((p-kC)/p*100).toFixed(1)+'% acima do KDO';
          const uC=document.getElementById('a3c-kuo');if(uC)uC.textContent=((kuC-p)/p*100).toFixed(1)+'% para o KUO';
          const sC=document.getElementById('a3c-st');if(sC){sC.textContent=p<=kC?'🔴 KDO ATINGIDO':p>=kuC?'⚠ KUO ATINGIDO':'✅ No range';sC.className='sv '+(p<=kC||p>=kuC?'warn':'ok');}
          checkAlertaBarreira('card-a3c', p, kC, kuC);
        }
        checkBadgeRisco();
      }catch(e){}
    },2000);
  }

  // ROXO34 — preço via /indicators (Yahoo bloqueia), ITM/OTM
  if(byId.rx){
    setTimeout(async()=>{
      try{const r=await fetch(B+'/indicators/ROXO34.SA');if(!r.ok)return;const d=await r.json();if(!d.preco_atual)return;
        const p=d.preco_atual,pant2=d.preco_anterior||p;E('rx-p',fR(p));Ch('rx-c',p,pant2,'r');
        const strike=byId.rx.strike;
        const itm=document.getElementById('rx-itm');
        const dist=p-strike;
        if(itm)itm.textContent=(dist>=0?'+ R$ ':'- R$ ')+Math.abs(dist).toFixed(2)+' '+(dist>=0?'acima (ITM ⚠)':'abaixo (OTM ✅)')+' do strike';
        _risco.roxoItm=p>strike;
        checkBadgeRisco();
      }catch(e){}
    },3000);
  }
}

function checkAlertaBarreira(cardId, preco, kdo, kuo){
  const card=document.getElementById(cardId);
  if(!card)return;
  const distKdo=(preco-kdo)/preco*100;
  const distKuo=(kuo-preco)/preco*100;
  const emRisco=distKdo<=5||distKuo<=5||preco<=kdo||preco>=kuo;
  card.classList.toggle('pos-alerta', emRisco);
  if(emRisco)_risco.barreira=true;
}

// Estado de risco das posições
const _risco = {barreira:false, roxoItm:false, vencUrgente:false};

function checkBadgeRisco(){
  const badge=document.getElementById('pos-badge');
  if(!badge)return;
  const temRisco=_risco.barreira||_risco.roxoItm||_risco.vencUrgente;
  badge.style.display=temRisco?'inline':'none';
}
async function MC(tk,sk,dias,lId,rId,iId,rtId,vsId,volsId,exercicio){
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const r=await fetch(B+'/montecarlo',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,body:JSON.stringify({ticker:tk,k_call:sk,k_put:sk,t_days:dias,n:5000,exercicio:exercicio||'europeia'})});
    if(!r.ok)throw 0;const d=await r.json();if(d.error)throw new Error(d.error);
    document.getElementById(lId).style.display='none';document.getElementById(rId).style.display='block';
    const riscoCls=p=>p<15?'ok':p<30?'warn':'itm';
    const prob=Number(d.prob_call_exercida||0);
    if(rtId){const rtEl=document.getElementById(rtId);if(rtEl){rtEl.textContent=prob.toFixed(1)+'%';rtEl.className='sv '+riscoCls(prob);}}
    let garchTxt='';
    let probHist=null;
    if(d.garch&&d.comparativo_vol_historica){
      probHist=Number(d.comparativo_vol_historica.prob_call_exercida||0);
      const diff=prob-probHist;
      const diffTxt=diff>0?`+${diff.toFixed(1)}pp maior`:diff<0?`${diff.toFixed(1)}pp menor`:'igual';
      garchTxt=`Vol.Simples ${d.volatilidade_historica_simples_pct}% → ${probHist.toFixed(1)}% exercer · <b>GARCH ${d.garch.vol_garch_projetada_pct}%</b> → ${prob.toFixed(1)}% exercer (${diffTxt})`;
    } else if(d.garch){
      garchTxt=`GARCH proj. ${d.garch.vol_garch_projetada_pct}% (persist. ${d.garch.persistencia})`;
    } else {
      garchTxt=`Vol.hist. ${d.volatilidade_historica_pct}%`;
    }
    if(vsId){
      const vsEl=document.getElementById(vsId);
      if(vsEl){
        if(probHist!=null){vsEl.textContent=probHist.toFixed(1)+'%';vsEl.className='sv '+riscoCls(probHist);}
        else{vsEl.textContent='—';vsEl.className='sv';}
      }
    }
    if(volsId){
      const volsEl=document.getElementById(volsId);
      if(volsEl){
        if(d.volatilidade_historica_simples_pct!=null&&d.garch){
          volsEl.textContent=d.volatilidade_historica_simples_pct+'% / '+d.garch.vol_garch_projetada_pct+'%';
        } else {
          volsEl.textContent=d.volatilidade_historica_pct+'%';
        }
      }
    }
    document.getElementById(iId).innerHTML=garchTxt+' · '+(prob<15?'<span style="color:var(--green)">✅ Risco baixo de exercício</span>':'<span style="color:var(--warn)">⚠ Monitorar posição</span>');
  }catch(e){const el=document.getElementById(lId);if(el)el.textContent='Erro: '+(e.message||'timeout');}
}
async function MCB(tk,en,kd,ku,dias,pfx){
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const r=await fetch(B+'/montecarlo/barrier',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,body:JSON.stringify({ticker:tk,entry:en,kdo:kd,kuo:ku,t_days:dias,n:3000})});
    if(!r.ok)throw 0;const d=await r.json();if(d.error)throw new Error(d.error);
    document.getElementById(pfx+'-mc-l').style.display='none';document.getElementById(pfx+'-mc-r').style.display='block';
    document.getElementById(pfx+'-mc-nb').textContent=d.prob_sem_barreira.toFixed(1)+'%';
    document.getElementById(pfx+'-mc-ku').textContent=d.prob_barreira_alta.toFixed(1)+'%';
    document.getElementById(pfx+'-mc-kd').textContent=d.prob_barreira_baixa.toFixed(1)+'%';
    document.getElementById(pfx+'-mc-vo').textContent=d.volatilidade_historica_pct+'%';
    let cmpTxt='';
    if(d.garch&&d.comparativo_vol_historica){
      const c=d.comparativo_vol_historica;
      cmpTxt=` · Vol.Simples ${d.volatilidade_historica_simples_pct}% → Sem barreira ${c.prob_sem_barreira.toFixed(1)}% / KUO ${c.prob_barreira_alta.toFixed(1)}% / KDO ${c.prob_barreira_baixa.toFixed(1)}% · <b>GARCH ${d.garch.vol_garch_projetada_pct}%</b> → Sem barreira ${d.prob_sem_barreira.toFixed(1)}% / KUO ${d.prob_barreira_alta.toFixed(1)}% / KDO ${d.prob_barreira_baixa.toFixed(1)}%`;
    } else if(d.garch){
      cmpTxt=` · GARCH proj. ${d.garch.vol_garch_projetada_pct}% (LP ${d.garch.vol_garch_longo_prazo_pct}%)`;
    }
    document.getElementById(pfx+'-mc-i').innerHTML='R$ '+d.preco_atual+' · KDO R$ '+d.kdo+' · KUO R$ '+d.kuo+cmpTxt;
  }catch(e){const el=document.getElementById(pfx+'-mc-l');if(el)el.textContent='Erro: '+(e.message||'timeout');}
}

// Adicionado 26/06/2026 -- preenche cotacao atual ('-p'), Dist. KDO
// ('-kdo') e Situacao ('-st') para posicoes tipo_posicao='barreira_simples'
// (retorno_controlado, so KDO sem KUO -- ex: BSLV39). Reaproveita
// /montecarlo/posicao_ativa em vez de /montecarlo/barrier (que exige
// KUO obrigatorio) -- mesmo endpoint ja confirmado funcionando para o
// fan chart do botao "Ver evolucao desde a entrada".
async function MCBSimples(p){
  const id=p.id;
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const body={ticker:p.ticker,data_entrada:p.data_entrada,vencimento:p.vencimento,kdo:p.kdo};
    if(p.ganho_prefixado_pct!=null)body.ganho_prefixado_pct=p.ganho_prefixado_pct;
    // ADICIONADO 30/06/2026 -- mesmo motivo da outra chamada a este endpoint
    // (ver loadEvolucaoPosicao): preco de entrada real tem prioridade sobre
    // extracao do Yahoo, que falha para ativos iliquidos como BSLV39.
    if(p.entry!=null)body.entry=p.entry;
    const r=await fetch(B+'/montecarlo/posicao_ativa',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    const pEl=document.getElementById(id+'-p');
    if(pEl){pEl.textContent='R$ '+d.preco_atual.toFixed(2).replace('.',',');pEl.classList.remove('loading');}
    const cEl=document.getElementById(id+'-c');
    if(cEl){
      const variacao=((d.preco_atual/d.preco_entrada-1)*100);
      cEl.textContent=(variacao>=0?'+':'')+variacao.toFixed(2)+'% desde a entrada';
    }
    const kdoEl=document.getElementById(id+'-kdo');
    if(kdoEl){
      const distKdo=((d.preco_atual/p.kdo-1)*100);
      kdoEl.textContent=distKdo.toFixed(1)+'% acima do KDO';
      kdoEl.className='sv '+(distKdo<10?'itm':distKdo<25?'warn':'ok');
    }
    const stEl=document.getElementById(id+'-st');
    if(stEl){
      const tocouBarreira=d.preco_atual<=p.kdo;
      stEl.textContent=tocouBarreira?'⚠ Barreira tocada':'✅ Dentro da faixa';
      stEl.className='sv '+(tocouBarreira?'itm':'ok');
    }
  }catch(e){
    const stEl=document.getElementById(id+'-st');
    if(stEl)stEl.textContent='Erro: '+e.message;
  }
}
async function MCR(tk,en,kd,dias,price){
  try{
    // CORRIGIDO 23/06/2026: timeout reduzido de 40000 para 25000 (igual MC) --
    // o tempo extra so compensava a chamada previa a /indicators, que foi
    // removida. Agora MCR faz so 1 chamada de rede, igual as outras.
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const payload={ticker:tk,k_call:en,k_put:en,t_days:dias,n:5000,exercicio:'americana'};
    if(kd)payload.knock_down=kd;
    if(price)payload.price=price;
    const r=await fetch(B+'/montecarlo',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,body:JSON.stringify(payload)});
    if(!r.ok)throw 0;const d=await r.json();if(d.error)throw new Error(d.error);
    document.getElementById('rx-mc-l').style.display='none';document.getElementById('rx-mc-r').style.display='block';
    const riscoCls=p=>p<15?'ok':p<30?'warn':'itm';
    const prob=Number(d.prob_call_exercida||0);
    const rtEl=document.getElementById('rx-mc-rt');
    if(rtEl){rtEl.textContent=prob.toFixed(1)+'%';rtEl.className='sv '+riscoCls(prob);}
    let probHist=null;
    let cmpTxt='';
    if(d.garch&&d.comparativo_vol_historica){
      probHist=Number(d.comparativo_vol_historica.prob_call_exercida||0);
      const diff=prob-probHist;
      const diffTxt=diff>0?`+${diff.toFixed(1)}pp maior`:diff<0?`${diff.toFixed(1)}pp menor`:'igual';
      cmpTxt=`Vol.Simples ${d.volatilidade_historica_simples_pct}% → ${probHist.toFixed(1)}% exercer · <b>GARCH ${d.garch.vol_garch_projetada_pct}%</b> → ${prob.toFixed(1)}% exercer (${diffTxt})`;
    } else if(d.garch){
      cmpTxt=`GARCH proj. ${d.garch.vol_garch_projetada_pct}%`;
    } else {
      cmpTxt=`Vol.hist. ${d.volatilidade_historica_pct}%`;
    }
    const vsEl=document.getElementById('rx-mc-vs');
    if(vsEl){
      if(probHist!=null){vsEl.textContent=probHist.toFixed(1)+'%';vsEl.className='sv '+riscoCls(probHist);}
      else{vsEl.textContent='—';vsEl.className='sv';}
    }
    const volsEl=document.getElementById('rx-mc-vols');
    if(volsEl){
      if(d.volatilidade_historica_simples_pct!=null&&d.garch){
        volsEl.textContent=d.volatilidade_historica_simples_pct+'% / '+d.garch.vol_garch_projetada_pct+'%';
      } else {
        volsEl.textContent=d.volatilidade_historica_pct+'%';
      }
    }
    const iEl=document.getElementById('rx-mc-i');
    if(iEl)iEl.innerHTML='R$ '+d.preco_atual+(d.knock_down?' · KDO R$ '+d.knock_down:'')+' · '+cmpTxt+' · '+(prob<15?'<span style="color:var(--green)">✅ Risco baixo de exercício</span>':'<span style="color:var(--warn)">⚠ Monitorar posição</span>');
  }catch(e){const el=document.getElementById('rx-mc-l');if(el)el.textContent='Erro: '+(e.message||'timeout');}
}
async function fInd(tk){try{const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),30000);const r=await fetch(B+'/indicators/'+tk,{signal:ctrl.signal});if(!r.ok)return null;return await r.json();}catch(e){return null;}}
async function fBTCI(){try{const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);const r=await fetch(B+'/btc/indicators',{signal:ctrl.signal});if(!r.ok)return null;return await r.json();}catch(e){return null;}}
async function fBTCC(){try{const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);const r=await fetch(B+'/btc/cycle',{signal:ctrl.signal});if(!r.ok)return null;return await r.json();}catch(e){return null;}}
async function fFG(){
  try{
    const r=await fetch(B+'/feargreed');if(!r.ok)return;const d=await r.json();
    const v=d.value||50,cls=v<=25?'var(--red)':v<=45?'var(--warn)':v<=75?'var(--accent)':'var(--green)';
    const el=document.getElementById('fg-area');
    if(el)el.innerHTML='<div style="background:var(--bg2);border:1px solid var(--border);padding:16px"><div style="font-size:11px;color:var(--muted);margin-bottom:8px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">😱 Fear & Greed Index</div><div style="display:flex;align-items:center;gap:14px"><div style="font-size:38px;font-weight:800;color:'+cls+'">'+v+'</div><div style="font-size:16px;font-weight:700;color:'+cls+'">'+(d.value_classification||'Neutro')+'</div></div></div>';
    E('fg-val',String(v));E('fg-lbl',d.value_classification||'Neutro');
    try{const rb=await fetch('https://api.hyperliquid.xyz/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'allMids'})});if(rb.ok){const db=await rb.json();const bp=parseFloat(db.BTC||0);if(bp>0){E('btc-ind-p','$'+Number(bp).toLocaleString('en-US',{maximumFractionDigits:0}));E('btc-p',fU(bp));}}}catch(e2){}
  }catch(e){}
}
function rndInd(id,data){
  const el=document.getElementById(id+'-ind');if(!el)return;
  if(!data){el.innerHTML='<div style="color:var(--warn);padding:12px;font-size:13px">⏳ Sem resposta — clique ↻</div>';return;}
  if(data.error){el.innerHTML='<div style="color:var(--red);padding:12px;font-size:13px">⚠ '+data.error+'</div>';return;}
  const inds=data.indicadores||[],sc=Number(data.score_total||0),preco=data.preco_atual,setor=data.setor||'';
  const sc2=sc>=65?'var(--green)':sc>=40?'var(--warn)':'var(--red)',sl=sc>=65?'Compra ▲':sc>=40?'Neutro →':'Venda ▼';
  let h='';
  if(data.fund_desatualizado){
    h+='<div style="background:rgba(255,183,77,.1);border:1px solid var(--warn);padding:8px 12px;margin-bottom:10px;font-size:11px;color:var(--warn);font-weight:600">⚠ Fundamentais (P/L, P/VP, ROE, Graham) com '+data.fund_idade_dias+' dias — solicitar revisão trimestral</div>';
  }
  // Convergência de preços-alvo — 4 métodos lado a lado (calculado antes para usar a média no destaque principal)
  const metodos=[
    {nome:'Graham',valor:data.graham_value,up:data.upside_graham},
    {nome:'Bazin',valor:data.preco_alvo_bazin,up:data.upside_bazin},
    {nome:'P/L Setor',valor:data.preco_alvo_pl_setorial,up:data.upside_pl_setorial},
    {nome:'P/VP Setor',valor:data.preco_alvo_vpa,up:data.upside_vpa},
  ].filter(m=>m.valor!=null);
  const mediaDestaque = metodos.length>0 ? metodos.reduce((s,m)=>s+m.valor,0)/metodos.length : null;
  const upMedia = (mediaDestaque && preco) ? Math.round((mediaDestaque/preco-1)*1000)/10 : null;
  h+='<div class="scb">'+
    '<div class="scc"><div class="scm">Score</div><div class="scn" style="color:'+sc2+'">'+sc+'</div><div class="scl" style="color:'+sc2+'">'+sl+'</div></div>'+
    '<div class="scc"><div class="scm">Cotação</div><div class="scv">'+(preco?'R$ '+Number(preco).toFixed(2):'—')+'</div><div class="scs">'+setor+'</div></div>'+
    '<div class="scc"><div class="scm">Méd. 4 Métodos</div><div class="scv" style="color:'+(upMedia&&upMedia>0?'var(--green)':'var(--red)')+'">'+(mediaDestaque?'R$ '+mediaDestaque.toFixed(2):'—')+'</div><div class="scs" style="color:'+(upMedia&&upMedia>0?'var(--green)':'var(--red)')+'">'+(upMedia!=null?(upMedia>0?'+':'')+upMedia+'% upside':'—')+'</div></div>'+
    '</div>';
  if(metodos.length>0){
    const media=metodos.reduce((s,m)=>s+m.valor,0)/metodos.length;
    const desvios=metodos.map(m=>Math.abs(m.valor-media)/media*100);
    const maxDesvio=Math.max(...desvios);
    const convergencia=maxDesvio<15?'✅ Convergem':maxDesvio<35?'⚠ Divergência moderada':'🔴 Divergência alta';
    const convCor=maxDesvio<15?'var(--green)':maxDesvio<35?'var(--warn)':'var(--red)';
    let garchLinha='';
    if(data.garch){
      const g=data.garch;
      const tendVol=g.vol_garch_projetada_pct>g.vol_garch_atual_pct?'↑ subindo':g.vol_garch_projetada_pct<g.vol_garch_atual_pct?'↓ descendo':'→ estável';
      garchLinha='<div style="font-size:10px;color:var(--muted);margin-top:6px;padding-top:6px;border-top:1px solid var(--border)">GARCH(1,1) — Vol. atual '+g.vol_garch_atual_pct+'% · projetada '+g.horizon_days+'d '+g.vol_garch_projetada_pct+'% ('+tendVol+') · persistência '+g.persistencia+'</div>';
    }
    h+='<div style="background:var(--bg2);border:1px solid var(--border);padding:12px;margin-bottom:14px">'+
      '<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">CONVERGÊNCIA DE PREÇOS-ALVO ('+metodos.length+' métodos)</div>'+
      '<div style="display:grid;grid-template-columns:repeat('+metodos.length+',1fr);gap:6px;margin-bottom:8px">'+
      metodos.map(m=>'<div style="text-align:center"><div style="font-size:9px;color:var(--muted)">'+m.nome+'</div><div style="font-size:13px;font-weight:700;color:'+(m.up>0?'var(--green)':'var(--red)')+'">R$ '+m.valor.toFixed(2)+'</div></div>').join('')+
      '</div>'+
      '<div style="font-size:11px;color:'+convCor+';font-weight:600">'+convergencia+' (desvio máx '+maxDesvio.toFixed(0)+'%) · Média: R$ '+media.toFixed(2)+'</div>'+
      garchLinha+
      '</div>';
  }
  inds.forEach(i=>{
    const s=i.sinal||'',cls=s==='Alta'||s==='Sobrevenda'?'ok':s==='Baixa'||s==='Sobrecompra'?'down':'warn',ar=cls==='ok'?'▲':cls==='down'?'▼':'→';
    h+='<div class="ir"><div class="irt"><span class="irn">'+(i.nome||'')+'</span><span class="irv '+cls+'">'+(i.valor!=null?i.valor:'—')+' '+ar+'</span></div>'+(i.explicacao?'<div class="ire">'+i.explicacao+'</div>':'')+'</div>';
  });
  el.innerHTML=h||'<div style="color:var(--muted);padding:10px">Sem indicadores</div>';
}
function rndBTCI(d){
  const el=document.getElementById('btc-ind-area');if(!el||!d)return;
  if(d.error){el.innerHTML='<div style="color:var(--warn);padding:12px;font-size:13px">⏳ '+d.error+'</div>';return;}
  let h='<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">';
  if(d.rsi_semanal!=null){const rv=d.rsi_semanal,rc=rv<30?'ok':rv>70?'down':'warn';h+='<div class="ib"><div class="il">RSI Semanal</div><div class="iv '+rc+'">'+rv.toFixed(1)+'</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+(rv<30?'Sobrevenda ⚡':rv>70?'Sobrecompra ⚠':'Neutro')+'</div></div>';E('btc-rsi',rv.toFixed(1));}
  if(d.mm50_semanal)h+='<div class="ib"><div class="il">MM 50 sem.</div><div class="iv warn">$'+Number(d.mm50_semanal).toLocaleString('en-US',{maximumFractionDigits:0})+'</div></div>';
  if(d.mm200_semanal)h+='<div class="ib"><div class="il">MM 200 sem.</div><div class="iv warn">$'+Number(d.mm200_semanal).toLocaleString('en-US',{maximumFractionDigits:0})+'</div></div>';
  if(d.macd_histogram!=null){const mh=d.macd_histogram;h+='<div class="ib"><div class="il">MACD Hist.</div><div class="iv '+(mh>0?'ok':'down')+'">'+Number(mh).toLocaleString('en-US',{maximumFractionDigits:0})+'</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+(mh>0?'Momentum ▲':'Momentum ▼')+'</div></div>';}
  if(d.obv_trend)h+='<div class="ib"><div class="il">OBV</div><div class="iv '+(d.obv_trend==='subindo'?'ok':'down')+'">'+d.obv_trend+'</div></div>';
  h+='</div>';el.innerHTML=h;
  if(d.price)E('btc-ind-p','$'+Number(d.price).toLocaleString('en-US',{maximumFractionDigits:0}));
}
function rndBTCC(d){
  const el=document.getElementById('btc-cycle-area');if(!el||!d||d.error)return;
  const fU2=v=>v?'$'+Number(v).toLocaleString('en-US',{maximumFractionDigits:0}):'—';
  el.innerHTML='<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">'+
    '<div class="ib"><div class="il">Puell Multiple</div><div class="iv warn">'+d.puell?.value+'</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+d.puell?.label+'</div></div>'+
    '<div class="ib"><div class="il">200W MA</div><div class="iv warn">'+fU2(d.ma200w)+'</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+(d.ma200w_pct?'+'+d.ma200w_pct+'%':'')+'</div></div>'+
    '<div class="ib"><div class="il">Rainbow Band</div><div class="iv warn">'+(d.rainbow?.band||'—')+'</div></div>'+
    '<div class="ib"><div class="il">Pi Cycle Dist.</div><div class="iv ok">'+fU2(d.pi_cycle?.distance)+'</div></div>'+
    '</div><div style="background:var(--bg2);border:1px solid var(--border);padding:10px;font-size:13px;color:var(--accent);font-weight:600">'+(d.pi_cycle?.signal||'')+'</div>'+
    '<div style="font-size:10px;color:var(--muted);margin-top:8px;text-align:center">MVRV/NUPL removidos — sem fonte gratuita confiável sem cadastro/API key (verificado 19/06/2026)</div>';
}
async function loadInd(){
  renderWatchlist();
  const wt=(p,ms,fb)=>Promise.race([p,new Promise(r=>setTimeout(()=>r(fb),ms))]);
  const[bi,bc]=await Promise.all([wt(fBTCI(),15000,{error:'Timeout — clique ↻'}),wt(fBTCC(),15000,null)]);
  rndBTCI(bi);rndBTCC(bc);fFG();
  // Lazy load: indicadores de cada ativo da watchlist NÃO carregam aqui —
  // só quando o usuário clica para expandir o card (ver togInd), via rl(id).
  // Antes, todos os ~16+ ativos eram buscados de uma vez ao abrir a aba,
  // deixando o carregamento pesado mesmo sem o usuário pedir.
  // Carrega status de fotos (adicionado 30/06/2026) em background, escalonado.
  setTimeout(()=>{
    const atvsFlat = getWatchlistFlat(); const ids = atvsFlat.map(a=>({ticker:a.ticker,id:a.id}));
    _carregarStatusFotosPares(ids);
  }, 1500);
}
async function rl(tk){
  const el=document.getElementById(tk+'-ind');
  if(el)el.innerHTML='<div style="color:var(--muted);padding:12px;animation:pulse 1s infinite">Carregando...</div>';
  const ativo=getWatchlistFlat().find(a=>a.id===tk);
  if(!ativo)return;
  rndInd(tk,await fInd(ativo.ticker));
}
const FLAGS={'USD':'🇺🇸','US':'🇺🇸','BRL':'🇧🇷','BR':'🇧🇷','EUR':'🇪🇺','EU':'🇪🇺','GBP':'🇬🇧','CNY':'🇨🇳','JPY':'🇯🇵','CAD':'🇨🇦','AUD':'🇦🇺','DE':'🇩🇪','NZD':'🇳🇿','CHF':'🇨🇭'};
// ── CALENDÁRIO ────────────────────────────────────────
let _calEvs = [];
let _calSemana = 'todas';
let _calMoeda  = 'TODAS';

function calFiltroSemana(v){
  _calSemana = v;
  ['todas','esta','proxima'].forEach(x=>{
    const b=document.getElementById('cal-f-'+x);
    if(b)b.className='cal-fb'+(x===v?' cal-fb-on':'');
  });
  renderCal();
}
function calFiltroMoeda(v){
  _calMoeda = v;
  ['TODAS','USD','EUR','GBP','JPY','CNY'].forEach(x=>{
    const b=document.getElementById('cal-m-'+x);
    if(b)b.className='cal-fb'+(x===v?' cal-fb-on':'');
  });
  renderCal();
}

function getWeekRange(offset){
  const hoje=new Date();
  const dow=hoje.getDay()||7; // 1=seg 7=dom
  const seg=new Date(hoje); seg.setDate(hoje.getDate()-dow+1+offset*7);
  const dom=new Date(seg); dom.setDate(seg.getDate()+6);
  const fmt=d=>d.toISOString().slice(0,10);
  return {ini:fmt(seg),fim:fmt(dom)};
}

function renderCal(){
  const el=document.getElementById('cal-area');
  const st=document.getElementById('cal-st');
  if(!el||!_calEvs.length)return;

  const hoje=new Date().toISOString().slice(0,10);
  const semEsta=getWeekRange(0);
  const semProx=getWeekRange(1);

  let evs=_calEvs.filter(e=>{
    if(_calMoeda!=='TODAS'&&e.country!==_calMoeda)return false;
    if(_calSemana==='esta')return e.date>=semEsta.ini&&e.date<=semEsta.fim;
    if(_calSemana==='proxima')return e.date>=semProx.ini&&e.date<=semProx.fim;
    return true;
  });

  if(st)st.textContent=evs.length+' eventos';
  if(!evs.length){el.innerHTML='<p style="color:var(--muted);padding:20px;text-align:center">Sem eventos para este filtro</p>';return;}

  const byD={};
  evs.forEach(e=>{
    if(!byD[e.date])byD[e.date]=[];
    byD[e.date].push(e);
  });

  let h='';
  Object.keys(byD).sort().forEach(dt=>{
    const isHoje=dt===hoje;
    const d=new Date(dt+'T12:00:00');
    const lbl=d.toLocaleDateString('pt-BR',{weekday:'long',day:'2-digit',month:'short'});
    h+='<div style="margin-bottom:16px">';
    h+='<div style="background:'+(isHoje?'rgba(124,106,247,.2)':'#1a1a24')+';padding:8px 14px;font-size:11px;font-weight:700;color:'+(isHoje?'#fff':'#7c6af7')+';text-transform:uppercase;letter-spacing:1px;border-left:3px solid #7c6af7'+(isHoje?';border-right:3px solid #7c6af7':'')+'">'+(isHoje?'● HOJE — ':'')+lbl+'</div>';
    byD[dt].forEach(e=>{
      const imp_color=e.importance>=3?'#ff4444':'#ff9800';
      const beat=e.signal==='beat', miss=e.signal==='miss';
      const act_color=beat?'#00e676':miss?'#f06292':'#aaa';
      const act_icon=beat?' ▲':miss?' ▼':'';
      const prev_color=e.previous?'#666':'#444';
      h+='<div style="display:grid;grid-template-columns:26px 50px 1fr 36px 75px 75px 75px;gap:5px;align-items:center;padding:7px 14px;border-bottom:1px solid #1a1a1a;font-size:12px'+(isHoje?';background:rgba(124,106,247,.04)':'')+'">';
      h+='<span style="font-size:15px">'+(e.flag||'🌐')+'</span>';
      h+='<span style="color:#555;font-size:11px;font-family:\'IBM Plex Mono\',monospace">'+(e.time||'—')+'</span>';
      h+='<span style="color:#ddd;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+e.event+'">'+e.event+'</span>';
      h+='<span style="color:'+imp_color+';text-align:center;font-size:10px">'+'●'.repeat(Math.min(e.importance,3))+'</span>';
      h+='<span style="color:'+act_color+';text-align:right;font-weight:700;font-family:\'IBM Plex Mono\',monospace">'+(e.actual?e.actual+act_icon:'—')+'</span>';
      h+='<span style="color:#555;text-align:right;font-size:11px;font-family:\'IBM Plex Mono\',monospace">'+(e.forecast||'—')+'</span>';
      h+='<span style="color:'+prev_color+';text-align:right;font-size:11px;font-family:\'IBM Plex Mono\',monospace">'+(e.previous||'—')+'</span>';
      h+='</div>';
    });
    h+='</div>';
  });
  el.innerHTML=h;
}

async function loadCal(){
  const el=document.getElementById('cal-area');
  const st=document.getElementById('cal-st');
  if(!el)return;
  el.innerHTML='<p style="color:#888;padding:20px;text-align:center">Carregando...</p>';
  try{
    const r=await fetch(B+'/calendar',{cache:'no-store'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    const evs=await r.json();
    if(evs.error)throw new Error(evs.error);
    _calEvs=evs;
    renderCal();
  }catch(e){
    el.innerHTML='<p style="color:#f06292;padding:20px">Erro: '+e.message+'</p>';
  }
}

async function main(){
  try{
    if(!_posData)await loadPositions();
    const wt=(p,ms,fb)=>Promise.race([p,new Promise(r=>setTimeout(()=>r(fb),ms))]);
    const[,tv,ft]=await Promise.all([wt(fHL(),12000,null),wt(fTV(),14000,{}),wt(fFut(),14000,null)]);
    const now=new Date().toLocaleTimeString('pt-BR');
    E('last-update','↻ '+now);E('last-update-tbl',now);E('footer-time',now);
    window._lastTV=tv;doMacro(tv,ft);doPos(tv);
    setTimeout(fFund,3000);
    // Yields soberanos em paralelo (endpoint separado, timeout próprio -- não bloqueia o carregamento principal)
    setTimeout(async()=>{try{const y=await fYields();if(y)doYields(y);}catch(e){}},1000);
    setTimeout(async()=>{try{const[bi,bc]=await Promise.all([fBTCI(),fBTCC()]);if(bi)rndBTCI(bi);if(bc)rndBTCC(bc);fFG();}catch(e){}},5000);

    if(_posData&&_posData.ativas){
      const hoje=new Date();
      const byId={}; _posData.ativas.forEach(p=>byId[p.id]=p);
      const diasAte=iso=>Math.max(1,Math.ceil((new Date(iso)-hoje)/864e5));

      // MC simples — PETR4, VALE3, BBAS3 (qualquer 'simples' exceto ROXO34 que usa MCR)
      let delay=6000;
      _posData.ativas.filter(p=>p.tipo_posicao==='simples'&&p.id!=='rx').forEach(p=>{
        setTimeout(()=>MC(p.ticker,p.strike,diasAte(p.vencimento),p.id+'-mc-l',p.id+'-mc-r',p.id+'-mc-i',p.id+'-mc-rt',p.id+'-mc-vs',p.id+'-mc-vols',p.exercicio||'europeia'),delay);
        delay+=6000;
      });

      // MCB barreira — AXIA3 A e B (ou quaisquer outras tipo 'barreira')
      _posData.ativas.filter(p=>p.tipo_posicao==='barreira').forEach(p=>{
        setTimeout(()=>MCB(p.ticker,p.entry,p.kdo,p.kuo,diasAte(p.vencimento),p.id),delay);
        delay+=6000;
      });

      // MCBSimples — retorno_controlado (BSLV39 e outras tipo
      // 'barreira_simples', so KDO sem KUO). Adicionado 26/06/2026:
      // usuario notou que cotacao/Dist.KDO/Situacao ficavam vazios ('—')
      // porque MCB (que preenche esses campos) so era chamado para
      // tipo_posicao==='barreira', nunca para 'barreira_simples'.
      // Reaproveita /montecarlo/posicao_ativa (mesmo endpoint ja testado
      // e confirmado funcionando para o fan chart via botao "Ver
      // evolucao") em vez de criar logica nova -- ele ja calcula
      // preco_atual e prob_sem_barreira corretamente sem exigir KUO.
      _posData.ativas.filter(p=>p.tipo_posicao==='barreira_simples').forEach(p=>{
        setTimeout(()=>MCBSimples(p),delay);
        delay+=6000;
      });

      // MCR — ROXO34 (CORRIGIDO 23/06/2026: antes buscava /indicators
      // primeiro para pegar o preco e so depois chamava /montecarlo --
      // duas chamadas de rede em SERIE, causando demora desproporcional
      // vs as outras posicoes (MC/MCB fazem 1 chamada so). O /montecarlo
      // ja busca o preco via Yahoo internamente quando 'price' nao e
      // enviado (mesmo comportamento usado por MC para PETR4/VALE3/BBAS3)
      // -- entao o fetch previo era redundante. Agora chama direto, em
      // paralelo com as demais, sem esperar nada antes.
      if(byId.rx){
        const dR=diasAte(byId.rx.vencimento);
        setTimeout(()=>MCR('ROXO34.SA',byId.rx.strike,null,dR,null),delay);
        delay+=6000;
      }

      // BBAS3 cotação — via TV ou fallback /indicators
      if(byId.bb||byId.bb2){
        const posicoesBB=[byId.bb,byId.bb2].filter(Boolean);
        const bbTV=tv['BMFBOVESPA:BBAS3'];
        const aplicarBB=(pos,preco,precoAnt)=>{
          const pid=pos.id;
          E(pid+'-p',fR(preco));
          if(precoAnt!=null){Ch(pid+'-c',preco,precoAnt,'r');}else{const ec=document.getElementById(pid+'-c');if(ec)ec.textContent='—';}
          const dist=preco-pos.strike;
          const itm2=document.getElementById(pid+'-itm');
          if(itm2){itm2.textContent=(dist>=0?'+ R$ ':'- R$ ')+Math.abs(dist).toFixed(2)+' '+(dist>=0?'acima (ITM ⚠)':'abaixo (OTM ✅)')+' do strike';itm2.className='sv '+(dist>=0?'itm':'ok');}
        };
        if(bbTV?.p){
          posicoesBB.forEach(pos=>aplicarBB(pos,bbTV.p,bbTV.v||bbTV.p));
        } else {
          fetch(B+'/indicators/BBAS3.SA').then(r2=>r2.json()).then(d2=>{
            if(d2.preco_atual){
              posicoesBB.forEach(pos=>aplicarBB(pos,d2.preco_atual,d2.preco_anterior));
            }
          }).catch(()=>{});
        }
      }
    }

    // Black-Scholes dinâmico — roda uma vez por ciclo, delay para não disputar com MC
    setTimeout(loadBS, 4000);
    // Badge risco — roda após todos os dados async carregarem
    setTimeout(checkBadgeRisco, 6000);
    window._IL=false;
  }catch(e){console.error(e);}
}
// ── BLACK-SCHOLES DINÂMICO ───────────────────────────
// Vol implícita atual (atualizar manualmente quando mudar)
async function loadBS(){
  if(!_posData||!_posData.ativas)return;
  const hoje=new Date();
  // Apenas posicoes tipo 'simples' tem B&S (barreira usa MCB)
  const simples=_posData.ativas.filter(p=>p.tipo_posicao==='simples');
  for(const p of simples){
    try{
      const dias=Math.max(1,Math.ceil((new Date(p.vencimento)-hoje)/864e5));
      const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),12000);
      const r=await fetch(B+'/bs',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        signal:ctrl.signal,
        body:JSON.stringify({ticker:p.ticker,strike:p.strike,t_days:dias,vol_impl:p.vol_impl,tipo:p.tipo||'call'})
      });
      if(!r.ok)continue;
      const d=await r.json();
      if(d.error)continue;
      const pfx=p.id;
      const evol=document.getElementById(pfx+'-bs-vol');
      if(evol){evol.textContent=d.vol_impl_pct.toFixed(1)+'%';}
      const edel=document.getElementById(pfx+'-bs-delta');
      if(edel){edel.textContent=Math.abs(d.delta).toFixed(3);}
      const eprob=document.getElementById(pfx+'-bs-prob');
      if(eprob){
        const prob=d.prob_exercicio_bs;
        const itm=d.itm;
        eprob.textContent=prob.toFixed(2)+'%'+(itm?' ⚠':'');
        eprob.className='sv '+(itm?'itm':prob>30?'warn':'ok');
      }
    }catch(e){}
  }

}

// ══ EM ANÁLISE — Fase 2, listagem/monitoramento de fotos congeladas ══
// Esta aba NUNCA cria foto nova (isso acontece em sessão de chat, ver
// FLUXO_FASE_A_FASE_B.md). Aqui só: listar, ver gráfico condicional,
// e mover status (em_analise -> ativa -> encerrada).
let _analiseData=null;
const _analiseCharts={};

const _STATUS_LABEL={em_analise:'🔍 EM ANÁLISE',ativa:'✅ ATIVA',encerrada:'🗂 ENCERRADA'};
const _STATUS_CLS={em_analise:'enc-warn',ativa:'enc-ok',encerrada:'enc-warn'};
// Adicionado 23/06/2026 -- distinguir "encerrada/rejeitada" (nunca foi
// ativa, descartada na Fase A por probabilidade real baixa, calculada via
// Monte Carlo) de uma encerrada normal (operacao real que foi ativa e
// foi encerrada de fato). Mesmo campo status='encerrada', diferenciado
// pelo campo extra motivo_encerramento.
function statusBadge(a){
  if(a.status==='encerrada'&&a.motivo_encerramento==='rejeitada'){
    return {cls:'enc-rejeitada',txt:'🚫 REJEITADA'};
  }
  return {cls:_STATUS_CLS[a.status]||'enc-warn',txt:_STATUS_LABEL[a.status]||a.status};
}
const _ORIGEM_LABEL={customizada:'Customizada (OpLab)',pronta:'Pronta'};
const _TIPO_LABEL={bidirecional:'Bidirecional',retorno_controlado:'Retorno Controlado',premio:'Prêmio',simples:'Simples'};

async function loadAnalises(){
  const cont=document.getElementById('analise-container');
  if(!cont)return;
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),10000);
    const r=await fetch(B+'/analises',{signal:ctrl.signal,cache:'no-store'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    _analiseData=Array.isArray(data)?data:[];
    renderAnalises();
    checarBarreirasRompidas();
  }catch(e){
    cont.innerHTML='<p style="color:var(--red);padding:20px">⚠ Erro ao carregar analises.json: '+e.message+'</p>';
  }
}

// ADICIONADO 05/08/2026 -- achado real do usuario: MUTC34 (retorno
// controlado) rompeu a barreira KDO no historico real e o app nunca
// avisou, porque o ranking so simula pra FRENTE a partir do preco de
// hoje. Esta funcao roda DEPOIS de renderAnalises() e so ACRESCENTA um
// selo visual nos cards afetados (via DOM, sem alterar tplAnalise nem
// o fluxo de render existente) -- se a chamada falhar por qualquer
// motivo (rede, timeout), o card simplesmente fica como estava antes,
// sem quebrar nada.
async function checarBarreirasRompidas(){
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),10000);
    const r=await fetch(B+'/analises/checar-barreiras',{signal:ctrl.signal,cache:'no-store'});
    if(!r.ok)return;
    const data=await r.json();
    const rompidas=(data.analises||[]).filter(x=>x.rompeu_barreira);
    rompidas.forEach(x=>{
      const seta=document.getElementById('ar-analise-'+x.id);
      const hdr=seta&&seta.closest('.pos-enc-hdr');
      const badgeRow=hdr&&hdr.querySelector('div[style*="display:flex"]');
      if(!badgeRow||badgeRow.querySelector('.barreira-rompida-selo'))return;
      const selo=document.createElement('span');
      selo.className='enc-badge barreira-rompida-selo';
      selo.style.cssText='background:rgba(255,80,80,.15);color:#ff5050;border:1px solid rgba(255,80,80,.4);font-weight:700';
      selo.title=x.detalhe||'Barreira rompida no histórico real';
      selo.textContent='⚠ BARREIRA ROMPIDA';
      badgeRow.appendChild(selo);
    });
  }catch(e){
    // silencioso de proposito -- checagem extra nao pode quebrar a aba
  }
}

// Adicionado 25/06/2026 -- painel de ranking em lote. Roda Monte Carlo de
// TODAS as em_analise de uma vez via GET /analises/ranking, monta tabela
// completa ordenada por score (ordenacao, NUNCA filtro -- todas as linhas
// aparecem, mesmo as com erro de calculo). Usuario decide manualmente
// olhando todas as colunas (prob, retorno mensal, prazo, DY vs CDI).
async function loadRankingAnalises(){
  const area=document.getElementById('ranking-container');
  const btn=document.getElementById('btn-ranking');
  if(!area)return;
  area.innerHTML='Calculando probabilidade de todas as análises em aberto (Monte Carlo em lote, pode levar alguns segundos)...';
  if(btn){btn.disabled=true;btn.style.opacity='.6';}
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),60000);
    const r=await fetch(B+'/analises/ranking',{signal:ctrl.signal,cache:'no-store'});
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    area.innerHTML=tplRanking(d);
  }catch(e){
    area.innerHTML='<p style="color:var(--red)">⚠ Erro ao rodar ranking: '+e.message+'</p>';
  }finally{
    if(btn){btn.disabled=false;btn.style.opacity='1';}
  }
}

function tplRanking(d){
  const linhas=d.ranking||[];
  // ADICIONADO 10/07/2026 -- cache das linhas do ranking por id, para o
  // botao de rejeitar poder enviar o EV/score/prob JA CALCULADOS (sem
  // recalcular nada), habilitando o painel de "deixou na mesa"/"economizou"
  // em Encerradas sem depender de calculo manual.
  window._rankingCache = window._rankingCache || {};
  linhas.forEach(r=>{ if(!r.erro) window._rankingCache[r.id]=r; });
  if(!linhas.length)return '<p style="color:var(--muted)">Nenhuma análise em_analise para ranquear.</p>';
  const TIPO_CURTO={bidirecional:'BI',retorno_controlado:'RC',simples:'SI',premio:'PR'};
  const rows=linhas.map(r=>{
    if(r.erro){
      return `<tr style="opacity:.55">
        <td style="padding:6px 8px">${(r.ticker||'').replace('.SA','')}</td>
        <td colspan="10" style="padding:6px 8px;color:var(--red);font-size:10px">⚠ ${r.erro}</td>
      </tr>`;
    }
    const dy=r.dy_anual_pct!=null?r.dy_anual_pct.toFixed(1)+'%':'—';
    const colchao=r.colchao_dy_vs_cdi_pct!=null
      ? (r.colchao_dy_vs_cdi_pct>0?'<span style="color:var(--green)">+':'<span style="color:var(--red)">')+r.colchao_dy_vs_cdi_pct.toFixed(2)+'%</span>'
      : '—';
    const loteTag=r.lote?`<span style="font-size:9px;color:var(--muted)"> · ${r.lote}</span>`:'';
    const tipoLabel=TIPO_CURTO[r.tipo_estrutura]||'?';
    const tipoFull=_TIPO_LABEL[r.tipo_estrutura]||r.tipo_estrutura;
    const evVal=r.ev_mensal_pct;
    const evCor=evVal>0?'var(--green)':'var(--red)';
    const evTxt=(evVal>0?'+':'')+evVal.toFixed(2)+'%';
    // ADICIONADO 15/07/2026 -- achado pelo Victor investigando SPCX34:
    // quando o historico do papel vem vazio (BDR exotico/pouco liquido),
    // o backend usava 35% de vol generica escondida, sem avisar. Agora
    // mostra um aviso visual claro na linha, pra nao confiar cegamente
    // no EV/score desses casos.
    const volAviso = r.vol_generica_usada
      ? ' <span title="Sem histórico suficiente pra calcular a volatilidade real deste papel — usando 35% genérico. EV/Score aqui podem estar subestimando o risco real." style="color:var(--orange,#f0a020);cursor:help">⚠️</span>'
      : '';
    return `<tr id="rk-row-${r.id}">
      <td style="padding:6px 8px;font-weight:700">${r.ticker.replace('.SA','')}${loteTag}${volAviso}<br><span style="font-weight:400;font-size:10px;color:var(--muted)">${r.nome||''}</span></td>
      <td style="padding:6px 8px;font-size:10px;color:var(--muted)" title="${tipoFull}">${tipoLabel}</td>
      <td style="padding:6px 8px;text-align:right">${r.dias_restantes}d</td>
      <td style="padding:6px 8px;text-align:right">${r.retorno_mensal_pct.toFixed(2)}%</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:${r.prob_meta_pct>=50?'var(--green)':'var(--muted)'}">${r.prob_meta_pct.toFixed(1)}%</td>
      <td style="padding:6px 8px;text-align:right;color:var(--muted)" title="${r.overshoot_medio_pct!=null?`Quando acontece, em média o papel rende ${r.overshoot_medio_pct.toFixed(2)}pp A MAIS do que o retorno travado -- dinheiro que fica na mesa`:'Só disponível para Retorno Controlado'}">${r.prob_overshoot_pct!=null?r.prob_overshoot_pct.toFixed(1)+'%':'—'}</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:${evCor}" title="Retorno médio ponderando TODOS os cenários (sucesso, parcial, rompimento da barreira) — não só prob. de bater a meta">${evTxt}</td>
      <td style="padding:6px 8px;text-align:right">${dy}</td>
      <td style="padding:6px 8px;text-align:right" title="DY mensal − CDI mensal: quanto o dividendo do papel rende a mais (ou menos) que o CDI por mês, se a estrutura quebrar e você ficar com o papel">${colchao}</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:var(--accent)" title="Score = EV mensal × peso de prazo, + bônus se colchão positivo">${r.score.toFixed(3)}</td>
      <td style="padding:6px 8px;text-align:right;white-space:nowrap">
        <button onclick="acaoRanking('${r.id}','ativa')" title="Marcar como Ativa" style="background:var(--green);border:none;color:#06140c;padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:700;margin-right:4px">✓</button>
        <button onclick="acaoRanking('${r.id}','rejeitada')" title="Rejeitar" style="background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:600;margin-right:4px">🚫</button>
        <button onclick="verFotoAnalise('${r.id}')" title="Ver foto do modelo — bandas congeladas no dia da análise, pra ver se está deixando dinheiro na mesa" style="background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:600">📸</button>
      </td>
    </tr>`;
  }).join('');
  return `
  <div style="font-size:10px;color:var(--muted);margin-bottom:8px">CDI atual: ${d.cdi_anual_pct.toFixed(2)}% a.a. · ${d.total_analises} análises em_analise · ordenado por score (EV completo, maior primeiro) — score é só ordenação, nenhuma linha é escondida</div>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="border-bottom:1px solid var(--border);color:var(--muted);text-align:left">
      <th style="padding:6px 8px">Ativo</th>
      <th style="padding:6px 8px" title="BI=Bidirecional, RC=Retorno Controlado, SI=Simples, PR=Prêmio">Tipo</th>
      <th style="padding:6px 8px;text-align:right">Prazo</th>
      <th style="padding:6px 8px;text-align:right" title="Retorno mensal equivalente SE bater a meta (ganho prefixado/teto), ignorando o cenário de romper a barreira. Veja EV mensal para o retorno médio considerando TODOS os cenários.">Ret. mensal <span style="opacity:.6;cursor:help">ⓘ</span></th>
      <th style="padding:6px 8px;text-align:right" title="Probabilidade de NÃO tocar a barreira DAQUI PRA FRENTE (a partir de hoje, com o preço atual) -- é dinâmica, recalcula a cada vez que você roda o ranking. Diferente do número 'desde o início' que aparece no detalhe de cada análise (esse usa o prazo total a partir do preço da foto).">Prob. <span style="opacity:.6;cursor:help">ⓘ</span></th>
      <th style="padding:6px 8px;text-align:right" title="RISCO DE OVERSHOOT -- probabilidade de o papel fechar ACIMA do retorno travado no Retorno Controlado, deixando dinheiro na mesa. Só existe pra Retorno Controlado (Bidirecional não trava um teto único do mesmo jeito).">Overshoot <span style="opacity:.6;cursor:help">ⓘ</span></th>
      <th style="padding:6px 8px;text-align:right" title="EV mensal -- retorno médio ponderando todos os cenários, não só se bateu a meta">EV mensal</th>
      <th style="padding:6px 8px;text-align:right">DY</th>
      <th style="padding:6px 8px;text-align:right" title="DY mensal menos CDI mensal -- colchão se a estrutura quebrar e você ficar com o papel">Colchão</th>
      <th style="padding:6px 8px;text-align:right">Score</th>
      <th style="padding:6px 8px;text-align:right" title="Último rendimento pago, via StatusInvest (carregado automaticamente só quando o filtro tem até 30 itens)">Últ. Prov.</th>
      <th style="padding:6px 8px;text-align:right">Ação</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>
  </div>`;
}

// FOTO DO MODELO EM "EM ANÁLISE" -- backlog #4 (30/06/2026): mesmo conceito
// da Foto do Papel, mas atrelada ao id da análise (bandas congeladas no
// momento da criação, server-side em POST /analises). Mostra se o preço
// real está saindo das bandas que o modelo projetava -- "deixando dinheiro
// na mesa" se rompeu pra cima da banda otimista, por exemplo.
let _analiseFotoChart = null;

async function verFotoAnalise(id){
  const panel = document.getElementById('analise-foto-panel');
  const titulo = document.getElementById('analise-foto-titulo');
  const confEl = document.getElementById('analise-foto-confianca');
  const scoreEl = document.getElementById('analise-foto-score');
  if(!panel) return;
  panel.style.display = 'block';
  panel.scrollIntoView({behavior:'smooth', block:'nearest'});
  titulo.textContent = '📸 Carregando foto do modelo...';
  confEl.innerHTML = ''; scoreEl.innerHTML = '';
  try{
    const r = await fetch(B+'/analises/'+encodeURIComponent(id)+'/foto-bandas',{cache:'no-store'});
    const d = await r.json();
    if(!r.ok || d.error) throw new Error(d.error || ('HTTP '+r.status));
    if(!d.encontrado){
      titulo.textContent = '📸 '+(d.ticker||'Análise');
      confEl.innerHTML = '<em style="color:var(--muted)">Sem bandas congeladas para esta análise (foto anterior à implementação, ou histórico/GARCH indisponível no momento da criação).</em>';
      return;
    }
    titulo.textContent = `📸 ${d.ticker.replace('.SA','')} — foto de ${d.data_foto} · Preço na foto: R$${d.preco_foto.toFixed(2)}`;

    const bc = d.bandas_congeladas;
    const periodo = Math.max(...bc.periodos);
    const bandas = bc.bandas[String(periodo)];
    const T = periodo;
    const labels = Array.from({length: T+1}, (_,i) => `D+${i}`);
    const histReal = (d.historico_real || []).slice(0, T+1);
    const realData = labels.map((_, i) => i < histReal.length ? histReal[i].close : null);

    const dsConfig = [
      { label:'P90 (banda ampla)', data: bandas.p90, borderColor:'transparent', backgroundColor:'rgba(100,120,180,0.10)', fill:'+1', pointRadius:0, borderWidth:0 },
      { label:'P10 (banda ampla)', data: bandas.p10, borderColor:'transparent', backgroundColor:'rgba(100,120,180,0.10)', fill:false, pointRadius:0, borderWidth:0 },
      { label:'P75 (banda central)', data: bandas.p75, borderColor:'transparent', backgroundColor:'rgba(100,180,130,0.18)', fill:'+1', pointRadius:0, borderWidth:0 },
      { label:'P25 (banda central)', data: bandas.p25, borderColor:'transparent', backgroundColor:'rgba(100,180,130,0.18)', fill:false, pointRadius:0, borderWidth:0 },
      { label:'Mediana (p50)', data: bandas.p50, borderColor:'rgba(180,200,255,0.6)', borderWidth:1.5, borderDash:[4,3], pointRadius:0, fill:false },
      { label:'Preço real', data: realData, borderColor:'#f0c040', borderWidth:2.5, pointRadius:0, fill:false, spanGaps:false },
    ];

    const canvas = document.getElementById('analise-foto-canvas');
    if(_analiseFotoChart){ _analiseFotoChart.destroy(); }
    _analiseFotoChart = new Chart(canvas, {
      type: 'line',
      data: { labels, datasets: dsConfig },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode:'index', intersect:false },
        plugins: {
          legend: { display:true, labels:{ color:'#aaa', font:{size:10},
            filter: item => !['P90 (banda ampla)','P10 (banda ampla)','P75 (banda central)','P25 (banda central)'].includes(item.text) } },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: R$${ctx.raw?.toFixed(2)??'—'}` } }
        },
        scales: {
          x: { ticks:{ color:'#666', maxTicksLimit:10, font:{size:9} }, grid:{color:'rgba(255,255,255,0.04)'} },
          y: { ticks:{ color:'#aaa', font:{size:10}, callback: v => 'R$'+v.toFixed(2) }, grid:{color:'rgba(255,255,255,0.06)'} }
        }
      }
    });

    const p10f = bandas.p10[bandas.p10.length-1], p90f = bandas.p90[bandas.p90.length-1];
    const p25f = bandas.p25[bandas.p25.length-1], p75f = bandas.p75[bandas.p75.length-1];
    const p50f = bandas.p50[bandas.p50.length-1];
    confEl.innerHTML =
      `📍 Com <b>80% de confiança</b>, o preço em <b>D+${T}</b> deveria estar entre `+
      `<b style="color:var(--red)">R$${p10f.toFixed(2)}</b> e <b style="color:var(--green)">R$${p90f.toFixed(2)}</b> `+
      `(projeção congelada em ${d.data_foto}). Com <b>50% de confiança</b>, entre `+
      `<b style="color:var(--red)">R$${p25f.toFixed(2)}</b> e <b style="color:var(--green)">R$${p75f.toFixed(2)}</b>. `+
      `Mediana: <b style="color:var(--accent)">R$${p50f.toFixed(2)}</b>.`;

    if(d.score){
      const s = d.score;
      const foraPraCima = histReal.length && histReal[histReal.length-1].close > p90f;
      const alertaMesa = foraPraCima
        ? ' <span style="color:var(--yellow)">⚠ preço real rompeu acima da banda p90 — possível "dinheiro deixado na mesa" se a estrutura tinha teto.</span>'
        : '';
      scoreEl.innerHTML = `<b>Assertividade</b> (${s.dias_observados} dias observados) — `+
        `Dentro banda central (p25–p75): <b style="color:var(--green)">${s.pct_dentro_p25_p75}%</b> do tempo · `+
        `Dentro banda ampla (p10–p90): <b style="color:var(--accent)">${s.pct_dentro_p10_p90}%</b> do tempo${alertaMesa}`;
    } else {
      scoreEl.innerHTML = '<em style="color:var(--muted)">Score disponível após o primeiro pregão desde a foto.</em>';
    }
  } catch(e){
    titulo.textContent = '📸 Erro';
    confEl.innerHTML = '<span style="color:var(--red)">Erro ao carregar foto do modelo: '+e.message+'</span>';
  }
}

function fecharFotoAnalise(){
  const panel = document.getElementById('analise-foto-panel');
  if(panel) panel.style.display = 'none';
  if(_analiseFotoChart){ _analiseFotoChart.destroy(); _analiseFotoChart = null; }
}

// Adicionado 25/06/2026 -- botoes Aprovar/Rejeitar direto na linha do
// ranking (substituem os botoes que existiam nos cards soltos de
// Em Analise -- decisao do usuario: nao faz sentido duplicar a acao em
// dois lugares quando o ranking e o ponto de decisao real).
async function acaoRanking(id,acao){
  const novoStatus = acao==='ativa' ? 'ativa' : 'encerrada';
  const motivo = acao==='rejeitada' ? 'rejeitada' : null;
  const linha=document.getElementById('rk-row-'+id);
  if(motivo){
    const ok=confirm('Confirma REJEITAR esta análise (sai de Em Análise e vai para Encerradas como rejeitada)? Essa ação grava no repositório.');
    if(!ok)return;
  }else{
    const ok=confirm('Confirma MARCAR COMO ATIVA esta análise? Essa ação grava no repositório.');
    if(!ok)return;
  }
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const body={status:novoStatus};
    if(motivo){
      body.motivo_encerramento=motivo;
      // ADICIONADO 10/07/2026 -- envia o EV/score/prob que o ranking JA
      // CALCULOU (cache de tplRanking), sem recalcular nada aqui.
      const rCache=(window._rankingCache||{})[id];
      if(rCache){
        if(rCache.ev_mensal_pct!=null)body.ev_mensal_pct=rCache.ev_mensal_pct;
        if(rCache.score!=null)body.score=rCache.score;
        if(rCache.prob_meta_pct!=null)body.prob_meta_pct=rCache.prob_meta_pct;
        if(rCache.preco_atual!=null)body.preco_atual=rCache.preco_atual;
      }
    }
    const r=await fetch(B+'/analises/'+encodeURIComponent(id)+'/status',{
      method:'PUT',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    if(linha)linha.style.opacity='.4';
    await loadAnalises();
  }catch(e){
    alert('Erro ao aplicar ação: '+e.message);
  }
}

// Adicionado 26/06/2026 -- ranking PROPRIO para FIIs em Em Analise (secao
// separada das estruturadas, mesmo criterio da aba FIIs: P/VP->DY->
// Liquidez->FFO->risco, mas so para os tickers ja em em_analise).
async function loadRankingFiisEmAnalise(){
  const area=document.getElementById('ranking-fiis-container');
  const btn=document.getElementById('btn-ranking-fiis');
  if(!area)return;
  area.innerHTML='Buscando dados atualizados do Fundamentus para os FIIs em análise...';
  if(btn){btn.disabled=true;btn.style.opacity='.6';}
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),30000);
    const r=await fetch(B+'/analises/ranking-fiis',{signal:ctrl.signal,cache:'no-store'});
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    area.innerHTML=tplRankingFii(d);
  }catch(e){
    area.innerHTML='<p style="color:var(--red)">⚠ Erro ao rodar ranking de FIIs: '+e.message+'</p>';
  }finally{
    if(btn){btn.disabled=false;btn.style.opacity='1';}
  }
}

function tplRankingFii(d){
  const linhas=d.ranking||[];
  if(!linhas.length)return '<p style="color:var(--muted)">Nenhum FII em_analise para ranquear.</p>';
  const RISCO_BADGE={
    high_grade:'<span style="background:rgba(76,217,100,.15);color:var(--green);border:1px solid rgba(76,217,100,.3);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">🟢 HG</span>',
    middle_risk:'<span style="background:rgba(255,204,0,.15);color:#ffcc00;border:1px solid rgba(255,204,0,.3);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">🟡 MR</span>',
    high_yield:'<span style="background:rgba(255,107,107,.15);color:var(--red);border:1px solid rgba(255,107,107,.3);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">🔴 HY</span>',
  };
  const aviso=d.nao_encontrados&&d.nao_encontrados.length
    ? `<p style="color:var(--red);font-size:10px;margin-bottom:8px">⚠ Não encontrados no Fundamentus (verifique): ${d.nao_encontrados.join(', ')}</p>` : '';
  // CORRIGIDO 30/06/2026: campos podem vir null para FI-Infra em casos
  // raros (ex: cotacao OU dy_pct ausente, mas nao ambos -- ja que o
  // backend so inclui o candidato se pelo menos um dos dois existir).
  // .toFixed() direto quebrava com "Cannot read properties of null".
  const rows=linhas.map(f=>{
    const badge=RISCO_BADGE[f.nivel_risco]||(f.segmento==='fi-infra'?'<span style="background:rgba(0,180,216,.15);color:#00b4d8;border:1px solid rgba(0,180,216,.4);padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700">FI-INFRA</span>':'');
    const dyCor=(f.dy_pct!=null&&f.dy_pct>=8)?'var(--green)':'var(--muted)';
    let ffoHtml='—';
    if(f.ffo_yield_pct!=null&&f.dy_pct!=null){
      const sustentavel=f.ffo_yield_pct>=f.dy_pct;
      ffoHtml=`<span style="color:${sustentavel?'var(--green)':'var(--red)'}">${f.ffo_yield_pct.toFixed(2)}% ${sustentavel?'▲':'▼'}</span>`;
    }
    return `<tr id="rkfii-row-${f.analise_id}">
      <td style="padding:6px 8px;font-weight:700">${f.ticker} ${badge}<br><span style="font-weight:400;font-size:9px;color:var(--muted)">${f.segmento_fundamentus}</span></td>
      <td style="padding:6px 8px;text-align:right">${f.cotacao!=null?'R$'+f.cotacao.toFixed(2):'—'}</td>
      <td style="padding:6px 8px;text-align:right">${f.p_vp!=null?f.p_vp.toFixed(2):'—'}</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:${dyCor}">${f.dy_pct!=null?f.dy_pct.toFixed(2)+'%':'—'}</td>
      <td style="padding:6px 8px;text-align:right">${ffoHtml}</td>
      <td style="padding:6px 8px;text-align:right">${f.liquidez!=null?'R$'+(f.liquidez/1000).toFixed(0)+'k/dia':'—'}</td>
      <td style="padding:6px 8px;text-align:right;font-weight:700;color:var(--accent)">${f.score!=null?f.score.toFixed(1):'—'}</td>
      <td style="padding:6px 8px;text-align:right;white-space:nowrap">
        <button onclick="acaoRankingFii('${f.analise_id}','${f.ticker}','ativar',${f.cotacao},${f.dy_pct},'${f.segmento}','${f.nivel_risco}')" title="Ativar na Carteira" style="background:var(--green);border:none;color:#06140c;padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:700;margin-right:4px">✓</button>
        <button onclick="acaoRankingFii('${f.analise_id}','${f.ticker}','rejeitar')" title="Rejeitar" style="background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:600">🚫</button>
      </td>
    </tr>`;
  }).join('');
  return `
  ${aviso}
  <div style="font-size:10px;color:var(--muted);margin-bottom:8px">${d.total_encontrados} de ${d.total_em_analise} FIIs em análise · mesmo critério da aba FIIs, ordenado por score</div>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="border-bottom:1px solid var(--border);color:var(--muted);text-align:left">
      <th style="padding:6px 8px">Ticker</th>
      <th style="padding:6px 8px;text-align:right">Cotação</th>
      <th style="padding:6px 8px;text-align:right">P/VP</th>
      <th style="padding:6px 8px;text-align:right">DY</th>
      <th style="padding:6px 8px;text-align:right">FFO</th>
      <th style="padding:6px 8px;text-align:right">Liquidez</th>
      <th style="padding:6px 8px;text-align:right">Score</th>
      <th style="padding:6px 8px;text-align:right" title="Último rendimento pago, via StatusInvest (carregado automaticamente só quando o filtro tem até 30 itens)">Últ. Prov.</th>
      <th style="padding:6px 8px;text-align:right">Ação</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>
  </div>`;
}

// acao: 'ativar' (vai para /carteira-fiis) ou 'rejeitar' (vai para
// Encerradas via mudarStatusAnalise, UNIFICADO com estruturadas -- usuario
// confirmou que pode ficar unificado em Encerradas, sem problema).
async function acaoRankingFii(analiseId,ticker,acao,cotacao,dyPct,segmento,nivelRisco){
  const linha=document.getElementById('rkfii-row-'+analiseId);
  if(acao==='rejeitar'){
    const ok=confirm(`Confirma REJEITAR ${ticker}? Sai de Em Análise e vai para Encerradas.`);
    if(!ok)return;
    try{
      const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
      const r=await fetch(B+'/analises/'+encodeURIComponent(analiseId)+'/status',{
        method:'PUT',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
        body:JSON.stringify({status:'encerrada',motivo_encerramento:'rejeitada'})
      });
      const d=await r.json();
      if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
      if(linha)linha.style.opacity='.4';
    }catch(e){
      alert('Erro ao rejeitar: '+e.message);
    }
    return;
  }
  // ativar
  const btn=linha?linha.querySelector('button'):null;
  if(btn&&btn.disabled)return;
  const ok=confirm(`Ativar ${ticker} na Carteira de FIIs? Preço de referência: R$${cotacao.toFixed(2)} (hoje).`);
  if(!ok)return;
  if(btn){btn.disabled=true;btn.style.opacity='.6';}
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const body={
      ticker: ticker, nome_fundo: ticker, segmento: segmento, nivel_risco: nivelRisco,
      preco_foto: cotacao, dy_anual_pct: dyPct, analise_id: analiseId,
    };
    const r=await fetch(B+'/carteira-fiis',{
      method:'POST',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    if(linha)linha.outerHTML='<tr><td colspan="8" style="padding:6px 8px;text-align:center;color:var(--green);font-size:11px;font-weight:700">✓ '+ticker+' migrado para Carteira</td></tr>';
  }catch(e){
    alert('Erro ao ativar: '+e.message);
    if(btn){btn.disabled=false;btn.style.opacity='1';}
  }
}

function renderAnalises(){
  const cont=document.getElementById('analise-container');
  if(!cont||!_analiseData)return;
  const badge=document.getElementById('analise-badge');
  const emAberto=_analiseData.filter(a=>a.status==='em_analise');
  if(badge)badge.style.display=emAberto.length?'inline-block':'none';
  if(badge)badge.textContent=emAberto.length||'';

  // CORRIGIDO 23/06/2026: usuario esclareceu que a aba Em Analise deve
  // mostrar SO o que esta em_analise ou ativa -- uma vez que vira
  // 'encerrada' (rejeitada ou encerramento real), ela MIGRA por completo
  // para a aba Encerradas (ver renderAnalisesEncerradas), nao fica mais
  // visivel aqui.
  //
  // CORRIGIDO 30/06/2026: FIIs (tipo_estrutura='fii') sao EXCLUIDOS daqui
  // -- usuario pediu separacao visual completa, sem misturar com
  // estruturadas. FIIs em_analise agora aparecem SO na secao dedicada
  // "FIIs em Analise" mais abaixo (tabela propria com acao direto na
  // linha, ver loadRankingFiisEmAnalise/tplRankingFii) -- nao tinham
  // ranking Monte Carlo mesmo, entao nunca apareciam no painel de cima;
  // o card solto aqui era so duplicata confusa do que ja existe na
  // tabela de baixo.
  const ativas=_analiseData.filter(a=>(a.status==='em_analise'||a.status==='ativa')&&a.tipo_estrutura!=='fii');

  if(!ativas.length){
    cont.innerHTML='<p style="color:var(--muted);padding:20px;text-align:center">Nenhuma estrutura em andamento.<br><span style="font-size:11px">Fotos são criadas em sessão de chat (Fase A → Fase B) e aparecem aqui automaticamente. FIIs aparecem na seção própria abaixo.</span></p>';
    return;
  }

  // Ordena: em_analise primeiro, depois ativa; dentro de cada grupo, mais recente primeiro
  const ordem={em_analise:0,ativa:1};
  const lista=[...ativas].sort((a,b)=>{
    const oa=ordem[a.status]??9,ob=ordem[b.status]??9;
    if(oa!==ob)return oa-ob;
    return (b.data_foto||'').localeCompare(a.data_foto||'');
  });

  cont.innerHTML=lista.map(a=>tplAnalise(a)).join('');
}

// Adicionado 23/06/2026 -- secao separada na aba Encerradas para
// historico de analises (rejeitadas + encerradas reais com sucesso/
// fracasso), distinta da secao de Posicoes reais (positions.json) que
// ja existia. Dashboard no mesmo estilo visual de calcDashboardEncerradas.
// CORRIGIDO 23/06/2026 (2a correcao): usuario simplificou -- nao precisa
// separar por "fase", e UM historico unico com funil simples:
// Total (todas as analises que ja existiram) -> % Aprovadas/Ativadas (do
// total, quantas chegaram a ser ativas -- inclui as que ainda estao
// ativas agora E as que ja foram encerradas) -> % Rejeitadas (do total,
// nunca chegaram a ser ativas) -> Taxa de Sucesso (medida SO entre as
// que foram ativas e ja encerraram, nao entre o total e nao incluindo
// rejeitadas, que nunca foram testadas de verdade).
async function loadAnalisesEncerradas(){
  const cont=document.getElementById('enc-analises-container');
  if(!cont)return;
  try{
    // ADICIONADO 13/08/2026 -- pedido do Victor: taxa de sucesso HIPOTETICA
    // (rejeitadas ja vencidas) ao lado da oficial (capital real). Busca
    // separada, tratada como best-effort -- se falhar, o resto do painel
    // continua funcionando normal, so essa linha nova fica ausente.
    const [rA,rS,rH]=await Promise.all([
      fetch(B+'/analises',{cache:'no-store'}),
      fetch(B+'/analises/stats',{cache:'no-store'}).catch(()=>null),
      fetch(B+'/analises/tracking-hipotetico',{cache:'no-store'}).catch(()=>null),
    ]);
    const dataA=rA.ok?await rA.json():[];
    const stats=(rS&&rS.ok)?await rS.json():{total_rejeitadas:0,total_migradas:0};
    const hipotetico=(rH&&rH.ok)?await rH.json():null;
    const hipItensPorId={};
    (hipotetico?.itens||[]).forEach(it=>{hipItensPorId[it.id]=it;});
    const todasVisiveis=Array.isArray(dataA)?dataA:[];
    const totalRejeitadasPermanente=stats.total_rejeitadas||0;
    // CORRIGIDO 13/08/2026 -- bug achado pelo Victor: o total caia toda
    // vez que uma analise migrava pra Ativa, porque o registro e REMOVIDO
    // de analises.json na migracao (by design) e so existia contador
    // permanente para rejeitadas, nao para migradas -- entao o total
    // "esquecia" quem tinha migrado. Agora soma tambem
    // stats.total_migradas (contador permanente que nunca diminui, ver
    // _incrementar_contador_migradas no backend).
    const totalMigradasPermanente=stats.total_migradas||0;
    // Total = todas as visiveis + rejeitadas ja limpas da lista (>30 dias)
    // que so existem no contador permanente + TODAS as migradas (essas
    // saem de analises.json imediatamente na migracao, entao 100% delas
    // dependem do contador permanente, nao so o excedente como as
    // rejeitadas)
    const rejeitadasVisiveis=todasVisiveis.filter(a=>a.motivo_encerramento==='rejeitada').length;
    const total=todasVisiveis.length+Math.max(0,totalRejeitadasPermanente-rejeitadasVisiveis)+totalMigradasPermanente;

    const jaFoiAtiva=todasVisiveis.filter(a=>a.status==='ativa'||(a.status==='encerrada'&&a.resultado));
    const totalJaFoiAtivaComMigradas=jaFoiAtiva.length+totalMigradasPermanente;
    const encerradasComResultado=todasVisiveis.filter(a=>a.status==='encerrada'&&a.resultado);
    const sucessos=encerradasComResultado.filter(a=>a.resultado==='sucesso').length;
    const taxaSucesso=encerradasComResultado.length?Math.round(sucessos/encerradasComResultado.length*100):null;
    const pctAprovadas=total?Math.round(totalJaFoiAtivaComMigradas/total*100):0;
    const pctRejeitadas=total?Math.round(totalRejeitadasPermanente/total*100):0;

    // ADICIONADO 15/07/2026 -- ate aqui a lista nao tinha ORDENACAO
    // nenhuma, so a ordem crua do array (que reflete quando cada
    // registro foi CRIADO, nao quando foi encerrado/rejeitado). Achado
    // pelo Victor: uma analise rejeitada HOJE aparecia acima de outras
    // rejeitadas dias antes, so porque tinha sido criada mais cedo no
    // arquivo. Ordena agora por data_rejeicao (ou data_encerramento como
    // fallback, ou data_foto se nenhuma das duas existir), MAIS RECENTE
    // PRIMEIRO -- assim a ordem na tela corresponde a ordem real das
    // decisoes, nao a ordem de criacao dos registros.
    const dataOrdenacao = a => a.data_rejeicao || a.data_encerramento || a.data_foto || '';
    const listaCards=todasVisiveis.filter(a=>a.status==='encerrada')
      .sort((a,b)=> dataOrdenacao(b).localeCompare(dataOrdenacao(a)));

    let dashboard=`
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px">
      <div class="card g">
        <div class="cl">Total Analisado</div>
        <div class="cp">${total}</div>
        <div class="cc" style="color:var(--muted)">histórico completo</div>
      </div>
      <div class="card g">
        <div class="cl">Aprovadas/Ativadas</div>
        <div class="cp">${pctAprovadas}%</div>
        <div class="cc" style="color:var(--green)">${totalJaFoiAtivaComMigradas} de ${total}</div>
      </div>
      <div class="card b">
        <div class="cl">Rejeitadas</div>
        <div class="cp">${pctRejeitadas}%</div>
        <div class="cc" style="color:#ff6b6b">🚫 ${totalRejeitadasPermanente} de ${total}</div>
      </div>
      <div class="card b">
        <div class="cl">Taxa de Sucesso</div>
        <div class="cp">${taxaSucesso!=null?taxaSucesso+'%':'—'}</div>
        <div class="cc" style="color:var(--accent)">${sucessos} de ${encerradasComResultado.length} (só ativadas)</div>
      </div>
    </div>`;

    // ADICIONADO 13/08/2026 -- linha separada (nao dentro do grid de 4,
    // pra nao competir visualmente com o card de capital real acima) com
    // a taxa HIPOTETICA -- sempre mostra o N junto, nunca so a
    // porcentagem sozinha (amostra ainda pequena, pedido explicito do
    // Victor pra nao induzir a erro). So aparece se a busca funcionou.
    if(hipotetico && hipotetico.total_avaliadas>0){
      dashboard+=`
      <div class="card" style="margin-bottom:20px;border-left:2px solid var(--accent)">
        <div class="cl" style="display:flex;align-items:center;gap:6px">
          🧪 Taxa de sucesso HIPOTÉTICA (rejeitadas já vencidas)
          <span style="font-size:9px;color:var(--muted);font-weight:400">nunca envolveu capital real -- so mede calibração do modelo</span>
        </div>
        <div class="cp">${hipotetico.taxa_acerto_binario_pct}% <span style="font-size:12px;font-weight:400;color:var(--muted)">(${hipotetico.itens.filter(i=>!i.erro&&i.acertou_previsao).length} de ${hipotetico.total_avaliadas})</span></div>
      </div>`;
    }

    if(!listaCards.length){
      cont.innerHTML=dashboard+'<p style="color:var(--muted);padding:20px;text-align:center">Nenhuma análise encerrada/rejeitada visível ainda.</p>';
      return;
    }

    const cards=listaCards.map(a=>tplAnaliseEncerrada(a)).join('');
    cont.innerHTML=dashboard+'<div id="enc-somatorio-panel" style="margin-bottom:16px"></div>'+cards;
    calcularSomatorioEncerradas(listaCards, hipItensPorId);
  }catch(e){
    cont.innerHTML='<p style="color:var(--red);padding:20px">⚠ Erro ao carregar histórico de análises: '+e.message+'</p>';
  }
}

// Adicionado 05/07/2026 (pedido do usuario) -- painel "quanto ficou na
// mesa": para cada analise ENCERRADA com resultado + preco_encerramento
// registrado, reaproveita /montecarlo/condicional (mesmo endpoint do
// botao "Ver probabilidade atualizada" em Em Analise) mas ancorado na
// DATA/PRECO DO ENCERRAMENTO em vez de hoje -- calcula, com esse ponto de
// referencia, o retorno medio TEORICO esperado da estrutura (ja calculado
// pelo endpoint a partir da foto original + vol atual como proxy) e
// compara com o retorno REALIZADO DE PRECO ate o fechamento (proxy simples
// -- nao reaplica o payoff exato da estrutura, ver nota abaixo).
//
// LIMITACAO ASSUMIDA E ANUNCIADA NA UI: "realizado" aqui e o retorno bruto
// de preco (preco_encerramento/preco_foto - 1), nao o payoff exato da
// estrutura (que dependeria de reimplementar kdo/kuo/alavancagem/teto no
// front, duplicando logica do backend) -- serve como indicador direcional
// de "ficou dinheiro na mesa ou nao", nao como valor financeiro exato.
//
// Chamadas SEQUENCIAIS com atraso (nao paralelas) -- mesmo cuidado de
// concorrencia do Render ja documentado no backlog (1 worker so).
// Adicionado 05/07/2026 -- helper simples de arredondamento, usado pelo
// calculo de aproveitamento em Encerradas.
function round2(n){ return Math.round(n*100)/100; }

async function calcularSomatorioEncerradas(lista, hipItensPorId){
  hipItensPorId = hipItensPorId || {};
  const qualificam=lista.filter(a=>
    a.status==='encerrada' && a.resultado && a.preco_encerramento!=null &&
    a.preco_foto!=null && a.data_encerramento && a.data_foto);
  // ADICIONADO 10/07/2026 -- itens REJEITADOS (nunca ativados) com EV
  // capturado no momento da rejeicao. Diferente do fluxo sucesso/fracasso:
  // nao precisa de chamada de rede (o EV ja foi calculado pelo ranking e
  // enviado no momento do clique em "Rejeitar") -- processamento e
  // instantaneo. gap = ev_mensal_na_rejeicao diretamente: EV positivo =
  // "deixou na mesa" (desistiu de uma expectativa boa); EV negativo =
  // "economizou" (evitou uma expectativa ruim) -- mesma convencao de sinal
  // e cores ja usada no restante do painel.
  const qualificamRejeitadas=lista.filter(a=>
    a.status==='encerrada' && a.motivo_encerramento==='rejeitada' &&
    a.ev_mensal_na_rejeicao!=null && a.preco_foto!=null);
  const painel=document.getElementById('enc-somatorio-panel');
  if(!painel)return;
  if(!qualificam.length && !qualificamRejeitadas.length){
    painel.innerHTML='<p style="font-size:11px;color:var(--muted)">Nenhuma análise encerrada com dado suficiente ainda para calcular aproveitamento (só disponível para encerramentos/rejeições a partir de 05-10/07/2026).</p>';
    return;
  }
  painel.innerHTML='<div class="card" style="margin-bottom:10px"><div class="cl">Calculando aproveitamento (quanto ficou na mesa)...</div></div>';
  let somaGap=0, somaGapRs=0, contabilizados=0;
  window._gapCache = window._gapCache || {};

  // Processa rejeitadas primeiro (instantaneo, sem rede)
  for(const a of qualificamRejeitadas){
    const gap=round2(a.ev_mensal_na_rejeicao);
    const gapRs=round2(gap*a.preco_foto);
    somaGap+=gap; somaGapRs+=gapRs; contabilizados++;
    const gapEl=document.getElementById('enc-gap-'+a.id);
    if(gapEl){
      const corGap=gap>0.05?'var(--accent)':(gap<-0.05?'var(--green)':'var(--muted)');
      const txtGap=gap>0.05?('deixou ~R$ '+gapRs.toFixed(2)+' na mesa ao rejeitar (lote de 100)'):(gap<-0.05?('economizou ~R$ '+Math.abs(gapRs).toFixed(2)+' ao rejeitar, evitou EV negativo (lote de 100)'):'EV próximo de zero, decisão neutra');
      let html='<span style="color:'+corGap+'">EV mensal na rejeição: '+(a.ev_mensal_na_rejeicao>=0?'+':'')+a.ev_mensal_na_rejeicao.toFixed(2)+'% · '+txtGap+'</span>';
      // ADICIONADO 13/08/2026 -- pedido do Victor: "historia completa" --
      // alem do EV PROJETADO acima (calculado no momento da rejeicao, via
      // Monte Carlo, nunca muda depois), mostrar tambem o EV REALIZADO
      // (o que aconteceu de verdade, usando o preco real ate o
      // vencimento -- so aparece se a estrutura ja venceu, ver
      // /analises/tracking-hipotetico). Mesma convencao de R$/lote de
      // 100 do calculo acima, pra ficar comparavel lado a lado.
      const hip = hipItensPorId[a.id];
      if(hip && !hip.erro){
        const ganhoReal = round2(hip.ganho_pct_hipotetico);
        const ganhoRealRs = round2(ganhoReal*a.preco_foto);
        const corReal = hip.resultado_hipotetico==='sucesso'?'var(--green)':'#ff6b6b';
        const emoji = hip.resultado_hipotetico==='sucesso'?'✅':'❌';
        html+='<br><span style="color:'+corReal+'">EV realizado (já venceu): '+emoji+' '+hip.resultado_hipotetico+' · '+(ganhoReal>=0?'+':'')+ganhoReal.toFixed(2)+'% · ~R$ '+ganhoRealRs.toFixed(2)+' (lote de 100)</span>';
      }
      gapEl.innerHTML=html;
    }
  }
  for(const a of qualificam){
    // Cache de sessao: preco_encerramento/data_encerramento sao imutaveis
    // uma vez fixados, entao o resultado nunca muda -- reabrir a aba na
    // mesma sessao do navegador nao precisa rebuscar rede (evita sobrecarga
    // no worker unico do Render, mesmo problema de concorrencia documentado
    // no backlog geral).
    if(window._gapCache[a.id]){
      const c=window._gapCache[a.id];
      const gapEl=document.getElementById('enc-gap-'+a.id);
      if(gapEl)gapEl.innerHTML=c.html;
      if(c.aplicavel){somaGap+=c.gap; somaGapRs+=c.gapRs; contabilizados++;}
      continue;
    }
    try{
      const body={ticker:a.ticker,preco_foto:a.preco_foto,data_foto:a.data_foto,prazo_dias:a.prazo_dias,
        data_referencia:a.data_encerramento,preco_referencia:a.preco_encerramento};
      if(a.k_call!=null)body.k_call=a.k_call;
      if(a.k_put!=null)body.k_put=a.k_put;
      if(a.kdo!=null)body.kdo=a.kdo;
      if(a.kuo!=null)body.kuo=a.kuo;
      if(a.alavancagem!=null)body.alavancagem=a.alavancagem;
      if(a.teto_retorno_pct!=null)body.teto_retorno_pct=a.teto_retorno_pct;
      if(a.ganho_prefixado_pct!=null)body.ganho_prefixado_pct=a.ganho_prefixado_pct;
      if(a.exercicio!=null)body.exercicio=a.exercicio;
      // ADICIONADO 15/07/2026 -- faltava repassar esses 2 campos novos
      // (mecanica de queda das estruturas Protecao Total/Parcial) --
      // sem isso, o backend sempre usava o default 'positiva'/'protegida'
      // (mecanica da Bidirecional comum) pra QUALQUER estrutura, mesmo
      // as que tem mecanica diferente. So achado porque o Victor reparou
      // que a Protecao Parcial mostrava 0% de chance de perda, quando
      // deveria mostrar perda real (mecanica 'perda_integral').
      if(a.downside_antes!=null)body.downside_antes=a.downside_antes;
      if(a.downside_apos!=null)body.downside_apos=a.downside_apos;
      const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),18000);
      const r=await fetch(B+'/montecarlo/condicional',{
        method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
        body:JSON.stringify(body)
      });
      const d=await r.json();
      const gapEl=document.getElementById('enc-gap-'+a.id);
      if(!r.ok||d.error||d.retorno_medio_pct==null){
        const htmlNA='<span style="color:var(--muted)">Aproveitamento: não aplicável a este tipo de estrutura.</span>';
        if(gapEl)gapEl.innerHTML=htmlNA;
        window._gapCache[a.id]={html:htmlNA,aplicavel:false};
      }else{
        const realizadoPct=round2((a.preco_encerramento/a.preco_foto-1)*100);
        const esperadoPct=d.retorno_medio_pct;
        const gap=round2(esperadoPct-realizadoPct);
        // LOTE PADRAO 100 ativos (pedido do usuario 05/07/2026) -- converte
        // pp em R$ usando sempre 100 unidades como base, seja ETF, acao ou
        // FII, para comparabilidade entre ativos de precos diferentes.
        // gap_rs = (gap_pct/100) * preco_foto * 100 unidades = gap_pct * preco_foto
        const gapRs=round2(gap*a.preco_foto);
        somaGap+=gap; somaGapRs+=gapRs; contabilizados++;
        const corGap=gap>0.05?'var(--accent)':(gap<-0.05?'var(--green)':'var(--muted)');
        const txtGap=gap>0.05?('deixou ~R$ '+gapRs.toFixed(2)+' na mesa (lote de 100)'):(gap<-0.05?('superou o esperado em ~R$ '+Math.abs(gapRs).toFixed(2)+' (lote de 100)'):'bateu bem próximo do esperado');
        const htmlOk='<span style="color:'+corGap+'">Esperado (teórico): '+esperadoPct.toFixed(2)+'% · Realizado (preço): '+realizadoPct.toFixed(2)+'% · '+txtGap+'</span>';
        if(gapEl)gapEl.innerHTML=htmlOk;
        window._gapCache[a.id]={html:htmlOk,aplicavel:true,gap:gap,gapRs:gapRs};
      }
    }catch(e){
      const gapEl=document.getElementById('enc-gap-'+a.id);
      if(gapEl)gapEl.innerHTML='<span style="color:var(--muted)">Não foi possível calcular (erro de rede).</span>';
    }
    await new Promise(res=>setTimeout(res,400));
  }
  if(contabilizados>0){
    const corSoma=somaGap>0?'var(--accent)':'var(--green)';
    const txtSoma=somaGap>0?'ficou em média na mesa (esperado acima do realizado)':'superou o esperado em média';
    painel.innerHTML='<div class="card" style="margin-bottom:10px">'+
      '<div class="cl">Somatório de aproveitamento ('+contabilizados+' análises com dado, lote de 100 ativos)</div>'+
      '<div class="cp" style="color:'+corSoma+'">'+(somaGapRs>0?'+':'')+'R$ '+somaGapRs.toFixed(2)+'</div>'+
      '<div class="cc" style="color:var(--muted)">'+(somaGap>0?'+':'')+somaGap.toFixed(2)+' pp · '+txtSoma+' · comparação bruta de retorno de preço, não payoff exato da estrutura</div>'+
    '</div>';
  }else{
    painel.innerHTML='<p style="font-size:11px;color:var(--muted)">Nenhuma das análises encerradas com preço registrado se aplica a este cálculo (tipo de estrutura sem payoff simulável).</p>';
  }
}

function tplAnaliseEncerrada(a){
  const isRejeitada=a.motivo_encerramento==='rejeitada';
  const badgeCls=isRejeitada?'enc-rejeitada':(a.resultado==='sucesso'?'enc-ok':'enc-warn');
  const badgeTxt=isRejeitada?'🚫 REJEITADA':(a.resultado==='sucesso'?'✅ SUCESSO':a.resultado==='fracasso'?'⚠ FRACASSO':'🗂 ENCERRADA');
  const dataRef=isRejeitada?fmtDataOrNull(a.data_rejeicao):fmtDataOrNull(a.data_encerramento);
  const sub=[_TIPO_LABEL[a.tipo_estrutura]||a.tipo_estrutura,dataRef?'Encerrada '+dataRef:'Encerrada'].join(' · ');
  let rows=`<div class="sr"><span class="sl">Tipo</span><span class="sv">${_TIPO_LABEL[a.tipo_estrutura]||a.tipo_estrutura}</span></div>`;
  if(a.preco_foto!=null)rows+=`<div class="sr"><span class="sl">Preço na foto</span><span class="sv">R$ ${Number(a.preco_foto).toFixed(2).replace('.',',')}</span></div>`;
  if(a.observacao)rows+=`<div class="sr"><span class="sl">Observação</span><span class="sv" style="color:var(--muted);white-space:pre-wrap">${a.observacao.slice(0,400)}</span></div>`;
  const qualificaGap=(a.status==='encerrada'&&a.resultado&&a.preco_encerramento!=null&&a.preco_foto!=null&&a.data_encerramento&&a.data_foto)
    || (a.status==='encerrada'&&a.motivo_encerramento==='rejeitada'&&a.ev_mensal_na_rejeicao!=null&&a.preco_foto!=null);
  const gapHtml=qualificaGap?`<div id="enc-gap-${a.id}" style="font-size:11px;margin-top:8px;color:var(--muted)">Calculando aproveitamento...</div>`:'';
  return `
  <div class="pos-enc" style="margin-top:10px">
    <div class="pos-enc-hdr" onclick="togPos('an-${a.id}')">
      <div style="display:flex;align-items:center;gap:12px">
        <div>
          <div class="pos-acc-tk" style="color:var(--muted);font-size:18px">${a.ticker}</div>
          <div class="pos-acc-sub">${sub}</div>
        </div>
        <span class="enc-badge ${badgeCls}">${badgeTxt}</span>
      </div>
      <span id="ar-an-${a.id}" style="color:var(--muted)">▼</span>
    </div>
    <div class="pos-acc-body" id="body-an-${a.id}">
      <div class="sb">${rows}</div>
      ${gapHtml}
    </div>
  </div>`;
}

function tplAnalise(a){
  const id=a.id;
  const dataFotoFmt=fmtDataOrNull(a.data_foto)||a.data_foto;
  const subParts=[_TIPO_LABEL[a.tipo_estrutura]||a.tipo_estrutura,_ORIGEM_LABEL[a.origem]||a.origem];
  subParts.push('Foto: '+dataFotoFmt+' · '+a.prazo_dias+'d');
  const sub=subParts.join(' · ');
  const badge=statusBadge(a);
  const badgeCls=badge.cls;
  const badgeTxt=badge.txt;

  let rows='';
  rows+='<div class="sr"><span class="sl">Preço na foto</span><span class="sv">'+fR(a.preco_foto)+'</span></div>';
  rows+='<div class="sr"><span class="sl">Prazo original</span><span class="sv">'+a.prazo_dias+' dias</span></div>';
  if(a.k_call!=null)rows+='<div class="sr"><span class="sl">Strike Call</span><span class="sv">'+fR(a.k_call)+'</span></div>';
  if(a.k_put!=null)rows+='<div class="sr"><span class="sl">Strike Put</span><span class="sv">'+fR(a.k_put)+'</span></div>';
  if(a.kdo!=null)rows+='<div class="sr"><span class="sl">Barreira baixa (KDO)</span><span class="sv">'+fR(a.kdo)+'</span></div>';
  if(a.kuo!=null)rows+='<div class="sr"><span class="sl">Barreira alta (KUO)</span><span class="sv">'+fR(a.kuo)+'</span></div>';
  if(a.premio!=null)rows+='<div class="sr"><span class="sl">Prêmio</span><span class="sv">'+fR(a.premio)+'</span></div>';

  const acoes=tplAnaliseAcoes(a);
  const liveCls=a.status!=='encerrada'?' is-live':'';

  return `
  <div class="pos-enc${liveCls}" style="margin-top:10px">
    <div class="pos-enc-hdr" onclick="togPos('analise-${id}')">
      <div style="display:flex;align-items:center;gap:12px">
        <div>
          <div class="pos-acc-tk" style="color:var(--muted);font-size:18px">${a.ticker.replace('.SA','')}</div>
          <div class="pos-acc-sub">${sub}</div>
        </div>
        <span class="enc-badge ${badgeCls}">${badgeTxt}</span>
        ${a.backtest?'<span class="enc-badge" style="background:rgba(124,106,247,.15);color:var(--accent);border:1px solid rgba(124,106,247,.3)">🧪 BACKTEST</span>':''}
        ${a.lote?'<span class="enc-badge" style="background:rgba(255,255,255,.06);color:var(--muted);border:1px solid var(--border)" title="Lote de origem">📦 '+a.lote+'</span>':''}
      </div>
      <span id="ar-analise-${id}" style="color:var(--muted)">▼</span>
    </div>
    <div class="pos-acc-body" id="body-analise-${id}">
      <div class="sb">${rows}</div>
      <div id="analise-cond-wrap-${id}" style="margin-top:14px">
        <button onclick="loadCondicional('${id}')" id="analise-cond-btn-${id}" style="background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:6px 14px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600;letter-spacing:.3px;width:100%">📊 Ver probabilidade atualizada</button>
        <div id="analise-cond-area-${id}" style="display:none;margin-top:10px"></div>
      </div>
      ${acoes}
    </div>
  </div>`;
}

function tplAnaliseAcoes(a){
  // CORRIGIDO 25/06/2026: botoes Marcar como Ativa / Rejeitar migraram para
  // a tabela de ranking (usuario decidiu que faz mais sentido decidir
  // direto na linha ranqueada, em vez de duplicar a acao no card solto).
  // O card aqui so mantem "Encerrar operacao" para quem ja esta 'ativa' --
  // isso nao faz parte do fluxo de ranking (ranking e so para em_analise).
  //
  // EXCECAO (25/06/2026): FIIs (tipo_estrutura='fii') NUNCA aparecem no
  // ranking de probabilidades -- ranking roda Monte Carlo, que nao se
  // aplica a FII (sem barreira/meta/vencimento). Por isso o card de FII em
  // em_analise mantem seu PROPRIO botao de acao aqui, indo direto para a
  // Carteira (endpoint POST /carteira-fiis), em vez de para 'ativa' dentro
  // de analises.json (FIIs ficam em arquivo proprio, carteira_fiis.json).
  if(a.tipo_estrutura==='fii'&&a.status==='em_analise'){
    return `
    <div style="display:flex;gap:8px;margin-top:14px" id="fii-acoes-${a.id}">
      <button id="btn-ativar-${a.id}" onclick="ativarFiiNaCarteira('${a.id}')" style="flex:1;background:var(--green);border:none;color:#06140c;padding:8px 10px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:700">✓ Ativar na Carteira</button>
      <button onclick="mudarStatusAnalise('${a.id}','encerrada','rejeitada')" style="flex:1;background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:8px 10px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600">🚫 Rejeitar</button>
    </div>`;
  }
  if(a.status==='ativa'){
    return `
    <div style="display:flex;gap:8px;margin-top:14px">
      <button onclick="encerrarOperacaoAtiva('${a.id}')" style="flex:1;background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:8px 10px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600">🗂 Encerrar operação</button>
    </div>`;
  }
  return '';
}

// Adicionado 25/06/2026 -- ativa um FII que esta em Em Analise para a
// Carteira de fato (POST /carteira-fiis), e remove de analises.json apos
// sucesso (passando analise_id no body -- backend faz a limpeza).
async function ativarFiiNaCarteira(analiseId){
  const a=_analiseData.find(x=>x.id===analiseId);
  if(!a)return;
  const btn=document.getElementById('btn-ativar-'+analiseId);
  // CORRIGIDO 26/06/2026 -- usuario relatou erro HTTP ao clicar em mais
  // de um FII em sequencia rapida, e o card nao desaparecia imediatamente
  // apos o clique (dando a impressao de "nao fez nada", levando a
  // cliques duplicados). Causa real: sem protecao contra duplo-clique, 2
  // requisicoes concorrentes para o MESMO analise_id podiam disparar --
  // a 2a falha porque o registro ja foi removido de analises.json pela
  // 1a (nao ha mais o que remover de novo).
  if(btn&&btn.disabled)return;  // ja esta processando, ignora clique extra
  const ok=confirm(`Ativar ${a.ticker.replace('.SA','')} na Carteira de FIIs? Preço de referência: R$${a.preco_foto.toFixed(2)} (hoje). Essa ação grava no repositório.`);
  if(!ok)return;
  if(btn){btn.disabled=true;btn.textContent='Ativando...';btn.style.opacity='.6';}
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const body={
      ticker: a.ticker.replace('.SA',''),
      nome_fundo: a.nome,
      segmento: a.segmento,
      nivel_risco: a.nivel_risco,
      preco_foto: a.preco_foto,
      dy_anual_pct: a.dy_anual_pct,
      analise_id: a.id,
    };
    const r=await fetch(B+'/carteira-fiis',{
      method:'POST',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    // Remove o card da tela IMEDIATAMENTE (sem esperar o full reload de
    // loadAnalises, que pode demorar/falhar por cache do GitHub raw) --
    // feedback visual instantaneo de que a acao funcionou.
    const card=btn?.closest('[id^="analise-card-"]')||btn?.closest('.analise-card');
    const acoesDiv=document.getElementById('fii-acoes-'+analiseId);
    if(acoesDiv)acoesDiv.outerHTML='<div style="margin-top:14px;text-align:center;color:var(--green);font-size:11px;font-weight:700">✓ Migrado para Carteira</div>';
    _analiseData=_analiseData.filter(x=>x.id!==analiseId);  // remove da lista em memoria tambem
    setTimeout(()=>loadAnalises(),1500);  // confirma com o servidor um pouco depois, sem pressa
  }catch(e){
    // Erro mais claro quando a causa provavel e duplo-clique/duplicata
    const msgAmigavel = e.message.includes('nao encontrada')||e.message.includes('404')
      ? 'Esta análise já foi processada (provavelmente por um clique anterior). Atualize a lista.'
      : e.message;
    alert('Erro ao ativar na carteira: '+msgAmigavel);
    if(btn){btn.disabled=false;btn.textContent='✓ Ativar na Carteira';btn.style.opacity='1';}
  }
}

// Adicionado 23/06/2026 -- ao encerrar uma analise que JA FOI ativa (nao
// uma rejeitada, que nunca chegou a operar), pergunta sucesso/fracasso
// para alimentar a taxa de sucesso do dashboard de funil. Fluxo em 2
// passos para nao confundir 'cancelar a acao' com 'foi fracasso'.
async function encerrarOperacaoAtiva(id){
  const prosseguir=confirm('Confirma ENCERRAR esta operação? Essa ação grava no repositório.');
  if(!prosseguir)return;
  const deuCerto=confirm('A operação foi um SUCESSO?\n\nClique OK para SIM (sucesso) ou Cancelar para NÃO (fracasso).');
  await mudarStatusAnalise(id,'encerrada',null,deuCerto?'sucesso':'fracasso');
}

// CORRIGIDO 23/06/2026: usuario esclareceu que o botao 'Encerrar sem
// executar' (renomeado para 'Rejeitar' acima) JA ERA o mecanismo certo
// para marcar uma analise como rejeitada -- nao precisava criar logica
// separada por fora. Agora mudarStatusAnalise aceita motivo opcional
// (so passado pelo botao 'Rejeitar', NAO pelo botao 'Encerrar operação'
// de uma posicao que ja foi ativa de fato).
async function mudarStatusAnalise(id,novoStatus,motivo,resultado){
  if(novoStatus==='encerrada'&&motivo==='rejeitada'){
    const ok=confirm('Confirma REJEITAR esta análise (nunca foi ativa, sai de Em Análise e vai para Encerradas como rejeitada)? Essa ação grava no repositório.');
    if(!ok)return;
  }
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),15000);
    const body={status:novoStatus};
    if(motivo)body.motivo_encerramento=motivo;
    if(resultado)body.resultado=resultado;
    const r=await fetch(B+'/analises/'+encodeURIComponent(id)+'/status',{
      method:'PUT',headers:{'Content-Type':'application/json',..._authHeaders()},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
    await loadAnalises();
  }catch(e){
    alert('Erro ao mudar status: '+e.message);
  }
}

async function loadCondicional(id){
  const a=(_analiseData||[]).find(x=>x.id===id);
  if(!a)return;
  const btn=document.getElementById('analise-cond-btn-'+id);
  const area=document.getElementById('analise-cond-area-'+id);
  if(!area)return;
  const abrir=area.style.display==='none';
  area.style.display=abrir?'block':'none';
  if(!abrir)return;
  if(area.dataset.loaded){return;}
  area.innerHTML='<p style="color:var(--muted);font-size:11px;padding:10px;text-align:center">Calculando probabilidade condicional...</p>';
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const body={ticker:a.ticker,preco_foto:a.preco_foto,data_foto:a.data_foto,prazo_dias:a.prazo_dias};
    if(a.k_call!=null)body.k_call=a.k_call;
    if(a.k_put!=null)body.k_put=a.k_put;
    if(a.kdo!=null)body.kdo=a.kdo;
    if(a.kuo!=null)body.kuo=a.kuo;
    if(a.alavancagem!=null)body.alavancagem=a.alavancagem;
    if(a.teto_retorno_pct!=null)body.teto_retorno_pct=a.teto_retorno_pct;
    if(a.ganho_prefixado_pct!=null)body.ganho_prefixado_pct=a.ganho_prefixado_pct;
    if(a.exercicio!=null)body.exercicio=a.exercicio;
    if(a.meta_pct!=null)body.meta_pct=a.meta_pct;
    if(a.premio!=null)body.premio=a.premio;
    if(a.qtd_acoes!=null)body.qtd_acoes=a.qtd_acoes;
    // ADICIONADO 15/07/2026 -- mesmo motivo do outro fetch acima pro
    // mesmo endpoint: faltava repassar a mecanica de queda customizada.
    if(a.downside_antes!=null)body.downside_antes=a.downside_antes;
    if(a.downside_apos!=null)body.downside_apos=a.downside_apos;
    const r=await fetch(B+'/montecarlo/condicional',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify(body)
    });
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    area.dataset.loaded='1';
    renderCondicional(id,d);
  }catch(e){
    area.innerHTML='<p style="color:var(--red);font-size:11px;padding:10px">Erro: '+e.message+'</p>';
  }
}

function renderCondicional(id,d){
  const area=document.getElementById('analise-cond-area-'+id);
  if(!area)return;

  if(d.fora_do_prazo){
    area.innerHTML='<div style="padding:10px;background:rgba(240,98,146,.08);border-left:2px solid var(--red);font-size:11px;color:var(--text);line-height:1.5">'+
      '⚠ '+(d.mensagem||'Prazo original já esgotado.')+
      '<br>Preço atual: <b>'+fR(d.preco_atual)+'</b> · Dias passados: <b>'+d.dias_passados+'</b> de '+d.prazo_dias+'</div>';
    return;
  }

  let probsHtml='<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">1. PROBABILIDADES — PREÇO DA FOTO vs. ATUAL</div>';
  probsHtml+='<div class="sb" style="margin-top:0">';
  probsHtml+='<div class="sr"><span class="sl">Preço atual</span><span class="sv">'+fR(d.preco_atual)+'</span></div>';
  probsHtml+='<div class="sr"><span class="sl">Dias passados / restantes</span><span class="sv">'+d.dias_passados+' / '+d.dias_restantes+'</span></div>';
  if(d.prob_call_exercida!=null)probsHtml+='<div class="sr"><span class="sl">Prob. Call exercida (restante)</span><span class="sv '+(d.prob_call_exercida>50?'itm':d.prob_call_exercida>30?'warn':'ok')+'">'+d.prob_call_exercida.toFixed(2)+'%</span></div>';
  if(d.prob_put_exercida!=null)probsHtml+='<div class="sr"><span class="sl">Prob. Put exercida (restante)</span><span class="sv '+(d.prob_put_exercida>50?'itm':d.prob_put_exercida>30?'warn':'ok')+'">'+d.prob_put_exercida.toFixed(2)+'%</span></div>';
  if(d.prob_sem_barreira!=null){
    probsHtml+='<div class="sr" title="Chance de NAO tocar a barreira DAQUI PRA FRENTE (a partir de hoje, usando o preco atual). Numero dinamico -- muda conforme o preco se move. E o numero que importa para decidir o proximo passo."><span class="sl">Prob. sem tocar barreira (daqui p/ frente)</span><span class="sv ok">'+d.prob_sem_barreira.toFixed(2)+'%</span></div>';
    probsHtml+='<div class="sr"><span class="sl">Prob. barreira alta (KUO)</span><span class="sv warn">'+d.prob_barreira_alta.toFixed(2)+'%</span></div>';
    probsHtml+='<div class="sr"><span class="sl">Prob. barreira baixa (KDO)</span><span class="sv warn">'+d.prob_barreira_baixa.toFixed(2)+'%</span></div>';
  }
  if(d.prob_ganho_prefixado_condicional!=null){
    probsHtml+='<div class="sr" title="Chance de NAO tocar a barreira DAQUI PRA FRENTE (a partir de hoje, usando o preco atual e os dias restantes). Numero dinamico -- muda conforme o preco se move. E o numero que importa para decidir o proximo passo (mesmo numero usado no ranking)."><span class="sl">Prob. ganho prefixado (daqui p/ frente)</span><span class="sv ok">'+d.prob_ganho_prefixado_condicional.toFixed(2)+'%</span></div>';
    probsHtml+='<div class="sr"><span class="sl">Prob. tocar barreira (sem garantia)</span><span class="sv warn">'+(100-d.prob_ganho_prefixado_condicional).toFixed(2)+'%</span></div>';
  }
  if(d.prob_ganho_prefixado!=null){
    probsHtml+='<div class="sr" title="Probabilidade calculada DESDE O INICIO da foto (prazo total, preco original) -- usada apenas para o painel de aproveitamento em Encerradas, nao reflete o momento atual."><span class="sl">Prob. ganho prefixado (desde o início, referência)</span><span class="sv" style="color:var(--muted)">'+d.prob_ganho_prefixado.toFixed(2)+'%</span></div>';
  }
  const g=d.garch;
  const volTxt=g?('GARCH '+g.vol_garch_projetada_pct+'%'):('Vol.hist '+d.volatilidade_historica_pct+'%');
  probsHtml+='<div class="sr"><span class="sl">Volatilidade usada</span><span class="sv">'+volTxt+'</span></div>';
  probsHtml+='</div>';

  // Venda de PUT: resultado fixo (premio/meta) + risco de exercício —
  // combina os blocos 2 e 3 num só, já que o retorno "se não exercida"
  // é um fato fixo (não simulado), diferente de call coberta/bidirecional
  let putFixoHtml='';
  if(d.put_resultado_fixo){
    const pf=d.put_resultado_fixo;
    putFixoHtml='<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">'+
      '<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">2-3. RESULTADO FIXO — PRÊMIO vs. META (venda de PUT)</div>'+
      '<div class="sb" style="margin-top:0">'+
      '<div class="sr"><span class="sl">'+pf.descricao_nao_exercida+'</span><span class="sv ok">+'+fR(pf.premio_reais)+'</span></div>'+
      '<div class="sr"><span class="sl">Retorno sobre capital comprometido</span><span class="sv">'+pf.retorno_pct.toFixed(2)+'% ('+(pf.retorno_mes_pct!=null?pf.retorno_mes_pct.toFixed(2):'?')+'%/mês)</span></div>'+
      '<div class="sr"><span class="sl">Bate a meta de 2-2,5%/mês?</span><span class="sv '+(pf.bate_meta?'ok':'itm')+'">'+(pf.bate_meta?'SIM ✓':'NÃO')+'</span></div>'+
      '<div class="sr"><span class="sl">'+pf.descricao_exercida+'</span><span class="sv warn">Capital R$'+fR(pf.capital_comprometido).replace('R$ ','')+'</span></div>'+
      '</div>'+
      '<div style="margin-top:8px;padding:8px 10px;background:rgba(124,106,247,.08);border-left:2px solid var(--accent);font-size:11px;color:var(--text);line-height:1.5">'+
      '📍 Este resultado é fixo (não simulado) — só a probabilidade de exercício acima usa Monte Carlo.'+
      '</div></div>';
  }

  // Simulação didática em 100 ações (R$ concretos, mesmo padrão para qualquer estrutura)
  let sim100Html='';
  if(d.simulacao_100_acoes){
    const s=d.simulacao_100_acoes;
    sim100Html='<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">'+
      '<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">2. SIMULAÇÃO DIDÁTICA — 100 AÇÕES A '+fR(s.preco_foto)+' (CAPITAL '+fR(s.capital)+')</div>'+
      '<div class="sb" style="margin-top:0">';
    if(s.defesa){
      sim100Html+='<div class="sr"><span class="sl">'+s.defesa.descricao+' ('+s.defesa.probabilidade_pct.toFixed(1)+'%)</span><span class="sv">'+fR(s.defesa.retorno_reais)+'</span></div>';
      sim100Html+='<div class="sr"><span class="sl">'+s.dentro.descricao+' ('+s.dentro.probabilidade_pct.toFixed(1)+'%)</span><span class="sv '+(s.dentro.retorno_medio_reais>=0?'ok':'itm')+'">'+(s.dentro.retorno_medio_reais>=0?'+':'')+fR(s.dentro.retorno_medio_reais)+'</span></div>';
      sim100Html+='<div class="sr"><span class="sl">'+s.teto.descricao+' ('+s.teto.probabilidade_pct.toFixed(1)+'%)</span><span class="sv ok">+'+fR(s.teto.retorno_reais)+'</span></div>';
    } else if(s.prefixado){
      sim100Html+='<div class="sr"><span class="sl">'+s.prefixado.descricao+' ('+s.prefixado.probabilidade_pct.toFixed(1)+'%)</span><span class="sv ok">+'+fR(s.prefixado.retorno_reais)+'</span></div>';
      sim100Html+='<div class="sr"><span class="sl">'+s.exposto.descricao+' ('+s.exposto.probabilidade_pct.toFixed(1)+'%)</span><span class="sv '+(s.exposto.retorno_medio_reais>=0?'ok':'itm')+'">'+(s.exposto.retorno_medio_reais>=0?'+':'')+fR(s.exposto.retorno_medio_reais)+'</span></div>';
    } else if(s.nao_exercida){
      sim100Html+='<div class="sr"><span class="sl">'+s.nao_exercida.descricao+' ('+s.nao_exercida.probabilidade_pct.toFixed(1)+'%)</span><span class="sv '+(s.nao_exercida.retorno_medio_reais>=0?'ok':'itm')+'">'+(s.nao_exercida.retorno_medio_reais>=0?'+':'')+fR(s.nao_exercida.retorno_medio_reais)+'</span></div>';
      sim100Html+='<div class="sr"><span class="sl">'+s.exercida.descricao+' ('+s.exercida.probabilidade_pct.toFixed(1)+'%)</span><span class="sv '+(s.exercida.retorno_reais>=0?'ok':'itm')+'">'+(s.exercida.retorno_reais>=0?'+':'')+fR(s.exercida.retorno_reais)+'</span></div>';
    }
    sim100Html+='</div></div>';
  }

  // Tabela de faixas de retorno (só presente quando a análise tem alavancagem + teto_retorno_pct)
  let faixasHtml='';
  if(d.prob_retorno_faixas){
    const f=d.prob_retorno_faixas;
    faixasHtml='<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">'+
      '<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px" title="Estes numeros simulam DESDE O INICIO da estrutura (do preco da foto, com o prazo TOTAL original) -- diferente das probabilidades do bloco 1, que so olham daqui pra frente. Use este bloco como contexto historico de como a estrutura nasceu, nao como criterio de decisao do dia a dia.">3. PROBABILIDADE DE RETORNO FINAL DA ESTRUTURA (desde o início, ⓘ)</div>'+
      '<div class="sb" style="margin-top:0">'+
      '<div class="sr"><span class="sl">Abaixo de 0% (perda)</span><span class="sv itm">'+f.menor_que_0.toFixed(1)+'%</span></div>'+
      '<div class="sr"><span class="sl">Entre 0% e 1%</span><span class="sv">'+f.entre_0_e_1.toFixed(1)+'%</span></div>'+
      '<div class="sr"><span class="sl">Entre 1% e 2%</span><span class="sv">'+f.entre_1_e_2.toFixed(1)+'%</span></div>'+
      '<div class="sr"><span class="sl">Entre 2% e a meta</span><span class="sv warn">'+f.entre_2_e_meta.toFixed(1)+'%</span></div>'+
      '<div class="sr" title="Probabilidade calculada DESDE O INICIO da operacao (prazo total, a partir do preco da foto) -- e diferente do numero do ranking, que olha so daqui pra frente. Pode ser mais alta porque ja incorpora o caminho que o preco percorreu desde a foto."><span class="sl">Bate a meta (≥'+(d.teto_retorno_usado_pct!=null?d.teto_retorno_usado_pct:'?')+'%) — desde o início</span><span class="sv ok">'+f.maior_ou_igual_meta.toFixed(1)+'%</span></div>'+
      '</div>'+
      '<div style="margin-top:8px;padding:8px 10px;background:rgba(124,106,247,.08);border-left:2px solid var(--accent);font-size:11px;color:var(--text);line-height:1.5">'+
      '📍 Retorno médio esperado da estrutura: <b style="color:var(--accent)">'+(d.retorno_medio_pct>=0?'+':'')+d.retorno_medio_pct.toFixed(2)+'%</b>'+
      '</div></div>';
  }

  // Gráfico fan chart (banda completa do dia 0 ao prazo, com linha real sobreposta)
  let graficoHtml='';
  if(d.fan_chart){
    graficoHtml='<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">'+
      '<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">4. EVOLUÇÃO DA FOTO — PREÇO REAL vs. CENÁRIOS PROJETADOS</div>'+
      '<div style="position:relative;height:clamp(240px,30vh,380px);background:var(--bg2);border:1px solid var(--border);padding:8px">'+
      '<canvas id="analise-fan-canvas-'+id+'"></canvas>'+
      '</div></div>';
  }

  area.innerHTML=probsHtml+putFixoHtml+sim100Html+faixasHtml+graficoHtml;

  if(d.fan_chart){
    renderFanChartAnalise(id, d.fan_chart);
  }
}

function renderFanChartAnalise(id, fc){
  const canvas=document.getElementById('analise-fan-canvas-'+id);
  if(!canvas||typeof Chart==='undefined')return;
  if(_analiseCharts[id]){ _analiseCharts[id].destroy(); }

  const dias=fc.dias;
  const datasets=[];
  fc.trajetorias.forEach(traj=>{
    datasets.push({data:traj,borderColor:'rgba(124,106,247,.15)',borderWidth:1,pointRadius:0,fill:false,tension:0.1,order:3});
  });
  datasets.push({label:'P75',data:fc.percentis.p75,borderColor:'transparent',backgroundColor:'rgba(124,106,247,.10)',pointRadius:0,fill:'+1',order:2,tension:0.1});
  datasets.push({label:'P25',data:fc.percentis.p25,borderColor:'transparent',pointRadius:0,fill:false,order:2,tension:0.1});
  datasets.push({label:'Mediana projetada',data:fc.percentis.p50,borderColor:'rgba(124,106,247,.7)',borderWidth:1.5,borderDash:[3,3],pointRadius:0,fill:false,order:1,tension:0.1});
  datasets.push({label:'P90',data:fc.percentis.p90,borderColor:'rgba(0,230,118,.5)',borderWidth:1.2,borderDash:[4,3],pointRadius:0,fill:false,order:1,tension:0.1});
  datasets.push({label:'P10',data:fc.percentis.p10,borderColor:'rgba(240,98,146,.5)',borderWidth:1.2,borderDash:[4,3],pointRadius:0,fill:false,order:1,tension:0.1});
  if(fc.precos_reais&&fc.precos_reais.length){
    datasets.push({label:'Preço real',data:fc.precos_reais,borderColor:'#00e676',borderWidth:2.5,pointRadius:0,fill:false,order:0,tension:0.1});
  }

  _analiseCharts[id]=new Chart(canvas,{
    type:'line',
    data:{labels:dias,datasets},
    options:{
      responsive:true,maintainAspectRatio:false,animation:{duration:300},
      interaction:{intersect:false,mode:'index'},
      plugins:{
        legend:{display:false},
        tooltip:{filter:(item)=>['Mediana projetada','P90','P10','Preço real'].includes(item.dataset.label),
          callbacks:{label:(ctx)=>ctx.dataset.label+': '+fR(ctx.parsed.y)}}
      },
      scales:{
        x:{title:{display:true,text:'Dias desde a foto',color:'#505068',font:{size:10}},ticks:{color:'#505068',font:{size:9}},grid:{color:'#1e1e2e'}},
        y:{title:{display:true,text:'Preço (R$)',color:'#505068',font:{size:10}},ticks:{color:'#505068',font:{size:9}},grid:{color:'#1e1e2e'}},
      }
    }
  });
}

function toggleAllAnalises(){
  if(!_analiseData)return;
  const ids=_analiseData.map(a=>'analise-'+a.id);
  const btn=document.getElementById('btn-all-analise');
  const anyOpen=ids.some(id=>document.getElementById('body-'+id)?.classList.contains('open'));
  ids.forEach(id=>{
    const body=document.getElementById('body-'+id);
    const arr=document.getElementById('ar-'+id);
    if(body){body.classList.toggle('open',!anyOpen);if(arr)arr.textContent=anyOpen?'▶':'▼';}
  });
  if(btn)btn.textContent=anyOpen?'− Recolher Todas':'+ Expandir Todas';
}

// Adicionado 25/06/2026 -- modal de aviso legal (disclaimer CVM).
// Exibido na PRIMEIRA visita deste navegador/dispositivo (controlado via
// localStorage, mesmo padrao ja usado para o token de API). Decisao do
// usuario: material e gratuito por agora (sem cobranca), entao o risco
// regulatorio e menor, mas o disclaimer e boa pratica de transparencia
// mesmo assim -- baseado em pratica real de mercado (BTG/Genial/Valora),
// MAS usuario foi avisado explicitamente que isso NAO substitui validacao
// juridica antes de qualquer uso comercial futuro.
function showDisclaimerIfNeeded(){
  const aceito=localStorage.getItem('disclaimer_aceito');
  if(!aceito){
    const ov=document.getElementById('disclaimer-overlay');
    if(ov)ov.style.display='flex';
  }
}
function aceitarDisclaimer(){
  localStorage.setItem('disclaimer_aceito','1');
  const ov=document.getElementById('disclaimer-overlay');
  if(ov)ov.style.display='none';
}
function abrirDisclaimer(){
  const ov=document.getElementById('disclaimer-overlay');
  if(ov)ov.style.display='flex';
}
showDisclaimerIfNeeded();

main();setInterval(main,120000);
// ============================================================
// ETFs -- aba nova (backlog item 4, fechado 02/07/2026)
// Universo fechado de 53 ETFs (27 Nacionais + 26 Americanos).
// Fluxo: Watchlist -> Em Analise (score por faixa de risco) -> Carteira
// (mesmo tratamento de ativo simples ja usado p/ PETR4/VALE3/BBAS3).
// ============================================================
let _etfData = [];
let _etfEstado = { em_analise: [], carteira: [] };
let _etfMercadoAtivo = 'Todos';
let _etfRiscoAtivo = 'Todos';
let _etfSortCol = 'cap';
let _etfSortDir = -1;

const ETF_RISCO_LABEL = {1:'1 RF curta',2:'2 RF longa',3:'3 High income',4:'4 Ouro/Câmbio',5:'5 Dividendo/Value',6:'6 Real Estate',7:'7 Índice amplo',8:'8 Small/Mid',9:'9 Setorial',10:'10 Cripto'};

function etfSubTab(nome, el) {
  document.querySelectorAll('.etf-subtab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.etf-subcontent').forEach(x => x.style.display = 'none');
  document.getElementById('etf-sub-' + nome).style.display = 'block';
  if (el) el.classList.add('active');
  if (nome === 'emanalise') renderEtfAnaliseTable();
  if (nome === 'carteira') renderEtfCarteira();
}

async function loadETFs(forcar) {
  const tbody = document.getElementById('etf-tbody');
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="9" style="padding:20px;text-align:center;color:var(--muted);animation:pulse 1.5s infinite">⏳ Carregando ETFs (investidor10 + Yahoo)...</td></tr>';
  }
  try {
    const urlEtfs = '/etfs' + (forcar ? '?forcar=1' : '');
    const [rData, rEstado] = await Promise.all([
      fetch(urlEtfs, {cache: 'no-store'}).then(r => r.json()),
      fetch('/etfs/estado', {cache: 'no-store'}).then(r => r.json())
    ]);
    _etfData = rData;
    _etfEstado = rEstado || { em_analise: [], carteira: [] };
    window._etfDataPronto = true;
    renderEtfFiltros();
    renderEtfTable();
  } catch (e) {
    console.error('Erro ao carregar ETFs', e);
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="9" style="padding:20px;text-align:center;color:var(--red)">Erro ao carregar ETFs. Tenta de novo em alguns segundos.</td></tr>';
    }
  }
}

function renderEtfFiltros() {
  const mercados = ['Todos', 'Nacional', 'Americano'];
  const mf = document.getElementById('etf-mercado-filtros');
  mf.innerHTML = '';
  mercados.forEach(m => {
    const b = document.createElement('button');
    b.className = 'etf-filtro-btn' + (m === _etfMercadoAtivo ? ' active' : '');
    b.textContent = m;
    b.onclick = () => { _etfMercadoAtivo = m; renderEtfFiltros(); renderEtfTable(); };
    mf.appendChild(b);
  });

  const riscos = ['Todos', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  const rf = document.getElementById('etf-risco-filtros');
  rf.innerHTML = '';
  riscos.forEach(r => {
    const label = r === 'Todos' ? 'Todos os riscos' : ETF_RISCO_LABEL[r];
    const b = document.createElement('button');
    b.className = 'etf-filtro-btn' + (r === _etfRiscoAtivo ? ' active' : '');
    b.textContent = label;
    b.onclick = () => { _etfRiscoAtivo = r; renderEtfFiltros(); renderEtfTable(); };
    rf.appendChild(b);
  });
}

function _etfFmtCap(v) {
  if (v == null) return '—';
  if (v >= 1000) return (v / 1000).toFixed(2).replace('.', ',') + ' B';
  return v.toFixed(2).replace('.', ',') + ' M';
}
function _etfFmtPct(v) {
  if (v == null) return '—';
  return (v > 0 ? '+' : '') + v.toFixed(2).replace('.', ',') + '%';
}

function _etfColunas() {
  return [
    { k: 'ticker', l: 'Ticker' },
    { k: 'mercado', l: 'Mercado' },
    { k: 'categoria', l: 'Categoria' },
    { k: 'desc', l: 'O que é' },
    { k: 'dy', l: 'DY' },
    { k: 'var_12m', l: 'Var 12m' },
    { k: 'var_24m', l: 'Var 24m' },
    { k: 'cap', l: 'Cap' },
    { k: 'risco', l: 'Risco' },
    { k: '_acao', l: '' }
  ];
}

function renderEtfTable() {
  const cols = _etfColunas();
  const thead = document.getElementById('etf-thead');
  thead.innerHTML = '';
  cols.forEach(c => {
    const th = document.createElement('th');
    th.textContent = c.l + (_etfSortCol === c.k ? (_etfSortDir === 1 ? ' ▲' : ' ▼') : '');
    if (c.k !== '_acao') {
      th.onclick = () => {
        if (_etfSortCol === c.k) { _etfSortDir *= -1; }
        else { _etfSortCol = c.k; _etfSortDir = ['ticker', 'mercado', 'categoria', 'desc'].includes(c.k) ? 1 : -1; }
        renderEtfTable();
      };
    }
    thead.appendChild(th);
  });

  let rows = _etfData.filter(d => {
    if (_etfMercadoAtivo !== 'Todos' && d.mercado !== _etfMercadoAtivo) return false;
    if (_etfRiscoAtivo !== 'Todos' && d.risco !== _etfRiscoAtivo) return false;
    if (document.getElementById('etf-so-pagadores').checked && !d.pagador) return false;
    return true;
  });
  rows.sort((a, b) => {
    let av = a[_etfSortCol], bv = b[_etfSortCol];
    if (av == null) av = (typeof bv === 'number') ? -Infinity : '';
    if (bv == null) bv = (typeof av === 'number') ? -Infinity : '';
    if (typeof av === 'string') return av.localeCompare(bv) * _etfSortDir;
    return (av - bv) * _etfSortDir;
  });
  document.getElementById('etf-count-label').textContent = rows.length + ' de ' + _etfData.length + ' ETFs';

  const tb = document.getElementById('etf-tbody');
  tb.innerHTML = '';
  const jaEmAnalise = new Set(_etfEstado.em_analise || []);
  const jaEmCarteira = new Set((_etfEstado.carteira || []).map(c => c.ticker));
  rows.forEach(d => {
    const tr = document.createElement('tr');
    const dyColor = d.dy == null ? 'var(--muted)' : 'inherit';
    const v12Color = d.var_12m == null ? 'var(--muted)' : (d.var_12m >= 0 ? '#2ecc71' : '#e74c3c');
    const v24Color = d.var_24m == null ? 'var(--muted)' : (d.var_24m >= 0 ? '#2ecc71' : '#e74c3c');
    let acaoHtml;
    if (jaEmCarteira.has(d.ticker)) {
      acaoHtml = '<span style="font-size:11px;color:var(--muted)">✓ Em carteira</span>';
    } else if (jaEmAnalise.has(d.ticker)) {
      acaoHtml = '<span style="font-size:11px;color:var(--accent)">✓ Em análise</span>';
    } else {
      acaoHtml = '<button style="font-size:11px;background:var(--bg3);border:1px solid var(--border);color:var(--accent);padding:4px 10px;cursor:pointer;font-family:inherit;font-weight:600;border-radius:3px" onclick="moverEtf(\'' + d.ticker + '\',\'em_analise\',null,this)">+ Em Análise</button>';
    }
    tr.innerHTML =
      '<td style="font-weight:600">' + d.ticker + (d.pagador ? '<span class="etf-tag-div">div</span>' : '') + '</td>' +
      '<td style="color:var(--muted)">' + d.mercado + '</td>' +
      '<td style="color:var(--muted)">' + d.categoria + '</td>' +
      '<td style="color:var(--muted);white-space:normal">' + d.desc + '</td>' +
      '<td style="color:' + dyColor + '">' + (d.dy == null ? '—' : d.dy.toFixed(2).replace('.', ',') + '%') + '</td>' +
      '<td style="color:' + v12Color + '">' + _etfFmtPct(d.var_12m) + '</td>' +
      '<td style="color:' + v24Color + '">' + _etfFmtPct(d.var_24m) + '</td>' +
      '<td style="color:var(--muted)">' + _etfFmtCap(d.cap) + '</td>' +
      '<td style="color:var(--muted)">' + d.risco + '</td>' +
      '<td>' + acaoHtml + '</td>';
    tb.appendChild(tr);
  });
}

function _etfScore(d, grupo) {
  // Score simples dentro da mesma faixa de risco: combina DY e variacao 12m
  // normalizados pelo maior valor do grupo. Volatilidade real (GARCH) fica
  // como refinamento futuro -- por ora usa os campos ja disponiveis.
  const maxDy = Math.max(1, ...grupo.map(g => g.dy || 0));
  const maxV12 = Math.max(1, ...grupo.map(g => Math.abs(g.var_12m || 0)));
  const nDy = (d.dy || 0) / maxDy;
  const nV12 = ((d.var_12m || 0) + maxV12) / (2 * maxV12);
  return Math.round((nDy * 0.6 + nV12 * 0.4) * 100);
}

function renderEtfAnaliseTable() {
  const tickers = new Set(_etfEstado.em_analise || []);
  const itens = _etfData.filter(d => tickers.has(d.ticker));
  const cols = _etfColunas().slice(0, -1).concat([{ k: '_score', l: 'Score' }, { k: '_acao', l: '' }]);
  const thead = document.getElementById('etf-analise-thead');
  thead.innerHTML = '';
  cols.forEach(c => {
    const th = document.createElement('th');
    th.textContent = c.l;
    thead.appendChild(th);
  });

  const tb = document.getElementById('etf-analise-tbody');
  tb.innerHTML = '';
  if (!itens.length) {
    tb.innerHTML = '<tr><td colspan="' + cols.length + '" style="color:var(--muted);padding:12px">Nenhum ETF em análise ainda. Mande algum da Watchlist.</td></tr>';
    return;
  }
  itens.forEach(d => {
    const grupo = itens.filter(x => x.risco === d.risco);
    const score = _etfScore(d, grupo);
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td style="font-weight:600">' + d.ticker + (d.pagador ? '<span class="etf-tag-div">div</span>' : '') + '</td>' +
      '<td style="color:var(--muted)">' + d.mercado + '</td>' +
      '<td style="color:var(--muted)">' + d.categoria + '</td>' +
      '<td style="color:var(--muted);white-space:normal">' + d.desc + '</td>' +
      '<td>' + (d.dy == null ? '—' : d.dy.toFixed(2).replace('.', ',') + '%') + '</td>' +
      '<td>' + _etfFmtPct(d.var_12m) + '</td>' +
      '<td>' + _etfFmtPct(d.var_24m) + '</td>' +
      '<td style="color:var(--muted)">' + _etfFmtCap(d.cap) + '</td>' +
      '<td style="color:var(--muted)">' + d.risco + '</td>' +
      '<td><span class="etf-tag-score">' + score + '</span></td>' +
      '<td><button style="font-size:11px;background:var(--accent);border:none;color:#fff;padding:4px 10px;cursor:pointer;font-family:inherit;font-weight:700;border-radius:3px" onclick="moverEtf(\'' + d.ticker + '\',\'carteira\',' + (d.preco || 'null') + ',this)">OK → Carteira</button></td>';
    tb.appendChild(tr);
  });
}

let _etfCarteiraProjecaoChart = null;

async function renderEtfCarteira() {
  const div = document.getElementById('etf-carteira-lista');
  const todosItens = _etfEstado.carteira || [];
  // ADICIONADO 15/07/2026 -- itens sem 'status' sao tratados como 'ativa'
  // (compatibilidade retroativa, mesmo padrao ja usado em FIIs).
  const itens = todosItens.filter(c => (c.status || 'ativa') === 'ativa');
  const encerrados = todosItens.filter(c => c.status === 'encerrada');
  if (!itens.length && !encerrados.length) {
    div.innerHTML = '<p style="color:var(--muted);font-size:13px">Nenhum ETF na carteira ainda.</p>';
    return;
  }

  div.innerHTML =
    (itens.length ? (
    '<div id="etf-carteira-resumo" style="border:1px solid var(--border);border-radius:6px;padding:14px;margin-bottom:14px;background:var(--bg2)">' +
      '<div style="font-size:11px;color:var(--muted)">Calculando resumo da carteira (vol. real com correlação entre ativos)...</div>' +
    '</div>' +
    '<div id="etf-carteira-cards"></div>' +
    '<div id="etf-carteira-projecao-panel" style="display:none;margin-top:14px;padding:10px;background:var(--bg2);border:1px solid var(--border)">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">' +
        '<div id="etf-projecao-titulo" style="font-size:12px;font-weight:700;color:var(--text)"></div>' +
        '<span onclick="fecharEtfProjecao()" style="cursor:pointer;color:var(--muted);font-size:14px">✕</span>' +
      '</div>' +
      '<div id="etf-projecao-confianca" style="font-size:11px;color:var(--text);line-height:1.5;margin-bottom:8px;padding:8px 10px;background:rgba(124,106,247,.08);border-left:2px solid var(--accent);text-align:left"></div>' +
      '<div style="position:relative;height:clamp(280px,34vh,440px);background:var(--bg1);border:1px solid var(--border);padding:8px">' +
        '<canvas id="etf-projecao-canvas"></canvas>' +
      '</div>' +
    '</div>'
    ) : '<p style="color:var(--muted);font-size:13px;margin-bottom:14px">Nenhum ETF ativo na carteira no momento.</p>') +
    '<div id="etf-carteira-encerrados"></div>';

  if (itens.length) {
  // Cards individuais (sincronos, usando dado ja carregado da watchlist -- rapido)
  const cardsDiv = document.getElementById('etf-carteira-cards');
  cardsDiv.innerHTML = itens.map(c => {
    const info = _etfData.find(d => d.ticker === c.ticker) || {};
    const precoAtual = info.preco;
    const variacao = (c.preco_entrada && precoAtual) ? ((precoAtual / c.preco_entrada - 1) * 100) : null;
    const varColor = variacao == null ? 'var(--muted)' : (variacao >= 0 ? '#2ecc71' : '#e74c3c');
    return '<div style="border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">' +
      '<div style="cursor:pointer" onclick="verEtfProjecao(\'' + c.ticker + '\')" onmouseover="this.parentElement.style.borderColor=\'var(--accent)\'" onmouseout="this.parentElement.style.borderColor=\'var(--border)\'"><b>' + c.ticker + '</b><span style="color:var(--muted);font-size:12px;margin-left:8px">' + (info.desc || '') + '</span>' +
      '<div style="font-size:11px;color:var(--muted)">Entrada: ' + (c.data_entrada || '—') + ' a R$ ' + (c.preco_entrada != null ? c.preco_entrada.toFixed(2) : '—') + ' · clique p/ ver projeção 📈</div></div>' +
      '<div style="text-align:right;display:flex;align-items:center;gap:10px">' +
      '<div><div>R$ ' + (precoAtual != null ? precoAtual.toFixed(2) : '—') + '</div>' +
      '<div style="color:' + varColor + ';font-size:12px">' + (variacao != null ? _etfFmtPct(variacao) : '—') + '</div></div>' +
      '<button onclick="encerrarEtfCarteira(\'' + c.ticker + '\')" style="background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 9px;font-size:10px;cursor:pointer;font-family:inherit;font-weight:600">Encerrar</button>' +
      '</div></div>';
  }).join('');
  }

  // Tabela de Encerrados (mesmo padrao visual de renderCarteiraFiis)
  const encDiv = document.getElementById('etf-carteira-encerrados');
  if (encerrados.length) {
    const linhaEncerrado = c => {
      const cor = c.resultado==='sucesso' ? 'var(--green,#2ecc71)' : c.resultado==='fracasso' ? 'var(--red,#e74c3c)' : 'var(--muted)';
      const valorTxt = c.valor_financeiro_resultado!=null
        ? (c.valor_financeiro_resultado>=0?'+':'')+'R$'+c.valor_financeiro_resultado.toFixed(2)
        : '—';
      return `<tr>
        <td style="padding:6px 8px;font-weight:700">${c.ticker}</td>
        <td style="padding:6px 8px;text-align:right">R$${c.preco_entrada!=null?c.preco_entrada.toFixed(2):'—'}</td>
        <td style="padding:6px 8px;text-align:right">${c.data_encerramento||'—'}</td>
        <td style="padding:6px 8px;text-align:right;color:${cor};font-weight:600">${c.resultado||'—'}</td>
        <td style="padding:6px 8px;text-align:right;color:${cor};font-weight:600">${valorTxt}</td>
        <td style="padding:6px 8px;font-size:9px;color:var(--muted)" title="${c.observacao_encerramento||''}">${c.observacao_encerramento||''}</td>
      </tr>`;
    };
    encDiv.innerHTML = `
    <div style="font-size:11px;font-weight:700;margin:14px 0 6px">Encerrados (${encerrados.length})</div>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:11px">
      <thead><tr style="border-bottom:1px solid var(--border);color:var(--muted);text-align:left">
        <th style="padding:6px 8px">Ticker</th>
        <th style="padding:6px 8px;text-align:right">Preço entrada</th>
        <th style="padding:6px 8px;text-align:right">Data encerr.</th>
        <th style="padding:6px 8px;text-align:right">Resultado</th>
        <th style="padding:6px 8px;text-align:right">Valor (R$)</th>
        <th style="padding:6px 8px">Obs.</th>
      </tr></thead>
      <tbody>${encerrados.map(linhaEncerrado).join('')}</tbody>
    </table>
    </div>`;
  } else if (encDiv) {
    encDiv.innerHTML = '';
  }

  if (!itens.length) return;

  // Resumo agregado (assincrono, roda GARCH/correlação no backend)
  try {
    const r = await fetch('/etfs/carteira/resumo', {cache:'no-store'});
    const d = await r.json();
    const resumoDiv = document.getElementById('etf-carteira-resumo');
    if (!r.ok || d.error) throw new Error(d.error || ('HTTP ' + r.status));
    const retornoColor = d.retorno_pct == null ? 'var(--muted)' : (d.retorno_pct >= 0 ? '#2ecc71' : '#e74c3c');
    let volLinha = '<span style="color:var(--muted)">Volatilidade da carteira indisponível (histórico insuficiente para 2+ ativos).</span>';
    if (d.vol_carteira_pct != null) {
      const diff = d.vol_soma_simples_pct != null ? (d.vol_soma_simples_pct - d.vol_carteira_pct) : null;
      volLinha = 'Vol. anualizada da carteira (correlação real): <b style="color:var(--accent)">' + d.vol_carteira_pct.toFixed(1) + '%</b>' +
        (diff != null && diff > 0.05 ? ' <span style="color:var(--muted);font-size:10px">(vs ' + d.vol_soma_simples_pct.toFixed(1) + '% se os ativos fossem 100% correlacionados — diversificação está descontando ~' + diff.toFixed(1) + 'pp)</span>' : '');
    }
    resumoDiv.innerHTML =
      '<div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:8px">' +
        '<div><div style="font-size:10px;color:var(--muted)">TOTAL INVESTIDO</div><div style="font-size:16px;font-weight:700">R$ ' + d.total_investido.toFixed(2) + '</div></div>' +
        '<div><div style="font-size:10px;color:var(--muted)">VALOR ATUAL</div><div style="font-size:16px;font-weight:700">R$ ' + d.valor_atual.toFixed(2) + '</div></div>' +
        '<div><div style="font-size:10px;color:var(--muted)">RETORNO</div><div style="font-size:16px;font-weight:700;color:' + retornoColor + '">' + (d.retorno_pct != null ? _etfFmtPct(d.retorno_pct) : '—') + '</div></div>' +
      '</div>' +
      '<div style="font-size:11px;color:var(--text)">' + volLinha + '</div>' +
      '<div style="font-size:9px;color:var(--muted);margin-top:6px">' + (d.nota || '') + '</div>';
  } catch (e) {
    const resumoDiv = document.getElementById('etf-carteira-resumo');
    if (resumoDiv) resumoDiv.innerHTML = '<span style="color:var(--red);font-size:11px">Erro ao calcular resumo: ' + e.message + '</span>';
  }
}

async function verEtfProjecao(ticker) {
  const panel = document.getElementById('etf-carteira-projecao-panel');
  const titulo = document.getElementById('etf-projecao-titulo');
  const confEl = document.getElementById('etf-projecao-confianca');
  if (!panel) return;
  panel.style.display = 'block';
  panel.scrollIntoView({behavior:'smooth', block:'nearest'});
  titulo.textContent = '📈 Carregando projeção de ' + ticker + '...';
  confEl.innerHTML = '';
  try {
    const r = await fetch('/etfs/carteira/' + encodeURIComponent(ticker) + '/projecao', {cache:'no-store'});
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || ('HTTP ' + r.status));

    titulo.textContent = `📈 ${d.ticker} (${d.desc || ''}) — preço atual: R$${d.preco_atual.toFixed(2)}`;

    const periodo = Math.max(...d.periodos);
    const bandas = d.bandas[String(periodo)];
    const T = periodo;
    const labels = Array.from({length: T + 1}, (_, i) => `D+${i}`);
    const histReal = (d.historico_real || []).slice(0, T + 1);
    const realData = labels.map((_, i) => i < histReal.length ? histReal[i].close : null);

    const dsConfig = [
      { label:'P90 (banda ampla)', data: bandas.p90, borderColor:'transparent', backgroundColor:'rgba(100,120,180,0.10)', fill:'+1', pointRadius:0, borderWidth:0 },
      { label:'P10 (banda ampla)', data: bandas.p10, borderColor:'transparent', backgroundColor:'rgba(100,120,180,0.10)', fill:false, pointRadius:0, borderWidth:0 },
      { label:'P75 (banda central)', data: bandas.p75, borderColor:'transparent', backgroundColor:'rgba(100,180,130,0.18)', fill:'+1', pointRadius:0, borderWidth:0 },
      { label:'P25 (banda central)', data: bandas.p25, borderColor:'transparent', backgroundColor:'rgba(100,180,130,0.18)', fill:false, pointRadius:0, borderWidth:0 },
      { label:'Mediana (p50)', data: bandas.p50, borderColor:'rgba(180,200,255,0.6)', borderWidth:1.5, borderDash:[4,3], pointRadius:0, fill:false },
      { label:'Preço real', data: realData, borderColor:'#f0c040', borderWidth:2.5, pointRadius:0, fill:false, spanGaps:false },
    ];

    const canvas = document.getElementById('etf-projecao-canvas');
    if (_etfCarteiraProjecaoChart) { _etfCarteiraProjecaoChart.destroy(); }
    _etfCarteiraProjecaoChart = new Chart(canvas, {
      type: 'line',
      data: { labels, datasets: dsConfig },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode:'index', intersect:false },
        plugins: {
          legend: { display:true, labels:{ color:'#aaa', font:{size:10},
            filter: item => !['P90 (banda ampla)','P10 (banda ampla)','P75 (banda central)','P25 (banda central)'].includes(item.text) } },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: R$${ctx.raw?.toFixed(2) ?? '—'}` } }
        },
        scales: {
          x: { ticks:{ color:'#666', maxTicksLimit:10, font:{size:9} }, grid:{color:'rgba(255,255,255,0.04)'} },
          y: { ticks:{ color:'#aaa', font:{size:10}, callback: v => 'R$' + v.toFixed(2) }, grid:{color:'rgba(255,255,255,0.06)'} }
        }
      }
    });

    const p10f = bandas.p10[bandas.p10.length - 1], p90f = bandas.p90[bandas.p90.length - 1];
    const p25f = bandas.p25[bandas.p25.length - 1], p75f = bandas.p75[bandas.p75.length - 1];
    const p50f = bandas.p50[bandas.p50.length - 1];
    confEl.innerHTML =
      `📍 Com <b>80% de confiança</b>, o preço em <b>D+${T}</b> deveria estar entre ` +
      `<b style="color:var(--red)">R$${p10f.toFixed(2)}</b> e <b style="color:var(--green)">R$${p90f.toFixed(2)}</b>. ` +
      `Com <b>50% de confiança</b>, entre ` +
      `<b style="color:var(--red)">R$${p25f.toFixed(2)}</b> e <b style="color:var(--green)">R$${p75f.toFixed(2)}</b>. ` +
      `Mediana: <b style="color:var(--accent)">R$${p50f.toFixed(2)}</b>. ` +
      `<span style="color:var(--muted);font-size:10px">Sem meta/barreira — ETF é buy-and-hold, projeção é só GARCH sobre o preço atual (vol projetada: ${d.sigma_pct?.toFixed(1)}% a.a.).</span>`;
  } catch (e) {
    titulo.textContent = '📈 Erro';
    confEl.innerHTML = '<span style="color:var(--red)">Erro ao carregar projeção: ' + e.message + '</span>';
  }
}

function fecharEtfProjecao() {
  const panel = document.getElementById('etf-carteira-projecao-panel');
  if (panel) panel.style.display = 'none';
  if (_etfCarteiraProjecaoChart) { _etfCarteiraProjecaoChart.destroy(); _etfCarteiraProjecaoChart = null; }
}

async function moverEtf(ticker, destino, precoEntrada, btnEl) {
  const token = localStorage.getItem('api_write_token');
  if (!token) { alert('Token de escrita não configurado neste navegador.'); return; }
  const textoOriginal = btnEl ? btnEl.textContent : null;
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.style.opacity = '.6';
    btnEl.textContent = '⏳ ...';
  }
  const body = { ticker, destino };
  if (destino === 'carteira') body.preco_entrada = precoEntrada;
  try {
    const r = await fetch('/etfs/mover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify(body)
    });
    const j = await r.json();
    if (!r.ok) { alert('Erro: ' + (j.error || r.status)); return; }
    _etfEstado = j.estado;
    renderEtfTable();
    if (destino === 'em_analise') renderEtfAnaliseTable();
    if (destino === 'carteira') renderEtfCarteira();
  } catch (e) {
    alert('Erro ao mover ETF: ' + e.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.style.opacity = '1';
      btnEl.textContent = textoOriginal;
    }
  }
}
