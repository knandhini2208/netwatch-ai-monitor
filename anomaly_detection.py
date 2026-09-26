"""
anomaly_detection.py
----------------------
Trains an unsupervised Isolation Forest model on the network metrics
and scores each sample for "how anomalous" it is. Isolation Forest is
chosen because we don't have labeled failure data in a real deployment
-- it learns what "normal" looks like and flags what doesn't fit.
"""

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report

from preprocessing import METRIC_COLUMNS, load_and_clean


def train_model(df, contamination=0.05, random_state=42):
    """
    Trains an Isolation Forest on the metric columns.
    `contamination` is our estimate of what fraction of the data
    is anomalous -- tune this to your dataset.
    """
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=random_state,
    )
    model.fit(df[METRIC_COLUMNS])
    return model


def score_dataset(df, model):
    """
    Adds two columns to df:
        anomaly_score  - raw model score (lower = more abnormal)
        predicted_anomaly - 1 if flagged anomalous, else 0
    """
    df = df.copy()
    df["anomaly_score"] = model.decision_function(df[METRIC_COLUMNS])
    # sklearn's predict() returns -1 for anomalies, 1 for normal
    df["predicted_anomaly"] = (model.predict(df[METRIC_COLUMNS]) == -1).astype(int)
    return df


def evaluate(df):
    """
    If ground-truth 'is_anomaly' exists (e.g. from the simulator),
    prints a classification report comparing predictions to truth.
    Useful for your project report / viva.
    """
    if "is_anomaly" not in df.columns:
        print("No ground-truth labels found -- skipping evaluation.")
        return
    print(classification_report(
        df["is_anomaly"], df["predicted_anomaly"],
        target_names=["normal", "anomaly"]
    ))


if __name__ == "__main__":
    df = load_and_clean()
    model = train_model(df)
    scored = score_dataset(df, model)

    print(scored[["timestamp", "latency_ms", "packet_loss",
                   "bandwidth_mbps", "anomaly_score", "predicted_anomaly"]]
          .sort_values("anomaly_score").head(10))

    print("\nEvaluation against injected ground truth:\n")
    evaluate(scored)

    scored.to_csv("scored_data.csv", index=False)
    print("\nSaved scored_data.csv")
