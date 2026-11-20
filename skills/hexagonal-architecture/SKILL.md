---
name: hexagonal-architecture
description: Use when creating or changing Java/Spring backend code in a hexagonal (ports & adapters) multi-module project — a new UseCase, Port, Adapter, Controller, Entity, DTO or a build.gradle(.kts) dependency — or when deciding where code belongs, how to name a port or use case, or whether a dependency breaks the layering. If the project has its own hexagonal-architecture skill, follow that one.
---

# 헥사고날 멀티모듈 백엔드

업무 코어가 DB·웹 프레임워크·메시지 브로커·외부 API 에 물들지 않도록 의존 방향을 지킨다. 아래 이름(`shop`, `Order`)은 예시다. 실제 이름은 0절에서 찾는다.

## 0. 프로젝트 값

처음 쓸 때 `CLAUDE.md`·`settings.gradle(.kts)`·기존 코드에서 찾는다. 없으면 기본값을 쓰고 `CLAUDE.md` 에 적어 두자고 제안한다.

| 항목 | 찾는 곳 | 예 |
|:--|:--|:--|
| 기본 패키지·모듈 | `settings.gradle.kts`, 소스 트리 | `com.acme.shop`, `shop-domain`·`shop-core`·`shop-infra`·`shop-api`·`shop-batch`·`shop-common` |
| 응답 래퍼·오류 코드 | common 모듈 | `CommonResponse<T>`, `ErrorCode`, `BusinessException` |
| API 경로 규칙 | 기존 Controller, ADR | `/api/{채널}/{자원}` |
| 스키마 기준 | DDL 파일·migration 폴더 | `docs/erd/schema.sql` |
| 명명 사전 | 사내 약어 사전·명명 스킬 | `Ord`, `Cust` 같은 표준 약어 |
| 보호 영역 | `CLAUDE.md` | 보안·인증·암호화·DB 설정은 리드 확인 후 수정 |

## 1. 모듈 의존

```
api   ──implementation──► core, common      (Driving Adapter: REST)
      ──runtimeOnly────► infra             (컴파일 참조 불가, 스캔 조립 전용)
batch ──implementation──► core, domain, common
      ──runtimeOnly────► infra
infra ──api────────────► core, domain, common   (Driven Adapter: JPA·S3·Redis·MQ·외부 API)
core  ──api────────────► domain, common         (Port + Service)
domain                     순수 객체·Enum·VO (의존 없음)
common                     응답 래퍼, 오류 코드, 업무 예외
```

- api·batch 는 infra 를 **`runtimeOnly`** 로만 받는다. 그러면 Controller·필터·배치 Job 이 Entity·Repository·Adapter 를 import 할 때 컴파일이 실패해서, Red Line 을 빌드가 막는다. 필요한 능력은 항상 `core.port` 로 받는다.
- 통합 테스트가 infra 를 직접 써야 하면 `testImplementation` 으로만 둔다. 단위 테스트는 infra 를 참조하지 않는다.
- **core·domain 의 빌드 파일에 infra 를 추가하면 Red Line 위반이다.**

## 2. Red Line

1. core·domain 은 infra 를 import·참조하지 않는다. domain 은 프레임워크(Spring·JPA·SDK)도 import 하지 않는다. Lombok 만 허용한다.
2. Controller 는 Entity·도메인 모델을 반환하지 않는다. 응답 DTO 를 래퍼에 담아 돌려준다. DTO 가 도메인 모델을 필드로 감싸도 위반이다.
3. 외부 API·영속 기술은 Controller·Service 에서 직접 부르지 않는다. Port → infra Adapter 를 거친다.
4. 레거시·외부 시스템의 권한 테이블과 JOIN 하지 않는다. 권한은 자체 RBAC 테이블로만 판정한다.

전수 점검은 `redline-audit`, MR 전 점검은 `dev-review` 스킬이 한다.

## 3. 패키지

