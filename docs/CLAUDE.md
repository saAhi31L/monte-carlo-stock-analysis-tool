# CLAUDE.md
# Interoperability Playbook: Project Context

## PROJECT OVERVIEW
You are working on the **Interoperability Playbook** — a Monte Carlo Trading Engine built with Python + Mojo.

### Core Value Proposition
- Technical Interoperability: Python fetches data, Mojo runs 100,000 simulations per horizon
- AI Literacy: Using Claude API for code review, optimization, documentation

### Project Structure
```
Project1/
├── SimulationWork/     # The actual tool: Pipeline.py, MarketContext.py, TrackRecord.py, MonteCarloRiskEngine.mojo
├── benchmarks/         # Python-vs-Mojo comparison only (PythonMonteCarlo.py) — not called by the tool
├── docs/               # This file + ChangeLog.md
└── README.md
```
Run from inside `SimulationWork/` — Python, the Mojo engine, and the generated `tradingToolCSV.csv`/`predictionLog.csv` files all stay co-located there. Pixi finds the repo-root `pixi.toml` via its normal upward directory search, so no path config was needed when these files moved out of `Project1/`'s top level.

## CURRENT STATE

### Complete Deliverables
- **MonteCarloRiskEngine_Complete.mojo** (Production-ready)
  - Per-horizon EWMA (each horizon has its own mean from relevant lookback window)
  - MAD filter for dynamic outlier detection
  - 100,000 simulations per horizon
  - Rolling one-day backtest with 90%+ accuracy
  - Adaptive signal logic based on volatility

- **Pipeline.py** (Complete)
  - Fetches 5 years from yfinance
  - Splits into 4-year training + 1-year backtest
  - Displays stock data, P/E ratio, 52-week range, turnover — every fundamental stat now has a plain-language tag next to it (e.g. "33.26x (Over-Saturated)", "97.10% (Strong Growth Expected)"), and the P/E-style ratios display with an "x" suffix instead of an incorrect "$" prefix (P/E, Forward P/E, D/E, P/B aren't dollar amounts)
  - Calls Mojo via subprocess
  - Two separate market-context prompts, split by whether the section depends on the chosen ticker:
    - **Before the ticker is even entered**: "Show current market pulse (regime, sentiment, commodities)?" — these three don't depend on which stock gets picked, so asking first lets the market's mood inform the stock choice, and keeps the per-stock report below uncluttered
    - **After the fundamentals print**: "Show sector fear index for TICKER's sector?" — asked here specifically because it needs the ticker's sector (from `info`) to highlight the right row
  - Investment Horizon Fit always prints (stock-specific, not gated) and now prints **after** the Sector Fear Index table rather than before it, so the table isn't pushed down the page by ancillary text
  - Earnings Watch prints right before the Mojo call — warns if any selected horizon extends past the ticker's next earnings date. Always checked (not gated), but **silent when nothing is affected**
  - Mojo's subprocess call now runs with `capture_output=True` instead of streaming straight to the terminal — Python prints `result.stdout` itself (same visible output, no perceptible delay given Mojo's runtime is well under a second) so it can also parse the report and hand it to `TrackRecord.logPredictions()` for the accuracy log

- **TrackRecord.py** (Complete)
  - Logs every run's Mojo predictions to `predictionLog.csv` (gitignored — per-user runtime state, not source): ticker, horizon, target date, price at prediction time, predicted signal, and Best/Average/Worst
  - `parseMojoReport()` regex-parses Mojo's captured stdout (label/days/EWMA/Best/Average/Worst/Signal per horizon) — no changes to the `.mojo` file itself
  - `resolveDuePredictions()`: for any logged prediction whose target date has arrived, fetches the actual price and tags it correct/incorrect (BUY correct if return > 0, SELL correct if return < 0, HOLD correct if |return| ≤ 2%, mirroring Mojo's own BUY/SELL threshold)
  - Standalone entry point (`python3 TrackRecord.py`) resolves whatever's due and prints an accuracy table by signal type + overall — deliberately decoupled from `Pipeline.py`'s main flow so checking accuracy doesn't add a prompt or fetch cost to every stock lookup

- **MarketContext.py** (Complete)
  - Display-only module — none of this feeds into the Mojo signal engine
  - Investment Horizon Fit: Short-Term vs. Long-Term suitability call for the chosen stock, from its own volatility + existing fundamentals (EPS growth, P/E, D/E) — **always shown**
  - Earnings Watch: compares each selected forecast horizon (converted from trading days to a calendar date via `pandas.bdate_range`) against `Ticker.calendar['Earnings Date']`; flags horizons that extend past it — **always checked, silent if no horizon is affected**
  - Sector Fear Index: annualized realized volatility of 11 sector ETFs (computed proxy, since true per-sector VIX indices don't exist) — highlights the analyzed stock's own sector — **gated behind the "sector fear index" prompt, asked after fundamentals**
  - Market Regime: Bull/Neutral/Bear via S&P 500 price vs. 50-day/200-day SMA — **gated behind the "market pulse" prompt, asked before the ticker**
  - Market Sentiment: 0–100 Fear/Neutral/Greed score from VIX level/trend + S&P momentum (no news/NLP, no API keys) — **gated behind "market pulse"**
  - Commodities Snapshot: price + 1-day % change for Oil, Gold, Silver, Natural Gas, Copper — **gated behind "market pulse"**
  - All 3 network calls are batched (`yf.download()` on ticker lists), and every section fails independently (try/except per section, per-ticker isolation within batches); declining either prompt skips the underlying fetch too, not just the printed output

## NEXT PHASE GOALS
1. Validate end-to-end with NVDA (target: 80%+ backtest accuracy)
2. Build agentic workflow: Code Reviewer + Data Validator + Signal Optimizer + Documentation Generator
3. Integrate Claude API for automated validation and optimization
4. Evaluate whether any `MarketContext.py` signals (regime, sentiment, sector fear index) should eventually feed into the Mojo BUY/SELL/HOLD logic as a weighted composite — deliberately deferred for now to keep the Mojo engine stable while the new features are validated

## KEY CONCEPTS
- Per-horizon EWMA: Each time horizon gets its own mean from relevant lookback window
- MAD Filter: Median ± 3*MAD replaces hard-coded ±5% filter
- Rolling Backtest: Validate day-by-day against actual year 5 prices
- Adaptive Signal: Buy/Sell/Hold based on volatility-scaled thresholds
- Sector Fear Index: proxy fear gauge (annualized realized vol of sector ETFs), not a real published index, since CBOE only publishes a handful of sector/asset volatility indices (VIX, VXN, OVX, GVZ)
- Investment Horizon Fit: heuristic only (volatility bucket + fundamentals red/green flags), not statistically validated like the Monte Carlo backtest