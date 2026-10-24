"""Step 1 — the VX term-structure dataset.

Definitions used everywhere in the project
  VX1, VX2, ...  the 1st, 2nd, ... VX contract whose expiry is AFTER today (a contract on its expiry day is gone).
  dte            calendar days to expiry; bdte = business days to expiry (weekdays, exchange holidays ignored).
  basis          VX1 - spot VIX          (vol pts; positive = futures above spot = normal "contango" state)
  slope          VX2 - VX1               (vol pts)
  contango       VX2 / VX1 - 1           (ratio; > 0 contango, < 0 backwardation / "inverted")
  roll yield     basis / dte             (vol pts per calendar day the front contract drifts toward spot if
                                          nothing else changes — the "carry" a short collects)
  CM-30          constant-maturity 30-day VX: linear interpolation in days to expiry between the two contracts
                 that straddle 30 days; flat VX1 if even VX1 is further than 30 days away.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def bdays_between(start: pd.Series | pd.DatetimeIndex, end: pd.Series) -> np.ndarray:
    """Business days from start (exclusive) to end (inclusive) — weekdays only."""
    a = np.asarray(pd.to_datetime(start).values, dtype="datetime64[D]")
    b = np.asarray(pd.to_datetime(end).values, dtype="datetime64[D]")
    return np.busday_count(a, b)


def front_table(vx: pd.DataFrame, n: int = 4) -> pd.DataFrame:
    """One row per date with the first n live contracts: VXk settle, contract name, expiry, dte, bdte.

    A contract is "live" on date t only if its expiry is strictly after t, so VX1 rolls to the next contract
    on the expiry date itself — exactly when the old one stops trading.
    """
    live = vx[vx.expiry > vx.date].copy()
    live["k"] = live.groupby("date").cumcount() + 1  # rows are sorted by (date, expiry) in load_vx
    live = live[live.k <= n]
    live["dte"] = (live.expiry - live.date).dt.days
    live["bdte"] = bdays_between(live.date, live.expiry)
    out = {}
    for k in range(1, n + 1):
        g = live[live.k == k].set_index("date")
        out[f"VX{k}"] = g.settle
        out[f"c{k}"] = g.contract
        out[f"exp{k}"] = g.expiry
        out[f"dte{k}"] = g.dte
        out[f"bdte{k}"] = g.bdte
    return pd.DataFrame(out).sort_index()


def constant_maturity(ft: pd.DataFrame, days: int, n: int = 4) -> pd.Series:
    """Constant-maturity VX at `days` calendar days, interpolated between the straddling contracts."""
    res = pd.Series(np.nan, index=ft.index)
    first = ft["dte1"] >= days  # even the front is further away -> use VX1 flat
    res[first] = ft.loc[first, "VX1"]
    for k in range(1, n):
        d1, d2 = ft[f"dte{k}"], ft[f"dte{k + 1}"]
        m = res.isna() & (d1 < days) & (d2 >= days)
        w = (d2[m] - days) / (d2[m] - d1[m])  # weight on the nearer contract: 1 when it sits exactly at `days`
        res[m] = w * ft.loc[m, f"VX{k}"] + (1 - w) * ft.loc[m, f"VX{k + 1}"]
    return res


def realised_vol(spx: pd.Series, window: int, periods: int = 252) -> pd.DataFrame:
    """Trailing and FORWARD realised S&P 500 volatility (annualised, in vol points).

    The forward one (next `window` days) is what VIX tries to predict, so VIX - forward RV is the
    variance-risk premium actually earned. It is ex-post and is only ever used for description, never as a signal.
    """
    r = np.log(spx.dropna()).diff()
    trail = r.rolling(window).std() * np.sqrt(periods) * 100
    fwd = trail.shift(-window)  # the window ending `window` days later = the next `window` returns
    return pd.DataFrame({"rv_trailing": trail, "rv_forward": fwd})


def build_term_structure(vx: pd.DataFrame, daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The full daily term-structure table used by every later step."""
    ft = front_table(vx, n=4)
    for d in cfg["term_structure"]["cm_days"]:
        ft[f"CM{d}"] = constant_maturity(ft, d)
    ft = ft.join(daily[["vix", "vix9d", "vix3m", "spx"]], how="left")
    ft["basis"] = ft.VX1 - ft.vix
    ft["slope"] = ft.VX2 - ft.VX1
    ft["contango"] = ft.VX2 / ft.VX1 - 1
    ft["in_contango"] = ft.slope > 0
    ft["roll_yield"] = ft.basis / ft.dte1.where(ft.dte1 > 0)  # vol pts per calendar day
    rv = realised_vol(daily["spx"], cfg["term_structure"]["rv_window"], cfg["term_structure"]["trading_days_per_year"])
    ft = ft.join(rv, how="left")
    ft["vrp"] = ft.vix - ft.rv_forward
    return ft


def curve_on_grid(vx: pd.DataFrame, grid: np.ndarray) -> pd.DataFrame:
    """Each date's VX curve linearly interpolated onto a fixed days-to-expiry grid (NaN outside listed range).

    Used for the heatmap and the percentile bands: it makes curves from different dates comparable even though
    each date has its own expiry calendar.
    """
    live = vx[vx.expiry > vx.date].assign(dte=lambda x: (x.expiry - x.date).dt.days)
    rows = {}
    for d, g in live.groupby("date"):
        rows[d] = np.interp(grid, g.dte.values, g.settle.values, left=np.nan, right=np.nan)
    return pd.DataFrame.from_dict(rows, orient="index", columns=grid).sort_index()
