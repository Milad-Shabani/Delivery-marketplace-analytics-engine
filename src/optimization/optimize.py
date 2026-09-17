"""Promotional-budget allocation optimization.

Business problem: allocate a fixed monthly promotion budget across
(city x customer segment) cells to maximize incremental contribution profit,
subject to a total budget cap, a per-cell spend cap (diminishing returns /
practical delivery limits), and a minimum-service constraint that every
active cell gets at least a small floor spend.

We model each cell's response as a concave (saturating) function of spend --
incremental orders = a * (1 - exp(-spend / b)) -- fit loosely from the
cell's observed discount-elasticity proxy (price sensitivity), then solve the
allocation with SciPy's SLSQP (a standard nonlinear solver appropriate for a
smooth, small-dimension concave allocation problem such as this one).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.optimize import minimize, LinearConstraint, Bounds


def build_cells(orders: pd.DataFrame, customers_enriched: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    o = orders[orders.order_status.isin(["Delivered", "Refunded"])].merge(
        customers_enriched[["customer_id", "customer_segment", "price_sensitivity"]], on="customer_id", how="left"
    )
    g = o.groupby(["city_id", "customer_segment"]).agg(
        orders=("order_id", "count"),
        contribution_profit=("contribution_profit", "sum"),
        avg_price_sensitivity=("price_sensitivity", "mean"),
        revenue=("platform_revenue", "sum"),
    ).reset_index()
    g = g.merge(cities[["city_id", "city_name"]], on="city_id", how="left")
    g["contribution_margin_pct"] = np.where(g.revenue > 0, g.contribution_profit / g.revenue, 0)
    # response-curve params: cells with higher price sensitivity respond more to promo spend (a),
    # but saturate faster (smaller b => quicker diminishing returns)
    g["resp_a"] = (g.orders * 0.06 * (0.5 + g.avg_price_sensitivity)).clip(lower=1)
    g["resp_b"] = (g.orders * 0.9 / (0.4 + g.avg_price_sensitivity)).clip(lower=50)
    g["profit_per_incremental_order"] = g.contribution_profit / g.orders.replace(0, np.nan)
    g["profit_per_incremental_order"] = g.profit_per_incremental_order.fillna(g.profit_per_incremental_order.median())
    return g


def optimize_allocation(cells: pd.DataFrame, total_budget: float, min_floor_frac=0.005, max_cell_frac=0.35) -> pd.DataFrame:
    n = len(cells)
    a = cells.resp_a.values
    b = cells.resp_b.values
    ppo = cells.profit_per_incremental_order.clip(lower=0.05).values

    def neg_profit(x):
        incr_orders = a * (1 - np.exp(-x / b))
        return -np.sum(incr_orders * ppo)

    def neg_profit_grad(x):
        d = (a / b) * np.exp(-x / b) * ppo
        return -d

    floor = total_budget * min_floor_frac
    cap = total_budget * max_cell_frac
    x0 = np.full(n, total_budget / n).clip(floor, cap)
    bounds = Bounds(np.full(n, floor), np.full(n, cap))
    lin_constraint = LinearConstraint(np.ones(n), total_budget, total_budget)

    # trust-constr handles the bound + equality-budget constraint far more
    # reliably than SLSQP here, given the wide dynamic range of per-cell
    # response-curve steepness (resp_b spans ~2 orders of magnitude).
    res = minimize(neg_profit, x0, jac=neg_profit_grad, method="trust-constr",
                    bounds=bounds, constraints=[lin_constraint],
                    options={"maxiter": 2000, "gtol": 1e-8, "xtol": 1e-10})

    df = cells.copy()
    df["optimized_spend"] = res.x
    # naive/status-quo baseline: even split, for "before optimization" comparison
    baseline_spend = np.full(n, total_budget / n)
    df["baseline_spend"] = baseline_spend
    df["baseline_incremental_orders"] = a * (1 - np.exp(-baseline_spend / b))
    df["optimized_incremental_orders"] = a * (1 - np.exp(-df.optimized_spend / b))
    df["baseline_incremental_profit"] = df.baseline_incremental_orders * ppo
    df["optimized_incremental_profit"] = df.optimized_incremental_orders * ppo
    df["success"] = res.success
    return df


def summarize_optimization(alloc: pd.DataFrame) -> dict:
    return dict(
        total_budget=float(alloc.optimized_spend.sum()),
        baseline_incremental_profit=float(alloc.baseline_incremental_profit.sum()),
        optimized_incremental_profit=float(alloc.optimized_incremental_profit.sum()),
        incremental_profit_gain=float(alloc.optimized_incremental_profit.sum() - alloc.baseline_incremental_profit.sum()),
        gain_pct=float((alloc.optimized_incremental_profit.sum() / max(alloc.baseline_incremental_profit.sum(), 1e-6) - 1) * 100),
        converged=bool(alloc.success.iloc[0]),
    )
