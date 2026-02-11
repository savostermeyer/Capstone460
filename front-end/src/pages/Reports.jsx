import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

// Class code mapping (keep these exact)
const CLASS_LABELS = {
  akiec: "Actinic keratosis",
  bcc: "Basal cell carcinoma",
  bkl: "Benign keratosis",
  df: "Dermatofibroma",
  mel: "Melanoma",
  nv: "Melanocytic nevi",
  vasc: "Vascular lesions",
};

// Short “static” descriptions (safe + non-diagnostic)
const CLASS_DESCRIPTIONS = {
  akiec:
    "Often appears as a rough, scaly patch caused by sun exposure. It can sometimes progress, so clinical evaluation is important.",
  bcc:
    "A common skin cancer that may look like a pearly bump or non-healing sore. Usually slow-growing, but should be checked by a clinician.",
  bkl:
    "A benign growth that can look waxy or scaly. Many are harmless, but changes in appearance should be evaluated.",
  df:
    "A typically benign, firm spot often found on the legs. Usually stable, but any rapid changes should be assessed.",
  mel:
    "A potentially serious skin cancer. New, changing, or irregular lesions require prompt medical evaluation.",
  nv:
    "A common mole-like lesion. Most are benign, but changes in size, shape, color, or symptoms warrant evaluation.",
  vasc:
    "A vascular-related lesion that may appear red/purple. Many are benign, but persistent or changing lesions should be checked.",
};

function fmtPct(x) {
  if (typeof x !== "number") return "";
  return (x * 100).toFixed(1) + "%";
}

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Heuristic “low confidence / uncertain” rule (NOT a medical standard)
function needsClinicianPrompt(top1, top2) {
  if (!top1) return true;

  const top1c = typeof top1.confidence === "number" ? top1.confidence : 0;
  const top2c = typeof top2?.confidence === "number" ? top2?.confidence : 0;

  if (top1c < 0.6) return true;
  if (Math.abs(top1c - top2c) < 0.1) return true;

  return false;
}

async function fetchImageObjectUrl({ apiBase, imageId, signal }) {
  const res = await fetch(`${apiBase}/api/images/${encodeURIComponent(imageId)}`, {
    method: "GET",
    credentials: "include",
    signal,
  });
  if (!res.ok) throw new Error(`Failed to fetch image (${res.status})`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

async function tryFetchReportsFromApi({ apiBase, signal }) {
  const res = await fetch(`${apiBase}/api/reports`, {
    method: "GET",
    credentials: "include",
    signal,
  });

  if (!res.ok) return null;

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return null;

  const data = await res.json();

  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.reports)) return data.reports;

  return null;
}

async function tryDeleteReportFromApi({ apiBase, id }) {
  // Best-effort delete
  try {
    await fetch(`${apiBase}/api/reports/${encodeURIComponent(id)}`, {
      method: "DELETE",
      credentials: "include",
    });
  } catch {
    // ignore: UI/localStorage will still update
  }
}

