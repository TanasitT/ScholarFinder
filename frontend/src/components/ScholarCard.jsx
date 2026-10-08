import { Link } from "react-router-dom";
import { countryLabel } from "../countryNames.js";

const ZONE_LABEL = {
  zone_1: "Zone 1",
  zone_2: "Zone 2",
  zone_3: "Zone 3",
  excluded: "Excluded",
};

const EMAIL_PILL = {
  verified: { cls: "pass", label: "verified" },
  unverified: { cls: "warn", label: "unverified" },
  not_found: { cls: "fail", label: "no email" },
};

export default function ScholarCard({ scholar, relevanceScore, rankPosition }) {
  const emailPill = EMAIL_PILL[scholar.email_verification_status] ?? EMAIL_PILL.not_found;
  const topics = (scholar.research_topics ?? []).slice(0, 4).map((t) => t.topic);

  return (
    <Link to={`/scholars/${scholar.id}`} className="scholar-card">
      <div className="top-row">
        <span className="name">
          {rankPosition ? `${rankPosition}. ` : ""}
          {scholar.display_name}
        </span>
        {relevanceScore != null && (
          <span
            className="score mono"
            title="Topical relevance to this search angle -- how much this scholar's research topics overlap the paper's keywords/title/abstract. Used only to order results within this keyword set, never to decide eligibility. Not on a fixed 0-1 scale, so don't compare it across different searches."
          >
            score {relevanceScore.toFixed(3)} <span className="info-hint">(i)</span>
          </span>
        )}
      </div>
      <div className="meta-row">
        <span>
          {scholar.current_institution_name ?? "Unknown institution"}
          {scholar.current_institution_country_code
            ? ` — ${countryLabel(scholar.current_institution_country_code)}`
            : ""}
        </span>
        <span className="pill neutral">{ZONE_LABEL[scholar.zone] ?? scholar.zone}</span>
        <span className="pill neutral">h-index {scholar.h_index ?? "—"}</span>
        <span className={`pill ${emailPill.cls}`}>
          {scholar.email ?? "no email"} · {emailPill.label}
        </span>
      </div>
      {topics.length > 0 && <div className="topics">{topics.join(", ")}</div>}
    </Link>
  );
}
