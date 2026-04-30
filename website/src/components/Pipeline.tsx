import { FineIcon } from "@/ui/FineIcon";

const steps = [
  {
    n: "01",
    title: "Resolve",
    icon: "globe",
    body: "Single video, full playlist, or a .txt of URLs. Cookies file optional for age-gated or private content.",
  },
  {
    n: "02",
    title: "Cache check",
    icon: "cache",
    body: "Hit? Skip the rest entirely. Otherwise pulls captions from YouTube, rate-limited (default 10/min) and stored verbatim under ~/.notewise.",
  },
  {
    n: "03",
    title: "Chapter-split",
    icon: "chapters",
    body: "Bundled into one note by default. Pass --chapter-directory-output to write each chapter as its own file. No chapters → 4 000-token chunks, 200-token overlap.",
  },
  {
    n: "04",
    title: "Generate",
    icon: "quill",
    body: "LiteLLM routes the chunks through your provider. Concurrency tunable; defaults to 5 parallel videos.",
  },
  {
    n: "05",
    title: "Render",
    icon: "doc",
    body: "Markdown is the source. HTML, PDF, and DOCX are typeset on top — same content, four surfaces.",
  },
  {
    n: "06",
    title: "Persist",
    icon: "folder",
    body: "Files land in ./output (or wherever -o points). The cache index updates so the next run skips what's already done.",
  },
] as const;

export function Pipeline() {
  return (
    <section id="pipeline" className="relative border-t border-[var(--rule)] bg-background">
      <div className="relative mx-auto max-w-[1200px] px-5 sm:px-6 py-20 sm:py-28 md:py-36">
        <div className="max-w-2xl">
          <>
            <span className="t-eyebrow">No 03 · Pipeline</span>
          </>
          <>
            <h2 className="mt-3 t-h2">
              From <em className="text-stamp">URL</em> to filed-away notes, in six small steps.
            </h2>
          </>
          <>
            <p className="mt-5 t-body max-w-xl">
              Nothing exotic. Each step is observable, tunable through CLI flags, and resumable from
              cache.
            </p>
          </>
        </div>

        <ol className="mt-12 sm:mt-14 grid gap-px overflow-hidden rounded-lg border border-[var(--rule)] bg-[var(--rule)] sm:grid-cols-2 lg:grid-cols-3">
          {steps.map((s, i) => (
            <li key={s.n} className="bg-card p-5 sm:p-7">
              <div className="flex items-start justify-between">
                <span className="flex h-9 w-9 sm:h-10 sm:w-10 items-center justify-center rounded-md border border-[var(--rule)] bg-muted text-stamp">
                  <FineIcon name={s.icon as never} size={17} />
                </span>
                <span className="t-mono-meta tracking-[0.18em]">{s.n}</span>
              </div>
              <h3 className="mt-5 t-cardtitle">{s.title}</h3>
              <p className="mt-2 t-meta">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
