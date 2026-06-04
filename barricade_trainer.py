from __future__ import annotations

import argparse
import math
import re
import time
from collections import deque
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Iterable


BOARD = 9
FILES = "abcdefghi"
PLAYERS = ("red", "blue")
START = {"red": (4, 0), "blue": (4, 8)}
GOAL_ROW = {"red": 8, "blue": 0}
FORWARD = {"red": 1, "blue": -1}
ROOT_ACTION_LIMIT = 24
SEARCH_ACTION_LIMIT = 18
QUIESCENCE_ACTION_LIMIT = 10
QUIESCENCE_EXTENSION_LIMIT = 1

Coord = tuple[int, int]
Wall = tuple[str, int, int]


def opponent(player: str) -> str:
    return "blue" if player == "red" else "red"


def coord_to_text(pos: Coord) -> str:
    return f"{FILES[pos[0]]}{pos[1] + 1}"


def text_to_coord(text: str) -> Coord:
    if not re.fullmatch(r"[a-i][1-9]", text, flags=re.I):
        raise ValueError(f"Bad square: {text}")
    return FILES.index(text[0].lower()), int(text[1]) - 1


def wall_to_text(wall: Wall) -> str:
    orient, x, y = wall
    return f"{orient}{FILES[x]}{y + 1}"


def text_to_wall(text: str) -> Wall:
    text = text.lower()
    if re.fullmatch(r"[hv][a-h][1-8]", text):
        orient, square = text[0], text[1:]
    elif re.fullmatch(r"[a-h][1-8][hv]", text):
        orient, square = text[-1], text[:-1]
    else:
        raise ValueError(f"Bad wall: {text}")
    x, y = text_to_coord(square)
    if x >= BOARD - 1 or y >= BOARD - 1:
        raise ValueError(f"Wall anchor must be a1-h8: {text}")
    return orient, x, y


def blocked_edges_for(wall: Wall) -> frozenset[tuple[Coord, Coord]]:
    orient, x, y = wall
    if orient == "h":
        edges = [((x, y), (x, y + 1)), ((x + 1, y), (x + 1, y + 1))]
    else:
        edges = [((x, y), (x + 1, y)), ((x, y + 1), (x + 1, y + 1))]
    return frozenset(tuple(sorted(edge)) for edge in edges)


@lru_cache(maxsize=200_000)
def blocked_edges_for_walls(walls_key: tuple[Wall, ...]) -> frozenset[tuple[Coord, Coord]]:
    edges: set[tuple[Coord, Coord]] = set()
    for wall in walls_key:
        edges.update(blocked_edges_for(wall))
    return frozenset(edges)


@dataclass(frozen=True)
class State:
    red: Coord = START["red"]
    blue: Coord = START["blue"]
    turn: str = "red"
    red_walls: int = 10
    blue_walls: int = 10
    walls: frozenset[Wall] = frozenset()

    @property
    def blocked(self) -> frozenset[tuple[Coord, Coord]]:
        return blocked_edges_for_walls(tuple(sorted(self.walls)))

    def pawn(self, player: str) -> Coord:
        return self.red if player == "red" else self.blue

    def walls_left(self, player: str) -> int:
        return self.red_walls if player == "red" else self.blue_walls

    def key(self) -> tuple:
        return (self.red, self.blue, self.turn, self.red_walls, self.blue_walls, tuple(sorted(self.walls)))


def state_from_key(key: tuple) -> State:
    return State(key[0], key[1], key[2], key[3], key[4], frozenset(key[5]))


def in_bounds(pos: Coord) -> bool:
    x, y = pos
    return 0 <= x < BOARD and 0 <= y < BOARD


def is_blocked(state: State, a: Coord, b: Coord) -> bool:
    return tuple(sorted((a, b))) in state.blocked


def basic_neighbors(state: State, pos: Coord) -> list[Coord]:
    out = []
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        nxt = (pos[0] + dx, pos[1] + dy)
        if in_bounds(nxt) and not is_blocked(state, pos, nxt):
            out.append(nxt)
    return out


def legal_pawn_moves(state: State, player: str | None = None) -> list[Coord]:
    return list(legal_pawn_moves_cached(state.key(), player or state.turn))


