from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

import barricade_trainer as engine


@dataclass
class MctsNode:
    state: engine.State
    parent: "MctsNode | None" = None
    action: str | None = None
    prior: float = 1.0
    visits: int = 0
    value_sum: float = 0.0
    children: dict[str, "MctsNode"] = field(default_factory=dict)
    expanded: bool = False

    @property
    def q(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


def winner(state: engine.State) -> str | None:
    if state.red[1] == engine.GOAL_ROW["red"]:
        return "red"
    if state.blue[1] == engine.GOAL_ROW["blue"]:
        return "blue"
    return None


def value_from_perspective(state: engine.State, perspective: str) -> float:
    win = winner(state)
    if win == perspective:
        return 1.0
    if win == engine.opponent(perspective):
        return -1.0
    score = engine.static_eval(state, perspective)
    return math.tanh(score / 900.0)


def action_prior_score(state: engine.State, action: str) -> float:
    perspective = state.turn
    child = engine.apply_action(state, action)
    if child.pawn(perspective)[1] == engine.GOAL_ROW[perspective]:
        return 1_000_000.0
    if engine.player_has_goal_move(child, engine.opponent(perspective)):
        return -500_000.0

    before_my = engine.movement_path(state, perspective)[0]
    before_opp = engine.movement_path(state, engine.opponent(perspective))[0]
    after_my = engine.movement_path(child, perspective)[0]
    after_opp = engine.movement_path(child, engine.opponent(perspective))[0]
    race_delta = (before_my - after_my) * 120 + (after_opp - before_opp) * 140
    race_score = engine.pawn_race_adjustment(state, action, perspective)
    if (
        engine.is_pawn_action(action)
        and state.walls_left(perspective) + state.walls_left(engine.opponent(perspective)) <= 3
        and after_my > before_my
    ):
        race_score -= 800 + (after_my - before_my) * 250
    return engine.action_score(state, action, perspective) + race_delta + race_score


def race_filtered_actions(
    state: engine.State,
    max_actions: int,
    forbidden_actions: set[str] | None = None,
) -> list[str]:
    forbidden_actions = forbidden_actions or set()
    race_actions = engine.safe_pawn_race_progress_actions(state, state.turn)
    if race_actions:
        return race_actions[:max_actions]

    perspective = state.turn
    opp = engine.opponent(perspective)
    low_wall_race = state.walls_left(perspective) + state.walls_left(opp) <= 3
    my_dist = engine.movement_path(state, perspective)[0]
    actions = [
        action
        for action in engine.ordered_actions(state, limit_walls=max_actions)
        if action not in forbidden_actions
        or (
            low_wall_race
            and
            engine.is_pawn_action(action)
            and engine.movement_path(engine.apply_action(state, action), perspective)[0] < my_dist
        )
    ][:max_actions]
    if not actions and forbidden_actions:
        actions = engine.ordered_actions(state, limit_walls=max_actions)[:max_actions]
    if low_wall_race:
        progress_pawns = [
            action for action in actions
            if engine.is_pawn_action(action)
            and engine.movement_path(engine.apply_action(state, action), perspective)[0] < my_dist
        ]
        if progress_pawns:
            actions = [
                action for action in actions
                if not (
                    engine.is_pawn_action(action)
                    and engine.movement_path(engine.apply_action(state, action), perspective)[0] > my_dist
                )
            ]
    return actions


def action_priors(
    state: engine.State,
    max_actions: int,
    forbidden_actions: set[str] | None = None,
) -> list[tuple[str, float]]:
    actions = race_filtered_actions(state, max_actions, forbidden_actions)
    if not actions:
        return []
    scored = [(action_prior_score(state, action), action) for action in actions]
    top = max(score for score, _ in scored)
    weights = [max(1.0, 1.0 + (score - top) / 220.0 + len(scored) - index) for index, (score, _) in enumerate(scored)]
    total = sum(weights)
    return [(action, weight / total) for weight, (_, action) in zip(weights, scored)]


def expand(
    node: MctsNode,
    max_actions: int,
    forbidden_actions: set[str] | None = None,
) -> None:
    if node.expanded or winner(node.state):
        node.expanded = True
        return
    root_forbidden = forbidden_actions if node.parent is None else None
    for action, prior in action_priors(node.state, max_actions, root_forbidden):
        if action not in node.children:
            child_state = engine.apply_action(node.state, action)
            node.children[action] = MctsNode(
                state=child_state,
                parent=node,
                action=action,
                prior=prior,
            )
    node.expanded = True


def select_child(
    node: MctsNode,
    exploration: float,
    rng: random.Random,
    root_perspective: str,
) -> MctsNode:
    parent_visits = max(1, node.visits)
    maximizing = node.state.turn == root_perspective
    best_score = -math.inf
    best_children: list[MctsNode] = []
    for child in node.children.values():
        u = exploration * child.prior * math.sqrt(parent_visits) / (1 + child.visits)
        score = (child.q if maximizing else -child.q) + u
        if score > best_score + 1e-12:
            best_score = score
            best_children = [child]
        elif abs(score - best_score) <= 1e-12:
            best_children.append(child)
    return rng.choice(best_children)


def backpropagate(node: MctsNode, value: float) -> None:
    cur: MctsNode | None = node
    while cur is not None:
        cur.visits += 1
        cur.value_sum += value
        cur = cur.parent


def rollout_value(
    state: engine.State,
    perspective: str,
    rollout_depth: int,
    max_actions: int,
) -> float:
    cur = state
    for _ in range(max(0, rollout_depth)):
        if winner(cur):
            break
        actions = race_filtered_actions(cur, max_actions)
        if not actions:
            break
        action = max(actions, key=lambda candidate: action_prior_score(cur, candidate))
        cur = engine.apply_action(cur, action)
    return value_from_perspective(cur, perspective)


def search_mcts(
    state: engine.State,
    time_limit: float = 0.2,
    simulations: int = 200,
    max_actions: int = 16,
    exploration: float = 1.35,
    rollout_depth: int = 2,
    avoid_actions: set[str] | None = None,
    seed: int = 0,
) -> tuple[str, float, int]:
    avoid_actions = avoid_actions or set()
    root_actions = race_filtered_actions(state, max_actions, avoid_actions)
    if not root_actions:
        raise ValueError("No legal actions available for MCTS")

    for action in root_actions:
        if engine.is_pawn_action(action) and engine.text_to_coord(action)[1] == engine.GOAL_ROW[state.turn]:
            return action, 100000.0, 0

    rng = random.Random(seed)
    root = MctsNode(state=state)
    perspective = state.turn
    deadline = time.perf_counter() + max(0.0, time_limit)
    completed = 0
    expand(root, max_actions, avoid_actions)

    while completed < simulations and time.perf_counter() < deadline:
        node = root
        while node.expanded and node.children and not winner(node.state):
            node = select_child(node, exploration, rng, perspective)
        expand(node, max_actions, avoid_actions)
        value = rollout_value(node.state, perspective, rollout_depth, max_actions)
        backpropagate(node, value)
        completed += 1

    if not root.children:
        return root_actions[0], engine.static_eval(engine.apply_action(state, root_actions[0]), perspective), completed

    best = max(
        root.children.values(),
        key=lambda child: (child.visits, child.q, child.prior, child.action or ""),
    )
    return best.action or root_actions[0], best.q * 1000.0, completed
