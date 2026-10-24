"""Load the raw settlement CSVs described in data/README.md into tidy pandas tables.

Everything downstream works on two shapes:
  * long tables  — one row per (date, contract), with the contract's expiry attached;
  * wide tables  — dates down, one column per FIXED contract (never a rolling "generic" column).
Keeping contracts as their own columns is what makes roll-safe returns trivial: a daily change is always
today's settle minus yesterday's settle of the SAME contract.
"""
from __future__ import annotations

import pandas as pd


def _read(cfg: dict, name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(cfg["paths"]["raw"] / name, **kw)


def _clip(df: pd.DataFrame, cfg: dict, col: str = "date") -> pd.DataFrame:
    """Drop rows after the configured sample end (None = keep everything)."""
    end = cfg["sample"].get("end")
    return df[df[col] <= pd.Timestamp(end)] if end else df


def load_vx(cfg: dict) -> pd.DataFrame:
    """VX futures settles, long format: date, contract, settle, expiry."""
    s = _read(cfg, "vx_settles.csv", parse_dates=["date"])
    k = _read(cfg, "vx_contracts.csv", parse_dates=["expiry"])
    df = s.merge(k[["contract", "expiry"]], on="contract", how="inner")
    df = df[df.settle > 0].dropna(subset=["settle"])  # a VX settle can never be zero or negative
    return _clip(df.sort_values(["date", "expiry"]).reset_index(drop=True), cfg)


def load_daily(cfg: dict) -> pd.DataFrame:
    """Daily index/rate series (VIX family, S&P 500, SOFR, Fed target, Treasury yields), indexed by date."""
    d = _read(cfg, "daily_series.csv", parse_dates=["date"]).set_index("date").sort_index()
    end = cfg["sample"].get("end")
    return d.loc[:end] if end else d


def load_sr3(cfg: dict) -> pd.DataFrame:
    """Quarterly SR3 settles, long format: date, contract, settle, last_trade, rate_bp (= (100 - price) x 100)."""
    s = _read(cfg, "sr3_settles.csv", parse_dates=["date"])
    k = _read(cfg, "sr3_contracts.csv", parse_dates=["last_trade"])
    k = k[k.quarterly.astype(str).str.lower() == "true"]  # serial (monthly) SR3 contracts are not used
    df = s.merge(k[["contract", "ref_month", "last_trade"]], on="contract", how="inner").dropna(subset=["settle"])
    df["rate_bp"] = (100.0 - df.settle) * 100.0  # SR3 rate = 100 - price, in basis points
    return _clip(df.sort_values(["date", "last_trade"]).reset_index(drop=True), cfg)


def load_zq(cfg: dict) -> pd.DataFrame:
    """30-day Fed funds futures settles: date, contract, month (period), rate_bp."""
    s = _read(cfg, "zq_settles.csv", parse_dates=["date"])
    k = _read(cfg, "zq_contracts.csv")
    df = s.merge(k[["contract", "month"]], on="contract", how="inner").dropna(subset=["settle"])
    df["month"] = pd.PeriodIndex(df["month"], freq="M")
    df["rate_bp"] = (100.0 - df.settle) * 100.0
    return _clip(df.sort_values(["date", "month"]).reset_index(drop=True), cfg)


def wide(df: pd.DataFrame, value: str = "settle") -> pd.DataFrame:
    """Dates x fixed contracts table of `value`."""
    return df.pivot_table(index="date", columns="contract", values=value, aggfunc="last").sort_index()
