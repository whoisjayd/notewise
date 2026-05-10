import { absoluteSiteUrl, docsUrls, siteUrls } from "./sitemapData";

export function SitemapPage() {
  return (
    <main id="main-content" className="min-h-screen bg-background px-5 py-16 sm:px-6 sm:py-24">
      <div className="mx-auto max-w-[980px]">
        <span className="t-eyebrow">Site index</span>
        <h1 className="mt-3 t-h2">NoteWise Sitemap</h1>
        <p className="mt-5 max-w-2xl t-body">
          This is a browser-friendly view of <code>/sitemap.xml</code>. Search engines and
          non-browser clients receive valid XML for <code>notewise.click</code> from the same URL.
        </p>

        <section className="mt-12 sm:mt-14">
          <h2 className="t-cardtitle">Website URLs</h2>
          <div className="mt-4 overflow-x-auto rounded-lg border border-[var(--rule)] bg-card">
            <table className="w-full min-w-[680px] text-left">
              <thead>
                <tr className="border-b border-[var(--rule)] bg-muted t-mono-meta uppercase tracking-[0.18em]">
                  <th className="px-4 py-3 font-inherit">URL</th>
                  <th className="px-4 py-3 font-inherit">Change frequency</th>
                  <th className="px-4 py-3 font-inherit">Priority</th>
                </tr>
              </thead>
              <tbody>
                {siteUrls.map((url) => (
                  <tr key={url.loc} className="border-b border-[var(--rule)] last:border-0">
                    <td className="px-4 py-3">
                      <a className="underline-ink" href={url.loc}>
                        <code>{absoluteSiteUrl(url.loc)}</code>
                      </a>
                    </td>
                    <td className="px-4 py-3 t-meta">{url.changefreq}</td>
                    <td className="px-4 py-3 t-meta">{url.priority}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mt-12 sm:mt-14">
          <h2 className="t-cardtitle">Docs URLs</h2>
          <p className="mt-3 max-w-2xl t-body">
            Docs are served under <code>notewise.click/docs</code>, so the public docs paths are
            listed here alongside their page titles.
          </p>
          <div className="mt-4 overflow-x-auto rounded-lg border border-[var(--rule)] bg-card">
            <table className="w-full min-w-[680px] text-left">
              <thead>
                <tr className="border-b border-[var(--rule)] bg-muted t-mono-meta uppercase tracking-[0.18em]">
                  <th className="px-4 py-3 font-inherit">URL</th>
                  <th className="px-4 py-3 font-inherit">Page</th>
                </tr>
              </thead>
              <tbody>
                {docsUrls.map((url) => (
                  <tr key={url.loc} className="border-b border-[var(--rule)] last:border-0">
                    <td className="px-4 py-3">
                      <a className="underline-ink" href={absoluteSiteUrl(url.loc)}>
                        <code>{absoluteSiteUrl(url.loc)}</code>
                      </a>
                    </td>
                    <td className="px-4 py-3 t-meta">{url.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
