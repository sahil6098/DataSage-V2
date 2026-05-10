from datetime import date, datetime
from decimal import Decimal

from bson import ObjectId
import pandas as pd


def normalize_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat()
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize_value(item) for item in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        try:
            converted = value.tolist()
        except Exception:
            converted = None
        if converted is not None and converted is not value:
            return normalize_value(converted)
    missing = pd.isna(value)
    if not hasattr(missing, "__len__") and bool(missing):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value
