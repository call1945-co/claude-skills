---
name: redline-audit
description: Use when asked to find architecture Red Line violations across a hexagonal (ports & adapters) Java/Spring backend or a Vue frontend — "레드라인 점검", "레드라인 벗어난 곳 찾아줘", "레드라인 위반 전수", "아키텍처 위반 찾아줘", "헥사고날 위반", "의존 방향 위반", "Red Line audit" — for a whole repo, a module or a branch diff. For checking only the changed lines before an MR, dev-review is enough. If the project has its own red-line audit skill, follow that one.
---

# Red Line 감사

결과물은 **확정 위반 목록**이다. 항목마다 Red Line 번호, 파일:줄, 근거, 고칠 방향, 담당을 적는다. 스크립트가 낸 후보는 하나씩 읽어 확정과 오탐으로 가른다. 파일은 고치지 않고, 사용자가 고치라고 할 때만 고친다.

dev-review 의 `pre_mr_check.py`는 MR 에서 바뀐 줄만 본다. 이 스킬은 저장소 전체를 보고, 정규식 한 줄로는 안 잡히는 것까지 찾는다. import 없이 전체 이름으로 참조한 것, DTO 안에 감싼 도메인 모델·Entity, 템플릿 클래스, 자식 컴포넌트의 props 변경, 스토어가 받는 서버 데이터가 그렇다.

## 기본 Red Line

| ID | 규칙 | 기본 |
|:--|:--|:--|
| BE-RL1 | core·domain 은 infra 에 의존하지 않는다(import·전체 이름 참조·빌드 의존). domain 은 프레임워크도 import 하지 않는다 | 켬 |
| BE-RL2 | Controller 는 Entity·도메인 모델을 반환하지 않는다. 응답 DTO 가 그것을 필드로 감싸도 위반이다 | 켬 |
| BE-RL3 | core·domain·api 는 외부 API 클라이언트·영속 기술(RestClient, JpaRepository, EntityManager, SDK)을 직접 쓰지 않는다 | 켬 |
| BE-RL4 | 금지 테이블(레거시·외부 권한 테이블)을 참조·JOIN 하지 않는다 | 설정 시 |
| FE-RL1 | 스타일은 `.vue` 밖 파일에 두고 `<style scoped src>` 로 잇는다 | 설정 시 |
| FE-RL2 | CSS 클래스명 표기(snake·kebab) | 설정 시 |
| FE-RL3 | EventBus 금지, 자식이 props 를 고치지 않는다. 설정하면 스토어의 서버 데이터, 공통 컴포넌트의 업무 스토어 의존도 본다 | 켬 |
| (rules) | 프로젝트가 더한 정규식 규칙 | 설정 시 |

프로젝트 값(층 경로, 패키지, 예외 경로, 금지 테이블, 프론트 규칙)은 `.claude/review-rules.json` 에 둔다. 키와 예시는 [references/review-rules.md](references/review-rules.md)에 있다. 설정이 없으면 기본값으로 돌리고, 그 결과에 오탐이 많으면 설정 파일을 만들자고 제안한다. 프로젝트 `CLAUDE.md` 에 Red Line 이 적혀 있으면 그것을 기준으로 설정을 맞춘다.

## 절차

1. **기준 맞추기**: 메인 체크아웃이 기준 브랜치가 아니면 원격 기준을 임시 worktree 로 꺼낸다.
   ```
   git -C <저장소> worktree add --detach <임시폴더>/audit origin/develop
   ```
   끝나면 `git worktree remove` 로 지운다.
2. **기계 검사**: `<스킬 폴더>` 는 스킬을 불러올 때 표시되는 Base directory 다.
   ```
   python -I <스킬 폴더>/scripts/redline_audit.py <백엔드 경로> <프론트 경로>
   python -I <스킬 폴더>/scripts/redline_audit.py <저장소 경로> --diff origin/develop   # 브랜치 변경분만
   ```
   첫 줄에 어떤 설정을 읽었는지 나온다. FAIL 이 있으면 종료 코드는 1 이다.
