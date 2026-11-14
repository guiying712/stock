"""DingTalk transport. Accepted means platform accepted, never read or traded."""
import base64
import hashlib
import hmac
import json
import math
import re
import socket
import time
from datetime import datetime
from urllib import error, parse, request
from zoneinfo import ZoneInfo
from threading import Lock

from . import __version__

MAX_MESSAGE_BYTES = 18000


class SimulationNotifier:
    """Local receipt only. No environment, URL, socket or unbounded message log."""
    def __init__(self):
        self.sent_count = 0
        self._lock = Lock()

    def send(self, payload, idempotency_key):
        from .store import digest
        if not payload.get("markdown", {}).get("title", "").startswith("【本地投递演练】"):
            raise ValueError("本地模拟器只接受明确标记的演练正文")
        with self._lock:
            self.sent_count += 1
        return {"status": "accepted", "retryable": False, "response_code": None, "error": None,
                "receipt": {"simulation": True, "transport": "local", "message_hash": digest(payload),
                            "idempotency_key": idempotency_key}}


class NotificationConfigError(ValueError):
    code = "CHANNEL_NOT_CONFIGURED"


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _result(status, response_code=None, receipt=None, error_message=None, retryable=False):
    return {"status": status, "response_code": response_code, "receipt": receipt,
            "error": error_message, "retryable": retryable}


class DingTalkNotifier:
    def __init__(self, webhook_url, secret=None, timeout=10, opener=None):
        try:
            if not isinstance(webhook_url, str) or any(ord(char) <= 32 for char in webhook_url):
                raise ValueError()
            parsed = parse.urlsplit(webhook_url)
            params = parse.parse_qs(parsed.query, strict_parsing=True)
            if (parsed.scheme != "https" or parsed.hostname != "oapi.dingtalk.com" or
                    parsed.port not in (None, 443) or parsed.path != "/robot/send" or
                    parsed.username or parsed.password or parsed.fragment or
                    set(params) != {"access_token"} or len(params["access_token"]) != 1 or
                    not re.fullmatch(r"[A-Za-z0-9_-]+", params["access_token"][0])):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise NotificationConfigError("钉钉 Webhook 格式无效；需要官方 HTTPS 群机器人地址") from None
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise NotificationConfigError("通知超时必须为有限正数")
        if secret is not None and (not isinstance(secret, str) or not secret.strip()):
            raise NotificationConfigError("加签密钥不能为空白")
        self._webhook_url, self._secret = webhook_url, secret
        self.timeout = timeout
        self._opener = opener or request.build_opener(_NoRedirect())

    def _signed_url(self):
        if not self._secret:
            return self._webhook_url
        timestamp = str(int(time.time() * 1000))
        signed = hmac.new(self._secret.encode("utf-8"),
                          (timestamp + "\n" + self._secret).encode("utf-8"), hashlib.sha256).digest()
        return self._webhook_url + "&" + parse.urlencode({"timestamp": timestamp,
                                                         "sign": base64.b64encode(signed).decode("ascii")})

    def send(self, payload, idempotency_key):
        # DingTalk custom webhooks do not expose an exactly-once idempotency API.
        # This key identifies the persisted application outbox entry only.
        if not isinstance(idempotency_key, str) or not idempotency_key:
            return _result("failed", error_message="缺少本地投递幂等键")
        try:
            if not isinstance(payload, dict) or payload.get("msgtype") != "markdown":
                raise ValueError()
            markdown = payload["markdown"]
            if not isinstance(markdown.get("title"), str) or not isinstance(markdown.get("text"), str):
                raise ValueError()
            raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(raw) > MAX_MESSAGE_BYTES:
                return _result("failed", error_message="通知正文过长；请在发件箱中拆分消息")
        except (TypeError, ValueError, KeyError, AttributeError):
            return _result("failed", error_message="通知载荷格式不正确")
        req = request.Request(self._signed_url(), data=raw, method="POST",
                              headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "StockRadar/" + __version__})
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                http_status = getattr(response, "status", 200)
                response_bytes = response.read(65537)
                if len(response_bytes) > 65536:
                    return _result("unknown", http_status, error_message="平台响应过长，投递结果无法确认")
        except error.HTTPError as exc:
            if exc.code == 429:
                return _result("failed", exc.code, error_message="平台限流；按发件箱退避规则重试", retryable=True)
            if 400 <= exc.code < 500:
                return _result("failed", exc.code, error_message="平台拒绝请求（HTTP %d）" % exc.code)
            return _result("unknown", exc.code, error_message="平台未返回可确认的投递结果；禁止自动重发")
        except (socket.timeout, TimeoutError, error.URLError, OSError):
            # A timeout or reset may happen after the request reached the server.
            # Never leak exception text: urllib errors can contain a credential URL.
            return _result("unknown", error_message="网络中断或超时，平台可能已受理；禁止自动重发")
        try:
            body = json.loads(response_bytes)
        except (ValueError, UnicodeError):
            return _result("unknown", http_status, error_message="平台响应无法解析；禁止自动重发")
        if not isinstance(body, dict) or type(body.get("errcode")) is not int:
            return _result("unknown", http_status, error_message="平台响应缺少有效结果码；禁止自动重发")
        code = body["errcode"]
        if code == 0:
            return _result("accepted", http_status, receipt={"errcode": 0, "accepted": True})
        # Preserve a numeric receipt, not untrusted platform text which may echo
        # webhook credentials. Exact errors stay distinguishable for diagnosis.
        throttled = code in (130101, 90018)
        return _result("failed", http_status, receipt={"errcode": code},
                       error_message="钉钉拒绝通知（错误码 %d）" % code, retryable=throttled)


