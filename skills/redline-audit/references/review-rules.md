# review-rules.json — 프로젝트 설정

`redline_audit.py`(redline-audit)와 `pre_mr_check.py`(dev-review)가 함께 읽는다. 위치는 프로젝트 루트의 `.claude/review-rules.json`이다. 스크립트가 검사 경로에서 위로 올라가며 찾는다. 다른 위치에 두려면 `--config`로 넘긴다. 파일이 없으면 아래 기본값으로 돈다.

적은 키만 기본값을 덮어쓴다. 객체는 키 단위로 합치고, 목록은 통째로 바꾼다. 정규식은 Python `re` 문법이고, JSON 안에서는 `\`를 `\\`로 쓴다.

## 키

| 키 | 기본값 | 뜻 |
|:--|:--|:--|
| `base` | 없음 → `origin/develop`·`origin/main` 중 있는 것 | pre_mr_check 비교 기준 |
| `branch.env` | `develop, staging, main, master` | 여기서 작업하면 FAIL |
| `branch.pattern` | `^(feature\|hotfix)/[a-z0-9]+-[a-z0-9-]+$` | 브랜치 이름. 어기면 WARN, `""`면 끔 |
| `branch.commit_pattern` | `^\[(feat\|fix\|…)\]\[[^\]]+\] \S` | 커밋 제목. 어기면 WARN, `""`면 끔 |
| `backend.layers` | `[[infra, /([\w-]+-)?(infra\|infrastructure)/], [api, …(api\|web)/], [batch, …], [core, …(core\|application)/], [domain, …domain/]]` | 파일 경로로 층을 정한다. 위에서부터 처음 맞는 층. 멀티모듈이면 모듈 폴더(`/shop-core/`)를 적는다 |
| `backend.infra_ref` | `\b[a-z]\w*(\.[a-z]\w*)*\.(infra\|infrastructure)\.` | core·domain 줄에서 이 패턴이 보이면 RL1(import·전체 이름 참조 모두) |
| `backend.infra_module` | `project\(":[\w-]*infra[\w-]*"\)` | core·domain 빌드 파일의 infra 의존 |
| `backend.domain_model_dir` | `/domain/model/` | RL2 판정용 도메인 모델 위치. Entity 는 infra 층의 `@Entity` 로 찾는다 |
| `backend.rl3_allow` | `[]` | RL3 예외 경로 정규식. 예: OIDC 클라이언트 설정처럼 웹 계층에 붙어야 하는 곳 |
| `backend.forbidden_tables` | `""`(끔) | 어디서든 나오면 RL4 FAIL. 레거시·외부 시스템 권한 테이블 |
| `backend.foreign_tables` + `own_tables` | `""`(끔) | infra 에서 두 패턴이 5줄 안에 함께 나오면 RL4 WARN(JOIN 의심). `external_dir`(기본 `/infra/external/`)은 뺀다 |
| `frontend.external_style` | `false` | `true`면 `.vue` 안 `<style>` 본문·script 의 스타일 import 를 FE-RL1 로 |
| `frontend.class_case` | `null`(끔) | `"snake"` 또는 `"kebab"`. 템플릿·SCSS 클래스명 FE-RL2 |
| `frontend.third_party_class` | `^(ag-\|v-\|router-\|el-\|q-\|…)` | 클래스명 검사에서 뺄 접두사 |
| `frontend.eventbus` | `true` | EventBus·mitt·`$on` FAIL, 전역 `dispatchEvent` WARN |
| `frontend.server_data_imports` | `[]`(끔) | 스토어가 이 경로를 import 하면 FE-RL3 WARN. 예 `["@/api/"]` |
| `frontend.common_components` | `null`(끔) | 이 경로의 컴포넌트가 스토어를 import 하면 WARN. 예 `"/components/common/"` |
| `frontend.global_stores` | `[]` | 위 검사에서 뺄 전역 UI 스토어 이름. 예 `["ui"]` |
| `rules` | `[]` | 프로젝트 규칙. 아래 |
| `pii_fields` | `[]` | 로그 호출에 이 필드명이 보이면 WARN(pre_mr_check) |
| `audit_annotation` | `null` | `{"name": "@PiiAudit", "mapping": "(down\|excel\|detail)"}`: 매핑 경로가 패턴에 맞는데 앞뒤 4줄 안에 어노테이션이 없으면 WARN |
| `naming_cmd` | `null` | 명명 검사기. 파일 경로를 인자로 받고 `ERROR\|WARN 경로:줄 …` 을 출력하는 명령. 상대 경로는 프로젝트 루트(`.claude/` 의 부모) 기준 |
| `build` / `test` | 자동 | 명령 목록의 목록. 없으면 `gradlew build -x test`·`mvn package`·`npm run build`(있는 것), `--test`면 `gradlew test`·`mvn test`·`npm test` |

## rules — 프로젝트 규칙

정규식 한 줄로 판정할 수 있는 규칙을 더한다. 주석을 뺀 줄에 적용한다.

```json
{ "id": "SEC-CTX", "why": "SecurityContextHolder 직접 사용 — CurrentUserPort 로",
  "pattern": "SecurityContextHolder", "files": "/src/main/.*\\.java$",
  "exclude": ["/common/security/"], "sev": "FAIL" }
```

- `files`·`exclude`는 정규화한 절대 경로(`/` 구분)에 `search`로 맞춘다.
- `sev`는 `FAIL`(기본)이나 `WARN`이다. 의도한 경우가 흔하면 `WARN`으로 둔다.
- 같은 지적이 리뷰에서 두 번 나오면 여기 규칙으로 올린다.

## 예 — 멀티모듈 Spring + Vue

```json
{
  "base": "origin/develop",
  "backend": {
    "layers": [["infra", "/shop-infra/"], ["api", "/shop-api/"], ["batch", "/shop-batch/"],
               ["core", "/shop-core/"], ["domain", "/shop-domain/"]],
    "infra_ref": "com\\.acme\\.shop\\.infra\\.",
    "infra_module": "project\\(\":shop-infra\"\\)",
    "rl3_allow": ["/api/common/security/oidc/"],
    "forbidden_tables": "\\bLEGACY_\\w*(ROLE|AUTH)\\w*\\b"
  },
  "frontend": {
    "external_style": true,
    "class_case": "snake",
    "server_data_imports": ["@/api/"],
    "common_components": "/components/common/",
    "global_stores": ["ui"]
  },
  "rules": [
    { "id": "API-PATH", "why": "API 경로는 /api/v1/ 로 시작",
      "pattern": "@RequestMapping\\(\\s*\"/(?!api/v1/)", "files": "/controller/.*\\.java$" }
  ],
  "pii_fields": ["ssn", "phoneNo", "accountNo"],
  "audit_annotation": { "name": "@PiiAudit", "mapping": "(down|excel|detail)" },
  "build": [["./gradlew", "clean", "bootJar", "-q"]],
  "test": [["./gradlew", "test", "-q"]]
}
```
