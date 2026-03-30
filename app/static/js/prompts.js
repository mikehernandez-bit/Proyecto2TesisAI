/* ============================================================
   prompts.js — Lógica con Variables Globales y Locales
   ============================================================ */

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

let _currentChapterTitle = '';
let _currentChapterNumber = 1;

/**
 * Prepara el modal y carga los datos existentes
 */
function resetPromptBlocks(chapterNumber = 1, chapterTitle = '') {
    const container = document.getElementById('prompts-container');
    if (!container) return;

    container.innerHTML = ''; 
    _currentChapterTitle = chapterTitle;
    _currentChapterNumber = chapterNumber;

    const promptID = document.getElementById('manual-prompt-name').value;
    const storageKey = `STORAGE_${promptID}`;
    const savedData = JSON.parse(localStorage.getItem(storageKey));

    if (savedData && savedData.prompts && savedData.prompts.length > 0) {
        savedData.prompts.forEach((p) => {
            addPromptBlock(
                chapterNumber, 
                p.capitulo_nombre, 
                true, 
                p.titulo_cabecera, 
                p.instrucciones_ia,
                p.variables_locales // Carga sus variables específicas
            );
        });
    } else {
        addPromptBlock(chapterNumber, chapterTitle, true);
    }
}

/**
 * Crea un bloque de prompt. 
 * 'variable_dependiente' siempre se incluye por defecto.
 */
