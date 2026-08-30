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

# Sufijos de bolsa de Yahoo Finance que usan punto (ej. "14D.AX",
# "0001.HK") — si el ticker termina en uno de estos, el punto NO se
# toca. Si no coincide con ninguno, se asume que es un caso tipo
# "BRK.B" (acciones de EEUU con clase) y el punto se convierte en
# guion, que es lo que espera yfinance para esos casos.
KNOWN_EXCHANGE_SUFFIXES = {
    "AX",  # Australia (ASX)
    "HK",  # Hong Kong
    "DE",  # Alemania (Xetra/Frankfurt)
    "F",   # Frankfurt (parqué, no Xetra)
    "T",   # Japón (Tokyo Stock Exchange)
    "L",   # Londres
    "PA",  # París
    "MI",  # Milán
    "MC",  # Madrid
    "AS",  # Ámsterdam
    "SW",  # Suiza
    "TO",  # Toronto
    "SI",  # Singapur
    "KS",  # Corea del Sur
    "SS",  # Shanghai
    "SZ",  # Shenzhen
}


def _fix_ticker(ticker: str) -> str:
    """Convierte el punto en guion SOLO si no es un sufijo de bolsa
    conocido — así "BRK.B" -> "BRK-B" pero "14D.AX" se queda igual."""

    if "." not in ticker:
        return ticker

    prefix, suffix = ticker.rsplit(".", 1)

    if suffix.upper() in KNOWN_EXCHANGE_SUFFIXES:
        return ticker

    return ticker.replace(".", "-")


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
        tickers = [_fix_ticker(t.strip()) for t in tickers]

        print(f"  {os.path.basename(path)}: {len(tickers)} tickers")

        all_tickers.extend(tickers)

    unique_tickers = list(dict.fromkeys(all_tickers))

    print(f"Universo total (sin duplicados): {len(unique_tickers)} tickers "
          f"desde {len(csv_paths)} archivo(s) en {tickers_dir}/")

    return unique_tickers


def load_ticker_names(tickers_dir: str = TICKERS_DIR) -> dict:
    """Devuelve {ticker: nombre_empresa} para los CSV que tengan una
    columna 'Name' o 'name'. Si un ticker aparece en varios archivos
    con nombres distintos, se queda con el del primer archivo (por
    orden alfabético) que lo traiga."""

    csv_paths = sorted(glob.glob(os.path.join(tickers_dir, "*.csv")))

    names = {}

    for path in csv_paths:

        df = pd.read_csv(path)

        ticker_col = "ticker" if "ticker" in df.columns else ("Symbol" if "Symbol" in df.columns else None)
        name_col = "Name" if "Name" in df.columns else ("name" if "name" in df.columns else None)

        if ticker_col is None or name_col is None:
            continue

        for _, row in df.iterrows():
            ticker = _fix_ticker(str(row[ticker_col]).strip())
            name = row[name_col]
            if ticker not in names and pd.notna(name):
                names[ticker] = str(name).strip()

    return names
