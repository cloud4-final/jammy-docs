<!-- confluence-page-id: 18350082 -->
# 공통 기준 · 아키텍처

3거점 하이브리드 플랫폼의 구성 요소, 트래픽·데이터·관측 흐름, 장애 전환 경계를 정의한다. 사람과 리뷰 AI가 함께 읽는다. 변경은 jammy-docs PR에서 팀원 1명이 승인해야 한다.

## 리뷰어 사용법

- 규칙 1개가 블록 1개다. 위반을 찾으면 규칙 ID를 인용한다. 예: `A-TOPO-001 위반: data VM에 k3s agent 설치`.
- 블록의 `scope`에 해당하는 변경에만 그 규칙을 적용한다.
- `status: active`만 위반으로 판단한다. `status: superseded`는 적용하지 않고 `by`가 가리키는 블록을 따른다.
- 구체적인 포트·대역·주소·환경변수·태그 값은 `contracts.md`의 `C-` 블록을 함께 확인한다.

## 토폴로지와 인프라 구조

### A-TOPO-001 · 3거점 독립 실행과 가상화 계층
- rule: 온프레미스 3거점(`jammy-a`, `jammy-b`, `jammy-c`)은 Ubuntu 24.04 물리 호스트 위에 KVM/libvirt로 VM(`cp`, `app`, `data`)을 분리한다(MUST). OpenStack은 쓰지 않으며, 3거점을 단일 Kubernetes 클러스터로 묶지 않고 거점마다 독립 k3s 클러스터를 운영한다(MUST). `data` VM에는 PostgreSQL을 직접 설치하고 k3s 노드로 편입하지 않는다(MUST NOT).
- scope: 모든 repo (`jammy-5th`, `jammy-collector`, `jammy-observability`)
- violation: 3거점을 단일 K8s 클러스터로 구성하거나 `data` VM에 k3s 워크로드 배치
- status: active
- source: Confluence 4194323, 6225923, 6094850

### A-TOPO-002 · 거점 안 브리지 망 분리
- rule: 거점 호스트 안의 네트워크는 `cp`·`app` VM이 붙는 `br-vm`(10.10·10.20·10.30.x.x/24)과 `data` VM이 붙는 `br-data`(10.11·10.21·10.31.x.x/24)로 분리한다(MUST). VM 간 DB 접근은 반드시 호스트 방화벽(nftables)을 거쳐 통제되어야 한다(MUST).
- scope: jammy-5th(`infra/*`, `k8s/*`, `scripts/*`), jammy-collector, jammy-observability
- violation: `data` VM을 `br-vm`에 연결하거나 호스트 방화벽을 우회하는 경로 생성
- status: active
- source: Confluence 4194323, 14909445, 16973840

### A-TOPO-003 · Tailscale 사설 메시와 공유기 무개방
- rule: AWS 입구·관리·burst 서버, 3거점 호스트, 관측 허브(`jammy-obs`)는 Tailscale 사설 메시와 subnet route(`--snat-subnet-routes=false`)로 연결한다(MUST). 온프레미스 공유기에서 외부 포트포워딩을 열면 안 된다(MUST NOT).
- scope: jammy-5th(`infra/*`, `scripts/*`), 모든 네트워크·방화벽 설정
- violation: 거점 공유기에 외부 인바운드 포트포워딩 설정 또는 SNAT 활성화로 출발지 VM IP 은닉
- status: active
- source: Confluence 4194323, 13467672, 10846229

## 트래픽 흐름과 AWS 경계

### A-FLOW-001 · 공개 진입과 거점 분배
- rule: 외부 사용자 API 요청은 Route 53 → AWS 입구 EC2 2대(AZ a·c, HAProxy, `tag:edge`) → Tailscale 메시 → 정상 거점 `app` VM(80/443) 순서로만 전달한다(MUST). 세 거점이 모두 DOWN이면 AWS burst(준비된 경우) 또는 입구 자체 점검 페이지로 응답해야 한다(MUST).
- scope: jammy-5th(`infra/aws/*`, `k8s/*`), jammy-collector
- violation: 외부 요청을 거점 IP로 직접 연결하거나 NLB/ALB를 합의 없이 추가
- status: active
- source: Confluence 4194323, 12943383, 14286851

### A-FLOW-002 · 정적 파일 다운로드 분리
- rule: 대용량 파일 다운로드는 비공개 S3(원본, 버전 관리) + CloudFront(OAC) + 서명 링크(API Gateway `/download-link` → Lambda 또는 승인된 발급 경로)로 제공하며, 거점 호스트나 Tailscale 메시를 거치면 안 된다(MUST NOT).
- scope: jammy-5th(`infra/aws/*`), jammy-collector
- violation: 거점 `app` VM이나 입구 HAProxy가 대용량 파일을 직접 프록시·서빙
- status: active
- source: Confluence 4194323, 10813445

### A-FLOW-003 · 대체 수집과 속도 제한 재처리
- rule: 거점이 수집 요청을 처리할 수 없을 때는 로컬 버퍼 또는 AWS API Gateway(`/ingest`) → SQS(+DLQ)에 보관한다(MUST). 입구 2대 모두 동일한 대체 수집 경로를 가리켜야 하며, 거점은 인바운드 포트를 열지 않고 SQS에서 pull 방식으로 꺼내 `event_id` 멱등성을 유지하며 속도 제한(backfill) 재처리한다(MUST).
- scope: jammy-5th(`infra/aws/*`, `k8s/*`), jammy-collector
- violation: SQS가 거점으로 push하기 위해 거점 인바운드 포트를 개방하거나 `event_id` 중복 검증 없이 재적재
- status: active
- source: Confluence 4194323, 10813445, 10846229

