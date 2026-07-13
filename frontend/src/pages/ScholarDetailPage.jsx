import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getScholar } from "../api.js";

const ZONE_LABEL = {
  zone_1: "Zone 1 (high trust)",
  zone_2: "Zone 2 (medium trust)",
  zone_3: "Zone 3 (never invited)",
  excluded: "Excluded",
};

const EMAIL_PILL = {
  verified: { cls: "pass", label: "verified" },
  unverified: { cls: "warn", label: "unverified" },
  not_found: { cls: "fail", label: "not found" },
};

export default function ScholarDetailPage() {
  const { scholarId } = useParams();
  const [scholar, setScholar] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setScholar(null);
    setError(null);
    getScholar(scholarId)
      .then(setScholar)
      .catch((err) => setError(err.message));
  }, [scholarId]);

  if (error) {
    return (
      <main className="page">
        <div className="banner error">{error}</div>
      </main>
    );
  }

  if (scholar === null) {
    return (
      <main className="page">
        <div className="loading-line">
          <span className="spinner" aria-hidden="true" />
          Loading…
        </div>
      </main>
    );
  }

  const emailPill = EMAIL_PILL[scholar.email_verification_status] ?? EMAIL_PILL.not_found;

  return (
    <main className="page">
      <div className="detail-header">
        <div className="eyebrow">Scholar</div>
        <h1>{scholar.display_name}</h1>
        <div className="kv-line">
          <span className="pill neutral">{ZONE_LABEL[scholar.zone] ?? scholar.zone}</span>
          <span className="pill neutral">h-index {scholar.h_index ?? "—"}</span>
          <span className={`pill ${emailPill.cls}`}>
            {scholar.email ?? "no email"} · {emailPill.label}
          </span>
        </div>
      </div>

      <h2 className="section-title">Affiliation</h2>
      <div className="card">
        <div className="kv-line" style={{ marginTop: 0 }}>
          <span>
            <b>Institution:</b> {scholar.current_institution_name ?? "Unknown"}
          </span>
          <span>
            <b>Country:</b> {scholar.current_institution_country_code ?? "—"}
          </span>
          <span>
            <b>Type:</b> {scholar.current_institution_type}
          </span>
        </div>
      </div>

      <h2 className="section-title">Publication record</h2>
      <div className="card">
        <div className="kv-line" style={{ marginTop: 0 }}>
          <span>
            <b>Total papers:</b> {scholar.works_count_total ?? "—"}
          </span>
          <span>
            <b>Recent papers (5y):</b> {scholar.works_count_last_5y ?? "—"}
          </span>
          <span>
            <b>H-index source:</b> {scholar.h_index_source ?? "—"}
          </span>
        </div>
      </div>

      {scholar.research_topics?.length > 0 && (
        <>
          <h2 className="section-title">Research topics</h2>
          <div className="card">{scholar.research_topics.map((t) => t.topic).join(", ")}</div>
        </>
      )}

      <h2 className="section-title">Identity &amp; profile links</h2>
      <div className="card">
        <div className="kv-line" style={{ marginTop: 0 }}>
          <span>
            <b>ORCID:</b> {scholar.orcid ?? "—"}
          </span>
          <span>
            <b>Profile check:</b> {scholar.profile_confirmation_status}
          </span>
        </div>
        <div className="kv-line">
          {scholar.gscholar_search_url && (
            <a href={scholar.gscholar_search_url} target="_blank" rel="noreferrer">
              Google Scholar search →
            </a>
          )}
          {scholar.scopus_search_url && (
            <a href={scholar.scopus_search_url} target="_blank" rel="noreferrer">
              Scopus search →
            </a>
          )}
        </div>
      </div>

      {scholar.email && (
        <>
          <h2 className="section-title">Email</h2>
          <div className="card">
            <div className="kv-line" style={{ marginTop: 0 }}>
              <span>
                <b>Address:</b> {scholar.email}
              </span>
              <span>
                <b>Status:</b> {scholar.email_verification_status}
              </span>
            </div>
            {scholar.email_source && (
              <p style={{ marginTop: "0.6rem", fontSize: "0.85rem", color: "var(--ink-soft)" }}>
                Found at: {scholar.email_source}
              </p>
            )}
          </div>
        </>
      )}

      <p style={{ marginTop: "1.6rem", fontSize: "0.8rem", color: "var(--ink-soft)" }}>
        Last checked: {scholar.last_checked_at ?? "never"}
      </p>
    </main>
  );
}
