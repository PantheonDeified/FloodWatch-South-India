#!/usr/bin/env python3
"""Train and chronologically evaluate an event classifier from verified labels.

Labels must identify a flood/high-water event in a future horizon and must come
from a documented source. Missing event documentation is not a negative label.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score, balanced_accuracy_score, brier_score_loss,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", required=True, type=pathlib.Path)
    ap.add_argument("--labels", required=True, type=pathlib.Path,
                    help="CSV with station_id, feature_date, flood_in_next_3d, label_source_url.")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()

    features = pd.read_csv(args.features, dtype={"station_id": str})
    labels = pd.read_csv(args.labels, dtype={"station_id": str})
    required = {"station_id", "date"}
    if not required.issubset(features.columns):
        raise SystemExit(f"Feature file needs {sorted(required)}.")
    label_required = {"station_id", "feature_date", "flood_in_next_3d", "label_source_url"}
    if not label_required.issubset(labels.columns):
        raise SystemExit(f"Labels file needs {sorted(label_required)}. See the supplied label template.")
    labels["feature_date"] = pd.to_datetime(labels["feature_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    labels["flood_in_next_3d"] = pd.to_numeric(labels["flood_in_next_3d"], errors="coerce")
    labels = labels.dropna(subset=["feature_date", "flood_in_next_3d"])
    if not labels["flood_in_next_3d"].isin([0, 1]).all():
        raise SystemExit("flood_in_next_3d must be 0 or 1; do not use undocumented or inferred negatives.")
    if labels["label_source_url"].fillna("").astype(str).str.strip().eq("").any():
        raise SystemExit("Every label must include a verified source URL.")
    features["date"] = pd.to_datetime(features["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    merged = features.merge(
        labels[["station_id", "feature_date", "flood_in_next_3d"]],
        left_on=["station_id", "date"], right_on=["station_id", "feature_date"],
        how="inner", validate="one_to_one",
    ).dropna(subset=["flood_in_next_3d"]).sort_values("date")
    numeric_candidates = [
        c for c in merged.columns
        if c.startswith(("rain_", "precipitation_", "temperature_", "wind_speed_",
                         "river_level_", "reservoir_level_", "river_discharge_",
                         "reservoir_discharge_", "reservoir_storage_"))
    ]
    feature_cols = [c for c in numeric_candidates if pd.api.types.is_numeric_dtype(
        pd.to_numeric(merged[c], errors="coerce")
    )]
    if not feature_cols:
        raise SystemExit("No numeric rainfall/weather/river-response features were found.")
    merged[feature_cols] = merged[feature_cols].apply(pd.to_numeric, errors="coerce")
    merged = merged.dropna(subset=["date"])
    if len(merged) < 150 or merged["flood_in_next_3d"].nunique() < 2:
        raise SystemExit("Need at least 150 independently labelled rows, including both classes. Do not infer negatives from unreported days.")
    unique_dates = sorted(merged["date"].unique())
    train_cut, val_cut = int(len(unique_dates) * .70), int(len(unique_dates) * .85)
    if train_cut < 1 or val_cut <= train_cut:
        raise SystemExit("Not enough distinct dates for chronological train/validation/test splits.")
    train_end, val_end = unique_dates[train_cut - 1], unique_dates[val_cut - 1]
    train = merged[merged["date"] <= train_end]
    val = merged[(merged["date"] > train_end) & (merged["date"] <= val_end)]
    test = merged[merged["date"] > val_end]
    if any(x.empty or x["flood_in_next_3d"].nunique() < 2 for x in (train, val, test)):
        raise SystemExit("Every chronological split must contain both 0 and 1 labels. More reviewed historical labels are needed.")
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("classifier", HistGradientBoostingClassifier(
            max_iter=160, learning_rate=0.06, max_leaf_nodes=15,
            l2_regularization=1.0, random_state=42,
        )),
    ])
    model.fit(train[feature_cols], train["flood_in_next_3d"].astype(int))
    # Choose a decision threshold on the validation period only; keep the test period untouched.
    val_probabilities = model.predict_proba(val[feature_cols])[:, 1]
    y_val = val["flood_in_next_3d"].astype(int).to_numpy()
    thresholds = np.arange(0.10, 0.91, 0.05)
    threshold_scores = [
        (float(f1_score(y_val, (val_probabilities >= threshold).astype(int), zero_division=0)), float(threshold))
        for threshold in thresholds
    ]
    best_f1 = max(score for score, _ in threshold_scores)
    decision_threshold = max(threshold for score, threshold in threshold_scores if score == best_f1)
    probabilities = model.predict_proba(test[feature_cols])[:, 1]
    predictions = (probabilities >= decision_threshold).astype(int)
    y = test["flood_in_next_3d"].astype(int).to_numpy()
    report = {
        "model_type": "hist-gradient-boosting event baseline (not the Google Flood Hub model)",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "label_definition": "Verified event starts within the next 3 days from feature_date; labels must include documented 0 and 1 examples.",
        "rows": len(merged),
        "train_rows": len(train), "validation_rows": len(val), "test_rows": len(test),
        "train_period_end": train_end, "validation_period_end": val_end,
        "test_period_start": str(test["date"].min()), "test_period_end": str(test["date"].max()),
        "features": feature_cols,
        "threshold_selection": {"method": "maximize F1 on validation period only", "selected_threshold": decision_threshold, "validation_best_f1": best_f1},
        "test_metrics": {
            "average_precision": float(average_precision_score(y, probabilities)),
            "roc_auc": float(roc_auc_score(y, probabilities)),
            "brier_score": float(brier_score_loss(y, probabilities)),
            "decision_threshold": decision_threshold,
            "balanced_accuracy": float(balanced_accuracy_score(y, predictions)),
            "precision": float(precision_score(y, predictions, zero_division=0)),
            "recall": float(recall_score(y, predictions, zero_division=0)),
            "f1": float(f1_score(y, predictions, zero_division=0)),
            "confusion_matrix_tn_fp_fn_tp": confusion_matrix(y, predictions, labels=[0, 1]).ravel().tolist(),
        },
        "warnings": [
            "This score is not a public flood probability until independent out-of-time and event-based validation is completed.",
            "The decision threshold is tuned on the validation period; the untouched test period is used only for final reporting.",
            "Unreported days must not be used as no-flood labels unless the source catalogue is known to be complete.",
            "A rainfall-level correlation is not proof that rainfall caused a given flood.",
        ],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.out_dir / "flood_event_classifier.joblib"
    joblib.dump({"pipeline": model, "feature_columns": feature_cols}, model_path)
    (args.out_dir / "flood_event_classifier.report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
