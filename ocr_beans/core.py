"""
OCR Beans - Core engine
Motor de OCR multiplataforma (Linux, Windows, macOS) para PDF e imagem,
com detecção automática de fontes corrompidas (comum em PDFs judiciais).
"""

import io
import logging
import os
import re
import shutil
import sys
import unicodedata

import pymupdf as fitz  # PyMuPDF (import moderno, sem warning no stdout)
import pytesseract
from PIL import Image

logger = logging.getLogger("ocr_beans")

# Formatos de imagem aceitos para OCR direto
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}


# ---------------------------------------------------------------------------
# Descoberta do Tesseract (Linux / Windows / macOS / PyInstaller)
# ---------------------------------------------------------------------------

def encontrar_tesseract() -> tuple[str | None, str | None]:
    """
    Procura o executável do Tesseract na seguinte ordem:
    1. Variável de ambiente TESSERACT_CMD
    2. Embutido no .exe/.app (PyInstaller _MEIPASS/tesseract/)
    3. Instalação padrão por sistema operacional
    4. PATH do sistema

    Retorna (caminho_exe, caminho_tessdata) ou (None, None).
    """
    # 1. Variável de ambiente
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd, os.environ.get("TESSDATA_PREFIX")

    # 2. Embutido (PyInstaller)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        exe_name = "tesseract.exe" if sys.platform == "win32" else "tesseract"
        bundled = os.path.join(meipass, "tesseract", exe_name)
        bundled_data = os.path.join(meipass, "tesseract", "tessdata")
        if os.path.isfile(bundled):
            return bundled, bundled_data

    # 3. Instalação padrão por SO
    candidatos: list[str] = []
    if sys.platform == "win32":
        candidatos += [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
        ]
    elif sys.platform == "darwin":
        candidatos += [
            "/opt/homebrew/bin/tesseract",   # Apple Silicon (brew)
            "/usr/local/bin/tesseract",      # Intel (brew)
            "/opt/local/bin/tesseract",      # MacPorts
        ]
    else:  # Linux e outros Unix
        candidatos += [
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/snap/bin/tesseract",
        ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c, None

    # 4. PATH do sistema
    found = shutil.which("tesseract")
    if found:
        return found, None

    return None, None


TESSERACT_PATH, TESSDATA_PATH = encontrar_tesseract()
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
if TESSDATA_PATH:
    os.environ.setdefault("TESSDATA_PREFIX", TESSDATA_PATH)

# Compat: TESSERACT_CMD legado (usado por Docker/ambientes que setam a env)
TESSERACT_CMD = TESSERACT_PATH or os.environ.get("TESSERACT_CMD", "")


def tesseract_disponivel() -> bool:
    """True se o Tesseract está acessível e responde."""
    if not TESSERACT_PATH:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def idiomas_disponiveis() -> list[str]:
    """Lista os idiomas instalados no Tesseract (ex.: ['eng', 'osd', 'por'])."""
    if not TESSERACT_PATH:
        return []
    try:
        return sorted(pytesseract.get_languages())
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Heurística de legibilidade (português jurídico)
# ---------------------------------------------------------------------------

def texto_legivel(text: str) -> bool:
    """
    Verifica se o texto extraído pelo PyMuPDF é legível ou se é lixo
    causado por fontes com encoding proprietário (comum em PDFs judiciais).
    """
    if len(text) < 30:
        return False

    controle = sum(
        1 for c in text if unicodedata.category(c).startswith("C") and c not in "\n\r\t"
    )
    if controle > len(text) * 0.05:
        return False

    letras = sum(1 for c in text if c.isalpha())
    espacos = sum(1 for c in text if c == " ")
    total = len(text)

    if total == 0:
        return False

    if letras / total < 0.40 or espacos / total < 0.05:
        return False

    palavras_comuns = [
        r"\bde\b", r"\bdo\b", r"\bda\b", r"\bdos\b", r"\bdas\b",
        r"\bque\b", r"\bem\b", r"\bno\b", r"\bna\b", r"\bnos\b",
        r"\bpor\b", r"\bcom\b", r"\bpara\b", r"\buma\b", r"\bse\b",
        r"\bnão\b", r"\bou\b", r"\bao\b", r"\bà\b", r"\be\b",
        r"\bser\b", r"\bfoi\b", r"\bsão\b", r"\best[aá]\b",
    ]
    texto_lower = text.lower()
    matches = sum(1 for p in palavras_comuns if re.search(p, texto_lower))

    return matches >= 2


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _ocr_image_obj(img: Image.Image, lang: str = "por", psm: int = 6) -> str:
    """Aplica Tesseract em um objeto PIL Image."""
    try:
        return pytesseract.image_to_string(img, lang=lang, config=f"--psm {psm}")
    except pytesseract.TesseractError:
        # Fallback: idioma default caso 'por' não esteja instalado
        if lang != "eng":
            return pytesseract.image_to_string(img, config=f"--psm {psm}")
        raise


def ocr_pagina(page, dpi: int = 300, lang: str = "por") -> str:
    """Renderiza a página do PDF como imagem e aplica OCR via Tesseract."""
    pix = page.get_pixmap(dpi=dpi)
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))
    try:
        return _ocr_image_obj(img, lang=lang)
    finally:
        img.close()


