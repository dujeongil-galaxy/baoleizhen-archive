#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「网购避雷真」全量数据抓取器（微信云开发 HTTP 访问服务 /post）。

产出:
  data/sku/sku_list_raw.json      664 条 SKU 聚合原始响应
  data/sku/sku.jsonl             逐条 SKU
  data/posts/by_sku/<skuId>.json 每个 SKU 下的实测帖原始响应（脱敏后）
  data/posts/posts.jsonl         全量实测帖（按 id 去重、脱敏后）
  data/meta.json                 抓取口径、统计与校验

用法: python tools/fetch_cloud.py [--out data] [--delay 0.15] [--limit 0]
支持断点续抓：已存在的 by_sku 文件默认跳过，--force 可重抓。

合规: 只访问小程序自身公开的数据接口；对 openid/uid 类字段做一致性哈希脱敏。
"""
import argparse, concurrent.futures, hashlib, json, os, re, ssl, sys, time, urllib.error, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://bilei-d1g97vsxp79326658.service.tcloudbase.com/post"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 个人标识符字段：保留结构、值做一致性哈希，避免公开仓库出现明文 openid
SENSITIVE = {"authoruid", "openid", "_openid", "uid", "userid", "agreeuserids",
             "doubtuserids", "helpfuluserids", "followuserids", "voterids", "userids"}


def scrub(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE:
                if isinstance(v, list):
                    out[k] = [pseudonym(x) for x in v]
                elif isinstance(v, str) and v:
                    out[k] = pseudonym(v)
                else:
                    out[k] = v
            else:
                out[k] = scrub(v)
        return out
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def pseudonym(s):
    return "uid_" + hashlib.sha256(("baoleizhen:" + str(s)).encode()).hexdigest()[:16]


def safe_name(sid):
    """SKU id 里含 | ? : 等 Windows 非法字符，必须清洗后落盘；加哈希保证唯一。"""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(sid))
    return s[:70] + "_" + hashlib.sha1(str(sid).encode("utf-8")).hexdigest()[:10] + ".json"


def call(params, timeout=20, retries=2):
    req = urllib.request.Request(
        BASE, data=json.dumps(params, ensure_ascii=False).encode("utf-8"),
        headers={"User-Agent": "baoleizhen-archive/1.0",
                 "Content-Type": "application/json", "Accept": "application/json"},
        method="POST")
    last = None
    for i in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(0.6 * (i + 1))
    raise RuntimeError(str(last))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个 SKU（调试用），0=全量")
    ap.add_argument("--workers", type=int, default=3, help="并发请求数（礼貌抓取，勿调过高）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    started = time.time()

    # 1) SKU 全量
    sku_file = os.path.join(out, "sku", "sku_list_raw.json")
    if os.path.exists(sku_file) and not args.force:
        raw = json.load(open(sku_file, encoding="utf-8"))
    else:
        raw = call({"action": "list"})
        write_json(sku_file, scrub(raw))
    skus = (raw.get("data") or {}).get("list") or []
    with open(os.path.join(out, "sku", "sku.jsonl"), "w", encoding="utf-8") as f:
        for r in skus:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("SKU 全量: %d 条" % len(skus), flush=True)

    # 2) 逐 SKU 抓实测帖
    by_sku = os.path.join(out, "posts", "by_sku")
    os.makedirs(by_sku, exist_ok=True)
    todo = skus[:args.limit] if args.limit else skus
    errors, fetched, total_posts = [], 0, 0

    def job(sku):
        sid = sku.get("id") or ""
        dest = os.path.join(by_sku, safe_name(sid))
        if os.path.exists(dest) and not args.force:
            try:
                return "skip", sid, json.load(open(dest, encoding="utf-8"))
            except Exception:
                pass
        try:
            d = scrub(call({"action": "skuPosts", "skuId": sid}))
            write_json(dest, d)
            time.sleep(args.delay)
            return "ok", sid, d
        except Exception as e:  # noqa: BLE001
            return "err", sid, str(e)[:200]

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (status, sid, d) in enumerate(pool.map(job, todo), 1):
            if status == "ok":
                fetched += 1
            elif status == "err":
                errors.append({"skuId": sid, "error": str(d)})
                d = None
            if isinstance(d, dict) and d.get("code") == 0:
                total_posts += len((d.get("data") or {}).get("list") or [])
            if i % 50 == 0 or i == len(todo):
                print("进度 %d/%d 新抓 %d 累计帖 %d 失败 %d" %
                      (i, len(todo), fetched, total_posts, len(errors)), flush=True)

    # 3) 汇总去重
    posts, seen = [], set()
    for fn in sorted(os.listdir(by_sku)):
        if not fn.endswith(".json"):
            continue
        d = json.load(open(os.path.join(by_sku, fn), encoding="utf-8"))
        if d.get("code") != 0:
            continue
        for p in (d.get("data") or {}).get("list") or []:
            pid = p.get("id") or p.get("_id") or ""
            if pid and pid in seen:
                continue
            seen.add(pid)
            posts.append(p)
    jsonl = os.path.join(out, "posts", "posts.jsonl")
    os.makedirs(os.path.dirname(jsonl), exist_ok=True)
    with open(jsonl, "w", encoding="utf-8") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    meta = {
        "source": "微信小程序「网购避雷真」公开云函数 HTTP 访问服务",
        "endpoint": BASE,
        "appid": "wx5bd3aa9f4674cca5",
        "cloud_env": "bilei-d1g97vsxp79326658",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sku_count": len(skus),
        "sku_with_posts_files": len([x for x in os.listdir(by_sku) if x.endswith('.json')]),
        "post_count": len(posts),
        "new_requests": fetched,
        "errors": errors,
        "privacy": "openid/uid 类字段已做一致性哈希脱敏（uid_ 前缀），其余字段保持原样",
        "duration_seconds": round(time.time() - started, 1),
    }
    write_json(os.path.join(out, "meta.json"), meta)
    print("完成: SKU %d / 实测帖 %d / 失败 %d / 耗时 %ss" %
          (len(skus), len(posts), len(errors), meta["duration_seconds"]), flush=True)
    return 1 if errors and not posts else 0


if __name__ == "__main__":
    sys.exit(main())
