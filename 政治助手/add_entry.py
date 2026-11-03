# -*- coding: utf-8 -*-
"""命令行添加词条（给 AI 转录内容入库用，也可手动用）
用法:
  python add_entry.py --subject 毛中特 --chapter 六个必须坚持 --source 网课第3讲 --hot --file t.txt
  python add_entry.py --subject 时政 --text-file t.txt          # 不带 --hot
  python add_entry.py --stdin < t.txt
正文里 {{词}} = 普通挖空, {{!词}} = 高频红色挖空
"""
import argparse
import json
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'data.json'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--subject', required=True)
    ap.add_argument('--chapter', default='')
    ap.add_argument('--source', default='')
    ap.add_argument('--hot', action='store_true')
    ap.add_argument('--file')
    ap.add_argument('--stdin', action='store_true')
    args = ap.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding='utf-8').strip()
    elif args.stdin and not sys.stdin.isatty():
        text = sys.stdin.buffer.read().decode('utf-8', errors='replace').strip()
    else:
        sys.exit('需要 --file 或 --stdin 提供正文')
    if not text:
        sys.exit('正文为空')

    data = json.loads(DATA.read_text(encoding='utf-8'))
    entry = {
        'id': 'c' + datetime.now().strftime('%y%m%d%H%M%S') + uuid.uuid4().hex[:4],
        'created': datetime.now().strftime('%Y-%m-%dT%H:%M'),
        'subject': args.subject,
        'chapter': args.chapter,
        'source': args.source,
        'hot': args.hot,
        'text': text.replace('\r\n', '\n'),
        'review': {'stage': 0, 'due': date.today().isoformat()},
    }
    data['entries'].insert(0, entry)
    tmp = DATA.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(DATA)
    print('OK %s marks=%d total=%d' % (entry['id'], text.count('{{'),
                                       len(data['entries'])))


if __name__ == '__main__':
    main()
