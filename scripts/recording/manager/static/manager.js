/*
 * The Recording Manager's page. Vanilla, no build step, no framework.
 *
 * Two rules run through all of it.
 *
 * ONE: every number is rendered through `num()`, which uses a proper minus sign
 * (U+2212) and a monospace class, so columns align digit-for-digit. A hyphen
 * breaks tabular alignment, and misread numbers are the failure this interface
 * exists to avoid.
 *
 * TWO: a source's status is never collapsed into a boolean. The server sends a
 * `liveness` of `live`, `as_of`, `unreachable` or `none`, and each renders
 * differently, because they are four different qualities of knowledge. `none` is
 * NOT an error state and is not styled as one: a standalone node with no live
 * status is a node working exactly as designed.
 */

const MINUS = "−";

/* ------------------------------------------------------------- helpers --- */

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, String(value));
  }
  for (const child of children || []) {
    if (child === null || child === undefined) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function num(value, digits) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const fixed = Number(value).toFixed(digits === undefined ? 1 : digits);
  return fixed.startsWith("-") ? MINUS + fixed.slice(1) : fixed;
}

function bytes(value) {
  if (!value) return "0 MB";
  if (value >= 1e9) return num(value / 1e9, 2) + " GB";
  return num(value / 1e6, 0) + " MB";
}

function ago(seconds) {
  if (seconds === null || seconds === undefined) return "never";
  if (seconds < 90) return num(seconds, 0) + "s ago";
  if (seconds < 5400) return num(seconds / 60, 0) + " min ago";
  if (seconds < 172800) return num(seconds / 3600, 1) + " h ago";
  return num(seconds / 86400, 1) + " days ago";
}

async function get(path) {
  const response = await fetch(path);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || ("HTTP " + response.status));
  return body;
}

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || JSON.stringify(body, null, 2));
  return body;
}

function stamp(node, text) {
  node.textContent = text;
}

/* ---------------------------------------------------------------- tabs --- */

const PANES = ["sources", "coverage", "gaps", "import", "create"];
const LOADED = {};

function show(name) {
  for (const pane of PANES) {
    const tab = document.getElementById("tab-" + pane);
    const section = document.getElementById("pane-" + pane);
    const selected = pane === name;
    tab.setAttribute("aria-selected", selected ? "true" : "false");
    section.hidden = !selected;
  }
  if (!LOADED[name]) {
    LOADED[name] = true;
    if (name === "sources") loadSources(false);
    if (name === "coverage") loadCoverage();
    if (name === "gaps") loadGaps();
    if (name === "import") loadPullOptions();
  }
}

for (const pane of PANES) {
  document.getElementById("tab-" + pane).addEventListener("click", () => show(pane));
}

/* ------------------------------------------------------------- sources --- */

function livenessCell(source) {
  const words = {
    live: "recording",
    as_of: "reachable",
    unreachable: "not reachable",
    none: "no live status",
  };
  return el("span", { class: "liveness", "data-state": source.liveness }, [
    el("span", { text: words[source.liveness] || source.liveness }),
    el("span", { class: "detail", text: source.detail || "" }),
  ]);
}

function knownAs(source) {
  /*
   * What we know, and WHEN we knew it. A server node's row says "checked 4 min
   * ago" rather than just showing a state, because a check from an hour ago is a
   * much weaker claim than one from a minute ago and the difference has to be on
   * the screen rather than in somebody's memory.
   */
  if (source.kind === "standalone") {
    const dates = (source.last_import_dates || []);
    return el("span", { class: "detail" }, [
      source.last_import
        ? "last import " + source.last_import + (dates.length
            ? " · covering " + dates[0] + (dates.length > 1 ? " to " + dates[dates.length - 1] : "")
            : " · covering nothing that parsed")
        : "never imported",
    ]);
  }
  if (source.kind === "master") {
    const status = source.status || {};
    return el("span", { class: "detail" }, [
      "last line " + ago(status.archive_age_s) +
        " · heartbeat " + ago(status.heartbeat_age_s) +
        (status.free_bytes ? " · " + bytes(status.free_bytes) + " free" : ""),
    ]);
  }
  return el("span", { class: "detail" }, [
    source.checked_at ? "checked at " + source.checked_at : "never checked",
  ]);
}

