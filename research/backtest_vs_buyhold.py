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
# SIGNAL — misma señal validada en robustness.py
# =============================================================

signal = (
    (df["return_1d"] >= 0.02)
    & (df["rvol_20"] >= 2.0)
    & (df["distance_high_20"] >= -0.05)
)


# =============================================================
# PERIODS
# =============================================================

periods = {
    "FULL SAMPLE": df.index == df.index,  # todo el rango
    "DEVELOPMENT — hasta 2022": df.index.year <= 2022,
    "OUT-OF-SAMPLE — 2023 en adelante": df.index.year >= 2023,
}


# =============================================================
# STRATEGY CONFIG — combo de referencia ya validado
# =============================================================

INITIAL_CAPITAL = 100_000.0
STOP_PCT = 0.02
TARGET_PCT = 0.05
MAX_DAYS = 20
POSITION_SIZE_PCT = 1.0
COMMISSION_PCT = 0.0
SLIPPAGE_PCT = 0.0


# =============================================================
# BUY & HOLD
# =============================================================

def buy_and_hold_equity(sub_df: pd.DataFrame, initial_capital: float) -> pd.Series:
    """Invierte todo el capital al Open del primer día del período y
    lo mantiene sin tocarlo hasta el Close del último día."""

    entry_price = sub_df["Open"].iloc[0]
    equity = initial_capital * (sub_df["Close"] / entry_price)
    equity.index = sub_df.index

    return equity


# =============================================================
# RUN COMPARISON
# =============================================================

def print_line(label, m):
    print(
        f"{label:<12} | "
        f"Return {m['total_return']:>8.2%} | "
        f"CAGR {m['cagr'] if m['cagr'] is not None else float('nan'):>7.2%} | "
        f"Sharpe {m['sharpe'] if m['sharpe'] is not None else float('nan'):>5.2f} | "
        f"MaxDD {m['max_drawdown']:>8.2%}"
    )


print()
print("=" * 90)
print("ESTRATEGIA vs BUY & HOLD (AAPL)")
print(f"Estrategia: stop={STOP_PCT:.0%}, target={TARGET_PCT:.0%}, max_days={MAX_DAYS}")
print("=" * 90)

comparison_rows = []

for period_label, mask in periods.items():

    sub_df = df[mask]
    sub_signal = signal[mask]

    # --- Estrategia ---
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

    strategy_result = bt.run(sub_df, sub_signal)

    strategy_metrics = compute_metrics(
        strategy_result.equity_curve,
        strategy_result.trades,
        INITIAL_CAPITAL,
    )

    # --- Buy & hold ---
    bh_equity = buy_and_hold_equity(sub_df, INITIAL_CAPITAL)

    bh_metrics = compute_metrics(
        bh_equity,
        [],
        INITIAL_CAPITAL,
    )

    print()
    print("-" * 90)
    print(period_label)
    print("-" * 90)

    print_line("Estrategia", strategy_metrics)
    print_line("Buy&Hold", bh_metrics)

    print(f"{'':12} | Trades estrategia: {strategy_metrics['n_trades']}")
    print(
        f"{'':12} | Tiempo en mercado (aprox): estrategia mantiene posición solo "
        f"durante los trades; buy & hold está invertido el 100% del período."
    )

    comparison_rows.append({
        "period": period_label,
        "strategy_return": strategy_metrics["total_return"],
        "strategy_cagr": strategy_metrics["cagr"],
        "strategy_sharpe": strategy_metrics["sharpe"],
        "strategy_max_dd": strategy_metrics["max_drawdown"],
        "strategy_trades": strategy_metrics["n_trades"],
        "buyhold_return": bh_metrics["total_return"],
        "buyhold_cagr": bh_metrics["cagr"],
        "buyhold_sharpe": bh_metrics["sharpe"],
        "buyhold_max_dd": bh_metrics["max_drawdown"],
    })


comparison_df = pd.DataFrame(comparison_rows)
comparison_df.to_csv("data/strategy_vs_buyhold.csv", index=False)

print()
print("=" * 90)
print("LECTURA")
print("=" * 90)
print(
    "La estrategia solo está expuesta al mercado durante sus propios trades\n"
    "(unos pocos días al año), mientras que buy & hold está expuesto siempre.\n"
    "Si el Sharpe de la estrategia es claramente mayor que el de buy & hold,\n"
    "es una señal de que el retorno no es solo 'estar en AAPL', sino que la\n"
    "señal aporta algo. Si son parecidos, es más probable que el resultado\n"
    "de la estrategia sea sobre todo beta de mercado."
)

print()
print("Resultados completos guardados en:")
print("data/strategy_vs_buyhold.csv")
