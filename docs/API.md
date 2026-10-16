# API REST — OCR Beans

Suba o servidor:

```bash
ocr-beans-api --port 8080
# ou: python -m ocr_beans.api --port 8080
# ou: uvicorn ocr_beans.api:app --port 8080
```

- **UI web** (para humanos): `http://localhost:8080/`
- **Swagger interativo**: `http://localhost:8080/docs`
- **Health check**: `GET /api/health`

Todas as rotas de operação aceitam `multipart/form-data` (upload de arquivo) e
devolvem o arquivo resultante para download (`Content-Disposition: attachment`),
exceto as de OCR de imagem e diagnóstico, que devolvem JSON.

## Limites

- Upload: 200MB por arquivo (env `OCR_BEANS_MAX_UPLOAD_MB`)
- Até 50 arquivos por request (merge / images-to-pdf)
- Range de páginas: máximo 500 páginas por request

## Autenticação

Não há auth embutida. Para expor publicamente, use reverse proxy com auth
(nginx + basic auth, Cloudflare Access, IAP no GCP, ALB auth na AWS).

---

## OCR

### `POST /api/ocr/pdf`

Extrai texto de PDF. Texto nativo quando legível; OCR automático quando a fonte
é corrompida ou a página é scan.

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `file` | arquivo | — | PDF |
| `dpi` | int | 300 | 150–400 |
| `lang` | string | `por` | Idioma Tesseract |

Resposta: `.txt` para download. Headers extras: `X-OCR-Pages`, `X-Text-Pages`.

```bash
curl -F "file=@processo.pdf" http://localhost:8080/api/ocr/pdf -o processo.txt
```

### `POST /api/ocr/image`

OCR direto em imagem. Resposta JSON.

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `file` | arquivo | — | png/jpg/jpeg/tif/tiff/bmp/webp |
| `lang` | string | `por` | Idioma |
| `psm` | int | 6 | Segmentação: 3=auto, 6=bloco, 11=esparso |

```bash
curl -F "file=@scan.png" http://localhost:8080/api/ocr/image
# {"arquivo":"scan.png","largura":1200,"altura":300,"idioma":"por","texto":"..."}
```

### `POST /api/check`

Diagnóstico rápido (< 1s): o PDF precisa de OCR?

```bash
curl -F "file=@doc.pdf" http://localhost:8080/api/check
# {"legible":true,"total_pages":5,"sample_text":"...","reason":"..."}
```

---

## Conversões

### `POST /api/convert/images-to-pdf`

Junta imagens em um PDF. Campo `files` (múltiplos), na ordem enviada.

```bash
curl -F "files=@f1.png" -F "files=@f2.jpg" http://localhost:8080/api/convert/images-to-pdf -o saida.pdf
```

### `POST /api/convert/pdf-to-images`

Renderiza páginas como imagens. Retorna `.zip`.

| Campo | Default | Descrição |
|-------|---------|-----------|
| `file` | — | PDF |
| `dpi` | 200 | Resolução |
| `fmt` | `png` | `png` ou `jpg` |
| `pages` | todas | Ex.: `1-3,7` |

### `POST /api/convert/merge`

Junta PDFs. Campo `files` (mínimo 2).

```bash
curl -F "files=@a.pdf" -F "files=@b.pdf" http://localhost:8080/api/convert/merge -o merged.pdf
```

### `POST /api/convert/split`

Extrai páginas. Campos: `file`, `pages` (ex.: `1-3,7`).

### `POST /api/convert/compress`

Comprime o PDF. Campos: `file`, `qualidade` (10–95, default 60).
Header da resposta: `X-Reducao-Pct`.

### `POST /api/convert/rotate`

Gira páginas. Campos: `file`, `graus` (90/180/270), `pages` (opcional).

### `POST /api/convert/watermark`

Marca d'água de texto. Campos: `file`, `texto`.

### `POST /api/convert/pdf-to-docx`

Converte para Word. Campos: `file`, `pages` (opcional, range contínuo).

### `POST /api/convert/pdf-to-txt`

Alias de `/api/ocr/pdf`.

### `POST /api/convert/extract-images`

Extrai imagens embutidas. Retorna `.zip` (ou JSON `{"imagens": 0}`).

---

## Erros

| HTTP | Significado |
|------|-------------|
| 413 | Arquivo maior que o limite |
| 422 | Input inválido (formato, páginas, parâmetros) |
| 500 | Erro interno de processamento |

Corpo: `{"detail": "mensagem de erro"}`

## Exemplo em Python

```python
import requests

# OCR de PDF
with open("processo.pdf", "rb") as f:
    r = requests.post("http://localhost:8080/api/ocr/pdf", files={"file": f})
r.raise_for_status()
open("processo.txt", "wb").write(r.content)
print(f"Páginas via OCR: {r.headers.get('X-OCR-Pages')}")

# Diagnóstico
with open("processo.pdf", "rb") as f:
    info = requests.post("http://localhost:8080/api/check", files={"file": f}).json()
print(info["legible"], "-", info["reason"])
```
