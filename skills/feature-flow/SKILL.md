---
name: feature-flow
description: git worktree + GitLab Flow 기능 개발 흐름 — feature 브랜치를 worktree 로 따로 떠서 개발하고, develop 따라가기·MR(glab)/PR(gh) 생성·머지 후 정리·긴급 수정까지 진행한다. "브랜치 따서 개발", "워크트리 만들어", "새 기능 시작", "MR 올려", "PR 올려", "develop 반영", "작업 끝났어 정리해", "feature 브랜치" 처럼 새 작업을 시작하거나 끝낼 때 로드한다. 프로젝트에 전용 흐름 스킬이 있으면 그쪽을 따른다.
---

# 기능 개발 흐름 (worktree + GitLab Flow)

브랜치 하나에 worktree 하나를 둔다. 원본 작업 폴더는 건드리지 않고, 환경 브랜치는 `develop` → `staging` → `main` 한 방향으로만 흐른다.

```
① 시작: origin/develop 에서 worktree + feature/{담당}-{기능}
② 개발: 프로젝트 규칙대로, 작게 커밋
③ 따라가기: 하루 1회 origin/develop merge
④ 점검: 빌드·테스트·린트 + 새 맥락 리뷰
⑤ MR/PR: develop 으로
⑥ 리뷰·머지: 리뷰어 몫
⑦ 정리: worktree 제거, 로컬 브랜치 삭제
```

## 0. 프로젝트 값

처음 쓸 때 프로젝트 `CLAUDE.md`·README·기존 브랜치 이름에서 아래 값을 찾는다. 없으면 기본값을 쓰되 사용자에게 한 번 확인하고, `CLAUDE.md` 에 적어 두자고 제안한다.

| 항목 | 기본값 |
|:--|:--|
| 루트 `$R` | git 저장소 최상위. 저장소 여러 개를 묶은 상위 폴더가 있으면 그 폴더 |
| 분기 기준 / MR 목적지 | `origin/develop` (hotfix 도 같다 — upstream first). `develop` 이 없는 저장소는 `main` |
| 브랜치 이름 | `feature/{담당}-{기능}`, 긴급 `hotfix/{요약}`. 담당·기능은 소문자·하이픈 |
| 커밋 제목 | `[feat|fix|docs|refactor|test|chore][브랜치명] 요약` |
| worktree 위치 | `$R/.worktrees/{저장소 약칭}--{담당}-{기능}` |
| 원격 도구 | GitLab `glab`, GitHub `gh` |

- worktree 를 `$R` 아래 숨김 폴더에 두는 이유: 프로젝트 `CLAUDE.md`·스킬이 그대로 적용되고 소스 폴더와 섞여 보이지 않는다. `.worktrees/` 는 `.gitignore` 나 `.git/info/exclude` 에 넣는다.
- 금지: 환경 브랜치(`develop`·`staging`·`main`)에서 커밋·푸시, 환경 브랜치를 feature 로 역머지(`origin/develop` 만 가져온다), `--force`(개인 브랜치의 `--force-with-lease` 만).
- 담당 값을 모르면 묻는다.

## 1. 시작 — worktree 생성

```bash
R=<루트>
REPO=<저장소 폴더>            # 단일 저장소면 R 과 같다
BR=feature/<담당>-<기능>
WT=$R/.worktrees/<약칭>--<담당>-<기능>

git -C $R/$REPO fetch origin
git -C $R/$REPO worktree add -b $BR "$WT" origin/develop
git -C "$WT" push -u origin $BR       # 원격 브랜치 생성 (선택, 백업 겸)
```

- 같은 이름의 브랜치·폴더가 이미 있으면 새로 만들지 말고 이어서 쓸지 묻는다.
- 시작 전 `git -C $R/$REPO status` 로 원본 폴더의 미커밋 변경을 확인만 한다(worktree 는 원본에 영향 없음).
- **분기 전 환경 브랜치 정렬 확인** — 예전 이력 때문에 `develop` 이 `main` 보다 뒤처져 있을 수 있다.
  ```bash
  git -C $R/$REPO merge-base --is-ancestor origin/main origin/develop && echo "develop ⊇ main" || echo "develop 이 main 보다 뒤처짐"
  git -C $R/$REPO log --oneline origin/develop..origin/main   # develop 에 없는 main 커밋
  ```
  뒤처져 있으면 그 상태로 분기하지 않고 보고한다. 저장소 관리자가 `develop` 을 맞춘다 — `develop` 이 `main` 의 조상이면 FF 푸시(`git push origin origin/main:develop`), 아니면 `main`→`develop` 머지 MR. upstream-first 를 복원하는 1회성 조치이지 역머지 허용이 아니다. 환경 브랜치 푸시는 Claude 가 하지 않는다.

### 환경 준비

