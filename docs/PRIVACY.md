# Privacy Policy — OCR Beans plugin

**Last updated: 2026-10-16**

OCR Beans (the "plugin") processes documents **entirely on your machine**.

## What we collect

**Nothing.** The plugin:

- makes **zero network requests** — no telemetry, no analytics, no crash reports, no phoning home;
- stores no data on any server — there is no BeansTech server involved in the plugin's operation;
- does not read any file other than the ones you explicitly pass to its tools.

## What stays on your machine

Everything: the documents you process (PDFs, images), the extracted text, and
any `.txt` files the tools save are written to your local disk only.

## Dependencies downloaded on first run

The plugin's manifest launches it via `uv run`, which downloads the pinned
Python packages (`pymupdf==1.28.2`, `pytesseract==0.3.13`, `Pillow==12.3.0`,
`mcp==2.3.0`) and a managed Python 3.12 interpreter from public package
repositories. This happens once, is cached, and involves only package names —
never your documents.

## Third-party components

- **Tesseract OCR** (Apache 2.0) — if installed on your system, it runs locally;
- **PyMuPDF** (AGPL/commercial) — runs locally;
- neither sends data anywhere.

## Contact

BeansTech — https://beanstech.io
