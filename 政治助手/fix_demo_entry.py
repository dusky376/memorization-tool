# -*- coding: utf-8 -*-
"""修复演示入库条目的嵌套标记，规范为清晰考点挖空"""
import json
from pathlib import Path

P = Path(r'E:\workspace\政治助手\data\data.json')
data = json.loads(P.read_text(encoding='utf-8'))
GOOD = ('二、考点一：物质与意识的辩证关系（马原）\n'
        '1. {{!物质决定意识}}，意识是客观存在在人脑中的反映。\n'
        '2. 意识对物质具有{{!能动的反作用}}，正确的意识促进事物发展。\n'
        '3. 【方法论】一切从实际出发，{{!实事求是}}。\n'
        '4. 割裂二者的两种错误：{{!古代朴素唯物主义}}、{{!主观唯心主义}}。\n'
        '(来源：网课第3讲 2026-11-03)')
for e in data['entries']:
    if e['id'] == 'e2611031615267f34':
        e['text'] = GOOD
P.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
print('fixed entry marks:', GOOD.count('{{'))
