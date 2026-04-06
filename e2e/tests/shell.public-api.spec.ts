import { expect, test } from "@playwright/test";

test("compatibility facade keeps legacy prompt and n8n methods callable", async ({ page }) => {
  await page.route(/\/api\/projects(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("/");

  const methodTypes = await page.evaluate(() => ({
    openPromptModal: typeof window.TesisAI?.openPromptModal,
    closePromptModal: typeof window.TesisAI?.closePromptModal,
    copyN8nPayload: typeof window.TesisAI?.copyN8nPayload,
    copyN8nHeaders: typeof window.TesisAI?.copyN8nHeaders,
    copyN8nWebhook: typeof window.TesisAI?.copyN8nWebhook,
    exportN8nGuide: typeof window.TesisAI?.exportN8nGuide,
  }));

  expect(methodTypes).toEqual({
    openPromptModal: "function",
    closePromptModal: "function",
    copyN8nPayload: "function",
    copyN8nHeaders: "function",
    copyN8nWebhook: "function",
    exportN8nGuide: "function",
  });

  const noThrow = await page.evaluate(async () => {
    window.TesisAI.openPromptModal?.();
    window.TesisAI.closePromptModal?.();
    await Promise.resolve(window.TesisAI.copyN8nPayload?.());
    await Promise.resolve(window.TesisAI.copyN8nHeaders?.());
    await Promise.resolve(window.TesisAI.copyN8nWebhook?.());
    window.TesisAI.exportN8nGuide?.();
    return true;
  });

  expect(noThrow).toBe(true);
});
