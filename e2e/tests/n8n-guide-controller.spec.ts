import { expect, test } from "@playwright/test";

test("n8n guide controller renders, copies and exports without app-shell logic", async ({ page }) => {
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
      <div id="n8n-guide-empty"></div>
      <div id="n8n-guide-content" class="hidden"></div>
      <div id="n8n-summary"></div>
      <ul id="n8n-autocheck"></ul>
      <pre id="n8n-payload"></pre>
      <pre id="n8n-headers"></pre>
      <ul id="n8n-checklist"></ul>
      <div id="n8n-urls"></div>
      <pre id="n8n-format-detail"></pre>
      <pre id="n8n-format-definition"></pre>
      <pre id="n8n-prompt-text"></pre>
      <pre id="n8n-expected-response"></pre>
      <pre id="n8n-sim-output"></pre>
      <div id="sim-run-status"></div>
      <button id="btn-export-guide"></button>
      <button id="btn-run-sim"></button>
    `;
  });

  const result = await page.evaluate(async () => {
    const { createN8nGuideController } = await import("/static/js/features/n8n/n8n-guide-controller.js");

    const copied: string[] = [];
    const downloads: Array<{ filename: string; text: string }> = [];
    let simulationPayload = null;
    let refreshDashboardCalls = 0;
    let refreshHistoryCalls = 0;

    const controller = createN8nGuideController({
      apiSend: async () => ({
        projectId: "proj-n8n-001",
        runId: "run-n8n-001",
        aiResult: { sections: [{ path: "INTRODUCCION", content: "Contenido" }] },
        artifacts: [{ type: "docx", downloadUrl: "/api/download/proj-n8n-001" }],
      }),
      getElement: (id: string) => document.getElementById(id),
      escapeHtml: (value: unknown) => String(value ?? ""),
      toPrettyJson: (value: unknown) => JSON.stringify(value ?? {}, null, 2),
      copyText: async (text: string) => {
        copied.push(String(text));
      },
      downloadText: (filename: string, text: string) => {
        downloads.push({ filename, text });
      },
      getCurrentProject: () => ({ id: "proj-n8n-001" }),
      refreshDashboard: async () => {
        refreshDashboardCalls += 1;
      },
      refreshHistory: async () => {
        refreshHistoryCalls += 1;
      },
      onSimulationOutput: (payload: unknown) => {
        simulationPayload = payload;
      },
    });

    controller.setSpec({
      summary: {
        format: { id: "fmt-001", title: "Formato Demo" },
        prompt: { id: "prompt-001", name: "Paquete Demo" },
        projectId: "proj-n8n-001",
        status: "draft",
      },
      envCheck: {
        N8N_WEBHOOK_URL: { ok: true, value: "https://n8n.example/webhook/demo" },
      },
      request: {
        webhookUrl: "https://n8n.example/webhook/demo",
        headers: { Authorization: "Bearer demo-token" },
        payload: {
          runtime: {
            callbackUrl: "https://gicagen.example/api/callback",
            gicatesisBaseUrl: "https://gicatesis.example",
          },
          prompt: { text: "Prompt institucional" },
        },
      },
      expectedResponse: {
        headers: { "X-Signature": "sha256=demo" },
        callbackUrl: "https://gicagen.example/api/callback",
        bodyExample: { ok: true, runId: "run-n8n-001" },
      },
      checklist: [
        { title: "Configurar webhook", detail: "Publicar el endpoint n8n." },
      ],
      formatDetail: { id: "fmt-001" },
      formatDefinition: { chapters: [{ id: "intro" }] },
      promptDetail: { text: "Prompt institucional" },
      promptText: "Prompt institucional",
      markdown: "# Guia n8n",
    });

    await controller.copyPayload();
    await controller.copyHeaders();
    await controller.copyWebhook();
    controller.exportGuide();
    await controller.runSimulation();

    return {
      emptyHidden: document.getElementById("n8n-guide-empty")?.classList.contains("hidden"),
      contentVisible: !document.getElementById("n8n-guide-content")?.classList.contains("hidden"),
      summary: document.getElementById("n8n-summary")?.textContent || "",
      payload: document.getElementById("n8n-payload")?.textContent || "",
      headers: document.getElementById("n8n-headers")?.textContent || "",
      simOutput: document.getElementById("n8n-sim-output")?.textContent || "",
      simStatus: document.getElementById("sim-run-status")?.textContent || "",
      copied,
      downloads,
      simulationPayload,
      refreshDashboardCalls,
      refreshHistoryCalls,
    };
  });

  expect(result.emptyHidden).toBe(true);
  expect(result.contentVisible).toBe(true);
  expect(result.summary).toContain("Formato Demo");
  expect(result.payload).toContain("callbackUrl");
  expect(result.headers).toContain("X-Signature");
  expect(result.simOutput).toContain("run-n8n-001");
  expect(result.simStatus).toContain("runId: run-n8n-001");
  expect(result.copied).toHaveLength(3);
  expect(result.copied[0]).toContain("callbackUrl");
  expect(result.copied[1]).toContain("Authorization");
  expect(result.copied[2]).toContain("https://n8n.example/webhook/demo");
  expect(result.downloads).toHaveLength(1);
  expect(result.downloads[0]?.filename).toBe("n8n-guide-proj-n8n-001.md");
  expect(result.downloads[0]?.text).toContain("# Guia n8n");
  expect(result.simulationPayload).toMatchObject({
    projectId: "proj-n8n-001",
    runId: "run-n8n-001",
  });
  expect(result.refreshDashboardCalls).toBe(1);
  expect(result.refreshHistoryCalls).toBe(1);
});
