import re
import uuid

from playwright.sync_api import Locator, Page, expect

# --- Helpers -----------------------------------------------------------------


def plant_on_canvas(page: Page, name: str) -> Locator:
    return page.get_by_label("Garden canvas").get_by_role("button", name=re.compile(rf"^{name}\."))


def drag_plant(page: Page, name: str, x_pct: int, y_pct: int) -> None:
    """Drag a plant to a spot on the canvas, given as a percentage of its size."""
    canvas = page.get_by_label("Garden canvas").bounding_box()
    plant = plant_on_canvas(page, name).bounding_box()
    page.mouse.move(plant["x"] + plant["width"] / 2, plant["y"] + plant["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        canvas["x"] + canvas["width"] * x_pct / 100,
        canvas["y"] + canvas["height"] * y_pct / 100,
        steps=10,
    )
    page.mouse.up()


def create_garden(page: Page, name: str) -> None:
    page.goto("/")
    page.get_by_role("button", name="Create a room").click()
    page.get_by_label("Garden name").fill(name)
    page.get_by_role("button", name="Create garden").click()
    expect(page).to_have_url(re.compile(r"/r/[^/]+$"))
    expect(page.get_by_role("heading", level=1, name=name)).to_be_visible()


def add_plant(page: Page, name: str) -> None:
    page.get_by_role("button", name="Add plant").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Plant name").fill(name)
    dialog.get_by_role("button", name=re.compile(rf"^{name}")).click()
    expect(plant_on_canvas(page, name)).to_be_visible()


# --- Shared garden -----------------------------------------------------------


def test_change_made_by_a_joined_gardener_appears_live_for_the_creator(new_gardener):
    garden_name = f"E2E garden {uuid.uuid4().hex[:8]}"

    # Session 1 creates a garden with two plants, spread out because new plants all start at the centre.
    creator = new_gardener().new_page()
    create_garden(creator, garden_name)
    add_plant(creator, "Basil")
    drag_plant(creator, "Basil", 25, 35)
    add_plant(creator, "Mint")
    drag_plant(creator, "Mint", 70, 40)
    expect(plant_on_canvas(creator, "Basil")).to_have_attribute("style", re.compile(r"left: 25%; top: 35%"))
    expect(plant_on_canvas(creator, "Mint")).to_have_attribute("style", re.compile(r"left: 70%; top: 40%"))

    # Session 1 shares the garden: the Share button puts the join link on the clipboard.
    creator.get_by_role("button", name="Share").click()
    expect(creator.get_by_text("Link copied")).to_be_visible()
    join_link = creator.evaluate("navigator.clipboard.readText()")
    assert re.fullmatch(r".+/r/[^/]+", join_link)

    # Session 2 is a separate browser context (own identity) and opens the link.
    joiner = new_gardener().new_page()
    joiner.goto(join_link)
    expect(joiner.get_by_role("heading", level=1, name=garden_name)).to_be_visible()
    expect(plant_on_canvas(joiner, "Basil")).to_have_attribute("style", re.compile(r"left: 25%; top: 35%"))
    expect(plant_on_canvas(joiner, "Mint")).to_have_attribute("style", re.compile(r"left: 70%; top: 40%"))

    # Session 2 changes the canvas by moving Basil. Session 1 is not reloaded.
    drag_plant(joiner, "Basil", 80, 75)
    expect(plant_on_canvas(joiner, "Basil")).to_have_attribute("style", re.compile(r"left: 80%; top: 75%"))

    # Session 1 sees the change arrive over the live feed.
    expect(plant_on_canvas(creator, "Basil")).to_have_attribute("style", re.compile(r"left: 80%; top: 75%"))
    expect(plant_on_canvas(creator, "Mint")).to_have_attribute("style", re.compile(r"left: 70%; top: 40%"))