def legal_pawn_moves_from(state: State, player: str, pos: Coord) -> tuple[Coord, ...]:
    enemy = state.pawn(opponent(player))
    moves: set[Coord] = set()
    for nxt in basic_neighbors(state, pos):
        if nxt != enemy:
            moves.add(nxt)
            continue

        dx, dy = nxt[0] - pos[0], nxt[1] - pos[1]
        behind = (nxt[0] + dx, nxt[1] + dy)
        if in_bounds(behind) and not is_blocked(state, nxt, behind):
            moves.add(behind)
        else:
            for sx, sy in ((-dy, dx), (dy, -dx)):
                side = (nxt[0] + sx, nxt[1] + sy)
                if in_bounds(side) and not is_blocked(state, nxt, side):
                    moves.add(side)
    ordered = sorted(moves, key=lambda p: (abs(p[0] - 4), -FORWARD[player] * p[1], p[0], p[1]))
    return tuple(ordered)


@lru_cache(maxsize=200_000)
def legal_pawn_moves_cached(state_key: tuple, player: str) -> tuple[Coord, ...]:
    state = state_from_key(state_key)
    return legal_pawn_moves_from(state, player, state.pawn(player))


def shortest_path(state: State, player: str) -> tuple[int, list[Coord]]:
    dist, path = shortest_path_cached(state.key(), player)
    return dist, list(path)


def movement_path(state: State, player: str) -> tuple[int, list[Coord]]:
    dist, path = movement_path_cached(state.key(), player)
    return dist, list(path)


@lru_cache(maxsize=200_000)
def movement_path_cached(state_key: tuple, player: str) -> tuple[int, tuple[Coord, ...]]:
    state = state_from_key(state_key)
    start = state.pawn(player)
    goal = GOAL_ROW[player]
    q = deque([start])
    parent: dict[Coord, Coord | None] = {start: None}
    while q:
        pos = q.popleft()
        if pos[1] == goal:
            path = []
            cur: Coord | None = pos
            while cur is not None:
                path.append(cur)
                cur = parent[cur]
            path.reverse()
            return len(path) - 1, tuple(path)
        for nxt in legal_pawn_moves_from(state, player, pos):
            if nxt not in parent:
                parent[nxt] = pos
                q.append(nxt)
    return math.inf, tuple()


@lru_cache(maxsize=200_000)
def shortest_path_cached(state_key: tuple, player: str) -> tuple[int, tuple[Coord, ...]]:
    state = state_from_key(state_key)
    start = state.pawn(player)
    goal = GOAL_ROW[player]
    q = deque([start])
    parent: dict[Coord, Coord | None] = {start: None}
    while q:
        pos = q.popleft()
        if pos[1] == goal:
            path = []
            cur: Coord | None = pos
            while cur is not None:
                path.append(cur)
                cur = parent[cur]
            path.reverse()
            return len(path) - 1, tuple(path)
        for nxt in basic_neighbors(state, pos):
            if nxt not in parent:
                parent[nxt] = pos
                q.append(nxt)
    return math.inf, tuple()


def wall_conflicts(existing: Wall, candidate: Wall) -> bool:
    if existing == candidate:
        return True
    if blocked_edges_for(existing) & blocked_edges_for(candidate):
        return True
    return existing[1:] == candidate[1:]


def can_place_wall(state: State, wall: Wall) -> bool:
    if state.walls_left(state.turn) <= 0:
        return False
    if any(wall_conflicts(w, wall) for w in state.walls):
        return False
    trial = replace(state, walls=state.walls | {wall})
    return shortest_path(trial, "red")[0] < math.inf and shortest_path(trial, "blue")[0] < math.inf


def all_wall_slots() -> Iterable[Wall]:
    for orient in ("h", "v"):
        for x in range(BOARD - 1):
            for y in range(BOARD - 1):
                yield orient, x, y


