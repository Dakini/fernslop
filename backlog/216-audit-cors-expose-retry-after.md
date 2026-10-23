# [audit] Expose `Retry-After` to cross-origin callers

## Goal

When the frontend calls the backend cross-origin (`VITE_API_BASE_URL` set to an absolute URL), the browser can read `Retry-After` on a 429, so the toast says "Try again in N ..." instead of "Try again in a moment".

## Acceptance criteria

- [ ] A cross-origin request from an allowed origin (`FERNSLOP_CORS_ORIGINS` or the defaults) gets `Access-Control-Expose-Headers` that includes `Retry-After`, on 429s and other responses alike.
- [ ] A request from an origin that is not allowed still gets no CORS headers, as today.
- [ ] With Vite on another port and `VITE_API_BASE_URL` pointing straight at the backend, a used-up bucket toasts "Try again in N ..." with the real wait.

## Out of scope

- Nothing moved out. Same-origin setups (Vite proxy, Caddy in prod) already work.

## Constraints

- `backend/app/main.py` (`expose_headers=["Retry-After"]` on `CORSMiddleware`) and `backend/app/test_main.py`. Size: small. At most 1 test.
