from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def ist_now() -> datetime:
    return datetime.now(tz=IST)


def to_ist_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(IST).isoformat()
