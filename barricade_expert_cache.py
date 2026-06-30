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
    "": ExpertCacheHit("e2", "opening-book", 40, 40, 1.0),
    "e2": ExpertCacheHit("e8", "opening-book", 40, 40, 1.0),
    "e2 e8": ExpertCacheHit("e3", "opening-book", 40, 40, 1.0),
    "e2 e8 e3": ExpertCacheHit("e7", "opening-book", 40, 40, 1.0),
    "e2 e8 e3 e7": ExpertCacheHit("e4", "opening-book", 40, 40, 1.0),
    "e2 e8 e3 e7 e4": ExpertCacheHit("e6", "opening-book", 40, 40, 1.0),
    "e2 e8 e3 e7 e4 e6 he3": ExpertCacheHit("hf6", "opening-book", 18, 20, 0.9),
    "e2 e8 e3 e7 e4 e6 he3 hf6": ExpertCacheHit("hc3", "opening-book", 22, 28, 0.7857),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3": ExpertCacheHit("vd4", "opening-book", 30, 32, 0.9375),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4": ExpertCacheHit("ve5", "opening-book", 29, 40, 0.725),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4 ve5": ExpertCacheHit("hh6", "opening-book", 23, 29, 0.7931),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4 ve5 hh6": ExpertCacheHit("e5", "opening-book", 18, 23, 0.7826),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4 ve5 hh6 e5": ExpertCacheHit("hd5", "opening-book", 18, 18, 1.0),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4 ve5 hh6 e5 hd5": ExpertCacheHit("vd6", "opening-book", 16, 18, 0.8889),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4 ve5 hh6 e5 hd5 vd6 ve8": ExpertCacheHit("e4", "opening-book", 11, 11, 1.0),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4 ve5 hh6 e5 hd5 vd6 ve8 e4": ExpertCacheHit("e7", "opening-book", 10, 11, 0.9091),
    "e2 e8 e3 e7 e4 e6 he3 hf6 hc3 vd4 ve5 hh6 e5 hd5 vd6 ve8 e4 e7": ExpertCacheHit("f4", "opening-book", 10, 10, 1.0),
    "e2 e8 e3 e7 e4 e6 hc3": ExpertCacheHit("vd4", "opening-book", 8, 10, 0.8),
    "e2 e8 e3 e7 e4 e6 hc3 vd4": ExpertCacheHit("ha3", "opening-book", 6, 8, 0.75),
    "e2 e8 e3 e7 e4 e6 hc3 vd4 ha3": ExpertCacheHit("f6", "opening-book", 6, 6, 1.0),
    "e2 e8 e3 e7 e4 e6 ha3": ExpertCacheHit("he6", "opening-book", 7, 10, 0.7),
    "e2 e8 e3 e7 e4 e6 ha3 he6": ExpertCacheHit("hc3", "opening-book", 7, 7, 1.0),
    "e2 e8 e3 e7 e4 e6 ha3 he6 hc3": ExpertCacheHit("vd4", "opening-book", 7, 7, 1.0),
    "e2 e8 e3 e7 e4 e6 ha3 he6 hc3 vd4": ExpertCacheHit("he3", "opening-book", 7, 7, 1.0),
    "e2 e8 e3 e7 e4 e6 ha3 he6 hc3 vd4 he3": ExpertCacheHit("f6", "opening-book", 7, 7, 1.0),
    "e2 e8 e3 e7 e4 e6 ha3 vd4": ExpertCacheHit("hc3", "opening-book", 4, 4, 1.0),
}


