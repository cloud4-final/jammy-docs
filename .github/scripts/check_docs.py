"""jammy-docs 문서 검사: 가리지 않은 IPv4, Confluence page ID, 최대 줄 수, 블록 형식, 대량 삭제 가드."""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
ALLOWED_IPV4 = {"1.1.1.1", "100.64.0.0"}
PAGE_ID = re.compile(r"<!-- confluence-page-id: \d+ -->")


def find_unmasked_ipv4(text: str) -> list[str]:
    return [ip for ip in IPV4.findall(text) if ip not in ALLOWED_IPV4]


def check_doc(path: Path, require_page_id: bool, max_lines: Optional[int] = None) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors = [
        f"{path}: 가리지 않은 IP {ip} (앞 두 자리만 쓰고 나머지는 x로 가린다)"
        for ip in find_unmasked_ipv4(text)
    ]
    if require_page_id and not PAGE_ID.search(text):
        errors.append(f"{path}: <!-- confluence-page-id: N --> 주석이 없다")
    if max_lines is not None:
        line_count = len(text.splitlines())
        if line_count > max_lines:
            errors.append(f"{path}: {line_count}줄 (AI 가독성 한도 {max_lines}줄 초과 — 블록을 압축하라)")
    return errors


HEADING = re.compile(r"^### (\S+) · ", re.M)
ID_FORMAT = re.compile(r"^([CAM]-[A-Z]+-\d{3}|D-\d{8}-\d{2})$")
ID_REF = re.compile(r"\b(?:[CAM]-[A-Z]+-\d{3}|D-\d{8}-\d{2})\b")
INLINE_FIELD = re.compile(r"(?:^|\n|- |\s*\|\s*)([a-z_]+):\s*", re.M)
STATUSES = ("active", "open", "superseded")
REQUIRED = {
    "C": {"active": ["rule", "scope", "violation", "source"], "open": ["rule", "owner"], "superseded": ["rule", "by"]},
    "D": {"active": ["decision", "implies", "why", "scope", "source"], "superseded": ["decision", "by"]},
    "A": {"active": ["rule", "scope", "violation", "source"], "superseded": ["rule", "by"]},
    "M": {"active": ["rule", "owner", "scope", "source"], "open": ["rule", "owner"], "superseded": ["rule", "by"]},
}


def parse_blocks(text: str) -> list[tuple[str, dict[str, str]]]:
    """'### ID · 제목' 블록을 (ID, {field: value}) 목록으로 나눈다 (다중 줄 및 '|' 구분 한 줄 표기 모두 지원)."""
    starts = [m for m in HEADING.finditer(text)]
    blocks = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        body = text[m.end():end].split("\n## ")[0]
        matches = list(INLINE_FIELD.finditer(body))
        fields = {}
        for j, fm in enumerate(matches):
            val_end = matches[j + 1].start() if j + 1 < len(matches) else len(body)
            fields[fm.group(1)] = body[fm.end():val_end].strip()
        blocks.append((m.group(1), fields))
    return blocks


def check_blocks(paths: list[Path]) -> list[str]:
    errors, seen, texts = [], {}, []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        texts.append(text)
        for block_id, fields in parse_blocks(text):
            where = f"{path.name}:{block_id}"
            if not ID_FORMAT.match(block_id):
                errors.append(f"{where}: ID 형식이 C-AAA-000 또는 D-YYYYMMDD-00이 아니다")
                continue
            if block_id in seen:
                errors.append(f"{where}: ID 중복 ({seen[block_id]})")
            seen[block_id] = path.name
            status = fields.get("status", "").split(" ")[0]
            if status not in STATUSES or status not in REQUIRED[block_id[0]]:
                errors.append(f"{where}: status는 {', '.join(REQUIRED[block_id[0]])} 중 하나여야 한다")
                continue
            for name in REQUIRED[block_id[0]][status]:
                if not fields.get(name):
                    errors.append(f"{where}: 필드 {name}가 없다")
    for text in texts:
        for ref in sorted(set(ID_REF.findall(text)) - set(seen)):
            errors.append(f"존재하지 않는 ID 참조: {ref}")
    return errors


def compare_text_deletion(
    name: str,
    before_text: str,
    after_text: str,
    max_drop_ratio: float = 0.20,
    check_block_ids: bool = True,
) -> list[str]:
    """이전 본문 대비 블록 ID 삭제 여부 및 본문 길이 급감(기본 20% 이상)을 검사한다."""
    errors: list[str] = []
    if not before_text.strip():
        return errors
    before_len = len(before_text.strip())
    after_len = len(after_text.strip())
    if before_len >= 100:
        drop_ratio = (before_len - after_len) / before_len
        if drop_ratio >= max_drop_ratio:
            pct = int(round(drop_ratio * 100))
            errors.append(
                f"{name}: 대량 삭제 가드 발동 — 본문 길이가 {before_len}자 -> {after_len}자로 {pct}% 감소 (허용 한도 {int(max_drop_ratio * 100)}%)"
            )
    if check_block_ids:
        before_ids = {bid for bid, _ in parse_blocks(before_text)}
        after_ids = {bid for bid, _ in parse_blocks(after_text)}
        removed_ids = sorted(before_ids - after_ids)
        if removed_ids:
            errors.append(
                f"{name}: 블록 무단 삭제 감지({', '.join(removed_ids)}) — 삭제 대신 status: superseded를 사용하라"
            )
    return errors


def check_git_deletion_guard(
    paths: list[Path],
    base_ref: str = "HEAD~1",
    max_drop_ratio: float = 0.20,
) -> list[str]:
    """직전 Git 커밋(base_ref) 대비 대량 삭제 또는 블록 삭제 여부를 검사한다."""
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            repo_root = subprocess.check_output(
                ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            rel_path = path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
            before_text = subprocess.check_output(
                ["git", "-C", repo_root, "show", f"{base_ref}:{rel_path}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            continue
        after_text = path.read_text(encoding="utf-8")
        has_blocks = path.name != "README.md"
        errors.extend(
            compare_text_deletion(
                path.name,
                before_text,
                after_text,
                max_drop_ratio=max_drop_ratio,
                check_block_ids=has_blocks,
            )
        )
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--require-page-id", action="store_true")
    parser.add_argument("--blocks", action="store_true", help="규칙·결정 블록 형식 검사")
    parser.add_argument("--max-lines", type=int, default=None, help="파일당 최대 허용 줄 수 (예: 150)")
    parser.add_argument("--guard-git-diff", action="store_true", help="직전 커밋 대비 대량 삭제 및 블록 삭제 차단")
    parser.add_argument("--base-ref", default="HEAD~1", help="대량 삭제 비교 기준 Git ref (기본: HEAD~1)")
    args = parser.parse_args(argv)
    file_paths = [Path(f) for f in args.files]
    errors = [e for p in file_paths for e in check_doc(p, args.require_page_id, args.max_lines)]
    if args.blocks:
        errors += check_blocks(file_paths)
    if args.guard_git_diff:
        errors += check_git_deletion_guard(file_paths, base_ref=args.base_ref)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
