# -*- coding: utf-8 -*-
"""用 difflib 计算两个引擎对同一张图的字符级识别率，结果写入纯 UTF-8 文件避免控制台乱码"""
import subprocess, re, json
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / 'test' / 'sample.png'

EXPECTED = [
    '考点一：物质与意识的辩证关系',
    '1. 物质决定意识，意识是客观存在在人脑中的反映。',
    '2. 意识对物质具有能动的反作用，正确的意识促进事物发展。',
    '【高频】3. 方法论：一切从实际出发，实事求是。',
    '4. 割裂二者的两种错误：古代朴素唯物主义、主观唯心主义。',
    '马原·第二章 | 来源：网课第3讲 2026-11-03',
]

def norm(s):
    return re.sub(r'[\s，。：；·་|.、【】()（）\-—]', '', s)

exp = ''.join(norm(l) for l in EXPECTED)

# ---- RapidOCR ----
from rapidocr_onnxruntime import RapidOCR
eng = RapidOCR()
result, _ = eng(str(IMG))
rapid_text = '\n'.join(line[1] for line in (result or []))

# ---- Windows OCR ----
ps = ROOT / 'ocr_windows.ps1'
r = subprocess.run([
    'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', str(ps), '-Image', str(IMG)
], capture_output=True, timeout=120)
win_text = r.stdout.decode('utf-8', errors='replace').replace('\r', '')

def score(text, name):
    got = ''.join(norm(l) for l in text.splitlines())
    ratio = SequenceMatcher(None, exp, got).ratio() * 100
    return '%s: 字符级相似度 %.1f%% | 识别字符数 %d (应得 %d) | 行数 %d' % (
        name, ratio, len(got), len(exp), len([l for l in text.splitlines() if l.strip()]))

out = []
out.append('===== 原始文本对比（保存为 UTF-8 供 Read 读取）=====')
out.append('')
out.append(score(rapid_text, 'RapidOCR   '))
out.append(score(win_text, 'Windows OCR'))
out.append('')
out.append('----- RapidOCR 输出 -----')
out.append(rapid_text)
out.append('')
out.append('----- Windows OCR 输出 -----')
out.append(win_text)
(ROOT / 'test' / 'ocr_compare-result.txt').write_text('\n'.join(out), encoding='utf-8')
print('written to test/ocr_compare-result.txt')
