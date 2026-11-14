"""Strict, immutable-by-value strategy configuration (all thresholds are explicit)."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path


class ConfigError(ValueError):
    code = "CONFIG_INCOMPLETE"


CONFIG_PATH = Path(__file__).resolve().parent / "fixture.json"
LEGACY_CONFIG_PATH = Path(__file__).resolve().parent / "fixture-v1.json"
MARKET_PAIRS = (("SSE", "MAIN"), ("SZSE", "MAIN"), ("SZSE", "CHINEXT"), ("SSE", "STAR"))


def config_hash(config):
    return sha256(json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_config(path=None):
    with open(path or CONFIG_PATH, encoding="utf-8") as stream:
        return validate_config(json.load(stream))


def _shape(value, template, path="config"):
    if isinstance(template, dict):
        if not isinstance(value, dict):
            raise ConfigError(path + " 必须是对象")
        missing, unknown = set(template) - set(value), set(value) - set(template)
        if missing or unknown:
            raise ConfigError("%s 缺少参数 %s；未知参数 %s" % (path, sorted(missing), sorted(unknown)))
        for key in template:
            _shape(value[key], template[key], path + "." + key)
    elif isinstance(template, list):
        if not isinstance(value, list) or not value:
            raise ConfigError(path + " 必须是非空数组")
        for item in value:
            _shape(item, template[0], path + "[]")
    elif isinstance(template, bool):
        if type(value) is not bool:
            raise ConfigError(path + " 必须是布尔值")
    elif isinstance(template, (float, int)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ConfigError(path + " 必须是有限数值")
        if isinstance(template, int) and not isinstance(value, int):
            raise ConfigError(path + " 必须是整数")
    elif not isinstance(value, str) or not value.strip():
        raise ConfigError(path + " 必须是非空字符串")


def validate_config(config):
    if not isinstance(config, dict):
        raise ConfigError("config 必须是对象")
    schema = config.get("schema_version", 1)
    if type(schema) is not int or schema not in (1, 2) or (schema == 1 and "schema_version" in config):
        raise ConfigError("配置schema须为2；历史v1格式不含schema_version")
    with open(CONFIG_PATH if schema == 2 else LEGACY_CONFIG_PATH, encoding="utf-8") as stream:
        template = json.load(stream)
    _shape(config, template)
    if config["mode"] not in {"fixture", "replay", "shadow", "live_alert"}:
        raise ConfigError("mode 必须是 fixture/replay/shadow/live_alert")
    if config["purpose"] not in {"fixture", "experimental"}:
        raise ConfigError("purpose 必须是 fixture 或 experimental")
    if config["purpose"] == "fixture" and config["mode"] in {"shadow", "live_alert"}:
        raise ConfigError("模拟参数不得启用真实行情模式")
    if config["research"]["alert_stage"] not in {"early", "confirmed"}:
        raise ConfigError("research.alert_stage 必须是 early/confirmed")
    if config["mode"] in {"shadow", "live_alert"} and not config["research"]["sector_filter"]:
        raise ConfigError("跳过板块过滤只允许离线研究")
    if config["strategy_id"] != "hotspot_breakout_v1":
        raise ConfigError("未知策略实现")
    if config["status"] not in {"draft", "frozen", "retired"}:
        raise ConfigError("未知策略状态")
    boards = config["preferences"]["boards"]
    if len(set(boards)) != len(boards) or not set(boards).issubset({"MAIN", "CHINEXT", "STAR"} if schema == 2 else {"MAIN", "CHINEXT"}):
        raise ConfigError("股票板块重复或超出配置schema范围；科创板须使用schema_version=2及显式STAR参数")
    if not 0 < config["preferences"]["max_loss_fraction"] <= 0.10:
        raise ConfigError("单笔结构风险上限必须在 (0, 0.10] 内")
    run = config["runtime"]
    if run["slice_seconds"] != 60 or run["stale_after_seconds"] < run["slice_seconds"]:
        raise ConfigError("第一版使用60秒完成切片，过期阈值不得小于切片")
    if not 0 <= run["group_window_seconds"] < 60 or run["collection_timeout_seconds"] <= 0:
        raise ConfigError("采集超时和合并窗口无效")
    for field in ("universe_min_coverage", "sector_min_coverage", "historical_min_coverage"):
        if not 0 < run[field] <= 1:
            raise ConfigError(field + " 必须在 (0,1] 内")
    market, sector, life = config["market"], config["sector"], config["lifecycle"]
    if not 1 <= market["short_window"] < market["long_window"] or market["volatility_window"] < 2:
        raise ConfigError("市场均线/波动窗口无效")
    if market["volatility_method"] != "population_std_daily_returns":
        raise ConfigError("第一版波动率使用日收益总体标准差")
    if not 0 <= market["down_breadth"] < market["up_breadth"] <= 1:
        raise ConfigError("市场广度阈值无效")
    for obj, keys in ((market, ("state_slices",)), (sector, ("rs_window_minutes", "rvol_days", "min_members", "min_breakouts", "candidate_slices", "confirm_slices", "fade_slices", "reset_slices", "extension_days", "concentration_top_k")), (life, ("entry_ttl_seconds", "candidate_timeout_seconds", "reset_slices", "stock_confirm_slices"))):
        if any(obj[k] < 1 for k in keys):
            raise ConfigError("窗口、最小样本和持续次数必须为正整数")
    if life["daily_new_limit"] < 0:
        raise ConfigError("每日额度不得为负，0表示关闭额度")
    if not 0 <= sector["exit_breadth"] < sector["min_breadth"] <= sector["confirm_breadth"] <= 1:
        raise ConfigError("板块退出、候选、确认广度必须有序")
    if sector["confirm_rs"] < sector["min_rs"] or sector["confirm_rvol"] < sector["min_rvol"]:
        raise ConfigError("确认阈值不得低于候选阈值")
    if not 0 < sector["max_concentration"] <= 1 or not 0 < sector["jaccard_threshold"] <= 1:
        raise ConfigError("集中度与聚合阈值无效")
    for board, stock in config["stock"].items():
        if stock["lookback_days"] < 2 or stock["atr_days"] < 1 or stock["min_listing_days"] < 0:
            raise ConfigError(board + " 历史窗口无效")
        if any(stock[k] < 0 for k in ("max_range_width", "breakout_buffer_atr", "invalidation_buffer_atr", "min_rvol", "min_amount_cny", "min_daily_amount_cny")):
            raise ConfigError(board + " 价格/量能门槛不得为负")
        if stock["max_distance_atr"] <= stock["breakout_buffer_atr"]:
            raise ConfigError(board + " 可参与上界必须超过突破缓冲")
    scoring = config["scoring"]
    if not 1 <= scoring["alert_threshold"] <= 100:
        raise ConfigError("通知分数门槛必须在1至100之间")
    if abs(sum(x["weight"] for x in scoring["groups"].values()) - 1) > 1e-9:
        raise ConfigError("评分分组权重之和必须为1")
    allowed = {"market_breadth", "sector_rs", "sector_delta_rs", "sector_breadth", "sector_rvol", "stock_rvol", "stock_relative", "entry_distance", "risk_fraction"}
    for group in scoring["groups"].values():
        if group["weight"] < 0 or abs(sum(f["weight"] for f in group["features"]) - 1) > 1e-9:
            raise ConfigError("组内权重之和必须为1，权重不得为负")
        for feature in group["features"]:
            if feature["name"] not in allowed or feature["weight"] < 0 or feature["high"] <= feature["low"]:
                raise ConfigError("评分特征或归一化锚点无效")
    return deepcopy(config)
