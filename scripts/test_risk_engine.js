#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const engine = require('../risk_engine.js');
const html = fs.readFileSync('index.html', 'utf8');
const engineSource = fs.readFileSync('risk_engine.js', 'utf8');
const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

test('Frontend loads the engine and renders its colors, badge, and index', () => {
  assert.ok(html.includes('<script src="risk_engine.js"></script>'));
  assert.ok(html.includes("marker.setIcon(riskMarkerIcon(res.color))"));
  assert.ok(html.includes("res.badge"));
  assert.ok(html.includes("res.percentage"));
  assert.ok(engineSource.includes("fetchLivePrecipitation24h"));
  assert.ok(!html.includes("return 15.0"));
});

test('Leaflet DEM layer uses exported hazard index and safe popup labels', () => {
  assert.ok(html.includes('value="dem"'));
  assert.ok(html.includes("async function addDEMHazardLayer(tok)"));
  assert.ok(html.includes("const DEM_HAZARD_URL='data/dem-inundation-zones.geojson'"));
  assert.ok(html.includes("fillColor,fillOpacity:0.55"));
  assert.ok(html.includes("leafletLayer.bindPopup(demPopup(feature))"));
  assert.ok(html.includes("not a flood probability"));
  assert.ok(!html.includes("TWI Risk Score:</b>") || html.includes("DEM terrain/wetness index"));
});

test('Complete inputs use the 40/35/25 factors and stay bounded', () => {
  const r = engine.calculateRisk({
    rainfall24h: 150, riverLevel: 12, riverDangerMark: 10,
    damStoragePct: 100, damSpillwayActive: true
  });
  assert.equal(r.score, 1);
  assert.equal(r.percentage, 100);
  assert.equal(r.level, 'CRITICAL');
  assert.equal(r.color, '#d90429');
  assert.equal(r.coveragePct, 100);
  assert.deepEqual(r.weightsUsed, { rain: 0.4, river: 0.35, dam: 0.25 });
});

test('Weighted components are combined with the requested normalizers', () => {
  const r = engine.calculateRisk({
    rainfall24h: 75, riverLevel: 6, riverDangerMark: 12,
    damStoragePct: 55, damSpillwayActive: false
  });
  assert.equal(r.score, 0.35);
  assert.equal(r.percentage, 35);
  assert.equal(r.level, 'MODERATE');
});

test('Missing dam telemetry is not silently treated as zero risk', () => {
  const r = engine.calculateRisk({ rainfall24h: 60, riverLevel: 3, riverDangerMark: 12 });
  assert.equal(r.normalized.dam, null);
  assert.equal(r.factorStatus.reservoir, 'unavailable');
  assert.equal(r.factorStatus.spillway, 'unavailable');
  assert.equal(r.coveragePct, 75);
  assert.ok(r.missingFactors.includes('reservoir storage'));
  assert.ok(r.missingFactors.includes('spillway/gate state'));
  assert.match(r.badge, /INPUTS INCOMPLETE/);
});

test('No valid inputs returns no score, not a low-risk score', () => {
  const r = engine.calculateRisk({
    rainfall24h: null, riverLevel: null, riverDangerMark: null,
    damStoragePct: null, damSpillwayActive: null
  });
  assert.equal(r.score, null);
  assert.equal(r.percentage, null);
  assert.equal(r.level, 'UNAVAILABLE');
  assert.equal(r.color, '#cbd5e1');
});

test('Negative and out-of-range inputs are excluded', () => {
  const r = engine.calculateRisk({
    rainfall24h: -1, riverLevel: 2, riverDangerMark: 0,
    damStoragePct: 120, damSpillwayActive: false
  });
  assert.equal(r.normalized.rain, null);
  assert.equal(r.normalized.river, null);
  assert.equal(r.normalized.dam, null);
  assert.equal(r.score, null);
});

