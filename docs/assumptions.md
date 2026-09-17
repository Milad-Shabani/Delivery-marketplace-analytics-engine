# Assumptions

This project uses **synthetic data calibrated to realistic marketplace
economics** — it is not real company data. Every hardcoded number below is a
modeling assumption, documented here rather than hidden in code.

## Scale (see README "Scope note" for why this differs from the original brief)
- ~12,000 customers, 320 restaurants, 520 riders, ~167,000 orders, 17 months
  of history (Apr 2025 – Aug 2026).
- Reproducible via a fixed NumPy seed (`SEED = 20260916` in
  `src/data_generation/generate.py`).

## Commission & take rate
- Restaurant commission rate: 16% (Budget tier) / 20% (Mid) / 24% (Premium) of
  food value, ± small random noise per restaurant.
- Platform retains 35% of the collected delivery fee as delivery revenue;
  the rest is passed through to rider cost.

## Delivery economics
- Rider cost = a city-level base pay per order ($1.14–$1.35) + distance (km) ×
  a city-level cost-per-km ($0.44–$0.55).
- Delivery fee charged to the customer = $1.2 base + $0.42/km + noise.

## Payments & promotions
- Payment processing cost = 1.9% of customer_total_paid + $0.10 per order
  (typical card-processing economics).
- Discounts are higher for price-sensitive customers and during low-season
  months (Jan/Feb/Sep), and every customer's first order carries an implicit
  new-customer discount if no other promotion applied.

## Customer behavior
- ~45% of customers pre-date the reporting window (an existing base); the
  rest sign up progressively during it — this avoids an unrealistic "zero to
  full base" ramp in the first few months.
- Underlying MoM organic growth trend: ~0.9%, with mild deceleration.
- Monthly seasonality: dip in Feb (~-14% vs. average), peak in Nov-Dec
  (~+15-20%) and mid-summer (~+8-10%).
- New-customer activity ramps up over ~2-3 months post-signup, then retention
  decays gradually with tenure (`exp(-0.028 × tenure)` after month 2) unless
  reinforced by subscription/loyalty behavior.

## Customer acquisition cost (CAC), by channel — illustrative
| Channel | Assumed CAC |
|---|---|
| Organic/Referral | $1.50 |
| Push/CRM | $2.00 |
| Partnership | $6.00 |
| Paid Social | $9.00 |
| Paid Search | $11.50 |

These are stated assumptions for the LTV:CAC analysis, not observed data —
flagged here explicitly per the "no data fabrication" principle below.

## Forecast horizon & scenarios
- 12-month forecast horizon; rolling-origin validation with a 3-month holdout
  per fold (see `docs/forecasting_methodology.md`).
- Scenario cases: Upside = point forecast × 1.12, Downside = point forecast ×
  0.85 (illustrative bands, not modeled from a separate causal driver).

## Optimization constraints
- Per-cell spend floor: 0.5% of the monthly promotion budget.
- Per-cell spend cap: 35% of the monthly promotion budget.
- Budget = trailing-3-month average monthly promotion spend in the dataset.

## No data fabrication
This project does not claim to use real data from Snapfood, SnappFood,
DoorDash, Uber Eats, Deliveroo, or any other real company. All figures above
are either generated synthetically with documented parameters, or stated
illustrative assumptions (like the CAC table) used consistently throughout
the analysis.
