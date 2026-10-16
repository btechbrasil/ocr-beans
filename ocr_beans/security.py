"""
OCR Beans - Validações de segurança.
Proteções contra path traversal, inputs maliciosos e abusos de recursos.
"""

import os
from pathlib import Path

from .core import IMAGE_EXTENSIONS

MAX_DPI = 400
MIN_DPI = 150
MAX_PDF_SIZE_MB = 200
MAX_IMAGE_SIZE_MB = 50
MAX_BATCH_FILES = 50
MAX_PAGES_PER_REQUEST = 100


def validate_path(path: str) -> str:
    """Resolve o path e bloqueia traversal e extensões inválidas."""
    resolved = Path(os.path.abspath(path)).resolve()

    if resolved.suffix.lower() != ".pdf":
        raise ValueError(f"Apenas arquivos .pdf são aceitos. Recebido: {resolved.suffix}")

    if not resolved.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    return str(resolved)


def validate_image_path(path: str) -> str:
    """Resolve o path e valida extensão de imagem + tamanho."""
    resolved = Path(os.path.abspath(path)).resolve()

    ext = resolved.suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise ValueError(
            f"Formato de imagem não suportado: {ext}. "
            f"Aceitos: {sorted(IMAGE_EXTENSIONS)}"
        )

    if not resolved.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    size_mb = os.path.getsize(resolved) / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        raise ValueError(
            f"Imagem muito grande: {size_mb:.0f}MB (máximo: {MAX_IMAGE_SIZE_MB}MB)"
        )

    return str(resolved)


def validate_directory(directory: str) -> str:
    """Resolve e valida que o diretório existe."""
    resolved = Path(os.path.abspath(directory)).resolve()

    if not resolved.is_dir():
        raise ValueError(f"Diretório não encontrado: {directory}")

    return str(resolved)


def validate_dpi(dpi: int) -> int:
    """Garante DPI dentro do range seguro."""
    if not isinstance(dpi, int) or dpi < MIN_DPI or dpi > MAX_DPI:
        raise ValueError(f"DPI deve ser entre {MIN_DPI} e {MAX_DPI}. Recebido: {dpi}")
    return dpi


def validate_pdf_size(path: str) -> None:
    """Rejeita PDFs maiores que o limite."""
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > MAX_PDF_SIZE_MB:
        raise ValueError(
            f"PDF muito grande: {size_mb:.0f}MB (máximo: {MAX_PDF_SIZE_MB}MB)"
        )


def validate_page_range(page_range: str) -> list[int]:
    """Valida e parseia range de páginas com limite de segurança."""
    pages = set()
    for part in page_range.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start, end = int(start_str), int(end_str)
            if end - start + 1 > MAX_PAGES_PER_REQUEST:
                raise ValueError(
                    f"Range muito grande: {part}. Máximo {MAX_PAGES_PER_REQUEST} páginas por request."
                )
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))

    if len(pages) > MAX_PAGES_PER_REQUEST:
        raise ValueError(
            f"Máximo {MAX_PAGES_PER_REQUEST} páginas por request. Solicitado: {len(pages)}"
        )

    if not pages:
        raise ValueError("Nenhuma página especificada.")

    return sorted(pages)


def validate_batch(directory: str) -> list[str]:
    """Lista PDFs no diretório com limite de segurança."""
    pdfs = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]
    if len(pdfs) > MAX_BATCH_FILES:
        raise ValueError(
            f"Muitos PDFs: {len(pdfs)} (máximo: {MAX_BATCH_FILES}). "
            f"Processe em lotes menores."
        )
    return sorted(pdfs)
