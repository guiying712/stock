"""Explicit, lossless input adapters. No data vendor is silently selected."""
import copy
import json
import math
import os
import re
import socket
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib import error, parse, request

from . import __version__
from .temporal import effective_interval
from .config import MARKET_PAIRS


class ProviderError(ValueError):
    def __init__(self, code, message, retryable=False, retry_after=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _bad(path, message):
    raise ProviderError("DATA_INVALID", "%s：%s" % (path, message))


def _required(obj, keys, path):
    if not isinstance(obj, dict):
        _bad(path, "必须为对象")
    missing = sorted(set(keys) - set(obj))
    if missing:
        _bad(path, "缺少字段 " + ", ".join(missing))


def _utc(value, path):
    if not isinstance(value, str):
        _bad(path, "需要带 UTC 时区的 ISO 时间字符串")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError()
    except (ValueError, AttributeError):
        _bad(path, "需要带 UTC 时区的 ISO 时间字符串")
    return parsed


def _day(value, path):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        date.fromisoformat(value)
    except (ValueError, TypeError):
        _bad(path, "需要 YYYY-MM-DD 日期")


def _number(value, path, positive=False):
    # Null is deliberately retained; the strategy decides whether it is required.
    if value is None:
        return
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or (positive and number <= 0):
            raise ValueError()
    except (InvalidOperation, ValueError, TypeError):
        _bad(path, "需要有限正数" if positive else "需要有限非负数")


def _effective_interval(record, path):
    try:
        effective_interval(record)
    except ValueError as exc:
        _bad(path, str(exc))


def _quote(quote, path):
    _required(quote, ["instrument_id", "open", "high", "low", "close", "prev_close",
                      "volume_shares", "amount_cny", "interval", "is_complete",
                      "event_time", "available_at", "ingested_at", "adjustment_factor",
                      "source", "quality", "revision"], path)
    if quote["interval"] != 60 or isinstance(quote["interval"], bool):
        _bad(path + ".interval", "首版只接受 60 秒切片")
    if type(quote["is_complete"]) is not bool:
        _bad(path + ".is_complete", "必须为布尔值")
    if type(quote["revision"]) is not int or quote["revision"] < 1:
        _bad(path + ".revision", "必须为正整数")
    for key in ("event_time", "available_at", "ingested_at"):
        _utc(quote[key], path + "." + key)
    for key in ("open", "high", "low", "close", "prev_close", "adjustment_factor"):
        _number(quote[key], path + "." + key, positive=True)
    for key in ("volume_shares", "amount_cny"):
        _number(quote[key], path + "." + key)
    if "execution" in quote:
        from .execution import validate_execution
        try:
            validate_execution(quote["execution"])
        except ValueError as exc:
            _bad(path + ".execution", str(exc))


def _daily(bar, path):
    _required(bar, ["instrument_id", "date", "high", "low", "close", "prev_close",
                    "amount_cny", "adjustment_factor", "available_at"], path)
    _day(bar["date"], path + ".date")
    _utc(bar["available_at"], path + ".available_at")
    for key in ("high", "low", "close", "prev_close", "adjustment_factor"):
        _number(bar[key], path + "." + key, positive=True)
    _number(bar["amount_cny"], path + ".amount_cny")


def validate_batch(batch):
    """Validate transport schema, preserving nulls and all original timestamps.

    Future availability and historical membership eligibility are strategy checks,
    not transport transformations. This function never fills missing quotes.
    """
    _required(batch, ["schema_version", "snapshot_id", "source", "simulated", "as_of", "units",
                      "calendar", "instruments", "sectors", "memberships", "quotes",
                      "daily_bars", "minute_history", "benchmark"], "batch")
    if batch["schema_version"] != 1 or type(batch["schema_version"]) is not int:
        _bad("schema_version", "不支持的 schema 版本")
    if type(batch["simulated"]) is not bool:
        _bad("simulated", "必须明确标记是否模拟数据")
    for key in ("snapshot_id", "source"):
        if not isinstance(batch[key], str) or not batch[key].strip():
            _bad(key, "不能为空")
    _utc(batch["as_of"], "as_of")
    if batch["units"] != {"volume": "shares", "amount": "CNY", "amount_mode": "cumulative"}:
        raise ProviderError("UNIT_MISMATCH", "单位必须为股、人民币元、截至同分钟累计成交额；禁止隐式换算")
    calendar = batch["calendar"]
    _required(calendar, ["version", "trading_dates", "sessions"], "calendar")
    if not isinstance(calendar["version"], str) or not calendar["version"]:
        _bad("calendar.version", "交易日历必须有版本")
    if not isinstance(calendar["trading_dates"], list) or not isinstance(calendar["sessions"], list):
        _bad("calendar", "交易日期和连续竞价时段必须为数组")
    for value in calendar["trading_dates"]:
        _day(value, "calendar.trading_dates")
    for session in calendar["sessions"]:
        if not isinstance(session, list) or len(session) != 2:
            _bad("calendar.sessions", "时段应为开始和结束时间")
        try:
            start, end = [datetime.strptime(v, "%H:%M").time() for v in session]
            if start >= end:
                raise ValueError()
        except (ValueError, TypeError):
            _bad("calendar.sessions", "时段需要有序 HH:MM 时间")
    for key in ("instruments", "sectors", "memberships", "quotes", "daily_bars", "minute_history"):
        if not isinstance(batch[key], list):
            _bad(key, "必须为数组")
    instruments, sectors = set(), set()
    for i, instrument in enumerate(batch["instruments"]):
        path = "instruments[%d]" % i
        _required(instrument, ["id", "code", "name", "exchange", "board", "listed_on", "status",
                               "valid_from", "valid_to", "available_at"], path)
        if not isinstance(instrument["id"], str) or not instrument["id"] or instrument["id"] in instruments:
            _bad(path + ".id", "证券 ID 需唯一且非空")
        instruments.add(instrument["id"])
        if not isinstance(instrument["code"], str) or not re.fullmatch(r"[0-9]{6}", instrument["code"]):
            _bad(path + ".code", "股票代码必须为保留前导零的六位字符串")
        if instrument["exchange"] not in ("SSE", "SZSE", "BSE"):
            _bad(path + ".exchange", "不支持的交易所标识")
        if instrument["board"] not in ("MAIN", "CHINEXT", "STAR", "BSE"):
            _bad(path + ".board", "不支持的上市板块")
        if (instrument["exchange"], instrument["board"]) not in MARKET_PAIRS + (("BSE", "BSE"),):
            _bad(path, "交易所与上市板块组合无效")
        if instrument["status"] not in ("active", "st", "suspended", "delisting", "delisted"):
            _bad(path + ".status", "不支持的证券状态")
        _day(instrument["listed_on"], path + ".listed_on")
        _utc(instrument["available_at"], path + ".available_at")
        _effective_interval(instrument, path)
    for i, sector in enumerate(batch["sectors"]):
        _required(sector, ["id", "name", "type"], "sectors[%d]" % i)
        if not isinstance(sector["id"], str) or not sector["id"] or sector["id"] in sectors:
            _bad("sectors.id", "板块 ID 需唯一且非空")
        sectors.add(sector["id"])
    for i, membership in enumerate(batch["memberships"]):
        path = "memberships[%d]" % i
        _required(membership, ["instrument_id", "sector_id", "valid_from", "valid_to", "available_at",
                               "provider", "snapshot_id"], path)
        if membership["instrument_id"] not in instruments or membership["sector_id"] not in sectors:
            _bad(path, "引用的证券或板块不存在")
        _utc(membership["available_at"], path + ".available_at")
        _effective_interval(membership, path)
    if "corporate_actions" in batch:
        from .execution import validate_action
        if not isinstance(batch["corporate_actions"], list):
            _bad("corporate_actions", "必须为数组")
        for action in batch["corporate_actions"]:
            try:
                validate_action(action)
            except ValueError as exc:
                _bad("corporate_actions", str(exc))
            if action["instrument_id"] not in instruments:
                _bad("corporate_actions", "证券引用不存在")
    for key in ("quotes", "minute_history", "daily_bars"):
        for i, item in enumerate(batch[key]):
            (_daily if key == "daily_bars" else _quote)(item, "%s[%d]" % (key, i))
            if item["instrument_id"] not in instruments:
                _bad("%s[%d].instrument_id" % (key, i), "证券不在基础资料中")
    benchmark = batch["benchmark"]
    _required(benchmark, ["id", "quote", "daily_bars", "minute_history"], "benchmark")
    if benchmark["quote"] is not None:
        _quote(benchmark["quote"], "benchmark.quote")
    for key in ("daily_bars", "minute_history"):
        if not isinstance(benchmark[key], list):
            _bad("benchmark." + key, "必须为数组")
        for i, item in enumerate(benchmark[key]):
            (_daily if key == "daily_bars" else _quote)(item, "benchmark.%s[%d]" % (key, i))
    return batch


def _loads(raw):
    def reject_constant(value):
        raise ValueError("nonfinite constant")
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError):
        raise ProviderError("DATA_INVALID", "输入不是有效的唯一键 JSON；不接受 NaN/Infinity") from None


