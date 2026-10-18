#!/usr/bin/env python3
"""Generate a source-aware Markdown data-quality report from a water snapshot.

This report summarizes the supplied snapshot; it never alters source records or
tries to infer missing coordinates, timestamps, units, or state labels.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CORE_STATES = {"Andhra Pradesh", "Karnataka", "Kerala", "Tamil Nadu", "Telangana"}
KIND_LABELS = {
    "river_level": "River level",
    "river_discharge": "River discharge",
    "reservoir_level": "Reservoir level",
    "reservoir_storage": "Reservoir storage",
    "reservoir_discharge": "Reservoir/regulator discharge",
}


def md_cell(value: Any) -> str:
    """Keep provider-controlled text safe for a Markdown table."""
    return str(value if value not in (None, "") else "—").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_report(data: dict[str, Any]) -> str:
    rows = data.get("observations", [])
    if not isinstance(rows, list):
        rows = []
    rows = [row for row in rows if isinstance(row, dict)]
    by_kind = Counter(str(row.get("kind") or "unknown") for row in rows)
    by_state = Counter(str(row.get("state") or "Unspecified") for row in rows)
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_resource: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    missing_coordinates = []
    missing_state = []
    outside_core = []
    timezone_unknown = []
    missing_district = []
    duplicate_keys = Counter()

    for row in rows:
        source = str(row.get("source_name") or "Unknown source")
        resource = str(row.get("source_resource_title") or "Unknown resource")
        by_source[source].append(row)
        by_resource[(source, resource)].append(row)
        lat, lon = row.get("latitude"), row.get("longitude")
        if lat is None and lon is None:
            missing_coordinates.append(row)
        if not str(row.get("state") or "").strip():
            missing_state.append(row)
        elif row.get("state") not in CORE_STATES:
            outside_core.append(row)
        if not str(row.get("district") or "").strip():
            missing_district.append(row)
        tz = str(row.get("source_timezone") or "").strip().lower()
        if not tz or "not specified" in tz or "unknown" in tz or "unspecified" in tz:
            timezone_unknown.append(row)
        station = str(row.get("station_id") or row.get("station_name") or "").strip().lower()
        timestamp = str(row.get("observed_at") or "").strip()
        kind = str(row.get("kind") or "")
        if station and timestamp and kind:
            duplicate_keys[(station, kind, timestamp)] += 1

    duplicate_groups = sum(1 for count in duplicate_keys.values() if count > 1)
    generated = data.get("generated_at_utc", "unknown")
    lines = [
        "# Water-observation snapshot — automated quality audit",
        "",
        f"- Snapshot generation timestamp: **{md_cell(generated)}**",
        f"- Records in snapshot: **{len(rows)}**",
        f"- Resource files checked: **{md_cell(data.get('resource_count_checked'))}**",
        f"- Report generated from this snapshot by the GitHub Actions pipeline; source records are not modified.",
        "",
        "## Measurement types",
        "",
        "| Measurement | Records |",
        "|---|---:|",
    ]
    for kind in sorted(set(by_kind) | set(KIND_LABELS)):
        if by_kind.get(kind, 0):
            lines.append(f"| {md_cell(KIND_LABELS.get(kind, kind))} | {by_kind[kind]} |")
    lines += [
        "",
        "## Quality indicators",
        "",
        "| Check | Count | Meaning |",
        "|---|---:|---|",
        f"| Missing both coordinates | {len(missing_coordinates)} | Do not plot these records as station points |",
        f"| Missing state | {len(missing_state)} | State coverage cannot be assigned from the record |",
        f"| Labelled outside five core states | {len(outside_core)} | Review geography; do not present as an in-area station by default |",
        f"| Missing district | {len(missing_district)} | District-level filtering may be incomplete |",
        f"| Source timezone unspecified | {len(timezone_unknown)} | Preserve the reported timestamp; do not assume UTC or local time |",
        f"| Duplicate station/type/timestamp groups | {duplicate_groups} | Review possible overlap; records are retained in this report |",
        "",
        "## Records by state label",
        "",
        "| State label | Records |",
        "|---|---:|",
    ]
    for state, count in sorted(by_state.items(), key=lambda pair: (-pair[1], pair[0].casefold())):
        lines.append(f"| {md_cell(state)} | {count} |")
    lines += [
        "",
        "## Records by configured source",
        "",
        "| Configured source | Records | Resources represented | Latest timestamp string in snapshot |",
        "|---|---:|---:|---|",
    ]
    for source, source_rows in sorted(by_source.items(), key=lambda pair: pair[0].casefold()):
        resource_count = len({str(r.get("source_resource_title") or "Unknown resource") for r in source_rows})
        timestamps = [str(r.get("observed_at") or "") for r in source_rows if r.get("observed_at")]
        latest = max(timestamps) if timestamps else "—"
        lines.append(f"| {md_cell(source)} | {len(source_rows)} | {resource_count} | {md_cell(latest)} |")
    # Report the collector's per-page/resource outcomes, including failures and empty CSVs.
    source_reports = data.get("sources", [])
    if not isinstance(source_reports, list):
        source_reports = []
    lines += [
        "",
        "## Collection outcomes",
        "",
        "These statuses describe what the collector could retrieve during this run; they do not prove that a source's latest observation is current.",
        "",
        "| Configured source page | Status | Resources discovered | Resource scans completed | Resource errors |",
        "|---|---|---:|---:|---:|",
    ]
    for report in source_reports:
        if not isinstance(report, dict):
            continue
        resources = report.get("resource_reports", [])
        errors = report.get("resource_errors", [])
        if not isinstance(resources, list):
            resources = []
        if not isinstance(errors, list):
            errors = []
        discovered = report.get("resources_discovered", report.get("resources", len(resources) + len(errors)))
        lines.append(
            f"| {md_cell(report.get('source_name'))} | {md_cell(report.get('status'))} | "
            f"{md_cell(discovered)} | {len(resources)} | {len(errors)} |"
        )
        if report.get("error"):
            lines.append(f"\n- **Source-page error — {md_cell(report.get('source_name'))}:** {md_cell(report.get('error'))}")
        for error in errors:
            if isinstance(error, dict):
                lines.append(
                    f"\n- **Resource error — {md_cell(report.get('source_name'))} / "
                    f"{md_cell(error.get('resource_title'))}:** {md_cell(error.get('error'))}"
                )
        for resource in resources:
            if isinstance(resource, dict) and resource.get("status") == "no_usable_records":
                lines.append(
                    f"\n- **No usable records — {md_cell(report.get('source_name'))} / "
                    f"{md_cell(resource.get('resource_title'))}:** scanned "
                    f"{md_cell(resource.get('rows_scanned', 0))} rows without a usable timestamped numeric record"
                )
    lines += [
        "",
        "## Units reported by the collector",
        "",
        "| Measurement type | Source unit label | Records |",
        "|---|---|---:|",
    ]
    unit_counts = Counter((str(row.get("kind") or "unknown"), str(row.get("unit") or "unspecified")) for row in rows)
    for (kind, unit), count in sorted(unit_counts.items()):
        lines.append(f"| {md_cell(KIND_LABELS.get(kind, kind))} | {md_cell(unit)} | {count} |")
    lines += [
        "",
        "Unit labels such as `source-defined` are intentionally not converted or assumed equivalent. Verify them against the original resource metadata before comparing values across stations.",
    ]
    lines += [
        "",
        "## Limits and review actions",
        "",
        "- A successful collection does not mean every river, dam or state is covered or updated in real time.",
        "- The latest timestamp above is the lexicographically greatest normalized timestamp string. Where source timezone semantics are unknown, it is not a definitive cross-source freshness ranking.",
        "- Check units and measurement types against source metadata; river level is not interchangeable with river discharge.",
        "- Do not infer danger thresholds unless the authoritative source supplies a compatible threshold and unit.",
        "- Do not invent coordinates, force missing readings to zero, silently rewrite timestamps, or delete suspicious values. Investigate source metadata and document any correction.",
        "- This snapshot is contextual source-reported data, not an official warning and not by itself a validated flood prediction.",
        "",
        "## Provenance",
        "",
        "- Source registry: [data_pipeline/sources.json](../data_pipeline/sources.json)",
        "- Collector: [refresh_water_observations.py](../data_pipeline/scripts/refresh_water_observations.py)",
        "- Structural validator: [validate_water_snapshot.py](../data_pipeline/scripts/validate_water_snapshot.py)",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/water-observations.json"))
    parser.add_argument("--out", type=Path, default=Path("docs/water-pipeline-report.md"))
    args = parser.parse_args()
    try:
        data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read valid snapshot JSON: {exc}")
    if not isinstance(data, dict):
        parser.error("snapshot root must be a JSON object")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_report(data), encoding="utf-8")
    print(f"Wrote quality audit to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
