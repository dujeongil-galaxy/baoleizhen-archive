#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_api.py 自测：正常翻页 + 空页自动停止 + 故障注入（接口全挂必须判红）。"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "tools", "fetch_api.py")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        page = int(parse_qs(urlparse(self.path).query).get("page", ["1"])[0])
        items = ([{"id": (page - 1) * 2 + i, "name": "店铺%d" % ((page - 1) * 2 + i)}
                  for i in range(2)] if page <= 3 else [])
        body = json.dumps({"code": 0, "data": {"list": items, "total": 6}}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def run(url, out, extra=None):
    cmd = [sys.executable, TOOL, "--url", url, "--start", "1", "--end", "10",
           "--delay", "0", "--out", out] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    good_url = "http://127.0.0.1:%d/api/list?page={page}" % port

    # 好路径：3 页共 6 条，随后空页自动停止
    out = tempfile.mkdtemp(prefix="fetch_ok_")
    r = run(good_url, out)
    n = sum(1 for _ in open(os.path.join(out, "records.jsonl"), encoding="utf-8"))
    meta = json.load(open(os.path.join(out, "meta.json"), encoding="utf-8"))
    assert r.returncode == 0, r.stderr
    assert n == 6 and meta["total_records"] == 6, (n, meta)
    print("PASS 正常翻页: 6 条, meta 一致")

    # 故障注入：端口无人监听，全页失败必须判红
    bad_out = tempfile.mkdtemp(prefix="fetch_bad_")
    r2 = run("http://127.0.0.1:1/api/list?page={page}", bad_out, ["--retries", "0"])
    assert r2.returncode != 0, "接口全挂时脚本必须返回非零退出码"
    print("PASS 故障注入: 接口全挂时判红 (exit=%d)" % r2.returncode)

    # 脱敏：URL 里的 token 不能写进 meta
    secret_out = tempfile.mkdtemp(prefix="fetch_secret_")
    r3 = run(good_url + "&token=SUPERSECRET", secret_out)
    meta3 = open(os.path.join(secret_out, "meta.json"), encoding="utf-8").read()
    assert r3.returncode == 0 and "SUPERSECRET" not in meta3, meta3
    print("PASS 凭据脱敏: meta.json 不含 token 明文")
    server.shutdown()


if __name__ == "__main__":
    main()
