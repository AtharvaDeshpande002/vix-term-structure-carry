"""Shared test helpers: a small synthetic VX market whose answers can be worked out by hand."""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from vixcarry.config import load_config  # noqa: E402

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"
needs_data = pytest.mark.skipif(not (RAW / "vx_settles.csv").exists(), reason="raw data not present (not committed)")


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def synthetic_vx():
    """Three monthly contracts over ~2 months of business days.

    Each contract has its own, very different price level (A=15, B=25, C=35) and drifts by +0.1 a day, so a
    "generic" series that naively differenced across a roll would show a fake +10 jump.
    """
    dates = pd.bdate_range("2024-01-01", "2024-03-29")
    exp = {"A": pd.Timestamp("2024-01-17"), "B": pd.Timestamp("2024-02-14"), "C": pd.Timestamp("2024-03-20"),
           "D": pd.Timestamp("2024-04-17")}
    base = {"A": 15.0, "B": 25.0, "C": 35.0, "D": 45.0}
    rows = []
    for i, d in enumerate(dates):
        for c, e in exp.items():
            if d <= e:
                rows.append({"date": d, "contract": c, "settle": base[c] + 0.1 * i, "expiry": e})
    return pd.DataFrame(rows).sort_values(["date", "expiry"]).reset_index(drop=True)
