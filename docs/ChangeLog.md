# Changelog & Explanation of All Changes Made

---

## File 1: `MonteCarloRiskEngine.mojo`

### Change 1 — Fixed a Corrupted/Mixed File State
**What happened:**
The file had gotten into a broken state — a mix of old and new code that wouldn't compile. Specific problems were:
- Line 16 had a syntax error: `List[Float64]ex` (typo)
- `var mean: Float64` was missing from the struct definition
- The old single `calculateEWMA()` function was mixed in alongside the newer `calculatePerHorizonEWMA()` logic
- `runSimulations()` had `for _ in range(len(self.meanHorizon[e])):` where `e` wasn't defined yet

**Fix:** Rewrote the file cleanly from scratch using the correct, complete version as the base.

---

### Change 2 — Per-Horizon EWMA (`calculatePerHorizonEWMA`)
**What the old code did:**
There was a single `calculateEWMA()` that computed one global EWMA drift using a fixed alpha of 0.30, applied to the entire price history. Every time horizon (Tomorrow, 1 Month, 1 Year) used the exact same drift number.

**What the new code does:**
```
fn calculatePerHorizonEWMA(mut self):
    for each horizon (e.g. 1 day, 5 days, 21 days...):
        lookback = horizon * 2  (minimum 10, capped at available data)
        alpha = 2.0 / (lookback + 1)
        compute EWMA over just that lookback window
        store result in meanHorizon[e]
```

**Why this matters:**
- A 1-day prediction should react to very recent price movements (short lookback, higher alpha)
- A 1-year prediction should smooth over a much longer window (long lookback, lower alpha)
- Each horizon now gets its own drift that is appropriate to its time scale
- This is how professional quant models handle multi-horizon forecasting

---

### Change 3 — Fixed the Starting Price for Simulations
**What the old code did:**
```
var currentPrice = priceListPtr[priceListLen - 1]
```
This used the **last price from training data** (Year 4 cutoff, ~June 2025) as the starting point for all simulations. Since the current date is June 2026, that price was about $130–140 for NVDA — way off from the actual $210.

**What the new code does:**
```
var backTestLen = len(self.backTestPrice)
var latestPrice: Float64
if backTestLen > 0:
    latestPrice = self.backTestPrice[backTestLen - 1]  # most recent actual close
else:
    latestPrice = priceListPtr[priceListLen - 1]       # fallback
```
Now simulations start from **the last price in the backtest data**, which is the most recent real closing price (e.g. $210.69 for NVDA on June 18, 2026).

**Same fix was applied in `printReport()`** so the signal comparison also uses the correct current price.

**Why this matters:**
The Monte Carlo engine projects prices *forward from today*. If you start from a price 12 months in the past, every prediction will be anchored to that old price — completely useless for making decisions today.

---

### Change 4 — Changed the Signal Logic to a 2% Threshold
**What the old code did:**
```
var scaledVolatility = self.stdvClose * sqrt(Float64(days))
if meanClose > currentPrice * (1.0 + scaledVolatility):  signal = "BUY"
elif meanClose < currentPrice * (1.0 - scaledVolatility): signal = "SELL"
```
This required the projected average to beat the current price by **one full standard deviation** before firing a BUY. For a volatile stock like NVDA (~2% daily stdv), the average would need to hit $214+ just for a 1-day BUY — nearly impossible.

**What the new code does:**
```
var expectedReturnPct = (meanClose - currentPrice) / currentPrice * 100.0
if expectedReturnPct > 2.0:   signal = "BUY"
elif expectedReturnPct < -2.0: signal = "SELL"
```

**Why this matters:**
- A $1 gain on a $210 stock is only 0.47% — not worth acting on
- The signal should be based on **percentage return**, not an arbitrary volatility band
- 2% is a meaningful minimum: if the simulation expects at least 2% upside, that's a genuine edge worth acting on
- This lets high-momentum stocks like MU (EWMA drift of 0.0138) correctly fire BUY on the 5-day horizon while NVDA and GOOGL stay at HOLD when the edge is small

---

### Change 5 — Fixed the Unused Variable Warning in `runBackTest()`
**What the old code did:**
```
var startPrice = Float64(0.0)   # <- compiler warned: this value is never read
...
for i in range(...):
    if i == 0:
        startPrice = self.priceList[...]   # always reassigned before use
    else:
        startPrice = self.backTestPrice[...]
```
The initial value `0.0` was dead code — the loop always overwrote it before reading it, so the Mojo compiler flagged it.

