import { expect, test } from "@playwright/test";

test("wizard surfaces 429 quota error and keeps retry path", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/api/formats**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        formats: [
          {
            id: "fmt-demo-002",
            title: "Formato Demo 2",
            university: "demo",
            category: "general",
            version: "v1",
          },
        ],
        stale: false,
        source: "demo",
      }),
    });
  });

  await page.route("**/api/prompts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "prompt-demo-002",
          name: "Prompt Demo 2",
          doc_type: "Tesis Completa",
          is_active: true,
          template: "Escribe sobre {{tema}}.",
          variables: ["tema"],
        },
      ]),
    });
  });

  await page.route("**/api/projects/draft", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: "proj-e2e-quota-001",
        projectId: "proj-e2e-quota-001",
        status: "draft",
      }),
    });
  });

  await page.route("**/api/ai/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        configured: true,
        reachable: true,
        engine: "gemini",
        model: "gemini-2.0-flash",
        message: "Gemini configurado",
      }),
    });
  });

  await page.route("**/api/projects/proj-e2e-quota-001/generate", async (route) => {
    await route.fulfill({
      status: 429,
      contentType: "application/json",
      headers: {
        "Retry-After": "30",
      },
      body: JSON.stringify({
        detail:
          "Quota exceeded. Check Gemini project quota/billing. Retry after 30 seconds.",
      }),
    });
  });

  await page.goto("/");
  await page.click("#nav-wizard");

  await page.click("#formats-grid .format-card");
  await expect(page.locator("#btn-step1-next")).toBeEnabled();
  await page.click("#btn-step1-next");

  await page.click("#prompts-grid .prompt-card");
  await expect(page.locator("#btn-step2-next")).toBeEnabled();
  await page.click("#btn-step2-next");

  await page.fill("#var_tema", "E2E quota");
  await page.click("#btn-step3-generate");

  await expect(page.locator("#gen-error")).toContainText("Quota exceeded");
  await expect(page.locator("#btn-gen-retry")).toBeVisible();
});

