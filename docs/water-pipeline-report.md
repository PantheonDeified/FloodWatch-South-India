# Water-observation snapshot — automated quality audit

- Snapshot generation timestamp: **2026-10-18T07:09:02.282063+00:00**
- Records in snapshot: **407**
- Resource files checked: **37**
- Report generated from this snapshot by the GitHub Actions pipeline; source records are not modified.

## Measurement types

| Measurement | Records |
|---|---:|
| Reservoir/regulator discharge | 8 |
| Reservoir level | 44 |
| Reservoir storage | 9 |
| River discharge | 201 |
| River level | 145 |

## Quality indicators

| Check | Count | Meaning |
|---|---:|---|
| Missing both coordinates | 34 | Do not plot these records as station points |
| Missing state | 34 | State coverage cannot be assigned from the record |
| Labelled outside five core states | 15 | Review geography; do not present as an in-area station by default |
| Missing district | 34 | District-level filtering may be incomplete |
| Source timezone unspecified | 407 | Preserve the reported timestamp; do not assume UTC or local time |
| Duplicate station/type/timestamp groups | 0 | Review possible overlap; records are retained in this report |

## Records by state label

| State label | Records |
|---|---:|
| Andhra Pradesh | 102 |
| Tamil Nadu | 81 |
| Karnataka | 70 |
| Telangana | 64 |
| Kerala | 41 |
| Unspecified | 34 |
| Maharashtra | 10 |
| Chhattisgarh | 4 |
| Madhya Pradesh | 1 |

## Records by configured source

| Configured source | Records | Resources represented | Latest timestamp string in snapshot |
|---|---:|---:|---|
| Andhra Pradesh reservoir storage and level | 19 | 2 | 2026-08-31T06:00:00 |
| Andhra Pradesh river discharge | 1 | 1 | 2026-02-28T08:00:00 |
| Andhra Pradesh river telemetry | 41 | 4 | 2026-10-16T23:00:00 |
| Central Water Commission river discharge | 200 | 5 | 2026-10-17T09:15:00 |
| Central Water Commission river telemetry | 74 | 5 | 2026-10-16T03:30:00 |
| Flood Flow Canal Head Regulator discharge | 1 | 1 | 2026-08-20T14:00:00 |
| Kaddam head regulator release/discharge | 1 | 1 | 2026-08-20T14:00:00 |
| Kakatiya Canal Head Regulator discharge | 1 | 1 | 2026-08-20T15:00:00 |
| Karnataka reservoir data | 34 | 1 | 2026-10-18T12:10:00 |
| Lakshmi Canal Head Regulator discharge | 1 | 1 | 2026-08-20T14:00:00 |
| Lower Manair Canal Head Regulator discharge | 1 | 1 | 2026-08-20T14:00:00 |
| Lower Manair Dam 2 discharge | 1 | 1 | 2026-08-20T14:00:00 |
| Saraswati Canal Head Regulator discharge | 1 | 1 | 2026-08-20T14:00:00 |
| Sri Ram Sagar Dam release/discharge | 1 | 1 | 2026-08-20T15:00:00 |
| Tamil Nadu river telemetry | 4 | 1 | 2026-10-16T23:00:00 |
| Telangana river telemetry | 26 | 2 | 2026-10-16T23:00:00 |

## Collection outcomes

These statuses describe what the collector could retrieve during this run; they do not prove that a source's latest observation is current.

| Configured source page | Status | Resources discovered | Resource scans completed | Resource errors |
|---|---|---:|---:|---:|
| Central Water Commission river telemetry | checked | 6 | 6 | 0 |

- **No usable records — Central Water Commission river telemetry / River Water Level CWC Pennar (2026 - 2030) Telemetry Hourly CSV:** scanned 0 rows without a usable timestamped numeric record
| Andhra Pradesh river telemetry | checked | 4 | 4 | 0 |
| Telangana river telemetry | checked | 2 | 2 | 0 |
| Kerala river telemetry | checked | 4 | 4 | 0 |

