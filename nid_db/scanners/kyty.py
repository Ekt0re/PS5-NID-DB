import os
import re
from pathlib import Path

from nid_db.classify import classify_cpp, extract_body
from nid_db.github import record
from nid_db.nid import NID_RE

LIB_NAME = re.compile(r'\bLIB_NAME\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)')
LIB_FUNC = re.compile(r'\bLIB_FUNC(?!_IN|_POSIX)\s*\(\s*"([^"]+)"\s*,\s*([^)]+?)\)')
LIB_FUNC_IN = re.compile(r'\bLIB_FUNC_IN\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([^)]+?)\)')
LIB_FUNC_POSIX = re.compile(r'\bLIB_FUNC_POSIX_KERNEL\s*\(\s*"([^"]+)"\s*,\s*([^)]+?)\)')
KEYWORDS = frozenset(
    {"if", "while", "for", "switch", "catch", "return", "else", "do", "sizeof", "alignof"}
)
SKIP_DIRS = {"3rdparty", "tests", ".git"}


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def last_name(qualified: str) -> str:
    return qualified.strip().split("::")[-1].strip()


def iter_sources(root: Path) -> list[Path]:
    found = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError:
            continue
        with entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRS and not entry.name.startswith("."):
                        stack.append(Path(entry.path))
                elif entry.name.endswith((".cpp", ".cc", ".h", ".hpp", ".cxx")):
                    found.append(Path(entry.path))
    return found


def find_definition(text: str, name: str) -> tuple[int, str] | None:
    pattern = re.compile(
        rf"(?:^|\n)[^\n;{{}}]*?\b{re.escape(name)}\s*\([^;{{]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{{",
        re.M,
    )
    for match in pattern.finditer(text):
        prefix = match.group()
        ident = re.findall(r"\b\w+\b", prefix)
        if ident and ident[0] in KEYWORDS:
            continue
        if re.search(rf"\b(?:if|while|for|switch)\s*\(\s*$", prefix.split(name)[0]):
            continue
        brace = match.end() - 1
        return line_of(text, match.start()), extract_body(text, brace)
    return None


def build_index(resolve_root: Path, names: set[str]) -> dict[str, tuple[Path, int, str]]:
    index: dict[str, tuple[Path, int, str]] = {}
    if not names:
        return index
    for path in iter_sources(resolve_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        remaining = [name for name in names if name not in index]
        if not remaining:
            break
        for name in remaining:
            if name not in text:
                continue
            found = find_definition(text, name)
            if found:
                index[name] = (path, found[0], found[1])
    return index


def scan_kyty(root: Path, *, github: str, sha: str, scan: str, resolve: str | None = None, **_kwargs) -> list[dict]:
    scan_root = root / scan
    resolve_root = root / (resolve or scan)
    if not scan_root.is_dir():
        return []

    symbols: list[tuple[str, str, str, Path, int]] = []
    for path in iter_sources(scan_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        default_lib = None
        match_name = LIB_NAME.search(text)
        if match_name:
            default_lib = match_name.group(1)
        if "LIB_FUNC" not in text and "LIB_FUNC_IN" not in text and "LIB_FUNC_POSIX_KERNEL" not in text:
            continue
        for match in LIB_FUNC_IN.finditer(text):
            nid, library, func = match.group(1), match.group(2), last_name(match.group(3))
            if NID_RE.fullmatch(nid):
                symbols.append((nid, func, library, path, line_of(text, match.start())))
        for match in LIB_FUNC.finditer(text):
            nid, func = match.group(1), last_name(match.group(2))
            if NID_RE.fullmatch(nid):
                symbols.append((nid, func, default_lib or path.stem, path, line_of(text, match.start())))
        for match in LIB_FUNC_POSIX.finditer(text):
            nid, func = match.group(1), last_name(match.group(2))
            if NID_RE.fullmatch(nid):
                symbols.append((nid, func, "libkernel", path, line_of(text, match.start())))

    names = {item[1] for item in symbols}
    index = build_index(resolve_root, names)
    records = []
    seen = set()
    for nid, func, library, path, line in symbols:
        if nid in seen:
            continue
        seen.add(nid)
        found = index.get(func)
        if found:
            src, src_line, body = found
            status = classify_cpp(body)
            rel = src.relative_to(root).as_posix()
            records.append(record("kyty", nid, func, library, status, rel, src_line, sha, github))
        else:
            rel = path.relative_to(root).as_posix()
            records.append(record("kyty", nid, func, library, "unknown", rel, line, sha, github))
    return records
