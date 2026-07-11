const files = "abcdefghi";

const historyEl = document.querySelector("#history");
const actionInput = document.querySelector("#actionInput");
const recommendationEl = document.querySelector("#recommendation");
const statusText = document.querySelector("#statusText");
const scoreText = document.querySelector("#scoreText");
const winRateText = document.querySelector("#winRateText");
const boardEl = document.querySelector("#board");
const resetTopBtn = document.querySelector("#resetTopBtn");
const nextBtn = document.querySelector("#nextBtn");
const hintBtn = document.querySelector("#editMineBtn");
const undoBtn = document.querySelector("#undoBtn");
const analyzeBtn = document.querySelector("#analyzeBtn");
const resetBtn = document.querySelector("#resetBtn");
const timeLimit = document.querySelector("#timeLimit");
const depthLimit = document.querySelector("#depthLimit");
const engineSelect = document.querySelector("#engineSelect");
const flowHint = document.querySelector("#flowHint");
const actionLabel = document.querySelector("#actionLabel");
const boardHintBtn = document.querySelector("#boardHintBtn");
const boardAcceptBtn = document.querySelector("#boardAcceptBtn");
const boardRecCode = document.querySelector("#boardRecCode");
const boardRecHint = document.querySelector("#boardRecHint");
const syncBadge = document.querySelector("#syncBadge");
const activeModelLabel = document.querySelector("#activeModelLabel");
const panelModelLabel = document.querySelector("#panelModelLabel");
const latencyText = document.querySelector("#latencyText");

let latest = null;
let dragPreviewWall = "";
let touchWallOrient = "";
let lastWallTouchAt = 0;
let analyzeRequestId = 0;
let latestHistoryText = "";
let requestBusy = false;

const initialBoardState = {
  turn: "red",
  user_side: "red",
  user_to_move: true,
  red: { pos: "e1", walls: 10, dist: 8, path: [] },
  blue: { pos: "e9", walls: 10, dist: 8, path: [] },
  walls: [],
  legal_actions: [],
  recommendation: null,
  winner: null,
};

const text = {
  red: "紅方",
  blue: "藍方",
  stepsToGoal: "步到終點",
  wallsLeft: "剩餘牆",
  noWalls: "剩餘牆為 0，不能再放牆。",
  noHistory: "目前沒有可以回復的上一步。",
  invalidNotSaved: "這步不合法，未寫入棋譜：",
  preview: "預覽：",
};

function other(side) {
  return side === "red" ? "blue" : "red";
}

function sideName(side) {
  return side === "red" ? text.red : text.blue;
}

function engineLabel(engine) {
  const labels = {
    expert: "Barricade.gg Expert",
    hybrid: "Hybrid · Alpha-Beta",
    mcts: "MCTS",
    "alpha-beta": "Alpha-Beta",
  };
  return labels[engine] || engine || "-";
}

function setSyncState(state, label) {
  syncBadge.dataset.state = state;
  syncBadge.textContent = label;
}

function setBusy(busy) {
  requestBusy = busy;
  hintBtn.disabled = busy || Boolean(latest?.winner);
  boardHintBtn.disabled = busy || Boolean(latest?.winner);
  nextBtn.disabled = busy || Boolean(latest?.winner);
  boardAcceptBtn.disabled = busy || !latest?.recommendation || Boolean(latest?.winner);
}

function coordToXY(coord) {
  return { x: files.indexOf(coord[0]), y: Number(coord[1]) - 1 };
}

function historyTokens() {
  return historyEl.value.trim().split(/\s+/).filter(Boolean);
}

function normalizedHistoryText() {
  return historyTokens().join(" ");
}

function historyWithActions(actions) {
  const clean = actions.map((action) => action.trim().toLowerCase()).filter(Boolean);
  return `${historyEl.value.trim()} ${clean.join(" ")}`.trim();
}

function isSquareCode(action) {
  return /^[a-i][1-9]$/i.test(action.trim());
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
    if (isWallCode(raw)) {
      const left = turn === "red" ? redWalls : blueWalls;
      if (left <= 0) return `${sideName(turn)}${text.noWalls}`;
      if (turn === "red") redWalls -= 1;
      else blueWalls -= 1;
    }
    turn = other(turn);
  }
  return "";
}