def legal_walls(state: State, focused: bool = True) -> list[Wall]:
    slots: Iterable[Wall] = all_wall_slots()
    if focused:
        candidates: set[Wall] = set()
        for player in PLAYERS:
            _, path = shortest_path(state, player)
            for a, b in zip(path, path[1:]):
                ax, ay = a
                bx, by = b
                if ax == bx:
                    y = min(ay, by)
                    for x in (ax - 1, ax):
                        if 0 <= x < BOARD - 1 and 0 <= y < BOARD - 1:
                            candidates.add(("h", x, y))
                else:
                    x = min(ax, bx)
                    for y in (ay - 1, ay):
                        if 0 <= x < BOARD - 1 and 0 <= y < BOARD - 1:
                            candidates.add(("v", x, y))
        slots = candidates
    return [wall for wall in slots if can_place_wall(state, wall)]


def apply_action(state: State, action: str) -> State:
    action = action.lower()
    next_turn = opponent(state.turn)
    if re.fullmatch(r"[a-i][1-9]", action):
        dest = text_to_coord(action)
        if dest not in legal_pawn_moves(state):
            raise ValueError(f"Illegal pawn move for {state.turn}: {action}")
        kwargs = {state.turn: dest, "turn": next_turn}
        return replace(state, **kwargs)

    wall = text_to_wall(action)
    if not can_place_wall(state, wall):
        raise ValueError(f"Illegal wall for {state.turn}: {action}")
    kwargs = {
        "walls": state.walls | {wall},
        "turn": next_turn,
        f"{state.turn}_walls": state.walls_left(state.turn) - 1,
    }
    return replace(state, **kwargs)


def tokenize_history(history: str) -> list[str]:
    cleaned = re.sub(r"\d+\.", " ", history)
    return re.findall(r"[hv]?[a-i][1-9][hv]?", cleaned, flags=re.I)


def state_from_history(history: str, start_turn: str = "red") -> State:
    if start_turn not in PLAYERS:
        raise ValueError("start_turn must be red or blue")
    state = State(turn=start_turn)
    for token in tokenize_history(history):
        state = apply_action(state, token)
    return state


def is_pawn_action(action: str) -> bool:
    return re.fullmatch(r"[a-i][1-9]", action) is not None


def player_has_goal_move(state: State, player: str) -> bool:
    return any(move[1] == GOAL_ROW[player] for move in legal_pawn_moves(state, player))


def distance_after_pawn_move(state: State, player: str, move: Coord) -> int:
    child = apply_action(replace(state, turn=player), coord_to_text(move))
    return movement_path(child, player)[0]


def path_flexibility(state: State, player: str) -> int:
    dist, _ = movement_path(state, player)
    if dist == math.inf:
        return 0
    useful = 0
    for move in legal_pawn_moves(state, player):
        if distance_after_pawn_move(state, player, move) <= dist:
            useful += 1
    return useful


def path_control_score(state: State, player: str) -> float:
    them = opponent(player)
    _, my_path = movement_path(state, player)
    _, their_path = movement_path(state, them)
    my_window = my_path[1:5]
    their_window = their_path[1:5]
    my_pos = state.pawn(player)
    their_pos = state.pawn(them)
    score = 0.0

    if my_pos in their_window:
        score += 32 - their_window.index(my_pos) * 6
    if their_pos in my_window:
        score -= 32 - my_window.index(their_pos) * 6

    shared = set(my_window) & set(their_window)
    score += len(shared) * 8
    if state.walls_left(player) + state.walls_left(them) <= 2:
        score *= 1.6
    return score


def wall_resource_adjustment(state: State, action: str, perspective: str) -> float:
    if is_pawn_action(action):
        return 0.0
    child = apply_action(state, action)
    opp = opponent(perspective)
    my_dist, _ = movement_path(state, perspective)
    opp_dist, _ = movement_path(state, opp)
    new_my_dist, _ = movement_path(child, perspective)
    new_opp_dist, _ = movement_path(child, opp)
    my_walls = state.walls_left(perspective)
    opp_walls = state.walls_left(opp)
    opp_delay = new_opp_dist - opp_dist
    self_delay = new_my_dist - my_dist
    score = 0.0

    if my_walls <= 2 and my_dist <= opp_dist:
        score -= 180
    if my_walls <= 2 and opp_delay <= 0:
        score -= 260
    if my_walls <= 1 and opp_delay < 2:
        score -= 360
    if opp_walls - my_walls >= 4 and opp_delay <= 1:
        score -= (opp_walls - my_walls) * 45
    if my_dist <= 3 and opp_dist >= my_dist + 3 and opp_delay < 2:
        score -= 220
    if self_delay > 0:
        score -= self_delay * 120
    if opp_delay >= 2:
        score += opp_delay * 160
    return score


