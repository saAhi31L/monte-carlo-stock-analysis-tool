#The Pipeline:
#Functionatlity: Extracting the data of any stock out there listed out on Y-Finance
# to give a proper prediction of it during a certain time period to give the user
# clarity whether this stock is worth buying, hoarding, selling, over-saturated or under-saturated
# in the present time

#-------------------------------------------------------------------------------------------------

import yfinance as yf #the Python library we are going to be extracting our financial data from
import csv #the module that will be used to organize our data in a Comma-Separated File for Mojo to read off of
from tabulate import tabulate
import subprocess
import MarketContext as mc #new market-wide context features: sentiment, commodities, regime, sector fear index
import TrackRecord as tr #logs each run's Mojo predictions locally so accuracy can be checked once horizons elapse

#-------------------------------------------------------------------------------------------------#
# Market Pulse: asked BEFORE the user even picks a stock, since Market Regime, Market Sentiment,
# and Commodities are all market-wide and don't depend on which ticker gets chosen. Showing this
# first lets the market's mood inform which stock the user picks, and keeps it out of the
# per-stock report below.

marketPulseInput = input("Show current market pulse (regime, sentiment, commodities)? (y/n): ").strip().lower()
showMarketPulse = marketPulseInput in ("y", "yes")
print()

if showMarketPulse:
    try:
        gspcClose, vixClose = mc.fetchIndexAndVix()
        marketDataAvailable = True
    except Exception:
        marketDataAvailable = False
        print("\n  Market Regime / Sentiment: Unavailable (index data fetch failed)")

    if marketDataAvailable:
        try:
            regime = mc.getMarketRegime(gspcClose)
            print(f"\n  MARKET REGIME (S&P 500)")
            print(f"  Price:       ${regime['price']:.2f}")
            print(f"  50-Day SMA:  ${regime['sma50']:.2f}")
            print(f"  200-Day SMA: ${regime['sma200']:.2f}")
            print(f"  Regime:      {regime['regime']}")
        except Exception:
            print("\n  Market Regime: Unavailable (insufficient index history)")

        try:
            sentiment = mc.getMarketSentiment(gspcClose, vixClose)
            print(f"\n  MARKET SENTIMENT (VIX & Momentum Proxy)")
            print(f"  VIX Level:        {sentiment['vix']:.2f}  ({sentiment['vixRegime']})")
            print(f"  VIX 5-Day Trend:  {sentiment['vixTrendPct']:+.2f}%")
            print(f"  SPX 5-Day Mom.:   {sentiment['momentumPct']:+.2f}%")
            print(f"  Sentiment Score:  {sentiment['score']}/100  ({sentiment['label']})")
        except Exception:
            print("\n  Market Sentiment: Unavailable (insufficient VIX/index history)")

    try:
        commodities = mc.getCommoditiesSnapshot()
        commodityRows = []
        for c in commodities:
            priceStr = f"${c['price']:.2f}" if c["price"] is not None else "N/A"
            changeStr = f"{c['changePct']:+.2f}%" if c["changePct"] is not None else "N/A"
            commodityRows.append([c["name"], f"{c['fullName']} ({c['ticker']})", priceStr, changeStr])
        commodityTable = tabulate(
            commodityRows,
            headers=["Commodity", "Contract", "Price", "1-Day Change"],
            tablefmt="fancy_grid", numalign="right", stralign="center",
            colalign=("center", "left", "right", "right")
        )
        print(f"\n  COMMODITIES SNAPSHOT")
        print(commodityTable)
    except Exception:
        print("\n  Commodities Snapshot: Unavailable (data fetch failed)")

    print()

#-------------------------------------------------------------------------------------------------#
#Asking for user-input and placing it into the Ticker class:
#Best practice: To place all of the code into a Try-Except block so if the user has spelt the
#ticker wrong or something, then it caution the user

userTicker = None # User's choice of Ticker
data = [] # List structure where we will be containing 5 years worth of data of the User's choice of Ticker
timePeriod = [] # List structure where the Time-Periods will be stored from the menu
tickerOfUser = None # Pre-initialized so it is never unbound if an early exception fires
showSectorFearIndex = False # Pre-initialized so it is never unbound if an early exception fires

