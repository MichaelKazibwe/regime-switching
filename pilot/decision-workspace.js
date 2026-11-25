// Current proposal views consume a single server-owned context. Legacy research
// views retain their separately labelled historical identities.
const decisionWorkspace=(()=>{
  let payload=null,selected='aggregate',fetchedAt=0,pending=false,error=null;
  const pct=(v,n=1)=>Number.isFinite(v)?`${(v*100).toFixed(n)}%`:'Unavailable';
  const active=()=>payload?.portfolios[selected]||null;
  const palette={cash:'#7b879e',equity:'#7061d7',government:'#158679',credit:'#c58b27',real_assets:'#bc6576',alternative:'#4f8cad'};
  function metric(parent,label,value,note){const node=el('div',undefined,'decision-metric');node.append(el('span',label),el('strong',value));if(note)node.append(el('small',note));parent.append(node);}
  function bindContext(){
    const p=active();if(!p)return;const c=p.context;
    const dates=`${c.currency} · Prices ${c.price_as_of} · Context ${c.context_as_of} · Research proposal`;
    text('decision-title',p.title);text('decision-dates',dates);text('decision-analysis-title',p.title);text('decision-analysis-dates',dates);
    for(const node of document.querySelectorAll('.decision-view'))node.dataset.contextId=c.context_id;
    const metrics=$('decision-metrics');metrics.replaceChildren();
    metric(metrics,'Invested assets',String(p.asset_count),'Holding count follows the data');
    metric(metrics,'Uninvested cash',pct(p.cash),'Treasury funds remain invested assets');
    metric(metrics,'Estimated annual price swings',pct(p.estimated_volatility,2),'Model estimate, not a loss boundary');
    drawAllocation(p);renderAttention(p);renderChanges(p);renderAnalysis(p);
    const evidence=$('decision-evidence');evidence.replaceChildren();
    for(const [label,value] of [['Portfolio type',c.kind],['Price cutoff',c.price_as_of],['Market context',c.context_as_of],['Currency',c.currency],['Review state',c.approval_state],['Version',c.revision],['Context identity',c.context_id]]){const line=el('p');line.append(el('strong',label+': '),document.createTextNode(value));evidence.append(line);}
    for(const [label,value] of [['Model validation',payload.catalogue.model.independent_validation],['Responsible owner',payload.catalogue.model.owner],['Data rights',payload.catalogue.datasets.rights_qualification],['Independent securities reconciliation',payload.catalogue.datasets.independent_securities_reconciliation]]){const line=el('p');line.append(el('strong',label+': '),document.createTextNode(human(value)));evidence.append(line);}
    for(const limitation of p.limitations)evidence.append(el('p',limitation,'small muted'));
  }
  function drawAllocation(p){
    const svg=$('decision-allocation-chart'),legend=$('decision-allocation-legend');svg.replaceChildren();legend.replaceChildren();
    const ns='http://www.w3.org/2000/svg',circumference=2*Math.PI*72;let offset=0;
    const title=document.createElementNS(ns,'title');title.textContent='Proposed capital allocation; no executed account holdings';svg.append(title);
    for(const [group,weight] of Object.entries(p.group_weights)){
      if(weight<=0)continue;const circle=document.createElementNS(ns,'circle');
      for(const [name,value] of Object.entries({cx:110,cy:110,r:72,fill:'none',stroke:palette[group]||'#7b879e','stroke-width':28,'stroke-dasharray':`${weight*circumference} ${circumference}`,'stroke-dashoffset':-offset*circumference,transform:'rotate(-90 110 110)'}))circle.setAttribute(name,String(value));
      svg.append(circle);offset+=weight;
      const row=el('div',undefined,'decision-legend-row'),swatch=el('span',undefined,'decision-swatch');swatch.style.background=palette[group]||'#7b879e';swatch.setAttribute('aria-hidden','true');row.append(swatch,el('span',({cash:'Uninvested cash',equity:'Shares',government:'Government bonds',credit:'Corporate credit',real_assets:'Real assets',alternative:'Alternative strategies'})[group]||human(group)),el('strong',pct(weight)));legend.append(row);
    }
    const label=document.createElementNS(ns,'text');label.setAttribute('x','110');label.setAttribute('y','106');label.setAttribute('text-anchor','middle');label.setAttribute('class','decision-donut-title');label.textContent=String(p.asset_count);svg.append(label);
    const sub=document.createElementNS(ns,'text');sub.setAttribute('x','110');sub.setAttribute('y','130');sub.setAttribute('text-anchor','middle');sub.textContent='invested assets';svg.append(sub);
  }
  function renderAttention(p){
    const list=$('decision-attention');list.replaceChildren();
    const id=p.context.revision+':'+p.horizon;
    const review=payload.review_history.find(r=>r.recommendation_id===id&&r.recommendation_revision===p.review_revision);
    const rows=[
      ['Research review',review?human(review.decision)+' · '+review.recorded_at.slice(0,10):'Awaiting your research decision'],
      ['Underlying diversification',p.exposure_evidence.status==='PASS'?'Reviewed coverage and stated limits pass':'Holdings look-through is not fully qualified'],
      ['Forecast evidence','Future forecasting advantage is not established'],
    ];
    for(const [title,description] of rows){const row=el('div',undefined,'decision-attention-row');row.append(el('strong',title),el('p',description,'small muted'));list.append(row);}
    $('decision-review').textContent=payload.role==='viewer'?'Inspect proposal →':'Review this proposal →';
  }
  function renderChanges(p){
    const node=$('decision-changes'),diff=p.comparison;node.replaceChildren();
    text('decision-change-date',diff.previous_price_as_of?'Compared with '+diff.previous_price_as_of:'');
    if(diff.status==='UNCHANGED_ALLOCATION'){node.append(el('p','Target weights are unchanged from the previous comparable proposal.'));if(diff.risk_estimate_changed)node.append(el('p','Risk estimates changed; review the updated model evidence.','small muted'));return;}
    if(diff.status!=='ALLOCATION_CHANGED'){node.append(el('p',diff.status==='PRIOR_EVIDENCE_UNAVAILABLE'?'Prior comparison evidence is unavailable. Current weights remain visible.':'No comparable prior model version is available. A new revision alone is not a rebalance.'));return;}
    for(const row of diff.changes.slice(0,6)){const line=el('div',undefined,'decision-change-row');line.append(el('strong',row.symbol),el('span',pct(row.previous_weight,2)+' → '+pct(row.proposed_weight,2)),el('span',(row.delta>=0?'+':'')+pct(row.delta,2)));node.append(line);}
    if(diff.changes.length>6)node.append(el('p',`${diff.changes.length-6} further changes are available in the full portfolio evidence.`,'small muted'));
  }
  function renderAnalysis(p){
    const bars=$('decision-risk-bars');bars.replaceChildren();
    const holdings=p.allocations.filter(r=>r.symbol!=='USD_CASH'&&r.weight>0).sort((a,b)=>b.risk_share-a.risk_share);
    const scale=Math.max(.35,...holdings.map(r=>Math.abs(r.risk_share)));
    for(const row of holdings){const line=el('div',undefined,'decision-risk-row'),track=el('div',undefined,'decision-risk-track'),bar=el('span');bar.style.width=Math.min(100,Math.abs(row.risk_share)/scale*100)+'%';bar.className=row.risk_share<0?'hedge':'';track.append(bar);line.append(el('span',row.symbol),track,el('strong',pct(row.risk_share,2)+(row.risk_share<0?' · hedge':'')));bars.append(line);}
    const stress=$('decision-stresses');stress.replaceChildren();for(const [name,value] of Object.entries(p.shocks)){const row=el('div',undefined,'decision-change-row');row.append(el('span',name),el('strong',pct(value,2)));stress.append(row);}
    const e=p.exposure_evidence;text('decision-coverage',e.covered_risky_fraction===null||e.covered_risky_fraction===undefined?'Verified underlying holdings have not been supplied. Listing country is not underlying exposure.':`${pct(e.covered_risky_fraction)} of risky capital covered · ${human(e.status)}. Coverage is not execution approval.`);
    const projection=p.projections.periods[$('decision-period').value],cards=$('decision-projection');cards.replaceChildren();
    if(projection){metric(cards,'5th / median / 95th scenario return',[projection.p05_return,projection.median_return,projection.p95_return].map(v=>pct(v,2)).join(' / '));metric(cards,'Sampled paths ending below entry',pct(projection.loss_frequency),'Simulation frequency, not a calibrated probability');metric(cards,'95th scenario drawdown',pct(projection.p95_drawdown,2),'Losses can exceed modeled scenarios');}
    text('decision-projection-note',projection?`Selected period: ${projection.weeks} weeks. Current target weights held through resampled scenarios; modeled turnover fees, zero residual cash yield and no tax.`:'Projection unavailable for this period.');
    const history=$('decision-history');history.replaceChildren(el('p',`Causal historical replay: ${pct(p.replay.total_return,2)} return; ${pct(p.replay.max_drawdown,2)} maximum weekly-close drawdown. Historical research, not an account track record.`),el('p',p.methodology,'small muted'));
  }
  async function load(force=false){
    if(pending||(!force&&payload&&Date.now()-fetchedAt<60000)){bindContext();return;}
    pending=true;
    try{const response=await fetch('/api/workspace',{signal:AbortSignal.timeout(20000)});if(!response.ok)throw Error('Verified proposals unavailable');const next=await response.json();if(next.execution_enabled!==false||next.schema_version!==1)throw Error('Unexpected portfolio context');payload=next;fetchedAt=Date.now();error=null;
      const options=$('decision-portfolio');options.replaceChildren();for(const [key,p] of Object.entries(payload.portfolios)){const o=el('option',p.title);o.value=key;options.append(o);}if(!payload.portfolios[selected])selected=payload.default_horizon;options.value=selected;bindContext();
    }catch(_){error='Update unavailable';}
    finally{pending=false;const status=error?(payload?'Update failed · retaining the last verified proposal.':'Verified current proposals are unavailable. Research history remains available in the library.'):(payload.stale?'STALE · a newer completed session or week is awaiting publication.':payload.update_error?'Update failed · retaining the last verified market context.':'Verified research proposal · client review required · no orders');text('decision-status',status);text('decision-analysis-status',status);}
  }
  $('decision-portfolio').addEventListener('change',()=>{selected=$('decision-portfolio').value;bindContext();});
  $('decision-period').addEventListener('change',()=>{if(active())renderAnalysis(active());});
  $('decision-analyze').addEventListener('click',()=>view('proposal-analysis'));
  $('decision-analysis-home').addEventListener('click',()=>view('decision-home'));
  $('decision-review').addEventListener('click',async()=>{if(!active())return;view('weekly');$('weekly-horizon').value=selected;weeklyResearch=null;await renderWeeklyResearch();$('weekly-review-submit').closest('article').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});
  document.addEventListener('regime:review-recorded',()=>load(true));
  document.addEventListener('regime:view-changed',event=>{if(['decision-home','proposal-analysis'].includes(event.detail.name))load();});
  $('weekly-horizon').addEventListener('change',()=>{if(payload?.portfolios[$('weekly-horizon').value])selected=$('weekly-horizon').value;});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&['#decision-home','#proposal-analysis'].includes(location.hash))load();});
  setInterval(()=>{if(!document.hidden&&['#decision-home','#proposal-analysis'].includes(location.hash))load();},60000);
  if(['#decision-home','#proposal-analysis'].includes(location.hash))load();
  return {refresh:()=>load(true)};
})();
