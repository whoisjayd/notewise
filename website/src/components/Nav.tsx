import { Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "./ThemeToggle";
import { FineIcon } from "@/ui/FineIcon";

const items = [
  { href: "#format", label: "Format" },
  { href: "#pipeline", label: "Pipeline" },
  { href: "#providers", label: "Providers" },
  { href: "#cookbook", label: "Cookbook" },
  { href: "#faq", label: "FAQ" },
];

export function Nav({ version }: { version: string }) {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!panelRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 bg-background",
        scrolled && "border-b border-[var(--rule)]",
      )}
    >
      <div className="mx-auto flex max-w-[1200px] items-center justify-between px-4 sm:px-6 py-3 sm:py-3.5">
        <Link to="/" aria-label="NoteWise home" className="group flex items-center gap-2.5">
          <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-[6px] border border-[var(--rule)] bg-card">
            <span className="font-display text-[18px] leading-none italic text-stamp">N</span>
          </span>
          <span className="font-display text-[18px] tracking-tight">NoteWise</span>
          <span className="hidden sm:inline ml-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            v{version}
          </span>
        </Link>

        <nav aria-label="Primary" className="hidden md:flex items-center gap-7">
          {items.map((it) => (
            <a
              key={it.href}
              href={it.href}
              className="hover-underline text-[13px] text-muted-foreground"
            >
              {it.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-1.5 sm:gap-2">
          <a
            href="https://github.com/whoisjayd/notewise"
            target="_blank"
            rel="noreferrer"
            aria-label="Open the NoteWise GitHub repository"
            className="hover-feedback hidden h-9 items-center gap-2 rounded-full border border-[var(--rule)] px-3 text-[12.5px] text-foreground/80 sm:inline-flex"
          >
            <FineIcon name="github" size={14} /> GitHub
          </a>
          <ThemeToggle />
          <a
            href="#install"
            className="hover-feedback inline-flex items-center gap-1.5 rounded-full border border-transparent bg-foreground px-3.5 py-2 text-[12.5px] font-medium text-background sm:px-4"
          >
            Install
            <FineIcon name="arrow" size={13} />
          </a>

          <button
            type="button"
            aria-label={open ? "Close sections" : "Open sections"}
            aria-expanded={open}
            aria-controls="mobile-sections"
            onClick={() => setOpen((v) => !v)}
            className="hover-feedback inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--rule)] text-foreground/80 md:hidden"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            >
              {open ? <path d="M5 5l14 14M19 5L5 19" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </div>

      {open && (
        <div
          id="mobile-sections"
          ref={panelRef}
          className="md:hidden mx-3 mt-1 rounded-lg border border-[var(--rule)] bg-background shadow-lg overflow-hidden"
        >
          <ul className="divide-y divide-[var(--rule)]">
            {items.map((it) => (
              <li key={it.href}>
                <a
                  href={it.href}
                  onClick={() => setOpen(false)}
                  className="hover-underline flex items-center justify-between px-5 py-3.5 text-[14px]"
                >
                  <span>{it.label}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    {it.href.replace("#", "")}
                  </span>
                </a>
              </li>
            ))}
            <li>
              <a
                href="https://github.com/whoisjayd/notewise"
                target="_blank"
                rel="noreferrer"
                onClick={() => setOpen(false)}
                className="hover-underline flex items-center gap-2 px-5 py-3.5 text-[14px]"
              >
                <FineIcon name="github" size={14} /> GitHub
                <FineIcon name="external" size={11} className="ml-auto opacity-60" />
              </a>
            </li>
          </ul>
        </div>
      )}
    </header>
  );
}
