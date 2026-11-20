# -*- coding: utf-8 -*-
"""
MR 사전 점검기 — 결과가 늘 같은 규칙만 기계로 판정한다. 로직·설계·누락은 AI·사람 리뷰 몫.

기준 브랜치 대비 이 브랜치에서 추가·수정된 줄만 본다(기존 코드의 위반은 이 MR 책임이 아니다).
Red Line 은 redline-audit 스킬의 redline_audit.py 를 모듈로 불러 같은 판정을 쓴다.

사용:
  python pre_mr_check.py <저장소 경로> [--base origin/develop] [--config <review-rules.json>]
                         [--no-build] [--test] [--no-fetch]
    --base     : 비교 기준. 없으면 설정 base, 그것도 없으면 origin/develop → origin/main 순으로 있는 것
    --config   : 없으면 저장소 위쪽에서 .claude/review-rules.json 을 찾는다
    --no-build : 빌드 생략
    --test     : 테스트도 실행
    --no-fetch : git fetch 생략
종료코드: 0 = 통과, 1 = FAIL 있음
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.normpath(os.path.join(HERE, "..", "..", "redline-audit", "scripts", "redline_audit.py"))

PRE_DEFAULTS = {
    "base": None,
    "branch": {
        "env": ["develop", "staging", "main", "master"],
        "pattern": r"^(feature|hotfix)/[a-z0-9]+-[a-z0-9-]+$",
        "commit_pattern": r"^\[(feat|fix|docs|refactor|test|chore)\]\[[^\]]+\] \S",
    },
    "pii_fields": [],
    "audit_annotation": None,
    "naming_cmd": None,
    "build": None,
    "test": None,
}

results = []  # (상태, 검사명, 상세)
ADDED = {}    # 저장소 기준 상대 경로 → 추가·수정된 줄 번호


def load_audit():
    spec = importlib.util.spec_from_file_location("redline_audit", AUDIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {r.stderr.strip()}")
    return r.stdout if r.returncode == 0 else ""


def add(status, name, details=None):
    results.append((status, name, details or []))


def read(repo, rel):
    p = os.path.join(repo, rel)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def scan(repo, files, pattern, name, where=lambda f: True, skip_comment=True, sev="FAIL"):
    rx = re.compile(pattern)
    hits = []
    for f in files:
        if not where(f):
            continue
        for no, line in enumerate(read(repo, f) or [], 1):
            if no not in ADDED.get(f, ()):
                continue
            s = line.strip()
            if len(s) > 400:  # base64 폰트·이미지 같은 데이터 줄
                continue
            if skip_comment and s.startswith(("//", "*", "/*", "#", "--", "<!--")):
                continue
            if rx.search(line):
                hits.append(f"{f}:{no}  {s[:140]}")
    add(sev if hits else "PASS", name, hits)


def run(repo, cmd, name):
    print(f"  … {name}: {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=(os.name == "nt"))
    tail = (r.stdout + r.stderr).strip().splitlines()[-15:]
    add("PASS" if r.returncode == 0 else "FAIL", name, [] if r.returncode == 0 else tail)


def default_cmds(repo, test):
    """빌드 도구를 보고 고른 기본 명령."""
    cmds = []
    win = os.name == "nt"
    if os.path.isfile(os.path.join(repo, "gradlew")):
        gw = ".\\gradlew.bat" if win else "./gradlew"
        cmds.append(("빌드 gradle", [gw, "build", "-x", "test", "-q", "--console=plain"]))
        if test:
            cmds.append(("테스트 gradle", [gw, "test", "-q", "--console=plain"]))
    elif os.path.isfile(os.path.join(repo, "pom.xml")):
        mvn = (".\\mvnw.cmd" if win else "./mvnw") if os.path.isfile(os.path.join(repo, "mvnw")) else "mvn"
        cmds.append(("빌드 maven", [mvn, "-q", "-DskipTests", "package"]))
        if test:
            cmds.append(("테스트 maven", [mvn, "-q", "test"]))
    pkg = os.path.join(repo, "package.json")
    if os.path.isfile(pkg):
        with open(pkg, encoding="utf-8") as f:
            scripts = json.load(f).get("scripts", {})
        if "build" in scripts:
            cmds.append(("빌드 npm", ["npm", "run", "build"]))
        if test and "test" in scripts:
            cmds.append(("테스트 npm", ["npm", "test"]))
    return cmds


def main(argv):
    def opt(name):
        if name in argv:
            i = argv.index(name)
            v = argv[i + 1]
            del argv[i:i + 2]
            return v
        return None

    base, cfg_path = opt("--base"), opt("--config")
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 1
    repo = os.path.abspath(paths[0])
    ra = load_audit()
    cfg, used = ra.load_config([repo], cfg_path)
    cfg = ra.merge(PRE_DEFAULTS, cfg)
    root = os.path.dirname(os.path.dirname(used)) if used else repo

    if "--no-fetch" not in argv:
        git(repo, "fetch", "origin", "-q")
    if not base:
        base = cfg["base"] or next((b for b in ("origin/develop", "origin/main", "origin/master")
                                    if git(repo, "rev-parse", "--verify", "-q", b, check=False)), "origin/main")

    branch = git(repo, "branch", "--show-current").strip()
    merge_base = git(repo, "merge-base", base, "HEAD").strip()
    files = sorted(set(git(repo, "diff", "--name-only", "--diff-filter=ACMR", f"{merge_base}..HEAD").split()))
    dirty = git(repo, "status", "--porcelain").splitlines()
    cur = None
    for line in git(repo, "diff", "-U0", "--no-color", f"{merge_base}..HEAD").splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and cur:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start, cnt = int(m.group(1)), int(m.group(2) or 1)
            ADDED.setdefault(cur, set()).update(range(start, start + cnt))

    print(f"저장소 {repo}\n브랜치 {branch} | 기준 {base} | 변경 파일 {len(files)}개\n설정 {used or '기본값'}\n")

    # 0. 브랜치·작업 상태
    br = cfg["branch"]
    if branch in br["env"]:
        add("FAIL", "환경 브랜치에서 작업하지 않음", [f"현재 브랜치 {branch} — feature 브랜치에서 작업"])
    else:
        ok = not br["pattern"] or re.match(br["pattern"], branch)
        add("PASS" if ok else "WARN", "브랜치 이름 규칙", [] if ok else [branch])
    add("WARN" if dirty else "PASS", "커밋 안 된 변경 없음", dirty[:20])
    behind = int(git(repo, "rev-list", "--count", f"HEAD..{base}").strip() or 0)
    add("WARN" if behind else "PASS", f"{base} 최신 반영",
        [f"{base} 에 {behind}개 커밋이 더 있음 — git merge {base}"] if behind else [])
    if br["commit_pattern"]:
        subjects = git(repo, "log", "--format=%s", f"{merge_base}..HEAD").splitlines()
        bad = [s for s in subjects if not s.startswith("Merge") and not re.match(br["commit_pattern"], s)]
        add("WARN" if bad else "PASS", "커밋 제목 규칙", bad)

    # 1. 공통
    scan(repo, files, r"^(<<<<<<<|=======|>>>>>>>)( |$)", "충돌 표시 없음", skip_comment=False)
    scan(repo, files,
         r"(?i)(arn:aws:kms:|\bAKIA[0-9A-Z]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY|(password|passwd|pswd|secret|token|apikey|api_key)\w*\s*[:=]\s*['\"][^'\"\s$<{]{6,}['\"])",
         "자격증명 평문 없음 — 소스·문서", skip_comment=False)
    scan(repo, files, r"(?i)^\s*[\w.-]*(password|passwd|secret|token|api-?key)[\w.-]*\s*[:=]\s*[^\s$'\"{][^\s]{5,}",
         "자격증명 평문 없음 — 설정 파일",
         lambda f: f.endswith((".yml", ".yaml", ".properties")) or os.path.basename(f).startswith(".env"),
         skip_comment=False)

    # 2. Red Line + 프로젝트 규칙 (redline_audit 판정을 바뀐 줄로 좁힌다)
    audit = ra.Audit(cfg)
    audit.run([repo])
    audit.keep_lines({ra.norm(os.path.abspath(os.path.join(repo, f))): v for f, v in ADDED.items()}, file_level=False)
    by_rl = {}
    for rl, sev, path, no, why, code in audit.hits:
        by_rl.setdefault(rl, []).append((sev, f"{os.path.relpath(path, repo).replace(os.sep, '/')}:{no}  {why} | {code}"))
    if not by_rl:
        add("PASS", "Red Line·프로젝트 규칙 (redline_audit)")
    for rl in sorted(by_rl):
        sevs = [s for s, _ in by_rl[rl]]
        add("FAIL" if "FAIL" in sevs else "WARN", f"{rl} (redline_audit)", [d for _, d in by_rl[rl]])

    java = lambda f: f.endswith(".java") and "/src/main/" in f
    if cfg["pii_fields"]:
        fields = "|".join(re.escape(x) for x in cfg["pii_fields"])
        scan(repo, files, rf"(?i)\blog\.(info|debug|warn|error|trace)\(.*\b({fields})\b",
             "로그의 개인정보는 마스킹 값만 (휴리스틱 — 줄을 직접 확인)", java, sev="WARN")
    aa = cfg["audit_annotation"]
    if aa:
        miss = []
        for f in files:
            if not (java(f) and "/controller/" in f):
                continue
            lines = read(repo, f) or []
            for i, line in enumerate(lines):
                if i + 1 in ADDED.get(f, ()) and re.search(r"@(Get|Post)Mapping", line) and re.search(aa["mapping"], line, re.I):
                    if aa["name"] not in "\n".join(lines[max(0, i - 4):i + 5]):
                        miss.append(f"{f}:{i + 1}  {line.strip()[:120]}")
        add("WARN" if miss else "PASS", f"개인정보 조회·다운로드 {aa['name']} (휴리스틱)", miss)

    # 3. 명명 검사기 — 'ERROR|WARN 경로:줄 …' 을 출력하는 프로젝트 명령
    if cfg["naming_cmd"]:
        cmd = [os.path.join(root, a) if os.path.isfile(os.path.join(root, a)) else a for a in cfg["naming_cmd"]]
        targets = [f for f in files if f.endswith((".java", ".sql", ".kt")) and os.path.isfile(os.path.join(repo, f))]
        hits = []
        for i in range(0, len(targets), 40):
            r = subprocess.run([*cmd, *targets[i:i + 40]], cwd=repo, capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            for l in r.stdout.splitlines():
                m = re.match(r"(ERROR|WARN)\s+(\S+?):(\d+)\s", l)
                if m and int(m.group(3)) in ADDED.get(m.group(2).replace("\\", "/"), ()):
                    hits.append(l)
        errs = [h for h in hits if h.startswith("ERROR")]
        add("FAIL" if errs else ("WARN" if hits else "PASS"), "명명 규칙 — 추가된 줄", hits[:40])

    # 4. 빌드·테스트
    if "--no-build" not in argv:
        test = "--test" in argv
        if cfg["build"] or (test and cfg["test"]):
            cmds = [("빌드", c) for c in cfg["build"] or []] + ([("테스트", c) for c in cfg["test"] or []] if test else [])
        else:
            cmds = default_cmds(repo, test)
        for name, c in cmds:
            run(repo, c, name)

    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
    print("\n| 결과 | 검사 |\n|:--:|:--|")
    for st, name, _ in results:
        print(f"| {icon[st]} {st} | {name} |")
    for st, name, det in results:
        if st != "PASS" and det:
            print(f"\n### {icon[st]} {name}")
            for d in det[:40]:
                print(f"- {d}")
    fails = sum(1 for r in results if r[0] == "FAIL")
    warns = sum(1 for r in results if r[0] == "WARN")
    print(f"\n요약: FAIL {fails} | WARN {warns} | PASS {len(results) - fails - warns}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
