# OCR Beans

**Extrator de texto de processos judiciais brasileiros — via MCP (Claude, ZCode e qualquer cliente MCP), CLI, API web e app desktop.**

PDFs de tribunais brasileiros (TJ-SP, TRT, STJ) frequentemente usam fontes
proprietárias que **nenhuma IA consegue ler**: aparentam ter texto, mas a
extração devolve lixo. O OCR Beans detecta automaticamente essas fontes
corrompidas e aplica OCR **somente onde precisa** — o resto sai do texto
nativo, instantâneo e perfeito.

**100% offline. Nenhum dado do processo sai da máquina. LGPD por construção.**

## Instalação como plugin MCP (Claude Code / Cowork / ZCode)

Os manifests estão na raiz deste repositório (`.claude-plugin/` e
`.zcode-plugin/`) — aponte o marketplace ou adicione direto:

```bash
# Claude Code (local, sem servidor):
claude mcp add ocr-beans -- uv run --no-project --python 3.12 \
  --with pymupdf==1.28.2 --with pytesseract==0.3.13 \
  --with Pillow==12.3.0 --with mcp==2.3.0 \
  python3 ocr_beans/mcp_server.py
```

O `uv` (um bin único) provisiona o Python 3.12 e as dependências
automaticamente na primeira execução. Tesseract é opcional: sem ele o texto
nativo funciona; para páginas escaneadas, `apt install tesseract-ocr
tesseract-ocr-por` (Linux), `brew install tesseract tesseract-lang` (macOS)
ou o instalador UB-Mannheim (Windows, marcar *Portuguese*).

## Ferramentas (MCP)

| Tool | O que faz |
|---|---|
| `check_legibility` | Diagnóstico em < 1s: o PDF precisa de OCR? |
| `ocr_pdf` | Processo inteiro; ≤30 págs devolve o texto, maiores salvam .txt + resumo |
| `ocr_page` | Páginas específicas ("1-5", "3,7,9") — para processos de milhares de fls. |
| `ocr_image` | Prints de decisões, fotos de documentos, scans avulsos |
| `batch_ocr` | Pasta inteira de PDFs (até 50 por vez) |

Cada página sai marcada como `TEXTO` ou `OCR`, com o número da folha
(`fls. N`) pronto para citação em petição.

## Qualidade — números medidos, não estimados

- **475/475 páginas** com decisão e conteúdo 100% idênticos ao motor do
  executável original (OCRBeans.exe) — comparação página a página em
  processos reais do TJSP; motor conferido contra o bytecode do `.exe`
  (29 funções, idênticas)
- **20 páginas/segundo** em texto nativo · **1,76 s por página** corrompida
  (Tesseract 300 DPI, `por`, `--psm 6`)
- **Determinístico**: mesmo arquivo, mesmo texto — sem alucinação de acentos
  (modelos de visão erraram "DE DIREito" e "JUNDIAI" nesta mesma página que
  o motor extrai perfeita)
- Segurança: validação de caminho anti-traversal, limites de DPI/páginas/
  tamanho/tamanho de lote, **zero chamadas de rede** no código
- Bateria de produção 16/16 (autenticação, 5 tools, rejeições de segurança,
  concorrência) no conector remoto

## Conector remoto (opcional)

Para quem prefere zero instalação: `https://mcp.beanstech.io/mcp` (MCP
Streamable HTTP, autenticação OIDC/Keycloak, hospedado em São Paulo —
território nacional). O plugin local **não depende** dele.

## O que mais está incluído

| Interface | Uso | Público |
|-----------|-----|---------|
| **MCP Server** | tools para Claude Code / agentes AI | Agentes AI |
| **API Web** | `ocr-beans-api` — UI estilo iLovePDF + REST em `/api/*` | Programas e humanos |
| **CLI** | `ocr_beans <comando>` — terminal | Scripts e automação |
| **App Desktop** | `ocr_beans_app.py` — GUI (Windows/macOS/Linux; `.exe` com Tesseract embutido via `OCR Beans.spec`) | Usuário final |

### Conversões de PDF (estilo iLovePDF)
- Imagens → PDF · PDF → imagens (zip por página) · PDF → Word (DOCX)
- Juntar, dividir, extrair páginas, girar, comprimir (−33,6% medido em
  contrato real), marca d'água, extrair imagens embutidas

## Instalação da suíte completa

```bash
# Linux
sudo apt install tesseract-ocr tesseract-ocr-por
pip install .            # ou: pip install -r requirements.txt

# Docker (MCP remoto / API)
docker build -t ocr-beans . && docker run -p 8080:8080 ocr-beans
```

Docs completas em `docs/` (API, CLI, MCP, instalação, arquitetura, privacidade).

## Licença

MIT — ver [LICENSE](LICENSE). Dependências: PyMuPDF (AGPL/comercial),
Tesseract (Apache-2.0), Pillow (HPND), MCP SDK (MIT).

---

**BeansTech** · https://beanstech.io
