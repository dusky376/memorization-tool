/* 政治背诵 - 录入页（上传识别 + 手动录入 + 编辑已有词条） */
const api = require('../../utils/api');
const app = getApp();

Page({
  data: {
    editing: false,
    editingId: null,

    subjects: api.SUBJECTS,
    subjectIdx: 0,
    chapter: '',
    source: '',
    hot: false,
    text: '',

    filesView: [],      // 本轮上传过的识别结果：{fid, short, text}
    curFile: -1,        // 当前载入的是第几份（-1 = 手动编辑态）
    uploading: false,
    canPickDoc: typeof wx.chooseMessageFile === 'function',   // 鸿蒙版微信兼容探测

    previewLines: [],
    prevRevealed: false,
    hasBlank: false,

    /* 大括号字面量只能放 data 进模板（WXML 直接写 {{词}} 会截断表达式） */
    mN: '{{词}}',
    mH: '{{!词}}',
  },

  onShow() {
    const eid = app.globalData.editId;
    if (eid) { this.startEdit(eid); return; }
    // 非编辑进入首次刷新一次库量提示；不覆盖用户正在编辑的草稿
    if (!this._openedOnce) {
      this._openedOnce = true;
      api.get('/api/status').then((j) => {
        this.setData({ cntInfo: '库里共 ' + (j.total || 0) + ' 条 · 上传识别后自动带挖空' });
      }).catch(() => { });
    }
  },

  /* ---------------- 表单控件 ---------------- */
  setSubject(ev) { this.setData({ subjectIdx: +ev.detail.value }); },
  setChapter(ev) { this.setData({ chapter: ev.detail.value }); },
  setSource(ev) { this.setData({ source: ev.detail.value }); },
  setHot(ev) { this.setData({ hot: ev.detail.value }); },
  onText(ev) {
    this.setText(ev.detail.value, -1);
  },
  setText(text, fileIdx) {
    const box = {};
    api.prepareInto(box, text);
    this.setData({
      text: text,
      curFile: fileIdx,
      hasBlank: api.hasBlank(text),
      previewLines: box.lines,
    });
  },

  togglePreview() { this.setData({ prevRevealed: !this.data.prevRevealed }); },

  /* ---------------- 图片上传 ---------------- */
  chooseImage() {
    if (this.data.uploading) { api.toast('识别中，稍等…', false); return; }
    wx.chooseMedia({
      count: 9,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],
      success: (res) => this.uploadQueue(res.tempFiles || []),
      fail: () => { },   // 用户取消选择，静默
    });
  },
  uploadQueue(files) {
    if (!files.length) return;
    this.setData({ uploading: true });
    api.toast('识别中 0/' + files.length, true);
    let idx = 0, lastText = null, autoLoaded = false;
    const fv = this.data.filesView.slice();
    const next = () => {
      if (idx >= files.length) {
        this.setData({ uploading: false });
        if (lastText !== null) this.setText(lastText, 0);   // 最新一张进表单（对齐网页版）
        return;
      }
      const f = files[idx];
      api.upload('/api/ocr', f.tempFilePath, 'file', {}).then((j) => {
        if (j.ok) {
          fv.unshift({ fid: 'f' + Date.now() + idx, short: (j.first_line || '截图') + '（挖空 ' + (j.auton || 0) + '）', text: j.text || '' });
          lastText = j.text || '';
          if (!autoLoaded) autoLoaded = true;   // 等全传完再载入（保证最新一张优先）
        } else {
          api.toast(j.error || '识别失败', false);
        }
        idx++;
        api.toast('识别中 ' + idx + '/' + files.length, true);
        this.setData({ filesView: fv });
        next();
      }).catch((e) => {
        idx++;
        this.setData({ filesView: fv });
        api.failToast(e);
        next();
      });
    };
    next();
  },
  loadFileText(ev) {
    const i = +ev.currentTarget.dataset.i;
    const fv = this.data.filesView[i];
    if (fv) this.setText(fv.text, i);
  },

  /* ---------------- 文档上传（聊天文件） ---------------- */
  chooseDoc() {
    if (this.data.uploading) { api.toast('识别中，稍等…', false); return; }
    if (typeof wx.chooseMessageFile !== 'function') {
      wx.showModal({
        title: '不支持从聊天选文件',
        content: '当前微信版本不支持该功能；请用拍照/选图上传，或按 PDF 直接在电脑端处理。',
        showCancel: false,
      });
      return;
    }
    wx.chooseMessageFile({
      count: 5,
      type: 'file',
      extension: ['pdf', 'docx', 'txt', 'md'],
      success: (res) => this.uploadDocs(res.tempFiles || []),
      fail: () => { },
    });
  },
  uploadDocs(files) {
    if (!files.length) return;
    this.setData({ uploading: true });
    const DOC = ['pdf', 'docx', 'txt', 'md'];
    let idx = 0, merged = this.data.text || '';
    const next = () => {
      if (idx >= files.length) { this.setData({ uploading: false }); if (merged) this.setText(merged, 0); return; }
      const f = files[idx];
      const ext = (f.name || '').split('.').pop().toLowerCase();
      if (DOC.indexOf(ext) < 0) { api.toast('跳过 ' + (f.name || '文件') + '（只支持 pdf/docx/txt/md）', false); idx++; next(); return; }
      api.upload('/api/doc_ocr', f.path, 'file', {}).then((j) => {
        if (j.ok) {
          merged = merged ? merged + '\n' + (j.text || '') : (j.text || '');
        } else {
          api.toast(j.error || '提取失败', false);
        }
        idx++;
        next();
      }).catch((e) => { idx++; api.failToast(e); next(); });
    };
    next();
  },

  /* ---------------- 挖空助手 ---------------- */
  wrapWord(kind) {
    const word = (this._pickWord || '').trim();
    if (!word) return;
    const t = this.data.text;
    const at = t.indexOf(word);
    if (at < 0) { api.toast('正文里没找到「' + word + '」', false); return; }
    // 已包区域内不重复包
    const marked = /\{\{!?[^{}]*\}\}/g; let m;
    while ((m = marked.exec(t))) {
      if (m.index <= at && at < m.index + m[0].length) { api.toast('该词已在标记内', false); return; }
    }
    const tag = kind === 'hot' ? '{{!' + word + '}}' : '{{' + word + '}}';
    this.setText(t.slice(0, at) + tag + t.slice(at + word.length), this.data.curFile);
    api.toast(kind === 'hot' ? '已包红色挖空' : '已包普通挖空', true);
  },
  helperHot() { this.askWord('hot'); },
  helperNormal() { this.askWord('normal'); },
  askWord(kind) {
    wx.showModal({
      title: kind === 'hot' ? '红色挖空助手' : '普通挖空助手',
      editable: true,
      placeholderText: '输入正文里的一个词，如：中国式现代化',
      success: (res) => {
        if (res.confirm && res.content) {
          this._pickWord = res.content;
          this.wrapWord(kind);
        } else if (res.confirm && !res.content) {
          // 老基础库不支持 editable 弹窗：点了确定但拿不到输入
          api.toast('该微信版本不支持弹窗输入，请直接在正文里手动包标记', false);
        }
      },
    });
  },

  /* ---------------- 保存 ---------------- */
  save() {
    const body = {
      id: this.data.editingId || undefined,
      subject: this.data.subjects[this.data.subjectIdx],
      chapter: this.data.chapter.trim(),
      source: this.data.source.trim(),
      hot: this.data.hot,
      text: this.data.text,
    };
    if (!body.text.trim()) { api.toast('正文为空', false); return; }
    api.post('/api/entry_save', body).then((j) => {
      if (j.dup && !body.force) {
        wx.showModal({
          title: '疑似重复',
          content: (j.error || '检测到重复') + '。仍要保存吗？',
          success: (res) => {
            if (res.confirm) { body.force = true; this.save(); }
          },
        });
        return;
      }
      if (!j.ok) { api.toast('未保存：' + (j.error || ''), false); return; }
      if (this.data.editing) {
        api.toast('✓ 已修改保存', true);
        app.globalData.editId = null;
        this.setData({ editing: false, editingId: null });
        wx.switchTab({ url: '/pages/manage/manage' });
      } else {
        api.toast('✓ 已保存，去【背诵】页开背', true);
        this.resetForm();
      }
    }).catch((e) => api.failToast(e));
  },
  resetForm() {
    this.setText('', -1);
    this.setData({ filesView: [], chapter: '', source: '', hot: false, subjectIdx: 0 });
  },

  /* ---------------- 编辑已有词条 ---------------- */
  startEdit(id) {
    api.get('/api/entries').then((j) => {
      const e = (j.entries || []).find((x) => x.id === id);
      if (!e) { api.toast('词条不存在', false); app.globalData.editId = null; return; }
      const si = Math.max(0, this.data.subjects.indexOf(e.subject));
      this.setData({
        editing: true,
        editingId: e.id,
        subjectIdx: si,
        chapter: e.chapter || '',
        source: e.source || '',
        hot: !!e.hot,
      });
      this.setText(e.text, -1);
    }).catch((er) => {
      app.globalData.editId = null;
      api.failToast(er);
    });
  },
  cancelEdit() {
    app.globalData.editId = null;
    this.setData({ editing: false, editingId: null });
    this.resetForm();
  },
});
