"""
Reporte final de la configuración ganadora de la reversión cross-sectional:
legs 10%, holding 40 días, rebalanceo continuo, CON fricciones realistas.

Da el retorno/CAGR exacto (no solo Sharpe) para poder responder con
números reales: "¿qué rentabilidad podría tener esto?"
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
HOLDING_DAYS = 40  # configuración ganadora del barrido

INITIAL_CAPITAL = 100_000.0

COMMISSION_PCT = 0.0005
SLIPPAGE_PCT = 0.0005
ANNUAL_BORROW_RATE = 0.01


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

print(f"Simulando cartera (holding={HOLDING_DAYS}d)...")

portfolio_returns = np.full(n, np.nan)

for x in range(1, n):

    start_d = max(0, x - HOLDING_DAYS)

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

daily_trading_drag = 2 * (1 / HOLDING_DAYS) * (COMMISSION_PCT + SLIPPAGE_PCT)
daily_borrow_drag = 0.5 * (ANNUAL_BORROW_RATE / 252)
daily_total_drag = daily_trading_drag + daily_borrow_drag

returns_net = returns_series - daily_total_drag
returns_net[returns_series.isna()] = np.nan


def build_equity(returns_sub, initial_capital):
    clean = returns_sub.dropna()
    if clean.empty:
        return pd.Series(dtype=float)
    return initial_capital * (1 + clean).cumprod()


print()
print("=" * 90)
print(f"REPORTE FINAL — legs {LEG_PCT:.0%}, holding {HOLDING_DAYS}d, CON fricciones")
print("=" * 90)

for label, mask in [
    ("FULL SAMPLE (11 años)", pd.Series(True, index=returns_net.index)),
    ("DEVELOPMENT — hasta 2022", pd.Series(returns_net.index.year <= 2022, index=returns_net.index)),
    ("OUT-OF-SAMPLE — 2023 en adelante", pd.Series(returns_net.index.year >= 2023, index=returns_net.index)),
]:

    sub_returns = returns_net[mask]
    equity = build_equity(sub_returns, INITIAL_CAPITAL)

    if equity.empty or len(equity) < 2:
        print(f"\n{label}: sin datos suficientes")
        continue

    metrics = compute_metrics(equity, [], INITIAL_CAPITAL)

    n_years = len(equity) / 252

    print()
    print(f"-- {label} ({n_years:.1f} años) --")
    print(f"Retorno total:   {metrics['total_return']:>8.2%}")
    if metrics["cagr"] is not None:
        print(f"CAGR:            {metrics['cagr']:>8.2%}")
    if metrics["sharpe"] is not None:
        print(f"Sharpe:          {metrics['sharpe']:>8.2f}")
    print(f"Max drawdown:    {metrics['max_drawdown']:>8.2%}")

    if metrics["cagr"] is not None:
        example_5y = INITIAL_CAPITAL * (1 + metrics["cagr"]) ** 5
        print(f"Ejemplo: 100.000 $ a este CAGR durante 5 años -> {example_5y:,.0f} $")

print()
print("=" * 90)
print("NOTA")
print("=" * 90)
print(
    "Esta estrategia es NEUTRAL A MERCADO: no compra ni vende el mercado en\n"
    "general, así que 'batir al mercado' no es la pregunta correcta aquí -\n"
    "el objetivo es generar un retorno positivo INDEPENDIENTE de si el\n"
    "mercado sube o baja, no superarlo en términos absolutos. Es un flujo\n"
    "de retorno distinto, no un sustituto de estar invertido en bolsa."
)
