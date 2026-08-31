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
import html
import os

import pandas as pd

from ticker_universe import load_tickers, load_ticker_names, load_ticker_sectors

FUNDAMENTALS_DIR = "data/sec_fundamentals"
PRICE_DIR = "data/raw/yahoo"

MIN_SECTOR_SAMPLE = 5  # tickers mínimos en un sector para fiarse de su P/E mediano
N_MOVERS = 5           # top N subidas / N caídas del día


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


def build_screener_table(tickers: list, ticker_names: dict, ticker_sectors: dict) -> pd.DataFrame:

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
            "company_name": ticker_names.get(ticker, ticker),
            "sector": ticker_sectors.get(ticker),
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


def compute_sector_median_pe(table: pd.DataFrame, min_sample: int) -> pd.Series:
    """P/E mediano por sector, calculado sobre TODO el universo con
    datos válidos (no solo las que pasan el filtro de calidad) — así
    el benchmark es más representativo. Sectores con menos de
    min_sample empresas se descartan (una mediana de 1-2 empresas no
    significa nada)."""

    valid = table.dropna(subset=["pe", "sector"])
    valid = valid[valid["pe"] > 0]

    counts = valid.groupby("sector")["pe"].count()
    medians = valid.groupby("sector")["pe"].median()

    return medians[counts >= min_sample]


def add_target_price(df: pd.DataFrame, sector_median_pe: pd.Series) -> pd.DataFrame:
    """Añade target_price (P/E mediano del sector x EPS de la empresa)
    y vs_target_pct (cuánto por encima/debajo cotiza respecto a ese
    precio). Es una referencia de valoración RELATIVA al sector, no
    un valor "justo" absoluto — no tiene en cuenta tipos de interés,
    ciclo económico, ni nada específico de la empresa más allá de su
    beneficio por acción."""

    df = df.copy()

    def _target(row):
        sector_pe = sector_median_pe.get(row["sector"])
        if sector_pe is None or row["eps"] is None or pd.isna(row["eps"]) or row["eps"] <= 0:
            return None
        return sector_pe * row["eps"]

    df["target_price"] = df.apply(_target, axis=1)
    df["vs_target_pct"] = df.apply(
        lambda row: (row["target_price"] / row["price"] - 1) if pd.notna(row["target_price"]) else None,
        axis=1,
    )

    return df


MIN_PRICE_FOR_MOVERS = 5.0  # excluye penny stocks: splits inversos y precios
                             # cercanos a cero producen "% de cambio" absurdos
                             # que no reflejan un movimiento de mercado real


