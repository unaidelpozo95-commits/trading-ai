"""
Backtest real de trend-following.

Señal: distance_sma_200 >= 5% (tendencia alcista confirmada, no solo
rozando la SMA200). A diferencia del momentum/reversión, el
trend-following clásico no usa un stop ajustado ni un target fijo —
se mantiene la posición mientras dura la tendencia. Como nuestro
motor de backtest está pensado para stop/target/max_days, lo
aproximamos así:
  - stop ANCHO (15%) — protección real ante un giro de tendencia,
    no un ruido normal dentro de ella.
  - target prácticamente DESACTIVADO (50%) — igual que hicimos en el
    análisis de holding period de AAPL, para que la salida real la
    controle max_days, no un techo artificial.
  - max_days LARGO — barrido en 60/90/120/150 días, acorde a lo que
    vimos en el análisis de ranking (el efecto solo aparecía a 120d).
"""

import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.multi_asset import MultiAssetBacktester
from src.backtest.metrics import compute_metrics


TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

TREND_THRESHOLD = 0.05

INITIAL_CAPITAL = 100_000.0
STOP_PCT = 0.15
TARGET_PCT = 0.50

MAX_DAYS_LIST = [60, 90, 120, 150]


def load_ticker(ticker: str) -> pd.DataFrame:
    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")
    engine = FeatureEngine()
    df = engine.build(data)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df


print()
print("Cargando universo:", TICKERS)

ticker_data = {t: load_ticker(t) for t in TICKERS}

signals = {}
for t in TICKERS:
    df = ticker_data[t]
    signals[t] = df["distance_sma_200"] >= TREND_THRESHOLD


def filter_by_year(data, signals, condition):
    sub_data, sub_signals = {}, {}
    for t in data:
        mask = condition(data[t].index)
        sub_data[t] = data[t][mask]
        sub_signals[t] = signals[t][mask]
    return sub_data, sub_signals


dev_data, dev_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year <= 2022)
oos_data, oos_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year >= 2023)


def basket_buy_and_hold_equity(data, dates, initial_capital):
    per_ticker_capital = initial_capital / len(TICKERS)
    entry_prices = {t: data[t].loc[dates[0], "Open"] for t in TICKERS}
    shares = {t: per_ticker_capital / entry_prices[t] for t in TICKERS}
    equity = {}
    for date in dates:
        value = sum(shares[t] * data[t].loc[date, "Close"] for t in TICKERS if date in data[t].index)
        equity[date] = value
    return pd.Series(equity).sort_index()


common_dates = None
for df in ticker_data.values():
    idx = set(df.index)
    common_dates = idx if common_dates is None else common_dates & idx
common_dates = sorted(common_dates)

dev_dates = [d for d in common_dates if d.year <= 2022]
oos_dates = [d for d in common_dates if d.year >= 2023]

buyhold_metrics = {}
for label, dates_subset in [("dev", dev_dates), ("oos", oos_dates)]:
    bh_equity = basket_buy_and_hold_equity(ticker_data, dates_subset, INITIAL_CAPITAL)
    buyhold_metrics[label] = compute_metrics(bh_equity, [], INITIAL_CAPITAL)

print()
print(f"Referencia Buy&Hold cesta — Dev Sharpe: {buyhold_metrics['dev']['sharpe']:.2f} | "
      f"OOS Sharpe: {buyhold_metrics['oos']['sharpe']:.2f}")


def run_backtest(data_subset, signals_subset, max_days):
    bt = MultiAssetBacktester(
        initial_capital=INITIAL_CAPITAL,
        stop_pct=STOP_PCT,
        target_pct=TARGET_PCT,
        max_days=max_days,
    )
    result = bt.run(data_subset, signals_subset)
    metrics = compute_metrics(result.equity_curve, result.trades, INITIAL_CAPITAL)
    return metrics, result


print()
print("=" * 100)
print(f"TREND-FOLLOWING — señal distance_sma_200>={TREND_THRESHOLD:.0%}, stop={STOP_PCT:.0%}, target~desactivado")
print("=" * 100)
print(f"{'MaxDays':>8} | {'DevN':>6} {'DevSharpe':>10} {'DevRet':>9} {'DevMaxDD':>9} | "
      f"{'OOSN':>6} {'OOSSharpe':>10} {'OOSRet':>9} {'OOSMaxDD':>9}")
print("-" * 100)

results = []

for max_days in MAX_DAYS_LIST:

    dev_metrics, _ = run_backtest(dev_data, dev_signals, max_days)
    oos_metrics, _ = run_backtest(oos_data, oos_signals, max_days)

    dev_sharpe_str = f"{dev_metrics['sharpe']:>10.2f}" if dev_metrics["sharpe"] is not None else "       N/A"
    oos_sharpe_str = f"{oos_metrics['sharpe']:>10.2f}" if oos_metrics["sharpe"] is not None else "       N/A"

    print(
        f"{max_days:>7}d | {dev_metrics['n_trades']:>6} {dev_sharpe_str} "
        f"{dev_metrics['total_return']:>8.2%} {dev_metrics['max_drawdown']:>8.2%} | "
        f"{oos_metrics['n_trades']:>6} {oos_sharpe_str} "
        f"{oos_metrics['total_return']:>8.2%} {oos_metrics['max_drawdown']:>8.2%}"
    )

    results.append({
        "max_days": max_days,
        "dev_trades": dev_metrics["n_trades"],
        "oos_trades": oos_metrics["n_trades"],
        "dev_sharpe": dev_metrics["sharpe"],
        "oos_sharpe": oos_metrics["sharpe"],
        "dev_return": dev_metrics["total_return"],
        "oos_return": oos_metrics["total_return"],
        "dev_max_dd": dev_metrics["max_drawdown"],
        "oos_max_dd": oos_metrics["max_drawdown"],
        "beats_buyhold_both": (
            dev_metrics["sharpe"] is not None and oos_metrics["sharpe"] is not None
            and dev_metrics["sharpe"] > buyhold_metrics["dev"]["sharpe"]
            and oos_metrics["sharpe"] > buyhold_metrics["oos"]["sharpe"]
        ),
    })


results_df = pd.DataFrame(results)
results_df.to_csv("data/backtest_trend_following.csv", index=False)

beats_both = results_df[results_df["beats_buyhold_both"]]

print()
print(f"Combinaciones que baten el Sharpe de buy&hold en AMBOS períodos: "
      f"{len(beats_both)} de {len(results_df)}")

print()
print("Resultados completos guardados en: data/backtest_trend_following.csv")
