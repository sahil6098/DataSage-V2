"""
anomaly_service.py — Local anomaly detection using Z-Score and IQR.
No external API calls. Pure pandas/numpy computation on query result rows.
"""
from __future__ import annotations

import math
from typing import Any


class AnomalyService:
    """Detect statistical outliers in query result rows using Z-Score and IQR."""

    ZSCORE_THRESHOLD = 2.5
    IQR_MULTIPLIER = 1.5
    MIN_POINTS = 5  # need at least this many numeric values to run detection

    def detect_anomalies(self, rows: list[dict]) -> dict:
        """
        Run Z-Score + IQR detection on numeric columns in result rows.

        Returns:
            {
                "anomalies": [{"row_index": int, "field": str, "value": float, "zscore": float, "method": str}],
                "anomaly_indices": [int],  # unique row indices that are anomalous
                "summary": str,            # human-readable one-liner for LLM prompt injection
                "has_anomalies": bool,
            }
        """
        if not rows:
            return self._empty_result()

        # Collect numeric columns
        numeric_cols = self._get_numeric_columns(rows)
        if not numeric_cols:
            return self._empty_result()

        all_anomalies: list[dict] = []
        anomaly_indices: set[int] = set()

        for col in numeric_cols:
            values = []
            valid_indices = []
            for i, row in enumerate(rows):
                raw = row.get(col)
                n = self._to_float(raw)
                if n is not None:
                    values.append(n)
                    valid_indices.append(i)

            if len(values) < self.MIN_POINTS:
                continue

            # Z-Score detection
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = math.sqrt(variance) if variance > 0 else 0.0

            # IQR detection
            sorted_vals = sorted(values)
            q1 = self._percentile(sorted_vals, 25)
            q3 = self._percentile(sorted_vals, 75)
            iqr = q3 - q1
            iqr_lower = q1 - self.IQR_MULTIPLIER * iqr
            iqr_upper = q3 + self.IQR_MULTIPLIER * iqr

            for list_idx, (row_idx, val) in enumerate(zip(valid_indices, values)):
                methods: list[str] = []
                zscore = 0.0

                if std > 0:
                    zscore = abs(val - mean) / std
                    if zscore >= self.ZSCORE_THRESHOLD:
                        methods.append("z-score")

                if iqr > 0 and (val < iqr_lower or val > iqr_upper):
                    methods.append("iqr")

                if methods:
                    all_anomalies.append({
                        "row_index": row_idx,
                        "field": col,
                        "value": val,
                        "zscore": round(zscore, 2),
                        "method": " & ".join(methods),
                    })
                    anomaly_indices.add(row_idx)

        if not all_anomalies:
            return self._empty_result()

        # Build summary for LLM prompt (short, < 80 chars)
        unique_fields = list({a["field"] for a in all_anomalies})
        count = len(anomaly_indices)
        field_list = ", ".join(unique_fields[:3])
        if len(unique_fields) > 3:
            field_list += f" (+{len(unique_fields) - 3} more)"
        summary = (
            f"ANOMALY ALERT: {count} outlier row{'s' if count != 1 else ''} detected "
            f"in field{'s' if len(unique_fields) != 1 else ''}: {field_list}. "
            "Flag these in your response."
        )

        return {
            "anomalies": all_anomalies[:20],  # cap to avoid huge payloads
            "anomaly_indices": sorted(anomaly_indices),
            "summary": summary,
            "has_anomalies": True,
        }

    # ── Helpers ──────────────────────────────────────────────────────────── #

    def _get_numeric_columns(self, rows: list[dict]) -> list[str]:
        """Return column names where at least half the sampled rows are numeric."""
        if not rows:
            return []
        sample = rows[:20]
        cols = list(rows[0].keys())
        result = []
        for col in cols:
            numeric_count = sum(
                1 for row in sample
                if self._to_float(row.get(col)) is not None
            )
            if numeric_count >= max(1, len(sample) // 2):
                result.append(col)
        return result

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

    def _percentile(self, sorted_values: list[float], pct: float) -> float:
        if not sorted_values:
            return 0.0
        n = len(sorted_values)
        k = (n - 1) * pct / 100
        f = int(k)
        c = f + 1
        if c >= n:
            return sorted_values[-1]
        return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)

    def _empty_result(self) -> dict:
        return {
            "anomalies": [],
            "anomaly_indices": [],
            "summary": "",
            "has_anomalies": False,
        }