try:
    #input
    userTicker = input("What Stock Would You Like to Look Into Today(e.g GOOG, APPL, MSFT):\n").upper().strip()
    print()

    #menu
    print("Time Period Menu: (Time) = # of Trading Days")
    print("If you want all Time Periods --> Type in 'all'")
    print("After you have selected your desired time period --> Type in 'done' in front of the reiterated prompt")
    print("1. Tomorrow = 1 \n2. Next week = 5 \n3. 2 weeks = 14 \n4. 1 Month = 21\n5. 3 Months = 63 \n6. 6 Months = 126\n7. 1 Year = 252")
    timeDictionary = {
    1: 1, 2: 5, 3: 14, 4: 21, 5: 63, 6: 126, 7: 252 }  # Dictionary that contains key-value pairs of the menu
    # Key =(Time) and Value =(# Trading Days)

    #If the user, by mistake, types in a string or includes a string in their input, then
    #Try-Except catches the ValueEror and throws the exception

    print("What Time Period(s) Do You Want to Check--(Select (and only) the Number) ?")
    print("Type 'ALL' to have all time periods and when finished selecting type 'DONE' ")
    while True:
        try:
            period_input = input("Your selection: ").strip()

            print()
            if(period_input == "done"):
                break
            elif(period_input == "all"):
                timePeriod.extend(timeDictionary.values())
                break
            else:
                timePeriod.append(timeDictionary[int(period_input)])

        except Exception:
            print("  Invalid input. Please enter a number from 1-7, 'all', or 'done'.")

    #Adding the User's Desired Stock into the Ticker class that will allocate that specific Ticker
    tickerOfUser = yf.Ticker(userTicker)


    # The data variable stores the 5 years worth of data of that specific company
    data = tickerOfUser.history("5y")

    #If the Company does not contain 5 years worth of data, Has no Data
    #or the Company doesn't even exist --> then it will raise a ValueError exception
    if data.empty:
        raise ValueError("Invalid Ticker or No Data Found")
except Exception:
    print("Invalid Ticker or No Data Found")


#For Back-Testing purposes: Split - first 4 years of training, last 252 days for backtesting
if len(data) < 60:
    print(f"\n  Error: {userTicker} only has {len(data)} trading days of history.")
    print(f"  At least 60 days are required to run simulations. Try a more established stock.\n")
    exit()
elif len(data) < 504:
    print(f"\n  Warning: {userTicker} only has {len(data)} days of history (ideally 2+ years).")
    print(f"  Using 80/20 split instead of fixed 252-day holdout.\n")
    splitIdx = int(len(data) * 0.8)
    trainingData = data.iloc[:splitIdx]
    actualYear5 = data.iloc[splitIdx:]
else:
    trainingData = data.iloc[:-252]
    actualYear5 = data.iloc[-252:]




closeData = trainingData["Close"].squeeze().dropna().tolist()
backTestData = actualYear5["Close"].squeeze().dropna().tolist()


#Now writing our CSV file for Mojo
with open("tradingToolCSV.csv", "w", newline='') as ttCSV: #initializing our CSV file
    writer = csv.writer(ttCSV)

    writer.writerow([userTicker])


    for prices in closeData:
        writer.writerow([prices])

    #Labelling a part of our file called Time Horizons that specifies all of the time the user can choose from
    # such as year, 6M, 3M, Today, Tomorrow, etc
    writer.writerow(["TIME HORIZON"]) # String "TIME HORIZON" is
    for horizon in timePeriod:
        writer.writerow([horizon]) # placing all of that data(dictionary Name(time) = Value(trading days))
        # underneath the label 'TIME HORIZON'

    #For back-testing purposes(validating your data is accurate or not)
    # Writing another section called ACTUAL PRICES that stores the actual prices of year 5
    writer.writerow(["ACTUAL PRICES OF YEAR 5"])
    for actualPrices in backTestData:
        writer.writerow([actualPrices])



date = data.reset_index()
date = date["Date"].dt.strftime('%m-%d-%Y').iloc[-1]
latestData = data.iloc[-1]
someData = [[
    date,
    f"${latestData['Open']:.2f}",
    f"${latestData['High']:.2f}",
    f"${latestData['Low']:.2f}",
    f"${latestData['Close']:.2f}",
    f"{int(latestData['Volume']):,}"
]]

