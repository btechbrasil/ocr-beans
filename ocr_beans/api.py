"""
OCR Beans - API online (FastAPI)
Estilo "iLovePDF para programas": OCR + conversões de PDF/imagem via REST.

Uso:
    python -m ocr_beans.api                # sobe em 0.0.0.0:8080
    ocr-beans-api --port 9000              # via entry point
"""

import os
import re
import tempfile
import uuid

import anyio
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import __version__
from .core import (
    IMAGE_EXTENSIONS,
    check_legibility,
    idiomas_disponiveis,
    ocr_imagem,
    tesseract_disponivel,
)
from .convert import (
    _open_checked,
    adicionar_marca_dagua,
    comprimir_pdf,
    dividir_pdf,
    extrair_imagens_pdf,
    imagens_para_pdf,
    juntar_pdfs,
    pdf_para_docx,
    pdf_para_imagens,
    pdf_para_txt,
    rotacionar_pdf,
)
from .webui import INDEX_HTML

MAX_UPLOAD_MB = int(os.environ.get("OCR_BEANS_MAX_UPLOAD_MB", "200"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_FILES_PER_REQUEST = 50

app = FastAPI(
    title="OCR Beans API",
    version=__version__,
    description=(
        "OCR de PDFs judiciais brasileiros e imagens + ferramentas de "
        "conversão de PDF. Detecção automática de fontes corrompidas."
    ),
)

# Diretório temporário da sessão (efêmero: some com o processo)
_WORKDIR = tempfile.mkdtemp(prefix="ocr_beans_api_")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nome_seguro(filename: str | None, fallback: str = "arquivo") -> str:
    """Extrai um nome de arquivo seguro (basename, sem caracteres perigosos)."""
    nome = os.path.basename(filename or fallback)
    nome = re.sub(r"[^\w.\- ]", "_", nome, flags=re.UNICODE).strip()
    return nome or fallback


def _contido_no_workdir(path: str) -> str:
    """Garante que o caminho resolvido está dentro do workdir temporário."""
    base = os.path.realpath(_WORKDIR)
    resolved = os.path.realpath(path)
    try:
        comum = os.path.commonpath([resolved, base])
    except ValueError:
        raise HTTPException(status_code=422, detail="Caminho inválido.")
    if comum != base:
        raise HTTPException(status_code=422, detail="Destino fora do diretório de trabalho.")
    return resolved


async def _salvar_upload(upload: UploadFile, subdir: str) -> str:
    """Salva um UploadFile em disco com nome seguro e limite de tamanho."""
    # Rejeição antecipada pelo tamanho declarado (quando o cliente informa)
    if upload.size is not None and upload.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {MAX_UPLOAD_MB}MB.",
        )

    nome = _nome_seguro(upload.filename)
    path = _contido_no_workdir(os.path.join(_WORKDIR, subdir, f"{uuid.uuid4().hex[:8]}_{nome}"))

    escrito = 0
    with _open_checked(path, "wb") as f:
        while chunk := await upload.read(1024 * 1024):
            escrito += len(chunk)
            if escrito > MAX_UPLOAD_BYTES:
                # Aborta. O arquivo parcial permanece no workdir temporário,
                # que é efêmero e some com o processo.
                raise HTTPException(
                    status_code=413,
                    detail=f"Arquivo excede o limite de {MAX_UPLOAD_MB}MB.",
                )
            f.write(chunk)
    return path


def _saida(nome_base: str, ext: str) -> str:
    """Gera caminho de saída único no workdir."""
    base = os.path.splitext(_nome_seguro(nome_base))[0]
    return os.path.join(_WORKDIR, "out", f"{base}_{uuid.uuid4().hex[:6]}{ext}")


def _resposta_arquivo(path: str, download_name: str, media_type: str) -> FileResponse:
    """FileResponse com nome de download amigável."""
    return FileResponse(path, filename=download_name, media_type=media_type)


def _parse_pages(pages: str | None) -> list[int] | None:
    """Converte '1-3,7' em [1,2,3,7]; None/vazio -> None."""
    if not pages or not pages.strip():
        return None
    result: set[int] = set()
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            ini, fim = int(a), int(b)
            if fim - ini > 500:
                raise HTTPException(422, "Range de páginas muito grande (máx 500).")
            result.update(range(ini, fim + 1))
        else:
            result.add(int(part))
    if not result:
        return None
    return sorted(result)


def _erro(e: Exception) -> HTTPException:
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, (FileNotFoundError, ValueError)):
        return HTTPException(status_code=422, detail=str(e))
    return HTTPException(status_code=500, detail=f"Erro interno: {e}")


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    return INDEX_HTML


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "versao": __version__,
        "tesseract": tesseract_disponivel(),
        "idiomas": idiomas_disponiveis(),
    }


