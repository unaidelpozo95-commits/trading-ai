"""
Backtester multi-activo.

Reutiliza las mismas reglas de entrada/salida que
src/backtest/engine.py (Trade, misma lógica de SL/TP/tiempo), pero
gestiona una cartera de varios símbolos a la vez.

Decisión de diseño: si varias señales se activan el mismo día, el
cash disponible en ese momento se reparte A PARTES IGUALES entre
todas ellas (no "el primero se lo lleva todo", que era el
comportamiento de la versión single-asset).
"""

from typing import Dict, List

import pandas as pd

from src.backtest.engine import Trade, BacktestResult


class MultiAssetBacktester:

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        stop_pct: float = 0.02,
        target_pct: float = 0.05,
        max_days: int = 20,
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
    ):
        self.initial_capital = initial_capital
        self.stop_pct = stop_pct
        self.target_pct = target_pct
        self.max_days = max_days
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

    def run(
        self,
        data: Dict[str, pd.DataFrame],
        signals: Dict[str, pd.Series],
    ) -> BacktestResult:

        symbols = list(data.keys())

        data = {
            symbol: (
                df
                if isinstance(df.index, pd.DatetimeIndex)
                else df.set_index(pd.to_datetime(df.index))
            )
            for symbol, df in data.items()
        }

        # Entrada en Open[D+1] -> desplazamos cada señal un día.
        entry_today = {
            symbol: signals[symbol].shift(1).fillna(False)
            for symbol in symbols
        }

        # Calendario unificado: unión de todas las fechas de todos los símbolos.
        all_dates = sorted(
            set().union(*[data[symbol].index for symbol in symbols])
        )

        cash = self.initial_capital
        open_positions: List[Trade] = []
        closed_trades: List[Trade] = []
        equity_curve = {}

        for date in all_dates:

            # --- 1. Gestionar posiciones abiertas ---
            still_open = []
            for pos in open_positions:

                sym_df = data[pos.symbol]

                if date not in sym_df.index:
                    still_open.append(pos)
                    continue

                row = sym_df.loc[date]

                hit_stop = row["Low"] <= pos.stop_price
                hit_target = row["High"] >= pos.target_price
                time_exit = date >= pos.max_exit_date

                if hit_stop and hit_target:
                    pos.exit_date = date
                    pos.exit_reason = "AMBIGUOUS"
                    pos.exit_price = self._apply_costs(pos.stop_price, sell=True)
                    cash += pos.shares * pos.exit_price
                    closed_trades.append(pos)
                    continue

                if hit_target:
                    pos.exit_date = date
                    pos.exit_price = self._apply_costs(pos.target_price, sell=True)
                    pos.exit_reason = "TP"
                    cash += pos.shares * pos.exit_price
                    closed_trades.append(pos)
                    continue

                if hit_stop:
                    pos.exit_date = date
                    pos.exit_price = self._apply_costs(pos.stop_price, sell=True)
                    pos.exit_reason = "SL"
                    cash += pos.shares * pos.exit_price
                    closed_trades.append(pos)
                    continue

                if time_exit:
                    pos.exit_date = date
                    pos.exit_price = self._apply_costs(row["Open"], sell=True)
                    pos.exit_reason = "TIME"
                    cash += pos.shares * pos.exit_price
                    closed_trades.append(pos)
                    continue

                still_open.append(pos)

            open_positions = still_open

            # --- 2. Señales que se activan hoy (con datos hoy) ---
            firing_symbols = [
                symbol
                for symbol in symbols
                if date in entry_today[symbol].index
                and bool(entry_today[symbol].loc[date])
                and date in data[symbol].index
            ]

            if firing_symbols:

                per_trade_cash = cash / len(firing_symbols)

                for symbol in firing_symbols:

                    sym_df = data[symbol]
                    row = sym_df.loc[date]

                    entry_price = self._apply_costs(row["Open"], sell=False)

                    if per_trade_cash <= 0 or entry_price <= 0:
                        continue

                    shares = per_trade_cash / entry_price

                    i = sym_df.index.get_loc(date)
                    max_exit_idx = min(i + self.max_days, len(sym_df) - 1)
                    max_exit_date = sym_df.index[max_exit_idx]

                    trade = Trade(
                        symbol=symbol,
                        entry_date=date,
                        entry_price=entry_price,
                        shares=shares,
                        stop_price=entry_price * (1 - self.stop_pct),
                        target_price=entry_price * (1 + self.target_pct),
                        max_exit_date=max_exit_date,
                    )

                    cash -= shares * entry_price
                    open_positions.append(trade)

            # --- 3. Marcar equity a mercado ---
            open_value = 0.0
            for pos in open_positions:
                sym_df = data[pos.symbol]
                if date in sym_df.index:
                    open_value += pos.shares * sym_df.loc[date, "Close"]
                else:
                    # símbolo sin dato ese día concreto (festivo local, etc.)
                    # -> aproximamos con el precio de entrada.
                    open_value += pos.shares * pos.entry_price

            equity_curve[date] = cash + open_value

        # Cerrar a la fuerza lo que quede abierto al final de los datos.
        if open_positions:
            for pos in open_positions:
                sym_df = data[pos.symbol]
                last_date = sym_df.index[-1]
                last_close = sym_df["Close"].iloc[-1]

                pos.exit_date = last_date
                pos.exit_price = self._apply_costs(last_close, sell=True)
                pos.exit_reason = "END_OF_DATA"
                cash += pos.shares * pos.exit_price
                closed_trades.append(pos)

            equity_curve[all_dates[-1]] = cash

        equity_series = pd.Series(equity_curve).sort_index()

        return BacktestResult(trades=closed_trades, equity_curve=equity_series)

    def _apply_costs(self, price: float, sell: bool) -> float:
        slip = price * self.slippage_pct
        price = price - slip if sell else price + slip
        commission_adj = price * self.commission_pct
        return price - commission_adj if sell else price + commission_adj