table = tabulate(
    someData,
    headers=[f"Date", "Open", "High", "Low", "Close", "Volume"],
    tablefmt="fancy_grid",
    numalign="right",
    stralign="center",
    colalign=("center", "center", "center", "center", "center", "right")
)
print(table)

# Fetch additional stats
info = tickerOfUser.info

# Price-to-EarninTgs Ratio: the ratio of a stock's price to its earnings per share
# Used to measure the stock's valuation level
peRatio = info.get('trailingPE', 'N/A')


fiftyTwoWeekHigh = info.get('fiftyTwoWeekHigh', 'N/A')
fiftyTwoWeekLow = info.get('fiftyTwoWeekLow', 'N/A')
sharesOutstanding = info.get('sharesOutstanding', None)

#-------------------------------------------------------------------------------------------------#
# Forward P/E Ratio: uses next year's EXPECTED earnings instead of the past year's actual earnings
# Investors watch this closely because the market prices in future performance, not just history
# A Forward P/E lower than the Trailing P/E suggests analysts expect earnings to grow next year
forwardPERatio = info.get('forwardPE', 'N/A')

if isinstance(forwardPERatio, float):
    forwardPEStr = f"{forwardPERatio:.2f}"
else:
    forwardPEStr = 'N/A'

#-------------------------------------------------------------------------------------------------#
# EPS Growth (Earnings Per Share Growth): measures how much earnings per share are expected to change
# Calculated as: ((Forward EPS - Trailing EPS) / |Trailing EPS|) * 100
# A positive % means analysts expect the company to become MORE profitable
# A negative % means profitability is expected to SHRINK
# This is important because earnings growth is one of the strongest long-term drivers of stock price
trailingEPS = info.get('trailingEps', None)
forwardEPS = info.get('forwardEps', None)

if trailingEPS is not None and forwardEPS is not None and trailingEPS != 0:
    epsGrowthValue = (forwardEPS - trailingEPS) / abs(trailingEPS) * 100
    epsGrowthStr = f"{epsGrowthValue:.2f}%"
else:
    epsGrowthValue = None
    epsGrowthStr = 'N/A'

#-------------------------------------------------------------------------------------------------#
# Debt-to-Equity Ratio (D/E): measures how much debt the company carries relative to shareholder equity
# A high D/E (e.g. above 2.0) signals heavier reliance on borrowed money, which increases financial risk
# A low D/E suggests the company funds itself more conservatively through equity
# yfinance returns this as a raw number (e.g. 45.67 means a D/E ratio of 0.4567 or ~45.67% leverage)
debtToEquityRatio = info.get('debtToEquity', 'N/A')

if isinstance(debtToEquityRatio, float):
    debtToEquityStr = f"{debtToEquityRatio:.2f}"
else:
    debtToEquityStr = 'N/A'

#-------------------------------------------------------------------------------------------------#
# Price-to-Book Ratio (P/B): compares the stock's market price to the company's net asset value (book value)
# A P/B below 1.0 can indicate the stock may be undervalued relative to its assets
# A very high P/B means investors are paying a large premium above what the company owns on paper
# More meaningful for asset-heavy businesses (banks, manufacturers) than for software/tech companies
priceToBookRatio = info.get('priceToBook', 'N/A')

if isinstance(priceToBookRatio, float):
    priceToBookStr = f"{priceToBookRatio:.2f}"
else:
    priceToBookStr = 'N/A'

#-------------------------------------------------------------------------------------------------#
# Turnover Rate = Volume / Shares Outstanding
if sharesOutstanding and sharesOutstanding > 0:
    turnoverRate = (int(latestData['Volume']) / sharesOutstanding) * 100
    turnoverStr = f"{turnoverRate:.2f}%"
else:
    turnoverRate = None
    turnoverStr = 'N/A'

# Format P/E
peStr = f"{peRatio:.2f}" if isinstance(peRatio, float) else "N/A"

# Valuation signal based on P/E
if isinstance(peRatio, float):
    if peRatio < 15:
        valuation = "Under-Saturated"
    elif peRatio > 30:
        valuation = "Over-Saturated"
    else:
        valuation = "Fairly Valued"
else:
    valuation = "N/A"

