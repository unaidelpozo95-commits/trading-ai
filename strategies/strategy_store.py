"""
Almacén de estrategias descubiertas por ticker.

El descubrimiento (strategy_discovery.py) es costoso — cientos de
combinaciones por ticker. Este módulo lo cachea en
data/strategies/{TICKER}.json, así que solo hace falta ejecutarlo
una vez por ticker nuevo. El scanner (futuro) y cualquier otro
script deberían leer de aquí, no volver a descubrir cada vez.
"""

import json
import os


STRATEGIES_DIR = "data/strategies"


def strategy_path(ticker: str) -> str:
    return os.path.join(STRATEGIES_DIR, f"{ticker}.json")


def has_strategy(ticker: str) -> bool:
    return os.path.exists(strategy_path(ticker))


def save_strategy(ticker: str, result: dict) -> None:

    os.makedirs(STRATEGIES_DIR, exist_ok=True)

    with open(strategy_path(ticker), "w") as f:
        json.dump(result, f, indent=2)


def load_strategy(ticker: str) -> dict | None:

    path = strategy_path(ticker)

    if not os.path.exists(path):
        return None

    with open(path) as f:
        return json.load(f)


def load_all_validated_strategies() -> dict:
    """Devuelve {ticker: strategy_dict} solo para los tickers con
    estrategia validada (validated=True)."""

    if not os.path.isdir(STRATEGIES_DIR):
        return {}

    result = {}

    for filename in os.listdir(STRATEGIES_DIR):
        if not filename.endswith(".json"):
            continue

        ticker = filename.replace(".json", "")
        strategy = load_strategy(ticker)

        if strategy and strategy.get("validated"):
            result[ticker] = strategy

    return result
