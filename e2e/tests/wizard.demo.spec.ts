import { expect, test } from "@playwright/test";

test("wizard happy-path in demo mode", async ({ page }) => {
  let pollCount = 0;

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
            id: "fmt-demo-001",
            title: "Formato Demo",
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
          id: "prompt-demo-001",
          name: "Prompt Demo",
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
        id: "proj-e2e-demo-001",
        projectId: "proj-e2e-demo-001",
        status: "draft",
      }),
    });
  });

  await page.route("**/api/ai/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        configured: false,
        reachable: false,
        engine: "simulation",
        message: "Modo demo/simulacion",
      }),
    });
  });

  await page.route("**/api/projects/proj-e2e-demo-001/generate", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        status: "processing",
        mode: "demo",
      }),
    });
  });

  await page.route("**/api/projects/proj-e2e-demo-001", async (route) => {
    pollCount += 1;
    const payload =
      pollCount < 2
        ? { id: "proj-e2e-demo-001", status: "processing" }
        : {
            id: "proj-e2e-demo-001",
            status: "completed",
            output_file: "outputs/proj-e2e-demo-001.docx",
          };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
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

  await page.fill("#var_tema", "E2E demo");
  await page.click("#btn-step3-generate");

  await expect(page.locator("#gen-success")).toBeVisible();
  await expect(page.locator("#btn-gen-downloads")).toBeVisible();
});

