import unittest
from unittest import mock

from fastapi import HTTPException

from app.models.agent import ProviderConfig
from app.models.game import GameRules, WinRule
from app.routers import game as game_router
from app.routers import settings as settings_router


class SettingsRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_list_and_delete_provider(self):
        saved_settings = {"providers": []}

        def fake_load_settings():
            return settings_router.AppSettings.model_validate(saved_settings)

        def fake_save_settings(settings):
            saved_settings["providers"] = [provider.model_dump() for provider in settings.providers]

        with mock.patch.object(settings_router, "_load_settings", side_effect=fake_load_settings), mock.patch.object(
            settings_router, "_save_settings", side_effect=fake_save_settings
        ):
            await settings_router.save_provider(
                settings_router.ProviderInput(
                    name="Test Provider",
                    provider_type="openai_compatible",
                    api_key="secret",
                    base_url="http://localhost:11434/v1",
                    models=["mock-model"],
                )
            )

            listed = await settings_router.list_providers()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["name"], "Test Provider")
            self.assertTrue(listed[0]["has_key"])

            await settings_router.delete_provider("Test Provider")
            listed_after_delete = await settings_router.list_providers()
            self.assertEqual(listed_after_delete, [])


class GameRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        game_router._games.clear()

    async def test_resolve_provider_defaults_raises_without_provider(self):
        with mock.patch.object(game_router, "get_all_providers", return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                game_router._resolve_provider_defaults()

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Please configure at least one LLM Provider first.", ctx.exception.detail)

    async def test_resolve_provider_defaults_uses_requested_provider(self):
        provider = ProviderConfig(
            name="Mock Provider",
            provider_type="openai_compatible",
            api_key="secret",
            base_url="http://localhost:11434/v1",
            models=["model-a", "model-b"],
        )

        with mock.patch.object(game_router, "get_provider", return_value=provider):
            resolved_provider, resolved_model = game_router._resolve_provider_defaults("Mock Provider", "")

        self.assertEqual(resolved_provider, "Mock Provider")
        self.assertEqual(resolved_model, "model-a")

    async def test_resolve_provider_defaults_prefers_glm_51_when_available(self):
        provider = ProviderConfig(
            name="Zhipu GLM",
            provider_type="claude",
            api_key="secret",
            base_url="https://open.bigmodel.cn/api/anthropic",
            models=["glm-4.7", "glm-5.1"],
        )

        with mock.patch.object(game_router, "get_provider", return_value=provider):
            resolved_provider, resolved_model = game_router._resolve_provider_defaults("Zhipu GLM", "")

        self.assertEqual(resolved_provider, "Zhipu GLM")
        self.assertEqual(resolved_model, "glm-5.1")

    async def test_create_game_rejects_mismatched_counts(self):
        with self.assertRaises(HTTPException) as ctx:
            await game_router.create_game(
                game_router.CreateGameInput(
                    players=[{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
                    roles=["werewolf", "villager"],
                )
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Player count (4) must match role count (2)", ctx.exception.detail)

    async def test_create_game_applies_provider_defaults_and_preserves_rules(self):
        class FakeGameManager:
            def __init__(self, state):
                self.state = state

        custom_rules = GameRules(win_rule=WinRule.TOTAL_ELIMINATION)
        players = [
            {"name": "Alpha", "personality": "calm"},
            {"name": "Beta", "personality": "direct"},
            {"name": "Gamma", "personality": "quiet"},
            {"name": "Delta", "personality": "active"},
        ]

        with mock.patch.object(game_router, "_resolve_provider_defaults", return_value=("Mock Provider", "model-a")), mock.patch.object(
            game_router, "GameManager", FakeGameManager
        ), mock.patch.object(game_router.random, "shuffle", side_effect=lambda items: None):
            result = await game_router.create_game(
                game_router.CreateGameInput(
                    players=players,
                    roles=["werewolf", "seer", "witch", "villager"],
                    auto_advance=True,
                    rules=custom_rules,
                )
            )

        self.assertIn("game_id", result)
        self.assertEqual(len(result["players"]), 4)
        self.assertEqual(result["players"][0]["llm_provider"], "Mock Provider")
        self.assertEqual(result["players"][0]["model_name"], "model-a")
        self.assertEqual(result["rules"]["win_rule"], "total_elimination")
        self.assertTrue(result["game_id"] in game_router._games)
