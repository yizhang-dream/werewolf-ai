import { expect, test } from "@playwright/test";

test("creates a provider from the settings panel", async ({ page }) => {
  let providers = [
    {
      name: "Mock Provider",
      provider_type: "openai_compatible",
      base_url: "http://localhost:11434/v1",
      models: ["mock-model"],
      has_key: true,
    },
  ];

  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    });
  });

  await page.route("**/api/settings/providers", async (route) => {
    const method = route.request().method();

    if (method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(providers),
      });
      return;
    }

    if (method === "POST") {
      const payload = route.request().postDataJSON() as {
        name: string;
        provider_type: string;
        api_key?: string;
        base_url?: string;
        models: string[];
      };

      providers = [
        ...providers.filter((provider) => provider.name !== payload.name),
        {
          name: payload.name,
          provider_type: payload.provider_type,
          base_url: payload.base_url ?? "",
          models: payload.models,
          has_key: Boolean(payload.api_key),
        },
      ];

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    await route.fallback();
  });

  await page.route("**/api/settings/providers/*", async (route) => {
    const method = route.request().method();
    const name = decodeURIComponent(route.request().url().split("/").pop() || "");

    if (method === "DELETE") {
      providers = providers.filter((provider) => provider.name !== name);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    await route.fallback();
  });

  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "模型设置不该只是填几行表单" })).toBeVisible();
  await expect(page.getByText("Mock Provider", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "+ 新建 OpenAI Compatible" }).click();
  await page.getByPlaceholder("例如：Zhipu GLM / OpenAI / Ollama").fill("QA Provider");
  await page.getByPlaceholder("例如：http://localhost:11434/v1").fill("https://qa.example.com/v1");
  await page.getByPlaceholder("用逗号分隔，例如：glm-4.7, glm-5.1").fill("qa-model, qa-model-pro");
  await page.locator('input[type="password"]').fill("secret-key");

  await page.getByRole("button", { name: "保存 Provider" }).click();

  await expect(page.getByText("QA Provider", { exact: true })).toBeVisible();
  await expect(page.getByText("qa-model-pro")).toBeVisible();
  await expect(page.getByText("API Key 已配置").first()).toBeVisible();
});
