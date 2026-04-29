import { createServerFn } from "@tanstack/react-start";

export type RepoStats = {
  version: string;
  stars: number;
  forks: number;
  pushedAt: string; // ISO
  license: string;
  fetchedAt: string;
};

let cache: { data: RepoStats; at: number } | null = null;
const TTL = 1000 * 60 * 30; // 30 min

export const getRepoStats = createServerFn({ method: "GET" }).handler(
  async (): Promise<RepoStats> => {
    if (cache && Date.now() - cache.at < TTL) return cache.data;

    const fallback: RepoStats = {
      version: "1.3.1",
      stars: 0,
      forks: 0,
      pushedAt: new Date().toISOString(),
      license: "MIT-Attribution",
      fetchedAt: new Date().toISOString(),
    };

    try {
      const ghHeaders = { "User-Agent": "notewise-landing", Accept: "application/vnd.github+json" };
      const [ghRes, releaseRes, pypiRes] = await Promise.all([
        fetch("https://api.github.com/repos/whoisjayd/notewise", { headers: ghHeaders }),
        fetch("https://api.github.com/repos/whoisjayd/notewise/releases/latest", {
          headers: ghHeaders,
        }),
        fetch("https://pypi.org/pypi/notewise/json", {
          headers: { "User-Agent": "notewise-landing" },
        }),
      ]);

      const gh = ghRes.ok ? await ghRes.json() : null;
      const release = releaseRes.ok ? await releaseRes.json() : null;
      const pypi = pypiRes.ok ? await pypiRes.json() : null;

      const releaseVersion = (release?.tag_name as string | undefined)?.replace(/^v/, "");
      const version = releaseVersion ?? pypi?.info?.version ?? fallback.version;
      const pypiUploadedAt = pypi?.releases?.[version]?.[0]?.upload_time_iso_8601;

      const data: RepoStats = {
        version,
        stars: gh?.stargazers_count ?? 0,
        forks: gh?.forks_count ?? 0,
        // Release date (not last edited / pushed_at)
        pushedAt: release?.published_at ?? pypiUploadedAt ?? fallback.pushedAt,
        license: "MIT-Attribution",
        fetchedAt: new Date().toISOString(),
      };
      cache = { data, at: Date.now() };
      return data;
    } catch {
      return fallback;
    }
  },
);