@app.get("/api/tools")
def tools():
    """Catálogo de operações — para descoberta programática."""
    return {
        "ocr": ["POST /api/ocr/pdf", "POST /api/ocr/image", "POST /api/check"],
        "conversoes": [
            "POST /api/convert/images-to-pdf",
            "POST /api/convert/pdf-to-images",
            "POST /api/convert/merge",
            "POST /api/convert/split",
            "POST /api/convert/compress",
            "POST /api/convert/rotate",
            "POST /api/convert/watermark",
            "POST /api/convert/pdf-to-docx",
            "POST /api/convert/pdf-to-txt",
            "POST /api/convert/extract-images",
        ],
        "limites": {"upload_mb": MAX_UPLOAD_MB, "arquivos_por_request": MAX_FILES_PER_REQUEST},
    }


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

@app.post("/api/ocr/pdf")
async def api_ocr_pdf(file: UploadFile = File(...), dpi: int = Form(300),
                      lang: str = Form("por")):
    """Extrai texto de PDF (nativo ou OCR automático). Retorna .txt."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        out = _saida(file.filename or "documento", ".txt")
        # Trabalho pesado em thread separada: não bloqueia o event loop
        info = await anyio.to_thread.run_sync(
            lambda: pdf_para_txt(src, out, dpi=dpi, lang=lang))
        resp = _resposta_arquivo(out, os.path.basename(out), "text/plain; charset=utf-8")
        resp.headers["X-OCR-Pages"] = str(info["ocr_pages"])
        resp.headers["X-Text-Pages"] = str(info["text_pages"])
        return resp
    except Exception as e:
        raise _erro(e)


@app.post("/api/ocr/image")
async def api_ocr_image(file: UploadFile = File(...), lang: str = Form("por"),
                        psm: int = Form(6)):
    """OCR direto em imagem (png/jpg/tif/bmp/webp). Retorna JSON com o texto."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        ext = os.path.splitext(src)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            raise HTTPException(422, f"Formato não suportado: {ext}")
        result = await anyio.to_thread.run_sync(
            lambda: ocr_imagem(src, lang=lang, psm=psm))
        return JSONResponse({
            "arquivo": _nome_seguro(file.filename),
            "largura": result["width"],
            "altura": result["height"],
            "idioma": result["lang"],
            "texto": result["content"],
        })
    except Exception as e:
        raise _erro(e)