#-------------------------------------------------------------------------------------------------#
# Tags for every remaining stat, so each number's meaning is legible at a glance (same idea as the
# P/E valuation tag above): Forward P/E reuses the same valuation bands as trailing P/E; EPS Growth,
# D/E, and P/B get their own bands; the 52-week High/Low tags show how close the latest close is to
# each bound; Turnover Rate is tagged by how actively the stock is trading.

# Forward P/E valuation tag (same bands as trailing P/E)
if isinstance(forwardPERatio, float):
    if forwardPERatio < 15:
        forwardValuation = "Under-Saturated"
    elif forwardPERatio > 30:
        forwardValuation = "Over-Saturated"
    else:
        forwardValuation = "Fairly Valued"
else:
    forwardValuation = "N/A"

# EPS Growth tag
if epsGrowthValue is not None:
    if epsGrowthValue > 15:
        epsGrowthTag = "Strong Growth Expected"
    elif epsGrowthValue > 0:
        epsGrowthTag = "Modest Growth Expected"
    elif epsGrowthValue > -15:
        epsGrowthTag = "Mild Decline Expected"
    else:
        epsGrowthTag = "Sharp Decline Expected"
else:
    epsGrowthTag = "N/A"

# D/E Ratio tag (raw yfinance number -- 100 on this scale is an actual D/E ratio of 1.0)
if isinstance(debtToEquityRatio, float):
    if debtToEquityRatio < 100:
        deTag = "Conservative Leverage"
    elif debtToEquityRatio <= 200:
        deTag = "Moderate Leverage"
    else:
        deTag = "High Leverage"
else:
    deTag = "N/A"

# P/B Ratio tag
if isinstance(priceToBookRatio, float):
    if priceToBookRatio < 1:
        pbTag = "Below Book Value"
    elif priceToBookRatio <= 3:
        pbTag = "Fairly Valued"
    else:
        pbTag = "Premium Valuation"
else:
    pbTag = "N/A"

# 52-Week High/Low tags -- how far the latest close sits from each bound
currentClose = float(latestData['Close'])

if isinstance(fiftyTwoWeekHigh, float):
    fiftyTwoWeekHighDisp = f"${fiftyTwoWeekHigh:.2f}"
    distFromHigh = (fiftyTwoWeekHigh - currentClose) / fiftyTwoWeekHigh * 100
    highTag = "Near 52-Week High" if distFromHigh <= 5 else f"{distFromHigh:.1f}% Below High"
else:
    fiftyTwoWeekHighDisp = "N/A"
    highTag = "N/A"

if isinstance(fiftyTwoWeekLow, float):
    fiftyTwoWeekLowDisp = f"${fiftyTwoWeekLow:.2f}"
    distFromLow = (currentClose - fiftyTwoWeekLow) / fiftyTwoWeekLow * 100
    lowTag = "Near 52-Week Low" if distFromLow <= 5 else f"{distFromLow:.1f}% Above Low"
else:
    fiftyTwoWeekLowDisp = "N/A"
    lowTag = "N/A"

# Turnover Rate tag
if turnoverRate is not None:
    if turnoverRate < 0.3:
        turnoverTag = "Low Trading Activity"
    elif turnoverRate <= 1:
        turnoverTag = "Normal Trading Activity"
    else:
        turnoverTag = "High Trading Activity"
else:
    turnoverTag = "N/A"

# Display strings for the P/E-style ratios -- "x" suffix (e.g. "17.85x") since these are multiples,
# not dollar amounts; only 52-Week High/Low are actual prices and keep the "$" prefix
peDisp = f"{peStr}x" if peStr != "N/A" else "N/A"
forwardPEDisp = f"{forwardPEStr}x" if forwardPEStr != "N/A" else "N/A"
pbDisp = f"{priceToBookStr}x" if priceToBookStr != "N/A" else "N/A"

print(f"\n  P/E Ratio:       {peDisp}  ({valuation})")
print(f"  Forward P/E:     {forwardPEDisp}  ({forwardValuation})")
print(f"  EPS Growth:      {epsGrowthStr}  ({epsGrowthTag})")
print(f"  D/E Ratio:       {debtToEquityStr}  ({deTag})")
print(f"  P/B Ratio:       {pbDisp}  ({pbTag})")
print(f"  52-Week High:    {fiftyTwoWeekHighDisp}  ({highTag})")
print(f"  52-Week Low:     {fiftyTwoWeekLowDisp}  ({lowTag})")
print(f"  Turnover Rate:   {turnoverStr}  ({turnoverTag})")

