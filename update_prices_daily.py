"""
Actualizador incremental de precios — pensado para correr a diario.

Pide a Yahoo un ticker cada vez (no por lotes — la versión por lotes
daba errores de "possibly delisted; no timezone found" en casi todos
los tickers, sin diagnosticar la causa raíz todavía; ver README /
memoria del proyecto, pendiente).

Para cada ticker, mira la última fecha que ya tienes guardada y pide
a Yahoo solo los días nuevos desde entonces. Si un ticker no tiene
parquet todavía, hace la descarga completa normal.

USO (pensado para un cron diario):
    python update_prices_daily.py
"""

import os
import time

import pandas as pd

from src.data.providers.yahoo import YahooProvider  # <-- ajusta esta ruta si hace falta
from src.data.validator import DataValidator
from ticker_universe import load_tickers


START_DATE = "2015-01-01"
OUTPUT_DIR = "data/raw/yahoo"

SLEEP_SECONDS = 0.3


def update_ticker(ticker: str, provider: YahooProvider) -> tuple:

    path = os.path.join(OUTPUT_DIR, f"{ticker}.parquet")

    if not os.path.exists(path):
        data = provider.get_daily(ticker, start=START_DATE)
        data.to_parquet(path)
        return "full_download", len(data), data

    existing = pd.read_parquet(path)

    if not isinstance(existing.index, pd.DatetimeIndex):
        existing.index = pd.to_datetime(existing.index)

    last_date = existing.index.max()
    next_date = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        new_data = provider.get_daily(ticker, start=next_date)
    except ValueError:
        return "up_to_date", 0, existing

    combined = pd.concat([existing, new_data])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()

    combined.to_parquet(path)

    return "updated", len(new_data), combined


def main():

    tickers = load_tickers()

    print(f"Actualizando precios para {len(tickers)} tickers...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    provider = YahooProvider()
    validator = DataValidator()

    counts = {"full_download": 0, "updated": 0, "up_to_date": 0, "error": 0}
    errors = []
    quality_failures = []

    for i, ticker in enumerate(tickers, 1):

        try:
            status, n_rows, df = update_ticker(ticker, provider)
            counts[status] += 1

            if status != "up_to_date":
                print(f"[{i}/{len(tickers)}] {ticker}: {status} (+{n_rows} filas)")

            report = validator.validate(df, ticker=ticker)

            if not report.is_valid:
                quality_failures.append({
                    "ticker": ticker,
                    "duplicate_dates": report.duplicate_dates,
                    "chronological": report.chronological,
                    "missing_values": report.missing_values,
                    "invalid_prices": report.invalid_prices,
                    "invalid_ohlc": report.invalid_ohlc,
                    "invalid_volume": report.invalid_volume,
                })
                print(f"  AVISO calidad de datos: {ticker} no pasa la validación (ver data/data_quality_failures.csv)")

        except Exception as e:
            counts["error"] += 1
            errors.append((ticker, str(e)))
            print(f"[{i}/{len(tickers)}] {ticker}: ERROR ({e})")

        time.sleep(SLEEP_SECONDS)

    print()
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"Descargas completas (tickers nuevos): {counts['full_download']}")
    print(f"Actualizados con datos nuevos:         {counts['updated']}")
    print(f"Ya estaban al día:                     {counts['up_to_date']}")
    print(f"Errores:                               {counts['error']}")
    print(f"Con problemas de calidad de datos:     {len(quality_failures)}")

    if errors:
        failed_df = pd.DataFrame(errors, columns=["ticker", "error"])
        failed_df.to_csv("data/price_update_failures.csv", index=False)
        print()
        print("Detalle de errores guardado en: data/price_update_failures.csv")

    if quality_failures:
        pd.DataFrame(quality_failures).to_csv("data/data_quality_failures.csv", index=False)
        print("Detalle de calidad de datos guardado en: data/data_quality_failures.csv")


if __name__ == "__main__":
    main()
