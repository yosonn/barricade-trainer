#!/usr/bin/env node
/*
 * Browser bridge for Barricade.gg live practice.
 *
 * This script intentionally defaults to assist-only mode: it watches the page,
 * reconstructs the move history, and asks the Python engine for a move. It does
 * not auto-click live human games. Use it to prevent transcription mistakes and
 * to keep the local trainer synchronized with the real board.
 */

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

function parseArgs(argv) {
  const args = {
    url: "https://barricade.gg/computer",
    engine: "expert",
    startTurn: "auto",
    intervalMs: 2500,
    python: process.env.PYTHON || "python",
    profileDir: path.join(process.cwd(), "output", "barricade-live-profile"),
    copy: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--copy") args.copy = true;
    else if (arg === "--url") args.url = argv[++i];
    else if (arg === "--engine") args.engine = argv[++i];
    else if (arg === "--start-turn") args.startTurn = argv[++i];
    else if (arg === "--interval-ms") args.intervalMs = Number(argv[++i]);
    else if (arg === "--python") args.python = argv[++i];
    else if (arg === "--profile-dir") args.profileDir = argv[++i];
    else if (arg === "--help") {
      console.log(`Usage: node tools/barricade_external/barricade_gg_live_bridge.js [options]

Options:
  --url URL              Page to open, default https://barricade.gg/computer
  --engine NAME          expert|hybrid|mcts|alpha-beta, default expert
  --start-turn SIDE      auto|red|blue, default auto
  --interval-ms N        Poll interval, default 2500
  --python PATH          Python executable for the local recommender
  --profile-dir PATH     Persistent browser profile, default output/barricade-live-profile
  --copy                 Copy the latest recommendation to clipboard when available
`);
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function requirePlaywright() {
  try {
    return require("playwright");
  } catch (error) {
    console.error("Missing npm package: playwright");
    console.error("Install once with: npm install -D playwright");
    console.error("Or run through npx in a shell that allows npm downloads.");
    process.exit(2);
  }
}

function appendObservation(observations, label, value) {
  if (!value) return;
  const text = String(value);
  if (!text.trim()) return;
  observations.push(`\n--- ${label} ---\n${text.slice(-12000)}`);
  if (observations.length > 80) observations.splice(0, observations.length - 80);
}

function runRecommendation(args, observationText) {
  const script = path.join(process.cwd(), "tools", "barricade_external", "live_sync_assistant.py");
  const result = spawnSync(
    args.python,
    [
      script,
      "--text",
      observationText,
      "--start-turn",
      args.startTurn,
      "--engine",
      args.engine,
      "--json",
    ],
    { encoding: "utf8", maxBuffer: 1024 * 1024 * 5 },
  );
  if (result.status !== 0) {
    return { ok: false, error: (result.stderr || result.stdout || "").trim() };
  }
  try {
    return { ok: true, data: JSON.parse(result.stdout) };
  } catch (error) {
    return { ok: false, error: `Bad recommender JSON: ${error.message}` };
  }
}

async function pageSnapshot(page) {
  return page.evaluate(() => {
    const storage = {};
    for (const storeName of ["localStorage", "sessionStorage"]) {
      try {
        const store = window[storeName];
        storage[storeName] = {};
        for (let i = 0; i < store.length; i += 1) {
          const key = store.key(i);
          storage[storeName][key] = store.getItem(key);
        }
      } catch {
        storage[storeName] = {};
      }
    }
    return {
      title: document.title,
      url: location.href,
      text: document.body ? document.body.innerText : "",
      storage,
    };
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { chromium } = requirePlaywright();
  fs.mkdirSync(args.profileDir, { recursive: true });

  const context = await chromium.launchPersistentContext(args.profileDir, {
    headless: false,
    viewport: { width: 1440, height: 980 },
  });
  const page = context.pages()[0] || await context.newPage();
  const observations = [];
  let lastKey = "";
  let lastError = "";

  page.on("websocket", (ws) => {
    appendObservation(observations, "websocket-url", ws.url());
    ws.on("framereceived", (frame) => appendObservation(observations, "ws-received", frame.payload));
    ws.on("framesent", (frame) => appendObservation(observations, "ws-sent", frame.payload));
  });
  page.on("response", async (response) => {
    const contentType = response.headers()["content-type"] || "";
    if (!/json|text|javascript/.test(contentType)) return;
    try {
      appendObservation(observations, `response ${response.url()}`, await response.text());
    } catch {
      // Some responses are already consumed by the page; ignore them.
    }
  });

  await page.goto(args.url, { waitUntil: "domcontentloaded" });
  console.log("Browser opened. Log in or navigate to the game, then leave this script running.");
  console.log("Assist-only mode: recommendations are printed here; live human auto-clicking is intentionally disabled.");

  setInterval(async () => {
    try {
      const snap = await pageSnapshot(page);
      appendObservation(observations, "page", JSON.stringify(snap));
      const result = runRecommendation(args, observations.join("\n"));
      if (!result.ok) {
        if (result.error !== lastError) {
          lastError = result.error;
          console.log(`[sync] waiting for legal history: ${result.error || "-"}`);
        }
        return;
      }
      lastError = "";
      const rec = result.data;
      const key = `${rec.start_turn}|${rec.history.join(" ")}|${rec.action}`;
      if (key === lastKey) return;
      lastKey = key;
      const line = [
        `[move ${rec.history.length + 1}]`,
        `start=${rec.start_turn}`,
        `turn=${rec.turn}`,
        `engine=${rec.resolved_engine}`,
        `red=${rec.red}(${rec.red_dist})`,
        `blue=${rec.blue}(${rec.blue_dist})`,
        `recommend=${rec.action || "-"}`,
      ].join(" ");
      console.log(line);
      if (args.copy && rec.action) {
        await page.evaluate((text) => navigator.clipboard.writeText(text), rec.action);
      }
    } catch (error) {
      console.log(`[sync] ${error.message}`);
    }
  }, args.intervalMs);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
