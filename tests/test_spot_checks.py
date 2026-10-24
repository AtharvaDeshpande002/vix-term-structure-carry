"""Three dates checked by hand against the raw settlement file (see tests/SPOT_CHECKS.md for the working).

Skipped automatically when data/raw/ is absent (raw data is licensed and not committed).
"""
import pandas as pd
import pytest

from conftest import needs_data

CHECKS = {
    # date: (VX1, VX2, spot VIX, held contract, held contract's change since the previous session)
    "2018-02-05": ("VXG18", 33.225, 27.975, 37.32, "VXG18", 33.225 - 15.625),
    "2020-03-16": ("VXH20", 72.625, 59.15, 82.69, "VXJ20", 59.15 - 43.9),
    "2024-08-05": ("VXQ24", 32.0986, 30.3911, 38.57, "VXQ24", 32.0986 - 21.8527),
}


@pytest.fixture(scope="module")
def run():
    from vixcarry import pipeline
    from vixcarry.config import load_config
    return pipeline.run(load_config(), save=False)


@needs_data
@pytest.mark.parametrize("day", list(CHECKS))
def test_term_structure_values(run, day):
    c1, vx1, vx2, vix, _, _ = CHECKS[day]
    r = run["ts"].loc[day]
    assert r.c1 == c1
    assert r.VX1 == pytest.approx(vx1) and r.VX2 == pytest.approx(vx2)
    assert r.basis == pytest.approx(vx1 - vix)
    assert r.contango == pytest.approx(vx2 / vx1 - 1)


@needs_data
@pytest.mark.parametrize("day", list(CHECKS))
def test_always_short_pnl_on_shock_days(run, day):
    *_, held, chg = CHECKS[day]
    d = run["results"]["Short front, always"].daily
    # a 1-lot short loses the held contract's rise x $1000 (no trade that day, so no cost)
    assert d.loc[day, "gross"] == pytest.approx(-chg * 1000)


@needs_data
def test_signal_on_shock_day(run):
    # 5-Feb-2018 closed inverted (VX2 < VX1): every filtered strategy must be flat the next day
    d = run["results"]["+ spike exit + stop"].daily
    nxt = d.index[d.index.get_loc(pd.Timestamp("2018-02-05")) + 2]
    assert d.loc[nxt, "exposure"] == 0
