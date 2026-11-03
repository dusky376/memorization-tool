# -*- coding: utf-8 -*-
"""政治助手 - 局域网 Web 服务
电脑运行本文件；手机同 WiFi 打开 http://<电脑IP>:8686
"""
import hashlib
import difflib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
DATA_FILE = ROOT / 'data' / 'data.json'
BACKUP_DIR = ROOT / 'backups'
INBOX = ROOT / 'inbox'
SHOTS = ROOT / 'screenshots'
ARCHIVE = SHOTS / 'inbox_done'
LOG_DIR = ROOT / 'logs'
DRAFT_FILE = ROOT / 'data' / 'drafts.json'
PROCESSED_FILE = ROOT / 'data' / 'processed.json'  # {md5: draftId} 已处理指纹
SCAN_INTERVAL = 5
IMG_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
DOC_EXTS = ('.pdf', '.docx', '.txt', '.md')   # .doc 老格式不支持，请先另存为 .docx
TMP_DIR = ROOT / 'data' / 'tmp'               # 文档解析/翻页临时文件
PORT = 8686

app = Flask(__name__, static_folder=str(STATIC), static_url_path='/static')
app.json.ensure_ascii = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0   # 静态文件禁用浏览器缓存：改 CSS/JS 立即生效（手机 PWA 另有 ?v= 双保险）

# ---------------------------------------------------------------- 数据读写
_data_lock = threading.Lock()

def _new_id():
    return 'e' + datetime.now().strftime('%y%m%d%H%M%S') + uuid.uuid4().hex[:4]

def load_data():
    if not DATA_FILE.exists():
        return {'version': 1, 'entries': []}
    return json.loads(DATA_FILE.read_text(encoding='utf-8'))

def save_data(data):
    DATA_FILE.parent.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)
    tmp = DATA_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    # 每日一份冷备份（覆盖前先备）
    today = date.today().strftime('%y%m%d')
    bak = BACKUP_DIR / ('data-%s.json' % today)
    if DATA_FILE.exists() and not bak.exists():
        bak.write_bytes(DATA_FILE.read_bytes())
        baks = sorted(BACKUP_DIR.glob('data-*.json'))
        for old in baks[:-30]:
            old.unlink(missing_ok=True)
    os.replace(tmp, DATA_FILE)

def plain_text(text):
    return re.sub(r'\{\{(!?)([^{}]*)\}\}', r'\2', text)

# ---------------------------------------------------------------- OCR
_ocr = None
_ocr_lock = threading.Lock()

def get_rapid():
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        return _ocr

def rapid_ocr_rows(img_path):
    """RapidOCR 检出行（带检测框）。同一视觉行的碎片先按中线聚类、从左到右拼接成完整行
    （旧版按 y/28 粗桶切行会导致同行碎片跨桶、行序错乱），再按阅读顺序输出。
    供红标分析和拼文共用——红标检测拿到的是整行连续框，切段词更连贯。"""
    eng = get_rapid()
    result, _ = eng(str(img_path))
    if not result:
        return []
    items = []
    for r in result:
        text = (r[1] or '').strip()
        if not text:
            continue
        try:
            b = [[float(p[0]), float(p[1])] for p in r[0]]
        except Exception:
            b = []
        if b:
            items.append({'box': b, 'text': text})
    if not items:
        return []

    def yc(it):     # 竖直中线
        return sum(p[1] for p in it['box']) / len(it['box'])
    def x0(it):
        return min(p[0] for p in it['box'])
    def hgt(it):
        ys = [p[1] for p in it['box']]
        return max(max(ys) - min(ys), 1.0)

    items.sort(key=lambda it: (yc(it), x0(it)))
    groups = []   # 每组 = 同一视觉行的碎片
    for it in items:
        if groups:
            g = groups[-1]
            ref_yc = sum(yc(x) for x in g) / len(g)
            ref_h = max(hgt(x) for x in g)
            if abs(yc(it) - ref_yc) <= 0.6 * max(hgt(it), ref_h):
                g.append(it)
                continue
        groups.append([it])

    rows = []
    for g in groups:
        g.sort(key=x0)
        text = ''
        for i, it in enumerate(g):
            if i and re.search(r'[A-Za-z0-9]$', text) and re.match(r'^[A-Za-z0-9]', it['text']):
                text += ' '
            text += it['text']
        if len(g) == 1:
            rows.append({'box': g[0]['box'], 'text': text})
        else:       # 并集外接框（红标切段用）
            xs = [p[0] for it in g for p in it['box']]
            ys = [p[1] for it in g for p in it['box']]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            rows.append({'box': [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], 'text': text})
    return rows

def rapid_ocr(img_path):
    return '\n'.join(r['text'] for r in rapid_ocr_rows(img_path) if r['text'])

def win_ocr(img_path):
    ps = ROOT / 'ocr_windows.ps1'
    r = subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
         '-File', str(ps), '-Image', str(img_path)],
        capture_output=True, timeout=120)
    return r.stdout.decode('utf-8', errors='replace').replace('\r', '')

def do_ocr(img_path, mode='auto'):
    if mode == 'win':
        return win_ocr(img_path), 'win'
    try:
        return rapid_ocr(img_path), 'rapid'
    except Exception:
        return win_ocr(img_path), 'win'

