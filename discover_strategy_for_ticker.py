"""
Descubre y guarda la estrategia para uno o varios tickers nuevos.

USO:
    python discover_strategy_for_ticker.py AAPL MSFT GOOGL
    python discover_strategy_for_ticker.py NVDA --force   (repite aunque ya exista)
    python discover_strategy_for_ticker.py --from-file data/sp500_tickers.csv

Si no se pasan tickers, usa TICKERS_TO_DISCOVER de abajo.

Esto solo hace falta ejecutarlo cuando añades un ticker NUEVO al
universo — el resultado queda guardado en data/strategies/{TICKER}.json
y de ahí lo leerá el scanner (o cualquier otro script) sin tener que
repetir la búsqueda.
"""

import sys

import pandas as pd

from src.research.strategy_discovery import discover_best_strategy
from src.research.strategy_store import has_strategy, save_strategy


TICKERS_TO_DISCOVER = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


def main():

    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    if "--from-file" in args:
        idx = args.index("--from-file")
        file_path = args[idx + 1]
        tickers_df = pd.read_csv(file_path)
        tickers = tickers_df["ticker"].tolist()
        print(f"Leyendo {len(tickers)} tickers desde {file_path}")
    else:
        tickers = args if args else TICKERS_TO_DISCOVER

    print(f"Descubriendo estrategia para {len(tickers)} tickers")
    if force:
        print("(--force: se repite el descubrimiento aunque ya exista un resultado guardado)")

    validated_count = 0

    for ticker in tickers:

        if not force and has_strategy(ticker):
            print(f"{ticker}: ya tiene estrategia guardada, se omite (usa --force para repetir)")
            continue

        try:
            result = discover_best_strategy(ticker, verbose=True)
        except Exception as e:
            print(f"{ticker}: ERROR ({e}), se omite")
            continue

        save_strategy(ticker, result)

        if result.get("validated"):
            validated_count += 1

    print()
    print(f"Listo. {validated_count} tickers validados en este pase.")


if __name__ == "__main__":
    main()
