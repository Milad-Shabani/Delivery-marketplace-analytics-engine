# Optimization Methodology

## Business problem

Allocate a fixed monthly promotion budget across **city × customer-segment**
cells to maximize incremental contribution profit, rather than splitting it
evenly (the common default).

## Response model

Each cell's incremental orders from spend `x` are modeled as a saturating
(concave) curve:

```
incremental_orders(x) = a · (1 − e^(−x / b))
```

- `a` scales with the cell's order volume and average price sensitivity
  (more price-sensitive cells respond more to promotions).
- `b` controls how quickly the response saturates (diminishing returns) —
  smaller `b` means the cell saturates faster.

Incremental contribution profit is `incremental_orders(x) × profit_per_order`
for that cell, where `profit_per_order` is the cell's own observed
contribution profit per order (so we don't overspend promoting cells that are
already loss-making per order).

## Solver

`scipy.optimize.minimize` with `method="trust-constr"`, given:

- **Objective**: maximize total incremental contribution profit (minimize its
  negative), with an analytic gradient supplied.
- **Equality constraint**: total spend = the fixed monthly budget.
- **Bounds**: a floor (0.5% of budget) so every active cell keeps some spend,
  and a cap (35% of budget) so no single cell absorbs the whole budget.

`trust-constr` was chosen over `SLSQP` after testing: with response curves
that span roughly two orders of magnitude in steepness (`b`) across cells,
SLSQP repeatedly hit its iteration cap without confirming convergence, while
`trust-constr` converges cleanly (see `data/processed/optimization_summary.json`,
`converged: true`). This is a legitimate, standard solver for a small,
smooth, concave nonlinear allocation problem — a full mixed-integer or
stochastic-programming formulation would be overkill for a single-period
budget split like this one.

## Reading the output

`optimization_allocation.csv` has one row per city × segment cell with the
baseline (even-split) and optimized spend, and the resulting incremental
profit under each. `optimization_summary.json` reports the aggregate gain.
