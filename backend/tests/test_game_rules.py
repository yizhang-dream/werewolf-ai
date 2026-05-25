import asyncio
import unittest
from unittest import mock

from app.agents.base import AgentContext
from app.engine.game_manager import GameManager
from app.engine.win_check import check_win_condition
from app.models.game import GameRules, GameState, NightAction, Phase, Player, PlayerStatus, Role, SpeechRecord, WinRule, WitchSelfSaveRule, WolfChatRecord


def make_player(name: str, role: Role, **overrides) -> Player:
    return Player(
        name=name,
        role=role,
        personality=overrides.pop("personality", ""),
        llm_provider=overrides.pop("llm_provider", "Mock Provider"),
        model_name=overrides.pop("model_name", "mock-model"),
        **overrides,
    )


def make_manager(
    players: list[Player],
    *,
    rules: GameRules | None = None,
    round_number: int = 1,
    phase: Phase = Phase.SETUP,
    night_actions: NightAction | None = None,
    sheriff_name: str | None = None,
    day_eliminated: str | None = None,
    auto_advance: bool = True,
) -> GameManager:
    return GameManager(
        GameState(
            game_id="test-game",
            players=players,
            phase=phase,
            round_number=round_number,
            night_actions=night_actions or NightAction(),
            auto_advance=auto_advance,
            rules=rules or GameRules(),
            sheriff_name=sheriff_name,
            day_eliminated=day_eliminated,
        )
    )


