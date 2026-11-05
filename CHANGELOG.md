# CHANGELOG

记账规则：每条记录只带**已推送的真实短哈希**。文档提交无法自指，故 CHANGELOG 记录的是「上一次推送的提交」（退一拍），不在文档里写占位符或待回填字段。

## 2026-11-05 · 仓库建立 + 抓取链路落地 — `02b92e2`

- 新建公开仓库 `dujeongil-galaxy/baoleizhen-archive`（GitHub App 连接器无建仓权限，改用本机 PAT 调 REST API，详见 PITFALLS 第 1 条）。
- 新增 `tools/decrypt_scan.cjs`：解密微信 PC 4.0 的 `V1MMWX` 小程序包，提取 appid、后端域名、接口路径线索；实跑 **392 个包，解密成功 392/392**。
- 新增 `tools/fetch_api.py`：通用分页接口全量抓取，产出每页原始响应 + `records.jsonl` + `meta.json`；内置限速、重试、连续空页自动停止、URL 中 token 脱敏。
- 新增 `tests/test_fetch_api.py`：好路径（3 页 6 条）、故障注入（接口全挂必须判红）、凭据脱敏，**3 项全部通过**。
- 新增 `README.md`、`STATUS.md`、`拿数据指引.md`、`PITFALLS.md`、`.gitignore`。
- 侦察结论：本机 2 个微信缓存目录共 109 个 appid / 392 个包，关键词「避雷」0 命中 → 该小程序未在电脑微信打开过；本地无项目、无抓包、无导出文件；公开网络无 H5/API 线索。**原始业务数据尚未接入**，等待用户按《拿数据指引》补一次本地代码包或抓包。

## 校验记录

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| Node 语法 | `node --check tools/decrypt_scan.cjs` | PASS |
| Python 编译 | `python -m py_compile tools/fetch_api.py tests/test_fetch_api.py` | PASS |
| 抓取器自测 | `python tests/test_fetch_api.py` | 3/3 PASS（含故障注入） |
| 解密实跑 | `node tools/decrypt_scan.cjs --json ...` | 392/392 解密成功 |
| 敏感信息 | 仓库内 grep 用户名 / `ghp_` / Bearer 明文 | 无命中（公开账号名除外） |
