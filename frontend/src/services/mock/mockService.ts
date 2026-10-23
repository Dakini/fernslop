import { CARE_FIELDS, CARE_LABELS } from "../care";
import type {
  Actor,
  AreaInput,
  FeedEvent,
  FeedEventType,
  GardenService,
  IdentifyCandidate,
  Photo,
  Plant,
  Room,
  RoomArea,
  RoomFollow,
  RoomPlant,
  UndoPayload,
} from "../types";
import { FEED_PAGE_SIZE, ROOM_LIMITS } from "../types";
import { SEED_PLANTS } from "./plants-seed";

/** Server-side follow row: the token never leaves the "server". */
export interface StoredFollow extends RoomFollow {
  id: string;
  created_at: string;
  unsubscribe_token: string;
  /** Unset until the emailed link is opened; only confirmed follows get digests. */
  confirmed_at?: string | null;
}

const CONFIRM_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

export interface StoredPhoto extends Photo {
  content_type: string;
  created_at: string;
}

export interface MockDB {
  rooms: Room[];
  room_plants: RoomPlant[];
  room_areas: RoomArea[];
  feed_events: FeedEvent[];
  room_follows: StoredFollow[];
  photos: StoredPhoto[];
}

export interface MockStorage {
  load(): MockDB | null;
  save(db: MockDB): void;
}

export const memoryStorage = (): MockStorage => {
  let data: MockDB | null = null;
  return { load: () => data, save: (db) => (data = structuredClone(db)) };
};

/** Same paging and search caps as the server (#202). */
const ROOM_PAGE_SIZE = 30;
const MAX_ROOM_PAGE_SIZE = 100;
const SEARCH_LIMIT = 12;
/** Feed paging like the server (#210); the mock never caps posts. */
const MAX_FEED_PAGE_SIZE = 100;

const LS_KEY = "fernslop:mockdb:v2";
export const localStorageAdapter = (): MockStorage => ({
  load: () => {
    try {
      const raw = window.localStorage.getItem(LS_KEY);
      return raw ? (JSON.parse(raw) as MockDB) : null;
    } catch {
      return null;
    }
  },
  save: (db) => {
    try {
      window.localStorage.setItem(LS_KEY, JSON.stringify(db));
    } catch {
      /* quota exceeded: keep in memory */
    }
  },
});

export interface MockOptions {
  storage?: MockStorage;
  now?: () => Date;
  latencyMs?: number;
  seed?: boolean;
  plants?: Plant[];
  random?: () => number;
  /** Sync changes across browser tabs (simulates realtime). */
  broadcast?: boolean;
}

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

function checkImage(file: File) {
  if (!IMAGE_TYPES.includes(file.type)) throw new Error("Please use a JPG, PNG or WebP image");
  if (file.size > MAX_IMAGE_BYTES) throw new Error("That photo is over 5 MB");
}

function toDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Couldn't read that photo"));
    r.readAsDataURL(file);
  });
}

const SYSTEM: Actor = { name: "Fernslop", device_id: "seed" };