class GameRuleTests(unittest.IsolatedAsyncioTestCase):
    def test_wolf_secret_info_lists_confirmed_roster_and_excludes_non_teammates(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        dead_wolf = make_player("DeadWolf", Role.WEREWOLF, status=PlayerStatus.DEAD)
        alive_wolf = make_player("AliveWolf", Role.WOLF_KING)
        hunter = make_player("Hunter", Role.HUNTER)
        manager = make_manager([wolf, dead_wolf, alive_wolf, hunter], round_number=2, phase=Phase.DAY_DISCUSS)

        prompt = AgentContext(wolf, manager.state).build_discuss_system_prompt()

        self.assertIn("你确认的狼队名单", prompt)
        self.assertIn("DeadWolf（狼人，已出局）", prompt)
        self.assertIn("AliveWolf（狼王，存活）", prompt)
        self.assertIn("名单外玩家不是你的已知狼队友", prompt)
        self.assertNotIn("Hunter（猎人", prompt)

    def test_wolf_self_destruct_prompt_does_not_frame_teammate_pressure_as_protection(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        dead_wolf = make_player("DeadWolf", Role.WEREWOLF, status=PlayerStatus.DEAD)
        alive_wolf = make_player("AliveWolf", Role.WOLF_KING)
        hunter = make_player("Hunter", Role.HUNTER)
        manager = make_manager([wolf, dead_wolf, alive_wolf, hunter], round_number=3, phase=Phase.DAY_DISCUSS)

        ctx = AgentContext(wolf, manager.state)
        prompt = ctx.build_day_self_destruct_reaction_user_prompt("Hunter", "AliveWolf looks suspicious, but I want to push Hunter.")

        self.assertEqual(ctx._visible_wolf_count_including_self(), 2)
        self.assertIn("你确认的狼队名单", prompt)
        self.assertIn("DeadWolf（狼人，已出局）", prompt)
        self.assertIn("AliveWolf（狼王，存活）", prompt)
        self.assertIn("自爆一般不能真正保护队友", prompt)
        self.assertIn("仅因为队友被怀疑，往往不是充分理由", prompt)
        self.assertIn("自爆会坐实你是狼人", prompt)
        self.assertIn("让剩余队友更难起跳", prompt)
        self.assertIn("优先比较穿衣服、悍跳/对跳、抗辩、倒钩、冲票、转移焦点", prompt)
        self.assertIn("你自己是否被严重怀疑", prompt)
        self.assertNotIn("保护更高价值狼队友", prompt)
        self.assertNotIn("保护确认狼队友", prompt)
        self.assertNotIn("Hunter（猎人", prompt)

    def test_last_wolf_self_destruct_prompt_says_no_future_knife(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        dead_wolf = make_player("DeadWolf", Role.WEREWOLF, status=PlayerStatus.DEAD)
        villager_one = make_player("VillagerOne", Role.VILLAGER)
        villager_two = make_player("VillagerTwo", Role.VILLAGER)
        manager = make_manager([wolf, dead_wolf, villager_one, villager_two], round_number=3, phase=Phase.DAY_DISCUSS)
        ctx = AgentContext(wolf, manager.state)

        self.assertTrue(ctx._is_last_visible_wolf_alive())
        context_block = ctx._day_self_destruct_context_block()
        discuss_prompt = ctx.build_discuss_user_prompt()
        reaction_prompt = ctx.build_day_self_destruct_reaction_user_prompt("VillagerOne", "Wolf should explain the vote.")

        for prompt in (context_block, discuss_prompt, reaction_prompt):
            self.assertIn("LAST_WOLF_NO_NIGHT_KILL", prompt)
        self.assertIn("no one can perform a night kill", context_block)
        self.assertIn("do not imagine", discuss_prompt + reaction_prompt)
        self.assertIn("usually loses", context_block)

    def test_wolf_day_prompt_encourages_deception_before_self_destruct(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        teammate = make_player("Mate", Role.WEREWOLF)
        seer = make_player("Seer", Role.SEER)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, teammate, seer, villager], round_number=2, phase=Phase.DAY_DISCUSS)

        prompt = AgentContext(wolf, manager.state).build_discuss_system_prompt() + AgentContext(wolf, manager.state).build_discuss_user_prompt()

        self.assertIn("狼人白天对抗策略", prompt)
        self.assertIn("游戏内说谎、伪装、诈身份和误导归票都是规则允许的竞技策略", prompt)
        self.assertIn("穿衣服", prompt)
        self.assertIn("悍跳/对跳", prompt)
        self.assertIn("不要把倒钩当成默认安全路线", prompt)
        self.assertIn("假身份口径", prompt)
        self.assertIn("非队友起跳者", prompt)
        self.assertIn("不要在 inner_thought 或 private_note 中把他写成“悍跳狼/队友悍跳”", prompt)
        self.assertIn("身份对抗优先考虑对跳", prompt)
        self.assertIn("质疑逻辑/票型只能当作支撑材料", prompt)
        self.assertNotIn("你可以选择对跳、质疑其逻辑", prompt)
        self.assertIn("不要把倒钩当成默认安全路线", prompt)
        self.assertIn("不是只用等待队友解释自己的选择", prompt)
        self.assertIn("由你承担起跳", prompt)
        self.assertIn("狼队公开打法提醒", prompt)
        self.assertIn("没有哪一个应当自动成为默认答案", prompt)
        self.assertIn("根据你自己的位置、发言质量、票权和队友状态决定公开姿态", prompt)
        self.assertIn("狼人神职衣服候选提醒", prompt)
        self.assertIn("神职衣服也是可选公开打法", prompt)
        self.assertIn("猎人衣服", prompt)
        self.assertIn("女巫/守卫衣服", prompt)
        self.assertIn("白痴衣服", prompt)
        self.assertNotIn("CLAIM_PLAN", prompt)
        self.assertNotIn("必须在 inner_thought", prompt)

    def test_wolf_sheriff_prompts_require_self_claim_evaluation(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        teammate = make_player("Mate", Role.WEREWOLF)
        seer = make_player("Seer", Role.SEER)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, teammate, seer, villager], round_number=1, phase=Phase.DAY_DISCUSS)
        ctx = AgentContext(wolf, manager.state)

        system_prompt = ctx.build_discuss_system_prompt()
        nomination_prompt = ctx.build_sheriff_nomination_user_prompt()
        campaign_prompt = ctx.build_sheriff_campaign_user_prompt(["Wolf", "Seer"])
        vote_prompt = ctx.build_sheriff_vote_user_prompt(["Wolf", "Seer"], [])

        self.assertIn("狼人警上身份压力提醒", system_prompt)
        self.assertIn("目前没有从关键词线索中看到已确认队友承担预言家衣服", system_prompt)
        self.assertIn("自己悍跳预言家抢警徽", system_prompt)
        self.assertIn("不要把“等队友悍跳”当成唯一计划", system_prompt)
        self.assertIn("狼队公共策略资料", system_prompt)
        self.assertIn("假验人", system_prompt)
        self.assertIn("金水/查杀理由", system_prompt)
        self.assertIn("自己上警悍跳/抢警徽", nomination_prompt)
        self.assertIn("不要把等待队友起跳当成唯一理由", nomination_prompt)
        self.assertIn("private_note 必须写清你的竞选衣服", nomination_prompt)
        self.assertIn("验人目标/金水或查杀/警徽流", nomination_prompt)
        self.assertIn("自己穿预言家衣服抢警徽", campaign_prompt)
        self.assertIn("公开发言不能只说“我会盘逻辑/我适合带队/后面给惊喜”", campaign_prompt)
        self.assertIn("必须明确落地一个可持续身份口径", campaign_prompt)
        self.assertIn("验人目标、金水/查杀理由和警徽流", campaign_prompt)
        self.assertIn("倒钩不是默认答案", vote_prompt)
        self.assertIn("如果你是狼人且选择不上警/倒钩", nomination_prompt)
        self.assertIn("它如何服务于你的后续身份、票型或刀口计划", campaign_prompt)
        self.assertIn("如果你投倒钩票", vote_prompt)

        villager_prompt = AgentContext(villager, manager.state).build_discuss_system_prompt()
        self.assertNotIn("狼队公共策略资料", villager_prompt)

    def test_wolf_prompt_keeps_non_teammate_claimants_out_of_pack(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        teammate = make_player("Mate", Role.WEREWOLF)
        seer = make_player("Seer", Role.SEER)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, teammate, seer, villager], round_number=1, phase=Phase.DAY_DISCUSS)
        manager.state.speeches.append(
            SpeechRecord(
                speaker="Seer",
                inner_thought="private",
                public_speech="我是预言家，昨晚验了 Villager 是金水。",
                round_number=1,
                phase="sheriff_campaign",
            )
        )

        prompt = AgentContext(wolf, manager.state).build_discuss_system_prompt()

        self.assertIn("你确认的狼队名单：Mate（狼人，存活）", prompt)
        self.assertIn("Seer 的发言出现 预言家 关键词", prompt)
        self.assertIn("不是系统盖章", prompt)
        self.assertIn("名单外玩家不是你的已知狼队友", prompt)
        self.assertIn("不能在真实推理里直接称其为“悍跳狼”", prompt)
        self.assertIn("公开狼面较高但未确认", prompt)

    def test_wolf_sheriff_strategy_detects_confirmed_teammate_seer_claim(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        teammate = make_player("Mate", Role.WEREWOLF)
        seer = make_player("Seer", Role.SEER)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, teammate, seer, villager], round_number=1, phase=Phase.DAY_DISCUSS)
        manager.state.speeches.append(
            SpeechRecord(
                speaker="Mate",
                inner_thought="private",
                public_speech="我是预言家，昨晚验了 Villager 是金水。",
                round_number=1,
                phase="sheriff_campaign",
            )
        )

        prompt = AgentContext(wolf, manager.state).build_discuss_system_prompt()

        self.assertIn("已确认队友中已有预言家关键词线索：Mate", prompt)
        self.assertIn("判断其是否正在承担预言家衣服", prompt)
        self.assertIn("选择配合、倒钩、补强或切割", prompt)

    def test_hidden_wolf_does_not_receive_unawakened_roster(self):
        hidden = make_player("Hidden", Role.HIDDEN_WOLF)
        wolf = make_player("Wolf", Role.WEREWOLF)
        manager = make_manager([hidden, wolf], round_number=1, phase=Phase.DAY_DISCUSS)

        prompt = AgentContext(hidden, manager.state).build_discuss_system_prompt()

        self.assertIn("你当前没有可确认的狼队友", prompt)
        self.assertNotIn("Wolf（狼人", prompt)

    def test_witch_self_save_never_disallows_saving_herself(self):
        witch = make_player("Witch", Role.WITCH)
        manager = make_manager(
            [witch],
            rules=GameRules(witch_self_save_rule=WitchSelfSaveRule.NEVER),
            round_number=1,
        )

        self.assertFalse(manager._can_witch_self_save(witch, "Witch"))
        self.assertTrue(manager._can_witch_self_save(witch, "Other"))

    def test_witch_self_save_first_night_only_depends_on_round(self):
        witch = make_player("Witch", Role.WITCH)
        first_night_manager = make_manager(
            [witch],
            rules=GameRules(witch_self_save_rule=WitchSelfSaveRule.FIRST_NIGHT_ONLY),
            round_number=1,
        )
        later_night_manager = make_manager(
            [witch],
            rules=GameRules(witch_self_save_rule=WitchSelfSaveRule.FIRST_NIGHT_ONLY),
            round_number=2,
        )

        self.assertTrue(first_night_manager._can_witch_self_save(witch, "Witch"))
        self.assertFalse(later_night_manager._can_witch_self_save(witch, "Witch"))

    async def test_resolve_night_same_guard_and_save_kills_when_rule_disabled(self):
        players = [
            make_player("Wolf", Role.WEREWOLF),
            make_player("Witch", Role.WITCH),
            make_player("Guard", Role.GUARD),
            make_player("Target", Role.VILLAGER),
        ]
        manager = make_manager(
            players,
            rules=GameRules(same_guard_save_survives=False),
            night_actions=NightAction(werewolf_target="Target", guard_target="Target", witch_save=True),
        )

        manager._emit = mock.AsyncMock()
        manager._kill_player = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)

        await manager._resolve_night()

        self.assertEqual(manager.state.night_kills, ["Target"])
        manager._kill_player.assert_awaited_once_with("Target", "night", "night")

    async def test_resolve_night_same_guard_and_save_survives_when_rule_enabled(self):
        players = [
            make_player("Wolf", Role.WEREWOLF),
            make_player("Witch", Role.WITCH),
            make_player("Guard", Role.GUARD),
            make_player("Target", Role.VILLAGER),
        ]
        manager = make_manager(
            players,
            rules=GameRules(same_guard_save_survives=True),
            night_actions=NightAction(werewolf_target="Target", guard_target="Target", witch_save=True),
        )

        manager._emit = mock.AsyncMock()
        manager._kill_player = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)

        await manager._resolve_night()

        self.assertEqual(manager.state.night_kills, [])
        manager._kill_player.assert_not_awaited()

    async def test_first_night_deaths_can_be_deferred_until_after_sheriff_election(self):
        players = [
            make_player("Wolf", Role.WEREWOLF),
            make_player("Target", Role.VILLAGER),
            make_player("Voter", Role.VILLAGER),
        ]
        manager = make_manager(
            players,
            rules=GameRules(sheriff_enabled=True),
            round_number=1,
            night_actions=NightAction(werewolf_target="Target"),
        )

        manager._emit = mock.AsyncMock()
        manager._kill_player = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)

        await manager._resolve_night(reveal=False)

        self.assertTrue(manager._pending_night_reveal)
        self.assertEqual(manager._pending_night_kills, ["Target"])
        self.assertEqual(manager.state.night_kills, [])
        self.assertEqual(manager.state.gm_announcement, "")
        self.assertEqual(manager._get_player("Target").status, PlayerStatus.ALIVE)
        manager._emit.assert_not_awaited()
        manager._kill_player.assert_not_awaited()

        await manager._reveal_pending_night()

        self.assertFalse(manager._pending_night_reveal)
        self.assertEqual(manager.state.night_kills, ["Target"])
        self.assertIn("Target", manager.state.gm_announcement)
        manager._emit.assert_awaited()
        manager._kill_player.assert_awaited_once_with("Target", "night", "night")

    async def test_day_phase_runs_sheriff_election_before_revealing_first_night_deaths(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        target = make_player("Target", Role.VILLAGER)
        voter = make_player("Voter", Role.VILLAGER)
        manager = make_manager(
            [wolf, target, voter],
            rules=GameRules(sheriff_enabled=True),
            round_number=1,
            phase=Phase.DAY_ANNOUNCE,
            auto_advance=True,
        )
        manager._pending_night_reveal = True
        manager._pending_night_kills = ["Target"]
        manager._emit = mock.AsyncMock()
        manager._reveal_pending_night = mock.AsyncMock(return_value=True)

        async def elect_sheriff():
            self.assertEqual(target.status, PlayerStatus.ALIVE)
            self.assertEqual(manager.state.night_kills, [])
            self.assertEqual(manager.state.gm_announcement, "")

        manager._elect_sheriff = mock.AsyncMock(side_effect=elect_sheriff)

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        manager._elect_sheriff.assert_awaited_once()
        manager._reveal_pending_night.assert_awaited_once()

    async def test_second_night_death_does_not_trigger_last_words(self):
        target = make_player("Target", Role.VILLAGER)
        witness = make_player("Witness", Role.VILLAGER)
        manager = make_manager(
            [target, witness],
            rules=GameRules(sheriff_enabled=False),
            round_number=1,
            phase=Phase.DAY_DISCUSS,
            auto_advance=True,
        )
        manager._emit = mock.AsyncMock()
        manager._last_words = mock.AsyncMock()

        async def resolve_second_night(*_args, **_kwargs):
            target.status = PlayerStatus.DEAD
            manager.state.night_kills = ["Target"]
            return False

        manager._resolve_night = mock.AsyncMock(side_effect=resolve_second_night)

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._night_phase()

        self.assertEqual(manager.state.round_number, 2)
        self.assertEqual(manager.state.night_kills, ["Target"])
        manager._last_words.assert_not_awaited()

    def test_sheriff_vote_weight_uses_configured_multiplier(self):
        sheriff = make_player("Sheriff", Role.VILLAGER)
        teammate = make_player("Teammate", Role.VILLAGER)
        manager = make_manager(
            [sheriff, teammate],
            rules=GameRules(sheriff_enabled=True, sheriff_vote_multiplier=1.5),
            sheriff_name="Sheriff",
        )

        self.assertEqual(manager._vote_weight(sheriff), 1.5)
        self.assertEqual(manager._vote_weight(teammate), 1.0)
        self.assertEqual(manager._vote_weights([sheriff, teammate]), {"Sheriff": 1.5, "Teammate": 1.0})

    async def test_resolve_knight_duel_kills_target_when_target_is_wolf(self):
        knight = make_player("Knight", Role.KNIGHT)
        wolf = make_player("Wolf", Role.WEREWOLF)
        manager = make_manager([knight, wolf], round_number=2)

        manager._record_private_thought = mock.AsyncMock()
        manager._kill_player = mock.AsyncMock()

        await manager._resolve_knight_duel(knight, "Wolf", {"action": {"shoot_target": "Wolf"}})

        manager._kill_player.assert_awaited_once()
        args = manager._kill_player.await_args.args
        self.assertEqual(args[:3], ("Wolf", "knight_duel", "knight_duel"))
        self.assertEqual(
            manager.state.history[-1],
            {"type": "knight_duel", "player": "Knight", "target": "Wolf", "round": 2},
        )

    async def test_resolve_knight_duel_kills_knight_when_target_is_good(self):
        knight = make_player("Knight", Role.KNIGHT)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([knight, villager], round_number=3)

        manager._record_private_thought = mock.AsyncMock()
        manager._kill_player = mock.AsyncMock()

        await manager._resolve_knight_duel(knight, "Villager", {"action": {"shoot_target": "Villager"}})

        manager._kill_player.assert_awaited_once()
        args = manager._kill_player.await_args.args
        self.assertEqual(args[:3], ("Knight", "knight_duel", "knight_duel"))
        self.assertEqual(manager.state.history[-1]["round"], 3)

    async def test_dead_player_agent_action_and_private_thought_are_skipped(self):
        dead = make_player("Dead", Role.SEER, status=PlayerStatus.DEAD)
        alive = make_player("Alive", Role.VILLAGER)
        manager = make_manager([dead, alive], round_number=2, phase=Phase.NIGHT)
        manager._emit = mock.AsyncMock()

        with mock.patch("app.engine.game_manager.get_structured_response", new_callable=mock.AsyncMock) as structured:
            result = await manager._agent_action(dead, "system", "user")

        self.assertEqual(result["action"], None)
        self.assertEqual(manager.state.agent_notes, {})
        structured.assert_not_awaited()

        await manager._record_private_thought(dead, {"inner_thought": "I should still think."}, "night_seer")

        self.assertEqual(manager.state.speeches, [])

    async def test_gravekeeper_reports_alignment_for_eliminated_player(self):
        keeper = make_player("Keeper", Role.GRAVEKEEPER)
        wolf = make_player("Wolf", Role.WEREWOLF, status=PlayerStatus.DEAD)
        villager = make_player("Villager", Role.VILLAGER, status=PlayerStatus.DEAD)
        wolf_manager = make_manager(
            [keeper, wolf],
            night_actions=NightAction(),
            day_eliminated="Wolf",
        )
        villager_manager = make_manager(
            [keeper, villager],
            night_actions=NightAction(),
            day_eliminated="Villager",
        )

        wolf_manager._record_private_thought = mock.AsyncMock()
        villager_manager._record_private_thought = mock.AsyncMock()

        await wolf_manager._gravekeeper_action()
        await villager_manager._gravekeeper_action()

        wolf_alignment = wolf_manager.state.night_actions.gravekeeper_alignment
        villager_alignment = villager_manager.state.night_actions.gravekeeper_alignment

        self.assertTrue(wolf_alignment.startswith("Wolf "))
        self.assertTrue(villager_alignment.startswith("Villager "))
        self.assertNotEqual(wolf_alignment, villager_alignment)
        wolf_manager._record_private_thought.assert_awaited_once()
        villager_manager._record_private_thought.assert_awaited_once()

    async def test_transfer_sheriff_badge_destroys_badge_when_no_targets(self):
        sheriff = make_player("Sheriff", Role.VILLAGER)
        manager = make_manager([sheriff], sheriff_name="Sheriff")

        manager._emit_sheriff_update = mock.AsyncMock()

        await manager._transfer_sheriff_badge(sheriff)

        self.assertIsNone(manager.state.sheriff_name)
        manager._emit_sheriff_update.assert_awaited_once()
        self.assertEqual(manager._emit_sheriff_update.await_args.kwargs["reason"], "destroyed")

    async def test_transfer_sheriff_badge_passes_to_valid_target(self):
        sheriff = make_player("Sheriff", Role.VILLAGER)
        target = make_player("Target", Role.VILLAGER)
        manager = make_manager([sheriff, target], sheriff_name="Sheriff")

        manager._emit_sheriff_update = mock.AsyncMock()
        manager._record_private_thought = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(return_value={"action": {"transfer_badge_target": "Target"}})

        await manager._transfer_sheriff_badge(sheriff)

        self.assertEqual(manager.state.sheriff_name, "Target")
        manager._record_private_thought.assert_awaited_once()
        self.assertEqual(manager._emit_sheriff_update.await_args.kwargs["reason"], "transfer")

    async def test_sheriff_election_only_non_candidates_vote(self):
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.VILLAGER)
        gamma = make_player("Gamma", Role.WEREWOLF)
        delta = make_player("Delta", Role.VILLAGER)
        manager = make_manager(
            [alpha, beta, gamma, delta],
            rules=GameRules(sheriff_enabled=True),
            round_number=1,
            phase=Phase.DAY_DISCUSS,
        )

        manager._emit = mock.AsyncMock()
        manager._emit_sheriff_update = mock.AsyncMock()
        manager._digest_public_speech_for_observers = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(
            side_effect=[
                {"action": {"run_for_sheriff": True}},
                {"action": {"run_for_sheriff": True}},
                {"action": {"run_for_sheriff": False}},
                {"action": {"run_for_sheriff": False}},
                {"public_speech": "Alpha campaign.", "action": {}},
                {"public_speech": "Beta campaign.", "action": {}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Alpha"}},
            ]
        )

        await manager._elect_sheriff()

        election = next(item for item in manager.state.history if item.get("type") == "sheriff_election")
        self.assertEqual(election["candidates"], ["Alpha", "Beta"])
        self.assertEqual(election["votes"], [{"voter": "Gamma", "target": "Alpha"}, {"voter": "Delta", "target": "Alpha"}])
        self.assertEqual(manager.state.sheriff_name, "Alpha")

    async def test_sheriff_election_allows_two_tied_runoffs_before_vacant(self):
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.VILLAGER)
        gamma = make_player("Gamma", Role.WEREWOLF)
        delta = make_player("Delta", Role.VILLAGER)
        epsilon = make_player("Epsilon", Role.WITCH)
        zeta = make_player("Zeta", Role.HUNTER)
        manager = make_manager(
            [alpha, beta, gamma, delta, epsilon, zeta],
            rules=GameRules(sheriff_enabled=True),
            round_number=1,
            phase=Phase.DAY_DISCUSS,
        )

        manager._emit = mock.AsyncMock()
        manager._emit_sheriff_update = mock.AsyncMock()
        manager._digest_public_speech_for_observers = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(
            side_effect=[
                {"action": {"run_for_sheriff": True}},
                {"action": {"run_for_sheriff": True}},
                {"action": {"run_for_sheriff": False}},
                {"action": {"run_for_sheriff": False}},
                {"action": {"run_for_sheriff": False}},
                {"action": {"run_for_sheriff": False}},
                {"public_speech": "Alpha campaign.", "action": {}},
                {"public_speech": "Beta campaign.", "action": {}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Beta"}},
                {"action": {"vote_target": "Beta"}},
                {"public_speech": "Alpha runoff two.", "action": {}},
                {"public_speech": "Beta runoff two.", "action": {}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Beta"}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Beta"}},
                {"public_speech": "Alpha runoff three.", "action": {}},
                {"public_speech": "Beta runoff three.", "action": {}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Alpha"}},
                {"action": {"vote_target": "Beta"}},
            ]
        )

        await manager._elect_sheriff()

        election = next(item for item in manager.state.history if item.get("type") == "sheriff_election")
        self.assertEqual(manager.state.sheriff_name, "Alpha")
        self.assertEqual(len(election["vote_rounds"]), 3)
        self.assertEqual(election["vote_rounds"][0]["tied_targets"], ["Alpha", "Beta"])
        self.assertEqual(election["vote_rounds"][1]["tied_targets"], ["Alpha", "Beta"])
        self.assertEqual(election["vote_rounds"][2]["winner"], "Alpha")
        self.assertEqual(election["votes"][0]["voter"], "Gamma")
        self.assertNotIn("Alpha", [vote["voter"] for round_item in election["vote_rounds"] for vote in round_item["votes"]])
        self.assertNotIn("Beta", [vote["voter"] for round_item in election["vote_rounds"] for vote in round_item["votes"]])

    async def test_hunter_does_not_shoot_when_poisoned(self):
        hunter = make_player("Hunter", Role.HUNTER)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([hunter, villager])

        manager._emit = mock.AsyncMock()
        manager._transfer_sheriff_badge = mock.AsyncMock()
        manager._gun_shot = mock.AsyncMock()

        await manager._kill_player("Hunter", "night", "witch_poison")

        self.assertEqual(hunter.status, PlayerStatus.DEAD)
        manager._gun_shot.assert_not_awaited()

    async def test_wolf_king_shoots_back_when_voted_out(self):
        wolf_king = make_player("WolfKing", Role.WOLF_KING)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf_king, villager])

        manager._emit = mock.AsyncMock()
        manager._transfer_sheriff_badge = mock.AsyncMock()
        manager._gun_shot = mock.AsyncMock()

        await manager._kill_player("WolfKing", "vote", "vote")

        self.assertEqual(wolf_king.status, PlayerStatus.DEAD)
        manager._gun_shot.assert_awaited_once()
        args = manager._gun_shot.await_args.args
        self.assertEqual(args[0].name, "WolfKing")
        self.assertEqual(args[1], "wolf_king_revenge")

    async def test_hunter_gun_prompt_does_not_expose_target_roles(self):
        hunter = make_player("Hunter", Role.HUNTER, status=PlayerStatus.DEAD)
        wolf = make_player("Wolf", Role.WEREWOLF)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([hunter, wolf, villager], round_number=1)

        manager._record_private_thought = mock.AsyncMock()
        manager._kill_player = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(return_value={"action": {"shoot_target": "Wolf"}})

        await manager._gun_shot(hunter, "hunter_revenge", "猎人 Hunter 开枪带走了 {target}！")

        user_prompt = manager._agent_action.await_args.args[2]
        self.assertIn("不包含真实身份信息", user_prompt)
        self.assertIn("不要声称“我知道某人是狼”", user_prompt)
        self.assertIn("可选目标：Wolf、Villager", user_prompt)
        self.assertNotIn("Wolf：狼人", user_prompt)
        self.assertNotIn("Villager：平民", user_prompt)

    async def test_day_phase_white_wolf_explodes_and_takes_target(self):
        white_wolf = make_player("WhiteWolf", Role.WHITE_WOLF)
        target = make_player("Target", Role.VILLAGER)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager(
            [white_wolf, target, villager],
            rules=GameRules(sheriff_enabled=False, white_wolf_explode_during_day=True),
            round_number=2,
            phase=Phase.DAY_DISCUSS,
            auto_advance=True,
        )

        manager._emit = mock.AsyncMock()
        manager._elect_sheriff = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)
        manager._kill_player = mock.AsyncMock()
        manager._determine_speak_order = mock.Mock(return_value=[white_wolf, target, villager])
        manager._agent_action = mock.AsyncMock(
            return_value={"public_speech": "I explode.", "action": {"shoot_target": "Target"}}
        )

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        self.assertEqual(manager._kill_player.await_count, 2)
        self.assertEqual(manager._kill_player.await_args_list[0].args[:3], ("WhiteWolf", "white_wolf_self", "white_wolf_self"))
        self.assertEqual(manager._kill_player.await_args_list[1].args[:3], ("Target", "white_wolf", "white_wolf"))

    def test_day_self_destruct_is_available_but_context_marks_low_signal(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        teammate = make_player("Mate", Role.WEREWOLF)
        villager_one = make_player("VillagerOne", Role.VILLAGER)
        villager_two = make_player("VillagerTwo", Role.VILLAGER)
        villager_three = make_player("VillagerThree", Role.VILLAGER)
        villager_four = make_player("VillagerFour", Role.VILLAGER)
        manager = make_manager([wolf, teammate, villager_one, villager_two, villager_three, villager_four], round_number=2, phase=Phase.DAY_DISCUSS)

        ctx = AgentContext(wolf, manager.state)
        self.assertTrue(ctx.should_offer_day_self_destruct())
        self.assertIn("当前没有额外自爆相关事实；这不代表系统建议自爆", ctx._day_self_destruct_context_block())

        manager.state.speeches.append(
            SpeechRecord(
                speaker="VillagerOne",
                inner_thought="Wolf is under direct pressure.",
                public_speech="I think Wolf is the obvious wolf here.",
                round_number=2,
                phase="discuss",
            )
        )

        self.assertTrue(AgentContext(wolf, manager.state).should_offer_day_self_destruct())

    def test_discuss_prompt_includes_public_board_and_previous_round_evidence(self):
        alpha = make_player("Alpha", Role.VILLAGER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.SEER)
        delta = make_player("Delta", Role.VILLAGER, status=PlayerStatus.DEAD)
        manager = make_manager([alpha, beta, gamma, delta], round_number=2, phase=Phase.DAY_DISCUSS, sheriff_name="Gamma")
        manager.state.history.extend(
            [
                {"type": "death", "round": 1, "phase": "night", "player": "Delta", "role": "平民"},
                {
                    "type": "day_vote",
                    "round": 1,
                    "votes": [
                        {"voter": "Alpha", "target": "Beta"},
                        {"voter": "Beta", "target": "Alpha"},
                    ],
                    "counts": {"Beta": 1, "Alpha": 1},
                    "eligible_voters": ["Alpha", "Beta", "Gamma"],
                    "actual_voters": ["Alpha", "Beta"],
                    "missing_voters": ["Gamma"],
                    "tied_targets": ["Alpha", "Beta"],
                    "eliminated": None,
                },
            ]
        )
        manager.state.speeches.extend(
            [
                SpeechRecord(
                    speaker="Beta",
                    inner_thought="",
                    public_speech="Alpha keeps pushing me without a full vote read.",
                    round_number=1,
                    phase="discuss",
                ),
                SpeechRecord(
                    speaker="Gamma",
                    inner_thought="",
                    public_speech="I want everyone to state clear wolf candidates.",
                    round_number=2,
                    phase="discuss",
                ),
            ]
        )

        prompt = AgentContext(alpha, manager.state).build_discuss_user_prompt()

        self.assertIn("公开局势面板", prompt)
        self.assertIn("2. Beta：存活", prompt)
        self.assertIn("3. Gamma（警长）：存活", prompt)
        self.assertIn("4. Delta：阵亡", prompt)
        self.assertNotIn("Delta：阵亡，公开身份：平民", prompt)
        self.assertIn("公开发言", prompt)
        self.assertIn("Beta：Alpha keeps pushing me", prompt)
        self.assertIn("投票记录：Alpha -> Beta、Beta -> Alpha", prompt)
        self.assertIn("票数：Beta 1票、Alpha 1票", prompt)
        self.assertIn("应投玩家：Alpha、Beta、Gamma；已投玩家：Alpha、Beta；未投玩家：Gamma", prompt)
        self.assertIn("平票目标：Alpha、Beta", prompt)
        self.assertIn("放逐结果：无人被放逐", prompt)
        self.assertIn("本轮排位推理任务", prompt)
        self.assertNotIn("Beta：存活，公开身份：狼人", prompt)

    def test_public_speech_digest_includes_previous_day_votes(self):
        alpha = make_player("Alpha", Role.VILLAGER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.SEER)
        manager = make_manager([alpha, beta, gamma], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.history.append(
            {
                "type": "day_vote",
                "round": 1,
                "votes": [{"voter": "Alpha", "target": "Beta"}, {"voter": "Gamma", "target": "Beta"}],
                "counts": {"Beta": 2},
                "eligible_voters": ["Alpha", "Beta", "Gamma"],
                "actual_voters": ["Alpha", "Gamma"],
                "missing_voters": ["Beta"],
                "eliminated": "Beta",
            }
        )

        prompt = AgentContext(alpha, manager.state).build_public_speech_digest_user_prompt(
            "Gamma",
            "昨天票型已经说明 Beta 被集中放逐。",
            "discuss",
        )

        self.assertIn("第 1 轮回顾", prompt)
        self.assertIn("投票记录：Alpha -> Beta、Gamma -> Beta", prompt)
        self.assertIn("票数：Beta 2票", prompt)
        self.assertIn("放逐结果：Beta", prompt)

    async def test_public_speech_digest_updates_observer_notes_in_parallel(self):
        speaker = make_player("Speaker", Role.VILLAGER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.SEER)
        manager = make_manager([speaker, beta, gamma], round_number=2, phase=Phase.DAY_DISCUSS)
        manager._emit = mock.AsyncMock()
        started: list[str] = []
        release = asyncio.Event()

        async def fake_agent_action(player, *_args, **_kwargs):
            started.append(player.name)
            if len(started) == 2:
                release.set()
            await release.wait()
            return {"private_note": f"{player.name} 已消化 Speaker 发言。", "delete_notes": []}

        manager._agent_action = mock.AsyncMock(side_effect=fake_agent_action)

        await manager._digest_public_speech_for_observers("Speaker", "我今天重点压 Beta。", "discuss")

        self.assertCountEqual(started, ["Beta", "Gamma"])
        self.assertEqual(manager._agent_action.await_count, 2)

    async def test_public_speech_digest_failure_does_not_crash_game(self):
        speaker = make_player("Speaker", Role.VILLAGER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.SEER)
        manager = make_manager([speaker, beta, gamma], round_number=2, phase=Phase.DAY_DISCUSS)

        async def fake_agent_action(player, *_args, **_kwargs):
            if player.name == "Beta":
                raise RuntimeError("Error code: 429 - rate_limit_error")
            return {"private_note": f"{player.name} 已消化 Speaker 发言。", "delete_notes": []}

        manager._agent_action = mock.AsyncMock(side_effect=fake_agent_action)

        await manager._digest_public_speech_for_observers("Speaker", "我今天重点压 Beta。", "discuss")

        self.assertEqual(manager._agent_action.await_count, 2)

    def test_day_prompts_include_sheriff_campaign_speeches_and_vote_shape(self):
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.VILLAGER)
        gamma = make_player("Gamma", Role.WEREWOLF)
        delta = make_player("Delta", Role.VILLAGER)
        manager = make_manager([alpha, beta, gamma, delta], round_number=1, phase=Phase.DAY_DISCUSS, sheriff_name="Alpha")
        manager.state.speeches.extend(
            [
                SpeechRecord(
                    speaker="Alpha",
                    inner_thought="private",
                    public_speech="I want badge because I can organize checks.",
                    round_number=1,
                    phase="sheriff_campaign",
                ),
                SpeechRecord(
                    speaker="Beta",
                    inner_thought="private",
                    public_speech="Alpha's badge logic is too smooth.",
                    round_number=1,
                    phase="sheriff_runoff",
                ),
            ]
        )
        manager.state.history.append(
            {
                "type": "sheriff_election",
                "round": 1,
                "candidates": ["Alpha", "Beta"],
                "votes": [{"voter": "Gamma", "target": "Alpha"}, {"voter": "Delta", "target": "Alpha"}],
                "counts": {"Alpha": 2},
                "vote_rounds": [
                    {
                        "round": 1,
                        "candidates": ["Alpha", "Beta"],
                        "votes": [{"voter": "Gamma", "target": "Alpha"}, {"voter": "Delta", "target": "Beta"}],
                        "counts": {"Alpha": 1, "Beta": 1},
                        "winner": None,
                        "tied_targets": ["Alpha", "Beta"],
                    },
                    {
                        "round": 2,
                        "candidates": ["Alpha", "Beta"],
                        "votes": [{"voter": "Gamma", "target": "Alpha"}, {"voter": "Delta", "target": "Alpha"}],
                        "counts": {"Alpha": 2},
                        "winner": "Alpha",
                        "tied_targets": ["Alpha"],
                    },
                ],
                "winner": "Alpha",
            }
        )

        ctx = AgentContext(gamma, manager.state)
        discuss_prompt = ctx.build_discuss_user_prompt()
        vote_prompt = ctx.build_vote_user_prompt()

        for prompt in (discuss_prompt, vote_prompt):
            self.assertIn("警长竞选公开信息", prompt)
            self.assertIn("上警候选人：Alpha、Beta", prompt)
            self.assertIn("警上 Alpha：I want badge", prompt)
            self.assertIn("警长PK Beta：Alpha's badge logic", prompt)
            self.assertIn("第 1 轮票型：Gamma -> Alpha、Delta -> Beta；票数：Alpha 1票、Beta 1票；结果：平票：Alpha、Beta", prompt)
            self.assertIn("已投警下玩家：Gamma、Delta；未投警下玩家：无。", prompt)
            self.assertIn("只有最初未上警玩家参与警长投票；上警候选人不投票，不要指控上警候选人未投票。", prompt)
            self.assertIn("票型中出现的人视为已经投票，不要指控其未投。", prompt)
            self.assertIn("第 2 轮票型：Gamma -> Alpha、Delta -> Alpha；票数：Alpha 2票；结果：Alpha 当选", prompt)
            self.assertIn("最终警长：Alpha", prompt)
            self.assertNotIn("private", prompt)

    def test_night_prompts_include_public_sheriff_claims_for_wolves(self):
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.WITCH)
        gamma = make_player("Gamma", Role.WEREWOLF)
        delta = make_player("Delta", Role.VILLAGER)
        manager = make_manager([alpha, beta, gamma, delta], round_number=2, phase=Phase.NIGHT, sheriff_name="Alpha")
        manager.state.speeches.extend(
            [
                SpeechRecord(
                    speaker="Alpha",
                    inner_thought="private seer thought",
                    public_speech="我是预言家。首夜验 Gamma，查杀。",
                    round_number=1,
                    phase="sheriff_campaign",
                ),
                SpeechRecord(
                    speaker="Beta",
                    inner_thought="private witch thought",
                    public_speech="我认 Alpha 的预言家面更高，但我没有跳身份。",
                    round_number=1,
                    phase="sheriff_campaign",
                ),
            ]
        )
        manager.state.history.append(
            {
                "type": "sheriff_election",
                "round": 1,
                "candidates": ["Alpha", "Beta"],
                "votes": [{"voter": "Gamma", "target": "Alpha"}, {"voter": "Delta", "target": "Alpha"}],
                "counts": {"Alpha": 2},
                "winner": "Alpha",
            }
        )

        ctx = AgentContext(gamma, manager.state)
        first_prompt = ctx.build_night_user_prompt()
        discuss_prompt = ctx.build_werewolf_discuss_user_prompt([{"name": "Gamma", "target": "Beta"}], 2)

        for prompt in (first_prompt, discuss_prompt):
            self.assertIn("夜晚可用公开信息", prompt)
            self.assertIn("警上 Alpha：我是预言家。首夜验 Gamma，查杀。", prompt)
            self.assertIn("警上 Beta：我认 Alpha 的预言家面更高，但我没有跳身份。", prompt)
            self.assertIn("身份起跳只能依据公开发言原文判断", prompt)
            self.assertIn("不要把支持某个预言家", prompt)
            self.assertIn("第 1 轮票型：Gamma -> Alpha、Delta -> Alpha", prompt)
            self.assertIn("已投警下玩家：Gamma、Delta；未投警下玩家：无", prompt)
            self.assertNotIn("private seer thought", prompt)
            self.assertNotIn("private witch thought", prompt)

    def test_sheriff_runoff_context_keeps_all_original_candidates_ineligible(self):
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.VILLAGER)
        gamma = make_player("Gamma", Role.WEREWOLF)
        delta = make_player("Delta", Role.VILLAGER)
        epsilon = make_player("Epsilon", Role.WITCH)
        manager = make_manager([alpha, beta, gamma, delta, epsilon], round_number=2, phase=Phase.DAY_DISCUSS, sheriff_name="Alpha")
        manager.state.history.append(
            {
                "type": "sheriff_election",
                "round": 1,
                "candidates": ["Alpha", "Beta", "Gamma"],
                "vote_rounds": [
                    {
                        "round": 1,
                        "candidates": ["Alpha", "Beta", "Gamma"],
                        "ineligible_voters": ["Alpha", "Beta", "Gamma"],
                        "eligible_voters": ["Delta", "Epsilon"],
                        "actual_voters": ["Delta", "Epsilon"],
                        "missing_voters": [],
                        "votes": [{"voter": "Delta", "target": "Alpha"}, {"voter": "Epsilon", "target": "Beta"}],
                        "counts": {"Alpha": 1, "Beta": 1},
                        "winner": None,
                        "tied_targets": ["Alpha", "Beta"],
                    },
                    {
                        "round": 2,
                        "candidates": ["Alpha", "Beta"],
                        "ineligible_voters": ["Alpha", "Beta", "Gamma"],
                        "eligible_voters": ["Delta", "Epsilon"],
                        "actual_voters": ["Delta", "Epsilon"],
                        "missing_voters": [],
                        "votes": [{"voter": "Delta", "target": "Alpha"}, {"voter": "Epsilon", "target": "Alpha"}],
                        "counts": {"Alpha": 2},
                        "winner": "Alpha",
                        "tied_targets": [],
                    },
                ],
                "winner": "Alpha",
            }
        )

        prompt = AgentContext(delta, manager.state).build_discuss_user_prompt()

        self.assertIn("本轮无投票权上警玩家：Alpha、Beta、Gamma", prompt)
        self.assertIn("已投警下玩家：Delta、Epsilon；未投警下玩家：无。", prompt)
        self.assertIn("上警候选人不投票，不要指控上警候选人未投票", prompt)
        self.assertNotIn("未投警下玩家：Gamma", prompt)

    def test_wolf_private_chat_context_is_wolf_channel_only(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        mate = make_player("Mate", Role.WEREWOLF)
        hidden = make_player("Hidden", Role.HIDDEN_WOLF)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, mate, hidden, villager], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.wolf_chat.append(
            WolfChatRecord(
                speaker="Mate",
                message="I will claim seer tomorrow; Wolf can support or cut depending on votes.",
                round_number=1,
                kill_target="Villager",
            )
        )

        wolf_prompt = AgentContext(wolf, manager.state).build_discuss_system_prompt()
        villager_prompt = AgentContext(villager, manager.state).build_discuss_system_prompt()
        hidden_prompt = AgentContext(hidden, manager.state).build_discuss_system_prompt()

        self.assertIn("wolf_team_private_chat", wolf_prompt)
        self.assertIn("I will claim seer tomorrow", wolf_prompt)
        self.assertNotIn("I will claim seer tomorrow", villager_prompt)
        self.assertNotIn("I will claim seer tomorrow", hidden_prompt)

    async def test_werewolf_action_records_private_chat_without_public_speech_event(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        mate = make_player("Mate", Role.WEREWOLF)
        target = make_player("Target", Role.VILLAGER)
        spare = make_player("Spare", Role.VILLAGER)
        manager = make_manager([wolf, mate, target, spare], round_number=1, phase=Phase.NIGHT, night_actions=NightAction())
        manager._emit = mock.AsyncMock()
        calls = []

        async def fake_agent_action(player, system, user, **kwargs):
            calls.append((player.name, system, user, kwargs))
            if len(calls) <= 2:
                return {"inner_thought": "kill thought", "public_speech": "", "action": {"kill_target": "Target"}}
            if player.name == "Wolf":
                return {
                    "inner_thought": "chat thought",
                    "public_speech": "Wolf private plan: I can claim seer tomorrow.",
                    "private_note": "I may claim seer tomorrow.",
                    "action": None,
                }
            return {
                "inner_thought": "chat thought",
                "public_speech": "Mate private plan: I will support Wolf unless votes punish it.",
                "private_note": "Support Wolf's fake claim unless risky.",
                "action": None,
            }

        manager._agent_action = mock.AsyncMock(side_effect=fake_agent_action)

        await manager._werewolf_action()

        self.assertEqual(manager.state.night_actions.werewolf_target, "Target")
        self.assertEqual([item.speaker for item in manager.state.wolf_chat], ["Wolf", "Mate"])
        self.assertIn("Wolf private plan", manager.state.wolf_chat[0].message)
        self.assertIn("Mate private plan", manager.state.wolf_chat[1].message)
        self.assertIn("do not follow a fixed checklist", calls[2][2])
        self.assertIn("your known teammate state", calls[2][2])
        self.assertIn("name the exact wolf responsible", calls[2][2])
        self.assertIn("claimed check target", calls[2][2])
        self.assertIn("gold-water or black-check result", calls[2][2])
        self.assertIn("badge flow", calls[2][2])
        self.assertIn("silver-water target", calls[2][2])
        self.assertIn("substitute source of public pressure", calls[2][2])
        self.assertIn("complete new tagged note", calls[2][2])
        self.assertNotIn("Anti-bussing check", calls[2][2])
        self.assertNotIn("God-claim check", calls[2][2])
        self.assertNotIn("CLAIM_PLAN", calls[2][2])
        self.assertIn("Wolf private plan", calls[3][1])
        self.assertIn("狼队夜话", "\n".join(manager.state.agent_notes["Wolf"]))
        self.assertIn("Mate private plan", "\n".join(manager.state.agent_notes["Wolf"]))
        self.assertTrue(any(call.args and call.args[0] == "wolf_chat" for call in manager._emit.await_args_list))
        self.assertTrue(any(call.args and call.args[0] == "agent_notes_update" for call in manager._emit.await_args_list))
        self.assertTrue(all(speech.public_speech == "" for speech in manager.state.speeches if speech.phase == "night_werewolf"))
        self.assertFalse(any(call.args and call.args[0] == "speech" for call in manager._emit.await_args_list))

    def test_sheriff_prompts_include_prior_campaign_speeches_and_vote_rounds(self):
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.VILLAGER)
        gamma = make_player("Gamma", Role.WEREWOLF)
        delta = make_player("Delta", Role.VILLAGER)
        manager = make_manager([alpha, beta, gamma, delta], round_number=1, phase=Phase.DAY_DISCUSS)
        manager.state.speeches.extend(
            [
                SpeechRecord(
                    speaker="Alpha",
                    inner_thought="secret",
                    public_speech="I claim a strong badge plan.",
                    round_number=1,
                    phase="sheriff_campaign",
                ),
                SpeechRecord(
                    speaker="Beta",
                    inner_thought="secret",
                    public_speech="Alpha ignored the wolf positions.",
                    round_number=1,
                    phase="sheriff_runoff",
                ),
            ]
        )
        vote_rounds = [
            {
                "round": 1,
                "candidates": ["Alpha", "Beta"],
                "votes": [{"voter": "Gamma", "target": "Alpha"}, {"voter": "Delta", "target": "Beta"}],
                "counts": {"Alpha": 1, "Beta": 1},
                "winner": None,
                "tied_targets": ["Alpha", "Beta"],
            }
        ]

        campaign_prompt = AgentContext(beta, manager.state).build_sheriff_campaign_user_prompt(["Alpha", "Beta"])
        runoff_prompt = AgentContext(alpha, manager.state).build_sheriff_runoff_campaign_user_prompt(["Alpha", "Beta"], 2, vote_rounds)
        voter_prompt = AgentContext(gamma, manager.state).build_sheriff_vote_user_prompt(["Alpha", "Beta"], vote_rounds)

        self.assertIn("已公开竞选发言", campaign_prompt)
        self.assertIn("最高优先级私有技能事实", campaign_prompt)
        self.assertIn("局内私有便签", campaign_prompt)
        self.assertIn("警上发言 Alpha：I claim a strong badge plan.", campaign_prompt)
        self.assertIn("最高优先级私有技能事实", runoff_prompt)
        self.assertIn("局内私有便签", runoff_prompt)
        self.assertIn("PK发言 Beta：Alpha ignored the wolf positions.", runoff_prompt)
        self.assertIn("第 1 轮：Gamma -> Alpha、Delta -> Beta；票数：Alpha 1票、Beta 1票；结果：平票：Alpha、Beta", runoff_prompt)
        self.assertIn("最高优先级私有技能事实", voter_prompt)
        self.assertIn("局内私有便签", voter_prompt)
        self.assertIn("请根据警上/PK发言、已有票型和你自己的站边判断投票", voter_prompt)
        self.assertIn("第 1 轮：Gamma -> Alpha、Delta -> Beta", voter_prompt)
        self.assertNotIn("secret", campaign_prompt + runoff_prompt + voter_prompt)

    def test_sheriff_prompts_explain_unrevealed_first_night_deaths_are_not_peaceful_night(self):
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.VILLAGER)
        manager = make_manager([alpha, beta], round_number=1, phase=Phase.DAY_DISCUSS)
        ctx = AgentContext(alpha, manager.state)

        nomination_prompt = ctx.build_sheriff_nomination_user_prompt()
        campaign_prompt = ctx.build_sheriff_campaign_user_prompt(["Alpha"])
        system_prompt = ctx.build_discuss_system_prompt()

        self.assertIn("昨夜死讯尚未公布", nomination_prompt)
        self.assertIn("不能说“平安夜”", nomination_prompt)
        self.assertIn("不要说“平安夜”", campaign_prompt)
        self.assertIn("不要把“未公布死讯”理解成“平安夜”", system_prompt)
        self.assertIn("首夜结束后先警长竞选", system_prompt)

    def test_seer_prompt_gets_private_checks_and_positioning_scaffold(self):
        seer = make_player("Seer", Role.SEER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.VILLAGER)
        manager = make_manager([seer, beta, gamma], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.history.append({"type": "seer_check", "player": "Seer", "target": "Beta", "is_wolf": True, "round": 1})
        manager.state.speeches.append(
            SpeechRecord(
                speaker="Seer",
                inner_thought="I am hiding the real check.",
                public_speech="我昨晚验 Gamma 是狼人。",
                round_number=1,
                phase="discuss",
            )
        )

        ctx = AgentContext(seer, manager.state)

        system_prompt = ctx.build_discuss_system_prompt()
        discuss_prompt = ctx.build_discuss_user_prompt()
        vote_prompt = ctx.build_vote_user_prompt()
        night_system_prompt = ctx.build_night_system_prompt()
        night_user_prompt = ctx.build_night_user_prompt()

        for prompt in (system_prompt, discuss_prompt, vote_prompt, night_system_prompt, night_user_prompt):
            self.assertIn("最高优先级私有技能事实", prompt)
            self.assertIn("预言家验人结果", prompt)
            self.assertIn("第 1 夜查验 Beta：狼人", prompt)
            self.assertIn("未验存活玩家：Gamma", prompt)
            self.assertIn("不能被自己的话术骗回去", prompt)

        self.assertIn("预言家特别要求", discuss_prompt)
        self.assertIn("下一验人方向", discuss_prompt)
        self.assertIn("我昨晚验 Gamma 是狼人。", discuss_prompt)

    def test_witch_private_skill_truth_includes_visible_kill_and_scratchpad(self):
        witch = make_player("Witch", Role.WITCH)
        wolf = make_player("Wolf", Role.WEREWOLF)
        target = make_player("Target", Role.VILLAGER)
        manager = make_manager(
            [witch, wolf, target],
            round_number=2,
            phase=Phase.NIGHT,
            night_actions=NightAction(werewolf_target="Target"),
        )
        manager.state.agent_notes["Witch"] = ["R1 day_discuss: 公开口径先不跳女巫，夜里优先保关键神。"]

        ctx = AgentContext(witch, manager.state)
        prompt = ctx.build_night_system_prompt() + ctx.build_night_user_prompt() + ctx.build_discuss_user_prompt()

        self.assertIn("最高优先级私有技能事实", prompt)
        self.assertIn("解药：未使用；毒药：未使用", prompt)
        self.assertIn("当前你可见的狼刀目标：Target", prompt)
        self.assertIn("局内私有便签", prompt)
        self.assertIn("公开口径先不跳女巫", prompt)
        self.assertIn("便签只属于你自己", prompt)
        self.assertIn("不能覆盖引擎提供的私有技能事实", prompt)
        self.assertIn("delete_notes 固定写 []", prompt)

        wolf_prompt = AgentContext(wolf, manager.state).build_night_system_prompt()
        self.assertNotIn("解药：未使用", wolf_prompt)
        self.assertNotIn("公开口径先不跳女巫", wolf_prompt)

    def test_witch_without_save_cannot_see_current_night_kill(self):
        witch = make_player("Witch", Role.WITCH)
        wolf = make_player("Wolf", Role.WEREWOLF)
        target = make_player("Target", Role.VILLAGER)
        manager = make_manager(
            [witch, wolf, target],
            round_number=2,
            phase=Phase.NIGHT,
            night_actions=NightAction(werewolf_target="Target"),
        )
        manager.state.witch_has_save = False

        prompt = AgentContext(witch, manager.state).build_night_system_prompt() + AgentContext(witch, manager.state).build_night_user_prompt()

        self.assertIn("解药已用完：从此夜开始你不再获得当夜狼刀目标信息。", prompt)
        self.assertNotIn("当前你可见的狼刀目标：Target", prompt)
        self.assertNotIn("今夜狼刀目标：Target", prompt)

    async def test_witch_action_record_does_not_leak_kill_after_save_used(self):
        witch = make_player("Witch", Role.WITCH)
        wolf = make_player("Wolf", Role.WEREWOLF)
        target = make_player("NightKill", Role.VILLAGER)
        poison_target = make_player("Poisoned", Role.VILLAGER)
        manager = make_manager(
            [witch, wolf, target, poison_target],
            round_number=2,
            phase=Phase.NIGHT,
            night_actions=NightAction(werewolf_target="NightKill"),
        )
        manager.state.witch_has_save = False
        manager._emit = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(return_value={"action": {"poison_target": "Poisoned"}})

        await manager._witch_action()

        record = next(speech for speech in manager.state.speeches if speech.phase == "night_witch")
        self.assertIn("解药已用完，本夜不可见狼刀目标", record.skill_info)
        self.assertNotIn("NightKill", record.skill_info)
        self.assertIn("Poisoned", record.skill_info)

    def test_private_note_updates_agent_scratchpad(self):
        player = make_player("Alpha", Role.VILLAGER)
        manager = make_manager([player], round_number=2, phase=Phase.DAY_DISCUSS)

        manager._update_agent_note(player, {"private_note": "坚持我上一轮的好人视角，先压 Beta 发言矛盾。"})

        self.assertEqual(len(manager.state.agent_notes["Alpha"]), 1)
        self.assertIn("战术计划：", manager.state.agent_notes["Alpha"][0])
        self.assertIn("坚持我上一轮的好人视角", manager.state.agent_notes["Alpha"][0])
        self.assertIn("R2 day_discuss", manager.state.agent_notes["Alpha"][0])

    def test_private_note_falls_back_to_inner_thought_for_digest_cache(self):
        player = make_player("Alpha", Role.VILLAGER)
        manager = make_manager([player], round_number=3, phase=Phase.DAY_DISCUSS)

        manager._update_agent_note(
            player,
            {"inner_thought": "Beta 这轮把自己和 Gamma 绑得太死，今晚先复核这两个位置。"},
            allow_fallback=True,
        )

        self.assertEqual(len(manager.state.agent_notes["Alpha"]), 1)
        self.assertIn("战术计划：", manager.state.agent_notes["Alpha"][0])
        self.assertIn("Beta 这轮把自己和 Gamma 绑得太死", manager.state.agent_notes["Alpha"][0])
        self.assertIn("R3 day_discuss", manager.state.agent_notes["Alpha"][0])

    def test_untagged_private_note_replaces_same_default_tag(self):
        player = make_player("Alpha", Role.VILLAGER)
        manager = make_manager([player], round_number=2, phase=Phase.DAY_DISCUSS)

        manager._update_agent_note(player, {"private_note": "先听 Beta 发言，再决定是否归票。"})
        manager._update_agent_note(player, {"private_note": "改为优先压 Gamma 表水，Beta 暂缓。"})

        notes = "\n".join(manager.state.agent_notes["Alpha"])
        self.assertEqual(len(manager.state.agent_notes["Alpha"]), 1)
        self.assertIn("战术计划：改为优先压 Gamma 表水", notes)
        self.assertNotIn("先听 Beta 发言", notes)

    def test_untagged_identity_note_replaces_identity_workspace(self):
        player = make_player("Alpha", Role.VILLAGER)
        manager = make_manager([player], round_number=2, phase=Phase.DAY_DISCUSS)

        manager._update_agent_note(player, {"private_note": "身份工作区：Beta 没交代身份，Gamma 偏神。"})
        manager._update_agent_note(player, {"private_note": "Beta 已交代平民，Gamma 进狼坑，Delta 需要继续逼身份。"})

        notes = "\n".join(manager.state.agent_notes["Alpha"])
        self.assertEqual(len(manager.state.agent_notes["Alpha"]), 1)
        self.assertIn("身份工作区：Beta 已交代平民", notes)
        self.assertNotIn("Beta 没交代身份", notes)

    def test_wolf_fake_identity_note_replaces_old_team_plan(self):
        wolf = make_player("Alpha", Role.WEREWOLF)
        manager = make_manager([wolf], round_number=1, phase=Phase.DAY_ANNOUNCE)

        manager._update_agent_note(wolf, {"private_note": "假身份：平民。策略：不上警倒钩。"})
        manager.state.phase = Phase.NIGHT
        manager._update_agent_note(wolf, {"private_note": "狼队计划：Alpha 明天亲自跳预言家，队友负责支持和垫票。"})

        notes = "\n".join(manager.state.agent_notes["Alpha"])
        self.assertIn("狼队计划：Alpha 明天亲自跳预言家", notes)
        self.assertNotIn("不上警倒钩", notes)
        self.assertEqual(len([note for note in manager.state.agent_notes["Alpha"] if "狼队计划：" in note or "假身份：" in note]), 1)

    def test_agent_can_delete_own_stale_notes_by_visible_number(self):
        player = make_player("Alpha", Role.VILLAGER)
        manager = make_manager([player], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.agent_notes["Alpha"] = [
            "R1 day_discuss: 旧站边：先保 Beta。",
            "R1 night: 身份素材：存活待分析 Beta, Gamma。",
            "R1 night: 身份工作区：Beta 没交代身份，Gamma 偏神。",
            "R2 day_discuss: 新信息：Beta 发言爆狼。",
        ]

        changed = manager._delete_agent_notes(player, [1, 2, 3, 9])

        self.assertTrue(changed)
        notes = "\n".join(manager.state.agent_notes["Alpha"])
        self.assertNotIn("旧站边", notes)
        self.assertIn("身份素材", notes)
        self.assertNotIn("身份工作区", notes)
        self.assertIn("新信息", notes)

    def test_delete_notes_runs_before_private_note_update(self):
        player = make_player("Alpha", Role.VILLAGER)
        manager = make_manager([player], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.agent_notes["Alpha"] = ["R1 day_discuss: 旧计划：跟随 Beta。"]

        notes_changed = manager._delete_agent_notes(player, [1])
        notes_changed = manager._update_agent_note(player, {"private_note": "新计划：Beta 已进狼坑，改投 Beta。"}) or notes_changed

        self.assertTrue(notes_changed)
        notes = "\n".join(manager.state.agent_notes["Alpha"])
        self.assertNotIn("旧计划", notes)
        self.assertIn("新计划", notes)

    def test_refresh_private_fact_notes_seeds_wolf_roster(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        teammate = make_player("Mate", Role.WEREWOLF)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, teammate, villager], round_number=0, phase=Phase.SETUP)

        manager._refresh_private_fact_notes()

        self.assertIn("Wolf", manager.state.agent_notes)
        self.assertIn("Mate", manager.state.agent_notes)
        wolf_notes = "\n".join(manager.state.agent_notes["Wolf"])
        self.assertIn("已确认存活狼队友 Mate", wolf_notes)
        self.assertIn("名单外玩家都不是你的已确认队友", wolf_notes)
        self.assertIn("身份素材", wolf_notes)
        self.assertIn("存活待分析", wolf_notes)
        self.assertIn("具体谁报身份、谁没交代", wolf_notes)
        self.assertNotIn("待排狼坑", wolf_notes)

    def test_wolf_discuss_prompt_tracks_gods_and_pushes_not_wolf_pit(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        mate = make_player("Mate", Role.WEREWOLF)
        seer = make_player("Seer", Role.SEER)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, mate, seer, villager], round_number=2, phase=Phase.DAY_DISCUSS)

        prompt = AgentContext(wolf, manager.state).build_discuss_user_prompt()

        self.assertIn("本轮狼队推理任务", prompt)
        self.assertIn("队友状态", prompt)
        self.assertIn("神位判断", prompt)
        self.assertIn("抗推判断", prompt)
        self.assertNotIn("坑位排序", prompt)
        self.assertNotIn("狼坑候选", prompt)

    def test_wolf_roster_note_replaces_old_state_after_teammate_death(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        teammate = make_player("Mate", Role.WEREWOLF)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, teammate, villager], round_number=2, phase=Phase.DAY_DISCUSS)

        manager._refresh_private_fact_notes()
        teammate.status = PlayerStatus.DEAD
        manager._refresh_private_fact_notes()

        wolf_notes = "\n".join(manager.state.agent_notes["Wolf"])
        self.assertEqual(len([note for note in manager.state.agent_notes["Wolf"] if "狼队硬信息" in note]), 1)
        self.assertIn("唯一存活狼人", wolf_notes)
        self.assertIn("已确认出局狼队友 Mate", wolf_notes)
        self.assertNotIn("已确认存活狼队友 Mate", wolf_notes)

    def test_identity_material_tracks_seer_checks_without_assigning_wolf_pit(self):
        seer = make_player("Seer", Role.SEER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.VILLAGER)
        delta = make_player("Delta", Role.VILLAGER)
        manager = make_manager([seer, beta, gamma, delta], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.history.append({"type": "seer_check", "player": "Seer", "target": "Beta", "is_wolf": True, "round": 1})

        manager._refresh_private_fact_notes()

        self.assertIn("Seer", manager.state.agent_notes)
        self.assertIn("身份素材", manager.state.agent_notes["Seer"][0])
        self.assertIn("查杀 Beta", manager.state.agent_notes["Seer"][0])
        self.assertIn("存活待分析 Beta, Gamma, Delta", manager.state.agent_notes["Seer"][0])
        self.assertNotIn("待排狼坑", manager.state.agent_notes["Seer"][0])

    def test_identity_material_is_created_for_villagers_without_role_judgment(self):
        alpha = make_player("Alpha", Role.VILLAGER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.SEER)
        manager = make_manager([alpha, beta, gamma], round_number=1, phase=Phase.DAY_DISCUSS)

        manager._refresh_private_fact_notes()

        self.assertIn("Alpha", manager.state.agent_notes)
        self.assertIn("身份素材", manager.state.agent_notes["Alpha"][0])
        self.assertIn("存活待分析 Beta, Gamma", manager.state.agent_notes["Alpha"][0])
        self.assertIn("由你在“身份工作区：”便签中自行维护", manager.state.agent_notes["Alpha"][0])
        self.assertNotIn("待排狼坑", manager.state.agent_notes["Alpha"][0])
        self.assertNotIn("待找神位", manager.state.agent_notes["Alpha"][0])

    def test_prompt_gives_full_role_quota_without_deciding_missing_roles(self):
        alpha = make_player("Alpha", Role.VILLAGER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.SEER)
        delta = make_player("Delta", Role.HUNTER)
        manager = make_manager([alpha, beta, gamma, delta], round_number=1, phase=Phase.DAY_DISCUSS)
        manager.state.speeches.append(
            SpeechRecord(
                speaker="Gamma",
                inner_thought="",
                public_speech="我是预言家，今天先听发言。",
                round_number=1,
                phase="sheriff_campaign",
            )
        )

        prompt = AgentContext(alpha, manager.state).build_discuss_user_prompt()

        self.assertIn("公开全额配置消息", prompt)
        self.assertIn("本局角色全额", prompt)
        self.assertIn("平民 1", prompt)
        self.assertIn("狼人 1", prompt)
        self.assertIn("预言家 1", prompt)
        self.assertIn("猎人 1", prompt)
        self.assertIn("存活玩家公开发言次数", prompt)
        self.assertIn("Alpha 0次", prompt)
        self.assertIn("Gamma 1次", prompt)
        self.assertIn("不是系统判断的“缺额”", prompt)
        self.assertNotIn("未被公开死亡或身份关键词覆盖", prompt)
        self.assertNotIn("系统认定无人持有", prompt)

    def test_unrevealed_deaths_do_not_consume_public_role_quota(self):
        alpha = make_player("Alpha", Role.VILLAGER)
        beta = make_player("Beta", Role.WEREWOLF)
        gamma = make_player("Gamma", Role.SEER)
        delta = make_player("Delta", Role.HUNTER, status=PlayerStatus.DEAD)
        manager = make_manager([alpha, beta, gamma, delta], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.history.append({"type": "death", "round": 1, "phase": "night", "player": "Delta", "role": "猎人"})

        prompt = AgentContext(alpha, manager.state).build_discuss_user_prompt()

        self.assertIn("已死亡玩家：Delta", prompt)
        self.assertIn("普通死亡不等于公开翻牌", prompt)
        self.assertIn("已公开翻牌/自爆消耗：无", prompt)
        self.assertIn("仅扣除这些公开身份后的可见容量", prompt)
        self.assertIn("猎人 1", prompt)
        self.assertNotIn("Delta：阵亡，公开身份：猎人", prompt)

    def test_public_self_destruct_consumes_public_wolf_quota(self):
        alpha = make_player("Alpha", Role.VILLAGER)
        wolf = make_player("Wolf", Role.WEREWOLF, status=PlayerStatus.DEAD)
        gamma = make_player("Gamma", Role.SEER)
        manager = make_manager([alpha, wolf, gamma], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.history.append({"type": "death", "round": 1, "phase": "werewolf_self", "player": "Wolf", "role": "狼人"})

        prompt = AgentContext(alpha, manager.state).build_discuss_user_prompt()

        self.assertIn("Wolf：阵亡，公开身份：狼人", prompt)
        self.assertIn("已公开翻牌/自爆消耗：狼人 1", prompt)

    def test_wolf_note_rejects_suspected_teammate_wording(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager([wolf, villager], round_number=2, phase=Phase.DAY_DISCUSS)

        manager._update_agent_note(wolf, {"private_note": "Villager 疑似队友，先保一下。"})

        self.assertNotIn("Wolf", manager.state.agent_notes)

    def test_non_seer_prompt_does_not_receive_private_seer_checks(self):
        villager = make_player("Villager", Role.VILLAGER)
        seer = make_player("Seer", Role.SEER)
        beta = make_player("Beta", Role.WEREWOLF)
        manager = make_manager([villager, seer, beta], round_number=2, phase=Phase.DAY_DISCUSS)
        manager.state.history.append({"type": "seer_check", "player": "Seer", "target": "Beta", "is_wolf": True, "round": 1})

        ctx = AgentContext(villager, manager.state)
        prompt = ctx.build_discuss_system_prompt() + ctx.build_discuss_user_prompt()

        self.assertNotIn("查验 Beta", prompt)
        self.assertNotIn("第 1 夜查验 Beta：狼人", prompt)

    def test_last_words_prompt_includes_completed_sheriff_context(self):
        dead = make_player("Dead", Role.VILLAGER, status=PlayerStatus.DEAD)
        alpha = make_player("Alpha", Role.SEER)
        beta = make_player("Beta", Role.WEREWOLF)
        manager = make_manager([dead, alpha, beta], round_number=1, phase=Phase.DAY_ANNOUNCE, sheriff_name="Alpha")
        manager.state.night_kills = ["Dead"]
        manager.state.gm_announcement = "昨夜，Dead 倒在了血泊中。"
        manager.state.speeches.append(
            SpeechRecord(
                speaker="Alpha",
                inner_thought="",
                public_speech="我上警是因为我有第一天带队视角，警徽流先压 Beta。",
                round_number=1,
                phase="sheriff_campaign",
            )
        )
        manager.state.history.append(
            {
                "type": "sheriff_election",
                "round": 1,
                "candidates": ["Alpha"],
                "votes": [{"voter": "Dead", "target": "Alpha"}, {"voter": "Beta", "target": "Alpha"}],
                "counts": {"Alpha": 2},
                "winner": "Alpha",
            }
        )

        prompt = AgentContext(dead, manager.state).build_last_words_user_prompt()

        self.assertIn("警长竞选公开信息", prompt)
        self.assertIn("我上警是因为我有第一天带队视角", prompt)
        self.assertIn("Dead -> Alpha", prompt)
        self.assertIn("最终警长：Alpha", prompt)
        self.assertIn("不要说“这局没听到任何发言”", prompt)
        self.assertIn("遗言会作为公开发言进入后续玩家上下文", prompt)

    def test_wolf_last_words_prompt_allows_fake_identity_line_after_vote_out(self):
        wolf = make_player("Wolf", Role.WEREWOLF, status=PlayerStatus.DEAD)
        villager = make_player("Villager", Role.VILLAGER)
        seer = make_player("Seer", Role.SEER)
        manager = make_manager([wolf, villager, seer], round_number=2, phase=Phase.DAY_VOTE, day_eliminated="Wolf")
        manager.state.history.append(
            {
                "type": "day_vote",
                "round": 2,
                "votes": [{"voter": "Villager", "target": "Wolf"}, {"voter": "Seer", "target": "Wolf"}],
                "counts": {"Wolf": 2},
                "eliminated": "Wolf",
            }
        )

        prompt = AgentContext(wolf, manager.state).build_last_words_user_prompt()

        self.assertIn("放逐票型", prompt)
        self.assertIn("投票记录：Villager -> Wolf、Seer -> Wolf", prompt)
        self.assertIn("延续悍跳/对跳/查杀口径", prompt)
        self.assertIn("被票出不等于必须提前自爆", prompt)

    async def test_day_phase_honors_wolf_self_destruct_choice(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        villager_one = make_player("VillagerOne", Role.VILLAGER)
        villager_two = make_player("VillagerTwo", Role.VILLAGER)
        villager_three = make_player("VillagerThree", Role.VILLAGER)
        villager_four = make_player("VillagerFour", Role.VILLAGER)
        manager = make_manager(
            [wolf, villager_one, villager_two, villager_three, villager_four],
            rules=GameRules(sheriff_enabled=False),
            round_number=2,
            phase=Phase.DAY_DISCUSS,
            auto_advance=True,
        )

        manager._emit = mock.AsyncMock()
        manager._elect_sheriff = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)
        manager._kill_player = mock.AsyncMock()
        manager._determine_speak_order = mock.Mock(return_value=[wolf, villager_one, villager_two, villager_three, villager_four])
        manager._digest_public_speech_for_observers = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(
            side_effect=[
                {"public_speech": "I am fine.", "action": {"self_destruct": True}},
                {"public_speech": "Normal speech 1.", "action": {}},
                {"public_speech": "Normal speech 2.", "action": {}},
                {"public_speech": "Normal speech 3.", "action": {}},
                {"public_speech": "Normal speech 4.", "action": {}},
                {"action": {"vote_target": "abstain"}},
                {"action": {"vote_target": "abstain"}},
                {"action": {"vote_target": "abstain"}},
                {"action": {"vote_target": "abstain"}},
                {"action": {"vote_target": "abstain"}},
            ]
        )

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        manager._kill_player.assert_awaited_once()
        self.assertEqual(manager._kill_player.await_args.args[:3], ("Wolf", "werewolf_self", "werewolf_self"))

    async def test_day_phase_allows_wolf_self_destruct_after_other_players_speak(self):
        villager = make_player("Villager", Role.VILLAGER)
        wolf = make_player("Wolf", Role.WEREWOLF)
        other = make_player("Other", Role.VILLAGER)
        manager = make_manager(
            [villager, wolf, other],
            rules=GameRules(sheriff_enabled=False),
            round_number=2,
            phase=Phase.DAY_DISCUSS,
            auto_advance=True,
        )

        manager._emit = mock.AsyncMock()
        manager._elect_sheriff = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)
        manager._kill_player = mock.AsyncMock()
        manager._determine_speak_order = mock.Mock(return_value=[villager, wolf, other])
        manager._digest_public_speech_for_observers = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(
            side_effect=[
                {"public_speech": "Wolf is too suspicious, I want to push Wolf.", "action": {}},
                {"public_speech": "", "action": {"self_destruct": True}},
            ]
        )

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        self.assertEqual(manager._agent_action.await_count, 2)
        reaction_prompt = manager._agent_action.await_args_list[1].args[2]
        self.assertIn("发言后即时自爆窗口", reaction_prompt)
        self.assertIn("刚刚发言者：Villager", reaction_prompt)
        self.assertIn("Wolf is too suspicious", reaction_prompt)
        manager._kill_player.assert_awaited_once()
        self.assertEqual(manager._kill_player.await_args.args[:3], ("Wolf", "werewolf_self", "werewolf_self"))

    async def test_day_phase_sheriff_vote_weight_breaks_tie_without_pk(self):
        sheriff = make_player("Sheriff", Role.VILLAGER)
        wolf = make_player("Wolf", Role.WEREWOLF)
        villager_one = make_player("VillagerOne", Role.VILLAGER)
        villager_two = make_player("VillagerTwo", Role.VILLAGER)
        manager = make_manager(
            [sheriff, wolf, villager_one, villager_two],
            rules=GameRules(sheriff_enabled=True, sheriff_vote_multiplier=1.5),
            round_number=2,
            phase=Phase.DAY_DISCUSS,
            sheriff_name="Sheriff",
            auto_advance=True,
        )

        manager._emit = mock.AsyncMock()
        manager._elect_sheriff = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)
        manager._kill_player = mock.AsyncMock()
        manager._last_words = mock.AsyncMock()
        manager._determine_speak_order = mock.Mock(return_value=[sheriff, wolf, villager_one, villager_two])
        manager._digest_public_speech_for_observers = mock.AsyncMock()
        manager._offer_wolf_self_destruct_after_speech = mock.AsyncMock(return_value=False)
        manager._agent_action = mock.AsyncMock(
            side_effect=[
                {"public_speech": "Speech 1", "action": {}},
                {"public_speech": "Speech 2", "action": {}},
                {"public_speech": "Speech 3", "action": {}},
                {"public_speech": "Speech 4", "action": {}},
                {"action": {"vote_target": "Wolf"}},
                {"action": {"vote_target": "VillagerOne"}},
                {"action": {"vote_target": "Wolf"}},
                {"action": {"vote_target": "VillagerOne"}},
            ]
        )

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        self.assertEqual(manager._kill_player.await_args.args[:3], ("Wolf", "vote", "vote"))
        manager._last_words.assert_awaited_once()
        self.assertEqual(manager._last_words.await_args.args[0].name, "Wolf")
        self.assertIn("投票放逐", manager._last_words.await_args.args[1])
        self.assertEqual(manager.state.day_eliminated, "Wolf")
        vote_event = next(item for item in manager.state.history if item.get("type") == "day_vote")
        self.assertEqual(len(vote_event["vote_rounds"]), 1)
        self.assertEqual(vote_event["vote_rounds"][0]["counts"], {"Wolf": 2.5, "VillagerOne": 2.0})
        self.assertEqual(vote_event["vote_rounds"][0]["tied_targets"], [])
        self.assertNotIn("sheriff_tiebreak", vote_event)
        self.assertEqual(vote_event["eliminated"], "Wolf")

    async def test_day_phase_tie_with_live_sheriff_uses_tiebreak_without_pk(self):
        sheriff = make_player("Sheriff", Role.VILLAGER)
        wolf = make_player("Wolf", Role.WEREWOLF)
        villager_one = make_player("VillagerOne", Role.VILLAGER)
        villager_two = make_player("VillagerTwo", Role.VILLAGER)
        manager = make_manager(
            [sheriff, wolf, villager_one, villager_two],
            rules=GameRules(sheriff_enabled=True, sheriff_vote_multiplier=1.0),
            round_number=2,
            phase=Phase.DAY_DISCUSS,
            sheriff_name="Sheriff",
            auto_advance=True,
        )

        manager._emit = mock.AsyncMock()
        manager._elect_sheriff = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)
        manager._kill_player = mock.AsyncMock()
        manager._last_words = mock.AsyncMock()
        manager._determine_speak_order = mock.Mock(return_value=[sheriff, wolf, villager_one, villager_two])
        manager._digest_public_speech_for_observers = mock.AsyncMock()
        manager._offer_wolf_self_destruct_after_speech = mock.AsyncMock(return_value=False)
        manager._agent_action = mock.AsyncMock(
            side_effect=[
                {"public_speech": "Speech 1", "action": {}},
                {"public_speech": "Speech 2", "action": {}},
                {"public_speech": "Speech 3", "action": {}},
                {"public_speech": "Speech 4", "action": {}},
                {"action": {"vote_target": "Wolf"}},
                {"action": {"vote_target": "VillagerOne"}},
                {"action": {"vote_target": "Wolf"}},
                {"action": {"vote_target": "VillagerOne"}},
                {"action": {"vote_target": "Wolf"}},
            ]
        )

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        vote_event = next(item for item in manager.state.history if item.get("type") == "day_vote")
        self.assertEqual(len(vote_event["vote_rounds"]), 1)
        self.assertCountEqual(vote_event["vote_rounds"][0]["tied_targets"], ["Wolf", "VillagerOne"])
        self.assertEqual(vote_event["sheriff_tiebreak"], {"sheriff": "Sheriff", "target": "Wolf"})
        self.assertEqual(vote_event["eliminated"], "Wolf")

    async def test_day_phase_without_sheriff_uses_runoff_pk_on_tie(self):
        wolf = make_player("Wolf", Role.WEREWOLF)
        villager_one = make_player("VillagerOne", Role.VILLAGER)
        villager_two = make_player("VillagerTwo", Role.VILLAGER)
        villager_three = make_player("VillagerThree", Role.VILLAGER)
        manager = make_manager(
            [wolf, villager_one, villager_two, villager_three],
            rules=GameRules(sheriff_enabled=False),
            round_number=2,
            phase=Phase.DAY_DISCUSS,
            auto_advance=True,
        )

        manager._emit = mock.AsyncMock()
        manager._elect_sheriff = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)
        manager._kill_player = mock.AsyncMock()
        manager._last_words = mock.AsyncMock()
        manager._determine_speak_order = mock.Mock(return_value=[wolf, villager_one, villager_two, villager_three])
        manager._digest_public_speech_for_observers = mock.AsyncMock()
        manager._offer_wolf_self_destruct_after_speech = mock.AsyncMock(return_value=False)
        manager._agent_action = mock.AsyncMock(
            side_effect=[
                {"public_speech": "Speech 1", "action": {}},
                {"public_speech": "Speech 2", "action": {}},
                {"public_speech": "Speech 3", "action": {}},
                {"public_speech": "Speech 4", "action": {}},
                {"action": {"vote_target": "VillagerOne"}},
                {"action": {"vote_target": "Wolf"}},
                {"action": {"vote_target": "VillagerOne"}},
                {"action": {"vote_target": "Wolf"}},
                {"public_speech": "I can explain the vote.", "action": {}},
                {"public_speech": "Wolf should be exiled.", "action": {}},
                {"action": {"vote_target": "VillagerOne"}},
                {"action": {"vote_target": "Wolf"}},
                {"action": {"vote_target": "Wolf"}},
                {"action": {"vote_target": "Wolf"}},
            ]
        )

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        vote_event = next(item for item in manager.state.history if item.get("type") == "day_vote")
        self.assertEqual(len(vote_event["vote_rounds"]), 2)
        self.assertCountEqual(vote_event["vote_rounds"][0]["tied_targets"], ["Wolf", "VillagerOne"])
        self.assertEqual(vote_event["vote_rounds"][1]["eliminated"], "Wolf")
        self.assertEqual(vote_event["eliminated"], "Wolf")

    async def test_sheriff_transfer_records_dead_sheriff_inner_thought(self):
        sheriff = make_player("Sheriff", Role.VILLAGER, status=PlayerStatus.DEAD)
        target = make_player("Target", Role.VILLAGER)
        manager = make_manager([sheriff, target], round_number=2, phase=Phase.DAY_DISCUSS, sheriff_name="Sheriff")
        manager._emit = mock.AsyncMock()
        manager._agent_action = mock.AsyncMock(
            return_value={
                "inner_thought": "Target kept the cleanest vote record, so I pass the badge.",
                "public_speech": "",
                "action": {"transfer_badge_target": "Target"},
            }
        )

        await manager._transfer_sheriff_badge(sheriff)

        transfer_record = next(speech for speech in manager.state.speeches if speech.phase == "sheriff_transfer")
        self.assertIn("cleanest vote record", transfer_record.inner_thought)
        self.assertEqual(transfer_record.skill_info, "警徽移交：Target")

    async def test_day_phase_idiot_vote_out_reveals_without_dying(self):
        idiot = make_player("Idiot", Role.IDIOT)
        wolf = make_player("Wolf", Role.WEREWOLF)
        villager = make_player("Villager", Role.VILLAGER)
        manager = make_manager(
            [idiot, wolf, villager],
            rules=GameRules(sheriff_enabled=False),
            round_number=2,
            phase=Phase.DAY_DISCUSS,
            auto_advance=True,
        )

        manager._emit = mock.AsyncMock()
        manager._elect_sheriff = mock.AsyncMock()
        manager._check_and_emit_winner = mock.AsyncMock(return_value=False)
        manager._kill_player = mock.AsyncMock()
        async def fake_agent_action(player, _system_prompt, user_prompt, **_kwargs):
            if "vote_target" in user_prompt:
                return {"action": {"vote_target": "Wolf" if player.name == "Idiot" else "Idiot"}}
            return {"public_speech": "I am innocent." if player.name == "Idiot" else "", "action": {}}

        manager._agent_action = mock.AsyncMock(side_effect=fake_agent_action)

        with mock.patch("app.engine.game_manager.asyncio.sleep", new=mock.AsyncMock()):
            await manager._day_phase()

        self.assertEqual(idiot.status, PlayerStatus.ALIVE)
        self.assertFalse(idiot.vote_right)
        self.assertIsNone(manager.state.day_eliminated)
        manager._kill_player.assert_not_awaited()