# ---------------- 截图红标 → 自动挖空（用户画的红就是重点，机器直接读） ----------------
RED_CELL_RATIO = 0.10   # 单字格里红色像素占比阈值（红字/红底/红下划线都算）
RED_SEG_AVG = 0.12      # 红段平均占比
RED_MAX = 40            # 每张图最多提取红段数

def _red_cells(img, box, n_chars):
    """检测框按切竖条逐字采样红色占比。
    红下划线常沉在 OCR 检测框外（检测框紧贴字形），下缘要多探一段；
    三个采样带各自算占比取最大值：正文红字 / 字底红 / 框外下划线，互不稀释。"""
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    h = int(max(y1 - y0, 1))          # box 坐标是浮点，必须先取整，range() 只吃整数
    pad_t = max(2, int(h * 0.08))
    pad_b = max(6, int(h * 0.35))     # 只探 0.35 倍行高，防止吃到下一行
    crop = img.crop((int(x0), int(y0 - pad_t), int(x1), int(y1 + pad_b))).convert('RGB')
    w, ch = crop.size
    if n_chars <= 0 or w <= 0 or ch <= 0:
        return []
    px = crop.load()
    sw = w / n_chars
    bands = [(pad_t + int(h * 0.18), pad_t + int(h * 0.70)),   # 正文带：红字/红底
             (pad_t + int(h * 0.62), pad_t + h),               # 基线带：字底红/贴字下划线
             (pad_t + h, min(ch, pad_t + h + pad_b))]          # 框外带：沉底红下划线
    cells = []
    for i in range(n_chars):
        cx0 = min(w - 1, max(0, int(i * sw)))
        cx1 = min(w, max(cx0 + 1, int((i + 1) * sw)))
        ratios = []
        for (by0, by1) in bands:
            red = tot = 0
            for xx in range(cx0, cx1, 2):
                for yy in range(by0, min(by1, ch), 2):
                    r, g, b = px[xx, yy]
                    tot += 1
                    if r >= 110 and r > g + 40 and r > b + 40:
                        red += 1
            if tot:
                ratios.append(red / tot)
        cells.append(max(ratios) if ratios else 0.0)
    return cells

_PUNCT_BRIDGING = '、，。：；！？·,….:;!?)）('   # 红段中间只夹这些标点时不许断开

def _red_rows(img_path, rows):
    """返回每行被用户标红的文字段"""
    from PIL import Image as PILImage
    if not rows:
        return []
    try:
        img = PILImage.open(img_path)
        img.load()
    except Exception:
        return []
    out = []
    for row in rows:
        t = row.get('text') or ''
        box = row.get('box')
        if len(t) < 2 or not box or len(box) < 4:
            continue
        try:
            cells = _red_cells(img, box, len(t))
        except Exception as e:
            LOG_DIR.mkdir(exist_ok=True)
            (LOG_DIR / 'error.log').open('a', encoding='utf-8').write(
                '[red-rows] %s %s %s\n' % (t[:20], e, time.strftime('%F %T')))
            continue
        i = 0
        while i < len(cells):
            if cells[i] >= RED_CELL_RATIO:
                j = i
                WEAK = RED_CELL_RATIO * 0.55   # 红字笔画更宽/更窄时会渗进邻字，别把邻字抖出去

                def is_word(ch):
                    return bool(re.match(r'[\u4e00-\u9fa5A-Za-z0-9]', ch))
                while i - 1 >= 0 and WEAK <= cells[i - 1] < RED_CELL_RATIO and is_word(t[i - 1]):
                    i -= 1   # 向左吃掉弱红邻字
                while j + 1 < len(cells):
                    if cells[j + 1] >= RED_CELL_RATIO:
                        j += 1
                    elif (WEAK <= cells[j + 1] < RED_CELL_RATIO and is_word(t[j + 1])
                          and (j + 2 >= len(cells) or cells[j + 2] >= RED_CELL_RATIO)):
                        j += 1    # 向右吃掉弱红邻字（渗色/切片漂移的边字）
                    elif (t[j + 1] in _PUNCT_BRIDGING and j + 2 < len(cells)
                          and cells[j + 2] >= RED_CELL_RATIO):
                        j += 2    # 吃过单个标点，别把「文化强国、体育强国」切断
                    else:
                        break
                seg = (t[i:j + 1] or '').strip()
                seg = seg.strip('.,。，、：:;；!！?？）)（(][【】“”\'\"…— ')   # 掐头去尾的杂符号
                avg = sum(cells[i:j + 1]) / max(j - i + 1, 1)
                if len(seg) >= 2 and avg >= RED_SEG_AVG and len(re.findall(r'[\u4e00-\u9fa5A-Za-z0-9]', seg)) >= 2:
                    out.append(seg)
                i = j + 1
            else:
                i += 1
    return out[:RED_MAX]

def _wrap_words(text, words, mark='{{!'):
    """把词包进挖空标记；跳过已包区域，永不嵌套"""
    def masked(t):
        mask = bytearray(len(t))
        depth = 0
        i = 0
        while i < len(t):
            if t.startswith('{{', i):
                depth += 1
                mask[i] = mask[i + 1] = 1
                i += 2
                continue
            if t.startswith('}}', i):
                depth = max(depth - 1, 0)
                mask[i] = mask[i + 1] = 1
                i += 2
                continue
            if depth:
                mask[i] = 1
            i += 1
        return mask
    for w in sorted({(w or '').strip() for w in words if w and len(w.strip()) >= 2},
                    key=len, reverse=True):
        for _ in range(8):   # 同一个词最多包 8 处
            mask = masked(text)
            start, i = -1, text.find(w)
            while i >= 0:
                if not any(mask[i:i + len(w)]):
                    start = i
                    break
                i = text.find(w, i + 1)
            if start < 0:
                break
            text = text[:start] + mark + w + '}}' + text[start + len(w):]
    return text