async function fetchAnalysis(history, { requestHint = false } = {}) {
  const requestStarted = performance.now();
  const controller = new AbortController();
  const timeoutMs = requestHint && engineSelect.value === "expert"
    ? 40000
    : requestHint
      ? Math.max(15000, Number(timeLimit.value || 0) * 1000 + 8000)
      : 15000;
  const timeoutId = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
  let response;
  try {
    response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        history,
        user_side: "red",
        start_turn: "red",
        recommend_for_turn: requestHint,
        suppress_recommend: !requestHint,
        fast_state: !requestHint,
        time: Number(timeLimit.value),
        depth: Number(depthLimit.value),
        engine: engineSelect.value,
      }),
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
  const payload = await response.json();
  if (payload?.state) {
    payload.state.client_ms = Math.round((performance.now() - requestStarted) * 10) / 10;
  }
  return payload;
}

function analysisErrorMessage(error, requestHint = false) {
  if (error?.name === "AbortError" || error === "timeout") {
    return requestHint
      ? "AI 提示逾時，棋局沒有受到影響，可稍後再試。"
      : "局面同步逾時，這一步尚未寫入，請再試一次。";
  }
  return `${requestHint ? "AI 提示" : "同步"}失敗：${error?.message || error}`;
}

function applyPayload(payload, historyText) {
  latest = payload.state;
  historyEl.value = historyText;
  latestHistoryText = historyText.trim().split(/\s+/).filter(Boolean).join(" ");
  render(latest);
}

async function analyze(message = "") {
  const requestId = ++analyzeRequestId;
  setBusy(true);
  setSyncState("busy", "同步局面");
  statusText.textContent = "正在同步雙人棋局...";
  try {
    const historyText = normalizedHistoryText();
    const payload = await fetchAnalysis(historyText);
    if (requestId !== analyzeRequestId) return;
    if (!payload.ok) {
      statusText.textContent = `棋譜有問題：${payload.error}`;
      setSyncState("error", "同步失敗");
      return;
    }
    applyPayload(payload, historyText);
    setSyncState("ready", "雙人對戰");
    statusText.textContent = message || (
      payload.state.winner
        ? `${sideName(payload.state.winner)}獲勝，可回復上一步或重新開局。`
        : `輪到${sideName(payload.state.turn)}，可輸入代碼、點棋盤或拖曳放牆。`
    );
  } catch (error) {
    if (requestId !== analyzeRequestId) return;
    statusText.textContent = analysisErrorMessage(error);
    setSyncState("error", "同步失敗");
  } finally {
    if (requestId === analyzeRequestId) setBusy(false);
  }
}

async function requestHint() {
  if (!latest || latest.winner || requestBusy) return;
  if (normalizedHistoryText() !== latestHistoryText) {
    statusText.textContent = "棋譜已修改，請先按「同步棋譜」。";
    return;
  }
  const requestId = ++analyzeRequestId;
  const hintedSide = latest.turn;
  setBusy(true);
  setSyncState("busy", engineSelect.value === "expert" ? "Expert 思考中" : "AI 思考中");
  statusText.textContent = `正在替${sideName(hintedSide)}計算單次提示...`;
  try {
    const historyText = normalizedHistoryText();
    const payload = await fetchAnalysis(historyText, { requestHint: true });
    if (requestId !== analyzeRequestId) return;
    if (!payload.ok) {
      statusText.textContent = `無法取得提示：${payload.error}`;
      setSyncState("error", "提示失敗");
      return;
    }
    applyPayload(payload, historyText);
    setSyncState("ready", "提示完成");
    statusText.textContent = payload.state.recommendation
      ? `AI 提示${sideName(hintedSide)}走 ${payload.state.recommendation}，可採用或自行走其他步。`
      : "目前沒有可用提示。";
  } catch (error) {
    if (requestId !== analyzeRequestId) return;
    statusText.textContent = analysisErrorMessage(error, true);
    setSyncState("error", "提示失敗");
  } finally {
    if (requestId === analyzeRequestId) setBusy(false);
  }
}

