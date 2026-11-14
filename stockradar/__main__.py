"""Run directly from the checkout: python3 -m stockradar --help."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .config import load_config
from .store import Store, StoreError, dumps, now


def replay_job(store, run_id):
    from .fixtures import fixture_batches
    from .providers import JSONLProvider
    from .replay import run_replay
    job = store.job(run_id)
    store.update_job(run_id, "running")
    try:
        dataset_id = job["request"]["dataset_id"]
        config = store.version(job["request"]["strategy_version"])
        batches = fixture_batches(config.get("schema_version", 1)) if dataset_id == "fixture" else list(JSONLProvider(Path(store.path).parent / "datasets" / (dataset_id + ".jsonl")).iter_batches())
        result = run_replay(batches, config)
        store.update_job(run_id, "completed", result=result)
    except Exception as exc:
        # Strategy/data errors contain field names, not requests or credential URLs.
        message = str(exc) if isinstance(exc, (ValueError, KeyError, TypeError)) else "回放失败，请校验数据集和配置"
        store.update_job(run_id, "failed", error=message[:1000])


def main(argv=None):
    parser = argparse.ArgumentParser(description="观势 · 本地 A 股热点启动与突破提醒工作台")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("serve", "worker", "demo", "replay", "export-fixture", "backup", "restore", "_replay-job", "_study-job", "study", "export-study-fixture", "ops-report", "supervise", "archive-scans", "benchmark", "dispatcher", "dispatch-report", "provider-poc", "channel-poc", "vendor-sample", "compare-vendor-samples", "minute-quality", "minute-acceptance-plan"):
        p = sub.add_parser(command)
        if command not in {"vendor-sample", "compare-vendor-samples", "minute-quality", "minute-acceptance-plan"}:
            p.add_argument("--db", default=None if command == "channel-poc" else "data/radar.sqlite3", required=command == "channel-poc", help="独立模式应使用独立数据库")
        if command == "vendor-sample":
            p.add_argument("--plan", required=True, help="供应商小样本计划；凭据只从环境变量读取")
            p.add_argument("--output-dir", required=True, help="不存在的新目录；原始样本不会送入策略或数据库")
            p.add_argument("--dry-run", action="store_true", help="只保存请求计划与准备缺口，不发送请求或验证账户权限")
            p.add_argument("--connections-dir", default="data/.connections", help="独立本地连接配置目录；环境变量优先，Key不进入采样计划")
        if command == "minute-quality":
            p.add_argument("--plan", required=True, help="显式分钟口径、证据与日历计划；未知项不推断")
            p.add_argument("--samples", nargs="*", default=[], help="已有vendor-sample目录；可省略以查看准备缺口")
            p.add_argument("--output", required=True, help="新的离线分钟诊断报告，不写数据库或策略输入")
        if command == "minute-acceptance-plan":
            p.add_argument("--plan", required=True, help="显式交易日、采集时点和总预算；不读凭据、不发网")
            p.add_argument("--output-dir", required=True, help="不存在的新目录，保存四份未授权采样计划及零请求准备报告")
        if command == "compare-vendor-samples":
            p.add_argument("--left", required=True, help="已有vendor-sample目录")
            p.add_argument("--right", required=True, help="另一供应商的vendor-sample目录")
            p.add_argument("--output", required=True, help="不存在的新日线比较报告；分钟不作未验证对齐")
        if command in {"serve", "worker", "demo", "replay", "supervise", "provider-poc"}:
            p.add_argument("--config", required=command == "provider-poc", help="完整策略 JSON；默认只使用 fixture 配置")
        if command == "provider-poc":
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument("--input", help="独立JSONL样本，不写实时数据库")
            group.add_argument("--http", action="store_true", help="按计划时点访问已授权标准HTTPS网关")
            p.add_argument("--plan", required=True, help="完整的数据能力、授权和覆盖验收计划")
            p.add_argument("--output", required=True, help="不存在的新PoC报告")
        if command == "channel-poc":
            p.add_argument("--send-test", action="store_true", help="明确向当前环境配置的钉钉群发送一条测试消息；不自动重试")
            p.add_argument("--output", required=True, help="不存在的新连接测试报告")
        if command == "serve":
            p.add_argument("--port", type=int, default=8765)
            p.add_argument("--empty", action="store_true", help="不自动加载前两个模拟切片")
        if command in {"worker", "supervise"}:
            p.add_argument("--simulation-dispatch-plan", help="显式启用仅本地通知演练的完整调度计划，不访问真实渠道")
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument("--input", help="以 JSONL 录制数据逐切片扫描")
            group.add_argument("--http", action="store_true", help="轮询 STOCKRADAR_PROVIDER_URL 标准网关")
            p.add_argument("--interval", type=float, default=60)
            if command == "worker":
                p.add_argument("--once", action="store_true")
                p.add_argument("--saved-version", help="读取数据库中已保存的不可变策略版本；不能同时指定--config")
            else:
                p.add_argument("--plan", required=True, help="完整运行验收/重启计划JSON")
        if command == "study":
            p.add_argument("--input", required=True, help="带显式execution证据的JSONL行情")
            p.add_argument("--plan", required=True, help="四组配置、成本、规则和分段的完整研究计划")
            p.add_argument("--output", required=True, help="必须是不存在的新实验报告路径")
        if command == "export-study-fixture":
            p.add_argument("--output-dir", required=True, help="不存在的新合成研究目录")
            p.add_argument("--days", type=int, default=90)
        if command == "ops-report":
            p.add_argument("--plan", required=True)
            p.add_argument("--output", required=True)
        if command in {"dispatcher", "dispatch-report"}:
            p.add_argument("--plan", required=True, help="完整本地投递演练计划JSON")
            if command == "dispatcher":
                p.add_argument("--simulation", required=True, action="store_true", help="必须明确选择本地演练；真实渠道保持锁定")
                p.add_argument("--once", action="store_true", help="仅执行一个调度轮次，未到期队列保留")
            else:
                p.add_argument("--output", required=True, help="新的只读调度报告路径")
        if command == "archive-scans":
            p.add_argument("--strategy-version", required=True)
            p.add_argument("--before", required=True, help="UTC截止时间，起点前输入只读压缩归档")
            p.add_argument("--output", required=True)
        if command == "benchmark":
            p.add_argument("--symbols", type=int, nargs="+", default=[12, 120])
            p.add_argument("--iterations", type=int, default=2)
            p.add_argument("--concurrent-replays", type=int, default=2)
            p.add_argument("--output", required=True)
        if command == "replay":
            p.add_argument("--input", help="可省略，默认回放合成样例")
            p.add_argument("--output", default="data/replay-report.json")
        if command in {"export-fixture", "backup"}:
            p.add_argument("--output", required=True)
        if command == "export-fixture":
            p.add_argument("--fixture-version", type=int, choices=(1, 2), default=2, help="默认2含科创板；1保留历史样例")
        if command == "restore":
            p.add_argument("--input", required=True)
        if command in {"_replay-job", "_study-job"}:
            p.add_argument("--id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "minute-acceptance-plan":
            from .contracts import load_json
            from .minute_acceptance import write_acceptance_plan
            report = write_acceptance_plan(load_json(args.plan), args.output_dir)
            print("分钟验收准备：%s；四阶段合计%d个请求，实际0请求；计划未授权、不会自动执行" %
                  (report["status"], report["planned_requests"]))
            return
        if args.command in {"vendor-sample", "compare-vendor-samples", "minute-quality"}:
            from .contracts import load_json, write_new_json
            from .vendor_samples import collect_samples, compare_samples, prepare_samples
            if args.command == "vendor-sample":
                if args.dry_run:
                    report = prepare_samples(load_json(args.plan), credentials_dir=args.connections_dir)
                    root = Path(args.output_dir)
                    root.mkdir(parents=True, exist_ok=False, mode=0o700)
                    write_new_json(root / "report.json", report)
                    os.chmod(root / "report.json", 0o600)
                    print("供应商采样准备：%s；计划%d个请求，实际0请求；账户权限未验证" % (report["status"], report["planned_requests"]))
                else:
                    report = collect_samples(load_json(args.plan), args.output_dir, credentials_dir=args.connections_dir)
                    print("供应商原始样本：%s；请求%d，保存%d个响应；未接入策略" % (report["status"], report["sent_requests"], report["captured_responses"]))
            elif args.command == "minute-quality":
                if Path(args.output).exists():
                    raise ValueError("分钟诊断须使用不存在的新报告路径")
                from .minute_quality import minute_quality_report
                report = minute_quality_report(load_json(args.plan), args.samples)
                write_new_json(args.output, report)
                os.chmod(args.output, 0o600)
                print("离线分钟诊断：%s；观测%d条，缺口/原因%d项；未接入策略" % (report["status"], report["observation_count"], len(report["reason_codes"])))
            else:
                if Path(args.output).exists():
                    raise ValueError("比较报告须使用不存在的新路径")
                report = compare_samples(args.left, args.right)
                write_new_json(args.output, report)
                print("未复权日线比较：%s，共同样本%d；分钟/历史可见性仍待验证" % (report["status"], report["common_bars"]))
            return
        if args.command in {"provider-poc", "channel-poc"}:
            from .contracts import load_json, write_new_json
            if Path(args.output).exists():
                raise ValueError("PoC报告必须使用不存在的新路径；未执行网络请求")
            if args.command == "provider-poc":
                from .acceptance import provider_report, validate_provider_plan
                from .providers import HTTPJSONProvider, JSONLProvider
                plan = validate_provider_plan(load_json(args.plan))
                config = load_config(args.config)
                if args.http:
                    if plan["purpose"] != "experimental" or not plan["authorization"]["confirmed"] or not plan["sample_times"]:
                        raise ValueError("网关PoC须提供experimental用途、授权声明及显式样本时点")
                    provider = HTTPJSONProvider(os.environ.get("STOCKRADAR_PROVIDER_URL", ""), os.environ.get("STOCKRADAR_PROVIDER_TOKEN"))
                    batches = (provider.get_slice(at) for at in plan["sample_times"])
                else:
                    batches = JSONLProvider(args.input).iter_batches()
                report = provider_report(batches, config, plan, "https" if args.http else "jsonl")
            else:
                from .acceptance import channel_report
                from .service import Application
                report = channel_report(Application(args.db, seed=False), args.send_test)
            write_new_json(args.output, report)
            print("PoC报告已保存：%s；真实提醒仍未发布" % report["status"])
            return
        if args.command in {"study", "export-study-fixture", "benchmark"}:
            from .contracts import load_json, write_new_json
            if args.command == "study":
                from .research import run_study
                from .providers import JSONLProvider
                result = run_study(JSONLProvider(args.input).iter_batches(), load_json(args.plan))
                write_new_json(args.output, result)
                print("独立信号仿真研究已保存；不代表实际成交或真实发布通过")
            elif args.command == "export-study-fixture":
                from .study_fixture import make_study_fixture
                from .providers import record_batches
                batches, plan = make_study_fixture(args.days)
                root = Path(args.output_dir)
                root.mkdir(parents=True, exist_ok=False)
                write_new_json(root / "study-plan.json", plan)
                record_batches(root / "synthetic.jsonl", batches)
                print("已导出明确标记的合成研究样例（%d切片），不是正式策略或真实交易日历" % len(batches))
            else:
                from .benchmark import run_benchmark
                write_new_json(args.output, run_benchmark(args.symbols, args.iterations, args.concurrent_replays))
                print("本机合成负载报告已保存；真实全市场/平台时延仍未验收")
            return
        if args.command == "export-fixture":
            from .fixtures import fixture_batches
            from .providers import record_batches
            count = record_batches(args.output, fixture_batches(args.fixture_version))
            print("已导出 %d 个模拟切片：%s" % (count, args.output))
            return
        if args.command == "restore":
            target, source = Path(args.db).resolve(), Path(args.input).resolve()
            if target.exists() or not source.is_file():
                raise ValueError("恢复源必须存在，目标必须是不存在的新数据库路径；请停止相关服务后执行")
            target.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True) as src:
                if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("备份源完整性检查失败")
                if not src.execute("SELECT 1 FROM sqlite_master WHERE name='scans'").fetchone():
                    raise ValueError("备份源不是观势数据库")
                with sqlite3.connect(str(target)) as dest:
                    src.backup(dest)
            os.chmod(target, 0o600)
            print("已恢复到：" + str(target))
            return
        if args.command in {"ops-report", "archive-scans", "dispatcher", "dispatch-report"} and not Path(args.db).is_file():
            raise ValueError("运行证据/归档源数据库必须已存在")
        store = Store(args.db)
        if args.command in {"dispatcher", "dispatch-report"}:
            from .contracts import load_json, write_new_json
            from .dispatcher import SimulationDispatcher, dispatch_report
            plan = load_json(args.plan)
            if args.command == "dispatch-report":
                write_new_json(args.output, dispatch_report(store, plan))
                print("本地演练投递报告已保存；不是钉钉平台回执或发布证明")
            else:
                with SimulationDispatcher(store, plan, autostart=not args.once) as dispatcher:
                    print("本地投递演练已启动，不读取钉钉凭据或访问网络", flush=True)
                    if args.once:
                        dispatcher.tick()
                    else:
                        dispatcher.wait()
            return
        if args.command == "ops-report":
            from .contracts import load_json, write_new_json
            from .operations import operations_report
            write_new_json(args.output, operations_report(store, load_json(args.plan)))
            print("运行证据报告已保存；真实发布入口仍锁定")
            return
        if args.command == "archive-scans":
            from .maintenance import archive_scans
            result = archive_scans(store, args.strategy_version, args.before, args.output)
            print("已只读压缩%d个原始输入；源数据库未删除或裁剪" % result["row_count"])
            return
        if args.command == "backup":
            print("已备份并通过完整性检查：" + store.backup(args.output))
            return
        if args.command == "_replay-job":
            replay_job(store, args.id)
            return
        if args.command == "_study-job":
            from .study_jobs import run_job
            run_job(store, args.id)
            return
        if args.command == "worker" and args.saved_version:
            if args.config:
                raise ValueError("--saved-version不能与--config同时使用")
            config = store.version(args.saved_version)
        elif args.config:
            config = load_config(args.config)
        elif args.command == "replay":
            config = load_config()
        else:
            config = store.running_config() or load_config()
        if args.command == "replay":
            from .fixtures import fixture_batches
            from .providers import JSONLProvider
            from .replay import run_replay
            batches = list(JSONLProvider(args.input).iter_batches()) if args.input else fixture_batches(config.get("schema_version", 1))
            result = run_replay(batches, config)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print("已完成功能回放：%s（%d个切片；实际收益未验证）" % (output, result["batch_count"]))
            return
        from .service import Application, get_token
        app = Application(args.db, config, seed=args.command == "serve" and not args.empty)
        if args.command == "serve":
            from .server import serve
            token = get_token(args.db)
            print("观势 v%s · %s\n访问地址：http://127.0.0.1:%d\n访问令牌：%s\n按 Ctrl+C 停止服务。" % (__version__, config["mode"], args.port, token), flush=True)
            serve(app, token, args.port)
        elif args.command == "demo":
            from .fixtures import fixture_batches
            for batch in fixture_batches(config.get("schema_version", 1)):
                result = app.scan(batch)
                print("%s  market=%s  signals=%d  events=%d%s" % (batch["as_of"], result["market"]["status"], len(result["signals"]), len(result["events"]), "（已处理）" if result.get("duplicate") else ""))
        elif args.command == "supervise":
            from .contracts import load_json
            from .worker import supervise_worker
            result = supervise_worker(store, config, load_json(args.plan), args.input, args.http, args.interval,
                                      simulation_dispatch_plan=args.simulation_dispatch_plan)
            print("守护结束：%s，重启%d次" % (result["status"], result["restarts"]))
        else:
            from .worker import run_worker
            from .contracts import load_json
            dispatch_plan = load_json(args.simulation_dispatch_plan) if args.simulation_dispatch_plan else None
            run_worker(app, args.input, args.http, args.interval, args.once, dispatch_plan=dispatch_plan)
    except KeyboardInterrupt:
        return
    except (ValueError, OSError, KeyError) as exc:
        print("错误：" + str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
