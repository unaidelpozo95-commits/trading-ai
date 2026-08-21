import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.engine import Backtester
from src.backtest.metrics import compute_metrics


# =============================================================
# LOAD DATA
# =============================================================

data = pd.read_parquet(
    "data/raw/yahoo/AAPL.parquet"
)

engine = FeatureEngine()

df = engine.build(data)

if not isinstance(df.index, pd.DatetimeIndex):
    df.index = pd.to_datetime(df.index)


# =============================================================
# SIGNAL — validada en robustness.py (región robusta)
# =============================================================

signal = (
    (df["return_1d"] >= 0.02)
    & (df["rvol_20"] >= 2.0)
    & (df["distance_high_20"] >= -0.05)
)


# =============================================================
# BACKTEST CONFIG
# =============================================================

INITIAL_CAPITAL = 100_000.0
STOP_PCT = 0.02
TARGET_PCT = 0.05
MAX_DAYS = 20
POSITION_SIZE_PCT = 1.0     # 100% del cash disponible por operación
COMMISSION_PCT = 0.0        # stub — activar más adelante
SLIPPAGE_PCT = 0.0          # stub — activar más adelante


def print_report(label, metrics):

    print()
    print("=" * 60)
    print(label)
    print("=" * 60)

    print(f"Trades:          {metrics['n_trades']}")
    print(f"Total return:    {metrics['total_return']:>7.2%}")

    if metrics["cagr"] is not None:
        print(f"CAGR:            {metrics['cagr']:>7.2%}")

    if metrics["sharpe"] is not None:
        print(f"Sharpe:          {metrics['sharpe']:>7.2f}")

    print(f"Max drawdown:    {metrics['max_drawdown']:>7.2%}")

    if metrics["win_rate"] is not None:
        print(f"Win rate:        {metrics['win_rate']:>7.1%}")

    if metrics["profit_factor"] is not None:
        print(f"Profit factor:   {metrics['profit_factor']:>7.2f}")

    print(f"Exit reasons:    {metrics['exit_reasons']}")


# =============================================================
# RUN — FULL SAMPLE
# =============================================================

backtester = Backtester(
    initial_capital=INITIAL_CAPITAL,
    stop_pct=STOP_PCT,
    target_pct=TARGET_PCT,
    max_days=MAX_DAYS,
    position_size_pct=POSITION_SIZE_PCT,
    commission_pct=COMMISSION_PCT,
    slippage_pct=SLIPPAGE_PCT,
    symbol="AAPL",
)

result = backtester.run(df, signal)

metrics = compute_metrics(
    result.equity_curve,
    result.trades,
    INITIAL_CAPITAL,
)

print_report("BACKTEST — FULL SAMPLE", metrics)


# =============================================================
# RUN — DEVELOPMENT / OUT-OF-SAMPLE
#
# NOTA: cada tramo se backtestea de forma independiente (capital
# reinicia a INITIAL_CAPITAL en cada uno), igual que robustness.py
# trata dev/oos como conjuntos separados. No es una única curva de
# equity continua — es una simplificación válida para comparar el
# comportamiento de la señal en ambos períodos.
# =============================================================

for label, mask in [
    ("DEVELOPMENT — hasta 2022", df.index.year <= 2022),
    ("OUT-OF-SAMPLE — 2023 en adelante", df.index.year >= 2023),
]:

    sub_df = df[mask]
    sub_signal = signal[mask]

    bt = Backtester(
        initial_capital=INITIAL_CAPITAL,
        stop_pct=STOP_PCT,
        target_pct=TARGET_PCT,
        max_days=MAX_DAYS,
        position_size_pct=POSITION_SIZE_PCT,
        commission_pct=COMMISSION_PCT,
        slippage_pct=SLIPPAGE_PCT,
        symbol="AAPL",
    )

    sub_result = bt.run(sub_df, sub_signal)

    sub_metrics = compute_metrics(
        sub_result.equity_curve,
        sub_result.trades,
        INITIAL_CAPITAL,
    )

    print_report(label, sub_metrics)


# =============================================================
# SAVE TRADE LOG (full sample)
# =============================================================

trade_log = pd.DataFrame([
    {
        "entry_date": t.entry_date,
        "exit_date": t.exit_date,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "shares": t.shares,
        "return_pct": t.return_pct,
        "pnl": t.pnl,
        "exit_reason": t.exit_reason,
    }
    for t in result.trades
])

trade_log.to_csv("data/backtest_trades.csv", index=False)

print()
print("Trade log guardado en: data/backtest_trades.csv")
