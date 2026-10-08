import { useMemo } from "react";
import { countryLabel } from "../countryNames.js";

// Purely client-side: derives the set of country codes actually present
// across every keyword set's passing scholars and renders them as
// toggleable pills. Selecting one or more narrows what KeywordSetResults
// renders -- no new API call, no effect on the underlying stored/returned
// data.
export default function CountryFilterBar({ keywordSetResults, selected, onChange }) {
  const codes = useMemo(() => {
    const set = new Set();
    for (const sr of keywordSetResults ?? []) {
      for (const rs of sr.passing_scholars) {
        const code = rs.scholar.current_institution_country_code;
        if (code) set.add(code);
      }
    }
    return [...set].sort();
  }, [keywordSetResults]);

  if (codes.length === 0) return null;

  function toggle(code) {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    onChange(next.size > 0 ? next : null);
  }

  return (
    <div className="country-filter-bar">
      <span className="country-filter-label">Filter by country:</span>
      {codes.map((code) => (
        <button
          key={code}
          type="button"
          className={`pill ${selected?.has(code) ? "pass" : "neutral"}`}
          onClick={() => toggle(code)}
        >
          {countryLabel(code)}
        </button>
      ))}
      {selected && selected.size > 0 && (
        <button type="button" className="country-filter-clear" onClick={() => onChange(null)}>
          Clear
        </button>
      )}
    </div>
  );
}
