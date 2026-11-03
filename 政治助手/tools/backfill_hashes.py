# -*- coding: utf-8 -*-
"""一次性回填：把已归档截图的 md5 指纹写入 processed.json，
防止用户把同样的截图再丢一次时生成重复草稿"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / 'screenshots' / 'inbox_done'
P = ROOT / 'data' / 'processed.json'

processed = json.loads(P.read_text(encoding='utf-8')) if P.exists() else {}
drafts = json.loads((ROOT / 'data' / 'drafts.json').read_text(encoding='utf-8'))
img2id = {}
for d in drafts:
    if d.get('img'):
        img2id[Path(d['img']).name] = d['id']

n0 = len(processed)
for f in ARCH.glob('*'):
    if f.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
        continue
    h = hashlib.md5(f.read_bytes()).hexdigest()
    if h not in processed:
        processed[h] = img2id.get(f.name, 'arch-' + h[:10])

P.write_text(json.dumps(processed, ensure_ascii=False, indent=1), encoding='utf-8')
print('backfill: %d -> %d hashes' % (n0, len(processed)))
