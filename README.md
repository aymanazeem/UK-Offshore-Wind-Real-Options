# Offshore Wind Farm, Real Options Valuation

This project works out what a large offshore wind farm is worth, and what the owner's freedom to change course over time adds to that value. The farm is a 1000 MW (1 GW) project off the UK coast.

Two questions drive it. What is the farm worth if the owner commits now. And how much is it worth to be able to wait, expand, or sell later, once electricity prices have moved.

I have written this so that someone with no background in finance or energy markets can follow it. I explain each piece of jargon the first time it appears, but keep the detail intact so it still holds up for a specialist. Every input comes from a public source, and where I could not find one, I say so. The reasons behind the main modelling choices are in [docs/decisions.md](docs/decisions.md).

## What the model finds

On central assumptions the farm breaks even, and the rights to wait and to expand add a little on top.

The headline number is the net present value (NPV). This is every future cash flow the project produces, converted into today's money and summed, minus the build cost. Future money is worth less than money now, so converting it back shrinks it, a step called discounting. A positive NPV creates value, a negative NPV destroys it.

The farm's NPV is +£0.003bn on a £3.12bn build, in effect zero. It is positive in 44% of the 50,000 futures I simulate, with the worst tenth at -£0.24bn or below and the best tenth at +£0.28bn or above.

| Question | Answer |
|---|---|
| Farm value if built now | +£0.00bn, break-even |
| Value of the right to wait up to 4 years | +£0.02bn |
| Value of the right to add a 500 MW second phase | +£0.02bn |
| Value of the right to sell to a buyer with cheaper finance | +£0.27bn, illustrative only |

The break-even sits close to the auction. The CfD strike price the farm would need, £90.84/MWh, is within 10p of the £90.91 the 2026 auction paid. That fits developers bidding near their costs, though the closeness is partly luck: with output held flat over the life, for example, the break-even would be £94.39. Waiting is worth a little because it lets the owner skip the futures where prices look poor, and the second phase is worth about as much. The sale figure rests on two numbers I could not source, so it illustrates a financing effect rather than a result.

These values are before tax, on the same basis as the discount rate I use. An after-tax view, with UK corporation tax and capital allowances, puts the farm at +£0.35bn. [docs/decisions.md](docs/decisions.md) explains both.

## How the model works

### The electricity price

The farm sells at the wholesale price in £/MWh. Nobody knows the future price, so instead of one forecast I simulate 50,000 price paths over the 5 year build and the 35 years of operation, and value the farm on each. This is a Monte Carlo simulation, running the model many times with random draws.

The price history comes from Elexon, which runs the market's settlement. It reports prices in the pounds of each day, so I restate them in 2024 pounds with the consumer price index. I keep the half-hours when the price went negative, which happens on windy days with low demand, because they are part of the true average. Two days in the fit window averaged below zero overall, and the model works in log prices, which need a positive price, so it leaves those two days out.

I build the price from three layers, all in log terms so each is a percentage move.

- A season, a fixed within-year pattern, higher in winter.
- A short-term wobble, fast swings that pull back toward normal. This is a mean-reverting (Ornstein-Uhlenbeck) process, fitted to the last 30 months of prices, January 2024 to June 2026. It reverts fast, with an 18 day half-life, so a spike fades halfway back in under three weeks.
- A long-term drift, where the normal level itself moves on a slow random walk, with no pull back.

The long-term drift is what matters for the options. It lets the price range keep widening with time, the way real long-dated prices behave. A model with only mean reversion settles into a fixed band within weeks, so its range barely grows over decades and every timing option comes out worthless by construction.

I track the spread with P10 and P90, the prices that only 10% of futures fall below and rise above, with P50 the median. The P90 to P10 ratio grows from 1.23 in year 1 to 2.65 in year 40, so a year 1 range of roughly £69 to £84 becomes £46 to £123 by year 40. The average simulated price over the farm's life, £79, matches the average of the 30 months the fit uses. The median sits lower, near £76, because high prices stretch further above it than low prices fall below.

I cannot estimate the drift's size from 30 months of data, so I set it from the literature at 6%/yr and treat it as an assumption to test. I start the fit in 2024 on purpose, to exclude the 2021 to 2023 gas crisis, a one-off that would otherwise dominate a 40 year forecast.

