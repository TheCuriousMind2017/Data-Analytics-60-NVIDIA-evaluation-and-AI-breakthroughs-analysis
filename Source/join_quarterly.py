#!/usr/bin/env python3
"""
Quarterly join / aggregation
============================

Third module in the pipeline. Reads the two ingestion outputs and merges them
into one analysis-ready quarterly panel keyed on (ticker, calendar_quarter):

  sec_fundamentals_wide.csv   (EDGAR)  fundamentals + margins
  sec_fundamentals_long.csv   (EDGAR)  used only for the filed-date provenance
  yahoo_prices_quarterly.csv  (Yahoo)  quarter-end price + QoQ return

Alignment: PERIOD-MATCHED (price quarter-end <-> same calendar quarter's
fundamentals). The EDGAR filing date is carried as `fundamentals_filed` so a
stricter as-known/lagged panel can be built downstream without re-ingesting.

Derived here (all split-invariant -> safe across NVDA's 2021 4:1 and 2024 10:1
splits): TTM revenue & net income, YoY revenue growth, and a base-100 cumulative
price index. Valuation multiples (P/E, P/S) and the earnings-vs-multiple
decomposition are deliberately NOT computed yet -- they need market cap from
*unadjusted* price x shares outstanding, which is the next ingestion add.

Outputs:
  outputs/master_quarterly_panel.csv

Run:                  python join_quarterly.py
Verify logic offline: python join_quarterly.py --selftest
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

import pandas as pd
from logging_config import logging

logging.info("Script started")


KEYS = ["ticker", "calendar_quarter"]


def cq_key(s: str) -> tuple:
    y, q = s.split("Q")
    return (int(y), int(q))


def build_panel(wide: pd.DataFrame, long_df: pd.DataFrame,
                yq: pd.DataFrame) -> pd.DataFrame:
    # filing-date provenance: latest filed date backing each ticker-quarter
    if not long_df.empty and "filed" in long_df.columns:
        filed = (long_df.groupby(KEYS)["filed"].max()
                 .reset_index().rename(columns={"filed": "fundamentals_filed"}))
    else:
        filed = pd.DataFrame(columns=KEYS + ["fundamentals_filed"])

    panel = pd.merge(wide, yq, on=KEYS, how="outer")
    panel = panel.merge(filed, on=KEYS, how="left")
    panel["_yq"] = panel["calendar_quarter"].map(cq_key)
    panel = panel.sort_values(["ticker", "_yq"]).reset_index(drop=True)

    gb = panel.groupby("ticker", sort=False)
    if "revenue" in panel:
        panel["revenue_ttm"] = gb["revenue"].transform(
            lambda s: s.rolling(4, min_periods=4).sum())
        panel["revenue_yoy"] = panel["revenue"] / gb["revenue"].shift(4) - 1
    if "net_income" in panel:
        panel["netincome_ttm"] = gb["net_income"].transform(
            lambda s: s.rolling(4, min_periods=4).sum())
    if "qoq_return" in panel:
        cum = gb["qoq_return"].transform(lambda s: (1 + s.fillna(0)).cumprod() * 100)
        if "qend_adj_close" in panel:
            cum = cum.where(panel["qend_adj_close"].notna())
        panel["price_index_100"] = cum

    front = [c for c in ["ticker", "calendar_quarter", "quarter_end_date",
                         "fundamentals_filed", "source_ticker",
                         "qend_adj_close", "qoq_return", "price_index_100",
                         "revenue", "revenue_ttm", "revenue_yoy",
                         "net_income", "netincome_ttm",
                         "gross_profit", "operating_income",
                         "gross_margin", "operating_margin", "net_margin",
                         "eps_diluted", "diluted_shares", "capex"]
             if c in panel.columns]
    rest = [c for c in panel.columns if c not in front and c != "_yq"]
    return panel[front + rest].reset_index(drop=True)


def run(indir: Path, outdir: Path):
    def need(name):
        p = indir / name
        if not p.exists():
            sys.exit(f"missing input: {p}")
        return pd.read_csv(p)

    wide = need("sec_fundamentals_wide.csv")
    long_df = need("sec_fundamentals_long.csv")
    yq = need("yahoo_prices_quarterly.csv")

    panel = build_panel(wide, long_df, yq)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "master_quarterly_panel.csv"
    panel.to_csv(out, index=False)

    print(f"[done] {len(panel)} rows -> {out}")
    cov = (panel.assign(has_price=panel["qend_adj_close"].notna(),
                        has_fund=panel.get("revenue", pd.Series(dtype=float)).notna()
                        if "revenue" in panel else False,
                        has_capex=panel.get("capex", pd.Series(dtype=float)).notna()
                        if "capex" in panel else False)
           .groupby("ticker")
           .agg(rows=("calendar_quarter", "size"),
                first_q=("calendar_quarter", "first"),
                last_q=("calendar_quarter", "last"),
                price_qtrs=("has_price", "sum"),
                fund_qtrs=("has_fund", "sum"),
                capex_qtrs=("has_capex", "sum")))
    print(cov.to_string())


# --------------------------------------------------------------------------- #
# Offline self-test
# --------------------------------------------------------------------------- #
def selftest() -> int:
    ok = True
    qs = ["2020Q1", "2020Q2", "2020Q3", "2020Q4", "2021Q1"]
    wide = pd.DataFrame({
        "ticker": ["NVDA"] * 5, "calendar_quarter": qs,
        "revenue": [100, 110, 120, 130, 140],
        "net_income": [10, 11, 12, 13, 14],
    })
    long_df = pd.DataFrame({
        "ticker": ["NVDA"] * 5, "calendar_quarter": qs,
        "filed": ["2020-05-01", "2020-08-01", "2020-11-01", "2021-02-01", "2021-05-01"],
    })
    yq = pd.DataFrame({
        "ticker": ["NVDA"] * 5 + ["SOX"] * 5,
        "calendar_quarter": qs + qs,
        "quarter_end_date": ["x"] * 10,
        "qend_adj_close": [50, 55, 60, 66, 72, 1000, 1100, 1100, 1210, 1331],
        "qoq_return": [None, .10, .0909090909, .10, .0909090909,
                       None, .10, 0.0, .10, .10],
    })

    panel = build_panel(wide, long_df, yq).set_index(KEYS)

    nv = panel.xs("NVDA")
    checks = {
        "NVDA has 5 merged rows": len(nv) == 5,
        "price + fundamentals aligned on key": nv.loc["2020Q1", "revenue"] == 100
                                               and nv.loc["2020Q1", "qend_adj_close"] == 50,
        "revenue_ttm 2021Q1 = 500": nv.loc["2021Q1", "revenue_ttm"] == 500,
        "revenue_ttm 2020Q4 = 460": nv.loc["2020Q4", "revenue_ttm"] == 460,
        "revenue_ttm 2020Q3 NaN (only 3 qtrs)": pd.isna(nv.loc["2020Q3", "revenue_ttm"]),
        "netincome_ttm 2021Q1 = 50": nv.loc["2021Q1", "netincome_ttm"] == 50,
        "revenue_yoy 2021Q1 = 0.40": abs(nv.loc["2021Q1", "revenue_yoy"] - 0.40) < 1e-9,
        "price_index base 100": abs(nv.loc["2020Q1", "price_index_100"] - 100) < 1e-9,
        "price_index 2020Q4 ~132": abs(nv.loc["2020Q4", "price_index_100"] - 132) < 1e-6,
        "fundamentals_filed carried": nv.loc["2021Q1", "fundamentals_filed"] == "2021-05-01",
    }
    sox = panel.xs("SOX")
    checks["index ticker has price, no fundamentals"] = (
        pd.isna(sox.loc["2020Q1", "revenue"]) and sox.loc["2020Q1", "qend_adj_close"] == 1000)
    checks["index ticker still gets price_index"] = abs(
        sox.loc["2020Q1", "price_index_100"] - 100) < 1e-9

    print("checks:")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        ok = ok and bool(v)
    print("\nSELF-TEST:", "ALL PASSED \u2705" if ok else "FAILURES \u274c")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Join EDGAR + Yahoo into a quarterly panel")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--indir", default="Data/outputs", type=Path)
    ap.add_argument("--outdir", default="Data/outputs", type=Path)
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    run(args.indir, args.outdir)


if __name__ == "__main__":
    main()
