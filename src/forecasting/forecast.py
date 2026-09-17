"""Demand forecasting: orders / GMV / revenue / contribution profit, 12 months ahead.

Uses rolling-origin (temporal) validation across three candidate models and
selects the one with the lowest validation WAPE. No random train/test split
is used, since this is time-series data.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def _seasonal_naive(train: pd.Series, horizon: int, season=12) -> np.ndarray:
    if len(train) < season:
        return np.repeat(train.iloc[-1], horizon)
    last_season = train.iloc[-season:].values
    reps = int(np.ceil(horizon / season))
    return np.tile(last_season, reps)[:horizon]


def _moving_average(train: pd.Series, horizon: int, window=3) -> np.ndarray:
    avg = train.iloc[-window:].mean()
    trend = (train.iloc[-1] - train.iloc[-window]) / window if len(train) > window else 0
    return np.array([avg + trend * (i + 1) for i in range(horizon)])


def _holt_winters(train: pd.Series, horizon: int, season=12) -> np.ndarray:
    try:
        seasonal = "add"
        sp = season if len(train) >= season * 2 else None
        model = ExponentialSmoothing(
            train.values, trend="add", damped_trend=True,
            seasonal=seasonal if sp else None, seasonal_periods=sp,
            initialization_method="estimated",
        ).fit(optimized=True)
        return model.forecast(horizon)
    except Exception:
        return _moving_average(train, horizon)


MODELS = {
    "seasonal_naive": _seasonal_naive,
    "moving_average": _moving_average,
    "holt_winters": _holt_winters,
}


def _wape(actual: np.ndarray, pred: np.ndarray) -> float:
    denom = np.sum(np.abs(actual))
    return float(np.sum(np.abs(actual - pred)) / denom) if denom else np.nan


def _mape(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = actual != 0
    return float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask]))) if mask.any() else np.nan


def rolling_origin_validate(series: pd.Series, horizon=3, min_train=8) -> pd.DataFrame:
    """Evaluate each model on rolling-origin folds and return per-model metrics."""
    rows = []
    n = len(series)
    for name, fn in MODELS.items():
        errors_abs, errors_signed, actual_all, pred_all = [], [], [], []
        for cut in range(min_train, n - horizon + 1):
            train = series.iloc[:cut]
            actual = series.iloc[cut:cut + horizon].values
            pred = np.asarray(fn(train, horizon))
            errors_abs.append(np.abs(actual - pred))
            errors_signed.append(actual - pred)
            actual_all.append(actual)
            pred_all.append(pred)
        if not actual_all:
            continue
        actual_all = np.concatenate(actual_all)
        pred_all = np.concatenate(pred_all)
        rows.append(dict(
            model=name,
            mae=float(np.mean(np.abs(actual_all - pred_all))),
            rmse=float(np.sqrt(np.mean((actual_all - pred_all) ** 2))),
            mape=_mape(actual_all, pred_all),
            wape=_wape(actual_all, pred_all),
            bias=float(np.mean(pred_all - actual_all)),
        ))
    return pd.DataFrame(rows).sort_values("wape")


def forecast_series(series: pd.Series, horizon=12) -> dict:
    """Validate models, pick the best by WAPE, and produce the final forecast
    plus a simple residual-based prediction interval."""
    val = rolling_origin_validate(series, horizon=3, min_train=max(8, len(series) - 6))
    if val.empty:
        best_name = "moving_average"
    else:
        best_name = val.iloc[0].model
    best_fn = MODELS[best_name]
    point_forecast = np.asarray(best_fn(series, horizon))
    point_forecast = np.clip(point_forecast, a_min=0, a_max=None)

    # residual std from one-step-ahead in-sample errors, for a rough interval
    resid = []
    for cut in range(max(6, len(series) - 8), len(series) - 1):
        pred1 = np.asarray(best_fn(series.iloc[:cut], 1))[0]
        resid.append(series.iloc[cut] - pred1)
    resid_std = float(np.std(resid)) if len(resid) > 1 else float(series.std() * 0.1)

    growth = np.linspace(1, 1.6, horizon)  # widen interval further out
    lower = np.clip(point_forecast - 1.28 * resid_std * growth, 0, None)
    upper = point_forecast + 1.28 * resid_std * growth

    return dict(
        model_selected=best_name,
        validation=val.to_dict(orient="records"),
        point_forecast=point_forecast.tolist(),
        lower_80=lower.tolist(),
        upper_80=upper.tolist(),
    )


def build_forecast_table(monthly: pd.DataFrame, horizon=12) -> tuple[pd.DataFrame, dict]:
    monthly = monthly.sort_values("month").reset_index(drop=True)
    last_month = monthly.month.max()
    future_months = pd.date_range(last_month + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")

    metrics = ["delivered_orders", "gmv", "platform_revenue", "contribution_profit"]
    results = {}
    frames = []
    for metric in metrics:
        series = monthly.set_index("month")[metric]
        out = forecast_series(series, horizon=horizon)
        results[metric] = out
        frames.append(pd.DataFrame({
            "month": future_months,
            "metric": metric,
            "point_forecast": out["point_forecast"],
            "lower_80": out["lower_80"],
            "upper_80": out["upper_80"],
        }))
    forecast_df = pd.concat(frames, ignore_index=True)
    return forecast_df, results


def scenario_cases(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """Base / Upside / Downside cases as +/- adjustments around the point forecast."""
    df = forecast_df.copy()
    df["base_case"] = df.point_forecast
    df["upside_case"] = df.point_forecast * 1.12
    df["downside_case"] = df.point_forecast * 0.85
    return df
