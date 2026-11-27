# Modelling decisions

This page records the main choices behind the model, the alternatives I considered, the evidence for each, and what each choice is worth. Values are the mean NPV across 50,000 simulated futures with seed 42, unless I say otherwise. The central NPV is +£0.003bn, so each effect below is roughly the NPV the alternative would give.

## Money and discounting

### Cash flows are valued before tax

I discount at Arup's 6.2%, a real rate before tax. Arup built it from BloombergNEF's after-tax, nominal costs of debt and equity, converting them with 2% inflation and 25% corporation tax by the method in BEIS's 2018 cost of capital report. A rate grossed up for tax belongs with cash flows before tax, which is also how Arup's LCOE is built. So the base case values cash flows before tax. Taking 25% tax off them and still discounting at 6.2% would count tax twice and lower the NPV by £0.24bn.

The after-tax view taxes the cash flows at 25%, with the main-pool writing-down allowance of 18% a year, and discounts them at the rate Arup's conversion started from. The BEIS method grosses up for tax in nominal terms, so undoing it gives 4.16% after tax in real terms, and an NPV of +£0.35bn. Applying the gross-up to real rates instead would give (1 − 25%) × 6.2% = 4.65% and +£0.17bn.

UK allowances are set on the build cost in the pounds of the year it is spent and are not indexed, so in the after-tax view they lose value to Arup's 2% inflation. Indexing them would add £0.06bn. The view also leaves out any tax relief on decommissioning, worth at most £0.015bn.

The after-tax view is higher than the base case because the allowances deduct the build cost much faster than the farm loses value, 18% in the first year against about 2%, which pushes tax later. With allowances that only kept pace with the farm's loss of value, the after-tax view would be +£0.02bn at 4.65%, in line with the base case, and +£0.21bn at 4.16%, where the rest comes from the lower rate. I keep the pre-tax view as the base case because it uses Arup's rate as published, and because I have not checked which allowances an offshore wind farm qualifies for, which could move the after-tax view either way.

### Everything is in real 2024 pounds

I work in real 2024 pounds throughout and discount at a real rate. Anything published in another year's prices is restated with the ONS consumer price index (CPI, series D7BT):

- Elexon's wholesale prices, month by month, from the pounds of each day.
- Arup's costs and its LCOE benchmark, from 2023 prices, which adds 2.6%.
- The 2024 auction's CfD strike price, from 2012 prices.

I use CPI because CfD strike prices are set in 2024 prices and rise with CPI, so it keeps every number in the same unit. DESNZ's own factor for moving CfD prices between 2012 and 2024 prices, 0.7177, is the same ratio as the ONS annual averages, 96.1 and 133.9.

The alternative is the GDP deflator, which Arup uses to bring its survey data to 2023 prices. It rose 3.8% from 2023 to 2024, against 2.6% for CPI. Restating Arup's costs with it would lower the NPV by £0.05bn.

Against leaving each figure in its published prices, restating the price history lowers the NPV by £0.02bn, and restating Arup's costs lowers it by £0.11bn.

## Prices

### Two price factors, a fast wobble and a slow drift

The log price is a seasonal pattern plus two random parts, the structure Schwartz and Smith (2000) proposed for commodity prices: a short-term factor that pulls back towards normal, and a long-term level that moves on a random walk with no pull back. A model with only the pull-back settles into a fixed band within weeks, so its range barely grows with the horizon and every timing option comes out worthless by construction. The random walk lets the range keep widening, as long-dated prices do: the P90 to P10 ratio grows from 1.23 in year 1 to 2.65 in year 40.

### The fit starts in January 2024

I fit the season and the short-term factor to January 2024 to June 2026, which leaves out the 2021 to 2023 gas crisis, a one-off shock that would otherwise dominate a 40 year forecast. Fitting from 2018 instead, crisis included, would slow the pull-back from an 18 day half-life to 224 days and lift the average merchant-year price from £80 to £104/MWh. The NPV would rise to +£0.19bn, and waiting would be worth nothing. The cost of the shorter window is a less precise short-term fit, below.

### The long-term drift is my assumption

