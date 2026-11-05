#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线归档 / 还原自测：好路径 + 6 类故障注入，确认校验真的会判红。

运行：python tests/test_restore.py
"""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)
import build_archive as B  # noqa: E402
import restore as R  # noqa: E402

MANIFEST = R.MANIFEST_NAME


def write(path, obj, raw=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if raw else json.dumps(obj, ensure_ascii=False, indent=2))


def jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def fixture(root):
    """造一个小而真实的归档源目录。"""
    skus = [
        {"id": "sku-1", "name": "测试商品A", "category": "food", "brandRaw": "品牌甲", "platform": "某多", "price": 12.5, "avgScore": 4.2, "scoreCount": 3},
        {"id": "sku-2", "name": "测试商品B", "category": "home", "brandRaw": "品牌乙", "platform": "某宝", "price": 88.0, "avgScore": 2.1, "scoreCount": 7},
        {"id": "sku-3", "name": "测试商品C", "category": "digital", "brandRaw": "品牌丙", "platform": "某音", "price": 299.0, "avgScore": 3.0, "scoreCount": 1},
    ]
    posts = [
        {"id": "p-1", "skuId": "sku-1", "type": "real", "score": 5, "title": "实测不错", "date": "2026-10-09", "status": "published", "content": "正文A", "authorUid": "uid_abc123"},
        {"id": "p-2", "skuId": "sku-2", "type": "real", "score": 1, "title": "踩雷了", "date": "2026-11-05", "status": "published", "content": "正文B", "authorUid": "uid_def456"},
    ]
    write(os.path.join(root, "data", "meta.json"), {
        "appid": "wxTEST", "cloud_env": "env-test",
        "fetched_at": "2026-11-05T21:42:19+0800", "sku_count": 3, "post_count": 2,
    })
    jsonl(os.path.join(root, "data", "sku", "sku.jsonl"), skus)
    write(os.path.join(root, "data", "sku", "sku_list_raw.json"), {"code": 0, "data": {"list": skus}})
    jsonl(os.path.join(root, "data", "posts", "posts.jsonl"), posts)
    write(os.path.join(root, "data", "posts", "by_sku", "sku-1.json"), {"code": 0, "data": {"list": [posts[0]]}})
    write(os.path.join(root, "data", "api-contract.json"), {"endpoint": "https://example.invalid/post"})
    write(os.path.join(root, "data", "misc", "liveCount.json"), {"code": 0, "data": {"count": 2}})
    write(os.path.join(root, "snapshots", "miniprogram", "app-config.json"), {"pages": []})
    write(os.path.join(root, "DATA_SUMMARY.md"), "# 摘要\n", raw=True)
    write(os.path.join(root, "README.md"), "# 测试仓库\n", raw=True)
    return skus, posts


def rewrite(src, dst, repl=None, drop=(), extra=None, patch=None, resync=()):
    """按注入需求重写 zip；resync 里的文件会同步更新 manifest 的 sha256/size。"""
    repl, extra = repl or {}, extra or {}
    with zipfile.ZipFile(src) as z:
        items = {n: z.read(n) for n in z.namelist()}
    for n, b in repl.items():
        items[n] = b
    for n, b in extra.items():
        items[n] = b
    for n in drop:
        items.pop(n, None)
    m = json.loads(items[MANIFEST])
    for e in m["files"]:
        if e["path"] in resync and e["path"] in items:
            b = items[e["path"]]
            e["sha256"] = hashlib.sha256(b).hexdigest()
            e["size"] = len(b)
    if patch:
        patch(m)
    items[MANIFEST] = json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in items.items():
            z.writestr(n, b)
    return dst


def failed_names(zip_path):
    checks, errors = R.verify(zip_path)
    return {n for n, ok, _ in checks if not ok}, errors


def expect(label, cond, detail=""):
    print("%s %-38s %s" % ("[PASS]" if cond else "[FAIL]", label, detail))
    if not cond:
        FAILURES.append(label)


FAILURES = []


def main():
    tmp = tempfile.mkdtemp(prefix="blz-restore-")
    try:
        root = os.path.join(tmp, "repo")
        skus, posts = fixture(root)
        good = os.path.join(tmp, "good.zip")
        m = B.build(root, good)
        expect("构建归档：文件数/条数", m["counts"]["files"] >= 9 and
               m["counts"]["sku"] == 3 and m["counts"]["posts"] == 2,
               "%s" % m["counts"])

        checks, errors = R.verify(good)
        expect("好路径：离线校验全绿", not errors and len(checks) >= 12,
               "%d 项检查" % len(checks))

        out = os.path.join(tmp, "restored")
        _, ns, np_, db = R.restore(good, out)
        conn = sqlite3.connect(db)
        n1 = conn.execute("SELECT COUNT(*) FROM skus").fetchone()[0]
        n2 = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        conn.close()
        expect("还原：文件 + SQLite 行数", ns == 3 and np_ == 2 and n1 == 3 and n2 == 2 and
               os.path.isfile(os.path.join(out, "README.txt")),
               "sku=%d post=%d" % (n1, n2))

        # 故障 1：篡改内容但不动 manifest → 必须被 SHA256 抓住
        tampered = open(os.path.join(root, "data", "posts", "posts.jsonl"), "rb").read()
        tampered = tampered.replace(b"published", b"publisheX")
        bad = rewrite(good, os.path.join(tmp, "tampered.zip"),
                      repl={"data/posts/posts.jsonl": tampered})
        names, _ = failed_names(bad)
        expect("故障注入1：内容篡改判红", "逐文件 SHA256" in names, str(sorted(names)))

        # 故障 2：删文件但 manifest 仍登记
        bad2 = rewrite(good, os.path.join(tmp, "missing.zip"), drop=("data/misc/liveCount.json",))
        names, _ = failed_names(bad2)
        expect("故障注入2：文件缺失判红", "文件清单齐全" in names, str(sorted(names)))

        # 故障 3：塞入未登记文件
        bad3 = rewrite(good, os.path.join(tmp, "extra.zip"), extra={"evil.txt": b"x"})
        names, _ = failed_names(bad3)
        expect("故障注入3：未登记文件判红", "无未登记文件" in names, str(sorted(names)))

        # 故障 4：清单条数写错
        bad4 = rewrite(good, os.path.join(tmp, "count.zip"),
                       patch=lambda mm: mm["counts"].update({"posts": 999}))
        names, _ = failed_names(bad4)
        expect("故障注入4：条数不符判红", "帖子条数一致" in names, str(sorted(names)))

        # 故障 5：内容里塞明文 openid，且同步哈希 → 证明内容级校验独立于哈希
        leaked = [dict(p) for p in posts]
        # 拼装而非字面量：让源码本身不出现明文 openid 样式串（全仓 grep 会扫），
        # 但运行时仍能造出匹配 OPENID_RE 的真实故障样本。
        leaked[0]["authorUid"] = "o" + "CKLnxQfwM4tvtI0ZWztqNZLCgx" + "U"
        payload = ("\n".join(json.dumps(x, ensure_ascii=False) for x in leaked) + "\n").encode("utf-8")
        bad5 = rewrite(good, os.path.join(tmp, "leak.zip"),
                       repl={"data/posts/posts.jsonl": payload},
                       resync=("data/posts/posts.jsonl",))
        names, _ = failed_names(bad5)
        expect("故障注入5：明文 openid 判红", "无明文 openid" in names and
               "逐文件 SHA256" not in names, str(sorted(names)))

        # 故障 6：孤立 skuId，同样同步哈希
        orphan = [dict(p) for p in posts]
        orphan[1]["skuId"] = "sku-NOT-EXIST"
        payload6 = ("\n".join(json.dumps(x, ensure_ascii=False) for x in orphan) + "\n").encode("utf-8")
        bad6 = rewrite(good, os.path.join(tmp, "orphan.zip"),
                       repl={"data/posts/posts.jsonl": payload6},
                       resync=("data/posts/posts.jsonl",))
        names, _ = failed_names(bad6)
        expect("故障注入6：孤立引用判红", "帖子 SKU 引用完整" in names, str(sorted(names)))

        # 坏归档必须拒绝还原
        try:
            R.restore(bad, os.path.join(tmp, "should-not-exist"))
            ok = False
        except RuntimeError:
            ok = not os.path.exists(os.path.join(tmp, "should-not-exist"))
        expect("坏归档拒绝还原", ok)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n结果：%s，失败 %d 项" % ("全部通过" if not FAILURES else "存在失败", len(FAILURES)))
    if FAILURES:
        for x in FAILURES:
            print("  - " + x)
        sys.exit(1)


if __name__ == "__main__":
    main()
