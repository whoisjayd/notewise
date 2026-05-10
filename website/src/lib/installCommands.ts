import { SITE_URL } from "./siteMeta";

export type InstallCommand = {
  label: string;
  command: string;
  recommended?: boolean;
};

export const packageCommands = [
  { label: "Recommended · uv tool", command: "uv tool install notewise", recommended: true },
  { label: "Try without installing · uvx", command: "uvx notewise --help" },
  { label: "Isolated CLI · pipx", command: "pipx install notewise" },
  { label: "Plain pip", command: "python -m pip install notewise" },
] as const satisfies readonly InstallCommand[];

export const binaryCommands = [
  { label: "macOS / Linux", command: `curl -fsSL ${SITE_URL}/install | sh` },
  { label: "Windows PowerShell", command: `irm ${SITE_URL}/install | iex` },
] as const satisfies readonly InstallCommand[];
