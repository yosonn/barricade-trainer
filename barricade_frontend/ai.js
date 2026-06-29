const files = "abcdefghi";

const historyEl = document.querySelector("#history");
const actionInput = document.querySelector("#actionInput");
const recommendationEl = document.querySelector("#recommendation");
const statusText = document.querySelector("#statusText");
const scoreText = document.querySelector("#scoreText");
const winRateText = document.querySelector("#winRateText");
const boardEl = document.querySelector("#board");
const modeHuman = document.querySelector("#modeHuman");
const modeTopHuman = document.querySelector("#modeTopHuman");
const modeAuto = document.querySelector("#modeAuto");
const playerFirst = document.querySelector("#playerFirst");
const computerFirst = document.querySelector("#computerFirst");
const modeHint = document.querySelector("#modeHint");
const mainBtn = document.querySelector("#mainBtn");
const aiStepBtn = document.querySelector("#aiStepBtn");
const autoBtn = document.querySelector("#autoBtn");
const undoBtn = document.querySelector("#undoBtn");
const analyzeBtn = document.querySelector("#analyzeBtn");
const resetBtn = document.querySelector("#resetBtn");
const replayStartBtn = document.querySelector("#replayStartBtn");
const replayBackBtn = document.querySelector("#replayBackBtn");
const replayPlayBtn = document.querySelector("#replayPlayBtn");
const replayForwardBtn = document.querySelector("#replayForwardBtn");
const replayLiveBtn = document.querySelector("#replayLiveBtn");
const timeLimit = document.querySelector("#timeLimit");
const depthLimit = document.querySelector("#depthLimit");
const engineSelect = document.querySelector("#engineSelect");
const redTimeLimit = document.querySelector("#redTimeLimit");
const redDepthLimit = document.querySelector("#redDepthLimit");
const redEngineSelect = document.querySelector("#redEngineSelect");
const blueTimeLimit = document.querySelector("#blueTimeLimit");
const blueDepthLimit = document.querySelector("#blueDepthLimit");
const blueEngineSelect = document.querySelector("#blueEngineSelect");

let mode = "human";
let humanSide = "red";
let firstMover = "player";
let latest = null;
let autoTimer = null;
let replayTimer = null;
let replayIndex = null;
let previewWall = "";
let touchWallOrient = "";
let lastWallTouchAt = 0;
let lastComputerAction = null;
let autoBusy = false;
let replayBusy = false;
let analyzeRequestId = 0;

const t = {
  red: "\u7d05\u65b9",
  blue: "\u85cd\u65b9",
  loading: "\u5206\u6790\u4e2d...",
  steps: "\u6b65\u5230\u7d42\u9ede",
  walls: "\u5269\u9918\u7246",
  inputError: "\u8f38\u5165\u6709\u554f\u984c\uff1a",
  invalid: "\u9019\u6b65\u4e0d\u5408\u6cd5\uff0c\u5df2\u4fdd\u7559\u8f38\u5165\u6846\uff0c\u4e0d\u6703\u5beb\u5165\u68cb\u8b5c\uff1a",
  noWalls: "\u5269\u9918\u7246\u70ba 0\uff0c\u4e0d\u80fd\u518d\u653e\u7246\u3002",
  noHistory: "\u76ee\u524d\u6c92\u6709\u53ef\u4ee5\u56de\u5fa9\u7684\u4e0a\u4e00\u6b65\u3002",
  undoDone: "\u5df2\u56de\u5fa9\u4e0a\u4e00\u6b65\u3002",
  preview: "\u9810\u89bd\uff1a",
};

function sideName(side) {
  return side === "red" ? t.red : t.blue;
}

function other(side) {
  return side === "red" ? "blue" : "red";
}

function shouldFlipBoard() {
  return false;
}

function coordToXY(coord) {
  return { x: files.indexOf(coord[0]), y: Number(coord[1]) - 1 };
}

function xyToCoord(x, y) {
  return `${files[x]}${y + 1}`;
}

function visualXY(x, y) {
  return { x, y };
}

function boardXYFromDisplayCell(col, displayRow) {
  return { x: col, y: 8 - displayRow };
}