### A-FLOW-004 · AWS 부분 전환(burst)
- rule: AWS burst(EC2 + 독립 k3s, `tag:burst`)는 평소 0대이며, 온프레미스 용량 부족 조건에서 EC2 기동 → 데이터·readiness 확인이 끝난 뒤에만 트래픽을 일부 유입한다(MUST). 인스턴스 기동만으로 트래픽을 보내면 안 된다(MUST NOT).
- scope: jammy-5th(`infra/aws/*`, `k8s/*`), jammy-collector
- violation: readiness 및 DB/데이터 연결 확인 전에 HAProxy 가중치로 burst에 요청 전달
- status: active
- source: Confluence 4194323, 10813445, 13565982

## 데이터·복제·백업 아키텍처

### A-DATA-001 · 단일 쓰기 원본과 비동기 읽기 사본
- rule: PostgreSQL 쓰기 원본(Primary)은 항상 전체에서 1곳(기본 `jammy-a`의 `10.11.x.130:5432`)만 둔다(MUST). `jammy-b`·`jammy-c`의 `data` VM은 비동기 streaming 읽기 사본(Replica)으로만 동작하며, 애플리케이션 쓰기(`DATABASE_URL`)는 원본으로만 보내야 한다(MUST).
- scope: jammy-collector, jammy-5th(`k8s/*`, DB 설정)
- violation: 다중 Primary 구성을 시도하거나 Replica에 쓰기 트랜잭션 연결
- status: active
- source: Confluence 4194323, 12943361, 16973840

### A-DATA-002 · 외부 백업 경로 분리
- rule: PostgreSQL 백업(pgBackRest)은 현재 쓰기 원본 거점에서 물리 인터넷 인터페이스(`lan0`)를 통해 AWS 백업 S3 버킷으로 직접 전송한다(MUST). 대용량 백업 트래픽이 Tailscale 메시(`tailscale0`)를 통과하면 안 된다(MUST NOT).
- scope: jammy-5th(`infra/*`, `scripts/*`), DB 백업 설정
- violation: S3 백업 경로를 Tailscale 터널 내부로 라우팅
- status: active
- source: Confluence 4194323, 10813468, 10846229

### A-DATA-003 · 수동 합의를 통한 원본 승격과 Fencing
- rule: 쓰기 원본 장애 시 네트워크 단절만으로 사망을 단정하지 않는다. 반드시 (1) 쓰기 중단, (2) 팀 승인, (3) 옛 원본 Fencing(5432 차단·격리 확인), (4) B 승격 및 C 재연결, (5) 앱 Secret(`DATABASE_URL`) 변경 순서로 진행하며, 무인 자동 승격(auto-failover)을 구현하면 안 된다(MUST NOT).
- scope: 모든 repo
- violation: 헬스체크 실패 시 스크립트나 오퍼레이터가 자동으로 Replica를 `pg_promote` 실행
- status: active
- source: Confluence 4194323, 12943361, 10813468, 10846229

## 배포·관측·AI 경계

### A-OPS-001 · CI/CD와 GitOps 배포 경로
- rule: 코드 변경은 GitHub Actions CI(단위 테스트·정적 분석·보안 검사)를 통과한 뒤 GHCR에 불변 태그(`sha-<commit>`) 이미지를 게시하고, 배포는 A 거점 검증 후 B·C 거점으로 확대한다(MUST). GitHub Actions의 AWS 접근은 OIDC 임시 자격 증명만 쓰고 장기 Access Key를 저장하면 안 된다(MUST NOT).
- scope: 모든 repo `.github/workflows/*`, `jammy-5th/k8s/*`, `jammy-5th/infra/aws/*`
- violation: CI에 `AWS_SECRET_ACCESS_KEY` 저장 또는 테스트 실패 상태에서 이미지 배포
- status: active
- source: Confluence 4194323, 3538951, 8126485

### A-OPS-002 · 거점 에이전트와 중앙 관측 허브
- rule: 각 거점 호스트와 VM의 지표·로그·trace는 거점 수집기(Alloy·Exporter)에서 수집하여 Tailscale 메시를 통해 관측 허브(`jammy-obs`, `tag:obs`)의 Prometheus·Loki·Tempo·Grafana로 모은다(MUST). 거점 단절 시에도 장애 원인을 구분할 수 있도록 외부 vantage 점검(관리 인스턴스 ↔ `jammy-obs`·거점 heartbeat)을 유지한다(MUST).
- scope: jammy-observability(`hub/*`, `site/*`, `alerts/*`), jammy-collector, jammy-5th
- violation: 관측 허브 주소를 IP로 하드코딩하거나 동일한 로그/지표를 여러 수집기로 중복 수집
- status: active
- source: Confluence 4194323, 8060964, jammy-observability README

### A-OPS-003 · 운영 데이터 파이프라인과 AI 보조 원칙
- rule: 운영 로그·지표 분석과 지연 예측·Pod 수 추천 모델은 업무 이벤트 처리(collector DB 트랜잭션)와 분리된 오프라인/별도 경로에서 실행한다(MUST). AI 추천 결과나 LLM 출력이 K8s HPA, Pod 수, 라우팅, DB 설정을 자동으로 변경하면 안 된다(MUST NOT).
- scope: 모든 repo
- violation: AI 모델 응답을 받아 `kubectl scale`이나 Terraform/Argo CD 설정을 무인 변경
- status: active
- source: Confluence 4194323, 4685838, 12910594
