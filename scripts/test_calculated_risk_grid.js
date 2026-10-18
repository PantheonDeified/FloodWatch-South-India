#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const assert = require('node:assert/strict');

const html = fs.readFileSync('index.html', 'utf8');
const mask = JSON.parse(fs.readFileSync('data/south-india-states.geojson', 'utf8'));
const basins = JSON.parse(fs.readFileSync('data/south-india-basins.geojson', 'utf8'));
const geoStart = html.indexOf('function pointInRing(');
const geoEnd = html.indexOf('\nfunction gaugeSignalForCell', geoStart);
const scoreStart = html.indexOf('function computeRiskScore(');
const scoreEnd = html.indexOf('\nfunction riskLevelColor', scoreStart);
assert(geoStart >= 0 && geoEnd > geoStart, 'Risk-grid geometry helpers should exist.');
assert(scoreStart >= 0 && scoreEnd > scoreStart, 'Risk score function should exist.');

const geoCode = html.slice(geoStart, geoEnd);
const geometry = new Function('FLOODWATCH_RISK_GRID', geoCode +
  '\nreturn {pointInSouthMask, buildRiskGridCells};')({gridDegrees: 0.5});
const cells = geometry.buildRiskGridCells(mask);
assert(cells.length > 100, 'Regional mask should generate a useful regional point set.');
assert(cells.every(c => c.north > c.south && c.east > c.west), 'Grid sample bounds must be positive.');
assert(cells.every(c => Math.abs((c.north-c.south)-0.5) < 1e-8), 'Sample step should stay 0.5 degrees.');
assert(geometry.pointInSouthMask(80.27, 13.08, mask), 'Chennai test point should be inside the regional mask.');
assert(geometry.pointInSouthMask(77.59, 12.97, mask), 'Bengaluru test point should be inside the regional mask.');
assert(geometry.pointInSouthMask(76.27, 9.93, mask), 'Kochi test point should be inside the regional mask.');

let mockGauge = null;
let mockHuman = {points:0,items:[],incident:false};
const scorer = new Function('clamp01','gaugeSignalForCell','humanMadeSignalForCell',
  html.slice(scoreStart, scoreEnd) + '\nreturn computeRiskScore;')(
  v=>Math.max(0,Math.min(1,v)), ()=>mockGauge, ()=>mockHuman
);
function weather(rainPerHour, probability, current) {
  const ceilHour=Math.ceil(Date.now()/3600000)*3600000;
  const times=Array.from({length:100},(_,i)=>new Date(ceilHour+i*3600000).toISOString().slice(0,16));
  return {current:{precipitation:current,time:times[0]},hourly:{
    time:times,precipitation:Array(times.length).fill(rainPerHour),
    precipitation_probability:Array(times.length).fill(probability)
  }};
}
const cell={lat:13,lon:80};
const green=scorer(cell,{weather:weather(0.1,5,0.1),flow:null});
assert.equal(green.level,'green','Low raw data should score green.');
assert(green.score<35,'Green score should remain below amber cutoff.');
const amber=scorer(cell,{weather:weather(2,40,0),flow:null});
assert.equal(amber.level,'amber','Moderate raw data should score amber.');
assert(amber.score>=35&&amber.score<65,'Amber score should sit within the configured cutoffs.');
const red=scorer(cell,{weather:weather(8,80,10),flow:null});
assert.equal(red.level,'red','High raw data should score red.');
assert(red.score>=65,'Red score should meet the configured cutoff.');
const unknown=scorer(cell,{weather:{failed:true},flow:null});
assert.equal(unknown.level,'unknown','Missing inputs must never silently turn green.');

const today=new Date().toISOString().slice(0,10),days=[],values=[];
for(let i=92;i>=1;i--){const d=new Date();d.setUTCDate(d.getUTCDate()-i);days.push(d.toISOString().slice(0,10));values.push(10);}
days.push(today);values.push(null);
for(let i=1;i<=7;i++){const d=new Date();d.setUTCDate(d.getUTCDate()+i);days.push(d.toISOString().slice(0,10));values.push(100);}
const flowOnly=scorer(cell,{weather:{failed:true},flow:{daily:{time:days,river_discharge:values}}});
assert.equal(flowOnly.level,'red','High GloFAS peak percentile should influence the score.');
assert.equal(flowOnly.flowHistoryCount,92,'Flow comparison should use valid pre-today history.');