class FixtureProvider:
    def __init__(self, version=2):
        if type(version) is not int or version not in (1, 2):
            raise ValueError("合成样例版本须为1或2")
        self.version = version

    def capabilities(self):
        return {"name": "合成验证数据", "type": "fixture", "simulated": True, "fixture_version": self.version,
                "scope": "synthetic_sample", "full_market_verified": False,
                "granularity_seconds": 60, "point_in_time": True,
                "authorization": "本项目合成数据；不是真实证券行情"}

    def iter_batches(self):
        from .fixtures import fixture_batches
        for batch in fixture_batches(self.version):
            yield validate_batch(copy.deepcopy(batch))


class JSONLProvider:
    def __init__(self, path, max_line_bytes=64 * 1024 * 1024):
        self.path = Path(path)
        self.max_line_bytes = max_line_bytes

    def capabilities(self):
        return {"name": self.path.name, "type": "jsonl", "scope": "dataset_declared",
                "full_market_verified": False, "granularity_seconds": 60,
                "point_in_time": "requires_dataset_audit", "authorization": "由数据提供方确认"}

    def iter_batches(self):
        try:
            with self.path.open("rb") as handle:
                line_number = 0
                while True:
                    line = handle.readline(self.max_line_bytes + 1)
                    if not line:
                        return
                    line_number += 1
                    if len(line) > self.max_line_bytes:
                        raise ProviderError("DATA_TOO_LARGE", "JSONL 第 %d 行超过大小上限" % line_number)
                    if not line.strip():
                        continue
                    try:
                        yield validate_batch(_loads(line))
                    except ProviderError as exc:
                        raise ProviderError(exc.code, "JSONL 第 %d 行：%s" % (line_number, exc.message)) from None
        except OSError:
            raise ProviderError("PROVIDER_UNAVAILABLE", "无法读取指定的行情文件") from None


