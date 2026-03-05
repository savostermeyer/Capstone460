import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/upload.css";

const LOGIN_GATE_DELAY_MS = 1000;
const MAX_IMAGES = 20;

// Use one API_BASE definition (fallback for local dev)
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:3720").replace(/\/$/, "");

/** Returns email/username or null */
function getLoggedInUser() {
  try {
    const raw = (localStorage.getItem("skinai_user") || "").trim();
    if (!raw || raw === "null" || raw === "undefined") return null;
    return raw;
  } catch {
    return null;
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

// Used for de-duping selected files
function fileSig(f) {
  return `${f.name}|${f.size}|${f.lastModified}`;
}

const DISEASE_LABELS = {
  akiec: "Actinic keratoses and intraepithelial carcinoma (Bowen disease)",
  bcc: "Basal cell carcinoma",
  bkl: "Benign keratosis (seborrheic keratosis, lichen planus-like keratosis)",
  df: "Dermatofibroma",
  mel: "Melanoma",
  nv: "Melanocytic nevus",
  vasc: "Vascular lesion (angioma, angiokeratoma, hemorrhage)",
};

const DISEASE_DESCRIPTIONS = {
  akiec: "Precancerous, sun-related scaly lesions that can evolve over time.",
  bcc: "Slow-growing skin cancer; often appears as a pearly or ulcerated bump.",
  bkl: "Common, benign growths with a waxy or stuck-on appearance.",
  df: "Benign, firm skin nodule, often on legs or arms.",
  mel: "Potentially aggressive skin cancer; needs prompt evaluation.",
  nv: "Common benign mole; usually stable in shape and color.",
  vasc: "Benign blood-vessel lesion; may appear red, purple, or blue.",
};

function normalizeLabel(label) {
  if (!label) return "Unknown";
  const raw = String(label).trim();
  const key = raw.toLowerCase();
  if (DISEASE_LABELS[key]) return DISEASE_LABELS[key];
  return raw;
}

function predictionDescription(label) {
  if (!label) return "";
  const key = String(label).trim().toLowerCase();
  if (DISEASE_DESCRIPTIONS[key]) return DISEASE_DESCRIPTIONS[key];

  const normalized = normalizeLabel(label).toLowerCase();
  const matchKey = Object.keys(DISEASE_LABELS).find(
    (abbr) => DISEASE_LABELS[abbr].toLowerCase() === normalized
  );
  if (matchKey && DISEASE_DESCRIPTIONS[matchKey]) return DISEASE_DESCRIPTIONS[matchKey];

  return "Consider a clinician review to confirm and correlate clinically.";
}

function fmtPct(x) {
  return (Number(x || 0) * 100).toFixed(1) + "%";
}

function nextStepForRisk(riskScore) {
  const score = String(riskScore || "").toLowerCase();
  if (score === "high_risk" || score === "high") return "Schedule an urgent dermatology visit and avoid delays.";
  if (score === "moderate_risk" || score === "moderate") return "Book a dermatology appointment within the next few weeks.";
  if (score === "low_risk" || score === "low") return "Monitor for changes and practice sun protection; see a clinician if it changes.";
  return "Seek medical advice if you are concerned or notice changes.";
}

export default function Upload() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [files, setFiles] = useState([]); // File[]
  const [previews, setPreviews] = useState([]); // { sig, name, url }[]

  // IMPORTANT: your UI uses form.location + form.duration.
  // Your earlier state had lesionLocation fields but the UI doesn't use them consistently.
  const [form, setForm] = useState({
    name: "",
    age: "",
    sex: "",
    skinType: "",
    location: "",
    duration: "",
    primarySymptoms: [],
    medicalBackground: "",
    familyHistory: "",
    sunExposure: "",
    spfUse: "",
    currentMedications: "",
    consent: false,
  });

  const [formMsg, setFormMsg] = useState("");
  const [result, setResult] = useState(null); // { meta, raw, raw_full } or { success, topPredictions, message }
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [userEmail, setUserEmail] = useState(getLoggedInUser);
  const [showLoginGate, setShowLoginGate] = useState(false);

  useEffect(() => {
    const syncUser = () => setUserEmail(getLoggedInUser());
    syncUser();
    window.addEventListener("storage", syncUser);
    window.addEventListener("focus", syncUser);
    return () => {
      window.removeEventListener("storage", syncUser);
      window.removeEventListener("focus", syncUser);
    };
  }, []);

  useEffect(() => {
    if (userEmail) {
      setShowLoginGate(false);
      return;
    }
    const timerId = setTimeout(() => setShowLoginGate(true), LOGIN_GATE_DELAY_MS);
    return () => clearTimeout(timerId);
  }, [userEmail]);

  // Build object URLs for previews (and clean them up)
  useEffect(() => {
    const next = files.map((f) => ({
      sig: fileSig(f),
      name: f.name,
      url: URL.createObjectURL(f),
    }));
    setPreviews(next);
    return () => next.forEach((p) => URL.revokeObjectURL(p.url));
  }, [files]);

  const canAnalyze = useMemo(() => {
    const requiredFilled =
      form.name.trim() &&
      String(form.age).trim() &&
      form.sex &&
      form.skinType &&
      form.location.trim() &&
      String(form.duration).trim();

    const hasSymptoms = form.primarySymptoms.length > 0;

    return Boolean(requiredFilled && hasSymptoms && form.consent && files.length > 0);
  }, [form, files]);

  function acceptFiles(fileList) {
    if (!userEmail) {
      setShowLoginGate(true);
      setFormMsg("Must be logged in to upload image.");
      return;
    }
    if (!fileList) return;

    const picked = Array.from(fileList).filter((f) =>
      ["image/jpeg", "image/png"].includes(f.type)
    );

    if (picked.length === 0) {
      setFormMsg("Please upload JPG or PNG images.");
      return;
    }

    setFormMsg("");
    setResult(null);

    setFiles((prev) => {
      const seen = new Set(prev.map(fileSig));
      const merged = [...prev];

      for (const f of picked) {
        const s = fileSig(f);
        if (!seen.has(s)) {
          merged.push(f);
          seen.add(s);
        }
      }

      if (merged.length > MAX_IMAGES) {
        setFormMsg(`You can upload up to ${MAX_IMAGES} images. Extra files were ignored.`);
        return merged.slice(0, MAX_IMAGES);
      }
      return merged;
    });
  }

  function onDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    acceptFiles(e.dataTransfer.files);
  }

  function onBrowse() {
    if (!userEmail) {
      setShowLoginGate(true);
      return;
    }
    fileInputRef.current?.click();
  }

  function deleteImage(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setResult(null);
  }

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setResult(null);
  }

  function toggleSymptom(symptom) {
    setForm((prev) => ({
      ...prev,
      primarySymptoms: prev.primarySymptoms.includes(symptom)
        ? prev.primarySymptoms.filter((s) => s !== symptom)
        : [...prev.primarySymptoms, symptom],
    }));
    setResult(null);
  }

  function clearAll() {
    setFiles([]);
    setPreviews([]);
    setResult(null);
    setFormMsg("");
    setForm({
      name: "",
      age: "",
      sex: "",
      skinType: "",
      location: "",
      duration: "",
      primarySymptoms: [],
      medicalBackground: "",
      familyHistory: "",
      sunExposure: "",
      spfUse: "",
      currentMedications: "",
      consent: false,
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmit(e) {
    e.preventDefault();

    if (!userEmail) {
      setShowLoginGate(true);
      setFormMsg("Must be logged in to upload image.");
      return;
    }

    if (!canAnalyze) {
      setFormMsg("Please complete required fields, consent, and add at least 1 image.");
      return;
    }

    setIsSubmitting(true);
    setFormMsg("Uploading and analyzing...");

    try {
      // One request containing many images (batch upload)
      const formData = new FormData();
      files.forEach((file) => formData.append("images", file));

      // Intake fields (keep aligned with your backend)
      formData.append("name", form.name);
      formData.append("age", String(form.age));
      formData.append("sex", form.sex);
      formData.append("skinType", form.skinType);
      formData.append("location", form.location);
      formData.append("duration_days", String(form.duration));
      formData.append("primarySymptoms", form.primarySymptoms.join(", "));
      formData.append("medicalBackground", form.medicalBackground);
      formData.append("familyHistory", form.familyHistory);
      formData.append("sunExposure", form.sunExposure);
      formData.append("spfUse", form.spfUse);
      formData.append("currentMedications", form.currentMedications);
      formData.append("consent", String(form.consent));
      formData.append("uploadDate", new Date().toISOString());

      const response = await fetch(`${API_BASE}/analyze_skin`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        let msg = "Failed to analyze images.";
        try {
          const errJson = await response.json();
          msg = errJson.error || errJson.message || msg;
        } catch {}
        throw new Error(msg);
      }

      const data = await response.json();

      // Minimal normalize into what your UI expects
      const now = new Date();
      const meta = `${files.length} image(s) analyzed • ${now.toLocaleString()}`;

      setResult({
        meta,
        raw: {
          primary_result: data?.risk_score ?? data?.primary_result ?? null,
        },
        raw_full: data,
      });

      setFormMsg(`✓ Analyzed ${files.length} image(s)`);

      // Save lastAnalysis (best effort)
      try {
        const images = await Promise.all(
          files.map(async (file) => ({
            name: file.name,
            dataUrl: await readFileAsDataUrl(file),
          }))
        );

        const last = {
          id: "report_" + Date.now(),
          createdAt: new Date().toISOString(),
          meta,
          user_email: userEmail,
          analysis: data,
          images,
          input: { ...form, user_email: userEmail },
        };

        localStorage.setItem("lastAnalysis", JSON.stringify(last));
      } catch {}

      // Go to reports
      setTimeout(() => navigate("/reports"), 900);
    } catch (error) {
      console.error("Upload error:", error);
      setFormMsg(`Error: ${error.message}`);
      setResult(null);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <main className="container narrow">
        <section className="section-pad">
          <h1 className="h-title">Upload</h1>
          <p className="muted">Drag and drop JPG/PNG files or click to browse.</p>

          {/* DROPZONE */}
          <div
            id="dz"
            className="dropzone card"
            tabIndex={0}
            role="button"
            aria-label="Upload images dropzone"
            onClick={onBrowse}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onBrowse();
              }
            }}
            onDragEnter={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onDrop={onDrop}
          >
            <p className="dz-title" style={{ fontWeight: 700 }}>
              Drag &amp; drop your images here
            </p>
            <p className="dz-sub" style={{ color: "var(--muted)" }}>
              or click to browse
            </p>

            <div style={{ fontSize: "2.5rem", margin: "12px 0", animation: "bounce 2s infinite" }}>
              ⬆️
            </div>

            <label
              className="file-btn"
              style={{ marginTop: 10, backgroundColor: "#4CAF50", borderColor: "#388E3C" }}
              onClick={(e) => e.stopPropagation()}
            >
              Choose File
              <input
                ref={fileInputRef}
                id="fileInput"
                type="file"
                accept="image/jpeg,image/png"
                multiple
                onChange={(e) => acceptFiles(e.target.files)}
              />
            </label>

            <p className="q-hint">Tip: Upload multiple images for comparison.</p>
            <p className="q-hint">Max {MAX_IMAGES} images</p>
          </div>

          {/* PREVIEW */}
          <div
            id="preview"
            className="preview-container"
            style={{
              marginTop: 16,
              maxHeight: 300,
              overflow: "auto",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: previews.length > 0 ? 12 : 0,
              backgroundColor: previews.length > 0 ? "var(--bg-alt)" : "transparent",
            }}
          >
            {previews.length === 0 ? (
              <p className="muted" style={{ textAlign: "center", padding: 12 }}>
                No images selected yet
              </p>
            ) : (
              <div
                className="preview"
                style={{
                  display: "grid",
                  gap: 12,
                  gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
                }}
              >
                {previews.map((p, idx) => (
                  <div
                    key={p.url}
                    className="preview-item"
                    style={{
                      position: "relative",
                      overflow: "hidden",
                      borderRadius: "var(--radius)",
                      backgroundColor: "white",
                    }}
                  >
                    <img
                      src={p.url}
                      alt={`Preview: ${p.name}`}
                      style={{
                        width: "100%",
                        height: "150px",
                        objectFit: "cover",
                        display: "block",
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        bottom: 0,
                        left: 0,
                        right: 0,
                        backgroundColor: "rgba(0,0,0,0.7)",
                        color: "white",
                        padding: "4px 6px",
                        fontSize: "0.75rem",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={p.name}
                    >
                      {p.name}
                    </div>
                    <button
                      type="button"
                      className="preview-delete-btn"
                      onClick={() => deleteImage(idx)}
                      style={{
                        position: "absolute",
                        top: 4,
                        right: 4,
                        backgroundColor: "rgba(255, 59, 48, 0.9)",
                        color: "white",
                        border: "none",
                        borderRadius: "50%",
                        width: 28,
                        height: 28,
                        padding: 0,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        cursor: "pointer",
                        fontSize: "1.2rem",
                        fontWeight: "bold",
                      }}
                      aria-label={`Delete ${p.name}`}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* FORM */}
          <form id="intakeForm" className="card" onSubmit={handleSubmit}>
            <h2 className="h-title" style={{ fontSize: "1.25rem" }}>
              Patient Intake
            </h2>
            <p className="section-sub">
              Required fields marked with <span className="req">*</span>
            </p>

            <div className="q-grid">
              <div className="q-card">
                <label className="q-label">
                  Full Name <span className="req">*</span>
                </label>
                <input
                  className="q-input"
                  value={form.name}
                  onChange={(e) => updateField("name", e.target.value)}
                  required
                />
              </div>

              <div className="q-card">
                <label className="q-label">
                  Age <span className="req">*</span>
                </label>
                <input
                  className="q-input"
                  type="number"
                  min="0"
                  max="120"
                  value={form.age}
                  onChange={(e) => updateField("age", e.target.value)}
                  required
                />
              </div>

              <div className="q-card">
                <label className="q-label">
                  Sex <span className="req">*</span>
                </label>
                <select
                  className="q-select"
                  value={form.sex}
                  onChange={(e) => updateField("sex", e.target.value)}
                  required
                >
                  <option value="">Select...</option>
                  <option>Female</option>
                  <option>Male</option>
                  <option>Intersex</option>
                </select>
              </div>

              <div className="q-card">
                <label className="q-label">
                  Skin Condition <span className="req">*</span>
                </label>
                <select
                  className="q-select"
                  value={form.skinType}
                  onChange={(e) => updateField("skinType", e.target.value)}
                  required
                >
                  <option value="">Select...</option>
                  <option value="I">I — Very fair</option>
                  <option value="II">II — Fair</option>
                  <option value="III">III — Medium</option>
                  <option value="IV">IV — Olive</option>
                  <option value="V">V — Brown</option>
                  <option value="VI">VI — Dark brown</option>
                </select>
              </div>

              <div className="q-card">
                <label className="q-label">
                  Location <span className="req">*</span>
                </label>
                <input
                  className="q-input"
                  value={form.location}
                  onChange={(e) => updateField("location", e.target.value)}
                  required
                />
              </div>

              <div className="q-card">
                <label className="q-label">
                  Duration (days) <span className="req">*</span>
                </label>
                <input
                  className="q-input"
                  type="number"
                  min="0"
                  max="3650"
                  value={form.duration}
                  onChange={(e) => updateField("duration", e.target.value)}
                  required
                />
              </div>

              <div className="q-card" style={{ gridColumn: "1 / -1" }}>
                <label className="q-label">Primary Symptoms</label>
                <div className="checkbox-grid">
                  {["Itching", "Bleeding", "Pain", "Rapid change", "Discoloration", "Other"].map((symptom) => (
                    <label key={symptom} className="checkbox-item">
                      <input
                        type="checkbox"
                        checked={form.primarySymptoms.includes(symptom)}
                        onChange={() => toggleSymptom(symptom)}
                      />
                      {symptom}
                    </label>
                  ))}
                </div>
              </div>

              <div className="q-card" style={{ gridColumn: "1 / -1" }}>
                <label className="q-label">Medical Background</label>
                <textarea
                  className="q-input"
                  value={form.medicalBackground}
                  onChange={(e) => updateField("medicalBackground", e.target.value)}
                  placeholder="List relevant medical conditions, treatments, or procedures..."
                  style={{ minHeight: 80, resize: "vertical" }}
                />
              </div>

              <div className="q-card">
                <label className="q-label">Family History</label>
                <select
                  className="q-select"
                  value={form.familyHistory}
                  onChange={(e) => updateField("familyHistory", e.target.value)}
                >
                  <option value="">Select...</option>
                  <option>Skin cancer in family</option>
                  <option>Melanoma in family</option>
                  <option>Both skin cancer and melanoma</option>
                  <option>No family history</option>
                  <option>Unknown</option>
                </select>
              </div>

              <div className="q-card">
                <label className="q-label">Sun Exposure</label>
                <select
                  className="q-select"
                  value={form.sunExposure}
                  onChange={(e) => updateField("sunExposure", e.target.value)}
                >
                  <option value="">Select...</option>
                  <option>Minimal</option>
                  <option>Moderate</option>
                  <option>High</option>
                  <option>Very high (outdoor work)</option>
                  <option>History of severe sunburns</option>
                </select>
              </div>

              <div className="q-card">
                <label className="q-label">SPF Use</label>
                <select
                  className="q-select"
                  value={form.spfUse}
                  onChange={(e) => updateField("spfUse", e.target.value)}
                >
                  <option value="">Select...</option>
                  <option>Never</option>
                  <option>Rarely</option>
                  <option>Sometimes</option>
                  <option>Usually</option>
                  <option>Always</option>
                </select>
              </div>

              <div className="q-card" style={{ gridColumn: "1 / -1" }}>
                <label className="q-label">Current Medications</label>
                <textarea
                  className="q-input"
                  value={form.currentMedications}
                  onChange={(e) => updateField("currentMedications", e.target.value)}
                  placeholder="List current medications, supplements, or treatments..."
                  style={{ minHeight: 80, resize: "vertical" }}
                />
              </div>

              <div className="q-card" style={{ gridColumn: "1 / -1" }}>
                <label>
                  <input
                    id="consent"
                    type="checkbox"
                    checked={form.consent}
                    onChange={(e) => updateField("consent", e.target.checked)}
                  />{" "}
                  I confirm this image is mine and consent to analysis.
                  <span className="req">*</span>
                </label>
              </div>
            </div>

            <div className="form-actions">
              <button className="btn btn-cta" type="submit" disabled={!canAnalyze || isSubmitting}>
                {isSubmitting ? "Analyzing..." : "Analyze"}
              </button>

              <button type="button" className="btn btn-secondary" onClick={clearAll} disabled={isSubmitting}>
                Clear
              </button>

              <span id="formMsg" className="q-hint">
                {formMsg}
              </span>
            </div>
          </form>

          {/* RESULTS */}
          <div id="resultCard" className={`card result ${result ? "show" : ""}`}>
            <h2 style={{ fontSize: "1.25rem", marginBottom: 12 }}>Preliminary Analysis</h2>
            <p className="muted" style={{ marginBottom: 16 }}>{result?.meta || ""}</p>

            {result?.raw && (
              <>
                <div style={{ marginTop: 10 }}>
                  <strong>Primary Result</strong>
                  <div style={{ marginTop: 6 }}>
                    <span className="pill">{result.raw.primary_result ?? "N/A"}</span>
                  </div>
                </div>

                <div style={{ marginTop: 22 }}>
                  <strong style={{ color: "#4a9ff5" }}>Top 3 predictions</strong>
                  <div className="report-predictions">
                    {(result.raw_full?.top_predictions || result.raw_full?.model_topk || [])
                      .slice(0, 3)
                      .map((p, i) => {
                        const label = p.label || p.name || "Unknown";
                        const confidence = p.confidence ?? p.prob ?? 0;
                        return (
                          <div key={i} className="report-prediction">
                            <div>
                              <strong>{normalizeLabel(label)}</strong>
                              <span className="report-prediction-score">{fmtPct(confidence)}</span>
                            </div>
                            <div className="muted report-prediction-desc">{predictionDescription(label)}</div>
                          </div>
                        );
                      })}
                  </div>
                </div>

                <div className="report-next-step">
                  <strong style={{ color: "#4a9ff5" }}>Suggested medical next step</strong>
                  <p className="muted" style={{ marginTop: 6 }}>
                    {nextStepForRisk(result.raw.primary_result)}
                  </p>
                </div>
              </>
            )}
          </div>
        </section>
      </main>

      {!userEmail && showLoginGate && (
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="upload-login-gate-title">
          <div className="modal-content">
            <h2 id="upload-login-gate-title">Login Required</h2>
            <p>Must be logged in to upload image.</p>
            <div className="modal-actions">
              <button className="btn btn-cta" type="button" onClick={() => navigate("/login?next=/upload")}>
                Log In
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => navigate("/")}>
                Back Home
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}