# -*- coding: utf-8 -*-
"""把本次项目确认跨项目通用的经验蒸馏进全局 records.json（程序化追加，禁止手写 JSON）"""
import json
from copy import deepcopy
from pathlib import Path

REC = Path(r'E:\workspace\全局复利与踩坑日志\records.json')
P = '政治助手'
D = '2026-11-03'

new = [
    {
        'id': 'G-0020', 'type': 'compounding', 'status': 'active',
        'title': 'Windows 自带 OCR 中文弱、开源 RapidOCR 直接 pip 就能用：先同图实测再定引擎',
        'category': '工具与编码',
        'tags': ['OCR', 'RapidOCR', 'PaddleOCR', 'onnxruntime', '截图提字', '中文识别'],
        'date': D, 'source_project': P,
        'symptom': 'Windows.Media.Ocr 识别中文截图：逐字碎开夹空格、错字（方法论→氵去论、错误→钅昔误）、破折号变"一"。',
        'root_cause': 'WinRT 自带 OCR 对 CJK 分词粒度差、字体渲染敏感；93.7% 字符级相似度且行结构需二次清洗，不可直用。',
        'solution': '主引擎 pip install rapidocr_onnxruntime（PaddleOCR 模型+onnxruntime，模型捆绑在 wheel，装完离线可用，国内装要 -i 清华源）；CPU 稳定 ~1.2s/张、同图 100% 全对。Windows OCR 保留 switch 兜底模式。',
        'lesson': '选 OCR 引擎别看宣传，写 15 行同图对比脚本（difflib 相似度+耗时+读宏图输出到 UTF-8 文件）拿数据说话。',
        'scenario': '截图提字 / 中文 OCR / 零依赖本地识别',
        'method': '同图 3 次 × 引擎 × 字符相似度（difflib.SequenceMatcher）× 平均耗时；结果写文件避免控制台 GBK 乱码',
        'effect': '政治助手项目 OCR 主链路一次到位，用户截图→可背文本零手打',
        'related_ids': ['G-0001'], 'links': [r'E:\workspace\政治助手\test\check_acc.py', r'E:\workspace\政治助手\test\ocr_compare-result.txt'],
    },
    {
        'id': 'G-0021', 'type': 'pitfall', 'status': 'active',
        'title': 'f-string 会吞 {{...}} 挖空/模板标记：含双花括号文本必须禁用 f-string',
        'category': '工具与编码',
        'tags': ['f-string', '花括号', '模板标记', '数据损坏', 'python'],
        'date': D, 'source_project': P,
        'symptom': '种子数据生成后前端"挖空标红"失效，接口返回里 {{!六个必须坚持}} 变成单花括号 {!...}。',
        'root_cause': 'f-string 中 {{ 渲染为字面 { ，本想输出 {{!词}} 的标记被减半；同时 f-string 外拼中文产生重复词。',
        'solution': '凡含自定义双花括号标记（模板/挖空语法）的字符串一律用 + 或普通 string 拼接，禁止 f-string；生成后加断言验证标记数量。',
        'lesson': '自定义标记语法和 f-string 的转义规则天然冲突，写数据生成器前先定规矩。',
        'scenario': '生成带模板标记的文本数据 / 任何自定义双花括号 DSL',
        'method': '', 'effect': '',
        'related_ids': [], 'links': [r'E:\workspace\政治助手\make_seed.py'],
    },
    {
        'id': 'G-0022', 'type': 'pitfall', 'status': 'active',
        'title': 'PS5.1 里 curl 是 Invoke-WebRequest 别名：请求要用 curl.exe',
        'category': '工具与编码',
        'tags': ['PowerShell', 'curl', '别名', 'Invoke-WebRequest', '冒烟测试'],
        'date': D, 'source_project': P,
        'symptom': '在 PS5.1 执行 curl 想做 API 冒烟测试，行为与预期不符（-F 表单上传语义不同）。',
        'root_cause': 'PowerShell 5.1 将 curl 预定义为 Invoke-WebRequest 的别名，不是真 curl。',
        'solution': '冒烟测试显式写 curl.exe；验证结果一律 -o 写入文件再读，避免控制台 GBK 乱码。',
        'lesson': 'PS 里调外部工具一律带扩展名，绕开内置别名。',
        'scenario': 'Windows 接口冒烟 / 脚本化 curl',
        'method': '', 'effect': '',
        'related_ids': ['G-0001'], 'links': [],
    },
]

data = json.loads(REC.read_text(encoding='utf-8'))
have = {r['id'] for r in data['records']}
added = 0
for n in new:
    if n['id'] not in have:
        data['records'].append(n)
        added += 1
data['updated'] = D
tmp = REC.with_suffix('.tmp')
tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
tmp.replace(REC)
print('added %d records; total %d' % (added, len(data['records'])))
