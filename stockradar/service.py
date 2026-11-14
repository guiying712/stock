"""Application use cases shared by the HTTP service and background CLI worker."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import uuid

from . import __version__
from .config import load_config
from .store import Store, StoreError, digest, dumps, now


class Application:
    def __init__(self, db_path="data/radar.sqlite3", config=None, seed=True):
        self.store = Store(db_path)
        selected = config if config is not None else self.store.running_config() or load_config()
        self.config = self.store.register_version(selected)
        if self.config["mode"] == "live_alert":
            raise StoreError("RELEASE_GATED", "真实提醒尚未完成行情、影子运行和研究发布条件；当前仅支持离线与影子运行")
        self.lock = threading.RLock()
        from .connection_settings import ConnectionSettings
        self.connections = ConnectionSettings(Path(self.store.path).parent / ".connections")
        from .minute_feed import MinuteFeed
        self.minutes = MinuteFeed(Path(self.store.path).parent / "minute-data", self.connections)
        from .real_market import RealMarket
        self.real_market = RealMarket(Path(self.store.path).parent / "real-market", self.connections)
        self.processes = []
        if seed and self.config["mode"] == "fixture" and self.store.latest(self.config["id"]) is None:
            self.advance_demo()
            self.advance_demo()

    def current(self):
        return self.store.latest(self.config["id"]) or {"market": {"status": "UNKNOWN"}, "sectors": [], "signals": [],
                    "quality": {"coverage": None, "expected_count": 0, "valid_count": 0, "status": "unknown", "reason_codes": ["NO_DATA"]}}

    def signal_detail(self, identifier):
        from .evidence import signal_chart
        signal = self.store.detail(identifier)
        signal["chart"] = signal_chart(self.store, signal)
        return signal

    def start_study(self, request):
        from .study_jobs import prepare_request
        with self.lock:
            prepared = prepare_request(self.store, request)
            self.processes = [p for p in self.processes if p.poll() is None]
            if len(self.processes) >= 2:
                raise StoreError("REPLAY_BUSY", "回放与成本研究合计最多同时运行两个任务")
            run_id = uuid.uuid4().hex
            self.store.save_job(run_id, prepared)
            try:
                proc = subprocess.Popen([sys.executable, "-m", "stockradar", "_study-job", "--db", self.store.path, "--id", run_id],
                                        cwd=str(Path(__file__).resolve().parent.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.processes.append(proc)
                prepared["runner_pid"] = proc.pid
                with self.store.connect() as db:
                    db.execute("UPDATE jobs SET request=? WHERE id=?", (dumps(prepared), run_id))
                def monitor():
                    code = proc.wait()
                    if self.store.job(run_id)["status"] in {"pending", "running"}:
                        self.store.update_job(run_id, "failed", error="独立成本研究进程提前退出（%s），原实时信号未改变" % code)
                threading.Thread(target=monitor, daemon=True).start()
            except OSError:
                self.store.update_job(run_id, "failed", error="无法启动独立成本研究进程")
                raise StoreError("REPLAY_START_FAILED", "无法启动独立成本研究进程")
            return {"run_id": run_id, "status": "pending"}

    def advance_demo(self):
        from .fixtures import fixture_batches
        if self.config["mode"] != "fixture":
            raise StoreError("MODE_FORBIDDEN", "只有离线模拟允许推进合成切片")
        with self.lock:
            batches = fixture_batches(self.config.get("schema_version", 1))
            with self.store.connect() as db:
                done = {r[0] for r in db.execute("SELECT snapshot_id FROM scans WHERE version=?", (self.config["id"],))}
            batch = next((b for b in batches if b["snapshot_id"] not in done), None)
            if batch is None:
                return {"complete": True, "message": "模拟场景已完成，可重置后重新观察", "as_of": self.current().get("as_of")}
            result = self.store.apply_batch(batch, self.config)
            return {"complete": False, "as_of": batch["as_of"], "event_count": len(result["events"]),
                    "step": len(done) + 1, "total": len(batches), "message": batch.get("description", "已处理下一模拟切片")}

    def reset_demo(self):
        with self.lock:
            self.store.reset_fixture(self.config["id"])
            self.advance_demo()
            return self.advance_demo()

    def scan(self, batch, *, simulation_delivery=None):
        from .providers import validate_batch
        validate_batch(batch)
        if batch.get("simulated") and self.config["mode"] in {"shadow", "live_alert"}:
            raise StoreError("MODE_MISMATCH", "真实行情模式拒绝模拟输入")
        if not batch.get("simulated") and self.config["mode"] == "fixture":
            raise StoreError("MODE_MISMATCH", "真实输入须使用独立 experimental shadow 配置与数据库")
        if self.config["mode"] == "shadow":
            cutoff = datetime.fromisoformat(batch["as_of"].replace("Z", "+00:00"))
            if (cutoff - datetime.now(timezone.utc)).total_seconds() > 5:
                raise StoreError("FUTURE_DATA", "真实扫描拒绝来自未来时点的批次")
        with self.lock:
            if simulation_delivery is None:
                return self.store.apply_batch(batch, self.config)
            return self.store.apply_batch(batch, self.config, simulation_delivery=simulation_delivery)

    def health(self):
        self.recover_stale_tasks()
        result = self.current()
        quality = deepcopy(result["quality"])
        warnings = list(quality.get("reason_codes", []))
        pause_code = self.store.pause_code(self.config["id"])
        if pause_code:
            warnings.append(pause_code)
        mode = self.config["mode"]
        if mode == "fixture":
            warnings.append("SYNTHETIC_DATA_ONLY")
        as_of = result.get("as_of")
        latency = None
        if as_of and mode == "shadow":
            latency = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(as_of.replace("Z", "+00:00"))).total_seconds())
            if latency > self.config["runtime"]["stale_after_seconds"]:
                warnings.append("DATA_STALE")
        updates_paused = bool(pause_code or "DATA_STALE" in warnings or quality.get("status") != "good")
        if updates_paused:
            quality.update(status="paused", reason_codes=warnings.copy())
        with self.store.connect() as db:
            counts = Counter({r["status"]: r["count"] for r in db.execute("SELECT status,count(*) AS count FROM outbox WHERE channel NOT IN ('inbox','dingtalk_simulation') GROUP BY status")})
            simulations = Counter({r["status"]: r["count"] for r in db.execute("SELECT status,count(*) AS count FROM outbox WHERE channel='dingtalk_simulation' GROUP BY status")})
            row = db.execute("SELECT recorded_at FROM scans WHERE version=? ORDER BY seq DESC LIMIT 1", (self.config["id"],)).fetchone()
            steps = db.execute("SELECT count(*) FROM scans WHERE version=?", (self.config["id"],)).fetchone()[0]
        from .providers import FixtureProvider
        from .dispatcher import dispatcher_status
        return {"version": __version__, "mode": mode, "simulated": mode == "fixture", "as_of": as_of,
                "last_scan": row[0] if row else None, "coverage": quality.get("coverage"),
                "expected_count": quality.get("expected_count", 0), "valid_count": quality.get("valid_count", 0),
                "missing_count": quality.get("expected_count", 0) - quality.get("valid_count", 0),
                "market_status": "UNKNOWN" if updates_paused else result["market"].get("status", "UNKNOWN"),
                "updates_paused": updates_paused,
                "quality": quality, "latency_seconds": latency, "demo_step": steps,
                "provider": {"name": "合成样例" if mode == "fixture" else "已配置数据接口（待验证）",
                             "status": "fixture" if mode == "fixture" else "stale" if "DATA_STALE" in warnings else "unverified",
                             "capabilities": FixtureProvider(self.config.get("schema_version", 1)).capabilities() if mode == "fixture" else {"verified": False}},
                "outbox": {key: counts[key] for key in ("pending", "sending", "accepted", "failed", "unknown", "expired")},
                "simulation_outbox": {key: simulations[key] for key in ("pending", "sending", "accepted", "failed", "unknown", "expired")},
                "dispatcher": dispatcher_status(self.store, self.config["id"]),
                "warnings": warnings, "dingtalk_configured": bool(os.environ.get("DINGTALK_WEBHOOK")),
                "dingtalk_current_target_tested": self._tested_channel(),
                "dingtalk_last_test": self._last_channel_test(),
                "strategy_version": self.config["id"], "boards": list(self.config["preferences"]["boards"])}

    def diagnostics(self):
        result = self.current()
        return {"config": self.config, "rejections": result.get("evaluations", []), "logs": self.store.logs(),
                "quality": result["quality"], "release_gates": [
                    {"name": "离线功能版本", "passed": True, "detail": "完整合成切片、确定性策略、持久化与页面可用；以随附测试报告为准"},
                    {"name": "真实行情服务", "passed": False, "detail": "暂无供应商；批量覆盖、分钟历史、时点成分、授权、费用与限流尚待实测"},
                    {"name": "当前钉钉配置连接测试", "passed": self._tested_channel(), "detail": "仅核对当前目标配置的平台受理；历史其他配置的测试不适用，不代表真实机会路径已通过"},
                    {"name": "真实机会投递路径", "passed": False, "detail": "本地模拟调度已完成；真实聚合呈现、恢复、时延与unknown人工核对待验收"},
                    {"name": "样本外与成本评价", "passed": False, "detail": "已具备显式成本和四组研究；真实授权历史、执行/费用核验与样本外评价待验收"},
                    {"name": "20交易日影子运行", "passed": False, "detail": "须在真实数据服务配置后积累运行与故障演练证据"}],
                "limitations": ["当前小型合成数据集，不代表全市场实际覆盖", "尚未验收真实机会推送", "买入按钮只保存反馈，不生成实际成交或持仓"],
                "runtime": {"database": Path(self.store.path).name, "python": sys.version.split()[0], "code_version": __version__}}

    def _tested_channel(self):
        from .acceptance import channel_fingerprint
        target = channel_fingerprint()
        if target is None:
            return False
        with self.store.connect() as db:
            for row in db.execute("SELECT response FROM outbox WHERE channel='dingtalk_test' AND status='accepted'"):
                if json.loads(row[0] or "{}").get("target_fingerprint") == target:
                    return True
        return False

    def _last_channel_test(self):
        from .acceptance import channel_fingerprint
        target = channel_fingerprint()
        if target is None:
            return None
        with self.store.connect() as db:
            rows = db.execute("SELECT status,updated_at,response FROM outbox WHERE channel='dingtalk_test' ORDER BY created_at DESC,rowid DESC")
            for row in rows:
                if json.loads(row["response"] or "{}").get("target_fingerprint") == target:
                    return {"status": row["status"], "at": row["updated_at"]}
        return None

    def recover_stale_tasks(self):
        """Surface abandoned work; uncertain sends are never silently retried."""
        clock = datetime.now(timezone.utc)
        with self.store.connect() as db:
            for row in db.execute("SELECT id,updated_at,response FROM outbox WHERE channel='dingtalk_test' AND status='sending'").fetchall():
                if (clock - datetime.fromisoformat(row["updated_at"])).total_seconds() > 60:
                    response = {"status": "unknown", "error": "测试发送进程中断，结果未知；请核对群消息后再决定是否重新测试", "retryable": False}
                    target = json.loads(row["response"] or "{}").get("target_fingerprint")
                    if target:
                        response["target_fingerprint"] = target
                    db.execute("UPDATE outbox SET status='unknown',updated_at=?,response=? WHERE id=? AND status='sending'", (now(), dumps(response), row["id"]))
                    db.execute("INSERT INTO attempts(notification_id,at,data) VALUES(?,?,?)", (row["id"], now(), dumps(response)))
            for row in db.execute("SELECT id,request,updated_at FROM jobs WHERE status IN ('pending','running')").fetchall():
                req = json.loads(row["request"])
                pid = req.get("runner_pid")
                if (clock - datetime.fromisoformat(row["updated_at"])).total_seconds() < 60:
                    continue
                alive = False
                if isinstance(pid, int):
                    try:
                        os.kill(pid, 0)
                        alive = True
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        alive = True
                if not alive:
                    db.execute("UPDATE jobs SET status='failed',updated_at=?,error=? WHERE id=?", (now(), "回放进程已中断，可使用原数据和参数重新运行", row["id"]))

    def start_replay(self, request):
        with self.lock:
            return self._start_replay(request)

    def _start_replay(self, request):
        if set(request) - {"dataset_id", "strategy_version"}:
            raise StoreError("INVALID_INPUT", "回放请求存在未知字段")
        dataset_id = request.get("dataset_id", "fixture")
        if not isinstance(dataset_id, str) or not dataset_id.replace("-", "").replace("_", "").isalnum():
            raise StoreError("INVALID_INPUT", "数据集 ID 无效")
        if dataset_id != "fixture" and not (Path(self.store.path).parent / "datasets" / (dataset_id + ".jsonl")).is_file():
            raise StoreError("NOT_FOUND", "数据集尚未导入到 data/datasets/<id>.jsonl")
        version = request.get("strategy_version", self.config["id"])
        self.store.version(version)
        self.processes = [p for p in self.processes if p.poll() is None]
        if len(self.processes) >= 2:
            raise StoreError("REPLAY_BUSY", "最多同时运行两个研究任务，请等待现有任务完成")
        run_id = uuid.uuid4().hex
        self.store.save_job(run_id, {"dataset_id": dataset_id, "strategy_version": version})
        try:
            proc = subprocess.Popen([sys.executable, "-m", "stockradar", "_replay-job", "--db", self.store.path, "--id", run_id],
                                    cwd=str(Path(__file__).resolve().parent.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.processes.append(proc)
            with self.store.connect() as db:
                db.execute("UPDATE jobs SET request=? WHERE id=?", (dumps({"dataset_id": dataset_id, "strategy_version": version, "runner_pid": proc.pid}), run_id))
            def monitor():
                exit_code = proc.wait()
                current = self.store.job(run_id)
                if current["status"] in {"pending", "running"}:
                    self.store.update_job(run_id, "failed", error="独立回放进程提前退出（%s），可重新提交同一输入重放" % exit_code)
            threading.Thread(target=monitor, daemon=True).start()
        except OSError:
            self.store.update_job(run_id, "failed", error="无法启动独立回放进程")
            raise StoreError("REPLAY_START_FAILED", "无法启动独立回放进程")
        return {"run_id": run_id, "status": "pending"}

    def test_channel(self):
        from .acceptance import channel_fingerprint
        from .notifier import DingTalkNotifier, build_message
        url = os.environ.get("DINGTALK_WEBHOOK")
        if not url:
            raise StoreError("CHANNEL_NOT_CONFIGURED", "未配置 DINGTALK_WEBHOOK；请在启动服务的环境中设置钉钉机器人地址")
        notifier = DingTalkNotifier(url, os.environ.get("DINGTALK_SECRET"))
        target_fingerprint = channel_fingerprint()
        notification_id = uuid.uuid4().hex
        signal = {"id": "TEST-" + notification_id[:8], "code": "000000", "name": "连接测试", "status": "PREALERT",
                  "strategy_version": self.config["id"], "score": None, "trigger_time": now(), "latest_time": now(),
                  "trigger_price": None, "latest_price": None, "invalidation_price": None,
                  "entry_low": None, "entry_high": None, "reason_codes": ["CHANNEL_TEST"], "simulated": True}
        event = {"id": notification_id, "at": now(), "to_status": "PREALERT", "reason_codes": ["CHANNEL_TEST"], "revision": 1}
        payload = build_message(signal, event, test=True)
        with self.store.connect() as db:
            db.execute("INSERT INTO outbox(id,revision,channel,status,created_at,updated_at,payload,response) VALUES(?,1,'dingtalk_test','sending',?,?,?,?)",
                       (notification_id, now(), now(), dumps(payload), dumps({"target_fingerprint": target_fingerprint})))
        result = notifier.send(payload, notification_id)
        result = {**result, "target_fingerprint": target_fingerprint}
        with self.store.connect() as db:
            db.execute("UPDATE outbox SET status=?,attempts=1,response=?,updated_at=? WHERE id=?", (result["status"], dumps(result), now(), notification_id))
            db.execute("INSERT INTO attempts(notification_id,at,data) VALUES(?,?,?)", (notification_id, now(), dumps(result)))
        self.store.log("CHANNEL_TEST", "钉钉测试结果：" + result["status"])
        return {"id": notification_id, **result, "message": "仅平台受理，不代表用户已读" if result["status"] == "accepted" else "投递未确认，请查看通知记录"}


def get_token(db_path):
    token = os.environ.get("STOCKRADAR_TOKEN")
    if token:
        if len(token) < 24:
            raise ValueError("STOCKRADAR_TOKEN 至少需要24字符")
        return token
    path = Path(db_path).resolve().parent / ".api-token"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        token = secrets.token_urlsafe(32)
        with os.fdopen(fd, "w") as stream:
            stream.write(token)
    except FileExistsError:
        token = path.read_text().strip()
    if len(token) < 24:
        raise ValueError("本地令牌文件不完整，请在停止服务后重新生成")
    os.chmod(path, 0o600)
    return token
