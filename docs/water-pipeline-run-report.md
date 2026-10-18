# Water-observation pipeline: verified run and remaining checks

## What the repository logs prove

A successful GitHub Actions run, [Refresh official water observations #39090443542](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39090443542), completed on 2026-10-18. The collector produced a snapshot generated at `2026-10-18T02:32:25.327209+00:00`. The same collection also confirms the new workflow guard accepted the non-empty snapshot and published it.

| Check | Result |
|---|---:|
| Observation records produced | 407 |
| Resource files attempted | 37 |
| Configured public source pages | 20 |
| River discharge records | 201 |
| River level records | 145 |
| Reservoir level records | 44 |
| Reservoir storage records | 9 |
| Reservoir / regulator discharge records | 8 |

The newest timestamp string reported in the latest snapshot was `2026-10-18T12:10:00` for Hemavathy Dam (raw source string `18-10-2026 12:10:00`). The snapshot's generation time was `2026-10-18T02:32:25Z`. Interpreted in the browser's India-local time, this appears to be a future timestamp; the site should label it **Future timestamp / unknown freshness**, not recent. Because the collector explicitly says the source timezone is unspecified, verify the source's timezone/meaning before correcting or using this timestamp. Do not label every station as real-time or classify freshness as exact until source timezone and provider update schedules are confirmed.

## Data-quality caveats to resolve

- **Station coordinates:** 34 of the 407 records have no latitude/longitude. They can be listed, but must not be placed on the map using guessed coordinates.
- **State coverage:** 358 records are labelled as belonging to one of the five main FloodWatch states (Andhra Pradesh, Karnataka, Kerala, Tamil Nadu and Telangana). Another 15 records are labelled Maharashtra, Chhattisgarh or Madhya Pradesh, reflecting broader basin/source coverage. The rest lack a state value. Keep records with known out-of-area locations from being misrepresented as a station inside the five-state core.
- **Freshness:** manual/daily and hourly telemetry resources differ. Several resources returned no usable rows, and successful resources can have very different newest timestamps. The site must show timestamp and freshness per record, not use the collector retrieval time as the observation time.
- **Measurement semantics:** river level, river discharge, reservoir level, reservoir storage and release/discharge are different measurements. Keep source units and labels visible. Do not infer a danger level if the official source did not supply one.
- **Source timezone:** until the source documents its timezone, show the raw reported timestamp and mark its timezone as unspecified instead of silently claiming UTC or local time.

## Workflow change made

The workflow's push trigger used to include `data/water-observations.json`, which the workflow itself commits. That can trigger another collection run after publishing a snapshot. The trigger now runs on changes to the source registry/scripts/workflow, a manual request, or the six-hour schedule—but not on the output file's own commit.

The workflow now refuses to publish a snapshot if the collector returns an empty observation list, the record count does not match the list, or the generation timestamp is missing. This prevents a temporary source outage from replacing a working snapshot with an empty file. Run #39090443542 passed the guard with 407 records. The site already classifies timestamps more than one hour in the future as unknown rather than recent.

## Automated validation added

The workflow now runs unit tests from `data_pipeline/tests/test_validate_water_snapshot.py` and calls `data_pipeline/scripts/validate_water_snapshot.py` before publishing. The validator fails on an empty snapshot, mismatched record counts, duplicate/missing IDs, unsupported measurement types, non-numeric values, invalid or half-missing coordinates, unparseable timestamps, and missing/invalid HTTPS source links. It reports warnings for records without coordinates/state, out-of-core-area labels, unspecified source timezones, and timestamps that appear later than the collector clock.

Run the check locally from the repository root:

```bash
python -m unittest discover -s data_pipeline/tests -p "test_*.py"
python data_pipeline/scripts/validate_water_snapshot.py --snapshot data/water-observations.json
```

Warnings require human review. In particular, do not automatically rewrite a timestamp when the source timezone isn't confirmed.

## How to check the next run

1. Open the [Actions workflow](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/refresh-water-observations.yml).
2. Run **Refresh official water observations** manually, or wait for the scheduled run.
3. Check the run logs for observation count, resources checked, latest reported observation timestamp, and resource-level errors.
4. Open the [published snapshot](../data/water-observations.json) and verify timestamps and locations in the website after GitHub Pages deploys.
5. Treat the values as public source-reported observations, not a complete all-dam network and not an official flood warning.

## References

- [Public snapshot](../data/water-observations.json)
- [Source registry](../data_pipeline/sources.json)
- [Collector](../data_pipeline/scripts/refresh_water_observations.py)
- [Refresh workflow](../.github/workflows/refresh-water-observations.yml)
- [Latest successful Action run used for this report](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39090443542)
