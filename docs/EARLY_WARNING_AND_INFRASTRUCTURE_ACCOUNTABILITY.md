# FloodWatch: Early Warning, Impact Reduction, and Infrastructure Accountability

**Status:** product/design specification for the FloodWatch South India research prototype. This is not an operational warning protocol, a structural-safety certification, or a substitute for IMD/CWC/NDMA authorities.

## 1. Problems FloodWatch is intended to address

1. **Fragmented situational awareness:** rainfall, radar, cyclone tracks, river observations, and modelled discharge are spread across different portals. FloodWatch places source-labelled context on one map.
2. **Late recognition of dangerous conditions:** heavy or persistent rainfall upstream, rising river observations, and official alerts can be reviewed together so an operator can investigate a developing threat earlier.
3. **Unclear data freshness and reliability:** each observation should show its source, observation time, update time where available, and whether it is observed, forecast, or modelled. Stale or failed feeds must be visibly marked.
4. **Hard-to-compare local conditions:** map search and location selection support checking rural and urban locations across Andhra Pradesh, Telangana, Karnataka, Kerala, and Tamil Nadu—not only a fixed city list.
5. **Weak hand-off and accountability:** preserve a timestamped record of what data and official warning were visible, what the system displayed, who reviewed/escalated it, and what action was taken—without implying that a dashboard log alone proves negligence.
6. **Infrastructure risk visibility:** provide a registry of dams, reservoirs, embankments, drainage assets, and gauges with official identifiers, responsible authority, inspection dates, published condition/status, and source documents where publicly available. Unknown values must remain “unknown,” never be guessed.

## 2. How it could support earlier alerts

### Evidence chain

- **Monitor:** ingest rainfall forecasts/observations, radar, cyclone or severe-weather bulletins, river gauges, reservoir/dam releases where officially published, and official flood warnings.
- **Detect signals:** calculate transparent rainfall accumulation and intensity windows; detect river-level/discharge rises only where a consistent time series and units exist; compare against official station thresholds when the authority publishes them.
- **Cross-check:** distinguish a single noisy sensor from multiple independent signals. Link upstream rainfall to downstream gauges only after river-network and travel-time relationships have been reviewed.
- **Estimate lead time:** show the latest observation, forecast horizon, data age, affected downstream places, and uncertainty. Never promise a fixed warning lead time without local back-testing.
- **Escalate:** notify a human operator when a documented threshold or official alert is met. Link directly to the relevant IMD/CWC/SDMA/DDMA source and include a clear “verify with authority” instruction.
- **Record:** keep an audit entry for trigger, inputs, rule/model version, recipient, delivery status, acknowledgement, and resolution. Provide a manual override and correction history.

### Alert maturity levels

| Level | Meaning | Permitted behaviour |
|---|---|---|
| Data-quality notice | Feed is stale, missing, inconsistent, or failed | Show warning about missing confidence; do not infer safety |
| Watch / investigate | One or more preliminary signals need checking | Internal dashboard notice; clearly labelled as unvalidated |
| Authority warning | An official IMD/CWC/SDMA/DDMA warning is available | Display/link the official warning and its valid time/area |
| Validated FloodWatch alert | A locally evaluated rule/model passes documented validation and governance | Only after independent back-testing, operational testing, and approval; communicate uncertainty and source provenance |

Do not send public “evacuate” instructions or label an unvalidated model output as an official warning. Any public notification pathway requires an approved owner, escalation protocol, delivery testing, and coordination with relevant authorities.

## 3. Human-made infrastructure and accountability

Floods are not only meteorological events. Land use, drainage capacity, embankments, reservoir operations, maintenance, and dam safety may affect consequences. FloodWatch should **surface evidence and responsibility records**, not assign blame automatically.

### Infrastructure record fields

- Asset name, type, official asset ID, river/basin, coordinates and coordinate source.
- Responsible operator/department and official contact page.
- Published design/storage/release information where authoritative and appropriate to disclose.
- Latest public inspection/safety review date, reported defects, repair/maintenance status, and source document.
- Current reservoir level/inflow/outflow only when published by a trustworthy source, with units and timestamp.
- Downstream settlements/critical facilities potentially exposed, derived from reviewed geospatial data.
- Data completeness, last verification date, and an explicit “not independently verified” flag.

