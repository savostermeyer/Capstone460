import { useState } from "react";

const teamMembers = [
  { id: "dw", name: "Damian Williams", role: "Team Lead · Back End", description: "Leads the backend development and system architecture with expertise in machine learning and API design." },
  { id: "sy", name: "Srinithi Yalamanchili", role: "Front End", description: "Designs and implements the user interface with focus on accessibility and user experience." },
  { id: "mng", name: "Manuel Nieves Garcia", role: "Front End", description: "Develops responsive frontend components and integrates APIs for seamless user interactions." },
  { id: "ms", name: "Maddie Sidwell", role: "Back End", description: "Works across frontend and backend, ensuring smooth integration and optimal system performance." },
  { id: "so", name: "Savannah Ostermeyer", role: "Back End", description: "Handles database management and API development with focus on data security and optimization." }
];

export default function Team() {
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
      <section className="section-pad" aria-labelledby="team-title">
        <div style={{ maxWidth: 900, margin: "0 auto 100px", textAlign: "center" }}>
          <h2 style={{ color: "var(--gold)", margin: 0, fontSize: "2rem", fontWeight: 700, letterSpacing: "0.6px" }}>Project Description</h2>
          <p className="muted" style={{ marginTop: 24, lineHeight: 1.7, fontSize: "1rem" }}>
            This Senior Capstone project (2025-2026) develops an AI-driven skin disease classification system that combines convolutional neural networks with expert-system rules to provide explainable, preliminary diagnostic support for clinicians and patients. The system is for demonstration and educational purposes only and is not a substitute for professional medical advice.
          </p>
        </div>

        <h1 id="team-title" className="h-title" style={{ textAlign: "center", color: "#FFFFFF", marginTop: 18 }}>
          Our Team
        </h1>
        <div style={{ display: "flex", justifyContent: "center", margin: "8px 0 22px" }}>
          <div style={{ width: 84, height: 6, background: "var(--gold)", borderRadius: 6, boxShadow: "0 2px 6px rgba(0,0,0,0.25)" }} />
        </div>

        <p className="muted" style={{ textAlign: "center", maxWidth: "760px", margin: "0 auto 18px" }}>
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
