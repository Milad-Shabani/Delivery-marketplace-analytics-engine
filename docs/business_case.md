# Business Case

## Company

**NOVAFOOD** is a fictional, fast-growing online food-delivery marketplace operating
across 8 metropolitan cities. It is a synthetic company created for this
portfolio/educational case study — it is not affiliated with, and does not use data
from, Snapfood, DoorDash, Uber Eats, Deliveroo, or any real company.

## The management problem

NOVAFOOD has grown delivered orders at roughly 65% annualized over the trailing
history in this dataset, but contribution margin has stayed flat-to-thin (around
5-8% of platform revenue) and is negative in at least one major city. The executive
team wants to know:

1. Which cities, customer segments, restaurants, and delivery zones drive
   *profitable* growth — not just GMV?
2. Why is revenue growing faster or slower than contribution profit?
3. Which operational factors are eroding unit economics?
4. How much demand should NOVAFOOD expect over the next 12 months?
5. What should management actually do about it?

## The central question

> **Can NOVAFOOD grow orders while improving contribution profit?**

And the specific executive target modeled in `docs/assumptions.md` /
`src/analytics/planning.py`:

> **Grow annual orders by 25% next year while improving contribution margin by
> at least 2 percentage points.**

## How this repository answers it

```
DATA  →  ANALYSIS  →  FORECAST  →  FINANCIAL MODEL  →  BUSINESS DECISION
```

- **Data**: a reproducible synthetic order-level ledger (`src/data_generation`)
- **Analysis**: KPI model, unit economics, cohorts, RFM, restaurant/rider performance
  (`src/data_processing`, `src/finance`)
- **Forecast**: 12-month demand forecast with rolling-origin model selection
  (`src/forecasting`)
- **Financial model**: a marketplace P&L, margin-driver decomposition, and a
  strategic growth-vs-margin plan (`src/finance`, `src/analytics/planning.py`)
- **Decision support**: a promotion-budget optimization
  (`src/optimization`) and an executive dashboard (`dashboard/index.html`)
