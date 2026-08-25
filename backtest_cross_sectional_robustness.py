import pandas as pd

from src.features.engine import FeatureEngine
from src.backtest.multi_asset import MultiAssetBacktester
from src.backtest.metrics import compute_metrics


# =============================================================
# UNIVERSE
# =============================================================

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "JNJ", "AVGO",
    "V", "MA", "UNH", "HD", "PG", "XOM", "CVX", "ABBV", "MRK", "LLY", "PEP", "KO", "WMT",
    "BAC", "WFC", "GS", "MS", "DIS", "NKE", "MCD", "ADBE", "CRM", "ORCL", "CSCO", "INTC",
    "AMD", "QCOM", "TXN", "IBM",
]

BOTTOM_PCT = 0.10

INITIAL_CAPITAL = 100_000.0

# Referencia: Sharpe de buy&hold de la cesta (ya calculado en backtest_cross_sectional.py)
BUYHOLD_SHARPE_DEV = 0.91
BUYHOLD_SHARPE_OOS = 1.68


# =============================================================
# RANGO A BARRER — distinto al de AAPL: reversión necesita más
# margen en el stop (para no salir justo antes del rebote) y
# horizontes de mantenimiento más cortos son plausibles.
# =============================================================

stop_pcts = [0.03, 0.05, 0.07, 0.10]
target_pcts = [0.03, 0.05, 0.07]
max_days_list = [10, 20, 30]


# =============================================================
# LOAD + FEATURES + SEÑAL (igual que backtest_cross_sectional.py)
# =============================================================

def load_ticker(ticker: str) -> pd.DataFrame:

    data = pd.read_parquet(f"data/raw/yahoo/{ticker}.parquet")

    engine = FeatureEngine()
    df = engine.build(data)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    return df


print()
print("Cargando universo:", TICKERS)

ticker_data = {ticker: load_ticker(ticker) for ticker in TICKERS}

common_dates = None
for df in ticker_data.values():
    idx = set(df.index)
    common_dates = idx if common_dates is None else common_dates & idx

common_dates = sorted(common_dates)


def build_panel(field: str) -> pd.DataFrame:
    return pd.DataFrame(
        {ticker: ticker_data[ticker].loc[common_dates, field] for ticker in TICKERS},
        index=common_dates,
    )


return_1d_panel = build_panel("return_1d")
rvol_20_panel = build_panel("rvol_20")
distance_high_20_panel = build_panel("distance_high_20")

return_rank = return_1d_panel.rank(axis=1, pct=True)
rvol_rank = rvol_20_panel.rank(axis=1, pct=True)
distance_rank = distance_high_20_panel.rank(axis=1, pct=True)

composite_score = (return_rank + rvol_rank + distance_rank) / 3

threshold_per_day = composite_score.quantile(BOTTOM_PCT, axis=1)
signal_panel = composite_score.le(threshold_per_day, axis=0)

signals = {}
for ticker in TICKERS:
    signals[ticker] = signal_panel[ticker].reindex(ticker_data[ticker].index, fill_value=False)

print(f"Señal: bottom {BOTTOM_PCT:.0%} del ranking construida.\n")


def filter_by_year(data, signals, condition):
    sub_data, sub_signals = {}, {}
    for ticker in data:
        mask = condition(data[ticker].index)
        sub_data[ticker] = data[ticker][mask]
        sub_signals[ticker] = signals[ticker][mask]
    return sub_data, sub_signals


dev_data, dev_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year <= 2022)
oos_data, oos_signals = filter_by_year(ticker_data, signals, lambda idx: idx.year >= 2023)


# =============================================================
# SWEEP
# =============================================================

def run_backtest(data_subset, signals_subset, stop_pct, target_pct, max_days):

    bt = MultiAssetBacktester(
        initial_capital=INITIAL_CAPITAL,
        stop_pct=stop_pct,
        target_pct=target_pct,
        max_days=max_days,
    )

    result = bt.run(data_subset, signals_subset)

    metrics = compute_metrics(result.equity_curve, result.trades, INITIAL_CAPITAL)

    return metrics


print("=" * 100)
print(f"BARRIDO — {len(stop_pcts)}x{len(target_pcts)}x{len(max_days_list)} = "
      f"{len(stop_pcts)*len(target_pcts)*len(max_days_list)} combinaciones")
