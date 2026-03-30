/* ============================================================
   admin_index.js — Navegación e Índice con Sincronización Total
   ============================================================ */

window._modalCtx = { univ: '', tipo: '', subtipo: '', logo: '', title: '', subtitle: '' };

/**
 * Helper para generar el ID Único (Igual al que usa el modal)
 */
function generateChapterID(ctx, number) {
    const roman = (typeof ROMAN !== 'undefined') ? (ROMAN[number - 1] || number) : number;
    return `${ctx.univ}_${ctx.tipo}_${ctx.subtipo}_CAPITULO_${roman}`.toUpperCase().replace(/\s+/g, '_');
}

/**
 * PASO 1: Abre el Índice y carga el estado
 */
function openPromptIndex(btn) {
    const d = btn.dataset;
    window._modalCtx = { 
        univ: d.univ, tipo: d.tipo, subtipo: d.subtipo, 
        logo: d.logo, title: d.title, subtitle: d.subtitle 
    };

    document.getElementById('index-title').textContent = `${d.univ} - ${d.title}`;
    document.getElementById('index-subtitle').textContent = d.subtitle;

    document.querySelectorAll('.view-section').forEach(el => el.classList.add('hidden'));
    document.getElementById('view-prompt-index').classList.remove('hidden');

    loadIndexState();
}

/**
 * FUNCIÓN: Limpia el contenido (Prompts) en LocalStorage y Servidor
 */
async function clearChapterStorage(number) {
    if (!confirm(`¿Limpiar contenido del Capítulo ${number}? Se borrarán los prompts del archivo JSON.`)) return;

    const ctx = window._modalCtx;
    const autoID = generateChapterID(ctx, number);

    try {
        // 1. Borrar en el Servidor
        const res = await fetch(`/api/delete-prompt/${autoID}`, { method: 'DELETE' });
        const result = await res.json();

        if (result.status === "success") {
            // 2. Borrar en LocalStorage
            localStorage.removeItem(`STORAGE_${autoID}`);
            alert(`Contenido del Capítulo ${number} eliminado del servidor.`);
        } else {
            alert("El capítulo ya estaba vacío en el servidor.");
        }
    } catch (error) {
        console.error("Error al limpiar:", error);
        alert("Error de conexión con el servidor.");
    }
}

/**
 * FUNCIÓN: Elimina el bloque y REORDENA todo el JSON en el servidor
 */