class WinConditionTests(unittest.TestCase):
    def test_village_wins_when_all_wolves_are_dead(self):
        state = make_manager(
            [
                make_player("Seer", Role.SEER),
                make_player("Wolf", Role.WEREWOLF, status=PlayerStatus.DEAD),
            ]
        ).state

        self.assertEqual(check_win_condition(state), "village")

    def test_slaughter_side_wolves_win_when_no_gods_remain(self):
        state = make_manager(
            [
                make_player("Wolf", Role.WEREWOLF),
                make_player("Villager", Role.VILLAGER),
            ],
            rules=GameRules(win_rule=WinRule.SLAUGHTER_SIDE),
        ).state

        self.assertEqual(check_win_condition(state), "werewolf")

    def test_slaughter_side_wolves_win_when_no_villagers_remain(self):
        state = make_manager(
            [
                make_player("Wolf", Role.WEREWOLF),
                make_player("Seer", Role.SEER),
            ],
            rules=GameRules(win_rule=WinRule.SLAUGHTER_SIDE),
        ).state

        self.assertEqual(check_win_condition(state), "werewolf")

    def test_total_elimination_requires_all_good_players_dead(self):
        ongoing_state = make_manager(
            [
                make_player("Wolf", Role.WEREWOLF),
                make_player("Seer", Role.SEER),
            ],
            rules=GameRules(win_rule=WinRule.TOTAL_ELIMINATION),
        ).state
        finished_state = make_manager(
            [
                make_player("Wolf", Role.WEREWOLF),
                make_player("Seer", Role.SEER, status=PlayerStatus.DEAD),
            ],
            rules=GameRules(win_rule=WinRule.TOTAL_ELIMINATION),
        ).state

        self.assertIsNone(check_win_condition(ongoing_state))
        self.assertEqual(check_win_condition(finished_state), "werewolf")

    def test_parity_rule_gives_wolves_win_on_equal_numbers(self):
        state = make_manager(
            [
                make_player("Wolf", Role.WEREWOLF),
                make_player("Villager", Role.VILLAGER),
            ],
            rules=GameRules(win_rule=WinRule.PARITY),
        ).state

        self.assertEqual(check_win_condition(state), "werewolf")
