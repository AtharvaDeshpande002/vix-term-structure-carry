"""Static charts (matplotlib, PNG >= 150 dpi) for the README and the notebook.

One style everywhere: white background, recessive grid, one colour per series in a fixed order, titles that state
the FINDING (computed from the results, never typed by hand), units on every axis and a source note.
"""
from __future__ import annotations

import pathlib
import sys

import matplotlib

if "ipykernel" not in sys.modules:  # scripts render straight to files; the notebook keeps its inline backend
    matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# fixed categorical order (colour follows the series, never its rank)
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SOURCE = "Source: Bloomberg settlement data; author's calculations"
STRAT_COLOURS = {"Short front, always": BLUE, "+ spike exit + stop": ORANGE, "Calendar 1:1 (short VX1 / long VX2)": AQUA,
                 "Contango > 0 + spike exit + stop": VIOLET}


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titlesize": 12.5,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.labelsize": 10,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.6, "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 9,
        "ytick.labelsize": 9, "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 1.6,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "figure.dpi": 100,
        "text.parse_math": False,  # a "$" in a title is a dollar sign, not maths
    })


def _finish(fig, path: pathlib.Path | None, note: str = SOURCE):
    fig.text(0.01, 0.005, note, fontsize=7.5, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=160)
    return fig


def _annotate(ax, cfg, ymax_frac=0.97, keys=None):
    for name, d in cfg["annotations"].items():
        if keys and name not in keys:
            continue
        x = pd.Timestamp(d)
        lo, hi = ax.get_xlim()
        if not (lo <= mdates.date2num(x) <= hi):
            continue
        ax.axvline(x, color=MUTED, lw=0.7, ls=":", zorder=0)
        ax.text(x, ax.get_ylim()[0] + (ax.get_ylim()[1] - ax.get_ylim()[0]) * ymax_frac, " " + name, rotation=90,
                va="top", ha="left", fontsize=7.5, color=INK2)


def usd(x: float) -> str:
    return f"-${abs(x) / 1000:,.0f}k" if x < 0 else f"${x / 1000:,.0f}k"


# ------------------------------------------------------------------------------------------------ charts
def heatmap(o, cfg, path=None):
    g = o["curve_grid"].resample("W-FRI").last().dropna(how="all")
    g = g.loc[:, g.columns >= 30]  # below ~30 days only VX1 exists on some days, so the grid would be patchy
    ts = o["ts"]
    share = o["key"]["contango_share"]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 5.6), height_ratios=[6, 0.6], sharex=True)
    x = mdates.date2num(g.index)
    m = ax.pcolormesh(x, g.columns, g.T.values, cmap="Blues", shading="nearest", vmin=10, vmax=40)
    cb = fig.colorbar(m, ax=[ax, ax2], pad=0.01, fraction=0.03)
    cb.set_label("VX futures level (vol pts)")
    ax.set_ylabel("days to expiry")
    ax.set_title(f"The VX curve slopes upward {share:.0%} of days; it inverts only in short, violent bursts")
    ax.grid(False)
    inv = (ts.slope < 0).astype(float).resample("W-FRI").max()
    ax2.bar(mdates.date2num(inv.index), inv.values, width=7, color=RED, align="center")
    ax2.set_yticks([]); ax2.set_ylabel("inverted", rotation=0, ha="right", va="center", fontsize=8.5)
    ax2.grid(False)
    ax2.xaxis_date()
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.01, 0.005, SOURCE + ". Weekly snapshots, each curve interpolated onto a fixed days-to-expiry grid; "
             "red = a week with VX1 > VX2.", fontsize=7.5, color=MUTED)
    if path:
        fig.savefig(path, dpi=160, bbox_inches="tight")
    return fig


def curve_today(o, cfg, path=None):
    g = o["curve_grid"]
    q = g.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    vx = o["vx"]
    t = vx.date.max()
    today = vx[(vx.date == t) & (vx.expiry > t)].assign(dte=lambda x: (x.expiry - x.date).dt.days)
    pct = [(g[c].dropna() <= np.interp(c, today.dte, today.settle)).mean() * 100 for c in [30, 120]]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.fill_between(q.columns, q.loc[0.1], q.loc[0.9], color=BLUE, alpha=0.12, lw=0, label="10th-90th percentile, 2016-today")
    ax.fill_between(q.columns, q.loc[0.25], q.loc[0.75], color=BLUE, alpha=0.22, lw=0, label="25th-75th percentile")
    ax.plot(q.columns, q.loc[0.5], color=BLUE, lw=1.2, ls="--", label="median")
    ax.plot(today.dte, today.settle, color=ORANGE, marker="o", ms=5, lw=2, label=f"today ({t:%d-%b-%Y})")
    for _, r in today.iterrows():
        ax.annotate(r.contract, (r.dte, r.settle), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7.5, color=INK2)
    ax.set_xlim(0, 240)
    ax.set_xlabel("days to expiry"); ax.set_ylabel("vol pts")
    ax.set_title(f"Today's VX curve sits at the {pct[0]:.0f}th percentile at 30 days and the {pct[1]:.0f}th at 120 days")
    ax.legend(loc="upper right", ncols=2)
    return _finish(fig, path)


