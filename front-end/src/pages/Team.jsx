export default function Team() {
  return (
    <main className="container narrow">
      <section className="section-pad" aria-labelledby="team-title">
        <h1 id="team-title" className="h-title">
          Team
        </h1>
        <p className="muted">Meet the people behind the project.</p>

        <div className="team-grid">
          <div className="member">
            <div className="avatar">DW</div>
            <div>
              <h3>Damian Williams</h3>
              <p className="muted">Team Lead · Back End</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">SY</div>
            <div>
              <h3>Srinithi Yalamanchili</h3>
              <p className="muted">Front End</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">MNG</div>
            <div>
              <h3>Manuel Nieves Garcia</h3>
              <p className="muted">Front End</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">MS</div>
            <div>
              <h3>Maddie Sidwell</h3>
              <p className="muted">Back End</p>
            </div>
          </div>

          <div className="member">
            <div className="avatar">SO</div>
            <div>
              <h3>Savannah Ostermeyer</h3>
              <p className="muted">Back End</p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