def count_marks(text):
    return len(re.findall(r'\{\{!?[^{}]*\}\}', text or ''))

def analyze_image(img_path, mode='auto'):
    """OCR + 读截图红标 → 已自动挖空的文本"""
    if mode == 'win':
        return win_ocr(img_path).strip(), [], 'win'
    rows = []
    try:
        rows = rapid_ocr_rows(img_path)
    except Exception as e:
        LOG_DIR.mkdir(exist_ok=True)
        (LOG_DIR / 'error.log').open('a', encoding='utf-8').write(
            '[rapid] %s %s %s\n' % (Path(img_path).name, e, time.strftime('%F %T')))
    text = '\n'.join(r['text'] for r in rows if r.get('text'))
    if not text.strip():
        try:
            return win_ocr(img_path).strip(), [], 'win'
        except Exception:
            return '', [], 'win'
    reds = _red_rows(img_path, rows)
    marked = _wrap_words(text, list(reds) + _quote_candidates(text))
    return marked, reds, 'rapid'

def save_image(fileobj, filename):
    SHOTS.mkdir(exist_ok=True)
    ext = Path(filename).suffix.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'):
        ext = '.png'
    name = time.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:6] + ext
    path = SHOTS / name
    fileobj.save(path)
    return path

# ---------------------------------------------------------------- 收件夹自动归档
_draft_lock = threading.Lock()

HOT_WORDS = [
    '最本质的特征', '本质特征', '根本立场', '总任务', '总体布局', '战略布局',
    '四个全面', '五位一体', '两个确立', '两个维护', '四个意识', '四个自信',
    '自我革命', '社会革命', '全面从严治党', '全过程人民民主', '共同富裕',
    '现代化强国', '中国梦', '人民至上', '自信自立', '守正创新', '问题导向',
    '系统观念', '胸怀天下', '世界观', '方法论', '立场观点方法', '群众史观',
    '实事求是', '一切从实际出发', '机遇和挑战', '最大公约数', '初心使命',
    '基本方略', '最大优势', '生命线', '基本经济制度', '决定性作用',
    '意识能动性', '主观能动性', '对立统一', '质量互变', '否定之否定',
    '矛盾', '普遍联系', '发展', '质变', '量变', '本质', '根本', '关键',
    '首要', '核心', '灵魂', '精髓', '实质', '主线', '基础', '前提',
    '保证', '保障', '基石', '动力', '源泉', '出发', '落脚',
]
SUBJECT_HINTS = {
    '毛中特': ['习近平', '新时代', '中特', '社会主义', '党 ', '党的', '毛泽东', '思想',
             '十四个', '四个', '五位', '中国梦', '一国两制', '共同体', '政治建设',
             '文化建设', '社会建设', '生态文明', '强国', '复兴', '现代化'],
    '马原': ['唯物', '唯心', '辩证', '矛盾', '认识', '实践', '真理', '剩余价值', '商品',
            '资本', '货币', '异化', '意识', '物质', '联系', '发展观', '规律', '感性',
            '理性', '价值', '规律性'],
    '史纲': ['鸦片战争', '辛亥革命', '五四', '抗日', '解放战争', '建国', '王朝', '太平天国',
            '洋务', '维新', '新文化', '长征', '会议', '年爆', '条约', '割让', '光绪',
            '宣统', '民国', '军阀'],
    '思修': ['人生观', '价值观', '道德', '法律', '法治', '理想信念', '爱国主义',
            '人生价值', '婚姻', '家庭', '职业', '人身权', '公民'],
    '时政': ['二十大', '中全会', '政府工作报告', '时政', '会议精神', '公报', '座谈会',
            '考察', '谈话', '重要讲话'],
    '常识': ['公文', '管理学', '科技', '地理', '文学', '天文', '物理常识'],
}

def _quote_candidates(text):
    out = set()
    for m in re.finditer(r'[“"\u3010【]([\u4e00-\u9fa5A-Za-z0-9、，,]{2,14})[”"\u3011】]', text):
        out.add(m.group(1))
    for w in HOT_WORDS:
        if w in text:
            out.add(w)
    return sorted(out, key=len, reverse=True)

def guess_subject(text):
    best, score = '毛中特', 0
    for subj, kws in SUBJECT_HINTS.items():
        n = sum(1 for k in kws if k in text)
        if n > score:
            best, score = subj, n
    return best

def guess_chapter(text):
    first = next((l.strip() for l in text.split('\n') if l.strip()), '')
    first = re.sub(r'^[一二三四五六七八九十\d\s]*[、.．)）]?\s*', '', first)
    if 0 < len(first) <= 16 and '。' not in first and '：' not in first:
        return first
    return ''

# ---------------------------------------------------------------- 重复检测
IGNORED_FILE = ROOT / 'data' / 'ignored.json'   # 已忽略的重复记录（给用户看）

def _load_ignored():
    if not IGNORED_FILE.exists():
        return []
    return json.loads(IGNORED_FILE.read_text(encoding='utf-8'))

