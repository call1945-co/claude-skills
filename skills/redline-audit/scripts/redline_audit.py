"""
헥사고날 백엔드(Java·Spring)와 Vue 프론트의 Red Line 위반 후보를 저장소 전체(또는 바뀐 줄)에서 찾는다.
정규식 한 줄 검사로는 못 잡는 것까지 본다: import 없는 전체 이름 참조, DTO 안에 감싼 도메인 모델·Entity,
템플릿 클래스, 자식의 props 변경, 스토어가 받는 서버 데이터.

사용:
  python redline_audit.py <경로 ...> [--config <review-rules.json>] [--diff <기준>]
    --config : 없으면 경로 위쪽에서 .claude/review-rules.json 을 찾고, 그래도 없으면 기본값
    --diff   : 그 기준 이후 추가·수정된 줄의 후보만 (작업 트리 포함)
결과: 'RL ID  판정  파일:줄 | 사유 | 코드' 와 요약. FAIL 이 있으면 종료 코드 1.
dev-review 의 pre_mr_check.py 가 이 파일을 모듈로 불러 쓴다.
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter

SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', 'target', '.gradle', '.idea', '.worktrees', 'test', 'tests'}
FE_EXT = ('.vue', '.js', '.mjs', '.ts', '.scss')

DEFAULTS = {
    'backend': {
        # 경로에 처음 맞는 층으로 판정한다. 순서가 우선순위다.
        'layers': [['infra', r'/([\w-]+-)?(infra|infrastructure)/'], ['api', r'/([\w-]+-)?(api|web)/'],
                   ['batch', r'/([\w-]+-)?batch/'], ['core', r'/([\w-]+-)?(core|application)/'],
                   ['domain', r'/([\w-]+-)?domain/']],
        'infra_ref': r'\b[a-z]\w*(\.[a-z]\w*)*\.(infra|infrastructure)\.[\w.]*',
        'infra_module': r'project\(":[\w-]*infra[\w-]*"\)',
        'domain_model_dir': r'/domain/model/',
        'rl3_allow': [],
        'forbidden_tables': '',
        'foreign_tables': '',
        'own_tables': '',
        'external_dir': r'/infra/external/',
    },
    'frontend': {
        'external_style': False,
        'class_case': None,
        'third_party_class': r'^(ag-|v-|router-|swiper-|el-|q-|mdi|fa-|material-|vue-)',
        'eventbus': True,
        'server_data_imports': [],
        'common_components': None,
        'global_stores': [],
    },
    'rules': [],
}

RL3_TOKENS = re.compile(
    r'\b(RestClient|WebClient|RestTemplate|HttpClient|HttpURLConnection|OkHttpClient|FeignClient|S3Client|'
    r'FirebaseMessaging|JavaMailSender|JpaRepository|EntityManager|JdbcTemplate|PersistenceContext)\b'
    r'|java\.net\.http|new\s+Socket\s*\(|\.openConnection\s*\(|software\.amazon\.awssdk|com\.google\.firebase'
    r'|^\s*import\s+jakarta\.persistence\.')
DOMAIN_FW = re.compile(r'^\s*import\s+(org\.springframework\.|jakarta\.persistence\.|javax\.persistence\.)')
MUTATE = re.compile(r'\bprops\.\w+(?:\.\w+|\[[^\]]+\])*\s*(?:=(?!=)|\+\+|--|[+\-*/]=)'
                    r'|\bprops\.\w+(?:\.\w+|\[[^\]]+\])*\.(?:push|pop|splice|shift|unshift|sort|reverse|fill|set|delete|clear)\s*\(')
TRANSITION = re.compile(r'-(enter|leave|appear)(-from|-active|-to)?$|-move$')


def merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def find_config(paths):
    for p in paths:
        d = os.path.abspath(p if os.path.isdir(p) else os.path.dirname(p))
        while True:
            c = os.path.join(d, '.claude', 'review-rules.json')
            if os.path.isfile(c):
                return c
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
    return None


def load_config(paths, path=None):
    path = path or find_config(paths)
    cfg = DEFAULTS
    if path:
        with open(path, encoding='utf-8') as f:
            cfg = merge(DEFAULTS, json.load(f))
    return cfg, path


class Audit:
    def __init__(self, cfg):
        self.cfg = cfg
        be, fe = cfg['backend'], cfg['frontend']
        self.layers = [(n, re.compile(rx)) for n, rx in be['layers']]
        self.infra_ref = re.compile(be['infra_ref'])
        self.infra_module = re.compile(be['infra_module'])
        self.model_dir = re.compile(be['domain_model_dir'])
        self.rl3_allow = [re.compile(x) for x in be['rl3_allow']]
        self.forbidden = re.compile(be['forbidden_tables'], re.I) if be['forbidden_tables'] else None
        self.foreign = re.compile(be['foreign_tables']) if be['foreign_tables'] else None
        self.own = re.compile(be['own_tables']) if be['own_tables'] else None
        self.external_dir = re.compile(be['external_dir'])
        self.third = re.compile(fe['third_party_class'], re.I)
        self.rules = [(r['id'], r.get('sev', 'FAIL'), re.compile(r['pattern']), re.compile(r.get('files', '.')),
                       r.get('why', r.get('name', r['id'])), [re.compile(x) for x in r.get('exclude', [])])
                      for r in cfg['rules']]
        self.hits = []

    def add(self, rl, sev, path, no, why, code=''):
        self.hits.append((rl, sev, path, no, why, code.strip()[:110]))

    def layer(self, nf):
        for n, rx in self.layers:
            if rx.search(nf):
                return n
        return None

    # ---------- 백엔드 ----------
    def class_index(self, files):
        """단순 클래스 이름 → 'model' | 'entity'"""
        idx = {}
        for f in files:
            if not f.endswith('.java'):
                continue
            nf = norm(f)
            name = os.path.splitext(os.path.basename(f))[0]
            if self.layer(nf) == 'domain' and self.model_dir.search(nf):
                idx[name] = 'model'
            elif self.layer(nf) == 'infra' and any(re.match(r'\s*@(jakarta\.persistence\.|javax\.persistence\.)?Entity\b', l)
                                                   for l in read(f)):
                idx[name] = 'entity'
        return idx

    def check_java(self, nf, code, raw, idx):
        lay = self.layer(nf)
        inner = lay in ('core', 'domain')
        for no, line in enumerate(code, 1):
            if inner and self.infra_ref.search(line) and not line.lstrip().startswith('package '):
                self.add('BE-RL1', 'FAIL', nf, no, f'{lay} 가 infra 를 참조 — 필요한 능력은 Port 로 선언', raw[no - 1])
            if lay == 'domain' and DOMAIN_FW.search(line):
                self.add('BE-RL1', 'FAIL', nf, no, 'domain 이 프레임워크에 의존 — 순수 객체로', raw[no - 1])
            if lay in ('core', 'domain', 'api') and not any(a.search(nf) for a in self.rl3_allow) and RL3_TOKENS.search(line):
                self.add('BE-RL3', 'FAIL', nf, no, '외부 호출·영속 기술은 infra Adapter 에만 — Port 를 거친다', raw[no - 1])
            if self.forbidden and self.forbidden.search(line):
                self.add('BE-RL4', 'FAIL', nf, no, '금지 테이블 참조 — 권한·판정은 자체 테이블로만', raw[no - 1])
            elif (self.foreign and self.own and lay == 'infra' and not self.external_dir.search(nf)
                  and self.foreign.search(line) and self.own.search(' '.join(code[max(0, no - 6):no + 5]))):
                self.add('BE-RL4', 'WARN', nf, no, '외부 시스템 테이블을 자체 테이블과 함께 조회 — JOIN 이면 위반', raw[no - 1])
        if lay == 'api' and ('/controller/' in nf or any(re.search(r'@(Rest)?Controller\b', l) for l in code)):
            sig = re.compile(r'^\s*public\s+(?!class|record|interface|enum)([\w<>,\s?\[\].]+?)\s+\w+\s*\(')
            for no, line in enumerate(code, 1):
                m = sig.match(line)
                if m:
                    for t in re.findall(r'[A-Z]\w*', m.group(1)):
                        if t in idx:
                            self.add('BE-RL2', 'FAIL', nf, no,
                                     f'Controller 가 {kind(idx[t])} {t} 를 반환 — 응답 DTO 로 바꾼다', raw[no - 1])
                m = re.match(r'\s*import\s+[\w.]+\.(\w+)\s*;', line)
                if m and idx.get(m.group(1)) == 'entity':
                    self.add('BE-RL2', 'FAIL', nf, no, 'Controller 가 Entity 를 import', raw[no - 1])
        if lay == 'api' and '/dto/' in nf:
            resp = re.search(r'(Response|Res|Rslt|Dto|View|Row)\.java$', nf) is not None
            body = '\n'.join(code)
            comps = []
            m = re.search(r'\brecord\s+\w+\s*\(([^)]*)\)', body, re.S)
            if m:
                comps = re.findall(r'([A-Z][\w<>,\s?]*?)\s+\w+\s*(?:,|$)', m.group(1))
            comps += re.findall(r'^\s*(?:private|public|protected)\s+(?:final\s+)?([A-Z][\w<>,\s?]*?)\s+\w+\s*[;=]', body, re.M)
            for decl in comps:
                for t in re.findall(r'[A-Z]\w*', decl):
                    if t in idx:
                        no = next((i for i, l in enumerate(code, 1) if re.search(rf'\b{t}\b', l) and 'import' not in l), 1)
                        self.add('BE-RL2', 'FAIL' if resp else 'WARN', nf, no,
                                 f'DTO 가 {kind(idx[t])} {t} 를 필드로 감싼다 — 값만 옮긴 DTO 로', raw[no - 1])

    def check_build(self, nf, raw):
        if self.layer(nf) in ('core', 'domain'):
            for no, line in enumerate(raw, 1):
                if self.infra_module.search(line) and not line.strip().startswith('//'):
                    self.add('BE-RL1', 'FAIL', nf, no, 'core/domain 모듈이 infra 모듈에 의존', line)

    # ---------- 프론트 ----------
    def bad_class(self, c):
        case = self.cfg['frontend']['class_case']
        c = TRANSITION.sub('', c)  # Vue <Transition> 이 붙이는 접미사
        if case == 'snake':
            return bool(re.search(r'[A-Z-]', c))
        if case == 'kebab':
            return bool(re.search(r'[A-Z_]', c))
        return False

    def selector_classes(self, sel):
        sel = re.sub(r':(deep|global|slotted)\([^)]*\)', ' ', sel)
        return [c for c in re.findall(r'(?<![\w-])\.([A-Za-z_][\w-]*)', sel) if not self.third.match(c)]

    def check_fe(self, nf, ext, code, raw):
        fe = self.cfg['frontend']
        case = fe['class_case']
        if ext == '.scss':
            if case:
                for no, line in enumerate(code, 1):
                    if '{' in line and not line.lstrip().startswith('@'):
                        for c in self.selector_classes(line.split('{')[0]):
                            if self.bad_class(c):
                                self.add('FE-RL2', 'FAIL', nf, no, f'CSS 클래스 {c} — {case} case 로', raw[no - 1])
            return
        if ext == '.vue':
            if fe['external_style']:
                for no, line in enumerate(raw, 1):
                    s = line.strip()
                    if re.match(r'<style\b', s):
                        if 'src=' not in s:
                            self.add('FE-RL1', 'FAIL', nf, no, '.vue 안에 스타일 본문 — 같은 이름 .scss 로 옮기고 <style scoped src>', line)
                        elif 'scoped' not in s:
                            self.add('FE-RL1', 'WARN', nf, no, '<style> 연결은 scoped src 한 줄로', line)
            if case:
                in_tpl = False
                for no, line in enumerate(code, 1):
                    if re.match(r'\s*<template\b', raw[no - 1]):
                        in_tpl = True
                    if re.match(r'\s*<script\b', raw[no - 1]):
                        in_tpl = False
                    if not in_tpl:
                        continue
                    for m in re.finditer(r'(?<![:\w-])class="([^"]*)"', line):
                        for c in m.group(1).split():
                            if not self.third.match(c) and self.bad_class(c):
                                self.add('FE-RL2', 'FAIL', nf, no, f'템플릿 클래스 {c} — {case} case 로', raw[no - 1])
                    for m in re.finditer(r':class="([^"]*)"', line):
                        expr = re.sub(r"(===|!==|==|!=|<=|>=|<|>)\s*'[^']*'|'[^']*'\s*(===|!==|==|!=)", ' ', m.group(1))
                        names = re.findall(r"'([^']+)'", expr) + re.findall(r'[{,]\s*([A-Za-z_][\w-]*)\s*:', expr)
                        for n in names:
                            for c in n.split():
                                if not self.third.match(c) and self.bad_class(c) and not c.startswith('$'):
                                    self.add('FE-RL2', 'WARN', nf, no, f':class 의 {c} — {case} case 인지 확인', raw[no - 1])
        js = '\n'.join(code)
        for no, line in enumerate(code, 1):
            if fe['external_style'] and ext == '.vue' and re.search(r"^\s*import\s+['\"][^'\"]+\.(scss|css)['\"]", line):
                self.add('FE-RL1', 'FAIL', nf, no, 'script 에서 스타일 import — 전역 CSS 가 된다', raw[no - 1])
            if fe['eventbus']:
                if re.search(r'\b(EventBus|mitt\s*\(|\$on\s*\(|\$off\s*\(|\$once\s*\()', line):
                    self.add('FE-RL3', 'FAIL', nf, no, 'EventBus 금지 — props/emit·provide/inject·스토어', raw[no - 1])
                elif re.search(r'window\.dispatchEvent\(\s*new\s+CustomEvent|document\.dispatchEvent\(', line):
                    self.add('FE-RL3', 'WARN', nf, no, '전역 이벤트 — EventBus 대용인지 확인', raw[no - 1])
            if ext == '.vue' and 'defineProps' in js and MUTATE.search(line):
                self.add('FE-RL3', 'FAIL', nf, no, '자식이 prop 을 고친다 — emit·defineModel 로', raw[no - 1])
        imports = fe['server_data_imports']
        if imports and '/store' in nf and 'defineStore' in js:
            rx = re.compile(r"from\s+['\"](" + '|'.join(re.escape(i) for i in imports) + ')')
            for no, line in enumerate(code, 1):
                if rx.search(line):
                    self.add('FE-RL3', 'WARN', nf, no, '스토어가 서버 데이터를 직접 받는다 — 서버 데이터는 쿼리 캐시로', raw[no - 1])
        if fe['common_components'] and fe['common_components'] in nf:
            for no, line in enumerate(code, 1):
                m = re.search(r"from\s+['\"]@/stores?/([\w/.-]+)['\"]", line)
                if m and not any(g in m.group(1) for g in fe['global_stores']):
                    self.add('FE-RL3', 'WARN', nf, no, '공통 컴포넌트가 업무 스토어에 묶임 — props·inject 로 받으면 재사용된다', raw[no - 1])

    # ---------- 프로젝트 규칙 ----------
    def check_rules(self, nf, code, raw):
        for rid, sev, rx, files, why, excl in self.rules:
            if not files.search(nf) or any(e.search(nf) for e in excl):
                continue
            for no, line in enumerate(code, 1):
                if rx.search(line):
                    self.add(rid, sev, nf, no, why, raw[no - 1])

    def run(self, paths):
        files = list(walk(paths))
        idx = self.class_index(files)
        for f in files:
            nf = norm(f)
            raw = read(f)
            ext = os.path.splitext(f)[1]
            if nf.endswith(('build.gradle.kts', 'build.gradle')):
                self.check_build(nf, raw)
                continue
            code = strip_comments(raw, ext)
            if ext == '.java' and '/src/main/' in nf:
                self.check_java(nf, code, raw, idx)
            elif ext in ('.sql', '.xml') and self.forbidden and '/src/main/' in nf:
                for no, l in enumerate(code, 1):
                    if self.forbidden.search(l):
                        self.add('BE-RL4', 'FAIL', nf, no, '금지 테이블 참조', raw[no - 1])
            elif ext in FE_EXT:
                self.check_fe(nf, ext, code, raw)
            self.check_rules(nf, code, raw)
        return files

    def keep_lines(self, changed, file_level=True):
        """changed: 정규화 절대 경로 → 줄 번호 집합. 바뀐 줄의 후보만 남긴다.
        file_level 이면 스토어·공통 컴포넌트 WARN 은 파일만 바뀌어도 남긴다(문제가 파일 전체라서)."""
        self.hits = [h for h in self.hits if h[2] in changed
                     and (h[3] in changed[h[2]] or (file_level and h[0] == 'FE-RL3' and h[1] == 'WARN'))]


def kind(k):
    return '도메인 모델' if k == 'model' else 'Entity'


def strip_comments(lines, ext):
    """주석을 빈칸으로 바꾼 줄 목록 (줄 번호 유지). 문자열 안의 // 는 남긴다."""
    out, in_block, in_html = [], False, False
    for s in lines:
        i, buf, q = 0, [], None
        while i < len(s):
            if in_block:
                j = s.find('*/', i)
                if j < 0:
                    i = len(s)
                    break
                in_block = False
                i = j + 2
                continue
            if in_html:
                j = s.find('-->', i)
                if j < 0:
                    i = len(s)
                    break
                in_html = False
                i = j + 3
                continue
            c = s[i]
            if q:
                buf.append(c)
                if c == '\\' and i + 1 < len(s):
                    buf.append(s[i + 1])
                    i += 2
                    continue
                if c == q:
                    q = None
                i += 1
                continue
            if c in '"\'`':
                q = c
                buf.append(c)
                i += 1
                continue
            if s.startswith('/*', i):
                in_block = True
                i += 2
                continue
            if s.startswith('<!--', i) and ext in ('.vue', '.html', '.xml'):
                in_html = True
                i += 4
                continue
            if s.startswith('//', i) and not (i and s[i - 1] == ':'):
                break
            if s.startswith('--', i) and ext == '.sql':
                break
            buf.append(c)
            i += 1
        out.append(''.join(buf))
    return out


