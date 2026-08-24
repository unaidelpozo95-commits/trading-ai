"""
Barrido AMPLIADO por ticker.

El rango original de robustness.py / signal_robustness_per_ticker.py
(move 1.5-3%, rvol 1.5-3.0, distance 1-10%) estaba, en la práctica,
centrado en lo que funciona para AAPL. Ese mismo rango dio 0/80
combinaciones robustas para MSFT, GOOGL y AMZN — pero eso solo dice
que ESE rango no tiene un óptimo para ellos, no que no exista
ninguno. Aquí se amplía el rango en ambas direcciones (umbrales más
bajos y más altos) para ver si aparece algo fuera de la zona
"AAPL-céntrica".
"""

import pandas as pd

from src.features.engine import FeatureEngine


TICKERS = ["MSFT", "GOOGL", "AMZN", "NVDA"]  # AAPL ya está validado, se omite


# =============================================================
# RANGO AMPLIADO
# =============================================================

move_thresholds = [0.010, 0.015, 0.020, 0.025, 0.030, 0.040]
rvol_thresholds = [1.2, 1.5, 2.0, 2.5, 3.0, 4.0]
distance_thresholds = [0.01, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20]

FORWARD_DAYS = [1, 3, 5, 10, 20]


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

print()
print(f"Rango ampliado: {len(move_thresholds)} move x {len(rvol_thresholds)} rvol x "
      f"{len(distance_thresholds)} distance = "
      f"{len(move_thresholds) * len(rvol_thresholds) * len(distance_thresholds)} combos por ticker")

summary_rows = []

for ticker in TICKERS:

    print()
    print("=" * 90)
    print(f"TICKER: {ticker}")
    print("=" * 90)

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
                })

    results_df = pd.DataFrame(results)

    results_df.to_csv(
        f"data/signal_robustness_wide_{ticker}.csv",
        index=False,
    )

    robust = results_df[
        (results_df["dev_events"] >= 10)
        & (results_df["oos_events"] >= 5)
        & (results_df["dev_alpha_20d"] > 0)
        & (results_df["oos_alpha_20d"] > 0)
    ]

    print(f"Combinaciones robustas: {len(robust)} de {len(results_df)}")

    if not robust.empty:

        robust_sorted = robust.sort_values("oos_alpha_20d", ascending=False)

        print()
        print("Top 10 combinaciones robustas (por OOS alpha):")
        print(f"{'Move':>6} {'RVOL':>5} {'Dist':>6} | {'DevN':>5} {'OOSN':>5} | "
              f"{'DevAlpha':>9} {'OOSAlpha':>9}")
        print("-" * 60)

        for _, row in robust_sorted.head(10).iterrows():
            print(
                f"{row['move']:>5.1%} {row['rvol']:>5.1f} {row['distance']:>6.1%} | "
                f"{int(row['dev_events']):>5} {int(row['oos_events']):>5} | "
                f"{row['dev_alpha_20d']:>8.2%} {row['oos_alpha_20d']:>8.2%}"
            )

    else:
        print("Ninguna combinación robusta ni siquiera en el rango ampliado.")

        # Diagnóstico: mostrar el mejor candidato aunque no sea "robusto",
        # para ver qué tan lejos está de serlo.
        with_enough_events = results_df[
            (results_df["dev_events"] >= 10) & (results_df["oos_events"] >= 5)
        ]

        if not with_enough_events.empty:
            best = with_enough_events.sort_values("oos_alpha_20d", ascending=False).iloc[0]
            print()
            print("Mejor candidato con muestra suficiente (aunque no sea robusto):")
            print(
                f"  Move {best['move']:.1%} | RVOL {best['rvol']:.1f} | "
                f"Distance {best['distance']:.1%} | "
                f"Dev N {int(best['dev_events'])} alpha {best['dev_alpha_20d']:.2%} | "
                f"OOS N {int(best['oos_events'])} alpha {best['oos_alpha_20d']:.2%}"
            )

    summary_rows.append({
        "ticker": ticker,
        "n_robust_combos": len(robust),
        "n_combos_tested": len(results_df),
    })


# =============================================================
# SUMMARY
# =============================================================

summary_df = pd.DataFrame(summary_rows)

print()
print("=" * 90)
print("RESUMEN — RANGO AMPLIADO")
print("=" * 90)

for _, row in summary_df.iterrows():
    print(f"{row['ticker']:<6} | Robustas: {int(row['n_robust_combos'])} de {int(row['n_combos_tested'])}")

print()
print("Detalle completo guardado en: data/signal_robustness_wide_{TICKER}.csv")
