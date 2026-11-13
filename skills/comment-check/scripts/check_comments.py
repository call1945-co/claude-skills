"""
주석 기계 검사 — 길이·여러 줄·기호 겹침·결정 이력·번역투를 찾는다.
'코드를 다시 설명하는 주석인가'는 사람(에이전트)이 판단한다.

사용:
  python check_comments.py <파일·폴더 ...>
  python check_comments.py --diff origin/develop   # 그 기준 이후 추가·수정된 줄의 주석만
  python check_comments.py --staged
옵션: --max-len 50  --max-lines 3  --strict(하나라도 있으면 종료 코드 1)

"""
import argparse
import os
import re
import subprocess
import sys
from collections import Counter

EXTS = {'.java', '.kt', '.kts', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.vue',
        '.scss', '.css', '.py', '.sql', '.xml', '.html', '.go'}
SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', 'target', '.gradle', '.idea', '.worktrees'}

HIST = [
    (re.compile(r'(?<![\w/])!\d+\b'), 'MR 번호'),
    (re.compile(r'\bMR\s*[!#]?\d+'), 'MR 번호'),
    (re.compile(r'\b20\d\d-\d\d-\d\d\b'), '날짜'),
    (re.compile(r'(PL|PM|대표|기획|현업|팀장)\s*(이|가|의|와)?\s*(결정|확정|지시|요청|합의)'), '누가 정했는지'),
]
TONE = [
    (re.compile(r'에\s*대(해서?|한)'), '~에 대해'),
    (re.compile(r'에\s*의(해서?|한)'), '~에 의해'),
    (re.compile(r'(을|를|기)\s*위(해서?|한)'), '~을 위해'),
    (re.compile(r'되어\s*([지-짛]|졌)|지게\s*된다'), '이중 피동'),
    (re.compile(r'에\s*있어서?'), '~에 있어'),
    (re.compile(r'(을|를)\s*가지고\s*있'), '~을 가지고 있다'),
    (re.compile(r'(와|과)\s*관련(하여|된|한)'), '~와 관련하여'),
    (re.compile(r'(제공|수행)(한다|합니다|하는)'), '제공/수행한다'),
]
DASH = re.compile(r'[—–]|\s-\s')
TAG = re.compile(r'^@(\w+)\s*(\{[^}]*\}\s*)?(\[?[\w.$]+\]?)?\s*-?\s*')
HEADER_TAG = re.compile(r'@(author|since|modified)\b')


def markers(ext):
    if ext == '.py':
        return ['#'], []
    if ext == '.sql':
        return ['--'], [('/*', '*/')]
    if ext in ('.xml', '.html'):
        return [], [('<!--', '-->')]
    if ext == '.vue':
        return ['//'], [('/*', '*/'), ('<!--', '-->')]
    return ['//'], [('/*', '*/')]


def extract(path):
    """주석 묶음 목록 [(시작 줄, [(줄번호, 글자)], 블록 여부)] — 이어진 한 줄 주석은 한 묶음."""
    ext = os.path.splitext(path)[1].lower()
    line_m, block_m = markers(ext)
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().split('\n')
    except OSError:
        return []
    units, cur_line_unit, in_block = [], None, None
    for no, raw in enumerate(lines, 1):
        if in_block:
            end, body = in_block
            idx = raw.find(end)
            text = raw if idx < 0 else raw[:idx]
            body.append((no, text))
            if idx >= 0:
                in_block = None
            continue
        found = scan(raw, line_m, block_m)
        if not found:
            cur_line_unit = None
            continue
        kind, pos, mk = found
        if kind == 'line':
            text = raw[pos + len(mk):]
            if cur_line_unit is not None and raw[:pos].strip() == '' and cur_line_unit[1][-1][0] == no - 1:
                cur_line_unit[1].append((no, text))
            else:
                cur_line_unit = (no, [(no, text)], False)
                units.append(cur_line_unit)
                if raw[:pos].strip() != '':
                    cur_line_unit = None  # 코드 뒤 주석은 이어 붙이지 않는다
            continue
        cur_line_unit = None
        start, end = mk
        rest = raw[pos + len(start):]
        idx = rest.find(end)
        body = [(no, rest if idx < 0 else rest[:idx])]
        units.append((no, body, True))
        if idx < 0:
            in_block = (end, body)
    return units


def scan(raw, line_m, block_m):
    """문자열 밖에서 처음 나오는 주석 시작 기호."""
    q, i = None, 0
    while i < len(raw):
        c = raw[i]
        if q:
            if c == '\\':
                i += 2
                continue
            if c == q:
                q = None
        elif c in '"\'`':
            q = c
        else:
            for s, e in block_m:
                if raw.startswith(s, i):
                    return 'block', i, (s, e)
            for m in line_m:
                if raw.startswith(m, i) and not (m == '//' and i > 0 and raw[i - 1] == ':'):
                    if m == '#' and raw.startswith('#!', i) and i == 0:
                        return None
                    return 'line', i, m
        i += 1
    return None