![Price fan](outputs/charts/chart1_price_fan.png)

*The shaded band is the P10 to P90 range. It widens with the horizon, driven by the long-term factor. The dark line is the price history in 2024 pounds, and the dashed line marks first power for a farm committed today.*

### How much the farm generates

Output depends on the wind, which varies year to year. The capacity factor is the share of the farm's theoretical maximum output it actually delivers over a year, so 0.50 means half of flat-out running.

I set the average capacity factor to 0.505, the central net figure Arup publishes for a modern UK offshore farm. The year to year variation, a standard deviation of 0.0213, comes from a 20 year record of simulated output for the site. A capacity factor is trapped between 0 and 1, so I draw it from a Beta distribution fitted to that average and spread.

Arup's 0.505 is an average over the farm's whole life, net of every loss, wear with age included. Output does fall as turbines wear, by about 0.5%/yr on my assumption, so I spread that average over the life rather than take wear off it a second time. Output starts at 4.81 TWh, a capacity factor of 0.549, and falls to 4.06 TWh in the 35th year, averaging 4.42 TWh.

![Capacity factor and generation](outputs/charts/chart_generation.png)

*Left, the capacity factor drawn from the fitted Beta distribution. Right, the yearly output band over the life.*

### Turning prices and output into value

Revenue comes in two stages.

For the first 20 years the farm is paid a fixed price through a Contract for Difference (CfD), the main UK subsidy for new renewables. It pays a set price per MWh, the strike price, whatever the market does, which removes price risk for those years. The strike is £90.91/MWh, from the 2026 auction.

After the CfD the farm sells at the market price of each year it runs, called merchant revenue. A farm committed today first generates after its 5 year build, so its 21st year of operation, the first after the CfD, earns the price simulated for year 26. Wind earns less than the average price here, because every wind farm produces in the same windy hours and that extra supply depresses the price at those times. This is cannibalisation. I apply a capture factor of 0.85, so merchant revenue is 85% of the average price times output.

Against revenue I set three costs. Arup publishes the build and operating costs in 2023 prices, so I restate them in 2024 pounds with the consumer price index, which adds 2.6%. Arup itself works with a different index, the GDP deflator, which rose 3.8% that year. I use the consumer price index to keep costs in the same unit as the CfD and the market prices; the GDP deflator would lower the NPV by about £0.05bn.

- The build cost (CAPEX) is £3,118/kW, or £3.12bn, spread over the 5 year build. Arup's total of £3,976/kW in 2023 prices also includes £937/kW for the offshore transmission link. The developer sells that link to an offshore transmission owner, and the farm pays for it through the grid charge below, so, as Arup does, I leave it out of the build cost rather than pay for it twice.
- The operating cost (OPEX) is £142,100/MW/yr, mostly turbine operations and maintenance (O&M) plus the transmission grid charge (TNUoS).
- Decommissioning, taking the farm down at the end, costs £300,000/MW in the final year.

I discount every future year's cash to today at the weighted average cost of capital (WACC), the annual return investors require, and sum it to the NPV. I use Arup's 6.2%, a real rate (one that leaves out inflation) before tax. Arup built it by grossing up investors' after-tax returns for 25% corporation tax, so I value the cash flows before tax too; taking tax off them as well would count it twice.

Averaged over 50,000 futures the NPV is +£0.003bn, and it splits like this.

| Piece | Value today |
|---|---|
| Build cost | -£2.69bn |
| CfD-year profit | +£2.40bn |
| Merchant-year profit | +£0.32bn |
| Decommissioning | -£0.03bn |
| NPV | +£0.00bn |

![NPV distribution and bridge](outputs/charts/chart2_npv.png)

*Left, the spread of NPV across the 50,000 futures, 56% of them negative. Right, the average build up from cost to NPV.*

### Why the farm breaks even

The clearest lens is the levelised cost of energy (LCOE), the single flat price per MWh the farm would need every year to break even. When the LCOE sits above the price the farm earns, it loses money.

Arup, for the UK government, publishes an LCOE of £88.5/MWh in 2023 prices, £90.8 in 2024 pounds, from the same cost inputs I use. My model's own figure is £86.5, within 5%. Once I apply Arup's conventions the gap closes to £0.11: Arup leaves out decommissioning, spends development costs over the 7 years before construction, phases construction differently and holds output flat over the life. [docs/decisions.md](docs/decisions.md) sets out each step.

