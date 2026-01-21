export default function Footer() {
  return (
    <footer className="site-footer" role="contentinfo">
      <div className="container">
        <p className="footnote">
          © {new Date().getFullYear()} SkinAI Classifier · Senior Capstone Project
          · For demonstration only.
        </p>
      </div>
    </footer>
  );
}
