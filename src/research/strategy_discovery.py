"""
Descubrimiento automático de estrategia por ticker.

Encapsula las 4 hipótesis de señal que hemos ido validando a lo
largo de la investigación:

  original_breakout  -> la señal de AAPL (move + rvol + distance a máximo)
  trend_breakout      -> la anterior, pero solo en tendencia alcista (SMA200)
  sustained_momentum  -> movimiento sostenido de 5 días + volumen, en tendencia
  pullback_uptrend    -> retroceso dentro de una tendencia alcista fuerte

Para un ticker nuevo, prueba las 4, aplica los mismos filtros que
hemos usado en toda la investigación (robustez estadística +
significancia económica >=1% alpha en ambos períodos) y se queda con
la mejor. Si ninguna pasa, el ticker se marca explícitamente como
"sin señal validada" — NUNCA se fuerza una estrategia sin respaldo.

Este descubrimiento es costoso (cientos de combinaciones) y solo
hace falta correrlo UNA VEZ por ticker nuevo — ver
discover_strategy_for_ticker.py y src/research/strategy_store.py
para el flujo de cacheo.
"""

import pandas as pd

from src.features.engine import FeatureEngine
from src.data.loader import load_and_validate


FORWARD_DAYS = [1, 3, 5, 10, 20]

# =============================================================
# CORTES DE FECHA PARA EL DESCUBRIMIENTO
#
# IMPORTANTE: antes usábamos Dev<=2022 / OOS>=2023 tanto para
# seleccionar como para "validar" — eso hacía que el propio OOS
# formara parte del criterio de selección (selection bias), dejando
# el backtest de cartera posterior sin ningún tramo genuinamente
# limpio para probar de verdad.
#
# Ahora el descubrimiento usa SOLO datos hasta 2022 (Dev hasta 2020,
# "OOS interno" 2021-2022, ambos usados para seleccionar). El tramo
# 2023 en adelante queda completamente fuera del proceso de
# selección — es el holdout real, y coincide con el corte OOS que ya
# usamos en el resto de la investigación (AAPL, reversión, etc.).
# =============================================================

DISCOVERY_DEV_END_YEAR = 2020
DISCOVERY_OOS_START_YEAR = 2021
DISCOVERY_OOS_END_YEAR = 2022

# Umbrales de validación — los mismos que hemos usado en toda la investigación.
MIN_DEV_EVENTS = 10
MIN_OOS_EVENTS = 5
MIN_ALPHA = 0.01  # 1% — significancia económica, no solo estadística
MIN_TSTAT = 3.5   # Umbral elevado respecto al usado con 14 tickers (2.0).
                  # Con 500 tickers x ~1000 combos = ~500.000 pruebas en
                  # total (frente a las ~5.000 de antes), el problema de
                  # comparaciones múltiples se dispara ~100x. t>=3.5 es un
                  # ajuste conservador aproximado (no un cálculo exacto de
                  # Bonferroni) para compensar — con esta escala de
                  # búsqueda, es preferible perder algún hallazgo real por
                  # ser demasiado estrictos que inundarse de falsos
                  # positivos. Trata cualquier "VALIDADA" como candidato a
                  # revisar, nunca como luz verde automática.


# =============================================================
# DATA
# =============================================================

def load_ticker_for_discovery(ticker: str) -> pd.DataFrame:

    data = load_and_validate(ticker)

    engine = FeatureEngine()
    df = engine.build(data)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    for days in FORWARD_DAYS:
        entry = df["Open"].shift(-1)
        exit_price = df["Open"].shift(-(days + 1))
        df[f"forward_{days}d"] = exit_price / entry - 1

    return df


def _evaluate(df, signal, period_mask):

    events = df[signal & period_mask]

    result = {"events": len(events)}

    for days in FORWARD_DAYS:
        returns = events[f"forward_{days}d"].dropna()

        if returns.empty:
            result[f"alpha_{days}d"] = None
            result[f"tstat_{days}d"] = None
            continue

        baseline = df.loc[period_mask, f"forward_{days}d"].dropna()

        result[f"alpha_{days}d"] = returns.mean() - baseline.mean()

        # Welch's t-test manual: distingue una diferencia de medias real
        # de una que podría deberse solo al azar, dado el tamaño de
        # muestra y la varianza de cada grupo.
        n_events = len(returns)
        n_baseline = len(baseline)

        if n_events >= 2 and n_baseline >= 2:
            var_events = returns.var(ddof=1)
            var_baseline = baseline.var(ddof=1)
            se = ((var_events / n_events) + (var_baseline / n_baseline)) ** 0.5
            result[f"tstat_{days}d"] = (result[f"alpha_{days}d"] / se) if se > 0 else None
        else:
            result[f"tstat_{days}d"] = None

    return result


# =============================================================
# RECIPES
# =============================================================

def _recipe_original_breakout(df, move, rvol, distance):
    return (
        (df["return_1d"] >= move)
        & (df["rvol_20"] >= rvol)
        & (df["distance_high_20"] >= -distance)
    )


def _recipe_trend_breakout(df, move, rvol, distance):
    return (
        (df["return_1d"] >= move)
        & (df["rvol_20"] >= rvol)
        & (df["distance_high_20"] >= -distance)
        & (df["distance_sma_200"] > 0)
    )


def _recipe_sustained_momentum(df, move5, rvol):
    return (
        (df["return_5d"] >= move5)
        & (df["rvol_20"] >= rvol)
        & (df["distance_sma_200"] > 0)
    )


