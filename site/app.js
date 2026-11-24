(() => {
  "use strict";

  const EMULATORS = ["anyps5", "kyty", "sharpemu"];
  const EMU_LABEL = { anyps5: "AnyPS5", kyty: "KytyPS5", sharpemu: "SharpEmu" };
  const EMU_SHORT = { anyps5: "A", kyty: "K", sharpemu: "S" };
  const EMU_COLOR = {
    anyps5: "var(--c-anyps5)",
    kyty: "var(--c-kyty)",
    sharpemu: "var(--c-sharpemu)",
  };
  const STATUS_LABEL = {
    implemented: "implemented",
    stub: "stub",
    unknown: "unknown",
    not_implemented: "not implemented",
  };
  const STATUS_CLASS = {
    implemented: "ok",
    stub: "warn",
    unknown: "dim",
    not_implemented: "off",
  };
  const STATUS_RANK = {
    implemented: 3,
    stub: 2,
    unknown: 1,
    not_implemented: 0,
  };

  const ROW_HEIGHT = 60;
  const WORKER_COUNT = Math.min(4, Math.max(2, navigator.hardwareConcurrency || 4));
  const FALLBACK_CONCURRENCY = 16;
  const DB_NAME = "ps5-nid-db";
  const DB_VERSION = 1;

  const LOG_PREFIX = "[PS5-NID-DB]";
  const log = {
    info: (...args) => console.info(LOG_PREFIX, ...args),
    debug: (...args) => console.debug(LOG_PREFIX, ...args),
    warn: (...args) => console.warn(LOG_PREFIX, ...args),
    error: (...args) => console.error(LOG_PREFIX, ...args),
  };

  window.addEventListener("error", (ev) => {
    log.error("Uncaught error:", ev.message, `@ ${ev.filename}:${ev.lineno}:${ev.colno}`, ev.error);
  });
  window.addEventListener("unhandledrejection", (ev) => {
    log.error("Unhandled promise rejection:", ev.reason);
  });

  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const els = {
    progress: $("progress"),
    progressBar: $("progress-bar"),
    search: $("search"),
    theme: $("theme"),
    fLib: $("f-lib"),
    fEmu: $("f-emu"),
    fStatus: $("f-status"),
    reset: $("reset"),
    overviewToggle: $("overview-toggle"),
    overview: $("overview"),
    stats: $("stats"),
    chart: $("chart"),
    legend: $("legend"),
    count: $("count"),
    list: $("list"),
    spacer: $("spacer"),
    rows: $("rows"),
    empty: $("empty"),
    loader: $("loader"),
    loaderTitle: $("loader-title"),
    loaderText: $("loader-text"),
    loaderBar: $("loader-bar"),
    retry: $("retry"),
    detailPane: $("detail-pane"),
    back: $("back"),
    detail: $("detail"),
    meta: $("meta"),
  };

  let NIDS = [];
  const NID_MAP = new Map();
  let HISTORY = [];
  let FUNCS = [];
  const FUNC_MAP = new Map();
  let FILTERED = [];
  let selectedName = null;
  let toastTimer = null;
  let cacheDb = null;
  let dataVersion = "";
  let totalNids = 0;
  let loadedNids = 0;
  let activeWorkers = [];
  const priorityFetches = new Map();
  const knownLibs = new Set();

  function openCacheDb() {
    return new Promise((resolve) => {
      if (!("indexedDB" in window)) {
        log.warn("IndexedDB not supported in this browser; caching disabled.");
        return resolve(null);
      }
      try {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
          log.info(`Upgrading IndexedDB "${DB_NAME}" to v${DB_VERSION}`);
          const db = req.result;
          if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta");
          if (!db.objectStoreNames.contains("nids")) db.createObjectStore("nids", { keyPath: "nid" });
        };
        req.onsuccess = () => {
          log.debug(`IndexedDB "${DB_NAME}" opened`);
          resolve(req.result);
        };
        req.onerror = () => {
          log.warn("IndexedDB open failed:", req.error);
          resolve(null);
        };
      } catch (err) {
        log.warn("IndexedDB exception:", err);
        resolve(null);
      }
    });
  }

  function idbGet(db, storeName, key) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(storeName, "readonly");
        const req = tx.objectStore(storeName).get(key);
        req.onsuccess = () => resolve(req.result ?? null);
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  function idbGetAll(db, storeName) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(storeName, "readonly");
        const req = tx.objectStore(storeName).getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => resolve([]);
      } catch {
        resolve([]);
      }
    });
  }

  function idbPutMeta(db, key, value) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("meta", "readwrite");
        tx.objectStore("meta").put(value, key);
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => resolve(false);
      } catch {
        resolve(false);
      }
    });
  }

  function idbPutBatch(db, items) {
    if (!db || !items.length) return Promise.resolve();
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("nids", "readwrite");
        const store = tx.objectStore("nids");
        for (const item of items) store.put(item);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  function idbClearNids(db) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("nids", "readwrite");
        tx.objectStore("nids").clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  function computeDataVersion(index, historyData) {
    const total = Object.keys(index).length;
    const latest = Array.isArray(historyData) && historyData.length ? historyData[historyData.length - 1] : null;
    const stamp = latest ? latest.generated_at || latest.date || "" : "";
    return `${stamp}|${total}`;
  }

  function initTheme() {
    const saved = localStorage.getItem("theme");
    const theme = saved === "light" || saved === "dark" ? saved : "dark";
    applyTheme(theme);
    els.theme.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      applyTheme(next);
      localStorage.setItem("theme", next);
    });
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) metaTheme.content = theme === "light" ? "#f4f6fb" : "#0b1020";
  }

  function setProgress(ratio) {
    const clamped = Math.max(0, Math.min(1, ratio));
    els.progressBar.style.transform = `scaleX(${clamped})`;
    els.loaderBar.style.transform = `scaleX(${clamped})`;
  }

  function showToast(message) {
    let toast = document.querySelector(".toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "toast";
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.hidden = true;
    }, 1800);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      showToast(`Copied "${text}"`);
    } catch {
      showToast("Copy failed");
    }
  }

  function emptyEmulators() {
    const out = {};
    for (const emu of EMULATORS) {
      out[emu] = { status: "not_implemented", url: null, name: null, path: null, line: null };
    }
    return out;
  }

  function buildInitialIndex(entries, cachedMap) {
    NIDS = new Array(entries.length);
    NID_MAP.clear();
    FUNC_MAP.clear();
    knownLibs.clear();
    loadedNids = 0;

    const pendingEntries = [];

    for (let i = 0; i < entries.length; i++) {
      const [nid, name] = entries[i];
      const cached = cachedMap.get(nid);
      let item;
      if (cached) {
        item = {
          nid,
          name: cached.name || name || nid,
          library: cached.library || "",
          emulators: cached.emulators || emptyEmulators(),
          _loaded: true,
        };
        loadedNids++;
        if (item.library) knownLibs.add(item.library);
      } else {
        item = {
          nid,
          name: name || nid,
          library: "",
          emulators: emptyEmulators(),
          _loaded: false,
        };
        pendingEntries.push([nid, name]);
      }
      NIDS[i] = item;
      NID_MAP.set(nid, item);

      const key = item.name || item.nid;
      let fn = FUNC_MAP.get(key);
      if (!fn) {
        fn = {
          name: key,
          library: item.library || "",
          nids: [],
          emuStatus: {
            anyps5: "not_implemented",
            kyty: "not_implemented",
            sharpemu: "not_implemented",
          },
          search: "",
        };
        FUNC_MAP.set(key, fn);
      }
      if (!fn.library && item.library) fn.library = item.library;
      fn.nids.push(item);

      for (const emu of EMULATORS) {
        const st = (item.emulators[emu] && item.emulators[emu].status) || "not_implemented";
        if ((STATUS_RANK[st] ?? 0) > (STATUS_RANK[fn.emuStatus[emu]] ?? 0)) {
          fn.emuStatus[emu] = st;
        }
      }
    }

    FUNCS = [...FUNC_MAP.values()];
    for (const fn of FUNCS) {
      fn.search = `${fn.name}\0${fn.library}\0${fn.nids.map((n) => n.nid).join("\0")}`.toLowerCase();
    }
    FUNCS.sort((a, b) => a.name.localeCompare(b.name));

    return pendingEntries;
  }

  function mergeLoadedItem(data) {
    const existing = NID_MAP.get(data.nid);
    if (!existing) return false;
    const wasLoaded = existing._loaded;

    existing.name = data.name || existing.name || existing.nid;
    existing.library = data.library || existing.library || "";
    existing.emulators = data.emulators || existing.emulators;
    existing._loaded = true;
    if (!wasLoaded) loadedNids++;

    if (existing.library && !knownLibs.has(existing.library)) {
      knownLibs.add(existing.library);
    }

    const fn = FUNC_MAP.get(existing.name) || FUNC_MAP.get(existing.nid);
    if (fn) {
      if (!fn.library && existing.library) fn.library = existing.library;
      for (const emu of EMULATORS) {
        const st = (existing.emulators[emu] && existing.emulators[emu].status) || "not_implemented";
        if ((STATUS_RANK[st] ?? 0) > (STATUS_RANK[fn.emuStatus[emu]] ?? 0)) {
          fn.emuStatus[emu] = st;
        }
      }
      fn.search = `${fn.name}\0${fn.library}\0${fn.nids.map((n) => n.nid).join("\0")}`.toLowerCase();
    }

    return !wasLoaded;
  }

  function populateLibraries() {
    const current = els.fLib.value;
    const sorted = [...knownLibs].sort((a, b) => a.localeCompare(b));
    els.fLib.innerHTML =
      '<option value="">All libraries</option>' +
      sorted.map((lib) => `<option value="${esc(lib)}">${esc(lib)}</option>`).join("");
    if (current && knownLibs.has(current)) els.fLib.value = current;
  }

  function setControlsEnabled(enabled) {
    els.search.disabled = !enabled;
    els.fLib.disabled = !enabled;
    els.fEmu.disabled = !enabled;
    els.fStatus.disabled = !enabled;
  }

  function applyFilters(preserveScroll = false) {
    const q = els.search.value.trim().toLowerCase();
    const lib = els.fLib.value;
    const emu = els.fEmu.value;
    const status = els.fStatus.value;

    const hasFilter = Boolean(q || lib || emu || status);
    els.reset.hidden = !hasFilter;

    FILTERED = FUNCS.filter((fn) => {
      if (q && !fn.search.includes(q)) return false;
      if (lib && fn.library !== lib && !fn.nids.some((n) => n.library === lib)) return false;
      if (emu && status) {
        if (fn.emuStatus[emu] !== status) return false;
      } else if (emu) {
        if (fn.emuStatus[emu] === "not_implemented") return false;
      } else if (status) {
        if (!EMULATORS.some((e) => fn.emuStatus[e] === status)) return false;
      }
      return true;
    });

    updateCountLabel(hasFilter);
    if (!preserveScroll) els.list.scrollTop = 0;
    renderVisibleRows();
  }

  function updateCountLabel(hasFilter) {
    const syncing = loadedNids < totalNids ? ` · syncing ${Math.round((loadedNids / Math.max(1, totalNids)) * 100)}%` : "";
    if (hasFilter) {
      els.count.textContent = `${FILTERED.length.toLocaleString()} of ${FUNCS.length.toLocaleString()} functions${syncing}`;
    } else {
      els.count.textContent = `${FUNCS.length.toLocaleString()} functions · ${totalNids.toLocaleString()} NIDs${syncing}`;
    }
  }

  function renderVisibleRows() {
    const total = FILTERED.length;
    els.spacer.style.height = `${total * ROW_HEIGHT}px`;
    els.empty.hidden = total > 0;

    if (total === 0) {
      els.rows.innerHTML = "";
      els.rows.style.transform = "translateY(0px)";
      return;
    }

    const scrollTop = els.list.scrollTop;
    const viewHeight = els.list.clientHeight || 600;
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 6);
    const end = Math.min(total, Math.ceil((scrollTop + viewHeight) / ROW_HEIGHT) + 6);

    els.rows.style.transform = `translateY(${start * ROW_HEIGHT}px)`;

    let html = "";
    for (let i = start; i < end; i++) {
      const fn = FILTERED[i];
      const sel = fn.name === selectedName ? " sel" : "";
      const nidText = fn.nids.map((n) => esc(n.nid)).join(", ");
      const libPart = fn.library ? `${esc(fn.library)} &middot; ` : "";
      const chips = EMULATORS.map((e) => {
        const st = fn.emuStatus[e];
        const cls = STATUS_CLASS[st] || "off";
        return `<span class="chip ${cls}" title="${EMU_LABEL[e]}: ${STATUS_LABEL[st] || st}">${EMU_SHORT[e]}</span>`;
      }).join("");
      const badge = fn.nids.length > 1 ? `<span class="badge">${fn.nids.length}</span>` : "";

      html += `
        <div class="row${sel}" data-name="${esc(fn.name)}">
          <div class="row-main">
            <div class="row-name">${esc(fn.name)}</div>
            <div class="row-meta">${libPart}<span class="mono">${nidText}</span></div>
          </div>
          <div class="chips">${chips}</div>
          ${badge}
        </div>`;
    }
    els.rows.innerHTML = html;
  }

  function copyIconSvg() {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
  }

  async function fetchNidPriority(nid, fallbackName) {
    const existing = NID_MAP.get(nid);
    if (existing && existing._loaded) return existing;
    if (priorityFetches.has(nid)) return priorityFetches.get(nid);

    const url = `api/${encodeURIComponent(nid)}.json`;
    log.debug(`Priority fetch started: ${url}`);
    const t0 = performance.now();

    const p = (async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status} (${res.statusText})`);
        const data = await res.json();
        const item = {
          nid: data.nid || nid,
          name: data.name || fallbackName || nid,
          library: data.library || "",
          emulators: data.emulators || emptyEmulators(),
        };
        mergeLoadedItem(item);
        if (cacheDb) await idbPutBatch(cacheDb, [item]);
        log.debug(`Priority fetch OK: ${nid} (${Math.round(performance.now() - t0)}ms)`);
        return item;
      } catch (err) {
        log.warn(`Priority fetch failed for ${url}:`, err && err.message ? err.message : err);
        const fallback = {
          nid,
          name: fallbackName || nid,
          library: "",
          emulators: emptyEmulators(),
        };
        mergeLoadedItem(fallback);
        return fallback;
      } finally {
        priorityFetches.delete(nid);
      }
    })();

    priorityFetches.set(nid, p);
    return p;
  }

  function renderDetailView(fn) {
    const tags = [];
    if (fn.library) tags.push(`<span class="tag">${esc(fn.library)}</span>`);
    tags.push(`<span class="tag">${fn.nids.length} NID${fn.nids.length === 1 ? "" : "s"}</span>`);
    if (fn.nids.some((n) => !n._loaded)) {
      tags.push(`<span class="tag warn">Loading details&hellip;</span>`);
    }

    const cards = fn.nids
      .map((n) => {
        const emuRows = n._loaded
          ? EMULATORS.map((e) => {
              const s = (n.emulators && n.emulators[e]) || {};
              const st = s.status || "not_implemented";
              const stCls = STATUS_CLASS[st] || "off";
              const stLbl = STATUS_LABEL[st] || st;
              const loc = s.path ? `<small>${esc(s.path)}${s.line ? `:${s.line}` : ""}</small>` : "";
              const sym =
                s.name || loc
                  ? `${s.name ? esc(s.name) : ""}${loc}`
                  : `<span style="color:var(--muted)">—</span>`;
              const src = s.url
                ? `<a class="src" href="${esc(s.url)}" target="_blank" rel="noopener">source</a>`
                : `<span class="src"></span>`;

              return `
                <div class="emu-row">
                  <div class="who"><i class="dot" style="background:${EMU_COLOR[e]}"></i><strong>${EMU_LABEL[e]}</strong></div>
                  <div class="st"><span class="pill ${stCls}">${stLbl}</span></div>
                  <div class="sym">${sym}</div>
                  ${src}
                </div>`;
            }).join("")
          : `<div class="emu-row"><div class="sym" style="grid-column:1/-1;color:var(--muted)">Fetching NID details&hellip;</div></div>`;

        return `
          <div class="nid-card">
            <div class="nid-head">
              <code>${esc(n.nid)}</code>
              ${n.library ? `<span class="lib">${esc(n.library)}</span>` : ""}
              <button class="copy" type="button" data-copy="${esc(n.nid)}" aria-label="Copy NID" title="Copy NID">${copyIconSvg()}</button>
            </div>
            ${emuRows}
          </div>`;
      })
      .join("");

    els.detail.innerHTML = `
      <div class="d-title">
        <h2>${esc(fn.name)}</h2>
        <button class="copy" type="button" data-copy="${esc(fn.name)}" aria-label="Copy function name" title="Copy function name">${copyIconSvg()}</button>
      </div>
      <div class="d-tags">${tags.join("")}</div>
      ${cards}`;
  }

  async function selectFunction(name, updateHash = true) {
    const fn = FUNC_MAP.get(name);
    if (!fn) return;
    selectedName = fn.name;

    if (updateHash) {
      history.replaceState(null, "", `#fn=${encodeURIComponent(fn.name)}`);
    }

    renderVisibleRows();
    renderDetailView(fn);
    els.detailPane.classList.add("open");

    const pending = fn.nids.filter((n) => !n._loaded);
    log.info(`Selected "${fn.name}" (${fn.nids.length} NIDs, ${pending.length} pending fetch)`);
    if (pending.length > 0) {
      await Promise.all(pending.map((n) => fetchNidPriority(n.nid, n.name)));
      if (selectedName === fn.name) {
        renderDetailView(fn);
      }
      populateLibraries();
      renderVisibleRows();
    }
  }

  function renderStats() {
    const latest = HISTORY.length ? HISTORY[HISTORY.length - 1] : null;
    const useHistoryCounts = loadedNids < totalNids && latest && latest.counts;
    const total = Math.max(1, totalNids || NIDS.length);

    const kpis = `
      <div class="kpis">
        <div class="kpi"><b>${FUNCS.length.toLocaleString()}</b><span>Functions</span></div>
        <div class="kpi"><b>${totalNids.toLocaleString()}</b><span>NIDs</span></div>
        <div class="kpi"><b>${knownLibs.size.toLocaleString()}</b><span>Libraries</span></div>
      </div>`;

    const emuCards = EMULATORS.map((e) => {
      let c;
      if (useHistoryCounts && latest.counts[e]) {
        c = {
          implemented: latest.counts[e].implemented || 0,
          stub: latest.counts[e].stub || 0,
          unknown: latest.counts[e].unknown || 0,
          not_implemented: latest.counts[e].not_implemented || 0,
        };
      } else {
        c = { implemented: 0, stub: 0, unknown: 0, not_implemented: 0 };
        for (const n of NIDS) {
          const st = (n.emulators && n.emulators[e] && n.emulators[e].status) || "not_implemented";
          c[st] = (c[st] || 0) + 1;
        }
      }
      const pct = ((c.implemented / total) * 100).toFixed(1);
      const wOk = (c.implemented / total) * 100;
      const wWarn = (c.stub / total) * 100;
      const wDim = (c.unknown / total) * 100;
      const wOff = (c.not_implemented / total) * 100;

      return `
        <div class="emu-card">
          <div class="emu-top">
            <i style="background:${EMU_COLOR[e]}"></i>
            <strong>${EMU_LABEL[e]}</strong>
            <span class="pct">${pct}%</span>
          </div>
          <div class="emu-sub">
            ${c.implemented.toLocaleString()} implemented &middot; ${c.stub.toLocaleString()} stub &middot; ${c.unknown.toLocaleString()} unknown
          </div>
          <div class="stack">
            <span class="ok" style="width:${wOk.toFixed(2)}%"></span>
            <span class="warn" style="width:${wWarn.toFixed(2)}%"></span>
            <span class="dim" style="width:${wDim.toFixed(2)}%"></span>
            <span class="off" style="width:${wOff.toFixed(2)}%"></span>
          </div>
        </div>`;
    }).join("");

    els.stats.innerHTML = kpis + emuCards;
  }

  function renderChart() {
    els.legend.innerHTML = EMULATORS.map(
      (e) => `<span><i class="dot" style="background:${EMU_COLOR[e]}"></i>${EMU_LABEL[e]} (implemented)</span>`
    ).join("");

    if (!HISTORY.length) {
      els.chart.innerHTML = `<div style="padding:24px;color:var(--muted);text-align:center">No history data yet.</div>`;
      return;
    }

    const W = Math.max(320, els.chart.clientWidth || 640);
    const H = 190;
    const padL = 44;
    const padR = 14;
    const padT = 14;
    const padB = 26;

    const maxVal = Math.max(
      1,
      ...HISTORY.map((p) =>
        Math.max(...EMULATORS.map((e) => (p.counts && p.counts[e] && p.counts[e].implemented) || 0))
      )
    );

    const x = (i) =>
      HISTORY.length === 1
        ? padL + (W - padL - padR) / 2
        : padL + (i * (W - padL - padR)) / (HISTORY.length - 1);
    const y = (v) => H - padB - (v * (H - padT - padB)) / maxVal;

    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
    for (let t = 0; t <= 4; t++) {
      const val = Math.round((maxVal * t) / 4);
      const yy = y(val).toFixed(1);
      svg += `<line class="grid" x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"/>`;
      svg += `<text class="tick" x="${padL - 6}" y="${yy}" dy="3" text-anchor="end">${val.toLocaleString()}</text>`;
    }

    for (const e of EMULATORS) {
      const pts = HISTORY.map(
        (p, i) => `${x(i).toFixed(1)},${y(((p.counts || {})[e] || {}).implemented || 0).toFixed(1)}`
      ).join(" ");
      if (HISTORY.length === 1) {
        const val = ((HISTORY[0].counts || {})[e] || {}).implemented || 0;
        svg += `<circle cx="${x(0).toFixed(1)}" cy="${y(val).toFixed(1)}" r="4" fill="${EMU_COLOR[e]}"/>`;
      } else {
        svg += `<polyline class="line" points="${pts}" stroke="${EMU_COLOR[e]}"/>`;
      }
    }

    const step = Math.max(1, Math.ceil(HISTORY.length / 6));
    HISTORY.forEach((p, i) => {
      if (i % step === 0 || i === HISTORY.length - 1) {
        svg += `<text class="tick" x="${x(i).toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(
          (p.date || "").slice(5)
        )}</text>`;
      }
    });

    svg += `<line class="cursor" x1="0" y1="${padT}" x2="0" y2="${H - padB}"/>`;
    svg += `<rect class="hit" x="${padL}" y="${padT}" width="${W - padL - padR}" height="${H - padT - padB}"/>`;
    svg += `</svg><div class="tip"></div>`;

    els.chart.innerHTML = svg;

    const svgEl = els.chart.querySelector("svg");
    const cursor = els.chart.querySelector(".cursor");
    const hit = els.chart.querySelector(".hit");
    const tip = els.chart.querySelector(".tip");

    hit.addEventListener("pointermove", (ev) => {
      const rect = svgEl.getBoundingClientRect();
      const relX = ((ev.clientX - rect.left) / rect.width) * W;
      let best = 0;
      let bestDist = Infinity;
      for (let i = 0; i < HISTORY.length; i++) {
        const d = Math.abs(x(i) - relX);
        if (d < bestDist) {
          bestDist = d;
          best = i;
        }
      }
      const pt = HISTORY[best];
      const cx = x(best);
      cursor.setAttribute("x1", cx.toFixed(1));
      cursor.setAttribute("x2", cx.toFixed(1));
      cursor.style.opacity = "1";

      tip.innerHTML =
        `<b>${esc(pt.date)}</b>` +
        EMULATORS.map((e) => {
          const v = ((pt.counts || {})[e] || {}).implemented || 0;
          return `<div><i class="dot" style="background:${EMU_COLOR[e]}"></i><span>${EMU_LABEL[e]}</span><span>${v.toLocaleString()}</span></div>`;
        }).join("");
      tip.style.opacity = "1";

      const tipX = Math.min(rect.width - tip.offsetWidth - 8, Math.max(8, (cx / W) * rect.width + 10));
      tip.style.transform = `translate(${tipX}px, 8px)`;
    });

    hit.addEventListener("pointerleave", () => {
      cursor.style.opacity = "0";
      tip.style.opacity = "0";
    });
  }

  function updateFooterMeta() {
    const latest = HISTORY.length ? HISTORY[HISTORY.length - 1] : null;
    const datePart = latest && latest.date ? `Updated ${latest.date} · ` : "";
    const syncPart =
      loadedNids < totalNids
        ? ` · Syncing ${loadedNids.toLocaleString()}/${totalNids.toLocaleString()}`
        : "";
    els.meta.textContent = `${datePart}${totalNids.toLocaleString()} NIDs · ${FUNCS.length.toLocaleString()} functions${syncPart}`;
  }

  function applyHashSelection() {
    const hash = location.hash;
    if (!hash) return;
    if (hash.startsWith("#fn=")) {
      const name = decodeURIComponent(hash.slice(4));
      selectFunction(name, false);
    } else if (hash.startsWith("#nid=")) {
      const nid = decodeURIComponent(hash.slice(5));
      const item = NID_MAP.get(nid);
      if (item) selectFunction(item.name, false);
    }
  }

  function stopWorkers() {
    for (const w of activeWorkers) {
      try {
        w.terminate();
      } catch {
        // ignore
      }
    }
    activeWorkers = [];
  }

  function startBackgroundSync(pendingEntries) {
    stopWorkers();
    if (pendingEntries.length === 0) {
      log.info(`All ${totalNids} NIDs already loaded from cache. Zero network requests needed.`);
      els.progress.style.opacity = "0";
      if (cacheDb) idbPutMeta(cacheDb, "state", { version: dataVersion, completed: true });
      return;
    }

    const syncStart = performance.now();
    let lastLoggedPct = -1;
    let totalOk = 0;
    let totalErr = 0;
    log.info(`Starting background sync for ${pendingEntries.length} pending NIDs...`);

    els.progress.style.opacity = "1";
    setProgress(loadedNids / Math.max(1, totalNids));

    let uiTimer = null;
    const scheduleUiRefresh = () => {
      const pct = Math.floor((loadedNids / Math.max(1, totalNids)) * 10) * 10;
      if (pct > lastLoggedPct && pct < 100) {
        lastLoggedPct = pct;
        log.info(`Background sync progress: ${loadedNids}/${totalNids} (${pct}%)`);
      }
      if (uiTimer) return;
      uiTimer = setTimeout(() => {
        uiTimer = null;
        setProgress(loadedNids / Math.max(1, totalNids));
        const hasFilter = Boolean(els.search.value.trim() || els.fLib.value || els.fEmu.value || els.fStatus.value);
        updateCountLabel(hasFilter);
        updateFooterMeta();
        populateLibraries();
        renderVisibleRows();
        if (!els.overview.hidden) renderStats();
      }, 250);
    };

    const finishSync = async () => {
      if (uiTimer) {
        clearTimeout(uiTimer);
        uiTimer = null;
      }
      if (cacheDb) await idbPutMeta(cacheDb, "state", { version: dataVersion, completed: true });
      setProgress(1);
      setTimeout(() => {
        els.progress.style.opacity = "0";
      }, 300);
      populateLibraries();
      applyFilters(true);
      renderStats();
      updateFooterMeta();
      const elapsed = Math.round(performance.now() - syncStart);
      log.info(
        `Background sync complete in ${elapsed}ms (total=${totalNids}, ok=${totalOk}, err=${totalErr}, libs=${knownLibs.size})`
      );
    };

    const handleBatch = async (items) => {
      for (const item of items) {
        mergeLoadedItem(item);
      }
      if (cacheDb) await idbPutBatch(cacheDb, items);
      scheduleUiRefresh();
    };

    if (typeof Worker !== "undefined") {
      const count = Math.min(WORKER_COUNT, pendingEntries.length);
      const chunks = Array.from({ length: count }, () => []);
      for (let i = 0; i < pendingEntries.length; i++) {
        chunks[i % count].push(pendingEntries[i]);
      }

      let remainingWorkers = count;
      const baseUrl = location.href;
      log.info(`Spawning ${count} Web Workers (baseUrl=${baseUrl})`);

      chunks.forEach((chunk, idx) => {
        const w = new Worker("worker.js");
        activeWorkers.push(w);
        w.addEventListener("message", async (ev) => {
          const msg = ev.data || {};
          if (msg.type === "batch" && Array.isArray(msg.items)) {
            await handleBatch(msg.items);
          } else if (msg.type === "done") {
            totalOk += msg.ok || 0;
            totalErr += msg.err || 0;
            w.terminate();
            remainingWorkers--;
            if (remainingWorkers === 0) {
              activeWorkers = [];
              await finishSync();
            }
          }
        });
        w.addEventListener("error", async (ev) => {
          log.error(`Web Worker #${idx} error:`, ev.message || ev);
          w.terminate();
          remainingWorkers--;
          if (remainingWorkers === 0) {
            activeWorkers = [];
            await finishSync();
          }
        });
        w.postMessage({ entries: chunk, baseUrl, workerId: idx });
      });
    } else {
      log.warn("Web Workers unavailable; falling back to main-thread async pool.");
      // Fallback if Web Workers are unavailable
      let cursor = 0;
      const runFallback = async () => {
        while (true) {
          const i = cursor++;
          if (i >= pendingEntries.length) break;
          const [nid, name] = pendingEntries[i];
          await fetchNidPriority(nid, name);
          totalOk++;
          scheduleUiRefresh();
        }
      };
      Promise.all(
        Array.from({ length: Math.min(FALLBACK_CONCURRENCY, pendingEntries.length) }, () => runFallback())
      ).then(finishSync);
    }
  }

  async function load() {
    stopWorkers();
    const loadStart = performance.now();
    log.info(`Initializing app @ ${location.href} (workers=${WORKER_COUNT})`);

    els.loader.hidden = false;
    els.loader.classList.remove("error");
    els.retry.hidden = true;
    els.loaderTitle.textContent = "Loading NID index";
    els.loaderText.textContent = "Fetching index…";
    els.progress.style.opacity = "1";
    setProgress(0);
    setControlsEnabled(false);

    try {
      const [indexRes, historyData, db] = await Promise.all([
        fetch("api/index.json", { cache: "no-cache" }).then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status} (${r.statusText}) loading api/index.json`);
          return r.json();
        }),
        fetch("history.json", { cache: "no-cache" })
          .then((r) => {
            if (!r.ok) log.warn(`history.json returned HTTP ${r.status}`);
            return r.ok ? r.json() : [];
          })
          .catch((err) => {
            log.warn("history.json fetch failed:", err);
            return [];
          }),
        openCacheDb(),
      ]);

      cacheDb = db;
      HISTORY = Array.isArray(historyData) ? historyData : [];
      const entries = Object.entries(indexRes);
      totalNids = entries.length;
      dataVersion = computeDataVersion(indexRes, HISTORY);
      log.info(
        `Index loaded in ${Math.round(performance.now() - loadStart)}ms: ${totalNids} NIDs, ${HISTORY.length} history points, version="${dataVersion}"`
      );

      const cachedMap = new Map();
      if (cacheDb) {
        const meta = await idbGet(cacheDb, "meta", "state");
        if (meta && meta.version === dataVersion) {
          const cached = await idbGetAll(cacheDb, "nids");
          for (const item of cached) {
            if (item && item.nid) cachedMap.set(item.nid, item);
          }
          log.info(`Cache hit: ${cachedMap.size}/${totalNids} NIDs restored from IndexedDB (completed=${Boolean(meta.completed)})`);
        } else {
          log.info(`Cache miss (stored="${meta ? meta.version : "none"}", current="${dataVersion}"); clearing old cache.`);
          await idbClearNids(cacheDb);
          await idbPutMeta(cacheDb, "state", { version: dataVersion, completed: false });
        }
      }

      const pendingEntries = buildInitialIndex(entries, cachedMap);
      log.info(
        `Initial UI ready in ${Math.round(performance.now() - loadStart)}ms: ${FUNCS.length} functions, ${cachedMap.size} cached, ${pendingEntries.length} pending`
      );

      // Show UI immediately!
      populateLibraries();
      setControlsEnabled(true);
      els.loader.hidden = true;

      renderStats();
      renderChart();
      updateFooterMeta();
      applyFilters();
      applyHashSelection();

      // Load remaining NIDs in background across multiple worker threads
      startBackgroundSync(pendingEntries);
    } catch (err) {
      log.error("Fatal initialization error:", err);
      els.loader.classList.add("error");
      els.loaderTitle.textContent = "Failed to load data";
      els.loaderText.textContent = err && err.message ? err.message : "Network error";
      els.retry.hidden = false;
      els.count.textContent = "Error";
    }
  }

  function bindEvents() {
    let searchTimer = null;
    els.search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => applyFilters(false), 120);
    });

    els.fLib.addEventListener("change", () => applyFilters(false));
    els.fEmu.addEventListener("change", () => applyFilters(false));
    els.fStatus.addEventListener("change", () => applyFilters(false));

    els.reset.addEventListener("click", () => {
      els.search.value = "";
      els.fLib.value = "";
      els.fEmu.value = "";
      els.fStatus.value = "";
      applyFilters(false);
    });

    els.overviewToggle.addEventListener("click", () => {
      const open = els.overview.hidden;
      els.overview.hidden = !open;
      els.overviewToggle.setAttribute("aria-expanded", String(open));
      if (open) {
        renderStats();
        renderChart();
      }
    });

    els.list.addEventListener("scroll", () => {
      requestAnimationFrame(renderVisibleRows);
    });

    els.rows.addEventListener("click", (ev) => {
      const row = ev.target.closest(".row");
      if (row && row.dataset.name) {
        selectFunction(row.dataset.name);
      }
    });

    els.detail.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".copy");
      if (btn && btn.dataset.copy) {
        copyText(btn.dataset.copy);
      }
    });

    els.back.addEventListener("click", () => {
      els.detailPane.classList.remove("open");
    });

    els.retry.addEventListener("click", load);

    window.addEventListener("resize", () => {
      renderVisibleRows();
      if (!els.overview.hidden) renderChart();
    });

    document.addEventListener("keydown", (ev) => {
      const tag = (ev.target && ev.target.tagName) || "";
      const typing = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
      if (ev.key === "/" && !typing && !els.search.disabled) {
        ev.preventDefault();
        els.search.focus();
      } else if (ev.key === "Escape" && document.activeElement === els.search) {
        els.search.blur();
      }
    });
  }

  initTheme();
  bindEvents();
  load();
})();
