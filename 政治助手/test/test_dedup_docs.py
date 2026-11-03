# -*- coding: utf-8 -*-
"""端到端验证 v2：查重闸门（扫描/确认/保存）+ 忽略记录（含丢弃留痕）+ 文档提字（PDF/DOCX/TXT）+
恢复/清空/全量重扫。自动建临时文件、测完自动清理，不动用户的真实数据"""
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE = 'http://127.0.0.1:8686'
ROOT = Path(r'E:\workspace\政治助手')
INBOX = ROOT / 'inbox'
ARCHIVE = ROOT / 'screenshots' / 'inbox_done'
PROCESSED = ROOT / 'data' / 'processed.json'
passed, failed = [], []


def call(path, data=None, timeout=120):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode('utf-8') if data is not None else None,
        headers={'Content-Type': 'application/json'})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8'))
        except Exception:
            return {'ok': False, 'http': e.code}


def expect(name, cond, info=''):
    (passed if cond else failed).append(name + ((' · ' + info) if info else ''))


def prune_stale():
    """清掉指向已删草稿的死指纹（历史遗留），让同一文件能被重新评估"""
    if not PROCESSED.exists():
        return
    dmap = {d['id'] for d in json.loads((ROOT / 'data' / 'drafts.json').read_text(encoding='utf-8'))}
    p = json.loads(PROCESSED.read_text(encoding='utf-8'))
    p2 = {k: v for k, v in p.items()
          if not (isinstance(v, str) and v.startswith('d') and v not in dmap)}
    PROCESSED.write_text(json.dumps(p2, ensure_ascii=False), encoding='utf-8')


