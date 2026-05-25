import unittest
from unittest import mock

from app.engine.game_manager import GameManager
from app.models.agent import AgentMemory
from app.models.game import GameState, Player, Role


class PostGameMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_post_game_saves_fallback_memory_when_reflection_raises(self):
        manager = GameManager(
            GameState(
                game_id="post-game",
                players=[
                    Player(name="Alpha", role=Role.WEREWOLF),
                    Player(name="Beta", role=Role.VILLAGER, is_ai=False),
                ],
                winner="werewolf",
            )
        )
        emitted: list[tuple[str, dict]] = []

        async def fake_emit(event: str, payload: dict):
            emitted.append((event, payload))

        with (
            mock.patch.object(manager, "_emit", side_effect=fake_emit),
            mock.patch.object(manager, "_get_client", return_value=object()),
            mock.patch.object(manager, "_get_model", return_value="mock-model"),
            mock.patch("app.engine.game_manager.load_agent_memory", return_value=AgentMemory(agent_name="Alpha")),
            mock.patch("app.engine.game_manager.agent_reflect", mock.AsyncMock(side_effect=RuntimeError("boom"))),
            mock.patch("app.engine.game_manager.save_agent_memory") as save_agent_memory,
            mock.patch("app.engine.game_manager.save_game_log"),
        ):
            await manager._post_game()

        saved_memory = save_agent_memory.call_args.args[0]
        self.assertEqual(saved_memory.agent_name, "Alpha")
        self.assertEqual(saved_memory.total_games, 1)
        self.assertEqual(saved_memory.wins, 1)
        self.assertEqual(saved_memory.lessons[-1].game_id, "post-game")
        self.assertIn("boom", saved_memory.lessons[-1].reflection)

        game_saved = next(payload for event, payload in emitted if event == "game_saved")
        self.assertEqual(game_saved["reflection_failures"], [{"player": "Alpha", "error": "boom"}])
