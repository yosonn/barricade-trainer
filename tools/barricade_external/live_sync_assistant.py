#!/usr/bin/env python3
"""Synchronize an observed Barricade.gg position and ask a local model for a move.

This is the safe core for live practice: it reconstructs a legal move history
from pasted text/network snippets, then recommends a move. Browser automation
can feed page observations into this script without changing the engine logic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.barricade_external.live_sync_core import (
    choose_best_history,
    recommend_from_history,
    recommendation_to_json,
    split_moves_field,
)


def read_observation(args: argparse.Namespace) -> str:
    chunks: list[str] = []
    if args.history:
        chunks.append("moves:" + ",".join(split_moves_field(args.history)))
    if args.text:
        chunks.append(args.text)
    if args.text_file:
        chunks.append(args.text_file.read_text(encoding="utf-8", errors="replace"))
    if not chunks and not sys.stdin.isatty():
        chunks.append(sys.stdin.read())
    return "\n".join(chunks)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recommend a Barricade move from observed live-game text.")
    parser.add_argument("--history", help="Known move history, e.g. 'e2 e8 hd5'.")
    parser.add_argument("--text", help="Raw page/network text to scan for moves.")
    parser.add_argument("--text-file", type=Path, help="File containing raw page/network text to scan.")
    parser.add_argument("--start-turn", choices=("auto", "red", "blue"), default="auto")
    parser.add_argument("--engine", choices=("hybrid", "mcts", "alpha-beta", "expert"), default="expert")
    parser.add_argument("--time", type=float, default=0.25)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    observation = read_observation(args)
    candidate = choose_best_history(observation, args.start_turn)
    if not candidate.valid:
        print(f"Could not reconstruct a legal history: {candidate.error}", file=sys.stderr)
        return 2
    try:
        recommendation = recommend_from_history(
            candidate.history,
            candidate.start_turn,
            args.engine,
            args.time,
            args.depth,
        )
    except Exception as exc:
        print(f"Could not recommend a move: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(recommendation_to_json(recommendation))
        return 0

    print(f"source={candidate.source}")
    print(f"start_turn={recommendation.start_turn} turn={recommendation.turn}")
    print(f"history={' '.join(recommendation.history)}")
    print(
        f"red={recommendation.red} d={recommendation.red_dist} "
        f"blue={recommendation.blue} d={recommendation.blue_dist}"
    )
    print(f"engine={recommendation.engine} resolved={recommendation.resolved_engine} score={recommendation.score}")
    print(f"recommendation={recommendation.action or '-'}")
    if recommendation.winner:
        print(f"winner={recommendation.winner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
