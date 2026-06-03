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


if __name__ == "__main__":
    unittest.main()
