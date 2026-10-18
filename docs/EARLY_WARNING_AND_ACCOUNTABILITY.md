# FloodWatch: problems solved, early-warning workflow, and infrastructure accountability

## 1. Problems FloodWatch is designed to address

FloodWatch is a regional situational-awareness and decision-support prototype. It aims to reduce fragmentation between weather, rainfall, river-flow context and official water observations.

- **Fragmented information:** bring source-labelled map layers and links into one place instead of requiring people to check many portals.
- **Rainfall and river conditions are hard to compare:** show current weather estimates, radar context, historical rainfall and modelled river flow together, with timestamps and caveats.
- **Uneven monitoring coverage:** expose where public station observations exist, where they are stale, and where there are gaps. Missing data must be shown as unknown, never as proof that a location is safe.
- **Lead-time for preparedness:** help an analyst or emergency manager notice a concerning combination early enough to verify it against official forecasts and take proportionate preparedness steps.
- **Weak traceability after an event:** preserve source, timestamp, station, data-quality and review information so later investigators can reconstruct what the dashboard showed and when.
- **Human and infrastructure contributors:** create a structured way to record and review dam/reservoir operations, drainage blockage, land-use changes and other potential contributors alongside the meteorological context, without automatically assigning blame.

## 2. How it could support early alerts

FloodWatch can be used as an **early-awareness layer**, not as an autonomous evacuation authority.

1. **Observe:** ingest time-stamped rainfall/radar, weather forecasts, river-flow forecasts and official gauge/reservoir observations where available.
2. **Check quality:** show provider, observation/forecast time, update age, units, missing values and geographic coverage. Mark stale or contradictory data clearly.
3. **Detect a potential concern:** future alert logic could combine forecast rainfall accumulation, river-flow trend/threshold exceedance, upstream observations, official warnings and known exposure. Each rule must be documented and locally calibrated.
4. **Cross-check:** compare with official India Meteorological Department (IMD), Central Water Commission (CWC), state disaster-management authority and district administration bulletins. Confirm the affected place, forecast window and confidence.
5. **Notify responsibly:** a future notification service could send opt-in SMS/email/app alerts to subscribed users and authorized response teams, with location, issue time, expected window, evidence links, uncertainty and clear instructions to follow official advisories.
6. **Track acknowledgement:** log who reviewed, acknowledged, escalated or closed an alert and when. Provide corrections/expiry so old alerts are not mistaken for current ones.
7. **After-action review:** compare forecast with observed outcomes and record false alarms, missed events, delivery failures and changes needed.

**Current implementation boundary:** the public map has live API-dependent weather/radar and external modelled river-flow context, plus a public water-observation explorer. It does not currently operate a validated FloodWatch flood-warning classifier, send emergency notifications, estimate local inundation depth, or guarantee warning lead time. Do not advertise those as live features until implemented, independently tested and monitored.

**Infrastructure evidence notebook now in the dashboard:** users can manually record public-source URLs and notes for dam/reservoir inspection or release bulletins, embankment/drainage maintenance, land-use documents and official warning/response timelines. Records are stored only in the current browser and can be exported as JSON; they are not sent to a server, published for other users, or automatically verified. This is a prototype evidence notebook—not a shared official register and not a structural-safety assessment.

## 3. Human-made and infrastructure contributors: accountability module proposal

Floods are often multi-causal. Rainfall and river flow interact with land use, drainage, reservoir operations, infrastructure condition and settlement exposure. FloodWatch should record evidence and timelines—not infer negligence from a flood map.

| Evidence category | Data to record | How it helps review |
|---|---|---|
| Dam/reservoir operations | Verified reservoir level, inflow/outflow, gate-release bulletin, timestamp, operator/agency, published operating rule and source link | Reconstruct whether releases and downstream conditions were communicated and managed under applicable rules |
| Dam safety/condition | Latest public inspection or safety-review date, published condition/status, known restrictions, official report reference | Show whether safety information is current; never invent a structural-strength score |
| River and drainage capacity | Gauge levels/flow, official flood marks, culvert/drain dimensions where documented, blockage/maintenance reports and inspection dates | Identify documented conveyance constraints and maintenance issues |
| Land-use and floodplain change | Dated official land-cover/land-use layers, development permissions where public, encroachment records and floodplain maps | Compare development/exposure changes over time without asserting causation from correlation alone |
| Embankments, levees and flood defences | Official inspection, repair history, breach/erosion reports, geotagged evidence and status of corrective actions | Track reported defects and whether remediation was recorded |
| Warning and response timeline | Official bulletin issue time, publication channel, alert dispatch/delivery/acknowledgement time, evacuation/closure decision records where public | Audit warning latency, communication gaps and response actions |
| Post-event evidence | Geotagged, time-stamped photographs/reports, water marks, affected locations, source reliability and reviewer status | Support transparent investigation and preserve evidence for authorized investigators |

### Minimum accountability record

Each entry should contain: unique record ID; location and coordinates (with precision); event/time window; observation or document type; original source URL or document ID; issuing organization; publication and retrieval timestamps; units; quality/confidence label; evidence attachment/hash where lawful; reviewer and review time; correction history; and current status.

Use neutral statuses such as **unverified report**, **official record**, **corroborated**, **disputed**, and **closed after review**. Preserve changes in an append-only audit log. Separate observed facts from hypotheses, and allow the named agency/person to submit a documented correction. Personal data, security-sensitive dam details and non-public operational information must not be published without lawful authorization.

### Dam strength is not something to guess

A public dashboard cannot determine a dam's structural strength from reservoir level, satellite imagery or rainfall alone. That requires qualified dam-safety engineering, inspections, design/maintenance records and authorized instrumentation. FloodWatch should show only verified, public, appropriately cleared safety status and the date/source of the latest inspection. If the record is unavailable or outdated, display **“safety status not verified / last report date unknown”**, not “unsafe” or “safe”.

## 4. Accountability and alerting guardrails

- Never present an external weather/flood-model estimate as an official gauge reading or as a FloodWatch-trained forecast.
- Never label a location safe just because no station data is available.
- Do not automatically accuse an agency, operator or developer of causing a flood. Display evidence and uncertainty; causal attribution belongs to a documented, competent investigation.
- Do not use unverified crowd reports alone to issue high-consequence public warnings.
- Use official thresholds and approved alert protocols, reviewed by hydrologists and local disaster-management authorities; test against historical events and measure false negatives as well as false positives.
- Clearly show source, issue time, valid period, affected area, uncertainty, last refresh and expiry.
- Keep a human approval step for consequential alerts until the system has formal authorization, validation, monitoring and incident-response procedures.
- Provide an accessible correction/feedback channel and maintain a record of alert revisions.

## 5. Submission-safe summary

> FloodWatch South India consolidates public weather, rainfall, modelled river-flow and water-observation context in a map-oriented prototype. It is designed to support earlier situational awareness, expose data gaps and make source provenance easier to inspect. A proposed accountability layer would record verified dam/reservoir operation and inspection documents, drainage/land-use evidence, and warning-response timelines so post-flood reviews can be evidence-based. Automated alerts and infrastructure accountability scoring are not yet operational features; warnings require official-source cross-checking and authorized review. FloodWatch does not independently certify dam strength or determine legal responsibility.
