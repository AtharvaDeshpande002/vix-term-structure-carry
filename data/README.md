# Input data

The raw data is the owner's Bloomberg settlement data, licensed for personal use, so **it is not in this repository**
(`data/raw/` is in `.gitignore`). To run the project, put CSV files with exactly these names and columns in `data/raw/`.
Any source works (exchange settlement files, another vendor) as long as the format matches.

Dates are `YYYY-MM-DD`. Holidays are simply absent (no forward-filled rows). One row per contract per session.

## Files used by this project

| File | Columns | Units | Frequency | Range used |
|---|---|---|---|---|
| `vx_settles.csv` | `date, contract, settle, volume, open_interest` | settle in VIX points; volume/OI in contracts (optional, may be blank) | daily | 2015-04 onward (front month from Dec-2015) |
| `vx_contracts.csv` | `contract, month, expiry` | `month` = `YYYY-MM` delivery month; `expiry` = final settlement date (the Wednesday 30 days before the next month's SPX options expiry) | one row per contract | VXF16 onward |
| `daily_series.csv` | `date, vix, vix9d, vix3m, vvix, spx, sofr, fed_target_upper, ust2y, ust10y` | index levels; rates in % | daily | VIX family from 2016-01; S&P 500 from 2020-11 |
| `sr3_settles.csv` | `date, contract, settle, volume, open_interest` | SR3 price (rate = 100 - price) | daily | 2018-05 onward |
| `sr3_contracts.csv` | `contract, ref_month, first_trade, last_trade, quarterly` | `quarterly` = True for H/M/U/Z contracts; serial months are ignored | one row per contract | |
| `zq_settles.csv` | `date, contract, settle, volume, open_interest` | ZQ price (rate = 100 - price) | daily | 2008 onward |
| `zq_contracts.csv` | `contract, month, first_trade, last_trade` | `month` = `YYYY-MM` | one row per contract | |
| `fomc_decisions.csv` | `decision_date, target_upper, survey_median, scheduled` | % | per meeting | present for completeness; not needed by this project |
| `econ_releases.csv` | `release, period, release_date, actual, survey_median, ...` | | per release | present for completeness; not needed by this project |

Contract naming: root + month code + 2-digit year, e.g. `VXH24` (VIX futures, March 2024), `SR3Z26`, `ZQF27`.
Month codes: F G H J K M N Q U V X Z = Jan ... Dec.

## Known gaps in the data set used for the published results

- **Spot VIX starts 2016-01-04**, and the VX file has no contract expiring before Jan-2016, so a true front-month
  series exists only from Dec-2015. The backtests therefore start on 2016-01-04, and the Aug-2015 shock is shown
  only through a proxy (a short in the nearest listed contract, VXF16).
- **S&P 500 closes start 2020-11-11**, so realised volatility and the variance-risk premium are measured from then.
- **`ust2y` / `ust10y` are almost empty** in this extract (a few days in 2026), so Treasury yields are not used; the
  cross-asset study uses SR3 (from 2018-05) and fed funds futures (ZQ) instead.
- VX volume is mostly blank; it is not used.

## Derived data

`scripts/run_all.py` writes only small derived tables to `reports/results/` (strategy statistics, crisis-window
table, seasonality percentiles, event-study averages, test statistics) — never price history.
