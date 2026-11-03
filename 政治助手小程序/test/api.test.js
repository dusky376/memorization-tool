/* 政治助手小程序 - utils/api.js 纯逻辑单测（node test/api.test.js）
 * 只测纯函数，不触 wx（所有 wx 调用都在函数体内）。
 * 挖空括号统一用 L/R 变量构造，避免字面量在传输/编辑中被截。 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const api = require('../utils/api');

/* 挖空标记括号：{{ 与 }} */
const L = String.fromCharCode(123, 123);
const R = String.fromCharCode(125, 125);
const B = (w) => L + w + R;        // {{词}}
const BH = (w) => L + '!' + w + R; // {{!词}}

let pass = 0, fail = 0;
function eq(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log('  ok ' + label); }
  else { fail++; console.log('  FAIL ' + label + '\n    got : ' + g + '\n    want: ' + w); }
}
function ok(label, cond) {
  if (cond) { pass++; console.log('  ok ' + label); }
  else { fail++; console.log('  FAIL ' + label); }
}

/* ---------- parseMarks ---------- */
console.log('parseMarks');
let r = api.parseMarks('你好世界');
eq('纯文本单段', r, [{ t: 'txt', s: '你好世界' }]);

r = api.parseMarks(B('词'));
eq('全挖空', r, [{ t: 'blank', s: '词', hot: false }]);

r = api.parseMarks(BH('词'));
eq('红标挖空 hot=true', r[0].hot, true);

r = api.parseMarks('A' + B('x') + 'B' + BH('y') + 'C');
eq('混合分段', r.map((s) => s.t), ['txt', 'blank', 'txt', 'blank', 'txt']);
eq('第2处是红标', r[3].hot, true);
eq('keyword 提取', r[1].s + '|' + r[3].s, 'x|y');

r = api.parseMarks('未闭合' + L + 'abc');
eq('未闭合标记不吞字', r, [{ t: 'txt', s: '未闭合{{abc' }]);

r = api.parseMarks(L + 'x');
eq('单花括号误用不误伤', r[0].t, 'txt');

/* ---------- prepareInto ---------- */
console.log('prepareInto');
const box = {};
api.prepareInto(box, '第一行有' + B('核心') + '词\n第二行' + BH('红') + '色');
eq('行数', box.lines.length, 2);
eq('ri', [box.lines[0].ri, box.lines[1].ri], [0, 1]);
eq('blank 有宽度字段（2字→2+2）', box.lines[0].segs[1].w, 4);
ok('blank 有 good 字段', box.lines[0].segs[1].good === 0);
const keys = box.lines.flatMap((l) => l.segs.map((s) => s.key));
ok('key 全局唯一', new Set(keys).size === keys.length);

const box2 = {};
api.prepareInto(box2, B('中') + '中');
eq('短词宽度下限4', box2.lines[0].segs[0].w, 4);

eq('多行 blank 计数', api.countBlanks(B('核心') + '\n' + BH('红')), 2);

/* ---------- hasBlank / countBlanks / plainText ---------- */
console.log('hasBlank / countBlanks / plainText');
eq('hasBlank true', api.hasBlank('a' + B('b') + 'c'), true);
eq('hasBlank false', api.hasBlank('没有标记'), false);
eq('hasBlank 空串', api.hasBlank(''), false);
eq('countBlanks', api.countBlanks('a' + B('b') + 'c' + BH('d') + 'e'), 2);
eq('plainText 去标记留词', api.plainText('建设' + BH('中国式现代化') + '道路'), '建设中国式现代化道路');

/* ---------- normalizeAnswer（校对填空的宽松匹配） ---------- */
console.log('normalizeAnswer');
eq('标点空白全剥离', api.normalizeAnswer(' 中，国。式！现代化 '), '中国式现代化');
eq('undefined 安全', api.normalizeAnswer(undefined), '');
eq('英文标点', api.normalizeAnswer('A,B;C!'), 'ABC');
eq('填空校对命中', api.normalizeAnswer('中  国') === api.normalizeAnswer('中国'), true);

