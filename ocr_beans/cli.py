"""
OCR Beans - CLI unificado.

Exemplos:
    ocr-beans pdf documento.pdf
    ocr-beans pdf documento.pdf --paginas 1-5 --dpi 300
    ocr-beans imagem scan.png
    ocr-beans check documento.pdf
    ocr-beans juntar a.pdf b.pdf -o merged.pdf
    ocr-beans dividir doc.pdf --paginas 1-3,7 -o saida.pdf
    ocr-beans comprimir doc.pdf -o pequeno.pdf --qualidade 60
    ocr-beans girar doc.pdf --graus 90 -o girado.pdf
    ocr-beans marca-dagua doc.pdf --texto CONFIDENCIAL -o marcado.pdf
    ocr-beans pdf-para-imagens doc.pdf -o paginas.zip --dpi 200
    ocr-beans imagens-para-pdf foto1.png foto2.jpg -o saida.pdf
    ocr-beans pdf-para-docx doc.pdf -o saida.docx
    ocr-beans extrair-imagens doc.pdf -o imagens.zip
"""

import argparse
import json
import os
import sys


def _resolver(path: str) -> str:
    """Resolve o caminho do usuário para absoluto antes de chamar o motor."""
    return os.path.realpath(os.path.expanduser(path))


def _saida_padrao(src: str, suffix: str, ext: str) -> str:
    base = os.path.splitext(_resolver(src))[0]
    return f"{base}{suffix}{ext}"


def _parse_pages(s: str | None) -> list[int] | None:
    if not s:
        return None
    pages: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return sorted(pages) if pages else None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ocr-beans",
        description="OCR Beans — OCR de PDFs judiciais e imagens + conversões de PDF.",
    )
    parser.add_argument("--version", action="store_true", help="Mostra a versão e sai")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("pdf", help="Extrai texto de PDF (nativo ou OCR)")
    p.add_argument("arquivo")
    p.add_argument("-o", "--output", help="Arquivo .txt de saída")
    p.add_argument("--paginas", help="Ex.: 1-5,8 (default: todas)")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--lang", default="por")

    p = sub.add_parser("imagem", help="OCR em imagem (png/jpg/tif/bmp/webp)")
    p.add_argument("arquivo")
    p.add_argument("--lang", default="por")
    p.add_argument("--psm", type=int, default=6)

    p = sub.add_parser("check", help="Diagnóstico: o PDF precisa de OCR?")
    p.add_argument("arquivo")

    p = sub.add_parser("juntar", help="Junta vários PDFs em um só")
    p.add_argument("arquivos", nargs="+")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("dividir", help="Extrai páginas de um PDF")
    p.add_argument("arquivo")
    p.add_argument("--paginas", required=True, help="Ex.: 1-3,7")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("comprimir", help="Comprime um PDF")
    p.add_argument("arquivo")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--qualidade", type=int, default=60)

    p = sub.add_parser("girar", help="Rotaciona páginas do PDF")
    p.add_argument("arquivo")
    p.add_argument("--graus", type=int, default=90, choices=[90, 180, 270])
    p.add_argument("--paginas", help="Ex.: 1-3,7 (default: todas)")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("marca-dagua", help="Aplica marca d'água de texto")
    p.add_argument("arquivo")
    p.add_argument("--texto", required=True)
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("pdf-para-imagens", help="Renderiza PDF para imagens (zip)")
    p.add_argument("arquivo")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--fmt", default="png", choices=["png", "jpg"])
    p.add_argument("--paginas", help="Ex.: 1-3 (default: todas)")

    p = sub.add_parser("imagens-para-pdf", help="Junta imagens em um PDF")
    p.add_argument("arquivos", nargs="+")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("pdf-para-docx", help="Converte PDF para DOCX")
    p.add_argument("arquivo")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--paginas", help="Ex.: 1-3 (default: todas)")

    p = sub.add_parser("extrair-imagens", help="Extrai imagens embutidas do PDF (zip)")
    p.add_argument("arquivo")
    p.add_argument("-o", "--output", required=True)

    args = parser.parse_args()

    if args.version:
        from . import __version__
        print(f"ocr-beans {__version__}")
        return

    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    try:
        _executar(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(2)


def _executar(args) -> None:
    from .core import check_legibility, ocr_imagem, processar_paginas, processar_pdf
    from . import convert

    if args.cmd == "pdf":
        src = _resolver(args.arquivo)
        out = _resolver(args.output) if args.output else _saida_padrao(src, "", ".txt")
        if args.paginas:
            result = processar_paginas(src, args.paginas, dpi=args.dpi, lang=args.lang)
        else:
            result = processar_pdf(src, dpi=args.dpi, lang=args.lang)
        lines = []
        for page in result["pages"]:
            lines.append(f"\n{'=' * 70}")
            lines.append(f"PÁGINA {page['number']} ({page['source']})")
            lines.append(f"{'=' * 70}")
            lines.append(page["content"])
        with convert._open_checked(out, "w") as f:
            f.write("\n".join(lines))
        print(f"Salvo: {out}")

    elif args.cmd == "imagem":
        result = ocr_imagem(_resolver(args.arquivo), lang=args.lang, psm=args.psm)
        print(result["content"])

    elif args.cmd == "check":
        info = check_legibility(_resolver(args.arquivo))
        print(json.dumps(info, ensure_ascii=False, indent=2))

    elif args.cmd == "juntar":
        fontes = [_resolver(a) for a in args.arquivos]
        print(f"Salvo: {convert.juntar_pdfs(fontes, _resolver(args.output))}")

    elif args.cmd == "dividir":
        pages = _parse_pages(args.paginas)
        print(f"Salvo: {convert.dividir_pdf(_resolver(args.arquivo), _resolver(args.output), pages)}")

    elif args.cmd == "comprimir":
        info = convert.comprimir_pdf(_resolver(args.arquivo), _resolver(args.output),
                                     qualidade_imagem=args.qualidade)
        print(f"Salvo: {info['output']} "
              f"({info['tamanho_original'] // 1024} KB -> {info['tamanho_final'] // 1024} KB, "
              f"-{info['reducao_pct']}%)")

    elif args.cmd == "girar":
        out = convert.rotacionar_pdf(_resolver(args.arquivo), _resolver(args.output),
                                     graus=args.graus, pages=_parse_pages(args.paginas))
        print(f"Salvo: {out}")

    elif args.cmd == "marca-dagua":
        out = convert.adicionar_marca_dagua(_resolver(args.arquivo), _resolver(args.output),
                                            args.texto)
        print(f"Salvo: {out}")

    elif args.cmd == "pdf-para-imagens":
        out = convert.pdf_para_imagens(_resolver(args.arquivo), _resolver(args.output),
                                       dpi=args.dpi, fmt=args.fmt,
                                       pages=_parse_pages(args.paginas))
        print(f"Salvo: {out}")

    elif args.cmd == "imagens-para-pdf":
        fontes = [_resolver(a) for a in args.arquivos]
        out = convert.imagens_para_pdf(fontes, _resolver(args.output))
        print(f"Salvo: {out}")

    elif args.cmd == "pdf-para-docx":
        out = convert.pdf_para_docx(_resolver(args.arquivo), _resolver(args.output),
                                    pages=_parse_pages(args.paginas))
        print(f"Salvo: {out}")

    elif args.cmd == "extrair-imagens":
        info = convert.extrair_imagens_pdf(_resolver(args.arquivo), _resolver(args.output))
        if info["output"]:
            print(f"Salvo: {info['output']} ({info['imagens']} imagens)")
        else:
            print("O PDF não contém imagens embutidas.")


if __name__ == "__main__":
    main()
