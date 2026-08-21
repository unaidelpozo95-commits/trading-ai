"""Métricas de rendimiento a partir de la curva de equity y el log de trades."""

import numpy as np
import pandas as pd


def compute_metrics(
    equity_curve: pd.Series,
    trades: list,
    initial_capital: float,
    periods_per_year: int = 252,
) -> dict:

    daily_returns = equity_curve.pct_change().dropna()

    total_return = equity_curve.iloc[-1] / initial_capital - 1

    n_years = len(equity_curve) / periods_per_year
    cagr = (
        (equity_curve.iloc[-1] / initial_capital) ** (1 / n_years) - 1
        if n_years > 0
        else None
    )

    sharpe = None
    if daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(periods_per_year)

    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1
    max_drawdown = drawdown.min()

    closed = [t for t in trades if t.exit_price is not None]
    returns = [t.return_pct for t in closed]

    win_rate = np.mean([r > 0 for r in returns]) if returns else None

    gains = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    profit_factor = (
        sum(gains) / abs(sum(losses))
        if losses and sum(losses) != 0
        else None
    )

    avg_win = np.mean(gains) if gains else None
    avg_loss = np.mean(losses) if losses else None

    exit_reasons = (
        pd.Series([t.exit_reason for t in closed]).value_counts().to_dict()
        if closed
        else {}
    )

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "n_trades": len(closed),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "exit_reasons": exit_reasons,
    }
