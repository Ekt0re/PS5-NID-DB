import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
REPOS = ROOT / "repos"
DATA = ROOT / "data"
SITE = ROOT / "site"
STATE_PATH = DATA / "state.json"
HISTORY_PATH = DATA / "history.json"
NIDS_PATH = DATA / "nids.json"


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
