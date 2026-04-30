import { createFileRoute } from "@tanstack/react-router";
import { renderToStaticMarkup } from "react-dom/server";
import { SitemapPage } from "@/components/SitemapPage";
import { absoluteSiteUrl, siteUrls } from "@/components/sitemapData";

function wantsBrowserHtml(request: Request) {
  const accept = request.headers.get("accept")?.toLowerCase() ?? "";
  const userAgent = request.headers.get("user-agent")?.toLowerCase() ?? "";

  if (!accept.includes("text/html")) return false;
  return ![
    "bot",
    "crawler",
    "spider",
    "curl",
    "wget",
    "httpie",
    "python-requests",
    "go-http-client",
  ].some((agent) => userAgent.includes(agent));
}

function xmlSitemap(today: string) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${siteUrls
  .map(
    (u) =>
      `  <url><loc>${absoluteSiteUrl(u.loc)}</loc><lastmod>${today}</lastmod><changefreq>${u.changefreq}</changefreq><priority>${u.priority}</priority></url>`,
  )
  .join("\n")}
</urlset>`;
}

function htmlSitemap(today: string) {
  return `<!doctype html>${renderToStaticMarkup(<SitemapPage today={today} />)}`;
}

export const Route = createFileRoute("/sitemap.xml")({
  server: {
    handlers: {
      GET: ({ request }) => {
        const today = new Date().toISOString().split("T")[0];

        if (wantsBrowserHtml(request)) {
          return new Response(htmlSitemap(today), {
            headers: {
              "Content-Type": "text/html; charset=utf-8",
              "Cache-Control": "public, max-age=3600",
              Vary: "Accept, User-Agent",
            },
          });
        }

        return new Response(xmlSitemap(today), {
          headers: {
            "Content-Type": "application/xml; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
            Vary: "Accept, User-Agent",
          },
        });
      },
    },
  },
});
