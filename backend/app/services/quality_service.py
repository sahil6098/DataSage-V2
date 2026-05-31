"""
quality_service.py — Dataset quality report generator.
Computes missing values, duplicates, outliers, column types and a 0-100 quality score.
Runs synchronously via pandas; call from asyncio.to_thread where needed.
"""
from __future__ import annotations

import math
from typing import Any


class QualityService:
    """Compute a quality report for a tabular dataset (list of row dicts)."""

    MISSING_WEIGHT = 40
    DUPLICATE_WEIGHT = 30
    OUTLIER_WEIGHT = 30

    def compute_quality_report(self, rows: list[dict], table_name: str = "data") -> dict:
        """
        Returns:
            {
                "table_name": str,
                "total_rows": int,
                "total_columns": int,
                "missing_by_column": {col: {"count": int, "pct": float}},
                "duplicate_rows": int,
                "duplicate_pct": float,
                "outlier_columns": [str],
                "column_types": {col: "numeric" | "text" | "mixed" | "empty"},
                "quality_score": int (0-100),
                "quality_label": "Excellent" | "Good" | "Fair" | "Poor",
            }
        """
        if not rows:
            return self._empty_report(table_name)

        columns = list(rows[0].keys())
        total = len(rows)

        # --- Column types ---
        column_types: dict[str, str] = {}
        for col in columns:
            values = [row.get(col) for row in rows]
            column_types[col] = self._classify_column(values)

        # --- Missing values ---
        missing_by_column: dict[str, dict] = {}
        for col in columns:
            count = sum(1 for row in rows if row.get(col) is None or str(row.get(col, "")).strip() == "")
            missing_by_column[col] = {
                "count": count,
                "pct": round(count / total * 100, 1) if total else 0.0,
            }

        avg_missing_pct = (
            sum(v["pct"] for v in missing_by_column.values()) / len(missing_by_column)
            if missing_by_column else 0.0
        )

        # --- Duplicates ---
        seen: set[tuple] = set()
        duplicate_count = 0
        for row in rows:
            # Use a tuple of sorted items as a fingerprint
            key = tuple(str(row.get(c, "")) for c in columns)
            if key in seen:
                duplicate_count += 1
            seen.add(key)
        duplicate_pct = round(duplicate_count / total * 100, 1) if total else 0.0

        # --- Outlier columns (IQR) ---
        outlier_columns: list[str] = []
        numeric_cols = [c for c, t in column_types.items() if t == "numeric"]
        for col in numeric_cols:
            numeric_vals = [self._to_float(row.get(col)) for row in rows]
            numeric_vals = [v for v in numeric_vals if v is not None]
            if len(numeric_vals) < 5:
                continue
            sorted_v = sorted(numeric_vals)
            q1 = self._percentile(sorted_v, 25)
            q3 = self._percentile(sorted_v, 75)
            iqr = q3 - q1
            if iqr > 0:
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outlier_count = sum(1 for v in numeric_vals if v < lower or v > upper)
                if outlier_count / len(numeric_vals) > 0.05:  # >5% outlier rate
                    outlier_columns.append(col)

        outlier_ratio = len(outlier_columns) / max(1, len(numeric_cols)) * 100

        # --- Quality score ---
        missing_penalty = min(100, avg_missing_pct) * (self.MISSING_WEIGHT / 100)
        dup_penalty = min(100, duplicate_pct) * (self.DUPLICATE_WEIGHT / 100)
        outlier_penalty = min(100, outlier_ratio) * (self.OUTLIER_WEIGHT / 100)
        score = max(0, round(100 - missing_penalty - dup_penalty - outlier_penalty))

        label = (
            "Excellent" if score >= 85
            else "Good" if score >= 65
            else "Fair" if score >= 45
            else "Poor"
        )

        return {
            "table_name": table_name,
            "total_rows": total,
            "total_columns": len(columns),
            "missing_by_column": missing_by_column,
            "avg_missing_pct": round(avg_missing_pct, 1),
            "duplicate_rows": duplicate_count,
            "duplicate_pct": duplicate_pct,
            "outlier_columns": outlier_columns,
            "column_types": column_types,
            "quality_score": score,
            "quality_label": label,
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    def _classify_column(self, values: list) -> str:
        non_null = [v for v in values if v is not None and str(v).strip() != ""]
        if not non_null:
            return "empty"
        numeric = sum(1 for v in non_null if self._to_float(v) is not None)
        if numeric == len(non_null):
            return "numeric"
        if numeric == 0:
            return "text"
        return "mixed"

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

    def _empty_report(self, table_name: str) -> dict:
        return {
            "table_name": table_name,
            "total_rows": 0,
            "total_columns": 0,
            "missing_by_column": {},
            "avg_missing_pct": 0.0,
            "duplicate_rows": 0,
            "duplicate_pct": 0.0,
            "outlier_columns": [],
            "column_types": {},
            "quality_score": 100,
            "quality_label": "Excellent",
        }
