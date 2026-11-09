<!-- confluence-page-id: 18153491 -->
# 공통 기준 · MVP·역할

팀이 합의한 MVP 필수 범위(M1~M13), 명시적 제외 사항, 파트별 주 담당자(Owner)와 접점 경계를 정의한다. 사람과 리뷰 AI가 함께 읽는다. 변경은 jammy-docs PR에서 팀원 1명이 승인해야 한다.

## 리뷰어 사용법

- 항목 1개가 블록 1개다. 위반이나 담당자 확인이 필요하면 ID와 `owner`를 인용한다. 예: `M-ROLE-002에 따라 방화벽·ACL 변경은 jiwon28 검토 필요`.
- `scope`에 해당하는 코드·설정 변경이 다른 파트의 책임 경계를 침범하거나 MVP 제외 항목을 무단으로 추가하면 지적한다.
- `status: active`만 적용한다. `status: superseded`는 적용하지 않고 `by`가 가리키는 블록을 따른다.

## MVP 필수 범위와 제외 경계

### M-MVP-001 · 코어 인프라·네트워크·데이터 MVP (M1~M4)
- rule: M1(3거점 독립 KVM VM·k3s 실행 환경), M2(AWS HAProxy 입구 2대 + Route 53 + Tailscale 사설 연결, 외부의 거점 직접 접속 차단), M3(`event_id`·`region` 검증·멱등 수집 및 조회 API), M4(A 쓰기 원본 + B·C 비동기 사본 + S3 외부 백업 및 승인된 수동 승격)는 MVP 필수 범위다(MUST). 단, `02-4 MVP` 초안의 "거점 안 망 분리 제외"는 `D-20261104-01`에 따라 **거점 안 망 분리(`br-vm`/`br-data`) 적용**으로 대체되었다.
- owner: HYE0NWEST, jiwon28, Hongsh6414, YangJunMan, daji0713
- scope: 모든 repo
- status: active
- source: Confluence 3538951, 10846229, D-20261104-01

### M-MVP-002 · AWS 연계·대체 수집·파일 분리·burst MVP (M5~M7)
- rule: M5(거점 장애 시 로컬 버퍼 및 API Gateway `/ingest` → SQS+DLQ 보관, 거점의 속도 제한 pull 재처리), M6(비공개 S3 + CloudFront OAC + 서명 링크를 통한 다운로드 분리), M7(온프레미스 용량 부족 시 readiness 확인 후 AWS EC2+k3s 부분 전환 및 복귀)을 준수해야 한다(MUST).
- owner: Hongsh6414, YangJunMan, daji0713, jiwon28
- scope: jammy-5th(`infra/aws/*`, `k8s/*`), jammy-collector
- status: active
- source: Confluence 3538951, 10813445

### M-MVP-003 · CI/CD·관측·비용 통제 MVP (M8~M9)
- rule: M8(단위·정적·통합 검사 통과 시에만 이미지 등록 및 A 검증 후 B·C 배포, 거점별 지연·오류·자원·알림 관측, OIDC 임시 자격 증명), M9(시험 입력·버전·결과·근거 로그 기록 및 예산 $450 내 시간·요청·용량 상한과 종료 후 잔여 자원 정리)를 지켜야 한다(MUST).
- owner: YangJunMan, Hongsh6414
- scope: 모든 repo `.github/workflows/*`, `jammy-observability`, `jammy-5th/infra/aws/*`
- status: active
- source: Confluence 3538951, 10715170, 10813445

### M-MVP-004 · 운영 데이터 파이프라인·AI 추천 MVP (M10~M13)
- rule: M10(거점·서비스·시간·요청 ID 기반 운영 로그 검색·오류 집계), M11(로그·지표 정제·품질 검사·재처리·버전 데이터셋 자동화), M12(작은 CPU 모델 1개 시간순 평가·기준선 비교·배포/롤백), M13(조회 API 지연 위험 및 실측 용량 기반 Pod 수 후보 추천·비교)을 범위로 한다(MUST).
- owner: daji0713, YangJunMan
- scope: jammy-5th, jammy-observability, jammy-collector
- status: active
- source: Confluence 3538951, 13565982, 12779522, 12910594

### M-MVP-005 · MVP 명시적 제외 사항 (Out of Scope)
- rule: 다음 항목은 MVP에서 제외하며 팀 합의(jammy-docs PR) 없이 코드에 도입하면 안 된다(MUST NOT): (1) OpenStack, (2) 3거점 단일 통합 Kubernetes 클러스터, (3) DB 무인 자동 승격(auto-failover), (4) AI/LLM의 운영 자원·Pod 수·라우팅·DB 설정 자동 변경, (5) 참조 수집/조회 API 외의 불필요한 프런트엔드 UI나 도메인 기능 확장, (6) 전 거점 Full ELK/OpenSearch나 다중 GPU 분산 학습.
- owner: daji0713, Hongsh6414, HYE0NWEST, jiwon28, YangJunMan
- scope: 모든 repo
- status: active
- source: Confluence 3538951, 5374003, 13565982

## 파트별 담당 역할과 변경 경계

