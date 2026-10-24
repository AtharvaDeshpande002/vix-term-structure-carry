"""Step 4 — does stress in the VIX curve show up in the SOFR curve and in Fed cut pricing?

Rates series used (all built roll-safe: daily changes on fixed contracts, then chained):
  * SR3 position k = the k-th quarterly SOFR future whose last trading day is after today (SR3 data from 2018-05).
    Rate = 100 - price, in bp. "1y spread" = pos1 - pos5 rate (front minus back; it RISES when the market prices
    more cuts a year out relative to the front, i.e. the curve inverts further).
  * ZQ 12m = rate of the fed funds future 12 months ahead minus the current-month contract, in bp.
    Negative = cuts priced over the next year. More negative = more cuts.
  * 2y Treasury yield (bp), the longest sample.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import grangercausalitytests


# ---------------------------------------------------------------- roll-safe rates series
def sr3_positions(sr3: pd.DataFrame, n: int) -> pd.DataFrame:
    """Which fixed SR3 contract sits in positions 1..n on each date (contract names)."""
    live = sr3[sr3.last_trade > sr3.date].copy()
    live["k"] = live.groupby("date").cumcount() + 1  # sorted by (date, last_trade)
    live = live[live.k <= n]
    return live.pivot(index="date", columns="k", values="contract")


def chained_position_changes(wide_rates: pd.DataFrame, names: pd.DataFrame) -> pd.DataFrame:
    """Daily change of each position, measured on the contract that held that position YESTERDAY."""
    out = pd.DataFrame(np.nan, index=names.index, columns=names.columns)
    R = wide_rates.reindex(names.index)
    cols = {c: j for j, c in enumerate(R.columns)}
    A = R.to_numpy()
    N = names.to_numpy()
    for i in range(1, len(names)):
        for k in range(names.shape[1]):
            c = N[i - 1, k]
            if isinstance(c, str) and c in cols:
                out.iat[i, k] = A[i, cols[c]] - A[i - 1, cols[c]]
    return out


def zq_12m_changes(zq: pd.DataFrame) -> pd.DataFrame:
    """Level and roll-safe daily change of (ZQ 12 months ahead - ZQ current month), in bp."""
    zq = zq.copy()
    zq["cur"] = zq.date.dt.to_period("M")
    wide = zq.pivot_table(index="date", columns="month", values="rate_bp")
    dates = wide.index
    level = pd.Series(np.nan, index=dates)
    chg = pd.Series(np.nan, index=dates)
    for i, t in enumerate(dates):
        m0 = t.to_period("M")
        m12 = m0 + 12
        if m0 in wide.columns and m12 in wide.columns:
            level.iat[i] = wide.at[t, m12] - wide.at[t, m0]
        if i:
            p = dates[i - 1].to_period("M")  # yesterday's pair, evaluated today and yesterday
            if p in wide.columns and p + 12 in wide.columns:
                chg.iat[i] = (wide.iat[i, wide.columns.get_loc(p + 12)] - wide.iat[i, wide.columns.get_loc(p)]) - \
                             (wide.iat[i - 1, wide.columns.get_loc(p + 12)] - wide.iat[i - 1, wide.columns.get_loc(p)])
    return pd.DataFrame({"zq12m_level": level, "d_zq12m": chg})


def vx_slope_changes(ts: pd.DataFrame, vx_wide: pd.DataFrame) -> pd.Series:
    """Roll-safe daily change of VX2 - VX1 (using yesterday's VX1 and VX2 contracts)."""
    out = pd.Series(np.nan, index=ts.index)
    W = vx_wide.reindex(ts.index)
    for i in range(1, len(ts)):
        c1, c2 = ts.c1.iat[i - 1], ts.c2.iat[i - 1]
        if isinstance(c1, str) and isinstance(c2, str):
            out.iat[i] = (W[c2].iat[i] - W[c1].iat[i]) - (W[c2].iat[i - 1] - W[c1].iat[i - 1])
    return out


# ---------------------------------------------------------------- inversion events
def inversion_events(ts: pd.DataFrame, min_contango_days: int) -> pd.DatetimeIndex:
    """First day VX1 > VX2 after at least `min_contango_days` consecutive days of contango (VX1 < VX2)."""
    s = ts.slope.dropna()
    run, events = 0, []
    for t, v in s.items():
        if v < 0:
            if run >= min_contango_days:
                events.append(t)
            run = 0
        elif v > 0:
            run += 1
    return pd.DatetimeIndex(events)


def event_paths(changes: pd.Series, events: pd.DatetimeIndex, pre: int, post: int) -> pd.DataFrame:
    """Cumulative change of a series around each event, re-based to 0 at the event-day close.

    Row = event, column = business-day offset (-pre..+post). Offset -5 shows level(-5) - level(0); +10 shows
    level(+10) - level(0). Events without full data are dropped.
    """
    c = changes.dropna()
    lvl = c.cumsum()
    idx = lvl.index
    rows = {}
    for e in events:
        if e not in idx:
            pos = idx.searchsorted(e)
            if pos >= len(idx):
                continue
        else:
            pos = idx.get_loc(e)
        if pos - pre < 0 or pos + post >= len(idx):
            continue
        base = lvl.iat[pos]
        rows[e] = [lvl.iat[pos + k] - base for k in range(-pre, post + 1)]
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(range(-pre, post + 1)), dtype=float)


