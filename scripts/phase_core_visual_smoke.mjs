import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { PNG } = require("pngjs");
const { chromium } = require("playwright");

const root = path.resolve(".");
const webRoot = path.join(root, "web");
const outDir = path.join(root, "docs", "phase13_browser_smoke");
fs.mkdirSync(outDir, { recursive: true });

const apiPayload = {
  visual_state: "idle",
  subtitles_enabled: true,
  last_subtitle: "ULTRON 2.7 visual smoke.",
  recent_tasks: [],
  knowledge_sources: [],
  status: "ok",
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname === "/favicon.ico") {
    res.writeHead(204);
    res.end();
    return;
  }
  if (url.pathname.startsWith("/api/")) {
    const payload = url.pathname === "/api/voice/providers"
      ? { status: "ok", active: { stt: "text_payload", tts: "browser_speech_synthesis" }, configured: { stt: "text_payload", tts: "browser_speech_synthesis" }, providers: {}, speech_settings: { rate: 0.92, pitch: 0.72, volume: 0.95 } }
      : url.pathname === "/api/voice/status"
        ? { status: "ok", voice: { microphone_enabled: false, muted: false, push_to_talk: true }, wake: { always_listening: false, mode: "inactive" }, history: [] }
        : apiPayload;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(payload));
    return;
  }
  const relative = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const file = path.resolve(webRoot, relative);
  if (!file.startsWith(webRoot) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404);
    res.end("not found");
    return;
  }
  const type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html";
  res.writeHead(200, { "Content-Type": type });
  fs.createReadStream(file).pipe(res);
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;
const url = `http://127.0.0.1:${port}`;

const executablePath = findBrowserExecutable();
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});

await page.goto(url, { waitUntil: "networkidle" });
await page.waitForTimeout(2200);

const states = ["Thinking", "Listening", "Speaking", "Wake", "Shutdown", "Idle"];
const metrics = {};
for (const label of states) {
  await page.getByRole("button", { name: label }).click();
  await page.waitForTimeout(label === "Shutdown" ? 1200 : 900);
  metrics[label.toLowerCase()] = await screenshotMetrics(page, path.join(outDir, `state-${label.toLowerCase()}.png`));
}
await page.getByRole("button", { name: "Idle" }).click();
await page.waitForTimeout(600);
metrics.desktop = await screenshotMetrics(page, path.join(outDir, "armillary-core-desktop.png"));

await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(800);
metrics.mobile = await screenshotMetrics(page, path.join(outDir, "armillary-core-mobile.png"));

await browser.close();
server.close();

const failed = Object.entries(metrics).filter(([, metric]) => metric.greenPixels < 120 || metric.brightPixels < 12);
const result = {
  status: failed.length || errors.length ? "failed" : "ok",
  metrics,
  errors,
  screenshots: ["docs/phase13_browser_smoke/armillary-core-desktop.png", "docs/phase13_browser_smoke/armillary-core-mobile.png"],
};
console.log(JSON.stringify(result, null, 2));
if (result.status !== "ok") process.exit(1);

async function screenshotMetrics(page, screenshotPath) {
  const buffer = await page.screenshot({ path: screenshotPath, fullPage: true });
  const png = PNG.sync.read(buffer);
  let greenPixels = 0;
  let brightPixels = 0;
  let sampledPixels = 0;
  const stride = 3;
  for (let y = 0; y < png.height; y += stride) {
    for (let x = 0; x < png.width; x += stride) {
      const i = (png.width * y + x) << 2;
      const r = png.data[i];
      const g = png.data[i + 1];
      const b = png.data[i + 2];
      sampledPixels += 1;
      if (g > 55 && g > r * 1.35 && g > b * 1.15) greenPixels += 1;
      if (g > 115 && r > 8 && b < g * 0.85) brightPixels += 1;
    }
  }
  return { greenPixels, brightPixels, sampledPixels, width: png.width, height: png.height };
}

function findBrowserExecutable() {
  const candidates = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  ];
  return candidates.find((candidate) => fs.existsSync(candidate));
}
