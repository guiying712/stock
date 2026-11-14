"""Durable operational facts and evidence gates; never a live release switch."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from time import monotonic
import uuid
from zoneinfo import ZoneInfo

from .contracts import fields, integer, numeric, string, utc
from .engine import _minute_number
from .replay import source_hash
from .store import StoreError, digest, dumps, now

SHANGHAI = ZoneInfo("Asia/Shanghai")
OPS_KEYS = ("schema_version", "id", "purpose", "strategy_version", "calendar_version", "target_universe_count", "universe_min_coverage", "sector_min_coverage", "p95_acceptance_seconds", "min_shadow_trading_days", "min_daily_slice_fraction", "max_data_age_seconds", "heartbeat_timeout_seconds", "restart_limit", "restart_backoff_seconds", "max_restart_backoff_seconds", "max_database_bytes", "retention_days")


def validate_operations_plan(plan):
    fields(plan, OPS_KEYS, "运行验收计划")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or plan["purpose"] not in ("fixture", "experimental"):
        raise ValueError("运行验收计划版本或用途无效")
    for key in ("id", "strategy_version", "calendar_version"):
        string(plan[key], key)
    integer(plan["target_universe_count"], 1, 100000, "目标股票池数量")
    integer(plan["min_shadow_trading_days"], 20, 1000, "影子观察交易日")
    integer(plan["heartbeat_timeout_seconds"], 10, 86400, "心跳超时")
    integer(plan["max_data_age_seconds"], 1, 86400, "数据新鲜度")
    integer(plan["restart_limit"], 0, 100, "最大重启次数")
    integer(plan["restart_backoff_seconds"], 1, 3600, "重启退避")
    integer(plan["max_restart_backoff_seconds"], plan["restart_backoff_seconds"], 86400, "最大重启退避")
    integer(plan["max_database_bytes"], 1, 2**63 - 1, "存储预算")
    integer(plan["retention_days"], 1, 36500, "原始输入归档周期")
    for key in ("universe_min_coverage", "sector_min_coverage", "min_daily_slice_fraction"):
        numeric(plan[key], key, low=0.000001, high=1)
    numeric(plan["p95_acceptance_seconds"], "平台受理P95目标", low=0.000001)
    return plan


def initialize(store):
    with store.connect() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ops_meta'").fetchone():
            row = db.execute("SELECT schema_version FROM ops_meta WHERE id=1").fetchone()
            if row is None or row[0] != 1:
                raise StoreError("SCHEMA_UNSUPPORTED", "运行证据数据库版本不支持")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS ops_meta (id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS ops_runs (id TEXT PRIMARY KEY, version TEXT NOT NULL, pid INTEGER NOT NULL,
          state TEXT NOT NULL, started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ops_observations (version TEXT NOT NULL, snapshot_id TEXT NOT NULL,
          observed_at TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(version,snapshot_id));
        CREATE TABLE IF NOT EXISTS ops_incidents (id TEXT PRIMARY KEY, version TEXT NOT NULL, code TEXT NOT NULL,
          episode INTEGER NOT NULL, state TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT,
          UNIQUE(version,code,episode));
        CREATE INDEX IF NOT EXISTS ops_observed ON ops_observations(version,observed_at);
        """)
        row = db.execute("SELECT schema_version FROM ops_meta WHERE id=1").fetchone()
        if row and row[0] != 1:
            raise StoreError("SCHEMA_UNSUPPORTED", "运行证据数据库版本不支持")
        db.execute("INSERT OR IGNORE INTO ops_meta VALUES(1,1)")


def _incident(db, version, code, timestamp, recover=False):
    row = db.execute("SELECT * FROM ops_incidents WHERE version=? AND code=? AND state='open' ORDER BY episode DESC LIMIT 1", (version, code)).fetchone()
    if recover:
        if row is None:
            return
        incident_id, episode = row["id"], row["episode"]
        db.execute("UPDATE ops_incidents SET state='recovered',closed_at=? WHERE id=?", (timestamp, incident_id))
        phase = "recovered"
    else:
        if row:
            return
        episode = db.execute("SELECT COALESCE(MAX(episode),0)+1 FROM ops_incidents WHERE version=? AND code=?", (version, code)).fetchone()[0]
        incident_id = digest([version, code, episode])
        db.execute("INSERT INTO ops_incidents VALUES(?,?,?,?,'open',?,NULL)", (incident_id, version, code, episode, timestamp))
        phase = "opened"
    payload = {"kind": "runtime_incident", "incident_id": incident_id, "strategy_version": version,
               "title": "运行异常" if phase == "opened" else "运行恢复", "code": code, "phase": phase,
               "text": code + " · " + ("已暂停相关更新，请检查诊断" if phase == "opened" else "新的成功扫描已恢复"),
               "at": timestamp}
    notification_id = digest(["ops", incident_id, phase])
    db.execute("INSERT OR IGNORE INTO outbox(id,channel,status,created_at,updated_at,payload) VALUES(?,'inbox','accepted',?,?,?)",
               (notification_id, timestamp, timestamp, dumps(payload)))
    db.execute("INSERT INTO logs(at,level,code,message) VALUES(?,?,?,?)",
               (timestamp, "error" if phase == "opened" else "info", code, payload["text"]))


