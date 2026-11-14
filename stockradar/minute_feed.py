"""Explicit, bounded Tushare minute capture and read-only research projection."""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import uuid
from zoneinfo import ZoneInfo

from .contracts import day, fields, integer, utc
from .store import StoreError, dumps
from .vendor_samples import collect_samples, prepare_samples, validate_sample_plan, _read_probe


SHANGHAI = ZoneInfo("Asia/Shanghai")
MODES = {"latest": "minute_quotes", "session": "intraday", "history": "minute_history"}


class MinuteFeed:
    def __init__(self, directory, connections, clock=None):
        self.directory = Path(directory)
        self.connections = connections
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        self.active = None

    def _directory(self, create=False):
        if self.directory.is_symlink():
            raise ValueError("分钟数据目录不能为符号链接")
        if create:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.exists():
            info = self.directory.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("分钟数据目录需仅当前用户可访问")

    def _read(self, name):
        self._directory()
        try:
            fd = os.open(self.directory / name, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        except OSError:
            raise ValueError("分钟状态文件不可读取") from None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("分钟状态文件权限无效")
            raw = stream.read(16385)
            if len(raw) > 16384:
                raise ValueError("分钟状态文件过大")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("分钟状态含重复字段")
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("分钟状态版本无效")
        if not isinstance(value.get("id"), str) or not re.fullmatch(r"[0-9a-f]{32}", value["id"]):
            raise ValueError("分钟记录标识无效")
        if name == "latest.json":
            fields(value, ("schema_version", "id"), "分钟记录引用")
        else:
            expected = {"schema_version", "id", "mode", "started_at", "status"}
            if set(value) not in (expected, expected | {"completed_at"}):
                raise ValueError("分钟获取状态字段无效")
            if value["mode"] not in MODES or value["status"] not in {"running", "captured", "partial", "failed"}:
                raise ValueError("分钟获取状态无效")
            utc(value["started_at"])
            if "completed_at" in value:
                utc(value["completed_at"])
        return value

    def _write(self, name, value):
        self._directory(create=True)
        fd, temporary = tempfile.mkstemp(prefix=".write-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write((dumps(value) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def plan(self, value, identifier="tushare-minute-preview"):
        fields(value, ("schema_version", "mode", "symbols", "start_date", "end_date", "access_confirmed"), "分钟获取请求")
        integer(value["schema_version"], 1, 1, "分钟请求版本")
        mode = value["mode"]
        if not isinstance(mode, str) or mode not in MODES or type(value["access_confirmed"]) is not bool:
            raise ValueError("分钟模式或访问确认无效")
        if not isinstance(value["symbols"], list) or not 1 <= len(value["symbols"]) <= 3:
            raise ValueError("每次显式选择1至3只A股")
        symbols = []
        for symbol in value["symbols"]:
            if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}\.(SH|SZ)", symbol):
                raise ValueError("请使用六位代码和交易所后缀，例如600519.SH")
            board = "STAR" if symbol.startswith(("688", "689")) else "CHINEXT" if symbol.startswith(("300", "301")) else "MAIN"
            symbols.append({"symbol": symbol, "board": board})
        today = self.clock().astimezone(SHANGHAI).date()
        if mode == "history":
            start, end = day(value["start_date"]), day(value["end_date"])
            if end >= today:
                raise ValueError("历史分钟请选择已结束的日期；当日数据使用当日分钟")
        else:
            if value["start_date"] is not None or value["end_date"] is not None:
                raise ValueError("当日/最新分钟不接受历史日期，日期需为null")
            start = end = today
        profile = self.connections.market_status("tushare")
        confirmed = value["access_confirmed"] and profile["authorization"]["confirmed"]
        return validate_sample_plan({"schema_version": 1, "id": identifier, "purpose": "experimental", "provider": "tushare",
            "authorization": {"confirmed": confirmed, "reference":
                "用户在分钟行情页面确认以上证券、日期和接口可用于个人研究并显式获取；Tushare连接中另已确认账户访问依据。" if confirmed else None},
            "symbols": symbols, "datasets": [MODES[mode]], "start_date": start.isoformat(), "end_date": end.isoformat(),
            "request_interval_seconds": "6.1", "request_timeout_seconds": 15, "max_requests": 3})

    def prepare(self, value):
        return prepare_samples(self.plan(value), credentials_dir=self.connections.directory, environ=self.connections.environ)

    def fetch(self, value, *, opener=None, sleep=None):
        prepared = self.prepare(value)
        if prepared["reason_codes"]:
            raise StoreError("MINUTE_NOT_READY", "请先保存Tushare Token、确认账户访问依据，并勾选本次分钟接口的个人研究访问确认")
        if not self.lock.acquire(blocking=False):
            raise StoreError("MINUTE_BUSY", "分钟获取正在进行，请等待本次完成")
        fd = None
        try:
            try:
                import fcntl
            except ImportError:
                raise StoreError("MINUTE_PLATFORM_UNSUPPORTED", "当前系统不支持分钟采集所需的独占文件锁；本机记录仍可查看") from None
            self._directory(create=True)
            fd = os.open(self.directory / ".fetch.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise StoreError("MINUTE_BUSY", "另一个服务正在获取分钟，请等待本次完成") from None
            timestamp = self.clock()
            previous = self._read("attempt.json")
            if previous and (timestamp - utc(previous["started_at"])).total_seconds() < 60:
                raise StoreError("MINUTE_COOLDOWN", "两次分钟获取至少间隔60秒，请稍后再试")
            identifier = uuid.uuid4().hex
            plan = self.plan(value, "tushare-minute-" + identifier)
            attempt = {"schema_version": 1, "id": identifier, "mode": value["mode"],
                       "started_at": timestamp.isoformat(), "status": "running"}
            self._write("attempt.json", attempt)
            self.active = identifier
            kwargs = {"credentials_dir": self.connections.directory, "environ": self.connections.environ}
            if opener is not None:
                kwargs["opener"] = opener
            if sleep is not None:
                kwargs["sleep"] = sleep
            try:
                report = collect_samples(plan, self.directory / identifier, **kwargs)
                attempt["status"] = "captured" if report["bar_count"] and report["status"] == "sample_captured" else "partial" if report["bar_count"] else "failed"
                self._write("latest.json", {"schema_version": 1, "id": identifier})
            except Exception:
                attempt["status"] = "failed"
                raise StoreError("MINUTE_CAPTURE_FAILED", "分钟获取未完成，原始记录已保留；请检查连接或本机存储") from None
            finally:
                attempt["completed_at"] = self.clock().isoformat()
                self._write("attempt.json", attempt)
            return self.describe()
        finally:
            self.active = None
            if fd is not None:
                os.close(fd)
            self.lock.release()

    def describe(self):
        attempt = self._read("attempt.json")
        if attempt and attempt["status"] == "running" and attempt["id"] != self.active:
            attempt = dict(attempt, status="unfinished")
        result = {"schema_version": 1, "provider": "tushare", "attempt": attempt, "capture": None, "groups": [],
                  "strategy_input_ready": False, "release_allowed": False, "automatic_collection": False}
        latest = self._read("latest.json")
        if not latest:
            return result
        report, bars = _read_probe(self.directory / latest["id"])
        if report["provider"] != "tushare" or set(report["plan"]["datasets"]) - set(MODES.values()):
            raise ValueError("分钟记录的来源或数据集无效")
        capture = {key: report[key] for key in ("status", "started_at", "completed_at", "planned_requests", "sent_requests", "captured_responses", "bar_count", "reason_codes", "output_hash")}
        capture.update(id=latest["id"], dataset=report["plan"]["datasets"][0], simulated=report["simulated"],
                       requests=[{key: record.get(key) for key in ("operation", "symbol", "status", "reason_code", "api_code", "http_status", "row_count")} for record in report["requests"]])
        result["capture"] = capture
        for instrument in report["plan"]["symbols"]:
            selected = sorted((bar for bar in bars if bar["symbol"] == instrument["symbol"]), key=lambda bar: bar["label"])
            reasons = Counter(reason for bar in selected for reason in bar["reason_codes"])
            visible = [{key: bar[key] for key in ("label", "prices", "volume_shares", "amount_cny", "event_time", "source_time", "available_at", "is_complete", "unit_basis", "reason_codes")} for bar in selected[-240:]]
            last_label = selected[-1]["source_time"] if selected else None
            result["groups"].append({"symbol": instrument["symbol"], "total_rows": len(selected), "bars": visible,
                "last_label": last_label, "label_age_seconds": max(0, (self.clock() - utc(last_label)).total_seconds()) if last_label else None,
                "reason_counts": dict(reasons), "timestamp_semantics_verified": False})
        return result
