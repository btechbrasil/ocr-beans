"""
OCR Beans - Conversões e utilitários de PDF/imagem.
Todas as funções operam em arquivos locais e retornam o caminho do resultado.

Segurança: todo acesso a disco passa por _open_checked() / _resolve_input() /
_resolve_output(), que rejeitam '..' e normalizam o caminho antes do I/O.
Chamadores (CLI/API) devem passar caminhos absolutos ou relativos simples.
"""

import io
import os
import zipfile

import pymupdf as fitz  # PyMuPDF (import moderno, sem warning no stdout)
import img2pdf
from PIL import Image
from pypdf import PdfReader, PdfWriter

from .core import IMAGE_EXTENSIONS

# ---------------------------------------------------------------------------
# Validação de caminhos
# ---------------------------------------------------------------------------

def _resolve_input(path: str, exts: set[str] | None = None) -> str:
    """Valida entrada: sem traversal, arquivo existe, extensão permitida."""
    if not path or "\x00" in path or ".." in path.replace("\\", "/").split("/"):
        raise ValueError(f"Caminho de entrada inválido: {path!r}")
    resolved = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if exts:
        ext = os.path.splitext(resolved)[1].lower()
        if ext not in exts:
            raise ValueError(f"Formato inválido: {ext}. Esperado: {sorted(exts)}")
    return resolved


def _resolve_output(path: str) -> str:
    """Valida saída: sem traversal e diretório pai existente."""
    if not path or "\x00" in path or ".." in path.replace("\\", "/").split("/"):
        raise ValueError(f"Caminho de saída inválido: {path!r}")
    resolved = os.path.realpath(os.path.expanduser(path))
    parent = os.path.dirname(resolved)
    if not parent or not os.path.isdir(parent):
        raise ValueError(f"Diretório de saída não existe: {parent or path}")
    return resolved


def _open_checked(path: str, mode: str):
    """
    Único ponto do módulo que abre arquivos. Revalida tudo inline:
    rejeita '..'/nulos, normaliza com realpath, exige arquivo existente
    para leitura e diretório pai existente para escrita.
    """
    if not path or "\x00" in path or ".." in path.replace("\\", "/").split("/"):
        raise ValueError(f"Caminho inválido: {path!r}")
    resolved = os.path.realpath(os.path.expanduser(path))
    if "r" in mode:
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    else:
        parent = os.path.dirname(resolved)
        if not parent or not os.path.isdir(parent):
            raise ValueError(f"Diretório de saída não existe: {parent or path}")
    return open(resolved, mode)


def _require_pdf(path: str) -> str:
    return _resolve_input(path, {".pdf"})


# ---------------------------------------------------------------------------
# Imagens -> PDF
# ---------------------------------------------------------------------------

def imagens_para_pdf(image_paths: list[str], output_path: str) -> str:
    """Junta várias imagens (png/jpg/tif/bmp/webp) em um único PDF."""
    if not image_paths:
        raise ValueError("Nenhuma imagem informada.")
    out = _resolve_output(output_path)

    # img2pdf não aceita RGBA/palette: normaliza para RGB em memória
    buffers: list[bytes] = []
    for p in image_paths:
        src = _resolve_input(p, IMAGE_EXTENSIONS)
        img = Image.open(src)
        try:
            img.load()
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buffers.append(buf.getvalue())
            else:
                with _open_checked(src, "rb") as f:
                    buffers.append(f.read())
        finally:
            img.close()

    with _open_checked(out, "wb") as f:
        f.write(img2pdf.convert(buffers))
    return out


# ---------------------------------------------------------------------------
# PDF -> Imagens (zip com PNGs)
# ---------------------------------------------------------------------------

def pdf_para_imagens(pdf_path: str, output_zip: str, dpi: int = 200,
                     fmt: str = "png", pages: list[int] | None = None) -> str:
    """
    Renderiza páginas do PDF como imagens e compacta em um .zip.
    pages: lista 1-based; None = todas.
    """
    src = _require_pdf(pdf_path)
    out = _resolve_output(output_zip)
    if fmt not in ("png", "jpg", "jpeg"):
        raise ValueError("fmt deve ser 'png' ou 'jpg'")

    doc = fitz.open(src)
    try:
        total = len(doc)
        alvo = pages if pages else list(range(1, total + 1))
        invalidas = [p for p in alvo if p < 1 or p > total]
        if invalidas:
            raise ValueError(f"Páginas inválidas: {invalidas}. O PDF tem {total} páginas.")

        base = os.path.splitext(os.path.basename(src))[0]
        with _open_checked(out, "wb") as raw:
            with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zf:
                for pnum in alvo:
                    pix = doc[pnum - 1].get_pixmap(dpi=dpi)
                    ext = "jpg" if fmt in ("jpg", "jpeg") else "png"
                    zf.writestr(f"{base}_pag{pnum:03d}.{ext}", pix.tobytes(ext))
    finally:
        doc.close()
    return out


