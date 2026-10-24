# Interview notes: VIX term structure carry

A study guide for this project, in plain words. If you can explain everything in this file, you can defend the repo
in any interview.

---

## 1. The whole project in 10 sentences

1. VIX futures (VX) are bets on where the VIX index will be on each monthly expiry date.
2. Most of the time the curve slopes upward ("contango"): later months are priced higher than spot VIX, because
   people pay a premium for crash insurance.
3. If nothing happens, a VX future drifts down toward spot VIX as it approaches expiry. A short position collects
   that drift. This is the "carry" or "roll-down".
4. I measured it: the curve was in contango on 84% of days, and the front future drifted about 0.07 vol points
   ($69 per contract) a day toward spot.
5. I backtested selling the front future in several ways: always, only in contango, with exits after a VIX spike,
   with stops, as a calendar spread, and with volatility-targeted size.
6. Every backtest uses only data available at the time, trades one day after the signal, never computes a return
   across a contract roll, and pays costs on every trade.
7. Always-short earned the most (Sharpe 0.48) but lost $68k per contract from peak in March 2020. Carry is payment
   for taking crash risk.
8. A simple rule ("short only in contango, go flat when the curve inverts or VIX jumps 20%") kept most of the return
   and cut the crisis losses a lot. A version with parameters tuned on 2016–2021 failed in 2022–2026, which is a
   lesson about over-fitting.
9. On the rates side, VIX stress weeks come with a SOFR futures rally of 5 to 11 bp. But by the time the VIX curve
   actually inverts, the rally has mostly happened, so "buy SOFR when VIX inverts" did not make money out of sample.
10. The practical outputs are a tail-risk table for sizing a short-vol book, a robust rule a risk manager can accept,
    and a daily screen that says where today's VX curve sits versus history.

---

## 2. Each method, explained simply

### 2.1 VX1, VX2 and the roll

**What:** on each day, VX1 is the nearest future that has not expired yet, and VX2 is the next one.
**Why it matters:** VX1 changes identity every month. If you glued VX1 prices into one series and took differences,
the day VX1 switches from the April contract (say 15) to the May contract (say 17) would look like a +2 jump that
nobody earned or lost.
**How I avoid it:** the P&L on any day is always today's settle minus yesterday's settle of **the same contract**.
Rolling means closing one contract and opening another, which costs money but never creates a fake jump.
**Tiny example:** short 1 April at 15.00. On the roll day April settles at 14.90 (+$100 for the short). I buy April
back and sell May at 16.80. The next day May settles at 16.70 (+$100). The 15 → 16.8 "gap" never enters P&L.
`test_rolls.py` proves it with contracts placed 10 points apart.

### 2.2 Roll rule ("held front")

I hold the nearest contract with **more than 5 business days to expiry**. In the last week a VX contract is pinned to
the special opening settlement (SOQ) of VIX options, which is noisy and not carry. The rule is fixed in advance, so
it cannot "know" the future.

### 2.3 Basis, slope, contango, roll yield

- **Basis = VX1 − spot VIX.** If it is +1.0 with 20 days left and spot stays put, the future falls 1.0 by expiry.
- **Roll yield = basis ÷ days to expiry** = 0.05 a day in that example, which is $50 per contract per day.
- **Slope = VX2 − VX1. Contango ratio = VX2/VX1 − 1.** For example 18.0 / 17.0 − 1 = 5.9%.
- Inverted (backwardation) means VX1 > VX2: the market expects VIX to fall from a high level. This happens in panics.

### 2.4 Constant-maturity 30-day VX

Interpolate in days to expiry between the two contracts around 30 days.
Example: VX1 = 20 with 10 days left, VX2 = 22 with 40 days. Thirty days is 2/3 of the way from 10 to 40, so
CM30 = 1/3 × 20 + 2/3 × 22 = 21.33. This gives a smooth series with no monthly jumps. I use it for description and
for the daily screen.

### 2.5 Variance risk premium (VRP)

