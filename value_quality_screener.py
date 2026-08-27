"""
Screener diario de Valor + Calidad.

Nada de IA, nada de caja negra: para cada ticker calcula P/E, P/B y
ROE con los datos más recientes disponibles (precio de hoy + último
10-K presentado), y saca un ranking transparente de las empresas más
baratas (P/E y P/B bajos) que además son rentables (ROE alto).

Requiere haber corrido antes:
  - download_sp500.py (o download_universe.py) para los precios
  - fetch_sec_fundamentals.py para los fundamentales

USO:
    python value_quality_screener.py
    python value_quality_screener.py --top 30
    python value_quality_screener.py --min-roe 0.15
"""

import argparse
import os

import pandas as pd

FUNDAMENTALS_DIR = "data/sec_fundamentals"
PRICE_DIR = "data/raw/yahoo"


def load_tickers(path: str = "data/SP500.csv") -> list:
    df = pd.read_csv(path)
    if "ticker" in df.columns:
        tickers = df["ticker"].tolist()
    elif "Symbol" in df.columns:
        tickers = df["Symbol"].tolist()
    else:
        raise ValueError(f"{path} no tiene columna 'ticker' ni 'Symbol'")
    tickers = [t.replace(".", "-") for t in tickers]
    return list(dict.fromkeys(tickers))


def get_latest_price(ticker: str):

    path = os.path.join(PRICE_DIR, f"{ticker}.parquet")

    if not os.path.exists(path):
        return None, None

    df = pd.read_parquet(path)

    if df.empty:
        return None, None

    last_row = df.iloc[-1]
    last_date = df.index[-1]

    return last_row["Close"], last_date


def get_latest_fundamentals(ticker: str) -> dict:

    path = os.path.join(FUNDAMENTALS_DIR, f"{ticker}.csv")

    if not os.path.exists(path):
        return {}

    df = pd.read_csv(path, parse_dates=["filed_date"])

    if df.empty:
        return {}

    df = df.sort_values("filed_date")
    latest = df.iloc[-1]

    return {
        "fiscal_year_end": latest.get("fiscal_year_end"),
        "filed_date": latest.get("filed_date"),
        "eps": latest.get("eps"),
        "book_value_per_share": latest.get("book_value_per_share"),
        "roe": latest.get("roe"),
    }


def build_screener_table(tickers: list) -> pd.DataFrame:

    rows = []

    for ticker in tickers:

        price, price_date = get_latest_price(ticker)

        if price is None:
            continue

        fundamentals = get_latest_fundamentals(ticker)

        if not fundamentals:
            continue

        eps = fundamentals.get("eps")
        bvps = fundamentals.get("book_value_per_share")
        roe = fundamentals.get("roe")

        pe = price / eps if eps is not None and pd.notna(eps) and eps > 0 else None
        pb = price / bvps if bvps is not None and pd.notna(bvps) and bvps > 0 else None

        rows.append({
            "ticker": ticker,
            "price": price,
            "price_date": price_date,
            "fiscal_year_end": fundamentals.get("fiscal_year_end"),
            "filed_date": fundamentals.get("filed_date"),
            "eps": eps,
            "book_value_per_share": bvps,
            "roe": roe,
            "pe": pe,
            "pb": pb,
        })

    return pd.DataFrame(rows)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20, help="Cuántas empresas mostrar")
    parser.add_argument("--min-roe", type=float, default=0.10, help="ROE mínimo para considerar 'calidad' (0.10 = 10%%)")
    args = parser.parse_args()

    tickers = load_tickers()

    print(f"Analizando {len(tickers)} tickers...")

    table = build_screener_table(tickers)

    print(f"Con datos completos (precio + fundamentales): {len(table)} de {len(tickers)}")

    quality_table = table[
        (table["roe"].notna()) & (table["roe"] >= args.min_roe)
        & (table["pe"].notna()) & (table["pe"] > 0)
        & (table["pb"].notna()) & (table["pb"] > 0)
    ].copy()

    print(f"Con ROE >= {args.min_roe:.0%} y P/E, P/B calculables: {len(quality_table)}")

    quality_table["pe_rank"] = quality_table["pe"].rank(pct=True)
    quality_table["pb_rank"] = quality_table["pb"].rank(pct=True)
    quality_table["value_score"] = (quality_table["pe_rank"] + quality_table["pb_rank"]) / 2

    quality_table = quality_table.sort_values("value_score")

    top = quality_table.head(args.top)

    print()
    print("=" * 100)
    print(f"TOP {args.top} — MÁS BARATAS (P/E y P/B más bajos) CON ROE >= {args.min_roe:.0%}")
    print("=" * 100)
    print(f"{'Ticker':<8} | {'Precio':>10} | {'P/E':>7} | {'P/B':>7} | {'ROE':>7} | {'10-K presentado':>16}")
    print("-" * 100)

    for _, row in top.iterrows():
        filed = row["filed_date"].strftime("%Y-%m-%d") if pd.notna(row["filed_date"]) else "N/A"
        print(
            f"{row['ticker']:<8} | {row['price']:>10.2f} | {row['pe']:>7.2f} | "
            f"{row['pb']:>7.2f} | {row['roe']:>6.1%} | {filed:>16}"
        )

    output_path = "data/value_quality_screener_report.csv"
    quality_table.sort_values("value_score").to_csv(output_path, index=False)

    print()
    print(f"Informe completo (todas las que cumplen el filtro) guardado en: {output_path}")
    print()
    print("=" * 100)
    print("CÓMO LEER ESTO")
    print("=" * 100)
    print(
        "P/E y P/B bajos = la acción cotiza barata respecto a su beneficio y a\n"
        "su valor contable. ROE alto = la empresa es rentable de verdad, no\n"
        "solo barata. El 'value_score' es el promedio simple de en qué percentil\n"
        "cae cada empresa en P/E y P/B (0 = más barata de todas, 1 = más cara) —\n"
        "no hay ningún modelo detrás, es aritmética directa y transparente.\n"
        "\n"
        "AVISO: esto es un punto de partida para tu propio análisis, no una\n"
        "recomendación de compra. Un P/E bajo a veces significa 'barata de\n"
        "verdad' y a veces significa 'el mercado sabe algo malo que tú no\n"
        "sabes todavía' — la herramienta no distingue entre ambos casos."
    )


if __name__ == "__main__":
    main()
