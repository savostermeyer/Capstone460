// scripts/upload.js
// Handles multiple image upload, preview, form validation, demo analysis,
// storing demo reports so they appear on reports.html, and sending uploads
// + metadata to the chatbot backend.

// ---- Helpers for demo reports (shape matches reports.js expectations) ----

function getCurrentUserEmail() {
  try {
    return localStorage.getItem("skinai_user") || null;
  } catch (e) {
    console.error("localStorage unavailable", e);
    return null;
  }
}

function getUserReports(email) {
  if (!email) return [];
  try {
    const raw = localStorage.getItem(`skinai_reports_${email}`);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.error("Failed to read reports", e);
    return [];
  }
}

function setUserReports(email, reports) {
  if (!email) return;
  try {
    localStorage.setItem(`skinai_reports_${email}`, JSON.stringify(reports));
  } catch (e) {
    console.error("Failed to save reports", e);
  }
}

// Build a demo analysis result for a single image.
// In a real app, this shape should match the backend's JSON.
function buildDemoResult(file, data, index) {
  const now = new Date();
  const idBase =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : String(Date.now()) + "_" + index;

  return {
    id: idBase,
    createdAt: now.toISOString(),
    filename: file ? file.name : `uploaded_lesion_${index + 1}.jpg`,
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
// Main upload page logic
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
  const yearEl = document.getElementById("year");
  const chatWindow = document.getElementById("chatbot-window");

  // Not on the upload page
  if (!dz || !fileInput || !preview || !form) {
    return;
  }

  // Ensure footer year is filled if app.js hasn't done it yet
  if (yearEl && !yearEl.textContent) {
    yearEl.textContent = new Date().getFullYear();
  }

  const MAX_FILES = 6;
  let selectedFiles = [];
  let justDropped = false;

  // ---- Login-required prompt ----
  function showLoginRequired() {
    alert("Please log in to analyze and save your report.");
    window.location.href = "login.html?next=upload.html";
  }

  // --- Preview helpers ---
  function resetPreview() {
    preview.innerHTML = "";
    selectedFiles = [];
  }

  function addFilesFromList(fileList) {
    if (!fileList) return;

    const incoming = Array.from(fileList);

    for (const file of incoming) {
      if (!/image\/(jpeg|png)/.test(file.type)) {
        // Skip non-images silently
        continue;
      }

      if (selectedFiles.length >= MAX_FILES) {
        alert(`You can upload up to ${MAX_FILES} images per session.`);
        break;
      }

      selectedFiles.push(file);

      const url = URL.createObjectURL(file);
      const imgWrap = document.createElement("div");
      imgWrap.style.position = "relative";

      const img = document.createElement("img");
      img.src = url;
      img.alt = "Uploaded image preview";

      imgWrap.appendChild(img);
      preview.appendChild(imgWrap);
    }

    validateForm();
  }

  // --- Drag & drop behavior ---
  const prevent = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  ["dragenter", "dragover", "dragleave", "drop"].forEach((evt) => {
    dz.addEventListener(evt, prevent);
  });

  dz.addEventListener("dragover", () => {
    dz.style.outline = "2px solid var(--gold)";
  });

  dz.addEventListener("dragleave", () => {
    dz.style.outline = "";
  });

  dz.addEventListener("drop", (e) => {
    dz.style.outline = "";
    justDropped = true;

    if (e.dataTransfer && e.dataTransfer.files) {
      const files = [...e.dataTransfer.files].filter((f) =>
        /image\/(jpeg|png)/.test(f.type)
      );
      if (files.length) {
        addFilesFromList(files);
      }
    }
  });

  dz.addEventListener("click", (e) => {
    // avoid double-click after drop
    if (justDropped) {
      justDropped = false;
      return;
    }
    fileInput.click();
  });

  dz.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", (e) => {
    const files = [...e.target.files].filter((f) =>
      /image\/(jpeg|png)/.test(f.type)
    );
    if (files.length) {
      addFilesFromList(files);
    }
  });

  // --- Form validation ---
  const requiredIds = ["name", "age", "skinType", "location", "duration"];

  function validateForm() {
    const allFilled = requiredIds.every((id) => {
      const el = document.getElementById(id);
      return el && el.value.trim() !== "";
    });

    const hasFiles = selectedFiles.length > 0;
    const hasConsent = consent && consent.checked;

    const ok = hasFiles && hasConsent && allFilled;

    if (analyzeBtn) analyzeBtn.disabled = !ok;
    if (formMsg) {
      if (!hasFiles) {
        formMsg.textContent = "Upload at least one image to analyze.";
      } else if (!allFilled) {
        formMsg.textContent = "Fill all required fields marked with *.";
      } else if (!hasConsent) {
        formMsg.textContent = "Please confirm consent before continuing.";
      } else {
        formMsg.textContent = "";
      }
    }
  }

  form.addEventListener("input", validateForm);
  form.addEventListener("change", validateForm);

  // -------------------------
  // Send to chatbot backend
  // -------------------------
  function sendUploadToChat(imageFile, formDataObject) {
    const fd = new FormData();

    if (imageFile) {
      fd.append("image", imageFile);
    }

    Object.entries(formDataObject || {}).forEach(([k, v]) => {
      fd.append(k, v);
    });

    // BACKEND_URL and addMessage are expected to be defined in chatbot.js
    return fetch(BACKEND_URL, { method: "POST", body: fd })
      .then((r) => r.json())
      .then((data) => {
        if (typeof addMessage === "function") {
          addMessage(data.reply || "Analysis complete.", "bot");
        }
      })
      .catch((err) => {
        console.error("Error sending upload to chatbot:", err);
        if (typeof addMessage === "function") {
          addMessage("Error sending upload.", "bot");
        }
      });
  }

  // --- Submit (demo analysis + chatbot integration) ---
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!selectedFiles.length) return;
    if (analyzeBtn && analyzeBtn.disabled) return;

    const email = getCurrentUserEmail();
    if (!email) {
      showLoginRequired();
      return;
    }

    const data = {
      name: (document.getElementById("name").value || "").trim(),
      age: Number(document.getElementById("age").value || 0),
      sex: document.getElementById("sex").value || "",
      fitzpatrick: document.getElementById("skinType").value || "",
      location: (document.getElementById("location").value || "").trim(),
      duration_days: Number(document.getElementById("duration").value || 0),
      // Placeholder fields; can be wired to real inputs later.
      symptom: "",
      family_history: "",
      sun_exposure: "",
      spf: "",
      meds: "",
      notes: ""
    };

    // Demo: create one result per selected image
    const results = selectedFiles.map((file, idx) =>
      buildDemoResult(file, data, idx)
    );

    // Update the result card summary
    if (resultMeta) {
      const count = results.length;
      resultMeta.textContent =
        `${data.name || "Patient"}, age ${data.age || "?"} — ` +
        `Skin condition: ${data.fitzpatrick || "N/A"} — ` +
        `Location: ${data.location || "N/A"}, ` +
        `${data.duration_days || 0} day(s). ` +
        `Analyzed ${count} image${count > 1 ? "s" : ""} in this session (demo).`;
    }

    if (resultTags) {
      resultTags.innerHTML = "";
      const tagStrings = [
        data.sex && `Sex: ${data.sex}`,
        data.location && `Location: ${data.location}`
      ].filter(Boolean);

      tagStrings.forEach((t) => {
        const pill = document.createElement("span");
        pill.className = "pill";
        pill.textContent = t;
        resultTags.appendChild(pill);
      });
    }

    if (resultCard) {
      resultCard.classList.add("show");
    }

    // Save demo reports for logged-in users so they appear on reports.html
    if (email) {
      const existing = getUserReports(email);
      const combined = [...results, ...existing]; // newest first
      setUserReports(email, combined);
    }

    // --- Chatbot integration ---
    const imageFile = selectedFiles[0] || null;
    const metadata = {
      name: data.name,
      age: String(data.age || ""),
      sex: data.sex,
      fitzpatrick: data.fitzpatrick,
      body_site: data.location,
      duration_days: String(data.duration_days || ""),
      consent: consent && consent.checked ? "true" : "false"
    };

    if (typeof addMessage === "function") {
      addMessage("Analyzing your uploaded image…", "bot");
    }

    if (analyzeBtn) {
      analyzeBtn.textContent = "Analyzing…";
      analyzeBtn.disabled = true;
    }

    sendUploadToChat(imageFile, metadata).finally(() => {
      if (analyzeBtn) {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = "Analyze";
      }
    });

    if (chatWindow) {
      chatWindow.style.display = "flex";
      try {
        localStorage.setItem("skinai_chat_open", "true");
      } catch (_) {}
    }
  });

  // --- Clear button ---
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      form.reset();
      resetPreview();
      if (resultCard) resultCard.classList.remove("show");
      if (formMsg) {
        formMsg.textContent =
          "Upload at least one image, fill required fields, and confirm consent.";
      }
      if (analyzeBtn) {
        analyzeBtn.disabled = true;
        analyzeBtn.textContent = "Analyze";
      }
      validateForm();
    });
  }

  // Initial validation state
  validateForm();
});
