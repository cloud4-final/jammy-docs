import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402
import compact_docs  # noqa: E402


def make_verbose_contracts(num_blocks: int = 24) -> str:
    lines = [
        "<!-- confluence-page-id: 17498113 -->",
        "# 파트 간 약속 (contracts)",
        "",
        "코드 PR이 지켜야 하는 파트 간 통일값이다.",
        "",
        "## 네트워크 (NET)",
        "",
    ]
    for i in range(1, num_blocks + 1):
        lines.extend([
            f"### C-NET-{i:03d} · 규칙 {i}",
            f"- rule: 거점 {i} 대역은 `10.10.x.x/24`를 써야 하며",
            "  절대 다른 대역을 혼용하지 않는다.",
            f"- scope: jammy-5th/net-{i}",
            f"- violation: 10.10.x.x 외 대역 사용 ({i})",
            "- status: active",
            "- source: Confluence 14909445",
            "",
        ])
    lines.extend([
        "### C-NET-999 · 구버전 대역",
        "- rule: 예전에 쓰던 아주 긴 설명이 들어간 구버전 대역 규칙이며 이제는 더 이상 사용하지 않는다.",
        "- scope: jammy-5th/legacy",
        "- violation: 구버전 사용",
        "- status: superseded",
        "- by: C-NET-001",
        "- source: Confluence 14909445",
        "",
    ])
    return "\n".join(lines) + "\n"


def test_skips_when_under_max_lines(tmp_path):
    doc = make_verbose_contracts(num_blocks=5)
    p = tmp_path / "contracts.md"
    p.write_text(doc, encoding="utf-8")
    changed, before, after = compact_docs.compact_file_if_needed(p, [p], max_lines=160)
    assert changed is False
    assert before == after
    assert p.read_text(encoding="utf-8") == doc


def test_deterministic_compacts_verbose_doc_under_160_lines(tmp_path):
    doc = make_verbose_contracts(num_blocks=24)
    p = tmp_path / "contracts.md"
    p.write_text(doc, encoding="utf-8")
    assert len(doc.splitlines()) > 160

    changed, before, after = compact_docs.compact_file_if_needed(p, [p], max_lines=160, env={})
    assert changed is True
    assert before > 160
    assert after <= 160

    compacted = p.read_text(encoding="utf-8")
    assert check_docs.check_doc(p, require_page_id=True, max_lines=160) == []
    assert check_docs.check_blocks([p]) == []
    # Superseded block should be compacted to 2 lines
    assert "- rule: 예전에 쓰던 아주 긴 설명이 들어간 구버전 대역 규칙이며 이제는 더 이상 사용하지 않는다. | status: superseded | by: C-NET-001" in compacted


def test_ai_fallback_used_when_deterministic_still_exceeds_limit(tmp_path, monkeypatch):
    # 55 blocks -> deterministic is ~172 lines (> 160)
    doc = make_verbose_contracts(num_blocks=55)
    p = tmp_path / "contracts.md"
    p.write_text(doc, encoding="utf-8")

    det = compact_docs.deterministic_compact(doc)
    assert len(det.splitlines()) > 160

    # Mock LLM to return a valid 2-line-per-block version that fits under 160 lines
    def fake_llm(provider, api_key, prompt):
        out = ["<!-- confluence-page-id: 17498113 -->", "# 파트 간 약속 (contracts)", "## 네트워크 (NET)"]
        for i in range(1, 56):
            out.append(f"### C-NET-{i:03d} · 규칙 {i}")
            out.append(
                f"- rule: `10.10.x.x/24` 필수 | scope: jammy-5th/net-{i} | "
                f"violation: 타 대역({i}) | status: active | source: Confluence 14909445"
            )
        out.append("### C-NET-999 · 구버전 대역")
        out.append("- rule: 구버전 | status: superseded | by: C-NET-001")
        return "\n".join(out) + "\n"

    monkeypatch.setattr(compact_docs, "call_llm_raw", fake_llm)
    changed, before, after = compact_docs.compact_file_if_needed(
        p, [p], max_lines=160, env={"ANTHROPIC_API_KEY": "sk-test"}
    )
    assert changed is True
    assert after <= 160
    assert check_docs.check_blocks([p]) == []


def test_guard_rejects_ai_output_missing_block_id(tmp_path, monkeypatch):
    doc = make_verbose_contracts(num_blocks=55)
    p = tmp_path / "contracts.md"
    p.write_text(doc, encoding="utf-8")

    # LLM drops C-NET-055
    def bad_llm(provider, api_key, prompt):
        out = ["<!-- confluence-page-id: 17498113 -->", "# 파트 간 약속 (contracts)"]
        for i in range(1, 55):
            out.append(f"### C-NET-{i:03d} · 규칙 {i}")
            out.append("- rule: r | scope: s | violation: v | status: active | source: src")
        return "\n".join(out) + "\n"

    monkeypatch.setattr(compact_docs, "call_llm_raw", bad_llm)
    changed, _, _ = compact_docs.compact_file_if_needed(
        p, [p], max_lines=160, env={"ANTHROPIC_API_KEY": "sk-test"}
    )
    assert changed is False
    assert p.read_text(encoding="utf-8") == doc


def test_single_line_fallback_without_llm_key(tmp_path):
    # 55 blocks -> 3-line deterministic is > 160 lines, but 2-line single_line fallback is ~116 lines (<= 160)
    doc = make_verbose_contracts(num_blocks=55)
    p = tmp_path / "contracts.md"
    p.write_text(doc, encoding="utf-8")

    changed, before, after = compact_docs.compact_file_if_needed(p, [p], max_lines=160, env={})
    assert changed is True
    assert before > 160
    assert after <= 160
    assert check_docs.check_blocks([p]) == []

