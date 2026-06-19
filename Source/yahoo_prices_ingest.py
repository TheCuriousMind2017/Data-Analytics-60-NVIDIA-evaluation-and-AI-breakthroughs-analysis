#!/usr/bin/env python3
"""
Yahoo Finance price / index ingestion pipeline
==============================================

Sibling module to sec_edgar_ingest.py. Single responsibility: pull split- and
dividend-adjusted daily closes for the study's price layer, then derive a
quarter-end panel keyed on the same `YYYYQn` calendar-quarter label the EDGAR
module uses, so the two join cleanly later.

Assets:
  companies : NVDA, AMD, INTC            (price layer for the chipmakers)
  indices   : NDX (^NDX), SOX (^SOX)     (Nasdaq-100 + semis benchmarks)
              SOX falls back to SOXX then SMH if ^SOX comes back empty/short.

Window: 2010-01-01 .. 2026-03-31 (pinned end for reproducibility).

Outputs:
  outputs/yahoo_prices_daily.csv      date, ticker, source_ticker, adj_close
  outputs/yahoo_prices_quarterly.csv  ticker, calendar_quarter, quarter_end_date,
                                      source_ticker, qend_adj_close, qoq_return

Run real ingestion:   python yahoo_prices_ingest.py
Verify logic offline: python yahoo_prices_ingest.py --selftest

NOTE: the live pull needs network access to Yahoo Finance (via the `yfinance`
library) and must be run in your own environment.
"""

from __future__ import annotations
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from logging_config import logging
logging.info("Script started")


# adjusted close is split/dividend adjusted -> correct for returns and trajectory
START = date(2010, 1, 1)
END = date(2026, 3, 31)          # pinned cutoff

# label -> (primary yahoo ticker, [fallbacks])
COMPANIES = {"NVDA": ("NVDA", []), "AMD": ("AMD", []), "INTC": ("INTC", [])}
INDICES = {"NDX": ("^NDX", []), "SOX": ("^SOX", ["SOXX", "SMH"])}
MIN_OBS = 100                    # a real series for this window has thousands of rows


