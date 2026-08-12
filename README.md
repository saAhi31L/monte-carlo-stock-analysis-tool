# Project1 — Stock Analysis & Monte Carlo Risk Engine

A CLI tool that analyzes a stock (via yfinance), runs a Monte Carlo price
simulation across multiple time horizons using the interoperability between
Python and Mojo, and prints a BUY/SELL/HOLD signal alongside fundamentals
(each tagged with a plain-language read, e.g. "33.26x (Over-Saturated)"), an
Earnings Watch caveat, and optional broader market context (sentiment,
commodities, market regime, sector fear index). Every run's predictions are
logged locally so their real-world accuracy can be checked later.

## Folder structure

```
Project1/
├── SimulationWork/     # The actual tool — run this
│   ├── Pipeline.py                   # Entry point: fetches data, prints report, calls Mojo
│   ├── MarketContext.py              # Market-wide context: sentiment, commodities, regime, sector fear index, earnings watch
│   ├── TrackRecord.py                # Logs predictions and checks past ones against what actually happened
│   └── MonteCarloRiskEngine.mojo     # Mojo engine: runs 100,000 simulations per horizon
├── benchmarks/          # Python-vs-Mojo performance comparison only — not called by the tool
│   └── PythonMonteCarlo.py
├── docs/
│   ├── CLAUDE.md        # Project context/status for AI-assisted development
│   └── ChangeLog.md     # Detailed log of what changed and why
└── .vscode/
```

## Running it

```bash
cd SimulationWork
python3 Pipeline.py
```

You'll be asked up front whether to show a market pulse (regime, sentiment,
commodities) before even picking a ticker, then prompted for a ticker and one or
more forecast horizons. After the fundamentals print, you're asked whether to show
the sector fear index. The script writes `tradingToolCSV.csv` (a generated hand-off
file, not source — regenerated every run) and invokes `pixi run mojo MonteCarloRiskEngine.mojo`
to run the simulation, then appends this run's predictions to `predictionLog.csv`.

To check how past predictions actually turned out:

```bash
python3 TrackRecord.py
```

This resolves any predictions whose forecast horizon has now elapsed against the
real price, and prints an accuracy breakdown by signal (BUY/SELL/HOLD). Both
`tradingToolCSV.csv` and `predictionLog.csv` are generated, gitignored files — not
source.

## Requirements

- A Python virtualenv with `yfinance`, `tabulate`, `numpy`, `pandas`
- [pixi](https://pixi.sh) with the `mojo` dependency declared in the repo-root `pixi.toml`
