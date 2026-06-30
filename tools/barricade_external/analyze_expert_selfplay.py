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


def analyze_turn(
    game: dict[str, Any],
    ply: int,
    state: engine.State,
    history_before: list[str],
    action: str,
    with_hybrid_ranking: bool = False,
) -> dict[str, Any]:
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
    expert_rank = None
    if with_hybrid_ranking:
        ordered = engine.ordered_actions(state, limit_walls=18)
        expert_rank = ordered.index(action) + 1 if action in ordered else None
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
        "hybrid_rank": expert_rank,
    }


def build_turns(games: list[dict[str, Any]], with_hybrid_ranking: bool = False) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for raw_index, raw_game in enumerate(games, 1):
        game = normalize_game(raw_game, raw_index)
        state = engine.State()
        history_before: list[str] = []
        for ply, action in enumerate(game["history"], 1):
            turns.append(analyze_turn(game, ply, state, history_before, action, with_hybrid_ranking))
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


def opening_tree(turns: list[dict[str, Any]], max_ply: int = 16) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for turn in turns:
        ply = int(turn["ply"])
        if ply > max_ply:
            continue
        buckets[(ply, str(turn["history_before"]))][str(turn["action"])] += 1
    rows: list[dict[str, Any]] = []
    for (ply, history), actions in buckets.items():
        total = sum(actions.values())
        best_action, best_count = actions.most_common(1)[0]
        rows.append({
            "ply": ply,
            "history": history,
            "best_action": best_action,
            "count": best_count,
            "total": total,
            "confidence": round(best_count / total, 4),
            "actions": dict(actions),
        })
    rows.sort(key=lambda row: (row["ply"], -row["total"], row["history"]))
    return rows


def trap_wall_stats(turns: list[dict[str, Any]]) -> dict[str, Any]:
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for turn in turns:
        by_game[str(turn["game"])].append(turn)
    direct: list[dict[str, Any]] = []
    prep: list[dict[str, Any]] = []
    quiet: list[dict[str, Any]] = []
    for game_turns in by_game.values():
        ordered = sorted(game_turns, key=lambda turn: int(turn["ply"]))
        for index, turn in enumerate(ordered):
            if turn["kind"] != "wall":
                continue
            if int(turn["opp_delay"]) > 0:
                direct.append(turn)
                continue
            later_same_side = [
                later for later in ordered[index + 1:index + 7]
                if later["side"] == turn["side"] and later["kind"] == "wall" and int(later["opp_delay"]) > 0
            ]
            if later_same_side:
                prep.append(turn)
            else:
                quiet.append(turn)
    return {
        "direct_effective_count": len(direct),
        "prep_wall_count": len(prep),
        "quiet_zero_delay_count": len(quiet),
        "top_direct_walls": Counter(turn["action"] for turn in direct).most_common(15),
        "top_prep_walls": Counter(turn["action"] for turn in prep).most_common(15),
        "top_quiet_walls": Counter(turn["action"] for turn in quiet).most_common(15),
    }


def race_decision_stats(turns: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    for turn in turns:
        self_dist = int(turn["self_dist_before"])
        opp_dist = int(turn["opp_dist_before"])
        if self_dist <= 3:
            bucket = "self_dist_le_3"
        elif opp_dist <= 3:
            bucket = "opp_dist_le_3"
        elif abs(self_dist - opp_dist) <= 1:
            bucket = "close_race"
        elif self_dist + 3 <= opp_dist:
            bucket = "leading_by_3_plus"
        elif opp_dist + 3 <= self_dist:
            bucket = "trailing_by_3_plus"
        else:
            bucket = "balanced"
        action_type = "wall" if turn["kind"] == "wall" else "progress" if int(turn["self_progress"]) > 0 else "reposition"
        buckets[bucket][action_type] += 1
    return {bucket: dict(counts) for bucket, counts in sorted(buckets.items())}


def hybrid_rank_stats(turns: list[dict[str, Any]]) -> dict[str, Any]:
    ranks = [int(turn["hybrid_rank"]) for turn in turns if turn.get("hybrid_rank") not in (None, "")]
    if not ranks:
        return {}
    return {
        "ranked_turns": len(ranks),
        "top1_rate": round(sum(rank == 1 for rank in ranks) / len(ranks), 4),
        "top3_rate": round(sum(rank <= 3 for rank in ranks) / len(ranks), 4),
        "top5_rate": round(sum(rank <= 5 for rank in ranks) / len(ranks), 4),
        "avg_rank": round(statistics.mean(ranks), 2),
        "rank_counts": dict(Counter(ranks).most_common(15)),
    }


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
        "opening_tree": opening_tree(turns)[:80],
        "trap_walls": trap_wall_stats(turns),
        "race_decisions": race_decision_stats(turns),
        "hybrid_rank": hybrid_rank_stats(turns),
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
        f"- Hybrid rank top1/top3/top5: {summary['hybrid_rank'].get('top1_rate')} / {summary['hybrid_rank'].get('top3_rate')} / {summary['hybrid_rank'].get('top5_rate')}",
        "",
        "## Top Cache Candidates",
        "",
    ]
    for row in candidates[:20]:
        lines.append(f"- {row['source']} `{row['key']}` -> `{row['best_action']}` ({row['count']}/{row['total']}, {row['confidence']})")
    lines.extend(["", "## Opening Tree", ""])
    for row in summary["opening_tree"][:30]:
        lines.append(f"- ply {row['ply']} `{row['history']}` -> `{row['best_action']}` ({row['count']}/{row['total']}, {row['confidence']})")
    lines.extend(["", "## Top Walls", ""])
    for action, count in summary["top_walls"]:
        lines.append(f"- `{action}`: {count}")
    lines.extend(["", "## Trap Wall Summary", ""])
    trap = summary["trap_walls"]
    lines.append(f"- Direct effective walls: {trap['direct_effective_count']}")
    lines.append(f"- Prep zero-delay walls: {trap['prep_wall_count']}")
    lines.append(f"- Quiet zero-delay walls: {trap['quiet_zero_delay_count']}")
    lines.append(f"- Top prep walls: {trap['top_prep_walls']}")
    lines.extend(["", "## Race Decisions", ""])
    for bucket, counts in summary["race_decisions"].items():
        lines.append(f"- {bucket}: {counts}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Expert self-play logs.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-count", type=int, default=3)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--with-hybrid-ranking", action="store_true")
    args = parser.parse_args()
    games = load_games(args.input)
    turns = build_turns(games, with_hybrid_ranking=args.with_hybrid_ranking)
    candidates = cache_candidates(turns, args.min_count, args.min_confidence)
    write_outputs(args.out_dir, games, turns, candidates)
    print(f"games={len(games)} turns={len(turns)} candidates={len(candidates)}")
    print(f"wrote {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
