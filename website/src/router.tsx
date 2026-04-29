import { createRouter } from "@tanstack/react-router";
import { DefaultError } from "@/components/DefaultError";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  const router = createRouter({
    routeTree,
    context: {},
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
    defaultErrorComponent: DefaultError,
  });

  return router;
};
