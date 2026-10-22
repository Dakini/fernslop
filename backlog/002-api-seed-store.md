# [api] In-memory store with seed data
**What:** `store.py` keeps rooms, plants, room plants, areas, feed events, photos and follows in memory. It is seeded with the plant reference table from `frontend/src/services/mock/plants-seed.ts` and 2–3 demo rooms that have plants, areas and feed events.
**Why:** The request asks for an in-memory store with enough seed data for the frontend to show something.
**Edge cases:** Plant ids must stay stable (e.g. `plant-tomato`), because the frontend caches `GET /plants` forever. Room ids are UUIDs. Seed rooms must stay under the limits (50 plants, 10 areas). Include at least one soft-deleted plant and one undone event so the filtering paths have data. Tests need a way to reset the store to a fresh seed between runs.
