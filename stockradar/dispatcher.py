"""Exclusive, observable local-simulation dispatch lifecycle; no live transport."""
from collections import Counter
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
import os
import sqlite3
from pathlib import Path
from threading import Event, Lock, Thread, current_thread
from time import monotonic
import uuid

from .config import validate_config
from .contracts import fields, integer, numeric, string, utc
from .notifier import SimulationNotifier
from .outbox import MAX_ATTEMPTS, SIMULATION_CHANNEL, dispatch_pending, recover_inflight
from .replay import source_hash
from .store import StoreError, digest, dumps, now

PLAN_KEYS = ("schema_version", "id", "strategy_version", "transport", "clock_mode", "simulation_start",
             "poll_interval_seconds", "heartbeat_timeout_seconds", "max_messages_per_tick",
             "shutdown_timeout_seconds", "drain_timeout_seconds")


def validate_dispatch_plan(plan):
    fields(plan, PLAN_KEYS, "本地投递演练计划")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("本地投递演练计划版本无效")
    for key in ("id", "strategy_version"):
        string(plan[key], key)
    if plan["transport"] != "local_simulation" or plan["clock_mode"] not in ("wall", "simulated"):
        raise ValueError("仅支持明确的local_simulation及wall/simulated时钟")
    if plan["clock_mode"] == "simulated":
        utc(plan["simulation_start"])
    elif plan["simulation_start"] is not None:
        raise ValueError("wall时钟的simulation_start须显式为null")
    poll = numeric(plan["poll_interval_seconds"], "轮询间隔", low=Decimal("0.05"), high=10)
    timeout = numeric(plan["heartbeat_timeout_seconds"], "心跳超时", low=1, high=3600)
    if timeout < poll * 3:
        raise ValueError("心跳超时须至少为轮询间隔三倍")
    numeric(plan["shutdown_timeout_seconds"], "停止等待", low=Decimal("0.05"), high=30)
    numeric(plan["drain_timeout_seconds"], "结束前排空等待", low=0, high=60)
    integer(plan["max_messages_per_tick"], 1, 20, "单轮请求上限")
    return deepcopy(plan)


