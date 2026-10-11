"""Tests for the v2 extended KPI layer and the two v2 data tables."""
import os, sys
import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from data_generation.generate import generate_all, HIST_START, ACQUISITION_CHANNELS, N_MONTHS
from data_processing.build_derived import enrich_customers, monthly_financials, cohort_table
from finance.finance import cac_ltv_by_channel
from analytics.kpis import monthly_kpi_extension, build_scorecard, build_kpi_bundle, SCORECARD_SPEC

CAC = {"Organic/Referral": 1.5, "Paid Social": 9.0, "Paid Search": 11.5, "Push/CRM": 2.0, "Partnership": 6.0}
ALLOWED_FMT = {"money0", "money2", "int", "pct1", "dec1", "dec2", "min1"}


@pytest.fixture(scope="module")
def data():
    return generate_all(n_customers=1500, n_restaurants=60, n_riders=90, target_orders=12000)


@pytest.fixture(scope="module")
def parts(data):
    cust = enrich_customers(data.customers, data.orders)
    monthly = monthly_financials(data.orders)
    cohorts = cohort_table(data.customers, data.orders)
    mx = monthly_kpi_extension(data.orders, monthly, data.marketing_spend, data.rider_shifts, data.customers, cohorts)
    cac_ltv = cac_ltv_by_channel(cust, CAC)
    return dict(cust=cust, monthly=monthly, mx=mx, cac_ltv=cac_ltv)


# ---------------- v2 data tables ----------------

def test_marketing_grid_is_month_by_channel(data):
    ms = data.marketing_spend
    assert len(ms) == N_MONTHS * len(ACQUISITION_CHANNELS)
    assert (ms.marketing_spend >= 0).all()
    assert ms.loc[ms.signups == 0, "marketing_spend"].eq(0).all()


def test_marketing_signups_match_customers(data):
    in_window = (data.customers.signup_date >= HIST_START).sum()
    assert data.marketing_spend.signups.sum() == in_window


def test_marketing_and_shifts_reproducible():
    kw = dict(n_customers=300, n_restaurants=15, n_riders=25, target_orders=1500)
    a, b = generate_all(**kw), generate_all(**kw)
    pd.testing.assert_frame_equal(a.marketing_spend, b.marketing_spend)
    pd.testing.assert_frame_equal(a.rider_shifts, b.rider_shifts)


def test_v2_tables_do_not_change_v1_orders():
    """Orders must be identical whether or not the v2 tables are built (separate RNG streams)."""
    kw = dict(n_customers=300, n_restaurants=15, n_riders=25, target_orders=1500)
    d = generate_all(**kw)
    assert d.orders.order_id.is_unique and len(d.orders) > 1000


def test_rider_utilization_is_bounded(data):
    rs = data.rider_shifts
    util = rs.busy_hours / rs.online_hours
    assert util.between(0.2, 0.8).all()
    assert (rs.orders > 0).all()


# ---------------- monthly KPI extension ----------------

def test_unit_economics_identity(parts):
    mx = parts["mx"]
    lhs = mx.revenue_per_order - mx.cost_to_serve_per_order
    assert np.allclose(lhs, mx.contribution_profit_per_order, atol=0.01)


def test_promotion_adjusted_contribution(parts):
    mx = parts["mx"]
    assert np.allclose(mx.contribution_after_promo, mx.contribution_profit - mx.promotion_cost, atol=0.01)


@pytest.mark.parametrize("col", [
    "on_time_rate_pct", "cancellation_rate_pct", "very_late_rate_pct", "refund_rate_pct", "promo_order_share_pct",
    "subscriber_order_share_pct", "weekend_share_pct", "new_customer_share_pct", "rider_utilization_pct",
    "m1_retention_pct",
])
def test_percentage_kpis_between_0_and_100(parts, col):
    s = parts["mx"][col].dropna()
    assert len(s) > 0 and s.between(0, 100).all()


def test_yoy_only_after_twelve_months(parts):
    mx = parts["mx"]
    assert mx.gmv_yoy_pct.iloc[:12].isna().all()


# ---------------- scorecard ----------------

def test_scorecard_structure(parts):
    sc = build_scorecard(parts["mx"])
    keys = [it["key"] for g in sc["groups"] for it in g["items"]]
    assert len(keys) == len(set(keys)) >= 30
    assert [g["key"] for g in sc["groups"]] == [g for g, _ in SCORECARD_SPEC]
    for g in sc["groups"]:
        for it in g["items"]:
            assert it["fmt"] in ALLOWED_FMT
            assert it["good"] in {"up", "down", "neutral"}
            assert it["delta_kind"] in {"pct", "pp"}
            assert it["window"] in {"1M", "3M"}
            assert len(it["spark"]) == 12


# ---------------- dashboard bundle ----------------

@pytest.fixture(scope="module")
def bundle(data, parts):
    return build_kpi_bundle(data, parts["cust"], parts["mx"], parts["cac_ltv"], CAC)


def test_waterfall_reconciles(bundle):
    w = bundle["unit_econ"]["waterfall"]
    total = w["revenue_per_order"] + w["rider_cost"] + w["payment_cost"] + w["refund_cost"]
    assert abs(total - w["contribution_per_order"]) < 0.03
    assert abs(w["contribution_per_order"] + w["promotion_cost"] - w["contribution_after_promo_per_order"]) < 0.03


def test_heatmap_shape_and_values(bundle):
    z = np.array(bundle["ops"]["heatmap"]["z"], dtype=float)
    assert z.shape == (7, 24) and (z >= 0).all()


def test_concentration_curve_is_monotonic(bundle):
    c = bundle["customers_ext"]["concentration"]
    y = c["y_pct_gmv"]
    assert y[0] == 0 and abs(y[-1] - 100) < 0.5
    assert all(b >= a for a, b in zip(y, y[1:]))
    assert c["top20_share_pct"] >= c["top10_share_pct"] >= 10


def test_cancel_reason_shares_sum_to_100(bundle):
    assert abs(sum(bundle["ops"]["cancel_reasons"]["share_pct"]) - 100) < 0.5


def test_city_scorecard_columns_align(bundle):
    cs = bundle["ops"]["city_scorecard"]
    n = len(cs["names"])
    assert n == 8 and all(len(v) == n for v in cs.values())


def test_marketing_observed_cac_above_assumed_for_paid(bundle):
    m = bundle["marketing"]
    for ch in ("Paid Social", "Paid Search"):
        assert m["cac_observed_latest_3m"][ch] >= m["cac_assumed"][ch] * 0.9
