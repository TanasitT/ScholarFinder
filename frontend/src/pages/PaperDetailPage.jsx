import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getPaper } from "../api.js";
import KeywordSetResults from "../components/KeywordSetResults.jsx";

export default function PaperDetailPage() {
  const { paperId } = useParams();
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    getPaper(paperId)
      .then(setDetail)
      .catch((err) => setError(err.message));
  }, [paperId]);

  if (error) {
    return (
      <main className="page">
        <div className="banner error">{error}</div>
      </main>
    );
  }

  if (detail === null) {
    return (
      <main className="page">
        <div className="loading-line">
          <span className="spinner" aria-hidden="true" />
          Loading…
        </div>
      </main>
    );
  }

  const { paper, keyword_set_results: keywordSetResults } = detail;
  const totalPassing = keywordSetResults.reduce((sum, sr) => sum + sr.passing_scholars.length, 0);

  return (
    <main className="page">
      <div className="detail-header">
        <div className="eyebrow">Paper</div>
        <h1>{paper.title}</h1>
        {paper.abstract && <p>{paper.abstract}</p>}
        <div className="kv-line">
          <span>
            <b>Run date:</b> {paper.run_date}
          </span>
          {paper.keywords.length > 0 && (
            <span>
              <b>Original keywords:</b> {paper.keywords.join(", ")}
            </span>
          )}
        </div>
      </div>

      <h2 className="section-title">
        {totalPassing} scholars passed all eligibility rules across {keywordSetResults.length}{" "}
        keyword sets
      </h2>

      <KeywordSetResults keywordSetResults={keywordSetResults} />
    </main>
  );
}