def _save_ignored(v):
    IGNORED_FILE.parent.mkdir(exist_ok=True)
    tmp = IGNORED_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, IGNORED_FILE)

def norm_text(t):
    return re.sub(r'[\s，。：；、·,.:;()（）"“”\'\'\'【】{}！!？?《》\-—\n\r]', '', t or '')

def find_dup(text, entries, drafts, skip_id=None):
    """与已有词条/草稿对比：内容高度相同即视为重复。
    返回 (重复对象, 'entry'|'draft')；不重复返回 None。
    规则（归一化后）：互相包含≥80% 或 相似度≥0.92"""
    n = norm_text(text)
    if len(n) < 8:
        return None
    for kind, pool in (('entry', entries), ('draft', drafts)):
        for x in pool:
            if x.get('id') == skip_id:
                continue
            m = norm_text(x.get('text', ''))
            if not m:
                continue
            small, big = (n, m) if len(n) <= len(m) else (m, n)
            if len(small) * 100 // max(len(big), 1) >= 80 and (small in big):
                return x, kind
            if difflib.SequenceMatcher(None, n[:400], m[:400]).ratio() >= 0.92:
                return x, kind
    return None

def extract_doc_text(p):
    """文档提字：PDF/Word/文本。PDF 有文字层直接抽，空白/扫描页渲染成图走 OCR 兜底"""
    ext = p.suffix.lower()
    if ext in ('.txt', '.md'):
        raw = p.read_bytes()
        for enc in ('utf-8', 'gb18030'):
            try:
                return raw.decode(enc), 'txt'
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', 'ignore'), 'txt'
    if ext == '.docx':
        import docx  # python-docx
        d = docx.Document(str(p))
        parts = [par.text for par in d.paragraphs if par.text.strip()]
        for tb in d.tables:
            for row in tb.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(' ｜ '.join(cells))
        return '\n'.join(parts), 'docx'
    if ext == '.pdf':
        import pypdf
        r = pypdf.PdfReader(str(p))
        pages = []
        for pg in r.pages:
            try:
                pages.append(pg.extract_text() or '')
            except Exception:
                pages.append('')
        out, modes = [], set()
        ocr_pdf = None
        n_pages = len(pages)
        for i, t in enumerate(pages):
            if len(re.sub(r'\s', '', t)) >= 4:      # 该页有文字层
                out.append(t)
                modes.add('pdf-text')
            elif i < 40:                             # 空白/扫描页 → 渲染成图走 OCR（最多40页防卡死）
                try:
                    if ocr_pdf is None:
                        import pypdfium2 as pdfium
                        ocr_pdf = pdfium.PdfDocument(str(p))
                    img = ocr_pdf[i].render(scale=2.2).to_pil().convert('RGB')
                    TMP_DIR.mkdir(parents=True, exist_ok=True)
                    tmp = TMP_DIR / ('pg%03d.png' % i)
                    img.save(tmp)
                    try:
                        o, _m = do_ocr(tmp)
                    finally:
                        try:
                            tmp.unlink()
                        except OSError:
                            pass
                    out.append(o)
                    modes.add('pdf-ocr')
                except Exception as e:
                    LOG_DIR.mkdir(exist_ok=True)
                    (LOG_DIR / 'error.log').open('a', encoding='utf-8').write(
                        '[pdfpage] %s p%d %s %s\n' % (p.name, i + 1, e, time.strftime('%F %T')))
            else:
                out.append('（第%d页未提取：页数过多，请拆分后重试）' % (i + 1))
        text = '\n'.join(x.strip() for x in out if x.strip())
        return text[:20000], (''.join(sorted(modes)) if modes else 'pdf')
    raise ValueError('暂不支持该文档格式（支持 pdf/docx/txt/md）')

def _load_drafts():
    if not DRAFT_FILE.exists():
        return []
    return json.loads(DRAFT_FILE.read_text(encoding='utf-8'))

def _save_drafts(items):
    DRAFT_FILE.parent.mkdir(exist_ok=True)
    tmp = DRAFT_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, DRAFT_FILE)

def _load_processed():
    if not PROCESSED_FILE.exists():
        return {}
    return json.loads(PROCESSED_FILE.read_text(encoding='utf-8'))

def _save_processed(d):
    PROCESSED_FILE.parent.mkdir(exist_ok=True)
    tmp = PROCESSED_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, PROCESSED_FILE)

_inbox_lock = threading.Lock()   # 手动扫描与后台扫描互斥
_ignored_lock = threading.Lock() # 忽略记录读写锁

