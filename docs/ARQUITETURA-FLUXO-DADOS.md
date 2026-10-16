# OCR Beans — Arquitetura e Fluxo de Dados (v2.0.0)

Análise técnica do pacote `ocr_beans/` e do pipeline que o consome.
Gerada em 2026-10-11. Fontes: código-fonte lido diretamente + logs do workspace.

---

## 1. Visão geral em camadas

```
┌─────────────────────────── CAMADA DE ENTRADA (4 interfaces) ───────────────────────┐
│ MCP Server            API FastAPI            CLI                  App Desktop      │
│ mcp_server.py         api.py + webui.py      cli.py                ocr_beans_app.py │
│ 5 tools stdio/HTTP    13 rotas REST + UI     12 subcomandos        Tkinter/PyInst.  │
│ (agentes AI)          (humanos+programas)    (scripts)             (legado)         │
└────────────┬──────────────────┬──────────────────┬────────────────────┬────────────┘
             │                  │                  │                    │
┌────────────▼──────────────────▼──────────────────▼────────────────────▼────────────┐
│                          CAMADA DE VALIDAÇÃO / SEGURANÇA                             │
│  security.py (extensão, tamanho, DPI 150–400, ≤100 págs, ≤50 batch)                 │
│  convert.py::_resolve_input/_resolve_output/_open_checked (anti-traversal, realpath) │
│  api.py::_nome_seguro + _contido_no_workdir (uploads confinados a tmpdir efêmero)    │
└────────────┬─────────────────────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────────────────────┐
│                              CAMADA DE MOTOR (núcleo)                                 │
│  core.py    — OCR: PyMuPDF (render/extração) + Tesseract (pytesseract)               │
│               heurística texto_legivel() decide TEXTO nativo vs OCR por página       │
│  convert.py — conversões: pypdf (merge/split), PyMuPDF (imagens, compress, girar,    │
│               marca-d'água, extrair-imagens), img2pdf (imagens→PDF), pdf2docx (DOCX) │
└────────────┬─────────────────────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────────────────────┐
│                       DEPENDÊNCIAS EXTERNAS (binário/bibliotecas)                     │
│  Tesseract OCR (binário de sistema, descoberto por env/MEIPASS/caminhos/PATH)        │
│  PyMuPDF, Pillow, pytesseract, pypdf, img2pdf, pdf2docx,                             │
│  FastAPI + uvicorn + python-multipart, MCP SDK (1.x e 2.x), anyio                    │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

**Ponto-chave:** o pacote **não faz chamadas de rede** — todo o processamento é
local (PyMuPDF + Tesseract). As "integrações externas" são o protocolo MCP,
o servidor HTTP da API e o ecossistema de deploy (Docker/Cloud Run/PyInstaller).

---

## 2. Fluxo de dados — OCR de PDF (o caminho crítico)

```
Entrada                Motor                        Saída
──────                 ─────                        ──────
caminho do PDF  ──►  validate_path()        ──►  fitz.open(pdf)
                     validate_dpi(150–400)        │
                     validate_pdf_size(≤200MB)    ▼
                                          extrai texto NATIVO da pág. 1
                                                  │
                                          texto_legivel(text) ── heurística:
                                          • ≥30 chars, ≤5% ctrl chars
                                          • ≥40% letras, ≥5% espaços
                                          • ≥2 palavras comuns pt-BR ("de","da",
                                            "que","não","são"...)
                                                  │
                        ┌── ilegível ─────────────┤───────────── legível ──┐
                        ▼                                                  ▼
                  forcar_ocr = TRUE                            por página: get_text()
                  (todas as páginas via OCR)                   se legível → TEXTO,
                        │                                      senão → OCR da página
                        ▼                                                  │
              get_pixmap(dpi=300) ──► PNG em memória ──► PIL.Image ◄───────┘
                        │
                        ▼
              pytesseract.image_to_string(lang="por", psm=6)
              (fallback automático p/ "eng" se 'por' ausente)
                        │
                        ▼
        dict estruturado: {path, total_pages, ocr_pages, text_pages,
                           pages:[{number, source:TEXTO|OCR|ERRO, content}]}
                        │
        ┌───────────────┼───────────────────┬──────────────────────┐
        ▼               ▼                   ▼                      ▼
   MCP: texto      API: .txt download   CLI: .txt ao lado    App: .txt + log
   "PÁGINA n       + headers X-OCR-     + stdout               por arquivo
   (OCR/TEXTO)"    Pages/X-Text-Pages
   + "fls. n"
