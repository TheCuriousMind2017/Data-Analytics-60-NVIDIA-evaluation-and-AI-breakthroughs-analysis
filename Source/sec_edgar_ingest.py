#!/usr/bin/env python3
"""
SEC EDGAR fundamentals ingestion pipeline
==========================================

Pulls quarterly fundamentals for an NVIDIA-vs-peers / hyperscaler-capex study
straight from SEC EDGAR's XBRL `companyfacts` API, applying the locked design:

  1. BULK FETCH + CACHE   one `companyfacts` request per CIK (every concept &
                          period in a single JSON), cached to disk so re-runs
                          never re-fetch. Polite throttle + retry/backoff.
  2. TAG COALESCING       ordered fallback lists per metric (handles the
                          Revenues -> RevenueFromContractWith... ASC 606 switch).
  3. PERIOD KEYING        key on (start, end); classify durations as quarterly
                          (~3 months) vs annual (~12 months); YTD spans dropped.
  4. DEDUP                per (concept, start, end): keep EARLIEST-filed value,
                          a same-period amendment (/A) overrides.
  5. Q4 DERIVATION        for additive flows: Q4 = annual - (Q1 + Q2 + Q3).
  6. CALENDAR ALIGNMENT   each fiscal quarter mapped to the calendar quarter
                          containing its period MIDPOINT (robust to NVDA/INTC
                          off-cycle fiscal years).
  7. COMPLETENESS REPORT  per ticker/metric: count, span, interior gaps.

Outputs (analysis-ready):
  outputs/sec_fundamentals_long.csv   one row per ticker/quarter/metric + provenance
  outputs/sec_fundamentals_wide.csv   one row per ticker/quarter, metrics + margins
  outputs/sec_completeness_report.csv per ticker/metric coverage + interior gaps

Run real ingestion:   python sec_edgar_ingest.py
Verify logic offline: python sec_edgar_ingest.py --selftest

NOTE: the live pull requires network access to https://data.sec.gov, which must
be run in your own environment.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from logging_config import logging
logging.info("Script started")

try:
    import requests
except ImportError:  # only needed for the live pull, not for --selftest
    requests = None

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
# SEC User-Agent is read from the SEC_IDENTITY env var or the --identity flag.
# Nothing is hard-coded, so the repo is safe to publish.
START = date(2010, 1, 1)
END = date(2025, 12, 31)
REQUESTS_PER_SEC = 5  # comfortably under SEC's ~10/s ceiling
CF_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# ticker -> CIK list (Alphabet needs the legacy Google Inc. CIK for pre-2015)
COMPANIES = {
    "NVDA":  {"ciks": [1045810],          "needs": "income"},
    "AMD":   {"ciks": [2488],             "needs": "income"},
    "INTC":  {"ciks": [50863],            "needs": "income"},
    "MSFT":  {"ciks": [789019],           "needs": "capex"},
    "GOOGL": {"ciks": [1652044, 1288776], "needs": "capex"},  # Alphabet + legacy Google
    "AMZN":  {"ciks": [1018724],          "needs": "capex"},
    "META":  {"ciks": [1326801],          "needs": "capex"},  # IPO 2012 -> short series
}

# Ordered fallback tag lists. First tag that reports a given period wins.
CONCEPTS = {
    "revenue":          ["RevenueFromContractWithCustomerExcludingAssessedTax",
                         "RevenueFromContractWithCustomerIncludingAssessedTax",
                         "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"],
    "gross_profit":     ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income":       ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted":      ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    "diluted_shares":   ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "capex":            ["PaymentsToAcquirePropertyPlantAndEquipment",
                         "PaymentsToAcquireProductiveAssets"],
}

# Additive income-statement flows -> Q4 derived by subtraction.
ADDITIVE = {"revenue", "gross_profit", "operating_income", "net_income"}
# Cash-flow items are reported year-to-date (cumulative) -> reconstruct by differencing.
CASHFLOW = {"capex"}
# Per-share / share counts are not additive: keep reported Q1-Q3, do not synthesise Q4.
REPORTED_ONLY = {"eps_diluted", "diluted_shares"}

NEEDS = {
    "income": ["revenue", "gross_profit", "operating_income",
               "net_income", "eps_diluted", "diluted_shares"],
    "capex":  ["capex"],
}

# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def period_kind(start: date, end: date) -> str:
    """Classify an XBRL duration by length. Tolerant of 52/53-week calendars."""
    days = (end - start).days
    if 80 <= days <= 100:
        return "Q"
    if 350 <= days <= 380:
        return "A"
    return "OTHER"  # 6-month / 9-month YTD spans, etc. -> ignored


def cal_quarter(start: date, end: date):
    """Map a fiscal period to the calendar quarter containing its midpoint."""
    mid = start + (end - start) / 2
    qn = (mid.month - 1) // 3 + 1
    return (mid.year, qn)


def q_label(yq) -> str:
    return f"{yq[0]}Q{yq[1]}"


def in_window(yq) -> bool:
    return (START.year, (START.month - 1) // 3 + 1) <= yq <= (END.year, (END.month - 1) // 3 + 1)

# --------------------------------------------------------------------------- #
# HTTP layer (bulk companyfacts + cache + throttle + backoff)
# --------------------------------------------------------------------------- #
_last_req = [0.0]


def _throttle():
    gap = 1.0 / REQUESTS_PER_SEC
    delta = time.time() - _last_req[0]
    if delta < gap:
        time.sleep(gap - delta)
    _last_req[0] = time.time()


def make_session(identity: str):
    s = requests.Session()
    s.headers.update({"User-Agent": identity, "Accept-Encoding": "gzip, deflate"})
    return s


def fetch_companyfacts(cik: int, session, cache_dir: Path, max_retries: int = 5) -> dict:
    cache = cache_dir / f"CIK{cik:010d}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    url = CF_URL.format(cik=cik)
    for attempt in range(max_retries):
        _throttle()
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache.write_text(r.text)
                return r.json()
            if r.status_code in (403, 429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
        except requests.RequestException:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch companyfacts for CIK {cik}")


def merge_companyfacts(jsons: list[dict]) -> dict:
    """Union us-gaap facts across CIKs (handles Alphabet's two CIKs)."""
    if len(jsons) == 1:
        return jsons[0]
    merged = {"facts": {"us-gaap": {}}}
    for j in jsons:
        for concept, node in j.get("facts", {}).get("us-gaap", {}).items():
            m = merged["facts"]["us-gaap"].setdefault(concept, {"units": {}})
            for unit, items in node.get("units", {}).items():
                m["units"].setdefault(unit, []).extend(items)
    return merged

# --------------------------------------------------------------------------- #
# Extraction + dedup
# --------------------------------------------------------------------------- #
def iter_concept_facts(facts: dict, concept: str) -> list[dict]:
    node = facts.get("facts", {}).get("us-gaap", {}).get(concept)
    if not node:
        return []
    out = []
    for unit, items in node.get("units", {}).items():
        for it in items:
            if "start" not in it or "end" not in it:
                continue  # we only want duration (flow) facts
            out.append({
                "concept": concept, "unit": unit,
                "start": _d(it["start"]), "end": _d(it["end"]),
                "val": it["val"], "accn": it.get("accn"),
                "form": it.get("form"), "fy": it.get("fy"), "fp": it.get("fp"),
                "filed": _d(it["filed"]) if it.get("filed") else None,
            })
    return out


def pick_fact(group: list[dict]) -> dict:
    """Earliest-filed wins; a same-period amendment (/A) overrides."""
    amendments = [f for f in group if (f["form"] or "").endswith("/A")]
    if amendments:
        return max(amendments, key=lambda f: f["filed"] or date.min)
    return min(group, key=lambda f: f["filed"] or date.max)


def resolve_series(by_concept: dict, concepts: list[str], kind: str) -> dict:
    """Coalesce across the fallback tag list, deduped, for one period kind.
    Returns {(start, end): fact}."""
    chosen: dict = {}
    for concept in concepts:  # priority order
        facts = [f for f in by_concept.get(concept, [])
                 if period_kind(f["start"], f["end"]) == kind]
        groups: dict = {}
        for f in facts:
            groups.setdefault((f["start"], f["end"]), []).append(f)
        for key, grp in groups.items():
            if key in chosen:
                continue  # higher-priority tag already supplied this period
            chosen[key] = pick_fact(grp)
    return chosen

# --------------------------------------------------------------------------- #
# Quarter assembly
# --------------------------------------------------------------------------- #
def build_metric(by_concept: dict, concepts: list[str], metric: str,
                 ticker: str) -> list[dict]:
    quarters = resolve_series(by_concept, concepts, "Q")
    rows = []

    # direct quarterly observations (Q1-Q3, sometimes a filed Q4)
    for (s, e), f in quarters.items():
        rows.append(_row(ticker, metric, s, e, f["val"], False, f))

    if metric in ADDITIVE:
        annuals = resolve_series(by_concept, concepts, "A")
        for (as_, ae), af in annuals.items():
            inside = [((s, e), f) for (s, e), f in quarters.items()
                      if as_ <= s and e <= ae]
            # only derive when we have a clean Q1+Q2+Q3 and Q4 isn't already filed
            already_q4 = any(cal_quarter(s, e) == cal_quarter(
                max(e for (_, e), _ in inside) + timedelta(days=1), ae)
                for (s, e), _ in inside) if inside else False
            if len(inside) == 3 and not already_q4:
                q4val = af["val"] - sum(f["val"] for (_, _), f in inside)
                q4start = max(e for (_, e), _ in inside) + timedelta(days=1)
                rows.append(_row(ticker, metric, q4start, ae, q4val, True, af))
    return rows


def resolve_all(by_concept: dict, concepts: list[str]) -> dict:
    """Coalesce + dedup across the fallback tag list, all period kinds.
    Returns {(start, end): fact}."""
    chosen: dict = {}
    for concept in concepts:  # priority order
        groups: dict = {}
        for f in by_concept.get(concept, []):
            groups.setdefault((f["start"], f["end"]), []).append(f)
        for key, grp in groups.items():
            if key in chosen:
                continue
            chosen[key] = pick_fact(grp)
    return chosen


def build_cashflow_metric(by_concept: dict, concepts: list[str], metric: str,
                          ticker: str) -> list[dict]:
    """Cash-flow items are filed year-to-date (cumulative). For each fiscal year,
    build the cumulative-from-FY-start curve at each quarter end using whatever is
    available -- YTD checkpoints (3/6/9/12-month) and/or discrete 3-month quarters,
    in any mix -- then difference to get the four discrete quarters. This handles
    pure-YTD reporting, pure-discrete reporting, and messy mixed years (e.g. AMZN
    2017, where only Q1, Q3, the 9-month YTD, and the annual survive). A final pass
    recovers filed quarters of an in-progress fiscal year that has no annual yet."""
    one = timedelta(days=1)
    chosen = resolve_all(by_concept, concepts)
    annuals = {(s, e): f for (s, e), f in chosen.items() if period_kind(s, e) == "A"}
    annual_spans = list(annuals.keys())
    rows = []
    emitted = set()

    def emit(s, e, v, src, der):
        yq = cal_quarter(s, e)
        if yq in emitted:
            return
        emitted.add(yq)
        rows.append(_row(ticker, metric, s, e, v, der, src))

    for (as_, ae), af in annuals.items():
        within = {(s, e): f for (s, e), f in chosen.items()
                  if as_ <= s and e <= ae and not (s == as_ and e == ae)}
        disc = {(s, e): f for (s, e), f in within.items() if period_kind(s, e) == "Q"}

        cum = {as_ - one: 0}            # cumulative capex from FY start; 0 before it
        cum_src = {}
        for (s, e), f in within.items():   # YTD checkpoints share the FY start
            if s == as_:
                cum[e] = f["val"]
                cum_src[e] = f
        cum[ae] = af["val"]

        changed = True                  # use discrete quarters to fill holes
        while changed:
            changed = False
            for (s, e), f in disc.items():
                prev = s - one
                if e in cum and prev not in cum:
                    cum[prev] = cum[e] - f["val"]
                    changed = True
                elif prev in cum and e not in cum:
                    cum[e] = cum[prev] + f["val"]
                    changed = True

        prev_t = as_ - one
        for t in sorted(t for t in cum if t > as_ - one):
            period = (prev_t + one, t)
            if period in disc:                       # directly filed quarter
                src, der = disc[period], False
            elif t in cum_src:                       # differenced from a YTD checkpoint
                src, der = cum_src[t], True
            else:                                    # differenced against the annual
                src, der = af, True
            emit(prev_t + one, t, cum[t] - cum[prev_t], src, der)
            prev_t = t

    # in-progress fiscal year (no annual yet) -> emit its filed 3-month quarters
    def in_completed_fy(s, e):
        return any(a_s <= s and e <= a_e for (a_s, a_e) in annual_spans)
    for (s, e), f in sorted(chosen.items()):
        if period_kind(s, e) == "Q" and not in_completed_fy(s, e):
            emit(s, e, f["val"], f, False)
    return rows


def _row(ticker, metric, start, end, val, derived, src) -> dict:
    yq = cal_quarter(start, end)
    return {
        "ticker": ticker, "calendar_quarter": q_label(yq), "_yq": yq,
        "metric": metric, "value": val,
        "period_start": start, "period_end": end, "derived_q4": derived,
        "source_form": src.get("form"), "source_accn": src.get("accn"),
        "filed": src.get("filed"),
    }

# --------------------------------------------------------------------------- #
# Assemble tables
# --------------------------------------------------------------------------- #
def assemble(long_rows: list[dict]):
    df = pd.DataFrame(long_rows)
    df = df[df["_yq"].map(in_window)].copy()

    # safety: one value per (ticker, metric, calendar_quarter); keep most recent period
    df.sort_values(["ticker", "metric", "calendar_quarter", "period_end"], inplace=True)
    df = df.drop_duplicates(["ticker", "metric", "calendar_quarter"], keep="last")

    long_df = df.drop(columns="_yq").sort_values(
        ["ticker", "metric", "calendar_quarter"]).reset_index(drop=True)

    wide = df.pivot_table(index=["ticker", "calendar_quarter"],
                          columns="metric", values="value", aggfunc="last").reset_index()
    # computed fields
    def safe_div(a, b):
        return a / b if (pd.notna(a) and pd.notna(b) and b != 0) else pd.NA
    for col in ["revenue", "gross_profit", "operating_income", "net_income",
                "eps_diluted", "diluted_shares", "capex"]:
        if col not in wide.columns:
            wide[col] = pd.NA
    wide["gross_margin"] = wide.apply(lambda r: safe_div(r["gross_profit"], r["revenue"]), axis=1)
    wide["operating_margin"] = wide.apply(lambda r: safe_div(r["operating_income"], r["revenue"]), axis=1)
    wide["net_margin"] = wide.apply(lambda r: safe_div(r["net_income"], r["revenue"]), axis=1)
    wide["eps_diluted_calc"] = wide.apply(lambda r: safe_div(r["net_income"], r["diluted_shares"]), axis=1)
    wide = wide.sort_values(["ticker", "calendar_quarter"]).reset_index(drop=True)
    return long_df, wide


def completeness(long_df: pd.DataFrame) -> pd.DataFrame:
    recs = []
    for (ticker, metric), g in long_df.groupby(["ticker", "metric"]):
        yqs = sorted({tuple(map(int, q[:-2].split("Q") if False else q.split("Q")))
                      for q in g["calendar_quarter"]})
        yqs = sorted({(int(q.split("Q")[0]), int(q.split("Q")[1]))
                      for q in g["calendar_quarter"]})
        if not yqs:
            continue
        first, last = yqs[0], yqs[-1]
        span = []
        y, qn = first
        while (y, qn) <= last:
            span.append((y, qn))
            qn += 1
            if qn > 4:
                qn = 1
                y += 1
        present = set(yqs)
        # per-share metrics carry no derived Q4 by design -> don't flag those as gaps
        if metric in REPORTED_ONLY:
            span = [q for q in span if q[1] != 4]
            present = {q for q in present if q[1] != 4}
        missing = [q_label(q) for q in span if q not in present]
        recs.append({
            "ticker": ticker, "metric": metric, "n_found": len(yqs),
            "first_quarter": q_label(first), "last_quarter": q_label(last),
            "n_interior_gaps": len(missing),
            "interior_gaps": ";".join(missing) if missing else "",
        })
    return pd.DataFrame(recs).sort_values(["ticker", "metric"]).reset_index(drop=True)

# --------------------------------------------------------------------------- #
# Live ingestion
# --------------------------------------------------------------------------- #
def run(identity: str, outdir: Path, cachedir: Path):
    if requests is None:
        sys.exit("`requests` is required for the live pull: pip install requests")
    session = make_session(identity)
    long_rows = []
    for ticker, cfg in COMPANIES.items():
        print(f"[fetch] {ticker} CIK(s) {cfg['ciks']}")
        jsons = [fetch_companyfacts(c, session, cachedir) for c in cfg["ciks"]]
        facts = merge_companyfacts(jsons)
        for metric in NEEDS[cfg["needs"]]:
            by_concept = {c: iter_concept_facts(facts, c) for c in CONCEPTS[metric]}
            builder = build_cashflow_metric if metric in CASHFLOW else build_metric
            long_rows.extend(builder(by_concept, CONCEPTS[metric], metric, ticker))

    long_df, wide = assemble(long_rows)
    report = completeness(long_df)

    outdir.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(outdir / "sec_fundamentals_long.csv", index=False)
    wide.to_csv(outdir / "sec_fundamentals_wide.csv", index=False)
    report.to_csv(outdir / "sec_completeness_report.csv", index=False)
    print(f"[done] {len(long_df)} long rows -> {outdir}")
    print(report.to_string(index=False))

# --------------------------------------------------------------------------- #
# Offline self-test (no network) - proves the transformation rules
# --------------------------------------------------------------------------- #
def _synthetic_facts() -> dict:
    def f(start, end, val, accn, form, filed):
        return {"start": start, "end": end, "val": val, "accn": accn,
                "form": form, "fy": int(start[:4]), "fp": "Q", "filed": filed}
    rev_old = [  # FY2010 reported under legacy "Revenues" tag
        f("2010-01-01", "2010-03-31", 100, "a1", "10-Q", "2010-05-01"),   # Q1 original
        f("2010-01-01", "2010-03-31", 999, "a9", "10-Q", "2011-05-01"),   # Q1 restated later -> must LOSE
        f("2010-04-01", "2010-06-30", 110, "a2", "10-Q", "2010-08-01"),   # Q2 original
        f("2010-04-01", "2010-06-30", 115, "a2A", "10-Q/A", "2010-09-01"),  # Q2 amendment -> must WIN
        f("2010-07-01", "2010-09-30", 120, "a3", "10-Q", "2010-11-01"),   # Q3
        f("2010-01-01", "2010-09-30", 330, "a3", "10-Q", "2010-11-01"),   # 9-month YTD -> must be IGNORED
        f("2010-01-01", "2010-12-31", 500, "a4", "10-K", "2011-02-01"),   # annual -> Q4 = 500-(100+115+120)=165
    ]
    rev_new = [  # FY2011 reported under ASC 606 tag (tag-switch test)
        f("2011-01-01", "2011-03-31", 200, "b1", "10-Q", "2011-05-01"),
        f("2011-04-01", "2011-06-30", 210, "b2", "10-Q", "2011-08-01"),
        f("2011-07-01", "2011-09-30", 220, "b3", "10-Q", "2011-11-01"),
        f("2011-01-01", "2011-12-31", 900, "b4", "10-K", "2012-02-01"),   # Q4 = 900-630 = 270
    ]
    cap = [  # capex: Style B cumulative YTD (FY2020) + Style A discrete (FY2021)
        f("2020-01-01", "2020-03-31", 10, "c1", "10-Q", "2020-05-01"),   # Q1 (3-month/cum1)
        f("2020-01-01", "2020-06-30", 25, "c2", "10-Q", "2020-08-01"),   # H1 cumulative
        f("2020-01-01", "2020-09-30", 45, "c3", "10-Q", "2020-11-01"),   # 9-month cumulative
        f("2020-01-01", "2020-12-31", 70, "c4", "10-K", "2021-02-01"),   # annual
        f("2021-01-01", "2021-03-31", 12, "d1", "10-Q", "2021-05-01"),   # discrete 3-month
        f("2021-04-01", "2021-06-30", 13, "d2", "10-Q", "2021-08-01"),
        f("2021-07-01", "2021-09-30", 14, "d3", "10-Q", "2021-11-01"),
        f("2021-01-01", "2021-12-31", 60, "d4", "10-K", "2022-02-01"),   # Q4 = 60-39 = 21
        f("2022-01-01", "2022-03-31", 5, "e1", "10-Q", "2022-05-01"),    # in-progress FY:
        f("2022-04-01", "2022-06-30", 6, "e2", "10-Q", "2022-08-01"),    # Q1,Q2 filed, no annual
        f("2023-01-01", "2023-03-31", 100, "m1", "10-Q", "2023-05-01"),  # mixed year (like AMZN 2017):
        f("2023-07-01", "2023-09-30", 130, "m3", "10-Q", "2023-11-01"),  #   Q1 + Q3 discrete,
        f("2023-01-01", "2023-09-30", 350, "m9", "10-Q", "2023-11-01"),  #   9-month YTD,
        f("2023-01-01", "2023-12-31", 500, "m12", "10-K", "2024-02-01"), #   annual -- no Q2 / 6-month
    ]
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": rev_old}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": rev_new}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": cap}},
    }}}