def _recipe_pullback_uptrend(df, trend_strength, pullback, rvol):
    return (
        (df["distance_sma_200"] >= trend_strength)
        & (df["distance_sma_20"] <= -pullback)
        & (df["rvol_20"] >= rvol)
    )


RECIPES = {

    "original_breakout": {
        "func": _recipe_original_breakout,
        "grid": [
            {"move": m, "rvol": r, "distance": d}
            for m in [0.010, 0.015, 0.020, 0.025, 0.030]
            for r in [1.2, 1.5, 2.0, 2.5, 3.0]
            for d in [0.05, 0.10, 0.15, 0.20]
        ],
    },

    "trend_breakout": {
        "func": _recipe_trend_breakout,
        "grid": [
            {"move": m, "rvol": r, "distance": d}
            for m in [0.010, 0.015, 0.020, 0.025, 0.030]
            for r in [1.2, 1.5, 2.0, 2.5, 3.0]
            for d in [0.05, 0.10, 0.15, 0.20]
        ],
    },

    "sustained_momentum": {
        "func": _recipe_sustained_momentum,
        "grid": [
            {"move5": m5, "rvol": r}
            for m5 in [0.03, 0.05, 0.07, 0.10]
            for r in [1.2, 1.5, 2.0, 2.5]
        ],
    },

    "pullback_uptrend": {
        "func": _recipe_pullback_uptrend,
        "grid": [
            {"trend_strength": t, "pullback": p, "rvol": r}
            for t in [0.05, 0.10, 0.15]
            for p in [0.02, 0.03, 0.05]
            for r in [1.0, 1.2, 1.5]
        ],
    },
}


# =============================================================
# DISCOVERY
# =============================================================

def discover_best_strategy(ticker: str, verbose: bool = True) -> dict:
    """
    Prueba las 4 recetas sobre el ticker y devuelve la mejor
    combinación validada, o un resultado marcado como no validado
    si ninguna combinación pasa los filtros.

    Devuelve un dict con, como mínimo:
        ticker, validated (bool)
    y si validated=True, además:
        recipe, params, dev_events, oos_events,
        dev_alpha_20d, oos_alpha_20d, score
    """

    df = load_ticker_for_discovery(ticker)

    development = df.index.year <= DISCOVERY_DEV_END_YEAR
    test = (df.index.year >= DISCOVERY_OOS_START_YEAR) & (df.index.year <= DISCOVERY_OOS_END_YEAR)

    candidates = []

    for recipe_name, recipe in RECIPES.items():

        for params in recipe["grid"]:

            signal = recipe["func"](df, **params)

            dev = _evaluate(df, signal, development)
            oos = _evaluate(df, signal, test)

            dev_alpha = dev["alpha_20d"]
            oos_alpha = oos["alpha_20d"]
            dev_tstat = dev["tstat_20d"]
            oos_tstat = oos["tstat_20d"]

            if dev_alpha is None or oos_alpha is None:
                continue
            if dev_tstat is None or oos_tstat is None:
                continue

            is_robust = (
                dev["events"] >= MIN_DEV_EVENTS
                and oos["events"] >= MIN_OOS_EVENTS
                and dev_alpha > 0
                and oos_alpha > 0
            )

            is_meaningful = (
                is_robust
                and dev_alpha >= MIN_ALPHA
                and oos_alpha >= MIN_ALPHA
                and dev_tstat >= MIN_TSTAT
                and oos_tstat >= MIN_TSTAT
            )

            if not is_meaningful:
                continue

            # Score: favorece alpha alto Y consistente en ambos períodos,
            # con un pequeño bonus por muestra más grande (más confianza).
            score = min(dev_alpha, oos_alpha) * (1 + 0.01 * min(dev["events"], oos["events"]))

            candidates.append({
                "recipe": recipe_name,
                "params": params,
                "dev_events": dev["events"],
                "oos_events": oos["events"],
                "dev_alpha_20d": dev_alpha,
                "oos_alpha_20d": oos_alpha,
                "dev_tstat_20d": dev_tstat,
                "oos_tstat_20d": oos_tstat,
                "score": score,
            })

    if not candidates:
        if verbose:
            print(f"{ticker}: SIN SEÑAL VALIDADA (ninguna de las {sum(len(r['grid']) for r in RECIPES.values())} combinaciones pasó los filtros)")
        return {"ticker": ticker, "validated": False}

    best = max(candidates, key=lambda c: c["score"])

    result = {
        "ticker": ticker,
        "validated": True,
        "recipe": best["recipe"],
        "params": best["params"],
        "dev_events": best["dev_events"],
        "oos_events": best["oos_events"],
        "dev_alpha_20d": best["dev_alpha_20d"],
        "oos_alpha_20d": best["oos_alpha_20d"],
        "dev_tstat_20d": best["dev_tstat_20d"],
        "oos_tstat_20d": best["oos_tstat_20d"],
        "n_candidates_found": len(candidates),
    }

    if verbose:
        print(
            f"{ticker}: VALIDADA -> receta '{best['recipe']}' con {best['params']} | "
            f"Dev(<={DISCOVERY_DEV_END_YEAR}) N {best['dev_events']} alpha {best['dev_alpha_20d']:.2%} (t={best['dev_tstat_20d']:.2f}) | "
            f"OOS-interno({DISCOVERY_OOS_START_YEAR}-{DISCOVERY_OOS_END_YEAR}) N {best['oos_events']} alpha {best['oos_alpha_20d']:.2%} (t={best['oos_tstat_20d']:.2f}) | "
            f"({len(candidates)} combinaciones candidatas en total)"
        )

    return result
