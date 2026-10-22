import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

/**
 * The one loading state every route shows. The static build prerenders a single shell page (at `/`)
 * that every path is served, and React hydrates it on whatever route the browser opened, so the
 * loading markup must be identical on every route or hydration fails (React error #418).
 */
export function PagePending() {
  return <p className="p-10 text-center font-display text-moss">Opening the garden gate…</p>;
}

export const getRouter = () => {
  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
    defaultPendingComponent: PagePending,
  });

  return router;
};
