const BASE = "/api";

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // response wasn't JSON -- keep the generic message
    }
    throw new Error(detail);
  }

  return resp.json();
}

export function listPapers() {
  return request("/papers");
}

export function getPaper(paperId) {
  return request(`/papers/${paperId}`);
}

// A real search can take minutes -- the paper is first decomposed into 5
// keyword-set angles (Claude), then each is searched independently
// (candidate enrichment + email hunting are many sequential external HTTP
// calls). So this doesn't return the result directly -- it starts a
// background job and the caller polls it.
export function startSearch({ title, abstract, keywords, maxPages = 2, resultsPerSet = 5 }) {
  return request("/papers/search", {
    method: "POST",
    body: JSON.stringify({
      title,
      abstract,
      keywords,
      max_pages: maxPages,
      results_per_set: resultsPerSet,
    }),
  });
}

export function getSearchJob(jobId) {
  return request(`/papers/search/${jobId}`);
}

const POLL_INTERVAL_MS = 800;

// Polls a search job until it finishes, calling onProgress with each
// intermediate status. Returns the finished job (status "done" or "error").
export async function pollSearchJob(jobId, onProgress, { signal } = {}) {
  while (true) {
    if (signal?.aborted) throw new DOMException("Polling aborted", "AbortError");

    const job = await getSearchJob(jobId);
    onProgress?.(job);

    if (job.status !== "running") return job;

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

export function getScholar(scholarId) {
  return request(`/scholars/${scholarId}`);
}
