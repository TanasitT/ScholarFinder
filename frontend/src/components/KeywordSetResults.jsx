import ScholarCard from "./ScholarCard.jsx";

export default function KeywordSetResults({ keywordSetResults, countryFilter }) {
  if (!keywordSetResults || keywordSetResults.length === 0) {
    return <div className="empty-state">No keyword sets recorded for this search.</div>;
  }

  return (
    <>
      {keywordSetResults.map((sr) => {
        const scholars = countryFilter
          ? sr.passing_scholars.filter((rs) =>
              countryFilter.has(rs.scholar.current_institution_country_code)
            )
          : sr.passing_scholars;

        return (
          <div key={sr.keyword_set.id ?? sr.keyword_set.set_index} className="keyword-set-block">
            <div className="keyword-set-header">
              <span className="keyword-set-title">
                Set {sr.keyword_set.set_index} — {sr.keyword_set.label}
                {sr.keyword_set.source === "manual" && (
                  <span className="pill neutral" style={{ marginLeft: "0.5rem" }}>
                    manual
                  </span>
                )}
              </span>
              <span className="keyword-set-terms mono">{sr.keyword_set.keywords.join(", ")}</span>
            </div>
            {scholars.length > 0 && (
              <p className="keyword-set-score-note">
                Scores order results within this set by topical overlap only — they don't affect
                eligibility and aren't comparable across sets.
              </p>
            )}
            {scholars.length === 0 ? (
              <div className="empty-state">
                {sr.passing_scholars.length === 0
                  ? "No scholars passed every rule for this angle."
                  : "No scholars from the selected countries in this set."}
              </div>
            ) : (
              scholars.map((rs) => (
                <ScholarCard
                  key={rs.scholar.id}
                  scholar={rs.scholar}
                  relevanceScore={rs.relevance_score}
                  rankPosition={rs.rank_position}
                />
              ))
            )}
          </div>
        );
      })}
    </>
  );
}
