const $ = id => document.getElementById(id);
let state = JSON.parse($("dashboard-data").textContent);
let quotes = new Map(), selected = "SPY", marketRange = "3M", performanceRange = "ALL";
let history = null, historySequence = 0, refreshing = false;
const colors = ["#008775", "#8174bd", "#5489b5", "#c29a50", "#77a6a3", "#a0aab8"];
const numeric = value => typeof value === "number" && Number.isFinite(value) ? value : null;
const money = value => numeric(value) === null ? "—" : new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",maximumFractionDigits:2}).format(value);
const plain = value => numeric(value) === null ? "—" : new Intl.NumberFormat("en-US", {maximumFractionDigits:2}).format(value);
const percent = (value, signed = false) => numeric(value) === null ? "—" : new Intl.NumberFormat("en-US", {style:"percent",maximumFractionDigits:2,minimumFractionDigits:2,signDisplay:signed?"exceptZero":"auto"}).format(value);
const date = value => {const stamp = new Date(value); return value && Number.isFinite(stamp.getTime()) ? stamp.toLocaleDateString("en-GB", {day:"2-digit",month:"short",year:"numeric",timeZone:"America/New_York"}) : "—";};
const time = value => {const stamp = new Date(value); return value && Number.isFinite(stamp.getTime()) ? stamp.toLocaleString("en-GB", {day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit",timeZone:"America/New_York"}) + " NY" : "—";};
const metrics = report => report?.decision?.paper_execution?.operator_metrics || {};
const asset = symbol => state.assets.find(item => item.symbol === symbol) || {symbol,name:symbol,group:"Other"};
const title = value => String(value || "Unobserved").toLowerCase().replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
const node = (tag, text, className) => {const item = document.createElement(tag); if(text !== undefined) item.textContent = text; if(className) item.className = className; return item;};
function tone(item, value) {item.classList.remove("positive","negative"); if(numeric(value)!==null && value!==0) item.classList.add(value>0?"positive":"negative");}
function empty(target, headline, detail, icon = "⌁") {target.replaceChildren(); const box=node("div",undefined,"empty-state"); box.append(node("span",icon,"empty-icon"),node("strong",headline),node("p",detail)); target.append(box);}
function tableEmpty(target, columns, message) {const row=node("tr"), cell=node("td",message,"empty-cell"); cell.colSpan=columns; row.append(cell); target.replaceChildren(row);}
function notify(message) {$("message").textContent=message || ""; $("message").hidden=!message;}
function iconClass(group) {return /income|Credit/.test(group)?"bond":/Real/.test(group)?"real":"";}
function assetIdentity(symbol) {const meta=asset(symbol), wrap=node("div",undefined,"holding-asset"), label=node("div"); label.append(node("strong",symbol),node("small",meta.name)); wrap.append(node("span",symbol.slice(0,2),"asset-icon "+iconClass(meta.group)),label); return wrap;}
function currentRecord() {return state.reports.find(report => numeric(metrics(report).portfolio_value)!==null);}

function renderMetrics() {
  const report=currentRecord(), m=metrics(report), latest=state.reports[0];
  $("nav-value").textContent=money(m.portfolio_value);
  $("nav-caption").textContent=report?"Saved account · "+plain(m.valuation_observations)+" valuation observations":"Awaiting the first paper valuation";
  $("valuation-date").textContent=date(report?.data_as_of);
  $("return-value").textContent=percent(m.cumulative_return_since_start,true); tone($("return-value"),m.cumulative_return_since_start);
  $("active-value").textContent=percent(m.active_return_since_start,true); tone($("active-value"),m.active_return_since_start);
  $("drawdown-value").textContent=percent(m.maximum_drawdown_since_start); tone($("drawdown-value"),m.maximum_drawdown_since_start);
  $("cost-value").textContent=money(m.cumulative_transaction_costs);
  const decision=state.reports.find(item => item.decision?.regime);
  $("regime-value").textContent=title(decision?.decision?.regime);
  $("regime-caption").textContent=decision?"Last recorded decision · "+date(decision.data_as_of):"A saved decision establishes market context";
  $("cycle-status").textContent=latest?.status || "No cycles";
  $("cycle-status").className=latest?.status==="APPROVED"?"positive":latest?"negative":"";
  $("benchmark-label").textContent=m.benchmark || "Benchmark";
}

function renderWatchlist() {
  const query=$("market-search").value.toLowerCase(), target=$("watchlist"); target.replaceChildren();
  const matches=state.assets.filter(item => (item.symbol+" "+item.name+" "+item.group).toLowerCase().includes(query));
  for(const item of matches) {
    const quote=quotes.get(item.symbol), button=node("button",undefined,"watch-row"+(item.symbol===selected?" active":""));
    button.setAttribute("aria-label",`Show ${item.symbol} ${item.name} chart`); button.setAttribute("aria-pressed",String(item.symbol===selected));
    const identity=node("div",undefined,"watch-identity"), prices=node("div",undefined,"watch-prices");
    identity.append(node("strong",item.symbol),node("small",item.name));
    const change=node("small",percent(quote?.change_pct,true)); tone(change,quote?.change_pct);
    prices.append(node("strong",money(quote?.price)),change);
    button.append(node("span",item.symbol.slice(0,2),"asset-icon "+iconClass(item.group)),identity,prices);
    button.addEventListener("click",()=>selectAsset(item.symbol)); target.append(button);
  }
  if(!matches.length) target.append(node("p","No assets match your search.","empty-cell"));
}
function renderSelected() {
  const meta=asset(selected), quote=quotes.get(selected);
  $("asset-select").value=selected; $("asset-description").textContent=meta.name;
  $("selected-price").textContent=money(quote?.price);
  $("selected-change").textContent=numeric(quote?.change_pct)===null?"Day change unavailable":percent(quote.change_pct,true)+" vs prior close";
  tone($("selected-change"),quote?.change_pct);
  $("quote-asof").textContent=quote?.as_of?"Bar as of "+time(quote.as_of):"No quote received";
  $("chart-symbol").textContent=selected;
}
function selectAsset(symbol) {selected=symbol;renderSelected();renderWatchlist();loadHistory();}

const svgNode = (tag, attrs={}) => {const item=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const [key,value] of Object.entries(attrs)) item.setAttribute(key,String(value));return item;};
function drawChart(target, definitions, formatValue, emptyHeadline, emptyDetail) {
  const series=definitions.map(def => ({...def,points:def.points.filter(p=>numeric(p.value)!==null && Number.isFinite(Date.parse(p.time))).sort((a,b)=>Date.parse(a.time)-Date.parse(b.time))})).filter(def=>def.points.length);
  if(!series.length) {empty(target,emptyHeadline,emptyDetail);return;}
  target.replaceChildren();
  const width=Math.max(target.clientWidth,250), height=Math.max(target.clientHeight,180), left=12, right=66, top=20, bottom=31;
  const chartWidth=width-left-right, chartHeight=height-top-bottom, all=series.flatMap(def=>def.points), stamps=all.map(p=>Date.parse(p.time));
  const minX=Math.min(...stamps), maxX=Math.max(...stamps), values=all.map(p=>p.value), minV=Math.min(...values), maxV=Math.max(...values), pad=(maxV-minV)*.16 || Math.max(Math.abs(maxV)*.02,.01);
  const minY=minV-pad,maxY=maxV+pad, x=stamp=>maxX===minX?left+chartWidth/2:left+(stamp-minX)/(maxX-minX)*chartWidth, y=value=>top+(maxY-value)/(maxY-minY)*chartHeight;
  const svg=svgNode("svg",{viewBox:`0 0 ${width} ${height}`,role:"img","aria-label":target.getAttribute("aria-label") || "Historical chart"});
  const description=svgNode("desc");description.textContent=series.map(def=>`${def.name}: ${def.points.length} observations; latest ${formatValue(def.points.at(-1).value)}`).join(". ");svg.append(description);
  for(let index=0;index<5;index++) {const value=minY+(maxY-minY)*index/4, pos=y(value); svg.append(svgNode("line",{x1:left,x2:left+chartWidth,y1:pos,y2:pos,class:"grid"}));const label=svgNode("text",{x:width-right+12,y:pos+3});label.textContent=formatValue(value);svg.append(label);}
  const ticks=minX===maxX?[minX]:[minX,(minX+maxX)/2,maxX];
  ticks.forEach((stamp,index)=>{const label=svgNode("text",{x:x(stamp),y:height-7,"text-anchor":index===0?"start":index===ticks.length-1?"end":"middle"});label.textContent=new Date(stamp).toLocaleDateString("en-GB",{day:"2-digit",month:"short",timeZone:"America/New_York"});if(maxX-minX<86400000) label.textContent=new Date(stamp).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit",timeZone:"America/New_York"});svg.append(label);});
  series.forEach((def,index)=>{
    const path=def.points.map((point,i)=>(i?"L":"M")+x(Date.parse(point.time)).toFixed(2)+","+y(point.value).toFixed(2)).join(" ");
    if(index===0 && def.points.length>1) {const id="gradient-"+target.id, defs=svgNode("defs"), gradient=svgNode("linearGradient",{id,x1:"0",y1:"0",x2:"0",y2:"1"});gradient.append(svgNode("stop",{offset:"0%","stop-color":def.color,"stop-opacity":.14}),svgNode("stop",{offset:"100%","stop-color":def.color,"stop-opacity":0}));defs.append(gradient);svg.append(defs,svgNode("path",{d:path+` L${x(Date.parse(def.points.at(-1).time))},${top+chartHeight} L${x(Date.parse(def.points[0].time))},${top+chartHeight} Z`,fill:`url(#${id})`}));}
    svg.append(svgNode("path",{d:path,fill:"none",stroke:def.color,"stroke-width":2,"stroke-linejoin":"round","stroke-linecap":"round"}));
    if(def.points.length===1) svg.append(svgNode("circle",{cx:x(Date.parse(def.points[0].time)),cy:y(def.points[0].value),r:4,fill:def.color}));
  });
  const crosshair=svgNode("line",{x1:0,x2:0,y1:top,y2:height-bottom,class:"crosshair",visibility:"hidden"});svg.append(crosshair);
  const tooltip=node("div",undefined,"chart-tooltip");tooltip.hidden=true;
  const interaction=svgNode("rect",{x:left,y:top,width:chartWidth,height:chartHeight,fill:"transparent",tabindex:"0","aria-label":"Move pointer to inspect historical values"});
  function inspectAt(ratio) {const stamp=minX+ratio*(maxX-minX), anchor=series[0].points.reduce((best,p)=>Math.abs(Date.parse(p.time)-stamp)<Math.abs(Date.parse(best.time)-stamp)?p:best);crosshair.setAttribute("x1",x(Date.parse(anchor.time)));crosshair.setAttribute("x2",x(Date.parse(anchor.time)));crosshair.setAttribute("visibility","visible");tooltip.replaceChildren(node("span",time(anchor.time)));for(const def of series) {const point=def.points.reduce((best,p)=>Math.abs(Date.parse(p.time)-Date.parse(anchor.time))<Math.abs(Date.parse(best.time)-Date.parse(anchor.time))?p:best);const line=node("strong",`${def.name}  ${formatValue(point.value)}`);line.style.color=def.color;tooltip.append(line);}tooltip.hidden=false;tooltip.style.left=Math.max(3,Math.min(x(Date.parse(anchor.time))+12,width-tooltip.offsetWidth-5))+"px";}
  interaction.addEventListener("pointermove",event=>{const bounds=svg.getBoundingClientRect();inspectAt(Math.max(0,Math.min(1,(event.clientX-bounds.left-left)/chartWidth)));});
  interaction.addEventListener("pointerleave",()=>{tooltip.hidden=true;crosshair.setAttribute("visibility","hidden");});
  interaction.addEventListener("focus",()=>inspectAt(1));interaction.addEventListener("blur",()=>{tooltip.hidden=true;crosshair.setAttribute("visibility","hidden");});
  let keyboardRatio=1;interaction.addEventListener("keydown",event=>{if(["ArrowLeft","ArrowRight"].includes(event.key)){event.preventDefault();keyboardRatio=Math.max(0,Math.min(1,keyboardRatio+(event.key==="ArrowLeft"?-1:1)/Math.max(1,series[0].points.length-1)));inspectAt(keyboardRatio);}});
  svg.append(interaction);target.append(svg,tooltip);
}
const cssColor = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
function renderMarketChart() {drawChart($("market-chart"),history?[{name:selected,color:cssColor("--teal"),points:history.points || []}]:[],value=>"$"+plain(value),"Market history is not available yet","Provider observations will appear here when the market connection is available.");}
function renderPerformance() {
  let reports=state.reports.filter(report=>numeric(metrics(report).cumulative_return_since_start)!==null && report.data_as_of).slice().reverse();
  if(performanceRange!=="ALL" && reports.length){const last=Date.parse(reports.at(-1).data_as_of),days=performanceRange==="1M"?31:93;reports=reports.filter(report=>Date.parse(report.data_as_of)>=last-days*86400000);}
  const unique=new Map(reports.map(report=>[report.data_as_of,report]));reports=[...unique.values()];
  drawChart($("performance-chart"),[
    {name:"Portfolio",color:cssColor("--teal"),points:reports.map(report=>({time:report.data_as_of,value:metrics(report).cumulative_return_since_start}))},
    {name:metrics(currentRecord()).benchmark||"Benchmark",color:cssColor("--purple"),points:reports.map(report=>({time:report.data_as_of,value:metrics(report).benchmark_return_since_first_observation}))}
  ],value=>(value*100).toFixed(1)+"%","Your performance record starts here","A saved paper cycle establishes the first observation. Returns are never simulated for display.");
}

function renderAllocation() {
  const m=metrics(currentRecord()), positions=m.positions_by_market_value || {}, groups=new Map();
  $("allocation-chart").replaceChildren();$("allocation-legend").replaceChildren();
  const values=Object.entries(positions).filter(([,position])=>numeric(position.market_value)!==null);
  const valid=values.length && numeric(m.portfolio_value)!==null && m.portfolio_value>0 && numeric(m.cash)!==null && m.cash>=0 && values.every(([,position])=>position.market_value>=0);
  const svg=svgNode("svg",{viewBox:"0 0 180 180",role:"img","aria-label":"Saved capital allocation"});
  svg.append(svgNode("circle",{cx:90,cy:90,r:66,fill:"none",stroke:cssColor("--border"),"stroke-width":19}));
  const center=node("div",undefined,"donut-center");center.append(node("strong",valid?String(values.length):"—"),node("span",valid?"HOLDINGS":"AWAITING A CYCLE"));
  $("allocation-chart").append(svg,center);
  if(!valid){$("allocation-legend").append(node("p",values.length?"Allocation chart requires nonnegative capital values. Review the holdings table.":"The first saved valuation will reveal allocation across asset classes.","subtle"));return;}
  for(const [symbol,position] of values) {const group=asset(symbol).group;groups.set(group,(groups.get(group)||0)+position.market_value);}
  if(m.cash>0) groups.set("Cash reserve",m.cash);
  const total=[...groups.values()].reduce((sum,value)=>sum+value,0), circumference=2*Math.PI*66;let offset=0;
  [...groups.entries()].sort((a,b)=>b[1]-a[1]).forEach(([group,value],index)=>{
    const fraction=value/total,color=colors[index%colors.length];
    svg.append(svgNode("circle",{cx:90,cy:90,r:66,fill:"none",stroke:color,"stroke-width":19,"stroke-dasharray":`${fraction*circumference} ${circumference}`,"stroke-dashoffset":-offset,transform:"rotate(-90 90 90)"}));offset+=fraction*circumference;
    const row=node("div",undefined,"allocation-item"),dot=node("span",undefined,"legend-dot");dot.style.background=color;row.append(dot,node("span",group),node("strong",percent(value/m.portfolio_value)));$("allocation-legend").append(row);
  });
}

function renderHoldings() {
  const target=$("holdings-body"), positions=metrics(currentRecord()).positions_by_market_value || {}, entries=Object.entries(positions).sort((a,b)=>(numeric(b[1].market_value)||0)-(numeric(a[1].market_value)||0));
  $("holdings-count").textContent=entries.length;target.replaceChildren();
  if(!entries.length){tableEmpty(target,6,"No saved holdings yet. Positions will appear after a completed paper cycle.");return;}
  for(const [symbol,position] of entries) {const row=node("tr"),identity=node("td");identity.append(assetIdentity(symbol));row.append(identity,node("td",asset(symbol).group),node("td",plain(position.shares),"numeric"),node("td",money(position.market_value),"numeric"));const weight=node("td",undefined,"numeric"),track=node("span",undefined,"weight-track"),bar=node("i");bar.style.width=Math.max(0,Math.min(100,(numeric(position.weight)||0)*100))+"%";track.append(bar);weight.append(track,document.createTextNode(percent(position.weight)));row.append(weight,node("td",money(quotes.get(symbol)?.price),"numeric"));target.append(row);}
}
function filteredReports() {const query=$("cycle-search").value.toLowerCase(),status=$("status-filter").value;return state.reports.filter(report=>(status==="ALL" || report.status===status) && ((report.cycle_id || "")+" "+(report.decision?.regime || "")).toLowerCase().includes(query));}
function renderActivity() {
  const reports=filteredReports(),target=$("activity-body");target.replaceChildren();$("cycle-count").textContent=reports.length+" of "+state.reports.length+" cycles";$("export").disabled=!reports.length;
  if(!reports.length){tableEmpty(target,7,state.reports.length?"No cycles match the selected filters.":"No valid paper cycle reports found. Completed cycles will appear here with their recorded status.");return;}
  for(const report of reports) {const m=metrics(report),row=node("tr"),status=node("td"),badge=node("span",report.status || "UNKNOWN","status-badge "+String(report.status||"").toLowerCase());status.append(badge);row.append(node("td",report.cycle_id||"—"),status,node("td",title(report.decision?.regime)),node("td",time(report.data_as_of)),node("td",money(m.portfolio_value),"numeric"));const returns=node("td",percent(m.cumulative_return_since_start,true),"numeric");tone(returns,m.cumulative_return_since_start);row.append(returns,node("td",money(m.cumulative_transaction_costs),"numeric"));target.append(row);}
}
function renderState() {renderMetrics();renderWatchlist();renderSelected();renderPerformance();renderAllocation();renderHoldings();renderActivity();}
async function request(path) {const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),35000);try{const response=await fetch(path,{signal:controller.signal,cache:"no-store",credentials:"omit"});if(!response.ok) throw new Error("Data unavailable");return await response.json();}finally{clearTimeout(timer);}}
async function loadHistory() {
  const sequence=++historySequence;history=null;empty($("market-chart"),"Loading "+selected+" history","Fetching recorded market observations…");$("history-status").textContent="Fetching provider history…";
  try {const result=await request(`/api/history?symbol=${encodeURIComponent(selected)}&range=${marketRange}`);if(sequence!==historySequence)return;history=result.available?result:null;renderMarketChart();$("history-status").textContent=result.available?(result.stale?"Cached history · provider unavailable":`${result.points?.length || 0} observations · ${result.interval} bars`):"Provider unavailable · retrying automatically";}
  catch{if(sequence!==historySequence)return;renderMarketChart();$("history-status").textContent="Market connection unavailable";}
}
async function refresh() {
  if(refreshing)return;refreshing=true;$("refresh").disabled=true;$("refresh").setAttribute("aria-busy","true");
  const stateRequest=request("/api/state").then(result=>{state=result;renderState();$("session-status").textContent=result.market_open?"NYSE market open":"NYSE market closed";$("session-dot").className="status-dot"+(result.market_open?"":" neutral");}).catch(()=>{$("session-status").textContent="Saved dashboard view";});
  const quoteRequest=request("/api/quotes").then(result=>{
    if(result.available)quotes=new Map((result.quotes||[]).map(item=>[item.symbol,item]));
    renderWatchlist();renderSelected();renderHoldings();
    const newest=Math.max(...[...quotes.values()].filter(item=>item.as_of).map(item=>Date.parse(item.as_of)));
    const old=state.market_open && Number.isFinite(newest) && Date.now()-newest>15*60*1000;
    const label=result.stale || old?"Stale provider prices":result.partial?"Partial provider coverage":"Provider prices · 5-minute bars · may be delayed";
    $("feed-status").textContent=result.available?label+" · fetched "+time(result.fetched_at):"Market provider unavailable";
    notify(result.stale?result.error:old?"Provider bars are older than 15 minutes during the market session. Saved portfolio values remain unchanged.":result.partial?"Some assets have no current provider quote. Missing prices are shown as dashes.":"");
  }).catch(()=>{$("feed-status").textContent="Market connection offline";notify("Market prices are unavailable. You can continue reviewing saved paper records; prices will retry automatically.");});
  await Promise.allSettled([stateRequest,quoteRequest,loadHistory()]);refreshing=false;$("refresh").disabled=false;$("refresh").setAttribute("aria-busy","false");
}

for(const meta of state.assets) {const option=node("option",meta.symbol);option.value=meta.symbol;$("asset-select").append(option);}
$("asset-select").addEventListener("change",event=>selectAsset(event.target.value));
$("market-search").addEventListener("input",renderWatchlist);$("cycle-search").addEventListener("input",renderActivity);$("status-filter").addEventListener("change",renderActivity);
function rangeControls(id,select) {for(const button of $(id).querySelectorAll("button")) {button.setAttribute("aria-pressed",String(button.classList.contains("selected")));button.addEventListener("click",()=>{for(const peer of $(id).querySelectorAll("button")){peer.classList.toggle("selected",peer===button);peer.setAttribute("aria-pressed",String(peer===button));}select(button.dataset.range);});}}
rangeControls("market-ranges",range=>{marketRange=range;loadHistory();});rangeControls("performance-ranges",range=>{performanceRange=range;renderPerformance();});
$("refresh").addEventListener("click",refresh);
$("export").addEventListener("click",()=>{
  const escape=value=>'"'+String(typeof value==="string" && /^[=+\-@\t\r]/.test(value)?"'"+value:value??"").replaceAll('"','""')+'"';
  const rows=[["Cycle","Status","Regime","Data as of","Portfolio value","Cumulative return","Cumulative costs"],...filteredReports().map(report=>[report.cycle_id,report.status,report.decision?.regime,report.data_as_of,metrics(report).portfolio_value,metrics(report).cumulative_return_since_start,metrics(report).cumulative_transaction_costs])];
  const blob=new Blob(["\ufeff"+rows.map(row=>row.map(escape).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob),link=node("a");link.href=url;link.download="regime-paper-cycles.csv";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
for(const link of document.querySelectorAll(".nav-link")) link.addEventListener("click",()=>{for(const peer of document.querySelectorAll(".nav-link"))peer.classList.toggle("active",peer===link);document.querySelector(".breadcrumb strong").textContent=link.hash==="#overview"?"Overview":link.hash==="#markets"?"Markets":link.hash==="#portfolio"?"Portfolio":"Cycle history";});
try{document.documentElement.dataset.theme=localStorage.getItem("regime-theme") || "light";}catch{}
$("theme-toggle").addEventListener("click",()=>{const theme=document.documentElement.dataset.theme==="dark"?"light":"dark";document.documentElement.dataset.theme=theme;try{localStorage.setItem("regime-theme",theme);}catch{}renderMarketChart();renderPerformance();renderAllocation();});
function clock() {$("local-clock").textContent=new Date().toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit",second:"2-digit",timeZone:"Europe/Warsaw"});}clock();setInterval(clock,1000);
let resizeTimer;const resize=new ResizeObserver(()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{renderMarketChart();renderPerformance();},100);});resize.observe($("market-chart"));resize.observe($("performance-chart"));
renderState();refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
