import unittest

from app.memory.summarizer import _apply_outcome_guardrails, _build_game_summary_for_agent, _is_wolf_win, agent_reflect_fallback
from app.models.agent import AgentMemory
from app.models.game import GameState, Player, Role, SpeechRecord


class MemorySummarizerTests(unittest.TestCase):
    def test_wolf_win_helper_uses_wolf_roles(self):
        self.assertTrue(_is_wolf_win(Role.WEREWOLF, "werewolf"))
        self.assertFalse(_is_wolf_win(Role.WEREWOLF, "village"))
        self.assertTrue(_is_wolf_win(Role.SEER, "village"))

    def test_loss_guardrails_turn_confident_self_review_into_negative_feedback(self):
        result = {
            "reflection": "I made a confident push and thought it controlled the table.",
            "key_moments": ["led a decisive push"],
            "strategy_updates": ["push harder when confident"],
            "useful_takeaways": ["confidence can lead the table"],
            "role_summary_update": {
                "strengths": ["confident decisive pushes"],
                "pitfalls": [],
                "signals_to_watch": [],
                "role_tips": [],
            },
        }

        guarded = _apply_outcome_guardrails(result, won=False)
        update = guarded["role_summary_update"]

        self.assertEqual(update["strengths"], [])
        self.assertIn("结果校准", guarded["reflection"])
        self.assertTrue(any("输局复盘默认是负反馈" in item for item in guarded["useful_takeaways"]))
        self.assertTrue(any("误判为高光" in item for item in update["pitfalls"]))
        self.assertTrue(any("长期记忆必须做结果校准" in item for item in guarded["strategy_updates"]))

    def test_win_guardrails_preserve_positive_learning(self):
        result = {
            "reflection": "The read was correct.",
            "key_moments": [],
            "strategy_updates": [],
            "useful_takeaways": [],
            "role_summary_update": {
                "strengths": ["accurate vote timing"],
                "pitfalls": [],
                "signals_to_watch": [],
                "role_tips": [],
            },
        }

        guarded = _apply_outcome_guardrails(result, won=True)

        self.assertEqual(guarded["role_summary_update"]["strengths"], ["accurate vote timing"])
        self.assertEqual(guarded["reflection"], "The read was correct.")

    def test_game_summary_includes_critical_action_audit(self):
        state = GameState(
            game_id="audit-game",
            round_number=2,
            winner="village",
            players=[
                Player(name="Alpha", role=Role.WEREWOLF),
                Player(name="Beta", role=Role.VILLAGER),
            ],
            speeches=[
                SpeechRecord(
                    speaker="Alpha",
                    inner_thought="This vote should save me.",
                    public_speech="Beta is suspicious.",
                    round_number=2,
                    phase="discuss",
                ),
                SpeechRecord(
                    speaker="Alpha",
                    inner_thought="",
                    public_speech="",
                    round_number=2,
                    phase="vote",
                    skill_info="投票：Beta",
                ),
            ],
            history=[
                {
                    "type": "day_vote",
                    "round": 2,
                    "votes": [{"voter": "Alpha", "target": "Beta"}],
                }
            ],
        )

        summary = _build_game_summary_for_agent(state, "Alpha")

        self.assertIn("Critical action audit", summary)
        self.assertIn("your vote: 投票：Beta", summary)
        self.assertIn("your exile vote: Beta", summary)
        self.assertIn("final winner=village", summary)

    def test_reflection_fallback_records_basic_recent_game(self):
        state = GameState(
            game_id="fallback-game",
            round_number=2,
            winner="werewolf",
            players=[
                Player(name="Alpha", role=Role.WEREWOLF),
                Player(name="Beta", role=Role.VILLAGER),
            ],
            speeches=[],
            history=[
                {
                    "type": "day_vote",
                    "round": 2,
                    "votes": [{"voter": "Alpha", "target": "Beta"}],
                }
            ],
        )
        memory = AgentMemory(agent_name="Alpha")

        updated = agent_reflect_fallback(state, "Alpha", memory, reason="model timeout")

        self.assertEqual(updated.total_games, 1)
        self.assertEqual(updated.wins, 1)
        self.assertEqual(updated.lessons[-1].game_id, "fallback-game")
        self.assertIn("自动复盘未完成", updated.lessons[-1].reflection)
        self.assertIn("model timeout", updated.lessons[-1].reflection)
        self.assertEqual(updated.role_summaries["werewolf"].last_updated_game_id, "fallback-game")
