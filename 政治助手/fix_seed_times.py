# -*- coding: utf-8 -*-
"""种子词条时间戳对齐真实录入时间（保证同一天内按视频顺序排列）"""
import json
from pathlib import Path

P = Path(r'E:\workspace\政治助手\data\data.json')
data = json.loads(P.read_text(encoding='utf-8'))
order = {'seed001': '2026-11-03T15:50', 'seed002': '2026-11-03T15:50:01', 'seed003': '2026-11-03T15:50:02'}
for e in data['entries']:
    if e['id'] in order:
        e['created'] = order[e['id']]
P.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
print('seed times fixed:', [('%s=%s' % (k, v)) for k, v in order.items()])
