import os
import re
from pathlib import Path

from nid_db.classify import classify_cpp, extract_body, strip_comments
from nid_db.github import record
from nid_db.nid import NID_RE, compute_nid, strip_nid_postfix

EXPORT = re.compile(r'\bAPS5_EXPORT\s*\(\s*"([^"]+)"\s*,\s*(\w+)\s*\)')
DEFINITION = re.compile(
    r"(?:^|\n)(?P<prefix>[^\n;{}]*?)\bAPS5_VABI\s+(?P<name>\w+)\s*\([^;{]*\)\s*"
    r"(?:noexcept\s*)?(?:try\s*)?\{",
    re.M,
)
SKIP_DIRS = {"tests"}


def library_from_path(scan_root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(scan_root)
    except ValueError:
        return path.parent.name
    parts = relative.parts
    folder = parts[0] if parts else path.parent.name
    if folder.endswith(".native"):
        return folder[: -len(".native")]
    return folder


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


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def is_unknown_name(name: str) -> bool:
    lowered = name.lower()
    return "unknown" in lowered or name.endswith("_nid_no_patch") or name.endswith("_nid_no_patch_cut")


def scan_anyps5(root: Path, *, github: str, sha: str, scan: str, **_kwargs) -> list[dict]:
    scan_root = root / scan
    if not scan_root.is_dir():
        return []
    definitions: dict[str, tuple[Path, int, str]] = {}
    exports: list[tuple[str, str, Path, int]] = []
    files: list[tuple[Path, str]] = []

    for path in iter_sources(scan_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        files.append((path, text))
        if "APS5_EXPORT" in text:
            for match in EXPORT.finditer(text):
                nid, name = match.group(1), match.group(2)
                if NID_RE.fullmatch(nid):
                    exports.append((nid, name, path, line_of(text, match.start())))
        if "APS5_VABI" in text:
            for match in DEFINITION.finditer(text):
                if re.search(r"\bstatic\b", match.group("prefix") or ""):
                    continue
                name = match.group("name")
                brace = match.end() - 1
                body = extract_body(text, brace)
                definitions[name] = (path, line_of(text, match.start("name")), body)

    exported_names = {name for _, name, _, _ in exports}
    records = []
    seen = set()

    def add(nid, name, path, line, body):
        key = nid
        if key in seen:
            return
        seen.add(key)
        if body is None:
            status = "unknown"
        elif is_unknown_name(name) and classify_cpp(body) == "stub":
            status = "unknown" if is_unknown_name(name) and "Unknown" in name else "stub"
            if "Unknown" in name:
                status = "unknown"
            else:
                status = classify_cpp(body)
        else:
            status = classify_cpp(body)
            if is_unknown_name(name) and "Unknown" in name:
                status = "unknown"
        rel = path.relative_to(root).as_posix()
        records.append(
            record("anyps5", nid, strip_nid_postfix(name), library_from_path(scan_root, path), status, rel, line, sha, github)
        )

    for nid, name, path, line in exports:
        found = definitions.get(name)
        body = found[2] if found else None
        src_path, src_line = (found[0], found[1]) if found else (path, line)
        add(nid, name, src_path, src_line, body)

    for name, (path, line, body) in definitions.items():
        if name in exported_names:
            continue
        nid = compute_nid(strip_nid_postfix(name))
        add(nid, name, path, line, body)

    return records