function addPromptBlock(chapterIndex = null, chapterTitle = '', isLocked = false, initialHeader = '', initialContent = '', initialVars = []) {
    const container = document.getElementById('prompts-container');
    const n = container.querySelectorAll('.prompt-block').length + 1;
    
    const finalTitle = (n === 1) ? chapterTitle : _currentChapterTitle;
    const finalChapterNum = (n === 1) ? chapterIndex : _currentChapterNumber;
    const roman = ROMAN[finalChapterNum - 1] || finalChapterNum;

    const block = document.createElement('div');
    block.className = 'prompt-block bg-white rounded-[2.5rem] border border-slate-200 shadow-sm overflow-hidden mb-8 fade-in';
    block.dataset.index = n;

    block.innerHTML = `
        <div class="p-6 flex gap-4 items-center bg-slate-50 border-b border-slate-100">
            <div class="px-5 py-2.5 bg-emerald-500 text-white rounded-2xl flex items-center gap-3 shadow-md shrink-0">
                <i class="fa-solid fa-bolt text-xs"></i>
                <span class="text-xs font-black uppercase tracking-widest">Prompt ${n}</span>
            </div>

            <div class="flex items-center rounded-2xl border border-slate-200 overflow-hidden flex-[1.5] bg-slate-100 text-slate-500 shadow-inner">
                <div class="bg-slate-200 px-4 py-2.5 text-[10px] font-black uppercase border-r border-slate-300 shrink-0">Capítulo ${roman}</div>
                <input type="text" value="${finalTitle}" readonly class="w-full px-4 py-2 bg-transparent text-sm font-bold outline-none cursor-not-allowed">
            </div>

            <div class="flex items-center bg-white rounded-2xl border border-slate-200 overflow-hidden flex-1 shadow-sm focus-within:border-blue-400 transition-all">
                <div class="bg-slate-100 px-4 py-2.5 text-[10px] font-black text-slate-400 uppercase border-r border-slate-200 shrink-0">Cabecera ${n}</div>
                <input type="text" placeholder="Ej: Realidad Problemática..." value="${initialHeader}" class="w-full px-4 py-2 bg-transparent text-sm font-bold text-slate-700 outline-none">
            </div>

            ${n > 1 ? `
            <button onclick="this.closest('.prompt-block').remove()" class="w-11 h-11 flex items-center justify-center rounded-2xl bg-red-50 text-red-400 hover:bg-red-500 hover:text-white transition-all">
                <i class="fa-solid fa-trash-can"></i>
            </button>` : ''}
        </div>

        <div class="p-8 space-y-6">
            <div class="space-y-3">
                <label class="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Instrucciones para la IA:</label>
                <textarea class="w-full h-[240px] p-7 bg-slate-900 text-blue-50 border-2 border-slate-800 rounded-[2rem] text-sm font-mono leading-relaxed focus:border-blue-500 outline-none shadow-2xl resize-none"
                    placeholder="Describe cómo debe actuar la IA en esta sección...">${initialContent}</textarea>
            </div>

            <div class="bg-slate-50/80 p-6 rounded-[2rem] border border-slate-100">
                <div class="flex items-center gap-2 mb-4">
                    <i class="fa-solid fa-tags text-blue-500 text-sm"></i>
                    <label class="text-[11px] font-black text-slate-600 uppercase tracking-widest">Variables de este bloque:</label>
                </div>
                
                <div class="local-vars-tags flex flex-wrap gap-2 mb-4">
                    <span class="px-4 py-2 bg-blue-600 text-white rounded-xl text-[10px] font-black shadow-md flex items-center gap-2 select-none border border-blue-700">
                        <i class="fa-solid fa-globe text-[9px]"></i> variable_dependiente
                    </span>
                    </div>

                <div class="flex gap-2">
                    <input type="text" placeholder="Añadir variable específica (ej: poblacion, muestra...)" 
                        class="local-var-input flex-1 px-5 py-3 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:border-blue-400 transition-all shadow-sm">
                    <button onclick="addVariableToBlock(this)" class="px-5 bg-slate-900 text-white rounded-2xl hover:bg-blue-600 transition-all shadow-lg">
                        <i class="fa-solid fa-plus"></i>
                    </button>
                </div>
            </div>
        </div>
    `;

    container.appendChild(block);

    // Cargar variables si vienen de la base de datos
    if (initialVars && initialVars.length > 0) {
        const localTagsContainer = block.querySelector('.local-vars-tags');
        initialVars.forEach(v => {
            if (v !== 'variable_dependiente') {
                _createLocalTag(localTagsContainer, v);
            }
        });
    }

    if(n > 1) block.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/**
 * Añade una variable al bloque específico donde se pulsó el botón
 */
function addVariableToBlock(btn) {
    const parentBlock = btn.closest('.prompt-block');
    const input = parentBlock.querySelector('.local-var-input');
    const tagsContainer = parentBlock.querySelector('.local-vars-tags');
    
    const val = input.value.trim().replace(/\s+/g, '_').toLowerCase();
    if (!val || val === 'variable_dependiente') { input.value = ''; return; }

    // Evitar duplicados locales
    const exists = Array.from(tagsContainer.querySelectorAll('input')).some(inp => inp.value === val);
    if (exists) { input.value = ''; return; }

    _createLocalTag(tagsContainer, val);
    input.value = '';
    input.focus();
}

/**
 * Crea visualmente el tag de la variable
 */
function _createLocalTag(container, val) {
    const tag = document.createElement('span');
    tag.className = 'var-tag px-4 py-2 bg-white text-slate-700 rounded-xl text-[10px] font-bold border border-slate-200 flex items-center gap-2 shadow-sm fade-in';

    tag.innerHTML = `
        <input type="text" value="${val}" class="bg-transparent outline-none border-none p-0 m-0 font-bold text-slate-800" style="width: ${Math.max(60, val.length * 8)}px">
        <i class="fa-solid fa-circle-xmark opacity-40 cursor-pointer hover:text-red-500 transition text-[12px]" onclick="this.parentElement.remove()"></i>
    `;
    container.appendChild(tag);
}

/**
 * Recolecta todo y guarda en el Servidor + LocalStorage
 */
async function savePackage() {
    const promptID = document.getElementById('manual-prompt-name').value;
    if (!promptID) return;

    const bloques = [];
    document.querySelectorAll('#prompts-container .prompt-block').forEach((block, i) => {
        const inputs = block.querySelectorAll('input[type="text"]');
        const textarea = block.querySelector('textarea');
        
        // Recolectar variables: La global + las que el usuario añadió en este bloque
        const varsDeEsteBloque = ['variable_dependiente'];
        block.querySelectorAll('.local-vars-tags .var-tag input').forEach(inp => {
            const v = inp.value.trim().toLowerCase();
            if (v) varsDeEsteBloque.push(v);
        });

        bloques.push({
            numero_prompt: i + 1,
            capitulo_nombre: inputs[0]?.value.trim(),
            titulo_cabecera: inputs[1]?.value.trim(),
            instrucciones_ia: textarea?.value.trim(),
            variables_locales: varsDeEsteBloque // Guardado independiente
        });
    });

    const ctx = window._modalCtx || {};
    const payload = {
        id_unico: promptID,
        universidad: ctx.univ,
        metodologia: ctx.tipo,
        categoria: ctx.subtipo,
        prompts: bloques,
        config_ia: { modelo: 'GPT-4o (Omni)', temperatura: 0.7, max_tokens: 4096 }
    };

    try {
        const res = await fetch('/api/save-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error();

        localStorage.setItem(`STORAGE_${promptID}`, JSON.stringify(payload));
        alert('Configuración guardada exitosamente.');
        window.closeManualModal();
    } catch (e) {
        alert("Error al conectar con el servidor.");
    }
}

// Exponer funciones para los botones onclick del HTML dinámico
window.resetPromptBlocks = resetPromptBlocks;
window.addPromptBlock = addPromptBlock;
window.addVariableToBlock = addVariableToBlock;
window.savePackage = savePackage;