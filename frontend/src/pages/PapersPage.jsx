import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listPapers } from "../api.js";

export default function PapersPage() {
  const [papers, setPapers] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listPapers()
      .then(setPapers)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <main className="page">
      <div className="eyebrow">History</div>
      <h1>Past searches</h1>
      <p className="page-lede">Every paper searched so far, with how many scholars passed all eligibility rules.</p>

      {error && <div className="banner error">{error}</div>}

      {!error && papers === null && (
        <div className="loading-line">
          <span className="spinner" aria-hidden="true" />
          Loading…
        </div>
      )}

      {papers !== null && papers.length === 0 && (
        <div className="empty-state">
          No searches yet. <Link to="/">Run your first search</Link>.
        </div>
      )}

      {papers !== null && papers.length > 0 && (
        <ul className="paper-list">
          {papers.map((p) => (
            <li key={p.id}>
              <Link to={`/papers/${p.id}`}>
                <span className="title">{p.title}</span>
                <span className="meta mono">
                  {p.run_date} · {p.passing_count} passed
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
