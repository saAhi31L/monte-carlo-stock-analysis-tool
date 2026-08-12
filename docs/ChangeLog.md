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

### Change 12 — Split the Market-Context Prompt in Two, by Ticker Dependency

**What happened:**
The single "show broader market context" prompt (Change 10) bundled four sections together — Market Regime, Market Sentiment, Commodities, and Sector Fear Index — but only the last one actually needs the chosen ticker (to know which sector to highlight). Asking about all four in one place, mid-flow, meant the market's overall mood couldn't inform which stock the user picked in the first place, and the fundamentals report still felt cluttered.

**What the new code does:**
The single prompt is now two, placed where each one's data dependency actually allows:
- **Before the ticker is entered at all**: `Show current market pulse (regime, sentiment, commodities)?` — fires Market Regime, Market Sentiment, and Commodities Snapshot immediately, since none of them need to know the stock.
- **After the fundamentals print**: `Show sector fear index for {userTicker}'s sector?` — fires only the Sector Fear Index table, now that `info.get('sector')` is available to highlight the right row.

Investment Horizon Fit stays always-on (ticker-specific, not part of either prompt), but its print statement moved to **after** the Sector Fear Index block instead of before it — so the fear index table isn't pushed down the page by ancillary text sitting above it.

**Why this matters:**
Market-wide context can now inform stock selection instead of only appearing after a ticker is already locked in, and the per-stock report stays focused: fundamentals, then (optionally) the sector comparison table, then the horizon-fit call.

---

### Change 13 — Added Interpretive Tags to Every Fundamental Stat, Fixed Incorrect "$" Formatting

**What happened:**
Only the trailing P/E Ratio had a plain-language tag next to it ("Fairly Valued" / "Over-Saturated" / "Under-Saturated"). Forward P/E, EPS Growth, D/E Ratio, P/B Ratio, 52-Week High/Low, and Turnover Rate were printed as bare numbers with no indication of whether that number was good, bad, or unremarkable. Several of them also had a stray `$` prefix left over from copy-pasting the P/E Ratio's print statement — a `$` in front of a P/E multiple, a percentage, or a leverage ratio is meaningless (e.g. `EPS Growth: $-26.11%`).

**What the new code does:**
Every stat now gets a tag, using the same three/four-tier banding style as the existing P/E tag:

| Stat | Tag logic |
|---|---|
| Forward P/E | Same bands as trailing P/E: `<15` Under-Saturated, `15–30` Fairly Valued, `>30` Over-Saturated |
| EPS Growth | `>15%` Strong Growth Expected, `0–15%` Modest Growth Expected, `-15–0%` Mild Decline Expected, `<-15%` Sharp Decline Expected |
| D/E Ratio | `<100` Conservative Leverage, `100–200` Moderate Leverage, `>200` High Leverage (raw yfinance scale, where 100 = an actual D/E of 1.0) |
| P/B Ratio | `<1` Below Book Value, `1–3` Fairly Valued, `>3` Premium Valuation |
| 52-Week High | Distance from the latest close to the high: `Near 52-Week High` if within 5%, else `X% Below High` |
| 52-Week Low | Distance from the latest close to the low: `Near 52-Week Low` if within 5%, else `X% Above Low` |
| Turnover Rate | `<0.3%` Low Trading Activity, `0.3–1%` Normal Trading Activity, `>1%` High Trading Activity |

The stray `$` was removed from P/E Ratio, Forward P/E, D/E Ratio, and P/B Ratio (these are multiples/ratios, not dollar amounts) and P/E-style ratios now print with an `x` suffix instead (e.g. `33.26x`). `$` is kept only on 52-Week High/Low, which are genuine prices.

**Why this matters:**
A raw number like `D/E Ratio: 18.86` doesn't tell a reader anything on its own — the tag turns every stat into an at-a-glance read on the stock's state, the same way the P/E tag already did, instead of leaving the user to know the thresholds themselves.

---

### Change 14 — Added Earnings Watch

**What happened:**
The Monte Carlo signal's drift and volatility come entirely from past price behavior. An earnings surprise is exactly the kind of event that can invalidate those assumptions overnight, and the tool gave no indication of whether a selected forecast horizon even overlapped one.

