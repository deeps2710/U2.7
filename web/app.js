import * as THREE from "./vendor/three.module.min.js";
import { createArmillaryCore } from "./ultron-core.js";

const canvas = document.getElementById("ultron-scene");
const subtitlePanel = document.getElementById("subtitlePanel");
const subtitleText = document.getElementById("subtitleText");
const subtitleToggle = document.getElementById("subtitleToggle");
const commandInput = document.getElementById("commandInput");
const sendButton = document.getElementById("sendButton");
const statusLabel = document.getElementById("statusLabel");
const voiceBadge = document.getElementById("voiceBadge");
const micToggle = document.getElementById("micToggle");
const backendCaptureButton = document.getElementById("backendCaptureButton");
const alwaysListeningToggle = document.getElementById("alwaysListeningToggle");
const pushToTalkToggle = document.getElementById("pushToTalkToggle");
const muteToggle = document.getElementById("muteToggle");
const stopSpeakingButton = document.getElementById("stopSpeakingButton");
const confirmVoiceButton = document.getElementById("confirmVoiceButton");
const mockVoiceButton = document.getElementById("mockVoiceButton");
const sttProviderLabel = document.getElementById("sttProviderLabel");
const sttProviderDetail = document.getElementById("sttProviderDetail");
const captureProviderLabel = document.getElementById("captureProviderLabel");
const captureProviderDetail = document.getElementById("captureProviderDetail");
const ttsProviderLabel = document.getElementById("ttsProviderLabel");
const ttsProviderDetail = document.getElementById("ttsProviderDetail");
const refreshProvidersButton = document.getElementById("refreshProvidersButton");
const testProvidersButton = document.getElementById("testProvidersButton");
const micStatusLabel = document.getElementById("micStatusLabel");
const micPrivacyDetail = document.getElementById("micPrivacyDetail");
const wakeStateLabel = document.getElementById("wakeStateLabel");
const wakeDetail = document.getElementById("wakeDetail");
const vadStateLabel = document.getElementById("vadStateLabel");
const vadDetail = document.getElementById("vadDetail");
const lastTranscriptLabel = document.getElementById("lastTranscriptLabel");
const confidenceDetail = document.getElementById("confidenceDetail");
const audioStateLabel = document.getElementById("audioStateLabel");
const audioDetail = document.getElementById("audioDetail");
const voiceHistory = document.getElementById("voiceHistory");
const skillsList = document.getElementById("skillsList");
const memoryToggle = document.getElementById("memoryToggle");
const memoryForgetInput = document.getElementById("memoryForgetInput");
const memoryForgetButton = document.getElementById("memoryForgetButton");
const knowledgeSearchInput = document.getElementById("knowledgeSearchInput");
const knowledgeSearchButton = document.getElementById("knowledgeSearchButton");
const knowledgeList = document.getElementById("knowledgeList");
const recentTasksList = document.getElementById("recentTasksList");
const stateButtons = [...document.querySelectorAll("[data-state]")];
const confirmationModal = document.getElementById("confirmationModal");
const confirmationTitle = document.getElementById("confirmationTitle");
const confirmationMessage = document.getElementById("confirmationMessage");
const confirmationTool = document.getElementById("confirmationTool");
const confirmationPermission = document.getElementById("confirmationPermission");
const approveConfirmationButton = document.getElementById("approveConfirmationButton");
const cancelConfirmationButton = document.getElementById("cancelConfirmationButton");

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(44, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 0.08, 4.35);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x000000, 0);

const clock = new THREE.Clock();
const stateTargets = {
  inactive: { scale: 1.0, ring: 0.18, line: 0.36, particle: 0.06, glow: 0.86 },
  idle: { scale: 1.0, ring: 0.25, line: 0.45, particle: 0.08, glow: 1.0 },
  waiting_for_wake_word: { scale: 0.94, ring: 0.28, line: 0.28, particle: 0.035, glow: 0.72 },
  listening: { scale: 0.88, ring: 0.36, line: 0.32, particle: 0.04, glow: 0.78 },
  transcribing: { scale: 0.98, ring: 0.68, line: 0.48, particle: 0.12, glow: 1.0 },
  thinking: { scale: 1.0, ring: 1.0, line: 0.62, particle: 0.14, glow: 1.12 },
  speaking: { scale: 1.1, ring: 0.55, line: 1.0, particle: 0.22, glow: 1.36 },
};

let visualState = "idle";
let subtitlesEnabled = true;
let micEnabled = false;
let pushToTalk = false;
let voiceMuted = false;
let returnTimer = null;
let recognition = null;
let recognitionActive = false;
let providerStatus = null;
let alwaysListening = false;
let pendingConfirmation = null;
let memoryEnabled = true;

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const root = new THREE.Group();
root.position.y = 0.32;
scene.add(root);

const sphereUniforms = {
  time: { value: 0 },
  intensity: { value: 0.7 },
};

