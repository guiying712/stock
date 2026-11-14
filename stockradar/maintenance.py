"""Read-only scan compression with checksums; never deletes event evidence."""
import gzip
import hashlib
import json
import os
from pathlib import Path

from .contracts import utc, write_new_json
from .store import digest, dumps


def archive_scans(store, version, before, output):
    cutoff = utc(before)
    config = store.version(version)
    target = Path(output)
    manifest_path = Path(str(output) + ".manifest.json")
    if target.exists() or manifest_path.exists():
        raise ValueError("归档及清单目标必须不存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as db:
        count = sum(utc(r[0]) < cutoff for r in db.execute("SELECT as_of FROM scans WHERE version=?", (version,)))
        header = {"kind": "stockradar-input-archive", "schema_version": 1, "version": version, "config": config,
                  "config_hash": digest(config), "before": cutoff.isoformat(), "row_count": count}
        with target.open("xb") as raw:
            os.chmod(target, 0o600)
            uncompressed = 0
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
                line = (dumps(header) + "\n").encode()
                stream.write(line)
                uncompressed += len(line)
                for row in db.execute("SELECT seq,snapshot_id,as_of,hash,input,result FROM scans WHERE version=? ORDER BY seq", (version,)):
                    if utc(row["as_of"]) >= cutoff:
                        continue
                    item = {"seq": row["seq"], "snapshot_id": row["snapshot_id"], "as_of": row["as_of"],
                            "input_hash": row["hash"], "input": json.loads(row["input"]),
                            "original_result_hash": digest(json.loads(row["result"]))}
                    line = (dumps(item) + "\n").encode()
                    stream.write(line)
                    uncompressed += len(line)
    sha = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    size = target.stat().st_size
    manifest = {**header, "sha256": sha.hexdigest(), "compressed_bytes": size, "uncompressed_bytes": uncompressed,
                "compression_ratio": size / uncompressed if uncompressed else None,
                "source_database_modified": False, "note": "只归档输入及原结果哈希；完整状态/事件恢复须使用SQLite备份"}
    write_new_json(manifest_path, manifest)
    os.chmod(manifest_path, 0o600)
    return manifest


def read_archive(path, expected_sha256):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    if sha.hexdigest() != expected_sha256:
        raise ValueError("归档校验和不匹配")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if header.get("kind") != "stockradar-input-archive" or header.get("schema_version") != 1 or digest(header["config"]) != header["config_hash"]:
            raise ValueError("归档头或配置哈希无效")
        rows = [json.loads(line) for line in stream]
    if len(rows) != header["row_count"] or any(digest(r["input"]) != r["input_hash"] for r in rows):
        raise ValueError("归档记录缺失或输入哈希冲突")
    return header, rows