function centerPercent(coord) {
  const actual = coordToXY(coord);
  const visual = visualXY(actual.x, actual.y);
  return {
    left: ((visual.x + 0.5) / 9) * 100,
    top: ((8 - visual.y + 0.5) / 9) * 100,
  };
}

function historyTokens() {
  return historyEl.value.trim().split(/\s+/).filter(Boolean);
}

function historyWithActions(actions) {
  const clean = actions.map((action) => action.trim().toLowerCase()).filter(Boolean);
  return `${historyEl.value.trim()} ${clean.join(" ")}`.trim();
}

function sideToMoveForHistory(history) {
  const count = history.trim().split(/\s+/).filter(Boolean).length;
  const start = currentStartTurn();
  if (count % 2 === 0) return start;
  return start === "red" ? "blue" : "red";
}

function searchParamsForSide(side) {
  if (mode !== "auto") {
    return { time: Number(timeLimit.value), depth: Number(depthLimit.value), engine: engineSelect.value };
  }
  if (side === "blue") {
    return { time: Number(blueTimeLimit.value), depth: Number(blueDepthLimit.value), engine: blueEngineSelect.value };
  }
  return { time: Number(redTimeLimit.value), depth: Number(redDepthLimit.value), engine: redEngineSelect.value };
}

function activeSearchParams(history) {
  return searchParamsForSide(sideToMoveForHistory(history));
}

function isWallCode(action) {
  return /^[hv][a-h][1-8]$/i.test(action.trim());
}

function wallLimitMessage(actions) {
  if (!latest) return "";
  let turn = latest.turn;
  let redWalls = latest.red.walls;
  let blueWalls = latest.blue.walls;
  for (const raw of actions) {
    const action = raw.trim().toLowerCase();
    if (isWallCode(action)) {
      const left = turn === "red" ? redWalls : blueWalls;
      if (left <= 0) return `${sideName(turn)}${t.noWalls}`;
      if (turn === "red") redWalls -= 1;
      else blueWalls -= 1;
    }
    turn = other(turn);
  }
  return "";
}

function currentStartTurn() {
  if (mode === "topHuman") return firstMover === "player" ? "blue" : "red";
  return "red";
}

function syncSidesForMode() {
  if (mode === "topHuman") {
    humanSide = "blue";
    return;
  }
  if (mode === "auto") {
    humanSide = "red";
    firstMover = "computer";
    return;
  }
  humanSide = firstMover === "player" ? "red" : "blue";
}

async function fetchAnalysis(history, options = {}) {
  const shouldRecommend = options.recommendForTurn ?? true;
  const params = shouldRecommend ? activeSearchParams(history) : { time: 0.05, depth: 1, engine: engineSelect.value };
  const controller = new AbortController();
  const timeoutMs = Math.max(8000, Number(params.time || 0) * 1000 + 5000);
  const timeoutId = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
  let response;
  try {
    response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        history,
        user_side: humanSide,
        start_turn: currentStartTurn(),
        recommend_for_turn: shouldRecommend,
        time: params.time,
        depth: params.depth,
        engine: params.engine,
      }),
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
  return response.json();
}

function analysisErrorMessage(error) {
  if (error?.name === "AbortError" || error === "timeout") {
    return "分析逾時，已停止本次思考。請再試一次，或改用較短秒數/其他模型。";
  }
  return `分析失敗：${error?.message || error}`;
}

async function analyze(message = "") {
  const requestId = ++analyzeRequestId;
  stopReplay();
  replayIndex = null;
  lastComputerAction = null;
  statusText.textContent = t.loading;
  try {
    const payload = await fetchAnalysis(historyEl.value);
    if (requestId !== analyzeRequestId) return;
    if (!payload.ok) {
      statusText.textContent = `${t.inputError}${payload.error}`;
      return;
    }
    latest = payload.state;
    render(latest);
    if (message) statusText.textContent = message;
  } catch (error) {
    if (requestId !== analyzeRequestId) return;
    statusText.textContent = analysisErrorMessage(error);
    stopAuto();
  }
}

