<!-- confluence-page-id: 17399809 -->
# 공통 기준 · 결정 기록

팀원 1명 이상이 승인한 결정이다. 사람과 리뷰 AI가 함께 읽는다. 변경은 jammy-docs PR로만 한다.

## 리뷰어 사용법

- 결정 1개가 블록 1개다. 근거로 인용할 때는 결정 ID를 쓴다. 예: `D-20261103-03에 따라 입구 EC2는 교체해야 함`.
- `implies`는 그 결정 때문에 코드가 지켜야 할 것이다. 리뷰는 `implies`를 기준으로 한다. 값 자체는 `contracts.md`의 `C-` 규칙이 기준이다.
- `status: active`만 적용한다. `status: superseded`는 적용하지 않고 `by`가 가리키는 결정을 따른다.
- 같은 날짜 안에서는 번호가 클수록 나중 결정이다.

### D-20261109-02 · AWS DB 사본은 MVP 범위 아님
- decision: AWS에 DB 사본(복제본)을 상시로 두지 않는다. MVP 이후 여유가 있을 때만 시험용으로 백업 S3에서 pgBackRest로 복원해 띄우고, 시험이 끝나면 삭제한다.
- implies: MVP 기간에는 AWS → 거점 DB 복제 경로(5432)와 ACL을 만들지 않는다. D-20261103-02의 "2순위 AWS 거점(추후)"은 이 시험용 거점을 뜻한다. 시험 전에는 C-DB-003(복구 검증 완료 표현 금지)을 그대로 지킨다. 시험을 하게 되면 복제 경로·ACL을 네트워크 담당(jiwon28)과 먼저 공유한다.
- why: 상시 사본은 EC2 비용과 복제 경로·ACL·fencing을 늘려 MVP 일정과 예산에 부담이 되고, 시험용 복원만으로도 3거점 전체 중단 시험과 백업 복원 검증을 할 수 있어서
- scope: AWS, 네트워크, DB
- status: active
- source: Confluence 19792000, 4194323

### D-20261109-01 · Data VM 백업 인증은 범위를 좁힌 IAM 사용자 키
- decision: 거점 Data VM의 pgBackRest는 IAM 사용자 `jammy-pgbackrest`의 액세스 키(`repo1-s3-key-type=shared`)로 백업 S3 버킷에 접근한다. 권한은 `pgbackrest/` 경로로만 제한한다. 백업 버킷 수명 주기는 현재 버전을 지우지 않고 이전 버전만 30일 뒤 정리한다.
- implies: pgBackRest는 `repo1-path=/pgbackrest`를 써야 한다. 액세스 키는 Terraform(`aws_iam_access_key`)으로 만들지 않는다(값이 tfstate에 남음). 키를 코드, tfstate, 문서, 메신저에 남기면 안 된다. 백업 보관 기간은 pgBackRest `expire`가 정하고, S3 수명 주기에 현재 버전 만료 규칙을 넣으면 안 된다(백업·WAL 세트가 깨짐). 이 키는 GitHub Actions용이 아니므로 A-OPS-001(GitHub Actions는 OIDC만)과 충돌하지 않는다.
- why: Data VM은 EC2가 아니라 인스턴스 역할을 쓸 수 없고, IAM Roles Anywhere는 사설 CA 운영과 별도 도구가 필요해 MVP 범위에 과해서
- scope: AWS, 온프레미스, DB
- status: active
- source: Confluence 20119725

### D-20261106-01 · Terraform CI는 lint와 plan 분리, plan은 PR 전용 OIDC 읽기 역할
- decision: lint(fmt·validate)는 `terraform.yml`, plan은 `terraform-plan.yml`로 나눈다. plan은 `pull_request`에서만 OIDC로 읽기 전용 역할 `jammy-gha-plan`을 빌려 실행하고, apply는 사람이 로컬에서 한다.
- implies: plan 역할에 쓰기·apply 권한을 주지 않는다. 신뢰 정책 `sub`는 immutable subject 형식(`repo:cloud4-final@<조직ID>/jammy-5th@<레포ID>:pull_request`)을 쓴다. 레포 이름을 바꾸면 신뢰 정책도 함께 바꿔야 한다(sub에 이름이 남음). 포크 PR은 건너뛰고 `pull_request_target`은 쓰지 않는다. 다른 OIDC 역할도 같은 sub 형식을 따른다.
- why: plan 역할을 PR 전용으로 좁게 유지하면서, main push에서도 도는 lint가 AWS 없이 계속 동작하게 하기 위해서
- scope: AWS, CI/CD
- status: active
- source: Confluence 19988482, 19792019

