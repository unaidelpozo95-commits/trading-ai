"""
Carga de precios en bruto con validación de calidad integrada.

Pensado para los scripts de investigación (research/, src/research/),
que hasta ahora leían el parquet directamente con pd.read_parquet sin
pasar por DataValidator — a diferencia del pipeline de producción
(update_prices_daily.py), que sí valida cada ticker al actualizarlo.

Uso:
    from src.data.loader import load_and_validate

    data = load_and_validate("AAPL")
"""

import os

import pandas as pd

from src.data.validator import DataValidator


PRICE_DIR = "data/raw/yahoo"

_validator = DataValidator()


def load_and_validate(ticker: str, base_dir: str = PRICE_DIR, verbose: bool = True) -> pd.DataFrame:
    """Lee el parquet de un ticker y lo valida con DataValidator.

    No bloquea nada — esto es investigación, no producción: si los
    datos no pasan la validación, se imprime un aviso claro (qué
    check falló) y se devuelve el DataFrame igualmente, para que
    quien esté investigando decida si le afecta a su análisis o no.
    """

    path = os.path.join(base_dir, f"{ticker}.parquet")
    data = pd.read_parquet(path)

    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index)

    report = _validator.validate(data, ticker=ticker)

    if not report.is_valid and verbose:
        problems = []
        if report.duplicate_dates:
            problems.append(f"{report.duplicate_dates} fechas duplicadas")
        if not report.chronological:
            problems.append("fechas no ordenadas cronológicamente")
        if report.missing_values:
            problems.append(f"{report.missing_values} valores ausentes")
        if report.invalid_prices:
            problems.append(f"{report.invalid_prices} precios inválidos (<=0)")
        if report.invalid_ohlc:
            problems.append(f"{report.invalid_ohlc} filas con OHLC inconsistente")
        if report.invalid_volume:
            problems.append(f"{report.invalid_volume} volúmenes negativos")

        print(f"AVISO calidad de datos [{ticker}]: {'; '.join(problems)}")

    return data
