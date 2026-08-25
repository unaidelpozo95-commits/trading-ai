"""
Descarga y guarda en Parquet los datos históricos de cada ticker del
universo, siguiendo la misma convención que ya usas para AAPL:
data/raw/yahoo/{TICKER}.parquet

AJUSTA el import de YahooProvider a la ruta real que tenga en tu
repo (no tengo visibilidad de dónde vive exactamente ese archivo
más allá de su contenido) — probablemente algo como:
    from src.data.providers.yahoo import YahooProvider
"""

import os

from src.data.providers.yahoo import YahooProvider  # <-- ajusta esta ruta si hace falta


TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

START_DATE = "2015-01-01"

OUTPUT_DIR = "data/raw/yahoo"


def main():

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    provider = YahooProvider()

    for ticker in TICKERS:

        output_path = os.path.join(OUTPUT_DIR, f"{ticker}.parquet")

        if os.path.exists(output_path):
            print(f"{ticker}: ya existe en {output_path}, se omite")
            continue

        print(f"{ticker}: descargando desde {START_DATE}...")

        data = provider.get_daily(ticker, start=START_DATE)

        data.to_parquet(output_path)

        print(f"{ticker}: guardado en {output_path} ({len(data)} filas)")

    print()
    print("Listo.")


if __name__ == "__main__":
    main()