async function removeChapter(number) {
    if (!confirm(`¿ELIMINAR bloque ${number}? Los capítulos siguientes se reenumerarán en el JSON.`)) return;

    const ctx = window._modalCtx;
    const container = document.getElementById('index-blocks-container');
    const totalBlocks = container.children.length;

    // 1. Borrar el elemento actual en el servidor
    const idToDelete = generateChapterID(ctx, number);
    await fetch(`/api/delete-prompt/${idToDelete}`, { method: 'DELETE' });
    localStorage.removeItem(`STORAGE_${idToDelete}`);

    // 2. REORDENAR CASCADA (Mover datos de arriba hacia abajo)
    // Si borro el 1, el 2 pasa a ser 1. Tenemos que cambiar el ID en el servidor.
    for (let i = number + 1; i <= totalBlocks; i++) {
        const oldID = generateChapterID(ctx, i);
        const newID = generateChapterID(ctx, i - 1);
        
        // Obtener datos del storage local
        let data = JSON.parse(localStorage.getItem(`STORAGE_${oldID}`));
        
        if (data) {
            data.id_unico = newID; // Actualizar el ID dentro del objeto
            
            // Guardar en el servidor con el nuevo ID (Esto hace un Update/Overwrite)
            await fetch('/api/save-prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            // Actualizar LocalStorage
            localStorage.setItem(`STORAGE_${newID}`, JSON.stringify(data));
            localStorage.removeItem(`STORAGE_${oldID}`);
            
            // Borrar el ID viejo del servidor
            await fetch(`/api/delete-prompt/${oldID}`, { method: 'DELETE' });
        }
    }

    // 3. Actualizar el Índice Visual
    const chapters = [];
    document.querySelectorAll('#index-blocks-container > div').forEach((block, index) => {
        if ((index + 1) === number) return; // Saltamos el borrado
        const input = block.querySelector('input[type="text"]');
        chapters.push({
            number: chapters.length + 1,
            title: input ? input.value : ''
        });
    });

    const storageKey = `INDEX_${ctx.univ}_${ctx.tipo}_${ctx.subtipo}`;
    localStorage.setItem(storageKey, JSON.stringify(chapters));

    loadIndexState(); // Refrescar vista
    alert("Reordenado completado con éxito.");
}

/**
 * Guarda el orden de los nombres en el índice
 */
function saveIndexState() {
    const ctx = window._modalCtx;
    const storageKey = `INDEX_${ctx.univ}_${ctx.tipo}_${ctx.subtipo}`;
    const chapters = [];
    document.querySelectorAll('#index-blocks-container > div').forEach((block, index) => {
        const input = block.querySelector('input[type="text"]');
        chapters.push({ number: index + 1, title: input ? input.value : '' });
    });
    localStorage.setItem(storageKey, JSON.stringify(chapters));
}

function loadIndexState() {
    const ctx = window._modalCtx;
    const storageKey = `INDEX_${ctx.univ}_${ctx.tipo}_${ctx.subtipo}`;
    const savedChapters = JSON.parse(localStorage.getItem(storageKey));
    const container = document.getElementById('index-blocks-container');
    container.innerHTML = ''; 

    if (savedChapters && savedChapters.length > 0) {
        savedChapters.forEach(ch => renderChapterCard(ch.number, ch.title));
    } else {
        renderChapterCard(1, "");
    }
}

function renderChapterCard(number, titleValue) {
    const container = document.getElementById('index-blocks-container');
    const roman = (typeof ROMAN !== 'undefined') ? (ROMAN[number - 1] || number) : number;

    const newBlock = document.createElement('div');
    newBlock.className = "bg-white border border-slate-200 rounded-2xl p-5 flex items-center justify-between cursor-pointer hover:border-blue-400 hover:shadow-md transition-all group fade-in";
    newBlock.onclick = function() { openManualModal(number); };

    newBlock.innerHTML = `
        <div class="flex items-center gap-4 w-full">
          <div class="w-12 h-12 rounded-xl bg-slate-50 text-slate-400 flex items-center justify-center font-black text-lg group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
            ${number}
          </div>
          <div class="flex-1">
            <h4 class="text-[10px] font-black text-blue-500 uppercase tracking-widest">Capítulo ${roman}</h4>
            <input type="text" 
              placeholder="Ej: Introducción y Planteamiento..." 
              value="${titleValue}"
              onclick="event.stopPropagation()" 
              oninput="saveIndexState()"
              class="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-slate-800 placeholder:text-slate-400 focus:bg-white focus:border-blue-400 focus:ring-4 focus:ring-blue-50 transition-all outline-none"
            >
          </div>
          
          <div class="flex items-center gap-2 ml-3">
             <button onclick="event.stopPropagation(); clearChapterStorage(${number})" 
                class="w-9 h-9 flex items-center justify-center rounded-lg bg-slate-50 text-slate-400 hover:bg-amber-500 hover:text-white transition-all border border-slate-100"
                title="Limpiar contenido">
                <i class="fa-solid fa-eraser text-xs"></i>
             </button>

             <button onclick="event.stopPropagation(); removeChapter(${number})" 
                class="w-9 h-9 flex items-center justify-center rounded-lg bg-red-50 text-red-400 hover:bg-red-500 hover:text-white transition-all border border-red-100"
                title="Eliminar este bloque">
                <i class="fa-solid fa-xmark text-sm"></i>
             </button>

             <i class="fa-solid fa-chevron-right text-slate-300 group-hover:text-blue-500 transition-colors ml-1"></i>
          </div>
        </div>
    `;
    container.appendChild(newBlock);
}

function createNewChapter() {
    const container = document.getElementById('index-blocks-container');
    const nextNumber = container.children.length + 1;
    renderChapterCard(nextNumber, "");
    saveIndexState();
}

function openManualModal(chapterNumber = 1) {
    const ctx = window._modalCtx;
    const blocks = document.querySelectorAll('#index-blocks-container > div');
    const targetBlock = blocks[chapterNumber - 1];
    const input = targetBlock ? targetBlock.querySelector('input[type="text"]') : null;
    const chapterTitle = input ? input.value.trim() : '';

    const autoID = generateChapterID(ctx, chapterNumber);

    const idField = document.getElementById('manual-prompt-name');
    if (idField) {
        idField.value = autoID;
        idField.readOnly = true;
        idField.classList.add('bg-slate-800', 'text-slate-400', 'cursor-not-allowed');
    }

    const img = document.getElementById('manual-logo-img');
    if (ctx.logo && img) { img.src = ctx.logo; img.classList.remove('hidden'); }
    document.getElementById('manual-title-display').textContent = ctx.title;
    document.getElementById('manual-subtitle-display').textContent = ctx.subtitle;

    if (typeof window.resetPromptBlocks === 'function') {
        window.resetPromptBlocks(chapterNumber, chapterTitle);
    }
    document.getElementById('modal-manual-config').classList.remove('hidden');
}

function closeManualModal() {
    document.getElementById('modal-manual-config').classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
    document.body.addEventListener('click', e => {
        const btn = e.target.closest('.btn-edit-pkg');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            openPromptIndex(btn);
        }
    });
});

window.openPromptIndex = openPromptIndex;
window.openManualModal = openManualModal;
window.closeManualModal = closeManualModal;
window.createNewChapter = createNewChapter;
window.saveIndexState = saveIndexState;
window.clearChapterStorage = clearChapterStorage;
window.removeChapter = removeChapter;