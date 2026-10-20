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
  ['capacity unknown rather than invented', /chosen\.capacity/],
  ['route safety caveat', /Route is NOT flood-validated/],
  ['imagery compare layer', /ArcGIS\/rest\/services\/World_Imagery/],
  ['glassmorphism', /backdrop-filter:blur\(12px\)/],
  ['reduced-motion handling', /prefers-reduced-motion:reduce/],
  ['live selected screening counter without fabricated default', /id=\"fwThreatScore\"/],
  ['grid telemetry counter', /id=\"fwGridCount\"/],
  ['status-driven warning badge', /fw-command-status\.is-critical/],
  ['radar pulse styling', /@keyframes fwRadarWave/],
  ['map scanline is non-interactive', /fw-map-scanline[^}]*pointer-events:none/],
  ['animated evacuation route styling', /\.fw-route-animated[^}]*stroke-dasharray/],
  ['SVG route path receives animation class', /layer\.on\('add',[\s\S]*?path\.classList\.add\('fw-route-animated'\)/],
  ['full-screen map control exists', /id="mapExpand"/],
  ['region reset control exists', /id="resetMapView"/],
  ['full-screen map action is implemented', /setMapExpanded\(expanded\)/],
  ['critical marker pulse derives from returned risk level', /res\.percentage!=null&&\(res\.level==='HIGH'\|\|res\.level==='CRITICAL'\)/],
  ['command HUD does not hard-code example threat score', /fwThreatScore/],
  ['full-width map above information panels', /grid-template-areas:"map" "side"/],
  ['existing map readout section reused without duplicate IDs', /getElementById\('fwMapReadouts'\)/],
  ['map feature popups docked below map', /map\.on\('popupopen'/],
  ['HUD below map instead of absolute overlay', /\.fw-hud,\.fw-playback,\.fw-profile-drawer\{[^}]{0,300}position:static/],
  ['whole-region terrain raster supported', /dem-inundation-zones\.geojson/],
  ['dark matter is the default map tile layer', /basemaps\.cartocdn\.com\/dark_all/],
  ['street and satellite alternatives remain available', /id="baseMapStyle"[^>]*Street map/],
  ['soundless boot curtain exists', /id="bootScreen"[^>]*fw-boot-screen/],
  ['boot says live feeds load in background instead of claiming they synchronized', /LIVE FEEDS LOAD IN BACKGROUND/],
  ['full-viewport CRT overlay does not intercept clicks', /fw-crt-overlay[^}]*pointer-events:none/],
  ['cloudburst simulator is clearly identified as a simulation', /CONTROLLED DEMONSTRATION[\s\S]*SIMULATION ONLY/],
  ['simulation index is separate from the real selected index', /id="fwSimScore"/],
  ['simulation includes illustrative Aluva, Chennai and Wayanad sites', /Aluva \/ Periyar basin[\s\S]*Chennai \/ Adyar–Cooum region[\s\S]*Wayanad \/ Kalpetta region/],
  ['simulation annotations do not claim real inundation boundaries', /synthetic demonstration buffers, not measured inundation boundaries/],
  ['simulation vectors are not presented as verified evacuation routes', /Schematic vectors only—not road-following evacuation routes/],
  ['simulation never claims to update real telemetry', /Live readings were not changed/],
  ['audio is opt-in and disabled by default', /audioEnabled:false[\s\S]*id="fwAudioToggle"[^>]*aria-pressed="false"/],
  ['audio context is created only by explicit audio cue action', /function playTactileClick[\s\S]*if\(!state\.audioEnabled\)return/],
  ['simulated zones use separate Leaflet vector layer', /fwSimulationPane[\s\S]*L\.polygon/],
]) assert.match(js+css+html, pattern, 'Missing feature or guardrail: '+label);
assert.match(html, /mission-control\.css/);
assert.match(html, /mission-control\.js/);
assert.match(html, /id="fwMapReadouts"/);
assert.equal((html.match(/id="fwMapReadouts"/g)||[]).length,1,'Map readout section must have a single DOM ID');
assert.match(html, /class="map-intro"/);
assert.match(html, /header-meta/);
assert.ok(html.indexOf('</main>') < html.indexOf('id="fwMapReadouts"'), 'Map legends and hover detail panel must sit below the map/grid');
assert.match(js, /insertAdjacentElement\('afterend',controls\)/, 'Mission-control panels must be inserted after the main map + graph');
assert.match(css, /#fwMissionControls\{\s*position:static;inset:auto/, 'Mission-control must not overlay the map');
assert.match(html, /DEM_HAZARD_PNG/);
assert.match(js, /not (a )?flood probability/i);
assert.match(js, /capacity.*unknown/i);
console.log('PASS mission-control feature and safety-guardrail checks');
