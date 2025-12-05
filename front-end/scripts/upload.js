document.getElementById('year').textContent = new Date().getFullYear();

const dz = document.getElementById('dz');
const fileInput = document.getElementById('fileInput');
const preview = document.getElementById('preview');
const form = document.getElementById("intakeForm");
const analyzeBtn = document.getElementById("analyzeBtn");
const clearBtn = document.getElementById("clearBtn");
const formMsg = document.getElementById("formMsg");

let selectedFiles = [];
let justDropped = false;

// -------------------------
// DRAG + DROP
// -------------------------
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
  validateForm();
});

// block double-click
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
  validateForm();
});

// -------------------------
// PREVIEW HANDLER
// -------------------------
function handleFiles(files) {
  selectedFiles = [...files];
  preview.innerHTML = "";

  selectedFiles.forEach((file) => {
    const url = URL.createObjectURL(file);
    const wrap = document.createElement("div");
    wrap.style.position = "relative";

    const img = document.createElement("img");
    img.src = url;

    wrap.appendChild(img);
    preview.appendChild(wrap);
  });
}

// -------------------------
// FORM VALIDATION
// -------------------------
function validateForm() {
  const requiredIds = ["name", "age", "skinType", "location", "duration"];
  const allFilled = requiredIds.every(id => document.getElementById(id).value.trim() !== "");

  const consent = document.getElementById("consent").checked;
  const ok = allFilled && consent && selectedFiles.length > 0;

  analyzeBtn.disabled = !ok;
  formMsg.textContent = ok ? "" : "Upload an image, fill required fields, and give consent.";
}

form.addEventListener("input", validateForm);
form.addEventListener("change", validateForm);

// -------------------------
// SEND TO CHATBOT
// -------------------------
function sendUploadToChat(imageFile, formDataObject) {
  const fd = new FormData();

  if (imageFile) {
    fd.append("image", imageFile);
  }

  Object.entries(formDataObject).forEach(([k, v]) => {
    fd.append(k, v);
  });

  fetch(BACKEND_URL, { method: "POST", body: fd })
    .then(r => r.json())
    .then(data => {
      addMessage(data.reply, "bot");
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = "Analyze";
    })
    .catch(() => addMessage("Error sending upload.", "bot"));
}

// -------------------------
// SUBMIT HANDLER
// -------------------------
form.addEventListener("submit", function (e) {
  e.preventDefault();
  if (analyzeBtn.disabled) return;

  analyzeBtn.textContent = "Analyzing…";
  analyzeBtn.disabled = true;

  let imageFile = null;
  if (selectedFiles.length > 0) imageFile = selectedFiles[0];

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

// -------------------------
// CLEAR BUTTON
// -------------------------
clearBtn.addEventListener("click", () => {
  form.reset();
  preview.innerHTML = "";
  selectedFiles = [];
  analyzeBtn.disabled = true;
  formMsg.textContent = "";

  validateForm();
});
