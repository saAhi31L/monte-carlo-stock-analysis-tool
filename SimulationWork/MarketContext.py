#Market Context Module:
#Functionality: Provides broader market-wide context (sentiment, commodities, market regime,
#sector fear index) and a stock-specific short-term vs. long-term suitability call, all
#computed from yfinance data. Display-only -- none of this feeds into the Mojo signal engine.

#-------------------------------------------------------------------------------------------------

import yfinance as yf
import numpy as np
import pandas as pd

#-------------------------------------------------------------------------------------------------#
# Shared batched fetch for the S&P 500 and VIX, used by both Market Regime and Market Sentiment
# so we only hit the network once for both features.

def fetchIndexAndVix(period="1y"):
    raw = yf.download(["^GSPC", "^VIX"], period=period, progress=False,
                       group_by="ticker", auto_adjust=False)
    gspcClose = raw["^GSPC"]["Close"].dropna()
    vixClose = raw["^VIX"]["Close"].dropna()
    return gspcClose, vixClose

#-------------------------------------------------------------------------------------------------#
# Bull/Neutral/Bear Market Regime: classic golden-cross/death-cross SMA alignment on the S&P 500

def getMarketRegime(gspcClose):
    if len(gspcClose) < 200:
        raise ValueError(f"Insufficient S&P 500 history for 200-SMA ({len(gspcClose)} days)")

    price = float(gspcClose.iloc[-1])
    sma50 = float(gspcClose.rolling(50).mean().iloc[-1])
    sma200 = float(gspcClose.rolling(200).mean().iloc[-1])

    if price > sma50 > sma200:
        regime = "Bull"
    elif price < sma50 < sma200:
        regime = "Bear"
    else:
        regime = "Neutral"

    return {"price": price, "sma50": sma50, "sma200": sma200, "regime": regime}

#-------------------------------------------------------------------------------------------------#
# Market Sentiment: a Fear/Neutral/Greed style 0-100 score built only from VIX level/trend and
# S&P momentum -- no news/NLP, no external API keys required

def getMarketSentiment(gspcClose, vixClose, vixTrendWindow=5, momentumWindow=5):
    if len(vixClose) <= vixTrendWindow or len(gspcClose) <= momentumWindow:
        raise ValueError("Insufficient history for sentiment calculation")

    currentVix = float(vixClose.iloc[-1])
    vixTrendPct = float((vixClose.iloc[-1] - vixClose.iloc[-1 - vixTrendWindow])
                        / vixClose.iloc[-1 - vixTrendWindow] * 100)
    momentumPct = float((gspcClose.iloc[-1] - gspcClose.iloc[-1 - momentumWindow])
                       / gspcClose.iloc[-1 - momentumWindow] * 100)

    # VIX-level component: 12 (calm) -> 100 pts, 40 (panic) -> 0 pts
    vixLevelScore = max(0.0, min(100.0, 100 * (40 - currentVix) / (40 - 12)))
    # Momentum component: centered at 50, +/- 5 pts per 1% index move
    momentumScore = max(0.0, min(100.0, 50 + momentumPct * 5))

    rawScore = 0.6 * vixLevelScore + 0.4 * momentumScore
    # Rising VIX (positive trend) nudges the score down (more fear); falling VIX nudges it up
    trendAdjustment = -max(-10.0, min(10.0, vixTrendPct))
    finalScore = int(round(max(0, min(100, rawScore + trendAdjustment))))

    if finalScore >= 60:
        label = "Greed"
    elif finalScore <= 40:
        label = "Fear"
    else:
        label = "Neutral"

    if currentVix < 20:
        vixRegime = "Complacent (Low Vol)"
    elif currentVix <= 30:
        vixRegime = "Neutral"
    else:
        vixRegime = "Elevated Fear (High Vol)"

    return {"vix": currentVix, "vixTrendPct": vixTrendPct, "momentumPct": momentumPct,
            "score": finalScore, "label": label, "vixRegime": vixRegime}

#-------------------------------------------------------------------------------------------------#
# Commodities Snapshot: price + 1-day % change for a handful of major commodity futures.
# Uses each ticker's own regularMarketPrice/regularMarketChangePercent (the same fields behind
# Yahoo Finance's own quote page) rather than diffing two daily OHLC bars via yf.download: futures
# trade nearly 24/6, so the most recent daily bar is often still live/incomplete mid-session, and
# diffing it against an older settled close produces a change % that doesn't match the real
# previous-close reference (confirmed against CL=F: bar-diffing gave +5.2%, the live quote fields
# gave +0.23%, matching Yahoo's own displayed change).

commodityTickers = {
    "Crude Oil": {"ticker": "CL=F", "fullName": "WTI Crude Oil Futures"},
    "Gold": {"ticker": "GC=F", "fullName": "Gold Futures"},
    "Silver": {"ticker": "SI=F", "fullName": "Silver Futures"},
    "Natural Gas": {"ticker": "NG=F", "fullName": "Henry Hub Natural Gas Futures"},
    "Copper": {"ticker": "HG=F", "fullName": "COMEX Copper Futures"},
}

