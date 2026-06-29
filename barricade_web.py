from __future__ import annotations

import json
import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import barricade_trainer as engine
import barricade_mcts
from barricade_expert import BarricadeGgAiClient, expert_history_for_start_turn, local_action_from_expert


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "barricade_frontend"
APP_VERSION = "2026.06.30.09"
DEFAULT_ENGINE = "hybrid"
EXPERT_ENGINE = "expert"
SUPPORTED_ENGINES = {"alpha-beta", "mcts", "hybrid", EXPERT_ENGINE}
EXPERT_TIMEOUT_SECONDS = 35.0
DEFAULT_MCTS_SIMULATIONS = 120
DEFAULT_MCTS_MAX_ACTIONS = 20
DEFAULT_MCTS_ROLLOUT_DEPTH = 2
DEFAULT_MCTS_EXPLORATION = 1.35


def win_rate_from_score(score: float) -> float:
    # Convert heuristic score to a practical 0-100 estimate. This is not a solved-game proof.
    return round(100 / (1 + 2.718281828 ** (-score / 350)), 1)


def verdict(score: float, win: str | None, perspective: str) -> str:
    if win == perspective:
        return "\u5df2\u52dd"
    if win is not None:
        return "\u5df2\u6557"
    if score >= 900:
        return "\u9ad8\u5ea6\u512a\u52e2\uff0c\u63a5\u8fd1\u5fc5\u52dd"
    if score >= 350:
        return "\u660e\u986f\u512a\u52e2"
    if score <= -900:
        return "\u9ad8\u5ea6\u52a3\u52e2\uff0c\u63a5\u8fd1\u5fc5\u6557"
    if score <= -350:
        return "\u660e\u986f\u52a3\u52e2"
    return "\u5c40\u52e2\u63a5\u8fd1"


def action_analysis(state: engine.State, action: str, perspective: str) -> dict:
    opp = engine.opponent(perspective)
    child = engine.apply_action(state, action)
    my_dist, _ = engine.movement_path(state, perspective)
    opp_dist, _ = engine.movement_path(state, opp)
    next_my_dist, _ = engine.movement_path(child, perspective)
    next_opp_dist, _ = engine.movement_path(child, opp)
    my_delta = my_dist - next_my_dist
    opp_delta = next_opp_dist - opp_dist
    raw_score = engine.action_score(state, action, perspective)
    reasons: list[str] = []

    if engine.is_pawn_action(action):
        reasons.append("\u68cb\u5b50\u9032\u653b" if my_delta > 0 else "\u8abf\u6574\u7ad9\u4f4d")
        if next_my_dist <= 2:
            reasons.append("\u903c\u8fd1\u7d42\u9ede")
        if engine.player_has_goal_move(child, opp):
            reasons.append("\u98a8\u96aa\uff1a\u5c0d\u624b\u4e0b\u6b65\u53ef\u80fd\u5230\u7d42\u9ede")
    else:
        reasons.append("\u653e\u7246\u963b\u64cb" if opp_delta > 0 else "\u653e\u7246\u5c0d\u5ef6\u9072\u6548\u679c\u6709\u9650")
        if opp_delta >= 2:
            reasons.append("\u660e\u986f\u62c9\u9577\u5c0d\u624b\u8def\u5f91")
        if my_delta < 0:
            reasons.append("\u4ee3\u50f9\uff1a\u81ea\u5df1\u8def\u5f91\u8b8a\u9577")

    if child.pawn(perspective)[1] == engine.GOAL_ROW[perspective]:
        reasons.insert(0, "\u7acb\u5373\u52dd\u5229")
    if not reasons:
        reasons.append("\u4fdd\u6301\u5c40\u9762\u5e73\u8861")

    return {
        "action": action,
        "kind": "pawn" if engine.is_pawn_action(action) else "wall",
        "score": round(raw_score, 1),
        "my_distance_delta": my_delta,
        "opponent_distance_delta": opp_delta,
        "my_distance_after": next_my_dist,
        "opponent_distance_after": next_opp_dist,
        "reasons": reasons[:3],
    }


