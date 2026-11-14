"""Local connection metadata and write-only, private token files; no strategy access."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import tempfile
import threading
from urllib import error, parse, request
import uuid

from .contracts import integer, utc
from .providers import _NoRedirect
from .store import dumps, now


MARKETS = {
    "fuyao": {"name": "同花顺 Fuyao", "base_url": "https://fuyao.aicubes.cn", "env": "FUYAO_API_KEY",
              "scope": "日线、当前报价与板块关系；分钟策略尚不可用"},
    "tickflow": {"name": "TickFlow", "base_url": "https://api.tickflow.org", "env": "TICKFLOW_API_KEY",
                 "scope": "原始研究采样；分钟权限与单位另验"},
    "tushare": {"name": "Tushare", "base_url": "https://api.tushare.pro", "env": "TUSHARE_TOKEN",
                "scope": "原始研究采样；历史与实时分钟权限另验"},
}
MODEL_ENV = "STOCKRADAR_LLM_API_KEY"
MAX_RESPONSE = 1024 * 1024


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[!-~]{1,4096}", value):
        raise ValueError("Key格式无效，请检查空格、换行及长度")
    return value


def _text(value, maximum, label, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()) or any(ord(c) < 32 for c in value):
        raise ValueError(label + "格式无效")
    return value.strip()


def _contains(value, secret):
    if not secret:
        return False
    if isinstance(value, dict):
        return any(_contains(k, secret) or _contains(v, secret) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains(v, secret) for v in value)
    return isinstance(value, str) and any(secret in v for v in (value, parse.unquote(value), parse.unquote_plus(value)))


def _base_url(value):
    value = _text(value, 500, "API地址", empty=True)
    if not value:
        return ""
    try:
        u = parse.urlsplit(value)
        port = u.port
    except ValueError:
        raise ValueError("API地址格式无效") from None
    if (not u.hostname or u.username is not None or u.password is not None or u.query or u.fragment
            or u.scheme not in {"https", "http"} or (port is not None and not 1 <= port <= 65535)
            or any(c in value for c in ("\\", " ", "%", "?", "#"))):
        raise ValueError("API地址需为不含凭据、查询参数或片段的完整地址")
    if u.scheme == "http" and u.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("远程API需使用HTTPS；本机兼容服务可使用HTTP")
    return value.rstrip("/")


class ConnectionSettings:
    def __init__(self, directory, environ=None):
        self.directory = Path(directory)
        self.environ = os.environ if environ is None else environ
        self.lock = threading.RLock()
        self.checks = {}

    def _directory(self, create=False):
        if self.directory.is_symlink():
            raise ValueError("连接配置目录不能为符号链接")
        if create:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.directory, 0o700)
        if self.directory.exists() and not self.directory.is_dir():
            raise ValueError("连接配置目录无效")

    def _read(self, name, maximum):
        self._directory()
        path = self.directory / name
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        except OSError:
            raise ValueError("连接配置或令牌文件不可读取") from None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("连接配置和令牌文件需仅当前用户可读写")
            raw = stream.read(maximum + 1)
            if len(raw) > maximum:
                raise ValueError("连接配置或令牌文件过大")
            return raw

    def _write(self, name, raw):
        self._directory(create=True)
        fd, filename = tempfile.mkstemp(prefix=".write-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, self.directory / name)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def _profile(self, identifier):
        if identifier not in MARKETS and identifier != "model":
            raise ValueError("未知连接配置")
        raw = self._read(identifier + ".json", 16384)
        if raw is None:
            return {"schema_version": 1, "id": identifier, "revision": "new", "updated_at": None, "credential_id": None,
                    **({"base_url": "", "model": "", "timeout_seconds": 15} if identifier == "model" else
                       {"authorization": {"confirmed": False, "reference": None}})}
        try:
            def unique(pairs):
                result = {}
                for k, v in pairs:
                    if k in result:
                        raise ValueError()
                    result[k] = v
                return result
            value = json.loads(raw, object_pairs_hook=unique)
            expected = {"schema_version", "id", "revision", "updated_at", "credential_id"} | (
                {"base_url", "model", "timeout_seconds"} if identifier == "model" else {"authorization"})
            if (set(value) != expected or type(value["schema_version"]) is not int or value["schema_version"] != 1
                    or value["id"] != identifier or not re.fullmatch(r"[0-9a-f]{32}", value["revision"])
                    or (value["credential_id"] is not None and not re.fullmatch(r"[0-9a-f]{32}", value["credential_id"]))):
                raise ValueError()
            utc(value["updated_at"])
            if identifier == "model":
                if _base_url(value["base_url"]) != value["base_url"] or _text(value["model"], 200, "模型ID", empty=True) != value["model"]:
                    raise ValueError()
                integer(value["timeout_seconds"], 1, 30, "连接超时")
            else:
                auth = value["authorization"]
                if not isinstance(auth, dict) or set(auth) != {"confirmed", "reference"} or type(auth["confirmed"]) is not bool:
                    raise ValueError()
                if auth["reference"] is not None:
                    _text(auth["reference"], 1000, "访问依据")
                if auth["confirmed"] and auth["reference"] is None:
                    raise ValueError()
            return value
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError("本地连接配置文件无效，请检查文件完整性") from None

    def _credential(self, identifier, profile=None):
        name = MODEL_ENV if identifier == "model" else MARKETS[identifier]["env"]
        value = self.environ.get(name, "")
        if value:
            return _key(value), "environment"
        profile = profile or self._profile(identifier)
        if profile["credential_id"]:
            raw = self._read(profile["credential_id"] + ".token", 4096)
            if raw is None:
                raise ValueError("已登记的本地Key文件缺失，请重新保存Key")
            try:
                return _key(raw.decode("ascii")), "local_file"
            except UnicodeError:
                raise ValueError("本地Key文件格式无效") from None
        return "", "missing"

    def market_credential(self, provider):
        if provider not in MARKETS:
            raise ValueError("未知行情连接")
        with self.lock:
            return self._credential(provider)[0]

    def _fingerprint(self, profile, credential):
        return hashlib.sha256((dumps(profile) + "\0" + credential).encode()).hexdigest()

    def _describe(self, identifier):
        profile = self._profile(identifier)
        key_error = None
        try:
            credential, source = self._credential(identifier, profile)
        except ValueError as exc:
            credential, source, key_error = "", "invalid", str(exc)
        result = {k: deepcopy(v) for k, v in profile.items() if k != "credential_id"}
        result.update(name="兼容模型 API" if identifier == "model" else MARKETS[identifier]["name"],
                      credential={"configured": bool(credential), "source": source,
                                  "local_key_saved": bool(profile["credential_id"]), "error": key_error},
                      strategy_input_ready=False)
        if identifier != "model":
            result.update(base_url=MARKETS[identifier]["base_url"], scope=MARKETS[identifier]["scope"])
        checked = self.checks.get(identifier)
        result["last_test"] = deepcopy(checked[1]) if checked and checked[0] == self._fingerprint(profile, credential) else None
        return result

    def describe(self):
        with self.lock:
            return {"market": [self._describe(p) for p in MARKETS], "model": self._describe("model"),
                    "model_usage": "connection_configuration_only", "release_allowed": False}

    def market_status(self, provider):
        if provider not in MARKETS:
            raise ValueError("未知行情连接")
        with self.lock:
            return self._describe(provider)

    def save(self, identifier, value):
        with self.lock:
            old = self._profile(identifier)
            expected = {"schema_version", "revision", "key_action", "api_key"} | (
                {"base_url", "model", "timeout_seconds"} if identifier == "model" else {"authorization"})
            if not isinstance(value, dict) or set(value) != expected:
                raise ValueError("连接配置字段缺失或包含未知字段")
            if type(value["schema_version"]) is not int or value["schema_version"] != 1:
                raise ValueError("连接配置版本不支持")
            if value["revision"] != old["revision"]:
                raise ValueError("连接配置已更新，请刷新后重新保存")
            action, supplied = value["key_action"], value["api_key"]
            if action not in ("keep", "replace", "clear") or not isinstance(supplied, str) or (action != "replace" and supplied):
                raise ValueError("Key操作无效；保留或清除时请勿提交Key")
            if action == "replace":
                _key(supplied)
            if identifier == "model":
                integer(value["timeout_seconds"], 1, 30, "连接超时")
                config = {"base_url": _base_url(value["base_url"]), "model": _text(value["model"], 200, "模型ID", empty=True),
                          "timeout_seconds": value["timeout_seconds"]}
            else:
                auth = value["authorization"]
                if not isinstance(auth, dict) or set(auth) != {"confirmed", "reference"} or type(auth["confirmed"]) is not bool:
                    raise ValueError("访问依据需包含确认状态和说明")
                reference = None if auth["reference"] is None else _text(auth["reference"], 1000, "访问依据", empty=True) or None
                if auth["confirmed"] and reference is None:
                    raise ValueError("确认个人研究访问后，请填写不含Key的访问依据")
                config = {"authorization": {"confirmed": auth["confirmed"], "reference": reference}}
            try:
                existing, _ = self._credential(identifier, old)
            except ValueError:
                if action == "keep":
                    raise
                existing = ""
            if any(_contains(config, secret) for secret in (supplied, existing)):
                raise ValueError("Key只能填入专用Key字段，不能写入地址、模型ID或访问说明")
            token_id = uuid.uuid4().hex if action == "replace" else None if action == "clear" else old["credential_id"]
            new = {"schema_version": 1, "id": identifier, "revision": uuid.uuid4().hex, "updated_at": now(),
                   "credential_id": token_id, **config}
            if action == "replace":
                self._write(token_id + ".token", supplied.encode("ascii"))
            try:
                self._write(identifier + ".json", (dumps(new) + "\n").encode())
            except OSError:
                if action == "replace":
                    (self.directory / (token_id + ".token")).unlink()
                raise
            if old["credential_id"] and token_id != old["credential_id"]:
                try:
                    (self.directory / (old["credential_id"] + ".token")).unlink()
                except FileNotFoundError:
                    pass
            self.checks.pop(identifier, None)
            return self._describe(identifier)

    def test(self, identifier, opener=None):
        """One explicit request: quotes/metadata or models list, never inference/retry."""
        with self.lock:
            profile = self._profile(identifier)
            credential, _ = self._credential(identifier, profile)
            fingerprint = self._fingerprint(profile, credential)
        blocked = None
        if identifier != "model" and not profile["authorization"]["confirmed"]:
            blocked = "请先确认并填写个人研究访问依据，再测试连接"
        if identifier == "model":
            base = _base_url(profile["base_url"])
            if not base or not profile["model"]:
                blocked = "请先保存API地址和模型ID"
            if base and parse.urlsplit(base).hostname not in {"localhost", "127.0.0.1", "::1"} and not credential:
                blocked = "请先配置模型API Key"
        elif not credential:
            blocked = "请先配置行情API Key"
        result = {"status": "blocked" if blocked else "failed", "message": blocked or "连接测试失败，请稍后重试",
                  "tested_at": now(), "sent_requests": 0, "strategy_input_ready": False, "inference_tested": False}
        if not blocked:
            headers = {"Accept": "application/json", "User-Agent": "StockRadar-connection-test"}
            body = None
            if identifier == "model":
                url = base + "/models"
                if credential:
                    headers["Authorization"] = "Bearer " + credential
            elif identifier == "fuyao":
                url = MARKETS[identifier]["base_url"] + "/api/a-share/prices/snapshot?thscodes=600519.SH"
                headers["X-api-key"] = credential
            elif identifier == "tickflow":
                url = MARKETS[identifier]["base_url"] + "/v1/quotes?symbols=600519.SH"
                headers["X-api-key"] = credential
            else:
                url = MARKETS[identifier]["base_url"]
                body = dumps({"api_name": "stock_basic", "token": credential, "params": {"ts_code": "600519.SH"},
                              "fields": "ts_code,name"}).encode()
                headers["Content-Type"] = "application/json"
            result["sent_requests"] = 1
            try:
                http = opener or request.build_opener(_NoRedirect())
                try:
                    response = http.open(request.Request(url, data=body, headers=headers), timeout=profile.get("timeout_seconds", 15))
                except error.HTTPError as exc:
                    response = exc
                with response:
                    result["http_status"] = response.code
                    if response.code != 200:
                        messages = {401: "认证失败，请核对Key", 403: "访问权限不足，请核对接口权限", 429: "请求已被限流；本次不自动重试"}
                        result["message"] = messages.get(response.code, "服务返回异常状态，请核对API地址和服务状态")
                    else:
                        raw = response.read(MAX_RESPONSE + 1)
                        if len(raw) > MAX_RESPONSE:
                            raise ValueError()
                        payload = json.loads(raw)
                        if identifier == "model":
                            rows = payload["data"]
                            if not isinstance(rows, list) or len(rows) > 10000 or any(not isinstance(r, dict) or not isinstance(r.get("id"), str) for r in rows):
                                raise ValueError()
                            present = any(row["id"] == profile["model"] for row in rows)
                            result.update(status="reachable" if present else "model_not_listed", model_listed=present,
                                          message="模型目录可达，所选模型已列出；推理能力尚未测试" if present else "模型目录可达，但未列出所选模型；请核对模型ID或服务说明")
                        elif identifier == "tickflow":
                            rows = payload["data"]
                            if not isinstance(rows, list) or not rows:
                                raise ValueError()
                            result.update(status="reachable", message="报价接口已响应；数据质量和分钟策略资格另验")
                        else:
                            code = payload["code"]
                            if type(code) is not int:
                                raise ValueError()
                            result["api_code"] = code
                            if code != 0:
                                result["message"] = {2001: "认证失败，请核对Key", 2002: "访问权限不足，请核对接口权限", 2003: "访问权限不足，请核对接口权限", 4001: "请求已被限流；本次不自动重试"}.get(code, "业务接口返回错误，请核对权限及服务状态")
                            else:
                                rows = payload["data"]["item" if identifier == "fuyao" else "items"]
                                if not isinstance(rows, list) or not rows:
                                    raise ValueError()
                                if identifier == "fuyao" and not any(isinstance(row, dict) and row.get("thscode") == "600519.SH" for row in rows):
                                    raise ValueError()
                                result.update(status="reachable", message="接口已返回样本；数据质量和分钟策略资格另验")
            except (error.URLError, socket.timeout, TimeoutError, OSError):
                result["message"] = "连接未完成，请检查API地址、网络或本地模型服务"
            except (ValueError, TypeError, KeyError, UnicodeError):
                result["message"] = "响应为空或格式不符合接口约定，请核对服务地址和能力"
        with self.lock:
            current = self._profile(identifier)
            current_key, _ = self._credential(identifier, current)
            if self._fingerprint(current, current_key) == fingerprint:
                self.checks[identifier] = (fingerprint, deepcopy(result))
            else:
                result.update(status="stale", message="测试期间配置已变化，请按最新配置重新测试")
        return result
