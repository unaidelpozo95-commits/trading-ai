import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.multi_asset import MultiAssetBacktester
from src.backtest.metrics import compute_metrics


# =============================================================
# UNIVERSE
# =============================================================

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]


# =============================================================
# CONFIG
# =============================================================

BOTTOM_PCT = 0.10  # punto de partida: buen t-stat OOS (3.92) en el análisis de ranking

INITIAL_CAPITAL = 100_000.0
STOP_PCT = 0.02
TARGET_PCT = 0.05
MAX_DAYS = 20
COMMISSION_PCT = 0.0
SLIPPAGE_PCT = 0.0


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

for ticker, df in ticker_data.items():
    print(f"  {ticker}: {len(df)} filas")


# =============================================================
# CALENDARIO COMÚN + RANKING CRUZADO (igual que cross_sectional_ranking.py)
# =============================================================

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
# CONSTRUIR SEÑAL POR TICKER — bottom_pct del ranking ese día
# =============================================================

threshold_per_day = composite_score.quantile(BOTTOM_PCT, axis=1)
signal_panel = composite_score.le(threshold_per_day, axis=0)

signals = {}
for ticker in TICKERS:
    signals[ticker] = signal_panel[ticker].reindex(ticker_data[ticker].index, fill_value=False)

avg_signals_per_day = signal_panel.sum(axis=1).mean()
print(f"\nSeñal: bottom {BOTTOM_PCT:.0%} del ranking -> ~{avg_signals_per_day:.1f} tickers activados por día en promedio")


# =============================================================
# RUN + REPORT (reutiliza el motor multi-activo ya validado)
# =============================================================

def run_and_report(label, data_subset, signals_subset):

    bt = MultiAssetBacktester(
        initial_capital=INITIAL_CAPITAL,
        stop_pct=STOP_PCT,
        target_pct=TARGET_PCT,
        max_days=MAX_DAYS,
        commission_pct=COMMISSION_PCT,
        slippage_pct=SLIPPAGE_PCT,
    )

    result = bt.run(data_subset, signals_subset)

    metrics = compute_metrics(result.equity_curve, result.trades, INITIAL_CAPITAL)

    print()
    print("=" * 70)
    print(label)
    print("=" * 70)

    print(f"Trades:          {metrics['n_trades']}")
    print(f"Total return:    {metrics['total_return']:>7.2%}")

    if metrics["cagr"] is not None:
        print(f"CAGR:            {metrics['cagr']:>7.2%}")

    if metrics["sharpe"] is not None:
        print(f"Sharpe:          {metrics['sharpe']:>7.2f}")

    print(f"Max drawdown:    {metrics['max_drawdown']:>7.2%}")

    if metrics["win_rate"] is not None:
        print(f"Win rate:        {metrics['win_rate']:>7.1%}")

    print(f"Exit reasons:    {metrics['exit_reasons']}")

    if result.trades:

        trade_df = pd.DataFrame([
            {"symbol": t.symbol, "pnl": t.pnl, "return_pct": t.return_pct}
            for t in result.trades
        ])

        by_symbol = trade_df.groupby("symbol").agg(
            trades=("pnl", "count"),
            total_pnl=("pnl", "sum"),
            avg_return=("return_pct", "mean"),
        )

        print()
        print("Por símbolo:")
        print(by_symbol.to_string())

    return result, metrics


def filter_by_year(data, signals, condition):
    sub_data, sub_signals = {}, {}
    for ticker in data:
        mask = condition(data[ticker].index)
        sub_data[ticker] = data[ticker][mask]
        sub_signals[ticker] = signals[ticker][mask]
    return sub_data, sub_signals


full_result, full_metrics = run_and_report(
    "FULL SAMPLE — REVERSIÓN CROSS-SECTIONAL (bottom 10%)",
    ticker_data,
    signals,
)

dev_data, dev_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year <= 2022)
oos_data, oos_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year >= 2023)

run_and_report("DEVELOPMENT — hasta 2022", dev_data, dev_signals)
run_and_report("OUT-OF-SAMPLE — 2023 en adelante", oos_data, oos_signals)


# =============================================================
# COMPARACIÓN: buy & hold de una cesta equiponderada de los 11 tickers
# =============================================================

def basket_buy_and_hold_equity(data, dates, initial_capital):

    per_ticker_capital = initial_capital / len(TICKERS)

    entry_prices = {t: data[t].loc[dates[0], "Open"] for t in TICKERS}
    shares = {t: per_ticker_capital / entry_prices[t] for t in TICKERS}

    equity = {}
    for date in dates:
        value = sum(shares[t] * data[t].loc[date, "Close"] for t in TICKERS if date in data[t].index)
        equity[date] = value

    return pd.Series(equity).sort_index()


for label, dates_subset in [
    ("FULL SAMPLE", common_dates),
    ("DEVELOPMENT", [d for d in common_dates if d.year <= 2022]),
    ("OUT-OF-SAMPLE", [d for d in common_dates if d.year >= 2023]),
]:

    bh_equity = basket_buy_and_hold_equity(ticker_data, dates_subset, INITIAL_CAPITAL)
    bh_metrics = compute_metrics(bh_equity, [], INITIAL_CAPITAL)

    print()
    print(f"Buy&Hold cesta equiponderada (11 tickers) — {label}: "
          f"Return {bh_metrics['total_return']:.2%} | "
          f"Sharpe {bh_metrics['sharpe']:.2f} | "
          f"MaxDD {bh_metrics['max_drawdown']:.2%}")


# =============================================================
# SAVE TRADE LOG
# =============================================================

trade_log = pd.DataFrame([
    {
        "symbol": t.symbol,
        "entry_date": t.entry_date,
        "exit_date": t.exit_date,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "shares": t.shares,
        "return_pct": t.return_pct,
        "pnl": t.pnl,
        "exit_reason": t.exit_reason,
    }
    for t in full_result.trades
])

trade_log.to_csv("data/backtest_cross_sectional_trades.csv", index=False)

print()
print("Trade log guardado en: data/backtest_cross_sectional_trades.csv")