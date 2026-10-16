"""
OCR Beans - Interface web embutida (single-page, sem dependências externas).
Servida pela API em GET /.
"""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OCR Beans — Ferramentas de PDF e OCR</title>
<style>
  :root { --verde:#2e7d32; --verde-esc:#1b5e20; --cinza:#f4f5f7; --texto:#222; }
  * { box-sizing:border-box; margin:0; padding:0; font-family:'Segoe UI',system-ui,sans-serif; }
  body { background:var(--cinza); color:var(--texto); }
  header { background:linear-gradient(135deg,var(--verde),var(--verde-esc)); color:#fff;
           padding:28px 20px; text-align:center; }
  header h1 { font-size:2rem; }
  header p { opacity:.9; margin-top:6px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr));
          gap:16px; max-width:1100px; margin:28px auto; padding:0 20px; }
  .card { background:#fff; border-radius:12px; padding:20px; cursor:pointer;
          box-shadow:0 1px 4px rgba(0,0,0,.08); transition:transform .15s, box-shadow .15s;
          border-top:4px solid var(--verde); }
  .card:hover { transform:translateY(-3px); box-shadow:0 6px 16px rgba(0,0,0,.14); }
  .card h3 { font-size:1.05rem; margin-bottom:6px; }
  .card p { font-size:.85rem; color:#666; }
  .card .icone { font-size:1.6rem; margin-bottom:8px; }
  #painel { display:none; max-width:720px; margin:0 auto 40px; background:#fff;
            border-radius:12px; padding:28px; box-shadow:0 2px 10px rgba(0,0,0,.1); }
  #painel h2 { margin-bottom:4px; }
  #painel .desc { color:#666; font-size:.9rem; margin-bottom:18px; }
  .drop { border:2px dashed var(--verde); border-radius:10px; padding:34px;
          text-align:center; color:var(--verde-esc); cursor:pointer; margin-bottom:14px; }
  .drop.over { background:#e8f5e9; }
  .campo { margin-bottom:12px; }
  .campo label { display:block; font-size:.85rem; margin-bottom:4px; color:#444; }
  .campo input, .campo select { width:100%; padding:8px 10px; border:1px solid #ccc;
          border-radius:6px; font-size:.9rem; }
  button.acao { background:var(--verde); color:#fff; border:0; padding:12px 26px;
          border-radius:8px; font-size:1rem; cursor:pointer; width:100%; }
  button.acao:disabled { background:#9e9e9e; cursor:wait; }
  #status { margin-top:14px; font-size:.9rem; white-space:pre-wrap; }
  #status.erro { color:#c62828; }
  #status.ok { color:var(--verde-esc); }
  .voltar { background:none; border:0; color:var(--verde); cursor:pointer;
            margin-bottom:14px; font-size:.9rem; }
  footer { text-align:center; color:#999; font-size:.8rem; padding:20px; }
  #lista-arqs { font-size:.85rem; color:#555; margin-bottom:12px; }
</style>
</head>
<body>
<header>
  <h1>☕ OCR Beans</h1>
  <p>OCR de PDFs judiciais e imagens + ferramentas de conversão — tudo via API</p>
</header>

<div class="grid" id="grid"></div>

<div id="painel">
  <button class="voltar" onclick="fechar()">← Todas as ferramentas</button>
  <h2 id="p-titulo"></h2>
  <p class="desc" id="p-desc"></p>
  <div class="drop" id="drop">Arraste arquivo(s) aqui ou clique para selecionar</div>
  <input type="file" id="file" style="display:none" multiple>
  <div id="lista-arqs"></div>
  <div id="opcoes"></div>
  <button class="acao" id="btn" onclick="executar()">Processar</button>
  <div id="status"></div>
</div>

<footer>BeansTech 2026 · OCR Beans API · <a href="/docs" style="color:#999">/docs</a> para integração</footer>

<script>
const TOOLS = [
 {id:'ocr-pdf',       icone:'📄➡️🔤', titulo:'PDF → Texto (OCR)', desc:'Extrai texto de PDF, com OCR automático para fontes corrompidas e scans.', accept:'.pdf', multiple:false, endpoint:'/api/ocr/pdf'},
 {id:'ocr-img',       icone:'🖼️➡️🔤', titulo:'Imagem → Texto (OCR)', desc:'Lê texto de PNG, JPG, TIFF, WEBP e mais.', accept:'.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp', multiple:false, endpoint:'/api/ocr/image'},
 {id:'check',         icone:'🩺', titulo:'Diagnosticar PDF', desc:'Detecta se o PDF tem fonte corrompida e precisa de OCR.', accept:'.pdf', multiple:false, endpoint:'/api/check'},
 {id:'img2pdf',       icone:'🖼️➡️📄', titulo:'Imagens → PDF', desc:'Junta várias imagens em um único PDF.', accept:'.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp', multiple:true, endpoint:'/api/convert/images-to-pdf'},
 {id:'pdf2img',       icone:'📄➡️🖼️', titulo:'PDF → Imagens', desc:'Renderiza páginas do PDF como PNG/JPG (zip).', accept:'.pdf', multiple:false, endpoint:'/api/convert/pdf-to-images',
   opcoes:[{nome:'dpi',label:'DPI',tipo:'select',valores:['150','200','300'],padrao:'200'},{nome:'fmt',label:'Formato',tipo:'select',valores:['png','jpg'],padrao:'png'}]},
 {id:'merge',         icone:'🔗', titulo:'Juntar PDFs', desc:'Combina vários PDFs em um só, na ordem selecionada.', accept:'.pdf', multiple:true, endpoint:'/api/convert/merge'},
 {id:'split',         icone:'✂️', titulo:'Dividir / Extrair páginas', desc:'Extrai páginas do PDF (ex.: 1-3,7).', accept:'.pdf', multiple:false, endpoint:'/api/convert/split',
   opcoes:[{nome:'pages',label:'Páginas (ex: 1-3,7)',tipo:'text',padrao:'1'}]},
 {id:'compress',      icone:'🗜️', titulo:'Comprimir PDF', desc:'Reduz o tamanho recompactando imagens embutidas.', accept:'.pdf', multiple:false, endpoint:'/api/convert/compress',
   opcoes:[{nome:'qualidade',label:'Qualidade imagem (10-95)',tipo:'select',valores:['40','60','75'],padrao:'60'}]},
 {id:'rotate',        icone:'🔄', titulo:'Girar PDF', desc:'Rotaciona páginas em 90, 180 ou 270 graus.', accept:'.pdf', multiple:false, endpoint:'/api/convert/rotate',
   opcoes:[{nome:'graus',label:'Graus',tipo:'select',valores:['90','180','270'],padrao:'90'}]},
 {id:'watermark',     icone:'💧', titulo:'Marca d’água', desc:'Aplica texto diagonal em todas as páginas.', accept:'.pdf', multiple:false, endpoint:'/api/convert/watermark',
   opcoes:[{nome:'texto',label:'Texto da marca d’água',tipo:'text',padrao:'CONFIDENCIAL'}]},
 {id:'pdf2docx',      icone:'📄➡️📝', titulo:'PDF → Word', desc:'Converte PDF para DOCX editável.', accept:'.pdf', multiple:false, endpoint:'/api/convert/pdf-to-docx'},
 {id:'extract-img',   icone:'🗃️', titulo:'Extrair imagens do PDF', desc:'Baixa todas as imagens embutidas (zip).', accept:'.pdf', multiple:false, endpoint:'/api/convert/extract-images'},
];

let toolAtual = null;
const grid = document.getElementById('grid');
const painel = document.getElementById('painel');
const fileInput = document.getElementById('file');
const drop = document.getElementById('drop');

TOOLS.forEach(t => {
  const el = document.createElement('div');
  el.className = 'card';
  el.innerHTML = `<div class="icone">${t.icone}</div><h3>${t.titulo}</h3><p>${t.desc}</p>`;
  el.onclick = () => abrir(t);
  grid.appendChild(el);
});

function abrir(t) {
  toolAtual = t;
  document.getElementById('p-titulo').textContent = t.titulo;
  document.getElementById('p-desc').textContent = t.desc;
  fileInput.value = ''; fileInput.multiple = t.multiple; fileInput.accept = t.accept;
  document.getElementById('lista-arqs').textContent = '';
  document.getElementById('status').textContent = '';
  const op = document.getElementById('opcoes'); op.innerHTML = '';
  (t.opcoes || []).forEach(o => {
    const div = document.createElement('div'); div.className = 'campo';
    const label = document.createElement('label'); label.textContent = o.label; div.appendChild(label);
    if (o.tipo === 'select') {
      const sel = document.createElement('select'); sel.id = 'opt-' + o.nome;
      o.valores.forEach(v => { const opt = document.createElement('option'); opt.value = v; opt.textContent = v; if (v === o.padrao) opt.selected = true; sel.appendChild(opt); });
      div.appendChild(sel);
    } else {
      const inp = document.createElement('input'); inp.id = 'opt-' + o.nome; inp.value = o.padrao; div.appendChild(inp);
    }
    op.appendChild(div);
  });
  grid.style.display = 'none'; painel.style.display = 'block';
}
function fechar() { painel.style.display = 'none'; grid.style.display = 'grid'; toolAtual = null; }

drop.onclick = () => fileInput.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); fileInput.files = e.dataTransfer.files; listar(); };
fileInput.onchange = listar;
function listar() {
  const nomes = [...fileInput.files].map(f => f.name).join(', ');
  document.getElementById('lista-arqs').textContent = nomes ? `📎 ${nomes}` : '';
}

async function executar() {
  const st = document.getElementById('status');
  const btn = document.getElementById('btn');
  if (!fileInput.files.length) { st.className = 'erro'; st.textContent = 'Selecione ao menos um arquivo.'; return; }
  const fd = new FormData();
  if (toolAtual.multiple) { [...fileInput.files].forEach(f => fd.append('files', f)); }
  else { fd.append('file', fileInput.files[0]); }
  (toolAtual.opcoes || []).forEach(o => fd.append(o.nome, document.getElementById('opt-' + o.nome).value));

  btn.disabled = true; st.className = ''; st.textContent = 'Processando…';
  try {
    const resp = await fetch(toolAtual.endpoint, { method: 'POST', body: fd });
    if (!resp.ok) {
      let msg = 'Erro ' + resp.status;
      try { const j = await resp.json(); msg = j.detail || msg; } catch(e) {}
      throw new Error(msg);
    }
    const ctype = resp.headers.get('content-type') || '';
    if (ctype.includes('application/json')) {
      const j = await resp.json();
      st.className = 'ok'; st.textContent = JSON.stringify(j, null, 2);
    } else {
      const blob = await resp.blob();
      const cd = resp.headers.get('content-disposition') || '';
      const m = cd.match(/filename="?([^";]+)"?/);
      const nome = m ? m[1] : 'resultado';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = nome; a.click();
      st.className = 'ok'; st.textContent = '✔ Pronto! Download iniciado: ' + nome;
    }
  } catch (e) {
    st.className = 'erro'; st.textContent = '✘ ' + e.message;
  } finally { btn.disabled = false; }
}
</script>
</body>
</html>
"""
