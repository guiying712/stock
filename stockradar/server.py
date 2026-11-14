"""Authenticated, loopback-only HTTP API and static UI."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote

from . import __version__
from .store import StoreError, digest


def handler_for(app, token):
    class Handler(BaseHTTPRequestHandler):
        server_version = "StockRadar/" + __version__

        def log_message(self, format, *args):
            # Do not log request paths, headers or tokens.
            pass

        def respond(self, value, status=200, content_type="application/json; charset=utf-8"):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if content_type.startswith("application/json") else value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def error_response(self, code, message, status=400):
            self.respond({"error": {"code": code, "message": message}}, status)

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

        def handle_request(self, method):
            try:
                host = self.headers.get("Host", "")
                if host.split(":")[0] not in {"127.0.0.1", "localhost"}:
                    return self.error_response("HOST_FORBIDDEN", "此服务仅接受本地访问", 403)
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + host:
                    return self.error_response("ORIGIN_FORBIDDEN", "拒绝跨站请求", 403)
                parsed = urlsplit(self.path)
                path = unquote(parsed.path)
                if path.startswith("/api/"):
                    supplied = self.headers.get("Authorization", "")
                    if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
                        return self.error_response("UNAUTHORIZED", "访问令牌无效或已失效", 401)
                    data = {}
                    if method == "POST":
                        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                            return self.error_response("INVALID_INPUT", "请求必须使用 application/json", 415)
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= 2_000_000:
                            return self.error_response("INVALID_INPUT", "请求大小无效", 413)
                        def unique_pairs(items):
                            result = {}
                            for key, value in items:
                                if key in result:
                                    raise ValueError("请求JSON含重复键")
                                result[key] = value
                            return result
                        data = json.loads(self.rfile.read(length), object_pairs_hook=unique_pairs,
                                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError("非法数字")))
                        if not isinstance(data, dict):
                            raise ValueError("请求必须为 JSON 对象")
                    result, status = self.route(method, path, parse_qs(parsed.query), data)
                    return self.respond(result, status)
                if method != "GET":
                    return self.error_response("NOT_FOUND", "接口不存在", 404)
                files = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
                         "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                         "/evidence-chart.js": ("evidence-chart.js", "text/javascript; charset=utf-8"),
                         "/study-view.js": ("study-view.js", "text/javascript; charset=utf-8")}
                files["/connection-view.js"] = ("connection-view.js", "text/javascript; charset=utf-8")
                files["/minute-view.js"] = ("minute-view.js", "text/javascript; charset=utf-8")
                files["/real-market-view.js"] = ("real-market-view.js", "text/javascript; charset=utf-8")
                files["/history-view.js"] = ("history-view.js", "text/javascript; charset=utf-8")
                files["/setup-view.js"] = ("setup-view.js", "text/javascript; charset=utf-8")
                if path == "/favicon.ico":
                    return self.respond(b"", 204, "image/x-icon")
                if path not in files:
                    return self.error_response("NOT_FOUND", "页面不存在", 404)
                filename, mime = files[path]
                return self.respond((Path(__file__).parent / "static" / filename).read_bytes(), content_type=mime)
            except (StoreError, ValueError, KeyError, TypeError) as exc:
                code = getattr(exc, "code", "INVALID_INPUT")
                return self.error_response(code, str(exc), 404 if code == "NOT_FOUND" else 409 if code in {"VERSION_IMMUTABLE", "IDEMPOTENCY_CONFLICT", "REPLAY_BUSY", "STUDY_NOT_COMPLETED", "MINUTE_BUSY", "MINUTE_COOLDOWN"} else 400)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                app.store.log("API_ERROR", "请求处理失败，请检查服务运行状态", "error")
                return self.error_response("INTERNAL_ERROR", "服务处理失败；详情见运行诊断", 500)

        def route(self, method, path, query, data):
            prefix = "/api/v1/"
            if not path.startswith(prefix):
                raise StoreError("NOT_FOUND", "接口不存在")
            endpoint = path[len(prefix):].strip("/")
            parts = endpoint.split("/")
            if method == "GET":
                if endpoint == "connections":
                    return app.connections.describe(), 200
                if endpoint == "minute-data":
                    return app.minutes.describe(), 200
                if endpoint == "real-market":
                    return app.real_market.describe(), 200
                if endpoint == "source-health":
                    from .source_health import source_health
                    return source_health(Path(app.store.path).parent), 200
                if endpoint == "health":
                    return app.health(), 200
                if endpoint == "market":
                    market = app.current()["market"].copy()
                    health = app.health()
                    if health["updates_paused"]:
                        market.update(status="UNKNOWN", reason_codes=health["quality"]["reason_codes"])
                    return market, 200
                if endpoint == "sectors":
                    sectors = app.current()["sectors"]
                    health = app.health()
                    if health["updates_paused"]:
                        for sector in sectors:
                            sector.update(quality="paused", reason_codes=sorted(set(sector["reason_codes"] + health["quality"]["reason_codes"])))
                    return {"items": sectors}, 200
                if endpoint == "sector-timeline":
                    from .evidence import sector_timeline
                    return sector_timeline(app.store, app.config["id"], query.get("sector_id", [""])[0]), 200
                if endpoint == "signals":
                    items = app.store.signals(app.config["id"])
                    health = app.health()
                    if health["updates_paused"]:
                        for signal in items:
                            if signal["status"] not in {"INVALIDATED", "EXPIRED"}:
                                signal.update(actionability="paused", reason_codes=health["quality"]["reason_codes"])
                    status = query.get("status", [""])[0]
                    text = query.get("q", [""])[0].lower()
                    sector = query.get("sector", [""])[0]
                    if status:
                        items = [s for s in items if s["status"] == status]
                    if text:
                        items = [s for s in items if text in (s["code"] + s["name"]).lower()]
                    if sector:
                        items = [s for s in items if s.get("primary_sector_id") == sector]
                    # Cursor binds an immutable view fingerprint: data changes force refresh.
                    fingerprint = digest(items)[:16]
                    cursor = query.get("cursor", [""])[0]
                    start = 0
                    if cursor:
                        sha, offset = cursor.split(":")
                        if sha != fingerprint:
                            raise StoreError("CURSOR_STALE", "信号已更新，请从第一页刷新")
                        start = int(offset)
                        if start < 0:
                            raise ValueError("游标无效")
                    limit = max(1, min(100, int(query.get("limit", ["30"])[0])))
                    end = start + limit
                    return {"items": items[start:end], "total": len(items), "next_cursor": fingerprint + ":" + str(end) if end < len(items) else None}, 200
                if len(parts) == 2 and parts[0] == "signals":
                    result = app.signal_detail(parts[1])
                    health = app.health()
                    if health["updates_paused"] and result["status"] not in {"INVALIDATED", "EXPIRED"}:
                        result.update(actionability="paused", reason_codes=health["quality"]["reason_codes"])
                    return result, 200
                if endpoint == "notifications":
                    return {"items": app.store.notifications()}, 200
                if endpoint == "strategy-versions":
                    return {"items": app.store.versions()}, 200
                if endpoint == "replays":
                    return {"items": app.store.jobs(kind="replay")}, 200
                if len(parts) == 2 and parts[0] == "replays":
                    job = app.store.job(parts[1])
                    if job["request"].get("kind", "replay") != "replay":
                        raise StoreError("NOT_FOUND", "回放任务不存在")
                    return job, 200
                if endpoint == "study-sources":
                    from .study_jobs import sources
                    return sources(app.store), 200
                if endpoint == "studies":
                    from .study_jobs import list_jobs
                    return {"items": list_jobs(app.store)}, 200
                if endpoint == "study-cards":
                    from .study_jobs import study_cards
                    return study_cards(app.store), 200
                if len(parts) == 3 and parts[0] == "studies" and parts[2] == "cases":
                    from .study_jobs import study_cases
                    return study_cases(app.store, parts[1], query.get("profile", [""])[0]), 200
                if len(parts) in (2, 3) and parts[0] == "studies" and (len(parts) == 2 or parts[2] == "report"):
                    from .study_jobs import get_job
                    job = get_job(app.store, parts[1], full=len(parts) == 3)
                    if len(parts) == 3:
                        if job["status"] != "completed":
                            raise StoreError("STUDY_NOT_COMPLETED", "成本研究尚未完成，不能导出报告")
                        return job["result"], 200
                    return job, 200
                if endpoint == "diagnostics":
                    return app.diagnostics(), 200
                if endpoint == "config/export":
                    return app.config, 200
            else:
                if endpoint == "minute-data/prepare":
                    return app.minutes.prepare(data), 200
                if endpoint == "real-market/fetch":
                    return app.real_market.fetch(data), 200
                if endpoint == "minute-data/fetch":
                    return app.minutes.fetch(data), 200
                if parts[:1] == ["connections"]:
                    identifier = (parts[2] if len(parts) in (3, 4) and parts[1] == "market" else
                                  "model" if len(parts) in (2, 3) and parts[1] == "model" else None)
                    if identifier is not None:
                        is_test = parts[-1] == "test"
                        if is_test and ((parts[1] == "market" and len(parts) == 4) or (parts[1] == "model" and len(parts) == 3)):
                            if data:
                                raise ValueError("连接测试使用已保存配置，不接受额外参数")
                            return app.connections.test(identifier), 200
                        if (parts[1] == "market" and len(parts) == 3) or (parts[1] == "model" and len(parts) == 2):
                            return app.connections.save(identifier, data), 200
                    raise StoreError("NOT_FOUND", "连接配置接口不存在")
                if len(parts) == 3 and parts[0] == "signals" and parts[2] == "feedback":
                    if set(data) != {"action", "idempotency_key"}:
                        raise ValueError("反馈仅接受 action 与 idempotency_key")
                    return app.store.feedback(parts[1], data["action"], data["idempotency_key"]), 200
                if endpoint == "strategy-versions":
                    if set(data) != {"config"}:
                        raise ValueError("新版本请求须包含 config 对象")
                    config = app.store.register_version(data["config"])
                    return {"id": config["id"], "config": config, "status": config["status"]}, 201
                if endpoint == "replays":
                    return app.start_replay(data), 202
                if endpoint == "studies":
                    return app.start_study(data), 202
                if endpoint in {"demo/advance", "demo/reset", "channels/dingtalk/test"} and data:
                    raise ValueError("此操作不接受额外参数")
                if endpoint == "demo/advance":
                    return app.advance_demo(), 200
                if endpoint == "demo/reset":
                    return app.reset_demo(), 200
                if endpoint == "channels/dingtalk/test":
                    return app.test_channel(), 200
            raise StoreError("NOT_FOUND", "接口不存在")

    return Handler


def serve(app, token, port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(app, token))
    server.daemon_threads = True
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
