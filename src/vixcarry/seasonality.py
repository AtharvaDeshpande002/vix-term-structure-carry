"""Step 3 — expiry seasonality: how the front of the VX curve typically behaves as a contract approaches expiry.

We line up every monthly expiry cycle by "business days to expiry of VX1" and take percentiles across cycles.
The current cycle is then drawn on top: is today's VX1-VX2 spread unusual for this point in the cycle?
"""
from __future__ import annotations

import pandas as pd

PCTS = [0.10, 0.25, 0.50, 0.75, 0.90]


def by_days_to_expiry(ts: pd.DataFrame, col: str, max_bdte: int = 22) -> pd.DataFrame:
    """Percentile table of `col` by business days to VX1 expiry (rows = bdte, columns = p10..p90, mean, n)."""
    d = ts[["bdte1", col]].dropna()
    d = d[d.bdte1 <= max_bdte]
    g = d.groupby("bdte1")[col]
    out = g.quantile(PCTS).unstack()
    out.columns = [f"p{int(p * 100)}" for p in PCTS]
    out["mean"] = g.mean()
    out["n"] = g.size()
    return out


def current_cycle(ts: pd.DataFrame, col: str) -> pd.Series:
    """The latest expiry cycle's path of `col`, indexed by business days to expiry."""
    last = ts.dropna(subset=[col]).iloc[-1]
    cyc = ts[ts.c1 == last.c1]
    return cyc.set_index("bdte1")[col]


def percentile_of_today(hist: pd.Series, value: float) -> float:
    """Share of history at or below today's value (0-100)."""
    h = hist.dropna()
    return float((h <= value).mean() * 100) if len(h) else float("nan")
