import { expect, test } from "@playwright/test";

const formatId = "fmt-demo-002";
const projectId = "proj-e2e-quota-001";

const promptPackage = {
  id: "promptpkg_fmt_demo_002",
  name: "Paquete Demo 2",
  format_id: formatId,
  format_name: "Formato Demo 2",
  format_version: "v1",
  doc_type: "tesis",
  template: "Escribe sobre {{tema}}.",
  variables: ["tema"],
  sections: [
    {
      section_id: "intro",
      section_path: "INTRODUCCION",
      section_title: "Introducción",
      parent_section_path: "",
      section_level: 1,
      optional: false,
      default_selected: true,
      source_hints: "",
      blocks: [
        {
          block_id: "intro-1",
          label: "Introducción",
          instructions: "Contextualiza el problema.",
          required_variables: ["objetivo_general"],
          required: true,
        },
      ],
    },
  ],
  selected_sections: [
    {
      section_id: "intro",
      section_path: "INTRODUCCION",
    },
  ],
  section_tree: [
    {
      section_id: "intro",
      section_path: "INTRODUCCION",
      section_title: "Introducción",
      section_level: 1,
      optional: false,
      default_selected: true,
      blocks: [{ block_id: "intro-1" }],
      children: [],
    },
  ],
};

const providerStatus = {
  selected_provider: "gemini",
  selected_model: "gemini-2.0-flash",
  fallback_provider: "mistral",
  fallback_model: "mistral-medium-2505",
  mode: "auto",
  providers: [
    {
      id: "gemini",
      display_name: "Gemini",
      model: "gemini-2.0-flash",
      configured: true,
      online: true,
      health: "OK",
      probe: { status: "OK", detail: "Probe OK" },
      stats: {},
    },
    {
      id: "mistral",
      display_name: "Mistral",
      model: "mistral-medium-2505",
      configured: true,
      online: true,
      health: "OK",
      probe: { status: "OK", detail: "Probe OK" },
      stats: {},
    },
  ],
};

test("wizard surfaces 429 quota error and keeps retry path", async ({ page }) => {
  await page.route(/\/api\/projects(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(/\/api\/formats(?:\/[^/?]+\/prompt-package)?(?:\?.*)?$/, async (route) => {
    const url = route.request().url();
    if (url.includes("/prompt-package")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(promptPackage),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        formats: [
          {
            id: formatId,
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

  await page.route("**/api/projects/draft", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: projectId,
        projectId,
        status: "draft",
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}`, async (route) => {
    if (route.request().method() === "PUT") {
      const payload = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: projectId,
          status: "draft",
          title: payload?.title || "Proyecto E2E Quota",
          format_id: payload?.formatId || formatId,
          prompt_id: payload?.promptId || promptPackage.id,
          selected_sections: payload?.selectedSections || promptPackage.selected_sections,
          prompt_snapshot: payload?.promptSnapshot || promptPackage,
          values: payload?.values || {},
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: projectId,
        status: "draft",
        format_id: formatId,
        prompt_id: promptPackage.id,
      }),
    });
  });

  await page.route(/\/api\/providers\/status(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(providerStatus),
    });
  });

  await page.route(/\/api\/providers\/select(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...providerStatus,
        selection: {
          provider: providerStatus.selected_provider,
          model: providerStatus.selected_model,
          fallback_provider: providerStatus.fallback_provider,
          fallback_model: providerStatus.fallback_model,
          mode: providerStatus.mode,
        },
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}/generate`, async (route) => {
    await route.fulfill({
      status: 429,
      contentType: "application/json",
      headers: {
        "Retry-After": "30",
      },
      body: JSON.stringify({
        detail: "Quota exceeded. Check Gemini project quota/billing. Retry after 30 seconds.",
      }),
    });
  });

  await page.goto("/");
  await page.click("#nav-wizard");

  await page.click("#formats-grid .format-card");
  await expect(page.locator("#btn-step1-next")).toBeEnabled();
  await page.click("#btn-step1-next");

  await expect(page.locator("#chapter-selection-grid .chapter-card")).toHaveCount(1);
  await expect(page.locator("#btn-step2-next")).toBeEnabled();
  await page.click("#btn-step2-next");

  await page.fill("#var_title", "Proyecto E2E Quota");
  await page.fill('[data-variable="objetivo_general"]', "Probar manejo de cuota.");
  await page.click("#btn-step3-next-provider");

  await expect(page.locator("#provider-cards")).toContainText("Gemini");
  await page.click("#btn-step4-generate");

  await expect(page.locator("#gen-error")).toContainText("Quota exceeded");
  await expect(page.locator("#btn-gen-retry")).toBeVisible();
});
