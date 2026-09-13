const items = [
  {
    q: "Where do my notes live?",
    a: "Wherever --output points, ./output if you don't say otherwise. The Markdown file is the real artifact; every other format is rendered next to it. Nothing about the video or your notes leaves your machine except the request to your LLM.",
  },
  {
    q: "What about videos without captions?",
    a: "Can't be processed. NoteWise reads YouTube's transcript API and stops there — it doesn't run its own speech-to-text. If a video has no captions, bring your own transcription and feed the text in some other way.",
  },
  {
    q: "Will it cost me money?",
    a: "NoteWise itself is free, MIT-licensed, and always will be. What the model call costs depends entirely on your provider's pricing and your usage — check their docs before you point it at a 40-video playlist.",
  },
  {
    q: "Can I use private or members-only videos?",
    a: "Yes. Export a Netscape-format cookie file, set YOUTUBE_COOKIE_FILE, and NoteWise transcribes anything your own browser session can already watch.",
  },
  {
    q: "Why CLI and not a web app?",
    a: "Because a terminal command drops into cron, CI, your editor, and whatever scripts you already have. A web app would mean re-uploading and re-pasting every time. The notes belong in your repo, not behind someone else's login.",
  },
  {
    q: "How are long videos handled?",
    a: "By default, one file — chapters just become headings inside it. Pass --chapter-directory-output for one file per chapter instead. Videos without chapter markers get chunked into 4,000-token windows with a 200-token overlap, so nothing important falls on a seam.",
  },
];

export function FAQ() {
  return (
    <section
      id="faq"
      className="relative scroll-mt-20 bg-background py-20 sm:scroll-mt-24 sm:py-28 md:py-36"
    >
      <div className="mx-auto max-w-[920px] px-5 sm:px-6">
        <div className="text-center">
          <span className="t-eyebrow">No 06 · Notes in the margin</span>
          <h2 className="mt-3 t-h2">Honest answers, before you install.</h2>
        </div>

        <ul className="mt-12 sm:mt-14 divide-y divide-[var(--rule)] border-y border-[var(--rule)]">
          {items.map((it) => (
            <li key={it.q}>
              <details className="group [&_summary::-webkit-details-marker]:hidden">
                <summary className="-mx-2 flex cursor-pointer items-start justify-between gap-4 rounded-md px-2 py-5 transition-colors duration-150 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stamp/45 focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:gap-6 sm:py-6">
                  <span className="t-cardtitle pr-2 text-balance">{it.q}</span>
                  <span
                    aria-hidden="true"
                    className="mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--rule)] text-stamp transition-transform duration-150 group-open:rotate-45 group-open:bg-stamp/5"
                  >
                    <svg
                      aria-hidden="true"
                      focusable="false"
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
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
