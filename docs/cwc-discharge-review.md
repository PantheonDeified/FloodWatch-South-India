# CWC historical discharge: preliminary review summary

**Status:** preliminary screening only. This report was derived from the historical archive artifact attached to [workflow run 39110516369](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39110516369), generated before the exact-resource provenance validator and collision-safe resource filenames were added. Rerun the current [historical hydrology workflow](https://github.com/PantheonDeified/FloodWatch-South-India/actions/workflows/download-historical-hydrology.yml) to regenerate the outputs with the new provenance checks.

## Ingestion facts from that run

| Metric | Reported result |
|---|---:|
| NWDP raw resources downloaded | 10 |
| Raw input rows | 1,876,539 |
| Normalized discharge rows | 1,876,509 |
| Rows rejected for negative discharge | 30 |
| Station IDs represented | 241 |
| Normalized timestamp range | 1965-01-01 to 2025-12-31 |

Stations appeared across five states: Tamil Nadu (68), Karnataka (66), Kerala (40), Andhra Pradesh (37), and Telangana (30). These counts reflect station labels generated from the source fields; they do not prove independent station identity or complete geographic coverage.

## Preliminary data-quality findings

The previous station audit reported:

- **210 of 241 station IDs** had at least one same-calendar-date duplicate; these summed to 16,615 duplicate rows.
- **143 stations** were flagged for sparse calendar coverage (more than 10% missing days across the station's observed span).
- **7 stations** had maximum discharge above the conservative 100,000 m³/s review threshold.
- **1 station** had multiple station-name variants.

These are review flags, not automatic rejection criteria. The source is labelled manual daily discharge, so same-day duplicates warrant investigation, but the audit does not decide whether a repeated observation is erroneous. Extreme positive values are retained for domain review, not deleted. Gaps must not be filled with zero.

## First-pass review queue estimate

Using the current queue's default structural thresholds—at least 365 days of calendar span, at least 180 unique observation dates, and at least 75% calendar-date coverage—this earlier audit yields a provisional triage:

| Triage status | Station count |
|---|---:|
| Priority for manual station review | 9 |
| Manual data review required (identity conflict or low calendar coverage) | 75 |
| Manual quality review required (data-quality flags) | 148 |
| Insufficient history for priority review | 9 |
| **Total** | **241** |

This is a pre-rebuild estimate derived from the archived audit and matches the currently committed queue logic; the regenerated workflow report is the authoritative result. Priority means “review this station first,” not that it is ready for model training.

## Non-negotiable gates

1. **Coordinate gate:** the generated station catalogue marks all coordinates unverified. Do not join weather grids or map station points until a reviewer independently checks each location and records a reliable coordinate source URL.
2. **Provenance gate:** the latest workflow now compares normalized-row resource URLs, title and SHA-256 to the download manifest and recomputes raw checksums. The previous artifact predates this gate and cannot count as a pass for the new check.
3. **Measurement gate:** confirm source units and station identity. Do not convert water level to discharge without a validated rating curve or official conversion.
4. **Model gate:** build weather/discharge features only for reviewed stations with suitable coverage, then evaluate chronologically against a persistence baseline. No validated local flood forecast follows from normalization or this screening report.

## Reproduce

After manually running the workflow and downloading the artifact, inspect:

- `cwc_discharge_quality_report.json`
- `cwc_discharge_station_audit.json`
- `cwc_station_catalog_review.csv` and `cwc_station_catalog_review.json`
- `cwc_station_research_readiness.csv` and `cwc_station_research_readiness.json`
- `cwc_discharge_provenance_report.json`

The artifact expires after seven days, so preserve it or store the needed reports in approved project storage. Raw data and generated bulk tables should remain artifacts rather than Git commits.
