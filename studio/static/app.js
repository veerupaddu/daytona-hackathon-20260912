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

function renderAnalysis(data) {
  document.getElementById("stat-runs").textContent = String(data.run_count || 0);
  document.getElementById("stat-nosana").textContent = `${data.avg_nosana_ms || 0} ms`;
  document.getElementById("stat-daytona").textContent = `${data.avg_daytona_ms || 0} ms`;
  document.getElementById("stat-fail").textContent =
    `${data.nosana_failures || 0} / ${data.daytona_failures || 0}`;
  const list = document.getElementById("key-messages");
  list.innerHTML = "";
  const messages = data.key_messages && data.key_messages.length
    ? data.key_messages
    : ["No key messages yet."];
  messages.forEach((msg) => {
    const item = document.createElement("li");
    item.textContent = msg;
    list.appendChild(item);
  });
  const latest = (data.runs && data.runs[0]) || {};
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
  renderTimingBars(data.runs || []);
}

function escapeXml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function nodeGroup(group) {
  const raw = String(group || "").toLowerCase();
  if (raw.includes("session")) return "session";
  if (raw.includes("prompt")) return "prompt";
  if (raw.includes("nosana")) return "nosana";
  if (raw.includes("daytona")) return "daytona";
  return "other";
}

function renderGraph(graph) {
  const board = document.getElementById("neo4j-graph");
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  if (!nodes.length) {
    board.innerHTML = `<p class="graph-empty">No Neo4j nodes yet. Run the pipeline to populate Aura.</p>`;
    return;
  }
  const columns = { session: [], prompt: [], nosana: [], daytona: [], other: [] };
  nodes.forEach((node) => columns[nodeGroup(node.group)].push(node));
  const order = ["session", "prompt", "nosana", "daytona"].filter((key) => columns[key].length);
  if (columns.other.length) order.push("other");
  const colW = 200;
  const rowH = 64;
  const padX = 36;
  const padY = 28;
  const maxRows = Math.max(1, ...order.map((key) => columns[key].length));
  const width = padX * 2 + Math.max(1, order.length) * colW;
  const height = padY * 2 + maxRows * rowH;
  const positions = {};
  order.forEach((key, col) => {
    columns[key].forEach((node, row) => {
      positions[node.id] = {
        x: padX + col * colW + 16,
        y: padY + row * rowH,
        label: (() => {
          const parts = String(node.label || node.title || key).split("\n");
          return (parts[1] || parts[0] || key).slice(0, 18);
        })(),
        group: key,
      };
    });
  });
  const lines = edges
    .filter((edge) => positions[edge.from] && positions[edge.to])
    .map((edge) => {
      const a = positions[edge.from];
      const b = positions[edge.to];
      const x1 = a.x + 132;
      const y1 = a.y + 18;
      const x2 = b.x;
      const y2 = b.y + 18;
      const mid = (x1 + x2) / 2;
      return `<path class="edge-line" d="M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}" />
        <text class="edge-label" x="${mid}" y="${(y1 + y2) / 2 - 6}">${escapeXml(edge.label || "")}</text>`;
    })
    .join("");
  const boxes = Object.entries(positions)
    .map(
      ([, pos]) =>
        `<g>
          <rect class="node-${pos.group}" x="${pos.x}" y="${pos.y}" width="132" height="36" rx="10" />
          <text class="node-label" x="${pos.x + 66}" y="${pos.y + 23}" text-anchor="middle">${escapeXml(pos.label)}</text>
        </g>`
    )
    .join("");
  board.innerHTML = `<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">${lines}${boxes}</svg>`;
}

function renderTimingBars(runs) {
  const host = document.getElementById("timing-bars");
  if (!runs.length) {
    host.innerHTML = "";
    return;
  }
  const max = Math.max(1, ...runs.map((run) => (run.nosana_ms || 0) + (run.daytona_ms || 0)));
  host.innerHTML = runs
    .slice(0, 6)
    .map((run) => {
      const prompt = String(run.prompt || "run").slice(0, 42);
      const nosana = Number(run.nosana_ms || 0);
      const daytona = Number(run.daytona_ms || 0);
      return `<div class="timing-row">
        <p>${escapeXml(prompt)}<small>${nosana} ms GPU · ${daytona} ms sandbox</small></p>
        <div class="bar-track">
          <span class="bar-nosana" style="width:${(nosana / max) * 100}%"></span>
          <span class="bar-daytona" style="width:${(daytona / max) * 100}%"></span>
        </div>
      </div>`;
    })
    .join("");
}

async function loadHealth() {
  const res = await fetch("/api/health");
  const data = await res.json();
  healthEl.textContent =
    data.backend === "neo4j" ? `Aura connected · ${data.database}` : "Neo4j offline";
  healthEl.classList.toggle("ok", data.backend === "neo4j");
  const refs = data.references || {};
  renderLinks("refs-neo4j", refs.neo4j);
  renderLinks("refs-nosana", refs.nosana);
  renderLinks("refs-daytona", refs.daytona);
}

async function loadAnalysis() {
  const [analysisRes, graphRes] = await Promise.all([
    fetch("/api/analysis"),
    fetch("/api/graph"),
  ]);
  renderAnalysis(await analysisRes.json());
  renderGraph(await graphRes.json());
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
    statusEl.textContent = "Step 4: analyzing Neo4j logs.";
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
