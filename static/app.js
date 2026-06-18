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
          const rb=await fetch(B+'/brapi/'+t+'.SA',{signal:AbortSignal.timeout(8000)});
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
          const r2=await fetch(B+'/indicators/'+t+'.SA',{signal:AbortSignal.timeout(15000)});
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
        const rb=await fetch(B+'/brapi/'+t+'.SA',{signal:AbortSignal.timeout(8000)});
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
        const r2=await fetch(B+'/indicators/'+t+'.SA',{signal:AbortSignal.timeout(15000)});
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
  const segs=['fin','pet','min','mat','uti','cc','cn','sau','ind','tit'];
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
function togPos(id){
  const body=document.getElementById('body-'+id);
  const arr=document.getElementById('ar-'+id);
  if(!body)return;
  const open=body.classList.contains('open');
  body.classList.toggle('open',!open);
  if(arr)arr.textContent=open?'▶':'▼';
}
function toggleAllPos(){
  const ids=['pos-pt','pos-vl','pos-a3','pos-a3b','pos-rx','pos-bb'];
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
function toggleAllInd(){
  const ids=['petr4','vale3','bbas3','axia3','roxo34'];
  const btn=document.getElementById('btn-all-ind');
  const anyOpen=ids.some(id=>document.getElementById(id+'-ind-wrap')?.classList.contains('open'));
  ids.forEach(id=>{
    const body=document.getElementById(id+'-ind-wrap');
    const arr=document.getElementById('ar-ind-'+id);
    if(body){body.classList.toggle('open',!anyOpen);if(arr)arr.textContent=anyOpen?'▶':'▼';}
  });
  if(btn)btn.textContent=anyOpen?'+ Expandir Todos':'− Recolher Todos';
}
async function fHL(){
  try{
    const r=await fetch('https://api.hyperliquid.xyz/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'allMids'})});
    if(!r.ok)return;const d=await r.json();
    const bp=parseFloat(d.BTC||0);
    if(bp>0){E('btc-p',fU(bp));Ch('btc-c',bp,bp*0.99,'u');}
    try{
      const r2=await fetch('https://api.hyperliquid.xyz/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'allMids',dex:'xyz'})});
      if(r2.ok){const d2=await r2.json();
        if(d2['xyz:CL'])E('cl-p','$'+parseFloat(d2['xyz:CL']).toFixed(2));
        if(d2['xyz:GOLD'])E('gold-p','$'+Number(d2['xyz:GOLD']).toLocaleString('en-US',{maximumFractionDigits:0}));
        if(d2['xyz:SILVER'])E('silver-p','$'+parseFloat(d2['xyz:SILVER']).toFixed(2));
        if(d2['xyz:COPPER'])E('copper-p','$'+parseFloat(d2['xyz:COPPER']).toFixed(3));}
    }catch(e){}
  }catch(e){}
}
async function fTV(){
  const out={};
  try{
    const r=await fetch(B+'/tv/brazil',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbols:{tickers:['BMFBOVESPA:PETR4','BMFBOVESPA:ITUB4','BMFBOVESPA:VALE3','BMFBOVESPA:BBDC4','BMFBOVESPA:ABEV3','BMFBOVESPA:BBAS3','BMFBOVESPA:WEGE3','BMFBOVESPA:IBOV']},columns:['close','change_abs']})});
    if(r.ok){const d=await r.json();(d.data||[]).forEach(x=>{const[c,ca]=x.d||[];if(c!=null)out[x.s]={p:c,v:c-(ca||0)};});}
  }catch(e){}
  try{const rr=await fetch(B+'/indicators/ROXO34.SA');if(rr.ok){const dd=await rr.json();if(dd.preco_atual){E('roxo34q-p',fR(dd.preco_atual));const prev=dd.preco_anterior||null;if(prev&&prev!==dd.preco_atual){ChTbl('roxo34q-v','roxo34q-c',dd.preco_atual,prev,'r');}else{const ep=document.getElementById('roxo34q-v');const ec=document.getElementById('roxo34q-c');if(ep)ep.textContent='—';if(ec)ec.textContent='—';}}}}catch(e){}
  return out;
}
async function fFut(){try{const r=await fetch(B+'/futures');if(!r.ok)return null;return await r.json();}catch(e){return null;}}
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
  const pt=tv['BMFBOVESPA:PETR4'];const pp=pt?.p||40,pv=pt?.v||40;
  E('pt-p',fR(pp));Ch('pt-c',pp,pv,'r');
  const pd=pp-30.85;E('pt-itm',(pd>=0?'+ R$ ':'- R$ ')+Math.abs(pd).toFixed(2)+' '+(pd>=0?'acima':'abaixo')+' do strike');
  const vl=tv['BMFBOVESPA:VALE3'];const vp=vl?.p||78,vv=vl?.v||78;
  E('vl-p',fR(vp));Ch('vl-c',vp,vv,'r');
  const vd=vp-57.40;E('vl-itm',(vd>=0?'+ R$ ':'- R$ ')+Math.abs(vd).toFixed(2)+' '+(vd>=0?'acima':'abaixo')+' do strike');

  // Contador de dias/horas dinâmico
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
  cdHoras('2026-12-17','pt-dias');cdHoras('2027-02-18','vl-dias');
  cdHoras('2026-09-14','a3-dias');cdHoras('2026-10-02','a3b-dias');
  cdHoras('2026-07-16','rx-dias');cdHoras('2026-08-20','bb-dias');
  checkBadgeRisco();

  setTimeout(async()=>{
    try{const r=await fetch(B+'/indicators/AXIA3.SA');if(!r.ok)return;const d=await r.json();if(!d.preco_atual)return;
      const p=d.preco_atual,pant=d.preco_anterior||p;E('a3-p',fR(p));E('a3b-p',fR(p));Ch('a3-c',p,pant,'r');Ch('a3b-c',p,pant,'r');
      const kA=43.51,kuA=68.76,kB=40.52,kuB=62.81;
      const dA=document.getElementById('a3-kdo');if(dA)dA.textContent=((p-kA)/p*100).toFixed(1)+'% acima do KDO';
      const uA=document.getElementById('a3-kuo');if(uA)uA.textContent=((kuA-p)/p*100).toFixed(1)+'% para o KUO';
      const sA=document.getElementById('a3-st');if(sA){sA.textContent=p<=kA?'🔴 KDO ATINGIDO':p>=kuA?'⚠ KUO ATINGIDO':'✅ No range';sA.className='sv '+(p<=kA||p>=kuA?'warn':'ok');}
      const dB=document.getElementById('a3b-kdo');if(dB)dB.textContent=((p-kB)/p*100).toFixed(1)+'% acima do KDO';
      const uB=document.getElementById('a3b-kuo');if(uB)uB.textContent=((kuB-p)/p*100).toFixed(1)+'% para o KUO';
      const sB=document.getElementById('a3b-st');if(sB){sB.textContent=p<=kB?'🔴 KDO ATINGIDO':p>=kuB?'⚠ KUO ATINGIDO':'✅ No range';sB.className='sv '+(p<=kB||p>=kuB?'warn':'ok');}
      // Alerta de barreira AXIA3 — vermelho pulsando se < 5% do KDO ou > 5% do KUO
      checkAlertaBarreira('card-a3', p, kA, kuA);
      checkAlertaBarreira('card-a3b', p, kB, kuB);
      // Badge de risco no tab
      checkBadgeRisco();
    }catch(e){}
  },2000);
  setTimeout(async()=>{
    try{const r=await fetch(B+'/indicators/ROXO34.SA');if(!r.ok)return;const d=await r.json();if(!d.preco_atual)return;
      const p=d.preco_atual,pant2=d.preco_anterior||p;E('rx-p',fR(p));Ch('rx-c',p,pant2,'r');
      const itm=document.getElementById('rx-itm');
      const dist=p-10.50;
      if(itm)itm.textContent=(dist>=0?'+ R$ ':'- R$ ')+Math.abs(dist).toFixed(2)+' '+(dist>=0?'acima (ITM ⚠)':'abaixo (OTM ✅)')+' do strike';
      const de=document.getElementById('rx-kdo');if(de)de.textContent=((p-10.50)/p*100).toFixed(1)+'% do strike';
      const itm2=p>10.50;
      const se=document.getElementById('rx-itm');
      _risco.roxoItm=itm2;
      checkBadgeRisco();
    }catch(e){}
  },3000);
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
    document.getElementById(iId).textContent='Vol.hist. '+d.volatilidade_historica_pct+'% · '+(prob<15?'✅ Risco baixo de exercício':'⚠ Monitorar posição');
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
    document.getElementById(pfx+'-mc-i').textContent='R$ '+d.preco_atual+' · KDO R$ '+d.kdo+' · KUO R$ '+d.kuo;
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
    document.getElementById('rx-mc-i').textContent='R$ '+d.preco_atual+(d.knock_down?' · KDO R$ '+d.knock_down:'');
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
  let h='<div class="scb">'+
    '<div class="scc"><div class="scm">Score</div><div class="scn" style="color:'+sc2+'">'+sc+'</div><div class="scl" style="color:'+sc2+'">'+sl+'</div></div>'+
    '<div class="scc"><div class="scm">Cotação</div><div class="scv">'+(preco?'R$ '+Number(preco).toFixed(2):'—')+'</div><div class="scs">'+setor+'</div></div>'+
    '<div class="scc"><div class="scm">Graham VJ</div><div class="scv" style="color:'+(up&&up>0?'var(--green)':'var(--red)')+'">'+(graham?'R$ '+Number(graham).toFixed(2):'—')+'</div><div class="scs" style="color:'+(up&&up>0?'var(--green)':'var(--red)')+'">'+(up!=null?(up>0?'+':'')+up+'% upside':'—')+'</div></div>'+
    '</div>';
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
    '<div class="ib"><div class="il">MVRV Z-Score</div><div class="iv '+(d.mvrv_zscore?.value<1?'ok':d.mvrv_zscore?.value<3?'warn':'down')+'">'+d.mvrv_zscore?.value+'</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+d.mvrv_zscore?.label+'</div></div>'+
    '<div class="ib"><div class="il">NUPL</div><div class="iv warn">'+((d.nupl?.value||0)*100).toFixed(0)+'%</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+d.nupl?.label+'</div></div>'+
    '<div class="ib"><div class="il">Puell Multiple</div><div class="iv warn">'+d.puell?.value+'</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+d.puell?.label+'</div></div>'+
    '<div class="ib"><div class="il">200W MA</div><div class="iv warn">'+fU2(d.ma200w)+'</div><div style="font-size:11px;color:var(--muted);margin-top:3px">'+(d.ma200w_pct?'+'+d.ma200w_pct+'%':'')+'</div></div>'+
    '<div class="ib"><div class="il">Rainbow Band</div><div class="iv warn">'+(d.rainbow?.band||'—')+'</div></div>'+
    '<div class="ib"><div class="il">Pi Cycle Dist.</div><div class="iv ok">'+fU2(d.pi_cycle?.distance)+'</div></div>'+
    '</div><div style="background:var(--bg2);border:1px solid var(--border);padding:10px;font-size:13px;color:var(--accent);font-weight:600">'+(d.pi_cycle?.signal||'')+'</div>';
}
async function loadInd(){
  const wt=(p,ms,fb)=>Promise.race([p,new Promise(r=>setTimeout(()=>r(fb),ms))]);
  const[bi,bc]=await Promise.all([wt(fBTCI(),15000,{error:'Timeout — clique ↻'}),wt(fBTCC(),15000,null)]);
  rndBTCI(bi);rndBTCC(bc);fFG();
  const stocks=[['PETR4.SA','petr4'],['VALE3.SA','vale3'],['BBAS3.SA','bbas3'],['AXIA3.SA','axia3'],['ROXO34.SA','roxo34']];
  const res=await Promise.all(stocks.map(([t])=>wt(fInd(t),30000,{error:'Timeout 30s'})));
  stocks.forEach(([,id],i)=>rndInd(id,res[i]));
}
async function rl(tk){
  const el=document.getElementById(tk+'-ind');
  if(el)el.innerHTML='<div style="color:var(--muted);padding:12px;animation:pulse 1s infinite">Carregando...</div>';
  const m={petr4:'PETR4.SA',vale3:'VALE3.SA',bbas3:'BBAS3.SA',axia3:'AXIA3.SA',roxo34:'ROXO34.SA'};
  rndInd(tk,await fInd(m[tk]));
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
    const[,tv,ft]=await Promise.all([fHL(),fTV(),fFut()]);
    const now=new Date().toLocaleTimeString('pt-BR');
    E('last-update','↻ '+now);E('last-update-tbl',now);E('footer-time',now);
    window._lastTV=tv;doMacro(tv,ft);doPos(tv);
    setTimeout(fFund,3000);
    setTimeout(async()=>{try{const[bi,bc]=await Promise.all([fBTCI(),fBTCC()]);if(bi)rndBTCI(bi);if(bc)rndBTCC(bc);fFG();}catch(e){}},5000);
    const hoje=new Date();
    const dP=Math.max(1,Math.ceil((new Date('2026-12-17')-hoje)/864e5));
    const dV=Math.max(1,Math.ceil((new Date('2027-02-18')-hoje)/864e5));
    const dA=Math.max(1,Math.ceil((new Date('2026-09-14')-hoje)/864e5));
    const dAb=Math.max(1,Math.ceil((new Date('2026-10-02')-hoje)/864e5));
    const dR=Math.max(1,Math.ceil((new Date('2026-07-16')-hoje)/864e5));
    setTimeout(()=>MC('PETR4.SA',30.85,dP,'pt-mc-l','pt-mc-r','pt-mc-s','pt-mc-v','pt-mc-i','pt-mc-rt'),6000);
    setTimeout(()=>MC('VALE3.SA',57.40,dV,'vl-mc-l','vl-mc-r','vl-mc-s','vl-mc-v','vl-mc-i','vl-mc-rt'),12000);
    setTimeout(()=>MCB('AXIA3.SA',54.31,43.51,68.76,dA,'a3'),18000);
    setTimeout(()=>MCB('AXIA3.SA',50.65,40.52,62.81,dAb,'a3b'),24000);
    setTimeout(async()=>{
    try{
      const rRX=await fetch(B+'/indicators/ROXO34.SA');
      const dRX=rRX.ok?await rRX.json():{};
      const priceRX=dRX.preco_atual||null;
      await MCR('ROXO34.SA',10.50,null,dR,priceRX);
    }catch(e){MCR('ROXO34.SA',10.50,null,dR,null);}
  },30000);
    const dBB=Math.max(1,Math.ceil((new Date('2026-08-20')-hoje)/864e5));
    setTimeout(()=>MC('BBAS3.SA',21.65,dBB,'bb-mc-l','bb-mc-r','bb-mc-s','bb-mc-v','bb-mc-i','bb-mc-rt'),36000);
    // BBAS3 cotação — via TV ou fallback /indicators
    const bbTV=tv['BMFBOVESPA:BBAS3'];
    if(bbTV?.p){
      E('bb-p',fR(bbTV.p));Ch('bb-c',bbTV.p,bbTV.v||bbTV.p,'r');
      const d2=bbTV.p-21.65;
      const itm2=document.getElementById('bb-itm');
      if(itm2){itm2.textContent=(d2>=0?'+ R$ ':'- R$ ')+Math.abs(d2).toFixed(2)+' '+(d2>=0?'acima (ITM ⚠)':'abaixo (OTM ✅)')+' do strike';itm2.className='sv '+(d2>=0?'itm':'ok');}
    } else {
      // TV não retornou BBAS3 — fallback
      fetch(B+'/indicators/BBAS3.SA').then(r2=>r2.json()).then(d2=>{
        if(d2.preco_atual){
          E('bb-p',fR(d2.preco_atual));if(d2.preco_anterior&&d2.preco_anterior!==d2.preco_atual){Ch('bb-c',d2.preco_atual,d2.preco_anterior,'r');}else{const ec=document.getElementById('bb-c');if(ec)ec.textContent='—';}
          const dist=d2.preco_atual-21.65;
          const itm2=document.getElementById('bb-itm');
          if(itm2){itm2.textContent=(dist>=0?'+ R$ ':'- R$ ')+Math.abs(dist).toFixed(2)+' '+(dist>=0?'acima (ITM ⚠)':'abaixo (OTM ✅)')+' do strike';itm2.className='sv '+(dist>=0?'itm':'ok');}
        }
      }).catch(()=>{});
    }
    // Black-Scholes dinâmico — roda uma vez por ciclo, delay para não disputar com MC
    setTimeout(loadBS, 4000);
    window._IL=false;
  }catch(e){console.error(e);}
}
// ── BLACK-SCHOLES DINÂMICO ───────────────────────────
// Vol implícita atual (atualizar manualmente quando mudar)
const BS_PARAMS = {
  pt: {ticker:'PETR4.SA', strike:30.85,  vol:0.434, tipo:'call', pfx:'pt'},
  vl: {ticker:'VALE3.SA', strike:57.40,  vol:0.712, tipo:'call', pfx:'vl'},
  rx: {ticker:'ROXO34.SA',strike:10.50,  vol:0.315, tipo:'call', pfx:'rx'},
  bb: {ticker:'BBAS3.SA', strike:21.65,  vol:0.262, tipo:'call', pfx:'bb'},
};

async function loadBS(){
  const hoje=new Date();
  const datas={
    pt:new Date('2026-12-17'), vl:new Date('2027-02-18'),
    rx:new Date('2026-07-16'), bb:new Date('2026-08-20'),
  };
  for(const [key,cfg] of Object.entries(BS_PARAMS)){
    try{
      const dias=Math.max(1,Math.ceil((datas[key]-hoje)/864e5));
      const ctrl=new AbortController();setTimeout(()=>ctrl.abort(),12000);
      const r=await fetch(B+'/bs',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        signal:ctrl.signal,
        body:JSON.stringify({ticker:cfg.ticker,strike:cfg.strike,t_days:dias,vol_impl:cfg.vol,tipo:cfg.tipo})
      });
      if(!r.ok)continue;
      const d=await r.json();
      if(d.error)continue;
      const pfx=cfg.pfx;
      // Vol Impl
      const evol=document.getElementById(pfx+'-bs-vol');
      if(evol){evol.textContent=d.vol_impl_pct.toFixed(1)+'%';}
      // Delta
      const edel=document.getElementById(pfx+'-bs-delta');
      if(edel){edel.textContent=Math.abs(d.delta).toFixed(3);}
      // Prob B&S
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