# [audit] Look up "photo already in a post" by URL instead of reading every feed
**What:** The #199 reuse check in `routers/posts.py` reads every room's feed on each photo post; add a store lookup by `photo_url` (the `feed_events.photo_url` column already exists) and use it.
**Why:** Cost grows with all feed events on every post; flagged by the #199 engineer.
**Edge cases:** soft-deleted rooms (#196) still count as "in a post" until purged; undone posts count too.
