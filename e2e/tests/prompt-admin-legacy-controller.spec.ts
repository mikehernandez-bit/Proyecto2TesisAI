import { expect, test } from "@playwright/test";

test("legacy prompt admin controller preserves modal, save and refresh flows", async ({ page }) => {
  await page.route(/\/api\/projects(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("/");
  await page.evaluate(() => {
    document.body.innerHTML = `
      <div id="modal-error" class="hidden"></div>
      <div id="modal-prompt" class="hidden"></div>
      <div id="modal-title"></div>
      <input id="modal-prompt-id" />
      <input id="modal-name" />
      <select id="modal-doc-type">
        <option value="Tesis Completa">Tesis Completa</option>
        <option value="Proyecto">Proyecto</option>
      </select>
      <input id="modal-is-active" type="checkbox" />
      <textarea id="modal-template"></textarea>
      <textarea id="modal-vars"></textarea>
      <div id="prompts-grid"></div>
      <table><tbody id="prompts-table"></tbody></table>
      <div id="prompts-empty" class="hidden"></div>
    `;
  });

  const result = await page.evaluate(async () => {
    const { createPromptAdminLegacyController } = await import("/static/js/features/prompt-admin-legacy/prompt-admin-controller.js");

    let prompts = [
      {
        id: "legacy-001",
        name: "Prompt legado",
        doc_type: "Tesis Completa",
        is_active: true,
        template: "Plantilla legado",
        variables: ["tema"],
        metodologia: "INF",
        categoria: "CUALI",
        prompts: [
          {
            numero_prompt: "1",
            capitulo_nombre: "Capitulo I",
            titulo_cabecera: "Introduccion",
          },
        ],
      },
    ];
    let onPromptsChangedCalls = 0;
    let step2Enabled = false;

    const controller = createPromptAdminLegacyController({
      apiGet: async () => prompts,
      apiSend: async (url: string, method: string, body?: Record<string, unknown>) => {
        if (url === "/api/prompts" && method === "POST") {
          prompts = [
            ...prompts,
            {
              id: "legacy-002",
              name: String(body?.name || ""),
              doc_type: String(body?.doc_type || "Tesis Completa"),
              is_active: Boolean(body?.is_active),
              template: String(body?.template || ""),
              variables: Array.isArray(body?.variables) ? body.variables : [],
              metodologia: "INF",
              categoria: "CUALI",
              prompts: [],
            },
          ];
          return prompts[prompts.length - 1];
        }
        if (url.startsWith("/api/prompts/") && method === "DELETE") {
          const id = decodeURIComponent(url.split("/").pop() || "");
          prompts = prompts.filter((item) => item.id !== id);
          return { ok: true };
        }
        return { ok: true };
      },
      getElement: (id: string) => document.getElementById(id),
      escapeHtml: (value: unknown) => String(value ?? ""),
      wizardStateRef: () => ({ module: "", enfoque: "", chapters: [] }),
      setStep2NextEnabled: (enabled: boolean) => {
        step2Enabled = enabled;
      },
      onPromptsChanged: async () => {
        onPromptsChangedCalls += 1;
      },
      confirmDelete: () => true,
    });

    await controller.refreshPromptsAdmin();
    const initialRows = document.querySelectorAll("#prompts-table tr").length;

    controller.openPromptModal();
    (document.getElementById("modal-name") as HTMLInputElement).value = "Prompt nuevo";
    (document.getElementById("modal-doc-type") as HTMLSelectElement).value = "Proyecto";
    (document.getElementById("modal-is-active") as HTMLInputElement).checked = true;
    (document.getElementById("modal-template") as HTMLTextAreaElement).value = "Plantilla nueva";
    (document.getElementById("modal-vars") as HTMLTextAreaElement).value = JSON.stringify(["tema", "objetivo_general"]);
    await controller.savePrompt();

    const rowsAfterSave = document.querySelectorAll("#prompts-table tr").length;
    const modalHiddenAfterSave = document.getElementById("modal-prompt")?.classList.contains("hidden");

    controller.renderModules(prompts);
    const moduleCards = document.querySelectorAll("#prompts-grid > div").length;
    (document.querySelector("#prompts-grid > div:last-child") as HTMLElement | null)?.click();
    (Array.from(document.querySelectorAll("#prompts-grid > div")) as HTMLElement[])
      .find((node) => !node.classList.contains("col-span-full"))
      ?.click();
    const chapterOptions = Array.from(document.querySelectorAll(".chapter-option"));
    if (chapterOptions[0]) {
      (chapterOptions[0] as HTMLElement).click();
    }

    await controller.deletePrompt("legacy-001");
    const rowsAfterDelete = document.querySelectorAll("#prompts-table tr").length;

    return {
      initialRows,
      rowsAfterSave,
      rowsAfterDelete,
      modalHiddenAfterSave,
      moduleCards,
      chapterOptions: chapterOptions.length,
      step2Enabled,
      onPromptsChangedCalls,
      emptyHidden: document.getElementById("prompts-empty")?.classList.contains("hidden"),
      tableText: document.getElementById("prompts-table")?.textContent || "",
    };
  });

  expect(result.initialRows).toBe(1);
  expect(result.rowsAfterSave).toBe(2);
  expect(result.rowsAfterDelete).toBe(1);
  expect(result.modalHiddenAfterSave).toBe(true);
  expect(result.moduleCards).toBeGreaterThan(0);
  expect(result.chapterOptions).toBeGreaterThan(0);
  expect(result.step2Enabled).toBe(true);
  expect(result.onPromptsChangedCalls).toBeGreaterThanOrEqual(2);
  expect(result.emptyHidden).toBe(true);
  expect(result.tableText).toContain("Prompt nuevo");
});
