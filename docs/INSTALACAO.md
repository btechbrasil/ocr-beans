# Instalação — Linux, Windows e macOS

O OCR Beans tem duas dependências: **Python 3.11+** e **Tesseract OCR** (com idioma português).

---

## Linux

### Debian / Ubuntu / Mint

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-por python3-pip
pip install -r requirements.txt        # dentro da pasta do projeto
# ou, para instalar como comando do sistema:
pip install .
```

### Fedora

```bash
sudo dnf install tesseract tesseract-langpack-por
pip install -r requirements.txt
```

### Arch

```bash
sudo pacman -S tesseract tesseract-data-por
pip install -r requirements.txt
```

### Verificar

```bash
tesseract --version
tesseract --list-langs        # deve listar "por"
ocr-beans --version           # se instalou com pip install .
```

---

## macOS

Via Homebrew (recomendado):

```bash
brew install tesseract tesseract-lang
brew install python@3.11      # se ainda não tiver
pip3 install -r requirements.txt
```

O OCR Beans procura o Tesseract automaticamente em:
- `/opt/homebrew/bin/tesseract` (Apple Silicon)
- `/usr/local/bin/tesseract` (Intel)
- `/opt/local/bin/tesseract` (MacPorts)

### Verificar

```bash
tesseract --list-langs        # deve listar "por"
```

---

## Windows

### 1. Tesseract

1. Baixe o instalador: https://github.com/UB-Mannheim/tesseract/wiki
2. Durante a instalação, **marque "Portuguese"** em *Additional language data*
3. Instale no caminho padrão: `C:\Program Files\Tesseract-OCR\`

Se instalou em outro lugar, defina a variável de ambiente:

```powershell
setx TESSERACT_CMD "C:\caminho\para\tesseract.exe"
```

### 2. Python

```powershell
pip install -r requirements.txt
```

### Verificar

```powershell
tesseract --version
```

---

## App Desktop com Tesseract embutido (Windows)

Para distribuir sem exigir instalação do Tesseract:

```powershell
python -m PyInstaller "OCR Beans.spec" --noconfirm
```

Gera `dist/OCR Beans.exe` com Tesseract + idiomas embutidos.

---

## Docker (qualquer SO)

```bash
docker build -t ocr-beans .
docker run -p 8080:8080 ocr-beans
```

A imagem já inclui Tesseract + português. Acesse http://localhost:8080/

---

## Solução de problemas

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `Tesseract não encontrado` | Não está no PATH nem no local padrão | Defina `TESSERACT_CMD` com o caminho completo |
| `Failed loading language 'por'` | Idioma não instalado | Instale `tesseract-ocr-por` (Linux), `tesseract-lang` (Mac) ou reinstale marcando Portuguese (Windows) |
| OCR lento | Normal: ~1–2s por página a 300 DPI | Use `--dpi 200` para rascunhos |
| Resultado vazio em PDF | O PDF pode ser scan sem texto | Normal — o OCR será aplicado automaticamente |
