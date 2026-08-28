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
eps, shares_outstanding, roe, book_value_per_share

AVISO: si ya tenías datos descargados con la versión anterior de este
script (sin eps/shares_outstanding), borra data/sec_fundamentals/ y
vuelve a descargar — el chequeo de "ya existe" no distingue esquemas
de columnas distintos.
"""

import os
import time

import pandas as pd
import requests

from ticker_universe import load_tickers


USER_AGENT = "ValueResearch tu-email-real@dominio.com"

OUTPUT_DIR = "data/sec_fundamentals"

HEADERS = {"User-Agent": USER_AGENT}


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

    merged["roe"] = merged["net_income"] / merged["stockholders_equity"]

    merged["book_value_per_share"] = merged["stockholders_equity"] / merged["shares_outstanding"]

    return merged.sort_values("filed_date")


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

    if os.path.exists(output_path):
        print(f"{ticker}: ya existe, se omite")
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
