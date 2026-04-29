import { createFileRoute } from "@tanstack/react-router";
import { Nav } from "@/components/Nav";
import { Hero } from "@/components/Hero";
import { Format } from "@/components/Format";
import { Pipeline } from "@/components/Pipeline";
import { Providers } from "@/components/Providers";
import { Cookbook } from "@/components/Cookbook";
import { FAQ } from "@/components/FAQ";
import { Install } from "@/components/Install";
import { Footer } from "@/components/Footer";
import { getRepoStats } from "@/server/repo.functions";

export const Route = createFileRoute("/")({
  component: Index,
  loader: () => getRepoStats(),
  staleTime: 1000 * 60 * 30,
});

function Index() {
  const stats = Route.useLoaderData();
  return (
    <main
      id="main-content"
      className="paper-texture relative min-h-screen overflow-x-hidden bg-background text-foreground"
    >
      <Nav version={stats.version} />
      <Hero stats={stats} />
      <Format />
      <Pipeline />
      <span aria-hidden className="deckle" />
      <Providers />
      <Cookbook />
      <FAQ />
      <span aria-hidden className="deckle" />
      <Install />
      <Footer stats={stats} />
    </main>
  );
}