async function tryCommit(actions, message = "", options = {}) {
  stopReplay();
  replayIndex = null;
  const wallMessage = wallLimitMessage(actions);
  if (wallMessage) {
    statusText.textContent = wallMessage;
    return false;
  }
  const candidateHistory = historyWithActions(actions);
  const nextThinkSide = sideToMoveForHistory(candidateHistory);
  const requestId = ++analyzeRequestId;
  statusText.textContent = `${sideName(nextThinkSide)}\u601d\u8003\u4e2d...`;
  try {
    const payload = await fetchAnalysis(candidateHistory);
    if (requestId !== analyzeRequestId) return false;
    if (!payload.ok) {
      statusText.textContent = `${t.invalid}${payload.error}`;
      actionInput.focus();
      return false;
    }
    historyEl.value = candidateHistory;
    actionInput.value = "";
    latest = payload.state;
    lastComputerAction = options.computerAction || null;
    render(latest);
    if (message) statusText.textContent = message;
    return true;
  } catch (error) {
    if (requestId !== analyzeRequestId) return false;
    statusText.textContent = analysisErrorMessage(error);
    stopAuto();
    return false;
  }
}

function render(state) {
  document.querySelector("#redPos").textContent = state.red.pos;
  document.querySelector("#bluePos").textContent = state.blue.pos;
  document.querySelector("#redDist").textContent = `${state.red.dist} ${t.steps}`;
  document.querySelector("#blueDist").textContent = `${state.blue.dist} ${t.steps}`;
  document.querySelector("#redInfo").textContent = `${t.walls} ${state.red.walls}`;
  document.querySelector("#blueInfo").textContent = `${t.walls} ${state.blue.walls}`;
  document.querySelector("#turnText").textContent = state.winner ? `${sideName(state.winner)}\u7372\u52dd` : `\u8f2a\u5230${sideName(state.turn)}`;
  recommendationEl.textContent = state.recommendation || "-";
  scoreText.textContent = state.recommendation ? `\u5206\u6578 ${Number(state.score).toFixed(1)}\uff5c\u6df1\u5ea6 ${state.searched_depth}\uff5c\u6a21\u578b ${state.resolved_engine || state.engine || "-"}` : "\u7b49\u5f85\u5206\u6790";
  winRateText.textContent = `\u7d05\u65b9 ${state.red_win_rate ?? "-"}%\uff5c\u85cd\u65b9 ${state.blue_win_rate ?? "-"}%`;

  const humanTurn = hasHumanPlayer() && state.turn === humanSide && !state.winner && replayIndex === null;
  mainBtn.disabled = !humanTurn;
  aiStepBtn.disabled = Boolean(state.winner) || replayIndex !== null || humanTurn;
  autoBtn.disabled = Boolean(state.winner) || replayIndex !== null;
  undoBtn.disabled = historyTokens().length === 0 || replayIndex !== null;
  updateModeText(state, humanTurn);
  drawBoard(state);
}

function hasHumanPlayer() {
  return mode === "human" || mode === "topHuman";
}