print("=" * 100)

results = []

for stop_pct in stop_pcts:
    for target_pct in target_pcts:
        for max_days in max_days_list:

            dev = run_backtest(dev_data, dev_signals, stop_pct, target_pct, max_days)
            oos = run_backtest(oos_data, oos_signals, stop_pct, target_pct, max_days)

            results.append({
                "stop_pct": stop_pct,
                "target_pct": target_pct,
                "max_days": max_days,
                "dev_trades": dev["n_trades"],
                "oos_trades": oos["n_trades"],
                "dev_return": dev["total_return"],
                "oos_return": oos["total_return"],
                "dev_sharpe": dev["sharpe"],
                "oos_sharpe": oos["sharpe"],
                "dev_max_dd": dev["max_drawdown"],
                "oos_max_dd": oos["max_drawdown"],
                "dev_win_rate": dev["win_rate"],
                "oos_win_rate": oos["win_rate"],
                "dev_sl": dev["exit_reasons"].get("SL", 0),
                "dev_tp": dev["exit_reasons"].get("TP", 0),
                "oos_sl": oos["exit_reasons"].get("SL", 0),
                "oos_tp": oos["exit_reasons"].get("TP", 0),
                "beats_buyhold_both": (
                    dev["sharpe"] is not None and oos["sharpe"] is not None
                    and dev["sharpe"] > BUYHOLD_SHARPE_DEV
                    and oos["sharpe"] > BUYHOLD_SHARPE_OOS
                ),
            })

            dev_sharpe_str = f"{dev['sharpe']:>5.2f}" if dev['sharpe'] is not None else "  N/A"
            oos_sharpe_str = f"{oos['sharpe']:>5.2f}" if oos['sharpe'] is not None else "  N/A"

            print(
                f"Stop {stop_pct:>4.0%} Target {target_pct:>4.0%} MaxDays {max_days:>3} | "
                f"Dev Sharpe {dev_sharpe_str} "
                f"(SL {dev['exit_reasons'].get('SL',0):>4} TP {dev['exit_reasons'].get('TP',0):>4}) | "
                f"OOS Sharpe {oos_sharpe_str} "
                f"(SL {oos['exit_reasons'].get('SL',0):>4} TP {oos['exit_reasons'].get('TP',0):>4})"
            )


results_df = pd.DataFrame(results)
results_df.to_csv("data/backtest_cross_sectional_robustness.csv", index=False)


# =============================================================
# TOP COMBOS
# =============================================================

print()
print("=" * 100)
print("TOP 10 POR SHARPE COMBINADO (min(dev,oos))")
print("=" * 100)

results_df["combined_sharpe"] = results_df[["dev_sharpe", "oos_sharpe"]].min(axis=1)
top = results_df.sort_values("combined_sharpe", ascending=False).head(10)

for _, row in top.iterrows():
    dev_sharpe_str = f"{row['dev_sharpe']:>5.2f}" if pd.notna(row['dev_sharpe']) else "  N/A"
    dev_dd_str = f"{row['dev_max_dd']:>7.2%}" if pd.notna(row['dev_max_dd']) else "    N/A"
    oos_sharpe_str = f"{row['oos_sharpe']:>5.2f}" if pd.notna(row['oos_sharpe']) else "  N/A"
    oos_dd_str = f"{row['oos_max_dd']:>7.2%}" if pd.notna(row['oos_max_dd']) else "    N/A"

    print(
        f"Stop {row['stop_pct']:>4.0%} Target {row['target_pct']:>4.0%} MaxDays {int(row['max_days']):>3} | "
        f"Dev Sharpe {dev_sharpe_str} MaxDD {dev_dd_str} | "
        f"OOS Sharpe {oos_sharpe_str} MaxDD {oos_dd_str} | "
        f"Bate buy&hold en ambos: {row['beats_buyhold_both']}"
    )


beats_both = results_df[results_df["beats_buyhold_both"]]

print()
print(f"Combinaciones que baten el Sharpe de buy&hold en AMBOS períodos "
      f"(Dev>{BUYHOLD_SHARPE_DEV}, OOS>{BUYHOLD_SHARPE_OOS}): {len(beats_both)} de {len(results_df)}")

print()
print("Resultados completos guardados en: data/backtest_cross_sectional_robustness.csv")