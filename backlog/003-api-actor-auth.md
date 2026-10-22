# [api] Actor headers dependency (`auth.py`)
**What:** A FastAPI dependency that reads `X-Device-Id` and `X-Actor-Name` on actor endpoints and gives routers the decoded actor. It attributes edits only and does not authorise anything (see the "Authentication" section of `openapi.yaml`).
**Why:** Every room mutation records the actor on its feed event, and `addPlant` also stores it as `added_by_name`.
**Edge cases:** The name arrives percent-encoded UTF-8 and must be decoded. It is at most 40 characters after decoding; the 120-character schema limit applies to the encoded form. The spec doesn't define the response for a missing, blank or oversized header, so the PM should pick one (400 is suggested). Room creation and following a room do not need an actor.
