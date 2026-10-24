"""No look-ahead: a decision on day t must not change when data after t is deleted, and it trades one day later."""
import numpy as np
import pandas as pd

from vixcarry import backtest as bt
from vixcarry import load
from vixcarry.strategies import CarrySpec, CarryStrategy
from vixcarry.termstructure import build_term_structure


def _market(seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", "2023-12-29")
    exps = pd.date_range("2023-01-18", periods=14, freq="28D")
    rows, vix = [], 18 + np.cumsum(rng.normal(0, 0.8, len(dates)))
    for i, d in enumerate(dates):
        live = [e for e in exps if e >= d]
        for j, e in enumerate(live[:5]):
            rows.append({"date": d, "contract": f"C{e:%m%d}", "expiry": e,
                         "settle": max(9.0, vix[i] + 0.8 * (j + 1) + rng.normal(0, 0.2))})
    vx = pd.DataFrame(rows).sort_values(["date", "expiry"]).reset_index(drop=True)
    daily = pd.DataFrame({"vix": vix, "vix9d": vix, "vix3m": vix, "spx": 4000 * np.exp(np.cumsum(rng.normal(0, 0.01, len(dates))))},
                         index=dates)
    return vx, daily


def _positions(vx, daily, cfg, spec):
    ts = build_term_structure(vx, daily, cfg)
    px = load.wide(vx)
    r = bt.run_backtest(px, CarryStrategy(spec, ts, px, cfg), cfg["vx"]["multiplier"], 52.5)
    return r.daily


def test_truncation_invariance(cfg):
    vx, daily = _market()
    spec = CarrySpec("t", "front", 0.02, spike_exit=True, stop_volpts=1.5, vol_target=True)
    full = _positions(vx, daily, cfg, spec)
    cut = pd.Timestamp("2023-08-15")
    part = _positions(vx[vx.date <= cut], daily.loc[:cut], cfg, spec)
    # everything up to the cut must be identical whether or not the future exists
    pd.testing.assert_frame_equal(full.loc[:cut], part, check_freq=False)


class _OneSignal:
    def __init__(self, day):
        self.day = day

    def decide(self, i, t, pnl, holdings):
        return {"A": -1.0} if t >= self.day else {}


def test_signal_at_t_trades_at_t_plus_1_and_earns_from_t_plus_2():
    dates = pd.bdate_range("2024-01-01", periods=6)
    px = pd.DataFrame({"A": [10, 11, 12, 13, 14, 15]}, index=dates, dtype=float)
    d = bt.run_backtest(px, _OneSignal(dates[2]), 1000, 50.0).daily
    assert d.cost.iloc[3] == 50.0 and d.cost.iloc[:3].sum() == 0  # decided at t=2, traded at t=3
    assert d.gross.iloc[:4].sum() == 0                              # nothing earned up to the trade day
    assert d.gross.iloc[4] == -1000.0                               # first P&L: the t+1 -> t+2 move
