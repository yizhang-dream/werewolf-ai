import asyncio
import json
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.engine.game_manager import GameManager
from .game import _games

router = APIRouter()


async def _event_generator(request: Request, game_id: str):
    if game_id not in _games:
        yield {"event": "error", "data": json.dumps({"message": "Game not found"})}
        return

    gm: GameManager = _games[game_id]
    queue = gm.event_queue

    while True:
        if await request.is_disconnected():
            break
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30)
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"], ensure_ascii=False),
            }
            if event["event"] == "game_saved":
                break
        except asyncio.TimeoutError:
            yield {"event": "ping", "data": ""}


@router.get("/{game_id}")
async def sse_endpoint(game_id: str, request: Request):
    return EventSourceResponse(_event_generator(request, game_id))
