"""
Detección de novedades día a día — SIN IA, pura lógica.

Guarda una "foto" (snapshot) de los datos de cada día en
data/snapshots/{fecha}/, y la compara contra la foto del día anterior
disponible para detectar cambios que merezca la pena destacar:

  - Empresas que ENTRAN o SALEN del top de calidad
  - Cambios grandes en P/E, D/E, o el signo de vs_target_pct
    (pasar de "por debajo del objetivo" a "por encima", o al revés)
  - Cambio de la puntuación combinada Valor+Calidad de 10 o más puntos
    (con la métrica que más lo explica)
  - Top movers del día: CADA UNO se comenta con su situación de
    valor/calidad (P/E, P/B, ROE, D/E, FCF Yield, Piotroski F-Score, precio objetivo) —
    no solo el % de subida/caída — para poder valorar si una caída es
    una oportunidad o una subida ya está agotada, y viceversa. Esto
    se hace siempre, todos los días, para todo el top movers.
  - Cada métrica se etiqueta con una OPINIÓN ya calculada (barata/cara,
    deuda alta/baja, genera/quema caja...) según umbrales fijos — los
    mismos que ya se explican en el glosario del email — y se añade
    una "lectura global" (p.ej. "no pinta mal" o "varias señales de
    alerta") contando cuántas de esas etiquetas son positivas o
    negativas. Esto también se aplica a entradas/salidas de la lista
    de calidad y a los cambios de P/E o D/E. Es aritmética directa con
    reglas fijas, no una puntuación oculta — el LLM solo redacta la
    opinión que esto ya concluyó, nunca decide el criterio.

Las anomalías (movimiento de precio/volumen fuera de rango) se siguen
calculando y guardando en `data/anomalies_report.csv` para quien
quiera mirarlas a mano, pero DELIBERADAMENTE no se convierten en
"hechos" aquí ni se le pasan a la IA — no entran en el email.

El resultado es una lista de "hechos" en texto plano — esto es lo que
luego se le pasa a un modelo de IA (ver daily_digest.py) para que
redacte el resumen. La IA nunca calcula estos hechos, solo los redacta.
"""

import os
import shutil
from datetime import datetime

import pandas as pd

from combined_score import METRICS as SCORE_METRICS, format_score, short_breakdown
from peg_ratio import peg_label
from piotroski import format_f_score, f_score_level


SNAPSHOTS_DIR = "data/snapshots"

QUALITY_CSV = "data/value_quality_screener_report.csv"
MOVERS_CSV = "data/top_movers_report.csv"
ANOMALIES_CSV = "data/anomalies_report.csv"

# Umbrales para considerar un cambio "grande" — ajustables
PE_CHANGE_THRESHOLD = 0.15   # 15% de cambio relativo en P/E
DE_CHANGE_THRESHOLD = 0.15   # 15% de cambio relativo en D/E
SCORE_CHANGE_THRESHOLD = 10  # puntos (de 100) de cambio en la puntuación combinada


def save_todays_snapshot() -> str:
    """Copia los 3 CSV de hoy a data/snapshots/{fecha}/. Devuelve la
    ruta de la carpeta creada."""

    today = datetime.now().strftime("%Y-%m-%d")
    folder = os.path.join(SNAPSHOTS_DIR, today)
    os.makedirs(folder, exist_ok=True)

    for src, name in [(QUALITY_CSV, "quality.csv"), (MOVERS_CSV, "movers.csv"), (ANOMALIES_CSV, "anomalies.csv")]:
        if os.path.exists(src):
            shutil.copy(src, os.path.join(folder, name))

    return folder


def find_previous_snapshot(before_date: str = None) -> str:
    """Busca la carpeta de snapshot más reciente ANTERIOR a hoy (o a
    before_date si se indica). Devuelve None si no hay ninguna."""

    if not os.path.exists(SNAPSHOTS_DIR):
        return None

    today = before_date or datetime.now().strftime("%Y-%m-%d")

    candidates = sorted(
        d for d in os.listdir(SNAPSHOTS_DIR)
        if os.path.isdir(os.path.join(SNAPSHOTS_DIR, d)) and d < today
    )

    if not candidates:
        return None

    return os.path.join(SNAPSHOTS_DIR, candidates[-1])


def _load_csv_safe(path: str) -> pd.DataFrame:
    if path is None or not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


