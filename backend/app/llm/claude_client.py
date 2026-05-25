import anthropic
from .base import LLMClient, LLMResponse


class ClaudeClient(LLMClient):
    def __init__(self, api_key: str, base_url: str = ""):
        kwargs = {"api_key": api_key, "timeout": 120.0}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.AsyncAnthropic(**kwargs)

    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        system = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system += m["content"] + "\n"
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system.strip()

        if json_mode and chat_messages:
            chat_messages[-1]["content"] = (
                chat_messages[-1]["content"]
                + "\n\n请只输出JSON，不要输出任何其他内容。"
            )

        kwargs["messages"] = chat_messages
        resp = await self.client.messages.create(**kwargs)
        # Find the text content block (skip thinking blocks)
        text = ""
        if resp.content:
            for block in resp.content:
                if hasattr(block, "text") and block.text:
                    text = block.text
                    break
        return LLMResponse(
            content=text,
            usage={"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens} if resp.usage else {},
            model=resp.model,
        )
