"""
OCR Beans - MCP Server
Expõe as capacidades de OCR como tools para Claude Code e agentes AI.

Uso:
    python -m ocr_beans.mcp_server            # local (stdio)
    python -m ocr_beans.mcp_server --remote   # cloud (HTTP, porta 8080)
"""

import json
import logging
import os
import sys

import anyio

try:
    # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer
    _MCP_V1 = True
except ImportError:
    # MCP SDK 2.x: FastMCP renomeado para MCPServer; host/port vão para run()
    from mcp.server.mcpserver import MCPServer as _MCPServer
    _MCP_V1 = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ocr_beans.core import (
    check_legibility as _check_legibility,
    ocr_imagem,
    processar_paginas,
    processar_pdf,
)
from ocr_beans.security import (
    validate_batch,
    validate_directory,
    validate_dpi,
    validate_image_path,
    validate_page_range,
    validate_path,
    validate_pdf_size,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("ocr_beans.mcp")

_remote = "--remote" in sys.argv
_port = 8080
for _i, _arg in enumerate(sys.argv):
    if _arg == "--port" and _i + 1 < len(sys.argv):
        _port = int(sys.argv[_i + 1])

_instructions = (
    "OCR Beans - Extrator de texto de PDFs judiciais brasileiros e imagens. "
    "Especializado em PDFs com fontes corrompidas/proprietárias comuns em tribunais do Brasil (TJ-SP, TRT, STJ). "
    "Detecta automaticamente se o PDF precisa de OCR ou se o texto nativo é legível."
)

if _MCP_V1:
    mcp = _MCPServer(
        name="ocr-beans",
        instructions=_instructions,
        host="0.0.0.0" if _remote else "127.0.0.1",
        port=_port,
    )
else:
    mcp = _MCPServer(name="ocr-beans", instructions=_instructions)

PAGE_THRESHOLD = 30
MAX_INLINE_CHARS = 100_000


def _format_full_text(result: dict) -> str:
    """Formata o resultado em texto completo com cabeçalho."""
    lines = []
    lines.append(f"{'=' * 70}")
    lines.append(f"DOCUMENTO: {os.path.basename(result['path'])}")
    lines.append(f"PROCESSADO EM: OCR Beans MCP (PyMuPDF + Tesseract)")
    lines.append(f"TOTAL DE PÁGINAS: {result['total_pages']}")
    lines.append(f"{'=' * 70}\n")

    for page in result["pages"]:
        lines.append(f"\n{'=' * 70}")
        lines.append(f"PÁGINA {page['number']} ({page['source']})")
        lines.append(f"{'=' * 70}")
        lines.append(page["content"])
        lines.append(f"fls. {page['number']}")

    return "\n".join(lines)


def _abrir_saida(path: str, mode: str = "w"):
    """Abre arquivo com validacao inline: sem '..' nem nulos, pasta existente."""
    if not path or "\x00" in path or ".." in path.replace("\\", "/").split("/"):
        raise ValueError(f"Caminho invalido: {path!r}")
    resolved = os.path.realpath(os.path.expanduser(path))
    if "r" in mode:
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
    else:
        parent = os.path.dirname(resolved)
        if not parent or not os.path.isdir(parent):
            raise ValueError(f"Diretorio de saida nao existe: {path}")
    return open(resolved, mode, encoding="utf-8" if "b" not in mode else None)


def _save_to_file(text: str, pdf_path: str, output_path: str | None = None) -> str:
    """Salva texto em arquivo .txt e retorna o caminho."""
    if not output_path:
        output_path = os.path.splitext(pdf_path)[0] + ".txt"
    with _abrir_saida(output_path, "w") as f:
        f.write(text)
    return os.path.realpath(output_path)


def _make_summary(result: dict, saved_path: str) -> str:
    """Gera resumo para PDFs grandes."""
    pages = result["pages"]
    first_preview = pages[0]["content"][:200] if pages else ""
    last_preview = pages[-1]["content"][:200] if len(pages) > 1 else ""

    summary = (
        f"Texto extraído e salvo em: {saved_path}\n\n"
        f"Resumo: {result['total_pages']} páginas | "
        f"{result['ocr_pages']} via OCR | {result['text_pages']} via texto nativo\n\n"
        f"--- Primeira página (preview) ---\n{first_preview}\n\n"
        f"--- Última página (preview) ---\n{last_preview}\n\n"
        f"Use a tool 'ocr_page' para ler páginas específicas."
    )
    return summary


@mcp.tool()
async def ocr_pdf(pdf_path: str, dpi: int = 300, save_to_file: bool = False) -> str:
    """Extrai texto de um PDF. Detecta automaticamente fontes corrompidas
    (comum em PDFs judiciais brasileiros) e aplica OCR quando necessário.

    Para PDFs pequenos (<=30 páginas), retorna o texto completo.
    Para PDFs grandes, salva em .txt e retorna o caminho + resumo.

    Args:
        pdf_path: Caminho absoluto do arquivo PDF.
        dpi: Resolução para OCR (150, 200, 300 ou 400). Default: 300.
        save_to_file: Forçar salvamento em arquivo .txt mesmo para PDFs pequenos.
    """
    pdf_path = validate_path(pdf_path)
    dpi = validate_dpi(dpi)
    validate_pdf_size(pdf_path)

    result = await anyio.to_thread.run_sync(lambda: processar_pdf(pdf_path, dpi=dpi))

    full_text = _format_full_text(result)

    if save_to_file or result["total_pages"] > PAGE_THRESHOLD or len(full_text) > MAX_INLINE_CHARS:
        saved_path = _save_to_file(full_text, pdf_path)
        return _make_summary(result, saved_path)

    return full_text


@mcp.tool()
async def ocr_page(pdf_path: str, pages: str, dpi: int = 300) -> str:
    """Extrai texto de páginas específicas de um PDF.

    Útil para PDFs grandes onde você só precisa de algumas páginas,
    ou para follow-up após usar ocr_pdf em um documento grande.

    Args:
        pdf_path: Caminho absoluto do arquivo PDF.
        pages: Páginas a extrair. Formatos aceitos: "1", "1-5", "1,3,7", "2-4,8".
        dpi: Resolução para OCR (150, 200, 300 ou 400). Default: 300.
    """
    pdf_path = validate_path(pdf_path)
    dpi = validate_dpi(dpi)
    validate_pdf_size(pdf_path)
    validate_page_range(pages)

    result = await anyio.to_thread.run_sync(
        lambda: processar_paginas(pdf_path, pages, dpi=dpi)
    )

    lines = []
    for page in result["pages"]:
        lines.append(f"\n{'=' * 70}")
        lines.append(f"PÁGINA {page['number']} ({page['source']})")
        lines.append(f"{'=' * 70}")
        lines.append(page["content"])
        lines.append(f"fls. {page['number']}")

    return "\n".join(lines)


@mcp.tool()
async def ocr_image(image_path: str, lang: str = "por", psm: int = 6) -> str:
    """Extrai texto de uma imagem via OCR (Tesseract).

    Útil para prints de decisões, páginas escaneadas salvas como imagem,
    fotos de documentos etc.

    Args:
        image_path: Caminho absoluto da imagem (png, jpg, jpeg, tif, tiff, bmp, webp, gif).
        lang: Idioma do Tesseract (por, eng, por+eng). Default: por.
        psm: Modo de segmentação (3=auto, 6=bloco uniforme, 11=texto esparso). Default: 6.
    """
    image_path = validate_image_path(image_path)
    if psm not in (3, 4, 6, 11, 12):
        raise ValueError("psm deve ser 3, 4, 6, 11 ou 12.")

    result = await anyio.to_thread.run_sync(
        lambda: ocr_imagem(image_path, lang=lang, psm=psm)
    )

    return (
        f"IMAGEM: {os.path.basename(result['path'])} "
        f"({result['width']}x{result['height']}, lang={result['lang']})\n"
        f"{'=' * 70}\n{result['content']}"
    )


@mcp.tool()
async def check_legibility(pdf_path: str) -> str:
    """Diagnóstico rápido: verifica se um PDF tem fontes corrompidas/proprietárias.

    Não faz OCR — apenas analisa o texto nativo da primeira página para determinar
    se o documento precisará de OCR. Operação rápida (< 1 segundo).

    Args:
        pdf_path: Caminho absoluto do arquivo PDF.
    """
    pdf_path = validate_path(pdf_path)

    result = await anyio.to_thread.run_sync(lambda: _check_legibility(pdf_path))

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def batch_ocr(directory: str, output_directory: str | None = None, dpi: int = 300) -> str:
    """Processa todos os PDFs de um diretório via OCR.

    Salva cada resultado como .txt (no mesmo diretório ou em output_directory).
    Retorna um resumo com a lista de arquivos processados.

    Args:
        directory: Caminho do diretório contendo os PDFs.
        output_directory: Diretório de saída (opcional). Se não informado, salva ao lado dos PDFs.
        dpi: Resolução para OCR (150, 200, 300 ou 400). Default: 300.
    """
    directory = validate_directory(directory)
    dpi = validate_dpi(dpi)
    pdf_files = validate_batch(directory)

    if output_directory:
        output_directory = os.path.abspath(output_directory)
        os.makedirs(output_directory, exist_ok=True)

    if not pdf_files:
        return f"Nenhum PDF encontrado em: {directory}"

    results = []

    for filename in pdf_files:
        pdf_path = os.path.join(directory, filename)
        try:
            validate_pdf_size(pdf_path)
            result = await anyio.to_thread.run_sync(
                lambda p=pdf_path: processar_pdf(p, dpi=dpi)
            )
            full_text = _format_full_text(result)

            if output_directory:
                out_path = os.path.join(output_directory, os.path.splitext(filename)[0] + ".txt")
            else:
                out_path = os.path.splitext(pdf_path)[0] + ".txt"

            _save_to_file(full_text, pdf_path, out_path)

            results.append(
                f"OK  | {filename} -> {os.path.basename(out_path)} "
                f"({result['total_pages']} pags, {result['ocr_pages']} OCR)"
            )
        except Exception as e:
            results.append(f"ERRO | {filename}: {e}")
            logger.error("Falha ao processar %s: %s", filename, e)

    summary = (
        f"Batch OCR concluido: {len(pdf_files)} PDFs em {directory}\n"
        f"{'=' * 70}\n" + "\n".join(results)
    )
    return summary


def main():
    if _remote:
        logger.info("OCR Beans MCP iniciando em modo remoto (porta %d)", _port)
        if _MCP_V1:
            mcp.run(transport="streamable-http")
        else:
            mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
