# FloodWatch historical-data pipeline

This folder is the first reproducible data-ingestion and basin-mapping step for FloodWatch South India. It deliberately separates observations from modelled/reanalysis data. Nothing here should be described as a production flood forecast until a hydrology model has been trained and tested on suitable South Indian river data.

## Verified source inventory

| Source | What it provides | Historical range documented | How FloodWatch should use it |
|---|---|---|---|
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | ERA5 / ERA5-Land reanalysis at a coordinate | ERA5 from 1940; ERA5-Land from 1950; ERA5-Land is about 0.1° / 11 km | Consistent multi-decade weather context. These are reanalysis estimates, not direct rain-gauge readings. The fetch script defaults to ERA5-Land from 1950 and stops 7 days before today to avoid presenting delayed reanalysis as current. |
| [NWDP/CWC hourly river-water-level telemetry archive](https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc) | CWC station-based water-level time series with station identifiers and geographic hierarchy | Portal lists river-group CSV resources for 1961–1990, 1991–2020 and newer periods; coverage varies by resource | Download the relevant South Indian river-group CSV, inspect actual rows, then normalize with the import script. A resource title is not proof every station has complete observations for the whole period. |
| [NWDP/CWC daily river-discharge archive](https://nwdp.nwic.gov.in/dataset/river-discharge-manual-dailly-central-water-commission-cwc) | CWC daily observed discharge records by station | State-specific resources include 1950–2000 and 2001–2025 periods plus newer 2026–2030 resources; actual coverage varies | Primary target candidate for a local streamflow model. Inspect station continuity, discharge units, source schema and station IDs before normalization. |
| [CWC Flood Forecasting System](https://ffs.india-water.gov.in/) | Official station and forecast context | Current portal | Verification/reference link; this pipeline does not scrape it or claim its display is a public API. |
| [Google Flood Forecasting API documentation](https://developers.google.com/flood-forecasting) | Reference to historical data products and API access | GRRR river-discharge reanalysis/reforecast: 1980–2023; inundation history: 1999–2020 | Benchmark/comparison source if access and terms permit. Google says real-time API access requires approval and a key; don't assume API access is enabled. |
| [HydroSHEDS HydroATLAS / HydroBASINS](https://www.hydrosheds.org/hydroatlas) | Basin polygons, river-network and catchment attributes | Static geospatial layers | Assign verified gauge coordinates to basin polygons. This is a first spatial mapping stage, not proof that two points are on the same connected river reach. |

## What this pipeline creates

1. Daily ERA5-Land weather rows at each verified gauge coordinate via fetch_historical_weather.py. This is point weather, not an area-weighted basin average.
2. A normalized CWC gauge-level time-series format while preserving source station ID, timestamp, source file and units via normalize_cwc_levels.py.
3. A GIS assignment from station coordinates to HydroBASINS polygons and candidate upstream basin relationships for selected sites via assign_gauges_to_basins.py. All proposed matches require channel/river and station metadata review.
4. A source manifest and a data-quality report so missing intervals, duplicate timestamps, coordinates and provenance are visible.

## Research LSTM training and inference

Only train a single-gauge LSTM after the input tables have been verified and contain enough continuous **observed discharge** history. Do not use the public 407-record snapshot as a substitute for a curated historical daily discharge table; it mixes measurement types and timestamp quality.

Install the optional ML dependencies:

    python -m pip install -r data_pipeline/requirements-ml.txt

Create a normalized daily feature table with `build_event_features.py` using source-reviewed station data and weather. The exact input schema is documented in that script. Then train a gauge-specific model:

    python data_pipeline/scripts/train_streamflow_lstm.py --features path/to/features.csv --station-id VERIFIED_STATION_ID --output-dir data_pipeline/output/models

The training report includes chronological train/validation/test periods, MAE/RMSE/NSE, and an out-of-time persistence baseline. If the LSTM does not beat the persistence baseline, do not promote it as a forecast model. A saved weight file alone is not evidence of skill.

Before training, audit all stations in a feature table to see which ones meet minimum structural requirements:

    python data_pipeline/scripts/assess_streamflow_readiness.py --features path/to/features.csv --out data_pipeline/output/streamflow-readiness.json

This is a go/no-go screen for data continuity and chronological sample counts, not evidence that a station's units/provenance are correct or that a model will perform well.

For a model that has already been trained and reviewed, generate a research-only seven-day discharge output (the lead horizon and lookback must match the trained model):

    python data_pipeline/scripts/predict_streamflow_lstm.py --features path/to/features.csv --station-id VERIFIED_STATION_ID --model data_pipeline/output/models/streamflow_lstm_VERIFIED_STATION_ID.pt --scalers data_pipeline/output/models/streamflow_lstm_VERIFIED_STATION_ID.scalers.npz --output data_pipeline/output/pilot_discharge_forecast.csv

The inference script refuses incomplete recent history instead of silently filling missing observations. It writes a CSV and a metadata JSON that explicitly state the output is not validated for public warnings, does not include future weather forecasts, and is not a flood probability or inundation map. Model artifacts and raw station data are intentionally not committed to Git.

## Downloading historical river records

The official CWC telemetry portal currently lists historical archive resources for some South Indian river groups, including 1961–1990, 1991–2020, 2021–2025 and new 2026–2030 resources. The public portal's dataset metadata may be updated even when individual rows are missing or incomplete. Use the archive downloader to make a checksum-tracked local copy of the raw CSVs before analysis:

    python -m pip install -r data_pipeline/requirements.txt
    python data_pipeline/scripts/download_nwdp_history.py --out-dir data_pipeline/raw/nwdp_history --max-resources 100

By default it searches the official CWC water-level telemetry, daily river-discharge, and daily rainfall dataset pages for South India state/basin resources across available historical periods. The portal lists older archive periods for daily discharge in Andhra Pradesh, Karnataka, Kerala, Tamil Nadu and Telangana, plus newer 2021–2025 and 2026–2030 resources; each file still requires inspection for actual station coverage and valid rows. It records the dataset page, each resource page, exact download URL, byte count and SHA-256 in a local `manifest.json`. Add other official NWDP dataset pages with repeated `--source-url` arguments. Raw archives are intentionally not committed to Git; they may be large and have their own metadata/usage conditions.

You can also run this download from GitHub without installing Python locally: open the repository's **Actions** tab, choose **Download historical South India hydrology data**, select **Run workflow**, and download the `floodwatch-south-india-historical-hydrology` artifact when it completes. The artifact is temporary (7-day retention) and contains raw source files plus checksums/URLs; it is not yet a cleaned model-training dataset.

After downloading, inspect a specific file before deciding which columns and units to normalize:

    python data_pipeline/scripts/inspect_cwc_csv.py --input data_pipeline/raw/nwdp_history/<file>.csv --date-column "Date"

Do not use the source's advertised date-range title as a substitute for checking the actual first and last valid timestamps in its records. The downloader saves raw source files and provenance; it does not claim that all stations have 60 years of valid data.

## Run locally

Python 3.10+ is recommended.

    python -m pip install -r data_pipeline/requirements.txt

Create a copy of the template and fill it only with station coordinates confirmed from an official station record or verified official dataset:

    cp data_pipeline/gauge_catalog.template.csv data_pipeline/gauge_catalog.csv

Fetch ERA5-Land daily weather, chunked into five-year requests:

    python data_pipeline/scripts/fetch_historical_weather.py --gauges data_pipeline/gauge_catalog.csv --out data_pipeline/output/historical_weather_daily.csv --start 1950-01-01

Inspect an official CWC CSV after downloading it from the NWDP portal:

    python data_pipeline/scripts/inspect_cwc_csv.py --input path/to/downloaded_cwc.csv

Normalize it after confirming the exact column names and units from that file:

    python data_pipeline/scripts/normalize_cwc_levels.py --input path/to/downloaded_cwc.csv --output data_pipeline/output/cwc_water_levels.csv --station-column station_id --time-column date --level-column water_level --unit m --source-url "PASTE THE OFFICIAL NWDP RESOURCE URL"

The example column names above are examples only: actual source CSV columns can vary. Inspect the file before running the normalizer. The normalizer never converts water level to discharge.

Assign gauges to downloaded HydroBASINS polygons (GeoJSON, Shapefile or GeoPackage):

    python data_pipeline/scripts/assign_gauges_to_basins.py --gauges data_pipeline/gauge_catalog.csv --basins path/to/HydroBASINS.gpkg --out data_pipeline/output/gauge_basin_assignments.csv

For site-to-gauge candidates, provide a separate CSV with columns target_id, latitude and longitude:

    python data_pipeline/scripts/assign_gauges_to_basins.py --gauges data_pipeline/gauge_catalog.csv --basins path/to/HydroBASINS.gpkg --targets data_pipeline/sites.csv --out data_pipeline/output/gauge_basin_assignments.csv

The basin layer must contain HydroBASINS-style HYBAS_ID and NEXT_DOWN fields (the script also accepts case-insensitive field names). The script reports whether a station falls in the same sub-basin or a hydrologically upstream sub-basin whose NEXT_DOWN chain drains into the target basin. It marks all results as candidates requiring manual channel/connectivity validation. It does not automatically select the geographically nearest gauge and call it hydrologically relevant.

## Data-quality rules

- Keep station water level (usually a height relative to a local gauge datum) separate from discharge (volume per time, such as m³/s). A rating curve and its validity period are needed to convert between them; never infer discharge from water level alone.
- Never fill observation gaps with zero. Blank/missing values remain missing.
- Preserve source URL, retrieval time, raw station ID, units, and timestamp timezone/semantics.
- A gauge coordinate must have a provenance field and verification status. Do not place guessed points into the station catalogue.
- Reanalysis rainfall at a gauge coordinate is not the same as rain measured at that gauge and is not a basin-average precipitation estimate.
- Check actual minimum/maximum dates and missingness in each CSV; do not trust period labels alone.
- Baseline comparisons should state their period (for example 1991–2020). All-record extremes should use only complete rolling windows and identify the date.
- Any candidate basin/gauge pairing must be checked against river name, station metadata, flow direction, dam/diversion context and gauge datum before hydrology modelling.

## Why we are not training a Google-style model yet

The published OpenHydroNet implementation uses streamflow as the prediction target. CWC hourly water-level CSVs are not automatically streamflow records. To adapt an LSTM appropriately we need suitable discharge observations (or approved station rating curves with valid periods), verified basin attributes and meteorological forcing data aligned to each gauge. The production-like configuration also uses multiple forcing products; not all operational input feeds are necessarily freely reusable in the same way. The code is a research/engineering starting point, not a ready-made South India model.

See [MODEL_ADAPTATION.md](../MODEL_ADAPTATION.md) for the evaluation plan.
