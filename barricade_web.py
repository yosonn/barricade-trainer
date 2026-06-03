from __future__ import annotations

import json
import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import barricade_trainer as engine


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "barricade_frontend"
APP_VERSION = "2026.06.03.03"


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


def state_payload(
    state: engine.State,
    user_side: str,
    search_time: float,
    depth: int,
    recommend_for_turn: bool = False,
    start_turn: str = "red",
    avoid_actions: set[str] | None = None,
) -> dict:
    red_dist, red_path = engine.shortest_path(state, "red")
    blue_dist, blue_path = engine.shortest_path(state, "blue")
    actions = engine.ordered_actions(state, limit_walls=18)
    win = winner(state)
    red_score = engine.static_eval(state, "red")
    blue_score = engine.static_eval(state, "blue")
    recommendation = None
    score = None
    searched_depth = None
    recommend_side = state.turn if recommend_for_turn else user_side
    if state.turn == recommend_side and actions:
        recommendation, score, searched_depth = engine.search_best(
            state,
            time_limit=search_time,
            max_depth=depth,
            avoid_actions=avoid_actions,
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
        "recommendation": recommendation,
        "score": score,
        "searched_depth": searched_depth,
        "winner": win,
        "red_win_rate": win_rate_from_score(red_score),
        "blue_win_rate": win_rate_from_score(blue_score),
        "red_verdict": verdict(red_score, win, "red"),
        "blue_verdict": verdict(blue_score, win, "blue"),
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
            recommend_for_turn = bool(payload.get("recommend_for_turn", False))
            state = engine.state_from_history(history, start_turn=start_turn)
            avoid_actions = recent_reversal_avoid_actions(history, start_turn)
            self.write_json({
                "ok": True,
                "state": state_payload(
                    state,
                    user_side,
                    search_time,
                    depth,
                    recommend_for_turn,
                    start_turn,
                    avoid_actions,
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