def strategy_summary(state: engine.State, perspective: str, state_score: float) -> list[str]:
    opp = engine.opponent(perspective)
    my_dist, _ = engine.movement_path(state, perspective)
    opp_dist, _ = engine.movement_path(state, opp)
    my_walls = state.walls_left(perspective)
    opp_walls = state.walls_left(opp)
    notes: list[str] = []

    if my_dist < opp_dist:
        notes.append("\u8def\u5f91\u9818\u5148\uff1a\u512a\u5148\u4fdd\u6301\u524d\u9032\u7bc0\u594f")
    elif my_dist > opp_dist:
        notes.append("\u8def\u5f91\u843d\u5f8c\uff1a\u9700\u8981\u627e\u5ef6\u9072\u7246\u6216\u5f37\u5236\u8df3\u9ede")
    else:
        notes.append("\u8def\u5f91\u76f8\u8fd1\uff1a\u6c7a\u7b56\u91cd\u9ede\u5728 tempo \u8207\u7246\u8cc7\u6e90")

    if my_walls <= 1:
        notes.append("\u7246\u8cc7\u6e90\u4f4e\uff1a\u4e0d\u5b9c\u8f15\u6613\u82b1\u6389\u6700\u5f8c\u9632\u5b88")
    elif opp_walls <= 1:
        notes.append("\u5c0d\u624b\u7246\u5c11\uff1a\u53ef\u8003\u616e\u76f4\u63a5\u8f49\u6210\u7d42\u5c40\u885d\u523a")

    if engine.player_has_goal_move(state, opp):
        notes.append("\u9ad8\u98a8\u96aa\uff1a\u5c0d\u624b\u5df2\u6709\u76f4\u63a5\u5230\u7d42\u9ede\u7684\u5a01\u8105")
    elif engine.player_has_goal_move(state, perspective):
        notes.append("\u9032\u653b\u6a5f\u6703\uff1a\u6211\u65b9\u5df2\u63a5\u8fd1\u76f4\u63a5\u7d42\u7d50")

    if abs(state_score) < 180:
        notes.append("\u5c40\u52e2\u7dca\u8cbc\uff1a\u4efb\u4f55\u4e00\u9762\u597d\u7246\u90fd\u53ef\u6539\u8b8a\u52dd\u8ca0")
    return notes[:4]


def analysis_payload(
    state: engine.State,
    search_time: float,
    depth: int,
    engine_kind: str,
    resolved_engine: str,
    recommendation: str | None,
    score: float | None,
    searched_depth: int | None,
    avoid_actions: set[str] | None,
) -> dict:
    perspective = state.turn
    opp = engine.opponent(perspective)
    state_score = engine.static_eval(state, perspective)
    candidates = [
        action_analysis(state, action, perspective)
        for action in engine.ordered_actions(state, limit_walls=18)[:6]
    ]
    avoided = sorted(avoid_actions or set())
    return {
        "engine": engine_kind,
        "resolved_engine": resolved_engine,
        "perspective": perspective,
        "opponent": opp,
        "search_time": search_time,
        "depth_limit": depth,
        "searched_depth": searched_depth,
        "recommendation": recommendation,
        "score": round(score if score is not None else state_score, 1),
        "state_score": round(state_score, 1),
        "verdict": verdict(state_score, winner(state), perspective),
        "strategy": strategy_summary(state, perspective, state_score),
        "candidates": candidates,
        "avoided_actions": avoided,
        "path_gap": state.pawn(opp)[1] - state.pawn(perspective)[1],
    }


def resolve_hybrid_engine(state: engine.State) -> str:
    perspective = state.turn
    opp = engine.opponent(perspective)
    my_dist, _ = engine.movement_path(state, perspective)
    opp_dist, _ = engine.movement_path(state, opp)
    total_walls = state.walls_left("red") + state.walls_left("blue")
    pawn_gap = abs(state.red[0] - state.blue[0]) + abs(state.red[1] - state.blue[1])

    # Use alpha-beta for tactical races, immediate threats, and narrow endgames.
    if engine.player_has_goal_move(state, perspective) or engine.player_has_goal_move(state, opp):
        return "alpha-beta"
    if pawn_gap <= 2 and total_walls >= 8 and min(my_dist, opp_dist) <= 6:
        return "alpha-beta"
    if min(my_dist, opp_dist) <= 3:
        return "alpha-beta"
    if total_walls <= 3:
        return "alpha-beta"
    if state.walls_left(perspective) <= 1 or state.walls_left(opp) <= 1:
        if abs(my_dist - opp_dist) <= 4:
            return "alpha-beta"
    return "mcts"


