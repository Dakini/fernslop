# [api] Live updates across several workers
**What:** Make `live.notify` reach streams held by other server processes, for example through a shared broker or the database from [#015](015-api-persistence.md).
**Why:** [#011](011-api-live-sse.md) keeps subscribers in one process's memory, so with `uvicorn --workers 2` a mutation on one worker is not seen by browsers connected to another.
**Edge cases:** Keep the message format and ping behaviour of 011; a lost broker must not break mutations; do this only once the app runs with more than one worker.
