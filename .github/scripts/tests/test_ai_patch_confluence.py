import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_patch_confluence as ap  # noqa: E402


def test_extract_confluence_ids():
    src = "Confluence 13467672, 16973840, jammy-collector README §3"
    assert ap.extract_confluence_ids(src) == ["13467672", "16973840"]


def test_extract_confluence_ids_skips_self_pages():
    src = "Confluence 17334273, 17367041, 4194323"
    assert ap.extract_confluence_ids(src) == ["4194323"]


def test_needs_sync_and_banner_idempotency():
    blocks = [{"id": "C-NET-002", "rule": "DB 대역 분리"}]
    sha = ap.compute_blocks_sha(blocks)
    body = "<p>원본 아키텍처 본문 10.10.1.130</p>"
    assert ap.needs_sync(body, sha) is True

    banner = ap.build_ai_banner("2026-11-06", ["C-NET-002"], "DB 대역 반영", sha)
    updated = ap.apply_banner(body, banner)
    assert ap.needs_sync(updated, sha) is False
    assert ap.needs_sync(updated, "different0000000") is True

    # 두 번 적용해도 배너는 1개만 유지
    banner2 = ap.build_ai_banner("2026-11-06", ["C-NET-002", "D-20261104-01"], "재반영", "newsha1234567890")
    updated2 = ap.apply_banner(updated, banner2)
    assert updated2.count("[jammy-docs AI 자동 최신화") == 1
    assert ap.needs_sync(updated2, "newsha1234567890") is False

    # Confluence 웹 에디터가 추가한 containerLevel parameter 및 local-id 속성이 있는 기존 배너도 중복 없이 제거
    editor_mutated = (
        '<ac:structured-macro ac:name="info" ac:schema-version="1" ac:local-id="ff58" ac:macro-id="0047">'
        '<ac:parameter ac:name="containerLevel">panel_c1</ac:parameter>'
        '<ac:rich-text-body><p local-id="44ef"><strong>[hybrid-docs AI 자동 최신화 · 2026-11-06]</strong> '
        '(<code>sync-sha:oldsha000</code>)</p></ac:rich-text-body></ac:structured-macro>'
        "<p>본문</p>"
    )
    updated3 = ap.apply_banner(editor_mutated, banner2)
    assert updated3.count("AI 자동 최신화") == 1
    assert "oldsha000" not in updated3


def test_check_ip_mask_leak():
    before = "<p>DB 주소는 10.11.1.130 이다.</p>"
    after_bad = "<p>DB 주소는 10.11.x.130 이다.</p>"
    after_good = "<p>DB 주소는 10.11.1.130 이며 포트는 5432다.</p>"
    assert ap.check_ip_mask_leak(before, after_bad) == ["10.11.x.130"]
    assert ap.check_ip_mask_leak(before, after_good) == []


def test_select_llm_provider_priority():
    assert ap.select_llm_provider({}) is None
    assert ap.select_llm_provider({"OPENAI_API_KEY": "sk-oai", "GEMINI_API_KEY": "gm"}) == ("openai", "sk-oai")
    assert ap.select_llm_provider(
        {"ANTHROPIC_API_KEY": "sk-ant", "OPENAI_API_KEY": "sk-oai"}
    ) == ("anthropic", "sk-ant")


def test_collect_page_blocks(tmp_path):
    doc = tmp_path / "contracts.md"
    doc.write_text(
        "# T\n### C-NET-001 · 대역\n- rule: r\n- scope: s\n- violation: v\n- status: active\n- source: Confluence 13467672\n",
        encoding="utf-8",
    )
    mapping = ap.collect_page_blocks([doc])
    assert "13467672" in mapping
    assert mapping["13467672"][0]["id"] == "C-NET-001"


def test_parse_and_apply_replacements():
    raw = """<summary>D-20261104-01에 따라 망 분리 상태를 적용 완료로 갱신</summary>
<replace>
<target>상태: 미적용</target>
<new>상태: 2026-11-05 적용 완료</new>
</replace>"""
    summary, reps = ap.parse_llm_response(raw)
    assert "D-20261104-01" in summary
    assert reps == [("상태: 미적용", "상태: 2026-11-05 적용 완료")]
    body, count = ap.apply_replacements("<p>상태: 미적용</p>", reps)
    assert count == 1
    assert body == "<p>상태: 2026-11-05 적용 완료</p>"
