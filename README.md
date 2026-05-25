# BAC SMA

BAC SMA is a Streamlit application that helps you shortlist potentially undervalued Indian stocks from the Nifty 500 universe.

It does this by:
- Fetching the latest Nifty 500 constituents from NSE India (with local caching)
- Pulling fundamentals and price data from Yahoo Finance (`yfinance`)
- Scoring each stock out of 100 using a 7-factor value-oriented model
- Classifying results as `Strong Buy`, `Buy`, `Hold`, or `Avoid`
- Presenting the output in an interactive dashboard with filters, charts, deep-dive views, and CSV export
- Saving every completed scan to a local SQLite history database for later review

## Purpose

The purpose of this application is to speed up fundamental stock screening for research.
It is designed to give a data-driven first pass across many stocks so you can identify candidates for deeper analysis.

It is not meant to generate automatic buy/sell signals.

## How Scoring Works

Each stock gets a composite score (0-100) from these metrics:
- P/E ratio (20 points)
- ROE (20 points)
- Debt/Equity (15 points; neutral handling for financial-sector companies)
- P/B ratio (15 points)
- EPS growth (15 points)
- Revenue growth (10 points)
- Dividend yield (5 points)

The default points above are editable from the **Screening Logic** page.
You can disable a metric or change its weight, and the app normalizes the final score back to 100.

Recommendation thresholds:
- `>= 75`: Strong Buy
- `>= 60`: Buy
- `>= 45`: Hold
- `< 45`: Avoid

## Key Features

- Live Nifty 500 constituent loading from NSE with cache fallback
- Sector filtering before running scans
- Scan progress for large batches
- Dashboard tab with recommendation mix, score distribution, and sector averages
- Screener table with sorting/filtering and CSV download
- Top Picks view for highest-scoring stocks
- Deep Dive view with:
  - 1-year price chart
  - 20-day and 50-day moving averages
  - Metric-wise score breakdown (radar chart)
  - 52-week price position gauge
- Screening Logic page:
  - Enable/disable each scoring parameter
  - Adjust per-parameter weightage without code changes
  - Save logic to `data/screening_logic.json`
- History screen:
  - Every completed scan is saved automatically
  - Each scan gets a unique ID in format `SCANTYPE_YYYYMMDD_HHMMSS_microseconds`
  - You can browse previous scans and reopen their saved results

## Project Structure

```text
.
|-- app.py           # Streamlit UI and workflow
|-- core/
|   |-- scan_history.py   # Local SQLite storage for scan history
|   |-- screener.py       # Data fetch and scoring engine
|   |-- screening_logic.py # JSON config load/save and defaults
|   `-- tickers.py        # Nifty 500 fetch + caching logic
|-- data/
|   |-- screening_logic.json # Saved screening logic (enabled flags + weights)
|   |-- scan_history.db      # Local scan history database
|   `-- nifty500_cache.csv   # Cached Nifty 500 constituents
|-- pages/
|   |-- History.py         # Streamlit page wrapper
|   `-- Screening_Logic.py # Streamlit page wrapper
|-- screens/
|   |-- history_screen.py         # History screen implementation
|   `-- screening_logic_screen.py # Screening logic page implementation
|-- requirements.txt
`-- README.md
```

## Run Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the app:

```bash
streamlit run app.py
```

3. Open the local URL shown by Streamlit (usually `http://localhost:8501`).

## Data Sources

- NSE India (`niftyindices.com`) for Nifty 500 constituents
- Yahoo Finance (via `yfinance`) for fundamentals and price history

## Limitations

- Uses mostly trailing/backward-looking metrics
- Depends on Yahoo Finance field availability and quality
- Does not include qualitative factors (management quality, moat, governance, etc.)
- Should be used as a research shortlist, not as direct investment advice

## Disclaimer

This tool is for educational and research use only and does not constitute financial advice.
Always do your own due diligence and consult a registered financial advisor before making investment decisions.
