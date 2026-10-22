# Design system

Templating and UI conventions to follow for anything touching the UI. Read
this before touching the UI, per `AGENT.md`.

## Templating approach

Per `_docs/outdated/architecture.md` §1 and §4, the target frontend approach
is **Django templates + htmx** (progressive enhancement, no separate SPA) -
no separate frontend build, no JS framework, no client-side router.

Current reality (as of this doc, screens from #1-#4): every screen is
plain, full-page Django templates. **htmx has not been introduced yet** -
there is no htmx script tag anywhere, no `hx-*` attribute, and no partial/
fragment templates. All templates render a full HTML document and all form
submissions are ordinary browser `POST`s. Treat htmx as the direction to
head in as soon as a screen needs partial updates (e.g. inline comments,
live board updates per `_docs/outdated/architecture.md` §4) - don't add it
speculatively to screens that don't need it yet.

Django's template engine is configured with defaults in
`app/config/settings.py`: `APP_DIRS: True`, so templates live under each
app's `templates/` directory (`app/<app>/templates/<app>/*.html`), e.g.
`app/projects/templates/projects/project_create.html`. The context processors
enabled are the standard `request`, `auth`, and `messages` ones - `{{ user }}`
and template `{% url %}` tags are available in every template without
passing them explicitly.

`registration/` is the one exception to the `<app>/templates/<app>/` nesting:
login/register live under `app/core/templates/registration/` because that's
the directory Django's built-in auth views look for by convention.

## CSS / styling

**Plain CSS - no framework, no utility system.** There is no CSS framework
(no Bootstrap/Tailwind/etc.) and, currently, no CSS at all: there's no
`static/` directory in any app and no `<link>`/`<style>` tag in any
template. Pages render as unstyled HTML. `STATIC_URL` is configured
(`app/config/settings.py`) and `django.contrib.staticfiles` is installed,
so the mechanism for adding CSS is ready, but no one has used it yet.

When a screen needs styling: add a per-app `static/<app>/...css` file (mirror
the `templates/<app>/` nesting) and link it with `{% load static %}` /
`{% static %}`, plain CSS (no preprocessor, no bundler) — that's what the
existing static/staticfiles setup supports out of the box. Don't introduce a
CSS framework or utility system without raising it first, matching the
dependency rule in `AGENT.md` (CSS frameworks pulled in via a package, e.g. a
Tailwind build step, count as a dependency decision).

## Base template / layout conventions

**There is no shared base template yet.** Every existing template
(`core/templates/core/dashboard.html`, `core/templates/registration/
login.html`, `core/templates/registration/register.html`,
`projects/templates/projects/project_create.html`,
`projects/templates/projects/project_detail.html`) is a fully self-contained
document repeating the same boilerplate:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>...</title>
</head>
<body>
    <h1>...</h1>
    ...
</body>
</html>
```

Until a shared base template is introduced, new screens should copy this
same boilerplate (`<!DOCTYPE html>`, `lang="en"`, `<meta charset="utf-8">`,
a `<title>` describing the page, an `<h1>` matching the title/heading) rather
than inventing a different shell. Introducing a `{% extends %}` base template
is expected but is its own piece of work (touches every existing template),
not something to fold silently into an unrelated UI change.

Other observed conventions to keep following on new screens:

- Forms: `<form method="post">` (explicit `action="{% url '...' %}"` when
  the form posts to a named URL other than the current page, e.g.
  `login.html`; omitted when posting back to the same view, e.g.
  `project_create.html`), immediately followed by `{% csrf_token %}`, then
  `{{ form.as_p }}` for field rendering - no manual per-field markup, no
  form-rendering helper library.
  - `login.html` also threads through a hidden `next` field
    (`<input type="hidden" name="next" value="{{ next }}">`) since it needs
    to preserve the redirect target across the `POST`.
- Submit buttons are plain `<button type="submit">Action Label</button>`
  with a specific, task-named label (`Create account`, `Log in`,
  `Create Project`), not a generic "Submit".
- Cross-links between related pages are a plain `<p><a href="...">...</a></p>`
  below the form, phrased as a question (e.g. `Need an account? Register`,
  `Already have an account? Log in`).
- Conditional content uses straightforward `{% if %}` blocks
  (`project_detail.html` only renders the description `<p>` when
  `project.description` is truthy) rather than defaulting to empty string in
  the view.
- Model-derived display strings use Django's built-ins rather than
  reimplementing formatting - e.g. `{{ project.get_deadline_weekday_display }}`
  and `{{ project.deadline_time|time:"g:i A" }}` in `project_detail.html`.

## Summary for new screens

1. Copy the existing full-document template boilerplate until a base
   template exists.
2. Use `{{ form.as_p }}` plus `{% csrf_token %}` for forms; don't hand-roll
   field markup.
3. No CSS/JS framework, no htmx, unless the screen actually needs
   partial/live updates - and even then, raise it rather than adding it
   silently.
4. Keep it in the app's own `templates/<app>/` directory (or
   `templates/registration/` for auth views specifically).
