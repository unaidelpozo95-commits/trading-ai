"""
Actualizador incremental de precios — por LOTES, no ticker a ticker.

La versión ticker-a-ticker (con YahooProvider) tarda ~4h con miles de
tickers, porque hace una llamada de red por ticker. Se probó una
versión por lotes anteriormente y falló con "possibly delisted; no
timezone found" en casi todos los tickers — la causa raíz resultó ser
una versión desactualizada de yfinance, incompatible con cambios
internos de la API de Yahoo. Confirmado con yfinance 1.7.0 que la
descarga por lotes (yf.download, con y sin threads=True) funciona
correctamente. Ver README / memoria del proyecto para el diagnóstico
completo.

Esta versión pide varios tickers de golpe en cada llamada a Yahoo,
agrupados en lotes de BATCH_SIZE, con threads=True (paralelismo
interno de yfinance). Valida cada ticker con DataValidator tras
actualizarlo, igual que la versión anterior — sin bloquear el
proceso, solo avisando.

Separa los tickers en dos grupos:
  - NUEVOS (sin parquet todavía): descarga completa desde START_DATE.
  - EXISTENTES: se pide solo un margen de los últimos
    INCREMENTAL_LOOKBACK_DAYS días (de sobra para cubrir fines de
    semana/festivos), y de ahí se queda solo con las filas
    realmente posteriores a lo último que ya tenías guardado.

REQUISITO: yfinance actualizado (pip install yfinance --upgrade).
Si vuelven a aparecer errores masivos de "possibly delisted", lo
primero es comprobar la versión de yfinance otra vez.

USO (pensado para un cron diario):
    python update_prices_daily.py
    python update_prices_daily.py --limit 200   # prueba con una muestra
"""

import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
import yfinance.shared as yf_shared

from src.data.validator import DataValidator
from ticker_universe import load_tickers


START_DATE = "2015-01-01"
OUTPUT_DIR = "data/raw/yahoo"

BATCH_SIZE = 200
INCREMENTAL_LOOKBACK_DAYS = 10
SLEEP_BETWEEN_BATCHES = 1.0
MAX_RETRIES = 2            # reintentos de un lote que lanza excepción
RETRY_BACKOFF_SECONDS = 20
ERRORS_CSV = "data/price_update_errors.csv"

# Errores por ticker que Yahoo/yfinance devuelve, acumulados en la ejecución
error_log = []


class YFErrorCollector(logging.Handler):
    """yfinance (>=1.x) ya no rellena yfinance.shared._ERRORS: los errores
    por ticker solo salen por su logger, con el formato "$TICKER: motivo".
    Se recogen aquí para guardarlos en ERRORS_CSV."""

    LINE = re.compile(r"^\$(.+?): (.*)$", re.S)

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.items = []

    def emit(self, record):
        m = self.LINE.match(record.getMessage())
        if m:
            self.items.append((m.group(1), m.group(2).strip()[:200]))


_collector = YFErrorCollector()
logging.getLogger("yfinance").addHandler(_collector)


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


def download_batch(tickers_batch: list, start_date: str, label: str = "") -> dict:
    """Descarga varios tickers en una sola llamada. Devuelve
    {ticker: DataFrame} — los tickers sin datos simplemente no
    aparecen en el resultado (no es un error).

    Si el lote lanza una excepción se reintenta (con espera) y, si sigue
    fallando, se registra y se devuelve vacío SIN abortar el resto. Los
    errores por ticker de yfinance se guardan en ERRORS_CSV."""

    data = None
    for attempt in range(1, MAX_RETRIES + 2):
        if hasattr(yf_shared, "_ERRORS"):
            yf_shared._ERRORS.clear()
        _collector.items.clear()
        try:
            data = yf.download(
                tickers_batch,
                start=start_date,
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=False,
            )
            break
        except Exception as e:
            print(f"    AVISO lote {label}: {type(e).__name__}: {e} (intento {attempt}/{MAX_RETRIES + 1})")
            error_log.append({"lote": label, "ticker": "(lote entero)", "error": f"{type(e).__name__}: {e}"})
            if attempt <= MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    for t, msg in (getattr(yf_shared, "_ERRORS", {}) or {}).items():
        error_log.append({"lote": label, "ticker": t, "error": str(msg)[:200]})
    for t, msg in _collector.items:
        error_log.append({"lote": label, "ticker": t, "error": msg})

    result = {}

    if data is None or data.empty:
        return result

    if len(tickers_batch) == 1:
        result[tickers_batch[0]] = data.dropna(how="all")
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


def update_existing_ticker(ticker: str, new_df: pd.DataFrame) -> tuple:
    """Combina los datos nuevos con lo que ya había, quedándose solo
    con las filas realmente nuevas. Devuelve (n_filas_nuevas,
    dataframe_completo_resultante) — este último para poder validarlo."""

    path = os.path.join(OUTPUT_DIR, f"{ticker}.parquet")
    existing = pd.read_parquet(path)

    if not isinstance(existing.index, pd.DatetimeIndex):
        existing.index = pd.to_datetime(existing.index)

    truly_new = new_df[new_df.index > existing.index.max()]

    if truly_new.empty:
        return 0, existing

    combined = pd.concat([existing, truly_new])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()

    combined.to_parquet(path)

    return len(truly_new), combined


def main():

    tickers = load_tickers()
    print(f"yfinance {yf.__version__}")
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
        step = max(1, len(tickers) // limit)
        tickers = tickers[::step][:limit]
        print(f"MODO PRUEBA: solo {len(tickers)} tickers (--limit {limit})")
    print(f"Universo: {len(tickers)} tickers")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    validator = DataValidator()
    quality_failures = []

    new_tickers, existing_tickers = split_new_vs_existing(tickers)
    print(f"Nuevos (descarga completa): {len(new_tickers)}")
    print(f"Existentes (actualización incremental): {len(existing_tickers)}")

    counts = {"full_download": 0, "updated": 0, "up_to_date": 0, "no_data": 0}

    def validate_and_track(ticker, df):
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

    if new_tickers:
        print()
        print("Descargando histórico completo de tickers nuevos, por lotes...")
        n_batches = (len(new_tickers) + BATCH_SIZE - 1) // BATCH_SIZE
        for i, batch in enumerate(chunk_list(new_tickers, BATCH_SIZE), 1):
            print(f"  Lote {i}/{n_batches} ({len(batch)} tickers)...")
            results = download_batch(batch, START_DATE, f"nuevos {i}/{n_batches}")
            for ticker, df in results.items():
                save_new_ticker(ticker, df)
                validate_and_track(ticker, df)
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
            results = download_batch(batch, lookback_start, f"existentes {i}/{n_batches}")
            for ticker in batch:
                if ticker not in results:
                    counts["up_to_date"] += 1
                    continue
                n_new, full_df = update_existing_ticker(ticker, results[ticker])
                validate_and_track(ticker, full_df)
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
    print(f"Con problemas de calidad de datos:     {len(quality_failures)}")

    if error_log:
        err_df = pd.DataFrame(error_log)
        err_df.to_csv(ERRORS_CSV, index=False)
        print(f"Errores de Yahoo por ticker: {len(err_df)} (agrupados abajo) -> {ERRORS_CSV}")
        for msg, n in err_df["error"].str[:90].value_counts().head(5).items():
            print(f"   {n:>5} x {msg}")

    if quality_failures:
        pd.DataFrame(quality_failures).to_csv("data/data_quality_failures.csv", index=False)
        print("Detalle de calidad de datos guardado en: data/data_quality_failures.csv")


if __name__ == "__main__":
    main()
