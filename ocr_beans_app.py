"""
OCR Beans - Extrator de Texto de PDFs
BeansTech 2026

Aplicativo com interface grafica para extracao de texto de PDFs,
com deteccao automatica de fontes corrompidas (comum em PDFs judiciais).
"""

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import logging
import os
import re
import subprocess
import sys
import glob
import shutil
import unicodedata
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# ---------------------------------------------------------------------------
# Diretorio base (compativel com PyInstaller .exe)
# ---------------------------------------------------------------------------
def _app_dir():
    """Retorna o diretorio do app — funciona tanto como .py quanto como .exe."""
    if getattr(sys, 'frozen', False):
        # Executavel PyInstaller: usa a pasta onde o .exe esta
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = _app_dir()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("ocr_beans")
logger.setLevel(logging.DEBUG)

# Handler para arquivo de log (rotativo por sessao)
_log_dir = os.path.join(APP_DIR, "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, f"ocr_beans_{datetime.now():%Y%m%d_%H%M%S}.log")
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
))
logger.addHandler(_file_handler)

# ---------------------------------------------------------------------------
# Configuracao do Tesseract
# ---------------------------------------------------------------------------

def _meipass():
    """Retorna o diretorio de recursos do PyInstaller, se existir."""
    return getattr(sys, '_MEIPASS', None)


def encontrar_tesseract():
    """
    Procura o executavel do Tesseract na seguinte ordem:
    1. Variavel de ambiente TESSERACT_CMD
    2. Embutido no app (PyInstaller _MEIPASS/tesseract/)
    3. Instalacao padrao do sistema operacional (Windows/macOS/Linux)
    4. PATH do sistema
    Retorna (caminho_exe, caminho_tessdata) ou (None, None).
    """
    # 1. Variavel de ambiente
    env_cmd = os.environ.get('TESSERACT_CMD')
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd, os.environ.get('TESSDATA_PREFIX')

    # 2. Embutido no app
    meipass = _meipass()
    if meipass:
        exe_name = 'tesseract.exe' if sys.platform == 'win32' else 'tesseract'
        bundled = os.path.join(meipass, 'tesseract', exe_name)
        bundled_data = os.path.join(meipass, 'tesseract', 'tessdata')
        if os.path.isfile(bundled):
            logger.info("Tesseract embutido encontrado: %s", bundled)
            return bundled, bundled_data

    # 3. Instalacao padrao por SO
    caminhos = []
    if sys.platform == 'win32':
        caminhos += [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Tesseract-OCR', 'tesseract.exe'),
        ]
    elif sys.platform == 'darwin':
        caminhos += [
            '/opt/homebrew/bin/tesseract',  # Apple Silicon (brew)
            '/usr/local/bin/tesseract',     # Intel (brew)
            '/opt/local/bin/tesseract',     # MacPorts
        ]
    else:  # Linux e outros Unix
        caminhos += [
            '/usr/bin/tesseract',
            '/usr/local/bin/tesseract',
            '/snap/bin/tesseract',
        ]
    for c in caminhos:
        if c and os.path.isfile(c):
            return c, None

    # 4. PATH do sistema
    found = shutil.which('tesseract')
    if found:
        return found, None

    return None, None


def abrir_pasta(pasta):
    """Abre uma pasta no gerenciador de arquivos do SO (Windows/macOS/Linux)."""
    try:
        if sys.platform == 'win32':
            os.startfile(pasta)  # type: ignore[attr-defined]  # Windows-only
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', pasta])
        else:
            subprocess.Popen(['xdg-open', pasta])
    except Exception as e:
        logger.error("Nao foi possivel abrir a pasta %s: %s", pasta, e)


TESSERACT_PATH, TESSDATA_PATH = encontrar_tesseract()
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
if TESSDATA_PATH:
    os.environ['TESSDATA_PREFIX'] = TESSDATA_PATH


