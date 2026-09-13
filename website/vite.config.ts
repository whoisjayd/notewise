import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import react from "@vitejs/plugin-react";
import { nitro } from "nitro/vite";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const loadedEnv = loadEnv(mode, process.cwd(), "VITE_");
  const envDefine = Object.fromEntries(
    Object.entries(loadedEnv).map(([key, value]) => [
      `import.meta.env.${key}`,
      JSON.stringify(value),
    ]),
  );

  return {
    define: envDefine,
    resolve: {
      tsconfigPaths: true,
      alias: {
        "@": `${process.cwd()}/src`,
      },
      dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime"],
    },
    server: {
      host: "::",
      port: 8080,
      // install.tsx pulls scripts/install.{sh,ps1} as ?raw from the repo
      // root, one level above this project's default (auto-detected) fs
      // boundary -- without this, the dev server 500s on every route.
      // Explicitly allow this project's own root too: setting `allow`
      // replaces Vite's auto-detected default rather than extending it, so
      // omitting it here would 403 every in-project request (node_modules
      // included) instead of just scoping the extra grant to scripts/.
      fs: {
        allow: [process.cwd(), path.resolve(process.cwd(), "../scripts")],
      },
    },
    plugins: [tailwindcss(), tanstackStart(), nitro(), react()],
  };
});
