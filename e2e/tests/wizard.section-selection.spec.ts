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
      section_title: "Introduccion",
      parent_section_path: "",
      section_level: 1,
      section_order: 1,
      optional: false,
      default_selected: true,
      source_hints: "",
      blocks: [
        {
          block_id: "intro-1",
          header: "Contexto introductorio",
          label: "Introduccion",
          instructions: "Usa el contexto institucional.",
          required_variables: ["variable_contextual"],
          required: true,
        },
      ],
    },
    {
      section_id: "cap1",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
      section_title: "I. PLANTEAMIENTO DEL PROBLEMA",
      parent_section_path: "",
      section_level: 1,
      section_order: 2,
      optional: false,
      default_selected: true,
      source_hints: "Agrupa las subsecciones del capitulo I.",
      blocks: [],
    },
    {
      section_id: "problema",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
      section_title: "1.1 Realidad problematica",
      parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
      section_level: 2,
      section_order: 3,
      optional: false,
      default_selected: true,
      source_hints: "",
      blocks: [
        {
          block_id: "problema-1",
          header: "Realidad problematica",
          label: "Realidad problematica",
          instructions: "Sustenta con variable dependiente.",
          required_variables: [
            "variable_dependiente",
            "contexto_organizacion",
            "problema_observable",
            "sustento_local",
            "propuesta_solucion_preliminar",
          ],
          required: true,
        },
      ],
    },
    {
      section_id: "formulacion",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
      section_title: "1.2 Formulacion del problema",
      parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
      section_level: 2,
      section_order: 4,
      optional: false,
      default_selected: true,
      source_hints: "Define la pregunta central.",
      blocks: [
        {
          block_id: "formulacion-1",
          header: "Formulacion del problema",
          label: "Formulacion del problema",
          instructions: "Redacta la pregunta principal.",
          required_variables: ["pregunta_principal"],
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
      section_order: 5,
      optional: true,
      default_selected: false,
      source_hints: "",
      blocks: [],
    },
    {
      section_id: "anexos",
      section_path: "ANEXOS",
      section_title: "ANEXOS",
      parent_section_path: "",
      section_level: 1,
      section_order: 6,
      optional: true,
      default_selected: false,
      source_hints: "",
      blocks: [],
    },
  ],
  selected_sections: [
    { section_id: "intro", section_path: "INTRODUCCION", section_order: 1 },
    {
      section_id: "problema",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
      section_order: 3,
    },
  ],
  section_tree: [
    {
      section_id: "intro",
      section_path: "INTRODUCCION",
      section_title: "Introduccion",
      section_level: 1,
      section_order: 1,
      optional: false,
      default_selected: true,
      blocks: [{ block_id: "intro-1" }],
      children: [],
    },
    {
      section_id: "cap1",
      section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
      section_title: "I. PLANTEAMIENTO DEL PROBLEMA",
      section_level: 1,
      section_order: 2,
      optional: false,
      default_selected: true,
      blocks: [],
      children: [
        {
          section_id: "problema",
          section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
          section_title: "1.1 Realidad problematica",
          parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
          section_level: 2,
          section_order: 3,
          optional: false,
          default_selected: true,
          blocks: [{ block_id: "problema-1" }],
          children: [],
        },
        {
          section_id: "formulacion",
          section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
          section_title: "1.2 Formulacion del problema",
          parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
          section_level: 2,
          section_order: 4,
          optional: false,
          default_selected: true,
          blocks: [{ block_id: "formulacion-1" }],
          children: [],
        },
      ],
    },
    {
      section_id: "resumen",
      section_path: "RESUMEN",
      section_title: "Resumen",
      section_level: 1,
      section_order: 5,
      optional: true,
      default_selected: false,
      blocks: [],
      children: [],
    },
    {
      section_id: "anexos",
      section_path: "ANEXOS",
      section_title: "ANEXOS",
      section_level: 1,
      section_order: 6,
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

test("wizard ignores stale package loads and keeps select-all stable", async ({ page }) => {
  let releaseFirstPackage: (() => void) | null = null;
  const firstPackageGate = new Promise<void>((resolve) => {
    releaseFirstPackage = resolve;
  });
  const secondFormatId = "fmt-demo-004";
  const secondPackage = {
    ...promptPackage,
    id: "promptpkg_fmt_demo_004",
    format_id: secondFormatId,
    format_name: "Formato Demo Secciones B",
  };

  await page.route(/\/api\/projects(?:\?.*)?$/, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: "proj-race", projectId: "proj-race", status: "draft" }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route(/\/api\/formats(?:\/[^/?]+\/prompt-package)?(?:\?.*)?$/, async (route) => {
    const url = route.request().url();
    if (url.includes(`${formatId}/prompt-package`)) {
      await firstPackageGate;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(promptPackage) });
      return;
    }
    if (url.includes(`${secondFormatId}/prompt-package`)) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(secondPackage) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        formats: [
          { id: formatId, title: "Formato Demo Secciones A", university: "demo", category: "general", version: "v1" },
          { id: secondFormatId, title: "Formato Demo Secciones B", university: "demo", category: "general", version: "v1" },
        ],
        stale: false,
        source: "demo",
      }),
    });
  });

  await page.goto("/");
  await page.click("#nav-wizard");
  await page.locator("#formats-grid .format-card").nth(0).click();
  await page.click("#btn-step1-next");

  await expect(page.locator("#btn-step2-select-all")).toBeDisabled();
  await expect(page.locator("#chapter-selection-grid")).toContainText("Cargando paquete institucional");

  await page.click('#step-2-content [data-action="app.prevStep"]');
  await page.locator("#formats-grid .format-card").nth(1).click();
  await page.click("#btn-step1-next");
  await expect(page.locator("#step2-format-name-display")).toHaveText("Formato Demo Secciones B");
  await expect(page.locator("#btn-step2-select-all")).toBeEnabled();

  await page.click("#btn-step2-select-all");
  await expect(page.locator("#chapter-selection-grid .wizard-tree-checkbox:checked")).toHaveCount(4);

  releaseFirstPackage?.();
  await page.waitForTimeout(250);
  await expect(page.locator("#step2-format-name-display")).toHaveText("Formato Demo Secciones B");
  await expect(page.locator("#chapter-selection-grid .wizard-tree-checkbox:checked")).toHaveCount(4);
  await expect(page.locator("#btn-step2-next")).toBeEnabled();

  await page.click("#btn-step2-select-all");
  await expect(page.locator("#chapter-selection-grid .wizard-tree-checkbox:checked")).toHaveCount(0);
  await expect(page.locator("#btn-step2-next")).toBeDisabled();
});