function renderSources(data) {
  const body = document.getElementById("sources-body");
  body.textContent = "";
  stamp(document.getElementById("sources-when"),
    "read " + data.checked_at + (data.live_check_performed ? " · server nodes checked over SSH" : ""));

  if (!data.sources.length) {
    /* The empty state is the main state. Say what the system knows, not "none". */
    body.appendChild(el("p", { class: "empty" }, [
      el("strong", { text: "No sources are registered yet." }),
      " The registry at ",
      el("code", { text: "scripts/recording/sources.yaml" }),
      " is empty or missing. Add this machine to it by hand, or use Create node to " +
      "build a package for another machine — registering it here is part of that.",
    ]));
    return;
  }

  const table = el("table", {}, [
    el("thead", {}, [el("tr", {}, [
      el("th", { text: "Source" }),
      el("th", { text: "Kind" }),
      el("th", { text: "Status" }),
      el("th", { text: "What is known" }),
      el("th", { class: "num", text: "Archive" }),
    ])]),
  ]);
  const tbody = el("tbody", {}, []);
  for (const source of data.sources) {
    const status = source.status || {};
    tbody.appendChild(el("tr", {}, [
      el("td", {}, [el("span", { class: "mono", text: source.id })]),
      el("td", {}, [el("span", { class: "kind", text: source.kind })]),
      el("td", {}, [livenessCell(source)]),
      el("td", {}, [knownAs(source)]),
      el("td", { class: "num", text: status.size_bytes ? bytes(status.size_bytes) : "—" }),
    ]));
  }
  table.appendChild(tbody);
  body.appendChild(table);
}

async function loadSources(check) {
  const body = document.getElementById("sources-body");
  body.textContent = check ? "Checking over SSH — this takes a few seconds per node …" : "Loading …";
  try {
    renderSources(await get("/api/sources" + (check ? "?check=true" : "")));
  } catch (error) {
    body.textContent = "";
    body.appendChild(el("p", { class: "warn", text: String(error.message || error) }));
  }
}

document.getElementById("sources-refresh").addEventListener("click", () => loadSources(false));
document.getElementById("sources-check").addEventListener("click", () => loadSources(true));

/* ------------------------------------------------------------ coverage --- */

function fillBand(hours) {
  /* Four steps, not a continuous ramp: a cell is "nothing", "a little", "most of
     a day" or "a full day", and a reader should not have to judge a shade. */
  if (!hours) return "0";
  if (hours < 6) return "1";
  if (hours < 18) return "2";
  if (hours < 23.5) return "3";
  return "4";
}

function renderCoverage(data) {
  const body = document.getElementById("coverage-body");
  body.textContent = "";
  stamp(document.getElementById("coverage-when"),
    data.file_count + " files in " + data.archive_dir);

  if (!data.dates.length) {
    body.appendChild(el("p", { class: "empty" }, [
      el("strong", { text: "No dated archive files found." }),
      " Nothing in " + data.archive_dir + " carries a UTC date in its name, so there " +
      "is nothing to lay out by day. If the recorder has been running, check that it " +
      "is writing where this manager is looking.",
    ]));
    return;
  }

  const head = el("tr", {}, [el("th", { text: "Source" })]);
  for (const date of data.dates) head.appendChild(el("th", { class: "date", text: date }));
  head.appendChild(el("th", { class: "num", text: "Total" }));

  const tbody = el("tbody", {}, []);
  for (const source of data.sources) {
    const row = el("tr", {}, [el("td", {}, [el("span", { class: "mono", text: source })])]);
    let total = 0;
    for (const date of data.dates) {
      const hours = (data.cells[source] || {})[date] || 0;
      total += hours;
      row.appendChild(el("td", {
        class: "cell",
        "data-fill": fillBand(hours),
        title: source + " · " + date + " · " + num(hours, 2) + " h",
        text: hours ? num(hours, 1) : "·",
      }, []));
    }
    row.appendChild(el("td", { class: "num", text: num(total, 1) + " h" }));
    tbody.appendChild(row);
  }

  const wrap = el("div", { class: "grid-scroll" }, [
    el("table", { class: "grid" }, [el("thead", {}, [head]), tbody]),
  ]);
  body.appendChild(wrap);
  body.appendChild(el("p", { class: "detail" }, [
    "Total across every source: " + num(data.total_hours, 1) + " hours. A cell shows " +
    "hours captured, so 24.0 is a whole day and a blank cell is a day that source " +
    "recorded nothing at all.",
  ]));
  if (data.undated && data.undated.length) {
    body.appendChild(el("p", { class: "note" }, [
      data.undated.length + " file(s) carry no readable date and are not in the grid: " +
      data.undated.slice(0, 6).join(", ") + (data.undated.length > 6 ? " …" : ""),
    ]));
  }
}

async function loadCoverage() {
  const body = document.getElementById("coverage-body");
  body.textContent = "Measuring the archive … the first run reads every file, later ones are cached.";
  try {
    renderCoverage(await get("/api/coverage"));
  } catch (error) {
    body.textContent = "";
    body.appendChild(el("p", { class: "warn", text: String(error.message || error) }));
  }
}

document.getElementById("coverage-refresh").addEventListener("click", loadCoverage);

