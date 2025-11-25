    document.getElementById('year').textContent = new Date().getFullYear();

    const dz = document.getElementById('dz');
    const fileInput = document.getElementById('fileInput');
    const preview = document.getElementById('preview');

    let selectedFiles = [];
    let justDropped = false;

    const prevent = e => { e.preventDefault(); e.stopPropagation(); };
    ['dragenter','dragover','dragleave','drop'].forEach(evt =>
      dz.addEventListener(evt, prevent)
    );

    dz.addEventListener('dragover', () => dz.style.outline = '2px solid var(--gold)');
    dz.addEventListener('dragleave', () => dz.style.outline = '');

    dz.addEventListener('drop', e => {
      dz.style.outline = '';
      justDropped = true;

      const files = [...e.dataTransfer.files].filter(f =>
        /image\/(jpeg|png)/.test(f.type)
      );
      if (files.length) handleFiles(files);
    });

    // prevent double-opening
    dz.addEventListener('click', (e) => {
      if (e.target.tagName === "LABEL" || e.target.tagName === "INPUT") return;
      if (justDropped) { justDropped = false; return; }
      fileInput.click();
    });

    fileInput.addEventListener('change', e => {
      const files = [...e.target.files].filter(f =>
        /image\/(jpeg|png)/.test(f.type)
      );
      if (files.length) handleFiles(files);
    });

    function handleFiles(files) {
      selectedFiles = [...selectedFiles, ...files];
      preview.innerHTML = "";

      selectedFiles.forEach((file, index) => {
        const url = URL.createObjectURL(file);
        const wrap = document.createElement("div");
        wrap.style.position = "relative";

        const img = document.createElement("img");
        img.src = url;

        const del = document.createElement("button");
        del.textContent = "✕";
        del.style.position = "absolute";
        del.style.top = "6px";
        del.style.right = "6px";
        del.style.background = "rgba(0,0,0,0.7)";
        del.style.color = "white";
        del.style.border = "none";
        del.style.padding = "2px 6px";
        del.style.cursor = "pointer";
        del.style.borderRadius = "4px";

        del.onclick = () => {
          selectedFiles.splice(index, 1);
          handleFiles([]);
        };

        wrap.appendChild(img);
        wrap.appendChild(del);
        preview.appendChild(wrap);
      });
    }
function sendUploadToChat(imageFile, formDataObject) {
    const fd = new FormData();

    // only attach the image if one exists
    if (imageFile) {
        fd.append("image", imageFile);
    }

    // attach metadata properly
    Object.entries(formDataObject).forEach(([k, v]) => {
        fd.append(k, v);
    });

    fetch(BACKEND_URL, { method: "POST", body: fd })
        .then(r => r.json())
        .then(data => {
            addMessage(data.reply, "bot");
        })
        .catch(err => addMessage("Error sending upload.", "bot"));
}

document.getElementById("intakeForm").addEventListener("submit", function (e) {
    e.preventDefault();

    let imageFile = null;
    if (selectedFiles.length > 0) {
        imageFile = selectedFiles[0];
    }

    const metadata = {
        name: document.getElementById("name").value,
        age: document.getElementById("age").value,
        sex: document.getElementById("sex").value,
        fitzpatrick: document.getElementById("skinType").value,
        body_site: document.getElementById("location").value,
        duration_days: document.getElementById("duration").value,
        consent: document.getElementById("consent").checked
    };

    addMessage("Analyzing your uploaded image…", "bot");

    sendUploadToChat(imageFile, metadata);

    chatWindow.style.display = "flex";
    localStorage.setItem("skinai_chat_open", "true");
});
