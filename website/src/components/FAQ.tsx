import { Reveal } from "@/ui/Reveal";

const items = [
  {
    q: "Where do my notes live?",
    a: "Anywhere you point --output to (default ./output). Markdown is the source; rendered formats sit alongside it. Nothing leaves your machine except the LLM call.",
  },
  {
    q: "What about videos without captions?",
    a: "NoteWise relies on YouTube's transcript API, so videos with disabled or missing captions can't be processed. There's no built-in audio-to-text — bring your own ASR if you need it.",
  },
  {
    q: "Will it cost me money?",
    a: "The default Gemini 2.5 Flash key is free for personal use within Google's quota. Other providers bill by token at their published rates. NoteWise itself is free under MIT-Attribution.",
  },
  {
    q: "Can I use private or members-only videos?",
    a: "Yes — pass a Netscape-format cookie file via YOUTUBE_COOKIE_FILE. Anything your browser can watch, NoteWise can transcribe.",
  },
  {
    q: "Why CLI and not a web app?",
    a: "Because a CLI fits inside cron, CI, your editor, and your existing scripts. A web app would force you to re-upload, re-paste, re-everything. The Markdown belongs in your repo, not in someone else's database.",
  },
  {
    q: "How are long videos handled?",
    a: "Bundled into a single note by default — chapters become headings inside one file. Pass --chapter-directory-output if you want each chapter as its own file. Videos with no chapters are chunked on 4 000-token windows with 200-token overlap so context flows across boundaries.",
  },
];

export function FAQ() {
  return (
    <section id="faq" className="relative py-20 sm:py-28 md:py-36 border-t border-[var(--rule)]">
      <div className="mx-auto max-w-[920px] px-5 sm:px-6">
        <div className="text-center">
          <Reveal>
            <span className="t-eyebrow">No 06 · Notes in the margin</span>
          </Reveal>
          <Reveal delay={60}>
            <h2 className="mt-3 t-h2">Honest answers, before you install.</h2>
          </Reveal>
        </div>

        <ul className="mt-12 sm:mt-14 divide-y divide-[var(--rule)] border-y border-[var(--rule)]">
          {items.map((it, i) => (
            <Reveal key={it.q} as="li" delay={40 * i}>
              <details className="group [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex cursor-pointer items-start justify-between gap-4 sm:gap-6 py-5 sm:py-6 px-2 -mx-2 rounded-md hover:bg-accent/40 transition-colors">
                  <span className="t-cardtitle pr-2 text-balance">{it.q}</span>
                  <span className="mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--rule)] text-stamp transition-transform group-open:rotate-45 group-open:bg-stamp/5">
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 12 12"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                    >
                      <path d="M6 1v10M1 6h10" />
                    </svg>
                  </span>
                </summary>
                <p className="pb-6 pl-2 -mt-1 max-w-prose t-body">{it.a}</p>
              </details>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
