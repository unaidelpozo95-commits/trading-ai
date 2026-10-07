"""
Puntuación combinada Valor + Calidad (0-100) por empresa.

Aritmética directa y comprobable, sin modelos ni pesos ajustados a los
datos. Dos mitades con el mismo peso (50% / 50%):

  VALOR    (¿está barata?)    P/E bajo · P/B bajo · FCF Yield alto
  CALIDAD  (¿es buena?)       ROE alto · D/E bajo · Piotroski F-Score alto

Cada métrica se convierte en una nota de 0 a 100:
  - P/E, P/B, FCF Yield, ROE y D/E: PERCENTIL dentro de TODO el universo
    con datos (no solo las que pasan el filtro de ROE) — 100 = la mejor
    del universo en esa métrica, 0 = la peor.
  - F-Score: la proporción de criterios cumplidos (7/9 → 78). Ya es una
    escala absoluta de 0 a 1, no hace falta percentil.
  - Una mitad = media de las notas de sus métricas disponibles (mínimo 2
    de 3; si no, la mitad queda sin nota). Total = media de las dos
    mitades; si falta una mitad, no hay puntuación total (N/A) — no se
    inventa nada con datos a medias.

PÉRDIDAS Y PATRIMONIO NEGATIVO: una empresa con beneficio por acción
negativo no tiene P/E calculable, pero eso NO es "dato que falta": es
la peor situación posible, así que su nota de P/E es 0 (igual con P/B y
D/E cuando el patrimonio es negativo). Si no se hiciera, perder dinero
saldría gratis en la puntuación.

La puntuación NUNCA se muestra sola: siempre con el desglose por
mitades y por métrica, para poder ver de dónde sale.

Los percentiles son RELATIVOS al universo del día: la nota de una
empresa puede moverse sin que ella cambie nada, solo porque cambian las
demás o su precio. Es una señal de "mira esto", no una medida absoluta.
"""

import pandas as pd


MIN_METRICS_PER_HALF = 2

# Umbrales de lectura (ajustables) para colorear/etiquetar el total
SCORE_HIGH = 65
SCORE_LOW = 35

# (columna de nota, nombre corto, mitad)
METRICS = [
    ("s_pe", "P/E", "valor"),
    ("s_pb", "P/B", "valor"),
    ("s_fcf", "FCF", "valor"),
    ("s_roe", "ROE", "calidad"),
    ("s_de", "D/E", "calidad"),
    ("s_f", "F-Score", "calidad"),
]

SCORE_COLUMNS = ["score_total", "score_value", "score_quality", "score_breakdown"] + [m[0] for m in METRICS]


def _percentile_score(series: pd.Series, higher_is_better: bool) -> pd.Series:
    """Nota 0-100 por percentil sobre los valores no nulos. 100 = mejor
    del universo, 0 = peor. Con un solo valor válido, 50."""

    valid = series.dropna()
    result = pd.Series(index=series.index, dtype="float64")

    if valid.empty:
        return result

    n = len(valid)

    if n == 1:
        result.loc[valid.index] = 50.0
        return result

    ranks = valid.rank(method="average", ascending=higher_is_better)
    result.loc[valid.index] = (ranks - 1) / (n - 1) * 100

    return result


def _fmt(value) -> str:
    return "N/A" if value is None or pd.isna(value) else f"{value:.0f}"


def compute_combined_scores(table: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una copia de `table` con las columnas de SCORE_COLUMNS
    añadidas. `table` es la tabla completa del screener (todas las
    empresas con precio y fundamentales)."""

    df = table.copy()

    if df.empty:
        for col in SCORE_COLUMNS:
            df[col] = None
        return df

    def col(name):
        return df[name] if name in df.columns else pd.Series(index=df.index, dtype="float64")

    eps = pd.to_numeric(col("eps"), errors="coerce")
    bvps = pd.to_numeric(col("book_value_per_share"), errors="coerce")
    pe = pd.to_numeric(col("pe"), errors="coerce")
    pb = pd.to_numeric(col("pb"), errors="coerce")
    de = pd.to_numeric(col("debt_to_equity"), errors="coerce")
    fcf = pd.to_numeric(col("fcf_yield"), errors="coerce")
    roe = pd.to_numeric(col("roe"), errors="coerce")
    f_score = pd.to_numeric(col("f_score"), errors="coerce")
    f_eval = pd.to_numeric(col("f_score_evaluable"), errors="coerce")

    # Percentil de menor a mayor valor: ascending=True da 100 al valor
    # más alto; para "menor es mejor" se invierte (ascending=False).
    df["s_pe"] = _percentile_score(pe.where(pe > 0), higher_is_better=False)
    df["s_pb"] = _percentile_score(pb.where(pb > 0), higher_is_better=False)
    df["s_fcf"] = _percentile_score(fcf, higher_is_better=True)
    df["s_roe"] = _percentile_score(roe, higher_is_better=True)
    df["s_de"] = _percentile_score(de.where(de >= 0), higher_is_better=False)

    # Pérdidas / patrimonio negativo = peor nota, no "dato que falta"
    df.loc[eps.notna() & (eps <= 0), "s_pe"] = 0.0
    df.loc[bvps.notna() & (bvps <= 0), "s_pb"] = 0.0
    df.loc[bvps.notna() & (bvps <= 0) & de.isna(), "s_de"] = 0.0

    f_ratio = (f_score / f_eval).where(f_score.notna() & (f_eval > 0))
    df["s_f"] = f_ratio * 100

    def half(metric_cols):
        block = df[metric_cols]
        mean = block.mean(axis=1, skipna=True)
        count = block.notna().sum(axis=1)
        return mean.where(count >= MIN_METRICS_PER_HALF)

    value_cols = [m[0] for m in METRICS if m[2] == "valor"]
    quality_cols = [m[0] for m in METRICS if m[2] == "calidad"]

    df["score_value"] = half(value_cols)
    df["score_quality"] = half(quality_cols)
    df["score_total"] = (df["score_value"] + df["score_quality"]) / 2

    def breakdown(row):
        if pd.isna(row["score_total"]):
            return None
        valor = ", ".join(f"{name} {_fmt(row[c])}" for c, name, h in METRICS if h == "valor" and pd.notna(row[c]))
        calidad = ", ".join(f"{name} {_fmt(row[c])}" for c, name, h in METRICS if h == "calidad" and pd.notna(row[c]))
        return f"Valor {_fmt(row['score_value'])} ({valor}) · Calidad {_fmt(row['score_quality'])} ({calidad})"

    df["score_breakdown"] = df.apply(breakdown, axis=1)

    for c in ["score_total", "score_value", "score_quality"] + [m[0] for m in METRICS]:
        df[c] = df[c].round(1)

    return df


def score_level(score_total):
    """'alta' / 'media' / 'baja' / None según SCORE_HIGH y SCORE_LOW."""
    if score_total is None or pd.isna(score_total):
        return None
    if score_total >= SCORE_HIGH:
        return "alta"
    if score_total <= SCORE_LOW:
        return "baja"
    return "media"


def format_score(score_total) -> str:
    return "N/A" if score_total is None or pd.isna(score_total) else f"{score_total:.0f}/100"


def short_breakdown(score_value, score_quality) -> str:
    """'Valor 78 · Calidad 70' — la versión corta para las fichas."""
    if pd.isna(score_value) or pd.isna(score_quality):
        return ""
    return f"Valor {score_value:.0f} · Calidad {score_quality:.0f}"