def process_inbox():
    """扫描 inbox：提字（截图OCR / 文档解析）→ 查重 → 生成草稿。
    铁律：原文件永不移动/删除；同一文件(md5)只处理一次；并发触发只跑一次"""
    INBOX.mkdir(exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    made = 0
    with _inbox_lock:
        files = [p for p in sorted(INBOX.iterdir())
                 if p.suffix.lower() in IMG_EXTS + DOC_EXTS and p.is_file()]
        if not files:
            return 0
        processed = _load_processed()
        for p in files:
            try:
                h = hashlib.md5(p.read_bytes()).hexdigest()
            except OSError:
                continue  # 被占用/正在写入，下轮再试
            if h in processed:
                continue
            is_img = p.suffix.lower() in IMG_EXTS
            # ---- 第一步：提字（截图读红标自动挖空；文档解析+热词自动挖空）----
            text, used, auton, words = '', '', 0, []
            try:
                if is_img:
                    text, reds, used = analyze_image(p)
                    plain = plain_text(text)
                    words = sorted(set(list(reds) + _quote_candidates(plain)), key=len, reverse=True)
                else:
                    text, used = extract_doc_text(p)
                    words = sorted(set(_quote_candidates(text)), key=len, reverse=True)
                    text = _wrap_words(text, words)
                auton = count_marks(text)
            except Exception as e:
                LOG_DIR.mkdir(exist_ok=True)
                (LOG_DIR / 'error.log').open('a', encoding='utf-8').write(
                    '[scan] %s %s %s\n' % (p.name, e, time.strftime('%F %T')))
            text = (text or '').strip()
            ok = bool(text)
            used = used or ('rapid' if is_img else 'doc')
            # ---- 第二步：查重闸门（与已有词条/草稿对比，重复不建草稿，只留忽略记录）----
            if ok:
                dup = find_dup(text, load_data().get('entries', []), _load_drafts())
                if dup:
                    dx, kind = dup
                    where = ('待确认草稿' if kind == 'draft'
                             else (dx.get('chapter') or dx.get('subject') or '已有词条'))
                    processed[h] = 'ig-' + h[:12]
                    _save_processed(processed)
                    with _ignored_lock:
                        ig = [x for x in _load_ignored() if x.get('hash') != h]
                        ig.append({
                            'id': 'ig' + uuid.uuid4().hex[:6],
                            'hash': h,
                            'time': datetime.now().strftime('%m-%d %H:%M'),
                            'src': p.name,
                            'text': text[:3000],
                            'reason': '与「%s」内容重复' % where,
                        })
                        _save_ignored(ig[-200:])
                    continue
            # ---- 第三步：归档副本（供预览），原文件保留在 inbox ----
            dest = ARCHIVE / p.name
            stem, ext = p.stem, p.suffix
            i = 0
            while dest.exists():
                i += 1
                dest = ARCHIVE / (stem + '_' + str(i) + ext)
            try:
                shutil.copy2(p, dest)
            except OSError as e:
                LOG_DIR.mkdir(exist_ok=True)
                (LOG_DIR / 'error.log').open('a', encoding='utf-8').write(
                    '[scan-copy] %s %s %s\n' % (p.name, e, time.strftime('%F %T')))
                continue
            tip = ('这张图没识别出文字（可能太花/不清晰），可点“重试”' if is_img
                   else '这份文档没提取出文字，可点“重试”')
            drafted = {
                'id': 'd' + time.strftime('%y%m%d%H%M%S') + uuid.uuid4().hex[:3],
                'created': datetime.now().strftime('%m-%d %H:%M'),
                'ts': int(p.stat().st_mtime),   # 文件真实时间（拍图/保存顺序）
                'img': 'inbox_done/' + dest.name,
                'doc': not is_img,
                'src': p.name,
                'mode': used,
                'text': text,
                'subject': guess_subject(text) if ok else '未分类',
                'chapter': guess_chapter(text),
                'source': ('文档' if not is_img else '截图') + time.strftime('%m-%d'),
                'candidates': words if ok else [],
                'auton': auton if ok else 0,
                'err': '' if ok else tip,
            }
            with _draft_lock:
                drafts = _load_drafts()
                _save_drafts(drafts + [drafted])   # 追加到尾部：保持丢文件时间顺序（视频顺序）
            processed[h] = drafted['id']
            _save_processed(processed)
            made += 1
    return made

def scan_loop():
    while True:
        time.sleep(SCAN_INTERVAL)
        try:
            process_inbox()
        except Exception as e:
            LOG_DIR.mkdir(exist_ok=True)
            (LOG_DIR / 'error.log').open('a', encoding='utf-8').write(
                '[scanloop] %s %s\n' % (e, time.strftime('%F %T')))

# ---------------------------------------------------------------- 间隔复习
STAGES = [1, 2, 4, 7, 15, 30, 45]  # 记住 N 次后间隔天数

def bump_review(entry, ok):
    rev = entry.setdefault('review', {'stage': 0, 'due': date.today().isoformat()})
    if ok:
        stage = min(int(rev.get('stage', 0)) + 1, len(STAGES) - 1)
        rev['stage'] = stage
        rev['due'] = (date.today() + timedelta(days=STAGES[stage])).isoformat()
        rev.setdefault('ok', 0)
        rev['ok'] += 1
    else:
        rev['stage'] = 0
        rev['due'] = (date.today() + timedelta(days=1)).isoformat()
        rev.setdefault('ng', 0)
        rev['ng'] += 1
    rev['last'] = date.today().isoformat()

# ---------------------------------------------------------------- 页面
@app.route('/favicon.ico')
def favicon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           '<rect width="24" height="24" rx="6" fill="#c62828"/>'
           '<path d="M6.5 5h7a4 4 0 0 1 4 4v10h-7a4 4 0 0 1-4-4V5z" fill="#fff" opacity=".9"/>'
           '</svg>')
    return send_file(io.BytesIO(svg.encode()), mimetype='image/svg+xml')

@app.route('/help')
def page_help():
    return send_file(STATIC / 'help.html')

@app.route('/')
def page_recite():
    return send_file(STATIC / 'recite.html')

@app.route('/add')
def page_add():
    return send_file(STATIC / 'add.html')

