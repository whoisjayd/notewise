import { createFileRoute } from "@tanstack/react-router";

import { SitemapPage } from "@/components/SitemapPage";
import { absoluteSiteUrl, docsUrls, siteUrls } from "@/components/sitemapData";

const SITEMAP_CACHE_MAX_AGE_SECONDS = 3600;

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
      changefreq: "weekly",
      priority: "0.7",
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

function wantsHtml(request?: Request) {
  const accept = request?.headers.get("accept")?.toLowerCase() ?? "";
  return accept.includes("text/html");
}

export const Route = createFileRoute("/sitemap.xml")({
  server: {
    handlers: {
      GET: ({ request, next }) => {
        if (wantsHtml(request)) {
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
