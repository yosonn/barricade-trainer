import unittest

import barricade_trainer as b
import barricade_web as web


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

    def test_opening_avoids_feeding_opponent_jump(self):
        state = b.state_from_history("e2 e8 e3 e7 e4 e6")
        best, _, _ = b.search_best(state, time_limit=0.2, max_depth=3)
        self.assertNotEqual(best, "e5")

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


if __name__ == "__main__":
    unittest.main()

