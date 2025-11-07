document.getElementById('year').textContent = new Date().getFullYear();

const drop = document.getElementById('dropzone');
const input = document.getElementById('fileInput');
const preview = document.getElementById('preview');

function handleFiles(files){
  if(!files) return;
  [...files].forEach(f => {
    if(!f.type.startsWith('image/')) return;
    const url = URL.createObjectURL(f);
    const img = document.createElement('img');
    img.src = url;
    img.alt = 'Uploaded preview';
    if(preview) preview.appendChild(img);
  });
}
if(input){ input.addEventListener('change', () => handleFiles(input.files)); }
if(drop){
  ['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); }));
  drop.addEventListener('drop', e => { e.preventDefault(); handleFiles(e.dataTransfer.files); });
  drop.addEventListener('click', () => input && input.click());
  drop.addEventListener('keydown', e => { if(e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input && input.click(); } });
}
