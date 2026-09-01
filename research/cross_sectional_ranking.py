"""
Ranking cruzado (cross-sectional).

En vez de preguntar "¿este ticker supera un umbral fijo hoy?", pregunta
"de todo el universo, ¿cuáles destacan MÁS hoy respecto a los demás?".

Para cada día:
  1. Se calcula el percentil de cada ticker en 3 dimensiones (las mismas
     3 features de la señal original, ahora relativas): momentum de 1
     día, volumen relativo (RVOL), y cercanía al máximo de 20 sesiones.
  2. Se promedian los 3 percentiles en un "score compuesto".
  3. Se seleccionan los tickers en el top-X% del score ese día.

El "alpha" ya no se mide contra el histórico propio de cada ticker,
sino contra la MEDIA DEL UNIVERSO ese mismo día — así se cancela
automáticamente "todo el mercado subió esa semana" y se aísla si
destacar en el ranking relativo predice o no un retorno superior.

Esto agrupa TODOS los ticker-días en una sola muestra estadística,
en vez de depender de encontrar suficientes eventos por ticker por
separado — es la respuesta directa al problema de tamaño de muestra
que arrastrábamos desde el principio.
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

FORWARD_DAYS = [1, 3, 5, 10, 20]

TOP_PCT_OPTIONS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


# =============================================================
# LOAD + FEATURES + FORWARD RETURNS (por ticker)
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


print()
print("Cargando universo:", TICKERS)

ticker_data = {ticker: load_ticker(ticker) for ticker in TICKERS}

for ticker, df in ticker_data.items():
    print(f"  {ticker}: {len(df)} filas")


# =============================================================
# CALENDARIO COMÚN + PANELES [fecha x ticker]
# =============================================================

common_dates = None
for df in ticker_data.values():
    idx = set(df.index)
    common_dates = idx if common_dates is None else common_dates & idx

common_dates = sorted(common_dates)

print(f"\nFechas comunes a los {len(TICKERS)} tickers: {len(common_dates)}")


def build_panel(field: str) -> pd.DataFrame:
    return pd.DataFrame(
        {ticker: ticker_data[ticker].loc[common_dates, field] for ticker in TICKERS},
        index=common_dates,
    )


return_1d_panel = build_panel("return_1d")
rvol_20_panel = build_panel("rvol_20")
distance_high_20_panel = build_panel("distance_high_20")

forward_panels = {days: build_panel(f"forward_{days}d") for days in FORWARD_DAYS}


# =============================================================
# RANKING CRUZADO (percentiles por fila/fecha)
# =============================================================

return_rank = return_1d_panel.rank(axis=1, pct=True)
rvol_rank = rvol_20_panel.rank(axis=1, pct=True)
distance_rank = distance_high_20_panel.rank(axis=1, pct=True)  # más alto = más cerca del máximo

composite_score = (return_rank + rvol_rank + distance_rank) / 3


# =============================================================
# PERIODS
# =============================================================

dev_dates = [d for d in common_dates if d.year <= 2022]
oos_dates = [d for d in common_dates if d.year >= 2023]


# =============================================================
# EVALUATION
# =============================================================

def evaluate_topk(top_pct, dates_subset, forward_days, from_bottom=False):

    fwd_panel = forward_panels[forward_days]

    excess_list = []

    for date in dates_subset:

        if date not in composite_score.index:
            continue

        row = composite_score.loc[date].dropna()

        if row.empty:
            continue

        if from_bottom:
            threshold = row.quantile(top_pct)
            selected = row[row <= threshold].index.tolist()
        else:
            threshold = row.quantile(1 - top_pct)
            selected = row[row >= threshold].index.tolist()

        if not selected:
            continue

        fwd_row = fwd_panel.loc[date]
        universe_mean = fwd_row.dropna().mean()

        if pd.isna(universe_mean):
            continue

        for ticker in selected:
            value = fwd_row.get(ticker)
            if pd.notna(value):
                excess_list.append(value - universe_mean)

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


# =============================================================
# SWEEP top_pct (a 20 días, la ventana de referencia)
# =============================================================

print()
print("=" * 90)
print("RANKING CRUZADO — sensibilidad al % seleccionado (forward 20d)")
print("=" * 90)
print(f"{'TopPct':>7} | {'DevN':>7} {'DevAlpha':>9} {'DevT':>6} | {'OOSN':>7} {'OOSAlpha':>9} {'OOST':>6}")
print("-" * 90)

for top_pct in TOP_PCT_OPTIONS:

    dev = evaluate_topk(top_pct, dev_dates, 20)
    oos = evaluate_topk(top_pct, oos_dates, 20)

    dev_alpha_str = f"{dev['alpha']:>8.2%}" if dev["alpha"] is not None else "     N/A"
    dev_t_str = f"{dev['tstat']:>5.2f}" if dev["tstat"] is not None else "  N/A"
    oos_alpha_str = f"{oos['alpha']:>8.2%}" if oos["alpha"] is not None else "     N/A"
    oos_t_str = f"{oos['tstat']:>5.2f}" if oos["tstat"] is not None else "  N/A"

    print(
        f"{top_pct:>6.0%} | {dev['n']:>7} {dev_alpha_str} {dev_t_str} | "
        f"{oos['n']:>7} {oos_alpha_str} {oos_t_str}"
    )


# =============================================================
# CURVA POR HORIZONTE (1,3,5,10,20 días) para un par de top_pct
# =============================================================

print()
print("=" * 90)
print("CURVA POR HORIZONTE — ¿el alpha crece, se estabiliza o revierte con el tiempo?")
print("=" * 90)

for top_pct in [0.10, 0.20]:

    print()
    print(f"-- top_pct = {top_pct:.0%} --")
    print(f"{'Horizonte':>10} | {'DevAlpha':>9} {'DevT':>6} | {'OOSAlpha':>9} {'OOST':>6}")

    for days in FORWARD_DAYS:

        dev = evaluate_topk(top_pct, dev_dates, days)
        oos = evaluate_topk(top_pct, oos_dates, days)

        dev_alpha_str = f"{dev['alpha']:>8.2%}" if dev["alpha"] is not None else "     N/A"
        dev_t_str = f"{dev['tstat']:>5.2f}" if dev["tstat"] is not None else "  N/A"
        oos_alpha_str = f"{oos['alpha']:>8.2%}" if oos["alpha"] is not None else "     N/A"
        oos_t_str = f"{oos['tstat']:>5.2f}" if oos["tstat"] is not None else "  N/A"

        print(
            f"{days:>9}d | {dev_alpha_str} {dev_t_str} | {oos_alpha_str} {oos_t_str}"
        )


print()
print("=" * 90)
print("HIPÓTESIS ESPEJO — seleccionar el FONDO del ranking (rezagados), no el top")
print("=" * 90)
print(f"{'BotPct':>7} | {'DevN':>7} {'DevAlpha':>9} {'DevT':>6} | {'OOSN':>7} {'OOSAlpha':>9} {'OOST':>6}")
print("-" * 90)

for bottom_pct in TOP_PCT_OPTIONS:

    dev = evaluate_topk(bottom_pct, dev_dates, 20, from_bottom=True)
    oos = evaluate_topk(bottom_pct, oos_dates, 20, from_bottom=True)

    dev_alpha_str = f"{dev['alpha']:>8.2%}" if dev["alpha"] is not None else "     N/A"
    dev_t_str = f"{dev['tstat']:>5.2f}" if dev["tstat"] is not None else "  N/A"
    oos_alpha_str = f"{oos['alpha']:>8.2%}" if oos["alpha"] is not None else "     N/A"
    oos_t_str = f"{oos['tstat']:>5.2f}" if oos["tstat"] is not None else "  N/A"

    print(
        f"{bottom_pct:>6.0%} | {dev['n']:>7} {dev_alpha_str} {dev_t_str} | "
        f"{oos['n']:>7} {oos_alpha_str} {oos_t_str}"
    )


print()
print("=" * 90)
print("LECTURA")
print("=" * 90)
print(
    "Busca: alpha positivo Y con t-stat >= ~2 en AMBOS períodos, para varios\n"
    "valores de top_pct (no solo uno) — eso indica que el ranking relativo\n"
    "captura algo real, no un valor aislado que funcionó por casualidad.\n"
    "La 'N' aquí ya no es un puñado de eventos por ticker: es cada selección\n"
    "diaria en 11 activos a lo largo de más de una década — muchísima más\n"
    "potencia estadística que cualquiera de los análisis por ticker."
)