def recommend_action(
    state: engine.State,
    search_time: float,
    depth: int,
    engine_kind: str,
    avoid_actions: set[str] | None,
    seed: int = 0,
    history_tokens: list[str] | None = None,
    start_turn: str = "red",
) -> tuple[str, float, int, str]:
    resolved_engine = resolve_hybrid_engine(state) if engine_kind == "hybrid" else engine_kind
    if resolved_engine == EXPERT_ENGINE:
        expert_history = expert_history_for_start_turn(history_tokens or [], start_turn)
        expert_action = BarricadeGgAiClient(timeout=EXPERT_TIMEOUT_SECONDS).get_move(expert_history)
        action = local_action_from_expert(expert_action, start_turn)
        try:
            engine.apply_action(state, action)
        except Exception as exc:
            raise ValueError(
                f"Barricade.gg Expert returned illegal move {expert_action} "
                f"(local {action}): {exc}"
            ) from exc
        return action, engine.action_score(state, action, state.turn), 0, resolved_engine
    if resolved_engine == "mcts":
        action, score, searched_depth = barricade_mcts.search_mcts(
            state,
            time_limit=search_time,
            simulations=DEFAULT_MCTS_SIMULATIONS,
            max_actions=DEFAULT_MCTS_MAX_ACTIONS,
            exploration=DEFAULT_MCTS_EXPLORATION,
            rollout_depth=DEFAULT_MCTS_ROLLOUT_DEPTH,
            avoid_actions=avoid_actions,
            seed=seed,
        )
        return action, score, searched_depth, resolved_engine
    action, score, searched_depth = engine.search_best(
        state,
        time_limit=search_time,
        max_depth=depth,
        avoid_actions=avoid_actions,
    )
    return action, score, searched_depth, resolved_engine


def state_payload(
    state: engine.State,
    user_side: str,
    search_time: float,
    depth: int,
    engine_kind: str = DEFAULT_ENGINE,
    recommend_for_turn: bool = False,
    start_turn: str = "red",
    avoid_actions: set[str] | None = None,
    mcts_seed: int = 0,
    history_tokens: list[str] | None = None,
    suppress_recommend: bool = False,
) -> dict:
    red_dist, red_path = engine.movement_path(state, "red")
    blue_dist, blue_path = engine.movement_path(state, "blue")
    actions = engine.ordered_actions(state, limit_walls=18)
    win = winner(state)
    red_score = engine.static_eval(state, "red")
    blue_score = engine.static_eval(state, "blue")
    recommendation = None
    score = None
    searched_depth = None
    resolved_engine = engine_kind
    recommend_side = state.turn if recommend_for_turn else user_side
    if not suppress_recommend and state.turn == recommend_side and actions:
        recommendation, score, searched_depth, resolved_engine = recommend_action(
            state,
            search_time,
            depth,
            engine_kind,
            avoid_actions,
            seed=mcts_seed,
            history_tokens=history_tokens,
            start_turn=start_turn,
        )

    return {
        "app_version": APP_VERSION,
        "turn": state.turn,
        "start_turn": start_turn,
        "user_side": user_side,
        "user_to_move": state.turn == user_side,
        "red": {
            "pos": engine.coord_to_text(state.red),
            "walls": state.red_walls,
            "dist": red_dist,
            "path": [engine.coord_to_text(pos) for pos in red_path],
        },
        "blue": {
            "pos": engine.coord_to_text(state.blue),
            "walls": state.blue_walls,
            "dist": blue_dist,
            "path": [engine.coord_to_text(pos) for pos in blue_path],
        },
        "walls": [engine.wall_to_text(wall) for wall in sorted(state.walls)],
        "legal_actions": actions,
        "engine": engine_kind,
        "resolved_engine": resolved_engine,
        "recommendation": recommendation,
        "score": score,
        "searched_depth": searched_depth,
        "winner": win,
        "red_win_rate": win_rate_from_score(red_score),
        "blue_win_rate": win_rate_from_score(blue_score),
        "red_verdict": verdict(red_score, win, "red"),
        "blue_verdict": verdict(blue_score, win, "blue"),
        "analysis": analysis_payload(
            state,
            search_time,
            depth,
            engine_kind,
            resolved_engine,
            recommendation,
            score,
            searched_depth,
            avoid_actions,
        ),
    }