const sphere = new THREE.Mesh(
  new THREE.IcosahedronGeometry(1.03, 8),
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: sphereUniforms,
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vPosition;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vPosition = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float time;
      uniform float intensity;
      varying vec3 vNormal;
      varying vec3 vPosition;
      void main() {
        float rim = pow(1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0))), 2.45);
        float plasma = sin(vPosition.x * 9.0 + time * 1.8) * sin(vPosition.y * 7.0 - time * 1.4);
        float veins = smoothstep(0.72, 0.98, abs(plasma));
        vec3 deep = vec3(0.0, 0.11, 0.045);
        vec3 neon = vec3(0.0, 1.0, 0.38);
        vec3 lime = vec3(0.58, 1.0, 0.18);
        vec3 color = mix(deep, neon, rim * 1.4 + veins * 0.45);
        color = mix(color, lime, veins * 0.35);
        float alpha = 0.12 + rim * 0.58 + veins * 0.14;
        gl_FragColor = vec4(color * intensity, alpha);
      }
    `,
  })
);
root.add(sphere);

const glow = new THREE.Sprite(
  new THREE.SpriteMaterial({
    map: makeGlowTexture(),
    transparent: true,
    blending: THREE.AdditiveBlending,
    opacity: 0.64,
    depthWrite: false,
  })
);
glow.scale.set(3.15, 3.15, 1);
root.add(glow);

const plasmaLines = new THREE.Group();
for (let i = 0; i < 24; i += 1) {
  plasmaLines.add(makeArc(i));
}
root.add(plasmaLines);

const ringGroup = new THREE.Group();
for (let i = 0; i < 5; i += 1) {
  const arc = i % 2 === 0 ? Math.PI * 2 : Math.PI * 1.42;
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(1.18 + i * 0.045, 0.006 + i * 0.001, 10, 180, arc),
    new THREE.MeshBasicMaterial({
      color: i % 2 === 0 ? 0x00ff66 : 0xa6ff3f,
      transparent: true,
      opacity: 0.26,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
  );
  ring.rotation.set(Math.PI / 2 + i * 0.22, i * 0.46, i * 0.31);
  ringGroup.add(ring);
}
root.add(ringGroup);

const particles = makeParticles();
scene.add(particles);

const fill = new THREE.PointLight(0x00ff66, 1.4, 7);
fill.position.set(1.8, 1.2, 2.4);
scene.add(fill);

root.visible = false;
particles.visible = false;
fill.intensity = 0;
const armillaryCore = createArmillaryCore({ scene, camera, renderer });

setVisualState("idle", { sync: false });
loadStatus();
loadProviders();
setupSpeechRecognition();
animate();

stateButtons.forEach((button) => {
  button.addEventListener("click", () => setVisualState(button.dataset.state));
});

subtitleToggle.addEventListener("click", async () => {
  subtitlesEnabled = !subtitlesEnabled;
  updateSubtitles();
  try {
    await fetch("/api/subtitles/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: subtitlesEnabled }),
    });
  } catch {
    // The local visual toggle should keep working even if the API is not ready.
  }
});

micToggle.addEventListener("click", () => {
  if (micEnabled) {
    stopVoiceInput();
  } else {
    startVoiceInput();
  }
});
backendCaptureButton.addEventListener("click", captureBackendVoice);

pushToTalkToggle.addEventListener("click", () => {
  pushToTalk = !pushToTalk;
  pushToTalkToggle.textContent = pushToTalk ? "Push-to-talk" : "Continuous";
  pushToTalkToggle.setAttribute("aria-pressed", String(pushToTalk));
  micPrivacyDetail.textContent = pushToTalk ? "One command per mic start" : "Continuous listening until stopped";
});

alwaysListeningToggle.addEventListener("click", () => {
  if (alwaysListening) {
    stopAlwaysListening();
  } else {
    startAlwaysListening();
  }
});

muteToggle.addEventListener("click", async () => {
  voiceMuted = !voiceMuted;
  muteToggle.textContent = voiceMuted ? "Muted" : "Mute Off";
  muteToggle.setAttribute("aria-pressed", String(voiceMuted));
  await postJson("/api/speak", { muted: voiceMuted, text: "" });
  if (voiceMuted) stopBrowserSpeech();
});

stopSpeakingButton.addEventListener("click", async () => {
  stopBrowserSpeech();
  await postJson("/api/speak", { action: "stop" });
  setVisualState(micEnabled ? "listening" : "idle");
});

confirmVoiceButton.addEventListener("click", () => handleVoiceTranscript("yes confirm"));
mockVoiceButton.addEventListener("click", () =>
  handleVoiceTranscript("ULTRON, create a note called demo and write that voice mode is working.")
);
refreshProvidersButton.addEventListener("click", loadProviders);
testProvidersButton.addEventListener("click", testVoiceProviders);
approveConfirmationButton.addEventListener("click", approvePendingConfirmation);
cancelConfirmationButton.addEventListener("click", cancelPendingConfirmation);
knowledgeSearchButton.addEventListener("click", searchKnowledge);
knowledgeSearchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") searchKnowledge();
});
memoryToggle.addEventListener("click", toggleMemory);
memoryForgetButton.addEventListener("click", forgetMemory);
memoryForgetInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") forgetMemory();
});

sendButton.addEventListener("click", sendCommand);
commandInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    sendCommand();
  }
});

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

async function sendCommand(options = {}) {
  const command = String(options.command ?? commandInput.value).trim();
  const confirmed = Boolean(options.confirmed);
  if (!command) return;
  if (!confirmed) commandInput.value = "";
  setSubtitle(confirmed ? `Confirmed: ${command}` : `Processing: ${command}`);
  setVisualState("thinking");
  try {
    const payload = await postJson("/api/command", { command, mode: "do", confirmed });
    const spoken = payload.subtitle || buildTaskSubtitle(payload.task) || payload.message || "Command processed.";
    setSubtitle(spoken);
    renderHistory(payload.conversation_history || []);
    renderRecentTasks(payload.recent_tasks || []);
    if (payload.memory_enabled !== undefined) memoryEnabled = Boolean(payload.memory_enabled);
    await loadMemoryKnowledge();
    if (taskNeedsConfirmation(payload.task)) {
      showConfirmation(payload.task, { command, source: "typed" });
      setVisualState("listening");
      return;
    }
    clearPendingConfirmation();
    setVisualState("speaking");
    await speakText(spoken);
    scheduleListeningReturn();
  } catch {
    setSubtitle("Local interface could not reach the ULTRON runtime.");
    setVisualState("idle");
  }
}

async function loadStatus() {
  try {
    const payload = await fetchJson("/api/status");
    subtitlesEnabled = Boolean(payload.subtitles_enabled);
    setSubtitle(payload.last_subtitle || "ULTRON 2.7 online.");
    setVisualState(payload.visual_state || "idle", { sync: false });
    updateSubtitles();
    const voicePayload = await fetchJson("/api/voice/status");
    applyVoiceStatus(voicePayload.voice);
    applyWakeStatus(voicePayload.wake);
    applyVoiceDiagnostics(voicePayload.voice_diagnostics || payload.voice_diagnostics);
    renderHistory(voicePayload.history || []);
    renderRecentTasks(payload.recent_tasks || []);
    memoryEnabled = payload.memory_enabled !== undefined ? Boolean(payload.memory_enabled) : memoryEnabled;
    renderKnowledgePanel({ sources: payload.knowledge_sources || [], memoryEnabled });
    await loadProviders();
    await loadWakeStatus();
    await loadSkills();
    await loadMemoryKnowledge();
  } catch {
    setSubtitle("ULTRON visual shell loaded. Runtime API pending.");
  }
}

async function loadProviders() {
  try {
    providerStatus = await fetchJson("/api/voice/providers");
    applyProviders(providerStatus);
  } catch {
    providerStatus = null;
    sttProviderDetail.textContent = "Runtime API pending";
    captureProviderDetail.textContent = "Runtime API pending";
    ttsProviderDetail.textContent = "Runtime API pending";
  }
}

async function loadWakeStatus() {
  try {
    const payload = await fetchJson("/api/wake/status");
    applyWakeStatus(payload.wake);
  } catch {
    wakeStateLabel.textContent = "Pending";
    wakeDetail.textContent = "Wake API pending";
  }
}

async function loadSkills() {
  try {
    const payload = await fetchJson("/api/skills");
    renderSkills(payload.skills || []);
  } catch {
    renderSkills([]);
  }
}

async function loadMemoryKnowledge() {
  try {
    const memory = await fetchJson("/api/memory");
    const status = await fetchJson("/api/status");
    memoryEnabled = memory.enabled !== undefined ? Boolean(memory.enabled) : memoryEnabled;
    renderKnowledgePanel({ memory: memory.memory || [], sources: status.knowledge_sources || [], memoryEnabled });
    renderRecentTasks(status.recent_tasks || []);
  } catch {
    renderKnowledgePanel({ memory: [], sources: [], memoryEnabled });
  }
}

async function toggleMemory() {
  memoryEnabled = !memoryEnabled;
  try {
    const payload = await postJson("/api/memory/toggle", { enabled: memoryEnabled });
    memoryEnabled = Boolean(payload.enabled);
    renderKnowledgePanel({ memory: payload.memory || [], sources: payload.knowledge_sources || [], memoryEnabled });
    setSubtitle(memoryEnabled ? "Memory is now on." : "Memory is now off.");
  } catch {
    setSubtitle("Memory controls could not reach the ULTRON runtime.");
  }
}

async function forgetMemory() {
  const query = memoryForgetInput.value.trim();
  if (!query) return;
  try {
    const payload = await postJson("/api/memory/forget", { query });
    memoryForgetInput.value = "";
    memoryEnabled = payload.enabled !== undefined ? Boolean(payload.enabled) : memoryEnabled;
    renderKnowledgePanel({ memory: payload.memory || [], sources: payload.knowledge_sources || [], memoryEnabled });
    setSubtitle(payload.last_subtitle || `Forgot ${payload.removed || 0} matching memory item(s).`);
  } catch {
    setSubtitle("Forget memory could not reach the ULTRON runtime.");
  }
}

async function searchKnowledge() {
  const query = knowledgeSearchInput.value.trim();
  if (!query) {
    await loadMemoryKnowledge();
    return;
  }
  try {
    const payload = await fetchJson(`/api/knowledge/search?query=${encodeURIComponent(query)}&limit=5`);
    renderKnowledgePanel({ matches: payload.knowledge?.matches || [], sources: payload.knowledge?.sources || [] });
  } catch {
    renderKnowledgePanel({ error: "Knowledge search unavailable." });
  }
}

async function startAlwaysListening() {
  alwaysListening = true;
  const payload = await postJson("/api/wake/start", {});
  applyVoiceStatus(payload.voice);
  applyWakeStatus(payload.wake);
  setSubtitle(payload.last_subtitle || "Always-listening is on. Say ULTRON or Hey ULTRON.");
  setVisualState("waiting_for_wake_word");
  if (!SpeechRecognition) {
    voiceBadge.textContent = "Wake mock available";
    return;
  }
  micEnabled = true;
  startRecognition();
}

async function stopAlwaysListening() {
  alwaysListening = false;
  const payload = await postJson("/api/wake/stop", {});
  applyVoiceStatus(payload.voice);
  applyWakeStatus(payload.wake);
  setSubtitle(payload.last_subtitle || "Always-listening is off.");
  setVisualState("idle");
  if (recognition && recognitionActive) {
    recognition.stop();
  }
}

async function testVoiceProviders() {
  setVisualState("thinking");
  setSubtitle("Testing voice providers...");
  try {
    const stt = await postJson("/api/voice/test-stt", { transcript: "ULTRON, create note provider test" });
    const tts = await postJson("/api/voice/test-tts", { text: "ULTRON voice provider test." });
    providerStatus = tts;
    applyProviders(tts);
    applyVoiceDiagnostics(stt.voice_diagnostics || tts.voice_diagnostics);
    const transcript = stt.transcript?.text || "No transcript";
    const speechStatus = tts.speech?.status || "checked";
    setSubtitle(`STT: ${transcript}\nTTS: ${speechStatus}`);
    if (tts.speech?.provider === "browser_speech_synthesis" && !voiceMuted) {
      await playBrowserSpeech("ULTRON voice provider test.");
    }
    setVisualState("speaking");
    scheduleListeningReturn();
  } catch {
    setSubtitle("Voice provider test could not reach the ULTRON runtime.");
    setVisualState("idle");
  }
}

async function startVoiceInput() {
  if (alwaysListening) {
    await stopAlwaysListening();
  }
  micEnabled = true;
  micToggle.textContent = "Stop Mic";
  micStatusLabel.textContent = "On";
  micPrivacyDetail.textContent = pushToTalk ? "Listening for one command" : "Continuous listening until stopped";
  voiceBadge.textContent = SpeechRecognition ? "Listening" : "Speech API unavailable";
  setVisualState("listening");
  const payload = await postJson("/api/voice/start", { push_to_talk: pushToTalk });
  applyVoiceStatus(payload.voice);
  applyWakeStatus(payload.wake);
  if (!SpeechRecognition) {
    setSubtitle("This browser does not expose speech recognition. Open ULTRON in Chrome or Edge, then allow microphone access. Typed input and Mock Voice still work.");
    return;
  }
  setSubtitle(pushToTalk ? "Listening. Speak one command now." : "Continuous listening is on. Speak when ready.");
  startRecognition();
}

async function stopVoiceInput() {
  micEnabled = false;
  micToggle.textContent = "Start Mic";
  micStatusLabel.textContent = "Off";
  micPrivacyDetail.textContent = "Microphone stopped";
  voiceBadge.textContent = "Voice standby";
  setVisualState("idle");
  if (recognition && recognitionActive) {
    recognition.stop();
  }
  const payload = await postJson("/api/voice/stop", {});
  applyVoiceStatus(payload.voice);
  applyWakeStatus(payload.wake);
}

function setupSpeechRecognition() {
  if (!SpeechRecognition) return;
  recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    recognitionActive = true;
    voiceBadge.textContent = "Listening";
    setVisualState("listening");
  };
  recognition.onspeechstart = () => {
    voiceBadge.textContent = "Speech detected";
    setVisualState("listening");
  };
  recognition.onresult = (event) => {
    const transcript = event.results?.[0]?.[0]?.transcript || "";
    const confidence = event.results?.[0]?.[0]?.confidence;
    if (transcript.trim()) handleVoiceTranscript(transcript, { confidence });
  };
  recognition.onerror = (event) => {
    voiceBadge.textContent = `Voice error: ${event.error}`;
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      setSubtitle("Microphone permission was blocked. Allow microphone access in the browser site settings, then press Start Mic again.");
      micEnabled = false;
      applyVoiceStatus({ microphone_enabled: false, muted: voiceMuted, push_to_talk: pushToTalk, listening: false, speaking: false });
      setVisualState("idle");
      return;
    }
    if (event.error === "no-speech") {
      setSubtitle(pushToTalk ? "I did not hear speech. Press Start Mic and try again, or switch to Continuous." : "I did not hear speech. Still listening...");
      setVisualState("listening");
      return;
    }
    setSubtitle(`Voice capture error: ${event.error}. Typed mode and Mock Voice still work.`);
    setVisualState(micEnabled ? "listening" : "idle");
  };
  recognition.onend = () => {
    recognitionActive = false;
    if (micEnabled && !alwaysListening && !pushToTalk) {
      window.setTimeout(startRecognition, 350);
    }
  };
}

function startRecognition() {
  if (!recognition || recognitionActive) return;
  recognition.continuous = alwaysListening || !pushToTalk;
  try {
    recognition.start();
  } catch {
    voiceBadge.textContent = "Voice restart pending";
  }
}

async function handleVoiceTranscript(transcript, options = {}) {
  if (!transcript.trim()) return;
  if (alwaysListening) {
    await handleWakeTranscript(transcript);
    return;
  }
  setSubtitle("Working on it.");
  setVisualState("thinking");
  voiceBadge.textContent = "Processing voice";
  try {
    const body = { transcript };
    if (typeof options.confidence === "number" && Number.isFinite(options.confidence) && options.confidence > 0.01) body.confidence = options.confidence;
    const payload = await postJson("/api/voice/transcribe", body);
    applyVoiceStatus(payload.voice);
    applyVoiceDiagnostics(payload.voice_diagnostics);
    renderHistory([...(payload.conversation_history || []), ...(payload.history || [])]);
    const response = payload.spoken_response || payload.subtitle || payload.message || "Voice command processed.";
    setSubtitle(formatAssistantSubtitle(payload, response));
    confirmVoiceButton.hidden = !payload.needs_confirmation;
    if (payload.needs_confirmation || taskNeedsConfirmation(payload.task)) {
      showConfirmation(payload.task, { command: payload.voice?.pending_confirmation_goal || transcript, source: "voice" });
    } else {
      clearPendingConfirmation();
    }
    if (payload.status === "empty") {
      setVisualState("listening");
      return;
    }
    setVisualState(payload.needs_confirmation ? "listening" : "speaking");
    await speakText(response);
    scheduleListeningReturn();
  } catch {
    setSubtitle("Voice mode could not reach the ULTRON runtime.");
    setVisualState("idle");
  }
}

async function captureBackendVoice() {
  setSubtitle("Listening.");
  setVisualState("listening");
  voiceBadge.textContent = "Backend capture";
  try {
    const payload = await postJson("/api/voice/capture", {});
    applyVoiceStatus(payload.voice);
    applyWakeStatus(payload.wake);
    applyVoiceDiagnostics(payload.voice_diagnostics);
    renderHistory([...(payload.conversation_history || []), ...(payload.history || [])]);
    if (payload.status === "capture_unavailable") {
      setSubtitle(payload.message || "Backend microphone capture is unavailable. Browser mic and typed mode still work.");
      setVisualState("listening");
      return;
    }
    const response = payload.spoken_response || payload.subtitle || payload.message || "Voice command processed.";
    const understood = payload.record?.ultron_understood || payload.transcript?.text || "";
    setSubtitle(formatAssistantSubtitle(payload, response));
    if (payload.needs_confirmation || taskNeedsConfirmation(payload.task)) {
      showConfirmation(payload.task, { command: payload.voice?.pending_confirmation_goal || understood, source: "voice" });
      setVisualState("listening");
      return;
    }
    clearPendingConfirmation();
    setVisualState(payload.status === "empty" ? "listening" : "speaking");
    await speakText(response);
    scheduleListeningReturn();
  } catch {
    setSubtitle("Backend microphone capture could not reach the ULTRON runtime.");
    setVisualState(micEnabled ? "listening" : "idle");
  }
}

async function handleWakeTranscript(transcript) {
  setSubtitle("Checking the wake phrase.");
  setVisualState("transcribing");
  voiceBadge.textContent = "Checking wake gate";
  try {
    const payload = await postJson("/api/wake/process", { transcript, audio_energy: transcript.trim() ? 0.8 : 0.0 });
    applyVoiceStatus(payload.voice);
    applyWakeStatus(payload.wake);
    applyVoiceDiagnostics(payload.voice_diagnostics);
    renderHistory([...(payload.conversation_history || []), ...(payload.history || [])]);
    if (payload.status === "ignored") {
      setSubtitle(payload.message || "Input ignored by wake/VAD gate.");
      setVisualState(payload.visual_state || "waiting_for_wake_word");
      return;
    }
    if (payload.status === "wake_detected") {
      setSubtitle(payload.message || "Wake word detected. Listening.");
      setVisualState("listening");
      return;
    }
    const response = payload.spoken_response || payload.subtitle || payload.message || "Voice command processed.";
    setSubtitle(formatAssistantSubtitle(payload, response));
    confirmVoiceButton.hidden = !payload.needs_confirmation;
    if (payload.needs_confirmation || taskNeedsConfirmation(payload.task)) {
      showConfirmation(payload.task, { command: payload.voice?.pending_confirmation_goal || transcript, source: "voice" });
    } else {
      clearPendingConfirmation();
    }
    setVisualState(payload.needs_confirmation ? "listening" : "speaking");
    await speakText(response);
    scheduleListeningReturn();
  } catch {
    setSubtitle("Wake mode could not reach the ULTRON runtime.");
    setVisualState("waiting_for_wake_word");
  }
}

async function speakText(text) {
  armillaryCore.setSpeechText(text);
  const payload = await postJson("/api/speak", { text, muted: voiceMuted });
  applyVoiceStatus(payload.voice);
  if (payload.speech?.provider && providerStatus?.active) {
    providerStatus.active.tts = payload.speech.provider;
    applyProviders(providerStatus);
  }
  if (voiceMuted || !text.trim()) return;
  if (payload.speech?.provider && payload.speech.provider !== "browser_speech_synthesis") {
    voiceBadge.textContent = payload.speech.status === "audio_file" ? "Local TTS ready" : "Local TTS checked";
    return;
  }
  await playBrowserSpeech(text);
}

async function playBrowserSpeech(text) {
  if (!window.speechSynthesis) {
    voiceBadge.textContent = "Speech output unavailable";
    return;
  }
  stopBrowserSpeech();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = providerStatus?.speech_settings?.rate || 0.94;
  utterance.pitch = providerStatus?.speech_settings?.pitch || 0.86;
  utterance.volume = providerStatus?.speech_settings?.volume || 0.95;
  const voices = await getBrowserVoices();
  const preferred =
    voices.find((voice) => /natural|online|neural|aria|guy|jenny/i.test(voice.name) && voice.lang?.startsWith("en")) ||
    voices.find((voice) => /david|mark|zira|english/i.test(voice.name) && voice.lang?.startsWith("en")) ||
    voices.find((voice) => voice.lang?.startsWith("en"));
  if (preferred) utterance.voice = preferred;
  utterance.onstart = () => {
    armillaryCore.setSpeechText(text);
    voiceBadge.textContent = "Speaking";
    setVisualState("speaking");
  };
  utterance.onend = () => {
    armillaryCore.setSpeechText("");
    voiceBadge.textContent = micEnabled ? "Listening" : "Voice standby";
    setVisualState(micEnabled ? "listening" : "idle");
  };
  window.speechSynthesis.speak(utterance);
}

async function getBrowserVoices() {
  const immediate = window.speechSynthesis.getVoices();
  if (immediate.length) return immediate;
  return await new Promise((resolve) => {
    const timeout = window.setTimeout(() => resolve(window.speechSynthesis.getVoices()), 700);
    window.speechSynthesis.onvoiceschanged = () => {
      window.clearTimeout(timeout);
      resolve(window.speechSynthesis.getVoices());
    };
  });
}

function stopBrowserSpeech() {
  armillaryCore.setSpeechText("");
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
}

function scheduleListeningReturn() {
  window.clearTimeout(returnTimer);
  returnTimer = window.setTimeout(() => setVisualState(alwaysListening ? "waiting_for_wake_word" : micEnabled ? "listening" : "idle"), 3200);
}

function setVisualState(state, options = {}) {
  if (!stateTargets[state]) state = "idle";
  visualState = state;
  armillaryCore.setState(state);
  document.body.className = `state-${state}`;
  statusLabel.textContent = displayState(state);
  stateButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.state === state));
  if (options.sync !== false) {
    fetch("/api/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state }),
    }).catch(() => {});
  }
}

function setSubtitle(text) {
  subtitleText.textContent = text;
}

function updateSubtitles() {
  subtitlePanel.classList.toggle("is-hidden", !subtitlesEnabled);
  subtitleToggle.textContent = subtitlesEnabled ? "On" : "Off";
  subtitleToggle.setAttribute("aria-pressed", String(subtitlesEnabled));
}

function applyVoiceStatus(status) {
  if (!status) return;
  micEnabled = Boolean(status.microphone_enabled);
  voiceMuted = Boolean(status.muted);
  pushToTalk = Boolean(status.push_to_talk);
  micToggle.textContent = micEnabled ? "Stop Mic" : "Start Mic";
  micStatusLabel.textContent = micEnabled ? "On" : "Off";
  micPrivacyDetail.textContent = alwaysListening
    ? "Always-listening enabled"
    : micEnabled
      ? pushToTalk
        ? "Listening for one command"
        : "Continuous listening until stopped"
      : SpeechRecognition
        ? "Microphone stopped"
        : "Speech recognition unavailable";
  muteToggle.textContent = voiceMuted ? "Muted" : "Mute Off";
  muteToggle.setAttribute("aria-pressed", String(voiceMuted));
  pushToTalkToggle.textContent = pushToTalk ? "Push-to-talk" : "Continuous";
  pushToTalkToggle.setAttribute("aria-pressed", String(pushToTalk));
  confirmVoiceButton.hidden = !status.pending_confirmation_goal;
  voiceBadge.textContent = status.listening
    ? SpeechRecognition ? "Listening" : "Speech API unavailable"
    : status.speaking
      ? `Speaking via ${status.tts_provider || "voice"}`
      : "Voice standby";
  if (!providerStatus) {
    sttProviderLabel.textContent = status.stt_provider || "text_payload";
    ttsProviderLabel.textContent = status.tts_provider || "browser_speech_synthesis";
  }
}

function applyVoiceDiagnostics(diagnostics) {
  if (!diagnostics) return;
  const transcript = diagnostics.last_transcript || "None";
  lastTranscriptLabel.textContent = transcript.length > 42 ? `${transcript.slice(0, 39)}...` : transcript;
  const confidence = Number(diagnostics.confidence || 0);
  const confidenceText = diagnostics.status === "clarification_required" || (confidence > 0 && confidence < 0.45)
    ? `Low confidence: ${Math.round(confidence * 100)}%`
    : confidence > 0
      ? `Confidence: ${Math.round(confidence * 100)}%`
      : "Confidence pending";
  confidenceDetail.textContent = confidenceText;
  audioStateLabel.textContent = diagnostics.rejected ? "Rejected" : displayState(diagnostics.status || "idle");
  const duration = Number(diagnostics.audio_duration_ms || 0);
  const speech = Number(diagnostics.speech_duration_ms || 0);
  const energy = Number(diagnostics.audio_energy || 0);
  audioDetail.textContent = diagnostics.detail || `${duration} ms audio, ${speech} ms speech, energy ${energy.toFixed(3)}`;
}

function applyWakeStatus(wake) {
  if (!wake) return;
  alwaysListening = Boolean(wake.always_listening);
  alwaysListeningToggle.textContent = alwaysListening ? "Always On" : "Always Off";
  alwaysListeningToggle.setAttribute("aria-pressed", String(alwaysListening));
  micStatusLabel.textContent = alwaysListening || micEnabled ? "On" : "Off";
  micPrivacyDetail.textContent = alwaysListening ? "Always-listening enabled" : "Push-to-talk available";
  wakeStateLabel.textContent = displayState(wake.mode || "inactive");
  wakeDetail.textContent = wake.last_event || `Wake phrases: ${(wake.wake_phrases || ["ULTRON", "Hey ULTRON"]).join(", ")}`;
  if (wake.noisy_ignored) {
    vadStateLabel.textContent = "Ignored";
    vadDetail.textContent = wake.last_event || "Noisy or empty input ignored";
  } else if (wake.voice_detected) {
    vadStateLabel.textContent = "Voice detected";
    vadDetail.textContent = wake.wake_word_detected ? `Wake: ${wake.last_wake_phrase || "detected"}` : "Waiting for wake phrase";
  } else {
    vadStateLabel.textContent = "Idle";
    vadDetail.textContent = alwaysListening ? "Monitoring for speech gate events" : "Always-listening disabled";
  }
  if (alwaysListening && (visualState === "idle" || visualState === "inactive")) {
    setVisualState(wake.mode || "waiting_for_wake_word", { sync: false });
  }
}

function applyProviders(payload) {
  if (!payload) return;
  if (payload.speech_settings) {
    armillaryCore.setVoiceProfile(payload.speech_settings);
  }
  const activeStt = payload.active?.stt || payload.voice?.stt_provider || "text_payload";
  const activeTts = payload.active?.tts || payload.voice?.tts_provider || "browser_speech_synthesis";
  const activeCapture = payload.active?.capture || payload.voice_diagnostics?.capture_provider || "browser";
  const configuredStt = payload.configured?.stt || activeStt;
  const configuredTts = payload.configured?.tts || activeTts;
  const configuredCapture = payload.configured?.capture || activeCapture;
  const sttHealth = payload.providers?.stt;
  const ttsHealth = payload.providers?.tts;
  const captureHealth = payload.providers?.capture;
  sttProviderLabel.textContent = activeStt;
  ttsProviderLabel.textContent = activeTts;
  captureProviderLabel.textContent = activeCapture;
  sttProviderDetail.textContent = providerDetail(configuredStt, activeStt, sttHealth);
  ttsProviderDetail.textContent = providerDetail(configuredTts, activeTts, ttsHealth);
  captureProviderDetail.textContent = providerDetail(configuredCapture, activeCapture, captureHealth);
  applyVoiceDiagnostics(payload.voice_diagnostics);
}

function providerDetail(configured, active, health) {
  const fallback = configured !== active ? `Fallback from ${configured}` : "Active";
  if (!health) return fallback;
  const state = health.available ? fallback : `Unavailable: ${health.detail}`;
  return health.fallback_to ? `${state}; using ${health.fallback_to}` : state;
}

function displayState(state) {
  if (state === "inactive") return "Shutdown";
  if (state === "waiting_for_wake_word") return "Wake";
  return String(state || "idle")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function renderHistory(items) {
  voiceHistory.innerHTML = "";
  const recent = [...items].slice(-6).reverse();
  if (!recent.length) {
    const empty = document.createElement("li");
    empty.textContent = "No conversation yet.";
    voiceHistory.append(empty);
    return;
  }
  for (const item of recent) {
    const li = document.createElement("li");
    if (item.user_said !== undefined) {
      const tool = item.tool_selected ? `Tool: ${item.tool_selected}` : "No tool selected";
      li.innerHTML = `<strong>You said</strong>: ${escapeHtml(item.user_said)}<br><strong>Understood</strong>: ${escapeHtml(item.ultron_understood)}<br><strong>ULTRON</strong>: ${escapeHtml(item.spoken_response)}<br><span>${escapeHtml(tool)}</span>`;
    } else {
      const route = item.route ? `Route: ${item.route}` : "Route: conversation";
      li.innerHTML = `<strong>You</strong>: ${escapeHtml(item.user_input)}<br><strong>Understood</strong>: ${escapeHtml(item.understood)}<br><strong>ULTRON</strong>: ${escapeHtml(item.response)}<br><span>${escapeHtml(route)}</span>`;
    }
    voiceHistory.append(li);
  }
}

function renderSkills(skills) {
  skillsList.innerHTML = "";
  if (!skills.length) {
    appendListItem(skillsList, "No skills loaded.");
    return;
  }
  for (const skill of skills) {
    const li = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = skill.name;
    const detail = document.createElement("span");
    detail.textContent = ` ${skill.risk_level}: ${skill.description}`;
    li.append(name, detail);
    skillsList.append(li);
  }
}

function renderKnowledgePanel({ memory = [], sources = [], matches = [], error = "", memoryEnabled: enabled = memoryEnabled }) {
  knowledgeList.innerHTML = "";
  memoryEnabled = Boolean(enabled);
  memoryToggle.textContent = memoryEnabled ? "Memory On" : "Memory Off";
  memoryToggle.setAttribute("aria-pressed", String(memoryEnabled));
  if (error) {
    appendListItem(knowledgeList, error);
    return;
  }
  appendListItem(knowledgeList, `Memory: ${memoryEnabled ? "on" : "off"}`);
  if (matches.length) {
    for (const match of matches) {
      appendListItem(knowledgeList, `${match.title}: ${match.snippet}`);
    }
    return;
  }
  if (sources.length) {
    for (const source of sources.slice(-4).reverse()) {
      appendListItem(knowledgeList, `${source.title} (${source.chunk_count} chunks)`);
    }
  }
  if (memory.length) {
    for (const item of memory.slice(-3).reverse()) {
      appendListItem(knowledgeList, `${item.key}: ${item.value}`);
    }
  }
  if (!sources.length && !memory.length) {
    appendListItem(knowledgeList, "No memory or knowledge sources yet.");
  }
}

function renderRecentTasks(items) {
  recentTasksList.innerHTML = "";
  const recent = [...items].slice(-5).reverse();
  if (!recent.length) {
    appendListItem(recentTasksList, "No recent tasks yet.");
    return;
  }
  for (const task of recent) {
    appendListItem(recentTasksList, `${task.status}: ${task.summary || task.goal || "Task updated"}`);
  }
}

function appendListItem(list, text) {
  const li = document.createElement("li");
  li.textContent = text;
  list.append(li);
}

function buildTaskSubtitle(task) {
  if (!task) return "";
  if (task.summary) return task.summary;
  return `Task ${task.status || "updated"}.`;
}

function formatAssistantSubtitle(payload, fallback) {
  const text = payload?.spoken_response || payload?.subtitle || payload?.response || payload?.message || fallback || "";
  return String(text || "Ready.").replace(/^(?:ULTRON:\s*)+/i, "").trim();
}

function taskNeedsConfirmation(task) {
  if (!task) return false;
  if (task.status === "waiting_for_confirmation") return true;
  return Boolean((task.steps || []).some((step) => step.status === "waiting_for_confirmation"));
}

function showConfirmation(task, context) {
  const step = firstPendingStep(task);
  const policy = step?.policy || {};
  const tool = step?.tool_call?.name || "unknown";
  pendingConfirmation = { ...context, task };
  confirmationTitle.textContent = "Review before execution";
  confirmationMessage.textContent = task?.summary || policy.reason || "ULTRON paused before running this action.";
  confirmationTool.textContent = tool;
  confirmationPermission.textContent = policy.permission_level || policy.risk_level || "confirmation_required";
  confirmationModal.hidden = false;
}

function firstPendingStep(task) {
  return (task?.steps || []).find((step) => step.status === "waiting_for_confirmation") || task?.steps?.[0] || null;
}

async function approvePendingConfirmation() {
  if (!pendingConfirmation) return;
  const { command, source } = pendingConfirmation;
  confirmationModal.hidden = true;
  if (source === "voice") {
    await handleVoiceTranscript("yes confirm");
    return;
  }
  await sendCommand({ command, confirmed: true });
}

async function cancelPendingConfirmation() {
  clearPendingConfirmation();
  confirmVoiceButton.hidden = true;
  await postJson("/api/confirmation/cancel", {}).catch(() => {});
  setSubtitle("Action cancelled.");
  setVisualState(alwaysListening ? "waiting_for_wake_word" : micEnabled ? "listening" : "idle");
}

function clearPendingConfirmation() {
  pendingConfirmation = null;
  confirmationModal.hidden = true;
}

async function fetchJson(url) {
  const response = await fetch(url);
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}

function animate() {
  const elapsed = clock.getElapsedTime();
  const target = stateTargets[visualState];
  const pulse = 1 + Math.sin(elapsed * (visualState === "listening" ? 2.0 : 3.8)) * 0.018;
  const sphereScale = target.scale * pulse;

  root.scale.lerp(new THREE.Vector3(sphereScale, sphereScale, sphereScale), 0.08);
  root.rotation.y += 0.002 + target.ring * 0.004;
  root.rotation.x = Math.sin(elapsed * 0.35) * 0.035;
  sphere.rotation.y -= 0.002;
  sphereUniforms.time.value = elapsed;
  sphereUniforms.intensity.value += (target.glow - sphereUniforms.intensity.value) * 0.08;
  glow.material.opacity += (0.42 + target.glow * 0.22 - glow.material.opacity) * 0.08;
  glow.scale.setScalar(2.75 + target.glow * 0.38 + Math.sin(elapsed * 2.2) * 0.04);

  plasmaLines.children.forEach((line, i) => {
    line.material.opacity += (target.line * (0.36 + (i % 5) * 0.08) - line.material.opacity) * 0.08;
    line.rotation.z += (visualState === "speaking" ? 0.006 : 0.002) * (i % 2 ? 1 : -1);
  });

  ringGroup.children.forEach((ring, i) => {
    ring.material.opacity += ((visualState === "thinking" ? 0.72 : target.ring * 0.24) - ring.material.opacity) * 0.08;
    ring.rotation.z += (0.006 + i * 0.0015) * (visualState === "thinking" ? 2.8 : 0.7);
    ring.rotation.x += 0.0015 * (i % 2 ? 1 : -1);
  });

  particles.rotation.y += target.particle * 0.003;
  particles.rotation.x = Math.sin(elapsed * 0.11) * 0.07;
  particles.material.opacity += ((visualState === "speaking" ? 0.75 : 0.42) - particles.material.opacity) * 0.04;

  armillaryCore.update(elapsed, visualState);
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}

function makeArc(seed) {
  const points = [];
  const radius = 1.055 + (seed % 4) * 0.006;
  const basePhi = 0.38 + (((seed * 37) % 180) / 180) * Math.PI * 0.72;
  const baseTheta = (((seed * 53) % 360) / 360) * Math.PI * 2;
  const length = 0.7 + (((seed * 29) % 100) / 100) * 1.6;
  for (let i = 0; i < 42; i += 1) {
    const t = i / 41;
    const wobble = Math.sin(t * Math.PI * 4 + seed) * 0.06;
    const phi = Math.max(0.18, Math.min(Math.PI - 0.18, basePhi + Math.sin(t * Math.PI * 2 + seed) * 0.22));
    const theta = baseTheta + t * length + wobble;
    points.push(new THREE.Vector3().setFromSpherical(new THREE.Spherical(radius, phi, theta)));
  }
  const material = new THREE.LineBasicMaterial({
    color: seed % 3 === 0 ? 0xa6ff3f : 0x00ff66,
    transparent: true,
    opacity: 0.35,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  return new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material);
}

function makeParticles() {
  const count = 780;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const radius = 3.5 + Math.random() * 8.5;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = Math.sin(phi) * Math.cos(theta) * radius;
    positions[i * 3 + 1] = Math.sin(phi) * Math.sin(theta) * radius * 0.72;
    positions[i * 3 + 2] = Math.cos(phi) * radius - 2.2;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      color: 0x00ff66,
      size: 0.025,
      transparent: true,
      opacity: 0.42,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
  );
}

function makeGlowTexture() {
  const size = 256;
  const glowCanvas = document.createElement("canvas");
  glowCanvas.width = size;
  glowCanvas.height = size;
  const ctx = glowCanvas.getContext("2d");
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 8, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(0,255,102,0.78)");
  gradient.addColorStop(0.34, "rgba(0,255,102,0.26)");
  gradient.addColorStop(0.68, "rgba(0,255,102,0.07)");
  gradient.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(glowCanvas);
}
