"""
Barrido de HOLDING_DAYS (rebalanceo continuo/solapado).

Corrección importante respecto a "probar frecuencias de rebalanceo":
con cohortes solapadas, el turnover total por unidad de tiempo es
prácticamente el mismo sea cual sea la frecuencia de formación de
cohortes, MIENTRAS el holding period se mantenga igual — todo el
libro rota cada HOLDING_DAYS días de una forma u otra. Lo que sí
cambia el coste (drag = 2/HOLDING_DAYS * coste) es la duración del
holding period en sí: mantener más tiempo diluye el coste de
entrada/salida entre más sesiones.

Este script barre HOLDING_DAYS buscando el punto donde el ahorro en
coste todavía compensa la posible pérdida de "frescura" de la señal
al mantener más tiempo.
"""

import numpy as np
import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.metrics import compute_metrics


TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

LEG_PCT = 0.10

INITIAL_CAPITAL = 100_000.0

COMMISSION_PCT = 0.0005
SLIPPAGE_PCT = 0.0005
ANNUAL_BORROW_RATE = 0.01

HOLDING_DAYS_LIST = [5, 10, 15, 20, 30, 40, 60]


# =============================================================
# LOAD + FEATURES (una vez)
# =============================================================

def load_ticker(ticker: str) -> pd.DataFrame:

    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")

    engine = FeatureEngine()
    df = engine.build(data)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    return df


print()
print("Cargando universo:", TICKERS)

ticker_data = {ticker: load_ticker(ticker) for ticker in TICKERS}

common_dates = None
for df in ticker_data.values():
    idx = set(df.index)
    common_dates = idx if common_dates is None else common_dates & idx

common_dates = sorted(common_dates)

print(f"Fechas comunes: {len(common_dates)}")


def build_panel(field: str) -> pd.DataFrame:
    return pd.DataFrame(
        {ticker: ticker_data[ticker].loc[common_dates, field] for ticker in TICKERS},
        index=common_dates,
    )


return_1d_panel = build_panel("return_1d")
rvol_20_panel = build_panel("rvol_20")
distance_high_20_panel = build_panel("distance_high_20")

return_rank = return_1d_panel.rank(axis=1, pct=True)
rvol_rank = rvol_20_panel.rank(axis=1, pct=True)
distance_rank = distance_high_20_panel.rank(axis=1, pct=True)

composite_score = (return_rank + rvol_rank + distance_rank) / 3

n = len(common_dates)
return_matrix = return_1d_panel[TICKERS].values
composite_matrix = composite_score[TICKERS].values


# =============================================================
# CESTAS LARGAS/CORTAS POR DÍA (no depende de HOLDING_DAYS, una vez)
# =============================================================

print("Precomputando cestas largas/cortas por día...")

long_baskets = []
short_baskets = []

for i in range(n):

    row = composite_matrix[i]
    valid = ~np.isnan(row)

    if valid.sum() == 0:
        long_baskets.append(np.array([], dtype=int))
        short_baskets.append(np.array([], dtype=int))
        continue

    idxs = np.where(valid)[0]
    vals = row[idxs]

    long_thr = np.quantile(vals, LEG_PCT)
    short_thr = np.quantile(vals, 1 - LEG_PCT)

    long_baskets.append(idxs[vals <= long_thr])
    short_baskets.append(idxs[vals >= short_thr])


# =============================================================
# SIMULACIÓN PARA UN HOLDING_DAYS DADO
# =============================================================

def simulate(holding_days):

    portfolio_returns = np.full(n, np.nan)

    for x in range(1, n):

        start_d = max(0, x - holding_days)

        contributions = []

        for d in range(start_d, x):

            long_idx = long_baskets[d]
            short_idx = short_baskets[d]

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

    daily_trading_drag = 2 * (1 / holding_days) * (COMMISSION_PCT + SLIPPAGE_PCT)
    daily_borrow_drag = 0.5 * (ANNUAL_BORROW_RATE / 252)
    daily_total_drag = daily_trading_drag + daily_borrow_drag

    returns_net = returns_series - daily_total_drag
    returns_net[returns_series.isna()] = np.nan

    return returns_series, returns_net, daily_total_drag


def metrics_for(returns_sub):
    clean = returns_sub.dropna()
    if clean.empty or len(clean) < 2:
        return None
    equity = INITIAL_CAPITAL * (1 + clean).cumprod()
    return compute_metrics(equity, [], INITIAL_CAPITAL)


# =============================================================
# BARRIDO
# =============================================================

print()
print("=" * 100)
print("BARRIDO DE HOLDING_DAYS (rebalanceo continuo, legs 10%, CON fricciones)")
print("=" * 100)
print(f"{'Holding':>8} | {'Drag/día':>9} | {'Dev Sharpe':>11} {'Dev MaxDD':>10} | {'OOS Sharpe':>11} {'OOS MaxDD':>10}")
print("-" * 100)

results = []

for holding_days in HOLDING_DAYS_LIST:

    returns_gross, returns_net, drag = simulate(holding_days)

    dev_mask = pd.Series(returns_net.index.year <= 2022, index=returns_net.index)
    oos_mask = pd.Series(returns_net.index.year >= 2023, index=returns_net.index)

    dev_metrics = metrics_for(returns_net[dev_mask])
    oos_metrics = metrics_for(returns_net[oos_mask])

    dev_sharpe = dev_metrics["sharpe"] if dev_metrics and dev_metrics["sharpe"] is not None else None
    oos_sharpe = oos_metrics["sharpe"] if oos_metrics and oos_metrics["sharpe"] is not None else None
    dev_dd = dev_metrics["max_drawdown"] if dev_metrics else None
    oos_dd = oos_metrics["max_drawdown"] if oos_metrics else None

    dev_sharpe_str = f"{dev_sharpe:>11.2f}" if dev_sharpe is not None else "        N/A"
    oos_sharpe_str = f"{oos_sharpe:>11.2f}" if oos_sharpe is not None else "        N/A"
    dev_dd_str = f"{dev_dd:>10.2%}" if dev_dd is not None else "       N/A"
    oos_dd_str = f"{oos_dd:>10.2%}" if oos_dd is not None else "       N/A"

    print(
        f"{holding_days:>7}d | {drag:>8.4%} | {dev_sharpe_str} {dev_dd_str} | {oos_sharpe_str} {oos_dd_str}"
    )

    results.append({
        "holding_days": holding_days,
        "daily_drag": drag,
        "dev_sharpe": dev_sharpe,
        "oos_sharpe": oos_sharpe,
        "dev_max_dd": dev_dd,
        "oos_max_dd": oos_dd,
        "both_positive": (dev_sharpe is not None and oos_sharpe is not None
                           and dev_sharpe > 0 and oos_sharpe > 0),
    })


results_df = pd.DataFrame(results)
results_df.to_csv("data/long_short_holding_sweep.csv", index=False)

both_positive = results_df[results_df["both_positive"]]

print()
print(f"Holding periods con Sharpe NETO positivo en AMBOS períodos: "
      f"{len(both_positive)} de {len(results_df)}")

if not both_positive.empty:
    print()
    print(both_positive[["holding_days", "dev_sharpe", "oos_sharpe"]].to_string(index=False))

print()
print("Resultados completos guardados en: data/long_short_holding_sweep.csv")