def getCommoditiesSnapshot(tickers=commodityTickers):
    results = []
    for name, meta in tickers.items():
        tkr = meta["ticker"]
        try:
            quoteInfo = yf.Ticker(tkr).info
            price = quoteInfo.get('regularMarketPrice')
            changePct = quoteInfo.get('regularMarketChangePercent')
            if price is None or changePct is None:
                raise ValueError("missing regular market quote fields")
            results.append({"name": name, "ticker": tkr, "fullName": meta["fullName"],
                             "price": float(price), "changePct": float(changePct)})
        except Exception:
            results.append({"name": name, "ticker": tkr, "fullName": meta["fullName"],
                             "price": None, "changePct": None})
    return results

#-------------------------------------------------------------------------------------------------#
# Sector Fear Index: annualized realized volatility of major sector ETFs, used as a proxy for a
# per-sector "fear index" since true VIX-style indices don't exist for most GICS sectors

sectorEtfs = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

def getSectorFearIndex(userSector, lookbackDays=21, etfs=sectorEtfs):
    raw = yf.download(list(etfs.values()), period=f"{lookbackDays + 15}d", progress=False,
                       group_by="ticker", auto_adjust=False)
    results = []
    for sector, etf in etfs.items():
        try:
            closes = raw[etf]["Close"].dropna().tail(lookbackDays + 1)
            if len(closes) < lookbackDays + 1:
                raise ValueError("insufficient data")
            logReturns = np.diff(np.log(closes.values))
            realizedVolPct = float(np.std(logReturns, ddof=1) * np.sqrt(252) * 100)
            results.append({"sector": sector, "etf": etf, "fearIndexPct": realizedVolPct,
                             "isUserSector": (sector == userSector)})
        except Exception:
            results.append({"sector": sector, "etf": etf, "fearIndexPct": None,
                             "isUserSector": (sector == userSector)})
    results.sort(key=lambda r: (r["fearIndexPct"] is None, -(r["fearIndexPct"] or 0)))
    return results

#-------------------------------------------------------------------------------------------------#
# Investment Horizon Fit: is this stock better suited for short-term trading or long-term holding?
# Ticker-specific -- reuses data already fetched/computed elsewhere in the pipeline, no new source.

def getInvestmentHorizonFit(closeData, epsGrowthPct, peRatio, deRatio):
    prices = np.array(closeData, dtype=float)
    if len(prices) < 21:
        raise ValueError("Insufficient price history for volatility calculation")

    logReturns = np.diff(np.log(prices))
    annualizedVolPct = float(np.std(logReturns, ddof=1) * np.sqrt(252) * 100)

    weakFundamentals = (
        (epsGrowthPct is not None and epsGrowthPct < 0)
        or (isinstance(deRatio, float) and deRatio > 200)   # yfinance reports D/E *100
        or (isinstance(peRatio, float) and peRatio < 0)      # negative earnings
    )
    strongFundamentals = (
        not weakFundamentals
        and epsGrowthPct is not None and epsGrowthPct > 10
        and (not isinstance(deRatio, float) or deRatio < 100)
    )

    if annualizedVolPct >= 40:
        volBucket = "high"
    elif annualizedVolPct <= 20:
        volBucket = "low"
    else:
        volBucket = "moderate"

    if weakFundamentals:
        label = "Caution -- High Risk, Weak Fundamentals"
        justification = "Negative EPS growth, heavy leverage, or negative earnings outweigh any volatility profile."
    elif volBucket == "high":
        label = "Better Suited for Short-Term"
        justification = f"Annualized volatility of {annualizedVolPct:.1f}% implies large short-term swings -- more suited to active trading than a buy-and-hold."
    elif volBucket == "low" and strongFundamentals:
        label = "Better Suited for Long-Term"
        justification = f"Low volatility ({annualizedVolPct:.1f}%) combined with solid EPS growth and manageable leverage favors patient holding."
    else:
        label = "Suitable for Both"
        justification = f"Moderate volatility ({annualizedVolPct:.1f}%) with no major fundamental red flags supports either horizon."

    return {"annualizedVolPct": annualizedVolPct, "label": label, "justification": justification}

#-------------------------------------------------------------------------------------------------#
# Earnings Watch: flags forecast horizons that extend past the stock's next earnings date. The
# Monte Carlo engine's drift/volatility come from past price behavior, which is exactly what an
# earnings surprise can invalidate -- this is a caveat, not a signal, so it stays silent when
# no selected horizon is actually affected.

def getEarningsWarning(tickerOfUser, latestDate, horizonsTradingDays):
    calendar = tickerOfUser.calendar
    earningsDates = calendar.get('Earnings Date') if calendar else None
    if not earningsDates:
        return None

    nextEarnings = min(earningsDates)
    if nextEarnings <= latestDate.date():
        return None

    affectedHorizons = []
    for tradingDays in horizonsTradingDays:
        targetDate = pd.bdate_range(start=latestDate, periods=tradingDays + 1)[-1].date()
        if nextEarnings <= targetDate:
            affectedHorizons.append(tradingDays)

    if not affectedHorizons:
        return None

    isEstimate = tickerOfUser.info.get('isEarningsDateEstimate', None)
    return {
        "earningsDate": nextEarnings,
        "isEstimate": bool(isEstimate),
        "affectedHorizons": sorted(set(affectedHorizons)),
    }
