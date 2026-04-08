import { useState, useEffect } from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();
  const [userEmail, setUserEmail] = useState(() =>
    localStorage.getItem("skinai_user") || null
  );

  useEffect(() => {
    function onStorage() {
      setUserEmail(localStorage.getItem("skinai_user") || null);
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function signOut() {
    localStorage.removeItem("skinai_user");
    localStorage.removeItem("skinai_role");
    setUserEmail(null);
    navigate("/login", { replace: true });
  }

  return (
    <header className="site-header" role="banner">
      <div className="container header-inner">
        <Link className="brand" to="/" aria-label="SkinAI Classifier Home">
          <div className="brand-mark" aria-hidden="true">
            AI
          </div>
          <div className="brand-text">
            <strong>SkinAI Classifier</strong>
            <span>Purdue Fort Wayne</span>
          </div>
        </Link>

        <nav className="nav" aria-label="Primary">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            Home
          </NavLink>

          <NavLink
            to="/upload"
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            Upload
          </NavLink>

          <NavLink
            to="/reports"
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            Reports
          </NavLink>

          <NavLink
            to="/team"
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            About Us
          </NavLink>

          <NavLink
            to="/login"
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            onClick={userEmail ? (e) => { e.preventDefault(); signOut(); } : undefined}
          >
            {userEmail ? "Sign Out" : "Login"}
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
