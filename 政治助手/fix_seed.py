# -*- coding: utf-8 -*-
"""修补 data.json 中 seed001 被 f-string 吞花括号的标记语法（保留复习进度）"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data' / 'data.json'
data = json.loads(DATA.read_text(encoding='utf-8'))

GOOD_1ST = ('二、六个必须坚持\n'
            '"{{!六个必须坚持}}"是习近平新时代中国特色社会主义思想的{{世界观}}、'
            '{{!方法论}}和贯穿其中的{{!立场观点方法}}的重要体现。\n')

for e in data['entries']:
    if e['id'] == 'seed001':
        lines = e['text'].split('\n')
        # 保留其余行，仅替换前 2 行（首行 + 总述句）
        rest = lines[2:]
        e['text'] = GOOD_1ST + '\n'.join(rest)

DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
print('patched seed001; marks:', e['text'].count('{{') + e['text'].count('{{!'))
