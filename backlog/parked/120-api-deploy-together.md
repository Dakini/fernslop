# [api] Follow-up: serve frontend and API together
**What:** Decide and set up how the built frontend and the API are served in production (same origin under `/api`, or separate origins), including `FERNSLOP_CORS_ORIGINS` and the frontend's production `VITE_API_BASE_URL`.
**Why:** Moved out of [#014](014-api-frontend-wiring.md), which only makes the HTTP service selectable and works in dev (proxy or the CORS defaults in `backend/app/main.py`).
**Edge cases:** Photo URLs and the SSE stream must keep working behind the chosen proxy (no response buffering); the Cloudflare/nitro build target of the frontend may not suit a Python backend.
