from collections import Counter
from datetime import date, datetime, timezone
import json

from nid_db import EMULATORS
from nid_db.nid import compute_nid
from nid_db.paths import DATA, HISTORY_PATH, NIDS_PATH


def _score_name(nid: str, name: str) -> tuple:
    if not name:
        return (0, 0, 0, 0)
    hashed = compute_nid(name) == nid
    sce = name.startswith("sce") or name.startswith("Sce")
    unknown = "Unknown" in name or "unknown" in name
    return (int(hashed), int(not unknown), int(sce), -len(name))


def pick_name(nid: str, entries: dict[str, dict]) -> str:
    ranked = []
    for row in entries.values():
        if not row or not row.get("name"):
            continue
        ranked.append((_score_name(nid, row["name"]), row["name"]))
    if not ranked:
        return nid
    ranked.sort(reverse=True)
    return ranked[0][1]


def pick_library(entries: dict[str, dict]) -> str:
    names = []
    for emu in ("sharpemu", "anyps5", "kyty"):
        row = entries.get(emu)
        if row and row.get("library"):
            names.append(row["library"])
    if not names:
        return ""
    counts = Counter(names)
    return counts.most_common(1)[0][0]


def empty_emu() -> dict:
    return {"status": "not_implemented", "url": None, "name": None, "path": None, "line": None}


def merge_records(by_emulator: dict[str, list[dict]]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for emu, rows in by_emulator.items():
        for row in rows:
            nid = row["nid"]
            slot = grouped.setdefault(nid, {"nid": nid, "emulators": {}})
            slot["emulators"][emu] = {
                "nid": nid,
                "status": row["status"],
                "url": row.get("url"),
                "name": row.get("name"),
                "path": row.get("path"),
                "line": row.get("line"),
                "library": row.get("library"),
                "sha": row.get("sha"),
            }
    merged = []
    for nid, slot in grouped.items():
        entries = {emu: slot["emulators"].get(emu) for emu in EMULATORS}
        emulators = {}
        for emu in EMULATORS:
            row = entries.get(emu)
            if row:
                emulators[emu] = {
                    "status": row["status"],
                    "url": row.get("url"),
                    "name": row.get("name"),
                    "path": row.get("path"),
                    "line": row.get("line"),
                }
            else:
                emulators[emu] = empty_emu()
        item = {
            "nid": nid,
            "name": pick_name(nid, slot["emulators"]),
            "library": pick_library(slot["emulators"]),
            "emulators": emulators,
        }
        merged.append(item)
    merged.sort(key=lambda row: ((row["name"] or "").lower(), row["nid"]))
    return merged


def count_emulator(merged: list[dict], emu: str) -> dict:
    counts = {"implemented": 0, "stub": 0, "unknown": 0, "not_implemented": 0}
    for row in merged:
        status = row["emulators"][emu]["status"]
        counts[status] = counts.get(status, 0) + 1
    present = counts["implemented"] + counts["stub"] + counts["unknown"]
    return {**counts, "total": present}


def update_history(merged: list[dict], shas: dict[str, str | None], path=None) -> list[dict]:
    path = path or HISTORY_PATH
    if path.is_file():
        history = json.loads(path.read_text(encoding="utf-8"))
    else:
        history = []
    today = date.today().isoformat()
    point = {
        "date": today,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha": {emu: shas.get(emu) for emu in EMULATORS},
        "counts": {emu: count_emulator(merged, emu) for emu in EMULATORS},
    }
    history = [item for item in history if item.get("date") != today]
    history.append(point)
    history.sort(key=lambda item: item["date"])
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    return history


def save_nids(merged: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    NIDS_PATH.write_text(json.dumps(merged) + "\n", encoding="utf-8")
