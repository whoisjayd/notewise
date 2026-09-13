import { Link } from "@tanstack/react-router";
import { FineIcon } from "@/ui/FineIcon";

export function NotFound() {
  return (
    <main
      id="main-content"
      className="flex min-h-screen items-center justify-center bg-background px-5"
    >
      <div className="max-w-md text-center">
        <span className="t-eyebrow">Error · 404</span>
        <h1 className="mt-4 t-h1 text-[clamp(48px,9vw,88px)]">
          Wrong <em className="text-stamp">page</em>.
        </h1>
        <p className="mt-5 t-body">
          That link is stale or was never real. The rest of the site still is.
        </p>
        <div className="mt-8 flex justify-center">
          <Link
            to="/"
            className="hover-feedback inline-flex items-center gap-2 rounded-full border border-transparent bg-foreground px-5 py-3 t-btn text-background sm:py-2.5"
          >
            Back to NoteWise
            <FineIcon name="arrow" size={14} />
          </Link>
        </div>
      </div>
    </main>
  );
}
