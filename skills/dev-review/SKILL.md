---
name: dev-review
description: Use when a developer wants their own feature-branch changes reviewed before opening an MR/PR — "리뷰해줘", "MR 전에 점검", "PR 전에 점검", "셀프 리뷰", "올려도 돼?", "pre-mr check" — especially in a hexagonal Java/Spring or Vue project. Reviewing someone else's MR as lead is mr-review. If the project has its own pre-MR review skill, follow that one.
---

# 셀프 리뷰 (MR 전)

MR 의 첫 관문이다. 기계가 판정할 수 있는 규칙은 스크립트가 보고, 판단이 필요한 것은 새 맥락의 AI 가 보고, 최종 판단은 개발자가 한다.

## 0. 프로젝트 값

| 항목 | 찾는 곳 → 없을 때 |
|:--|:--|
| 기준 브랜치 | `.claude/review-rules.json` 의 `base`, `CLAUDE.md` 의 브랜치 규칙 → `origin/develop`, 없으면 `origin/main` |
| 규칙 문서 | 프로젝트 `CLAUDE.md`, 아키텍처·보안 스킬(`hexagonal-architecture`, `isms-compliance` 또는 프로젝트 전용) |
| 기계 규칙 | `.claude/review-rules.json`([redline-audit 의 설명](../redline-audit/references/review-rules.md)) → 기본값 |
| MR 본문 위치 | 프로젝트 흐름 스킬(`feature-flow` 등)의 MR 본문 형식 |

## 1. 대상 확정

- 저장소·worktree 경로와 기준 브랜치를 정한다. hotfix 를 하류로 반영하는 경우면 그 목적지가 기준이다.
- `git -C <경로> fetch origin` 을 하고, `git log --oneline <기준>..HEAD` 와 `git diff --stat <기준>...HEAD` 로 범위를 사용자에게 한 줄로 보여 준다.
- 커밋 안 된 변경이 있으면 커밋한 뒤 리뷰할지 그대로 둘지 묻는다. 스크립트는 커밋된 변경만 본다.

## 2. 기계 점검 — `scripts/pre_mr_check.py`

```bash
python -I <스킬 폴더>/scripts/pre_mr_check.py <저장소|worktree> [--base origin/develop] [--config <json>] [--test] [--no-build] [--no-fetch]
```

`<스킬 폴더>` 는 스킬을 불러올 때 표시되는 Base directory 다. Red Line 판정은 같은 플러그인의 `redline-audit/scripts/redline_audit.py` 를 불러 쓰므로 두 스킬이 함께 있어야 한다.

| 구분 | 검사 (추가·수정된 줄만. 기존 코드의 위반은 이 MR 책임이 아니다) |
|:--|:--|
| 흐름 | 환경 브랜치에서 작업하면 FAIL. 브랜치 이름·커밋 제목 규칙, 미커밋 변경, 기준 브랜치 최신 반영 여부는 WARN |
| 공통 | 충돌 표시, 자격증명 평문(소스·문서·설정 파일) |
| Red Line | BE-RL1~4, FE-RL1~3, 프로젝트 `rules` (redline-audit 와 같은 판정) |
| 선택 | 로그의 개인정보 필드(`pii_fields`), 개인정보 API 감사 어노테이션 누락(`audit_annotation`), 명명 검사기(`naming_cmd`) |
| 빌드 | `build`/`test` 설정, 없으면 gradle·maven·npm 자동. `--no-build` 로 생략할 수 있지만 MR 직전에는 생략하지 않는다 |

- **FAIL 이 있으면 AI 리뷰 전에 고친다.** 고칠 수 없는 FAIL(오탐)은 근거와 함께 보여 주고, `review-rules.json` 예외에 넣을지 묻는다.
- WARN 은 하나씩 "의도"인지 "수정"할지 판단해서 MR 본문에 남긴다.

## 3. AI 리뷰 — 작성 맥락과 분리