function optimisticStateForAction(state, action) {
  if (!state) return null;
  const normalized = action.trim().toLowerCase();
  if (!isSquareCode(normalized) && !isWallCode(normalized)) return null;
  const next = JSON.parse(JSON.stringify(state));
  const side = state.turn;
  if (isWallCode(normalized)) {
    if (next[side].walls <= 0) return null;
    next.walls = [...next.walls, normalized];
    next[side].walls -= 1;
  } else {
    next[side].pos = normalized;
    if ((side === "red" && normalized.endsWith("9")) || (side === "blue" && normalized.endsWith("1"))) {
      next.winner = side;
    }
  }
  next.turn = other(side);
  next.recommendation = null;
  next.score = null;
  next.searched_depth = null;
  next.legal_actions = [];
  return next;
}

async function tryCommit(actions, message = "") {
  if (!latest || latest.winner || requestBusy) return false;
  const wallMessage = wallLimitMessage(actions);
  if (wallMessage) {
    statusText.textContent = wallMessage;
    return false;
  }
  const candidateHistory = historyWithActions(actions);
  const requestId = ++analyzeRequestId;
  const previousState = latest;
  const previousHistory = normalizedHistoryText();
  const optimisticState = actions.length === 1 ? optimisticStateForAction(latest, actions[0]) : null;

  setBusy(true);
  if (optimisticState) {
    latest = optimisticState;
    historyEl.value = candidateHistory;
    latestHistoryText = candidateHistory;
    actionInput.value = "";
    render(latest);
    statusText.textContent = message || `已輸入 ${actions[0]}，正在驗證...`;
    await new Promise((resolve) => requestAnimationFrame(resolve));
  }
  setSyncState("busy", "驗證走法");
  try {
    const payload = await fetchAnalysis(candidateHistory);
    if (requestId !== analyzeRequestId) return false;
    if (!payload.ok) {
      latest = previousState;
      historyEl.value = previousHistory;
      latestHistoryText = previousHistory;
      render(latest);
      statusText.textContent = `${text.invalidNotSaved}${payload.error}`;
      setSyncState("error", "走法已回復");
      return false;
    }
    applyPayload(payload, candidateHistory);
    actionInput.value = "";
    setSyncState("ready", "雙人對戰");
    statusText.textContent = message || `已記錄 ${actions.join(" ")}。`;
    return true;
  } catch (error) {
    if (requestId !== analyzeRequestId) return false;
    latest = previousState;
    historyEl.value = previousHistory;
    latestHistoryText = previousHistory;
    render(latest);
    statusText.textContent = analysisErrorMessage(error);
    setSyncState("error", "走法已回復");
    return false;
  } finally {
    if (requestId === analyzeRequestId) setBusy(false);
  }
}

function render(state) {
  document.querySelector("#redPos").textContent = state.red.pos;
  document.querySelector("#bluePos").textContent = state.blue.pos;
  document.querySelector("#redDist").textContent = `${state.red.dist} ${text.stepsToGoal}`;
  document.querySelector("#blueDist").textContent = `${state.blue.dist} ${text.stepsToGoal}`;
  document.querySelector("#redInfo").textContent = `${text.wallsLeft} ${state.red.walls}`;
  document.querySelector("#blueInfo").textContent = `${text.wallsLeft} ${state.blue.walls}`;
  document.querySelector("#turnText").textContent = state.winner
    ? `${sideName(state.winner)}獲勝`
    : `輪到${sideName(state.turn)}`;

  recommendationEl.textContent = state.recommendation || "-";
  const displayEngine = engineLabel(engineSelect.value);
  activeModelLabel.textContent = `提示：${displayEngine}`;
  panelModelLabel.textContent = displayEngine;
  const total = Number(state.client_ms);
  const server = Number(state.server_ms);
  latencyText.textContent = Number.isFinite(total)
    ? `回應 ${Math.round(total)} ms`
    : Number.isFinite(server) ? `後端 ${Math.round(server)} ms` : "局面已載入";

  if (state.recommendation) {
    const score = Number.isFinite(Number(state.score)) ? Number(state.score).toFixed(1) : "-";
    scoreText.textContent = `${state.resolved_engine || state.engine || displayEngine} · 評分 ${score}`;
  } else {
    scoreText.textContent = "尚未要求提示";
  }
  winRateText.textContent = `紅方 ${state.red_win_rate ?? "-"}%｜藍方 ${state.blue_win_rate ?? "-"}%`;

  updateFlow(state);
  updateBoardHint(state);
  drawBoard(state);
  undoBtn.disabled = historyTokens().length === 0 || requestBusy;
}

