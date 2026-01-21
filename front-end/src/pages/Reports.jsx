import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

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
    try {
      return localStorage.getItem("skinai_user");
    } catch {
      return null;
    }
  }, []);

  // simple auth gate (demo-level, same as old page)
  useEffect(() => {
    if (!userEmail) {
      navigate("/login?next=/reports", { replace: true });
    }
  }, [userEmail, navigate]);

  const storageKey = userEmail ? `skinai_reports_${userEmail}` : null;

  const [reports, setReports] = useState([]);

  // load reports + seed demo if empty
  useEffect(() => {
    if (!storageKey) return;

    const raw = localStorage.getItem(storageKey);
    let data = raw ? JSON.parse(raw) : [];

    if (data.length === 0) {
      data = [
        {
          id: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
          filename: "lesion_2025-10-10_14-32-11.jpg",
          topPredictions: [
            { label: "Melanocytic nevus", confidence: 0.78 },
            { label: "Benign keratosis", confidence: 0.15 },
            { label: "Melanoma (flag for review)", confidence: 0.07 },
          ],
          notes: "Preliminary model output. Not a medical diagnosis.",
        },
      ];
      localStorage.setItem(storageKey, JSON.stringify(data));
    }

    setReports(data);
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
                  <strong>Top predictions</strong>
                  <ul style={{ margin: "6px 0 0 18px" }}>
                    {r.topPredictions.map((p) => (
                      <li key={p.label}>
                        {p.label} — {fmtPct(p.confidence)}
                      </li>
                    ))}
                  </ul>
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