function updateModeText(state, humanTurn) {
  const firstLabel = firstMover === "player" ? "\u73a9\u5bb6\u5148\u624b" : "\u96fb\u8166\u5148\u624b";
  if (mode === "topHuman") modeHint.textContent = `\u4f60\u63a7\u5236\u4e0a\u65b9\u85cd\u65b9\uff0c\u96fb\u8166\u63a7\u5236\u4e0b\u65b9\u7d05\u65b9\u3002${firstLabel}\u3002`;
  else if (mode === "human") {
    const playerSide = humanSide === "red" ? "\u7d05\u65b9" : "\u85cd\u65b9";
    modeHint.textContent = `\u73a9\u5bb6\u5c0d\u96fb\u8166\u3002${firstLabel}\uff0c\u73a9\u5bb6\u70ba${playerSide}\u3002`;
  }
  else modeHint.textContent = "\u96d9\u96fb\u8166\u4e92\u73a9\uff0c\u6703\u4f9d\u7167\u76ee\u524d\u641c\u5c0b\u79d2\u6578\u8207\u6700\u5927\u6df1\u5ea6\u81ea\u52d5\u6c7a\u7b56\u3002";

  if (state.winner) statusText.textContent = `${sideName(state.winner)}\u7372\u52dd\uff0c\u53ef\u4ee5\u4f7f\u7528\u56de\u653e\u63a7\u5236\u6aa2\u8996\u68cb\u5c40\u3002`;
  else if (replayIndex !== null) statusText.textContent = `\u56de\u653e\u4e2d\uff1a\u7b2c ${replayIndex} / ${historyTokens().length} \u624b`;
  else if (mode === "auto") statusText.textContent = "\u96d9\u96fb\u8166\u6a21\u5f0f\uff0c\u53ef\u4ee5\u6309\u958b\u59cb\u81ea\u52d5\u5c0d\u6230\u3002";
  else if (humanTurn) statusText.textContent = "\u8f2a\u5230\u73a9\u5bb6\uff0c\u53ef\u4ee5\u8f38\u5165\u4ee3\u78bc\u3001\u9ede\u68cb\u76e4\u6216\u62d6\u66f3\u653e\u7246\u3002";
  else statusText.textContent = `\u8f2a\u5230\u96fb\u8166${sideName(state.turn)}\uff0c\u53ef\u4ee5\u6309\u96fb\u8166\u8d70\u4e00\u6b65\u6216\u958b\u59cb\u81ea\u52d5\u3002`;
}

function drawBoard(state) {
  boardEl.innerHTML = "";
  for (let displayRow = 0; displayRow < 9; displayRow += 1) {
    for (let col = 0; col < 9; col += 1) {
      const actual = boardXYFromDisplayCell(col, displayRow);
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.dataset.coord = xyToCoord(actual.x, actual.y);
      if (actual.y === 8) cell.classList.add("goal-red");
      if (actual.y === 0) cell.classList.add("goal-blue");
      if (col === 0 || displayRow === 8) {
        const label = document.createElement("span");
        label.className = "coord";
        label.textContent = col === 0 ? String(actual.y + 1) : files[actual.x];
        if (col === 0 && displayRow === 8) label.textContent = xyToCoord(actual.x, actual.y);
        cell.appendChild(label);
      }
      boardEl.appendChild(cell);
    }
  }
  for (const wall of state.walls) drawWall(wall);
  drawLastComputerAction();
  drawPawn(state.red.pos, "red");
  drawPawn(state.blue.pos, "blue");
  if (previewWall) drawWall(previewWall, true);
}

function drawLastComputerAction() {
  if (!lastComputerAction || replayIndex !== null) return;
  if (lastComputerAction.kind === "wall") drawWall(lastComputerAction.action, false, "computer-last");
  else drawMoveArrow(lastComputerAction.from, lastComputerAction.to, lastComputerAction.side);
}

function drawMoveArrow(from, to, side) {
  const start = centerPercent(from);
  const end = centerPercent(to);
  const dx = end.left - start.left;
  const dy = end.top - start.top;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;
  const arrow = document.createElement("div");
  arrow.className = `move-arrow ${side}`;
  arrow.style.left = `${start.left}%`;
  arrow.style.top = `${start.top}%`;
  arrow.style.width = `${distance}%`;
  arrow.style.transform = `rotate(${angle}deg)`;
  boardEl.appendChild(arrow);
}

function drawPawn(coord, color) {
  const { left, top } = centerPercent(coord);
  const pawn = document.createElement("div");
  pawn.className = `pawn ${color}`;
  pawn.style.left = `${left}%`;
  pawn.style.top = `${top}%`;
  boardEl.appendChild(pawn);
}

function transformedWall(code) {
  return code;
}

