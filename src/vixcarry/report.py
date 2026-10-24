"""The interactive report (reports/report.html): every chart in Plotly with hover values, plus the key tables.

Self-contained except for plotly.js, which loads from the CDN, so the file stays small enough for GitHub Pages.
"""
from __future__ import annotations

import html
import pathlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .plots import AQUA, BLUE, GRID, INK, INK2, MUTED, ORANGE, RED, SOURCE, STRAT_COLOURS, usd

LAYOUT = dict(template="plotly_white", font=dict(family="Segoe UI, system-ui, sans-serif", size=12, color=INK2),
              margin=dict(l=60, r=30, t=70, b=60), hovermode="x unified", height=430,
              legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, xanchor="left"))


def _fig(title: str, **kw) -> go.Figure:
    f = go.Figure()
    f.update_layout(**{**LAYOUT, **kw}, title=dict(text=f"<b>{html.escape(title)}</b>", x=0.01, font=dict(size=15, color=INK)))
    return f


def _div(f: go.Figure) -> str:
    return f.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True})


def _table(df: pd.DataFrame) -> str:
    return df.to_html(index=False, classes="tbl", border=0, na_rep="–", escape=True)


def build(o: dict, cfg: dict) -> pathlib.Path:
    k = o["key"]
    figs = []

    # 1 heatmap
    g = o["curve_grid"].resample("W-FRI").last().dropna(how="all")
    f = _fig(f"The VX curve slopes upward {k['contango_share']:.0%} of days; it inverts only in short, violent bursts",
             height=480, hovermode="closest")
    f.add_trace(go.Heatmap(x=g.index, y=g.columns, z=g.T.values, colorscale="Blues", zmin=10, zmax=40,
                           colorbar=dict(title="vol pts"), hovertemplate="%{x|%d-%b-%Y}<br>%{y} days: %{z:.2f}<extra></extra>"))
    inv = o["ts"].slope.lt(0).resample("W-FRI").max()
    inv = inv[inv]
    f.add_trace(go.Scatter(x=inv.index, y=[-6] * len(inv), mode="markers", marker=dict(color=RED, symbol="line-ns-open", size=10),
                           name="VX1 > VX2 (inverted week)", hovertemplate="%{x|%d-%b-%Y} inverted<extra></extra>"))
    f.update_yaxes(title="days to expiry")
    figs.append(("Term structure through time", f))

    # 2 today vs history
    q = o["curve_grid"].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    vx = o["vx"]
    t = vx.date.max()
    today = vx[(vx.date == t) & (vx.expiry > t)].assign(dte=lambda x: (x.expiry - x.date).dt.days)
    f = _fig(f"Today's VX curve ({t:%d-%b-%Y}) against its 2016-today distribution", hovermode="closest")
    f.add_trace(go.Scatter(x=q.columns, y=q.loc[0.9], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    f.add_trace(go.Scatter(x=q.columns, y=q.loc[0.1], fill="tonexty", fillcolor="rgba(42,120,214,0.12)", line=dict(width=0),
                           name="10th-90th pct"))
    f.add_trace(go.Scatter(x=q.columns, y=q.loc[0.75], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    f.add_trace(go.Scatter(x=q.columns, y=q.loc[0.25], fill="tonexty", fillcolor="rgba(42,120,214,0.25)", line=dict(width=0),
                           name="25th-75th pct"))
    f.add_trace(go.Scatter(x=q.columns, y=q.loc[0.5], line=dict(color=BLUE, dash="dash", width=1.5), name="median"))
    f.add_trace(go.Scatter(x=today.dte, y=today.settle, text=today.contract, mode="lines+markers+text", textposition="top center",
                           line=dict(color=ORANGE, width=2.5), name="today"))
    f.update_xaxes(title="days to expiry", range=[0, 240]); f.update_yaxes(title="vol pts")
    figs.append(("Today vs history", f))

    # 3 contango share
    y = o["contango_by_year"]
    f = _fig("Share of days in contango, by year", hovermode="closest")
    f.add_trace(go.Bar(x=y.index.astype(str), y=y.contango_share * 100, marker_color=BLUE, text=(y.contango_share * 100).round(0),
                       texttemplate="%{text:.0f}%", textposition="outside", name="% days VX2 > VX1"))
    f.update_yaxes(title="% of days", range=[0, 110])
    figs.append(("Contango by year", f))

    # 4 equity curves
    a, b = k["Short front, always | full"], k["+ spike exit + stop | full"]
    f = _fig(f"Always-short earns the most (Sharpe {a['sharpe']:.2f}) but with a {usd(a['max_dd_usd'])} drawdown; "
             f"exits cut it to {usd(b['max_dd_usd'])}")
    for name, r in o["results"].items():
        eq = r.daily.net.cumsum()
        f.add_trace(go.Scatter(x=eq.index, y=eq.values, name=name, line=dict(width=2 if name in STRAT_COLOURS else 1,
                    color=STRAT_COLOURS.get(name)), visible=True if name in STRAT_COLOURS else "legendonly",
                    hovertemplate="%{y:$,.0f}"))
    f.add_vrect(x0=pd.Timestamp(cfg["sample"]["out_of_sample_start"]), x1=o["ts"].index[-1], fillcolor=GRID, opacity=0.35, line_width=0,
                annotation_text="out-of-sample", annotation_position="top left")
    f.update_yaxes(title="cumulative net P&L, 1 contract ($)", tickformat="$,.0f")
    figs.append(("Carry strategies (click legend to add variants)", f))

    # 5 tails
    tl = o["tails"].dropna(subset=["pnl_usd"])
    f = _fig("Worst drawdown inside each crisis window, 1 contract", hovermode="closest")
    for name, col in STRAT_COLOURS.items():
        d = tl[tl.strategy == name]
        f.add_trace(go.Bar(x=d.window, y=d.max_dd_usd, name=name, marker_color=col, hovertemplate="%{x}: %{y:$,.0f}"))
    f.update_layout(barmode="group"); f.update_yaxes(title="$", tickformat="$,.0f")
    figs.append(("Tail risk", f))

    # 6 seasonality
    s, now = o["season_spread"], o["season_now_spread"]
    f = _fig("VX1 - VX2 by business days to expiry: history bands vs the current cycle", hovermode="x")
    f.add_trace(go.Scatter(x=s.index, y=s.p90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    f.add_trace(go.Scatter(x=s.index, y=s.p10, fill="tonexty", fillcolor="rgba(42,120,214,0.12)", line=dict(width=0), name="10-90th pct"))
    f.add_trace(go.Scatter(x=s.index, y=s.p75, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    f.add_trace(go.Scatter(x=s.index, y=s.p25, fill="tonexty", fillcolor="rgba(42,120,214,0.25)", line=dict(width=0), name="25-75th pct"))
    f.add_trace(go.Scatter(x=s.index, y=s.p50, line=dict(color=BLUE, width=2), name="median"))
    f.add_trace(go.Scatter(x=now.index, y=now.values, line=dict(color=ORANGE, width=2.5), mode="lines+markers", name="current cycle"))
    f.update_xaxes(title="business days to VX1 expiry", autorange="reversed"); f.update_yaxes(title="vol pts")
    figs.append(("Expiry seasonality", f))

    # 7 event study
    es = o["event_summary"]
    ser = list(es.series.unique())
    f = make_subplots(rows=1, cols=len(ser), subplot_titles=ser, shared_xaxes=True)
    for i, (sname, c) in enumerate(zip(ser, [BLUE, ORANGE, AQUA]), start=1):
        d = es[es.series == sname]
        rgba = f"rgba({int(c[1:3], 16)},{int(c[3:5], 16)},{int(c[5:7], 16)},0.18)"
        f.add_trace(go.Scatter(x=d.offset, y=d.hi, line=dict(width=0), showlegend=False, hoverinfo="skip"), row=1, col=i)
        f.add_trace(go.Scatter(x=d.offset, y=d.lo, fill="tonexty", fillcolor=rgba, line=dict(width=0), showlegend=False,
                               hoverinfo="skip"), row=1, col=i)
        f.add_trace(go.Scatter(x=d.offset, y=d["mean"], line=dict(color=c, width=2.5), name=sname,
                               hovertemplate="day %{x}: %{y:.1f} bp"), row=1, col=i)
        f.add_vline(x=0, line_dash="dot", line_color=MUTED, row=1, col=i)
    f.update_layout(**LAYOUT, title=dict(text="<b>Rates around VIX-curve inversions (mean, 95% band; bp vs inversion-day close)</b>",
                                         x=0.01, font=dict(size=15, color=INK)), showlegend=False)
    f.update_xaxes(title="business days from inversion")
    figs.append(("VIX inversion event study", f))

    # 8 lead-lag
    ll = o["leadlag"]
    f = _fig(f"Lead-lag: VX slope vs rates, daily changes (same-day corr with SR3 pos2 = {k['leadlag_lag0']:.2f})", hovermode="closest")
    f.add_trace(go.Bar(x=ll.index, y=ll["SR3 pos2"], name="SR3 pos2 rate", marker_color=BLUE))
    f.add_trace(go.Bar(x=ll.index, y=ll["ZQ 12m"], name="ZQ 12m implied", marker_color=ORANGE))
    f.update_xaxes(title="lag (days): positive = VX slope leads"); f.update_yaxes(title="correlation")
    figs.append(("Lead-lag", f))

    # 9 VRP
    v = o["vrp"]
    f = _fig(f"VIX vs subsequent realised S&P 500 vol: premium positive on {k['vrp_positive_share']:.0%} of days")
    f.add_trace(go.Scatter(x=v.index, y=v.vix, name="VIX", line=dict(color=BLUE, width=1.5)))
    f.add_trace(go.Scatter(x=v.index, y=v.rv_forward, name="realised vol, next 21d", line=dict(color=ORANGE, width=1.5)))
    f.update_yaxes(title="vol pts")
    figs.append(("Variance risk premium", f))

    # 10 robustness
    gtb = o["threshold_grid"]
    f = make_subplots(rows=1, cols=2, subplot_titles=["in-sample Sharpe", "out-of-sample Sharpe"], shared_yaxes=True)
    for i, col in enumerate(["is_sharpe", "oos_sharpe"], start=1):
        p = gtb.pivot(index="stop_volpts", columns="threshold", values=col)
        f.add_trace(go.Heatmap(x=[f"{c:.1%}" for c in p.columns], y=[f"{r:g} pts" for r in p.index], z=p.values,
                               zmin=-1, zmax=1, colorscale="RdBu", text=np.round(p.values, 2), texttemplate="%{text}",
                               showscale=(i == 2)), row=1, col=i)
    f.update_layout(**{**LAYOUT, "hovermode": "closest"},
                    title=dict(text="<b>Robustness: net Sharpe over entry threshold x stop</b>", x=0.01, font=dict(size=15, color=INK)))
    figs.append(("Parameter robustness", f))

    # tables
    sm = o["summary"]
    keep = ["strategy", "period", "trades", "hit_rate", "net_usd", "sharpe", "max_dd_usd", "worst_day_usd", "worst_week_usd", "costs_usd"]
    tbl = sm[sm.period != "full"][keep].copy()
    for c in ["net_usd", "max_dd_usd", "worst_day_usd", "worst_week_usd", "costs_usd"]:
        tbl[c] = tbl[c].map(lambda x: f"{x:,.0f}")
    tbl["hit_rate"] = tbl.hit_rate.map(lambda x: "–" if pd.isna(x) else f"{x:.0%}")
    tbl["sharpe"] = tbl.sharpe.map(lambda x: f"{x:.2f}")
    tails = o["tails"].dropna(subset=["pnl_usd"]).copy()
    for c in ["pnl_usd", "worst_day_usd", "worst_week_usd", "max_dd_usd"]:
        tails[c] = tails[c].map(lambda x: f"{x:,.0f}")
    trans = o["sr3_translation"].copy()
    for c in ["avg_net_usd", "total_net_usd", "baseline_avg_net_usd"]:
        trans[c] = trans[c].map(lambda x: f"{x:,.0f}")
    for c in ["hit_rate", "baseline_hit_rate"]:
        trans[c] = trans[c].map(lambda x: f"{x:.0%}")

    body = []
    for title, f in figs:
        body.append(f"<section><h2>{html.escape(title)}</h2>{_div(f)}</section>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VIX Term Structure Carry</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root{{--ink:{INK};--ink2:{INK2};--muted:{MUTED};--grid:{GRID};--bg:#ffffff;--plane:#f9f9f7}}
body{{margin:0;background:var(--plane);color:var(--ink);font:15px/1.55 "Segoe UI",system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:28px 16px 60px}}
h1{{font-size:28px;margin:0 0 4px}} h2{{font-size:18px;margin:0 0 6px}} .sub{{color:var(--ink2);margin:0 0 18px}}
section{{background:var(--bg);border:1px solid rgba(11,11,11,.08);border-radius:10px;padding:16px;margin:16px 0}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:18px 0}}
.kpi{{background:var(--bg);border:1px solid rgba(11,11,11,.08);border-radius:10px;padding:12px 14px}}
.kpi b{{display:block;font-size:24px}} .kpi span{{color:var(--ink2);font-size:13px}}
.tbl{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}
.tbl th,.tbl td{{padding:5px 8px;border-bottom:1px solid var(--grid);text-align:right}}
.tbl th:first-child,.tbl td:first-child,.tbl td:nth-child(2),.tbl th:nth-child(2){{text-align:left}}
.scroll{{overflow-x:auto}} .note{{color:var(--muted);font-size:12px}}
</style></head><body><main>
<h1>VIX futures term structure: carry, tail risk and the link to SOFR</h1>
<p class="sub">How much does the VX curve pay for being short volatility, how do you survive the blow-ups, and does VIX stress
lead the SOFR curve? Sample {k['sample_start']} to {k['sample_end']}; parameters chosen on 2016-2021, judged on 2022 onward.</p>
<div class="kpis">
<div class="kpi"><b>{k['contango_share']:.0%}</b><span>of days the VX curve is in contango (VX2 &gt; VX1)</span></div>
<div class="kpi"><b>{k['avg_roll_yield_contango']:.3f}</b><span>vol pts/day average roll-down of VX1 toward spot in contango (${k['avg_roll_yield_contango'] * 1000:,.0f} per contract per day)</span></div>
<div class="kpi"><b>{a['sharpe']:.2f}</b><span>net Sharpe, always short the front, full sample, max drawdown {usd(a['max_dd_usd'])} per contract</span></div>
<div class="kpi"><b>{k['+ spike exit + stop | out-of-sample']['sharpe']:.2f}</b><span>out-of-sample Sharpe of the in-sample-optimised defended strategy (2022 onward)</span></div>
</div>
{''.join(body)}
<section><h2>Strategy summary (net of costs, 1 contract)</h2><div class="scroll">{_table(tbl)}</div></section>
<section><h2>Crisis windows</h2><div class="scroll">{_table(tails)}</div>
<p class="note">recovery_bdays = business days from the trough to regain the pre-drawdown high; inf = not regained by the end of the data.</p></section>
<section><h2>Trading the inversion signal in SR3 (buy the 4th quarterly contract, hold 20 days)</h2><div class="scroll">{_table(trans)}</div></section>
<p class="note">{SOURCE}. Signals use data up to the close of day t; trades happen at the close of t+1. Costs: 1 tick + $2.50 per contract per side.</p>
</main></body></html>"""
    p = cfg["paths"]["report"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(page, encoding="utf-8")
    return p