def walk(paths):
    for p in paths:
        if os.path.isfile(p):
            yield os.path.abspath(p)
            continue
        for d, dirs, files in os.walk(p):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for f in files:
                if f.endswith(('.java', '.sql', '.xml', '.kts', '.gradle') + FE_EXT):
                    yield os.path.abspath(os.path.join(d, f))


def norm(p):
    return p.replace('\\', '/')


def read(p):
    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            return f.read().split('\n')
    except OSError:
        return []


def changed_lines(paths, base):
    out = {}
    for p in paths:
        d = p if os.path.isdir(p) else os.path.dirname(p)
        r = subprocess.run(['git', '-C', d, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if r.returncode:
            continue
        root = r.stdout.strip()
        diff = subprocess.run(['git', '-C', root, 'diff', '-U0', '--no-color', base], capture_output=True,
                              text=True, encoding='utf-8', errors='replace').stdout
        cur = None
        for ln in diff.split('\n'):
            if ln.startswith('+++ '):
                cur = None if ln.endswith('/dev/null') else norm(os.path.abspath(os.path.join(root, ln[6:])))
                if cur:
                    out.setdefault(cur, set())
            elif ln.startswith('@@') and cur:
                m = re.search(r'\+(\d+)(?:,(\d+))?', ln)
                s, n = int(m.group(1)), int(m.group(2) or 1)
                out[cur].update(range(s, s + n))
    return out


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    base = cfg_path = None
    if '--diff' in args:
        i = args.index('--diff')
        base = args[i + 1]
        del args[i:i + 2]
    if '--config' in args:
        i = args.index('--config')
        cfg_path = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 2
    cfg, used = load_config(args, cfg_path)
    print(f'설정: {used or "기본값 (.claude/review-rules.json 없음)"}\n')
    a = Audit(cfg)
    files = a.run(args)
    if base:
        a.keep_lines(changed_lines(args, base))
    a.hits.sort(key=lambda h: (h[0], h[1] != 'FAIL', h[2], h[3]))
    for rl, sev, path, no, why, code in a.hits:
        print(f'{rl:7} {sev:4}  {path}:{no} | {why} | {code}')
    c = Counter((h[0], h[1]) for h in a.hits)
    print(f'\n파일 {len(files)}개 — ' + (', '.join(f'{k[0]} {k[1]} {v}' for k, v in sorted(c.items())) or '위반 후보 없음'))
    return 1 if any(h[1] == 'FAIL' for h in a.hits) else 0


if __name__ == '__main__':
    sys.exit(main())
