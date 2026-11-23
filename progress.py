"""PS5 NID database pipeline: sync | scan | merge | site | all."""

import argparse
import json
import sys

from nid_db import EMULATORS
from nid_db.merge import merge_records, save_nids, update_history
from nid_db.paths import DATA, SITE, load_config, emulator_dir
from nid_db.scanners import SCANNERS
from nid_db.site import generate_site
from nid_db.sync import collect_shas, head_sha, load_state, sync_all

SCANS_DIR = DATA / "scans"


def run_scan(write: bool = True) -> dict[str, list[dict]]:
    config = load_config()
    state = load_state()
    results = {}
    for name, cfg in config["emulators"].items():
        cfg = dict(cfg)
        cfg["_name"] = name
        repo = emulator_dir(cfg)
        if not (repo / cfg["scan"]).is_dir():
            print(f"[{name}] scan dir missing: {repo / cfg['scan']}", file=sys.stderr)
            results[name] = []
            continue
        sha = head_sha(repo)
        if sha is None and (repo / ".git").exists():
            sha = state.get("emulators", {}).get(name, {}).get("sha")
        scanner = SCANNERS[name]
        kwargs = {k: v for k, v in cfg.items() if k not in {"url", "github", "dir", "fallback_dirs", "_name"}}
        records = scanner(repo, github=cfg["github"], sha=sha, **kwargs)
        results[name] = records
        print(f"[{name}] {len(records)} records @ {sha or 'unknown-sha'}")
        if write:
            SCANS_DIR.mkdir(parents=True, exist_ok=True)
            (SCANS_DIR / f"{name}.json").write_text(
                json.dumps(records) + "\n", encoding="utf-8"
            )
    return results


def load_scans() -> dict[str, list[dict]]:
    scans = {}
    for name in EMULATORS:
        path = SCANS_DIR / f"{name}.json"
        scans[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    return scans


def run_merge(scans: dict[str, list[dict]] | None = None) -> list[dict]:
    scans = scans if scans is not None else load_scans()
    merged = merge_records(scans)
    shas = collect_shas()
    update_history(merged, shas)
    save_nids(merged)
    DATA.mkdir(parents=True, exist_ok=True)
    return merged


def run_site(merged: list[dict] | None = None) -> None:
    merged = merged if merged is not None else json.loads(
        (DATA / "nids.json").read_text(encoding="utf-8")
    )
    generate_site(merged)
    api_count = len(list((SITE / "api").glob("*.json"))) - 1
    print(f"site: {len(merged)} NIDs, {api_count} api files")


def cmd_sync(_args) -> int:
    reports = sync_all()
    for name, info in reports.items():
        print(f"[{name}] sha={info.get('sha')} updated={info.get('updated')} {info.get('reason', '')}")
    return 0


def cmd_scan(args) -> int:
    if not args.skip_sync:
        sync_all()
    scans = run_scan()
    merged = run_merge(scans)
    run_site(merged)
    return 0


def cmd_merge(_args) -> int:
    merged = run_merge()
    run_site(merged)
    return 0


def cmd_site(_args) -> int:
    run_site()
    return 0


def cmd_all(_args) -> int:
    sync_all()
    scans = run_scan()
    merged = run_merge(scans)
    run_site(merged)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PS5 NID database pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="clone/fetch emulator repos, update data/state.json")
    p_scan = sub.add_parser("scan", help="scan sources, merge, update history and site")
    p_scan.add_argument("--skip-sync", action="store_true", help="do not git sync first")
    sub.add_parser("merge", help="merge existing data/scans/*.json")
    sub.add_parser("site", help="regenerate site/ from data/nids.json")
    sub.add_parser("all", help="sync + scan + merge + site")
    args = parser.parse_args(argv)
    return {
        "sync": cmd_sync,
        "scan": cmd_scan,
        "merge": cmd_merge,
        "site": cmd_site,
        "all": cmd_all,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