function drawWall(code, preview = false, extraClass = "") {
  const visualCode = transformedWall(code);
  const orient = visualCode[0];
  const { x, y } = coordToXY(visualCode.slice(1));
  const wall = document.createElement("div");
  const label = document.createElement("div");
  wall.className = `wall ${orient}${preview ? " preview-wall" : ""}${extraClass ? ` ${extraClass}-wall` : ""}`;
  label.className = `wall-label${preview ? " preview-label" : ""}${extraClass ? ` ${extraClass}-label` : ""}`;
  label.textContent = preview ? `${t.preview}${code}` : code;
  if (orient === "h") {
    wall.style.left = `${(x / 9) * 100}%`;
    wall.style.top = `${((8 - y) / 9) * 100}%`;
    wall.style.width = `${(2 / 9) * 100}%`;
    label.style.left = `${((x + 1) / 9) * 100}%`;
    label.style.top = `${((8 - y) / 9) * 100}%`;
    label.style.transform = "translate(-50%, -170%)";
  } else {
    wall.style.left = `${((x + 1) / 9) * 100}%`;
    wall.style.top = `${((8 - (y + 1)) / 9) * 100}%`;
    wall.style.height = `${(2 / 9) * 100}%`;
    label.style.left = `${((x + 1) / 9) * 100}%`;
    label.style.top = `${((8 - y) / 9) * 100}%`;
    label.style.transform = "translate(18%, -50%)";
  }
  boardEl.appendChild(wall);
  boardEl.appendChild(label);
}

