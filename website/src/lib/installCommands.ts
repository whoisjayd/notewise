import { SITE_URL } from "./siteMeta";

export type InstallCommand = {
  id: InstallCommandId;
  label: string;
  command: string;
  recommended?: boolean;
};

export type InstallCommandId =
  | "uv-tool"
  | "uvx"
  | "pipx"
  | "pip"
  | "posix-binary"
  | "powershell-binary";

export const packageCommands = [
  {
    id: "uv-tool",
    label: "Recommended · uv tool",
    command: "uv tool install notewise",
    recommended: true,
  },
  { id: "uvx", label: "Try without installing · uvx", command: "uvx notewise --help" },
  { id: "pipx", label: "Isolated CLI · pipx", command: "pipx install notewise" },
  { id: "pip", label: "Plain pip", command: "python -m pip install notewise" },
] as const satisfies readonly InstallCommand[];

export const binaryCommands = [
  { id: "posix-binary", label: "macOS / Linux", command: `curl -fsSL ${SITE_URL}/install | sh` },
  {
    id: "powershell-binary",
    label: "Windows PowerShell",
    command: `irm ${SITE_URL}/install | iex`,
  },
] as const satisfies readonly InstallCommand[];
