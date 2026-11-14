"""Independent ZSXQ event store: cross-capture dedup, revisions and coverage.

Run with ``python3 -m stockradar.zsxq_store --help``. The store is a separate
SQLite file; it never touches the strategy database, notifiers or evaluate.
It does not schedule anything: each ``fetch`` is one explicit, budgeted page.

Coverage semantics: the source lists topics newest-first. A page proves that
no topic was missed between its oldest and newest entries. It only joins the
previous coverage when it re-observes an already stored topic inside that
coverage; otherwise the interval in between is recorded as an open gap.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from zoneinfo import ZoneInfo

from .zsxq_events import GROUP_ID, MAX_BYTES, fetch as cli_fetch, normalize

SHANGHAI = ZoneInfo("Asia/Shanghai")
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, mode TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, completed_at TEXT, budget_date TEXT,
  requested_limit INTEGER, observed_at TEXT, fetched_count INTEGER, unique_count INTEGER,
  has_more INTEGER, new_topics INTEGER, new_revisions INTEGER, unchanged INTEGER,
  coverage TEXT, error_code TEXT, source_sha256 TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS topics(
  topic_id TEXT PRIMARY KEY, published_at TEXT NOT NULL,
  first_observed_at TEXT NOT NULL, last_observed_at TEXT NOT NULL,
  latest_hash TEXT NOT NULL, revision_count INTEGER NOT NULL, observation_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS revisions(
  topic_id TEXT NOT NULL, content_hash TEXT NOT NULL, first_observed_at TEXT NOT NULL,
  first_run TEXT NOT NULL, record TEXT NOT NULL, PRIMARY KEY(topic_id, content_hash));
CREATE TABLE IF NOT EXISTS observations(
  run_id TEXT NOT NULL, topic_id TEXT NOT NULL, content_hash TEXT NOT NULL,
  PRIMARY KEY(run_id, topic_id));
CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY, oldest_published_at TEXT NOT NULL, newest_published_at TEXT NOT NULL,
  reaches_start INTEGER NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gaps(
  id INTEGER PRIMARY KEY, after_published_at TEXT NOT NULL, before_published_at TEXT NOT NULL,
  detected_run TEXT NOT NULL, status TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def utc(value):
    return datetime.fromisoformat(value)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class EventStore:
    def __init__(self, path, clock=now):
        self.path = Path(path)
        self.clock = clock
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise ValueError("事件数据库及目录不能为符号链接")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript(SCHEMA)
            row = db.execute("SELECT value FROM meta WHERE key='group_id'").fetchone()
            if row is None:
                db.execute("INSERT INTO meta VALUES('schema_version','1'),('group_id',?)", (GROUP_ID,))
            elif row[0] != GROUP_ID:
                raise ValueError("事件数据库属于其他星球")
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @contextmanager
    def lock(self):
        path = self.path.with_name(self.path.name + ".collect.lock")
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("另一个事件采集正在运行；未发起读取") from None
            yield
        finally:
            os.close(fd)

    # -- budget and run bookkeeping -------------------------------------
    def budget_used(self, day):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM runs WHERE mode='manual_fetch' AND budget_date=?",
                              (day,)).fetchone()[0]

    def recover_interrupted(self):
        """A started fetch whose process vanished stays counted and visible."""
        with self.transaction() as db:
            return db.execute("UPDATE runs SET status='interrupted', error_code='PROCESS_INTERRUPTED' "
                              "WHERE status='started'").rowcount

    def begin_fetch(self, limit, daily_budget):
        if type(daily_budget) is not int or not 1 <= daily_budget <= 1000:
            raise ValueError("每日请求预算须为 1—1000 的整数")
        started = self.clock()
        day = utc(started).astimezone(SHANGHAI).date().isoformat()
        run_id = uuid.uuid4().hex
        with self.transaction() as db:
            used = db.execute("SELECT count(*) FROM runs WHERE mode='manual_fetch' AND budget_date=?",
                              (day,)).fetchone()[0]
            if used >= daily_budget:
                raise ValueError("北京时间 %s 的事件请求预算已用尽（%d/%d）；未发起读取" % (day, used, daily_budget))
            # Recorded and committed before any network so a crash cannot refund budget.
            db.execute("INSERT INTO runs(id,mode,status,started_at,budget_date,requested_limit) "
                       "VALUES(?,?,?,?,?,?)", (run_id, "manual_fetch", "started", started, day, limit))
        return run_id

    def fail_run(self, run_id, code):
        with self.transaction() as db:
            db.execute("UPDATE runs SET status='failed',completed_at=?,error_code=? WHERE id=?",
                       (self.clock(), code, run_id))

    # -- applying a normalized page -------------------------------------
    def apply(self, report, run_id=None, mode="manual_fetch", source_sha256=None):
        if report.get("group_id") != GROUP_ID or report.get("schema_version") != 1:
            raise ValueError("快照不属于指定星球或版本不支持")
        topics = report["topics"]
        observed = report["observed_at"]
        with self.transaction() as db:
            if source_sha256:
                old = db.execute("SELECT id FROM runs WHERE source_sha256=?", (source_sha256,)).fetchone()
                if old:
                    return dict(run_id=old["id"], duplicate=True)
            if run_id is None:
                run_id = uuid.uuid4().hex
                db.execute("INSERT INTO runs(id,mode,status,started_at) VALUES(?,?,?,?)",
                           (run_id, mode, "started", self.clock()))
            coverage = self._coverage(db, topics, report["has_more"], run_id)
            counts = dict(new_topics=0, new_revisions=0, unchanged=0)
            for topic in topics:
                record = dumps(topic)
                existing = db.execute("SELECT * FROM topics WHERE topic_id=?", (topic["topic_id"],)).fetchone()
                known = db.execute("SELECT first_observed_at FROM revisions WHERE topic_id=? AND content_hash=?",
                                   (topic["topic_id"], topic["content_hash"])).fetchone()
                if not known:
                    db.execute("INSERT INTO revisions VALUES(?,?,?,?,?)",
                               (topic["topic_id"], topic["content_hash"], observed, run_id, record))
                elif utc(observed) < utc(known["first_observed_at"]):
                    db.execute("UPDATE revisions SET first_observed_at=?, first_run=? WHERE topic_id=? AND content_hash=?",
                               (observed, run_id, topic["topic_id"], topic["content_hash"]))
                if existing is None:
                    counts["new_topics"] += 1
                    db.execute("INSERT INTO topics VALUES(?,?,?,?,?,1,1)",
                               (topic["topic_id"], topic["published_at"], observed, observed, topic["content_hash"]))
                    continue
                if existing["published_at"] != topic["published_at"]:
                    raise ValueError("同一主题的发布时间发生变化；保留原记录并停止导入")
                changed = existing["latest_hash"] != topic["content_hash"]
                counts["new_revisions" if changed and not known else "unchanged"] += 1
                # Observation order may differ from capture order (offline imports).
                later = utc(observed) >= utc(existing["last_observed_at"])
                db.execute("UPDATE topics SET first_observed_at=?, last_observed_at=?, latest_hash=?, "
                           "revision_count=revision_count+?, observation_count=observation_count+1 WHERE topic_id=?",
                           (min(observed, existing["first_observed_at"], key=utc),
                            max(observed, existing["last_observed_at"], key=utc),
                            topic["content_hash"] if later else existing["latest_hash"],
                            0 if known else 1, topic["topic_id"]))
            db.executemany("INSERT OR IGNORE INTO observations VALUES(?,?,?)",
                           [(run_id, t["topic_id"], t["content_hash"]) for t in topics])
            db.execute("UPDATE runs SET status='completed',completed_at=?,observed_at=?,fetched_count=?,"
                       "unique_count=?,has_more=?,new_topics=?,new_revisions=?,unchanged=?,coverage=?,"
                       "source_sha256=? WHERE id=?",
                       (self.clock(), observed, report["fetched_count"], report["unique_count"],
                        int(report["has_more"]), counts["new_topics"], counts["new_revisions"],
                        counts["unchanged"], coverage, source_sha256, run_id))
        return dict(run_id=run_id, duplicate=False, coverage=coverage, **counts)

    def _coverage(self, db, topics, has_more, run_id):
        if not topics:
            return "empty_page"
        times = [t["published_at"] for t in topics]
        if any(utc(a) < utc(b) for a, b in zip(times, times[1:])):
            # Without newest-first order a page proves nothing about gaps.
            return "order_unverified"
        newest, oldest = times[0], times[-1]
        stamp = self.clock()
        segments = db.execute("SELECT * FROM segments").fetchall()
        head = max(segments, key=lambda r: utc(r["newest_published_at"])) if segments else None
        if not has_more:
            # The page holds every remaining topic: all earlier gaps are closed.
            db.execute("DELETE FROM segments")
            db.execute("UPDATE gaps SET status='closed' WHERE status='open'")
            low = min([oldest] + [r["oldest_published_at"] for r in segments], key=utc)
            high = max([newest] + [r["newest_published_at"] for r in segments], key=utc)
            db.execute("INSERT INTO segments(oldest_published_at,newest_published_at,reaches_start,updated_at) "
                       "VALUES(?,?,1,?)", (low, high, stamp))
            return "complete_to_start"
        if head is None:
            db.execute("INSERT INTO segments(oldest_published_at,newest_published_at,reaches_start,updated_at) "
                       "VALUES(?,?,0,?)", (oldest, newest, stamp))
            return "initial"
        ids = [t["topic_id"] for t in topics]
        marks = ",".join("?" * len(ids))
        rows = db.execute("SELECT published_at FROM topics WHERE topic_id IN (%s)" % marks, ids).fetchall()
        overlap = any(utc(head["oldest_published_at"]) <= utc(r[0]) <= utc(head["newest_published_at"]) for r in rows)
        if overlap and utc(oldest) <= utc(head["newest_published_at"]):
            db.execute("UPDATE segments SET newest_published_at=?, oldest_published_at=?, updated_at=? WHERE id=?",
                       (max(newest, head["newest_published_at"], key=utc),
                        min(oldest, head["oldest_published_at"], key=utc), stamp, head["id"]))
            return "contiguous"
        db.execute("INSERT INTO gaps(after_published_at,before_published_at,detected_run,status) VALUES(?,?,?,'open')",
                   (head["newest_published_at"], oldest, run_id))
        db.execute("INSERT INTO segments(oldest_published_at,newest_published_at,reaches_start,updated_at) "
                   "VALUES(?,?,0,?)", (oldest, newest, stamp))
        return "gap_recorded"

    # -- read-only summary ----------------------------------------------
    def status(self, daily_budget=None):
        with self.connect() as db:
            q = lambda sql, *a: db.execute(sql, a).fetchone()[0]
            today = utc(self.clock()).astimezone(SHANGHAI).date().isoformat()
            segments = [dict(r) for r in db.execute(
                "SELECT oldest_published_at,newest_published_at,reaches_start FROM segments "
                "ORDER BY newest_published_at DESC")]
            gaps = [dict(r) for r in db.execute(
                "SELECT after_published_at,before_published_at,detected_run FROM gaps WHERE status='open' "
                "ORDER BY before_published_at DESC")]
            last = db.execute("SELECT id,mode,status,started_at,completed_at,coverage,error_code,new_topics,"
                              "new_revisions,unchanged FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
            used = q("SELECT count(*) FROM runs WHERE mode='manual_fetch' AND budget_date=?", today)
            return dict(schema_version=1, group_id=GROUP_ID,
                        topics=q("SELECT count(*) FROM topics"),
                        revisions=q("SELECT count(*) FROM revisions"),
                        revised_topics=q("SELECT count(*) FROM topics WHERE revision_count>1"),
                        runs={r[0]: r[1] for r in db.execute("SELECT status,count(*) FROM runs GROUP BY status")},
                        budget=dict(date=today, used=used, limit=daily_budget,
                                    remaining=None if daily_budget is None else max(0, daily_budget - used)),
                        coverage_segments=segments, open_gaps=gaps,
                        history_complete=bool(segments and len(segments) == 1 and segments[0]["reaches_start"]
                                              and not gaps),
                        last_run=dict(last) if last else None,
                        automatic_collection=False, strategy_input_ready=False, release_allowed=False)


def import_capture(store, directory):
    """Import a saved zsxq_events capture after verifying its manifest hash."""
    directory = Path(directory)
    data = (directory / "topics.json").read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError("快照超过大小上限")
    manifest = json.loads((directory / "manifest.json").read_text())
    digest = hashlib.sha256(data).hexdigest()
    if manifest.get("topics_sha256") != digest or manifest.get("group_id") != GROUP_ID:
        raise ValueError("快照哈希或星球不匹配；未导入")
    report = json.loads(data)
    return store.apply(report, mode="capture_import", source_sha256=digest)


def fetch_once(store, cli, limit, daily_budget, fetcher=cli_fetch):
    with store.lock():
        store.recover_interrupted()
        run_id = store.begin_fetch(limit, daily_budget)
        try:
            payload = fetcher(cli, limit)
            report = normalize(payload, store.clock(), limit)
        except ValueError:
            store.fail_run(run_id, "FETCH_OR_VALIDATION_FAILED")
            raise
        return store.apply(report, run_id=run_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description="知识星球事件库：跨次去重、修订与覆盖水位；不生成策略信号")
    parser.add_argument("--db", required=True, help="独立事件数据库，勿使用策略数据库")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="导入已保存的 zsxq_events 快照目录；不发网")
    imp.add_argument("captures", nargs="+")
    get = sub.add_parser("fetch", help="手动读取最新一页并入库；预算先记账")
    get.add_argument("--cli", required=True)
    get.add_argument("--limit", type=int, choices=range(1, 21), required=True)
    get.add_argument("--daily-budget", type=int, required=True, help="北京时间自然日请求上限，含失败")
    stat = sub.add_parser("status", help="只读汇总")
    stat.add_argument("--daily-budget", type=int)
    args = parser.parse_args(argv)
    try:
        store = EventStore(args.db)
        if args.command == "import":
            results = [dict(capture=str(Path(c).name), **import_capture(store, c)) for c in args.captures]
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif args.command == "fetch":
            print(json.dumps(fetch_once(store, args.cli, args.limit, args.daily_budget), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(store.status(args.daily_budget), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, sqlite3.DatabaseError) as error:
        parser.exit(1, "事件库操作未完成：%s\n" % (error if isinstance(error, ValueError) else type(error).__name__))


if __name__ == "__main__":
    main()
