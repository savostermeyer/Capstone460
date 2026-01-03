import { Routes, Route } from "react-router-dom";

function Home() {
  return <h1>Home</h1>;
}

function Upload() {
  return <h1>Upload</h1>;
}

function Reports() {
  return <h1>Reports</h1>;
}

function Login() {
  return <h1>Login</h1>;
}

function Team() {
  return <h1>Team</h1>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/upload" element={<Upload />} />
      <Route path="/reports" element={<Reports />} />
      <Route path="/login" element={<Login />} />
      <Route path="/team" element={<Team />} />
    </Routes>
  );
}
