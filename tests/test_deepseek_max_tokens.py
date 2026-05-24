import unittest
from types import SimpleNamespace

from wq_workflow.deepseek_client import DEEPSEEK_MAX_OUTPUT_TOKENS, DeepSeekClient
from wq_workflow.models import WorkflowConfig


_DEFAULT_RESPONSE = object()


class _FakeCompletions:
    def __init__(self, finish_reason: str = "stop", content: str = "ok", response=_DEFAULT_RESPONSE) -> None:
        self.calls = []
        self.finish_reason = finish_reason
        self.content = content
        self.response = response

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.response is not _DEFAULT_RESPONSE:
            return self.response
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message, finish_reason=self.finish_reason)
        return SimpleNamespace(choices=[choice])


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = _FakeChat(completions)
        self.closed = False

    async def close(self):
        self.closed = True


class _TestDeepSeekClient(DeepSeekClient):
    def __init__(self, completions: _FakeCompletions) -> None:
        super().__init__(WorkflowConfig(deepseek_api_key="test-key", deepseek_max_tokens=123))
        self.completions = completions
        self.fake_client = _FakeClient(self.completions)

    async def _client(self):
        return self.fake_client


class DeepSeekMaxTokensTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_uses_max_output_tokens_when_override_is_passed(self) -> None:
        completions = _FakeCompletions()
        client = _TestDeepSeekClient(completions)

        await client.chat("system", "prompt", max_tokens=8000)

        self.assertEqual(DEEPSEEK_MAX_OUTPUT_TOKENS, completions.calls[0]["max_tokens"])
        self.assertTrue(client.fake_client.closed)

    async def test_chat_uses_max_output_tokens_by_default(self) -> None:
        completions = _FakeCompletions()
        client = _TestDeepSeekClient(completions)

        await client.chat("system", "prompt")

        self.assertEqual(DEEPSEEK_MAX_OUTPUT_TOKENS, completions.calls[0]["max_tokens"])

    async def test_length_finish_reason_does_not_retry_with_larger_budget(self) -> None:
        completions = _FakeCompletions(finish_reason="length", content="")
        client = _TestDeepSeekClient(completions)

        result = await client.chat("system", "prompt", max_tokens=8000)

        self.assertEqual("", result)
        self.assertEqual(1, len(completions.calls))
        self.assertEqual(DEEPSEEK_MAX_OUTPUT_TOKENS, completions.calls[0]["max_tokens"])

    async def test_empty_response_raises_readable_error(self) -> None:
        completions = _FakeCompletions(response=None)
        client = _TestDeepSeekClient(completions)

        with self.assertRaisesRegex(RuntimeError, "empty response"):
            await client.chat("system", "prompt")

        self.assertTrue(client.fake_client.closed)

    async def test_empty_choices_raises_readable_error(self) -> None:
        completions = _FakeCompletions(response=SimpleNamespace(choices=[]))
        client = _TestDeepSeekClient(completions)

        with self.assertRaisesRegex(RuntimeError, "no choices"):
            await client.chat("system", "prompt")

        self.assertTrue(client.fake_client.closed)

    async def test_missing_message_raises_readable_error(self) -> None:
        completions = _FakeCompletions(response=SimpleNamespace(choices=[SimpleNamespace(message=None)]))
        client = _TestDeepSeekClient(completions)

        with self.assertRaisesRegex(RuntimeError, "without message"):
            await client.chat("system", "prompt")

        self.assertTrue(client.fake_client.closed)


if __name__ == "__main__":
    unittest.main()
