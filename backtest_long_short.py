"""
Long-short neutral a mercado.

En vez de comprar solo los rezagados (long-only, expuesto al beta
completo de la cesta), aquí se compran los rezagados Y se vende en
corto a los líderes del ranking, con el mismo importe en dólares en
cada lado (dollar-neutral). Si el mercado sube o baja en bloque, el
efecto se cancela en gran parte entre las dos patas — lo que queda
es, aproximadamente, el efecto de reversión relativa en sí mismo.

Metodología: rebalanceo periódico (no basado en eventos individuales
con stop/target como el motor principal). Cada `REBALANCE_DAYS`
sesiones se recalcula la cesta larga (bottom LEG_PCT del ranking) y
la cesta corta (top LEG_PCT), equiponderadas dentro de cada pata, y
se mantienen hasta el siguiente rebalanceo. Esto es la forma estándar
de simular una estrategia factorial long-short (similar a cómo se
construyen los factores académicos tipo Fama-French).
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

LEG_PCT = 0.10       # % de tickers en cada pata (largo/corto). Con 40 tickers,
                     # esto da ~4 por pata — diversificación razonable Y en la
                     # zona (5-10%) donde el análisis de ranking mostró el
                     # efecto más fuerte, algo que no era posible con 11 tickers.
REBALANCE_DAYS = 20  # sesiones entre rebalanceos

INITIAL_CAPITAL = 100_000.0


# =============================================================
# LOAD + FEATURES
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


# =============================================================
# SIMULACIÓN LONG-SHORT CON REBALANCEO PERIÓDICO
# =============================================================

def simulate_long_short(dates_subset):

    rebalance_dates = dates_subset[::REBALANCE_DAYS]

    daily_returns = {}

    for i in range(len(rebalance_dates) - 1):

        reb_date = rebalance_dates[i]
        next_reb_date = rebalance_dates[i + 1]

        if reb_date not in composite_score.index:
            continue

        row = composite_score.loc[reb_date].dropna()

        if row.empty:
            continue

        long_threshold = row.quantile(LEG_PCT)
        short_threshold = row.quantile(1 - LEG_PCT)

        long_tickers = row[row <= long_threshold].index.tolist()
        short_tickers = row[row >= short_threshold].index.tolist()

        if not long_tickers or not short_tickers:
            continue

        window_dates = [d for d in dates_subset if reb_date < d <= next_reb_date]

        for date in window_dates:

            long_rets = return_1d_panel.loc[date, long_tickers].dropna()
            short_rets = return_1d_panel.loc[date, short_tickers].dropna()

            if long_rets.empty or short_rets.empty:
                continue

            # Dollar-neutral: 50% del capital en largos, 50% en cortos.
            portfolio_return = 0.5 * long_rets.mean() - 0.5 * short_rets.mean()

            daily_returns[date] = portfolio_return

    if not daily_returns:
        return None

    returns_series = pd.Series(daily_returns).sort_index()
    equity = INITIAL_CAPITAL * (1 + returns_series).cumprod()

    return equity


# =============================================================
# RUN — FULL / DEV / OOS
# =============================================================

dev_dates = [d for d in common_dates if d.year <= 2022]
oos_dates = [d for d in common_dates if d.year >= 2023]

print()
print("=" * 80)
print(f"LONG-SHORT NEUTRAL A MERCADO — legs {LEG_PCT:.0%}, rebalanceo cada {REBALANCE_DAYS} sesiones")
print("=" * 80)

for label, dates_subset in [
    ("FULL SAMPLE", common_dates),
    ("DEVELOPMENT — hasta 2022", dev_dates),
    ("OUT-OF-SAMPLE — 2023 en adelante", oos_dates),
]:

    equity = simulate_long_short(dates_subset)

    if equity is None or len(equity) < 2:
        print(f"\n{label}: sin datos suficientes")
        continue

    metrics = compute_metrics(equity, [], INITIAL_CAPITAL)

    print()
    print(f"-- {label} --")
    print(f"Retorno total:   {metrics['total_return']:>8.2%}")
    if metrics["cagr"] is not None:
        print(f"CAGR:            {metrics['cagr']:>8.2%}")
    if metrics["sharpe"] is not None:
        print(f"Sharpe:          {metrics['sharpe']:>8.2f}")
    print(f"Max drawdown:    {metrics['max_drawdown']:>8.2%}")
    print(f"Sesiones:        {len(equity)}")


print()
print("=" * 80)
print("LECTURA")
print("=" * 80)
print(
    "Al ser neutral a mercado, la barra de comparación NO es el buy&hold de\n"
    "la cesta (que aquí no aplica) sino simplemente: ¿Sharpe claramente\n"
    "positivo y consistente en Dev Y OOS? Un Sharpe positivo aquí significa\n"
    "que el efecto de reversión relativa aporta algo por sí mismo, separado\n"
    "de si el mercado en general subió o bajó ese período."
)