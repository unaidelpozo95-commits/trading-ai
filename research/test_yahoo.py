from src.data.providers.yahoo import YahooProvider

provider = YahooProvider()

data = provider.get_daily(
    "AAPL",
    "2015-01-01",
)

print(data.head())
print()
print(data.tail())
print()
print(data.shape)

data.to_parquet("data/raw/yahoo/AAPL.parquet", engine="pyarrow")
print("Guardado correctamente.")
