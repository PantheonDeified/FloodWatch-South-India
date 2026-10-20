/* FloodWatch experimental live-risk engine.
 * Uses Open-Meteo's hourly precipitation and optional explicitly sourced gauge/reservoir telemetry.
 * The result is an index, not a flood probability, official alert, or substitute for emergency services.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.FloodWatchRiskEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const WEIGHTS = Object.freeze({ rain: 0.40, river: 0.35, dam: 0.25 });
  const CACHE_TTL_MS = 5 * 60 * 1000;
  const FAILURE_CACHE_TTL_MS = 30 * 1000;
  const rainCache = new Map();

  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const clamp = value => Math.max(0, Math.min(1, value));
  const round2 = value => Math.round(value * 100) / 100;

  function classify(score, incomplete) {
    if (score == null) return {
      level: 'UNAVAILABLE',
      badge: 'DATA INCOMPLETE — NO INDEX CALCULATED',
      color: '#cbd5e1'
    };
    let result;
    if (score >= 0.75) result = {
      level: 'CRITICAL',
      badge: 'VERY HIGH SCREENING INDEX — CHECK OFFICIAL WARNINGS',
      color: '#d90429'
    };
    else if (score >= 0.55) result = {
      level: 'HIGH',
      badge: 'HIGH SCREENING INDEX — CHECK OFFICIAL WARNINGS',
      color: '#f77f00'
    };
    else if (score >= 0.35) result = {
      level: 'MODERATE',
      badge: 'ELEVATED SCREENING INDEX — MONITOR CONDITIONS',
      color: '#fcbf49'
    };
    else result = {
      level: 'LOW',
      badge: 'LOW SCREENING INDEX — NOT A SAFETY CLEARANCE',
      color: '#2ec4b6'
    };
    if (incomplete) result.badge += ' · INPUTS INCOMPLETE';
    return result;
  }

  /**
   * Rain = 40%, river stage/danger mark = 35%, dam storage/spillway = 25%.
   * Missing variables are excluded and remaining weights renormalized, never replaced by zero.
   * rainfall24h is in mm; river values are metres; storage is 0..100; spillway is boolean.
   */
  function calculateRisk(params) {
    const p = params && typeof params === 'object' ? params : {};
    const factors = [];
    const normalized = { rain: null, river: null, dam: null };
    const subFactors = { rainContribution: 0, riverContribution: 0, damContribution: 0 };
    const factorStatus = {
      rainfall: 'unavailable',
      riverStage: 'unavailable',
      reservoir: 'unavailable',
      spillway: typeof p.damSpillwayActive === 'boolean' ? 'available' : 'unavailable'
    };

    if (finite(p.rainfall24h) && p.rainfall24h >= 0) {
      normalized.rain = clamp(p.rainfall24h / 150);
      factors.push({ key: 'rain', weight: WEIGHTS.rain, value: normalized.rain });
      factorStatus.rainfall = 'available';
    }
    const hasRiver = finite(p.riverLevel) && p.riverLevel >= 0 &&
      finite(p.riverDangerMark) && p.riverDangerMark >= 0.1;
    if (hasRiver) {
      normalized.river = Math.min(p.riverLevel / Math.max(p.riverDangerMark, 0.1), 1.2) / 1.2;
      factors.push({ key: 'river', weight: WEIGHTS.river, value: clamp(normalized.river) });
      factorStatus.riverStage = 'available';
    }
    const hasStorage = finite(p.damStoragePct) && p.damStoragePct >= 0 && p.damStoragePct <= 100;
    if (hasStorage) factorStatus.reservoir = 'available';
    // The 25% dam factor requires both storage and a known gate state.
    if (hasStorage && typeof p.damSpillwayActive === 'boolean') {
      let dam = Math.max(0, (p.damStoragePct - 55) / 45);
      if (p.damSpillwayActive) dam = Math.min(1, dam * 1.35 + 0.15);
      normalized.dam = clamp(dam);
      factors.push({ key: 'dam', weight: WEIGHTS.dam, value: normalized.dam });
    }

    const availableWeight = factors.reduce((sum, item) => sum + item.weight, 0);
    const missingFactors = [];
    if (normalized.rain == null) missingFactors.push('24-hour rainfall');
    if (normalized.river == null) missingFactors.push('river stage and danger mark');
    if (normalized.dam == null) missingFactors.push('reservoir storage and spillway state');
    if (availableWeight === 0) {
      return {
        score: null, percentage: null, level: 'UNAVAILABLE',
        badge: 'DATA INCOMPLETE — NO INDEX CALCULATED', color: '#cbd5e1',
        subFactors, normalized, weights: WEIGHTS, weightsUsed: {},
        coveragePct: 0, factorStatus, missingFactors,
        note: 'No valid input factors were available. Missing data is not treated as zero risk.'
      };
    }

    const weightsUsed = {};
    let rawScore = 0;
    factors.forEach(item => {
      const weight = item.weight / availableWeight;
      weightsUsed[item.key] = round2(weight);
      rawScore += item.value * weight;
      const contribution = round2(item.value * weight);
      if (item.key === 'rain') subFactors.rainContribution = contribution;
      if (item.key === 'river') subFactors.riverContribution = contribution;
      if (item.key === 'dam') subFactors.damContribution = contribution;
    });
    const score = round2(clamp(rawScore));
    const incomplete = factors.length < 3;
    const classification = classify(score, incomplete);
    return {
      score,
      percentage: Math.round(score * 100),
      ...classification,
      subFactors,
      normalized,
      weights: WEIGHTS,
      weightsUsed,
      coveragePct: Math.round(availableWeight * 100),
      factorStatus,
      missingFactors,
      note: incomplete
        ? 'Experimental index using available inputs only; remaining configured weights were renormalized. This is not a calibrated flood probability or official warning.'
        : 'Experimental weighted screening index; not a calibrated flood probability or official warning.'
    };
  }

  function parseUtcTime(value) {
    if (typeof value !== 'string') return NaN;
    return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z');
  }

  /**
   * Sum the last 24 completed hourly precipitation values from a UTC hourly response.
   * Requires at least 22 valid hourly values to avoid treating missing observations as dry weather.
   */
  function sumPast24Hours(hourly, nowMs) {
    if (!hourly || !Array.isArray(hourly.time) || !Array.isArray(hourly.precipitation)) return null;
    const end = Math.floor((Number.isFinite(nowMs) ? nowMs : Date.now()) / 3600000) * 3600000;
    const start = end - 24 * 3600000;
    let count = 0;
    let total = 0;
    for (let i = 0; i < hourly.time.length; i++) {
      const t = parseUtcTime(hourly.time[i]);
      if (!Number.isFinite(t) || t <= start || t > end) continue;
      const v = hourly.precipitation[i];
      if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) continue;
      total += v;
      count++;
    }
    if (count < 22) return null;
    return Math.round(total * 10) / 10;
  }

  async function fetchLivePrecipitation24h(lat, lon, options) {
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 ||
        !Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      throw new TypeError('Latitude/longitude must be valid numeric coordinates.');
    }
    const opts = options && typeof options === 'object' ? options : {};
    const key = latitude.toFixed(4) + ',' + longitude.toFixed(4);
    const now = Date.now();
    const cached = rainCache.get(key);
    if (!opts.force && cached && (cached.expiresAt === Infinity || cached.expiresAt > now)) return cached.promise;

    const query = new URLSearchParams({
      latitude: String(latitude),
      longitude: String(longitude),
      hourly: 'precipitation',
      past_days: '1',
      forecast_days: '1',
      timezone: 'UTC'
    });
    const endpoint = 'https://api.open-meteo.com/v1/forecast?' + query.toString();
    const promise = (async () => {
      try {
        const response = await fetch(endpoint, { cache: 'no-store', headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error('Open-Meteo returned HTTP ' + response.status);
        const data = await response.json();
        const amount = sumPast24Hours(data.hourly, Date.now());
        if (amount == null) throw new Error('Open-Meteo did not provide at least 22 valid readings for the last 24 completed hours.');
        const entry = rainCache.get(key);
        if (entry) entry.expiresAt = Date.now() + CACHE_TTL_MS;
        return amount;
      } catch (error) {
        console.warn('[FloodWatch] Live 24-hour precipitation unavailable for ' + key + ':', error.message);
        const entry = rainCache.get(key);
        if (entry) entry.expiresAt = Date.now() + FAILURE_CACHE_TTL_MS;
        return null;
      }
    })();
    rainCache.set(key, { promise, expiresAt: Infinity });
    return promise;
  }

  async function evaluateZoneFloodRisk(zone) {
    const z = zone && typeof zone === 'object' ? zone : {};
    const lat = Number(z.lat);
    const lon = Number(z.lon);
    const rainfall24h = finite(z.rainfall24h) && z.rainfall24h >= 0
      ? z.rainfall24h
      : await fetchLivePrecipitation24h(lat, lon);
    const assessment = calculateRisk({
      rainfall24h,
      riverLevel: z.riverLevel,
      riverDangerMark: z.riverDangerMark,
      damStoragePct: z.damStoragePct,
      damSpillwayActive: z.damSpillwayActive
    });
    return {
      zoneName: typeof z.name === 'string' ? z.name : 'Selected location',
      coordinates: [lat, lon],
      liveRainfall24h_mm: rainfall24h,
      rainfallSource: rainfall24h == null ? 'unavailable' : 'Open-Meteo hourly precipitation; last 24 completed hours',
      ...assessment
    };
  }

  return Object.freeze({
    WEIGHTS,
    calculateRisk,
    fetchLivePrecipitation24h,
    evaluateZoneFloodRisk,
    sumPast24Hours
  });
});