function squareFromPointer(event) {
  const cellEl = event.target.closest(".cell");
  if (cellEl && boardEl.contains(cellEl) && cellEl.dataset.coord) {
    return cellEl.dataset.coord;
  }
  const rect = boardEl.getBoundingClientRect();
  const cell = rect.width / 9;
  const col = Math.floor((event.clientX - rect.left) / cell);
  const displayRow = Math.floor((event.clientY - rect.top) / cell);
  if (col < 0 || col > 8 || displayRow < 0 || displayRow > 8) return "";
  const actual = boardXYFromDisplayCell(col, displayRow);
  return xyToCoord(actual.x, actual.y);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function visualWallToActual(code) {
  return code;
}

function wallFromPointer(event, orient) {
  const rect = boardEl.getBoundingClientRect();
  const cell = rect.width / 9;
  const relX = event.clientX - rect.left;
  const relY = event.clientY - rect.top;
  if (relX < 0 || relY < 0 || relX > rect.width || relY > rect.height) return "";
  let visualCode;
  if (orient === "h") {
    const x = clamp(Math.round(relX / cell - 1), 0, 7);
    const y = clamp(Math.round(8 - relY / cell), 0, 7);
    visualCode = `h${files[x]}${y + 1}`;
  } else {
    const x = clamp(Math.round(relX / cell) - 1, 0, 7);
    const y = clamp(Math.round(8 - relY / cell - 0.5), 0, 7);
    visualCode = `v${files[x]}${y + 1}`;
  }
  return visualWallToActual(visualCode);
}

function setMode(nextMode) {
  stopAuto();
  stopReplay();
  replayIndex = null;
  lastComputerAction = null;
  mode = nextMode;
  modeHuman.classList.toggle("active", mode === "human");
  modeTopHuman.classList.toggle("active", mode === "topHuman");
  modeAuto.classList.toggle("active", mode === "auto");
  syncSidesForMode();
  playerFirst.disabled = mode === "auto";
  computerFirst.disabled = mode === "auto";
  updateFirstButtons();
  analyze();
  if (latest) render(latest);
}

function setFirst(which) {
  stopAuto();
  lastComputerAction = null;
  firstMover = which;
  syncSidesForMode();
  updateFirstButtons();
  analyze();
}

function updateFirstButtons() {
  playerFirst.classList.toggle("active", firstMover === "player");
  computerFirst.classList.toggle("active", firstMover === "computer");
}

async function aiStep() {
  if (!latest || latest.winner || !latest.recommendation) return;
  const side = latest.turn;
  const action = latest.recommendation;
  const computerAction = isWallCode(action)
    ? { kind: "wall", action }
    : { kind: "move", side, from: latest[side].pos, to: action };
  await tryCommit([action], `\u96fb\u8166\u8d70\u4e86 ${action}`, { computerAction });
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoBusy = false;
  autoBtn.textContent = "\u958b\u59cb\u81ea\u52d5\u5c0d\u6230";
}

function toggleAuto() {
  if (autoTimer) {
    stopAuto();
    return;
  }
  stopReplay();
  replayIndex = null;
  autoBtn.textContent = "\u66ab\u505c\u81ea\u52d5\u5c0d\u6230";
  autoTimer = setInterval(async () => {
    if (autoBusy) return;
    if (!latest || latest.winner) {
      stopAuto();
      return;
    }
    if (hasHumanPlayer() && latest.turn === humanSide) return;
    autoBusy = true;
    try {
      await aiStep();
    } finally {
      autoBusy = false;
    }
  }, 650);
}

async function submitHumanMove() {
  const typed = actionInput.value.trim();
  if (!typed) {
    statusText.textContent = "\u8acb\u5148\u8f38\u5165\u73a9\u5bb6\u8d70\u6cd5\u3002";
    return;
  }
  await tryCommit([typed], `\u73a9\u5bb6\u8d70\u4e86 ${typed}`);
}

function undoLastMove() {
  const tokens = historyTokens();
  if (!tokens.length) {
    statusText.textContent = t.noHistory;
    return;
  }
  tokens.pop();
  historyEl.value = tokens.join(" ");
  actionInput.value = "";
  analyze(t.undoDone);
}

function stopReplay() {
  if (replayTimer) clearInterval(replayTimer);
  replayTimer = null;
  replayBusy = false;
  replayPlayBtn.textContent = "\u64ad\u653e";
}

async function renderReplay(index) {
  const requestId = ++analyzeRequestId;
  stopAuto();
  lastComputerAction = null;
  const tokens = historyTokens();
  replayIndex = clamp(index, 0, tokens.length);
  try {
    const payload = await fetchAnalysis(tokens.slice(0, replayIndex).join(" "), { recommendForTurn: false });
    if (requestId !== analyzeRequestId) return;
    if (!payload.ok) {
      statusText.textContent = `${t.inputError}${payload.error}`;
      return;
    }
    render(payload.state);
    statusText.textContent = `\u56de\u653e\u4e2d\uff1a\u7b2c ${replayIndex} / ${tokens.length} \u624b`;
  } catch (error) {
    if (requestId !== analyzeRequestId) return;
    statusText.textContent = analysisErrorMessage(error);
    stopReplay();
  }
}

function toggleReplay() {
  const tokens = historyTokens();
  if (!tokens.length) {
    statusText.textContent = "\u76ee\u524d\u6c92\u6709\u68cb\u8b5c\u53ef\u4ee5\u56de\u653e\u3002";
    return;
  }
  if (replayTimer) {
    stopReplay();
    return;
  }
  if (replayIndex === null) replayIndex = 0;
  replayPlayBtn.textContent = "\u66ab\u505c";
  replayTimer = setInterval(async () => {
    if (replayBusy) return;
    if (replayIndex >= tokens.length) {
      stopReplay();
      return;
    }
    replayBusy = true;
    try {
      await renderReplay(replayIndex + 1);
    } finally {
      replayBusy = false;
    }
  }, 700);
}

modeHuman.addEventListener("click", () => setMode("human"));
modeTopHuman.addEventListener("click", () => setMode("topHuman"));
modeAuto.addEventListener("click", () => setMode("auto"));
playerFirst.addEventListener("click", () => setFirst("player"));
computerFirst.addEventListener("click", () => setFirst("computer"));
mainBtn.addEventListener("click", submitHumanMove);
aiStepBtn.addEventListener("click", aiStep);
autoBtn.addEventListener("click", toggleAuto);
undoBtn.addEventListener("click", undoLastMove);
analyzeBtn.addEventListener("click", analyze);
resetBtn.addEventListener("click", () => {
  stopAuto();
  stopReplay();
  replayIndex = null;
  lastComputerAction = null;
  historyEl.value = "";
  actionInput.value = "";
  analyze();
});
replayStartBtn.addEventListener("click", () => {
  stopReplay();
  renderReplay(0);
});
replayBackBtn.addEventListener("click", () => renderReplay((replayIndex ?? historyTokens().length) - 1));
replayForwardBtn.addEventListener("click", () => renderReplay((replayIndex ?? 0) + 1));
replayPlayBtn.addEventListener("click", toggleReplay);
replayLiveBtn.addEventListener("click", () => {
  stopReplay();
  replayIndex = null;
  analyze("\u5df2\u56de\u5230\u6700\u65b0\u5c40\u9762\u3002");
});

actionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    submitHumanMove();
  }
});

