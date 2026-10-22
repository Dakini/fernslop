# [api] Follow-up: weekly digest email job
**What:** A scheduled job that emails each follower a summary of rooms that had activity that week, including the unsubscribe token link.
**Why:** This was moved out of 010. The spec says it is a scheduled job, not an endpoint, and it needs an email provider.
**Edge cases:** Rooms with no activity that week get no email. The digest must not include undone events.
