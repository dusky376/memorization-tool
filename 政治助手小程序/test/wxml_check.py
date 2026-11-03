# -*- coding: utf-8 -*-
"""政治助手小程序 - WXML 静态校验（交付前自测）。
中文结果写 test/report.txt（UTF-8），控制台只打 ASCII（避开 GBK 控制台坑）。"""
import re
import sys
from pathlib import Path

ROOT = Path(r"E:\workspace\政治助手小程序")
SELF_CLOSED = {"input", "image", "checkbox", "radio", "switch", "slider", "progress", "icon"}
FORBIDDEN = {"small", "br", "span", "button", "img", "b", "i", "u"}

errors = []
summary = []

for wxml in sorted(ROOT.rglob("*.wxml")):
    rel = str(wxml.relative_to(ROOT))
    src = wxml.read_text(encoding="utf-8")
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)          # 去注释
    if not src.strip():
        summary.append("  (empty) " + rel)
        continue

    # ---- 表达式配对：{{ }} 成对，且表达式内部引号闭合 ----
    n_open = len(re.findall(re.escape("{{"), src))
    n_close = len(re.findall(re.escape("}}"), src))
    if n_open != n_close:
        errors.append(rel + ": 大括号不配对 {{ x" + str(n_open) + " vs }} x" + str(n_close))
    for i, m in enumerate(re.finditer(re.escape("{{") + r"(.+?)" + re.escape("}}"), src, flags=re.S), 1):
        expr = m.group(1)
        if "'" in expr and expr.count("'") % 2 != 0:
            errors.append(rel + ": 第" + str(i) + "个表达式单引号不闭合 -> " + expr.strip()[:40])
        if '"' in expr and expr.count('"') % 2 != 0:
            errors.append(rel + ": 第" + str(i) + "个表达式双引号不闭合 -> " + expr.strip()[:40])
        if re.search(r"[\u4e00-\u9fff]", expr) and expr.count("'") == 0 and expr.count('"') == 0:
            # 表达式里直书中文且没有任何引号/比较符 → 疑似把 {{词}} 字面量写进了模板
            errors.append(rel + ": 第" + str(i) + "个表达式疑似字面量词直书 -> " + expr.strip()[:40])

    # ---- 标签流：配对 ----
    events = []
    for m in re.finditer(r"<(/?)([A-Za-z][\w-]*)([^>]*?)(/?)>", src, flags=re.S):
        line = src.count("\n", 0, m.start()) + 1
        closing, tag, attrs, selfclose = m.group(1), m.group(2), m.group(3) or "", m.group(4)
        if tag.lower() in FORBIDDEN :
            errors.append(rel + ": " + str(line) + " 行用了 HTML 专属标签 <" + tag + ">（WXML 不认）")
        if closing :
            events.append((line, "close", tag, attrs))
        elif selfclose or tag.lower() in SELF_CLOSED :
            events.append((line, "self", tag, attrs))
        else :
            events.append((line, "open", tag, attrs))

    stack = []
    prev_att = None
    for line, kind, tag, attrs in events:
        has_elif = "wx:elif" in attrs
        has_else = "wx:else" in attrs
        if has_elif and prev_att is None:
            errors.append(rel + ": " + str(line) + " 行 wx:elif 缺前置兄弟节点")
        if has_else and prev_att is None:
            errors.append(rel + ": " + str(line) + " 行 wx:else 缺前置兄弟节点")
        if kind == "open":
            stack.append((tag, line))
        elif kind == "close":
            if not stack:
                errors.append(rel + ": " + str(line) + " 行 </" + tag + "> 多余（栈空）")
                continue
            otag, oline = stack.pop()
            if otag != tag:
                errors.append(rel + ": " + str(line) + " 行 </" + tag + "> 与 " + str(oline) + " 行 <" + otag + "> 交叉")
        prev_att = attrs

    if stack:
        for tag, line in stack:
            errors.append(rel + ": <" + tag + ">（第 " + str(line) + " 行）未闭合")

    summary.append("  " + rel + "  表达式 " + str(n_open) + " 处")

report = "WXML 检查：\n" + "\n".join(summary)
if errors:
    report += "\n\n发现 " + str(len(errors)) + " 处问题：\n" + "\n".join("  x " + e for e in errors) + "\n"
    out = Path(__file__).with_name("report.txt")
    out.write_text(report, encoding="utf-8")
    print("FAIL " + str(len(errors)) + " -> see test/report.txt")
    sys.exit(1)
report += "\nOK 全部 .wxml 标签配对 / 表达式 / 条件链 通过\n"
(Path(__file__).with_name("report.txt")).write_text(report, encoding="utf-8")
print("OK all wxml")
