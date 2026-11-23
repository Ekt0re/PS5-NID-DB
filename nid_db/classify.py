import re

DISCARD = re.compile(r"\(void\)\s*[\w.]+\s*;")
EMPTY_RETURN = re.compile(r"return\s*;")
CONST_RETURN = re.compile(
    r"return\s+(?:[+-]?\s*(?:0[xX][0-9a-fA-F]+|\d+)[uUlL]*|[A-Za-z_]\w*|nullptr|NULL|true|false"
    r"|\"(?:\\.|[^\"\\])*\")\s*;"
)
BARE_THROW = re.compile(r"throw\b[^;]*;")
CS_INERT_RETURN = re.compile(
    r"return\s+(?:"
    r"0|"
    r"Ok\s*\(\s*\w+\s*\)|"
    r"(?:\w+\.)?SetReturn\s*\(\s*(?:0|[A-Za-z_][\w.]*)\s*\)"
    r")\s*;"
)
CS_SETRETURN = re.compile(r"(?:\w+\.)?SetReturn\s*\(\s*(?:0|[A-Za-z_][\w.]*)\s*\)\s*;")
COMMENT_LINE = re.compile(r"//.*?$", re.M)
COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.S)
CS_COMMENT_LINE = re.compile(r"///.*?$|//.*?$", re.M)
BRACE = re.compile(r"[{}]")
STRING = re.compile(r'"(?:\\.|[^"\\])*"')
CPP_STUB_MARKERS = (
    "NotImplemented_nid_no_patch",
    "UNIMPLEMENTED()",
    "UNIMPLEMENTED_MSG",
    "EXIT_NOT_IMPLEMENTED(true)",
    "EXIT_NOT_IMPLEMENTED(1)",
    "EXIT_NOT_IMPLEMENTED(false == false)",
)
CS_STUB_MARKERS = (
    "NotImplementedException",
    "throw new NotImplemented",
)
LOGIC = re.compile(r"\b(?:if|for|while|switch|foreach|do)\b")


def strip_comments(text: str, csharp: bool = False) -> str:
    pattern = CS_COMMENT_LINE if csharp else COMMENT_LINE
    text = pattern.sub(" ", text)
    return COMMENT_BLOCK.sub(" ", text)


def body_end(text: str, start: int) -> int:
    depth = 0
    for brace in BRACE.finditer(text, start):
        if brace.group() == "{":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return brace.end()
    return len(text)


def extract_body(text: str, brace_index: int) -> str:
    return text[brace_index : body_end(text, brace_index)]


def _statements(body: str) -> list[str]:
    inner = body.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    inner = DISCARD.sub(" ", inner)
    inner = STRING.sub('""', inner)
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(inner):
        if ch in "{(":
            depth += 1
        elif ch in "})":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            part = inner[start : i + 1].strip()
            if part:
                parts.append(part)
            start = i + 1
    tail = inner[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def classify_cpp(body: str) -> str:
    raw = strip_comments(body)
    for marker in CPP_STUB_MARKERS:
        if marker in raw:
            return "stub"
    statements = _statements(raw)
    if not statements:
        return "stub"
    for statement in statements:
        compact = " ".join(statement.split())
        if EMPTY_RETURN.fullmatch(compact) or CONST_RETURN.fullmatch(compact) or BARE_THROW.fullmatch(compact):
            continue
        return "implemented"
    return "stub"


def classify_csharp(body: str, *, in_stubs_namespace: bool = False) -> str:
    if in_stubs_namespace:
        return "stub"
    raw = strip_comments(body, csharp=True)
    for marker in CS_STUB_MARKERS:
        if marker in raw:
            return "stub"
    statements = _statements(raw)
    if not statements:
        return "stub"
    if LOGIC.search(raw):
        return "implemented"
    for statement in statements:
        compact = " ".join(statement.split())
        if (
            CS_INERT_RETURN.fullmatch(compact)
            or CS_SETRETURN.fullmatch(compact)
            or EMPTY_RETURN.fullmatch(compact)
            or BARE_THROW.fullmatch(compact)
        ):
            continue
        if CONST_RETURN.fullmatch(compact):
            continue
        return "implemented"
    return "stub"
