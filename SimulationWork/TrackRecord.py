#Track Record Module:
#Functionality: Logs each run's Mojo BUY/SELL/HOLD predictions to a local CSV, then -- once a
#prediction's horizon has actually elapsed -- checks the real price against what was predicted
#and tags it correct/incorrect. Run this file directly (`python3 TrackRecord.py`) to resolve
#whatever's due and print an accuracy summary.

#-------------------------------------------------------------------------------------------------

import csv
import os
import re
from datetime import date

import pandas as pd
import yfinance as yf
from tabulate import tabulate

LOG_COLUMNS = ["runDate", "ticker", "horizonLabel", "horizonDays", "targetDate",
               "priceAtPrediction", "signal", "bestCase", "avgCase", "worstCase",
               "resolved", "actualPrice", "actualReturnPct", "wasCorrect"]

DEFAULT_LOG_PATH = "predictionLog.csv"

#-------------------------------------------------------------------------------------------------#
# Parses Mojo's printed report (captured from subprocess stdout) into structured per-horizon
# results, so predictions can be logged without touching MonteCarloRiskEngine.mojo itself.

MOJO_BLOCK_RE = re.compile(
    r"(?P<label>[A-Za-z0-9 ]+?)\s*\((?P<days>\d+) Trading Days\)\s*\n"
    r"\s*[─\-]+\s*\n"
    r"\s*EWMA Drift:\s*(?P<ewma>-?[\d.eE+-]+)\s*\n"
    r"\s*Best Case:\s*\$\s*(?P<best>-?[\d.]+)\s*\n"
    r"\s*Average:\s*\$\s*(?P<avg>-?[\d.]+)\s*\n"
    r"\s*Worst Case:\s*\$\s*(?P<worst>-?[\d.]+)\s*\n"
    r"\s*Signal:\s*(?P<signal>BUY|SELL|HOLD)"
)

def parseMojoReport(stdoutText):
    results = []
    for m in MOJO_BLOCK_RE.finditer(stdoutText):
        results.append({
            "label": m.group("label").strip(),
            "days": int(m.group("days")),
            "best": float(m.group("best")),
            "avg": float(m.group("avg")),
            "worst": float(m.group("worst")),
            "signal": m.group("signal"),
        })
    return results

#-------------------------------------------------------------------------------------------------#
# Appends this run's predictions to the log. One row per selected horizon.

def logPredictions(ticker, latestDate, priceAtPrediction, mojoResults, logPath=DEFAULT_LOG_PATH):
    if not mojoResults:
        return

    fileExists = os.path.isfile(logPath)
    runDate = date.today().isoformat()

    with open(logPath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if not fileExists:
            writer.writeheader()
        for r in mojoResults:
            targetDate = pd.bdate_range(start=latestDate, periods=r["days"] + 1)[-1].date()
            writer.writerow({
                "runDate": runDate,
                "ticker": ticker,
                "horizonLabel": r["label"],
                "horizonDays": r["days"],
                "targetDate": targetDate.isoformat(),
                "priceAtPrediction": f"{priceAtPrediction:.2f}",
                "signal": r["signal"],
                "bestCase": r["best"],
                "avgCase": r["avg"],
                "worstCase": r["worst"],
                "resolved": "False",
                "actualPrice": "",
                "actualReturnPct": "",
                "wasCorrect": "",
            })

#-------------------------------------------------------------------------------------------------#
# For every logged prediction whose target date has arrived, fetches the actual price and tags
# whether the signal was correct:
#   BUY  -> correct if the actual return was positive
#   SELL -> correct if the actual return was negative
#   HOLD -> correct if the actual return stayed within +/-2% (the same threshold Mojo uses to
#           decide HOLD in the first place, so "correct" means the predicted lack of a meaningful
#           edge actually held)

def resolveDuePredictions(logPath=DEFAULT_LOG_PATH):
    if not os.path.isfile(logPath):
        return

    with open(logPath, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    today = date.today()
    changed = False

    for row in rows:
        if row["resolved"] == "True":
            continue

        targetDate = date.fromisoformat(row["targetDate"])
        if targetDate > today:
            continue

        try:
            windowEnd = (pd.Timestamp(targetDate) + pd.Timedelta(days=5)).date()
            hist = yf.Ticker(row["ticker"]).history(start=targetDate.isoformat(), end=windowEnd.isoformat())
            if hist.empty:
                continue

            actualPrice = float(hist["Close"].iloc[0])
            priceAtPrediction = float(row["priceAtPrediction"])
            actualReturnPct = (actualPrice - priceAtPrediction) / priceAtPrediction * 100

            signal = row["signal"]
            if signal == "BUY":
                wasCorrect = actualReturnPct > 0
            elif signal == "SELL":
                wasCorrect = actualReturnPct < 0
            else:
                wasCorrect = abs(actualReturnPct) <= 2.0

            row["resolved"] = "True"
            row["actualPrice"] = f"{actualPrice:.2f}"
            row["actualReturnPct"] = f"{actualReturnPct:.2f}"
            row["wasCorrect"] = str(wasCorrect)
            changed = True
        except Exception:
            continue

    if changed:
        with open(logPath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

#-------------------------------------------------------------------------------------------------#
# Accuracy broken down by signal type, plus an overall row. Only counts resolved predictions.

def getAccuracySummary(logPath=DEFAULT_LOG_PATH):
    if not os.path.isfile(logPath):
        return None

    with open(logPath, "r", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["resolved"] == "True"]

    if not rows:
        return None

    summary = {}
    for signalType in ["BUY", "SELL", "HOLD"]:
        subset = [r for r in rows if r["signal"] == signalType]
        correct = sum(1 for r in subset if r["wasCorrect"] == "True")
        summary[signalType] = {"total": len(subset), "correct": correct}

    summary["OVERALL"] = {"total": len(rows), "correct": sum(1 for r in rows if r["wasCorrect"] == "True")}
    return summary

#-------------------------------------------------------------------------------------------------#
# Standalone entry point: resolve whatever's due, then print the accuracy table.

if __name__ == "__main__":
    resolveDuePredictions()
    summary = getAccuracySummary()

    if summary is None:
        print("\n  No resolved predictions yet -- run Pipeline.py a few times, then check back once a horizon has passed.\n")
    else:
        rows = []
        for signalType in ["BUY", "SELL", "HOLD", "OVERALL"]:
            s = summary[signalType]
            accStr = f"{(s['correct'] / s['total'] * 100):.1f}%" if s["total"] > 0 else "N/A"
            rows.append([signalType, s["total"], s["correct"], accStr])

        table = tabulate(
            rows,
            headers=["Signal", "Total", "Correct", "Accuracy"],
            tablefmt="fancy_grid", numalign="right", stralign="center", colalign=("center", "right", "right", "right")
        )
        print("\n  PREDICTION TRACK RECORD\n")
        print(table)
