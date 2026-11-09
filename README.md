# BAC SMA

BAC SMA is a Streamlit application for shortlisting Indian stocks from the Nifty 500 using a
multi-factor fundamental score. It is a research tool, not a source of buy/sell signals.

## Principles

- **Nothing is assumed.** If Yahoo Finance does not provide a value, the app shows
  **Not available** and leaves that metric out of the score. Missing data is never scored as 0
  and never given default points.
- **Every stock is accounted for.** Each scan reports how many stocks were in scope, scored,
  disqualified (with the reason and the actual value) and without data (with the error).
- **Data freshness is visible.** Each stock shows when its fundamentals were downloaded.

## How scoring works

Ten metrics, each converted to points on a piecewise-linear curve:

| Metric | Default weight | Yahoo Finance field |
|---|---|---|
| P/E | 12 | `trailingPE` |
| PEG | 13 | `pegRatio`, else `trailingPegRatio` |
| P/B | 10 | `priceToBook` |
| ROE | 13 | `returnOnEquity` (TTM) |
| ROA | 7 | `returnOnAssets` (TTM) |
| D/E | 10 | `debtToEquity` (reported in %, converted to a ratio) |
| FCF Yield | 10 | `freeCashflow` / `marketCap` |
| Op Margin | 8 | `operatingMargins` (TTM) |
| Earnings Growth | 10 | `earningsQuarterlyGrowth` (latest quarter, year over year) |
| Revenue Growth | 7 | `revenueGrowth` (latest quarter, year over year) |

- **Score (0–100)** = points earned ÷ weight of the metrics that have data × 100.
- **Data Coverage** = share of the enabled weight backed by real data. Below the minimum
  (default 70%) the stock is rated **Insufficient Data** instead of receiving a recommendation.
- **Financial Services** stocks: D/E is *not applicable* and is excluded (not given assumed points).
  The current-ratio and D/E hard filters are not applied to them.
- **FCF Yield** is only computed when cash flow and market cap are in the same currency.
- Zero or negative P/E, PEG, P/B and negative D/E (negative equity) are real values and score 0.

Recommendation thresholds (editable): `>= 75` Strong Buy, `>= 60` Buy, `>= 45` Hold, otherwise Avoid.

### Hard filters

A stock is disqualified only if the relevant value exists and:

- current ratio < 0.8 (non-financials),
- trailing 12-month ROE is negative,
- D/E > 3.0x (non-financials), or
- free cash flow and operating margin are both negative.

All triggered reasons are listed in the **Excluded** tab.

## Features

- Live Nifty 500 constituents from NSE Indices; if NSE is unreachable the last saved list is used
  and the app says so, with its date.
- Fundamentals cache (`data/base_data.csv`) updated per stock. **Run Scan** downloads only stocks that
  are missing or older than the chosen age (default 24 h). Failed downloads keep older data and are listed
  with Yahoo's actual error (e.g. HTTP 429 rate limit, 401 "Invalid Crumb", 404 symbol not found), grouped by cause.
- Downloads use 2 parallel requests with a short pause. If Yahoo starts rate-limiting, the download pauses
  for 60 s (up to twice), retries the affected stocks, and otherwise stops with a clear message instead of
  marking hundreds of stocks as failed. A full Nifty 500 download takes roughly 5–10 minutes.
- Tabs: Dashboard (counts, mix, sector averages, score distribution, data availability per metric),
  Screener (sortable table, CSV export), Top Picks, Deep Dive (price chart, per-metric values and points,
  sources), Excluded (disqualified and unavailable stocks).
- **Screening Logic** page: enable/disable metrics, weights, thresholds and minimum data coverage.
- **History**: every scan is stored in SQLite with its results, exclusions and the settings used.
  Scans from older versions are flagged, since they scored missing data as 0.
- **Accuracy Verification**: compares each tier (and disqualified stocks) against the NIFTY 50.
  Returns run from the last official close available when each stock's data was downloaded to
  the latest close. Both sides are price returns (dividends excluded), so the comparison is like-for-like.

## Project structure

```text
.
|-- app.py                       # Screener page
|-- core/
|   |-- scan_history.py          # SQLite scan history
|   |-- screener.py              # Data download, scoring, hard filters, returns
|   |-- screening_logic.py       # Metric definitions and JSON settings
|   |-- tickers.py               # Nifty 500 list from NSE (with saved fallback)
|   `-- timeutil.py              # IST helpers
|-- pages/                       # Streamlit pages (History, Screening Logic, Accuracy Verification)
|-- screens/
|   |-- components.py            # Shared tables, tabs and charts
|   |-- history_screen.py
|   `-- screening_logic_screen.py
|-- tests/                       # pytest suite
`-- data/                        # Settings, caches and scan history
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Run the tests with `python -m pytest tests`.

## Data sources and limitations

- NSE Indices (`niftyindices.com`) for constituents; Yahoo Finance (via `yfinance`) for fundamentals
  and prices. Yahoo data can be delayed, incomplete or wrong, and Yahoo does not publish PEG for
  many Indian stocks.
- Growth metrics are single-quarter year-over-year figures and can be distorted by one-off items.
- No qualitative factors (management, governance, moat).

## Disclaimer

For education and research only. This is not investment advice. Verify figures with company
filings and consult a SEBI-registered adviser before making investment decisions.