@app.route('/manage')
def page_manage():
    return send_file(STATIC / 'manage.html')

@app.route('/arrange')
def page_arrange():
    return send_file(STATIC / 'arrange.html')

@app.route('/shots/<path:rel>')
def shot_file(rel):
    return send_from_directory(str(SHOTS), rel)

# ---------------------------------------------------------------- API
@app.route('/api/status')
def api_status():
    data = load_data()
    ip = lan_ip()
    return jsonify({'ok': True, 'url': 'http://%s:%d' % (ip, PORT), 'port': PORT,
                    'total': len(data['entries'])})

@app.route('/api/ocr', methods=['POST'])
def api_ocr():
    f = request.files.get('image') or request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'error': 'no file'}), 400
    path = save_image(f, f.filename or 'paste.png')
    mode = request.form.get('mode', 'auto')
    text, reds, used = analyze_image(path, mode)
    lines = text.split('\n')
    return jsonify({'ok': True, 'file': path.name, 'text': text, 'mode': used,
                    'reds': reds, 'auton': count_marks(text),
                    'first_line': lines[0] if lines else ''})

@app.route('/api/doc_ocr', methods=['POST'])
def api_doc_ocr():
    """录入页直接上传文档（PDF/Word/txt）提取文字"""
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'error': 'no file'}), 400
    name = f.filename or 'doc.pdf'
    ext = Path(name).suffix.lower()
    if ext not in DOC_EXTS:
        return jsonify({'ok': False, 'error': '暂只支持 ' + '/'.join(DOC_EXTS) + '；.doc 老格式请先另存为 .docx'}), 400
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / (uuid.uuid4().hex[:8] + ext)
    f.save(path)
    try:
        text, used = extract_doc_text(path)
    except Exception as e:
        return jsonify({'ok': False, 'error': '提取失败：%s' % e}), 500
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    return jsonify({'ok': True, 'text': text, 'mode': used})

@app.route('/api/inbox_scan', methods=['POST'])
def api_inbox_scan():
    n = process_inbox()
    return jsonify({'ok': True, 'created': n})

@app.route('/api/inbox_rescan', methods=['POST'])
def api_inbox_rescan():
    """全量重扫：释放全部文件指纹，inbox 现存文件重新走一遍“提字+查重”。
    已入库的内容会被查重拦下进忽略面板，不会重复入库"""
    with _inbox_lock:
        _save_processed({})
    n = process_inbox()
    return jsonify({'ok': True, 'created': n})

@app.route('/api/drafts')
def api_drafts():
    return jsonify({'ok': True, 'drafts': _load_drafts()})

@app.route('/api/draft_confirm', methods=['POST'])
def api_draft_confirm():
    body = request.get_json(force=True)
    text = (body.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'error': '内容为空'}), 400
    with _data_lock, _draft_lock:
        data = load_data()
        drafts = _load_drafts()
        d = next((x for x in drafts if x['id'] == body.get('id')), None)
        # ---- 查重闸门：与现有词条/其它草稿对比（可与 body.force 强制入库） ----
        if not body.get('force'):
            dup = find_dup(text, data['entries'], [x for x in drafts if x is not d])
            if dup:
                dx, kind = dup
                where = ('待确认草稿' if kind == 'draft'
                         else (dx.get('chapter') or dx.get('subject') or '已有词条'))
                if d:
                    d['dup'] = '与「%s」内容重复' % where
                    _save_drafts(drafts)
                return jsonify({'ok': False, 'dup': True,
                                'error': '与「%s」内容重复，未入库' % where}), 200
        created = datetime.now().strftime('%Y-%m-%dT%H:%M')
        if d and d.get('ts'):
            created = datetime.fromtimestamp(d['ts']).strftime('%Y-%m-%dT%H:%M')  # 以截图时间为准
        entry = {
            'id': _new_id(),
            'created': created,
            'subject': body.get('subject') or '未分类',
            'chapter': body.get('chapter', ''),
            'source': body.get('source', ''),
            'hot': bool(body.get('hot')),
            'text': text.replace('\r\n', '\n').replace('\r', '\n'),
            'review': {'stage': 0, 'due': date.today().isoformat()},
        }
        data['entries'].insert(0, entry)
        save_data(data)
        drafts = [d for d in _load_drafts() if d['id'] != body.get('id')]
        _save_drafts(drafts)
    return jsonify({'ok': True, 'id': entry['id']})

@app.route('/api/draft_delete', methods=['POST'])
def api_draft_delete():
    did = (request.get_json(force=True) or {}).get('id')
    with _draft_lock, _ignored_lock:
        drafts = _load_drafts()
        d = next((x for x in drafts if x['id'] == did), None)
        _save_drafts([x for x in drafts if x['id'] != did])
        if d:
            # 丢弃也要有说法：忽略面板留痕（可「转为草稿」找回），文件指纹继续挡住同文件复活
            processed = _load_processed()
            h = next((k for k, v in processed.items() if v == did), '')
            ig = _load_ignored()
            ig.append({
                'id': 'ig' + uuid.uuid4().hex[:6],
                'hash': h,
                'time': datetime.now().strftime('%m-%d %H:%M'),
                'src': d.get('src') or (d.get('img') or '').rsplit('/', 1)[-1] or '（无原图）',
                'text': (d.get('text') or '')[:3000],
                'reason': '手动丢弃（同文件已挡住不复活；可「转为草稿」找回）',
            })
            _save_ignored(ig[-200:])
            img = d.get('img')
            if img:
                try:
                    (SHOTS / img).unlink()
                except OSError:
                    pass
    return jsonify({'ok': True})

