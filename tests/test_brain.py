import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis import brain as module


class HybridTests(unittest.TestCase):
    def setUp(self):
        self.brain = module.Brain()
        self.brain._local = Mock(return_value="Local answer")
        self.brain._cloud = Mock(return_value="Cloud answer")

    def test_simple_stays_local(self):
        self.assertEqual(self.brain.think("Hello"), "Local answer")
        self.brain._cloud.assert_not_called()

    def test_harder_routes_cloud(self):
        self.assertEqual(self.brain.think("Debug my Python code"), "Cloud answer")
        self.brain._local.assert_not_called()

    def test_local_failure_uses_cloud(self):
        self.brain._local.side_effect = TimeoutError
        self.assertEqual(self.brain.think("Hello"), "Cloud answer")
        self.assertEqual(self.brain.last_backend, "cloud")

    def test_cloud_failure_uses_local(self):
        self.brain._cloud.side_effect = TimeoutError
        self.assertEqual(self.brain.think("Prove this theorem"), "Local answer")

    def test_forced_local_never_cloud(self):
        self.brain._local.side_effect = TimeoutError
        self.brain.think("Use local: debug this code")
        self.brain._cloud.assert_not_called()
        self.assertEqual(len(self.brain.history), 1)

    def test_forced_cloud(self):
        self.assertEqual(self.brain.think("use cloud hello"), "Cloud answer")
        self.brain._local.assert_not_called()

    def test_failed_turn_not_saved(self):
        self.brain._local.side_effect = TimeoutError
        self.brain._cloud.side_effect = TimeoutError
        self.brain.think("Hello")
        self.assertEqual(len(self.brain.history), 1)

    def test_history_retains_complete_pairs(self):
        for index in range(12):
            self.brain.think("Hello " + str(index))
        self.assertEqual(self.brain.history[0]["role"], "system")
        self.assertEqual([m["role"] for m in self.brain.history[1:]], ["user", "assistant"] * 5)

    def test_empty_prefix_makes_no_request(self):
        self.brain.think("use cloud")
        self.brain._cloud.assert_not_called()
        self.brain._local.assert_not_called()

    def test_local_payload_and_empty_answer(self):
        brain = module.Brain()
        response = Mock()
        response.json.return_value = {"message": {"content": "  hello  "}}
        with patch.object(module.requests, "post", return_value=response) as post:
            self.assertEqual(brain._local([]), "hello")
            self.assertFalse(post.call_args.kwargs["json"]["think"])
            response.json.return_value = {"message": {"content": ""}}
            with self.assertRaises(ValueError):
                brain._local([])


if __name__ == "__main__":
    unittest.main()
