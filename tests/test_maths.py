"""Hand-checkable maths: costs, constant maturity, term-structure measures, events, SR3 trade P&L."""
import numpy as np
import pandas as pd
import pytest

from vixcarry import backtest as bt
from vixcarry import crossasset as xa
from vixcarry.pipeline import vx_cost_per_side
from vixcarry.termstructure import constant_maturity


def test_vx_cost_per_side(cfg):
    # 1 tick (0.05 vol pts x $1000 = $50) + $2.50 commission
    assert vx_cost_per_side(cfg) == pytest.approx(52.5)


def test_constant_maturity_interpolation():
    ft = pd.DataFrame({"VX1": [20.0], "VX2": [22.0], "VX3": [23.0], "VX4": [24.0],
                       "dte1": [10], "dte2": [40], "dte3": [70], "dte4": [100]})
    # 30 days sits 2/3 of the way from 10 to 40 -> weight 1/3 on VX1, 2/3 on VX2
    assert constant_maturity(ft, 30).iloc[0] == pytest.approx(20 / 3 + 2 * 22 / 3)
    # if even VX1 is beyond the target, use VX1 flat
    ft2 = ft.assign(dte1=35, dte2=65)
    assert constant_maturity(ft2, 30).iloc[0] == 20.0


def test_drawdown_and_metrics():
    d = pd.DataFrame({"gross": [0, 100, -300, 50, 400], "cost": [0, 0, 0, 0, 0]},
                     index=pd.bdate_range("2024-01-01", periods=5), dtype=float)
    d["net"] = d.gross - d.cost
    d["exposure"] = [0, 1, 1, 1, 0]
    d["active"] = d.exposure > 0
    d["trade_id"] = np.where(d.active, 1, 0)
    r = bt.BacktestResult(daily=d, trades=bt.trade_table(d))
    m = bt.metrics(r)
    assert m["max_dd_usd"] == -300           # peak 100 -> trough -200
    assert m["net_usd"] == 250
    # one trade over days 2-4: +100 - 300 + 50 = -150 -> a loser (the +400 day is after exposure ended)
    assert m["trades"] == 1 and m["hit_rate"] == 0.0
    assert r.trades.net.iloc[0] == -150


def test_inversion_events_need_a_contango_run():
    idx = pd.bdate_range("2024-01-01", periods=30)
    slope = pd.Series([1.0] * 22 + [-1.0] * 3 + [1.0] * 2 + [-1.0] * 3, index=idx)
    ev = xa.inversion_events(pd.DataFrame({"slope": slope}), min_contango_days=20)
    # first inversion follows 22 contango days -> counts; the second follows only 2 -> ignored
    assert list(ev) == [idx[22]]


def test_event_paths_rebased_to_event_day():
    idx = pd.bdate_range("2024-01-01", periods=10)
    ch = pd.Series([0, 1, 1, 1, 1, 1, 1, 1, 1, 1], index=idx, dtype=float)
    p = xa.event_paths(ch, pd.DatetimeIndex([idx[4]]), pre=2, post=3)
    assert p.iloc[0].tolist() == [-2, -1, 0, 1, 2, 3]


def test_sr3_event_trade_pnl(cfg):
    idx = pd.bdate_range("2024-01-01", periods=10)
    ch = pd.Series(-1.0, index=idx)  # rate falls 1 bp a day -> a long SR3 position gains $25 a day
    t = xa.sr3_event_trade(pd.DatetimeIndex([idx[2]]), ch, hold=4, cfg=cfg)
    rt = 2 * (1 * 0.5 * 25 + 2.5)   # 1 tick = 0.5 bp x $25 + $2.50, both sides
    assert t.entry.iloc[0] == idx[3]
    assert t.gross_usd.iloc[0] == pytest.approx(4 * 25)
    assert t.net_usd.iloc[0] == pytest.approx(100 - rt)