STATE_CACHE: dict[str, ExpertCacheHit] = {
    '{"blue":"e9","blue_walls":10,"red":"e1","red_walls":10,"turn":"red","walls":[]}': ExpertCacheHit("e2", "state-cache", 40, 40, 1.0),
    '{"blue":"e9","blue_walls":10,"red":"e2","red_walls":10,"turn":"blue","walls":[]}': ExpertCacheHit("e8", "state-cache", 40, 40, 1.0),
    '{"blue":"e8","blue_walls":10,"red":"e2","red_walls":10,"turn":"red","walls":[]}': ExpertCacheHit("e3", "state-cache", 40, 40, 1.0),
    '{"blue":"e8","blue_walls":10,"red":"e3","red_walls":10,"turn":"blue","walls":[]}': ExpertCacheHit("e7", "state-cache", 40, 40, 1.0),
    '{"blue":"e7","blue_walls":10,"red":"e3","red_walls":10,"turn":"red","walls":[]}': ExpertCacheHit("e4", "state-cache", 40, 40, 1.0),
    '{"blue":"e7","blue_walls":10,"red":"e4","red_walls":10,"turn":"blue","walls":[]}': ExpertCacheHit("e6", "state-cache", 40, 40, 1.0),
    '{"blue":"e6","blue_walls":10,"red":"e4","red_walls":9,"turn":"blue","walls":["he3"]}': ExpertCacheHit("hf6", "state-cache", 18, 20, 0.9),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":9,"turn":"red","walls":["he3","hf6"]}': ExpertCacheHit("hc3", "state-cache", 22, 28, 0.7857),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":8,"turn":"blue","walls":["hc3","he3","hf6"]}': ExpertCacheHit("vd4", "state-cache", 30, 32, 0.9375),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":8,"turn":"blue","walls":["ha3","hc3","vd4"]}': ExpertCacheHit("f6", "state-cache", 10, 10, 1.0),
    '{"blue":"e6","blue_walls":10,"red":"e4","red_walls":9,"turn":"blue","walls":["hc3"]}': ExpertCacheHit("vd4", "state-cache", 8, 10, 0.8),
    '{"blue":"e6","blue_walls":8,"red":"e4","red_walls":8,"turn":"red","walls":["hc3","he3","hf6","vd4"]}': ExpertCacheHit("ve5", "state-cache", 29, 40, 0.725),
    '{"blue":"e6","blue_walls":9,"red":"e4","red_walls":9,"turn":"red","walls":["hc3","vd4"]}': ExpertCacheHit("ha3", "state-cache", 6, 8, 0.75),
    '{"blue":"e6","blue_walls":8,"red":"e4","red_walls":7,"turn":"blue","walls":["hc3","he3","hf6","vd4","ve5"]}': ExpertCacheHit("hh6", "state-cache", 23, 29, 0.7931),
    '{"blue":"e6","blue_walls":7,"red":"e4","red_walls":7,"turn":"red","walls":["hc3","he3","hf6","hh6","vd4","ve5"]}': ExpertCacheHit("e5", "state-cache", 18, 23, 0.7826),
    '{"blue":"e6","blue_walls":7,"red":"e5","red_walls":7,"turn":"blue","walls":["hc3","he3","hf6","hh6","vd4","ve5"]}': ExpertCacheHit("hd5", "state-cache", 18, 18, 1.0),
    '{"blue":"e6","blue_walls":6,"red":"e5","red_walls":7,"turn":"red","walls":["hc3","hd5","he3","hf6","hh6","vd4","ve5"]}': ExpertCacheHit("vd6", "state-cache", 16, 18, 0.8889),
    '{"blue":"e6","blue_walls":5,"red":"e5","red_walls":6,"turn":"red","walls":["hc3","hd5","he3","hf6","hh6","vd4","vd6","ve5","ve8"]}': ExpertCacheHit("e4", "state-cache", 11, 11, 1.0),
    '{"blue":"e6","blue_walls":5,"red":"e4","red_walls":6,"turn":"blue","walls":["hc3","hd5","he3","hf6","hh6","vd4","vd6","ve5","ve8"]}': ExpertCacheHit("e7", "state-cache", 10, 11, 0.9091),
    '{"blue":"e7","blue_walls":5,"red":"e4","red_walls":6,"turn":"red","walls":["hc3","hd5","he3","hf6","hh6","vd4","vd6","ve5","ve8"]}': ExpertCacheHit("f4", "state-cache", 10, 10, 1.0),
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
