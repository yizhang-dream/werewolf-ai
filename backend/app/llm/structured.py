import asyncio
import json
import logging
from typing import Type
from pydantic import BaseModel, ValidationError
from .base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_BACKOFF_SECONDS = [3, 6, 12, 24]


async def get_structured_response(
    client: LLMClient,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: Type[BaseModel],
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict:
    output_instruction = _build_output_instruction(schema)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_prompt + output_instruction,
        },
    ]

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp: LLMResponse = await _chat_with_rate_limit_retry(
                client,
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.info("LLM raw response (attempt %d, model=%s): %s", attempt + 1, model, resp.content[:500])

            if not resp.content or not resp.content.strip():
                logger.warning("LLM returned empty content (attempt %d)", attempt + 1)
                if attempt < MAX_RETRIES:
                    messages.append({"role": "user", "content": "你的回复为空，请重新回复，只输出JSON。"})
                continue

            # Strip markdown code fences if present
            content = resp.content.strip()
            if content.startswith("```"):
                first_newline = content.index("\n") + 1 if "\n" in content else 3
                content = content[first_newline:]
                if content.endswith("```"):
                    content = content[:-3].strip()

            parsed = json.loads(content)
            validated = schema(**parsed)
            return validated.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Structured output parse error (attempt %d): %s | raw: %s", attempt + 1, e, resp.content[:200] if resp.content else "EMPTY")
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({
                    "role": "user",
                    "content": f"你的回复不是有效的JSON或不符合格式要求。错误：{e}\n请重新回复，只输出一个完整 JSON 对象。大幅压缩 inner_thought，不要复盘长篇推理，不要 Markdown，不要代码块。",
                })
        except Exception as e:
            logger.error("LLM call failed (attempt %d): %s: %s", attempt + 1, type(e).__name__, e)
            if attempt >= MAX_RETRIES:
                raise

    raise RuntimeError(f"Failed to get valid structured output after {MAX_RETRIES + 1} attempts")


def _build_output_instruction(schema: Type[BaseModel]) -> str:
    fields = set(schema.model_fields)
    if {"inner_thought", "public_speech", "private_note", "delete_notes"}.issubset(fields):
        return (
            "\n\n结构化输出要求：只输出一个完整 JSON 对象；inner_thought 控制在 180 字以内；"
            "public_speech 控制在 220 字以内；private_note 控制在 220 字以内，默认应填写，"
            "并尽量以固定标签开头：身份工作区：/战术计划：/假身份：/狼队计划：/技能计划：；"
            "同标签便签会被系统覆盖更新，请输出完整新版内容。delete_notes 必须填写为数组，固定填 []；"
            "不要用删除编号来修正便签。即使暂无新变化，也要简短写下你仍坚持的核心判断或下一步计划；"
            "不要使用 Markdown 列表或代码块。"
        )

    return "\n\n结构化输出要求：只输出一个完整 JSON 对象，字段必须匹配本次要求；不要使用 Markdown 列表或代码块。"


async def _chat_with_rate_limit_retry(
    client: LLMClient,
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return await client.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= RATE_LIMIT_RETRIES:
                raise

            delay = RATE_LIMIT_BACKOFF_SECONDS[min(attempt, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)]
            logger.warning("LLM rate limited; retrying in %s seconds (attempt %d/%d): %s", delay, attempt + 1, RATE_LIMIT_RETRIES, exc)
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable")


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    text = str(exc).lower()
    return "rate_limit" in text or "rate limit" in text or "429" in text or "速率限制" in text
