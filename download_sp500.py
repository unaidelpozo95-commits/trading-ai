"""
Descarga masiva de datos para el universo del S&P 500.

Reutiliza YahooProvider, igual que download_universe.py, pero con
manejo de errores por ticker — con 500 tickers, es seguro que
alguno falle (deslistado, símbolo cambiado, rate limiting, etc.) y
no queremos que eso pare toda la descarga.

Requiere que data/sp500_tickers.csv ya exista (ejecuta primero
get_sp500_tickers.py).
"""

import os
import time

import pandas as pd

from src.data.providers.yahoo import YahooProvider  # <-- ajusta esta ruta si hace falta


START_DATE = "2015-01-01"
OUTPUT_DIR = "data/raw/yahoo"

SLEEP_SECONDS = 0.3


def main():

    tickers_df = pd.read_csv("data/sp500_tickers.csv")
    tickers = tickers_df["ticker"].tolist()

    print(f"Descargando {len(tickers)} tickers desde {START_DATE}...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    provider = YahooProvider()

    ok = []
    failed = []
    skipped = []

    for i, ticker in enumerate(tickers, 1):

        output_path = os.path.join(OUTPUT_DIR, f"{ticker}.parquet")

        if os.path.exists(output_path):
            skipped.append(ticker)
            continue

        try:
            data = provider.get_daily(ticker, start=START_DATE)
            data.to_parquet(output_path)
            ok.append(ticker)
            print(f"[{i}/{len(tickers)}] {ticker}: OK ({len(data)} filas)")

        except Exception as e:
            failed.append((ticker, str(e)))
            print(f"[{i}/{len(tickers)}] {ticker}: FALLO ({e})")

        time.sleep(SLEEP_SECONDS)

    print()
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"Descargados correctamente: {len(ok)}")
    print(f"Ya existían (omitidos):    {len(skipped)}")
    print(f"Fallidos:                  {len(failed)}")

    if failed:
        print()
        print("Tickers que fallaron:")
        for ticker, error in failed:
            print(f"  {ticker}: {error}")

        failed_df = pd.DataFrame(failed, columns=["ticker", "error"])
        failed_df.to_csv("data/sp500_download_failures.csv", index=False)
        print()
        print("Detalle de fallos guardado en: data/sp500_download_failures.csv")


if __name__ == "__main__":
    main()
