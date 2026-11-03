/* 政治背诵小程序 - 共享逻辑（协议与网页版 static/app.js 保持一致） */
const config = require('../config');

/* 后端地址：开发者工具里走 127.0.0.1；真机走电脑局域网 IP */
function base() {
  let platform = '';
  try {
    const d = wx.getDeviceInfo ? wx.getDeviceInfo() : wx.getSystemInfoSync();
    platform = d.platform || '';
  } catch (e) { /* 旧基础库兜底 */ }
  const host = platform === 'devtools' ? '127.0.0.1' : config.LAN_IP;
  return 'http://' + host + ':' + config.PORT;
}

function request(path, opts) {
  opts = opts || {};
  return new Promise((resolve, reject) => {
    wx.request({
      url: base() + path,
      method: opts.method || 'GET',
      data: opts.data,
      header: { 'content-type': 'application/json' },
      timeout: 15000,
      success(res) {
        const j = res.data;
        if (typeof j === 'string') { reject(new Error('响应不是 JSON')); return; }
        if (res.statusCode >= 400 && !j) { reject(new Error('HTTP ' + res.statusCode)); return; }
        resolve(j);
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || '网络请求失败'));
      },
    });
  });
}

const get = (path) => request(path);
const post = (path, body) => request(path, { method: 'POST', data: body || {} });

/* 上传文件（wx.uploadFile），字段名与网页版一致：截图 file/image，文档 file */
function upload(apiPath, filePath, name, extraForm) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: base() + apiPath,
      filePath: filePath,
      name: name || 'file',
      formData: extraForm || {},
      timeout: 60000,
      success(res) {
        let j;
        try { j = JSON.parse(res.data); }
        catch (e) { reject(new Error('识别接口返回异常（HTTP ' + res.statusCode + '）')); return; }
        resolve(j);
      },
      fail(err) { reject(new Error((err && err.errMsg) || '上传失败')); },
    });
  });
}

function toast(title, ok) {
  wx.showToast({
    title: String(title || '').slice(0, 20),
    icon: ok === false ? 'none' : 'none',   // 统一 none：消息可能超 7 字
    duration: 2000,
  });
}

function failToast(err) {
  const msg = (err && err.message) ? err.message : String(err);
  toast(msg, false);
}

/* ================= 挖空标记 ================= */
/* {{词}} 普通挖空；{{!词}} 高频红色挖空 → [{t:'txt'|'blank', s, hot}] */
function parseMarks(text) {
  const segs = [];
  const re = /\{\{(!?)([^{}]*)\}\}/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) segs.push({ t: 'txt', s: text.slice(last, m.index) });
    segs.push({ t: 'blank', s: m[2], hot: m[1] === '!' });
    last = m.index + m[0].length;
  }
  if (last < text.length) segs.push({ t: 'txt', s: text.slice(last) });
  return segs;
}

/* 文本 → 按行分段的渲染数据（WXML 里 wx:for 用；给挖空块分配唯一 key 方便 setData）
 * 返回 [{segs:[{t,s,hot,key,w,inp}]}] */
let KEY = 0;
function prepareInto(obj, text) {
  const lines = String(text || '').split('\n').map((line, ri) => {
    const segs = parseMarks(line).map((seg, si) => {
      seg.key = 'k' + (++KEY);
      if (seg.t === 'blank') {
        seg.w = Math.max(seg.s.length + 2, 4);
        seg.good = 0;
      } else {
        // 替换 wx:for 内惊险字符；纯文本即可
      }
      return seg;
    });
    return { segs: segs, ri: ri };
  });
  obj.lines = lines;
  return obj;
}
function hasBlank(text) { return /\{\{!?[^{}]*\}\}/.test(text || ''); }
function countBlanks(text) { return ((text || '').match(/\{\{!?[^{}]*\}\}/g) || []).length; }
function plainText(t) { return (t || '').replace(/\{\{(!?)([^{}]*)\}\}/g, '$2'); }
function normalizeAnswer(s) {
  return (s || '').replace(/[\s，。：；、·,.:;()（）"'“”‘’【】\-—！!？?]/g, '');
}

/* 草稿识别方式 → 中文标签（对齐网页版 modeLabel） */
function modeLabel(m) {
  if (m === 'win') return '兜底识别';
  if (m === 'recover') return '忽略恢复';
  if (m === 'docx') return 'Word解析';
  if (m === 'txt') return '纯文本';
  if ((m || '').indexOf('pdf') === 0) return 'PDF解析';
  return 'AI识别';
}

/* 自动挖空：候选高频词包 {{!词}}，跳过已包区域（对齐网页版 autoMark） */
const MARK_STOP = new Set(['高频', '考点', '重点', '第一章', '第二章', '第三章']);
function autoMark(text, candidates) {
  let t = text;
  for (const c of (candidates || []).slice().sort((a, b) => b.length - a.length)) {
    if (!c || c.length < 2 || MARK_STOP.has(c)) continue;
    if (t.includes('{{' + c + '}}') || t.includes('{{!' + c + '}}')) continue;
    const spans = [];
    const re = /\{\{!?[^{}]*\}\}/g; let m;
    while ((m = re.exec(t))) spans.push([m.index, m.index + m[0].length]);
    let at = -1;
    for (let k = 0; k + c.length <= t.length; k++) {
      if (!t.startsWith(c, k)) continue;
      if (spans.some(([a, b]) => k < b && k + c.length > a)) continue;
      at = k; break;
    }
    if (at >= 0) t = t.slice(0, at) + '{{!' + c + '}}' + t.slice(at + c.length);
  }
  return t;
}

const SUBJECTS = ['毛中特', '马原', '史纲', '思修', '时政', '常识', '其他'];

module.exports = {
  base, request, post, get, upload, toast, failToast,
  parseMarks, prepareInto, hasBlank, countBlanks, plainText, normalizeAnswer,
  modeLabel, autoMark, SUBJECTS,
};
