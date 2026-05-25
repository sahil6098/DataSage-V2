from pathlib import Path

import pandas as pd

from app.utils.serialization import normalize_value


SUPPORTED_FILE_TYPES = {
    ".csv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
}


def detect_source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FILE_TYPES:
        raise ValueError("Unsupported file type.")
    return SUPPORTED_FILE_TYPES[suffix]


def _clean_table_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char == "_" else "_" for char in name.strip())
    cleaned = cleaned.strip("_") or "data"
    if cleaned[0].isdigit():
        cleaned = f"table_{cleaned}"
    return cleaned


def load_tabular_source(path: Path, display_name: str | None = None) -> dict[str, pd.DataFrame]:
    source_type = detect_source_type(path)
    if source_type == "csv":
        table_source = Path(display_name).stem if display_name else path.stem
        return {_clean_table_name(table_source): pd.read_csv(path)}
    if source_type == "parquet":
        table_source = Path(display_name).stem if display_name else path.stem
        return {_clean_table_name(table_source): pd.read_parquet(path)}
    workbook = pd.read_excel(path, sheet_name=None)
    return {_clean_table_name(sheet_name): dataframe for sheet_name, dataframe in workbook.items()}


def infer_series_type(series: pd.Series) -> str:
    dtype = str(series.dtype).lower()
    if "int" in dtype:
        return "integer"
    if "float" in dtype or "double" in dtype:
        return "float"
    if "bool" in dtype:
        return "boolean"
    if "datetime" in dtype or "date" in dtype:
        return "datetime"
    return "string"


def dataframe_preview_fields(df: pd.DataFrame, field_descriptions: dict[str, str] | None = None) -> list[dict]:
    field_descriptions = field_descriptions or {}
    fields: list[dict] = []
    for column in df.columns:
        series = df[column]
        non_null = series.dropna().head(3).tolist()
        fields.append(
            {
                "name": str(column),
                "type": infer_series_type(series),
                "nullable": bool(series.isna().any()),
                "samples": [str(normalize_value(value)) for value in non_null],
                "description": field_descriptions.get(str(column)),
            }
        )
    return fields


def dataframe_rows(df: pd.DataFrame, limit: int) -> list[dict]:
    subset = df.head(limit).copy()
    subset = subset.where(pd.notnull(subset), None)
    return [
        {str(column): normalize_value(value) for column, value in row.items()}
        for row in subset.to_dict(orient="records")
    ]
