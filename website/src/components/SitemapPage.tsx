import { absoluteSiteUrl, DOCS_URL, docsUrls, siteUrls } from "./sitemapData";

export function SitemapPage() {
  return (
    <main id="main-content" className="min-h-screen bg-background px-5 py-16 sm:px-6 sm:py-24">
      <div className="mx-auto max-w-[980px]">
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
                    <a href={absoluteSiteUrl(url.loc)}>
                      <code>{absoluteSiteUrl(url.loc)}</code>
                    </a>
                  </td>
                  <td>{url.title}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </main>
  );
}
