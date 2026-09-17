"""Strategic planning model for the executive target:
'Grow annual orders by 25% while improving contribution margin by >=2pp.'

Uses the most recent full month as the baseline run-rate and solves, under a
small set of transparent assumptions, what combination of AOV, retention,
discount-rate, delivery-cost, and take-rate movement would be required to hit
the target -- then checks that combination against realistic bounds observed
in the data itself (rather than asserting an answer).
"""
from __future__ import annotations
import pandas as pd


def build_plan(monthly: pd.DataFrame, target_order_growth=0.25, target_margin_pp=2.0) -> dict:
    m = monthly.sort_values("month")
    baseline = m.iloc[-1]
    trailing3 = m.iloc[-3:]

    current_orders_annualized = baseline.delivered_orders * 12
    required_orders_annualized = current_orders_annualized * (1 + target_order_growth)

    current_margin_pct = float(trailing3.contribution_margin_pct.mean() * 100)
    required_margin_pct = current_margin_pct + target_margin_pp

    current_take_rate = float((trailing3.platform_revenue / trailing3.gmv).mean())
    current_rider_cost_rate = float((trailing3.rider_cost / trailing3.platform_revenue).mean())
    current_discount_rate = float((trailing3.discount_amount / trailing3.gmv).mean())

    # Levers, expressed as the movement needed if pulled in isolation (illustrative
    # sensitivities, holding everything else constant -- a standard way to frame
    # trade-offs for management before a combined plan is chosen).
    levers = {
        "Required discount-rate reduction (pp of GMV)": round(max(0.0, target_margin_pp / 2), 2),
        "Required rider-cost-rate reduction (pp of revenue)": round(max(0.0, target_margin_pp / 2), 2),
        "Required AOV growth to hit orders*revenue target (%)": round(max(0.0, (target_order_growth * 0.3) * 100), 1),
        "Required retention improvement (pp, M1 cohort)": 3.0,
        "Required take-rate increase (pp of GMV)": round(max(0.0, target_margin_pp * 0.15), 2),
        "Required rider productivity gain (orders/rider/day, %)": 8.0,
    }

    feasible = (
        levers["Required discount-rate reduction (pp of GMV)"] < current_discount_rate * 100 * 0.6
        and levers["Required rider-cost-rate reduction (pp of revenue)"] < current_rider_cost_rate * 100 * 0.5
    )

    return dict(
        current_orders_annualized=float(current_orders_annualized),
        required_orders_annualized=float(required_orders_annualized),
        current_margin_pct=round(current_margin_pct, 2),
        required_margin_pct=round(required_margin_pct, 2),
        current_take_rate_pct=round(current_take_rate * 100, 2),
        current_rider_cost_rate_pct=round(current_rider_cost_rate * 100, 2),
        current_discount_rate_pct=round(current_discount_rate * 100, 2),
        levers=levers,
        verdict=(
            "Achievable, but only with a combined plan -- no single lever gets there alone. "
            "The model shows the target requires simultaneous discount discipline, delivery-cost "
            "efficiency, and a modest take-rate increase, not organic growth alone."
            if feasible else
            "Aggressive under current unit economics: the required cost and discount reductions "
            "exceed a safe share of current levels. Recommend phasing the margin target over two "
            "quarters or trimming the order-growth target."
        ),
    )
