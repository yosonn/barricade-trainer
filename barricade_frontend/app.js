const files = "abcdefghi";

const historyEl = document.querySelector("#history");
const actionInput = document.querySelector("#actionInput");
const recommendationEl = document.querySelector("#recommendation");
const statusText = document.querySelector("#statusText");
const scoreText = document.querySelector("#scoreText");
const winRateText = document.querySelector("#winRateText");
const boardEl = document.querySelector("#board");
const sideRed = document.querySelector("#sideRed");
const sideBlue = document.querySelector("#sideBlue");
const nextBtn = document.querySelector("#nextBtn");
const editMineBtn = document.querySelector("#editMineBtn");
const undoBtn = document.querySelector("#undoBtn");
const analyzeBtn = document.querySelector("#analyzeBtn");
const resetBtn = document.querySelector("#resetBtn");
const timeLimit = document.querySelector("#timeLimit");
const depthLimit = document.querySelector("#depthLimit");
const engineSelect = document.querySelector("#engineSelect");
const flowHint = document.querySelector("#flowHint");
const actionLabel = document.querySelector("#actionLabel");
const boardAcceptBtn = document.querySelector("#boardAcceptBtn");
const boardRecCode = document.querySelector("#boardRecCode");
const boardRecHint = document.querySelector("#boardRecHint");

let userSide = "red";
let latest = null;
let editingOwnMove = false;
let dragPreviewWall = "";
let touchWallOrient = "";
let lastWallTouchAt = 0;
let analyzeRequestId = 0;

const text = {
  red: "紅方",
  blue: "藍方",
  loading: "分析中...",
  inputError: "輸入有問題：",
  invalidNotSaved: "這步不合法，已保留輸入框，不會寫入棋譜：",
  stepsToGoal: "步到終點",
  wallsLeft: "剩餘牆",
  waiting: "等待對手走完後再推薦",
  turn: "輪到",
  wins: "獲勝",
  reachedGoal: "已到達終點。",
  ended: "這局已結束。",
  finished: "已結束",
  recommended: "推薦走法",
  clickIfUsed: "如果你照這步走，直接按金色按鈕。",
  defaultFlow: "預設流程：先採用推薦，下個畫面再輸入對手走法。也可以直接點棋盤或拖牆改走。",
  optionalOpponent: "對手走法（可留空）",
  use: "採用",
  different: "我不是走推薦",
  waitingOpponent: "等待對手",
  enterOpponent: "請輸入對手走法，或直接點棋盤 / 拖牆。",
  opponentMove: "對手走法",
  recordOpponent: "記錄對手走法",
  enterActual: "請先輸入你實際走的那一步。",
  enterOpponentFirst: "請先輸入對手走法。",
  actualMove: "你實際的走法",
  manualHint: "輸入你實際走的那一步，或直接點棋盤 / 拖牆。之後再輸入對手走法。",
  recordActual: "記錄我的實際走法",
  manualMode: "已切換成手動改走模式。",
  noWalls: "剩餘牆為 0，不能再放牆。",
  noHistory: "目前沒有可以回復的上一步。",
  undoDone: "已回復上一步。",
  clickSaved: "已從棋盤記錄走法：",
  dragWallSaved: "已從拖曳記錄放牆：",
  preview: "預覽：",
};

function other(side) {
  return side === "red" ? "blue" : "red";
}

function sideName(side) {
  return side === "red" ? text.red : text.blue;
}

function coordToXY(coord) {
  return { x: files.indexOf(coord[0]), y: Number(coord[1]) - 1 };
}

function historyTokens() {
  return historyEl.value.trim().split(/\s+/).filter(Boolean);
}

function historyWithActions(actions) {
  const cleanActions = actions.map((action) => action.trim().toLowerCase()).filter(Boolean);
  return `${historyEl.value.trim()} ${cleanActions.join(" ")}`.trim();
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
    const action = raw.trim().toLowerCase();
    if (isWallCode(action)) {
      const left = turn === "red" ? redWalls : blueWalls;
      if (left <= 0) return `${sideName(turn)}${text.noWalls}`;
      if (turn === "red") redWalls -= 1;
      else blueWalls -= 1;
    }
    turn = other(turn);
  }
  return "";
}

