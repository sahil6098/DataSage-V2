"""
forecast_service.py — Time-series forecasting using statsmodels ExponentialSmoothing.
Falls back to simple linear extrapolation if statsmodels is unavailable.
"""
from __future__ import annotations

import math
from typing import Any


class ForecastService:
    """Generate short-horizon forecasts for time-series numeric data."""

    MIN_POINTS = 6      # minimum history points required
    DEFAULT_N = 7       # default forecast horizon
    CI_FACTOR = 1.645   # ~90% confidence interval

    def forecast_series(
        self,
        values: list[float],
        n_future: int = DEFAULT_N,
    ) -> dict:
        """
        Forecast `n_future` future points from a list of historical values.

        Returns:
            {
                "forecast": [float, ...],      # predicted values
                "lower_ci": [float, ...],      # lower confidence bound
                "upper_ci": [float, ...],      # upper confidence bound
                "method": str,                 # algorithm used
                "can_forecast": bool,
                "summary": str,                # human-readable insight
            }
        """
        clean = [v for v in values if v is not None and math.isfinite(v)]
        if len(clean) < self.MIN_POINTS:
            return self._no_forecast(f"Need at least {self.MIN_POINTS} data points; only {len(clean)} provided.")

        n_future = max(1, min(n_future, 15))

        # Try statsmodels first
        try:
            return self._exponential_smoothing(clean, n_future)
        except Exception:
            pass

        # Fallback: simple linear trend extrapolation
        return self._linear_extrapolation(clean, n_future)

    # ── Exponential Smoothing (statsmodels) ─────────────────────────────── #

    def _exponential_smoothing(self, values: list[float], n: int) -> dict:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore
        import numpy as np  # type: ignore

        arr = np.array(values, dtype=float)
        # Choose trend/seasonal params based on series length
        trend = "add" if len(values) >= 8 else None
        seasonal = None  # skip seasonal to keep it lightweight

        model = ExponentialSmoothing(arr, trend=trend, seasonal=seasonal)
        fit = model.fit(optimized=True, disp=False)
        fcast = fit.forecast(n)

        # Compute residual std for CI
        residuals = arr - fit.fittedvalues
        resid_std = float(np.std(residuals)) if len(residuals) > 1 else 0.0

        forecast_vals = [round(float(v), 4) for v in fcast]
        lower = [round(v - self.CI_FACTOR * resid_std, 4) for v in forecast_vals]
        upper = [round(v + self.CI_FACTOR * resid_std, 4) for v in forecast_vals]

        last_val = values[-1]
        projected = forecast_vals[-1]
        pct_change = ((projected - last_val) / abs(last_val) * 100) if last_val != 0 else 0
        direction = "increase" if pct_change > 0 else "decrease"

        summary = (
            f"Forecast ({n} periods): projected {direction} of {abs(pct_change):.1f}% "
            f"from {last_val:,.2f} to ~{projected:,.2f}. "
            f"90% CI: [{lower[-1]:,.2f} – {upper[-1]:,.2f}]."
        )

        return {
            "forecast": forecast_vals,
            "lower_ci": lower,
            "upper_ci": upper,
            "method": "ExponentialSmoothing",
            "can_forecast": True,
            "summary": summary,
        }

    # ── Linear Extrapolation Fallback ────────────────────────────────────── #

    def _linear_extrapolation(self, values: list[float], n: int) -> dict:
        x_vals = list(range(len(values)))
        x_mean = sum(x_vals) / len(x_vals)
        y_mean = sum(values) / len(values)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, values))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        base_x = len(values)
        forecast_vals = [round(intercept + slope * (base_x + i), 4) for i in range(n)]

        # Estimate error as residual std
        residuals = [values[i] - (intercept + slope * i) for i in x_vals]
        resid_std = math.sqrt(sum(r ** 2 for r in residuals) / len(residuals))

        lower = [round(v - self.CI_FACTOR * resid_std, 4) for v in forecast_vals]
        upper = [round(v + self.CI_FACTOR * resid_std, 4) for v in forecast_vals]

        last_val = values[-1]
        projected = forecast_vals[-1]
        pct_change = ((projected - last_val) / abs(last_val) * 100) if last_val != 0 else 0
        direction = "increase" if pct_change > 0 else "decrease"

        summary = (
            f"Forecast ({n} periods, linear trend): projected {direction} of "
            f"{abs(pct_change):.1f}% from {last_val:,.2f} to ~{projected:,.2f}."
        )

        return {
            "forecast": forecast_vals,
            "lower_ci": lower,
            "upper_ci": upper,
            "method": "LinearTrend",
            "can_forecast": True,
            "summary": summary,
        }

    def _no_forecast(self, reason: str) -> dict:
        return {
            "forecast": [],
            "lower_ci": [],
            "upper_ci": [],
            "method": "none",
            "can_forecast": False,
            "summary": reason,
        }

    # ── Time-series detection helper ─────────────────────────────────────── #

    def extract_time_series(self, rows: list[dict]) -> dict | None:
        """
        Detect if `rows` represent a time series (one label column + one numeric column).
        Returns {"labels": [...], "values": [...], "value_key": str, "label_key": str} or None.
        """
        if not rows or len(rows) < self.MIN_POINTS:
            return None

        keys = list(rows[0].keys())
        if len(keys) < 2:
            return None

        import re
        TIME_PATTERN = re.compile(
            r"\b(date|time|month|year|week|day|quarter|period|timestamp)\b", re.I
        )

        label_key = None
        value_key = None

        for k in keys:
            if TIME_PATTERN.search(k):
                label_key = k
                break

        if label_key is None:
            # Fall back: first non-numeric col as label
            for k in keys:
                vals = [rows[i].get(k) for i in range(min(3, len(rows)))]
                if not all(self._to_float(v) is not None for v in vals):
                    label_key = k
                    break

        if label_key is None:
            return None

        # Find a numeric value key
        for k in keys:
            if k == label_key:
                continue
            sample = [rows[i].get(k) for i in range(min(5, len(rows)))]
            if sum(1 for v in sample if self._to_float(v) is not None) >= len(sample) // 2 + 1:
                value_key = k
                break

        if value_key is None:
            return None

        values = [self._to_float(row.get(value_key)) for row in rows]
        labels = [str(row.get(label_key, "")) for row in rows]

        # Only keep rows with valid numeric values
        clean_pairs = [(lbl, v) for lbl, v in zip(labels, values) if v is not None]
        if len(clean_pairs) < self.MIN_POINTS:
            return None

        clean_labels, clean_values = zip(*clean_pairs)
        return {
            "labels": list(clean_labels),
            "values": list(clean_values),
            "value_key": value_key,
            "label_key": label_key,
        }

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
        if isinstance(value, str):
            try:
                f = float(value.replace(",", "").replace("$", "").strip())
                return f if math.isfinite(f) else None
            except (ValueError, AttributeError):
                return None
        return None
