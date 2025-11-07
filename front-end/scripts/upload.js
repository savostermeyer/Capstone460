// upload.js — drag/drop + preview for upload.html

(function(){
  const drop = document.getElementById('dz') || document.getElementById('dropzone');
  const input = document.getElementById('fileInput');
  const preview = document.getElementById('preview');

  if (!drop || !input || !preview) return;

  function handleFiles(files){
    const f = files && files[0];
    if(!f) return;
    if(!f.type.startsWith('image/')) { alert('Please upload a JPG or PNG.'); return; }
    const url = URL.createObjectURL(f);
    preview.innerHTML = '';
    const img = document.createElement('img');
    img.src = url; img.alt = 'Uploaded preview';
    preview.appendChild(img);
  }

  const prevent = e => { e.preventDefault(); e.stopPropagation(); };
  ['dragenter','dragover','dragleave','drop'].forEach(evt => drop.addEventListener(evt, prevent));
  drop.addEventListener('dragover', () => drop.style.outline = '2px solid var(--gold)');
  drop.addEventListener('dragleave', () => drop.style.outline = '');
  drop.addEventListener('drop', e => { drop.style.outline=''; handleFiles(e.dataTransfer.files); });
  drop.addEventListener('click', () => input.click());
  input.addEventListener('change', e => handleFiles(e.target.files));
})();