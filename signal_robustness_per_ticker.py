"""
Diagnóstico por activo — misma lógica que robustness.py (barrido de
move/rvol/distance con forward returns, alpha vs baseline, split
Dev/OOS y región robusta), pero corrida de forma independiente para
cada ticker del universo.

Objetivo: saber si el patrón que encontraste en AAPL es una
regularidad que se sostiene por sí sola en cada activo, o si solo
"sobrevivió" en la cartera multi-activo porque AAPL y NVDA tiraban
del resultado global.
"""

import pandas as pd

from src.features.engine import FeatureEngine


# =============================================================
# UNIVERSE
# =============================================================

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


# =============================================================
# PARAMETERS TO SWEEP — mismos rangos que robustness.py original
# =============================================================

move_thresholds = [0.015, 0.020, 0.025, 0.030]
rvol_thresholds = [1.5, 2.0, 2.5, 3.0]
distance_thresholds = [0.01, 0.03, 0.05, 0.075, 0.10]

FORWARD_DAYS = [1, 3, 5, 10, 20]

# El combo original, ajustado sobre AAPL, como referencia en cada ticker.
ORIGINAL_MOVE = 0.02
ORIGINAL_RVOL = 2.0
ORIGINAL_DISTANCE = 0.05


# =============================================================
# LOAD + FEATURES + FORWARD RETURNS
# =============================================================

def load_ticker(ticker: str) -> pd.DataFrame:

    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")

    engine = FeatureEngine()
    df = engine.build(data)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    for days in FORWARD_DAYS:
        entry = df["Open"].shift(-1)
        exit_price = df["Open"].shift(-(days + 1))
        df[f"forward_{days}d"] = exit_price / entry - 1

    return df


# =============================================================
# SIGNAL EVALUATION — misma función que robustness.py
# =============================================================

def evaluate_signal(df, move_threshold, rvol_threshold, distance_threshold, period_mask):

    signal = (
        (df["return_1d"] >= move_threshold)
        & (df["rvol_20"] >= rvol_threshold)
        & (df["distance_high_20"] >= -distance_threshold)
    )

    events = df[signal & period_mask]

    result = {"events": len(events)}

    for days in FORWARD_DAYS:

        returns = events[f"forward_{days}d"].dropna()

        if returns.empty:
            result[f"mean_{days}d"] = None
            result[f"alpha_{days}d"] = None
            continue

        baseline = df.loc[period_mask, f"forward_{days}d"].dropna()

        result[f"mean_{days}d"] = returns.mean()
        result[f"alpha_{days}d"] = returns.mean() - baseline.mean()

    return result


# =============================================================
# RUN PER TICKER
# =============================================================

summary_rows = []

for ticker in TICKERS:

    print()
    print("=" * 80)
    print(f"TICKER: {ticker}")
    print("=" * 80)

    df = load_ticker(ticker)

    development = df.index.year <= 2022
    test = df.index.year >= 2023

    results = []

    for move in move_thresholds:
        for rvol in rvol_thresholds:
            for distance in distance_thresholds:

                dev = evaluate_signal(df, move, rvol, distance, development)
                oos = evaluate_signal(df, move, rvol, distance, test)

                results.append({
                    "move": move,
                    "rvol": rvol,
                    "distance": distance,
                    "dev_events": dev["events"],
                    "oos_events": oos["events"],
                    "dev_alpha_20d": dev["alpha_20d"],
                    "oos_alpha_20d": oos["alpha_20d"],
                    "dev_mean_20d": dev["mean_20d"],
                    "oos_mean_20d": oos["mean_20d"],
                })

    results_df = pd.DataFrame(results)

    results_df.to_csv(
        f"data/signal_robustness_{ticker}.csv",
        index=False,
    )

    robust = results_df[
        (results_df["dev_events"] >= 10)
        & (results_df["oos_events"] >= 5)
        & (results_df["dev_alpha_20d"] > 0)
        & (results_df["oos_alpha_20d"] > 0)
    ]

    original = results_df[
        (results_df["move"] == ORIGINAL_MOVE)
        & (results_df["rvol"] == ORIGINAL_RVOL)
        & (results_df["distance"] == ORIGINAL_DISTANCE)
    ]

    print(f"Combinaciones robustas: {len(robust)} de {len(results_df)}")
    print()
    print(f"Combo original (move=2%, rvol=2.0, distance=5%) en {ticker}:")

    if not original.empty:
        row = original.iloc[0]
        dev_alpha = row["dev_alpha_20d"]
        oos_alpha = row["oos_alpha_20d"]

        print(
            f"  Dev events: {int(row['dev_events'])} | "
            f"Dev alpha 20d: {dev_alpha:>7.2%}" if dev_alpha is not None
            else f"  Dev events: {int(row['dev_events'])} | Dev alpha 20d: N/A"
        )
        print(
            f"  OOS events: {int(row['oos_events'])} | "
            f"OOS alpha 20d: {oos_alpha:>7.2%}" if oos_alpha is not None
            else f"  OOS events: {int(row['oos_events'])} | OOS alpha 20d: N/A"
        )

    summary_rows.append({
        "ticker": ticker,
        "n_robust_combos": len(robust),
        "n_combos_tested": len(results_df),
        "original_dev_events": int(original.iloc[0]["dev_events"]) if not original.empty else None,
        "original_oos_events": int(original.iloc[0]["oos_events"]) if not original.empty else None,
        "original_dev_alpha_20d": original.iloc[0]["dev_alpha_20d"] if not original.empty else None,
        "original_oos_alpha_20d": original.iloc[0]["oos_alpha_20d"] if not original.empty else None,
    })


# =============================================================
# SIDE-BY-SIDE SUMMARY
# =============================================================

summary_df = pd.DataFrame(summary_rows)

print()
print("=" * 80)
print("RESUMEN COMPARATIVO — TODOS LOS TICKERS")
print("=" * 80)

for _, row in summary_df.iterrows():

    dev_alpha = row["original_dev_alpha_20d"]
    oos_alpha = row["original_oos_alpha_20d"]

    dev_alpha_str = f"{dev_alpha:>7.2%}" if dev_alpha is not None else "   N/A"
    oos_alpha_str = f"{oos_alpha:>7.2%}" if oos_alpha is not None else "   N/A"

    print(
        f"{row['ticker']:<6} | "
        f"Robustas {int(row['n_robust_combos']):>3}/{int(row['n_combos_tested']):<3} | "
        f"Combo original -> Dev N {row['original_dev_events']!s:>3} alpha {dev_alpha_str} | "
        f"OOS N {row['original_oos_events']!s:>3} alpha {oos_alpha_str}"
    )

summary_df.to_csv("data/signal_robustness_summary.csv", index=False)

print()
print("Detalle completo por ticker guardado en:")
print("  data/signal_robustness_{TICKER}.csv")
print("Resumen guardado en:")
print("  data/signal_robustness_summary.csv")
