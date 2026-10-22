# [api] Follow-up: try the Pl@ntNet provider with a real key
**What:** Run one real photo through `PlantNetIdentifyProvider` from [#012](012-api-identify-provider.md) using an account key, and confirm the request and response shapes match what the mocked tests assume.
**Why:** #012 is done without external accounts, so only mocked HTTP was tested.
**Edge cases:** Check what Pl@ntNet returns for a non-plant photo and for a quota error (its docs list no status codes); both must end as a 502, and the key must stay out of logs.
