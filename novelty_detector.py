"""
Detección de novedades día a día — SIN IA, pura lógica.

Guarda una "foto" (snapshot) de los datos de cada día en
data/snapshots/{fecha}/, y la compara contra la foto del día anterior
disponible para detectar cambios que merezca la pena destacar:

  - Empresas que ENTRAN o SALEN del top de calidad
  - Cambios grandes en P/E, D/E, o el signo de vs_target_pct
    (pasar de "por debajo del objetivo" a "por encima", o al revés)
  - Anomalías repetidas (mismo ticker con anomalía 2+ días seguidos)
  - Movers del día que TAMBIÉN están en la lista de calidad (cruce
    interesante: una empresa que ya nos gustaba, y hoy además se mueve)

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


def detect_novelties() -> list:
    """Devuelve una lista de strings, cada uno un "hecho" detectado.
    Si no hay snapshot anterior (primera vez que corre esto), solo
    incluye los hechos que no dependen de comparar con ayer (el cruce
    movers x calidad)."""

    facts = []

    today_quality = _load_csv_safe(QUALITY_CSV)
    today_movers = _load_csv_safe(MOVERS_CSV)
    today_anomalies = _load_csv_safe(ANOMALIES_CSV)

    previous_folder = find_previous_snapshot()

    # --- Cruce: movers de hoy que también están en la lista de calidad ---
    if not today_movers.empty and not today_quality.empty:
        quality_tickers = set(today_quality["ticker"])
        for _, row in today_movers.iterrows():
            if row["ticker"] in quality_tickers:
                direccion = "subida" if row.get("tipo") == "subida" else "caída"
                facts.append(
                    f"{row['ticker']} ({row.get('company_name', '')}) está en tu lista de calidad "
                    f"Y ADEMÁS hoy tuvo una {direccion} destacada del {row['change_pct']:+.1%}."
                )

    if previous_folder is None:
        return facts

    prev_quality = _load_csv_safe(os.path.join(previous_folder, "quality.csv"))
    prev_anomalies = _load_csv_safe(os.path.join(previous_folder, "anomalies.csv"))

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

    # --- Anomalías repetidas ---
    if not today_anomalies.empty and not prev_anomalies.empty:
        today_anomaly_tickers = set(today_anomalies["ticker"])
        prev_anomaly_tickers = set(prev_anomalies["ticker"])
        repeated = today_anomaly_tickers & prev_anomaly_tickers
        for ticker in repeated:
            name = today_anomalies.loc[today_anomalies["ticker"] == ticker, "company_name"].iloc[0]
            facts.append(f"{ticker} ({name}) tiene una anomalía de datos por SEGUNDO día seguido — vale la pena revisarlo.")

    return facts
