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
