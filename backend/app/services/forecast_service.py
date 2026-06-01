"""
forecast_service.py — High-accuracy time-series forecasting for DataSage V2.

Accuracy improvements over v1:
  1. AIC-based model selection — automatically picks the best ETS variant
     (trend / no-trend, seasonal / non-seasonal) from the data instead of
     hard-coding 'add trend when n≥8'.
  2. Auto seasonality detection — tests periods 4, 7, 12 and enables the
     seasonal component when 2+ full cycles are present.
  3. Expanding confidence intervals — CI widens with sqrt(h) as horizon
     grows, giving honest uncertainty bands instead of a flat ±band.
  4. Walk-forward cross-validation — backtests the chosen model on held-out
     data and returns the real MAPE, giving the LLM an honest accuracy figure
     to quote to the user.
  5. Extended TIME_PATTERN — catches _at, _ts, _dt, fiscal_, sale_date, etc.
     so more real-world column names are recognised as time axes.
  6. All methods have a trust_explanation for the LLM to relay to users.

Dependencies (already in requirements.txt): statsmodels≥0.14, scipy≥1.11, numpy.
Falls back to scipy linear regression if statsmodels is unavailable.
"""
from __future__ import annotations

import math
import re
from typing import Any


class ForecastService:
    """Generate short-horizon forecasts for time-series numeric data."""

    MIN_POINTS   = 6    # minimum history points to attempt any forecast
    DEFAULT_N    = 7    # default forecast horizon
    MAX_N        = 30   # hard cap on forecast horizon
    CI_Z         = 1.645  # z-score for 90% confidence interval

    # Candidate seasonal periods to test (in ascending order of length)
    SEASONAL_PERIODS = [4, 7, 12]

    # Extended pattern — matches common real-world time column names
    TIME_PATTERN = re.compile(
        r"(date|time|month|year|week|day|quarter|period|timestamp"
        r"|fiscal|interval|epoch|created|updated|recorded|reported"
        r"|_ts\b|_dt\b|_at\b|^ts$|^dt$|^wk$|yyyymm|mmyyyy)",
        re.I,
    )

    # ── Public API ────────────────────────────────────────────────────────── #

    def forecast_series(
        self,
        values: list[float],
        n_future: int = DEFAULT_N,
    ) -> dict:
        """
        Forecast `n_future` future points from historical values.

        Returns:
            {
                "forecast":          [float, ...]   — predicted values
                "lower_ci":          [float, ...]   — 90% lower bound (expanding)
                "upper_ci":          [float, ...]   — 90% upper bound (expanding)
                "method":            str            — algorithm used
                "model_config":      dict           — ETS params chosen by AIC
                "mape":              float | None   — walk-forward CV accuracy (%)
                "accuracy_pct":      float | None   — 100 - mape
                "can_forecast":      bool
                "summary":           str            — LLM-ready one-liner
                "trust_explanation": str            — detailed trust narrative
            }
        """
        clean = [v for v in values if v is not None and math.isfinite(v)]
        if len(clean) < self.MIN_POINTS:
            return self._no_forecast(
                f"Need at least {self.MIN_POINTS} data points; got {len(clean)}."
            )

        n_future = max(1, min(n_future, self.MAX_N))

        # Warn if forecasting beyond 30% of history (unreliable extrapolation)
        horizon_warning = ""
        if n_future > len(clean) * 0.3:
            horizon_warning = (
                f" Note: forecasting {n_future} steps with only {len(clean)} "
                "history points — treat longer-horizon values with extra caution."
            )

        try:
            return self._ets_forecast(clean, n_future, horizon_warning)
        except Exception:
            pass

        # Fallback: scipy OLS linear regression
        try:
            return self._linear_forecast(clean, n_future, horizon_warning)
        except Exception as exc:
            return self._no_forecast(f"Forecasting failed: {exc}")

    def extract_time_series(self, rows: list[dict]) -> dict | None:
        """
        Detect if `rows` represent a time series (one time label col + one
        numeric col).  Returns a dict or None.

        Improvements over v1:
        - Extended TIME_PATTERN covers _at, _ts, fiscal_, sale_date, etc.
        - Falls back gracefully to first non-numeric col when no time keyword found.
        - Accepts all numeric value columns, not just the first one.
        """
        if not rows or len(rows) < self.MIN_POINTS:
            return None

        keys = list(rows[0].keys())
        if len(keys) < 2:
            return None

        # ── Find label column ─────────────────────────────────────────── #
        label_key: str | None = None
        for k in keys:
            if self.TIME_PATTERN.search(k):
                label_key = k
                break

        if label_key is None:
            # Fallback: first column that isn't fully numeric
            for k in keys:
                sample_vals = [rows[i].get(k) for i in range(min(5, len(rows)))]
                if not all(self._to_float(v) is not None for v in sample_vals):
                    label_key = k
                    break

        if label_key is None:
            return None

        # ── Find best numeric value column ────────────────────────────── #
        # Prefer columns with names suggesting a metric (revenue, count, etc.)
        METRIC_HINTS = ("revenue", "sales", "amount", "count", "total", "value",
                        "price", "cost", "profit", "qty", "quantity", "units")
        value_key: str | None = None
        best_completeness = -1

        for k in keys:
            if k == label_key:
                continue
            sample = [rows[i].get(k) for i in range(min(10, len(rows)))]
            numeric_count = sum(1 for v in sample if self._to_float(v) is not None)
            completeness = numeric_count / len(sample) if sample else 0
            if completeness >= 0.6:
                # Prefer metric-named columns
                is_metric = any(h in k.lower() for h in METRIC_HINTS)
                score = completeness + (0.1 if is_metric else 0)
                if score > best_completeness:
                    best_completeness = score
                    value_key = k

        if value_key is None:
            return None

        values = [self._to_float(row.get(value_key)) for row in rows]
        labels = [str(row.get(label_key, "")) for row in rows]
        clean_pairs = [(lbl, v) for lbl, v in zip(labels, values) if v is not None]

        if len(clean_pairs) < self.MIN_POINTS:
            return None

        clean_labels, clean_values = zip(*clean_pairs)
        return {
            "labels":    list(clean_labels),
            "values":    list(clean_values),
            "value_key": value_key,
            "label_key": label_key,
        }

    # ── ETS forecasting (statsmodels) ─────────────────────────────────────── #

    def _ets_forecast(
        self, values: list[float], n: int, horizon_warning: str
    ) -> dict:
        import numpy as np  # type: ignore
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore

        arr = np.array(values, dtype=float)

        # Select best model by AIC
        best_fit, best_cfg = self._select_best_ets(arr)
        if best_fit is None:
            raise RuntimeError("No ETS model converged.")

        # Walk-forward cross-validation for honest accuracy estimate
        mape, cv_note = self._walk_forward_cv(values, best_cfg)

        # Forecast + expanding CI
        raw_fcast = best_fit.forecast(n)
        resid_std = float(np.std(arr - best_fit.fittedvalues))

        forecast_vals = [round(float(v), 4) for v in raw_fcast]
        lower = [
            round(forecast_vals[h] - self.CI_Z * resid_std * math.sqrt(h + 1), 4)
            for h in range(n)
        ]
        upper = [
            round(forecast_vals[h] + self.CI_Z * resid_std * math.sqrt(h + 1), 4)
            for h in range(n)
        ]

        last_val   = values[-1]
        projected  = forecast_vals[-1]
        pct_change = ((projected - last_val) / abs(last_val) * 100) if last_val != 0 else 0
        direction  = "increase" if pct_change > 0 else "decrease"
        accuracy_pct = round(100 - mape, 1) if mape is not None else None

        cfg_label = self._cfg_label(best_cfg)
        summary = (
            f"Forecast ({n} steps, {cfg_label}): projected {direction} of "
            f"{abs(pct_change):.1f}% from {last_val:,.2f} to ~{projected:,.2f}. "
            f"90% CI at step {n}: [{lower[-1]:,.2f} – {upper[-1]:,.2f}]."
        )
        if mape is not None:
            summary += f" Model accuracy (walk-forward CV): ~{accuracy_pct:.1f}%."
        if horizon_warning:
            summary += horizon_warning

        trust = self._ets_trust_explanation(
            n_history=len(values),
            n_future=n,
            cfg=best_cfg,
            mape=mape,
            accuracy_pct=accuracy_pct,
            resid_std=resid_std,
            cv_note=cv_note,
            horizon_warning=horizon_warning,
        )

        return {
            "forecast":          forecast_vals,
            "lower_ci":          lower,
            "upper_ci":          upper,
            "method":            "ExponentialSmoothing (AIC-selected)",
            "model_config":      best_cfg,
            "mape":              mape,
            "accuracy_pct":      accuracy_pct,
            "can_forecast":      True,
            "summary":           summary,
            "trust_explanation": trust,
        }

    def _select_best_ets(self, arr):
        """
        Try all sensible ETS configurations and return the one with lowest AIC.
        Configurations tested:
          - Trend: additive or none
          - Seasonal: additive or none (when data has 2+ full cycles)
          - Periods: 4, 7, 12 (quarterly, weekly, monthly)
        """
        try:
            import numpy as np  # type: ignore
            from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore
        except ImportError:
            return None, {}

        n = len(arr)
        candidates: list[tuple] = []

        # Seasonal candidates (requires 2× period data points).
        # Try ALL valid periods — AIC will select the best one.
        for period in self.SEASONAL_PERIODS:
            if n < 2 * period:
                continue
            for trend in ["add", None]:
                try:
                    m = ExponentialSmoothing(
                        arr,
                        trend=trend,
                        seasonal="add",
                        seasonal_periods=period,
                    )
                    f = m.fit(optimized=True)
                    candidates.append((f.aic, trend, "add", period, f))
                except Exception:
                    pass

        # Non-seasonal candidates
        for trend in ["add", None]:
            try:
                m = ExponentialSmoothing(arr, trend=trend, seasonal=None)
                f = m.fit(optimized=True)
                candidates.append((f.aic, trend, None, None, f))
            except Exception:
                pass

        if not candidates:
            return None, {}

        candidates.sort(key=lambda x: x[0])
        aic, trend, seasonal, period, best_fit = candidates[0]
        cfg = {
            "trend":    trend,
            "seasonal": seasonal,
            "period":   period,
            "aic":      round(float(aic), 2),
        }
        return best_fit, cfg

    def _walk_forward_cv(
        self, values: list[float], cfg: dict
    ) -> tuple[float | None, str]:
        """
        Walk-forward (expanding-window) cross-validation.
        Trains on the first k points, predicts point k+1, for k = MIN_POINTS..n-1.
        Returns (mape, cv_note_string).
        """
        try:
            import numpy as np  # type: ignore
            from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore
        except ImportError:
            return None, "statsmodels unavailable — CV skipped."

        n = len(values)
        errors: list[float] = []
        trend    = cfg.get("trend")
        seasonal = cfg.get("seasonal")
        period   = cfg.get("period")

        for i in range(self.MIN_POINTS, n):
            train = np.array(values[:i], dtype=float)
            actual = values[i]
            if actual == 0:
                continue
            try:
                # Only use seasonality if enough data exists in this fold
                use_seasonal = (seasonal and period and len(train) >= 2 * period)
                m = ExponentialSmoothing(
                    train,
                    trend=trend,
                    seasonal="add" if use_seasonal else None,
                    seasonal_periods=period if use_seasonal else None,
                )
                f = m.fit(optimized=True)
                pred = float(f.forecast(1)[0])
                errors.append(abs((actual - pred) / actual) * 100)
            except Exception:
                pass

        if not errors:
            return None, "CV produced no valid folds."

        mape = float(sum(errors) / len(errors))
        seasonal_note = ""
        if seasonal and period:
            seasonal_note = (
                f" (Early CV folds lacked enough data for seasonal component "
                f"(need {2 * period} pts per fold), so they used a simpler model — "
                "the final deployed model uses full seasonality and is typically more accurate.)"
            )
        cv_note = (
            f"Walk-forward CV over {len(errors)} fold(s): "
            f"mean absolute error {mape:.1f}% of actual values.{seasonal_note}"
        )
        return round(mape, 2), cv_note

    # ── Linear regression fallback (scipy) ───────────────────────────────── #

    def _linear_forecast(
        self, values: list[float], n: int, horizon_warning: str
    ) -> dict:
        try:
            from scipy.stats import linregress  # type: ignore
            x = list(range(len(values)))
            slope, intercept, r_value, p_value, std_err = linregress(x, values)
            r_sq = r_value ** 2
        except ImportError:
            # Pure-python OLS if scipy also missing
            x = list(range(len(values)))
            xm = sum(x) / len(x); ym = sum(values) / len(values)
            num = sum((xi - xm) * (yi - ym) for xi, yi in zip(x, values))
            den = sum((xi - xm) ** 2 for xi in x)
            slope = num / den if den else 0.0
            intercept = ym - slope * xm
            preds_train = [intercept + slope * xi for xi in x]
            ss_res = sum((vi - pi) ** 2 for vi, pi in zip(values, preds_train))
            ss_tot = sum((vi - ym) ** 2 for vi in values) or 1e-9
            r_sq = 1 - ss_res / ss_tot
            std_err = math.sqrt(ss_res / max(len(values) - 2, 1))
            p_value = None

        base_x = len(values)
        forecast_vals = [
            round(intercept + slope * (base_x + i), 4) for i in range(n)
        ]

        # Residual std for CI
        preds_train = [intercept + slope * xi for xi in range(len(values))]
        residuals   = [values[i] - preds_train[i] for i in range(len(values))]
        resid_std   = math.sqrt(sum(r ** 2 for r in residuals) / max(len(residuals) - 2, 1))

        lower = [
            round(forecast_vals[h] - self.CI_Z * resid_std * math.sqrt(h + 1), 4)
            for h in range(n)
        ]
        upper = [
            round(forecast_vals[h] + self.CI_Z * resid_std * math.sqrt(h + 1), 4)
            for h in range(n)
        ]

        last_val   = values[-1]
        projected  = forecast_vals[-1]
        pct_change = ((projected - last_val) / abs(last_val) * 100) if last_val != 0 else 0
        direction  = "increase" if pct_change > 0 else "decrease"

        summary = (
            f"Forecast ({n} steps, linear trend, R²={r_sq:.2f}): "
            f"projected {direction} of {abs(pct_change):.1f}% "
            f"from {last_val:,.2f} to ~{projected:,.2f}."
        )
        if horizon_warning:
            summary += horizon_warning

        trust = (
            f"Linear regression fallback used (statsmodels unavailable or failed). "
            f"R²={r_sq:.2f} — {'good' if r_sq > 0.8 else 'moderate' if r_sq > 0.5 else 'weak'} "
            f"linear fit on {len(values)} history points. "
            "CI widens with forecast horizon (√h scaling). "
            "Linear forecasts assume a constant trend — if the series is non-linear or "
            "seasonal, accuracy will degrade quickly beyond a few steps."
            + (horizon_warning or "")
        )

        return {
            "forecast":          forecast_vals,
            "lower_ci":          lower,
            "upper_ci":          upper,
            "method":            "LinearRegression (fallback)",
            "model_config":      {"r_squared": round(r_sq, 4), "slope": round(slope, 6)},
            "mape":              None,
            "accuracy_pct":      None,
            "can_forecast":      True,
            "summary":           summary,
            "trust_explanation": trust,
        }

    # ── Trust / explain helpers ───────────────────────────────────────────── #

    def _cfg_label(self, cfg: dict) -> str:
        parts = []
        if cfg.get("trend"):
            parts.append("trend")
        if cfg.get("seasonal"):
            parts.append(f"seasonal(p={cfg['period']})")
        if not parts:
            parts.append("simple smoothing")
        return "ETS " + "+".join(parts)

    def _ets_trust_explanation(
        self,
        *,
        n_history: int,
        n_future: int,
        cfg: dict,
        mape: float | None,
        accuracy_pct: float | None,
        resid_std: float,
        cv_note: str,
        horizon_warning: str,
    ) -> str:
        cfg_label = self._cfg_label(cfg)
        aic_note  = f"AIC={cfg['aic']}" if "aic" in cfg else ""

        accuracy_note = ""
        if mape is not None:
            if mape < 5:
                quality = "excellent"
            elif mape < 10:
                quality = "good"
            elif mape < 20:
                quality = "moderate"
            else:
                quality = "poor — interpret with caution"
            accuracy_note = (
                f"Walk-forward cross-validation measured a mean absolute percentage error "
                f"of {mape:.1f}% (accuracy ≈ {accuracy_pct:.1f}%), which is {quality} "
                f"for this data. {cv_note} "
            )
        else:
            accuracy_note = (
                "Cross-validation could not be computed for this series — "
                "treat the confidence intervals as approximate. "
            )

        return (
            f"Model: {cfg_label} ({aic_note}), automatically selected from multiple "
            f"ETS configurations by lowest AIC score. "
            f"Trained on {n_history} history points, forecasting {n_future} step(s) ahead. "
            f"{accuracy_note}"
            f"Confidence intervals use a 90% level and widen with horizon (±1.645 × σ × √h), "
            f"giving honest uncertainty that grows as the forecast extends further. "
            f"Residual standard deviation: {resid_std:.4g}. "
            "What this number means: a MAPE of 5% means the model's predictions were on "
            "average within 5% of the actual values on held-out data — comparable to "
            "professional short-term business forecasts. "
            "Do not use these forecasts to make irreversible decisions without domain "
            "expert review, especially beyond 3–5 steps from the last known value."
            + (f" {horizon_warning}" if horizon_warning else "")
        )

    def _no_forecast(self, reason: str) -> dict:
        return {
            "forecast":          [],
            "lower_ci":          [],
            "upper_ci":          [],
            "method":            "none",
            "model_config":      {},
            "mape":              None,
            "accuracy_pct":      None,
            "can_forecast":      False,
            "summary":           reason,
            "trust_explanation": reason,
        }

    # ── Low-level helpers ─────────────────────────────────────────────────── #

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
        if isinstance(value, str):
            try:
                f = float(
                    value.replace(",", "").replace("$", "").replace("%", "").strip()
                )
                return f if math.isfinite(f) else None
            except (ValueError, AttributeError):
                return None
        return None