import { createFileRoute } from "@tanstack/react-router";

import { SitemapPage } from "@/components/SitemapPage";
import { absoluteSiteUrl, docsUrls, siteUrls } from "@/components/sitemapData";

const SITEMAP_CACHE_MAX_AGE_SECONDS = 3600;
const DEFAULT_DOCS_CHANGEFREQ = "weekly";
const DEFAULT_DOCS_PRIORITY = "0.7";

type ParsedAccept = {
  mediaType: string;
  q: number;
};

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function xmlSitemap() {
  const urls = [
    ...siteUrls.map((url) => ({
      loc: absoluteSiteUrl(url.loc),
      changefreq: url.changefreq,
      priority: url.priority,
    })),
    ...docsUrls.map((url) => ({
      loc: absoluteSiteUrl(url.loc),
      changefreq: url.changefreq ?? DEFAULT_DOCS_CHANGEFREQ,
      priority: url.priority ?? DEFAULT_DOCS_PRIORITY,
    })),
  ];

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls
  .map(
    (u) =>
      `  <url><loc>${escapeXml(u.loc)}</loc><changefreq>${escapeXml(u.changefreq)}</changefreq><priority>${escapeXml(String(u.priority))}</priority></url>`,
  )
  .join("\n")}
</urlset>`;
}

function parseAcceptHeader(accept: string): ParsedAccept[] {
  return accept
    .split(",")
    .map((entry) => {
      const [mediaRange = "", ...parameters] = entry.trim().split(";");
      const qParameter = parameters.find((parameter) => parameter.trim().startsWith("q="));
      const parsedQ = qParameter ? Number.parseFloat(qParameter.trim().slice(2)) : 1;
      const q = Number.isFinite(parsedQ) && parsedQ >= 0 ? Math.min(parsedQ, 1) : 0;

      return { mediaType: mediaRange.toLowerCase(), q };
    })
    .filter((entry) => entry.mediaType.length > 0 && entry.q > 0);
}

function maxAcceptedQ(accepted: ParsedAccept[], mediaTypes: readonly string[]) {
  return accepted.reduce((maxQ, entry) => {
    if (mediaTypes.includes(entry.mediaType)) {
      return Math.max(maxQ, entry.q);
    }
    return maxQ;
  }, 0);
}

function wantsHtml(request?: Request) {
  const accept = request?.headers.get("accept") ?? "";
  if (!accept) {
    return false;
  }

  const accepted = parseAcceptHeader(accept);
  const htmlQ = maxAcceptedQ(accepted, ["text/html"]);
  // Treat application/* and */* as XML preferences so CLI clients like curl get XML unless text/html is explicit.
  const xmlQ = maxAcceptedQ(accepted, ["application/xml", "text/xml", "application/*", "*/*"]);

  return htmlQ > 0 && htmlQ >= xmlQ;
}

export const Route = createFileRoute("/sitemap.xml")({
  server: {
    handlers: {
      GET: ({ request, next }) => {
        if (wantsHtml(request) && next) {
          return next();
        }

        return new Response(xmlSitemap(), {
          headers: {
            "Content-Type": "application/xml; charset=utf-8",
            "Cache-Control": `public, max-age=${SITEMAP_CACHE_MAX_AGE_SECONDS}`,
            Vary: "Accept",
          },
        });
      },
    },
  },
  component: SitemapPage,
});
