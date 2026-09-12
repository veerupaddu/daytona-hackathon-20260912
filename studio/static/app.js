const healthEl = document.getElementById("health");
const form = document.getElementById("prompt-form");
const promptEl = document.getElementById("prompt");
const runBtn = document.getElementById("run-btn");
const statusEl = document.getElementById("status");

function setStep(step, state, label) {
  document.querySelectorAll(`[data-step="${step}"]`).forEach((el) => {
    el.classList.remove("active", "done", "error");
    if (state) el.classList.add(state);
  });
  const stateEl = document.getElementById(`state-${step}`);
  if (stateEl) {
    stateEl.textContent = label;
    stateEl.className = "step-state";
    if (state === "active") stateEl.classList.add("running");
    if (state === "done") stateEl.classList.add("ok");
    if (state === "error") stateEl.classList.add("bad");
  }
  document.querySelectorAll(".rail-arrow").forEach((arrow) => {
    const after = Number(arrow.dataset.after || 0);
    const prev = document.querySelector(`.rail-item[data-step="${after}"]`);
    arrow.classList.toggle("done", Boolean(prev && prev.classList.contains("done")));
  });
}

function resetSteps() {
  setStep(1, "", "Waiting");
  setStep(2, "", "Waiting");
  setStep(3, "", "Waiting");
  setStep(4, "", "Waiting");
  document.getElementById("out-prompt").textContent = "Your question will appear here.";
  document.getElementById("out-nosana").textContent = "GPT-OSS will write a Python script here.";
  document.getElementById("out-code").textContent = "Sandbox source will appear here.";
  document.getElementById("out-daytona").textContent = "Printed result will appear here.";
  document.getElementById("out-summary").textContent =
    "After a run, Nosana reads stored logs and writes an operator summary here.";
  document.getElementById("nosana-ms").textContent = "";
  document.getElementById("daytona-ms").textContent = "";
  document.getElementById("summary-ms").textContent = "";
}

function renderLinks(containerId, links) {
  const nav = document.getElementById(containerId);
  nav.innerHTML = "";
  (links || []).forEach((item) => {
    const a = document.createElement("a");
    a.href = item.url;
    a.target = "_blank";
    a.rel = "noreferrer";
    a.innerHTML = `<strong>${item.label}</strong><small>${item.detail || item.url}</small>`;
    nav.appendChild(a);
  });
}