Thirty months cannot show how fast the long-run level moves, so I set its volatility at 6%/yr and test 4% to 10%. Across that range the NPV moves from -£0.02bn to +£0.07bn, the value of waiting from £0.023bn to £0.014bn, and the expansion option from £0.002bn to £0.092bn. Prices are lognormal, so a higher volatility also raises the average price: the average merchant-year price is £78, £80 and £89/MWh at 4%, 6% and 10%. That is why the value of waiting falls as volatility rises, since building now becomes more attractive. I also assume the level has no trend, so real prices neither rise nor fall on average.

### Negative prices stay in

The daily price is the volume-weighted average of every half-hour that traded on the APX index. That includes the 1,170 half-hours in the fit window, January 2024 to June 2026, when the price went negative. These are real trades, mostly in windy hours of low demand, so leaving them out would overstate the average. In 2024 pounds the window averages £78.40/MWh with them and £80.01 without, 2.0% higher. Keeping them lowers the NPV by £0.03bn.

The model works in log prices, which need a positive price, so the two days whose whole-day average was negative, 7 April 2024 and 28 June 2025, are left out of the fit.

### The fast price swings are measured imprecisely

The short-term wobble is fitted to 29 month-to-month changes. Its half-life comes out at 18 days, but one standard error either side spans 10 to 30 days, so small changes to the data move it noticeably. It matters little: yearly prices average the fast swings out, and swapping in a fit with a 33 day half-life moves the NPV by about £0.001bn.

### Each operating year earns its own year's price

The simulated prices count years from today. A farm committed in year d builds for 5 years, so in operating year j it earns the price simulated for year d + 5 + j. This only matters once the CfD ends: the 21st year of operation falls 26 years from today. Reading each year's price as if there were no build would lower the NPV by £0.006bn, because later prices average slightly higher and spread wider.

## Costs and output

### Costs and load factor from one source

The build cost, the operating cost and the net load factor, 0.505 with a range of 0.460 to 0.561, all come from Arup's 2024 report for DESNZ. That report is also the source of the LCOE benchmark, so the model and the benchmark rest on the same inputs. A load factor of 0.50 instead would lower the NPV by £0.04bn.

### Wear is counted once

Arup defines its load factor as the ratio of average annual output to full-capacity output over the plant's lifetime, net of all losses, and its list of losses includes degradation. So 0.505 already allows for wear. Output does fall as turbines wear, so the model keeps a 0.5%/yr decline but scales it to average 1 over the 35 years: the capacity factor starts at 0.549, ends at 0.463 and averages 0.505.

- Taking the decline off 0.505 instead would count wear twice, leave a lifetime average of 0.464 and lower the NPV by £0.34bn.
- A flat 0.505 in every year would lower the NPV by £0.14bn and raise the CfD break-even to £94.39/MWh, because more of the output would come later.
- The 0.5%/yr rate itself is an industry rule of thumb, not a sourced figure. It only shapes output over the life; the average is fixed by Arup.

### The transmission link is paid for once

Arup's total build cost, £3,976/kW in 2023 prices, includes £937/kW of infrastructure. Arup states that these costs relate to the offshore transmission owner (OFTO) and should not be included in the LCOE, because they are reimbursed to the developer through the OFTO regime and covered by the TNUoS charges the generator pays. The model includes TNUoS, £85,600/MW/yr, in operating costs, so it leaves the £937/kW out of the build cost. Counting both would lower the NPV by £0.83bn.

In practice the developer pays for the link during the build and recovers its value when the link is sold to the OFTO, after commissioning. Funding it in between costs £0.16bn in today's money if the sale comes a year after first power, rising to £0.27bn after four years, unless the sale price also covers the financing cost. Leaving the link out, as Arup does, ignores that cost.

### The LCOE check

With the same inputs, the model's pre-tax LCOE is £86.52/MWh, against Arup's £88.5 in 2023 prices, or £90.81 in 2024 pounds. Applying Arup's conventions one at a time closes the gap almost entirely, which is the best check that the model counts what Arup counts:

| Step, £/MWh in 2024 pounds | LCOE | Change |
|---|---|---|
| The model | 86.52 | |
| Leave out decommissioning, as Arup's LCOE does | 85.97 | −0.55 |
| Spend development costs over the 7 years before construction | 87.68 | +1.71 |
| Phase construction as Arup does, 21.6% a year for four years then the rest | 88.16 | +0.47 |
| Hold output flat at 0.505 over the life | 90.70 | +2.54 |
| Arup | 90.81 | 0.11 left |

### Development costs are counted at the decision

The model counts Arup's development costs, £222/kW in 2024 pounds, as part of the build cost, spread over the 5 year build. In practice they are spent over the years before construction, so a developer deciding whether to build would already have spent them. I keep them in to show the value of the whole project, and this choice matters for the options:

- Treating them as already spent would raise the commit-now NPV by £0.19bn. Building now would then be best in every future, and the right to wait would add nothing.
- Spending them over the 7 years before construction, as Arup's LCOE does, would lower the NPV by £0.08bn.

### Decommissioning

I use £300,000/MW in the final year, a central gross figure within the ranges from DNV (€200,000 to €600,000/MW) and the Crown Estate (about £426,000/MW). Neither states its price year. Arup's survey average is much lower, £86,000/MW in 2023 prices, but it is net of scrap sales, and Arup leaves decommissioning out of its LCOE. Using Arup's figure would raise the NPV by £0.02bn.

## Revenue

### The CfD strike price and its range

The central strike price is £90.91/MWh for 20 years. It is the 2026 auction's average for fixed offshore wind across its regions, £91.20 in England and Wales and £89.49 in Scotland, in 2024 prices. The high case is that auction's £113 cap. The low case is the 2024 auction's price for new fixed offshore wind, £58.87/MWh in 2012 prices, or £82.03 in 2024 pounds. That auction gave 15 year contracts, and a 20 year contract would clear lower, so £82.03 is a cautious low end.

### The capture factor is my assumption

After the CfD the farm sells at the market price, but wind earns less than the time-average price, because every wind farm generates in the same windy hours and that depresses the price then. I apply a capture factor of 0.85 to the merchant years, which fall in the 2050s and 2060s. It is my assumption, not a sourced figure. Across 0.70 to 1.00 it moves the NPV by £0.11bn either way, the smallest swing of any input I test, because the merchant years are far off and heavily discounted.

## Options

### Longstaff-Schwartz with a quadratic in price

I value the options with the least-squares Monte Carlo method of Longstaff and Schwartz (2001), the standard method for options that can be exercised on many dates. At each decision it estimates the value of acting and of waiting from the price already seen, by fitting a quadratic across all futures. The test suite checks the engine against a binomial tree on a textbook American put, to within about 3%. A straight line or a cubic instead of the quadratic changes the option values by less than £0.001bn.

### What each option means

- Defer is the right to delay committing the farm by up to 4 years, including the right never to build. Four years is my choice. The value rises with each extra year allowed, from £0.003bn with no wait to £0.023bn with 4 years.
- Expand is the right to add a fully merchant 500 MW second phase in any year from 3 to 8 years after first power, at a 7.5% lower build cost. The saving is my assumption for lessons learned on the first phase. Arup's medium case has industry build costs flat to 2035 and 4.2% lower by 2040. With no saving the option would be worth £0.011bn, with 4.2% £0.014bn, and with 7.5% £0.017bn.
- Abandon is the right to sell the running farm to a buyer with a cheaper cost of capital. It is a financing gain rather than flexibility, and its two inputs, the buyer's 5.0% rate and the 2% sale cost, have no source, so it is illustrative only.

### Decisions use only prices already seen

The option engine decides at the start of each year, using the average price of the year just ended. At the first decision the owner knows only the price history, which is the same in every future, so the decision cannot depend on which future is unfolding. Deciding instead on the average of the year that is starting would let the owner see months that have not happened yet, and would raise the farm's value with the right to defer from £22.9m to £26.3m, and the expand option from £16.8m to £19.0m.

### The same contract is available in every year

The defer option assumes the same CfD, at the same strike price, is available whenever the owner decides to build. In practice a project bids into a particular auction, and later rounds clear at different prices, so the true value of waiting also depends on what those rounds pay, which the model does not capture.