### M-ROLE-001 · AWS 입구·파일·대체 수집·burst·비용 (홍석현)
- rule: AWS VPC·서브넷·보안 그룹, Route 53, HAProxy 입구 EC2 2대, S3(파일·백업)·CloudFront·서명 링크, API Gateway·SQS 대체 수집, burst EC2+k3s 인프라, 관리 인스턴스, AWS 예산·태그는 `Hongsh6414`(서브: `HYE0NWEST`)가 담당한다. 다른 파트가 `jammy-5th/infra/aws/*`나 AWS 리소스 구성을 바꿀 때는 담당자 검토를 받아야 한다(MUST).
- owner: Hongsh6414
- scope: jammy-5th(`infra/aws/*`)
- status: active
- source: Confluence 5374003, 10813445

### M-ROLE-002 · 네트워크·Tailscale 메시·방화벽 (손지원)
- rule: 온프레미스 호스트 라우터(`netplan`, `br-vm`, `br-data`), 호스트 방화벽(`nftables`), Tailscale subnet route·ACL·태그(`tag:site`, `tag:edge`, `tag:mgmt`, `tag:obs`, `tag:db`, `tag:burst`), AWS 보안 그룹·라우팅 요구 정의, DB 장애 시 네트워크 Fencing은 `jiwon28`(서브: `Hongsh6414`)이 담당한다. 새 포트·대역·경로 변경은 `jiwon28` 합의가 필수다(MUST).
- owner: jiwon28
- scope: jammy-5th(네트워크·방화벽·ACL 설정), 모든 repo의 포트·주소 변경
- status: active
- source: Confluence 5374003, 10846229, 13467672

### M-ROLE-003 · 온프레미스 호스트·KVM·스토리지·DB 구축 (김현서)
- rule: 3거점 물리 호스트(Ubuntu 24.04), KVM/libvirt VM(`cp`·`app`·`data`) 정의 및 Ansible 프로비저닝, LVM/데이터 볼륨(`pg-data`), PostgreSQL 설치·스트리밍 복제 구축·pgBackRest S3 백업 및 별도 환경 복원 검증은 `HYE0NWEST`(서브: `jiwon28`)가 담당한다. 구축 완료 후 K8s 연동 및 일상 DB 운영은 `daji0713`에게 인계한다.
- owner: HYE0NWEST
- scope: jammy-5th(`infra/onprem/*`, VM·스토리지·DB 구축 설정)
- status: active
- source: Confluence 5374003, 10813468, 16973840

### M-ROLE-004 · 수집·조회 API·공통 CI/CD·통합 관측·부하 시험 (양준혁)
- rule: 참조 이벤트 수집·조회 API(`jammy-collector`), 공통 GitHub Actions CI·GHCR 이미지 게시·Argo CD 배포 파이프라인, 거점 에이전트 및 관측 허브(`jammy-observability` Prometheus·Loki·Tempo·Grafana·Alertmanager), k6·iperf3 부하 및 장애 시험 자동화는 `YangJunMan`(서브: `daji0713`)이 담당한다.
- owner: YangJunMan
- scope: jammy-collector, jammy-observability, jammy-5th(`.github/workflows/*`, `loadtest/*`, `observability/*`)
- status: active
- source: Confluence 5374003, 10715170

### M-ROLE-005 · Kubernetes 운영·데이터 파이프라인·AI 모델·추천 (정다정)
- rule: 3거점 k3s 클러스터 운영(버전·라벨·taint·CNI·NetworkPolicy·자원 한도·HPA·배포 매니페스트), 구축된 DB의 운영 인수, 운영 로그·지표 정제·품질·재처리·버전 데이터셋 파이프라인, 지연 예측 모델 학습·평가·추론 API·Pod 수 추천 검증은 `daji0713`(서브: `YangJunMan`)이 담당한다.
- owner: daji0713
- scope: jammy-5th(`k8s/*`, `apps/*`, 데이터·AI 파이프라인)
- status: active
- source: Confluence 5374003, 13565982

### M-ROLE-006 · 파트 간 접점 인계 규칙
- rule: 두 파트가 맞물리는 경계는 다음 원칙을 지킨다(MUST).
  - **VM → K8s**: `HYE0NWEST`(VM/디스크) → `jiwon28`(통신/반환 경로) → `daji0713`(k3s/워크로드) 순서로 검증 후 인계한다.
  - **K8s ↔ CI/CD**: 클러스터 정책·리소스 한도·readiness 기준은 `daji0713`이 정하고, 이미지 빌드·Argo CD 배포 자동화는 `YangJunMan`이 맡는다.
  - **관측 ↔ 데이터·AI**: 수집기·저장소·대시보드는 `YangJunMan`이 구축하고(중복 수집기 설치 금지), 분석용 필드 추출·정제·모델링은 `daji0713`이 맡는다.
  - **burst**: 인스턴스·k3s 기동·비용 상한은 `Hongsh6414`, 배치·readiness 기준은 `daji0713`, 이미지 배포·부하 시험은 `YangJunMan`, ACL은 `jiwon28`이 맞춘다.
- owner: daji0713, Hongsh6414, HYE0NWEST, jiwon28, YangJunMan
- scope: 모든 repo
- status: active
- source: Confluence 5374003
