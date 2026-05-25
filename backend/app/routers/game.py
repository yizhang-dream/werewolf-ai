import asyncio
import random
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.engine.game_manager import GameManager
from app.models.game import (
    DEFAULT_AI_NAMES,
    DEFAULT_PERSONALITIES,
    GAME_TEMPLATES,
    GameRules,
    GameState,
    Phase,
    Player,
    Role,
    derive_default_rules,
)
from app.routers.settings import get_all_providers, get_provider

router = APIRouter()

_games: dict[str, GameManager] = {}
PREFERRED_DEFAULT_MODEL = "glm-5.1"


class CreateGameInput(BaseModel):
    players: list[dict]
    roles: list[str]
    auto_advance: bool = False
    step_delay: float = 2.0
    rules: GameRules | None = None


def _resolve_provider_defaults(llm_provider: str = "", model_name: str = "") -> tuple[str, str]:
    if llm_provider:
        provider = get_provider(llm_provider)
        resolved_model = model_name or _default_model_for_provider(provider.models)
        return provider.name, resolved_model

    from app.routers.settings import _load_settings
    settings = _load_settings()
    default_name = settings.default_provider

    providers = get_all_providers()
    if not providers:
        raise HTTPException(400, "Please configure at least one LLM Provider first.")

    # Use the user's chosen default, or the first provider
    if default_name:
        for p in providers:
            if p.name == default_name:
                resolved_model = model_name or _default_model_for_provider(p.models)
                return p.name, resolved_model

    provider = providers[0]
    resolved_model = model_name or _default_model_for_provider(provider.models)
    return provider.name, resolved_model


def _default_model_for_provider(models: list[str]) -> str:
    return PREFERRED_DEFAULT_MODEL if PREFERRED_DEFAULT_MODEL in models else (models[0] if models else "")


@router.post("")
async def create_game(inp: CreateGameInput):
    if len(inp.players) < 4:
        raise HTTPException(400, "Need at least 4 players")
    if len(inp.players) != len(inp.roles):
        raise HTTPException(
            400,
            f"Player count ({len(inp.players)}) must match role count ({len(inp.roles)})",
        )

    roles = [Role(role) for role in inp.roles]
    game_id = f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    shuffled_roles = list(roles)
    random.shuffle(shuffled_roles)

    players = []
    for index, player_config in enumerate(inp.players):
        llm_provider, model_name = _resolve_provider_defaults(
            player_config.get("llm_provider", ""),
            player_config.get("model_name", ""),
        )
        players.append(
            Player(
                name=player_config["name"],
                role=shuffled_roles[index],
                personality=player_config.get("personality", ""),
                llm_provider=llm_provider,
                model_name=model_name,
            )
        )

    state = GameState(
        game_id=game_id,
        players=players,
        auto_advance=inp.auto_advance,
        step_delay=inp.step_delay,
        rules=inp.rules or derive_default_rules(roles),
    )

    gm = GameManager(state)
    _games[game_id] = gm
    return {"game_id": game_id, "players": [player.model_dump() for player in players], "rules": state.rules.model_dump()}


@router.get("")
async def list_games():
    from app.memory.store import list_game_logs

    seen: set[str] = set()
    result: list[dict] = []

    # In-progress games from memory
    for game_id, gm in _games.items():
        state = gm.state
        result.append({
            "game_id": game_id,
            "winner": state.winner,
            "finished_at": state.finished_at,
            "created_at": state.created_at,
            "player_count": len(state.players),
            "round_number": state.round_number,
        })
        seen.add(game_id)

    # Completed games from disk (skip if already listed from memory)
    for log in list_game_logs():
        gid = log.get("game_id", "")
        if gid in seen:
            continue
        result.append({
            "game_id": gid,
            "winner": log.get("winner"),
            "finished_at": log.get("finished_at"),
            "created_at": log.get("created_at"),
            "player_count": len(log.get("players", [])),
            "round_number": log.get("round_number", 0),
        })

    return result


@router.get("/templates/list")
async def list_templates():
    return [template.model_dump() for template in GAME_TEMPLATES]


@router.post("/templates/quick-start")
async def quick_start(template_id: str = "9p_hunter", auto_advance: bool = False, step_delay: float = 2.0):
    template = next((item for item in GAME_TEMPLATES if item.id == template_id), None)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    llm_provider, model_name = _resolve_provider_defaults()
    game_id = f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    shuffled_roles = list(template.roles)
    random.shuffle(shuffled_roles)

    players = []
    for index in range(len(template.roles)):
        players.append(
            Player(
                name=DEFAULT_AI_NAMES[index] if index < len(DEFAULT_AI_NAMES) else f"玩家{index + 1}",
                role=shuffled_roles[index],
                personality=DEFAULT_PERSONALITIES[index % len(DEFAULT_PERSONALITIES)],
                is_ai=True,
                llm_provider=llm_provider,
                model_name=model_name,
            )
        )

    state = GameState(
        game_id=game_id,
        players=players,
        auto_advance=auto_advance,
        step_delay=step_delay,
        rules=template.rules.model_copy(deep=True),
    )

    gm = GameManager(state)
    _games[game_id] = gm
    asyncio.create_task(gm.run_game())

    return {
        "game_id": game_id,
        "template": template.name,
        "players": [player.model_dump() for player in players],
        "rules": state.rules.model_dump(),
    }


@router.get("/{game_id}")
async def get_game(game_id: str):
    if game_id not in _games:
        raise HTTPException(404, "Game not found")
    return _games[game_id].state.model_dump()


@router.post("/{game_id}/start")
async def start_game(game_id: str):
    if game_id not in _games:
        raise HTTPException(404, "Game not found")

    gm = _games[game_id]
    if gm.state.phase != Phase.SETUP:
        raise HTTPException(400, "Game already started")

    asyncio.create_task(gm.run_game())
    return {"status": "started"}


@router.get("/{game_id}/full")
async def get_game_full(game_id: str):
    if game_id not in _games:
        raise HTTPException(404, "Game not found")
    return _games[game_id].state.model_dump()


@router.get("/{game_id}/log")
async def get_game_log(game_id: str):
    # In-progress game in memory
    if game_id in _games:
        return _games[game_id].state.model_dump()

    # Completed game on disk
    from app.memory.store import load_game_log

    log = load_game_log(game_id)
    if log is None:
        raise HTTPException(404, "Game log not found")
    return log
