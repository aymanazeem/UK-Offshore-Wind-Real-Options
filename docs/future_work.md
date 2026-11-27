# Future work

Proposals, not commitments. Ordered by leverage on the central finding: a static NPV of about
−£1.19bn with the defer and expand options near £0.

## Done (were the biggest issues in the earlier version)

- **Two-factor price model.** The price is now season + a fast mean-reverting short-term factor +
  a slow random-walk long-term level (`price_simulator.py`). The long-term factor makes the fan
  widen with the horizon (P90/P10 ~1.2 at year 1 → ~2.7 at year 40), so the muted timing options
  are now a genuine economic result, not an artifact of a flat fan.
- **Capital allowances in the base case.** The base case uses the 18% writing-down allowance (the
  realistic UK tax shield), not conservative straight-line.
- **Merchant capture factor.** Merchant revenue is haircut by a capture factor (0.85) to reflect
  cannibalisation, applied to merchant years only.

## 1. Calibrate the long-term price volatility to forward data

The long-term volatility (`PRICE_LT_VOL`) is currently a forward-looking assumption reported as a
sensitivity, because ~2.5 years of history cannot pin it down. The principled fix is to calibrate
it (and the whole two-factor model, e.g. via a Kalman filter) against long-dated GB power
forward-curve data (ICE/EEX baseload futures or broker curves). This is the one genuinely new data
class the project needs, and the item most likely to be blocked on the corporate network — confirm
access before starting.

## 2. Stochastic CAPEX and construction cost

CAPEX is deterministic at the Arup central figure. Real developers face material capital-cost risk
(supply chain, steel, vessels, financing). Making CAPEX stochastic would widen the NPV distribution
and give the defer option a second, price-independent rationale — waiting to resolve cost
uncertainty — that a price-only model cannot capture. Needs no external data.

## 3. Sub-annual price shape and a declining capture curve

Revenue uses annual-average prices with a single flat capture factor. A price-duration-curve or
hourly overlay on the merchant tail would let the capture factor decline over time as renewable
penetration rises, and capture negative-price hours. Needs an hourly wind-and-price dataset.

## 4. TNUoS and siting scenario

TNUoS sits at the Arup central, location-specific charge (~+£20/MWh on LCOE). A better-sited
project carries far less. A locational scenario would quantify how much of the negative NPV is the
grid charge versus the underlying economics. Cheap — a parameter sweep, no new data.