# ---------------------------------------------------------------------------
# Merge / Split
# ---------------------------------------------------------------------------

def juntar_pdfs(pdf_paths: list[str], output_path: str) -> str:
    """Concatena vários PDFs em um só, na ordem informada."""
    if len(pdf_paths) < 2:
        raise ValueError("Informe ao menos 2 PDFs para juntar.")
    fontes = [_require_pdf(p) for p in pdf_paths]
    out = _resolve_output(output_path)

    writer = PdfWriter()
    for src in fontes:
        for page in PdfReader(src).pages:
            writer.add_page(page)
    with _open_checked(out, "wb") as f:
        writer.write(f)
    return out


def dividir_pdf(pdf_path: str, output_path: str, pages: list[int]) -> str:
    """Extrai páginas (1-based) de um PDF para um novo PDF."""
    src = _require_pdf(pdf_path)
    out = _resolve_output(output_path)
    if not pages:
        raise ValueError("Nenhuma página informada.")

    reader = PdfReader(src)
    total = len(reader.pages)
    invalidas = [p for p in pages if p < 1 or p > total]
    if invalidas:
        raise ValueError(f"Páginas inválidas: {invalidas}. O PDF tem {total} páginas.")

    writer = PdfWriter()
    for p in pages:
        writer.add_page(reader.pages[p - 1])
    with _open_checked(out, "wb") as f:
        writer.write(f)
    return out


# ---------------------------------------------------------------------------
# Compressão
# ---------------------------------------------------------------------------