#-------------------------------------------------------------------------------------------------#
# Sector Fear Index: asked here, AFTER the stats above, since it needs the ticker's sector (just
# fetched into `info`) to know which row to highlight. Kept as its own late prompt rather than
# bundled with the Market Pulse question at the top, which fires before the ticker is even known.
sectorInput = input(f"\nShow sector fear index for {userTicker}'s sector? (y/n): ").strip().lower()
showSectorFearIndex = sectorInput in ("y", "yes")
print()

if showSectorFearIndex:
    try:
        userSector = info.get('sector', None)
        sectorData = mc.getSectorFearIndex(userSector)
        sectorRows = []
        for s in sectorData:
            marker = " <-- Your Sector" if s["isUserSector"] else ""
            volStr = f"{s['fearIndexPct']:.2f}%" if s["fearIndexPct"] is not None else "N/A"
            sectorRows.append([s["sector"] + marker, s["etf"], volStr])
        sectorTable = tabulate(
            sectorRows,
            headers=["Sector", "ETF", "Fear Index (Ann. Realized Vol)"],
            tablefmt="fancy_grid", numalign="right", stralign="center",
            colalign=("left", "center", "right")
        )
        print(f"  SECTOR FEAR INDEX")
        print(sectorTable)
        if userSector is None:
            print("  Note: Sector not classified for this ticker -- no row highlighted above.")
    except Exception:
        print("  Sector Fear Index: Unavailable (data fetch failed)")

#-------------------------------------------------------------------------------------------------#
# Investment Horizon Fit (ticker-specific -- reuses closeData, epsGrowthValue, peRatio, debtToEquityRatio)
# Printed after the Sector Fear Index table (rather than before it) so the table itself isn't
# pushed down by this ancillary text.
try:
    fit = mc.getInvestmentHorizonFit(closeData, epsGrowthValue, peRatio, debtToEquityRatio)
    print(f"\n  INVESTMENT HORIZON FIT")
    print(f"  Annualized Volatility: {fit['annualizedVolPct']:.2f}%")
    print(f"  Suitability:           {fit['label']}")
    print(f"  Why:                   {fit['justification']}")
except Exception:
    print("\n  Investment Horizon Fit: Unavailable (insufficient price history)")

#-------------------------------------------------------------------------------------------------#
# Earnings Watch: warns if any selected forecast horizon extends past the next earnings date,
# since the Monte Carlo drift/volatility below are based on past price behavior and may not hold
# through an earnings surprise. Stays silent if there's nothing to flag.
horizonLabels = {1: "Tomorrow", 5: "Next Week", 14: "2 Weeks", 21: "1 Month",
                  63: "3 Months", 126: "6 Months", 252: "1 Year"}
try:
    earningsWarning = mc.getEarningsWarning(tickerOfUser, data.index[-1], timePeriod)
    if earningsWarning is not None:
        affectedLabels = ", ".join(horizonLabels.get(h, f"{h}d") for h in earningsWarning["affectedHorizons"])
        estimateNote = "estimated" if earningsWarning["isEstimate"] else "confirmed"
        print(f"\n  EARNINGS WATCH")
        print(f"  Next Earnings Date: {earningsWarning['earningsDate']} ({estimateNote})")
        print(f"  ⚠ Your \"{affectedLabels}\" horizon(s) extend past this date -- Monte Carlo drift/volatility")
        print(f"    are based on past price behavior and may not hold through an earnings surprise.")
except Exception:
    pass


result = subprocess.run(["pixi", "run", "mojo", "MonteCarloRiskEngine.mojo"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"\n  Error: Mojo simulation failed (exit code {result.returncode}). Check the output above for details.")
    if result.stderr:
        print(result.stderr)
else:
    #Log this run's predictions to the local track record so accuracy can be checked later
    #(via TrackRecord.py) once each horizon's target date has actually arrived.
    try:
        mojoResults = tr.parseMojoReport(result.stdout)
        tr.logPredictions(userTicker, data.index[-1], currentClose, mojoResults)
    except Exception:
        pass
