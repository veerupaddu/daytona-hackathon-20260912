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

function groupKeyMessages(messages, latest) {
  const groups = { prompt: [], nosana: [], daytona: [] };
  (messages || []).forEach((msg) => {
    const text = String(msg);
    if (/prompt/i.test(text)) groups.prompt.push(text.replace(/^Last prompt:\s*/i, ""));
    else if (/nosana/i.test(text)) groups.nosana.push(text.replace(/^Nosana[^:]*:\s*/i, ""));
    else if (/daytona/i.test(text)) groups.daytona.push(text.replace(/^Daytona[^:]*:\s*/i, ""));
  });
  if (!groups.prompt.length && latest.prompt) groups.prompt.push(latest.prompt);
  if (!groups.nosana.length && (latest.nosana_reply || latest.nosana_error)) {
    groups.nosana.push(latest.nosana_error || latest.nosana_reply);
  }
  if (!groups.daytona.length && (latest.daytona_output || latest.daytona_error)) {
    groups.daytona.push(latest.daytona_error || String(latest.daytona_output).trim());
  }
  return groups;
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
  const groups = groupKeyMessages(data.key_messages, latest);
  document.getElementById("message-groups").innerHTML = [
    ["prompt", "Prompt", groups.prompt],
    ["nosana", "Nosana", groups.nosana],
    ["daytona", "Daytona", groups.daytona],
  ]
    .map(([kind, title, items]) => {
      const body = items.length ? items.map((item) => escapeText(item)).join("\n\n") : "No logs yet.";
      return `<article class="message-card ${kind}"><h3>${title}</h3><p>${body}</p></article>`;
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
