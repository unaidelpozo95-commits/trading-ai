"""
Diagnóstico de la descarga de precios por lotes (yf.download).

No toca ningún dato de producción: solo descarga una muestra pequeña de
tickers de tu universo con distintas configuraciones y dice cuál
funciona, cuánto tarda y QUÉ error devuelve Yahoo por ticker (el
"possibly delisted; no timezone found" suele ser en realidad un límite
de peticiones o un bloqueo, no un ticker retirado).

Pruebas:
  0. Versiones y un ticker suelto (AAPL) para descartar red/bloqueo.
  1. Lotes de 10, 50 y 200 tickers con threads=True.
  2. Lote de 50 con threads=False (sin paralelismo).
  3. Lote de 50 con la ventana por "period" en vez de "start".

USO (en el servidor, desde ~/trading-ai con el venv activado):
    python diagnose_price_download.py            # muestra de 200 tickers
    python diagnose_price_download.py 100        # muestra de 100

Guarda todo en data/price_diag_output.txt — pégamelo entero.
"""

import logging
import os
import platform
import sys
import time
from collections import Counter

import pandas as pd
import yfinance as yf
import yfinance.shared as yf_shared

from ticker_universe import load_tickers


SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 200
OUT = []


def out(text=""):
    print(text, flush=True)
    OUT.append(str(text))


class Collector(logging.Handler):
    """Recoge los avisos/errores que yfinance escribe por ticker."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


collector = Collector()
logging.getLogger("yfinance").addHandler(collector)


def summarize_errors(label_n_total):
    """Agrupa los errores de yfinance (diccionario interno + log)."""
    errors = dict(getattr(yf_shared, "_ERRORS", {}) or {})
    groups = Counter(str(v)[:110] for v in errors.values())
    out(f"   errores por ticker (yfinance._ERRORS): {len(errors)} de {label_n_total}")
    for msg, n in groups.most_common(5):
        out(f"     {n:>4} x {msg}")
    log_groups = Counter(m[:110] for m in collector.messages)
    if log_groups:
        out(f"   mensajes del log de yfinance: {len(collector.messages)}")
        for msg, n in log_groups.most_common(5):
            out(f"     {n:>4} x {msg}")
    for name in ("YFRateLimitError", "YFTzMissingError"):
        if any(name in str(v) for v in errors.values()) or any(name in m for m in collector.messages):
            out(f"   >>> aparece {name}")
    if any("Too Many Requests" in str(v) or "429" in str(v) for v in errors.values()) or \
       any("Too Many Requests" in m or "429" in m for m in collector.messages):
        out("   >>> Yahoo está limitando por exceso de peticiones (429)")


def run_test(title, tickers, **kwargs):
    out()
    out(f"--- {title} ({len(tickers)} tickers) ---")
    if hasattr(yf_shared, "_ERRORS"):
        yf_shared._ERRORS.clear()
    collector.messages.clear()
    t0 = time.time()
    try:
        data = yf.download(tickers, group_by="ticker", progress=False, auto_adjust=False, **kwargs)
    except Exception as e:
        out(f"   EXCEPCIÓN: {type(e).__name__}: {e}")
        summarize_errors(len(tickers))
        return
    elapsed = time.time() - t0

    if data is None or data.empty:
        ok = 0
    elif len(tickers) == 1:
        ok = 1
    else:
        level0 = set(data.columns.get_level_values(0))
        ok = sum(1 for t in tickers if t in level0 and not data[t].dropna(how="all").empty)

    out(f"   con datos: {ok}/{len(tickers)} ({ok / len(tickers):.0%}) en {elapsed:.1f} s")
    summarize_errors(len(tickers))


out("=" * 70)
out("DIAGNÓSTICO DE DESCARGA DE PRECIOS")
out("=" * 70)
out(f"yfinance {yf.__version__} | pandas {pd.__version__} | python {platform.python_version()} | {platform.platform()}")
for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    if os.environ.get(var):
        out(f"proxy en entorno: {var}={os.environ[var]}")

universe = load_tickers()
step = max(1, len(universe) // SAMPLE)
sample = universe[::step][:SAMPLE]
out(f"Universo: {len(universe)} tickers; muestra repartida: {len(sample)}")

out()
out("--- 0. Un ticker suelto (AAPL) ---")
try:
    t0 = time.time()
    h = yf.Ticker("AAPL").history(period="5d")
    out(f"   filas: {len(h)} en {time.time() - t0:.1f} s" + ("" if len(h) else "   <-- VACÍO: problema de red/bloqueo, no de lotes"))
except Exception as e:
    out(f"   EXCEPCIÓN: {type(e).__name__}: {e}")

start = (pd.Timestamp.now() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")

run_test("1a. lote de 10, threads=True", sample[:10], start=start, threads=True)
time.sleep(2)
run_test("1b. lote de 50, threads=True", sample[:50], start=start, threads=True)
time.sleep(2)
run_test("1c. lote de 200, threads=True", sample[:200], start=start, threads=True)
time.sleep(2)
run_test("2. lote de 50, threads=False", sample[:50], start=start, threads=False)
time.sleep(2)
run_test("3. lote de 50, period='10d'", sample[:50], period="10d", threads=True)

out()
out("Guardado en data/price_diag_output.txt — pégame ese fichero.")
os.makedirs("data", exist_ok=True)
with open("data/price_diag_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