**Dam strength is not a single live number.** Structural capacity, safety margins, defects, and failure likelihood require engineering inspections, design records, instrumentation, and qualified assessment. FloodWatch must not estimate or display “dam strength” from rainfall or reservoir level alone. It can show the latest official inspection/status record and flag missing or overdue public records for human follow-up.

### Accountability log

For each incident or alert, retain (with access controls and privacy safeguards):

- Event ID and time window; source URLs and source timestamps.
- Data-feed outages, missing/stale inputs, and model/rule version.
- Alert trigger and the evidence that caused it; confidence/limitations.
- Responsible agency/role for review, acknowledgement time, escalation and action status.
- Corrections, overrides, and reasons, preserving prior versions.
- Post-event review: what was known at the time, what was communicated, delays, and corrective actions.

The log should support transparent after-action review, not automatically declare a person or agency legally responsible. Public records should be cited, allegations distinguished from verified facts, and personal or security-sensitive infrastructure details withheld where disclosure could create risk.

## 4. Proposed system architecture

1. **Data adapters:** independent modules for IMD/GDACS/public weather feeds, CWC/NWDP gauges, reservoir bulletins, and official disaster-management alerts.
2. **Quality/provenance layer:** schema validation, units, timestamp normalization with original timestamp retained, freshness checks, source attribution, and missingness tracking.
3. **Transparent baseline rules:** configurable, source-documented rainfall accumulation and official gauge thresholds. Rules are a benchmark, not proof of forecast skill.
4. **ML research layer:** start with a persistence baseline and discharge-only LSTM for a reviewed gauge; then test weather-plus-discharge features and a separately labelled flood-event classifier with reviewed event labels. Use chronological train/validation/test splits and compare MAE/RMSE/NSE and skill against baseline.
5. **Geospatial impact layer:** verified gauge coordinates, reviewed river connectivity, catchments, terrain/flood footprints, and exposed settlements. Do not imply inundation depth/extent without a validated hydraulic model.
6. **Alert and audit layer:** human-reviewed escalation, official warning links, acknowledgement/delivery logs, incident timeline, and exportable after-action report.
7. **Frontend:** map layers and a timeline that visibly separate observed, forecast, modelled, and official-warning information.

## 5. Validation gates before relying on predictions

- Verify source provenance, measurement units, station identity, timestamps, and freshness.
- Manually review gauge coordinates and upstream/downstream connections before weather joins.
- Compare the model with persistence and a simple transparent threshold baseline.
- Use time-ordered held-out periods and report missingness, false alarms, missed events, lead time, and performance by basin/season.
- Evaluate against independently sourced flood-event records; absence of a record is not a negative label.
- Run a shadow-mode period with no public automated warnings; review alert usefulness and failure modes.
- Test feed outage, stale data, extreme values, duplicate observations, notification failures, and manual override.
- Publish a model card and clear limits; obtain operational/agency approval before public deployment.

## 6. First implementation order

1. Complete and inspect the latest historical CWC/NWDP workflow artifact, including provenance and station-readiness reports.
2. Select one reviewed station; confirm units, identity, continuity, and valid dates.
3. Reproduce the discharge-only LSTM and persistence comparison. Keep model weights as workflow artifacts, not auto-deployed.
4. Build one auditable rainfall + gauge timeline for that station only after location and river relationship review.
5. Add a transparent “data-quality notice / official-warning link” alert prototype before attempting predictive public alerts.
6. Create the infrastructure registry schema and populate only records with authoritative source links.
7. Evaluate alert timing and false alarms on historical events before expanding to additional basins.

## 7. Intended outcomes and non-goals

**Potential benefit:** faster evidence gathering, earlier human investigation, clearer data gaps, more traceable hand-offs, and better post-event accountability.

**Not claimed:** guaranteed prediction, exact flood depth, dam structural safety, legal fault, complete coverage of South India, or parity with Google Flood Hub. FloodWatch is a research/situational-awareness prototype, not an official warning service.
