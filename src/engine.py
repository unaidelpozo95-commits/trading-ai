"""
Motor de backtesting.

Notas de diseño
----------------
- La señal se genera en Close[D]; la entrada se ejecuta en Open[D+1],
  igual que en event_study.py y robustness.py (evita look-ahead bias).
- Las salidas replican la lógica de stop_tp_study() en event_study.py:
  Stop Loss / Take Profit fijos comprobados contra el High/Low diario,
  con salida por tiempo si no se toca ningún nivel en `max_days`.
- Si el mismo día se tocan SL y TP (no se puede saber el orden con
  datos OHLC diarios), se asume conservadoramente salida al stop.
- Position sizing: cada nueva operación usa `position_size_pct` del
  cash disponible en ese momento (por defecto 100%). La arquitectura
  soporta posiciones simultáneas (pensando en multi-activo), pero con
  100% de cash por operación, una segunda señal mientras hay una
  posición abierta simplemente no encontrará cash disponible y se
  saltará — es el comportamiento esperado por ahora, no un bug.
- Comisiones y slippage están modelados pero desactivados por defecto
  (commission_pct=0.0, slippage_pct=0.0) — quedan como parámetro para
  activarlos más adelante sin tocar el motor.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    stop_price: float
    target_price: float
    max_exit_date: pd.Timestamp
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "TP" | "SL" | "TIME" | "AMBIGUOUS" | "END_OF_DATA"

    @property
    def is_open(self) -> bool:
        return self.exit_date is None

    @property
    def pnl(self) -> Optional[float]:
        if self.exit_price is None:
            return None
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def return_pct(self) -> Optional[float]:
        if self.exit_price is None:
            return None
        return self.exit_price / self.entry_price - 1


@dataclass
class BacktestResult:
    trades: list
    equity_curve: pd.Series


class Backtester:

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        stop_pct: float = 0.02,
        target_pct: float = 0.05,
        max_days: int = 20,
        position_size_pct: float = 1.0,
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
        symbol: str = "AAPL",
    ):
        self.initial_capital = initial_capital
        self.stop_pct = stop_pct
        self.target_pct = target_pct
        self.max_days = max_days
        self.position_size_pct = position_size_pct
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.symbol = symbol

    def run(self, df: pd.DataFrame, signal: pd.Series) -> BacktestResult:
        """
        df: OHLCV indexado por fecha (debe contener Open, High, Low, Close).
        signal: serie booleana alineada con df.index; True el día en que
                se cumple la condición en Close[D] (la entrada ocurre en D+1).
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)

        dates = df.index
        n = len(df)

        # La decisión de entrar se toma en Open[D+1] -> desplazamos la señal.
        entry_today = signal.shift(1).fillna(False)

        cash = self.initial_capital
        open_positions: list[Trade] = []
        closed_trades: list[Trade] = []
        equity_curve = {}

        for i in range(n):
            date = dates[i]
            row = df.iloc[i]

            # --- 1. Gestionar posiciones abiertas: comprobar salidas ---
            still_open = []
            for pos in open_positions:
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

            # --- 2. Abrir nueva posición si la señal se activó ayer ---
            if entry_today.iloc[i]:
                available = cash * self.position_size_pct
                entry_price = self._apply_costs(row["Open"], sell=False)

                if available > 0 and entry_price > 0:
                    shares = available / entry_price
                    max_exit_idx = min(i + self.max_days, n - 1)

                    trade = Trade(
                        symbol=self.symbol,
                        entry_date=date,
                        entry_price=entry_price,
                        shares=shares,
                        stop_price=entry_price * (1 - self.stop_pct),
                        target_price=entry_price * (1 + self.target_pct),
                        max_exit_date=dates[max_exit_idx],
                    )

                    cash -= shares * entry_price
                    open_positions.append(trade)

            # --- 3. Marcar equity a mercado ---
            open_value = sum(pos.shares * row["Close"] for pos in open_positions)
            equity_curve[date] = cash + open_value

        # Cerrar a la fuerza lo que siga abierto al final de los datos.
        if open_positions:
            last_row = df.iloc[-1]
            for pos in open_positions:
                pos.exit_date = dates[-1]
                pos.exit_price = self._apply_costs(last_row["Close"], sell=True)
                pos.exit_reason = "END_OF_DATA"
                cash += pos.shares * pos.exit_price
                closed_trades.append(pos)
            equity_curve[dates[-1]] = cash

        equity_series = pd.Series(equity_curve).sort_index()

        return BacktestResult(trades=closed_trades, equity_curve=equity_series)

    def _apply_costs(self, price: float, sell: bool) -> float:
        """Aplica slippage y comisión como ajuste porcentual simple.
        Ambos son 0.0 por defecto (stub) según la decisión de diseño actual."""
        slip = price * self.slippage_pct
        price = price - slip if sell else price + slip
        commission_adj = price * self.commission_pct
        return price - commission_adj if sell else price + commission_adj
