'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const js = fs.readFileSync('mission-control.js', 'utf8');
const html = fs.readFileSync('index.html', 'utf8');
const css = fs.readFileSync('mission-control.css', 'utf8');
for (const [label, pattern] of [
  ['hourly wind direction', /wind_direction_10m/],
  ['hourly precipitation', /precipitation_probability/],
  ['modelled soil moisture unit', /m³\/m³/],
  ['24-hour slider', /id="fwTimeline"[^>]*max="24"/],
  ['two frames per second playback', /setInterval\(\(\)=>\{if\(state\.hour>=24\)state\.hour=-1;advanceHour\(\)\},500\)/],
  ['SRTM elevation profiler', /opentopodata\.org\/v1\/srtm90m/],
  ['OSM shelter query', /"emergency"="shelter"/],
  ['walking route profile', /profile=trekking/],
  ['capacity unknown rather than invented', /Capacity: '\+\(chosen\.capacity\?escapeHTML\(chosen\.capacity\)\+' \(OSM tag\)':'unknown'\)/],
  ['route safety caveat', /Route is NOT flood-validated/],
  ['imagery compare layer', /ArcGIS\/rest\/services\/World_Imagery/],
  ['glassmorphism', /backdrop-filter:blur\(12px\)/],
  ['reduced-motion handling', /prefers-reduced-motion:reduce/]
]) assert.match(js+css, pattern, 'Missing feature or guardrail: '+label);
assert.match(html, /mission-control\.css/);
assert.match(html, /mission-control\.js/);
assert.match(js, /not (a )?flood probability/i);
assert.match(js, /capacity.*unknown/i);
console.log('PASS mission-control feature and safety-guardrail checks');
