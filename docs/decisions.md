# Modelling decisions

This page records the main choices behind the model, the alternatives I considered, the evidence for each, and what each choice is worth. Values are the mean NPV across 50,000 simulated futures with seed 42, unless I say otherwise.

## Money and prices

### Everything is in real 2024 pounds

I work in real 2024 pounds throughout and discount at a real rate. Anything published in another year's prices is restated with the ONS consumer price index (CPI, series D7BT):

- Elexon's wholesale prices, month by month, from the pounds of each day.
- Arup's costs and its LCOE benchmark, from 2023 prices, which adds 2.6%.
- The 2024 auction's CfD strike price, from 2012 prices.

I use CPI because CfD strike prices are set in 2024 prices and rise with CPI, so it keeps every number in the same unit. DESNZ's own factor for moving CfD prices between 2012 and 2024 prices, 0.7177, is the same ratio as the ONS annual averages, 96.1 and 133.9.

The alternative is the GDP deflator, which Arup uses to bring its survey data to 2023 prices. It rose 3.8% from 2023 to 2024, against 2.6% for CPI. Restating Arup's costs with it would lower the NPV by £0.05bn.

Against leaving each figure in its published prices, restating the price history lowers the NPV by £0.01bn, and restating Arup's costs lowers it by £0.10bn.

### Negative prices stay in

The daily price is the volume-weighted average of every half-hour that traded on the APX index. That includes the 1,170 half-hours in the fit window, January 2024 to June 2026, when the price went negative. These are real trades, mostly in windy hours of low demand, so leaving them out would overstate the average. In 2024 pounds the window averages £78.40/MWh with them and £80.01 without, 2.0% higher. Keeping them lowers the NPV by £0.02bn.

The model works in log prices, which need a positive price, so the two days whose whole-day average was negative, 7 April 2024 and 28 June 2025, are left out of the fit.

### The fast price swings are measured imprecisely

The short-term wobble is fitted to 29 month-to-month changes. Its half-life comes out at 18 days, but one standard error either side spans 10 to 30 days, so small changes to the data move it noticeably. It matters little: yearly prices average the fast swings out, and swapping in a fit with a 33 day half-life moves the NPV by less than £0.001bn.

### Each operating year earns its own year's price

The simulated prices count years from today. A farm committed in year d builds for 5 years, so in operating year j it earns the price simulated for year d + 5 + j. This only matters once the CfD ends: the 21st year of operation falls 26 years from today. Reading each year's price as if there were no build would lower the NPV by £0.004bn, because later prices average slightly higher and spread wider.

## Costs and output

### Costs and load factor from one source

The build cost, the operating cost and the net load factor, 0.505 with a range of 0.460 to 0.561, all come from Arup's 2024 report for DESNZ. That report is also the source of the LCOE benchmark, so the model and the benchmark rest on the same inputs. A load factor of 0.50 instead would lower the NPV by £0.03bn.

### Decommissioning

I use £300,000/MW in the final year, a central gross figure within the ranges from DNV (€200,000 to €600,000/MW) and the Crown Estate (about £426,000/MW). Neither states its price year. Arup's survey average is much lower, £86,000/MW in 2023 prices, but it is net of scrap sales, and Arup leaves decommissioning out of its LCOE. Using Arup's figure would raise the NPV by £0.02bn.

### Open: wear and transmission are counted twice

Two costs appear twice, and together they explain most of the £22/MWh gap between my LCOE and Arup's:

- Arup's load factor is an average over the farm's life, net of all losses, wear included. The model also takes 0.5%/yr off output as the turbines age, so its lifetime average is 0.465, not 0.505.
- Arup's total build cost includes £937/kW of infrastructure, the offshore transmission link. The developer sells that link to an offshore transmission owner (OFTO), and the farm then pays for it through the TNUoS grid charge, which the model also includes. Arup leaves the infrastructure out of its LCOE for that reason.

## Revenue

### The CfD strike price and its range

The central strike price is £90.91/MWh for 20 years. It is the 2026 auction's average for fixed offshore wind across its regions, £91.20 in England and Wales and £89.49 in Scotland, in 2024 prices. The high case is that auction's £113 cap. The low case is the 2024 auction's price for new fixed offshore wind, £58.87/MWh in 2012 prices, or £82.03 in 2024 pounds. That auction gave 15 year contracts, and a 20 year contract would clear lower, so £82.03 is a cautious low end. The range affects only the sensitivity.

## Options

### Decisions use the price of the decision year

The option engine decides each year from that year's average price. That average includes months the owner has not yet seen, so it slightly flatters the decisions. It has no effect on the current results, because the farm is never built under the defer option and the sale happens at the start on every path. Near break-even it can add a few million pounds to an option's value; using the last completed year's price instead would remove that.