3. **후보 판정**: FAIL·WARN 마다 그 줄과 주변을 읽고 아래 판정표로 가른다.
4. **스크립트 밖 확인**: 아래 목록을 grep 으로 좁혀서 읽는다.
5. **보고**: 아래 형식으로 쓴다.

## 판정표

| RL | 확정 위반 | 오탐 (빼고 사유별로 센다) |
|:--|:--|:--|
| BE-RL1 | import, 전체 이름 참조, `Class.forName("...infra...")`, core·domain 빌드 파일의 infra 의존 | 주석·로그 문자열 안의 패키지 이름 |
| BE-RL2 | Controller 반환 타입에 도메인 모델·Entity, 응답 DTO 의 필드·record 구성요소가 도메인 모델·Entity | DTO 가 `static from(도메인)` 변환에만 import |
| BE-RL3 | core·api 의 HTTP 클라이언트·`EntityManager`·외부 SDK | `rl3_allow` 에 적은 예외 경로(이유가 ADR 에 있어야 한다) |
| BE-RL4 | 금지 테이블 JOIN, 권한 판정에 사용 | 외부 시스템 동기화 어댑터가 그 시스템 데이터를 읽기만 함(권한 판정에 안 씀) |
| FE-RL1 | `.vue` 안 `<style>` 본문, script 의 스타일 import | — |
| FE-RL2 | 규칙과 다른 표기의 클래스 | Vue `<Transition>` 클래스, 서드파티 클래스(스크립트가 대부분 거름) |
| FE-RL3 FAIL | `mitt`·`$on`, `props.x =`·`props.x.push(` | — |
| FE-RL3 WARN 스토어 | 목록·상세 같은 **서버 데이터를 state 에 담아 캐시** | 로그인·토큰·세션 같은 인증 상태, 결과를 state 에 두지 않고 저장 요청만 보내는 액션 |
| FE-RL3 WARN 공통 컴포넌트 | 업무 스토어에 묶임 | 전역 UI 스토어(토스트·확인창)만 씀 → `global_stores` 에 추가 |

## 스크립트 밖 확인

- BE-RL2: 응답 래퍼(`CommonResponse.ok(`, `ResponseEntity.ok(` 등) 안에 `Map`·`Object`·`List<?>` 로 도메인을 감싸 넘기는 곳. 래퍼 호출을 grep 해서 인자 타입을 본다.
- BE-RL3: core 서비스가 `ApplicationContext`·`getBean` 으로 구현체를 꺼내는 곳, Controller 가 Port 가 아닌 `*Client` 빈을 주입받는 곳.
- FE-RL3: 스토어 state 에 목록을 담는 확정 건은 그 스토어를 쓰는 화면 수도 적는다. 옮겨야 할 범위가 된다.

## 보고 형식

```
## Red Line 감사 — <대상> (<기준 커밋>)
| # | RL | 파일:줄 | 근거 | 고칠 방향 | 담당 |
|:--|:--|:--|:--|:--|:--|
| 1 | BE-RL2 | shop-api/.../OrderController.java:12 | ResponseEntity<Order> 반환 | OrderResponse record 로 | (경로로 판단) |
오탐으로 뺀 것 n건: <사유별 개수>
스크립트 밖 확인: <한 일 한 줄>
```

담당은 프로젝트 `CLAUDE.md` 의 R&R(영역별 담당 경로)로 정한다. R&R 이 없으면 칸을 비운다.

## 흔한 실수

- 스크립트 출력만 옮겨 적는다 → 오탐이 섞이고 판정 근거가 없다. 후보마다 줄을 읽는다.
- 파일을 다 읽으려다 일부만 보고 끝낸다 → 큰 저장소는 스크립트로 후보를 좁히고 판정표와 스크립트 밖 목록만 읽는다.
- WARN 을 모두 위반으로 센다 → 판정표의 오탐 조건을 먼저 본다.
- 같은 오탐이 반복된다 → `review-rules.json` 의 예외(`rl3_allow`, `global_stores`, `rules[].exclude`)에 넣자고 제안한다.
