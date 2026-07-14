# Project1 — Stock Analysis & Monte Carlo Risk Engine

A CLI tool that analyzes a stock (via yfinance), runs a Mojo-powered Monte Carlo
price simulation across multiple time horizons, and prints a BUY/SELL/HOLD signal
alongside fundamentals and optional broader market context (sentiment, commodities,
market regime, sector fear index).

## Folder structure

```
Project1/
├── SimulationWork/     # The actual tool — run this
│   ├── Pipeline.py                   # Entry point: fetches data, prints report, calls Mojo
│   ├── MarketContext.py              # Market-wide context: sentiment, commodities, regime, sector fear index
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

You'll be prompted for a ticker, one or more forecast horizons, and whether to show
broader market context. The script writes `tradingToolCSV.csv` (a generated hand-off
file, not source — regenerated every run) and invokes `pixi run mojo MonteCarloRiskEngine.mojo`
to run the simulation.

## Requirements

- A Python virtualenv with `yfinance`, `tabulate`, `numpy`, `pandas`
- [pixi](https://pixi.sh) with the `mojo` dependency declared in the repo-root `pixi.toml`
