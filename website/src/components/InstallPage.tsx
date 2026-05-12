import { binaryCommands, type InstallCommand, packageCommands } from "@/lib/installCommands";
import { DOCS_URL, GITHUB_URL } from "@/lib/siteMeta";
import { useCopyFeedback } from "@/lib/useCopyFeedback";
import { FineIcon } from "@/ui/FineIcon";

export function InstallPage() {
  return (
    <main id="main-content" className="min-h-screen bg-background px-5 py-16 sm:px-6 sm:py-24">
      <div className="mx-auto max-w-[980px]">
        <a href="/" className="hover-underline t-mono-meta text-muted-foreground">
          ← Back to website
        </a>

        <section className="mt-12">
          <p className="t-eyebrow">NoteWise installer</p>
          <h1 className="mt-4 max-w-4xl font-display text-[clamp(2.6rem,7vw,5.6rem)] leading-[0.96] tracking-[-0.055em]">
            One short URL.
            <br /> Any shell.
          </h1>
          <p className="mt-6 max-w-2xl t-body">
            Choose the install style that matches your workflow. Python tool installers are usually
            best; the short URL is for standalone binary installs.
          </p>
        </section>

        <div className="mt-10 grid gap-10">
          <InstallOptionGroup
            title="Use Python tooling"
            copy="Best when you already use Python, uv, or pipx. This installs from PyPI."
            commands={packageCommands}
          />

          <InstallOptionGroup
            title="Prefer a standalone binary?"
            copy="Use the short installer endpoint. It downloads the latest GitHub release binary and verifies checksums."
            commands={binaryCommands}
          />
        </div>

        <nav className="mt-10 flex flex-wrap gap-4 t-btn" aria-label="Install page links">
          <a className="hover-underline" href="/">
            Website
          </a>
          <a
            className="hover-underline"
            href={`${DOCS_URL}/start/install`}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Full install docs (opens in a new tab)"
          >
            Full install docs
          </a>
          <a
            className="hover-underline"
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub repository (opens in a new tab)"
          >
            GitHub
          </a>
        </nav>
      </div>
    </main>
  );
}

function InstallOptionGroup({
  title,
  copy,
  commands,
}: {
  title: string;
  copy: string;
  commands: readonly InstallCommand[];
}) {
  return (
    <section>
      <h2 className="font-display text-[clamp(1.35rem,2vw,1.8rem)] tracking-[-0.035em]">{title}</h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-7 text-muted-foreground sm:text-base">
        {copy}
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {commands.map((command) => (
          <CommandCard key={command.id} command={command} />
        ))}
      </div>
    </section>
  );
}

function CommandCard({ command }: { command: InstallCommand }) {
  const { copy, copyState } = useCopyFeedback();

  const handleCopy = async () => {
    await copy(command.command);
  };

  return (
    <article
      className={[
        "min-w-0 rounded-lg border bg-card p-4",
        command.recommended ? "border-stamp/55" : "border-[var(--rule)]",
      ].join(" ")}
    >
      <p className="t-mono-meta text-muted-foreground">{command.label}</p>
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <code className="min-w-0 break-words font-mono text-[13px] font-semibold leading-7 text-foreground sm:text-[14px]">
          {command.command}
        </code>
        <button
          type="button"
          onClick={handleCopy}
          className="hover-feedback inline-flex items-center gap-1.5 rounded-full border border-[var(--rule)] px-3 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.16em]"
          aria-label={`Copy ${command.label} command`}
        >
          <FineIcon
            name={copyState === "copied" ? "check" : copyState === "failed" ? "stop" : "copy"}
            size={11}
          />
          {copyState === "copied" ? "Copied" : copyState === "failed" ? "Failed" : "Copy"}
        </button>
        <span className="sr-only" aria-live="polite">
          {copyState === "copied"
            ? `${command.label} command copied`
            : copyState === "failed"
              ? `Failed to copy ${command.label} command`
              : ""}
        </span>
      </div>
    </article>
  );
}
