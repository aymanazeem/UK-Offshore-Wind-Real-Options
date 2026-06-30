# Future work

Proposals, not commitments. Each is gated on author go-ahead. The first additionally depends
on getting data off the corporate network, since the Zscaler proxy blocked the live
renewables.ninja pull, so treat any external data dependency as a real obstacle until proven
otherwise.

Ranked by leverage on the central finding, a static NPV of -£1.27bn with the defer and expand
options coming out near £0.

## 1. Two-factor price model, the principled fix for the muted options

The defer and expand options came out near £0 largely because of the price model, not because
flexibility is genuinely worthless. A single-factor Ornstein-Uhlenbeck process reverts to its
mean within roughly one half-life, about 6 weeks at the monthly calibration, so the simulated
price fan flattens after the first year or two. The long-dated price uncertainty that defer and
expand key off therefore barely exists in the model. It is strangled by mean reversion and by
averaging 35 annual draws. This is the single biggest modelling limitation.

The fix is a Schwartz-Smith (2000) two-factor model. A short-term deviation reverts to the mean
as now, and a stochastic equilibrium level follows a random walk with drift. Because the
equilibrium factor does not revert, the fan keeps widening with horizon, restoring genuine
uncertainty in the merchant tail, years 21 to 35, which is exactly where the option value should
live. The expected outcome is that the expand option, and the price-timing component of defer,
move off zero in a defensible way.

The gate is data. Calibrating the equilibrium factor wants long-dated GB power forward-curve
data, for example ICE or EEX baseload futures or broker curves out several years. This is the one
genuinely new data class the project would need, and it is the item most likely to be blocked on
the corporate network, so confirm access before starting.

Effort is moderate. The simulation and LSM layers already take an arbitrary price matrix, so the
change is contained to `price_simulator.py` plus a new calibration path. The option engines are
agnostic to how prices were generated.

## 2. CAPEX and construction-cost uncertainty, a different source of option value

The current model treats CAPEX as deterministic at the Arup central figure. Real developers face
material capital-cost risk from supply chain, steel, installation vessels and financing. Making
CAPEX stochastic would widen the NPV distribution, and it would give the defer option a second,
price-independent rationale, waiting to resolve cost uncertainty, that the price-only model
cannot capture. This is arguably the most realistic way to make deferral genuinely valuable, and
it needs no external data, since a sourced cost-volatility assumption suffices. Worth doing
alongside or before item 1.

## 3. Promote capital allowances to the base case

Front-loaded UK capital allowances are already implemented via `depreciation_method` and add
£257m on the 18% writing-down allowance, rising to £407m under full expensing. They are the
correct UK tax treatment, so realistic bid economics should arguably use them as the headline
rather than the conservative straight-line reference. The decision needed is realistic-bid
framing versus conservative-reference framing. Effort is trivial, flip a config default and
re-baseline the tests.

## 4. Sub-annual price shape, capture, cannibalisation and negative prices

Revenue is computed on annual-average prices. With rising renewables penetration, wind capture
prices diverge from baseload through cannibalisation, and negative-price hours are increasingly
common. An hourly or price-duration-curve overlay on the merchant tail would sharpen merchant
revenue and the CF and price interaction. It needs an hourly wind and price dataset, and effort
is moderate.

## 5. Empirical CF and price dependence

The CF and price correlation is currently a Gaussian-copula tilt with a single correlation value
from the literature. A genuine version would estimate the joint distribution from a real GB
wind-output and price series, renewables.ninja CF plus Elexon price, capturing the full
non-linear cannibalisation shape. The effect is small, under £1m, given the CfD shields 20 years,
so this is low priority. It is about honesty, not materiality.

## 6. TNUoS and siting scenario

TNUoS sits at the Arup central, location-specific charge, about +£20/MWh on LCOE. A better-sited
project carries far less. A locational scenario would quantify how much of the -£1.27bn is the
grid charge versus the underlying economics. Cheap, it is a parameter sweep with no new data.
