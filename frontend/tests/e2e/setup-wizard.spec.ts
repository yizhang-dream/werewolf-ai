import { expect, test } from "@playwright/test";

function installMockEventSourceScript() {
  return () => {
    class MockEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      readyState = MockEventSource.OPEN;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;

      constructor(_url: string) {
        setTimeout(() => {
          this.onopen?.(new Event("open"));
        }, 0);
      }

      addEventListener() {}
      removeEventListener() {}
      close() {
        this.readyState = MockEventSource.CLOSED;
      }
    }

    // @ts-expect-error testing shim
    window.EventSource = MockEventSource;
  };
}

test("loads a template into the setup editor", async ({ page }) => {
  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    });
  });

  await page.route("**/api/settings/providers", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "Mock Provider",
          provider_type: "openai_compatible",
          base_url: "http://localhost:11434/v1",
          models: ["mock-model"],
          has_key: true,
        },
      ]),
    });
  });

  await page.route("**/api/games/templates/list", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "6p_beginner",
          name: "6人入门局",
          description: "2狼 + 预言家 + 女巫 + 2平民",
          roles: ["werewolf", "werewolf", "seer", "witch", "villager", "villager"],
          rules: {
            win_rule: "slaughter_side",
            witch_self_save_rule: "first_night_only",
            same_guard_save_survives: false,
            guard_can_self_protect: true,
            first_night_last_words: true,
            sheriff_enabled: true,
            sheriff_vote_multiplier: 1.5,
            white_wolf_explode_during_day: true,
            white_wolf_explode_ends_day: true,
            knight_duel_ends_discussion: true,
          },
        },
        {
          id: "9p_hunter",
          name: "9人预女猎",
          description: "3狼 + 预言家 + 女巫 + 猎人 + 3平民",
          roles: ["werewolf", "werewolf", "werewolf", "seer", "witch", "hunter", "villager", "villager", "villager"],
          rules: {
            win_rule: "slaughter_side",
            witch_self_save_rule: "first_night_only",
            same_guard_save_survives: false,
            guard_can_self_protect: true,
            first_night_last_words: true,
            sheriff_enabled: true,
            sheriff_vote_multiplier: 1.5,
            white_wolf_explode_during_day: true,
            white_wolf_explode_ends_day: true,
            knight_duel_ends_discussion: true,
          },
        },
      ]),
    });
  });

  await page.goto("/setup");

  await expect(page.getByRole("heading", { name: "创建一局真正可跑、可调、可复盘的狼人杀" })).toBeVisible();

  await page.locator("article").filter({ hasText: "9人预女猎" }).getByRole("button", { name: "载入编辑器" }).click();

  await expect(page.getByText("已载入 9人预女猎")).toBeVisible();
  await expect(page.getByText("9 名玩家 / 9 个身份")).toBeVisible();
});

test("creates a game from the setup wizard and opens the game board", async ({ page }) => {
  await page.addInitScript(installMockEventSourceScript());

  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    });
  });

  await page.route("**/api/settings/providers", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "Mock Provider",
          provider_type: "openai_compatible",
          base_url: "http://localhost:11434/v1",
          models: ["mock-model"],
          has_key: true,
        },
      ]),
    });
  });

  await page.route("**/api/games/templates/list", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/api/games", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        game_id: "test_game_001",
        players: [
          { name: "阿尔法", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "贝塔", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "伽马", role: "seer", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "德尔塔", role: "witch", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "艾普西隆", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "泽塔", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
        ],
        rules: {
          win_rule: "slaughter_side",
          witch_self_save_rule: "first_night_only",
          same_guard_save_survives: false,
          guard_can_self_protect: true,
          first_night_last_words: true,
          sheriff_enabled: true,
          sheriff_vote_multiplier: 1.5,
          white_wolf_explode_during_day: true,
          white_wolf_explode_ends_day: true,
          knight_duel_ends_discussion: true,
        },
      }),
    });
  });

  await page.route("**/api/games/test_game_001/full", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        game_id: "test_game_001",
        players: [
          { name: "阿尔法", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "贝塔", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "伽马", role: "seer", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "德尔塔", role: "witch", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "艾普西隆", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "泽塔", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
        ],
        phase: "setup",
        round_number: 0,
        night_kills: [],
        day_eliminated: null,
        winner: null,
        speeches: [],
        gm_announcement: "",
        auto_advance: false,
        step_delay: 2,
        rules: {
          win_rule: "slaughter_side",
          witch_self_save_rule: "first_night_only",
          same_guard_save_survives: false,
          guard_can_self_protect: true,
          first_night_last_words: true,
          sheriff_enabled: true,
          sheriff_vote_multiplier: 1.5,
          white_wolf_explode_during_day: true,
          white_wolf_explode_ends_day: true,
          knight_duel_ends_discussion: true,
        },
        sheriff_name: null,
      }),
    });
  });

  await page.goto("/setup");
  await page.getByRole("button", { name: "开始游戏" }).click();

  await expect(page).toHaveURL(/\/game\/test_game_001$/);
  await expect(page.getByRole("heading", { name: "对局控制台" })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始游戏" })).toBeVisible();
});
