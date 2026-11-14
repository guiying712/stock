"""Explicit study plans, independent baselines and purged time partitions."""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
import random
from statistics import mean

from .config import validate_config
from .contracts import fields, integer, numeric, string, utc
from .engine import evaluate
from .execution import Tape, simulate, summarize, validate_rules
from .replay import source_hash
from .store import digest

PROFILE_IDS = ("stock_only", "sector_filter", "early", "confirmed")
PLAN_KEYS = ("schema_version", "id", "purpose", "capital_per_signal", "delivery_delay_seconds", "reaction_delays_minutes", "holding_windows_days", "exit_modes", "price_model", "dividend_accounting", "max_loss_fraction", "benchmark_id", "rules", "profiles", "splits", "bootstrap_samples", "min_clusters", "seed")


def validate_study_plan(plan):
    fields(plan, PLAN_KEYS, "研究计划")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or plan["purpose"] not in ("fixture", "experimental"):
        raise ValueError("研究计划版本或用途无效")
    string(plan["id"], "研究计划ID")
    string(plan["benchmark_id"], "基准ID")
    numeric(plan["capital_per_signal"], "独立样本预算", low=Decimal("0.01"))
    numeric(plan["max_loss_fraction"], "风险边界", low=Decimal("0.000001"), high=Decimal("0.10"))
    integer(plan["delivery_delay_seconds"], 0, 3600, "投递延迟")
    integer(plan["bootstrap_samples"], 0, 10000, "聚类自举次数")
    integer(plan["min_clusters"], 2, 10000, "最少独立簇数")
    integer(plan["seed"], 0, 2**32 - 1, "随机种子")
    if plan["price_model"] != "next_completed_close" or plan["dividend_accounting"] != "net_receivable_on_ex_date":
        raise ValueError("未支持的价格或分红记账假设")
    for name, high in (("reaction_delays_minutes", 60), ("holding_windows_days", 250)):
        values = plan[name]
        if not isinstance(values, list) or not values:
            raise ValueError(name + "须为无重复的非空数组")
        for value in values:
            integer(value, 0 if name == "reaction_delays_minutes" else 1, high, name)
        if len(values) != len(set(values)):
            raise ValueError(name + "须为无重复的非空数组")
    if not isinstance(plan["exit_modes"], list) or len(plan["exit_modes"]) != 2 or any(not isinstance(x, str) for x in plan["exit_modes"]) or sorted(plan["exit_modes"]) != ["fixed", "risk"]:
        raise ValueError("须分别报告fixed及risk两种退出模型")
    validate_rules(plan["rules"])
    splits = plan["splits"]
    if not isinstance(splits, list) or any(not isinstance(s, dict) for s in splits) or [s.get("name") for s in splits] != ["train", "validation", "test"]:
        raise ValueError("须提供依时间排序的train/validation/test分段")
    end = None
    for split in splits:
        fields(split, ("name", "start", "end"), "时间分段")
        a, b = utc(split["start"]), utc(split["end"])
        if a >= b or (end is not None and a < end):
            raise ValueError("研究分段无效或重叠")
        end = b
    profiles = plan["profiles"]
    if not isinstance(profiles, list) or any(not isinstance(p, dict) for p in profiles) or [p.get("id") for p in profiles] != list(PROFILE_IDS):
        raise ValueError("须显式提供四组完整策略配置")
    configs = {}
    for profile in profiles:
        fields(profile, ("id", "config"), "对照组")
        config = validate_config(profile["config"])
        if config["mode"] != "replay" or config["purpose"] != "experimental":
            raise ValueError("研究对照配置须为experimental replay")
        if config["market"]["benchmark"] != plan["benchmark_id"]:
            raise ValueError("对照组基准必须一致")
        configs[profile["id"]] = config
    for name, cfg in configs.items():
        if cfg["research"]["sector_filter"] != (name != "stock_only"):
            raise ValueError("对照组板块资格门槛不符合定义")
        if cfg["research"]["alert_stage"] != ("confirmed" if name == "confirmed" else "early"):
            raise ValueError("对照组提醒阶段不符合定义")
        if (cfg["scoring"]["groups"]["sector"]["weight"] == 0) != (name in {"stock_only", "sector_filter"}):
            raise ValueError("前两组须关闭板块评分，后两组须保留板块评分")
    base, confirmed = deepcopy(configs["early"]), deepcopy(configs["confirmed"])
    base.pop("id"); confirmed.pop("id")
    confirmed["research"]["alert_stage"] = "early"
    if base != confirmed:
        raise ValueError("early与confirmed仅可改变提醒阶段及配置ID")
    a, b = deepcopy(configs["stock_only"]), deepcopy(configs["sector_filter"])
    a.pop("id"); b.pop("id")
    a["research"]["sector_filter"] = True
    if a != b:
        raise ValueError("stock_only与sector_filter仅可改变板块资格门槛及ID")
    filtered = deepcopy(configs["sector_filter"])
    filtered.pop("id")
    groups = filtered["scoring"]["groups"]
    early_groups = base["scoring"]["groups"]
    if Decimal(str(groups["stock"]["weight"])) != Decimal(str(early_groups["stock"]["weight"])) + Decimal(str(early_groups["sector"]["weight"])):
        raise ValueError("关闭板块评分时须将其权重转给个股组")
    groups["stock"]["weight"] = early_groups["stock"]["weight"]
    groups["sector"]["weight"] = early_groups["sector"]["weight"]
    if filtered != base:
        raise ValueError("四组对照须保持其余参数一致")
    return deepcopy(plan)


