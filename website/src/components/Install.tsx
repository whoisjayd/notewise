import { Terminal } from "@/ui/Terminal";
import { FineIcon } from "@/ui/FineIcon";

export function Install() {
  return (
    <section id="install" className="relative border-t border-[var(--rule)] bg-background">
      <div className="relative mx-auto max-w-[920px] px-5 sm:px-6 py-20 sm:py-28 md:py-36 text-center">
        <>
          <span className="t-eyebrow">Coda · Install</span>
        </>
        <>
          <h2 className="mt-3 t-h2">
            Pick a video. <em className="text-stamp">Keep</em> what you learn.
          </h2>
        </>
        <>
          <p className="mx-auto mt-5 max-w-xl t-body">
            Use Python tooling when you want the PyPI package. Prefer the short installer when you
            want the standalone binary from GitHub releases.
          </p>
        </>

        <>
          <div className="mx-auto mt-9 sm:mt-10 max-w-2xl text-left">
            <Terminal
              title="notewise.click/install"
              lines={[
                { kind: "muted", text: "# recommended Python tool install" },
                {
                  kind: "prompt",
                  text: <span className="text-foreground">uv tool install notewise</span>,
                },
                { kind: "muted", text: "" },
                { kind: "muted", text: "# try without installing" },
                {
                  kind: "prompt",
                  text: <span className="text-foreground">uvx notewise --help</span>,
                },
                { kind: "muted", text: "" },
                { kind: "muted", text: "# pipx / pip" },
                {
                  kind: "prompt",
                  text: <span className="text-foreground">pipx install notewise</span>,
                },
                {
                  kind: "prompt",
                  text: <span className="text-foreground">python -m pip install notewise</span>,
                },
                { kind: "muted", text: "" },
                { kind: "muted", text: "# prefer standalone binary?" },
                {
                  kind: "prompt",
                  text: (
                    <>
                      <span className="text-foreground">curl -fsSL</span>{" "}
                      <span className="text-azure">https://notewise.click/install</span>{" "}
                      <span className="text-thread">| sh</span>
                    </>
                  ),
                },
                { kind: "muted", text: "" },
                { kind: "muted", text: "# Windows binary installer" },
                {
                  kind: "prompt",
                  text: (
                    <>
                      <span className="text-foreground">irm</span>{" "}
                      <span className="text-azure">https://notewise.click/install</span>{" "}
                      <span className="text-thread">| iex</span>
                    </>
                  ),
                },
              ]}
              caption="the endpoint returns the right installer for curl, wget, PowerShell, or a browser"
            />
          </div>
        </>

        <>
          <div className="mt-9 sm:mt-10 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center justify-center gap-3">
            <a
              href="/install"
              className="hover-feedback inline-flex items-center justify-center gap-2 rounded-full border border-transparent bg-foreground px-5 py-3 t-btn text-background sm:py-2.5"
            >
              Open short installer
              <FineIcon name="arrow" size={14} />
            </a>
            <a
              href="https://docs.notewise.click"
              target="_blank"
              rel="noreferrer"
              className="hover-feedback inline-flex items-center justify-center gap-2 rounded-full border border-[var(--rule)] px-5 py-3 t-btn sm:py-2.5"
            >
              Full docs
              <FineIcon name="external" size={12} className="opacity-70" />
            </a>
          </div>
        </>
      </div>
    </section>
  );
}
