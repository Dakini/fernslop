// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// FERNSLOP_STATIC=1 builds a client-only SPA (dist/client, with a shell page) for the backend to
// serve; without it the build keeps the default SSR/Nitro target.
const staticBuild = process.env.FERNSLOP_STATIC === "1";

export default defineConfig({
  ...(staticBuild && { nitro: false as const }),
  tanstackStart: {
    ...(staticBuild && { spa: { enabled: true } }),
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  // Dev: forward /api (the default VITE_API_BASE_URL) to the backend started with `make backend` (port 8091).
  vite: { server: { proxy: { "/api": "http://localhost:8091" } } },
});
