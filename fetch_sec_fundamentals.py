"""
Descarga y cachea datos fundamentales anuales (10-K) desde SEC EDGAR.

Usa solo cifras de 10-K (anuales, no trimestrales) para simplificar:
NetIncomeLoss, StockholdersEquity, EPS diluido y acciones en
circulación, todo del mismo informe anual, indexado por la fecha REAL
de presentación (`filed`), no por el cierre del año fiscal — así
cualquier ratio calculado con estos datos solo "existe" a partir del
día en que se hizo público de verdad, evitando look-ahead bias.

Guarda un CSV por ticker en data/sec_fundamentals/{TICKER}.csv con
columnas: fiscal_year_end, filed_date, net_income, stockholders_equity,
eps, shares_outstanding, liabilities, operating_cash_flow, capex,
roe, book_value_per_share, debt_to_equity, free_cash_flow,
fcf_per_share, total_assets, current_assets, current_liabilities,
gross_profit, revenue
(las 5 últimas alimentan el Piotroski F-Score, ver piotroski.py)

REFRESCO: un fichero existente se vuelve a descargar si (a) tiene más
de FUNDAMENTALS_MAX_AGE_DAYS días — así llegan los 10-K nuevos — o
(b) le faltan columnas del esquema actual (REQUIRED_COLUMNS) — así una
ampliación del esquema se aplica sola, sin borrar data/sec_fundamentals/.
Si la descarga de un ticker falla, se conserva su fichero anterior.
"""

import os
import time

import pandas as pd
import requests

from ticker_universe import load_tickers


USER_AGENT = "ValueResearch tu-email-real@dominio.com"

OUTPUT_DIR = "data/sec_fundamentals"

HEADERS = {"User-Agent": USER_AGENT}

# Mismo valor que FUNDAMENTALS_MAX_AGE_DAYS en run_daily_pipeline.py
FUNDAMENTALS_MAX_AGE_DAYS = 25

# Si a un CSV existente le falta alguna, se vuelve a descargar entero
REQUIRED_COLUMNS = ["total_assets", "current_assets", "current_liabilities", "gross_profit", "revenue"]

# Ingresos: las empresas cambian de etiqueta XBRL con los años (p.ej. al
# adoptar ASC 606), así que se combinan y manda la primera con dato
REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
]


TICKERS = load_tickers()


def get_ticker_to_cik_map() -> dict:
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    mapping = {}
    for entry in data.values():
        ticker = entry["ticker"].upper()
        cik = str(entry["cik_str"]).zfill(10)
        mapping[ticker] = cik
    return mapping


