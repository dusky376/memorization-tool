/* 政治助手 - 共享逻辑 */
const SUBJECTS = ['毛中特', '马原', '史纲', '思修', '时政', '常识', '其他'];

/* ---------- 导航骨架（页面顶栏 + 手机底部导航） ---------- */
const PAGES = [
  ['/', 'recite', '📖', '背诵'],
  ['/add', 'add', '📷', '录入'],
  ['/arrange', 'arrange', '📥', '整理'],
  ['/manage', 'manage', '🗂', '管理'],
];
function mountChrome(active) {
  const t = document.getElementById('chromeTop');
  if (t) t.innerHTML = `<header class="appbar"><div class="abin">
    <a class="logo" href="/">📘</a><b class="name">政治背诵</b>
    <nav class="topnav">${PAGES.map(([u, k, , label]) =>
      `<a class="${k === active ? 'on' : ''}" href="${u}">${label}</a>`).join('')}</nav>
    <span class="abtools"><a href="/help" target="_blank" title="使用指北">❓</a>
      <a href="/qr.svg" target="_blank" title="手机扫码访问">📱</a></span>
  </div></header>`;
  // 底部导航必须包在 nav.bnav 里（CSS 按类选择），且 chromeBottom 容器要在各页 <script> 之前出现
  const b = document.getElementById('chromeBottom');
  if (b) b.innerHTML = `<nav class="bnav">${PAGES.map(([u, k, ic, label]) =>
    `<a class="${k === active ? 'on' : ''}" href="${u}"><span class="ic">${ic}</span>${label}</a>`).join('')}</nav>`;
}

/* 字号循环：标准 → 大 → 特大（localStorage 记忆） */
(function initFs() { const v = localStorage.getItem('fs'); if (v) document.body.dataset.fs = v; })();
function cycleFs() {
  const i = (+localStorage.getItem('fs') + 1) % 3;
  localStorage.setItem('fs', String(i));
  document.body.dataset.fs = ['1', '2', '3'][i] === '1' ? '' : ['1', '2', '3'][i];
  document.documentElement.dataset.fs = document.body.dataset.fs;
  return ['字号:标准', '字号:大', '字号:特大'][i];
}

/* ---------- 数据标记 ---------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({ ok: false, error: '响应不是JSON' }));
  if (!r.ok || j.ok === false) console.warn('API失败', path, j);
  return j;
}
function post(path, body) {
  return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify(body) });
}

/* {{词}} 普通挖空；{{!词}} 高频红色挖空 → [{t,s,hot}] */
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
function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function hasBlank(text) { return /\{\{!?[^{}]*\}\}/.test(text); }
function countBlanks(text) { return (text.match(/\{\{!?[^{}]*\}\}/g) || []).length; }
function plainText(t) { return (t || '').replace(/\{\{(!?)([^{}]*)\}\}/g, '$2'); }
function normalizeAnswer(s) {
  return (s || '').replace(/[\s，。：；、·,.:;()（）"'"'"'【】\-—！!？?]/g, '');
}

/* mode: show 全部可见 / hide 遮罩可点开 / input 填空输入 */
function renderText(text, mode) {
  return (text || '').split('\n').map(line => {
    let html = '';
    for (const seg of parseMarks(line)) {
      if (seg.t === 'txt') { html += esc(seg.s); continue; }
      if (mode === 'show') {
        html += `<span class="mk rev${seg.hot ? ' hot' : ''}">${esc(seg.s)}</span>`;
      } else if (mode === 'hide') {
        html += `<span class="mk hid${seg.hot ? ' hot' : ''}" onclick="this.classList.add('rev')">${esc(seg.s)}</span>`;
      } else {
        html += `<span class="mk-inwrap"><input class="mk-in${seg.hot ? ' hot' : ''}" data-ans="${esc(seg.s)}" style="width:${seg.s.length + 2}em"><span class="mk-ans">${esc(seg.s)}</span></span>`;
      }
    }
    return html;
  }).join('<br>');
}

/* 籍贯色小标签 */
const SUBJ_CLASS = { '毛中特': 'cs1', '马原': 'cs2', '史纲': 'cs3', '思修': 'cs4', '时政': 'cs5', '常识': 'cs6' };
function chipTag(sub) {
  const c = SUBJ_CLASS[sub] || 'cs7';
  return `<span class="chip ${c}">${esc(sub || '未分类')}</span>`;
}

/* 在 textarea 包裹选区（点按钮前记得先选中文字） */
function surround(id, pre, post) {
  const ta = document.getElementById(id);
  if (!ta) return;
  let a = ta.selectionStart, b = ta.selectionEnd;
  if (a === b) { toast('先选中一段文字（长按拖选/双击选词）'); return; }
  const v = ta.value, word = v.slice(a, b);
  ta.value = v.slice(0, a) + pre + word + post + v.slice(b);
  ta.selectionStart = ta.selectionEnd = a + pre.length + word.length + post.length;
  ta.focus();
  ta.dispatchEvent(new Event('input'));
}

let _toastTimer;
function toast(msg, ok) {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  el.textContent = msg;
  el.className = ok === false ? 'ng' : '';
  el.style.display = 'block';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.style.display = 'none', 2200);
}
