"""Build notebooks/walkthrough.ipynb from the cells below and execute it, so the saved outputs always match the code.

    python scripts/build_notebook.py
"""
from __future__ import annotations

import pathlib

import nbformat as nbf
from nbclient import NotebookClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# VIX futures term structure: carry, tail risk, and the link to SOFR

**Two trading questions**

1. How much does the VIX futures (VX) curve pay you for being short volatility, and how do you survive the blow-ups?
2. When the VX curve inverts (risk-off), what happens to the SOFR curve and to Fed pricing, and does VIX lead?

This notebook tells the story step by step. All the code lives in `src/vixcarry/`; the notebook only calls it and
explains the results. The same numbers are produced by `python scripts/run_all.py`.

Conventions: VX in vol points (1 contract = $1,000 per point; tick 0.05 = $50). SOFR futures (SR3) as rates,
`rate = 100 - price`, in basis points. Signals use data up to the close of day *t*; trades happen at the close of
*t+1*. Every P&L is net of 1 tick + $2.50 per contract per side."""),
    code("""import sys, warnings
sys.path.insert(0, "../src")
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.precision", 3); pd.set_option("display.width", 160)
%matplotlib inline
from vixcarry.config import load_config
from vixcarry import pipeline, plots
plots.style()
cfg = load_config()
o = pipeline.run(cfg, save=False)
k = o["key"]
print(f"Sample {k['sample_start']} to {k['sample_end']}: {len(o['ts'])} trading days")"""),
    md("""## Step 1 - The term-structure dataset

For each day we take the live VX contracts (expiry after today), call them VX1, VX2, ..., and compute:

* **basis** = VX1 - spot VIX. Positive basis means the future is above spot; if nothing changes, the future drifts
  down to spot by expiry. That drift is what a short collects.
* **slope** = VX2 - VX1, and the **contango ratio** = VX2/VX1 - 1. Positive = normal upward-sloping curve.
* **roll yield** = basis / days to expiry: the drift per day, in vol points.
* **constant-maturity 30-day VX**: interpolate between the two contracts around 30 days, so the series does not
  jump at every expiry.

