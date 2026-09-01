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

development_mask = df.index.year <= 2022
test_mask = df.index.year >= 2023


# =============================================================
# CONFIG FIJA
# =============================================================

INITIAL_CAPITAL = 100_000.0
MAX_DAYS = 20
POSITION_SIZE_PCT = 1.0
COMMISSION_PCT = 0.0
SLIPPAGE_PCT = 0.0


# =============================================================
# PARAMETERS TO SWEEP
# =============================================================

stop_pcts = [0.01, 0.015, 0.02, 0.025, 0.03]
target_pcts = [0.03, 0.04, 0.05, 0.07, 0.10, 0.12, 0.15, 0.20]


# =============================================================
# FUNCTION
# =============================================================

def run_backtest(sub_df, sub_signal, stop_pct, target_pct):

    bt = Backtester(
        initial_capital=INITIAL_CAPITAL,
        stop_pct=stop_pct,
        target_pct=target_pct,
        max_days=MAX_DAYS,
        position_size_pct=POSITION_SIZE_PCT,
        commission_pct=COMMISSION_PCT,
        slippage_pct=SLIPPAGE_PCT,
        symbol="AAPL",
    )

    result = bt.run(sub_df, sub_signal)

    metrics = compute_metrics(
        result.equity_curve,
        result.trades,
        INITIAL_CAPITAL,
    )

    return metrics


# =============================================================
# SWEEP
# =============================================================

print()
print("=" * 80)
print("BACKTEST ROBUSTNESS — STOP / TARGET SENSITIVITY")
print("=" * 80)

results = []

for stop_pct in stop_pcts:

    for target_pct in target_pcts:

        dev = run_backtest(
            df[development_mask],
            signal[development_mask],
            stop_pct,
            target_pct,
        )

        oos = run_backtest(
            df[test_mask],
            signal[test_mask],
            stop_pct,
            target_pct,
        )

        results.append({

            "stop_pct": stop_pct,
            "target_pct": target_pct,

            "dev_trades": dev["n_trades"],
            "oos_trades": oos["n_trades"],

            "dev_return": dev["total_return"],
            "oos_return": oos["total_return"],

            "dev_sharpe": dev["sharpe"],
            "oos_sharpe": oos["sharpe"],

            "dev_max_dd": dev["max_drawdown"],
            "oos_max_dd": oos["max_drawdown"],

            "dev_win_rate": dev["win_rate"],
            "oos_win_rate": oos["win_rate"],

            "dev_profit_factor": dev["profit_factor"],
            "oos_profit_factor": oos["profit_factor"],

            "dev_tp": dev["exit_reasons"].get("TP", 0),
            "dev_sl": dev["exit_reasons"].get("SL", 0),
            "dev_time": dev["exit_reasons"].get("TIME", 0),

            "oos_tp": oos["exit_reasons"].get("TP", 0),
            "oos_sl": oos["exit_reasons"].get("SL", 0),
            "oos_time": oos["exit_reasons"].get("TIME", 0),

        })


results_df = pd.DataFrame(results)


# =============================================================
# SAVE RESULTS
# =============================================================

results_df.to_csv(
    "data/backtest_robustness_sensitivity.csv",
    index=False,
)


# =============================================================
# DEVELOPMENT — TOP COMBOS
# =============================================================

print()
print("=" * 80)
print("DEVELOPMENT — TOP 15 by return")
print("=" * 80)

dev_sorted = results_df.sort_values(
    "dev_return",
    ascending=False,
)

for _, row in dev_sorted.head(15).iterrows():

    print(
        f"Stop {row['stop_pct']:>5.1%} | "
        f"Target {row['target_pct']:>5.1%} | "
        f"N {int(row['dev_trades']):>3} | "
        f"Return {row['dev_return']:>7.2%} | "
        f"Sharpe {row['dev_sharpe'] if row['dev_sharpe'] is not None else float('nan'):>5.2f} | "
        f"MaxDD {row['dev_max_dd']:>7.2%} | "
        f"Win {row['dev_win_rate'] if row['dev_win_rate'] is not None else float('nan'):>5.1%} | "
        f"TP {int(row['dev_tp']):>2} SL {int(row['dev_sl']):>2} TIME {int(row['dev_time']):>2}"
    )


# =============================================================
# OUT-OF-SAMPLE — TOP COMBOS
# =============================================================

print()
print("=" * 80)
print("OUT-OF-SAMPLE — TOP 15 by return")
print("=" * 80)

oos_sorted = results_df.sort_values(
    "oos_return",
    ascending=False,
)

for _, row in oos_sorted.head(15).iterrows():

    print(
        f"Stop {row['stop_pct']:>5.1%} | "
        f"Target {row['target_pct']:>5.1%} | "
        f"N {int(row['oos_trades']):>3} | "
        f"Return {row['oos_return']:>7.2%} | "
        f"Sharpe {row['oos_sharpe'] if row['oos_sharpe'] is not None else float('nan'):>5.2f} | "
        f"MaxDD {row['oos_max_dd']:>7.2%} | "
        f"Win {row['oos_win_rate'] if row['oos_win_rate'] is not None else float('nan'):>5.1%} | "
        f"TP {int(row['oos_tp']):>2} SL {int(row['oos_sl']):>2} TIME {int(row['oos_time']):>2}"
    )


# =============================================================
# ORIGINAL COMBO — REFERENCE
# =============================================================

original = results_df[
    (results_df["stop_pct"] == 0.02)
    & (results_df["target_pct"] == 0.05)
]

print()
print("=" * 80)
print("ORIGINAL COMBO — REFERENCE (stop=2%, target=5%)")
print("=" * 80)

print(
    original[
        [
            "stop_pct",
            "target_pct",
            "dev_trades",
            "oos_trades",
            "dev_return",
            "oos_return",
            "dev_sharpe",
            "oos_sharpe",
            "dev_max_dd",
            "oos_max_dd",
        ]
    ].to_string(index=False)
)


# =============================================================
# ROBUST REGION
# =============================================================

print()
print("=" * 80)
print("ROBUST REGION")
print("=" * 80)

robust = results_df[
    (results_df["dev_trades"] >= 8)
    & (results_df["oos_trades"] >= 3)
    & (results_df["dev_return"] > 0)
    & (results_df["oos_return"] > 0)
]

print("Combinaciones de stop/target que cumplen:")
print("  Development trades >= 8")
print("  OOS trades >= 3")
print("  Return positivo en AMBOS períodos")
print()
print(f"Combinaciones robustas: {len(robust)} de {len(results_df)}")

if not robust.empty:

    print()

    robust = robust.sort_values(
        "oos_sharpe",
        ascending=False,
    )

    for _, row in robust.head(20).iterrows():

        print(
            f"Stop {row['stop_pct']:>5.1%} | "
            f"Target {row['target_pct']:>5.1%} | "
            f"Dev N {int(row['dev_trades']):>3} | "
            f"OOS N {int(row['oos_trades']):>3} | "
            f"Dev return {row['dev_return']:>7.2%} | "
            f"OOS return {row['oos_return']:>7.2%} | "
            f"OOS Sharpe {row['oos_sharpe'] if row['oos_sharpe'] is not None else float('nan'):>5.2f} | "
            f"OOS TP {int(row['oos_tp']):>2} SL {int(row['oos_sl']):>2} TIME {int(row['oos_time']):>2}"
        )


# =============================================================
# SUMMARY
# =============================================================

print()
print("=" * 80)
print("DONE")
print("=" * 80)
print()
print("Resultados completos guardados en:")
print("data/backtest_robustness_sensitivity.csv")
