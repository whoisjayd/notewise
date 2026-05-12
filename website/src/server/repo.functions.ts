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
const SUCCESS_TTL = 1000 * 60 * 5; // 5 min
const FAILURE_TTL = 1000 * 60; // 1 min
const FETCH_TIMEOUT_MS = 5000;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

async function readSettledJson(
  result: PromiseSettledResult<Response>,
): Promise<Record<string, unknown> | null> {
  if (result.status !== "fulfilled" || !result.value.ok) {
    return null;
  }

  try {
    return asRecord(await result.value.json());
  } catch {
    return null;
  }
}

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
        const [ghResult, releaseResult, pypiResult] = await Promise.allSettled([
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

        const [gh, release, pypi] = await Promise.all([
          readSettledJson(ghResult),
          readSettledJson(releaseResult),
          readSettledJson(pypiResult),
        ]);

        const releaseTagName = release?.tag_name;
        const releaseVersion =
          typeof releaseTagName === "string" ? releaseTagName.replace(/^v/, "") : undefined;
        const pypiInfo = asRecord(pypi?.info);
        const pypiVersion = typeof pypiInfo?.version === "string" ? pypiInfo.version : undefined;
        const version = releaseVersion ?? pypiVersion ?? fallback.version;
        const pypiReleases = asRecord(pypi?.releases);
        const pypiReleasesForVersion = pypiReleases?.[version];
        const pypiReleaseFiles = Array.isArray(pypiReleasesForVersion)
          ? pypiReleasesForVersion
          : [];
        const pypiReleaseFile = asRecord(pypiReleaseFiles[0]);
        const pypiUploadedAt =
          typeof pypiReleaseFile?.upload_time_iso_8601 === "string"
            ? pypiReleaseFile.upload_time_iso_8601
            : undefined;
        const ghLicense = asRecord(gh?.license);
        const ghLicenseId = ghLicense?.spdx_id;
        const resolvedLicense =
          typeof ghLicenseId === "string" && ghLicenseId !== "NOASSERTION"
            ? ghLicenseId
            : fallback.license;
        const stars = typeof gh?.stargazers_count === "number" ? gh.stargazers_count : 0;
        const forks = typeof gh?.forks_count === "number" ? gh.forks_count : 0;
        const releasePublishedAt =
          typeof release?.published_at === "string" ? release.published_at : undefined;

        const data: RepoStats = {
          version,
          stars,
          forks,
          // Release date (not last edited / pushed_at)
          pushedAt: releasePublishedAt ?? pypiUploadedAt ?? fallback.pushedAt,
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
