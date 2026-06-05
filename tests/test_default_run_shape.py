from __future__ import annotations

import io
import unittest

from providers_discuss.configure import _write_setup_sequence, configure_from_answers
from providers_discuss.public_config import example_public_config, validate_public_config


def _enabled_seats(config: dict[str, object]) -> list[dict[str, object]]:
    seats = config["seats"]
    assert isinstance(seats, list)
    return [seat for seat in seats if isinstance(seat, dict) and seat.get("enabled", True) is not False]


class DefaultRunShapeTests(unittest.TestCase):
    def test_example_public_config_defaults_to_gpt_and_claude_team_agents(self) -> None:
        # Given: the package example config is the source for config-template defaults.
        config = example_public_config()

        # When: the enabled default seats are inspected.
        seats = _enabled_seats(config)

        # Then: the default run shape is the CEO-approved two-seat topology.
        self.assertEqual([seat["seat_id"] for seat in seats], ["gpt", "claude_team"])
        self.assertEqual(seats[0]["provider"], "openai")
        self.assertEqual(seats[0]["model"], "gpt-5.5")
        self.assertEqual(seats[0]["reasoning_effort"], "xhigh")
        self.assertEqual(seats[1]["transport"], "claude_k_team_agents")
        self.assertEqual(seats[1]["model"], "claude-opus-4-8")
        self.assertEqual(seats[1]["reasoning_effort"], "max")
        team_agents = seats[1]["team_agents"]
        assert isinstance(team_agents, dict)
        self.assertNotIn("team_agent_count", team_agents)
        self.assertIn("Ideation Catalyst", team_agents["roles"])

    def test_validate_public_config_rejects_team_agents_without_ideation(self) -> None:
        # Given: a Claude Team Agents config that violates the default-shape contract.
        config = example_public_config()
        seats = _enabled_seats(config)
        team_agents = seats[1]["team_agents"]
        assert isinstance(team_agents, dict)
        team_agents["roles"] = ["Research Synthesizer", "System Architect"]

        # When: the public config validator runs.
        result = validate_public_config(config)
        blocker_checks = {item["check"] for item in result["blockers"]}

        # Then: the invalid shape is rejected with specific blockers.
        self.assertEqual(result["status"], "fail")
        self.assertIn("seat_2_team_agents_ideation_role", blocker_checks)

    def test_configure_from_empty_answers_preserves_default_two_seat_shape(self) -> None:
        # Given: non-interactive configure receives an empty answers file.
        answers: dict[str, object] = {}

        # When: configure builds the config from defaults.
        config = configure_from_answers(answers)
        seats = _enabled_seats(config)

        # Then: the CEO does not need to restate the default run shape.
        self.assertEqual([seat["seat_id"] for seat in seats], ["gpt", "claude_team"])
        self.assertEqual(seats[0]["model"], "gpt-5.5")
        self.assertEqual(seats[0]["reasoning_effort"], "xhigh")
        self.assertEqual(seats[1]["model"], "claude-opus-4-8")
        team_agents = seats[1]["team_agents"]
        assert isinstance(team_agents, dict)
        self.assertIn("Ideation Catalyst", team_agents["roles"])
        self.assertNotIn("team_agent_count", team_agents)

    def test_setup_sequence_mentions_default_two_seat_shape(self) -> None:
        # Given: the interactive configure setup sequence is shown before run-shape prompts.
        stdout = io.StringIO()

        # When: the sequence is rendered.
        _write_setup_sequence(stdout)
        text = stdout.getvalue()

        # Then: the user sees the default without needing to ask.
        self.assertIn("Default run shape", text)
        self.assertIn("gpt-5.5", text)
        self.assertIn("xhigh", text)
        self.assertIn("Claude Team Agents", text)
        self.assertIn("claude-opus-4-8", text)
        self.assertIn("max", text)
        self.assertIn("Ideation Catalyst", text)
        self.assertNotIn("teammate guidance", text)

    def test_configure_cli_handlers_live_in_configure_cli_module(self) -> None:
        # Given: configure/config-template/validate-config are a cohesive CLI slice.
        from providers_discuss import cli_configure

        # When/Then: the overlarge CLI module can delegate those commands.
        self.assertTrue(callable(cli_configure.cmd_config_template))
        self.assertTrue(callable(cli_configure.cmd_validate_config))
        self.assertTrue(callable(cli_configure.cmd_configure))


if __name__ == "__main__":
    unittest.main()
