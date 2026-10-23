# End-to-end tests

Browser tests (Playwright, Chromium) that run against the real stack in `docker-compose.yaml`: Postgres plus the app serving the built frontend.

```sh
cd e2e
uv sync
uv run pytest
```

The suite builds and starts its own copy of the stack under the compose project `fernslop-e2e` on a free port, then removes it and its database volume. A stack you run by hand is not touched.

If Chromium is missing, run `uv run playwright install chromium` once.

| Variable | Effect |
|---|---|
| `E2E_BASE_URL` | Test an already running stack instead of starting one |
| `E2E_KEEP_STACK=1` | Leave the compose stack running afterwards |
| `E2E_HEADED=1` | Show the browsers |

## Tests

- `test_shared_garden.py`: one gardener creates a garden, adds two plants and shares the link; a second gardener (separate browser context, so a separate identity) joins, moves a plant, and the first sees it move without reloading.
- `test_post_photo.py`: one gardener posts text with a JPEG; the preview shows, the post's image loads from `/api/photos/{id}`, and a second gardener sees the photo arrive in the feed without reloading. A 12 MP JPEG over 5 MB is shrunk in the browser to 2048 px and posts.
- `test_not_found.py`: loading `/nope` directly shows the "Page not found" page with no console error (no React #418 hydration mismatch), and its "Go home" link works.