class HTTPJSONProvider:
    """A user-configured standards gateway, not a built-in market data license."""
    def __init__(self, endpoint, token=None, timeout=10, max_bytes=64 * 1024 * 1024, opener=None):
        parsed = parse.urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ProviderError("CONFIG_INVALID", "行情网关必须为不含用户凭据或片段的 HTTPS URL")
        if parsed.query:
            raise ProviderError("CONFIG_INVALID", "行情网关 URL 不允许查询参数；令牌须通过请求头配置")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ProviderError("CONFIG_INVALID", "行情请求超时必须为有限正数")
        self._endpoint, self._token = endpoint, token
        self.timeout, self.max_bytes = timeout, max_bytes
        self._opener = opener or request.build_opener(_NoRedirect())

    def capabilities(self):
        return {"name": "标准行情网关", "type": "http_json", "scope": "provider_declared",
                "full_market_verified": False, "granularity_seconds": 60,
                "history_depth": None, "rate_limit": None, "latency_seconds": None,
                "authorization": "未核验；需服务商授权与全市场 PoC",
                "required": ["全市场基础资料", "交易日历", "历史板块成员", "复权因子", "分钟累计成交", "历史日线"]}

    def get_slice(self, as_of=None, universe=None):
        params = {}
        if as_of is not None:
            _utc(as_of, "as_of")
            params["as_of"] = as_of
        # The configured gateway must return the complete expected universe. An
        # instrument filter cannot silently turn a whole-market scan into a watchlist.
        if universe is not None:
            raise ProviderError("CONFIG_INVALID", "首版网关不接受缩小股票池的请求参数")
        url = self._endpoint + ("?" + parse.urlencode(params) if params else "")
        headers = {"Accept": "application/json", "User-Agent": "StockRadar/" + __version__}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        try:
            with self._opener.open(request.Request(url, headers=headers), timeout=self.timeout) as response:
                raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise ProviderError("DATA_TOO_LARGE", "行情响应超过大小上限")
        except error.HTTPError as exc:
            retry_after = None
            if exc.code == 429:
                try:
                    retry_after = max(0, min(3600, int(exc.headers.get("Retry-After", "60"))))
                except (ValueError, TypeError, AttributeError):
                    retry_after = 60
            raise ProviderError("PROVIDER_LIMITED" if exc.code == 429 else "PROVIDER_HTTP_ERROR",
                                "行情服务返回 HTTP %d" % exc.code, exc.code == 429 or exc.code >= 500,
                                retry_after) from None
        except (error.URLError, socket.timeout, TimeoutError, OSError):
            raise ProviderError("PROVIDER_UNAVAILABLE", "行情连接失败或超时；没有使用旧值替代", True) from None
        return validate_batch(_loads(raw))

    def fetch(self):
        return self.get_slice()


def record_batches(path, batches):
    """Atomically export canonical UTF-8 JSONL; never discard input timestamps."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    count = 0
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(target.parent),
                                         prefix=".recording-", delete=False) as handle:
            temp_path = Path(handle.name)
            for batch in batches:
                validate_batch(batch)
                handle.write(json.dumps(batch, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(target))
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return count