```

Erros de OCR por página não abortam o documento: `_ocr_safe()` devolve
`source="ERRO"` com a mensagem embutida no texto (graceful degradation).

### Estratégia de resposta do MCP (controle de tokens para agentes)
- PDF ≤ 30 páginas **e** ≤ 100.000 chars → texto completo **inline**.
- Acima disso → salva `.txt` ao lado do PDF e retorna **resumo + previews**
  (primeira/última página) + instrução para usar `ocr_page` sob demanda.
- `ocr_page` aceita range ("1-5", "1,3,7"), máx. 100 páginas/request.
- `batch_ocr` processa diretório (máx. 50 PDFs), um `.txt` por arquivo,
  sempre retorna resumo OK/ERRO por arquivo.
- Todo trabalho pesado roda em `anyio.to_thread.run_sync` — o event loop do
  MCP/API nunca bloqueia (o motor em si é síncrono e sequencial por página).

---

## 3. Fluxo de dados — API REST (upload em memória/disco)

```
multipart/form-data
   │  _nome_seguro(): basename + regex (sem chars perigosos)
   │  prefixo uuid4 no nome → sem colisão
   ▼
_WORKDIR = tempfile.mkdtemp()          ← confinamento: _contido_no_workdir()
   │  grava em chunks de 1MB, aborta >200MB (OCR_BEANS_MAX_UPLOAD_MB)
   ▼
qualquer função de core.py/convert.py via anyio.to_thread
   │
   ▼
