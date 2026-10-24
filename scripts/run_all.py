"""One command reproduces every result, chart and the interactive report:

    python scripts/run_all.py

Reads data/raw/*.csv (see data/README.md), writes reports/results/*.csv, reports/figures/*.png, reports/report.html.
"""
from __future__ import annotations

import pathlib
import sys
import time
import warnings

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from vixcarry import pipeline, plots, report  # noqa: E402
from vixcarry.config import load_config  # noqa: E402


def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    t0 = time.time()
    cfg = load_config()
    print("1/3 building term structure, backtests, tail and cross-asset studies ...")
    o = pipeline.run(cfg, save=True)
    print(f"    in-sample parameters: contango threshold {o['threshold']:.1%}, stop {o['stop']:g} vol pts; "
          f"{len(o['events'])} VIX inversion events")
    print("2/3 static charts ...")
    for p in plots.save_all(o, cfg):
        print("    ", p.relative_to(cfg["paths"]["figures"].parents[1]))
    print("3/3 interactive report ...")
    print("    ", report.build(o, cfg).relative_to(cfg["paths"]["figures"].parents[1]))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
