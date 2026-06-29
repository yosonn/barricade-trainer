#!/usr/bin/env python3
"""Play Barricade.gg's online Expert computer against the local engine.

The public site asks its remote AI service for a move through Socket.IO.  This
tool uses the same polling transport with only the Python standard library so
external regression games can be replayed and audited without browser clicks.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import barricade_trainer as engine
import barricade_web as web
from barricade_expert import BarricadeGgAiClient


@dataclass(frozen=True)
class TurnRecord:
    ply: int
    side: str
    player: str
    action: str
    resolved_engine: str | None
    score_before: float
    score_after: float
    my_dist_before: int
    opp_dist_before: int
    my_dist_after: int
    opp_dist_after: int
    legal: bool


@dataclass(frozen=True)
class ExternalGameResult:
    generated_at: str
    difficulty: str
    local_side: str
    local_engine: str
    winner: str | None
    winner_player: str | None
    plies: int
    terminal_reason: str
    history: list[str]
    turns: list[TurnRecord]
    errors: list[str]


def opposite(side: str) -> str:
    return "blue" if side == "red" else "red"


def analyze_action(state: engine.State, action: str, side: str, player: str, resolved_engine: str | None) -> TurnRecord:
    opp = opposite(side)
    if engine.is_pawn_action(action):
        legal = engine.text_to_coord(action) in engine.legal_pawn_moves(state)
    else:
        legal = engine.can_place_wall(state, engine.text_to_wall(action))
    before_score = engine.static_eval(state, side)
    my_before, _ = engine.movement_path(state, side)
    opp_before, _ = engine.movement_path(state, opp)
    child = engine.apply_action(state, action)
    after_score = engine.static_eval(child, side)
    my_after, _ = engine.movement_path(child, side)
    opp_after, _ = engine.movement_path(child, opp)
    return TurnRecord(
        ply=0,
        side=side,
        player=player,
        action=action,
        resolved_engine=resolved_engine,
        score_before=round(before_score, 1),
        score_after=round(after_score, 1),
        my_dist_before=my_before,
        opp_dist_before=opp_before,
        my_dist_after=my_after,
        opp_dist_after=opp_after,
        legal=legal,
    )


def local_recommendation(
    state: engine.State,
    history: list[str],
    engine_kind: str,
    time_limit: float,
    depth: int,
) -> tuple[str, float, int, str]:
    avoid = web.root_avoid_actions(" ".join(history), "red")
    return web.recommend_action(
        state,
        search_time=time_limit,
        depth=depth,
        engine_kind=engine_kind,
        avoid_actions=avoid,
        seed=len(history),
    )


def play_game(args: argparse.Namespace) -> ExternalGameResult:
    ai = BarricadeGgAiClient(args.difficulty, timeout=args.timeout, pause_sec=args.pause_sec)
    history: list[str] = []
    turns: list[TurnRecord] = []
    errors: list[str] = []
    terminal_reason = "max_plies"
    winner: str | None = None

    for ply in range(1, args.max_plies + 1):
        state = engine.state_from_history(" ".join(history), start_turn="red")
        winner = web.winner(state)
        if winner:
            terminal_reason = "winner"
            break

        side = state.turn
        player = "local" if side == args.local_side else "barricade.gg"
        resolved_engine: str | None = None
        try:
            if player == "local":
                action, _, _, resolved_engine = local_recommendation(
                    state,
                    history,
                    args.local_engine,
                    args.time,
                    args.depth,
                )
            else:
                action = ai.get_move(history)
        except Exception as exc:
            errors.append(f"ply {ply} {player} failed: {exc}")
            terminal_reason = "external_error" if player == "barricade.gg" else "local_error"
            break

        try:
            record = analyze_action(state, action, side, player, resolved_engine)
            record = TurnRecord(**{**asdict(record), "ply": ply})
            if not record.legal:
                errors.append(f"ply {ply} illegal {player} action {action}")
                terminal_reason = "illegal_action"
                break
            history.append(action)
            turns.append(record)
        except Exception as exc:
            errors.append(f"ply {ply} could not apply {player} action {action!r}: {exc}")
            terminal_reason = "apply_error"
            break
    else:
        state = engine.state_from_history(" ".join(history), start_turn="red")
        winner = web.winner(state)
        if winner:
            terminal_reason = "winner"

    winner_player = None
    if winner:
        winner_player = "local" if winner == args.local_side else "barricade.gg"

    return ExternalGameResult(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        difficulty=args.difficulty,
        local_side=args.local_side,
        local_engine=args.local_engine,
        winner=winner,
        winner_player=winner_player,
        plies=len(history),
        terminal_reason=terminal_reason,
        history=history,
        turns=turns,
        errors=errors,
    )


def render_markdown(result: ExternalGameResult) -> str:
    local_turns = [turn for turn in result.turns if turn.player == "local"]
    expert_turns = [turn for turn in result.turns if turn.player == "barricade.gg"]
    local_drops = sorted(local_turns, key=lambda turn: turn.score_after - turn.score_before)[:5]
    expert_gains = sorted(expert_turns, key=lambda turn: turn.opp_dist_after - turn.opp_dist_before, reverse=True)[:5]
    avg_local_delta = statistics.mean([turn.score_after - turn.score_before for turn in local_turns]) if local_turns else 0

    lines = [
        "# Barricade.gg Expert Match",
        "",
        f"- Generated: {result.generated_at}",
        f"- Difficulty: {result.difficulty}",
        f"- Local side: {result.local_side}",
        f"- Local engine: {result.local_engine}",
        f"- Winner: {result.winner or '-'} ({result.winner_player or '-'})",
        f"- Plies: {result.plies}",
        f"- Terminal reason: {result.terminal_reason}",
        f"- Average local score delta: {round(avg_local_delta, 1)}",
        f"- Errors: {'; '.join(result.errors) if result.errors else '-'}",
        f"- Replay: `{' '.join(result.history)}`",
        "",
        "## Biggest Local Score Drops",
        "",
    ]
    for turn in local_drops:
        lines.append(
            f"- Ply {turn.ply} {turn.side} {turn.action}: score {turn.score_before} -> "
            f"{turn.score_after}, dist {turn.my_dist_before}/{turn.opp_dist_before} -> "
            f"{turn.my_dist_after}/{turn.opp_dist_after}, engine={turn.resolved_engine}"
        )
    lines.extend(["", "## Expert Delay Moves", ""])
    for turn in expert_gains:
        lines.append(
            f"- Ply {turn.ply} {turn.side} {turn.action}: local-opponent dist "
            f"{turn.my_dist_before}/{turn.opp_dist_before} -> {turn.my_dist_after}/{turn.opp_dist_after}"
        )
    return "\n".join(lines) + "\n"


def write_outputs(result: ExternalGameResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    (out_dir / "game.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_markdown(result), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play local Barricade AI against Barricade.gg computer.")
    parser.add_argument("--difficulty", choices=("easy", "medium", "hard", "expert"), default="expert")
    parser.add_argument("--local-side", choices=("red", "blue"), default="red")
    parser.add_argument("--local-engine", choices=("alpha-beta", "mcts", "hybrid"), default="hybrid")
    parser.add_argument("--time", type=float, default=0.25)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=220)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--pause-sec", type=float, default=1.0)
    parser.add_argument("--out-dir", type=Path, default=Path("backtest_runs") / "barricade-gg-expert-latest")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = play_game(args)
    write_outputs(result, args.out_dir)
    print(f"winner={result.winner or '-'} player={result.winner_player or '-'} plies={result.plies}")
    print(f"reason={result.terminal_reason}")
    print(f"history={' '.join(result.history)}")
    print(f"wrote {args.out_dir}")
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
