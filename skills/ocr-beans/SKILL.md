---
name: ocr-beans
description: Extrai texto de processos judiciais brasileiros (PDF/imagens) com o motor PyMuPDF + Tesseract offline. Use quando o usuário citar processos, petições, decisões, TJSP/TRF/STJ, PDFs de tribunais, OCR de documentos jurídicos, ou precisar ler PDF que "não abre texto" (fonte corrompida de tribunal).
---

# OCR Beans

Extrator de texto para documentos jurídicos brasileiros. Motor **PyMuPDF + Tesseract,
100% offline** — nada sai da máquina (LGPD por construção).

## Por que existe

PDFs de tribunais brasileiros frequentemente têm **fontes com encoding
proprietário**: aparentam ter texto, mas a extração devolve lixo
(`?@#¥Ø§...`). O OCR Beans detecta isso automaticamente e só então aplica OCR
na página — o resto sai do texto nativo, instantâneo e perfeito.

## Ferramentas (MCP)

| Tool | Quando usar |
|---|---|
| `check_legibility` | Diagnóstico rápido (<1s): o PDF precisa de OCR? |
| `ocr_pdf` | Processo completo. ≤30 págs retorna texto; maiores salvam .txt + resumo |
| `ocr_page` | Páginas específicas ("1-5", "3,7,9") — ideal em processos de milhares de páginas |
| `ocr_image` | Prints de decisões, fotos de documentos, scans avulsos |
| `batch_ocr` | Pasta inteira de PDFs (até 50 por vez) |

## Fluxo recomendado para processos

1. `check_legibility` → sabe em <1s se o processo é texto nativo ou escaneado
2. `ocr_pdf` → extrai tudo (texto nativo instantâneo; OCR ~2s/página só onde precisa)
3. `ocr_page` → reler páginas específicas citadas na decisão
4. PDFs de 200+ páginas: o resultado vai para `.txt` ao lado do PDF — leia o
   caminho retornado e use Read/zoom conforme necessário

## Vantagens sobre visão-LLM (glm-ocr & cia)

- **Instantâneo** em texto nativo (0,0s vs 26–67s/página)
- **Determinístico**: mesma entrada, mesmo texto — sem alucinação de acentos
- **Offline**: nenhum dado sai do computador do usuário
- **Grátis**: sem tokens, sem GPU, sem endpoint

## Pré-requisitos

**Dependências Python: automáticas.** O manifest do plugin sobe o servidor via
`uv run --with pymupdf --with pytesseract --with Pillow --with mcp` — o uv cria
o ambiente isolado sozinho na primeira execução (baixa ~50 MB uma vez, usa
cache depois). Sem uv na máquina: `curl -LsSf https://astral.sh/uv/install.sh | sh`
(um binário) — ou o fallback documentado `pip install --user pymupdf pytesseract Pillow mcp`.

**Tesseract + idioma `por`:** único componente de sistema. Sem ele o servidor
**sobe mesmo assim** (texto nativo — ~99% dos processos PJe — funciona
normalmente; páginas OCR retornam erro instrutivo):
- Linux: `sudo apt install tesseract-ocr tesseract-ocr-por`
- macOS: `brew install tesseract tesseract-lang`
- Windows: instalador UB-Mannheim (marcar Portuguese)
- Sem PATH: variável `TESSERACT_CMD` apontando o binário

**Diagnóstico:** `python3 verificar.py` (na raiz do plugin) — confere tudo e
imprime os comandos exatos do que faltar.

## Limites de segurança

PDF até 200 MB · imagem até 50 MB · 50 arquivos por batch · 100 páginas por
`ocr_page` · DPI 150–400.
