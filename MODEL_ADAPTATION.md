# Evaluating Google's open hydrology framework for FloodWatch

## Finding

Google Research's public [flood-forecasting repository](https://github.com/google-research/flood-forecasting) contains OpenHydroNet and implementations of the Mean Embedding Forecast LSTM and the former Handoff Forecast LSTM. Its README describes Mean Embedding Forecast LSTM as the current production architecture as of December 2025. It is an open-source implementation of core models, not Google's entire Flood Hub production website or pipeline.

Relevant references:
- [Google's hydrology model explanation](https://support.google.com/flood-hub/answer/15637389?hl=en)
- [OpenHydroNet repository and docs](https://github.com/google-research/flood-forecasting)
- [Flood Forecasting API and historical datasets](https://developers.google.com/flood-forecasting)
- [CWC/NWDP water-level archive](https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc)
- [HydroATLAS / HydroBASINS](https://www.hydrosheds.org/hydroatlas)

## Can it be adapted?

**Potentially yes, but only after data and validation work.** The repository supports configurable training/inference and multi-meteorological input groups. Its Flood Hub-style configuration uses a Mean Embedding Forecast LSTM, streamflow target, 365-day hindcast sequence, a 7-day forecast horizon and a probabilistic CMAL output head. Static basin attributes are inputs too. The exact production pipeline differs from the open-source implementation; copying a YAML file alone does not reproduce the production system.

The largest current blocker is target data: the NWDP/CWC dataset linked above is described as river water level. A water-level series is not discharge. The reference model predicts streamflow. We need either CWC streamflow discharge at known gauges, or station-specific rating curves with a documented validity range and uncertainty, before water-level readings can safely support a streamflow training target. Do not train on water level relabelled as m³/s.

## Recommended staged evaluation

### Stage 1 — source and station inventory
- Download South India-relevant CWC/NWDP river groups (Godavari, Krishna, Pennar, Cauvery, east-flowing rivers between Pennar and Kanyakumari, and west-flowing rivers from Tapi to Tadri where relevant).
- Inspect actual station identifiers, columns, units, time zones and minimum/maximum dates. CWC portal period labels (such as 1961–1990 and 1991–2020) are resource periods, not a guarantee that every station has complete data.
- Populate data_pipeline/gauge_catalog.csv only with coordinates and source links verified from the source itself.
- Preserve original downloaded files and checksums outside the frontend repository; store normalized derived tables separately.

### Stage 2 — watershed-to-gauge mapping
- Download a HydroBASINS basin-polygon layer and confirm its identifier fields.
- Assign each verified gauge coordinate to its polygon, preserving the polygon ID and downstream ID.
- For each selected site, generate same-subbasin and upstream-subbasin candidates using the NEXT_DOWN basin graph.
- Validate candidate pairs against named river, actual flowline, station position, upstream/downstream direction, dams/diversions and station metadata. Polygon adjacency alone is not sufficient proof of channel connectivity.
- Keep unmapped or ambiguous locations explicitly unresolved rather than selecting the nearest station blindly.

### Stage 3 — historical forcing pipeline
- Fetch a consistent meteorological reanalysis for each gauge and catchment. ERA5 is documented from 1940; ERA5-Land from 1950. Reanalysis values are gridded model estimates, not gauge observations.
- The starter script fetches daily ERA5-Land values at gauge points in five-year chunks. For an actual catchment model, replace point forcing with a reproducible basin aggregation (for example, area-weighted grid-cell means over the delineated catchment), with masks and units documented.
- Align observation and forcing timestamps; retain gaps and data lineage.

### Stage 4 — baseline and data eligibility
- First test a small set of basins with adequate discharge data, not every map point.
- Compare a simple baseline (climatology/persistence or a public hydrological product) against the candidate ML model.
- Use chronological train/validation/test splits. Avoid training and evaluating on the same years or event windows. Report per-basin and pooled metrics: NSE/KGE where appropriate, peak-flow bias, peak timing, false/missed threshold events, and missing-data coverage.
- Include event-based tests over major monsoon/flood periods and explicitly test dams/reservoirs where operations may dominate downstream flow.
- Evaluate transfer to basins withheld entirely from training to see if the model generalises across South Indian catchments.

### Stage 5 — model integration
- Run OpenHydroNet training/inference in a Python-capable backend or scheduled compute environment, not inside this static GitHub Pages HTML.
- A future API should return predictions plus issue time, valid time, model version, training-data cutoff, input freshness, uncertainty, basin/gauge ID and quality status.
- Add downstream routing or a separately validated inundation model only as its own stage. Streamflow forecasting alone does not produce a flood extent map.

## Historical periods we can realistically investigate

- **Rainfall/weather reanalysis:** ERA5 from 1940 or ERA5-Land from 1950 through the latest available complete period. For consistent multi-decade trends, use one dataset/model consistently and disclose the dataset version.
- **CWC river levels:** the NWDP portal lists multiple South Indian river-group CSV resources labelled 1961–1990, 1991–2020 and newer periods. Actual station-level coverage must be calculated from downloaded rows.
- **Google GRRR:** a published 1980–2023 global river-discharge reanalysis/reforecast dataset is listed in Google's Flood Forecasting documentation. Treat it as a research/benchmark product and check its documented access, licence and semantics before use; it is not the same as a live CWC observation.
- **Google Inundation History:** a published 1999–2020 inundation dataset is also listed by Google. It can potentially support historical map-validation research, but coverage and data-access requirements must be checked.

## Safety and integrity

FloodWatch remains an independent prototype. Do not call historical metrics official warnings or describe modelled discharge as a gauge reading. Do not display a flood probability until a model has been calibrated and externally tested for the relevant region. Always show source, model/dataset, time range and limitations.
