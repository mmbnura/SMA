# 📈 NSE Value Finder

A multi-factor fundamental screener for **Nifty 500 stocks**, built with Python and Streamlit. It fetches live data from Yahoo Finance, scores each stock out of 100 using a value-investing model, and presents the results across an interactive dashboard.

---

## Features

- **Live Nifty 500 constituent list** fetched directly from NSE India (auto-cached for 24 hours)
- **7-factor scoring model** inspired by Benjamin Graham / Warren Buffett value investing principles
- **4-tab UI**: Dashboard · Screener · Top Picks · Deep Dive
- **Sector filter** to scan a subset of stocks (useful for faster scans)
- **Downloadable CSV** of screener results
- **Deep Dive view** with 1-year price chart (20/50-day MAs), radar chart, metrics table, and 52-week gauge

---

## Screenshots

| Dashboard | Screener | Deep Dive |
|-----------|----------|-----------|
| Recommendation pie, sector bars, score histogram | Sortable table with score progress bars | Price chart, radar, fundamentals table |

---

## Scoring Model

Each stock is scored out of **100 points** across 7 fundamental metrics:

| Metric | Max Points | What it rewards |
|--------|-----------|-----------------|
| P/E Ratio | 20 | Low price relative to earnings |
| ROE | 20 | High return on equity (management efficiency) |
| Debt / Equity | 15 | Low financial leverage (safety) |
| P/B Ratio | 15 | Low price relative to book value |
| EPS Growth | 15 | Strong earnings growth YoY |
| Revenue Growth | 10 | Strong sales growth YoY |
| Dividend Yield | 5 | Income generation |

**Recommendation thresholds:**

| Score | Signal |
|-------|--------|
| ≥ 75 | 🟢 Strong Buy |
| ≥ 60 | 🟡 Buy |
| ≥ 45 | 🟠 Hold |
| < 45 | 🔴 Avoid |

> **Note:** Banks, NBFCs, and insurance companies receive a neutral score on Debt/Equity since high leverage is structurally normal for financial sector businesses.

---

## Project Structure

```
nse-value-finder/
├── app.py            # Streamlit UI — all 4 tabs, sidebar, charts
├── screener.py       # Scoring engine — yfinance fetch + metric scoring
├── tickers.py        # Nifty 500 list — live fetch from NSE + local cache
├── requirements.txt  # Python dependencies
└── README.md
```

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-username/nse-value-finder.git
cd nse-value-finder
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

---

## Usage

1. **Select sectors** in the sidebar (or keep "Select All Sectors" checked)
2. Click **🔍 Run Scan** — the app fetches fundamentals for each stock one by one
3. Browse results across the four tabs:
   - **📊 Dashboard** — Overview charts and score distribution
   - **📋 Screener** — Full filterable table; download as CSV
   - **🏆 Top Picks** — Visual score bars for the top 20 value stocks
   - **🔍 Deep Dive** — Select any stock for a detailed breakdown

### Tips

- Scanning all 500 stocks takes **10–15 minutes** due to Yahoo Finance rate limits
- For a quick test, scan just **2–3 sectors** (e.g. Banking + IT) — takes ~2 minutes
- The **🔄 button** in the sidebar forces a fresh Nifty 500 list from NSE (useful after quarterly index rebalancing)
- Results are your **research shortlist**, not buy orders — always do your own due diligence

---

## Deployment on Streamlit Community Cloud

1. Push all files to a **public GitHub repository**
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo
3. Set the main file to `app.py`
4. No secrets or API keys are required — all data sources are public

---

## Data Sources

| Source | What is fetched |
|--------|----------------|
| [NSE India](https://www.niftyindices.com) | Official Nifty 500 constituent list (symbols, company names, sectors) |
| [Yahoo Finance](https://finance.yahoo.com) via `yfinance` | Price, P/E, P/B, ROE, D/E, EPS growth, revenue growth, dividend yield, 52-week high/low |

---

## Dependencies

```
streamlit >= 1.32.0
yfinance  >= 0.2.40
pandas    >= 2.0.0
plotly    >= 5.18.0
numpy     >= 1.24.0
requests  >= 2.31.0
```

---

## Limitations

- **Backward-looking data** — all metrics are trailing (historical), not forward estimates
- **No qualitative factors** — management quality, competitive moat, governance are not captured
- **Yahoo Finance data gaps** — some smaller Nifty 500 stocks may have missing or stale fundamentals
- **Not a buy signal** — a high score means a stock is worth researching, not that it should be purchased blindly

---

## Disclaimer

> This application is for **educational and research purposes only**. It does not constitute investment advice and is not registered with SEBI. Past fundamentals do not guarantee future returns. Always consult a SEBI-registered financial advisor before making any investment decision. The developer accepts no liability for financial decisions made based on this tool.

---

## License

MIT License — free to use, modify, and distribute.
