"""
Diagnóstico de datos para Post-Earnings Announcement Drift (PEAD).

ANTES de construir el análisis completo, hay que saber si yfinance
te da suficiente histórico de fechas de resultados. Este script NO
hace ningún backtest todavía — solo comprueba, para cada ticker,
cuántas fechas de earnings hay disponibles y en qué rango de años.

Si la cobertura es buena (varios años, muchos trimestres), seguimos
con el análisis completo. Si es pobre (solo 1-4 trimestres), hay que
buscar otra fuente de datos antes de construir nada más.
"""

import pandas as pd
import yfinance as yf


TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]


def check_ticker(ticker: str) -> dict:

    try:
        t = yf.Ticker(ticker)
        earnings = t.get_earnings_dates(limit=80)
    except Exception as e:
        return {
            "ticker": ticker,
            "error": str(e),
            "n_dates": 0,
            "earliest": None,
            "latest": None,
            "has_eps_surprise": False,
        }

    if earnings is None or earnings.empty:
        return {
            "ticker": ticker,
            "error": "sin datos",
            "n_dates": 0,
            "earliest": None,
            "latest": None,
            "has_eps_surprise": False,
        }

    has_surprise = "Surprise(%)" in earnings.columns and earnings["Surprise(%)"].notna().any()

    return {
        "ticker": ticker,
        "error": None,
        "n_dates": len(earnings),
        "earliest": earnings.index.min(),
        "latest": earnings.index.max(),
        "has_eps_surprise": has_surprise,
    }


print()
print(f"Comprobando disponibilidad de datos de earnings para {len(TICKERS)} tickers...")
print("(esto hace una llamada de red por ticker, puede tardar)")
print()

results = []

for ticker in TICKERS:
    result = check_ticker(ticker)
    results.append(result)

    if result["error"]:
        print(f"{ticker:<6} | ERROR: {result['error']}")
    else:
        earliest = result["earliest"].strftime("%Y-%m-%d") if result["earliest"] is not None else "N/A"
        latest = result["latest"].strftime("%Y-%m-%d") if result["latest"] is not None else "N/A"
        print(
            f"{ticker:<6} | {result['n_dates']:>3} fechas | "
            f"{earliest} -> {latest} | "
            f"Surprise(%) disponible: {result['has_eps_surprise']}"
        )


results_df = pd.DataFrame(results)
results_df.to_csv("data/pead_data_availability.csv", index=False)

print()
print("=" * 90)
print("RESUMEN")
print("=" * 90)

valid = results_df[results_df["error"].isna()]

if not valid.empty:
    print(f"Tickers con datos: {len(valid)} de {len(TICKERS)}")
    print(f"Mediana de fechas de earnings por ticker: {valid['n_dates'].median():.0f}")
    print(f"Con Surprise(%): {valid['has_eps_surprise'].sum()} de {len(valid)}")

    valid_with_dates = valid.dropna(subset=["earliest", "latest"])
    if not valid_with_dates.empty:
        years_span = (valid_with_dates["latest"] - valid_with_dates["earliest"]).dt.days / 365
        print(f"Rango típico de histórico: {years_span.median():.1f} años (mediana)")

print()
print("=" * 90)
print("LECTURA")
print("=" * 90)
print(
    "Si la mediana de años de histórico es baja (ej. <3 años) o pocos\n"
    "tickers tienen Surprise(%), NO conviene construir el backtest completo\n"
    "de PEAD todavía — la muestra sería demasiado pequeña para el mismo\n"
    "nivel de rigor que hemos usado en el resto de la investigación.\n"
    "En ese caso, haría falta buscar otra fuente de datos de earnings\n"
    "antes de seguir con esta línea."
)

print()
print("Resultados completos guardados en: data/pead_data_availability.csv")
