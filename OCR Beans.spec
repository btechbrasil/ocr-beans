# -*- mode: python ; coding: utf-8 -*-
# OCR Beans v2.0 - BeansTech 2026
# Build (na pasta do projeto, Windows):
#   python -m PyInstaller "OCR Beans.spec" --noconfirm
#
# Caminhos relativos ao diretorio deste .spec (SPECPATH) — funciona em
# qualquer lugar, sem hardcode de "c:/OCR Beans".

import os
import glob

PROJECT_DIR = SPECPATH  # definido pelo PyInstaller

# ---------------------------------------------------------------------------
# Tesseract embutido - coleta apenas os arquivos necessarios
# ---------------------------------------------------------------------------
TESSERACT_DIR = os.environ.get('TESSERACT_DIR', r'C:\Program Files\Tesseract-OCR')

# Executavel principal
tesseract_binaries = []
tesseract_exe = os.path.join(TESSERACT_DIR, 'tesseract.exe')
if os.path.isfile(tesseract_exe):
    tesseract_binaries.append((tesseract_exe, 'tesseract'))

    # Todas as DLLs necessarias
    for dll in glob.glob(os.path.join(TESSERACT_DIR, '*.dll')):
        tesseract_binaries.append((dll, 'tesseract'))

# Dados de idioma (apenas por/eng/osd — o minimo necessario)
tesseract_datas = []
for lang_file in ['por.traineddata', 'eng.traineddata', 'osd.traineddata']:
    src = os.path.join(TESSERACT_DIR, 'tessdata', lang_file)
    if os.path.isfile(src):
        tesseract_datas.append((src, 'tesseract/tessdata'))

# Configs do Tesseract (necessario para --psm etc.)
configs_dir = os.path.join(TESSERACT_DIR, 'tessdata', 'configs')
if os.path.isdir(configs_dir):
    for f in os.listdir(configs_dir):
        src = os.path.join(configs_dir, f)
        if os.path.isfile(src):
            tesseract_datas.append((src, 'tesseract/tessdata/configs'))

tessconfigs_dir = os.path.join(TESSERACT_DIR, 'tessdata', 'tessconfigs')
if os.path.isdir(tessconfigs_dir):
    for f in os.listdir(tessconfigs_dir):
        src = os.path.join(tessconfigs_dir, f)
        if os.path.isfile(src):
            tesseract_datas.append((src, 'tesseract/tessdata/tessconfigs'))

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(PROJECT_DIR, 'ocr_beans_app.py')],
    pathex=[PROJECT_DIR],
    binaries=tesseract_binaries,
    datas=tesseract_datas + [(os.path.join(PROJECT_DIR, 'ocr_beans.ico'), '.')],
    hiddenimports=[
        'fitz',
        'pymupdf',
        'PIL',
        'PIL.Image',
        'pytesseract',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'notebook',
        'jupyter',
        'IPython',
        # modulos da suite que NAO fazem parte do app desktop
        'fastapi',
        'uvicorn',
        'pdf2docx',
        'img2pdf',
        'pypdf',
        'mcp',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OCR Beans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_DIR, 'ocr_beans.ico'),
)
