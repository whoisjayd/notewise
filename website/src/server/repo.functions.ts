import { createServerFn } from "@tanstack/react-start";
import { NOTEWISE_VERSION } from "@/lib/version";

export type RepoStats = {
  version: string;
  stars: number;
  forks: number;
  pushedAt: string; // ISO
  license: string;
  fetchedAt: string;
};

let cache: { data: RepoStats; at: number; ttl: number } | null = null;
let inFlightFetch: Promise<RepoStats> | null = null;
const SUCCESS_TTL = 1000 * 60 * 30; // 30 min
const FAILURE_TTL = 1000 * 60; // 1 min
const FETCH_TIMEOUT_MS = 5000;

async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = FETCH_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

export const getRepoStats = createServerFn({ method: "GET" }).handler(
  async (): Promise<RepoStats> => {
    if (cache && Date.now() - cache.at < cache.ttl) return cache.data;

    if (inFlightFetch) {
      return await inFlightFetch;
    }

    const fallback: RepoStats = {
      version: NOTEWISE_VERSION,
      stars: 0,
      forks: 0,
      pushedAt: new Date().toISOString(),
      license: "MIT",
      fetchedAt: new Date().toISOString(),
    };

    inFlightFetch = (async () => {
      try {
        const ghHeaders = {
          "User-Agent": "notewise-landing",
          Accept: "application/vnd.github+json",
        };
        const [ghRes, releaseRes, pypiRes] = await Promise.all([
          fetchWithTimeout("https://api.github.com/repos/whoisjayd/notewise", {
            headers: ghHeaders,
          }),
          fetchWithTimeout("https://api.github.com/repos/whoisjayd/notewise/releases/latest", {
            headers: ghHeaders,
          }),
          fetchWithTimeout("https://pypi.org/pypi/notewise/json", {
            headers: { "User-Agent": "notewise-landing" },
          }),
        ]);

        const gh = ghRes.ok ? await ghRes.json() : null;
        const release = releaseRes.ok ? await releaseRes.json() : null;
        const pypi = pypiRes.ok ? await pypiRes.json() : null;

        const releaseVersion = (release?.tag_name as string | undefined)?.replace(/^v/, "");
        const version = releaseVersion ?? pypi?.info?.version ?? fallback.version;
        const pypiUploadedAt = pypi?.releases?.[version]?.[0]?.upload_time_iso_8601;
        const resolvedLicense =
          typeof gh?.license?.spdx_id === "string" && gh.license.spdx_id !== "NOASSERTION"
            ? gh.license.spdx_id
            : fallback.license;

        const data: RepoStats = {
          version,
          stars: gh?.stargazers_count ?? 0,
          forks: gh?.forks_count ?? 0,
          // Release date (not last edited / pushed_at)
          pushedAt: release?.published_at ?? pypiUploadedAt ?? fallback.pushedAt,
          license: resolvedLicense,
          fetchedAt: new Date().toISOString(),
        };
        cache = { data, at: Date.now(), ttl: SUCCESS_TTL };
        inFlightFetch = null;
        return data;
      } catch {
        cache = { data: fallback, at: Date.now(), ttl: FAILURE_TTL };
        inFlightFetch = null;
        return fallback;
      }
    })();

    return await inFlightFetch;
  },
);
