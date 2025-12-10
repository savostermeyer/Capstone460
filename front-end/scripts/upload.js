// scripts/upload.js
// Handles image upload (multi-file), preview, deletion,
// form validation, demo analysis, saving demo reports,
// and sending uploads to chatbot backend when available.

// ----------------------
// Helpers for demo data
// ----------------------
function getCurrentUserEmail() {
  try {
    return localStorage.getItem("skinai_user") || null;
  } catch {
    return null;
  }
}

function getUserReports(email) {
  if (!email) return [];
  try {
    const raw = localStorage.getItem(`skinai_reports_${email}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function setUserReports(email, reports) {
  if (!email) return;
  try {
    localStorage.setItem(`skinai_reports_${email}`, JSON.stringify(reports));
  } catch {}
}

// Demo result builder (matches reports.html expectations)
function buildDemoResult(file, data, index) {
  const now = new Date();
  const id = crypto.randomUUID ? crypto.randomUUID() : Date.now() + "_" + index;

  return {
    id,
    createdAt: now.toISOString(),
    filename: file?.name || `uploaded_lesion_${index + 1}.jpg`,
    topPredictions: [
      { label: "Melanocytic nevus", confidence: 0.78 },
      { label: "Benign keratosis", confidence: 0.15 },
      { label: "Melanoma (flag for review)", confidence: 0.07 }
    ],
    notes:
      "Demo summary based on the intake form. Connect this page to your ML backend to return real predictions.",
    meta: {
      name: data.name,
      age: data.age,
      fitzpatrick: data.fitzpatrick,
      location: data.location,
      duration_days: data.duration_days,
      symptom: data.symptom,
      family_history: data.family_history,
      sun_exposure: data.sun_exposure,
      spf: data.spf,
      meds: data.meds,
      notes: data.notes
    }
  };
}

// -----------------------------
// Main Upload Handler
// -----------------------------
document.addEventListener("DOMContentLoaded", () => {
  const dz = document.getElementById("dz");
  const fileInput = document.getElementById("fileInput");
  const preview = document.getElementById("preview");
  const form = document.getElementById("intakeForm");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const clearBtn = document.getElementById("clearBtn");
  const consent = document.getElementById("consent");
  const formMsg = document.getElementById("formMsg");
  const resultCard = document.getElementById("resultCard");
  const resultMeta = document.getElementById("resultMeta");
  const resultTags = document.getElementById("resultTags");

  if (!dz || !fileInput || !preview || !form) return;

  const MAX_FILES = 6;
  let selectedFiles = [];
  let justDropped = false;

  // --------------------------
  // Rendering the preview
  // --------------------------
  function renderPreview() {
    preview.innerHTML = "";

    selectedFiles.forEach((file) => {
      const url = URL.createObjectURL(file);

      const wrap = document.createElement("div");
      wrap.style.position = "relative";

      const img = document.createElement("img");
      img.src = url;
      img.alt = "Uploaded image preview";
      wrap.appendChild(img);

      // DELETE BUTTON
      const del = document.createElement("button");
      del.textContent = "✕";
      del.style.position = "absolute";
      del.style.top = "6px";
      del.style.right = "6px";
      del.style.background = "rgba(0,0,0,0.75)";
      del.style.color = "white";
      del.style.border = "none";
      del.style.padding = "2px 6px";
      del.style.cursor = "pointer";
      del.style.borderRadius = "4px";

      del.onclick = () => {
        selectedFiles = selectedFiles.filter((f) => f !== file);
        renderPreview();
        validateForm();
      };

      wrap.appendChild(del);
      preview.appendChild(wrap);
    });

    validateForm();
  }

  // --------------------------
  // Add Files
  // --------------------------
  function addFiles(files) {
    for (const file of files) {
      if (!/image\/(jpeg|png)/.test(file.type)) continue;

      if (selectedFiles.length >= MAX_FILES) {
        alert(`Maximum ${MAX_FILES} images allowed.`);
        break;
      }

      selectedFiles.push(file);
    }

    renderPreview();
  }

  // --------------------------
  // Drag + Drop
  // --------------------------
  const prevent = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };
  ["dragenter", "dragover", "dragleave", "drop"].forEach((evt) =>
    dz.addEventListener(evt, prevent)
  );

  dz.addEventListener("dragover", () => {
    dz.style.outline = "2px solid var(--gold)";
  });

  dz.addEventListener("dragleave", () => {
    dz.style.outline = "";
  });

dz.addEventListener("drop", (e) => {
  dz.style.outline = "";

  justDropped = true;

  // BLOCK the next click completely
  dz.dataset.blockNextClick = "true";

  // Allow real clicking again after short delay
  setTimeout(() => {
    dz.dataset.blockNextClick = "false";
    justDropped = false;
  }, 120);

  const files = [...e.dataTransfer.files].filter((f) =>
    /image\/(jpeg|png)/.test(f.type)
  );

  if (files.length) addFiles(files);
});



dz.addEventListener("click", (e) => {
  // Do not open file dialog if drop event just happened
  if (dz.dataset.blockNextClick === "true") {
    e.stopPropagation();
    e.preventDefault();
    return;
  }

  // Keep your original protection
  if (e.target.tagName === "LABEL" || e.target.tagName === "INPUT") return;

  fileInput.click();
});



  fileInput.addEventListener("change", (e) => {
    const files = [...e.target.files].filter((f) =>
      /image\/(jpeg|png)/.test(f.type)
    );
    if (files.length) addFiles(files);
  });

  // --------------------------
  // Form Validation
  // --------------------------
  const requiredIds = ["name", "age", "skinType", "location", "duration"];

  function validateForm() {
    const allFilled = requiredIds.every((id) => {
      const el = document.getElementById(id);
      return el && el.value.trim() !== "";
    });

    const ok = selectedFiles.length > 0 && consent.checked && allFilled;

    analyzeBtn.disabled = !ok;

    if (!selectedFiles.length) {
      formMsg.textContent = "Upload at least one image.";
    } else if (!allFilled) {
      formMsg.textContent = "Fill required fields.";
    } else if (!consent.checked) {
      formMsg.textContent = "Please confirm consent.";
    } else {
      formMsg.textContent = "";
    }
  }

  form.addEventListener("input", validateForm);
  form.addEventListener("change", validateForm);

  // --------------------------
  // Chatbot upload sender
  // --------------------------
  function sendUploadToChat(imageFile, metadata) {
    if (!window.BACKEND_URL) return Promise.resolve();

    const fd = new FormData();
    fd.append("image", imageFile);

    Object.entries(metadata).forEach(([k, v]) => fd.append(k, v));

    return fetch(BACKEND_URL, { method: "POST", body: fd })
      .then((r) => r.json())
      .then((data) => {
        if (typeof addMessage === "function") {
          addMessage(data.reply || "Analysis complete.", "bot");
        }
      })
      .catch(() => {
        if (typeof addMessage === "function") {
          addMessage("Error sending upload.", "bot");
        }
      });
  }

  // --------------------------
  // Submit handler
  // --------------------------
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!selectedFiles.length || analyzeBtn.disabled) return;

    const email = getCurrentUserEmail();
    if (!email) {
      alert("Please log in to analyze images.");
      window.location.href = "login.html?next=upload.html";
      return;
    }

    const data = {
      name: document.getElementById("name").value.trim(),
      age: Number(document.getElementById("age").value),
      sex: document.getElementById("sex").value,
      fitzpatrick: document.getElementById("skinType").value,
      location: document.getElementById("location").value.trim(),
      duration_days: Number(document.getElementById("duration").value),
      symptom: "",
      family_history: "",
      sun_exposure: "",
      spf: "",
      meds: "",
      notes: ""
    };

    const results = selectedFiles.map((file, i) =>
      buildDemoResult(file, data, i)
    );

    // Display summary
    resultMeta.textContent =
      `${data.name}, age ${data.age} — Skin: ${data.fitzpatrick} — ` +
      `${data.location}, ${data.duration_days} days — ` +
      `Analyzed ${results.length} image(s).`;

    resultTags.innerHTML = "";
    if (data.sex) {
      const pill = document.createElement("span");
      pill.className = "pill";
      pill.textContent = `Sex: ${data.sex}`;
      resultTags.appendChild(pill);
    }

    resultCard.classList.add("show");

    // Save demo results
    const existing = getUserReports(email);
    const merged = [...results, ...existing];
    setUserReports(email, merged);

    // Send first file to chatbot
    analyzeBtn.textContent = "Analyzing…";
    analyzeBtn.disabled = true;

    sendUploadToChat(selectedFiles[0], {
      name: data.name,
      age: String(data.age),
      sex: data.sex,
      fitzpatrick: data.fitzpatrick,
      body_site: data.location,
      duration_days: String(data.duration_days),
      consent: "true"
    }).finally(() => {
      analyzeBtn.textContent = "Analyze";
      analyzeBtn.disabled = false;
    });
  });

  // --------------------------
  // Clear button
  // --------------------------
  clearBtn.addEventListener("click", () => {
    form.reset();
    selectedFiles = [];
    resultCard.classList.remove("show");
    preview.innerHTML = "";
    analyzeBtn.disabled = true;
    formMsg.textContent =
      "Upload at least one image, fill required fields, and confirm consent.";
  });

  validateForm();
});