@app.post("/api/check")
async def api_check(file: UploadFile = File(...)):
    """Diagnóstico rápido: o PDF precisa de OCR? (sem processar)."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        info = await anyio.to_thread.run_sync(lambda: check_legibility(src))
        return JSONResponse(info)
    except Exception as e:
        raise _erro(e)


# ---------------------------------------------------------------------------
# Conversões
# ---------------------------------------------------------------------------

@app.post("/api/convert/images-to-pdf")
async def api_images_to_pdf(files: list[UploadFile] = File(...)):
    """Junta imagens em um único PDF."""
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(422, f"Máximo {MAX_FILES_PER_REQUEST} arquivos.")
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        paths = [await _salvar_upload(f, os.path.basename(sub)) for f in files]
        out = _saida("imagens", ".pdf")
        await anyio.to_thread.run_sync(lambda: imagens_para_pdf(paths, out))
        return _resposta_arquivo(out, "imagens.pdf", "application/pdf")
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/pdf-to-images")
async def api_pdf_to_images(file: UploadFile = File(...), dpi: int = Form(200),
                            fmt: str = Form("png"), pages: str = Form("")):
    """Renderiza páginas do PDF como imagens (zip)."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        out = _saida(file.filename or "pdf", ".zip")
        alvo = _parse_pages(pages)
        await anyio.to_thread.run_sync(
            lambda: pdf_para_imagens(src, out, dpi=dpi, fmt=fmt, pages=alvo))
        return _resposta_arquivo(out, os.path.basename(out), "application/zip")
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/merge")
async def api_merge(files: list[UploadFile] = File(...)):
    """Junta vários PDFs em um só, na ordem enviada."""
    if len(files) < 2:
        raise HTTPException(422, "Envie ao menos 2 PDFs.")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(422, f"Máximo {MAX_FILES_PER_REQUEST} arquivos.")
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        paths = [await _salvar_upload(f, os.path.basename(sub)) for f in files]
        out = _saida("merged", ".pdf")
        await anyio.to_thread.run_sync(lambda: juntar_pdfs(paths, out))
        return _resposta_arquivo(out, "merged.pdf", "application/pdf")
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/split")
async def api_split(file: UploadFile = File(...), pages: str = Form(...)):
    """Extrai páginas do PDF (ex.: pages='1-3,7')."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        lista = _parse_pages(pages)
        if not lista:
            raise HTTPException(422, "Informe as páginas (ex.: 1-3,7).")
        out = _saida(file.filename or "pdf", ".pdf")
        await anyio.to_thread.run_sync(lambda: dividir_pdf(src, out, lista))
        return _resposta_arquivo(out, os.path.basename(out), "application/pdf")
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/compress")
async def api_compress(file: UploadFile = File(...), qualidade: int = Form(60)):
    """Comprime o PDF recompactando imagens embutidas."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        out = _saida(file.filename or "pdf", ".pdf")
        info = await anyio.to_thread.run_sync(
            lambda: comprimir_pdf(src, out, qualidade_imagem=qualidade))
        resp = _resposta_arquivo(out, os.path.basename(out), "application/pdf")
        resp.headers["X-Reducao-Pct"] = str(info["reducao_pct"])
        return resp
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/rotate")
async def api_rotate(file: UploadFile = File(...), graus: int = Form(90),
                     pages: str = Form("")):
    """Rotaciona páginas do PDF (90/180/270)."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        out = _saida(file.filename or "pdf", ".pdf")
        alvo = _parse_pages(pages)
        await anyio.to_thread.run_sync(
            lambda: rotacionar_pdf(src, out, graus=graus, pages=alvo))
        return _resposta_arquivo(out, os.path.basename(out), "application/pdf")
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/watermark")
async def api_watermark(file: UploadFile = File(...), texto: str = Form("CONFIDENCIAL")):
    """Aplica marca d'água de texto em todas as páginas."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        out = _saida(file.filename or "pdf", ".pdf")
        await anyio.to_thread.run_sync(
            lambda: adicionar_marca_dagua(src, out, texto))
        return _resposta_arquivo(out, os.path.basename(out), "application/pdf")
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/pdf-to-docx")
async def api_pdf_to_docx(file: UploadFile = File(...), pages: str = Form("")):
    """Converte PDF para DOCX editável."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        out = _saida(file.filename or "pdf", ".docx")
        alvo = _parse_pages(pages)
        await anyio.to_thread.run_sync(
            lambda: pdf_para_docx(src, out, pages=alvo))
        return _resposta_arquivo(
            out, os.path.basename(out),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        raise _erro(e)


@app.post("/api/convert/pdf-to-txt")
async def api_pdf_to_txt(file: UploadFile = File(...), dpi: int = Form(300),
                         lang: str = Form("por")):
    """Alias de /api/ocr/pdf."""
    return await api_ocr_pdf(file=file, dpi=dpi, lang=lang)


@app.post("/api/convert/extract-images")
async def api_extract_images(file: UploadFile = File(...)):
    """Extrai todas as imagens embutidas do PDF (zip)."""
    sub = tempfile.mkdtemp(dir=_WORKDIR)
    try:
        src = await _salvar_upload(file, os.path.basename(sub))
        out = _saida(file.filename or "pdf", ".zip")
        info = await anyio.to_thread.run_sync(
            lambda: extrair_imagens_pdf(src, out))
        if not info["output"]:
            return JSONResponse({"imagens": 0, "detalhe": "PDF não contém imagens embutidas."})
        return _resposta_arquivo(out, os.path.basename(out), "application/zip")
    except Exception as e:
        raise _erro(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="OCR Beans API (web + REST)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()

    os.makedirs(os.path.join(_WORKDIR, "out"), exist_ok=True)
    uvicorn.run(app, host=args.host, port=args.port)


# Garante o diretório de saída mesmo quando servido por outro ASGI server
os.makedirs(os.path.join(_WORKDIR, "out"), exist_ok=True)

if __name__ == "__main__":
    main()
