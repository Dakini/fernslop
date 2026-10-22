# [db] Follow-up: schema migrations (Alembic)
**What:** Replace `create_all` at startup with versioned migrations so schema changes can be applied to an existing database.
**Why:** Moved out of #016; the MVP creates missing tables only and cannot alter existing ones.
**Edge cases:** Existing SQLite files created by #016 must be adoptable as the baseline revision.
