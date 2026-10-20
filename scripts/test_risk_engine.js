#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const engine = require('../risk_engine.js');
const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

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
    name: 'Test zone', lat: 10.1, lon: 76.3, rainfall24h: 75,
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