def _dica_instalacao_tesseract():
    """Instrucoes de instalacao do Tesseract conforme o SO."""
    if sys.platform == 'win32':
        return ("Instale em: C:\\Program Files\\Tesseract-OCR\\\n"
                "Download: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "(marque 'Portuguese' nos idiomas)")
    if sys.platform == 'darwin':
        return "Instale com: brew install tesseract tesseract-lang"
    return "Instale com: sudo apt install tesseract-ocr tesseract-ocr-por"


# ---------------------------------------------------------------------------
# Motor de OCR (compartilhado entre modo unitario e batch)
# ---------------------------------------------------------------------------

def texto_legivel(text):
    """
    Verifica se o texto extraido pelo PyMuPDF e legivel ou se e lixo
    causado por fontes com encoding proprietario (comum em PDFs judiciais).

    Criterios:
    - Proporcao minima de letras e espacos vs caracteres totais
    - Presenca de palavras comuns em portugues
    - Ausencia excessiva de caracteres de controle
    """
    if len(text) < 30:
        return False

    controle = sum(1 for c in text if unicodedata.category(c).startswith('C')
                   and c not in '\n\r\t')
    if controle > len(text) * 0.05:
        return False

    letras = sum(1 for c in text if c.isalpha())
    espacos = sum(1 for c in text if c == ' ')
    total = len(text)

    if total == 0:
        return False

    if letras / total < 0.40 or espacos / total < 0.05:
        return False

    palavras_comuns = [
        r'\bde\b', r'\bdo\b', r'\bda\b', r'\bdos\b', r'\bdas\b',
        r'\bque\b', r'\bem\b', r'\bno\b', r'\bna\b', r'\bnos\b',
        r'\bpor\b', r'\bcom\b', r'\bpara\b', r'\buma\b', r'\bse\b',
        r'\bnão\b', r'\bou\b', r'\bao\b', r'\bà\b', r'\be\b',
        r'\bser\b', r'\bfoi\b', r'\bsão\b', r'\best[aá]\b',
    ]
    texto_lower = text.lower()
    matches = sum(1 for p in palavras_comuns if re.search(p, texto_lower))

    return matches >= 2


def ocr_pagina(page):
    """Renderiza a pagina como imagem a 300 DPI e aplica OCR via Tesseract."""
    pix = page.get_pixmap(dpi=300)
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))
    return pytesseract.image_to_string(img, lang='por', config='--psm 6')


IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp')


def _abrir_saida(path: str, mode: str = 'w'):
    """Abre arquivo de saida com validacao inline: sem '..' nem nulos, pasta existente."""
    if not path or "\x00" in path or ".." in path.replace("\\", "/").split("/"):
        raise ValueError(f"Caminho de saida invalido: {path!r}")
    resolved = os.path.realpath(os.path.expanduser(path))
    if "r" in mode:
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
    else:
        parent = os.path.dirname(resolved)
        if not parent or not os.path.isdir(parent):
            raise ValueError(f"Diretorio de saida nao existe: {path}")
    return open(resolved, mode, encoding='utf-8' if "b" not in mode else None)


def processar_imagem(img_path, output_path):
    """
    Aplica OCR direto em um arquivo de imagem e salva o texto.
    Retorna (sucesso: bool, mensagem: str).
    """
    filename = os.path.basename(img_path)

    try:
        src = _abrir_saida(img_path, 'r')
        src.close()
        img = Image.open(img_path)
        img.load()
        if img.mode not in ('L', 'RGB'):
            img = img.convert('RGB')
        # Upscale de imagens pequenas melhora o Tesseract
        w, h = img.size
        work = img
        if max(w, h) < 1500:
            fator = 1500 / max(w, h)
            work = img.resize((int(w * fator), int(h * fator)), Image.LANCZOS)
        text = pytesseract.image_to_string(work.convert('L'), lang='por', config='--psm 6')
        img.close()
    except Exception as e:
        logger.error("Erro no OCR de imagem %s: %s", filename, e)
        return False, f"Erro no OCR de {filename}: {e}"

    header = [
        '=' * 70,
        f"IMAGEM: {filename}",
        f"PROCESSADO EM: OCR Beans (Tesseract)",
        f"DATA: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        '=' * 70,
        '',
        text.strip(),
    ]
    try:
        with _abrir_saida(output_path, 'w') as f:
            f.write("\n".join(header))
    except Exception as e:
        logger.error("Erro ao salvar %s: %s", filename, e)
        return False, f"Erro ao salvar: {e}"

    tamanho_kb = os.path.getsize(os.path.realpath(output_path)) / 1024
    return True, f"Salvo: {os.path.basename(output_path)} ({tamanho_kb:.1f} KB)"


