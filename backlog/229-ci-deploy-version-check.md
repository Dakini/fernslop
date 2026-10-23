# [ci] Health check proves the newly deployed image is running
**What:** Bake the image tag into the image, return it from `/api/health`, and make the dev check (#238) and prod promotion (#239) require it to match the deployed tag.
**Why:** A 200 from `/api/health` can't tell the new container from an old one, so promotion could ship a tag dev never ran.
**Edge cases:** Return only the tag (it contains a short SHA) because `/api/health` is public; local and e2e builds have no tag, so the field is optional.
