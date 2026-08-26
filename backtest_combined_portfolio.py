"""
Cartera combinada: AAPL (momentum/breakout) + Reversión cross-sectional.

Dos estrategias ya validadas por separado, con lógicas de mercado
opuestas (momentum vs reversión) — la hipótesis es que su
correlación sea baja o negativa, y que combinarlas mejore el Sharpe
conjunto por diversificación, aunque ninguna por separado bata
claramente al mercado.

Split 50/50 de capital entre ambas. Se reporta:
  - Sharpe de cada estrategia por separado (en el mismo rango de
    fechas, para comparación justa)
  - Correlación entre sus retornos diarios — el dato clave
  - Sharpe/CAGR/MaxDD de la cartera combinada
"""

import numpy as np
import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.engine import Backtester
from src.backtest.metrics import compute_metrics


print()
print("Cargando AAPL (momentum)...")

aapl_data = pd.read_parquet("data/raw/yahoo/AAPL.parquet")
engine = FeatureEngine()
aapl_df = engine.build(aapl_data)

if not isinstance(aapl_df.index, pd.DatetimeIndex):
    aapl_df.index = pd.to_datetime(aapl_df.index)

aapl_signal = (
    (aapl_df["return_1d"] >= 0.02)
    & (aapl_df["rvol_20"] >= 2.0)
    & (aapl_df["distance_high_20"] >= -0.05)
)

aapl_bt = Backtester(
    initial_capital=100_000.0,
    stop_pct=0.02,
    target_pct=0.05,
    max_days=20,
)

aapl_result = aapl_bt.run(aapl_df, aapl_signal)
aapl_returns = aapl_result.equity_curve.pct_change().dropna()

print(f"AAPL: {len(aapl_returns)} días con retorno diario calculado")


print()
print("Cargando universo de 40 tickers (reversión)...")

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

LEG_PCT = 0.10
HOLDING_DAYS = 40

COMMISSION_PCT = 0.0005
SLIPPAGE_PCT = 0.0005
ANNUAL_BORROW_RATE = 0.01


def load_ticker(ticker):
    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")
    df = FeatureEngine().build(data)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df


ticker_data = {t: load_ticker(t) for t in TICKERS}

common_dates = None
for df in ticker_data.values():
    idx = set(df.index)
    common_dates = idx if common_dates is None else common_dates & idx
common_dates = sorted(common_dates)


def build_panel(field):
    return pd.DataFrame(
        {t: ticker_data[t].loc[common_dates, field] for t in TICKERS},
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

print("Precomputando cestas largas/cortas por día...")

long_baskets, short_baskets = [], []

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

print("Simulando reversión con cohortes solapadas...")

reversion_returns_arr = np.full(n, np.nan)

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
        reversion_returns_arr[x] = np.mean(contributions)

reversion_returns_gross = pd.Series(reversion_returns_arr, index=common_dates)

daily_trading_drag = 2 * (1 / HOLDING_DAYS) * (COMMISSION_PCT + SLIPPAGE_PCT)
daily_borrow_drag = 0.5 * (ANNUAL_BORROW_RATE / 252)
daily_total_drag = daily_trading_drag + daily_borrow_drag

reversion_returns = reversion_returns_gross - daily_total_drag
reversion_returns[reversion_returns_gross.isna()] = np.nan
reversion_returns = reversion_returns.dropna()

print(f"Reversión: {len(reversion_returns)} días con retorno diario calculado")


aligned = pd.DataFrame({
    "aapl": aapl_returns,
    "reversion": reversion_returns,
}).dropna()

print(f"\nDías con ambas series alineadas: {len(aligned)}")

correlation = aligned["aapl"].corr(aligned["reversion"])

print(f"\nCorrelación entre AAPL (momentum) y Reversión: {correlation:.3f}")

aligned["combined"] = 0.5 * aligned["aapl"] + 0.5 * aligned["reversion"]


def report_period(label, sub_df):

    print()
    print(f"-- {label} --")

    for col, name in [("aapl", "AAPL solo"), ("reversion", "Reversión sola"), ("combined", "COMBINADA 50/50")]:

        returns = sub_df[col]
        if returns.empty:
            print(f"  {name}: sin datos")
            continue

        equity = 100_000.0 * (1 + returns).cumprod()
        metrics = compute_metrics(equity, [], 100_000.0)

        sharpe_str = f"{metrics['sharpe']:.2f}" if metrics["sharpe"] is not None else "N/A"
        cagr_str = f"{metrics['cagr']:.2%}" if metrics["cagr"] is not None else "N/A"

        print(
            f"  {name:<16} | Return {metrics['total_return']:>7.2%} | "
            f"CAGR {cagr_str:>7} | Sharpe {sharpe_str:>5} | MaxDD {metrics['max_drawdown']:>7.2%}"
        )


print()
print("=" * 90)
print("RESULTADOS")
print("=" * 90)

report_period("FULL SAMPLE", aligned)
report_period("hasta 2022", aligned[aligned.index.year <= 2022])
report_period("2023 en adelante", aligned[aligned.index.year >= 2023])

print()
print("=" * 90)
print("BARRIDO DE PESOS — ¿es 50/50 el mejor reparto?")
print("=" * 90)
print(f"{'% Reversión':>12} | {'Full Sharpe':>11} | {'Dev Sharpe':>10} | {'OOS Sharpe':>10} | {'OOS MaxDD':>10}")
print("-" * 90)

dev_mask = aligned.index.year <= 2022
oos_mask = aligned.index.year >= 2023

for reversion_weight in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:

    aapl_weight = 1 - reversion_weight
    combo_returns = aapl_weight * aligned["aapl"] + reversion_weight * aligned["reversion"]

    sharpes = {}
    maxdds = {}

    for label, mask in [("full", pd.Series(True, index=combo_returns.index)), ("dev", dev_mask), ("oos", oos_mask)]:
        sub = combo_returns[mask]
        if sub.empty:
            sharpes[label] = None
            continue
        equity = 100_000.0 * (1 + sub).cumprod()
        m = compute_metrics(equity, [], 100_000.0)
        sharpes[label] = m["sharpe"]
        maxdds[label] = m["max_drawdown"]

    full_s = f"{sharpes['full']:.2f}" if sharpes['full'] is not None else "N/A"
    dev_s = f"{sharpes['dev']:.2f}" if sharpes['dev'] is not None else "N/A"
    oos_s = f"{sharpes['oos']:.2f}" if sharpes['oos'] is not None else "N/A"
    oos_dd = f"{maxdds['oos']:.2%}" if maxdds.get('oos') is not None else "N/A"

    print(f"{reversion_weight:>11.0%} | {full_s:>11} | {dev_s:>10} | {oos_s:>10} | {oos_dd:>10}")

print()
print("Busca el peso donde el Sharpe combinado supera a AAPL solo (peso=0%)")
print("en LOS TRES períodos a la vez, no solo en uno.")

