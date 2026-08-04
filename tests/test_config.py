from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pipeline.config import get_settings


class SettingsWindowTests(unittest.TestCase):
    def test_window_times_are_read_from_environment(self) -> None:
        with patch("pipeline.config.load_env"), patch.dict(
            os.environ,
            {
                "BRIEF_WINDOW_START": "8:45",
                "BRIEF_WINDOW_END": "09:55",
            },
            clear=False,
        ):
            settings = get_settings()

        self.assertEqual(settings.window_start, "08:45")
        self.assertEqual(settings.window_end, "09:55")

    def test_invalid_window_time_uses_default(self) -> None:
        with patch("pipeline.config.load_env"), patch.dict(
            os.environ,
            {
                "BRIEF_WINDOW_START": "25:00",
                "BRIEF_WINDOW_END": "not-a-time",
            },
            clear=False,
        ):
            settings = get_settings()

        self.assertEqual(settings.window_start, "08:00")
        self.assertEqual(settings.window_end, "08:00")


if __name__ == "__main__":
    unittest.main()
