# 数据目录说明

数据来源：微信小程序「网购避雷真」（appid `wx5bd3aa9f4674cca5`）公开只读的云函数 HTTP 访问服务。抓取口径与接口契约见 [api-contract.json](api-contract.json)，统计与校验见仓库根目录 `DATA_SUMMARY.md`。

## 文件清单

| 路径 | 内容 |
| --- | --- |
| `sku/sku_list_raw.json` | `post` 接口 `list` 的原始响应（一次返回全量 SKU，无分页） |
| `sku/sku.jsonl` | 逐条 SKU，一行一个 JSON |
| `posts/by_sku/<skuId>.json` | 对每个 SKU 调 `skuPosts` 得到的原始响应，文件名即 SKU id |
| `posts/posts.jsonl` | 全部实测/避雷帖，按帖子 id 去重，一行一个 JSON |
| `misc/*.json` | 其他公开只读 action（`liveCount` / `subList` / `merchantBrands` / `merchantPosts` / `brandApplyStatus` / `myPosts`）的响应 |
| `api-contract.json` | 接口契约、云函数与 action 清单、探测结论、隐私说明 |
| `meta.json` | 本次抓取的时间、条数、失败记录、耗时 |

## 复现 / 增量更新

```bash
python tools/fetch_cloud.py --out data --delay 0.15   # 断点续抓，已存在的 by_sku 文件默认跳过
python tools/make_summary.py                          # 重新生成摘要与完整性校验
python tests/test_fetch_api.py                         # 通用抓取器自测
```

`list` 接口不分页，每次都返回当前全量 SKU；重跑即可拿到新增内容。`--force` 可强制重抓所有 SKU 的帖子。

## 主要字段

**SKU（`sku.jsonl`）**：`id`、`name`、`brand`（前端脱敏展示）、`brandRaw`（原始品牌）、`category`、`platform`、`channel`、`anchor`（脱敏）、`anchorRaw`（原始店铺/主播）、`price`、`scoreSum`、`scoreCount`、`scoreDist`、`avgScore`、`verifiedCount`、`latestDate`。

**帖子（`posts.jsonl`）**：`id` / `_id`、`skuId`、`type`、`score`、`tag`、`title`、`content`（实测正文）、`evidenceLevel`、`realEvidence`、`claimEvidence`、`media[]`（`cloud://` 实拍/订单凭证引用）、`author`、`creditScore`、`merchantResponse`、`helpfulCount`、`agreeCount`、`doubtCount`、`createTime`、`date`、`status`、`updates[]`、`arbitration*` 等。

## 隐私与边界

- `authorUid`、`agreeUserIds`、`doubtUserIds` 等 openid/uid 类字段已做**一致性哈希脱敏**（`uid_` 前缀），同一用户在不同帖子里仍可关联，但不含明文个人标识符。
- 帖内 `media` 为微信云开发私有 `cloud://` 地址，COS 直链返回 403，本存档**只保留引用、不下载图片**。
- 只调用只读 action；`create` / `delete` / `reply` / `vote` / `like` / `report` / `orderCreate` 等写操作从未调用。
- 数据版权归原小程序及发帖用户所有，本仓库仅作资料性存档备份，并非官方数据源。
