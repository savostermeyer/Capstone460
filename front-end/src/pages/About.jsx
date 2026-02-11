import { useState } from "react";

const teamMembers = [
  { id: "dw", name: "Damian Williams", role: "Team Lead · Backend", description: "Leads the backend development and system architecture with expertise in machine learning and API design." },
  { id: "sy", name: "Srinithi Yalamanchili", role: "Frontend Lead", description: "Designs and implements the user interface with focus on accessibility and user experience." },
  { id: "mng", name: "Manuel Nieves Garcia", role: "Frontend Developer", description: "Develops responsive frontend components and integrates APIs for seamless user interactions." },
  { id: "ms", name: "Maddie Sidwell", role: "Full Stack Developer", description: "Works across frontend and backend, ensuring smooth integration and optimal system performance." },
  { id: "so", name: "Savannah Ostermeyer", role: "Backend Developer", description: "Handles database management and API development with focus on data security and optimization." }
];

export default function About() {
  const [images, setImages] = useState({});

  const handleImageUpload = (memberId, event) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        setImages(prev => ({
          ...prev,
          [memberId]: e.target.result
        }));
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <main className="container">
      <section className="section-pad" aria-labelledby="about-title">
        <h1 id="about-title" className="h-title" style={{ textAlign: "center", color: "#E0C98D" }}>
          About Our Project
        </h1>

        <p className="muted" style={{ textAlign: "center", maxWidth: "700px", margin: "0 auto 40px" }}>
          This project was developed as part of the Purdue University Senior Capstone Project 2025-2026. Our goal is to design an AI-powered system to assist with early detection of skin diseases using advanced convolutional neural networks. By leveraging machine learning and expert system knowledge, we provide trustworthy, interpretable results for skin disease classification and analysis.
        </p>
      </section>

      <section className="section-pad" aria-labelledby="team-title">
        <h1 id="team-title" className="h-title" style={{ textAlign: "center", color: "#E0C98D" }}>
          Our Team
        </h1>
        <p className="muted" style={{ textAlign: "center", maxWidth: "700px", margin: "0 auto 40px" }}>
          Meet the talented team members behind this project with expertise in backend development, frontend design, and machine learning.
        </p>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "30px",
          maxWidth: "1200px",
          margin: "0 auto"
        }}>
          {teamMembers.map(member => (
            <div key={member.id} style={{
              background: "var(--gold)",
              border: "1px solid var(--border)",
              borderRadius: "12px",
              padding: "20px",
              textAlign: "center",
              boxShadow: "var(--shadow)"
            }}>
              <div style={{
                width: "150px",
                height: "150px",
                borderRadius: "12px",
                background: "#1d1d1d",
                margin: "0 auto 20px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                overflow: "hidden",
                position: "relative",
                cursor: "pointer",
                border: "2px solid #2a2a2a"
              }}>
                {images[member.id] ? (
                  <>
                    <img 
                      src={images[member.id]} 
                      alt={member.name} 
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                    <label htmlFor={`upload-${member.id}`} style={{
                      position: "absolute",
                      inset: 0,
                      background: "rgba(0,0,0,0.5)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      opacity: 0,
                      transition: "opacity 0.3s ease",
                      cursor: "pointer",
                      fontSize: "0.8rem",
                      color: "#E0C98D"
                    }} 
                    onMouseEnter={(e) => e.currentTarget.style.opacity = "1"}
                    onMouseLeave={(e) => e.currentTarget.style.opacity = "0"}
                    >
                      Change Photo
                    </label>
                  </>
                ) : (
                  <label htmlFor={`upload-${member.id}`} style={{
                    cursor: "pointer",
                    color: "#C9C9C9",
                    textAlign: "center",
                    padding: "20px",
                    fontSize: "0.85rem"
                  }}>
                    Click to upload photo
                  </label>
                )}
                <input 
                  id={`upload-${member.id}`}
                  type="file" 
                  accept="image/*"
                  onChange={(e) => handleImageUpload(member.id, e)}
                  style={{ display: "none" }}
                />
              </div>
              <h3 style={{ margin: "15px 0 5px", color: "#111" }}>{member.name}</h3>
              <p style={{ color: "#422d00", fontWeight: "600", fontSize: "0.95rem", margin: "0 0 15px" }}>{member.role}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