def clean(text):
    t = text.strip()
    t = re.sub(r'^\*+\s?', '', t).strip()
    t = re.sub(r'\*+/?$', '', t).strip()
    return t


def check_unit(path, unit, max_len, max_lines):
    start, body, is_block = unit
    texts = [(no, clean(t)) for no, t in body]
    texts = [(no, t) for no, t in texts if t]
    if not texts:
        return []
    header = is_block and any(HEADER_TAG.search(t) for _, t in texts)
    out = []
    prose = []
    for no, t in texts:
        if t.startswith('@'):
            if HEADER_TAG.match(t) or re.match(r'@(see|link|type|typedef|returns?\s*\{[^}]*\}\s*$)', t):
                continue
            t = TAG.sub('', t, count=1)
            if not t:
                continue
        prose.append((no, t))
    for no, t in prose:
        if len(t) > max_len and not header:
            out.append((no, 'LEN', f'{len(t)}자', t))
        dash, paren = len(DASH.findall(t)), t.count('(')
        if dash >= 2 or (dash and paren) or paren >= 2:
            out.append((no, 'STACK', '— ( ) 겹침', t))
        for rx, why in HIST:
            if rx.search(t):
                out.append((no, 'HIST', why, t))
        for rx, why in TONE:
            if rx.search(t):
                out.append((no, 'TONE', why, t))
    # 파일 헤더는 설명이 몇 줄 더 있어도 된다 — 줄마다 길이 대신 전체 줄 수만 본다
    limit = max_lines + 2 if header else max_lines
    if len(prose) > limit:
        out.append((prose[0][0], 'LINES', f'{"헤더 " if header else ""}{len(prose)}줄', prose[0][1]))
    return [(path,) + o for o in out]


def git(*args):
    r = subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        sys.exit(f'git {" ".join(args)} 실패: {r.stderr.strip()}')
    return r.stdout


def changed_lines(diff_args):
    """{파일: {추가된 줄번호}}"""
    root = git('rev-parse', '--show-toplevel').strip()
    out, cur = {}, None
    for ln in git('diff', '-U0', '--no-color', *diff_args).split('\n'):
        if ln.startswith('+++ '):
            p = ln[4:].strip()
            cur = None if p == '/dev/null' else os.path.join(root, p[2:] if p.startswith('b/') else p)
            if cur:
                out.setdefault(cur, set())
        elif ln.startswith('@@') and cur:
            m = re.search(r'\+(\d+)(?:,(\d+))?', ln)
            s, n = int(m.group(1)), int(m.group(2) or 1)
            out[cur].update(range(s, s + n))
    return out


def walk(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for d, dirs, files in os.walk(p):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for f in files:
                if os.path.splitext(f)[1].lower() in EXTS:
                    yield os.path.join(d, f)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--diff', metavar='BASE')
    ap.add_argument('--staged', action='store_true')
    ap.add_argument('--max-len', type=int, default=50)
    ap.add_argument('--max-lines', type=int, default=3)
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()

    only = None
    if a.diff or a.staged:
        only = changed_lines(['--cached'] if a.staged else [a.diff])
        files = [f for f in only if os.path.splitext(f)[1].lower() in EXTS and os.path.isfile(f)]
    elif a.paths:
        files = list(walk(a.paths))
    else:
        ap.error('파일·폴더 또는 --diff/--staged 를 준다')

    hits, units_n = [], 0
    for f in files:
        for u in extract(f):
            if only is not None and not any(no in only[f] for no, _ in u[1]):
                continue
            units_n += 1
            hits += check_unit(f, u, a.max_len, a.max_lines)

    cwd = os.getcwd()
    by_line = {}
    for path, no, rule, why, text in hits:
        k = (path, no)
        by_line.setdefault(k, [text, []])
        tag = rule if rule in ('STACK',) else f'{rule} {why}'
        if tag not in by_line[k][1]:
            by_line[k][1].append(tag)
    for (path, no), (text, tags) in by_line.items():
        rel = os.path.relpath(path, cwd) if os.path.splitdrive(path)[0] == os.path.splitdrive(cwd)[0] else path
        short = text if len(text) <= 70 else text[:69] + '…'
        print(f'{rel}:{no} [{", ".join(tags)}] {short}')
    c = Counter(h[2] for h in hits)
    print(f'\n주석 {units_n}개 검사, 걸린 줄 {len(by_line)}개 — ' +
          (', '.join(f'{k} {v}' for k, v in sorted(c.items())) or '없음'))
    sys.exit(1 if a.strict and hits else 0)


if __name__ == '__main__':
    main()
