// scripts/account.js
// Simple account page logic:
// - Redirects to login if not signed in
// - Shows email and basic stats
// - Lets me choose and save my role (patient or doctor)

document.addEventListener("DOMContentLoaded", () => {
  // read logged-in user email
  let email = null;
  try {
    email = localStorage.getItem("skinai_user");
  } catch (e) {
    console.error("localStorage unavailable", e);
  }

  // if not signed in, send to login and come back here
  if (!email) {
    const next = encodeURIComponent("account.html");
    window.location.href = `login.html?next=${next}`;
    return;
  }

  // make sure footer year is set (in case app.js missed it)
  const yearEl = document.getElementById("year");
  if (yearEl && !yearEl.textContent) {
    yearEl.textContent = new Date().getFullYear();
  }

  // basic DOM references
  const emailSpan = document.getElementById("acct-email");
  const reportCountSpan = document.getElementById("acct-report-count");
  const lastReportSpan = document.getElementById("acct-last-report");
  const roleMsg = document.getElementById("role-msg");

  const rolePatient = document.getElementById("role-patient");
  const roleDoctor = document.getElementById("role-doctor");

  const btnReports = document.getElementById("acct-go-reports");
  const btnUpload = document.getElementById("acct-go-upload");
  const btnSignout = document.getElementById("acct-signout");

  if (emailSpan) {
    emailSpan.textContent = email;
  }

  // ---- load reports for this user to show basic stats ----

  let reports = [];
  try {
    const raw = localStorage.getItem(`skinai_reports_${email}`);
    reports = raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.error("Failed to read reports for account page", e);
    reports = [];
  }

  if (reportCountSpan) {
    reportCountSpan.textContent = String(reports.length);
  }

  if (lastReportSpan) {
    if (!reports.length) {
      lastReportSpan.textContent = "None";
    } else {
      // find most recent by createdAt
      let latest = reports[0];
      for (const r of reports) {
        if (r.createdAt && latest.createdAt && r.createdAt > latest.createdAt) {
          latest = r;
        }
      }
      const d = latest.createdAt ? new Date(latest.createdAt) : null;
      lastReportSpan.textContent = d
        ? d.toLocaleString([], {
            year: "numeric",
            month: "short",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })
        : "Unknown";
    }
  }

  // ---- role selection and persistence ----

  const roleKey = `skinai_role_${email}`;
  let currentRole = "patient";

  try {
    const saved = localStorage.getItem(roleKey);
    if (saved === "doctor" || saved === "patient") {
      currentRole = saved;
    }
  } catch (e) {
    console.error("Failed to read saved role", e);
  }

  function updateRoleUI(role) {
    if (rolePatient) rolePatient.checked = role === "patient";
    if (roleDoctor) roleDoctor.checked = role === "doctor";
    if (roleMsg) {
      if (role === "doctor") {
        roleMsg.textContent =
          "Doctor / medical professional mode. This is still a demo interface and does not replace clinical judgment.";
      } else {
        roleMsg.textContent =
          "Patient / general user mode. This tool is a demonstration and not a substitute for a dermatologist.";
      }
    }
  }

  updateRoleUI(currentRole);

  function setRole(role) {
    currentRole = role;
    updateRoleUI(role);
    try {
      localStorage.setItem(roleKey, role);
    } catch (e) {
      console.error("Failed to save role", e);
    }
  }

  if (rolePatient) {
    rolePatient.addEventListener("change", () => {
      if (rolePatient.checked) setRole("patient");
    });
  }

  if (roleDoctor) {
    roleDoctor.addEventListener("change", () => {
      if (roleDoctor.checked) setRole("doctor");
    });
  }

  // ---- buttons ----

  if (btnReports) {
    btnReports.addEventListener("click", () => {
      window.location.href = "reports.html";
    });
  }

  if (btnUpload) {
    btnUpload.addEventListener("click", () => {
      window.location.href = "upload.html";
    });
  }

  if (btnSignout) {
    btnSignout.addEventListener("click", () => {
      try {
        localStorage.removeItem("skinai_user");
      } catch (e) {
        console.error("Failed to clear skinai_user", e);
      }
      window.location.href = "login.html";
    });
  }
});
