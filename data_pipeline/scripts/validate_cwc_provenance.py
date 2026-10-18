#!/usr/bin/env python3
"""Fail-closed validation of exact source provenance in normalized CWC discharge."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import re
from collections import Counter
from typing import Any

REQUIRED_NORMALIZED = {
    "source_file", "source_url", "source_download_url", "source_dataset_url",
    "source_resource_title", "source_sha256", "source_provenance_status",
}
SUCCESS_STATUSES = {"downloaded", "already_downloaded"}
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_file(path: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_manifest(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("files")
    if not isinstance(items, list):
        raise ValueError("Manifest must contain a files list")
    result = {}
    for item in items:
        if not isinstance(item, dict) or item.get("status") not in SUCCESS_STATUSES:
            continue
        local_name = pathlib.Path(str(item.get("local_path") or "")).name
        if not local_name:
            raise ValueError("Manifest success entry is missing local_path")
        if local_name in result and result[local_name] != item:
            raise ValueError(f"Conflicting manifest entries for local file: {local_name}")
        result[local_name] = item
    return result


def validate(
    raw_dir: pathlib.Path,
    normalized_path: pathlib.Path,
    quality_report_path: pathlib.Path,
    manifest_path: pathlib.Path,
    verify_raw_sha256: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    raw_files = sorted(raw_dir.glob("*.csv"))
    if not raw_files:
        raise ValueError(f"No raw CSV files found in {raw_dir}")
    missing_from_manifest = sorted(path.name for path in raw_files if path.name not in manifest)
    if missing_from_manifest:
        raise ValueError(f"Raw CSV files absent from successful manifest entries: {missing_from_manifest}")

    report = json.loads(quality_report_path.read_text(encoding="utf-8"))
    per_file = report.get("source_provenance_by_file")
    if not isinstance(per_file, dict):
        raise ValueError("Quality report is missing source_provenance_by_file metadata")
    row_counts = Counter()
    exact_rows = 0
    total_rows = 0
    mismatches = []
    for raw_path in raw_files:
        item = manifest[raw_path.name]
        expected_resource = str(item.get("resource_page_url") or "").strip()
        expected_download = str(item.get("download_url") or "").strip()
        expected_dataset = str(item.get("dataset_page_url") or "").strip()
        expected_title = str(item.get("title") or "").strip()
        expected_sha = str(item.get("sha256") or "").strip().lower()
        if not expected_resource or not expected_download or not expected_dataset or not expected_title:
            mismatches.append({"file": raw_path.name, "problem": "manifest entry lacks exact resource metadata"})
        if not SHA256_PATTERN.fullmatch(expected_sha):
            mismatches.append({"file": raw_path.name, "problem": "manifest SHA-256 is missing or malformed"})
        file_report = per_file.get(raw_path.name)
        if not isinstance(file_report, dict):
            mismatches.append({"file": raw_path.name, "problem": "quality report has no per-file provenance record"})
        else:
            expected_report = {
                "source_url_used": expected_resource,
                "provenance_status": "manifest_exact_resource",
                "source_resource_title": expected_title,
                "source_download_url": expected_download,
                "source_dataset_url": expected_dataset,
                "source_sha256": expected_sha,
            }
            for key, value in expected_report.items():
                actual = str(file_report.get(key) or "").strip()
                if actual.casefold() != value.casefold():
                    mismatches.append({
                        "file": raw_path.name,
                        "problem": "per-file quality report metadata mismatch",
                        "field": key,
                        "expected": value,
                        "actual": actual,
                    })
        if verify_raw_sha256 and SHA256_PATTERN.fullmatch(expected_sha):
            actual_sha = sha256_file(raw_path).lower()
            if actual_sha != expected_sha:
                mismatches.append({
                    "file": raw_path.name,
                    "problem": "raw file does not match manifest SHA-256",
                    "expected": expected_sha,
                    "actual": actual_sha,
                })

    with normalized_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(REQUIRED_NORMALIZED - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"Normalized discharge file lacks provenance columns: {missing}")
        for row in reader:
            total_rows += 1
            source_file = pathlib.Path(str(row.get("source_file") or "")).name
            row_counts[source_file] += 1
            item = manifest.get(source_file)
            if item is None:
                mismatches.append({"row": total_rows, "source_file": source_file, "problem": "row source file is not in manifest"})
                continue
            expected = {
                "source_url": str(item.get("resource_page_url") or "").strip(),
                "source_download_url": str(item.get("download_url") or "").strip(),
                "source_dataset_url": str(item.get("dataset_page_url") or "").strip(),
                "source_resource_title": str(item.get("title") or "").strip(),
                "source_sha256": str(item.get("sha256") or "").strip(),
                "source_provenance_status": "manifest_exact_resource",
            }
            for field, value in expected.items():
                actual = str(row.get(field) or "").strip()
                if actual.casefold() != value.casefold():
                    mismatches.append({
                        "row": total_rows,
                        "source_file": source_file,
                        "problem": "normalized row provenance mismatch",
                        "field": field,
                        "expected": value,
                        "actual": actual,
                    })
                    break
            else:
                exact_rows += 1

    missing_rows = sorted(name for name in manifest if name not in row_counts)
    result = {
        "status": "passed" if not mismatches and total_rows > 0 else "failed",
        "raw_csv_files": len(raw_files),
        "manifest_success_files": len(manifest),
        "normalized_rows": total_rows,
        "rows_with_exact_provenance": exact_rows,
        "normalized_rows_by_source_file": dict(sorted(row_counts.items())),
        "files_with_no_normalized_rows": missing_rows,
        "raw_sha256_recomputed": verify_raw_sha256,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:100],
        "mismatches_truncated": len(mismatches) > 100,
        "warning": "Provenance integrity does not validate station coordinates, measurement accuracy, units beyond schema, or forecast skill.",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=pathlib.Path, required=True)
    parser.add_argument("--normalized", type=pathlib.Path, required=True)
    parser.add_argument("--quality-report", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--verify-raw-sha256", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest or (args.raw_dir / "manifest.json")
    try:
        result = validate(args.raw_dir, args.normalized, args.quality_report,
                          manifest_path, args.verify_raw_sha256)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = {k: result[k] for k in (
        "status", "raw_csv_files", "manifest_success_files", "normalized_rows",
        "rows_with_exact_provenance", "raw_sha256_recomputed", "mismatch_count",
    )}
    print(json.dumps(summary, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
