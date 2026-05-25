import { expect, test } from "@playwright/test";

test("renders the upgraded agent memory archive", async ({ page }) => {
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

  await page.route("**/api/agents", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "阿尔法",
          personality: "冷静理性，擅长逻辑分析",
          total_games: 8,
          wins: 5,
          losses: 3,
          strategies: ["先看站边结构，再决定是否强冲", "有把握时再推动节奏"],
          lesson_count: 8,
        },
      ]),
    });
  });

  await page.route("**/api/agents/%E9%98%BF%E5%B0%94%E6%B3%95", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        agent_name: "阿尔法",
        personality: "冷静理性，擅长逻辑分析",
        total_games: 8,
        wins: 5,
        losses: 3,
        strategies: ["先看站边结构，再决定是否强冲", "有把握时再推动节奏"],
        memory_version: 2,
        role_summaries: {
          werewolf: {
            role: "werewolf",
            total_games: 4,
            wins: 3,
            losses: 1,
            strengths: ["会先观察预言家对跳力度再决定冲锋顺序"],
            pitfalls: ["发言太平会被当作深水狼"],
            signals_to_watch: ["真预言家通常更早给出警徽流"],
            role_tips: ["狼队顺风时别抢太多结论位"],
            recent_examples: ["6人局里通过顺势站边活到末轮"],
            last_updated_game_id: "game_20260523_demo_1",
          },
        },
        lessons: [
          {
            game_id: "game_20260523_demo_1",
            role: "werewolf",
            won: true,
            reflection: "这局前期没有急着抢话，等预言家站边基本成型后再顺势推票，节奏更稳。",
            key_moments: ["第二轮顺着票型把怀疑导向了真焦点"],
            player_count: 6,
            role_config: "狼人x2 / 预言家x1 / 女巫x1 / 平民x2",
            rounds_played: 3,
            survived_to_end: true,
            final_status: "alive",
            winner: "werewolf",
            useful_takeaways: ["小板子里狼队更怕发言失衡，不怕慢一点"],
          },
        ],
      }),
    });
  });

  await page.goto("/agents");

  await expect(page.getByRole("heading", { name: "Agent 进化档案馆" })).toBeVisible();
  await expect(page.getByText("阿尔法")).toBeVisible();

  await page.getByRole("button", { name: "展开" }).click();

  await expect(page.getByText("角色长期记忆")).toBeVisible();
  await expect(page.getByText("这个角色常打好的点")).toBeVisible();
  await expect(page.getByText("相似旧局引用")).toBeVisible();
  await expect(page.getByRole("button", { name: /狼人\s+4 局/ })).toBeVisible();
  await expect(page.getByText("小板子里狼队更怕发言失衡，不怕慢一点").first()).toBeVisible();
});