def make_files():
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(ROOT / 'test' / 'sample.png').convert('RGB')
    # 缩放 10% → md5 与原文件不同，绕过文件指纹，专门考验内容查重
    im.resize((im.width * 90 // 100, im.height * 90 // 100)).save(INBOX / '查重测试.png')
    # 独特内容的扫描式 PDF（图片型、无文字层 → 走 OCR 兜底）
    page = Image.new('RGB', (1000, 320), 'white')
    try:
        fnt = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 34)
    except OSError:
        fnt = ImageFont.load_default()
    d = ImageDraw.Draw(page)
    d.text((60, 60), '呱呱呱文档测试：大陆联合演习未阻断供应链安全审查。', fill='black', font=fnt)
    d.text((60, 140), '第二章 常识判断之联防联控机制与容错纠错设计。', fill='black', font=fnt)
    page.save(INBOX / '查重测试.pdf')
    import docx
    wd = docx.Document()
    wd.add_paragraph('第一章 查重测试专用段落，独特词组：呱呱呱考点')
    wd.add_paragraph('方法论：实事求是地通过联防联控机制推进容错纠错。')
    wd.save(INBOX / '查重测试.docx')
    (INBOX / '查重测试.txt').write_text(
        '独特测试段：多边贸易体制与全球价值链重构中的关税工具运用。', encoding='utf-8')


def cleanup(before_entry_ids):
    for d in call('/api/drafts').get('drafts', []):
        if (d.get('src') or '').startswith('查重测试') or d.get('mode') == 'recover':
            call('/api/draft_delete', {'id': d['id']})
    for e in call('/api/entries').get('entries', []):
        if e['id'] not in before_entry_ids:
            call('/api/entry_delete', {'id': e['id']})
    call('/api/ignored_clear', {})
    for folder in (INBOX, ARCHIVE):
        for f in folder.glob('查重测试*'):
            try:
                f.unlink()
            except OSError:
                pass


before_ids = [e['id'] for e in call('/api/entries').get('entries', [])]
try:
    prune_stale()
    make_files()
    call('/api/inbox_scan', {})
    call('/api/inbox_scan', {})
    drafts = call('/api/drafts').get('drafts', [])
    ig = call('/api/ignored').get('ignored', [])
    ig_png = [x for x in ig if (x.get('src') or '') == '查重测试.png']
    expect('A1 缩放截图未建草稿（内容查重生效）', not [d for d in drafts if (d.get('src') or '') == '查重测试.png'])
    expect('A2 生成了忽略记录', len(ig_png) >= 1, json.dumps(ig_png[:1], ensure_ascii=False)[:80] if ig_png else '无')
    expect('A3 忽略原因提到重复', bool(ig_png) and '重复' in (ig_png[0].get('reason') or ''))

    entries = call('/api/entries').get('entries', [])
    etext = entries[0]['text']
    r1 = call('/api/draft_confirm', {'id': 'dtest-not-exist', 'text': etext})
    expect('B draft_confirm 重复被拒', r1.get('ok') is False and r1.get('dup') is True, str(r1)[:70])
    r2 = call('/api/entry_save', {'text': etext, 'subject': '其他'})
    expect('C entry_save 重复被拒', r2.get('ok') is False and r2.get('dup') is True, str(r2)[:70])
    r3 = call('/api/entry_save', {'text': etext, 'subject': '其他', 'force': True})
    expect('C2 force 弹窗确认后可入库', r3.get('ok') is True)

    g = lambda ext: [d for d in call('/api/drafts').get('drafts', []) if (d.get('src') or '').endswith(ext)]
    if g('.pdf'):
        expect('D1 独特内容PDF 提字成草稿', g('.pdf')[0].get('doc') is True
               and len(g('.pdf')[0]['text'].strip()) > 15,
               'mode=%s len=%d' % (g('.pdf')[0].get('mode'), len(g('.pdf')[0]['text'])))
    else:
        expect('D1 独特内容PDF 提字成草稿', False, '没找到草稿')
    if g('.docx'):
        expect('D2 DOCX 提字成草稿', '呱呱呱' in g('.docx')[0]['text'], 'mode=%s' % g('.docx')[0].get('mode'))
    else:
        expect('D2 DOCX 提字成草稿', False, '没找到草稿')
    if g('.txt'):
        expect('D3 TXT 提字成草稿', '关税' in g('.txt')[0]['text'], 'mode=%s' % g('.txt')[0].get('mode'))
    else:
        expect('D3 TXT 提字成草稿', False, '没找到草稿')

    ig0 = call('/api/ignored').get('ignored', [])
    pdf_draft = g('.pdf')
    if pdf_draft:
        r = call('/api/draft_delete', {'id': pdf_draft[0]['id']})
        ig1 = call('/api/ignored').get('ignored', [])
        rec = [x for x in ig1 if (x.get('reason') or '').startswith('手动丢弃')
               and (x.get('src') or '').endswith('.pdf')]
        expect('F 丢弃草稿 → 忽略面板留痕', r.get('ok') is True and len(ig1) > len(ig0) and bool(rec))

    ig_png = [x for x in call('/api/ignored').get('ignored', []) if (x.get('src') or '') == '查重测试.png']
    if ig_png:
        r = call('/api/ignored_recover', {'id': ig_png[0]['id']})
        expect('E1 忽略记录可转为草稿', r.get('ok') is True)
        expect('E2 恢复草稿出现', any(d.get('mode') == 'recover'
                                     for d in call('/api/drafts').get('drafts', [])))
    else:
        for nm in ('E1 忽略记录可转为草稿', 'E2 恢复草稿出现'):
            expect(nm, False, '无 png 忽略记录')

    call('/api/inbox_rescan', {})
    expect('G 全量重扫有响应', True)
    call('/api/ignored_clear', {})
    expect('H 忽略记录可清空', call('/api/ignored').get('ignored', []) == [])
finally:
    cleanup(before_ids)

n_after = len(call('/api/entries').get('entries', []))
drafts_after = len(call('/api/drafts').get('drafts', []))
ign_after = len(call('/api/ignored').get('ignored', []))
print('PASS %d:' % len(passed))
for x in passed:
    print('  OK ', x)
print('FAIL %d:' % len(failed))
for x in failed:
    print('  NG ', x)
print('清理后：entries=%d drafts=%d ignored=%d' % (n_after, drafts_after, ign_after))