# Umbrales de interpretación — LOS MISMOS que ya se explican en el
# glosario del email (templates/report_shell.html), para que la
# opinión que se da aquí sea consistente con lo que el usuario puede
# comprobar a mano. Es aritmética fija, no una IA decidiendo el
# criterio — el LLM solo redacta lo que esto ya concluyó.
PE_BARATA = 15
PE_CARA = 25
ROE_BUENO = 0.15
DEUDA_BAJA = 1.0
DEUDA_ALTA = 2.0
FCF_BUENO = 0.05
TARGET_MARGEN = 0.05  # margen antes de decir "infra/sobrevalorada" en vez de "cerca de objetivo"


def _valuation_tags(row: pd.Series) -> dict:
    """Banderas true/false ya interpretadas a partir de los umbrales de
    arriba — el bloque de construcción de toda opinión que se muestra
    en los hechos (por métrica) y en el veredicto global."""

    tags = {}

    pe = row.get("pe")
    if pd.notna(pe):
        tags["pe_barata"] = pe < PE_BARATA
        tags["pe_cara"] = pe > PE_CARA

    roe = row.get("roe")
    if pd.notna(roe):
        tags["roe_bueno"] = roe >= ROE_BUENO
        tags["roe_malo"] = roe < 0

    de = row.get("debt_to_equity")
    if pd.notna(de):
        tags["deuda_baja"] = de < DEUDA_BAJA
        tags["deuda_alta"] = de > DEUDA_ALTA

    fcf = row.get("fcf_yield")
    if pd.notna(fcf):
        tags["fcf_bueno"] = fcf >= FCF_BUENO
        tags["fcf_malo"] = fcf < 0

    vt = row.get("vs_target_pct")
    if pd.notna(vt):
        tags["infravalorada"] = vt > TARGET_MARGEN
        tags["sobrevalorada"] = vt < -TARGET_MARGEN

    level = f_score_level(row.get("f_score"), row.get("f_score_evaluable"))
    if level is not None:
        tags["f_score_solido"] = level == "sólido"
        tags["f_score_debil"] = level == "débil"

    return tags


def _verdict_from_tags(tags: dict) -> str:
    """Lectura global en una frase, contando cuántas señales positivas
    y negativas hay entre las ya calculadas — sigue siendo aritmética
    directa (contar banderas), no una puntuación oculta ni un juicio
    del LLM."""

    good = sum(1 for k in ("pe_barata", "roe_bueno", "deuda_baja", "fcf_bueno", "infravalorada", "f_score_solido") if tags.get(k))
    bad = sum(1 for k in ("pe_cara", "roe_malo", "deuda_alta", "fcf_malo", "sobrevalorada", "f_score_debil") if tags.get(k))

    if not tags:
        return "sin suficientes datos para una lectura global"
    if bad >= 2:
        return "⚠️ varias señales de alerta en sus fundamentales — conviene revisarla con calma antes de nada"
    if bad == 1 and good == 0:
        return "al menos una señal de alerta en sus fundamentales — mirar con cuidado"
    if bad == 1 and good >= 2:
        return "fundamentales mayoritariamente sólidos, con una salvedad a tener en cuenta"
    if good >= 2 and bad == 0:
        return "fundamentales sólidos según estos criterios — no pinta mal"
    if good >= 1 and bad == 0:
        return "fundamentales razonables, sin señales de alerta claras"
    return "fundamentales mixtos — ni claramente atractiva ni con banderas rojas evidentes"


