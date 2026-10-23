# 232 ci: upload Playwright traces and screenshots when e2e fails

- What: record a Playwright trace and screenshot per failing e2e test (`e2e/conftest.py`) and upload them as an artifact from the CI `stack` job (#226)
- Why: today only `docker compose logs` are uploaded, so a failed browser step in CI cannot be replayed
- Edge cases: keep traces only on failure (size); artifact retention; tests that fail before a page is opened
