#!/usr/bin/env python3
"""API-level and local-engine self-play backtesting for Barricade Trainer."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import barricade_trainer as engine
import barricade_mcts
import barricade_web as web


DEFAULT_BASE_URL = "https://barricade-trainer.onrender.com"


@dataclass(frozen=True)
class EngineConfig:
    name: str
    depth: int
    time_limit: float
    kind: str = "alpha-beta"
    simulations: int = 200
    max_actions: int = 16
    rollout_depth: int = 2
    mcts_exploration: float = 1.35


@dataclass
class GameRecord:
    game_id: int
    seed: int
    red_engine: str
    blue_engine: str
    winner: str | None
    winner_engine: str | None
    plies: int
    history: list[str]
    terminal_reason: str
    errors: list[str]
    final_state: dict[str, Any] | None
    duration_sec: float


class BarricadeApiClient:
    def __init__(self, base_url: str, retries: int = 2, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.timeout = timeout

    def analyze(
        self,
        history: list[str],
        side_to_optimize: str,
        start_turn: str,
        config: EngineConfig,
    ) -> dict[str, Any]:
        payload = {
            "history": " ".join(history),
            "user_side": side_to_optimize,
            "start_turn": start_turn,
            "recommend_for_turn": True,
            "time": config.time_limit,
            "depth": config.depth,
            "engine": config.kind,
        }
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/analyze",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "barricade-backtest/0.1"},
            method="POST",
        )

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.6 * (attempt + 1))
        raise RuntimeError(f"API request failed after {self.retries + 1} attempts: {last_error}")


class LocalEngineClient:
    def analyze(
        self,
        history: list[str],
        side_to_optimize: str,
        start_turn: str,
        config: EngineConfig,
    ) -> dict[str, Any]:
        joined_history = " ".join(history)
        state = engine.state_from_history(joined_history, start_turn=start_turn)
        avoid_actions = web.root_avoid_actions(joined_history, start_turn)
        recommendation = None
        score = None
        searched_depth = None
        if state.turn == side_to_optimize:
            if config.kind == "mcts":
                recommendation, score, searched_depth = barricade_mcts.search_mcts(
                    state,
                    time_limit=config.time_limit,
                    simulations=config.simulations,
                    max_actions=config.max_actions,
                    exploration=config.mcts_exploration,
                    rollout_depth=config.rollout_depth,
                    avoid_actions=avoid_actions,
                    seed=len(history),
                )
            elif config.kind == "hybrid":
                recommendation, score, searched_depth, _ = web.recommend_action(
                    state,
                    config.time_limit,
                    config.depth,
                    "hybrid",
                    avoid_actions,
                    seed=len(history),
                )
            else:
                recommendation, score, searched_depth = engine.search_best(
                    state,
                    time_limit=config.time_limit,
                    max_depth=config.depth,
                    avoid_actions=avoid_actions,
                )
        payload = web.state_payload(
            state,
            user_side=side_to_optimize,
            search_time=config.time_limit,
            depth=config.depth,
            engine_kind=config.kind,
            recommend_for_turn=False,
            start_turn=start_turn,
            avoid_actions=avoid_actions,
        )
        payload["recommendation"] = recommendation
        payload["score"] = score
        payload["searched_depth"] = searched_depth
        return {
            "ok": True,
            "state": payload,
        }


def other(side: str) -> str:
    return "blue" if side == "red" else "red"


def side_to_move(start_turn: str, plies: int) -> str:
    return start_turn if plies % 2 == 0 else other(start_turn)


def choose_action(state: dict[str, Any], rng: random.Random, exploration: float) -> str | None:
    recommendation = state.get("recommendation")
    legal_actions = state.get("legal_actions") or []
    if legal_actions and exploration > 0 and rng.random() < exploration:
        return rng.choice(legal_actions)
    return recommendation


def play_game(
    game_id: int,
    seed: int,
    client: BarricadeApiClient,
    red_engine: EngineConfig,
    blue_engine: EngineConfig,
    start_turn: str,
    max_plies: int,
    exploration: float,
    pause_sec: float,
) -> GameRecord:
    started_at = time.perf_counter()
    rng = random.Random(seed)
    history: list[str] = []
    errors: list[str] = []
    seen_histories: set[tuple[str, ...]] = set()
    final_state: dict[str, Any] | None = None
    terminal_reason = "max_plies"

    for _ in range(max_plies):
        turn = side_to_move(start_turn, len(history))
        engine = red_engine if turn == "red" else blue_engine
        try:
            payload = client.analyze(history, turn, start_turn, engine)
        except RuntimeError as exc:
            errors.append(str(exc))
            terminal_reason = "api_error"
            break

        if not payload.get("ok"):
            errors.append(str(payload.get("error", "unknown API error")))
            terminal_reason = "invalid_history"
            break

        state = payload.get("state") or {}
        final_state = state
        winner = state.get("winner")
        if winner:
            terminal_reason = "winner"
            break

        action = choose_action(state, rng, exploration)
        if not action:
            errors.append("missing recommendation")
            terminal_reason = "missing_recommendation"
            break

        legal_actions = state.get("legal_actions") or []
        if legal_actions and action not in legal_actions:
            errors.append(f"illegal recommendation {action!r} for {turn}")
            terminal_reason = "illegal_recommendation"
            break

        history.append(action)
        key = tuple(history)
        if key in seen_histories:
            terminal_reason = "repeated_history"
            break
        seen_histories.add(key)

        if pause_sec:
            time.sleep(pause_sec)

    winner = final_state.get("winner") if final_state else None
    winner_engine = None
    if winner == "red":
        winner_engine = red_engine.name
    elif winner == "blue":
        winner_engine = blue_engine.name

    return GameRecord(
        game_id=game_id,
        seed=seed,
        red_engine=red_engine.name,
        blue_engine=blue_engine.name,
        winner=winner,
        winner_engine=winner_engine,
        plies=len(history),
        history=history,
        terminal_reason=terminal_reason,
        errors=errors,
        final_state=final_state,
        duration_sec=round(time.perf_counter() - started_at, 3),
    )


def summarize(
    records: list[GameRecord],
    baseline: EngineConfig,
    candidate: EngineConfig,
    mode: str,
    base_url: str,
) -> dict[str, Any]:
    wins = {baseline.name: 0, candidate.name: 0, "draw_or_none": 0}
    terminal_reasons: dict[str, int] = {}
    side_wins = {"red": 0, "blue": 0, "none": 0}
    engine_side_results: dict[str, dict[str, int]] = {
        f"{baseline.name}_as_red": {"wins": 0, "games": 0},
        f"{baseline.name}_as_blue": {"wins": 0, "games": 0},
        f"{candidate.name}_as_red": {"wins": 0, "games": 0},
        f"{candidate.name}_as_blue": {"wins": 0, "games": 0},
    }

    for record in records:
        terminal_reasons[record.terminal_reason] = terminal_reasons.get(record.terminal_reason, 0) + 1
        side_wins[record.winner or "none"] = side_wins.get(record.winner or "none", 0) + 1
        red_key = f"{record.red_engine}_as_red"
        blue_key = f"{record.blue_engine}_as_blue"
        engine_side_results.setdefault(red_key, {"wins": 0, "games": 0})["games"] += 1
        engine_side_results.setdefault(blue_key, {"wins": 0, "games": 0})["games"] += 1
        if record.winner == "red":
            engine_side_results[red_key]["wins"] += 1
        elif record.winner == "blue":
            engine_side_results[blue_key]["wins"] += 1
        if record.winner_engine in (baseline.name, candidate.name):
            wins[record.winner_engine] += 1
        else:
            wins["draw_or_none"] += 1

    plies = [record.plies for record in records]
    error_games = sum(1 for record in records if record.errors)
    total = len(records) or 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "games": len(records),
        "mode": mode,
        "base_url": base_url if mode == "api" else None,
        "baseline": asdict(baseline),
        "candidate": asdict(candidate),
        "wins": wins,
        "candidate_win_rate": round(wins[candidate.name] / total * 100, 2),
        "baseline_win_rate": round(wins[baseline.name] / total * 100, 2),
        "draw_or_none_rate": round(wins["draw_or_none"] / total * 100, 2),
        "side_wins": side_wins,
        "engine_side_results": engine_side_results,
        "terminal_reasons": terminal_reasons,
        "error_games": error_games,
        "avg_plies": round(statistics.mean(plies), 2) if plies else 0,
        "median_plies": round(statistics.median(plies), 2) if plies else 0,
        "total_duration_sec": round(sum(record.duration_sec for record in records), 3),
    }


def write_outputs(out_dir: Path, records: list[GameRecord], summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    games_path = out_dir / "games.jsonl"
    with games_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "summary.md").write_text(render_markdown(summary, records), encoding="utf-8")


def render_markdown(summary: dict[str, Any], records: list[GameRecord]) -> str:
    notable = sorted(records, key=lambda record: (bool(record.errors), record.plies), reverse=True)[:5]
    lines = [
        "# Barricade Backtest Summary",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Games: {summary['games']}",
        f"- Mode: {summary['mode']}",
        f"- Candidate win rate: {summary['candidate_win_rate']}%",
        f"- Baseline win rate: {summary['baseline_win_rate']}%",
        f"- Draw / no result rate: {summary['draw_or_none_rate']}%",
        f"- Error games: {summary['error_games']}",
        f"- Average plies: {summary['avg_plies']}",
        "",
        "## Engines",
        "",
        (
            f"- Baseline: kind={summary['baseline']['kind']}, depth={summary['baseline']['depth']}, "
            f"time={summary['baseline']['time_limit']}, simulations={summary['baseline']['simulations']}, "
            f"max_actions={summary['baseline']['max_actions']}, rollout_depth={summary['baseline']['rollout_depth']}"
        ),
        (
            f"- Candidate: kind={summary['candidate']['kind']}, depth={summary['candidate']['depth']}, "
            f"time={summary['candidate']['time_limit']}, simulations={summary['candidate']['simulations']}, "
            f"max_actions={summary['candidate']['max_actions']}, rollout_depth={summary['candidate']['rollout_depth']}"
        ),
        "",
        "## Source",
        "",
    ]
    if summary["mode"] == "api":
        lines.append(f"- Base URL: {summary['base_url']}")
    else:
        lines.append(f"- Workspace root: {ROOT}")
    lines.extend([
        "",
        "## Terminal Reasons",
        "",
    ])
    for reason, count in sorted(summary["terminal_reasons"].items()):
        lines.append(f"- {reason}: {count}")

    lines.extend(["", "## Side Wins", ""])
    for side, count in sorted(summary["side_wins"].items()):
        lines.append(f"- {side}: {count}")

    lines.extend(["", "## Engine Side Results", ""])
    for key, result in sorted(summary["engine_side_results"].items()):
        games = result["games"] or 1
        rate = round(result["wins"] / games * 100, 2)
        lines.append(f"- {key}: {result['wins']}/{result['games']} ({rate}%)")

    lines.extend(["", "## Notable Games", ""])
    for record in notable:
        errors = "; ".join(record.errors) if record.errors else "-"
        final_score = "-"
        if record.final_state:
            score = record.final_state.get("score")
            searched_depth = record.final_state.get("searched_depth")
            final_score = f"score={score}, searched_depth={searched_depth}"
        lines.extend(
            [
                f"### Game {record.game_id}",
                "",
                f"- Red: {record.red_engine}",
                f"- Blue: {record.blue_engine}",
                f"- Winner: {record.winner or '-'} ({record.winner_engine or '-'})",
                f"- Plies: {record.plies}",
                f"- Terminal reason: {record.terminal_reason}",
                f"- Errors: {errors}",
                f"- Final state: {final_score}",
                f"- Replay: `{' '.join(record.history)}`",
                "",
            ]
        )

    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Barricade API self-play backtests.")
    parser.add_argument(
        "--mode",
        choices=("api", "local"),
        default="api",
        help="Use the deployed API or run decisions directly against the local Python engine.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--max-plies", type=int, default=220)
    parser.add_argument("--seed", type=int, default=20260603)
    parser.add_argument("--time", type=float, default=0.05, help="Default time limit for both engines.")
    parser.add_argument("--baseline-time", type=float)
    parser.add_argument("--candidate-time", type=float)
    parser.add_argument("--baseline-depth", type=int, default=2)
    parser.add_argument("--candidate-depth", type=int, default=3)
    parser.add_argument("--baseline-engine", choices=("alpha-beta", "mcts", "hybrid"), default="alpha-beta")
    parser.add_argument("--candidate-engine", choices=("alpha-beta", "mcts", "hybrid"), default="alpha-beta")
    parser.add_argument("--baseline-simulations", type=int, default=200)
    parser.add_argument("--candidate-simulations", type=int, default=200)
    parser.add_argument("--baseline-max-actions", type=int, default=16)
    parser.add_argument("--candidate-max-actions", type=int, default=16)
    parser.add_argument("--baseline-rollout-depth", type=int, default=2)
    parser.add_argument("--candidate-rollout-depth", type=int, default=2)
    parser.add_argument("--baseline-mcts-exploration", type=float, default=1.35)
    parser.add_argument("--candidate-mcts-exploration", type=float, default=1.35)
    parser.add_argument("--exploration", type=float, default=0.0, help="Chance to choose a random legal move.")
    parser.add_argument("--pause-sec", type=float, default=0.0, help="Pause between plies to reduce server load.")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--fail-on-errors", action="store_true")
    parser.add_argument("--fail-under-candidate-rate", type=float)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.games < 1:
        raise SystemExit("--games must be at least 1")
    if not 0 <= args.exploration <= 1:
        raise SystemExit("--exploration must be between 0 and 1")

    baseline = EngineConfig(
        name="baseline",
        depth=args.baseline_depth,
        time_limit=args.baseline_time if args.baseline_time is not None else args.time,
        kind=args.baseline_engine,
        simulations=args.baseline_simulations,
        max_actions=args.baseline_max_actions,
        rollout_depth=args.baseline_rollout_depth,
        mcts_exploration=args.baseline_mcts_exploration,
    )
    candidate = EngineConfig(
        name="candidate",
        depth=args.candidate_depth,
        time_limit=args.candidate_time if args.candidate_time is not None else args.time,
        kind=args.candidate_engine,
        simulations=args.candidate_simulations,
        max_actions=args.candidate_max_actions,
        rollout_depth=args.candidate_rollout_depth,
        mcts_exploration=args.candidate_mcts_exploration,
    )
    client: BarricadeApiClient | LocalEngineClient
    if args.mode == "local":
        client = LocalEngineClient()
    else:
        client = BarricadeApiClient(args.base_url, retries=args.retries, timeout=args.timeout)
    records: list[GameRecord] = []

    for index in range(args.games):
        seed = args.seed + index
        candidate_is_red = index % 2 == 0
        red_engine = candidate if candidate_is_red else baseline
        blue_engine = baseline if candidate_is_red else candidate
        record = play_game(
            game_id=index + 1,
            seed=seed,
            client=client,
            red_engine=red_engine,
            blue_engine=blue_engine,
            start_turn="red",
            max_plies=args.max_plies,
            exploration=args.exploration,
            pause_sec=args.pause_sec,
        )
        records.append(record)
        print(
            f"game={record.game_id} winner={record.winner or '-'} "
            f"engine={record.winner_engine or '-'} plies={record.plies} reason={record.terminal_reason}",
            flush=True,
        )

    summary = summarize(records, baseline, candidate, args.mode, args.base_url)
    out_dir = args.out_dir or Path("backtest_runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    write_outputs(out_dir, records, summary)
    print(f"wrote {out_dir}")
    print(
        f"candidate={summary['candidate_win_rate']}% "
        f"baseline={summary['baseline_win_rate']}% errors={summary['error_games']}"
    )
    if args.fail_on_errors and summary["error_games"]:
        print("failed: error games were detected", file=sys.stderr)
        return 2
    if (
        args.fail_under_candidate_rate is not None
        and summary["candidate_win_rate"] < args.fail_under_candidate_rate
    ):
        print(
            f"failed: candidate win rate {summary['candidate_win_rate']}% is below "
            f"{args.fail_under_candidate_rate}%",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
