import os, json
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT_DIR = os.path.join(ROOT, "dashboard", "data")
os.makedirs(OUT_DIR, exist_ok=True)


def r(x, n=2):
    if pd.isna(x):
        return None
    return round(float(x), n)


def main():
    monthly = pd.read_csv(f"{PROC}/monthly_financials.csv", parse_dates=["month"])
    ue_city = pd.read_csv(f"{PROC}/unit_economics_by_city.csv")
    ue_segment = pd.read_csv(f"{PROC}/unit_economics_by_segment.csv")
    cac_ltv = pd.read_csv(f"{PROC}/cac_ltv_by_channel.csv")
    drivers = pd.read_csv(f"{PROC}/margin_driver_decomposition.csv")
    quadrants = pd.read_csv(f"{PROC}/restaurant_quadrants.csv")
    cust_enriched = pd.read_csv(f"{PROC}/customers_enriched.csv")
    cohorts = pd.read_csv(f"{PROC}/cohorts.csv", parse_dates=["cohort_month"])
    forecast = pd.read_csv(f"{PROC}/forecast.csv", parse_dates=["month"])
    alloc = pd.read_csv(f"{PROC}/optimization_allocation.csv")
    with open(f"{PROC}/optimization_summary.json") as f:
        opt_summary = json.load(f)
    with open(f"{PROC}/strategic_plan.json") as f:
        plan = json.load(f)
    with open(f"{ROOT}/outputs/reports/key_findings.json") as f:
        findings = json.load(f)
    with open(f"{PROC}/forecast_model_selection.json") as f:
        model_sel = json.load(f)
    with open(f"{ROOT}/outputs/reports/data_quality_report.json") as f:
        dq = json.load(f)

    months = monthly.month.dt.strftime("%Y-%m").tolist()

    kpis = {
        "gmv": r(monthly.gmv.iloc[-1], 0),
        "orders": int(monthly.delivered_orders.iloc[-1]),
        "revenue": r(monthly.platform_revenue.iloc[-1], 0),
        "contribution_profit": r(monthly.contribution_profit.iloc[-1], 0),
        "contribution_margin_pct": r(monthly.contribution_margin_pct.tail(3).mean() * 100, 1),
        "active_customers": int(monthly.active_customers.iloc[-1]),
        "aov": r(monthly.aov.iloc[-1], 2),
        "on_time_rate": r(monthly.on_time_rate.iloc[-1] * 100, 1),
        "gmv_growth_pct": r(monthly.gmv_growth_pct.iloc[-1] * 100, 1) if not pd.isna(monthly.gmv_growth_pct.iloc[-1]) else None,
        "orders_growth_annualized_pct": findings["annualized_order_growth_rate_pct"],
    }

    financial = {
        "months": months,
        "gmv": monthly.gmv.round(0).tolist(),
        "discount_amount": monthly.discount_amount.round(0).tolist(),
        "net_customer_spend": monthly.net_customer_spend.round(0).tolist(),
        "commission_revenue": monthly.commission_revenue.round(0).tolist(),
        "delivery_fee_collected": monthly.delivery_fee_collected.round(0).tolist(),
        "service_fee_revenue": monthly.service_fee_revenue.round(0).tolist(),
        "platform_revenue": monthly.platform_revenue.round(0).tolist(),
        "rider_cost": monthly.rider_cost.round(0).tolist(),
        "payment_processing_cost": monthly.payment_processing_cost.round(0).tolist(),
        "promotion_cost": monthly.promotion_cost.round(0).tolist(),
        "refund_amount": monthly.refund_amount.round(0).tolist(),
        "contribution_profit": monthly.contribution_profit.round(0).tolist(),
        "contribution_margin_pct": (monthly.contribution_margin_pct * 100).round(2).tolist(),
        "delivered_orders": monthly.delivered_orders.tolist(),
        "new_customers": monthly.new_customers.tolist(),
        "active_customers": monthly.active_customers.tolist(),
        "cancellation_rate": (monthly.cancellation_rate * 100).round(2).tolist(),
        "on_time_rate": (monthly.on_time_rate * 100).round(2).tolist(),
    }

    cities = {
        "names": ue_city.city_name.tolist(),
        "orders": ue_city.orders.tolist(),
        "gmv": ue_city.gmv.round(0).tolist(),
        "aov": ue_city.aov.round(2).tolist(),
        "contribution_margin_pct": (ue_city.contribution_margin_pct * 100).round(1).tolist(),
        "contribution_profit": ue_city.contribution_profit.round(0).tolist(),
    }

    segments = {
        "names": ue_segment.customer_segment.tolist(),
        "orders": ue_segment.orders.tolist(),
        "contribution_profit_per_order": ue_segment.contribution_profit_per_order.round(2).tolist(),
        "contribution_margin_pct": (ue_segment.contribution_margin_pct * 100).round(1).tolist(),
        "customer_counts": cust_enriched.customer_segment.value_counts().reindex(ue_segment.customer_segment).fillna(0).astype(int).tolist(),
    }

    channels = {
        "names": cac_ltv.acquisition_channel.tolist(),
        "cac": cac_ltv.cac.round(2).tolist(),
        "ltv": cac_ltv.ltv.round(2).tolist(),
        "ltv_to_cac": cac_ltv.ltv_to_cac.round(2).tolist(),
        "churn_rate": (cac_ltv.churn_rate * 100).round(1).tolist(),
    }

    quad_counts = quadrants.quadrant.value_counts()
    restaurants_out = {
        "quadrant_labels": quad_counts.index.tolist(),
        "quadrant_counts": quad_counts.values.tolist(),
        "scatter": {
            "gmv": quadrants.monthly_gmv.round(1).fillna(0).tolist(),
            "margin_pct": (quadrants.margin_pct * 100).round(1).fillna(0).tolist(),
            "quadrant": quadrants.quadrant.fillna("Review: Low Revenue / Low Margin").tolist(),
            "name": quadrants.restaurant_name.tolist(),
            "cuisine": quadrants.cuisine.tolist(),
        },
        "cuisine_gmv": quadrants.groupby("cuisine").monthly_gmv.sum().sort_values(ascending=False).round(0).to_dict(),
    }

    piv = cohorts.pivot_table(index="cohort_month", columns="month_number", values="retention_rate")
    cohort_out = {
        "cohort_labels": [d.strftime("%Y-%m") for d in piv.index],
        "month_numbers": [int(c) for c in piv.columns],
        "matrix": [[None if pd.isna(v) else round(float(v) * 100, 1) for v in row] for row in piv.values],
        "m1_retention_avg": r(piv[1].mean() * 100, 1) if 1 in piv.columns else None,
        "m3_retention_avg": r(piv[3].mean() * 100, 1) if 3 in piv.columns else None,
    }

    fc = {}
    for metric in forecast.metric.unique():
        sub = forecast[forecast.metric == metric]
        fc[metric] = {
            "months": sub.month.dt.strftime("%Y-%m").tolist(),
            "point_forecast": sub.point_forecast.round(1).tolist(),
            "lower_80": sub.lower_80.round(1).tolist(),
            "upper_80": sub.upper_80.round(1).tolist(),
            "base_case": sub.base_case.round(1).tolist(),
            "upside_case": sub.upside_case.round(1).tolist(),
            "downside_case": sub.downside_case.round(1).tolist(),
        }
    forecast_out = {
        "metrics": fc,
        "history_orders": {"months": months, "values": monthly.delivered_orders.tolist()},
        "model_selection": {k: v["model_selected"] for k, v in model_sel.items()},
        "validation": {k: v["validation"] for k, v in model_sel.items()},
    }

    alloc_top = alloc.sort_values("optimized_incremental_profit", ascending=False).head(15)
    optimization_out = {
        "summary": opt_summary,
        "cells": {
            "labels": (alloc_top.city_name + " / " + alloc_top.customer_segment).tolist(),
            "baseline_spend": alloc_top.baseline_spend.round(0).tolist(),
            "optimized_spend": alloc_top.optimized_spend.round(0).tolist(),
            "baseline_profit": alloc_top.baseline_incremental_profit.round(1).tolist(),
            "optimized_profit": alloc_top.optimized_incremental_profit.round(1).tolist(),
        },
    }

    payload = {
        "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "kpis": kpis,
        "financial": financial,
        "cities": cities,
        "segments": segments,
        "channels": channels,
        "restaurants": restaurants_out,
        "cohorts": cohort_out,
        "forecast": forecast_out,
        "optimization": optimization_out,
        "drivers": {"labels": drivers.driver.tolist(), "values": drivers.approx_margin_pp_impact.tolist()},
        "plan": plan,
        "findings": findings,
        "data_quality": dq,
    }

    js = "window.NOVAFOOD_DATA = " + json.dumps(payload, default=str) + ";\n"
    with open(f"{OUT_DIR}/novafood_data.js", "w") as f:
        f.write(js)
    print("Wrote", f"{OUT_DIR}/novafood_data.js", len(js), "bytes")


if __name__ == "__main__":
    main()
