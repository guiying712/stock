"""Small strict validators for explicit research and operational contracts."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path


def fields(value, keys, path):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(path + "字段必须完整且不得含未知键")


def string(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(path + "需要非空字符串")
    return value


def integer(value, low, high, path):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(path + "整数超出允许范围")
    return value


def numeric(value, path, low=Decimal(0), high=None, nullable=False):
    if value is None and nullable:
        return None
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or result < low or (high is not None and result > high):
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(path + "需要范围内的有限数值") from None


def utc(value):
    string(value, "UTC时间")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except ValueError:
        raise ValueError("需要带UTC时区的ISO时间") from None


def day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("需要YYYY-MM-DD日期")
    return date.fromisoformat(value)


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("JSON含重复键")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("JSON禁止NaN或Infinity")
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def write_new_json(path, report):
    """Never overwrite an existing experiment/evidence artifact."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
