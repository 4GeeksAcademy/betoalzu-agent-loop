import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import agent


class AgentLoopTests(unittest.TestCase):
    def test_tool_result_returns_to_history_and_log_is_append_only(self) -> None:
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="list_inventory", arguments="{}"
            ),
        )
        tool_message = SimpleNamespace(
            tool_calls=[tool_call],
            content=None,
            model_dump=lambda exclude_none: {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "list_inventory", "arguments": "{}"},
                    }
                ],
            },
        )
        final_message = SimpleNamespace(
            tool_calls=None,
            content="Hay 4 productos.",
            model_dump=lambda exclude_none: {
                "role": "assistant",
                "content": "Hay 4 productos.",
            },
        )
        responses = iter([tool_message, final_message])

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        return SimpleNamespace(
                            choices=[
                                SimpleNamespace(message=next(responses))
                            ]
                        )

        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "conversation_log.csv"
            history = [{"role": "system", "content": "system"}]
            with (
                patch.object(agent, "LOG_FILE", log_file),
                patch.object(agent, "api_request", return_value=[{"name": "Coffee"}]) as api_call,
            ):
                answer = agent.run_turn(FakeClient(), history, "Lista el inventario")
                agent.log_event("user", "segunda sesión")

            self.assertEqual(answer, "Hay 4 productos.")
            self.assertEqual(api_call.call_args.args, ("/inventory",))
            self.assertIn(
                {"role": "tool", "tool_call_id": "call-1", "content": '[{"name": "Coffee"}]'},
                history,
            )
            with log_file.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(
                list(rows[0].keys()), ["actor", "message", "tool_call", "timestamp"]
            )
            self.assertEqual([row["actor"] for row in rows], ["user", "tool", "tool", "agent", "user"])
            self.assertEqual(rows[1]["tool_call"], "list_inventory")


if __name__ == "__main__":
    unittest.main()
