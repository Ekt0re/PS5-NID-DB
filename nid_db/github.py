from pathlib import Path, PurePosixPath


def permalink(github: str, sha: str, path: str | Path, line: int | None) -> str:
    rel = PurePosixPath(str(path).replace("\\", "/"))
    ref = sha or "main"
    url = f"https://github.com/{github}/blob/{ref}/{rel}"
    if line:
        url += f"#L{line}"
    return url


def record(
    emulator: str,
    nid: str,
    name: str,
    library: str,
    status: str,
    path: str,
    line: int,
    sha: str,
    github: str,
) -> dict:
    return {
        "emulator": emulator,
        "nid": nid,
        "name": name,
        "library": library,
        "status": status,
        "path": str(path).replace("\\", "/"),
        "line": line,
        "sha": sha,
        "url": permalink(github, sha, path, line),
    }
