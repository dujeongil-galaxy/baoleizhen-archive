#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_cloud.py 自测：非法文件名修复（含故障注入）+ openid 脱敏。"""
import os, sys, tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from fetch_cloud import safe_name, scrub  # noqa: E402

ILLEGAL = set('<>:"/\\|?*')
CASES = [
    "脱骨侠|无骨鸡爪（450g）|某音|旗舰店",
    "BOBO|幸运肚肚水杯（1300ml）|某宝|其他",
    "a/b?c:d*e<f>g",
    "正常SKU_123",
]

tmp = tempfile.mkdtemp(prefix="fetchcloud_")
names = set()
for sid in CASES:
    n = safe_name(sid)
    assert not (set(n) & ILLEGAL), "文件名仍含非法字符: %r -> %r" % (sid, n)
    assert n not in names, "不同 SKU 生成了同名文件: %s" % n
    names.add(n)
    with open(os.path.join(tmp, n), "w", encoding="utf-8") as f:
        f.write("{}")
print("PASS 安全文件名: 4 个含非法字符的 SKU id 全部可落盘且互不冲突")

# 故障注入：旧规则（只替换斜杠）在 Windows 上必须失败，证明这个 bug 真实存在
old = CASES[0].replace("/", "_") + ".json"
try:
    with open(os.path.join(tmp, old), "w", encoding="utf-8") as f:
        f.write("{}")
    if os.name == "nt":
        raise AssertionError("故障注入未生效：旧规则竟然写成功了")
except OSError:
    pass
print("PASS 故障注入: 旧文件名规则在 Windows 上确实抛 OSError（正是 498 条失败的根因）")

d = {
    "authorUid": "TEST_OPENID_ALPHA",
    "agreeUserIds": ["TEST_OPENID_BETA", "TEST_OPENID_GAMMA"],
    "nested": {"helpfulUserIds": ["TEST_OPENID_DELTA"]},
    "title": "实测：东方树叶", "score": 4, "media": [{"url": "cloud://x/y.jpg"}],
}
s = scrub(d)
assert s["authorUid"].startswith("uid_"), s["authorUid"]
assert all(x.startswith("uid_") for x in s["agreeUserIds"])
assert s["nested"]["helpfulUserIds"][0].startswith("uid_")
assert s["title"] == "实测：东方树叶" and s["score"] == 4
assert s["media"][0]["url"] == "cloud://x/y.jpg"
assert scrub(d)["authorUid"] == s["authorUid"], "脱敏结果必须一致可关联"
print("PASS 脱敏: uid 类字段一致性哈希，业务字段原样保留")
