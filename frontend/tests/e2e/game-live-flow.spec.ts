import { expect, test } from "@playwright/test";

type MockStreamEvent = {
  type: string;
  data: Record<string, unknown>;
  delay?: number;
};

function installMockEventSource(events: MockStreamEvent[]) {
  return (injectedEvents: MockStreamEvent[]) => {
    class MockEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;

      readyState = MockEventSource.OPEN;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      listeners = new Map<string, Array<(event: MessageEvent) => void>>();

      constructor(_url: string) {
        setTimeout(() => {
          this.onopen?.(new Event("open"));

          injectedEvents.forEach((entry, index) => {
            window.setTimeout(() => {
              const listeners = this.listeners.get(entry.type) ?? [];
              const event = new MessageEvent(entry.type, {
                data: JSON.stringify(entry.data),
              });
              listeners.forEach((listener) => listener(event));
            }, entry.delay ?? 120 * (index + 1));
          });
        }, 0);
      }

      addEventListener(type: string, listener: (event: MessageEvent) => void) {
        const bucket = this.listeners.get(type) ?? [];
        bucket.push(listener);
        this.listeners.set(type, bucket);
      }

      removeEventListener(type: string, listener: (event: MessageEvent) => void) {
        const bucket = this.listeners.get(type) ?? [];
        this.listeners.set(
          type,
          bucket.filter((item) => item !== listener)
        );
      }

      close() {
        this.readyState = MockEventSource.CLOSED;
      }
    }

    // @ts-expect-error test shim
    window.EventSource = MockEventSource;
  };
}

test("creates a game, starts it, and renders live SSE updates", async ({ page }) => {
  const events: MockStreamEvent[] = [
    {
      type: "phase_change",
      data: { phase: "day_announce", round: 1, message: "Night one resolved." },
      delay: 160,
    },
    {
      type: "gm_announcement",
      data: { message: "Night one was peaceful.", deaths: [] },
      delay: 240,
    },
    {
      type: "phase_change",
      data: { phase: "day_discuss", round: 1, message: "Discussion starts now." },
      delay: 320,
    },
    {
      type: "speech",
      data: {
        speaker: "Alpha",
        public_speech: "I want to watch Beta first.",
        inner_thought: "Beta entered too eagerly.",
        round: 1,
        phase: "discuss",
      },
      delay: 400,
    },
    {
      type: "vote_result",
      data: { message: "Voting window is open." },
      delay: 470,
    },
  ];

  await page.addInitScript(installMockEventSource(events), events);

  let started = false;

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
        game_id: "live_game_001",
        players: [
          { name: "Alpha", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "Beta", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "Gamma", role: "seer", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "Delta", role: "witch", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "Epsilon", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          { name: "Zeta", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
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

  await page.route("**/api/games/live_game_001/start", async (route) => {
    started = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "started" }),
    });
  });

  await page.route("**/api/games/live_game_001/full", async (route) => {
    const body = started
      ? {
          game_id: "live_game_001",
          players: [
            { name: "Alpha", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Beta", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Gamma", role: "seer", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Delta", role: "witch", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Epsilon", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Zeta", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
          ],
          phase: "day_discuss",
          round_number: 1,
          night_kills: [],
          day_eliminated: null,
          winner: null,
          speeches: [],
          gm_announcement: "Night one was peaceful.",
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
        }
      : {
          game_id: "live_game_001",
          players: [
            { name: "Alpha", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Beta", role: "werewolf", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Gamma", role: "seer", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Delta", role: "witch", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Epsilon", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
            { name: "Zeta", role: "villager", status: "alive", personality: "", llm_provider: "Mock Provider", model_name: "mock-model" },
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
        };

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.goto("/setup");
  await page.getByRole("button", { name: /开始游戏|寮€濮嬫父鎴?/ }).click();

  await expect(page).toHaveURL(/\/game\/live_game_001$/);
  await expect(page.getByText("Live Match")).toBeVisible();

  await page.getByRole("button", { name: /开始游戏|寮€濮嬫父鎴?/ }).click();

  await expect(page.getByText("Night one was peaceful.").first()).toBeVisible();
  await expect(page.getByText("I want to watch Beta first.").first()).toBeVisible();
  await expect(page.getByText("Voting window is open.")).toBeVisible();

  await expect(page.getByText("Beta entered too eagerly.").first()).toBeVisible();
});
