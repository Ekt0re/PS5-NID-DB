"use strict";

const CONCURRENCY = 4;
const BATCH_SIZE = 100;
const MAX_ERROR_LOGS = 20;

function emptyEmulators() {
  return {
    anyps5: { status: "not_implemented", url: null, name: null, path: null, line: null },
    kyty: { status: "not_implemented", url: null, name: null, path: null, line: null },
    sharpemu: { status: "not_implemented", url: null, name: null, path: null, line: null },
  };
}

async function fetchOne(baseUrl, nid, fallbackName, stats) {
  const url = new URL(`api/${encodeURIComponent(nid)}.json`, baseUrl).href;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status} (${res.statusText})`);
    const data = await res.json();
    stats.ok++;
    return {
      nid: data.nid || nid,
      name: data.name || fallbackName || nid,
      library: data.library || "",
      emulators: data.emulators || emptyEmulators(),
    };
  } catch (err) {
    stats.err++;
    if (stats.err <= MAX_ERROR_LOGS) {
      console.warn(`[PS5-NID-DB][worker#${stats.id}] Failed ${url}:`, err && err.message ? err.message : err);
    } else if (stats.err === MAX_ERROR_LOGS + 1) {
      console.warn(`[PS5-NID-DB][worker#${stats.id}] Further fetch errors will be summarized at completion.`);
    }
    return {
      nid,
      name: fallbackName || nid,
      library: "",
      emulators: emptyEmulators(),
    };
  }
}

self.addEventListener("message", async (ev) => {
  const { entries, baseUrl, workerId = 0 } = ev.data || {};
  if (!Array.isArray(entries) || entries.length === 0) {
    self.postMessage({ type: "done", workerId, ok: 0, err: 0, elapsedMs: 0 });
    return;
  }

  const t0 = performance.now();
  const stats = { id: workerId, ok: 0, err: 0 };
  console.info(`[PS5-NID-DB][worker#${workerId}] Started (${entries.length} NIDs, concurrency=${CONCURRENCY})`);

  let cursor = 0;
  let batch = [];

  function flush() {
    if (batch.length > 0) {
      self.postMessage({ type: "batch", items: batch });
      batch = [];
    }
  }

  async function run() {
    while (true) {
      const i = cursor++;
      if (i >= entries.length) break;
      const [nid, name] = entries[i];
      const item = await fetchOne(baseUrl, nid, name, stats);
      batch.push(item);
      if (batch.length >= BATCH_SIZE) {
        flush();
      }
    }
  }

  const workers = Array.from({ length: Math.min(CONCURRENCY, entries.length) }, () => run());
  await Promise.all(workers);
  flush();
  const elapsedMs = Math.round(performance.now() - t0);
  console.info(
    `[PS5-NID-DB][worker#${workerId}] Finished in ${elapsedMs}ms (ok=${stats.ok}, err=${stats.err})`
  );
  self.postMessage({ type: "done", workerId, ok: stats.ok, err: stats.err, elapsedMs });
});
