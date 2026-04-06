import { expect, test } from "@playwright/test";

const formatId = "fmt-demo-gen-ctrl";
const projectId = "proj-e2e-gen-ctrl-001";

const promptPackage = {
  id: "promptpkg_fmt_demo_gen_ctrl",
  name: "Paquete Demo Control",
  format_id: formatId,
  format_name: "Formato Demo Control",
  format_version: "v1",
  doc_type: "tesis",
  template: "Base {{tema}}",
  variables: ["tema"],
  sections: [
    {
      section_id: "intro",
      section_path: "INTRODUCCION",
      section_title: "Introduccion",
      parent_section_path: "",
      section_level: 1,
      optional: false,
      default_selected: true,
      source_hints: "",
      blocks: [
        {
          block_id: "intro-1",
          label: "Introduccion",
          instructions: "Contextualiza el estudio.",
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
      section_title: "Introduccion",
      section_level: 1,
      optional: false,
      default_selected: true,
      blocks: [{ block_id: "intro-1" }],
      children: [],
    },
  ],
};

const providerStatus = {
  selected_provider: "mistral",
  selected_model: "mistral-medium-2505",
  fallback_provider: "gemini",
  fallback_model: "gemini-2.0-flash",
  mode: "fixed",
  providers: [
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
  ],
};

test("generation controller keeps cancel and retry path alive after extraction", async ({ page }) => {
  let cancelCalls = 0;

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
            title: "Formato Demo Control",
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
          title: payload?.title || "Proyecto Control",
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
        status: "processing",
        format_id: formatId,
        prompt_id: promptPackage.id,
        generation_phase: {
          status: "running",
          total_sections: 1,
          current_path: "INTRODUCCION",
          current_section_path: "INTRODUCCION",
          base_prompt: "Base Proyecto Control",
          planned_sections: promptPackage.sections,
          sections: [
            {
              section_id: "intro",
              section_path: "INTRODUCCION",
              section_title: "Introduccion",
              status: "generating",
              provider: "mistral",
              model: "mistral-medium-2505",
              prompt_sent: "Prompt introduccion",
              ai_output: "",
              total_tokens: 0,
              input_tokens: 0,
              output_tokens: 0,
              duration_ms: 0,
            },
          ],
        },
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
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        status: "processing",
        mode: "ai",
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}/cancel`, async (route) => {
    cancelCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });

  await page.goto("/");
  await page.click("#nav-wizard");
  await page.click("#formats-grid .format-card");
  await page.click("#btn-step1-next");
  await page.click("#btn-step2-next");
  await page.fill("#var_title", "Proyecto Control");
  await page.fill('[data-variable="objetivo_general"]', "Validar cancelacion.");
  await page.click("#btn-step3-next-provider");
  await page.click("#btn-step4-generate");

  await expect(page.locator('[data-testid="step5"]')).toBeVisible();
  await expect(page.locator("#gen-live-summary")).toContainText("Usando:");
  await page.click("#btn-gen-cancel");

  await expect(page.locator("#gen-error")).toContainText("Cancelacion solicitada");
  await expect(page.locator("#btn-gen-retry")).toBeVisible();
  expect(cancelCalls).toBe(1);
});
