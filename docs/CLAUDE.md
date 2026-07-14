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
├── SimulationWork/     # The actual tool: Pipeline.py, MarketContext.py, MonteCarloRiskEngine.mojo
├── benchmarks/         # Python-vs-Mojo comparison only (PythonMonteCarlo.py) — not called by the tool
├── docs/               # This file + ChangeLog.md
└── README.md
```
Run from inside `SimulationWork/` — Python, the Mojo engine, and the generated `tradingToolCSV.csv` hand-off file all stay co-located there. Pixi finds the repo-root `pixi.toml` via its normal upward directory search, so no path config was needed when these files moved out of `Project1/`'s top level.

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
  - Displays stock data, P/E ratio, 52-week range, turnover
  - Calls Mojo via subprocess
  - After the time-period menu, asks one y/n prompt: "Show broader market context (regime, sentiment, commodities, sector fear index)?" — gates four of the five `MarketContext.py` sections; Investment Horizon Fit always prints since it's stock-specific, not market-wide

- **MarketContext.py** (Complete)
  - Display-only module — none of this feeds into the Mojo signal engine
  - Investment Horizon Fit: Short-Term vs. Long-Term suitability call for the chosen stock, from its own volatility + existing fundamentals (EPS growth, P/E, D/E) — **always shown**, not gated by the market-context prompt
  - Sector Fear Index: annualized realized volatility of 11 sector ETFs (computed proxy, since true per-sector VIX indices don't exist) — highlights the analyzed stock's own sector — **gated behind the market-context prompt**
  - Market Regime: Bull/Neutral/Bear via S&P 500 price vs. 50-day/200-day SMA — **gated**
  - Market Sentiment: 0–100 Fear/Neutral/Greed score from VIX level/trend + S&P momentum (no news/NLP, no API keys) — **gated**
  - Commodities Snapshot: price + 1-day % change for Oil, Gold, Silver, Natural Gas, Copper — **gated**
  - All 3 network calls are batched (`yf.download()` on ticker lists), and every section fails independently (try/except per section, per-ticker isolation within batches); the batched calls are skipped entirely when the user answers "n", so declining also saves the extra network round-trips

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