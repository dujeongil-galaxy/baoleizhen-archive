# 踩坑记录（PITFALLS）

## 1. GitHub 连接器无法建仓

`mcp__github__create_repository` 返回 `403 Resource not accessible by integration`。
GitHub App 类连接器通常只有仓库读写权限，没有个人账户的「创建仓库」权限；这不是登录失效，重连也没用。

**解法**：用本机 git 凭据里的 PAT 直接调 REST API：

```python
p = subprocess.run(["git", "credential", "fill"],
                   input="protocol=https\nhost=github.com\n\n",
                   capture_output=True, text=True)
token = dict(l.split("=", 1) for l in p.stdout.splitlines() if "=" in l)["password"]
# POST https://api.github.com/user/repos  Authorization: Bearer <token>
```

凭据由 git-credential-manager 托管，不要打印、不要写进仓库。

## 2. Windows 上 curl 调 GitHub API 无输出

`curl https://api.github.com/user` 报 `schannel: next InitializeSecurityContext failed: CRYPT_E_NO_REVOCATION_CHECK (0x80092012)`，HTTP 000，空响应。
curl 用 Windows Schannel 做证书吊销检查失败所致。

**解法**：`curl --ssl-no-revoke`，或改用 Python `urllib.request`（本仓库脚本走这条，实测 200）。注意 `git ls-remote` 是通的不代表 curl 通。

## 3. 微信 PC 4.0 小程序包是加密的

`%APPDATA%\Tencent\xwechat\radium\users\*\applet\packages\<appid>\<version>\*.wxapkg` 全部以 `V1MMWX` 开头，直接 `grep` 中文关键词永远 0 命中。

**解法**（本机 392 个包 100% 解密成功）：

1. `key = PBKDF2-HMAC-SHA1(appid, "saltiest", 1000, 32字节)`
2. `iv = "the iv: 16 bytes"`，AES-256-CBC 解密 `[6, 6+1024)`，`setAutoPadding(false)`
3. 从 `6+1024` 起的每个字节与 `appid` 倒数第二个字符的 ASCII 做异或（旧版为固定 `0x66`，两种都试）
4. 拼接后强制首字节 `0xBE`，校验偏移 13 == `0xED`、偏移 14 的文件数在合理范围
5. 解密结果即标准 wxapkg，JS 源码里的中文与 `https://` 域名均为明文

实现见 `tools/decrypt_scan.cjs`（Node 内置 crypto，无需装依赖）。

## 4. `applet.db` 打不开

`data/8/applet.db`（含小程序名称与 appid 对应关系）是 SQLCipher 加密库，用 `sqlite3` 直连会报 `file is not a database`，即使把 `-wal` 一起复制过去也一样。别在它身上浪费时间，直接从解密后的代码包里找名称与接口。

## 5. 小程序数据不能直接爬

微信小程序没有公网网页入口，数据全部通过 `wx.request` 走开发者自己的服务器。仅凭小程序名称无法推出接口域名，搜索引擎也查不到。必须先在电脑微信打开一次（留下代码包）或抓一次包，才能进入自动化抓取流程。

## 6. 用微信云开发时，扫 http 域名只会得到 0 条

「网购避雷真」解密后 `https://` 域名 **0 命中**，因为它用的是 `wx.cloud.callFunction({name:'post',data:{action:'list'}})`，请求由微信客户端代理，包里只有云环境 ID：`wx.cloud.init({env:"bilei-d1g97vsxp79326658"})`。

**解法**：拿到 env 后探测腾讯云开发 HTTP 访问服务的固定域名格式 `https://<env>.service.tcloudbase.com/<云函数名>`。本例 `/post` 返回 200 全量数据。区分信号很有用：

| 响应 | 含义 |
| --- | --- |
| `404 {"code":"INVALID_HOST"}` | 域名对、但不是 HTTP 访问服务的合法 host |
| `404 {"code":"INVALID_PATH"}` | **域名对**，只是路径不对，继续试云函数名作路径 |
| `418`（空 body） | `ap-shanghai.tcb.qcloud.la` 旧域名，不走这条 |
| `200 {"code":0,"data":{"list":[...]}}` | 找到公开只读入口 |

