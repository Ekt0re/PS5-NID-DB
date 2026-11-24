import json
import os
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
REPOS = ROOT / "repos"
DATA = ROOT / "data"
SITE = ROOT / "site"
STATE_PATH = DATA / "state.json"
HISTORY_PATH = DATA / "history.json"
NIDS_PATH = DATA / "nids.json"

_PROGRESS_LOCK = threading.Lock()


def print_progress(label: str, done: int, total: int, width: int = 24) -> None:
    """Print a compact single-line progress bar to stdout."""
    total = max(1, total)
    ratio = min(1.0, max(0.0, done / total))
    filled = int(round(width * ratio))
    bar = "#" * filled + "-" * (width - filled)
    pct = int(ratio * 100)
    end = "\n" if done >= total else ""
    with _PROGRESS_LOCK:
        sys.stdout.write(f"\r[{label}] [{bar}] {done}/{total} ({pct}%){end}")
        sys.stdout.flush()


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text atomically via a temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(content)
        for attempt in range(10):
            try:
                os.replace(tmp_path, path)
                return
            except OSError:
                if attempt == 9:
                    break
                time.sleep(0.05 * (attempt + 1))
        # Fallback for Windows rename/AV locks on existing destination files
        with path.open("w", encoding=encoding, newline="\n") as handle:
            handle.write(content)
        tmp_path.unlink(missing_ok=True)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def emulator_dir(cfg: dict) -> Path:
    primary = REPOS / cfg["dir"]
    if (primary / ".git").exists() or (primary / cfg["scan"]).exists():
        return primary
    for name in cfg.get("fallback_dirs", []):
        candidate = REPOS / name
        if candidate.is_dir():
            return candidate
    return primary