def winner(state: engine.State) -> str | None:
    if state.red[1] == engine.GOAL_ROW["red"]:
        return "red"
    if state.blue[1] == engine.GOAL_ROW["blue"]:
        return "blue"
    return None


def recent_reversal_avoid_actions(history: str, start_turn: str) -> set[str]:
    state = engine.State(turn=start_turn)
    recent_positions: dict[str, list[str]] = {"red": [], "blue": []}
    for token in engine.tokenize_history(history):
        side = state.turn
        before = state.pawn(side)
        state = engine.apply_action(state, token)
        if engine.is_pawn_action(token):
            recent_positions[side].append(engine.coord_to_text(before))
            recent_positions[side] = recent_positions[side][-3:]
    return set(recent_positions.get(state.turn, []))


def recent_state_repeat_avoid_actions(
    history: str,
    start_turn: str,
    window: int = 12,
) -> set[str]:
    tokens = engine.tokenize_history(history)
    state = engine.State(turn=start_turn)
    states = [state]
    for token in tokens:
        state = engine.apply_action(state, token)
        states.append(state)

    recent_keys = {past.key() for past in states[-(window + 1):-1]}
    if not recent_keys:
        return set()

    avoid: set[str] = set()
    for action in engine.ordered_actions(state, limit_walls=18):
        child = engine.apply_action(state, action)
        if child.key() in recent_keys:
            avoid.add(action)
    return avoid


def root_avoid_actions(history: str, start_turn: str) -> set[str]:
    return recent_reversal_avoid_actions(history, start_turn) | recent_state_repeat_avoid_actions(
        history,
        start_turn,
    )


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        path = unquote(self.path.split("?", 1)[0])
        if path == "/":
            self.serve_file(FRONTEND / "index.html", "text/html; charset=utf-8")
            return
        candidate = (FRONTEND / path.lstrip("/")).resolve()
        if FRONTEND.resolve() in candidate.parents and candidate.is_file():
            content_type = "text/plain; charset=utf-8"
            if candidate.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            elif candidate.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif candidate.suffix == ".js":
                content_type = "text/javascript; charset=utf-8"
            self.serve_file(candidate, content_type)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/api/analyze":
            self.send_error(404)
            return
        try:
            payload = self.read_json()
            history = str(payload.get("history", ""))
            user_side = str(payload.get("user_side", "red"))
            if user_side not in engine.PLAYERS:
                raise ValueError("user_side must be red or blue")
            start_turn = str(payload.get("start_turn", "red"))
            if start_turn not in engine.PLAYERS:
                raise ValueError("start_turn must be red or blue")
            search_time = max(0.05, min(float(payload.get("time", 0.5)), 3.0))
            depth = max(1, min(int(payload.get("depth", 3)), 5))
            engine_kind = str(payload.get("engine", DEFAULT_ENGINE))
            if engine_kind not in SUPPORTED_ENGINES:
                raise ValueError("engine must be alpha-beta, mcts, hybrid, or expert")
            recommend_for_turn = bool(payload.get("recommend_for_turn", False))
            suppress_recommend = bool(payload.get("suppress_recommend", False))
            history_tokens = engine.tokenize_history(history)
            state = engine.state_from_history(history, start_turn=start_turn)
            avoid_actions = root_avoid_actions(history, start_turn)
            mcts_seed = len(history_tokens)
            self.write_json({
                "ok": True,
                "state": state_payload(
                    state,
                    user_side,
                    search_time,
                    depth,
                    engine_kind,
                    recommend_for_turn,
                    start_turn,
                    avoid_actions,
                    mcts_seed,
                    history_tokens,
                    suppress_recommend,
                ),
            })
        except Exception as exc:
            self.write_json({"ok": False, "error": str(exc)}, status=400)

    def serve_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def write_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Barricade offline trainer web UI.")
    default_host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    default_port = int(os.environ.get("PORT", "8765"))
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Barricade Trainer running at http://{args.host}:{args.port}")
    print("Use Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
