"""P&L construction, unit economics, and margin-driver decomposition."""
from __future__ import annotations
import numpy as np
import pandas as pd


def pnl_summary(monthly: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "month", "gmv", "discount_amount", "net_customer_spend",
        "commission_revenue", "delivery_fee_collected", "service_fee_revenue", "platform_revenue",
        "rider_cost", "payment_processing_cost", "promotion_cost", "refund_amount",
        "contribution_profit", "contribution_margin_pct",
    ]
    return monthly[cols].copy()


def unit_economics_by(orders: pd.DataFrame, dim_col: str, dim_lookup: pd.DataFrame | None = None) -> pd.DataFrame:
    delivered = orders[orders.order_status.isin(["Delivered", "Refunded"])]
    g = delivered.groupby(dim_col).agg(
        orders=("order_id", "count"),
        gmv=("gross_order_value", "sum"),
        revenue=("platform_revenue", "sum"),
        rider_cost=("rider_cost", "sum"),
        payment_processing_cost=("payment_processing_cost", "sum"),
        promotion_cost=("promotion_cost", "sum"),
        refund_amount=("refund_amount", "sum"),
        contribution_profit=("contribution_profit", "sum"),
        unique_customers=("customer_id", "nunique"),
    ).reset_index()
    g["aov"] = (g.gmv / g.orders).round(2)
    g["revenue_per_order"] = (g.revenue / g.orders).round(2)
    g["variable_cost_per_order"] = ((g.rider_cost + g.payment_processing_cost + g.promotion_cost + g.refund_amount) / g.orders).round(2)
    g["contribution_profit_per_order"] = (g.contribution_profit / g.orders).round(2)
    g["contribution_margin_pct"] = (g.contribution_profit / g.revenue.replace(0, np.nan)).round(4)
    g["orders_per_customer"] = (g.orders / g.unique_customers).round(2)
    if dim_lookup is not None:
        g = dim_lookup.merge(g, on=dim_col, how="left")
    return g


def cac_ltv_by_channel(customers_enriched: pd.DataFrame, cac_by_channel: dict) -> pd.DataFrame:
    g = customers_enriched.groupby("acquisition_channel").agg(
        customers=("customer_id", "count"),
        avg_lifetime_profit=("lifetime_profit", "mean"),
        avg_lifetime_gmv=("lifetime_gmv", "mean"),
        avg_orders=("total_orders", "mean"),
        churn_rate=("churn_flag", "mean"),
    ).reset_index()
    g["cac"] = g.acquisition_channel.map(cac_by_channel)
    g["ltv"] = g.avg_lifetime_profit.clip(lower=0)
    g["ltv_to_cac"] = (g.ltv / g.cac).round(2)
    g["payback_orders"] = np.where(g.avg_orders > 0, (g.cac / (g.avg_lifetime_profit / g.avg_orders).replace(0, np.nan)).round(1), np.nan)
    return g.sort_values("ltv_to_cac", ascending=False)


def margin_driver_decomposition(monthly: pd.DataFrame) -> pd.DataFrame:
    """Approximate decomposition of the change in contribution-margin % between
    the first and last full month, attributing the delta to named drivers using
    a first-order (linear) sensitivity approximation -- a standard, transparent
    approach for management-facing driver analysis (not a formal Shapley split)."""
    m = monthly.sort_values("month").reset_index(drop=True)
    start, end = m.iloc[0], m.iloc[-1]

    def rate(row, num, den):
        return row[num] / row[den] if row[den] else 0

    drivers = {}
    drivers["Discount rate (of GMV)"] = -(rate(end, "discount_amount", "gmv") - rate(start, "discount_amount", "gmv"))
    drivers["Rider cost rate (of revenue)"] = -(rate(end, "rider_cost", "platform_revenue") - rate(start, "rider_cost", "platform_revenue"))
    drivers["Payment processing rate"] = -(rate(end, "payment_processing_cost", "platform_revenue") - rate(start, "payment_processing_cost", "platform_revenue"))
    drivers["Refund rate"] = -(rate(end, "refund_amount", "platform_revenue") - rate(start, "refund_amount", "platform_revenue"))
    drivers["Revenue mix / take-rate"] = (rate(end, "platform_revenue", "gmv") - rate(start, "platform_revenue", "gmv"))

    df = pd.DataFrame({"driver": list(drivers.keys()), "approx_margin_pp_impact": [round(v * 100, 2) for v in drivers.values()]})
    df = df.sort_values("approx_margin_pp_impact")
    return df


def restaurant_quadrants(restaurant_summary: pd.DataFrame) -> pd.DataFrame:
    df = restaurant_summary.copy()
    df = df[df.total_orders > 0]
    rev_med = df.monthly_gmv.median()
    df["margin_pct"] = np.where(df.monthly_gmv > 0, df.contribution_profit / df.monthly_gmv, 0)
    margin_med = df.margin_pct.median()

    def quad(row):
        high_rev = row.monthly_gmv >= rev_med
        high_margin = row.margin_pct >= margin_med
        if high_rev and high_margin:
            return "Star: High Revenue / High Margin"
        if high_rev and not high_margin:
            return "Volume Trap: High Revenue / Low Margin"
        if not high_rev and high_margin:
            return "Niche Profit: Low Revenue / High Margin"
        return "Review: Low Revenue / Low Margin"

    df["quadrant"] = df.apply(quad, axis=1)
    return df
