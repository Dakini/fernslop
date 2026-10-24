# Frontend

The Fernslop web app: React 19, TanStack Router and Query, Tailwind 4, Vite. The first version was generated with [Lovable](https://lovable.dev) from [`_docs/lovable-spec.md`](../_docs/lovable-spec.md).

```sh
npm install
npm run dev          # prints its URL; /api is proxied to http://localhost:8091
npm test             # Vitest, once (npm run test:watch to keep it running)
npm run lint
npm run build
```

Start the backend first with `make backend-dev` from the repo root, or use the mock below.

## Layout

- `src/routes/`: one file per page
- `src/components/`: UI, with shared pieces in `components/ui/`
- `src/services/`: every backend call, with an HTTP version (`http/`) and an in-browser mock (`mock/`)
- `src/styles.css`: colours, fonts and other design tokens
- `src/test/`: test setup and helpers

## Backend selection

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_USE_MOCK` | unset | `true` uses the in-browser mock, so no backend is needed |
| `VITE_API_BASE_URL` | `/api` | API base URL |

Set them in `.env.local` or the environment.