def selftest():
    facts = _synthetic_facts()
    by_concept = {c: iter_concept_facts(facts, c) for c in CONCEPTS["revenue"]}
    rows = build_metric(by_concept, CONCEPTS["revenue"], "revenue", "TEST")
    long_df, wide = assemble(rows)
    got = dict(zip(long_df["calendar_quarter"], long_df["value"]))
    expected = {"2010Q1": 100, "2010Q2": 115, "2010Q3": 120, "2010Q4": 165,
                "2011Q1": 200, "2011Q2": 210, "2011Q3": 220, "2011Q4": 270}

    ok = True
    print("quarter   expected   got")
    for q in expected:
        g = got.get(q)
        flag = "" if g == expected[q] else "  <-- MISMATCH"
        if g != expected[q]:
            ok = False
        print(f"{q}     {expected[q]:>6}   {g!s:>5}{flag}")

    checks = {
        "8 quarters produced": len(got) == 8,
        "no extra quarter from 9-month YTD": "2010Q3" in got and len(got) == 8,
        "earliest-filed wins on 2010Q1 (100 not 999)": got.get("2010Q1") == 100,
        "amendment overrides 2010Q2 (115 not 110)": got.get("2010Q2") == 115,
        "Q4 derived correctly (165)": got.get("2010Q4") == 165,
        "tag-switch coalesced 2011 (ASC 606)": got.get("2011Q1") == 200,
        "Q4 flagged derived": bool(long_df.loc[long_df.calendar_quarter == "2010Q4", "derived_q4"].iloc[0]),
        "Q1-Q3 flagged not-derived": not bool(long_df.loc[long_df.calendar_quarter == "2010Q1", "derived_q4"].iloc[0]),
    }
    print("\nchecks (revenue / income path):")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        ok = ok and v

    # capex path: cumulative-YTD differencing (Style B) + discrete fallback (Style A)
    cap_by = {c: iter_concept_facts(facts, c) for c in CONCEPTS["capex"]}
    cap_rows = build_cashflow_metric(cap_by, CONCEPTS["capex"], "capex", "TEST")
    cap_long, _ = assemble(cap_rows)
    cap = dict(zip(cap_long["calendar_quarter"], cap_long["value"]))
    cap_exp = {"2020Q1": 10, "2020Q2": 15, "2020Q3": 20, "2020Q4": 25,
               "2021Q1": 12, "2021Q2": 13, "2021Q3": 14, "2021Q4": 21,
               "2022Q1": 5, "2022Q2": 6,                       # in-progress FY: filed only
               "2023Q1": 100, "2023Q2": 120, "2023Q3": 130, "2023Q4": 150}  # mixed-year solve
    print("\nchecks (capex path):")
    for q, want in cap_exp.items():
        gv = cap.get(q)
        passed = gv == want
        ok = ok and passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {q} = {want} (got {gv})")
    # in-progress year must NOT fabricate Q3/Q4 (no annual to derive from)
    no_fab = ("2022Q3" not in cap) and ("2022Q4" not in cap)
    ok = ok and no_fab
    print(f"  [{'PASS' if no_fab else 'FAIL'}] in-progress FY2022 has no fabricated Q3/Q4")

    print("\nSELF-TEST:", "ALL PASSED ✅" if ok else "FAILURES ❌")
    return 0 if ok else 1

