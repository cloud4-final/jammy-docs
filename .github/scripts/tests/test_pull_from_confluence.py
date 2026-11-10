import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pull_from_confluence as pfc  # noqa: E402


def test_mask_private_ips():
    raw = "A DB는 10.11.0.130:5432, 대역은 10.10.0.0/24, DNS는 1.1.1.1, Tailscale은 100.64.0.0/10"
    masked = pfc.mask_private_ips(raw)
    assert "10.11.x.130:5432" in masked
    assert "10.10.x.x/24" in masked
    assert "1.1.1.1" in masked
    assert "100.64.0.0/10" in masked
    assert "10.11.0.130" not in masked


def test_is_bot_version_message():
    assert pfc.is_bot_version_message("jammy-docs AI sync (C-NET-001)") is True
    assert pfc.is_bot_version_message("hybrid-docs AI sync") is True
    assert pfc.is_bot_version_message("네트워크 허용 표 수정") is False


def test_parse_and_apply_reverse_patches_with_guard(tmp_path):
    cfile = tmp_path / "contracts.md"
    cfile.write_text(
        "<!-- confluence-page-id: 17367041 -->\n"
        "# 공통 기준 · 계약\n"
        "### C-NET-001 · 대역\n"
        "- rule: `10.10.x.x/24` 필수\n"
        "- scope: jammy-5th\n"
        "- violation: 다른 대역\n"
        "- status: active\n"
        "- source: Confluence 13467672\n",
        encoding="utf-8",
    )

    raw_llm = """<summary>Confluence 13467672 수정분 반영</summary>
<patch>
<file>contracts.md</file>
<target>- rule: `10.10.x.x/24` 필수</target>
<new>- rule: `10.10.0.130` 및 `10.10.x.x/24` 필수</new>
</patch>"""
    summary, patches = pfc.parse_reverse_patches(raw_llm)
    assert "13467672" in summary
    # parse_reverse_patches masks raw IPs automatically
    assert "10.10.x.130" in patches[0][2]

    applied = pfc.apply_and_validate_patches(tmp_path, patches)
    assert applied == 1
    assert "10.10.x.130" in cfile.read_text(encoding="utf-8")


def test_extract_halt_reason_and_mass_deletion_guard():
    halt_raw = "<halt>Confluence 본문의 네트워크 대역과 contracts.md C-NET-001이 정면충돌하여 사람 확인 필요</halt>"
    assert pfc.ap.extract_halt_reason(halt_raw) is not None
    assert "정면충돌" in pfc.ap.extract_halt_reason(halt_raw)
    assert pfc.ap.extract_halt_reason("<summary>정상</summary>") is None

    before = "A" * 500
    after_half = "A" * 200
    err = pfc.ap.check_mass_deletion(before, after_half)
    assert err is not None
    assert "대량 삭제 감지" in err
    assert pfc.ap.check_mass_deletion(before, "A" * 450) is None


def test_git_block_deletion_guard():
    before = (
        "<!-- confluence-page-id: 17367041 -->\n"
        "### C-NET-001 · 대역\n"
        "- rule: r1 | scope: s1 | violation: v1 | status: active | source: src1\n"
        "### C-NET-002 · 포트\n"
        "- rule: r2 | scope: s2 | violation: v2 | status: active | source: src2\n"
    )
    after_deleted_block = (
        "<!-- confluence-page-id: 17367041 -->\n"
        "### C-NET-001 · 대역\n"
        "- rule: r1 | scope: s1 | violation: v1 | status: active | source: src1\n"
    )
    errors = pfc.check_docs.compare_text_deletion("contracts.md", before, after_deleted_block)
    assert any("C-NET-002" in e and "블록 무단 삭제 감지" in e for e in errors)
