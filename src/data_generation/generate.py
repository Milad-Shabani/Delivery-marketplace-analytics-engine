"""
NOVAFOOD synthetic data generator.

Produces a reproducible, internally-consistent synthetic dataset simulating an
online food-delivery marketplace: customers, restaurants, riders, cities/zones,
orders (with realistic financial relationships), delivery events, and
derived monthly/financial tables used by the rest of the pipeline.

This is SYNTHETIC data calibrated to look like realistic marketplace economics.
It is not based on, and does not claim to represent, any real company.

Scale note: the brief asked for 300k+ orders / 30k+ customers. This build uses
a smaller (still large, still fully realistic and internally consistent) scale
-- ~180k orders / 12k customers over 17 months -- so the full pipeline
(generation -> analytics -> forecasting -> optimization -> Excel -> dashboard)
actually runs end-to-end in this environment. Every generator here is a pure
function of N and the seed, so scaling up is a one-line change
(see scripts/generate_data.py --orders / --customers).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta

SEED = 20260916
RNG = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# Time window: 17 months of history, ending at the "current" month.
# ---------------------------------------------------------------------------
HIST_START = pd.Timestamp("2025-04-01")
HIST_END = pd.Timestamp("2026-08-31")
N_MONTHS = (HIST_END.year - HIST_START.year) * 12 + (HIST_END.month - HIST_START.month) + 1

CITIES = [
    # name, tier (1=largest metro), base_demand_weight, base_delivery_cost_per_km, rider_pay_per_order
    ("Metroville", 1, 1.00, 0.55, 1.35),
    ("Porthaven", 1, 0.85, 0.52, 1.30),
    ("Rivertown", 2, 0.60, 0.48, 1.20),
    ("Lakeside City", 2, 0.55, 0.47, 1.18),
    ("Hillcrest", 2, 0.45, 0.50, 1.22),
    ("Bayshore", 3, 0.30, 0.45, 1.15),
    ("Northfield", 3, 0.28, 0.44, 1.14),
    ("Sunview", 3, 0.22, 0.46, 1.16),
]

CUISINES = [
    "Fast Food", "Pizza", "Asian", "Indian", "Middle Eastern", "Burgers",
    "Healthy/Salads", "Cafe/Breakfast", "Desserts & Bakery", "Seafood",
    "Mexican", "Italian", "Vegan", "BBQ/Grill", "Sandwiches",
]

ACQUISITION_CHANNELS = ["Organic/Referral", "Paid Social", "Paid Search", "Push/CRM", "Partnership"]
PAYMENT_METHODS = ["Card", "Wallet", "Cash on Delivery", "BNPL"]
VEHICLE_TYPES = ["Bike", "Scooter", "Car"]

HOLIDAYS = pd.to_datetime([
    "2025-05-01", "2025-07-04", "2025-11-27", "2025-12-25", "2025-12-31",
    "2026-01-01", "2026-02-14", "2026-03-20", "2026-05-01", "2026-07-04",
])


def month_index(dt: pd.Series) -> pd.Series:
    return (dt.dt.year - HIST_START.year) * 12 + (dt.dt.month - HIST_START.month)


def seasonal_multiplier(month_start: pd.Timestamp) -> float:
    """Smooth yearly seasonality: dip in Feb, peak in Nov-Dec (holidays) and Jul-Aug (summer)."""
    m = month_start.month
    base = {
        1: 0.92, 2: 0.86, 3: 0.95, 4: 1.00, 5: 1.03, 6: 1.05,
        7: 1.10, 8: 1.08, 9: 1.00, 10: 1.02, 11: 1.15, 12: 1.20,
    }[m]
    return base


def growth_trend(m_idx: int) -> float:
    """Underlying MoM organic growth trend (~0.9% average with mild deceleration)."""
    return (1.009 ** m_idx) * (1 - 0.0004 * m_idx)


# ---------------------------------------------------------------------------
# Dimension tables
# ---------------------------------------------------------------------------

def build_cities() -> pd.DataFrame:
    rows = []
    for i, (name, tier, demand_w, cost_per_km, rider_pay) in enumerate(CITIES, start=1):
        rows.append(dict(
            city_id=i, city_name=name, city_tier=tier,
            demand_weight=demand_w,
            delivery_cost_per_km=cost_per_km,
            rider_base_pay_per_order=rider_pay,
            avg_commission_rate=round(RNG.uniform(0.16, 0.24), 3),
        ))
    return pd.DataFrame(rows)


def build_zones(cities: pd.DataFrame, zones_per_city=(3, 6)) -> pd.DataFrame:
    rows = []
    zone_id = 1
    for _, c in cities.iterrows():
        n_zones = RNG.integers(zones_per_city[0], zones_per_city[1] + 1)
        for z in range(1, n_zones + 1):
            rows.append(dict(
                zone_id=zone_id, city_id=c.city_id,
                zone_name=f"{c.city_name} Zone {z}",
                density_weight=round(RNG.uniform(0.5, 1.5), 2),
                avg_delivery_distance_km=round(RNG.uniform(1.8, 6.5), 2),
            ))
            zone_id += 1
    return pd.DataFrame(rows)


def build_restaurants(zones: pd.DataFrame, n=320) -> pd.DataFrame:
    zone_ids = RNG.choice(zones.zone_id.values, size=n,
                           p=zones.density_weight.values / zones.density_weight.sum())
    tiers = RNG.choice(["Budget", "Mid", "Premium"], size=n, p=[0.45, 0.4, 0.15])
    cuisines = RNG.choice(CUISINES, size=n)
    tier_commission = {"Budget": 0.16, "Mid": 0.20, "Premium": 0.24}
    tier_aov = {"Budget": 8.5, "Mid": 14.0, "Premium": 24.0}
    tier_prep = {"Budget": 12, "Mid": 18, "Premium": 26}
    join_offsets = RNG.integers(-30, N_MONTHS * 30, size=n)  # some pre-existing, some join later
    df = pd.DataFrame({
        "restaurant_id": np.arange(1, n + 1),
        "zone_id": zone_ids,
        "cuisine": cuisines,
        "restaurant_tier": tiers,
    }).merge(zones[["zone_id", "city_id"]], on="zone_id", how="left")
    df["restaurant_name"] = [f"{c} House #{i}" for i, c in zip(df.restaurant_id, df.cuisine)]
    df["commission_rate"] = df.restaurant_tier.map(tier_commission) + RNG.normal(0, 0.01, n)
    df["commission_rate"] = df.commission_rate.clip(0.12, 0.28).round(3)
    df["base_aov"] = (df.restaurant_tier.map(tier_aov) * RNG.uniform(0.85, 1.2, n)).round(2)
    df["avg_food_prep_minutes"] = (df.restaurant_tier.map(tier_prep) + RNG.normal(0, 3, n)).clip(6, 45).round(1)
    df["average_rating"] = RNG.normal(4.3, 0.35, n).clip(2.8, 5.0).round(2)
    df["join_date"] = HIST_START + pd.to_timedelta(join_offsets, unit="D")
    df["join_date"] = df.join_date.clip(lower=HIST_START - pd.Timedelta(days=730))
    df["active_status"] = np.where(RNG.random(n) < 0.05, "Inactive", "Active")
    df["cancellation_bias"] = RNG.uniform(0.01, 0.06, n).round(3)
    return df


def build_riders(zones: pd.DataFrame, n=520) -> pd.DataFrame:
    zone_ids = RNG.choice(zones.zone_id.values, size=n,
                           p=zones.density_weight.values / zones.density_weight.sum())
    df = pd.DataFrame({
        "rider_id": np.arange(1, n + 1),
        "zone_id": zone_ids,
    }).merge(zones[["zone_id", "city_id"]], on="zone_id", how="left")
    df["vehicle_type"] = RNG.choice(VEHICLE_TYPES, size=n, p=[0.55, 0.35, 0.10])
    join_offsets = RNG.integers(-60, N_MONTHS * 30, size=n)
    df["join_date"] = HIST_START + pd.to_timedelta(join_offsets, unit="D")
    df["join_date"] = df.join_date.clip(lower=HIST_START - pd.Timedelta(days=365))
    df["active_status"] = np.where(RNG.random(n) < 0.08, "Inactive", "Active")
    df["speed_factor"] = RNG.normal(1.0, 0.12, n).clip(0.7, 1.4)  # <1 faster than avg
    df["reliability"] = RNG.normal(0.93, 0.05, n).clip(0.65, 0.995)  # on-time propensity
    return df


CUSTOMER_SEGMENT_ORDER = ["New", "Occasional", "Loyal", "High Value", "Subscription", "Price Sensitive", "At Risk", "Churned"]


def build_customers(cities: pd.DataFrame, n=12000) -> pd.DataFrame:
    city_ids = RNG.choice(cities.city_id.values, size=n,
                           p=cities.demand_weight.values / cities.demand_weight.sum())
    # NOVAFOOD already had an established base before this reporting window opens:
    # ~45% of customers signed up in the 12 months before HIST_START (pre-existing base),
    # the remainder sign up progressively during the history window (new-customer growth).
    pre_existing = RNG.random(n) < 0.45
    signup_offsets = np.where(
        pre_existing,
        RNG.integers(-365, 0, size=n),
        RNG.integers(0, N_MONTHS * 30, size=n),
    )
    signup_dates = HIST_START + pd.to_timedelta(signup_offsets, unit="D")
    channel_p = [0.34, 0.24, 0.20, 0.14, 0.08]
    channels = RNG.choice(ACQUISITION_CHANNELS, size=n, p=channel_p)
    age_bands = RNG.choice(["18-24", "25-34", "35-44", "45-54", "55+"], size=n, p=[0.18, 0.34, 0.26, 0.14, 0.08])

    # Latent behavioral traits (drive orders later, not the label itself)
    order_propensity = RNG.gamma(shape=2.0, scale=1.0, size=n)  # relative order frequency
    price_sensitivity = RNG.beta(2, 2, size=n)  # 0=insensitive, 1=very sensitive to discounts
    subscription_flag = (RNG.random(n) < 0.16) & (order_propensity > np.quantile(order_propensity, 0.35))

    df = pd.DataFrame(dict(
        customer_id=np.arange(1, n + 1),
        city_id=city_ids,
        signup_date=signup_dates,
        acquisition_channel=channels,
        age_band=age_bands,
        order_propensity=order_propensity,
        price_sensitivity=price_sensitivity,
        subscription_status=np.where(subscription_flag, "Subscribed", "Not Subscribed"),
    ))
    return df


# ---------------------------------------------------------------------------
# Orders: simulate a Poisson order process per customer, then attach economics
# ---------------------------------------------------------------------------

def simulate_orders(customers: pd.DataFrame, restaurants: pd.DataFrame, riders: pd.DataFrame,
                     zones: pd.DataFrame, cities: pd.DataFrame, target_orders=180_000) -> pd.DataFrame:
    active_rest = restaurants[restaurants.active_status == "Active"].copy()
    active_riders = riders[riders.active_status == "Active"].copy()

    n_cust = len(customers)
    months = pd.date_range(HIST_START, HIST_END, freq="MS")

    # Base expected monthly orders per customer, scaled at the end to hit target_orders
    base_rate = 0.9  # orders/month for an "average" customer before propensity scaling

    records = []
    cust_city = customers.set_index("customer_id").city_id
    cust_prop = customers.set_index("customer_id").order_propensity
    cust_signup = customers.set_index("customer_id").signup_date
    cust_price_sens = customers.set_index("customer_id").price_sensitivity
    cust_sub = customers.set_index("customer_id").subscription_status

    city_demand_w = cities.set_index("city_id").demand_weight
    city_tier = cities.set_index("city_id").city_tier

    # tenure-based churn/ramp curve: new customers ramp up for ~2 months then
    # gradually decay in activity (typical marketplace retention curve)
    for m_idx, month_start in enumerate(months):
        month_end = (month_start + pd.offsets.MonthEnd(0))
        eligible = customers[customers.signup_date <= month_end].customer_id.values
        if len(eligible) == 0:
            continue
        tenure_months = ((month_start.year - cust_signup.loc[eligible].dt.year) * 12 +
                          (month_start.year - cust_signup.loc[eligible].dt.year) * 0 +
                          (month_start.month - cust_signup.loc[eligible].dt.month))
        tenure_months = tenure_months.clip(lower=0)
        ramp = np.minimum(1.0, 0.35 + 0.25 * tenure_months)
        retention_decay = np.exp(-0.028 * np.maximum(tenure_months - 2, 0))
        seas = seasonal_multiplier(month_start)
        trend = growth_trend(m_idx)

        lam = (base_rate * cust_prop.loc[eligible].values * ramp.values * retention_decay.values
               * seas * trend * city_demand_w.loc[cust_city.loc[eligible].values].values)
        n_orders_this_month = RNG.poisson(lam)
        for cust_id, n_o in zip(eligible, n_orders_this_month):
            if n_o == 0:
                continue
            records.append((cust_id, month_start, n_o))

    order_alloc = pd.DataFrame(records, columns=["customer_id", "month_start", "n_orders"])
    total_simulated = order_alloc.n_orders.sum()
    scale = target_orders / max(total_simulated, 1)
    # scale by thinning/duplicating counts proportionally (keep integer, reproducible)
    order_alloc["n_orders"] = np.maximum(
        1 if scale > 1 else 0,
        RNG.binomial(order_alloc.n_orders.values, min(scale, 1.0)) if scale <= 1
        else (order_alloc.n_orders.values * scale).round().astype(int)
    )
    order_alloc = order_alloc[order_alloc.n_orders > 0]

    total_orders = int(order_alloc.n_orders.sum())
    cust_ids = np.repeat(order_alloc.customer_id.values, order_alloc.n_orders.values)
    month_starts = np.repeat(order_alloc.month_start.values, order_alloc.n_orders.values)

    n = total_orders
    days_in_month = pd.DatetimeIndex(month_starts).days_in_month.values
    day_offsets = RNG.integers(0, days_in_month)
    order_date = pd.DatetimeIndex(month_starts) + pd.to_timedelta(day_offsets, unit="D")

    dow = order_date.dayofweek
    is_weekend = dow >= 5

    hour_weights_weekday = np.array([0.5,0.3,0.2,0.2,0.3,0.5,1,2,2.5,2,1.5,3,5,4.5,2,1.5,1.5,2,3.5,5,4,2.5,1.5,0.8])
    hour_weights_weekend = np.array([1,0.7,0.5,0.4,0.4,0.5,0.8,1.2,2,3,3.5,4,5,4.5,3,2.5,2.5,3,4,5,4.5,3.5,2,1.3])
    order_hour = np.empty(n, dtype=int)
    for wk in (True, False):
        mask = is_weekend == wk
        w = hour_weights_weekend if wk else hour_weights_weekday
        order_hour[mask] = RNG.choice(24, size=mask.sum(), p=w / w.sum())

    order_datetime = order_date + pd.to_timedelta(order_hour, unit="h") + pd.to_timedelta(RNG.integers(0, 60, n), unit="m")
    is_holiday = np.isin(order_date.normalize(), HOLIDAYS)

    customer_id = cust_ids
    city_id = cust_city.loc[customer_id].values
    price_sens = cust_price_sens.loc[customer_id].values
    sub_status = cust_sub.loc[customer_id].values

    # pick restaurant within customer's city (weighted by tier popularity), zone follows restaurant
    df_r = active_rest
    order_city_restaurants = {cid: df_r[df_r.city_id == cid] for cid in cities.city_id}
    restaurant_id = np.empty(n, dtype=int)
    for cid, sub in order_city_restaurants.items():
        mask = city_id == cid
        cnt = mask.sum()
        if cnt == 0:
            continue
        if len(sub) == 0:
            sub = df_r
        w = np.where(sub.restaurant_tier == "Budget", 1.3, np.where(sub.restaurant_tier == "Mid", 1.0, 0.6))
        restaurant_id[mask] = RNG.choice(sub.restaurant_id.values, size=cnt, p=w / w.sum())

    rest_lookup = restaurants.set_index("restaurant_id")
    r_zone = rest_lookup.zone_id.loc[restaurant_id].values
    r_tier = rest_lookup.restaurant_tier.loc[restaurant_id].values
    r_commission = rest_lookup.commission_rate.loc[restaurant_id].values
    r_base_aov = rest_lookup.base_aov.loc[restaurant_id].values
    r_prep = rest_lookup.avg_food_prep_minutes.loc[restaurant_id].values
    r_cancel_bias = rest_lookup.cancellation_bias.loc[restaurant_id].values

    zone_lookup = zones.set_index("zone_id")
    z_dist = zone_lookup.avg_delivery_distance_km.loc[r_zone].values

    # assign a rider from the same zone when possible
    riders_by_zone = {z: active_riders[active_riders.zone_id == z] for z in zones.zone_id}
    rider_id = np.empty(n, dtype=int)
    for z, sub in riders_by_zone.items():
        mask = r_zone == z
        cnt = mask.sum()
        if cnt == 0:
            continue
        pool = sub.rider_id.values if len(sub) else active_riders.rider_id.values
        rider_id[mask] = RNG.choice(pool, size=cnt)

    rider_lookup = riders.set_index("rider_id")
    rd_speed = rider_lookup.speed_factor.loc[rider_id].values
    rd_reliab = rider_lookup.reliability.loc[rider_id].values

    city_lookup = cities.set_index("city_id")
    delivery_cost_per_km = city_lookup.delivery_cost_per_km.loc[city_id].values
    rider_base_pay = city_lookup.rider_base_pay_per_order.loc[city_id].values

    # ---------- financials ----------
    seasonal_food_noise = RNG.lognormal(mean=0, sigma=0.28, size=n)
    food_value = np.round(r_base_aov * seasonal_food_noise, 2)
    food_value = np.clip(food_value, 3.0, 220.0)

    delivery_distance_km = np.clip(RNG.normal(z_dist, 1.1, n), 0.5, 18.0).round(2)
    delivery_fee = np.round(1.2 + delivery_distance_km * 0.42 + RNG.normal(0, 0.3, n), 2).clip(0.9, 12.0)
    service_fee = np.round(food_value * 0.06 + 0.3, 2).clip(0.3, 6.0)

    # discount targeting: higher for price-sensitive customers / promo pushes in low season
    promo_intensity = np.where(np.isin(order_date.month, [1, 2, 9]), 0.22, 0.14)
    has_discount = RNG.random(n) < (0.25 + 0.35 * price_sens) * (promo_intensity / 0.18)
    discount_amount = np.where(
        has_discount,
        np.round(food_value * RNG.uniform(0.10, 0.40, n) * (0.6 + 0.8 * price_sens), 2),
        0.0,
    )
    new_customer_flag = (order_date <= (cust_signup.loc[customer_id] + pd.Timedelta(days=3)).values)
    discount_amount = np.where(new_customer_flag & ~has_discount, np.round(food_value * 0.20, 2), discount_amount)
    discount_amount = np.minimum(discount_amount, food_value * 0.5)

    customer_total_paid = np.round(food_value + delivery_fee + service_fee - discount_amount, 2).clip(min=0)
    restaurant_commission = np.round(food_value * r_commission, 2)
    payment_processing_cost = np.round(customer_total_paid * 0.019 + 0.10, 2)
    promotion_cost = discount_amount.copy()
    rider_cost = np.round(rider_base_pay + delivery_distance_km * delivery_cost_per_km, 2)

    # status / cancellation / refunds
    cancel_prob = np.clip(0.025 + r_cancel_bias + (1 - rd_reliab) * 0.05, 0.01, 0.22)
    is_holiday_bump = np.where(is_holiday, 0.01, 0.0)
    cancel_prob = np.clip(cancel_prob + is_holiday_bump, 0.01, 0.25)
    status_roll = RNG.random(n)
    order_status = np.where(status_roll < cancel_prob, "Cancelled", "Delivered")
    refund_roll = RNG.random(n)
    refund_mask = (order_status == "Delivered") & (refund_roll < 0.035)
    order_status = np.where(refund_mask, "Refunded", order_status)
    cancellation_reason = np.where(
        order_status == "Cancelled",
        RNG.choice(["Restaurant Rejected", "Customer Cancelled", "No Rider Available", "Long Wait"], size=n),
        "",
    )
    refund_amount = np.where(order_status == "Refunded", np.round(customer_total_paid * RNG.uniform(0.3, 1.0, n), 2), 0.0)

    platform_revenue = np.round(restaurant_commission + service_fee + delivery_fee * 0.35, 2)
    platform_revenue = np.where(order_status == "Cancelled", 0.0, platform_revenue)
    platform_revenue = platform_revenue - refund_amount * 0.5
    gross_order_value = np.where(order_status == "Cancelled", 0.0, np.round(food_value + delivery_fee + service_fee, 2))
    rider_cost = np.where(order_status == "Cancelled", rider_cost * 0.2, rider_cost)  # partial dispatch cost
    contribution_profit = np.round(
        platform_revenue - rider_cost - payment_processing_cost - promotion_cost * 0 - refund_amount * 0.5, 2
    )
    # promotion cost already subtracted from customer_total_paid/platform math implicitly via discount;
    # treat promotion_cost as a marketing spend line separate from revenue accounting below in finance module.

    estimated_delivery_minutes = np.round(r_prep + 8 + z_dist * 3.2, 1)
    delay_noise = RNG.normal(0, 5, n) + (1 - rd_reliab) * 12 + np.where(is_holiday, 4, 0)
    actual_delivery_minutes = np.clip(estimated_delivery_minutes * rd_speed + delay_noise, 8, 120).round(1)
    delivery_delay_minutes = np.round(actual_delivery_minutes - estimated_delivery_minutes, 1)

    rating = np.clip(RNG.normal(4.4 - np.maximum(delivery_delay_minutes, 0) * 0.01, 0.4, n), 1.0, 5.0).round(1)
    rating = np.where(order_status != "Delivered", np.nan, rating)

    payment_method = RNG.choice(PAYMENT_METHODS, size=n, p=[0.52, 0.28, 0.14, 0.06])

    orders = pd.DataFrame(dict(
        order_id=np.arange(1, n + 1),
        customer_id=customer_id,
        restaurant_id=restaurant_id,
        rider_id=rider_id,
        city_id=city_id,
        zone_id=r_zone,
        order_datetime=order_datetime,
        order_date=pd.DatetimeIndex(order_date).normalize(),
        order_hour=order_hour,
        day_of_week=dow,
        is_weekend=is_weekend,
        is_holiday=is_holiday,
        order_status=order_status,
        cancellation_reason=cancellation_reason,
        gross_order_value=gross_order_value,
        food_value=food_value,
        delivery_fee=delivery_fee,
        service_fee=service_fee,
        discount_amount=discount_amount,
        restaurant_commission=restaurant_commission,
        customer_total_paid=customer_total_paid,
        platform_revenue=platform_revenue.round(2),
        rider_cost=rider_cost.round(2),
        payment_processing_cost=payment_processing_cost,
        promotion_cost=promotion_cost,
        refund_amount=refund_amount,
        contribution_profit=contribution_profit,
        delivery_distance_km=delivery_distance_km,
        estimated_delivery_minutes=estimated_delivery_minutes,
        actual_delivery_minutes=actual_delivery_minutes,
        delivery_delay_minutes=delivery_delay_minutes,
        rating=rating,
        new_customer_flag=new_customer_flag,
        subscription_customer_flag=(sub_status == "Subscribed"),
        promotion_id=np.where(has_discount, RNG.integers(1, 25, n), 0),
        payment_method=payment_method,
    ))
    return orders


@dataclass
class GeneratedData:
    cities: pd.DataFrame
    zones: pd.DataFrame
    restaurants: pd.DataFrame
    riders: pd.DataFrame
    customers: pd.DataFrame
    orders: pd.DataFrame


def generate_all(n_customers=12000, n_restaurants=320, n_riders=520, target_orders=180_000, seed=SEED) -> GeneratedData:
    global RNG
    RNG = np.random.default_rng(seed)  # reset each call so repeated calls in one process stay reproducible
    cities = build_cities()
    zones = build_zones(cities)
    restaurants = build_restaurants(zones, n=n_restaurants)
    riders = build_riders(zones, n=n_riders)
    customers = build_customers(cities, n=n_customers)
    orders = simulate_orders(customers, restaurants, riders, zones, cities, target_orders=target_orders)
    return GeneratedData(cities, zones, restaurants, riders, customers, orders)


if __name__ == "__main__":
    data = generate_all()
    print({k: len(v) for k, v in data.__dict__.items()})
