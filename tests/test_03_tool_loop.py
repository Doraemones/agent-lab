import io
import runpy
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "llm_practice" / "03_tool_loop.py"


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.index = 0
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        return {
            "content": self.content,
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool.id,
                    "type": tool.type,
                    "index": tool.index,
                    "function": {
                        "name": tool.function.name,
                        "arguments": tool.function.arguments,
                    },
                }
                for tool in (self.tool_calls or [])
            ]
            or None,
        }


class FakeCompletions:
    def __init__(self, final_content="The result is 3."):
        self.tool_result_counts = []
        self.responses = [
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_time",
                        "get_current_time",
                        '{"timezone": "Asia/Shanghai"}',
                    )
                ]
            ),
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_calculator",
                        "calculator",
                        '{"expression": "1 + 2"}',
                    )
                ]
            ),
            FakeMessage(content=final_content, tool_calls=None),
        ]

    def create(self, **kwargs):
        messages = kwargs["messages"]
        self.tool_result_counts.append(
            sum(
                1
                for message in messages
                if isinstance(message, dict) and message.get("role") == "tool"
            )
        )
        response = self.responses[len(self.tool_result_counts) - 1]
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=response)]
        )


class ToolLoopTest(unittest.TestCase):
    def test_executes_sequential_tool_calls_until_final_answer(self):
        completions = FakeCompletions()
        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=completions)
        )
        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = lambda **kwargs: fake_client

        with patch.dict("sys.modules", {"openai": fake_openai}):
            with redirect_stdout(io.StringIO()):
                runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

        self.assertEqual(completions.tool_result_counts, [0, 1, 2])

    def test_configures_windows_stdout_for_unicode_answers(self):
        completions = FakeCompletions(final_content="Done \U0001f550")
        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=completions)
        )
        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = lambda **kwargs: fake_client
        output = io.BytesIO()
        gbk_stdout = io.TextIOWrapper(output, encoding="gbk")

        with patch.dict("sys.modules", {"openai": fake_openai}):
            with patch("sys.stdout", gbk_stdout):
                runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

        gbk_stdout.flush()
        self.assertIn("Done", output.getvalue().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
