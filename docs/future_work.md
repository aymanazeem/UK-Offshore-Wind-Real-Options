# Future work

Proposals, not commitments. The central NPV is about £0, so each item below could tip the answer either way. They are ordered by how much they could move it.

## 1. Model the transmission link's round trip

The model leaves out the £937/kW transmission link, as Arup does, because the farm pays for it through the TNUoS grid charge. In practice the developer funds the link during the build and recovers its value when it is sold to an offshore transmission owner after first power. Funding it in between is worth £0.16bn to £0.27bn, depending on when the sale happens and whether the sale price covers financing costs. Adding the outflow during the build and the sale proceeds afterwards would remove that gap. It needs Ofgem's rules on what the sale price covers.

## 2. Settle the tax treatment

The base case values cash flows before tax, because Arup's 6.2% is a pre-tax rate. The after-tax view puts the farm at +£0.35bn, but it assumes every pound of build cost earns the 18% main-pool allowance from first power. Checking which capital allowances an offshore wind farm's assets qualify for, and when they can be claimed, would make the after-tax view firm enough to report alongside the base case.

## 3. Calibrate the long-term price volatility to forward data

The long-term volatility, 6%/yr, is my assumption, because 30 months of history cannot pin it down. Across my test range of 4% to 10% it moves the farm's value from -£0.02bn to +£0.07bn and the expansion option from £0.002bn to £0.092bn, partly because in this model a higher volatility also raises the average merchant price. Calibrating the two-factor model to long-dated GB power forward prices, for example with a Kalman filter, would replace the assumption with a measurement. This is the one new class of data the project needs, and forward prices are usually licensed, so check access first.

## 4. Seabed rent and business rates

Arup's LCOE, and so this model, leaves out seabed lease payments to the Crown Estate and business rates. As an illustration, a seabed rent of 2% of revenue would lower the NPV by about £0.09bn. Sourcing both would close the last gap between the model and a developer's full cost.

## 5. Uncertain build cost

The build cost is fixed at Arup's central figure. Real developers face large build-cost risk from the supply chain, steel, vessels and financing. Making it uncertain would widen the NPV distribution and give the defer option a second reason to wait, to see costs settle, that a price-only model cannot capture. It needs no new data.

## 6. When the CfD is available

The defer option assumes the same CfD, at the same strike price, is available in any of the next four years. In practice a project bids into a particular auction, and later rounds clear at different prices. Modelling the next auction's price as uncertain would make the value of waiting more realistic.

## 7. Hourly prices and a falling capture factor

Revenue uses yearly average prices and a flat capture factor of 0.85. An hourly overlay on the merchant years would let the capture factor fall as more wind is built, and show how often the farm sells into negative prices. It needs an hourly wind and price dataset.

## 8. Siting and the grid charge

The grid charge sits at Arup's central, location-specific figure. Across its range it moves the NPV by about £0.5bn either way. A scenario for named locations would show how much of the answer depends on where the farm connects. It is a cheap parameter sweep that needs no new data.
