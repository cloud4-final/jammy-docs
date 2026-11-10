"""jammy-docs의 C-/D-/A-/M- 블록과 연결된 기존 Confluence 문서를 AI로 최신화한다.

- 각 블록의 source 필드에 적힌 Confluence 페이지 ID를 추출한다 ('0. 공통 기준' 자체 페이지들은 제외).
- Confluence Storage Format은 HTML 주석을 제거하므로, Info 패널 안의 <code>sync-sha:<sha></code>로 변경 여부를 판정한다.
- LLM 프로바이더는 ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY 순서로 자동 감지한다.
- Confluence 내부 문서의 실제 사설 IP(예: 10.10.1.110)를 마스킹된 x(10.10.x.110)로 덮어쓰지 않도록 보호한다.
- 페이지 상단에 최근 AI 반영 내역(날짜, 근거 ID, 변경 요약) 배너를 남긴다.
"""
import argparse
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import check_docs

DOMAIN = os.environ.get("CONFLUENCE_DOMAIN", "teamjammyjammy.atlassian.net")
DOCS_FILES = ("contracts.md", "decisions.md", "architecture.md", "mvp-roles.md")
SELF_PAGE_IDS = {"17334273", "17367041", "17399809", "18350082", "18153491"}

CONFLUENCE_REF = re.compile(r"Confluence\s+([\d,\s]+)")
PAGE_ID_TOKEN = re.compile(r"\b(\d{5,12})\b")
SYNC_SHA_RE = re.compile(r"sync-sha:([A-Za-z0-9_-]+)")
# Confluence가 렌더링한 Info 매크로 중 "[jammy-docs AI 자동 최신화" (및 구 명칭, 에디터 parameter/local-id 포함) 블록과 레거시 주석 배너 모두 매칭
BANNER_MACRO_RE = re.compile(
    r"(?:<!--\s*(?:jammy-docs|hybrid-docs)-ai-banner-start\s*-->\s*)?"
    r"(?:<!--\s*(?:jammy-docs|hybrid-docs)-sync-sha:\s*[A-Za-z0-9_-]+\s*-->\s*)?"
    r"<ac:structured-macro\b[^>]*ac:name=\"info\"[^>]*>"
    r"(?:<ac:parameter\b[^>]*>.*?</ac:parameter>\s*)*"
    r"<ac:rich-text-body>\s*<p\b[^>]*>\s*<strong>\[(?:jammy-docs|hybrid-docs) AI 자동 최신화.*?</ac:structured-macro>"
    r"(?:\s*<!--\s*(?:jammy-docs|hybrid-docs)-ai-banner-end\s*-->)?",
    re.S,
)
MASKED_IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.x\.(?:x|\d{1,3})\b")
SUMMARY_TAG_RE = re.compile(r"<summary>(.*?)</summary>", re.S)
REPLACEMENTS_TAG_RE = re.compile(
    r"<replace>\s*<target>(.*?)</target>\s*<new>(.*?)</new>\s*</replace>",
    re.S,
)

KST = timezone(timedelta(hours=9))


def extract_confluence_ids(source_value: str) -> list[str]:
    """source 필드 문자열에서 Confluence 페이지 ID 목록을 추출한다."""
    ids: list[str] = []
    for match in CONFLUENCE_REF.finditer(source_value):
        for pid in PAGE_ID_TOKEN.findall(match.group(1)):
            if pid not in SELF_PAGE_IDS and pid not in ids:
                ids.append(pid)
    return ids


def collect_page_blocks(paths: list[Path]) -> dict[str, list[dict[str, str]]]:
    """문서들에서 Confluence 페이지 ID별로 연결된 블록 목록을 수집한다."""
    mapping: dict[str, list[dict[str, str]]] = {}
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for block_id, fields in check_docs.parse_blocks(text):
            source = fields.get("source", "")
            for pid in extract_confluence_ids(source):
                entry = {"id": block_id, "file": path.name, **fields}
                mapping.setdefault(pid, []).append(entry)
    return mapping


