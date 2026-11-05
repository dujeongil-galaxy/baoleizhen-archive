#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线校验并还原 baoleizhen-snapshot.zip。

只用 Python 标准库，不联网、不依赖原小程序或云函数。

用法：
    python tools/restore.py --check                       # 只校验，不写任何文件
    python tools/restore.py                              # 校验通过后解包到 restored/ 并生成 SQLite
    python tools/restore.py --archive X.zip --out DIR    # 指定归档与目标目录
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ARCHIVE = os.path.join(ROOT, "archive", "baoleizhen-snapshot.zip")
MANIFEST_NAME = "ARCHIVE_MANIFEST.json"
SCHEMA_VERSION = 1
OPENID_RE = re.compile(r"o[A-Za-z0-9_-]{25,}")
REQUIRED = (
    "data/sku/sku.jsonl", "data/sku/sku_list_raw.json",
    "data/posts/posts.jsonl", "data/meta.json", "data/api-contract.json",
)


def _checks():
    return []


def add(checks, name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    return bool(ok)


def read_jsonl_bytes(b):
    return [json.loads(x) for x in b.decode("utf-8").splitlines() if x.strip()]


def scalar(v):
    """SQLite 索引列只接受标量，嵌套结构留在 json 全文列里。"""
    return v if v is None or isinstance(v, (str, int, float, bool)) else None


def verify(zip_path):
    """返回 (checks, errors)。checks 为 (名称, 是否通过, 说明) 列表。"""
    checks = _checks()
    if not os.path.isfile(zip_path):
        add(checks, "归档文件存在", False, zip_path)
        return checks, ["归档文件不存在: %s" % zip_path]
    add(checks, "归档文件存在", True, os.path.basename(zip_path))

    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        if not add(checks, "清单文件存在", MANIFEST_NAME in names):
            return checks, ["归档内缺少 %s" % MANIFEST_NAME]
        try:
            manifest = json.loads(z.read(MANIFEST_NAME))
        except Exception as e:  # noqa: BLE001
            add(checks, "清单可解析", False, str(e)[:120])
            return checks, ["清单 JSON 解析失败"]
        add(checks, "清单可解析", True)
        add(checks, "清单版本", manifest.get("schema_version") == SCHEMA_VERSION,
            "期望 %d，实际 %s" % (SCHEMA_VERSION, manifest.get("schema_version")))

        declared = {e["path"] for e in manifest.get("files", [])}
        missing = declared - names
        extra = (names - declared) - {MANIFEST_NAME}
        add(checks, "文件清单齐全", not missing, "缺失 %d 个" % len(missing))
        add(checks, "无未登记文件", not extra, "多出 %d 个" % len(extra))

        bad_hash, bad_size = [], []
        for e in manifest.get("files", []):
            rel = e["path"]
            if rel not in names:
                continue
            data = z.read(rel)
            import hashlib
            if hashlib.sha256(data).hexdigest() != e.get("sha256"):
                bad_hash.append(rel)
            if len(data) != e.get("size"):
                bad_size.append(rel)
        add(checks, "逐文件 SHA256", not bad_hash, "不符 %d 个%s" %
            (len(bad_hash), "（例：%s）" % bad_hash[0] if bad_hash else ""))
        add(checks, "逐文件体积", not bad_size, "不符 %d 个" % len(bad_size))

        need = [p for p in REQUIRED if p not in names]
        add(checks, "核心数据文件齐全", not need, "缺 %s" % (", ".join(need) if need else "无"))
        if need:
            return checks, ["核心数据文件缺失: %s" % ", ".join(need)]

        skus = read_jsonl_bytes(z.read("data/sku/sku.jsonl"))
        posts = read_jsonl_bytes(z.read("data/posts/posts.jsonl"))
        counts = manifest.get("counts", {})
        add(checks, "SKU 条数一致", len(skus) == counts.get("sku"),
            "%d vs 清单 %s" % (len(skus), counts.get("sku")))
        add(checks, "帖子条数一致", len(posts) == counts.get("posts"),
            "%d vs 清单 %s" % (len(posts), counts.get("posts")))

        ids = [p.get("id") for p in posts]
        add(checks, "帖子 id 唯一", len(ids) == len(set(ids)),
            "重复 %d 条" % (len(ids) - len(set(ids))))
        sku_ids = {s.get("id") for s in skus}
        orphan = [p.get("skuId") for p in posts if p.get("skuId") not in sku_ids]
        add(checks, "帖子 SKU 引用完整", not orphan, "孤立 %d 条" % len(orphan))

        blob = z.read("data/sku/sku.jsonl") + z.read("data/posts/posts.jsonl")
        leaks = set(OPENID_RE.findall(blob.decode("utf-8", "replace")))
        add(checks, "无明文 openid", not leaks, "命中 %d 个" % len(leaks))

    errors = ["%s：%s" % (n, d) for n, ok, d in checks if not ok]
    return checks, errors


def safe_member(rel):
    rel = rel.replace("\\", "/")
    return not (rel.startswith("/") or ".." in rel.split("/") or ":" in rel.split("/")[0])


def write_sqlite(out, skus, posts, manifest):
    db = os.path.join(out, "baoleizhen.db")
    if os.path.exists(db):
        os.remove(db)
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE skus (
            id TEXT PRIMARY KEY, name TEXT, category TEXT, brand_raw TEXT,
            platform TEXT, price REAL, avg_score REAL, score_count INTEGER,
            latest_date TEXT, json TEXT NOT NULL);
        CREATE TABLE posts (
            id TEXT PRIMARY KEY, sku_id TEXT, type TEXT, score INTEGER,
            title TEXT, date TEXT, status TEXT, json TEXT NOT NULL);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE INDEX idx_posts_sku ON posts(sku_id);
        CREATE INDEX idx_skus_cat ON skus(category);
    """)
    conn.executemany(
        "INSERT OR REPLACE INTO skus VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(x.get("id"), scalar(x.get("name")), scalar(x.get("category")),
          scalar(x.get("brandRaw")), scalar(x.get("platform")),
          scalar(x.get("price")), scalar(x.get("avgScore")),
          scalar(x.get("scoreCount")), scalar(x.get("latestDate")),
          json.dumps(x, ensure_ascii=False)) for x in skus])
    conn.executemany(
        "INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?,?,?,?)",
        [(x.get("id"), scalar(x.get("skuId")), scalar(x.get("type")),
          scalar(x.get("score")), scalar(x.get("title")), scalar(x.get("date")),
          scalar(x.get("status")), json.dumps(x, ensure_ascii=False)) for x in posts])
    conn.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
        ("schema_version", str(manifest.get("schema_version"))),
        ("created_at", str(manifest.get("created_at"))),
        ("source_fetched_at", str(manifest.get("source", {}).get("fetched_at"))),
        ("appid", str(manifest.get("source", {}).get("appid"))),
        ("sku_count", str(len(skus))), ("post_count", str(len(posts))),
    ])
    conn.commit()
    conn.close()
    return db


def restore(zip_path, out, with_sqlite=True):
    checks, errors = verify(zip_path)
    if errors:
        raise RuntimeError("归档校验未通过，拒绝还原：" + "；".join(errors[:5]))
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        members = [n for n in z.namelist() if n != MANIFEST_NAME]
        unsafe = [n for n in members if not safe_member(n)]
        if unsafe:
            raise RuntimeError("归档含不安全路径，拒绝解包：" + ", ".join(unsafe[:3]))
        z.extractall(out, members=members)
    skus = [json.loads(x) for x in open(os.path.join(out, "data", "sku", "sku.jsonl"), encoding="utf-8") if x.strip()]
    posts = [json.loads(x) for x in open(os.path.join(out, "data", "posts", "posts.jsonl"), encoding="utf-8") if x.strip()]
    manifest = json.loads(zipfile.ZipFile(zip_path).read(MANIFEST_NAME))
    db = write_sqlite(out, skus, posts, manifest) if with_sqlite else None
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as f:
        f.write("网购避雷真 · 离线还原结果\n\n")
        f.write("来源归档：%s\n抓取时点：%s\n" %
                (os.path.basename(zip_path), manifest.get("source", {}).get("fetched_at")))
        f.write("SKU %d 条 / 帖子 %d 篇\n\n" % (len(skus), len(posts)))
        f.write("data/ 为按原结构还原的全部文件（含 664 个 by_sku 原始响应）。\n")
        if db:
            f.write("baoleizhen.db 为 SQLite：skus / posts / meta 三表，json 列保留完整字段。\n")
        f.write("图片为 cloud:// 引用，原件属私有读，不在归档内。\n")
    return checks, len(skus), len(posts), db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default=DEFAULT_ARCHIVE)
    ap.add_argument("--out", default=os.path.join(ROOT, "restored"))
    ap.add_argument("--check", action="store_true", help="只校验，不写任何文件")
    ap.add_argument("--no-sqlite", action="store_true")
    a = ap.parse_args()

    checks, errors = verify(a.archive)
    for name, ok, detail in checks:
        print("%s %-22s %s" % ("[PASS]" if ok else "[FAIL]", name, detail))
    if errors:
        print("\n校验未通过（%d 项），未执行还原：" % len(errors))
        for e in errors[:10]:
            print("  - " + e)
        sys.exit(1)
    print("\n离线校验全部通过（%d/%d）" % (len(checks), len(checks)))
    if a.check:
        return
    checks, ns, np_, db = restore(a.archive, a.out, not a.no_sqlite)
    print("已还原到 %s：SKU %d 条 / 帖子 %d 篇" % (a.out, ns, np_))
    if db:
        print("SQLite：%s" % db)


if __name__ == "__main__":
    main()
