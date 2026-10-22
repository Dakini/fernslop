# [api] Follow-up: real third-party plant identification
**What:** Swap the identify stub from 005 for a real plant ID API that uses a server-side key, and map its results to reference-table rows.
**Why:** This was moved out of 005 because the request asked only for an in-memory, seeded backend with no external services.
**Edge cases:** A failing or timed-out upstream returns 502. Results that don't match any reference plant are dropped. The key must never reach the client.
