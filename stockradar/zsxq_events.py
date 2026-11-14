"""Bounded manual ZSXQ collection, independent of strategy/store/notifiers.

Run with ``python3 -m stockradar.zsxq_events --help``. Authentication belongs
to the official CLI; this module never reads its credentials or browser data.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit, urlunsplit

GROUP_ID = "51128424448184"
MAX_BYTES = 8 * 1024 * 1024


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,32}", value):
        raise ValueError("ID 必须是数字字符串")
    return value


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("时间必须是带时区的字符串")
    # Python 3.9 does not accept the vendor's compact +0800 offset.
    value = re.sub(r"([+-][0-9]{2})([0-9]{2})$", r"\1:\2", value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("时间必须带时区")
    return parsed.astimezone(timezone.utc).isoformat()


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "e":
            self.parts.append(unquote(dict(attrs).get("title", "")))
        elif tag in {"br", "p", "div"}:
            self.parts.append("\n")


def plain(value):
    if not isinstance(value, str):
        raise ValueError("主题文本必须是字符串")
    parser = PlainText()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts)
    # Signed attachment URLs and tracking parameters are not research evidence.
    def clean_url(match):
        parsed = urlsplit(match.group())
        if parsed.username or parsed.password:
            return "[已移除含凭据链接]"
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return re.sub(r"https?://[^\s<>\"']+", clean_url, text).strip()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def normalize(payload, observed_at, limit=20):
    observed_at = timestamp(observed_at)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("本接入单次只允许 1—20 条主题")
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("知识星球没有返回成功结果")
    rows = payload.get("topics_brief")
    if not isinstance(rows, list) or len(rows) > limit or payload.get("count") != len(rows):
        raise ValueError("主题数量或响应结构不匹配")
    if type(payload.get("has_more")) is not bool:
        raise ValueError("缺少分页完整性状态")
    topics, seen = [], {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("group"), dict):
            raise ValueError("主题结构不完整")
        if row["group"].get("group_id") != GROUP_ID:
            raise ValueError("响应含非指定星球内容")
        topic_id = identifier(row.get("topic_id"))
        published = timestamp(row.get("create_time"))
        modified = timestamp(row["modify_time"]) if row.get("modify_time") else None
        images, files = row.get("images", []), row.get("files", [])
        if not isinstance(images, list) or not isinstance(files, list):
            raise ValueError("附件结构不完整")
        content = plain(row.get("content"))
        version = dict(group_id=GROUP_ID, topic_id=topic_id,
                       title=plain(row.get("title", "")), content=content,
                       published_at=published, modified_at=modified,
                       image_ids=[identifier(i.get("image_id")) for i in images],
                       file_ids=[identifier(i.get("file_id")) for i in files])
        revision = fingerprint(version)
        if topic_id in seen:
            if seen[topic_id] != revision:
                raise ValueError("同一响应内主题版本冲突")
            continue
        seen[topic_id] = revision
        reasons = ["EVENT_TIME_NOT_VERIFIED", "PUBLIC_FACTS_NOT_VERIFIED", "MARKET_DATA_NOT_EVALUATED"]
        if images or files:
            reasons.append("ATTACHMENTS_NOT_PARSED")
        if not content or content == "「图片」":
            reasons.append("NO_TEXT_CONTENT")
        if datetime.fromisoformat(published) > datetime.fromisoformat(observed_at):
            reasons.append("SOURCE_TIME_AFTER_OBSERVATION")
        topics.append(dict(version, content_hash=revision, observed_at=observed_at,
                           event_time=None, available_at=None,
                           source_url="https://wx.zsxq.com/group/" + GROUP_ID,
                           research_status="pending_verification", reason_codes=reasons))
    return dict(schema_version=1, source="zsxq_official_cli", group_id=GROUP_ID,
                observed_at=observed_at, fetched_count=len(rows), unique_count=len(topics),
                has_more=payload["has_more"], scope="latest_page_only",
                topics=topics, automatic_collection=False, strategy_input_ready=False,
                release_allowed=False)


def fetch(cli, limit):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("单次主题上限必须为 1—20")
    binary = Path(cli).expanduser().resolve(strict=True)
    if not binary.is_file():
        raise ValueError("CLI 路径不是文件")
    # No shell, no raw stdout/stderr logging, no credentials in arguments.
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run([str(binary), "group", "+topics", "--group-id", GROUP_ID,
                                     "--limit", str(limit), "--json"], stdout=output,
                                    stderr=subprocess.DEVNULL, timeout=45, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("知识星球读取失败或超时；未重试，请检查官方授权或连接") from None
        if result.returncode:
            raise ValueError("知识星球读取未成功；请检查官方授权与群权限")
        if output.tell() > MAX_BYTES:
            raise ValueError("主题响应超过大小上限")
        output.seek(0)
        try:
            return json.load(output)
        except (ValueError, UnicodeError):
            raise ValueError("知识星球响应不是有效 JSON") from None


def save(report, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    data = json.dumps(report, ensure_ascii=False, indent=2).encode()
    path = destination / "topics.json"
    with path.open("xb") as out:
        out.write(data)
    path.chmod(0o600)
    manifest = {"schema_version": 1, "group_id": GROUP_ID,
                "observed_at": report["observed_at"], "unique_count": report["unique_count"],
                "topics_sha256": hashlib.sha256(data).hexdigest(),
                "sanitized": True, "raw_response_saved": False,
                "strategy_input_ready": False, "release_allowed": False}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="指定知识星球的有界手动事件采集；不生成策略信号")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cli", help="已安装并完成授权的官方 zsxq-cli 路径")
    source.add_argument("--input", help="离线导入官方 CLI 的 JSON 文件；不发网")
    parser.add_argument("--output", required=True, help="新输出目录；已有目录拒绝覆盖")
    parser.add_argument("--limit", type=int, choices=range(1, 21), default=20)
    args = parser.parse_args(argv)
    if Path(args.output).exists():
        parser.error("输出目录已存在；未发起读取")
    try:
        if args.input:
            path = Path(args.input)
            if path.stat().st_size > MAX_BYTES:
                raise ValueError("导入文件超过大小上限")
            payload = json.loads(path.read_text())
        else:
            payload = fetch(args.cli, args.limit)
        report = normalize(payload, datetime.now(timezone.utc).isoformat(), args.limit)
        report["capture_mode"] = "offline_import" if args.input else "manual_fetch"
        report["ingested_at"] = report["observed_at"]
        manifest = save(report, args.output)
        print(json.dumps(manifest, ensure_ascii=False))
    except (ValueError, OSError, TypeError, AttributeError) as error:
        # Do not include raw JSON, response body or credential-bearing URLs.
        parser.exit(1, "知识星球采集未完成（%s）；未生成策略信号。\n" % type(error).__name__)


if __name__ == "__main__":
    main()
