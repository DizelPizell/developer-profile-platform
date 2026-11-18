// Renders a mockup page to ../<name>.png at 2x, full height, through Chrome DevTools.
// Usage: node render.mjs project-page   (CHROME = path to chrome or headless shell)
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const name = process.argv[2];
const here = fileURLToPath(new URL(".", import.meta.url));
const chrome = spawn(process.env.CHROME, ["--headless", "--remote-debugging-port=9333", "--no-first-run", "about:blank"]);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

let target;
for (let i = 0; i < 50 && !target; i++) {
  await wait(200);
  target = await fetch("http://127.0.0.1:9333/json").then((r) => r.json()).then((t) => t.find((x) => x.type === "page")).catch(() => null);
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); pending.get(m.id)?.(m.result); });
const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });

await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 2, mobile: false });
await send("Page.navigate", { url: pathToFileURL(`${here}${name}.html`).href });
await wait(1500);
await send("Runtime.evaluate", { expression: "document.fonts.ready", awaitPromise: true });
const { result } = await send("Runtime.evaluate", { expression: "document.documentElement.scrollHeight" });
await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: result.value, deviceScaleFactor: 2, mobile: false });
// PREVIEW="y,height" writes only that band at 1x to $PREVIEW_OUT, for checking details.
const [y, h] = (process.env.PREVIEW ?? "").split(",").map(Number);
const clip = process.env.PREVIEW ? { clip: { x: 0, y, width: 1280, height: h, scale: 0.5 } } : {};
const shot = await send("Page.captureScreenshot", { format: "png", ...clip });
writeFileSync(process.env.PREVIEW ? process.env.PREVIEW_OUT : `${here}../${name}.png`, Buffer.from(shot.data, "base64"));
ws.close();
chrome.kill();
