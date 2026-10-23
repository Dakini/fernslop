# [env] Create prod, move the data and switch the domain
**What:** A runbook in `infra/README.md` that the user runs: create prod on `fernslop.example.com`, freeze dev, dump, restore into prod, verify, switch DNS, then move dev to `dev-fernslop.example.com`.
**Why:** Prod takes over the live domain and its real user data (photos are inside the Postgres dump).
**Edge cases:** Dev is single-level because of Cloudflare's certificate limits; prod's Caddy only gets a certificate after the DNS switch; dev keeps real PII and must never email followers ([#241](parked/241-env-dev-data-scrub.md)).