| 모듈 | 패키지 | 내용 |
|:--|:--|:--|
| domain | `domain.model` | 도메인 모델. 상태 전이·검증은 도메인 메서드로 둔다(`order.cancel(userNo, rson)`) |
| domain | `domain.enums` | 상태·유형 열거형(`desc`, `fromCode`) |
| core | `core.port.in` | Inbound Port(UseCase) |
| core | `core.port.out` | Outbound Port. **모든 아웃바운드 포트는 이 패키지 한 곳에 둔다** |
| core | `core.security` | 기술 중립 보안 객체: 현재 사용자 주체, 데이터 범위 조건, 관리 기능 게이트, 마스킹 |
| core | `core.service` | UseCase 구현. `@Service @Transactional(readOnly = true)`, 쓰기 메서드만 `@Transactional`. 서비스 여럿이 쓰는 규칙 조각은 `@Component` |
| infra | `infra.persistence` | `*PersistenceAdapter`(`@Repository`, Load·Save Port 함께 구현), `entity`·`repository` |
| infra | `infra.persistence.config` | DataSource·벤더 설정 (보호 영역) |
| infra | `infra.external` | 외부 API 어댑터. 대행사별 하위 패키지 |
| infra | `infra.storage`·`crypto`·`cache`·`messaging`·`security` | 파일 저장, 암호화, 캐시, MQ, 토큰 어댑터 |
| api | `api.{자원}.controller`·`.dto` | Controller, 요청·응답 Record DTO(`from(domain)`, `toCommand()`) |
| api | `api.common.security`·`.exception` | 보안 설정·필터·현재 사용자 어댑터, 전역 예외 처리 |

## 4. 명명

- 도메인 이름은 프로젝트 명명 사전을 클래스·메서드·DTO 에도 똑같이 쓴다. 사전에 약어가 있으면 풀네임 클래스를 새로 만들지 않는다.
- Inbound Port 는 두 종류다. **기준은 "성공했을 때 DB 한 행이 바뀌는 것 말고 업무적으로 달라지는 것이 있는가"**다. 없으면 CRUD, 있으면 워크플로우다.

  | 종류 | UseCase 이름 | 메서드 | 예 |
  |:--|:--|:--|:--|
  | 마스터·관리성 CRUD | `{자원}UseCase` 하나에 묶음 | `get` 단건, `sel…List` 목록, `ins`, `upd`, `del` (사내 접두사가 있으면 그것) | `RoleUseCase.getRole/selRoleList/insRole` |
  | 업무 워크플로우 | `{동사}{자원}UseCase` | 업무 동사 | `PlaceOrderUseCase.placeOrder`, `ApproveOrderUseCase.approve` |

  워크플로우를 `updOrderStat` 처럼 CRUD 이름으로 부르지 않는다. 전이 검증·알림·이력이 붙은 동작의 업무 의미가 사라지고, 리뷰어가 부작용을 놓친다.
- Outbound Port 이름은 `{Load|Save|Delete}{자원}Port`(영속)나 `{자원}{기능}Port`(외부·기술)로 짓고, 메서드는 **`load`·`save`·`delete` 만** 쓴다. JPA `save` 가 insert 와 update 를 구분하지 않으므로, 포트에서 `ins`·`upd` 를 나누면 지킬 수 없는 약속이 된다.
- Adapter 는 `{자원}PersistenceAdapter`, `{벤더}{기능}Adapter`(`S3StorageAdapter`)로 짓는다. Controller 핸들러는 호출하는 UseCase 메서드와 같은 이름을 쓴다. DTO 는 `{자원}{행위}Request`·`Response` Record 로 짓는다.
- **새 Port 를 만들기 전에 `port.out` 에 같은 역할의 포트가 있는지 grep 한다.** 파일 저장, 암호화, 캐시, MQ 포트는 하나씩만 둔다.

## 5. 층별 규칙

### core
- 조회 실패는 `BusinessException(ErrorCode.X_NOT_FOUND)` 로 던진다. 오류 코드는 common 에 자원별 대역으로 둔다.
- **범위 조건이 없는 단건 조회 포트는 서버가 확정한 식별자로만 부른다.** 사용자가 경로·본문으로 보낸 식별자로 부르면 IDOR 이다. 사용자 요청 경로는 데이터 범위 조건을 받는 포트(`loadOrderInScope(cond, no)`)를 쓰고, 범위 밖이어도 404 로 응답해서 존재를 숨긴다.
- 관리 기능(마스터 변경·최종 승인·삭제·엑셀 다운로드 등) 권한은 게이트 하나(`AuthGuard.requireMgmtAuth(user)`)로 판정한다. 서비스마다 `scope == HQ` 같은 비교를 흩뿌리지 않는다.
- 주체·범위 조건 객체는 운영 코드에서 팩토리(`AuthPrincipal.from(user)`, `toDataScopeCond()`)로만 만든다. 생성자를 직접 부르면 범위 필드가 빠진 객체가 생긴다.
- 권한을 주는 변경(역할 마스터, 역할 할당)은 토큰이 아니라 DB 의 현재 할당·계정 상태로 다시 판정한다. 요청자 자신에게 걸린 할당은 바꿀 수 없게 한다. 회수된 관리자가 남은 토큰으로 권한을 되살리지 못하게 하려는 것이다.

