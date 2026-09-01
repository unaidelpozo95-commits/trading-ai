import pandas as pd

from src.features.engine import FeatureEngine


data = pd.read_parquet(
    "data/raw/yahoo/AAPL.parquet"
)

engine = FeatureEngine()

features = engine.build(data)

print(features.tail())

print()
print("Shape:", features.shape)

print()
print("Features:")
print(features.columns.tolist())

print()
print("NaN count:")
print(features.isna().sum())
