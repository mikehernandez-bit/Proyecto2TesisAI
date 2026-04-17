function renderLogoHtml({ escapeHtml, gicatesisOnline, universityCode }) {
  if (!gicatesisOnline) {
    return `<span class="text-blue-700 font-bold">${escapeHtml(String(universityCode).toUpperCase())}</span>`;
  }

  const logoUrl = `/api/assets/logos/${universityCode}.png`;
  return `<img src="${logoUrl}" alt="${escapeHtml(universityCode)}" class="w-full h-full object-contain" data-logo-fallback="${escapeHtml(String(universityCode).toUpperCase())}">`;
}

function syncSelectedFormatCard({ getSelectedFormat }) {
  document.querySelectorAll(".format-card").forEach((card) => {
    const isSelected = String(card.dataset.formatId || "") === String(getSelectedFormat()?.id || "");
    card.classList.remove("border-blue-500", "bg-blue-50");
    if (isSelected) {
      card.classList.add("border-blue-500", "bg-blue-50");
    }
  });
}

function renderFormats({
  items,
  getElement,
  escapeHtml,
  getCategoryLabel,
  getSelectedFormat,
  gicatesisOnline,
  selectFormat,
}) {
  const uniSel = getElement("filter-university");
  const catSel = getElement("filter-career");
  const selectedUni = uniSel?.value || "";
  const selectedCategory = catSel?.value || "";
  const filtered = items.filter((item) => {
    const matchesUni = !selectedUni || item.university === selectedUni;
    const matchesCategory = !selectedCategory || getCategoryLabel(item.category) === selectedCategory;
    return matchesUni && matchesCategory;
  });

  const grid = getElement("formats-grid");
  if (!grid) return;
  grid.innerHTML = "";

  if (!filtered.length) {
    grid.innerHTML = '<div class="text-sm text-gray-500">No hay formatos para esos filtros.</div>';
    return;
  }

  filtered.forEach((format) => {
    const card = document.createElement("div");
    card.className = "format-card border-2 border-gray-100 hover:border-blue-400 p-4 rounded-lg cursor-pointer transition group relative bg-white";
    card.dataset.formatId = String(format.id || "");
    card.addEventListener("click", () => {
      selectFormat(format, card);
    });

    const docType = format.documentType ? ` (${format.documentType})` : "";
    const universityCode = String(format.university || "generic").toLowerCase();
    const logoHtml = renderLogoHtml({
      escapeHtml,
      gicatesisOnline,
      universityCode,
    });

    card.innerHTML = `
      <div class="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-blue-500">
        <i class="fa-solid fa-circle-check fa-lg"></i>
      </div>
      <div class="flex items-center gap-4 mb-3">
        <div class="w-12 h-12 shrink-0 flex items-center justify-center p-1 border rounded bg-gray-50">
          ${logoHtml}
        </div>
        <div>
          <div class="font-bold text-sm text-slate-800 leading-tight">${escapeHtml(format.title || format.name || format.id)}</div>
          <div class="text-xs text-gray-400 mt-1">v${escapeHtml(String(format.version || "").substring(0, 8))}</div>
        </div>
      </div>
      <div class="mt-2 text-xs text-slate-500 bg-slate-50 p-2 rounded flex items-center gap-2">
        <i class="fa-solid fa-tag text-blue-400"></i>
        <span>${escapeHtml(getCategoryLabel(format.category))}${escapeHtml(docType)}</span>
      </div>
    `;

    const logo = card.querySelector("img[data-logo-fallback]");
    if (logo) {
      logo.addEventListener("error", () => {
        const fallback = document.createElement("span");
        fallback.className = "text-blue-700 font-bold";
        fallback.textContent = String(logo.getAttribute("data-logo-fallback") || "").trim();
        logo.replaceWith(fallback);
      }, { once: true });
    }

    grid.appendChild(card);
  });

  syncSelectedFormatCard({ getSelectedFormat });
}

export function createFormatCatalogController({
  fetchImpl = fetch,
  getElement,
  parseError,
  escapeHtml,
  getSelectedFormat,
  setSelectedFormat,
  getCategoryLabel,
  setFormatsCache,
  setGicatesisOnline,
  onFormatSelected,
}) {
  let renderCurrentFormats = () => {};

  function rerenderFormats() {
    renderCurrentFormats();
  }

  function selectFormat(formatObj, cardEl) {
    document.querySelectorAll(".format-card").forEach((card) => {
      card.classList.remove("border-blue-500", "bg-blue-50");
    });

    setSelectedFormat(formatObj);
    if (cardEl) {
      cardEl.classList.remove("border-gray-100");
      cardEl.classList.add("border-blue-500", "bg-blue-50");
    } else {
      syncSelectedFormatCard({ getSelectedFormat });
    }

    const nextButton = getElement("btn-step1-next");
    if (nextButton) nextButton.disabled = false;
    Promise.resolve(onFormatSelected?.(formatObj)).catch(console.error);
  }

  async function loadFormats() {
    const raw = await fetchImpl("/api/formats");
    if (!raw.ok) throw new Error(await parseError(raw));

    const gicatesisOnline = raw.headers.get("X-Upstream-Online") !== "false";
    setGicatesisOnline(gicatesisOnline);

    const response = await raw.json();
    const items = response.formats || [];
    setFormatsCache(items);

    const banner = getElement("gicatesis-offline-banner");
    if (banner) {
      banner.classList.toggle("hidden", gicatesisOnline);
    }

    const universities = Array.from(new Set(items.map((item) => item.university))).filter(Boolean).sort();
    const categories = Array.from(new Set(items.map((item) => getCategoryLabel(item.category)))).filter(Boolean).sort();
    const uniSel = getElement("filter-university");
    const catSel = getElement("filter-career");

    if (uniSel) {
      uniSel.innerHTML = '<option value="">Todas las universidades</option>'
        + universities.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(String(item).toUpperCase())}</option>`).join("");
      if (uniSel.dataset.catalogBound !== "true") {
        uniSel.addEventListener("change", rerenderFormats);
        uniSel.dataset.catalogBound = "true";
      }
    }

    if (catSel) {
      catSel.innerHTML = '<option value="">Tipo de documento</option>'
        + categories.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("");
      if (catSel.dataset.catalogBound !== "true") {
        catSel.addEventListener("change", rerenderFormats);
        catSel.dataset.catalogBound = "true";
      }
    }

    renderCurrentFormats = () => renderFormats({
        items,
        getElement,
        escapeHtml,
        getCategoryLabel,
        getSelectedFormat,
        gicatesisOnline,
        selectFormat,
      });

    renderCurrentFormats();
  }

  return {
    loadFormats,
    selectFormat,
    syncSelectedFormatCard() {
      syncSelectedFormatCard({ getSelectedFormat });
    },
  };
}
