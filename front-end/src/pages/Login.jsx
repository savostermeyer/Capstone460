import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");

  const nextPath = useMemo(() => {
    const params = new URLSearchParams(location.search);
    // Expect paths like "/reports" instead of "reports.html"
    return params.get("next") || "/reports";
  }, [location.search]);

  function onSubmit(e) {
    e.preventDefault();

    if (!email.trim() || !password.trim()) {
      setMsg("Please enter your email and password.");
      return;
    }

    try {
      localStorage.setItem("skinai_user", email.trim());
    } catch (err) {
      console.error("localStorage error:", err);
    }

    setMsg("Signing in…");

    setTimeout(() => {
      navigate(nextPath);
    }, 300);
  }

  return (
    <main className="container narrow">
      <section className="section-pad" aria-labelledby="login-title">
        <h1 id="login-title" className="h-title">
          Login
        </h1>
        <p className="muted">Sign in to access your saved analysis reports.</p>

        <div className="card" role="region" aria-label="Login form">
          <form id="login-form" autoComplete="on" noValidate onSubmit={onSubmit}>
            <div style={{ display: "grid", gap: 12, maxWidth: 420 }}>
              <label>
                <span style={{ display: "block", marginBottom: 6 }}>Email</span>
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@pfw.edu"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={{
                    width: "100%",
                    padding: 10,
                    borderRadius: 8,
                    border: "1px solid #2a2a2a",
                    background: "#0f0f0f",
                    color: "#ededed",
                  }}
                />
              </label>

              <label>
                <span style={{ display: "block", marginBottom: 6 }}>
                  Password
                </span>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="••••••••"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{
                    width: "100%",
                    padding: 10,
                    borderRadius: 8,
                    border: "1px solid #2a2a2a",
                    background: "#0f0f0f",
                    color: "#ededed",
                  }}
                />
              </label>

              <button type="submit" className="btn btn-cta">
                Sign In
              </button>

              <p id="login-msg" className="muted" aria-live="polite" style={{ marginTop: 4 }}>
                {msg}
              </p>
            </div>
          </form>
        </div>
      </section>
    </main>
  );
}
