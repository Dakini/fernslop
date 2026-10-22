# [api] Follow-up: real email sender for the digest
**What:** An `EmailSender` implementation that delivers through a real SMTP server or email provider, chosen by configuration.
**Why:** [#013](013-api-weekly-digest.md) only ships a console/in-memory fake, so no digest reaches a real inbox yet.
**Edge cases:** Needs an account and credentials from the owner (ask before adding any dependency). Credentials come from env vars, never the repo or logs. Set up SPF/DKIM/DMARC for the sending domain (moved here from `audit.md` 3 via #200), and do not ship before #200 (double opt-in, safe digest) is done.
