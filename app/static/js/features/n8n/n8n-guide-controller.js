export function createN8nGuideController({
  apiSend,
  getElement,
  escapeHtml,
  toPrettyJson,
  copyText,
  downloadText,
  getCurrentProject,
  refreshDashboard,
  refreshHistory,
  onSimulationOutput,
}) {
  let n8nSpec = null;
  let isRunningSimulation = false;

  function reset() {
    n8nSpec = null;
    isRunningSimulation = false;
  }

  function setSpec(spec) {
    n8nSpec = spec && typeof spec === "object" ? spec : null;
    render();
  }

  function getSpec() {
    return n8nSpec;
  }

  function renderList(id, items, mapper) {
    const element = getElement(id);
    if (!element) return;
    element.innerHTML = (Array.isArray(items) ? items : []).map(mapper).join("");
  }

  function render() {
    const empty = getElement("n8n-guide-empty");
    const content = getElement("n8n-guide-content");
    if (!n8nSpec || !empty || !content) return;

    empty.classList.add("hidden");
    content.classList.remove("hidden");

    const summary = n8nSpec.summary || {};
    const summaryFormat = summary.format || {};
    const summaryPrompt = summary.prompt || {};

    const summaryEl = getElement("n8n-summary");
    if (summaryEl) {
      summaryEl.innerHTML = `
        <div><strong>Formato:</strong> ${escapeHtml(summaryFormat.title || summaryFormat.id || "")}</div>
        <div><strong>Prompt:</strong> ${escapeHtml(summaryPrompt.name || summaryPrompt.id || "")}</div>
        <div><strong>projectId:</strong> <code>${escapeHtml(summary.projectId || "")}</code></div>
        <div><strong>status:</strong> ${escapeHtml(summary.status || "")}</div>
      `;
    }

    renderList("n8n-autocheck", Object.entries(n8nSpec.envCheck || {}), ([name, meta]) => {
      const ok = Boolean(meta?.ok);
      const mark = ok ? "OK" : "MISSING";
      const color = ok ? "text-green-600" : "text-red-600";
      return `<li><span class="${color} font-semibold">${mark}</span> <code>${escapeHtml(name)}</code> = ${escapeHtml(meta?.value ?? "")}</li>`;
    });

    const request = n8nSpec.request || {};
    const expected = n8nSpec.expectedResponse || {};
    const payloadRuntime = request.payload?.runtime || {};

    const payloadEl = getElement("n8n-payload");
    if (payloadEl) payloadEl.textContent = toPrettyJson(request.payload || {});
    const headersEl = getElement("n8n-headers");
    if (headersEl) {
      headersEl.textContent = toPrettyJson({
        toN8N: request.headers || {},
        toCallback: expected.headers || {},
      });
    }
    renderList("n8n-checklist", n8nSpec.checklist || [], (item) => (
      `<li><strong>${escapeHtml(item.title || "")}</strong> - ${escapeHtml(item.detail || "")}</li>`
    ));

    const urlsEl = getElement("n8n-urls");
    if (urlsEl) {
      urlsEl.innerHTML = `
        <div><strong>Webhook n8n:</strong> <code>${escapeHtml(request.webhookUrl || "")}</code></div>
        <div><strong>Callback GicaGen:</strong> <code>${escapeHtml(expected.callbackUrl || payloadRuntime.callbackUrl || "")}</code></div>
        <div><strong>GicaTesis base:</strong> <code>${escapeHtml(payloadRuntime.gicatesisBaseUrl || "")}</code></div>
      `;
    }

    const formatDetailEl = getElement("n8n-format-detail");
    if (formatDetailEl) formatDetailEl.textContent = toPrettyJson(n8nSpec.formatDetail || {});
    const formatDefinitionEl = getElement("n8n-format-definition");
    if (formatDefinitionEl) {
      formatDefinitionEl.textContent = toPrettyJson(n8nSpec.formatDefinition || n8nSpec.formatDetail?.definition || {});
    }
    const promptTextEl = getElement("n8n-prompt-text");
    if (promptTextEl) {
      promptTextEl.textContent = String(
        n8nSpec.promptDetail?.text || n8nSpec.promptText || request.payload?.prompt?.text || "",
      );
    }
    const expectedResponseEl = getElement("n8n-expected-response");
    if (expectedResponseEl) expectedResponseEl.textContent = toPrettyJson(expected.bodyExample || {});
    const simOutputEl = getElement("n8n-sim-output");
    if (simOutputEl) simOutputEl.textContent = toPrettyJson(n8nSpec.simulationOutput || expected.bodyExample || {});

    const runOutput = n8nSpec.simulationOutput || {};
    const runId = runOutput.runId || "";
    const runStatus = getElement("sim-run-status");
    if (runStatus) {
      runStatus.textContent = runId
        ? `Resultado simulado disponible (runId: ${runId})`
        : "Aun no se ejecuto una simulacion manual.";
    }

    const exportButton = getElement("btn-export-guide");
    if (exportButton) exportButton.disabled = !n8nSpec.markdown;
  }

  async function runSimulation() {
    const project = getCurrentProject();
    if (!project?.id || isRunningSimulation) return;

    const button = getElement("btn-run-sim");
    const status = getElement("sim-run-status");
    isRunningSimulation = true;
    if (button) button.disabled = true;
    if (status) status.textContent = "Ejecutando simulacion...";

    try {
      const result = await apiSend(`/api/sim/n8n/run?projectId=${encodeURIComponent(project.id)}`, "POST");
      onSimulationOutput?.(result);
      if (n8nSpec) {
        n8nSpec.simulationOutput = {
          projectId: result.projectId,
          runId: result.runId,
          status: "success",
          aiResult: result.aiResult,
          artifacts: result.artifacts,
        };
      }
      render();
      refreshDashboard?.().catch(() => {});
      refreshHistory?.().catch(() => {});
    } catch (error) {
      const message = error?.message || "No se pudo ejecutar la simulacion.";
      if (status) status.textContent = message;
      alert(`Error: ${message}`);
    } finally {
      isRunningSimulation = false;
      if (button) button.disabled = false;
    }
  }

  async function copyPayload() {
    if (!n8nSpec) return;
    await copyText(toPrettyJson(n8nSpec.request?.payload || {}));
  }

  async function copyHeaders() {
    if (!n8nSpec) return;
    await copyText(toPrettyJson({
      toN8N: n8nSpec.request?.headers || {},
      toCallback: n8nSpec.expectedResponse?.headers || {},
    }));
  }

  async function copyWebhook() {
    if (!n8nSpec) return;
    await copyText(n8nSpec.request?.webhookUrl || "");
  }

  function exportGuide() {
    if (!n8nSpec || !n8nSpec.markdown) return;
    const projectId = n8nSpec.summary?.projectId || "project";
    downloadText(`n8n-guide-${projectId}.md`, n8nSpec.markdown);
  }

  return {
    reset,
    setSpec,
    getSpec,
    render,
    runSimulation,
    copyPayload,
    copyHeaders,
    copyWebhook,
    exportGuide,
  };
}
