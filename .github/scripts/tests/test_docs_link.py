import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import docs_link  # noqa: E402

BODY = (
    "변경 설명\n"
    "https://github.com/cloud4-final/jammy-docs/pull/12 와 "
    "https://github.com/cloud4-final/jammy-docs/pull/15\n"
    "https://github.com/cloud4-final/jammy-5th/pull/3"
)


def test_linked_docs_prs_extracts_only_hybrid_docs():
    assert docs_link.linked_docs_prs(BODY) == [12, 15]


def test_linked_docs_prs_handles_none_body():
    assert docs_link.linked_docs_prs(None) == []


def test_docs_link_check_warns_on_unmerged(monkeypatch, capsys):
    warnings = docs_link.docs_link_check(BODY, merged=lambda n: n == 12)
    assert len(warnings) == 1 and "#15" in warnings[0]
    monkeypatch.setenv("PR_BODY", BODY)
    monkeypatch.setattr(docs_link, "gh_merged", lambda n: n == 12)
    assert docs_link.main() == 0
    assert "::warning::" in capsys.readouterr().out


def test_docs_link_check_passes_without_links():
    assert docs_link.docs_link_check("링크 없음", merged=lambda n: False) == []


def test_docs_link_check_dedupes():
    body = "https://github.com/cloud4-final/jammy-docs/pull/7 https://github.com/cloud4-final/jammy-docs/pull/7"
    calls = []
    docs_link.docs_link_check(body, merged=lambda n: calls.append(n) or True)
    assert calls == [7]
