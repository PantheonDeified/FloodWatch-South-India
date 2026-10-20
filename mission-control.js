(function(){
'use strict';
const bridge=window.FloodWatchBridge;
if(!bridge||!bridge.map||!window.L)return;
const map=bridge.map;
const $=id=>document.getElementById(id);
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const escapeHTML=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const compass=d=>{if(!Number.isFinite(+d))return '—';return ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round((+d%360)/22.5)%16]};
const fmt=(n,d=1)=>Number.isFinite(+n)?(+n).toFixed(d):'—';
const setText=(id,value)=>{const el=$(id);if(el)el.textContent=value};
const state={hour:0,playing:false,timer:null,selection:null,weather:[],weatherKey:'',weatherAt:0,fieldScreen:[],particles:[],rain:[],dem:null,profile:{active:false,points:[],line:null,markers:[]},route:{line:null,markers:[]},compare:false,comparePct:50,beforeLayer:null,raf:0,lastFrame:0,canvas:null,ctx:null,profileLine:null,loadingField:false};
const host=document.querySelector('.mapcard');
if(!host)return;
const controls=document.createElement('div');
controls.id='fwMissionControls';
controls.innerHTML=
'<section class="fw-hud" aria-label="FloodWatch mission control">'+
'<div class="fw-hud-top"><div><span class="fw-kicker">FLOODWATCH / LIVE MODEL FEED</span><h2>Atmospheric telemetry</h2></div><span class="fw-pulse" aria-hidden="true"></span></div>'+
'<div id="fwFeedStatus" class="fw-feed-status">Loading local forecast grid…</div>'+
'<div class="fw-metric-grid">'+
'<div class="fw-metric"><span>Wind speed</span><b id="fwWind">—</b><small id="fwWindDir">Direction —</small></div>'+
'<div class="fw-metric"><span>Hourly rain</span><b id="fwRain">—</b><small id="fwRainProb">Precipitation —</small></div>'+
'<div class="fw-metric"><span>Surface soil moisture</span><b id="fwSoil">—</b><small>Modelled 0–7 cm · m³/m³</small></div>'+
'<div class="fw-metric"><span>Rain in last 24h</span><b id="fwRain24">—</b><small>Open-Meteo model estimate</small></div>'+
'</div>'+
'<div class="fw-hud-divider"></div>'+
'<div class="fw-hud-two">'+
'<div><span class="fw-label">Official nearby gauge</span><b id="fwGauge">Not available</b><small id="fwGaugeMeta">No recent qualified record</small></div>'+
'<div><span class="fw-label">Reservoir data</span><b id="fwDam">Not available</b><small id="fwDamMeta">Release/capacity not assumed</small></div>'+
'</div>'+
'<div class="fw-spark-head"><span>Next 24h rainfall forecast</span><span id="fwSparkTotal">—</span></div><svg id="fwRainSpark" class="fw-spark" viewBox="0 0 250 36" role="img" aria-label="Hourly modelled rainfall forecast sparkline"></svg>'+
'<div class="fw-smallnote" id="fwHudNote">Forecast values are model output; grey or missing means unknown, not safe.</div>'+
'<div class="fw-action-grid">'+
'<button type="button" id="fwParticles" class="fw-btn fw-btn-active">〰 Wind / rain particles</button>'+
'<button type="button" id="fwProfile" class="fw-btn">⌁ Cross-section</button>'+
'<button type="button" id="fwRoute" class="fw-btn">⇢ Find elevated shelter</button>'+
'<button type="button" id="fwCompare" class="fw-btn">◫ Before / after</button>'+
'</div>'+
'<div id="fwRouteStatus" class="fw-route-status" aria-live="polite">Select a map location before asking for candidate shelter routes.</div>'+
'</section>'+
'<section class="fw-playback" aria-label="24-hour forecast playback">'+
'<div class="fw-playback-head"><span>FORECAST PLAYBACK</span><b id="fwTimeValue">Now · T+0h</b><button type="button" id="fwPlay" class="fw-play">▶ Play</button></div>'+
'<input id="fwTimeline" type="range" min="0" max="24" step="1" value="0" aria-label="Forecast hour from now">'+
'<div class="fw-timeline-labels"><span>NOW</span><span>+6h</span><span>+12h</span><span>+18h</span><span>+24h</span></div>'+
'<div class="fw-playback-foot" id="fwScenarioLabel">Weather-grid colours use modelled rain. Terrain layer is static until a DEM is published.</div>'+
'<div class="fw-compare-control" id="fwCompareControl" hidden><label for="fwCompareRange">Swipe curtain · satellite baseline / live overlays</label><input id="fwCompareRange" type="range" min="10" max="90" value="50" aria-label="Before and after divider position"></div>'+
'</section>'+
'<section class="fw-profile-drawer" id="fwProfileDrawer" hidden>'+
'<div class="fw-drawer-head"><div><span class="fw-kicker">SRTM TERRAIN SAMPLE</span><h3>Elevation cross-section</h3></div><button type="button" id="fwCloseProfile" aria-label="Close elevation cross-section">×</button></div>'+
'<div class="fw-drawer-status" id="fwProfileStatus">Activate the tool and click two locations on the map.</div>'+
'<canvas id="fwProfileChart" width="700" height="150" aria-label="Terrain elevation profile chart"></canvas>'+
'<div class="fw-profile-input"><label for="fwReferenceWater">Optional hypothetical reference water elevation (m)</label><input id="fwReferenceWater" type="number" step="0.1" placeholder="Leave empty if unknown"><button type="button" id="fwRedrawProfile">Apply reference line</button></div>'+
'<div class="fw-smallnote">SRTM 90 m elevation is coarse terrain context, not a building-height survey. A reference line is user-entered and hypothetical; it is not a measured or projected water surface.</div>'+
'</section>';
document.querySelector('main').insertAdjacentElement('afterend',controls);
const mapReadouts=document.createElement('section');
mapReadouts.id='fwMapReadouts';
mapReadouts.setAttribute('aria-label','Map legend and location details');
mapReadouts.innerHTML='<div class="fw-readout-heading">MAP LEGEND &amp; LOCATION DETAILS</div><div class="fw-readout-grid"></div>';
controls.insertAdjacentElement('afterend',mapReadouts);
const readoutGrid=mapReadouts.querySelector('.fw-readout-grid');
[host.querySelector('.legend'),document.getElementById('ovLegend'),document.getElementById('hover')].forEach(el=>{if(el)readoutGrid.appendChild(el)});
const popupDock=document.createElement('section');
popupDock.className='fw-docked-popup';
popupDock.setAttribute('aria-live','polite');
popupDock.setAttribute('aria-label','Selected map feature details');
popupDock.hidden=true;
mapReadouts.insertBefore(popupDock,readoutGrid);
let movingPopupToDock=false;
map.on('popupopen',event=>{
 const element=event.popup&&event.popup.getElement();
 const source=element&&element.querySelector('.leaflet-popup-content');
 if(!source)return;
 popupDock.replaceChildren();
 Array.from(source.childNodes).forEach(node=>popupDock.appendChild(node.cloneNode(true)));
 popupDock.hidden=false;
 movingPopupToDock=true;
 map.closePopup(event.popup);
 movingPopupToDock=false;
});
map.on('popupclose',()=>{if(!movingPopupToDock)popupDock.hidden=true});
const hudCss = document.createElement('style');
hudCss.textContent = '';
document.head.appendChild(hudCss);
const canvas=document.createElement('canvas');
canvas.className='fw-particle-canvas';
canvas.setAttribute('aria-hidden','true');
map.getContainer().appendChild(canvas);
state.canvas=canvas;
state.ctx=canvas.getContext('2d',{alpha:true});
function updateCanvasSize(){
 const r=map.getContainer().getBoundingClientRect(),dpr=Math.min(2,window.devicePixelRatio||1);
 canvas.width=Math.max(1,Math.round(r.width*dpr));canvas.height=Math.max(1,Math.round(r.height*dpr));
 canvas.style.width=r.width+'px';canvas.style.height=r.height+'px';
 state.ctx.setTransform(dpr,0,0,dpr,0,0);
 state.fieldScreen=state.weather.map(w=>({x:map.latLngToContainerPoint([w.lat,w.lon]).x,y:map.latLngToContainerPoint([w.lat,w.lon]).y,w}));
 if(!state.particles.length)resetParticles();
 if(!state.rain.length)resetRain();
}
function resetParticles(){
 const w=map.getSize().x,h=map.getSize().y;
 state.particles=Array.from({length:210},()=>({x:Math.random()*w,y:Math.random()*h,age:Math.random()*80,life:45+Math.random()*85}));
 state.rain=Array.from({length:105},()=>({x:Math.random()*w,y:Math.random()*h,age:Math.random()*40}));
}
function nearestScreenCell(x,y){
 let best=null,dist=Infinity;
 for(const c of state.fieldScreen){const d=(c.x-x)*(c.x-x)+(c.y-y)*(c.y-y);if(d<dist){dist=d;best=c.w}}
 return best;
}
const hourIndexCache=new WeakMap();
function baseIndex(hourly){
 if(!hourly||!Array.isArray(hourly.time)||!hourly.time.length)return 0;
 const now=Date.now(),cached=hourIndexCache.get(hourly);
 if(cached&&now-cached.at<30000)return cached.index;
 let i=hourly.time.findIndex(t=>Date.parse(String(t)+'Z')>=now-10*60*1000);
 i=i<0?hourly.time.length-1:i;hourIndexCache.set(hourly,{index:i,at:now});return i;
}
function atHour(hourly,offset){
 if(!hourly)return null;
 const ix=baseIndex(hourly)+offset;
 const get=k=>Array.isArray(hourly[k])&&ix>=0&&ix<hourly[k].length&&hourly[k][ix]!=null&&Number.isFinite(+hourly[k][ix])?+hourly[k][ix]:null;
 return {time:hourly.time&&hourly.time[ix],rain:get('precipitation'),prob:get('precipitation_probability'),speed:get('wind_speed_10m'),dir:get('wind_direction_10m'),soil:get('soil_moisture_0_to_7cm')};
}
function pickWeather(lat,lon){
 let best=null,d=Infinity;
 for(const p of state.weather){const q=(p.lat-lat)*(p.lat-lat)*111*111+(p.lon-lon)*(p.lon-lon)*Math.cos(lat*Math.PI/180)**2*111*111;if(q<d){d=q;best=p}}
 return best;
}
function windFrame(){
 const ctx=state.ctx;if(!ctx)return;
 const w=map.getSize().x,h=map.getSize().y;
 ctx.globalCompositeOperation='destination-out';ctx.fillStyle='rgba(0,0,0,0.12)';ctx.fillRect(0,0,w,h);ctx.globalCompositeOperation='source-over';
 if(!state.weather.length){
   ctx.clearRect(0,0,w,h);
   if(!state.loadingField){ctx.fillStyle='rgba(15,23,42,.8)';ctx.font='12px monospace';ctx.fillText('Wind / precipitation field unavailable',12,20)}
   return;
 }
 if(!state.fieldScreen.length)updateCanvasSize();
 const dt=state.lastFrame?Math.min(.05,(performance.now()-state.lastFrame)/1000):.016;state.lastFrame=performance.now();
 for(const p of state.particles){
   const c=nearestScreenCell(p.x,p.y),v=atHour(c&&c.hourly,state.hour);
   if(!v||v.dir==null||v.speed==null){p.x=Math.random()*w;p.y=Math.random()*h;continue}
   const rad=(v.dir+180)*Math.PI/180,dx=Math.sin(rad),dy=-Math.cos(rad),spd=clamp(v.speed/45,.08,2.1);
   const len=5+spd*7;
   ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x-dx*len,p.y-dy*len);
   ctx.strokeStyle='rgba(112,224,255,'+(0.18+0.22*clamp(v.speed/60,0,1))+')';ctx.lineWidth=.7+spd*.25;ctx.stroke();
   p.x+=dx*(15+spd*48)*dt;p.y+=dy*(15+spd*48)*dt;p.age++;
   if(p.x<-20||p.x>w+20||p.y<-20||p.y>h+20||p.age>p.life){p.x=Math.random()*w;p.y=Math.random()*h;p.age=0;p.life=45+Math.random()*110}
 }
 for(const p of state.rain){
   const c=nearestScreenCell(p.x,p.y),v=atHour(c&&c.hourly,state.hour),rain=v&&v.rain;
   if(rain==null||rain<.08){p.y+=.9; if(p.y>h){p.y=0;p.x=Math.random()*w}continue}
   const intensity=clamp(rain/6,0,1),len=3+intensity*9;
   ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+1,p.y+len);
   ctx.strokeStyle='rgba(83,177,255,'+(0.05+intensity*.42)+')';ctx.lineWidth=.6+intensity*.5;ctx.stroke();
   p.y+=(45+intensity*140)*dt;p.x+=.5*dt;
   if(p.y>h){p.y=Math.random()*h*.15;p.x=Math.random()*w}
 }
}
function animate(t){
 state.raf=requestAnimationFrame(animate);
 if(t&&t-state.lastFrame<14)return;
 if(!$('fwParticles')||$('fwParticles').dataset.enabled!=='1')return;
 windFrame();
}
function weatherUrl(points){
 const lat=points.map(p=>p.lat.toFixed(3)).join(','),lon=points.map(p=>p.lon.toFixed(3)).join(',');
 return 'https://api.open-meteo.com/v1/forecast?latitude='+encodeURIComponent(lat)+'&longitude='+encodeURIComponent(lon)+
 '&hourly=precipitation,precipitation_probability,wind_speed_10m,wind_direction_10m,soil_moisture_0_to_7cm&forecast_days=2&timezone=UTC';
}
function gridForView(){
 const b=map.getBounds(),sw=b.getSouthWest(),ne=b.getNorthEast();
 let latCount=5,lonCount=6;
 if((ne.lat-sw.lat)>17)latCount=4;if((ne.lng-sw.lng)>22)lonCount=5;
 const pts=[];
 for(let i=0;i<latCount;i++)for(let j=0;j<lonCount;j++){
  const lat=sw.lat+(ne.lat-sw.lat)*(i+.5)/latCount,lon=sw.lng+(ne.lng-sw.lng)*(j+.5)/lonCount;
  pts.push({lat,lon});
 }
 return pts;
}
let fieldTimer=null,fieldEpoch=0;
async function loadWeatherField(force){
 if(state.loadingField)return;
 const pts=gridForView(),key=pts.map(p=>p.lat.toFixed(1)+','+p.lon.toFixed(1)).join(';');
 if(!force&&state.weatherKey===key&&Date.now()-state.weatherAt<15*60*1000)return;
 state.loadingField=true;const epoch=++fieldEpoch;
 setText('fwFeedStatus','Updating gridded forecast…');
 try{
  const r=await fetch(weatherUrl(pts),{cache:'no-store',headers:{Accept:'application/json'}});
  if(!r.ok)throw Error('Open-Meteo HTTP '+r.status);
  const payload=await r.json();const arr=Array.isArray(payload)?payload:[payload];
  if(epoch!==fieldEpoch)return;
  state.weather=arr.map((v,i)=>({lat:Number.isFinite(+v.latitude)?+v.latitude:pts[i].lat,lon:Number.isFinite(+v.longitude)?+v.longitude:pts[i].lon,hourly:v.hourly||null})).filter(v=>v.hourly&&Array.isArray(v.hourly.time));
  if(!state.weather.length)throw Error('Forecast response contains no hourly grid data');
  state.weatherKey=key;state.weatherAt=Date.now();updateCanvasSize();refreshHud();restyleDem();
  setText('fwFeedStatus','Forecast grid refreshed '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}));
 }catch(e){if(epoch===fieldEpoch)setText('fwFeedStatus','Weather grid unavailable: '+e.message+'. HUD will use selected-point data where possible.')}
 finally{
  if(epoch===fieldEpoch)state.loadingField=false;
  const latest=gridForView().map(p=>p.lat.toFixed(1)+','+p.lon.toFixed(1)).join(';');
  if(latest!==key)setTimeout(()=>loadWeatherField(false),500);
 }
}
function updateHud(){
 const sel=state.selection;
 const primary=sel&&sel.bundle&&sel.bundle.w&&sel.bundle.w.hourly;
 const point=primary?atHour(primary,state.hour):null;
 let weather=point;
 if(!weather&&state.weather.length){
  const c=pickWeather(map.getCenter().lat,map.getCenter().lng);weather=atHour(c&&c.hourly,state.hour);
 }
 if(weather){
  setText('fwWind',weather.speed==null?'—':fmt(weather.speed)+' km/h');
  setText('fwWindDir',weather.dir==null?'Direction —':'From '+compass(weather.dir)+' ('+Math.round(weather.dir)+'°)');
  setText('fwRain',weather.rain==null?'—':fmt(weather.rain)+' mm');
  setText('fwRainProb',weather.prob==null?'Probability —':'Rain chance '+Math.round(weather.prob)+'%');
  setText('fwSoil',weather.soil==null?'—':fmt(weather.soil,3)+' m³/m³');
  setText('fwTimeValue',(weather.time?new Date(String(weather.time)+'Z').toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',timeZone:'UTC'})+' UTC':'Forecast')+' · T+'+state.hour+'h');
 }else{
  ['fwWind','fwWindDir','fwRain','fwRainProb','fwSoil'].forEach(id=>setText(id,'—'));
  setText('fwTimeValue','Forecast unavailable · T+'+state.hour+'h');
 }
 const risk=sel&&sel.liveRisk;
 setText('fwRain24',risk&&risk.liveRainfall24h_mm!=null?fmt(risk.liveRainfall24h_mm)+' mm':'Unavailable');
 const g=risk&&risk.riverTelemetry;
 if(g&&Number.isFinite(+g.riverLevel)&&Number.isFinite(+g.riverDangerMark)){
  const diff=+g.riverLevel-(+g.riverDangerMark);
  setText('fwGauge',fmt(g.riverLevel)+' m · '+(diff>=0?'+':'')+fmt(diff)+' m vs danger');
  setText('fwGaugeMeta',String(g.stationName||'Gauge')+' · '+fmt(g.distanceKm)+' km · age '+fmt(g.ageMinutes,0)+' min');
 }else{
  setText('fwGauge','Not available');
  setText('fwGaugeMeta','No recent nearby gauge with danger mark');
 }
 const tel=risk&&risk.telemetry||{},parts=[];
 if(tel.damStoragePct!=null)parts.push('Storage '+fmt(tel.damStoragePct,0)+'%');
 if(typeof tel.damSpillwayActive==='boolean')parts.push('Gate/spillway '+(tel.damSpillwayActive?'active':'not reported active'));
 setText('fwDam',parts.length?parts.join(' · '):'Not available');
 setText('fwDamMeta','Dam release flow is not supplied for this point');
 const h=primary||(state.weather.length&&pickWeather(map.getCenter().lat,map.getCenter().lng)||{}).hourly;
 if(h){
  const start=baseIndex(h),vals=[];
  for(let k=0;k<24;k++){const v=h.precipitation&&h.precipitation[start+k];vals.push(Number.isFinite(+v)?Math.max(0,+v):0)}
  const max=Math.max(.1,...vals),sum=vals.reduce((a,b)=>a+b,0);
  const pts=vals.map((v,i)=>[(i/(Math.max(1,vals.length-1)))*246+2,32-(v/max)*27]);
  const path=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');
  $('fwRainSpark').innerHTML='<path d="'+path+'" fill="none" stroke="#55d9fa" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 34 H248" stroke="rgba(255,255,255,.2)" stroke-width="1"/>';
  setText('fwSparkTotal',fmt(sum)+' mm forecast');
 }else{$('fwRainSpark').innerHTML='';setText('fwSparkTotal','Unavailable')}
 setText('fwHudNote',sel?'Selected spot: '+fmt(sel.lat,3)+', '+fmt(sel.lon,3)+'. Gauge/dam data are latest available and do not advance with the weather scrubber.':'Select a point for location-specific gauge/rainfall context. Weather grid is regional and modelled.');
 setText('fwScenarioLabel',state.dem?'Terrain/rain scenario colours are a visualization only—not flood probability, extent or depth.':'Hourly rain tints visible contour/DEM layers where their data exists; this is an illustrative index, not simulated inundation.');
 if(typeof bridge.setScenario==='function')bridge.setScenario(state.hour,state.weather);
}
function refreshHud(){updateHud();restyleDem()}
function stopPlayback(){state.playing=false;if(state.timer)clearInterval(state.timer);state.timer=null;setText('fwPlay','▶ Play');$('fwPlay').classList.remove('fw-btn-active')}
function advanceHour(){state.hour=state.hour>=24?0:state.hour+1;$('fwTimeline').value=String(state.hour);updateHud();restyleDem()}
$('fwTimeline').addEventListener('input',e=>{state.hour=clamp(+e.target.value,0,24);updateHud();restyleDem()});
$('fwPlay').addEventListener('click',()=>{
 if(state.playing){stopPlayback();return}
 state.playing=true;$('fwPlay').textContent='Ⅱ Pause';$('fwPlay').classList.add('fw-btn-active');
 state.timer=setInterval(()=>{if(state.hour>=24)state.hour=-1;advanceHour()},500);
});
$('fwParticles').dataset.enabled='1';
$('fwParticles').addEventListener('click',()=>{
 const on=$('fwParticles').dataset.enabled!=='1';
 $('fwParticles').dataset.enabled=on?'1':'0';$('fwParticles').classList.toggle('fw-btn-active',on);
 $('fwParticles').textContent=on?'〰 Wind / rain particles':'〰 Particles paused';
 if(on){state.ctx.clearRect(0,0,map.getSize().x,map.getSize().y);state.lastFrame=0;if(!state.raf)state.raf=requestAnimationFrame(animate)}else{cancelAnimationFrame(state.raf);state.raf=0}
});
map.on('moveend zoomend',()=>{
 updateCanvasSize();
 clearTimeout(fieldTimer);fieldTimer=setTimeout(()=>loadWeatherField(false),800);
});
window.addEventListener('resize',updateCanvasSize);
window.addEventListener('floodwatch:location',e=>{
 const d=e.detail||{};
 if(!Number.isFinite(+d.lat)||!Number.isFinite(+d.lon))return;
 state.selection={lat:+d.lat,lon:+d.lon,name:d.name||'Selected location',bundle:d.bundle||null,liveRisk:d.liveRisk||null};
 state.hour=clamp(state.hour,0,24);$('fwTimeline').value=String(state.hour);
 setText('fwRouteStatus','Origin set to '+state.selection.name+'. Shelter capacity and route safety are not verified by this demo.');
 updateHud();
});
window.addEventListener('floodwatch:dem-layer',e=>{
 const d=e.detail||{};if(!d.layer)return;
 state.dem=d;prepareDemLayer();restyleDem();
});
bridge.onDemLayer=function(d){if(d&&d.layer){state.dem=d;prepareDemLayer();restyleDem()}};
function prepareDemLayer(){
 if(!state.dem||state.dem.prepared)return;
 state.dem.cache=[];
 state.dem.layer.eachLayer(l=>{
  const f=l.feature,p=f&&f.properties||{};
  let center=null;try{center=l.getBounds().getCenter()}catch(e){}
  state.dem.cache.push({layer:l,base:Number.isFinite(+p.hazard_index)?clamp(+p.hazard_index,0,1):null,center:center});
 });
 state.dem.prepared=true;
}
function restyleDem(){
 if(!state.dem||!state.dem.layer||!state.dem.cache)return;
 const sel=state.selection,grid=state.weather;
 for(const row of state.dem.cache){
  if(row.base==null)continue;
  let rain=0;
  let nearest=null,dist=Infinity;
  if(row.center&&grid.length){
   for(const w of grid){const d=(w.lat-row.center.lat)**2+(w.lon-row.center.lng)**2;if(d<dist){dist=d;nearest=w}}
  }
  const hour=atHour(nearest&&nearest.hourly,state.hour),selectedRain=sel&&sel.bundle&&sel.bundle.w&&atHour(sel.bundle.w.hourly,state.hour);
  const r=hour&&hour.rain!=null?hour.rain:(selectedRain&&selectedRain.rain!=null?selectedRain.rain:null);
  if(r!=null)rain=clamp(r/10,0,1);
  const display=.75*row.base+.25*rain;
  const color=display>=.75?'#d90429':display>=.55?'#f77f00':display>=.25?'#fcbf49':'#2ec4b6';
  row.layer.setStyle({fillColor:color,fillOpacity:.55,weight:.5,color:'#fff',opacity:.8});
 }
}
$('fwCompare').addEventListener('click',()=>{
 state.compare=!state.compare;$('fwCompare').classList.toggle('fw-btn-active',state.compare);
 $('fwCompareControl').hidden=!state.compare;
 if(state.compare){
  if(!state.beforeLayer){
   const pane=map.getPane('fwBeforePane')||map.createPane('fwBeforePane');pane.style.zIndex='350';
   state.beforeLayer=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{pane:'fwBeforePane',maxZoom:19,attribution:'Imagery © Esri and contributors'}).addTo(map);
  }else if(!map.hasLayer(state.beforeLayer))state.beforeLayer.addTo(map);
  applyCompare();
 }else clearCompare();
});
$('fwCompareRange').addEventListener('input',e=>{state.comparePct=+e.target.value;applyCompare()});
const curtain=document.createElement('div');curtain.id='fwCurtain';curtain.setAttribute('aria-hidden','true');map.getContainer().appendChild(curtain);
function paneLocalCurtain(pct,pane){
 if(!pane)return pct;
 pane.style.width='100%';pane.style.height='100%';
 const mapRect=map.getContainer().getBoundingClientRect(),r=pane.getBoundingClientRect();
 if(!r.width)return pct;
 return clamp((mapRect.left+mapRect.width*pct/100-r.left)/r.width*100,0,100);
}
function applyCompare(){
 if(!state.compare)return;
 const pct=state.comparePct,before=map.getPane('fwBeforePane');
 if(before){const cut=paneLocalCurtain(pct,before),style='inset(0 '+(100-cut)+'% 0 0)';before.style.clipPath=style;before.style.webkitClipPath=style}
 ['overlayPane','markerPane'].forEach(n=>{const p=map.getPane(n);if(p){const cut=paneLocalCurtain(pct,p),style='inset(0 0 0 '+cut+'%)';p.style.clipPath=style;p.style.webkitClipPath=style}});
 const right='inset(0 0 0 '+pct+'%)';canvas.style.clipPath=right;canvas.style.webkitClipPath=right;
 curtain.style.display='block';curtain.style.left=pct+'%';
}
function clearCompare(){
 ['overlayPane','markerPane'].forEach(n=>{const p=map.getPane(n);if(p){p.style.clipPath='';p.style.webkitClipPath='';p.style.width='';p.style.height=''}});
 const p=map.getPane('fwBeforePane');if(p){p.style.clipPath='';p.style.webkitClipPath='';p.style.width='';p.style.height=''}
 canvas.style.clipPath='';canvas.style.webkitClipPath='';
 if(state.beforeLayer&&map.hasLayer(state.beforeLayer))map.removeLayer(state.beforeLayer);
 curtain.style.display='none';
}
map.on('move zoom resize',()=>{if(state.compare)requestAnimationFrame(applyCompare)});
const originalClearCompare=clearCompare;
const enableProfile=()=>{
 state.profile.active=true;state.profile.points=[];$('fwProfileDrawer').hidden=false;
 $('fwProfile').classList.add('fw-btn-active');setText('fwProfileStatus','Click the FIRST point on the map.');
 map.getContainer().style.cursor='crosshair';
};
function clearProfileLayers(){
 if(state.profile.line){map.removeLayer(state.profile.line);state.profile.line=null}
 state.profile.markers.forEach(m=>map.removeLayer(m));state.profile.markers=[];
}
$('fwProfile').addEventListener('click',()=>{if(state.profile.active){state.profile.active=false;$('fwProfile').classList.remove('fw-btn-active');map.getContainer().style.cursor='';setText('fwProfileStatus','Tool paused. Click Cross-section to draw another line.')}else enableProfile()});
$('fwCloseProfile').addEventListener('click',()=>{$('fwProfileDrawer').hidden=true;state.profile.active=false;$('fwProfile').classList.remove('fw-btn-active');map.getContainer().style.cursor=''});
map.on('click',e=>{
 if(!state.profile.active)return;
 state.profile.points.push(e.latlng);
 state.profile.markers.push(L.circleMarker(e.latlng,{radius:5,color:'#9ee7ff',weight:2,fillColor:'#06101e',fillOpacity:1}).addTo(map));
 if(state.profile.points.length===1){setText('fwProfileStatus','Start recorded. Click the SECOND point.');return}
 const pts=state.profile.points.slice(0,2);state.profile.active=false;$('fwProfile').classList.remove('fw-btn-active');map.getContainer().style.cursor='';
 sampleElevationProfile(pts[0],pts[1]).catch(err=>setText('fwProfileStatus','Elevation profile failed: '+err.message+'. Try a shorter line or again later.'));
});
function distanceKm(a,b){
 const rad=x=>x*Math.PI/180,dLat=rad(b.lat-a.lat),dLon=rad(b.lng-a.lng),z=Math.sin(dLat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLon/2)**2;
 return 6371*2*Math.asin(Math.min(1,Math.sqrt(z)));
}
async function elevationSamples(coords){
 const loc=coords.map(p=>p.lat.toFixed(5)+','+p.lng.toFixed(5)).join('|');
 const r=await fetch('https://api.opentopodata.org/v1/srtm90m?locations='+encodeURIComponent(loc),{headers:{Accept:'application/json'}});
 if(!r.ok)throw Error('Elevation service HTTP '+r.status);
 const data=await r.json();
 if(data.status!=='OK'||!Array.isArray(data.results)||data.results.length!==coords.length)throw Error('Elevation response incomplete');
 return data.results.map((v,i)=>({distance:coords[i].distance,elevation:Number.isFinite(+v.elevation)?+v.elevation:null,lat:coords[i].lat,lng:coords[i].lng}));
}
async function sampleElevationProfile(a,b){
 clearProfileLayers();
 const km=distanceKm(a,b),n=clamp(Math.ceil(km/.5)+1,8,45),coords=[];
 for(let i=0;i<n;i++){const t=i/(n-1);coords.push({lat:a.lat+(b.lat-a.lat)*t,lng:a.lng+(b.lng-a.lng)*t,distance:km*t})}
 setText('fwProfileStatus','Requesting '+n+' SRTM elevation samples over '+fmt(km,2)+' km…');
 const values=await elevationSamples(coords);
 if(values.some(v=>v.elevation==null))throw Error('Some terrain elevations are missing; no profile plotted');
 state.profile.values=values;state.profile.line=L.polyline([a,b],{color:'#56e5ff',weight:3,dashArray:'8 6'}).addTo(map);
 drawProfile();
 setText('fwProfileStatus','Loaded SRTM 90 m samples · '+fmt(km,2)+' km. Elevation is approximate and not a flood-depth model.');
}
function drawProfile(){
 const c=$('fwProfileChart'),ctx=c.getContext('2d'),vals=state.profile.values;
 if(!vals||!vals.length)return;
 const w=c.width,h=c.height,pad={l:44,r:10,t:12,b:24},mn=Math.min(...vals.map(v=>v.elevation)),mx=Math.max(...vals.map(v=>v.elevation)),span=Math.max(1,mx-mn),ref=$('fwReferenceWater').value.trim();
 const y=v=>h-pad.b-(v-mn)/span*(h-pad.t-pad.b),x=i=>pad.l+i/(vals.length-1)*(w-pad.l-pad.r);
 ctx.clearRect(0,0,w,h);ctx.fillStyle='#081321';ctx.fillRect(0,0,w,h);
 ctx.strokeStyle='rgba(255,255,255,.12)';ctx.lineWidth=1;
 for(let i=0;i<4;i++){const yy=pad.t+i*(h-pad.t-pad.b)/3;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke()}
 ctx.beginPath();vals.forEach((v,i)=>i?ctx.lineTo(x(i),y(v.elevation)):ctx.moveTo(x(i),y(v.elevation)));
 ctx.lineTo(x(vals.length-1),h-pad.b);ctx.lineTo(x(0),h-pad.b);ctx.closePath();ctx.fillStyle='rgba(45,185,240,.14)';ctx.fill();
 ctx.beginPath();vals.forEach((v,i)=>i?ctx.lineTo(x(i),y(v.elevation)):ctx.moveTo(x(i),y(v.elevation)));ctx.strokeStyle='#60dbff';ctx.lineWidth=2.5;ctx.stroke();
 if(ref!==''&&Number.isFinite(+ref)){
  const ry=y(+ref);ctx.fillStyle='rgba(43,140,255,.17)';ctx.fillRect(pad.l,Math.max(pad.t,ry),w-pad.l-pad.r,Math.max(0,h-pad.b-Math.max(pad.t,ry)));
  ctx.setLineDash([7,4]);ctx.beginPath();ctx.moveTo(pad.l,ry);ctx.lineTo(w-pad.r,ry);ctx.strokeStyle='#4ea9ff';ctx.lineWidth=2;ctx.stroke();ctx.setLineDash([]);
 }
 ctx.fillStyle='#d9e8f6';ctx.font='11px monospace';ctx.fillText(Math.round(mx)+' m',4,pad.t+7);ctx.fillText(Math.round(mn)+' m',4,h-pad.b);ctx.fillText('0 km',pad.l,h-5);ctx.fillText(fmt(vals[vals.length-1].distance,1)+' km',w-60,h-5);
}
$('fwRedrawProfile').addEventListener('click',drawProfile);
$('fwReferenceWater').addEventListener('keydown',e=>{if(e.key==='Enter')drawProfile()});
async function queryShelters(origin){
 const lat=origin.lat,lon=origin.lon,rad=15000;
 const q='[out:json][timeout:20];(node(around:'+rad+','+lat+','+lon+')["emergency"="shelter"];way(around:'+rad+','+lat+','+lon+')["emergency"="shelter"];relation(around:'+rad+','+lat+','+lon+')["emergency"="shelter"];node(around:'+rad+','+lat+','+lon+')["amenity"="shelter"];way(around:'+rad+','+lat+','+lon+')["amenity"="shelter"];);out center;';
 const r=await fetch('https://overpass-api.de/api/interpreter?data='+encodeURIComponent(q),{headers:{Accept:'application/json'}});
 if(!r.ok)throw Error('OpenStreetMap Overpass HTTP '+r.status);
 const d=await r.json(),out=[],seen=new Set();
 for(const e of d.elements||[]){
  const lat0=e.lat??e.center?.lat,lon0=e.lon??e.center?.lon;
  if(!Number.isFinite(+lat0)||!Number.isFinite(+lon0))continue;
  const key=e.type+':'+e.id;if(seen.has(key))continue;seen.add(key);
  out.push({lat:+lat0,lon:+lon0,name:e.tags?.name||e.tags?.['name:en']||'Unnamed OSM shelter',capacity:e.tags?.capacity||null,tags:e.tags||{},distance:distanceKm({lat:origin.lat, lng:origin.lon},{lat:+lat0,lng:+lon0})});
 }
 return out.sort((a,b)=>a.distance-b.distance).slice(0,18);
}
async function routeToCandidate(origin,target){
 const pts=origin.lon+','+origin.lat+'|'+target.lon+','+target.lat;
 const u='https://brouter.de/brouter?lonlats='+encodeURIComponent(pts)+'&profile=trekking&alternativeidx=0&format=geojson';
 const r=await fetch(u,{headers:{Accept:'application/geo+json, application/json'}});
 if(!r.ok)throw Error('Walking-route service HTTP '+r.status);
 const d=await r.json(),fs=d.type==='FeatureCollection'?d.features:d.type==='Feature'?[d]:[];
 const good=fs.find(f=>f.geometry&&(f.geometry.type==='LineString'||f.geometry.type==='MultiLineString'));
 if(!good)throw Error('Walking route could not be constructed along the mapped path network');
 return good;
}
function routeLength(feature){
 let coords=feature.geometry.coordinates||[];if(feature.geometry.type==='MultiLineString')coords=coords.flat();
 let km=0;for(let i=1;i<coords.length;i++)km+=distanceKm({lat:coords[i-1][1],lng:coords[i-1][0]},{lat:coords[i][1],lng:coords[i][0]});return km;
}
function clearRoute(){
 if(state.route.line){map.removeLayer(state.route.line);state.route.line=null}
 state.route.markers.forEach(m=>map.removeLayer(m));state.route.markers=[];
}
$('fwRoute').addEventListener('click',async()=>{
 const sel=state.selection;if(!sel){setText('fwRouteStatus','Select a starting point on the map or use Locate Me first.');return}
 clearRoute();const origin={lat:sel.lat,lon:sel.lon};
 $('fwRoute').disabled=true;setText('fwRouteStatus','Searching mapped emergency shelters and sampling terrain elevation…');
 try{
  const candidates=await queryShelters(origin);
  if(!candidates.length)throw Error('No OpenStreetMap objects tagged as emergency shelters were found within 15 km');
  const locs=[{lat:origin.lat,lng:origin.lon},...candidates.map(s=>({lat:s.lat,lng:s.lon}))].slice(0,50);
  const elev=await elevationSamples(locs.map((p,i)=>({lat:p.lat,lng:p.lng,distance:i})));
  const startElev=elev[0].elevation;
  if(startElev==null)throw Error('Starting-point elevation is missing');
  candidates.forEach((c,i)=>c.elevation=elev[i+1]&&elev[i+1].elevation);
  const elevated=candidates.filter(c=>Number.isFinite(c.elevation)&&c.elevation>=startElev+5).sort((a,b)=>a.distance-b.distance);
  if(!elevated.length)throw Error('No mapped shelter in range has a terrain estimate at least 5 m above the start. No route was drawn.');
  let chosen=null,feature=null,lastError=null;
  for(const c of elevated.slice(0,3)){try{feature=await routeToCandidate(origin,c);chosen=c;break}catch(e){lastError=e}}
  if(!chosen||!feature)throw lastError||Error('No route was returned');
  const outline=L.geoJSON({type:'Feature',properties:feature.properties||{},geometry:feature.geometry},{style:{color:'#071629',weight:8,opacity:.9,className:'fw-route-outline'}});
  const animated=L.geoJSON({type:'Feature',properties:feature.properties||{},geometry:feature.geometry},{style:{color:'#50e6ff',weight:4,dashArray:'10 9',opacity:1,className:'fw-route-animated'}});
  state.route.line=L.layerGroup([outline,animated]).addTo(map);
  const dest=L.marker([chosen.lat,chosen.lon],{title:chosen.name}).addTo(map).bindPopup('<b>'+escapeHTML(chosen.name)+'</b><br>OSM-tagged shelter · terrain estimate '+fmt(chosen.elevation)+' m<br>Capacity: '+(chosen.capacity?escapeHTML(chosen.capacity)+' (OSM tag)':'unknown')+'<br>Not confirmation that this site is open or designated by current authorities.');
  state.route.markers.push(dest);
  const originMarker=L.circleMarker([origin.lat,origin.lon],{radius:6,color:'#fff',weight:2,fillColor:'#ff6b6b',fillOpacity:1}).addTo(map);state.route.markers.push(originMarker);
  const km=routeLength(feature),bounds=L.geoJSON({type:'Feature',geometry:feature.geometry,properties:{}}).getBounds();if(bounds.isValid())map.fitBounds(bounds.pad(.15),{maxZoom:13});
  setText('fwRouteStatus','Candidate: '+chosen.name+' · route '+fmt(km,1)+' km · SRTM rise +'+fmt(chosen.elevation-startElev,1)+' m. Capacity '+(chosen.capacity?chosen.capacity+' (OSM tag)':'unknown')+'. Route is NOT flood-validated and may cross flooded/closed roads. Follow official evacuation orders.');
 }catch(e){setText('fwRouteStatus','No candidate route: '+e.message+'. External public map/elevation services may be unavailable. This tool cannot verify a safe route.')}
 finally{$('fwRoute').disabled=false}
});
updateCanvasSize();
loadWeatherField(true);
state.raf=requestAnimationFrame(animate);
window.FloodWatchMissionControl={setHour:n=>{state.hour=clamp(+n,0,24);$('fwTimeline').value=state.hour;updateHud();restyleDem()},getHour:()=>state.hour};
})();