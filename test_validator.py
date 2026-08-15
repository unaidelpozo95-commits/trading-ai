import pandas as pd

from src.data.validation.validator import (
    DataValidator,
    AnomalyDetector,
)


data = pd.read_parquet(
    "data/raw/yahoo/AAPL.parquet"
)

# Basic validation
validator = DataValidator()

report = validator.validate(
    data,
    ticker="AAPL",
)

report.print()

# Anomaly detection
detector = AnomalyDetector()

anomalies = detector.detect(data)

print()
print("ANOMALIES")
print("-" * 40)

for anomaly in anomalies:
    print(
        f"{anomaly.date.date()} | "
        f"{anomaly.kind} | "
        f"{anomaly.description}"
    )

print()
print(f"Total anomalies: {len(anomalies)}")
