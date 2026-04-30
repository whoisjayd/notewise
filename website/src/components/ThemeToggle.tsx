import { useEffect, useState } from "react";

function getSystemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getPreferredTheme() {
  const stored = localStorage.getItem("nw-theme");
  return stored === "light" || stored === "dark" ? stored : getSystemTheme();
}

function applyTheme(next: "light" | "dark") {
  document.documentElement.classList.toggle("dark", next === "dark");
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const syncTheme = () => {
      const next = getPreferredTheme();
      setTheme(next);
      applyTheme(next);
    };

    syncTheme();
    query.addEventListener("change", syncTheme);
    window.addEventListener("storage", syncTheme);

    return () => {
      query.removeEventListener("change", syncTheme);
      window.removeEventListener("storage", syncTheme);
    };
  }, []);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    try {
      localStorage.setItem("nw-theme", next);
    } catch {
      // Theme still applies for this page when storage is unavailable.
    }
  };

  const nextThemeLabel = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={nextThemeLabel}
      className="hover-feedback relative inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--rule)] text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stamp/45 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="absolute dark:hidden"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="absolute hidden dark:block"
      >
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    </button>
  );
}
