"""A small, explicit, day-by-day futures backtest engine plus performance metrics.

Timing convention (no look-ahead):
  * At the close of day t a strategy sees ONLY data up to and including t and decides a target position.
  * That target is traded at the settlement of day t+1 (costs charged on t+1).
  * The new position earns the settle-to-settle change from t+1 to t+2 onward.
So a signal is never traded at the very price that produced it.

Roll safety: positions are held in named contracts (e.g. "VXH24"), and P&L is always the change in the SAME
contract's settle. Rolling = closing one contract and opening another, which costs two trades and never creates a
fake jump in P&L.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np
import pandas as pd


class Strategy(Protocol):
    def decide(self, i: int, t: pd.Timestamp, last_net_pnl: float, holdings: dict[str, float]) -> dict[str, float]:
        ...


@dataclass
class BacktestResult:
    daily: pd.DataFrame                       # gross, cost, net, gross_qty, active, trade_id
    trades: pd.DataFrame = field(default_factory=pd.DataFrame)


def run_backtest(px: pd.DataFrame, strategy: Strategy, multiplier: float,
                 cost_per_side: float | Callable[[str], float]) -> BacktestResult:
    """Run `strategy` over the dates of `px` (dates x contracts settle table).

    cost_per_side: dollars charged per contract traded, per side (slippage + commission), or a function of contract.
    """
    cost_of = cost_per_side if callable(cost_per_side) else (lambda c, v=cost_per_side: v)
    dates = px.index
    P = px.to_numpy()
    col = {c: j for j, c in enumerate(px.columns)}
    last_px: dict[str, float] = {}     # last valid settle per contract (a missing settle = no change that day)
    holdings: dict[str, float] = {}    # position held after the close of the previous day
    pending: dict[str, float] = {}     # target decided yesterday, executed at today's close
    rec = np.zeros((len(dates), 4))
    for i, t in enumerate(dates):
        # 1) mark yesterday's holdings to today's settle (same contract -> roll safe)
        gross = 0.0
        for c, q in holdings.items():
            p = P[i, col[c]]
            if not np.isnan(p):
                if c in last_px:
                    gross += q * (p - last_px[c]) * multiplier
        for c in px.columns[~np.isnan(P[i])]:
            last_px[c] = P[i, col[c]]
        # 2) execute yesterday's decision at today's settle
        cost = 0.0
        for c in set(pending) | set(holdings):
            dq = pending.get(c, 0.0) - holdings.get(c, 0.0)
            if dq != 0:
                cost += abs(dq) * cost_of(c)
        prev_qty = sum(abs(q) for q in holdings.values())
        holdings = {c: q for c, q in pending.items() if q != 0}
        net = gross - cost
        rec[i] = (gross, cost, net, prev_qty + sum(abs(q) for q in holdings.values()))
        # 3) decide tomorrow's target with information up to today only
        pending = strategy.decide(i, t, net, dict(holdings)) or {}
    d = pd.DataFrame(rec, index=dates, columns=["gross", "cost", "net", "exposure"])
    d["active"] = d.exposure > 0
    # a "trade" is a continuous block of days with exposure (a roll inside the block does not split it)
    start = d.active & ~d.active.shift(1, fill_value=False)
    d["trade_id"] = np.where(d.active, start.cumsum(), 0)
    return BacktestResult(daily=d, trades=trade_table(d))


def trade_table(d: pd.DataFrame) -> pd.DataFrame:
    """One row per trade: entry/exit dates, business days held, net P&L."""
    a = d[d.trade_id > 0].assign(day=lambda x: x.index)
    if a.empty:
        return pd.DataFrame(columns=["entry", "exit", "days", "net"])
    g = a.groupby("trade_id")
    return pd.DataFrame({"entry": g.day.first(), "exit": g.day.last(), "days": g.size() - 1, "net": g.net.sum()})


def drawdown(equity: pd.Series) -> pd.Series:
    """Distance below the running peak of a cumulative P&L curve (<= 0)."""
    return equity - equity.cummax()


def metrics(res: BacktestResult, start=None, end=None, periods: int = 252) -> dict:
    """Headline statistics over [start, end]. Trades are assigned to the period of their entry date."""
    d = res.daily.loc[start:end]
    tr = res.trades
    if len(tr):
        tr = tr[(tr.entry >= d.index[0]) & (tr.entry <= d.index[-1])]
    net = d.net
    eq = net.cumsum()
    sd = net.std()
    wins, losses = tr.net[tr.net > 0], tr.net[tr.net <= 0]
    return {
        "start": d.index[0].date(), "end": d.index[-1].date(),
        "trades": int(len(tr)),
        "hit_rate": float((tr.net > 0).mean()) if len(tr) else np.nan,
        "avg_win_usd": float(wins.mean()) if len(wins) else np.nan,
        "avg_loss_usd": float(losses.mean()) if len(losses) else np.nan,
        "avg_days_held": float(tr.days.mean()) if len(tr) else np.nan,
        "gross_usd": float(d.gross.sum()), "costs_usd": float(d.cost.sum()), "net_usd": float(net.sum()),
        "net_usd_per_year": float(net.mean() * periods),
        "sharpe": float(net.mean() / sd * np.sqrt(periods)) if sd > 0 else np.nan,
        "max_dd_usd": float(drawdown(eq).min()),
        "worst_day_usd": float(net.min()),
        "worst_week_usd": float(net.rolling(5).sum().min()),
        "time_in_market": float(d.active.mean()),
    }


def tail_stats(res: BacktestResult, start: str, end: str) -> dict:
    """What a strategy did inside one crisis window, and how long it took to get back to its pre-crisis high."""
    full = res.daily.net.cumsum()
    w = res.daily.loc[start:end]
    if w.empty:
        return {"pnl_usd": np.nan, "worst_day_usd": np.nan, "worst_week_usd": np.nan, "max_dd_usd": np.nan,
                "recovery_bdays": np.nan}
    before = full.loc[:start].iloc[:-1]
    base = float(before.iloc[-1]) if len(before) else 0.0     # equity the day before the window opens
    eq_w = full.loc[start:end]
    peak = np.maximum(eq_w.cummax(), base)                    # peaks reached from the window start onward
    dd = eq_w - peak                                          # drawdown that happened INSIDE the window
    recovery = np.nan
    if dd.min() < 0:
        trough_day = dd.idxmin()
        target = peak.loc[trough_day]                         # the high we must get back to
        after = full.loc[trough_day:]
        rec = after[after >= target]
        # business days from the trough until the strategy is back at its high (inf = not recovered by data end)
        recovery = float(np.busday_count(trough_day.date(), rec.index[0].date())) if len(rec) else np.inf
    return {"pnl_usd": float(w.net.sum()), "worst_day_usd": float(w.net.min()),
            "worst_week_usd": float(w.net.rolling(5, min_periods=1).sum().min()),
            "max_dd_usd": float(dd.min()), "recovery_bdays": recovery}
