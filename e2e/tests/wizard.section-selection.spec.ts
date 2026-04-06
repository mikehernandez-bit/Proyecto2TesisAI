import { expect, test } from "@playwright/test";

const formatId = "fmt-demo-003";
const projectId = "proj-e2e-sections-001";

const promptPackage = {
  id: "promptpkg_fmt_demo_003",
  name: "Paquete Demo Secciones",
  format_id: formatId,
  format_name: "Formato Demo Secciones",
  format_version: "v1",
  doc_type: "tesis",
  template: "Base {{tema}}",
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
          instructions: "Usa el contexto institucional.",
          required_variables: ["variable_contextual"],
          required: true,
        },
      ],
    },
    {
      section_id: "problema",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
      section_title: "Realidad problemática",
      parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
      section_level: 2,
      optional: false,
      default_selected: true,
      source_hints: "",
      blocks: [
        {
          block_id: "problema-1",
          label: "Realidad problemática",
          instructions: "Sustenta con variable dependiente.",
          required_variables: ["variable_dependiente"],
          required: true,
        },
      ],
    },
    {
      section_id: "resumen",
      section_path: "RESUMEN",
      section_title: "Resumen",
      parent_section_path: "",
      section_level: 1,
      optional: true,
      default_selected: false,
      source_hints: "",
      blocks: [],
    },
  ],
  selected_sections: [
    { section_id: "intro", section_path: "INTRODUCCION" },
    {
      section_id: "problema",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
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
    {
      section_id: "problema",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
      section_title: "Realidad problemática",
      section_level: 2,
      optional: false,
      default_selected: true,
      blocks: [{ block_id: "problema-1" }],
      children: [],
    },
    {
      section_id: "resumen",
      section_path: "RESUMEN",
      section_title: "Resumen",
      section_level: 1,
      optional: true,
      default_selected: false,
      blocks: [],
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

test("wizard details and IA trace only use selected sections", async ({ page }) => {
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
            title: "Formato Demo Secciones",
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
          title: payload?.title || "Proyecto selección",
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
        selected_sections: [
          {
            section_id: "problema",
            section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
          },
        ],
        generation_phase: {
          status: "running",
          total_sections: 1,
          current_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
          current_section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
          base_prompt: "Base Proyecto selección",
          planned_sections: [
            {
              section_id: "problema",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
              section_title: "Realidad problemática",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
            },
          ],
          sections: [
            {
              section_id: "problema",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problemática",
              section_title: "Realidad problemática",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              status: "ok",
              provider: "mistral",
              model: "mistral-medium-2505",
              prompt_sent: "Prompt combinado para realidad problemática",
              ai_output: "Salida IA solo para realidad problemática",
              total_tokens: 1200,
              input_tokens: 900,
              output_tokens: 300,
              duration_ms: 1800,
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
        provider: "mistral",
        model: "mistral-medium-2505",
        selectionMode: "fixed",
      }),
    });
  });

  await page.goto("/");
  await page.click("#nav-wizard");

  await page.click("#formats-grid .format-card");
  await page.click("#btn-step1-next");

  await expect(page.locator("#chapter-selection-grid .chapter-card")).toHaveCount(3);
  await page.locator('#chapter-selection-grid .chapter-card:has-text("Introducción")').click();
  await page.click("#btn-step2-next");

  await expect(page.locator('[data-variable="variable_contextual"]')).toHaveCount(0);
  await expect(page.locator('[data-variable="variable_dependiente"]')).toHaveCount(1);

  await page.fill("#var_title", "Proyecto selección");
  await page.fill('[data-variable="variable_dependiente"]', "Desempeño académico");
  await page.click("#btn-step3-next-provider");
  await page.click("#btn-step4-generate");

  await expect(page.locator("#gen-ai-count")).toContainText("1/1");
  await expect(page.locator("#gen-ai-section-list")).toContainText("Realidad problemática");
  await expect(page.locator("#gen-ai-section-list")).not.toContainText("Introducción");
  await expect(page.locator("#gen-ai-detail-prompt")).toContainText("Prompt combinado");
  await expect(page.locator("#gen-ai-detail-response")).toContainText("Salida IA solo para realidad problemática");
});
