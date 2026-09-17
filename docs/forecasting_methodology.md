# Forecasting Methodology

## Models compared

For each metric (delivered orders, GMV, platform revenue, contribution
profit), three candidate models are evaluated:

1. **Seasonal naive** — repeats the same month from the prior year.
2. **Moving average with trend** — trailing 3-month average plus the recent
   slope.
3. **Holt-Winters (exponential smoothing)** — additive, damped trend, additive
   seasonality when at least 24 months of history are available
   (`statsmodels.tsa.holtwinters.ExponentialSmoothing`).

## Validation: rolling-origin, not random split

Time series data must **not** be split randomly for validation — a model
trained partly on future months and tested on the past would look
artificially good. Instead, `rolling_origin_validate()` walks the origin
forward one month at a time, training on everything up to that origin and
scoring a short (3-month) holdout immediately after it. Errors are pooled
across every fold before computing metrics, which is the standard
"rolling-origin" or "walk-forward" approach for time-series model selection.

## Metrics

- **MAE** — mean absolute error
- **RMSE** — root mean squared error
- **MAPE** — mean absolute percentage error (undefined/skipped where actual = 0)
- **WAPE** — weighted absolute percentage error, `sum(|error|) / sum(|actual|)`;
  used as the primary selection metric because it is not distorted by
  low-volume months the way MAPE can be
- **Bias** — mean(forecast − actual), reported for transparency but not used
  for model selection

The model with the lowest WAPE per metric is selected
(`data/processed/forecast_model_selection.json` records the full comparison
table). In this dataset, Holt-Winters wins for every metric because the
series has both a clear trend and monthly seasonality that a naive or
moving-average model cannot capture.

## Prediction intervals

A rough 80% interval is built from the standard deviation of recent one-step-
ahead residuals from the selected model, widened linearly across the 12-month
horizon (uncertainty compounds the further out the forecast goes). This is a
simplified, residual-based interval — not a full state-space or bootstrap
interval — chosen so the interval construction stays transparent and fast to
recompute; the trade-off is documented here rather than presented as more
rigorous than it is.

## Scenario cases

`scenario_cases()` builds Base (the point forecast), Upside (+12%), and
Downside (−15%) cases around each metric's point forecast, for management
scenario planning (`Scenarios` sheet / dashboard section).
