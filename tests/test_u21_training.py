import unittest

from bb_site import GameLogEntry
from coachparrot_model import POSITION_PRESETS, TrainingAction, listed_salary, replay_training
from u21_training import (
    aggregate_minutes,
    get_game_week,
    infer_training,
    is_counting_game,
    selected_training_position,
    skill_display_rows,
    target_seasons_for_player,
)


class U21TrainingTests(unittest.TestCase):
    def test_non_counting_game_filters(self):
        self.assertFalse(is_counting_game("BBM"))
        self.assertFalse(is_counting_game("BBB"))
        self.assertFalse(is_counting_game("National Team"))
        self.assertFalse(is_counting_game("U21 National Team"))
        self.assertFalse(is_counting_game("Private"))
        self.assertTrue(is_counting_game("League"))

    def test_aggregate_minutes_ignores_non_club_rows(self):
        minutes, ignored = aggregate_minutes(
            {
                72: [
                    GameLogEntry("5/9/2026", "PG", 30, "League"),
                    GameLogEntry("5/9/2026", "PG", 25, "BBB"),
                    GameLogEntry("5/10/2026", "SG", 20, "Cup"),
                ]
            }
        )

        self.assertEqual(minutes[72][2]["PG"], 30)
        self.assertEqual(minutes[72][2]["SG"], 20)
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored[0]["game_type"], "BBB")

    def test_unknown_game_position_does_not_default_to_sg(self):
        minutes, ignored = aggregate_minutes(
            {72: [GameLogEntry("5/9/2026", "", 48, "League")]}
        )

        self.assertEqual(minutes[72], {})
        self.assertEqual(ignored[0]["reason"], "unknown game-log position")

    def test_46_plus_selection_uses_tie_priority(self):
        self.assertIsNone(selected_training_position({"PG": 45, "C": 45}))
        self.assertEqual(selected_training_position({"PG": 46, "C": 46}), "C")
        self.assertEqual(selected_training_position({"SG": 51, "C": 46}), "SG")

    def test_target_seasons_do_not_include_future_seasons(self):
        self.assertEqual(target_seasons_for_player(20, 72), [70, 71, 72])
        self.assertEqual(target_seasons_for_player(21, 72), [69, 70, 71, 72])

    def test_week_attribution_accepts_day_month_dates_when_needed(self):
        self.assertEqual(get_game_week("10/5/2026", 72), 2)
        self.assertEqual(get_game_week("5/10/2026", 72), 2)

    def test_training_dictionary_by_age_and_position(self):
        inferred, rows, counts = infer_training(
            {
                71: {1: {"PG": 48}, 2: {"SF": 48}},
                72: {1: {"PG": 48}, 2: {"SG": 48}},
            },
            current_age=20,
            current_season=72,
        )

        self.assertEqual(counts["PG"], 2)
        self.assertEqual(counts["SF"], 1)
        self.assertEqual(counts["SG"], 1)
        self.assertEqual(rows[0]["training"], "OD for 1")
        self.assertEqual(rows[1]["training"], "DR for 34")
        self.assertEqual(rows[2]["training"], "OD for 1")
        self.assertEqual(rows[3]["training"], "JR for 2")
        self.assertEqual([item.action.name for item in inferred], ["OD for 1", "DR for 34", "OD for 1", "JR for 2"])

    def test_age_20_pg_training_is_only_od_for_1(self):
        _, rows, _ = infer_training(
            {72: {1: {"PG": 48}}},
            current_age=20,
            current_season=72,
        )

        self.assertEqual(rows[0]["training"], "OD for 1")

    def test_skill_display_rounds_and_labels(self):
        rows = skill_display_rows({"JS": 7.49, "JR": 7.5, "OD": 20.2})

        self.assertEqual(rows[0][0]["skill"], "JS")
        self.assertEqual(rows[0][0]["rounded"], 7)
        self.assertEqual(rows[0][0]["label"], "respectable")
        self.assertEqual(rows[0][1]["rounded"], 8)
        self.assertEqual(rows[1][0]["label"], "legendary")

    def test_strong_nt_multiplier_boosts_training_gain(self):
        base = list(POSITION_PRESETS["PG"])
        weak = replay_training(
            base,
            [TrainingAction("OD for 1", 20)],
            height_cm=201,
            potential=8,
            training_multiplier=1.0,
        )
        strong = replay_training(
            base,
            [TrainingAction("OD for 1", 20)],
            height_cm=201,
            potential=8,
            training_multiplier=1.5,
        )

        self.assertGreater(strong[2], weak[2])

    def test_center_age_20_split_remainder_priority(self):
        _, rows, _ = infer_training(
            {72: {week: {"C": 48} for week in range(1, 5)}},
            current_age=20,
            current_season=72,
        )

        self.assertEqual(
            [row["training"] for row in rows],
            ["ID for 5", "IS for 5", "RB for 45", "ID for 5"],
        )

    def test_coachparrot_salary_formula_sample(self):
        self.assertAlmostEqual(listed_salary(POSITION_PRESETS["SG"], "SG"), 2758.35, places=2)


if __name__ == "__main__":
    unittest.main()