- **No usable records — Kerala river telemetry / River Water Level Kerala_SW - (2026 - 2030) Telemetry Hourly CSV:** scanned 0 rows without a usable timestamped numeric record

- **No usable records — Kerala river telemetry / River Water Level Kerala_SW Tapi (2026 - 2030) Telemetry Hourly CSV:** scanned 0 rows without a usable timestamped numeric record

- **No usable records — Kerala river telemetry / River Water Level Kerala_SW Narmada (2026 - 2030) Telemetry Hourly CSV:** scanned 0 rows without a usable timestamped numeric record

- **No usable records — Kerala river telemetry / River Water Level Kerala_SW West flowing rivers from Tapi to Tadri (2026 - 2030) Telemetry Hourly CSV:** scanned 0 rows without a usable timestamped numeric record
| Tamil Nadu river telemetry | checked | 1 | 1 | 0 |
| Andhra Pradesh reservoir storage and level | checked | 2 | 2 | 0 |
| Karnataka reservoir data | checked | 1 | 1 | 0 |
| Sri Ram Sagar Dam release/discharge | checked | 1 | 1 | 0 |
| Kaddam head regulator release/discharge | checked | 1 | 1 | 0 |
| Central Water Commission river discharge | checked | 5 | 5 | 0 |
| Andhra Pradesh river discharge | checked | 1 | 1 | 0 |
| Telangana river discharge | checked | 1 | 1 | 0 |

- **No usable records — Telangana river discharge / River Discharge Telangana_SW Telangana (2026 - 2030) Manual Daily CSV:** scanned 0 rows without a usable timestamped numeric record
| Kerala river discharge | checked | 1 | 1 | 0 |

- **No usable records — Kerala river discharge / River Discharge Kerala_SW Kerala (2026 - 2030) Manual Daily CSV:** scanned 0 rows without a usable timestamped numeric record
| Tamil Nadu river discharge | checked | 1 | 1 | 0 |

- **No usable records — Tamil Nadu river discharge / River Discharge Tamil_Nadu_SW_GW Tamil Nadu (2026 - 2030) Manual Daily CSV:** scanned 0 rows without a usable timestamped numeric record
| Flood Flow Canal Head Regulator discharge | checked | 1 | 1 | 0 |
| Lower Manair Dam 2 discharge | checked | 1 | 1 | 0 |
| Saraswati Canal Head Regulator discharge | checked | 1 | 1 | 0 |
| Lower Manair Canal Head Regulator discharge | checked | 1 | 1 | 0 |
| Lakshmi Canal Head Regulator discharge | checked | 1 | 1 | 0 |
| Kakatiya Canal Head Regulator discharge | checked | 1 | 1 | 0 |

## Units reported by the collector

| Measurement type | Source unit label | Records |
|---|---|---:|
| Reservoir/regulator discharge | cusec | 8 |
| Reservoir level | m | 10 |
| Reservoir level | source-defined | 34 |
| Reservoir storage | source-defined | 9 |
| River discharge | m3/s | 201 |
| River level | m | 145 |

Unit labels such as `source-defined` are intentionally not converted or assumed equivalent. Verify them against the original resource metadata before comparing values across stations.

## Limits and review actions

- A successful collection does not mean every river, dam or state is covered or updated in real time.
- The latest timestamp above is the lexicographically greatest normalized timestamp string. Where source timezone semantics are unknown, it is not a definitive cross-source freshness ranking.
- Check units and measurement types against source metadata; river level is not interchangeable with river discharge.
- Do not infer danger thresholds unless the authoritative source supplies a compatible threshold and unit.
- Do not invent coordinates, force missing readings to zero, silently rewrite timestamps, or delete suspicious values. Investigate source metadata and document any correction.
- This snapshot is contextual source-reported data, not an official warning and not by itself a validated flood prediction.

## Provenance

- Source registry: [data_pipeline/sources.json](../data_pipeline/sources.json)
- Collector: [refresh_water_observations.py](../data_pipeline/scripts/refresh_water_observations.py)
- Structural validator: [validate_water_snapshot.py](../data_pipeline/scripts/validate_water_snapshot.py)
