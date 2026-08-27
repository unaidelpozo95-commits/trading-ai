"""
Diagnóstico de datos fundamentales vía SEC EDGAR.

SEC EDGAR (data.sec.gov) es gratuito, sin clave de API, y contiene
todos los datos XBRL que las empresas han reportado oficialmente
desde ~2009. Este script comprueba, para cada uno de los 40 tickers,
cuántos años de histórico hay realmente disponibles para 3 conceptos
clave (ingresos, beneficio neto, patrimonio neto) — antes de construir
ningún backtest.

IMPORTANTE: la SEC exige identificarte con un User-Agent que incluya
un email de contacto real — cámbialo abajo antes de ejecutar, o la
SEC puede bloquear las peticiones.
"""

import time

import pandas as pd
import requests


USER_AGENT = "ValueResearch unaidelpozo95@gmail.com"

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

CONCEPTS_TO_CHECK = ["Revenues", "NetIncomeLoss", "StockholdersEquity"]

HEADERS = {"User-Agent": USER_AGENT}


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


def check_concept(cik: str, concept: str) -> dict:

    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"

    resp = requests.get(url, headers=HEADERS)

    if resp.status_code != 200:
        return {"available": False, "n_facts": 0, "earliest": None, "latest": None}

    data = resp.json()

    facts = []
    for unit_facts in data.get("units", {}).values():
        facts.extend(unit_facts)

    if not facts:
        return {"available": False, "n_facts": 0, "earliest": None, "latest": None}

    dates = [f["end"] for f in facts if "end" in f]

    return {
        "available": True,
        "n_facts": len(facts),
        "earliest": min(dates) if dates else None,
        "latest": max(dates) if dates else None,
    }


print()
print("Obteniendo mapa ticker -> CIK desde la SEC...")

try:
    ticker_to_cik = get_ticker_to_cik_map()
    print(f"Mapa obtenido: {len(ticker_to_cik)} tickers conocidos por la SEC.")
except Exception as e:
    print(f"ERROR obteniendo el mapa de tickers: {e}")
    raise SystemExit(1)


results = []

print()
print(f"Comprobando {len(CONCEPTS_TO_CHECK)} conceptos para {len(TICKERS)} tickers...")
print("(pausa de 0.15s entre peticiones para respetar el límite de la SEC)")
print()

for ticker in TICKERS:

    lookup_ticker = ticker.replace("-", ".")

    cik = ticker_to_cik.get(ticker) or ticker_to_cik.get(lookup_ticker)

    if cik is None:
        print(f"{ticker:<8} | NO ENCONTRADO en el mapa de la SEC")
        results.append({"ticker": ticker, "error": "no encontrado"})
        continue

    row = {"ticker": ticker, "cik": cik, "error": None}

    for concept in CONCEPTS_TO_CHECK:
        info = check_concept(cik, concept)
        row[f"{concept}_available"] = info["available"]
        row[f"{concept}_earliest"] = info["earliest"]
        row[f"{concept}_latest"] = info["latest"]
        time.sleep(0.15)

    revenues_range = f"{row.get('Revenues_earliest')} -> {row.get('Revenues_latest')}"
    print(f"{ticker:<8} | CIK {cik} | Revenues: {revenues_range}")

    results.append(row)


results_df = pd.DataFrame(results)
results_df.to_csv("data/sec_edgar_data_availability.csv", index=False)

print()
print("=" * 90)
print("RESUMEN")
print("=" * 90)

if "Revenues_earliest" in results_df.columns:
    valid = results_df.dropna(subset=["Revenues_earliest"])
    if not valid.empty:
        earliest_years = pd.to_datetime(valid["Revenues_earliest"]).dt.year
        print(f"Tickers con datos de Revenues: {len(valid)} de {len(TICKERS)}")
        print(f"Año más antiguo disponible (mediana): {earliest_years.median():.0f}")
        print(f"Año más antiguo disponible (el peor caso): {earliest_years.max():.0f}")

print()
print("Resultados completos guardados en: data/sec_edgar_data_availability.csv")