def _check_schema(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dispatcher_meta'").fetchone():
        return False
    row = db.execute("SELECT schema_version FROM dispatcher_meta WHERE id=1").fetchone()
    if row is None or row[0] != 1:
        raise StoreError("SCHEMA_UNSUPPORTED", "投递生命周期数据库版本不支持")
    return True


def _initialize(store, plan):
    with store.connect() as db:
        _check_schema(db)
        db.executescript("""
        CREATE TABLE IF NOT EXISTS dispatcher_meta(id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS dispatcher_plans(id TEXT PRIMARY KEY, hash TEXT NOT NULL, plan TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dispatcher_runs(id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, version TEXT NOT NULL,
          channel TEXT NOT NULL, pid INTEGER NOT NULL, state TEXT NOT NULL, started_at TEXT NOT NULL,
          heartbeat_at TEXT NOT NULL, clock_at TEXT NOT NULL, clock_mode TEXT NOT NULL, data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS dispatcher_run_version ON dispatcher_runs(version,started_at);
        CREATE TABLE IF NOT EXISTS dispatcher_watermarks(version TEXT PRIMARY KEY, clock_mode TEXT NOT NULL,
          logical_at TEXT NOT NULL, wall_at TEXT NOT NULL);
        """)
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO dispatcher_meta VALUES(1,1)")
        existing = db.execute("SELECT hash FROM dispatcher_plans WHERE id=?", (plan["id"],)).fetchone()
        if existing and existing[0] != digest(plan):
            raise StoreError("PLAN_IMMUTABLE", "同一投递计划ID不能更改内容，请使用新ID")
        db.execute("INSERT OR IGNORE INTO dispatcher_plans VALUES(?,?,?)", (plan["id"], digest(plan), dumps(plan)))


def _pending_rows(db, version):
    rows = []
    for row in db.execute("SELECT * FROM outbox WHERE channel=? AND status IN ('pending','sending','failed')", (SIMULATION_CHANNEL,)):
        payload = json.loads(row["payload"])
        if payload.get("signal", {}).get("strategy_version") != version:
            continue
        response = json.loads(row["response"] or "{}")
        if row["status"] == "failed" and (not response.get("retryable") or row["attempts"] >= MAX_ATTEMPTS):
            continue
        rows.append((row, payload))
    return rows


class SimulationClock:
    def __init__(self, start, timer=monotonic):
        self._base, self._timer, self._start = utc(start), timer, timer()
        self._lock = Lock()

    def __call__(self):
        with self._lock:
            return (self._base + timedelta(seconds=max(0, self._timer() - self._start))).isoformat()

    def advance_to(self, value):
        target = utc(value)
        with self._lock:
            instant = self._timer()
            current = self._base + timedelta(seconds=max(0, instant - self._start))
            self._base, self._start = max(target, current), instant


class SimulationDispatcher:
    """A channel-wide lock precedes recovery; only the selected version is sent.

    close() lets the claimed request finish, then prevents further claims.
    If a custom test notifier hangs, ownership is retained until that thread
    exits or the process dies; a timeout never grants a second owner access.
    """
    def __init__(self, store, plan, *, notifier=None, clock=None, wall_clock=now, autostart=True):
        self.store, self.plan = store, validate_dispatch_plan(plan)
        self.config = validate_config(store.version(self.plan["strategy_version"]))
        if self.config["mode"] not in ("fixture", "replay", "shadow") or self.config["status"] != "frozen":
            raise StoreError("RELEASE_GATED", "投递演练仅支持冻结的离线/影子版本，不能启用真实提醒")
        self.notifier = notifier if notifier is not None else SimulationNotifier()
        if not isinstance(self.notifier, SimulationNotifier):
            raise StoreError("SIMULATION_TRANSPORT_REQUIRED", "演练进程仅允许本地SimulationNotifier")
        self.clock, self.wall_clock, self.autostart = clock, wall_clock, autostart
        if clock is not None and (not callable(clock) or (self.plan["clock_mode"] == "simulated" and not callable(getattr(clock, "advance_to", None)))):
            raise ValueError("模拟时钟须可调用并支持advance_to")
        self.run_id, self.state, self.error = uuid.uuid4().hex, "starting", None
        self._lock_file, self._thread = None, None
        self._stop, self._wake, self._tick_lock = Event(), Event(), Lock()
        self.counts = {"ticks": 0, "requests": 0, "notifications": 0, "recovered": 0, "outcomes": {}}
        self._code_hash = source_hash()
        self._run_saved = False

    def __enter__(self):
        if self._lock_file is not None or self.state != "starting":
            raise StoreError("DISPATCHER_STATE", "投递器实例不能重复启动")
        try:
            import fcntl
        except ImportError:
            raise StoreError("PLATFORM_UNSUPPORTED", "投递互斥锁当前仅支持macOS/Linux") from None
        path = Path(self.store.path + ".dispatcher-simulation.lock")
        self._lock_file = path.open("a+")
        os.chmod(path, 0o600)
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._release()
            raise StoreError("DISPATCHER_BUSY", "该数据库已有本地演练投递进程；未执行恢复") from None
        except BaseException:
            self._release()
            raise
        try:
            _initialize(self.store, self.plan)
            timestamp = utc(self.wall_clock())
            with self.store.connect() as db:
                pending = _pending_rows(db, self.config["id"])
                if any(p.get("simulation_context", {}).get("clock_mode") != self.plan["clock_mode"] for _, p in pending):
                    raise StoreError("CLOCK_DOMAIN_CONFLICT", "未完成的同策略模拟队列不能混用时钟域")
                previous = db.execute("SELECT * FROM dispatcher_runs WHERE version=? AND clock_mode=? ORDER BY rowid DESC LIMIT 1",
                                      (self.config["id"], self.plan["clock_mode"])).fetchone()
                anchors = []
                if self.plan["clock_mode"] == "simulated":
                    watermark = db.execute("SELECT logical_at,wall_at FROM dispatcher_watermarks WHERE version=? AND clock_mode='simulated'", (self.config["id"],)).fetchone()
                    if watermark:
                        anchors.append((utc(watermark["logical_at"]), utc(watermark["wall_at"])))
                    # Scan/claim may commit immediately before a crash, before
                    # the dispatcher heartbeat can record its new clock. Use
                    # persisted logical/wall pairs instead of rewinding time.
                    for item in db.execute("SELECT id,created_at,payload FROM outbox WHERE channel=?", (SIMULATION_CHANNEL,)):
                        payload = json.loads(item["payload"])
                        if (payload.get("signal", {}).get("strategy_version") != self.config["id"] or
                                payload.get("simulation_context", {}).get("clock_mode") != "simulated"):
                            continue
                        anchors.append((utc(item["created_at"]), utc(payload["wall_enqueued_at"])))
                        for attempt in db.execute("SELECT at,data FROM attempts WHERE notification_id=?", (item["id"],)):
                            data = json.loads(attempt["data"])
                            if data.get("phase") == "started" and data.get("request_started_at"):
                                anchors.append((utc(attempt["at"]), utc(data["request_started_at"])))
            if self.plan["clock_mode"] == "simulated":
                start = utc(self.plan["simulation_start"])
                if previous:
                    gap = max(timedelta(0), timestamp - utc(previous["heartbeat_at"]))
                    start = max(start, utc(previous["clock_at"]) + gap)
                for logical, wall in anchors:
                    start = max(start, logical + max(timedelta(0), timestamp - wall))
                if self.clock is None:
                    self.clock = SimulationClock(start.isoformat())
                elif hasattr(self.clock, "advance_to"):
                    self.clock.advance_to(start.isoformat())
                elif utc(self.clock()) < start:
                    raise StoreError("CLOCK_REWIND", "模拟时钟不能倒退到已保存水位之前")
            elif self.clock is None:
                self.clock = self.wall_clock
            clock_at = utc(self.clock()).isoformat()
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE dispatcher_runs SET state='interrupted' WHERE channel=? AND state IN ('running','stopping')", (SIMULATION_CHANNEL,))
                self.state = "running"
                db.execute("INSERT INTO dispatcher_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (self.run_id, self.plan["id"], self.config["id"], SIMULATION_CHANNEL, os.getpid(), self.state,
                            timestamp.isoformat(), timestamp.isoformat(), clock_at, self.plan["clock_mode"], dumps(self._data())))
            self._run_saved = True
            self.counts["recovered"] = recover_inflight(self.store, channel=SIMULATION_CHANNEL, strategy_version=self.config["id"],
                                                        as_of=self.clock() if self.plan["clock_mode"] == "simulated" else None)
            self._record()
            if self.autostart:
                self.start()
            return self
        except BaseException:
            if self._run_saved:
                self.state = "failed"
                self.error = StoreError("DISPATCHER_START_FAILED", "本地演练投递启动失败，未完成记录保留")
                try:
                    self._record(nonblocking=True)
                except Exception:
                    pass
            self._release()
            raise

    def _data(self):
        return {"simulation": True, "transport": "local", "release_allowed": False, "plan_hash": digest(self.plan),
                "config_hash": digest(self.config), "code_hash": self._code_hash, "counts": self.counts,
                "error_code": self.error.code if self.error else None}

    def _record(self, nonblocking=False):
        with self.store.connect() as db:
            if nonblocking:
                db.execute("PRAGMA busy_timeout=0")
            db.execute("UPDATE dispatcher_runs SET state=?,heartbeat_at=?,clock_at=?,data=? WHERE id=?",
                       (self.state, utc(self.wall_clock()).isoformat(), utc(self.clock()).isoformat(), dumps(self._data()), self.run_id))

    def _release(self):
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    def start(self):
        if self._lock_file is None or self.state != "running" or self._thread is not None:
            raise StoreError("DISPATCHER_STATE", "只有已取得所有权的投递器可以启动一次")
        self._thread = Thread(target=self._loop, name="stockradar-simulation-dispatch", daemon=True)
        self._thread.start()

    def check(self):
        if self.error is not None:
            raise self.error

    def delivery_for(self, as_of):
        self.check()
        if self._lock_file is None or self.state != "running":
            raise StoreError("DISPATCHER_STATE", "只有已启动的投递器能提供扫描上下文")
        instant = utc(self.clock())
        if self.plan["clock_mode"] == "simulated":
            instant = max(instant, utc(as_of))
        return {"plan_id": self.plan["id"], "clock_mode": self.plan["clock_mode"], "enqueued_at": instant.isoformat()}

    def after_scan(self, as_of, duplicate=False):
        if not duplicate and self.plan["clock_mode"] == "simulated":
            self.clock.advance_to(as_of)
        self._wake.set()
        self.check()

    def wake(self):
        self._wake.set()

    def _sync_clock(self):
        if self.plan["clock_mode"] != "simulated":
            return
        with self.store.connect() as db:
            row = db.execute("SELECT logical_at,wall_at FROM dispatcher_watermarks WHERE version=? AND clock_mode='simulated'", (self.config["id"],)).fetchone()
        if row:
            logical = utc(row["logical_at"]) + max(timedelta(0), utc(self.wall_clock()) - utc(row["wall_at"]))
            self.clock.advance_to(logical.isoformat())

    def tick(self):
        if self._lock_file is None:
            raise StoreError("DISPATCHER_STATE", "投递前必须先取得独占所有权")
        with self._tick_lock:
            results = []
            if self._stop.is_set():
                return results
            with self.store.connect() as db:
                if any(p.get("simulation_context", {}).get("clock_mode") != self.plan["clock_mode"] for _, p in _pending_rows(db, self.config["id"])):
                    raise StoreError("CLOCK_DOMAIN_CONFLICT", "未完成模拟队列的时钟域不一致")
            for _ in range(self.plan["max_messages_per_tick"]):
                if self._stop.is_set():
                    break
                self._sync_clock()
                # Refresh checks for every request; a previous slow call must
                # not give later opportunities its obsolete freshness cutoff.
                current = utc(self.clock()).isoformat()
                batch = dispatch_pending(self.store, self.notifier, current, max_messages=1,
                                         channel=SIMULATION_CHANNEL, strategy_version=self.config["id"],
                                         should_stop=self._stop.is_set)
                results.extend(batch)
                deliveries = {r["delivery_id"] for r in batch if r.get("delivery_id")}
                self.counts["requests"] += len(deliveries)
                if not deliveries:
                    break
            outcomes = Counter(self.counts["outcomes"])
            outcomes.update(r["status"] for r in results)
            self.counts.update(ticks=self.counts["ticks"] + 1, notifications=self.counts["notifications"] + len(results), outcomes=dict(outcomes))
            self._record()
            return results

    def next_delay(self):
        delay = float(self.plan["poll_interval_seconds"])
        cutoff = utc(self.clock())
        with self.store.connect() as db:
            for row, payload in _pending_rows(db, self.config["id"]):
                if row["status"] == "sending":
                    continue
                due = max(utc(row["created_at"]), utc(payload["event"]["at"]))
                if payload.get("aggregation"):
                    due = max(due, utc(payload["aggregation"]["ready_at"]))
                if row["next_attempt_at"]:
                    due = max(due, utc(row["next_attempt_at"]))
                seconds = (due - cutoff).total_seconds()
                if seconds > 0:
                    delay = min(delay, seconds)
        return delay

    def _loop(self):
        try:
            while not self._stop.is_set():
                self._wake.clear()
                self.tick()
                self._wake.wait(self.next_delay())
        except Exception:
            self.error = StoreError("DISPATCHER_FAILED", "本地模拟投递进程失败，请检查计划、队列及诊断；未调用真实渠道")
            self._stop.set()
        finally:
            self.state = "failed" if self.error else "stopped"
            try:
                self._record()
                if self.error:
                    self.store.log(self.error.code, str(self.error), "error")
            finally:
                self._release()

    def pending_count(self):
        with self.store.connect() as db:
            return len(_pending_rows(db, self.config["id"]))

    def drain(self):
        deadline = monotonic() + float(self.plan["drain_timeout_seconds"])
        while self.pending_count() and monotonic() < deadline:
            self.check()
            if self._thread is None:
                self.tick()
            self._wake.set()
            self._stop.wait(min(.05, max(0, deadline - monotonic())))
        self.check()
        return self.pending_count()

    def close(self):
        if self._lock_file is None:
            self.check()
            return
        self.state = "stopping"
        self._stop.set()
        self._wake.set()
        try:
            self._record(nonblocking=True)
        except sqlite3.OperationalError:
            pass
        if self._thread is current_thread():
            return
        if self._thread is not None and self._thread is not current_thread():
            self._thread.join(float(self.plan["shutdown_timeout_seconds"]))
            if self._thread.is_alive():
                self.error = StoreError("DISPATCHER_STOP_TIMEOUT", "模拟请求尚未返回，保留所有权；进程退出后未完成请求按unknown恢复")
                raise self.error
            self.check()
            return
        try:
            self.state = "failed" if self.error else "stopped"
            self._record()
        finally:
            self._release()

    def __exit__(self, error_type, error, traceback):
        if error_type and error_type is not KeyboardInterrupt and self.error is None:
            self.error = StoreError("DISPATCHER_ABORTED", "采集或调用流程中断，本地演练停止，未完成队列保留")
        try:
            self.close()
        except StoreError:
            if error_type is None:
                raise

    def wait(self):
        while not self._stop.wait(.25):
            self.check()
        self.check()


