#!/usr/bin/env python3
"""
NVIDIA revenue-by-segment ingestion (third pipeline)
====================================================

Independent of the SEC/Yahoo pipelines: this one reads a single hand-collected
CSV (transcribed from NVIDIA 10-K "Revenue by Reportable Segment" disclosures)
and turns it into a clean, analysis-ready annual table for Pillar 3 (revenue
mix). No network access -- the source is manual because NVIDIA does not expose
segment splits through the XBRL facts API in a usable, consistent form.

Runs standalone: it produces an ANNUAL table and does NOT feed join_quarterly.py
(segments are annual; the master panel is quarterly).

Input  (Data/inputs/nvda_revenue_by_segment.csv):
    period, gaming, data_center, pro_viz, oem_other, total,
    data_center_pct, gaming_pct          # $M; *_pct are NVIDIA's reported %s

What this script does
---------------------
1. Fiscal -> calendar mapping. NVIDIA's fiscal year ends late January, so a
   fiscal year is ~11/12 the *prior* calendar year:  FY(n) ~= calendar (n-1).
   FY2023 (ended Jan 2023) -> calendar 2022, the ChatGPT year. This is what
   lets the segment crossover line up with the gen-AI milestone.

2. Unallocated band. The four listed segments do not sum to total -- early
   years omit Automotive / OEM&IP / Tegra residue (~15-37% unallocated), and
   a couple of recent years slightly *over*-sum total by rounding. We derive
       other_unallocated = max(total - sum(4 segments), 0)
   and use denom = max(total, sum4) so every year's shares sum to exactly 1.0
   and the stacked area never overflows 100%.

3. Recomputed shares. Shares are recomputed from the raw $ (seg / denom) rather
   than trusting the transcribed *_pct columns; the reported %s are kept only as
   a cross-check and the script warns on any large divergence (transcription QA).

4. Data-quality flags surfaced at run time: signed reconciliation residual,
   overage flag, and a consecutive-duplicate check (catches e.g. the FY2016 and
   FY2017 data_center cells both reading 830, a suspected transcription error).

Output (Data/outputs/nvda_segments_annual.csv): one row per fiscal year, with
fiscal_year, calendar_year, the five revenue bands ($M), their shares (sum=1),
the reported-vs-computed data-center % cross-check, and the QA columns.

Paths resolve to <repo>/Data automatically (via __file__), so no flags are
needed. A real run logs to Logs/ + console through logging_config, matching the
other pipeline scripts; --selftest stays a plain offline logic check.

Run (from repo root):  python Source/segments_ingest.py
Verify logic offline:  python Source/segments_ingest.py --selftest
Optional window:       python Source/segments_ingest.py --min-fy 2017
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

SEGMENTS = ["gaming", "data_center", "pro_viz", "oem_other"]


def fy_to_calendar(fiscal_year: int) -> int:
    """NVIDIA FY ends ~end of January -> fiscal year n maps to calendar n-1."""
    return fiscal_year - 1


def _parse_fy(period: str) -> int:
    s = str(period).strip().upper().replace("FY", "")
    return int(s)


def build_segments(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [c.strip().lstrip("\ufeff").lower() for c in df.columns]

    missing = [c for c in (["period", "total"] + SEGMENTS) if c not in df.columns]
    if missing:
        raise ValueError(f"input missing required columns: {missing}")

    df["fiscal_year"] = df["period"].map(_parse_fy)
    df["calendar_year"] = df["fiscal_year"].map(fy_to_calendar)

    for c in SEGMENTS + ["total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    sum4 = df[SEGMENTS].sum(axis=1)
    df["other_unallocated"] = (df["total"] - sum4).clip(lower=0)
    # denom guarantees shares in [0,1] and summing to 1 even when segments
    # over-sum the reported total (recent rounding artifacts).
    denom = pd.concat([df["total"], sum4], axis=1).max(axis=1)

    bands = SEGMENTS + ["other_unallocated"]
    for c in bands:
        df[f"{c}_share"] = df[c] / denom

    # reconciliation diagnostics (signed: + = genuine unallocated, - = overage)
    df["recon_residual"] = df["total"] - sum4
    df["recon_residual_pct"] = df["recon_residual"] / df["total"]
    df["overage_flag"] = sum4 > df["total"]

    # cross-check transcribed vs recomputed data-center %
    if "data_center_pct" in df.columns:
        df["data_center_pct_reported"] = pd.to_numeric(
            df["data_center_pct"], errors="coerce")
        df["data_center_pct_check_diff"] = (
            df["data_center_share"] * 100 - df["data_center_pct_reported"])

    df = df.sort_values("fiscal_year").reset_index(drop=True)

    front = ["fiscal_year", "calendar_year", "total"] + bands + \
            [f"{c}_share" for c in bands] + \
            ["recon_residual", "recon_residual_pct", "overage_flag"]
    if "data_center_pct_reported" in df.columns:
        front += ["data_center_pct_reported", "data_center_pct_check_diff"]
    front = [c for c in front if c in df.columns]
    return df[front]


def _quality_report(df: pd.DataFrame) -> None:
    logging.info("reconciliation residual by fiscal year:")
    for _, r in df.iterrows():
        tag = " OVERAGE" if r["overage_flag"] else ""
        logging.info("  FY%d (cal %d): %+6.1f%% unallocated%s",
                     int(r["fiscal_year"]), int(r["calendar_year"]),
                     r["recon_residual_pct"] * 100, tag)

    # consecutive-duplicate check (e.g. FY2016/FY2017 data_center both 830)
    for c in SEGMENTS:
        d = df[c]
        dup = (d == d.shift(1)) & d.notna() & (d != 0)
        for i in df.index[dup]:
            logging.warning("%s: FY%d and FY%d both = %d -- verify against 10-K "
                            "(possible transcription error)",
                            c, int(df.loc[i - 1, "fiscal_year"]),
                            int(df.loc[i, "fiscal_year"]), int(d.loc[i]))

    if "data_center_pct_check_diff" in df.columns:
        big = df["data_center_pct_check_diff"].abs() > 1.5
        for i in df.index[big]:
            logging.warning("FY%d data_center %%: reported %.1f vs computed %.1f",
                            int(df.loc[i, "fiscal_year"]),
                            df.loc[i, "data_center_pct_reported"],
                            df.loc[i, "data_center_share"] * 100)

    # crossover: first fiscal year data_center share overtakes gaming
    cross = df[df["data_center_share"] > df["gaming_share"]]
    if not cross.empty:
        r = cross.iloc[0]
        logging.info("Data Center first overtakes Gaming in FY%d (calendar %d): "
                     "DC %.1f%% vs Gaming %.1f%%",
                     int(r["fiscal_year"]), int(r["calendar_year"]),
                     r["data_center_share"] * 100, r["gaming_share"] * 100)


def run(indir: Path, outdir: Path, min_fy: int | None):
    src = indir / "nvda_revenue_by_segment.csv"
    if not src.exists():
        logging.error("missing input: %s", src)
        sys.exit(1)
    # tolerate Excel re-saves: sniff the delimiter (comma / semicolon / tab) and
    # strip a UTF-8 BOM, so a locale-dependent Excel save doesn't break the read.
    df = build_segments(pd.read_csv(src, sep=None, engine="python",
                                    encoding="utf-8-sig"))

    if min_fy:
        df = df[df["fiscal_year"] >= min_fy].reset_index(drop=True)

    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "nvda_segments_annual.csv"
    df.to_csv(out, index=False)
    logging.info("wrote %d fiscal years (FY%d-FY%d) -> %s",
                 len(df), int(df["fiscal_year"].min()),
                 int(df["fiscal_year"].max()), out)
    _quality_report(df)


# --------------------------------------------------------------------------- #
# Offline self-test (plain stdout: no logging side effects, no Logs/ file)
# --------------------------------------------------------------------------- #
def selftest() -> int:
    ok = True
    # FY2015 normal (sum4 < total -> unallocated); FY2024 overage (sum4 > total)
    raw = pd.DataFrame({
        "period": ["FY2015", "FY2023", "FY2024"],
        "gaming": [2055, 9066, 10447],
        "data_center": [557, 15005, 47532],
        "pro_viz": [564, 1544, 1591],
        "oem_other": [782, 1353, 1866],
        "total": [4682, 26974, 60922],
        "data_center_pct": [11.9, 55.6, 78.0],
        "gaming_pct": [43.9, 33.6, 17.1],
    })
    df = build_segments(raw).set_index("fiscal_year")

    bands = SEGMENTS + ["other_unallocated"]
    checks = {
        "FY2015 -> calendar 2014": df.loc[2015, "calendar_year"] == 2014,
        "FY2024 -> calendar 2023": df.loc[2024, "calendar_year"] == 2023,
        "FY2015 unallocated = 724": df.loc[2015, "other_unallocated"] == 724,
        "FY2024 overage clamps unallocated to 0":
            df.loc[2024, "other_unallocated"] == 0,
        "FY2024 flagged as overage": bool(df.loc[2024, "overage_flag"]),
        "FY2015 not overage": not bool(df.loc[2015, "overage_flag"]),
        "FY2015 shares sum to 1":
            abs(sum(df.loc[2015, f"{c}_share"] for c in bands) - 1.0) < 1e-9,
        "FY2024 shares sum to 1 (clamped denom)":
            abs(sum(df.loc[2024, f"{c}_share"] for c in bands) - 1.0) < 1e-9,
        "FY2023 DC share > Gaming share":
            df.loc[2023, "data_center_share"] > df.loc[2023, "gaming_share"],
        "FY2015 DC share < Gaming share":
            df.loc[2015, "data_center_share"] < df.loc[2015, "gaming_share"],
        "recon residual signed (+ FY2015, - FY2024)":
            df.loc[2015, "recon_residual"] > 0 and df.loc[2024, "recon_residual"] < 0,
        "computed DC% ~ reported (FY2023)":
            abs(df.loc[2023, "data_center_share"] * 100 - 55.6) < 1.0,
    }
    print("checks:")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        ok = ok and bool(v)
    print("\nSELF-TEST:", "ALL PASSED \u2705" if ok else "FAILURES \u274c")
    return 0 if ok else 1


def main():
    # repo root = parent of Source/; data lives in <root>/Data regardless of CWD
    DATA = Path(__file__).resolve().parents[1] / "Data"
    ap = argparse.ArgumentParser(
        description="Ingest NVIDIA revenue-by-segment into a clean annual table")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--indir", default=DATA / "inputs", type=Path)
    ap.add_argument("--outdir", default=DATA / "outputs", type=Path)
    ap.add_argument("--min-fy", type=int, default=None,
                    help="optional: drop fiscal years before this (e.g. 2017)")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    # configure file + console logging only for a real run -- keeps --selftest
    # clean and leaves build_segments importable without logging side effects
    import logging_config  # noqa: F401  (configures root logger on import)
    run(args.indir, args.outdir, args.min_fy)


if __name__ == "__main__":
    main()