def race_conversion_adjustment(state: State, action: str, perspective: str) -> float:
    """Prefer converting a large race lead into progress instead of spending final walls."""
    opp = opponent(perspective)
    my_dist, _ = movement_path(state, perspective)
    opp_dist, _ = movement_path(state, opp)
    if my_dist == math.inf or opp_dist == math.inf:
        return 0.0

    lead = opp_dist - my_dist
    if my_dist > 4 or lead < 6:
        return 0.0

    child = apply_action(state, action)
    new_my_dist, _ = movement_path(child, perspective)
    new_opp_dist, _ = movement_path(child, opp)
    my_walls = state.walls_left(perspective)
    opp_walls = state.walls_left(opp)
    score = 0.0

    if is_pawn_action(action):
        progress = my_dist - new_my_dist
        if progress > 0:
            score += 520 + progress * 180 + max(0, 4 - my_dist) * 80
        else:
            score -= 520 + (new_my_dist - my_dist) * 180
        return score

    opp_delay = new_opp_dist - opp_dist
    self_delay = new_my_dist - my_dist
    score -= 460
    if my_walls <= 2:
        score -= 620
    if opp_walls - my_walls >= 3:
        score -= 220
    if opp_delay < 4:
        score -= 320
    score += min(max(opp_delay, 0), 4) * 90
    if self_delay > 0:
        score -= self_delay * 220
    return score


def should_convert_race_by_sprinting(state: State, perspective: str) -> bool:
    my_dist, _ = movement_path(state, perspective)
    opp_dist, _ = movement_path(state, opponent(perspective))
    return my_dist <= 4 and opp_dist >= my_dist + 6


def opening_book_action(state: State) -> str | None:
    if (
        state.turn == "blue"
        and state.red == text_to_coord("e4")
        and state.blue == text_to_coord("e7")
        and state.red_walls == 10
        and state.blue_walls == 10
        and not state.walls
    ):
        return "hd4"
    return None


def immediate_reply_adjustment(state: State, action: str, perspective: str) -> float:
    if not is_pawn_action(action):
        return 0
    child = apply_action(state, action)
    opp = opponent(perspective)
    score = 0.0

    old_pos = state.pawn(perspective)
    pos = text_to_coord(action)
    enemy = state.pawn(opp)
    if abs(pos[0] - enemy[0]) + abs(pos[1] - enemy[1]) == 1 and old_pos in legal_pawn_moves(child, opp):
        score -= 260

    my_dist, _ = movement_path(state, perspective)
    new_my_dist, _ = movement_path(child, perspective)
    opp_dist, _ = movement_path(state, opp)
    new_opp_dist, _ = movement_path(child, opp)
    if state.walls_left(perspective) + state.walls_left(opp) <= 2:
        if new_my_dist > my_dist and new_opp_dist <= opp_dist:
            score -= 120
        if new_opp_dist > opp_dist and new_my_dist <= my_dist + 1:
            score += 90
    score += (path_control_score(child, perspective) - path_control_score(state, perspective)) * 0.7
    return score


