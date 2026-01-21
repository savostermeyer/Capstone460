export default function About() {
  return (
    <main className="container narrow">
      <section className="section-pad" aria-labelledby="about-title">
        <h1 id="about-title" className="h-title">
          About
        </h1>

        <p className="muted">
          This project was developed as part of the Purdue University Senior
          Capstone Project 2025. Our goal is to design an AI-powered system to
          assist with early detection of skin diseases.
        </p>

        <h2>Meet the Team</h2>
        <div className="team-grid">
          <div className="member">
            <div className="avatar">DW</div>
            <div>
              <h3>Damian Williams</h3>
              <p className="muted">Team Lead · Backend</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">SY</div>
            <div>
              <h3>Srinithi Yalamanchili</h3>
              <p className="muted">Frontend</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">MNG</div>
            <div>
              <h3>Manuel Nieves Garcia</h3>
              <p className="muted">Frontend</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">MS</div>
            <div>
              <h3>Maddie Sidwell</h3>
              <p className="muted">Full stack</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">SO</div>
            <div>
              <h3>Savannah Ostermeyer</h3>
              <p className="muted">Backend</p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