export function createMockService(opts: MockOptions = {}): GardenService & { _db: () => MockDB } {
  const storage = opts.storage ?? memoryStorage();
  const now = opts.now ?? (() => new Date());
  const latency = opts.latencyMs ?? 0;
  const plants = opts.plants ?? SEED_PLANTS;
  const rand = opts.random ?? Math.random;
  const listeners = new Map<string, Set<() => void>>();
  const channel =
    opts.broadcast && typeof BroadcastChannel !== "undefined"
      ? new BroadcastChannel("fernslop-mock")
      : null;

  let idCounter = 0;
  const uid = (p: string) => `${p}_${now().getTime().toString(36)}${(idCounter++).toString(36)}${Math.floor(rand() * 1e6).toString(36)}`;
  const iso = () => now().toISOString();
  const wait = <T>(v: T): Promise<T> =>
    latency ? new Promise((r) => setTimeout(() => r(structuredClone(v)), latency)) : Promise.resolve(structuredClone(v));

  let db: MockDB = storage.load() ?? { rooms: [], room_plants: [], room_areas: [], feed_events: [], room_follows: [], photos: [] };

  const reload = () => {
    const fresh = storage.load();
    if (fresh) db = fresh;
  };

  function emit(roomId: string, fromRemote = false) {
    listeners.get(roomId)?.forEach((fn) => fn());
    listeners.get("*")?.forEach((fn) => fn());
    if (!fromRemote) channel?.postMessage(roomId);
  }
  channel?.addEventListener("message", (e) => {
    reload();
    emit(String(e.data), true);
  });

  function commit(roomId: string) {
    const room = db.rooms.find((r) => r.id === roomId);
    if (room) room.last_activity_at = iso();
    storage.save(db);
    emit(roomId);
  }

  const plantById = (id: string) => {
    const p = plants.find((x) => x.id === id);
    if (!p) throw new Error("Plant not found");
    return p;
  };
  const rpById = (id: string) => {
    const rp = db.room_plants.find((x) => x.id === id && !x.deleted_at);
    if (!rp) throw new Error("Plant is no longer in this garden");
    return rp;
  };
  const roomById = (id: string) => {
    const room = db.rooms.find((r) => r.id === id);
    if (!room) throw new Error("Garden not found");
    return room;
  };
  const livePlants = (roomId: string) => db.room_plants.filter((p) => p.room_id === roomId && !p.deleted_at);
  const liveAreas = (roomId: string) => db.room_areas.filter((a) => a.room_id === roomId && !a.deleted_at);
  const checkPlantRoom = (roomId: string) => {
    if (livePlants(roomId).length >= ROOM_LIMITS.plants) throw new Error(`This garden is full (${ROOM_LIMITS.plants} plants max)`);
  };
  const checkAreaRoom = (roomId: string) => {
    if (liveAreas(roomId).length >= ROOM_LIMITS.areas) throw new Error(`This garden has the maximum ${ROOM_LIMITS.areas} areas`);
  };
  const displayName = (rp: RoomPlant) => rp.nickname ?? plantById(rp.plant_id).common_name;

  function log(
    roomId: string,
    type: FeedEventType,
    actor: Actor,
    text: string,
    extra: Partial<FeedEvent> = {},
  ): FeedEvent {
    const ev: FeedEvent = {
      id: uid("ev"),
      room_id: roomId,
      type,
      actor_name: actor.name,
      device_id: actor.device_id,
      room_plant_id: null,
      text,
      photo_url: null,
      undo_payload: null,
      undone_at: null,
      created_at: iso(),
      ...extra,
    };
    db.feed_events.push(ev);
    return ev;
  }

  function insertRoom(input: { name: string; description?: string; region?: string }): Room {
    const room: Room = {
      id: crypto.randomUUID(),
      name: input.name.trim(),
      description: input.description?.trim() ?? "",
      region: input.region?.trim() ?? "",
      created_at: iso(),
      last_activity_at: iso(),
    };
    db.rooms.push(room);
    return room;
  }

  function insertPlant(roomId: string, plantId: string, actor: Actor, x = 50, y = 50): RoomPlant {
    roomById(roomId);
    plantById(plantId);
    checkPlantRoom(roomId);
    const rp: RoomPlant = {
      id: uid("rp"),
      room_id: roomId,
      plant_id: plantId,
      nickname: null,
      x_pct: x,
      y_pct: y,
      last_watered_at: null,
      last_fed_at: null,
      last_pruned_at: null,
      last_harvested_at: null,
      added_by_name: actor.name,
      created_at: iso(),
      deleted_at: null,
    };
    db.room_plants.push(rp);
    return rp;
  }

  function seed() {
    const a = insertRoom({ name: "Elm Street Allotment", description: "Plot 14 — shared by the whole street.", region: "Bristol, UK" });
    const areaVeg: RoomArea = { id: uid("area"), room_id: a.id, label: "Veg bed", shape: "rect", x_pct: 8, y_pct: 12, w_pct: 40, h_pct: 45, colour: "soil", deleted_at: null };
    const areaPond: RoomArea = { id: uid("area"), room_id: a.id, label: "Pond", shape: "ellipse", x_pct: 62, y_pct: 55, w_pct: 26, h_pct: 30, colour: "water", deleted_at: null };
    db.room_areas.push(areaVeg, areaPond);
    for (const [pid, x, y] of [["plant-tomato", 18, 25], ["plant-courgette", 36, 40], ["plant-basil", 22, 46], ["plant-sunflower", 70, 22]] as const) {
      const rp = insertPlant(a.id, pid, SYSTEM, x, y);
      log(a.id, "plant_added", SYSTEM, `added the ${displayName(rp)}`, { room_plant_id: rp.id });
    }
    const b = insertRoom({ name: "Balcony Jungle", description: "Third-floor balcony, south facing.", region: "Leeds, UK" });
    for (const [pid, x, y] of [["plant-monstera", 30, 50], ["plant-chilli-pepper", 60, 40], ["plant-geranium", 75, 65]] as const) {
      insertPlant(b.id, pid, SYSTEM, x, y);
    }
    storage.save(db);
  }

  // The plant or area an undo writes to; null for an event with no undo (a post).
  const undoTarget = (p: UndoPayload | null) =>
    !p ? null
    : p.kind === "restore_plant" ? `plant:${p.room_plant.id}`
    : p.kind === "delete_plant" ? `plant:${p.room_plant_id}`
    : `area:${p.area_id}`;

  // Refuse an undo that would revert a later, not-undone event for the same plant or area.
  // feed_events is in save order, so every event after this one is later.
  function checkNoLaterChanges(ev: FeedEvent) {
    const target = undoTarget(ev.undo_payload);
    const later = db.feed_events.slice(db.feed_events.indexOf(ev) + 1);
    if (later.some((e) => e.room_id === ev.room_id && !e.undone_at && undoTarget(e.undo_payload) === target)) {
      throw new Error(`Undo the later changes to this ${target!.startsWith("plant:") ? "plant" : "area"} first`);
    }
  }

  function applyUndo(p: UndoPayload) {
    if (p.kind === "restore_plant") {
      const i = db.room_plants.findIndex((x) => x.id === p.room_plant.id);
      const revives = !p.room_plant.deleted_at && (i < 0 || db.room_plants[i]!.deleted_at);
      if (revives) checkPlantRoom(p.room_plant.room_id);
      if (i >= 0) db.room_plants[i] = { ...p.room_plant };
      else db.room_plants.push({ ...p.room_plant });
    } else if (p.kind === "delete_plant") {
      const rp = db.room_plants.find((x) => x.id === p.room_plant_id);
      if (rp) rp.deleted_at = iso();
    } else {
      const i = db.room_areas.findIndex((x) => x.id === p.area_id);
      const revives = p.area && !p.area.deleted_at && (i < 0 || db.room_areas[i]!.deleted_at);
      if (revives) checkAreaRoom(p.area!.room_id);
      if (p.area === null) {
        if (i >= 0) db.room_areas[i]!.deleted_at = iso();
      } else if (i >= 0) db.room_areas[i] = { ...p.area };
      else db.room_areas.push({ ...p.area });
    }
  }

  // A room's feed newest first, like the server: created_at, then save order (feed_events is in save order).
  function roomFeed(roomId: string): FeedEvent[] {
    return db.feed_events
      .map((e, i) => ({ e, i }))
      .filter(({ e }) => e.room_id === roomId)
      .sort((a, b) => b.e.created_at.localeCompare(a.e.created_at) || b.i - a.i)
      .map(({ e }) => e);
  }

  // One page after the event `before` (the cursor is an event id, as on the server).
  function feedPage(roomId: string, before: string | null | undefined, limit: number) {
    if (!Number.isInteger(limit) || limit < 1 || limit > MAX_FEED_PAGE_SIZE)
      throw new Error(`limit must be a whole number from 1 to ${MAX_FEED_PAGE_SIZE}`);
    let events = roomFeed(roomId);
    if (before) {
      const at = events.findIndex((e) => e.id === before);
      if (at < 0) throw new Error("before is not a cursor this server gave out");
      events = events.slice(at + 1);
    }
    const page = events.slice(0, limit);
    return { events: page, next: events.length > limit ? page[page.length - 1]!.id : null };
  }

  if (!storage.load() && opts.seed !== false) seed();

  return {
    _db: () => db,

    async listRooms({ before, limit = ROOM_PAGE_SIZE } = {}) {
      reload();
      if (!Number.isInteger(limit) || limit < 1 || limit > MAX_ROOM_PAGE_SIZE)
        throw new Error(`limit must be a whole number from 1 to ${MAX_ROOM_PAGE_SIZE}`);
      // Same keyset cursor as the server: newest activity first, then created_at, then id.
      const key = (r: Room) => `${r.last_activity_at}_${r.created_at}_${r.id}`;
      let rooms = [...db.rooms].sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0));
      if (before) rooms = rooms.filter((r) => key(r) < before);
      const page = rooms.slice(0, limit);
      return wait({
        rooms: page.map((room) => ({
          room,
          plants: db.room_plants
            .filter((p) => p.room_id === room.id && !p.deleted_at)
            .map((p) => ({ x_pct: p.x_pct, y_pct: p.y_pct, category: plantById(p.plant_id).category })),
          areas: db.room_areas.filter((x) => x.room_id === room.id && !x.deleted_at),
        })),
        next: rooms.length > limit ? key(page[page.length - 1]!) : null,
      });
    },

    async createRoom(input) {
      if (!input.name?.trim()) throw new Error("A room needs a name");
      const room = insertRoom(input);
      commit(room.id);
      return wait(room);
    },

    async getRoomState(roomId) {
      reload();
      const room = db.rooms.find((r) => r.id === roomId);
      if (!room) return wait(null);
      const feed = feedPage(room.id, null, FEED_PAGE_SIZE);
      return wait({
        room,
        plants: livePlants(room.id),
        areas: liveAreas(room.id),
        feed: feed.events,
        feed_next: feed.next,
      });
    },

    async getRoomFeed(roomId, { before, limit = FEED_PAGE_SIZE } = {}) {
      reload();
      roomById(roomId);
      return wait(feedPage(roomId, before, limit));
    },

    async deleteRoom(roomId) {
      if (!db.rooms.some((r) => r.id === roomId)) return wait(true); // already gone: idempotent
      db.rooms = db.rooms.filter((r) => r.id !== roomId);
      db.room_plants = db.room_plants.filter((p) => p.room_id !== roomId);
      db.room_areas = db.room_areas.filter((a) => a.room_id !== roomId);
      db.feed_events = db.feed_events.filter((e) => e.room_id !== roomId);
      db.room_follows = db.room_follows.filter((f) => f.room_id !== roomId);
      storage.save(db);
      emit(roomId);
      return wait(true);
    },

    async listPlants() {
      return wait(plants);
    },

    async searchPlants(query) {
      const q = query.trim().toLowerCase();
      const matches = q
        ? plants.filter((p) => p.common_name.toLowerCase().includes(q) || p.scientific_name.toLowerCase().includes(q))
        : plants;
      return wait(matches.slice(0, SEARCH_LIMIT));
    },

    async identifyPlant(file) {
      checkImage(file);
      // Mock: deterministic pseudo-candidates from the file name/size.
      let h = 0;
      for (const ch of file.name + file.size) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
      const picks: IdentifyCandidate[] = [];
      const confs = [0.82, 0.11, 0.04];
      for (let i = 0; i < 3; i++) picks.push({ plant: plants[(h + i * 7) % plants.length]!, confidence: confs[i]! });
      if (file.name.toLowerCase().includes("blurry")) return wait(picks.map((c) => ({ ...c, confidence: c.confidence / 4 })));
      return wait(picks);
    },

    async addPlant(roomId, plantId, actor) {
      const rp = insertPlant(roomId, plantId, actor);
      log(roomId, "plant_added", actor, `added a ${displayName(rp)}`, {
        room_plant_id: rp.id,
        undo_payload: { kind: "delete_plant", room_plant_id: rp.id },
      });
      commit(roomId);
      return wait(rp);
    },

    async movePlant(id, x, y, actor) {
      const rp = rpById(id);
      const before = { ...rp };
      rp.x_pct = Math.max(0, Math.min(100, x));
      rp.y_pct = Math.max(0, Math.min(100, y));
      log(rp.room_id, "plant_moved", actor, `moved the ${displayName(rp)}`, {
        room_plant_id: rp.id,
        undo_payload: { kind: "restore_plant", room_plant: before },
      });
      commit(rp.room_id);
      return wait(rp);
    },

    async removePlant(id, actor) {
      const rp = rpById(id);
      const before = { ...rp };
      rp.deleted_at = iso();
      log(rp.room_id, "plant_removed", actor, `removed the ${displayName(rp)}`, {
        room_plant_id: rp.id,
        undo_payload: { kind: "restore_plant", room_plant: before },
      });
      commit(rp.room_id);
      return wait(undefined);
    },

    async markCare(id, care, actor) {
      const rp = rpById(id);
      const plant = plantById(rp.plant_id);
      if (!plant[CARE_FIELDS[care].interval]) throw new Error(`No ${care} data for this plant`);
      const before = { ...rp };
      (rp as unknown as Record<string, string>)[CARE_FIELDS[care].last as string] = iso();
      log(rp.room_id, "care_done", actor, `${CARE_LABELS[care].done} the ${displayName(rp)}`, {
        room_plant_id: rp.id,
        undo_payload: { kind: "restore_plant", room_plant: before },
      });
      commit(rp.room_id);
      return wait(rp);
    },

    async addArea(roomId, input, actor) {
      roomById(roomId);
      checkAreaRoom(roomId);
      const area: RoomArea = { id: uid("area"), room_id: roomId, deleted_at: null, ...input };
      db.room_areas.push(area);
      log(roomId, "area_changed", actor, `added the "${area.label}" area`, {
        undo_payload: { kind: "restore_area", area: null, area_id: area.id },
      });
      commit(roomId);
      return wait(area);
    },

    async updateArea(id, patch, actor) {
      const area = db.room_areas.find((a) => a.id === id && !a.deleted_at);
      if (!area) throw new Error("Area not found");
      const before = { ...area };
      Object.assign(area, patch);
      const what = patch.label && patch.label !== before.label ? `renamed "${before.label}" to "${patch.label}"` : `changed the "${area.label}" area`;
      log(area.room_id, "area_changed", actor, what, { undo_payload: { kind: "restore_area", area: before, area_id: id } });
      commit(area.room_id);
      return wait(area);
    },

    async deleteArea(id, actor) {
      const area = db.room_areas.find((a) => a.id === id && !a.deleted_at);
      if (!area) throw new Error("Area not found");
      const before = { ...area };
      area.deleted_at = iso();
      log(area.room_id, "area_changed", actor, `removed the "${area.label}" area`, {
        undo_payload: { kind: "restore_area", area: before, area_id: id },
      });
      commit(area.room_id);
      return wait(undefined);
    },

    async uploadPhoto(file) {
      checkImage(file);
      const id = crypto.randomUUID();
      // A real backend would serve the bytes at /photos/{id}; the mock inlines them.
      const photo: StoredPhoto = { id, url: await toDataUrl(file), content_type: file.type, created_at: iso() };
      db.photos.push(photo);
      storage.save(db);
      return wait({ id: photo.id, url: photo.url });
    },

    async postUpdate(roomId, text, photoId, actor) {
      roomById(roomId);
      if (!text.trim() && !photoId) throw new Error("Write something or add a photo");
      let photoUrl: string | null = null;
      if (photoId) {
        const photo = db.photos.find((p) => p.id === photoId);
        if (!photo) throw new Error("That photo didn't upload — try again");
        photoUrl = photo.url;
      }
      const ev = log(roomId, "post", actor, text.trim(), { photo_url: photoUrl });
      commit(roomId);
      return wait(ev);
    },

    async undoEvent(eventId, actor) {
      const ev = db.feed_events.find((e) => e.id === eventId);
      if (!ev?.undo_payload) throw new Error("This can't be undone");
      if (ev.undone_at) throw new Error("Already undone");
      checkNoLaterChanges(ev);
      applyUndo(ev.undo_payload);
      ev.undone_at = iso();
      void actor;
      commit(ev.room_id);
      return wait(undefined);
    },

    async followRoom(roomId, email) {
      const e = email.trim().toLowerCase();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) throw new Error("That email doesn't look right");
      roomById(roomId);
      const existing = db.room_follows.find((f) => f.room_id === roomId && f.email === e);
      // No email is sent here; a repeat restarts the 7 days to confirm, like the server.
      if (!existing) {
        db.room_follows.push({ id: uid("fol"), room_id: roomId, email: e, unsubscribe_token: uid("tok"), created_at: iso(), confirmed_at: null });
      } else if (!existing.confirmed_at) {
        existing.created_at = iso();
      }
      storage.save(db);
      return wait<RoomFollow>({ room_id: roomId, email: e });
    },

    async confirmFollow(token) {
      const f = db.room_follows.find((x) => x.unsubscribe_token === token);
      if (!f) return wait(false);
      if (f.confirmed_at) return wait(true);
      if (now().getTime() - Date.parse(f.created_at) > CONFIRM_WINDOW_MS) return wait(false);
      f.confirmed_at = iso();
      storage.save(db);
      return wait(true);
    },

    async unfollow(token) {
      const before = db.room_follows.length;
      db.room_follows = db.room_follows.filter((f) => f.unsubscribe_token !== token);
      storage.save(db);
      return wait(db.room_follows.length < before);
    },

    subscribe(roomId, fn) {
      if (!listeners.has(roomId)) listeners.set(roomId, new Set());
      listeners.get(roomId)!.add(fn);
      return () => listeners.get(roomId)?.delete(fn);
    },
  };
}
