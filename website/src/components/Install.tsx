import { Reveal } from "@/ui/Reveal";
import { Terminal } from "@/ui/Terminal";
import { FineIcon } from "@/ui/FineIcon";

export function Install() {
  return (
    <section id="install" className="relative paper-texture">
      <div className="relative mx-auto max-w-[920px] px-5 sm:px-6 py-20 sm:py-28 md:py-36 text-center">
        <Reveal>
          <span className="t-eyebrow">Coda · Install</span>
        </Reveal>
        <Reveal delay={60}>
          <h2 className="mt-3 t-h2">
            Pick a video. <em className="text-stamp">Keep</em> what you learn.
          </h2>
        </Reveal>
        <Reveal delay={120}>
          <p className="mx-auto mt-5 max-w-xl t-body">
            Four ways to install. Pick the one that matches the rest of your toolbox — they all land
            the same binary.
          </p>
        </Reveal>

        <Reveal delay={180}>
          <div className="mx-auto mt-9 sm:mt-10 max-w-2xl text-left">
            <Terminal
              title="install"
              lines={[
                { kind: "muted", text: "# uvx — try without installing" },
                {
                  kind: "prompt",
                  text: <span className="text-foreground">uvx notewise --help</span>,
                },
                { kind: "muted", text: "" },
                { kind: "muted", text: "# uv (recommended)" },
                {
                  kind: "prompt",
                  text: <span className="text-foreground">uv tool install notewise</span>,
                },
                { kind: "muted", text: "" },
                { kind: "muted", text: "# pipx" },
                {
                  kind: "prompt",
                  text: <span className="text-foreground">pipx install notewise</span>,
                },
                { kind: "muted", text: "" },
                { kind: "muted", text: "# docker" },
                {
                  kind: "prompt",
                  text: (
                    <>
                      <span className="text-foreground">
                        docker run --rm -v $(pwd)/output:/output
                      </span>{" "}
                      <span className="text-azure">ghcr.io/whoisjayd/notewise:latest</span>{" "}
                      <span className="text-thread">--help</span>
                    </>
                  ),
                },
              ]}
              caption="then: notewise setup → drop your API key → notewise process …"
            />
          </div>
        </Reveal>

        <Reveal delay={240}>
          <div className="mt-9 sm:mt-10 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center justify-center gap-3">
            <a
              href="https://github.com/whoisjayd/notewise"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-foreground px-5 py-3 sm:py-2.5 t-btn text-background hover:opacity-90 transition-opacity"
            >
              <FineIcon name="github" size={14} /> Read on GitHub
              <FineIcon name="external" size={12} className="opacity-70" />
            </a>
            <a
              href="https://docs.notewise.click"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-[var(--rule)] px-5 py-3 sm:py-2.5 t-btn hover:bg-accent transition-colors"
            >
              Full docs
              <FineIcon name="external" size={12} className="opacity-70" />
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
