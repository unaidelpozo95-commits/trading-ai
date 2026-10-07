"""
PEG ratio = P/E ÷ crecimiento anual del beneficio por acción (en %).

Idea: un P/E de 30 es caro para una empresa que no crece, pero puede ser
razonable si el beneficio crece un 30% al año. El PEG pone las dos cosas
en la misma cifra. Orientativo: por debajo de 1 suele considerarse
barato respecto al crecimiento, entre 1 y 2 razonable, por encima de 2
caro.

CÓMO SE CALCULA EL CRECIMIENTO (pasado, no una previsión):
tasa de crecimiento anual compuesta (CAGR) del EPS diluido de los
10-K, con hasta PEG_MAX_YEARS años hacia atrás.

LIMITACIONES, TODAS EXPLÍCITAS (el PEG es un ratio ruidoso):
  - Los EPS están tal como se publicaron cada año, SIN ajustar por
    splits. Para que un split no falsee el crecimiento, la ventana se
    corta donde el número de acciones salta un factor >= SPLIT_RATIO
    entre dos años consecutivos (a un cambio así casi nunca llega una
    empresa por recompras o emisiones, sí por un split).
  - La ventana debe ser de años fiscales consecutivos (sin huecos) y
    tener como mínimo MIN_POINTS puntos; si no, N/A.
  - El EPS inicial y el final deben ser positivos; con pérdidas el CAGR
    no está definido.
  - Si el crecimiento es <= 0 NO hay PEG (N/A): un PEG con crecimiento
    negativo o nulo no significa "barato", significa que el ratio no
    sirve. El crecimiento se guarda aparte (`eps_growth`) y se muestra.
  - Es crecimiento PASADO: nada garantiza que continúe. Un PEG muy bajo
    por un rebote puntual del beneficio es una trampa habitual.
"""

import pandas as pd


PEG_MAX_YEARS = 5
MIN_POINTS = 3                    # mínimo 3 EPS (2 años de crecimiento)
SPLIT_RATIO = 1.6                 # salto de acciones año a año que se trata como split
YEAR_GAP_DAYS = (300, 430)        # años fiscales consecutivos

PEG_CHEAP = 1.0
PEG_EXPENSIVE = 2.0


def _num(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_eps_growth(df: pd.DataFrame) -> dict:
    """CAGR del EPS a partir del DataFrame de fundamentales de un
    ticker, ordenado por filed_date. Devuelve
    {"eps_growth": float|None, "eps_growth_years": int}."""

    empty = {"eps_growth": None, "eps_growth_years": 0}

    if df is None or df.empty or "eps" not in df.columns or "fiscal_year_end" not in df.columns:
        return empty

    work = df.copy()
    work["_end"] = pd.to_datetime(work["fiscal_year_end"], errors="coerce")
    work["_eps"] = work["eps"].map(_num)
    work["_shares"] = work["shares_outstanding"].map(_num) if "shares_outstanding" in work.columns else None
    work = work.dropna(subset=["_end", "_eps"]).sort_values("_end").reset_index(drop=True)

    if len(work) < MIN_POINTS:
        return empty

    # Ventana contigua que acaba en el último año: se extiende hacia atrás
    # mientras los años sean consecutivos y no haya salto de acciones (split)
    start = len(work) - 1
    while start > 0 and (len(work) - start) <= PEG_MAX_YEARS:
        gap = (work.loc[start, "_end"] - work.loc[start - 1, "_end"]).days
        if not (YEAR_GAP_DAYS[0] <= gap <= YEAR_GAP_DAYS[1]):
            break
        s_cur, s_prev = work.loc[start, "_shares"], work.loc[start - 1, "_shares"]
        if s_cur is not None and s_prev is not None and not pd.isna(s_cur) and not pd.isna(s_prev) and s_cur > 0 and s_prev > 0:
            ratio = s_cur / s_prev
            if ratio >= SPLIT_RATIO or ratio <= 1 / SPLIT_RATIO:
                break
        start -= 1

    window = work.iloc[start:]

    # El EPS inicial debe ser positivo: se recorta por delante hasta el primero positivo
    positive = window.index[window["_eps"] > 0]
    if len(positive) == 0:
        return empty
    window = window.loc[positive.min():]

    if len(window) < MIN_POINTS:
        return empty

    first, last = window.iloc[0], window.iloc[-1]

    if last["_eps"] <= 0 or first["_eps"] <= 0:
        return empty

    years = (last["_end"] - first["_end"]).days / 365.25

    if years < 1.5:
        return empty

    growth = (last["_eps"] / first["_eps"]) ** (1 / years) - 1

    return {"eps_growth": float(growth), "eps_growth_years": int(round(years))}


def compute_peg(pe, eps_growth):
    """PEG = P/E ÷ (crecimiento en %). None si P/E no es positivo o el
    crecimiento es <= 0 (ratio sin sentido)."""

    pe, g = _num(pe), _num(eps_growth)

    if pe is None or g is None or pe <= 0 or g <= 0:
        return None

    return pe / (g * 100)


def format_peg(peg) -> str:
    return "N/A" if peg is None or pd.isna(peg) else f"{peg:.2f}"


def peg_label(peg):
    """'barato' / 'razonable' / 'caro' (respecto al crecimiento) o None."""
    if peg is None or pd.isna(peg):
        return None
    if peg < PEG_CHEAP:
        return "barato"
    if peg <= PEG_EXPENSIVE:
        return "razonable"
    return "caro"
