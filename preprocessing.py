"""
preprocessing.py
-----------------
Cleans the raw network data and computes descriptive statistics
(mean, dispersion, variance, five-point summary, etc.) exactly as
covered in Unit 2 of the syllabus, before the data reaches the
anomaly-detection model.
"""

import pandas as pd
import numpy as np

METRIC_COLUMNS = ["latency_ms", "packet_loss", "bandwidth_mbps",
                   "jitter_ms", "error_rate"]


def load_and_clean(csv_path="network_data.csv"):
    """Loads the CSV, handles missing values, removes duplicates."""
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])

    # Handle missing values: forward-fill then back-fill as a fallback
    df[METRIC_COLUMNS] = df[METRIC_COLUMNS].ffill().bfill()

    # Drop exact duplicate rows, if any
    df = df.drop_duplicates().reset_index(drop=True)

    return df


def descriptive_stats(df):
    """
    Returns a DataFrame of descriptive statistics per metric:
    mean, std dev, variance, min, Q1, median, Q3, max (five-point
    summary), and kurtosis -- as named explicitly in the syllabus.
    """
    stats = {}
    for col in METRIC_COLUMNS:
        series = df[col]
        stats[col] = {
            "mean": series.mean(),
            "std_dev": series.std(),
            "variance": series.var(),
            "min": series.min(),
            "Q1": series.quantile(0.25),
            "median": series.median(),
            "Q3": series.quantile(0.75),
            "max": series.max(),
            "kurtosis": series.kurtosis(),
        }
    return pd.DataFrame(stats).T.round(3)


def add_zscore_features(df):
    """
    Adds a z-score column per metric. z = (x - mean) / std.
    A simple statistical baseline used alongside the ML model --
    any |z| > 3 is a classic "textbook" outlier flag.
    """
    df = df.copy()
    for col in METRIC_COLUMNS:
        mean = df[col].mean()
        std = df[col].std()
        df[f"{col}_zscore"] = (df[col] - mean) / std if std > 0 else 0
    return df


def normalize(df, columns=None):
    """Min-max normalizes the given columns to a 0-1 range."""
    columns = columns or METRIC_COLUMNS
    df = df.copy()
    for col in columns:
        min_val, max_val = df[col].min(), df[col].max()
        if max_val > min_val:
            df[f"{col}_norm"] = (df[col] - min_val) / (max_val - min_val)
        else:
            df[f"{col}_norm"] = 0.0
    return df


if __name__ == "__main__":
    df = load_and_clean()
    print("Descriptive statistics:\n")
    print(descriptive_stats(df))

    df_z = add_zscore_features(df)
    flagged = df_z[(df_z[[f"{c}_zscore" for c in METRIC_COLUMNS]].abs() > 3).any(axis=1)]
    print(f"\nRows flagged by simple z-score rule (|z| > 3): {len(flagged)}")
