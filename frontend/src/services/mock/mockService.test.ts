import { describe, expect, it, vi } from "vitest";
import { careStatus } from "../care";
import { ROOM_LIMITS } from "../types";
import { createMockService, memoryStorage } from "./mockService";
import { SEED_PLANTS } from "./plants-seed";

const actor = { name: "Robin", device_id: "dev1" };
const day = 86_400_000;

function setup() {
  let t = new Date("2026-06-01T09:00:00Z").getTime();
  const svc = createMockService({ storage: memoryStorage(), seed: false, now: () => new Date(t) });
  return { svc, advance: (days: number) => (t += days * day) };
}

describe("rooms", () => {
  it("gives rooms with the same name distinct UUIDs", async () => {
    const { svc } = setup();
    const a = await svc.createRoom({ name: "Back Garden" });
    const b = await svc.createRoom({ name: "Back Garden" });
    expect(a.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(a.id).not.toBe(b.id);
    expect((await svc.getRoomState(b.id))!.room.id).toBe(b.id);
  });

  it("returns null for an unknown room", async () => {
    const { svc } = setup();
    expect(await svc.getRoomState("00000000-0000-4000-8000-000000000000")).toBeNull();
  });

  it("requires a room name", async () => {
    const { svc } = setup();
    await expect(svc.createRoom({ name: "  " })).rejects.toThrow();
  });

  it("lists rooms newest activity first", async () => {
    const { svc, advance } = setup();
    const a = await svc.createRoom({ name: "A" });
    advance(1);
    await svc.createRoom({ name: "B" });
    advance(1);
    await svc.addPlant(a.id, "plant-basil", actor);
    const list = await svc.listRooms();
    expect(list.map((r) => r.room.name)).toEqual(["A", "B"]);
  });

});

describe("deleting a room", () => {
  it("removes the room with its data, notifies subscribers and is idempotent", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "Doomed" });
    const other = await svc.createRoom({ name: "Kept" });
    await svc.addPlant(room.id, "plant-basil", actor);
    await svc.addPlant(other.id, "plant-basil", actor);
    await svc.followRoom(room.id, "a@example.com");
    const onChange = vi.fn();
    svc.subscribe(room.id, onChange);

    await expect(svc.deleteRoom(room.id)).resolves.toBe(true);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(await svc.getRoomState(room.id)).toBeNull();
    const db = svc._db();
    expect(db.room_plants.map((p) => p.room_id)).toEqual([other.id]);
    expect(db.feed_events.every((e) => e.room_id === other.id)).toBe(true);
    expect(db.room_follows).toHaveLength(0);
    expect((await svc.listRooms()).map((r) => r.room.id)).toEqual([other.id]);

    await expect(svc.deleteRoom(room.id)).resolves.toBe(true); // second delete: no error, no change
    expect(onChange).toHaveBeenCalledTimes(1);
    expect((await svc.listRooms()).map((r) => r.room.id)).toEqual([other.id]);
  });
});

describe("plants and care", () => {
  it("adds a plant in the centre of the canvas and logs it", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const rp = await svc.addPlant(room.id, "plant-basil", actor);
    expect([rp.x_pct, rp.y_pct]).toEqual([50, 50]);
    const state = await svc.getRoomState(room.id);
    expect(state!.feed[0]).toMatchObject({ type: "plant_added", actor_name: "Robin" });
  });

  it("basil water ring counts down from its 2-day interval and resets when watered", async () => {
    const { svc, advance } = setup();
    const basil = SEED_PLANTS.find((p) => p.id === "plant-basil")!;
    const room = await svc.createRoom({ name: "R" });
    const rp = await svc.addPlant(room.id, basil.id, actor);
    advance(3);
    const now = new Date(new Date("2026-06-01T09:00:00Z").getTime() + 3 * day);
    expect(careStatus(basil, rp, "water", now)!.overdue).toBe(true);
    const watered = await svc.markCare(rp.id, "water", actor);
    const s = careStatus(basil, watered, "water", now)!;
    expect(s.overdue).toBe(false);
    expect(s.daysLeft).toBe(2);
  });

  it("does not invent a ring when the plant table has no data", () => {
    const carrot = SEED_PLANTS.find((p) => p.id === "plant-carrot")!;
    const rp = { created_at: new Date().toISOString() } as never;
    expect(careStatus(carrot, rp, "feed")).toBeNull();
  });

  it("rejects care actions the plant has no data for", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const rp = await svc.addPlant(room.id, "plant-carrot", actor);
    await expect(svc.markCare(rp.id, "feed", actor)).rejects.toThrow();
  });

  it("clamps moves to the canvas", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const rp = await svc.addPlant(room.id, "plant-basil", actor);
    const moved = await svc.movePlant(rp.id, 140, -5, actor);
    expect([moved.x_pct, moved.y_pct]).toEqual([100, 0]);
  });
});