The farm earns £90.91 under the CfD for 20 years, £4.4 above its LCOE. In its merchant years the market price averages about £80, of which wind captures about £68, well below it. The two roughly cancel, which is why the NPV is close to zero.

### The three options

A real option is the right, not the duty, to make a decision later once you have seen how things turn out. Waiting, growing, and quitting all carry value, like a financial option. I value three.

I use Longstaff-Schwartz, the standard method for options that can be exercised on many dates. It steps backwards from the final year, and at each year compares acting now against the estimated value of carrying on, keeping the better one. The estimate is the careful part. The payoff from acting depends on prices that have not happened yet, so reading each future's own later prices would be a look-ahead the owner would not really have. Instead the method estimates both values from the prices the owner has already seen, the average of the year just ended, by fitting a curve across all futures, and decides on that. I checked it against a textbook option with a known answer, and it matches.

Defer, the right to wait up to 4 years, adds +£0.02bn to committing now. Waiting lets the owner see how prices move first. At the start the owner knows only the price history, and waiting a year is always worth more than building straight away. In 57% of futures the owner builds in years 2 to 4, and in the other 43% prices never look good enough. The gain is small because the CfD fixes revenue for 20 years, so what decides the outcome is the market price 25 to 40 years after the decision, which the prices seen so far predict only weakly: the correlation is 0.07 when deciding in year 1 and 0.27 in year 4. Waiting with a duty to build by year 4 adds £0.004bn. The value of waiting also assumes the development costs are still to be spent. If they were already spent, building now would be best in every future.

![Defer option](outputs/charts/chart4_defer.png)

*Waiting with the right to walk away is worth most. Waiting with a duty to build by year 4 adds less.*

Expand, the right to add a 500 MW phase in years 8 to 13 at a 7.5% lower build cost (£2,884/kW) from lessons learned, is worth +£0.02bn. Built at the first chance, a merchant second phase would lose £0.23bn, so its value is the right to build only where prices have risen far enough, which happens in 17% of futures.

![Expand option](outputs/charts/chart5_expand.png)

*The option stays near zero until the price a second phase would achieve clears break-even, which merchant prices rarely reach.*

Abandon, here the right to sell the running farm to a buyer with a lower cost of capital, 5.0% against my 6.2%, adds £0.27bn, taking the value from about zero to +£0.27bn. Real options writing treats a sale like this as abandonment, with the sale price as the value recovered. Here it is a financing gain rather than flexibility: the same cash flows are worth more to a buyer who discounts them less, so selling at the start is best on every path. It rests on two numbers I could not source, the buyer's rate and the 2% sale cost, so I treat it as illustrative and leave it out of the conclusions.

![Abandon option](outputs/charts/chart6_abandon.png)

*The sale add-on grows as the buyer's discount rate falls further below ours, and vanishes when the two match.*

### What moves the answer

I change one input at a time across its range and watch the NPV. The farm is at break-even, so every input's break-even sits within about 1% of its central value, and the question is how far each one swings the answer.

| Input, low to high | NPV, low end | NPV, high end |
|---|---|---|
| CfD strike price, £82.03 to £113/MWh | -£0.35bn | +£0.88bn |
| Discount rate (WACC), 5% to 9% | +£0.43bn | -£0.66bn |
| Grid charge (TNUoS), £36,200 to £136,400/MW/yr | +£0.54bn | -£0.55bn |
| Capacity factor, 0.460 to 0.561 | -£0.38bn | +£0.48bn |
| Build cost (CAPEX), £2,585 to £3,498/kW | +£0.46bn | -£0.32bn |
| O&M + insurance, £39,500 to £76,200/MW/yr | +£0.19bn | -£0.21bn |
| Merchant capture, 0.70 to 1.00 | -£0.11bn | +£0.11bn |

The CfD strike moves the NPV most. Its range runs from £82.03/MWh, the 2024 auction's price in 2024 pounds, to the £113 cap of the 2026 auction. The 2024 price was for a 15 year contract, and a 20 year contract would clear lower, so it is a cautious low end. The discount rate and the grid charge come next. The grid charge depends on where the farm connects, so siting alone can move the answer by about £0.5bn either way. Arup gives a single discount rate, so its range is my own test.

