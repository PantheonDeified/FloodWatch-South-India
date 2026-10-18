from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_cwc_provenance.py"


class CwcProvenanceTests(unittest.TestCase):
    def build_fixture(self, root: Path):
        raw = root / "raw"
        raw.mkdir()
        raw_file = raw / "source.csv"
        raw_file.write_text("data\nexample\n", encoding="utf-8")
        digest = hashlib.sha256(raw_file.read_bytes()).hexdigest()
        manifest = {
            "files": [{
                "title": "CWC sample discharge",
                "resource_page_url": "https://example.gov/resource/abc",
                "dataset_page_url": "https://example.gov/dataset/discharge",
                "download_url": "https://example.gov/download/abc.csv",
                "local_path": str(raw_file),
                "status": "downloaded",
                "sha256": digest,
            }]
        }
        manifest_path = raw / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        normalized = root / "normalized.csv"
        fields = ["source_file", "source_url", "source_download_url", "source_dataset_url",
                  "source_resource_title", "source_sha256", "source_provenance_status"]
        row = {
            "source_file": raw_file.name,
            "source_url": manifest["files"][0]["resource_page_url"],
            "source_download_url": manifest["files"][0]["download_url"],
            "source_dataset_url": manifest["files"][0]["dataset_page_url"],
            "source_resource_title": manifest["files"][0]["title"],
            "source_sha256": digest,
            "source_provenance_status": "manifest_exact_resource",
        }
        with normalized.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(row)
        quality = root / "quality.json"
        quality.write_text(json.dumps({
            "source_provenance_by_file": {
                raw_file.name: {
                    "source_url_used": row["source_url"],
                    "provenance_status": "manifest_exact_resource",
                    "source_resource_title": row["source_resource_title"],
                    "source_download_url": row["source_download_url"],
                    "source_dataset_url": row["source_dataset_url"],
                    "source_sha256": row["source_sha256"],
                }
            }
        }), encoding="utf-8")
        return raw, raw_file, normalized, quality, manifest_path

    def run_validator(self, root, raw, normalized, quality, manifest, *extra, expect=0):
        output = root / "provenance-report.json"
        run = subprocess.run([
            sys.executable, str(SCRIPT), "--raw-dir", str(raw),
            "--normalized", str(normalized), "--quality-report", str(quality),
            "--manifest", str(manifest), "--out", str(output), *extra,
        ], capture_output=True, text=True)
        self.assertEqual(run.returncode, expect, run.stdout + run.stderr)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_passes_exact_row_and_raw_checksum(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, _, normalized, quality, manifest = self.build_fixture(root)
            result = self.run_validator(root, raw, normalized, quality, manifest, "--verify-raw-sha256")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["normalized_rows"], 1)
            self.assertEqual(result["rows_with_exact_provenance"], 1)
            self.assertEqual(result["mismatch_count"], 0)

    def test_rejects_dataset_fallback_and_row_metadata_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, _, normalized, quality, manifest = self.build_fixture(root)
            with normalized.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                fields = reader.fieldnames
                rows = list(reader)
            rows[0]["source_url"] = "https://example.gov/dataset/discharge"
            with normalized.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            result = self.run_validator(root, raw, normalized, quality, manifest, expect=2)
            self.assertEqual(result["status"], "failed")
            self.assertGreater(result["mismatch_count"], 0)

    def test_rejects_raw_files_missing_from_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw, _, normalized, quality, manifest = self.build_fixture(root)
            (raw / "unlisted.csv").write_text("data\n", encoding="utf-8")
            result = self.run_validator(root, raw, normalized, quality, manifest, expect=2)
            self.assertEqual(result["status"], "failed")
            self.assertIn("mismatches", result)


if __name__ == "__main__":
    unittest.main()
