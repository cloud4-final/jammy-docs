"""코드 PR 본문에 링크한 jammy-docs PR이 모두 merge됐는지 확인한다."""
import json
import os
import re
import subprocess
import sys
from typing import Callable, Optional

LINK = re.compile(r"https://github\.com/cloud4-final/jammy-docs/pull/(\d+)")


def linked_docs_prs(body: Optional[str]) -> list[int]:
    seen: list[int] = []
    for number in LINK.findall(body or ""):
        if int(number) not in seen:
            seen.append(int(number))
    return seen


def docs_link_check(body: Optional[str], merged: Callable[[int], bool]) -> list[str]:
    return [
        f"jammy-docs#{n}이 아직 merge되지 않았다. 기준 변경이 함께 필요한 경우 문서 PR merge 여부를 확인한다."
        for n in linked_docs_prs(body)
        if not merged(n)
    ]


def gh_merged(number: int) -> bool:
    out = subprocess.run(
        ["gh", "api", f"repos/cloud4-final/jammy-docs/pulls/{number}"],
        check=True, capture_output=True, text=True,
    ).stdout
    return bool(json.loads(out).get("merged"))


def main() -> int:
    body = os.environ.get("PR_BODY", "")
    links = linked_docs_prs(body)
    warnings = docs_link_check(body, gh_merged)
    for warning in warnings:
        print(f"::warning::{warning}")
    if not warnings:
        print(f"연결된 jammy-docs PR {len(links)}개, 모두 merge됨" if links else "연결된 jammy-docs PR 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
