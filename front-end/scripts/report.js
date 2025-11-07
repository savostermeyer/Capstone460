// reports.js — auth gate + demo list

(function(){
  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  const user = localStorage.getItem('skinai_user') || sessionStorage.getItem('skinai_user');
  if (!user) {
    location.href = 'login.html?next=' + encodeURIComponent('reports.html');
    return;
  }

  const hello = document.getElementById('hello');
  if (hello) hello.textContent = `Signed in as ${user}`;

  const signout = document.getElementById('signout');
  if (signout) {
    signout.addEventListener('click', () => {
      localStorage.removeItem('skinai_user');
      sessionStorage.removeItem('skinai_user');
      location.href = 'login.html';
    });
  }

  // demo storage helpers
  const key = `skinai_reports_${user}`;
  const get = () => JSON.parse(localStorage.getItem(key) || '[]');
  const set = v => localStorage.setItem(key, JSON.stringify(v));

  // seed a sample if none
  if (get().length === 0) {
    set([{
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      filename: "lesion_sample.jpg",
      topPredictions: [
        { label: "Melanocytic nevus", confidence: 0.78 },
        { label: "Benign keratosis", confidence: 0.15 },
        { label: "Melanoma (flag)", confidence: 0.07 }
      ],
      notes: "Preliminary model output. Not a medical diagnosis."
    }]);
  }

  // render
  const listEl = document.getElementById('report-list');
  const emptyEl = document.getElementById('empty');
  const fmtPct = x => (x*100).toFixed(1) + '%';
  const fmtDate = iso => new Date(iso).toLocaleString([], {year:'numeric', month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit'});

  function render(){
    const items = get();
    if (!items.length) { emptyEl.style.display='block'; return; }
    emptyEl.style.display='none';
    listEl.innerHTML = items.map(r => `
      <div class="card">
        <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
          <div>
            <h3 style="margin:0 0 4px 0">${r.filename}</h3>
            <div class="muted">Created: ${fmtDate(r.createdAt)}</div>
          </div>
          <div><a class="btn" href="upload.html">Analyze another</a></div>
        </div>
        <div style="margin-top:10px">
          <strong>Top predictions</strong>
          <ul style="margin:6px 0 0 18px">
            ${r.topPredictions.map(p => `<li>${p.label} — ${fmtPct(p.confidence)}</li>`).join('')}
          </ul>
          <p class="muted" style="margin-top:8px">${r.notes || ''}</p>
        </div>
        <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
          <button class="btn" data-action="download" data-id="${r.id}">Download JSON</button>
          <button class="btn" data-action="delete" data-id="${r.id}">Delete</button>
        </div>
      </div>
    `).join('');
  }

  listEl.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const action = btn.getAttribute('data-action');
    const id = btn.getAttribute('data-id');
    const items = get();
    const idx = items.findIndex(r => r.id === id);
    if (idx === -1) return;

    if (action === 'download') {
      const blob = new Blob([JSON.stringify(items[idx], null, 2)], {type:'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `skinai_report_${id}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } else if (action === 'delete') {
      items.splice(idx,1); localStorage.setItem(key, JSON.stringify(items)); render();
    }
  });

  render();
})();