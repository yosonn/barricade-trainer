#!/usr/bin/env python3
"""Audit lost backtest games and compare decisions against alpha-beta."""

from __future__ import annotations

import argparse
import json
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


@dataclass
class DecisionAudit:
    ply: int
    side: str
    actual: str
    alpha_beta: str
    actual_score: float
    alpha_beta_score: float
    regret: float
    actual_my_delta: int | float
    actual_opp_delta: int | float
    alpha_beta_my_delta: int | float
    alpha_beta_opp_delta: int | float
    phase: str
    reasons: list[str]
    history_before: list[str]


@dataclass
class GameAudit:
    game_id: int
    audited_engine: str
    audited_side: str
    winner: str | None
    winner_engine: str | None
    plies: int
    audited_decisions: int
    top_suspects: list[DecisionAudit]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def games_path_from_input(path: Path) -> Path:
    if path.is_dir():
        return path / "games.jsonl"
    return path


def side_to_move(start_turn: str, ply: int) -> str:
    if ply % 2 == 0:
        return start_turn
    return engine.opponent(start_turn)


def score_action(state: engine.State, action: str, perspective: str) -> float:
    try:
        return float(engine.action_score(state, action, perspective))
    except Exception:
        return float("-inf")


def distance_delta(state: engine.State, action: str, perspective: str) -> tuple[int | float, int | float]:
    opp = engine.opponent(perspective)
    child = engine.apply_action(state, action)
    my_before = engine.movement_path(state, perspective)[0]
    opp_before = engine.movement_path(state, opp)[0]
    my_after = engine.movement_path(child, perspective)[0]
    opp_after = engine.movement_path(child, opp)[0]
    return my_before - my_after, opp_after - opp_before


def classify_phase(state: engine.State, perspective: str) -> str:
    opp = engine.opponent(perspective)
    my_dist = engine.movement_path(state, perspective)[0]
    opp_dist = engine.movement_path(state, opp)[0]
    walls = state.walls_left("red") + state.walls_left("blue")
    if min(my_dist, opp_dist) <= 2:
        return "finish"
    if walls <= 3:
        return "low-wall-race"
    if len(state.walls) <= 4:
        return "opening"
    return "midgame"


def explain_regret(
    state: engine.State,
    actual: str,
    alpha_beta: str,
    perspective: str,
    regret: float,
) -> list[str]:
    reasons: list[str] = []
    actual_my, actual_opp = distance_delta(state, actual, perspective)
    best_my, best_opp = distance_delta(state, alpha_beta, perspective)
    actual_child = engine.apply_action(state, actual)
    opp = engine.opponent(perspective)

    if regret >= 1000:
        reasons.append("large-score-divergence")
    elif regret >= 250:
        reasons.append("medium-score-divergence")
    if best_my > actual_my:
        reasons.append("missed-faster-progress")
    if best_opp > actual_opp:
        reasons.append("missed-better-delay")
    if engine.player_has_goal_move(actual_child, opp):
        reasons.append("allowed-opponent-goal-threat")
    if not engine.is_pawn_action(actual) and actual_opp <= 0:
        reasons.append("low-impact-wall")
    if engine.is_pawn_action(actual) and actual_my < 0:
        reasons.append("stepped-away-from-goal")
    if not reasons:
        reasons.append("style-divergence")
    return reasons


def audit_decision(
    history_before: list[str],
    action: str,
    start_turn: str,
    search_time: float,
    depth: int,
) -> DecisionAudit:
    state = engine.state_from_history(" ".join(history_before), start_turn=start_turn)
    side = state.turn
    avoid_actions = web.recent_reversal_avoid_actions(" ".join(history_before), start_turn)
    alpha_beta, _, _ = engine.search_best(
        state,
        time_limit=search_time,
        max_depth=depth,
        avoid_actions=avoid_actions,
    )
    actual_score = score_action(state, action, side)
    alpha_action_score = score_action(state, alpha_beta, side)
    regret = alpha_action_score - actual_score
    actual_my, actual_opp = distance_delta(state, action, side)
    best_my, best_opp = distance_delta(state, alpha_beta, side)
    return DecisionAudit(
        ply=len(history_before) + 1,
        side=side,
        actual=action,
        alpha_beta=alpha_beta,
        actual_score=round(actual_score, 1),
        alpha_beta_score=round(alpha_action_score, 1),
        regret=round(regret, 1),
        actual_my_delta=actual_my,
        actual_opp_delta=actual_opp,
        alpha_beta_my_delta=best_my,
        alpha_beta_opp_delta=best_opp,
        phase=classify_phase(state, side),
        reasons=explain_regret(state, action, alpha_beta, side, regret),
        history_before=list(history_before),
    )


def audited_side_for_game(record: dict[str, Any], engine_name: str) -> str | None:
    if record.get("red_engine") == engine_name:
        return "red"
    if record.get("blue_engine") == engine_name:
        return "blue"
    return None


