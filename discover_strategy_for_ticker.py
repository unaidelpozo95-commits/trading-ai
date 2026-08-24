"""
Descubre y guarda la estrategia para uno o varios tickers nuevos.

USO:
    python discover_strategy_for_ticker.py AAPL MSFT GOOGL
    python discover_strategy_for_ticker.py NVDA --force   (repite aunque ya exista)

Si no se pasan tickers, usa TICKERS_TO_DISCOVER de abajo.

Esto solo hace falta ejecutarlo cuando añades un ticker NUEVO al
universo — el resultado queda guardado en data/strategies/{TICKER}.json
y de ahí lo leerá el scanner (o cualquier otro script) sin tener que
repetir la búsqueda.
"""

import sys

from src.research.strategy_discovery import discover_best_strategy
from src.research.strategy_store import has_strategy, save_strategy


TICKERS_TO_DISCOVER = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO"]


def main():

    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    tickers = args if args else TICKERS_TO_DISCOVER

    print(f"Descubriendo estrategia para: {tickers}")
    if force:
        print("(--force: se repite el descubrimiento aunque ya exista un resultado guardado)")

    for ticker in tickers:

        if not force and has_strategy(ticker):
            print(f"{ticker}: ya tiene estrategia guardada, se omite (usa --force para repetir)")
            continue

        print()
        print(f"--- Descubriendo {ticker} ---")

        result = discover_best_strategy(ticker)

        save_strategy(ticker, result)

        print(f"{ticker}: guardado en data/strategies/{ticker}.json")

    print()
    print("Listo.")


if __name__ == "__main__":
    main()
