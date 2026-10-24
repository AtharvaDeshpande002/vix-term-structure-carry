# Resume bullets

All numbers come from `reports/results/` and are reproduced by `python scripts/run_all.py`.

- Built a roll-safe backtest of VIX futures carry strategies over 2016–2026, with costs and a separate out-of-sample
  period. Always short the front contract earned Sharpe 0.48 net (0.58 out of sample) but drew down $68k per contract
  in Mar-2020. A simple contango-and-inversion exit rule kept Sharpe 0.40 and cut the worst crisis drawdown to $11k.
- Showed that a contango threshold optimised in-sample (Sharpe 0.58, 2016–21) failed out of sample (Sharpe −0.27,
  2022–26), while the parameter-free rule held up (0.32). Documented the over-fitting with a full parameter
  robustness grid.
- Linked volatility and rates: in weeks when VIX rose more than 5 points, SOFR futures 3–24 months out rallied
  5–11 bp more than usual (t ≈ −2.5). An event study of 20 VIX-curve inversions showed the rally happens before the
  inversion, so buying SOFR on the signal had no out-of-sample edge.
