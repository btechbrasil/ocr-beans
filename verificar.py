#!/usr/bin/env python3
"""Diagnóstico do OCR Beans — roda ANTES/DEPOIS de instalar, sem executar nada.

Uso:  python3 verificar.py   (ou dentro do uv do plugin)

Verifica: Python, dependências (pymupdf/pytesseract/Pillow/mcp), Tesseract com
idioma 'por', e o motor em si (detecta o binário como o core faz). Ao final,
imprime o status e os comandos exatos para corrigir o que faltar.
"""
import importlib
import importlib.machinery
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

DEPS = [
    ("pymupdf", "PyMuPDF (extração de texto nativo)"),
    ("pytesseract", "pytesseract (ponte Python→Tesseract)"),
    ("PIL", "Pillow (imagens)"),
    ("mcp", "SDK MCP (servidor)"),
]

print("Diagnóstico OCR Beans")
print("=" * 60)
print(f"Python: {sys.version.split()[0]} ({sys.executable})")

ok = True
for modulo, desc in DEPS:
    try:
        importlib.import_module(modulo)
        print(f"  ✓ {desc}")
    except ImportError:
        ok = False
        print(f"  ✗ {desc} — FALTANDO")

# Tesseract: usa a própria descoberta do core (PATH/Program Files/TESSERACT_CMD)
tess_ok = False
try:
    loader = importlib.machinery.SourceFileLoader(
        "core_diag", os.path.join(HERE, "ocr_beans", "core.py"))
    spec = importlib.util.spec_from_loader("core_diag", loader)
    core = importlib.util.module_from_spec(spec)
    loader.exec_module(core)
    if core.TESSERACT_PATH:
        versao = "versão não lida"
        try:
            versao = core.pytesseract.get_tesseract_version()
        except Exception:
            pass
        print(f"  ✓ Tesseract: {core.TESSERACT_PATH} ({versao})")
        idiomas = core.idiomas_disponiveis()
        if "por" in idiomas:
            print(f"  ✓ idioma 'por' instalado ({', '.join(idiomas)})")
            tess_ok = True
        else:
            print(f"  ✗ idioma 'por' FALTANDO (instalados: {', '.join(idiomas) or 'nenhum'})")
    else:
        print("  ✗ Tesseract não encontrado em lugar nenhum")
except Exception as e:
    print(f"  ✗ motor não carregou: {e}")

print()
if ok and tess_ok:
    print("TUDO PRONTO ✅ — o conector funciona completo (nativo + OCR).")
elif ok and not tess_ok:
    print("PARCIAL ⚠️ — texto nativo funciona; páginas OCR precisam do Tesseract:")
    print("  Linux:   sudo apt install tesseract-ocr tesseract-ocr-por")
    print("  macOS:   brew install tesseract tesseract-lang")
    print("  Windows: instalador UB-Mannheim (marcar Portuguese)")
    print("           https://github.com/UB-Mannheim/tesseract/wiki")
    print("  (ou defina TESSERACT_CMD apontando para o binário)")
else:
    print("INSTALE AS DEPENDÊNCIAS (comando único, escolha um):")
    print("  uv run --no-project --with pymupdf --with pytesseract --with Pillow \\")
    print("     --with mcp python3 ocr_beans/mcp_server.py")
    print("  # ou:")
    print("  pip install --user pymupdf pytesseract Pillow mcp")
