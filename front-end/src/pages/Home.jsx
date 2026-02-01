import { Link } from "react-router-dom";

export default function Home() {
  return (
    <main>
      <section className="hero" role="region" aria-labelledby="hero-title">
        <div className="hero-overlay" />
        <img
          src="/assets/hero.jpg"
          alt=""
          className="hero-bg"
          aria-hidden="true"
        />
        <div className="container hero-inner">
          <span className="badge">Senior Capstone Project 2025</span>
          <h1 id="hero-title" className="hero-title">
            AI-Driven Skin Disease Classification System
          </h1>
          <p className="hero-lead">Early detection, trustworthy results.</p>
          <p className="hero-sub">
            Leveraging advanced convolutional neural networks to assist in the
            early detection and classification of skin diseases, including
            melanoma, with high accuracy and confidence.
          </p>

          <Link className="btn btn-cta" to="/upload">
            Upload Image for Analysis
          </Link>
        </div>
      </section>
    </main>
  );
}
