"""
Carga de universo de tickers — dinámica, desde data/tickers/.

Cualquier CSV que metas en data/tickers/ (con columna 'ticker' o
'Symbol') se carga automáticamente y se fusiona con el resto. Así
puedes tener data/tickers/sp500.csv, data/tickers/watchlist.csv,
data/tickers/europa.csv, etc. — todos los scripts del proyecto los
verán juntos, sin tocar código cada vez que añadas una lista nueva.

Import: from ticker_universe import load_tickers
"""

import glob
import os

import pandas as pd


TICKERS_DIR = "data/tickers"


def load_tickers(tickers_dir: str = TICKERS_DIR) -> list:
    """Lee todos los .csv de tickers_dir, extrae la columna de ticker
    de cada uno (acepta 'ticker' o 'Symbol'), arregla símbolos con
    punto (BRK.B -> BRK-B), fusiona y quita duplicados manteniendo el
    orden de aparición."""

    csv_paths = sorted(glob.glob(os.path.join(tickers_dir, "*.csv")))

    if not csv_paths:
        raise FileNotFoundError(
            f"No se encontró ningún CSV en {tickers_dir}/ — mete al menos uno "
            f"con una columna 'ticker' o 'Symbol'."
        )

    all_tickers = []

    for path in csv_paths:

        df = pd.read_csv(path)

        if "ticker" in df.columns:
            col = "ticker"
        elif "Symbol" in df.columns:
            col = "Symbol"
        else:
            print(f"AVISO: {path} no tiene columna 'ticker' ni 'Symbol', se omite")
            continue

        tickers = df[col].dropna().astype(str).tolist()
        tickers = [t.strip().replace(".", "-") for t in tickers]

        print(f"  {os.path.basename(path)}: {len(tickers)} tickers")

        all_tickers.extend(tickers)

    unique_tickers = list(dict.fromkeys(all_tickers))

    print(f"Universo total (sin duplicados): {len(unique_tickers)} tickers "
          f"desde {len(csv_paths)} archivo(s) en {tickers_dir}/")

    return unique_tickers
