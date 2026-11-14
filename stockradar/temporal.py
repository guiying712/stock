"""Effective interval parsing shared by transport and strategy layers."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def effective_boundary(value):
    """Return a UTC instant; civil dates begin at midnight in Shanghai.

    None denotes an open boundary. Explicit instants must carry UTC, matching
    the transport contract. Parsing never rewrites the source record.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("有效边界需要 YYYY-MM-DD 日期或 UTC 时间")
    if len(value) == 10:
        parsed = datetime.combine(date.fromisoformat(value), time(), ZoneInfo("Asia/Shanghai"))
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("有效边界时间必须使用 UTC")
    return parsed.astimezone(timezone.utc)


def effective_interval(record):
    start = effective_boundary(record.get("valid_from"))
    end = effective_boundary(record.get("valid_to"))
    if start is not None and end is not None and start >= end:
        raise ValueError("有效区间起点必须早于终点")
    return start, end
