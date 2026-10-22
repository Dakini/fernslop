# [audit] A 429 shows its toast twice on some screens
**What:** #195 makes `httpService.ts` show one `toast.error` (id `rate-limit`) on 429 and then reject with the same message; the room page's `run()`, the post photo upload and the delete-garden dialog also toast `e.message`, so the message appears twice there.
**Why:** Flagged by the #195 engineer; noisy UI exactly when a user is already being slowed down.
**Edge cases:** Other errors must still toast once; the identify dialog shows errors inline, not as a toast (#211).