function updateFlow(state) {
  if (state.winner) {
    flowHint.textContent = `${sideName(state.winner)}已到達終點，本局結束。`;
    actionLabel.textContent = "棋局已結束";
    nextBtn.textContent = "棋局已結束";
    statusText.textContent = `${sideName(state.winner)}獲勝，可回復上一步或重新開局。`;
    return;
  }
  const side = sideName(state.turn);
  flowHint.textContent = state.recommendation
    ? `AI 已提示${side}，仍可自由選擇其他合法走法。`
    : "紅藍雙方輪流操作，AI 只在按下提示時參與一次。";
  actionLabel.textContent = `${side}走法`;
  actionInput.placeholder = state.turn === "red" ? "例如 e2、hd5、ve4" : "例如 e8、hd5、ve4";
  nextBtn.textContent = `送出${side}走法`;
  hintBtn.textContent = state.recommendation ? "重新提示一次" : "AI 提示一次";
  if (!requestBusy) {
    statusText.textContent = state.recommendation
      ? `AI 提示${side}走 ${state.recommendation}，也可自行走其他步。`
      : `輪到${side}，可輸入代碼、點棋盤或拖曳放牆。`;
  }
}

function updateBoardHint(state) {
  const canAccept = Boolean(state.recommendation && !state.winner);
  boardRecCode.textContent = canAccept ? state.recommendation : "-";
  boardAcceptBtn.disabled = requestBusy || !canAccept;
  boardHintBtn.disabled = requestBusy || Boolean(state.winner);
  if (state.winner) boardRecHint.textContent = "棋局已結束。";
  else if (canAccept) boardRecHint.textContent = `輪到${sideName(state.turn)}，棋盤上已標出 AI 提示。`;
  else boardRecHint.textContent = "需要協助時再要求一次提示，不會自動替玩家走棋。";
}

function drawBoard(state) {
  boardEl.innerHTML = "";
  for (let row = 8; row >= 0; row -= 1) {
    for (let col = 0; col < 9; col += 1) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.dataset.coord = `${files[col]}${row + 1}`;
      if (row === 8) cell.classList.add("goal-red");
      if (row === 0) cell.classList.add("goal-blue");
      if (col === 0 || row === 0) {
        const label = document.createElement("span");
        label.className = "coord";
        label.textContent = col === 0 ? String(row + 1) : files[col];
        if (row === 0 && col === 0) label.textContent = "a1";
        cell.appendChild(label);
      }
      boardEl.appendChild(cell);
    }
  }
  drawHintPreview(state);
  for (const wall of state.walls) drawWall(wall);
  drawPawn(state.red.pos, "red");
  drawPawn(state.blue.pos, "blue");
  if (dragPreviewWall) drawWall(dragPreviewWall, "drag-preview");
}

function drawHintPreview(state) {
  if (!state.recommendation || state.winner) return;
  if (isSquareCode(state.recommendation)) {
    drawPawn(state.recommendation, `${state.turn} recommendation`);
  } else if (isWallCode(state.recommendation)) {
    drawWall(state.recommendation, "recommendation");
  }
}

function drawPawn(coord, colorClass) {
  const { x, y } = coordToXY(coord);
  const pawn = document.createElement("div");
  pawn.className = `pawn ${colorClass}`;
  pawn.style.left = `${((x + 0.5) / 9) * 100}%`;
  pawn.style.top = `${((8 - y + 0.5) / 9) * 100}%`;
  boardEl.appendChild(pawn);
}

