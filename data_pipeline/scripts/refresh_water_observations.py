#!/usr/bin/env python3
"""Refresh latest records from official NWDP/NWIC water CSV resources.

This collector downloads only the newest-period CSV resources linked from a
small, documented source registry, scans records, and publishes one latest
record per station/measurement type. It does not call these data live unless
the source timestamp is fresh, and it never fabricates missing observations.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import sys
import tempfile
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DEFAULT_SOURCE_FILE = pathlib.Path("data_pipeline/sources.json")
DEFAULT_OUTPUT = pathlib.Path("data/water-observations.json")
MAX_RESOURCE_BYTES = 180 * 1024 * 1024
MAX_ROWS_PER_RESOURCE = 8_000_000
TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d",
)


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def parse_time(value: str):
    raw = (value or "").strip()
    if not raw:
        return None, ""
    candidate = raw.replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(candidate)
        return d, d.isoformat()
    except ValueError:
        pass
    for fmt in TIME_FORMATS:
        try:
            d = dt.datetime.strptime(raw, fmt)
            return d, d.isoformat()
        except ValueError:
            continue
    return None, ""


def is_latest_resource(title: str) -> bool:
    """Prefer 2026-2030 period resources, or a source series explicitly ending in 2026."""
    text = re.sub(r"[–—]", "-", title.lower())
    years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", text)]
    if not years:
        return False
    if any(a in text for a in ["1961-1990", "1991-2020", "2021-2025", "2021 - 2025", "2019-2025"]):
        return False
    if re.search(r"2026\s*-\s*2030", text):
        return True
    return max(years) >= 2026


def resource_links(session: requests.Session, source: dict) -> tuple[list[dict], str | None]:
    response = session.get(source["url"], timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        title = " ".join(anchor.get_text(" ", strip=True).split())
        href = urljoin(source["url"], anchor["href"])
        if "csv" not in title.lower():
            continue
        if not is_latest_resource(title):
            continue
        # The CWC master page lists many basins; limit it to South-India-relevant groups.
        if source.get("basins") and not any(k.lower() in title.lower() for k in source["basins"]):
            continue
        if href in seen:
            continue
        seen.add(href)
        effective_kind = source["kind"]
        title_lower = title.lower()
        if effective_kind == "reservoir_level" and "storage" in title_lower and "water level" not in title_lower:
            effective_kind = "reservoir_storage"
        candidates.append({"title": title, "resource_page_url": href, "download_url": None, "kind": effective_kind})
    return candidates, None


def find_download_url(session: requests.Session, candidate: dict) -> str:
    url = candidate["resource_page_url"]
    if "/download/" in url.lower() or url.lower().endswith(".csv"):
        return url
    response = session.get(url, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    choices = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        label = " ".join(a.get_text(" ", strip=True).split()).lower()
        if "/download/" in href.lower() and (href.lower().endswith(".csv") or "download" in label):
            choices.append(href)
    if not choices:
        # Some portal resource pages do not render a direct URL; do not guess the file name.
        raise RuntimeError("No direct CSV download link was found on the resource page.")
    return choices[0]


def select_col(headers, kind, role):
    cleaned = {h: norm(h) for h in headers}
    if role == "time":
        exact = ["observationdatetime", "datetime", "dateandtime", "timestamp", "observedat", "dataacquisitiontime", "acquisitiontime", "observationdate", "date", "time"]
        for candidate in exact:
            for h, c in cleaned.items():
                if c == candidate:
                    return h
        for h, c in cleaned.items():
            if "date" in c and ("time" in c or c.endswith("date")):
                return h
        return None
    if role == "station_id":
        for h, c in cleaned.items():
            if (("station" in c or "gauge" in c or "location" in c) and ("id" in c or "code" in c)) or c in {"stationid", "gaugeid"}:
                return h
        return None
    if role == "station_name":
        for h, c in cleaned.items():
            if c in {"station", "site", "name", "assetname"} or any(word in c for word in ("stationname", "gaugename", "damname", "reservoirname", "locationname")):
                return h
        return None
    if role == "state":
        return next((h for h, c in cleaned.items() if c in {"state", "statename"}), None)
    if role == "district":
        return next((h for h, c in cleaned.items() if "district" in c), None)
    if role == "river":
        return next((h for h, c in cleaned.items() if c in {"river", "rivername", "streamname"}), None)
    if role == "latitude":
        return next((h for h, c in cleaned.items() if c in {"latitude", "lat", "stationlatitude"}), None)
    if role == "longitude":
        return next((h for h, c in cleaned.items() if c in {"longitude", "lon", "long", "stationlongitude"}), None)
    if role == "warning_level":
        return next((h for h, c in cleaned.items() if "warning" in c and "level" in c), None)
    if role == "danger_level":
        return next((h for h, c in cleaned.items() if "danger" in c and "level" in c), None)
    if role == "full_reservoir_level":
        return next((h for h, c in cleaned.items() if ("fullreservoirlevel" in c or "frl" == c)), None)
    if role == "value":
        reject = ("warning", "danger", "threshold", "alarm", "normallevel", "fullreservoirlevel", "unit")
        if kind in {"river_level", "reservoir_level"}:
            preferred = ("waterlevel", "riverlevel", "reservoirlevel", "levelm", "level")
        elif kind in {"river_discharge", "reservoir_discharge"}:
            preferred = ("discharge", "flowrate", "outflow", "release")
        elif kind == "reservoir_storage":
            preferred = ("reservoirstorage", "storage", "livestorage", "livecapacity", "reservoirvolume", "volume")
        else:
            preferred = ()
        ranked = []
        for h, c in cleaned.items():
            if any(x in c for x in reject):
                continue
            if preferred and any(x in c for x in preferred):
                score = max((len(x) for x in preferred if x in c), default=0)
                ranked.append((score, h))
        return max(ranked)[1] if ranked else None
    return None


def select_value_columns(headers, kind):
    """Return source column(s) representing one measurement; do not silently pick one gate."""
    cleaned = {h: norm(h) for h in headers}
    if kind == "reservoir_discharge":
        totals = [h for h, c in cleaned.items() if "total" in c and any(word in c for word in ("discharge", "outflow", "release"))]
        if totals:
            return [totals[0]]
        gates = [h for h, c in cleaned.items() if re.search(r"gate\d+.*discharge|discharge.*gate\d+", c)]
        if len(gates) >= 2:
            return gates
    selected = select_col(headers, kind, "value")
    return [selected] if selected else []


def parse_float(value):
    try:
        s = str(value or "").strip().replace(",", "")
        if not s or s.lower() in {"na", "n/a", "nan", "null", "-", "--"}:
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def scan_resource(session, source, candidate, fetched_at):
    download_url = find_download_url(session, candidate)
    candidate["download_url"] = download_url
    kind = candidate.get("kind", source["kind"])
    latest: dict[str, dict] = {}
    series_by_station: dict[str, dict[str, float]] = {}
    scanned_rows = 0
    byte_count = 0
    with session.get(download_url, timeout=90, stream=True) as response:
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(prefix="floodwatch-", suffix=".csv", delete=True) as temp:
            for block in response.iter_content(chunk_size=1024 * 512):
                if not block:
                    continue
                byte_count += len(block)
                if byte_count > MAX_RESOURCE_BYTES:
                    raise RuntimeError(f"CSV exceeded size safety limit ({MAX_RESOURCE_BYTES} bytes).")
                temp.write(block)
            temp.flush()
            # Resource CSVs are streamed to disk to avoid retaining entire multi-year files in RAM.
            with open(temp.name, "r", newline="", encoding="utf-8-sig", errors="replace") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                time_col = select_col(headers, kind, "time")
                id_col = select_col(headers, source["kind"], "station_id")
                name_col = select_col(headers, source["kind"], "station_name")
                state_col = select_col(headers, source["kind"], "state")
                district_col = select_col(headers, source["kind"], "district")
                river_col = select_col(headers, source["kind"], "river")
                lat_col = select_col(headers, source["kind"], "latitude")
                lon_col = select_col(headers, source["kind"], "longitude")
                value_cols = select_value_columns(headers, kind)
                warning_col = select_col(headers, kind, "warning_level")
                danger_col = select_col(headers, kind, "danger_level")
                full_reservoir_col = select_col(headers, kind, "full_reservoir_level")
                if not time_col or not value_cols:
                    raise RuntimeError(f"Could not identify time/value columns. Headers={headers}")
                for row in reader:
                    scanned_rows += 1
                    if scanned_rows > MAX_ROWS_PER_RESOURCE:
                        raise RuntimeError(f"CSV exceeded row safety limit ({MAX_ROWS_PER_RESOURCE}).")
                    when, iso = parse_time(row.get(time_col, ""))
                    numeric_values = [parse_float(row.get(col, "")) for col in value_cols]
                    numeric_values = [number for number in numeric_values if number is not None]
                    if not numeric_values:
                        value = None
                    elif kind == "reservoir_discharge" and len(value_cols) > 1:
                        # Each gate column is one component of total site release.
                        value = sum(numeric_values)
                    else:
                        value = numeric_values[0]
                    if when is None or value is None:
                        continue
                    station_id = (row.get(id_col) or "").strip() if id_col else ""
                    station_name = (row.get(name_col) or "").strip() if name_col else ""
                    state = (row.get(state_col) or "").strip() if state_col else ""
                    district = (row.get(district_col) or "").strip() if district_col else ""
                    river = (row.get(river_col) or "").strip() if river_col else ""
                    if not station_id:
                        station_id = station_name or "|".join(x for x in (state, district, river) if x)
                    if not station_id:
                        continue
                    lat = parse_float(row.get(lat_col, "")) if lat_col else None
                    lon = parse_float(row.get(lon_col, "")) if lon_col else None
                    key = (kind, station_id, state, district)
                    header_norm = norm(" ".join(value_cols))
                    if kind in {"river_level", "reservoir_level"}:
                        unit = "m" if (header_norm.endswith("m") or "meter" in header_norm or "metre" in header_norm) else "source-defined"
                    elif kind in {"river_discharge", "reservoir_discharge"}:
                        if "cusec" in header_norm or "cusecs" in header_norm:
                            unit = "cusec"
                        else:
                            unit = "m3/s" if any(token in header_norm for token in ["m3s", "cumec", "cubicmetrepersecond"]) else "source-defined"
                    else:
                        unit = "source-defined"
                    warning_value = parse_float(row.get(warning_col, "")) if warning_col else None
                    danger_value = parse_float(row.get(danger_col, "")) if danger_col else None
                    full_reservoir_value = parse_float(row.get(full_reservoir_col, "")) if full_reservoir_col else None
                    record = {
                        "id": "|".join(key),
                        "station_id": station_id,
                        "station_name": station_name,
                        "state": state,
                        "district": district,
                        "river": river,
                        "latitude": lat,
                        "longitude": lon,
                        "kind": kind,
                        "value": value,
                        "unit": unit,
                        "warning_level": warning_value,
                        "danger_level": danger_value,
                        "full_reservoir_level": full_reservoir_value,
                        "observed_at": iso,
                        "observed_at_raw": (row.get(time_col) or "").strip(),
                        "source_timezone": "not specified in collector; raw timestamp preserved",
                        "source_name": source["name"],
                        "agency": source["agency"],
                        "source_dataset_url": source["url"],
                        "source_resource_title": candidate["title"],
                        "source_resource_page_url": candidate.get("resource_page_url"),
                        "source_download_url": download_url,
                        "fetched_at_utc": fetched_at,
                    }
                    previous = latest.get(record["id"])
                    if previous is None or iso > previous["observed_at"]:
                        latest[record["id"]] = record
                    series = series_by_station.setdefault(record["id"], {})
                    series[iso] = value
                    if len(series) > 96:
                        keep = sorted(series)[-48:]
                        series_by_station[record["id"]] = {k: series[k] for k in keep}
    histories = [
        {"id": key, "points": [{"observed_at": when, "value": val} for when, val in sorted(points.items())[-48:]]}
        for key, points in series_by_station.items()
    ]
    return list(latest.values()), histories, {
        "source_name": source["name"],
        "kind": kind,
        "dataset_page_url": source["url"],
        "resource_title": candidate["title"],
        "download_url": download_url,
        "fetched_at_utc": fetched_at,
        "rows_scanned": scanned_rows,
        "stations_with_numeric_timestamped_record": len(latest),
        "latest_observation_timestamp_reported": max((r["observed_at"] for r in latest.values()), default=None),
        "bytes_downloaded": byte_count,
        "status": "ok" if latest else "no_usable_records",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", type=pathlib.Path, default=DEFAULT_SOURCE_FILE)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--max-resources", type=int, default=40)
    ap.add_argument("--request-delay-seconds", type=float, default=0.6)
    args = ap.parse_args()
    registry = json.loads(args.sources.read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    session = requests.Session()
    session.headers.update({"User-Agent": "FloodWatch-South-India/0.1 (open research prototype)"})
    observations_by_id = {}
    series_by_id = {}
    source_reports = []
    resource_count = 0
    for source in registry["sources"]:
        page_report = {"source_name": source["name"], "kind": source["kind"], "dataset_page_url": source["url"]}
        try:
            candidates, _ = resource_links(session, source)
            if not candidates:
                page_report.update({"status": "no_current_period_resources_found", "resources": 0})
                source_reports.append(page_report)
                continue
            # Choose newest labelled resources. On state pages many basins may exist; cap each page too.
            candidates = candidates[: max(1, min(int(source.get("max_resources", 2)), args.max_resources, 20))]
            page_report["resources_discovered"] = len(candidates)
            for candidate in candidates:
                if resource_count >= args.max_resources:
                    break
                try:
                    resource_count += 1  # Count each attempted resource, including schema/download failures.
                    latest, histories, report = scan_resource(session, source, candidate, now)
                    page_report.setdefault("resource_reports", []).append(report)
                    for history in histories:
                        previous_points = series_by_id.get(history["id"], [])
                        combined = {point["observed_at"]: point for point in previous_points}
                        combined.update({point["observed_at"]: point for point in history["points"]})
                        series_by_id[history["id"]] = [
                            combined[key] for key in sorted(combined)[-48:]
                        ]
                    for record in latest:
                        key = record["id"]
                        previous = observations_by_id.get(key)
                        if previous is None or record["observed_at"] > previous["observed_at"]:
                            observations_by_id[key] = record
                except Exception as exc:
                    page_report.setdefault("resource_errors", []).append({
                        "resource_title": candidate["title"],
                        "resource_page_url": candidate["resource_page_url"],
                        "error": str(exc),
                    })
                time.sleep(args.request_delay_seconds)
            page_report["status"] = "checked"
        except Exception as exc:
            page_report.update({"status": "source_page_error", "error": str(exc)})
        source_reports.append(page_report)

    observations = list(observations_by_id.values())
    observations.sort(key=lambda item: (item["kind"], item["state"], item["station_name"] or item["station_id"]))
    output = {
        "schema_version": 1,
        "product": "FloodWatch South India public water observations",
        "generated_at_utc": now,
        "source_registry_url": "https://github.com/PantheonDeified/FloodWatch-South-India/blob/main/data_pipeline/sources.json",
        "coverage_note": "Only stations/resources exposed by the registered public data pages are included. This is not every river or dam. Per-station source timestamps and source URLs must be checked.",
        "observation_semantics": {
            "river_level": "Source-reported river water level; not necessarily a height above sea level and not a flood threshold unless a station-specific datum and official threshold are provided.",
            "reservoir_level": "Source-reported reservoir water level; may not be comparable between reservoirs without their datum and full-reservoir-level metadata.",
            "reservoir_discharge": "Release/outflow discharge, not reservoir level or storage.",
            "river_discharge": "River flow measurement when a verified source provides it; not the same quantity as water level."
        },
        "observation_count": len(observations),
        "resource_count_checked": resource_count,
        "observations": observations,
        "series": [{"id": key, "points": points} for key, points in series_by_id.items()],
        "sources": source_reports,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    diagnostics = []
    for report in source_reports:
        diagnostics.append({
            "source_name": report.get("source_name"),
            "status": report.get("status"),
            "resources_discovered": report.get("resources_discovered", report.get("resources", 0)),
            "resources_succeeded": len(report.get("resource_reports", [])),
            "source_error": report.get("error"),
            "resource_errors": report.get("resource_errors", []),
            "resource_summaries": [{
                "title": item.get("resource_title"),
                "status": item.get("status"),
                "stations": item.get("stations_with_numeric_timestamped_record"),
                "latest_timestamp": item.get("latest_observation_timestamp_reported"),
                "download_url": item.get("download_url"),
            } for item in report.get("resource_reports", [])],
        })
    print(json.dumps({
        "output": str(args.out),
        "observation_count": len(observations),
        "resource_count_checked": resource_count,
        "source_pages": len(source_reports),
        "statuses": {r["source_name"]: r["status"] for r in source_reports},
        "diagnostics": diagnostics,
    }, indent=2))
    # Partial source failures should not erase a previously published snapshot in automation.
    return 0 if observations else 1


if __name__ == "__main__":
    raise SystemExit(main())