The heatmap shows every day's curve; red marks weeks when it was inverted."""),
    code("""plots.heatmap(o, cfg);"""),
    code("""print(f"Contango on {k['contango_share']:.0%} of days; average roll-down in contango "
      f"{k['avg_roll_yield_contango']:.3f} vol pts/day = ${k['avg_roll_yield_contango']*1000:,.0f} per contract per day")
o["contango_by_year"]"""),
    code("""plots.contango_by_year(o, cfg);"""),
    md("""**Why is there carry at all?** VIX itself is a price of insurance (implied volatility). Most of the time
implied volatility is above the volatility that actually happens next, the *variance risk premium*. The chart
compares VIX with the S&P 500's realised volatility over the following 21 days (S&P data here starts Nov-2020)."""),
    code("""plots.vrp_chart(o, cfg);"""),
    code("""plots.curve_today(o, cfg);"""),
    md("""## Step 2 - Carry strategies (backtests, net of costs)

Which contract: the nearest VX contract with **more than 5 business days to expiry** (fixed rule, known in advance).
We roll into the next one 5 days before expiry. P&L is always the change of the same contract's settle, so a roll
never creates a fake jump.

Variants, from naive to most defended:

| Variant | Rule |
|---|---|
| Short front, always | always short 1 lot |
| contango filter | short only when VX2/VX1 - 1 > threshold |
| + spike exit | also go flat (for 5 days) if the curve inverts or spot VIX jumps > 20% in a day |
| + spike exit + stop | also stop a trade after it loses X vol points |
| Contango > 0 + spike exit + stop | the same with the parameter-free threshold 0 (reference, not optimised) |
| Calendar 1:1 | short VX1-held / long the next contract, same filter and exits |
| Calendar beta-weighted | long beta x the next contract, beta from a 60-day regression |
| vol-targeted | size so the expected daily P&L s.d. is ~$1,000, max 10 lots |

**Parameter choice is in-sample only (2016-2021).** We try every threshold x stop and keep the best in-sample
Sharpe. 2022 onward is never looked at when choosing."""),
    code("""print(f"In-sample choice: contango threshold {o['threshold']:.1%}, stop {o['stop']:g} vol pts")
o["threshold_grid"].pivot(index="stop_volpts", columns="threshold", values="oos_sharpe").round(2)"""),
    code("""plots.robustness(o, cfg);"""),
    md("""The heatmap is the most important honesty check in the project: the threshold that looked best in-sample
(7.5%) was among the worst afterwards, while the obvious, parameter-free rule (contango > 0) kept working. A
filter tuned on six years of history mostly learned the noise of those years."""),
    code("""s = o["summary"]
cols = ["strategy", "period", "trades", "hit_rate", "net_usd", "sharpe", "max_dd_usd", "worst_day_usd", "costs_usd"]
s[s.period != "full"][cols]"""),
    code("""plots.equity_curves(o, cfg);"""),
    md("""### Tail analysis (mandatory)

Carry is paid for tail risk. The table shows what each strategy did inside each crisis window: P&L, worst day,
worst week, the drawdown that happened inside the window, and how many business days it took to regain the
previous high (`inf` = not yet regained)."""),
    code("""t = o["tails"].dropna(subset=["pnl_usd"])
t[t.strategy.isin(list(plots.STRAT_COLOURS))].round(0)"""),
    code("""print("Aug-2015 proxy (no front-month VX in the data before Dec-2015):", o["aug2015_proxy"])
plots.tail_chart(o, cfg);"""),
    md("""**Reading it.** Always-short is the best earner over the whole sample, but one contract lost about $68k from
peak in March 2020 and took more than a year to recover. The exits avoid the slow-motion disasters because the
curve usually flattens or inverts *before* the worst days, but they cannot avoid an overnight gap such as
5-Aug-2024, when VX jumped 10 points between two closes while the strategy was still short."""),
    md("""## Step 3 - Expiry seasonality

Line up every monthly cycle by business days to VX1 expiry and look at VX1 - VX2. The band is the 10-90th
percentile across cycles; orange is the current cycle."""),
    code("""plots.seasonality(o, cfg);"""),
    code("""o["season_spread"][["p10", "p25", "p50", "p75", "p90", "n"]].round(2)"""),
    md("""## Step 4 - Cross-asset: VIX -> rates

**Inversion events** = first day VX1 > VX2 after at least 20 days of contango. Around each event we measure, on
fixed contracts chained across rolls:

* the SR3 1-year spread (position 1 minus position 5, in rate terms),
* the SR3 4th quarterly contract's rate,
* the fed funds futures (ZQ) rate 12 months ahead minus the current month (negative = cuts priced).

The 2-year Treasury yield was planned too, but it is not populated in this data set (see `data/README.md`)."""),
    code("""print(len(o["events"]), "inversion events:", ", ".join(str(d.date()) for d in o["events"]))
plots.event_study(o, cfg);"""),
    code("""es = o["event_summary"]
es[es.offset.isin([-10, -5, 5, 10, 20, 30])].pivot(index="offset", columns="series", values="mean").round(1)"""),
    md("""Lead-lag: correlation of today's change in the VX slope with the SR3 2nd contract's rate change *lag* days
later, plus Granger tests in both directions."""),
    code("""plots.leadlag(o, cfg);
o["granger"].round(4)"""),
    md("""Conditional weeks: average weekly SR3 change by position in weeks when spot VIX rose more than 5 points,
versus all other weeks (2018 onward)."""),
    code("""o["stress_weeks"].round(2)"""),
    md("""**Trading translation.** Buy (receive) the 4th SR3 contract at the close after each inversion and hold 20
business days, net of costs, versus doing the same trade on every day (the baseline)."""),
    code("""o["sr3_translation"].round(2)"""),
    md("""## Conclusions

1. **The carry is real.** The VX curve is in contango on most days and VX1 drifts toward spot by about 0.07 vol
   points a day when it is; implied volatility exceeded the next month's realised volatility on most days.
2. **It is paid for crash risk.** A permanently short front contract has the best long-run P&L but drew down about
   $68k per contract in March 2020. Any desk running it needs a hard rule for the left tail.
3. **Simple defences work, tuned ones don't.** "Short only in contango, flat after an inversion or a 20% VIX jump"
   cut the worst crisis drawdown sharply and kept a positive out-of-sample Sharpe. The in-sample-optimised
   threshold failed out of sample: a lesson about over-fitting.
4. **Calendar spreads (short VX1 / long VX2) lose**: VX2 rolls down too, so the long leg gives the carry back.
5. **VIX and SOFR move on the same day, not in sequence.** Stress weeks come with a significant SR3 rally, but by
   the time the VX curve inverts most of it has happened; buying SR3 after an inversion did not beat the baseline
   out of sample."""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
path = ROOT / "notebooks" / "walkthrough.ipynb"
path.parent.mkdir(exist_ok=True)
NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}).execute()
nbf.write(nb, path)
print("wrote", path.relative_to(ROOT))