function drawWall(code, mode = "") {
  const orient = code[0];
  const { x, y } = coordToXY(code.slice(1));
  const wall = document.createElement("div");
  const label = document.createElement("div");
  wall.className = `wall ${orient}${mode ? ` ${mode}-wall` : ""}`;
  label.className = `wall-label${mode ? ` ${mode}-label` : ""}`;
  label.textContent = mode ? `${text.preview}${code}` : code;
  if (orient === "h") {
    wall.style.left = `${(x / 9) * 100}%`;
    wall.style.top = `${((8 - y) / 9) * 100}%`;
    wall.style.width = `${(2 / 9) * 100}%`;
    label.style.left = `${((x + 1) / 9) * 100}%`;
    label.style.top = `${((8 - y) / 9) * 100}%`;
    label.style.transform = "translate(-50%, -205%)";
  } else {
    wall.style.left = `${((x + 1) / 9) * 100}%`;
    wall.style.top = `${((8 - (y + 1)) / 9) * 100}%`;
    wall.style.height = `${(2 / 9) * 100}%`;
    label.style.left = `${((x + 1) / 9) * 100}%`;
    label.style.top = `${((8 - y) / 9) * 100}%`;
    label.style.transform = "translate(32%, -50%)";
  }
  boardEl.appendChild(wall);
  boardEl.appendChild(label);
}