/* ---------------------------------------------------------------- gaps --- */

function renderGaps(data) {
  const body = document.getElementById("gaps-body");
  body.textContent = "";
  stamp(document.getElementById("gaps-when"), data.dates_examined + " days examined");

  if (!data.dates_examined) {
    body.appendChild(el("p", { class: "empty" }, [
      el("strong", { text: "Nothing to examine yet." }),
      " There are no dated files in the archive, so there is no span to look for " +
      "holes in.",
    ]));
    return;
  }

  if (!data.uncovered.length) {
    body.appendChild(el("p", { class: "empty" }, [
      el("strong", { text: "Every day in the span is covered." }),
      " Across " + data.dates_examined + " days, no date is missing from every source. " +
      "That is the reading this screen shows most of the time and it is the one you " +
      "want.",
    ]));
  } else {
    body.appendChild(el("h2", { text: "Covered by nothing" }));
    body.appendChild(el("p", { class: "warn" }, [
      data.uncovered.length + " of " + data.dates_examined + " days have no recording " +
      "from any source. Order book and spread for those hours do not exist anywhere " +
      "and cannot be recovered.",
    ]));
    const list = el("ul", {}, []);
    for (const date of data.uncovered) {
      list.appendChild(el("li", {}, [el("span", { class: "mono", text: date })]));
    }
    body.appendChild(list);
  }

  body.appendChild(el("h2", { text: "Covered by one source only" }));
  if (!data.single_source.length) {
    body.appendChild(el("p", { class: "empty" }, [
      "None. Every covered day has at least two sources, so every day has a second " +
      "observation to check the first against.",
    ]));
  } else {
    body.appendChild(el("p", { class: "note" }, [
      "Not a failure — these days are recorded. But there is no second observation " +
      "for them, so a dropped subscription or a bad feed on one of these days cannot " +
      "be detected, then or ever.",
    ]));
    const table = el("table", {}, [
      el("thead", {}, [el("tr", {}, [
        el("th", { text: "Date" }),
        el("th", { text: "Only source" }),
        el("th", { class: "num", text: "Hours" }),
      ])]),
    ]);
    const tbody = el("tbody", {}, []);
    for (const item of data.single_source) {
      tbody.appendChild(el("tr", {}, [
        el("td", {}, [el("span", { class: "mono", text: item.date })]),
        el("td", {}, [el("span", { class: "mono", text: item.source_id })]),
        el("td", { class: "num", text: num(item.hours, 1) }),
      ]));
    }
    table.appendChild(tbody);
    body.appendChild(table);
  }

  if (data.multiple_sources.length) {
    body.appendChild(el("h2", { text: "Covered by two or more" }));
    body.appendChild(el("p", { class: "empty" }, [
      data.multiple_sources.length + " day(s) have more than one source. That is the " +
      "good case: the difference between two independent observations of one market " +
      "is the only measurement there is of what a single recorder misses.",
    ]));
  }
}

async function loadGaps() {
  const body = document.getElementById("gaps-body");
  body.textContent = "Measuring the archive …";
  try {
    renderGaps(await get("/api/gaps"));
  } catch (error) {
    body.textContent = "";
    body.appendChild(el("p", { class: "warn", text: String(error.message || error) }));
  }
}

document.getElementById("gaps-refresh").addEventListener("click", loadGaps);

/* -------------------------------------------------------------- import --- */

async function loadPullOptions() {
  const select = document.getElementById("pull-source");
  select.textContent = "";
  try {
    const data = await get("/api/sources");
    const servers = data.sources.filter((source) => source.kind === "server");
    if (!servers.length) {
      select.appendChild(el("option", { value: "", text: "no server nodes registered" }));
      select.disabled = true;
      document.getElementById("pull-dry").disabled = true;
      document.getElementById("pull-go").disabled = true;
      return;
    }
    for (const source of servers) {
      select.appendChild(el("option", { value: source.id, text: source.id + " — " + (source.ssh_host || "no host") }));
    }
  } catch (error) {
    select.appendChild(el("option", { value: "", text: String(error.message || error) }));
  }
}

function describeMerge(report) {
  const lines = [];
  lines.push((report.dry_run ? "DRY RUN — nothing was copied" : "Merged into " + report.archive_dir));
  lines.push("");
  lines.push(report.merged + " merged, " + report.collisions + " name collisions, " + report.refused + " refused");
  for (const file of report.files || []) {
    lines.push("  [" + file.state + "] " + file.name + " — " + file.detail);
    if (file.note) lines.push("        note: " + file.note);
  }
  if ((report.overlaps || []).length) {
    lines.push("");
    lines.push(report.overlaps.length + " overlapping period(s) — two sources covering one span.");
    lines.push("Both copies are kept. This is an independent observation of one market,");
    lines.push("and the difference between them is the only check there is on a bad feed.");
    for (const overlap of report.overlaps) {
      lines.push("  " + overlap.left_source + " and " + overlap.right_source +
        " both cover " + overlap.from + " to " + overlap.to +
        " (" + num(overlap.hours, 1) + " h)");
      lines.push("      " + overlap.left);
      lines.push("      " + overlap.right);
    }
  } else {
    lines.push("");
    lines.push("No overlapping coverage: every period is covered by at most one source.");
  }
  return lines.join("\n");
}

