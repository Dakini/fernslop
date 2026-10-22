# Fernslop — Lovable Build Spec

> Paste this whole document into Lovable as the first prompt. It replaces the community/personal-garden scope in `plan.md`.

## 1. What we're building

A cosy, public, community gardening web app. Anyone can create a **room**, which represents one real garden (a home garden, allotment or balcony). Rooms are listed on a public index and shared by link. **Anyone can edit any room. There are no accounts.**

Inside a room, visitors:
- add plants (by photo identification or by searching a plant table),
- arrange them on a free-form garden canvas,
- keep care tasks ticking along (watering, feeding, etc.),
- post updates and photos to the room's activity feed.

**Product promise:** a shared, living garden plan that anyone can help tend.

## 2. Scope

### In
- Public index of all rooms.
- Create a room (no login).
- Room page: free canvas, plant list, care tasks, activity feed.
- Add plant: search the plant table, or upload a photo for identification. The user confirms the match before it is added.
- Care countdown rings per plant, based on plant data.
- Optional nickname, remembered per device.
- Optional "follow this room" by email.
- Share link per room.

### Out
- User accounts, login, passwords.
- Private rooms and permissions.
- Personal "My Garden" collection.
- Chat or direct messages.
- Native mobile apps.
- Moderation tools beyond the change history.

## 3. Pages

