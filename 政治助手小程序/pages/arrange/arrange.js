/* 政治背诵 - 整理页（草稿确认 / 忽略记录） */
const api = require('../../utils/api');

Page({
  data: {
    subjects: api.SUBJECTS,
    drafts: [],
    ignored: [],
    statsLine: '加载中…',
    base: api.base(),
  },

  onShow() {
    this.load();
    this._timer = setInterval(() => this.load(), 8000);   // 后台 5 秒扫描，8 秒轮询足够
  },
  onHide() { clearInterval(this._timer); this._timer = null; },
  onUnload() { clearInterval(this._timer); this._timer = null; },

  load() {
    Promise.all([
      api.get('/api/drafts'),
      api.get('/api/ignored').catch(() => ({ ignored: [] })),
    ]).then((rs) => {
      const ds = (rs[0].drafts || []).slice().sort((a, b) =>
        ((a.ts || 0) - (b.ts || 0)) || String(a.created || '').localeCompare(String(b.created || ''))
      );
      const ig = rs[1].ignored || [];
      this.setData({
        drafts: ds.map((d, i) => this.shapeDraft(d)),
        ignored: ig.map((x) => Object.assign({}, x, {
          reason: String(x.reason || '内容重复').split('（')[0],
          snip: String(x.text || '').slice(0, 90) + (String(x.text || '').length > 90 ? '…' : ''),
        })),
        statsLine: '草稿 ' + ds.length + ' 张 · 自动扫描运行中' + (ig.length ? ' · 已忽略重复 ' + ig.length + ' 条' : ''),
      });
    }).catch((e) => { this.setData({ statsLine: '加载失败：' + e.message }); });
  },

  shapeDraft(d) {
    const box = {};
    api.prepareInto(box, d.text);
    const idx = Math.max(0, this.data.subjects.indexOf(d.subject));
    return Object.assign({}, d, {
      subjectIdx: idx,
      chapter: d.chapter || '',
      source: d.source || '',
      modeTex: api.modeLabel(d.mode),
      candidateN: (d.candidates || []).length,
      remarkable: !!d.img && !d.doc && !d.auton && String(d.text || '').indexOf('{{') < 0,
      previewLines: box.lines,
      prevRevealed: false,
      hasBlank: api.hasBlank(d.text),
    });
  },

  /* ---------------- 草稿编辑 ---------------- */
  onDraftText(ev) {
    const i = +ev.currentTarget.dataset.i;
    const text = ev.detail.value;
    const box = {};
    api.prepareInto(box, text);
    this.setData({
      ['drafts[' + i + '].text']: text,
      ['drafts[' + i + '].hasBlank']: api.hasBlank(text),
      ['drafts[' + i + '].previewLines']: box.lines,
      ['drafts[' + i + '].remarkable']: false,
    });
  },
  setDraftSubject(ev) {
    this.setData({ ['drafts[' + ev.currentTarget.dataset.i + '].subjectIdx']: +ev.detail.value });
  },
  onDraftChapter(ev) { this.setData({ ['drafts[' + ev.currentTarget.dataset.i + '].chapter']: ev.detail.value }); },
  onDraftSource(ev) { this.setData({ ['drafts[' + ev.currentTarget.dataset.i + '].source']: ev.detail.value }); },
  toggleDraftPreview(ev) {
    const i = +ev.currentTarget.dataset.i;
    this.setData({ ['drafts[' + i + '].prevRevealed']: !this.data.drafts[i].prevRevealed });
  },

  /* ---------------- 草稿操作 ---------------- */
  assembleBody(i) {
    const d = this.data.drafts[i];
    return {
      id: d.id,
      text: d.text,
      subject: this.data.subjects[d.subjectIdx],
      chapter: (d.chapter || '').trim(),
      source: (d.source || '').trim(),
      hot: /\{\{!/.test(d.text || ''),
    };
  },
  confirmDraft(ev) {
    const i = +ev.currentTarget.dataset.i;
    const body = this.assembleBody(i);
    if (!String(body.text || '').trim()) { api.toast('内容为空', false); return; }
    api.post('/api/draft_confirm', body).then((j) => {
      if (j.dup && !body.force) {
        wx.showModal({
          title: '疑似重复',
          content: (j.error || '检测到重复') + '。仍要入库吗？',
          success: (res) => { if (res.confirm) { body.force = true; this.forceConfirm(body); } },
        });
        return;
      }
      api.toast(j.ok ? '✓ 已入背诵库！' : (j.error || '未入库'), j.ok);
      this.load();
    }).catch((e) => api.failToast(e));
  },
  forceConfirm(body) {
    api.post('/api/draft_confirm', body).then((j) => {
      api.toast(j.ok ? '✓ 已入背诵库！' : (j.error || '未入库'), j.ok);
      this.load();
    }).catch((e) => api.failToast(e));
  },
  delDraft(ev) {
    const i = +ev.currentTarget.dataset.i;
    const d = this.data.drafts[i];
    wx.showModal({
      title: '丢弃草稿',
      content: '丢进「已忽略」留痕（可转为草稿找回）。确定丢弃？',
      success: (res) => {
        if (!res.confirm) return;
        api.post('/api/draft_delete', { id: d.id }).then(() => this.load()).catch((e) => api.failToast(e));
      },
    });
  },
  retryDraft(ev) {
    const i = +ev.currentTarget.dataset.i;
    api.toast('重新识别中…', true);
    api.post('/api/draft_retry', { id: this.data.drafts[i].id })
      .then((j) => { api.toast(j.ok ? '✓ 重新识别完成' : (j.error || '失败'), j.ok); this.load(); })
      .catch((e) => api.failToast(e));
  },
  remarkDraft(ev) {
    const i = +ev.currentTarget.dataset.i;
    api.toast('读截图红标中…', true);
    api.post('/api/draft_remark', { id: this.data.drafts[i].id })
      .then((j) => { api.toast(j.ok ? '🤖 已按红标+热词自动挖空' : (j.error || '失败'), j.ok); this.load(); })
      .catch((e) => api.failToast(e));
  },
  autoMarkDraft(ev) {
    const i = +ev.currentTarget.dataset.i;
    const d = this.data.drafts[i];
    const text = api.autoMark(d.text, d.candidates || []);
    const box = {};
    api.prepareInto(box, text);
    this.setData({
      ['drafts[' + i + '].text']: text,
      ['drafts[' + i + '].hasBlank']: api.hasBlank(text),
      ['drafts[' + i + '].previewLines']: box.lines,
    });
    api.toast('已按高频词表自动标红', true);
  },
  allIn() {
    const ds = this.data.drafts;
    if (!ds.length) { api.toast('没有草稿可入库', false); return; }
    wx.showModal({
      title: '全部入库',
      content: '把全部草稿一次性入背诵库？重复的自动跳过。',
      success: (res) => {
        if (!res.confirm) return;
        api.toast('批量入库中…', true);
        let okN = 0, dupN = 0, errN = 0;
        const walk = (k) => {
          if (k >= ds.length) {
            api.toast('⚡ 完成：入库 ' + okN + ' · 跳过重复 ' + dupN + (errN ? ' · 失败 ' + errN : ''), true);
            this.load();
            return;
          }
          const d = ds[k];
          const body = {
            id: d.id,
            text: d.text,
            subject: this.data.subjects[d.subjectIdx],
            chapter: (d.chapter || '').trim(),
            source: (d.source || '').trim(),
            hot: /\{\{!/.test(d.text || ''),
          };
          if (!String(body.text || '').trim()) { errN++; walk(k + 1); return; }
          api.post('/api/draft_confirm', body).then((j) => {
            if (j.ok) okN++; else if (j.dup) dupN++; else errN++;
            walk(k + 1);
          }).catch(() => { errN++; walk(k + 1); });
        };
        walk(0);
      },
    });
  },
  dedupe() {
    api.post('/api/drafts_dedupe', {}).then((j) => {
      api.toast(j.ok ? '已清理 ' + (j.removed || 0) + ' 张重复草稿' : '失败', j.ok);
      this.load();
    }).catch((e) => api.failToast(e));
  },
  previewImg(ev) {
    const i = +ev.currentTarget.dataset.i;
    const d = this.data.drafts[i];
    if (d && d.img) {
      wx.previewImage({ urls: [this.data.base + '/shots/' + d.img] });
    }
  },
  goAdd() { wx.switchTab({ url: '/pages/add/add' }); },

  /* ---------------- 忽略记录 ---------------- */
  recoverIg(ev) {
    const i = +ev.currentTarget.dataset.i;
    api.post('/api/ignored_recover', { id: this.data.ignored[i].id }).then((j) => {
      api.toast(j.ok ? '已转为草稿，在上方核对入库' : (j.error || '失败'), j.ok);
      this.load();
    }).catch((e) => api.failToast(e));
  },
  clearIgnored() {
    wx.showModal({
      title: '清空忽略记录',
      content: '清掉全部「已忽略」留痕？被挡住的文件指纹还在（同文件仍不会复活）。',
      success: (res) => {
        if (!res.confirm) return;
        api.post('/api/ignored_clear', {}).then(() => this.load()).catch((e) => api.failToast(e));
      },
    });
  },
});
