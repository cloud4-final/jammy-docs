"""jammy-docs 문서가 max_lines(기본 160줄)를 넘으면 중요 내용 위주로 자동 압축한다.

1단계 (결정적 구조 압축):
  - 연속 빈 줄 제거
  - 여러 줄로 풀어진 메타데이터 필드(scope, violation, status, source, owner, by, implies, why)를
    '|' 구분 한 줄로 병합하고, 여러 줄 rule/decision 본문을 한 줄로 합친다.
  - superseded 블록은 rule/decision을 핵심 요약으로 줄이고 by만 남긴다.

2단계 (AI 요약 압축):
  - 1단계 후에도 max_lines를 넘고 LLM API 키(ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)가 있으면,
    AI가 블록 ID·필수 필드·포트·대역·수치·버전·상태는 100% 보존하면서 서술어만 간결하게 줄인다.
  - 압축 후 check_docs 검증(IP 마스킹, page ID, 블록 필수 필드, ID 참조)을 통과할 때만 파일에 반영한다.
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import ai_patch_confluence as ap
import check_docs

HEADING_LINE = re.compile(r"^### (\S+) · (.+)$")
SECTION_LINE = re.compile(r"^## .+$")


def format_compact_block(block_id: str, title: str, fields: dict[str, str], single_line: bool = False) -> list[str]:
    """블록 1개를 최소 줄 수(2~3줄)로 직렬화한다."""
    kind = block_id[0]
    status = fields.get("status", "active").split(" ")[0]
    primary_key = "decision" if kind == "D" else "rule"
    primary_val = re.sub(r"\s+", " ", fields.get(primary_key, "")).strip()

    if status == "superseded":
        # superseded 블록은 2줄로 최소화
        by_val = fields.get("by", "")
        short_primary = primary_val[:60] + ("…" if len(primary_val) > 60 else "")
        return [
            f"### {block_id} · {title}",
            f"- {primary_key}: {short_primary} | status: {fields.get('status', 'superseded')} | by: {by_val}",
        ]

    meta_order = {
        "C": ["scope", "violation", "owner", "status", "source"],
        "D": ["implies", "why", "scope", "status", "source"],
        "A": ["scope", "violation", "status", "source"],
        "M": ["owner", "scope", "status", "source"],
    }.get(kind, ["scope", "status", "source"])

    meta_parts = []
    for k in meta_order:
        if k in fields and fields[k]:
            val = re.sub(r"\s+", " ", fields[k]).strip()
            meta_parts.append(f"{k}: {val}")

    if single_line:
        all_parts = [f"{primary_key}: {primary_val}"] + meta_parts
        return [
            f"### {block_id} · {title}",
            f"- {' | '.join(all_parts)}",
        ]

    return [
        f"### {block_id} · {title}",
        f"- {primary_key}: {primary_val}",
        f"- {' | '.join(meta_parts)}",
    ]


def deterministic_compact(text: str, single_line: bool = False) -> str:
    """마크다운 문서를 파싱해 모든 블록을 2~3줄 형식으로 압축하고 불필요한 빈 줄을 제거한다."""
    lines = text.splitlines()
    first_heading_idx = next((i for i, l in enumerate(lines) if HEADING_LINE.match(l) or SECTION_LINE.match(l)), len(lines))

    # 서두(preamble)의 연속 빈 줄 정리
    preamble_lines: list[str] = []
    for line in lines[:first_heading_idx]:
        if not line.strip() and (not preamble_lines or not preamble_lines[-1].strip()):
            continue
        preamble_lines.append(line)

    # 첫 '### ' 이전까지의 섹션과 블록들을 순서대로 재구성
    blocks_map = dict(check_docs.parse_blocks(text))
    out: list[str] = list(preamble_lines)
    if out and out[-1].strip() and not single_line:
        out.append("")

    i = first_heading_idx
    while i < len(lines):
        line = lines[i]
        sec_m = SECTION_LINE.match(line)
        if sec_m and not line.startswith("### "):
            if out and out[-1].strip() and not single_line:
                out.append("")
            out.append(line.strip())
            i += 1
            # 섹션 직후 일반 설명 줄(블록 시작 전) 보존
            while i < len(lines) and not HEADING_LINE.match(lines[i]) and not SECTION_LINE.match(lines[i]):
                if lines[i].strip():
                    out.append(lines[i])
                i += 1
            continue

        hm = HEADING_LINE.match(line)
        if hm:
            block_id, title = hm.group(1), hm.group(2).strip()
            fields = blocks_map.get(block_id)
            if fields:
                out.extend(format_compact_block(block_id, title, fields, single_line=single_line))
            else:
                out.append(line)
            i += 1
            while i < len(lines) and not HEADING_LINE.match(lines[i]) and not SECTION_LINE.match(lines[i]):
                i += 1
            continue

        if line.strip():
            out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n"


def build_ai_compact_prompt(filename: str, text: str, max_lines: int) -> str:
    return f"""당신은 팀 기술 기준 문서(`{filename}`) 압축기다.
