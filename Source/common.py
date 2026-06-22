"""
common.py — shared scaffolding for the descriptive and diagnostic analyses
==========================================================================

Single source of truth for everything both analysis notebooks must agree on:
the three era definitions, the AI milestone markers, the faint confounder
bands, a fixed colour per ticker/segment, the panel/segment loaders, and a set
of matplotlib helpers that draw the era shading and milestone lines identically
on every chart.

This module lives in Source/ and resolves the data directory relative to its
own location (via __file__), so it works no matter which folder a notebook runs
from. The notebooks themselves only need to put Source/ on the import path. Drop
this at the top of each notebook (walks up to the repo root, then imports):

    import sys
    from pathlib import Path
    for _p in [Path.cwd(), *Path.cwd().parents]:
        if (_p / "Source" / "common.py").exists():
            sys.path.insert(0, str(_p / "Source")); break
    import common
    common.apply_style()
    panel = common.load_panel()

Eras (per the README's three-era model):
    Pre-Attention / CNN   2010Q1 - 2017Q2   (AlexNet 2012Q3 sits inside this band)
    Transformer           2017Q3 - 2022Q3
    Generative-AI         2022Q4 - 2026Q1
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Paths (resolved relative to this file, not the caller's working directory)
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "Data" / "outputs"
PANEL_CSV = DATA_DIR / "master_quarterly_panel.csv"
SEGMENTS_CSV = DATA_DIR / "nvda_segments_annual.csv"


# --------------------------------------------------------------------------- #
# Eras, milestones, confounders
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Era:
    name: str
    start_q: str          # inclusive, e.g. "2010Q1"
    end_q: str            # inclusive, e.g. "2017Q2"
    color: str

    @property
    def start(self) -> pd.Timestamp:
        return pd.Period(self.start_q, "Q").start_time

    @property
    def end(self) -> pd.Timestamp:
        return pd.Period(self.end_q, "Q").end_time


@dataclass(frozen=True)
class Milestone:
    name: str
    quarter: str          # the quarter it lands in, e.g. "2017Q3"

    @property
    def date(self) -> pd.Timestamp:
        return pd.Period(self.quarter, "Q").start_time


@dataclass(frozen=True)
class Span:
    name: str
    start_q: str
    end_q: str

    @property
    def start(self) -> pd.Timestamp:
        return pd.Period(self.start_q, "Q").start_time

    @property
    def end(self) -> pd.Timestamp:
        return pd.Period(self.end_q, "Q").end_time


# Three eras. Colours are light/recessive (drawn at low alpha) — grey for the
# baseline era, cool blue for Transformer, warm amber for Generative-AI so the
# eye is drawn to the gen-AI period without the shading shouting.
ERAS: list[Era] = [
    Era("Pre-Attention / CNN", "2010Q1", "2017Q2", "#b0bec5"),
    Era("Transformer",         "2017Q3", "2022Q3", "#90caf9"),
    Era("Generative-AI",       "2022Q4", "2026Q1", "#ffcc80"),
]

# AlexNet is a marker *inside* the first band; the other two coincide with the
# band boundaries they define.
MILESTONES: list[Milestone] = [
    Milestone("AlexNet (ImageNet)", "2012Q3"),
    Milestone("Transformer",        "2017Q3"),
    Milestone("ChatGPT",            "2022Q4"),
]

# Confounders to keep visible but recessive, so we don't misread a crypto/COVID
# bump as an AI-era effect.
CONFOUNDERS: list[Span] = [
    Span("Crypto 2017-18", "2017Q2", "2018Q1"),
    Span("COVID-19",       "2020Q1", "2020Q2"),
    Span("Crypto 2020-21", "2020Q4", "2021Q4"),
]


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #
TICKER_COLORS: dict[str, str] = {
    "NVDA": "#76b900",   # NVIDIA green
    "AMD":  "#ed1c24",   # AMD red
    "INTC": "#0071c5",   # Intel blue
    "NDX":  "#555555",   # Nasdaq-100 (benchmark)
    "SOX":  "#9467bd",   # PHLX Semiconductor (benchmark)
    # hyperscalers (Pillar 6 capex)
    "MSFT":  "#f25022",
    "GOOGL": "#4285f4",
    "AMZN":  "#ff9900",
    "META":  "#0668e1",
}
BENCHMARKS = {"NDX", "SOX"}
HYPERSCALERS = ["MSFT", "GOOGL", "AMZN", "META"]

SEGMENT_COLORS: dict[str, str] = {
    "gaming":            "#76b900",
    "data_center":       "#1f77b4",
    "pro_viz":           "#9467bd",
    "oem_other":         "#8c8c8c",
    "other_unallocated": "#dcdcdc",
}
SEGMENT_LABELS: dict[str, str] = {
    "gaming":            "Gaming",
    "data_center":       "Data Center",
    "pro_viz":           "Pro Visualization",
    "oem_other":         "OEM & Other",
    "other_unallocated": "Unallocated",
}

MILESTONE_COLOR = "#37474f"
CONFOUNDER_COLOR = "#9e9e9e"


def color(ticker: str) -> str:
    """Fixed colour for a ticker (falls back to dark grey)."""
    return TICKER_COLORS.get(ticker, "#333333")


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def load_panel(path: str | Path | None = None) -> pd.DataFrame:
    """Master quarterly panel with parsed `date` and `period`, plus an `era` column."""
    df = pd.read_csv(Path(path) if path else PANEL_CSV)
    df["date"] = pd.to_datetime(df["quarter_end_date"])
    df["period"] = df["calendar_quarter"].map(lambda q: pd.Period(q, "Q"))
    df["era"] = df["calendar_quarter"].map(era_of)
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


def load_segments(path: str | Path | None = None) -> pd.DataFrame:
    """NVIDIA annual revenue-by-segment table (adds a mid-year `date` for plotting)."""
    df = pd.read_csv(Path(path) if path else SEGMENTS_CSV)
    df["date"] = pd.to_datetime(dict(year=df["calendar_year"], month=7, day=1))
    return df.sort_values("calendar_year").reset_index(drop=True)


def ticker_series(panel: pd.DataFrame, ticker: str, col: str) -> pd.DataFrame:
    """`date` + `col` for one ticker, dropna, sorted — convenient for line plots."""
    return (panel[panel["ticker"] == ticker][["date", col]]
            .dropna().sort_values("date").reset_index(drop=True))


def era_of(quarter: str) -> str | None:
    """Which era a 'YYYYQn' quarter falls in (None if outside all eras)."""
    p = pd.Period(quarter, "Q")
    for era in ERAS:
        if pd.Period(era.start_q, "Q") <= p <= pd.Period(era.end_q, "Q"):
            return era.name
    return None


# --------------------------------------------------------------------------- #
# Matplotlib helpers
# --------------------------------------------------------------------------- #
def apply_style() -> None:
    """Apply the shared chart style. Call once near the top of a notebook."""
    import matplotlib as mpl
    mpl.rcParams.update({
        "figure.figsize": (11, 5.5),
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.alpha": 0.25,
        "grid.linewidth": 0.6,
        "font.size": 10,
        "axes.titlesize": 12.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 10.5,
        "legend.frameon": False,
        "legend.fontsize": 9,
    })


def add_era_bands(ax, *, alpha: float = 0.13, label: bool = False,
                  label_fontsize: float = 8) -> None:
    """Shade the three eras on a datetime x-axis."""
    for era in ERAS:
        ax.axvspan(era.start, era.end, color=era.color, alpha=alpha, lw=0, zorder=0)
        if label:
            mid = era.start + (era.end - era.start) / 2
            ax.text(mid, 0.985, era.name, transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=label_fontsize,
                    color="#455a64", zorder=1)


def add_milestones(ax, *, label: bool = True, label_fontsize: float = 8) -> None:
    """Vertical dashed lines for the three AI milestones.

    Labels are drawn vertically *inside* the top of the axes (with a faint white
    backing) so they never collide with the title or legend above the plot.
    """
    for m in MILESTONES:
        ax.axvline(m.date, color=MILESTONE_COLOR, ls="--", lw=1.0, alpha=0.75, zorder=2)
        if label:
            ax.text(m.date, 0.975, f"{m.name} ", transform=ax.get_xaxis_transform(),
                    rotation=90, ha="right", va="top", fontsize=label_fontsize,
                    color=MILESTONE_COLOR, zorder=3,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.55))


def add_confounders(ax, *, alpha: float = 0.07) -> None:
    """Faint grey spans for crypto/COVID windows."""
    for c in CONFOUNDERS:
        ax.axvspan(c.start, c.end, color=CONFOUNDER_COLOR, alpha=alpha, lw=0, zorder=0)


def annotate(ax, *, eras: bool = True, milestones: bool = True,
             confounders: bool = True, era_labels: bool = False,
             milestone_labels: bool = True) -> None:
    """Draw confounders, era bands, and milestone lines in the right z-order."""
    if confounders:
        add_confounders(ax)
    if eras:
        add_era_bands(ax, label=era_labels)
    if milestones:
        add_milestones(ax, label=milestone_labels)


def style_time_axis(ax, *, every: int = 2) -> None:
    """Year ticks on a datetime x-axis."""
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.YearLocator(every))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def set_log(ax, axis: str = "y") -> None:
    if axis in ("y", "both"):
        ax.set_yscale("log")
    if axis in ("x", "both"):
        ax.set_xscale("log")


def set_symlog(ax, axis: str = "y", linthresh: float = 1.0) -> None:
    if axis in ("y", "both"):
        ax.set_yscale("symlog", linthresh=linthresh)
    if axis in ("x", "both"):
        ax.set_xscale("symlog", linthresh=linthresh)
