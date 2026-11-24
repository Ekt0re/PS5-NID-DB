from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
from pathlib import Path

from nid_db import EMULATORS
from nid_db.paths import HISTORY_PATH, SITE, atomic_write_text, print_progress

STATUS_LABEL = {
    "implemented": "implemented",
    "stub": "stub",
    "unknown": "unknown",
    "not_implemented": "not implemented",
}
STATUS_CLASS = {
    "implemented": "ok",
    "stub": "warn",
    "unknown": "dim",
    "not_implemented": "off",
}
EMU_LABEL = {"anyps5": "AnyPS5", "kyty": "KytyPS5", "sharpemu": "SharpEmu"}


def api_payload(item: dict) -> dict:
    emulators = {}
    for emu in EMULATORS:
        row = item["emulators"].get(emu) or {}
        emulators[emu] = {
            "status": row.get("status", "not_implemented"),
            "url": row.get("url"),
            "name": row.get("name"),
            "path": row.get("path"),
            "line": row.get("line"),
        }
    return {
        "nid": item["nid"],
        "name": item.get("name") or item["nid"],
        "library": item.get("library") or "",
        "emulators": emulators,
    }


def _write_json(path: Path, payload) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def write_api(merged: list[dict], site_dir: Path | None = None) -> None:
    site_dir = site_dir or SITE
    api_dir = site_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)

    index = {}
    items = []
    expected_lower = {"index.json"}
    for item in merged:
        payload = api_payload(item)
        index[item["nid"]] = payload["name"]
        filename = f"{item['nid']}.json"
        expected_lower.add(filename.lower())
        items.append((api_dir / filename, payload))

    total = len(items)
    if total > 0:
        print_progress("api", 0, total)
        max_workers = min(32, (os.cpu_count() or 4) * 4)
        step = max(1, total // 100)
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_write_json, path, payload) for path, payload in items]
            for future in as_completed(futures):
                future.result()
                done += 1
                if done % step == 0 or done == total:
                    print_progress("api", done, total)

    _write_json(api_dir / "index.json", index)

    for existing in api_dir.iterdir():
        if existing.is_file() and existing.name.lower() not in expected_lower:
            try:
                existing.unlink()
            except OSError:
                pass


def write_nids_json(merged: list[dict], site_dir: Path | None = None) -> None:
    site_dir = site_dir or SITE
    site_dir.mkdir(parents=True, exist_ok=True)
    _write_json(site_dir / "nids.json", merged)


