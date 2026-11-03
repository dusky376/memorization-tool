/* 政治背诵 - 背诵页 */
const api = require('../../utils/api');
const app = getApp();

Page({
  data: {
    view: 'list',
    subjects: ['全部科目'].concat(api.SUBJECTS),
    subjectIdx: 0,
    subject: '',
    sizes: [5, 10, 20, 50, 9999],
    sizeLabels: ['5 题/轮', '10 题/轮', '20 题/轮', '50 题/轮', '全部'],
    sizeIdx: 1,

    /* list 视图 */
    entries: [],        // 展示中的（已过滤）
    _all: [],           // 全量（tab 页数据不进 _ 的集合，放 this 上）
    q: '',
    covered: false,
    revealAll: false,
    stats: '加载中…',

    /* cards 视图 */
    queue: [],
    idx: 0,
    done: false,
    mode: 'hide',      // hide 点击遮挡 / input 输入填空
    cur: null,
    blankN: 0,
    statsCards: '加载中…',
  },

  onShow() {
    this.refresh();   // 从录入/管理/整理回来数据可能变了；首次进入也会触发
  },

  refresh() {
    if (this.data.view === 'list') this.loadList();
    else this.loadCards();
  },

  /* ================= 顶部控制 ================= */
  setView(ev) {
    const v = ev.currentTarget.dataset.v;
    if (this.data.view === v) return;
    this.setData({ view: v });
    this.refresh();
  },
  setSubject(ev) {
    const i = +ev.detail.value;
    const subject = this.data.subjects[i] === '全部科目' ? '' : this.data.subjects[i];
    this.setData({ subjectIdx: i, subject });
    this.refresh();
  },
  onQ(ev) {
    this.setData({ q: ev.detail.value });
    this.renderFiltered();
  },
  toggleCover() {
    this.setData({ covered: !this.data.covered, revealAll: false });
  },
  doRevealAll() {
    this.setData({ revealAll: true });
  },

  /* ================= 全库列表 ================= */
  loadList() {
    const qs = this.data.subject ? '?subject=' + encodeURIComponent(this.data.subject) : '';
    api.get('/api/entries' + qs).then((j) => {
      const all = (j.entries || []).slice().sort((a, b) => String(a.created).localeCompare(String(b.created)));
      const shaped = all.map((e) => this.shapeEntry(e));
      this._all = shaped;
      this.setData({
        stats: '共 ' + all.length + ' 条 · 高频 ' + all.filter((e) => e.hot).length + ' 条',
      });
      this.renderFiltered();
    }).catch((e) => { this.setData({ stats: '加载失败：' + e.message }); api.failToast(e); });
  },
  shapeEntry(e) {
    const box = {};
    api.prepareInto(box, e.text);
    return Object.assign({}, e, {
      hot: !!e.hot,
      chapter: e.chapter || '',
      createdShort: String(e.created || '').slice(5, 16).replace('T', ' '),
      revealed: false,
      lines: box.lines,
    });
  },
  renderFiltered() {
    const q = this.data.q.trim().toLowerCase();
    const rows = q ? this._all.filter((e) =>
      (api.plainText(e.text) + ' ' + (e.subject || '') + ' ' + (e.chapter || '') + ' ' + (e.source || ''))
        .toLowerCase().includes(q)) : this._all;
    this.setData({ entries: rows });
    if (!this._all.length) this.setData({ stats: '还没有词条，去【录入】页拍照上传' });
  },
  tapRevealEntry(ev) {
    if (!this.data.covered || this.data.revealAll) return;
    const i = +ev.currentTarget.dataset.i;
    const e = this.data.entries[i];
    if (!e) return;
    this.setData({ ['entries[' + i + '].revealed']: !e.revealed });
  },
  goEdit(ev) {
    const id = ev.currentTarget.dataset.id;
    if (!id) return;
    app.globalData.editId = id;
    wx.switchTab({ url: '/pages/add/add' });
  },

  /* ================= 今日卡片 ================= */
  loadCards() {
    const qs = this.data.subject ? '?subject=' + encodeURIComponent(this.data.subject) : '';
    api.get('/api/today' + qs).then((j) => {
      const st = j.stats || {};
      const size = this.data.sizes[this.data.sizeIdx];
      const queue = (j.queue || []).slice(0, size);
      this.setData({
        statsCards: '今日待背 ' + (st.due === undefined ? (j.queue || []).length : st.due) +
          ' · 高频 ' + (st.hot || 0) + ' · 全库 ' + (st.total || 0),
        queue: queue,
        idx: 0,
        done: false,
      });
      this.buildCard();
    }).catch((e) => { this.setData({ statsCards: '加载失败：' + e.message }); api.failToast(e); });
  },
  reloadCards() { this.loadCards(); },
  buildCard() {
    const q = this.data.queue, i = this.data.idx;
    if (!q.length || i >= q.length) { this.setData({ done: true, cur: null }); return; }
    const box = {};
    api.prepareInto(box, q[i].text);
    const cur = Object.assign({}, q[i], {
      hot: !!q[i].hot,
      chapter: q[i].chapter || '',
      revealed: false,
      lines: box.lines,
    });
    this.setData({
      cur: cur,
      blankN: api.countBlanks(q[i].text),
      done: false,
    });
  },
  stepPrev() { this.step(-1); },
  stepNext() { this.step(1); },
  step(d) {
    const i = Math.min(Math.max(this.data.idx + d, 0), this.data.queue.length);
    this.setData({ idx: i });
    this.buildCard();
  },
  toggleMode() {
    const m = this.data.mode === 'hide' ? 'input' : 'hide';
    this.setData({ mode: m });
    this.buildCard();
  },
  tapRevealCard() {
    if (this.data.mode !== 'hide') return;
    const c = this.data.cur;
    if (!c) return;
    this.setData({ 'cur.revealed': !c.revealed });
  },
  onBlank(ev) {
    const ri = ev.currentTarget.dataset.ri, si = ev.currentTarget.dataset.si;
    this.setData({ ['cur.lines[' + ri + '].segs[' + si + '].inp']: ev.detail.value });
  },
  doCheck() {
    const cur = this.data.cur;
    if (!cur) return;
    let good = 0, total = 0;
    const patch = {};
    cur.lines.forEach((row, ri) => {
      row.segs.forEach((seg, si) => {
        if (seg.t !== 'blank') return;
        total++;
        const ok = api.normalizeAnswer(seg.inp) && api.normalizeAnswer(seg.inp) === api.normalizeAnswer(seg.s);
        if (ok) good++;
        patch['cur.lines[' + ri + '].segs[' + si + '].good'] = ok ? 1 : 2;
      });
    });
    this.setData(patch);
    api.toast('答对 ' + good + ' / ' + total, true);
  },
  doOk() { this.review(true); },
  doNg() { this.review(false); },
  review(ok) {
    const q = this.data.queue.slice();
    const e = q[this.data.idx];
    if (!e) return;
    const idx = this.data.idx;
    api.post('/api/review', { id: e.id, ok: !!ok }).then(() => {
      q.splice(idx, 1);
      const ni = idx >= q.length ? 0 : idx;
      this.setData({ queue: q, idx: ni });
      api.toast(ok ? '👍 背上了' : '明天再见！', true);
      this.buildCard();
      if (!q.length) this.setData({ done: true, cur: null });
    }).catch((er) => api.failToast(er));
  },
});
