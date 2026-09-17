import { FineIcon, type IconName } from "@/ui/FineIcon";

type PipelineStep = {
  n: string;
  title: string;
  icon: IconName;
  body: string;
};

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
    body: "Hit? Skip the rest entirely. Otherwise pulls captions from YouTube over a reused connection, rate-limited (default 10/min) and stored verbatim under ~/.notewise.",
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
    body: "LiteLLM routes the chunks through your provider. Concurrency tunable; defaults to 5 parallel videos. Per-token cost is tracked as it goes, with pricing discovered from the endpoint itself for custom or self-hosted setups.",
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
] as const satisfies readonly PipelineStep[];

export function Pipeline() {
  return (
    <section id="pipeline" className="relative scroll-mt-20 bg-background sm:scroll-mt-24">
      <div className="relative mx-auto max-w-[1200px] px-5 sm:px-6 py-20 sm:py-28 md:py-36">
        <div className="max-w-2xl">
          <span className="t-eyebrow">No 03 · Pipeline</span>
          <h2 className="mt-3 t-h2">
            From <em className="text-stamp">URL</em> to filed-away notes, in six small steps.
          </h2>
          <p className="mt-5 t-body max-w-xl">
            Six ordinary steps, not a black box. Each one shows up in the logs, takes a flag if you
            want to change it, and if step four dies, rerunning picks up from cache instead of
            starting over.
          </p>
        </div>

        <div className="relative mt-12 sm:mt-14">
          <div
            aria-hidden="true"
            className="absolute left-[22px] top-3 bottom-3 w-px bg-[var(--rule)]"
          />
          <ol className="space-y-5 sm:space-y-6">
            {steps.map((s) => (
              <li key={s.n} className="group relative flex gap-5 sm:gap-6">
                <span className="relative z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 border-stamp bg-card text-stamp transition-colors duration-150 group-hover:bg-stamp group-hover:text-background">
                  <FineIcon name={s.icon} size={17} />
                </span>
                <div className="hover-feedback flex-1 rounded-lg border border-[var(--rule)] bg-card p-4 sm:p-5">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="t-cardtitle">{s.title}</h3>
                    <span className="t-mono-meta shrink-0 tracking-[0.18em]">{s.n}</span>
                  </div>
                  <p className="mt-1.5 t-meta">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
