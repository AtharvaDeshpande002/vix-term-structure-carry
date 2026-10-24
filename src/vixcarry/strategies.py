"""Step 2 — the carry strategies.

All of them sell VX futures when the curve is upward sloping (contango), because then the contract drifts DOWN
toward spot VIX as expiry approaches and a short position collects that drift. They differ in how they try to
survive the days when volatility explodes.

Which contract is traded (fixed rule, known in advance -> no look-ahead):
  "held front" = the nearest contract with MORE than `roll_bdays` business days to expiry. So we hold VX1 until
  5 business days before expiry, then roll into VX2 (the last week of a VX contract is dominated by the
  expiry-settlement mechanics, not carry).
  "held next"  = the contract after the held front (used by the calendar spreads).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CarrySpec:
    name: str
    kind: str = "front"              # "front" | "calendar" | "calendar_beta"
    threshold: float | None = None   # contango filter; None = always short
    spike_exit: bool = False
    stop_volpts: float | None = None
    vol_target: bool = False


def held_contracts(ft: pd.DataFrame, roll_bdays: int) -> pd.DataFrame:
    """For each date: the held front contract and the one after it, by the fixed roll rule."""
    early = ft.bdte1 > roll_bdays
    return pd.DataFrame({"front": np.where(early, ft.c1, ft.c2), "next": np.where(early, ft.c2, ft.c3)},
                        index=ft.index)


def chained_changes(px: pd.DataFrame, names: pd.Series) -> pd.Series:
    """Roll-safe daily change of a "generic" position: on day t, the change of the contract held on day t-1.

    This is the only correct way to build a continuous return series from futures: the change is always measured
    on one fixed contract; the roll happens between days, never inside a change.
    """
    prev = names.shift(1)
    out = pd.Series(np.nan, index=px.index)
    cols = {c: j for j, c in enumerate(px.columns)}
    P = px.to_numpy()
    for i in range(1, len(px)):
        c = prev.iloc[i]
        if isinstance(c, str) and c in cols:
            out.iloc[i] = P[i, cols[c]] - P[i - 1, cols[c]]
    return out


class CarryStrategy:
    """Turns a CarrySpec into day-by-day target positions. Sees only data up to the current date."""

    def __init__(self, spec: CarrySpec, ft: pd.DataFrame, px: pd.DataFrame, cfg: dict):
        c = cfg["carry"]
        self.s, self.cfg = spec, cfg
        self.held = held_contracts(ft, cfg["vx"]["roll_bdays"]).reindex(px.index)
        self.contango = ft.contango.reindex(px.index).to_numpy()
        self.inverted = (ft.slope < 0).reindex(px.index).to_numpy()
        vix = ft.vix.reindex(px.index)
        self.vix_jump = (vix / vix.ffill().shift(1) - 1).to_numpy()
        dfront = chained_changes(px, self.held.front)
        dnext = chained_changes(px, self.held.next)
        # 1-lot daily $ volatility of the traded leg, from the last `vol_lookback` days (known at t)
        self.sigma_usd = (dfront.rolling(c["vol_lookback"]).std() * cfg["vx"]["multiplier"]).to_numpy()
        # hedge ratio: how many points the front moves per point of the next contract (rolling OLS slope)
        w = c["hedge_beta_window"]
        self.beta = (dfront.rolling(w).cov(dnext) / dnext.rolling(w).var()).clip(0.5, 3.0).to_numpy()
        self.cooldown = 0
        self.trade_pnl = 0.0
        self.exits = {"spike": 0, "stop": 0, "filter": 0}  # why trades ended (for the README / notes)
        self.mult = cfg["vx"]["multiplier"]

    def _signal_on(self, i: int) -> bool:
        if self.s.threshold is None:
            return True
        x = self.contango[i]
        return bool(not np.isnan(x) and x > self.s.threshold)

    def decide(self, i, t, last_net_pnl, holdings):
        s, c = self.s, self.cfg["carry"]
        in_trade = bool(holdings)
        self.trade_pnl = self.trade_pnl + last_net_pnl if in_trade else 0.0
        if self.cooldown > 0:
            self.cooldown -= 1
            return {}
        # exits that override the carry signal
        if s.spike_exit and (self.inverted[i] or (not np.isnan(self.vix_jump[i]) and self.vix_jump[i] > c["spike_exit_vix_jump"])):
            self.cooldown = c["cooldown_days"]
            self.exits["spike"] += in_trade
            return {}
        if s.stop_volpts is not None and in_trade:
            lots = max(abs(q) for q in holdings.values() if q < 0)
            if self.trade_pnl / (lots * self.mult) <= -s.stop_volpts:
                self.cooldown = c["cooldown_days"]
                self.exits["stop"] += 1
                return {}
        if not self._signal_on(i):
            self.exits["filter"] += in_trade
            return {}
        front, nxt = self.held.front.iloc[i], self.held.next.iloc[i]
        if not isinstance(front, str):
            return {}
        n = 1.0
        if s.vol_target:
            sig = self.sigma_usd[i]
            if np.isnan(sig) or sig <= 0:
                return {}
            n = float(min(c["max_contracts"], max(1, math.floor(c["vol_target_daily_usd"] / sig))))
            if in_trade:  # keep size fixed during a trade (resize only at entry) to avoid churn costs
                n = max(abs(q) for k, q in holdings.items() if q < 0)
        if s.kind == "front":
            return {front: -n}
        if not isinstance(nxt, str):
            return {}
        if s.kind == "calendar":
            return {front: -n, nxt: +n}
        b = self.beta[i]
        if np.isnan(b):
            return {}
        if in_trade and nxt in holdings:  # keep the hedge ratio fixed during a trade
            return {front: -n, nxt: holdings[nxt]}
        return {front: -n, nxt: round(float(b) * n, 2)}


def default_specs(threshold: float, stop: float) -> list[CarrySpec]:
    """The strategy variants compared in the README, from naive to most defended."""
    return [
        CarrySpec("Short front, always", "front", None),
        CarrySpec("Short front, contango filter", "front", threshold),
        CarrySpec("+ spike exit", "front", threshold, spike_exit=True),
        CarrySpec("+ spike exit + stop", "front", threshold, spike_exit=True, stop_volpts=stop),
        # the parameter-free reading of the rule ("short whenever the curve slopes up"), NOT chosen in-sample;
        # shown so the reader can compare the optimised rule with the obvious one
        CarrySpec("Contango > 0 + spike exit + stop", "front", 0.0, spike_exit=True, stop_volpts=stop),
        CarrySpec("Calendar 1:1 (short VX1 / long VX2)", "calendar", threshold, spike_exit=True),
        CarrySpec("Calendar beta-weighted", "calendar_beta", threshold, spike_exit=True),
        CarrySpec("Spike exit + stop, vol-targeted", "front", threshold, spike_exit=True, stop_volpts=stop, vol_target=True),
    ]