mockGauge={percentile:50,rising:true,rapidRise:true,hydrologyLinked:true,riseRatePerHour:3,distanceKm:3,historyCount:15};
const risingOnly=scorer(cell,{weather:{failed:true},flow:null});
assert(risingOnly.score>=35,'A recent river rise alone should be at least elevated.');
assert(risingOnly.gauge.rapidRise,'Rapid rise flag should be preserved.');
mockGauge={percentile:97,rising:false,rapidRise:false,hydrologyLinked:false,distanceKm:4,historyCount:20};
const highRiverOnly=scorer(cell,{weather:{failed:true},flow:null});
assert(highRiverOnly.score>=35,'Unusually high recent station-relative river level should be elevated.');
mockGauge=null;

mockHuman={points:29,items:[{category:'Dam/gate malfunction or abnormal release',points:29,distanceKm:3}],incident:true};
const humanOnly=scorer(cell,{weather:{failed:true},flow:null});
assert(humanOnly.score>=35,'Documented physical flood incident should not be presented as low risk when weather/flow feeds are missing.');
assert(humanOnly.humanSignal.items.length===1,'Human-made factor evidence should be retained for explanation.');
mockHuman={points:0,items:[],incident:false};

const evidenceStart=html.indexOf('function scoreHumanMadeEvidence(');
const evidenceEnd=html.indexOf('\nfunction localInfrastructureEvidence()',evidenceStart);
assert(evidenceStart>=0&&evidenceEnd>evidenceStart,'Human-evidence scorer should exist.');
const humanScorer=new Function('kmBetween',html.slice(evidenceStart,evidenceEnd)+'\nreturn scoreHumanMadeEvidence;')(()=>1);
const incident={
  category:'Dam/gate malfunction or abnormal release',place:'Test reservoir',
  latitude:13.01,longitude:80.01,hydrologyLinked:false,
  status:'Official public record',sourceUrl:'https://cwc.gov.in/test-report',
  date:today,notes:'Published abnormal release'
};
assert.equal(humanScorer(cell,[incident]).points,0,'Dam/gate incident without verified hydrology link must not affect a downstream cell.');
incident.hydrologyLinked=true;
assert(humanScorer(cell,[incident]).points>0,'Dated official incident with verified hydrology link should affect the nearby cell.');
incident.status='Unverified report';
assert.equal(humanScorer(cell,[incident]).points,0,'Unverified reports must not change the numeric risk score.');

const contourStart=html.indexOf('function buildRiskContourPolylines(');
const contourEnd=html.indexOf('\nfunction drawComputedRiskCells',contourStart);
assert(contourStart>=0&&contourEnd>contourStart,'Connected contour builder should exist.');
const contourBuilder=new Function('pointInSouthMask',html.slice(contourStart,contourEnd)+'\nreturn buildRiskContourPolylines;')(()=>true);
const contour=contourBuilder([[0,0,0],[0,80,0],[0,0,0]],35,1,10,20,{features:[]});
assert(contour.length>0&&contour.every(line=>line.length>=2),'Marching-squares contour should create connected lines around a test hotspot.');
assert(html.includes("layers:'IMERG_Precipitation_Rate'"),'NASA IMERG overlay should be registered.');
assert(html.includes('id="basinRiskSection"'),'Basin-risk context section should exist.');
assert(html.includes('async function loadSouthIndiaBasins()'),'Basin loader should exist.');
assert(html.includes('updateZoomStatus();\\nloadSouthIndiaBasins();'),'Basin data should load without selecting the calculated-risk layer.');
assert(html.includes('const basinGeo=await loadSouthIndiaBasins();'),'Calculated risk layer should reuse the shared basin loader.');
assert(Array.isArray(basins.features)&&basins.features.length>=50,'Regional basin GeoJSON should include a useful set of features.');
assert(basins.features.every(f=>f.geometry&&Number.isFinite(Number(f.properties?.HYBAS_ID))&&f.properties?.NEXT_DOWN!==undefined),'Basin features should carry geometry, HYBAS_ID and NEXT_DOWN routing attributes.');
assert(html.includes('id="infraLatitude"')&&html.includes('id="infraLongitude"'),'Infrastructure evidence must include coordinates.');
assert(!html.includes('L.rectangle([[cell.south,cell.west]'),'The active risk rendering should no longer draw square risk cells.');

console.log(JSON.stringify({
  status:'PASS',
  sample_cells:cells.length,
  checks:30,
  examples:{
    green:green.score,amber:amber.score,red:red.score,
    flow_only:flowOnly.score,rising_only:risingOnly.score,
    high_river_only:highRiverOnly.score,human_incident_only:humanOnly.score,
    unknown:unknown.level,contour_paths:contour.length
  }
},null,2));
