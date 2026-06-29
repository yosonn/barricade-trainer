from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import barricade_trainer as engine
import barricade_web as web

ACTION_RE = re.compile(r"\b(?:[a-i][1-9]|[hv][a-h][1-8])\b", re.IGNORECASE)
MOVE_FIELD_RE = re.compile(r'"moves"\s*:\s*"([^"]*)"', re.IGNORECASE)


@dataclass(frozen=True)
class SyncCandidate:
    history: list[str]
    start_turn: str
    source: str
    valid: bool
    error: str = ""


@dataclass(frozen=True)
class LiveRecommendation:
    history: list[str]
    start_turn: str
    turn: str
    action: str | None
    engine: str
    resolved_engine: str
    score: float | None
    red: str
    blue: str
    red_dist: int
    blue_dist: int
    winner: str | None


def normalize_action(token: str) -> str:
    return token.strip().lower()


def tokenize_actions(text: str) -> list[str]:
    return [normalize_action(match.group(0)) for match in ACTION_RE.finditer(text)]


def split_moves_field(value: str) -> list[str]:
    return [normalize_action(part) for part in re.split(r"[\s,;/]+", value) if ACTION_RE.fullmatch(part.strip())]


def json_move_histories(value: Any) -> Iterable[list[str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"moves", "history", "movehistory"}:
                if isinstance(child, str):
                    moves = split_moves_field(child)
                    if moves:
                        yield moves
                elif isinstance(child, list):
                    moves = [normalize_action(str(item)) for item in child if ACTION_RE.fullmatch(str(item).strip())]
                    if moves:
                        yield moves
            yield from json_move_histories(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_move_histories(child)


def candidate_histories_from_text(text: str) -> list[tuple[str, list[str]]]:
    candidates: list[tuple[str, list[str]]] = []
    for match in MOVE_FIELD_RE.finditer(text):
        moves = split_moves_field(match.group(1))
        if moves:
            candidates.append(("moves-field", moves))

    for json_like in re.findall(r"[\[{].{0,4000}[\]}]", text, flags=re.DOTALL):
        try:
            parsed = json.loads(json_like)
        except Exception:
            continue
        for moves in json_move_histories(parsed):
            candidates.append(("json", moves))

    plain = tokenize_actions(text)
    if plain:
        candidates.append(("plain-text", plain))
    return candidates


def validate_history(history: list[str], start_turn: str) -> SyncCandidate:
    try:
        engine.state_from_history(" ".join(history), start_turn=start_turn)
        return SyncCandidate(history=history, start_turn=start_turn, source="validated", valid=True)
    except Exception as exc:
        return SyncCandidate(history=history, start_turn=start_turn, source="validated", valid=False, error=str(exc))


def longest_legal_subsequence(tokens: list[str], start_turn: str) -> list[str]:
    state = engine.State(turn=start_turn)
    legal: list[str] = []
    for token in tokens:
        try:
            state = engine.apply_action(state, token)
        except Exception:
            continue
        legal.append(token)
    return legal


def choose_best_history(text: str, start_turn: str = "auto") -> SyncCandidate:
    starts = ["red", "blue"] if start_turn == "auto" else [start_turn]
    best: SyncCandidate | None = None
    for source, raw_history in candidate_histories_from_text(text):
        for start in starts:
            candidate = validate_history(raw_history, start)
            candidate = SyncCandidate(candidate.history, candidate.start_turn, source, candidate.valid, candidate.error)
            if not candidate.valid:
                repaired = longest_legal_subsequence(raw_history, start)
                if repaired:
                    repaired_candidate = validate_history(repaired, start)
                    candidate = SyncCandidate(
                        repaired_candidate.history,
                        repaired_candidate.start_turn,
                        f"{source}-legal-subsequence",
                        repaired_candidate.valid,
                        repaired_candidate.error,
                    )
            if candidate.valid and (best is None or len(candidate.history) > len(best.history)):
                best = candidate
    if best is not None:
        return best
    return SyncCandidate([], "red" if start_turn == "auto" else start_turn, "none", False, "No legal move history found")


def recommend_from_history(
    history: list[str],
    start_turn: str,
    engine_kind: str,
    search_time: float,
    depth: int,
) -> LiveRecommendation:
    state = engine.state_from_history(" ".join(history), start_turn=start_turn)
    payload = web.state_payload(
        state,
        user_side=state.turn,
        search_time=search_time,
        depth=depth,
        engine_kind=engine_kind,
        recommend_for_turn=True,
        start_turn=start_turn,
        avoid_actions=web.root_avoid_actions(" ".join(history), start_turn),
        mcts_seed=len(history),
        history_tokens=history,
    )
    return LiveRecommendation(
        history=history,
        start_turn=start_turn,
        turn=payload["turn"],
        action=payload["recommendation"],
        engine=payload["engine"],
        resolved_engine=payload["resolved_engine"],
        score=payload["score"],
        red=payload["red"]["pos"],
        blue=payload["blue"]["pos"],
        red_dist=payload["red"]["dist"],
        blue_dist=payload["blue"]["dist"],
        winner=payload["winner"],
    )


def recommendation_to_json(recommendation: LiveRecommendation) -> str:
    return json.dumps(asdict(recommendation), ensure_ascii=False, indent=2)
