from __future__ import annotations

import json
from dataclasses import dataclass

import barricade_trainer as engine


@dataclass(frozen=True)
class ExpertCacheHit:
    action: str
    source: str
    count: int
    total: int
    confidence: float


def expert_state_key(state: engine.State) -> str:
    payload = {
        "blue": engine.coord_to_text(state.blue),
        "blue_walls": state.blue_walls,
        "red": engine.coord_to_text(state.red),
        "red_walls": state.red_walls,
        "turn": state.turn,
        "walls": sorted(engine.wall_to_text(wall) for wall in state.walls),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


HISTORY_CACHE: dict[str, ExpertCacheHit] = {
    "": ExpertCacheHit("e2", "opening-book", 20, 20, 1.0),
    "e2": ExpertCacheHit("e8", "opening-book", 20, 20, 1.0),
    "e2 e8": ExpertCacheHit("e3", "opening-book", 20, 20, 1.0),
    "e2 e8 e3": ExpertCacheHit("e7", "opening-book", 20, 20, 1.0),
    "e2 e8 e3 e7": ExpertCacheHit("e4", "opening-book", 20, 20, 1.0),
    "e2 e8 e3 e7 e4": ExpertCacheHit("e6", "opening-book", 20, 20, 1.0),
    "e2 e8 e3 e7 e4 e6 he3": ExpertCacheHit("hf6", "opening-book", 6, 6, 1.0),
    "e2 e8 e3 e7 e4 e6 he3 hf6": ExpertCacheHit("hc3", "opening-book", 5, 6, 0.8333),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3": ExpertCacheHit("vd4", "opening-book", 4, 5, 0.8),
    "e2 e8 e3 e7 e4 e6 hc3": ExpertCacheHit("vd4", "opening-book", 4, 5, 0.8),
    "e2 e8 e3 e7 e4 e6 hc3 vd4": ExpertCacheHit("ha3", "opening-book", 3, 4, 0.75),
    "e2 e8 e3 e7 e4 e6 hc3 vd4 ha3": ExpertCacheHit("f6", "opening-book", 3, 3, 1.0),
}


STATE_CACHE: dict[str, ExpertCacheHit] = {
    '{"blue":"e9","blue_walls":10,"red":"e1","red_walls":10,"turn":"red","walls":[]}': ExpertCacheHit("e2", "state-cache", 20, 20, 1.0),
    '{"blue":"e9","blue_walls":10,"red":"e2","red_walls":10,"turn":"blue","walls":[]}': ExpertCacheHit("e8", "state-cache", 20, 20, 1.0),
    '{"blue":"e8","blue_walls":10,"red":"e2","red_walls":10,"turn":"red","walls":[]}': ExpertCacheHit("e3", "state-cache", 20, 20, 1.0),
    '{"blue":"e8","blue_walls":10,"red":"e3","red_walls":10,"turn":"blue","walls":[]}': ExpertCacheHit("e7", "state-cache", 20, 20, 1.0),
    '{"blue":"e7","blue_walls":10,"red":"e3","red_walls":10,"turn":"red","walls":[]}': ExpertCacheHit("e4", "state-cache", 20, 20, 1.0),
    '{"blue":"e7","blue_walls":10,"red":"e4","red_walls":10,"turn":"blue","walls":[]}': ExpertCacheHit("e6", "state-cache", 20, 20, 1.0),
    '{"blue":"e6","blue_walls":10,"red":"e4","red_walls":9,"turn":"blue","walls":["he3"]}': ExpertCacheHit("hf6", "state-cache", 8, 9, 0.8889),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":9,"turn":"red","walls":["he3","hf6"]}': ExpertCacheHit("hc3", "state-cache", 8, 8, 1.0),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":8,"turn":"blue","walls":["hc3","he3","hf6"]}': ExpertCacheHit("vd4", "state-cache", 6, 8, 0.75),
    '{"blue":"e6","blue_walls":8,"red":"e4","red_walls":8,"turn":"red","walls":["hc3","he3","hf6","vd4"]}': ExpertCacheHit("ve5", "state-cache", 5, 6, 0.8333),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":8,"turn":"blue","walls":["ha3","hc3","vd4"]}': ExpertCacheHit("f6", "state-cache", 5, 5, 1.0),
    '{"blue":"e6","blue_walls":8,"red":"e4","red_walls":7,"turn":"blue","walls":["hc3","he3","hf6","vd4","ve5"]}': ExpertCacheHit("hh6", "state-cache", 5, 5, 1.0),
    '{"blue":"e6","blue_walls":10,"red":"e4","red_walls":9,"turn":"blue","walls":["hc3"]}': ExpertCacheHit("vd4", "state-cache", 4, 5, 0.8),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":9,"turn":"red","walls":["hc3","vd4"]}': ExpertCacheHit("ha3", "state-cache", 3, 4, 0.75),
}


def lookup_expert_cache(history: list[str]) -> ExpertCacheHit | None:
    history_key = " ".join(history)
    hit = HISTORY_CACHE.get(history_key)
    if hit:
        return hit

    try:
        state = engine.state_from_history(history_key, start_turn="red")
    except Exception:
        return None
    return STATE_CACHE.get(expert_state_key(state))
