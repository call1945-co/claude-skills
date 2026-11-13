# Claude Code skills

개인 Claude Code 스킬 모음. 폴더째 `~/.claude/skills/` 아래에 두면 된다.

| 스킬 | 하는 일 |
|:--|:--|
| `comment-check` | 코드 주석이 짧고 자연스러운 한국어인지, 코드에 없는 이유만 말하는지 검사하고 줄인 문장을 제안한다 |

## comment-check

- Claude Code 에서 `/comment-check` 또는 "주석 검사해줘"
- 스크립트만 쓸 때(Python 3, 표준 라이브러리만):
  ```
  python comment-check/scripts/check_comments.py <파일·폴더 ...>
  python comment-check/scripts/check_comments.py --diff origin/main   # 바뀐 줄의 주석만
  ```
  사유: `LEN` 50자 초과 · `LINES` 4줄 이상 · `STACK` `—`·`( )` 겹침 · `HIST` MR 번호·날짜·결정자 · `TONE` 번역투