describe("room limits", () => {
  const area = { label: "Bed", shape: "rect", x_pct: 1, y_pct: 1, w_pct: 10, h_pct: 10, colour: "soil" } as const;

  it(`caps a room at ${ROOM_LIMITS.plants} live plants`, async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const added = [];
    for (let i = 0; i < ROOM_LIMITS.plants; i++) added.push(await svc.addPlant(room.id, "plant-basil", actor));
    await expect(svc.addPlant(room.id, "plant-basil", actor)).rejects.toThrow(/full/);
    await svc.removePlant(added[0]!.id, actor);
    await expect(svc.addPlant(room.id, "plant-basil", actor)).resolves.toBeTruthy();
  });

  it(`caps a room at ${ROOM_LIMITS.areas} live areas`, async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    for (let i = 0; i < ROOM_LIMITS.areas; i++) await svc.addArea(room.id, area, actor);
    await expect(svc.addArea(room.id, area, actor)).rejects.toThrow(/maximum/);
  });

  it("won't undo a removal into a full room", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const first = await svc.addPlant(room.id, "plant-basil", actor);
    await svc.removePlant(first.id, actor);
    for (let i = 0; i < ROOM_LIMITS.plants; i++) await svc.addPlant(room.id, "plant-basil", actor);
    const state = await svc.getRoomState(room.id);
    const removal = state!.feed.find((e) => e.type === "plant_removed")!;
    await expect(svc.undoEvent(removal.id, actor)).rejects.toThrow(/full/);
    expect((await svc.getRoomState(room.id))!.feed.find((e) => e.id === removal.id)!.undone_at).toBeNull();
  });

  it("won't undo an area deletion into a full room", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const a = await svc.addArea(room.id, area, actor);
    await svc.deleteArea(a.id, actor);
    for (let i = 0; i < ROOM_LIMITS.areas; i++) await svc.addArea(room.id, area, actor);
    const del = (await svc.getRoomState(room.id))!.feed.find((e) => e.text.startsWith("removed"))!;
    await expect(svc.undoEvent(del.id, actor)).rejects.toThrow(/maximum/);
  });

  it("rejects plants for a room that doesn't exist", async () => {
    const { svc } = setup();
    await expect(svc.addPlant("nope", "plant-basil", actor)).rejects.toThrow(/not found/);
  });
});

describe("undo", () => {
  it("undoing a removal brings the plant back", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const rp = await svc.addPlant(room.id, "plant-rose", actor);
    await svc.removePlant(rp.id, actor);
    let state = await svc.getRoomState(room.id);
    expect(state!.plants).toHaveLength(0);
    const ev = state!.feed.find((e) => e.type === "plant_removed")!;
    await svc.undoEvent(ev.id, actor);
    state = await svc.getRoomState(room.id);
    expect(state!.plants.map((p) => p.id)).toEqual([rp.id]);
    await expect(svc.undoEvent(ev.id, actor)).rejects.toThrow();
  });

  it("undoing a move restores the old position", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const rp = await svc.addPlant(room.id, "plant-rose", actor);
    await svc.movePlant(rp.id, 10, 20, actor);
    const state = await svc.getRoomState(room.id);
    await svc.undoEvent(state!.feed.find((e) => e.type === "plant_moved")!.id, actor);
    const after = await svc.getRoomState(room.id);
    expect([after!.plants[0]!.x_pct, after!.plants[0]!.y_pct]).toEqual([50, 50]);
  });

  it("undoing an area add removes it", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    await svc.addArea(room.id, { label: "Pond", shape: "ellipse", x_pct: 1, y_pct: 1, w_pct: 10, h_pct: 10, colour: "water" }, actor);
    const s = await svc.getRoomState(room.id);
    await svc.undoEvent(s!.feed[0]!.id, actor);
    expect((await svc.getRoomState(room.id))!.areas).toHaveLength(0);
  });

  it("posts have no undo", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const ev = await svc.postUpdate(room.id, "First tomatoes!", null, actor);
    await expect(svc.undoEvent(ev.id, actor)).rejects.toThrow();
  });
});

describe("identify, follow, realtime", () => {
  it("returns up to 3 candidates and rejects files over 5 MB", async () => {
    const { svc } = setup();
    const ok = new File(["x"], "leaf.jpg", { type: "image/jpeg" });
    expect((await svc.identifyPlant(ok)).length).toBeLessThanOrEqual(3);
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.jpg", { type: "image/jpeg" });
    await expect(svc.identifyPlant(big)).rejects.toThrow();
    const gif = new File(["x"], "a.gif", { type: "image/gif" });
    await expect(svc.identifyPlant(gif)).rejects.toThrow();
  });

  it("follows without leaking the unsubscribe token and validates email", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    await expect(svc.followRoom(room.id, "nope")).rejects.toThrow();
    const f = await svc.followRoom(room.id, "Me@Example.com");
    expect(f.email).toBe("me@example.com");
    expect(f).not.toHaveProperty("unsubscribe_token");
    expect(await svc.followRoom(room.id, "me@example.com")).not.toHaveProperty("unsubscribe_token");
    const token = svc._db().room_follows[0]!.unsubscribe_token;
    expect(await svc.unfollow(token)).toBe(true);
    expect(await svc.unfollow(token)).toBe(false);
  });

  it("stores uploaded photos and attaches them to posts by id", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    const photo = await svc.uploadPhoto(new File(["hi"], "tomato.png", { type: "image/png" }));
    expect(photo.url).toBe("data:image/png;base64,aGk=");
    const ev = await svc.postUpdate(room.id, "", photo.id, actor);
    expect(ev.photo_url).toBe(photo.url);
    await expect(svc.postUpdate(room.id, "x", "missing", actor)).rejects.toThrow();
    await expect(svc.uploadPhoto(new File(["x"], "a.gif", { type: "image/gif" }))).rejects.toThrow();
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.jpg", { type: "image/jpeg" });
    await expect(svc.uploadPhoto(big)).rejects.toThrow();
  });

  it("notifies subscribers on change", async () => {
    const { svc } = setup();
    const room = await svc.createRoom({ name: "R" });
    let calls = 0;
    const off = svc.subscribe(room.id, () => calls++);
    await svc.addPlant(room.id, "plant-basil", actor);
    off();
    await svc.addPlant(room.id, "plant-basil", actor);
    expect(calls).toBe(1);
  });

  it("seeds two demo gardens on first run", async () => {
    const svc = createMockService({ storage: memoryStorage() });
    expect((await svc.listRooms()).length).toBe(2);
  });

  it("seeds about 50 plants", () => {
    expect(SEED_PLANTS.length).toBeGreaterThanOrEqual(45);
  });
});
