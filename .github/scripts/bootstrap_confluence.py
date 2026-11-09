"""1회용: Confluence에 '0. 공통 기준' 부모 페이지와 자식 2개를 만든다.

편집 제한은 시도만 한다. Confluence Free plan은 페이지 제한을 지원하지 않아 403이 나면 경고만 한다.

사용: ATLASSIAN_EMAIL, ATLASSIAN_TOKEN 환경 변수 설정 후
  python bootstrap_confluence.py           # dry-run
  python bootstrap_confluence.py --apply   # 생성
  python bootstrap_confluence.py --apply --parent <id>   # 부모가 이미 있을 때
"""
import base64
import json
import os
import sys
import urllib.request

DOMAIN = "teamjammyjammy.atlassian.net"
SPACE_ID = "294916"
HOMEPAGE_ID = "295028"
PARENT_TITLE = "0. 공통 기준"
CHILDREN = [
    ("contracts.md", "공통 기준 · 파트 간 계약"),
    ("decisions.md", "공통 기준 · 결정 기록"),
    ("architecture.md", "공통 기준 · 아키텍처"),
    ("mvp-roles.md", "공통 기준 · MVP·역할"),
]
PARENT_BODY = (
    "<p>팀 공통 기준의 읽기용 사본이다. 원본은 "
    '<a href="https://github.com/cloud4-final/jammy-docs">GitHub cloud4-final/jammy-docs</a>이고, '
    "평일 09·13·18시에 자동 갱신된다. 이 폴더의 페이지는 직접 수정하지 않는다.</p>"
)


def plan_pages() -> list[tuple[str, str]]:
    return [("", PARENT_TITLE)] + CHILDREN


def request(method: str, path: str, body=None) -> dict:
    token = base64.b64encode(f"{os.environ['ATLASSIAN_EMAIL']}:{os.environ['ATLASSIAN_TOKEN']}".encode()).decode()
    req = urllib.request.Request(
        f"https://{DOMAIN}/wiki{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{method} {path}: {err.code} {err.read()[:200]!r}") from err


def create_page(parent_id: str, title: str, body: str) -> str:
    page = request("POST", "/api/v2/pages", {
        "spaceId": SPACE_ID, "status": "current", "title": title, "parentId": parent_id,
        "body": {"representation": "storage", "value": body},
    })
    return page["id"]


def restrict_edit_to_self(page_id: str, account_id: str) -> None:
    try:
        request("PUT", f"/rest/api/content/{page_id}/restriction", [
            {"operation": "update", "restrictions": {"user": [{"type": "known", "accountId": account_id}]}},
        ])
    except RuntimeError as err:
        print(f"경고: 편집 제한 실패({page_id}). 배너와 덮어쓰기로 대신한다. {err}")


def main(argv: list[str]) -> int:
    if "--apply" not in argv:
        for doc, title in plan_pages():
            print(f"[dry-run] {doc or '(부모)'} -> {title}")
        return 0
    account_id = request("GET", "/rest/api/user/current")["accountId"]
    if "--parent" in argv:
        parent_id = argv[argv.index("--parent") + 1]
    else:
        parent_id = create_page(HOMEPAGE_ID, PARENT_TITLE, PARENT_BODY)
        restrict_edit_to_self(parent_id, account_id)
    print(f"(부모): {parent_id}")
    for doc, title in CHILDREN:
        page_id = create_page(parent_id, title, "<p>GitHub에서 첫 동기화 대기 중</p>")
        restrict_edit_to_self(page_id, account_id)
        print(f"{doc}: {page_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