function downloadHtmlReport({ report, imageUrls, userEmail }) {
  const top = (report.topPredictions || []).slice(0, 3);
  const top1 = top[0];
  const top2 = top[1];
  const uncertain = needsClinicianPrompt(top1, top2);

  const imagesHtml = (report.images || [])
    .map((img) => {
      const key = img.imageId || img.filename;
      const url = imageUrls[key];
      if (!url) return "";
      return `<div style="margin: 10px 0;">
        <div style="color:#666; font-size: 12px; margin-bottom: 6px;">${img.filename || ""}</div>
        <img src="${url}" style="max-width: 100%; border: 1px solid #ddd; border-radius: 8px;" />
      </div>`;
    })
    .join("");

  const predsHtml = top.length
    ? `<ol>
        ${top
          .map((p) => {
            const label = CLASS_LABELS[p.code] || p.label || p.code || "Unknown";
            const desc = CLASS_DESCRIPTIONS[p.code] || "";
            const pct = fmtPct(p.confidence);
            return `<li style="margin-bottom: 10px;">
              <div><strong>${label}</strong> — ${pct}</div>
              <div style="color:#444; margin-top: 4px;">${desc}</div>
            </li>`;
          })
          .join("")}
      </ol>`
    : `<p><em>No predictions available yet.</em></p>`;

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>SkinAI Report</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { font-family: Arial, sans-serif; padding: 24px; color: #111; }
    .muted { color: #555; }
    .warn { background: #fff3cd; border: 1px solid #ffe69c; padding: 12px; border-radius: 10px; }
    .box { border: 1px solid #ddd; padding: 14px; border-radius: 12px; margin-top: 12px; }
    h1 { margin: 0 0 6px 0; }
  </style>
</head>
<body>
  <h1>SkinAI Report</h1>
  <div class="muted">Generated: ${fmtDate(report.createdAt)} ${userEmail ? `• User: ${userEmail}` : ""}</div>

  <div class="box">
    <h2 style="margin:0 0 10px 0;">Images</h2>
    ${imagesHtml || "<p><em>No images available.</em></p>"}
  </div>

  <div class="box">
    <h2 style="margin:0 0 10px 0;">Top 3 Predictions</h2>
    ${predsHtml}
  </div>

  <div class="warn" style="margin-top: 14px;">
    <strong>Important:</strong> This report is generated by an AI model and is <strong>not</strong> a medical diagnosis.
    If you are concerned, or if the lesion is new, changing, painful, bleeding, or irregular, seek evaluation by a licensed clinician.
    ${uncertain ? "<div style='margin-top:8px;'><strong>Low confidence / uncertain result:</strong> We recommend consulting a dermatologist for an accurate assessment.</div>" : ""}
  </div>
</body>
</html>`;

  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `skinai_report_${report.id || "report"}.html`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function Reports() {
  const navigate = useNavigate();

  const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

  const userEmail = useMemo(() => {
    try {
      return localStorage.getItem("skinai_user");
    } catch {
      return null;
    }
  }, []);

  const isLoggedIn = Boolean(userEmail);
  const storageKey = userEmail ? `skinai_reports_${userEmail}` : null;
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  // Map (imageId or filename) -> objectURL
  const [imageUrls, setImageUrls] = useState({});
  const urlCleanupRef = useRef(new Set());

  // Load reports: API first, then localStorage
  useEffect(() => {
    if (!isLoggedIn || !storageKey) return;

    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setMsg("");

      try {
        const apiReports = await tryFetchReportsFromApi({
          apiBase: API_BASE,
          signal: controller.signal,
        });
        if (apiReports) {
          setReports(apiReports);
          setLoading(false);
          return;
        }
      } catch (e) {
        if (e?.name !== "AbortError") {
          // silent fallback
        }
      }

      try {
        const raw = localStorage.getItem(storageKey);
        const data = raw ? JSON.parse(raw) : [];
        setReports(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error(err);
        setMsg("Could not load reports.");
        setReports([]);
      } finally {
        setLoading(false);
      }
    }

    load();
    return () => controller.abort();
  }, [isLoggedIn, storageKey, API_BASE]);

  // Load image URLs:
  // - If imageId exists => fetch from backend (/api/images/:id)
  // - Else => try sessionStorage preview (Upload put it there)
  useEffect(() => {
    if (!isLoggedIn) return;
    const controller = new AbortController();

    async function loadImages() {
      const toFetchIds = [];
      const toSetLocal = {};

      for (const r of reports) {
        // Attach previewUrls from sessionStorage (best-effort)
        try {
          const raw = sessionStorage.getItem(`skinai_report_previews_${r.id}`);
          if (raw) {
            const pairs = JSON.parse(raw);
            if (Array.isArray(pairs)) {
              for (const pair of pairs) {
                if (pair?.filename && pair?.previewUrl) {
                  // key by filename (since localStorage report stores filename)
                  toSetLocal[pair.filename] = pair.previewUrl;
                }
              }
            }
          }
        } catch {
          // ignore
        }

        for (const img of r.images || []) {
          if (img?.imageId && !imageUrls[img.imageId]) {
            toFetchIds.push(img.imageId);
          }
        }
      }

      // Set any sessionStorage previews immediately
      if (Object.keys(toSetLocal).length > 0) {
        setImageUrls((prev) => ({ ...prev, ...toSetLocal }));
      }

      const unique = Array.from(new Set(toFetchIds));
      if (unique.length === 0) return;

      const reallyFetch = unique.filter((id) => !imageUrls[id]);
      if (reallyFetch.length === 0) return;

      try {
        const pairs = await Promise.all(
          reallyFetch.map(async (id) => {
            const url = await fetchImageObjectUrl({
              apiBase: API_BASE,
              imageId: id,
              signal: controller.signal,
            });
            return [id, url];
          })
        );

        setImageUrls((prev) => {
          const next = { ...prev };
          for (const [id, url] of pairs) {
            next[id] = url;
            urlCleanupRef.current.add(url);
          }
          return next;
        });
      } catch (e) {
        if (e?.name !== "AbortError") {
          console.error(e);
          setMsg("Some images could not be loaded.");
        }
      }
    }

    loadImages();
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reports, isLoggedIn, API_BASE]);

  // Cleanup created object URLs on unmount
  useEffect(() => {
    return () => {
      for (const url of urlCleanupRef.current) URL.revokeObjectURL(url);
      urlCleanupRef.current.clear();
    };
  }, []);

  function signOut() {
    try {
      localStorage.removeItem("skinai_user");
    } catch {}
    navigate("/login", { replace: true });
  }

  async function deleteReport(id) {
    if (!storageKey) return;

    // Best-effort backend delete (A)
    tryDeleteReportFromApi({ apiBase: API_BASE, id });

    // Always update UI + localStorage
    const next = reports.filter((r) => r.id !== id);
    setReports(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {}

    // Also clear any session previews
    try {
      sessionStorage.removeItem(`skinai_report_previews_${id}`);
    } catch {}
  }

  if (!isLoggedIn) {
    return (
      <main className="container">
        <section className="section-pad" aria-labelledby="reports-title">
          <h1 id="reports-title" className="h-title">
            Reports
          </h1>

          <div className="card">
            <p style={{ marginTop: 0 }}>You must be logged in to view reports.</p>
            <p className="muted">Log in to access saved analysis results and download reports.</p>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Link className="btn btn-cta" to="/login">
                Log in
              </Link>
              <Link className="btn" to="/upload">
                Go to Upload
              </Link>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="container">
      <section className="section-pad" aria-labelledby="reports-title">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <h1 id="reports-title" className="h-title" style={{ margin: 0 }}>
            Reports
          </h1>

          <div>
            <span className="muted">{userEmail ? `Signed in as ${userEmail}` : ""}</span>
            <button className="btn" style={{ marginLeft: 8 }} onClick={signOut}>
              Sign out
            </button>
          </div>
        </div>

        <p className="muted" style={{ marginTop: 8 }}>
          Your saved analysis results are shown below.
        </p>

        {loading && (
          <div className="card">
            <p className="muted" style={{ margin: 0 }}>
              Loading reports…
            </p>
          </div>
        )}

        {msg && (
          <div className="card">
            <p className="muted" style={{ margin: 0 }}>
              {msg}
            </p>
          </div>
        )}

        {!loading && reports.length === 0 ? (
          <div className="card">
            <p style={{ marginTop: 0 }}>No reports yet. Upload images to generate your first report.</p>
            <Link className="btn btn-cta" to="/upload">
              Go to Upload
            </Link>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {reports.map((r) => {
              const top = (r.topPredictions || []).slice(0, 3);
              const top1 = top[0];
              const top2 = top[1];
              const uncertain = needsClinicianPrompt(top1, top2);

              return (
                <div key={r.id} className="card">
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                      flexWrap: "wrap",
                    }}
                  >
                    <div>
                      <h3 style={{ margin: "0 0 4px 0" }}>
                        {r.title || "SkinAI Analysis Report"}
                      </h3>
                      <div className="muted">Created: {fmtDate(r.createdAt)}</div>
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <Link className="btn" to="/upload">
                        Analyze another
                      </Link>
                      <button className="btn" onClick={() => deleteReport(r.id)}>
                        Delete
                      </button>
                    </div>
                  </div>

                  {/* Images */}
                  <div style={{ marginTop: 12 }}>
                    <strong>Image(s)</strong>
                    <div style={{ display: "grid", gap: 10, marginTop: 8 }}>
                      {(r.images || []).map((img, idx) => {
                        const key = img.imageId || img.filename || String(idx);
                        const url =
                          (img.imageId && imageUrls[img.imageId]) ||
                          (img.filename && imageUrls[img.filename]) ||
                          null;

                        return (
                          <div key={key} style={{ display: "grid", gap: 6 }}>
                            <div className="muted" style={{ fontSize: 12 }}>
                              {img.filename || img.imageId || "Image"}
                            </div>
                            {url ? (
                              <img
                                src={url}
                                alt={img.filename || "Uploaded lesion"}
                                style={{
                                  width: "100%",
                                  maxWidth: 520,
                                  borderRadius: 12,
                                  border: "1px solid #2a2a2a",
                                }}
                              />
                            ) : (
                              <div className="muted">Image not available yet.</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Predictions */}
                  <div style={{ marginTop: 14 }}>
                    <strong>Top 3 predictions</strong>

                    {top.length === 0 ? (
                      <p className="muted" style={{ marginTop: 6 }}>
                        No predictions available yet. Backend analysis may still be in progress.
                      </p>
                    ) : (
                      <div style={{ marginTop: 8, display: "grid", gap: 10 }}>
                        {top.map((p, i) => {
                          const label = CLASS_LABELS[p.code] || p.label || p.code || "Unknown";
                          const desc = CLASS_DESCRIPTIONS[p.code] || "";
                          return (
                            <div key={`${p.code || p.label}-${i}`}>
                              <div>
                                <strong>
                                  {i + 1}. {label}
                                </strong>{" "}
                                <span className="muted">— {fmtPct(p.confidence)}</span>
                              </div>
                              {desc && (
                                <div className="muted" style={{ marginTop: 4 }}>
                                  {desc}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <div
                      style={{
                        marginTop: 12,
                        padding: 12,
                        borderRadius: 12,
                        border: "1px solid #3a3a3a",
                        background: "#0f0f0f",
                      }}
                    >
                      <div style={{ fontWeight: 800, marginBottom: 6 }}>
                        Important medical note
                      </div>
                      <div className="muted">
                        This output is generated by an AI model and is <strong>not</strong> a medical
                        diagnosis. If the lesion is new, changing, painful, bleeding, or irregular,
                        seek evaluation by a licensed clinician.
                      </div>

                      {uncertain && (
                        <div className="muted" style={{ marginTop: 10 }}>
                          <strong>Low confidence / uncertain:</strong> The model confidence is low or
                          the top predictions are close. We recommend consulting a dermatologist for
                          an accurate assessment.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Download */}
                  <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                    <button
                      className="btn btn-cta"
                      onClick={() => downloadHtmlReport({ report: r, imageUrls, userEmail })}
                    >
                      Download Report
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
