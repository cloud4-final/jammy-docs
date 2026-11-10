"""Confluence 주요 문서(2. MVP 폴더 및 source 연결 페이지)의 최신 변경을 읽어 jammy-docs를 역방향 최신화한다.

- Confluence 페이지의 수정 시각(version.when)이 마지막 동기화(또는 git commit 시각)보다 최신이고,
  봇 자동 동기화 커밋이 아닌 경우에만 대상 페이지로 선정한다.
- Confluence 내부의 실제 사설 IP(예: 10.11.0.130)는 Public 저장소 규칙에 맞춰 10.11.x.130으로 자동 마스킹한다.
- 패치 적용 후 check_docs.check_file 검증을 통과한 파일만 유지하고, 위반 시 즉시 원복(guard)한다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import ai_patch_confluence as ap
import check_docs

CORE_MFS_PAGES = (
    "3342364",   # 01. 기획서
    "3538951",   # 02. MVP
    "10813445",  # 02-1. MVP AWS
    "10715170",  # 02-2. MVP 수집·CI/CD·관측
    "10813468",  # 02-3. MVP 온프레미스
    "10846229",  # 02-4. MVP 네트워크
    "13565982",  # 02-5. MVP K8s·데이터·AI
    "4194323",   # 03. 아키텍처
    "4685838",   # 04. AI 적용 계획
    "5374003",   # 05. 역할 분담
)

ALLOWED_IPS = check_docs.ALLOWED_IPV4
RAW_IPV4_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
DOC_PATCH_RE = re.compile(
    r"<patch>\s*<file>(.*?)</file>\s*<target>(.*?)</target>\s*<new>(.*?)</new>\s*</patch>",
    re.S,
)


def mask_private_ips(text: str) -> str:
    """Public 저장소 노출 방지를 위해 허용된 표준 IP 외 모든 IPv4의 3번째 옥텟을 x로 마스킹한다."""
    def _replace(match: re.Match[str]) -> str:
        full = match.group(0)
        if full in ALLOWED_IPS:
            return full
        o1, o2, _o3, o4 = match.groups()
        if o4 == "0":
            return f"{o1}.{o2}.x.x"
        return f"{o1}.{o2}.x.{o4}"

    return RAW_IPV4_RE.sub(_replace, text)


def html_to_plain_text(storage_html: str) -> str:
    """Confluence Storage HTML에서 AI 배너와 태그를 제거하고 텍스트만 추출한다."""
    cleaned = ap.strip_existing_banners(storage_html)
    cleaned = re.sub(r"</(p|li|tr|h[1-6]|div)>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)
    return mask_private_ips(cleaned.strip())


def parse_iso_timestamp(ts: str) -> float:
    """ISO 8601 타임스탬프를 UTC epoch 초로 변환한다."""
    if not ts:
        return 0.0
    norm = ts.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(norm).astimezone(timezone.utc).timestamp()
    except ValueError:
        return 0.0


def is_bot_version_message(msg: str) -> bool:
    """봇이 생성한 Confluence 버전 메시지인지 판별한다."""
    lower = (msg or "").lower()
    return "ai sync" in lower or "자동 생성" in lower or "md2conf" in lower


def get_last_git_commit_epoch(root: Path) -> float:
    """DOCS_FILES의 마지막 git commit 시각(epoch)을 조회한다."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "log", "-1", "--format=%ct", "--", *ap.DOCS_FILES],
            text=True,
        ).strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0


