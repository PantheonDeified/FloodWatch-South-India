#!/usr/bin/env python3
"""Gate a trained single-gauge LSTM report before human review; never auto-deploy it."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=pathlib.Path)
    parser.add_argument("--model", required=True, type=pathlib.Path)
    parser.add_argument("--scalers", required=True, type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read training report: {exc}") from exc

    checks = {
        "model_artifact_exists": args.model.is_file(),
        "scaler_artifact_exists": args.scalers.is_file(),
        "beats_persistence_baseline": report.get("beats_persistence_baseline_on_rmse") is True,
        "positive_rmse_skill": isinstance(report.get("rmse_skill_vs_persistence"), (int, float))
            and report["rmse_skill_vs_persistence"] > 0,
        "enough_test_windows": isinstance(report.get("test_windows"), int) and report["test_windows"] >= 10,
        "test_metrics_present": isinstance(report.get("test_metrics"), dict)
            and isinstance(report["test_metrics"].get("rmse_m3s"), (int, float))
            and isinstance(report["test_metrics"].get("mae_m3s"), (int, float)),
        "persistence_metrics_present": isinstance(report.get("persistence_baseline_test_metrics"), dict)
            and isinstance(report["persistence_baseline_test_metrics"].get("rmse_m3s"), (int, float)),
        "chronological_split_present": isinstance(report.get("chronological_split_dates"), dict),
    }
    passed = all(checks.values())
    result = {
        "status": "eligible_for_human_review" if passed else "not_eligible_for_review",
        "automatically_deployed": False,
        "station_id": report.get("station_id"),
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
        "warning": "Passing these gates is not proof of hydrological validity. A human must review source provenance, station/catchment mapping, event periods, uncertainty, and the model card before any external use.",
    }
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
