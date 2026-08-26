"""
Diagnóstico de datos fundamentales vía yfinance.

ANTES de construir ningún backtest de factores Value/Quality, hay que
saber si yfinance da suficiente histórico. Este script NO hace ningún
backtest — solo comprueba, para cada ticker:

  1. ticker.info: valores ACTUALES de ratios clave (P/E, P/B, ROE,
     deuda/equity). Esto es solo una foto de HOY, útil para saber si
     el dato existe en general, pero NO sirve para backtesting
     histórico por sí solo.

  2. ticker.quarterly_balance_sheet / quarterly_financials /
     quarterly_cashflow: cuántos trimestres de histórico hay
     realmente disponibles — esto sí determina si se puede construir
     una serie temporal de ratios a lo largo de los años.

AVISO IMPORTANTE que ya sabemos de antemano: incluso si hay varios
años de histórico, estos son datos TAL COMO SE VEN HOY (posiblemente
reexpresados/revisados), no necesariamente lo que se conocía en el
momento (point-in-time). Backtestear con datos reexpresados introduce
look-ahead bias — hay que tenerlo en cuenta al interpretar cualquier
resultado futuro, no solo la profundidad del histórico.
"""

import pandas as pd
import yfinance as yf


TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

INFO_FIELDS = ["trailingPE", "priceToBook", "returnOnEquity", "debtToEquity", "marketCap"]


def check_ticker(ticker: str) -> dict:

    result = {
        "ticker": ticker,
        "error": None,
        "info_fields_available": 0,
        "quarterly_financials_n": 0,
        "quarterly_financials_range": None,
        "quarterly_balance_n": 0,
        "quarterly_balance_range": None,
    }

    try:
        t = yf.Ticker(ticker)

        info = t.info
        result["info_fields_available"] = sum(
            1 for f in INFO_FIELDS if info.get(f) is not None
        )

        qf = t.quarterly_financials
        if qf is not None and not qf.empty:
            result["quarterly_financials_n"] = qf.shape[1]
            dates = sorted(qf.columns)
            result["quarterly_financials_range"] = f"{dates[0].date()} -> {dates[-1].date()}"

        qb = t.quarterly_balance_sheet
        if qb is not None and not qb.empty:
            result["quarterly_balance_n"] = qb.shape[1]
            dates = sorted(qb.columns)
            result["quarterly_balance_range"] = f"{dates[0].date()} -> {dates[-1].date()}"

    except Exception as e:
        result["error"] = str(e)

    return result


print()
print(f"Comprobando disponibilidad de datos fundamentales para {len(TICKERS)} tickers...")
print("(esto hace varias llamadas de red por ticker, puede tardar bastante)")
print()

results = []

for ticker in TICKERS:
    r = check_ticker(ticker)
    results.append(r)

    if r["error"]:
        print(f"{ticker:<8} | ERROR: {r['error']}")
    else:
        print(
            f"{ticker:<8} | info: {r['info_fields_available']}/{len(INFO_FIELDS)} campos | "
            f"financials trimestrales: {r['quarterly_financials_n']} ({r['quarterly_financials_range']}) | "
            f"balance trimestral: {r['quarterly_balance_n']} ({r['quarterly_balance_range']})"
        )


results_df = pd.DataFrame(results)
results_df.to_csv("data/fundamental_data_availability.csv", index=False)

print()
print("=" * 90)
print("RESUMEN")
print("=" * 90)

valid = results_df[results_df["error"].isna()]

if not valid.empty:
    print(f"Tickers con datos: {len(valid)} de {len(TICKERS)}")
    print(f"Mediana de campos de info disponibles: {valid['info_fields_available'].median():.0f} de {len(INFO_FIELDS)}")
    print(f"Mediana de trimestres de financials disponibles: {valid['quarterly_financials_n'].median():.0f}")
    print(f"Mediana de trimestres de balance disponibles: {valid['quarterly_balance_n'].median():.0f}")

print()
print("=" * 90)
print("LECTURA")
print("=" * 90)
print(
    "Si la mediana de trimestres es baja (ej. <16, menos de 4 años), NO hay\n"
    "suficiente histórico para un backtest de factores fundamentales con el\n"
    "mismo rigor que hemos aplicado al resto de esta investigación (recuerda\n"
    "que momentum/reversión usaron 8-11 años de datos). En ese caso, la\n"
    "conclusión honesta es que yfinance no sirve para esto y haría falta una\n"
    "fuente de datos fundamentales de pago con histórico point-in-time real\n"
    "(ej. Sharadar, Compustat, FactSet) antes de seguir con esta vía."
)

print()
print("Resultados completos guardados en: data/fundamental_data_availability.csv")
