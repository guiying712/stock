"""Bounded synthetic load/concurrency measurements, never market coverage proof."""
from copy import deepcopy
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
from time import monotonic

from .contracts import integer
from .fixtures import fixture_batches
from .providers import record_batches
from .replay import source_hash
from .service import Application


def load_batches(symbols):
    integer(symbols, 12, 6000, "合成证券数")
    if symbols % 12:
        raise ValueError("合成证券数须为12的整数倍")
    originals = fixture_batches()[:2]
    output = []
    for original in originals:
        quote_ids = {q["instrument_id"] for q in original["quotes"]}
        universe = [i for i in original["instruments"] if i["id"] in quote_ids]
        # Keep the existing 12-symbol workload unit, with explicit STAR members.
        cohort = [i for i in universe if i["board"] != "STAR"][:10] + [i for i in universe if i["board"] == "STAR"][:2]
        batch = {key: deepcopy(value) for key, value in original.items()
                 if key not in {"instruments", "quotes", "daily_bars", "minute_history", "memberships"}}
        batch.update(source="synthetic-load-only", snapshot_id="load-%d-%s" % (symbols, original["snapshot_id"]),
                     instruments=[], quotes=[], daily_bars=[], minute_history=[], memberships=[])
        for group in range(symbols // 12):
            mapping = {}
            for index, instrument in enumerate(cohort):
                current = deepcopy(instrument)
                number = group * 12 + index + 1
                base = 688000 if current["board"] == "STAR" else 600000 if current["exchange"] == "SSE" else 300000 if current["board"] == "CHINEXT" else 0
                code = "%06d" % (base + number)
                current.update(id=current["exchange"] + "." + code, code=code, name="合成负载%d" % number)
                mapping[instrument["id"]] = current["id"]
                batch["instruments"].append(current)
            for name in ("quotes", "daily_bars", "minute_history", "memberships"):
                for item in original[name]:
                    if item["instrument_id"] in mapping:
                        current = deepcopy(item)
                        current["instrument_id"] = mapping[item["instrument_id"]]
                        batch[name].append(current)
        output.append(batch)
    return output


def run_benchmark(symbol_counts, iterations=2, concurrent_replays=2):
    integer(iterations, 1, 10, "压测轮数")
    integer(concurrent_replays, 0, 2, "并行回放数量")
    if not symbol_counts or len(symbol_counts) > 6 or len(set(symbol_counts)) != len(symbol_counts):
        raise ValueError("须提供1至6个不重复的合成证券规模")
    cases = []
    with tempfile.TemporaryDirectory(prefix="stockradar-load-") as directory:
        root = Path(directory)
        for symbols in symbol_counts:
            batches = load_batches(symbols)
            latencies = []
            size = 0
            for iteration in range(iterations):
                app = Application(str(root / ("load-%d-%d.sqlite3" % (symbols, iteration))), seed=False)
                for batch in batches:
                    start = monotonic()
                    result = app.scan(batch)
                    latencies.append(monotonic() - start)
                    if result["quality"]["expected_count"] != symbols:
                        raise ValueError("压测股票池分母与声明规模不一致")
                size = max(size, sum(Path(app.store.path + suffix).stat().st_size for suffix in ("", "-wal", "-shm") if Path(app.store.path + suffix).exists()))
            from .operations import percentile95
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            cases.append({"synthetic_symbols": symbols, "scans": len(latencies), "scan_commit_p95_seconds": percentile95(latencies),
                          "scan_commit_max_seconds": max(latencies), "database_and_wal_bytes": size,
                          "process_peak_rss_bytes": peak if sys.platform == "darwin" else peak * 1024})
        concurrency = {"workers": concurrent_replays, "synthetic_symbols_per_worker": 15, "elapsed_seconds": None, "completed": 0}
        if concurrent_replays:
            tape = root / "replay.jsonl"
            record_batches(tape, fixture_batches())
            processes = []
            start = monotonic()
            try:
                for index in range(concurrent_replays):
                    command = [sys.executable, "-m", "stockradar", "replay", "--input", str(tape), "--db", str(root / ("replay-%d.sqlite3" % index)), "--output", str(root / ("replay-%d.json" % index))]
                    processes.append(subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                for process in processes:
                    if process.wait(timeout=180) != 0:
                        raise ValueError("并行回放进程失败")
                    concurrency["completed"] += 1
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
            concurrency["elapsed_seconds"] = monotonic() - start
            reports = [json.loads((root / ("replay-%d.json" % i)).read_text()) for i in range(concurrent_replays)]
            if len({r["dataset_hash"] for r in reports}) != 1:
                raise ValueError("并行回放输入哈希不一致")
            if any(r != reports[0] for r in reports[1:]):
                raise ValueError("并行回放结果不一致")
            concurrency["dataset_hash"] = reports[0]["dataset_hash"]
            concurrency["identical_results"] = True
    return {"schema_version": 1, "kind": "synthetic_local_load", "simulated": True, "code_hash": source_hash(),
            "cases": cases, "concurrent_replay": concurrency, "full_market_verified": False,
            "platform_acceptance_p95_seconds": None,
            "limitations": ["证券数为合成负载，不代表真实股票池、上游历史覆盖或平台受理时延",
                            "并行回放固定使用15证券合成数据，不能推导该并发在最大规模时仍通过",
                            "RSS为本进程截至该点的峰值；运行耗时和磁盘增长仅对应本机本次样本"]}