def _mover_quality_commentary(row: pd.Series) -> str:
    """Frase con las métricas de valor/calidad disponibles para un
    mover, CADA UNA ya etiquetada como barata/cara, deuda alta/baja,
    etc. (umbrales fijos de arriba), más una lectura global al final —
    para poder decir si, además de moverse hoy, es una empresa
    interesante en sí misma (o si simplemente no tenemos datos suyos,
    p.ej. porque no reporta a la SEC)."""

    tags = _valuation_tags(row)
    parts = []

    if pd.notna(row.get("score_total")):
        parts.append(f"Puntuación combinada {format_score(row['score_total'])} ({short_breakdown(row.get('score_value'), row.get('score_quality'))})")
    if pd.notna(row.get("pe")):
        etiqueta = "barata" if tags.get("pe_barata") else ("cara" if tags.get("pe_cara") else "en rango razonable")
        parts.append(f"P/E {row['pe']:.1f} ({etiqueta})")
    if pd.notna(row.get("pb")):
        parts.append(f"P/B {row['pb']:.1f}")
    if pd.notna(row.get("roe")):
        etiqueta = "buena rentabilidad" if tags.get("roe_bueno") else ("en pérdidas" if tags.get("roe_malo") else "rentabilidad modesta")
        parts.append(f"ROE {row['roe']:.1%} ({etiqueta})")
    if pd.notna(row.get("debt_to_equity")):
        etiqueta = "deuda baja" if tags.get("deuda_baja") else ("deuda alta, ojo" if tags.get("deuda_alta") else "deuda moderada")
        parts.append(f"D/E {row['debt_to_equity']:.2f} ({etiqueta})")
    if pd.notna(row.get("fcf_yield")):
        etiqueta = "genera bastante caja" if tags.get("fcf_bueno") else ("quema caja, ojo" if tags.get("fcf_malo") else "genera algo de caja")
        parts.append(f"FCF Yield {row['fcf_yield']:.1%} ({etiqueta})")
    peg_lvl = peg_label(row.get("peg"))
    if peg_lvl is not None:
        parts.append(f"PEG {row['peg']:.2f} ({peg_lvl} respecto a su crecimiento pasado)")
    f_level = f_score_level(row.get("f_score"), row.get("f_score_evaluable"))
    if f_level is not None:
        nivel_f = {"sólido": "sólida", "intermedio": "intermedia", "débil": "débil"}[f_level]
        parts.append(f"Piotroski F-Score {format_f_score(row['f_score'], row['f_score_evaluable'])} (salud financiera {nivel_f})")
    if pd.notna(row.get("vs_target_pct")):
        etiqueta = "por debajo de su precio objetivo" if tags.get("infravalorada") else ("por encima de su precio objetivo" if tags.get("sobrevalorada") else "cerca de su precio objetivo")
        parts.append(f"precio objetivo {row['vs_target_pct']:+.1%} vs. actual ({etiqueta})")

    if not parts:
        return "sin fundamentales disponibles para valorarla (no reporta a la SEC o falta el dato)"

    return ", ".join(parts) + f". Lectura global: {_verdict_from_tags(tags)}"


