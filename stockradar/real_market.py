"""Bounded Fuyao quote/daily viewer, isolated from strategy inputs."""
from datetime import datetime, timedelta, timezone
from .contracts import fields, integer, numeric, utc
from .minute_feed import MinuteFeed, SHANGHAI
from .store import StoreError
from .vendor_samples import _read_probe, validate_sample_plan
from .contracts import load_json
import json


class RealMarket(MinuteFeed):
    def plan(self, value, identifier="fuyao-view"):
        fields(value, ("schema_version", "mode", "symbols", "access_confirmed"), "真实行情请求")
        integer(value["schema_version"], 1, 1, "真实行情版本")
        if value["mode"] != "latest" or type(value["access_confirmed"]) is not bool:
            raise ValueError("真实行情须明确选择latest与本次访问确认")
        if not isinstance(value["symbols"], list) or not 1 <= len(value["symbols"]) <= 3:
            raise ValueError("每次选择1至3只股票")
        symbols = []
        for symbol in value["symbols"]:
            if not isinstance(symbol, str):
                raise ValueError("股票代码须为字符串")
            symbols.append(dict(symbol=symbol, board="STAR" if symbol.startswith(("688", "689")) else "CHINEXT" if symbol.startswith(("300", "301")) else "MAIN"))
        end = self.clock().astimezone(SHANGHAI).date() - timedelta(days=1)
        profile = self.connections.market_status("fuyao")
        confirmed = value["access_confirmed"] and profile["authorization"]["confirmed"]
        return validate_sample_plan(dict(schema_version=1, id=identifier.replace("tushare-minute", "fuyao-view"), purpose="experimental", provider="fuyao",
            symbols=symbols, datasets=["quotes", "daily_bars"], start_date=(end-timedelta(days=6)).isoformat(), end_date=end.isoformat(),
            authorization=dict(confirmed=confirmed, reference="Explicit manual two-request personal research capture in real market viewer" if confirmed else None),
            request_interval_seconds="6.1", request_timeout_seconds=15, max_requests=2))

    def fetch(self, value, **kwargs):
        try:
            return super().fetch(value, **kwargs)
        except StoreError as exc:
            raise StoreError(str(exc.code).replace("MINUTE", "MARKET"), str(exc).replace("Tushare Token", "Fuyao Key").replace("分钟", "行情")) from None

    def describe(self):
        result = dict(provider="fuyao", capture=None, groups=[], attempt=self._read("attempt.json"),
                      strategy_input_ready=False, release_allowed=False, automatic_collection=False)
        if result["attempt"] and result["attempt"]["status"] == "running" and result["attempt"]["id"] != self.active:
            result["attempt"] = dict(result["attempt"], status="unfinished")
        latest = self._read("latest.json")
        if not latest:
            return result
        directory = self.directory / latest["id"]
        report, bars = _read_probe(directory)
        if report["provider"] != "fuyao" or report["plan"]["datasets"] != ["quotes", "daily_bars"]:
            raise ValueError("真实行情记录来源或范围不匹配")
        snapshots = [json.loads(line) for line in (directory / "snapshots.jsonl").read_text().splitlines()]
        quote = next((s for s in snapshots if s["dataset"] == "quotes"), None)
        batch_time = None
        if quote and type(quote.get("source_timestamp_ms")) is int:
            try:
                batch_time = (datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=quote["source_timestamp_ms"])).isoformat()
            except (OverflowError, ValueError):
                pass
        result["capture"] = {k: report[k] for k in ("status", "simulated", "completed_at", "sent_requests", "bar_count", "output_hash")}
        result["capture"].update(batch_time=batch_time, quote_event_time=None, date_window=[report["plan"]["start_date"], report["plan"]["end_date"]],
            reception_age_seconds=max(0, (self.clock()-utc(report["completed_at"])).total_seconds()),
            requests=[{k:r.get(k) for k in ("dataset","status","reason_code","api_code")} for r in report["requests"]])
        result["capture"]["batch_time_after_receipt"] = bool(batch_time and quote and utc(batch_time)>utc(quote["observed_at"]))
        for item in report["plan"]["symbols"]:
            row = next((r for r in quote["rows"] if r.get("thscode")==item["symbol"]), {}) if quote else {}
            prices = {}
            for key in ("last_price", "open_price", "high_price", "low_price", "prev_price"):
                try:
                    number = numeric(row.get(key), key, nullable=True)
                    prices[key] = str(number) if number is not None and number>0 else None
                except ValueError:
                    prices[key] = None
            result["groups"].append(dict(symbol=item["symbol"], prices=prices, quote_available=bool(row), quote_event_time=None,
                daily=[{k:b[k] for k in ("label","prices","volume_shares","amount_cny")} for b in bars if b["symbol"]==item["symbol"]]))
        return result