def audit_game(
    record: dict[str, Any],
    engine_name: str,
    search_time: float,
    depth: int,
    max_suspects: int,
    min_regret: float,
) -> GameAudit | None:
    audited_side = audited_side_for_game(record, engine_name)
    if not audited_side or record.get("winner_engine") == engine_name:
        return None

    start_turn = str(record.get("start_turn") or "red")
    history = list(record.get("history") or [])
    audits: list[DecisionAudit] = []
    for index, action in enumerate(history):
        side = side_to_move(start_turn, index)
        if side != audited_side:
            continue
        audits.append(
            audit_decision(
                history[:index],
                str(action),
                start_turn,
                search_time,
                depth,
            )
        )

    suspect_pool = [
        item
        for item in audits
        if item.regret >= min_regret and item.actual != item.alpha_beta
    ]
    suspects = sorted(
        suspect_pool,
        key=lambda item: (
            item.regret,
            "allowed-opponent-goal-threat" in item.reasons,
            "low-impact-wall" in item.reasons,
        ),
        reverse=True,
    )[:max_suspects]
    return GameAudit(
        game_id=int(record.get("game_id", 0)),
        audited_engine=engine_name,
        audited_side=audited_side,
        winner=record.get("winner"),
        winner_engine=record.get("winner_engine"),
        plies=int(record.get("plies", len(history))),
        audited_decisions=len(audits),
        top_suspects=suspects,
    )


def render_markdown(summary: dict[str, Any], audits: list[GameAudit]) -> str:
    lines = [
        "# Barricade Loss Decision Audit",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Source: `{summary['source']}`",
        f"- Audited engine: `{summary['engine_name']}`",
        f"- Lost games audited: {summary['lost_games_audited']}",
        f"- Search reference: alpha-beta depth {summary['depth']} / {summary['search_time']} sec",
        "",
        "## Top Suspects",
        "",
    ]
    top = summary["global_top_suspects"]
    if not top:
        lines.append("- No suspect decisions found.")
    for item in top:
        lines.extend(
            [
                (
                    f"- Game {item['game_id']} ply {item['ply']} ({item['side']}, {item['phase']}): "
                    f"actual `{item['actual']}` vs alpha-beta `{item['alpha_beta']}`, "
                    f"regret {item['regret']}"
                ),
                f"  reasons: {', '.join(item['reasons'])}",
            ]
        )

    lines.extend(["", "## Games", ""])
    for audit in audits:
        lines.extend(
            [
                f"### Game {audit.game_id}",
                "",
                f"- Audited side: {audit.audited_side}",
                f"- Winner: {audit.winner or '-'} ({audit.winner_engine or '-'})",
                f"- Plies: {audit.plies}",
                f"- Audited decisions: {audit.audited_decisions}",
                "",
            ]
        )
        for suspect in audit.top_suspects:
            lines.extend(
                [
                    (
                        f"- Ply {suspect.ply}: `{suspect.actual}` vs `{suspect.alpha_beta}` "
                        f"(regret {suspect.regret}, phase {suspect.phase})"
                    ),
                    (
                        f"  deltas actual my/opp {suspect.actual_my_delta}/{suspect.actual_opp_delta}; "
                        f"alpha-beta my/opp {suspect.alpha_beta_my_delta}/{suspect.alpha_beta_opp_delta}"
                    ),
                    f"  reasons: {', '.join(suspect.reasons)}",
                    f"  history before: `{' '.join(suspect.history_before)}`",
                    "",
                ]
            )
    return "\n".join(lines)


def write_outputs(out_dir: Path, summary: dict[str, Any], audits: list[GameAudit]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "games": [
            {
                **asdict(audit),
                "top_suspects": [asdict(item) for item in audit.top_suspects],
            }
            for audit in audits
        ],
    }
    (out_dir / "loss_audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "loss_audit.md").write_text(render_markdown(summary, audits), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit lost Barricade backtest games.")
    parser.add_argument("source", type=Path, help="Backtest run directory or games.jsonl path.")
    parser.add_argument("--engine-name", default="candidate")
    parser.add_argument("--time", type=float, default=0.05)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--max-games", type=int)
    parser.add_argument("--max-suspects", type=int, default=5)
    parser.add_argument("--min-regret", type=float, default=1.0)
    parser.add_argument("--out-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    games_path = games_path_from_input(args.source)
    if not games_path.is_file():
        raise SystemExit(f"games.jsonl not found: {games_path}")

    records = read_jsonl(games_path)
    audits: list[GameAudit] = []
    for record in records:
        audit = audit_game(
            record,
            args.engine_name,
            args.time,
            args.depth,
            args.max_suspects,
            args.min_regret,
        )
        if audit:
            audits.append(audit)
            if args.max_games and len(audits) >= args.max_games:
                break

    all_suspects: list[dict[str, Any]] = []
    for audit in audits:
        for suspect in audit.top_suspects:
            all_suspects.append({"game_id": audit.game_id, **asdict(suspect)})
    global_top = sorted(all_suspects, key=lambda item: item["regret"], reverse=True)[:10]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(games_path),
        "engine_name": args.engine_name,
        "search_time": args.time,
        "depth": args.depth,
        "min_regret": args.min_regret,
        "lost_games_audited": len(audits),
        "global_top_suspects": global_top,
    }
    out_dir = args.out_dir or games_path.parent
    write_outputs(out_dir, summary, audits)
    print(f"audited_lost_games={len(audits)} wrote={out_dir}")
    if global_top:
        top = global_top[0]
        print(
            f"top_suspect=game {top['game_id']} ply {top['ply']} "
            f"{top['actual']} vs {top['alpha_beta']} regret={top['regret']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
