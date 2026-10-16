# CLI — ocr-beans

Se instalou com `pip install .`, o comando `ocr-beans` fica disponível.
Sem instalar, use `python -m ocr_beans.cli` a partir da pasta do projeto.

## OCR

```bash
# Extrair texto de PDF (nativo ou OCR automático)
ocr-beans pdf processo.pdf                      # salva processo.txt ao lado
ocr-beans pdf processo.pdf -o saida.txt
ocr-beans pdf processo.pdf --paginas 1-5,8      # páginas específicas
ocr-beans pdf processo.pdf --dpi 200 --lang por

# OCR de imagem (imprime no terminal)
ocr-beans imagem scan.png
ocr-beans imagem foto.jpg --lang por --psm 6

# Diagnóstico: o PDF precisa de OCR? (JSON)
ocr-beans check processo.pdf
```

## Conversões

```bash
# Juntar PDFs
ocr-beans juntar a.pdf b.pdf c.pdf -o merged.pdf

# Extrair páginas
ocr-beans dividir doc.pdf --paginas 1-3,7 -o trecho.pdf

# Comprimir (recompacta imagens embutidas)
ocr-beans comprimir doc.pdf -o pequeno.pdf --qualidade 60

# Girar páginas
ocr-beans girar doc.pdf --graus 90 -o girado.pdf            # todas
ocr-beans girar doc.pdf --graus 180 --paginas 2-4 -o g.pdf  # só algumas

# Marca d'água
ocr-beans marca-dagua doc.pdf --texto "CONFIDENCIAL" -o marcado.pdf

# PDF -> imagens (zip)
ocr-beans pdf-para-imagens doc.pdf -o pags.zip --dpi 200 --fmt png
ocr-beans pdf-para-imagens doc.pdf -o capa.zip --paginas 1 --dpi 300

# Imagens -> PDF
ocr-beans imagens-para-pdf pag1.png pag2.jpg -o documento.pdf

# PDF -> Word
ocr-beans pdf-para-docx doc.pdf -o editavel.docx

# Extrair imagens embutidas
ocr-beans extrair-imagens doc.pdf -o imagens.zip
```

## Códigos de saída

| Código | Significado |
|--------|-------------|
| 0 | Sucesso |
| 1 | Uso incorreto (falta de argumentos) |
| 2 | Erro de processamento (arquivo não encontrado, formato inválido etc.) |

## Observações

- Caminhos com `..` são rejeitados por segurança — use caminhos absolutos ou relativos simples.
- Em PDFs com texto nativo legível, o OCR não é aplicado (resultado instantâneo).
  O OCR só entra quando a fonte é corrompida ou a página é imagem.
