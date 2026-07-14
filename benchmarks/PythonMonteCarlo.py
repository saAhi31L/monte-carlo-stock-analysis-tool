# Python Monte-Carlo Risk Engine
# This program is here to show how slow Python is against Mojo 
# because of its GIL liability
# --------------------------------------------------------------

#All of the same libraries imported from the Pipeline except yfinance
import time
import math
import random
import csv

# Reading the CSV through the 'with open()' 
# "r" means read
prices = []
with open("sp500_closes.csv", "r") as f:
    #Stripping each line from the file and incorporating it into the price list as a floating point num
    # since its it takes less memory than a double
    for line in f:
        line = line.strip()
        if line:
            prices.append(float(line))

# Calculate mean and stdv of daily returns 
dailyValueList = []
for i in range(1, len(prices)):
    daily_returns = ((prices[i] - prices[i-1]) / prices[i-1])
    #Daily Returns is the percentage between two consecutive closing prices. It's a small number
    # such as .0045 meaning the 'price went up .00045% today or it went down .0045%'
    dailyValueList.append(daily_returns)

mean = sum(dailyValueList) / len(dailyValueList)

for r in dailyValueList:
    variance = (r - mean) ** 2 

stdv = math.sqrt(variance)

# Run 10,000 simulations
start = time.perf_counter()
results = [] # list to store all of the new calculated numbers into

for i in range(100000): # the amount of simulations

    price = prices[-1] # Starting from the last index of the price list so we can utilize 
    # the most recent number in the list, and make our way backward
    # the '.append()' for a list is basically like a queue --> it always adds elements to the end of the list
    # example: list[2] --> list.append(4) --> list[2,4] --> list.append(3) --> list[2,4,3]

    for j in range(252): # the range here(252) is the amount of stock trading days in a year in the 
        # U.S Stock Exchange --> Just do 252 * how many years(eg. 2, 3,5, 20), and you will predict the stock market
        # in that many years 

        daily_return = mean + stdv * random.gauss(0, 1) #adding the mean + standard dev, multiplied 
        # Gaussian function() from the random module, which returns a floating point number based on the Gaussian distribution
        # aka Normal Distribution (0 --> mean, 1 --> sigma) 

        price = price * math.exp(daily_return) # formula for calculating the distribution of outcomes 
        # to estimate the risk

    # adding all the new/calculated numbers into the results list    
    results.append(price)
end = time.perf_counter()

print("Python Monte Carlo Risk Engine")
print("--------------------------")
print("Best Case:", max(results))
print("Average Case:", sum(results) / len(results))
print("Worst Case:", min(results))
print(f"Elapsed time: {end - start:.4f} seconds")