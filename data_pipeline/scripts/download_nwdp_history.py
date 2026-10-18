#!/usr/bin/env python3
"""Download source-linked raw historical NWDP/CWC CSV resources for review.

The script records source URLs, checksums and byte counts. It does not assume
that the resource title's date range means every station has complete data.
By default it selects South India-relevant CWC water-level, discharge and rainfall resources across all periods
listed on the official CWC telemetry page.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DEFAULT_PAGES = [
    "https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc",
    "https://nwdp.nwic.gov.in/dataset/river-discharge-manual-dailly-central-water-commission-cwc",
    "https://nwdp.nwic.gov.in/en/dataset/rainfall-manual-daily-central-water-commission-cwc",
]
DEFAULT_KEYWORDS = [
    "andhra pradesh", "karnataka", "kerala", "tamil nadu", "telangana",
    "puducherry", "godavari", "krishna", "pennar", "cauvery",
    "east flowing rivers between pennar and kanyakumari",
    "west flowing rivers from tapi to tadri",
    "east flowing rivers between mahanadi and pennar",
]
MAX_BYTES = 300 * 1024 * 1024


def slugify(text: str) -> str:
    text = re.sub(r"(?i)csv$", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:150] or "nwdp-resource") + ".csv"


def title_years(text: str) -> list[int]:
    return [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", text)]


def get_download_url(session: requests.Session, resource_url: str) -> str:
    if "/download/" in resource_url.lower() or resource_url.lower().endswith(".csv"):
        return resource_url
    r = session.get(resource_url, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    matches = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(resource_url, anchor["href"])
        label = " ".join(anchor.get_text(" ", strip=True).split()).lower()
        if "/download/" in href.lower() and (href.lower().endswith(".csv") or "download" in label):
            matches.append(href)
    if not matches:
        raise RuntimeError("No explicit CSV download link found on resource page.")
    return matches[0]


def download(session: requests.Session, url: str, destination: pathlib.Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with session.get(url, stream=True, timeout=90) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type and not url.lower().endswith(".csv"):
            raise RuntimeError(f"Expected a CSV response, received {content_type}")
        with destination.open("wb") as out:
            for block in response.iter_content(1024 * 512):
                if not block:
                    continue
                total += len(block)
                if total > MAX_BYTES:
                    out.close()
                    destination.unlink(missing_ok=True)
                    raise RuntimeError(f"Resource exceeded {MAX_BYTES} byte safety limit.")
                hasher.update(block)
                out.write(block)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Downloaded file was empty.")
    # Protect against accidentally saving an HTML error page with a .csv suffix.
    with destination.open("rb") as check:
        prefix = check.read(256).lstrip().lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
        destination.unlink(missing_ok=True)
        raise RuntimeError("The download endpoint returned HTML instead of CSV.")
    return total, hasher.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-url", action="append", default=None,
                    help="Official NWDP dataset page; may be passed multiple times.")
    ap.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("data_pipeline/raw/nwdp_history"))
    ap.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS),
                    help="Comma-separated substring filters on resource titles.")
    ap.add_argument("--start-year", type=int, default=1961)
    ap.add_argument("--end-year", type=int, default=2030)
    ap.add_argument("--max-resources", type=int, default=100)
    ap.add_argument("--delay-seconds", type=float, default=0.5)
    args = ap.parse_args()

    pages = args.source_url or DEFAULT_PAGES
    keywords = [x.strip().lower() for x in args.keywords.split(",") if x.strip()]
    session = requests.Session()
    session.headers.update({"User-Agent": "FloodWatch-South-India/0.1 (source-linked hydrology research)"})
    report = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "historical_period_requested": [args.start_year, args.end_year],
        "source_pages": pages,
        "keyword_filter": keywords,
        "files": [],
        "errors": [],
        "warning": "These are raw source files. Inspect columns, units, station coordinates and actual dates before normalization or modelling.",
    }
    seen = set()
    count = 0
    for page_url in pages:
        try:
            response = session.get(page_url, timeout=60)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_matches = 0
            for anchor in soup.find_all("a", href=True):
                title = " ".join(anchor.get_text(" ", strip=True).split())
                low = title.lower()
                if "csv" not in low:
                    continue
                if keywords and not any(k in low for k in keywords):
                    continue
                years = title_years(title)
                if not years or max(years) < args.start_year or min(years) > args.end_year:
                    continue
                resource_page = urljoin(page_url, anchor["href"])
                if resource_page in seen:
                    continue
                seen.add(resource_page)
                if count >= args.max_resources:
                    break
                entry = {
                    "title": title,
                    "resource_page_url": resource_page,
                    "dataset_page_url": page_url,
                }
                try:
                    download_url = get_download_url(session, resource_page)
                    entry["download_url"] = download_url
                    destination = args.out_dir / slugify(title)
                    # Resource titles should be unique, but don't silently overwrite a different resource.
                    if destination.exists():
                        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                        entry.update({"status": "already_downloaded", "local_path": str(destination),
                                      "bytes": destination.stat().st_size, "sha256": digest})
                    else:
                        size, digest = download(session, download_url, destination)
                        entry.update({"status": "downloaded", "local_path": str(destination),
                                      "bytes": size, "sha256": digest})
                    report["files"].append(entry)
                    count += 1
                    page_matches += 1
                except Exception as exc:
                    entry.update({"status": "error", "error": str(exc)})
                    report["errors"].append(entry)
                time.sleep(args.delay_seconds)
            report.setdefault("pages", []).append({
                "url": page_url,
                "status": "checked",
                "resources_downloaded_or_present": page_matches,
            })
        except Exception as exc:
            report["errors"].append({"dataset_page_url": page_url, "error": str(exc)})
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest = args.out_dir / "manifest.json"
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest),
        "resources_recorded": len(report["files"]),
        "errors": len(report["errors"]),
        "output_dir": str(args.out_dir),
    }, indent=2))
    return 1 if not report["files"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
