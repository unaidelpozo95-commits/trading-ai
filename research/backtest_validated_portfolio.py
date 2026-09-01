"""
Backtest real de la cartera de tickers validados por el S&P 500 scan.

Reconstruye la señal de cada ticker usando su receta y parámetros
propios descubiertos (no una señal uniforme), y los mete todos juntos
en el motor multi-activo — el mismo tratamiento riguroso que le dimos
a la reversión cross-sectional antes de creérnosla.
"""

import pandas as pd

from src.research.strategy_discovery import RECIPES, load_ticker_for_discovery
from src.research.strategy_store import load_all_validated_strategies
from src.backtest.multi_asset import MultiAssetBacktester
from src.backtest.metrics import compute_metrics


INITIAL_CAPITAL = 100_000.0

STOP_PCT = 0.05
TARGET_PCT = 0.10
MAX_DAYS = 20


print()
print("Cargando estrategias validadas...")

validated = load_all_validated_strategies()

print(f"{len(validated)} tickers validados encontrados.")

ticker_data = {}
signals = {}

for ticker, strategy in validated.items():

    try:
        df = load_ticker_for_discovery(ticker)
    except Exception as e:
        print(f"{ticker}: no se pudo cargar ({e}), se omite")
        continue

    recipe_name = strategy["recipe"]
    params = strategy["params"]

    recipe_func = RECIPES[recipe_name]["func"]
    signal = recipe_func(df, **params)

    ticker_data[ticker] = df
    signals[ticker] = signal

print(f"Señales construidas para {len(ticker_data)} tickers.")


def filter_by_year(data, signals, condition):
    sub_data, sub_signals = {}, {}
    for t in data:
        mask = condition(data[t].index)
        sub_data[t] = data[t][mask]
        sub_signals[t] = signals[t][mask]
    return sub_data, sub_signals


dev_data, dev_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year <= 2022)
oos_data, oos_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year >= 2023)


def run_and_report(label, data_subset, signals_subset):

    bt = MultiAssetBacktester(
        initial_capital=INITIAL_CAPITAL,
        stop_pct=STOP_PCT,
        target_pct=TARGET_PCT,
        max_days=MAX_DAYS,
    )

    result = bt.run(data_subset, signals_subset)
    metrics = compute_metrics(result.equity_curve, result.trades, INITIAL_CAPITAL)

    print()
    print("=" * 70)
    print(label)
    print("=" * 70)
    print(f"Trades:          {metrics['n_trades']}")
    print(f"Total return:    {metrics['total_return']:>7.2%}")
    if metrics["cagr"] is not None:
        print(f"CAGR:            {metrics['cagr']:>7.2%}")
    if metrics["sharpe"] is not None:
        print(f"Sharpe:          {metrics['sharpe']:>7.2f}")
    print(f"Max drawdown:    {metrics['max_drawdown']:>7.2%}")
    if metrics["win_rate"] is not None:
        print(f"Win rate:        {metrics['win_rate']:>7.1%}")
    print(f"Exit reasons:    {metrics['exit_reasons']}")

    if result.trades:
        trade_df = pd.DataFrame([
            {"symbol": t.symbol, "pnl": t.pnl, "return_pct": t.return_pct}
            for t in result.trades
        ])
        by_symbol = trade_df.groupby("symbol").agg(
            trades=("pnl", "count"),
            total_pnl=("pnl", "sum"),
        ).sort_values("total_pnl", ascending=False)

        print()
        print("Top 10 por PnL:")
        print(by_symbol.head(10).to_string())
        print()
        print("Bottom 10 por PnL:")
        print(by_symbol.tail(10).to_string())

    return result, metrics


full_result, full_metrics = run_and_report("FULL SAMPLE — CARTERA VALIDADA (S&P 500 scan)", ticker_data, signals)
run_and_report("PERÍODO DE DESCUBRIMIENTO — hasta 2022 (usado para seleccionar, NO es una prueba independiente)", dev_data, dev_signals)
run_and_report("HOLDOUT REAL — 2023 en adelante (nunca visto por la selección, esta SÍ es la prueba honesta)", oos_data, oos_signals)


trade_log = pd.DataFrame([
    {
        "symbol": t.symbol,
        "entry_date": t.entry_date,
        "exit_date": t.exit_date,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "return_pct": t.return_pct,
        "pnl": t.pnl,
        "exit_reason": t.exit_reason,
    }
    for t in full_result.trades
])

trade_log.to_csv("data/backtest_validated_portfolio_trades.csv", index=False)

print()
print("Trade log guardado en: data/backtest_validated_portfolio_trades.csv")
print()
print("NOTA: stop/target/max_days aquí son genéricos, no optimizados para")
print("esta cartera. Si el resultado es prometedor, el siguiente paso sería")
print("un barrido de sensibilidad específico, igual que hicimos con AAPL y")
print("con la reversión, antes de dar esto por bueno de verdad.")