test('Fresh timezone-qualified official river gauge supplies stage and danger mark', () => {
  const now = Date.parse('2026-10-20T10:00:00Z');
  const snapshot = { observations: [{
    id: 'test-gauge', kind: 'river_level', value: 8.6, unit: 'm', danger_level: 9.2,
    latitude: 10.1, longitude: 76.3, observed_at: '2026-10-20T09:30:00+00:00',
    station_name: 'Periyar test gauge', station_id: 'TEST-1', river: 'Periyar',
    source_name: 'CWC test feed', source_dataset_url: 'https://example.gov.in/gauge'
  }] };
  const r = engine.findNearestRiverGauge(snapshot, 10.1, 76.3, now);
  assert.ok(r);
  assert.equal(r.riverLevel, 8.6);
  assert.equal(r.riverDangerMark, 9.2);
  assert.equal(r.stationName, 'Periyar test gauge');
  assert.equal(r.ageMinutes, 30);
  assert.equal(r.distanceKm, 0);
});

test('Stale, timezone-ambiguous, and non-metre gauge records are rejected', () => {
  const now = Date.parse('2026-10-20T10:00:00Z');
  const base = {
    kind: 'river_level', value: 8.6, unit: 'm', danger_level: 9.2,
    latitude: 10.1, longitude: 76.3, station_name: 'Test gauge'
  };
  const snapshot = { observations: [
    { ...base, id: 'no-timezone', observed_at: '2026-10-20T09:30:00' },
    { ...base, id: 'stale', observed_at: '2026-10-20T01:00:00Z' },
    { ...base, id: 'unit-unknown', unit: 'source-defined', observed_at: '2026-10-20T09:30:00Z' }
  ] };
  assert.equal(engine.findNearestRiverGauge(snapshot, 10.1, 76.3, now), null);
});

test('Last-24-hour sum uses completed hourly readings only', () => {
  const end = Date.parse('2026-10-20T10:00:00Z');
  const times = [];
  for (let i = 24; i >= 0; i--) times.push(new Date(end - i * 3600000).toISOString().slice(0, 16));
  const hourly = { time: times, precipitation: times.map(() => 1) };
  assert.equal(engine.sumPast24Hours(hourly, end), 24);
});

test('Insufficient hourly coverage returns unavailable rather than treating gaps as dry', () => {
  const end = Date.parse('2026-10-20T10:00:00Z');
  const times = [];
  for (let i = 24; i >= 0; i--) times.push(new Date(end - i * 3600000).toISOString().slice(0, 16));
  const precipitation = times.map((_, i) => i < 5 ? null : 1);
  assert.equal(engine.sumPast24Hours({ time: times, precipitation }, end), null);
});

test('Zone evaluation returns live-rainfall provenance, input details, badge and index', async () => {
  const r = await engine.evaluateZoneFloodRisk({
    name: 'Test zone', lat: 10.1, lon: 76.3, rainfall24h: 75, disableGaugeLookup: true,
    riverLevel: null, riverDangerMark: null, damStoragePct: null, damSpillwayActive: null
  });
  assert.equal(r.zoneName, 'Test zone');
  assert.equal(r.liveRainfall24h_mm, 75);
  assert.equal(r.percentage, 50);
  assert.equal(r.color, '#fcbf49');
  assert.equal(r.inputDetails.riverLevelM, null);
  assert.ok(r.badge.length > 0);
});

test('Open-Meteo failure returns unavailable, not fabricated rain', async () => {
  const previousFetch = global.fetch;
  try {
    global.fetch = async url => {
      assert.match(String(url), /api\.open-meteo\.com\/v1\/forecast/);
      assert.match(String(url), /hourly=precipitation/);
      assert.match(String(url), /past_days=1/);
      return { ok: false, status: 503 };
    };
    const rainfall = await engine.fetchLivePrecipitation24h(31.1234, -122.1234);
    assert.equal(rainfall, null);
  } finally {
    global.fetch = previousFetch;
  }
});

(async () => {
  for (const item of tests) {
    await item.fn();
    process.stdout.write('✓ ' + item.name + '\n');
  }
  process.stdout.write('\n' + tests.length + ' risk-engine tests passed.\n');
})().catch(err => {
  process.stderr.write(String(err.stack || err) + '\n');
  process.exitCode = 1;
});
