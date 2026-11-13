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

플러그인 스킬은 이름 앞에 플러그인 이름이 붙는다: `/jarvis-skills:comment-check`, `/jarvis-skills:feature-flow`. "주석 검사해줘", "브랜치 따서 개발해" 처럼 말해도 불러온다.

### comment-check

- 스크립트만 쓸 때(Python 3, 표준 라이브러리만):
  ```
  python skills/comment-check/scripts/check_comments.py <파일·폴더 ...>
  python skills/comment-check/scripts/check_comments.py --diff origin/main   # 바뀐 줄의 주석만
  ```
  사유: `LEN` 50자 초과 · `LINES` 4줄 이상 · `STACK` `—`·`( )` 겹침 · `HIST` MR 번호·날짜·결정자 · `TONE` 번역투

### feature-flow

- 기본값: `develop` → `staging` → `main`, 브랜치 `feature/{담당}-{기능}`, worktree `<루트>/.worktrees/`. 프로젝트 `CLAUDE.md` 에 다른 값이 있으면 그것을 따른다.

## 구조

```
.claude-plugin/marketplace.json   마켓플레이스 jarvis
.claude-plugin/plugin.json        플러그인 jarvis-skills
skills/<스킬>/SKILL.md
```
