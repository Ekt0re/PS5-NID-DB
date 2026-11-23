import os
import re
from pathlib import Path

from nid_db.classify import classify_csharp, extract_body
from nid_db.github import record
from nid_db.nid import NID_RE, compute_nid

ATTRIBUTE = re.compile(
    r"\[SysAbiExport\s*\((?P<args>.*?)\)\s*\]",
    re.S,
)
NAMED = re.compile(r'(Nid|ExportName|LibraryName)\s*=\s*"([^"]*)"')
METHOD = re.compile(
    r"(?:public|internal|private|protected)\s+static\s+\w+(?:\s*<[^>]+>)?\s+(\w+)\s*\("
)
NAMESPACE = re.compile(r"\bnamespace\s+([\w.]+)")
SKIP_DIRS = {"obj", "bin", "tests"}


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def parse_args(block: str) -> dict[str, str]:
    values = {}
    for match in NAMED.finditer(block):
        values[match.group(1)] = match.group(2)
    return values


def method_after(text: str, start: int) -> tuple[str, int, str] | None:
    match = METHOD.search(text, start)
    if not match:
        return None
    opening = text.find("{", match.end() - 1)
    if opening < 0:
        return None
    body = extract_body(text, opening)
    return match.group(1), line_of(text, match.start(1)), body


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
                elif entry.name.endswith(".cs"):
                    found.append(Path(entry.path))
    return found


def scan_sharpemu(root: Path, *, github: str, sha: str, scan: str, **_kwargs) -> list[dict]:
    scan_root = root / scan
    if not scan_root.is_dir():
        return []
    records = []
    seen = set()
    for path in iter_sources(scan_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "SysAbiExport" not in text:
            continue
        namespace = NAMESPACE.search(text)
        in_stubs = bool(namespace and ".Stubs" in namespace.group(1))
        rel = path.relative_to(root).as_posix()
        for match in ATTRIBUTE.finditer(text):
            values = parse_args(match.group("args"))
            method = method_after(text, match.end())
            export_name = values.get("ExportName") or (method[0] if method else "")
            nid = values.get("Nid") or (compute_nid(export_name) if export_name else "")
            if not nid or not NID_RE.fullmatch(nid):
                continue
            if nid in seen:
                continue
            seen.add(nid)
            library = values.get("LibraryName") or path.parent.name
            if method:
                name, line, body = method
                status = classify_csharp(body, in_stubs_namespace=in_stubs)
                display = export_name or name
                records.append(record("sharpemu", nid, display, library, status, rel, line, sha, github))
            else:
                records.append(
                    record(
                        "sharpemu",
                        nid,
                        export_name or nid,
                        library,
                        "unknown",
                        rel,
                        line_of(text, match.start()),
                        sha,
                        github,
                    )
                )
    return records
