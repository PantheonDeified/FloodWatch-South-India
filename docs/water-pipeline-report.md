# Water data quality audit — initial status

Checked 2026-10-18 from repository source and the successful collector run report. This is an initial audit; I could not independently download and inspect all 407 raw records in this execution environment, so no individual reading is silently corrected.

## Known snapshot facts

The documented successful run on 2026-10-18 created a snapshot generated at 2026-10-18T02:32:25Z, with 407 records from 37 resource files across 20 configured source pages.

| Measurement type | Count |
|---|---:|
| River discharge | 201 |
| River level | 145 |
| Reservoir level | 44 |
| Reservoir storage | 9 |
| Reservoir/regulator discharge | 8 |
| **Total** | **407** |

## Known quality issues from the run report

- 34 records have no coordinates; list them in the table but do not place them on the map.
- 15 records are labelled Maharashtra, Chhattisgarh or Madhya Pradesh rather than the five core states. Keep out-of-area records from being presented as South India stations without a clear geographic reason.
- Some resources return no usable rows or much older reported timestamps.
- A reported Hemavathy Dam timestamp 2026-10-18T12:10:00 is later than the documented snapshot generation time 2026-10-18T02:32:25Z if both are interpreted on the same clock. Since the source timezone is not specified, do not rewrite or call it fresh; mark it unknown/future pending source-specific verification.
- River level, discharge, reservoir level, storage and release are different quantities with distinct units. Never relabel one as another.
- Hourly telemetry and manually reported daily observations have different expected refresh schedules.

## Validation already in code

The GitHub Actions collector workflow runs validator unit tests, checks JSON structure, and calls data_pipeline/scripts/validate_water_snapshot.py before publishing. Its documented checks include non-empty snapshot/count consistency, record IDs, supported measurement types, numeric values, units, coordinate pairs, source HTTPS links and timestamp parsing. It warns on unknown time zones, missing coordinates/state, out-of-core-area labels and future-looking timestamps.

## Required next steps

1. Run the validator on the latest file and retain its output in the report.
2. Produce a repeatable audit export of missing coordinates, missing state/district, unknown source timezone, future timestamps, duplicate station/time/type records and per-source last-observed timestamp.
3. Check resource-specific unit conventions and station identifiers against source metadata. Do not convert units unless the source's original units are known.
4. Verify coordinate/state coverage against station metadata; never guess coordinates.
5. Test the browser station table and map overlay against the published snapshot after Pages deploys.
6. Keep a source-specific freshness policy: do not apply one universal age threshold to hourly telemetry and manual/daily resources.
7. Only after these checks, use vetted historical discharge records and aligned weather inputs for baseline or machine-learning experiments.

## References

- [Run report](water-pipeline-run-report.md)
- [Snapshot](../data/water-observations.json)
- [Source registry](../data_pipeline/sources.json)
- [Collector](../data_pipeline/scripts/refresh_water_observations.py)
- [Validator](../data_pipeline/scripts/validate_water_snapshot.py)
- [Validator tests](../data_pipeline/tests/test_validate_water_snapshot.py)

The public snapshot is not a complete, uniformly real-time South India water network. Do not interpret the table as an official flood warning.
