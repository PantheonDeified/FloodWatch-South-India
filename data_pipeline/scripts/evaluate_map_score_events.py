#!/usr/bin/env python3
"""Evaluate archived FloodWatch map scores against independently reviewed flood events.

The experimental 0-100 index is not a probability. A logistic calibrator is fit
on the earliest chronological split, a decision threshold is chosen on the next
split, and the final time period is reported once as the untouched test set.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, balanced_accuracy_score, brier_score_loss,
    confusion_matrix, f1_score, log_loss, precision_score, recall_score,
    roc_auc_score,
)


def require_two_classes(frame: pd.DataFrame, split: str, minimum: int = 10) -> None:
    counts = frame["flood_in_next_3d"].value_counts().to_dict()
    if counts.get(0, 0) < minimum or counts.get(1, 0) < minimum:
        raise SystemExit(
            f"{split} needs at least {minimum} verified positive and {minimum} verified negative labels; "
            f"found {counts.get(1, 0)} positive and {counts.get(0, 0)} negative."
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", required=True, type=pathlib.Path,
                    help="CSV exported by FloodWatch's Saved places & browser alerts card.")
    ap.add_argument("--labels", required=True, type=pathlib.Path,
                    help="Reviewed CSV based on data_pipeline/flood_event_verification.template.csv.")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--minimum-per-class", type=int, default=10,
                    help="Minimum positive and negative examples in each chronological split (default: 10).")
    args = ap.parse_args()

    scores = pd.read_csv(args.scores, dtype={"location_id": str})
    labels = pd.read_csv(args.labels, dtype={"location_id": str})
    score_required = {"location_id", "feature_date", "score", "score_version"}
    label_required = {
        "location_id", "feature_date", "flood_in_next_3d", "event_onset_date",
        "label_source_url", "label_method", "label_confidence", "label_review_status",
    }
    if missing := sorted(score_required - set(scores.columns)):
        raise SystemExit(f"Score archive is missing columns: {missing}.")
    if missing := sorted(label_required - set(labels.columns)):
        raise SystemExit(f"Event labels are missing columns: {missing}. Use the verification template.")

    for frame, col in ((scores, "feature_date"), (labels, "feature_date")):
        frame[col] = pd.to_datetime(frame[col], errors="coerce").dt.strftime("%Y-%m-%d")
    labels["event_onset_date"] = pd.to_datetime(labels["event_onset_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    scores["score"] = pd.to_numeric(scores["score"], errors="coerce")
    labels["flood_in_next_3d"] = pd.to_numeric(labels["flood_in_next_3d"], errors="coerce")
    labels["label_confidence"] = labels["label_confidence"].astype(str).str.strip().str.casefold()
    labels["label_review_status"] = labels["label_review_status"].astype(str).str.strip().str.casefold()
    labels["label_method"] = labels["label_method"].astype(str).str.strip().str.casefold()

    if scores[["location_id", "feature_date"]].isna().any().any() or scores["score"].isna().any():
        raise SystemExit("Score archive contains missing location/date/score values.")
    if not scores["score"].between(0, 100).all():
        raise SystemExit("Archived map scores must be in [0, 100].")
    if labels[["location_id", "feature_date", "flood_in_next_3d"]].isna().any().any():
        raise SystemExit("Event labels contain missing location/date/label values.")
    if not labels["flood_in_next_3d"].isin([0, 1]).all():
        raise SystemExit("flood_in_next_3d must be 0 or 1; unknown/unreported days are not negative labels.")
    if labels.duplicated(["location_id", "feature_date"]).any():
        raise SystemExit("Event labels must have one reviewed row per location_id and feature_date.")
    if not labels["label_review_status"].eq("reviewed").all():
        raise SystemExit("Every event label must have label_review_status=reviewed.")
    if not labels["label_confidence"].isin(["high", "moderate"]).all():
        raise SystemExit("Every event label needs high or moderate reviewer confidence.")
    source_urls = labels["label_source_url"].fillna("").astype(str).str.strip()
    if not source_urls.str.match(r"^https://\S+$", case=False).all():
        raise SystemExit("Every event label needs a source URL beginning with https://.")
    positive = labels["flood_in_next_3d"].eq(1)
    negative = ~positive
    if not labels.loc[positive, "label_method"].eq("verified_flood_event").all():
        raise SystemExit("Positive rows must use label_method=verified_flood_event.")
    if not labels.loc[negative, "label_method"].eq("verified_no_event").all():
        raise SystemExit("Negative rows must use label_method=verified_no_event and a source known to cover the full window.")
    if labels.loc[positive, "event_onset_date"].isna().any():
        raise SystemExit("Positive rows need event_onset_date to verify the three-day lead window.")
    lead = (
        pd.to_datetime(labels.loc[positive, "event_onset_date"])
        - pd.to_datetime(labels.loc[positive, "feature_date"])
    ).dt.total_seconds() / 86400
    if ((lead < 0) | (lead > 3)).any():
        raise SystemExit("Positive event_onset_date must fall from feature_date through the next 3 days.")

    # Join reviewed labels and keep one forecast per location/day so six-hour browser snapshots
    # are not counted as independent flood events. Use the latest forecast issued that day.
    joined = scores.merge(
        labels, on=["location_id", "feature_date"], how="inner", validate="many_to_one",
        suffixes=("", "_label"),
    )
    matched_score_rows = len(joined)
    sort_columns = ["feature_date", "location_id"]
    if "forecast_created_at_utc" in joined.columns:
        sort_columns.append("forecast_created_at_utc")
    merged = joined.sort_values(sort_columns).drop_duplicates(["location_id", "feature_date"], keep="last")
    if merged.empty:
        raise SystemExit("No score samples matched reviewed event labels on location_id and feature_date.")
    dates = sorted(merged["feature_date"].unique())
    if len(dates) < 20:
        raise SystemExit(f"Only {len(dates)} labelled dates match. Need at least 20 distinct dates for chronological evaluation.")
    train_cut, validation_cut = int(len(dates) * .70), int(len(dates) * .85)
    if train_cut < 2 or validation_cut <= train_cut or validation_cut >= len(dates):
        raise SystemExit("Insufficient distinct dates for chronological train/validation/test periods.")
    train_end, validation_end = dates[train_cut - 1], dates[validation_cut - 1]
    merged["split"] = np.where(
        merged["feature_date"] <= train_end, "train",
        np.where(merged["feature_date"] <= validation_end, "validation", "test"),
    )
    train = merged[merged["split"] == "train"].copy()
    validation = merged[merged["split"] == "validation"].copy()
    test = merged[merged["split"] == "test"].copy()
    for frame, name in ((train, "Training period"), (validation, "Validation period"), (test, "Test period")):
        require_two_classes(frame, name, args.minimum_per_class)

    calibrator = LogisticRegression(C=1.0, max_iter=2000, random_state=42)
    calibrator.fit(train[["score"]], train["flood_in_next_3d"].astype(int))
    validation_probability = calibrator.predict_proba(validation[["score"]])[:, 1]
    thresholds = np.linspace(.05, .95, 91)
    threshold_f1 = [
        (float(f1_score(validation["flood_in_next_3d"].astype(int), validation_probability >= threshold, zero_division=0)), float(threshold))
        for threshold in thresholds
    ]
    best_f1 = max(value for value, _ in threshold_f1)
    decision_threshold = max(threshold for value, threshold in threshold_f1 if value == best_f1)

    test["calibrated_probability"] = calibrator.predict_proba(test[["score"]])[:, 1]
    test["predicted_event"] = (test["calibrated_probability"] >= decision_threshold).astype(int)
    y = test["flood_in_next_3d"].astype(int).to_numpy()
    probability = test["calibrated_probability"].to_numpy()
    prediction = test["predicted_event"].to_numpy()
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    calibrated_bins = []
    edges = np.linspace(0, 1, 11)
    bin_ids = np.digitize(probability, edges[1:-1], right=True)
    for index in range(10):
        mask = bin_ids == index
        if mask.any():
            calibrated_bins.append({
                "probability_range": [float(edges[index]), float(edges[index + 1])],
                "samples": int(mask.sum()),
                "mean_predicted_probability": float(probability[mask].mean()),
                "observed_event_rate": float(y[mask].mean()),
            })
    positive_test = test[test["flood_in_next_3d"].eq(1)].copy()
    lead_days = (
        pd.to_datetime(positive_test["event_onset_date"])
        - pd.to_datetime(positive_test["feature_date"])
    ).dt.total_seconds() / 86400
    report = {
        "model_type": "out-of-time verification of the archived experimental map index with validation-trained logistic calibration",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "label_horizon": "verified flood event onset from feature_date through the next 3 days",
        "matched_score_rows_before_daily_deduplication": int(matched_score_rows),
        "matched_location_day_samples": int(len(merged)),
        "daily_selection": "latest archived forecast for each reviewed location and feature_date",
        "distinct_location_dates": int(merged[["location_id", "feature_date"]].drop_duplicates().shape[0]),
        "unmatched_score_rows": int(len(scores) - scores[["location_id", "feature_date"]].merge(labels[["location_id", "feature_date"]], on=["location_id", "feature_date"]).shape[0]),
        "periods": {"train_end": train_end, "validation_end": validation_end, "test_start": str(test["feature_date"].min()), "test_end": str(test["feature_date"].max())},
        "split_rows": {"train": int(len(train)), "validation": int(len(validation)), "test": int(len(test))},
        "score_versions": sorted(merged["score_version"].dropna().astype(str).unique().tolist()),
        "calibration": {"method": "logistic regression fit on training period only", "coefficients": calibrator.coef_.ravel().astype(float).tolist(), "intercept": float(calibrator.intercept_[0])},
        "threshold_selection": {"method": "maximize F1 on validation period", "threshold": decision_threshold, "validation_f1": best_f1},
        "test_metrics": {
            "raw_index_roc_auc": float(roc_auc_score(y, test["score"])),
            "raw_index_average_precision": float(average_precision_score(y, test["score"])),
            "calibrated_brier_score": float(brier_score_loss(y, probability)),
            "calibrated_log_loss": float(log_loss(y, probability, labels=[0, 1])),
            "decision_threshold_probability": decision_threshold,
            "precision": float(precision_score(y, prediction, zero_division=0)),
            "recall": float(recall_score(y, prediction, zero_division=0)),
            "f1": float(f1_score(y, prediction, zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
            "false_positive_rate": float(fp / (fp + tn)) if fp + tn else None,
            "false_discovery_rate": float(fp / (fp + tp)) if fp + tp else None,
            "confusion_matrix_tn_fp_fn_tp": [int(tn), int(fp), int(fn), int(tp)],
            "reliability_bins": calibrated_bins,
            "positive_event_lead_days_median": float(lead_days.median()) if len(lead_days) else None,
        },
        "warnings": [
            "This report applies only to archived scores and reviewed labels in the stated sample and periods.",
            "The calibrated probability is a research estimate; it is not an official warning or operational flood probability.",
            "Do not label unreported dates as no-event. Negative labels require a source that covers the complete forecast window.",
            "A location-level browser archive is not a station network evaluation and may be geographically biased by user-selected places.",
        ],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "map_score_event_verification.report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    merged.to_csv(args.out_dir / "map_score_event_verification.joined.csv", index=False)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
