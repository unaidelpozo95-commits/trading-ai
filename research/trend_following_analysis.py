"""
Trend-following a nivel de cartera.

Hipótesis: distinta del momentum de corto plazo (AAPL) y de la
reversión — aquí es la lógica CTA clásica: cuando un activo está en
tendencia alcista confirmada (Close > SMA200), tiende a seguir
rindiendo mejor que cuando no lo está, en horizontes largos (varias
semanas/meses, no días).

Metodología: se agrupan TODOS los ticker-días del universo (no hace
falta ranking cruzado diario aquí — es una condición por activo, no
relativa a los demás ese día). Se compara el retorno futuro medio de
los días "en tendencia" contra los días "sin tendencia", con t-stat.
"""

import numpy as np
import pandas as pd

from src.features.engine import FeatureEngine


TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

FORWARD_DAYS = [5, 10, 20, 40, 60, 120]

TREND_THRESHOLDS = [0.0, 0.05, 0.10]


def load_ticker(ticker: str) -> pd.DataFrame:
    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")
    engine = FeatureEngine()
    df = engine.build(data)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    for days in FORWARD_DAYS:
        entry = df["Open"].shift(-1)
        exit_price = df["Open"].shift(-(days + 1))
        df[f"forward_{days}d"] = exit_price / entry - 1
    df["ticker"] = ticker
    return df


print()
print("Cargando universo:", TICKERS)

frames = []
for t in TICKERS:
    df = load_ticker(t)
    frames.append(df)

pooled = pd.concat(frames)
pooled["year"] = pooled.index.year

print(f"Total ticker-días combinados: {len(pooled)}")

development = pooled["year"] <= 2022
test = pooled["year"] >= 2023


def evaluate_trend(trend_threshold, period_mask, forward_days):

    in_trend = pooled["distance_sma_200"] >= trend_threshold

    trend_returns = pooled.loc[in_trend & period_mask, f"forward_{forward_days}d"].dropna()
    no_trend_returns = pooled.loc[~in_trend & period_mask, f"forward_{forward_days}d"].dropna()

    if trend_returns.empty or no_trend_returns.empty:
        return {"n_trend": len(trend_returns), "alpha": None, "tstat": None}

    alpha = trend_returns.mean() - no_trend_returns.mean()

    n1, n2 = len(trend_returns), len(no_trend_returns)
    var1, var2 = trend_returns.var(ddof=1), no_trend_returns.var(ddof=1)
    se = ((var1 / n1) + (var2 / n2)) ** 0.5
    tstat = alpha / se if se > 0 else None

    return {"n_trend": n1, "n_no_trend": n2, "alpha": alpha, "tstat": tstat}


print()
print("=" * 90)
print("TREND-FOLLOWING — forward 20d, por umbral de tendencia")
print("=" * 90)
print(f"{'Umbral':>7} | {'DevN':>8} {'DevAlpha':>9} {'DevT':>6} | {'OOSN':>8} {'OOSAlpha':>9} {'OOST':>6}")
print("-" * 90)

for threshold in TREND_THRESHOLDS:
    dev = evaluate_trend(threshold, development, 20)
    oos = evaluate_trend(threshold, test, 20)
    dev_a = f"{dev['alpha']:>8.2%}" if dev["alpha"] is not None else "     N/A"
    dev_t = f"{dev['tstat']:>5.2f}" if dev["tstat"] is not None else "  N/A"
    oos_a = f"{oos['alpha']:>8.2%}" if oos["alpha"] is not None else "     N/A"
    oos_t = f"{oos['tstat']:>5.2f}" if oos["tstat"] is not None else "  N/A"
    print(f"{threshold:>6.0%} | {dev['n_trend']:>8} {dev_a} {dev_t} | {oos['n_trend']:>8} {oos_a} {oos_t}")

print()
print("=" * 90)
print("CURVA POR HORIZONTE — umbral 5%")
print("=" * 90)
print(f"{'Horizonte':>10} | {'DevAlpha':>9} {'DevT':>6} | {'OOSAlpha':>9} {'OOST':>6}")

for days in FORWARD_DAYS:
    dev = evaluate_trend(0.05, development, days)
    oos = evaluate_trend(0.05, test, days)
    dev_a = f"{dev['alpha']:>8.2%}" if dev["alpha"] is not None else "     N/A"
    dev_t = f"{dev['tstat']:>5.2f}" if dev["tstat"] is not None else "  N/A"
    oos_a = f"{oos['alpha']:>8.2%}" if oos["alpha"] is not None else "     N/A"
    oos_t = f"{oos['tstat']:>5.2f}" if oos["tstat"] is not None else "  N/A"
    print(f"{days:>9}d | {dev_a} {dev_t} | {oos_a} {oos_t}")

print()
print("=" * 90)
print("LECTURA")
print("=" * 90)
print(
    "Busca alpha positivo Y t-stat >= ~2 en Dev y OOS a la vez, idealmente\n"
    "en varios umbrales y horizontes (no solo uno). El trend-following\n"
    "clásico suele necesitar horizontes largos (40-120 días) para mostrar\n"
    "su ventaja, así que no descartes el patrón solo por ver poco en 5-20d."
)