其它路径（`/ask`、`/member`、`/user`）都不通，说明只开放了 `post` 一个云函数。

## 7. 云函数 `list` 无分页，别写翻页逻辑

`post` 默认（或 `action=list`）一次返回全部 664 条 SKU，`page` / `pageSize` / `limit` / `offset` 参数全部被忽略，GET query 与 POST body 结果一致。写通用翻页抓取器前先验证参数是否真的生效，否则会抓 N 遍同样的数据还以为翻完了。帖子数据要另外按 SKU 调 `skuPosts`。

## 8. Windows 非法文件名造成 498 条「假失败」（血泪）

SKU 的 `id` 不是纯 ID，而是 `脱骨侠|无骨鸡爪（450g）|某音|旗舰店` 这种带 `|` 的复合字符串。直接用 `id + ".json"` 当文件名，在 Windows 上抛 `Errno 13 Permission denied`，被上层记成「接口失败」——实际上请求全都成功了，白跑 5 分钟并误判断是被限流。

**解法**：清洗 `[<>:"/\\|?*\x00-\x1f]` + 追加 `sha1(id)[:10]` 保证唯一；配套 `tests/test_fetch_cloud.py` 做**故障注入**（用旧规则故意写含 `|` 的文件，确认真的抛 OSError），确认校验能判红。排查这类问题时先看 `meta.json` 的 `errors[].error` 全文，不要凭「大量失败」就猜限流。

## 9. 实拍图 / 订单凭证是私有读，拿不到原件

帖子里的 `media[].url` 是 `cloud://<env>.<bucket>/media/xxx.jpg`。按 bucket 拼 COS 公网域名返回 `403 Forbidden`（私有读），其它 region 返回 404。存档只保留引用，并在 `data/README.md` 写明，不要假装图片已备份。

## 10. 解包索引项可能畸形

标准 wxapkg 索引是 `nameLen(4) + name + offset(4) + size(4)`，个别包会出现异常 `nameLen`，直接 `readUInt32BE` 会 `ERR_OUT_OF_RANGE` 崩掉整个解包（已有文件能写出但脚本报错）。`tools/unpack_wxapkg.cjs` 里加了边界检查，遇异常项提前结束。

## 11. 离线归档别收「记账文档」，改数据后必须重打包

归档 zip 里如果塞进 README / CHANGELOG / PITFALLS，每次「提交 → 用真实哈希回填文档」都会让二进制包变化，git 里堆一堆无意义的大文件版本，还会让「归档 = 数据时点快照」这个语义失效。所以 `build_archive.py` 只收 `data/`、`snapshots/`、`DATA_SUMMARY.md`、`data/README.md`、还原脚本与 `RESTORE.txt`；记账文档留在仓库里即可。

反过来，**改过 `data/` 或 `DATA_SUMMARY.md` 之后必须重跑 `build_archive.py`**：`ARCHIVE_MANIFEST.json` 记录的是打包那一刻的 SHA256，漏重打包会让 zip 和工作区数据不一致，`restore.py --check` 会直接判红。这条已写进 `data/README.md` 和 `RESTORE.txt`。

## 12. 哈希一致 ≠ 数据正确，故障注入要覆盖「内容级」样本

只测「篡改一个字节 → SHA256 判红」是不够的：如果有人把脏数据连同 manifest 里的哈希一起改掉，所有哈希检查都会通过。`tests/test_restore.py` 因此专门做了两个**同步重算哈希**的注入样本（明文 openid、孤立 `skuId`），确认条数 / 引用 / 隐私这类**内容级校验**独立于哈希也能判红。写校验器时这两层要分开测。

## 13. Python `bytes` 字面量里不能写中文

测试里想用 `b"正文A"` 做篡改样本，直接 `SyntaxError: bytes can only contain ASCII literal characters`。改成替换 ASCII 字段（`b"published"` → `b"publisheX"`），或用 `"中文".encode()`。另外 `py_compile` 生成的 `__pycache__/*.pyc` 会保留**修改前**的字符串字面量，全仓 `grep` 复查敏感串时要先清掉，否则旧缓存会造成误报（本轮就命中过一次 `tests/__pycache__/test_restore.cpython-313.pyc`）。