# --------------------------------------------------------------------------- #
# Helpers (mirror the EDGAR module's calendar-quarter convention)
# --------------------------------------------------------------------------- #
def cal_q(ts) -> tuple:
    return (ts.year, (ts.month - 1) // 3 + 1)


def q_label(yq) -> str:
    return f"{yq[0]}Q{yq[1]}"


def in_window(yq) -> bool:
    lo = (START.year, (START.month - 1) // 3 + 1)
    hi = (END.year, (END.month - 1) // 3 + 1)
    return lo <= yq <= hi


def to_quarterly(daily: pd.DataFrame, label: str, source: str) -> pd.DataFrame:
    """Daily adj_close -> quarter-end panel: last trading day per calendar quarter,
    plus quarter-over-quarter return. `daily` is indexed by date with 'adj_close'."""
    d = daily.dropna(subset=["adj_close"]).sort_index()
    if d.empty:
        return pd.DataFrame()
    d = d.assign(_yq=[cal_q(ts) for ts in d.index])
    rows = []
    for yq, g in d.groupby("_yq", sort=True):
        rows.append({
            "ticker": label, "calendar_quarter": q_label(yq), "_yq": yq,
            "quarter_end_date": g.index[-1].date(), "source_ticker": source,
            "qend_adj_close": round(float(g["adj_close"].iloc[-1]), 6),
        })
    q = pd.DataFrame(rows).sort_values("_yq").reset_index(drop=True)
    q["qoq_return"] = q["qend_adj_close"].pct_change()
    q = q[q["_yq"].map(in_window)].drop(columns="_yq").reset_index(drop=True)
    return q


def pick_series(candidates: list) -> tuple:
    """candidates: ordered [(ticker, series_or_None), ...]. Return the first with
    enough observations, else (first_ticker, None)."""
    for tk, s in candidates:
        if s is not None and len(s) >= MIN_OBS:
            return tk, s
    return candidates[0][0], None


# --------------------------------------------------------------------------- #
# Live loading (yfinance)
# --------------------------------------------------------------------------- #
def load_series(ticker: str):
    """Fetch adjusted daily closes for one ticker. Returns a DataFrame indexed by
    naive date with a single 'adj_close' column, or None."""
    import yfinance as yf
    h = yf.Ticker(ticker).history(
        start=START.isoformat(), end=(END + timedelta(days=1)).isoformat(),
        auto_adjust=True, interval="1d")
    if h is None or h.empty or "Close" not in h.columns:
        return None
    s = h[["Close"]].rename(columns={"Close": "adj_close"})
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s.sort_index()


def load_with_fallback(primary: str, fallbacks: list):
    cands = [(tk, load_series(tk)) for tk in [primary] + fallbacks]
    return pick_series(cands)


def run(outdir: Path):
    try:
        import yfinance  # noqa: F401
    except ImportError:
        sys.exit("`yfinance` is required for the live pull: pip install yfinance")

    daily_frames, q_frames = [], []

    def ingest(label, primary, fallbacks):
        used, s = load_with_fallback(primary, fallbacks)
        if s is None:
            print(f"[warn] {label}: no data from {[primary] + fallbacks}")
            return
        if used != primary:
            print(f"[fallback] {label}: {primary} unavailable -> using {used}")
        df = s.assign(ticker=label, source_ticker=used).reset_index(
            names="date")[["date", "ticker", "source_ticker", "adj_close"]]
        daily_frames.append(df)
        q_frames.append(to_quarterly(s, label, used))
        print(f"[ok] {label}: {len(s)} daily rows ({used})")

    for label, (primary, fb) in {**COMPANIES, **INDICES}.items():
        ingest(label, primary, fb)

    outdir.mkdir(parents=True, exist_ok=True)
    daily = pd.concat(daily_frames, ignore_index=True)
    quarterly = pd.concat(q_frames, ignore_index=True)
    daily.to_csv(outdir / "yahoo_prices_daily.csv", index=False)
    quarterly.to_csv(outdir / "yahoo_prices_quarterly.csv", index=False)

    print(f"\n[done] {len(daily)} daily rows, {len(quarterly)} quarter-end rows -> {outdir}")
    summary = (quarterly.groupby("ticker")
               .agg(n_quarters=("calendar_quarter", "size"),
                    first_q=("calendar_quarter", "first"),
                    last_q=("calendar_quarter", "last"),
                    source=("source_ticker", "last")))
    print(summary.to_string())


# --------------------------------------------------------------------------- #
# Offline self-test (no network)
# --------------------------------------------------------------------------- #
def selftest() -> int:
    ok = True

    # 1) quarter-end resampling + labelling + return, on a known daily ramp
    idx = pd.bdate_range("2019-11-01", "2020-06-30")
    px = pd.Series(range(100, 100 + len(idx)), index=idx, dtype=float)
    daily = pd.DataFrame({"adj_close": px})
    q = to_quarterly(daily, "TEST", "TEST").set_index("calendar_quarter")

    last_2019q4 = px[(idx.year == 2019) & (idx.month >= 10)].index.max()
    last_2020q1 = px[(idx.year == 2020) & (idx.month <= 3)].index.max()
    last_2020q2 = px[(idx.year == 2020) & (idx.month.isin([4, 5, 6]))].index.max()
    exp_close = {"2019Q4": px[last_2019q4], "2020Q1": px[last_2020q1],
                 "2020Q2": px[last_2020q2]}
    exp_ret_q1 = exp_close["2020Q1"] / exp_close["2019Q4"] - 1

    checks = {
        "three calendar quarters produced": list(q.index) == ["2019Q4", "2020Q1", "2020Q2"],
        "2020Q1 end = last trading day of Mar": q.loc["2020Q1", "quarter_end_date"] == last_2020q1.date(),
        "2019Q4 close = last close of Dec": q.loc["2019Q4", "qend_adj_close"] == exp_close["2019Q4"],
        "2020Q1 close = last close of Mar": q.loc["2020Q1", "qend_adj_close"] == exp_close["2020Q1"],
        "first quarter return is NaN": pd.isna(q.loc["2019Q4", "qoq_return"]),
        "2020Q1 qoq return correct": abs(q.loc["2020Q1", "qoq_return"] - exp_ret_q1) < 1e-9,
    }

    # 2) window filtering drops out-of-range quarters
    idx2 = pd.bdate_range("2009-10-01", "2010-03-31")
    d2 = pd.DataFrame({"adj_close": pd.Series(range(len(idx2)), index=idx2, dtype=float)})
    q2 = to_quarterly(d2, "T2", "T2")
    checks["pre-2010 quarter excluded by window"] = "2009Q4" not in set(q2["calendar_quarter"])
    checks["2010Q1 kept"] = "2010Q1" in set(q2["calendar_quarter"])

    # 3) SOX fallback chooser
    short = pd.Series(range(50))
    good = pd.Series(range(300))
    pick_sox = pick_series([("^SOX", None), ("SOXX", short), ("SMH", good)])[0]
    pick_keep = pick_series([("^SOX", good), ("SOXX", short)])[0]
    checks["fallback picks SMH when SOX empty / SOXX short"] = pick_sox == "SMH"
    checks["fallback keeps ^SOX when it has data"] = pick_keep == "^SOX"

    print("checks:")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        ok = ok and bool(v)
    print("\nSELF-TEST:", "ALL PASSED \u2705" if ok else "FAILURES \u274c")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Yahoo Finance price/index ingestion")
    ap.add_argument("--selftest", action="store_true", help="run offline logic tests")
    ap.add_argument("--outdir", default="Data/outputs", type=Path)
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    run(args.outdir)


if __name__ == "__main__":
    main()
