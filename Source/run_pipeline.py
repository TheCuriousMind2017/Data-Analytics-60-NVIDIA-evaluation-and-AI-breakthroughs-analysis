#!/usr/bin/env python3
"""
NVIDIA data pipeline orchestrator
=================================

Runs the four ingestion scripts in dependency order, each as its own process
(so every step keeps its independent logging to Logs/ via logging_config and an
isolated failure mode). Stops immediately if any step fails.

    1. sec_edgar_ingest.py     SEC EDGAR fundamentals          [network]
    2. yahoo_prices_ingest.py  Yahoo Finance prices/indices    [network]
    3. segments_ingest.py      NVIDIA revenue by segment       [local CSV]
    4. join_quarterly.py       merge -> master quarterly panel [needs 1 + 2]

`join` depends on the SEC and Yahoo outputs; `segments` is independent. Scripts
run with the repo root as the working directory, so their Data/ and Logs/ paths
resolve regardless of where you launch this from.

The SEC step needs a contact (SEC fair-access policy). Set it once:
    PowerShell:  $env:SEC_IDENTITY = "Your Name you@email.com"
    bash/zsh:    export SEC_IDENTITY="Your Name you@email.com"

Usage (from the repo root):
    python Source/run_pipeline.py                  # full pipeline
    python Source/run_pipeline.py --skip sec,yahoo # offline re-run (segments + join)
    python Source/run_pipeline.py --only segments  # a single step
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent      # Source/
ROOT = HERE.parent                          # repo root -> Data/, Logs/ resolve here

STEPS = [
    ("sec",      "sec_edgar_ingest.py"),
    ("yahoo",    "yahoo_prices_ingest.py"),
    ("segments", "segments_ingest.py"),
    ("join",     "join_quarterly.py"),
]


def main():
    ap = argparse.ArgumentParser(description="Run the NVIDIA data pipeline end to end")
    ap.add_argument("--only", help="comma-separated subset, e.g. segments,join")
    ap.add_argument("--skip", help="comma-separated steps to skip, e.g. sec,yahoo")
    args = ap.parse_args()

    names = [n for n, _ in STEPS]
    only = {s.strip() for s in args.only.split(",")} if args.only else None
    skip = {s.strip() for s in args.skip.split(",")} if args.skip else set()
    for given in (only or set()) | skip:
        if given not in names:
            sys.exit(f"unknown step '{given}'. valid steps: {', '.join(names)}")

    selected = [(n, s) for (n, s) in STEPS
                if (only is None or n in only) and n not in skip]
    if not selected:
        sys.exit("no steps selected")

    print(f"pipeline: {' -> '.join(n for n, _ in selected)}\n")
    for name, script in selected:
        print(f"{'=' * 64}\n[run_pipeline] {name}: {script}\n{'=' * 64}")
        result = subprocess.run([sys.executable, str(HERE / script)], cwd=ROOT)
        if result.returncode != 0:
            sys.exit(f"\n[run_pipeline] step '{name}' failed "
                     f"(exit {result.returncode}); stopping.")
    print("\n[run_pipeline] all steps completed.")


if __name__ == "__main__":
    main()
