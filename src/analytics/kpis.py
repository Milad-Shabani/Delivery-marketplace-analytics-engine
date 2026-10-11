"""Extended KPI layer (v2).

Everything here is a pure function of the generated tables -- no hardcoded
results. It produces:

* ``monthly_kpi_extension``  -- ~40 extra monthly KPI columns on top of
  ``monthly_financials`` (unit economics, customer health, operations,
  marketplace liquidity, marketing efficiency, YoY growth).
* ``build_scorecard``        -- the executive KPI scorecard (latest month vs.
  previous month, with a 12-month sparkline series per KPI).
* ``build_kpi_bundle``       -- every aggregate the dashboards need beyond the
  v1 payload (unit economics, customer deep-dive, operations, marketing),
  as a JSON-serializable dict.

Definitions (kept consistent with docs/financial_model.md):

* delivered orders      = Delivered + Refunded orders
* contribution profit   = platform revenue - rider - payment processing - 50% of refunds
  (this is the model's headline definition and it is *before* promotions)
* contribution after promotions = contribution profit - promotion cost
  (promotion cost = discount_amount, a platform-funded incentive)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from finance.finance import unit_economics_by

DELIVERED = ["Delivered", "Refunded"]
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def _num(x, n=2):
    if x is None or (isinstance(x, float) and np.isnan(x)) or pd.isna(x):
        return None
    return round(float(x), n)


def _list(values, n=2):
    return [_num(v, n) for v in values]


def _safe_div(a, b):
    return a / b.replace(0, np.nan) if isinstance(b, pd.Series) else (a / b if b else np.nan)


# ----------------------------------------------------------------------------
# monthly KPI extension
# ----------------------------------------------------------------------------

def monthly_kpi_extension(orders: pd.DataFrame, monthly: pd.DataFrame,
                          marketing_spend: pd.DataFrame, rider_shifts: pd.DataFrame,
                          customers: pd.DataFrame, cohorts: pd.DataFrame) -> pd.DataFrame:
    o = orders.copy()
    o["month"] = o.order_date.dt.to_period("M").dt.to_timestamp()
    d = o[o.order_status.isin(DELIVERED)]
    g = d.groupby("month")

    ext = pd.DataFrame({
        "refunded_orders": d.order_status.eq("Refunded").groupby(d.month).sum(),
        "promo_orders": d.discount_amount.gt(0).groupby(d.month).sum(),
        "weekend_orders": d.is_weekend.groupby(d.month).sum(),
        "subscriber_orders": d.subscription_customer_flag.groupby(d.month).sum(),
        "very_late_orders": d.delivery_delay_minutes.gt(15).groupby(d.month).sum(),
        "avg_delay_minutes": g.delivery_delay_minutes.mean(),
        "avg_distance_km": g.delivery_distance_km.mean(),
        "active_restaurants": g.restaurant_id.nunique(),
        "active_riders": g.rider_id.nunique(),
    }).reset_index()

    # "Activated new customers": signed up in the month AND placed a delivered order in it.
    signup_month = customers.set_index("customer_id").signup_date.dt.to_period("M").dt.to_timestamp()
    new_act = d[d.customer_id.map(signup_month) == d.month].groupby("month").customer_id.nunique()
    ext["activated_new_customers"] = ext.month.map(new_act).fillna(0).astype(int)

    # Month-1 retention: of the customers who signed up in month t-1, the share who ordered in month t.
    m1 = cohorts[cohorts.month_number == 1].set_index("cohort_month").retention_rate * 100
    ext["m1_retention_pct"] = (ext.month - pd.offsets.MonthBegin(1)).map(m1)

    m = monthly.merge(ext, on="month", how="left")

    mk = marketing_spend.groupby("month").agg(
        marketing_spend=("marketing_spend", "sum"), signups=("signups", "sum")).reset_index()
    rs = rider_shifts.groupby("month").agg(
        rider_online_hours=("online_hours", "sum"), rider_busy_hours=("busy_hours", "sum")).reset_index()
    m = m.merge(mk, on="month", how="left").merge(rs, on="month", how="left")

    n = m.delivered_orders.replace(0, np.nan)
    rev = m.platform_revenue.replace(0, np.nan)

    # profitability & unit economics
    m["take_rate_pct"] = m.platform_revenue / m.gmv.replace(0, np.nan) * 100
    m["contribution_profit_per_order"] = m.contribution_profit / n
    m["cost_to_serve_per_order"] = (m.platform_revenue - m.contribution_profit) / n
    m["rider_cost_per_order"] = m.rider_cost / n
    m["payment_cost_per_order"] = m.payment_processing_cost / n
    m["delivery_fee_coverage_pct"] = m.delivery_fee_collected / m.rider_cost.replace(0, np.nan) * 100
    m["promotion_cost_per_order"] = m.promotion_cost / n
    m["promotion_cost_pct_revenue"] = m.promotion_cost / rev * 100
    m["discount_rate_pct"] = m.discount_amount / m.gmv.replace(0, np.nan) * 100
    m["promo_order_share_pct"] = m.promo_orders / n * 100
    m["contribution_after_promo"] = m.contribution_profit - m.promotion_cost
    m["contribution_after_promo_margin_pct"] = m.contribution_after_promo / rev * 100

    # customers
    m["orders_per_active_customer"] = m.delivered_orders / m.active_customers.replace(0, np.nan)
    m["returning_customers"] = (m.active_customers - m.activated_new_customers).clip(lower=0)
    m["new_customer_share_pct"] = m.activated_new_customers / m.active_customers.replace(0, np.nan) * 100
    m["subscriber_order_share_pct"] = m.subscriber_orders / n * 100

    # operations
    m["on_time_rate_pct"] = m.on_time_rate * 100
    m["cancellation_rate_pct"] = m.cancellation_rate * 100
    m["very_late_rate_pct"] = m.very_late_orders / n * 100
    m["refund_rate_pct"] = m.refunded_orders / n * 100
    m["weekend_share_pct"] = m.weekend_orders / n * 100

    # marketplace liquidity
    m["orders_per_restaurant"] = m.delivered_orders / m.active_restaurants.replace(0, np.nan)
    m["rider_utilization_pct"] = m.rider_busy_hours / m.rider_online_hours.replace(0, np.nan) * 100
    m["orders_per_rider_hour"] = m.delivered_orders / m.rider_online_hours.replace(0, np.nan)

    # marketing efficiency
    m["blended_cac"] = m.marketing_spend / m.signups.replace(0, np.nan)
    m["marketing_pct_revenue"] = m.marketing_spend / rev * 100

    # trailing-3-month versions of the sign-up-driven KPIs. Customer sign-ups are generated
    # over a fixed 510-day window, so the final reporting month only holds ~22 days of sign-ups;
    # 3-month windows keep those KPIs from showing a spurious month-over-month cliff.
    roll = lambda c: m[c].rolling(3).sum()
    m["activated_new_customers_t3"] = m.activated_new_customers.rolling(3).mean()
    m["new_customer_share_pct_t3"] = roll("activated_new_customers") / roll("active_customers") * 100
    m["marketing_spend_t3"] = m.marketing_spend.rolling(3).mean()
    m["blended_cac_t3"] = roll("marketing_spend") / roll("signups").replace(0, np.nan)
    m["marketing_pct_revenue_t3"] = roll("marketing_spend") / roll("platform_revenue").replace(0, np.nan) * 100

    # year-over-year (only defined once 12 months of history exist)
    m["gmv_yoy_pct"] = (m.gmv / m.gmv.shift(12) - 1) * 100
    m["orders_yoy_pct"] = (m.delivered_orders / m.delivered_orders.shift(12) - 1) * 100
    return m.sort_values("month").reset_index(drop=True)


# ----------------------------------------------------------------------------
# executive scorecard
# ----------------------------------------------------------------------------

# (kpi key, source column, scale, format, "up"/"down"/"neutral" = which move is good, delta kind[, window])
# window "3M" = trailing-3-month value compared with the same measure one month earlier.
SCORECARD_SPEC = [
    ("growth", [
        ("gmv", "gmv", 1, "money0", "up", "pct"),
        ("gmv_yoy", "gmv_yoy_pct", 1, "pct1", "up", "pp"),
        ("delivered_orders", "delivered_orders", 1, "int", "up", "pct"),
        ("active_customers", "active_customers", 1, "int", "up", "pct"),
        ("orders_per_active_customer", "orders_per_active_customer", 1, "dec2", "up", "pct"),
    ]),
    ("profitability", [
        ("platform_revenue", "platform_revenue", 1, "money0", "up", "pct"),
        ("take_rate", "take_rate_pct", 1, "pct1", "neutral", "pp"),
        ("contribution_profit", "contribution_profit", 1, "money0", "up", "pct"),
        ("contribution_margin", "contribution_margin_pct", 100, "pct1", "up", "pp"),
        ("contribution_per_order", "contribution_profit_per_order", 1, "money2", "up", "pct"),
    ]),
    ("unit_economics", [
        ("aov", "aov", 1, "money2", "up", "pct"),
        ("revenue_per_order", "revenue_per_order", 1, "money2", "up", "pct"),
        ("cost_to_serve", "cost_to_serve_per_order", 1, "money2", "down", "pct"),
        ("delivery_fee_coverage", "delivery_fee_coverage_pct", 1, "pct1", "up", "pp"),
        ("promotion_burden", "promotion_cost_pct_revenue", 1, "pct1", "down", "pp"),
    ]),
    ("customers", [
        ("new_customers", "activated_new_customers_t3", 1, "int", "up", "pct", "3M"),
        ("new_share", "new_customer_share_pct_t3", 1, "pct1", "neutral", "pp", "3M"),
        ("m1_retention", "m1_retention_pct", 1, "pct1", "up", "pp"),
        ("subscriber_share", "subscriber_order_share_pct", 1, "pct1", "up", "pp"),
    ]),
    ("operations", [
        ("on_time_rate", "on_time_rate", 100, "pct1", "up", "pp"),
        ("avg_delivery_minutes", "avg_delivery_minutes", 1, "min1", "down", "pct"),
        ("very_late_rate", "very_late_rate_pct", 1, "pct1", "down", "pp"),
        ("cancellation_rate", "cancellation_rate", 100, "pct1", "down", "pp"),
        ("refund_rate", "refund_rate_pct", 1, "pct1", "down", "pp"),
        ("avg_rating", "avg_rating", 1, "dec2", "up", "pct"),
    ]),
    ("marketplace", [
        ("active_restaurants", "active_restaurants", 1, "int", "up", "pct"),
        ("orders_per_restaurant", "orders_per_restaurant", 1, "dec1", "up", "pct"),
        ("active_riders", "active_riders", 1, "int", "neutral", "pct"),
        ("rider_utilization", "rider_utilization_pct", 1, "pct1", "up", "pp"),
        ("orders_per_rider_hour", "orders_per_rider_hour", 1, "dec2", "up", "pct"),
    ]),
    ("marketing", [
        ("marketing_spend", "marketing_spend_t3", 1, "money0", "neutral", "pct", "3M"),
        ("blended_cac", "blended_cac_t3", 1, "money2", "down", "pct", "3M"),
        ("marketing_pct_revenue", "marketing_pct_revenue_t3", 1, "pct1", "down", "pp", "3M"),
        ("discount_rate", "discount_rate_pct", 1, "pct1", "down", "pp"),
    ]),
]


def build_scorecard(mx: pd.DataFrame, spark_months: int = 12) -> dict:
    """Latest month vs. previous month for every KPI, plus a sparkline series."""
    last, prev = mx.iloc[-1], mx.iloc[-2]
    groups = []
    for gkey, items in SCORECARD_SPEC:
        out = []
        for key, col, scale, fmt, good, kind, *rest in items:
            window = rest[0] if rest else "1M"
            v, p = last[col] * scale, prev[col] * scale
            if pd.isna(v) or pd.isna(p):
                delta = None
            elif kind == "pp":
                delta = v - p
            else:
                delta = (v / p - 1) * 100 if p else None
            spark = (mx[col] * scale).tail(spark_months).tolist()
            out.append({
                "key": key, "value": _num(v, 3), "prev": _num(p, 3), "delta": _num(delta, 2),
                "delta_kind": kind, "fmt": fmt, "good": good, "window": window, "spark": _list(spark, 3),
            })
        groups.append({"key": gkey, "items": out})
    return {
        "as_of": last["month"].strftime("%Y-%m"),
        "prev": prev["month"].strftime("%Y-%m"),
        "groups": groups,
    }


# ----------------------------------------------------------------------------
# bundle of dashboard aggregates
# ----------------------------------------------------------------------------

def _unit_econ_table(df: pd.DataFrame, key: str) -> dict:
    ue = unit_economics_by(df, key)
    ue["payment_cost_per_order"] = (ue.payment_processing_cost / ue.orders).round(2)
    ue["promotion_cost_per_order"] = (ue.promotion_cost / ue.orders).round(2)
    ue = ue.sort_values("orders", ascending=False)
    rating = df[df.order_status == "Delivered"].groupby(key).rating.mean()
    return {
        "names": ue[key].astype(str).tolist(),
        "orders": ue.orders.astype(int).tolist(),
        "order_share_pct": _list(ue.orders / ue.orders.sum() * 100, 1),
        "gmv": _list(ue.gmv, 0),
        "aov": _list(ue.aov, 2),
        "revenue_per_order": _list(ue.revenue_per_order, 2),
        "contribution_profit_per_order": _list(ue.contribution_profit_per_order, 2),
        "contribution_margin_pct": _list(ue.contribution_margin_pct * 100, 1),
        "payment_cost_per_order": _list(ue.payment_cost_per_order, 2),
        "promotion_cost_per_order": _list(ue.promotion_cost_per_order, 2),
        "avg_rating": _list(ue[key].map(rating), 2),
    }


def build_kpi_bundle(data, cust_enriched: pd.DataFrame, mx: pd.DataFrame, cac_ltv: pd.DataFrame,
                     cac_assumed: dict) -> dict:
    orders = data.orders
    delivered = orders[orders.order_status.isin(DELIVERED)].copy()
    months = mx.month.dt.strftime("%Y-%m").tolist()
    last3 = mx.tail(3)

    # ---- monthly series for the new KPIs -------------------------------------------------
    monthly_cols = [
        "take_rate_pct", "contribution_profit_per_order", "revenue_per_order", "cost_to_serve_per_order",
        "rider_cost_per_order", "payment_cost_per_order", "delivery_fee_coverage_pct",
        "promotion_cost_per_order", "promotion_cost_pct_revenue", "discount_rate_pct", "promo_order_share_pct",
        "contribution_after_promo", "contribution_after_promo_margin_pct",
        "orders_per_active_customer", "new_customer_share_pct", "m1_retention_pct", "activated_new_customers", "returning_customers",
        "subscriber_order_share_pct", "on_time_rate_pct", "cancellation_rate_pct", "very_late_rate_pct",
        "refund_rate_pct", "weekend_share_pct", "avg_delivery_minutes", "avg_delay_minutes", "avg_distance_km",
        "avg_rating", "active_restaurants", "active_riders", "orders_per_restaurant", "rider_online_hours",
        "rider_utilization_pct", "orders_per_rider_hour", "marketing_spend", "blended_cac",
        "marketing_pct_revenue", "signups", "gmv_yoy_pct", "orders_yoy_pct",
    ]
    monthly_ext = {"months": months}
    for c in monthly_cols:
        monthly_ext[c] = _list(mx[c], 3)

    # ---- per-order unit-economics waterfall (trailing 3 months) ------------------------------
    n3 = last3.delivered_orders.sum()
    wf = {
        "revenue": last3.platform_revenue.sum() / n3,
        "rider": -last3.rider_cost.sum() / n3,
        "payment": -last3.payment_processing_cost.sum() / n3,
        "refund": -0.5 * last3.refund_amount.sum() / n3,
        "promotion": -last3.promotion_cost.sum() / n3,
    }
    contribution = wf["revenue"] + wf["rider"] + wf["payment"] + wf["refund"]
    unit_econ = {
        "window": f"{last3.month.iloc[0].strftime('%Y-%m')} to {last3.month.iloc[-1].strftime('%Y-%m')}",
        "waterfall": {
            "revenue_per_order": _num(wf["revenue"], 2), "rider_cost": _num(wf["rider"], 2),
            "payment_cost": _num(wf["payment"], 2), "refund_cost": _num(wf["refund"], 2),
            "contribution_per_order": _num(contribution, 2),
            "promotion_cost": _num(wf["promotion"], 2),
            "contribution_after_promo_per_order": _num(contribution + wf["promotion"], 2),
            "aov": _num(last3.gmv.sum() / n3, 2),
        },
        "by_cuisine": _unit_econ_table(delivered.merge(data.restaurants[["restaurant_id", "cuisine"]], on="restaurant_id"), "cuisine"),
        "by_tier": _unit_econ_table(delivered.merge(data.restaurants[["restaurant_id", "restaurant_tier"]], on="restaurant_id"), "restaurant_tier"),
        "by_payment": _unit_econ_table(delivered, "payment_method"),
    }
    refunds = delivered.assign(refunded=delivered.order_status.eq("Refunded")).groupby("payment_method").refunded.mean()
    unit_econ["by_payment"]["refund_rate_pct"] = _list(pd.Series(unit_econ["by_payment"]["names"]).map(refunds) * 100, 1)

    # ---- customers deep-dive -------------------------------------------------------------------
    ce = cust_enriched
    ordered = ce[ce.total_orders > 0]
    sub = ordered.groupby("subscription_status").agg(
        customers=("customer_id", "count"),
        orders=("total_orders", "sum"),
        gmv=("lifetime_gmv", "sum"),
        profit=("lifetime_profit", "sum"),
        discount=("total_discount", "sum"),
        freq=("average_order_frequency", "mean"),
        churn=("churn_flag", "mean"),
    ).reindex(["Subscribed", "Not Subscribed"])
    subscription = {
        "names": sub.index.tolist(),
        "customers": sub.customers.astype(int).tolist(),
        "orders_per_customer": _list(sub.orders / sub.customers, 2),
        "orders_per_month": _list(sub.freq, 2),
        "aov": _list(sub.gmv / sub.orders, 2),
        "contribution_per_order": _list(sub.profit / sub.orders, 2),
        "lifetime_profit_per_customer": _list(sub.profit / sub.customers, 2),
        "discount_dependency_pct": _list(sub.discount / sub.gmv * 100, 1),
        "churn_rate_pct": _list(sub.churn * 100, 1),
    }

    ranked = ordered.sort_values("lifetime_gmv", ascending=False).lifetime_gmv.reset_index(drop=True)
    cum = ranked.cumsum() / ranked.sum()
    xs = list(range(0, 101, 5))
    ys = [0.0] + [float(cum.iloc[max(int(np.ceil(len(ranked) * x / 100)) - 1, 0)] * 100) for x in xs[1:]]
    concentration = {
        "x_pct_customers": xs, "y_pct_gmv": _list(ys, 1),
        "top10_share_pct": _num(cum.iloc[max(int(np.ceil(len(ranked) * 0.10)) - 1, 0)] * 100, 1),
        "top20_share_pct": _num(cum.iloc[max(int(np.ceil(len(ranked) * 0.20)) - 1, 0)] * 100, 1),
        "customers_ranked": int(len(ranked)),
    }

    seg = ce[ce.total_orders > 0].groupby("customer_segment").agg(
        customers=("customer_id", "count"), orders=("total_orders", "sum"),
        gmv=("lifetime_gmv", "sum"), profit=("lifetime_profit", "sum"),
        discount=("total_discount", "sum"), freq=("average_order_frequency", "mean"),
    ).sort_values("profit", ascending=False)
    segment_profile = {
        "names": seg.index.tolist(),
        "customers": seg.customers.astype(int).tolist(),
        "profit_share_pct": _list(seg.profit / seg.profit.sum() * 100, 1),
        "orders_per_customer": _list(seg.orders / seg.customers, 2),
        "aov": _list(seg.gmv / seg.orders, 2),
        "contribution_per_order": _list(seg.profit / seg.orders, 2),
        "discount_dependency_pct": _list(seg.discount / seg.gmv * 100, 1),
    }

    seg_all = ce.customer_segment.value_counts()
    snapshot = {
        "customers_total": int(len(ce)),
        "customers_ordered": int(len(ordered)),
        "never_ordered_pct": _num((ce.total_orders == 0).mean() * 100, 1),
        "active_60d_pct": _num((ordered.recency_days <= 60).mean() * 100, 1),
        "at_risk_pct": _num(seg_all.get("At Risk", 0) / len(ordered) * 100, 1),
        "churned_pct": _num(seg_all.get("Churned", 0) / len(ordered) * 100, 1),
        "avg_orders_per_customer": _num(ordered.total_orders.mean(), 1),
        "avg_lifetime_gmv": _num(ordered.lifetime_gmv.mean(), 1),
        "avg_lifetime_profit": _num(ordered.lifetime_profit.mean(), 2),
        "subscriber_customer_share_pct": _num((ordered.subscription_status == "Subscribed").mean() * 100, 1),
    }

    # ---- restaurants / supply ------------------------------------------------------------------
    rest = delivered.groupby("restaurant_id").gross_order_value.sum().sort_values(ascending=False)
    rest_cum = rest.cumsum() / rest.sum()
    restaurants_ext = {
        "top10_share_pct": _num(rest.head(10).sum() / rest.sum() * 100, 1),
        "top20pct_share_pct": _num(rest_cum.iloc[max(int(np.ceil(len(rest) * 0.20)) - 1, 0)] * 100, 1),
        "restaurants_with_orders": int(len(rest)),
        "avg_rating": _num(delivered.rating.mean(), 2),
    }

    # ---- operations ----------------------------------------------------------------------------
    d = delivered.copy()
    n_days = pd.Series(pd.date_range(orders.order_date.min(), orders.order_date.max(), freq="D")).dt.dayofweek.value_counts()
    cnt = d.groupby(["day_of_week", "order_hour"]).size().unstack(fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0)
    heat = cnt.div(n_days.reindex(range(7)).values, axis=0)
    hour_share = d.groupby("order_hour").size() / len(d) * 100
    peak_hours = hour_share.sort_values(ascending=False).head(3).index.tolist()

    reasons = orders[orders.order_status == "Cancelled"].cancellation_reason.value_counts()
    cancel_reasons = {
        "names": reasons.index.tolist(), "orders": reasons.astype(int).tolist(),
        "share_pct": _list(reasons / reasons.sum() * 100, 1),
        "per_100_orders": _list(reasons / len(orders) * 100, 2),
    }

    city_names = data.cities.set_index("city_id").city_name
    oc = orders.groupby("city_id").agg(total=("order_id", "count"), cancelled=("order_status", lambda s: (s == "Cancelled").sum()))
    dc = d.groupby("city_id").agg(
        orders=("order_id", "count"), gmv=("gross_order_value", "sum"), revenue=("platform_revenue", "sum"),
        profit=("contribution_profit", "sum"), rider_cost=("rider_cost", "sum"),
        avg_delivery=("actual_delivery_minutes", "mean"), avg_delay=("delivery_delay_minutes", "mean"),
        on_time=("delivery_delay_minutes", lambda s: (s <= 5).mean()), rating=("rating", "mean"),
        distance=("delivery_distance_km", "mean"),
    )
    city = dc.join(oc).sort_values("orders", ascending=False)
    city_scorecard = {
        "names": city.index.map(city_names).tolist(),
        "orders": city.orders.astype(int).tolist(),
        "share_pct": _list(city.orders / city.orders.sum() * 100, 1),
        "aov": _list(city.gmv / city.orders, 2),
        "on_time_pct": _list(city.on_time * 100, 1),
        "avg_delivery_minutes": _list(city.avg_delivery, 1),
        "avg_delay_minutes": _list(city.avg_delay, 1),
        "cancellation_rate_pct": _list(city.cancelled / city.total * 100, 2),
        "avg_rating": _list(city.rating, 2),
        "rider_cost_per_order": _list(city.rider_cost / city.orders, 2),
        "avg_distance_km": _list(city.distance, 2),
        "contribution_per_order": _list(city.profit / city.orders, 2),
        "contribution_margin_pct": _list(city.profit / city.revenue * 100, 1),
    }

    riders_v = data.riders.set_index("rider_id").vehicle_type
    d["vehicle_type"] = d.rider_id.map(riders_v)
    veh = d.groupby("vehicle_type").agg(
        orders=("order_id", "count"), rider_cost=("rider_cost", "sum"), distance=("delivery_distance_km", "sum"),
        avg_delivery=("actual_delivery_minutes", "mean"), on_time=("delivery_delay_minutes", lambda s: (s <= 5).mean()),
    ).sort_values("orders", ascending=False)
    shifts = data.rider_shifts.groupby("vehicle_type").agg(busy=("busy_hours", "sum"), online=("online_hours", "sum"),
                                                          riders=("rider_id", "nunique"))
    vehicle = {
        "names": veh.index.tolist(), "orders": veh.orders.astype(int).tolist(),
        "share_pct": _list(veh.orders / veh.orders.sum() * 100, 1),
        "rider_cost_per_order": _list(veh.rider_cost / veh.orders, 2),
        "rider_cost_per_km": _list(veh.rider_cost / veh.distance, 2),
        "avg_delivery_minutes": _list(veh.avg_delivery, 1),
        "on_time_pct": _list(veh.on_time * 100, 1),
        "utilization_pct": _list(veh.index.map(shifts.busy / shifts.online * 100), 1),
        "riders": [int(shifts.riders.get(v, 0)) for v in veh.index],
    }

    rated = d[d.rating.notna()].copy()
    buckets = pd.cut(rated.delivery_delay_minutes, [-np.inf, 0, 5, 10, 20, np.inf],
                     labels=["On time or early", "1-5 min late", "5-10 min late", "10-20 min late", "20+ min late"])
    dr = rated.groupby(buckets, observed=False).rating.agg(["mean", "count"])
    delay_rating = {
        "buckets": dr.index.astype(str).tolist(), "avg_rating": _list(dr["mean"], 2),
        "order_share_pct": _list(dr["count"] / dr["count"].sum() * 100, 1),
    }

    ops = {
        "heatmap": {"days": DAY_NAMES, "hours": list(range(24)), "z": [_list(r, 2) for r in heat.values]},
        "peak_hours": [int(h) for h in peak_hours],
        "peak_3h_share_pct": _num(hour_share.loc[peak_hours].sum(), 1),
        "weekend_share_pct": _num(d.is_weekend.mean() * 100, 1),
        "holiday_lift_pct": _num((d[d.is_holiday].groupby("order_date").size().mean() /
                                  d[~d.is_holiday].groupby("order_date").size().mean() - 1) * 100, 1),
        "cancel_reasons": cancel_reasons,
        "city_scorecard": city_scorecard,
        "vehicle": vehicle,
        "delay_rating": delay_rating,
        "avg_distance_km": _num(d.delivery_distance_km.mean(), 2),
        "avg_eta_error_minutes": _num(d.delivery_delay_minutes.abs().mean(), 1),
    }

    # ---- marketing & promotions ---------------------------------------------------------------
    ms = data.marketing_spend
    channels = [c for c in cac_assumed if c in set(ms.acquisition_channel)]
    spend_piv = ms.pivot_table(index="month", columns="acquisition_channel", values="marketing_spend", aggfunc="sum").reindex(columns=channels)
    sign_piv = ms.pivot_table(index="month", columns="acquisition_channel", values="signups", aggfunc="sum").reindex(columns=channels)
    obs = ms.groupby("acquisition_channel").agg(spend=("marketing_spend", "sum"), signups=("signups", "sum")).reindex(channels)
    obs["observed_cac"] = obs.spend / obs.signups.replace(0, np.nan)
    latest = ms[ms.month >= ms.month.max() - pd.offsets.MonthBegin(2)].groupby("acquisition_channel").agg(
        spend=("marketing_spend", "sum"), signups=("signups", "sum")).reindex(channels)
    latest["cac"] = latest.spend / latest.signups.replace(0, np.nan)
    ltv = cac_ltv.set_index("acquisition_channel").ltv.reindex(channels)

    marketing = {
        "months": spend_piv.index.strftime("%Y-%m").tolist(),
        "channels": channels,
        "spend_by_channel": {c: _list(spend_piv[c], 0) for c in channels},
        "signups_by_channel": {c: [int(v) for v in sign_piv[c]] for c in channels},
        "cac_assumed": {c: cac_assumed[c] for c in channels},
        "cac_observed_period": {c: _num(obs.observed_cac[c], 2) for c in channels},
        "cac_observed_latest_3m": {c: _num(latest.cac[c], 2) for c in channels},
        "ltv": {c: _num(ltv[c], 2) for c in channels},
        "ltv_to_cac_observed": {c: _num(ltv[c] / latest.cac[c], 2) if latest.cac[c] else None for c in channels},
        "total_spend_period": _num(ms.marketing_spend.sum(), 0),
        "total_signups_period": int(ms.signups.sum()),
        "paid_share_of_spend_pct": _num(ms[ms.acquisition_channel.isin(["Paid Social", "Paid Search"])].marketing_spend.sum()
                                         / ms.marketing_spend.sum() * 100, 1),
    }

    d["has_promo"] = d.discount_amount > 0
    pr = d.groupby("has_promo").agg(
        orders=("order_id", "count"), gmv=("gross_order_value", "sum"), revenue=("platform_revenue", "sum"),
        profit=("contribution_profit", "sum"), discount=("discount_amount", "sum"), food=("food_value", "sum"),
    ).reindex([True, False])
    promo = {
        "names": ["With discount", "No discount"],
        "order_share_pct": _list(pr.orders / pr.orders.sum() * 100, 1),
        "aov": _list(pr.gmv / pr.orders, 2),
        "revenue_per_order": _list(pr.revenue / pr.orders, 2),
        "contribution_per_order": _list(pr.profit / pr.orders, 2),
        "promotion_cost_per_order": _list(pr.discount / pr.orders, 2),
        "contribution_after_promo_per_order": _list((pr.profit - pr.discount) / pr.orders, 2),
        "avg_discount_pct_of_food": _num(pr.discount.iloc[0] / pr.food.iloc[0] * 100, 1),
    }
    marketing["promo"] = promo

    return {
        "monthly_ext": monthly_ext,
        "unit_econ": unit_econ,
        "customers_ext": {"subscription": subscription, "concentration": concentration,
                          "segment_profile": segment_profile, "snapshot": snapshot},
        "restaurants_ext": restaurants_ext,
        "ops": ops,
        "marketing": marketing,
    }
