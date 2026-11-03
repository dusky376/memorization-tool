# -*- coding: utf-8 -*-
"""向全局复利与踩坑日志追加 G-0023（指纹死链静默跳过）和 G-0024（文档提字管线），
字段格式与现有记录保持一致，分类/类型自动沿用库里已有的值"""
import json
from pathlib import Path

P = Path(r'E:\workspace\全局复利与踩坑日志\records.json')
root = json.loads(P.read_text(encoding='utf-8'))
items = root if isinstance(root, list) else root['records']
ids = {x.get('id') for x in items}
cats = [x.get('category') for x in items if x.get('category')]
types = [x.get('type') for x in items if x.get('type')]
cat = next((c for c in cats if '工程' in c), cats[0] if cats else '工程实施类')
typ = 'pitfall' if 'pitfall' in types else (types[0] if types else 'pitfall')
practice = next((t for t in types if t not in ('pitfall',)), typ)

add = [
    {
        'id': 'G-0023', 'type': typ, 'status': 'active',
        'title': '文件指纹/缓存死链导致静默跳过——失效必须配可见性兜底',
        'category': cat,
        'tags': ['去重', '缓存失效', 'md5', '静默失败', '摄取管道', 'inbox'],
        'date': '2026-11-03', 'source_project': '政治助手',
        'symptom': '同一截图重复丢进收件夹完全没反应：既没有新草稿、也没有任何忽略记录，用户感觉"丢了没反应"。',
        'root_cause': '_processed.json 的 md5→draftId 映射只在"处理过"时写入；草稿被确认后删除或手动丢弃时映射变成死链，扫描 fast-path 只查 key 存在与否(value 死链不检查)，于是静默跳过。',
        'solution': '三层设计：①md5 指纹仅作"已处理见"快路径；②内容查重(文本归一化剥标记符号{}!，互相包含≥80% 或相似度≥0.92)重复者不入库但写「已忽略」记录；③丢弃草稿→忽略面板留痕(带hash可找回/转草稿)＋「全量重扫」按钮释放全部指纹作最终兜底。',
        'lesson': "任何'已处理过'的缓存判定都必须有对应的可见记录和人工释放通道，否则死链静默跳过就是新型的'吞文件'。",
        'scenario': '一切扫描式摄取：收件夹监听、爬虫增量、ETL 幂等表',
        'method': 'test/test_dedup_docs.py 14 条端到端断言(world缩放绕指纹/确认拒绝/保存拒绝/force通道/恢复/清空/重扫)',
        'effect': '重复丢图不再生成重复草稿；误判可一键转回草稿；静默跳过消亡。',
        'related_ids': ['G-0022'], 'links': ['E:\\workspace\\政治助手\\server.py', 'E:\\workspace\\政治助手\\static\\arrange.html'],
    },
    {
        'id': 'G-0024', 'type': practice, 'status': 'active',
        'title': 'PDF/Word/txt 提字：文字层逐页混合+OCR兜底，直接复用已有摄取管道',
        'category': cat,
        'tags': ['PDF', 'pypdf', 'pypdfium2', 'python-docx', 'OCR', '扫描件'],
        'date': '2026-11-03', 'source_project': '政治助手',
        'symptom': '',
        'root_cause': '',
        'solution': '扫描白名单加 pdf/docx/txt/md；PDF 用 pypdf 逐页抽文字层，空白/扫描页用 pypdfium2 render(scale=2.2) 转图走既有 RapidOCR，逐页混合拼接；OCR 页数上限(40/份)+总量截断(2万字)防后台扫描线程被大文件卡死。测试无报告库时用 PIL ImageDraw 画中文(msyh.ttc)生成无文字层 PDF 打 OCR 路径。',
        'lesson': '文档支持不要另起炉灶：在既有 图片管道 上加扩展名分支即可，草稿/查重/时间排序/忽略面板全部免费获得；但必须给 OCR 兜底设页数上限。',
        'scenario': "任何'丢文件自动提字'型助手",
        'method': 'pip -i tsinghua 装了 pypdf + pypdfium2 + python-docx',
        'effect': '扫描版 PDF/Word/txt 全部走通，手机录入页直传文档也通。',
        'related_ids': ['G-0020'], 'links': ['E:\\workspace\\政治助手\\server.py'],
    },
]
for rec in add:
    if rec['id'] not in ids:
        items.append(rec)
if isinstance(root, list):
    json.dump(items, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    root['records'] = items
    json.dump(root, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('total now', len(items), '| ids tail:', [x['id'] for x in items[-2:]])
