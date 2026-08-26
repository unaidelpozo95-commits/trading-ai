"""
Long-short con rebalanceo CONTINUO/SOLAPADO.

La versión anterior (backtest_long_short.py) rebalanceaba cada 20
sesiones — formaba una cesta larga/corta y la mantenía fija hasta el
siguiente punto de rebalanceo. Eso da solo ~145 puntos de entrada en
11 años, muy por debajo de las miles de observaciones diarias
solapadas que usó el análisis de ranking original (cross_sectional_
ranking.py) para encontrar la señal.

Aquí, en cambio, se forma una cohorte NUEVA cada día (larga en el
bottom LEG_PCT del ranking, corta en el top LEG_PCT), y esa cohorte
se mantiene activa durante HOLDING_DAYS sesiones. La cartera total,
cada día, es el promedio de TODAS las cohortes activas ese día
(normalmente ~HOLDING_DAYS cohortes solapadas a la vez). Esto es la
forma estándar de simular un factor long-short con rebalanceo diario
(similar a cómo se construyen los factores académicos tipo
Fama-French con carteras solapadas).
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

LEG_PCT = 0.10        # % de tickers en cada pata — zona de efecto fuerte confirmada
HOLDING_DAYS = 20     # sesiones que se mantiene cada cohorte

INITIAL_CAPITAL = 100_000.0

# =============================================================
# FRICCIONES — antes no modeladas. Con cohorte nueva cada día,
# el turnover es alto (a diferencia de la señal de AAPL, que
# operaba ~20 veces al año), así que las fricciones importan mucho.
#
# Supuestos conservadores mas no exagerados para 40 megacaps muy
# líquidas (fácil pedir prestado, spreads estrechos):
# =============================================================

COMMISSION_PCT = 0.0005   # 5 puntos básicos por operación
SLIPPAGE_PCT = 0.0005     # 5 puntos básicos por operación
ANNUAL_BORROW_RATE = 0.01  # 1% anual por mantener posiciones cortas
                           # (razonable para megacaps líquidas; nombres
                           # más difíciles de pedir prestado cuestan más)


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


# =============================================================
# COHORTES DIARIAS SOLAPADAS
# =============================================================

n = len(common_dates)

return_matrix = return_1d_panel[TICKERS].values
composite_matrix = composite_score[TICKERS].values

print("\nPrecomputando cestas largas/cortas por día...")

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


print("Simulando cartera con cohortes solapadas...")

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


# =============================================================
# APLICAR FRICCIONES
#
# Cada día entra una cohorte nueva (1/HOLDING_DAYS del "peso" de la
# cartera; dentro de esa cohorte, 50% va a la pata larga y 50% a la
# corta) y sale una vieja igual -> turnover diario = 2 * (1/HOLDING_DAYS)
# del capital total pasa por comisión+slippage (entrada + salida).
# El coste de préstamo se aplica solo sobre la pata corta (50% del capital).
# =============================================================

daily_trading_drag = 2 * (1 / HOLDING_DAYS) * (COMMISSION_PCT + SLIPPAGE_PCT)
daily_borrow_drag = 0.5 * (ANNUAL_BORROW_RATE / 252)
daily_total_drag = daily_trading_drag + daily_borrow_drag

print(f"\nFricción diaria aplicada: {daily_total_drag:.4%} "
      f"(trading: {daily_trading_drag:.4%} + borrow: {daily_borrow_drag:.4%})")

returns_series_net = returns_series - daily_total_drag
# el drag no aplica en días sin cohortes activas (NaN se mantiene NaN)
returns_series_net[returns_series.isna()] = np.nan


# =============================================================
# REPORT — FULL / DEV / OOS
# =============================================================

def build_equity(returns_sub: pd.Series, initial_capital: float) -> pd.Series:
    clean = returns_sub.dropna()
    if clean.empty:
        return pd.Series(dtype=float)
    equity = initial_capital * (1 + clean).cumprod()
    return equity


print()
print("=" * 80)
print(f"LONG-SHORT — REBALANCEO CONTINUO (legs {LEG_PCT:.0%}, holding {HOLDING_DAYS}d)")
print("=" * 80)

for label, mask in [
    ("FULL SAMPLE", pd.Series(True, index=returns_series.index)),
    ("DEVELOPMENT — hasta 2022", pd.Series(returns_series.index.year <= 2022, index=returns_series.index)),
    ("OUT-OF-SAMPLE — 2023 en adelante", pd.Series(returns_series.index.year >= 2023, index=returns_series.index)),
]:

    print()
    print(f"-- {label} --")

    for sub_label, series in [("SIN fricciones", returns_series), ("CON fricciones", returns_series_net)]:

        sub_returns = series[mask]
        equity = build_equity(sub_returns, INITIAL_CAPITAL)

        if equity.empty or len(equity) < 2:
            print(f"  {sub_label}: sin datos suficientes")
            continue

        metrics = compute_metrics(equity, [], INITIAL_CAPITAL)

        sharpe_str = f"{metrics['sharpe']:.2f}" if metrics["sharpe"] is not None else "N/A"

        print(
            f"  {sub_label:<16} | Return {metrics['total_return']:>7.2%} | "
            f"Sharpe {sharpe_str:>5} | MaxDD {metrics['max_drawdown']:>7.2%}"
        )


print()
print("=" * 80)
print("LECTURA")
print("=" * 80)
print(
    "Igual que antes: neutral a mercado, así que la barra es simplemente\n"
    "Sharpe positivo Y consistente en Dev y OOS — no hace falta batir a\n"
    "ningún buy&hold. Esta versión usa muchísimas más cohortes solapadas\n"
    "que la de rebalanceo cada 20 días, así que debería reflejar mejor la\n"
    "señal estadística que vimos en cross_sectional_ranking.py."
)