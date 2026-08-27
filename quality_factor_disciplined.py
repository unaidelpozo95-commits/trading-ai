"""
Factor de Calidad (ROE) — misma disciplina que economic_factors_disciplined.py.

Requiere haber corrido antes fetch_sec_fundamentals.py (necesita
data/sec_fundamentals/{TICKER}.csv para cada ticker).

Metodología idéntica a la del momentum 12-1:
  - Especificación FIJA: top 30% ROE cross-sectional, sin barrido.
  - VALIDACIÓN (2020-2022): se mira una vez, solo para confirmar signo.
  - TEST (2023-2026): se mira UNA SOLA VEZ, se acepta el resultado.

El ROE de cada ticker se construye como una serie diaria "piecewise
constant": el valor conocido en cada fecha es el ROE del último 10-K
CUYA FECHA DE PRESENTACIÓN ya haya pasado en esa fecha — nunca se usa
un dato que todavía no se había publicado.
"""

import os

import numpy as np
import pandas as pd

from src.features.engine import FeatureEngine


TOP_PCT = 0.30
FORWARD_DAYS = 20

FUNDAMENTALS_DIR = "data/sec_fundamentals"


def load_tickers(path: str = "data/SP500.csv") -> list:
    """Lee tickers desde un CSV con columna 'ticker' o 'Symbol', arreglando
    símbolos con punto (BRK.B -> BRK-B)."""

    df = pd.read_csv(path)

    if "ticker" in df.columns:
        tickers = df["ticker"].tolist()
    elif "Symbol" in df.columns:
        tickers = df["Symbol"].tolist()
    else:
        raise ValueError(f"{path} no tiene columna 'ticker' ni 'Symbol'")

    tickers = [t.replace(".", "-") for t in tickers]

    return list(dict.fromkeys(tickers))


TICKERS = load_tickers()


def load_price_data(ticker: str) -> pd.DataFrame:

    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")
    df = FeatureEngine().build(data)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    entry = df["Open"].shift(-1)
    exit_price = df["Open"].shift(-(FORWARD_DAYS + 1))
    df[f"forward_{FORWARD_DAYS}d"] = exit_price / entry - 1

    return df


def build_roe_series(ticker: str, price_dates: pd.DatetimeIndex) -> pd.Series:

    path = os.path.join(FUNDAMENTALS_DIR, f"{ticker}.csv")

    if not os.path.exists(path):
        return pd.Series(index=price_dates, dtype=float)

    fundamentals = pd.read_csv(path, parse_dates=["filed_date"])
    fundamentals = fundamentals.sort_values("filed_date")

    roe_series = pd.Series(index=price_dates, dtype=float)

    for date in price_dates:
        available = fundamentals[fundamentals["filed_date"] <= date]
        if not available.empty:
            roe_series[date] = available.iloc[-1]["roe"]

    return roe_series


print()
print(f"Cargando precios para {len(TICKERS)} tickers...")

ticker_data = {}
skipped = []

for t in TICKERS:
    try:
        ticker_data[t] = load_price_data(t)
    except Exception as e:
        skipped.append((t, str(e)))

if skipped:
    print(f"Omitidos por falta de datos de precio: {len(skipped)} de {len(TICKERS)}")

print(f"Tickers con precio cargado: {len(ticker_data)}")

VALID_TICKERS = list(ticker_data.keys())

# UNIÓN de fechas, no intersección estricta — con 505 tickers, alguno
# seguro que tiene menos historial (IPO más tardía, huecos, etc.), y
# una intersección estricta dejaría el análisis reducido al rango más
# corto de todos. Cada ticker simplemente tendrá NaN en las fechas que
# no tenga datos, y el resto del código ya maneja NaN correctamente.
all_dates = set()
for df in ticker_data.values():
    all_dates |= set(df.index)
common_dates = sorted(all_dates)

print(f"Rango de fechas (unión): {len(common_dates)} sesiones, {common_dates[0].date()} -> {common_dates[-1].date()}")

for t in VALID_TICKERS:
    ticker_data[t] = ticker_data[t].reindex(common_dates)

print("Construyendo series de ROE point-in-time...")

roe_panel = pd.DataFrame(
    {t: build_roe_series(t, pd.DatetimeIndex(common_dates)) for t in VALID_TICKERS},
    index=common_dates,
)

n_with_roe = roe_panel.notna().any().sum()
print(f"Tickers con al menos un dato de ROE: {n_with_roe} de {len(VALID_TICKERS)}")

roe_rank = roe_panel.rank(axis=1, pct=True)


def build_panel(field):
    return pd.DataFrame(
        {t: ticker_data[t].loc[common_dates, field] for t in VALID_TICKERS},
        index=common_dates,
    )


forward_panel = build_panel(f"forward_{FORWARD_DAYS}d")


def evaluate(rank_panel, dates_subset, top_pct):

    excess_list = []

    for date in dates_subset:

        if date not in rank_panel.index:
            continue

        row = rank_panel.loc[date].dropna()
        if row.empty:
            continue

        threshold = row.quantile(1 - top_pct)
        selected = row[row >= threshold].index.tolist()

        if not selected:
            continue

        fwd_row = forward_panel.loc[date]
        universe_mean = fwd_row.dropna().mean()

        if pd.isna(universe_mean):
            continue

        for t in selected:
            v = fwd_row.get(t)
            if pd.notna(v):
                excess_list.append(v - universe_mean)

    if not excess_list:
        return {"n": 0, "alpha": None, "tstat": None}

    arr = np.array(excess_list)
    n = len(arr)
    mean = arr.mean()

    if n > 1 and arr.std(ddof=1) > 0:
        se = arr.std(ddof=1) / np.sqrt(n)
        tstat = mean / se
    else:
        tstat = None

    return {"n": n, "alpha": mean, "tstat": tstat}


validation_dates = [d for d in common_dates if 2020 <= d.year <= 2022]
test_dates = [d for d in common_dates if d.year >= 2023]


def report(label, result):
    alpha_str = f"{result['alpha']:>7.2%}" if result["alpha"] is not None else "    N/A"
    tstat_str = f"{result['tstat']:>5.2f}" if result["tstat"] is not None else " N/A"
    print(f"{label:<12} | N {result['n']:>5} | alpha {alpha_str} | t-stat {tstat_str}")


print()
print("=" * 80)
print("PASO 1 — VALIDACIÓN (2020-2022), especificación fija (top 30% ROE)")
print("=" * 80)

roe_validation = evaluate(roe_rank, validation_dates, TOP_PCT)
report("Validación", roe_validation)

roe_pass = roe_validation["alpha"] is not None and roe_validation["alpha"] > 0

print()
print(f"Calidad (ROE): {'signo correcto (positivo), se mira TEST' if roe_pass else 'signo incorrecto o sin datos, NO se mira TEST'}")

print()
print("=" * 80)
print("PASO 2 — TEST (2023-2026), se mira UNA SOLA VEZ, se acepta el resultado")
print("=" * 80)

if roe_pass:
    roe_test = evaluate(roe_rank, test_dates, TOP_PCT)
    report("TEST", roe_test)
else:
    print()
    print("-- Calidad (ROE): DESCARTADO en validación, no se mira TEST --")

print()
print("=" * 80)
print("NOTA")
print("=" * 80)
print(
    "Igual que con el momentum: este resultado de TEST es definitivo dentro\n"
    "de esta metodología. No se retoca, no se prueban más ventanas de ROE\n"
    "(TTM vs anual, distintos percentiles) para 'mejorarlo' después de verlo."
)