def comprimir_pdf(pdf_path: str, output_path: str,
                  qualidade_imagem: int = 60, dpi_imagem: int = 150) -> dict:
    """
    Comprime um PDF: regrava streams com deflate e reduz imagens embutidas.

    Returns:
        dict com keys: output, tamanho_original, tamanho_final, reducao_pct
    """
    src = _require_pdf(pdf_path)
    out = _resolve_output(output_path)
    if not 10 <= qualidade_imagem <= 95:
        raise ValueError("qualidade_imagem deve ser entre 10 e 95.")

    original = os.path.getsize(src)
    doc = fitz.open(src)
    try:
        # Recomprime imagens raster embutidas acima de um tamanho mínimo
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base = doc.extract_image(xref)
                    img = Image.open(io.BytesIO(base["image"]))
                    if img.width < 200 or img.height < 200:
                        continue  # ícones/logos pequenos não valem a recompressão
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
                    # Downscale para o DPI alvo
                    escala = dpi_imagem / 300.0
                    if escala < 1.0 and img.width * escala >= 200:
                        img = img.resize(
                            (max(1, int(img.width * escala)),
                             max(1, int(img.height * escala))),
                            Image.LANCZOS,
                        )
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=qualidade_imagem, optimize=True)
                    page.replace_image(xref, stream=buf.getvalue())
                except Exception:
                    continue  # imagem não recompressível — mantém a original

        doc.save(out, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    final = os.path.getsize(out)
    return {
        "output": out,
        "tamanho_original": original,
        "tamanho_final": final,
        "reducao_pct": round((1 - final / original) * 100, 1) if original else 0.0,
    }


# ---------------------------------------------------------------------------
# Rotação
# ---------------------------------------------------------------------------

def rotacionar_pdf(pdf_path: str, output_path: str, graus: int = 90,
                   pages: list[int] | None = None) -> str:
    """Rotaciona páginas (90/180/270 graus). pages: 1-based; None = todas."""
    src = _require_pdf(pdf_path)
    out = _resolve_output(output_path)
    if graus not in (90, 180, 270):
        raise ValueError("graus deve ser 90, 180 ou 270.")

    doc = fitz.open(src)
    try:
        total = len(doc)
        alvo = pages if pages else list(range(1, total + 1))
        for pnum in alvo:
            if pnum < 1 or pnum > total:
                raise ValueError(f"Página inválida: {pnum}. O PDF tem {total} páginas.")
            page = doc[pnum - 1]
            page.set_rotation((page.rotation + graus) % 360)
        doc.save(out, garbage=4, deflate=True)
    finally:
        doc.close()
    return out


# ---------------------------------------------------------------------------
# Marca d'água de texto
# ---------------------------------------------------------------------------

def adicionar_marca_dagua(pdf_path: str, output_path: str, texto: str,
                          opacidade: float = 0.15, tamanho: int = 48,
                          angulo: int = 45) -> str:
    """Aplica marca d'água de texto diagonal em todas as páginas."""
    src = _require_pdf(pdf_path)
    out = _resolve_output(output_path)
    if not texto.strip():
        raise ValueError("Texto da marca d'água não pode ser vazio.")
    if not 0.02 <= opacidade <= 1.0:
        raise ValueError("opacidade deve ser entre 0.02 e 1.0.")

    doc = fitz.open(src)
    try:
        for page in doc:
            rect = page.rect
            ponto = fitz.Point(rect.width * 0.15, rect.height * 0.55)
            # morph permite ângulo arbitrário (rotate só aceita múltiplos de 90)
            page.insert_text(
                ponto,
                texto,
                fontsize=tamanho,
                color=(0.5, 0.5, 0.5),
                fill_opacity=opacidade,
                render_mode=0,
                morph=(ponto, fitz.Matrix(angulo)),
            )
        doc.save(out, garbage=4, deflate=True)
    finally:
        doc.close()
    return out


# ---------------------------------------------------------------------------
# Extração de imagens embutidas
# ---------------------------------------------------------------------------

def extrair_imagens_pdf(pdf_path: str, output_zip: str) -> dict:
    """Extrai todas as imagens embutidas do PDF para um .zip."""
    src = _require_pdf(pdf_path)
    out = _resolve_output(output_zip)
    doc = fitz.open(src)
    count = 0
    try:
        base = os.path.splitext(os.path.basename(src))[0]
        with _open_checked(out, "wb") as raw:
            with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zf:
                vistos: set[int] = set()
                for pnum, page in enumerate(doc, 1):
                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        if xref in vistos:
                            continue
                        vistos.add(xref)
                        try:
                            img = doc.extract_image(xref)
                            ext = img.get("ext", "png")
                            zf.writestr(f"{base}_img{count:03d}_p{pnum}.{ext}", img["image"])
                            count += 1
                        except Exception:
                            continue
    finally:
        doc.close()

    if count == 0:
        if os.path.isfile(out):
            os.remove(out)
        return {"output": None, "imagens": 0}
    return {"output": out, "imagens": count}


# ---------------------------------------------------------------------------
# PDF -> DOCX
# ---------------------------------------------------------------------------

def pdf_para_docx(pdf_path: str, output_path: str,
                  pages: list[int] | None = None) -> str:
    """Converte PDF para DOCX editável (melhor em PDFs com texto nativo)."""
    src = _require_pdf(pdf_path)
    out = _resolve_output(output_path)
    from pdf2docx import Converter

    doc = fitz.open(src)
    total = len(doc)
    doc.close()

    cv = Converter(src)
    try:
        if pages:
            invalidas = [p for p in pages if p < 1 or p > total]
            if invalidas:
                raise ValueError(f"Páginas inválidas: {invalidas}. O PDF tem {total} páginas.")
            # pdf2docx usa índices 0-based contínuos
            idx = sorted(p - 1 for p in pages)
            cv.convert(out, start=idx[0], end=idx[-1] + 1)
        else:
            cv.convert(out)
    finally:
        cv.close()
    return out


# ---------------------------------------------------------------------------
# PDF -> TXT (usa o motor OCR Beans)
# ---------------------------------------------------------------------------

def pdf_para_txt(pdf_path: str, output_path: str, dpi: int = 300,
                 lang: str = "por") -> dict:
    """Extrai texto do PDF (nativo ou OCR) e salva em .txt."""
    from .core import processar_pdf

    src = _require_pdf(pdf_path)
    out = _resolve_output(output_path)
    result = processar_pdf(src, dpi=dpi, lang=lang)

    lines = []
    for page in result["pages"]:
        lines.append(f"\n{'=' * 70}")
        lines.append(f"PÁGINA {page['number']} ({page['source']})")
        lines.append(f"{'=' * 70}")
        lines.append(page["content"])

    with _open_checked(out, "w") as f:
        f.write("\n".join(lines))

    return {
        "output": out,
        "total_pages": result["total_pages"],
        "ocr_pages": result["ocr_pages"],
        "text_pages": result["text_pages"],
    }