현재 문서가 {len(text.splitlines())}줄로, AI 가독성 한도인 {max_lines}줄을 초과했다.
아래 절대 규칙을 지키면서 중요 핵심 내용(포트, 대역, IP, 버전, 환경변수, API 경로, MUST/MUST NOT 조건, 담당자)만 남기고 군더더기 서술어를 줄여 **{max_lines - 15}줄 이하**로 압축하라.

## 절대 보존 규칙 (어기면 검증 실패)
1. 1행의 `<!-- confluence-page-id: ... -->` 주석과 2행의 `# ...` 제목을 그대로 유지하라.
2. 모든 `### <ID> · <제목>` 블록 헤더를 빠짐없이 유지하라(ID 변경·삭제 절대 금지).
3. 각 블록의 필수 필드 키(`- rule:`, `- decision:`, `scope:`, `violation:`, `implies:`, `why:`, `owner:`, `status:`, `source:`, `by:`)와 다른 블록 ID 참조(`C-...`, `D-...`, `A-...`, `M-...`), `Confluence <숫자>` 출처를 절대 지우지 마라.
4. 각 블록은 헤더 1줄 + `- rule:`(또는 `- decision:`) 1줄 + `- scope: ... | ... | status: ... | source: ...` 1줄(총 3줄, superseded는 2줄) 형식을 유지하고, 블록 사이의 빈 줄을 없애라.
5. IP 마스킹(`10.10.x.x` 등)을 절대 풀지 마라.
6. 마크다운 코드블록(```)으로 감싸지 말고 압축된 마크다운 원문만 바로 출력하라.

## 현재 문서
{text}
"""


def call_llm_raw(provider: str, api_key: str, prompt: str) -> str:
    """선택된 LLM을 호출해 압축된 마크다운 원문을 반환한다."""
    import json
    import os
    import urllib.request

    if provider == "anthropic":
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
        payload = {"model": model, "max_tokens": 8192, "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        raw = "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict) and "text" in b)
    elif provider == "openai":
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        raw = data["choices"][0]["message"]["content"]
    elif provider == "gemini":
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", cleaned, flags=re.S).strip()
    return cleaned + "\n"


def compact_file_if_needed(
    path: Path,
    all_block_paths: list[Path],
    max_lines: int = 160,
    env: Optional[dict[str, str]] = None,
) -> tuple[bool, int, int]:
    """파일이 max_lines를 넘으면 (1) 결정적 압축, (2) 부족 시 AI 압축을 수행하고 검증 통과 시 저장한다.
    반환값: (변경 여부, 기존 줄 수, 최종 줄 수)
    """
    original = path.read_text(encoding="utf-8")
    before_lines = len(original.splitlines())
    if before_lines <= max_lines:
        return False, before_lines, before_lines

    candidate = deterministic_compact(original)
    after_det_lines = len(candidate.splitlines())

    if after_det_lines > max_lines:
        llm = ap.select_llm_provider(env)
        if llm:
            try:
                ai_cand = call_llm_raw(llm[0], llm[1], build_ai_compact_prompt(path.name, candidate, max_lines))
                if len(ai_cand.splitlines()) <= max_lines:
                    candidate = ai_cand
            except Exception as err:
                print(f"[warn] {path.name} AI 압축 호출 실패({err}), 2줄 초압축 모드 시도")
                candidate = deterministic_compact(original, single_line=True)
        else:
            candidate = deterministic_compact(original, single_line=True)

    # 임시 적용 후 check_docs 검증 (블록 ID 누락·필수 필드·IP 마스킹·참조 무결성 확인)
    orig_ids = {bid for bid, _ in check_docs.parse_blocks(original)}
    cand_ids = {bid for bid, _ in check_docs.parse_blocks(candidate)}
    if orig_ids != cand_ids:
        print(f"[guard] {path.name}: 블록 ID 집합 불일치로 압축 취소 (누락: {orig_ids - cand_ids})")
        return False, before_lines, before_lines

    path.write_text(candidate, encoding="utf-8")
    errors = check_docs.check_doc(path, require_page_id=True, max_lines=max_lines)
    if path in all_block_paths:
        errors += check_docs.check_blocks(all_block_paths)
    if errors:
        path.write_text(original, encoding="utf-8")
        print(f"[guard] {path.name}: 압축 결과 검증 실패로 원복 ({errors})")
        return False, before_lines, before_lines

    final_lines = len(candidate.splitlines())
    print(f"[compacted] {path.name}: {before_lines}줄 -> {final_lines}줄 (한도 {max_lines}줄)")
    return True, before_lines, final_lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="160줄 초과 문서를 중요 내용 위주로 자동 압축")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--max-lines", type=int, default=160)
    args = parser.parse_args(argv)

    paths = [Path(f) for f in args.files]
    block_paths = [p for p in paths if p.name != "README.md"]
    for p in paths:
        compact_file_if_needed(p, block_paths, max_lines=args.max_lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