def static_eval(state: State, perspective: str) -> float:
    me = perspective
    them = opponent(me)
    my_dist, _ = movement_path(state, me)
    their_dist, _ = movement_path(state, them)
    if state.pawn(me)[1] == GOAL_ROW[me]:
        return 100000
    if state.pawn(them)[1] == GOAL_ROW[them]:
        return -100000

    my_walls = state.walls_left(me)
    their_walls = state.walls_left(them)
    low_wall_endgame = my_walls + their_walls <= 2
    path_weight = 135 if low_wall_endgame else 100
    if min(my_dist, their_dist) <= 4:
        path_weight += 25
    path_score = (their_dist - my_dist) * path_weight
    progress = (state.pawn(me)[1] * FORWARD[me] - state.pawn(them)[1] * FORWARD[them]) * 2

    # Walls are most valuable before the final sprint, and especially when
    # the opponent is not already far behind.
    race_tension = max(0, 8 - abs(their_dist - my_dist))
    wall_value = 4 + race_tension
    wall_score = (my_walls - their_walls) * wall_value

    reserve_score = 0
    if my_walls == 0 and my_dist >= their_dist:
        reserve_score -= 35
    if their_walls == 0 and their_dist <= my_dist + 2:
        reserve_score += 20
    if my_walls >= 2 and their_dist < my_dist:
        reserve_score += 10
    if my_dist <= 2:
        reserve_score -= my_walls * 2

    tempo_score = 0
    if my_dist <= 1:
        tempo_score += 1200
    if their_dist <= 1:
        tempo_score -= 1400
    elif their_dist <= 2 and my_walls == 0:
        tempo_score -= 260
    if player_has_goal_move(state, me):
        tempo_score += 600
    if player_has_goal_move(state, them):
        tempo_score -= 700

    mobility_score = (len(legal_pawn_moves(state, me)) - len(legal_pawn_moves(state, them))) * 5
    flex_weight = 18 if low_wall_endgame else 9
    flexibility_score = (path_flexibility(state, me) - path_flexibility(state, them)) * flex_weight
    control_score = path_control_score(state, me)

    return path_score + wall_score + reserve_score + progress + tempo_score + mobility_score + flexibility_score + control_score


def action_score(state: State, action: str, perspective: str) -> float:
    child = apply_action(state, action)
    if child.pawn(perspective)[1] == GOAL_ROW[perspective]:
        return 1_000_000
    if child.pawn(opponent(perspective))[1] == GOAL_ROW[opponent(perspective)]:
        return -1_000_000
    if child.turn == opponent(perspective) and player_has_goal_move(child, opponent(perspective)):
        return -75_000
    return static_eval(child, perspective)


def ordered_actions(state: State, limit_walls: int = 18) -> list[str]:
    perspective = state.turn
    scored_actions: list[tuple[float, str]] = []
    my_dist, _ = movement_path(state, state.turn)
    _, my_path = movement_path(state, state.turn)
    opp = opponent(state.turn)
    opp_dist, _ = movement_path(state, opp)

    for pos in legal_pawn_moves(state):
        action = coord_to_text(pos)
        trial = apply_action(state, action)
        new_my = movement_path(trial, state.turn)[0]
        score = action_score(state, action, perspective)
        score += (my_dist - new_my) * 90
        score += immediate_reply_adjustment(state, action, perspective)
        score += race_conversion_adjustment(state, action, perspective)
        if len(my_path) > 1 and pos == my_path[1]:
            score += 80
        if opp_dist <= 1 and pos[1] != GOAL_ROW[perspective]:
            score -= 1800
        scored_actions.append((score, action))

    wall_scores: list[tuple[float, str]] = []
    for wall in legal_walls(state, focused=True):
        action = wall_to_text(wall)
        trial = apply_action(state, action)
        new_my = movement_path(trial, state.turn)[0]
        new_opp = movement_path(trial, opp)[0]
        opp_delay = new_opp - opp_dist
        self_delay = new_my - my_dist
        gain = opp_delay * 150 - self_delay * 120
        gain += static_eval(trial, state.turn) * 0.02
        gain += wall_resource_adjustment(state, action, state.turn)
        gain += race_conversion_adjustment(state, action, state.turn)
        if opp_delay <= 0:
            gain -= 120
        if opp_dist <= 1 and opp_delay > 0:
            gain += 2600 + opp_delay * 450
        elif opp_dist <= 2 and opp_delay > 0:
            gain += 650 + opp_delay * 220
        if new_opp <= 1:
            gain -= 900
        if self_delay >= 2:
            gain -= self_delay * 170
        if state.walls_left(state.turn) <= 2 and opp_delay < 2:
            gain -= 80
        if opp_dist <= my_dist + 1 and opp_delay > 0:
            gain += 45
        if my_dist <= 2 and my_dist < opp_dist:
            gain -= 120
        wall_scores.append((gain, action))
    wall_scores.sort(reverse=True)
    scored_actions.extend(wall_scores[:limit_walls])
    scored_actions.sort(reverse=True)
    return [action for _, action in scored_actions]


