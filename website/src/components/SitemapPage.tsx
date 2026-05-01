import { absoluteSiteUrl, DOCS_URL, docsUrls, siteUrls } from "./sitemapData";

export function SitemapPage({ today }: { today: string }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>NoteWise Sitemap</title>
        <style>{`
          :root { color-scheme: light dark; --bg: #f8fafc; --fg: #0f172a; --muted: #64748b; --card: #ffffff; --rule: rgba(15,23,42,.14); }
          @media (prefers-color-scheme: dark) { :root { --bg: #0b1118; --fg: #eef5fb; --muted: #9aa7b2; --card: #111827; --rule: rgba(238,245,251,.16); } }
          * { box-sizing: border-box; }
          body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: clamp(24px, 6vw, 72px); }
          main { max-width: 980px; margin: 0 auto; }
          p { color: var(--muted); max-width: 62ch; }
          section { margin-top: 34px; }
          table { width: 100%; border-collapse: collapse; margin-top: 28px; overflow: hidden; border: 1px solid var(--rule); border-radius: 12px; background: var(--card); }
          th, td { padding: 14px 16px; border-bottom: 1px solid var(--rule); text-align: left; vertical-align: top; }
          th { color: var(--muted); font-size: 12px; letter-spacing: .14em; text-transform: uppercase; }
          tr:last-child td { border-bottom: 0; }
          a { color: inherit; text-underline-offset: .22em; }
          code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
        `}</style>
      </head>
      <body>
        <main>
          <h1>NoteWise Sitemap</h1>
          <p>
            This is a browser-friendly view of <code>/sitemap.xml</code>. Search engines and
            non-browser clients receive valid XML for <code>notewise.click</code> from the same URL.
          </p>

          <section>
            <h2>Website URLs</h2>
            <table>
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Last modified</th>
                  <th>Change frequency</th>
                  <th>Priority</th>
                </tr>
              </thead>
              <tbody>
                {siteUrls.map((url) => (
                  <tr key={url.loc}>
                    <td>
                      <a href={url.loc}>
                        <code>{absoluteSiteUrl(url.loc)}</code>
                      </a>
                    </td>
                    <td>{today}</td>
                    <td>{url.changefreq}</td>
                    <td>{url.priority}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h2>Docs URLs</h2>
            <p>
              Docs are served under <code>notewise.click/docs</code>, so the public docs paths are
              listed here alongside their page titles.
            </p>
            <table>
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Page</th>
                </tr>
              </thead>
              <tbody>
                {docsUrls.map((url) => (
                  <tr key={url.loc}>
                    <td>
                      <a href={`${DOCS_URL}${url.loc}`}>
                        <code>
                          {DOCS_URL}
                          {url.loc}
                        </code>
                      </a>
                    </td>
                    <td>{url.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </main>
      </body>
    </html>
  );
}