def contango_by_year(o, cfg, path=None):
    y = o["contango_by_year"]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(y.index.astype(str), y.contango_share * 100, color=BLUE, width=0.6)
    for i, v in enumerate(y.contango_share * 100):
        ax.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=8.5, color=INK2)
    ax.set_ylim(0, 108); ax.set_ylabel("% of trading days with VX2 > VX1")
    lo = y.contango_share.idxmin()
    ax.set_title(f"Contango is the normal state; the worst year ({lo}) still spent {y.contango_share.min():.0%} of days in it")
    ax.grid(axis="x", visible=False)
    return _finish(fig, path, SOURCE + f". {y.index.max()} = year to date.")


def equity_curves(o, cfg, path=None):
    oos = pd.Timestamp(cfg["sample"]["out_of_sample_start"])
    k = o["key"]
    fig, ax = plt.subplots(figsize=(11, 5))
    for name, col in STRAT_COLOURS.items():
        eq = o["results"][name].daily.net.cumsum() / 1000
        ax.plot(eq.index, eq.values, color=col, lw=1.6, label=name)
        ax.annotate(name if len(name) < 22 else name.split(" (")[0], (eq.index[-1], eq.iloc[-1]), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=8, color=INK2)
    base = o["results"]["Short front, always"].daily.net.cumsum() / 1000
    dd = base - base.cummax()
    ax.fill_between(dd.index, base.cummax(), base, where=dd < 0, color=BLUE, alpha=0.08, lw=0, label="drawdown (always short)")
    ax.axvspan(oos, base.index[-1], color=GRID, alpha=0.35, lw=0, zorder=0)
    ax.text(oos, ax.get_ylim()[1], "  out-of-sample", va="top", fontsize=8.5, color=INK2)
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel("cumulative net P&L, 1 contract ($ thousands)")
    a = k["Short front, always | full"]
    b = k["Contango > 0 + spike exit + stop | full"]
    ax.set_title(f"Always-short earns the most (Sharpe {a['sharpe']:.2f}) but pays for it with a {usd(a['max_dd_usd'])} drawdown; "
                 f"the simple exits keep Sharpe {b['sharpe']:.2f} at {usd(b['max_dd_usd'])}", fontsize=11.5)
    ax.legend(loc="upper left")
    _annotate(ax, cfg, keys=["Feb-2018", "Mar-2020", "Aug-2024", "Apr-2025", "2026 shock"])
    ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    return _finish(fig, path, SOURCE + ". Net of 1 tick + $2.50 per contract per side. Signal at close t, trade at close t+1.")


def tail_chart(o, cfg, path=None):
    t = o["tails"]
    wins = [w for w in cfg["tails"] if not t[t.window == w].pnl_usd.isna().all()]
    names = list(STRAT_COLOURS)
    x = np.arange(len(wins))
    w = 0.8 / len(names)
    fig, ax = plt.subplots(figsize=(11.5, 5))
    for i, n in enumerate(names):
        v = [t[(t.window == win) & (t.strategy == n)].max_dd_usd.iloc[0] / 1000 for win in wins]
        xs = x + (i - (len(names) - 1) / 2) * w
        ax.bar(xs, v, width=w - 0.02, color=STRAT_COLOURS[n], label=n)
        for xi, vi in zip(xs, v):  # label every bar; a zero bar means "was flat"
            ax.text(xi, vi - 0.8, "flat" if abs(vi) < 0.05 else f"{vi:,.1f}", ha="center", va="top", fontsize=7.5, color=INK2)
    ax.set_xticks(x, [s.replace(" (", "\n(") for s in wins])
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel("worst drawdown inside the window ($ thousands, 1 contract)")
    worst = t[t.strategy == "Short front, always"].set_index("window").max_dd_usd
    ref = t[t.strategy == "Contango > 0 + spike exit + stop"].set_index("window").max_dd_usd.dropna()
    ax.set_title(f"Always-short drew down {usd(worst.min())} per contract in {worst.idxmin().split(' (')[0]}; "
                 f"simple exits cap the worst window at {usd(ref.min())} (one overnight gap)")
    ax.legend(loc="lower right")
    ax.grid(axis="x", visible=False)
    p = o.get("aug2015_proxy")
    note = SOURCE + ". Aug-2015 is not shown: the data has no front-month VX before Dec-2015"
    if p:
        note += f" (a short in the nearest listed contract, {p['contract']}, drew down {usd(p['max_dd_usd'])})"
    return _finish(fig, path, note + ".")


