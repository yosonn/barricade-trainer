#!/usr/bin/env python3
"""Collect complete Barricade.gg Expert-vs-Expert self-play games."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import barricade_trainer as engine
import barricade_web as web
from barricade_expert import BarricadeGgAiClient
from barricade_expert_cache import expert_state_key


def normalize_action(action: str) -> str:
    action = action.strip().lower()
    if engine.is_pawn_action(action):
        return engine.coord_to_text(engine.text_to_coord(action))
    return engine.wall_to_text(engine.text_to_wall(action))


def phase_of_ply(ply: int) -> str:
    if ply <= 16:
        return "opening"
    if ply <= 44:
        return "midgame"
    return "endgame"


def get_expert_move(client: BarricadeGgAiClient, history: list[str], retries: int, retry_sleep: float) -> tuple[str, float, int]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            action = normalize_action(client.get_move(history))
            return action, round((time.perf_counter() - started) * 1000, 1), attempt
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(retry_sleep)
    raise RuntimeError(str(last_error))


def analyze_turn(
    worker_id: str,
    game_no: int,
    ply: int,
    state: engine.State,
    history_before: list[str],
    action: str,
    request_ms: float,
    retries_used: int,
    prefix_id: str,
    prefix: str,
    prefix_len: int,
) -> dict[str, Any]:
    side = state.turn
    opp = engine.opponent(side)
    self_before, self_path_before = engine.movement_path(state, side)
    opp_before, opp_path_before = engine.movement_path(state, opp)
    score_before = engine.static_eval(state, side)
    child = engine.apply_action(state, action)
    self_after, self_path_after = engine.movement_path(child, side)
    opp_after, opp_path_after = engine.movement_path(child, opp)
    score_after = engine.static_eval(child, side)
    kind = "pawn" if engine.is_pawn_action(action) else "wall"
    wall_orient = ""
    wall_anchor = ""
    if kind == "wall":
        wall = engine.text_to_wall(action)
        wall_orient = wall[0]
        wall_anchor = engine.wall_to_text(wall)
    return {
        "worker_id": worker_id,
        "game": game_no,
        "prefix_id": prefix_id,
        "prefix": prefix,
        "prefix_len": prefix_len,
        "ply": ply,
        "phase": phase_of_ply(ply),
        "side": side,
        "action": action,
        "kind": kind,
        "wall_orient": wall_orient,
        "wall_anchor": wall_anchor,
        "red_pos_before": engine.coord_to_text(state.red),
        "blue_pos_before": engine.coord_to_text(state.blue),
        "red_walls_before": state.red_walls,
        "blue_walls_before": state.blue_walls,
        "self_dist_before": self_before,
        "self_dist_after": self_after,
        "opp_dist_before": opp_before,
        "opp_dist_after": opp_after,
        "self_progress": self_before - self_after,
        "opp_delay": opp_after - opp_before,
        "score_before": round(score_before, 1),
        "score_after": round(score_after, 1),
        "score_delta": round(score_after - score_before, 1),
        "request_ms": request_ms,
        "retries_used": retries_used,
        "self_path_before": " ".join(engine.coord_to_text(pos) for pos in self_path_before),
        "opp_path_before": " ".join(engine.coord_to_text(pos) for pos in opp_path_before),
        "self_path_after": " ".join(engine.coord_to_text(pos) for pos in self_path_after),
        "opp_path_after": " ".join(engine.coord_to_text(pos) for pos in opp_path_after),
        "state_key": expert_state_key(state),
        "history_before": " ".join(history_before),
        "expert_action": action,
    }


def play_game(game_no: int, args: argparse.Namespace) -> dict[str, Any]:
    client = BarricadeGgAiClient("expert", timeout=args.timeout, pause_sec=args.pause_sec)
    prefix_tokens = list(getattr(args, "prefix_tokens", []))
    prefix = " ".join(prefix_tokens)
    prefix_len = len(prefix_tokens)
    history: list[str] = list(prefix_tokens)
    turns: list[dict[str, Any]] = []
    errors: list[str] = []
    terminal_reason = "max_plies"
    for ply in range(prefix_len + 1, args.max_plies + 1):
        state = engine.state_from_history(" ".join(history), start_turn="red")
        if web.winner(state):
            terminal_reason = "winner"
            break
        try:
            history_before = list(history)
            action, request_ms, retries_used = get_expert_move(client, list(history), args.retries, args.retry_sleep)
            row = analyze_turn(
                args.worker_id,
                game_no,
                ply,
                state,
                history_before,
                action,
                request_ms,
                retries_used,
                args.prefix_id,
                prefix,
                prefix_len,
            )
            turns.append(row)
            history.append(action)
            print(f"G{game_no:02d} ply {ply:03d} {state.turn} {action} {request_ms}ms retry={retries_used}", flush=True)
        except Exception as exc:
            errors.append(f"ply {ply} {state.turn}: {exc}")
            terminal_reason = "expert_error"
            break
    final_state = engine.state_from_history(" ".join(history), start_turn="red")
    return {
        "worker_id": args.worker_id,
        "game": game_no,
        "prefix_id": args.prefix_id,
        "prefix": prefix,
        "prefix_len": prefix_len,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "winner": web.winner(final_state),
        "plies": len(history),
        "terminal_reason": terminal_reason,
        "history": history,
        "history_text": " ".join(history),
        "errors": errors,
        "turns": turns,
    }


def summarize(games: list[dict[str, Any]], turns: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [game for game in games if game["terminal_reason"] == "winner"]
    errored = [game for game in games if game["terminal_reason"] == "expert_error"]
    wall_turns = [turn for turn in turns if turn["kind"] == "wall"]
    request_ms = [float(turn["request_ms"]) for turn in turns]
    return {
        "worker_id": games[0]["worker_id"] if games else "",
        "prefix_id": games[0].get("prefix_id", "") if games else "",
        "prefix": games[0].get("prefix", "") if games else "",
        "prefix_len": games[0].get("prefix_len", 0) if games else 0,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "games": len(games),
        "completed_games": len(completed),
        "errored_games": len(errored),
        "winners": dict(Counter(game["winner"] or "none" for game in games)),
        "terminal_reasons": dict(Counter(game["terminal_reason"] for game in games)),
        "avg_plies_completed": round(statistics.mean(game["plies"] for game in completed), 2) if completed else 0,
        "total_turns": len(turns),
        "pawn_turns": len(turns) - len(wall_turns),
        "wall_turns": len(wall_turns),
        "wall_rate": round(len(wall_turns) / len(turns), 4) if turns else 0,
        "wall_orient_counts": dict(Counter(turn["wall_orient"] for turn in wall_turns if turn["wall_orient"])),
        "phase_wall_counts": dict(Counter(turn["phase"] for turn in wall_turns)),
        "top_wall_anchors": Counter(turn["wall_anchor"] for turn in wall_turns if turn["wall_anchor"]).most_common(30),
        "avg_request_ms": round(statistics.mean(request_ms), 1) if request_ms else 0,
        "p95_request_ms": round(statistics.quantiles(request_ms, n=20)[18], 1) if len(request_ms) >= 20 else 0,
        "retry_count": sum(int(turn["retries_used"]) for turn in turns),
        "unique_histories": len(set(game["history_text"] for game in games)),
    }


def write_outputs(out_dir: Path, games: list[dict[str, Any]], turns: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "games.jsonl").open("w", encoding="utf-8") as handle:
        for game in games:
            handle.write(json.dumps(game, ensure_ascii=False) + "\n")
    with (out_dir / "turns.jsonl").open("w", encoding="utf-8") as handle:
        for turn in turns:
            handle.write(json.dumps(turn, ensure_ascii=False) + "\n")
    if turns:
        with (out_dir / "turns.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(turns[0].keys()))
            writer.writeheader()
            writer.writerows(turns)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Expert-vs-Expert Self-Play Collection",
        "",
        f"- Games: {summary['games']}",
        f"- Prefix ID: {summary['prefix_id'] or '-'}",
        f"- Prefix length: {summary['prefix_len']}",
        f"- Prefix: {summary['prefix'] or '-'}",
        f"- Completed: {summary['completed_games']}",
        f"- Winners: {summary['winners']}",
        f"- Avg plies completed: {summary['avg_plies_completed']}",
        f"- Turns: {summary['total_turns']}",
        f"- Wall rate: {summary['wall_rate']}",
        f"- Avg request ms: {summary['avg_request_ms']}",
        f"- P95 request ms: {summary['p95_request_ms']}",
        f"- Retry count: {summary['retry_count']}",
        "",
        "## Top Wall Anchors",
        "",
    ]
    for anchor, count in summary["top_wall_anchors"]:
        lines.append(f"- `{anchor}`: {count}")
    lines.extend(["", "## Histories", ""])
    for game in games:
        lines.append(f"- G{game['game']} winner={game['winner']} plies={game['plies']} history={game['history_text']}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Barricade.gg Expert-vs-Expert self-play data.")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--max-plies", type=int, default=220)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--pause-sec", type=float, default=1.2)
    parser.add_argument("--worker-id", default="manual-expert-20")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--prefix-id", default="")
    return parser.parse_args()


def validate_prefix(prefix: str) -> list[str]:
    tokens = engine.tokenize_history(prefix)
    engine.state_from_history(" ".join(tokens), start_turn="red")
    return tokens


def main() -> int:
    args = parse_args()
    try:
        args.prefix_tokens = validate_prefix(args.prefix)
    except Exception as exc:
        print(f"Invalid --prefix: {exc}", file=sys.stderr)
        return 2
    if args.out_dir is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix_part = f"-{args.prefix_id}" if args.prefix_id else ""
        args.out_dir = Path("backtest_runs") / f"expert-vs-expert-{args.games}{prefix_part}-{stamp}"
    games: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    for game_no in range(1, args.games + 1):
        print(f"Running Expert-vs-Expert game {game_no}/{args.games}", flush=True)
        game = play_game(game_no, args)
        games.append(game)
        turns.extend(game["turns"])
        print(f"G{game_no:02d} done winner={game['winner'] or '-'} plies={game['plies']} reason={game['terminal_reason']}", flush=True)
    summary = summarize(games, turns)
    write_outputs(args.out_dir, games, turns, summary)
    print(f"Wrote complete self-play data to {args.out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