def build_reverse_prompt(
    page_id: str,
    page_title: str,
    confluence_text: str,
    docs_content: dict[str, str],
) -> str:
    docs_dump = "\n\n".join(
        f"=== FILE: {name} ===\n{content}" for name, content in docs_content.items()
    )
    return f"""너는 3거점 하이브리드 클라우드 프로젝트의 팀 기준 문서(`cloud4-final/jammy-docs`) 동기화 에이전트다.
팀원이 Confluence 페이지(ID: {page_id}, 제목: `{page_title}`)를 수정했다.
아래 Confluence 본문과 현재 `jammy-docs`의 4개 기준 문서를 비교하여, **팀 공통 규칙(포트, 대역, 태그, 버전, 아키텍처 경계, MVP 범위, 담당 역할)이 변경되었거나 새로 확정된 경우에만** 최소한의 패치를 출력하라.

## 엄격한 규칙
1. **사설 IP 마스킹 필수**: `jammy-docs`는 Public 저장소이므로 모든 IP는 앞 두 자리만 남기고 `10.10.x.x` 또는 역할 끝자리 `10.11.x.130` 형식으로만 써야 한다(절대 3번째 옥텟에 숫자를 쓰지 마라).
2. **이력 보존(`superseded`)**: 기존 `status: active` 블록의 규칙이 바뀌었으면 삭제하지 말고 `status: superseded | by: <새 ID>`로 바꾼 뒤 새 블록을 추가하라.
3. **160줄 제한 및 블록 형식 준수**: 각 파일은 160줄 이하여야 하며 기존 블록 필드 형식을 정확히 유지해야 한다.
4. **불필요한 변경 금지**: 단순 문장 표현 차이나 파트 내부 세부 일지여서 공통 기준(`contracts.md`, `decisions.md`, `architecture.md`, `mvp-roles.md`)을 바꿀 필요가 없으면 `<patch>`를 하나도 출력하지 마라.
5. **사람 확인 게이트(`<halt>`)**: 만약 Confluence 본문 내용이 대규모로 바뀌었거나 삭제되었거나, 기존 `jammy-docs`의 active 계약·결정과 정면충돌하는데 어느 쪽이 최신 합의인지 판단할 수 없거나, 사람의 확인·의사결정이 반드시 필요한 변경이라면 절대 `<patch>`를 출력하지 말고 `<halt>사람 확인이 필요한 구체적 사유</halt>`만 출력하라.

## 출력 형식
<summary>반영 요약 한 줄 (변경 없으면 '공통 기준 변경 없음')</summary>
<patch>
<file>수정할 파일명 (contracts.md | decisions.md | architecture.md | mvp-roles.md)</file>
<target>파일 내 기존 문자열 그대로</target>
<new>대체할 새 문자열</new>
</patch>

## Confluence 최신 본문 (ID: {page_id}, 제목: {page_title})
{confluence_text[:12000]}

## 현재 jammy-docs 문서
{docs_dump}
"""


def parse_reverse_patches(raw: str) -> tuple[str, list[tuple[str, str, str]]]:
    summary_match = ap.SUMMARY_TAG_RE.search(raw)
    summary = summary_match.group(1).strip() if summary_match else "Confluence 최신 변경 동기화"
    patches: list[tuple[str, str, str]] = []
    for f_name, target, new in DOC_PATCH_RE.findall(raw):
        f_clean = f_name.strip()
        if f_clean in ap.DOCS_FILES and target.strip() and target != new:
            patches.append((f_clean, target, mask_private_ips(new)))
    return summary, patches


