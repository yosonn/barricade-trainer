import unittest
from dataclasses import replace
from unittest.mock import patch

import barricade_mcts as mcts
import barricade_trainer as b
import barricade_expert as expert
import barricade_web as web
from tools.barricade_backtest import audit_losses
from tools.barricade_external import live_sync_core


class BarricadeTrainerTests(unittest.TestCase):
    def test_opening_history(self):
        state = b.state_from_history("1. e2 e8 2. e3 e7")
        self.assertEqual(state.red, b.text_to_coord("e3"))
        self.assertEqual(state.blue, b.text_to_coord("e7"))
        self.assertEqual(state.turn, "red")

    def test_blue_can_start_history(self):
        state = b.state_from_history("e8", start_turn="blue")
        self.assertEqual(state.blue, b.text_to_coord("e8"))
        self.assertEqual(state.red, b.text_to_coord("e1"))
        self.assertEqual(state.turn, "red")

    def test_wall_blocks_shortest_path(self):
        state = b.apply_action(b.State(), "he1")
        dist, path = b.shortest_path(state, "red")
        self.assertGreater(dist, 8)
        self.assertNotEqual(path[1], b.text_to_coord("e2"))

    def test_cannot_overlap_wall(self):
        state = b.apply_action(b.State(), "he1")
        self.assertFalse(b.can_place_wall(state, b.text_to_wall("he1")))
        self.assertFalse(b.can_place_wall(state, b.text_to_wall("ve1")))

    def test_jump_and_diagonal_jump(self):
        state = b.State(red=b.text_to_coord("e4"), blue=b.text_to_coord("e5"))
        self.assertIn(b.text_to_coord("e6"), b.legal_pawn_moves(state, "red"))

        blocked = b.apply_action(b.State(red=b.text_to_coord("e4"), blue=b.text_to_coord("e5")), "he5")
        moves = set(b.legal_pawn_moves(blocked, "blue"))
        self.assertIn(b.text_to_coord("d5"), moves)
        self.assertIn(b.text_to_coord("f5"), moves)

    def test_screenshot_history_is_parseable(self):
        state = b.state_from_history(
            "1. e2 e8 2. e3 e7 3. e4 e6 4. hd5 ve4 "
            "5. hb3 vc4 6. e3 vc2 7. e2 f6 8. hf5 va3"
        )
        self.assertEqual(state.turn, "red")
        self.assertEqual(state.red_walls, 7)
        self.assertEqual(state.blue_walls, 6)
        self.assertLess(b.shortest_path(state, "red")[0], float("inf"))
        self.assertLess(b.shortest_path(state, "blue")[0], float("inf"))

    def test_search_blocks_one_step_opponent_win(self):
        state = b.State(
            red=b.text_to_coord("a5"),
            blue=b.text_to_coord("e2"),
            turn="red",
            red_walls=10,
            blue_walls=10,
        )
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=2)
        child = b.apply_action(state, best)
        self.assertRegex(best, r"^[hv][a-h][1-8]$")
        self.assertGreater(b.shortest_path(child, "blue")[0], 1)

    def test_movement_path_counts_jump_threats(self):
        state = b.state_from_history("e2 e8 e3 e7 e4 e6 e5")
        self.assertEqual(b.shortest_path(state, "blue")[0], 5)
        self.assertEqual(b.movement_path(state, "blue")[0], 4)

    def test_opening_uses_expert_style_tempo_development(self):
        state = b.state_from_history("e2 e8 e3 e7 e4 e6")
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=3)
        self.assertEqual(best, "e5")

    def test_blue_opening_book_develops_before_back_rank_walls(self):
        state = b.state_from_history("e2 e8 e3 e7 e4")
        best, _, depth = b.search_best(state, time_limit=0.05, max_depth=3)
        self.assertEqual(best, "e6")
        self.assertEqual(depth, 0)

    def test_path_flexibility_counts_useful_moves(self):
        open_state = b.State(red=b.text_to_coord("e5"), blue=b.text_to_coord("i9"), turn="red")
        boxed_state = b.State(
            red=b.text_to_coord("e5"),
            blue=b.text_to_coord("i9"),
            turn="red",
            walls=frozenset({
                b.text_to_wall("hd5"),
                b.text_to_wall("ve4"),
                b.text_to_wall("vf4"),
            }),
        )
        self.assertGreater(b.path_flexibility(open_state, "red"), b.path_flexibility(boxed_state, "red"))

    def test_path_control_rewards_occupying_opponent_route(self):
        neutral = b.State(red=b.text_to_coord("i6"), blue=b.text_to_coord("g8"), red_walls=0, blue_walls=0)
        controlled = b.State(red=b.text_to_coord("g6"), blue=b.text_to_coord("g8"), red_walls=0, blue_walls=0)
        self.assertGreater(b.path_control_score(controlled, "red"), b.path_control_score(neutral, "red"))

    def test_recent_reversal_avoid_action_from_history(self):
        avoid = web.recent_reversal_avoid_actions("e2 e8 e3 e7 e4 e6", "red")
        self.assertEqual(avoid, {"e1", "e2", "e3"})

    def test_recent_state_repeat_avoid_actions_detects_cycle_closing_move(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 e5 hc2 he5 hg2 hc5 f5 vf4 d5 ha5 ha2 vd4 "
            "vh3 hh5 hh1 vf1 d4 hd3 c4 e4 c3 f4 d3 f3 e3 g3 hf3 h3 f3 h4 "
            "vg5 hf6 e3 h5 f3 h4"
        )
        avoid = web.recent_state_repeat_avoid_actions(history, "red")
        self.assertIn("e3", avoid)

    def test_root_avoid_actions_combines_reversal_and_repeat_filters(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 e5 hc2 he5 hg2 hc5 f5 vf4 d5 ha5 ha2 vd4 "
            "vh3 hh5 hh1 vf1 d4 hd3 c4 e4 c3 f4 d3 f3 e3 g3 hf3 h3 f3 h4 "
            "vg5 hf6 e3 h5 f3 h4"
        )
        avoid = web.root_avoid_actions(history, "red")
        self.assertIn("e3", avoid)

    def test_search_avoids_immediate_reversal_when_alternatives_exist(self):
        history = (
            "e2 e8 e3 e7 e4 e6 d4 e5 d5 e4 d6 hc6 hc5 vd5 "
            "ha5 ha7 vc7 hb8 c6 e3 b6 e2 hd1 f2 hf1"
        )
        state = b.state_from_history(history)
        avoid = web.recent_reversal_avoid_actions(history, "red")
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=2, avoid_actions=avoid)
        self.assertNotEqual(best, "e2")

    def test_recent_position_filter_keeps_shortest_path_progress(self):
        history = (
            "e2 e8 e3 e7 e4 e6 e5 e4 e6 he6 d6 hc6 c6 vb5 "
            "he3 d4 hc3 c4 vb3 vc5 vf4 hg6 hg5 hh8 hh4 vh7 "
            "c5 vf2 d4 ve1 d5 vd5 ve5 c5 vd1"
        )
        state = b.state_from_history(history)
        avoid = web.recent_reversal_avoid_actions(history, "red")
        self.assertIn("c4", avoid)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=2, avoid_actions=avoid)
        self.assertEqual(best, "c4")

    def test_state_repeat_filter_keeps_ai_out_of_recent_loop(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 e5 hc2 he5 hg2 hc5 f5 vf4 d5 ha5 ha2 vd4 "
            "vh3 hh5 hh1 vf1 d4 hd3 c4 e4 c3 f4 d3 f3 e3 g3 hf3 h3 f3 h4 "
            "vg5 hf6 e3 h5 f3 h4"
        )
        state = b.state_from_history(history)
        avoid = web.root_avoid_actions(history, "red")
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=3, avoid_actions=avoid)
        self.assertNotEqual(best, "e3")

    def test_state_payload_includes_realtime_analysis(self):
        state = b.state_from_history("e2 e8 e3 e7")
        payload = web.state_payload(state, "red", 0.05, 2, recommend_for_turn=True)
        analysis = payload["analysis"]
        self.assertEqual(analysis["engine"], "hybrid")
        self.assertIn(analysis["resolved_engine"], {"mcts", "alpha-beta"})
        self.assertEqual(analysis["perspective"], state.turn)
        self.assertGreaterEqual(len(analysis["candidates"]), 1)
        self.assertIn("action", analysis["candidates"][0])
        self.assertIn("strategy", analysis)

    def test_state_payload_can_use_alpha_beta_engine(self):
        state = b.state_from_history("e2 e8 e3 e7")
        payload = web.state_payload(
            state,
            "red",
            0.05,
            2,
            engine_kind="alpha-beta",
            recommend_for_turn=True,
        )
        self.assertEqual(payload["analysis"]["engine"], "alpha-beta")
        self.assertEqual(payload["analysis"]["resolved_engine"], "alpha-beta")
        self.assertIn(payload["recommendation"], payload["legal_actions"])

    @patch("barricade_web.BarricadeGgAiClient")
    def test_state_payload_can_use_external_expert_engine(self, client_cls):
        client_cls.return_value.get_move.return_value = "e2"
        state = b.State()
        payload = web.state_payload(
            state,
            "red",
            0.05,
            2,
            engine_kind="expert",
            recommend_for_turn=True,
            history_tokens=[],
        )
        self.assertEqual(payload["analysis"]["engine"], "expert")
        self.assertEqual(payload["analysis"]["resolved_engine"], "expert")
        self.assertEqual(payload["recommendation"], "e2")
        client_cls.return_value.get_move.assert_called_once_with([])

    def test_expert_coordinate_mirror_for_blue_first_mode(self):
        self.assertEqual(expert.mirror_action("e2"), "e8")
        self.assertEqual(expert.mirror_action("e8"), "e2")
        self.assertEqual(expert.mirror_action("ha1"), "ha8")
        self.assertEqual(expert.mirror_action("va3"), "va6")

    @patch("barricade_web.BarricadeGgAiClient")
    def test_external_expert_blue_first_opening_is_mirrored(self, client_cls):
        client_cls.return_value.get_move.return_value = "e2"
        state = b.State(turn="blue")
        payload = web.state_payload(
            state,
            "blue",
            0.05,
            2,
            engine_kind="expert",
            recommend_for_turn=True,
            start_turn="blue",
            history_tokens=[],
        )
        self.assertEqual(payload["recommendation"], "e8")
        client_cls.return_value.get_move.assert_called_once_with([])

    @patch("barricade_web.BarricadeGgAiClient")
    def test_external_expert_blue_first_history_is_mirrored_for_api(self, client_cls):
        client_cls.return_value.get_move.return_value = "e8"
        state = b.state_from_history("e8", start_turn="blue")
        payload = web.state_payload(
            state,
            "red",
            0.05,
            2,
            engine_kind="expert",
            recommend_for_turn=True,
            start_turn="blue",
            history_tokens=["e8"],
        )
        self.assertEqual(payload["recommendation"], "e2")
        client_cls.return_value.get_move.assert_called_once_with(["e2"])

    @patch("barricade_web.BarricadeGgAiClient")
    def test_external_expert_illegal_move_is_rejected(self, client_cls):
        client_cls.return_value.get_move.return_value = "a1"
        with self.assertRaisesRegex(ValueError, "illegal move"):
            web.recommend_action(
                b.State(),
                search_time=0.05,
                depth=2,
                engine_kind="expert",
                avoid_actions=set(),
                history_tokens=[],
            )

    @patch("barricade_web.BarricadeGgAiClient")
    def test_state_payload_can_suppress_expert_recommendation(self, client_cls):
        state = b.state_from_history("e2 e8 e3 e7")
        payload = web.state_payload(
            state,
            "red",
            0.05,
            2,
            engine_kind="expert",
            recommend_for_turn=False,
            history_tokens=["e2", "e8", "e3", "e7"],
            suppress_recommend=True,
        )
        self.assertIsNone(payload["recommendation"])
        client_cls.assert_not_called()

    def test_hybrid_resolves_to_alpha_beta_in_late_goal_threat(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 hd4 f4 e5 f5 g5 hg4 he5 "
            "vg5 g6 vf3 g7 vg7 g8 g5 hf6 g6 ve6 g5 g9 hh8 "
            "vd5 vf8 g8 vd7 g7 f5 f7 f4 f8 e4 vc3 e3 f9 d3 e9 d2 d9 c2 "
            "hb2 ha1 c9 b2 b9 hc1 a9 a2 a8 a3 a7 a4 a6 b4 a5 b5 a4 "
            "b6 hb6 a6 ha7 a7 a3"
        )
        state = b.state_from_history(history)
        payload = web.state_payload(state, "blue", 0.05, 3, recommend_for_turn=True)
        self.assertEqual(payload["analysis"]["engine"], "hybrid")
        self.assertEqual(payload["analysis"]["resolved_engine"], "alpha-beta")
        self.assertEqual(payload["recommendation"], "a6")

    def test_hybrid_uses_alpha_beta_for_close_wall_trap_opening(self):
        state = b.state_from_history("e2 e8 e3 e7 e4 e6")
        payload = web.state_payload(state, "red", 0.05, 3, recommend_for_turn=True)
        self.assertEqual(payload["analysis"]["resolved_engine"], "alpha-beta")
        self.assertEqual(payload["recommendation"], "e5")

    def test_reported_strong_computer_game_avoids_mcts_opening_trap(self):
        history = "e2 e8 e3 e7 e4 e6 he2 hf6"
        state = b.state_from_history(history)
        payload = web.state_payload(state, "red", 0.05, 3, recommend_for_turn=True)
        self.assertEqual(payload["analysis"]["resolved_engine"], "alpha-beta")
        self.assertEqual(payload["recommendation"], "e5")

    def test_barricade_gg_expert_red_avoids_next_wall_trap(self):
        history = "e2 e8 e3 e7 e4 e6 hd4 hf6 hf3 ha7 f4 hh6"
        state = b.state_from_history(history)
        avoid = web.root_avoid_actions(history, "red")
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4, avoid_actions=avoid)
        child = b.apply_action(state, best)
        threat, _ = b.opponent_wall_threat(child, "red")
        self.assertNotEqual(best, "f5")
        self.assertLess(threat, 5)

    def test_barricade_gg_expert_blue_avoids_endgame_wall_trap(self):
        history = "e2 e8 e3 he8 e4 hc8 ha1 e7 e5 hg8 f5 e6 vd1 e5 he4 d5 vd3"
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4)
        child = b.apply_action(state, best)
        threat, _ = b.opponent_wall_threat(child, "blue")
        self.assertNotEqual(best, "d4")
        self.assertLess(threat, 4)

    def test_barricade_gg_expert_red_spends_final_wall_to_defuse_trap(self):
        history = (
            "e2 e8 e3 e7 e4 e6 hd4 hf6 hf3 hh6 f4 e5 e4 hd6 d4 vc3 "
            "e4 hb6 vc6 f5 hd1 ha2 vf5 e5 hb4 ha5 e3 f5 hf4 e5 hb1 hd2 vb2 hf2"
        )
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4)
        child = b.apply_action(state, best)
        threat, _ = b.opponent_wall_threat(child, "red")
        self.assertEqual(best, "hf1")
        self.assertLessEqual(threat, 2)

    def test_loss_audit_helpers_identify_side_and_distance_delta(self):
        record = {"red_engine": "candidate", "blue_engine": "baseline"}
        self.assertEqual(audit_losses.audited_side_for_game(record, "candidate"), "red")
        state = b.state_from_history("e2 e8 e3 e7")
        my_delta, opp_delta = audit_losses.distance_delta(state, "e4", state.turn)
        self.assertEqual(my_delta, 1)
        self.assertEqual(opp_delta, 0)

    def test_live_sync_extracts_moves_field_history(self):
        text = '{"moves":"e2,e8,e3,e7,hd5"}'
        candidate = live_sync_core.choose_best_history(text, "red")
        self.assertTrue(candidate.valid)
        self.assertEqual(candidate.history, ["e2", "e8", "e3", "e7", "hd5"])

    def test_live_sync_repairs_plain_text_by_legal_subsequence(self):
        text = "board labels a1 b1 c1 moves e2 e8 e3 e7 bad e4"
        candidate = live_sync_core.choose_best_history(text, "red")
        self.assertTrue(candidate.valid)
        self.assertEqual(candidate.history[-5:], ["e2", "e8", "e3", "e7", "e4"])

    def test_blue_preserves_last_walls_when_race_is_winning(self):
        history = (
            "e2 e8 e3 e7 e4 e6 e5 he8 e7 hd7 f7 e5 g7 hg7 "
            "f7 e4 f8 vf8 e8 vd8 f8 f4 f7 vf6 hd6 ve6 f6 g4 f5 hh8 g5"
        )
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=3)
        self.assertEqual(best, "g3")

    def test_blue_endgame_tempo_does_not_step_back_from_goal_lane(self):
        history = (
            "e2 e8 e3 e7 e4 e6 e5 he8 e7 hd7 d7 vc7 hc5 e5 vb6 e4 "
            "vd6 hb8 ha7 e3 d6 e2 hd1 f2 hf1"
        )
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=3)
        self.assertNotEqual(best, "f3")

    def test_red_converts_large_race_lead_instead_of_spending_last_walls(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 he7 hd5 hd4 d4 f6 c4 f5 "
            "c5 hb5 hf4 e5 hb4 f5 vf5 e5 vc5 f5 vf7 f6 "
            "vc7 va6 b5 va3 a5 e6"
        )
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4)
        self.assertEqual(best, "a6")

    def test_red_keeps_sprinting_after_large_race_lead_with_one_wall_left(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 he7 hd5 hd4 d4 f6 c4 f5 "
            "c5 hb5 hf4 e5 hb4 f5 vf5 e5 vc5 f5 vf7 f6 "
            "vc7 va6 b5 va3 a5 e6 hd6 f6"
        )
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4)
        self.assertEqual(best, "a6")

    def test_red_does_not_spend_low_walls_on_weak_delay_when_behind(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 he6 hd5 vc4 e5 d6 vc6 hf5 "
            "f5 hh5 hd7 vd3 ve7 e6 hg6 f6 e5 g6 hc2 hd4 "
            "f5 h6 f4 i6 hb1 i7 g4 h7 g3 hg2 h3 vh3 h4 hg4 g4 h8"
        )
        state = b.state_from_history(history)
        self.assertEqual(state.red_walls, 2)
        self.assertEqual(state.blue_walls, 1)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4)
        self.assertEqual(best, "f4")

    def test_red_preserves_final_wall_for_sprint_when_trailing(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 he6 hd5 vc4 e5 d6 vc6 hf5 "
            "f5 hh5 hd7 vd3 ve7 e6 hg6 f6 e5 g6 hc2 hd4 "
            "f5 h6 f4 i6 hb1 i7 g4 h7 g3 hg2 h3 vh3 h4 hg4 "
            "g4 h8 vg8 h7 f4 g7 f5 g8"
        )
        state = b.state_from_history(history)
        self.assertEqual(state.red_walls, 1)
        self.assertEqual(state.blue_walls, 1)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4)
        self.assertEqual(best, "g5")

    def test_defensive_wall_values_reducing_future_wall_threat(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 hd4 f4 e5 f5 g5 hg4 he5 "
            "vg5 g6 vf3 g7 vg7 g8 g5 hf6 g6 ve6 g5 g9 hh8 "
            "vd5 vf8 g8 vd7 g7 f5 f7 f4 f8 e4 vc3 e3 f9 d3 e9 d2 d9 c2 "
            "hb2 ha1 c9 b2 b9 hc1 a9 a2 a8 a3 a7 a4 a6 b4 a5 b5 a4 "
            "b6 hb6 a6 ha7 a7 a3"
        )
        state = replace(b.state_from_history(history), red_walls=1, turn="red")
        before_threat, _ = b.opponent_wall_threat(state, "red")
        child = b.apply_action(state, "hb8")
        after_threat, _ = b.opponent_wall_threat(child, "red")
        self.assertGreaterEqual(before_threat, 5)
        self.assertLess(after_threat, before_threat)
        self.assertGreater(b.defensive_wall_adjustment(state, "hb8", "red"), 0)

    def test_low_wall_trailing_race_uses_two_step_delay_wall(self):
        history = (
            "e2 e8 e3 he8 he7 hc8 e4 hg8 e5 ha8 hd3 d8 "
            "e6 ve6 e7 vf8 e6 ve4 hc6 ve2 hb2 vc3 ha1 d7 "
            "hc1 c7 vb7 vd5 e5 d7 e4 e7 d4 e6 d5 e5 c5 e4 "
            "c4 d4 b4 d5 a4 c5 a3 c4 vb3 c5 a2 b5 b2 b4"
        )
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.05, max_depth=3)
        self.assertEqual(best, "va3")

    def test_opening_tempo_prefers_progress_over_weak_delay_wall(self):
        history = "e2 e8 e3 he8 he7 hc8 e4 hg8 e5 ha8"
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.05, max_depth=3)
        self.assertEqual(best, "e6")

    def test_opening_tempo_avoids_self_slowing_delay_wall(self):
        history = "e2 e8 e3 he8 he7 hc8 e4 hg8 e5 d8"
        state = b.state_from_history(history)
        best, _, _ = b.search_best(state, time_limit=0.05, max_depth=3)
        self.assertEqual(best, "e6")

    def test_deeper_search_simplifies_losing_low_wall_corridor_race(self):
        history = (
            "e2 e8 e3 he8 he7 hc8 e4 hg8 e5 ha8 hd3 d8 "
            "e6 ve6 e7 vf8 hc7 ve4 hb6 c8 va7 b8 hc2 b7 "
            "hb1 c7 vd4 vd2 e6 d7 d6 d5 vc4 d7 c6 d6 c5 c6 c4 c5 c3 c4"
        )
        state = b.state_from_history(history)
        self.assertEqual(state.red_walls + state.blue_walls, 3)
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=4)
        self.assertEqual(best, "b3")

    def test_red_sprints_in_winning_no_wall_race(self):
        state = b.State(
            red=b.text_to_coord("a4"),
            blue=b.text_to_coord("a8"),
            turn="red",
            red_walls=0,
            blue_walls=0,
        )
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=3)
        self.assertEqual(best, "a5")

    def test_blue_sprints_in_winning_no_wall_race(self):
        state = b.State(
            red=b.text_to_coord("i2"),
            blue=b.text_to_coord("i6"),
            turn="blue",
            red_walls=0,
            blue_walls=0,
        )
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=3)
        self.assertEqual(best, "i5")

    def test_mcts_recommends_legal_opening_action(self):
        state = b.state_from_history("e2 e8 e3 e7")
        best, _, simulations = mcts.search_mcts(state, time_limit=0.05, simulations=30, seed=7)
        self.assertIn(best, b.ordered_actions(state))
        self.assertGreater(simulations, 0)

    def test_mcts_takes_immediate_win(self):
        state = b.State(red=b.text_to_coord("e8"), blue=b.text_to_coord("a9"), turn="red")
        best, score, simulations = mcts.search_mcts(state, time_limit=0.01, simulations=5)
        self.assertEqual(best, "e9")
        self.assertEqual(score, 100000.0)
        self.assertEqual(simulations, 0)

    def test_mcts_sprints_in_red_no_wall_race(self):
        state = b.State(
            red=b.text_to_coord("a4"),
            blue=b.text_to_coord("a8"),
            turn="red",
            red_walls=0,
            blue_walls=0,
        )
        best, _, _ = mcts.search_mcts(
            state,
            time_limit=0.05,
            simulations=40,
            max_actions=20,
            seed=17,
        )
        self.assertEqual(best, "a5")

    def test_mcts_sprints_in_blue_no_wall_race(self):
        state = b.State(
            red=b.text_to_coord("i2"),
            blue=b.text_to_coord("i6"),
            turn="blue",
            red_walls=0,
            blue_walls=0,
        )
        best, _, _ = mcts.search_mcts(
            state,
            time_limit=0.05,
            simulations=40,
            max_actions=20,
            seed=19,
        )
        self.assertEqual(best, "i5")

    def test_mcts_avoids_low_wall_step_away_from_goal(self):
        history = (
            "e2 e8 e3 e7 e4 e6 he2 he4 hd1 hd8 f4 vf3 e4 vd4 "
            "e3 e5 ve5 hc7 vd6 ha7 ve7 hc2 hb8 vc3 d3 vc5 d4 "
            "vd2 d5 e6 d6 e7 d7 e8 c7 d8 c6 c8 c5 b8 c4 a8 "
            "b4 a9 b3 b9 b2 c9 hg1 d9 c2 e9 c1 f9 d1 f8 "
            "e1 f7 f1 f6 vf5"
        )
        state = b.state_from_history(history)
        best, _, _ = mcts.search_mcts(
            state,
            time_limit=0.05,
            simulations=120,
            max_actions=20,
            rollout_depth=2,
            seed=len(history.split()),
        )
        self.assertEqual(best, "f7")

    def test_mcts_respects_root_avoid_actions(self):
        state = b.state_from_history("e2 e8 e3 e7")
        forbidden = b.ordered_actions(state)[0]
        best, _, _ = mcts.search_mcts(
            state,
            time_limit=0.05,
            simulations=30,
            avoid_actions={forbidden},
            seed=11,
        )
        self.assertNotEqual(best, forbidden)

    def test_mcts_falls_back_when_all_root_actions_are_avoided(self):
        state = b.state_from_history("e2 e8 e3 e7")
        legal = set(b.ordered_actions(state))
        best, _, _ = mcts.search_mcts(
            state,
            time_limit=0.02,
            simulations=10,
            avoid_actions=legal,
            seed=13,
        )
        self.assertIn(best, legal)


if __name__ == "__main__":
    unittest.main()