function squareFromPointer(event) {
  const cellEl = event.target.closest(".cell");
  if (cellEl && boardEl.contains(cellEl)) return cellEl.dataset.coord || "";
  const rect = boardEl.getBoundingClientRect();
  const cell = rect.width / 9;
  const col = Math.floor((event.clientX - rect.left) / cell);
  const displayRow = Math.floor((event.clientY - rect.top) / cell);
  if (col < 0 || col > 8 || displayRow < 0 || displayRow > 8) return "";
  return `${files[col]}${8 - displayRow + 1}`;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function touchPreviewOffset() {
  return Math.max(52, Math.min(84, boardEl.getBoundingClientRect().width / 6.5));
}

function wallFromPointer(event, orient, offsetForTouch = false) {
  const rect = boardEl.getBoundingClientRect();
  const cell = rect.width / 9;
  const relX = event.clientX - rect.left;
  const relY = event.clientY - rect.top - (offsetForTouch ? touchPreviewOffset() : 0);
  if (relX < 0 || relY < 0 || relX > rect.width || relY > rect.height) return "";
  if (orient === "h") {
    const x = clamp(Math.round(relX / cell - 1), 0, 7);
    const y = clamp(Math.round(8 - relY / cell), 0, 7);
    return `h${files[x]}${y + 1}`;
  }
  const x = clamp(Math.round(relX / cell) - 1, 0, 7);
  const y = clamp(Math.round(8 - relY / cell - 0.5), 0, 7);
  return `v${files[x]}${y + 1}`;
}

function submitTypedMove() {
  if (normalizedHistoryText() !== latestHistoryText) {
    statusText.textContent = "棋譜已修改，請先按「同步棋譜」。";
    return;
  }
  const typed = actionInput.value.trim();
  if (!typed) {
    statusText.textContent = `請先輸入${sideName(latest?.turn || "red")}走法。`;
    return;
  }
  tryCommit([typed], `${sideName(latest.turn)}走了 ${typed}`);
}

function acceptHint() {
  if (!latest?.recommendation || latest.winner) return;
  tryCommit([latest.recommendation], `${sideName(latest.turn)}採用 AI 提示 ${latest.recommendation}`);
}

function undoLastMove() {
  const tokens = historyTokens();
  if (!tokens.length) {
    statusText.textContent = text.noHistory;
    return;
  }
  tokens.pop();
  historyEl.value = tokens.join(" ");
  actionInput.value = "";
  analyze("已回復上一步。");
}

function resetGame() {
  analyzeRequestId += 1;
  historyEl.value = "";
  actionInput.value = "";
  latestHistoryText = "";
  analyze("已重新開局，由紅方先手。");
}

boardEl.addEventListener("click", (event) => {
  if (!latest || latest.winner || requestBusy || dragPreviewWall || Date.now() - lastWallTouchAt < 350) return;
  const square = squareFromPointer(event);
  if (square) tryCommit([square], `${sideName(latest.turn)}走了 ${square}`);
});

function beginTouchWallDrag(event, orient) {
  if (
    event.pointerType === "mouse"
    || !(orient === "h" || orient === "v")
    || !latest
    || latest.winner
    || requestBusy
  ) return;
  touchWallOrient = orient;
  dragPreviewWall = "";
  event.currentTarget.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function updateTouchWallDrag(event) {
  if (!touchWallOrient) return;
  event.preventDefault();
  const nextPreview = wallFromPointer(event, touchWallOrient, true);
  boardEl.classList.toggle("drag-over", Boolean(nextPreview));
  if (nextPreview !== dragPreviewWall) {
    dragPreviewWall = nextPreview;
    drawBoard(latest);
  }
}

function finishTouchWallDrag(event) {
  if (!touchWallOrient) return;
  event.preventDefault();
  const wall = dragPreviewWall || wallFromPointer(event, touchWallOrient, true);
  touchWallOrient = "";
  dragPreviewWall = "";
  lastWallTouchAt = Date.now();
  boardEl.classList.remove("drag-over");
  if (latest) drawBoard(latest);
  if (wall) tryCommit([wall], `${sideName(latest.turn)}放牆 ${wall}`);
}

function cancelTouchWallDrag() {
  if (!touchWallOrient) return;
  touchWallOrient = "";
  dragPreviewWall = "";
  lastWallTouchAt = Date.now();
  boardEl.classList.remove("drag-over");
  if (latest) drawBoard(latest);
}

function setWallDragImage(event, orient) {
  const ghost = document.createElement("div");
  ghost.className = `wall-drag-image ${orient}`;
  document.body.appendChild(ghost);
  const width = orient === "h" ? 88 : 12;
  const height = orient === "h" ? 12 : 76;
  event.dataTransfer.setDragImage(ghost, width / 2, height / 2);
  window.setTimeout(() => ghost.remove(), 0);
}

document.querySelectorAll(".drag-wall").forEach((tool) => {
  tool.addEventListener("dragstart", (event) => {
    if (!latest || latest.winner || requestBusy) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData("text/plain", tool.dataset.wall);
    event.dataTransfer.effectAllowed = "copy";
    setWallDragImage(event, tool.dataset.wall);
  });
  tool.addEventListener("pointerdown", (event) => beginTouchWallDrag(event, tool.dataset.wall));
});

document.addEventListener("pointermove", updateTouchWallDrag, { passive: false });
document.addEventListener("pointerup", finishTouchWallDrag, { passive: false });
document.addEventListener("pointercancel", cancelTouchWallDrag);

boardEl.addEventListener("dragover", (event) => {
  if (!latest || latest.winner || requestBusy) return;
  event.preventDefault();
  const orient = event.dataTransfer.getData("text/plain");
  if (orient === "h" || orient === "v") {
    const nextPreview = wallFromPointer(event, orient);
    if (nextPreview !== dragPreviewWall) {
      dragPreviewWall = nextPreview;
      drawBoard(latest);
    }
    boardEl.classList.add("drag-over");
  }
});

boardEl.addEventListener("dragleave", () => {
  dragPreviewWall = "";
  boardEl.classList.remove("drag-over");
  if (latest) drawBoard(latest);
});

boardEl.addEventListener("drop", (event) => {
  if (!latest || latest.winner || requestBusy) return;
  event.preventDefault();
  boardEl.classList.remove("drag-over");
  const orient = event.dataTransfer.getData("text/plain");
  const wall = dragPreviewWall || wallFromPointer(event, orient);
  dragPreviewWall = "";
  drawBoard(latest);
  if (wall) tryCommit([wall], `${sideName(latest.turn)}放牆 ${wall}`);
});

nextBtn.addEventListener("click", submitTypedMove);
hintBtn.addEventListener("click", requestHint);
boardHintBtn.addEventListener("click", requestHint);
boardAcceptBtn.addEventListener("click", acceptHint);
undoBtn.addEventListener("click", undoLastMove);
analyzeBtn.addEventListener("click", () => analyze("棋譜已同步。"));
resetBtn.addEventListener("click", resetGame);
resetTopBtn.addEventListener("click", resetGame);

actionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    submitTypedMove();
  }
});

historyEl.addEventListener("blur", () => {
  if (normalizedHistoryText() !== latestHistoryText) {
    statusText.textContent = "棋譜已修改，按「同步棋譜」後套用新局面。";
  }
});

historyEl.addEventListener("input", () => {
  latestHistoryText = "";
  statusText.textContent = "棋譜已修改，按「同步棋譜」後會從新局面繼續。";
});

engineSelect.addEventListener("change", () => {
  if (latest) {
    latest.recommendation = null;
    render(latest);
    statusText.textContent = `提示模型已改為 ${engineLabel(engineSelect.value)}。`;
  }
});

drawBoard(initialBoardState);
analyze();