코드를 쓴 세션은 자기 가정을 믿는다. 리뷰는 Agent 도구(general-purpose)에 맡겨 새 맥락에서 하게 한다. 프롬프트는 아래를 채워서 쓴다.

```
<프로젝트>(<저장소 경로>)의 feature 브랜치 변경을 MR 전에 리뷰한다. 코드는 고치지 말 것.
범위: git -C <경로> diff <기준>...HEAD (파일 목록: <--stat 결과>)
먼저 읽을 것: <프로젝트 CLAUDE.md>, <아키텍처·보안·명명·영역 스킬의 SKILL.md 경로>.
기계 점검(pre_mr_check)은 통과했다. import 위치·스타일 위치 같은 규칙 위반은 찾지 말고 아래에 집중:
 1. 정확성: 분기 누락, null·빈 목록, 경계값, 트랜잭션 경계(readOnly·전파), 예외 → 오류 코드 매핑
 2. 도메인 규칙: 상태 전이는 도메인 메서드로만, 이력·알림 누락, 동시 처리(중복 요청·경합)
 3. 보안: 모든 목록·상세 쿼리에 테넌트·데이터 범위 조건, 개인정보는 어댑터 경계에서만 암·복호화,
    응답은 마스킹 값, 조회·다운로드 접속기록(다운로드는 사유), 로그·예외·toString 에 평문 개인정보 없음,
    사용자가 보낸 식별자로 범위 없는 단건 조회(IDOR)
 4. 계약: 응답 규격, API 경로·DTO 필드 변경을 FE/BE 가 함께 반영했는지, 다른 영역이 쓰는 포트·상태코드 영향
 5. 데이터: Entity 컬럼이 스키마(DDL)에 있는지, 스키마 변경이 기준 DDL 에 반영됐는지, 기존 데이터 호환
 6. FE: 스토어 경계, 서버 데이터는 쿼리 캐시로, 서버가 준 마스킹 값을 그대로 표시, 사용자 피드백(토스트·확인)
 7. 테스트: 새 규칙·분기에 테스트가 있는지, 없으면 필요한 케이스
각 지적은 확인한 코드 줄을 근거로. 추측이면 "가능성" 으로 표시.
출력: 심각도(높음/중간/낮음) | 파일:줄 | 문제 | 실패 시나리오(입력→잘못된 결과) | 제안. 마지막에 "남은 위험" 3줄 이내.
```

- 변경이 크면(파일 30개 초과 등) BE·FE 나 모듈 단위로 나눠 에이전트를 병렬로 돌린다. 최대 3개.
- 일반 버그 관점은 `/code-review`, 인증·세션·암호화·다운로드 비중이 크면 `/security-review` 를 함께 돌려도 된다.

## 4. 지적 검증과 처리

1. 에이전트 지적마다 **인용한 줄을 직접 열어** 사실인지 확인한다. 틀린 지적은 "오탐 — 근거"로 버린다.
2. 사실인 지적을 심각도 순으로 보여 주고 고칠지 묻는다. 높음은 고치는 것을 기본으로 제안한다.
3. 고친 뒤 `pre_mr_check.py` 를 다시 돌려 FAIL 0 을 확인한다.
4. **같은 종류의 지적이 반복되면** 정규식으로 잡히는 것은 `review-rules.json` 의 `rules` 에, 판단이 필요한 것은 해당 스킬에 추가하자고 제안한다.

## 5. 결과 — MR 본문용 요약

```markdown
## 확인 (dev-review, YYYY-MM-DD)
- pre_mr_check: FAIL 0 / WARN n — (각 WARN 의 판단: 의도 | 후속)
- 빌드: ✅ (테스트 ✅)
- AI 리뷰: 지적 n건 중 반영 a, 오탐 b, 보류 c(사유)
- 남은 위험: …
- 리뷰어가 특히 볼 곳: 파일:줄 — 이유
```

이 요약을 MR 본문에 붙인다. 푸시와 MR 생성은 사용자 승인 후에 한다.