**What the new code does:**
```
for i in range(...):
    var startPrice: Float64        # declared without initial value
    if i == 0:
        startPrice = self.priceList[...]
    else:
        startPrice = self.backTestPrice[...]
```
Moving the declaration *inside* the loop means it is always assigned before being read, and the dead initial `0.0` is gone. Zero warnings.

---

## File 2: `Pipeline.py`

### Change 6 — Added Data Sufficiency Guard
**What the old code did:**
Always split the data as `data.iloc[:-252]` for training and `data.iloc[-252:]` for backtesting, regardless of how much history was available. If a stock had fewer than 252 days of data (newly listed), training data would be empty and Mojo would crash with a stack trace.

**What the new code does:**
```python
if len(data) < 60:
    # Hard stop — not enough data for any meaningful calculation
    print(f"Error: {userTicker} only has {len(data)} trading days of history.")
    print("At least 60 days required. Try a more established stock.")
    exit()

elif len(data) < 504:
    # Between 60 and ~2 years — use an 80/20 split as a fallback
    splitIdx = int(len(data) * 0.8)
    trainingData = data.iloc[:splitIdx]
    actualYear5  = data.iloc[splitIdx:]

else:
    # Normal case — full 4-year training + 1-year backtest
    trainingData = data.iloc[:-252]
    actualYear5  = data.iloc[-252:]
```

**Why the three tiers:**
| Data Available | Behaviour | Reason |
|---|---|---|
| < 60 days | Exit with error | Too little for EWMA, stdv, MAD filter to work |
| 60–504 days | 80/20 split | Still runs, but warns user accuracy may be lower |
| 504+ days | Standard 4yr/1yr split | Full accuracy, ideal case |

**Why this matters:**
Without this guard, running a recently IPO'd stock (like SPCX with only 5 days of data) caused a hard Mojo crash with a cryptic stack trace. Now the user gets a clear, friendly error message instead.

---

### Change 7 — Added Four New Investor Metrics to Display Output
**What the old code did:**
After the summary table, only three additional metrics were shown: Trailing P/E Ratio, 52-Week High/Low, and Turnover Rate. This gave a limited snapshot — valuation, price range, and trading activity — but left out growth expectations, leverage, and asset-based valuation.

**What the new code does:**
Four new metrics are now fetched from `tickerOfUser.info` and printed alongside the existing ones:

| Metric | yfinance key | What it measures |
|---|---|---|
| Forward P/E | `forwardPE` | Valuation based on next year's *expected* earnings, not past earnings |
| EPS Growth | `trailingEps` + `forwardEps` | `(forwardEps - trailingEps) / abs(trailingEps) * 100` — expected change in earnings per share |
| D/E Ratio | `debtToEquity` | Debt carried relative to shareholder equity; higher = more financial risk |
| P/B Ratio | `priceToBook` | Market price vs accounting net asset value; below 1.0 can signal undervaluation |

Each metric block in the code has a separator line and a multi-line comment explaining what it measures, why investors use it, and any quirks in how yfinance returns the data.

**Why this matters:**
These four metrics were identified through a Yahoo Finance AI consultation as the highest-value additions to complement what was already displayed. Together they cover:
- **Growth expectations** (Forward P/E, EPS Growth) — is the company expected to earn more next year?
- **Financial risk** (D/E Ratio) — how leveraged is the balance sheet?
- **Asset-based valuation** (P/B Ratio) — is the stock cheap relative to what the company actually owns?

---

## File 3: `MarketContext.py` (new file)

### Change 8 — Added Market-Wide Context Features

**What prompted this:**
The tool only ever analyzed a stock in isolation — no sense of whether the broader market was risk-on or risk-off, what commodities were doing, or how the stock's own sector's volatility compared to others. The goal was to turn this from a pure Python/Mojo interoperability demo into a genuinely useful real-world research tool, without touching the Mojo signal engine itself.

**What the new code does:**
A new module, `MarketContext.py`, adds five display-only features, all computed from data already reachable via `yfinance` (no news APIs, no external keys):

