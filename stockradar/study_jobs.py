"""Independent study jobs sharing the existing durable job ledger."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from .contracts import load_json
from .research import validate_study_plan
from .store import StoreError, digest


CARD_REPORT_LIMIT = 8
CARD_REPORT_BYTES = 128 * 1024 * 1024


def local_file(store, directory, identifier, suffix):
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
        raise StoreError("INVALID_INPUT", "本地研究文件ID只接受字母、数字、下划线和连字符")
    root = Path(store.path).parent / directory
    path = root / (identifier + suffix)
    if root.is_symlink() or path.is_symlink() or not path.is_file() or path.resolve().parent != root.resolve():
        raise StoreError("NOT_FOUND", "研究文件尚未放入独立数据库旁的指定目录")
    return path


def file_hash(path):
    if path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("页面研究文件上限256MiB；更大研究请使用CLI独立运行")
    result = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def prepare_request(store, request):
    if not isinstance(request, dict) or set(request) != {"dataset_id", "plan_id"}:
        raise StoreError("INVALID_INPUT", "成本研究须显式提供dataset_id和plan_id，且不接受未知字段")
    dataset_id, plan_id = request["dataset_id"], request["plan_id"]
    from .replay import source_hash
    result = {"kind": "study", "dataset_id": dataset_id, "plan_id": plan_id, "submitted_code_hash": source_hash()}
    if dataset_id == "fixture" and plan_id == "fixture":
        return result
    if dataset_id == "fixture" or plan_id == "fixture":
        raise StoreError("INVALID_INPUT", "内置合成数据与计划必须配对使用")
    data = local_file(store, "datasets", dataset_id, ".jsonl")
    plan = validate_study_plan(load_json(local_file(store, "study-plans", plan_id, ".json")))
    result.update(plan=plan, input_sha256=file_hash(data))
    return result


def sources(store):
    result = {"datasets": ["fixture"], "plans": ["fixture"]}
    for directory, suffix, key in (("datasets", ".jsonl", "datasets"), ("study-plans", ".json", "plans")):
        root = Path(store.path).parent / directory
        if root.is_dir() and not root.is_symlink():
            for path in sorted(root.iterdir()):
                if path.suffix == suffix and path.stem != "fixture" and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", path.stem) and path.is_file() and not path.is_symlink():
                    result[key].append(path.stem)
                if len(result[key]) >= 100:
                    break
    return result


def list_jobs(store):
    result = []
    with store.connect() as db:
        for row in db.execute("SELECT id,status,created_at,updated_at,request,error FROM jobs ORDER BY created_at DESC, rowid DESC"):
            request = json.loads(row["request"])
            if request.get("kind") == "study":
                result.append({**dict(row), "request": {key: request[key] for key in ("kind", "dataset_id", "plan_id")}})
            if len(result) == 30:
                break
    return result


def get_job(store, identifier, full=False):
    job = store.job(identifier)
    if job["request"].get("kind") != "study":
        raise StoreError("NOT_FOUND", "成本研究任务不存在")
    job["request"] = {key: job["request"][key] for key in ("kind", "dataset_id", "plan_id")}
    if job["result"] is not None and not full:
        result = job["result"]
        job["result"] = {key: deepcopy(value) for key, value in result.items() if key != "profiles"}
        job["result"]["profiles"] = [{key: deepcopy(value) for key, value in profile.items()
                                      if key not in {"samples", "signal_refs"}} for profile in result["profiles"]]
    return job


def _card_window(plan):
    delays, horizons = plan["reaction_delays_minutes"], plan["holding_windows_days"]
    split = next(item for item in plan["splits"] if item["name"] == "test")
    return {"split": split["name"], "delay_minutes": 1 if 1 in delays else min(delays),
            "holding_days": 5 if 5 in horizons else min(horizons), "exit_mode": "fixed"}


def _window_match(item, window):
    return all(item[key] == value for key, value in window.items())


def study_cards(store):
    """Group saved runs by their exact profile configuration, without pooling outcomes."""
    cards, reports, skipped, total_bytes = {}, set(), 0, 0
    jobs = [job for job in list_jobs(store) if job["status"] == "completed"]
    for job in jobs:
        with store.connect() as db:
            row = db.execute("SELECT length(CAST(result AS BLOB)) FROM jobs WHERE id=? AND status='completed'",
                             (job["id"],)).fetchone()
        size = row[0] if row else None
        if not size or len(reports) >= CARD_REPORT_LIMIT or total_bytes + size > CARD_REPORT_BYTES:
            skipped += 1
            continue
        total_bytes += size
        try:
            report = get_job(store, job["id"], full=True)["result"]
        except (StoreError, json.JSONDecodeError):
            skipped += 1
            continue
        if not isinstance(report, dict) or report.get("kind") != "assumption_based_independent_signal_study":
            skipped += 1
            continue
        sha = report["output_hash"]
        if sha in reports:
            continue
        reports.add(sha)
        plan = report["plan"]
        window = _card_window(plan)
        split = next(item for item in plan["splits"] if item["name"] == window["split"])
        configs = {item["id"]: item["config"] for item in plan["profiles"]}
        for profile in report["profiles"]:
            config = configs[profile["id"]]
            if digest(config) != profile["config_hash"]:
                continue
            cell = next((item for item in profile["summaries"] if _window_match(item, window)), None)
            if cell is None:
                continue
            key = profile["config_hash"], profile["id"], report["simulated"]
            card = cards.setdefault(key, {
                "config_hash": key[0], "profile_id": key[1], "simulated": key[2],
                "strategy_version": config["id"], "strategy_id": config["strategy_id"],
                "weights": {name: group["weight"] for name, group in config["scoring"]["groups"].items()},
                "requirements": {"benchmark_id": plan["benchmark_id"], "sector_filter": config["research"]["sector_filter"],
                                 "alert_stage": config["research"]["alert_stage"]},
                "runs": [],
            })
            card["runs"].append({
                "job_id": job["id"], "created_at": job["created_at"], **job["request"],
                "window": window, "split_start": split["start"], "split_end": split["end"],
                "plan_hash": report["plan_hash"], "data_hash": report["data_hash"], "code_hash": report["code_hash"], "output_hash": sha,
                "freeze_reasons": report["parameter_freeze"]["reasons"], "observation_gaps": report["observation_gaps"],
                "counts": {name: cell[name] for name in ("closed_count", "eligible_denominator", "status_counts",
                            "structure_failures", "structure_failure_denominator", "revenue_failures",
                            "revenue_failure_denominator", "reason_counts")},
                "net_return_mean": cell["net_return_mean"], "benchmark_excess": cell["benchmark_excess"],
            })
    return {"items": list(cards.values()), "report_count": len(reports), "skipped_count": skipped}


def study_cases(store, job_id, profile_id):
    if not isinstance(profile_id, str) or profile_id not in {"stock_only", "sector_filter", "early", "confirmed"}:
        raise ValueError("请选择研究对照组")
    with store.connect() as db:
        row = db.execute("SELECT length(CAST(result AS BLOB)) FROM jobs WHERE id=? AND status='completed'", (job_id,)).fetchone()
    if row and row[0] is not None and row[0] > CARD_REPORT_BYTES:
        raise ValueError("该报告超出页面案例预览上限，可导出完整报告")
    job = get_job(store, job_id, full=True)
    if job["status"] != "completed" or not job["result"]:
        raise StoreError("STUDY_NOT_COMPLETED", "成本研究尚未完成")
    report = job["result"]
    if not isinstance(report, dict) or report.get("kind") != "assumption_based_independent_signal_study":
        raise StoreError("NOT_FOUND", "该报告没有可预览的研究案例")
    window = _card_window(report["plan"])
    profile = next((item for item in report["profiles"] if item["id"] == profile_id), None)
    if profile is None:
        raise StoreError("NOT_FOUND", "研究对照组不存在")
    failures, unresolved = [], []
    for sample in profile["samples"]:
        if not _window_match(sample, window):
            continue
        if sample["status"] == "closed" and (sample["structure_failure"] is True or sample["revenue_failure"] is True):
            failures.append(sample)
        elif sample["status"] in {"pending", "not_filled"}:
            unresolved.append(sample)
    failures.sort(key=lambda sample: (sample["net_return"], sample["signal_id"]))
    refs = profile.get("signal_refs", {})
    return {"job_id": job_id, "profile_id": profile_id, "simulated": report["simulated"], "window": window,
            "output_hash": report["output_hash"], "failure_count": len(failures), "unresolved_count": len(unresolved),
            "items": [dict(sample, signal=refs.get(sample["signal_id"])) for sample in failures[:6] + unresolved[:4]]}


def run_job(store, identifier):
    job = store.job(identifier)
    store.update_job(identifier, "running")
    try:
        request = job["request"]
        from .replay import source_hash
        if request["submitted_code_hash"] != source_hash():
            raise ValueError("代码在提交后发生变化，请使用同一版本重新提交研究")
        if request["dataset_id"] == "fixture":
            from .study_fixture import make_study_fixture
            batches, plan = make_study_fixture(30)
        else:
            from .providers import JSONLProvider
            path = local_file(store, "datasets", request["dataset_id"], ".jsonl")
            if file_hash(path) != request["input_sha256"]:
                raise ValueError("行情文件在提交后发生变化，请使用新数据集ID重新提交")
            batches, plan = list(JSONLProvider(path).iter_batches()), request["plan"]
            if file_hash(path) != request["input_sha256"]:
                raise ValueError("研究读取期间行情文件发生变化，未生成结果")
        from .research import run_study
        result = run_study(batches, plan)
        if source_hash() != request["submitted_code_hash"] or result["code_hash"] != request["submitted_code_hash"]:
            raise ValueError("研究计算期间代码发生变化，未保存结果")
        store.update_job(identifier, "completed", result=result)
    except Exception:
        # Paths and external input text may contain secrets. Details remain in
        # validated reports, never raw exceptions in the page or job ledger.
        store.update_job(identifier, "failed", error="研究未完成：请核对数据/代码是否变化、模拟标记、显式计划及执行证据；可使用CLI校验原输入")