# --------------------------------------------------------------------------- #
# Diagnostic: dump raw deduped facts for one ticker/metric/year
# --------------------------------------------------------------------------- #
def inspect(identity, ticker, metric, year, cachedir):
    if requests is None:
        sys.exit("`requests` is required to inspect (it fetches companyfacts).")
    yr = int(year)
    session = make_session(identity)
    cfg = COMPANIES[ticker]
    facts = merge_companyfacts(
        [fetch_companyfacts(c, session, cachedir) for c in cfg["ciks"]])
    by_concept = {c: iter_concept_facts(facts, c) for c in CONCEPTS[metric]}
    chosen = resolve_all(by_concept, CONCEPTS[metric])
    print(f"{ticker} {metric}: raw deduped duration facts touching {yr}")
    print(f"{'period':<26}{'days':>5}{'kind':>6}{'value':>20}  form     concept / filed")
    for (s, e), f in sorted(chosen.items()):
        if s.year == yr or e.year == yr:
            print(f"{str(s)+'..'+str(e):<26}{(e - s).days:>5}{period_kind(s, e):>6}"
                  f"{f['val']:>20}  {str(f['form']):<8} {f['concept']}  (filed {f['filed']})")

# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="SEC EDGAR fundamentals ingestion")
    ap.add_argument("--selftest", action="store_true", help="run offline logic tests")
    ap.add_argument("--inspect", nargs=3, metavar=("TICKER", "METRIC", "YEAR"),
                    help="dump raw deduped facts, e.g. --inspect AMZN capex 2017")
    ap.add_argument("--identity", default=None,
                    help="SEC User-Agent, e.g. 'Your Name you@email.com' "
                         "(or set the SEC_IDENTITY environment variable)")
    ap.add_argument("--outdir", default="Data/outputs", type=Path)
    ap.add_argument("--cachedir", default="Data/sec_cache", type=Path)
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())

    identity = args.identity or os.environ.get("SEC_IDENTITY")
    if not identity:
        sys.exit(
            "No SEC contact configured. SEC's fair-access policy requires a "
            "User-Agent with a real contact.\n"
            '  PowerShell:  $env:SEC_IDENTITY = "Your Name you@email.com"\n'
            '  bash/zsh:    export SEC_IDENTITY="Your Name you@email.com"\n'
            '  or pass:     --identity "Your Name you@email.com"'
        )

    if args.inspect:
        inspect(identity, args.inspect[0], args.inspect[1], args.inspect[2], args.cachedir)
        return
    run(identity, args.outdir, args.cachedir)


if __name__ == "__main__":
    main()
