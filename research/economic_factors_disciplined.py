"""
Factores académicos con disciplina metodológica real.

Diferencias clave respecto a TODO lo anterior en esta investigación:

1. NO hay barrido de parámetros. Se usan valores fijos tomados de la
   literatura académica (no "lo que mejor funcionó" — eso es
   precisamente el origen del sesgo que nos explotó con el S&P 500).

2. Split en TRES tramos, no dos:
     TRAIN      2015-2019  (no se usa para decidir nada aquí, solo
                            para que las features de largo plazo,
                            como el máximo de 252 sesiones, tengan
                            histórico suficiente desde el principio
                            del período de validación)
     VALIDACIÓN 2020-2022  (se mira UNA vez, para confirmar que el
                            signo va en la dirección que predice la
                            literatura, antes de tocar TEST)
     TEST       2023-2026  (se mira UNA SOLA VEZ, al final, y se
                            acepta el resultado sea cual sea — nunca
                            se vuelve a tocar ni se usa para elegir
                            nada)

Dos factores, cada uno con UNA especificación fija:

  - Momentum 12-1 (Jegadeesh & Titman, 1993): retorno de los últimos
    12 meses, saltando el último mes (para evitar contaminar con el
    efecto de reversión a corto plazo que ya validamos). Top 30%
    cross-sectional.

  - Cercanía al máximo de 52 semanas (George & Hwang, 2004): estar
    cerca del máximo de las últimas 252 sesiones predice continuación.
    Top 30% cross-sectional (más cerca del máximo).
"""

import numpy as np
import pandas as pd

from src.features.engine import FeatureEngine


TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

TOP_PCT = 0.30
FORWARD_DAYS = 20


def load_ticker(ticker: str) -> pd.DataFrame:

    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")

    engine = FeatureEngine()
    df = engine.build(data)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df["momentum_12_1"] = df["Close"].shift(21) / df["Close"].shift(252) - 1

    high_252 = df["High"].rolling(252).max().shift(1)
    df["distance_high_252"] = df["Close"] / high_252 - 1

    entry = df["Open"].shift(-1)
    exit_price = df["Open"].shift(-(FORWARD_DAYS + 1))
    df[f"forward_{FORWARD_DAYS}d"] = exit_price / entry - 1

    return df


print()
print("Cargando universo:", TICKERS)

ticker_data = {t: load_ticker(t) for t in TICKERS}

common_dates = None
for df in ticker_data.values():
    idx = set(df.index)
    common_dates = idx if common_dates is None else common_dates & idx
common_dates = sorted(common_dates)

print(f"Fechas comunes: {len(common_dates)}")


def build_panel(field):
    return pd.DataFrame(
        {t: ticker_data[t].loc[common_dates, field] for t in TICKERS},
        index=common_dates,
    )


momentum_panel = build_panel("momentum_12_1")
distance_252_panel = build_panel("distance_high_252")
forward_panel = build_panel(f"forward_{FORWARD_DAYS}d")

momentum_rank = momentum_panel.rank(axis=1, pct=True)
distance_252_rank = distance_252_panel.rank(axis=1, pct=True)


def evaluate(rank_panel, dates_subset, top_pct):

    excess_list = []

    for date in dates_subset:

        if date not in rank_panel.index:
            continue

        row = rank_panel.loc[date].dropna()
        if row.empty:
            continue

        threshold = row.quantile(1 - top_pct)
        selected = row[row >= threshold].index.tolist()

        if not selected:
            continue

        fwd_row = forward_panel.loc[date]
        universe_mean = fwd_row.dropna().mean()

        if pd.isna(universe_mean):
            continue

        for t in selected:
            v = fwd_row.get(t)
            if pd.notna(v):
                excess_list.append(v - universe_mean)

    if not excess_list:
        return {"n": 0, "alpha": None, "tstat": None}

    arr = np.array(excess_list)
    n = len(arr)
    mean = arr.mean()

    if n > 1 and arr.std(ddof=1) > 0:
        se = arr.std(ddof=1) / np.sqrt(n)
        tstat = mean / se
    else:
        tstat = None

    return {"n": n, "alpha": mean, "tstat": tstat}


validation_dates = [d for d in common_dates if 2020 <= d.year <= 2022]
test_dates = [d for d in common_dates if d.year >= 2023]


def report(label, result):
    alpha_str = f"{result['alpha']:>7.2%}" if result["alpha"] is not None else "    N/A"
    tstat_str = f"{result['tstat']:>5.2f}" if result["tstat"] is not None else " N/A"
    print(f"{label:<12} | N {result['n']:>5} | alpha {alpha_str} | t-stat {tstat_str}")


print()
print("=" * 80)
print("PASO 1 — VALIDACIÓN (2020-2022), especificación fija de la literatura")
print("=" * 80)
print("Solo se comprueba el SIGNO. Si no va en la dirección predicha, se para aquí.")
print()

print("-- Momentum 12-1 (top 30%) --")
mom_validation = evaluate(momentum_rank, validation_dates, TOP_PCT)
report("Validación", mom_validation)

print()
print("-- Cercanía a máximo 52 semanas (top 30%) --")
high52_validation = evaluate(distance_252_rank, validation_dates, TOP_PCT)
report("Validación", high52_validation)

print()
print("=" * 80)
print("DECISIÓN")
print("=" * 80)

mom_pass = mom_validation["alpha"] is not None and mom_validation["alpha"] > 0
high52_pass = high52_validation["alpha"] is not None and high52_validation["alpha"] > 0

print(f"Momentum 12-1: {'signo correcto (positivo), se mira TEST' if mom_pass else 'signo incorrecto o sin datos, NO se mira TEST'}")
print(f"Cercanía 52s:  {'signo correcto (positivo), se mira TEST' if high52_pass else 'signo incorrecto o sin datos, NO se mira TEST'}")

print()
print("=" * 80)
print("PASO 2 — TEST (2023-2026), se mira UNA SOLA VEZ, se acepta el resultado")
print("=" * 80)

if mom_pass:
    print()
    print("-- Momentum 12-1 (top 30%) --")
    mom_test = evaluate(momentum_rank, test_dates, TOP_PCT)
    report("TEST", mom_test)
else:
    print()
    print("-- Momentum 12-1: DESCARTADO en validación, no se mira TEST --")

if high52_pass:
    print()
    print("-- Cercanía a máximo 52 semanas (top 30%) --")
    high52_test = evaluate(distance_252_rank, test_dates, TOP_PCT)
    report("TEST", high52_test)
else:
    print()
    print("-- Cercanía 52 semanas: DESCARTADO en validación, no se mira TEST --")

print()
print("=" * 80)
print("NOTA")
print("=" * 80)
print(
    "Este resultado de TEST es definitivo dentro de esta metodología: no se\n"
    "vuelve a tocar, no se prueban más parámetros para 'mejorarlo'. Si el\n"
    "resultado no es bueno, la conclusión honesta es que el factor no aplica\n"
    "a este universo/período — no se sigue buscando hasta que salga bien,\n"
    "porque eso es exactamente el error que ya cometimos con el S&P 500."
)
