# Financial Model

## Marketplace P&L structure

```
GMV (food_value + delivery_fee + service_fee, delivered/refunded orders)
  − Discounts / Customer Incentives
  = Net Customer Spend

Platform Revenue
  = Restaurant Commission Revenue
  + Delivery Fee Revenue (35% of collected delivery fee retained by the platform)
  + Service Fee Revenue
  − Refund offset (50% of refund_amount)

Variable Costs
  = Rider / Delivery Cost
  + Payment Processing Cost (1.9% + $0.10 per order)
  + Promotion Cost (= discount_amount, viewed as a marketing-spend line)
  + Refund Amount (remaining 50%, on top of the revenue offset above)

Contribution Profit = Platform Revenue − Variable Costs
Contribution Margin % = Contribution Profit / Platform Revenue
```

This mirrors how real delivery marketplaces typically report unit economics:
GMV is a volume metric, not a revenue metric; only the commission/fee take is
revenue, and rider payouts are the largest variable cost line.

## Unit economics

Computed per order and rolled up by city, customer segment, and acquisition
channel (`src/finance/finance.py::unit_economics_by`):

- **AOV** = GMV / orders
- **Revenue per order** = platform revenue / orders
- **Variable cost per order** = (rider + payment processing + promotion + refund) / orders
- **Contribution profit per order** = contribution profit / orders
- **LTV** = average customer lifetime contribution profit, by channel
- **CAC** = an assumed, documented cost per channel (see `docs/assumptions.md`)
- **LTV : CAC** and **payback (in orders)** follow directly

## Margin driver decomposition

`margin_driver_decomposition()` compares the first and last full month in the
series and attributes the contribution-margin-percent change to five drivers
using a first-order (linear) sensitivity approximation:

- Discount rate (% of GMV)
- Rider cost rate (% of platform revenue)
- Payment processing rate (% of platform revenue)
- Refund rate (% of platform revenue)
- Revenue mix / take-rate (platform revenue as % of GMV)

This is a standard, transparent way to communicate driver direction and
rough magnitude to management. It is **not** a formal Shapley/Oaxaca-Blinder
decomposition — with only five drivers and monthly granularity, the simpler
linear approximation is more legible without materially changing the
conclusion, and that trade-off is stated here rather than hidden.

## Strategic plan model (`src/analytics/planning.py`)

Given the executive target (+25% annual orders, +2pp contribution margin), the
model:

1. Annualizes the trailing month's delivered orders and compares to the +25% target.
2. Takes the trailing-3-month average contribution margin as the baseline.
3. Computes illustrative, isolated lever sizes (discount-rate cut,
   rider-cost-rate cut, required AOV growth, required retention lift,
   required take-rate increase, required rider productivity gain) needed to
   close the gap if pulled one at a time.
4. Checks those lever sizes against a share of the current rate (a simple
   feasibility heuristic) and returns a verdict plus the full lever table —
   management still decides how to combine levers; the model frames the
   trade-off rather than dictating the plan.
