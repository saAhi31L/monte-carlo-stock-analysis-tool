from std.math import sqrt, exp, trunc
from std.random import randn_float64
from std.time import perf_counter_ns

struct MonteCarloEngine:
    var meanHorizon: List[Float64]
    var mean: Float64
    var stdvClose: Float64
    var priceList: List[Float64]
    var results: List[List[Float64]]
    var dailyReturns: List[Float64]
    var horizon: List[Int]
    var backTestPrice: List[Float64]


    #-------------------------------------------------------------------------------------------------#
    # Initializes all fields of the MonteCarloEngine struct to their default empty or zero state.
    # This runs automatically when a new engine instance is created in main().
    # Every List starts empty and every Float64 starts at 0.0 -- they are populated
    # by the load and calculation methods that follow in sequence.
    fn __init__(out self) raises:
        self.meanHorizon = List[Float64]()
        self.mean = 0.0
        self.stdvClose = 0.0
        self.priceList = List[Float64]()
        self.results = List[List[Float64]]()
        self.dailyReturns = List[Float64]()
        self.horizon = List[Int]()
        self.backTestPrice = List[Float64]()

    #-------------------------------------------------------------------------------------------------#
    # Reads tradingToolCSV.csv and populates three separate data collections:
    #   - priceList      : the 4-year training close prices used for drift and stdv calculations
    #   - horizon        : the user-selected time horizons in trading days to simulate
    #   - backTestPrice  : the Year 5 actual close prices used to validate backtest accuracy
    # The CSV has three sections separated by label rows ("TIME HORIZON" and "ACTUAL PRICES OF YEAR 5").
    # Any row that cannot be parsed as a number (including the ticker symbol on row 1) is silently skipped.
    fn loadData(mut self) raises:
        var numbers = open("tradingToolCSV.csv", "r").read()
        var readingString = False
        var data = numbers.split("\n")
        var readingActualData = False
        for i in data:
            var line = i.strip()
            if len(line) > 0:
                if line == "TIME HORIZON":
                    readingString = True
                elif line == "ACTUAL PRICES OF YEAR 5":
                    readingActualData = True
                    readingString = False
                elif readingActualData:
                    try:
                        self.backTestPrice.append(atof(line))
                    except:
                        pass
                elif readingString:
                    self.horizon.append(atol(line))
                else:
                    try:
                        self.priceList.append(atof(line))
                    except:
                        pass

    #-------------------------------------------------------------------------------------------------#
    # Computes the day-over-day percentage return for every consecutive pair of training prices,
    # then filters out statistical outliers using the MAD (Median Absolute Deviation) method.
    #
    # Step 1 -- Compute raw daily returns: (price[i] - price[i-1]) / price[i-1]
    # Step 2 -- Sort the returns using insertion sort
    # Step 3 -- Find the median of the sorted returns
    # Step 4 -- Compute the absolute deviation of each return from the median
    # Step 5 -- Sort those deviations and find their median (this is the MAD value)
    # Step 6 -- Keep only returns that fall within Median +/- 3 * MAD
    #
    # Why MAD instead of a fixed +/-5% filter:
    # MAD automatically scales to each stock's actual volatility. A hard 5% cutoff
    # would incorrectly discard normal moves on high-volatility stocks and keep
    # suspicious outliers on low-volatility ones. MAD adapts to the data itself.
    fn calculateDailyReturns(mut self):
        var drList = List[Float64]()
        for i in range(1, len(self.priceList)):
            var dailyReturn = (self.priceList[i] - self.priceList[i-1]) / self.priceList[i-1]
            drList.append(dailyReturn)

        for i in range(1, len(drList)):
            var key = drList[i]
            var j = i - 1
            while j >= 0 and drList[j] > key:
                drList[j+1] = drList[j]
                j -= 1
            drList[j+1] = key

        var length = len(drList)
        var median = Float64(0.0)
        if length % 2 == 0:
            median = (drList[length // 2 - 1] + drList[length // 2]) / 2.0
        elif(length % 2 == 1):
            median = drList[length // 2]

        var madList = List[Float64]()
        for i in drList:
            var partOfMad = i - median
            if partOfMad < 0.0:
                partOfMad = partOfMad * -1.0
            madList.append(partOfMad)

        for i in range(1, len(madList)):
            var mlKey = madList[i]
            var mlElement = i - 1
            while mlElement >= 0 and madList[mlElement] > mlKey:
                madList[mlElement+1] = madList[mlElement]
                mlElement -= 1
            madList[mlElement + 1] = mlKey

        var madListLength = len(madList)
        var madListMedian = Float64(0.0)

        if(madListLength % 2 == 0):
            madListMedian = (madList[madListLength // 2 - 1] + madList[madListLength // 2]) / 2.0
        elif(madListLength % 2 == 1):
            madListMedian = (madList[madListLength // 2])

        var lowerBound = median - 3.0 * madListMedian
        var upperBound = median + 3.0 * madListMedian

        for i in drList:
            if i > lowerBound and i < upperBound:
                self.dailyReturns.append(i)

    #-------------------------------------------------------------------------------------------------#
    # Computes the arithmetic mean (average) of the filtered daily returns
    # stored in self.dailyReturns after the MAD filter has been applied.
    # This mean is used as a baseline and for standard deviation calculation.
    # Per-horizon drift is handled separately by calculatePerHorizonEWMA.
    fn calculateMean(mut self):
        var sizeDaily = len(self.dailyReturns)
        if sizeDaily == 0:
            return
        var total = Float64(0.0)
        for i in range(sizeDaily):
            total += self.dailyReturns[i]
        self.mean = total / Float64(sizeDaily)

    #-------------------------------------------------------------------------------------------------#
    # Computes the standard deviation of the filtered daily returns.
    # Standard deviation measures how much individual daily returns tend to deviate from the mean.
    # It is used in every simulation step as the volatility component:
    #   dailyReturn = drift + stdv * randomShock
    # A higher stdv means simulated price paths spread further apart,
    # producing a wider gap between the Best Case and Worst Case outputs.
    fn calculateStdv(mut self):
        var sizeDailySTDV = len(self.dailyReturns)
        if sizeDailySTDV == 0:
            return
        var variance = Float64(0.0)
        for i in range(sizeDailySTDV):
            variance += (self.dailyReturns[i] - self.mean) * (self.dailyReturns[i] - self.mean)
        self.stdvClose = sqrt(variance / Float64(sizeDailySTDV))

    #-------------------------------------------------------------------------------------------------#
    # Computes a separate Exponentially Weighted Moving Average (EWMA) drift
    # for each time horizon the user selected, and stores each result in self.meanHorizon.
    #
    # Why per-horizon instead of one global drift:
    # A 1-day prediction should react quickly to very recent price movements
    # (short lookback, higher alpha). A 1-year prediction should smooth over a much
    # longer window (long lookback, lower alpha). One single drift for all horizons
    # would over-weight recent noise in long-term forecasts and under-weight it in short-term ones.
    #
    # Lookback window = horizon * 2, minimum 10 days, capped at available data length.
    # Alpha = 2 / (lookback + 1) -- the standard EWMA smoothing factor formula.
    # EWMA is computed over only the lookback window, not the full price history.
    fn calculatePerHorizonEWMA(mut self):
        var priceLen = len(self.priceList)
        if priceLen < 2:
            for _ in range(len(self.horizon)):
                self.meanHorizon.append(0.0)
            return
        for e in range(len(self.horizon)):
            var days = self.horizon[e]

            # Lookback window: 2x the horizon, minimum 10 days, capped at available data
            var lookback = days * 2
            if lookback < 10:
                lookback = 10
            if lookback >= priceLen:
                lookback = priceLen - 1

            var alpha = 2.0 / Float64(lookback + 1)

            var startIdx = priceLen - lookback
            var ewma = (self.priceList[startIdx] - self.priceList[startIdx - 1]) / self.priceList[startIdx - 1]

            for i in range(startIdx + 1, priceLen):
                var ret = (self.priceList[i] - self.priceList[i - 1]) / self.priceList[i - 1]
                ewma = alpha * ret + (1.0 - alpha) * ewma

            self.meanHorizon.append(ewma)

    #-------------------------------------------------------------------------------------------------#
    # Runs 100,000 Monte Carlo simulation paths for each user-selected time horizon
    # and stores every simulated ending price in self.results.
    #
    # Each simulation path works as follows:
    #   - Start from the most recent actual closing price (last price in the Year 5 backtest data)
    #   - For each trading day in the horizon, draw a random shock from a standard normal
    #     distribution clamped to [-3, +3] to prevent extreme unrealistic tail events
    #   - Apply: currentPrice = currentPrice * exp(drift + stdv * randomShock)
    #   - Record the final price after all days in the horizon have been stepped through
    #
    # Starting from the most recent actual price (not the training cutoff price) ensures
    # that all predictions are anchored to today's real market price, not a price from
    # potentially a full year ago.
    fn runSimulations(mut self):
        var priceListLen = len(self.priceList)
        var priceListPtr = self.priceList.unsafe_ptr()

        # Start simulations from the most recent actual price (end of Year 5),
        # not the training data cutoff (end of Year 4)
        var backTestLen = len(self.backTestPrice)
        var latestPrice: Float64
        if backTestLen > 0:
            latestPrice = self.backTestPrice[backTestLen - 1]
        else:
            latestPrice = priceListPtr[priceListLen - 1]

        for _ in range(len(self.horizon)):
            self.results.append(List[Float64]())

        for e in range(len(self.horizon)):
            var days = self.horizon[e]
            var horizonMean = self.meanHorizon[e]
            for _ in range(100000):
                var currentPrice = latestPrice
                for _ in range(days):
                    var randomValue = randn_float64()
                    if randomValue > 3.0:
                        randomValue = 3.0
                    elif randomValue < -3.0:
                        randomValue = -3.0
                    var dailyReturn = horizonMean + self.stdvClose * randomValue
                    currentPrice = currentPrice * exp(dailyReturn)
                self.results[e].append(currentPrice)

    #-------------------------------------------------------------------------------------------------#
    # Validates the engine's 1-day prediction accuracy against the actual Year 5 closing prices.
    # Rolls through every day in the backtest period and checks whether the predicted price
    # landed within 10% of what actually happened. Returns the percentage of days within that range.
    #
    # How it works:
    #   - Computes a fresh 1-day EWMA drift using a fixed 10-day lookback window
    #     (independent of whatever horizons the user selected, so accuracy is always measured)
    #   - Calls simulateAverage() once to produce a price multiplier: E[P1] / P0
    #   - For each day in Year 5: multiplies the previous day's actual close by that multiplier
    #     and checks if the result is within 10% of the real closing price
    #   - Returns (correct predictions / total days) * 100
    #
    # Using a single multiplier instead of running 100,000 simulation paths per backtest day
    # makes the backtest complete in milliseconds rather than minutes.
    fn runBackTest(mut self) -> Float64:
        var correct = Float64(0.0)
        var total = Float64(len(self.backTestPrice))

        if total == 0.0:
            return 0.0

        # Always compute a fresh 1-day EWMA for backtest regardless of selected horizons,
        # so accuracy is never wrong when the user picks only multi-day horizons.
        var priceLen = len(self.priceList)
        var backtestMean = Float64(0.0)
        if priceLen >= 2:
            var lookback = 10
            if lookback >= priceLen:
                lookback = priceLen - 1
            var alpha = 2.0 / Float64(lookback + 1)
            var startIdx = priceLen - lookback
            backtestMean = (self.priceList[startIdx] - self.priceList[startIdx - 1]) / self.priceList[startIdx - 1]
            for i in range(startIdx + 1, priceLen):
                var ret = (self.priceList[i] - self.priceList[i - 1]) / self.priceList[i - 1]
                backtestMean = alpha * ret + (1.0 - alpha) * backtestMean

        # Compute the 1-day expected return multiplier once — the distribution is stationary
        # (same drift + stdv every day), so E[P1 | P0] = P0 * multiplier.
        # This replaces 252 × 100,000 redundant simulation paths with a single 100,000-path run.
        var multiplier = self.simulateAverage(1, 1.0, backtestMean)

        for i in range(len(self.backTestPrice)):
            var startPrice: Float64
            if i == 0:
                startPrice = self.priceList[len(self.priceList) - 1]
            else:
                startPrice = self.backTestPrice[i - 1]
            var projected = startPrice * multiplier
            var actualPrice = self.backTestPrice[i]
            var diff = projected - actualPrice
            if diff < 0.0:
                diff = diff * -1.0
            var errorPct = diff / actualPrice
            if errorPct < 0.10:
                correct += 1.0

        return (correct / total) * 100.0

    #-------------------------------------------------------------------------------------------------#
    # Runs 100,000 simulation paths for a given number of days and returns
    # the mean (average) ending price across all paths as a single Float64.
    #
    # Parameters:
    #   days       : number of trading days to simulate forward
    #   startPrice : the starting price all 100,000 paths begin from
    #   meanDrift  : the EWMA drift to apply at each daily step
    #
    # Used by runBackTest() to produce a single average multiplier (E[P1] / P0) efficiently,
    # avoiding the need to run a full set of simulation paths for every backtest day.
    fn simulateAverage(mut self, days: Int, startPrice: Float64, meanDrift: Float64) -> Float64:
        var simAverageList = List[Float64]()

        for _ in range(100000):
            var currentPrice = startPrice
            for _ in range(days):
                var randomValue = randn_float64()
                if randomValue > 3.0:
                    randomValue = 3.0
                elif randomValue < -3.0:
                    randomValue = -3.0
                var dailyReturn = meanDrift + self.stdvClose * randomValue
                currentPrice = currentPrice * exp(dailyReturn)
            simAverageList.append(currentPrice)

        var total = Float64(0.0)
        for i in range(len(simAverageList)):
            total += simAverageList[i]
        return total / Float64(len(simAverageList))

    #-------------------------------------------------------------------------------------------------#
    # Formats and prints the full simulation report for every selected time horizon,
    # followed by rolling backtest accuracy and total elapsed simulation time.
    #
    # For each horizon it prints:
    #   - EWMA Drift   : the per-horizon drift value computed by calculatePerHorizonEWMA
    #   - Best Case    : the highest simulated ending price across all 100,000 paths
    #   - Average      : the mean ending price across all 100,000 paths
    #   - Worst Case   : the lowest simulated ending price across all 100,000 paths
    #   - Signal       : BUY if average return > +2%, SELL if < -2%, else HOLD
    #
    # Signal logic is percentage-based so it scales correctly across all price levels.
    # A $1 gain on a $200 stock is only 0.5% -- not actionable. The 2% threshold
    # filters out noise and only fires when the simulation projects a meaningful edge.
    fn printReport(mut self, elapsed: Float64):
        # Use most recent actual price as the reference for signals
        var backTestLen = len(self.backTestPrice)
        var currentPrice: Float64
        if backTestLen > 0:
            currentPrice = self.backTestPrice[backTestLen - 1]
        else:
            currentPrice = self.priceList[len(self.priceList) - 1]

        for e in range(len(self.horizon)):
            var days = self.horizon[e]

            var label = String("")
            if days == 1: label = "Tomorrow"
            elif days == 5: label = "Next Week"
            elif days == 14: label = "2 Weeks"
            elif days == 21: label = "1 Month"
            elif days == 63: label = "3 Months"
            elif days == 126: label = "6 Months"
            elif days == 252: label = "1 Year"

            var minPrice = self.results[e][0]
            var maxPrice = self.results[e][0]
            var totalClose = Float64(0.0)

            for i in range(len(self.results[e])):
                if self.results[e][i] < minPrice:
                    minPrice = self.results[e][i]
                elif self.results[e][i] > maxPrice:
                    maxPrice = self.results[e][i]
                totalClose += self.results[e][i]

            var meanClose = totalClose / Float64(len(self.results[e]))
            var expectedReturnPct = (meanClose - currentPrice) / currentPrice * 100.0

            var signal = String("HOLD")
            if expectedReturnPct > 2.0:
                signal = "BUY"
            elif expectedReturnPct < -2.0:
                signal = "SELL"

            var maxRounded = Float64(trunc(maxPrice * 100)) / 100.0
            var meanRounded = Float64(trunc(meanClose * 100)) / 100.0
            var minRounded = Float64(trunc(minPrice * 100)) / 100.0

            print("\n  " + label + " (" + String(days) + " Trading Days)")
            print("  " + "─" * 35)
            print("  EWMA Drift:  ", self.meanHorizon[e])
            print("  Best Case:   $", maxRounded)
            print("  Average:     $", meanRounded)
            print("  Worst Case:  $", minRounded)
            print("  Signal:      ", signal)
            print("  " + "─" * 35)

        var accuracy = self.runBackTest()
        print("\n  Backtest Accuracy (within 10%):", trunc(accuracy * 100.0) / 100.0, "%")
        print("\n  Elapsed Time:", elapsed, "seconds")

#-------------------------------------------------------------------------------------------------#
# Entry point -- orchestrates the full engine pipeline in order:
#   1. Load training prices, time horizons, and backtest prices from tradingToolCSV.csv
#   2. Compute filtered daily returns using the MAD outlier removal method
#   3. Compute the mean and standard deviation of those filtered returns
#   4. Compute a per-horizon EWMA drift for each user-selected time horizon
#   5. Run 100,000 Monte Carlo simulation paths per horizon (timed in nanoseconds)
#   6. Print the full report: signals, price ranges, backtest accuracy, and elapsed time
fn main() raises:
    var engine = MonteCarloEngine()
    engine.loadData()
    engine.calculateDailyReturns()
    engine.calculateMean()
    engine.calculateStdv()
    engine.calculatePerHorizonEWMA()

    var start = perf_counter_ns()
    engine.runSimulations()
    var end = perf_counter_ns()

    var elapsed = Float64(end - start) / 1_000_000_000.0
    engine.printReport(elapsed)
