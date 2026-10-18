#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const assert = require('node:assert/strict');

const html = fs.readFileSync('index.html', 'utf8');
const mask = JSON.parse(fs.readFileSync('data/south-india-states.geojson', 'utf8'));
const geoStart = html.indexOf('function pointInRing(');
const geoEnd = html.indexOf('\nfunction gaugeSignalForCell', geoStart);
const scoreStart = html.indexOf('function computeRiskScore(');
const scoreEnd = html.indexOf('\nfunction riskLevelColor', scoreStart);
assert(geoStart >= 0 && geoEnd > geoStart, 'Grid geometry functions should exist.');
assert(scoreStart >= 0 && scoreEnd > scoreStart, 'Risk scorer should exist.');

const geoCode = html.slice(geoStart, geoEnd);
const grid = new Function('FLOODWATCH_RISK_GRID', geoCode +
  '\nreturn {pointInSouthMask, buildRiskGridCells};')({gridDegrees: 0.5});
const cells = grid.buildRiskGridCells(mask);
assert(cells.length > 100, 'Regional mask should generate a useful whole-region grid.');
assert(cells.every(c => c.north > c.south && c.east > c.west), 'Grid cells must have positive dimensions.');
assert(cells.every(c => Math.abs((c.north-c.south)-0.5) < 1e-8), 'Grid cell latitude size should remain 0.5 degrees.');
assert(grid.pointInSouthMask(80.27, 13.08, mask), 'Chennai test point should be inside the regional mask.');
assert(grid.pointInSouthMask(77.59, 12.97, mask), 'Bengaluru test point should be inside the regional mask.');
assert(grid.pointInSouthMask(76.27, 9.93, mask), 'Kochi test point should be inside the regional mask.');

const riskConfig = {weights:{rain24h:40,rain72h:30,chance24h:15,currentPrecipitation:15},cutoffs:{amber:35,red:65}};
const scorer = new Function('FLOODWATCH_RISK_GRID','clamp01', 'gaugeSignalForCell', html.slice(scoreStart, scoreEnd) +
  '\nreturn computeRiskScore;')(riskConfig,(v)=>Math.max(0,Math.min(1,v)), ()=>null);
function weather(rainPerHour, probability, current) {
  const ceilHour = Math.ceil(Date.now()/3600000)*3600000;
  const times = Array.from({length:100}, (_,i)=>new Date(ceilHour+i*3600000).toISOString().slice(0,16));
  return {current:{precipitation:current,time:times[0]},hourly:{
    time:times,precipitation:Array(times.length).fill(rainPerHour),
    precipitation_probability:Array(times.length).fill(probability)
  }};
}
const cell={lat:13,lon:80};
const green=scorer(cell,{weather:weather(0.1,5,0.1),flow:null});
assert.equal(green.level,'green','Low raw numerical values should score green.');
assert(green.score < 35,'Green score should be below the configured cutoff.');
const amber=scorer(cell,{weather:weather(2,40,0),flow:null});
assert.equal(amber.level,'amber','Moderate raw numerical values should score amber.');
assert(amber.score >=35 && amber.score <65,'Amber score should be within configured cutoffs.');
const red=scorer(cell,{weather:weather(8,80,10),flow:null});
assert.equal(red.level,'red','High raw numerical values should score red.');
assert(red.score >=65,'Red score should meet the configured cutoff.');
const unknown=scorer(cell,{weather:{failed:true},flow:null});
assert.equal(unknown.level,'unknown','Missing values must never silently turn green.');
const isolatedCurrent=scorer(cell,{weather:{current:{precipitation:19},hourly:{time:[],precipitation:[],precipitation_probability:[]}},flow:null});
assert.equal(isolatedCurrent.level,'unknown','A single current field alone must not produce a traffic-light colour.');
const today=new Date().toISOString().slice(0,10);
const days=[],values=[];
for(let i=92;i>=1;i--){const d=new Date();d.setUTCDate(d.getUTCDate()-i);days.push(d.toISOString().slice(0,10));values.push(10);}
days.push(today);values.push(null);
for(let i=1;i<=7;i++){const d=new Date();d.setUTCDate(d.getUTCDate()+i);days.push(d.toISOString().slice(0,10));values.push(100);}
const flowOnly=scorer(cell,{weather:{failed:true},flow:{daily:{time:days,river_discharge:values}}});
assert.equal(flowOnly.level,'red','A high own-history GloFAS flow percentile should be reflected in the score.');
assert.equal(flowOnly.flowHistoryCount,92,'Flow comparison should use the available pre-today history.');
const flatDays=[],flatValues=[];
for(let i=92;i>=1;i--){const d=new Date();d.setUTCDate(d.getUTCDate()-i);flatDays.push(d.toISOString().slice(0,10));flatValues.push(10);}
flatDays.push(today);flatValues.push(null);
for(let i=1;i<=7;i++){const d=new Date();d.setUTCDate(d.getUTCDate()+i);flatDays.push(d.toISOString().slice(0,10));flatValues.push(10);}
const flatFlow=scorer(cell,{weather:{failed:true},flow:{daily:{time:flatDays,river_discharge:flatValues}}});
assert.equal(flatFlow.flowPercentile,50,'Tied constant-flow history must receive a mid-rank percentile.');
assert.equal(flatFlow.level,'green','Constant low flow must not become red merely because many values tie.');
console.log(JSON.stringify({status:'PASS',grid_cells:cells.length,checks:13,examples:{green:green.score,amber:amber.score,red:red.score,flow_only:flowOnly.score,flat_flow_percentile:flatFlow.flowPercentile,missing:unknown.level}},null,2));