@app.route('/api/draft_retry', methods=['POST'])
def api_draft_retry():
    did = (request.get_json(force=True) or {}).get('id')
    with _draft_lock:
        drafts = _load_drafts()
        d = next((x for x in drafts if x['id'] == did), None)
        if not d:
            return jsonify({'ok': False, 'error': '草稿不存在'}), 404
        p = INBOX / d.get('src', '')
        if not p.is_file():
            return jsonify({'ok': False, 'error': '原图已不在 inbox，请重新丢入后再试'}), 400
        try:
            if p.suffix.lower() in DOC_EXTS:
                text0, used = extract_doc_text(p)
                words = sorted(set(_quote_candidates(text0)), key=len, reverse=True)
                text = _wrap_words(text0, words)
            else:
                text, reds, used = analyze_image(p)
                words = sorted(set(list(reds) + _quote_candidates(plain_text(text))),
                               key=len, reverse=True)
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
        if not text.strip():
            return jsonify({'ok': False, 'error': '仍未识别出文字'}), 200
        d.update({'text': text.strip(), 'mode': used, 'err': '',
                  'subject': guess_subject(plain_text(text)), 'chapter': guess_chapter(text) or d.get('chapter', ''),
                  'source': d.get('source', ''), 'candidates': words, 'auton': count_marks(text)})
        _save_drafts(drafts)
    return jsonify({'ok': True})

@app.route('/api/draft_remark', methods=['POST'])
def api_draft_remark():
    """旧草稿补做：读归档截图里的红标+热词，自动挖空"""
    did = (request.get_json(force=True) or {}).get('id')
    with _draft_lock:
        drafts = _load_drafts()
        d = next((x for x in drafts if x['id'] == did), None)
        if not d:
            return jsonify({'ok': False, 'error': '草稿不存在'}), 404
        img = d.get('img') or ''
        if d.get('doc') or not img:
            return jsonify({'ok': False, 'error': '该草稿没有可用截图（文档用「补充自动挖空」）'}), 400
        p = SHOTS / img
        if not p.is_file():
            return jsonify({'ok': False, 'error': '归档截图不存在'}), 400
        try:
            text, reds, used = analyze_image(p)
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
        if not text.strip():
            return jsonify({'ok': False, 'error': '截图识别为空'}), 200
        words = sorted(set(list(reds) + _quote_candidates(plain_text(text))), key=len, reverse=True)
        d.update({'text': text, 'mode': used, 'err': '', 'auton': count_marks(text),
                  'subject': guess_subject(plain_text(text)),
                  'chapter': guess_chapter(text) or d.get('chapter', ''),
                  'candidates': words})
        _save_drafts(drafts)
    return jsonify({'ok': True})

@app.route('/api/drafts_dedupe', methods=['POST'])
def api_drafts_dedupe():
    """同内容草稿去重：保留最旧一张，删掉后来重复的"""
    with _draft_lock:
        drafts = _load_drafts()
        seen = set()
        kept, removed = [], 0
        for d in drafts:            # 列表最旧在前 → 先见先留（保住视频顺序里最早的）
            key = re.sub(r'\s+', '', d.get('text', ''))[:200]
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(d)
        _save_drafts(kept)
    return jsonify({'ok': True, 'removed': removed})

@app.route('/api/ignored')
def api_ignored():
    return jsonify({'ok': True, 'ignored': _load_ignored()})

@app.route('/api/ignored_clear', methods=['POST'])
def api_ignored_clear():
    with _ignored_lock:
        ig = _load_ignored()
        _save_ignored([])
        # 记录清空时，这些被忽略文件的指纹一并放开：
        # 以后再丢同名/同内容文件会重新走完整查重（而不是被指纹悄悄跳过没反应）
        processed = _load_processed()
        ig_hashes = {x.get('hash') for x in ig}
        for h in [k for k, v in processed.items() if v.startswith('ig-') or k in ig_hashes]:
            processed.pop(h, None)
        _save_processed(processed)
    return jsonify({'ok': True})

@app.route('/api/ignored_recover', methods=['POST'])
def api_ignored_recover():
    """误判恢复：把忽略记录转回草稿，人工核对处理"""
    rid = (request.get_json(force=True) or {}).get('id')
    with _ignored_lock, _draft_lock:
        ig = _load_ignored()
        rec = next((x for x in ig if x.get('id') == rid), None)
        if not rec:
            return jsonify({'ok': False, 'error': '记录不存在（可能已被清空）'}), 404
        text = rec.get('text') or ''
        src = rec.get('src', '')
        src_ext = ('.' + src.rsplit('.', 1)[-1].lower()) if '.' in src else ''
        drafted = {
            'id': 'd' + time.strftime('%y%m%d%H%M%S') + uuid.uuid4().hex[:3],
            'created': datetime.now().strftime('%m-%d %H:%M'),
            'ts': int(time.time()),
            'img': '',
            'doc': src_ext in DOC_EXTS,
            'src': src,
            'mode': 'recover',
            'text': text,
            'subject': guess_subject(text) or '未分类',
            'chapter': guess_chapter(text),
            'source': '忽略恢复',
            'candidates': _quote_candidates(text),
            'err': '',
        }
        drafts = _load_drafts()
        _save_drafts(drafts + [drafted])
        _save_ignored([x for x in ig if x.get('id') != rid])
        h = rec.get('hash')
        if h:
            processed = _load_processed()
            if processed.get(h, '').startswith('ig-'):
                processed[h] = drafted['id']   # 同一文件以后不再重复忽略，直接映射到这份草稿
                _save_processed(processed)
    return jsonify({'ok': True, 'draft': drafted['id']})