| Feature | Function | How it's computed |
|---|---|---|
| Market Regime (Bull/Neutral/Bear) | `getMarketRegime()` | S&P 500 price vs. its 50-day and 200-day SMA (golden-cross/death-cross alignment) |
| Market Sentiment | `getMarketSentiment()` | 0–100 Fear/Neutral/Greed score from VIX level (60% weight), 5-day S&P momentum (40% weight), and VIX trend as a ±10pt nudge — no news/NLP |
| Commodities Snapshot | `getCommoditiesSnapshot()` | Price + 1-day % change for Crude Oil, Gold, Silver, Natural Gas, Copper futures |
| Sector Fear Index | `getSectorFearIndex()` | Annualized realized volatility (`stdev(diff(log(close))) * sqrt(252) * 100`) of 11 major sector ETFs over a 21-day lookback — a computed proxy, since true VIX-style indices don't exist for most GICS sectors |
| Investment Horizon Fit | `getInvestmentHorizonFit()` | Combines the chosen stock's own annualized volatility (computed from `closeData`, already fetched) with its existing EPS growth/P-E/D-E fundamentals into a heuristic: Better Suited for Short-Term / Long-Term / Both / Caution |

All five are fetched with **3 batched `yf.download()` calls total** (not one call per ticker) to keep the added network latency low. Every section in `Pipeline.py` is wrapped in its own `try/except`, so one bad fetch (e.g. `^VIX` unavailable) prints an "Unavailable" message for just that section instead of crashing the whole report. Batches (Commodities, Sector Fear Index) also isolate failures per-ticker, so one bad symbol shows `N/A` in that row only.

**Where it plugs in:**
`Pipeline.py` gained one new import (`import MarketContext as mc`) and five new print blocks inserted after the existing fundamentals output and before the `subprocess.run(["pixi","run","mojo",...])` call. The Mojo engine and `tradingToolCSV.csv` schema are completely untouched — this is purely additive, display-only context around the existing report.

**One small existing-code fix required:** `epsGrowthValue` was previously only assigned inside the branch where both trailing and forward EPS were available; the `else` branch left it unassigned entirely. Since Investment Horizon Fit needs this value, the `else` branch now also sets `epsGrowthValue = None`, matching the file's existing pattern of pre-initializing variables.

**Why this matters:**
A BUY/SELL/HOLD signal for one stock means more when you know whether the whole market is bullish or bearish, whether fear is elevated, what commodities are doing, and whether the stock's own sector is unusually volatile right now — and whether the stock itself is a better fit for a quick trade or a long hold.

---

### Change 9 — Renamed the New Module and Its Identifiers to camelCase

**What happened:**
`market_context.py` was originally written with Python's conventional `snake_case` (function names like `get_market_regime`, variables like `vix_trend_pct`, dict keys like `fear_index_pct`). This didn't match the naming style used everywhere else in the project (`userTicker`, `closeData`, `epsGrowthValue`, `Pipeline.py`, `MonteCarloRiskEngine.mojo`).

**What changed:**
- File renamed: `market_context.py` → `MarketContext.py` (matches the existing PascalCase file-naming pattern)
- Every function renamed to camelCase: `fetch_index_and_vix` → `fetchIndexAndVix`, `get_market_regime` → `getMarketRegime`, `get_market_sentiment` → `getMarketSentiment`, `get_commodities_snapshot` → `getCommoditiesSnapshot`, `get_sector_fear_index` → `getSectorFearIndex`, `get_investment_horizon_fit` → `getInvestmentHorizonFit`
- Every internal variable and returned dict key renamed to camelCase (e.g. `vix_trend_pct` → `vixTrendPct`, `fear_index_pct` → `fearIndexPct`, `is_user_sector` → `isUserSector`, `annualized_vol_pct` → `annualizedVolPct`)
- The two module-level lookup dicts renamed: `COMMODITIES` → `commodityTickers`, `SECTOR_ETFS` → `sectorEtfs`
- All call sites in `Pipeline.py` updated to match (import statement, function calls, dict-key lookups)

**Note:** `group_by` and `auto_adjust` inside the `yf.download(...)` calls are left as-is — those are fixed keyword-argument names from the yfinance library's own API, not our identifiers, so they can't be renamed without breaking the call.

**Why this matters:**
Consistent naming across the codebase — no file should read like it was written by two different people.

---

### Change 10 — Made Market-Wide Context Sections Opt-In

