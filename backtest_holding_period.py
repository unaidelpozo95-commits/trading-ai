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
#
# Target al 50% -> en la práctica nunca se toca, así que aísla el
# efecto de max_days sin que el take profit interfiera. El stop se
# deja en 2% (referencia ya probada como razonable en el barrido
# anterior).
# =============================================================

INITIAL_CAPITAL = 100_000.0
STOP_PCT = 0.02
TARGET_PCT = 0.50
POSITION_SIZE_PCT = 1.0
COMMISSION_PCT = 0.0
SLIPPAGE_PCT = 0.0


# =============================================================
# PARAMETER TO SWEEP
# =============================================================

max_days_list = [5, 10, 15, 20, 30, 40, 60, 90]


# =============================================================
# FUNCTION
# =============================================================

def run_backtest(sub_df, sub_signal, max_days):

    bt = Backtester(
        initial_capital=INITIAL_CAPITAL,
        stop_pct=STOP_PCT,
        target_pct=TARGET_PCT,
        max_days=max_days,
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
print("=" * 90)
print("BACKTEST ROBUSTNESS — HOLDING PERIOD (max_days) SENSITIVITY")
print(f"Target fijado al {TARGET_PCT:.0%} (efectivamente desactivado) para aislar el efecto de max_days")
print("=" * 90)

results = []

for max_days in max_days_list:

    dev = run_backtest(
        df[development_mask],
        signal[development_mask],
        max_days,
    )

    oos = run_backtest(
        df[test_mask],
        signal[test_mask],
        max_days,
    )

    results.append({

        "max_days": max_days,

        "dev_trades": dev["n_trades"],
        "oos_trades": oos["n_trades"],

        "dev_return": dev["total_return"],
        "oos_return": oos["total_return"],

        "dev_cagr": dev["cagr"],
        "oos_cagr": oos["cagr"],

        "dev_sharpe": dev["sharpe"],
        "oos_sharpe": oos["sharpe"],

        "dev_max_dd": dev["max_drawdown"],
        "oos_max_dd": oos["max_drawdown"],

        "dev_win_rate": dev["win_rate"],
        "oos_win_rate": oos["win_rate"],

        "dev_sl": dev["exit_reasons"].get("SL", 0),
        "dev_time": dev["exit_reasons"].get("TIME", 0),

        "oos_sl": oos["exit_reasons"].get("SL", 0),
        "oos_time": oos["exit_reasons"].get("TIME", 0),

    })


results_df = pd.DataFrame(results)


# =============================================================
# SAVE RESULTS
# =============================================================

results_df.to_csv(
    "data/backtest_holding_period_sensitivity.csv",
    index=False,
)


# =============================================================
# REPORT
# =============================================================

def print_row(row):
    print(
        f"max_days {row['max_days']:>3} | "
        f"Dev N {int(row['dev_trades']):>3} Return {row['dev_return']:>7.2%} "
        f"CAGR {row['dev_cagr'] if row['dev_cagr'] is not None else float('nan'):>6.2%} "
        f"Sharpe {row['dev_sharpe'] if row['dev_sharpe'] is not None else float('nan'):>5.2f} "
        f"MaxDD {row['dev_max_dd']:>7.2%} "
        f"(SL {int(row['dev_sl']):>2} TIME {int(row['dev_time']):>2}) | "
        f"OOS N {int(row['oos_trades']):>2} Return {row['oos_return']:>7.2%} "
        f"CAGR {row['oos_cagr'] if row['oos_cagr'] is not None else float('nan'):>6.2%} "
        f"Sharpe {row['oos_sharpe'] if row['oos_sharpe'] is not None else float('nan'):>5.2f} "
        f"MaxDD {row['oos_max_dd']:>7.2%} "
        f"(SL {int(row['oos_sl']):>2} TIME {int(row['oos_time']):>2})"
    )


print()
print("=" * 90)
print("RESULTADOS POR max_days (ordenado de menor a mayor holding period)")
print("=" * 90)

for _, row in results_df.sort_values("max_days").iterrows():
    print_row(row)


print()
print("=" * 90)
print("LECTURA")
print("=" * 90)
print(
    "Si el retorno sube y luego se estabiliza o cae al aumentar max_days,\n"
    "hay una estructura temporal real que vale la pena fijar.\n"
    "Si sigue subiendo sin freno hasta max_days=90, es más probable que\n"
    "estemos viendo el efecto genérico de 'mercado alcista de fondo' que\n"
    "una ventaja específica de la señal — conviene revisar el CAGR (no solo\n"
    "el retorno total) porque el retorno total crece con el tiempo de forma\n"
    "mecánica al mantener posiciones más tiempo."
)

print()
print("Resultados completos guardados en:")
print("data/backtest_holding_period_sensitivity.csv")
