import ScholarCard from "./ScholarCard.jsx";

export default function KeywordSetResults({ keywordSetResults }) {
  if (!keywordSetResults || keywordSetResults.length === 0) {
    return <div className="empty-state">No keyword sets recorded for this search.</div>;
  }

  return (
    <>
      {keywordSetResults.map((sr) => (
        <div key={sr.keyword_set.id ?? sr.keyword_set.set_index} className="keyword-set-block">
          <div className="keyword-set-header">
            <span className="keyword-set-title">
              Set {sr.keyword_set.set_index} — {sr.keyword_set.label}
            </span>
            <span className="keyword-set-terms mono">{sr.keyword_set.keywords.join(", ")}</span>
          </div>
          {sr.passing_scholars.length === 0 ? (
            <div className="empty-state">No scholars passed every rule for this angle.</div>
          ) : (
            sr.passing_scholars.map((rs) => (
              <ScholarCard
                key={rs.scholar.id}
                scholar={rs.scholar}
                relevanceScore={rs.relevance_score}
                rankPosition={rs.rank_position}
              />
            ))
          )}
        </div>
      ))}
    </>
  );
}
