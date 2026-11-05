#!/usr/bin/env node
// 解密 Windows 微信 4.0 小程序包 (V1MMWX)，定位目标 appid、后端域名与接口路径。
// 用法:
//   node tools/decrypt_scan.cjs
//   node tools/decrypt_scan.cjs --root "C:/.../applet/packages" --keyword 避雷 --json out.json
// 依赖: Node 内置 crypto / fs，无需 npm install。
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const argv = process.argv.slice(2);
function arg(name, def) {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : def;
}
const APPDATA = process.env.APPDATA || path.join(process.env.USERPROFILE || '', 'AppData', 'Roaming');
const defaultRoot = path.join(APPDATA, 'Tencent', 'xwechat', 'radium', 'users');
const rootArg = arg('--root', defaultRoot);
const keywordArg = arg('--keyword', '');
const jsonOut = arg('--json', '');
const KWS = ['避雷', '网购', '踩雷', '拔草', '避坑', '黑店', '曝光', '店铺', '商家', '投诉', '假货', '翻车'];
if (keywordArg) KWS.unshift(keywordArg);
const URL_RE = /https?:\/\/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{4,200}/g;
const PATH_RE = /["'`](\/[A-Za-z0-9_./-]*(?:list|query|search|detail|goods|shop|item|record|black|risk|expose)[A-Za-z0-9_./-]*)/gi;

function walk(dir, out = []) {
  let ents;
  try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return out; }
  for (const e of ents) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith('.wxapkg')) out.push(p);
  }
  return out;
}

function decrypt(appid, data) {
  if (data.subarray(0, 6).toString() !== 'V1MMWX' || data.length < 1030) return null;
  const key = crypto.pbkdf2Sync(appid, 'saltiest', 1000, 32, 'sha1');
  const decipher = crypto.createDecipheriv('aes-256-cbc', key, Buffer.from('the iv: 16 bytes'));
  decipher.setAutoPadding(false);
  const head = Buffer.concat([decipher.update(data.subarray(6, 6 + 1024)), decipher.final()]);
  for (const xk of [appid.charCodeAt(appid.length - 2) & 0xff, 0x66]) {
    const tail = Buffer.from(data.subarray(6 + 1024));
    for (let i = 0; i < tail.length; i++) tail[i] ^= xk;
    const out = Buffer.concat([head, tail]);
    out[0] = 0xbe;
    const cnt = out.length > 18 ? out.readUInt32BE(14) : 0;
    if (out[13] === 0xed && cnt > 0 && cnt < 20000) return out;
  }
  return null;
}

// 支持直接传 packages 根目录，或传 users/ 根目录（自动扫描所有用户）
const roots = [];
if (path.basename(rootArg) === 'packages') roots.push(rootArg);
else {
  let users = [];
  try { users = fs.readdirSync(rootArg); } catch (e) {}
  for (const u of users) {
    const p = path.join(rootArg, u, 'applet', 'packages');
    if (fs.existsSync(p)) roots.push(p);
  }
}
if (!roots.length) { console.error('未找到小程序包目录，请用 --root 指定 packages 路径'); process.exit(1); }

const result = {};
let total = 0, ok = 0, fail = 0;
for (const root of roots) {
  for (const file of walk(root)) {
    total++;
    const appid = path.relative(root, file).split(path.sep)[0];
    let data;
    try { data = fs.readFileSync(file); } catch (e) { continue; }
    const dec = decrypt(appid, data);
    if (!dec) { fail++; continue; }
    ok++;
    const s = dec.toString('utf8');
    const rec = result[appid] || (result[appid] = { packages: 0, keywords: new Set(), domains: new Set(), paths: new Set() });
    rec.packages++;
    KWS.forEach(k => { if (s.includes(k)) rec.keywords.add(k); });
    let m;
    URL_RE.lastIndex = 0;
    while ((m = URL_RE.exec(s)) !== null) {
      try { rec.domains.add(new URL(m[0]).hostname); } catch (e) {}
    }
    PATH_RE.lastIndex = 0;
    while ((m = PATH_RE.exec(s)) !== null) rec.paths.add(m[1]);
  }
}
console.log('扫描包数:', total, '| 解密成功:', ok, '| 失败:', fail);
const list = Object.entries(result).map(([appid, r]) => ({
  appid, packages: r.packages,
  keywords: [...r.keywords], domains: [...r.domains], paths: [...r.paths].slice(0, 80),
}));
list.sort((a, b) => b.keywords.length - a.keywords.length);
console.log('\n=== 命中关键词的小程序 ===');
for (const r of list.filter(x => x.keywords.length)) {
  console.log(' ', r.appid, '| 包数', r.packages, '|', r.keywords.join(','));
  console.log('    域名:', r.domains.slice(0, 12).join(', '));
  if (r.paths.length) console.log('    接口线索:', r.paths.slice(0, 15).join(', '));
}
if (jsonOut) {
  fs.writeFileSync(jsonOut, JSON.stringify({ scanned: total, decrypted: ok, apps: list }, null, 2));
  console.log('\n完整清单已写入', jsonOut);
}
