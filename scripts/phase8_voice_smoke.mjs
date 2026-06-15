import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const root = process.cwd();
const webRoot = path.join(root, "web");
const outDir = path.join(root, "docs", "phase8_browser_smoke");
fs.mkdirSync(outDir, { recursive: true });

const mime = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "text/javascript",
  ".json": "application/json",
};

let visualState = "idle";
let subtitlesEnabled = true;
let lastSubtitle = "ULTRON 2.7 online.";
let voice = {
  microphone_enabled: false,
  listening: false,
  muted: false,
  speaking: false,
  push_to_talk: true,
  pending_confirmation_goal: null,
};
const history = [];

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname === "/api/status") {
    sendJson(res, { status: "ok", visual_state: visualState, subtitles_enabled: subtitlesEnabled, last_subtitle: lastSubtitle });
    return;
  }
  if (url.pathname === "/api/voice/status") {
    sendJson(res, { status: "ok", voice, history });
    return;
  }
  if (url.pathname === "/api/voice/start" && req.method === "POST") {
    collectJson(req).then((body) => {
      voice.microphone_enabled = true;
      voice.listening = true;
      voice.push_to_talk = typeof body.push_to_talk === "boolean" ? body.push_to_talk : voice.push_to_talk;
      visualState = "listening";
      sendJson(res, { status: "ok", visual_state: visualState, voice, history });
    });
    return;
  }
  if (url.pathname === "/api/voice/stop" && req.method === "POST") {
    voice.microphone_enabled = false;
    voice.listening = false;
    visualState = "idle";
    sendJson(res, { status: "ok", visual_state: visualState, voice, history });
    return;
  }
  if (url.pathname === "/api/voice/transcribe" && req.method === "POST") {
    collectJson(req).then((body) => {
      const transcript = String(body.transcript || "").replace(/^ULTRON,\s*/i, "");
      const record = {
        user_said: body.transcript || transcript,
        ultron_understood: transcript,
        tool_selected: "create_note",
        action_result: "dry_run: Would create note: demo.md",
        spoken_response: `Completed mock voice command: ${transcript}`,
        needs_confirmation: false,
      };
      history.push(record);
      visualState = "speaking";
      lastSubtitle = `You: ${body.transcript || transcript}\nULTRON: ${record.spoken_response}`;
      sendJson(res, { status: "ok", visual_state: visualState, voice, history, record, spoken_response: record.spoken_response, subtitle: lastSubtitle, task: { status: "completed", steps: [{ tool_call: { name: "create_note" } }] } });
    });
    return;
  }
  if (url.pathname === "/api/speak" && req.method === "POST") {
    collectJson(req).then((body) => {
      if (typeof body.muted === "boolean") voice.muted = body.muted;
      voice.speaking = !voice.muted && body.action !== "stop";
      sendJson(res, { status: "ok", voice, history, speech: { status: body.action === "stop" ? "stopped" : "delegated" } });
    });
    return;
  }
  if (url.pathname === "/api/subtitles/toggle" && req.method === "POST") {
    collectJson(req).then((body) => {
      subtitlesEnabled = typeof body.enabled === "boolean" ? body.enabled : !subtitlesEnabled;
      sendJson(res, { status: "ok", subtitles_enabled: subtitlesEnabled });
    });
    return;
  }
  if (url.pathname === "/api/state" && req.method === "POST") {
    collectJson(req).then((body) => {
      visualState = ["idle", "listening", "thinking", "speaking"].includes(body.state) ? body.state : visualState;
      sendJson(res, { status: "ok", visual_state: visualState });
    });
    return;
  }
  const rel = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const file = path.resolve(webRoot, rel);
  if (!file.startsWith(path.resolve(webRoot)) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404);
    res.end("not found");
    return;
  }
  res.writeHead(200, { "Content-Type": mime[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

await new Promise((resolve) => server.listen(9877, "127.0.0.1", resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  server.close();
  console.log(JSON.stringify({ browser_available: false, reason: String(error).split("\n")[0], outDir }, null, 2));
  process.exit(0);
}

const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
await page.goto("http://127.0.0.1:9877/", { waitUntil: "networkidle" });
await page.waitForSelector("#ultron-scene");
await page.waitForSelector("#micToggle");
await page.getByRole("button", { name: "Mock Voice" }).click();
await page.waitForTimeout(900);
const subtitle = await page.locator("#subtitleText").textContent();
const historyCount = await page.locator("#voiceHistory li").count();
const controls = await page.locator(".voice-console button").count();
await page.screenshot({ path: path.join(outDir, "voice-mode.png"), fullPage: true });
await browser.close();
server.close();

console.log(JSON.stringify({ subtitle, historyCount, controls, outDir }, null, 2));

function sendJson(res, payload) {
  const data = JSON.stringify(payload);
  res.writeHead(200, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) });
  res.end(data);
}

async function collectJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    return {};
  }
}