FileResponse (anexo p/ download)  |  JSONResponse (ocr/image, check, /api/health)
```

- Estado **efêmero**: workdir some com o processo; não há persistência nem fila.
- `/api/health` reporta disponibilidade do Tesseract e idiomas instalados —
  descoberta de capacidades para clientes.
- `/api/tools` é um catálogo programático de rotas + limites (auto-descrição).
- **Sem autenticação embutida** (decisão documentada: auth fica no reverse
  proxy / IAP / Cloud Run `--no-allow-unauthenticated`).

---

## 4. Componentes, um por um

| Arquivo | Papel | Entradas | Saídas |
|---|---|---|---|
| `ocr_beans/core.py` | Motor OCR + heurística de legibilidade | PDF, imagem, DPI, lang | dicts estruturados por página |
| `ocr_beans/convert.py` | 10 conversões de PDF/imagem | caminhos validados internamente | caminho do output (+ métricas em compress/extract) |
| `ocr_beans/security.py` | Limite de recursos + validação de tipos | paths/params crus | paths resolvidos ou exceção |
| `ocr_beans/mcp_server.py` | 5 tools MCP (stdio/streamable-http) | chamadas JSON-RPC de agentes | texto formatado p/ LLM / resumo+arquivo |
| `ocr_beans/api.py` | 13 rotas REST FastAPI | uploads multipart | arquivos download ou JSON |
| `ocr_beans/webui.py` | SPA single-file (sem CDN) servida em `/` | cliques do usuário | fetch para as rotas REST |
| `ocr_beans/cli.py` | argparse com 12 subcomandos | argv | stdout + arquivos |
| `ocr_beans_app.py` (raiz) | GUI Tkinter **legado v1** | file dialogs | .txt + logs em `logs/` |
| `ocr_pdf.py`, `ocr_pdf_batch.py` (raiz) | Scripts **legados v1** com lógica duplicada | argv | .txt |

### Descoberta do Tesseract (core.py::encontrar_tesseract)
Ordem: `TESSERACT_CMD` (env) → embutido PyInstaller (`_MEIPASS/tesseract/`)
→ caminhos padrão por SO (Program Files / brew / /usr/bin / snap) → `PATH`.
Isso é o que torna o `.exe` do app autocontido e o Docker simples.

---

## 5. Integrações externas e deploy

1. **MCP (Model Context Protocol)** — `mcp>=1.0.0`; compatibilidade dual com
   SDK 1.x (`FastMCP`) e 2.x (`MCPServer`) resolvida em runtime por try/except.
   Transporte stdio (local) e streamable-http (`--remote --port`).
   Já plugado no BeansCode via `~/.beanscode.json` (memória global).
2. **Docker** — `Dockerfile`: python:3.11-slim + `tesseract-ocr` +
   `tesseract-ocr-por`; CMD sobe a API na 8080; modo MCP remoto documentado.
3. **GCP Cloud Run** — deploy direto (`gcloud run deploy --source .`),
   2Gi/2CPU/timeout 300s, sem auth pública (IAM na frente).
4. **PyInstaller** — `OCR Beans.spec` gera binário Windows com Tesseract
   embutido para o app desktop.
5. **Pipeline jurídico "ativos.ai / Beans Tech"** (consumidor a jusante, fora
   do pacote — ver `manifest.json`, `pipeline.log`, `pipeline-gpu.log`):
   `914 PDFs → extracoes/*.txt (OCR Beans) → entidades/*.json (LLM granite4.1:30b
   via GPU própria, endpoint HTTP) → cruzamentos/ (CPF/CNPJ/valores) →
   rastreamento/ (DataJud, RAGJur, blockchain) → ragjur/precedentes.json
   (182 precedentes, 70,6M de docs indexados) → mdx_output/ (artigos)`.
   O OCR Beans é o **portão de entrada** dessa cadeia: nada a jusante funciona
   se a extração de texto falhar.

---

## 6. Gaps e riscos técnicos identificados

| # | Achado | Impacto | Onde |
|---|---|---|---|
| 1 | **Zero testes automatizados** (nenhum `test_*.py` no repo) | regressões silenciosas na heurística e nas rotas | global |
| 2 | Heurística decide `forcar_ocr` só pela **página 1**; PDF com pág. 1 corrompida faz OCR em tudo (lento) — e PDF misto depende do recheck por página | performance/qualidade | `core.py::processar_pdf` |
| 3 | `pdf_para_docx` com páginas não contíguas converte o **intervalo min–max** inteiro (ex.: "1,10" → 10 páginas) | resultado inesperado | `convert.py:358-364` |
| 4 | Workdir da API nunca é podado durante a vida do processo (uploads abortados ficam em disco) | disco cresce em serviço longo | `api.py::_salvar_upload` |
| 5 | MCP usa **caminhos de arquivo do host** — no modo `--remote` o cliente precisa de sistema de arquivos compartilhado com o servidor | limitação de arquitetura p/ cloud | `mcp_server.py` |
| 6 | `ocr_pdf` (MCP) não expõe `lang`; API expõe mas o default do motor é `por` fixo em alguns caminhos | consistência | `mcp_server.py:118` |
| 7 | Scripts legados v1 (`ocr_pdf.py`, `ocr_pdf_batch.py`, `ocr_beans_app.py`) duplicam a heurística com caminho Windows hardcoded — divergem do pacote | manutenção | raiz |
| 8 | Processamento **sequencial por página** (sem paralelismo) — 914 PDFs levaram ~15s só em texto nativo, mas OCR real é linear e lento | throughput | `core.py` |
| 9 | Sem rate limiting/CORS configurado na API; bind `0.0.0.0` default no Docker | exposição acidental | `api.py::main` |

---

## 7. Resumo executivo

OCR Beans 2.0.0 é um pacote **motor único + 4 fachadas** (MCP, REST, CLI, GUI):
toda a lógica de OCR vive em `core.py`/`convert.py`, com validação centralizada
em `security.py` e nos guardas de path de `convert.py`. O diferencial técnico é
a **heurística de legibilidade em português jurídico**, que evita OCR quando o
texto nativo é bom e o aciona quando fontes proprietárias de tribunais corrompem
a extração — decisão tomada na página 1 e revalidada página a página. A saída é
sempre um dict estruturado por página (`source: TEXTO|OCR|ERRO`), que cada
fachada formata conforme seu público: texto marcado com "fls. N" para agentes
MCP (com fallback arquivo+resumo acima de 30 págs/100k chars para poupar
tokens), `.txt`/`.zip`/JSON com headers de métricas para REST, e stdout para CLI.
Não há dependência de nuvem dentro do pacote; as integrações externas são o
protocolo MCP, o stack Docker/Cloud Run, o empacotamento PyInstaller e, a
jusante, o pipeline jurídico do workspace (extração → entidades via GPU →
cruzamentos → RAGJur → artigos), do qual o OCR Beans é o primeiro elo.
