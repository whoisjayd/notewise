import { createFileRoute } from "@tanstack/react-router";

import { InstallPage } from "@/components/InstallPage";

const RAW_INSTALL_SH =
  "https://raw.githubusercontent.com/whoisjayd/notewise/main/scripts/install.sh";
const RAW_INSTALL_PS1 =
  "https://raw.githubusercontent.com/whoisjayd/notewise/main/scripts/install.ps1";

const POSIX_INSTALLER = `#!/usr/bin/env sh
set -eu

INSTALLER_URL="${RAW_INSTALL_SH}"

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$INSTALLER_URL" | sh
  exit $?
fi

if command -v wget >/dev/null 2>&1; then
  wget -qO- "$INSTALLER_URL" | sh
  exit $?
fi

echo "error: curl or wget is required to install NoteWise" >&2
exit 1
`;

const POWERSHELL_INSTALLER = `$ErrorActionPreference = "Stop"
$installerUrl = "${RAW_INSTALL_PS1}"
$script = Invoke-RestMethod -Uri $installerUrl
Invoke-Expression $script
`;

function wantsPowerShell(request?: Request) {
  const userAgent = request?.headers.get("user-agent")?.toLowerCase() ?? "";
  const url = request ? new URL(request.url) : undefined;

  return (
    url?.searchParams.get("shell") === "powershell" ||
    url?.searchParams.get("shell") === "pwsh" ||
    userAgent.includes("powershell") ||
    userAgent.includes("pwsh")
  );
}

function wantsHtml(request?: Request) {
  const accept = request?.headers.get("accept")?.toLowerCase() ?? "";
  const userAgent = request?.headers.get("user-agent")?.toLowerCase() ?? "";

  if (!accept.includes("text/html")) return false;
  return ![
    "curl",
    "wget",
    "powershell",
    "pwsh",
    "httpie",
    "python-requests",
    "go-http-client",
  ].some((agent) => userAgent.includes(agent));
}

function scriptResponse(body: string, shell: "sh" | "powershell") {
  return new Response(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      Pragma: "no-cache",
      Vary: "Accept, User-Agent",
      "X-Content-Type-Options": "nosniff",
      "Content-Disposition": `inline; filename="notewise-install.${shell === "sh" ? "sh" : "ps1"}"`,
    },
  });
}

export const Route = createFileRoute("/install")({
  head: () => ({
    meta: [
      { title: "Install NoteWise" },
      {
        name: "description",
        content: "Install NoteWise with uv, pipx, pip, or the short binary installer.",
      },
    ],
  }),
  server: {
    handlers: {
      GET: ({ request, next }) => {
        if (wantsPowerShell(request)) {
          return scriptResponse(POWERSHELL_INSTALLER, "powershell");
        }

        if (wantsHtml(request)) {
          return next();
        }

        return scriptResponse(POSIX_INSTALLER, "sh");
      },
    },
  },
  component: InstallPage,
});
