/* 政治背诵小程序 - 管理页（列表 / 搜索 / 编辑跳转 / 删除） */
const api = require('../../utils/api');
const app = getApp();

Page({
  data: {
    subjects: ['全部科目'].concat(api.SUBJECTS),
    subjectIdx: 0,
    subject: '',
    q: '',

    orderLabels: ['按时间', '按科目', '按背诵次数'],
    orderIdx: 0,

    entries: [],
    loaded: false,
    stats: '加载中…',
  },

  onShow() {
    this.load();   // 编辑保存 / 删除回来后刷新
  },

  load() {
    api.get('/api/entries').then((j) => {
      const all = (j.entries || []).map((e) => ({
        id: e.id,
        subject: e.subject || '',
        chapter: e.chapter || '',
        source: e.source || '',
        hot: !!e.hot,
        text: e.text || '',
        created: String(e.created || ''),
        stage: (e.review && e.review.stage) || 0,
        due: (e.review && e.review.due) || '',
      }));
      this._all = all;
      this.setData({ loaded: true });
      this.render();
    }).catch((e) => {
      this._all = [];
      this.setData({ loaded: true, stats: '加载失败：' + e.message });
    });
  },

  render() {
    const q = this.data.q.trim().toLowerCase();
    const sub = this.data.subject;
    let rows = this._all || [];
    if (sub) rows = rows.filter((e) => e.subject === sub);
    if (q) rows = rows.filter((e) =>
      (api.plainText(e.text) + ' ' + e.subject + ' ' + e.chapter + ' ' + e.source)
        .toLowerCase().includes(q));

    if (this.data.orderIdx === 1) {
      rows = rows.slice().sort((a, b) => a.subject.localeCompare(b.subject, 'zh') ||
        String(a.created).localeCompare(String(b.created)));
    } else if (this.data.orderIdx === 2) {
      rows = rows.slice().sort((a, b) => (b.stage - a.stage) || String(b.created).localeCompare(String(a.created)));
    } else {
      rows = rows.slice().sort((a, b) => String(b.created).localeCompare(String(a.created)));
    }

    const shaped = rows.map((e) => Object.assign({}, e, {
      title: api.plainText(e.text).replace(/\s+/g, ' ').slice(0, 60),
      reviewN: e.stage || 0,
      due: e.due,
    }));
    this.setData({
      entries: shaped,
      stats: '共 ' + rows.length + ' 条' + (this._all.length !== rows.length ? '（全库 ' + this._all.length + '）' : '') +
        ' · 高频 ' + (sub ? rows.filter((e) => e.hot).length : (this._all.filter((e) => e.hot)).length) + ' 条',
    });
  },

  onQ(ev) {
    this.setData({ q: ev.detail.value });
    this.render();
  },
  setSubject(ev) {
    const i = +ev.detail.value;
    const subject = this.data.subjects[i] === '全部科目' ? '' : this.data.subjects[i];
    this.setData({ subjectIdx: i, subject: subject });
    this.render();
  },
  setOrder(ev) {
    this.setData({ orderIdx: +ev.detail.value });
    this.render();
  },

  goEdit(ev) {
    const id = ev.currentTarget.dataset.id;
    if (!id) return;
    app.globalData.editId = id;
    wx.switchTab({ url: '/pages/add/add' });
  },

  delEntry(ev) {
    const id = ev.currentTarget.dataset.id;
    const t = ev.currentTarget.dataset.t || '';
    if (!id) return;
    wx.showModal({
      title: '删除词条',
      content: '删掉「' + (t.slice(0, 18) || '这条') + '…」？删除后不可恢复。',
      confirmText: '删除',
      confirmColor: '#c62828',
      success: (res) => {
        if (!res.confirm) return;
        api.post('/api/entry_delete', { id: id }).then((j) => {
          api.toast(j.ok ? '✓ 已删除' : (j.error || '删除失败'), j.ok);
          this.load();
        }).catch((e) => api.failToast(e));
      },
    });
  },

  goAdd() { wx.switchTab({ url: '/pages/add/add' }); },
  goHelp() { wx.navigateTo({ url: '/pages/help/help' }); },
});
