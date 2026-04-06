import subprocess
import re
import sys

skills_to_download = [
    'frontend-design', 'vanilla-web', 'tailwind-patterns', 'accessibility', 'seo', 'spa-routes',
    'playwright-best-practices', 'e2e-testing-patterns', 'qa-test-planner',
    'nodejs-backend-patterns', 'nodejs-best-practices', 'fastapi', 'fastapi-expert', 'pydantic',
    'python', 'python-testing', 'python-pytest-patterns', 'python-code-quality',
    'architecture', 'modern-web-app-architecture', 'code-review', 'lsp-code-analysis', 'git-workflow',
    'docs-writer', 'technical-writing', 'code-documentation', 'documentation-templates',
    'find-skills', 'plugin-creator', 'skill-creator', 'skill-installer', 'spreadsheet', 'document-docx', 'mermaid-diagrams', 'uml',
    'notion-knowledge-capture', 'notion-research-documentation', 'notion-spec-to-implementation'
]

print("Iniciando descarga masiva desde skills.sh...")
for skill in skills_to_download:
    print(f"\nBuscando '{skill}' en skills.sh...")
    try:
        # Busqueda silenciosa (-y para autoinstalar npx si hace falta)
        # Se añade encoding='utf-8' para no fallar con los caracteres ASCII especiales en consola Windows.
        result = subprocess.run(
            ['npx', '-y', 'skills', 'search', skill], 
            capture_output=True, text=True, shell=True, encoding='utf-8', errors='ignore'
        )
        
        # Parseando la primera coincidencia que luzca como owner/repo@skill
        matches = re.findall(r'(\S+/\S+@\S+)\s+\d+', result.stdout)
        
        if matches:
            best_match = matches[0]
            print(f"  Encontrado: {best_match}. Descargando...")
            # Descargar automaticamente
            subprocess.run(['npx', '-y', 'skills', 'add', best_match.split('@')[0]], shell=True, encoding='utf-8')
            print(f"  ✔ {skill} ({best_match}) instalado con exito.")
        else:
            print(f"  ✗ No se encontro un owner/repo valido para '{skill}'.")
    except Exception as e:
        print(f"  Error procesando {skill}: {e}")

print("\nTerminado. Todas las skills disponibles fueron descargadas del catalogo de skills.sh (si existian).")
