import { type HTMLAttributes, type ElementType } from "react";
import { cn } from "@/lib/utils";

type RevealProps = HTMLAttributes<HTMLElement> & {
  as?: ElementType;
  delay?: number;
};

export function Reveal({
  as: Tag = "div",
  className,
  style,
  delay = 0,
  children,
  ...rest
}: RevealProps) {
  return (
    <Tag
      className={cn("reveal", className)}
      style={{ transitionDelay: `${delay}ms`, ...style }}
      {...rest}
    >
      {children}
    </Tag>
  );
}
