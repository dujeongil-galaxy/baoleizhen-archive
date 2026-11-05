#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用分页接口全量抓取器：拿到小程序后端接口后，一键翻页落盘。

用法示例:
  python tools/fetch_api.py --url "https://api.example.com/list?page={page}" \
      --start 1 --end 500 --delay 0.2 --out data/ \
      --header "X-App-Id: xxx" --header "Authorization: Bearer xxx"

占位符: {page} 页码 / {offset} 偏移量 / {limit} 每页条数，三者会在每页自动替换。
产出: <out>/pages/page_0001.json (原始响应)、<out>/records.jsonl、<out>/meta.json
合规: 只请求你有权访问的公开接口；不要用它绕过鉴权或抓取个人信息。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

LIST_KEYS = ("list", "records", "items", "rows", "data", "result", "results", "content", "recordsList")
SECRET_RE = re.compile(r"((?:token|key|secret|signature|access_token|openid)=)[^&\s]+", re.I)


def extract_records(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in LIST_KEYS:
            if k in obj:
                got = extract_records(obj[k])
                if got:
                    return got
    return []


def get(url, headers, timeout, retries):
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - 网络错误统一重试
            last = e
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("请求失败: %s" % last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="接口 URL 模板，含 {page} / {offset} / {limit}")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=200, help="最大页码（含）")
    ap.add_argument("--step", type=int, default=20, help="每页条数，用于 {offset}/{limit}")
    ap.add_argument("--delay", type=float, default=0.2, help="每页间隔秒数，礼貌抓取")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--empty-stop", type=int, default=3, help="连续空页/重复页数达到后自动停止")
    ap.add_argument("--header", action="append", default=[], help="请求头，可重复，如 'Key: Value'")
    ap.add_argument("--out", default="data")
    ap.add_argument("--prefix", default="", help="输出文件名前缀，多接口抓取时区分用")
    args = ap.parse_args()

    headers = {"User-Agent": "baoleizhen-archive/1.0 (+data preservation)",
               "Accept": "application/json, text/plain, */*"}
    for h in args.header:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

    out = os.path.abspath(args.out)
    pages_dir = os.path.join(out, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    prefix = args.prefix + "_" if args.prefix else ""
    jsonl_path = os.path.join(out, prefix + "records.jsonl")
    meta_path = os.path.join(out, prefix + "meta.json")

    seen_hash, empty_streak, total, errors, last_hash = set(), 0, 0, [], None
    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for page in range(args.start, args.end + 1):
            offset = (page - args.start) * args.step
            url = args.url.format(page=page, offset=offset, limit=args.step)
            try:
                text = get(url, headers, args.timeout, args.retries)
            except Exception as e:  # noqa: BLE001
                errors.append({"page": page, "error": str(e)})
                print("[ERROR] page=%d %s" % (page, e), file=sys.stderr)
                if len(errors) >= 3:
                    print("连续失败过多，终止。", file=sys.stderr)
                    break
                continue

            with open(os.path.join(pages_dir, "%spage_%04d.json" % (prefix, page)),
                      "w", encoding="utf-8") as pf:
                pf.write(text)
            h = hashlib.sha256(text.encode()).hexdigest()
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                obj = {}
            records = extract_records(obj)
            for rec in records:
                jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total += len(records)
            print("page=%d records=%d total=%d" % (page, len(records), total))

            duplicate = h == last_hash or h in seen_hash
            seen_hash.add(h)
            last_hash = h
            if not records or duplicate:
                empty_streak += 1
                if empty_streak >= args.empty_stop:
                    print("连续 %d 页无新数据，判定已到末尾。" % empty_streak)
                    break
            else:
                empty_streak = 0
            time.sleep(args.delay)

    meta = {
        "url_template": SECRET_RE.sub(r"\1***", args.url),
        "page_range": [args.start, args.end],
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_records": total,
        "errors": errors,
        "note": "原始响应见 pages/，逐条数据见 records.jsonl；仅用于资料存档。",
    }
    with open(meta_path, "w", encoding="utf-8") as mf:
        json.dump(meta, mf, ensure_ascii=False, indent=2)
    print("完成：%d 条，输出 %s" % (total, out))
    return 1 if errors and total == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