VRP = VIX today − the volatility the S&P 500 actually realised over the next 21 trading days. It was positive on 88%
of days, averaging 4.5 vol pts. This is the economic reason the carry exists: insurance sellers are paid on average.
It is measured with future data, so it is only ever used to describe, **never as a trading signal**.

### 2.6 The backtest engine and timing

Each day, in this order:
1. mark yesterday's holdings to today's settle;
2. execute yesterday's decision at today's settle and pay costs;
3. decide tomorrow's target using data up to today only.

So a signal from Monday's close trades at Tuesday's settle and starts earning on Wednesday.
`test_no_lookahead.py` deletes all data after a date and checks that every position before that date is unchanged.

### 2.7 Exits

- **Contango filter:** be short only if VX2/VX1 − 1 > threshold.
- **Spike exit:** go flat for 5 days if the curve inverts or spot VIX rises more than 20% in one day.
- **Stop:** flat if the trade has lost X vol points per contract.
- In the data the stop rarely fired. Big losses arrive as one-day gaps, and the spike rule usually fires first.

### 2.8 Calendar spread

Short the held front, long the next contract. The idea is that in a spike both legs rise, so the long leg hedges the
short. The beta-weighted version buys β of the next contract per front contract, where β comes from a 60-day
regression of front changes on next-contract changes (the front moves more, so β > 1).

### 2.9 Volatility targeting