def detect_novelties() -> list:
    """Devuelve una lista de strings, cada uno un "hecho" detectado.
    El comentario de cada top mover se genera siempre (no depende de
    tener snapshot anterior); el resto de chequeos (entradas/salidas
    de la lista de calidad, cambios de P/E o D/E) sí necesitan un
    snapshot de ayer para poder comparar."""

    facts = []

    today_quality = _load_csv_safe(QUALITY_CSV)
    today_movers = _load_csv_safe(MOVERS_CSV)

    previous_folder = find_previous_snapshot()

    # --- Top movers del día, cada uno comentado con su valor/calidad ---
    # Se hace todos los días para todo el top movers (no solo si es
    # "nuevo" respecto a ayer): el objetivo es poder valorar, con el
    # P/E, ROE, D/E, FCF Yield y precio objetivo de cada uno, si una
    # caída pinta a oportunidad o una subida ya se ha comido el
    # recorrido — no solo enterarte de que "se movió".
    if not today_movers.empty:
        quality_tickers = set(today_quality["ticker"]) if not today_quality.empty else set()

        for _, row in today_movers.iterrows():
            direccion = "subida" if row.get("tipo") == "subida" else "caída"
            commentary = _mover_quality_commentary(row)
            nota_calidad = " Está en tu lista de calidad." if row["ticker"] in quality_tickers else ""

            facts.append(
                f"{row['ticker']} ({row.get('company_name', '')}): {direccion} del "
                f"{row['change_pct']:+.1%} hoy -> {row['price']:.2f}. "
                f"Fundamentales: {commentary}.{nota_calidad}"
            )

    if previous_folder is None:
        return facts

    prev_quality = _load_csv_safe(os.path.join(previous_folder, "quality.csv"))

    # --- Empresas que entran o salen del top de calidad ---
    if not today_quality.empty and not prev_quality.empty:
        today_tickers = set(today_quality["ticker"])
        prev_tickers = set(prev_quality["ticker"])

        new_entries = today_tickers - prev_tickers
        exits = prev_tickers - today_tickers

        for ticker in new_entries:
            today_row = today_quality.loc[today_quality["ticker"] == ticker].iloc[0]
            name = today_row["company_name"]
            facts.append(
                f"{ticker} ({name}) ENTRA hoy en la lista de calidad — no estaba ayer. "
                f"{_mover_quality_commentary(today_row)}"
            )

        for ticker in exits:
            prev_row = prev_quality.loc[prev_quality["ticker"] == ticker].iloc[0]
            name = prev_row["company_name"]
            facts.append(
                f"{ticker} ({name}) SALE hoy de la lista de calidad — sí estaba ayer "
                f"(últimos datos conocidos: {_mover_quality_commentary(prev_row)})."
            )

        # --- Cambios grandes en tickers presentes en ambos días ---
        common = today_tickers & prev_tickers
        for ticker in common:

            today_row = today_quality.loc[today_quality["ticker"] == ticker].iloc[0]
            prev_row = prev_quality.loc[prev_quality["ticker"] == ticker].iloc[0]

            name = today_row["company_name"]

            today_tags = _valuation_tags(today_row)

            today_score, prev_score = today_row.get("score_total"), prev_row.get("score_total")
            if pd.notna(today_score) and pd.notna(prev_score) and abs(today_score - prev_score) >= SCORE_CHANGE_THRESHOLD:
                # ¿Qué métrica explica más el cambio? (mayor variación de nota)
                cambios = []
                for col_name, short_name, _half in SCORE_METRICS:
                    t, p_ = today_row.get(col_name), prev_row.get(col_name)
                    if pd.notna(t) and pd.notna(p_):
                        cambios.append((abs(t - p_), short_name, p_, t))
                motivo = ""
                if cambios:
                    _, nombre, antes, ahora = max(cambios)
                    motivo = f" Lo que más ha cambiado: {nombre} (nota de {antes:.0f} a {ahora:.0f})."
                direccion = "mejora" if today_score > prev_score else "empeora"
                facts.append(
                    f"{ticker} ({name}): su puntuación combinada {direccion} de {prev_score:.0f} a {today_score:.0f} "
                    f"(hoy: {short_breakdown(today_row.get('score_value'), today_row.get('score_quality'))}).{motivo}"
                )

            if pd.notna(today_row.get("pe")) and pd.notna(prev_row.get("pe")) and prev_row["pe"] != 0:
                pe_change = (today_row["pe"] - prev_row["pe"]) / prev_row["pe"]
                if abs(pe_change) >= PE_CHANGE_THRESHOLD:
                    etiqueta = "barata" if today_tags.get("pe_barata") else ("cara" if today_tags.get("pe_cara") else "en rango razonable")
                    facts.append(
                        f"{ticker} ({name}): su P/E cambió un {pe_change:+.1%} desde ayer "
                        f"({prev_row['pe']:.1f} -> {today_row['pe']:.1f}, ahora {etiqueta})."
                    )

            if pd.notna(today_row.get("debt_to_equity")) and pd.notna(prev_row.get("debt_to_equity")) and prev_row["debt_to_equity"] != 0:
                de_change = (today_row["debt_to_equity"] - prev_row["debt_to_equity"]) / prev_row["debt_to_equity"]
                if abs(de_change) >= DE_CHANGE_THRESHOLD:
                    etiqueta = "deuda baja" if today_tags.get("deuda_baja") else ("deuda alta, ojo" if today_tags.get("deuda_alta") else "deuda moderada")
                    facts.append(
                        f"{ticker} ({name}): su ratio deuda/patrimonio cambió un {de_change:+.1%} desde ayer "
                        f"({prev_row['debt_to_equity']:.2f} -> {today_row['debt_to_equity']:.2f}, ahora {etiqueta})."
                    )

            today_vs_target = today_row.get("vs_target_pct")
            prev_vs_target = prev_row.get("vs_target_pct")
            if pd.notna(today_vs_target) and pd.notna(prev_vs_target):
                if (today_vs_target > 0) != (prev_vs_target > 0):
                    lado_ahora = "por debajo (más atractiva por precio)" if today_vs_target > 0 else "por encima (menos atractiva por precio)"
                    facts.append(
                        f"{ticker} ({name}): ha cruzado su precio objetivo — ahora cotiza {lado_ahora} "
                        f"({today_vs_target:+.1%})."
                    )

    return facts
