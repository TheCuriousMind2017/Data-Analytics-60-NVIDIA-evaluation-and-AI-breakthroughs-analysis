"""
NVIDIA Project — Dataset Download Script
-----------------------------------------
Downloads daily stock price data for NVDA, QQQ, AMD, and INTC
from Yahoo Finance using yfinance.

Saves 4 CSV files to a 'data/' folder in the same directory as this script.

How to run:
    1. Open a Python environment
    2. Type: pip install yfinance pandas
    3. Navigate to the folder where this script is saved
    4. Type: python download_datasets.py
"""

import yfinance as yf
import pandas as pd
import os

# ── Output folder ──────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)

# ── Date range ─────────────────────────────────────────────────────────────────
START = "2010-01-01"
END   = "2026-05-17"

# ── Helper function ────────────────────────────────────────────────────────────
def download(ticker, filename):
    print(f"Downloading {ticker}...")
    df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
    df = df[["Close", "Volume"]]
    df.columns = ["Close", "Volume"]
    df.index.name = "Date"
    df.reset_index(inplace=True)
    df.to_csv(f"data/{filename}", index=False)
    print(f"  Saved → data/{filename} | {len(df)} rows | {df['Date'].min().date()} to {df['Date'].max().date()}")

# ── Download all four ──────────────────────────────────────────────────────────
download("NVDA", "nvda_stock_price.csv")
download("QQQ",  "qqq_price.csv")
download("AMD",  "amd_stock_price.csv")
download("INTC", "intc_stock_price.csv")

print("\nAll 4 datasets downloaded successfully.")
