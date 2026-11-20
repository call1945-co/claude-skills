---
name: mr-review
description: Use when a tech lead or reviewer wants to review someone else's GitLab MR or GitHub PR — "MR 리뷰", "PR 리뷰", "!12 봐줘", "#34 봐줘", "머지해도 돼?", "승격 MR 검토", or when an MR/PR link is given. Reviewing your own changes before opening an MR is dev-review. If the project has its own MR review skill, follow that one.
---

# MR 리뷰 (리드)

개발자 셀프 리뷰(`dev-review`)를 거친 MR 을 다른 관점으로 본다. 셀프 리뷰가 "이 변경이 맞게 동작하는가"를 본다면, 리드 리뷰는 **"이 변경이 시스템·팀·규정에 안전한가"**를 본다.
AI 는 요약하고 위험 지점을 뽑는다. **승인·머지·코멘트 게시는 사용자가 명시적으로 지시할 때만** 한다.

## 0. 프로젝트 값

| 항목 | 찾는 곳 → 없을 때 |
|:--|:--|
| 원격 도구 | GitLab `glab`, GitHub `gh` (원격 URL 로 판단) |
| 브랜치 흐름 | `CLAUDE.md`·흐름 스킬 → feature/hotfix → `develop`, 승격 `develop→staging→main` |
| 보호 영역(베이스라인) | `CLAUDE.md` 에 리드 확인이 필요하다고 적힌 패키지·파일(보안·인증·암호화·DB 설정 등) → 없으면 보안·인증·암호화·영속 설정·공용 모듈 |
| 결정 기록 | ADR·아키텍처 정의서 경로 |
| worktree 위치 | `<루트>/.worktrees/` |

## 1. MR 정보 수집

```bash
glab mr view <번호>               # gh pr view <번호>
glab mr view <번호> --comments    # gh pr view <번호> --comments
glab mr diff <번호>               # gh pr diff <번호>  (크면 파일로 저장해 나눠 읽는다)
```

먼저 아래 두 가지를 확인하고 사용자에게 한 줄로 보고한다.
- **목적지가 규칙에 맞는가**: feature·hotfix 는 `develop`, 승격은 정해진 방향만 허용한다. 어긋나면 리뷰 전에 지적한다.
- 본문에 셀프 리뷰 결과 요약이 있는가. 없으면 "셀프 리뷰 누락"을 첫 지적으로 둔다.

## 2. 소스 브랜치를 별도 worktree 에 꺼내 다시 점검

리뷰어의 작업 폴더는 건드리지 않는다.

```bash
git -C <저장소> fetch origin <소스브랜치>
git -C <저장소> worktree add --detach "<루트>/.worktrees/review--<저장소>-mr<번호>" origin/<소스브랜치>
python -I <플러그인 skills 폴더>/dev-review/scripts/pre_mr_check.py "<worktree>" --base origin/<목적지>
```

- `<플러그인 skills 폴더>` 는 이 스킬 Base directory 의 상위 폴더다.
- detached 라서 나오는 브랜치 이름 WARN 은 무시한다.
- FE 빌드에는 worktree 에 `node_modules` 가 필요하다. lock 파일이 원본과 같으면 링크(Windows junction, `ln -s`)로 잇고 빌드만 확인한다. 끝나면 **링크만 지운다**(PowerShell `(Get-Item <경로>\node_modules).Delete()`, `rm <링크>`). lock 파일이 바뀐 MR 은 새로 설치해서 확인한다.
- 개발자가 보고한 결과와 다르면 그 차이 자체가 지적 사항이다.

## 3. 리드 관점 리뷰 — 서브에이전트

Agent 도구(general-purpose)에 맡긴다. 프롬프트는 아래를 채워서 쓴다.

```
<프로젝트> MR <번호>(<소스> → <목적지>)를 리드 관점에서 리뷰한다. 코드 수정·게시 금지.
코드: <worktree 경로>, 범위: git diff origin/<목적지>...HEAD
먼저 읽을 것: <CLAUDE.md>, <ADR·아키텍처 정의서>, <아키텍처·보안·명명·영역 스킬 경로>.
MR 본문의 셀프 리뷰 결과: <붙여넣기>
셀프 리뷰가 이미 본 단일 로직 버그보다 아래에 집중:
 1. 영역 간 영향: 여러 팀·영역이 함께 쓰는 도메인·포트 시그니처·상태코드·응답 규격·오류 코드 대역 변경,
    API 경로·DTO 필드 변경을 FE/BE 가 함께 반영했는지, 다른 화면·배치가 쓰는 코드 영향
 2. 보호 영역 변경: <보호 영역 목록> — 바뀌었으면 무조건 "리드 확인 필요"로 표시
 3. 아키텍처: 의존 방향, 새 Port/UseCase 가 기존 것과 겹치는지, 명명 규칙, ADR 과 충돌하는 결정
 4. 보안: 데이터 범위 조건이 빠졌을 수 있는 쿼리, 개인정보 노출 경로(응답·로그·엑셀·오류), 다운로드 사유, 인증 통제
 5. 데이터·운영: 기준 DDL 반영, 기존 데이터 호환(코드값·NOT NULL 추가), 새 설정·환경변수를 모든 환경 설정에 반영했는지, 자격증명
 6. 규모·분리: MR 이 너무 크거나 관계없는 변경이 섞였는지
출력: 심각도(차단/중간/참고) | 파일:줄 | 문제 | 영향 | 제안. 마지막에 "머지 판단에 필요한 질문" 최대 3개.
```

승격 MR(`develop→staging`, `staging→main`)이면 코드 리뷰 대신 다음을 정리한다.
- 포함된 MR 목록: `git log --merges --first-parent origin/<목적지>..origin/<소스>`
- 검증 안 된 항목
- DDL·설정 변경 목록과 적용 순서(DB 먼저인지, BE 먼저인지)
- 롤백 기준점(태그)

## 4. 검증과 보고

1. 에이전트 지적에 인용된 줄을 직접 열어 확인하고 오탐을 버린다.
2. 사용자에게 보고한다.

```markdown
## MR <번호> 리뷰 — <제목>
- 경로: <소스> → <목적지> (규칙 적합 ✅/❌) · 셀프 리뷰 첨부 ✅/❌
- pre_mr_check 재실행: FAIL n / WARN n (개발자 보고와 일치 ✅/❌)
- 판정 제안: 머지 가능 | 수정 후 머지 | 보류 — 근거 한 줄

| 심각도 | 위치 | 문제 | 제안 |
|:--|:--|:--|:--|

리드 확인 필요(보호 영역·ADR): …
작성자에게 물을 것: …
```

3. 사용자가 원하면 MR 코멘트 초안을 만든다. **게시 전에 본문을 보여 주고 승인받는다.**
   - 전체 코멘트: `glab mr note create <번호> -m "<내용>"` / `gh pr comment <번호> --body "<내용>"`
   - 승인·머지는 사용자가 직접 지시할 때만 한다: `glab mr approve|merge <번호>` / `gh pr review --approve`, `gh pr merge`. 승격 MR 은 merge commit 으로 하고 squash 하지 않는다(이력 추적).

## 5. 정리

```bash
git -C <저장소> worktree remove "<루트>/.worktrees/review--<저장소>-mr<번호>"
```

같은 지적이 반복되면 해당 스킬, `review-rules.json` 의 `rules`, ADR 체크리스트에 반영하자고 제안한다.