def dispatcher_status(store, version, as_of=None):
    cutoff = utc(as_of or now())
    with store.connect() as db:
        if not _check_schema(db):
            return None
        row = db.execute("SELECT * FROM dispatcher_runs WHERE version=? ORDER BY rowid DESC LIMIT 1", (version,)).fetchone()
        if not row:
            return None
        plan = json.loads(db.execute("SELECT plan FROM dispatcher_plans WHERE id=?", (row["plan_id"],)).fetchone()[0])
    value = dict(row)
    data = json.loads(value.pop("data"))
    age = (cutoff - utc(value["heartbeat_at"])).total_seconds()
    value.update(data, heartbeat_age_seconds=age,
                 healthy=value["state"] == "running" and 0 <= age <= float(plan["heartbeat_timeout_seconds"])
                 and data["code_hash"] == source_hash())
    return value


def dispatch_report(store, plan):
    plan = validate_dispatch_plan(plan)
    config = store.version(plan["strategy_version"])
    counts, attempts = Counter(), set()
    with store.connect() as db:
        _check_schema(db)
        for row in db.execute("SELECT * FROM outbox WHERE channel=?", (SIMULATION_CHANNEL,)):
            if json.loads(row["payload"]).get("signal", {}).get("strategy_version") != config["id"]:
                continue
            counts[row["status"]] += 1
            for attempt in db.execute("SELECT id,data FROM attempts WHERE notification_id=?", (row["id"],)):
                data = json.loads(attempt["data"])
                if data.get("phase") == "started":
                    attempts.add(data.get("delivery_id") or str(attempt["id"]))
    report = {"schema_version": 1, "kind": "local_simulation_dispatch_report", "as_of": now(),
              "simulation": True, "transport": "local", "release_allowed": False, "plan": plan,
              "plan_hash": digest(plan), "config_hash": digest(config), "code_hash": source_hash(),
              "current": dispatcher_status(store, config["id"]), "queue_counts": dict(counts),
              "simulation_request_count": len(attempts), "platform_acceptance_p95_seconds": None,
              "limitations": ["本地模拟器只保存回执，不读取钉钉凭据或访问网络",
                              "模拟时钟下的窗口/限流不是实际平台时延或吞吐证据",
                              "unknown不自动重试；未完成队列保留原截止时间和重试水位",
                              "不补投历史事件，不修改原SignalEvent、数据模拟标记或live_alert锁定"]}
    report["output_hash"] = digest(report)
    return report
