import asyncio
import logging
import random
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.engine.voting import tally_votes
from app.engine.win_check import check_win_condition
from app.llm.base import LLMClient
from app.llm.factory import create_client
from app.llm.structured import get_structured_response
from app.memory.store import save_agent_memory, save_game_log
from app.memory.summarizer import agent_reflect, agent_reflect_fallback
from app.models.agent import AgentMemory
from app.models.game import (
    COMMON_WOLF_ROLES,
    GameState,
    NightAction,
    Phase,
    Player,
    PlayerStatus,
    ROLE_NAMES_ZH,
    Role,
    SpeechRecord,
    VISIBLE_PACK_WOLF_ROLES,
    VoteRecord,
    WolfChatRecord,
    WOLF_ROLES,
    WitchSelfSaveRule,
)

logger = logging.getLogger(__name__)

MAX_WOLF_ROUNDS = 3
POISON_CAUSES = {"witch_poison", "evil_spirit_poison"}
NO_GUN_CAUSES = POISON_CAUSES | {"werewolf_self", "white_wolf_self"}
REPLACEABLE_NOTE_PREFIXES = (
    "身份工作区：",
    "战术计划：",
    "假身份：",
    "狼队计划：",
    "技能计划：",
)


class ActionSchema(BaseModel):
    kill_target: Optional[str] = None
    check_target: Optional[str] = None
    use_save: Optional[bool] = None
    poison_target: Optional[str] = None
    protect_target: Optional[str] = None
    vote_target: Optional[str] = None
    shoot_target: Optional[str] = None
    run_for_sheriff: Optional[bool] = None
    transfer_badge_target: Optional[str] = None
    self_destruct: Optional[bool] = None


class FullResponseSchema(BaseModel):
    inner_thought: str = ""
    public_speech: str = ""
    private_note: Optional[str] = None
    delete_notes: list[int] = Field(default_factory=list)
    action: Optional[ActionSchema] = None


