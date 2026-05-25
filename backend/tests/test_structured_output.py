import unittest
from unittest import mock

from app.llm.base import LLMClient, LLMResponse
from app.llm.structured import get_structured_response
from app.engine.game_manager import FullResponseSchema
from app.memory.summarizer import ReflectionResult


class FakeClient(LLMClient):
    def __init__(self, content='{"inner_thought":"short","public_speech":"","action":{"vote_target":"Alpha"}}'):
        self.calls = []
        self.content = content

    async def chat(self, messages, model, temperature=0.7, max_tokens=1024, json_mode=False):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
            }
        )
        return LLMResponse(
            content=self.content,
            model=model,
        )


class RateLimitThenSuccessClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.failures_left = 1

    async def chat(self, messages, model, temperature=0.7, max_tokens=1024, json_mode=False):
        if self.failures_left:
            self.failures_left -= 1
            raise RuntimeError("Error code: 429 - rate_limit_error")
        return await super().chat(messages, model, temperature, max_tokens, json_mode)


class StructuredOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_response_passes_expanded_token_budget_and_short_output_instruction(self):
        client = FakeClient()

        result = await get_structured_response(
            client,
            "mock-model",
            "system",
            "user",
            FullResponseSchema,
            max_tokens=2048,
        )

        self.assertEqual(result["inner_thought"], "short")
        self.assertEqual(client.calls[0]["max_tokens"], 2048)
        self.assertTrue(client.calls[0]["json_mode"])
        self.assertIn("inner_thought 控制在 180 字以内", client.calls[0]["messages"][1]["content"])
        self.assertIn("private_note 控制在 220 字以内", client.calls[0]["messages"][1]["content"])
        self.assertIn("同标签便签会被系统覆盖更新", client.calls[0]["messages"][1]["content"])
        self.assertIn("delete_notes 必须填写为数组，固定填 []", client.calls[0]["messages"][1]["content"])

    async def test_reflection_schema_does_not_receive_in_game_note_instruction(self):
        client = FakeClient(
            content=(
                '{"reflection":"good review","key_moments":[],"strategy_updates":[],'
                '"useful_takeaways":[],"role_summary_update":{}}'
            )
        )

        result = await get_structured_response(
            client,
            "mock-model",
            "system",
            "user",
            ReflectionResult,
            max_tokens=2048,
        )

        prompt = client.calls[0]["messages"][1]["content"]
        self.assertEqual(result["reflection"], "good review")
        self.assertNotIn("private_note", prompt)
        self.assertNotIn("delete_notes", prompt)
        self.assertIn("字段必须匹配本次要求", prompt)

    async def test_rate_limit_error_retries_before_failing(self):
        client = RateLimitThenSuccessClient()

        with mock.patch("app.llm.structured.asyncio.sleep", mock.AsyncMock()) as sleep:
            result = await get_structured_response(
                client,
                "mock-model",
                "system",
                "user",
                FullResponseSchema,
                max_tokens=2048,
            )

        self.assertEqual(result["inner_thought"], "short")
        sleep.assert_awaited_once()
