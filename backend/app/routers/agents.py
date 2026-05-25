from fastapi import APIRouter, HTTPException
from app.memory.store import load_agent_memory, save_agent_memory, list_agents

router = APIRouter()


@router.get("")
async def get_agents():
    agents = list_agents()
    agents.sort(key=_latest_lesson_game_id, reverse=True)
    return [
        _agent_list_item(a)
        for a in agents
    ]


def _agent_list_item(memory):
    last_lesson = max(memory.lessons, key=lambda lesson: lesson.game_id, default=None)
    return {
        "name": memory.agent_name,
        "personality": memory.personality,
        "total_games": memory.total_games,
        "wins": memory.wins,
        "losses": memory.losses,
        "strategies": memory.strategies,
        "lesson_count": len(memory.lessons),
        "last_game_id": last_lesson.game_id if last_lesson else "",
        "last_role": last_lesson.role if last_lesson else "",
        "last_won": last_lesson.won if last_lesson else None,
        "last_rounds_played": last_lesson.rounds_played if last_lesson else 0,
        "last_reflection": last_lesson.reflection if last_lesson else "",
    }


def _latest_lesson_game_id(memory) -> str:
    return max((lesson.game_id for lesson in memory.lessons), default="")


@router.get("/{name}")
async def get_agent(name: str):
    memory = load_agent_memory(name)
    return memory.model_dump()


@router.delete("/{name}")
async def reset_agent(name: str):
    from app.models.agent import AgentMemory
    memory = AgentMemory(agent_name=name)
    save_agent_memory(memory)
    return {"ok": True}
