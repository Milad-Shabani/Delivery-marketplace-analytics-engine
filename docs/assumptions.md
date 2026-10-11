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

### Marketing spend table (v2)
`data/raw/marketing_spend.csv` (month × channel: `signups`, `marketing_spend`,
`cac`) is a *generated* table: spend = sign-ups × the channel CAC above, with
CAC drifting up each month (Paid Search +1.5 %/month, Paid Social +1.2 %,
Partnership +0.6 %, Push/CRM +0.3 %, Organic +0.2 %) and ±6 % noise. The
dashboard's "observed" CAC and observed LTV:CAC come from this table, so the
gap to the planning assumption is a modelled outcome of that drift — not
market evidence. Only customers who sign up inside the reporting window
(Apr 2025 – 23 Aug 2026) count as acquisitions.

### Rider shifts table (v2)
`data/raw/rider_shifts.csv` (rider × month: `orders`, `busy_hours`,
`online_hours`, `distance_km`). Busy hours = distance / vehicle speed
(Bike 14, Scooter 22, Car 26 km/h) + 0.12 h hand-off per order; online hours =
busy hours / a per-rider-month utilization drawn around 45 % (bounded 25–75 %).

Both tables use their own seeded random streams, so the original six tables
and every v1 number are bit-for-bit unchanged.

### Sign-up truncation
Customer sign-ups are generated over a fixed 510-day window ending on
2026-08-23, so the final reporting month holds only ~22 days of sign-ups.
Sign-up-driven KPIs (new customers, new-customer share, marketing spend, CAC,
marketing % of revenue) therefore use a trailing 3-month window on the
scorecard (tagged "3M") instead of a single month.

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
This project does not claim to use real data from any real company. All figures above
are either generated synthetically with documented parameters, or stated
illustrative assumptions (like the CAC table) used consistently throughout
the analysis.
