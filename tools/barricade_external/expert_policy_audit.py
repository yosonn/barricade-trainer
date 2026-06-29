#!/usr/bin/env python3
"""Compare Barricade.gg Expert policy with local engines on a supplied history."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import barricade_trainer as engine
import barricade_web as web
from barricade_expert import BarricadeGgAiClient


@dataclass(frozen=True)
class PolicyRow:
    ply: int
    side: str
    actual: str
    expert: str | None
    local: str
    local_engine: str
    actual_matches_expert: bool | None
    local_matches_expert: bool | None
    red_dist: int
    blue_dist: int
    expert_error: str = ""


def local_move(state: engine.State, history: list[str], engine_kind: str, time_limit: float, depth: int) -> tuple[str, str]:
    action, _, _, resolved = web.recommend_action(
        state,
        search_time=time_limit,
        depth=depth,
        engine_kind=engine_kind,
        avoid_actions=web.root_avoid_actions(" ".join(history), "red"),
        seed=len(history),
        history_tokens=history,
        start_turn="red",
    )
    return action, resolved


def audit_history(args: argparse.Namespace) -> list[PolicyRow]:
    tokens = engine.tokenize_history(args.history)
    client = BarricadeGgAiClient(args.difficulty, timeout=args.timeout, pause_sec=args.pause_sec)
    state = engine.State()
    rows: list[PolicyRow] = []
    for index, actual in enumerate(tokens, 1):
        history = tokens[: index - 1]
        side = state.turn
        if args.side != "both" and side != args.side:
            state = engine.apply_action(state, actual)
            continue

        expert_action: str | None = None
        expert_error = ""
        if not args.no_expert:
            try:
                expert_action = client.get_move(history)
            except Exception as exc:
                expert_error = str(exc)

        local_action, resolved = local_move(state, history, args.local_engine, args.time, args.depth)
        red_dist, _ = engine.movement_path(state, "red")
        blue_dist, _ = engine.movement_path(state, "blue")
        rows.append(
            PolicyRow(
                ply=index,
                side=side,
                actual=actual,
                expert=expert_action,
                local=local_action,
                local_engine=resolved,
                actual_matches_expert=None if expert_action is None else actual == expert_action,
                local_matches_expert=None if expert_action is None else local_action == expert_action,
                red_dist=red_dist,
                blue_dist=blue_dist,
                expert_error=expert_error,
            )
        )
        state = engine.apply_action(state, actual)
    return rows


def write_outputs(rows: list[PolicyRow], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rows": [asdict(row) for row in rows],
    }
    (out_dir / "expert_policy_audit.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Expert Policy Audit", ""]
    for row in rows:
        marker = "same" if row.local_matches_expert else "diff"
        lines.append(
            f"- Ply {row.ply} {row.side}: actual `{row.actual}`, expert `{row.expert or '-'}`, "
            f"local `{row.local}` ({row.local_engine}), {marker}, dist R/B {row.red_dist}/{row.blue_dist}"
        )
        if row.expert_error:
            lines.append(f"  Expert error: {row.expert_error}")
    (out_dir / "expert_policy_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit local moves against Barricade.gg Expert decisions.")
    parser.add_argument("--history", required=True)
    parser.add_argument("--side", choices=("red", "blue", "both"), default="both")
    parser.add_argument("--difficulty", choices=("easy", "medium", "hard", "expert"), default="expert")
    parser.add_argument("--local-engine", choices=("hybrid", "mcts", "alpha-beta"), default="hybrid")
    parser.add_argument("--time", type=float, default=0.2)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--pause-sec", type=float, default=0.0)
    parser.add_argument("--no-expert", action="store_true", help="Skip live Expert API calls and only compute local moves.")
    parser.add_argument("--out-dir", type=Path, default=Path("backtest_runs") / "expert-policy-audit-latest")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    rows = audit_history(args)
    write_outputs(rows, args.out_dir)
    compared = [row for row in rows if row.expert is not None]
    local_matches = sum(1 for row in compared if row.local_matches_expert)
    actual_matches = sum(1 for row in compared if row.actual_matches_expert)
    print(f"rows={len(rows)} compared={len(compared)}")
    if compared:
        print(f"actual_matches_expert={actual_matches}/{len(compared)}")
        print(f"local_matches_expert={local_matches}/{len(compared)}")
    print(f"wrote {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