def seasonality(o, cfg, path=None):
    s = o["season_spread"]
    now = o["season_now_spread"]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = s.index
    ax.fill_between(x, s.p10, s.p90, color=BLUE, alpha=0.12, lw=0, label="10th-90th percentile")
    ax.fill_between(x, s.p25, s.p75, color=BLUE, alpha=0.24, lw=0, label="25th-75th percentile")
    ax.plot(x, s.p50, color=BLUE, lw=1.6, label="median")
    ax.plot(now.index, now.values, color=ORANGE, marker="o", ms=4, lw=2, label="current cycle")
    ax.invert_xaxis()
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_xlabel("business days to VX1 expiry"); ax.set_ylabel("VX1 - VX2 (vol pts)")
    far, near = s.p50.loc[s.index.max()], s.p50.loc[s.index.min()]
    word = "widens" if near < far else "narrows"
    ax.set_title(f"VX2's premium over VX1 {word} into expiry: median VX1-VX2 {far:.2f} at {s.index.max()} days, "
                 f"{near:.2f} on the last day")
    ax.legend(loc="lower right", ncols=2)
    return _finish(fig, path)


def event_study(o, cfg, path=None):
    es = o["event_summary"]
    series = list(es.series.unique())
    fig, axes = plt.subplots(1, len(series), figsize=(12, 4.2), sharex=True)
    cols = [BLUE, ORANGE, AQUA]
    for ax, ser, c in zip(axes, series, cols):
        d = es[es.series == ser]
        ax.fill_between(d.offset, d.lo, d.hi, color=c, alpha=0.18, lw=0)
        ax.plot(d.offset, d["mean"], color=c, lw=2)
        ax.axvline(0, color=MUTED, lw=0.8, ls=":")
        ax.axhline(0, color=AXIS, lw=0.8)
        ax.set_title(f"{ser}\n(n = {int(d.n.max())} inversions)", fontsize=10)
        ax.set_xlabel("business days from inversion")
    axes[0].set_ylabel("change vs inversion-day close (bp)")
    e = cfg["events"]
    d4 = es[es.series == "SR3 pos4 rate"].set_index("offset")
    into, after = -d4.loc[-e["pre"], "mean"], d4.loc[e["post"], "mean"]
    verb_in = "falls" if into < 0 else "rises"
    verb_out = "rises" if after > 0 else "falls"
    fig.suptitle(f"On average the SR3 pos4 rate {verb_in} {abs(into):.1f} bp INTO a VIX inversion, then {verb_out} "
                 f"{abs(after):.1f} bp over the next {e['post']} days: no rally left to chase", x=0.01, ha="left",
                 fontsize=12.5, fontweight="bold")
    return _finish(fig, path, SOURCE + ". Mean path with 95% confidence band. Rate changes measured on fixed contracts "
                   "and chained across rolls.")


def leadlag(o, cfg, path=None):
    ll = o["leadlag"]["SR3 pos2"]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(ll.index, ll.values, color=[ORANGE if l == 0 else BLUE for l in ll.index], width=0.7)
    n = o["dslope"].dropna().index.intersection(o["pos_chg"].pos2.dropna().index).size
    band = 1.96 / np.sqrt(n)
    ax.axhspan(-band, band, color=GRID, alpha=0.6, lw=0, zorder=0)
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_xlabel("lag (days): positive = VX slope change leads the SR3 move")
    ax.set_ylabel("correlation")
    k = o["key"]
    pos = ll.drop(0)
    lag_best = int(pos.idxmax())
    gp = k["granger_min_p"]["VX slope -> SR3 pos2"]
    ax.set_title(f"VIX slope and SOFR move mostly on the SAME day (corr {k['leadlag_lag0']:.2f}); the best lagged echo "
                 f"(+{lag_best}d) is only {pos.max():.2f} (Granger p = {gp:.3f})")
    ax.grid(axis="x", visible=False)
    return _finish(fig, path, SOURCE + ". Daily changes, VX2-VX1 vs SR3 2nd quarterly contract rate, from 2018. "
                   "Grey band = +-1.96/sqrt(n), the zero-correlation noise range.")


