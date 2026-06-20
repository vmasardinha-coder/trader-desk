const B='https://trader-desk.onrender.com';
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
  dj:['UNH','GS','HD','SHW','CAT','AXP','MCD','AMGN','V','TRV','IBM','JPM','HON','CRM','CVX','AAPL','MSFT','DIS','NKE','BA']
};
const fR=v=>v!=null?'R$ '+Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
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

}
function tg(id){
  const b=document.getElementById('sb-'+id),a=document.getElementById('ar-'+id);
  if(!b)return;const op=b.style.display!=='block';
  b.style.display=op?'block':'none';
  if(a)a.textContent=op?'▲':'▼';
  if(op&&!b.dataset.l){b.dataset.l='1';loadSeg(id);}
}

async function loadSeg(id){
  const g=document.getElementById('g-'+id);if(!g)return;
  g.classList.remove('grid');g.style.display='block';
  const pfx=id+'_';
  if(USSEG[id]){
    const tks=USSEG[id];
    g.innerHTML='<table class="tbl-mkt tbl-seg"><colgroup><col style="width:40%"><col style="width:20%"><col style="width:20%"><col style="width:20%"></colgroup><thead><tr><th>Ativo</th><th class="r">Último</th><th class="r">Variação</th><th class="r">Var.%</th></tr></thead><tbody>'+
      tks.map(t=>{const tid=t.replace(/[^a-zA-Z0-9]/g,'_');return '<tr><td><div class="sym">'+t+'</div></td><td class="r"><span class="val loading" id="'+pfx+tid+'_p">—</span></td><td class="r"><span class="chg" id="'+pfx+tid+'_v">—</span></td><td class="r"><span class="chg" id="'+pfx+tid+'_c">—</span></td></tr>';}).join('')+'</tbody></table>';
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
      <div class="sr"><span class="sl">Prob. MC exercer</span><span class="sv ok" id="${id}-mc-rt">calc...</span></div>
      ${p.objetivo?`<div class="sr"><span class="sl">Objetivo</span><span class="sv ok">${p.objetivo}</span></div>`:''}
    </div>
    <div class="sig">
      <div class="sgt">🎲 Monte Carlo — Prob. call ser exercida</div>
      <div id="${id}-mc-l" style="color:var(--muted);font-size:12px">Calculando 5.000 cenários...</div>
      <div id="${id}-mc-r" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
          <div class="ib"><div class="il">Prob. exercer</div><div class="iv" id="${id}-mc-s">—</div></div>
          <div class="ib"><div class="il">Vol. Hist.</div><div class="iv warn" id="${id}-mc-v">—</div></div>
        </div>
        <div style="font-size:11px;color:var(--muted);margin-top:6px;line-height:1.5" id="${id}-mc-i">—</div>
      </div>
    </div>
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
        <div style="font-size:11px;color:var(--muted);margin-top:6px" id="${id}-mc-i">—</div>
      </div>
    </div>
    </div>
  </div>`;
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
  const badgeCls=p.status==='sucesso'?'enc-ok':'enc-warn';
  const badgeTxt=p.status==='sucesso'?'✅ SUCESSO':'⚠ PARCIAL';

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
  ]},
  {segmento:'🛡️ Seguros', ativos:[
    {id:'pssa3', ticker:'PSSA3.SA', nome:'PSSA3 — Porto Seguro ON'},
    {id:'bbse3', ticker:'BBSE3.SA', nome:'BBSE3 — BB Seguridade ON'},
    {id:'cxse3', ticker:'CXSE3.SA', nome:'CXSE3 — Caixa Seguridade ON'},
  ]},
  {segmento:'⚡ Energia Elétrica', ativos:[
    {id:'axia3', ticker:'AXIA3.SA', nome:'AXIA3 — Axia Energia ON'},
  ]},
  {segmento:'🛢️ Petróleo & Gás', ativos:[
    {id:'petr4', ticker:'PETR4.SA', nome:'PETR4 — Petrobras PN'},
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
  ]},
  {segmento:'🏭 Siderurgia', ativos:[
    {id:'ggbr4', ticker:'GGBR4.SA', nome:'GGBR4 — Gerdau PN'},
  ]},
  {segmento:'💳 Fintech / BDR', ativos:[
    {id:'roxo34', ticker:'ROXO34.SA', nome:'ROXO34 — Nubank BDR'},
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
      <div style="display:flex;align-items:center;gap:10px"><span style="cursor:pointer;color:var(--accent);font-size:13px" onclick="event.stopPropagation();rl('${a.id}')">↻</span><span id="ar-ind-${a.id}">▼</span></div>
    </div>
    <div class="ind-acc-body open" id="${a.id}-ind-wrap"><div id="${a.id}-ind"><div style="color:var(--muted);padding:12px;animation:pulse 1.5s infinite">Carregando...</div></div></div>
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

  // AXIA3 A e B — preço via /indicators, distância KDO/KUO
  const a3=byId.a3, a3b=byId.a3b;
  if(a3||a3b){
    setTimeout(async()=>{
      try{const r=await fetch(B+'/indicators/AXIA3.SA');if(!r.ok)return;const d=await r.json();if(!d.preco_atual)return;
        const p=d.preco_atual,pant=d.preco_anterior||p;
        if(a3){E('a3-p',fR(p));Ch('a3-c',p,pant,'r');}
        if(a3b){E('a3b-p',fR(p));Ch('a3b-c',p,pant,'r');}
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
async function MC(tk,sk,dias,lId,rId,sId,vId,iId,rtId){
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),25000);
    const r=await fetch(B+'/montecarlo',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,body:JSON.stringify({ticker:tk,k_call:sk,k_put:sk,t_days:dias,n:5000})});
    if(!r.ok)throw 0;const d=await r.json();if(d.error)throw new Error(d.error);
    document.getElementById(lId).style.display='none';document.getElementById(rId).style.display='block';
    const prob=Number(d.prob_call_exercida||0);
    const sEl=document.getElementById(sId);sEl.textContent=prob.toFixed(1)+'%';
    sEl.className='iv '+(prob<15?'ok':prob<30?'warn':'down');
    document.getElementById(vId).textContent=d.volatilidade_historica_pct+'%';
    const garchTxt=d.garch?` · GARCH proj. ${d.garch.vol_garch_projetada_pct}% (persist. ${d.garch.persistencia})`:'';
    document.getElementById(iId).textContent='Vol.hist. '+d.volatilidade_historica_pct+'%'+garchTxt+' · '+(prob<15?'✅ Risco baixo de exercício':'⚠ Monitorar posição');
    if(rtId)E(rtId,prob.toFixed(1)+'%');
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
    const garchTxt=d.garch?` · GARCH proj. ${d.garch.vol_garch_projetada_pct}% (LP ${d.garch.vol_garch_longo_prazo_pct}%)`:'';
    document.getElementById(pfx+'-mc-i').textContent='R$ '+d.preco_atual+' · KDO R$ '+d.kdo+' · KUO R$ '+d.kuo+garchTxt;
  }catch(e){const el=document.getElementById(pfx+'-mc-l');if(el)el.textContent='Erro: '+(e.message||'timeout');}
}
async function MCR(tk,en,kd,dias,price){
  try{
    const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),40000);
    const payload={ticker:tk,k_call:en,k_put:en,t_days:dias,n:5000};
    if(kd)payload.knock_down=kd;
    if(price)payload.price=price;
    const r=await fetch(B+'/montecarlo',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,body:JSON.stringify(payload)});
    if(!r.ok)throw 0;const d=await r.json();if(d.error)throw new Error(d.error);
    document.getElementById('rx-mc-l').style.display='none';document.getElementById('rx-mc-r').style.display='block';
    const sEl=document.getElementById('rx-mc-s');sEl.textContent=Number(d.prob_sucesso).toFixed(1)+'%';sEl.className='iv '+(d.prob_sucesso>70?'ok':d.prob_sucesso>50?'warn':'down');
    const cEl=document.getElementById('rx-mc-c');if(cEl)cEl.textContent=Number(d.prob_call_exercida).toFixed(1)+'%';
    const kEl=document.getElementById('rx-mc-k');if(kEl)kEl.textContent=d.prob_kdo_atingido!=null?Number(d.prob_kdo_atingido).toFixed(1)+'%':'—';
    document.getElementById('rx-mc-v').textContent=d.volatilidade_historica_pct+'%';
    const garchTxt=d.garch?` · GARCH proj. ${d.garch.vol_garch_projetada_pct}%`:'';
    document.getElementById('rx-mc-i').textContent='R$ '+d.preco_atual+(d.knock_down?' · KDO R$ '+d.knock_down:'')+garchTxt;
    E('rx-mc-rt',Number(d.prob_call_exercida).toFixed(1)+'%');
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
  const inds=data.indicadores||[],sc=Number(data.score_total||0),preco=data.preco_atual,graham=data.graham_value,up=data.upside_graham,setor=data.setor||'';
  const sc2=sc>=65?'var(--green)':sc>=40?'var(--warn)':'var(--red)',sl=sc>=65?'Compra ▲':sc>=40?'Neutro →':'Venda ▼';
  let h='';
  if(data.fund_desatualizado){
    h+='<div style="background:rgba(255,183,77,.1);border:1px solid var(--warn);padding:8px 12px;margin-bottom:10px;font-size:11px;color:var(--warn);font-weight:600">⚠ Fundamentais (P/L, P/VP, ROE, Graham) com '+data.fund_idade_dias+' dias — solicitar revisão trimestral</div>';
  }
  h+='<div class="scb">'+
    '<div class="scc"><div class="scm">Score</div><div class="scn" style="color:'+sc2+'">'+sc+'</div><div class="scl" style="color:'+sc2+'">'+sl+'</div></div>'+
    '<div class="scc"><div class="scm">Cotação</div><div class="scv">'+(preco?'R$ '+Number(preco).toFixed(2):'—')+'</div><div class="scs">'+setor+'</div></div>'+
    '<div class="scc"><div class="scm">Graham VJ</div><div class="scv" style="color:'+(up&&up>0?'var(--green)':'var(--red)')+'">'+(graham?'R$ '+Number(graham).toFixed(2):'—')+'</div><div class="scs" style="color:'+(up&&up>0?'var(--green)':'var(--red)')+'">'+(up!=null?(up>0?'+':'')+up+'% upside':'—')+'</div></div>'+
    '</div>';
  // Convergência de preços-alvo — 4 métodos lado a lado
  const metodos=[
    {nome:'Graham',valor:data.graham_value,up:data.upside_graham},
    {nome:'Bazin',valor:data.preco_alvo_bazin,up:data.upside_bazin},
    {nome:'P/L Setor',valor:data.preco_alvo_pl_setorial,up:data.upside_pl_setorial},
    {nome:'P/VP Setor',valor:data.preco_alvo_vpa,up:data.upside_vpa},
  ].filter(m=>m.valor!=null);
  if(metodos.length>0){
    const media=metodos.reduce((s,m)=>s+m.valor,0)/metodos.length;
    const desvios=metodos.map(m=>Math.abs(m.valor-media)/media*100);
    const maxDesvio=Math.max(...desvios);
    const convergencia=maxDesvio<15?'✅ Convergem':maxDesvio<35?'⚠ Divergência moderada':'🔴 Divergência alta';
    const convCor=maxDesvio<15?'var(--green)':maxDesvio<35?'var(--warn)':'var(--red)';
    h+='<div style="background:var(--bg2);border:1px solid var(--border);padding:12px;margin-bottom:14px">'+
      '<div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-bottom:8px">CONVERGÊNCIA DE PREÇOS-ALVO ('+metodos.length+' métodos)</div>'+
      '<div style="display:grid;grid-template-columns:repeat('+metodos.length+',1fr);gap:6px;margin-bottom:8px">'+
      metodos.map(m=>'<div style="text-align:center"><div style="font-size:9px;color:var(--muted)">'+m.nome+'</div><div style="font-size:13px;font-weight:700;color:'+(m.up>0?'var(--green)':'var(--red)')+'">R$ '+m.valor.toFixed(2)+'</div></div>').join('')+
      '</div>'+
      '<div style="font-size:11px;color:'+convCor+';font-weight:600">'+convergencia+' (desvio máx '+maxDesvio.toFixed(0)+'%) · Média: R$ '+media.toFixed(2)+'</div>'+
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
  const ativos=getWatchlistFlat();
  // Carrega em lotes de 4 para não sobrecarregar o brapi/Yahoo simultaneamente
  const tamLote=4;
  for(let i=0;i<ativos.length;i+=tamLote){
    const lote=ativos.slice(i,i+tamLote);
    const res=await Promise.all(lote.map(a=>wt(fInd(a.ticker),30000,{error:'Timeout 30s'})));
    lote.forEach((a,j)=>rndInd(a.id,res[j]));
  }
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
    setTimeout(async()=>{try{const[bi,bc]=await Promise.all([fBTCI(),fBTCC()]);if(bi)rndBTCI(bi);if(bc)rndBTCC(bc);fFG();}catch(e){}},5000);

    if(_posData&&_posData.ativas){
      const hoje=new Date();
      const byId={}; _posData.ativas.forEach(p=>byId[p.id]=p);
      const diasAte=iso=>Math.max(1,Math.ceil((new Date(iso)-hoje)/864e5));

      // MC simples — PETR4, VALE3, BBAS3 (qualquer 'simples' exceto ROXO34 que usa MCR)
      let delay=6000;
      _posData.ativas.filter(p=>p.tipo_posicao==='simples'&&p.id!=='rx').forEach(p=>{
        setTimeout(()=>MC(p.ticker,p.strike,diasAte(p.vencimento),p.id+'-mc-l',p.id+'-mc-r',p.id+'-mc-s',p.id+'-mc-v',p.id+'-mc-i',p.id+'-mc-rt'),delay);
        delay+=6000;
      });

      // MCB barreira — AXIA3 A e B (ou quaisquer outras tipo 'barreira')
      _posData.ativas.filter(p=>p.tipo_posicao==='barreira').forEach(p=>{
        setTimeout(()=>MCB(p.ticker,p.entry,p.kdo,p.kuo,diasAte(p.vencimento),p.id),delay);
        delay+=6000;
      });

      // MCR — ROXO34 (caso especial: busca preço via /indicators antes)
      if(byId.rx){
        const dR=diasAte(byId.rx.vencimento);
        setTimeout(async()=>{
          try{
            const rRX=await fetch(B+'/indicators/ROXO34.SA');
            const dRX=rRX.ok?await rRX.json():{};
            const priceRX=dRX.preco_atual||null;
            await MCR('ROXO34.SA',byId.rx.strike,null,dR,priceRX);
          }catch(e){MCR('ROXO34.SA',byId.rx.strike,null,dR,null);}
        },delay);
        delay+=6000;
      }

      // BBAS3 cotação — via TV ou fallback /indicators
      if(byId.bb){
        const strikeBB=byId.bb.strike;
        const bbTV=tv['BMFBOVESPA:BBAS3'];
        if(bbTV?.p){
          E('bb-p',fR(bbTV.p));Ch('bb-c',bbTV.p,bbTV.v||bbTV.p,'r');
          const d2=bbTV.p-strikeBB;
          const itm2=document.getElementById('bb-itm');
          if(itm2){itm2.textContent=(d2>=0?'+ R$ ':'- R$ ')+Math.abs(d2).toFixed(2)+' '+(d2>=0?'acima (ITM ⚠)':'abaixo (OTM ✅)')+' do strike';itm2.className='sv '+(d2>=0?'itm':'ok');}
        } else {
          fetch(B+'/indicators/BBAS3.SA').then(r2=>r2.json()).then(d2=>{
            if(d2.preco_atual){
              E('bb-p',fR(d2.preco_atual));if(d2.preco_anterior!=null){Ch('bb-c',d2.preco_atual,d2.preco_anterior,'r');}else{const ec=document.getElementById('bb-c');if(ec)ec.textContent='—';}
              const dist=d2.preco_atual-strikeBB;
              const itm2=document.getElementById('bb-itm');
              if(itm2){itm2.textContent=(dist>=0?'+ R$ ':'- R$ ')+Math.abs(dist).toFixed(2)+' '+(dist>=0?'acima (ITM ⚠)':'abaixo (OTM ✅)')+' do strike';itm2.className='sv '+(dist>=0?'itm':'ok');}
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

main();setInterval(main,120000);