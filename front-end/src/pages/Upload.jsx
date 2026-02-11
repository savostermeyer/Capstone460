import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/upload.css";

/**
 * Shared report schema (stored in localStorage, WITHOUT previewUrl):
 * {
 *   id: string,
 *   createdAt: ISO string,
 *   title: string,
 *   images: [{ imageId?: string, filename: string }],
 *   topPredictions: [{ code?: string, label: string, confidence: number }],
 *   patientInfo?: object
 * }
 *
 * Preview URLs are stored in sessionStorage only:
 * sessionStorage["skinai_report_previews_<reportId>"] = JSON.stringify([{ filename, previewUrl }])
 */

function makeId() {
  // crypto.randomUUID() is great but not universal in older environments
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // fallback: reasonably unique
  return `r_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function fileSig(f) {
  // stable signature for matching previews to files (handles reordering better than idx)
  return `${f.name}__${f.size}__${f.lastModified}`;
}

export default function Upload() {
  const MAX_IMAGES = 20;
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  // If API_BASE is "", fetch will hit same-origin (good when you have a dev proxy)

  const [files, setFiles] = useState([]); // File[]
  const [previews, setPreviews] = useState([]); // { sig, name, url }[]

  const [form, setForm] = useState({
    name: "",
    age: "",
    sex: "",
    skinType: "",
    lesionLocation: "",
    lesionLocationOther: "",
    duration: "",
    primarySymptoms: [],
    primarySymptomsOther: "",
    medicalBackground: "", // yes | no | unsure
    medicalBackgroundDetails: "",
    familyHistory: "", // none | skincancer | melanoma | unsure
    sunExposure: "", // low | moderate | high
    spfUse: "", // never | sometimes | often | daily
    medications: "",
    consent: false,
  });

  const [formMsg, setFormMsg] = useState("");
  const [result, setResult] = useState(null); // { success: bool, topPredictions?: [], message: string }
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Get logged-in user email
  const userEmail = useMemo(() => {
    try {
      return localStorage.getItem("skinai_user");
    } catch {
      return null;
    }
  }, []);

  // Build object URLs for previews (and clean them up)
  useEffect(() => {
    const next = files.map((f) => ({
      sig: fileSig(f),
      name: f.name,
      url: URL.createObjectURL(f),
    }));
    setPreviews(next);

    return () => {
      next.forEach((p) => URL.revokeObjectURL(p.url));
    };
  }, [files]);

  const canAnalyze = useMemo(() => {
    const requiredFilled =
      form.name.trim() &&
      String(form.age).trim() &&
      form.sex &&
      form.skinType &&
      (form.lesionLocation === "Other"
        ? form.lesionLocationOther.trim()
        : form.lesionLocation) &&
      String(form.duration).trim();

    const hasSymptoms = form.primarySymptoms.length > 0;

    return Boolean(requiredFilled && hasSymptoms && form.consent && files.length > 0);
  }, [form, files]);

  function acceptFiles(fileList) {
    if (!fileList) return;

    const picked = Array.from(fileList).filter((f) =>
      ["image/jpeg", "image/png"].includes(f.type)
    );

    if (picked.length === 0) {
      setFormMsg("Please upload JPG or PNG images.");
      return;
    }

    setResult(null);

    setFiles((prev) => {
      const sig = (f) => fileSig(f);
      const seen = new Set(prev.map(sig));
      const merged = [...prev];

      for (const f of picked) {
        const s = sig(f);
        if (!seen.has(s)) {
          merged.push(f);
          seen.add(s);
        }
      }

      if (merged.length > MAX_IMAGES) {
        setFormMsg(`You can upload up to ${MAX_IMAGES} images. Extra files were ignored.`);
        return merged.slice(0, MAX_IMAGES);
      }

      setFormMsg("");
      return merged;
    });
  }

  function removeFileAt(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setResult(null);
  }

  function onDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    acceptFiles(e.dataTransfer.files);
  }

  function onBrowse() {
    fileInputRef.current?.click();
  }

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
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
      lesionLocation: "",
      lesionLocationOther: "",
      duration: "",
      primarySymptoms: [],
      primarySymptomsOther: "",
      medicalBackground: "",
      medicalBackgroundDetails: "",
      familyHistory: "",
      sunExposure: "",
      spfUse: "",
      medications: "",
      consent: false,
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function toggleSymptom(symptom) {
    setForm((prev) => {
      const has = prev.primarySymptoms.includes(symptom);
      const next = has
        ? prev.primarySymptoms.filter((s) => s !== symptom)
        : [...prev.primarySymptoms, symptom];

      return {
        ...prev,
        primarySymptoms: next,
        primarySymptomsOther: next.includes("Other") ? prev.primarySymptomsOther : "",
      };
    });
    setResult(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();

    if (!canAnalyze) {
      setFormMsg("Please complete required fields, consent, and add at least 1 image.");
      return;
    }

    if (!userEmail) {
      setFormMsg("You must be logged in to upload.");
      return;
    }

    setIsSubmitting(true);
    setFormMsg("Uploading and analyzing...");

    try {
      // Send all images and patient info in ONE request to backend.
      // Backend contract: expects "images" (multipart array) and "patientInfo" (JSON string).
      const formData = new FormData();
      files.forEach((file) => formData.append("images", file));

      const patientInfo = {
        name: form.name,
        age: form.age,
        sex: form.sex,
        skinType: form.skinType,
        lesionLocation: form.lesionLocation,
        lesionLocationOther: form.lesionLocationOther,
        durationDays: form.duration,
        primarySymptoms: form.primarySymptoms,
        primarySymptomsOther: form.primarySymptomsOther,
        medicalBackground: form.medicalBackground,
        medicalBackgroundDetails: form.medicalBackgroundDetails,
        familyHistory: form.familyHistory,
        sunExposure: form.sunExposure,
        spfUse: form.spfUse,
        medications: form.medications,
        uploadDate: new Date().toISOString(),
      };

      formData.append("patientInfo", JSON.stringify(patientInfo));

      const response = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
        credentials: "include",
      });

      let data = null;
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        data = await response.json();
      }

      if (!response.ok) {
        const msg = data?.error || `Upload failed (${response.status})`;
        throw new Error(msg);
      }

      // Backend response (suggested):
      // { reportId, topPredictions, images?: [{imageId, filename}] }
      const reportId = data?.reportId || makeId();
      const topPredictions = Array.isArray(data?.topPredictions) ? data.topPredictions : [];

      // Store preview URLs in sessionStorage (NOT localStorage)
      // to support immediate "Upload -> Reports" view without storing object URLs long-term.
      try {
        const previewPairs = files.map((f) => {
          const sig = fileSig(f);
          const p = previews.find((x) => x.sig === sig);
          return {
            filename: f.name,
            previewUrl: p?.url || "",
          };
        });
        sessionStorage.setItem(
          `skinai_report_previews_${reportId}`,
          JSON.stringify(previewPairs)
        );
      } catch {
        // safe to ignore
      }

      // Build image array: prefer backend-provided imageIds; fallback is filename-only.
      const images =
        Array.isArray(data?.images) && data.images.length > 0
          ? data.images.map((img) => ({
              imageId: img.imageId,
              filename: img.filename || img.imageId || "image",
            }))
          : files.map((f) => ({
              filename: f.name,
            }));

      const report = {
        id: reportId,
        createdAt: new Date().toISOString(),
        title: `Lesion Analysis — ${form.lesionLocation || "Unknown location"}`,
        images,
        topPredictions,
        patientInfo: {
          name: form.name,
          age: form.age,
          sex: form.sex,
          skinType: form.skinType,
          lesionLocation: form.lesionLocation,
          lesionLocationOther: form.lesionLocationOther,
          durationDays: form.duration,
        },
      };

      // Save report to localStorage (NO previewUrl here)
      const storageKey = `skinai_reports_${userEmail}`;
      try {
        const existing = localStorage.getItem(storageKey);
        const reports = existing ? JSON.parse(existing) : [];
        reports.unshift(report);
        localStorage.setItem(storageKey, JSON.stringify(reports));
      } catch (err) {
        console.error("Failed to save report to localStorage:", err);
      }

      // Show success result
      if (topPredictions.length > 0) {
        setResult({
          success: true,
          topPredictions,
          message: `✓ Analysis complete. Showing top 3 predictions for ${files.length} image(s).`,
        });
      } else {
        setResult({
          success: true,
          topPredictions: [],
          message: `✓ Uploaded ${files.length} image(s). Backend analysis may still be processing.`,
        });
      }

      setFormMsg("");

      // Navigate to Reports page after short delay so user sees success status
      setTimeout(() => {
        navigate("/reports");
      }, 900);
    } catch (error) {
      console.error("Upload error:", error);
      setFormMsg(`Error: ${error.message}`);
      setResult(null);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
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
          <div style={{ fontSize: "2rem" }}>⬆️</div>
          <p className="dz-title" style={{ fontWeight: 700 }}>
            Drag &amp; drop your images here
          </p>
          <p className="dz-sub" style={{ color: "var(--muted)" }}>
            or click to browse
          </p>

          <label
            className="file-btn"
            style={{ marginTop: 10 }}
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
        </div>

        {/* PREVIEW */}
        <div className="preview-header" style={{ marginTop: 16 }}>
          <p className="muted" style={{ margin: 0 }}>
            Selected images: <strong>{files.length}</strong> / {MAX_IMAGES}
          </p>
        </div>

        <div id="preview" className="preview preview-scroller" aria-label="Selected image previews">
          <div className="preview-grid">
            {previews.map((p, idx) => (
              <div key={p.url} className="preview-item">
                <button
                  type="button"
                  className="preview-remove"
                  aria-label={`Remove ${p.name}`}
                  onClick={() => removeFileAt(idx)}
                >
                  ×
                </button>
                <img src={p.url} alt={`Preview: ${p.name}`} />
                <div className="preview-name" title={p.name}>
                  {p.name}
                </div>
              </div>
            ))}
          </div>
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
              <p className="q-hint">Enter your age in years.</p>
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
              </select>
            </div>

            <div className="q-card">
              <label className="q-label">
                Skin Type <span className="req">*</span>
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
                Location of Lesion <span className="req">*</span>
              </label>
              <select
                className="q-select"
                value={form.lesionLocation}
                onChange={(e) => updateField("lesionLocation", e.target.value)}
                required
              >
                <option value="">Select...</option>
                <option>Face / Neck</option>
                <option>Scalp</option>
                <option>Chest</option>
                <option>Back</option>
                <option>Abdomen</option>
                <option>Arms / Hands</option>
                <option>Legs / Feet</option>
                <option>Other</option>
              </select>

              {form.lesionLocation === "Other" && (
                <input
                  className="q-input"
                  style={{ marginTop: 10 }}
                  placeholder="Describe location"
                  value={form.lesionLocationOther}
                  onChange={(e) => updateField("lesionLocationOther", e.target.value)}
                  required
                />
              )}
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

            {/* Primary symptoms checkboxes */}
            <div className="q-card" style={{ gridColumn: "1 / -1" }}>
              <label className="q-label">
                Primary Symptoms <span className="req">*</span>
              </label>

              <div className="checkbox-grid" role="group" aria-label="Primary symptoms">
                {[
                  "Itching",
                  "Pain",
                  "Bleeding",
                  "Crusting",
                  "Color change",
                  "Size change",
                  "Irregular border",
                  "New lesion",
                  "Other",
                ].map((sym) => (
                  <label key={sym} className="checkbox-item">
                    <input
                      type="checkbox"
                      checked={form.primarySymptoms.includes(sym)}
                      onChange={() => toggleSymptom(sym)}
                    />
                    <span>{sym}</span>
                  </label>
                ))}
              </div>

              {form.primarySymptoms.includes("Other") && (
                <input
                  className="q-input"
                  style={{ marginTop: 10 }}
                  placeholder="Other symptoms (optional)"
                  value={form.primarySymptomsOther}
                  onChange={(e) => updateField("primarySymptomsOther", e.target.value)}
                />
              )}
            </div>

            <div className="q-card" style={{ gridColumn: "1 / -1" }}>
              <label className="q-label">Medical Background</label>
              <select
                className="q-select"
                value={form.medicalBackground}
                onChange={(e) => updateField("medicalBackground", e.target.value)}
              >
                <option value="">Select...</option>
                <option value="no">No relevant history</option>
                <option value="yes">Yes</option>
                <option value="unsure">Not sure</option>
              </select>

              {form.medicalBackground === "yes" && (
                <textarea
                  className="q-textarea"
                  style={{ marginTop: 10 }}
                  placeholder="Briefly describe"
                  value={form.medicalBackgroundDetails}
                  onChange={(e) => updateField("medicalBackgroundDetails", e.target.value)}
                />
              )}
            </div>

            <div className="q-card">
              <label className="q-label">Family history</label>
              <select
                className="q-select"
                value={form.familyHistory}
                onChange={(e) => updateField("familyHistory", e.target.value)}
              >
                <option value="">Select...</option>
                <option value="none">None</option>
                <option value="skincancer">Skin cancer</option>
                <option value="melanoma">Melanoma</option>
                <option value="unsure">Not sure</option>
              </select>
            </div>

            <div className="q-card">
              <label className="q-label">Sun exposure</label>
              <select
                className="q-select"
                value={form.sunExposure}
                onChange={(e) => updateField("sunExposure", e.target.value)}
              >
                <option value="">Select...</option>
                <option value="low">Low</option>
                <option value="moderate">Moderate</option>
                <option value="high">High</option>
              </select>
            </div>

            <div className="q-card">
              <label className="q-label">SPF use</label>
              <select
                className="q-select"
                value={form.spfUse}
                onChange={(e) => updateField("spfUse", e.target.value)}
              >
                <option value="">Select...</option>
                <option value="never">Never</option>
                <option value="sometimes">Sometimes</option>
                <option value="often">Often</option>
                <option value="daily">Daily</option>
              </select>
            </div>

            <div className="q-card" style={{ gridColumn: "1 / -1" }}>
              <label className="q-label">Current medications</label>
              <textarea
                className="q-textarea"
                placeholder="List medications (optional)"
                value={form.medications}
                onChange={(e) => updateField("medications", e.target.value)}
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
              {isSubmitting ? "Uploading..." : "Analyze"}
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={clearAll}
              disabled={isSubmitting}
            >
              Clear
            </button>

            <span id="formMsg" className="q-hint">
              {formMsg}
            </span>
          </div>
        </form>

        {/* RESULTS */}
        <div id="resultCard" className={`card result ${result ? "show" : ""}`}>
          <h3>Analysis Results</h3>
          <p id="resultMeta" className="muted">
            {result?.message || ""}
          </p>

          {result?.success && result?.topPredictions?.length > 0 ? (
            <div id="resultPredictions" style={{ marginTop: 12 }}>
              <strong>Top 3 Predictions:</strong>
              <ul style={{ margin: "8px 0 0 20px" }}>
                {result.topPredictions.slice(0, 3).map((p, i) => (
                  <li key={i}>
                    <strong>{p.label || p.code}</strong> —{" "}
                    {typeof p.confidence === "number" ? `${(p.confidence * 100).toFixed(1)}%` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : result?.success ? (
            <p className="muted" style={{ marginTop: 8 }}>
              Backend processing your images. Check Reports to see results once analysis is complete.
            </p>
          ) : null}
        </div>
      </section>
    </main>
  );
}
