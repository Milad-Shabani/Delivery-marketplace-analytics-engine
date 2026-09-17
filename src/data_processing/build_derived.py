"""Derive customer/restaurant/rider aggregates, segmentation, and monthly financials
from the raw orders table. Segmentation is rule-based on realized behavior
(recency/frequency/monetary + subscription), not random labels.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

CURRENT_DATE = pd.Timestamp("2026-08-31")


def enrich_customers(customers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    delivered = orders[orders.order_status.isin(["Delivered", "Refunded"])]
    agg = delivered.groupby("customer_id").agg(
        first_order_date=("order_date", "min"),
        last_order_date=("order_date", "max"),
        total_orders=("order_id", "count"),
        lifetime_gmv=("gross_order_value", "sum"),
        lifetime_revenue=("platform_revenue", "sum"),
        lifetime_profit=("contribution_profit", "sum"),
        avg_order_value=("gross_order_value", "mean"),
        total_discount=("discount_amount", "sum"),
    ).reset_index()

    df = customers.merge(agg, on="customer_id", how="left")
    df["total_orders"] = df.total_orders.fillna(0).astype(int)
    for col in ["lifetime_gmv", "lifetime_revenue", "lifetime_profit", "avg_order_value", "total_discount"]:
        df[col] = df[col].fillna(0.0)

    tenure_days = (CURRENT_DATE - df.signup_date).dt.days.clip(lower=1)
    df["average_order_frequency"] = (df.total_orders / (tenure_days / 30.0)).round(3)  # orders/month
    df["discount_dependency"] = np.where(df.lifetime_gmv > 0, (df.total_discount / df.lifetime_gmv).round(3), 0.0)
    recency_days = (CURRENT_DATE - df.last_order_date).dt.days
    df["recency_days"] = recency_days
    df["churn_flag"] = (df.total_orders > 0) & (recency_days > 60)

    # Rule-based segmentation
    def segment(row):
        if row.total_orders == 0:
            return "Never Ordered"
        if row.recency_days is not None and not np.isnan(row.recency_days) and row.recency_days > 90:
            return "Churned"
        if row.subscription_status == "Subscribed" and row.average_order_frequency >= 1.5:
            return "Subscription"
        if row.recency_days is not None and not np.isnan(row.recency_days) and 60 < row.recency_days <= 90:
            return "At Risk"
        if row.total_orders >= 15 and row.lifetime_profit >= row.lifetime_profit:  # placeholder, refined below
            pass
        if (CURRENT_DATE - row.signup_date).days <= 30:
            return "New"
        if row.discount_dependency >= 0.28:
            return "Price Sensitive"
        if row.lifetime_profit >= 25 and row.average_order_frequency >= 1.2:
            return "High Value"
        if row.average_order_frequency >= 0.8:
            return "Loyal"
        return "Occasional"

    df["customer_segment"] = df.apply(segment, axis=1)
    return df


def restaurant_daily_metrics(orders: pd.DataFrame) -> pd.DataFrame:
    g = orders.groupby(["restaurant_id", "order_date"]).agg(
        orders=("order_id", "count"),
        delivered_orders=("order_status", lambda s: (s == "Delivered").sum()),
        cancelled_orders=("order_status", lambda s: (s == "Cancelled").sum()),
        gmv=("gross_order_value", "sum"),
        commission_revenue=("restaurant_commission", "sum"),
        contribution_profit=("contribution_profit", "sum"),
        avg_prep_minutes=("estimated_delivery_minutes", "mean"),
        avg_rating=("rating", "mean"),
    ).reset_index()
    g["cancellation_rate"] = (g.cancelled_orders / g.orders).round(3)
    return g


def restaurant_summary(restaurants: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    delivered = orders[orders.order_status.isin(["Delivered", "Refunded"])]
    g = delivered.groupby("restaurant_id").agg(
        monthly_orders=("order_id", "count"),
        monthly_gmv=("gross_order_value", "sum"),
        monthly_revenue=("restaurant_commission", "sum"),
        contribution_profit=("contribution_profit", "sum"),
        avg_rating=("rating", "mean"),
        repeat_customers=("customer_id", lambda s: s.duplicated().sum()),
        unique_customers=("customer_id", "nunique"),
    ).reset_index()
    all_o = orders.groupby("restaurant_id").agg(
        total_orders=("order_id", "count"),
        cancelled=("order_status", lambda s: (s == "Cancelled").sum()),
    ).reset_index()
    g = g.merge(all_o, on="restaurant_id", how="right").fillna(0)
    n_months = orders.order_date.dt.to_period("M").nunique()
    g["monthly_orders"] = (g.monthly_orders / n_months).round(1)
    g["monthly_gmv"] = (g.monthly_gmv / n_months).round(2)
    g["cancellation_rate"] = (g.cancelled / g.total_orders.replace(0, np.nan)).fillna(0).round(3)
    g["repeat_customer_rate"] = (g.repeat_customers / g.unique_customers.replace(0, np.nan)).fillna(0).round(3)
    df = restaurants.merge(g, on="restaurant_id", how="left")
    return df


def rider_summary(riders: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    delivered = orders[orders.order_status == "Delivered"]
    g = delivered.groupby("rider_id").agg(
        orders_completed=("order_id", "count"),
        average_delivery_time=("actual_delivery_minutes", "mean"),
        average_distance=("delivery_distance_km", "mean"),
        on_time_rate=("delivery_delay_minutes", lambda s: (s <= 5).mean()),
    ).reset_index()
    all_o = orders.groupby("rider_id").agg(
        total_orders=("order_id", "count"),
        cancelled=("order_status", lambda s: (s == "Cancelled").sum()),
    ).reset_index()
    g = g.merge(all_o, on="rider_id", how="right").fillna(0)
    g["cancellation_rate"] = (g.cancelled / g.total_orders.replace(0, np.nan)).fillna(0).round(3)
    df = riders.merge(g, on="rider_id", how="left")
    return df


def monthly_financials(orders: pd.DataFrame) -> pd.DataFrame:
    o = orders.copy()
    o["month"] = o.order_date.dt.to_period("M").dt.to_timestamp()
    delivered = o[o.order_status.isin(["Delivered", "Refunded"])]

    g = o.groupby("month").agg(
        total_orders=("order_id", "count"),
        cancelled_orders=("order_status", lambda s: (s == "Cancelled").sum()),
    ).reset_index()

    d = delivered.groupby("month").agg(
        delivered_orders=("order_id", "count"),
        gmv=("gross_order_value", "sum"),
        food_value=("food_value", "sum"),
        discount_amount=("discount_amount", "sum"),
        commission_revenue=("restaurant_commission", "sum"),
        delivery_fee_collected=("delivery_fee", "sum"),
        service_fee_revenue=("service_fee", "sum"),
        platform_revenue=("platform_revenue", "sum"),
        rider_cost=("rider_cost", "sum"),
        payment_processing_cost=("payment_processing_cost", "sum"),
        promotion_cost=("promotion_cost", "sum"),
        refund_amount=("refund_amount", "sum"),
        contribution_profit=("contribution_profit", "sum"),
        active_customers=("customer_id", "nunique"),
        avg_delivery_minutes=("actual_delivery_minutes", "mean"),
        on_time_rate=("delivery_delay_minutes", lambda s: (s <= 5).mean()),
        avg_rating=("rating", "mean"),
    ).reset_index()

    m = g.merge(d, on="month", how="left").fillna(0)
    m["net_customer_spend"] = m.gmv - m.discount_amount
    m["aov"] = np.where(m.delivered_orders > 0, m.gmv / m.delivered_orders, 0)
    m["revenue_per_order"] = np.where(m.delivered_orders > 0, m.platform_revenue / m.delivered_orders, 0)
    m["contribution_margin_pct"] = np.where(m.platform_revenue > 0, m.contribution_profit / m.platform_revenue, 0)
    m["cancellation_rate"] = np.where(m.total_orders > 0, m.cancelled_orders / m.total_orders, 0)

    new_cust = orders[orders.new_customer_flag].groupby(orders.order_date.dt.to_period("M").dt.to_timestamp()).customer_id.nunique()
    m["new_customers"] = m.month.map(new_cust).fillna(0).astype(int)
    m["repeat_customers"] = (m.active_customers - m.new_customers).clip(lower=0)

    for col in ["gmv", "platform_revenue", "contribution_profit", "delivered_orders"]:
        m[f"{col}_growth_pct"] = m[col].pct_change().round(4)

    return m.sort_values("month").reset_index(drop=True)


def cohort_table(customers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    o = orders[orders.order_status.isin(["Delivered", "Refunded"])].copy()
    cust_cohort = customers.set_index("customer_id").signup_date.dt.to_period("M")
    o["cohort_month"] = o.customer_id.map(cust_cohort)
    o["order_month"] = o.order_date.dt.to_period("M")
    o["month_number"] = (o.order_month - o.cohort_month).apply(lambda x: x.n if pd.notna(x) else np.nan)
    o = o[(o.month_number >= 0) & (o.month_number <= 12)]

    cohort_sizes = customers.groupby(customers.signup_date.dt.to_period("M")).customer_id.nunique()

    g = o.groupby(["cohort_month", "month_number"]).agg(
        active_customers=("customer_id", "nunique"),
        revenue=("platform_revenue", "sum"),
        orders=("order_id", "count"),
        contribution_profit=("contribution_profit", "sum"),
    ).reset_index()
    g["cohort_size"] = g.cohort_month.map(cohort_sizes)
    g["retention_rate"] = (g.active_customers / g.cohort_size).round(4)
    g["cohort_month"] = g.cohort_month.dt.to_timestamp()
    return g


def rfm_table(customers_enriched: pd.DataFrame) -> pd.DataFrame:
    df = customers_enriched[customers_enriched.total_orders > 0].copy()
    df["r_score"] = pd.qcut(df.recency_days.rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    df["f_score"] = pd.qcut(df.total_orders.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    df["m_score"] = pd.qcut(df.lifetime_gmv.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    df["rfm_score"] = df.r_score + df.f_score + df.m_score
    return df[["customer_id", "recency_days", "total_orders", "lifetime_gmv", "r_score", "f_score", "m_score", "rfm_score"]]
