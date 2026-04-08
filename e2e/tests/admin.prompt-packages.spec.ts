import { expect, test } from "@playwright/test";

const formatId = "unac-informe-cual";
const packageId = "promptpkg_unac_informe_cual";

const promptPackage = {
  id: packageId,
  name: "Paquete institucional UNAC Informe",
  format_id: formatId,
  format_name: "Informe de Tesis UNAC - Enfoque Cualitativo",
  format_version: "v1",
  doc_type: "tesis",
  template: "Base institucional {{title}}",
  system_instruction: "",
  is_active: true,
  variables: ["title"],
  sections: [
    {
      section_id: "cap1",
      section_path: "CAPITULO I",
      section_title: "CAPITULO I",
      parent_section_path: "",
      section_level: 1,
      section_order: 1,
      optional: false,
      default_selected: true,
      source_hints: "Agrupa el capitulo institucional.",
      blocks: [],
    },
    {
      section_id: "intro",
      section_path: "CAPITULO I/Introduccion",
      section_title: "Introduccion",
      parent_section_path: "CAPITULO I",
      section_level: 2,
      section_order: 2,
      optional: false,
      default_selected: true,
      source_hints: "",
      blocks: [
        {
          block_id: "intro-1",
          label: "Prompt 1",
          instructions: "Redacta la introduccion con contexto academico.",
          required_variables: ["variable_contextual"],
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
      section_order: 3,
      optional: true,
      default_selected: false,
      source_hints: "",
      blocks: [],
    },
  ],
};

test("admin prompt packages opens institutional section editor and saves", async ({ page }) => {
  await page.route(/\/api\/projects(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`**/api/formats/${formatId}/prompt-package`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(promptPackage),
    });
  });

  await page.route(`**/api/prompts/${packageId}`, async (route) => {
    const payload = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...promptPackage,
        ...payload,
      }),
    });
  });

  page.on("dialog", async (dialog) => {
    await dialog.accept();
  });

  await page.goto("/");

  await page.click("#nav-admin-prompts");
  await expect(page.getByRole("heading", { name: "Paquetes Universitarios" })).toBeVisible();
  await page.waitForFunction(() => window.__promptAdminListBooted === true);

  await page.locator("#card-unac").click();
  await expect(page.locator("#panel-unac")).toBeVisible();
  await page.locator('#panel-unac .btn-accordion[data-target="unac-inf"]').click();
  await page.locator('button.btn-edit-pkg[data-format-id="unac-informe-cual"]').first().click();

  await expect(page.locator("#view-prompt-index")).toBeVisible();
  await expect(page.locator("#index-title")).toContainText("Paquete institucional UNAC Informe");
  await expect(page.locator("#prompt-package-context-panel")).toBeVisible();
  await expect(page.locator("#package-base-template")).toHaveValue("Base institucional {{title}}");
  const chapterCard = page.locator("#index-blocks-container > button").first();
  await expect(chapterCard).toContainText("CAPITULO I");
  await expect(page.locator("#index-blocks-container")).not.toContainText("Introduccion");
  await expect(chapterCard.locator(".js-tree-toggle")).toContainText("+");
  await chapterCard.locator(".js-tree-toggle").click();
  await expect(chapterCard.locator(".js-tree-toggle")).toContainText("-");
  await expect(page.locator("#index-blocks-container")).toContainText("Introduccion");

  await page.locator("#index-blocks-container > button").nth(1).click();

  await expect(page.locator("#modal-manual-config")).toBeVisible();
  await expect(page.locator("#manual-title-display")).toContainText("INFORME TESIS");
  await expect(page.locator("#manual-subtitle-display")).toContainText("CUALITATIVA");
  await expect(page.locator("#prompts-container")).toContainText("Introduccion");
  await expect(page.locator("#modal-manual-config")).not.toContainText("Contexto base del paquete");
  await expect(page.locator("#modal-manual-config")).not.toContainText("Bloque obligatorio");

  await page.locator(".prompt-block-header").fill("Bloque principal");
  await page.locator(".prompt-block-instructions").fill("Instrucciones E2E para la introduccion.");
  await page.getByRole("button", { name: /Guardar Paquete/i }).click();

  await expect(page.locator("#modal-manual-config")).toBeHidden();
  await expect(page.locator("#index-blocks-container")).toContainText("Introduccion");
});

test("admin prompt packages lets prompt management customize package structure", async ({ page }) => {
  let savedPayload: any = null;

  await page.route(/\/api\/projects(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`**/api/formats/${formatId}/prompt-package`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(promptPackage),
    });
  });

  await page.route(`**/api/prompts/${packageId}`, async (route) => {
    savedPayload = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...promptPackage,
        ...savedPayload,
      }),
    });
  });

  page.on("dialog", async (dialog) => {
    await dialog.accept();
  });

  await page.goto("/");
  await page.click("#nav-admin-prompts");
  await page.waitForFunction(() => window.__promptAdminListBooted === true);

  await page.locator("#card-unac").click();
  await page.locator('#panel-unac .btn-accordion[data-target="unac-inf"]').click();
  await page.locator('button.btn-edit-pkg[data-format-id="unac-informe-cual"]').first().click();

  await expect(page.locator("#prompt-package-structure-panel")).toBeVisible();
  await page.locator("#package-base-template").fill("Contexto global actualizado para todo el paquete.");

  await page.selectOption("#admin-custom-structure-kind", "chapter");
  await page.fill("#admin-custom-section-title", "CAPITULO ESPECIAL");
  await page.click("#btn-add-admin-custom-structure");

  await expect(page.locator("#index-blocks-container")).toContainText("CAPITULO ESPECIAL");
  await expect(page.locator("#admin-custom-structure-list")).toContainText("CAPITULO ESPECIAL");

  await page.selectOption("#admin-custom-structure-kind", "section");
  await page.selectOption("#admin-custom-parent-section", { label: "[Personalizado] CAPITULO ESPECIAL" });
  await page.fill("#admin-custom-section-title", "3.1 Aplicacion piloto");
  await page.fill("#admin-custom-block-header", "Aplicacion piloto");
  await page.fill("#admin-custom-block-prompt", "Describe el piloto personalizado.");
  await page.fill("#admin-custom-block-variables", "alcance_piloto");
  await page.click("#btn-add-admin-custom-structure");

  await expect(page.locator("#admin-custom-structure-list")).toContainText("3.1 Aplicacion piloto");

  await page.selectOption("#admin-custom-structure-kind", "block");
  await page.selectOption("#admin-custom-target-section", { label: "CAPITULO I > Introduccion" });
  await page.fill("#admin-custom-block-header", "Analisis adicional");
  await page.fill("#admin-custom-block-prompt", "Amplia el diagnostico con evidencia complementaria.");
  await page.fill("#admin-custom-block-variables", "fuente_adicional");
  await page.click("#btn-add-admin-custom-structure");

  await expect(page.locator("#admin-custom-structure-list")).toContainText("Analisis adicional");

  await page.getByRole("button", { name: /Guardar estructura del paquete/i }).click();

  expect(savedPayload).toBeTruthy();
  expect(savedPayload.template).toBe("Contexto global actualizado para todo el paquete.");
  expect(savedPayload.sections.map((item: any) => item.section_path)).toContain("CAPITULO ESPECIAL");
  expect(savedPayload.sections.map((item: any) => item.section_path)).toContain("CAPITULO ESPECIAL/3.1 Aplicacion piloto");

  const introSection = savedPayload.sections.find((item: any) => item.section_path === "CAPITULO I/Introduccion");
  expect(introSection.blocks.some((block: any) => block.header === "Analisis adicional")).toBeTruthy();
});
