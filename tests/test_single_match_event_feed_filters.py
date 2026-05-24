import unittest

import web_tool


class SingleMatchEventFeedFilterTemplateTests(unittest.TestCase):
    def test_event_feed_renders_player_and_type_filter_mounts(self):
        self.assertIn('id="eventPlayerFilter"', web_tool.REPORT_HTML)
        self.assertIn('id="eventTypeFilter"', web_tool.REPORT_HTML)
        self.assertIn("setupEventFeedFilters();", web_tool.REPORT_HTML)

    def test_event_feed_type_options_include_requested_categories(self):
        expected = [
            "Passes",
            "Shots Taken - Close",
            "Shots Taken - Mid",
            "Shots Taken - 3PT",
            "Rebound",
            "Turnover",
            "Score",
            "Miss",
            "Assist",
            "Block",
            "Foul",
        ]

        for label in expected:
            self.assertIn(f'label: "{label}"', web_tool.REPORT_HTML)

    def test_event_feed_filters_preserve_all_selected_default(self):
        self.assertIn(
            "selectedPlayers.size === 0 || selectedPlayers.size === eventPlayerFilterOptions.length",
            web_tool.REPORT_HTML,
        )
        self.assertIn(
            "selectedTypes.size === 0 || selectedTypes.size === eventTypeOptions.length",
            web_tool.REPORT_HTML,
        )

    def test_event_feed_type_filters_are_role_aware(self):
        self.assertIn("function eventTypeActorKeys(ev, typeKey)", web_tool.REPORT_HTML)
        self.assertIn('["passes", "assist"].includes(typeKey)', web_tool.REPORT_HTML)
        self.assertIn("ev.assistant", web_tool.REPORT_HTML)
        self.assertNotIn('keys.add("passes");\n      } else if (ev.event_type === "foul")', web_tool.REPORT_HTML)


if __name__ == "__main__":
    unittest.main()