@app.route('/api/entries')
def api_entries():
    data = load_data()
    subject = request.args.get('subject', '')
    q = request.args.get('q', '').strip()
    rows = data['entries']
    if subject:
        rows = [e for e in rows if e.get('subject') == subject]
    if q:
        ql = q.lower()
        rows = [e for e in rows if ql in plain_text(e['text']).lower()
                or ql in e.get('chapter', '') or ql in e.get('source', '')]
    return jsonify({'ok': True, 'entries': rows})

@app.route('/api/entry_save', methods=['POST'])
def api_entry_save():
    body = request.get_json(force=True)
    text = (body.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'error': '内容不能为空'}), 400
    with _data_lock, _draft_lock:
        data = load_data()
        # ---- 查重闸门：与现有词条/草稿对比（编辑时排除自己；force 可跳过） ----
        if not body.get('force'):
            dup = find_dup(text, data['entries'], _load_drafts(), skip_id=body.get('id'))
            if dup:
                dx, kind = dup
                where = ('待确认草稿' if kind == 'draft'
                         else (dx.get('chapter') or dx.get('subject') or '已有词条'))
                return jsonify({'ok': False, 'dup': True,
                                'error': '与「%s」内容重复，未保存' % where}), 200
        entry = {
            'id': body.get('id') or _new_id(),
            'created': datetime.now().strftime('%Y-%m-%dT%H:%M'),
            'subject': body.get('subject', '未分类'),
            'chapter': body.get('chapter', ''),
            'source': body.get('source', ''),
            'hot': bool(body.get('hot')),
            'text': text.replace('\r\n', '\n').replace('\r', '\n'),
            'review': {'stage': 0, 'due': date.today().isoformat()},
        }
        if body.get('id'):
            old = next((e for e in data['entries'] if e['id'] == body['id']), None)
            if old:
                old.update({k: entry[k] for k in ('subject', 'chapter', 'source', 'text')})
                old['hot'] = bool(body.get('hot', old.get('hot', False)))   # 编辑时不传 hot 就保留原值
            else:
                return jsonify({'ok': False, 'error': '词条不存在'}), 404
        else:
            data['entries'].insert(0, entry)
        save_data(data)
    return jsonify({'ok': True, 'id': entry['id']})

@app.route('/api/entry_delete', methods=['POST'])
def api_entry_delete():
    eid = (request.get_json(force=True) or {}).get('id')
    with _data_lock:
        data = load_data()
        n = len(data['entries'])
        data['entries'] = [e for e in data['entries'] if e['id'] != eid]
        if len(data['entries']) == n:
            return jsonify({'ok': False, 'error': 'not found'}), 404
        save_data(data)
    return jsonify({'ok': True})

@app.route('/api/review', methods=['POST'])
def api_review():
    body = request.get_json(force=True)
    eid, ok = body.get('id'), bool(body.get('ok'))
    with _data_lock:
        data = load_data()
        entry = next((e for e in data['entries'] if e['id'] == eid), None)
        if not entry:
            return jsonify({'ok': False, 'error': 'not found'}), 404
        bump_review(entry, ok)
        save_data(data)
        return jsonify({'ok': True, 'review': entry['review']})

@app.route('/api/today')
def api_today():
    today = date.today().isoformat()
    data = load_data()
    subject = request.args.get('subject', '')
    rows = [e for e in data['entries'] if e.get('review', {}).get('due', today) <= today]
    if subject:
        rows = [e for e in rows if e.get('subject') == subject]
    rows = sorted(rows, key=lambda e: e['created'])   # 按录入时间（视频顺序）
    entries = data['entries']
    return jsonify({'ok': True, 'date': today, 'queue': rows,
                    'stats': {'total': len(entries),
                              'due': len(rows),
                              'hot': sum(1 for e in rows if e.get('hot'))}})

@app.route('/qr.svg')
def api_qr():
    import qrcode
    from qrcode.image.svg import SvgPathImage
    url = 'http://%s:%d' % (lan_ip(), PORT)
    img = qrcode.make(url, image_factory=SvgPathImage, border=2)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/svg+xml')

def lan_ip():
    s = socket.socket(type=socket.SOCK_DGRAM)
    try:
        s.connect(('223.5.5.5', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

# ---------------------------------------------------------------- 错误日志
@app.errorhandler(Exception)
def on_error(e):
    LOG_DIR.mkdir(exist_ok=True)
    import traceback
    (LOG_DIR / 'error.log').open('a', encoding='utf-8').write(
        '\n[%s] %s\n%s\n' % (datetime.now(), e, traceback.format_exc()))
    return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == '__main__':
    threading.Thread(target=scan_loop, daemon=True).start()
    print('政治助手已启动:')
    print('  本机:   http://127.0.0.1:%d' % PORT)
    print('  手机同WiFi: http://%s:%d  (可在网页右上角扫码)' % (lan_ip(), PORT))
    app.run(host='0.0.0.0', port=PORT, debug=False)
