import { type ReactNode, Children, isValidElement } from "react";
import { useCopyFeedback } from "@/lib/useCopyFeedback";
import { cn } from "@/lib/utils";
import { FineIcon } from "./FineIcon";

type Line = { kind?: "prompt" | "out" | "ok" | "warn" | "muted"; text: ReactNode };

function nodeToText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeToText).join("");
  if (isValidElement(node)) {
    const props = node.props as { children?: ReactNode };
    return Children.toArray(props.children).map(nodeToText).join("");
  }
  return "";
}

export function Terminal({
  title = "~/notewise",
  lines,
  className,
  caption,
  copyable = true,
}: {
  title?: string;
  lines: Line[];
  className?: string;
  caption?: ReactNode;
  copyable?: boolean;
}) {
  const { copy, copyState } = useCopyFeedback();
  const copied = copyState === "copied";
  const copyFailed = copyState === "failed";

  const handleCopy = async () => {
    const text = lines
      .filter((l) => l.kind === "prompt" || l.kind === undefined)
      .map((l) => nodeToText(l.text))
      .join("\n");
    await copy(text);
  };

  return (
    <figure className={cn("leaf-card overflow-hidden bg-card", className)}>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-[var(--rule)] bg-card px-3 py-2.5 sm:px-4">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border border-[var(--rule)] bg-[oklch(0.78_0.13_28)]" />
          <span className="h-2.5 w-2.5 rounded-full border border-[var(--rule)] bg-[oklch(0.85_0.13_85)]" />
          <span className="h-2.5 w-2.5 rounded-full border border-[var(--rule)] bg-[oklch(0.80_0.13_150)]" />
        </div>
        <span className="max-w-[42vw] truncate font-mono text-[10.5px] uppercase tracking-[0.2em] text-muted-foreground">
          {title}
        </span>
        {copyable ? (
          <button
            type="button"
            onClick={handleCopy}
            aria-label={copied ? "Command copied" : "Copy command"}
            aria-live="polite"
            aria-atomic="true"
            className="hover-feedback ml-auto inline-flex h-6 items-center gap-1 rounded-md border border-[var(--rule)] bg-background px-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stamp/45 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {copyFailed ? (
              <>
                <FineIcon name="stop" size={10} className="text-thread" /> failed
              </>
            ) : copied ? (
              <>
                <FineIcon name="check" size={10} className="text-leaf" /> copied
              </>
            ) : (
              <>
                <FineIcon name="copy" size={10} /> copy
              </>
            )}
          </button>
        ) : (
          <span className="ml-auto font-mono text-[10.5px] text-muted-foreground/60">zsh</span>
        )}
      </div>
      <pre className="m-0 overflow-hidden bg-card px-4 py-4 font-mono text-[11.5px] leading-[1.7] text-foreground sm:px-5 sm:text-[12.5px]">
        <code className="block">
          {lines.map((l, i) => (
            <span
              key={i}
              className={cn(
                "flex min-w-0 gap-3 whitespace-pre-wrap break-words",
                l.kind === "muted" && "text-muted-foreground/80",
                l.kind === "ok" && "text-leaf",
                l.kind === "warn" && "text-thread",
              )}
            >
              {l.kind === "prompt" ? (
                <span className="w-3 shrink-0 select-none text-stamp">›</span>
              ) : (
                <span className="w-3 shrink-0 select-none opacity-0">›</span>
              )}
              <span className="min-w-0 [overflow-wrap:anywhere]">{l.text}</span>
            </span>
          ))}
        </code>
      </pre>
      {caption && (
        <figcaption className="flex items-center gap-2 border-t border-[var(--rule)] bg-card px-4 py-2 font-mono text-[10.5px] text-muted-foreground sm:px-5 sm:text-[11px]">
          <span className="inline-block h-1 w-1 rounded-full bg-stamp/70" />
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
