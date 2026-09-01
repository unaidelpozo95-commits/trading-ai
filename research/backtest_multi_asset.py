import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.multi_asset import MultiAssetBacktester
from src.backtest.metrics import compute_metrics


# =============================================================
# UNIVERSE
# =============================================================

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


# =============================================================
# CONFIG — mismo combo de referencia validado en single-asset
# =============================================================

INITIAL_CAPITAL = 100_000.0
STOP_PCT = 0.02
TARGET_PCT = 0.05
MAX_DAYS = 20
COMMISSION_PCT = 0.0
SLIPPAGE_PCT = 0.0


# =============================================================
# LOAD + FEATURES + SIGNAL PER TICKER
# =============================================================

def load_ticker(ticker: str) -> pd.DataFrame:

    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")

    engine = FeatureEngine()
    df = engine.build(data)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    return df


def build_signal(df: pd.DataFrame) -> pd.Series:

    return (
        (df["return_1d"] >= 0.02)
        & (df["rvol_20"] >= 2.0)
        & (df["distance_high_20"] >= -0.05)
    )


print()
print("Cargando universo:", TICKERS)

data = {}
signals = {}

for ticker in TICKERS:
    df = load_ticker(ticker)
    sig = build_signal(df)

    data[ticker] = df
    signals[ticker] = sig

    print(f"  {ticker}: {len(df)} filas | {int(sig.sum())} señales brutas")


# =============================================================
# RUN + REPORT
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

    metrics = compute_metrics(
        result.equity_curve,
        result.trades,
        INITIAL_CAPITAL,
    )

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
            {
                "symbol": t.symbol,
                "pnl": t.pnl,
                "return_pct": t.return_pct,
            }
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


full_result, full_metrics = run_and_report(
    "FULL SAMPLE — MULTI-ASSET",
    data,
    signals,
)


def filter_by_year(data, signals, condition):

    sub_data = {}
    sub_signals = {}

    for ticker in data:
        mask = condition(data[ticker].index)
        sub_data[ticker] = data[ticker][mask]
        sub_signals[ticker] = signals[ticker][mask]

    return sub_data, sub_signals


dev_data, dev_signals = filter_by_year(
    data, signals, lambda idx: idx.year <= 2022
)

oos_data, oos_signals = filter_by_year(
    data, signals, lambda idx: idx.year >= 2023
)

run_and_report("DEVELOPMENT — hasta 2022", dev_data, dev_signals)
run_and_report("OUT-OF-SAMPLE — 2023 en adelante", oos_data, oos_signals)


# =============================================================
# SAVE TRADE LOG (full sample)
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

trade_log.to_csv("data/backtest_multi_asset_trades.csv", index=False)

print()
print("Trade log guardado en: data/backtest_multi_asset_trades.csv")
