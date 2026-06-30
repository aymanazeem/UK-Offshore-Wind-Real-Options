"""
One command to regenerate every chart in outputs/charts/.

This is a thin orchestrator. It calls each module's own simulate -> report -> plot pipeline,
the same code paths the module mains use, so running it also re-runs the validation asserts
baked into the option engine. Nothing is recomputed here that a module doesn't already own.

    python -m src.visualisation            # base case (N_PATHS)
    python -m src.visualisation --n=10000  # quick, fewer paths
    python -m src.visualisation --final     # production quality (N_PATHS_FINAL)

Charts are chart1 price fan, chart_generation, chart2 NPV, chart3 sensitivity, and the three
option charts chart4 defer, chart5 expand and chart6 abandon.
"""

from __future__ import annotations

import sys
import time

from config import parameters as P
from src import price_simulator, generation_model, financial_model, sensitivity, lsm_engine

# (label, output filename, callable taking n_paths), in narrative order.
CHARTS = [
    ("Price fan",        "chart1_price_fan.png",   lambda n: price_simulator.main([f"--n={n}"])),
    ("Generation",       "chart_generation.png",   lambda n: generation_model.main([f"--n={n}"])),
    ("NPV distribution", "chart2_npv.png",         lambda n: financial_model.main([f"--n={n}"])),
    ("Sensitivity",      "chart3_sensitivity.png", lambda n: sensitivity.main([f"--n={n}"])),
    ("Defer option",     "chart4_defer.png",       lambda n: lsm_engine.main_defer(n)),
    ("Expand option",    "chart5_expand.png",      lambda n: lsm_engine.main_expand(n)),
    ("Abandon option",   "chart6_abandon.png",     lambda n: lsm_engine.main_abandon(n)),
]


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = P.N_PATHS
    for arg in argv:
        if arg == "--final":
            n_paths = P.N_PATHS_FINAL
        elif arg.startswith("--n="):
            n_paths = int(arg.split("=", 1)[1])

    P.CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Regenerating {len(CHARTS)} charts at {n_paths:,} paths -> {P.CHARTS_DIR}\n")
    t0 = time.time()
    for i, (label, fname, run) in enumerate(CHARTS, 1):
        print(f"{'=' * 70}\n[{i}/{len(CHARTS)}] {label}  ->  {fname}\n{'=' * 70}")
        run(n_paths)
        print()
    print(f"All {len(CHARTS)} charts regenerated in {time.time() - t0:.0f}s.")


if __name__ == "__main__":
    main()
