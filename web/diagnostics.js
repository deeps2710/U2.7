const refreshButton = document.getElementById("refreshDiagnostics");
const statusBanner = document.getElementById("diagnosticsStatus");
const backendList = document.getElementById("backendList");
const brainList = document.getElementById("brainList");
const runtimeList = document.getElementById("runtimeList");
const voiceList = document.getElementById("voiceList");
const safeRootsList = document.getElementById("safeRootsList");
const errorsList = document.getElementById("errorsList");

window.lucide?.createIcons({ attrs: { "aria-hidden": "true" } });
refreshButton.addEventListener("click", loadDiagnostics);
loadDiagnostics();

async function loadDiagnostics() {
  statusBanner.textContent = "Checking readiness...";
  try {
    const payload = await fetchJson("/api/diagnostics");
    statusBanner.textContent =
      payload.readiness === "ready" ? "System readiness: ready" : "System readiness: attention needed";
    statusBanner.dataset.status = payload.readiness || "unknown";
    renderDefinitionList(backendList, {
      Version: payload.version,
      Python: payload.backend?.python,
      Platform: payload.backend?.platform,
      Package: payload.backend?.package,
    });
    renderDefinitionList(brainList, {
      Status: payload.brain?.status,
      Planner: payload.brain?.planner_mode,
      Dataset: pathState(payload.brain?.dataset),
      Memory: pathState(payload.brain?.memory),
      Skills: `${payload.skills?.count || 0} loaded`,
    });
    renderDefinitionList(runtimeList, {
      Workspace: pathState(payload.runtime?.workspace),
      "Audit log": pathState(payload.runtime?.audit_log),
      "Screenshot dir": pathState(payload.runtime?.screenshot_dir),
      "Dry run": String(Boolean(payload.runtime?.dry_run)),
      "Audit enabled": String(Boolean(payload.runtime?.audit_enabled)),
    });
    renderDefinitionList(voiceList, {
      STT: `${payload.voice?.providers?.active?.stt || "unknown"} (${payload.voice?.providers?.configured?.stt || "unknown"} configured)`,
      TTS: `${payload.voice?.providers?.active?.tts || "unknown"} (${payload.voice?.providers?.configured?.tts || "unknown"} configured)`,
      Wake: payload.voice?.wake?.gate_providers?.active_wake?.name || "unknown",
      VAD: payload.voice?.wake?.gate_providers?.active_vad?.name || "unknown",
      Microphone: payload.voice?.status?.microphone_enabled ? "on" : "off",
    });
    renderSafeRoots(payload.runtime?.safe_roots || []);
    renderErrors(payload.recent_errors || []);
  } catch {
    statusBanner.textContent = "Diagnostics API unavailable.";
    statusBanner.dataset.status = "attention_needed";
  }
}

function renderDefinitionList(list, values) {
  list.innerHTML = "";
  for (const [key, value] of Object.entries(values)) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value || "unknown";
    list.append(dt, dd);
  }
}

function renderSafeRoots(items) {
  safeRootsList.innerHTML = "";
  if (!items.length) {
    appendItem(safeRootsList, "No safe roots configured.");
    return;
  }
  for (const item of items) {
    appendItem(safeRootsList, `${item.exists ? "OK" : "Missing"}: ${item.path}`);
  }
}

function renderErrors(items) {
  errorsList.innerHTML = "";
  if (!items.length) {
    appendItem(errorsList, "No recent readiness errors.");
    return;
  }
  for (const item of items) {
    appendItem(errorsList, item);
  }
}

function appendItem(list, text) {
  const li = document.createElement("li");
  li.textContent = text;
  list.append(li);
}

function pathState(payload) {
  if (!payload) return "unknown";
  return `${payload.exists || payload.parent_exists ? "OK" : "Missing"}: ${payload.path}`;
}

async function fetchJson(url) {
  const response = await fetch(url);
  return response.json();
}