def summarise_paths(paths: pd.DataFrame) -> pd.DataFrame:
    """Mean path with a 95% confidence band (mean +- 1.96 standard errors)."""
    m = paths.mean()
    se = paths.std(ddof=1) / np.sqrt(paths.count())
    return pd.DataFrame({"mean": m, "lo": m - 1.96 * se, "hi": m + 1.96 * se, "n": paths.count()})


# ---------------------------------------------------------------- lead-lag
def cross_correlation(x: pd.Series, y: pd.Series, max_lag: int) -> pd.Series:
    """corr(x_t, y_{t+lag}). Positive lag = x LEADS y (today's x vs y `lag` days later)."""
    d = pd.concat([x, y], axis=1, keys=["x", "y"]).dropna()
    return pd.Series({lag: d.x.corr(d.y.shift(-lag)) for lag in range(-max_lag, max_lag + 1)})


def granger(x: pd.Series, y: pd.Series, maxlag: int) -> pd.DataFrame:
    """Does x help forecast y beyond y's own past? (F-test p-values by lag; small p = yes)."""
    d = pd.concat([y, x], axis=1).dropna()
    r = grangercausalitytests(d.to_numpy(), maxlag=maxlag)
    return pd.DataFrame({"lag": list(r), "F": [r[k][0]["ssr_ftest"][0] for k in r],
                         "p_value": [r[k][0]["ssr_ftest"][1] for k in r]})


# ---------------------------------------------------------------- conditional weeks
def stress_week_table(vix: pd.Series, pos_changes: pd.DataFrame, rise: float) -> pd.DataFrame:
    """Average weekly SR3 change by position in weeks where spot VIX rose more than `rise` points vs other weeks."""
    wk_vix = vix.dropna().resample("W-FRI").last().diff()
    wk_pos = pos_changes.resample("W-FRI").sum(min_count=1)
    d = wk_pos.join(wk_vix.rename("dvix"), how="inner").dropna()
    stress = d.dvix > rise
    rows = []
    for k in pos_changes.columns:
        a, b = d.loc[stress, k], d.loc[~stress, k]
        t, p = stats.ttest_ind(a, b, equal_var=False)
        rows.append({"position": k, "stress_weeks_bp": a.mean(), "other_weeks_bp": b.mean(),
                     "difference_bp": a.mean() - b.mean(), "t_stat": t, "p_value": p,
                     "n_stress": int(stress.sum()), "n_other": int((~stress).sum())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- trading translation
def sr3_event_trade(events: pd.DatetimeIndex, pos_chg: pd.Series, hold: int, cfg: dict) -> pd.DataFrame:
    """Buy (receive) one SR3 contract at the close AFTER each inversion day and hold `hold` business days.

    P&L per contract = -(rate change in bp) x $25, measured on the roll-safe chained series of that position,
    minus one round trip of costs. Signal at close t, entry at close t+1: no look-ahead.
    """
    s = cfg["sr3"]
    rt_cost = 2 * (s["slippage_ticks"] * s["tick_bp"] * s["multiplier"] + s["commission"])
    c = pos_chg.dropna()
    rows = []
    for e in events:
        if e < c.index[0]:                      # event before this series has data (e.g. SR3 before 2018)
            continue
        pos = c.index.searchsorted(e)          # event day (or next available)
        entry = pos + 1                         # trade at the next close
        if entry + hold >= len(c):
            continue
        move = c.iloc[entry + 1: entry + hold + 1].sum()  # changes earned after the entry close
        rows.append({"event": e, "entry": c.index[entry], "rate_change_bp": move,
                     "gross_usd": -move * s["multiplier"], "net_usd": -move * s["multiplier"] - rt_cost})
    return pd.DataFrame(rows)


def unconditional_trade(pos_chg: pd.Series, hold: int, cfg: dict) -> pd.Series:
    """Net P&L of the same long-SR3 trade entered on EVERY day (the baseline the event trade must beat)."""
    s = cfg["sr3"]
    rt_cost = 2 * (s["slippage_ticks"] * s["tick_bp"] * s["multiplier"] + s["commission"])
    fwd = pos_chg.dropna()[::-1].rolling(hold).sum()[::-1].shift(-1)  # sum of the next `hold` changes after entry
    return (-fwd * s["multiplier"] - rt_cost).dropna()
