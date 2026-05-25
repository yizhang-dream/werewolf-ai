import json
from collections import Counter

from app.config import AGENTS_DIR, GAMES_DIR
from app.models.agent import AgentMemory, RetrievedGameMemory
from app.models.game import ROLE_NAMES_ZH, Player, WOLF_ROLES

WOLF_ROLE_VALUES = {role.value for role in WOLF_ROLES}
ROLE_NAME_BY_VALUE = {role.value: name for role, name in ROLE_NAMES_ZH.items()}


def load_agent_memory(name: str) -> AgentMemory:
    path = AGENTS_DIR / f"{name}.json"
    if not path.exists():
        return AgentMemory(agent_name=name)
    return AgentMemory.model_validate_json(path.read_text(encoding="utf-8"))


def save_agent_memory(memory: AgentMemory) -> None:
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = AGENTS_DIR / f"{memory.agent_name}.json"
    path.write_text(memory.model_dump_json(indent=2), encoding="utf-8")


def list_agents() -> list[AgentMemory]:
    if not AGENTS_DIR.exists():
        return []

    result = []
    for file_path in AGENTS_DIR.glob("*.json"):
        result.append(AgentMemory.model_validate_json(file_path.read_text(encoding="utf-8")))
    return result


def save_game_log(game_id: str, data: dict) -> None:
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    path = GAMES_DIR / f"{game_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_game_log(game_id: str) -> dict | None:
    path = GAMES_DIR / f"{game_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_game_logs() -> list[dict]:
    if not GAMES_DIR.exists():
        return []

    result = []
    files = sorted(GAMES_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for file_path in files:
        result.append(json.loads(file_path.read_text(encoding="utf-8")))
    return result


def find_agent_game_logs(agent_name: str) -> list[dict]:
    result: list[dict] = []
    for log in list_game_logs():
        if any(player.get("name") == agent_name for player in log.get("players", [])):
            result.append(log)
    return result


def retrieve_relevant_memories(
    agent_name: str,
    current_role: str,
    current_players: list[Player],
    memory: AgentMemory | None = None,
    limit: int = 3,
) -> list[RetrievedGameMemory]:
    history = find_agent_game_logs(agent_name)
    if not history:
        return []

    memory = memory or load_agent_memory(agent_name)
    lessons_by_game = {lesson.game_id: lesson for lesson in memory.lessons}
    current_counts = _count_roles_from_players(current_players)
    current_player_count = len(current_players)

    retrieved: list[RetrievedGameMemory] = []
    for recency_index, log in enumerate(history):
        player = _find_player(log, agent_name)
        if not player:
            continue

        role_value = _role_value(player.get("role"))
        role_counts = _count_roles_from_log(log)
        score = _memory_score(
            current_role=current_role,
            current_player_count=current_player_count,
            current_role_counts=current_counts,
            past_role=role_value,
            past_player_count=len(log.get("players", [])),
            past_role_counts=role_counts,
            recency_index=recency_index,
        )

        if score <= 0:
            continue

        lesson = lessons_by_game.get(log.get("game_id", ""))
        retrieved.append(
            RetrievedGameMemory(
                game_id=log.get("game_id", ""),
                role=role_value,
                score=score,
                won=_did_agent_win(role_value, log.get("winner")),
                player_count=len(log.get("players", [])),
                role_config=_format_role_counts(role_counts),
                rounds_played=int(log.get("round_number") or 0),
                survived_to_end=player.get("status") == "alive",
                final_status=player.get("status", ""),
                winner=log.get("winner", ""),
                summary=_build_memory_summary(log, agent_name, lesson),
                key_moments=(lesson.key_moments[:3] if lesson else _extract_key_moments(log, agent_name, limit=3)),
                useful_takeaways=lesson.useful_takeaways[:3] if lesson else [],
            )
        )

    retrieved.sort(key=lambda item: item.score, reverse=True)
    return retrieved[:limit]


def _memory_score(
    current_role: str,
    current_player_count: int,
    current_role_counts: dict[str, int],
    past_role: str,
    past_player_count: int,
    past_role_counts: dict[str, int],
    recency_index: int,
) -> float:
    score = 0.0

    if current_role == past_role:
        score += 50.0

    player_count_gap = abs(current_player_count - past_player_count)
    if player_count_gap == 0:
        score += 20.0
    else:
        score += max(0.0, 12.0 - player_count_gap * 3.0)

    score += _role_overlap_score(current_role_counts, past_role_counts)
    score += max(0.0, 10.0 - recency_index * 2.0)
    return round(score, 2)


def _role_overlap_score(current_role_counts: dict[str, int], past_role_counts: dict[str, int]) -> float:
    if not current_role_counts or not past_role_counts:
        return 0.0

    overlap = 0
    total = 0
    for role, count in current_role_counts.items():
        total += count
        overlap += min(count, past_role_counts.get(role, 0))

    if total == 0:
        return 0.0
    return round(20.0 * (overlap / total), 2)


def _find_player(log: dict, agent_name: str) -> dict | None:
    for player in log.get("players", []):
        if player.get("name") == agent_name:
            return player
    return None


def _build_memory_summary(log: dict, agent_name: str, lesson) -> str:
    player = _find_player(log, agent_name)
    if not player:
        return ""

    role_value = _role_value(player.get("role"))
    outcome = "won" if _did_agent_win(role_value, log.get("winner")) else "lost"
    parts = [
        f"{outcome} as {role_value} in a {len(log.get('players', []))}-player game",
        f"board: {_format_role_counts(_count_roles_from_log(log))}",
        f"rounds: {int(log.get('round_number') or 0)}",
        f"survived: {'yes' if player.get('status') == 'alive' else 'no'}",
    ]

    own_speech = _extract_agent_speeches(log, agent_name, limit=2)
    if own_speech:
        parts.append("own calls: " + " | ".join(own_speech))

    if lesson and lesson.reflection:
        parts.append("reflection: " + lesson.reflection.strip())

    return "; ".join(parts)


def _extract_agent_speeches(log: dict, agent_name: str, limit: int = 2) -> list[str]:
    result: list[str] = []
    speeches = log.get("speeches", [])
    for speech in speeches:
        if speech.get("speaker") != agent_name:
            continue

        public_speech = (speech.get("public_speech") or "").strip()
        if public_speech:
            result.append(f"R{speech.get('round_number', '?')} {public_speech}")
        if len(result) >= limit:
            break
    return result


def _extract_key_moments(log: dict, agent_name: str, limit: int = 3) -> list[str]:
    results: list[str] = []

    for item in log.get("history", []):
        event_type = item.get("type")
        if event_type == "seer_check" and item.get("player") == agent_name:
            results.append(
                f"R{item.get('round', '?')} checked {item.get('target', '?')} -> "
                f"{'wolf' if item.get('is_wolf') else 'good'}"
            )
        elif event_type == "day_vote":
            votes = item.get("votes", [])
            own_vote = next((vote for vote in votes if vote.get("voter") == agent_name), None)
            if own_vote:
                results.append(f"R{item.get('round', '?')} voted {own_vote.get('target', '?')}")
        elif event_type == "death" and item.get("player") == agent_name:
            results.append(f"R{item.get('round', '?')} died during {item.get('phase', '?')}")
        elif event_type == "elimination":
            results.append(f"R{item.get('round', '?')} exile: {item.get('player', '?')}")

        if len(results) >= limit:
            break

    if len(results) < limit:
        for speech in _extract_agent_speeches(log, agent_name, limit=limit - len(results)):
            results.append("speech: " + speech)

    return results[:limit]


def _count_roles_from_players(players: list[Player]) -> dict[str, int]:
    counter = Counter(player.role.value for player in players)
    return dict(counter)


def _count_roles_from_log(log: dict) -> dict[str, int]:
    counter = Counter(_role_value(player.get("role")) for player in log.get("players", []))
    return {role: count for role, count in counter.items() if role}


def _format_role_counts(role_counts: dict[str, int]) -> str:
    ordered_items = sorted(role_counts.items(), key=lambda item: item[0])
    return " / ".join(f"{_role_name(role)}x{count}" for role, count in ordered_items) or "unknown"


def _did_agent_win(role_value: str, winner: str | None) -> bool:
    if winner == "werewolf":
        return role_value in WOLF_ROLE_VALUES
    if winner == "village":
        return role_value not in WOLF_ROLE_VALUES
    return False


def _role_name(role_value: str) -> str:
    return ROLE_NAME_BY_VALUE.get(role_value, role_value or "unknown")


def _role_value(raw_role) -> str:
    if hasattr(raw_role, "value"):
        return raw_role.value
    return str(raw_role or "")
