"""
Actualizador incremental de precios — por LOTES, no ticker a ticker.

La versión anterior hacía una llamada de red por ticker; con varios
miles de tickers (NYSE+AMEX+NASDAQ+SP500), eso son horas solo en
latencia de red, aunque cada llamada traiga poquísimos datos nuevos.

Esta versión pide varios tickers de golpe en cada llamada a Yahoo
(con threads=True, que además paraleliza internamente), agrupados en
lotes de BATCH_SIZE. Con esto, miles de tickers pasan de horas a
minutos.

Separa los tickers en dos grupos:
  - NUEVOS (sin parquet todavía): descarga completa desde START_DATE.
  - EXISTENTES: se pide solo un margen de los últimos
    INCREMENTAL_LOOKBACK_DAYS días (de sobra para cubrir fines de
    semana/festivos), y de ahí se queda solo con las filas
    realmente posteriores a lo último que ya tenías guardado.

USO (pensado para un cron diario):
    python update_prices_daily.py
"""

import os
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from ticker_universe import load_tickers


START_DATE = "2015-01-01"
OUTPUT_DIR = "data/raw/yahoo"

BATCH_SIZE = 200
INCREMENTAL_LOOKBACK_DAYS = 10
SLEEP_BETWEEN_BATCHES = 1.0


def chunk_list(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def split_new_vs_existing(tickers: list) -> tuple:

    new_tickers, existing_tickers = [], []

    for t in tickers:
        path = os.path.join(OUTPUT_DIR, f"{t}.parquet")
        if os.path.exists(path):
            existing_tickers.append(t)
        else:
            new_tickers.append(t)

    return new_tickers, existing_tickers


def download_batch(tickers_batch: list, start_date: str) -> dict:

    data = yf.download(
        tickers_batch,
        start=start_date,
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=False,
    )

    result = {}

    if len(tickers_batch) == 1:
        ticker = tickers_batch[0]
        if not data.empty:
            result[ticker] = data.dropna(how="all")
        return result

    for ticker in tickers_batch:
        if ticker not in data.columns.get_level_values(0):
            continue
        df_t = data[ticker].dropna(how="all")
        if not df_t.empty:
            result[ticker] = df_t

    return result


def save_new_ticker(ticker: str, df: pd.DataFrame) -> None:
    path = os.path.join(OUTPUT_DIR, f"{ticker}.parquet")
    df.to_parquet(path)


def update_existing_ticker(ticker: str, new_df: pd.DataFrame) -> int:

    path = os.path.join(OUTPUT_DIR, f"{ticker}.parquet")
    existing = pd.read_parquet(path)

    if not isinstance(existing.index, pd.DatetimeIndex):
        existing.index = pd.to_datetime(existing.index)

    last_date = existing.index.max()

    truly_new = new_df[new_df.index > last_date]

    if truly_new.empty:
        return 0

    combined = pd.concat([existing, truly_new])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()

    combined.to_parquet(path)

    return len(truly_new)


def main():

    tickers = load_tickers()
    print(f"Universo: {len(tickers)} tickers")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    new_tickers, existing_tickers = split_new_vs_existing(tickers)
    print(f"Nuevos (descarga completa): {len(new_tickers)}")
    print(f"Existentes (actualización incremental): {len(existing_tickers)}")

    counts = {"full_download": 0, "updated": 0, "up_to_date": 0, "no_data": 0}

    if new_tickers:
        print()
        print("Descargando histórico completo de tickers nuevos, por lotes...")
        n_batches = (len(new_tickers) + BATCH_SIZE - 1) // BATCH_SIZE
        for i, batch in enumerate(chunk_list(new_tickers, BATCH_SIZE), 1):
            print(f"  Lote {i}/{n_batches} ({len(batch)} tickers)...")
            results = download_batch(batch, START_DATE)
            for ticker, df in results.items():
                save_new_ticker(ticker, df)
                counts["full_download"] += 1
            counts["no_data"] += len(batch) - len(results)
            time.sleep(SLEEP_BETWEEN_BATCHES)

    if existing_tickers:
        print()
        print("Actualizando tickers existentes, por lotes...")
        lookback_start = (datetime.now() - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        n_batches = (len(existing_tickers) + BATCH_SIZE - 1) // BATCH_SIZE
        for i, batch in enumerate(chunk_list(existing_tickers, BATCH_SIZE), 1):
            print(f"  Lote {i}/{n_batches} ({len(batch)} tickers)...")
            results = download_batch(batch, lookback_start)
            for ticker in batch:
                if ticker not in results:
                    counts["up_to_date"] += 1
                    continue
                n_new = update_existing_ticker(ticker, results[ticker])
                if n_new > 0:
                    counts["updated"] += 1
                else:
                    counts["up_to_date"] += 1
            time.sleep(SLEEP_BETWEEN_BATCHES)

    print()
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"Descargas completas (tickers nuevos): {counts['full_download']}")
    print(f"Actualizados con datos nuevos:         {counts['updated']}")
    print(f"Ya estaban al día:                     {counts['up_to_date']}")
    print(f"Sin datos de Yahoo:                    {counts['no_data']}")


if __name__ == "__main__":
    main()
