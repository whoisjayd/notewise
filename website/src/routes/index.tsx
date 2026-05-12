import { createFileRoute } from "@tanstack/react-router";

import { HomePage } from "@/components/HomePage";
import { getRepoStats } from "@/server/repo.functions";

export const Route = createFileRoute("/")({
  component: HomePage,
  loader: () => getRepoStats(),
  staleTime: 1000 * 60 * 5,
});