![Sensitivity tornado](outputs/charts/chart3_sensitivity.png)

*Each bar swings one input across its range. The CfD strike, discount rate and grid charge move the NPV most.*

## Data and sources

All money is in real 2024 pounds. Figures published in another year's prices are restated with the consumer price index. Where a source gives a range I use the central figure and test the low and high in the sensitivity.

| Input | Source | Value |
|---|---|---|
| Wholesale price history | Elexon market index data, January 2018 to June 2026 | Daily GB price in 2024 pounds, short-term fit from January 2024 |
| Inflation | ONS consumer price index, series D7BT | Restates other years' prices in 2024 pounds |
| Build cost (CAPEX) | Arup for the UK government, 2024 | £3,118/kW over a 5 year build: Arup's development and construction costs, £3,039 in 2023 prices, without the £937 transmission link |
| O&M + insurance | Arup for the UK government, 2024 | £56,500/MW/yr (£55,100 in 2023 prices) |
| Grid charge (TNUoS) | Arup for the UK government, 2024 | £85,600/MW/yr (£83,400 in 2023 prices) |
| Capacity factor | Arup for the UK government for the average, renewables.ninja for the spread | 0.505 lifetime average (0.460 to 0.561), 0.0213 standard deviation |
| Operating life, discount rate | Arup for the UK government, 2024 | 35 years; 6.2% real before tax, tested from 5% to 9% |
| Output decline with age | Industry rule of thumb, my assumption | 0.5%/yr, scaled so output still averages the load factor |
| CfD strike and term | UK auction results, January 2026 and September 2024 | £90.91/MWh for 20 years; range £82.03 (the 2024 auction) to the £113 cap |
| Decommissioning | DNV, Crown Estate | £300,000/MW in the final year, price year not stated |
| Corporation tax | UK main rate | 25%, with an 18% writing-down allowance on the nominal build cost, in the after-tax view only |
| Merchant capture factor | My assumption, for cannibalisation | 0.85 |
| Long-term price volatility | My assumption, from the literature | 6%/yr |
| Second phase cost saving | Arup and IRENA learning rates | 7.5% |
| Buyer discount rate, sale cost | Not sourced, placeholders | 5.0%, 2% |

The price history contains BMRS data © Elexon Limited copyright and database right 2026, used under the [BMRS data licence](https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/). The consumer price index is from the Office for National Statistics, licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

## What I could not pin down

Eight things are weaker than the rest, and I flag them.

- The tax basis. Before tax, on Arup's basis, the farm breaks even. After tax it looks better, at +£0.35bn, or +£0.17bn if Arup grossed up its rate in real rather than nominal terms. The after-tax view also leans on capital allowances, and I have not checked which ones an offshore wind farm qualifies for, which could move it either way.
- The shape of wear. The 0.5%/yr decline is a rule of thumb, not a sourced figure. It only spreads Arup's lifetime average over the years, but at break-even that matters: output held flat over the life would lower the NPV by £0.14bn and raise the break-even strike price to £94.39/MWh.
- The transmission link. The developer pays for it during the build and gets its value back when the link is sold to an offshore transmission owner, after first power. Leaving it out, as Arup does, ignores the cost of funding it in between: £0.16bn if the sale comes a year after first power, rising to £0.27bn after four years, unless the sale price also covers the financing cost. Arup notes the sale can also make a profit, which would cut the other way.
- The long-term price volatility, 6%/yr, is a literature assumption, not something the data can pin down. Across the literature's 4% to 10%, the farm's value moves from -£0.02bn to +£0.07bn, the value of waiting from £0.023bn to £0.014bn, and the second phase from £0.002bn to £0.092bn, so it matters most for the expansion. Waiting is worth less at higher volatility because, in this model, volatility also raises the average merchant price, from £78 to £89/MWh, which makes building now more attractive.
- The buyer's discount rate and sale cost in the abandon option, 5.0% and 2%, have no single source.
- The short-term price fit uses only 30 months. This is deliberate, to exclude the gas crisis, and it only sets the fast wobble. Its two numbers, how fast prices pull back and how hard they jump, are imprecise and shift noticeably with small changes to the data, but they barely move yearly prices. The long-run uncertainty comes from the drift.
- The grid charge is at the central, location-specific figure. A better or worse sited farm pays very different charges, so siting can move the answer by about £0.5bn either way.
- The year to year spread of output comes from renewables.ninja, a free tool that estimates a turbine's output from past weather. I used one turbine at Dogger Bank in the North Sea, with NASA's MERRA-2 record of the weather from 2000 to 2019. I did not record the turbine model or hub height, so I cannot regenerate that series exactly. The model uses only its spread, a standard deviation of about 4% of average output, which is small next to the price uncertainty.

