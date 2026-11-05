#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data/ 与小程序静态快照打成一个自包含、可离线校验的 zip 归档。

设计目标：即使原小程序下架、云函数关停、仓库只剩一个 zip 文件，
也能不联网、不依赖任何第三方库地还原出全量数据。

用法：
    python tools/build_archive.py
    python tools/build_archive.py --root . --out archive/baoleizhen-snapshot.zip
"""
import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_VERSION = 1
MANIFEST_NAME = "ARCHIVE_MANIFEST.json"
INCLUDE_DIRS = ("data", "snapshots")
# 只收「数据资产 + 数据说明 + 还原工具」。README / CHANGELOG / PITFALLS 会随每次
# 记账提交变动，若打进 zip 会让二进制归档无谓变化，故排除（仓库里始终有）。
INCLUDE_DOCS = ("DATA_SUMMARY.md", "data/README.md", "archive/RESTORE.txt")
INCLUDE_TOOLS = ("tools/restore.py", "tools/build_archive.py")
SKIP_SUFFIX = (".pyc", ".log", ".DS_Store")


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def collect_files(root):
    """返回要归档的相对路径（POSIX 风格、排序后、去重）。"""
    found = set()
    for sub in INCLUDE_DIRS:
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for fn in sorted(filenames):
                if fn.endswith(SKIP_SUFFIX):
                    continue
                p = os.path.join(dirpath, fn)
                found.add(os.path.relpath(p, root).replace(os.sep, "/"))
    for rel in INCLUDE_DOCS + INCLUDE_TOOLS:
        if os.path.isfile(os.path.join(root, rel)):
            found.add(rel)
    return sorted(found)


def count_jsonl(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def make_manifest(root, files):
    meta_path = os.path.join(root, "data", "meta.json")
    meta = {}
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    entries = []
    for rel in files:
        with open(os.path.join(root, rel), "rb") as f:
            b = f.read()
        entries.append({"path": rel, "sha256": sha256(b), "size": len(b)})
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": "tools/build_archive.py",
        "manifest_name": MANIFEST_NAME,
        "description": "网购避雷真 · 离线自包含数据归档；还原用 tools/restore.py",
        "source": {
            "appid": meta.get("appid", ""),
            "cloud_env": meta.get("cloud_env", ""),
            "fetched_at": meta.get("fetched_at", ""),
        },
        "counts": {
            "sku": count_jsonl(os.path.join(root, "data", "sku", "sku.jsonl")),
            "posts": count_jsonl(os.path.join(root, "data", "posts", "posts.jsonl")),
            "files": len(files),
        },
        "files": entries,
    }


def zip_datetime(root):
    """用抓取时间作为 zip 内文件时间戳，使相同内容可复现为相同字节。"""
    meta_path = os.path.join(root, "data", "meta.json")
    try:
        with open(meta_path, encoding="utf-8") as f:
            s = json.load(f).get("fetched_at", "")
        dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second // 2 * 2)
    except Exception:
        return (2026, 1, 1, 0, 0, 0)


def build(root, out_zip, manifest_out=None):
    """生成归档 zip，返回 manifest dict。"""
    files = collect_files(root)
    if not files:
        raise RuntimeError("没有可归档的文件，检查 --root")
    manifest = make_manifest(root, files)
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2,
                                sort_keys=True).encode("utf-8")
    dt = zip_datetime(root)
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(MANIFEST_NAME, date_time=dt)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        z.writestr(info, manifest_bytes)
        for rel in files:
            with open(os.path.join(root, rel), "rb") as f:
                data = f.read()
            it = zipfile.ZipInfo(rel, date_time=dt)
            it.compress_type = zipfile.ZIP_DEFLATED
            it.external_attr = 0o644 << 16
            z.writestr(it, data)
    if manifest_out:
        os.makedirs(os.path.dirname(os.path.abspath(manifest_out)), exist_ok=True)
        with open(manifest_out, "w", encoding="utf-8") as f:
            f.write(manifest_bytes.decode("utf-8"))
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--out", default=os.path.join(ROOT, "archive", "baoleizhen-snapshot.zip"))
    ap.add_argument("--manifest-out", default=os.path.join(ROOT, "archive", "MANIFEST.json"))
    a = ap.parse_args()
    m = build(a.root, a.out, a.manifest_out)
    size = os.path.getsize(a.out)
    print("归档完成: %s" % a.out)
    print("  %d 个文件 / SKU %d 条 / 帖子 %d 篇 / 压缩后 %.1f KB" %
          (m["counts"]["files"], m["counts"]["sku"], m["counts"]["posts"], size / 1024))
    print("  清单: %s" % a.manifest_out)


if __name__ == "__main__":
    main()
