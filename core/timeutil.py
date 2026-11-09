from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NSE_CLOSE = time(15, 30)


def now_ist() -> datetime:
    return datetime.now(IST)


def parse_timestamp(value) -> datetime | None:
    """Parse an ISO timestamp; naive values (legacy records) are read as IST."""
    if value is None:
        return None
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    return ts.astimezone(IST)


def format_age(ts: datetime | None) -> str:
    if ts is None:
        return "unknown age"
    seconds = (now_ist() - ts).total_seconds()
    if seconds < 3600:
        return f"{max(int(seconds // 60), 0)} min ago"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.1f} h ago"
    return f"{int(seconds // 86400)} days ago"
