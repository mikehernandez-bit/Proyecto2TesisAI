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
      section_id: "intro",
      section_path: "CAPITULO I/Introduccion",
      section_title: "Introduccion",
      parent_section_path: "CAPITULO I",
      section_level: 2,
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

  await page.getByRole("button", { name: "Gestión Prompts" }).click();
  await expect(page.getByRole("heading", { name: "Paquetes Universitarios" })).toBeVisible();

  await page.locator("#card-unac").click();
  await expect(page.locator("#panel-unac")).toBeVisible();
  await page.locator('#panel-unac .btn-accordion[data-target="unac-inf"]').click();
  await page.locator('button.btn-edit-pkg[data-format-id="unac-informe-cual"]').first().click();

  await expect(page.locator("#view-prompt-index")).toBeVisible();
  await expect(page.locator("#index-title")).toContainText("Paquete institucional UNAC Informe");
  await expect(page.getByRole("button", { name: /Introduccion/i })).toBeVisible();

  await page.getByRole("button", { name: /Introduccion/i }).click();

  await expect(page.locator("#modal-manual-config")).toBeVisible();
  await expect(page.locator("#manual-subtitle-display")).toContainText("Introduccion");

  await page.locator(".prompt-block-label").fill("Bloque principal");
  await page.locator(".prompt-block-instructions").fill("Instrucciones E2E para la introduccion.");
  await page.getByRole("button", { name: /Guardar Paquete/i }).click();

  await expect(page.locator("#modal-manual-config")).toBeHidden();
  await expect(page.locator("#index-blocks-container")).toContainText("Introduccion");
});
