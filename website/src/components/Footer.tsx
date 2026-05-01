import { FineIcon } from "@/ui/FineIcon";
import type { RepoStats } from "@/server/repo.functions";

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function Footer({ stats }: { stats: RepoStats }) {
  return (
    <footer className="border-t border-[var(--rule)] bg-background">
      <div className="mx-auto max-w-[1200px] px-5 sm:px-6 py-12">
        <div className="grid gap-10 grid-cols-1 sm:grid-cols-2 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="sm:col-span-2 md:col-span-1">
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] border border-[var(--rule)] bg-card">
                <span className="font-display text-[18px] leading-none italic text-stamp">N</span>
              </span>
              <span className="font-display text-[18px]">NoteWise</span>
            </div>
            <p className="mt-4 max-w-sm text-[13px] leading-[1.7] text-muted-foreground">
              An open-source CLI by{" "}
              <a
                className="hover-underline underline-ink"
                href="https://github.com/whoisjayd"
                target="_blank"
                rel="noopener noreferrer"
              >
                whoisjayd
              </a>
              . MIT License.
            </p>
          </div>

          <FooterCol title="Project">
            <FooterLink href="https://github.com/whoisjayd/notewise" label="GitHub" external />
            <FooterLink href="https://pypi.org/project/notewise/" label="PyPI" external />
            <FooterLink href="https://ghcr.io/whoisjayd/notewise" label="Docker image" external />
          </FooterCol>

          <FooterCol title="Read">
            <FooterLink href="https://notewise.click/docs" label="Docs" external />
            <FooterLink
              href="https://github.com/whoisjayd/notewise#-quick-start"
              label="Quick start"
              external
            />
            <FooterLink
              href="https://github.com/whoisjayd/notewise/blob/main/CONTRIBUTING.md"
              label="Contributing"
              external
            />
          </FooterCol>

          <FooterCol title="Stats">
            <li className="flex items-center gap-2 font-mono text-[12px] text-muted-foreground">
              <FineIcon name="star" size={12} className="text-stamp" /> {stats.stars} stars
            </li>
            <li className="flex items-center gap-2 font-mono text-[12px] text-muted-foreground">
              <FineIcon name="leaf" size={12} className="text-leaf" /> v{stats.version}
            </li>
            <li className="flex items-center gap-2 font-mono text-[12px] text-muted-foreground">
              <FineIcon name="quill" size={12} /> {fmtDate(stats.pushedAt)}
            </li>
          </FooterCol>
        </div>

        <div className="thread my-10" />

        <div className="flex flex-col items-start justify-between gap-3 md:flex-row md:items-center">
          <p className="font-mono text-[11px] text-muted-foreground">
            © {new Date().getFullYear()} NoteWise · {stats.license}
          </p>
          <p className="font-mono text-[11px] text-muted-foreground">
            Made with care ·{" "}
            <a
              className="underline-ink"
              href="https://github.com/whoisjayd/notewise"
              target="_blank"
              rel="noopener noreferrer"
            >
              contribute on GitHub
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="eyebrow">{title}</p>
      <ul className="mt-4 space-y-2.5">{children}</ul>
    </div>
  );
}

function FooterLink({
  href,
  label,
  external,
}: {
  href: string;
  label: string;
  external?: boolean;
}) {
  return (
    <li>
      <a
        href={href}
        target={external ? "_blank" : undefined}
        rel={external ? "noopener noreferrer" : undefined}
        className="hover-underline inline-flex items-center gap-1.5 text-[13px] text-muted-foreground"
      >
        {label}
        {external && <FineIcon name="external" size={11} className="opacity-50" />}
      </a>
    </li>
  );
}
