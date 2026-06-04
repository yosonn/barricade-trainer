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


def action_priors(state: engine.State, max_actions: int) -> list[tuple[str, float]]:
    actions = engine.ordered_actions(state, limit_walls=max_actions)[:max_actions]
    if not actions:
        return []
    weights = [len(actions) - index for index in range(len(actions))]
    total = sum(weights)
    return [(action, weight / total) for action, weight in zip(actions, weights)]


def expand(node: MctsNode, max_actions: int) -> None:
    if node.expanded or winner(node.state):
        node.expanded = True
        return
    for action, prior in action_priors(node.state, max_actions):
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


def search_mcts(
    state: engine.State,
    time_limit: float = 0.2,
    simulations: int = 200,
    max_actions: int = 16,
    exploration: float = 1.35,
    seed: int = 0,
) -> tuple[str, float, int]:
    root_actions = engine.ordered_actions(state, limit_walls=max_actions)[:max_actions]
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
    expand(root, max_actions)

    while completed < simulations and time.perf_counter() < deadline:
        node = root
        while node.expanded and node.children and not winner(node.state):
            node = select_child(node, exploration, rng, perspective)
        expand(node, max_actions)
        value = value_from_perspective(node.state, perspective)
        backpropagate(node, value)
        completed += 1

    if not root.children:
        return root_actions[0], engine.static_eval(engine.apply_action(state, root_actions[0]), perspective), completed

    best = max(
        root.children.values(),
        key=lambda child: (child.visits, child.q, child.prior, child.action or ""),
    )
    return best.action or root_actions[0], best.q * 1000.0, completed
