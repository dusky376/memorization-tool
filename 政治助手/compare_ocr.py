# -*- coding: utf-8 -*-
"""生成仿网课PPT测试图，对比 RapidOCR 与 Windows 自带 OCR 的识别质量和速度"""
import subprocess, sys, time, statistics
from pathlib import Path

ROOT = Path(__file__).parent
TEST_IMG = ROOT / 'test' / 'sample.png'
TEST_IMG.parent.mkdir(exist_ok=True)

# ---------- 1. 生成测试图（PPT 风格：标题+正文+红字）----------
from PIL import Image, ImageDraw, ImageFont

if not TEST_IMG.exists():
    W, H = 960, 420
    img = Image.new('RGB', (W, H), (252, 252, 248))
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 30)
    f_body = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 24)
    f_small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20)
    d.rectangle([0, 0, W, 64], fill=(198, 40, 40))
    d.text((24, 14), '考点一：物质与意识的辩证关系', font=f_title, fill=(255, 255, 255))
    d.text((40, 90), '1. 物质决定意识，意识是客观存在在人脑中的反映。', font=f_body, fill=(40, 40, 40))
    d.text((40, 145), '2. 意识对物质具有能动的反作用，正确的意识促进事物发展。', font=f_body, fill=(40, 40, 40))
    d.text((40, 200), '【高频】3. 方法论：一切从实际出发，实事求是。', font=f_body, fill=(198, 40, 40))
    d.text((40, 260), '4. 割裂二者的两种错误：古代朴素唯物主义、主观唯心主义。', font=f_body, fill=(40, 40, 40))
    d.text((40, 340), '马原·第二章 | 来源：网课第3讲 2026-11-03', font=f_small, fill=(150, 150, 150))
    img.save(TEST_IMG)
    print('测试图已生成:', TEST_IMG)

# ---------- 2. RapidOCR ----------
from rapidocr_onnxruntime import RapidOCR
engine = RapidOCR()
times_r, text_r = [], []
for _ in range(3):
    t0 = time.perf_counter()
    result, _ = engine(str(TEST_IMG))
    times_r.append(time.perf_counter() - t0)
    text_r.append('\n'.join(line[1] for line in (result or [])))

# ---------- 3. Windows 自带 OCR ----------
def win_ocr(path):
    ps = ROOT / 'ocr_windows.ps1'
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                        '-File', str(ps), '-Image', str(path)],
                       capture_output=True, timeout=120)
    return r.stdout.decode('utf-8', errors='replace')

times_w = []
for _ in range(3):
    t0 = time.perf_counter()
    text_w_raw = win_ocr(TEST_IMG)
    times_w.append(time.perf_counter() - t0)

# ---------- 4. 结果 ----------
line = '-' * 56
print(line)
print('基准文本（图中实际文字）:')
print('  考点一：物质与意识的辩证关系')
print('  1. 物质决定意识，意识是客观存在在人脑中的反映。')
print('  2. 意识对物质具有能动的反作用，正确的意识促进事物发展。')
print('  【高频】3. 方法论：一切从实际出发，实事求是。')
print('  4. 割裂二者的两种错误：古代朴素唯物主义、主观唯心主义。')
print(line)
print('RapidOCR 三次耗时: %s  平均 %.2fs' % (['%.2f' % t for t in times_r], statistics.mean(times_r)))
print(text_r[-1])
print(line)
print('WindowsOCR 三次耗时: %s  平均 %.2fs（首次可能偏慢）' % (['%.2f' % t for t in times_w], statistics.mean(times_w)))
print(text_w_raw)