**What the new code does:**
`MarketContext.getEarningsWarning(tickerOfUser, latestDate, horizonsTradingDays)` pulls the next earnings date from `Ticker.calendar['Earnings Date']` (confirmed working with the installed yfinance version — no new dependency needed; `Ticker.get_earnings_dates()` was tried first but requires `lxml`, which isn't installed, so `.calendar` was used instead). Each selected horizon (given in trading days) is converted to an actual calendar date via `pandas.bdate_range(start=latestDate, periods=tradingDays+1)[-1]`, then compared against the earnings date. Horizons that extend past it are collected and reported together, e.g.:
```
  EARNINGS WATCH
  Next Earnings Date: 2026-08-26 (confirmed)
  ⚠ Your "3 Months" horizon(s) extend past this date -- Monte Carlo drift/volatility
    are based on past price behavior and may not hold through an earnings surprise.
```
The `isEarningsDateEstimate` field from `.info` is surfaced as "(confirmed)" or "(estimated)" alongside the date. Printed right before the Mojo subprocess call, immediately ahead of the simulation results it's caveating. If no selected horizon is affected, or the ticker has no upcoming earnings data at all (e.g. some ETFs), the function returns `None` and the section is skipped entirely — no clutter when there's nothing to flag.

**Why this matters:**
Turns a silent blind spot in the model's assumptions into an explicit, only-when-relevant caveat, without touching the Mojo engine itself.

---

### Change 15 — Commodities Snapshot Now Shows Full Contract Names

**What happened:**
The table's "Ticker" column showed raw Yahoo Finance futures symbols like `CL=F`, which mean nothing without already knowing the convention (`CL` = crude oil, `=F` = futures contract).

**What the new code does:**
`commodityTickers` in `MarketContext.py` now maps each commodity to a `{"ticker": ..., "fullName": ...}` dict instead of a bare symbol string (e.g. `"Crude Oil": {"ticker": "CL=F", "fullName": "WTI Crude Oil Futures"}`). `getCommoditiesSnapshot()` returns this `fullName` alongside the existing fields, and the table's second column is renamed "Contract" and now reads `WTI Crude Oil Futures (CL=F)` — the descriptive name up front, with the raw symbol kept in parentheses for anyone who wants to look it up elsewhere. `tabulate` widens the column automatically to fit.

**Why this matters:**
`CL=F` on its own is meaningless to someone who isn't already familiar with Yahoo Finance's futures ticker convention; the full name makes the table self-explanatory.

---

### Change 16 — Fixed a Real Bug: Commodities "1-Day Change" Was Actually a Multi-Session Change

**What happened:**
Compared against Yahoo Finance's own live quote for CL=F (Crude Oil), the table's "1-Day Change" was showing +5.35% when the real 1-day move was +0.29% — nearly 20x off. Traced to `getCommoditiesSnapshot()` fetching 5 days of daily OHLC bars and diffing the last two closes. Commodity futures trade nearly 24/6; when the tool runs mid-session, the most recent daily bar is still live/incomplete (confirmed: its volume was ~4% of a normal day's), so diffing it against an older *settled* close produces an inflated, multi-session delta instead of a true 1-day move.

**What the new code does:**
`getCommoditiesSnapshot()` now reads each ticker's `regularMarketPrice` / `regularMarketChangePercent` directly from `Ticker.info` — the same fields that power Yahoo Finance's own quote page — instead of reconstructing the change from daily bars. Verified against CL=F: the old bar-diffing approach gave +5.2%, the new approach gives the same ~0.2–0.8% range Yahoo's live quote shows. Costs one `.info` lookup per commodity (5 sequential requests, ~2 seconds total) instead of one batched `yf.download()` call — worth it for correctness.

**Why this matters:**
A "1-Day Change" that's actually a 3-4 day change silently misrepresents momentum for exactly the kind of near-continuously-traded instrument (futures) where session boundaries are easy to get wrong.

---

### Change 17 — Added a Local Prediction Track Record

**What happened:**
The tool showed a BUY/SELL/HOLD signal every run but never checked whether past signals actually played out — there was no way to know if the model was any good beyond the existing single-run backtest.

**What the new code does:**
New module `TrackRecord.py`:
- `parseMojoReport(stdoutText)` regex-parses Mojo's captured stdout (label, days, EWMA, Best/Average/Worst, Signal per horizon) — required switching the Mojo `subprocess.run()` call in `Pipeline.py` to `capture_output=True, text=True` instead of letting it stream straight to the terminal; Python now prints `result.stdout` itself, so the visible output is identical, just captured first. `MonteCarloRiskEngine.mojo` itself is untouched.
- `logPredictions()` appends one row per selected horizon to `predictionLog.csv` (ticker, run date, target date, price at prediction, signal, Best/Average/Worst) every time `Pipeline.py` completes a run. Target date is computed the same way as Earnings Watch: `pandas.bdate_range` from the latest price date.
- `resolveDuePredictions()` — for any logged prediction whose target date has arrived, fetches the actual price and tags it correct/incorrect: BUY is correct if the actual return was positive, SELL if negative, HOLD if the actual return stayed within ±2% (the same threshold Mojo itself uses to decide HOLD).
- Running `python3 TrackRecord.py` directly resolves whatever's due and prints an accuracy table by signal type + overall. Deliberately kept separate from `Pipeline.py`'s main flow — logging happens automatically on every run, but checking accuracy is an on-demand step that doesn't add a prompt or fetch cost to a normal stock lookup.

Tested end-to-end: logged real NVDA predictions, then verified resolution against a synthetic already-due row — fetched the actual historical price, computed the correct return, and tagged it correctly.

`predictionLog.csv` is gitignored (per-user runtime state, grows with usage, not source).

**Why this matters:**
Turns the tool's own signal into something it can be held accountable to over time, instead of a number that's shown once and forgotten.

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
| 12 | Python | Split the market-context prompt into "market pulse" (before ticker) and "sector fear index" (after stats); reordered Investment Horizon Fit after the fear index table | Market mood can inform stock choice; per-stock report is less cluttered |
| 13 | Python | Added interpretive tags to every fundamental stat; fixed incorrect `$` formatting on non-dollar ratios | Every number now shows what it means, not just its raw value |
| 14 | Python | Added Earnings Watch (flags forecast horizons crossing the next earnings date) | Surfaces a real blind spot in the Monte Carlo model's assumptions, only when relevant |
| 15 | Python | Commodities Snapshot shows full contract names, not just raw futures symbols | `CL=F` alone meant nothing without knowing Yahoo's ticker convention |
| 16 | Python | Fixed Commodities "1-Day Change" (was diffing a live/incomplete bar against a stale settled close) | Displayed change was off by up to ~20x versus Yahoo's real live quote |
| 17 | Python | Added `TrackRecord.py` — logs every run's predictions, resolves outcomes, reports accuracy | Signals were shown once and forgotten; now there's a real accountability record over time |
