"""
Exploración de features/hipótesis ALTERNATIVAS por ticker.

No retunea los mismos 3 umbrales (return_1d, rvol_20, distance_high_20)
que ya sabemos que no generalizan. Prueba 3 formulaciones de señal
distintas, usando features de FeatureEngine que aún no habíamos usado:

  A) Breakout con filtro de tendencia (SMA200)
  B) Momentum sostenido de 5 días (en vez de un salto de 1 día)
  C) Retroceso dentro de una tendencia alcista fuerte ("buy the dip")

Umbral de significancia económica: además del filtro de robustez
estadística (dev_events>=10, oos_events>=5, alpha>0 en ambos), se
marca como "económicamente significativo" solo lo que supera 1% de
alpha en ambos períodos — para no confundir ruido de comparaciones
múltiples con una ventaja real, como ya vimos en el barrido anterior.
"""

import pandas as pd

from src.features.engine import FeatureEngine


TICKERS = ["MSFT", "GOOGL", "AMZN", "NVDA"]

FORWARD_DAYS = [1, 3, 5, 10, 20]

ALPHA_BAR = 0.01  # 1% — umbral de significancia económica


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


def evaluate(df, signal, period_mask):

    events = df[signal & period_mask]

    result = {"events": len(events)}

    for days in FORWARD_DAYS:
        returns = events[f"forward_{days}d"].dropna()

        if returns.empty:
            result[f"alpha_{days}d"] = None
            continue

        baseline = df.loc[period_mask, f"forward_{days}d"].dropna()
        result[f"alpha_{days}d"] = returns.mean() - baseline.mean()

    return result


# =============================================================
# RECIPES — hipótesis de señal
# =============================================================

def recipe_trend_breakout(df, move, rvol, distance):
    return (
        (df["return_1d"] >= move)
        & (df["rvol_20"] >= rvol)
        & (df["distance_high_20"] >= -distance)
        & (df["distance_sma_200"] > 0)
    )


def recipe_sustained_momentum(df, move5, rvol):
    return (
        (df["return_5d"] >= move5)
        & (df["rvol_20"] >= rvol)
        & (df["distance_sma_200"] > 0)
    )


def recipe_pullback_in_uptrend(df, trend_strength, pullback, rvol):
    return (
        (df["distance_sma_200"] >= trend_strength)
        & (df["distance_sma_20"] <= -pullback)
        & (df["rvol_20"] >= rvol)
    )


RECIPES = {

    "A_trend_breakout": {
        "func": recipe_trend_breakout,
        "description": "Breakout (subida + volumen + cerca de máximos) SOLO en tendencia alcista (Close > SMA200)",
        "grid": [
            {"move": m, "rvol": r, "distance": d}
            for m in [0.010, 0.015, 0.020, 0.025, 0.030]
            for r in [1.2, 1.5, 2.0, 2.5, 3.0]
            for d in [0.05, 0.10, 0.15, 0.20]
        ],
    },

    "B_sustained_momentum": {
        "func": recipe_sustained_momentum,
        "description": "Momentum de 5 días (no de 1 día) + volumen alto, en tendencia alcista",
        "grid": [
            {"move5": m5, "rvol": r}
            for m5 in [0.03, 0.05, 0.07, 0.10]
            for r in [1.2, 1.5, 2.0, 2.5]
        ],
    },

    "C_pullback_uptrend": {
        "func": recipe_pullback_in_uptrend,
        "description": "Retroceso respecto a SMA20 dentro de una tendencia alcista fuerte (comprar la pausa, no la subida)",
        "grid": [
            {"trend_strength": t, "pullback": p, "rvol": r}
            for t in [0.05, 0.10, 0.15]
            for p in [0.02, 0.03, 0.05]
            for r in [1.0, 1.2, 1.5]
        ],
    },
}


# =============================================================
# RUN PER TICKER x RECIPE
# =============================================================

def format_params(row, param_keys):
    return ", ".join(f"{k}={row[k]:.1%}" if row[k] < 1 else f"{k}={row[k]:.2f}" for k in param_keys)


summary_rows = []

for ticker in TICKERS:

    print()
    print("=" * 90)
    print(f"TICKER: {ticker}")
    print("=" * 90)

    df = load_ticker(ticker)

    development = df.index.year <= 2022
    test = df.index.year >= 2023

    for recipe_name, recipe in RECIPES.items():

        param_keys = list(recipe["grid"][0].keys())

        results = []

        for params in recipe["grid"]:

            signal = recipe["func"](df, **params)

            dev = evaluate(df, signal, development)
            oos = evaluate(df, signal, test)

            row = dict(params)
            row.update({
                "dev_events": dev["events"],
                "oos_events": oos["events"],
                "dev_alpha_20d": dev["alpha_20d"],
                "oos_alpha_20d": oos["alpha_20d"],
            })
            results.append(row)

        results_df = pd.DataFrame(results)

        results_df.to_csv(
            f"data/signal_alt_{recipe_name}_{ticker}.csv",
            index=False,
        )

        robust = results_df[
            (results_df["dev_events"] >= 10)
            & (results_df["oos_events"] >= 5)
            & (results_df["dev_alpha_20d"] > 0)
            & (results_df["oos_alpha_20d"] > 0)
        ]

        meaningful = robust[
            (robust["dev_alpha_20d"] >= ALPHA_BAR)
            & (robust["oos_alpha_20d"] >= ALPHA_BAR)
        ]

        print()
        print(f"  [{recipe_name}] {recipe['description']}")
        print(
            f"    Robustas: {len(robust)} de {len(results_df)} | "
            f"Económicamente significativas (alpha>=1% ambos períodos): {len(meaningful)}"
        )

        if not meaningful.empty:

            best = meaningful.sort_values("oos_alpha_20d", ascending=False).iloc[0]

            print(
                f"    Mejor combo: {format_params(best, param_keys)} | "
                f"Dev N {int(best['dev_events'])} alpha {best['dev_alpha_20d']:.2%} | "
                f"OOS N {int(best['oos_events'])} alpha {best['oos_alpha_20d']:.2%}"
            )

        summary_rows.append({
            "ticker": ticker,
            "recipe": recipe_name,
            "n_robust": len(robust),
            "n_meaningful": len(meaningful),
            "n_tested": len(results_df),
        })


# =============================================================
# SUMMARY
# =============================================================

summary_df = pd.DataFrame(summary_rows)

print()
print("=" * 90)
print("RESUMEN — TICKER x RECETA")
print("=" * 90)
print(summary_df.to_string(index=False))

summary_df.to_csv("data/signal_alt_features_summary.csv", index=False)

print()
print("Detalle completo guardado en:")
print("  data/signal_alt_{RECETA}_{TICKER}.csv")
print("Resumen guardado en:")
print("  data/signal_alt_features_summary.csv")