### 3.1 Index `/`
- Header: app name, short tagline, **Create a room** button.
- Grid of room cards, newest activity first.
- Each card shows: **canvas thumbnail** (a mini render of the room's canvas) and the room name. Click opens the room.
- Simple search box filtering by room name.
- Empty state: friendly illustration + "Plant the first garden" CTA.

### 3.2 Create room (modal or `/new`)
- Fields: room name (required), short description (optional), country/region (optional, shown as text only).
- On create: redirect to the room and show a "Share this garden" toast with a copy-link button.

### 3.3 Room `/r/:slug`
Layout: canvas as the hero. Side panel on desktop, tabs below the canvas on mobile.

**Header:** room name, description, Share button, Follow button (email), nickname chip ("You're Anonymous Hedgehog · change").

**Free canvas**
- A fixed-size garden area (16:10 ratio) with a soft, textured soil/grass background. It scales to fit the screen with no infinite scrolling or zooming.
- **Room limits:** max **50 plants** and **10 labelled areas** per room. When a limit is reached, the + button shows a friendly "This garden is full — remove something to make space" message.
- Each plant is a round token (photo or illustration + name label).
- Drag tokens anywhere. Positions are stored as x/y percentages so they scale.
- Optional freeform labelled areas (rectangles/ovals) such as "Veg bed" or "Pond", which can be added, resized, renamed and deleted.
- Clicking a plant token opens its plant drawer.
- Changes save automatically and update live for other visitors.

**Plant drawer** (opens from token or list)
- Name, scientific name, image, description, source attribution.
- Care rings (see 3.4).
- "Mark watered" / "Mark fed" etc. buttons. Each one resets that ring and posts to the feed.
- Remove plant (logged to the feed, can be undone from the feed).

**Tabs / side panel**
1. **Plants**: list of plant cards in the reference style (photo, name, care rings), filterable by category (All / Flowers / Vegetables / Herbs / Houseplants).
2. **Tasks**: all care actions due, soonest first. Overdue items use the warm accent colour. Tick to complete.
3. **Feed**: chronological activity. Auto events ("Robin watered the Basil", "Someone added a Dahlia", "Plant moved") plus manual posts (text + optional photo). Every auto event on plants and areas has an **Undo** link.

**Floating "+" button:** Add plant.

### 3.4 Care rings
- One circular countdown per care type the plant data supports (water, feed, prune, harvest).
- Shows days remaining, e.g. "2d".
- Intervals come **only from the plant table**. Users cannot edit them.
- Reset when someone marks the action done.
- Overdue: ring turns terracotta with a small dot. Wording stays gentle ("Basil would love a drink").
- If the plant has no data for a care type, don't show that ring and don't invent one.

### 3.5 Add plant flow (modal)
Two tabs:
1. **Search**: type a common or scientific name, then pick from the plant table results (image, names).
2. **Photo**: upload a JPG/PNG/WebP up to 5 MB. This calls the identification API through a server function, which returns up to 3 candidates with confidence. The user taps the correct one, or falls back to Search.

After confirming, the plant is dropped in the centre of the canvas, ready to drag.

## 4. Identity (no accounts)
- On first visit, generate a random `device_id` and a fun default name ("Anonymous Hedgehog", "Anonymous Toad") and store both in localStorage.
- The user can change their nickname from the chip. Feed events store the nickname as text.

## 5. Follow by email
- "Follow" opens a small form asking only for an email.
- Store it against the room with an unsubscribe token.
- Emails go out weekly (scheduled function) **only if the room had activity**: summary of tasks due + recent feed items + link back.
- Every email has a one-click unsubscribe link.
- Can be stubbed for the first build: store follows, build the email later.

## 6. Data model (Supabase)

**rooms**: `id`, `slug` (unique), `name`, `description`, `region`, `created_at`, `last_activity_at`

**plants** (reference table, seeded): `id`, `common_name`, `scientific_name`, `category` (flower/vegetable/herb/houseplant/shrub/tree), `description`, `image_url`, `water_every_days`, `feed_every_days`, `prune_every_days`, `harvest_every_days` (nullable), `source`, `source_url`

**room_plants**: `id`, `room_id`, `plant_id`, `nickname` (optional), `x_pct`, `y_pct`, `last_watered_at`, `last_fed_at`, `last_pruned_at`, `last_harvested_at`, `added_by_name`, `created_at`, `deleted_at` (soft delete for undo)

**room_areas**: `id`, `room_id`, `label`, `shape` (rect/ellipse), `x_pct`, `y_pct`, `w_pct`, `h_pct`, `colour`, `deleted_at`

**feed_events**: `id`, `room_id`, `type` (plant_added, plant_removed, plant_moved, care_done, area_changed, post), `actor_name`, `device_id`, `room_plant_id` (nullable), `text`, `photo_url`, `undo_payload` (json), `undone_at`, `created_at`

**room_follows**: `id`, `room_id`, `email`, `unsubscribe_token`, `created_at`

Notes:
- Enforce the room limits (50 plants, 10 areas, not counting soft-deleted rows) in the database, not just the UI.
- No auth. Use RLS policies allowing anonymous read/insert/update on room tables. Deletes are soft.
- Enable Supabase Realtime on `room_plants`, `room_areas` and `feed_events`.
- Photo uploads go to a Supabase Storage bucket, compressed client-side first.
- Seed `plants` with ~50 common UK/US garden plants with sensible care intervals and a source noted.

## 7. Server functions
- `identify-plant`: receives the image, calls a plant ID API (e.g. Plant.id or PlantNet) with the server-side key, and maps results to `plants` rows where possible.
- `weekly-follow-digest`: scheduled weekly job, sends emails via Resend (or stub).
- Keep all API keys server-side.

## 8. Visual design

Cosy botanical, gently game-inspired (in the spirit of Stardew Valley; do not copy its art).

- **Palette:** sage green `#9CAF88` (primary), deep moss `#4F6B4A` (text/headings), warm cream `#F7F1E3` (background), oat `#EADFC8` (cards/surfaces), terracotta `#C9734F` (overdue/accent), soft clay `#E4B69A` (highlights).
- **Shapes:** generously rounded cards (20–24px radius), pill buttons, soft shadows.
- **Type:** a friendly rounded sans for headings (e.g. Nunito or Quicksand) and a clean sans for body.
- **Canvas:** textured grass/soil background with subtle hand-drawn detail. Plant tokens are round with a cream border and a small label.
- **Plant cards:** layout like the mobile reference: round photo left, name top, care rings in small rounded tiles.
- **Icons:** simple line icons (watering can, seedling, scissors, basket).
- **Motion:** gentle (tokens bob slightly when dropped). Respect `prefers-reduced-motion`.
- **Mobile-first and responsive.** On mobile: canvas on top, tabs below, floating + button bottom-right.

## 9. Accessibility
- WCAG AA contrast on cream backgrounds.
- All canvas actions also possible from the Plants list, so dragging isn't required.
- Keyboard: tokens focusable, arrow keys nudge position.
- Alt text on plant images; labels on all inputs.
- Visible loading, success and error states.

## 10. Error and empty states
- Photo ID fails or has low confidence: "We couldn't be sure — try searching instead" with Search tab opened.
- Plant missing care data: show what we have, and note "No watering data available".
- Empty room: illustration on the canvas + "Add the first plant".
- Realtime disconnect: small "Reconnecting…" pill. Edits queue and retry.

## 11. Build order (suggested prompts)
1. Design system, index page, create room, room page shell with tabs. Seed `plants`.
2. Add plant via search, plant list with care rings, mark-done actions.
3. Free canvas: drag tokens, labelled areas, save positions, realtime sync, index thumbnails.
4. Activity feed with auto events, manual posts with photos, undo.
5. Photo identification function.
6. Follow by email + weekly digest.

## 12. Done when
- A visitor can create a room and share its link.
- Anyone with the link (or from the index) can add plants by search or photo.
- Plants can be arranged on the canvas, and other visitors see changes live.
- Care rings count down from plant data and reset when marked done.
- All changes appear in the feed and can be undone.
- Visitors can set a nickname and optionally follow a room by email.
- Works well on phone and desktop.