def processar_pdf(pdf_path, output_path, callback_log=None, callback_progresso=None):
    """
    Processa um unico PDF e salva o resultado como .txt.
    Retorna (sucesso: bool, mensagem: str).
    """
    def log(msg):
        logger.info(msg.strip())
        if callback_log:
            callback_log(msg)

    def progresso(atual, total):
        if callback_progresso:
            callback_progresso(atual, total)

    filename = os.path.basename(pdf_path)

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("Erro ao abrir %s: %s", filename, e)
        return False, f"Erro ao abrir {filename}: {e}"

    total_pages = len(doc)

    if total_pages == 0:
        logger.error("PDF sem paginas: %s", filename)
        doc.close()
        return False, f"PDF sem paginas: {filename}"

    log(f"  {total_pages} paginas")

    # Detecta fonte corrompida na primeira pagina
    texto_teste = doc[0].get_text("text").strip()
    forcar_ocr = not texto_legivel(texto_teste)

    if forcar_ocr:
        logger.warning("Fonte proprietaria detectada em %s", filename)
        log(f"  [!] Fonte proprietaria detectada - usando OCR")

    all_text = []
    all_text.append(f"{'='*70}")
    all_text.append(f"DOCUMENTO: {filename}")
    all_text.append(f"PROCESSADO EM: OCR Beans (PyMuPDF + Tesseract)")
    all_text.append(f"DATA: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    all_text.append(f"TOTAL DE PAGINAS: {total_pages}")
    all_text.append(f"{'='*70}\n")

    for page_num in range(total_pages):
        page = doc[page_num]

        if forcar_ocr:
            try:
                text = ocr_pagina(page)
                source = "OCR"
            except Exception as e:
                text = f"[ERRO NO OCR: {str(e)}]"
                source = "ERRO"
        else:
            text = page.get_text("text").strip()

            if texto_legivel(text):
                source = "TEXTO"
            else:
                try:
                    text = ocr_pagina(page)
                    source = "OCR"
                except Exception as e:
                    text = f"[ERRO NO OCR: {str(e)}]"
                    source = "ERRO"

        all_text.append(f"\n{'='*70}")
        all_text.append(f"PAGINA {page_num + 1} ({source})")
        all_text.append(f"{'='*70}")
        all_text.append(text)
        all_text.append(f"fls. {page_num + 1}")

        progresso(page_num + 1, total_pages)

    doc.close()

    final_text = "\n".join(all_text)
    with _abrir_saida(output_path) as f:
        f.write(final_text)

    tamanho_kb = os.path.getsize(output_path) / 1024
    return True, f"Salvo: {os.path.basename(output_path)} ({tamanho_kb:.1f} KB)"


# ---------------------------------------------------------------------------
# Interface Grafica
# ---------------------------------------------------------------------------

class OCRBeansApp:
    def __init__(self, root):
        self.root = root
        self.root.title("OCR Beans - Extrator de Texto de PDFs")
        self.root.geometry("750x580")
        self.root.resizable(True, True)
        self.root.minsize(600, 450)

        self.processando = False
        self.arquivos_selecionados = []

        self._criar_widgets()

    def _criar_widgets(self):
        # --- Frame principal ---
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Titulo ---
        titulo = ttk.Label(main, text="OCR Beans", font=("Segoe UI", 18, "bold"))
        titulo.pack(pady=(0, 2))
        subtitulo = ttk.Label(main, text="Extrator de texto de PDFs - BeansTech",
                              font=("Segoe UI", 9))
        subtitulo.pack(pady=(0, 12))

        # --- Tesseract status ---
        if TESSERACT_PATH:
            if TESSDATA_PATH:
                # Tesseract embutido no app
                status_tess = "Tesseract OCR: Integrado"
            else:
                # Instalacao local
                status_tess = f"Tesseract OCR: {TESSERACT_PATH}"
            cor = "green"
        else:
            status_tess = "Tesseract NAO encontrado! " + _dica_instalacao_tesseract()
            cor = "red"
        lbl_tess = ttk.Label(main, text=status_tess, foreground=cor, font=("Segoe UI", 8))
        lbl_tess.pack(pady=(0, 10))

        # --- Botoes de selecao ---
        frame_btns = ttk.Frame(main)
        frame_btns.pack(fill=tk.X, pady=(0, 8))

        self.btn_arquivos = ttk.Button(frame_btns, text="Selecionar PDFs",
                                       command=self._selecionar_arquivos)
        self.btn_arquivos.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_pasta = ttk.Button(frame_btns, text="Selecionar Pasta",
                                    command=self._selecionar_pasta)
        self.btn_pasta.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_processar = ttk.Button(frame_btns, text="Processar",
                                        command=self._iniciar_processamento)
        self.btn_processar.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_processar.state(['disabled'])

        self.btn_abrir_pasta = ttk.Button(frame_btns, text="Abrir Pasta de Saida",
                                          command=self._abrir_pasta_saida)
        self.btn_abrir_pasta.pack(side=tk.RIGHT)

        # --- Label de selecao ---
        self.lbl_selecao = ttk.Label(main, text="Nenhum arquivo selecionado",
                                     font=("Segoe UI", 9))
        self.lbl_selecao.pack(anchor=tk.W, pady=(0, 5))

        # --- Pasta de saida ---
        frame_saida = ttk.Frame(main)
        frame_saida.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(frame_saida, text="Salvar em:").pack(side=tk.LEFT)
        self.var_saida = tk.StringVar(value="(mesma pasta do PDF)")
        self.entry_saida = ttk.Entry(frame_saida, textvariable=self.var_saida, state='readonly')
        self.entry_saida.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_saida = ttk.Button(frame_saida, text="Alterar",
                                    command=self._selecionar_saida)
        self.btn_saida.pack(side=tk.LEFT)

        # --- Barra de progresso ---
        self.progresso = ttk.Progressbar(main, mode='determinate')
        self.progresso.pack(fill=tk.X, pady=(0, 5))

        self.lbl_progresso = ttk.Label(main, text="", font=("Segoe UI", 9))
        self.lbl_progresso.pack(anchor=tk.W, pady=(0, 5))

        # --- Log ---
        frame_log = ttk.LabelFrame(main, text="Log", padding=5)
        frame_log.pack(fill=tk.BOTH, expand=True)

        self.txt_log = tk.Text(frame_log, height=12, wrap=tk.WORD,
                               font=("Consolas", 9), state='disabled',
                               bg="#1e1e1e", fg="#d4d4d4",
                               insertbackground="#d4d4d4",
                               selectbackground="#264f78")
        scroll = ttk.Scrollbar(frame_log, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        self.pasta_saida_real = None

    # --- Acoes ---

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(
            title="Selecionar PDFs e imagens",
            filetypes=[
                ("PDFs e imagens", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
                ("Arquivos PDF", "*.pdf"),
                ("Imagens", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
            ],
        )
        if arquivos:
            self.arquivos_selecionados = list(arquivos)
            n = len(self.arquivos_selecionados)
            self.lbl_selecao.config(text=f"{n} arquivo(s) selecionado(s)")
            self.btn_processar.state(['!disabled'])

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecionar pasta com PDFs/imagens")
        if pasta:
            arquivos = sorted(glob.glob(os.path.join(pasta, '*.pdf')))
            for ext in IMAGE_EXTS:
                arquivos += glob.glob(os.path.join(pasta, f'*{ext}'))
            arquivos = sorted(set(arquivos))
            if not arquivos:
                messagebox.showwarning("Aviso", "Nenhum PDF ou imagem encontrado nesta pasta.")
                return
            self.arquivos_selecionados = arquivos
            n = len(arquivos)
            self.lbl_selecao.config(text=f"{n} arquivo(s) encontrado(s) em: {pasta}")
            self.btn_processar.state(['!disabled'])

    def _selecionar_saida(self):
        pasta = filedialog.askdirectory(title="Pasta de saida para os .txt")
        if pasta:
            self.pasta_saida_real = pasta
            self.var_saida.set(pasta)

    def _abrir_pasta_saida(self):
        if self.pasta_saida_real:
            abrir_pasta(self.pasta_saida_real)
        elif self.arquivos_selecionados:
            abrir_pasta(os.path.dirname(self.arquivos_selecionados[0]))

    def _log(self, msg):
        self.txt_log.configure(state='normal')
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state='disabled')

    def _atualizar_progresso_global(self, arquivo_idx, total_arquivos, pagina, total_paginas):
        # Progresso combinado: arquivos + paginas dentro do arquivo atual
        base = ((arquivo_idx - 1) / total_arquivos) * 100
        dentro = (pagina / total_paginas) * (100 / total_arquivos)
        valor = base + dentro
        self.progresso['value'] = min(valor, 100)
        self.lbl_progresso.config(
            text=f"Arquivo {arquivo_idx}/{total_arquivos} - "
                 f"Pagina {pagina}/{total_paginas}"
        )
        self.root.update_idletasks()

    def _iniciar_processamento(self):
        if self.processando:
            return
        if not TESSERACT_PATH:
            messagebox.showerror(
                "Tesseract nao encontrado",
                "O Tesseract OCR nao foi encontrado.\n\n" + _dica_instalacao_tesseract()
            )
            return

        self.processando = True
        self.btn_processar.state(['disabled'])
        self.btn_arquivos.state(['disabled'])
        self.btn_pasta.state(['disabled'])
        self.progresso['value'] = 0

        self.txt_log.configure(state='normal')
        self.txt_log.delete('1.0', tk.END)
        self.txt_log.configure(state='disabled')

        thread = threading.Thread(target=self._processar_todos, daemon=True)
        thread.start()

    def _processar_todos(self):
        arquivos = self.arquivos_selecionados
        total = len(arquivos)
        sucesso = 0
        erros = 0

        self._log_safe(f"Iniciando processamento de {total} arquivo(s)...\n")

        for idx, pdf_path in enumerate(arquivos, 1):
            filename = os.path.basename(pdf_path)
            self._log_safe(f"[{idx}/{total}] {filename}")

            # Determinar pasta de saida
            if self.pasta_saida_real:
                out_dir = self.pasta_saida_real
            else:
                out_dir = os.path.dirname(pdf_path)

            txt_name = os.path.splitext(filename)[0] + '.txt'
            output_path = os.path.join(out_dir, txt_name)

            # Guardar referencia para abrir pasta depois (via main thread)
            if not self.pasta_saida_real:
                self.root.after(0, self._setar_pasta_saida, out_dir)

            def cb_log(msg):
                self._log_safe(msg)

            def cb_progresso(pagina, total_paginas, _idx=idx, _total=total):
                self.root.after(0, self._atualizar_progresso_global,
                                _idx, _total, pagina, total_paginas)

            ext = os.path.splitext(pdf_path)[1].lower()
            if ext in IMAGE_EXTS:
                ok, msg = processar_imagem(pdf_path, output_path)
                cb_progresso(1, 1)
            else:
                ok, msg = processar_pdf(pdf_path, output_path, cb_log, cb_progresso)

            if ok:
                sucesso += 1
                self._log_safe(f"  {msg}\n")
            else:
                erros += 1
                self._log_safe(f"  ERRO: {msg}\n")

        self._log_safe(f"{'='*50}")
        self._log_safe(f"Concluido! {sucesso} processado(s), {erros} erro(s).")

        self.root.after(0, self._finalizar_processamento)

    def _setar_pasta_saida(self, pasta):
        """Seta pasta_saida_real na main thread (thread-safe)."""
        if not self.pasta_saida_real:
            self.pasta_saida_real = pasta

    def _log_safe(self, msg):
        """Thread-safe log."""
        self.root.after(0, self._log, msg)

    def _finalizar_processamento(self):
        self.processando = False
        self.progresso['value'] = 100
        self.lbl_progresso.config(text="Concluido!")
        self.btn_processar.state(['!disabled'])
        self.btn_arquivos.state(['!disabled'])
        self.btn_pasta.state(['!disabled'])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()

    # Icone do app (busca embutido no .exe ou na pasta do script)
    try:
        meipass = getattr(sys, '_MEIPASS', None)
        icon_candidates = []
        if meipass:
            icon_candidates.append(os.path.join(meipass, 'ocr_beans.ico'))
        icon_candidates.append(os.path.join(APP_DIR, 'ocr_beans.ico'))
        for icon_path in icon_candidates:
            if os.path.isfile(icon_path):
                root.iconbitmap(icon_path)
                break
    except Exception:
        pass

    # Estilo
    style = ttk.Style()
    style.theme_use('clam')

    app = OCRBeansApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