def write_history(site_dir: Path | None = None) -> None:
    site_dir = site_dir or SITE
    site_dir.mkdir(parents=True, exist_ok=True)
    if HISTORY_PATH.is_file():
        shutil.copyfile(HISTORY_PATH, site_dir / "history.json")
    else:
        _write_json(site_dir / "history.json", [])


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PS5 NID Database</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: system-ui, sans-serif; margin: 0; background: #0f1420; color: #dde3ee; }
  header { padding: 16px 24px; border-bottom: 1px solid #26304a; }
  h1 { font-size: 20px; margin: 0 0 12px; }
  #search { width: 100%; max-width: 560px; padding: 8px 12px; font-size: 15px;
            background: #1a2236; color: inherit; border: 1px solid #33405e; border-radius: 6px; }
  #legend { font-size: 13px; color: #9aa7c2; margin-top: 8px; }
  main { display: grid; grid-template-columns: minmax(340px, 420px) 1fr; min-height: calc(100vh - 96px); }
  #chart { padding: 16px 24px; border-bottom: 1px solid #26304a; }
  svg { width: 100%; height: 220px; display: block; }
  #list { overflow-y: auto; border-right: 1px solid #26304a; max-height: calc(100vh - 96px); }
  .func { padding: 8px 16px; cursor: pointer; border-bottom: 1px solid #1b2338; }
  .func:hover { background: #1a2236; }
  .func.sel { background: #22304f; }
  .func .lib { color: #7d8db0; font-size: 12px; }
  .func .cnt { float: right; font-size: 12px; color: #9aa7c2; }
  #detail { padding: 16px 24px; overflow-y: auto; max-height: calc(100vh - 96px); }
  #detail h2 { font-size: 18px; margin: 0 0 4px; word-break: break-all; }
  #detail .meta { color: #9aa7c2; font-size: 13px; margin-bottom: 16px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #26304a; font-size: 14px; vertical-align: top; }
  th { color: #9aa7c2; font-weight: 600; }
  .st { font-weight: 600; }
  .st.ok { color: #6fd08c; } .st.warn { color: #e8c46a; }
  .st.dim { color: #8fa3cc; } .st.off { color: #5a6780; }
  a { color: #7db4ff; }
  #empty { color: #7d8db0; padding: 24px; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin: 0 4px 0 12px; }
</style>
</head>
<body>
<header>
  <h1>PS5 NID Database</h1>
  <input id="search" type="search" placeholder="Search NID or function name&hellip;" autocomplete="off">
  <div id="legend"></div>
</header>
<main>
  <div id="chart"></div>
  <div id="list"></div>
  <div id="detail"><div id="empty">Select a function or search a NID.</div></div>
</main>
<script>
const EMULATORS = __EMULATORS__;
const EMU_LABEL = __EMU_LABEL__;
const STATUS_LABEL = {implemented: "implemented", stub: "stub", unknown: "unknown", not_implemented: "not implemented"};
const STATUS_CLASS = {implemented: "ok", stub: "warn", unknown: "dim", not_implemented: "off"};
const COLORS = ["#6fd08c", "#e8c46a", "#7db4ff"];

let NIDS = [];
let HISTORY = [];
let FUNCS = [];
let selected = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function load() {
  [NIDS, HISTORY] = await Promise.all([
    fetch("nids.json").then((r) => r.json()),
    fetch("history.json").then((r) => r.json()).catch(() => []),
  ]);
  FUNCS = functionIndex();
  renderChart();
  renderList("");
}

function renderChart() {
  const el = $("chart");
  if (!HISTORY.length) { el.innerHTML = "<div id='empty'>No history yet.</div>"; return; }
  const W = Math.max(320, el.clientWidth || 800), H = 220, pad = 36;
  const max = Math.max(1, ...HISTORY.map((p) => Math.max(...EMULATORS.map((e) => (p.counts && p.counts[e] && p.counts[e].implemented) || 0))));
  const x = (i) => pad + (i * (W - pad * 2)) / Math.max(1, HISTORY.length - 1);
  const y = (v) => H - 20 - (v * (H - 40)) / max;
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
  svg += `<line x1="${pad}" y1="${H - 20}" x2="${W - pad}" y2="${H - 20}" stroke="#33405e"/>`;
  svg += `<text x="4" y="${y(max)}" fill="#7d8db0" font-size="11">${max}</text>`;
  svg += `<text x="4" y="${H - 24}" fill="#7d8db0" font-size="11">0</text>`;
  EMULATORS.forEach((e, ei) => {
    const pts = HISTORY.map((p, i) => `${x(i).toFixed(1)},${y(((p.counts || {})[e] || {}).implemented || 0).toFixed(1)}`).join(" ");
    svg += `<polyline points="${pts}" fill="none" stroke="${COLORS[ei]}" stroke-width="2"/>`;
  });
  HISTORY.forEach((p, i) => {
    if (i % Math.ceil(HISTORY.length / 8) === 0 || i === HISTORY.length - 1)
      svg += `<text x="${x(i)}" y="${H - 4}" fill="#7d8db0" font-size="10" text-anchor="middle">${p.date.slice(5)}</text>`;
  });
  svg += "</svg>";
  svg += EMULATORS.map((e, i) => `<span class="dot" style="background:${COLORS[i]}"></span>${EMU_LABEL[e]} (implemented)`).join("");
  $("chart").innerHTML = svg;
  $("legend").innerHTML = EMULATORS.map((e, i) => `<span class="dot" style="background:${COLORS[i]}"></span>${EMU_LABEL[e]} (implemented)`).join("");
}

function functionIndex() {
  const map = new Map();
  for (const item of NIDS) {
    const key = item.name || item.nid;
    if (!map.has(key)) map.set(key, { name: key, library: item.library || "", nids: [] });
    map.get(key).nids.push(item);
  }
  return [...map.values()];
}

function renderList(query) {
  const q = (query || "").trim().toLowerCase();
  const items = FUNCS.filter((f) =>
    !q || f.name.toLowerCase().includes(q) || f.nids.some((n) => n.nid.toLowerCase().includes(q)));
  $("list").innerHTML = items.slice(0, 2000).map((f) => `
    <div class="func ${f.name === selected ? "sel" : ""}" data-name="${esc(f.name)}">
      <span class="cnt">${f.nids.length}</span>${esc(f.name)}
      <div class="lib">${esc(f.library)} &middot; ${f.nids.map((n) => esc(n.nid)).join(", ")}</div>
    </div>`).join("") || `<div id="empty">No matches.</div>`;
  $("list").querySelectorAll(".func").forEach((el) =>
    el.addEventListener("click", () => { selected = el.dataset.name; showFunction(selected); renderList($("search").value); }));
}

function showFunction(name) {
  const f = FUNCS.find((x) => x.name === name);
  if (!f) return;
  let rows = "";
  for (const n of f.nids) {
    rows += `<tr><td colspan="4" style="padding-top:14px"><b>NID:</b> <code>${esc(n.nid)}</code>` +
      (n.library ? ` &middot; <b>lib:</b> ${esc(n.library)}` : "") + `</td></tr>`;
    for (const e of EMULATORS) {
      const s = (n.emulators || {})[e] || {};
      const st = s.status || "not_implemented";
      rows += `<tr>
        <td>${EMU_LABEL[e]}</td>
        <td class="st ${STATUS_CLASS[st] || "off"}">${STATUS_LABEL[st] || st}</td>
        <td>${s.name ? esc(s.name) : ""}${s.path ? ` <span style="color:#7d8db0">(${esc(s.path)}${s.line ? ":" + s.line : ""})</span>` : ""}</td>
        <td>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">source</a>` : ""}</td>
      </tr>`;
    }
  }
  $("detail").innerHTML = `
    <h2>${esc(f.name)}</h2>
    <div class="meta">${esc(f.library)} &middot; ${f.nids.length} NID(s)</div>
    <table><tr><th>Emulator</th><th>Status</th><th>Symbol / location</th><th></th></tr>${rows}</table>`;
}

let timer = null;
$("search").addEventListener("input", (e) => {
  clearTimeout(timer);
  timer = setTimeout(() => renderList(e.target.value), 150);
});

load();
</script>
</body>
</html>
"""


def write_index_html(site_dir: Path | None = None) -> None:
    site_dir = site_dir or SITE
    site_dir.mkdir(parents=True, exist_ok=True)
    html = INDEX_HTML.replace("__EMULATORS__", json.dumps(list(EMULATORS)))
    html = html.replace("__EMU_LABEL__", json.dumps(EMU_LABEL))
    (site_dir / "index.html").write_text(html, encoding="utf-8")


def generate_site(merged: list[dict]) -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    write_nids_json(merged)
    write_history()
    write_api(merged)
