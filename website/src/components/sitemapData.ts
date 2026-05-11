export { absoluteSiteUrl, DOCS_URL } from "@/lib/siteMeta";

type SitemapEntry = {
  loc: string;
  changefreq: string;
  priority: string;
};

type DocsSitemapEntry = {
  loc: string;
  title: string;
  changefreq?: string;
  priority?: string;
};

export const siteUrls: readonly SitemapEntry[] = [
  { loc: "/", changefreq: "weekly", priority: "1.0" },
  { loc: "/install", changefreq: "monthly", priority: "0.8" },
] as const;

export const docsUrls: readonly DocsSitemapEntry[] = [
  { loc: "/docs", title: "Docs home", changefreq: "weekly", priority: "0.8" },
  { loc: "/docs/start/install", title: "Install NoteWise" },
  { loc: "/docs/start/quickstart", title: "Quickstart" },
  { loc: "/docs/config/configuration", title: "Configuration" },
  { loc: "/docs/config/providers", title: "Providers" },
  { loc: "/docs/config/oauth", title: "OAuth providers" },
  { loc: "/docs/use/process", title: "Process videos" },
  { loc: "/docs/use/playlists-batches", title: "Playlists and batches" },
  { loc: "/docs/use/private-docker", title: "Private videos and Docker" },
  { loc: "/docs/operate/commands", title: "CLI commands" },
  { loc: "/docs/operate/cache-logs-history", title: "Cache, logs, and history" },
  { loc: "/docs/operate/troubleshooting", title: "Troubleshooting" },
  { loc: "/docs/understand/pipeline-output", title: "Pipeline output" },
  { loc: "/docs/understand/storage-events", title: "Storage and events" },
  { loc: "/docs/understand/development", title: "Development" },
  { loc: "/docs/understand/website-docs", title: "Website and docs" },
] as const;
