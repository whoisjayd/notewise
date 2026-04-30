import { HeadContent, Outlet, Scripts } from "@tanstack/react-router";
import type { ReactNode } from "react";

export function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

export function RootComponent() {
  return <Outlet />;
}
