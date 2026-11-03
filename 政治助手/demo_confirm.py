# -*- coding: utf-8 -*-
"""演示：把当前草稿自动挖空并入库（等价于整理页点「✨自动挖空」+「✓入库」）"""
import json, urllib.request

BASE = 'http://127.0.0.1:8686'

drafts = json.loads(urllib.request.urlopen(BASE + '/api/drafts').read().decode('utf-8'))['drafts']
d = drafts[0]
text = d['text']
# 把候选词（长词优先）包成 {{!...}}，等价前端 autoMark()
for c in sorted(d.get('candidates', []), key=len, reverse=True):
    if not c or len(c) < 2:
        continue
    if '{{' + c + '}}' in text or '{{!' + c + '}}' in text:
        continue
    i = text.find(c)
    if i >= 0:
        text = text[:i] + '{{!' + c + '}}' + text[i + len(c):]

body = {
    'id': d['id'],
    'subject': d['subject'],
    'chapter': '物质与意识的辩证关系',
    'source': '网课第3讲',
    'hot': True,
    'text': text,
}
req = urllib.request.Request(BASE + '/api/draft_confirm',
                             data=json.dumps(body).encode('utf-8'),
                             headers={'Content-Type': 'application/json'})
r = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
print('confirm:', r)

today = json.loads(urllib.request.urlopen(BASE + '/api/today').read().decode('utf-8'))
out = ['today queue=%d stats=%s' % (len(today['queue']), today['stats'])]
for e in today['queue']:
    out.append('  - %s | %s | marks=%d' % (e['id'], e['chapter'] or plain, e['text'].count('{')))
print('\n'.join(out))
