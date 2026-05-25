from .base import LLMClient
from .claude_client import ClaudeClient
from .openai_client import OpenAIClient


def create_client(provider_type: str, api_key: str, base_url: str = "") -> LLMClient:
    if provider_type == "claude":
        return ClaudeClient(api_key=api_key, base_url=base_url)
    return OpenAIClient(
        api_key=api_key,
        base_url=base_url or "https://api.openai.com/v1",
    )