def fetch_annual_concept(cik: str, concept: str, taxonomy: str = "us-gaap") -> pd.DataFrame:

    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code != 200:
        return pd.DataFrame()

    data = resp.json()

    rows = []
    for unit_facts in data.get("units", {}).values():
        for fact in unit_facts:
            if fact.get("form") != "10-K":
                continue
            rows.append({
                "fiscal_year_end": fact.get("end"),
                "filed_date": fact.get("filed"),
                "value": fact.get("val"),
                "fy": fact.get("fy"),
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values("filed_date").drop_duplicates(subset="fiscal_year_end", keep="first")

    return df


def fetch_concept_with_fallbacks(cik: str, concepts: list) -> pd.DataFrame:
    """Prueba varias etiquetas XBRL y las combina por año fiscal: para
    cada año manda la primera etiqueta de la lista que tenga dato."""

    frames = []
    for concept in concepts:
        df = fetch_annual_concept(cik, concept)
        time.sleep(0.15)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames).drop_duplicates(subset="fiscal_year_end", keep="first")


def merge_optional_concept(merged: pd.DataFrame, concept_df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Añade una columna opcional (left join por año fiscal); si el
    concepto no existe para esta empresa, la columna queda vacía."""

    if concept_df.empty:
        merged[column] = None
        return merged

    return pd.merge(
        merged,
        concept_df[["fiscal_year_end", "value"]].rename(columns={"value": column}),
        on="fiscal_year_end",
        how="left",
    )


def fetch_shares_outstanding(cik: str) -> pd.DataFrame:
    """Acciones en circulación — vive en la taxonomía 'dei' (datos de
    portada del informe), no en 'us-gaap'. Se prueban dos conceptos
    porque las empresas no siempre usan el mismo."""

    df = fetch_annual_concept(cik, "EntityCommonStockSharesOutstanding", taxonomy="dei")

    if df.empty:
        df = fetch_annual_concept(cik, "CommonStockSharesOutstanding", taxonomy="us-gaap")

    return df


def build_ticker_fundamentals(ticker: str, cik: str) -> pd.DataFrame:

    net_income = fetch_annual_concept(cik, "NetIncomeLoss")
    time.sleep(0.15)

    equity = fetch_annual_concept(cik, "StockholdersEquity")
    time.sleep(0.15)

    eps = fetch_annual_concept(cik, "EarningsPerShareDiluted")
    time.sleep(0.15)
    if eps.empty:
        eps = fetch_annual_concept(cik, "EarningsPerShareBasic")
        time.sleep(0.15)

    shares = fetch_shares_outstanding(cik)
    time.sleep(0.15)

    liabilities = fetch_annual_concept(cik, "Liabilities")
    time.sleep(0.15)

    operating_cash_flow = fetch_annual_concept(cik, "NetCashProvidedByUsedInOperatingActivities")
    time.sleep(0.15)

    capex = fetch_annual_concept(cik, "PaymentsToAcquirePropertyPlantAndEquipment")
    time.sleep(0.15)

    # --- Para el Piotroski F-Score ---
    total_assets = fetch_annual_concept(cik, "Assets")
    time.sleep(0.15)

    current_assets = fetch_annual_concept(cik, "AssetsCurrent")
    time.sleep(0.15)

    current_liabilities = fetch_annual_concept(cik, "LiabilitiesCurrent")
    time.sleep(0.15)

    gross_profit = fetch_annual_concept(cik, "GrossProfit")
    time.sleep(0.15)

    revenue = fetch_concept_with_fallbacks(cik, REVENUE_CONCEPTS)

    if net_income.empty or equity.empty:
        return pd.DataFrame()

    merged = pd.merge(
        net_income[["fiscal_year_end", "filed_date", "value"]].rename(columns={"value": "net_income"}),
        equity[["fiscal_year_end", "value"]].rename(columns={"value": "stockholders_equity"}),
        on="fiscal_year_end",
        how="inner",
    )

    if not eps.empty:
        merged = pd.merge(
            merged,
            eps[["fiscal_year_end", "value"]].rename(columns={"value": "eps"}),
            on="fiscal_year_end",
            how="left",
        )
    else:
        merged["eps"] = None

    if not shares.empty:
        merged = pd.merge(
            merged,
            shares[["fiscal_year_end", "value"]].rename(columns={"value": "shares_outstanding"}),
            on="fiscal_year_end",
            how="left",
        )
    else:
        merged["shares_outstanding"] = None

    if not liabilities.empty:
        merged = pd.merge(
            merged,
            liabilities[["fiscal_year_end", "value"]].rename(columns={"value": "liabilities"}),
            on="fiscal_year_end",
            how="left",
        )
    else:
        merged["liabilities"] = None

    if not operating_cash_flow.empty:
        merged = pd.merge(
            merged,
            operating_cash_flow[["fiscal_year_end", "value"]].rename(columns={"value": "operating_cash_flow"}),
            on="fiscal_year_end",
            how="left",
        )
    else:
        merged["operating_cash_flow"] = None

    if not capex.empty:
        merged = pd.merge(
            merged,
            capex[["fiscal_year_end", "value"]].rename(columns={"value": "capex"}),
            on="fiscal_year_end",
            how="left",
        )
    else:
        merged["capex"] = None

    merged = merge_optional_concept(merged, total_assets, "total_assets")
    merged = merge_optional_concept(merged, current_assets, "current_assets")
    merged = merge_optional_concept(merged, current_liabilities, "current_liabilities")
    merged = merge_optional_concept(merged, gross_profit, "gross_profit")
    merged = merge_optional_concept(merged, revenue, "revenue")

    merged["roe"] = merged["net_income"] / merged["stockholders_equity"]

    merged["book_value_per_share"] = merged["stockholders_equity"] / merged["shares_outstanding"]

    # Flujo de caja libre = flujo de caja operativo - CapEx (inversión en
    # activo fijo). Más difícil de maquillar contablemente que el
    # beneficio neto, que puede incluir partidas no monetarias.
    merged["free_cash_flow"] = merged.apply(
        lambda row: row["operating_cash_flow"] - row["capex"]
        if pd.notna(row["operating_cash_flow"]) and pd.notna(row["capex"])
        else None,
        axis=1,
    )

    merged["fcf_per_share"] = merged.apply(
        lambda row: row["free_cash_flow"] / row["shares_outstanding"]
        if pd.notna(row["free_cash_flow"]) and pd.notna(row["shares_outstanding"]) and row["shares_outstanding"] > 0
        else None,
        axis=1,
    )

    # Deuda/Patrimonio: solo tiene sentido si el patrimonio es positivo
    # (con patrimonio negativo el ratio sale sin sentido — una empresa
    # con patrimonio negativo ya es de por sí una señal de alerta que
    # no necesita este ratio para verse)
    merged["debt_to_equity"] = merged.apply(
        lambda row: row["liabilities"] / row["stockholders_equity"]
        if pd.notna(row["liabilities"]) and row["stockholders_equity"] > 0
        else None,
        axis=1,
    )

    return merged.sort_values("filed_date")


def needs_download(path: str) -> bool:
    """True si el fichero no existe, está desactualizado (> 25 días) o
    es de un esquema antiguo al que le faltan columnas."""

    if not os.path.exists(path):
        return True

    age_days = (time.time() - os.path.getmtime(path)) / 86400
    if age_days > FUNDAMENTALS_MAX_AGE_DAYS:
        return True

    try:
        columns = set(pd.read_csv(path, nrows=0).columns)
    except Exception:
        return True

    return not set(REQUIRED_COLUMNS).issubset(columns)


print()
print("Obteniendo mapa ticker -> CIK...")
ticker_to_cik = get_ticker_to_cik_map()

print(f"Tickers a procesar: {len(TICKERS)} (desde data/SP500.csv)")

os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"Descargando fundamentales anuales para {len(TICKERS)} tickers...")
print()

ok, failed = [], []

for ticker in TICKERS:

    output_path = os.path.join(OUTPUT_DIR, f"{ticker}.csv")

    if not needs_download(output_path):
        print(f"{ticker}: al día, se omite")
        ok.append(ticker)
        continue

    lookup_ticker = ticker.replace("-", ".")
    cik = ticker_to_cik.get(ticker) or ticker_to_cik.get(lookup_ticker)

    if cik is None:
        print(f"{ticker}: CIK no encontrado")
        failed.append(ticker)
        continue

    try:
        df = build_ticker_fundamentals(ticker, cik)
    except Exception as e:
        print(f"{ticker}: ERROR ({e})")
        failed.append(ticker)
        continue

    if df.empty:
        print(f"{ticker}: sin datos suficientes (falta NetIncomeLoss o StockholdersEquity)")
        failed.append(ticker)
        continue

    df.to_csv(output_path, index=False)
    print(f"{ticker}: guardado ({len(df)} años, {df['filed_date'].min()} -> {df['filed_date'].max()})")
    ok.append(ticker)


print()
print("=" * 70)
print("RESUMEN")
print("=" * 70)
print(f"OK: {len(ok)} de {len(TICKERS)}")
if failed:
    print(f"Fallidos: {failed}")
print()
print(f"Datos guardados en: {OUTPUT_DIR}/")
