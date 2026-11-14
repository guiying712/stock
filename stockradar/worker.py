"""Observable single-writer worker and bounded local process supervision."""
import math
import os
import subprocess
import sys
from contextlib import nullcontext
from time import monotonic, sleep

from .contracts import utc
from .operations import WorkerRuntime, initialize, record_incident, validate_operations_plan
from .providers import HTTPJSONProvider, JSONLProvider, ProviderError
from .store import StoreError, now


def run_worker(app, input_path=None, http=False, interval=60, once=False, provider=None,
               dispatch_plan=None, simulation_notifier=None):
    if isinstance(interval, bool) or not isinstance(interval, (float, int)) or not math.isfinite(interval) or interval < 1:
        raise ValueError("轮询间隔须为至少1秒的有限数值")
    if bool(input_path) == bool(http):
        raise ValueError("须且仅须选择JSONL输入或HTTP网关")
    if http and app.config["mode"] != "shadow":
        raise ValueError("HTTP真实行情只允许experimental shadow运行")
    dispatcher = None
    if dispatch_plan is not None:
        from .dispatcher import SimulationDispatcher, validate_dispatch_plan
        plan = validate_dispatch_plan(dispatch_plan)
        if plan["strategy_version"] != app.config["id"]:
            raise ValueError("投递计划须匹配当前采集策略版本")
        dispatcher = SimulationDispatcher(app.store, plan, notifier=simulation_notifier, autostart=False)
    elif simulation_notifier is not None:
        raise ValueError("模拟通知器必须同时提供显式投递计划")
    if provider is None:
        provider = HTTPJSONProvider(os.environ.get("STOCKRADAR_PROVIDER_URL", ""), os.environ.get("STOCKRADAR_PROVIDER_TOKEN")) if http else JSONLProvider(input_path)
    with dispatcher if dispatcher is not None else nullcontext():
        return _scan_loop(app, provider, http, interval, once, dispatcher)


def _scan_loop(app, provider, http, interval, once, dispatcher):
    with WorkerRuntime(app.store, app.config, "http" if http else "jsonl", provider.capabilities()) as runtime:
        if dispatcher is not None:
            dispatcher.start()
        def scan(batch):
            context = dispatcher.delivery_for(batch["as_of"]) if dispatcher is not None else None
            result = runtime.scan(app, batch, simulation_delivery=context)
            if dispatcher is not None:
                dispatcher.after_scan(batch["as_of"], result.get("duplicate", False))
            return result
        if not http:
            for batch in provider.iter_batches():
                result = scan(batch)
                print("切片已处理" + ("（重复输入，无新业务事件）" if result.get("duplicate") else ""), flush=True)
                if once:
                    break
            if dispatcher is not None:
                dispatcher.drain()
            return
        while True:
            delay = interval
            try:
                scan(provider.get_slice())
                print("shadow切片已处理，外部机会提醒关闭", flush=True)
            except (ProviderError, ValueError) as exc:
                if dispatcher is not None:
                    dispatcher.check()
                code = exc.code if isinstance(exc, ProviderError) else "DATA_INVALID"
                runtime.fault(code)
                if dispatcher is not None:
                    dispatcher.wake()
                app.store.log(code, "工作进程暂停，等待新的有效行情", "error")
                print(code + "：工作进程暂停", file=sys.stderr, flush=True)
                if isinstance(exc, ProviderError):
                    delay = max(interval, exc.retry_after or 0)
                if once:
                    raise
            if once:
                break
            runtime.wait(delay, sleep)
        if dispatcher is not None:
            dispatcher.drain()


def supervise_worker(store, config, plan, input_path=None, http=False, interval=60,
                     process_factory=subprocess.Popen, pause=sleep, clock=monotonic,
                     simulation_dispatch_plan=None):
    """Restart only this child, with bounded exponential backoff and watchdog.

    No OS service is installed and no notification credentials are read here.
    The child continues using the existing live_alert application gate.
    """
    validate_operations_plan(plan)
    if config["id"] != plan["strategy_version"] or bool(input_path) == bool(http):
        raise ValueError("守护配置版本或输入方式不匹配")
    if config["mode"] not in {"fixture", "shadow"}:
        raise StoreError("RELEASE_GATED", "守护仅支持离线或shadow，不能启用真实提醒")
    if http and config["mode"] != "shadow":
        raise ValueError("HTTP守护只允许shadow配置")
    initialize(store)
    command = [sys.executable, "-m", "stockradar", "worker", "--db", store.path, "--interval", str(interval)]
    # A saved config file is deliberately not needed: the child gets an
    # existing immutable strategy ID via a separate, explicit CLI argument.
    command += ["--saved-version", config["id"]]
    command += ["--http"] if http else ["--input", str(input_path)]
    if simulation_dispatch_plan is not None:
        from pathlib import Path
        from .contracts import load_json
        from .dispatcher import validate_dispatch_plan
        dispatch_plan = validate_dispatch_plan(load_json(simulation_dispatch_plan))
        if dispatch_plan["strategy_version"] != config["id"]:
            raise ValueError("投递计划须匹配守护的策略版本")
        command += ["--simulation-dispatch-plan", str(Path(simulation_dispatch_plan).resolve())]
    restarts, child = 0, None
    try:
        while True:
            started = clock()
            child = process_factory(command, cwd=os.getcwd(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            stale = False
            while child.poll() is None:
                pause(0.25)
                if clock() - started <= plan["heartbeat_timeout_seconds"]:
                    continue
                with store.connect() as db:
                    row = db.execute("SELECT heartbeat_at FROM ops_runs WHERE pid=? ORDER BY started_at DESC LIMIT 1", (child.pid,)).fetchone()
                if row is None or (utc(now()) - utc(row[0])).total_seconds() > plan["heartbeat_timeout_seconds"]:
                    stale = True
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
                    record_incident(store, config["id"], "WORKER_HEARTBEAT_STALE")
                    break
            exit_code = child.wait()
            if exit_code == 0 and not stale:
                return {"status": "stopped", "restarts": restarts, "exit_code": 0}
            record_incident(store, config["id"], "WORKER_CHILD_FAILED")
            if restarts >= plan["restart_limit"]:
                record_incident(store, config["id"], "WORKER_RESTART_EXHAUSTED")
                raise StoreError("WORKER_RESTART_EXHAUSTED", "工作进程连续失败，已达到重启上限；请检查内置通知与运行日志")
            delay = min(plan["max_restart_backoff_seconds"], plan["restart_backoff_seconds"] * 2 ** restarts)
            restarts += 1
            pause(delay)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