| 대상 | 할 일 |
|:--|:--|
| Node | worktree 마다 `node_modules` 가 따로 필요하다. `"$WT"` 에서 `npm ci`(workspaces 면 루트에서만). 원본 `node_modules` 를 junction·symlink 로 공유하는 것은 lock 파일이 같을 때 빌드 확인용으로만 쓴다. `package.json`·lock 을 바꿨으면 반드시 새로 `npm ci` 해서 확인한다 |
| 동시 실행 | 다른 worktree 의 dev 서버와 포트가 겹치면 포트를 바꾼다(`-- --port 5174`, `--server.port=8081`). 프록시 대상은 gitignore 된 로컬 env 파일로 바꾼다 |
| Gradle·Maven | 캐시는 공유된다. 그대로 빌드 |
| 공용 개발 DB | 모든 worktree 가 같은 DB 를 쓴다. 스키마·시드를 바꾸는 작업은 동시에 하지 않고, 바꾸면 사용자에게 알린다 |
| IDE | worktree 폴더를 별도 프로젝트로 연다 |

이후 이 작업의 파일 읽기·수정·명령은 모두 **`$WT` 절대경로**로 한다. 원본 저장소 폴더를 고치지 않는다.

## 2. 개발 중

- 커밋은 기능 단위로 작게, 제목 규칙대로. 푸시는 사용자가 요청할 때.
- MR 하나는 기능 하나, 변경 약 400줄 이하를 목표로 한다. 넘으면 나눌 지점을 제안한다.

## 3. develop 따라가기 (하루 1회, MR 직전 필수)

```bash
git -C "$WT" fetch origin
git -C "$WT" merge origin/develop        # 혼자 쓰는 브랜치면 rebase 도 가능 → 푸시는 --force-with-lease
```

충돌 시:
1. `git -C "$WT" diff --name-only --diff-filter=U` 로 파일 목록을 보고 각 충돌 블록을 읽는다.
2. 두 변경의 의도를 모두 살린다. 상대 변경 이유는 `git log origin/develop -- <파일>` 로 확인한다.
3. 충돌 표시 제거 → `git diff --check` → `git add`.
4. 충돌이 없던 파일까지 빌드로 확인한다(상대가 지운 함수·상수를 내 코드가 쓰는지 grep).
5. `git commit` (머지 커밋 메시지 기본값 유지).
6. 업무 규칙·상태값·인터페이스 시그니처가 걸린 충돌은 임의로 정하지 말고 사용자에게 보인다.

## 4. 점검

CI 가 없거나 느리면 MR 전에 직접 돌린다.
- 빌드·테스트·린트. 프로젝트에 점검 스크립트나 리뷰 스킬이 있으면 그것을 쓴다.
- 미커밋 변경 없음, `origin/develop` 최신 반영, 커밋 제목 규칙, 자격증명 평문 없음을 확인한다.
- 리뷰는 코드를 쓴 맥락과 분리한다 — 서브에이전트에게 diff 범위와 프로젝트 규칙 파일만 주고 정확성·누락·보안을 보게 한다. 지적은 인용한 줄을 직접 열어 확인한 뒤 반영한다.

## 5. MR / PR 생성

외부에 게시되는 동작이다. **제목·본문 초안을 보여 주고 승인받은 뒤** 실행한다.

```bash
git -C "$WT" push -u origin $BR

# GitLab
cd "$WT" && glab mr create --source-branch $BR --target-branch develop \
  --title "[feat][$BR] 요약" --description "$(cat <본문 파일>)" --remove-source-branch --yes

# GitHub
cd "$WT" && gh pr create --base develop --head $BR \
  --title "[feat][$BR] 요약" --body-file <본문 파일>
```

본문 템플릿:

```markdown
## 변경 요약
- …

## 관련
- 이슈: #n / 결정 기록: …
- 다른 영역 영향: 없음 | (공유 인터페이스·상태값·응답 규격 변경 내용)

## 확인
- [x] origin/develop 반영, 충돌 없음
- [x] 빌드 · 테스트 · 린트
- [x] 리뷰: 지적 n건 반영, 남은 위험 …

## 리뷰어에게
- 특히 봐 줄 곳: …
```

- 목적지는 항상 `develop`. `staging`/`main` 을 요청받으면 규칙을 설명하고 확인받는다(승격 MR 은 관리자 몫).
- 결과 URL 을 알려 준다.

## 6. 머지 후 정리

```bash
git -C $R/$REPO fetch origin --prune
git -C $R/$REPO worktree remove "$WT"         # 미커밋 변경이 있으면 실패 — 지우지 말고 보고
git -C $R/$REPO branch -d $BR                 # 머지 안 된 브랜치면 실패 — -D 쓰지 말고 보고
```

- `node_modules` 를 junction·symlink 로 공유했다면 **링크부터 제거**하고(PowerShell `(Get-Item <경로>\node_modules).Delete()`, POSIX `rm <경로>/node_modules`) worktree 를 지운다. `Remove-Item -Recurse` 나 `worktree remove --force` 를 먼저 쓰면 원본 `node_modules` 까지 지워질 수 있다.
- squash 머지였다면 `branch -d` 가 실패할 수 있다. 원격 브랜치가 지워졌고 MR 이 머지됐는지 확인한 뒤 사용자 승인을 받고 `-D`.
- `git worktree list` 로 남은 worktree 를 보여 준다.

## 7. 긴급 수정 (hotfix)

`origin/develop` 에서 `hotfix/{요약}` worktree → `develop` MR(긴급 표시) → 머지된 커밋을 `origin/main`(필요하면 `staging`) 기준 새 브랜치에 `git cherry-pick -x` → 하류 MR. 하류 MR·태그는 관리자 승인 사항이므로 초안까지만 만들고 넘긴다.
