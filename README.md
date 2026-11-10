<!-- confluence-page-id: 17334273 -->
# 0. 공통 기준

GitHub `cloud4-final/jammy-docs`는 3거점 하이브리드 프로젝트의 팀 공통 기준이다. 사람과 AI 모두 이 repo의 main을 기준으로 작업한다.

| 파일 | 내용 |
|---|---|
| [contracts.md](https://github.com/cloud4-final/jammy-docs/blob/main/contracts.md) | 파트 간 통일값: 대역, 주소, 포트, 이름, API, DB, 관측 label, AWS 태그, 최소 버전 (`C-`) |
| [decisions.md](https://github.com/cloud4-final/jammy-docs/blob/main/decisions.md) | 팀이 승인한 결정 (`D-`) |
| [architecture.md](https://github.com/cloud4-final/jammy-docs/blob/main/architecture.md) | 전체 아키텍처 경계: 토폴로지, 트래픽 흐름, 데이터·복제·백업, 배포·관측·AI (`A-`) |
| [mvp-roles.md](https://github.com/cloud4-final/jammy-docs/blob/main/mvp-roles.md) | MVP 필수·제외 범위와 파트별 담당 역할(Owner)·인계 경계 (`M-`) |

## 바꾸는 방법

1. 팀에 먼저 제안한다(회의, 채팅, PR 코멘트).
2. 이 repo에 PR을 올린다. 작은 변경은 GitHub 웹에서 연필 아이콘으로 고쳐도 된다. 자기 AI에게 "jammy-docs에 반영 PR 올려줘"라고 시켜도 된다.
3. 팀원 1명이 승인하면 merge된다. 승인이 곧 합의 기록이다.
4. 코드 PR 본문에 이 PR 링크를 적는다. 링크한 jammy-docs PR이 아직 merge되지 않았으면 `docs-link-check`가 경고로 알려준다.
5. 정기 양방향 동기화(`confluence-sync`, 평일 09·18시 및 수동 실행)가 Confluence 주요 문서의 최신 변경을 이 repo에 반영하고(사설 IP 마스킹 및 `docs-check` 검증 포함), Confluence `0. 공통 기준` 사본 및 연결된 기존 Confluence 문서도 양방향으로 최신화한다.

## 작성 규칙

네 파일은 리뷰 AI가 계속 읽는 문서다. AI가 내용을 놓치지 않도록 **파일당 160줄 이하**로 유지하며(160줄 초과 시 `compact_docs.py`가 중요 핵심 내용 위주로 자동 압축), 규칙 1개를 블록 1개로 쓰고 `docs-check`가 줄 수와 형식을 검사한다. (필드는 여러 줄 또는 `|` 구분 한 줄로 쓸 수 있다.)

- `contracts.md` 블록: `### C-<분류>-<번호> · 제목` (예: `C-NET-001`)
  - `status: active` 필드: `rule`(MUST / MUST NOT / SHOULD 문장), `scope`(repo·경로), `violation`(위반 예시), `source`
  - `status: open`(아직 정하지 않음) 필드: `rule`(정할 것), `owner`
- `decisions.md` 블록: `### D-<YYYYMMDD>-<번호> · 제목` (예: `D-20261104-01`)
  - 필드: `decision`, `implies`(이 결정 때문에 코드가 지켜야 할 것), `why`(한 줄), `scope`, `status`, `source`
- `architecture.md` 블록: `### A-<분류>-<번호> · 제목` (예: `A-TOPO-001`)
  - `status: active` 필드: `rule`, `scope`, `violation`, `source`
- `mvp-roles.md` 블록: `### M-<분류>-<번호> · 제목` (예: `M-MVP-001`, `M-ROLE-001`)
  - `status: active` 필드: `rule`, `owner`(담당자 GitHub ID), `scope`, `source`
- 바뀐 규칙이나 결정은 지우지 않는다. `status: superseded`와 `by: <새 ID>`를 붙이고 새 블록을 추가한다. AI는 Git 이력을 보지 않으므로 파일 안에 남긴다.
- ID는 한 번 쓰면 바꾸거나 재사용하지 않는다. 다른 블록을 가리킬 때는 ID로 쓴다.
- IP 주소는 앞 두 자리만 쓰고 뒤를 `x`로 가린다(`10.10.x.x`, 역할 끝자리는 `10.10.x.110`). 예외는 표준 값(`100.64.0.0/10`, `1.1.1.1`)이다. 정확한 값은 Confluence(내부)에 둔다.
- 비밀번호, 키, 계정 비밀값은 적지 않는다.
- 파트 내부의 세부 설계, 작업 기록, 일지는 여기에 두지 않는다.

## 읽는 곳

- GitHub: 이 repo의 main
- Confluence: `0. 공통 기준` (평일 09·18시 및 수동 실행 시 자동 갱신, 직접 수정 금지)
- AI: 평소에는 읽지 않는다. 다른 파트와 함께 쓰는 값을 다루거나 내용이 서로 맞지 않을 때만, 각 코드 repo의 `AGENTS.md`에 따라 아래 raw URL에서 관련 분류만 읽는다.
  - `https://raw.githubusercontent.com/cloud4-final/jammy-docs/main/contracts.md`
  - `https://raw.githubusercontent.com/cloud4-final/jammy-docs/main/decisions.md`
  - `https://raw.githubusercontent.com/cloud4-final/jammy-docs/main/architecture.md`
  - `https://raw.githubusercontent.com/cloud4-final/jammy-docs/main/mvp-roles.md`
- 리뷰 AI(CodeRabbit): 코드 PR마다 이 repo main의 4개 문서를 `code_guidelines`로 읽고 아래 `PR 리뷰 기준`으로 리뷰한다.

## PR 리뷰 기준

코드 PR 리뷰는 아래 5가지만 본다. 단순 성능 튜닝 제안이나 스타일·취향은 지적하지 않는다. 각 코드 repo의 `.coderabbit.yaml`이 이 목록을 그대로 쓰므로, 바꿀 때 함께 고친다.

1. 팀 약속·방향성 위반: 버전, 포트, 주소, 이름, API, DB, label, 태그, 아키텍처 경계, MVP 범위가 `contracts.md`·`decisions.md`·`architecture.md`·`mvp-roles.md`와 다른가
2. merge 후 장애: merge 후 배포, 실행, 마이그레이션, 설정이 실패하거나 서비스가 멈추는가
3. 코드 결함: 버그, 보안 문제, 예외 처리 누락, 테스트 누락이 있는가
4. 함께 쓸 때 문제: 다른 repo나 파트가 이 코드(API, 이미지, env, metric, 설정)를 쓸 때 깨지는가
5. 다른 파트 영향: 이 변경 때문에 다른 repo나 경로도 고쳐야 하는가 (`mvp-roles.md`의 `owner` 함께 안내)

판단 규칙:
- 근거는 규칙 ID(`C-`), 결정 ID(`D-`), 아키텍처 ID(`A-`), MVP·역할 ID(`M-`), 또는 파일과 줄로 인용한다.
- `status: active`만 위반으로 본다. `superseded` 규칙을 따르는 코드는 legacy로 지적하고 `by`의 ID를 안내한다. `open` 규칙에 의존하는 코드는 "결정 필요"로 표시한다.
- 기준과 다르지만 의도한 변경이면 코드를 되돌리지 않는다. 이 repo에 PR을 올려 merge하고 코드 PR 본문에 링크한다.
