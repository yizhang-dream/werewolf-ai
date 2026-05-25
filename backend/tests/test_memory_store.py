import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.memory import store
from app.models.agent import AgentMemory, Lesson
from app.models.game import Player, Role


def build_log(game_id: str, role: str, winner: str, player_count: int, roles: list[str], status: str = "alive") -> dict:
    players = [{"name": "Alpha", "role": role, "status": status}]
    for index, extra_role in enumerate(roles[1:], start=1):
        players.append({"name": f"Player{index}", "role": extra_role, "status": "alive"})

    return {
        "game_id": game_id,
        "winner": winner,
        "round_number": 3,
        "players": players[:player_count],
        "speeches": [
            {
                "speaker": "Alpha",
                "public_speech": "watch the vote shape first",
                "inner_thought": "stay flexible",
                "round_number": 1,
                "phase": "discuss",
            }
        ],
        "history": [
            {
                "type": "day_vote",
                "round": 1,
                "votes": [{"voter": "Alpha", "target": "Player1"}],
            }
        ],
    }


class RetrieveRelevantMemoriesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.agents_dir = base / "agents"
        self.games_dir = base / "games"
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.games_dir.mkdir(parents=True, exist_ok=True)

        self.agents_patch = mock.patch.object(store, "AGENTS_DIR", self.agents_dir)
        self.games_patch = mock.patch.object(store, "GAMES_DIR", self.games_dir)
        self.agents_patch.start()
        self.games_patch.start()

    def tearDown(self):
        self.agents_patch.stop()
        self.games_patch.stop()
        self.temp_dir.cleanup()

    def test_retrieve_relevant_memories_prefers_same_role_and_board(self):
        memory = AgentMemory(
            agent_name="Alpha",
            lessons=[
                Lesson(
                    game_id="game_same_role",
                    role="werewolf",
                    won=True,
                    reflection="Stayed patient until the table polarized.",
                    useful_takeaways=["Delay hard push until vote shape is visible."],
                ),
                Lesson(
                    game_id="game_other_role",
                    role="guard",
                    won=False,
                    reflection="Protected too predictably.",
                    useful_takeaways=["Do not guard the obvious target twice."],
                ),
            ],
        )
        store.save_agent_memory(memory)

        store.save_game_log(
            "game_same_role",
            build_log(
                game_id="game_same_role",
                role="werewolf",
                winner="werewolf",
                player_count=6,
                roles=["werewolf", "werewolf", "seer", "witch", "villager", "villager"],
            ),
        )
        store.save_game_log(
            "game_other_role",
            build_log(
                game_id="game_other_role",
                role="guard",
                winner="village",
                player_count=6,
                roles=["guard", "werewolf", "seer", "witch", "villager", "villager"],
                status="dead",
            ),
        )

        current_players = [
            Player(name="Alpha", role=Role.WEREWOLF),
            Player(name="Beta", role=Role.WEREWOLF),
            Player(name="Gamma", role=Role.SEER),
            Player(name="Delta", role=Role.WITCH),
            Player(name="Epsilon", role=Role.VILLAGER),
            Player(name="Zeta", role=Role.VILLAGER),
        ]

        retrieved = store.retrieve_relevant_memories(
            agent_name="Alpha",
            current_role="werewolf",
            current_players=current_players,
            memory=memory,
            limit=2,
        )

        self.assertEqual(len(retrieved), 2)
        self.assertEqual(retrieved[0].game_id, "game_same_role")
        self.assertGreater(retrieved[0].score, retrieved[1].score)
        self.assertIn("Delay hard push until vote shape is visible.", retrieved[0].useful_takeaways)
        self.assertEqual(retrieved[0].role, "werewolf")

    def test_find_agent_game_logs_only_returns_games_with_that_agent(self):
        store.save_game_log(
            "game_alpha",
            {
                "game_id": "game_alpha",
                "players": [{"name": "Alpha", "role": "villager", "status": "alive"}],
                "winner": "village",
                "round_number": 1,
                "speeches": [],
                "history": [],
            },
        )
        store.save_game_log(
            "game_other",
            {
                "game_id": "game_other",
                "players": [{"name": "Beta", "role": "villager", "status": "alive"}],
                "winner": "village",
                "round_number": 1,
                "speeches": [],
                "history": [],
            },
        )

        logs = store.find_agent_game_logs("Alpha")
        self.assertEqual([log["game_id"] for log in logs], ["game_alpha"])
