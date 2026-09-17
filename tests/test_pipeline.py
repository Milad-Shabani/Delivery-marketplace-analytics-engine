import os, sys, json
import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from data_generation.generate import generate_all
from data_processing.build_derived import enrich_customers, monthly_financials, cohort_table, restaurant_summary
from finance.finance import unit_economics_by, margin_driver_decomposition, restaurant_quadrants
from forecasting.forecast import rolling_origin_validate, forecast_series, _wape, _mape
from optimization.optimize import build_cells, optimize_allocation, summarize_optimization
from analytics.planning import build_plan


@pytest.fixture(scope="module")
def small_data():
    return generate_all(n_customers=800, n_restaurants=40, n_riders=60, target_orders=6000)


@pytest.fixture(scope="module")
def monthly(small_data):
    return monthly_financials(small_data.orders)


# ---------------- Data quality ----------------

def test_no_duplicate_order_ids(small_data):
    assert small_data.orders.order_id.duplicated().sum() == 0


def test_order_foreign_keys_valid(small_data):
    assert small_data.orders.customer_id.isin(small_data.customers.customer_id).all()
    assert small_data.orders.restaurant_id.isin(small_data.restaurants.restaurant_id).all()


def test_no_negative_core_financials(small_data):
    o = small_data.orders
    assert (o.food_value >= 0).all()
    assert (o.delivery_fee >= 0).all()
    assert (o.rider_cost >= 0).all()


def test_financial_equation_reconciles(small_data):
    o = small_data.orders
    calc = (o.food_value + o.delivery_fee + o.service_fee - o.discount_amount).round(2)
    assert (calc - o.customer_total_paid).abs().max() < 0.02


def test_order_status_values_valid(small_data):
    assert set(small_data.orders.order_status.unique()) <= {"Delivered", "Cancelled", "Refunded"}


def test_reproducible_with_fixed_seed():
    d1 = generate_all(n_customers=200, n_restaurants=10, n_riders=15, target_orders=500)
    d2 = generate_all(n_customers=200, n_restaurants=10, n_riders=15, target_orders=500)
    assert d1.orders.shape == d2.orders.shape
    pd.testing.assert_series_equal(d1.orders.gross_order_value, d2.orders.gross_order_value)


# ---------------- KPI / financial calculations ----------------

def test_monthly_gmv_is_positive(monthly):
    assert (monthly.gmv > 0).all()


def test_contribution_margin_pct_is_bounded(monthly):
    assert monthly.contribution_margin_pct.between(-2, 1).all()


def test_aov_matches_gmv_over_orders(monthly):
    recomputed = monthly.gmv / monthly.delivered_orders.replace(0, np.nan)
    assert np.allclose(recomputed.fillna(0), monthly.aov, atol=0.01)


def test_unit_economics_by_city_sums_reasonably(small_data):
    cust = enrich_customers(small_data.customers, small_data.orders)
    ue = unit_economics_by(small_data.orders, "city_id")
    assert ue.orders.sum() <= len(small_data.orders)
    assert (ue.aov > 0).all()


def test_customer_segments_are_from_known_set(small_data):
    cust = enrich_customers(small_data.customers, small_data.orders)
    known = {"New", "Occasional", "Loyal", "High Value", "Subscription", "Price Sensitive",
             "At Risk", "Churned", "Never Ordered"}
    assert set(cust.customer_segment.unique()) <= known


def test_restaurant_quadrants_are_four_categories(small_data):
    rs = restaurant_summary(small_data.restaurants, small_data.orders)
    quad = restaurant_quadrants(rs)
    assert set(quad.quadrant.unique()) <= {
        "Star: High Revenue / High Margin", "Volume Trap: High Revenue / Low Margin",
        "Niche Profit: Low Revenue / High Margin", "Review: Low Revenue / Low Margin",
    }


def test_cohort_retention_between_zero_and_one(small_data):
    coh = cohort_table(small_data.customers, small_data.orders)
    assert coh.retention_rate.between(0, 1.0001).all()


# ---------------- Forecasting ----------------

def test_wape_zero_for_perfect_forecast():
    actual = np.array([10, 20, 30])
    assert _wape(actual, actual) == 0


def test_mape_reasonable_value():
    actual = np.array([100, 200])
    pred = np.array([110, 190])
    m = _mape(actual, pred)
    assert 0 < m < 0.2


def test_rolling_origin_validate_returns_all_models():
    series = pd.Series(np.linspace(100, 300, 24)) + np.tile([5, -5, 3, -3], 6)
    val = rolling_origin_validate(series, horizon=2, min_train=12)
    assert set(val.model) == {"seasonal_naive", "moving_average", "holt_winters"}


def test_forecast_series_produces_nonnegative_horizon():
    series = pd.Series(np.linspace(50, 150, 18))
    out = forecast_series(series, horizon=6)
    assert len(out["point_forecast"]) == 6
    assert all(v >= 0 for v in out["point_forecast"])


# ---------------- Optimization ----------------

def test_optimization_respects_budget_constraint(small_data):
    cust = enrich_customers(small_data.customers, small_data.orders)
    cells = build_cells(small_data.orders, cust, small_data.cities)
    budget = 5000.0
    alloc = optimize_allocation(cells, total_budget=budget)
    assert abs(alloc.optimized_spend.sum() - budget) < 1.0


def test_optimization_respects_bounds(small_data):
    cust = enrich_customers(small_data.customers, small_data.orders)
    cells = build_cells(small_data.orders, cust, small_data.cities)
    budget = 5000.0
    alloc = optimize_allocation(cells, total_budget=budget, min_floor_frac=0.005, max_cell_frac=0.35)
    assert (alloc.optimized_spend >= budget * 0.005 - 1e-6).all()
    assert (alloc.optimized_spend <= budget * 0.35 + 1e-6).all()


def test_optimization_beats_or_matches_baseline(small_data):
    cust = enrich_customers(small_data.customers, small_data.orders)
    cells = build_cells(small_data.orders, cust, small_data.cities)
    alloc = optimize_allocation(cells, total_budget=4000.0)
    summary = summarize_optimization(alloc)
    assert summary["optimized_incremental_profit"] >= summary["baseline_incremental_profit"] - 1e-6


# ---------------- Scenario / planning ----------------

def test_strategic_plan_has_required_fields(monthly):
    plan = build_plan(monthly)
    for key in ["current_margin_pct", "required_margin_pct", "levers", "verdict"]:
        assert key in plan
    assert plan["required_margin_pct"] > plan["current_margin_pct"]


def test_margin_driver_decomposition_returns_five_drivers(monthly):
    drivers = margin_driver_decomposition(monthly)
    assert len(drivers) == 5
    assert "driver" in drivers.columns and "approx_margin_pp_impact" in drivers.columns
