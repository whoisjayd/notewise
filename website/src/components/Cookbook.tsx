import { Terminal } from "@/ui/Terminal";

const recipes = [
  {
    title: "Single video, default everything",
    sub: "The most boring, useful command in the project.",
    lines: [
      {
        kind: "prompt" as const,
        text: (
          <>
            <span className="text-foreground">notewise process</span>{" "}
            <span className="text-azure">"https://youtu.be/VIDEO"</span>
          </>
        ),
      },
    ],
    caption: (
      <>
        -&gt; ./output/<code>&lt;title&gt;</code>.md
      </>
    ),
  },
  {
    title: "Full playlist · PDF + DOCX",
    sub: "Hand it the playlist URL and walk away.",
    lines: [
      {
        kind: "prompt" as const,
        text: (
          <>
            <span className="text-foreground">notewise process</span>{" "}
            <span className="text-azure">"https://youtube.com/playlist?list=…"</span>{" "}
            <span className="text-thread">--format md,pdf,docx -o ./course</span>
          </>
        ),
      },
    ],
    caption: "concurrent · respects YOUTUBE_REQUESTS_PER_MINUTE",
  },
  {
    title: "Batch a syllabus from a .txt",
    sub: "One URL per line. Resume on next run.",
    lines: [
      {
        kind: "prompt" as const,
        text: (
          <>
            <span className="text-foreground">notewise process</span>{" "}
            <span className="text-azure">syllabus.txt</span>{" "}
            <span className="text-thread">--quiz</span>
          </>
        ),
      },
    ],
    caption: (
      <>
        -&gt; writes <code>&lt;name&gt;</code>.md and <code>&lt;name&gt;</code>_quiz.md per video
      </>
    ),
  },
  {
    title: "Sign in with ChatGPT — no API key",
    sub: "OAuth device flow; uses your existing ChatGPT account.",
    lines: [
      {
        kind: "prompt" as const,
        text: <span className="text-foreground">notewise auth login chatgpt</span>,
      },
      {
        kind: "prompt" as const,
        text: (
          <>
            <span className="text-foreground">notewise process</span>{" "}
            <span className="text-azure">"…"</span>{" "}
            <span className="text-thread">--model chatgpt/gpt-5.2</span>
          </>
        ),
      },
    ],
    caption: "tokens stored in ~/.notewise/auth.json · also: github_copilot/gpt-5-mini",
  },
];

export function Cookbook() {
  return (
    <section
      id="cookbook"
      className="relative border-t border-[var(--rule)] bg-background py-20 sm:py-28 md:py-36"
    >
      <div className="mx-auto max-w-[1200px] px-5 sm:px-6">
        <div className="max-w-2xl">
          <span className="t-eyebrow">No 05 · Cookbook</span>
          <h2 className="mt-3 t-h2">
            Four commands that cover
            <br />
            most of <em className="text-stamp">a semester</em>.
          </h2>
          <p className="mt-5 t-body max-w-xl">
            Anything more elaborate is a flag away —{" "}
            <code className="t-code text-foreground/85">notewise process --help</code>.
          </p>
        </div>

        <div className="mt-12 sm:mt-14 grid gap-5 md:grid-cols-2">
          {recipes.map((r, i) => (
            <div key={`${r.title}-${i}`} className="leaf-card p-5 sm:p-6">
              <p className="t-eyebrow">Recipe · {String(i + 1).padStart(2, "0")}</p>
              <h3 className="mt-2 t-cardtitle text-balance">{r.title}</h3>
              <p className="mt-1.5 t-meta">{r.sub}</p>
              <div className="mt-4">
                <Terminal title="zsh" lines={r.lines} caption={r.caption} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
