#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const assert = require('node:assert/strict');

const html = fs.readFileSync('index.html', 'utf8');
const mask = JSON.parse(fs.readFileSync('data/south-india-states.geojson', 'utf8'));
const testNames = [];
function test(name, fn) { fn(); testNames.push(name); }

assert(mask.features && mask.features.length > 0, 'The South India state mask should contain features.');
assert(html.includes('function calculateFloodHazardScore('), 'Rain/GloFAS score function must exist.');
assert(html.includes('function nearestLstmSignal('), 'Station-aware LSTM lookup must exist.');
assert(html.includes('function applyLstmCellScore('), 'LSTM map-colour contribution must exist.');

const geoStart = html.indexOf('const polysOf=');
const geoEnd = html.indexOf('\nfunction maskPath', geoStart);
assert(geoStart >= 0 && geoEnd > geoStart, 'Map geometry helpers should exist.');
const geo = new Function('GRID', html.slice(geoStart, geoEnd) +
  '\nreturn {inMask, gridCells};')({step: 0.5, w: 73.5, e: 86.5, s: 7.5, n: 21.5});
const cells = geo.gridCells(mask);

test('Regional mask generates more than 100 grid cells', () => assert(cells.length > 100));
test('All grid points have finite coordinates inside South India bounds', () => {
  assert(cells.every(c => Number.isFinite(c.lat) && Number.isFinite(c.lon)));
  assert(cells.every(c => c.lat >= 7.5 && c.lat <= 21.5 && c.lon >= 73.5 && c.lon <= 86.5));
});
test('Chennai is inside the state mask', () => assert(geo.inMask(80.27, 13.08, mask)));
test('Bengaluru is inside the state mask', () => assert(geo.inMask(77.59, 12.97, mask)));
test('Kochi is inside the state mask', () => assert(geo.inMask(76.27, 9.93, mask)));
test('Hyderabad is inside the state mask', () => assert(geo.inMask(78.49, 17.39, mask)));
test('An out-of-coverage point is outside the regional mask', () => assert.equal(geo.inMask(95, 30, mask), false));

const clamp = x => Math.max(0, Math.min(1, x));
const scoreStart = html.indexOf('function calculateFloodHazardScore(');
const scoreEnd = html.indexOf('\nfunction score(', scoreStart);
const calc = new Function('clamp', html.slice(scoreStart, scoreEnd) +
  '\nreturn calculateFloodHazardScore;')(clamp);
test('Risk score stays bounded for extreme rain and flow', () =>
  assert(calc(1000, 100, null).score <= 100 && calc(1000, 100, null).score >= 0));
test('Missing GloFAS input is not invented as zero flow', () =>
  assert.equal(calc(10, NaN, null).riverScore, null));
test('High station-relative flow increases the base risk score', () =>
  assert(calc(40, 95, null).score > calc(40, 10, null).score));
test('Missing reservoir storage does not add a reservoir score', () =>
  assert.equal(calc(20, 40, null).damScore, null));
test('Available reservoir storage is a separate factor', () =>
  assert(Number.isFinite(calc(20, 40, 80).damScore)));

const haversineKm = (a,b,c,d) => {
  const rad=x=>x*Math.PI/180, dLat=rad(c-a), dLon=rad(d-b);
  const h=Math.sin(dLat/2)**2+Math.cos(rad(a))*Math.cos(rad(c))*Math.sin(dLon/2)**2;
  return 12742*Math.asin(Math.min(1,Math.sqrt(h)));
};
const nearestStart = html.indexOf('function nearestLstmSignal(');
const nearestEnd = html.indexOf('\nfunction applyLstmToPointScore', nearestStart);
const testBasinAt=(lat,lon)=>Math.abs(lat-13.08)<.001&&Math.abs(lon-80.27)<.001?'A':Math.abs(lat-17.39)<.001&&Math.abs(lon-78.49)<.001?'B':null;
const testUpstreamHops=(stationId,targetId)=>stationId===targetId?0:stationId==='U'&&targetId==='A'?1:null;
const nearest = new Function('kmBetween','basinAt','upstreamBasinHops',html.slice(nearestStart,nearestEnd)+
  '\nreturn nearestLstmSignal;')(haversineKm,testBasinAt,testUpstreamHops);
const applyPointStart = html.indexOf('function applyLstmToPointScore(');
const applyPointEnd = html.indexOf('\n\nfunction clearOverlay',applyPointStart);
const applyPoint = new Function('nearestLstmSignal','clamp',
  html.slice(applyPointStart,applyPointEnd)+'\nreturn applyLstmToPointScore;')(nearest,clamp);
const applyCellStart = html.indexOf('function applyLstmCellScore(');
const applyCellEnd = html.indexOf('\nfunction adjustedScores',applyCellStart);
const applyCell = new Function('nearestLstmSignal','clamp',
  html.slice(applyCellStart,applyCellEnd)+'\nreturn applyLstmCellScore;')(nearest,clamp);