def ocr_imagem(image_path: str, lang: str = "por", psm: int = 6,
               pre_processar: bool = True) -> dict:
    """
    Aplica OCR diretamente em um arquivo de imagem.

    Args:
        image_path: Caminho da imagem (png, jpg, tif, bmp, webp, gif).
        lang: Idioma Tesseract (por, eng, por+eng...).
        psm: Page segmentation mode (3=auto, 6=bloco uniforme, 11=esparsa).
        pre_processar: Aplica upscale + grayscale para melhorar imagens pequenas.

    Returns:
        dict com keys: path, width, height, lang, content
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {image_path}")

    ext = os.path.splitext(image_path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise ValueError(f"Formato não suportado: {ext}. Use: {sorted(IMAGE_EXTENSIONS)}")

    img = Image.open(image_path)
    try:
        img.load()
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        width, height = img.size

        work = img
        if pre_processar:
            # Upscale de imagens pequenas — Tesseract rende melhor com mais pixels
            if max(width, height) < 1500:
                fator = 1500 / max(width, height)
                work = img.resize((int(width * fator), int(height * fator)),
                                  Image.LANCZOS)
            work = work.convert("L")

        text = _ocr_image_obj(work, lang=lang, psm=psm)
    finally:
        img.close()

    return {
        "path": image_path,
        "width": width,
        "height": height,
        "lang": lang,
        "content": text.strip(),
    }


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def processar_pdf(pdf_path: str, dpi: int = 300, lang: str = "por",
                  progress_callback=None) -> dict:
    """
    Processa um PDF e retorna resultado estruturado.

    Returns:
        dict com keys: path, total_pages, ocr_pages, text_pages, pages
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if total_pages == 0:
        doc.close()
        raise ValueError(f"PDF sem páginas: {pdf_path}")

    texto_teste = doc[0].get_text("text").strip()
    forcar_ocr = not texto_legivel(texto_teste)

    pages_result = []
    ocr_count = 0
    text_count = 0

    for page_num in range(total_pages):
        page = doc[page_num]

        if forcar_ocr:
            source, text = _ocr_safe(page, dpi, lang, page_num)
            if source == "OCR":
                ocr_count += 1
        else:
            text = page.get_text("text").strip()
            if texto_legivel(text):
                source = "TEXTO"
                text_count += 1
            else:
                source, text = _ocr_safe(page, dpi, lang, page_num)
                if source == "OCR":
                    ocr_count += 1

        pages_result.append({
            "number": page_num + 1,
            "source": source,
            "content": text,
        })

        if progress_callback:
            progress_callback(page_num + 1, total_pages)

    doc.close()

    return {
        "path": pdf_path,
        "total_pages": total_pages,
        "ocr_pages": ocr_count,
        "text_pages": text_count,
        "pages": pages_result,
    }


def _ocr_safe(page, dpi: int, lang: str, page_num: int) -> tuple[str, str]:
    """OCR de uma página com tratamento de erro. Retorna (source, text)."""
    try:
        return "OCR", ocr_pagina(page, dpi, lang)
    except Exception as e:
        logger.error("OCR falhou na página %d: %s", page_num + 1, e)
        return "ERRO", f"[ERRO NO OCR: {e}]"


def processar_paginas(pdf_path: str, page_range: str, dpi: int = 300,
                      lang: str = "por") -> dict:
    """
    Processa páginas específicas de um PDF.

    Args:
        pdf_path: Caminho absoluto do PDF.
        page_range: String tipo "1", "1-5", "1,3,7" ou "2-4,8".
        dpi: Resolução para OCR.

    Returns:
        dict com keys: path, total_pages, requested_pages, pages
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

    page_numbers = _parse_page_range(page_range)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    invalid = [p for p in page_numbers if p < 1 or p > total_pages]
    if invalid:
        doc.close()
        raise ValueError(
            f"Páginas inválidas: {invalid}. O PDF tem {total_pages} páginas."
        )

    texto_teste = doc[0].get_text("text").strip()
    forcar_ocr = not texto_legivel(texto_teste)

    pages_result = []

    for page_num in sorted(page_numbers):
        page = doc[page_num - 1]

        if forcar_ocr:
            source, text = _ocr_safe(page, dpi, lang, page_num - 1)
        else:
            text = page.get_text("text").strip()
            if texto_legivel(text):
                source = "TEXTO"
            else:
                source, text = _ocr_safe(page, dpi, lang, page_num - 1)

        pages_result.append({
            "number": page_num,
            "source": source,
            "content": text,
        })

    doc.close()

    return {
        "path": pdf_path,
        "total_pages": total_pages,
        "requested_pages": sorted(page_numbers),
        "pages": pages_result,
    }


def check_legibility(pdf_path: str) -> dict:
    """
    Diagnóstico rápido: verifica se o PDF tem fontes corrompidas.

    Returns:
        dict com keys: legible, total_pages, sample_text, reason
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if total_pages == 0:
        doc.close()
        return {
            "legible": False,
            "total_pages": 0,
            "sample_text": "",
            "reason": "PDF sem páginas",
        }

    texto_teste = doc[0].get_text("text").strip()
    doc.close()

    legible = texto_legivel(texto_teste)
    sample = texto_teste[:500] if texto_teste else ""

    if legible:
        reason = "Texto nativo legível — OCR não necessário"
    elif len(texto_teste) < 30:
        reason = "Texto insuficiente na primeira página (possível imagem ou scan)"
    else:
        reason = "Fonte com encoding proprietário detectada — OCR necessário"

    return {
        "legible": legible,
        "total_pages": total_pages,
        "sample_text": sample,
        "reason": reason,
    }


def _parse_page_range(page_range: str) -> list[int]:
    """Converte '1,3-5,8' em [1, 3, 4, 5, 8]."""
    pages = set()
    for part in page_range.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), int(end) + 1))
        else:
            pages.add(int(part))
    return sorted(pages)
