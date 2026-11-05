# CHANGELOG

记账规则：每条记录只带**已推送的真实短哈希**。文档提交无法自指，故 CHANGELOG 记录的是「上一次推送的提交」（退一拍），不在文档里写占位符或待回填字段。

## 2026-11-05 · 仓库建立 + 抓取链路落地 — `02b92e2`

- 新建公开仓库 `dujeongil-galaxy/baoleizhen-archive`（GitHub App 连接器无建仓权限，改用本机 PAT 调 REST API，详见 PITFALLS 第 1 条）。
- 新增 `tools/decrypt_scan.cjs`：解密微信 PC 4.0 的 `V1MMWX` 小程序包，提取 appid、后端域名、接口路径线索；实跑 **392 个包，解密成功 392/392**。
- 新增 `tools/fetch_api.py`：通用分页接口全量抓取，产出每页原始响应 + `records.jsonl` + `meta.json`；内置限速、重试、连续空页自动停止、URL 中 token 脱敏。
- 新增 `tests/test_fetch_api.py`：好路径（3 页 6 条）、故障注入（接口全挂必须判红）、凭据脱敏，**3 项全部通过**。
- 新增 `README.md`、`STATUS.md`、`拿数据指引.md`、`PITFALLS.md`、`.gitignore`。
- 侦察结论：本机 2 个微信缓存目录共 109 个 appid / 392 个包，关键词「避雷」0 命中 → 该小程序未在电脑微信打开过；本地无项目、无抓包、无导出文件；公开网络无 H5/API 线索。**原始业务数据尚未接入**，等待用户按《拿数据指引》补一次本地代码包或抓包。

## 2026-11-05 · 全量数据入库（阻塞解除） — `c8cb884`

- 用户按《拿数据指引》在电脑微信打开一次「网购避雷真」，新代码包 `wx5bd3aa9f4674cca5/11/__APP__.wxapkg` 落地；解密重扫命中「避雷」。
- `tools/unpack_wxapkg.cjs` 解包确认使用微信云开发：`wx.cloud.init({env:"bilei-d1g97vsxp79326658"})` + `wx.cloud.callFunction({name:"post"})`；探测到公开只读 HTTP 访问服务 `<env>.service.tcloudbase.com/post`。
- 新增 `tools/fetch_cloud.py`（断点续抓、3 并发限速、uid 脱敏、按 id 去重）、`tools/make_summary.py`、`tests/test_fetch_cloud.py`、`data/README.md`、`DATA_SUMMARY.md`。
- **全量抓取：664 条 SKU / 195 篇实测帖 / 0 失败 / 106.1 秒**，数据 2.9 MB、676 个文件；完整性校验 4/4 PASS。
- 修复首轮「498 条假失败」：SKU id 含 `|` 等 Windows 非法字符导致写盘 `Errno 13`，改用清洗 + sha1 的安全文件名；配套故障注入测试确认旧规则确实判红。
- 新增 `data/`（sku / posts / misc / api-contract / meta）、`snapshots/miniprogram/`（app-config + 14 张分类图）。
- PITFALLS 追加第 6~10 条（云开发无 http 域名、list 无分页、非法文件名、私有图片、畸形解包索引）；README / STATUS 改为完成态。
- 隐私收尾：测试夹具里的样例 openid 也换成假 ID，全仓 `grep -rE 'o[A-Za-z0-9_-]{25,}'` **0 命中**。

## 校验记录

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| Node 语法 | `node --check tools/decrypt_scan.cjs` | PASS |
| Python 编译 | `python -m py_compile tools/fetch_api.py tests/test_fetch_api.py` | PASS |
| 抓取器自测 | `python tests/test_fetch_api.py` | 3/3 PASS（含故障注入） |
| 解密实跑 | `node tools/decrypt_scan.cjs --json ...` | 392/392 解密成功 |
| 敏感信息 | 仓库内 grep 用户名 / `ghp_` / Bearer 明文 | 无命中（公开账号名除外） |
| 云函数抓取器自测 | `python tests/test_fetch_cloud.py` | 3/3 PASS（含文件名故障注入、脱敏一致性） |
| 解包实跑 | `node tools/unpack_wxapkg.cjs <包> <目录> <appid>` | 30 个文件，畸形索引优雅退出 |
| 全量抓取 | `python tools/fetch_cloud.py --delay 0.1 --workers 3` | 664/664 SKU，0 失败，106.1s |
| 完整性校验 | `python tools/make_summary.py` | 4/4 PASS（去重 / 引用完整 / 条数一致 / 无明文 openid） |
| 全仓敏感复查 | `grep -rEl 'o[A-Za-z0-9_-]{25,}' .` | 0 命中 |