async function runImport(path, payload, describe) {
  const output = document.getElementById("import-output");
  output.textContent = "Working …";
  try {
    const data = await post(path, payload);
    output.textContent = describe(data);
    output.classList.remove("flash");
    void output.offsetWidth;
    output.classList.add("flash");
    LOADED.coverage = false;
    LOADED.gaps = false;
  } catch (error) {
    output.textContent = String(error.message || error);
  }
}

document.getElementById("pull-dry").addEventListener("click", () => {
  const source = document.getElementById("pull-source").value;
  runImport("/api/import/pull", { source_id: source, dry_run: true }, (data) =>
    [
      "Node " + data.source_id + " at " + data.remote_dir,
      data.remote_files + " files on the node, " + data.already_held + " already held here",
      data.skipped_today.length
        ? "Skipped (still being written to on the node): " + data.skipped_today.join(", ")
        : "Nothing skipped for being today's file.",
      "",
      describeMerge(data.merge),
    ].join("\n"));
});

document.getElementById("pull-go").addEventListener("click", () => {
  const source = document.getElementById("pull-source").value;
  runImport("/api/import/pull", { source_id: source, dry_run: false }, (data) =>
    [
      "Node " + data.source_id + " at " + data.remote_dir,
      "Transferred " + data.transferred.length + " file(s); " + data.failed.length + " failed",
      data.skipped_today.length ? "Skipped today's file: " + data.skipped_today.join(", ") : "",
      "",
      describeMerge(data.merge),
    ].filter(Boolean).join("\n"));
});

document.getElementById("inbox-dry").addEventListener("click", () => {
  runImport("/api/import/inbox", { dry_run: true }, (data) =>
    ["Inbox " + data.inbox, "Staged " + data.copied.length + " file(s)", "", describeMerge(data.merge)].join("\n"));
});

document.getElementById("inbox-go").addEventListener("click", () => {
  runImport("/api/import/inbox", { dry_run: false }, (data) =>
    ["Inbox " + data.inbox, "Staged " + data.copied.length + " file(s)", "", describeMerge(data.merge)].join("\n"));
});

/* --------------------------------------------------------- create node --- */

async function createNode(kind) {
  const output = document.getElementById("create-output");
  const payload = {
    source_id: document.getElementById("node-id").value.trim(),
    kind: kind,
    archive_dir: document.getElementById("node-archive").value.trim() || "data/raw",
  };
  if (!payload.source_id) {
    output.textContent = "Give the node a source id first. It goes into every filename " +
      "the machine writes and cannot be changed once it has recorded anything.";
    return;
  }
  if (kind === "server") {
    payload.ssh_host = document.getElementById("node-host").value.trim();
    payload.remote_archive_dir = document.getElementById("node-remote").value.trim() || null;
    if (!payload.ssh_host) {
      output.textContent = "A server node needs an SSH host — that is the whole difference " +
        "between it and a standalone node. Without one, create a standalone node instead.";
      return;
    }
  }
  output.textContent = "Building …";
  try {
    const data = await post("/api/nodes", payload);
    const lines = [
      "Wrote " + data.path,
      "",
      "Files:",
      ...data.files.map((name) => "  " + name),
      "",
      "Next:",
      ...data.next_steps.map((step, index) => "  " + (index + 1) + ". " + step),
    ];
    if (data.public_key_from) {
      lines.push("", "The public key came from " + data.public_key_from + ".");
      lines.push("Its private half stays on this machine and was never read by this process.");
    }
    output.textContent = lines.join("\n");
    LOADED.sources = false;
    loadPullOptions();
  } catch (error) {
    output.textContent = String(error.message || error);
  }
}

document.getElementById("create-server").addEventListener("click", () => createNode("server"));
document.getElementById("create-standalone").addEventListener("click", () => createNode("standalone"));

/* ---------------------------------------------------------------- boot --- */

get("/api/health").then((health) => {
  stamp(document.getElementById("where"),
    health.archive + (health.ssh_available ? "" : " · ssh not on PATH, so Pull cannot run"));
}).catch(() => {
  stamp(document.getElementById("where"), "could not read /api/health");
});

show("sources");
