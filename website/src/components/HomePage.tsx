import { getRouteApi } from "@tanstack/react-router";

import { Cookbook } from "@/components/Cookbook";
import { FAQ } from "@/components/FAQ";
import { Footer } from "@/components/Footer";
import { Format } from "@/components/Format";
import { Hero } from "@/components/Hero";
import { Install } from "@/components/Install";
import { Nav } from "@/components/Nav";
import { Pipeline } from "@/components/Pipeline";
import { Providers } from "@/components/Providers";

const indexRoute = getRouteApi("/");

export function HomePage() {
  const stats = indexRoute.useLoaderData();

  return (
    <main
      id="main-content"
      className="relative min-h-screen overflow-x-hidden bg-background text-foreground"
    >
      <Nav version={stats.version} />
      <Hero stats={stats} />
      <Format />
      <Pipeline />
      <Providers />
      <Cookbook />
      <FAQ />
      <Install />
      <Footer stats={stats} />
    </main>
  );
}