const station = {
  station_id:'TEST-GAUGE', station_latitude:13.08, station_longitude:80.27,
  basin_id:'A',
  coordinates_available:true, forecast_is_live:true,
  peak_discharge_percentile_all_available_history:100
};

test('Same-basin eligible station is found at its coordinates', () =>
  assert.equal(nearest(13.08,80.27,[station]).station.station_id,'TEST-GAUGE'));
test('Stale source history is not used for the LSTM overlay', () =>
  assert.equal(nearest(13.08,80.27,[{...station,forecast_is_live:false}]),null));
test('Stations without usable coordinates are ignored', () =>
  assert.equal(nearest(13.08,80.27,[{...station,coordinates_available:false}]),null));
test('A disconnected station is ignored even when the point is geographically close', () =>
  assert.equal(nearest(13.1,80.3,[station]),null));
test('Station upstream through a mapped downstream link can contribute', () =>
  assert.equal(nearest(13.08,80.27,[{...station,basin_id:'U'}]).basinHops,1));
test('A station in a different basin is ignored', () =>
  assert.equal(nearest(17.39,78.49,[station]),null));
test('Station-relative discharge modifies a supported selected-point score', () => {
  const result = applyPoint({score:50,level:'amber'},13.08,80.27,[station]);
  assert(result.score > 50);
  assert.equal(result.lstmSignal.station.station_id,'TEST-GAUGE');
});
test('At a gauge, LSTM blending is capped at 25 percent', () => {
  const result = applyPoint({score:50,level:'amber'},13.08,80.27,[station]);
  assert.equal(result.score,62.5);
  assert.equal(result.lstmBlendWeight,0.25);
});
test('Upstream-basin influence fades by network links', () => {
  const result=applyPoint({score:50,level:'amber'},13.08,80.27,[{...station,basin_id:'U'}]);
  assert(result.score>50&&result.score<62.5);
  assert(result.lstmBlendWeight<0.25);
});
test('No nearby LSTM station leaves the existing score unchanged', () =>
  assert.equal(applyPoint({score:50,level:'amber'},17.39,78.49,[station]).score,50));
test('Unknown point scores stay unknown even near a station', () =>
  assert.equal(applyPoint({score:null,level:'unk'},13.08,80.27,[station]).score,null));
test('LSTM factor changes a nearby grid-cell score', () =>
  assert.equal(applyCell(50,{lat:13.08,lon:80.27},[station]),62.5));
test('Unknown grid cells remain unknown despite nearby station forecasts', () =>
  assert.equal(applyCell(null,{lat:13.08,lon:80.27},[station]),null));

test('Map and location-card colour cutoffs are 35/65', () => {
  assert(html.includes("s>=65?'red':s>=35?'amber':'green'"));
  assert(html.includes('contourSegs(f.grid,35'));
  assert(html.includes('contourSegs(f.grid,65'));
});
test('Contour view reports progress while loading and shows final legend when ready', () => {
  assert(html.includes('progress-only #ovRows'));
  assert(html.includes("Loading data · '+Math.min(100,Math.floor(progressDone/Math.max(1,totalWork)*100))+'%"));
  assert(html.includes("showLegend('Rainfall + river contours'"));
  assert(html.includes('Lower screening score (<35)'));
  assert(html.includes('Higher screening score (≥65)'));
  assert(!html.includes('Chill: score under 35'));
  assert(!html.includes('Clear areas: not enough data, not safe.'));
});
test('Frontend requests all station forecasts rather than one arbitrary gauge', () =>
  assert(html.includes('/api/v1/models/regional-discharge/forecast?all_stations=true')));
test('Map overlay requires fresh source-history dates, coordinates and a station-relative percentile', () => {
  assert(html.includes('function sourceHistoryAgeDays('));
  assert(html.includes('actualAge<=3'));
  assert(html.includes('coordinates_available===true'));
  assert(html.includes('peak_discharge_percentile_all_available_history'));
  assert(html.includes('Date.now()-created>36*60*60*1000'));
});
test('Map can load scheduled regional LSTM forecasts without a backend URL', () => {
  assert(html.includes('LSTM_STATIC_FORECAST_URL'));
  assert(html.includes('regional-lstm-forecast.json'));
  assert(html.includes('scheduled GitHub Actions inference snapshot'));
  assert(html.includes('all_stations=true'));
});
test('LSTM influence requires a basin link and is clearly not a calibrated probability', () => {
  assert(html.includes('MAX_UPSTREAM_BASIN_LINKS=6'));
  assert(html.includes('HydroBASINS'));
  assert(html.includes('not calibrated flood probability'));
  assert(html.includes('This is a discharge rank, not flood probability.'));
});

console.log('PASS: ' + testNames.length + ' FloodWatch frontend checks.');
for (const name of testNames) console.log('  PASS ' + name);
