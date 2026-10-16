# MCP Server — OCR Beans

Expõe o OCR como tools para Claude Code e outros agentes AI compatíveis com
Model Context Protocol. Compatível com MCP SDK 1.x e 2.x.

## Configuração (stdio — uso local)

Adicione ao `~/.claude.json` (seção `mcpServers`):

**Linux/macOS:**
```json
{
  "ocr-beans": {
    "type": "stdio",
    "command": "python3",
    "args": ["/caminho/para/OCR Beans/ocr_beans/mcp_server.py"]
  }
}
```

**Windows:**
```json
{
  "ocr-beans": {
    "type": "stdio",
    "command": "python",
    "args": ["C:/OCR Beans/ocr_beans/mcp_server.py"],
    "env": {
      "TESSERACT_CMD": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
    }
  }
}
```

Reinicie o cliente. As tools ficam disponíveis automaticamente.

## Tools

### `ocr_pdf`
Extrai texto de um PDF completo. PDFs pequenos (≤30 páginas) retornam inline;
grandes são salvos em `.txt` e retornam resumo + previews.

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `pdf_path` | — | Caminho absoluto do PDF |
| `dpi` | 300 | 150–400 |
| `save_to_file` | false | Forçar salvamento em .txt |

### `ocr_page`
Extrai páginas específicas: `"1"`, `"1-5"`, `"1,3,7"`, `"2-4,8"` (máx. 100 por request).

### `ocr_image`
OCR de imagem (png/jpg/jpeg/tif/tiff/bmp/webp/gif, máx. 50MB).

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `image_path` | — | Caminho absoluto da imagem |
| `lang` | por | Idioma Tesseract |
| `psm` | 6 | Segmentação: 3, 4, 6, 11 ou 12 |

### `check_legibility`
Diagnóstico rápido (< 1s): retorna JSON com `legible`, `total_pages`,
`sample_text`, `reason`. Não faz OCR.

### `batch_ocr`
Processa todos os PDFs de um diretório (máx. 50), salvando um `.txt` por PDF.

## Modo remoto (HTTP)

```bash
python -m ocr_beans.mcp_server --remote --port 8080
```

Cliente:

```json
{
  "ocr-beans": {
    "type": "streamable-http",
    "url": "http://localhost:8080/mcp"
  }
}
```

## Limites de segurança

- Apenas extensões válidas (.pdf nas tools de PDF; formatos de imagem em `ocr_image`)
- PDFs até 200MB; imagens até 50MB
- DPI entre 150 e 400
- Até 100 páginas por request / 50 PDFs por batch
