#!/usr/bin/env python3
"""Smoke test autossuficiente do OCR Beans MCP (stdio).

Gera os próprios fixtures (PDF com texto nativo, PDF somente-imagem e PNG),
soba o servidor MCP com o MESMO comando do manifest (uv run --with …) e
exercita os 5 tools. Sem dados externos, sem rede, sem GPU.

Uso:  python3 tests/smoke.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def fixtures(tmp):
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(
        "core_fx", os.path.join(ROOT, "ocr_beans", "core.py"))
    spec = importlib.util.spec_from_loader("core_fx", loader)
    core = importlib.util.module_from_spec(spec)
    loader.exec_module(core)

    from PIL import Image, ImageDraw, ImageFont

    # PDF com texto nativo
    doc = core.fitz.open()
    p = doc.new_page()
    p.insert_text((72, 120), "TRIBUNAL DE JUSTICA DO ESTADO DE SAO PAULO")
    p.insert_text((72, 160), "Processo teste smoke OCR Beans")
    pdf_path = os.path.join(tmp, "nativo.pdf")
    doc.save(pdf_path)

    # PDF somente-imagem (força OCR) + PNG solto
    font = ImageFont.load_default(size=52)
    img = Image.new("RGB", (1654, 2339), "white")
    d = ImageDraw.Draw(img)
    d.text((80, 200), "MANDADO DE CITACAO", font=font, fill="black")
    d.text((80, 320), "Documento escaneado teste smoke", font=font, fill="black")
    png_path = os.path.join(tmp, "scan.png")
    img.save(png_path)
    doc = core.fitz.open()
    p = doc.new_page()
    p.insert_image(p.rect, filename=png_path)
    scan_path = os.path.join(tmp, "scan.pdf")
    doc.save(scan_path)
    return pdf_path, png_path, scan_path


def main():
    tmp = tempfile.mkdtemp(prefix="ocrbeans-smoke-")
    pdf, png, scan = fixtures(tmp)

    proc = subprocess.Popen(  # lista literal, sem shell — comando do manifest
        ["uv", "run", "--no-project", "--python", "3.12",
         "--with", "pymupdf==1.28.2", "--with", "pytesseract==0.3.13",
         "--with", "Pillow==12.3.0", "--with", "mcp==2.3.0",
         "python3", os.path.join(ROOT, "ocr_beans", "mcp_server.py")],
        cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    msg_id = 0

    def call(method, params=None):
        nonlocal msg_id
        msg_id += 1
        m = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            m["params"] = params
        proc.stdin.write(json.dumps(m) + "\n")
        proc.stdin.flush()
        deadline = time.time() + 240
        while time.time() < deadline:
            line = proc.stdout.readline()
            if line:
                resp = json.loads(line)
                if resp.get("id") == msg_id:
                    return resp
        raise TimeoutError(f"sem resposta: {method}")

    def tool(name, args):
        return call("tools/call", {"name": name, "arguments": args})

    ok = True

    r = call("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "smoke", "version": "1.0"}})
    srv = r.get("result", {}).get("serverInfo", {}).get("name", "")
    print(f"1. initialize → {srv}")
    ok &= srv == "ocr-beans"
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    names = [t["name"] for t in call("tools/list").get("result", {}).get("tools", [])]
    print(f"2. tools/list → {len(names)} tools")
    ok &= len(names) == 5

    r = tool("check_legibility", {"pdf_path": pdf})
    txt = r["result"]["content"][0]["text"]
    print(f"3. check_legibility → {'legível' if 'true' in txt.lower() else '??'}")
    ok &= "true" in txt.lower()

    r = tool("ocr_pdf", {"pdf_path": pdf})
    txt = r["result"]["content"][0]["text"]
    print(f"4. ocr_pdf (nativo) → {'TRIBUNAL' in txt and 'PÁGINA 1' in txt}")
    ok &= "TRIBUNAL" in txt

    r = tool("ocr_page", {"pdf_path": pdf, "pages": "1"})
    txt = r["result"]["content"][0]["text"]
    print(f"5. ocr_page 1 → {'PÁGINA 1' in txt}")
    ok &= "PÁGINA 1" in txt

    r = tool("ocr_image", {"image_path": png})
    txt = r["result"]["content"][0]["text"]
    print(f"6. ocr_image (Tesseract) → {'MANDADO' in txt.upper()}")
    ok &= "MANDADO" in txt.upper()

    r = tool("ocr_pdf", {"pdf_path": scan})
    txt = r["result"]["content"][0]["text"]
    print(f"7. ocr_pdf (somente-imagem → OCR) → {'MANDADO' in txt.upper()}")
    ok &= "MANDADO" in txt.upper()

    r = tool("ocr_pdf", {"pdf_path": "/tmp/inexistente-smoke.pdf"})
    err = r["result"].get("isError", False)
    print(f"8. arquivo inexistente → rejeitado: {err}")
    ok &= err

    r = tool("ocr_pdf", {"pdf_path": pdf, "dpi": 500})
    err = r["result"].get("isError", False)
    print(f"9. dpi inválido → rejeitado: {err}")
    ok &= err

    proc.stdin.close()
    proc.terminate()

    print()
    print("SMOKE " + ("PASSOU" if ok else "FALHOU"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
