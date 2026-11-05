# 避雷真 · 数据存档（baoleizhen-archive）

> 目标：在微信小程序「**网购避雷真**」（网购避雷 / 商品实测与店铺避坑）可能被下架之前，把它的全量数据完整保存到 GitHub。
>
> **状态：全量数据已入库。** 664 条 SKU 商品记录 + 195 篇实测/避雷帖（含正文、评分、证据、时间、原始品牌与店铺），0 抓取失败，完整性校验 4/4 PASS。
> 抓取过程与边界见 [STATUS.md](STATUS.md)，统计与校验见 [DATA_SUMMARY.md](DATA_SUMMARY.md)，字段说明见 [data/README.md](data/README.md)。

## 数据快照（2026-11-05 21:42 +0800）

| 指标 | 数值 |
| --- | --- |
| SKU 商品记录 | 664 |
| 实测 / 避雷帖（去重） | 195 |
| 分类 | 14（digital 227、home 108、food 80、beauty 74…） |
| 涉及真实品牌 | 139 |
| 帖子日期范围 | 2026-10-09 ~ 2026-11-05 |
| 抓取失败 | 0 / 664 |
| 数据体积 | 约 2.9 MB（676 个文件） |

## 数据怎么拿到的

1. 本机电脑微信打开一次小程序，留下加密代码包 `wx5bd3aa9f4674cca5/11/__APP__.wxapkg`；
2. 用 `tools/decrypt_scan.cjs` 解密 `V1MMWX` 包，定位到 appid 与关键词「避雷」；
3. `tools/unpack_wxapkg.cjs` 解包后发现它用微信云开发：`wx.cloud.init({env:"bilei-d1g97vsxp79326658"})` + `wx.cloud.callFunction({name:"post"})`；
4. 探测到该云函数开了 HTTP 访问服务：`https://bilei-d1g97vsxp79326658.service.tcloudbase.com/post`（公开只读，无需登录态）；
5. `list` 一次返回全量 664 条 SKU；逐 SKU 调 `skuPosts` 拿到 195 篇含正文的实测帖；
6. `tools/fetch_cloud.py` 落盘、脱敏、去重，`tools/make_summary.py` 生成摘要与校验。

完整接口契约见 [data/api-contract.json](data/api-contract.json)，踩坑记录见 [PITFALLS.md](PITFALLS.md)。

## 数据边界（重要）

- 只做资料性存档备份，数据版权归原小程序 / 原作者与发帖用户所有，**并非官方数据源**。
- 只调用**公开只读**接口；`create` / `delete` / `reply` / `vote` / `like` / `report` / 下单等写操作从未调用，不绕过任何登录鉴权。
- `authorUid`、`agreeUserIds` 等 openid/uid 字段已做**一致性哈希脱敏**（`uid_` 前缀），公开文件里无明文个人标识符。
- 帖内实拍图 / 订单凭证是私有 `cloud://` 地址（COS 直链 403），**只保留引用、不下载图片**。
- 抓取带限速、重试与并发上限（3），不对原服务施压。
- 如原作者或权利方要求下线，请通过 GitHub Issue 联系仓库所有者，会及时处理。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `data/sku/` | 664 条 SKU：原始响应 + `sku.jsonl` |
| `data/posts/` | 664 个按 SKU 的响应文件 + 195 篇帖子的 `posts.jsonl` |
| `data/misc/` | 其他公开只读 action 的响应 |
| `data/api-contract.json` / `data/meta.json` | 接口契约 / 本次抓取统计 |
| `snapshots/miniprogram/` | 小程序 `app-config.json` 与 14 张分类图 |
| `tools/decrypt_scan.cjs` | 解密并扫描本机微信 PC 小程序包，定位 appid / 域名 / 接口 |
| `tools/unpack_wxapkg.cjs` | 解密并解开单个小程序包 |
| `tools/fetch_cloud.py` | 本小程序的全量抓取器（断点续抓、并发限速、脱敏、去重） |
| `tools/fetch_api.py` | 通用分页接口抓取器（备用） |
| `tools/make_summary.py` | 生成 `DATA_SUMMARY.md` 与完整性校验 |
| `tests/` | 两个抓取器的自测，含故障注入 |
| `DATA_SUMMARY.md` / `STATUS.md` / `拿数据指引.md` | 摘要 / 进度 / 历史操作指引 |
| `CHANGELOG.md` / `PITFALLS.md` | 改动记账 / 踩坑记录 |

## 复现与增量更新

```bash
python tools/fetch_cloud.py --out data --delay 0.1 --workers 3   # 断点续抓，已存在文件默认跳过
python tools/make_summary.py                                      # 重算摘要与校验
python tests/test_fetch_api.py && python tests/test_fetch_cloud.py # 自测
```

`list` 不分页，每次返回当前全量 SKU；重跑即可拿到新增内容，`--force` 可强制重抓所有帖。

## 归档基线

- 首次内容提交：`02b92e2`（2026-11-05 20:52 +0800），已推送。
- 改动记账见 [CHANGELOG.md](CHANGELOG.md)，只记录已推送的真实提交号。