Contracts = $1,000 ÷ (20-day standard deviation of one contract's daily $ P&L), capped at 10 and fixed for the life
of a trade. Example: one contract has moved $500 a day lately, so trade 2 contracts.
The flaw: volatility is lowest just before a crash, so this rule is at its **biggest** size going into a shock. That
is exactly why it did worse here.

### 2.10 In-sample / out-of-sample

I tried 5 contango thresholds × 4 stops and picked the best Sharpe on **2016–2021 only**. Then I looked at
**2022–Oct 2026**, which I never used for choosing. The whole grid is shown in a heatmap, so nobody has to trust one
lucky cell.

### 2.11 Event study

An "inversion event" is the first day VX1 > VX2 after at least 20 days of contango (so one long crisis counts once).
For each event I line up the rates series from 10 days before to 30 days after. I set the inversion day to 0, average
across events, and add a 95% band (mean ± 1.96 × standard error).
Example: if SR3 pos4's rate was 3.70% ten days before and 3.66% on the event day, that event contributes +4 bp at
offset −10. "+4 at −10" means rates fell 4 bp into the event.

### 2.12 Lead-lag and Granger

- **Cross-correlation at lag L:** today's change in VX slope versus the SR3 change L days later. A big value at
  positive L would mean VIX leads.
- **Granger test:** do past VX slope changes improve a forecast of SR3 changes beyond SR3's own past? A small p-value
  means "yes, statistically". It does **not** mean "causes" in the everyday sense, and it says nothing about size.

### 2.13 SR3 positions and chaining

Position k = the k-th quarterly SOFR future whose last trading day is after today. A daily change is measured on the
contract that held the position **yesterday**, then the changes are summed. This is the same roll logic as VX.
SR3 rate = 100 − price, in bp.

---

## 3. Design choices, and the alternatives

| Choice | Why | Alternative considered |
|---|---|---|
| Trade fixed contracts, roll 5 business days before expiry | Real tradable P&L; avoids the expiry-week settlement noise | Trade CM30 (not tradable without constant rebalancing) or hold to expiry (SOQ risk) |
| Signal at close t, trade at close t+1 | Removes any chance of trading on the price that made the signal | Trade at the close t settle: unrealistic, because the settle is only known after the close |
| Costs on every entry, exit and roll | Carry is small per day, so costs decide whether it survives | Ignore costs: the calendar spreads would look profitable gross (+$13.8k) |
| One split, 2016–21 / 2022–26 | Simple and honest; the out-of-sample period holds a hiking cycle, Aug-2024, Apr-2025 and the 2026 shock | Rolling walk-forward: better but heavier. Listed under next steps |
| Show a parameter-free rule next to the optimised one | Shows how much optimisation helped (it didn't) | Report only the optimised rule: would hide the over-fitting |
| Spike exit uses an inversion or a 20% VIX jump | Both are observable at the close and economically meaningful | A VIX level (e.g. > 30): fires too late and depends on the regime |
| Event study on SR3 + ZQ, not Treasuries | The STIR curve is what I trade; the 2y yield is missing in this data set | 2y Treasury yield (would extend the sample to 2016 for SR3-like moves) |
| Daily data | All I have for 10 years | Intraday: would model gaps and fills properly |

---

## 4. Every number in the README, and where it comes from

All of these are in `reports/results/key_numbers.json`, unless a different CSV is named.

| Number | Meaning | Source |
|---|---|---|
| 84% | days with VX2 > VX1, 2016-01-04 to 2026-10-19 | `contango_share` |
| 0.069 vol pts/day, $69 | average roll yield (basis ÷ days) on contango days | `avg_roll_yield_contango` |
| 88%, 4.5 vol pts | share of days VIX > next-21-day realised vol; average gap (from Nov-2020) | `vrp_positive_share`, `avg_vrp` |
| $107k, Sharpe 0.48 / 0.42 / 0.58 | always-short: full net P&L; full / in-sample / out-of-sample Sharpe | `strategy_summary.csv` |
| −$68k | always-short max drawdown (Mar-2020) | `strategy_summary.csv` (−67,935) and `tail_windows.csv` (−67,680 inside the window) |
| −$17.6k | worst day, 5-Feb-2018 | `strategy_summary.csv`, hand-checked in `tests/SPOT_CHECKS.md` |
| 273 business days | recovery from the Mar-2020 trough | `tail_windows.csv` |
| Sharpe 0.40, 0.32 OOS, −$26.1k | parameter-free rule (contango > 0 + exits + 2-pt stop) | `strategy_summary.csv` |
| $11k | worst in-window drawdown of that rule (Aug-2024) | `tail_windows.csv` |
| 7.5%, 2 pts; 0.58 → −0.27 | in-sample-chosen parameters; their in-sample vs out-of-sample Sharpe | `threshold_grid.csv` |
| +$13.8k gross, $38k costs, −$24k net | calendar 1:1, full sample | `strategy_summary.csv` (gross_usd, costs_usd, net_usd) |
| 5–11 bp, t ≈ −2.0 to −2.6 | extra SR3 pos2–pos8 rally in weeks VIX rose > 5 pts | `stress_weeks_sr3.csv` |
| 20 / 26 events | VX inversions with SR3 data / all | `inversion_events.csv`, `event_study_summary.csv` |
| −3.7 bp, +5.2 bp | SR3 pos4 change in the 10 days before / after an inversion | `event_study_summary.csv` (offset −10 = +3.725 means a fall into the event) |
| −$387 vs −$298 | buy-SR3-after-inversion trade out of sample vs the same trade every day | `sr3_inversion_trade.csv` |
| 0.15; p = 0.013 | same-day correlation; minimum Granger p, VX → SR3 | `leadlag_crosscorr.csv`, `granger.csv` |

---

## 5. What didn't work, and why

- **Tuning the contango threshold.** 7.5% was best in 2016–21 and among the worst afterwards. In 2022–26 the curve
  was in shallower contango (average ratio about 5% versus about 9% in 2016–17 and 2021), so a high threshold
  sat out much of the carry and traded only short, late bursts. Lesson: with about 50 trades, the differences between
  nearby parameters are noise.
- **Calendar spreads.** The hedge works (tiny crisis losses), but VX2 also rolls down. What is left is less than the
  cost of trading two legs.
- **Volatility targeting.** It sizes up when recent volatility is low, which is right before shocks. It made the
  results worse.
- **Stop-losses.** These rarely fired. Losses come as overnight gaps, which a daily stop cannot catch.
- **Using a VIX inversion as a signal to buy SOFR.** The rates move happens at the same time as, or before, the
  inversion. Afterwards rates on average rose (the panic rally partly reversed).
- **2y Treasury in the event study** was dropped, because the yield series is not populated in this data set.

---

## 6. Fifteen likely interview questions, with model answers

**1. Why does VIX futures carry exist at all?**
Investors pay up for protection against equity crashes, so implied volatility usually sits above the volatility that
then happens (here VIX beat next-month realised vol on 88% of days). The futures curve reflects that premium.
Futures above spot then drift down toward spot as expiry nears. A short collects the insurance premium and in return
takes the crash risk.

**2. How did you avoid look-ahead bias?**
Three ways. Signals use only data up to the close of day t. Trades execute at the settle of t+1, so the earliest P&L
is t+1 → t+2. The roll schedule and every parameter are fixed in advance or chosen on 2016–21 only. A unit test
deletes all data after a date and checks that nothing before that date changes.

**3. How do you handle rolls?**
I never difference a "generic" series. P&L is always the change in one named contract. When I roll, I close the old
contract and open the new one, and pay costs on both. The same rule applies to the SR3 and ZQ series: changes are
measured on yesterday's contract, then chained.

**4. Why roll 5 business days before expiry?**
In the final days a VX contract converges to the special opening quotation of SPX options on expiry morning. That
adds noise and settlement risk that has nothing to do with carry. Most practitioners and ETPs roll before that.

**5. Your best in-sample strategy lost money out of sample. Isn't that a failed project?**
No, it's the most useful result. It shows that the carry is real but the "smart" filter is not. With about 50 trades
in-sample, the difference between a 5% and a 7.5% threshold is noise. The parameter-free rule kept a positive Sharpe
out of sample. Showing that honestly is exactly what a desk wants from research.

**6. What would break the always-short strategy?**
A shock bigger or longer than March 2020. A regime where VIX trends up for months (2008-style). A sudden gap such as
Feb-2018, when VX1 rose 17.6 points in one day: one day wiped out more than a year of carry. Also liquidity: in a
crisis, bid-ask spreads widen exactly when you need to cut.

**7. How would you size it?**
From the tail, not the average. One contract lost up to $68k in a real crisis. If the desk can lose $200k on this
book in a 1-in-10-year event, that is about 3 contracts, before thinking about carry. I would add the exit rules,
then size so the stressed loss (with the overnight gap the exits can't avoid, e.g. $10–11k a contract) fits the
limit.

**8. Why does the spike exit help so much?**
Big VIX events usually build up over a few days. The curve flattens, then inverts. Going flat at the first
inversion or 20% VIX jump means you are out before the worst of the slow-motion crises (Mar-2020, Apr-2025). It
can't save you from a one-night gap (Aug-2024), and it costs some carry when it fires on false alarms.

**9. Why did the calendar spread lose money?**
The long VX2 leg also rolls down in contango, so it gives back most of the short leg's carry. What is left
(+$13.8k gross over ten years) is less than the cost of trading two legs on every entry, exit and roll ($38k). It is
a good hedge but a bad carry trade at these costs.

**10. What does the variance risk premium tell you, and why not trade on it?**
It confirms that insurance is usually overpriced. But it is measured with future realised volatility, so on the day
you trade you don't know it. I use it only to explain why the carry exists, never as a signal.

**11. Is VIX a leading indicator for SOFR?**
Not in a tradable way. The same-day correlation of daily changes is 0.15. The best lagged correlation is 0.07. A
Granger test says VX slope changes help forecast SR3 statistically (p ≈ 0.01), but the effect is tiny. In stress
weeks SOFR does rally 5–11 bp more than usual. By the time the curve inverts, though, most of that move has already
happened.

**12. Why is the front SR3 contract unaffected by VIX stress while pos4–pos8 rally?**
The front contract's rate is mostly fixed by the current policy rate and the fixings already in its reference
quarter. Risk-off changes expectations of **future** Fed cuts, which sit in contracts 6–24 months out. That is why
the effect grows along the curve.

**13. How many events do you have, and is that enough?**
There are 26 VX inversions, 20 with SR3 data. That is enough to see the average shape, but the 95% bands are wide
(±10–20 bp at 30 days). I state that, and I tested the trading rule out of sample instead of trusting the average.

**14. Why use Sharpe on daily P&L in dollars, with no capital?**
Futures need margin, not capital, so return on capital depends on an arbitrary margin assumption. Sharpe on daily
dollar P&L is scale-free (doubling the size doesn't change it), and that makes strategies comparable. For risk I
quote dollars per contract: drawdown, worst day, worst week.

**15. What would you do next?**
Use intraday data to model gaps and real exit prices. Run a rolling walk-forward instead of one split. Price an
explicit hedge (VIX calls or SPX puts) and compare its cost with the drawdown it removes. Condition the VIX → SOFR
study on the Fed regime, because inversions during hiking cycles behave differently from those near cuts.

---

## 7. Walk me through the code

| File | What it does |
|---|---|
| `config.yaml` | Every parameter: sample dates, in/out-of-sample split, VX and SR3 contract specs and costs, strategy grids, crisis windows, event-study settings, chart annotations. |
| `src/vixcarry/config.py` | `load_config()` reads the YAML and turns relative paths into absolute ones, so scripts work from any folder. |
| `src/vixcarry/load.py` | Reads the CSVs. `load_vx` attaches expiries; `load_sr3` keeps quarterly contracts and adds `rate_bp`; `load_zq` adds the delivery month; `wide()` makes a dates × contracts table (never a generic column). |
| `src/vixcarry/termstructure.py` | `front_table` gives VX1..VX4 with names, expiries and days to expiry; `constant_maturity` gives CM30/60/90; `realised_vol` gives trailing and forward S&P vol; `build_term_structure` adds basis, slope, contango, roll yield, VRP; `curve_on_grid` interpolates each day's curve onto fixed days-to-expiry for the heatmap and bands. |
| `src/vixcarry/strategies.py` | `held_contracts` applies the roll rule; `chained_changes` gives roll-safe daily changes; `CarryStrategy.decide()` holds all the rules (filter, spike exit with cooldown, stop, sizing, calendar legs) and sees only data up to today; `default_specs` lists the variants. |
| `src/vixcarry/backtest.py` | `run_backtest` is the day loop (mark → execute → decide) with costs; `trade_table` groups continuous exposure into trades; `metrics` gives Sharpe, drawdown, hit rate and so on for any period; `tail_stats` measures the drawdown inside a window and the recovery time. |
| `src/vixcarry/seasonality.py` | Percentile bands by business days to expiry, the current cycle, and the percentile of today's value. |
| `src/vixcarry/crossasset.py` | SR3 positions and chained changes, ZQ 12-month measure, roll-safe VX slope change, `inversion_events`, `event_paths` and `summarise_paths` (mean ± 95%), cross-correlation, Granger, the stress-week t-tests, and the SR3 translation trade vs its every-day baseline. |
| `src/vixcarry/pipeline.py` | `run()` does everything in order, chooses parameters in-sample (`choose_parameters`), builds the summary and tail tables, computes `key_numbers` (the README numbers) and saves the CSVs. |
| `src/vixcarry/plots.py` | One matplotlib style. Ten charts whose titles are computed from the results. `save_all()` writes the PNGs. |
| `src/vixcarry/report.py` | The same charts in Plotly, plus the tables, as one HTML page for GitHub Pages. |
| `scripts/run_all.py` | One command: results, charts, report. |
| `scripts/screen_today.py` | The daily desk screen. |
| `scripts/build_notebook.py` | Builds and executes the walkthrough notebook, so its outputs always match the code. |
| `tests/` | `test_rolls.py` (no cross-roll returns, roll timing, roll costs), `test_no_lookahead.py` (truncation invariance, t+1 execution), `test_maths.py` (costs, interpolation, drawdown, events, SR3 trade P&L), `test_spot_checks.py` + `SPOT_CHECKS.md` (three real dates by hand). |