### D-20261105-01 · 팀 기준 문서는 jammy-docs
- decision: 파트 간 통일값은 `contracts.md`, 팀 결정은 이 파일에 둔다. GitHub `cloud4-final/jammy-docs` main이 기준이고, Confluence `0. 공통 기준`은 읽기용 사본이다.
- implies: 통일값이나 방향을 바꾸는 코드 PR은 jammy-docs PR 링크를 본문에 적어야 한다. 링크한 PR이 merge되기 전에는 `docs-link-check`가 실패한다.
- why: 팀원마다 AI가 서로 다른 설계를 기준으로 작업하는 문제를 막기 위해서
- scope: 전체
- status: active
- source: jammy-docs#1

### D-20261104-01 · 거점 안 망 분리
- decision: 세 거점 모두 data VM만 `br-data`와 DB 대역(10.11·10.21·10.31.x.x/24)으로 옮긴다. cp·app VM 주소는 그대로다.
- implies: C-NET-002, C-PATH-004. DB 주소는 `10.x1.x.130`만 쓴다. cp VM → DB 5432·22는 차단된다. 02-4 MVP의 "거점 안 망 분리 MVP 제외"는 이 결정으로 대체된다.
- why: 같은 거점 안의 DB 접근을 host 방화벽에서 통제하고, 장애 전환 때 fencing이 같은 거점 app의 쓰기까지 막게 하기 위해서
- scope: 온프레미스, 네트워크, DB, K8s
- status: active (2026-11-05 A·B·C 적용, 복제 재연결 완료)
- source: Confluence 14909445, 16973840

### D-20261103-01 · 입구 EC2 2대
- decision: 입구 EC2를 서브넷 a·c에 1대씩, 같은 Terraform 코드(`for_each`)로 둔다. 기존 입구 a의 EIP는 유지한다.
- implies: 입구 설정 변경은 두 대에 똑같이 적용되도록 코드 한 곳에서 한다. 입구별로 손으로 고치면 안 된다.
- why: 입구 1대 장애에도 서비스를 유지하기 위해서(MVP M2)
- scope: AWS, 네트워크
- status: active
- source: Confluence 14286851

### D-20261103-02 · HAProxy 목적지와 예비 순서
- decision: HAProxy에 거점 A·B·C의 app VM을 모두 미리 등록한다. 상태 확인은 `GET /`, 3초 간격, 3회 실패 DOWN, 2회 성공 UP이다. 세 곳이 모두 DOWN이면 2순위 AWS 거점(추후), 3순위 점검 페이지로 보낸다.
- implies: C-PATH-001, C-ADDR-001. app VM 주소가 바뀌면 HAProxy 목적지도 함께 바꾼다. cp VM은 목적지에 넣지 않는다. 상태 페이지(8404)는 서버 안에서만 연다.
- why: 거점이 준비될 때마다 입구를 교체하지 않기 위해서
- scope: AWS, 네트워크, K8s
- status: active
- source: Confluence 12943383

### D-20261103-03 · 입구 EC2는 고치지 않고 교체
- decision: user_data가 바뀌면 서버에 들어가 고치지 않고 Terraform이 새 서버로 교체한다(`user_data_replace_on_change = true`).
- implies: 입구 설정 변경은 코드 수정 → fmt → validate → plan → apply 순서로만 한다. SSM으로 들어가 수동 설치하면 안 된다. 교체 중 1–2분은 응답이 없다.
- why: 코드와 실제 서버를 항상 같게 유지하기 위해서
- scope: AWS
- status: active
- source: Confluence 13107219

### D-20261103-04 · Tailscale 가입 키
- decision: AWS 서버는 서버별 1회용 `tag:edge` 키를 Parameter Store SecureString(`/jammy/tailscale/edge-authkey-{a,c}`)에서 IAM 역할로 읽어 가입한다. burst처럼 대수가 자동으로 늘어나는 단계에서는 OAuth 자동 발급으로 바꾼다.
- implies: Tailscale 키를 코드, tfstate, 로그, 메신저에 남기면 안 된다. 키를 다루는 구간은 로그 출력(`set -x`)을 끈다. Terraform으로 키를 만들면 안 된다(값이 tfstate에 남음).
- why: 키가 새어 나가도 재사용되지 않게 하기 위해서
- scope: AWS, 네트워크
- status: active
- source: Confluence 12713986, 14286851

### D-20261103-05 · AWS 비용 감시
- decision: 비용 할당 태그 6개를 켜고, 비용 이상 탐지를 $5 기준으로 켠다. 리소스에 `Component` 태그를 붙인다. Component별 금액 배분은 아직 제안이다.
- implies: C-AWS-001, C-AWS-002. 입구 EC2는 `cpu_credits = "standard"`이고 안 쓸 때 중지한다.
- why: 총예산 $450 안에서 비용이 어디에 나가는지 보기 위해서
- scope: AWS 리소스를 만드는 모든 파트
- status: active
- source: Confluence 13139969
