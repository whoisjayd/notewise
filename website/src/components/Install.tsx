import { binaryCommands, packageCommands } from "@/lib/installCommands";
import { DOCS_URL } from "@/lib/siteMeta";
import { Terminal } from "@/ui/Terminal";
import { FineIcon } from "@/ui/FineIcon";

const [uvToolCommand, uvxCommand, pipxCommand, pipCommand] = packageCommands;
const [posixBinaryCommand, powershellBinaryCommand] = binaryCommands;

export function Install() {
  return (
    <section
      id="install"
      aria-labelledby="install-heading"
      className="relative scroll-mt-20 border-t border-[var(--rule)] bg-background sm:scroll-mt-24"
    >
      <div className="relative mx-auto max-w-[920px] px-5 sm:px-6 py-20 sm:py-28 md:py-36 text-center">
        <span className="t-eyebrow">Coda · Install</span>
        <h2 id="install-heading" className="mt-3 t-h2">
          Pick a video. <em className="text-stamp">Keep</em> what you learn.
        </h2>
        <p className="mx-auto mt-5 max-w-xl t-body">
          Use Python tooling when you want the PyPI package. Prefer the short installer when you
          want the standalone binary from GitHub releases.
        </p>

        <div className="mx-auto mt-9 sm:mt-10 max-w-2xl text-left">
          <Terminal
            title="notewise.click/install"
            lines={[
              { kind: "muted", text: "# recommended Python tool install" },
              {
                kind: "prompt",
                text: <span className="text-foreground">{uvToolCommand.command}</span>,
              },
              { kind: "muted", text: "" },
              { kind: "muted", text: "# try without installing" },
              {
                kind: "prompt",
                text: <span className="text-foreground">{uvxCommand.command}</span>,
              },
              { kind: "muted", text: "" },
              { kind: "muted", text: "# pipx / pip" },
              {
                kind: "prompt",
                text: <span className="text-foreground">{pipxCommand.command}</span>,
              },
              {
                kind: "prompt",
                text: <span className="text-foreground">{pipCommand.command}</span>,
              },
              { kind: "muted", text: "" },
              { kind: "muted", text: "# prefer standalone binary?" },
              {
                kind: "prompt",
                text: <span className="text-foreground">{posixBinaryCommand.command}</span>,
              },
              { kind: "muted", text: "" },
              { kind: "muted", text: "# Windows binary installer" },
              {
                kind: "prompt",
                text: <span className="text-foreground">{powershellBinaryCommand.command}</span>,
              },
            ]}
            caption="the endpoint returns the right installer for curl, wget, PowerShell, or a browser"
          />
        </div>

        <div className="mt-9 sm:mt-10 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center justify-center gap-3">
          <a
            href="/install"
            className="hover-feedback inline-flex items-center justify-center gap-2 rounded-full border border-transparent bg-foreground px-5 py-3 t-btn text-background sm:py-2.5"
          >
            Open short installer
            <FineIcon name="arrow" size={14} />
          </a>
          <a
            href={DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Full docs (opens in a new tab)"
            className="hover-feedback inline-flex items-center justify-center gap-2 rounded-full border border-[var(--rule)] px-5 py-3 t-btn sm:py-2.5"
          >
            Full docs
            <FineIcon name="external" size={12} className="opacity-70" />
          </a>
        </div>
      </div>
    </section>
  );
}