def vrp_chart(o, cfg, path=None):
    v = o["vrp"]
    k = o["key"]
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.plot(v.index, v.vix, color=BLUE, lw=1.3, label="VIX (implied, 30-day)")
    ax.plot(v.index, v.rv_forward, color=ORANGE, lw=1.3, label="S&P 500 realised vol, next 21 days")
    ax.fill_between(v.index, v.vix, v.rv_forward, where=v.vrp < 0, color=RED, alpha=0.25, lw=0, label="realised > implied")
    ax.set_ylabel("vol pts (annualised)")
    ax.set_title(f"Implied beat realised vol on {k['vrp_positive_share']:.0%} of days (avg premium {k['avg_vrp']:.1f} vol pts): "
                 "the premium carry sellers collect")
    ax.set_ylim(0, 66)
    ax.legend(loc="upper left", ncols=3)
    _annotate(ax, cfg, ymax_frac=0.88, keys=["Hikes start", "Aug-2024", "Apr-2025", "2026 shock"])
    return _finish(fig, path, SOURCE + f". S&P 500 data in this set starts {k['vrp_start']}.")


def robustness(o, cfg, path=None):
    g = o["threshold_grid"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, col, ttl in zip(axes, ["is_sharpe", "oos_sharpe"], ["in-sample 2016-2021", "out-of-sample 2022-today"]):
        p = g.pivot(index="stop_volpts", columns="threshold", values=col)
        m = ax.imshow(p.values, cmap="RdBu", vmin=-1, vmax=1, aspect="auto", origin="lower")
        ax.set_xticks(range(p.shape[1]), [f"{c:.1%}" for c in p.columns])
        ax.set_yticks(range(p.shape[0]), [f"{r:g}" for r in p.index])
        for i in range(p.shape[0]):
            for j in range(p.shape[1]):
                ax.text(j, i, f"{p.values[i, j]:.2f}", ha="center", va="center", fontsize=8.5, color=INK)
        ax.set_xlabel("contango entry threshold (VX2/VX1 - 1)")
        ax.set_title(ttl, fontsize=10.5)
        ax.grid(False)
    axes[0].set_ylabel("stop (vol pts)")
    fig.colorbar(m, ax=axes, fraction=0.025, pad=0.01).set_label("net Sharpe")
    th, st = o["threshold"], o["stop"]
    chosen = g[(g.threshold == th) & (g.stop_volpts == st)].iloc[0]
    best_oos = g.loc[g.oos_sharpe.idxmax()]
    fig.suptitle(f"The in-sample winner ({th:.1%} threshold, {st:g}-pt stop) scores {chosen.oos_sharpe:.2f} out of sample; "
                 f"the best OOS cell used a {best_oos.threshold:.1%} threshold ({best_oos.oos_sharpe:.2f})",
                 x=0.01, y=1.0, ha="left", fontsize=12.5, fontweight="bold")
    fig.text(0.01, -0.06, SOURCE + ". 'Spike exit + stop' variant, net of costs.", fontsize=7.5, color=MUTED)
    if path:
        fig.savefig(path, dpi=160, bbox_inches="tight")
    return fig


ALL = {
    "01_vx_term_structure_heatmap.png": heatmap,
    "02_vx_curve_today_vs_history.png": curve_today,
    "03_contango_share_by_year.png": contango_by_year,
    "04_carry_equity_curves.png": equity_curves,
    "05_tail_windows.png": tail_chart,
    "06_expiry_seasonality.png": seasonality,
    "07_inversion_event_study.png": event_study,
    "08_leadlag_crosscorr.png": leadlag,
    "09_vix_vs_realised_vol.png": vrp_chart,
    "10_parameter_robustness.png": robustness,
}


def save_all(o, cfg) -> list[pathlib.Path]:
    style()
    out = []
    for name, fn in ALL.items():
        p = cfg["paths"]["figures"] / name
        p.parent.mkdir(parents=True, exist_ok=True)
        fig = fn(o, cfg, p)
        plt.close(fig)
        out.append(p)
    return out
