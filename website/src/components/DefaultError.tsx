import { Link, useRouter } from "@tanstack/react-router";
import { FineIcon } from "@/ui/FineIcon";

export function DefaultError({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();

  return (
    <main
      id="main-content"
      className="flex min-h-screen items-center justify-center bg-background px-5"
    >
      <div className="max-w-md text-center">
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-[var(--rule)] bg-muted text-thread">
          <FineIcon name="stop" size={20} />
        </span>
        <h1 className="mt-6 t-h2 text-[clamp(30px,4vw,40px)]">Something broke.</h1>
        <p className="mt-3 t-body">Not you, us. Reloading usually fixes it.</p>
        {import.meta.env.DEV && error.message && (
          <pre className="mt-4 max-h-40 overflow-auto rounded-md border border-[var(--rule)] bg-muted p-3 text-left font-mono text-xs text-thread">
            {error.message}
          </pre>
        )}
        <div className="mt-7 flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="hover-feedback inline-flex items-center gap-2 rounded-full border border-transparent bg-foreground px-5 py-3 t-btn text-background sm:py-2.5"
          >
            Try again
          </button>
          <Link
            to="/"
            className="hover-feedback inline-flex items-center gap-2 rounded-full border border-[var(--rule)] px-5 py-3 t-btn sm:py-2.5"
          >
            Go home
          </Link>
        </div>
      </div>
    </main>
  );
}
