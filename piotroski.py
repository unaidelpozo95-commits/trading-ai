"""
Piotroski F-Score (Piotroski, 2000) — 9 criterios binarios (cumple / no
cumple) sobre la salud financiera de una empresa, comparando el último
año fiscal con el anterior. Pura aritmética sobre los fundamentales ya
descargados de SEC EDGAR: sin modelos ni caja negra, y cada criterio se
puede comprobar a mano.

Rentabilidad
  1. ROA positivo                      (beneficio neto / activos totales > 0)
  2. Flujo de caja operativo positivo
  3. ROA mejora respecto al año anterior
  4. Calidad del beneficio             (flujo de caja operativo > beneficio neto:
                                        el beneficio no es solo "contable")
Deuda, liquidez y financiación
  5. Apalancamiento baja               (pasivos totales / activos totales menor que el año anterior)
  6. Ratio corriente mejora            (activo corriente / pasivo corriente)
  7. Sin dilución                      (no hay más acciones que el año anterior)
Eficiencia operativa
  8. Margen bruto mejora               (beneficio bruto / ingresos)
  9. Rotación de activos mejora        (ingresos / activos totales)

Puntuación = nº de criterios cumplidos. Interpretación habitual: 7-9 =
fundamentales sólidos, 0-3 = débiles.

DIFERENCIAS CON EL PAPER ORIGINAL (documentadas, no ocultas):
  - Se usan activos de FIN de año (no de principio) para ROA y rotación.
  - El apalancamiento usa pasivos totales / activos totales (el paper usa
    deuda a largo plazo, un concepto XBRL que muchas empresas no
    informan de forma uniforme).
  - Las acciones salen de la portada del 10-K (dato ruidoso), por eso se
    tolera hasta un +1% de aumento antes de considerar "dilución".

CRITERIOS NO EVALUABLES: no todas las empresas informan de todo (los
bancos no tienen activo corriente ni beneficio bruto, por ejemplo). Un
criterio sin datos NO cuenta ni como cumplido ni como fallado: se
descuenta de los "evaluables". El resultado se muestra como "7/9" o,
si faltan datos, "5/7" (5 cumplidos de 7 evaluables). Si hay menos de
MIN_EVALUABLE criterios evaluables, no se da puntuación (N/A) — con 3 o
4 criterios el número no significa nada.
"""

import pandas as pd


MIN_EVALUABLE = 6
SHARES_TOLERANCE = 1.01   # hasta +1% de acciones no se considera dilución
MAX_YEAR_GAP_DAYS = (300, 430)  # los dos años comparados deben ser consecutivos

STRONG_RATIO = 7 / 9   # 7 de 9 (o su equivalente proporcional)
WEAK_RATIO = 3 / 9

CRITERIA = [
    "roa_positivo",
    "cfo_positivo",
    "roa_mejora",
    "calidad_beneficio",
    "apalancamiento_baja",
    "ratio_corriente_mejora",
    "sin_dilucion",
    "margen_bruto_mejora",
    "rotacion_activos_mejora",
]


def _num(value):
    """float válido o None (NaN/None/no numérico → None)."""
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator, denominator):
    n, d = _num(numerator), _num(denominator)
    if n is None or d is None or d <= 0:
        return None
    return n / d


def _compare(current, previous, strictly_greater=True):
    """True/False si ambos existen, None si falta alguno."""
    if current is None or previous is None:
        return None
    return current > previous if strictly_greater else current < previous


def compute_piotroski(df: pd.DataFrame) -> dict:
    """Calcula el F-Score con las dos últimas filas (años fiscales) del
    DataFrame de fundamentales de un ticker, ordenado por filed_date.

    Devuelve {"f_score": int|None, "f_score_evaluable": int,
    "f_score_details": {criterio: True/False/None}}.
    """

    empty = {
        "f_score": None,
        "f_score_evaluable": 0,
        "f_score_details": {name: None for name in CRITERIA},
    }

    if df is None or len(df) < 2:
        return empty

    cur = df.iloc[-1]
    prev = df.iloc[-2]

    try:
        gap_days = (pd.to_datetime(cur["fiscal_year_end"]) - pd.to_datetime(prev["fiscal_year_end"])).days
    except Exception:
        return empty

    if not (MAX_YEAR_GAP_DAYS[0] <= gap_days <= MAX_YEAR_GAP_DAYS[1]):
        return empty

    def g(row, col):
        return _num(row.get(col))

    roa_cur = _ratio(g(cur, "net_income"), g(cur, "total_assets"))
    roa_prev = _ratio(g(prev, "net_income"), g(prev, "total_assets"))

    cfo_cur = g(cur, "operating_cash_flow")
    ni_cur = g(cur, "net_income")

    lev_cur = _ratio(g(cur, "liabilities"), g(cur, "total_assets"))
    lev_prev = _ratio(g(prev, "liabilities"), g(prev, "total_assets"))

    cr_cur = _ratio(g(cur, "current_assets"), g(cur, "current_liabilities"))
    cr_prev = _ratio(g(prev, "current_assets"), g(prev, "current_liabilities"))

    gm_cur = _ratio(g(cur, "gross_profit"), g(cur, "revenue"))
    gm_prev = _ratio(g(prev, "gross_profit"), g(prev, "revenue"))

    at_cur = _ratio(g(cur, "revenue"), g(cur, "total_assets"))
    at_prev = _ratio(g(prev, "revenue"), g(prev, "total_assets"))

    shares_cur, shares_prev = g(cur, "shares_outstanding"), g(prev, "shares_outstanding")

    details = {
        "roa_positivo": (roa_cur > 0) if roa_cur is not None else None,
        "cfo_positivo": (cfo_cur > 0) if cfo_cur is not None else None,
        "roa_mejora": _compare(roa_cur, roa_prev),
        "calidad_beneficio": (cfo_cur > ni_cur) if cfo_cur is not None and ni_cur is not None else None,
        "apalancamiento_baja": _compare(lev_cur, lev_prev, strictly_greater=False),
        "ratio_corriente_mejora": _compare(cr_cur, cr_prev),
        "sin_dilucion": (
            (shares_cur <= shares_prev * SHARES_TOLERANCE)
            if shares_cur is not None and shares_prev is not None and shares_prev > 0 else None
        ),
        "margen_bruto_mejora": _compare(gm_cur, gm_prev),
        "rotacion_activos_mejora": _compare(at_cur, at_prev),
    }

    evaluable = [v for v in details.values() if v is not None]

    if len(evaluable) < MIN_EVALUABLE:
        return {"f_score": None, "f_score_evaluable": len(evaluable), "f_score_details": details}

    return {
        "f_score": int(sum(1 for v in evaluable if v)),
        "f_score_evaluable": len(evaluable),
        "f_score_details": details,
    }


def format_f_score(f_score, evaluable) -> str:
    """'7/9', '5/7' (si faltan criterios evaluables) o 'N/A'."""
    if f_score is None or pd.isna(f_score) or evaluable is None or pd.isna(evaluable) or evaluable <= 0:
        return "N/A"
    return f"{int(f_score)}/{int(evaluable)}"


def f_score_level(f_score, evaluable):
    """'sólido' / 'intermedio' / 'débil' / None — por proporción de
    criterios cumplidos (así '5/6' se trata igual que '7/9')."""
    if f_score is None or pd.isna(f_score) or evaluable is None or pd.isna(evaluable) or evaluable <= 0:
        return None
    ratio = f_score / evaluable
    if ratio >= STRONG_RATIO - 1e-9:
        return "sólido"
    if ratio <= WEAK_RATIO + 1e-9:
        return "débil"
    return "intermedio"