test("wizard renders tree in institutional order, expands/collapses, and persists recursive concrete selection", async ({ page }) => {
  const draftPayloads: any[] = [];
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

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
    draftPayloads.push(route.request().postDataJSON());
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
      draftPayloads.push(payload);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: projectId,
          status: "draft",
          title: payload?.title || "Proyecto seleccion",
          format_id: payload?.formatId || formatId,
          prompt_id: payload?.promptId || promptPackage.id,
          selected_sections: payload?.selectedSections || promptPackage.selected_sections,
          prompt_snapshot: payload?.promptSnapshot || promptPackage,
          values: payload?.values || {},
        }),
      });
      return;
    }

    const selectedSections = draftPayloads[draftPayloads.length - 1]?.selectedSections || promptPackage.selected_sections;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: projectId,
        status: "processing",
        format_id: formatId,
        prompt_id: promptPackage.id,
        selected_sections: selectedSections,
        generation_phase: {
          status: "running",
          total_sections: 2,
          current_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
          current_section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
          base_prompt: "Base Proyecto seleccion",
          planned_sections: [
            {
              section_id: "problema",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
              section_title: "1.1 Realidad problematica",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              section_order: 3,
            },
            {
              section_id: "formulacion",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
              section_title: "1.2 Formulacion del problema",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              section_order: 4,
            },
          ],
          sections: [
            {
              section_id: "problema",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
              section_title: "1.1 Realidad problematica",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              status: "ok",
              provider: "mistral",
              model: "mistral-medium-2505",
              prompt_sent: "Prompt combinado para realidad problematica",
              ai_output: "Salida IA para realidad problematica",
              total_tokens: 1200,
              input_tokens: 900,
              output_tokens: 300,
              duration_ms: 1800,
            },
            {
              section_id: "formulacion",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
              section_title: "1.2 Formulacion del problema",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              status: "ok",
              provider: "mistral",
              model: "mistral-medium-2505",
              prompt_sent: "Prompt combinado para formulacion del problema",
              ai_output: "Salida IA para formulacion del problema",
              total_tokens: 1000,
              input_tokens: 760,
              output_tokens: 240,
              duration_ms: 1500,
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

  const visibleTitles = await page.locator("#chapter-selection-grid .chapter-card .font-bold.text-slate-800").allTextContents();
  expect(visibleTitles).toEqual([
    "Introduccion",
    "I. PLANTEAMIENTO DEL PROBLEMA",
    "Resumen",
    "ANEXOS",
  ]);

  const chapterCard = page.locator("#chapter-selection-grid .chapter-card").nth(1);
  const chapterToggle = chapterCard.locator(".wizard-tree-toggle");

  await expect(chapterToggle).toContainText("+");
  await expect(page.locator("#chapter-selection-grid")).not.toContainText("1.1 Realidad problematica");
  await chapterToggle.click();
  await expect(chapterToggle).toContainText("-");
  await expect(page.locator("#chapter-selection-grid")).toContainText("1.2 Formulacion del problema");
  await expect(chapterCard).not.toContainText("Agrupa las subsecciones del capitulo I.");
  await chapterToggle.click();
  await expect(chapterToggle).toContainText("+");
  await expect(page.locator("#chapter-selection-grid")).not.toContainText("1.2 Formulacion del problema");

  await page.getByRole("button", { name: /Seleccionar \/ deseleccionar todo/i }).click();
  await expect(page.locator("#btn-step2-next")).toBeEnabled();
  await expect(
    page.locator("#chapter-selection-grid .wizard-tree-checkbox:checked"),
  ).toHaveCount(4);
  await chapterToggle.click();
  await expect(chapterToggle).toContainText("-");
  await expect(
    page.locator("#chapter-selection-grid .wizard-tree-checkbox:checked"),
  ).toHaveCount(6);
  await chapterToggle.click();
  await expect(chapterToggle).toContainText("+");
  await page.getByRole("button", { name: /Seleccionar \/ deseleccionar todo/i }).click();
  await expect(page.locator("#btn-step2-next")).toBeDisabled();
  await expect(
    page.locator("#chapter-selection-grid .wizard-tree-checkbox:checked"),
  ).toHaveCount(0);

  await chapterCard.click();
  await page.locator("#step-2-content").evaluate((element) => {
    (element as HTMLElement).style.minHeight = "2200px";
  });
  await page.locator("#app-main-scroll").evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect.poll(() => page.locator("#app-main-scroll").evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await page.click("#btn-step2-next");

  await expect(page.locator("#step-3-content > div > div h3").first()).toContainText("3. Detalles del Proyecto");
  await expect.poll(() => page.locator("#app-main-scroll").evaluate((element) => element.scrollTop)).toBe(0);
  await expect(page.locator("#var_title")).toBeInViewport();

  await expect(page.locator('[data-variable="variable_contextual"]')).toHaveCount(0);
  await expect(page.locator('[data-variable="variable_dependiente"]')).toHaveCount(1);
  await expect(page.locator('[data-variable="problema_observable"]')).toHaveCount(1);
  await expect(page.locator('[data-variable="pregunta_principal"]')).toHaveCount(1);
  await expect(page.locator("#dynamic-form")).toContainText("Capítulo padre: I. PLANTEAMIENTO DEL PROBLEMA");
  await expect(page.locator("#dynamic-form")).not.toContainText("Cabeceras que usan este dato");
  await expect(page.locator("#dynamic-form")).not.toContainText("Hints de la seccion");

  await page.fill("#var_title", "Proyecto seleccion");
  await page.fill('[data-variable="variable_dependiente"]', "Desempeno academico");
  await page.fill('[data-variable="pregunta_principal"]', "Como mejorar el proceso");
  await page.click("#btn-step3-next-provider");

  expect(pageErrors).toEqual([]);
  expect(draftPayloads).not.toHaveLength(0);
  expect(
    draftPayloads[draftPayloads.length - 1].selectedSections.map((item: any) => item.section_path),
  ).toEqual([
    "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
    "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
  ]);

  await page.click("#btn-step4-generate");

  await expect(page.locator("#gen-ai-count")).toContainText("2/2");
  await expect(page.locator("#gen-ai-section-list")).toContainText("1.1 Realidad problematica");
  await expect(page.locator("#gen-ai-section-list")).toContainText("1.2 Formulacion del problema");
  await expect(page.locator("#gen-ai-section-list")).not.toContainText("Introduccion");
});

test("wizard details for realidad problematica show useful fields without prompt dump or garbage", async ({ page }) => {
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

  await page.goto("/");
  await page.click("#nav-wizard");
  await page.click("#formats-grid .format-card");
  await page.click("#btn-step1-next");

  await page.locator("#chapter-selection-grid .chapter-card").first().click();
  await page.click("#btn-step2-next");

  await expect(page.locator("#dynamic-form")).toContainText("1.1 Realidad problematica");
  await expect(page.locator('[data-variable="variable_dependiente"]')).toHaveCount(1);
  await expect(page.locator('[data-variable="contexto_organizacion"]')).toHaveCount(1);
  await expect(page.locator('[data-variable="problema_observable"]')).toHaveCount(1);
  await expect(page.locator('[data-variable="sustento_local"]')).toHaveCount(1);
  await expect(page.locator('[data-variable="propuesta_solucion_preliminar"]')).toHaveCount(1);
  await expect(page.locator("#dynamic-form")).toContainText("Problema observable");
  await expect(page.locator("#dynamic-form")).toContainText("Contexto de la organización");
  await expect(page.locator("#dynamic-form")).toContainText("Ejemplo:");
  await expect(page.locator("#dynamic-form")).not.toContainText("Cabeceras que usan este dato");
  await expect(page.locator("#dynamic-form")).not.toContainText("XD");
  await expect(page.locator("#dynamic-form")).not.toContainText("Hints de la seccion");
  await expect(page.locator("#dynamic-form")).not.toContainText("Contexto internacional: Describe");
  await expect(page.locator('[data-variable="problema_observable"]')).toHaveAttribute(
    "placeholder",
    "Ej: Demoras frecuentes en la atención de proyectos de investigación.",
  );
});

test("wizard step 2 no longer exposes package customization controls", async ({ page }) => {
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

  await page.goto("/");
  await page.click("#nav-wizard");
  await page.click("#formats-grid .format-card");
  await page.click("#btn-step1-next");

  await expect(page.locator("#step-2-content")).not.toContainText("Personalizar estructura");
  await expect(page.locator("#custom-structure-kind")).toHaveCount(0);
  await expect(page.locator("#btn-add-custom-structure")).toHaveCount(0);
});

test("wizard step 5 keeps institutional order from planned sections even when phase sections arrive scrambled", async ({ page }) => {
  const draftPayloads: any[] = [];
  let generationMode = false;

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
    draftPayloads.push(route.request().postDataJSON());
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
      draftPayloads.push(payload);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: projectId,
          status: generationMode ? "processing" : "draft",
          title: payload?.title || "Proyecto seleccion",
          format_id: payload?.formatId || formatId,
          prompt_id: payload?.promptId || promptPackage.id,
          selected_sections: payload?.selectedSections || promptPackage.selected_sections,
          prompt_snapshot: payload?.promptSnapshot || promptPackage,
          values: payload?.values || {},
        }),
      });
      return;
    }

    const selectedSections = draftPayloads[draftPayloads.length - 1]?.selectedSections || promptPackage.selected_sections;
    if (!generationMode) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: projectId,
          status: "draft",
          format_id: formatId,
          prompt_id: promptPackage.id,
          selected_sections: selectedSections,
          prompt_snapshot: promptPackage,
          values: {},
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
        selected_sections: selectedSections,
        generation_phase: {
          status: "running",
          total_sections: 6,
          completed_sections: 3,
          current_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
          current_section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
          base_prompt: "Base Proyecto seleccion",
          planned_sections: [
            {
              section_id: "titulo-info-basica",
              section_path: "Título + Información Básica",
              path: "Título + Información Básica",
              section_title: "Título + Información Básica",
              parent_section_path: "",
              section_level: 1,
              section_order: -100,
            },
            {
              section_id: "intro",
              section_path: "INTRODUCCIÓN",
              path: "INTRODUCCIÓN",
              section_title: "INTRODUCCIÓN",
              parent_section_path: "",
              section_level: 1,
              section_order: 1,
            },
            {
              section_id: "cap1",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_title: "I. PLANTEAMIENTO DEL PROBLEMA",
              parent_section_path: "",
              section_level: 1,
              section_order: 2,
            },
            {
              section_id: "problema",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
              path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
              section_title: "1.1 Realidad problematica",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              section_order: 3,
            },
            {
              section_id: "formulacion",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
              path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
              section_title: "1.2 Formulacion del problema",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              section_order: 4,
            },
            {
              section_id: "anexos",
              section_path: "ANEXOS",
              path: "ANEXOS",
              section_title: "ANEXOS",
              parent_section_path: "",
              section_level: 1,
              section_order: 99,
            },
          ],
          sections: [
            {
              section_id: "anexos",
              section_path: "ANEXOS",
              path: "ANEXOS",
              section_title: "ANEXOS",
              status: "pending",
              provider: "",
              model: "",
            },
            {
              section_id: "intro",
              section_path: "INTRODUCCIÓN",
              path: "INTRODUCCIÓN",
              section_title: "INTRODUCCIÓN",
              status: "ok",
              provider: "mistral",
              model: "mistral-medium-2505",
            },
            {
              section_id: "titulo-info-basica",
              section_path: "Título + Información Básica",
              path: "Título + Información Básica",
              section_title: "Título + Información Básica",
              status: "ok",
              provider: "mistral",
              model: "mistral-medium-2505",
            },
            {
              section_id: "formulacion",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
              path: "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
              section_title: "1.2 Formulacion del problema",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              status: "generating",
              provider: "mistral",
              model: "mistral-medium-2505",
            },
            {
              section_id: "cap1",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_title: "I. PLANTEAMIENTO DEL PROBLEMA",
              status: "pending",
              provider: "",
              model: "",
            },
            {
              section_id: "problema",
              section_path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
              path: "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
              section_title: "1.1 Realidad problematica",
              parent_section_path: "I. PLANTEAMIENTO DEL PROBLEMA",
              section_level: 2,
              status: "ok",
              provider: "mistral",
              model: "mistral-medium-2505",
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
    generationMode = true;
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

  await page.locator("#chapter-selection-grid .chapter-card").nth(1).click();
  await page.click("#btn-step2-next");
  await page.fill("#var_title", "Proyecto seleccion");
  await page.fill('[data-variable="variable_dependiente"]', "Desempeno academico");
  await page.fill('[data-variable="pregunta_principal"]', "Como mejorar el proceso");
  await page.click("#btn-step3-next-provider");
  await page.click("#btn-step4-generate");

  await expect(page.locator("#gen-ai-section-list")).toContainText("Título + Información Básica");
  await expect(page.locator("#gen-ai-section-list")).toContainText("INTRODUCCIÓN");
  await expect(page.locator("#gen-ai-section-list")).toContainText("ANEXOS");

  const orderedPaths = await page.locator("#gen-ai-section-list [data-ai-node-key]").evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute("data-ai-node-path")),
  );

  expect(orderedPaths).toEqual([
    "Título + Información Básica",
    "INTRODUCCIÓN",
    "I. PLANTEAMIENTO DEL PROBLEMA",
    "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
    "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
    "ANEXOS",
  ]);
});