## Running it

You need Python 3.12, 3.13 or 3.14, and the automatic checks on GitHub use 3.13. If `python3` on your machine is another version, name one of these, for example `make install PYTHON=python3.13`.

```bash
make install      # create ./venv if needed, then install the pinned dependencies
make data         # download the Elexon prices and the ONS price index, then rebuild the daily price file
make test         # run the test suite
make charts       # regenerate every chart at 50,000 paths
make lcoe         # print the levelised cost reconciliation
```

`make data` needs internet access and takes a couple of minutes. It fetches the dates set in `config/parameters.py` and, unless Elexon revises its records, reproduces the committed `data/processed/gb_price_daily.csv`. `make price` then refits the price model to it.

Each part also runs on its own.

```bash
./venv/bin/python -m src.download_prices      # fetch the Elexon prices and the ONS price index
./venv/bin/python -m src.data_prep            # turn them into the daily price series
./venv/bin/python -m src.price_simulator      # recalibrate and show the price range widening
./venv/bin/python -m src.financial_model      # the static NPV
./venv/bin/python -m src.lsm_engine --option=defer
./venv/bin/python -m src.lsm_engine --option=expand
./venv/bin/python -m src.lsm_engine --option=abandon
./venv/bin/python -m src.sensitivity
```

## Project structure

Each file has one job, and the calculation is kept separate from the charts, so every module reads as plain maths. The flow of data through the project is below. Solid arrows carry data, dotted arrows carry the input numbers from the config file.

```mermaid
flowchart TD
    elexon(["Elexon market index API"])
    ons(["ONS consumer price index"])
    ninja(["cf_annual.csv, renewables.ninja"])
    params["config/parameters.py, every input"]

    elexon --> dl["download_prices.py"]
    ons --> dl
    dl -->|"half-hourly prices, monthly CPI"| prep["data_prep.py"]
    prep -->|"daily prices in 2024 pounds"| daily[("gb_price_daily.csv")]

    daily --> cal["price_simulator.py, calibrate"]
    cal -->|"fitted price process"| caljson[("price_calibrated.json")]
    caljson --> simp["price_simulator.py, simulate_price_paths"]

    ninja --> gen["generation_model.py"]

    simp -->|"price paths"| fin["financial_model.py, cash flows to NPV"]
    gen -->|"generation"| fin

    fin -->|"NPV"| viz["visualisation.py"]
    fin --> lsm["lsm_engine.py, defer, expand, abandon"]
    fin --> sens["sensitivity.py"]
    fin --> lcoe["lcoe.py"]

    lsm --> viz
    sens --> viz
    lcoe --> viz
    viz -->|"7 charts"| charts(["outputs/charts/"])

    params -.-> simp
    params -.-> gen
    params -.-> fin
```

| File | Job |
|---|---|
| config/parameters.py | Every input number, in one place |
| src/download_prices.py | Download the raw half-hourly prices from Elexon and the consumer price index from ONS |
| src/data_prep.py | Turn the raw price download into a daily series in 2024 pounds |
| src/price_simulator.py | Calibrate and simulate the electricity price |
| src/generation_model.py | Turn the capacity factor into yearly output |
| src/financial_model.py | Turn prices and output into cash flows and the NPV |
| src/lcoe.py | Reconcile the model to the published cost benchmark |
| src/lsm_engine.py | Value the defer, expand and abandon options |
| src/sensitivity.py | Show which input moves the NPV most |
| src/visualisation.py | Draw every chart |
| tests/ | Checks on the maths, including the option engine against a known answer, and on the data downloads and daily prices |
```
