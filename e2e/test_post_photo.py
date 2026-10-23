import re
import uuid

from playwright.sync_api import Page, expect

# --- Helpers -----------------------------------------------------------------


def create_garden(page: Page, name: str) -> None:
    page.goto("/")
    page.get_by_role("button", name="Create a room").click()
    page.get_by_label("Garden name").fill(name)
    page.get_by_role("button", name="Create garden").click()
    expect(page).to_have_url(re.compile(r"/r/[^/]+$"))
    expect(page.get_by_role("heading", level=1, name=name)).to_be_visible()


def image_has_loaded(page: Page, img) -> None:
    img.scroll_into_view_if_needed()
    page.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=img.element_handle())


# --- Post photo --------------------------------------------------------------


def test_photo_posted_by_one_gardener_appears_live_in_another_gardeners_feed(new_gardener):
    garden_name = f"E2E photo garden {uuid.uuid4().hex[:8]}"
    post_text = f"First tomatoes {uuid.uuid4().hex[:8]}"
    poster = new_gardener().new_page()
    create_garden(poster, garden_name)
    # A real JPEG without a fixture file: a small screenshot of the page itself.
    jpeg = poster.screenshot(type="jpeg", clip={"x": 0, "y": 0, "width": 64, "height": 64})
    viewer = new_gardener().new_page()
    viewer.goto(poster.url)
    expect(viewer.get_by_role("heading", level=1, name=garden_name)).to_be_visible()
    viewer.get_by_role("tab", name="Feed").click()

    poster.get_by_role("tab", name="Feed").click()
    poster.get_by_label("Post an update").fill(post_text)
    poster.locator("#post-photo").set_input_files({"name": "tomatoes.jpg", "mimeType": "image/jpeg", "buffer": jpeg})
    expect(poster.get_by_alt_text("Photo to post")).to_be_visible()
    poster.get_by_role("button", name="Post", exact=True).click()

    posted = poster.get_by_role("listitem").filter(has_text=post_text).get_by_role("img")
    expect(posted).to_have_attribute("src", re.compile(r"/api/photos/[^/]+$"))
    image_has_loaded(poster, posted)
    # The viewer is not reloaded: the post arrives over the live feed.
    seen = viewer.get_by_role("listitem").filter(has_text=post_text).get_by_role("img")
    expect(seen).to_have_attribute("src", re.compile(r"/api/photos/[^/]+$"))
    image_has_loaded(viewer, seen)


# A 12 MP JPEG of about 6-7 MB, drawn in the page (a gradient with noise, so it compresses like a photo).
LARGE_JPEG_JS = """async () => {
  const w = 4000, h = 3000, c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d"), img = ctx.createImageData(w, h), d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const g = (((i / 4) % w) / w) * 166;
    d[i] = g + Math.random() * 89; d[i + 1] = g + Math.random() * 89; d[i + 2] = g + Math.random() * 89; d[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.92));
  return Array.from(new Uint8Array(await blob.arrayBuffer()));
}"""


def test_large_phone_photo_is_shrunk_in_the_browser_and_posts(new_gardener):
    post_text = f"Whole bed {uuid.uuid4().hex[:8]}"
    page = new_gardener().new_page()
    create_garden(page, f"E2E big photo garden {uuid.uuid4().hex[:8]}")
    jpeg = bytes(page.evaluate(LARGE_JPEG_JS))
    assert len(jpeg) > 5 * 1024 * 1024  # over the server's limit as it is

    page.get_by_role("tab", name="Feed").click()
    page.get_by_label("Post an update").fill(post_text)
    page.locator("#post-photo").set_input_files({"name": "bed.jpg", "mimeType": "image/jpeg", "buffer": jpeg})
    expect(page.get_by_alt_text("Photo to post")).to_be_visible()
    page.get_by_role("button", name="Post", exact=True).click()

    posted = page.get_by_role("listitem").filter(has_text=post_text).get_by_role("img")
    expect(posted).to_have_attribute("src", re.compile(r"/api/photos/[^/]+$"))
    image_has_loaded(page, posted)
    assert posted.evaluate("(el) => [el.naturalWidth, el.naturalHeight]") == [2048, 1536]


# The start of an iPhone HEIC: an ISO-BMFF "ftyp" box naming the heic brand.
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + bytes(64)


def test_heic_renamed_jpg_is_refused_in_the_browser_without_a_request(new_gardener):
    page = new_gardener().new_page()
    create_garden(page, f"E2E heic garden {uuid.uuid4().hex[:8]}")
    uploads, errors = [], []
    page.on("request", lambda r: r.method == "POST" and "/api/photos" in r.url and uploads.append(r.url))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))

    page.get_by_role("tab", name="Feed").click()
    page.locator("#post-photo").set_input_files({"name": "leaf.jpg", "mimeType": "image/jpeg", "buffer": HEIC})

    expect(page.get_by_text("Please use a JPG, PNG or WebP image")).to_be_visible()
    expect(page.get_by_alt_text("Photo to post")).to_have_count(0)
    assert uploads == []
    assert errors == []