function escapeText(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function executedText(run, kind) {
  if (kind === "prompt") return String(run.prompt || "").trim();
  if (kind === "nosana") {
    return String(run.nosana_error || run.code || run.nosana_reply || "").trim();
  }
  return String(run.daytona_error || run.daytona_output || "").trim();
}

function groupKeyMessages(latest) {
  return {
    prompt: executedText(latest, "prompt") ? [executedText(latest, "prompt")] : [],
    nosana: executedText(latest, "nosana") ? [executedText(latest, "nosana")] : [],
    daytona: executedText(latest, "daytona") ? [executedText(latest, "daytona")] : [],
  };
}

function renderAnalysis(data) {
  const nosana = Number(data.avg_nosana_ms || 0);
  const daytona = Number(data.avg_daytona_ms || 0);
  const total = Number(data.total_pipeline_ms || nosana + daytona);
  const max = Math.max(nosana, daytona, 1);
  document.getElementById("stat-runs").textContent = String(data.run_count || 0);
  document.getElementById("stat-nosana").textContent = `${nosana} ms`;
  document.getElementById("stat-daytona").textContent = `${daytona} ms`;
  document.getElementById("stat-total").textContent = `${total} ms`;
  document.getElementById("stat-nosana-fail").textContent =
    `${data.nosana_failures || 0} failures`;
  document.getElementById("stat-daytona-fail").textContent =
    `${data.daytona_failures || 0} failures`;
  document.getElementById("meter-nosana").style.width = `${(nosana / max) * 100}%`;
  document.getElementById("meter-daytona").style.width = `${(daytona / max) * 100}%`;
  const latest = (data.runs && data.runs[0]) || {};
  if (latest.prompt) showTurn(latest);
  const groups = groupKeyMessages(latest);
  document.getElementById("message-groups").innerHTML = [
    ["prompt", "Prompt", groups.prompt],
    ["nosana", "Nosana code", groups.nosana],
    ["daytona", "Daytona output", groups.daytona],
  ]
    .map(([kind, title, items]) => {
      const body = items.length ? items.map((item) => escapeText(item)).join("\n\n") : "No logs yet.";
      return `<article class="message-card ${kind}"><h3>${title}</h3><pre>${body}</pre></article>`;
    })
    .join("");
  document.getElementById("ref-nosana-log").textContent =
    latest.nosana_error || latest.nosana_reply
      ? `${latest.nosana_ms || 0} ms · ${latest.nosana_error || latest.nosana_reply}`
      : "Waiting for a run.";
  document.getElementById("ref-daytona-log").textContent =
    latest.daytona_error || latest.daytona_output
      ? `${latest.daytona_ms || 0} ms · ${String(latest.daytona_error || latest.daytona_output).trim()}`
      : "Waiting for a run.";
  if (data.llm_summary) document.getElementById("out-summary").textContent = data.llm_summary;
  if (data.llm_ms) document.getElementById("summary-ms").textContent = `${data.llm_ms} ms`;
  renderRunGraph(data.runs || []);
  renderTimingChart(data.runs || []);
}

function shorten(value, n) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

function promptKey(run) {
  return String(run.prompt || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function uniqueRunsByPrompt(runs, limit = 6) {
  const seen = new Set();
  const rows = [];
  for (const run of runs) {
    const key = promptKey(run);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const copies = runs.filter((item) => promptKey(item) === key).length;
    rows.push({ ...run, copies });
    if (rows.length >= limit) break;
  }
  return rows;
}

function splitCurrentAndHistory(runs) {
  const current = runs[0] || null;
  if (!current) return { current: null, history: [] };
  const copies = runs.filter((item) => promptKey(item) === promptKey(current)).length;
  const history = uniqueRunsByPrompt(
    runs.filter((item) => item.prompt_id !== current.prompt_id),
    5,
  );
  return { current: { ...current, copies }, history };
}

function sessionLabel(run) {
  if (run.session_label) return run.session_label;
  const id = String(run.session_id || "").replace(/^session-/, "");
  return id ? `S ${id.slice(0, 6)}` : "Session";
}

function graphSvg(rows, { current = false } = {}) {
  const colW = 210;
  const rowH = 62;
  const padX = 28;
  const padY = 28;
  const width = padX * 2 + colW * 4;
  const height = padY + rows.length * rowH;
  const headers = ["Session", "Prompt", "Nosana", "Daytona"];
  const header = headers
    .map((title, i) => `<text class="edge-label" x="${padX + i * colW + 66}" y="16" text-anchor="middle">${title}</text>`)
    .join("");
  const currentClass = current ? " current" : "";
  const nodeExtra = current ? " node-current" : "";
  const bodies = rows
    .map((run, row) => {
      const y = padY + row * rowH;
      const labels = [
        ["session", sessionLabel(run)],
        ["prompt", run.copies > 1 ? `${shorten(run.prompt, 12)} ×${run.copies}` : shorten(run.prompt, 16) || "Prompt"],
        ["nosana", shorten(run.nosana_error || run.code || run.nosana_reply || "Nosana", 16)],
        ["daytona", shorten(run.daytona_error || run.daytona_output || "Daytona", 16)],
      ];
      const boxes = labels
        .map(([kind, label], col) => {
          const x = padX + col * colW;
          return `<g>
            <rect class="node-${kind}${nodeExtra}" x="${x}" y="${y}" width="132" height="36" rx="10" />
            <text class="node-label" x="${x + 66}" y="${y + 23}" text-anchor="middle">${escapeText(label)}</text>
          </g>`;
        })
        .join("");
      const edges = [0, 1, 2]
        .map((col) => {
          const x1 = padX + col * colW + 132;
          const x2 = padX + (col + 1) * colW;
          const mid = (x1 + x2) / 2;
          const rel = ["ASKED", "PLANNED_ON", "EXECUTED_IN"][col];
          return `<path class="edge-line${currentClass}" d="M ${x1} ${y + 18} C ${mid} ${y + 18}, ${mid} ${y + 18}, ${x2} ${y + 18}" />
            <text class="edge-label" x="${mid}" y="${y + 12}" text-anchor="middle">${rel}</text>`;
        })
        .join("");
      return edges + boxes;
    })
    .join("");
  return `<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">${header}${bodies}</svg>`;
}

function historyRollup(runs, current) {
  const past = runs.filter((item) => item.prompt_id !== current.prompt_id);
  const unique = new Set(past.map(promptKey).filter(Boolean));
  const nosanaFail = past.filter((item) => item.nosana_error).length;
  const daytonaFail = past.filter((item) => item.daytona_error).length;
  const ok = past.find((item) => item.daytona_output && !item.daytona_error);
  return {
    session_id: "history",
    session_label: `${past.length} runs`,
    prompt: `${unique.size} prompts`,
    copies: 1,
    nosana_reply: nosanaFail ? `${nosanaFail} Nosana fails` : `${past.length - nosanaFail} GPU ok`,
    nosana_error: "",
    code: "",
    daytona_output: ok ? String(ok.daytona_output).trim() : "",
    daytona_error: !ok && daytonaFail ? `${daytonaFail} Daytona fails` : "",
    nosana_ms: past.length ? Math.round(past.reduce((s, r) => s + Number(r.nosana_ms || 0), 0) / past.length) : 0,
    daytona_ms: past.length ? Math.round(past.reduce((s, r) => s + Number(r.daytona_ms || 0), 0) / past.length) : 0,
  };
}

function renderRunGraph(runs) {
  const board = document.getElementById("neo4j-graph");
  const { current } = splitCurrentAndHistory(runs);
  if (!current) {
    board.innerHTML = `<p class="graph-empty">No Neo4j runs yet. Execute the pipeline to draw Session → Prompt → Nosana → Daytona.</p>`;
    return;
  }
  const failed = Boolean(current.nosana_error || current.daytona_error);
  const currentNote = failed ? " · this run failed (Nosana not ready)" : "";
  const extra = current.copies > 1 ? ` · same prompt stored ${current.copies} times` : "";
  const past = runs.filter((item) => item.prompt_id !== current.prompt_id);
  const rollup = past.length ? historyRollup(runs, current) : null;
  const accumulated = rollup
    ? `<div class="graph-band history">
        <p class="graph-band-title">Accumulated · averages of ${past.length} earlier runs</p>
        ${graphSvg([rollup])}
      </div>`
    : "";
  board.innerHTML = `<div class="graph-band current${failed ? " failed" : ""}">
      <p class="graph-band-title">Current execution${currentNote}${extra}</p>
      ${graphSvg([current], { current: true })}
    </div>${accumulated}`;
}

function renderTimingChart(runs) {
  const board = document.getElementById("timing-chart");
  const { current } = splitCurrentAndHistory(runs);
  if (!current) {
    board.innerHTML = "";
    return;
  }
  const past = runs.filter((item) => item.prompt_id !== current.prompt_id);
  const rollup = past.length ? historyRollup(runs, current) : null;
  const rows = [
    { label: "current", nosana: Number(current.nosana_ms || 0), daytona: Number(current.daytona_ms || 0), weight: 1 },
  ];
  if (rollup) {
    rows.push({
      label: "accumulated avg",
      nosana: Number(rollup.nosana_ms || 0),
      daytona: Number(rollup.daytona_ms || 0),
      weight: 0.5,
    });
  }
  const max = Math.max(1, ...rows.map((row) => Math.max(row.nosana, row.daytona)));
  const left = 140;
  const top = 16;
  const barH = 12;
  const gap = 36;
  const plotW = 400;
  const height = top + rows.length * gap + 8;
  const width = left + plotW + 24;
  const bars = rows
    .map((row, i) => {
      const y = top + i * gap;
      return `<text class="edge-label" x="${left - 8}" y="${y + 14}" text-anchor="end">${escapeText(row.label)}</text>
        <rect x="${left}" y="${y}" width="${(row.nosana / max) * plotW}" height="${barH}" rx="4" fill="#5b4dff" fill-opacity="${row.weight}" />
        <rect x="${left}" y="${y + 16}" width="${(row.daytona / max) * plotW}" height="${barH}" rx="4" fill="#0f8f6b" fill-opacity="${row.weight}" />`;
    })
    .join("");
  board.innerHTML = `<p class="chart-legend"><b class="nosana">■ Nosana GPU</b><b class="daytona">■ Daytona sandbox</b><span>Two bars only: this run vs average of earlier runs.</span></p>
    <svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">${bars}</svg>`;
}

async function loadHealth() {
  const res = await fetch("/api/health");
  const data = await res.json();
  const llm = data.llm || {};
  const neo = data.backend === "neo4j" ? `Aura · ${data.database}` : "Neo4j offline";
  const gpu = llm.ready
    ? "Nosana ready"
    : llm.status === "queued"
      ? "Nosana queued / starting"
      : llm.status
        ? `Nosana ${llm.status}`
        : "Nosana unknown";
  healthEl.textContent = `${neo} · ${gpu}`;
  healthEl.classList.toggle("ok", data.backend === "neo4j" && Boolean(llm.ready));
  healthEl.classList.toggle("warn", Boolean(llm.status) && !llm.ready);
  healthEl.title = llm.detail || "";
  const refs = data.references || {};
  renderLinks("refs-neo4j", refs.neo4j);
  renderLinks("refs-nosana", refs.nosana);
  renderLinks("refs-daytona", refs.daytona);
}

async function loadAnalysis() {
  const res = await fetch("/api/analysis");
  renderAnalysis(await res.json());
}

async function summarizeLogs() {
  setStep(4, "active", "Summarizing…");
  const res = await fetch("/api/summarize", { method: "POST" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Summary failed");
  renderAnalysis(data);
  setStep(4, data.llm_error ? "error" : "done", data.llm_error ? "Local only" : "Summarized");
}

function showTurn(turn) {
  document.getElementById("out-prompt").textContent = turn.prompt;
  setStep(1, "done", "Captured");
  document.getElementById("nosana-ms").textContent = turn.nosana_ms ? `${turn.nosana_ms} ms` : "";
  document.getElementById("out-nosana").textContent =
    turn.nosana_error || turn.nosana_reply || "(empty)";
  setStep(2, turn.nosana_error ? "error" : "done", turn.nosana_error ? "Failed" : "Code ready");
  document.getElementById("daytona-ms").textContent = turn.daytona_ms ? `${turn.daytona_ms} ms` : "";
  document.getElementById("out-code").textContent = turn.code || "(none)";
  document.getElementById("out-daytona").textContent =
    turn.daytona_error || turn.daytona_output || "(empty)";
  setStep(3, turn.daytona_error ? "error" : "done", turn.daytona_error ? "Failed" : "Ran");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = promptEl.value.trim();
  runBtn.disabled = true;
  resetSteps();
  document.getElementById("out-prompt").textContent = prompt;
  setStep(1, "done", "Captured");
  setStep(2, "active", "Calling GPU…");
  statusEl.textContent = "Step 2: Nosana is writing Python.";
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const turn = await res.json();
    if (!res.ok) throw new Error(turn.detail || "Run failed");
    showTurn(turn);
    statusEl.textContent = "Updating Neo4j insights, then summarizing logs.";
    await loadAnalysis();
    await summarizeLogs();
    statusEl.textContent = "Done. Use the three columns below to open Neo4j, Nosana, and Daytona.";
  } catch (error) {
    setStep(2, "error", "Failed");
    setStep(3, "error", "Skipped");
    setStep(4, "error", "Skipped");
    statusEl.textContent = error.message;
  } finally {
    runBtn.disabled = false;
  }
});

loadHealth();
loadAnalysis();
