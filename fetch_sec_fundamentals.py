"""
Descarga y cachea datos fundamentales anuales (10-K) desde SEC EDGAR.

Usa solo cifras de 10-K (anuales, no trimestrales) para simplificar:
NetIncomeLoss y StockholdersEquity del mismo informe anual, indexados
por la fecha REAL de presentación (`filed`), no por el cierre del año
fiscal — así el ROE calculado con estos datos solo "existe" para el
backtest a partir del día en que se hizo público de verdad, evitando
look-ahead bias.

Guarda un CSV por ticker en data/sec_fundamentals/{TICKER}.csv con
columnas: fiscal_year_end, filed_date, net_income, stockholders_equity, roe
"""

import os
import time

import pandas as pd
import requests


USER_AGENT = "ValueResearch tu-email-real@dominio.com"

OUTPUT_DIR = "data/sec_fundamentals"

HEADERS = {"User-Agent": USER_AGENT}


def load_tickers(path: str = "data/SP500.csv") -> list:
    """Lee tickers desde un CSV con columna 'ticker' o 'Symbol', arreglando
    símbolos con punto (BRK.B -> BRK-B)."""

    df = pd.read_csv(path)

    if "ticker" in df.columns:
        tickers = df["ticker"].tolist()
    elif "Symbol" in df.columns:
        tickers = df["Symbol"].tolist()
    else:
        raise ValueError(f"{path} no tiene columna 'ticker' ni 'Symbol'")

    tickers = [t.replace(".", "-") for t in tickers]

    return list(dict.fromkeys(tickers))


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


def fetch_annual_concept(cik: str, concept: str) -> pd.DataFrame:

    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
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


def build_ticker_fundamentals(ticker: str, cik: str) -> pd.DataFrame:

    net_income = fetch_annual_concept(cik, "NetIncomeLoss")
    time.sleep(0.15)

    equity = fetch_annual_concept(cik, "StockholdersEquity")
    time.sleep(0.15)

    if net_income.empty or equity.empty:
        return pd.DataFrame()

    merged = pd.merge(
        net_income[["fiscal_year_end", "filed_date", "value"]].rename(columns={"value": "net_income"}),
        equity[["fiscal_year_end", "value"]].rename(columns={"value": "stockholders_equity"}),
        on="fiscal_year_end",
        how="inner",
    )

    merged["roe"] = merged["net_income"] / merged["stockholders_equity"]

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
