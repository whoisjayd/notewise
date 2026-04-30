import { createFileRoute } from "@tanstack/react-router";
import { absoluteSiteUrl, siteUrls } from "@/components/sitemapData";

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function xmlSitemap() {
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${siteUrls
  .map(
    (u) =>
      `  <url><loc>${escapeXml(absoluteSiteUrl(u.loc))}</loc><changefreq>${escapeXml(u.changefreq)}</changefreq><priority>${escapeXml(String(u.priority))}</priority></url>`,
  )
  .join("\n")}
</urlset>`;
}

export const Route = createFileRoute("/sitemap.xml")({
  server: {
    handlers: {
      GET: () => {
        return new Response(xmlSitemap(), {
          headers: {
            "Content-Type": "application/xml; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
            Vary: "Accept",
          },
        });
      },
    },
  },
});