/* ---------- modeLabel ---------- */
console.log('modeLabel');
eq('win', api.modeLabel('win'), '兜底识别');
eq('recover', api.modeLabel('recover'), '忽略恢复');
eq('docx', api.modeLabel('docx'), 'Word解析');
eq('txt', api.modeLabel('txt'), '纯文本');
eq('pdfmr', api.modeLabel('pdfmr'), 'PDF解析');
eq('AI', api.modeLabel(''), 'AI识别');

/* ---------- autoMark（自动挖空：一律包 {{!}} 红标） ---------- */
console.log('autoMark');
let t = '党中央部署了新举措';
let t2 = api.autoMark(t, ['新举措']);
eq('候选词包红标（统一 {{!}} 样式）', t2, '党中央部署了' + BH('新举措'));

t2 = api.autoMark('重点在第一章：现代化', ['重点', '第一章', '现代化']);
ok('停用词跳过', !t2.includes(BH('重点')) && !t2.includes(BH('第一章')));
eq('正常词仍标', t2.includes(BH('现代化')), true);

t2 = api.autoMark('中国式现代化', ['中国式现代化', '中国']);
eq('长词优先', t2, BH('中国式现代化'));
ok('不嵌套', t2.indexOf(BH('中国')) < 0);

t2 = api.autoMark('词一个词二个', ['词']);
eq('单字候选跳过', t2, '词一个词二个');

t = '已经' + B('旧') + '了再来一次';
t2 = api.autoMark(t, ['再来']);
eq('已标记区不动、新词标首个出现', t2, '已经' + B('旧') + '了' + BH('再来') + '一次');

t2 = api.autoMark('', ['什么']);
eq('空文本安全', t2, '');

eq('SUBJECTS 七科', api.SUBJECTS.length, 7);

/* ---------- base()：node 环境下 wx 不存在也不炸（防御式兜底路径） ---------- */
console.log('base 防御');
let b;
try { b = api.base(); } catch (e) { b = 'throw:' + e.message; }
ok('node 里 base() 走 LAN 兜底', b === 'http://192.168.4.12:8686');

/* ---------- JSON 配置文件合法 + 关键字段 ---------- */
console.log('json 配置');
const root = path.join(__dirname, '..');
['app.json', 'project.config.json', 'sitemap.json'].forEach((f) => {
  JSON.parse(fs.readFileSync(path.join(root, f), 'utf8'));   // 解析失败会抛
  pass++;
  console.log('  ok ' + f + ' JSON 合法');
});
const appj = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'));
eq('app.json 5页注册', appj.pages.length, 5);
eq('tabBar 4项', appj.tabBar.list.length, 4);
appj.tabBar.list.flatMap((x) => [x.iconPath, x.selectedIconPath]).forEach((p) => {
  ok('图标存在 ' + p, fs.existsSync(path.join(root, p)));
});
ok('help 不在 tabBar（navigateTo 进入）', JSON.stringify(appj.tabBar.list).indexOf('help') < 0);
ok('注册的页都有 4 件套', appj.pages.every((p) =>
  ['js', 'json', 'wxml'].every((ext) =>
    fs.existsSync(path.join(root, p + '.' + ext)))));

/* ---------- WXML 引用的事件处理器在 JS 里都实现 ---------- */
console.log('wxml/js 引用闭环');
function checkPage(dir, name) {
  const wxml = fs.readFileSync(path.join(root, 'pages', dir, name + '.wxml'), 'utf8');
  const js = fs.readFileSync(path.join(root, 'pages', dir, name + '.js'), 'utf8');
  const handlers = new Set();
  const re = /(?:bind|catch)[\w:]*="(\w+)"/g; let m;
  while ((m = re.exec(wxml))) handlers.add(m[1]);
  const missing = [...handlers].filter((h) =>
    !new RegExp('[,{ ]' + h + '\\s*[:(]', 'm').test(js));
  eq(name + ' 模板事件处理器都存在 js（' + handlers.size + ' 个）', missing, []);
}
checkPage('recite', 'recite');
checkPage('add', 'add');
checkPage('arrange', 'arrange');
checkPage('manage', 'manage');
checkPage('help', 'help');

console.log('\n==== ' + pass + ' 通过 / ' + fail + ' 失败 ====');
process.exit(fail ? 1 : 0);
