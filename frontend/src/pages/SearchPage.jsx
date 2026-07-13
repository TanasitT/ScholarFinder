import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { pollSearchJob, startSearch } from "../api.js";
import KeywordSetResults from "../components/KeywordSetResults.jsx";
import SearchProgress from "../components/SearchProgress.jsx";

export default function SearchPage() {
  const [title, setTitle] = useState("");
  const [abstract, setAbstract] = useState("");
  const [keywords, setKeywords] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const abortRef = useRef(null);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    setError(null);
    setConfirming(true);
  }

  async function handleConfirm() {
    setConfirming(false);
    setLoading(true);
    setError(null);
    setResult(null);
    setJob(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const keywordList = keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      const started = await startSearch({ title, abstract: abstract || null, keywords: keywordList });
      setJob(started);

      const finished = await pollSearchJob(started.job_id, setJob, { signal: controller.signal });

      if (finished.status === "done") {
        setResult(finished.result);
      } else {
        setError(finished.error ?? "Search failed for an unknown reason.");
      }
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <div className="eyebrow">Find reviewers</div>
      <h1>Search for candidate scholars</h1>
      <p className="page-lede">
        Claude first decomposes the paper into 5 distinct keyword-set angles, then each is
        searched independently: OpenAlex discovery, profile enrichment, eligibility filtering,
        email hunting, and topical ranking. This queries OpenAlex and Claude live, so it costs
        a small amount of API budget and can take several minutes.
      </p>

      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="title">Title</label>
          <input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Deep learning for protein structure prediction"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="abstract">Abstract</label>
          <textarea
            id="abstract"
            value={abstract}
            onChange={(e) => setAbstract(e.target.value)}
            placeholder="Optional, but improves candidate relevance"
          />
        </div>
        <div className="field">
          <label htmlFor="keywords">Keywords</label>
          <input
            id="keywords"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="protein folding, deep learning, transformers"
          />
          <small>Comma-separated</small>
        </div>

        {!confirming && (
          <button type="submit" className="btn" disabled={loading}>
            Run search
          </button>
        )}
      </form>

      {confirming && (
        <div className="banner confirm">
          <span>This will call Claude and query OpenAlex, and can take several minutes — run it?</span>
          <div className="actions">
            <button type="button" className="btn secondary" onClick={() => setConfirming(false)}>
              Cancel
            </button>
            <button type="button" className="btn" onClick={handleConfirm}>
              Confirm &amp; run
            </button>
          </div>
        </div>
      )}

      {loading && <SearchProgress job={job} />}

      {error && <div className="banner error">{error}</div>}

      {result && (
        <>
          <h2 className="section-title">
            {result.evaluated_count} candidates evaluated across {result.keyword_set_results.length}{" "}
            keyword sets
          </h2>
          <KeywordSetResults keywordSetResults={result.keyword_set_results} />
          <p style={{ marginTop: "1.2rem" }}>
            <Link to={`/papers/${result.paper.id}`}>View this search in past papers →</Link>
          </p>
        </>
      )}
    </main>
  );
}
