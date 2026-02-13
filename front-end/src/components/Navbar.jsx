import { NavLink, Link, useNavigate } from "react-router-dom";
import { getCurrentUser } from "../auth";

export default function Navbar() {
  const navigate = useNavigate();
  const userEmail = getCurrentUser();

  function signOut() {
    try {
      localStorage.removeItem("skinai_user");
    } catch { }
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
            <span>Purdue University</span>
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

          {userEmail ? (
            <button type="button" className="nav-link" onClick={signOut}>
              Logout
            </button>
          ) : (
            <NavLink
              to="/login"
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              Login
            </NavLink>
          )}
        </nav>
      </div>
    </header>
  );
}