def _cluster_interval(samples, plan):
    grouped = defaultdict(list)
    for sample in samples:
        if sample["status"] == "closed":
            grouped[tuple(sample["cluster"])].append(sample["net_return"])
    clusters = [mean(values) for _, values in sorted(grouped.items())]
    result = {"cluster_unit": "first_trading_date_and_hotspot", "cluster_count": len(clusters),
              "cluster_weighted_mean": mean(clusters) if clusters else None,
              "interval_95": None, "seed": plan["seed"], "resamples": plan["bootstrap_samples"]}
    if len(clusters) < plan["min_clusters"] or not plan["bootstrap_samples"]:
        result["reason"] = "INSUFFICIENT_CLUSTERS_OR_BOOTSTRAP_DISABLED"
        return result
    rng = random.Random(plan["seed"])
    values = sorted(mean(rng.choice(clusters) for _ in clusters) for _ in range(plan["bootstrap_samples"]))
    result["interval_95"] = [values[int((len(values) - 1) * fraction)] for fraction in (0.025, 0.975)]
    return result


def run_study(batches, plan):
    plan = validate_study_plan(plan)
    batches = list(batches)
    if not batches or any(not isinstance(b, dict) or type(b.get("simulated")) is not bool for b in batches):
        raise ValueError("研究数据必须非空并显式声明模拟状态")
    if len({b["simulated"] for b in batches}) != 1:
        raise ValueError("模拟与真实数据不能混合研究")
    simulated = batches[0]["simulated"]
    if simulated != (plan["purpose"] == "fixture"):
        raise ValueError("合成研究计划不得默认用于真实数据，须另建experimental计划")
    seen, unique = {}, []
    for batch in batches:
        key, sha = batch["snapshot_id"], digest(batch)
        if key in seen:
            if seen[key] != sha:
                raise ValueError("同一快照内容冲突")
            continue
        seen[key] = sha
        unique.append(batch)
    batches = unique
    tape = Tape(batches)
    profiles = []
    for profile in plan["profiles"]:
        state, first, history = None, {}, defaultdict(list)
        for batch in batches:
            result = evaluate(batch, profile["config"], state)
            state = result["state"]
            for event in result["events"]:
                history[event["signal_id"]].append(event)
                if event["to_status"] in {"PREALERT", "CONFIRMED"}:
                    first.setdefault(event["signal_id"], event)
        samples, signal_refs, unassigned = [], {}, 0
        for signal_id, alert in first.items():
            signal = alert["snapshot"]
            split = next((s for s in plan["splits"] if utc(s["start"]) <= utc(alert["at"]) < utc(s["end"])), None)
            if split is None:
                unassigned += 1
                continue
            signal_refs[signal_id] = {
                "code": signal.get("code"), "name": signal.get("name"), "trigger_time": signal.get("trigger_time"),
                "first_alert_at": alert["at"], "snapshot_id": signal["evidence"].get("snapshot_id"),
            }
            for delay in plan["reaction_delays_minutes"]:
                for horizon in plan["holding_windows_days"]:
                    for mode in plan["exit_modes"]:
                        samples.append(simulate(signal, alert, history[signal_id], tape, plan, delay, horizon, mode, split))
        summaries = []
        for split in plan["splits"]:
            for delay in plan["reaction_delays_minutes"]:
                for horizon in plan["holding_windows_days"]:
                    for mode in plan["exit_modes"]:
                        values = [s for s in samples if (s["split"], s["delay_minutes"], s["holding_days"], s["exit_mode"]) == (split["name"], delay, horizon, mode)]
                        summaries.append({"split": split["name"], "delay_minutes": delay, "holding_days": horizon,
                                          "exit_mode": mode, **summarize(values), "clusters": _cluster_interval(values, plan)})
        profiles.append({"id": profile["id"], "config_hash": digest(profile["config"]), "alert_count": len(first),
                         "outside_splits": unassigned, "samples": samples, "signal_refs": signal_refs, "summaries": summaries,
                         "sample_hash": digest(samples)})
    reasons = ["REAL_PATH_AND_SHADOW_RELEASE_EVIDENCE_REQUIRED"]
    if simulated:
        reasons.append("SYNTHETIC_DATA_ONLY")
    if not all(rule["verified"] for rule in plan["rules"]):
        reasons.append("RULES_AND_COSTS_NOT_VERIFIED")
    if not all(any(s["split"] == "test" and s["closed_count"] and s["clusters"]["interval_95"] is not None for s in p["summaries"]) for p in profiles):
        reasons.append("HOLDOUT_EVIDENCE_INSUFFICIENT")
    report = {"schema_version": 1, "kind": "assumption_based_independent_signal_study", "simulated": simulated,
              "plan": plan, "plan_hash": digest(plan), "data_hash": digest(batches), "code_hash": source_hash(),
              "batch_count": len(batches), "observation_gaps": dict(tape.gaps), "profiles": profiles,
              "parameter_freeze": {"eligible": False, "reasons": reasons},
              "limitations": ["仿真成交不是实际成交，不构建组合净值，不代表盈利或胜率",
                              "分钟成交模型为下一完成分钟收盘的全额成交假设，依赖显式买卖资格及可成交量",
                              "缺执行、成本、公司行为或窗口数据保留pending，跨分段标签purged",
                              "分红按显式每旧股净应收在除权日计入，不模拟实际到账或个人税务账本",
                              "本模块不选择参数、不改写历史版本、不解除live_alert锁定"]}
    report["output_hash"] = digest(report)
    return report
