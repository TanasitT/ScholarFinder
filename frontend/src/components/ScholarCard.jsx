import { Link } from "react-router-dom";

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
          <span className="score mono">score {relevanceScore.toFixed(3)}</span>
        )}
      </div>
      <div className="meta-row">
        <span>
          {scholar.current_institution_name ?? "Unknown institution"}
          {scholar.current_institution_country_code
            ? ` (${scholar.current_institution_country_code})`
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
