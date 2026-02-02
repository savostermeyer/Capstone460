import { useEffect, useMemo, useRef, useState } from "react";
import "../styles/upload.css";

export default function Upload() {
  const MAX_IMAGES = 20;
  const fileInputRef = useRef(null);

  const [files, setFiles] = useState([]); // File[]
  const [previews, setPreviews] = useState([]); // { name, url }[]
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
  const [result, setResult] = useState(null); // demo result object

  // Build object URLs for previews (and clean them up)
  useEffect(() => {
    const next = files.map((f) => ({ name: f.name, url: URL.createObjectURL(f) }));
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
      (form.lesionLocation === "Other" ? form.lesionLocationOther.trim() : form.lesionLocation) &&
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
      // De-dupe by a stable signature (name/size/lastModified).
      const sig = (f) => `${f.name}__${f.size}__${f.lastModified}`;
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

  function updateMulti(key, selectedOptions) {
    const values = Array.from(selectedOptions).map((o) => o.value);
    updateField(key, values);
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

  function handleSubmit(e) {
    e.preventDefault();

    if (!canAnalyze) {
      setFormMsg("Please complete required fields, consent, and add at least 1 image.");
      return;
    }

    // Demo analysis (matches your current “Preliminary Analysis (demo)” idea)
    const now = new Date();
    const meta = `${files.length} image(s) • ${now.toLocaleString()}`;

    const tags = [
      `Age: ${form.age}`,
      `Skin type: ${form.skinType}`,
      `Location: ${form.lesionLocation === "Other" ? form.lesionLocationOther : form.lesionLocation}`,
      `Duration: ${form.duration} day(s)`,
    ];

    setResult({ meta, tags });
    setFormMsg("");
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

          <label className="file-btn" style={{ marginTop: 10 }} onClick={(e) => e.stopPropagation()}>
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
                <option>Intersex</option>
              </select>
              <p className="q-hint">Used only to provide context for the demo analysis.</p>
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
              <p className="q-hint">This is the Fitzpatrick skin type scale (I–VI).</p>
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
              <p className="q-hint">Pick the closest area where the lesion is located.</p>
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
              <p className="q-hint">How long you’ve noticed the lesion (estimate is fine).</p>
            </div>

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

              <p className="q-hint">Select all that apply.</p>

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
              <p className="q-hint">Examples: prior biopsies, chronic skin conditions, immune issues.</p>

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
              <p className="q-hint">Only include immediate family if known.</p>
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
              <p className="q-hint">Think of your typical daily/weekly time in direct sun.</p>
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
              <p className="q-hint">How often you use sunscreen when outdoors.</p>
            </div>

            <div className="q-card" style={{ gridColumn: "1 / -1" }}>
              <label className="q-label">Current medications</label>
              <textarea
                className="q-textarea"
                placeholder="List medications (optional)"
                value={form.medications}
                onChange={(e) => updateField("medications", e.target.value)}
              />
              <p className="q-hint">Optional. You can separate items with commas.</p>
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
            <button className="btn btn-cta" type="submit" disabled={!canAnalyze}>
              Analyze
            </button>

            <button type="button" className="btn btn-secondary" onClick={clearAll}>
              Clear
            </button>

            <span id="formMsg" className="q-hint">
              {formMsg}
            </span>
          </div>
        </form>

        {/* RESULTS */}
        <div id="resultCard" className={`card result ${result ? "show" : ""}`}>
          <h3>Preliminary Analysis (demo)</h3>
          <p id="resultMeta" className="muted">
            {result?.meta || ""}
          </p>
          <div id="resultTags" style={{ marginTop: 6 }}>
            {result?.tags?.map((t) => (
              <span key={t} className="pill">
                {t}
              </span>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