def apply_and_validate_patches(
    root: Path,
    patches: list[tuple[str, str, str]],
) -> int:
    """패치를 적용하고 check_docs 및 대량 삭제 검증을 통과하는지 확인한다. 실패 시 원복한다."""
    applied = 0
    backups: dict[str, str] = {}
    touched: set[str] = set()

    for fname, target, new in patches:
        fpath = root / fname
        if not fpath.exists():
            continue
        if fname not in backups:
            backups[fname] = fpath.read_text(encoding="utf-8")
        current = fpath.read_text(encoding="utf-8")
        t_clean = target.strip()
        n_clean = mask_private_ips(new.strip())
        if t_clean in current:
            fpath.write_text(current.replace(t_clean, n_clean, 1), encoding="utf-8")
            touched.add(fname)
            applied += 1

    existing_paths = [root / name for name in ap.DOCS_FILES if (root / name).exists()]
    block_errors = check_docs.check_blocks(existing_paths)
    for fname in touched:
        fpath = root / fname
        after_text = fpath.read_text(encoding="utf-8")
        del_errors = check_docs.compare_text_deletion(fname, backups[fname], after_text)
        errors = check_docs.check_doc(fpath, require_page_id=True, max_lines=160) + block_errors + del_errors
        if errors:
            print(f"[guard] {fname} 검증 실패({errors}) -> 변경 원복")
            fpath.write_text(backups[fname], encoding="utf-8")
            applied = 0
            if del_errors:
                ap.send_slack_alert("jammy-docs 역방향 패치 대량/블록 삭제 차단", "; ".join(del_errors))

    return applied


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Confluence 변경사항을 jammy-docs에 역방향 반영")
    parser.add_argument("--apply", action="store_true", help="실제 파일 패치 수행")
    parser.add_argument("--dry-run", action="store_true", help="변경 감지 여부만 확인")
    parser.add_argument("--max-pages", type=int, default=5, help="한 번에 처리할 최대 페이지 수")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    doc_paths = [root / name for name in ap.DOCS_FILES]
    page_blocks = ap.collect_page_blocks(doc_paths)
    candidate_ids = list(dict.fromkeys([*CORE_MFS_PAGES, *sorted(page_blocks.keys())]))

    creds = ap.resolve_confluence_creds()
    if not creds:
        print("[skip] Confluence 자격 증명이 없어 역방향 동기화를 건너뜁니다.")
        return 0

    client = ap.ConfluenceClient(ap.DOMAIN, creds[0], creds[1])
    baseline_epoch = get_last_git_commit_epoch(root)
    changed_pages: list[tuple[str, str, str]] = []

    for pid in candidate_ids:
        try:
            page = client.get_page(pid)
        except Exception as err:
            print(f"[warn] Confluence 페이지 조회 실패({pid}): {err}")
            continue

        ver_info = page.get("version", {})
        when_str = ver_info.get("when", "")
        ver_msg = ver_info.get("message", "")
        version_num = int(ver_info.get("number", 1) or 1)
        page_epoch = parse_iso_timestamp(when_str)

        if is_bot_version_message(ver_msg):
            continue
        if page_epoch <= baseline_epoch:
            continue

        title = page.get("title", pid)
        html_body = page.get("body", {}).get("storage", {}).get("value", "")
        current_plain = html_to_plain_text(html_body)

        if version_num > 1:
            try:
                prev_page = client.get_page(pid, version=version_num - 1)
                prev_html = prev_page.get("body", {}).get("storage", {}).get("value", "")
                prev_plain = html_to_plain_text(prev_html)
                del_err = ap.check_mass_deletion(prev_plain, current_plain)
                if del_err:
                    print(f"[guard] Confluence {pid} ({title}) 대량 삭제 감지 -> 동기화 즉시 중단: {del_err}")
                    ap.send_slack_alert(
                        "Confluence 본문 대량 삭제 가드 발동 (역방향 동기화 중단)",
                        del_err,
                        page_id=pid,
                        page_title=title,
                    )
                    return 1
            except Exception as err:
                print(f"[warn] 이전 버전({version_num - 1}) 비교 생략({pid}): {err}")

        changed_pages.append((pid, title, current_plain))

    if not changed_pages:
        print("[up-to-date] 마지막 커밋 이후 사람이 수정한 Confluence 페이지가 없습니다.")
        return 0

    if not args.apply:
        for pid, title, _ in changed_pages:
            print(f"[dry-run] 역방향 동기화 대상 감지: {pid} ({title})")
        return 0

    llm = ap.select_llm_provider()
    if not llm:
        print("[skip] LLM API 키가 없어 역방향 패치 생성을 건너뜁니다.")
        return 0

    provider, api_key = llm
    for pid, title, plain_text in changed_pages[: args.max_pages]:
        docs_content = {
            name: (root / name).read_text(encoding="utf-8")
            for name in ap.DOCS_FILES
            if (root / name).exists()
        }
        prompt = build_reverse_prompt(pid, title, plain_text, docs_content)
        try:
            raw = ap.call_llm_raw(provider, api_key, prompt)
        except Exception as err:
            print(f"[warn] 역방향 LLM 호출 실패({pid} {title}): {err}")
            continue

        halt_reason = ap.extract_halt_reason(raw)
        if halt_reason:
            print(f"[halt] {pid} ({title}) AI 판단으로 역방향 동기화 보류: {halt_reason}")
            ap.send_slack_alert(
                "AI 역방향 동기화 보류 (사람 확인 필요)",
                halt_reason,
                page_id=pid,
                page_title=title,
            )
            return 1

        summary, patches = parse_reverse_patches(raw)
        if not patches:
            print(f"[no-op] {pid} ({title}): {summary}")
            continue

        count = apply_and_validate_patches(root, patches)
        print(f"[pulled] {pid} ({title}) patches={count}: {summary}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