async function fetchAnalysis(history) {
  const controller = new AbortController();
  const timeoutMs = engineSelect.value === "expert"
    ? 40000
    : Math.max(8000, Number(timeLimit.value || 0) * 1000 + 5000);
  const timeoutId = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
  let response;
  try {
    response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        history,
        user_side: userSide,
        time: Number(timeLimit.value),
        depth: Number(depthLimit.value),
        engine: engineSelect.value,
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

function applyAnalysis(payload) {
  latest = payload.state;
  editingOwnMove = false;
  render(latest);
}

async function analyze(message = "") {
  const requestId = ++analyzeRequestId;
  statusText.textContent = text.loading;
  try {
    const payload = await fetchAnalysis(historyEl.value);
    if (requestId !== analyzeRequestId) return;
    if (!payload.ok) {
      statusText.textContent = `${text.inputError}${payload.error}`;
      return;
    }
    applyAnalysis(payload);
    if (message) statusText.textContent = message;
  } catch (error) {
    if (requestId !== analyzeRequestId) return;
    statusText.textContent = analysisErrorMessage(error);
  }
}

async function tryCommit(actions, messagePrefix = "") {
  const wallMessage = wallLimitMessage(actions);
  if (wallMessage) {
    statusText.textContent = wallMessage;
    actionInput.focus();
    return false;
  }

  const candidateHistory = historyWithActions(actions);
  const requestId = ++analyzeRequestId;
  statusText.textContent = text.loading;
  try {
    const payload = await fetchAnalysis(candidateHistory);
    if (requestId !== analyzeRequestId) return false;
    if (!payload.ok) {
      statusText.textContent = `${text.invalidNotSaved}${payload.error}`;
      actionInput.focus();
      return false;
    }

    historyEl.value = candidateHistory;
    actionInput.value = "";
    applyAnalysis(payload);
    if (messagePrefix) statusText.textContent = `${messagePrefix}${actions.join(" ")}`;
    return true;
  } catch (error) {
    if (requestId !== analyzeRequestId) return false;
    statusText.textContent = analysisErrorMessage(error);
    return false;
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
    ? `${sideName(state.winner)}${text.wins}`
    : `${text.turn}${sideName(state.turn)}`;

  recommendationEl.textContent = state.recommendation || "-";
  scoreText.textContent = state.recommendation
    ? `分數 ${Number(state.score).toFixed(1)}｜深度 ${state.searched_depth}`
    : text.waiting;
  if (state.recommendation) {
    scoreText.textContent = `分數 ${Number(state.score).toFixed(1)}｜深度 ${state.searched_depth}｜模型 ${state.resolved_engine || state.engine || "-"}`;
  }

  const myRate = userSide === "red" ? state.red_win_rate : state.blue_win_rate;
  const myVerdict = userSide === "red" ? state.red_verdict : state.blue_verdict;
  const rateText = Number.isFinite(Number(myRate)) ? `${myRate}%` : "-";
  winRateText.textContent = `勝率估計：${rateText}｜${myVerdict || "等待新版後端"}`;

  updateFlow(state);
  updateBoardRecommendation(state);
  drawBoard(state);
  updateUndoButton();
}

function updateFlow(state) {
  nextBtn.disabled = Boolean(state.winner);
  editMineBtn.disabled = !state.user_to_move || !state.recommendation || Boolean(state.winner);

  if (state.winner) {
    statusText.textContent = `${sideName(state.winner)}${text.reachedGoal}`;
    flowHint.textContent = text.ended;
    actionLabel.textContent = text.finished;
    nextBtn.textContent = text.finished;
    return;
  }

  if (state.user_to_move) {
    statusText.textContent = `${text.recommended}：${state.recommendation}。${text.clickIfUsed}`;
    flowHint.textContent = text.defaultFlow;
    actionLabel.textContent = text.optionalOpponent;
    actionInput.placeholder = "可留空，或輸入對手走法 e8 / hd5 / ve4";
    nextBtn.textContent = `${text.use} ${state.recommendation}`;
    editMineBtn.textContent = text.different;
    return;
  }

  statusText.textContent = `${text.waitingOpponent}（${sideName(other(userSide))}）。${text.enterOpponent}`;
  flowHint.textContent = "輸入對手棋子移動或放牆代碼，系統會重新計算你的下一步。";
  actionLabel.textContent = text.opponentMove;
  actionInput.placeholder = "e2 / hd5 / ve4";
  nextBtn.textContent = text.recordOpponent;
  editMineBtn.textContent = text.different;
}

function updateBoardRecommendation(state) {
  const canAccept = Boolean(state.user_to_move && state.recommendation && !state.winner);
  boardAcceptBtn.disabled = !canAccept;
  boardRecCode.textContent = canAccept ? state.recommendation : "-";

  if (state.winner) {
    boardRecHint.textContent = "棋局已結束。";
  } else if (canAccept) {
    boardRecHint.textContent = "輪到你，棋盤上已標出推薦位置。";
  } else {
    boardRecHint.textContent = "等待對手走完後，這裡會顯示推薦。";
  }
}

function updateUndoButton() {
  undoBtn.disabled = historyTokens().length === 0;
}

function drawBoard(state) {
  boardEl.innerHTML = "";
  for (let row = 8; row >= 0; row -= 1) {
    for (let col = 0; col < 9; col += 1) {
      const cell = document.createElement("div");
      cell.className = "cell";
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

  drawRecommendationPreview(state);
  for (const wall of state.walls) drawWall(wall);
  drawPawn(state.red.pos, "red");
  drawPawn(state.blue.pos, "blue");
  if (dragPreviewWall) drawWall(dragPreviewWall, "drag-preview");
}

function drawRecommendationPreview(state) {
  if (!state.user_to_move || !state.recommendation || state.winner) return;
  const action = state.recommendation;
  if (isSquareCode(action)) {
    drawPawn(action, `${userSide} recommendation`);
  } else if (isWallCode(action)) {
    drawWall(action, "recommendation");
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
  wall.className = `wall ${orient}${mode ? ` ${mode}-wall` : ""}`;
  const label = document.createElement("div");
  label.className = `wall-label${mode ? ` ${mode}-label` : ""}`;
  label.textContent = mode ? `${text.preview}${code}` : code;

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

function wallFromPointer(event, orient) {
  const rect = boardEl.getBoundingClientRect();
  const cell = rect.width / 9;
  const relX = event.clientX - rect.left;
  const relY = event.clientY - rect.top;
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

function setSide(side) {
  userSide = side;
  sideRed.classList.toggle("active", side === "red");
  sideBlue.classList.toggle("active", side === "blue");
  analyze();
}

function recordNext() {
  if (!latest || latest.winner) return;
  const typed = actionInput.value.trim();

  if (editingOwnMove) {
    if (!typed) {
      statusText.textContent = text.enterActual;
      return;
    }
    tryCommit([typed]);
    return;
  }

  if (latest.user_to_move && latest.recommendation) {
    const actions = typed ? [latest.recommendation, typed] : [latest.recommendation];
    tryCommit(actions);
    return;
  }

  if (!typed) {
    statusText.textContent = text.enterOpponentFirst;
    return;
  }
  tryCommit([typed]);
}

function acceptRecommendationOnly() {
  if (!latest?.user_to_move || !latest.recommendation || latest.winner) return;
  tryCommit([latest.recommendation]);
}

function commitBoardAction(action, messagePrefix) {
  if (!latest || latest.winner) return;
  editingOwnMove = false;
  actionInput.value = action;
  tryCommit([action], messagePrefix);
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
  editingOwnMove = false;
  analyze(text.undoDone);
}

sideRed.addEventListener("click", () => setSide("red"));
sideBlue.addEventListener("click", () => setSide("blue"));
analyzeBtn.addEventListener("click", analyze);
resetBtn.addEventListener("click", () => {
  historyEl.value = "";
  actionInput.value = "";
  editingOwnMove = false;
  analyze();
});
undoBtn.addEventListener("click", undoLastMove);
nextBtn.addEventListener("click", recordNext);
boardAcceptBtn.addEventListener("click", acceptRecommendationOnly);
editMineBtn.addEventListener("click", () => {
  if (!latest?.user_to_move) return;
  editingOwnMove = true;
  actionInput.value = "";
  actionInput.placeholder = `${text.actualMove}，例如 ${latest.recommendation}`;
  actionLabel.textContent = text.actualMove;
  flowHint.textContent = text.manualHint;
  nextBtn.textContent = text.recordActual;
  statusText.textContent = text.manualMode;
  actionInput.focus();
});

actionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    recordNext();
  }
});

boardEl.addEventListener("click", (event) => {
  if (dragPreviewWall || Date.now() - lastWallTouchAt < 350) return;
  const square = squareFromPointer(event);
  if (square) commitBoardAction(square, text.clickSaved);
});

function beginTouchWallDrag(event, orient) {
  if (event.pointerType === "mouse" || !(orient === "h" || orient === "v")) return;
  touchWallOrient = orient;
  dragPreviewWall = "";
  event.currentTarget.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function updateTouchWallDrag(event) {
  if (!touchWallOrient) return;
  event.preventDefault();
  const nextPreview = wallFromPointer(event, touchWallOrient);
  boardEl.classList.toggle("drag-over", Boolean(nextPreview));
  if (nextPreview !== dragPreviewWall) {
    dragPreviewWall = nextPreview;
    if (latest) drawBoard(latest);
  }
}

function finishTouchWallDrag(event) {
  if (!touchWallOrient) return;
  event.preventDefault();
  const wall = dragPreviewWall || wallFromPointer(event, touchWallOrient);
  touchWallOrient = "";
  dragPreviewWall = "";
  lastWallTouchAt = Date.now();
  boardEl.classList.remove("drag-over");
  if (latest) drawBoard(latest);
  if (wall) commitBoardAction(wall, text.dragWallSaved);
}

function cancelTouchWallDrag() {
  if (!touchWallOrient) return;
  touchWallOrient = "";
  dragPreviewWall = "";
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
  event.preventDefault();
  const orient = event.dataTransfer.getData("text/plain");
  if (orient === "h" || orient === "v") {
    const nextPreview = wallFromPointer(event, orient);
    if (nextPreview !== dragPreviewWall) {
      dragPreviewWall = nextPreview;
      if (latest) drawBoard(latest);
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
  event.preventDefault();
  boardEl.classList.remove("drag-over");
  const orient = event.dataTransfer.getData("text/plain");
  const wall = dragPreviewWall || wallFromPointer(event, orient);
  dragPreviewWall = "";
  if (latest) drawBoard(latest);
  if (wall) commitBoardAction(wall, text.dragWallSaved);
});

historyEl.addEventListener("blur", analyze);
engineSelect.addEventListener("change", () => analyze("已更新模型設定。"));
analyze();