### infra
- `port.out` 을 구현하고, Entity ↔ 도메인 변환은 어댑터(또는 `*Mapper`) 안에서 끝낸다. 개인정보 암·복호화도 이 경계에서 한다.
- 외부 시스템은 **`infra.external` 어댑터로만** 부른다.
- **대행사 이름·응답 코드는 infra 안에만 둔다.** core 의 포트·결과 코드는 업무 개념으로 짓고(`MobileAuthPort`, `MobileAuthRslt`), 대행사 코드는 어댑터가 중립 결과로 바꿔 넘긴다. 그래야 대행사를 바꿀 때 어댑터·코드 표·설정만 바뀐다.
- **외부 연동 구현은 설정으로 고른다.** api·batch 가 infra 빈을 모두 띄우므로, 생성자에서 키를 검사하는 클라이언트를 무조건 `@Component` 로 두면 그 연동을 안 쓰는 배치까지 기동에 실패한다.
  - 실제 구현은 `@ConditionalOnProperty(name = "app.{연동}.vendor", havingValue = "<실제>")` 로 둔다. 설정이 없을 때 쓸 기본 구현(`matchIfMissing = true`)을 함께 둔다. 포트를 요구하는 서비스가 있으니 빈을 비워 두지 않는다.
  - 기본 구현은 연동 성격에 따라 정한다. 인증·검증처럼 통과가 곧 우회가 되는 연동은 **부르면 실패**하게 한다. 발송처럼 계약 전 흐름 확인용이면 mock 으로 둔다.
  - 지연 생성(`spring.main.lazy-initialization`)으로 대신하지 않는다. 기동 시 점검(키 확인값, 코드 정합성)이 미뤄지거나 빠진다.
- Entity 는 자체 테이블만 매핑한다. 복합 PK 중 AUTO_INCREMENT 컬럼은 단일 `@Id` 로 매핑하고, 조회에는 테넌트 키를 함께 건다.

### api
- Controller 는 UseCase 만 주입받고 `Response.ok(XxxResponse.from(domain))` 로 돌려준다. 파일 응답만 `ResponseEntity<byte[]>` 를 허용한다.
- 현재 사용자는 `CurrentUserPort.requireUser()` 같은 포트로 받는다. `SecurityContextHolder` 를 Controller·Service 에서 직접 쓰지 않는다.
- 응답 래퍼 규격(`success, code, message, data`)은 바꾸지 않는다. 프론트 인터셉터가 이 규격에 의존한다.
- 예외는 전역 예외 처리기가 오류 코드로 바꾸므로 Controller 에서 try-catch 하지 않는다.
- 개인정보 조회·다운로드 핸들러에는 접속기록을 남긴다(`isms-compliance` 스킬).

## 6. 기준 템플릿

```java
// core.port.in
public interface PlaceOrderUseCase { Order placeOrder(Order order); }

// core.service
@Service
@Transactional(readOnly = true)
public class OrderService implements PlaceOrderUseCase, GetOrderUseCase {
    private final SaveOrderPort saveOrderPort;
    private final SrchOrderPort srchOrderPort;
    private final CurrentUserPort currentUserPort;
    // 생성자 주입

    @Override @Transactional
    public Order placeOrder(Order order) { order.validate(); return saveOrderPort.saveOrder(order); }

    @Override
    public Order getOrder(Long orderNo) {
        AuthPrincipal user = currentUserPort.requireUser();
        // 번호만으로 조회하면 남의 주문이 보인다
        return srchOrderPort.loadOrderInScope(user.toDataScopeCond(), orderNo)
            .orElseThrow(() -> new BusinessException(ErrorCode.ORDER_NOT_FOUND));
    }
}

// api.order.controller
@RestController
@RequestMapping("/api/admin/order")
public class OrderController {
    private final GetOrderUseCase getOrderUseCase;
    @GetMapping("/{orderNo}")
    public CommonResponse<OrderDtlResponse> getOrder(@PathVariable Long orderNo) {
        return CommonResponse.ok(OrderDtlResponse.from(getOrderUseCase.getOrder(orderNo)));
    }
}
```

## 7. 작업 전 체크리스트

- [ ] 바꾸려는 모듈의 빌드 의존이 1절 그림과 같은가
- [ ] 같은 역할의 Port·UseCase 가 이미 있는가 (`port/in`, `port/out` 을 먼저 grep)
- [ ] 클래스·메서드·DTO 필드가 프로젝트 명명 사전을 따르는가
- [ ] Controller 반환 타입이 `응답래퍼<XxxResponse>` 인가
- [ ] 사용자 요청 경로의 조회에 데이터 범위 조건이 걸렸는가
- [ ] 새 Entity 의 테이블이 스키마 기준 파일에 있는가
- [ ] 보호 영역을 건드리면 리드 확인을 받고 ADR 을 갱신했는가
