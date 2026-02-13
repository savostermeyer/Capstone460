
//VITE_API_BASE_URL=http://localhost:3000   add to .env
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
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

  // Persistent session id (shared with chatbot widget)
  const sid = useMemo(() => {
    try {
      let existing = localStorage.getItem("skinai_sid");
      if (!existing) {
        existing = "sid_" + Math.random().toString(36).substring(2);
        localStorage.setItem("skinai_sid", existing);
      }
      return existing;
    } catch {
      return "sid_" + Math.random().toString(36).substring(2);
    }
  }, []);
  const [formMsg, setFormMsg] = useState("");
  const [result, setResult] = useState(null); // demo result object

  const [aiMsg, setAiMsg] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  // Build object URLs for previews (and clean them up)
  useEffect(() => {
    const next = files.map((f) => ({
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
      form.skinType &&
      form.location.trim() &&
      String(form.duration).trim();

    return Boolean(requiredFilled && form.consent && files.length > 0);
  }, [form, files]);

  function acceptFiles(fileList) {
    if (!fileList) return;

    const picked = Array.from(fileList).filter((f) =>
      ["image/jpeg", "image/png"].includes(f.type),
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

  async function handleSubmit(e) {
    e.preventDefault();

    if (!canAnalyze) {
      setFormMsg(
        "Please complete required fields, consent, and add at least 1 image.",
      );
      return;
    }

    setFormMsg("Analyzing...");
    setAiMsg("");
    setAiLoading(false);

    try {
      // 1️⃣ Analyze images (Flask)
      const uploadPromises = files.map(async (file) => {
        const formData = new FormData();
        formData.append("image", file);
        // include page so backend/chat won't KeyError
        formData.append("page", "upload");

        // required by Flask
        formData.append("rapid_change", "false");
        formData.append("bleeding", "false");
        formData.append("itching", "false");
        formData.append("pain", "false");

        // intake fields
        formData.append("name", form.name);
        formData.append("age", String(form.age));
        formData.append("sex", form.sex);
        formData.append("skinType", form.skinType);
        formData.append("location", form.location);
        formData.append("duration_days", String(form.duration));
        formData.append("consent", String(form.consent));
        formData.append("uploadDate", new Date().toISOString());

        const response = await fetch(`${API_BASE}/analyze_skin?sid=${encodeURIComponent(sid)}`, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          let msg = `Failed to analyze ${file.name}`;
          try {
            const errJson = await response.json();
            msg = errJson.error || msg;
          } catch {}
          throw new Error(msg);
        }

        return await response.json();
      });

      // ⬅️ IMPORTANT: Promise.all happens OUTSIDE the map
      const results = await Promise.all(uploadPromises);

      const now = new Date();
      const meta = `${results.length} image(s) analyzed • ${now.toLocaleString()}`;
      const first = results[0];
      if (!first) throw new Error("No analysis results returned.");

      // If backend returned the seeded assistant explanation, dispatch it into the chat widget
      try {
        const seedText = first.assistant_seed || first.explanation_summary?.text || "";
        if (seedText) {
          console.debug(
            "[Upload] Dispatching assistant seed to chatbot widget:",
            seedText.substring(0, 100)
          );
          const dispatched = window.dispatchEvent(
            new CustomEvent("skinai:assistantMessage", {
              detail: String(seedText),
              bubbles: true,
              composed: true,
            })
          );
          console.debug("[Upload] dispatchEvent returned:", dispatched);
          window.dispatchEvent(
            new CustomEvent("skinai:open", { bubbles: true, composed: true })
          );
        } else {
          console.warn("[Upload] No assistant_seed found in response");
        }
      } catch (e) {
        console.warn("Could not dispatch assistant seed", e);
      }

      // Normalize new pipeline response into the shape the UI expects
      // new response shape: { top_predictions, risk_score, explanation_summary }
      const normalized = {};
      normalized.primary_result = first.risk_score ?? null;

      // derive key indicators from risk_score
      const rs = (first.risk_score || "").toLowerCase();
      normalized.key_indicators = {
        high_risk_flag: rs === "high_risk",
        moderate_risk_flag: rs === "moderate_risk",
        low_risk_flag: rs === "low_risk",
        needs_clinician_review: rs === "high_risk",
      };

      // model_topk expected as [{label, prob}]
      normalized.model_topk = (first.top_predictions || []).map((p) => ({
        label: p.label,
        prob: p.confidence ?? p.prob ?? 0,
      }));

      // attach explanation/facts for Gemini
      normalized.facts = first.explanation_summary?.facts || first.explanation_summary || {};
      normalized.trace = first.explanation_summary?.trace || [];

      setResult({ meta, raw: normalized, raw_full: first });
      setFormMsg(`✓ Analyzed ${results.length} image(s)`);

      // 2️⃣ Gemini explanation
      setAiLoading(true);

      const chatData = new FormData();
      chatData.append(
        "text",
        "Explain the result in plain language, summarize key risk indicators, and ask any follow-up questions you need.",
      );

      chatData.append("image", files[0]);
      // ensure chat endpoint has page value
      chatData.append("page", "upload");

      chatData.append("name", form.name);
      chatData.append("age", String(form.age));
      chatData.append("sex", form.sex);
      chatData.append("skinType", form.skinType);
      chatData.append("location", form.location);
      chatData.append("duration_days", String(form.duration));

      chatData.append("primary_result", normalized.primary_result ?? "");
      chatData.append("facts", JSON.stringify(normalized.facts ?? {}));
      chatData.append("model_topk", JSON.stringify(normalized.model_topk ?? []));
      chatData.append("trace", JSON.stringify(normalized.trace ?? []));

      // Send the follow-up prompt to the chat endpoint using the same persistent SID
      const chatRes = await fetch(`${API_BASE}/chat?sid=${encodeURIComponent(sid)}`, {
        method: "POST",
        body: chatData,
      });

      const chatJson = await chatRes.json();
      const reply =
        chatJson.reply || chatJson.message || chatJson.assistant || chatJson.text || "";
      setAiMsg(String(reply));

      // Dispatch assistant reply to chat widget and open it
      try {
        console.debug(
          "[Upload] Dispatching Gemini reply to chatbot widget:",
          reply.substring(0, 100)
        );
        const dispatched = window.dispatchEvent(
          new CustomEvent("skinai:assistantMessage", {
            detail: String(reply),
            bubbles: true,
            composed: true,
          })
        );
        console.debug("[Upload] dispatchEvent returned:", dispatched);
        // signal the chat to open
        window.dispatchEvent(
          new CustomEvent("skinai:open", { bubbles: true, composed: true })
        );
      } catch (e) {
        console.warn("Could not dispatch assistant event", e);
      }
      setAiLoading(false);

      // Save lastAnalysis to localStorage with timestamp & input metadata
      try {
        const last = {
          createdAt: new Date().toISOString(),
          meta,
          analysis: first,
          input: {
            name: form.name,
            age: form.age,
            sex: form.sex,
            skinType: form.skinType,
            location: form.location,
            duration_days: form.duration,
          },
        };
        localStorage.setItem("lastAnalysis", JSON.stringify(last));

        // Send to backend reports/save (best-effort)
        fetch(`${API_BASE}/reports/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(last),
        }).catch((err) => console.warn("reports/save failed", err));
      } catch (e) {
        console.warn("Could not save lastAnalysis", e);
      }
    } catch (error) {
      console.error("Analyze error:", error);
      setFormMsg(`Error: ${error.message}`);
      setResult(null);
      setAiMsg("");
      setAiLoading(false);
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
            <button
              className="btn btn-cta"
              type="submit"
              disabled={!canAnalyze}
            >
              Analyze
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={clearAll}
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
          <h3>Preliminary Analysis</h3>

          <p className="muted">{result?.meta || ""}</p>

          {result?.raw && (
            <>
              <div style={{ marginTop: 10 }}>
                <strong>Primary Result:</strong>{" "}
                <span className="pill">
                  {result.raw.primary_result ?? "N/A"}
                </span>
              </div>

              <div style={{ marginTop: 10 }}>
                <strong>Risk Indicators</strong>
                <div style={{ marginTop: 6 }}>
                  <span className="pill">
                    High risk:{" "}
                    {String(result.raw.key_indicators?.high_risk_flag)}
                  </span>
                  <span className="pill">
                    Moderate risk:{" "}
                    {String(result.raw.key_indicators?.moderate_risk_flag)}
                  </span>
                  <span className="pill">
                    Low risk: {String(result.raw.key_indicators?.low_risk_flag)}
                  </span>
                  <span className="pill">
                    Needs clinician review:{" "}
                    {String(result.raw.key_indicators?.needs_clinician_review)}
                  </span>
                </div>
              </div>

              <div style={{ marginTop: 10 }}>
                <strong>Top Predictions</strong>
                <div style={{ marginTop: 6 }}>
                  {(result.raw_full?.top_predictions || result.raw?.model_topk || [])
                    .slice(0, 5)
                    .map((p, i) => (
                      <span key={i} className="pill">
                        {p.label || p["label"]}: {Number(p.confidence ?? p.prob ?? p["confidence"] ?? p["prob"]).toFixed(3)}
                      </span>
                    ))}
                </div>
              </div>
            </>
          )}
        </div>
        {/* AI explanation moved into chatbot window; assistant message is dispatched to widget */}
      </section>
    </main>
  );
}
