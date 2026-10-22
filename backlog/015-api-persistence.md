# [api] Follow-up: persistent storage and photo cleanup
**What:** Replace the in-memory store with a real database and file/object storage, and clean up photos that were never posted.
**Why:** This was moved out of 002 and 009. The request asked for in-memory storage, so all data is lost on restart.
**Edge cases:** The undo and limit checks must stay atomic under concurrent requests.
