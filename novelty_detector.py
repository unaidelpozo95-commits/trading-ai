"""
Detección de novedades día a día — SIN IA, pura lógica.

Guarda una "foto" (snapshot) de los datos de cada día en
data/snapshots/{fecha}/, y la compara contra la foto del día anterior
disponible para detectar cambios que merezca la pena destacar:

  - Empresas que ENTRAN o SALEN del top de calidad
  - Cambios grandes en P/E, D/E, o el signo de vs_target_pct
    (pasar de "por debajo del objetivo" a "por encima", o al revés)
  - Top movers del día: CADA UNO se comenta con su situación de
    valor/calidad (P/E, P/B, ROE, D/E, FCF Yield, precio objetivo) —
    no solo el % de subida/caída — para poder valorar si una caída es
    una oportunidad o una subida ya está agotada, y viceversa. Esto
    se hace siempre, todos los días, para todo el top movers.

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


SNAPSHOTS_DIR = "data/snapshots"

QUALITY_CSV = "data/value_quality_screener_report.csv"
MOVERS_CSV = "data/top_movers_report.csv"
ANOMALIES_CSV = "data/anomalies_report.csv"

# Umbrales para considerar un cambio "grande" — ajustables
PE_CHANGE_THRESHOLD = 0.15   # 15% de cambio relativo en P/E
DE_CHANGE_THRESHOLD = 0.15   # 15% de cambio relativo en D/E


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


def _mover_quality_commentary(row: pd.Series) -> str:
    """Frase con las métricas de valor/calidad disponibles para un
    mover — para poder decir si, además de moverse hoy, es una empresa
    interesante en sí misma (o si simplemente no tenemos datos suyos,
    p.ej. porque no reporta a la SEC)."""

    parts = []

    if pd.notna(row.get("pe")):
        parts.append(f"P/E {row['pe']:.1f}")
    if pd.notna(row.get("pb")):
        parts.append(f"P/B {row['pb']:.1f}")
    if pd.notna(row.get("roe")):
        parts.append(f"ROE {row['roe']:.1%}")
    if pd.notna(row.get("debt_to_equity")):
        parts.append(f"D/E {row['debt_to_equity']:.2f}")
    if pd.notna(row.get("fcf_yield")):
        parts.append(f"FCF Yield {row['fcf_yield']:.1%}")
    if pd.notna(row.get("vs_target_pct")):
        parts.append(f"precio objetivo {row['vs_target_pct']:+.1%} respecto al actual")

    if not parts:
        return "sin fundamentales disponibles para valorarla (no reporta a la SEC o falta el dato)"

    return ", ".join(parts)


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
            name = today_quality.loc[today_quality["ticker"] == ticker, "company_name"].iloc[0]
            facts.append(f"{ticker} ({name}) ENTRA hoy en la lista de calidad — no estaba ayer.")

        for ticker in exits:
            name = prev_quality.loc[prev_quality["ticker"] == ticker, "company_name"].iloc[0]
            facts.append(f"{ticker} ({name}) SALE hoy de la lista de calidad — sí estaba ayer.")

        # --- Cambios grandes en tickers presentes en ambos días ---
        common = today_tickers & prev_tickers
        for ticker in common:

            today_row = today_quality.loc[today_quality["ticker"] == ticker].iloc[0]
            prev_row = prev_quality.loc[prev_quality["ticker"] == ticker].iloc[0]

            name = today_row["company_name"]

            if pd.notna(today_row.get("pe")) and pd.notna(prev_row.get("pe")) and prev_row["pe"] != 0:
                pe_change = (today_row["pe"] - prev_row["pe"]) / prev_row["pe"]
                if abs(pe_change) >= PE_CHANGE_THRESHOLD:
                    facts.append(
                        f"{ticker} ({name}): su P/E cambió un {pe_change:+.1%} desde ayer "
                        f"({prev_row['pe']:.1f} -> {today_row['pe']:.1f})."
                    )

            if pd.notna(today_row.get("debt_to_equity")) and pd.notna(prev_row.get("debt_to_equity")) and prev_row["debt_to_equity"] != 0:
                de_change = (today_row["debt_to_equity"] - prev_row["debt_to_equity"]) / prev_row["debt_to_equity"]
                if abs(de_change) >= DE_CHANGE_THRESHOLD:
                    facts.append(
                        f"{ticker} ({name}): su ratio deuda/patrimonio cambió un {de_change:+.1%} desde ayer "
                        f"({prev_row['debt_to_equity']:.2f} -> {today_row['debt_to_equity']:.2f})."
                    )

            today_vs_target = today_row.get("vs_target_pct")
            prev_vs_target = prev_row.get("vs_target_pct")
            if pd.notna(today_vs_target) and pd.notna(prev_vs_target):
                if (today_vs_target > 0) != (prev_vs_target > 0):
                    lado_ahora = "por debajo" if today_vs_target > 0 else "por encima"
                    facts.append(
                        f"{ticker} ({name}): ha cruzado su precio objetivo — ahora cotiza {lado_ahora} "
                        f"({today_vs_target:+.1%})."
                    )

    return facts
