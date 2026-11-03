# -*- coding: utf-8 -*-
"""一次性数据修复：把库里「没有任何挖空标记」的词条补标。
优先从 shots/inbox/archived 截图里按文本相似度找回原图 → 用新红标引擎重出文本；
找不到原图则退化为对现有文本套热词挖空。用户已标注过的词条绝不触碰。"""
import difflib
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, r'E:\workspace\政治助手')
import server

BASE = 'http://127.0.0.1:8686'
ROOT = Path(r'E:\workspace\政治助手')
SHOTS, INBOX, ARCHIVE = ROOT / 'screenshots', ROOT / 'inbox', ROOT / 'screenshots' / 'inbox_done'


def call(path, data=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode('utf-8') if data is not None else None,
        headers={'Content-Type': 'application/json'})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=180).read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8'))
        except Exception:
            return {'ok': False, 'http': e.code}


def norm(s):
    return server.norm_text(s or '')


entries = call('/api/entries').get('entries', [])
# 强制重标白名单：本来有标记但要把旧引擎的断字标记重做成新引擎的；用户手动编辑过的词条绝不能进来
FORCE_REDO = {'e261103170029fc81'}
Todo = [e for e in entries
        if not server.count_marks(e.get('text') or '') or e['id'] in FORCE_REDO]
print('词条 %d 条，其中需补标/强制重标 %d 条：' % (len(entries), len(Todo)))
for e in Todo:
    print('  - %s [%s] %s' % (e['id'], e.get('subject'), (e['text'] or '')[:24].replace('\n', ' / ')))
if not Todo:
    print('没有需要补标的词条。')
    sys.exit(0)

src_imgs = [(p, folder) for folder in (SHOTS, INBOX, ARCHIVE)
            for p in sorted(list(folder.glob('*.png')) + list(folder.glob('*.jpg')))
            if not (p.name.startswith('红标') or p.name.startswith('查重测试'))]
# 去重（archive 里的可能同时存在于 shots）
seen, imgs = set(), []
for p, folder in src_imgs:
    key = (p.stat().st_size, p.name)
    if key in seen or p.name in seen:
        continue
    seen.add(p.name)
    imgs.append((p, folder))
print('候选原图 %d 张，逐张 OCR 比对中（每张约几秒）…' % len(imgs))

analyzed = {}
for p, folder in imgs:
    try:
        text, reds, used = server.analyze_image(str(p))
        analyzed[str(p)] = text
    except Exception as e:
        analyzed[str(p)] = ''
        print('  [跳过] %s: %s' % (p.name, str(e)[:60]))

used_imgs = set()
for e in Todo:
    et = norm(e['text'])
    if not et:
        continue
    best, bsim = None, 0.0
    for sp, tx in analyzed.items():
        if sp in used_imgs or not tx:
            continue
        sim = difflib.SequenceMatcher(None, et, norm(tx)).ratio()
        if sim > bsim:
            best, bsim = sp, sim
    if best and bsim >= 0.50:
        p = Path(best)
        marked = analyzed[best]
        used_imgs.add(best)
        body = {'id': e['id'], 'subject': e.get('subject') or '未分类',
                'chapter': e.get('chapter', ''), 'source': e.get('source', '') or p.name,
                'text': marked}
        r = call('/api/entry_save', body)
        ok = r.get('ok')
        print('  [重标+%d处挖空] %s ← 匹配原图 %s 相似度%.2f %s'
              % (server.count_marks(marked), e['id'], p.name, bsim, '✓已保存' if ok else '✗' + str(r)[:60]))
    else:
        # 退化：找不到可信原图 → 对现有文本套热词自动挖空（不换文本，避免损坏用户内容）
        words = server._quote_candidates(e['text'])
        if words:
            new = server._wrap_words(e['text'], words)
            r = call('/api/entry_save', {'id': e['id'], 'subject': e.get('subject') or '未分类',
                                         'chapter': e.get('chapter', ''), 'source': e.get('source', ''),
                                         'text': new})
            print('  [热词补标+%d处] %s 相似度不足(%.2f)，仅按热词挖空 %s'
                  % (server.count_marks(new), e['id'], bsim, '✓' if r.get('ok') else '✗' + str(r)[:60]))
        else:
            print('  [跳过] %s 没找到原图(最高相似度%.2f)也无热词可挖' % (e['id'], bsim))

after = call('/api/entries').get('entries', [])
left = [e['id'] for e in after if not server.count_marks(e.get('text') or '')]
print('完成。剩余未标注词条：%s' % (left or '无'))