boardEl.addEventListener("click", (event) => {
  if (!hasHumanPlayer() || latest?.turn !== humanSide || previewWall || replayIndex !== null || Date.now() - lastWallTouchAt < 350) return;
  const square = squareFromPointer(event);
  if (square) tryCommit([square], `\u73a9\u5bb6\u8d70\u4e86 ${square}`);
});

function canTouchPlaceWall() {
  return hasHumanPlayer() && latest?.turn === humanSide && replayIndex === null;
}

function beginTouchWallDrag(event, orient) {
  if (event.pointerType === "mouse" || !(orient === "h" || orient === "v") || !canTouchPlaceWall()) return;
  touchWallOrient = orient;
  previewWall = "";
  event.currentTarget.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function updateTouchWallDrag(event) {
  if (!touchWallOrient) return;
  event.preventDefault();
  const nextPreview = wallFromPointer(event, touchWallOrient);
  boardEl.classList.toggle("drag-over", Boolean(nextPreview));
  if (nextPreview !== previewWall) {
    previewWall = nextPreview;
    if (latest) drawBoard(latest);
  }
}

function finishTouchWallDrag(event) {
  if (!touchWallOrient) return;
  event.preventDefault();
  const wall = previewWall || wallFromPointer(event, touchWallOrient);
  touchWallOrient = "";
  previewWall = "";
  lastWallTouchAt = Date.now();
  boardEl.classList.remove("drag-over");
  if (latest) drawBoard(latest);
  if (wall && canTouchPlaceWall()) tryCommit([wall], `玩家放牆 ${wall}`);
}

function cancelTouchWallDrag() {
  if (!touchWallOrient) return;
  touchWallOrient = "";
  previewWall = "";
  lastWallTouchAt = Date.now();
  boardEl.classList.remove("drag-over");
  if (latest) drawBoard(latest);
}

document.querySelectorAll(".drag-wall").forEach((tool) => {
  tool.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", tool.dataset.wall);
    event.dataTransfer.effectAllowed = "copy";
  });
  tool.addEventListener("pointerdown", (event) => beginTouchWallDrag(event, tool.dataset.wall));
});

document.addEventListener("pointermove", updateTouchWallDrag, { passive: false });
document.addEventListener("pointerup", finishTouchWallDrag, { passive: false });
document.addEventListener("pointercancel", cancelTouchWallDrag);

boardEl.addEventListener("dragover", (event) => {
  if (!hasHumanPlayer() || latest?.turn !== humanSide || replayIndex !== null) return;
  event.preventDefault();
  const orient = event.dataTransfer.getData("text/plain");
  if (orient === "h" || orient === "v") {
    const nextPreview = wallFromPointer(event, orient);
    if (nextPreview !== previewWall) {
      previewWall = nextPreview;
      drawBoard(latest);
    }
    boardEl.classList.add("drag-over");
  }
});

boardEl.addEventListener("dragleave", () => {
  previewWall = "";
  boardEl.classList.remove("drag-over");
  if (latest) drawBoard(latest);
});

boardEl.addEventListener("drop", (event) => {
  if (!hasHumanPlayer() || latest?.turn !== humanSide || replayIndex !== null) return;
  event.preventDefault();
  boardEl.classList.remove("drag-over");
  const orient = event.dataTransfer.getData("text/plain");
  const wall = previewWall || wallFromPointer(event, orient);
  previewWall = "";
  if (latest) drawBoard(latest);
  if (wall) tryCommit([wall], `\u73a9\u5bb6\u653e\u7246 ${wall}`);
});


[timeLimit, depthLimit, engineSelect, redTimeLimit, redDepthLimit, redEngineSelect, blueTimeLimit, blueDepthLimit, blueEngineSelect].forEach((input) => {
  input.addEventListener("change", () => {
    stopAuto();
    analyze("\u5df2\u66f4\u65b0\u641c\u5c0b\u8a2d\u5b9a\u3002");
  });
});
historyEl.addEventListener("blur", analyze);
updateFirstButtons();
analyze();
