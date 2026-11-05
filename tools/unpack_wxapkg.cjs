#!/usr/bin/env node
// 解密并解开单个微信 PC 小程序包 (V1MMWX) -> 目录
// 用法: node tools/unpack_wxapkg.cjs <app.wxapkg> <输出目录> [appid]
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const src = process.argv[2];
const out = process.argv[3];
const appid = process.argv[4] || path.basename(path.dirname(path.dirname(src)));
if (!src || !out) { console.error('用法: node unpack_wxapkg.cjs <包> <输出目录> [appid]'); process.exit(1); }

function decrypt(data) {
  if (data.subarray(0, 6).toString() !== 'V1MMWX') return data; // 已是明文包
  const key = crypto.pbkdf2Sync(appid, 'saltiest', 1000, 32, 'sha1');
  const d = crypto.createDecipheriv('aes-256-cbc', key, Buffer.from('the iv: 16 bytes'));
  d.setAutoPadding(false);
  const head = Buffer.concat([d.update(data.subarray(6, 6 + 1024)), d.final()]);
  for (const xk of [appid.charCodeAt(appid.length - 2) & 0xff, 0x66]) {
    const tail = Buffer.from(data.subarray(6 + 1024));
    for (let i = 0; i < tail.length; i++) tail[i] ^= xk;
    const buf = Buffer.concat([head, tail]);
    buf[0] = 0xbe;
    if (buf[13] === 0xed) return buf;
  }
  throw new Error('解密失败');
}

const buf = decrypt(fs.readFileSync(src));
if (buf[0] !== 0xbe || buf[13] !== 0xed) throw new Error('不是有效 wxapkg: ' + buf.subarray(0, 16).toString('hex'));
const idxLen = buf.readUInt32BE(5);
const count = buf.readUInt32BE(14);
const bodyStart = 14 + idxLen;
let p = 18, written = 0, skipped = 0;
fs.mkdirSync(out, { recursive: true });
for (let i = 0; i < count; i++) {
  // 微信包偶见畸形索引项，缺了这道检查会 ERR_OUT_OF_RANGE 崩掉整个解包
  if (p + 4 > buf.length) break;
  const nameLen = buf.readUInt32BE(p); p += 4;
  if (nameLen <= 0 || nameLen > 1024 || p + nameLen + 8 > buf.length) {
    console.error('索引项异常，提前结束于第 %d 项 (nameLen=%d)', i, nameLen);
    break;
  }
  const name = buf.toString('utf8', p, p + nameLen); p += nameLen;
  const off = buf.readUInt32BE(p); p += 4;
  const size = buf.readUInt32BE(p); p += 4;
  // 微信包里偶有控制字符/非法文件名，统一清洗，避免 Windows 下 EPERM
  const rel = name.replace(/[\x00-\x1f<>:"|?*]/g, '_')
                  .replace(/^\/+/, '').replace(/\.\./g, '__');
  const dest = path.join(out, rel);
  try {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, buf.subarray(bodyStart + off, bodyStart + off + size));
    written++;
  } catch (e) {
    skipped++;
    console.error('跳过文件', JSON.stringify(name), e.code);
  }
}
console.log('解包完成: 文件数 %d, 跳过 %d, 输出 %s, indexLen=%d', written, skipped, out, idxLen);
