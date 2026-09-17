import sys, os, json
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from data_generation.generate import generate_all
from data_processing.build_derived import (
    enrich_customers, restaurant_daily_metrics, restaurant_summary, rider_summary,
    monthly_financials, cohort_table, rfm_table,
)
from finance.finance import (
    pnl_summary, unit_economics_by, cac_ltv_by_channel, margin_driver_decomposition, restaurant_quadrants,
)
from forecasting.forecast import build_forecast_table, scenario_cases
from optimization.optimize import build_cells, optimize_allocation, summarize_optimization
from analytics.planning import build_plan

RAW = os.path.join(ROOT, "data", "raw")
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(ROOT, "outputs")
os.makedirs(RAW, exist_ok=True)
os.makedirs(PROC, exist_ok=True)


def validate(orders: pd.DataFrame, customers: pd.DataFrame, restaurants: pd.DataFrame) -> dict:
    report = {}
    report["duplicate_order_ids"] = int(orders.order_id.duplicated().sum())
    report["missing_values"] = {c: int(orders[c].isna().sum()) for c in orders.columns if orders[c].isna().any()}
    report["negative_financials"] = int((orders[["gross_order_value", "delivery_fee", "rider_cost"]] < 0).any(axis=1).sum())
    report["orphan_customer_fk"] = int((~orders.customer_id.isin(customers.customer_id)).sum())
    report["orphan_restaurant_fk"] = int((~orders.restaurant_id.isin(restaurants.restaurant_id)).sum())
    calc_total = (orders.food_value + orders.delivery_fee + orders.service_fee - orders.discount_amount).round(2)
    report["financial_equation_mismatches"] = int((calc_total - orders.customer_total_paid).abs().gt(0.01).sum())
    report["order_status_values"] = orders.order_status.value_counts().to_dict()
    report["status"] = "PASS" if report["duplicate_order_ids"] == 0 and report["orphan_customer_fk"] == 0 and report["orphan_restaurant_fk"] == 0 else "REVIEW"
    return report


def main(n_customers=12000, n_restaurants=320, n_riders=520, target_orders=180_000):
    print("1/9 Generating synthetic data ...")
    data = generate_all(n_customers, n_restaurants, n_riders, target_orders)

    print("2/9 Validating data quality ...")
    dq = validate(data.orders, data.customers, data.restaurants)
    with open(os.path.join(OUT, "reports", "data_quality_report.json"), "w") as f:
        json.dump(dq, f, indent=2, default=str)
    print("   ->", dq["status"], "| orders:", len(data.orders))

    print("3/9 Saving raw tables ...")
    data.cities.to_csv(f"{RAW}/cities.csv", index=False)
    data.zones.to_csv(f"{RAW}/zones.csv", index=False)
    data.restaurants.to_csv(f"{RAW}/restaurants.csv", index=False)
    data.riders.to_csv(f"{RAW}/riders.csv", index=False)
    data.customers.to_csv(f"{RAW}/customers.csv", index=False)
    data.orders.to_csv(f"{RAW}/orders.csv", index=False)

    print("4/9 Building derived tables (customers, restaurants, riders, cohorts) ...")
    cust_enriched = enrich_customers(data.customers, data.orders)
    rest_daily = restaurant_daily_metrics(data.orders)
    rest_summary = restaurant_summary(data.restaurants, data.orders)
    rid_summary = rider_summary(data.riders, data.orders)
    monthly = monthly_financials(data.orders)
    cohorts = cohort_table(data.customers, data.orders)
    rfm = rfm_table(cust_enriched)

    cust_enriched.to_csv(f"{PROC}/customers_enriched.csv", index=False)
    rest_daily.to_csv(f"{PROC}/restaurant_daily_metrics.csv", index=False)
    rest_summary.to_csv(f"{PROC}/restaurant_summary.csv", index=False)
    rid_summary.to_csv(f"{PROC}/rider_summary.csv", index=False)
    monthly.to_csv(f"{PROC}/monthly_financials.csv", index=False)
    cohorts.to_csv(f"{PROC}/cohorts.csv", index=False)
    rfm.to_csv(f"{PROC}/rfm.csv", index=False)

    print("5/9 Financial analysis, unit economics, driver decomposition ...")
    pnl = pnl_summary(monthly)
    ue_city = unit_economics_by(data.orders, "city_id", data.cities[["city_id", "city_name"]])
    ue_segment = unit_economics_by(
        data.orders.merge(cust_enriched[["customer_id", "customer_segment"]], on="customer_id", how="left"),
        "customer_segment",
    )
    ue_channel = unit_economics_by(
        data.orders.merge(data.customers[["customer_id", "acquisition_channel"]], on="customer_id", how="left"),
        "acquisition_channel",
    )
    cac_by_channel = {"Organic/Referral": 1.5, "Paid Social": 9.0, "Paid Search": 11.5, "Push/CRM": 2.0, "Partnership": 6.0}
    cac_ltv = cac_ltv_by_channel(cust_enriched, cac_by_channel)
    drivers = margin_driver_decomposition(monthly)
    quadrants = restaurant_quadrants(rest_summary)

    pnl.to_csv(f"{PROC}/pnl_monthly.csv", index=False)
    ue_city.to_csv(f"{PROC}/unit_economics_by_city.csv", index=False)
    ue_segment.to_csv(f"{PROC}/unit_economics_by_segment.csv", index=False)
    ue_channel.to_csv(f"{PROC}/unit_economics_by_channel.csv", index=False)
    cac_ltv.to_csv(f"{PROC}/cac_ltv_by_channel.csv", index=False)
    drivers.to_csv(f"{PROC}/margin_driver_decomposition.csv", index=False)
    quadrants.to_csv(f"{PROC}/restaurant_quadrants.csv", index=False)

    print("6/9 Demand forecasting (rolling-origin validation across 3 models) ...")
    forecast_df, forecast_results = build_forecast_table(monthly, horizon=12)
    forecast_scn = scenario_cases(forecast_df)
    forecast_scn.to_csv(f"{PROC}/forecast.csv", index=False)
    with open(f"{PROC}/forecast_model_selection.json", "w") as f:
        json.dump({k: {kk: vv for kk, vv in v.items() if kk in ("model_selected", "validation")} for k, v in forecast_results.items()}, f, indent=2, default=str)

    print("7/9 Scenario planning + strategic plan ...")
    plan = build_plan(monthly)
    with open(f"{PROC}/strategic_plan.json", "w") as f:
        json.dump(plan, f, indent=2, default=str)

    print("8/9 Promotion budget optimization ...")
    cells = build_cells(data.orders, cust_enriched, data.cities)
    monthly_promo_budget = float(monthly.promotion_cost.tail(3).mean())
    alloc = optimize_allocation(cells, total_budget=monthly_promo_budget)
    opt_summary = summarize_optimization(alloc)
    alloc.to_csv(f"{PROC}/optimization_allocation.csv", index=False)
    with open(f"{PROC}/optimization_summary.json", "w") as f:
        json.dump(opt_summary, f, indent=2, default=str)

    print("9/9 Key findings ...")
    findings = compute_findings(data, cust_enriched, ue_city, ue_segment, cac_ltv, monthly, plan, opt_summary)
    with open(f"{OUT}/reports/key_findings.json", "w") as f:
        json.dump(findings, f, indent=2, default=str)

    print("\nDone. Orders:", len(data.orders), "| Customers:", len(data.customers),
          "| Restaurants:", len(data.restaurants), "| Riders:", len(data.riders))
    return dict(data=data, cust_enriched=cust_enriched, rest_summary=rest_summary, rid_summary=rid_summary,
                monthly=monthly, cohorts=cohorts, rfm=rfm, pnl=pnl, ue_city=ue_city, ue_segment=ue_segment,
                ue_channel=ue_channel, cac_ltv=cac_ltv, drivers=drivers, quadrants=quadrants,
                forecast=forecast_scn, plan=plan, alloc=alloc, opt_summary=opt_summary, findings=findings, dq=dq)


