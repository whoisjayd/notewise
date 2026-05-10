import { FineIcon, type IconName } from "@/ui/FineIcon";

type FormatItem = {
  id: string;
  label: string;
  note: string;
  icon: IconName;
};

const formats = [
  { id: "md", label: "Markdown", note: "Plain, portable, the source of truth.", icon: "doc" },
  { id: "html", label: "HTML", note: "Self-contained, opens in any browser.", icon: "globe" },
  { id: "pdf", label: "PDF", note: "Typeset, printable, archive-grade.", icon: "bookmark" },
  { id: "docx", label: "DOCX", note: "Edit, annotate, share with non-devs.", icon: "doc" },
  { id: "txt", label: "Transcript .txt", note: "Raw words, no formatting.", icon: "wave" },
  {
    id: "json",
    label: "Transcript .json",
    note: "Word-level timestamps for tooling.",
    icon: "stack",
  },
] as const satisfies readonly FormatItem[];

export function Format() {
  return (
    <section
      id="format"
      className="relative border-t border-[var(--rule)] bg-background py-20 sm:py-28 md:py-36"
    >
      <div className="mx-auto max-w-[1200px] px-5 sm:px-6">
        <div className="grid gap-12 md:grid-cols-[1fr_1.4fr] md:gap-16 lg:gap-20">
          <div className="min-w-0">
            <span className="t-eyebrow">No 02 · Output</span>
            <h2 className="mt-3 t-h2">
              One run. <em className="text-stamp">Six</em>
              <br />
              kinds of paper.
            </h2>
            <p className="mt-5 max-w-md t-body">
              Pick a single format or pass a comma-separated list — NoteWise renders each one from
              the same generated study notes.
            </p>
            <pre className="mt-6 overflow-x-auto rounded-md border border-[var(--rule)] bg-card px-4 py-3 t-code whitespace-pre">
              <span className="text-stamp">›</span> notewise process{" "}
              <span className="text-azure">"…"</span>{" "}
              <span className="text-thread">--format md,html,pdf,docx</span>
            </pre>
            <p className="mt-4 t-mono-meta">
              ¶ PDF rendering supports Latin scripts cleanly; CJK / RTL fall back to HTML.
            </p>
          </div>

          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {formats.map((f, i) => (
              <li key={f.id} className="leaf-card group relative p-4 sm:p-5">
                <div className="flex items-center justify-between">
                  <span className="flex h-9 w-9 items-center justify-center rounded-md border border-[var(--rule)] bg-muted text-stamp">
                    <FineIcon name={f.icon} size={16} />
                  </span>
                  <span className="t-mono-meta uppercase tracking-[0.2em]">.{f.id}</span>
                </div>
                <p className="mt-4 t-cardtitle">{f.label}</p>
                <p className="mt-1.5 t-meta">{f.note}</p>
                <span className="absolute bottom-3 right-3 sm:bottom-4 sm:right-4 font-mono text-[10px] text-muted-foreground/60">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
