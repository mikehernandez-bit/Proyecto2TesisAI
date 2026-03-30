/**
 * admin_prompts.js
 * Gestión de Paquetes Universitarios y Configuración Manual de Prompts.
 * Maneja: Navegación de paneles, Acordeones exclusivos y Apertura de Modal.
 */

document.addEventListener("DOMContentLoaded", () => {
    const gridAdmin = document.getElementById('prompts-grid-admin');
    const panels = document.querySelectorAll('.univ-panel');
    const modalManual = document.getElementById('modal-manual-config');

    // ==========================================
    // 1. NAVEGACIÓN: GRID -> PANELES
    // ==========================================
    const cardMap = [
        { id: 'card-unac', target: 'panel-unac' },
        { id: 'card-uni', target: 'panel-uni' },
        { id: 'card-uns', target: 'panel-uns' }
    ];

    cardMap.forEach(card => {
        const cardEl = document.getElementById(card.id);
        if (cardEl) {
            cardEl.addEventListener('click', () => {
                // Ocultar Grid y todos los paneles
                if (gridAdmin) gridAdmin.classList.add('hidden');
                panels.forEach(p => p.classList.add('hidden'));
                
                // Mostrar panel seleccionado
                const targetPanel = document.getElementById(card.target);
                if (targetPanel) {
                    targetPanel.classList.remove('hidden');
                    targetPanel.classList.add('fade-in');
                }
            });
        }
    });

    // ==========================================
    // 2. NAVEGACIÓN: VOLVER AL GRID
    // ==========================================
    document.querySelectorAll('.btn-back').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            panels.forEach(p => p.classList.add('hidden'));
            if (gridAdmin) {
                gridAdmin.classList.remove('hidden');
                gridAdmin.classList.add('fade-in');
            }
        });
    });

    // ==========================================
    // 3. LÓGICA DE ACORDEÓN EXCLUSIVO
    // ==========================================
    const accordionButtons = document.querySelectorAll('.btn-accordion');
    
    accordionButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const targetId = this.getAttribute('data-target');
            const targetContent = document.getElementById(targetId);
            const icon = this.querySelector('.accordion-icon');
            
            if (!targetContent) return;

            const isAlreadyOpen = !targetContent.classList.contains('hidden');

            // CERRAR TODOS los acordeones del panel actual
            const currentPanel = this.closest('.univ-panel');
            currentPanel.querySelectorAll('.btn-accordion').forEach(otherBtn => {
                const otherTarget = document.getElementById(otherBtn.getAttribute('data-target'));
                const otherIcon = otherBtn.querySelector('.accordion-icon');
                if (otherTarget) otherTarget.classList.add('hidden');
                if (otherIcon) otherIcon.classList.remove('rotate-180');
            });

            // Si estaba cerrado, lo abrimos
            if (!isAlreadyOpen) {
                targetContent.classList.remove('hidden');
                if (icon) icon.classList.add('rotate-180');
            }
        });
    });

    // ============================================================
    // 4. LÓGICA: MODAL DE CONFIGURACIÓN MANUAL (EDITAR)
    // ============================================================
    // Usamos delegación de eventos para mayor seguridad
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn-edit-pkg');
        if (!btn) return;

        e.preventDefault();
        e.stopPropagation();

        // --- A. Extraer información del contexto ---
        const activePanel = btn.closest('.univ-panel');
        let univName = "Universidad";
        let logoSrc = "";
        let templateName = "Configuración de Plantilla";
        let subcategory = "";

        if (activePanel) {
            // Nombre y Logo del Panel
            const headerTitle = activePanel.querySelector('h2');
            const headerImg = activePanel.querySelector('img');
            univName = headerTitle ? headerTitle.innerText : "Universidad";
            logoSrc = headerImg ? headerImg.src : "";
            
            // Título de la Tesis (h4)
            const accordionGroup = btn.closest('.group');
            const listRow = btn.closest('li');
            
            if (accordionGroup) {
                // Caso UNAC (Acordeones)
                const groupTitle = accordionGroup.querySelector('h4');
                templateName = groupTitle ? groupTitle.innerText : "Plantilla";
            } else if (listRow) {
                // Caso UNI (Lista simple)
                const rowTitle = listRow.querySelector('h4');
                templateName = rowTitle ? rowTitle.innerText : "Plantilla";
            }

            // Subcategoría (Cuali/Cuanti)
            const badge = btn.closest('li')?.querySelector('span');
            if (badge) subcategory = ` • ${badge.innerText}`;
        }

        // --- B. Inyectar datos en el Modal ---
        const modalLogo = document.getElementById('manual-logo-container');
        const modalTitle = document.getElementById('manual-title-display');
        const modalSubtitle = document.getElementById('manual-subtitle-display');

        if (modalLogo) {
            modalLogo.innerHTML = logoSrc ? `<img src="${logoSrc}" class="max-w-full max-h-full object-contain">` : '';
        }
        if (modalTitle) modalTitle.innerText = templateName;
        if (modalSubtitle) modalSubtitle.innerText = `${univName}${subcategory}`;

        // --- C. Mostrar el Modal ---
        if (modalManual) {
            modalManual.classList.remove('hidden');
            // Opcional: Hacer scroll al inicio del modal
            const modalContent = modalManual.querySelector('.bg-white');
            if (modalContent) modalContent.scrollTop = 0;
        }
    });
});