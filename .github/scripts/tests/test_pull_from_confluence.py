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
