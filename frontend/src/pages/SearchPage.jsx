import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { pollSearchJob, startSearch } from "../api.js";
import CountryFilterBar from "../components/CountryFilterBar.jsx";
import KeywordSetResults from "../components/KeywordSetResults.jsx";
import SearchProgress from "../components/SearchProgress.jsx";

const MAX_MANUAL_KEYWORD_SETS = 5;

export default function SearchPage() {
  const [title, setTitle] = useState("");
  const [abstract, setAbstract] = useState("");
  const [keywords, setKeywords] = useState("");
  const [allowedCountries, setAllowedCountries] = useState("");
  const [excludedCountries, setExcludedCountries] = useState("");
  const [keywordMode, setKeywordMode] = useState("auto"); // "auto" | "manual"
  const [manualSets, setManualSets] = useState([""]);
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [countryFilter, setCountryFilter] = useState(null);

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

  function updateManualSet(index, value) {
    setManualSets((sets) => sets.map((s, i) => (i === index ? value : s)));
  }

  function addManualSet() {
    setManualSets((sets) => (sets.length < MAX_MANUAL_KEYWORD_SETS ? [...sets, ""] : sets));
  }

  function removeManualSet(index) {
    setManualSets((sets) => (sets.length > 1 ? sets.filter((_, i) => i !== index) : sets));
  }

  async function handleConfirm() {
    setConfirming(false);
    setLoading(true);
    setError(null);
    setResult(null);
    setJob(null);
    setCountryFilter(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const keywordList = keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      const allowedList = allowedCountries
        .split(",")
        .map((c) => c.trim().toUpperCase())
        .filter(Boolean);
      const excludedList = excludedCountries
        .split(",")
        .map((c) => c.trim().toUpperCase())
        .filter(Boolean);
      const manualKeywordSets =
        keywordMode === "manual"
          ? manualSets
              .map((group) => group.split(",").map((k) => k.trim()).filter(Boolean))
              .filter((group) => group.length > 0)
          : null;

      const started = await startSearch({
        title,
        abstract: abstract || null,
        keywords: keywordList,
        allowedCountries: allowedList,
        excludedCountries: excludedList,
        manualKeywordSets,
      });
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
        A local Ollama model first decomposes the paper into 5 distinct keyword-set angles (or use
        your own manual keyword sets below), then each is searched independently: OpenAlex
        discovery, profile enrichment, eligibility filtering, email hunting, and topical ranking.
        This queries OpenAlex live, so it costs a small amount of API budget and can take several
        minutes.
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
          <label>Keyword-set angles</label>
          <div className="keyword-mode-toggle">
            <button
              type="button"
              className={`btn ${keywordMode === "auto" ? "" : "secondary"}`}
              onClick={() => setKeywordMode("auto")}
            >
              Auto-generate (Ollama)
            </button>
            <button
              type="button"
              className={`btn ${keywordMode === "manual" ? "" : "secondary"}`}
              onClick={() => setKeywordMode("manual")}
            >
              Enter manually
            </button>
          </div>
        </div>

        {keywordMode === "auto" ? (
          <div className="field">
            <label htmlFor="keywords">Keywords</label>
            <input
              id="keywords"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="protein folding, deep learning, transformers"
            />
            <small>Comma-separated. Fed to Ollama, which proposes 5 distinct search angles.</small>
          </div>
        ) : (
          <div className="field">
            <label>Manual keyword sets</label>
            <small>
              Each set is its own independent search angle (1-{MAX_MANUAL_KEYWORD_SETS} sets,
              comma-separated keywords per set). Ollama is not called in this mode.
            </small>
            {manualSets.map((group, i) => (
              <div className="manual-keyword-set-row" key={i}>
                <input
                  value={group}
                  onChange={(e) => updateManualSet(i, e.target.value)}
                  placeholder={`Set ${i + 1} keywords, e.g. transformers, protein folding`}
                />
                {manualSets.length > 1 && (
                  <button
                    type="button"
                    className="btn secondary small"
                    onClick={() => removeManualSet(i)}
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
            {manualSets.length < MAX_MANUAL_KEYWORD_SETS && (
              <button type="button" className="btn secondary small" onClick={addManualSet}>
                + Add another set
              </button>
            )}
          </div>
        )}

        <div className="field">
          <label htmlFor="allowedCountries">Only these countries</label>
          <input
            id="allowedCountries"
            value={allowedCountries}
            onChange={(e) => setAllowedCountries(e.target.value)}
            placeholder="US, GB, DE"
          />
          <small>Comma-separated ISO codes. Leave blank to allow any Zone 1/2 country.</small>
        </div>
        <div className="field">
          <label htmlFor="excludedCountries">Exclude these countries</label>
          <input
            id="excludedCountries"
            value={excludedCountries}
            onChange={(e) => setExcludedCountries(e.target.value)}
            placeholder="CN, RU"
          />
          <small>Comma-separated ISO codes, on top of the built-in exclusion rules.</small>
        </div>

        {!confirming && (
          <button type="submit" className="btn" disabled={loading}>
            Run search
          </button>
        )}
      </form>

      {confirming && (
        <div className="banner confirm">
          <span>This will query OpenAlex{keywordMode === "auto" ? " and Ollama" : ""}, and can take several minutes — run it?</span>
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
          <CountryFilterBar
            keywordSetResults={result.keyword_set_results}
            selected={countryFilter}
            onChange={setCountryFilter}
          />
          <KeywordSetResults keywordSetResults={result.keyword_set_results} countryFilter={countryFilter} />
          <p style={{ marginTop: "1.2rem" }}>
            <Link to={`/papers/${result.paper.id}`}>View this search in past papers →</Link>
          </p>
        </>
      )}
    </main>
  );
}
