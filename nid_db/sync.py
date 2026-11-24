from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import subprocess
from pathlib import Path

from nid_db.paths import DATA, REPOS, STATE_PATH, atomic_write_text, emulator_dir, load_config, print_progress


def run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def git_ok(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess | None:
    try:
        return run_git(args, cwd)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def head_sha(repo: Path) -> str | None:
    if not (repo / ".git").exists():
        return None
    result = git_ok(["rev-parse", "HEAD"], repo)
    if result is None:
        return None
    return result.stdout.strip() or None


def load_state() -> dict:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"emulators": {}}


def save_state(state: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    atomic_write_text(STATE_PATH, json.dumps(state, indent=2) + "\n")


def sync_emulator(name: str, cfg: dict, state: dict) -> dict:
    REPOS.mkdir(parents=True, exist_ok=True)
    dest = REPOS / cfg["dir"]
    branch = cfg.get("branch", "main")
    info = {"dir": str(dest), "updated": False, "sha": None, "skipped": False}

    if dest.exists() and not (dest / ".git").exists():
        sha = head_sha(dest)
        info["sha"] = sha
        info["skipped"] = True
        info["reason"] = "directory exists but is not a git clone"
        state.setdefault("emulators", {})[name] = {"sha": sha, "path": str(dest)}
        return info

    if not dest.exists():
        run_git(["clone", "--depth", "1", "--branch", branch, cfg["url"], str(dest)])
        info["updated"] = True
    else:
        run_git(["fetch", "--depth", "1", "origin", branch], dest)
        remote = git_ok(["rev-parse", f"origin/{branch}"], dest)
        local = head_sha(dest)
        remote_sha = remote.stdout.strip() if remote else None
        previous = state.get("emulators", {}).get(name, {}).get("sha")
        if remote_sha and remote_sha not in {local, previous}:
            run_git(["checkout", "-B", branch, f"origin/{branch}"], dest)
            run_git(["reset", "--hard", f"origin/{branch}"], dest)
            info["updated"] = True
        elif previous and local and previous != local:
            info["updated"] = True

    sha = head_sha(dest)
    info["sha"] = sha
    state.setdefault("emulators", {})[name] = {"sha": sha, "path": str(dest)}
    return info


def collect_shas() -> dict[str, str | None]:
    config = load_config()
    state = load_state()
    shas = {}
    for name, cfg in config["emulators"].items():
        repo = emulator_dir(cfg)
        sha = head_sha(repo)
        if sha is None and (repo / ".git").exists():
            sha = state.get("emulators", {}).get(name, {}).get("sha")
        shas[name] = sha
        if (repo / ".git").exists():
            state.setdefault("emulators", {})[name] = {
                "sha": sha,
                "path": str(repo),
            }
    save_state(state)
    return shas


def sync_all() -> dict:
    config = load_config()
    state = load_state()
    emulators = config["emulators"]
    total = len(emulators)
    reports = {}
    if total == 0:
        save_state(state)
        return reports

    print_progress("sync", 0, total)
    done = 0
    with ThreadPoolExecutor(max_workers=total) as pool:
        futures = {
            pool.submit(sync_emulator, name, cfg, {}): name
            for name, cfg in emulators.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            info = future.result()
            reports[name] = info
            state.setdefault("emulators", {})[name] = {
                "sha": info.get("sha"),
                "path": info.get("dir"),
            }
            done += 1
            print_progress("sync", done, total)

    save_state(state)
    return reports
