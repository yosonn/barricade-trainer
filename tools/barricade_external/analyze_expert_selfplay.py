#!/usr/bin/env python3
"""Analyze Barricade.gg Expert self-play logs and extract cache candidates."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import barricade_trainer as engine
from barricade_expert_cache import expert_state_key


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_games(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        return read_jsonl(path)

    names = {"combined-games.jsonl", "merged-games.jsonl", "games.jsonl"}
    games: list[dict[str, Any]] = []
    for file in sorted(path.rglob("*.jsonl")):
        if file.name in names:
            games.extend(read_jsonl(file))

    # Prefer merged/combined files when present to avoid counting worker files twice.
    merged = [g for g in games if "combined_game_id" in g or "global_game_id" in g]
    return merged or games


def normalize_game(game: dict[str, Any], index: int) -> dict[str, Any]:
    history = game.get("history") or []
    if isinstance(history, str):
        history = engine.tokenize_history(history)
    return {
        "id": game.get("combined_game_id") or game.get("global_game_id") or game.get("game") or index,
        "winner": game.get("winner"),
        "plies": int(game.get("plies") or len(history)),
        "reason": game.get("terminal_reason") or game.get("reason") or "",
        "history": [str(action).lower() for action in history],
        "source_run": game.get("source_run") or "",
    }


def analyze_turn(game: dict[str, Any], ply: int, state: engine.State, history_before: list[str], action: str) -> dict[str, Any]:
    side = state.turn
    opp = engine.opponent(side)
    self_before, self_path_before = engine.movement_path(state, side)
    opp_before, opp_path_before = engine.movement_path(state, opp)
    child = engine.apply_action(state, action)
    self_after, self_path_after = engine.movement_path(child, side)
    opp_after, opp_path_after = engine.movement_path(child, opp)
    kind = "pawn" if engine.is_pawn_action(action) else "wall"
    wall_orient = ""
    if kind == "wall":
        wall_orient = engine.text_to_wall(action)[0]
    return {
        "game": game["id"],
        "ply": ply,
        "phase": "opening" if ply <= 16 else "midgame" if ply <= 44 else "endgame",
        "side": side,
        "action": action,
        "kind": kind,
        "wall_orient": wall_orient,
        "red_walls_before": state.red_walls,
        "blue_walls_before": state.blue_walls,
        "self_dist_before": self_before,
        "self_dist_after": self_after,
        "opp_dist_before": opp_before,
        "opp_dist_after": opp_after,
        "self_progress": self_before - self_after,
        "opp_delay": opp_after - opp_before,
        "score_before": round(engine.static_eval(state, side), 1),
        "score_after": round(engine.static_eval(child, side), 1),
        "self_path_before": " ".join(engine.coord_to_text(pos) for pos in self_path_before),
        "opp_path_before": " ".join(engine.coord_to_text(pos) for pos in opp_path_before),
        "self_path_after": " ".join(engine.coord_to_text(pos) for pos in self_path_after),
        "opp_path_after": " ".join(engine.coord_to_text(pos) for pos in opp_path_after),
        "state_key": expert_state_key(state),
        "history_before": " ".join(history_before),
    }


def build_turns(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for raw_index, raw_game in enumerate(games, 1):
        game = normalize_game(raw_game, raw_index)
        state = engine.State()
        history_before: list[str] = []
        for ply, action in enumerate(game["history"], 1):
            turns.append(analyze_turn(game, ply, state, history_before, action))
            state = engine.apply_action(state, action)
            history_before.append(action)
    return turns


def cache_candidates(turns: list[dict[str, Any]], min_count: int, min_confidence: float) -> list[dict[str, Any]]:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    history_buckets: dict[str, Counter[str]] = defaultdict(Counter)
    for turn in turns:
        buckets[str(turn["state_key"])][str(turn["action"])] += 1
        history_buckets[str(turn["history_before"])][str(turn["action"])] += 1

    rows: list[dict[str, Any]] = []
    for source, data in (("state", buckets), ("history", history_buckets)):
        for key, counts in data.items():
            total = sum(counts.values())
            action, count = counts.most_common(1)[0]
            confidence = count / total
            if total >= min_count and confidence >= min_confidence:
                rows.append({
                    "source": source,
                    "key": key,
                    "best_action": action,
                    "count": count,
                    "total": total,
                    "confidence": round(confidence, 4),
                    "actions": dict(counts),
                })
    rows.sort(key=lambda row: (row["count"], row["confidence"]), reverse=True)
    return rows


def summarize(games: list[dict[str, Any]], turns: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    winners = Counter(normalize_game(game, index)["winner"] or "none" for index, game in enumerate(games, 1))
    wall_turns = [turn for turn in turns if turn["kind"] == "wall"]
    request_times = []
    for game in games:
        for turn in game.get("turns", []):
            value = turn.get("request_ms") or turn.get("ms")
            if value not in (None, ""):
                request_times.append(float(value))
    return {
        "games": len(games),
        "turns": len(turns),
        "winners": dict(winners),
        "avg_plies": round(statistics.mean([normalize_game(game, i)["plies"] for i, game in enumerate(games, 1)]), 2) if games else 0,
        "wall_rate": round(len(wall_turns) / len(turns), 4) if turns else 0,
        "wall_orients": dict(Counter(turn["wall_orient"] for turn in wall_turns if turn["wall_orient"])),
        "phase_wall_counts": dict(Counter(turn["phase"] for turn in wall_turns)),
        "zero_delay_walls": sum(1 for turn in wall_turns if int(turn["opp_delay"]) == 0),
        "delay_walls": sum(1 for turn in wall_turns if int(turn["opp_delay"]) > 0),
        "top_actions": Counter(turn["action"] for turn in turns).most_common(20),
        "top_walls": Counter(turn["action"] for turn in wall_turns).most_common(20),
        "avg_request_ms": round(statistics.mean(request_times), 1) if request_times else None,
        "cache_candidates": len(candidates),
        "top_cache_candidates": candidates[:20],
    }


def write_outputs(out_dir: Path, games: list[dict[str, Any]], turns: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(games, turns, candidates)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "cache-candidates.json").write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out_dir / "turns.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(turns[0].keys()))
        writer.writeheader()
        writer.writerows(turns)
    lines = [
        "# Expert Self-Play Analysis",
        "",
        f"- Games: {summary['games']}",
        f"- Turns: {summary['turns']}",
        f"- Winners: {summary['winners']}",
        f"- Avg plies: {summary['avg_plies']}",
        f"- Wall rate: {summary['wall_rate']}",
        f"- Wall orientation: {summary['wall_orients']}",
        f"- Delay walls / zero-delay walls: {summary['delay_walls']} / {summary['zero_delay_walls']}",
        f"- Avg request ms: {summary['avg_request_ms']}",
        f"- High-confidence cache candidates: {summary['cache_candidates']}",
        "",
        "## Top Cache Candidates",
        "",
    ]
    for row in candidates[:20]:
        lines.append(f"- {row['source']} `{row['key']}` -> `{row['best_action']}` ({row['count']}/{row['total']}, {row['confidence']})")
    lines.extend(["", "## Top Walls", ""])
    for action, count in summary["top_walls"]:
        lines.append(f"- `{action}`: {count}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Expert self-play logs.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-count", type=int, default=3)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    args = parser.parse_args()
    games = load_games(args.input)
    turns = build_turns(games)
    candidates = cache_candidates(turns, args.min_count, args.min_confidence)
    write_outputs(args.out_dir, games, turns, candidates)
    print(f"games={len(games)} turns={len(turns)} candidates={len(candidates)}")
    print(f"wrote {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
