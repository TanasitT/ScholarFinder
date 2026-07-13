const PHASES = [
  { key: "discovering", label: "Discovering candidates" },
  { key: "enriching", label: "Enriching profiles" },
  { key: "filtering", label: "Applying eligibility rules" },
  { key: "email_hunt", label: "Hunting for emails" },
  { key: "ranking", label: "Ranking results" },
];

function parseStage(stage) {
  if (!stage || stage === "starting") return { kind: "starting" };
  if (stage === "generating_keywords") return { kind: "keywords" };
  if (stage === "done") return { kind: "done" };
  const match = /^set_(\d+)_(.+)$/.exec(stage);
  if (match) return { kind: "set", setIndex: Number(match[1]), phase: match[2] };
  return { kind: "unknown" };
}

export default function SearchProgress({ job }) {
  if (!job) return null;

  const parsed = parseStage(job.stage);
  const determinate = job.total > 0;
  const pct = determinate ? Math.min(100, Math.round((job.done / job.total) * 100)) : 0;

  let headline;
  if (parsed.kind === "starting") headline = "Starting";
  else if (parsed.kind === "keywords") headline = "Deriving 5 keyword-set angles with Claude";
  else if (parsed.kind === "done") headline = "Done";
  else if (parsed.kind === "set") {
    const phaseLabel = PHASES.find((p) => p.key === parsed.phase)?.label ?? parsed.phase;
    headline = `Keyword set ${parsed.setIndex} of 5 — ${phaseLabel}`;
  } else {
    headline = job.stage;
  }

  return (
    <div className="search-progress">
      <div className="stage-row">
        <span className="stage-label">{headline}…</span>
        {determinate && (
          <span className="stage-count mono">
            {job.done} / {job.total}
          </span>
        )}
      </div>
      <div className={`progress-track${determinate ? "" : " indeterminate"}`}>
        <div className="progress-fill" style={determinate ? { width: `${pct}%` } : undefined} />
      </div>
      {parsed.kind === "set" && (
        <div className="stage-list">
          {[1, 2, 3, 4, 5].map((n) => (
            <span
              key={n}
              className={
                "stage-chip" +
                (n === parsed.setIndex ? " active" : n < parsed.setIndex ? " complete" : "")
              }
            >
              Set {n}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