**What happened:**
Someone just looking up a single stock doesn't necessarily want Commodities and Sector Fear Index (and the other market-wide sections) cluttering the report every time — that information is about the broader market, not the stock itself.

**What the new code does:**
Right after the time-period menu, the script now asks one question:
```
Show broader market context (regime, sentiment, commodities, sector fear index)? (y/n):
```
The answer is stored in `showMarketContext` (pre-initialized to `False` at the top of the file, matching the existing pattern for `tickerOfUser`). The four market-wide sections — Sector Fear Index, Market Regime, Market Sentiment, and Commodities Snapshot — are now wrapped in a single `if showMarketContext:` block. **Investment Horizon Fit stays always-on**, since it's a call about the specific stock being analyzed, not general market context.

Answering "n" also skips the underlying `yf.download()` calls entirely (they sit inside the same `if` block), so declining saves the extra network round-trips, not just the printed output.

**Why this matters:**
Keeps the core, per-stock report (OHLCV, fundamentals, Investment Horizon Fit, Mojo Monte Carlo signal) fast and uncluttered for users who just want a quick read on one stock, while still making the market-wide context available on request.

---

### Change 11 — Reorganized the Project Folder Structure

**What happened:**
Every file previously sat flat at the top of `Project1/` — the real product, the Python-vs-Mojo benchmark script, and the context docs were all mixed together with no visual signal for which was which.

**What changed:**
- `SimulationWork/` — the actual product: `Pipeline.py`, `MarketContext.py`, `MonteCarloRiskEngine.mojo`
- `benchmarks/` — `PythonMonteCarlo.py`, which exists purely to demonstrate Python-vs-Mojo performance and is never invoked by the real pipeline
- `docs/` — `CLAUDE.md`, `ChangeLog.md`
- `Project1Description.txt` (empty) replaced with a real `README.md` describing what the tool does, the folder layout, and how to run it
- Added a `.gitignore` for `SimulationWork/tradingToolCSV.csv` (a generated hand-off file rewritten every run, not source) and `__pycache__/`

**Why this didn't require code changes:**
`Pipeline.py` writes `tradingToolCSV.csv` and calls `subprocess.run(["pixi","run","mojo","MonteCarloRiskEngine.mojo"])` using paths relative to the current working directory. Since the Python script, the Mojo engine, and the generated CSV all moved into `SimulationWork/` together, running from inside that folder keeps every relative path valid. Pixi itself finds the repo-root `pixi.toml` via its own upward directory search, regardless of which subfolder it's invoked from. Verified end-to-end against NVDA after the move — Mojo ran, read the CSV, and printed results exactly as before.

**Why this matters:**
Anyone opening the repo can now tell at a glance what's the product versus what's a performance demo, without reading every file.

---

## Summary Table

| # | File | Change | Problem Solved |
|---|------|--------|----------------|
| 1 | Mojo | Rewrote corrupted file | Syntax errors, missing struct fields, mixed old/new code |
| 2 | Mojo | Per-horizon EWMA | Each time horizon gets its own drift, not a one-size-fits-all number |
| 3 | Mojo | Fixed simulation starting price | Predictions were anchoring to a year-old price instead of today's |
| 4 | Mojo | 2% return threshold for signals | Signals were nearly impossible to trigger; now based on meaningful % gain |
| 5 | Mojo | Moved `startPrice` inside loop | Eliminated compiler warning about unused initial value |
| 6 | Python | Data sufficiency guard | Prevented hard Mojo crash on stocks with insufficient history |
| 7 | Python | Four new investor metrics | Display now includes Forward P/E, EPS Growth, D/E Ratio, and P/B Ratio |
| 8 | Python | Added `MarketContext.py` (Market Regime, Sentiment, Commodities, Sector Fear Index, Investment Horizon Fit) | Report now includes broader market context, not just a single stock in isolation |
| 9 | Python | Renamed `MarketContext.py` identifiers to camelCase | Matches the naming convention used everywhere else in the project |
| 10 | Python | Gated 4 of 5 `MarketContext.py` sections behind a y/n prompt | Users analyzing a single stock aren't forced to see market-wide context they didn't ask for |
| 11 | Structure | Reorganized into `SimulationWork/`, `benchmarks/`, `docs/` + added `README.md`/`.gitignore` | Repo now visually separates the real product from the benchmark demo and context docs |
