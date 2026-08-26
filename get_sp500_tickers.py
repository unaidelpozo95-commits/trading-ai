"""
Obtiene la lista de tickers del S&P 500 desde Wikipedia y la guarda
en data/sp500_tickers.csv, con los símbolos ya adaptados al formato
que espera yfinance (ej. BRK.B -> BRK-B).
"""

import os

import pandas as pd


WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def main():

    print(f"Descargando lista de tickers desde {WIKI_URL}...")

    tables = pd.read_html(WIKI_URL)
    sp500_table = tables[0]

    tickers = sp500_table["Symbol"].tolist()

    # yfinance usa guion en vez de punto (BRK.B -> BRK-B)
    tickers = [t.replace(".", "-") for t in tickers]

    print(f"Encontrados {len(tickers)} tickers.")

    os.makedirs("data", exist_ok=True)

    df = pd.DataFrame({"ticker": tickers})
    df.to_csv("data/sp500_tickers.csv", index=False)

    print("Guardado en: data/sp500_tickers.csv")
    print()
    print("Primeros 10:", tickers[:10])


if __name__ == "__main__":
    main()