def search_best(
    state: State,
    time_limit: float = 1.0,
    max_depth: int = 4,
    avoid_actions: set[str] | None = None,
) -> tuple[str, float, int]:
    deadline = time.perf_counter() + time_limit
    perspective = state.turn
    avoid_actions = avoid_actions or set()
    book_action = opening_book_action(state) if max_depth >= 3 else None
    if book_action and book_action in ordered_actions(state, limit_walls=16):
        return book_action, static_eval(apply_action(state, book_action), perspective), 0

    root_actions = ordered_actions(state, limit_walls=16)[:ROOT_ACTION_LIMIT]
    winning_moves = [
        action for action in root_actions
        if is_pawn_action(action)
        and text_to_coord(action)[1] == GOAL_ROW[perspective]
    ]
    if winning_moves:
        return winning_moves[0], 100000, 0

    my_root_dist, _ = shortest_path(state, perspective)

    def improves_root_path(action: str) -> bool:
        if not is_pawn_action(action):
            return False
        child = apply_action(state, action)
        return movement_path(child, perspective)[0] < my_root_dist

    def tactically_justified_reposition(action: str) -> bool:
        if not is_pawn_action(action):
            return False
        child = apply_action(state, action)
        opp = opponent(perspective)
        opp_dist, _ = movement_path(state, opp)
        new_opp_dist, _ = movement_path(child, opp)
        control_gain = path_control_score(child, perspective) - path_control_score(state, perspective)
        return new_opp_dist > opp_dist or control_gain >= 18

    if avoid_actions:

        non_reversing = [
            action for action in root_actions
            if action not in avoid_actions or improves_root_path(action) or tactically_justified_reposition(action)
        ]
        if non_reversing:
            root_actions = non_reversing

    def harmful_root_wall(action: str) -> bool:
        if is_pawn_action(action):
            return False
        child = apply_action(state, action)
        opp = opponent(perspective)
        my_dist, _ = movement_path(state, perspective)
        opp_dist, _ = movement_path(state, opp)
        new_my = movement_path(child, perspective)[0]
        new_opp = movement_path(child, opp)[0]
        return new_opp <= opp_dist and new_my > my_dist

    non_harmful = [action for action in root_actions if not harmful_root_wall(action)]
    if non_harmful:
        root_actions = non_harmful

    opp = opponent(perspective)
    opp_dist, _ = movement_path(state, opp)
    if should_convert_race_by_sprinting(state, perspective):
        progress_actions = [
            action for action in root_actions
            if is_pawn_action(action)
            and movement_path(apply_action(state, action), perspective)[0] < movement_path(state, perspective)[0]
        ]
        if progress_actions:
            root_actions = progress_actions

    if opp_dist <= 1 and state.walls_left(perspective) > 0:
        blockers: list[tuple[float, str]] = []
        for wall in legal_walls(state, focused=True):
            action = wall_to_text(wall)
            child = apply_action(state, action)
            if movement_path(child, opp)[0] > opp_dist:
                blockers.append((static_eval(child, perspective), action))
        if blockers:
            blockers.sort(reverse=True)
            return blockers[0][1], blockers[0][0], 0

    def root_adjusted_score(action: str, score: float) -> float:
        score += immediate_reply_adjustment(state, action, perspective)
        score += wall_resource_adjustment(state, action, perspective)
        score += race_conversion_adjustment(state, action, perspective)
        if action in avoid_actions and not improves_root_path(action) and not tactically_justified_reposition(action):
            return score - 900
        return score

    best_action = root_actions[0]
    best_score = root_adjusted_score(best_action, static_eval(apply_action(state, best_action), perspective))
    reached_depth = 0

    transposition: dict[tuple[tuple, int, int], float] = {}
    history_scores: dict[str, int] = {}
    killer_moves: dict[int, list[str]] = {}

    def tactical_position(cur: State) -> bool:
        if cur.red[1] == GOAL_ROW["red"] or cur.blue[1] == GOAL_ROW["blue"]:
            return False
        cur_dist, _ = movement_path(cur, cur.turn)
        opp_dist, _ = movement_path(cur, opponent(cur.turn))
        return (
            cur_dist <= 2
            or opp_dist <= 2
            or player_has_goal_move(cur, cur.turn)
            or player_has_goal_move(cur, opponent(cur.turn))
        )

    def remember_cutoff(action: str, depth: int, ply: int) -> None:
        history_scores[action] = history_scores.get(action, 0) + depth * depth
        killers = killer_moves.setdefault(ply, [])
        if action not in killers:
            killers.insert(0, action)
            del killers[2:]

    def ranked_actions(cur: State, ply: int, limit_walls: int, limit: int) -> list[str]:
        actions = ordered_actions(cur, limit_walls=limit_walls)
        killers = killer_moves.get(ply, [])

        def priority(action: str) -> int:
            killer_bonus = 50_000 if action in killers else 0
            return killer_bonus + history_scores.get(action, 0)

        actions.sort(key=priority, reverse=True)
        return actions[:limit]

    def negamax(key: tuple, depth: int, alpha: float, beta: float, ply: int = 0, q_depth: int = 0) -> float:
        if time.perf_counter() >= deadline:
            raise TimeoutError

        cur = state_from_key(key)
        action_limit = SEARCH_ACTION_LIMIT
        wall_limit = 10
        if depth == 0 and tactical_position(cur) and q_depth < QUIESCENCE_EXTENSION_LIMIT:
            depth = 1
            q_depth += 1
            action_limit = QUIESCENCE_ACTION_LIMIT
            wall_limit = 8

        cache_key = (key, depth, q_depth)
        if cache_key in transposition:
            return transposition[cache_key]

        if depth == 0 or cur.red[1] == GOAL_ROW["red"] or cur.blue[1] == GOAL_ROW["blue"]:
            sign = 1 if cur.turn == perspective else -1
            value = sign * static_eval(cur, perspective)
            transposition[cache_key] = value
            return value
        value = -math.inf
        cut = False
        for action in ranked_actions(cur, ply, wall_limit, action_limit):
            child = apply_action(cur, action)
            value = max(value, -negamax(child.key(), depth - 1, -beta, -alpha, ply + 1, q_depth))
            alpha = max(alpha, value)
            if alpha >= beta:
                cut = True
                remember_cutoff(action, depth, ply)
                break
        if not cut:
            transposition[cache_key] = value
        return value

    try:
        for depth in range(1, max_depth + 1):
            local_best, local_score = best_action, -math.inf
            alpha = -math.inf
            for action in root_actions:
                child = apply_action(state, action)
                score = -negamax(child.key(), depth - 1, -math.inf, -alpha, 1)
                adjusted = root_adjusted_score(action, score)
                if adjusted > local_score:
                    local_best, local_score = action, adjusted
                alpha = max(alpha, local_score)
                if time.perf_counter() >= deadline:
                    raise TimeoutError
            best_action, best_score = local_best, local_score
            reached_depth = depth
    except TimeoutError:
        pass
    return best_action, best_score, reached_depth


def describe_state(state: State) -> str:
    red_dist, red_path = shortest_path(state, "red")
    blue_dist, blue_path = shortest_path(state, "blue")
    lines = [
        f"turn: {state.turn}",
        f"red:  {coord_to_text(state.red)} walls={state.red_walls} dist={red_dist} path={' '.join(map(coord_to_text, red_path))}",
        f"blue: {coord_to_text(state.blue)} walls={state.blue_walls} dist={blue_dist} path={' '.join(map(coord_to_text, blue_path))}",
        f"walls: {' '.join(wall_to_text(w) for w in sorted(state.walls)) or '-'}",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline Barricade/Quoridor training analyzer.")
    parser.add_argument("--history", default="", help='Move list, e.g. "1. e2 e8 2. e3 e7 3. hd5"')
    parser.add_argument("--time", type=float, default=1.0, help="Search seconds.")
    parser.add_argument("--depth", type=int, default=4, help="Maximum search depth.")
    args = parser.parse_args()

    state = state_from_history(args.history)
    best, score, depth = search_best(state, time_limit=args.time, max_depth=args.depth)
    print(describe_state(state))
    print(f"recommendation_for_training: {best}")
    print(f"score={score:.1f} searched_depth={depth}")


if __name__ == "__main__":
    main()
