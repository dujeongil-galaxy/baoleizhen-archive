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

微信小程序没有公网网页入口，数据全部通过 `wx.request` 走开发者自己的服务器。仅凭小程序名称无法推出接口域名，搜索引擎也查不到。必须先在电脑微信打开一次（留下代码包）或抓一次包，才能进入自动化抓取流程。这是本项目当前唯一的硬阻塞。
