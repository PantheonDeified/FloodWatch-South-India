# Water-observation pipeline: verified run and remaining checks

## What the repository logs prove

A successful GitHub Actions run, [Refresh official water observations #39078125961](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39078125961), completed on 2026-10-17. The collector produced a snapshot generated at `2026-10-17T23:12:45.397895+00:00`.

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

The newest timestamp string reported in that snapshot was `2026-10-17T12:10:00`. The collector currently preserves a raw timestamp and explicitly says source timezone semantics are not specified. Therefore, do not label every station as real-time or classify freshness as exact until the timestamp timezone and provider update schedule are confirmed.

## Data-quality caveats to resolve

- **Station coordinates:** 34 of the 407 records have no latitude/longitude. They can be listed, but must not be placed on the map using guessed coordinates.
- **State coverage:** 358 records are labelled as belonging to one of the five main FloodWatch states (Andhra Pradesh, Karnataka, Kerala, Tamil Nadu and Telangana). Another 15 records are labelled Maharashtra, Chhattisgarh or Madhya Pradesh, reflecting broader basin/source coverage. The rest lack a state value. Keep records with known out-of-area locations from being misrepresented as a station inside the five-state core.
- **Freshness:** manual/daily and hourly telemetry resources differ. Several resources returned no usable rows, and successful resources can have very different newest timestamps. The site must show timestamp and freshness per record, not use the collector retrieval time as the observation time.
- **Measurement semantics:** river level, river discharge, reservoir level, reservoir storage and release/discharge are different measurements. Keep source units and labels visible. Do not infer a danger level if the official source did not supply one.
- **Source timezone:** until the source documents its timezone, show the raw reported timestamp and mark its timezone as unspecified instead of silently claiming UTC or local time.

## Workflow change made

The workflow's push trigger used to include `data/water-observations.json`, which the workflow itself commits. That can trigger another collection run after publishing a snapshot. The trigger now runs on changes to the source registry/scripts/workflow, a manual request, or the six-hour schedule—but not on the output file's own commit.

The workflow now refuses to publish a snapshot if the collector returns an empty observation list, the record count does not match the list, or the generation timestamp is missing. This prevents a temporary source outage from replacing a working snapshot with an empty file.

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
- [Successful Action run used for this report](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39078125961)
