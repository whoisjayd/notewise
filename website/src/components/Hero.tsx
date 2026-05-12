import { GITHUB_URL } from "@/lib/siteMeta";
import { Terminal } from "@/ui/Terminal";
import { FineIcon } from "@/ui/FineIcon";
import type { RepoStats } from "@/server/repo.functions";

function fmtNumber(n: number) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function relativeTime(iso: string) {
  const timestamp = new Date(iso).getTime();
  if (Number.isNaN(timestamp)) return "recently";
  const diff = Date.now() - timestamp;
  const d = Math.floor(diff / 86_400_000);
  if (d < 1) return "today";
  if (d === 1) return "yesterday";
  if (d < 30) return `${d} days ago`;
  const m = Math.floor(d / 30);
  if (m === 1) return "a month ago";
  if (m < 12) return `${m} months ago`;
  const y = Math.floor(m / 12);
  return y === 1 ? "a year ago" : `${y} years ago`;
}

export function Hero({ stats }: { stats: RepoStats }) {
  return (
    <section className="relative overflow-hidden bg-background pt-24 pb-20 sm:pt-28 sm:pb-24 md:pt-36 md:pb-28">
      {/* fine corner ornaments */}
      <svg
        aria-hidden
        className="pointer-events-none absolute left-6 top-24 h-12 w-12 text-stamp/30 hidden md:block"
        viewBox="0 0 48 48"
        fill="none"
        stroke="currentColor"
        strokeWidth="0.8"
      >
        <path d="M2 2h12M2 2v12M2 2l16 16" strokeLinecap="round" />
      </svg>
      <svg
        aria-hidden
        className="pointer-events-none absolute right-6 top-24 h-12 w-12 text-stamp/30 hidden md:block"
        viewBox="0 0 48 48"
        fill="none"
        stroke="currentColor"
        strokeWidth="0.8"
      >
        <path d="M46 2H34M46 2v12M46 2L30 18" strokeLinecap="round" />
      </svg>

      <div className="relative mx-auto max-w-[1200px] px-5 sm:px-6">
        <div className="grid gap-12 xl:grid-cols-[1.05fr_0.95fr] xl:gap-16 items-center">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <span className="stamp">v{stats.version} · stable</span>
              <span className="t-mono-meta">released {relativeTime(stats.pushedAt)}</span>
            </div>

            <h1 className="mt-6 sm:mt-7 t-h1">
              A YouTube link,
              <br />
              turned into <em className="text-stamp">study notes</em>
              <br />
              you actually <span className="marker">keep.</span>
            </h1>

            <p className="mt-6 sm:mt-7 max-w-xl t-lead">
              NoteWise reads a video — or a whole playlist — and writes hierarchical Markdown the
              way a careful student would. Quizzes, transcripts, PDF, DOCX, HTML. Cached locally.
              Through the LLM provider you choose.
            </p>

            <div className="mt-8 sm:mt-9 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-3">
              <a
                href="#install"
                className="hover-feedback inline-flex items-center justify-center gap-2 rounded-full border border-transparent bg-foreground px-5 py-3 t-btn text-background sm:py-2.5"
              >
                Install in 30 seconds
                <FineIcon name="arrow" size={14} />
              </a>
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="hover-feedback inline-flex items-center justify-center gap-2 rounded-full border border-[var(--rule)] px-5 py-3 t-btn sm:py-2.5"
              >
                <FineIcon name="github" size={14} />
                Star on GitHub
                <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 t-mono-meta">
                  <FineIcon name="star" size={10} className="text-stamp" />
                  {fmtNumber(stats.stars)}
                </span>
              </a>
            </div>

            <ul className="mt-9 sm:mt-10 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2.5 t-meta sm:max-w-md">
              {(
                [
                  { i: "playlist", t: "Videos & playlists" },
                  { i: "chapters", t: "Chapter-aware notes" },
                  { i: "route", t: "LiteLLM provider routing" },
                  { i: "doc", t: "MD · HTML · PDF · DOCX" },
                ] as const
              ).map((x) => (
                <li key={x.t} className="flex items-center gap-2">
                  <FineIcon name={x.i} size={14} className="text-stamp" />
                  <span>{x.t}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="relative min-w-0">
            <Terminal
              title="~/notewise"
              lines={[
                {
                  kind: "prompt",
                  text: (
                    <>
                      <span className="text-foreground">notewise process</span>{" "}
                      <span className="text-azure">"https://youtu.be/iDulhoQ2pro"</span>{" "}
                      <span className="text-thread">--quiz --format md,pdf</span>
                    </>
                  ),
                },
                {
                  kind: "muted",
                  text: "→ parsing url · fetching transcript · detecting chapters",
                },
                { kind: "muted", text: "→ chapters: 7 · chunking 4000 / overlap 200" },
                { kind: "muted", text: "→ generating with gemini/gemini-2.5-flash" },
                { kind: "ok", text: "✓ wrote attention_is_all_you_need.md" },
                { kind: "ok", text: "✓ wrote attention_is_all_you_need_quiz.md" },
                { kind: "ok", text: "✓ wrote attention_is_all_you_need.pdf" },
              ]}
              caption="cached · skip on rerun unless --force"
            />

            <ul className="mt-5 flex flex-wrap items-center gap-2 t-mono-meta">
              <li className="flex items-center gap-1.5 rounded-full border border-[var(--rule)] bg-card px-2.5 py-1">
                <span className="h-1.5 w-1.5 rounded-full bg-leaf" />
                attention_is_all_you_need.md
              </li>
              <li className="flex items-center gap-1.5 rounded-full border border-[var(--rule)] bg-card px-2.5 py-1">
                <span className="h-1.5 w-1.5 rounded-full bg-leaf" />
                …_quiz.md
              </li>
              <li className="flex items-center gap-1.5 rounded-full border border-[var(--rule)] bg-card px-2.5 py-1">
                <span className="h-1.5 w-1.5 rounded-full bg-leaf" />
                attention_is_all_you_need.pdf
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
