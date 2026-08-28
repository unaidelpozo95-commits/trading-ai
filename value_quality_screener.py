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

from ticker_universe import load_tickers

FUNDAMENTALS_DIR = "data/sec_fundamentals"
PRICE_DIR = "data/raw/yahoo"


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


def explain_pick(row: pd.Series, min_roe: float) -> str:
    """Explicación en lenguaje llano de por qué esta empresa aparece
    en el ranking — pura aritmética sobre los datos ya calculados,
    sin IA ni caja negra."""

    parts = []

    pe_pct = row["pe_rank"]
    pb_pct = row["pb_rank"]

    parts.append(
        f"P/E de {row['pe']:.1f} (más barata que el {(1 - pe_pct):.0%} de las "
        f"empresas del ranking, según este criterio)"
    )
    parts.append(
        f"P/B de {row['pb']:.1f} (más barata que el {(1 - pb_pct):.0%} en este criterio)"
    )

    roe_vs_min = row["roe"] - min_roe
    parts.append(
        f"ROE de {row['roe']:.1%} ({roe_vs_min:+.1%} respecto al mínimo exigido de {min_roe:.0%})"
    )

    # Identificar el motivo principal: el criterio donde destaca más
    # (percentil más bajo = más barata en ese criterio concreto).
    # Solo se afirma "destaca por X bajo" si de verdad está por debajo
    # de la mediana — si no, es más honesto decir que no destaca por
    # precio en ninguno de los dos criterios.
    if pe_pct < 0.5 or pb_pct < 0.5:
        if pe_pct <= pb_pct:
            main_reason = f"Destaca sobre todo por su P/E bajo ({row['pe']:.1f})"
        else:
            main_reason = f"Destaca sobre todo por su P/B bajo ({row['pb']:.1f})"
    else:
        main_reason = (
            "No destaca por tener un precio especialmente bajo en P/E ni P/B "
            "respecto al resto del universo, pero es de las mejores opciones "
            "entre las que cumplen el filtro de calidad"
        )

    return f"{main_reason}. " + "; ".join(parts) + "."


def write_readable_report(top: pd.DataFrame, min_roe: float, output_path: str) -> None:
    """Informe legible en texto plano, con una explicación por empresa
    — pensado para leer de un vistazo, no para procesar con código."""

    lines = []
    lines.append("INFORME DE VALOR + CALIDAD")
    lines.append("=" * 70)
    lines.append("")

    for rank, (_, row) in enumerate(top.iterrows(), 1):
        filed = row["filed_date"].strftime("%Y-%m-%d") if pd.notna(row["filed_date"]) else "N/A"
        lines.append(f"{rank}. {row['ticker']} — Precio: {row['price']:.2f}")
        lines.append(f"   P/E: {row['pe']:.2f} | P/B: {row['pb']:.2f} | ROE: {row['roe']:.1%} | Último 10-K: {filed}")
        lines.append(f"   {explain_pick(row, min_roe)}")
        lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


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

    top = top.copy()
    top["explicacion"] = top.apply(lambda row: explain_pick(row, args.min_roe), axis=1)

    print()
    print("=" * 100)
    print(f"TOP {args.top} — MÁS BARATAS (P/E y P/B más bajos) CON ROE >= {args.min_roe:.0%}")
    print("=" * 100)

    for rank, (_, row) in enumerate(top.iterrows(), 1):
        filed = row["filed_date"].strftime("%Y-%m-%d") if pd.notna(row["filed_date"]) else "N/A"
        print()
        print(f"{rank}. {row['ticker']} — Precio: {row['price']:.2f} | P/E: {row['pe']:.2f} | "
              f"P/B: {row['pb']:.2f} | ROE: {row['roe']:.1%} | Último 10-K: {filed}")
        print(f"   {row['explicacion']}")

    output_path = "data/value_quality_screener_report.csv"
    quality_table_with_explain = quality_table.copy()
    quality_table_with_explain["explicacion"] = quality_table_with_explain.apply(
        lambda row: explain_pick(row, args.min_roe), axis=1
    )
    quality_table_with_explain.sort_values("value_score").to_csv(output_path, index=False)

    readable_path = "data/value_quality_screener_report.txt"
    write_readable_report(top, args.min_roe, readable_path)

    print()
    print(f"Informe completo (CSV, todas las que cumplen el filtro): {output_path}")
    print(f"Informe legible (top {args.top}, con explicación de cada una): {readable_path}")
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
