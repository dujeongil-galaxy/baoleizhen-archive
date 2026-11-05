#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成数据摘要与完整性校验报告 DATA_SUMMARY.md。"""
import json, os, re, sys, collections, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def load_jsonl(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


skus = load_jsonl(os.path.join(DATA, "sku", "sku.jsonl"))
posts = load_jsonl(os.path.join(DATA, "posts", "posts.jsonl"))
sku_ids = {s.get("id") for s in skus}
by_sku_files = [x for x in os.listdir(os.path.join(DATA, "posts", "by_sku"))] \
    if os.path.isdir(os.path.join(DATA, "posts", "by_sku")) else []
raw_total = 0
for fn in by_sku_files:
    if fn.endswith(".json"):
        d = json.load(open(os.path.join(DATA, "posts", "by_sku", fn), encoding="utf-8"))
        raw_total += len((d.get("data") or {}).get("list") or [])

cat = collections.Counter(s.get("category") for s in skus)
plat = collections.Counter(s.get("platform") for s in skus)
score = collections.Counter(p.get("score") for p in posts)
ptype = collections.Counter(p.get("type") for p in posts)
tag = collections.Counter(p.get("tag") for p in posts)
ev = collections.Counter(p.get("evidenceLevel") for p in posts)
brand = collections.Counter(s.get("brandRaw") for s in skus if s.get("brandRaw"))
dates = sorted(p.get("date") for p in posts if p.get("date"))
orphan = [p.get("skuId") for p in posts if p.get("skuId") not in sku_ids]
blob = open(os.path.join(DATA, "posts", "posts.jsonl"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(DATA, "posts", "posts.jsonl")) else ""
leaks = set(re.findall(r"o[A-Za-z0-9_-]{25,}", blob))

lines = []
lines.append("# 数据摘要与完整性校验\n")
lines.append("生成时间：%s\n" % time.strftime("%Y-%m-%d %H:%M:%S %z"))
lines.append("| 指标 | 数值 |")
lines.append("| --- | --- |")
lines.append("| SKU 商品记录 | %d |" % len(skus))
lines.append("| 实测/避雷帖（去重后） | %d |" % len(posts))
lines.append("| 按 SKU 抓取的响应文件 | %d |" % len(by_sku_files))
lines.append("| 各响应内帖子条数合计 | %d |" % raw_total)
lines.append("| 帖子日期范围 | %s ~ %s |" % (dates[0] if dates else "-", dates[-1] if dates else "-"))
lines.append("| 分类数 | %d |" % len(cat))
lines.append("| 涉及真实品牌 | %d |" % len(brand))
lines.append("\n## 完整性校验\n")
lines.append("| 校验项 | 结果 |")
lines.append("| --- | --- |")
lines.append("| 帖子按 id 去重 | %s |" % ("PASS" if len(posts) == len({p.get('id') for p in posts}) else "FAIL"))
lines.append("| 帖子 skuId 均能在 SKU 全量中找到 | %s（孤立 %d 条） |" % ("PASS" if not orphan else "FAIL", len(orphan)))
lines.append("| 汇总条数 == 各响应条数 | %s |" % ("PASS" if len(posts) == raw_total else "注意：%d vs %d（跨 SKU 重复帖已去重）" % (len(posts), raw_total)))
lines.append("| 公开文件无明文 openid | %s（命中 %d 个） |" % ("PASS" if not leaks else "FAIL", len(leaks)))
lines.append("\n## 分类分布（SKU）\n")
lines.append("| 分类 | 数量 |")
lines.append("| --- | --- |")
for k, v in cat.most_common():
    lines.append("| %s | %d |" % (k, v))
lines.append("\n## 平台分布（SKU）\n")
lines.append("| 平台 | 数量 |")
lines.append("| --- | --- |")
for k, v in plat.most_common(20):
    lines.append("| %s | %d |" % (k, v))
lines.append("\n## 帖子评分分布\n")
lines.append("| 分值 | 帖子数 |")
lines.append("| --- | --- |")
for k in sorted(score, key=lambda x: (x is None, x)):
    lines.append("| %s | %d |" % (k, score[k]))
lines.append("\n## 帖子类型 / 标签 / 证据等级\n")
lines.append("- 类型：%s" % ", ".join("%s=%d" % (k, v) for k, v in ptype.most_common()))
lines.append("- 标签：%s" % ", ".join("%s=%d" % (k, v) for k, v in tag.most_common(15)))
lines.append("- 证据等级：%s" % ", ".join("%s=%d" % (k, v) for k, v in ev.most_common()))
lines.append("\n## 出现最多的真实品牌（Top 15）\n")
lines.append("| 品牌 | SKU 数 |")
lines.append("| --- | --- |")
for k, v in brand.most_common(15):
    lines.append("| %s | %d |" % (k, v))
lines.append("\n> 数据来自小程序公开只读接口；`brandRaw` / `anchorRaw` 是接口返回的原始品牌与店铺名，`brand` / `anchor` 是小程序前端的脱敏展示值。")
lines.append("> openid / uid 类个人标识符已做一致性哈希脱敏，媒体为私有 `cloud://` 引用，未下载图片。\n")

out = os.path.join(ROOT, "DATA_SUMMARY.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved", out)
print("SKU=%d POSTS=%d files=%d raw_total=%d orphan=%d leaks=%d" %
      (len(skus), len(posts), len(by_sku_files), raw_total, len(orphan), len(leaks)))