def compute_blocks_sha(blocks: list[dict[str, str]]) -> str:
    """블록 목록의 결정적 SHA-256 해시(앞 16자리)를 계산한다."""
    canonical = json.dumps(
        sorted(blocks, key=lambda b: b["id"]),
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def needs_sync(storage_html: str, target_sha: str) -> bool:
    """Confluence 본문의 마지막 동기화 해시와 현재 블록 해시가 다른지 확인한다."""
    match = SYNC_SHA_RE.search(storage_html)
    if not match:
        return True
    return match.group(1) != target_sha


def build_ai_banner(date_str: str, block_ids: list[str], summary: str, target_sha: str) -> str:
    """Confluence Storage Format 상단에 삽입할 AI 동기화 내역 Info 패널을 만든다."""
    ids_text = html.escape(", ".join(block_ids))
    summary_text = html.escape(summary.strip() or "팀 기준(jammy-docs) 최신 규칙·결정 반영")
    sha_text = html.escape(target_sha)
    return (
        '<ac:structured-macro ac:name="info">'
        "<ac:rich-text-body>"
        f"<p><strong>[jammy-docs AI 자동 최신화 · {html.escape(date_str)}]</strong> "
        '원본 기준: <a href="https://github.com/cloud4-final/jammy-docs">cloud4-final/jammy-docs</a> '
        f"(<code>sync-sha:{sha_text}</code>)</p>"
        f"<p>연결된 기준 ID: <code>{ids_text}</code></p>"
        f"<p>최근 반영 요약: {summary_text}</p>"
        "</ac:rich-text-body>"
        "</ac:structured-macro>"
    )


def strip_existing_banners(storage_html: str) -> str:
    """기존에 삽입된 모든 AI 최신화 Info 배너를 제거한다."""
    return BANNER_MACRO_RE.sub("", storage_html).lstrip()


def apply_banner(storage_html: str, banner_html: str) -> str:
    """기존 AI 배너들을 모두 제거하고 최상단에 최신 배너 1개만 추가한다."""
    cleaned = strip_existing_banners(storage_html)
    return banner_html + "\n" + cleaned


def check_ip_mask_leak(before_html: str, after_html: str) -> list[str]:
    """기존 Confluence 문서에 없던 마스킹 IP(10.10.x.x 등)가 새로 유입되었는지 검사한다."""
    before_masked = set(MASKED_IP_RE.findall(before_html))
    after_masked = set(MASKED_IP_RE.findall(after_html))
    return sorted(after_masked - before_masked)


def parse_llm_response(raw_text: str) -> tuple[str, list[tuple[str, str]]]:
    """LLM 응답에서 <summary>와 <replace><target>...<new>...</replace> 목록을 추출한다."""
    summary_match = SUMMARY_TAG_RE.search(raw_text)
    summary = summary_match.group(1).strip() if summary_match else "팀 기준(jammy-docs) 최신 규칙·결정 동기화"
    replacements = [
        (m.group(1).strip(), m.group(2).strip())
        for m in REPLACEMENTS_TAG_RE.finditer(raw_text)
        if m.group(1).strip()
    ]
    return summary, replacements


def apply_replacements(storage_html: str, replacements: list[tuple[str, str]]) -> tuple[str, int]:
    """원본 XHTML에서 정확히 일치하는 target 조각만 안전하게 치환한다(&middot; 등 엔티티 정규화 포함)."""
    updated = storage_html
    applied = 0
    for target, new in replacements:
        if not target or target == new:
            continue
        if target in updated:
            updated = updated.replace(target, new, 1)
            applied += 1
            continue
        # Confluence storage format은 '·'을 '&middot;'으로, '→'을 '&rarr;' 등으로 저장하는 경우가 많음
        norm_target = (
            target.replace("·", "&middot;")
            .replace("→", "&rarr;")
            .replace("←", "&larr;")
            .replace("↔", "&harr;")
            .replace("—", "&mdash;")
        )
        norm_new = (
            new.replace("·", "&middot;")
            .replace("→", "&rarr;")
            .replace("←", "&larr;")
            .replace("↔", "&harr;")
            .replace("—", "&mdash;")
        )
        if norm_target in updated and norm_target != norm_new:
            updated = updated.replace(norm_target, norm_new, 1)
            applied += 1
    return updated, applied


def select_llm_provider(env: Optional[dict[str, str]] = None) -> Optional[tuple[str, str]]:
    """사용 가능한 LLM 프로바이더와 API 키를 반환한다."""
    e = env if env is not None else os.environ
    for provider, key_name in (
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ):
        val = e.get(key_name, "").strip()
        if val:
            return provider, val
    return None


def build_prompt(page_title: str, current_html: str, blocks: list[dict[str, str]]) -> str:
    blocks_json = json.dumps(blocks, ensure_ascii=False, indent=2)
    return f"""당신은 팀 아키텍처·운영 문서 관리 AI다.
GitHub `cloud4-final/jammy-docs`의 최신 규칙·결정 블록을 기준으로, 아래 Confluence 페이지의 Storage Format XHTML 본문 중 **바뀌었거나 옛 상태(예: 미적용, 합의 대기, 제외 등)로 남아 있는 부분만** 찾아 최신화하라.

## 대상 Confluence 페이지 제목
{page_title}

## 적용할 jammy-docs 최신 블록 (JSON)
{blocks_json}

## 절대 지켜야 할 안전 규칙
1. **Confluence 내부의 실제 IP 보존**: jammy-docs는 Public 저장소라서 IP가 `10.10.x.110`처럼 `x`로 가려져 있다. Confluence 본문에 이미 실제 숫자 IP(예: `10.10.1.110`)가 적혀 있다면 절대 `x`로 덮어쓰지 마라.
2. **기존 문서 구조 보존**: 전체 문서를 다시 출력하지 말고, 고쳐야 할 정확한 부분 문자열(`<target>`)과 바꿀 문자열(`<new>`)만 출력하라. `<target>`은 현재 Confluence XHTML에 있는 문자열과 글자 그대로 일치해야 한다.
3. **응답 형식**: 반드시 아래 태그 형식으로만 응답하라. 고칠 문단이 없으면 `<summary>`만 출력하라.

<summary>어떤 문단/상태를 최신화했는지(또는 이미 최신 기준과 일치하는지) 한국어 한 줄 요약 (근거 ID 포함)</summary>
<replace>
<target>기존 XHTML에서 바꿀 정확한 조각</target>
<new>최신화된 XHTML 조각</new>
</replace>

## 현재 Confluence Storage Format XHTML
{current_html}
"""


def call_llm(provider: str, api_key: str, prompt: str) -> tuple[str, list[tuple[str, str]]]:
    """선택된 프로바이더의 REST API를 호출해 (summary, replacements)를 반환한다."""
    if provider == "anthropic":
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        raw_text = "".join(
            block.get("text", "") for block in data.get("content", []) if isinstance(block, dict) and "text" in block
        )
    elif provider == "openai":
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        raw_text = data["choices"][0]["message"]["content"]
    elif provider == "gemini":
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    else:
        raise ValueError(f"지원하지 않는 LLM provider: {provider}")

    return parse_llm_response(raw_text)


class ConfluenceClient:
    def __init__(self, domain: str, email: str, token: str):
        self.domain = domain
        auth = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
        self.headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _req(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        req = urllib.request.Request(
            f"https://{self.domain}/wiki{path}",
            method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers=self.headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raise RuntimeError(f"{method} {path}: {err.code} {err.read()[:200]!r}") from err

    def get_page(self, page_id: str) -> dict:
        return self._req("GET", f"/api/v2/pages/{page_id}?body-format=storage")

    def update_page(self, page_id: str, title: str, storage_value: str, next_version: int, message: str) -> None:
        self._req(
            "PUT",
            f"/api/v2/pages/{page_id}",
            {
                "id": page_id,
                "status": "current",
                "title": title,
                "body": {"representation": "storage", "value": storage_value},
                "version": {"number": next_version, "message": message},
            },
        )


def resolve_confluence_creds(env: Optional[dict[str, str]] = None) -> Optional[tuple[str, str]]:
    e = env if env is not None else os.environ
    email = e.get("CONFLUENCE_USER_NAME") or e.get("ATLASSIAN_EMAIL") or ""
    token = e.get("CONFLUENCE_API_KEY") or e.get("ATLASSIAN_TOKEN") or ""
    if email.strip() and token.strip():
        return email.strip(), token.strip()
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="jammy-docs 변경사항을 기존 Confluence 페이지에 AI로 반영")
    parser.add_argument("--apply", action="store_true", help="실제 Confluence 페이지 업데이트 수행")
    parser.add_argument("--dry-run", action="store_true", help="대상 페이지와 블록 매핑만 확인 (기본값)")
    parser.add_argument("--page-id", help="특정 Confluence 페이지 ID만 처리")
    parser.add_argument("--force", action="store_true", help="sync-sha가 같아도 강제 재실행")
    parser.add_argument("--max-pages", type=int, default=10, help="한 번에 최대 갱신할 페이지 수")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    doc_paths = [root / name for name in DOCS_FILES]
    page_blocks = collect_page_blocks(doc_paths)
    if args.page_id:
        page_blocks = {k: v for k, v in page_blocks.items() if k == args.page_id}

    if not args.apply:
        for pid, blocks in sorted(page_blocks.items()):
            ids = ", ".join(b["id"] for b in blocks)
            sha = compute_blocks_sha(blocks)
            print(f"[dry-run] Confluence {pid} (sha={sha}, blocks={len(blocks)}): {ids}")
        return 0

    creds = resolve_confluence_creds()
    if not creds:
        print("[skip] Confluence 자격 증명(CONFLUENCE_USER_NAME / CONFLUENCE_API_KEY)이 없어 건너뜁니다.")
        return 0

    llm = select_llm_provider()
    if not llm:
        print("[skip] LLM API 키(ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)가 없어 건너뜁니다.")
        return 0

    provider, api_key = llm
    client = ConfluenceClient(DOMAIN, creds[0], creds[1])
    today = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    updated_count = 0

    for pid, blocks in sorted(page_blocks.items()):
        if updated_count >= args.max_pages:
            print(f"[limit] 최대 페이지 수({args.max_pages})에 도달하여 나머지는 다음 주기에 처리합니다.")
            break
        target_sha = compute_blocks_sha(blocks)
        try:
            page = client.get_page(pid)
        except Exception as err:
            print(f"[warn] 페이지 조회 실패({pid}): {err}")
            continue

        title = page["title"]
        version_num = int(page["version"]["number"])
        current_html = page.get("body", {}).get("storage", {}).get("value", "")

        if not args.force and not needs_sync(current_html, target_sha):
            print(f"[up-to-date] {pid} ({title}) sha={target_sha}")
            continue

        block_ids = [b["id"] for b in blocks]
        clean_body = strip_existing_banners(current_html)

        try:
            summary, replacements = call_llm(provider, api_key, build_prompt(title, clean_body, blocks))
        except Exception as err:
            print(f"[warn] LLM 호출 실패({pid} {title}): {err}")
            continue

        candidate_body, applied_patches = apply_replacements(clean_body, replacements)

        leaked_masks = check_ip_mask_leak(clean_body, candidate_body)
        if leaked_masks:
            print(f"[guard] {pid} ({title}): 마스킹 IP 유입 감지({leaked_masks}) -> 본문 치환 취소, 배너만 갱신")
            candidate_body = clean_body
            summary += " (본문 IP 보호로 배너만 갱신)"

        banner = build_ai_banner(today, block_ids, summary, target_sha)
        final_html = apply_banner(candidate_body, banner)

        try:
            client.update_page(
                pid,
                title,
                final_html,
                version_num + 1,
                f"jammy-docs AI sync ({', '.join(block_ids[:5])})",
            )
            updated_count += 1
            print(f"[updated] {pid} ({title}) v{version_num + 1} (patches={applied_patches}): {summary}")
        except Exception as err:
            print(f"[warn] 페이지 업데이트 실패({pid} {title}): {err}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
