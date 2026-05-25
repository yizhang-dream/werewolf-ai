from pydantic import BaseModel, Field

from app.llm.base import LLMClient
from app.llm.structured import get_structured_response
from app.models.agent import AgentMemory, Lesson, RoleMemorySummary
from app.models.game import GameState, ROLE_NAMES_ZH, Role, WOLF_ROLES


class RoleSummaryUpdate(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    signals_to_watch: list[str] = Field(default_factory=list)
    role_tips: list[str] = Field(default_factory=list)


class ReflectionResult(BaseModel):
    reflection: str
    key_moments: list[str] = Field(default_factory=list)
    strategy_updates: list[str] = Field(default_factory=list)
    useful_takeaways: list[str] = Field(default_factory=list)
    role_summary_update: RoleSummaryUpdate = Field(default_factory=RoleSummaryUpdate)


def _build_game_summary_for_agent(state: GameState, player_name: str) -> str:
    lines = [
        f"Game id: {state.game_id}",
        f"Rounds played: {state.round_number}",
        f"Winner: {state.winner or 'unknown'}",
        "",
        "Final table:",
    ]

    for player in state.players:
        role_name = ROLE_NAMES_ZH.get(player.role, player.role.value)
        status = "alive" if player.status.value == "alive" else "dead"
        lines.append(f"- {player.name}: {role_name} ({player.role.value}), {status}")

    lines.append("")
    lines.append("Discussion log:")
    for speech in state.speeches:
        if speech.speaker == player_name:
            lines.append(f"- R{speech.round_number} {speech.phase} you said: {speech.public_speech}")
            if speech.inner_thought:
                lines.append(f"  Inner thought: {speech.inner_thought}")
        else:
            lines.append(f"- R{speech.round_number} {speech.phase} {speech.speaker}: {speech.public_speech}")

    audit = _critical_action_audit_lines(state, player_name)
    if audit:
        lines.append("")
        lines.append("Critical action audit:")
        lines.extend(audit)

    return "\n".join(lines)


def _critical_action_audit_lines(state: GameState, player_name: str) -> list[str]:
    lines = []
    winner = state.winner or "unknown"
    action_phases = {
        "vote",
        "sheriff_vote",
        "sheriff_tiebreak",
        "sheriff_transfer",
        "night_werewolf",
        "night_wolf_beauty",
        "night_stone_gargoyle",
        "night_seer",
        "night_witch",
        "night_guard",
        "night_silencer",
        "night_gravekeeper",
        "hunter_revenge",
        "wolf_king_revenge",
        "knight_duel",
        "werewolf_self_destruct",
        "white_wolf_self_destruct",
    }

    for speech in state.speeches:
        if speech.speaker != player_name or speech.phase not in action_phases:
            continue
        detail = speech.skill_info or speech.public_speech or speech.inner_thought or "action recorded"
        lines.append(f"- R{speech.round_number} your {speech.phase}: {detail}; final winner={winner}")

    for item in state.history:
        if item.get("type") == "day_vote":
            own_vote = next((vote for vote in item.get("votes", []) if vote.get("voter") == player_name), None)
            if own_vote:
                lines.append(f"- R{item.get('round', '?')} your exile vote: {own_vote.get('target', '?')}; final winner={winner}")
        elif item.get("type") == "sheriff_election":
            for vote_round in item.get("vote_rounds", []):
                own_vote = next((vote for vote in vote_round.get("votes", []) if vote.get("voter") == player_name), None)
                if own_vote:
                    lines.append(
                        f"- R{item.get('round', '?')} your sheriff vote round {vote_round.get('round', '?')}: "
                        f"{own_vote.get('target', '?')}; final sheriff={item.get('winner') or 'none'}; final winner={winner}"
                    )
        elif item.get("type") == "seer_check" and item.get("player") == player_name:
            lines.append(
                f"- R{item.get('round', '?')} your seer check: {item.get('target', '?')} -> "
                f"{'wolf' if item.get('is_wolf') else 'good'}; final winner={winner}"
            )
        elif item.get("type") == "knight_duel" and item.get("player") == player_name:
            lines.append(f"- R{item.get('round', '?')} your knight duel target: {item.get('target', '?')}; final winner={winner}")
        elif item.get("type") == "death" and item.get("player") == player_name:
            lines.append(f"- R{item.get('round', '?')} you died during {item.get('phase', '?')}; final winner={winner}")

    # Self-destruct deaths are useful to show to wolf teammates too, not only the actor.
    for item in state.history:
        if item.get("type") != "death" or item.get("phase") not in {"werewolf_self", "white_wolf_self"}:
            continue
        relation = "you" if item.get("player") == player_name else "wolf teammate/other"
        lines.append(
            f"- R{item.get('round', '?')} {item.get('player', '?')} self-destruct death ({relation}); final winner={winner}"
        )

    return lines


def _role_config_summary(state: GameState) -> str:
    counts: dict[str, int] = {}
    for player in state.players:
        role_name = ROLE_NAMES_ZH.get(player.role, player.role.value)
        counts[role_name] = counts.get(role_name, 0) + 1
    return " / ".join(f"{name}x{count}" for name, count in counts.items())


def _is_wolf_win(player_role: Role, winner: str | None) -> bool:
    if winner == "werewolf":
        return player_role in WOLF_ROLES
    if winner == "village":
        return player_role not in WOLF_ROLES
    return False


def _merge_unique(existing: list[str], new_items: list[str], limit: int) -> list[str]:
    merged = [item.strip() for item in existing if item and item.strip()]
    for item in new_items:
        cleaned = item.strip()
        if not cleaned or cleaned in merged:
            continue
        merged.append(cleaned)
    return merged[-limit:]


def _append_unique(items: list[str], new_items: list[str]) -> list[str]:
    merged = [item for item in items if item]
    for item in new_items:
        if item and item not in merged:
            merged.append(item)
    return merged


def _apply_outcome_guardrails(result: dict, won: bool) -> dict:
    if won:
        return result

    update = result.setdefault("role_summary_update", {}) or {}
    result["role_summary_update"] = update

    warning = "结果校准：这是一局失败样本，本局自信的发言、投票和技能选择都应优先作为负反馈审计，不能直接沉淀为高光或稳定优势。"
    takeaway = "输局复盘默认是负反馈：先找导致失败的判断链、票型选择、技能使用和节奏决策，再提出下次可验证的替代打法。"
    pitfall = "在失败局中把主观自信、强势发言或主动操作误判为高光，会污染长期记忆并重复同类错误。"

    result["reflection"] = (result.get("reflection", "").strip() + " " + warning).strip()
    result["key_moments"] = _append_unique(result.get("key_moments", []), [warning])
    result["useful_takeaways"] = _append_unique(result.get("useful_takeaways", []), [takeaway])
    result["strategy_updates"] = _append_unique(
        result.get("strategy_updates", []),
        ["长期记忆必须做结果校准：胜局经验才可谨慎强化；输局经验优先进入风险、误判和替代打法。"],
    )
    update["pitfalls"] = _append_unique(update.get("pitfalls", []), [pitfall])
    update["role_tips"] = _append_unique(
        update.get("role_tips", []),
        ["失败后复盘不要问“我哪里打得帅”，而要问：哪一步判断没有被结果支持、下次如何用票型/发言/技能信息提前纠偏。"],
    )
    update["signals_to_watch"] = _append_unique(
        update.get("signals_to_watch", []),
        ["如果一局最终失败，所有曾被自己认为正确的关键操作都需要重新校验其真实收益。"],
    )
    update["strengths"] = []

    return result


def _apply_lesson_to_memory(
    memory: AgentMemory,
    state: GameState,
    player_name: str,
    lesson: Lesson,
) -> AgentMemory:
    player = next(p for p in state.players if p.name == player_name)
    won = lesson.won

    memory.total_games += 1
    if won:
        memory.wins += 1
    else:
        memory.losses += 1

    memory.lessons.append(lesson)

    role_summary = memory.role_summaries.get(player.role.value, RoleMemorySummary(role=player.role.value))
    role_summary.total_games += 1
    if won:
        role_summary.wins += 1
    else:
        role_summary.losses += 1
    role_summary.recent_examples = _merge_unique(
        role_summary.recent_examples,
        lesson.useful_takeaways + lesson.key_moments,
        limit=6,
    )
    role_summary.last_updated_game_id = state.game_id
    memory.role_summaries[player.role.value] = role_summary

    if len(memory.lessons) > 80:
        memory.lessons = memory.lessons[-80:]

    return memory


def agent_reflect_fallback(
    state: GameState,
    player_name: str,
    memory: AgentMemory,
    reason: str = "",
) -> AgentMemory:
    player = next(p for p in state.players if p.name == player_name)
    won = _is_wolf_win(player.role, state.winner)
    reason_text = reason.strip()
    if reason_text:
        reason_text = f" 失败原因：{reason_text}"

    lesson = Lesson(
        game_id=state.game_id,
        role=player.role.value,
        won=won,
        reflection=f"自动复盘未完成，已先保留这局的基础结果和关键动作。{reason_text}",
        key_moments=_critical_action_audit_lines(state, player_name)[:3],
        player_count=len(state.players),
        role_config=_role_config_summary(state),
        rounds_played=state.round_number,
        survived_to_end=player.status.value == "alive",
        final_status=player.status.value,
        winner=state.winner or "",
        useful_takeaways=[],
    )
    return _apply_lesson_to_memory(memory, state, player_name, lesson)


async def agent_reflect(
    client: LLMClient,
    model: str,
    state: GameState,
    player_name: str,
    memory: AgentMemory,
) -> AgentMemory:
    player = next(p for p in state.players if p.name == player_name)
    won = _is_wolf_win(player.role, state.winner)

    existing_role_summary = memory.role_summaries.get(player.role.value, RoleMemorySummary(role=player.role.value))
    strategies_text = "\n".join(f"- {item}" for item in memory.strategies) if memory.strategies else "- none yet"
    game_summary = _build_game_summary_for_agent(state, player_name)
    role_summary_text = "\n".join(
        [
            f"strengths: {', '.join(existing_role_summary.strengths) or 'none'}",
            f"pitfalls: {', '.join(existing_role_summary.pitfalls) or 'none'}",
            f"signals_to_watch: {', '.join(existing_role_summary.signals_to_watch) or 'none'}",
            f"role_tips: {', '.join(existing_role_summary.role_tips) or 'none'}",
        ]
    )

    role_name = ROLE_NAMES_ZH.get(player.role, player.role.value)
    system = (
        f"You are {player_name}. You just finished a Werewolf game as {role_name} ({player.role.value}). "
        "Reflect like a strong competitive player who wants to improve across many future games. "
        "Return JSON only."
    )

    user = f"""## Game summary
{game_summary}

## Result
You {'won' if won else 'lost'} as {role_name} ({player.role.value}).
Board: {_role_config_summary(state)}

## Existing general strategy memory
{strategies_text}

## Existing same-role summary
{role_summary_text}

## Outcome calibration rules
- If you lost, treat this game as a negative training sample first.
- In a loss, do not label your own confident calls, votes, skill uses, fake claims, self-destructs, or tempo pushes as "highlights" unless you also explain why they were not part of the losing chain.
- In a loss, put most reusable learning into pitfalls, signals_to_watch, role_tips, and alternative future actions.
- Strengths should mostly come from wins. For losses, only include a strength if it is clearly partial, bounded, and not contradicted by the final result.
- The Critical action audit lists decisions that need outcome-based scrutiny; do not repeat their inner_thought as proof that the decision was good.

Return JSON in this shape:
{{
  "reflection": "2-4 sentence reflection",
  "key_moments": ["short moment", "short moment"],
  "strategy_updates": ["general strategy update"],
  "useful_takeaways": ["portable takeaway for future similar games"],
  "role_summary_update": {{
    "strengths": ["what worked well for this role"],
    "pitfalls": ["what failed or is risky for this role"],
    "signals_to_watch": ["tells or game patterns worth watching"],
    "role_tips": ["actionable same-role advice"]
  }}
}}

Keep each list concise and reusable across future games."""

    result = await get_structured_response(
        client,
        model,
        system,
        user,
        ReflectionResult,
        temperature=0.4,
    )
    result = _apply_outcome_guardrails(result, won)

    lesson = Lesson(
        game_id=state.game_id,
        role=player.role.value,
        won=won,
        reflection=result["reflection"],
        key_moments=result["key_moments"],
        player_count=len(state.players),
        role_config=_role_config_summary(state),
        rounds_played=state.round_number,
        survived_to_end=player.status.value == "alive",
        final_status=player.status.value,
        winner=state.winner or "",
        useful_takeaways=result.get("useful_takeaways", []),
    )
    memory = _apply_lesson_to_memory(memory, state, player_name, lesson)

    memory.strategies = _merge_unique(memory.strategies, result.get("strategy_updates", []), limit=18)

    update = result.get("role_summary_update", {}) or {}
    role_summary = memory.role_summaries.get(player.role.value, RoleMemorySummary(role=player.role.value))
    role_summary.strengths = _merge_unique(role_summary.strengths, update.get("strengths", []), limit=6)
    role_summary.pitfalls = _merge_unique(role_summary.pitfalls, update.get("pitfalls", []), limit=6)
    role_summary.signals_to_watch = _merge_unique(
        role_summary.signals_to_watch,
        update.get("signals_to_watch", []),
        limit=6,
    )
    role_summary.role_tips = _merge_unique(role_summary.role_tips, update.get("role_tips", []), limit=6)
    role_summary.recent_examples = _merge_unique(
        role_summary.recent_examples,
        result.get("useful_takeaways", []) + result.get("key_moments", []),
        limit=6,
    )
    role_summary.last_updated_game_id = state.game_id
    memory.role_summaries[player.role.value] = role_summary

    return memory
