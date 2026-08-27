"""
Backtest real del factor Calidad (ROE).

Long-short: top 30% ROE (largo) vs bottom 30% ROE (corto), dollar-
neutral. Holding de ~252 sesiones (1 año) — acorde a la frecuencia
natural de actualización del dato (el ROE solo cambia una vez al año,
al presentar el 10-K), a diferencia del momentum (mensual) o la
reversión (diaria). Esto debería traducirse en un turnover mucho
menor y, por tanto, menos coste de fricción.

Rebalanceo continuo/solapado (misma metodología que validó la
reversión y el momentum) — no periódico.

El único bloque que importa de verdad es el HOLDOUT REAL (2023+, con
fricciones) — el resto es contexto/referencia.
"""

import os

import numpy as np
import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.metrics import compute_metrics


LEG_PCT = 0.30
HOLDING_DAYS = 252

INITIAL_CAPITAL = 100_000.0

COMMISSION_PCT = 0.0005
SLIPPAGE_PCT = 0.0005
ANNUAL_BORROW_RATE = 0.01

FUNDAMENTALS_DIR = "data/sec_fundamentals"


def load_tickers(path: str = "data/SP500.csv") -> list:
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
for t in TICKERS:
    try:
        ticker_data[t] = load_price_data(t)
    except Exception:
        continue

print(f"Tickers con precio cargado: {len(ticker_data)}")

VALID_TICKERS = list(ticker_data.keys())

all_dates = set()
for df in ticker_data.values():
    all_dates |= set(df.index)
common_dates = sorted(all_dates)

for t in VALID_TICKERS:
    ticker_data[t] = ticker_data[t].reindex(common_dates)

print(f"Rango de fechas: {len(common_dates)} sesiones, {common_dates[0].date()} -> {common_dates[-1].date()}")

print("Construyendo ROE point-in-time...")

roe_panel = pd.DataFrame(
    {t: build_roe_series(t, pd.DatetimeIndex(common_dates)) for t in VALID_TICKERS},
    index=common_dates,
)

FINAL_TICKERS = [t for t in VALID_TICKERS if roe_panel[t].notna().any()]
print(f"Tickers con ROE disponible: {len(FINAL_TICKERS)}")

roe_rank = roe_panel[FINAL_TICKERS].rank(axis=1, pct=True)

return_1d_panel = pd.DataFrame(
    {t: ticker_data[t].loc[common_dates, "return_1d"] for t in FINAL_TICKERS},
    index=common_dates,
)

n = len(common_dates)
return_matrix = return_1d_panel[FINAL_TICKERS].values
roe_matrix = roe_rank[FINAL_TICKERS].values

print("Precomputando cestas largas/cortas por día...")

long_baskets, short_baskets = [], []

for i in range(n):
    row = roe_matrix[i]
    valid = ~np.isnan(row)
    if valid.sum() == 0:
        long_baskets.append(np.array([], dtype=int))
        short_baskets.append(np.array([], dtype=int))
        continue
    idxs = np.where(valid)[0]
    vals = row[idxs]
    long_thr = np.quantile(vals, 1 - LEG_PCT)
    short_thr = np.quantile(vals, LEG_PCT)
    long_baskets.append(idxs[vals >= long_thr])
    short_baskets.append(idxs[vals <= short_thr])

print("Simulando cartera con cohortes solapadas (esto puede tardar)...")

portfolio_returns = np.full(n, np.nan)

for x in range(1, n):
    start_d = max(0, x - HOLDING_DAYS)
    contributions = []
    for d in range(start_d, x):
        long_idx, short_idx = long_baskets[d], short_baskets[d]
        if len(long_idx) == 0 or len(short_idx) == 0:
            continue
        long_rets = return_matrix[x, long_idx]
        short_rets = return_matrix[x, short_idx]
        long_rets = long_rets[~np.isnan(long_rets)]
        short_rets = short_rets[~np.isnan(short_rets)]
        if len(long_rets) == 0 or len(short_rets) == 0:
            continue
        contributions.append(0.5 * long_rets.mean() - 0.5 * short_rets.mean())
    if contributions:
        portfolio_returns[x] = np.mean(contributions)

returns_series = pd.Series(portfolio_returns, index=common_dates)

daily_trading_drag = 2 * (1 / HOLDING_DAYS) * (COMMISSION_PCT + SLIPPAGE_PCT)
daily_borrow_drag = 0.5 * (ANNUAL_BORROW_RATE / 252)
daily_total_drag = daily_trading_drag + daily_borrow_drag

print(f"\nFricción diaria aplicada: {daily_total_drag:.5%} (mucho menor que momentum/reversión por el holding largo)")

returns_net = returns_series - daily_total_drag
returns_net[returns_series.isna()] = np.nan


def build_equity(returns_sub, initial_capital):
    clean = returns_sub.dropna()
    if clean.empty:
        return pd.Series(dtype=float)
    return initial_capital * (1 + clean).cumprod()


print()
print("=" * 90)
print(f"CALIDAD (ROE) LONG-SHORT — legs {LEG_PCT:.0%}, holding {HOLDING_DAYS}d (~1 año)")
print("=" * 90)

for label, mask in [
    ("FULL SAMPLE", pd.Series(True, index=returns_net.index)),
    ("hasta 2022 (incluye tramo de Validación, NO independiente)",
     pd.Series(returns_net.index.year <= 2022, index=returns_net.index)),
    ("HOLDOUT REAL — 2023 en adelante (la única prueba que cuenta)",
     pd.Series(returns_net.index.year >= 2023, index=returns_net.index)),
]:

    print()
    print(f"-- {label} --")

    for sub_label, series in [("SIN fricciones", returns_series), ("CON fricciones", returns_net)]:

        sub_returns = series[mask]
        equity = build_equity(sub_returns, INITIAL_CAPITAL)

        if equity.empty or len(equity) < 2:
            print(f"  {sub_label}: sin datos suficientes")
            continue

        metrics = compute_metrics(equity, [], INITIAL_CAPITAL)

        sharpe_str = f"{metrics['sharpe']:.2f}" if metrics["sharpe"] is not None else "N/A"
        cagr_str = f"{metrics['cagr']:.2%}" if metrics["cagr"] is not None else "N/A"

        print(
            f"  {sub_label:<16} | Return {metrics['total_return']:>7.2%} | "
            f"CAGR {cagr_str:>7} | Sharpe {sharpe_str:>5} | MaxDD {metrics['max_drawdown']:>7.2%}"
        )

print()
print("=" * 90)
print("NOTA")
print("=" * 90)
print(
    "El único bloque que importa de verdad para decidir si esto es operable\n"
    "es 'HOLDOUT REAL — 2023 en adelante, CON fricciones'."
)
