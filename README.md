# Claude Code skills

개인 Claude Code 스킬 묶음. Claude Code 플러그인(`jarvis-skills`)으로 설치한다.

## 설치

Claude Code 안에서:
```
/plugin marketplace add call1945-co/claude-skills
/plugin install jarvis-skills@jarvis
```
또는 터미널에서 `claude plugin marketplace add call1945-co/claude-skills` → `claude plugin install jarvis-skills@jarvis`.

- 비공개 저장소라 GitHub 자격증명(gh 로그인 등)이 있어야 받아진다.
- 업데이트: `/plugin marketplace update jarvis` 후 `/plugin` 에서 업데이트. 스킬을 고치면 `.claude-plugin/` 두 파일의 `version` 을 올린다.

## 스킬

| 스킬 | 하는 일 |
|:--|:--|
| `comment-check` | 코드 주석이 짧고 자연스러운 한국어인지, 코드에 없는 이유만 말하는지 검사하고 줄인 문장을 제안한다 |
| `feature-flow` | git worktree 로 feature 브랜치를 따로 떠서 개발하고, develop 따라가기·MR/PR·머지 후 정리·hotfix 까지 GitLab Flow 로 진행한다 |
| `hexagonal-architecture` | 헥사고날 멀티모듈 Java/Spring 백엔드의 의존 방향·Red Line·패키지·Port/UseCase 명명·층별 규칙 |
| `isms-compliance` | ISMS-P 기준 개인정보 암호화(봉투암호화·HMAC 검색 해시)·접속기록·계정/세션 통제·데이터 권한 범위 |
| `redline-audit` | 저장소 전체에서 Red Line 위반 후보를 스크립트로 찾고 하나씩 판정해 확정 목록을 만든다 |
| `dev-review` | MR 전 셀프 리뷰: 기계 점검(pre_mr_check) → 새 맥락 AI 리뷰 → 지적 검증 → MR 본문 요약 |
| `mr-review` | 리드가 남의 MR/PR 을 리뷰: worktree 재점검 → 영역 간 영향·보호 영역·보안 중심 리뷰 → 판정 제안 |

플러그인 스킬은 이름 앞에 플러그인 이름이 붙는다: `/jarvis-skills:comment-check`, `/jarvis-skills:feature-flow`. "주석 검사해줘", "브랜치 따서 개발해" 처럼 말해도 불러온다.
프로젝트에 같은 일을 하는 전용 스킬이 있으면 그쪽을 따른다(각 스킬 description 에 적혀 있다).

### comment-check

- 스크립트만 쓸 때(Python 3, 표준 라이브러리만):
  ```
  python skills/comment-check/scripts/check_comments.py <파일·폴더 ...>
  python skills/comment-check/scripts/check_comments.py --diff origin/main   # 바뀐 줄의 주석만
  ```
  사유: `LEN` 50자 초과 · `LINES` 4줄 이상 · `STACK` `—`·`( )` 겹침 · `HIST` MR 번호·날짜·결정자 · `TONE` 번역투

### feature-flow

- 기본값: `develop` → `staging` → `main`, 브랜치 `feature/{담당}-{기능}`, worktree `<루트>/.worktrees/`. 프로젝트 `CLAUDE.md` 에 다른 값이 있으면 그것을 따른다.

### redline-audit · dev-review · mr-review

- 프로젝트 값은 프로젝트 루트 `.claude/review-rules.json` 에 둔다(층 경로, 패키지, 금지 테이블, 프론트 규칙, 프로젝트 정규식 규칙, 빌드 명령). 키와 예시: `skills/redline-audit/references/review-rules.md`. 없으면 기본값으로 돈다.
- 스크립트만 쓸 때(Python 3, 표준 라이브러리만):
  ```
  python skills/redline-audit/scripts/redline_audit.py <백엔드> <프론트> [--diff origin/develop]
  python skills/dev-review/scripts/pre_mr_check.py <저장소> [--base origin/develop] [--test] [--no-build]
  ```
  `pre_mr_check.py` 는 `redline_audit.py` 를 불러 쓰므로 두 폴더를 함께 둔다.

## 구조

```
.claude-plugin/marketplace.json   마켓플레이스 jarvis
.claude-plugin/plugin.json        플러그인 jarvis-skills
skills/<스킬>/SKILL.md
```
