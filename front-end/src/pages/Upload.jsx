import { useEffect, useMemo, useRef, useState } from "react";
import "../styles/upload.css";

export default function Upload() {
  const fileInputRef = useRef(null);

  const [files, setFiles] = useState([]); // File[]
  const [previews, setPreviews] = useState([]); // { name, url }[]
  const [form, setForm] = useState({
    name: "",
    age: "",
    sex: "",
    skinType: "",
    location: "",
    duration: "",
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
      form.skinType &&
      form.location.trim() &&
      String(form.duration).trim();

    return Boolean(requiredFilled && form.consent && files.length > 0);
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

    setFormMsg("");
    setResult(null);
    setFiles(picked);
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
      location: "",
      duration: "",
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
      `Location: ${form.location}`,
      `Duration: ${form.duration} day(s)`,
    ];

    setResult({ meta, tags });
    setFormMsg("");
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
        <div
          id="preview"
          className="preview"
          style={{
            marginTop: 16,
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          }}
        >
          {previews.map((p) => (
            <img key={p.url} src={p.url} alt={`Preview: ${p.name}`} />
          ))}
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
              <label className="q-label">Sex at Birth</label>
              <select
                className="q-select"
                value={form.sex}
                onChange={(e) => updateField("sex", e.target.value)}
              >
                <option value="">Prefer not to say</option>
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