class GameManager:
    def __init__(self, game_state: GameState):
        self.state = game_state
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self._pending_night_reveal = False
        self._pending_night_kills: list[str] = []

    async def _emit(self, event: str, data: dict):
        await self.event_queue.put({"event": event, "data": data})

    def _alive_players(self) -> list[Player]:
        return [player for player in self.state.players if player.status == PlayerStatus.ALIVE]

    def _alive_targets(self, exclude: Optional[str] = None) -> list[str]:
        return [player.name for player in self._alive_players() if player.name != exclude]

    def _get_player(self, name: str) -> Player:
        return next(player for player in self.state.players if player.name == name)

    def _is_wolf(self, player: Player) -> bool:
        return player.role in WOLF_ROLES

    def _visible_wolf_teammates_for(self, player: Player) -> list[str]:
        if player.role not in WOLF_ROLES:
            return []

        teammates: list[str] = []
        for other in self.state.players:
            if other.name == player.name or other.role not in WOLF_ROLES:
                continue
            if player.role == Role.STONE_GARGOYLE and other.role in COMMON_WOLF_ROLES:
                continue
            if other.role == Role.STONE_GARGOYLE and player.role in COMMON_WOLF_ROLES:
                continue
            if player.role == Role.HIDDEN_WOLF and other.role in COMMON_WOLF_ROLES:
                continue
            if other.role == Role.HIDDEN_WOLF and player.role in COMMON_WOLF_ROLES:
                continue
            teammates.append(other.name)
        return teammates

    def _compose_wolf_team_note(self, player: Player) -> str:
        if player.role not in WOLF_ROLES:
            return ""

        alive_teammates = [name for name in self._visible_wolf_teammates_for(player) if self._get_player(name).status == PlayerStatus.ALIVE]
        dead_teammates = [name for name in self._visible_wolf_teammates_for(player) if self._get_player(name).status == PlayerStatus.DEAD]
        known_alive_count = 1 + len(alive_teammates) if player.status == PlayerStatus.ALIVE else len(alive_teammates)
        if alive_teammates:
            return (
                f"狼队硬信息：已确认存活狼队友 {', '.join(alive_teammates)}；"
                f"已确认出局狼队友 {', '.join(dead_teammates) if dead_teammates else '暂无'}；"
                f"你已知范围内当前还有 {known_alive_count} 名存活狼人（含你自己时已计入）；名单外玩家都不是你的已确认队友。"
            )
        return (
            f"狼队硬信息：你当前是已知范围内唯一存活狼人；"
            f"已确认出局狼队友 {', '.join(dead_teammates) if dead_teammates else '暂无'}；"
            "名单外玩家都不是你的已确认队友。"
        )

    def _compose_identity_workspace_note(self, player: Player) -> str:
        alive_others = [other.name for other in self._alive_players() if other.name != player.name]
        dead_public = [
            other.name
            for other in self.state.players
            if other.status == PlayerStatus.DEAD
        ]
        checked_targets: set[str] = set()
        confirmed_wolves: list[str] = []
        confirmed_good: list[str] = []
        private_facts: list[str] = []

        if player.role == Role.SEER:
            for item in self.state.history:
                if item.get("type") != "seer_check" or item.get("player") != player.name:
                    continue
                target = str(item.get("target") or "")
                if not target:
                    continue
                checked_targets.add(target)
                if item.get("is_wolf"):
                    confirmed_wolves.append(target)
                else:
                    confirmed_good.append(target)
            private_facts.append(
                f"验人：查杀 {', '.join(confirmed_wolves) if confirmed_wolves else '暂无'}；"
                f"金水 {', '.join(confirmed_good) if confirmed_good else '暂无'}"
            )

        if player.role in WOLF_ROLES:
            alive_teammates = [name for name in self._visible_wolf_teammates_for(player) if self._get_player(name).status == PlayerStatus.ALIVE]
            dead_teammates = [name for name in self._visible_wolf_teammates_for(player) if self._get_player(name).status == PlayerStatus.DEAD]
            private_facts.append(
                f"狼队：存活队友 {', '.join(alive_teammates) if alive_teammates else '暂无'}；"
                f"出局队友 {', '.join(dead_teammates) if dead_teammates else '暂无'}"
            )

        return (
            f"身份素材：存活待分析 {', '.join(alive_others) if alive_others else '暂无'}；"
            f"已死亡玩家 {', '.join(dead_public) if dead_public else '暂无'}；"
            f"私有硬事实 {'；'.join(private_facts) if private_facts else '暂无'}；"
            "具体谁报身份、谁没交代、谁进民坑/神坑/狼坑，由你在“身份工作区：”便签中自行维护。"
        )

    def _refresh_private_fact_notes(self) -> bool:
        changed = False
        for player in self.state.players:
            identity_note = self._compose_identity_workspace_note(player)
            if identity_note:
                changed = self._store_agent_note(player, identity_note, replace_prefix="身份素材：") or changed
            if player.role in WOLF_ROLES:
                note = self._compose_wolf_team_note(player)
                if note:
                    changed = self._store_agent_note(player, note, replace_prefix="狼队硬信息：") or changed
        return changed

    def _has_alive_role(self, role: Role) -> bool:
        return any(player.role == role and player.status == PlayerStatus.ALIVE for player in self.state.players)

    def _is_hidden_wolf_awakened(self, player: Player) -> bool:
        return player.role == Role.HIDDEN_WOLF and not any(
            other.name != player.name and other.status == PlayerStatus.ALIVE and other.role in COMMON_WOLF_ROLES
            for other in self.state.players
        )

    def _is_stone_gargoyle_awakened(self, player: Player) -> bool:
        return player.role == Role.STONE_GARGOYLE and not any(
            other.name != player.name and other.status == PlayerStatus.ALIVE and other.role in COMMON_WOLF_ROLES
            for other in self.state.players
        )

    def _can_join_wolf_kill(self, player: Player) -> bool:
        if player.role in VISIBLE_PACK_WOLF_ROLES:
            return True
        if player.role == Role.HIDDEN_WOLF:
            return self._is_hidden_wolf_awakened(player)
        if player.role == Role.STONE_GARGOYLE:
            return self._is_stone_gargoyle_awakened(player)
        return False

    def _wolf_chat_message(self, result: dict) -> str:
        message = " ".join(str(result.get("public_speech") or "").split())
        if not message:
            message = " ".join(str(result.get("inner_thought") or "").split())
        return message[:500]

    def _get_client(self, player: Player) -> LLMClient:
        from app.routers.settings import get_provider

        provider = get_provider(player.llm_provider)
        return create_client(provider.provider_type, provider.api_key, provider.base_url)

    def _get_model(self, player: Player) -> str:
        if player.model_name:
            return player.model_name

        from app.routers.settings import get_provider

        try:
            provider = get_provider(player.llm_provider)
            if provider.models:
                return provider.models[0]
        except Exception:
            pass
        return "gpt-4o"

    async def _agent_action(
        self,
        player: Player,
        system: str,
        user: str,
        temp: float = 0.7,
        max_tokens: int = 2048,
        allow_note_fallback: bool = False,
        allow_dead_action: bool = False,
    ) -> dict:
        if player.status == PlayerStatus.DEAD and not allow_dead_action:
            return {"inner_thought": "", "public_speech": "", "private_note": "", "action": None}
        client = self._get_client(player)
        model = self._get_model(player)
        result = await get_structured_response(client, model, system, user, FullResponseSchema, temperature=temp, max_tokens=max_tokens)
        if player.status == PlayerStatus.ALIVE:
            notes_changed = self._delete_agent_notes(player, result.get("delete_notes") or [])
            notes_changed = self._update_agent_note(player, result, allow_fallback=allow_note_fallback) or notes_changed
            if notes_changed:
                await self._emit_agent_notes_update()
        return result

    async def _emit_agent_notes_update(self) -> None:
        await self._emit("agent_notes_update", {"agent_notes": self.state.agent_notes})

    def _fallback_agent_note(self, result: dict) -> str:
        inner_thought = " ".join(str(result.get("inner_thought") or "").split())
        if not inner_thought:
            return ""

        segments = [segment.strip() for segment in re.split(r"(?<=[。！？!?；;])", inner_thought) if segment.strip()]
        note = "".join(segments[:2]) if segments else inner_thought
        return note[:120]

    def _normalize_agent_note(self, player: Player, note: str) -> str:
        normalized = " ".join(note.split()).strip(" ，,、；;：:。!！?？")
        if not normalized:
            return ""

        if player.role in WOLF_ROLES and ("疑似队友" in normalized or "像队友" in normalized):
            known_teammates = self._visible_wolf_teammates_for(player)
            for teammate in known_teammates:
                if teammate in normalized:
                    normalized = normalized.replace("疑似队友", "已确认狼队友").replace("像队友", "是已确认狼队友")
                    break
            else:
                return ""

        if not normalized.startswith(("狼队硬信息：", "身份素材：", *REPLACEABLE_NOTE_PREFIXES)):
            normalized = f"{self._default_agent_note_prefix(player, normalized)}{normalized}"

        return normalized

    def _default_agent_note_prefix(self, player: Player, note: str) -> str:
        if player.role in WOLF_ROLES and any(keyword in note for keyword in ("假身份", "悍跳", "对跳", "倒钩", "冲票", "刀口", "狼队")):
            return "狼队计划："
        if any(keyword in note for keyword in ("技能", "验", "毒", "救", "守", "枪", "警徽流", "刀")):
            return "技能计划："
        if any(keyword in note for keyword in ("身份", "狼坑", "神坑", "民坑", "站边", "金水", "查杀", "报身份", "交代")):
            return "身份工作区："
        return "战术计划："

    @staticmethod
    def _agent_note_body(entry: str) -> str:
        return entry.split(": ", 1)[-1] if ": " in entry else entry

    @staticmethod
    def _is_protected_agent_note(entry: str) -> bool:
        body = GameManager._agent_note_body(entry)
        return body.startswith(("狼队硬信息：", "身份素材："))

    def _delete_agent_notes(self, player: Player, visible_note_numbers: list[int]) -> bool:
        if not visible_note_numbers:
            return False

        entries = self.state.agent_notes.get(player.name)
        if not entries:
            return False

        visible_start = max(len(entries) - 8, 0)
        visible_entries = entries[visible_start:]
        indexes_to_delete: set[int] = set()
        for raw_number in visible_note_numbers:
            if not isinstance(raw_number, int):
                continue
            visible_index = raw_number - 1
            if visible_index < 0 or visible_index >= len(visible_entries):
                continue
            actual_index = visible_start + visible_index
            if self._is_protected_agent_note(entries[actual_index]):
                continue
            indexes_to_delete.add(actual_index)

        if not indexes_to_delete:
            return False

        self.state.agent_notes[player.name] = [
            entry for index, entry in enumerate(entries) if index not in indexes_to_delete
        ]
        if not self.state.agent_notes[player.name]:
            self.state.agent_notes.pop(player.name, None)
        return True

    def _store_agent_note(self, player: Player, note: str, replace_prefix: str | tuple[str, ...] | None = None) -> bool:
        note = note[:220]
        entries = self.state.agent_notes.setdefault(player.name, [])
        formatted = f"R{self.state.round_number} {self.state.phase.value}: {note}"

        if replace_prefix:
            prefixes = (replace_prefix,) if isinstance(replace_prefix, str) else replace_prefix
            for index, entry in enumerate(entries):
                body = self._agent_note_body(entry)
                if body.startswith(prefixes):
                    if body == note:
                        return False
                    entries.pop(index)
                    entries.append(formatted)
                    self.state.agent_notes[player.name] = entries[-8:]
                    return True

        if any(self._agent_note_body(entry) == note for entry in entries):
            return False

        entries.append(formatted)
        self.state.agent_notes[player.name] = entries[-8:]
        return True

    def _update_agent_note(self, player: Player, result: dict, allow_fallback: bool = False) -> bool:
        raw_note = result.get("private_note")
        note = " ".join(str(raw_note or "").split())
        if not note and allow_fallback:
            note = self._fallback_agent_note(result)
        note = self._normalize_agent_note(player, note)
        if not note:
            return False
        replace_prefix = None
        if note.startswith("狼队硬信息："):
            replace_prefix = "狼队硬信息："
        elif note.startswith("身份素材："):
            replace_prefix = "身份素材："
        elif note.startswith(REPLACEABLE_NOTE_PREFIXES):
            replace_prefix = self._replace_prefix_for_agent_note(player, note)
        return self._store_agent_note(player, note, replace_prefix=replace_prefix)

    def _replace_prefix_for_agent_note(self, player: Player, note: str) -> str | tuple[str, ...] | None:
        if note.startswith("身份工作区："):
            return "身份工作区："
        if note.startswith("战术计划："):
            return "战术计划："
        if note.startswith("技能计划："):
            return "技能计划："
        if player.role in WOLF_ROLES and note.startswith(("假身份：", "狼队计划：")):
            return ("假身份：", "狼队计划：")
        if note.startswith(("假身份：", "狼队计划：")):
            return note.split("：", 1)[0] + "："
        return None

    async def _digest_public_speech_for_observers(self, speaker_name: str, public_speech: str, phase: str) -> None:
        if not public_speech:
            return

        digest_tasks = []
        for observer in self._alive_players():
            if observer.name == speaker_name:
                continue

            ctx = AgentContext(observer, self.state)
            digest_tasks.append(
                self._agent_action(
                    observer,
                    ctx.build_discuss_system_prompt(),
                    ctx.build_public_speech_digest_user_prompt(speaker_name, public_speech, phase),
                    temp=0.25,
                    max_tokens=900,
                    allow_note_fallback=True,
                )
            )

        if digest_tasks:
            results = await asyncio.gather(*digest_tasks, return_exceptions=True)
            failures = [result for result in results if isinstance(result, Exception)]
            if failures:
                logger.warning(
                    "Skipped %d observer note digest(s) after %s spoke: %s",
                    len(failures),
                    speaker_name,
                    "; ".join(str(failure) for failure in failures[:3]),
                )

    async def _record_private_thought(self, player: Player, result: dict, phase: str, skill_info: str = "", allow_dead: bool = False):
        if player.status == PlayerStatus.DEAD and not allow_dead:
            return
        self.state.speeches.append(
            SpeechRecord(
                speaker=player.name,
                inner_thought=result.get("inner_thought", ""),
                public_speech="",
                round_number=self.state.round_number,
                phase=phase,
                skill_info=skill_info,
            )
        )

    def _record_history_death(self, name: str, phase: str):
        player = self._get_player(name)
        self.state.history.append(
            {
                "type": "death",
                "round": self.state.round_number,
                "phase": phase,
                "player": name,
                "role": ROLE_NAMES_ZH[player.role],
            }
        )

    async def _check_and_emit_winner(self) -> bool:
        winner = check_win_condition(self.state)
        if winner:
            self.state.winner = winner
            await self._emit("game_over", {"winner": winner})
            return True
        return False

    def _can_witch_self_save(self, witch: Player, killed: Optional[str]) -> bool:
        if killed != witch.name:
            return True
        if self.state.rules.witch_self_save_rule == WitchSelfSaveRule.ALWAYS:
            return True
        if self.state.rules.witch_self_save_rule == WitchSelfSaveRule.FIRST_NIGHT_ONLY:
            return self.state.round_number == 1
        return False

    def _has_used_knight_duel(self, name: str) -> bool:
        return any(item.get("type") == "knight_duel" and item.get("player") == name for item in self.state.history)

    def _has_alive_sheriff(self) -> bool:
        if not self.state.sheriff_name:
            return False
        return self._get_player(self.state.sheriff_name).status == PlayerStatus.ALIVE

    def _vote_weight(self, player: Player) -> float:
        if self.state.rules.sheriff_enabled and self.state.sheriff_name == player.name:
            return self.state.rules.sheriff_vote_multiplier
        return 1.0

    def _vote_weights(self, players: list[Player]) -> dict[str, float]:
        return {player.name: self._vote_weight(player) for player in players if player.vote_right}

    @staticmethod
    def _format_vote_counts(counts: dict[str, float]) -> str:
        return "、".join(f"{name} {count:g}票" for name, count in counts.items()) if counts else "无人得票"

    async def _emit_sheriff_update(self, message: str, previous: Optional[str] = None, reason: str = "update"):
        await self._emit(
            "sheriff_update",
            {
                "sheriff": self.state.sheriff_name,
                "previous": previous,
                "reason": reason,
                "message": message,
            },
        )

    async def run_game(self):
        self.state.created_at = datetime.now().isoformat()
        random.shuffle(self.state.players)
        await self._emit("seating", {"order": [player.name for player in self.state.players]})
        if self._refresh_private_fact_notes():
            await self._emit_agent_notes_update()

        try:
            while self.state.winner is None:
                await self._night_phase()
                if self.state.winner:
                    break
                await self._day_phase()
            await self._post_game()
        except Exception as exc:
            logger.exception("Game crashed: %s: %s", type(exc).__name__, exc)
            await self._emit("error", {"message": f"游戏运行出错：{exc}"})

    def _determine_speak_order(self) -> list[Player]:
        all_players = self.state.players
        alive_players = self._alive_players()
        alive_names = {p.name for p in alive_players}
        sheriff_name = self.state.sheriff_name
        sheriff_alive = sheriff_name in alive_names

        if sheriff_alive:
            # 警长存活时：从警长下一位开始顺时针发言，警长最后一个发言
            sheriff_index = next(
                index for index, p in enumerate(all_players) if p.name == sheriff_name
            )
            start_index = (sheriff_index + 1) % len(all_players)
        else:
            # 无警长时：从最近死亡者下一位开始，或随机
            start_index = random.randint(0, len(all_players) - 1)
            recent_dead = self.state.night_kills[-1] if self.state.night_kills else self.state.day_eliminated
            if recent_dead:
                dead_index = next((index for index, player in enumerate(all_players) if player.name == recent_dead), -1)
                if dead_index >= 0:
                    start_index = (dead_index - 1) % len(all_players)

        order: list[Player] = []
        sheriff_player = None
        for offset in range(len(all_players)):
            player = all_players[(start_index + offset) % len(all_players)]
            if player.name not in alive_names:
                continue
            if sheriff_alive and player.name == sheriff_name:
                sheriff_player = player  # 警长留到最后
            else:
                order.append(player)

        if sheriff_player:
            order.append(sheriff_player)  # 警长最后一个发言

        return order

    async def _night_phase(self):
        self.state.round_number += 1
        self.state.phase = Phase.NIGHT
        if self._refresh_private_fact_notes():
            await self._emit_agent_notes_update()
        previous = self.state.night_actions
        self.state.night_actions = NightAction(
            last_guard_target=previous.guard_target if previous else None,
            last_wolf_beauty_target=previous.wolf_beauty_target if previous else self.state.current_charmed_target,
            last_silencer_target=previous.silencer_target if previous else self.state.silenced_player,
        )
        self.state.silenced_player = None

        await self._emit("phase_change", {"phase": "night", "round": self.state.round_number, "message": f"第 {self.state.round_number} 夜开始，天黑请闭眼。"})

        await self._werewolf_action()
        await self._wolf_beauty_action()
        if self._has_alive_role(Role.WITCH):
            await self._witch_action()
        if self._has_alive_role(Role.SEER):
            await self._seer_action()
        if self._has_alive_role(Role.GUARD):
            await self._guard_action()
        await self._stone_gargoyle_action()
        if self._has_alive_role(Role.SILENCER):
            await self._silencer_action()
        if self._has_alive_role(Role.GRAVEKEEPER):
            await self._gravekeeper_action()

        defer_first_night_reveal = self.state.round_number == 1 and self.state.rules.sheriff_enabled
        await self._resolve_night(reveal=not defer_first_night_reveal)
        if not defer_first_night_reveal and self.state.rules.first_night_last_words and self.state.round_number == 1 and not self.state.winner:
            for name in self.state.night_kills:
                await self._last_words(self._get_player(name))

    async def _elect_sheriff(self):
        if not self.state.rules.sheriff_enabled or self.state.sheriff_election_completed or self.state.round_number != 1:
            return

        self.state.sheriff_election_completed = True
        alive_players = self._alive_players()
        await self._emit("vote_result", {"message": "开始警长竞选。所有存活玩家可以选择是否上警。"})

        candidates: list[str] = []
        for player in alive_players:
            ctx = AgentContext(player, self.state)
            result = await self._agent_action(player, ctx.build_discuss_system_prompt(), ctx.build_sheriff_nomination_user_prompt(), temp=0.4)
            will_run = bool((result.get("action") or {}).get("run_for_sheriff"))
            await self._record_private_thought(player, result, "sheriff_nomination", "选择上警" if will_run else "选择不上警")
            if will_run:
                candidates.append(player.name)

        if not candidates:
            self.state.history.append({"type": "sheriff_election", "round": self.state.round_number, "candidates": [], "votes": [], "winner": None})
            await self._emit_sheriff_update("警长竞选无人上警，本局没有警长。", reason="vacant")
            await self._emit("vote_result", {"message": "警长竞选无人上警，本局没有警长。"})
            return

        await self._emit("vote_result", {"message": f"上警玩家：{'、'.join(candidates)}。"})

        original_candidates = list(candidates)
        voters = [player for player in alive_players if player.name not in original_candidates]
        eligible_voter_names = [player.name for player in voters if player.vote_right]
        active_candidates = list(candidates)
        vote_rounds: list[dict] = []

        def record_election_snapshot(winner_name: Optional[str] = None) -> None:
            snapshot = {
                "type": "sheriff_election",
                "round": self.state.round_number,
                "candidates": original_candidates,
                "votes": vote_rounds[-1]["votes"] if vote_rounds else [],
                "counts": vote_rounds[-1]["counts"] if vote_rounds else {},
                "vote_rounds": vote_rounds,
                "winner": winner_name,
            }
            for index, item in enumerate(self.state.history):
                if item.get("type") == "sheriff_election" and item.get("round") == self.state.round_number:
                    self.state.history[index] = snapshot
                    return
            self.state.history.append(snapshot)

        for vote_round in range(1, 4):
            if vote_round > 1:
                await self._emit("vote_result", {"message": f"警长竞选第 {vote_round} 轮 PK，候选人：{'、'.join(active_candidates)}。"})

            for candidate_name in active_candidates:
                candidate = self._get_player(candidate_name)
                if candidate.status != PlayerStatus.ALIVE:
                    continue
                ctx = AgentContext(candidate, self.state)
                prompt = (
                    ctx.build_sheriff_campaign_user_prompt(active_candidates)
                    if vote_round == 1
                    else ctx.build_sheriff_runoff_campaign_user_prompt(active_candidates, vote_round, vote_rounds)
                )
                result = await self._agent_action(candidate, ctx.build_discuss_system_prompt(), prompt, temp=0.8)
                speech = SpeechRecord(
                    speaker=candidate.name,
                    inner_thought=result.get("inner_thought", ""),
                    public_speech=result.get("public_speech", ""),
                    round_number=self.state.round_number,
                    phase="sheriff_campaign" if vote_round == 1 else "sheriff_runoff",
                )
                self.state.speeches.append(speech)
                await self._emit("speech", {"speaker": candidate.name, "public_speech": speech.public_speech, "inner_thought": speech.inner_thought, "round": self.state.round_number, "phase": speech.phase})
                await self._digest_public_speech_for_observers(candidate.name, speech.public_speech, speech.phase)
                if not self.state.auto_advance:
                    await asyncio.sleep(self.state.step_delay)

            sheriff_votes: list[VoteRecord] = []
            valid_targets = active_candidates + ["abstain"]
            await self._emit("vote_result", {"message": f"警长竞选第 {vote_round} 轮开始投票。可投候选人：{'、'.join(active_candidates)}。"})
            for player in voters:
                if player.status != PlayerStatus.ALIVE:
                    continue
                if not player.vote_right:
                    continue
                ctx = AgentContext(player, self.state)
                result = await self._agent_action(player, ctx.build_vote_system_prompt(), ctx.build_sheriff_vote_user_prompt(active_candidates, vote_rounds), temp=0.4)
                target = (result.get("action") or {}).get("vote_target")
                if target not in valid_targets:
                    target = random.choice(valid_targets)
                await self._record_private_thought(player, result, "sheriff_vote", f"警长第 {vote_round} 轮投票：{target}")
                sheriff_votes.append(VoteRecord(voter=player.name, target=target))
                await self._emit("vote_cast", {"voter": player.name, "target": target, "context": "sheriff", "round": vote_round})

            winner, tied_targets, counts = tally_votes(sheriff_votes)
            round_summary = {
                "round": vote_round,
                "candidates": active_candidates,
                "ineligible_voters": original_candidates,
                "eligible_voters": eligible_voter_names,
                "votes": [{"voter": vote.voter, "target": vote.target} for vote in sheriff_votes],
                "actual_voters": [vote.voter for vote in sheriff_votes],
                "missing_voters": [name for name in eligible_voter_names if name not in {vote.voter for vote in sheriff_votes}],
                "counts": counts,
                "winner": winner,
                "tied_targets": tied_targets,
            }
            vote_rounds.append(round_summary)
            record_election_snapshot(winner)

            if winner:
                self.state.sheriff_name = winner
                await self._emit_sheriff_update(f"{winner} 当选警长。", reason="elected")
                await self._emit("vote_result", {"message": f"警长竞选第 {vote_round} 轮结果：{self._format_vote_counts(counts)}，{winner} 当选警长。"})
                return

            if tied_targets and vote_round < 3:
                await self._emit("vote_result", {"message": f"警长竞选第 {vote_round} 轮平票（{self._format_vote_counts(counts)}），平票候选人继续竞选。"})
                active_candidates = tied_targets
                continue

            record_election_snapshot(None)
            self.state.sheriff_name = None
            await self._emit_sheriff_update(f"警长竞选第 {vote_round} 轮仍未产生胜者（{self._format_vote_counts(counts)}），本局没有警长。", reason="vacant")
            await self._emit("vote_result", {"message": f"警长竞选第 {vote_round} 轮仍未产生胜者（{self._format_vote_counts(counts)}），本局没有警长。"})
            return

    async def _transfer_sheriff_badge(self, sheriff: Player):
        previous = sheriff.name
        alive_targets = self._alive_targets(exclude=sheriff.name)
        if not alive_targets:
            self.state.sheriff_name = None
            await self._emit_sheriff_update(f"{previous} 出局，场上没有可移交的目标，警徽被撕毁。", previous=previous, reason="destroyed")
            return

        ctx = AgentContext(sheriff, self.state)
        result = await self._agent_action(
            sheriff,
            ctx.build_discuss_system_prompt(),
            ctx.build_sheriff_transfer_user_prompt(alive_targets),
            temp=0.3,
            allow_dead_action=True,
        )
        target = (result.get("action") or {}).get("transfer_badge_target")
        if target not in alive_targets:
            target = None

        await self._record_private_thought(sheriff, result, "sheriff_transfer", f"警徽移交：{target or '撕毁'}", allow_dead=True)
        self.state.sheriff_name = target

        if target:
            await self._emit_sheriff_update(f"{previous} 将警徽移交给了 {target}。", previous=previous, reason="transfer")
        else:
            await self._emit_sheriff_update(f"{previous} 出局，警徽被撕毁。", previous=previous, reason="destroyed")

    async def _last_words(self, player: Player, context_hint: str | None = None):
        hint = context_hint or "你在第一夜被淘汰了。这是你的遗言时间。action 设为 null。"
        ctx = AgentContext(player, self.state)
        result = await self._agent_action(
            player,
            ctx.build_discuss_system_prompt() + f"\n\n{hint}",
            ctx.build_last_words_user_prompt(),
            temp=0.8,
            allow_dead_action=True,
        )
        speech = SpeechRecord(
            speaker=player.name,
            inner_thought=result.get("inner_thought", ""),
            public_speech=result.get("public_speech", ""),
            round_number=self.state.round_number,
            phase="last_words",
        )
        self.state.speeches.append(speech)
        await self._emit("speech", {"speaker": player.name, "public_speech": speech.public_speech, "inner_thought": speech.inner_thought, "round": self.state.round_number, "phase": speech.phase})
        await self._digest_public_speech_for_observers(player.name, speech.public_speech, speech.phase)

    async def _werewolf_action(self):
        wolves = [player for player in self.state.players if player.status == PlayerStatus.ALIVE and self._can_join_wolf_kill(player)]
        targets = [player.name for player in self.state.players if player.status == PlayerStatus.ALIVE and not self._is_wolf(player)]
        if not wolves or not targets:
            return

        proposals: list[dict[str, str]] = []
        for round_number in range(1, MAX_WOLF_ROUNDS + 1):
            current_round: list[dict[str, str]] = []
            for wolf in wolves:
                ctx = AgentContext(wolf, self.state)
                user_prompt = ctx.build_night_user_prompt() if round_number == 1 else ctx.build_werewolf_discuss_user_prompt(proposals, round_number)
                result = await self._agent_action(wolf, ctx.build_night_system_prompt(), user_prompt, temp=0.3)
                target = (result.get("action") or {}).get("kill_target")
                if target not in targets:
                    target = random.choice(targets)
                current_round.append({"name": wolf.name, "target": target})
                await self._record_private_thought(wolf, result, "night_werewolf", f"提议击杀：{target}" + (f"（狼人讨论第 {round_number} 轮）" if round_number > 1 else ""))
                await self._emit("night_action", {"role": "werewolf", "message": f"狼人 {wolf.name} 提议击杀：{target}"})

            proposals = current_round
            if len({proposal['target'] for proposal in proposals}) == 1:
                break
            if round_number < MAX_WOLF_ROUNDS:
                await self._emit("night_action", {"role": "werewolf", "message": "狼人尚未统一刀口，正在继续讨论。"})

        target_counts: dict[str, int] = {}
        for proposal in proposals:
            target_counts[proposal["target"]] = target_counts.get(proposal["target"], 0) + 1
        self.state.night_actions.werewolf_target = max(target_counts, key=target_counts.get)
        await self._emit("night_action", {"role": "werewolf", "message": "狼人已经确定了今晚的刀口。"})

        kill_target = self.state.night_actions.werewolf_target
        visible_to = [wolf.name for wolf in wolves]
        notes_changed = False
        for wolf in wolves:
            ctx = AgentContext(wolf, self.state)
            result = await self._agent_action(
                wolf,
                ctx.build_wolf_private_chat_system_prompt(),
                ctx.build_wolf_private_chat_user_prompt(kill_target),
                temp=0.6,
                max_tokens=900,
                allow_note_fallback=True,
            )
            message = self._wolf_chat_message(result)
            if message:
                self.state.wolf_chat.append(
                    WolfChatRecord(
                        speaker=wolf.name,
                        message=message,
                        round_number=self.state.round_number,
                        kill_target=kill_target,
                        visible_to=visible_to,
                    )
                )
                notes_changed = self._store_agent_note(wolf, f"狼队夜话：我对队友说：{message}", replace_prefix="狼队夜话：我对队友说：") or notes_changed
                for teammate in wolves:
                    if teammate.name == wolf.name:
                        continue
                    notes_changed = self._store_agent_note(teammate, f"狼队夜话：{wolf.name}说：{message}") or notes_changed
                await self._emit(
                    "wolf_chat",
                    {
                        "speaker": wolf.name,
                        "message": message,
                        "round_number": self.state.round_number,
                        "kill_target": kill_target,
                        "visible_to": visible_to,
                    },
                )
        if notes_changed:
            await self._emit_agent_notes_update()

    async def _wolf_beauty_action(self):
        if not self._has_alive_role(Role.WOLF_BEAUTY):
            return
        beauty = next(player for player in self.state.players if player.role == Role.WOLF_BEAUTY and player.status == PlayerStatus.ALIVE)
        ctx = AgentContext(beauty, self.state)
        result = await self._agent_action(beauty, ctx.build_night_system_prompt(), ctx.build_night_user_prompt(), temp=0.3)
        target = (result.get("action") or {}).get("check_target")
        valid_targets = self._alive_targets(exclude=beauty.name)
        if target not in valid_targets:
            target = None
        if target == self.state.night_actions.last_wolf_beauty_target:
            target = None
        if target:
            self.state.night_actions.wolf_beauty_target = target
            self.state.current_charmed_target = target
        await self._record_private_thought(beauty, result, "night_wolf_beauty", f"魅惑目标：{target or '无'}")

    async def _stone_gargoyle_action(self):
        gargoyle = next((player for player in self.state.players if player.role == Role.STONE_GARGOYLE and player.status == PlayerStatus.ALIVE), None)
        if not gargoyle or self._is_stone_gargoyle_awakened(gargoyle):
            return
        ctx = AgentContext(gargoyle, self.state)
        result = await self._agent_action(gargoyle, ctx.build_night_system_prompt(), ctx.build_night_user_prompt(), temp=0.3)
        target = (result.get("action") or {}).get("check_target")
        valid_targets = self._alive_targets(exclude=gargoyle.name)
        if target not in valid_targets:
            target = random.choice(valid_targets)
        target_player = self._get_player(target)
        self.state.night_actions.stone_gargoyle_target = target
        self.state.night_actions.stone_gargoyle_result = target_player.role
        await self._record_private_thought(gargoyle, result, "night_stone_gargoyle", f"查验身份：{target} -> {ROLE_NAMES_ZH[target_player.role]}")

    async def _seer_action(self):
        seer = next(player for player in self.state.players if player.role == Role.SEER and player.status == PlayerStatus.ALIVE)
        ctx = AgentContext(seer, self.state)
        result = await self._agent_action(seer, ctx.build_night_system_prompt(), ctx.build_night_user_prompt(), temp=0.3)
        targets = self._alive_targets(exclude=seer.name)
        target = (result.get("action") or {}).get("check_target")
        if target not in targets:
            target = random.choice(targets)

        target_player = self._get_player(target)
        hidden_wolf_appears_good = target_player.role == Role.HIDDEN_WOLF and not self._is_hidden_wolf_awakened(target_player)
        is_wolf = self._is_wolf(target_player) and not hidden_wolf_appears_good
        self.state.night_actions.seer_target = target
        self.state.night_actions.seer_result = target_player.role
        self.state.history.append({"type": "seer_check", "player": seer.name, "target": target, "is_wolf": is_wolf, "round": self.state.round_number})
        if self._refresh_private_fact_notes():
            await self._emit_agent_notes_update()
        if target_player.role == Role.EVIL_SPIRIT_KNIGHT:
            self.state.night_actions.reflected_target = seer.name
            self.state.night_actions.reflected_reason = "evil_spirit_check"
        await self._record_private_thought(seer, result, "night_seer", f"查验 {target}：{'狼人' if is_wolf else '好人'}")
        await self._emit("night_action", {"role": "seer", "player": seer.name, "message": f"预言家查验了 {target}。"})

    async def _witch_action(self):
        witch = next(player for player in self.state.players if player.role == Role.WITCH and player.status == PlayerStatus.ALIVE)
        ctx = AgentContext(witch, self.state)
        result = await self._agent_action(witch, ctx.build_night_system_prompt(), ctx.build_night_user_prompt(), temp=0.3)
        action = result.get("action") or {}
        killed = self.state.night_actions.werewolf_target
        skill_parts = []
        if self.state.witch_has_save:
            skill_parts.append(f"今晚狼刀目标：{killed or '无'}")
        else:
            skill_parts.append("解药已用完，本夜不可见狼刀目标")

        if self.state.witch_has_save and killed and action.get("use_save"):
            if self._can_witch_self_save(witch, killed):
                self.state.night_actions.witch_save = True
                self.state.witch_has_save = False
                skill_parts.append(f"使用解药救下：{killed}")
            else:
                skill_parts.append("尝试自救，但当前房规不允许")
        elif self.state.witch_has_poison:
            poison_target = action.get("poison_target")
            if poison_target in self._alive_targets(exclude=None):
                target_player = self._get_player(poison_target)
                if target_player.role == Role.EVIL_SPIRIT_KNIGHT:
                    self.state.night_actions.reflected_target = witch.name
                    self.state.night_actions.reflected_reason = "evil_spirit_poison"
                    self.state.witch_has_poison = False
                    skill_parts.append(f"对恶灵骑士使用毒药，被反噬：{poison_target}")
                else:
                    self.state.night_actions.witch_poison_target = poison_target
                    self.state.witch_has_poison = False
                    skill_parts.append(f"使用毒药毒杀：{poison_target}")
            else:
                skill_parts.append("没有使用毒药")

        await self._record_private_thought(witch, result, "night_witch", " | ".join(skill_parts))
        await self._emit("night_action", {"role": "witch", "message": "女巫完成了夜间决策。"})

    async def _guard_action(self):
        guard = next(player for player in self.state.players if player.role == Role.GUARD and player.status == PlayerStatus.ALIVE)
        ctx = AgentContext(guard, self.state)
        result = await self._agent_action(guard, ctx.build_night_system_prompt(), ctx.build_night_user_prompt(), temp=0.3)
        target = (result.get("action") or {}).get("protect_target")
        actual_target = "未守护任何人"

        if target in self._alive_targets(exclude=None):
            if target == guard.name and not self.state.rules.guard_can_self_protect:
                actual_target = "尝试守护自己，但当前房规不允许"
            elif target == self.state.night_actions.last_guard_target:
                actual_target = f"尝试守护 {target}，但规则禁止连续两晚守同一人"
            else:
                self.state.night_actions.guard_target = target
                actual_target = f"守护 {target}"

        await self._record_private_thought(guard, result, "night_guard", f"上一晚守护：{self.state.night_actions.last_guard_target or '无'} | 本晚结果：{actual_target}")
        await self._emit("night_action", {"role": "guard", "message": "守卫完成了夜间守护选择。"})

    async def _silencer_action(self):
        silencer = next(player for player in self.state.players if player.role == Role.SILENCER and player.status == PlayerStatus.ALIVE)
        ctx = AgentContext(silencer, self.state)
        result = await self._agent_action(silencer, ctx.build_night_system_prompt(), ctx.build_night_user_prompt(), temp=0.3)
        target = (result.get("action") or {}).get("check_target")
        valid_targets = self._alive_targets(exclude=silencer.name)
        if target not in valid_targets or target == self.state.night_actions.last_silencer_target:
            target = None
        self.state.night_actions.silencer_target = target
        self.state.silenced_player = target
        await self._record_private_thought(silencer, result, "night_silencer", f"禁言目标：{target or '无'}")

    async def _gravekeeper_action(self):
        keeper = next(player for player in self.state.players if player.role == Role.GRAVEKEEPER and player.status == PlayerStatus.ALIVE)
        eliminated = self.state.day_eliminated
        if eliminated:
            role = self._get_player(eliminated).role
            result_text = "狼人阵营" if role in WOLF_ROLES else "好人阵营"
            self.state.night_actions.gravekeeper_alignment = f"{eliminated} 属于{result_text}"
        else:
            self.state.night_actions.gravekeeper_alignment = "昨天地面没有被放逐玩家"
        await self._record_private_thought(keeper, {}, "night_gravekeeper", self.state.night_actions.gravekeeper_alignment)

    async def _kill_player(self, name: str, phase: str, cause: str, message: Optional[str] = None):
        player = self._get_player(name)
        if player.status == PlayerStatus.DEAD:
            return

        was_sheriff = self.state.sheriff_name == player.name
        player.status = PlayerStatus.DEAD
        self._record_history_death(name, phase)
        await self._emit("death", {"player": name, "cause": cause, "role": ROLE_NAMES_ZH[player.role], "message": message or f"{name} 死亡。"})
        if self._refresh_private_fact_notes():
            await self._emit_agent_notes_update()

        if was_sheriff:
            await self._transfer_sheriff_badge(player)

        if player.role == Role.WOLF_BEAUTY and self.state.current_charmed_target:
            target_name = self.state.current_charmed_target
            if target_name != player.name and self._get_player(target_name).status == PlayerStatus.ALIVE:
                await self._kill_player(target_name, "wolf_beauty", "wolf_beauty", f"狼美人 {player.name} 出局，{target_name} 殉情死亡。")
            self.state.current_charmed_target = None

        if player.role == Role.HUNTER and cause not in NO_GUN_CAUSES:
            await self._gun_shot(player, "hunter_revenge", f"猎人 {player.name} 开枪带走了 {{target}}！")

        if player.role == Role.WOLF_KING and cause not in NO_GUN_CAUSES:
            await self._gun_shot(player, "wolf_king_revenge", f"狼王 {player.name} 开枪带走了 {{target}}！")

    async def _gun_shot(self, shooter: Player, phase: str, template: str):
        targets = self._alive_targets(exclude=shooter.name)
        if not targets:
            return
        ctx = AgentContext(shooter, self.state)
        result = await self._agent_action(
            shooter,
            ctx.build_discuss_system_prompt(),
            ctx.build_gun_shot_user_prompt(targets),
            temp=0.3,
            allow_dead_action=True,
        )
        target = (result.get("action") or {}).get("shoot_target")
        if target not in targets:
            target = random.choice(targets)
        await self._record_private_thought(shooter, result, phase, f"带走目标：{target}", allow_dead=True)
        await self._kill_player(target, phase, phase, template.format(target=target))

    async def _resolve_night(self, reveal: bool = True):
        killed: list[str] = []
        wolf_target = self.state.night_actions.werewolf_target
        guarded = wolf_target and wolf_target == self.state.night_actions.guard_target
        saved = self.state.night_actions.witch_save

        if wolf_target:
            if guarded and saved:
                if not self.state.rules.same_guard_save_survives:
                    killed.append(wolf_target)
            elif not guarded and not saved:
                killed.append(wolf_target)

        if self.state.night_actions.witch_poison_target:
            killed.append(self.state.night_actions.witch_poison_target)

        if self.state.night_actions.reflected_target:
            killed.append(self.state.night_actions.reflected_target)

        unique_killed: list[str] = []
        for name in killed:
            if name not in unique_killed:
                unique_killed.append(name)

        if not reveal:
            self._pending_night_reveal = True
            self._pending_night_kills = unique_killed
            self.state.night_kills = []
            self.state.gm_announcement = ""
            return

        await self._reveal_night_kills(unique_killed)

    async def _reveal_night_kills(self, unique_killed: list[str]) -> bool:
        self.state.night_kills = unique_killed
        if unique_killed:
            self.state.gm_announcement = f"昨夜，{'、'.join(unique_killed)} 倒在了血泊中。"
        else:
            self.state.gm_announcement = "昨夜是平安夜，没有人死亡。"

        await self._emit("gm_announcement", {"message": self.state.gm_announcement, "deaths": unique_killed})

        for name in unique_killed:
            cause = "night"
            if name == self.state.night_actions.witch_poison_target:
                cause = "witch_poison"
            elif name == self.state.night_actions.reflected_target:
                cause = self.state.night_actions.reflected_reason or "reflect"
            await self._kill_player(name, "night", cause)

        return await self._check_and_emit_winner()

    async def _reveal_pending_night(self) -> bool:
        if not self._pending_night_reveal:
            return False

        unique_killed = list(self._pending_night_kills)
        self._pending_night_reveal = False
        self._pending_night_kills = []
        return await self._reveal_night_kills(unique_killed)

    async def _resolve_knight_duel(self, knight: Player, target_name: str, result: dict):
        target = self._get_player(target_name)
        await self._record_private_thought(knight, result, "knight_duel", f"决斗目标：{target_name}")
        self.state.history.append({"type": "knight_duel", "player": knight.name, "target": target_name, "round": self.state.round_number})

        if self._is_wolf(target):
            await self._kill_player(target_name, "knight_duel", "knight_duel", f"骑士 {knight.name} 决斗成功，{target_name} 当场出局。")
        else:
            await self._kill_player(knight.name, "knight_duel", "knight_duel", f"骑士 {knight.name} 决斗失败，自己出局。")

    async def _werewolf_day_self_destruct(self, wolf: Player, result: dict):
        await self._record_private_thought(wolf, result, "werewolf_self_destruct", "白天自爆")
        await self._kill_player(wolf.name, "werewolf_self", "werewolf_self", f"{ROLE_NAMES_ZH[wolf.role]} {wolf.name} 在白天自爆，白天讨论立即结束。")
        await self._emit("vote_result", {"message": f"{ROLE_NAMES_ZH[wolf.role]} {wolf.name} 自爆，白天讨论结束；若游戏未结束，将进入黑夜。"})

    async def _white_wolf_day_explode(self, white_wolf: Player, target_name: str, result: dict):
        await self._record_private_thought(white_wolf, result, "white_wolf_self_destruct", f"白天自爆带走：{target_name}")
        await self._kill_player(white_wolf.name, "white_wolf_self", "white_wolf_self", f"白狼王 {white_wolf.name} 在白天自爆！")
        if self._get_player(target_name).status == PlayerStatus.ALIVE:
            await self._kill_player(target_name, "white_wolf", "white_wolf", f"白狼王 {white_wolf.name} 自爆带走了 {target_name}！")

    async def _offer_wolf_self_destruct_after_speech(self, latest_speaker: str, latest_speech: str, exclude: set[str] | None = None) -> bool:
        excluded = exclude or set()
        for wolf in self._alive_players():
            if wolf.name in excluded or wolf.role not in WOLF_ROLES:
                continue

            ctx = AgentContext(wolf, self.state)
            if not ctx.should_offer_day_self_destruct():
                continue

            result = await self._agent_action(
                wolf,
                ctx.build_discuss_system_prompt(),
                ctx.build_day_self_destruct_reaction_user_prompt(latest_speaker, latest_speech),
                temp=0.35,
            )
            action = result.get("action") or {}

            if wolf.role == Role.WHITE_WOLF and self.state.rules.white_wolf_explode_during_day:
                target = action.get("shoot_target")
                if target in self._alive_targets(exclude=wolf.name):
                    await self._white_wolf_day_explode(wolf, target, result)
                    await self._check_and_emit_winner()
                    return True
            elif wolf.role != Role.WHITE_WOLF and action.get("self_destruct"):
                await self._werewolf_day_self_destruct(wolf, result)
                await self._check_and_emit_winner()
                return True

            await self._record_private_thought(wolf, result, "werewolf_self_destruct_check", f"听完 {latest_speaker} 发言后选择不自爆")

        return False

    async def _day_phase(self):
        self.state.phase = Phase.DAY_ANNOUNCE
        if self._refresh_private_fact_notes():
            await self._emit_agent_notes_update()
        await self._emit("phase_change", {"phase": "day_announce", "round": self.state.round_number})
        await asyncio.sleep(1)

        await self._elect_sheriff()

        if self._pending_night_reveal:
            if await self._reveal_pending_night():
                return
            if self.state.rules.first_night_last_words and self.state.round_number == 1 and not self.state.winner:
                for name in self.state.night_kills:
                    await self._last_words(self._get_player(name))

        self.state.phase = Phase.DAY_DISCUSS
        await self._emit("phase_change", {"phase": "day_discuss", "round": self.state.round_number})

        for player in self._determine_speak_order():
            if player.status != PlayerStatus.ALIVE:
                continue

            if self.state.silenced_player == player.name:
                speech = SpeechRecord(
                    speaker=player.name,
                    inner_thought="我被禁言了，今天无法公开发言。",
                    public_speech="（被禁言，本轮无法发言）",
                    round_number=self.state.round_number,
                    phase="discuss",
                    skill_info="因禁言长老效果，本轮无法发言",
                )
                self.state.speeches.append(speech)
                await self._emit("speech", {"speaker": player.name, "public_speech": speech.public_speech, "inner_thought": speech.inner_thought, "round": self.state.round_number, "phase": speech.phase})
                await self._digest_public_speech_for_observers(player.name, speech.public_speech, speech.phase)
                if await self._offer_wolf_self_destruct_after_speech(player.name, speech.public_speech, exclude={player.name}):
                    return
                continue

            ctx = AgentContext(player, self.state)
            result = await self._agent_action(player, ctx.build_discuss_system_prompt(), ctx.build_discuss_user_prompt(), temp=0.8)
            speech = SpeechRecord(
                speaker=player.name,
                inner_thought=result.get("inner_thought", ""),
                public_speech=result.get("public_speech", ""),
                round_number=self.state.round_number,
                phase="discuss",
            )
            self.state.speeches.append(speech)
            await self._emit("speech", {"speaker": player.name, "public_speech": speech.public_speech, "inner_thought": speech.inner_thought, "round": self.state.round_number, "phase": speech.phase})
            await self._digest_public_speech_for_observers(player.name, speech.public_speech, speech.phase)

            action = result.get("action") or {}
            can_self_destruct_now = ctx.should_offer_day_self_destruct()

            if player.role == Role.WHITE_WOLF and self.state.rules.white_wolf_explode_during_day and can_self_destruct_now:
                target = action.get("shoot_target")
                if target in self._alive_targets(exclude=player.name):
                    await self._white_wolf_day_explode(player, target, result)
                    if await self._check_and_emit_winner():
                        return
                    return

            if player.role in WOLF_ROLES and player.role != Role.WHITE_WOLF and can_self_destruct_now and action.get("self_destruct"):
                await self._werewolf_day_self_destruct(player, result)
                if await self._check_and_emit_winner():
                    return
                return

            if await self._offer_wolf_self_destruct_after_speech(player.name, speech.public_speech, exclude={player.name}):
                return

            if player.role == Role.KNIGHT and not self._has_used_knight_duel(player.name):
                target = action.get("shoot_target")
                if target in self._alive_targets(exclude=player.name):
                    await self._resolve_knight_duel(player, target, result)
                    if await self._check_and_emit_winner():
                        return
                    if self.state.rules.knight_duel_ends_discussion:
                        break

            if not self.state.auto_advance:
                await asyncio.sleep(self.state.step_delay)

        # 警长归票阶段：警长存活且有投票权时，先进行归票
        sheriff_vote_public: str | None = None
        sheriff = self._get_player(self.state.sheriff_name) if self.state.sheriff_name else None
        if sheriff and sheriff.status == PlayerStatus.ALIVE and sheriff.vote_right:
            ctx = AgentContext(sheriff, self.state)
            result = await self._agent_action(
                sheriff,
                ctx.build_discuss_system_prompt(),
                ctx.build_sheriff_guipiao_user_prompt(),
                temp=0.4,
            )
            sheriff_vote_public = (result.get("action") or {}).get("vote_target")
            speech = SpeechRecord(
                speaker=sheriff.name,
                inner_thought=result.get("inner_thought", ""),
                public_speech=result.get("public_speech", ""),
                round_number=self.state.round_number,
                phase="sheriff_guipiao",
            )
            self.state.speeches.append(speech)
            await self._emit("speech", {
                "speaker": sheriff.name,
                "public_speech": speech.public_speech,
                "inner_thought": speech.inner_thought,
                "round": self.state.round_number,
                "phase": speech.phase,
            })
            await self._emit("sheriff_vote", {
                "sheriff": sheriff.name,
                "vote_target": sheriff_vote_public,
            })

        self.state.phase = Phase.DAY_VOTE
        await self._emit("phase_change", {"phase": "day_vote", "round": self.state.round_number})

        alive_players = self._alive_players()
        eligible_voters = [player.name for player in alive_players if player.vote_right]
        day_vote_event = {
            "type": "day_vote",
            "round": self.state.round_number,
            "sheriff": self.state.sheriff_name,
            "eligible_voters": eligible_voters,
            "vote_rounds": [],
            "votes": [],
            "counts": {},
            "actual_voters": [],
            "missing_voters": eligible_voters,
            "tied_targets": [],
            "eliminated": None,
        }
        self.state.history.append(day_vote_event)

        eliminated = None
        tied_targets: list[str] = []
        counts: dict[str, float] = {}
        active_candidates = [player.name for player in alive_players]
        vote_rounds: list[dict] = day_vote_event["vote_rounds"]

        for vote_round in range(1, 4):
            if vote_round > 1:
                await self._emit("vote_result", {"message": f"白天放逐第 {vote_round} 轮 PK，目标：{'、'.join(active_candidates)}。"})
                for candidate_name in active_candidates:
                    candidate = self._get_player(candidate_name)
                    if candidate.status != PlayerStatus.ALIVE:
                        continue
                    ctx = AgentContext(candidate, self.state)
                    result = await self._agent_action(
                        candidate,
                        ctx.build_discuss_system_prompt(),
                        ctx.build_day_vote_runoff_speech_user_prompt(active_candidates, vote_round, vote_rounds),
                        temp=0.8,
                    )
                    speech = SpeechRecord(
                        speaker=candidate.name,
                        inner_thought=result.get("inner_thought", ""),
                        public_speech=result.get("public_speech", ""),
                        round_number=self.state.round_number,
                        phase="day_vote_runoff",
                    )
                    self.state.speeches.append(speech)
                    await self._emit("speech", {"speaker": candidate.name, "public_speech": speech.public_speech, "inner_thought": speech.inner_thought, "round": self.state.round_number, "phase": speech.phase})
                    await self._digest_public_speech_for_observers(candidate.name, speech.public_speech, speech.phase)
                    if not self.state.auto_advance:
                        await asyncio.sleep(self.state.step_delay)

            votes: list[VoteRecord] = []
            # 如果警长已在归票阶段投票，预填入警长的票
            sheriff_name = self.state.sheriff_name
            if sheriff_vote_public and vote_round == 1:
                votes.append(VoteRecord(voter=sheriff_name, target=sheriff_vote_public))
                await self._emit("vote_cast", {"voter": sheriff_name, "target": sheriff_vote_public, "round": vote_round})

            await self._emit("vote_result", {"message": f"白天放逐第 {vote_round} 轮开始投票。可投目标：{'、'.join(active_candidates)}。"})
            for player in self._alive_players():
                if not player.vote_right:
                    continue
                # 警长已在归票阶段投过票，跳过
                if sheriff_vote_public and vote_round == 1 and player.name == sheriff_name:
                    continue
                ctx = AgentContext(player, self.state)
                prompt = ctx.build_vote_user_prompt(active_candidates, vote_round, vote_rounds)
                result = await self._agent_action(player, ctx.build_vote_system_prompt(), prompt, temp=0.4)
                target = (result.get("action") or {}).get("vote_target")
                valid_targets = [candidate for candidate in active_candidates if candidate != player.name] + ["abstain"]
                if target not in valid_targets:
                    target = random.choice(valid_targets)
                await self._record_private_thought(player, result, "vote", f"第 {vote_round} 轮投票：{target}")
                votes.append(VoteRecord(voter=player.name, target=target))
                await self._emit("vote_cast", {"voter": player.name, "target": target, "round": vote_round})

            alive_players = self._alive_players()
            weight_by_voter = self._vote_weights(alive_players)
            eliminated, tied_targets, counts = tally_votes(votes, weight_by_voter)
            if eliminated:
                tied_targets = []

            round_eligible_voters = [player.name for player in alive_players if player.vote_right]
            round_summary = {
                "round": vote_round,
                "candidates": list(active_candidates),
                "votes": [{"voter": vote.voter, "target": vote.target} for vote in votes],
                "counts": counts,
                "eligible_voters": round_eligible_voters,
                "actual_voters": [vote.voter for vote in votes],
                "missing_voters": [name for name in round_eligible_voters if name not in {vote.voter for vote in votes}],
                "tied_targets": tied_targets,
                "eliminated": eliminated,
            }
            vote_rounds.append(round_summary)
            day_vote_event.update(
                {
                    "votes": round_summary["votes"],
                    "counts": counts,
                    "eligible_voters": round_summary["eligible_voters"],
                    "actual_voters": round_summary["actual_voters"],
                    "missing_voters": round_summary["missing_voters"],
                    "tied_targets": tied_targets,
                    "eliminated": eliminated,
                }
            )

            if eliminated or not tied_targets:
                break

            if self._has_alive_sheriff():
                await self._emit("vote_result", {"message": f"白天放逐第 {vote_round} 轮平票（{self._format_vote_counts(counts)}），警徽仍在场，不进入多轮 PK，交由警长归票处理。"})
                break

            if vote_round < 3:
                await self._emit("vote_result", {"message": f"白天放逐第 {vote_round} 轮平票（{self._format_vote_counts(counts)}），平票目标进入下一轮 PK。"})
                active_candidates = tied_targets
                continue

            await self._emit("vote_result", {"message": f"白天放逐第 {vote_round} 轮仍然平票（{self._format_vote_counts(counts)}），进入最终平票处理。"})

        if not eliminated:
            if tied_targets and self._has_alive_sheriff():
                sheriff = self._get_player(self.state.sheriff_name)
                ctx = AgentContext(sheriff, self.state)
                result = await self._agent_action(sheriff, ctx.build_vote_system_prompt(), ctx.build_sheriff_tiebreak_user_prompt(tied_targets, self._format_vote_counts(counts)), temp=0.3)
                target = (result.get("action") or {}).get("vote_target")
                if target not in tied_targets:
                    target = random.choice(tied_targets)
                await self._record_private_thought(sheriff, result, "sheriff_tiebreak", f"归票：{target}")
                day_vote_event["sheriff_tiebreak"] = {"sheriff": sheriff.name, "target": target}
                day_vote_event["eliminated"] = target
                await self._emit("vote_result", {"message": f"投票平票（{self._format_vote_counts(counts)}），警长 {sheriff.name} 归票放逐 {target}。"})
                eliminated = target
            else:
                day_vote_event["eliminated"] = None
                tie_message = f"平票（{self._format_vote_counts(counts)}），本轮无人被放逐。" if counts else "本轮无人出票，本轮无人被放逐。"
                await self._emit("vote_result", {"message": tie_message})
                await self._check_and_emit_winner()
                return

        if not eliminated:
            await self._emit("vote_result", {"message": "平票，本轮无人被放逐。"})
            await self._check_and_emit_winner()
            return

        player = self._get_player(eliminated)
        if player.role == Role.IDIOT:
            player.vote_right = False
            day_vote_event["eliminated"] = None
            day_vote_event["idiot_reveal"] = eliminated
            self.state.day_eliminated = None
            await self._emit("death", {"player": eliminated, "cause": "idiot_reveal", "role": ROLE_NAMES_ZH[player.role], "message": f"投票结果：{eliminated} 被放逐，但翻牌亮出了白痴身份，免于死亡，并永久失去投票权。"})
        else:
            self.state.day_eliminated = eliminated
            await self._kill_player(eliminated, "vote", "vote", f"投票结果：{eliminated} 被放逐。")
            await self._last_words(player, "你被白天投票放逐了。这是你的遗言时间。你可以最后一次公开表明或延续自己的身份口径。action 设为 null。")

        await self._check_and_emit_winner()

    async def _post_game(self):
        self.state.phase = Phase.GAME_OVER
        self.state.finished_at = datetime.now().isoformat()
        winner_label = "好人阵营" if self.state.winner == "village" else "狼人阵营"
        await self._emit("phase_change", {"phase": "game_over", "winner": self.state.winner, "message": f"游戏结束，{winner_label} 获胜！"})

        reflection_failures: list[dict[str, str]] = []
        for player in self.state.players:
            if not player.is_ai:
                continue
            try:
                client = self._get_client(player)
                model = self._get_model(player)
                memory = load_agent_memory(player.name)
                memory = await agent_reflect(client, model, self.state, player.name, memory)
                save_agent_memory(memory)
            except Exception as exc:
                logger.error("Reflection failed for %s: %s", player.name, exc)
                reflection_failures.append({"player": player.name, "error": str(exc)})
                try:
                    memory = load_agent_memory(player.name)
                    memory = agent_reflect_fallback(self.state, player.name, memory, reason=str(exc))
                    save_agent_memory(memory)
                except Exception as fallback_exc:
                    logger.error("Reflection fallback failed for %s: %s", player.name, fallback_exc)

        save_game_log(self.state.game_id, self.state.model_dump())
        await self._emit("game_saved", {"game_id": self.state.game_id, "reflection_failures": reflection_failures})


def load_agent_memory(name: str) -> AgentMemory:
    from app.memory.store import load_agent_memory as _load

    return _load(name)
