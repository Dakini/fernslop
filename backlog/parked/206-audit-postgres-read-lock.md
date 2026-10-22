# [audit] Follow-up: do not take the advisory lock on every read in Postgres
**What:** Review whether `sql_store.py` needs the process-wide `RLock` and the Postgres advisory lock for read-only transactions, and drop it for reads if consistency allows.
**Why:** Moved out of #192 (`audit.md` 5, last sentence): every request, reads included, is serialised through one lock, so one slow write stalls the whole site. Not needed for the immediate fix, which moved store calls off the event loop.
**Edge cases:** Reads that must see a consistent snapshot across tables (room state, digest); the SQLite store; the multi-worker plan in parked #090.
