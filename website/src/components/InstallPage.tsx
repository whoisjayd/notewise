import { useEffect, useRef, useState } from "react";

import { FineIcon } from "@/ui/FineIcon";

const SITE_URL = "https://notewise.click";

type InstallCommand = {
  label: string;
  command: string;
  recommended?: boolean;
};

const packageCommands: InstallCommand[] = [
  { label: "Recommended · uv tool", command: "uv tool install notewise", recommended: true },
  { label: "Try without installing · uvx", command: "uvx notewise --help" },
  { label: "Isolated CLI · pipx", command: "pipx install notewise" },
  { label: "Plain pip", command: "python -m pip install notewise" },
];

const binaryCommands: InstallCommand[] = [
  { label: "macOS / Linux", command: `curl -fsSL ${SITE_URL}/install | sh` },
  { label: "Windows PowerShell", command: `irm ${SITE_URL}/install | iex` },
];

async function copyCommand(command: string) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(command);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = command;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  try {
    textarea.select();
    if (!document.execCommand("copy")) {
      throw new Error("Copy command was rejected");
    }
  } finally {
    textarea.remove();
  }
}

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
          <a className="hover-underline" href="https://docs.notewise.click/docs/start/install">
            Full install docs
          </a>
          <a className="hover-underline" href="https://github.com/whoisjayd/notewise">
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
  commands: InstallCommand[];
}) {
  return (
    <section>
      <h2 className="font-display text-[clamp(1.35rem,2vw,1.8rem)] tracking-[-0.035em]">{title}</h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-7 text-muted-foreground sm:text-base">
        {copy}
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {commands.map((command) => (
          <CommandCard key={command.command} command={command} />
        ))}
      </div>
    </section>
  );
}

function CommandCard({ command }: { command: InstallCommand }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const resetTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    if (resetTimerRef.current !== null) {
      window.clearTimeout(resetTimerRef.current);
    }

    try {
      await copyCommand(command.command);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }

    resetTimerRef.current = window.setTimeout(() => {
      setCopyState("idle");
      resetTimerRef.current = null;
    }, 1400);
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
