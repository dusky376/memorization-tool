# -*- coding: utf-8 -*-
"""端到端验证 v3：截图红标自动挖空（红字 / 红下划线 / 同行碎片合并秩序）+ 旧接口回归 +
编辑保高频 + 编辑查重复拒 + 真实截图逐张打印红标结果（供人工比对红标引擎）。
自动建临时素材、测完清理，绝不碰用户真实数据（含「已忽略」面板里用户自己的记录）。"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = 'http://127.0.0.1:8686'
ROOT = Path(r'E:\workspace\政治助手')
INBOX = ROOT / 'inbox'
SHOTS = ROOT / 'screenshots'
ARCHIVE = SHOTS / 'inbox_done'
TMP = ROOT / 'test'
TAG = '红标t'   # 测试素材统一前缀，清理只认它
passed, failed = [], []


def call(path, data=None, timeout=180):
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


def upload(path, fname, fbytes, field='image', timeout=180):
    # 文件名一定用 ASCII：multipart 头里塞中文会导致 werkzeug 解析不到文件
    # 收尾边界前必须有 CRLF，否则 werkzeug 把整个 part 丢弃 → 'no file'
    b = uuid.uuid4().hex[:8]
    safe = 'up' + uuid.uuid4().hex[:5] + (Path(fname).suffix.lower() if '.' in fname else '.png')
    parts = [
        ('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
         'Content-Type: application/octet-stream\r\n\r\n' % (b, field, safe)).encode('ascii'),
        fbytes,
        ('\r\n--%s--\r\n' % b).encode('ascii')]
    req = urllib.request.Request(BASE + path, data=b''.join(parts), headers={
        'Content-Type': 'multipart/form-data; boundary=%s' % b})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8'))
        except Exception:
            return {'ok': False, 'http': e.code}


def prune_stale():
    """清掉指向已删草稿的死指纹（历史遗留），让同一文件能被重新评估（可重复跑本测试）"""
    pf = ROOT / 'data' / 'processed.json'
    if not pf.exists():
        return
    dmap = {d['id'] for d in json.loads((ROOT / 'data' / 'drafts.json').read_text(encoding='utf-8'))}
    p = json.loads(pf.read_text(encoding='utf-8'))
    p2 = {k: v for k, v in p.items()
          if not (isinstance(v, str) and v.startswith('d') and v not in dmap)}
    pf.write_text(json.dumps(p2, ensure_ascii=False), encoding='utf-8')


def expect(name, cond, info=''):
    (passed if cond else failed).append(name + ((' · ' + info) if info else ''))


def make_red_png():
    """三合一考题 PNG：
    · 第 2 行红字       → 验红字识别
    · 第 3 行黑字+红下划线 → 验下划线识别
    · 第 4 行左右两段一次排（左黑右红） → 验同行碎片合并 + 行内部分红"""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new('RGB', (1100, 460), 'white')
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 34)
    except OSError:
        f = ImageFont.load_default()
    RED, BLACK = (200, 30, 30), (30, 30, 30)
    d.text((60, 40), '第四章 建设社会主义现代化强国', fill=BLACK, font=f)
    d.text((60, 150), '改革创新是最大的活力。', fill=RED, font=f)
    d.text((60, 260), '健全联防联控机制与容错纠错机制。', fill=BLACK, font=f)
    d.line((55, 298, 651, 298), fill=RED, width=6)
    d.text((60, 370), '建成教育强国、科技强国、', fill=BLACK, font=f)
    d.text((470, 370), '文化强国、体育强国、健康中国。', fill=RED, font=f)
    p = TMP / 'redred_tmp.png'
    p.parent.mkdir(exist_ok=True)
    im.save(p)
    return p, p.read_bytes()


def snapshot_shots():
    """记录测试前的截图目录文件，测完删掉测试期间新增的（/api/ocr 会存副本）"""
    return {p.name for d in (SHOTS, ARCHIVE) for p in d.glob('*') if p.is_file()}


def cleanup(shot_before):
    for d in call('/api/drafts').get('drafts', []):
        if (d.get('src') or '').startswith(TAG):
            call('/api/draft_delete', {'id': d['id']})
    # 只摘掉本次测试的忽略记录，用户的记录原样保留
    igf = ROOT / 'data' / 'ignored.json'
    if igf.exists():
        cur = json.loads(igf.read_text(encoding='utf-8'))
        keep = [x for x in cur if not (x.get('src') or '').startswith(TAG)]
        if len(keep) != len(cur):
            igf.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding='utf-8')
    for folder in (INBOX, ARCHIVE):
        for f in folder.glob(TAG + '*'):
            try:
                f.unlink()
            except OSError:
                pass
    # 守护扫描线程每 5s 扫一遍 inbox，可能跟上面的清理竞态——隔半秒再补一刀
    time.sleep(1.2)
    for folder in (INBOX, ARCHIVE):
        for f in folder.glob(TAG + '*'):
            try:
                f.unlink()
            except OSError:
                pass
    for p in SHOTS.glob('*'):
        if p.name not in shot_before and p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    for f in TMP.glob('redred_tmp.png'):
        try:
            f.unlink()
        except OSError:
            pass


shot_before = snapshot_shots()
seed001, seed002 = None, None
try:
    prune_stale()
    # ---------------- A. 真实截图逐张验证：打印红标结果供人工比对 ----------------
    print('==== A. 真实截图 /api/ocr 红标结果 ====')
    shots = sorted(ARCHIVE.glob('*.png')) + sorted(ARCHIVE.glob('*.jpg'))
    for p in shots:
        r = upload('/api/ocr', p.name, p.read_bytes())
        if not r.get('ok'):
            print('[%s] 识别失败: %s' % (p.name, r))
            expect('A0 ' + p.name + ' 识别成功', False, str(r)[:80])
            continue
        reds = r.get('reds') or []
        print('[%s] auton=%d 红标=%d个' % (p.name, r.get('auton') or 0, len(reds)))
        print('    红标词: ' + ' | '.join(reds[:20]))
        for ln in (r.get('text') or '').split('\n')[:8]:
            print('    | ' + ln[:60])
        expect('A0 ' + p.name + ' 识别成功', len(r.get('text') or '') > 10)

    # ---------------- B. 合成图全流程：inbox → 草稿(自动挖空) → 弃稿留痕 ----------------
    print('==== B. 合成红标图全流程 ====')
    p_png, p_bytes = make_red_png()
    (INBOX / (TAG + '三合一.png')).write_bytes(p_bytes)
    call('/api/inbox_scan', {})
    drafts = call('/api/drafts').get('drafts', [])
    ds = [d for d in drafts if (d.get('src') or '').startswith(TAG)]
    if not ds:
        expect('B1 草稿生成', False, '没找到前缀 ' + TAG + ' 的草稿')
    else:
        d = ds[0]
        t = d.get('text') or ''
        print('    draft auton=%d reds=%s' % (d.get('auton') or 0, json.dumps(d.get('candidates') or [], ensure_ascii=False)[:200]))
        print('    text:')
        for ln in t.split('\n'):
            print('      | ' + ln[:80])
        expect('B1 草稿生成', True)
        expect('B2 自动挖空数>=3', (d.get('auton') or 0) >= 3, 'auton=%s' % d.get('auton'))
        expect('B3 红下划线被识别', bool(re.search(r'\{\{![^{}]*联防联控', t)))
        expect('B4 红字行被识别', '{{!改革创新' in t)
        expect('B5 同行碎片x序合并',
               0 <= t.find('建成教育强国、科技强国、') < t.find('文化强国'),
               'finds=%d,%d' % (t.find('建成教育强国、科技强国、'), t.find('文化强国')))
        expect('B6 行内右半红被识别', '{{!文化强国' in t)
        expect('B7 阅读顺序正确',
               0 <= t.find('第四章') < t.find('改革创新') < t.find('健全联防联控')
               < t.find('建成教育强国'),
               'finds=%d,%d,%d,%d' % (t.find('第四章'), t.find('改革创新'),
                                      t.find('健全联防联控'), t.find('建成教育强国')))
        expect('B8 /api/ocr 返回 auton 字段', 'auton' in upload('/api/ocr', TAG + 'a.png', p_bytes))
        r0 = call('/api/draft_remark', {'id': 'dnotexist000test'})
        expect('B9 draft_remark 不存在id 报404语义', r0.get('ok') is False, str(r0)[:60])
    # ---------------- C. 编辑流程：保高频 + 查重自斥 ----------------
    print('==== C. 词条编辑流程 ====')
    entries = call('/api/entries').get('entries', [])
    sm = {e['id']: e for e in entries}
    seed001, seed002 = sm.get('seed001'), sm.get('seed002')
    if not (seed001 and seed002):
        expect('C0 种子词条存在', False, 'seed001/seed002 缺失')
    else:
        body = {'id': seed001['id'], 'subject': seed001['subject'],
                'chapter': seed001['chapter'], 'source': seed001['source'],
                'text': seed001['text'] + '\n[红标t编辑校验]'}   # 故意不带 hot → 应保留原高频
        r = call('/api/entry_save', body)
        e_now = {e['id']: e for e in call('/api/entries').get('entries', [])}.get('seed001', {})
        expect('C1 编辑保存成功', r.get('ok') is True, str(r)[:60])
        expect('C2 编辑不带hot也保高频', e_now.get('hot') is True, 'hot=%s' % e_now.get('hot'))
        r2 = call('/api/entry_save', {'id': seed001['id'], 'subject': '毛中特', 'text': seed002['text']})
        expect('C3 编辑成别的词条内容→查重拒', r2.get('ok') is False and r2.get('dup') is True, str(r2)[:70])
finally:
    if seed001:
        call('/api/entry_save', {'id': seed001['id'], 'subject': seed001['subject'],
                                 'chapter': seed001['chapter'], 'source': seed001['source'],
                                 'hot': seed001.get('hot'), 'text': seed001['text'], 'force': True})
    cleanup(shot_before)

n = len(call('/api/entries').get('entries', []))
print('PASS %d:' % len(passed))
for x in passed:
    print('  OK ', x)
print('FAIL %d:' % len(failed))
for x in failed:
    print('  NG ', x)
print('用户词条数（应还原）=%d' % n)
