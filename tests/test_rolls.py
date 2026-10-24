"""Roll handling: returns are never computed across two different contracts."""
import numpy as np
import pandas as pd

from vixcarry import backtest as bt
from vixcarry import load
from vixcarry.crossasset import chained_position_changes
from vixcarry.strategies import chained_changes, held_contracts
from vixcarry.termstructure import front_table


def test_front_rolls_on_expiry_day(synthetic_vx):
    ft = front_table(synthetic_vx, n=2)
    # on A's expiry day A is no longer "live": VX1 is already B
    assert ft.loc["2024-01-16", "c1"] == "A"
    assert ft.loc["2024-01-17", "c1"] == "B"
    assert ft.loc["2024-01-17", "c2"] == "C"


def test_chained_changes_ignore_level_gap(synthetic_vx):
    ft = front_table(synthetic_vx, n=3)
    px = load.wide(synthetic_vx)
    held = held_contracts(ft, roll_bdays=5)
    d = chained_changes(px, held.front).dropna()
    # every contract drifts +0.1/day; the 10-point gap between contracts must never appear
    assert np.allclose(d.values, 0.1)


def test_roll_rule_switches_five_business_days_before_expiry(synthetic_vx):
    ft = front_table(synthetic_vx, n=3)
    held = held_contracts(ft, roll_bdays=5)
    # A expires Wed 17-Jan: 5 business days before is Wed 10-Jan (bdte = 5) -> already holding B
    assert held.loc["2024-01-09", "front"] == "A"   # bdte = 6
    assert held.loc["2024-01-10", "front"] == "B"   # bdte = 5


class _Hold:
    """Short 1 of the held front every day (decided at t, executed at t+1)."""

    def __init__(self, held):
        self.held = held

    def decide(self, i, t, pnl, holdings):
        return {self.held.front.iloc[i]: -1.0}


def test_backtest_pnl_and_costs_through_a_roll(synthetic_vx):
    ft = front_table(synthetic_vx, n=3)
    px = load.wide(synthetic_vx)
    held = held_contracts(ft, 5).reindex(px.index)
    res = bt.run_backtest(px, _Hold(held), multiplier=1000, cost_per_side=52.5)
    d = res.daily
    # a 1-lot short loses exactly 0.1 x $1000 = $100 every day it is held, rolls included
    held_days = d.gross[d.gross != 0]
    assert np.allclose(held_days.values, -100.0)
    # cost: one opening trade, then 2 contracts traded per roll (close old + open new)
    n_rolls = (held.front != held.front.shift()).sum() - 1
    assert d.cost.sum() == 52.5 * (1 + 2 * n_rolls)


def test_sr3_position_changes_chain_across_roll():
    # pos1 is X until X stops trading, then Y. X and Y sit 50 bp apart; each moves +1 bp a day.
    dates = pd.bdate_range("2024-01-01", periods=6)
    names = pd.DataFrame({1: ["X", "X", "X", "Y", "Y", "Y"]}, index=dates)
    rates = pd.DataFrame({"X": [100, 101, 102, 103, np.nan, np.nan], "Y": [150, 151, 152, 153, 154, 155]}, index=dates)
    ch = chained_position_changes(rates, names)
    assert ch[1].iloc[1:].tolist() == [1, 1, 1, 1, 1]  # the 50 bp level gap never shows up
