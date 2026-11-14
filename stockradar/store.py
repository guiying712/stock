"""SQLite event log and transactional outbox. A scan is one atomic commit."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from . import __version__


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


class StoreError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Store:
    def __init__(self, path="data/radar.sqlite3"):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS versions (
              id TEXT PRIMARY KEY, hash TEXT NOT NULL, config TEXT NOT NULL,
              created_at TEXT NOT NULL, code_version TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS states (version TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_flags (version TEXT PRIMARY KEY, code TEXT NOT NULL, at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scans (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id TEXT NOT NULL,
              version TEXT NOT NULL, hash TEXT NOT NULL, as_of TEXT NOT NULL,
              recorded_at TEXT NOT NULL, input TEXT NOT NULL, result TEXT NOT NULL,
              UNIQUE(snapshot_id,version));
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY, signal_id TEXT NOT NULL, revision INTEGER NOT NULL,
              at TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(signal_id,revision));
            CREATE TABLE IF NOT EXISTS signals (
              id TEXT PRIMARY KEY, version TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tags (
              id TEXT PRIMARY KEY, signal_id TEXT, observed_at TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
              id TEXT PRIMARY KEY, signal_id TEXT, revision INTEGER, channel TEXT NOT NULL,
              status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, next_attempt_at TEXT,
              payload TEXT NOT NULL, response TEXT, UNIQUE(signal_id,revision,channel));
            CREATE TABLE IF NOT EXISTS attempts (
              id INTEGER PRIMARY KEY AUTOINCREMENT, notification_id TEXT NOT NULL,
              at TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feedback (
              id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL,
              action TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, request TEXT NOT NULL, result TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, level TEXT NOT NULL,
              code TEXT NOT NULL, message TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS scan_version ON scans(version,seq);
            CREATE INDEX IF NOT EXISTS event_signal ON events(signal_id,revision);
            """)
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def register_version(self, config):
        from .config import validate_config, config_hash
        from .replay import source_hash
        config = validate_config(config)
        version, sha = config["id"], config_hash(config)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT hash FROM versions WHERE id=?", (version,)).fetchone()
            if row and row["hash"] != sha:
                raise StoreError("VERSION_IMMUTABLE", "策略版本不可原地修改，请使用新的版本 ID")
            db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?,?)", (version, sha, dumps(config), now(), __version__ + ":" + source_hash()))
        return config

    def versions(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM versions ORDER BY created_at DESC,id DESC").fetchall()
        return [{"id": r["id"], "config_hash": r["hash"], "config": json.loads(r["config"]),
                 "created_at": r["created_at"], "code_version": r["code_version"],
                 "status": json.loads(r["config"])["status"]} for r in rows]

    def running_config(self):
        """Retain the last scanned version across a default-config upgrade."""
        with self.connect() as db:
            row = db.execute("SELECT v.config FROM scans s JOIN versions v ON v.id=s.version ORDER BY s.seq DESC LIMIT 1").fetchone()
            if row:
                return json.loads(row[0])
            saved = db.execute("SELECT config FROM versions ORDER BY created_at,id LIMIT 2").fetchall()
        if len(saved) > 1:
            raise StoreError("CONFIG_SELECTION_REQUIRED", "数据库已有多个版本但无运行记录，请用--config或--saved-version明确选择")
        return json.loads(saved[0][0]) if saved else None

    def version(self, version_id):
        with self.connect() as db:
            row = db.execute("SELECT config FROM versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            raise StoreError("NOT_FOUND", "策略版本不存在")
        return json.loads(row[0])

    def apply_batch(self, batch, config, *, simulation_delivery=None):
        from .engine import evaluate
        if simulation_delivery is not None:
            from .contracts import fields, string, utc
            fields(simulation_delivery, ("plan_id", "clock_mode", "enqueued_at"), "模拟投递上下文")
            string(simulation_delivery["plan_id"], "模拟投递计划ID")
            if simulation_delivery["clock_mode"] not in ("wall", "simulated"):
                raise StoreError("INVALID_TIME", "模拟投递时钟域无效")
            utc(simulation_delivery["enqueued_at"])
            if config["mode"] not in ("fixture", "replay", "shadow") or config["status"] != "frozen":
                raise StoreError("RELEASE_GATED", "本地演练只支持冻结的离线或影子版本")
        self.register_version(config)
        version = config["id"]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if simulation_delivery is not None:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dispatcher_plans'").fetchone():
                    raise StoreError("SIMULATION_PLAN_MISSING", "先初始化明确的本地投递演练计划")
                plan_row = db.execute("SELECT plan FROM dispatcher_plans WHERE id=?", (simulation_delivery["plan_id"],)).fetchone()
                plan = json.loads(plan_row[0]) if plan_row else {}
                if (plan.get("strategy_version") != version or plan.get("transport") != "local_simulation"
                        or plan.get("clock_mode") != simulation_delivery["clock_mode"]):
                    raise StoreError("SIMULATION_PLAN_MISMATCH", "模拟投递计划与策略或时钟域不匹配")
                if db.execute("SELECT 1 FROM dispatcher_runs WHERE version=? AND state IN ('running','stopping') AND clock_mode!=?",
                              (version, simulation_delivery["clock_mode"])).fetchone():
                    raise StoreError("CLOCK_DOMAIN_CONFLICT", "同一策略的在运行模拟投递不能混用时钟域")
            old = db.execute("SELECT hash,result FROM scans WHERE snapshot_id=? AND version=?", (batch["snapshot_id"], version)).fetchone()
            if old:
                if old["hash"] != digest(batch):
                    raise StoreError("DATA_CORRECTION", "同一快照内容发生修订；须保留原记录并以新 snapshot_id 导入修订，不静默重写")
                return {**json.loads(old["result"]), "duplicate": True}
            row = db.execute("SELECT data FROM states WHERE version=?", (version,)).fetchone()
            result = evaluate(batch, config, json.loads(row[0]) if row else None)
            result["mode"] = config["mode"]
            result["simulated"] = bool(batch.get("simulated"))
            result["as_of"] = batch["as_of"]
            from .replay import source_hash
            result["code_hash"] = source_hash()
            db.execute("INSERT OR REPLACE INTO states VALUES(?,?)", (version, dumps(result["state"])))
            db.execute("INSERT INTO scans(snapshot_id,version,hash,as_of,recorded_at,input,result) VALUES(?,?,?,?,?,?,?)",
                       (batch["snapshot_id"], version, digest(batch), batch["as_of"], now(), dumps(batch), dumps(result)))
            db.execute("DELETE FROM runtime_flags WHERE version=?", (version,))
            signals = {s["id"]: s for s in result["signals"]}
            for signal in signals.values():
                db.execute("INSERT OR REPLACE INTO signals VALUES(?,?,?)", (signal["id"], version, dumps(signal)))
            for event in result["events"]:
                db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (event["id"], event["signal_id"], event["revision"], event["at"], dumps(event)))
                signal = event["snapshot"]
                payload = {"signal": signal, "event": event, "simulated": bool(batch.get("simulated"))}
                # DETECTED is internal only; all alert/risk revisions have an inbox event.
                if event["to_status"] != "DETECTED" and (signal.get("alert_time") or event["from_status"] in {"PREALERT", "CONFIRMED"}):
                    notification_id = digest([signal["id"], event["revision"], "inbox"])
                    db.execute("INSERT INTO outbox(id,signal_id,revision,channel,status,created_at,updated_at,payload) VALUES(?,?,?,'inbox','accepted',?,?,?)",
                               (notification_id, signal["id"], event["revision"], now(), now(), dumps(payload)))
                    if simulation_delivery is not None:
                        from .outbox import SIMULATION_CHANNEL, enqueue
                        context = {k: simulation_delivery[k] for k in ("plan_id", "clock_mode")}
                        enqueue(db, signal, event, SIMULATION_CHANNEL,
                                created_at=simulation_delivery["enqueued_at"], simulation_context=context)
            for tag in result.get("tags", []):
                db.execute("INSERT OR IGNORE INTO tags VALUES(?,?,?,?)",
                           (digest(tag), tag.get("signal_id", tag.get("entity_id")), tag.get("observed_at"), dumps(tag)))
            if simulation_delivery is not None:
                db.execute("INSERT OR REPLACE INTO dispatcher_watermarks VALUES(?,?,?,?)",
                           (version, simulation_delivery["clock_mode"], simulation_delivery["enqueued_at"], now()))
        return result

    def latest(self, version=None):
        with self.connect() as db:
            row = db.execute("SELECT result FROM scans WHERE version=? ORDER BY seq DESC LIMIT 1", (version,)).fetchone() if version else db.execute("SELECT result FROM scans ORDER BY seq DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def signals(self, version=None):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM signals WHERE version=?", (version,)).fetchall() if version else db.execute("SELECT data FROM signals").fetchall()
        return sorted((json.loads(r[0]) for r in rows), key=lambda s: (-(s.get("score") or 0), s.get("trigger_time", ""), s["id"]))

    def detail(self, signal_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM signals WHERE id=?", (signal_id,)).fetchone()
            if not row:
                raise StoreError("NOT_FOUND", "信号不存在")
            signal = json.loads(row[0])
            signal["events"] = [json.loads(r[0]) for r in db.execute("SELECT data FROM events WHERE signal_id=? ORDER BY revision", (signal_id,))]
            signal["feedback"] = [dict(r) for r in db.execute("SELECT * FROM feedback WHERE signal_id=? ORDER BY id", (signal_id,))]
            tag_rows = db.execute("SELECT data FROM tags WHERE signal_id IN (?,?,?) ORDER BY observed_at", (signal_id, signal.get("instrument_id"), signal.get("primary_sector_id")))
            signal["tags"] = [tag for tag in (json.loads(r[0]) for r in tag_rows) if tag.get("rule_version") == signal.get("strategy_version")]
        signal["notifications"] = self.notifications(signal_id)
        return signal

    def feedback(self, signal_id, action, key):
        if action not in {"watch", "ignore", "bought"}:
            raise StoreError("INVALID_INPUT", "反馈必须为 watch、ignore 或 bought")
        if not isinstance(key, str) or not 8 <= len(key) <= 128:
            raise StoreError("INVALID_INPUT", "幂等键须为8至128字符")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM signals WHERE id=?", (signal_id,)).fetchone():
                raise StoreError("NOT_FOUND", "信号不存在")
            old = db.execute("SELECT * FROM feedback WHERE idempotency_key=?", (key,)).fetchone()
            if old:
                if old["signal_id"] != signal_id or old["action"] != action:
                    raise StoreError("IDEMPOTENCY_CONFLICT", "该幂等键已用于不同反馈")
                return dict(old)
            cursor = db.execute("INSERT INTO feedback(signal_id,action,idempotency_key,at) VALUES(?,?,?,?)", (signal_id, action, key, now()))
            return dict(db.execute("SELECT * FROM feedback WHERE id=?", (cursor.lastrowid,)).fetchone())

    def notifications(self, signal_id=None):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM outbox WHERE signal_id=? ORDER BY created_at DESC,rowid DESC", (signal_id,)).fetchall() if signal_id else db.execute("SELECT * FROM outbox ORDER BY created_at DESC,rowid DESC LIMIT 200").fetchall()
            result = []
            for row in rows:
                obj = dict(row)
                obj["payload"] = json.loads(obj["payload"])
                obj["response"] = json.loads(obj["response"]) if obj["response"] else None
                obj["delivery_attempts"] = [json.loads(r[0]) for r in db.execute("SELECT data FROM attempts WHERE notification_id=? ORDER BY id", (row["id"],))]
                result.append(obj)
        return result

    def log(self, code, message, level="info"):
        with self.connect() as db:
            db.execute("INSERT INTO logs(at,level,code,message) VALUES(?,?,?,?)", (now(), level, code, message))

    def logs(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 100")]

    def pause(self, version, code):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO runtime_flags VALUES(?,?,?)", (version, code, now()))

    def pause_code(self, version):
        with self.connect() as db:
            row = db.execute("SELECT code FROM runtime_flags WHERE version=?", (version,)).fetchone()
        return row[0] if row else None

    def save_job(self, job_id, request):
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?)", (job_id, "pending", now(), now(), dumps(request), None, None))

    def update_job(self, job_id, status, result=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,updated_at=?,result=?,error=? WHERE id=?", (status, now(), dumps(result) if result else None, error, job_id))

    def jobs(self, kind=None):
        with self.connect() as db:
            if kind is None:
                return [self._job(r) for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100")]
            if kind not in {"replay", "study"}:
                raise ValueError("研究任务类型无效")
            # Filter small requests before selecting result blobs. Completed
            # studies can be large and must not be decoded on every replay poll.
            identifiers = []
            for row in db.execute("SELECT id,request FROM jobs ORDER BY created_at DESC"):
                if json.loads(row["request"]).get("kind", "replay") == kind:
                    identifiers.append(row["id"])
                    if len(identifiers) == 100:
                        break
            return [self._job(db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()) for identifier in identifiers]

    def job(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise StoreError("NOT_FOUND", "回放任务不存在")
        return self._job(row)

    @staticmethod
    def _job(row):
        obj = dict(row)
        for key in ("request", "result"):
            obj[key] = json.loads(obj[key]) if obj[key] else None
        return obj

    def backup(self, target):
        target = Path(target).resolve()
        if str(target) == self.path or target.exists():
            raise StoreError("BACKUP_EXISTS", "备份目标必须是不存在的新路径")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(str(target)) as dest:
            source.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise StoreError("BACKUP_INVALID", "备份完整性检查失败")
        os.chmod(target, 0o600)
        return str(target)

    def reset_fixture(self, version):
        config = self.version(version)
        if config["mode"] != "fixture":
            raise StoreError("MODE_FORBIDDEN", "仅允许重置模拟数据")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            ids = [r[0] for r in db.execute("SELECT id FROM signals WHERE version=?", (version,))]
            for sid in ids:
                db.execute("DELETE FROM attempts WHERE notification_id IN (SELECT id FROM outbox WHERE signal_id=?)", (sid,))
                for table in ("events", "outbox", "feedback", "tags"):
                    db.execute("DELETE FROM " + table + " WHERE signal_id=?", (sid,))
            db.execute("DELETE FROM signals WHERE version=?", (version,))
            db.execute("DELETE FROM states WHERE version=?", (version,))
            db.execute("DELETE FROM scans WHERE version=?", (version,))
            db.execute("DELETE FROM runtime_flags WHERE version=?", (version,))
        self.log("DEMO_RESET", "用户重置了模拟场景；研究任务与策略版本保留")
