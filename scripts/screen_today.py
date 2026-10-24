"""The "use it on the desk tomorrow" screen: where today's VX curve sits versus its own history.

    python scripts/screen_today.py

Prints and saves (reports/screen_today.csv / .html):
  * basis, slope, contango ratio, roll yield today and their percentile in 2016-today history;
  * where today's VX1-VX2 sits versus the same point of past expiry cycles (seasonality);
  * whether the carry signal (parameters chosen in-sample) is ON or OFF for tomorrow's close;
  * if the VIX curve is inverted today: the historical average SR3 / ZQ path after past inversions.
"""
from __future__ import annotations

import html
import pathlib
import sys
import warnings

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from vixcarry import pipeline  # noqa: E402
from vixcarry.config import load_config  # noqa: E402
from vixcarry.seasonality import percentile_of_today  # noqa: E402


def main() -> None:
    warnings.filterwarnings("ignore")
    cfg = load_config()
    o = pipeline.run(cfg, save=False)
    ts = o["ts"]
    t = ts.dropna(subset=["VX1", "VX2"]).index[-1]
    r = ts.loc[t]
    rows = []
    for col, label, unit in [("basis", "Basis VX1 - VIX", "vol pts"), ("slope", "Slope VX2 - VX1", "vol pts"),
                             ("contango", "Contango ratio VX2/VX1 - 1", "%"), ("roll_yield", "Roll yield (basis / days)", "vol pts/day"),
                             ("vix", "Spot VIX", "vol pts"), ("CM30", "Constant-maturity 30d VX", "vol pts")]:
        v = r[col]
        rows.append({"measure": label, "today": round(float(v) * (100 if unit == "%" else 1), 3), "unit": unit,
                     "percentile_vs_history": round(percentile_of_today(ts[col], v), 1)})
    # seasonality: same business-day-to-expiry point in past cycles
    fs = (ts.VX1 - ts.VX2)
    same = fs[ts.bdte1 == r.bdte1]
    rows.append({"measure": f"VX1 - VX2 at {int(r.bdte1)} business days to expiry", "today": round(float(r.VX1 - r.VX2), 3),
                 "unit": "vol pts", "percentile_vs_history": round(percentile_of_today(same, r.VX1 - r.VX2), 1)})
    th, st = o["threshold"], o["stop"]
    on = bool(r.contango > th and r.slope > 0)
    rows.append({"measure": f"Carry signal (contango > {th:.1%}, not inverted)", "today": "ON" if on else "OFF",
                 "unit": "", "percentile_vs_history": np.nan})
    rows.append({"measure": "Carry signal, simplest robust version (contango > 0%)", "today": "ON" if r.slope > 0 else "OFF",
                 "unit": "", "percentile_vs_history": np.nan})
    table = pd.DataFrame(rows)
    extra = ""
    if r.slope < 0:
        es = o["event_summary"]
        lines = []
        for ser in es.series.unique():
            for off in (10, cfg["events"]["post"]):
                x = es[(es.series == ser) & (es.offset == off)].iloc[0]
                lines.append(f"{ser}, +{off}d: {x['mean']:+.1f} bp (95% band {x.lo:+.1f} to {x.hi:+.1f}, n={int(x.n)})")
        extra = "VIX curve INVERTED today. After past inversions:\n  " + "\n  ".join(lines)
    else:
        extra = "VIX curve not inverted today: no inversion-conditional rates expectation."

    print(f"VX screen for {t:%d-%b-%Y} (front contract {r.c1}, {int(r.bdte1)} business days to expiry)\n")
    print(table.to_string(index=False))
    print("\n" + extra)
    out = cfg["paths"]["results"].parent
    table.to_csv(out / "screen_today.csv", index=False)
    (out / "screen_today.html").write_text(
        f"<!doctype html><meta charset='utf-8'><title>VX screen {t:%d-%b-%Y}</title>"
        f"<body style='font:14px Segoe UI,system-ui,sans-serif;margin:24px'><h2>VX screen {t:%d-%b-%Y}</h2>"
        f"{table.to_html(index=False, border=0, na_rep='')}<pre>{html.escape(extra)}</pre>"
        f"<p style='color:#898781;font-size:12px'>Source: Bloomberg settlement data; author's calculations.</p></body>",
        encoding="utf-8")


if __name__ == "__main__":
    main()