def compute_findings(data, cust_enriched, ue_city, ue_segment, cac_ltv, monthly, plan, opt_summary) -> dict:
    best_city = ue_city.loc[ue_city.contribution_margin_pct.idxmax()]
    worst_city = ue_city.loc[ue_city.contribution_margin_pct.idxmin()]
    best_seg = ue_segment.loc[ue_segment.contribution_profit_per_order.idxmax()]
    best_channel = cac_ltv.iloc[0]
    # Skip the first 3 months (customer-base ramp-up distorts a raw start/end CAGR)
    # and use a trailing-quarter-over-trailing-quarter annualized growth rate instead.
    stable = monthly.iloc[3:]
    early_q = stable.iloc[:3].delivered_orders.mean()
    late_q = stable.iloc[-3:].delivered_orders.mean()
    n_month_gap = len(stable) - 3
    order_cagr = (late_q / max(early_q, 1)) ** (12 / max(n_month_gap, 1)) - 1
    order_cagr = max(min(order_cagr, 2.0), -0.9)  # sanity clamp for the headline stat

    return {
        "highest_margin_city": {"city": best_city.city_name, "contribution_margin_pct": round(float(best_city.contribution_margin_pct) * 100, 1)},
        "weakest_margin_city": {"city": worst_city.city_name, "contribution_margin_pct": round(float(worst_city.contribution_margin_pct) * 100, 1)},
        "highest_value_segment": {"segment": best_seg.customer_segment, "contribution_profit_per_order": round(float(best_seg.contribution_profit_per_order), 2)},
        "best_ltv_cac_channel": {"channel": best_channel.acquisition_channel, "ltv_to_cac": round(float(best_channel.ltv_to_cac), 2)},
        "annualized_order_growth_rate_pct": round(float(order_cagr) * 100, 1),
        "current_contribution_margin_pct": round(float(monthly.contribution_margin_pct.tail(3).mean()) * 100, 2),
        "strategic_plan_verdict": plan["verdict"],
        "optimization_incremental_profit_gain_pct": round(opt_summary["gain_pct"], 1),
        "total_orders": int(len(data.orders)),
        "total_customers": int(len(data.customers)),
        "total_restaurants": int(len(data.restaurants)),
        "total_riders": int(len(data.riders)),
        "history_months": int(monthly.shape[0]),
    }


if __name__ == "__main__":
    main()
