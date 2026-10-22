from playwright.sync_api import expect


def test_unknown_path_loaded_directly_shows_404_page_without_console_errors(new_gardener):
    page = new_gardener().new_page()
    errors: list[str] = []
    page.on("console", lambda message: message.type == "error" and errors.append(message.text))
    page.on("pageerror", lambda error: errors.append(str(error)))

    page.goto("/nope")

    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()
    # Hydration finishes before the 404 swaps in, so a #418 would already have been reported.
    page.get_by_role("link", name="Go home").click()
    expect(page.get_by_role("heading", level=1, name="Gardens anyone can tend")).to_be_visible()
    assert errors == []
