import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getCurrentUser } from "../auth";

function fmtPct(x) {
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

export default function Reports() {
  const navigate = useNavigate();

  const userEmail = useMemo(() => {
    return getCurrentUser();
  }, []);

  // simple auth gate (demo-level, same as old page)
  useEffect(() => {
    if (!userEmail) {
      navigate("/login?next=/reports", { replace: true });
    }
  }, [userEmail, navigate]);

  const storageKey = userEmail ? `skinai_reports_${userEmail}` : null;
  const [reports, setReports] = useState([]);

  // load reports from backend if available, else fallback to localStorage
  useEffect(() => {
    const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:3720").replace(/\/$/, "");

    async function load() {
      if (API_BASE) {
        try {
          const res = await fetch(`${API_BASE}/reports`);
          if (res.ok) {
            const js = await res.json();
            if (Array.isArray(js) && js.length > 0) {
              setReports(js);
              return;
            }
          }
        } catch (e) {
          console.warn("Could not fetch reports from backend", e);
        }
      }

      if (!storageKey) return;
      const raw = localStorage.getItem(storageKey);
      let data = raw ? JSON.parse(raw) : [];
      setReports(data);
    }

    load();
  }, [storageKey]);

  function signOut() {
    localStorage.removeItem("skinai_user");
    navigate("/login", { replace: true });
  }

  function deleteReport(id) {
    const next = reports.filter((r) => r.id !== id);
    setReports(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  }

  function downloadReport(report) {
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `skinai_report_${report.id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
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
            <span className="muted">
              {userEmail ? `Signed in as ${userEmail}` : ""}
            </span>
            <button className="btn" style={{ marginLeft: 8 }} onClick={signOut}>
              Sign out
            </button>
          </div>
        </div>

        <p className="muted" style={{ marginTop: 8 }}>
          Your saved analysis results are shown below.
        </p>

        {reports.length === 0 ? (
          <div className="card">
            <p>
              No reports yet. Try{" "}
              <Link to="/upload">uploading an image</Link> to generate your first
              report.
            </p>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {reports.map((r) => (
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
                    <h3 style={{ margin: "0 0 4px 0" }}>{r.filename}</h3>
                    <div className="muted">
                      Created: {fmtDate(r.createdAt)}
                    </div>
                  </div>

                  <div>
                    <Link className="btn" to="/upload">
                      Analyze another
                    </Link>
                  </div>
                </div>

                <div style={{ marginTop: 10 }}>
                  <strong>Primary Result</strong>
                  <div style={{ marginTop: 6 }}>
                    {r.analysis?.risk_score || r.primary_result || "N/A"}
                  </div>

                  <strong style={{ display: "block", marginTop: 8 }}>Risk Indicators</strong>
                  <div style={{ marginTop: 6 }}>
                    <span className="pill">High: {String(r.analysis?.risk_score === "high_risk" || r.key_indicators?.high_risk_flag)}</span>
                    <span className="pill">Moderate: {String(r.analysis?.risk_score === "moderate_risk" || r.key_indicators?.moderate_risk_flag)}</span>
                    <span className="pill">Low: {String(r.analysis?.risk_score === "low_risk" || r.key_indicators?.low_risk_flag)}</span>
                  </div>

                  <div style={{ marginTop: 8 }}>
                    <strong>Top predictions</strong>
                    <ul style={{ margin: "6px 0 0 18px" }}>
                      {(r.analysis?.top_predictions || r.topPredictions || []).map((p, i) => (
                        <li key={i}>{p.label} — {fmtPct(p.confidence ?? p.prob ?? 0)}</li>
                      ))}
                    </ul>
                  </div>

                  <p className="muted" style={{ marginTop: 8 }}>
                    {r.notes}
                  </p>
                </div>

                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    marginTop: 12,
                    flexWrap: "wrap",
                  }}
                >
                  <button
                    className="btn"
                    onClick={() => downloadReport(r)}
                  >
                    Download JSON
                  </button>
                  <button
                    className="btn"
                    onClick={() => deleteReport(r.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
