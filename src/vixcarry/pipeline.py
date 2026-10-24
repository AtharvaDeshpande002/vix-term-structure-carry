"""Glue: run every step in order and return (and save) the result tables.

`run(cfg)` is what scripts/run_all.py, the notebook and screen_today.py call, so all three always agree.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from . import backtest as bt
from . import crossasset as xa
from . import load
from . import seasonality as seas
from .strategies import CarrySpec, CarryStrategy, default_specs
from .termstructure import build_term_structure, curve_on_grid


def vx_cost_per_side(cfg: dict) -> float:
    v = cfg["vx"]
    return v["slippage_ticks"] * v["tick_value"] + v["commission"]


def run_strategy(spec: CarrySpec, ts: pd.DataFrame, px: pd.DataFrame, cfg: dict) -> bt.BacktestResult:
    strat = CarryStrategy(spec, ts, px, cfg)
    res = bt.run_backtest(px, strat, cfg["vx"]["multiplier"], vx_cost_per_side(cfg))
    res.exits = strat.exits  # how many trades ended on a spike, a stop, or the contango filter switching off
    return res


def choose_parameters(ts, px, cfg) -> tuple[float, float, pd.DataFrame]:
    """Pick the contango threshold and the stop on the IN-SAMPLE period only.

    Grid = every threshold x every stop of config.yaml, run on the "spike exit + stop" variant. The pair with the
    best in-sample Sharpe wins. The out-of-sample columns are kept for the robustness heatmap and the honesty
    check ("did the in-sample winner also win afterwards?") but play no part in the choice.
    """
    s, c = cfg["sample"], cfg["carry"]
    rows = []
    for th in c["threshold_grid"]:
        for st in c["stop_grid"]:
            r = run_strategy(CarrySpec("grid", "front", th, spike_exit=True, stop_volpts=st), ts, px, cfg)
            ins = bt.metrics(r, s["start"], s["in_sample_end"])
            oos = bt.metrics(r, s["out_of_sample_start"], None)
            rows.append({"threshold": th, "stop_volpts": st, "is_sharpe": ins["sharpe"], "is_net_usd": ins["net_usd"],
                         "oos_sharpe": oos["sharpe"], "oos_net_usd": oos["net_usd"], "stops_hit": r.exits["stop"]})
    g = pd.DataFrame(rows)
    best = g.loc[g.is_sharpe.idxmax()]
    return float(best.threshold), float(best.stop_volpts), g


def run(cfg: dict, save: bool = True) -> dict:
    out: dict = {}
    s = cfg["sample"]
    vx = load.load_vx(cfg)
    daily = load.load_daily(cfg)
    ts_all = build_term_structure(vx, daily, cfg)
    ts = ts_all.loc[s["start"]:]
    px = load.wide(vx).loc[s["start"]:]
    out.update(vx=vx, daily=daily, ts=ts, ts_all=ts_all, px=px)

    # ---- Step 1 descriptive
    yearly = ts.groupby(ts.index.year).agg(contango_share=("in_contango", "mean"), avg_contango=("contango", "mean"),
                                           avg_basis=("basis", "mean"), avg_roll_yield=("roll_yield", "mean"),
                                           days=("in_contango", "size"))
    out["contango_by_year"] = yearly
    grid = np.arange(0, 241, 10)
    out["curve_grid"] = curve_on_grid(vx[vx.date >= s["start"]], grid)
    vrp = ts[["vix", "rv_forward", "vrp"]].dropna()
    out["vrp"] = vrp

    # ---- Step 2 carry backtests
    th, stop, grid_tbl = choose_parameters(ts, px, cfg)
    out["threshold"], out["stop"], out["threshold_grid"] = th, stop, grid_tbl
    specs = default_specs(th, stop)
    results = {sp.name: run_strategy(sp, ts, px, cfg) for sp in specs}
    out["results"], out["specs"] = results, specs
    rows = []
    for name, r in results.items():
        for period, a, b in [("in-sample", s["start"], s["in_sample_end"]), ("out-of-sample", s["out_of_sample_start"], None),
                             ("full", s["start"], None)]:
            rows.append({"strategy": name, "period": period, **bt.metrics(r, a, b)})
    out["summary"] = pd.DataFrame(rows)

    # ---- tail analysis
    trows = []
    for wname, (a, b) in cfg["tails"].items():
        for name, r in results.items():
            trows.append({"window": wname, "strategy": name, **bt.tail_stats(r, a, b)})
    tails = pd.DataFrame(trows)
    # Aug-2015: the data has no front-month VX then (the nearest listed contract was Jan-2016), so we show a proxy:
    # a 1-lot short in the nearest listed contract through the window.
    a, b = cfg["tails"]["Aug-2015 (China deval)"]
    near = vx[(vx.date >= a) & (vx.date <= b)]
    if len(near):
        c0 = near.sort_values(["date", "expiry"]).groupby("date").contract.first().iloc[0]
        p = near[near.contract == c0].set_index("date").settle
        pnl = -p.diff().fillna(0) * cfg["vx"]["multiplier"]
        eq = pnl.cumsum()
        out["aug2015_proxy"] = {"contract": c0, "pnl_usd": float(pnl.sum()) - 2 * vx_cost_per_side(cfg),
                                "worst_day_usd": float(pnl.min()), "max_dd_usd": float(bt.drawdown(eq).min())}
    out["tails"] = tails

    # ---- Step 3 seasonality
    ts_s = ts.assign(front_spread=ts.VX1 - ts.VX2)
    out["season_spread"] = seas.by_days_to_expiry(ts_s, "front_spread", 25)
    out["season_basis"] = seas.by_days_to_expiry(ts_s, "basis", 25)
    out["season_now_spread"] = seas.current_cycle(ts_s, "front_spread")
    out["season_now_basis"] = seas.current_cycle(ts_s, "basis")

    # ---- Step 4 cross-asset
    sr3 = load.load_sr3(cfg)
    zq = load.load_zq(cfg)
    n = cfg["sr3"]["positions"]
    names = xa.sr3_positions(sr3, n)
    rates = load.wide(sr3, "rate_bp")
    pos_chg = xa.chained_position_changes(rates, names)
    pos_chg.columns = [f"pos{k}" for k in pos_chg.columns]
    zqc = xa.zq_12m_changes(zq)
    rates_chg = pd.DataFrame({
        "SR3 1y spread (pos1-pos5)": pos_chg.pos1 - pos_chg.pos5,
        "SR3 pos4 rate": pos_chg.pos4,
        "ZQ 12m implied change": zqc.d_zq12m,
    })
    out["pos_chg"], out["zq12m"], out["rates_chg"] = pos_chg, zqc, rates_chg
    ev = xa.inversion_events(ts, cfg["events"]["min_contango_days"])
    out["events"] = ev
    e = cfg["events"]
    paths, summ = {}, []
    for col in rates_chg:
        p = xa.event_paths(rates_chg[col].loc[s["start"]:], ev, e["pre"], e["post"])
        paths[col] = p
        sm = xa.summarise_paths(p)
        sm["series"] = col
        summ.append(sm.reset_index().rename(columns={"index": "offset"}))
    out["event_paths"], out["event_summary"] = paths, pd.concat(summ, ignore_index=True)

    dslope = xa.vx_slope_changes(ts, load.wide(vx))
    out["dslope"] = dslope
    ll = pd.DataFrame({
        "SR3 pos2": xa.cross_correlation(dslope, pos_chg.pos2, e["max_lag"]),
        "ZQ 12m": xa.cross_correlation(dslope, zqc.d_zq12m, e["max_lag"]),
    })
    ll.index.name = "lag"
    out["leadlag"] = ll
    g1 = xa.granger(dslope, pos_chg.pos2, e["granger_maxlag"]).assign(test="VX slope -> SR3 pos2")
    g2 = xa.granger(pos_chg.pos2, dslope, e["granger_maxlag"]).assign(test="SR3 pos2 -> VX slope")
    out["granger"] = pd.concat([g1, g2], ignore_index=True)
    out["stress_weeks"] = xa.stress_week_table(daily.vix.loc[s["start"]:], pos_chg, e["cond_week_vix_rise"])

    k = f"pos{e['sr3_trade_position']}"
    trades = xa.sr3_event_trade(ev, pos_chg[k], e["sr3_hold_days"], cfg)
    base = xa.unconditional_trade(pos_chg[k], e["sr3_hold_days"], cfg)
    trades["period"] = np.where(trades.entry < pd.Timestamp(s["out_of_sample_start"]), "in-sample", "out-of-sample")
    out["sr3_trades"] = trades
    tr_rows = []
    for per, a, b in [("in-sample", None, s["in_sample_end"]), ("out-of-sample", s["out_of_sample_start"], None), ("all", None, None)]:
        t = trades if per == "all" else trades[trades.period == per]
        bb = base.loc[a:b]
        tr_rows.append({"period": per, "events": len(t), "avg_net_usd": t.net_usd.mean(), "hit_rate": (t.net_usd > 0).mean(),
                        "total_net_usd": t.net_usd.sum(), "baseline_avg_net_usd": bb.mean(),
                        "baseline_hit_rate": (bb > 0).mean()})
    out["sr3_translation"] = pd.DataFrame(tr_rows)

    out["key"] = key_numbers(out, cfg)
    if save:
        save_tables(out, cfg)
    return out


def key_numbers(o: dict, cfg: dict) -> dict:
    """The handful of numbers quoted in the README / resume bullets, computed (never typed by hand)."""
    sm = o["summary"].set_index(["strategy", "period"])
    best = "+ spike exit + stop"
    k = {
        "sample_start": str(o["ts"].index[0].date()), "sample_end": str(o["ts"].index[-1].date()),
        "contango_share": float(o["ts"].in_contango.mean()),
        "avg_roll_yield_contango": float(o["ts"].loc[o["ts"].in_contango, "roll_yield"].mean()),
        "avg_basis_contango": float(o["ts"].loc[o["ts"].in_contango, "basis"].mean()),
        "avg_vrp": float(o["vrp"].vrp.mean()), "vrp_positive_share": float((o["vrp"].vrp > 0).mean()),
        "vrp_start": str(o["vrp"].index[0].date()),
        "threshold": o["threshold"], "stop": o["stop"], "n_events": int(len(o["events"])),
        "exits": {name: r.exits for name, r in o["results"].items()},
        "events": [str(d.date()) for d in o["events"]],
    }
    for name in sm.index.get_level_values(0).unique():
        for per in ["in-sample", "out-of-sample", "full"]:
            m = sm.loc[(name, per)]
            k[f"{name} | {per}"] = {x: (float(m[x]) if isinstance(m[x], (int, float, np.floating, np.integer)) else str(m[x]))
                                    for x in ["sharpe", "net_usd", "max_dd_usd", "worst_day_usd", "worst_week_usd", "trades", "hit_rate", "time_in_market"]}
    k["best_variant"] = best
    tl = o["tails"].set_index(["window", "strategy"])
    k["tails"] = {w: {s_: {"pnl_usd": float(tl.loc[(w, s_), "pnl_usd"]), "max_dd_usd": float(tl.loc[(w, s_), "max_dd_usd"]),
                           "worst_day_usd": float(tl.loc[(w, s_), "worst_day_usd"])}
                      for s_ in ["Short front, always", best, "Contango > 0 + spike exit + stop", "Calendar 1:1 (short VX1 / long VX2)"]}
                  for w in cfg["tails"]}
    if "aug2015_proxy" in o:
        k["aug2015_proxy"] = o["aug2015_proxy"]
    es = o["event_summary"]
    for ser in es.series.unique():
        r = es[(es.series == ser) & (es.offset == cfg["events"]["post"])].iloc[0]
        r10 = es[(es.series == ser) & (es.offset == 10)].iloc[0]
        k[f"event +{cfg['events']['post']}d {ser}"] = {"mean": float(r["mean"]), "lo": float(r.lo), "hi": float(r.hi), "n": int(r.n)}
        k[f"event +10d {ser}"] = {"mean": float(r10["mean"]), "lo": float(r10.lo), "hi": float(r10.hi), "n": int(r10.n)}
    ll = o["leadlag"]["SR3 pos2"]
    k["leadlag_lag0"] = float(ll.loc[0])
    k["leadlag_max_abs_nonzero"] = {"lag": int(ll.drop(0).abs().idxmax()), "corr": float(ll.drop(0).loc[ll.drop(0).abs().idxmax()])}
    g = o["granger"]
    k["granger_min_p"] = {t: float(g[g.test == t].p_value.min()) for t in g.test.unique()}
    k["sr3_translation"] = o["sr3_translation"].to_dict(orient="records")
    sw = o["stress_weeks"].set_index("position")
    k["stress_weeks"] = {p: {"diff_bp": float(sw.loc[p, "difference_bp"]), "t": float(sw.loc[p, "t_stat"]),
                             "n_stress": int(sw.loc[p, "n_stress"])} for p in sw.index}
    return k


def save_tables(o: dict, cfg: dict) -> None:
    res = cfg["paths"]["results"]
    res.mkdir(parents=True, exist_ok=True)
    o["summary"].to_csv(res / "strategy_summary.csv", index=False, float_format="%.4f")
    o["threshold_grid"].to_csv(res / "threshold_grid.csv", index=False, float_format="%.4f")
    o["tails"].to_csv(res / "tail_windows.csv", index=False, float_format="%.2f")
    o["contango_by_year"].to_csv(res / "contango_by_year.csv", float_format="%.4f")
    o["season_spread"].to_csv(res / "seasonality_vx1_minus_vx2.csv", float_format="%.4f")
    o["season_basis"].to_csv(res / "seasonality_basis.csv", float_format="%.4f")
    o["event_summary"].to_csv(res / "event_study_summary.csv", index=False, float_format="%.3f")
    o["leadlag"].to_csv(res / "leadlag_crosscorr.csv", float_format="%.4f")
    o["granger"].to_csv(res / "granger.csv", index=False, float_format="%.4f")
    o["stress_weeks"].to_csv(res / "stress_weeks_sr3.csv", index=False, float_format="%.4f")
    o["sr3_translation"].to_csv(res / "sr3_inversion_trade.csv", index=False, float_format="%.2f")
    o["sr3_trades"].to_csv(res / "sr3_inversion_trade_list.csv", index=False, float_format="%.2f")
    pd.Series([str(d.date()) for d in o["events"]], name="inversion_date").to_csv(res / "inversion_events.csv", index=False)
    (res / "key_numbers.json").write_text(json.dumps(o["key"], indent=1, default=str), encoding="utf-8")
