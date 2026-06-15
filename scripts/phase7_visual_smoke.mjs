import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const root = process.cwd();
const webRoot = path.join(root, "web");
const outDir = path.join(root, "docs", "phase7_browser_smoke");
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

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname === "/api/status") {
    sendJson(res, { status: "ok", visual_state: visualState, subtitles_enabled: subtitlesEnabled, last_subtitle: lastSubtitle });
    return;
  }
  if (url.pathname === "/api/memory") {
    sendJson(res, { status: "ok", memory: [] });
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
  if (url.pathname === "/api/command" && req.method === "POST") {
    collectJson(req).then((body) => {
      visualState = "speaking";
      lastSubtitle = `Completed mock task for: ${body.command || "command"}`;
      sendJson(res, { status: "ok", visual_state: visualState, subtitle: lastSubtitle, task: { status: "completed", summary: lastSubtitle, steps: [] } });
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

await new Promise((resolve) => server.listen(9876, "127.0.0.1", resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  server.close();
  console.log(JSON.stringify({ browser_available: false, reason: String(error).split("\n")[0], outDir }, null, 2));
  process.exit(0);
}
const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
await page.goto("http://127.0.0.1:9876/", { waitUntil: "networkidle" });
await page.waitForSelector("#ultron-scene");
await page.waitForSelector("#subtitleText");
await page.screenshot({ path: path.join(outDir, "idle.png"), fullPage: true });

for (const state of ["Listening", "Thinking", "Speaking"]) {
  await page.getByRole("button", { name: state }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, `${state.toLowerCase()}.png`), fullPage: true });
}

await page.getByPlaceholder("Type a command for ULTRON...").fill("create note visual interface");
await page.getByRole("button", { name: "Send" }).click();
await page.waitForTimeout(900);
const subtitle = await page.locator("#subtitleText").textContent();
const canvasBox = await page.locator("#ultron-scene").boundingBox();
const buttonCount = await page.locator(".state-controls button").count();
await page.screenshot({ path: path.join(outDir, "command-result.png"), fullPage: true });
await browser.close();
server.close();

console.log(JSON.stringify({ subtitle, canvasBox, buttonCount, outDir }, null, 2));

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