def _text(value):
    if value is None:
        return "未知"
    # Treat all provider-sourced strings as plain content, not markdown links.
    return re.sub(r"([\\`*_{}\[\]()#+.!<>])", r"\\\1", str(value).replace("\r", " ").replace("\n", " "))


def _time(value):
    if not value:
        return "未知"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return "未知（无时区）"
        return parsed.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S") + " 北京时间"
    except (ValueError, TypeError):
        return "未知"


def build_message(signal, event, test=False, base_url=None):
    signal, event = signal or {}, event or {}
    evidence = signal.get("evidence") or {}
    simulated = (evidence.get("simulated", True) if isinstance(evidence, dict) else True)
    prefix = "【测试通知】" if test else "【模拟数据】" if simulated else "【热点提醒】"
    status = {"DETECTED": "内部观察", "PREALERT": "启动预警", "CONFIRMED": "增强确认",
              "INVALIDATED": "策略失效", "EXPIRED": "机会过期"}.get(signal.get("status"), "连接测试")
    actionability = {"eligible": "在规则参与范围内", "extended": "当前已偏离参与范围",
                     "paused": "更新暂停或条件不足", "expired": "参与机会已过期"}.get(signal.get("actionability"), "测试消息")
    title = prefix + status
    lines = ["### " + title,
             "**%s · %s**" % (_text(signal.get("code", "TEST")), _text(signal.get("name", "热点雷达"))),
             "- 关联热点：" + _text(signal.get("sector_name")),
             "- 规则分：%s / 100（规则匹配度，非胜率）" % _text(signal.get("score")),
             "- 当前状态：" + actionability,
             "- 触发价：%s；%s" % (_text(signal.get("trigger_price")), _time(signal.get("trigger_time"))),
             "- 最新价：%s；%s" % (_text(signal.get("latest_price")), _time(signal.get("latest_time"))),
             "- 突破参考：%s；结构失效位：%s" % (_text(signal.get("breakout_price")), _text(signal.get("invalidation_price"))),
             "- 参与范围：%s — %s" % (_text(signal.get("entry_low")), _text(signal.get("entry_high"))),
             "- 版本：" + _text(signal.get("strategy_version", "test")),
             "- 信号 ID：" + _text(signal.get("id", "connection-test")),
             "- 更新原因：" + _text(" / ".join(event.get("reason_codes") or signal.get("reason_codes") or ["连接测试"])),
             "- 数据来源：" + _text(evidence.get("source") if isinstance(evidence, dict) else None)]
    parts = signal.get("score_parts") or {}
    if isinstance(parts, dict) and parts:
        summary = []
        for key, part in parts.items():
            if isinstance(part, dict):
                summary.append("%s %s分" % (_text(part.get("label", key)), _text(part.get("points"))))
        if summary:
            lines.append("- 分项贡献：" + " / ".join(summary) + "（总分另含基础1分）")
    related = signal.get("related_sectors") or []
    if isinstance(related, list) and related:
        names = [item.get("name", item.get("id")) if isinstance(item, dict) else item for item in related]
        lines.append("- 其他关联：" + " / ".join(_text(name) for name in names[:10]))
    if signal.get("expires_at"):
        lines.append("- 入场机会有效至：" + _time(signal["expires_at"]))
    if base_url and signal.get("id"):
        parsed = parse.urlsplit(base_url)
        if (parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or
                parsed.password or parsed.query or parsed.fragment):
            raise NotificationConfigError("详情页地址不得包含凭据、查询参数或片段")
        link = base_url.rstrip("/") + "/#signals/" + parse.quote(str(signal["id"]), safe="")
        lines.append("[查看信号详情（需登录）](%s)" % link)
    lines.append("平台受理不表示用户已读或成交。软件仅提醒，不自动交易。")
    return {"msgtype": "markdown", "markdown": {"title": title, "text": "\n\n".join(lines)},
            "at": {"isAtAll": False}}


def build_group_message(messages):
    """Combine already-rendered opportunity messages without dropping evidence."""
    if not messages:
        raise NotificationConfigError("聚合通知不能为空")
    if len(messages) == 1:
        return messages[0]
    prefix = "【模拟数据】" if any(m["markdown"]["title"].startswith("【模拟数据】") for m in messages) else "【热点提醒】"
    title = prefix + "同热点新机会 · %d条" % len(messages)
    return {"msgtype": "markdown", "markdown": {
                "title": title,
                "text": "### " + title + "\n\n" + "\n\n---\n\n".join(m["markdown"]["text"] for m in messages)},
            "at": {"isAtAll": False}}