def record_incident(store, version, code):
    initialize(store)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _incident(db, version, code, now())


class WorkerRuntime:
    """One worker per local database, with restart evidence and safe notices."""
    def __init__(self, store, config, provider_kind, capabilities=None, clock=now, timer=monotonic):
        self.store, self.config, self.kind = store, config, provider_kind
        self.clock, self.timer, self.capabilities = clock, timer, capabilities or {}
        self.run_id, self.lock, self.state = uuid.uuid4().hex, None, "running"
        self.code_hash = source_hash()

    def __enter__(self):
        try:
            import fcntl
        except ImportError:
            raise StoreError("PLATFORM_UNSUPPORTED", "工作进程互斥锁当前仅支持macOS/Linux") from None
        path = Path(self.store.path + ".worker.lock")
        self.lock = path.open("a+")
        os.chmod(path, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            raise StoreError("WORKER_BUSY", "该数据库已有行情工作进程") from None
        try:
            initialize(self.store)
            timestamp = self.clock()
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                stale = db.execute("SELECT id,version FROM ops_runs WHERE state IN ('running','paused')").fetchall()
                for row in stale:
                    db.execute("UPDATE ops_runs SET state='interrupted' WHERE id=?", (row["id"],))
                    _incident(db, row["version"], "WORKER_INTERRUPTED", timestamp)
                data = {"provider_kind": self.kind, "mode": self.config["mode"], "config_hash": digest(self.config), "code_hash": self.code_hash}
                db.execute("INSERT INTO ops_runs VALUES(?,?,?,'running',?,?,?)",
                           (self.run_id, self.config["id"], os.getpid(), timestamp, timestamp, dumps(data)))
            return self
        except BaseException:
            self.lock.close()
            self.lock = None
            raise

    def heartbeat(self, state=None):
        if state:
            self.state = state
        with self.store.connect() as db:
            db.execute("UPDATE ops_runs SET state=?,heartbeat_at=? WHERE id=?", (self.state, self.clock(), self.run_id))

    def fault(self, code):
        self.state = "paused"
        self.store.pause(self.config["id"], code)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _incident(db, self.config["id"], code, self.clock())
        self.heartbeat()

    def scan(self, app, batch, *, simulation_delivery=None):
        start = self.timer()
        result = app.scan(batch) if simulation_delivery is None else app.scan(batch, simulation_delivery=simulation_delivery)
        duration = self.timer() - start
        timestamp = self.clock()
        if result.get("duplicate"):
            self.heartbeat("paused" if self.store.pause_code(self.config["id"]) else "running")
            return result
        quality = result["quality"]
        cutoff = utc(batch["as_of"])
        observed = utc(timestamp)
        index = _minute_number(cutoff.replace(second=0, microsecond=0), batch["calendar"])
        expected_minutes = 0
        for a, b in batch["calendar"]["sessions"]:
            begin, end = [datetime.strptime(v, "%H:%M") for v in (a, b)]
            expected_minutes += int((end - begin).total_seconds() / 60)
        sectors = [s["coverage"] for s in result["sectors"] if s["member_count"]]
        fact = {"run_id": self.run_id, "config_hash": digest(self.config), "code_hash": self.code_hash,
                "as_of": batch["as_of"], "observed_at": timestamp, "mode": self.config["mode"], "simulated": batch["simulated"],
                "slice_end": (cutoff - timedelta(seconds=quality.get("latency_seconds", 0))).isoformat(),
                "calendar_version": batch["calendar"]["version"], "trading_date": cutoff.astimezone(SHANGHAI).date().isoformat(),
                "calendar_trading_dates": batch["calendar"]["trading_dates"], "session_end": batch["calendar"]["sessions"][-1][1],
                "trading_minute": index, "expected_minutes": expected_minutes,
                "expected_count": quality.get("expected_count"), "valid_count": quality.get("valid_count"),
                "coverage": quality.get("coverage"), "minimum_sector_coverage": min(sectors) if sectors and None not in sectors else None,
                "quality": quality["status"], "scan_commit_seconds": duration,
                "data_age_seconds": (observed - cutoff).total_seconds() + quality.get("latency_seconds", 0),
                "full_market_verified": self.capabilities.get("full_market_verified") is True,
                "input_hash": digest(batch)}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO ops_observations VALUES(?,?,?,?)", (self.config["id"], batch["snapshot_id"], timestamp, dumps(fact)))
            if quality["status"] == "good":
                codes = [r[0] for r in db.execute("SELECT code FROM ops_incidents WHERE version=? AND state='open'", (self.config["id"],))]
                for code in codes:
                    _incident(db, self.config["id"], code, timestamp, recover=True)
            else:
                _incident(db, self.config["id"], "SCAN_QUALITY_PAUSED", timestamp)
        self.heartbeat("running" if quality["status"] == "good" else "paused")
        return result

    def wait(self, seconds, sleep):
        # A long provider Retry-After still gets heartbeats and is not mistaken
        # for a hung process by the supervisor. It never clears a pause flag.
        while seconds > 0:
            chunk = min(seconds, 10)
            sleep(chunk)
            seconds -= chunk
            self.heartbeat()

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type and error_type is not KeyboardInterrupt:
                if self.state != "paused":
                    self.fault("WORKER_EXCEPTION")
                self.heartbeat("crashed")
            else:
                self.heartbeat("stopped")
        finally:
            if self.lock:
                self.lock.close()
                self.lock = None


def percentile95(values):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, (95 * len(values) + 99) // 100 - 1)]


def operations_report(store, plan, as_of=None):
    plan = validate_operations_plan(plan)
    cutoff = utc(as_of or now())
    config = store.version(plan["strategy_version"])
    with store.connect() as db:
        has_ops = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ops_meta'").fetchone()
        if has_ops:
            schema = db.execute("SELECT schema_version FROM ops_meta WHERE id=1").fetchone()
            if schema is None or schema[0] != 1:
                raise StoreError("SCHEMA_UNSUPPORTED", "运行证据数据库版本不支持")
        rows = db.execute("SELECT * FROM ops_observations WHERE version=? ORDER BY observed_at,snapshot_id", (plan["strategy_version"],)).fetchall() if has_ops else []
        runs = db.execute("SELECT * FROM ops_runs WHERE version=? ORDER BY started_at DESC,rowid DESC", (plan["strategy_version"],)).fetchall() if has_ops else []
        incidents = [dict(r) for r in db.execute("SELECT * FROM ops_incidents WHERE version=? ORDER BY opened_at,id", (plan["strategy_version"],))] if has_ops else []
        deliveries = db.execute("SELECT payload,response FROM outbox WHERE channel='dingtalk' AND status='accepted'").fetchall()
        tables = {name: db.execute("SELECT count(*) FROM " + name).fetchone()[0] for name in ("scans", "signals", "events", "outbox", "attempts")}
        tables["ops_observations"] = len(rows)
        archive_before = cutoff - timedelta(days=plan["retention_days"])
        archivable = sum(utc(r[0]) < archive_before for r in db.execute("SELECT as_of FROM scans WHERE version=?", (plan["strategy_version"],)))
    facts = [json.loads(row["data"]) for row in rows]
    facts_by_snapshot = {r["snapshot_id"]: json.loads(r["data"]) for r in rows}
    config_hash, code_hash = digest(config), source_hash()
    matching = [f for f in facts if f["config_hash"] == config_hash and f["code_hash"] == code_hash and f["mode"] == config["mode"] and utc(f["observed_at"]) <= cutoff]
    real = [f for f in matching if plan["purpose"] == "experimental" and config["mode"] == "shadow" and f["mode"] == "shadow" and f["simulated"] is False]
    eligible = [f for f in real
                if f["full_market_verified"] is True and f["calendar_version"] == plan["calendar_version"]
                and f["quality"] == "good" and f["expected_count"] == plan["target_universe_count"]
                and f["coverage"] is not None and f["coverage"] >= float(plan["universe_min_coverage"])
                and f["minimum_sector_coverage"] is not None and f["minimum_sector_coverage"] >= float(plan["sector_min_coverage"])
                and 0 <= f["data_age_seconds"] <= plan["max_data_age_seconds"] and f["trading_minute"] is not None
                and utc(f["observed_at"]).astimezone(SHANGHAI).date().isoformat() == f["trading_date"]]
    by_day = defaultdict(list)
    for fact in eligible:
        by_day[fact["trading_date"]].append(fact)
    days = []
    first_date = min((x["trading_date"] for x in matching), default="9999-12-31")
    declared_dates = sorted({d for f in matching if f["calendar_version"] == plan["calendar_version"] for d in f["calendar_trading_dates"]
                             if first_date <= d <= cutoff.astimezone(SHANGHAI).date().isoformat()})
    consecutive = 0
    for current in declared_dates:
        values = by_day.get(current, [])
        if current == cutoff.astimezone(SHANGHAI).date().isoformat():
            ends = [f["session_end"] for f in matching if f["calendar_version"] == plan["calendar_version"]]
            if not ends or cutoff.astimezone(SHANGHAI).strftime("%H:%M") < max(ends):
                continue
        expected = max((v["expected_minutes"] for v in values), default=0)
        fraction = len({v["trading_minute"] for v in values}) / expected if expected else None
        qualified = fraction is not None and fraction >= float(plan["min_daily_slice_fraction"])
        consecutive = consecutive + 1 if qualified else 0
        days.append({"date": current, "slice_fraction": fraction, "qualified": qualified})
    qualified_days = sum(d["qualified"] for d in days)
    acceptance = {}
    for row in deliveries:
        payload, response = json.loads(row["payload"]), json.loads(row["response"] or "{}")
        signal = payload.get("signal", {})
        fact = facts_by_snapshot.get(payload.get("event", {}).get("snapshot_id"))
        if (plan["purpose"] != "experimental" or config["mode"] not in {"shadow", "live_alert"} or fact is None or fact["simulated"] is not False
                or fact["mode"] != config["mode"]
                or fact["code_hash"] != code_hash or fact["config_hash"] != config_hash
                or signal.get("strategy_version") != plan["strategy_version"] or signal.get("evidence", {}).get("simulated") is not False):
            continue
        try:
            # Older cutoff-only delivery records cannot prove wall-clock
            # acceptance latency. Require the new actual completion timestamp.
            if response.get("request_completed_at") is None:
                continue
            end = utc(response["request_completed_at"])
            elapsed = (end - utc(fact["slice_end"])).total_seconds()
            if elapsed >= 0 and end <= cutoff:
                key = response.get("delivery_id") or digest(payload)
                acceptance[key] = max(acceptance.get(key, 0), elapsed)
        except (KeyError, TypeError, ValueError):
            continue
    latency = percentile95(list(acceptance.values()))
    latest = dict(runs[0]) if runs else None
    if latest:
        latest.pop("data")
        latest["heartbeat_age_seconds"] = (cutoff - utc(latest["heartbeat_at"])).total_seconds()
        latest["healthy"] = latest["state"] == "running" and 0 <= latest["heartbeat_age_seconds"] <= plan["heartbeat_timeout_seconds"]
    real_samples = len(eligible)
    database_bytes = sum(Path(store.path + suffix).stat().st_size for suffix in ("", "-wal", "-shm") if Path(store.path + suffix).exists())
    gates = [{"id": "full_market_coverage", "status": "pending" if not real or not any(f["full_market_verified"] for f in real) else "pass" if len(real) == real_samples else "fail", "eligible_slices": real_samples},
             {"id": "shadow_trading_days", "status": "pass" if consecutive >= plan["min_shadow_trading_days"] else "pending",
              "observed": consecutive, "total_qualified_days": qualified_days, "target": plan["min_shadow_trading_days"]},
             {"id": "platform_acceptance_p95", "status": "pending" if latency is None else "pass" if latency <= float(plan["p95_acceptance_seconds"]) else "fail",
              "observed_seconds": latency, "target_seconds": plan["p95_acceptance_seconds"], "request_count": len(acceptance)},
             {"id": "storage_budget", "status": "pass" if database_bytes <= plan["max_database_bytes"] else "fail",
              "observed_bytes": database_bytes, "target_bytes": plan["max_database_bytes"], "scope": "local_storage_only"}]
    report = {"schema_version": 1, "kind": "operational_evidence_report", "as_of": cutoff.isoformat(), "plan": plan,
              "plan_hash": digest(plan), "config_hash": config_hash, "code_hash": code_hash,
              "release_allowed": False, "gates": gates, "current_worker": latest, "incidents": incidents,
              "observed_slices": len(matching), "excluded_or_older_code_slices": len(facts) - len(matching),
              "scan_commit_p95_seconds": percentile95([f["scan_commit_seconds"] for f in matching]),
              "minimum_observed_coverage": min((f["coverage"] for f in matching if f["coverage"] is not None), default=None),
              "shadow_days": days, "table_rows": tables,
              "database_bytes": database_bytes, "retention": {"days": plan["retention_days"], "archive_before": archive_before.isoformat(),
              "archivable_input_rows": archivable, "automatic_deletion": False},
              "limitations": ["模拟、旧代码、重传及非当时采集数据不计为真实影子证据",
                              "完整股票池声明尚需服务商PoC；少量切片不能代替完整交易日",
                              "内部扫描耗时不是平台受理时延；缺投递样本时P95为null",
                              "运行事件只存内置中心；真实外部故障提醒仍待显式渠道接线",
                              "任何报告都不会解除应用入口live_alert锁定"]}
    report["output_hash"] = digest(report)
    return report