def compute_top_movers(tickers: list, ticker_names: dict, n: int = N_MOVERS) -> tuple:
    """Top N subidas y top N caídas del día, sobre TODO el universo
    cargado (no solo las que pasan el filtro de calidad) — es una
    foto de mercado, no un filtro de valor.

    Usa el precio AJUSTADO (Adj Close, corrige splits/dividendos) en
    vez del precio en bruto — si no, un split inverso de una penny
    stock aparece como una "subida" del 1000% que no es real.
    También excluye acciones por debajo de MIN_PRICE_FOR_MOVERS: con
    precios cercanos a cero, hasta el movimiento más pequeño en
    términos absolutos se convierte en un porcentaje descontrolado."""

    changes = []

    for ticker in tickers:

        path = os.path.join(PRICE_DIR, f"{ticker}.parquet")

        if not os.path.exists(path):
            continue

        df = pd.read_parquet(path)

        if len(df) < 2:
            continue

        close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        last_two = df[close_col].iloc[-2:]

        if last_two.iloc[-2] == 0 or pd.isna(last_two.iloc[-2]) or pd.isna(last_two.iloc[-1]):
            continue

        if last_two.iloc[-1] < MIN_PRICE_FOR_MOVERS:
            continue

        change_pct = (last_two.iloc[-1] / last_two.iloc[-2]) - 1

        changes.append({
            "ticker": ticker,
            "company_name": ticker_names.get(ticker, ticker),
            "price": last_two.iloc[-1],
            "change_pct": change_pct,
        })

    changes_df = pd.DataFrame(changes)

    if changes_df.empty:
        return changes_df.copy(), changes_df.copy()

    gainers = changes_df.sort_values("change_pct", ascending=False).head(n).reset_index(drop=True)
    losers = changes_df.sort_values("change_pct", ascending=True).head(n).reset_index(drop=True)

    return gainers, losers


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

    if pd.notna(row.get("vs_target_pct")):
        parts.append(
            f"precio objetivo por P/E mediano de su sector: {row['target_price']:.2f} "
            f"({row['vs_target_pct']:+.1%} respecto al precio actual)"
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


def write_readable_report(top: pd.DataFrame, gainers: pd.DataFrame, losers: pd.DataFrame,
                           min_roe: float, output_path: str) -> None:
    """Informe legible en texto plano, con una explicación por empresa
    — pensado para leer de un vistazo, no para procesar con código."""

    lines = []
    lines.append("INFORME DE VALOR + CALIDAD")
    lines.append("=" * 70)
    lines.append("")

    if not gainers.empty or not losers.empty:
        lines.append("TOP MOVERS DEL DÍA")
        lines.append("-" * 70)
        lines.append("Mayores subidas:")
        for _, row in gainers.iterrows():
            lines.append(f"  {row['ticker']} ({row['company_name']}): {row['change_pct']:+.2%} -> {row['price']:.2f}")
        lines.append("Mayores caídas:")
        for _, row in losers.iterrows():
            lines.append(f"  {row['ticker']} ({row['company_name']}): {row['change_pct']:+.2%} -> {row['price']:.2f}")
        lines.append("")
        lines.append("=" * 70)
        lines.append("")

    for rank, (_, row) in enumerate(top.iterrows(), 1):
        filed = row["filed_date"].strftime("%Y-%m-%d") if pd.notna(row["filed_date"]) else "N/A"
        lines.append(f"{rank}. {row['ticker']} ({row['company_name']}) — Precio: {row['price']:.2f}")
        lines.append(f"   P/E: {row['pe']:.2f} | P/B: {row['pb']:.2f} | ROE: {row['roe']:.1%} | Último 10-K: {filed}")
        lines.append(f"   {explain_pick(row, min_roe)}")
        lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


TEMPLATES_DIR = "templates"


def write_html_report(top: pd.DataFrame, gainers: pd.DataFrame, losers: pd.DataFrame,
                       min_roe: float, output_path: str) -> None:
    """Informe en HTML, construido a partir de las plantillas en
    templates/ (report_shell.html, report_row.html y
    movers_row.html) — edítalas directamente para cambiar colores,
    textos o estructura sin tocar este script."""

    from datetime import datetime

    today = datetime.now().strftime("%d/%m/%Y")

    with open(os.path.join(TEMPLATES_DIR, "report_shell.html")) as f:
        shell = f.read()

    with open(os.path.join(TEMPLATES_DIR, "report_row.html")) as f:
        row_template = f.read()

    with open(os.path.join(TEMPLATES_DIR, "movers_row.html")) as f:
        movers_row_template = f.read()

    rows_html = []

    for rank, (_, row) in enumerate(top.iterrows(), 1):

        bg = "#f8f9fa" if rank % 2 == 0 else "#ffffff"
        roe_color = "#1a7f37" if row["roe"] >= min_roe * 1.5 else "#2d2d2d"

        if pd.notna(row.get("vs_target_pct")):
            target_str = f"{row['target_price']:.2f}"
            vs_target_str = f"{row['vs_target_pct']:+.1%}"
            vs_target_color = "#1a7f37" if row["vs_target_pct"] > 0 else "#c0392b"
        else:
            target_str = "N/A"
            vs_target_str = "N/A"
            vs_target_color = "#6b7280"

        row_html = (
            row_template
            .replace("{{BG_COLOR}}", bg)
            .replace("{{RANK}}", str(rank))
            .replace("{{TICKER}}", html.escape(str(row["ticker"])))
            .replace("{{COMPANY_NAME}}", html.escape(str(row["company_name"])))
            .replace("{{PRICE}}", f"{row['price']:.2f}")
            .replace("{{PE}}", f"{row['pe']:.1f}")
            .replace("{{PB}}", f"{row['pb']:.1f}")
            .replace("{{ROE}}", f"{row['roe']:.1%}")
            .replace("{{ROE_COLOR}}", roe_color)
            .replace("{{TARGET_PRICE}}", target_str)
            .replace("{{VS_TARGET}}", vs_target_str)
            .replace("{{VS_TARGET_COLOR}}", vs_target_color)
            .replace("{{EXPLANATION}}", html.escape(explain_pick(row, min_roe)))
        )

        rows_html.append(row_html)

    def build_movers_html(movers_df, is_gainer):
        parts = []
        for _, row in movers_df.iterrows():
            color = "#1a7f37" if is_gainer else "#c0392b"
            parts.append(
                movers_row_template
                .replace("{{TICKER}}", html.escape(str(row["ticker"])))
                .replace("{{COMPANY_NAME}}", html.escape(str(row["company_name"])))
                .replace("{{PRICE}}", f"{row['price']:.2f}")
                .replace("{{CHANGE_PCT}}", f"{row['change_pct']:+.2%}")
                .replace("{{CHANGE_COLOR}}", color)
            )
        return "".join(parts)

    gainers_html = build_movers_html(gainers, is_gainer=True)
    losers_html = build_movers_html(losers, is_gainer=False)

    html_output = (
        shell
        .replace("{{HEADER_DATE}}", today)
        .replace("{{TOP_N}}", str(len(top)))
        .replace("{{MIN_ROE}}", f"{min_roe:.0%}")
        .replace("{{ROWS_HTML}}", "".join(rows_html))
        .replace("{{GAINERS_HTML}}", gainers_html)
        .replace("{{LOSERS_HTML}}", losers_html)
    )

    with open(output_path, "w") as f:
        f.write(html_output)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20, help="Cuántas empresas mostrar")
    parser.add_argument("--min-roe", type=float, default=0.10, help="ROE mínimo para considerar 'calidad' (0.10 = 10%%)")
    args = parser.parse_args()

    tickers = load_tickers()
    ticker_names = load_ticker_names()
    ticker_sectors = load_ticker_sectors()

    print(f"Analizando {len(tickers)} tickers...")

    table = build_screener_table(tickers, ticker_names, ticker_sectors)

    print(f"Con datos completos (precio + fundamentales): {len(table)} de {len(tickers)}")

    sector_median_pe = compute_sector_median_pe(table, MIN_SECTOR_SAMPLE)
    print(f"Sectores con muestra suficiente (>= {MIN_SECTOR_SAMPLE} empresas) para precio objetivo: {len(sector_median_pe)}")

    quality_table = table[
        (table["roe"].notna()) & (table["roe"] >= args.min_roe)
        & (table["pe"].notna()) & (table["pe"] > 0)
        & (table["pb"].notna()) & (table["pb"] > 0)
    ].copy()

    print(f"Con ROE >= {args.min_roe:.0%} y P/E, P/B calculables: {len(quality_table)}")

    quality_table["pe_rank"] = quality_table["pe"].rank(pct=True)
    quality_table["pb_rank"] = quality_table["pb"].rank(pct=True)
    quality_table["value_score"] = (quality_table["pe_rank"] + quality_table["pb_rank"]) / 2

    quality_table = add_target_price(quality_table, sector_median_pe)

    quality_table = quality_table.sort_values("value_score")

    top = quality_table.head(args.top)

    top = top.copy()
    top["explicacion"] = top.apply(lambda row: explain_pick(row, args.min_roe), axis=1)

    print()
    print("=" * 100)
    print("TOP MOVERS DEL DÍA")
    print("=" * 100)

    gainers, losers = compute_top_movers(tickers, ticker_names, N_MOVERS)

    print(f"Mayores subidas (top {N_MOVERS}):")
    for _, row in gainers.iterrows():
        print(f"  {row['ticker']} ({row['company_name']}): {row['change_pct']:+.2%} -> {row['price']:.2f}")
    print(f"Mayores caídas (top {N_MOVERS}):")
    for _, row in losers.iterrows():
        print(f"  {row['ticker']} ({row['company_name']}): {row['change_pct']:+.2%} -> {row['price']:.2f}")

    print()
    print("=" * 100)
    print(f"TOP {args.top} — MÁS BARATAS (P/E y P/B más bajos) CON ROE >= {args.min_roe:.0%}")
    print("=" * 100)

    for rank, (_, row) in enumerate(top.iterrows(), 1):
        filed = row["filed_date"].strftime("%Y-%m-%d") if pd.notna(row["filed_date"]) else "N/A"
        print()
        print(f"{rank}. {row['ticker']} ({row['company_name']}) — Precio: {row['price']:.2f} | P/E: {row['pe']:.2f} | "
              f"P/B: {row['pb']:.2f} | ROE: {row['roe']:.1%} | Último 10-K: {filed}")
        print(f"   {row['explicacion']}")

    output_path = "data/value_quality_screener_report.csv"
    quality_table_with_explain = quality_table.copy()
    quality_table_with_explain["explicacion"] = quality_table_with_explain.apply(
        lambda row: explain_pick(row, args.min_roe), axis=1
    )
    quality_table_with_explain.sort_values("value_score").to_csv(output_path, index=False)

    readable_path = "data/value_quality_screener_report.txt"
    write_readable_report(top, gainers, losers, args.min_roe, readable_path)

    html_path = "data/value_quality_screener_report.html"
    write_html_report(top, gainers, losers, args.min_roe, html_path)

    print()
    print(f"Informe completo (CSV, todas las que cumplen el filtro): {output_path} ({len(quality_table)} filas)")
    print(f"Informe legible (top {args.top}, con explicación de cada una): {readable_path}")
    print(f"Informe HTML (para email): {html_path}")
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
        "El 'precio objetivo' es el P/E MEDIANO de las demás empresas del mismo\n"
        "sector, multiplicado por el beneficio por acción de la empresa. Es una\n"
        "referencia RELATIVA al sector, no un valor \"justo\" absoluto — no tiene\n"
        "en cuenta tipos de interés, ciclo económico, ni nada específico de la\n"
        "empresa más allá de su beneficio. Sectores con menos de "
        f"{MIN_SECTOR_SAMPLE} empresas con datos no tienen precio objetivo (muestra insuficiente).\n"
        "\n"
        "AVISO: esto es un punto de partida para tu propio análisis, no una\n"
        "recomendación de compra. Un P/E bajo a veces significa 'barata de\n"
        "verdad' y a veces significa 'el mercado sabe algo malo que tú no\n"
        "sabes todavía' — la herramienta no distingue entre ambos casos."
    )


if __name__ == "__main__":
    main()
